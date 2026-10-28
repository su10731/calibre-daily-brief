#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
选材：把 recipes/*.recipe 里声明的 FEED_GROUPS + QUOTA 变成 build/picked.json。

Calibre 的配方只有 max_articles_per_feed 这一个全局开关，做不了「前沿 3 + 科普 1 +
物理 1 + 时事 2」这种按类别配额，所以选材在这里用纯标准库做完，Calibre 只负责排版。

用法：
    python scripts/pick_articles.py                 # 抓源、选文、写 build/picked.json
    python scripts/pick_articles.py --print-only    # 只看本期会选哪些，不写文件
    python scripts/pick_articles.py --days 7        # 临时收紧新鲜度窗口

依赖：只用标准库。
"""

import argparse
import concurrent.futures
import datetime as dt
import email.utils
import html as html_mod
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import recipe_config  # noqa: E402

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')

BEIJING = dt.timezone(dt.timedelta(hours=8))


# ---------------------------------------------------------------------------
# 抓 RSS
# ---------------------------------------------------------------------------
def fetch(url, timeout):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/xml, */*',
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def local(tag):
    return tag.rsplit('}', 1)[-1].lower()


def child(entry, *names):
    for node in entry:
        if local(node.tag) in names:
            return node
    return None


def text_of(entry, *names):
    node = child(entry, *names)
    if node is None:
        return ''
    return (node.text or '').strip()


def link_of(entry):
    node = child(entry, 'link')
    if node is not None:
        href = node.get('href')
        rel = (node.get('rel') or 'alternate').lower()
        if href and rel == 'alternate':
            return href.strip()
        if (node.text or '').strip():
            return node.text.strip()
    # Atom 里可能有多个 link，遍历一遍
    for node in entry:
        if local(node.tag) == 'link' and node.get('href'):
            if (node.get('rel') or 'alternate').lower() == 'alternate':
                return node.get('href').strip()
    for name in ('guid', 'id', 'identifier'):
        val = text_of(entry, name)
        if val.startswith('http'):
            return val
    return ''


def parse_long_date(raw):
    """Elsevier 的 RSS 条目没有 pubDate，日期藏在正文的 'Publication date: 1 December 2026' 里。"""
    match = re.search(r'publication date:?\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})', raw, re.I)
    if not match:
        return None
    for fmt in ('%d %B %Y', '%d %b %Y'):
        try:
            return dt.datetime.strptime(match.group(1).strip(), fmt).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
    return None


def parse_date(raw):
    raw = (raw or '').strip()
    if not raw:
        return None
    try:
        val = email.utils.parsedate_to_datetime(raw)
        if val:
            return val if val.tzinfo else val.replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        pass
    try:
        val = dt.datetime.fromisoformat(raw.replace('Z', '+00:00'))
        return val if val.tzinfo else val.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


class _ToText(HTMLParser):
    """把 RSS 里的 HTML 摘成纯文本段落，避免出版社的脏 HTML 把转换搞崩。"""

    BLOCK = ('p', 'br', 'div', 'li', 'dt', 'dd', 'h1', 'h2', 'h3', 'h4',
             'tr', 'table', 'section', 'article', 'dd>')
    SKIP = ('script', 'style', 'head')

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip_depth += 1
        elif tag in self.BLOCK:
            self.out.append('\n')

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip_depth:
            self.skip_depth -= 1
        elif tag in self.BLOCK:
            self.out.append('\n')

    def handle_data(self, data):
        if not self.skip_depth:
            self.out.append(data)

    def paragraphs(self):
        text = ''.join(self.out)
        text = html_mod.unescape(text)
        text = text.replace('\u00a0', ' ')
        parts = [re.sub(r'\s+', ' ', p).strip() for p in text.split('\n')]
        return [p for p in parts if p]


def html_to_paragraphs(raw):
    parser = _ToText()
    try:
        parser.feed(raw or '')
        parser.close()
    except Exception:  # noqa: BLE001  脏 HTML 就退化成转义原文
        return [raw] if raw else []
    return parser.paragraphs()


def image_of(entry, raw_content):
    for node in entry:
        name = local(node.tag)
        if name == 'enclosure' and (node.get('type') or '').startswith('image'):
            return node.get('url') or ''
        if name in ('content', 'thumbnail') and node.get('medium') == 'image':
            return node.get('url') or ''
        if name == 'thumbnail' and node.get('url'):
            return node.get('url')
    match = re.search(r'<img[^>]+src=["\']([^"\']+)', raw_content or '', re.I)
    return match.group(1) if match else ''


def parse_feed(data):
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []
    items = []
    for entry in root.iter():
        if local(entry.tag) not in ('item', 'entry'):
            continue
        title = html_mod.unescape(text_of(entry, 'title')).strip()
        url = link_of(entry)
        if not title or not url:
            continue
        raw = (text_of(entry, 'encoded')
               or text_of(entry, 'content')
               or text_of(entry, 'description', 'summary'))
        paras = html_to_paragraphs(raw)
        if not paras:
            continue
        when = parse_date(text_of(entry, 'pubdate', 'published', 'updated', 'date'))
        if when is None:
            when = parse_long_date(' '.join(paras[:2]))
        author = text_of(entry, 'creator')
        if not author:
            node = child(entry, 'author')
            if node is not None:
                author = text_of(node, 'name') or (node.text or '').strip()
        items.append({
            'title': title,
            'url': url,
            'author': re.sub(r'\s+', ' ', html_mod.unescape(author)).strip()[:120],
            'paras': paras,
            'chars': sum(len(p) for p in paras),
            'image': image_of(entry, raw),
            'when': when,
        })
    return items


# ---------------------------------------------------------------------------
# 摘要补全：Elsevier 的 RSS 只给标题和出处，得从 OpenAlex 的元数据里捞摘要。
# 捞不到就退回标题（标题本身在期刊目录里已经是主要信息量了）。
# ---------------------------------------------------------------------------
def _tokens(text):
    return set(re.findall(r'[0-9a-z一-鿿]+', text.lower()))


def rebuild_abstract(inverted):
    positions = {}
    for word, idxs in (inverted or {}).items():
        for i in idxs:
            positions[i] = word
    return ' '.join(positions[i] for i in sorted(positions))


def openalex_abstract(title, timeout=20.0):
    query = urllib.parse.quote(title[:200])
    url = ('https://api.openalex.org/works?filter=title.search:%s'
           '&per-page=3&select=title,doi,abstract_inverted_index' % query)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'daily-brief/1.0 (个人订阅)'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            results = json.load(resp).get('results', [])
    except Exception:  # noqa: BLE001  补不到就算了，不影响出书
        return ''
    want = _tokens(title)
    if not want:
        return ''
    for work in results:
        inverted = work.get('abstract_inverted_index')
        if not inverted:
            continue
        got = _tokens(work.get('title') or '')
        if len(want & got) / len(want) < 0.6:
            continue  # 标题差太多，多半是另一篇
        text = rebuild_abstract(inverted)
        text = re.sub(r'<[^>]+>', ' ', html_mod.unescape(text))
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > 120:
            return text
    return ''


# ---------------------------------------------------------------------------
# 打分与选取
# ---------------------------------------------------------------------------
def topic_score(item, keywords):
    title = item['title'].lower()
    body = ' '.join(item['paras']).lower()
    score = 0
    for kw in keywords.get('strong', []):
        key = kw.lower()
        if key in title:
            score += 3
        elif key in body:
            score += 1
    for kw in keywords.get('weak', []):
        if kw.lower() in title:
            score += 1
    return score


def pick_diverse(items, count):
    """轮流从各个源取，避免 3 篇前沿全来自同一本期刊。"""
    groups = {}
    for item in items:
        groups.setdefault(item['source'], []).append(item)
    picked = []
    while len(picked) < count and groups:
        for name in list(groups):
            bucket = groups[name]
            if not bucket:
                del groups[name]
                continue
            picked.append(bucket.pop(0))
            if len(picked) >= count:
                break
    return picked


def norm_title(title):
    return re.sub(r'[^0-9a-zA-Z\u4e00-\u9fff]+', '', title).lower()[:120]


def article_id(item):
    return 'u:' + item['url'] if item['url'].startswith('http') else 't:' + norm_title(item['title'])


def load_seen(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
        return {k: v for k, v in data.get('seen', {}).items()}
    except (ValueError, OSError):
        return {}


def save_seen(path, seen, keep_days=60):
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=keep_days)).date().isoformat()
    seen = {k: v for k, v in seen.items() if v >= cutoff}
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump({'seen': seen}, fh, ensure_ascii=False, indent=0, sort_keys=True)


# ---------------------------------------------------------------------------
# 组装
# ---------------------------------------------------------------------------
def build_content(item):
    esc = lambda s: html_mod.escape(s, quote=False)  # noqa: E731
    meta = ' · '.join(x for x in (item['source'], item['date'], item['author']) if x)
    parts = ['<p class="picked-meta">%s</p>' % esc(meta)]
    if item['image']:
        parts.append('<p><img src="%s" alt=""/></p>' % html_mod.escape(item['image'], quote=True))
    for para in item['paras'][:14]:
        parts.append('<p>%s</p>' % esc(para))
    parts.append('<p><a href="%s">原文链接</a></p>' % html_mod.escape(item['url'], quote=True))
    return '\n'.join(parts)


def collect(cfg, timeout, workers, categories=None, verbose=True):
    feeds = [job for job in recipe_config.all_feeds(cfg)
             if categories is None or job[0] in categories]
    pools = {cat: [] for cat in cfg['SECTION_ORDER']}
    failed = []

    def work(job):
        category, name, url = job
        try:
            data = fetch(url, timeout)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            try:
                data = fetch(url, timeout)
            except Exception as exc2:  # noqa: BLE001
                return category, name, url, [], '%s: %s' % (type(exc2).__name__, exc2)
        try:
            items = parse_feed(data)
        except Exception as exc:  # noqa: BLE001
            return category, name, url, [], '解析失败 %s' % type(exc).__name__
        for item in items:
            item['source'] = name
            item['category'] = category
        return category, name, url, items, ''

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for category, name, url, items, err in pool.map(work, feeds):
            if err:
                failed.append((name, err))
            pools[category].extend(items)
            if verbose:
                print('   %-28s %3d 条%s' % (name, len(items), ('  ← ' + err) if err else ''),
                      file=sys.stderr)
    return pools, failed


def choose(cfg, pools, seen, use_history, parts, enrich=True, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    keywords = cfg.get('TOPIC_KEYWORDS', {})
    fresh_days = cfg.get('FRESH_DAYS', {})
    titles = cfg.get('SECTION_TITLES', {})
    scored = set(cfg.get('SCORED', []))
    must_hit = set(cfg.get('REQUIRE_KEYWORD_HIT', []))
    need_body = set(cfg.get('NEEDS_ABSTRACT', []))
    skip = tuple(kw.lower() for kw in cfg.get('EXCLUDE_TITLE', []))
    sections = []
    for category, quota in parts:
        limit = fresh_days.get(category, 30)
        items = pools.get(category, [])
        fresh = []
        for item in items:
            when = item['when'] or now
            if (now - when).days <= limit:
                fresh.append(item)
            item['date'] = when.astimezone(BEIJING).date().isoformat()
        if skip:
            fresh = [it for it in fresh if not any(kw in it['title'].lower() for kw in skip)]

        if category in scored:
            # 关键词打分排序；RSS 自带完整摘要的源略微加分（光有标题的读不了）
            for it in fresh:
                it['score'] = topic_score(it, keywords)
            ranked = sorted(fresh,
                            key=lambda it: (-(it['score'] + (1 if it['chars'] >= 300 else 0)),
                                            it['date']))
            if category in must_hit:
                ranked = [it for it in ranked if it['score'] > 0]
        else:
            for it in fresh:
                it['score'] = 0
            ranked = sorted(fresh, key=lambda it: it['when'] or now, reverse=True)

        unseen = [it for it in ranked if article_id(it) not in seen] if use_history else ranked
        if category in need_body:
            # 候选够用的时候只收带正文/摘要的：Elsevier 的 RSS 光给标题，
            # 一本书里三条只有标题没法读。arXiv / IOP / Quanta 那些源每天都有货。
            rich = [it for it in unseen if it['chars'] >= 300]
            if len(rich) >= quota:
                unseen = rich
        chosen = pick_diverse(unseen, quota)
        if len(chosen) < quota:
            # 去重之后不够配额，就允许重复上期的（宁可重一篇也不要空章节）
            used = {id(it) for it in chosen}
            chosen = chosen + pick_diverse([it for it in ranked if id(it) not in used],
                                           quota - len(chosen))

        if enrich:
            fill_thin_abstracts(chosen)
        for item in chosen:
            item['content'] = build_content(item)
        sections.append({
            'key': category,
            'title': titles.get(category, category),
            'items': chosen,
        })
    return sections


def fill_thin_abstracts(items, threshold=260, workers=4):
    """正文太短的（Elsevier 那类只给标题的），去 OpenAlex 捞一次摘要。"""
    thin = [item for item in items if item['chars'] < threshold]
    if not thin:
        return 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        texts = list(pool.map(lambda it: openalex_abstract(it['title']), thin))
    filled = 0
    for item, text in zip(thin, texts):
        if text:
            item['paras'] = [text]
            item['chars'] = len(text)
            item['from_openalex'] = True
            filled += 1
    return filled


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:  # noqa: BLE001
        pass

    ap = argparse.ArgumentParser(description='按类别配额挑选本期文章')
    ap.add_argument('--recipe', default=recipe_config.DEFAULT_RECIPE)
    ap.add_argument('--book', help='书名，见配方里的 BOOKS；默认 %s' % 'daily')
    ap.add_argument('--list-books', action='store_true', help='列出所有书和它们的篇数构成')
    ap.add_argument('--out', default='build/picked.json')
    ap.add_argument('--state', default='state/seen.json')
    ap.add_argument('--days', type=int, help='覆盖配方里的新鲜度窗口（所有类别用同一个值）')
    ap.add_argument('--timeout', type=float, default=25.0)
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--print-only', action='store_true', help='只打印选中的文章，不写文件、不更新历史')
    ap.add_argument('--no-history', action='store_true', help='不做跨天去重')
    ap.add_argument('--no-enrich', action='store_true', help='短正文不去 OpenAlex 补摘要')
    args = ap.parse_args()

    cfg = recipe_config.load(args.recipe)
    book_key = args.book or cfg.get('DEFAULT_BOOK', 'daily')
    book_title, parts = recipe_config.resolve_book(cfg, book_key)

    if args.list_books:
        print('可选的书（--book 用冒号前的键名）：')
        for name, (title, book_parts) in cfg['BOOKS'].items():
            text = ' + '.join('%s %s' % (cfg['SECTION_TITLES'].get(c, c),
                                          q or cfg['QUOTA'].get(c, 1)) for c, q in book_parts)
            print('  %-14s 《%s》  %s（共 %d 篇）'
                  % (name, title, text, sum(q or cfg['QUOTA'].get(c, 1) for c, q in book_parts)))
        return 0

    if args.days:
        cfg['FRESH_DAYS'] = {k: args.days for k in cfg['FRESH_DAYS']}

    wanted = [c for c, _ in parts]
    quota_text = ' + '.join('%s %d' % (cfg['SECTION_TITLES'].get(c, c), q) for c, q in parts)
    feeds = [job for job in recipe_config.all_feeds(cfg) if job[0] in wanted]
    proxy_hint = ''
    needs_proxy = set(cfg.get('NEEDS_PROXY', []))
    if any(c in needs_proxy for c in wanted):
        proxy_hint = '（含需要代理的大类：%s）' % '、'.join(c for c in wanted if c in needs_proxy)
    print('《%s》选材：%s（共 %d 篇），候选源 %d 个%s'
          % (book_title, quota_text, sum(q for _, q in parts), len(feeds), proxy_hint))
    pools, failed = collect(cfg, args.timeout, args.workers, categories=set(wanted))

    seen = {} if args.no_history else load_seen(args.state)
    sections = choose(cfg, pools, seen, use_history=not args.no_history,
                      parts=parts, enrich=not args.no_enrich)

    total = 0
    filled = 0
    for section, (_, quota) in zip(sections, parts):
        print('\n== %s（%d/%d）' % (section['title'], len(section['items']), quota))
        for item in section['items']:
            total += 1
            tag = ' [%s]' % item['score'] if item.get('score') else ''
            if item.get('from_openalex'):
                filled += 1
                tag += ' [补摘要]'
            print('  · %s%s — %s  %s' % (item['title'][:78], tag, item['source'], item['date']))
    if filled:
        print('\n从 OpenAlex 补回了 %d 篇原本只有标题的摘要' % filled)
    if not total:
        print('\n!! 一篇都没选到：网络不通（这一类要不要代理？），或者全部被去重挡掉。'
              '失败源前 5 个：%s' % [name for name, _ in failed[:5]])
        return 1

    if failed:
        print('\n抓取的 %d 个源里 %d 个失败：%s'
              % (len(feeds), len(failed), '; '.join('%s(%s)' % f for f in failed[:6])))

    if args.print_only:
        print('\n--print-only：没写 %s' % args.out)
        return 0

    payload = {
        'book': book_title,
        'book_key': book_key,
        'generated': dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec='seconds'),
        'sections': [{
            'key': s['key'],
            'title': s['title'],
            'items': [{
                'title': i['title'],
                'url': i['url'],
                'author': i['author'],
                'date': i['date'],
                'source': i['source'],
                'content': i['content'],
            } for i in s['items']],
        } for s in sections],
    }
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print('\n已写出 %s' % args.out)

    if not args.no_history:
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        for section in sections:
            for item in section['items']:
                # 同一篇新闻常被两个源用不同链接转发，标题也一起记账
                seen[article_id(item)] = today
                seen['t:' + norm_title(item['title'])] = today
        save_seen(args.state, seen)
        print('已更新去重记录 %s（%d 条）' % (args.state, len(seen)))
    return 0


if __name__ == '__main__':
    sys.exit(main())

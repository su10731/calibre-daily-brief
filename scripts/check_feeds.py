#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
源可达性自检：从 Calibre 配方文件里读出 FEEDS 列表，逐个探测能不能拿到 RSS。

用途有两个：
  1. 在 GitHub Actions 里先看海外 runner 侧哪些源是通的（和你本地网络的结论常常相反）；
  2. 本地加了新源之后，先确认地址没错再提交。

用法：
    python3 scripts/check_feeds.py                       # 默认检查 recipes/daily-science-brief.recipe
    python3 scripts/check_feeds.py recipes/xxx.recipe --timeout 25 --strict

依赖：只用 Python 标准库，不需要 pip install。
"""

import argparse
import ast
import concurrent.futures
import re
import ssl
import sys
import urllib.error
import urllib.request

UA = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')

FEED_NAME = 'FEEDS'


def extract_feeds(recipe_path):
    """用 AST 从配方源码里取出 FEEDS 常量，避免 import calibre 包。"""
    with open(recipe_path, encoding='utf-8') as fh:
        tree = ast.parse(fh.read(), filename=recipe_path)

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if FEED_NAME not in names or not isinstance(node.value, ast.List):
            continue
        feeds = []
        for item in node.value.elts:
            if isinstance(item, (ast.Tuple, ast.List)) and len(item.elts) == 2:
                title = getattr(item.elts[0], 'value', None)
                url = getattr(item.elts[1], 'value', None)
                if isinstance(title, str) and isinstance(url, str):
                    feeds.append((title, url))
        return feeds
    return []


def probe(title, url, timeout):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/xml, */*',
        'Accept-Encoding': 'identity',
    })
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            status = resp.getcode()
            ctype = resp.headers.get('Content-Type', '') or ''
            body = resp.read(400_000).decode('utf-8', errors='replace').lower()
    except urllib.error.HTTPError as exc:
        return title, url, str(exc.code), '', 0, 'HTTP 错误'
    except urllib.error.URLError as exc:
        reason = str(exc.reason)
        kind = 'DNS 失败' if 'getaddrinfo' in reason else ('超时' if 'timed out' in reason else '连接失败')
        return title, url, '000', '', 0, kind
    except Exception as exc:  # noqa: BLE001  任何异常都只报告，不中断
        return title, url, 'ERR', '', 0, type(exc).__name__

    items = len(re.findall(r'<item[\s>]', body)) + len(re.findall(r'<entry[\s>]', body))
    looks_like_feed = bool(re.search(r'<(rss|feed|rdf:rdf)[\s>]', body))
    note = ''
    if not looks_like_feed and items == 0:
        note = '不是 RSS/Atom（可能是 HTML 页面或被反爬拦截）'
    elif not looks_like_feed:
        note = '没认出 rss/feed 根标签，但有条目，多半能用'
    elif items == 0:
        note = '是 XML 但没有任何条目'
    return title, url, str(status), ctype.split(';')[0], items, note


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:  # noqa: BLE001
        pass

    ap = argparse.ArgumentParser(description='检查 Calibre 配方里的 RSS 源是否可达')
    ap.add_argument('recipe', nargs='?', default='recipes/daily-science-brief.recipe')
    ap.add_argument('--timeout', type=float, default=20.0, help='单个源的超时秒数，默认 20')
    ap.add_argument('--workers', type=int, default=6, help='并发数，默认 6')
    ap.add_argument('--strict', action='store_true',
                    help='一个源都拿不到时以非 0 退出（默认永远返回 0，不阻塞出书）')
    ap.add_argument('--no-retry', action='store_true', help='失败的源不重试第二轮')
    args = ap.parse_args()

    feeds = extract_feeds(args.recipe)
    if not feeds:
        print(f'!! 在 {args.recipe} 里没解析出 FEEDS 列表（格式应为 ("名称", "https://...")）')
        return 1 if args.strict else 0

    print(f'检查 {args.recipe} 中的 {len(feeds)} 个源（超时 {args.timeout:g}s）\n')
    width = max(len(t) for t, _ in feeds)

    def probe_all(targets):
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            return list(pool.map(lambda tu: probe(tu[0], tu[1], args.timeout), targets))

    results = probe_all(feeds)

    def usable(row):
        return row[2] == '200' and row[4] > 0

    if not args.no_retry:
        # 单次失败常常只是本机网络抖动，失败的源串行重试一轮再下结论
        for i, (title, url) in enumerate(feeds):
            if not usable(results[i]):
                retry = probe(title, url, args.timeout)
                if usable(retry):
                    results[i] = retry

    ok = sum(1 for row in results if usable(row))
    for title, url, status, ctype, items, note in results:
        flag = 'OK  ' if usable((title, url, status, ctype, items, note)) else 'WARN'
        extra = f'{items} 条' if items else '0 条'
        if ctype:
            extra += f' / {ctype}'
        print(f'{flag} {title.ljust(width)}  {status:>4}  {extra:<32} {note}')

    print(f'\n汇总：{ok}/{len(feeds)} 个源在当前位置可用。')
    print('提示：GitHub Actions 的 runner 在海外，国内被墙的源（Google News、Guardian 等）'
          '在那边通常是通的；反过来 rsshub.app 这类公共实例在云端 IP 上容易被限流。')
    if args.strict and ok == 0:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

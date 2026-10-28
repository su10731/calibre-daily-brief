#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地出书：选材 → 调 Calibre 排版 → 打印本期目录。双击根目录的 0-*.bat ~ 8-*.bat 跑的就是这个。

用法：
    python scripts/build_brief.py --list-books          # 有哪些书、各几篇
    python scripts/build_brief.py --book science        # 出"科学前沿"这本
    python scripts/build_brief.py                       # 默认出 daily 这本
    python scripts/build_brief.py --book daily --open   # 出完直接用默认阅读器打开
    python scripts/build_brief.py --skip-pick           # 沿用上次选材，只重排一遍

同一天可以反复跑：文件名带到秒的时间戳，不会互相覆盖；而且上一期选过的文章已经
记进 state/seen.json，下一次会自动换新的。

依赖：本机装有 Calibre（ebook-convert）。找不到时看 CALIBRE_HINTS。
"""

import argparse
import datetime as dt
import glob
import json
import os
import shutil
import socket
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import recipe_config  # noqa: E402

BEIJING = dt.timezone(dt.timedelta(hours=8))

CALIBRE_HINTS = [
    r'D:\Program\Calibre2\ebook-convert.exe',
    r'C:\Program Files\Calibre2\ebook-convert.exe',
    r'%LOCALAPPDATA%\Programs\Calibre\ebook-convert.exe',
]

# 常见的本地代理端口（Clash / mihomo / v2rayN 那一类），探到就顺手把国外那两本书打开
PROXY_PORTS = [7890, 7897, 10808, 10809, 8118, 33210, 12781]


def find_ebook_convert():
    """优先环境变量 → PATH → 常见安装位置。CI 上装完 Calibre 走 PATH 那条。"""
    override = os.environ.get('EBOOK_CONVERT')
    if override:
        return override if os.path.exists(override) else None
    found = shutil.which('ebook-convert')
    if found:
        return found
    for candidate in CALIBRE_HINTS:
        path = os.path.expandvars(candidate)
        if os.path.exists(path):
            return path
    return None


def detect_proxy():
    """本机有没有在跑的代理？返回 'http://127.0.0.1:端口' 或 None。"""
    for port in PROXY_PORTS:
        sock = socket.socket()
        sock.settimeout(0.3)
        try:
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                return 'http://127.0.0.1:%d' % port
        finally:
            sock.close()
    return None


def prune(directory, prefix, keep):
    """只清理同一本书的旧文件，别把其它大类的书删掉。"""
    books = sorted(glob.glob(os.path.join(directory, '%s-*.epub' % prefix)),
                   key=os.path.getmtime, reverse=True)
    for stale in books[keep:]:
        try:
            os.remove(stale)
            print('已删掉过期的书：%s' % os.path.basename(stale))
        except OSError as exc:
            print('!! 删除 %s 失败：%s' % (stale, exc))


def summarize(picked_path):
    try:
        with open(picked_path, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return
    for section in data.get('sections', []):
        print('   %-24s %d 篇' % (section['title'], len(section['items'])))


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:  # noqa: BLE001
        pass

    ap = argparse.ArgumentParser(description='本地生成《每日科学简报》EPUB')
    ap.add_argument('--recipe', default=os.path.join(ROOT, 'recipes', 'daily-science-brief.recipe'))
    ap.add_argument('--book', help='书名，见 --list-books；默认用配方里的 DEFAULT_BOOK')
    ap.add_argument('--list-books', action='store_true', help='列出所有书及其篇数构成')
    ap.add_argument('--dir', default=os.path.join(ROOT, 'out'), help='输出目录，默认 out/')
    ap.add_argument('--out', help='指定完整文件名（云端用固定名）；给了它就按原名写，不清理旧书')
    ap.add_argument('--picked', help='选材结果文件路径；默认 build/picked-<书>.json')
    ap.add_argument('--keep', type=int, default=14, help='同一本书最多留几本，默认 14')
    ap.add_argument('--days', type=int, help='透传给 pick_articles.py 的新鲜度窗口')
    ap.add_argument('--no-proxy', action='store_true', help='不自动使用本机代理')
    ap.add_argument('--skip-pick', action='store_true', help='不重新选材，直接用已有 picked.json')
    ap.add_argument('--open', action='store_true', help='生成后用默认程序打开')
    args = ap.parse_args()

    cfg = recipe_config.load(args.recipe)
    book_key = args.book or cfg.get('DEFAULT_BOOK', 'daily')
    book_title, parts = recipe_config.resolve_book(cfg, book_key)

    if args.list_books:
        print('可选的书（bat 和 --book 用的都是冒号前的键名）：')
        for name, (title, book_parts) in cfg['BOOKS'].items():
            text = ' + '.join('%s %d' % (cfg['SECTION_TITLES'].get(c, c),
                                          q or cfg['QUOTA'].get(c, 1)) for c, q in book_parts)
            total = sum(q or cfg['QUOTA'].get(c, 1) for c, q in book_parts)
            hint = '  ← 需要代理' if any(c in cfg.get('NEEDS_PROXY', []) for c, _ in book_parts) else ''
            print('  %-14s 《%s》 %s（%d 篇）%s' % (name, title, text, total, hint))
        return 0

    picked = args.picked or os.path.join(ROOT, 'build', 'picked-%s.json' % book_key)
    categories = [c for c, _ in parts]
    wants_proxy = any(c in cfg.get('NEEDS_PROXY', []) for c in categories)

    env = dict(os.environ)
    if wants_proxy and not args.no_proxy and not (env.get('HTTPS_PROXY') or env.get('https_proxy')):
        proxy = detect_proxy()
        if proxy:
            env['HTTP_PROXY'] = env['HTTPS_PROXY'] = proxy
            print('检测到本机代理 %s，这一本里的国外源走代理' % proxy)
        else:
            print('提示：这一本含需要代理的国外源，但没探到本机代理端口 %s。'
                  '空章节是正常的，也可以交给云端每天跑（见 README）。'
                  % ', '.join(str(p) for p in PROXY_PORTS))

    converter = find_ebook_convert()
    if not converter:
        print('!! 没找到 ebook-convert。装一下 Calibre：https://calibre-ebook.com/download_windows')
        print('   装完如果不在默认位置，设环境变量 EBOOK_CONVERT 指向 ebook-convert.exe。')
        return 2

    if not args.skip_pick:
        cmd = [sys.executable, os.path.join(HERE, 'pick_articles.py'),
               '--book', book_key, '--out', picked]
        if args.days:
            cmd += ['--days', str(args.days)]
        code = subprocess.call(cmd, env=env)
        if code != 0:
            print('!! 选材步骤失败（退出码 %s），没生成书。' % code)
            return code
    elif not os.path.exists(picked):
        print('!! --skip-pick 但 %s 不存在' % picked)
        return 1

    stamp = dt.datetime.now(BEIJING).strftime('%Y-%m-%d-%H%M%S')
    book = args.out or os.path.join(args.dir, '%s-%s.epub' % (book_title, stamp))
    os.makedirs(os.path.dirname(os.path.abspath(book)), exist_ok=True)

    env['BRIEF_PICKED'] = os.path.abspath(picked)
    print('\n开始排版（Calibre）：%s' % os.path.basename(converter))
    # 书名不通过命令行传（ebook-convert 没这个选项），由配方读 picked.json 里的 book
    code = subprocess.call([converter, args.recipe, book], cwd=ROOT, env=env)
    if code != 0 or not os.path.exists(book) or os.path.getsize(book) == 0:
        print('!! ebook-convert 退出码 %s，书没生成。' % code)
        return code or 1

    mb = os.path.getsize(book) / 1048576.0
    print('\n《%s》生成完毕：%.1f MB' % (book_title, mb))
    summarize(picked)
    print('\n文件位置：%s' % os.path.abspath(book))
    if mb > 10:
        print('提示：超过 10 MB，发邮件或推 Kindle 可能被拒收，可把配方里对应大类的 QUOTA 调小。')

    if not args.out:
        prune(args.dir, book_title, args.keep)

    if args.open:
        if hasattr(os, 'startfile'):
            os.startfile(book)
        else:
            print('（当前系统不能直接打开，请手动双击文件）')
    return 0


if __name__ == '__main__':
    sys.exit(main())

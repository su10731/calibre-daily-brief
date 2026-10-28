#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地出书：选材 → 调 Calibre 排版 → 打印本期目录。双击 daily-brief.bat 跑的就是这个。

用法：
    python scripts/build_brief.py                 # 生成 out/每日科学简报-YYYY-MM-DD.epub
    python scripts/build_brief.py --open          # 生成完直接用默认阅读器打开
    python scripts/build_brief.py --skip-pick     # 沿用上次选材结果，只重排一遍
    python scripts/build_brief.py --days 7        # 传给 pick_articles.py 的新鲜度窗口

依赖：本机装有 Calibre（ebook-convert）。找不到时看下面的 CALIBRE_HINTS。
"""

import argparse
import datetime as dt
import glob
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

CALIBRE_HINTS = [
    r'D:\Program\Calibre2\ebook-convert.exe',
    r'C:\Program Files\Calibre2\ebook-convert.exe',
    r'%LOCALAPPDATA%\Programs\Calibre\ebook-convert.exe',
]


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


def prune(directory, keep):
    books = sorted(glob.glob(os.path.join(directory, '*.epub')), key=os.path.getmtime, reverse=True)
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
        print('   %-22s %d 篇' % (section['title'], len(section['items'])))


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:  # noqa: BLE001
        pass

    ap = argparse.ArgumentParser(description='本地生成《每日科学简报》EPUB')
    ap.add_argument('--recipe', default=os.path.join(ROOT, 'recipes', 'daily-science-brief.recipe'))
    ap.add_argument('--dir', default=os.path.join(ROOT, 'out'), help='输出目录，默认 out/')
    ap.add_argument('--out', help='完整输出文件名；不给就用 每日科学简报-<北京日期>.epub')
    ap.add_argument('--picked', default=os.path.join(ROOT, 'build', 'picked.json'))
    ap.add_argument('--keep', type=int, default=14, help='out/ 里最多保留几本，默认 14')
    ap.add_argument('--days', type=int, help='透传给 pick_articles.py')
    ap.add_argument('--skip-pick', action='store_true', help='不重新选材，直接用已有 picked.json')
    ap.add_argument('--open', action='store_true', help='生成后用默认程序打开')
    args = ap.parse_args()

    converter = find_ebook_convert()
    if not converter:
        print('!! 没找到 ebook-convert。装一下 Calibre：https://calibre-ebook.com/download_windows')
        print('   装完如果不在默认位置，设环境变量 EBOOK_CONVERT 指向 ebook-convert.exe。')
        return 2

    if not args.skip_pick:
        cmd = [sys.executable, os.path.join(HERE, 'pick_articles.py'), '--out', args.picked]
        if args.days:
            cmd += ['--days', str(args.days)]
        code = subprocess.call(cmd)
        if code != 0:
            print('!! 选材步骤失败（退出码 %s），没生成书。' % code)
            return code
    elif not os.path.exists(args.picked):
        print('!! --skip-pick 但 %s 不存在' % args.picked)
        return 1

    beijing = dt.timezone(dt.timedelta(hours=8))
    book = args.out or os.path.join(
        args.dir, '每日科学简报-%s.epub' % dt.datetime.now(beijing).date().isoformat())
    os.makedirs(os.path.dirname(os.path.abspath(book)), exist_ok=True)

    env = dict(os.environ, BRIEF_PICKED=os.path.abspath(args.picked))
    print('\n开始排版（Calibre）：%s' % os.path.basename(converter))
    code = subprocess.call([converter, args.recipe, book], cwd=ROOT, env=env)
    if code != 0 or not os.path.exists(book) or os.path.getsize(book) == 0:
        print('!! ebook-convert 退出码 %s，书没生成。' % code)
        return code or 1

    mb = os.path.getsize(book) / 1048576.0
    print('\n《每日科学简报》%s 生成完毕：%.1f MB' % (os.path.basename(book), mb))
    summarize(args.picked)
    print('\n文件位置：%s' % os.path.abspath(book))
    if mb > 10:
        print('提示：超过 10 MB，发邮件或推 Kindle 可能被拒收，可调小配方里的 QUOTA。')

    prune(args.dir, args.keep)

    if args.open:
        if hasattr(os, 'startfile'):
            os.startfile(book)
        else:
            print('（当前系统不能直接打开，请手动双击文件）')
    return 0


if __name__ == '__main__':
    sys.exit(main())

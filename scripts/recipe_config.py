# -*- coding: utf-8 -*-
"""
从 Calibre 配方文件里读出选材配置（QUOTA / FEED_GROUPS / TOPIC_KEYWORDS …）。

配方文件顶部 `from calibre.web.feeds.news import BasicNewsRecipe`，普通 python
解释器 import 不了；这里只用 ast 把几个常量字面量抠出来，保证配方文件是唯一的
配置出处，改源不用两边同步。
"""

import ast

CONFIG_NAMES = (
    'QUOTA',
    'SECTION_TITLES',
    'FRESH_DAYS',
    'FEED_GROUPS',
    'TOPIC_KEYWORDS',
    'EXCLUDE_TITLE',
    'SECTION_ORDER',
)

DEFAULT_RECIPE = 'recipes/daily-science-brief.recipe'


def load(path=DEFAULT_RECIPE):
    with open(path, encoding='utf-8') as fh:
        tree = ast.parse(fh.read(), filename=path)

    cfg = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in CONFIG_NAMES:
                try:
                    cfg[target.id] = ast.literal_eval(node.value)
                except ValueError:
                    pass
    missing = [name for name in ('QUOTA', 'FEED_GROUPS', 'SECTION_ORDER') if name not in cfg]
    if missing:
        raise SystemExit('!! 配方 %s 里缺少配置：%s' % (path, ', '.join(missing)))
    return cfg


def all_feeds(cfg):
    """展开成 [(类别, 源名, 地址), ...]，顺序与配方里的书写顺序一致。"""
    out = []
    for category in cfg['SECTION_ORDER']:
        for name, url in cfg['FEED_GROUPS'].get(category, []):
            out.append((category, name, url))
    return out

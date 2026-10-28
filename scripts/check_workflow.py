"""轻量校验 workflow：缩进解析 run 块 → 把 ${{ }} 换成占位符 → bash -n；再查 steps.<id>.outputs 引用。"""
import io
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
PATH = '.github/workflows/daily-brief.yml'
raw = io.open(PATH, encoding='utf-8').read()
lines = raw.split('\n')

steps = []          # [(name, id, [run lines])]
current = None
in_run = False
i = 0
while i < len(lines):
    line = lines[i]
    stripped = line.strip()
    if re.match(r'^      - ', line):
        if current:
            steps.append(current)
        current = {'name': '', 'id': '', 'run': None}
        in_run = False
    if current is not None and stripped.startswith('- name:'):
        current['name'] = stripped.split('- name:', 1)[1].strip()
    elif current is not None and stripped.startswith('id:'):
        current['id'] = stripped.split('id:', 1)[1].strip()
    elif current is not None and stripped.startswith('run:'):
        if stripped == 'run: |':
            in_run = True
            current['run'] = []
        else:
            current['run'] = [stripped.split('run:', 1)[1].strip()]
            in_run = False
    elif in_run:
        if line.strip() == '' or line.startswith('          '):
            current['run'].append(line[10:] if line.strip() else '')
        else:
            in_run = False
    i += 1
if current:
    steps.append(current)

ids = [s['id'] for s in steps if s['id']]
print('步骤 %d 个，带 id 的：%s' % (len(steps), ids))

refs = set(re.findall(r'steps\.([a-zA-Z0-9_-]+)\.outputs\.([a-zA-Z0-9_]+)', raw))
dangling = [(a, b) for a, b in refs if a not in ids]
print('steps.*.outputs 悬空引用：%s' % (dangling or '无'))

fails = 0
for s in steps:
    if not s['run']:
        continue
    body = re.sub(r'\$\{\{[^}]*\}\}', 'X', '\n'.join(s['run']))
    proc = subprocess.run(['bash', '-n'], input=body.encode('utf-8'), capture_output=True)
    mark = 'OK  ' if proc.returncode == 0 else 'FAIL'
    if proc.returncode != 0:
        fails += 1
    err = proc.stderr.decode('utf-8', 'replace')[:220].replace('\n', ' | ')
    print('  %s %-28s %s' % (mark, s['name'][:28], err))

# heredoc 里的 python 代码缩进是否被 YAML 块剥干净（跑一遍 py_compile 看语法）
for s in steps:
    if not s['run']:
        continue
    for match in re.finditer(r"<<'PY'\n(.*?)\n\s*PY\n", '\n'.join(s['run']), re.S):
        code = match.group(1)
        try:
            compile(code, '<inline>', 'exec')
        except SyntaxError as exc:
            fails += 1
            print('  FAIL 内嵌 Python（步骤《%s》）：%s' % (s['name'], exc))
print('\n结果：%s' % ('全部通过' if fails == 0 else '%d 处有问题' % fails))

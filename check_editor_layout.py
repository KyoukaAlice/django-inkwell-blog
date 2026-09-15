"""检查写文章页的模板结构与排版相关类是否齐全。

    python check_editor_layout.py
"""
import os
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
TEMPLATE = BASE / 'blog' / 'templates' / 'blog' / 'post_form.html'
CSS = BASE / 'static' / 'css' / 'style.css'

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'DjangoBlog.settings')
sys.path.insert(0, str(BASE))
import django                                     # noqa: E402

django.setup()

from django.template.loader import get_template    # noqa: E402

problems = []

# ---------- 1. 模板能否编译 ----------
try:
    get_template('blog/post_form.html')
    print('  [OK]   模板编译通过（Django 标签语法正确）')
except Exception as exc:                           # noqa: BLE001
    problems.append(f'模板编译失败：{exc}')
    print(f'  [FAIL] 模板编译失败：{exc}')

html = TEMPLATE.read_text(encoding='utf-8')
css = CSS.read_text(encoding='utf-8')

# ---------- 2. div 配对 ----------
content = html.split('{% block content %}')[1].split('{% endblock %}')[0]
opens = len(re.findall(r'<div\b', content))
closes = len(re.findall(r'</div>', content))
if opens == closes:
    print(f'  [OK]   div 配对正确（{opens} 开 / {closes} 闭）')
else:
    problems.append(f'div 不配对：{opens} 开 vs {closes} 闭')
    print(f'  [FAIL] div 不配对：{opens} 开 / {closes} 闭')

# ---------- 3. 排版用的类名是否都在模板里 ----------
NEEDED_CLASSES = ['editor-layout', 'editor-main', 'editor-card',
                  'editor-card-body', 'editor-grow', 'editor-side']
for cls in NEEDED_CLASSES:
    if cls in content:
        print(f'  [OK]   模板里有 .{cls}')
    else:
        problems.append(f'模板缺少 .{cls}')
        print(f'  [FAIL] 模板缺少 .{cls}')

# ---------- 4. CSS 里是否定义了这些类 ----------
for cls in NEEDED_CLASSES:
    if re.search(r'\.' + cls + r'\b', css):
        print(f'  [OK]   CSS 定义了 .{cls}')
    else:
        problems.append(f'CSS 缺少 .{cls} 的定义')
        print(f'  [FAIL] CSS 缺少 .{cls} 的定义')

# ---------- 5. 关键布局属性的检查 ----------
checks = [
    ('editor-layout 用 stretch 让两栏等高',
     re.search(r'\.editor-layout\s*\{[^}]*align-items:\s*stretch', css, re.S)),
    ('正文 textarea 会撑满（flex: 1 1 auto）',
     re.search(r'\.editor-grow\s+\.markdown-editor\s*\{[^}]*flex:\s*1 1 auto', css, re.S)),
    ('正文 textarea 有 min-height 兜底',
     re.search(r'\.editor-grow\s+\.markdown-editor\s*\{[^}]*min-height', css, re.S)),
    # 这条是回归守卫：grid 的 align-self 同时影响横轴，给侧栏加 start 会让它
    # 收缩成内容宽度，卡片右边空出一条。曾经这么写过，所以固化成检查项。
    ('右栏没有 align-self: start（否则卡片右边会空一块）',
     not re.search(r'\.editor-side\s*\{[^}]*align-self', css, re.S)),
    ('右栏卡片宽度撑满（没有 width: fit-content 之类）',
     not re.search(r'\.editor-side[^{]*\{[^}]*width:\s*(fit-content|max-content|min-content)', css, re.S)),
    ('窄屏回退成单栏',
     re.search(r'@media \(max-width: 1000px\)\s*\{[^}]*\.editor-layout', css, re.S)),
]
for label, matched in checks:
    if matched:
        print(f'  [OK]   {label}')
    else:
        problems.append(label)
        print(f'  [FAIL] {label}')

print()
if problems:
    print(f'发现 {len(problems)} 个问题：')
    for p in problems:
        print(f'  - {p}')
    sys.exit(1)
print('结果：写文章页的排版结构检查全部通过 ✅')

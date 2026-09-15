"""检查写文章页的模板结构与排版，专门防已经踩过的几个坑。

    python check_editor_layout.py

固化的回归项（每一个都是真实踩过的 bug）：
  1. 不能清空 base.html 的 sidebar block —— 否则右侧整条是白的
  2. 不能重复 include sidebar.html —— 否则侧边栏渲染两份
  3. 正文编辑器全宽单列，不再和设置栏并排 —— 并排必留空白
  4. 正文 textarea 要有 min-height 兜底
  5. div 必须配对（改这块时很容易漏闭合标签）
"""
import os
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
TEMPLATE = BASE / 'blog' / 'templates' / 'blog' / 'post_form.html'
CSS = BASE / 'static' / 'css' / 'style.css'
SIDEBAR_PARTIAL = BASE / 'blog' / 'templates' / 'blog' / 'partials' / 'sidebar.html'

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'DjangoBlog.settings')
sys.path.insert(0, str(BASE))
import django                                      # noqa: E402

django.setup()

from django.template.loader import get_template     # noqa: E402

problems = []


def check(label, ok, detail=''):
    if ok:
        print(f'  [OK]   {label}')
    else:
        problems.append(label + (f'：{detail}' if detail else ''))
        print(f'  [FAIL] {label}{"：" + detail if detail else ""}')


# ---------- 1. 模板能否编译 ----------
try:
    get_template('blog/post_form.html')
    check('模板编译通过（Django 标签语法正确）', True)
except Exception as exc:                            # noqa: BLE001
    check('模板编译通过', False, str(exc))
    print('\n模板都编译不了，后面的检查没意义，先修语法。')
    sys.exit(1)

html = TEMPLATE.read_text(encoding='utf-8')
css = CSS.read_text(encoding='utf-8')
content = html.split('{% block content %}')[1].split('{% endblock %}')[0]

# ---------- 2. div 配对 ----------
opens = len(re.findall(r'<div\b', content))
closes = len(re.findall(r'</div>', content))
check(f'div 配对（{opens} 开 / {closes} 闭）', opens == closes)

# ---------- 3. 侧边栏坑（回归守卫）----------
check('没有清空 base 的 sidebar block（清了右侧会整条空白）',
      not re.search(r'\{%\s*block\s+sidebar\s*%\}\s*\{%\s*endblock\s*%\}', html))

sidebar_raises = len(re.findall(r"\{%\s*include\s+'blog/partials/sidebar.html'\s*%\}", html))
check(f'没有重复 include 侧边栏（当前 {sidebar_raises} 次，应为 0）', sidebar_raises == 0)

# ---------- 4. 结构：全宽单列 ----------
check('正文区用 .editor-main 且不再有并排的设置栏',
      'editor-main' in content and 'editor-side' not in content
      and 'editor-layout' not in content)
check('设置项用 .settings-grid 横向铺开', 'settings-grid' in content)

# CSS 里不应该再留着已废弃的两栏规则
for dead in ('.editor-layout', '.editor-side', '.editor-aside'):
    check(f'CSS 里没有残留废弃规则 {dead}', dead not in css)

# ---------- 5. 表单字段齐全 ----------
# 注意：模板里写的是 {{ form.xxx }}，渲染后才有 name="xxx"，
# 所以这里检查模板源码里的表单变量，而不是 HTML 属性。
for field in ('title', 'content', 'excerpt', 'status', 'category',
              'tags_input', 'cover'):
    check(f'表单字段 {field} 有渲染', f'form.{field}' in html)

# ---------- 6. 正文高度兜底 ----------
check('正文 textarea 有 min-height 兜底',
      re.search(r'\.editor-grow\s+\.markdown-editor\s*\{[^}]*min-height', css, re.S))
check('窄屏有单独的高度回退',
      re.search(r'@media\s*\(max-width:\s*700px\)', css))

# ---------- 7. 侧边栏组件本身还在（否则 base 会渲染空 aside）----------
check('partials/sidebar.html 仍然存在', SIDEBAR_PARTIAL.is_file())

print()
if problems:
    print(f'发现 {len(problems)} 个问题：')
    for p in problems:
        print(f'  - {p}')
    sys.exit(1)
print('结果：写文章页的排版结构检查全部通过 ✅')

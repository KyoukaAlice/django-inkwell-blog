"""检查**渲染后**的写文章页（快照 HTML），确认最终结构正确。

和 check_editor_layout.py 的分工：
  * check_editor_layout.py  —— 查模板源码 + CSS 规则（构建前就能跑）
  * 本脚本                  —— 查渲染结果（能发现模板里 include 重复、
                              条件分支没生效这类只在输出里暴露的问题）

    python check_editor_snapshot.py
"""
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
DOCS = BASE / 'docs'

FILES = [
    ('写文章（新建）', 'post-create.html'),
    ('编辑文章', 'post/1/edit.html'),
]

# 侧边栏的卡片：每个都应恰好出现 1 次（重复 include 会变成 2 次）
SIDEBAR_WIDGETS = ['📊 站点数据', '🔥 热门文章', '📂 文章分类']

# 页内（表单里）的卡片
FORM_CARDS = ['⚙️ 发布设置', '👀 摘要', '📖 Markdown 速查']

# 已废弃的两栏布局类，渲染结果里不该再出现
DEAD_CLASSES = ['editor-layout', 'editor-side', 'editor-aside']

problems = []


def check(label, ok, detail=''):
    if ok:
        print(f'  [OK]   {label}')
    else:
        problems.append(f'{label}{"：" + detail if detail else ""}')
        print(f'  [FAIL] {label}{"：" + detail if detail else ""}')


def count(html, needle):
    return len(re.findall(re.escape(needle), html))


for label, rel in FILES:
    path = DOCS / rel
    print(f'\n--- {label}  ({rel}) ---')
    if not path.is_file():
        print('  [SKIP] 文件不存在，先跑 manage.py build_snapshot')
        continue

    html = path.read_text(encoding='utf-8')
    print(f'  大小 {len(html.encode("utf-8")) / 1024:.1f} KB')

    # 1. 侧边栏各 1 次
    for widget in SIDEBAR_WIDGETS:
        n = count(html, f'widget-head">{widget}')
        check(f'侧边栏「{widget}」出现 1 次（当前 {n}）', n == 1)

    # 2. 表单内的卡片各 1 次
    for card in FORM_CARDS:
        n = count(html, f'card-head"><h3>{card}')
        check(f'表单卡片「{card}」出现 1 次（当前 {n}）', n == 1)

    # 3. 表单字段
    for field in ('title', 'content', 'excerpt', 'status', 'category',
                  'tags_input', 'cover'):
        check(f'字段 {field} 渲染出来了', f'name="{field}"' in html)

    # 4. 正文 textarea 带 markdown-editor 类（CSS 靠它设高度）
    ta = re.search(r'<textarea[^>]*name="content"[^>]*>', html)
    check('正文 textarea 有 markdown-editor 类',
          bool(ta) and 'markdown-editor' in ta.group(0))

    # 5. 废弃类清干净
    for dead in DEAD_CLASSES:
        n = count(html, dead)
        check(f'没有残留废弃类 .{dead}（当前 {n}）', n == 0)

    # 6. 提交按钮存在
    check('提交按钮存在', '发布文章' in html or '保存修改' in html)

print()
if problems:
    print(f'发现 {len(problems)} 个问题：')
    for p in problems:
        print(f'  - {p}')
    sys.exit(1)
print('结果：渲染结果检查全部通过 ✅')

"""检查快照里写文章页的结构（不依赖浏览器）。

浏览器沙箱里跑不起来，所以这里退一步：直接读渲染后的 HTML，
确认 1) 排版用的类名都在  2) 左右两栏的容器层级正确  3) 表单字段存在。
几何尺寸要你自己在浏览器里看一眼（地址见下方提示）。

    python check_editor_snapshot.py            # 检查 docs/ 里的两个版本
"""
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
DOCS = BASE / 'docs'

FILES = [
    ('写文章（新建，就是有空白的那个页面）', 'post-create.html'),
    ('编辑文章', 'post/1/edit.html'),
]

REQUIRED_CLASSES = ['editor-layout', 'editor-main', 'editor-card',
                    'editor-card-body', 'editor-grow', 'editor-side']


def check(path):
    html = path.read_text(encoding='utf-8')
    problems = []

    # 1. 排版类名
    for cls in REQUIRED_CLASSES:
        if cls not in html:
            problems.append(f'缺少 .{cls}')

    # 2. 嵌套层级：editor-layout > editor-main > editor-card > editor-card-body > editor-grow
    if 'editor-layout' in html:
        layout = html.split('editor-layout', 1)[1]
        order = [layout.find(cls) for cls in
                 ('editor-main', 'editor-card', 'editor-card-body', 'editor-grow',
                  'editor-side')]
        if -1 in order:
            problems.append('两栏结构不完整')
        elif order != sorted(order):
            problems.append('容器嵌套顺序不对（editor-side 应在 editor-main 之后）')

    # 3. 正文 textarea 与它的类
    ta = re.search(r'<textarea[^>]*name="content"[^>]*>', html)
    if not ta:
        problems.append('没找到正文 textarea')
    else:
        if 'markdown-editor' not in ta.group(0):
            problems.append('正文 textarea 没有 markdown-editor 类（CSS 靠它撑高）')

    # 4. 关键字段
    for field in ('title', 'content', 'excerpt', 'status', 'category',
                  'tags_input', 'cover'):
        if f'name="{field}"' not in html:
            problems.append(f'缺少表单字段 {field}')

    # 5. 右栏的卡片数量（发布设置 / 封面图 / Markdown 速查 / 提交按钮）
    side = html.split('editor-side', 1)[1] if 'editor-side' in html else ''
    cards = len(re.findall(r'class="card(?:\s|")', side))
    if cards < 3:
        problems.append(f'右栏卡片偏少（{cards} 个）')

    return problems, {
        'size_kb': len(html.encode('utf-8')) / 1024,
        'textarea_rows': re.search(r'name="content"[^>]*rows="(\d+)"', html),
        'side_cards': cards,
    }


def main():
    all_ok = True
    for label, rel in FILES:
        path = DOCS / rel
        print(f'\n--- {label}  ({rel}) ---')
        if not path.is_file():
            print('  [SKIP] 文件不存在（重建快照即可生成：manage.py build_snapshot）')
            continue
        problems, info = check(path)
        rows = info['textarea_rows']
        print(f'  文件大小      : {info["size_kb"]:.1f} KB')
        print(f'  正文 rows     : {rows.group(1) if rows else "-"}'
              f'  （CSS 里 min-height 会把它撑到约一屏）')
        print(f'  右栏卡片      : {info["side_cards"]} 个')
        if problems:
            all_ok = False
            for p in problems:
                print(f'  [FAIL] {p}')
        else:
            print('  [OK]   结构检查通过')
    print()
    print('注意：这个脚本只能验证 HTML 结构，量不了实际像素高度。')
    print('      想看排版效果，直接打开这个文件（无需服务器）：')
    print(f'        {DOCS / "post-create.html"}')
    print('      或在本地起服务后访问 http://127.0.0.1:8000/post/create/')
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())

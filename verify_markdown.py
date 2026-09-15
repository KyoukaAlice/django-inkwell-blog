"""Markdown 渲染管线自检。

    python verify_markdown.py

检查：代码块高亮、表格、引用、中文标题锚点、外链安全属性、XSS 过滤、表情码转换。
"""
import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'DjangoBlog.settings')
django.setup()                                   # noqa: E402

from blog.markdown_utils import _slugify, render_markdown   # noqa: E402

FENCE = '`' * 3

SAMPLE = f"""## 中文标题测试

正文里有 **加粗**、*斜体* 和 `行内代码`。

{FENCE}python
def hello(name):
    # 这是注释
    return f"hi {{name}}"
{FENCE}

| 列 A | 列 B |
| --- | --- |
| 1 | 2 |

> 这是一段引用

- 列表项一
- 列表项二

[站内链接](/about/) 和 [外链](https://example.com/)

表情测试 [em:smile]

<script>alert('xss')</script>
<img src="x" onerror="alert(1)">
"""

html = render_markdown(SAMPLE)

CHECKS = [
    ('代码块高亮容器 codehilite', 'codehilite' in html),
    ('Python 关键字高亮 (class="k")', 'class="k"' in html),
    ('函数名高亮 (class="nf")', 'class="nf"' in html),
    ('注释高亮 (class="c1")', 'class="c1"' in html),
    ('行内代码 <code>', '<code>' in html),
    ('表格 <table>', '<table' in html),
    ('引用 <blockquote>', '<blockquote' in html),
    ('无序列表 <ul>', '<ul>' in html),
    ('二级标题 <h2>', '<h2' in html),
    ('中文标题锚点 id', 'id="中文标题测试"' in html),
    ('标题永久链接 (permalink)', 'headerlink' in html),
    ('外链加了 target=_blank', 'target="_blank"' in html),
    ('外链加了 rel=noopener', 'noopener' in html),
    ('表情码 [em:smile] 转成 SVG', 'emoticons/smile.svg' in html),
    ('XSS: <script> 被清除', '<script' not in html),
    ('XSS: onerror 属性被清除', 'onerror' not in html),
    ('XSS: javascript: 协议被清除', 'javascript:' not in html),
]

print('Markdown 渲染管线自检')
print('=' * 60)
failed = 0
for label, ok in CHECKS:
    print(f'  {"[OK]  " if ok else "[FAIL]"}  {label}')
    if not ok:
        failed += 1

print()
print('示例输出片段：')
print('-' * 60)
print(html[:600])
print('-' * 60)
print('slugify("中文 标题 Test-1") =', _slugify('中文 标题 Test-1'))

if failed:
    print(f'\n{failed} 项检查失败')
    sys.exit(1)
print(f'\n全部 {len(CHECKS)} 项检查通过 ✅')

"""校验 docs/index.html（项目介绍页）的结构与链接。

介绍页是**手写**的，不由 build_snapshot 生成，所以它需要自己的检查：
  * 必需的章节是否都在（少了会让页面显得残缺）
  * 链接是否有效（含指向 docs/app/ 快照的入口）
  * 是否误引了博客的 style.css（介绍页样式是内联的，引了会互相污染）
  * 主题切换、响应式等关键能力是否还在

    python verify_intro.py
"""
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
DOCS = BASE / 'docs'
INTRO = DOCS / 'index.html'

# 介绍页应有的章节锚点（id 或文字）
REQUIRED_ANCHORS = {
    'top': '顶部',
    'features': '功能特性',
    'comments': '评论系统',
    'flow': '处理流程',
    'stack': '技术栈',
    'arch': '系统架构',
    'quality': '工程质量',
    'start': '快速开始',
}

REQUIRED_TEXT = [
    '项目概览', '功能特性', '评论系统', '技术栈', '系统架构', '快速开始',
    'DjangoBlog', '楼中楼', 'Markdown', 'GitHub Pages',
    'BlogDemo!2026',            # 演示账号密码
    'seed_demo',                # 演示数据命令
]

# 应该指向快照的入口
SNAPSHOT_ENTRIES = ['app/index.html', 'app/index-generated.html']

problems = []
ok_count = 0


def check(label, ok, detail=''):
    global ok_count
    if ok:
        ok_count += 1
        print(f'  [OK]   {label}')
    else:
        problems.append(f'{label}{"：" + detail if detail else ""}')
        print(f'  [FAIL] {label}{"：" + detail if detail else ""}')


print('=' * 70)
print('项目介绍页校验 ——', INTRO)
print('=' * 70)

if not INTRO.is_file():
    print(f'[ERROR] 介绍页不存在：{INTRO}')
    sys.exit(1)

html = INTRO.read_text(encoding='utf-8')
print(f'\n文件大小 {len(html.encode("utf-8")) / 1024:.1f} KB\n')

# ---------- 1. 章节锚点 ----------
for anchor, label in REQUIRED_ANCHORS.items():
    check(f'有「{label}」章节锚点 #{anchor}', f'id="{anchor}"' in html)

# ---------- 2. 关键内容 ----------
for text in REQUIRED_TEXT:
    check(f'包含关键内容「{text}」', text in html)

# ---------- 3. 快照入口 ----------
for entry in SNAPSHOT_ENTRIES:
    check(f'链接到快照入口 {entry}', entry in html)
    target = DOCS / entry
    check(f'  该入口真实存在（{entry}）', target.is_file())

# ---------- 4. 链接有效性 ----------
dead = []
checked = 0
for m in re.finditer(r'\b(?:href|src)="([^"]+)"', html):
    url = m.group(1)
    if url.startswith(('#', 'http://', 'https://', '//', 'data:', 'mailto:', 'javascript:')):
        continue
    path = urlparse(url).path
    if not path:
        continue
    checked += 1
    if not (INTRO.parent / path).resolve().exists():
        dead.append(url)
check(f'本地链接全部有效（检查 {checked} 个）', not dead,
      '死链: ' + ', '.join(dead[:5]) if dead else '')

# ---------- 5. 样式独立 ----------
check('没有误引博客的 style.css（介绍页样式是内联的）',
      'static/css/style.css' not in html)

# ---------- 6. 关键能力 ----------
check('有深色模式（data-theme 与切换按钮）',
      'data-theme' in html and 'themeBtn' in html)
check('有移动端适配（viewport + 响应式断点）',
      'width=device-width' in html and '@media' in html)
check('有 SEO 描述', 'name="description"' in html)
check('有页面图标', 'rel="icon"' in html)

# ---------- 7. .nojekyll 在发布根目录 ----------
check('.nojekyll 在 docs/ 根目录（Pages 认这个位置）',
      (DOCS / '.nojekyll').is_file())

print()
if problems:
    print(f'发现 {len(problems)} 个问题：')
    for p in problems:
        print(f'  - {p}')
    sys.exit(1)
print(f'结果：介绍页检查全部通过 ✅（{ok_count} 项）')

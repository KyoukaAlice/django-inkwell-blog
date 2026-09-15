"""校验静态快照的链接完整性。

检查每一项：
  * 每个 href / src 指向的本地文件是否真实存在（死链检测）
  * 是否还有根绝对路径（/static/... 这种在 Pages 子目录下会 404）
  * 关键页面是否都在
  * 静态资源是否被正确引用

    python verify_snapshot.py            # 校验仓库根目录（默认，快照就在这里）
    python verify_snapshot.py docs       # 校验指定目录
"""
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

SITE = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()

LINK_RE = re.compile(r'\b(?:href|src)=(?P<q>["\'])(?P<url>[^"\']+)(?P=q)')
CSS_URL_RE = re.compile(r'url\((?P<q>["\']?)(?P<url>[^"\')]+)(?P=q)\)')

REQUIRED_PAGES = [
    'index.html', 'index-generated.html', 'about.html', 'tags.html',
    'login.html', 'register.html', 'search.html', 'profile.html',
    'notifications.html', 'post-create.html', 'profile-edit.html',
    'u-alice.html', '404.html', 'post/1/index.html', '.nojekyll',
]

ok_count = 0
problems = []


def note(ok, message):
    global ok_count
    if ok:
        ok_count += 1
    else:
        problems.append(message)


def is_snapshot_page(path: Path) -> bool:
    """只校验快照生成的页面，排除项目自身的文件（模板、源码等）。"""
    rel = path.relative_to(SITE)
    if rel.parts and rel.parts[0] == '.git':
        return False
    skip_dirs = {'.venv', 'venv', '__pycache__', 'blog', 'DjangoBlog', 'staticfiles', '.git'}
    if any(part in skip_dirs for part in rel.parts):
        return False
    return True


print('=' * 72)
print('静态快照校验 ——', SITE)
print('=' * 72)

if not (SITE / 'index-generated.html').exists():
    print(f'[ERROR] 没找到 index-generated.html，这里看起来不是快照目录：{SITE}')
    print('        先运行：python manage.py build_snapshot')
    sys.exit(1)

html_files = sorted(p for p in SITE.rglob('*.html') if is_snapshot_page(p))
print(f'\n共 {len(html_files)} 个 HTML 文件\n')

# ---------- 1. 必备页面 ----------
for page in REQUIRED_PAGES:
    note((SITE / page).exists(), f'缺少页面：{page}')
print(f'[1] 必备页面        {sum((SITE / p).exists() for p in REQUIRED_PAGES)}/{len(REQUIRED_PAGES)} 存在')

# ---------- 2. 死链检测 ----------
checked = 0
dead = []
for html in html_files:
    text = html.read_text(encoding='utf-8')
    for m in LINK_RE.finditer(text):
        url = m.group('url').strip()
        if not url or url.startswith(('#', 'http://', 'https://', '//', 'data:', 'mailto:', 'javascript:')):
            continue
        path_part = urlparse(url).path
        if not path_part:
            continue                      # 纯查询串或纯锚点，指回本页
        checked += 1
        target = (html.parent / unquote(path_part)).resolve()
        if not target.exists():
            dead.append(f'{html.relative_to(SITE)}  ->  {url}')
note(not dead, f'发现 {len(dead)} 个死链')
print(f'[2] 链接检查        {checked} 个本地链接，死链 {len(dead)} 个')

# ---------- 3. 根绝对路径 ----------
absolute = []
for html in html_files:
    for m in LINK_RE.finditer(html.read_text(encoding='utf-8')):
        if m.group('url').startswith('/') and not m.group('url').startswith('//'):
            absolute.append(f'{html.relative_to(SITE)}  ->  {m.group("url")}')
note(not absolute, f'发现 {len(absolute)} 处根绝对路径')
print(f'[3] 绝对路径检查    {len(absolute)} 处残留（应为 0）')

# ---------- 4. 静态资源 ----------
css_files = list(SITE.rglob('*.css'))
js_files = list(SITE.rglob('*.js'))
svg_files = list(SITE.rglob('*.svg'))
note(len(css_files) >= 1, '没有复制到任何 CSS')
note(len(js_files) >= 1, '没有复制到任何 JS')
note(len(svg_files) >= 30, f'表情 SVG 数量偏少：{len(svg_files)}')
print(f'[4] 静态资源        CSS {len(css_files)} · JS {len(js_files)} · SVG {len(svg_files)}')

# CSS 里的 url() 也要能解析到
css_dead = []
for css in css_files:
    for m in CSS_URL_RE.finditer(css.read_text(encoding='utf-8')):
        url = m.group('url').strip()
        if not url or url.startswith(('data:', 'http', '//', '#')):
            continue
        if not (css.parent / unquote(urlparse(url).path)).resolve().exists():
            css_dead.append(f'{css.relative_to(SITE)}  ->  {url}')
note(not css_dead, f'CSS 里有 {len(css_dead)} 个资源找不到')
print(f'[5] CSS 资源引用    {len(css_dead)} 个失效（应为 0）')

# ---------- 6. 页面内容抽查 ----------
sample = (SITE / 'post' / '1' / 'index.html')
if sample.exists():
    body = sample.read_text(encoding='utf-8')
    note('markdown-body' in body, '文章详情页缺少正文容器')
    note('codehilite' in body, '文章详情页缺少代码高亮')
    note('class="comment' in body, '文章详情页缺少评论区')
    note('replies' in body, '文章详情页缺少楼中楼')
    note('emoticons/' in body, '评论表情没有渲染')
    print('[6] 详情页内容      正文/高亮/评论/楼中楼/表情 已检查')
else:
    problems.append('缺少 post/1/index.html，无法抽查内容')

index_body = (SITE / 'index.html').read_text(encoding='utf-8')
note('post-card' in index_body, '首页缺少文章卡片')
note('static/css/style.css' in index_body, '首页没有引用样式表')
note('static/js/main.js' in index_body, '首页没有引用脚本')

# ---------- 7. 目录结构抽样 ----------
print('\n目录结构抽样：')
for item in sorted(SITE.rglob('*'))[:1]:
    pass
for rel in ['index.html', 'index-generated.html', '.nojekyll', 'static/css/style.css',
            'static/js/main.js', 'post/1/index.html', 'u-alice.html', 'u-admin.html']:
    mark = 'OK ' if (SITE / rel).exists() else '!! '
    print(f'  [{mark}] {rel}')

print()
if problems:
    print('发现问题：')
    for p in problems:
        print(f'  [FAIL] {p}')
    if dead:
        print(f'\n死链明细（前 15 条）：')
        for d in dead[:15]:
            print(f'  {d}')
    print(f'\n结果：{ok_count} 项通过，{len(problems)} 项失败')
    sys.exit(1)
print(f'结果：全部检查通过 ✅（{ok_count} 项，本地链接 {checked} 个全部有效）')

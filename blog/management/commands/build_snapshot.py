"""把网站渲染成一套静态 HTML 快照，用于发布到 GitHub Pages 预览。

为什么需要它
------------
GitHub Pages 只能托管静态文件（HTML / CSS / JS），而 Django 是服务端渲染的，
需要 Python 进程和数据库。所以 Pages 上跑不了真正的站点，
只能传一套「渲染好的页面截图（HTML 版）」——界面完全一样，
但登录、发评论这类交互不会有真实效果。

实现方式
--------
在临时测试数据库里灌一份演示数据，用 Django 测试客户端把页面挨个请求一遍，
把返回的 HTML 写成文件；再复制 static/ 资源，并把所有站内绝对链接
改写成相对链接，这样无论部署在域名根目录还是 /<仓库名>/ 子路径下都能正常打开。

用法
----
    python manage.py build_snapshot              # 输出到 docs/（GitHub Pages 可直接用）
    python manage.py build_snapshot -o _site     # 换成别的目录
    python manage.py build_snapshot --skip-admin # 不抓 /admin/ 后台界面

发布到 Pages 的步骤：把 docs/ 一起提交，然后在仓库 Settings -> Pages 里选
「Deploy from a branch」+ 分支 main + 目录 /docs 即可。选 docs 这个目录名是
因为它是 GitHub Pages 官方支持的两种目录之一（另一种是根目录），
不需要在仓库里额外加 workflow 或改配置。
"""
import re
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.test.utils import setup_test_environment, teardown_test_environment
from django.test.runner import DiscoverRunner

from blog.management.commands.seed_demo import PASSWORD, SITE_OWNER
from blog.models import Post

# 需要抓取的页面：(路径, 输出文件名, 是否要登录, 说明)
PAGES = [
    ('/', 'index.html', False, '首页'),
    ('/?sort=hot', 'index-sort-hot.html', False, '首页·最受欢迎'),
    ('/?sort=views', 'index-sort-views.html', False, '首页·阅读最多'),
    ('/search/?keyword=Django', 'search.html', False, '搜索结果'),
    ('/tags/', 'tags.html', False, '标签云'),
    ('/about/', 'about.html', False, '关于本站'),
    ('/login/', 'login.html', False, '登录页'),
    ('/register/', 'register.html', False, '注册页'),
    ('/u/alice/', 'u-alice.html', False, '用户主页'),
    ('/this-page-does-not-exist/', '404.html', False, '404 页面'),
]

# 登录后才有意义的页面
AUTH_PAGES = [
    ('/', 'index-logged-in.html', '首页（登录状态）'),
    ('/profile/', 'profile.html', '个人中心'),
    ('/profile/?status=draft', 'profile-drafts.html', '个人中心·草稿'),
    ('/profile/edit/', 'profile-edit.html', '编辑资料'),
    ('/notifications/', 'notifications.html', '通知中心'),
    ('/post/create/', 'post-create.html', '写文章'),
    ('/u/{owner}/?tab=bookmarks', 'bookmarks.html', '我的收藏'),
]

# 静态资源：把 "/static/..." 的根斜杠去掉，变成 "static/..."。
# 这里刻意不加 "../" 前缀 —— 层级前缀由下面 STATIC_PREFIX_RE 统一补，
# 用 lookbehind 只消费那个斜杠，避免和层级逻辑互相打架。
STATIC_PREFIX_RULES = [
    (re.compile(r'(?<=["\'(])/(?=static/|media/)'), ''),
]
# 紧跟在引号后面、以 static/ 或 media/ 开头的路径（此时已经没有根斜杠）
STATIC_PREFIX_RE = re.compile(r'(?<=["\'])(?:static|media)/')

# URL 里带 id / slug 的动态路径 -> 快照里的文件。
# 这些在 fix_link 里按前后顺序判断并一次性补上 "../" 前缀，
# 千万不要再单独做一次全局替换：那样第二步会把已经混进去的
# 相对前缀当成普通路径，导致嵌套页面的链接丢掉 "../../"。
DYNAMIC_PATH_PATTERNS = [
    (re.compile(r'^post/(\d+)/edit/?$'), r'post/\1/edit.html'),
    (re.compile(r'^post/(\d+)/delete/?$'), r'post/\1/delete.html'),
    (re.compile(r'^post/(\d+)/?$'), r'post/\1/index.html'),
    (re.compile(r'^u/([\w.@+-]+)/?$'), r'u-\1.html'),
    (re.compile(r'^tag/([\w-]+)/?$'), r'tag-\1.html'),
]

# 普通页面路径 -> 快照里的文件名（顺序有意义：长路径在前）
PAGE_MAP = [
    ('profile/edit', 'profile-edit.html'),
    ('post/create', 'post-create.html'),
    ('tags', 'tags.html'),
    ('about', 'about.html'),
    ('login', 'login.html'),
    ('register', 'register.html'),
    ('search', 'search.html'),
    ('notifications', 'notifications.html'),
    ('admin', 'admin.html'),
    ('profile', 'profile.html'),
]

# 匹配 href="/xxx" / src='/xxx' 这样的根绝对路径（含查询串和锚点）
ABSOLUTE_LINK = re.compile(r'(?P<attr>\b(?:href|src|action)=)(?P<q>["\'])(?P<path>/[^"\']*)(?P=q)')
# 匹配相对路径链接，用于自检「改完之后是否真的能找到文件」
RELATIVE_LINK = re.compile(r'\b(?:href|src)=(?P<q>["\'])(?P<url>(?![/"\'])[^"\']*)(?P=q)')
# admin 页面里的相对链接（href="admin/blog/post/..." 这种）
ADMIN_RELATIVE_LINK = re.compile(
    r'(?P<attr>\b(?:href|src)=)(?P<q>["\'])(?P<url>(?![/"\']|https?:|#)[^"\']*)(?P=q)')
# 匹配 url(/xxx) 这种 CSS 里的写法
ABSOLUTE_CSS_URL = re.compile(r'url\((?P<q>["\']?)(?P<path>/[^"\')]*)(?P=q)\)')

BANNER = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  body {{ margin:0; padding:0; font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif; background:#0aa7e0; color:#fff; }}
  .bar {{ display:flex; align-items:center; gap:12px; padding:9px 16px; font-size:13px; flex-wrap:wrap; }}
  .bar b {{ background:rgba(255,255,255,.22); padding:2px 9px; border-radius:20px; }}
  .bar a {{ color:#fff; margin-left:auto; opacity:.9; }}
  .bar button {{ background:rgba(255,255,255,.22); border:0; color:#fff; padding:4px 12px; border-radius:20px; cursor:pointer; font-size:12px; font-family:inherit; }}
  iframe {{ width:100%; height:calc(100vh - 40px); border:0; display:block; background:#f4f6fa; }}
</style>
</head>
<body>
<div class="bar">
  <b>📸 静态预览</b>
  <span>{desc} <code>{file}</code></span>
  <button onclick="document.getElementById('f').src=document.getElementById('f').src">重新加载</button>
  <a href="index.html">← 返回预览目录</a>
</div>
<iframe id="f" src="{file}" title="preview"></iframe>
</body>
</html>
"""


class Command(BaseCommand):
    help = '把网站渲染成静态 HTML 快照（用于 GitHub Pages 预览）'

    def add_arguments(self, parser):
        parser.add_argument('-o', '--output', default='docs',
                            help='输出目录，默认 docs（GitHub Pages 可直接从该目录发布）')
        parser.add_argument('--include-admin', action='store_true',
                            help='额外抓取 /admin/ 后台界面')
        parser.add_argument('--skip-admin', action='store_true',
                            help='不抓 /admin/ 后台界面（默认会抓，因为导航里的「后台管理」链接需要它）')
        parser.add_argument('--keep-output', action='store_true',
                            help='输出目录已存在时不要清空，直接覆盖')

    def handle(self, *args, **options):
        output_dir = Path(settings.BASE_DIR) / options['output']
        if output_dir.exists():
            if not options['keep_output']:
                shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        self.stdout.write(self.style.MIGRATE_HEADING('\n准备临时数据库…'))
        setup_test_environment()
        runner = DiscoverRunner(verbosity=0, interactive=False)
        old_config = runner.setup_databases()
        try:
            call_command('seed_demo', reset=True, verbosity=0)
            # 导航栏里对 staff 用户会显示「后台管理」链接，所以默认也抓一份后台首页，
            # 否则快照里会留下一个指不到文件的死链。
            include_admin = not options['skip_admin']
            written = self._render_all(output_dir, include_admin)
            self._copy_static(output_dir)
            self._rewrite_links(output_dir)
            self._write_support_files(output_dir, written)
        finally:
            runner.teardown_databases(old_config)
            teardown_test_environment()

        self._report(output_dir, written)

    # -- 渲染页面 ----------------------------------------------------------
    def _render_all(self, output_dir, include_admin):
        client = Client()
        written = []

        def fetch(path, out_file, desc, need_login=False):
            if need_login:
                client.force_login(self.owner)
            else:
                client.logout()
            response = client.get(path)
            body = response.content.decode('utf-8')
            target = output_dir / out_file
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding='utf-8')
            size_kb = len(response.content) / 1024
            self.stdout.write(f'  [OK]  {path:34} -> {out_file:28} {response.status_code}  {size_kb:6.1f} KB')
            written.append({'file': out_file, 'title': desc, 'desc': desc, 'path': path})
            return body

        # 先确定站长账号（登录态页面要用）
        self.owner = None
        from django.contrib.auth.models import User
        self.owner = User.objects.get(username=SITE_OWNER)

        self.stdout.write(self.style.MIGRATE_HEADING('\n抓取公开页面…'))
        for path, out_file, _need_login, desc in PAGES:
            fetch(path, out_file, desc)

        self.stdout.write(self.style.MIGRATE_HEADING('\n抓取登录状态页面…'))
        for path, out_file, desc in AUTH_PAGES:
            fetch(path.replace('{owner}', SITE_OWNER), out_file, desc, need_login=True)

        self.stdout.write(self.style.MIGRATE_HEADING('\n抓取文章详情页…'))
        for post in Post.objects.published().order_by('id'):
            out_file = f'post/{post.id}/index.html'
            fetch(f'/post/{post.id}/', out_file, f'文章：{post.title}')
            if post.author_id == self.owner.id:
                fetch(f'/post/{post.id}/edit/', f'post/{post.id}/edit.html', f'编辑：{post.title}', need_login=True)
                fetch(f'/post/{post.id}/delete/', f'post/{post.id}/delete.html', f'删除确认：{post.title}', need_login=True)

        self.stdout.write(self.style.MIGRATE_HEADING('\n抓取用户主页…'))
        from django.contrib.auth.models import User
        for profile_user in User.objects.all().order_by('id'):
            fetch(f'/u/{profile_user.username}/', f'u-{profile_user.username}.html',
                  f'用户主页：{profile_user.username}')

        self.stdout.write(self.style.MIGRATE_HEADING('\n抓取标签页…'))
        from blog.models import Tag
        for tag in Tag.objects.all():
            # 每个标签一个独立文件，避免互相覆盖
            fetch(f'/tag/{tag.slug}/', f'tag-{tag.slug}.html', f'标签：{tag.name}')

        if include_admin:
            self.stdout.write(self.style.MIGRATE_HEADING('\n抓取后台界面…'))
            fetch('/admin/', 'admin.html', '后台首页', need_login=True)

        return written

    # -- 复制静态资源 ------------------------------------------------------
    def _copy_static(self, output_dir):
        """复制项目静态资源 + Django 自带（admin）静态资源。

        项目自己的 static/ 直接拷过去即可；但 /admin/ 后台的 CSS/JS 属于
        django.contrib.admin，必须靠 collectstatic 收集，否则后台页面会没样式。
        """
        self.stdout.write(self.style.MIGRATE_HEADING('\n复制静态资源…'))
        target = output_dir / 'static'
        total = 0
        seen_names = set()

        def copy_tree(src: Path, label):
            nonlocal total
            if not src.exists():
                return
            shutil.copytree(src, target, dirs_exist_ok=True)
            count = sum(1 for p in src.rglob('*') if p.is_file())
            total += count
            self.stdout.write(f'  [OK]  {label}  （{count} 个文件）')

        for src in getattr(settings, 'STATICFILES_DIRS', []):
            copy_tree(Path(src), f'{src}')

        # 收集 Django 内置 app（主要是 admin）的静态文件到 STATIC_ROOT。
        #
        # 关于 copytree 的一个坑：copytree(SRC, DST) 复制的是 SRC 的**内容**到 DST，
        # 也就是 DST 相当于 SRC 本身。所以想让结果变成 "static/admin/..."，
        # 目标要写 "…/static"（父目录），写成 "…/static/admin" 会把内容倒进 static/ 根里。
        # 之前就是这里写错，导致 admin 目录凭空消失、后台页面全是死链。
        static_root = Path(settings.STATIC_ROOT)
        try:
            call_command('collectstatic', interactive=False, verbosity=0, clear=False)
            if (static_root / 'admin').exists():
                # 整个 STATIC_ROOT 合并进 static/：
                #   staticfiles/admin      -> _site/static/admin      （后台 CSS/JS）
                #   staticfiles/js/vendor  -> _site/static/js/vendor  （后台的前端库）
                copy_tree(static_root, 'Django 内置静态资源（admin 等） -> static/')
            else:
                self.stdout.write(self.style.WARNING(
                    '  [warn] collectstatic 没有产出 admin 静态资源，后台页面可能缺样式'))
        except Exception as exc:                    # noqa: BLE001
            self.stdout.write(self.style.WARNING(
                f'  [warn] collectstatic 失败（{exc}），后台页面可能缺样式'))

        if not total:
            raise CommandError('没有找到静态资源，请检查 settings.STATICFILES_DIRS')

        # 用户上传目录（演示数据里没有图片，存在就一起带上）
        media_root = Path(settings.MEDIA_ROOT)
        if media_root.exists() and any(media_root.rglob('*')):
            shutil.copytree(media_root, output_dir / 'media', dirs_exist_ok=True)
            self.stdout.write(f'  [OK]  {media_root}  ->  media/')

    # -- 链接改写 ----------------------------------------------------------
    def _rewrite_links(self, output_dir):
        """把所有根绝对路径改成相对路径。

        为什么要做：GitHub Pages 的项目站点挂在 /<仓库名>/ 子路径下，
        而 Django 生成的是 /static/... 这种根绝对路径，直接访问会 404。
        改成相对路径后，放在域名根目录还是子目录都能打开。

        做法分两步：
          1. 先处理「URL 形态会变」的路径（/post/12/ -> post/12/index.html 等），
             这些规则不区分层级，先全局替换掉；
          2. 剩下的根绝对路径统一交给 rewrite_absolute_paths，由它根据当前
             文件所在层级补上正确数量的 "../" —— 早期版本就是漏了这一步，
             导致 post/1/delete.html 里的 static/css/style.css 少了 ../../。
        """
        self.stdout.write(self.style.MIGRATE_HEADING('\n改写链接为相对路径…'))
        changed_files = 0

        for html_file in output_dir.rglob('*.html'):
            text = html_file.read_text(encoding='utf-8')
            original = text
            depth = len(html_file.relative_to(output_dir).parts) - 1
            up = '../' * depth

            # --- 第一步：只把静态资源的根斜杠去掉，层级前缀留到第二步一起补 ---
            for pattern, repl in STATIC_PREFIX_RULES:
                text = pattern.sub(repl, text)
            text = STATIC_PREFIX_RE.sub(lambda m: up + m.group(0), text)

            # --- 第二步：所有根绝对路径，按层级补前缀 + 映射成快照文件名 ---
            def fix_link(match):
                path = match.group('path')
                if path.startswith('//'):          # 协议相对地址，保持原样
                    return match.group(0)

                clean = path.lstrip('/')
                # 拆出 ?查询串 / #锚点，避免把 ? 丢掉
                suffix = ''
                for sep in ('?', '#'):
                    if sep in clean:
                        clean, rest = clean.split(sep, 1)
                        suffix = sep + rest
                        break

                clean = clean.rstrip('/')

                if not clean:
                    new = up + 'index.html' + suffix
                else:
                    # 1) 动态路径（/post/12/、/u/xxx/、/tag/xxx/ 等）
                    mapped = None
                    for pattern, repl in DYNAMIC_PATH_PATTERNS:
                        if pattern.match(clean):
                            mapped = pattern.sub(repl, clean)
                            break
                    if mapped is None:
                        # 2) 普通页面路径
                        for key, target in PAGE_MAP:
                            if clean == key:
                                mapped = target
                                break
                    # 3) 静态资源等路径在快照里是同构的，直接用
                    new = up + (mapped if mapped else clean) + suffix
                return f'{match.group("attr")}{match.group("q")}{new}{match.group("q")}'

            text = ABSOLUTE_LINK.sub(fix_link, text)

            # --- 第三步：Django admin 内部的相对链接 ---
            # 后台首页里全是 "admin/blog/post/" 这种相对链接，指向的是需要服务端
            # 才能处理的增删改查页面，静态快照里不存在。这里把它们统一指回后台
            # 首页，避免在 Pages 上点出一堆 404。
            if html_file.name == 'admin.html':
                def loop_back(match):
                    url = match.group('url')
                    if url.startswith(('admin/', '#')) or url.endswith('.html'):
                        return f'{match.group("attr")}="../admin.html"'
                    return match.group(0)

                text = ADMIN_RELATIVE_LINK.sub(loop_back, text)

            # CSS 里的 url(/xxx)
            def fix_css(match):
                path = match.group('path')
                if path.startswith('//'):
                    return match.group(0)
                return f'url({up}{path.lstrip("/")})'

            text = ABSOLUTE_CSS_URL.sub(fix_css, text)

            if text != original:
                html_file.write_text(text, encoding='utf-8')
                changed_files += 1

        self.stdout.write(f'  [OK]  改写了 {changed_files} 个 HTML 文件')

        # --- 自检：确认没有残留，并且改出来的相对链接真的指向存在的文件 ---
        leftovers, broken = [], []
        for html_file in output_dir.rglob('*.html'):
            text = html_file.read_text(encoding='utf-8')
            for match in ABSOLUTE_LINK.finditer(text):
                if not match.group('path').startswith('//'):
                    leftovers.append(f'{html_file.relative_to(output_dir)}: {match.group(0)[:80]}')
            for match in RELATIVE_LINK.finditer(text):
                url = match.group('url')
                if url.startswith(('#', 'http', '//', 'data:', 'mailto:', 'javascript:')):
                    continue
                path_part = url.split('?', 1)[0].split('#', 1)[0]
                if not path_part:
                    continue
                if not (html_file.parent / path_part).resolve().exists():
                    broken.append(f'{html_file.relative_to(output_dir)} -> {url}')

        if leftovers:
            self.stdout.write(self.style.WARNING(
                f'  [warn] 还有 {len(leftovers)} 处根绝对链接未改写：'))
            for line in leftovers[:5]:
                self.stdout.write(f'         {line}')
        else:
            self.stdout.write('  [OK]  没有残留的根绝对链接')

        if broken:
            self.stdout.write(self.style.WARNING(
                f'  [warn] 有 {len(broken)} 个相对链接指向不存在的文件：'))
            for line in broken[:8]:
                self.stdout.write(f'         {line}')
        else:
            self.stdout.write('  [OK]  所有相对链接都能在快照里找到对应文件')

        css_leftovers = [str(c.relative_to(output_dir)) for c in output_dir.rglob('*.css')
                         if ABSOLUTE_CSS_URL.search(c.read_text(encoding='utf-8'))]
        if css_leftovers:
            self.stdout.write(self.style.WARNING(
                f'  [warn] 这些 CSS 里还有绝对 url()：{css_leftovers}'))

    # -- Pages 辅助文件 ----------------------------------------------------
    def _write_support_files(self, output_dir, written):
        # .nojekyll：阻止 GitHub Pages 的 Jekyll 处理，保证 _ 开头的文件也能访问
        (output_dir / '.nojekyll').write_text('', encoding='utf-8')

        # 预览目录页：用 iframe 嵌每个页面，方便逐页查看
        # 预览目录页里的每一项都直接链到对应页面
        cards = '\n'.join(
            f'      <li><a href="{item["file"]}">{item["title"]}</a>'
            f' <code>{item["file"]}</code></li>'
            for item in written
        )
        index = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DjangoBlog 静态预览</title>
<style>
  body {{ margin:0; font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
         background:#f4f6fa; color:#1b2434; line-height:1.7; }}
  .hero {{ background:linear-gradient(120deg,#0aa7e0,#fb7299); color:#fff; padding:40px 24px; }}
  .hero h1 {{ margin:0 0 8px; font-size:1.7rem; }}
  .hero p {{ margin:0; opacity:.95; max-width:720px; }}
  .wrap {{ max-width:900px; margin:0 auto; padding:26px 24px 60px; }}
  .tip {{ background:#fff7e6; border:1px solid #f5d9a3; border-radius:12px; padding:14px 18px; margin-bottom:22px; font-size:.9rem; }}
  ul {{ list-style:none; padding:0; margin:0; }}
  li {{ background:#fff; border:1px solid #e5e9f0; border-radius:10px; margin-bottom:8px; }}
  li a {{ display:block; padding:12px 16px; color:#0891c4; text-decoration:none; font-weight:600; }}
  li a:hover {{ background:#e6f7fe; border-radius:10px; }}
  code {{ color:#8b97ab; font-weight:400; font-size:.82rem; }}
</style>
</head>
<body>
<div class="hero">
  <h1>📸 DjangoBlog 静态预览</h1>
  <p>这是把网站渲染成静态 HTML 后的快照，用于在 GitHub Pages 上展示界面。
     点击下面任意一页即可查看，每页顶部有返回本目录的入口。</p>
</div>
<div class="wrap">
  <div class="tip">
    <b>⚠️ 这是静态快照，不是运行中的网站</b><br>
    页面样式、排版、评论楼中楼都是真实的渲染结果，但所有需要服务器的操作
    （登录、发文、点赞、发评论）都不会生效——GitHub Pages 只能托管静态文件，跑不了 Django。
    想看完整功能请按 README 在本地运行，或在支持 Python 的平台部署。
  </div>
  <ul>
{cards}
  </ul>
</div>
</body>
</html>
"""
        (output_dir / 'index-preview-list.html').write_text(index, encoding='utf-8')

        # 不再生成 preview.html：
        # 预览目录页本身就直接列出所有页面并链过去，再套一层 iframe 反而多余，
        # 而且 iframe 的 src 需要运行时才知道（会留下未替换的占位符）。

    def _report(self, output_dir, written):
        total_bytes = sum(f.stat().st_size for f in output_dir.rglob('*') if f.is_file())
        html_count = sum(1 for _ in output_dir.rglob('*.html'))
        self.stdout.write(self.style.SUCCESS(
            f'\n快照生成完成\n'
            f'  输出目录 : {output_dir}\n'
            f'  HTML 页面: {html_count} 个\n'
            f'  总大小   : {total_bytes / 1024 / 1024:.1f} MB\n'
            f'\n推到 GitHub 后，Pages 地址一般是：\n'
            f'  https://<用户名>.github.io/<仓库名>/index-preview-list.html   ← 预览目录\n'
            f'  https://<用户名>.github.io/<仓库名>/index.html               ← 直接进首页\n'
            f'\n本地预览可以先起个静态服务器：\n'
            f'  cd {output_dir.name} && python -m http.server 8080\n'
        ))

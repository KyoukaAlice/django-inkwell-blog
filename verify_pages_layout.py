"""按 GitHub Pages 的部署结构做一次「结构体检」。

Pages 的 Source 是 main + /docs，所以发布根目录是 docs/。这个脚本会：
  1. 起一个本地静态服务器，把 docs/ 当发布根
  2. 逐个请求关键页面，确认都能 200（而不是 404）
  3. 校验「介绍页 → 快照」和「快照 → 介绍页」双向链接都能走通
  4. 检查 .nojekyll 是否在发布根目录（放错位置会让 Jekyll 去解析仓库）

比 verify_intro.py / verify_snapshot.py 更靠后一步：
那两个查文件内容，这个查「部署出来到底能不能打开」。

    python verify_pages_layout.py
"""
import functools
import http.server
import posixpath
import re
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
DOCS = BASE / 'docs'
PORT = 8155

# (路径, 期望状态码, 说明, 内容里应包含的片段)
CASES = [
    ('/index.html', 200, '项目介绍页（发布根首页）', ['DjangoBlog', '评论系统', '快速开始']),
    ('/app/index.html', 200, '站点首页快照', ['post-card', 'markdown-body'.replace('markdown-body', '最新文章')]),
    ('/app/index-generated.html', 200, '全部页面索引', ['页面索引']),
    ('/app/about.html', 200, '关于页快照', []),
    ('/app/tags.html', 200, '标签云快照', []),
    ('/app/post/1/index.html', 200, '文章详情快照', ['markdown-body', 'comments']),
    ('/app/static/css/style.css', 200, '快照的样式表', ['--brand']),
    ('/app/static/js/main.js', 200, '快照的脚本', ['swapComments']),
    ('/app/admin.html', 200, '后台首页快照', []),
]

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


print('=' * 74)
print('Pages 部署结构体检 ——', DOCS)
print('=' * 74)

# ---------- 0. 前置检查 ----------
print('\n[0] 目录结构')
if not DOCS.is_dir():
    print(f'[ERROR] 找不到 {DOCS}')
    sys.exit(1)

print('  docs/ 顶层:', ', '.join(sorted(p.name for p in DOCS.iterdir())))
check('docs/index.html 是项目介绍页（手写）',
      (DOCS / 'index.html').is_file()
      and '评论系统是怎么做的' in (DOCS / 'index.html').read_text(encoding='utf-8'))
check('docs/app/ 存在且有内容',
      (DOCS / 'app').is_dir() and any((DOCS / 'app').iterdir()))
check('.nojekyll 在发布根目录 docs/（放错位置会失效）',
      (DOCS / '.nojekyll').is_file())

# ---------- 1. 起服务器 ----------
class Server(socketserver.TCPServer):
    allow_reuse_address = True


class Handler(http.server.SimpleHTTPRequestHandler):
    """把 docs/ 当发布根；顺便关掉访问日志，避免刷屏。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DOCS), **kwargs)

    def log_message(self, *args):
        pass


httpd = Server(('127.0.0.1', PORT), Handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
time.sleep(0.6)

base = f'http://127.0.0.1:{PORT}'
pages = {}


def fetch(path):
    try:
        with urllib.request.urlopen(base + path, timeout=15) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as exc:                       # noqa: BLE001
        return None, repr(exc)


try:
    # ---------- 2. 关键页面 ----------
    print('\n[1] 关键页面探活')
    for path, expect, label, needles in CASES:
        status, body = fetch(path)
        if status != expect:
            check(f'{label}  {path}', False, f'期望 {expect}，实际 {status}')
            continue
        missing = [n for n in needles if n not in body]
        check(f'{label}  {path}  ({len(body.encode("utf-8")) / 1024:.1f} KB)',
              not missing, f'内容里缺少 {missing}' if missing else '')
        pages[path] = body

    # ---------- 3. 双向链接 ----------
    print('\n[2] 介绍页 ↔ 快照 的跳转')
    intro = pages.get('/index.html', '')
    check('介绍页里有指向快照首页的链接', 'app/index.html' in intro)
    check('介绍页里有指向页面索引的链接', 'app/index-generated.html' in intro)

    index_gen = pages.get('/app/index-generated.html', '')
    check('页面索引里有返回介绍页的链接', '../index.html' in index_gen)

    # ---------- 4. 快照内部链接抽样 ----------
    print('\n[3] 快照内部链接抽样（抽 12 个相对链接实探）')
    detail = pages.get('/app/post/1/index.html', '')
    links = re.findall(r'(?:href|src)="([^"]+)"', detail)
    local = [u for u in links
             if not u.startswith(('#', 'http', '//', 'data:', 'mailto:', 'javascript:'))][:12]
    bad = []
    for url in local:
        path = url.split('?')[0].split('#')[0]
        if not path:
            continue
        # 用 posixpath 归一化相对路径，避免手写解析出错
        resolved = posixpath.normpath(posixpath.join('/app/post/1', path))
        status, _ = fetch(resolved)
        if status != 200:
            bad.append(f'{url} -> {resolved} ({status})')
    check(f'详情页里抽样的 {len(local)} 个链接都能打开', not bad,
          '; '.join(bad[:4]) if bad else '')

finally:
    httpd.shutdown()

print()
if problems:
    print(f'发现 {len(problems)} 个问题：')
    for p in problems:
        print(f'  - {p}')
    sys.exit(1)
print(f'结果：Pages 部署结构检查全部通过 ✅（{ok_count} 项）')
print('\n线上地址（Pages Source = main + /docs）：')
print('  https://<用户名>.github.io/<仓库名>/                 ← 项目介绍页')
print('  https://<用户名>.github.io/<仓库名>/app/index.html   ← 站点首页快照')

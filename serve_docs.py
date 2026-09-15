"""模拟 GitHub Pages 的 docs/ 发布方式，在本地把快照跑起来并逐个探活。

Pages 的项目站点地址形如 https://<用户名>.github.io/<仓库名>/
内容来自仓库的 docs/ 目录。本地就照这个结构复刻一份来验证。

    python serve_docs.py            # 起服务并探活，然后退出
    python serve_docs.py --serve    # 起服务后保持运行（Ctrl+C 停止）
"""
import argparse
import functools
import http.server
import shutil
import socketserver
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_NAME = 'django-inkwell-blog'
DOCS = Path(__file__).resolve().parent / 'docs'
PORT = 8130

PATHS = [
    '/index-generated.html', '/index.html', '/index-logged-in.html',
    '/post/1/index.html', '/post/1/edit.html', '/post/1/delete.html',
    '/tags.html', '/tag-前端.html', '/tag-毕业设计.html', '/tag-django.html',
    '/about.html', '/login.html', '/register.html', '/search.html',
    '/u-alice.html', '/u-bob.html', '/u-admin.html', '/profile.html',
    '/notifications.html', '/post-create.html', '/admin.html', '/404.html',
    '/static/css/style.css', '/static/js/main.js',
    '/static/img/emoticons/smile.svg', '/static/admin/css/base.css',
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serve', action='store_true', help='探活后保持运行')
    args = parser.parse_args()

    if not (DOCS / 'index-generated.html').exists():
        print(f'[ERROR] 没找到 {DOCS / "index-generated.html"}')
        print('        先运行：python manage.py build_snapshot')
        return 1

    # 复刻 Pages 的目录结构：<根>/<仓库名>/ 里放 docs 的内容
    tmp = Path(tempfile.mkdtemp(prefix='pages-docs-'))
    site_root = tmp / REPO_NAME
    shutil.copytree(DOCS, site_root)
    print(f'模拟站点根目录：{tmp}')
    print(f'站点地址（本地）：http://127.0.0.1:{PORT}/{REPO_NAME}/')
    print()

    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(tmp))
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(('127.0.0.1', PORT), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.6)

    base = f'http://127.0.0.1:{PORT}/{REPO_NAME}'
    ok = bad = 0
    print('-' * 66)
    for path in PATHS:
        url = base + urllib.parse.quote(path)
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                print(f'  HTTP {r.status}  {len(r.read()):>7,} B   {path}')
                ok += 1
        except urllib.error.HTTPError as e:
            print(f'  HTTP {e.code}              {path}')
            bad += 1
        except Exception as e:                      # noqa: BLE001
            print(f'  失败                {path}  ({type(e).__name__})')
            bad += 1
    print('-' * 66)
    print(f'{ok} 个正常，{bad} 个异常')

    if args.serve and bad == 0:
        print('\n服务保持运行中，浏览器打开上面那个地址即可（Ctrl+C 停止）')
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print('\n已停止')
    httpd.shutdown()
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    import urllib.parse                            # noqa: E402
    sys.exit(main())

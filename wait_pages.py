"""等待并确认 GitHub Pages 已成功从 docs/ 发布。

适合在「手动把 Pages 源改成 /docs」之后运行，它会：
  1. 轮询仓库的 Pages 配置，直到 source 变成 main + /docs
  2. 等这一次构建跑完
  3. 对线上地址做分步探活（DNS / TCP / TLS / HTTP）
  4. 抽查关键资源是否都是 200

用法：
    python wait_pages.py                # 默认最多等 10 分钟
    python wait_pages.py --timeout 300  # 自定义超时（秒）
"""
import argparse
import json
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

REPO = 'KyoukaAlice/django-inkwell-blog'
TOKEN = os.environ.get('GITHUB_TOKEN', '')
SITE = 'https://kyoukaalice.github.io/django-inkwell-blog/'

PROBE_PATHS = [
    '/index-generated.html', '/index.html', '/post/1/index.html',
    '/tags.html', '/tag-前端.html', '/about.html', '/login.html',
    '/static/css/style.css', '/static/js/main.js',
    '/static/img/emoticons/smile.svg', '/static/admin/css/base.css',
]


def make_opener():
    """优先直连，失败则探测本地代理（国内直连 github.io 常被干扰）。"""
    handlers = []
    for port in (7897, 7890, 7891, 10809, 10808, 1080):
        s = socket.socket()
        s.settimeout(0.25)
        try:
            s.connect(('127.0.0.1', port))
            handlers.append(urllib.request.ProxyHandler(
                {'http': f'http://127.0.0.1:{port}', 'https': f'http://127.0.0.1:{port}'}))
            print(f'  （检测到本地代理 127.0.0.1:{port}，API 走代理）')
            break
        except Exception:                          # noqa: BLE001
            continue
        finally:
            s.close()
    return urllib.request.build_opener(*handlers)


OPENER = make_opener()


def api(path):
    if not TOKEN:
        return None, {}
    req = urllib.request.Request('https://api.github.com' + path)
    req.add_header('Authorization', 'Bearer ' + TOKEN)
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('User-Agent', 'DjangoBlog-WaitPages')
    try:
        with OPENER.open(req, timeout=30) as r:
            body = r.read().decode()
            return r.status, (json.loads(body) if body.strip() else {})
    except Exception as exc:                       # noqa: BLE001
        return None, {'error': repr(exc)}


def pages_source():
    status, data = api(f'/repos/{REPO}/pages')
    if status == 200:
        return data.get('source') or {}, data
    return None, data


def snapshot_is_live(timeout=15):
    """判断线上跑的到底是不是我们的快照。

    为什么要单独判断：从仓库根目录发布时，Jekyll 会把 README.md 渲染成
    index.html，那个页面也会返回 200 —— 但它不是博客首页。所以不能拿
    /index.html 当成功标志，必须用一个只有快照才有的文件当哨兵：
    docs/index-generated.html（预览目录页）。
    """
    url = SITE + 'index-generated.html'
    for opener in (urllib.request.build_opener(), OPENER):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with opener.open(req, timeout=timeout) as r:
                body = r.read().decode('utf-8', 'replace')
                # 再确认一下内容确实是我们的预览页
                return r.status == 200 and 'DjangoBlog 静态预览' in body
        except Exception:                          # noqa: BLE001
            continue
    return False


def probe(base=SITE, timeout=15, quiet=False):
    """分步探活，返回 (是否成功, 说明)。"""
    host = urlparse(base).netloc
    steps = []

    try:
        socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        steps.append('DNS OK')
    except Exception as exc:                       # noqa: BLE001
        return False, f'DNS 解析失败：{exc}'

    try:
        sock = socket.create_connection((host, 443), timeout=timeout)
        steps.append('TCP OK')
    except Exception as exc:                       # noqa: BLE001
        return False, f'TCP 连接失败：{exc}（网络层被挡，可能需要代理）'

    try:
        tls = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
        steps.append(f'TLS {tls.version()}')
        tls.close()
    except Exception as exc:                       # noqa: BLE001
        return False, f'TLS 握手失败：{exc}（连接被干扰，国内直连常见）'

    # HTTP 探活：直连不通就试代理
    for opener, tag in ((urllib.request.build_opener(), '直连'),
                        (OPENER, '代理')):
        try:
            req = urllib.request.Request(base, headers={'User-Agent': 'Mozilla/5.0'})
            with opener.open(req, timeout=timeout) as r:
                body = r.read()
                steps.append(f'HTTP {r.status} via {tag}')
                if r.status == 200:
                    if not quiet:
                        print(f'    探活: {" -> ".join(steps)}')
                    return True, f'HTTP 200（{len(body)} 字节）'
                return False, f'HTTP {r.status}'
        except urllib.error.HTTPError as e:
            if e.code == 404:
                steps.append(f'HTTP 404 via {tag}')
                return False, 'HTTP 404（源目录里还没有 index.html）'
            steps.append(f'HTTP {e.code} via {tag}')
            return False, f'HTTP {e.code}'
        except Exception:                          # noqa: BLE001
            continue
    return False, 'HTTP 探活失败（直连和代理都不通）'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--timeout', type=int, default=600, help='最长等待秒数')
    args = parser.parse_args()

    print('=' * 72)
    print('等待 GitHub Pages 从 docs/ 发布')
    print('=' * 72)
    print(f'\n仓库：{REPO}')
    print(f'站点：{SITE}')
    if not TOKEN:
        print('\n[提示] 没设 GITHUB_TOKEN，无法查询 Pages 配置，')
        print('       只能直接对站点做探活（也能判断成没成）。')

    source, _ = pages_source()
    if source is not None:
        print(f'\n当前 source = {source}')

    deadline = time.time() + args.timeout
    last_source = None
    switched = False

    while time.time() < deadline:
        source, _ = pages_source()

        if source is not None and not switched:
            path = source.get('path', '/')
            if path.rstrip('/') == '/docs':
                switched = True
                print(f'\n  ✅ Pages 源已切换为 main /docs')
                print('     等这次构建跑完…')
            else:
                if source != last_source:
                    print(f'  等待你在 GitHub 上把 source 改成 /docs（当前 {path}）…')
                    print('     https://github.com/%s/settings/pages' % REPO)
                    last_source = source

        # 只有哨兵文件（docs/index-generated.html）能打开，才算真正发布成功。
        # 不能拿 /index.html 当标志：从根目录发布时 Jekyll 会把 README.md
        # 渲染成 index.html，那个页面也会 200。
        if snapshot_is_live():
            print(f'\n  ✅ 快照已发布：{SITE}')
            print(f'\n  预览目录：{SITE}index-generated.html')
            print(f'  站点首页：{SITE}index.html')
            print('\n  抽查关键资源：')

            good = bad = 0
            for p in PROBE_PATHS:
                url = SITE + urllib.parse.quote(p.lstrip('/'))
                opened = False
                for opener in (urllib.request.build_opener(), OPENER):
                    try:
                        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                        with opener.open(req, timeout=20) as r:
                            print(f'    HTTP {r.status}  {len(r.read()):>7,} B   {p}')
                            good += 1
                            opened = True
                        break
                    except urllib.error.HTTPError as e:
                        print(f'    HTTP {e.code}              {p}')
                        bad += 1
                        opened = True
                        break
                    except Exception:              # noqa: BLE001
                        continue
                if not opened:
                    print(f'    连接失败           {p}')
                    bad += 1
            print(f'\n  {good} 个正常，{bad} 个异常')
            return 0 if bad == 0 else 1

        time.sleep(20)

    print(f'\n超时（{args.timeout}s）。当前状态：')
    print(f'  source : {source}')
    print(f'  探活   : {detail}')
    print('\n如果 source 已经是 /docs 但还是 404，稍等 1~2 分钟再跑一次；')
    print('如果 source 还是 /，说明 Pages 设置还没改：')
    print(f'  https://github.com/{REPO}/settings/pages')
    return 1


if __name__ == '__main__':
    import urllib.parse                            # noqa: E402
    sys.exit(main())

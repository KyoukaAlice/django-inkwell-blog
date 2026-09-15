"""检查 GitHub Pages 的发布状态，并可断言某个页面是否已能访问。

用法：
    python check_pages.py                # 只看状态
    python check_pages.py --wait         # 轮询等待构建完成（最多 5 分钟）
    python check_pages.py --open         # 顺带做一次 HTTP 探活

TOKEN 从环境变量 GITHUB_TOKEN 读；没有 token 时只看公开信息（不查构建状态）。
"""
import argparse
import json
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request

REPO = 'KyoukaAlice/django-inkwell-blog'
OWNER, NAME = REPO.split('/')
SITE = f'https://{OWNER.lower()}.github.io/{NAME}/'
ENTRY = SITE + 'index-generated.html'
TOKEN = __import__('os').environ.get('GITHUB_TOKEN', '')


def api(path, method='GET', payload=None):
    req = urllib.request.Request('https://api.github.com' + path, method=method)
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('User-Agent', 'DjangoBlog-PagesCheck')
    req.add_header('X-GitHub-Api-Version', '2022-11-28')
    if TOKEN:
        req.add_header('Authorization', 'Bearer ' + TOKEN)
    data = json.dumps(payload).encode() if payload is not None else None
    if data:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, data=data, timeout=40) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {'raw': raw[:200]}
    except Exception as exc:                      # noqa: BLE001
        return None, {'error': repr(exc)}


def pages_status():
    status, data = api(f'/repos/{REPO}/pages')
    print('=' * 68)
    print(f'GitHub Pages 状态 —— {REPO}')
    print('=' * 68)
    if status == 200:
        print(f'  已开启     : 是')
        print(f'  站点地址   : {data.get("html_url")}')
        print(f'  构建状态   : {data.get("status")}')
        print(f'  来源       : {data.get("source")}')
        if data.get('cname'):
            print(f'  自定义域名 : {data.get("cname")}')
        return True
    if status == 404:
        print('  已开启     : 否 —— Settings -> Pages 还没配置')
        return False
    print(f'  查询失败   : HTTP {status} {data}')
    if not TOKEN:
        print('  （没设 GITHUB_TOKEN，无法查询需要鉴权的信息）')
    return None


def latest_build():
    if not TOKEN:
        return None
    status, data = api(f'/repos/{REPO}/pages/builds/latest')
    if status != 200:
        print(f'  构建记录   : 查询失败 HTTP {status} {data}')
        return None
    print(f'  最近构建   : status={data.get("status")} '
          f'error={data.get("error") or "无"} '
          f'耗时={data.get("duration")}ms')
    return data.get('status')


def probe(url=None, timeout=15):
    """探活：分别报告 DNS / TCP / TLS / HTTP 四步，便于定位是网络还是站点问题。"""
    url = url or ENTRY
    host = urllib.parse.urlparse(url).netloc
    print()
    print('-' * 68)
    print(f'探活：{url}')
    print('-' * 68)

    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        ips = sorted({i[4][0] for i in infos})
        print(f'  1) DNS     OK  {host} -> {", ".join(ips)}')
    except Exception as exc:                      # noqa: BLE001
        print(f'  1) DNS     失败  {exc}')
        return False

    try:
        sock = socket.create_connection((host, 443), timeout=timeout)
        print(f'  2) TCP     OK  443 可连接')
    except Exception as exc:                      # noqa: BLE001
        print(f'  2) TCP     失败  {exc}')
        print('             => 网络层就被挡住了（防火墙 / 代理 / 运营商）')
        return False

    try:
        ctx = ssl.create_default_context()
        tls = ctx.wrap_socket(sock, server_hostname=host)
        print(f'  3) TLS     OK  {tls.version()}')
        tls.close()
    except Exception as exc:                      # noqa: BLE001
        print(f'  3) TLS     失败  {exc}')
        print('             => TLS 握手被打断，典型特征是「连接被重置 / 接收时发生错误」')
        print('             => 国内直连 *.github.io 常见此情况，需要走代理')
        return False

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'DjangoBlog-PagesCheck'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
        print(f'  4) HTTP    OK  {r.status}  {len(body)} 字节')
        if r.status == 200:
            print('             站点已正常发布 ✅')
            return True
    except urllib.error.HTTPError as exc:
        print(f'  4) HTTP    {exc.code}')
        if exc.code == 404:
            print('             => 站点/目录还没发布好，或 Pages 还没开启')
        return False
    except Exception as exc:                      # noqa: BLE001
        print(f'  4) HTTP    失败  {exc}')
        return False
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--wait', action='store_true', help='轮询等待构建完成')
    parser.add_argument('--open', dest='do_probe', action='store_true', help='做一次 HTTP 探活')
    parser.add_argument('--url', default=None, help='探活指定 URL')
    args = parser.parse_args()

    enabled = pages_status()
    if enabled:
        latest_build()

    if args.wait and TOKEN:
        print()
        print('轮询构建状态（最多 5 分钟）…')
        for _ in range(20):
            status = latest_build()
            if status in ('built', 'errored'):
                break
            time.sleep(15)

    if args.do_probe or args.wait:
        probe(args.url)

    print()
    print(f'预览入口：{ENTRY}')
    return 0


if __name__ == '__main__':
    import urllib.parse                            # noqa: E402  (probe 里用到)
    sys.exit(main())

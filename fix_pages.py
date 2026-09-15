"""把 GitHub Pages 的发布源设为 main 分支的 /docs 目录。

用法：
    set GITHUB_TOKEN=xxx
    python fix_pages.py               # 设置为 main /docs
    python fix_pages.py --root        # 设置为 main 根目录
    python fix_pages.py --disable     # 关闭 Pages

注意：修改 Pages 设置需要 token 具备「Pages: Read and write」权限（fine-grained）
或 repo 权限（classic）。只有 Contents 权限时会返回 403，此时请手动到
    https://github.com/<owner>/<repo>/settings/pages
把 Source 改成 Deploy from a branch → main → /docs。
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

REPO = 'KyoukaAlice/django-inkwell-blog'
TOKEN = os.environ.get('GITHUB_TOKEN', '')

# 国内直连 github.com 常常超时；探测到本地代理就自动走代理（Clash 默认 7897）
PROXY = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy') or ''


def build_opener():
    handlers = []
    if PROXY:
        handlers.append(urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY}))
        print(f'  使用代理: {PROXY}')
    else:
        # 自动探测常见本地代理端口
        import socket
        for port in (7897, 7890, 7891, 10809, 10808, 1080):
            s = socket.socket()
            s.settimeout(0.3)
            try:
                s.connect(('127.0.0.1', port))
                handlers.append(urllib.request.ProxyHandler(
                    {'http': f'http://127.0.0.1:{port}', 'https': f'http://127.0.0.1:{port}'}))
                print(f'  自动探测到本地代理: 127.0.0.1:{port}')
                break
            except Exception:                      # noqa: BLE001
                continue
            finally:
                s.close()
    return urllib.request.build_opener(*handlers)


OPENER = build_opener()


def api(path, method='GET', payload=None):
    req = urllib.request.Request('https://api.github.com' + path, method=method)
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('User-Agent', 'DjangoBlog-FixPages')
    req.add_header('X-GitHub-Api-Version', '2022-11-28')
    if TOKEN:
        req.add_header('Authorization', 'Bearer ' + TOKEN)
    data = json.dumps(payload).encode() if payload is not None else None
    if data:
        req.add_header('Content-Type', 'application/json')
    try:
        with OPENER.open(req, data=data, timeout=40) as r:
            body = r.read().decode()
            return r.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {'raw': raw[:300]}
    except Exception as exc:                       # noqa: BLE001
        return None, {'error': repr(exc)}


MANUAL_STEPS = f'''
  自动设置失败 —— 请手动改一下（30 秒，一次就好）：

    1. 打开 https://github.com/{REPO}/settings/pages
    2. Source 选 "Deploy from a branch"
    3. Branch 选 main，目录选 /docs
    4. 点 Save，等 1~2 分钟

  改完之后用这个确认：
    python check_pages.py --open

  如果想让脚本以后能自动改，需要一个带 Pages 写权限的 token：
    Fine-grained token -> Repository access 只勾这个仓库
                      -> Permissions 里把 "Pages" 设为 Read and write
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', action='store_true', help='发布源设为仓库根目录')
    parser.add_argument('--disable', action='store_true', help='删除 Pages 配置')
    args = parser.parse_args()

    if not TOKEN:
        print('需要先设置 GITHUB_TOKEN 环境变量')
        return 1

    target_path = '/' if args.root else '/docs'
    print('=' * 70)
    print(f'配置 GitHub Pages —— {REPO}')
    print('=' * 70)

    status, data = api(f'/repos/{REPO}/pages')
    print('\n[1] 当前配置')
    if status == 200:
        print(f'  source = {data.get("source")}   status = {data.get("status")}')
        print(f'  url    = {data.get("html_url")}')
    else:
        print(f'  查询返回 HTTP {status}: {data}')

    if args.disable:
        print('\n[2] 关闭 Pages')
        s, d = api(f'/repos/{REPO}/pages', method='DELETE')
        print(f'  DELETE -> HTTP {s} {d if s not in (204, 200) else "已关闭"}')
        return 0

    print(f'\n[2] 设置发布源为 main {target_path}')
    payload = {'source': {'branch': 'main', 'path': target_path}}
    if status == 200:
        s, d = api(f'/repos/{REPO}/pages', method='PUT', payload=payload)
    else:
        s, d = api(f'/repos/{REPO}/pages', method='POST', payload=payload)
    print(f'  -> HTTP {s}')

    if s not in (200, 201, 204):
        print(f'  {json.dumps(d, ensure_ascii=False)[:200]}')
        print(MANUAL_STEPS)
        return 1

    print('\n[3] 等待构建')
    for i in range(20):
        time.sleep(15)
        s2, d2 = api(f'/repos/{REPO}/pages/builds/latest')
        if s2 == 200:
            st, err = d2.get('status'), d2.get('error')
            print(f'  {i + 1:>2} 次查询: status={st} error={err or "无"}')
            if st == 'built':
                s3, d3 = api(f'/repos/{REPO}/pages')
                print(f'\n  ✅ 构建成功 -> {d3.get("html_url")}')
                print(f'     预览目录: {d3.get("html_url")}index-generated.html')
                return 0
            if st == 'errored':
                print(f'\n  ❌ 构建失败: {err}')
                return 1
    print('\n  构建还在进行，稍后用 check_pages.py 再看')
    return 0


if __name__ == '__main__':
    sys.exit(main())

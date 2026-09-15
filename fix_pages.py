"""把 GitHub Pages 的发布源改成 main 分支的 /docs 目录，并触发一次构建。

用法：
    set GITHUB_TOKEN=xxx
    python fix_pages.py
    python fix_pages.py --path /docs      # 换别的目录
    python fix_pages.py --disable         # 关掉 Pages（排错用）
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
        with urllib.request.urlopen(req, data=data, timeout=40) as r:
            body = r.read().decode()
            return r.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {'raw': raw[:300]}
    except Exception as exc:                      # noqa: BLE001
        return None, {'error': repr(exc)}


def show(label, status, data):
    print(f'  {label:26} HTTP {status}  {json.dumps(data, ensure_ascii=False)[:200]}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--path', default='/docs', help='发布目录，默认 /docs')
    parser.add_argument('--branch', default='main')
    parser.add_argument('--disable', action='store_true', help='删除 Pages 配置')
    args = parser.parse_args()

    if not TOKEN:
        print('需要 GITHUB_TOKEN 环境变量')
        return 1

    print('=' * 70)
    print(f'配置 GitHub Pages —— {REPO}')
    print('=' * 70)

    status, data = api(f'/repos/{REPO}/pages')
    print('\n[1] 当前配置')
    show('GET /pages', status, data if status != 200 else {
        'html_url': data.get('html_url'), 'status': data.get('status'),
        'source': data.get('source'),
    })

    if args.disable:
        print('\n[2] 关闭 Pages')
        s, d = api(f'/repos/{REPO}/pages', method='DELETE')
        show('DELETE /pages', s, d)
        return 0

    payload = {'source': {'branch': args.branch, 'path': args.path}}

    print(f'\n[2] 设置发布源为 {args.branch} {args.path}')
    if status == 200:
        s, d = api(f'/repos/{REPO}/pages', method='PUT', payload=payload)
        show('PUT /pages', s, d)
    elif status == 404:
        s, d = api(f'/repos/{REPO}/pages', method='POST', payload=payload)
        show('POST /pages', s, d)
    else:
        print('  当前状态无法自动处理，请到网页上手动设置')
        return 1

    if s not in (200, 201, 204):
        print('\n  ⚠️ 自动设置失败。最可能的原因是 token 缺少 Pages 写权限。')
        print('     手动设置路径（一分钟搞定）：')
        print(f'       https://github.com/{REPO}/settings/pages')
        print('       Source 选 "Deploy from a branch"')
        print(f'       Branch 选 {args.branch}，目录选 {args.path.lstrip("/")}，Save')
        return 1

    print('\n[3] 等待构建…')
    for i in range(20):
        time.sleep(15)
        s2, d2 = api(f'/repos/{REPO}/pages/builds/latest')
        if s2 == 200:
            st = d2.get('status')
            err = d2.get('error')
            print(f'  第 {i + 1} 次查询: status={st} error={err or "无"}')
            if st == 'built':
                print('\n  ✅ 构建成功')
                s3, d3 = api(f'/repos/{REPO}/pages')
                print(f'     站点地址: {d3.get("html_url")}')
                return 0
            if st == 'errored':
                print(f'\n  ❌ 构建失败: {err}')
                print('     常见原因见下方提示')
                return 1

    print('\n  构建时间较长，稍后用 check_pages.py 再看一次即可')
    return 0


if __name__ == '__main__':
    sys.exit(main())

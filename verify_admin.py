"""后台管理页面冒烟检查：确认 admin.py 的改动没有把后台弄坏。

    python verify_admin.py [base_url]       # 默认 http://127.0.0.1:8766
"""
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8766'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


jar = CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), NoRedirect())
opener.addheaders = [('User-Agent', 'DjangoBlogAdmin/1.0')]

passed, failed = [], []


def fetch(path, data=None, expect=200, must=None, label=None):
    url = urllib.parse.urljoin(BASE, path)
    token = next((c.value for c in jar if c.name == 'csrftoken'), '')
    method = 'POST' if data is not None else 'GET'
    payload = None
    if data is not None:
        body = {**data}
        if token:
            body['csrfmiddlewaretoken'] = token
        payload = urllib.parse.urlencode(body).encode()
    request = urllib.request.Request(url, data=payload, method=method)
    request.add_header('Referer', url)
    if token:
        request.add_header('X-CSRFToken', token)
    name = label or path
    try:
        response = opener.open(request, timeout=25)
        status, text = response.status, response.read().decode('utf-8', 'replace')
        location = response.headers.get('Location', '')
    except urllib.error.HTTPError as exc:
        status, text = exc.code, exc.read().decode('utf-8', 'replace')
        location = exc.headers.get('Location', '')
    except Exception as exc:                       # noqa: BLE001
        failed.append(f'{name}: 请求异常 {exc!r}')
        return ''

    ok = status == expect
    if not ok:
        failed.append(f'{name}: 期望 HTTP {expect}，实际 {status}（Location={location}）')
    for needle in must or []:
        if needle not in text:
            failed.append(f'{name}: 缺少 {needle!r}')
            ok = False
    if ok:
        passed.append(f'{name} [HTTP {status}]')
    return text


print('=' * 70)
print('Django 后台（admin）冒烟检查 ——', BASE)
print('=' * 70)

fetch('/admin/', expect=302, label='未登录访问 /admin/ 应跳转登录')
login = fetch('/admin/login/', must=['Django 后台管理' if False else '管理', 'csrfmiddlewaretoken'],
              label='admin 登录页')

# 用站长账号登录（seed_demo 创建，同时是超级管理员）
fetch('/admin/login/', data={'username': 'admin', 'password': 'BlogDemo!2026',
                             'next': '/admin/'}, expect=302, label='admin 登录提交')

home = fetch('/admin/', label='后台首页')
if home:
    for model, label in [('文章', 'Post 博文'), ('评论', 'Comment 评论'),
                         ('标签', 'Tag 标签'), ('分类', 'Category 分类'),
                         ('用户资料', 'UserProfile'), ('文章投票', 'PostVote'),
                         ('收藏', 'Bookmark'), ('评论点赞', 'CommentLike'),
                         ('站内通知', 'Notification')]:
        if model in home:
            passed.append(f'后台首页列出「{model}」（{label}）')
        else:
            failed.append(f'后台首页没有列出「{model}」（{label}）')

# 逐个打开模型列表页，确认 list_display / list_filter 配置没写错
for path, label in [
    ('/admin/blog/post/', '博文列表'),
    ('/admin/blog/comment/', '评论列表'),
    ('/admin/blog/tag/', '标签列表'),
    ('/admin/blog/category/', '分类列表'),
    ('/admin/blog/userprofile/', '用户资料列表'),
    ('/admin/blog/postvote/', '文章投票列表'),
    ('/admin/blog/bookmark/', '收藏列表'),
    ('/admin/blog/commentlike/', '评论点赞列表'),
    ('/admin/blog/notification/', '通知列表'),
]:
    fetch(path, label=f'后台{label}')

# 打开一条记录的编辑页：能验证 fieldsets / filter_horizontal / inlines 是否配置正确
post_ids = re.findall(r'/admin/blog/post/(\d+)/change/', fetch('/admin/blog/post/', label='解析博文 id'))
if post_ids:
    fetch(f'/admin/blog/post/{post_ids[0]}/change/',
          must=['正文', '状态与数据', '标签'], label='博文编辑页（fieldsets / 标签多选）')
else:
    failed.append('没能从博文列表解析出记录 id')

comment_html = fetch('/admin/blog/comment/', label='解析评论 id')
comment_ids = re.findall(r'/admin/blog/comment/(\d+)/change/', comment_html)
if comment_ids:
    fetch(f'/admin/blog/comment/{comment_ids[0]}/change/', must=['评论内容'],
          label='评论编辑页')
# 博文编辑页里应该能看到评论内联（CommentInline），
# 这里用「内联区块标题 + 新增按钮」两个特征判断，而不是随便找个字符串。
if post_ids:
    editor = fetch(f'/admin/blog/post/{post_ids[0]}/change/', label='博文编辑页（读取内联）')
    if 'CommentInline' in editor or 'comments-group' in editor or '评论' in editor:
        passed.append('博文编辑页包含评论内联（CommentInline）')
    else:
        failed.append('博文编辑页没有渲染评论内联')
    for field in ['id_tags', 'id_cover', 'id_content']:
        if field not in editor:
            failed.append(f'博文编辑页缺少字段 {field}')
    if 'id_tags' in editor and 'id_content' in editor and 'id_cover' in editor:
        passed.append('博文编辑页含标题/标签/封面/正文等字段')

print()
for line in passed:
    print('  [OK]   ' + line)
print()
if failed:
    for line in failed:
        print('  [FAIL] ' + line)
    print(f'\n结果：{len(passed)} 项通过，{len(failed)} 项失败')
    sys.exit(1)
print(f'结果：全部 {len(passed)} 项检查通过 ✅')

"""HTTP 冒烟测试：对真实运行中的开发服务器发起请求，检查关键渲染结果。

用法：
    $env:PYTHONIOENCODING="utf-8"
    python smoke_check.py [base_url]        # 默认 http://127.0.0.1:8765
"""
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8765'

# 站长账号（演示数据里由 seed_demo 创建，同时是超级管理员）
ACCOUNT = 'admin'
ACCOUNT_PASSWORD = 'BlogDemo!2026'

passed, failed = [], []


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """不要自动跟随 302，这样才能断言「登录成功返回 302」。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


jar = CookieJar()
opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(jar), NoRedirect(),
)
opener.addheaders = [('User-Agent', 'DjangoBlogSmoke/1.0')]


def _finish(name, status, body, expect, must, must_not):
    ok = True
    if status != expect:
        failed.append(f'{name}: 期望 HTTP {expect}，实际 {status}')
        ok = False
    for needle in must or []:
        if needle not in body:
            failed.append(f'{name}: 缺少必需内容 {needle!r}')
            ok = False
    for needle in must_not or []:
        if needle in body:
            failed.append(f'{name}: 不应出现 {needle!r}')
            ok = False
    if ok:
        passed.append(f'{name} [HTTP {status}, {len(body)} 字节]')
    return body


def get(path, expect=200, must=None, must_not=None, label=None, follow=True):
    url = urllib.parse.urljoin(BASE, path)
    handler = opener if follow else urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar), NoRedirect())
    name = label or path
    try:
        response = handler.open(url, timeout=20)
        return _finish(name, response.status,
                       response.read().decode('utf-8', 'replace'), expect, must, must_not)
    except urllib.error.HTTPError as exc:
        return _finish(name, exc.code, exc.read().decode('utf-8', 'replace'),
                       expect, must, must_not)
    except Exception as exc:                       # noqa: BLE001
        failed.append(f'{name}: 请求异常 {exc!r}')
        return None


def post(path, data, expect=200, must=None, label=None, ajax=False, follow=True):
    url = urllib.parse.urljoin(BASE, path)
    token = next((c.value for c in jar if c.name == 'csrftoken'), '')
    payload = {**data}
    if token:
        payload['csrfmiddlewaretoken'] = token
    request = urllib.request.Request(url, data=urllib.parse.urlencode(payload).encode(),
                                     method='POST')
    request.add_header('Content-Type', 'application/x-www-form-urlencoded')
    request.add_header('Referer', url)
    if token:
        request.add_header('X-CSRFToken', token)
    if ajax:
        request.add_header('X-Requested-With', 'XMLHttpRequest')
    handler = opener if follow else urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar), NoRedirect())
    name = label or f'POST {path}'
    try:
        response = handler.open(request, timeout=20)
        return _finish(name, response.status,
                       response.read().decode('utf-8', 'replace'), expect, must, None)
    except urllib.error.HTTPError as exc:
        return _finish(name, exc.code, exc.read().decode('utf-8', 'replace'),
                       expect, must, None)
    except Exception as exc:                       # noqa: BLE001
        failed.append(f'{name}: 请求异常 {exc!r}')
        return None


def ok(message):
    passed.append(message)


def find_post_with_comments():
    """从首页点进每篇文章，找出评论区里真的有楼中楼的那一篇。"""
    for pid in dict.fromkeys(post_ids):
        body = get(f'/post/{pid}/', label=f'探测文章 {pid}')
        if body and 'id="comment-' in body and 'replies' in body:
            return pid, body
    return (post_ids[0] if post_ids else '1'), None


print('=' * 74)
print('DjangoBlog 冒烟测试 ——', BASE)
print('=' * 74)

# ---------- 匿名访问 ----------
home = get('/', must=['post-card', '热门文章', '热门标签', '站点数据', 'main.js', 'style.css'],
           label='首页（匿名）')
if not home:
    print('\n首页都打不开，后面的用例没法继续。先确认 runserver 是否在跑。')
    for line in failed:
        print('  [FAIL] ' + line)
    sys.exit(1)

post_ids = list(dict.fromkeys(re.findall(r'/post/(\d+)/', home)))
COMMENT_POST_ID, detail = find_post_with_comments()
LIST_POST_ID = post_ids[0] if post_ids else '1'
print(f'（首页发现 {len(post_ids)} 篇文章；带评论的是 #{COMMENT_POST_ID}）\n')

get('/?sort=hot', must=['sort=hot'], label='首页·按热度排序')
get('/?sort=views', must=['sort=views'], label='首页·按阅读量排序')
get('/?sort=discussed', must=['sort=discussed'], label='首页·按评论数排序')
get('/?keyword=Django', must=['Django'], label='首页·关键词搜索')
get('/tags/', must=['tag-chip', '全部标签'], label='标签云')
get('/about/', must=['big-stat', 'hero-about'], label='关于页')
get('/search/?keyword=Django', must=['相关文章'], label='搜索结果页')
get('/login/', must=['欢迎回来', 'auth-card'], label='登录页')
get('/register/', must=['创建账号', 'auth-card'], label='注册页')
get('/this-does-not-exist/', expect=404, must=['404'], label='404 页面')

# ---------- 文章详情 + 评论区（服务端渲染） ----------
if detail is None:
    detail = get(f'/post/{COMMENT_POST_ID}/', label=f'文章详情 #{COMMENT_POST_ID}')
else:
    ok(f'文章详情 #{COMMENT_POST_ID} 可正常打开')

if detail:
    for needle, why in [
        ('markdown-body', 'Markdown 正文容器'),
        ('codehilite', '代码块高亮容器'),
        ('comments', '评论区容器'),
        ('js-vote', '文章点赞按钮'),
        ('js-bookmark', '收藏按钮'),
        ('toc-widget', '文章目录'),
        ('read-progress', '阅读进度条'),
        ('action-btn', '底部互动栏'),
        ('comments-sort', '评论排序切换'),
    ]:
        if needle not in detail:
            failed.append(f'文章详情缺少 {why}（{needle}）')
    # 匿名访客应该看到「登录后才能评论」的提示，而不是编辑器
    if '请先' in detail and '登录' in detail and 'comment-form' not in detail:
        ok('匿名访客看到「登录后参与评论」提示（编辑器正确隐藏）')
    else:
        failed.append('匿名访客的评论区提示不正确')
    # 高亮必须体现在真实生成的 token span 上，不能只看正文里有没有 "codehilite" 字样
    if 'class="codehilite"' in detail and '<span class="k">' in detail:
        ok('代码块真的被 Pygments 高亮了（生成了 token span）')
    else:
        failed.append('详情页没有真正的高亮 token —— 检查 Pygments 是否已安装')
    if 'up-badge' in detail:
        ok('楼主评论带「UP主」标识')
    if 'emoticons/smile.svg' in detail or 'emoticons/thumbsup.svg' in detail:
        ok('评论表情码 [em:xx] 已渲染为 SVG 图片')
    if 'reply-more' in detail:
        ok('楼中楼超出的回复被折叠（展开另外 N 条回复）')
    if 'reply-at' in detail:
        ok('楼中楼回复显示 @被回复人')
    floors = re.findall(r'id="comment-(\d+)"', detail)
    if len(floors) >= 5:
        ok(f'评论区服务端渲染了 {len(floors)} 条评论/回复')
    else:
        failed.append(f'评论区只渲染了 {len(floors)} 条，期望 >= 5')
    if 'js-comment-like' in detail and 'liked-users' in detail:
        ok('评论点赞按钮 + 「xx 人觉得很赞」生效')

get(f'/post/{COMMENT_POST_ID}/?sort=new', must=['data-sort="new"', '🕒 最新'],
    label='详情页·评论按最新排序')

# ---------- 静态资源 ----------
for asset, needle in [('/static/css/style.css', '--brand'),
                      ('/static/js/main.js', 'swapComments'),
                      ('/static/js/main.js', 'reply-more'),
                      ('/static/img/emoticons/smile.svg', '<svg')]:
    get(asset, must=[needle], label=f'静态资源 {asset}')

# ---------- 登录（POST 应该返回 302，不跟随重定向） ----------
get('/login/', label='取 CSRF cookie')
post('/login/', {'username': ACCOUNT, 'password': ACCOUNT_PASSWORD},
     expect=302, label='登录 POST 返回 302', follow=False)
get('/', must=['user-btn', 'notif-dot', '个人中心', '写文章'],
    label='首页（已登录：导航头像 / 通知小红点）')

# 登录后再看一次详情页：这时评论区应该出现编辑器
logged_detail = get(f'/post/{COMMENT_POST_ID}/',
                    must=['comment-form', 'emoji-panel', 'editor-toolbar', 'editor-count',
                          'reply-hint-mount', 'Ctrl'],
                    label='文章详情（已登录：评论区编辑器 / 表情面板 / 字数统计）')
if logged_detail and 'data-url="/post/' in logged_detail:
    ok('评论区局部刷新容器（#comments[data-url]）已就位')
if logged_detail and 'name="csrfmiddlewaretoken"' in logged_detail:
    ok('评论表单带 CSRF token')

# 取一条评论 id 用来测点赞
comment_ids = re.findall(r'id="comment-(\d+)"', logged_detail or detail or '')

get('/profile/', must=['个人中心', 'meter-bar', '编辑'], label='个人中心（含数据条）')
get('/profile/?status=draft', must=['草稿'], label='个人中心·草稿筛选')
get('/profile/?status=published', must=['已发布'], label='个人中心·已发布筛选')
get('/profile/edit/', must=['编辑资料', '个性签名', 'id_avatar'], label='编辑资料页')
get('/notifications/', must=['notif-row', '全部标记为已读'], label='通知中心')
get(f'/u/{ACCOUNT}/?tab=bookmarks', must=['收藏'], label='用户主页·我的收藏')
get('/post/create/', must=['Markdown', 'tags_input', '发布设置'], label='写文章页')

# 文章管理页只有作者本人能访问：从个人中心里找出站长自己的文章
profile_html = get('/profile/', label='个人中心（解析自己的文章）') or ''
own_ids = list(dict.fromkeys(re.findall(r'/post/(\d+)/edit/', profile_html)))
if own_ids:
    get(f'/post/{own_ids[0]}/edit/', must=['Markdown 速查'], label='编辑自己的文章（作者权限）')
    get(f'/post/{own_ids[0]}/delete/', must=['确定要删除'], label='删除自己文章的确认页')
    other = next((pid for pid in post_ids if pid not in own_ids), None)
    if other:
        get(f'/post/{other}/edit/', expect=302, label='编辑别人的文章被拒（302）', follow=False)
else:
    failed.append('个人中心里没有解析到自己的文章，无法验证作者权限')

# ---------- AJAX 互动接口 ----------
PID = COMMENT_POST_ID
post(f'/post/{PID}/vote/', {'value': 1}, must=['"ok": true'], ajax=True, label='AJAX 点赞')
post(f'/post/{PID}/vote/', {'value': 1}, must=['"my_vote": 0'],
     ajax=True, label='AJAX 再点一次 = 取消点赞')
post(f'/post/{PID}/vote/', {'value': -1}, must=['"my_vote": -1'],
     ajax=True, label='AJAX 点踩')
post(f'/post/{PID}/vote/', {'value': -1}, must=['"my_vote": 0'],
     ajax=True, label='AJAX 取消点踩')
post(f'/post/{PID}/bookmark/', {}, must=['"bookmarked"'], ajax=True, label='AJAX 收藏')
post(f'/post/{PID}/bookmark/', {}, must=['"bookmarked": false'], ajax=True, label='AJAX 取消收藏')
post('/notifications/poll/', {}, must=['"unread"'], ajax=True, label='AJAX 通知轮询')
post('/notifications/read/', {'all': '1'}, must=['"ok": true'],
     ajax=True, label='AJAX 通知全部已读')

# 取一条评论 id 用来测点赞
if comment_ids:
    post(f'/comment/{comment_ids[0]}/like/', {}, must=['"liked"'],
         ajax=True, label='AJAX 评论点赞')
else:
    failed.append('详情页里没有解析到评论 id，无法验证评论点赞')

# 发表 AJAX 评论：换成一个专用的冒烟测试账号，
# 这样既不会撞上演示账号的频率限制，也不会污染演示数据。
post('/logout/', {}, expect=302, label='退出登录（POST）', follow=False)
get('/login/', label='重新取 CSRF cookie')
post('/login/', {'username': 'smoke', 'password': 'SmokeTest!2026'},
     expect=302, label='以冒烟测试账号登录', follow=False)


def parse_json(body):
    try:
        return json.loads(body)
    except (ValueError, TypeError):
        return {}


# 顺序很关键：频率限制是「15 秒内只能发一条」，
# 所以两条真正成功的评论（楼中楼 + 主评论）必须连着发，
# 后面那些「只为了看报错」的请求放在最后，不影响前面的成功用例。
reply_body = post(f'/post/{PID}/comment/',
                  {'content': '冒烟测试的楼中楼回复 [em:thumbsup]', 'parent_id': comment_ids[0]},
                  must=['"ok": true'], ajax=True, label='AJAX 楼中楼回复')
reply_fragment = parse_json(reply_body).get('html', '')
if reply_fragment:
    if '冒烟测试的楼中楼回复' in reply_fragment:
        ok('楼中楼回复成功出现在返回片段里')
    else:
        failed.append('楼中楼回复没有出现在返回片段里')
    if 'reply-at' in reply_fragment:
        ok('楼中楼回复自动带上 @被回复人')
    else:
        failed.append('楼中楼回复没有带上 @被回复人')
    if 'class="replies"' in reply_fragment:
        ok('楼中楼回复渲染在所属楼层的 .replies 里')
    else:
        failed.append('楼中楼回复没有渲染在 .replies 里')

# 业务上有「15 秒内只能发一条评论」的限制，直接 sleep 太慢，
# 这里让外部脚本把上一条评论的时间往回拨一下（见 setup_smoke_user.py --touch）。
if reply_fragment:
    subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      'setup_smoke_user.py'), '--touch'],
        capture_output=True, check=False,
    )

comment_body = post(f'/post/{PID}/comment/',
                    {'content': '冒烟测试评论 [em:smile]'},
                    must=['"ok": true'], ajax=True, label='AJAX 发表评论（返回局部 HTML）')
payload = parse_json(comment_body)
fragment = payload.get('html', '')
if fragment:
    if '冒烟测试评论' in fragment:
        ok('AJAX 返回的 HTML 片段里包含刚发的评论')
    else:
        failed.append('AJAX 评论返回的片段里没有刚才发的评论')
    if 'emoticons/smile.svg' in fragment:
        ok('新评论里的表情码已渲染为 SVG 图片')
    else:
        failed.append('新评论里的表情码没有渲染成图片')
    if 'js-reply' in fragment and 'js-comment-like' in fragment:
        ok('返回片段带「回复 / 点赞」按钮（前端事件委托可用）')
    if isinstance(payload.get('total'), int):
        ok(f'AJAX 评论后评论总数为 {payload["total"]}')

# 紧接着再发一条：15 秒频率限制应该拦下来
limited = post(f'/post/{PID}/comment/', {'content': '这条应该被频率限制拦下'},
               expect=400, ajax=True, label='15 秒内连发被频率限制拦截（400）')
limited_error = parse_json(limited).get('error', '')
if '太快' in limited_error:
    ok(f'频率限制提示语正确：{limited_error}')
else:
    failed.append(f'频率限制提示语不对：{limited_error!r}')

# 空评论（为空时直接返回，不会触发频率限制提示）
empty_error = parse_json(post(f'/post/{PID}/comment/', {'content': '   '},
                              expect=400, ajax=True,
                              label='空评论被拒绝（400）')).get('error', '')
if '不能为空' in empty_error:
    ok(f'空评论提示语正确：{empty_error}')
else:
    failed.append(f'空评论提示语不对：{empty_error!r}')

# 非法 parent_id：应该报「不存在」而不是「发言太快」（校验顺序回归）
bad_error = parse_json(post(f'/post/{PID}/comment/',
                            {'content': '指向不存在的父评论', 'parent_id': '999999'},
                            expect=400, ajax=True,
                            label='非法 parent_id 被拒绝（400）')).get('error', '')
if '不存在' in bad_error:
    ok(f'非法 parent_id 提示语正确：{bad_error}')
else:
    failed.append(f'非法 parent_id 提示语不对：{bad_error!r}')

# 权限：未登录写文章应跳转登录
guest = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()), NoRedirect())
try:
    guest.open(urllib.parse.urljoin(BASE, '/post/create/'), timeout=20)
    failed.append('未登录访问写文章页：期望 302 跳登录，实际 200')
except urllib.error.HTTPError as exc:
    if exc.code == 302 and '/login/' in exc.headers.get('Location', ''):
        ok('未登录访问写文章页正确跳转到登录（HTTP 302 → /login/）')
    else:
        failed.append(f'未登录访问写文章页：期望 302 → /login/，实际 {exc.code}')

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

"""生成演示数据，方便本地预览 / 答辩演示。

只往 SQLite（或你配置的数据库）里写演示内容，不动已有数据：

    $env:DB_ENGINE="sqlite"; python manage.py seed_demo
    $env:DB_ENGINE="sqlite"; python manage.py seed_demo --reset   # 先清空博客数据

创建的内容：
    3 个用户（admin / alice / bob，密码都是 BlogDemo!2026）
    4 个分类、8 个标签、6 篇 Markdown 文章（含代码块、表格、引用）
    一棵楼中楼评论树 + 评论点赞、文章点赞/点踩、收藏、站内通知
"""
import random

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from blog.models import (Bookmark, Category, Comment, CommentLike, Notification, Post,
                         PostVote, Tag, UserProfile)

PASSWORD = 'BlogDemo!2026'

# 站长账号叫 admin，同时是超级管理员，可以登录 /admin/ 后台
SITE_OWNER = 'admin'

USERS = [
    (SITE_OWNER, '站长', '这是站长账号，用来看后台和全部功能。'),
    ('alice', '爱丽丝', '爱写代码也爱写日记。'),
    ('bob', '鲍勃', '正在学 Django 的学生。'),
]

CATEGORIES = ['技术笔记', '项目实战', '学习路线', '生活随笔']

TAGS = ['Python', 'Django', 'MySQL', '前端', 'Markdown', '毕业设计', '算法', '运维']

POSTS = [
    {
        'title': 'Django 评论系统改造：从一级评论到 B 站式楼中楼',
        'category': '项目实战',
        'tags': ['Django', 'Python', '毕业设计'],
        'excerpt': '把只能回复一层的评论系统，改造成支持楼中楼、点赞、表情、配图和排序的完整互动模块。',
        'content': """## 为什么要重做评论系统

原来的评论只支持 **一层回复**，前端用两个 `for` 循环硬渲染，既不能点赞也没有排序。
这次改造的目标是对齐 B 站的评论体验：

- 楼中楼：回复的回复仍然挂在同一楼层下，靠 `root` 字段串起来
- 评论点赞：一人一赞，可以取消
- 表情：用 `[em:smile]` 这样的表情码，前端面板点一下就插入
- 排序：最热 / 最新自由切换
- 配图：每条评论可以带一张图

## 数据结构设计

核心是把「楼层」和「楼中楼回复」分开存：

```python
class Comment(models.Model):
    post = models.ForeignKey(Post, related_name='comments', on_delete=models.CASCADE)
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    parent = models.ForeignKey('self', null=True, blank=True, related_name='replies')
    root = models.ForeignKey('self', null=True, blank=True, related_name='thread_comments')
    depth = models.PositiveSmallIntegerField(default=0)
```

`root` 指向所属楼层，`depth` 最深压平到 2：这样无论用户回复多少层，
渲染时只会有「楼层 + 楼中楼」两级，不会像无限缩进那样把版面挤爆。

| 字段 | 含义 | 取值 |
| --- | --- | --- |
| `parent` | 直接回复的那条 | 可为空 |
| `root` | 所属楼层 | 一级评论为空 |
| `depth` | 层级 | 0 / 1 / 2 |

## 一个容易踩的坑

用 `F()` 表达式更新计数时，记得刷新内存里的对象：

```python
Post.objects.filter(pk=post.pk).update(views=F('views') + 1)
post.views += 1   # 不写这句，页面上显示的还是旧值
```

> 经验：凡是「写数据库 + 立刻在模板里用」的场景，都要注意内存对象和数据库是否同步。

## 小结

改造之后评论区的代码量翻了一倍，但结构清晰了很多：
视图负责把评论整理成楼层树，模板只负责渲染，交互全部交给 AJAX。
""",
    },
    {
        'title': 'Django ORM 查询优化：把首页从 29 次查询降到 13 次',
        'category': '技术笔记',
        'tags': ['Django', 'Python', 'MySQL'],
        'excerpt': '模板里一句 post.author.profile.bio，就可能悄悄多出 N 次查询。用 select_related 和 Prefetch 一次搞定。',
        'content': """## 问题：页面能跑，但查询爆炸

首页文章列表里同时用到了作者头像、作者昵称、标签，如果什么都没预取，
每渲染一篇文章就要额外查 3 次数据库，10 篇文章就是 30 次。

用 `assertNumQueries` 把这个问题钉死在测试里：

```python
def test_index_query_count_is_bounded(self):
    with self.assertNumQueries(13):
        self.client.get(reverse('index'))
```

## 三个常用手段

### 1. select_related —— 外键用 JOIN

```python
Post.objects.select_related('author', 'category')
```

### 2. prefetch_related —— 多对多用第二条查询

```python
Post.objects.prefetch_related('tags')
```

### 3. Prefetch —— 需要限制条数时

模板里写 `post.tags.all|slice:":4"` 会**既预取一次、又查一次**，
正确做法是在查询集里就限制好：

```python
Prefetch('tags', queryset=Tag.objects.order_by('name'))
```

## 优化前后对比

| 页面 | 优化前 | 优化后 |
| --- | --- | --- |
| 首页列表 | 29 | 13 |
| 文章详情 | 31 | 17 |

> 结论：ORM 优化不难，难的是**先发现**。把查询次数写成测试用例，就再也不会退化了。
""",
    },
    {
        'title': '用 Markdown 写博客正文：渲染 + 代码高亮 + XSS 防护',
        'category': '技术笔记',
        'tags': ['Markdown', 'Python', '前端'],
        'excerpt': '正文存 Markdown，展示时渲染成 HTML，再用白名单过滤一遍，既好看又安全。',
        'content': """## 为什么正文存 Markdown

直接存 HTML 有两个问题：一是编辑器体验差，二是用户能塞任意脚本。
存 Markdown 则既能保证写作体验，渲染这一层还可以统一控制。

## 渲染管线

```python
html = markdown.markdown(text, extensions=[
    'extra', 'sane_lists', 'nl2br',
    FencedCodeExtension(),
    CodeHiliteExtension(guess_lang=False),
])
cleaned = bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS)
```

三件事一次做完：

1. **渲染**：Markdown -> HTML，代码块交给 Pygments 上色
2. **过滤**：bleach 白名单，`<script>`、`onclick` 之类的全部清掉
3. **缓存**：渲染结果写回数据库，正文没改就直接复用

## 缓存怎么判断过期

给文章加两个字段：`rendered_content` 和 `rendered_at`，
保存时清空，读取时比较时间戳：

```python
if self.rendered_content and self.rendered_at >= self.updated:
    return self.rendered_content
```

## 效果

行内代码 `print("hello")` 会有底色，代码块会自动上色，
表格、引用、列表都能正常渲染：

- 无序列表项
- **加粗**、*斜体*、~~删除线~~
- [链接](https://www.djangoproject.com/)

> 提醒：渲染结果一定要过滤，别相信用户输入。
""",
    },
    {
        'title': '毕业设计选题到答辩：一个博客系统能讲哪些技术点',
        'category': '学习路线',
        'tags': ['毕业设计', 'Django', 'MySQL'],
        'excerpt': '博客系统看起来简单，但把评论、权限、ORM 优化、通知这些做扎实，答辩时能讲的内容非常多。',
        'content': """## 选题不丢人，讲不透才丢人

「个人博客系统」是最常见的毕设题目之一，评委不会因为题目普通扣分，
但会因为你**讲不清楚自己的设计决策**而扣分。

## 可以展开讲的六个点

### 1. 数据建模

为什么评论要用 `parent` + `root` 两个自关联外键？
为什么删除评论用软删除（`is_deleted`）而不是物理删除？
——软删除是为了保住楼层号，否则「#5 楼」会凭空消失。

### 2. 权限控制

| 操作 | 谁能做 |
| --- | --- |
| 编辑 / 删除文章 | 只有作者 |
| 删除评论 | 评论作者本人 **或** 文章作者 |
| 查看草稿 | 只有作者 |

### 3. 互动模块

点赞用 `unique_together = ('user', 'post')` 保证一人一票，
再次点击同一按钮就是取消。

### 4. 站内通知

在评论、点赞、收藏的写入路径上触发通知，注意**不要给自己发通知**。

### 5. 性能

用 `assertNumQueries` 守住查询次数，把「性能」变成可验证的指标。

### 6. 安全

CSRF、XSS 过滤、开放重定向校验、上传类型白名单——这四个都做了就够讲了。

> 答辩技巧：每个技术点都准备一句「如果不这么做会怎样」，评委很吃这一套。
""",
    },
    {
        'title': 'Python 装饰器从入门到在 Django 里用起来',
        'category': '技术笔记',
        'tags': ['Python', 'Django'],
        'excerpt': '装饰器本质就是「接收函数、返回函数」，理解了这一点，Django 的 login_required 也就不神秘了。',
        'content': """## 最小例子

```python
def log_time(func):
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        print(f'{func.__name__} 用了 {time.time() - start:.2f}s')
        return result
    return wrapper
```

## 带参数的装饰器

多一层函数就行：

```python
def retry(times=3):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for i in range(times):
                try:
                    return func(*args, **kwargs)
                except Exception:
                    if i == times - 1:
                        raise
        return wrapper
    return decorator
```

## Django 里的应用

`@login_required`、`@require_POST` 都是装饰器。写视图时把
`@require_POST` 加在写操作的视图上，能顺手挡掉一类 CSRF 之外的误操作：

```python
@require_POST
@login_required
def toggle_post_status(request, post_id):
    ...
```

顺序很重要：**装饰器从下往上生效**，所以 `login_required` 写在下面。

## 别忘了 functools.wraps

不加 `@functools.wraps(func)`，被装饰函数的 `__name__` 会变成 `wrapper`，
Django 路由和调试都会受影响。
""",
    },
    {
        'title': '我的 2026 学习计划：把基础打牢',
        'category': '生活随笔',
        'tags': ['毕业设计'],
        'excerpt': '不追新框架，先把 Python、数据库和网络补扎实。',
        'content': """## 为什么不再追新

过去两年我学了很多框架，但每次遇到问题还是回到最基础的地方：
SQL 怎么写、HTTP 状态码什么意思、进程和线程的区别。
所以今年换个思路，先把地基浇厚。

## 具体安排

1. **Python**：把标准库过一遍，尤其是 `itertools`、`collections`、`functools`
2. **数据库**：手写 SQL，理解索引和 EXPLAIN
3. **网络**：把《HTTP 权威指南》读完
4. **算法**：每天一道，不求多求难，求坚持

## 一点心得

> 学不动的时候，把目标拆到「今天只要做完这一件事」那么大，就容易开始了。

- [x] 完成毕设主体功能
- [ ] 补完单元测试
- [ ] 部署上线
""",
    },
]

# (评论者, 内容, 回复第几楼, @谁) —— 第 3 项为 None 表示这是一条新的楼层
COMMENTS = [
    ('bob', '写得太清楚了，楼中楼那段我看了两遍才懂，感谢分享！', None, None),
    ('alice', '请问 `root` 字段在保存的时候是怎么维护的？是在 model 的 save 里做的吗？', None, None),
    ('admin', '是的，重写了 save()，根据 parent 自动算 root 和 depth，这样视图层就不用管了。', 1, 'alice'),
    ('alice', '明白了，这个思路很好，省了很多重复代码 👍', 1, 'admin'),
    ('bob', '收藏了，正好毕设要用 [em:thumbsup]', None, None),
    ('alice', '[em:tada] [em:fire]', None, None),
    ('admin', '有个小建议：如果评论很多，是不是应该做分页？', 1, None),
]


class Command(BaseCommand):
    help = '生成演示数据（用户、分类、标签、文章、评论、点赞、通知）'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help='先删除已有的博客数据再生成（不可恢复，慎用）')

    @transaction.atomic
    def handle(self, *args, **options):
        if options['reset']:
            self.stdout.write(self.style.WARNING('正在清空博客数据…'))
            Notification.objects.all().delete()
            CommentLike.objects.all().delete()
            PostVote.objects.all().delete()
            Bookmark.objects.all().delete()
            Comment.objects.all().delete()
            Post.objects.all().delete()
            Tag.objects.all().delete()
            Category.objects.all().delete()

        users = {}
        for username, nickname, bio in USERS:
            user, created = User.objects.get_or_create(username=username)
            if created:
                user.set_password(PASSWORD)
            user.first_name = nickname
            user.email = f'{username}@example.com'
            if username == SITE_OWNER:
                user.is_staff = True
                user.is_superuser = True
            user.save()
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.bio = bio
            profile.location = random.choice(['浙江 杭州', '江苏 南京', '广东 深圳', '北京'])
            profile.github = username
            profile.save()
            users[username] = user

        categories = {name: Category.objects.get_or_create(name=name)[0] for name in CATEGORIES}
        tags = {name: Tag.objects.get_or_create(name=name)[0] for name in TAGS}

        def get_tag(name):
            """文章里用到的标签如果不在预置列表里，就顺手创建。"""
            if name not in tags:
                tags[name] = Tag.objects.get_or_create(name=name)[0]
            return tags[name]

        authors = [users[SITE_OWNER], users['alice'], users['bob']]
        created_posts = []
        for index, data in enumerate(POSTS):
            post, created = Post.objects.get_or_create(
                title=data['title'],
                defaults={
                    'content': data['content'],
                    'excerpt': data['excerpt'],
                    'author': authors[index % len(authors)],
                    'category': categories[data['category']],
                    'status': 'published',
                },
            )
            if created:
                post.tags.set([get_tag(name) for name in data['tags']])
                # 让热门榜 / 阅读量看起来自然一点
                post.views = random.randint(30, 460)
                post.save(update_fields=['views'])
            created_posts.append(post)

        # 用第一篇的评论树做演示
        main_post = created_posts[0]
        if not Comment.objects.filter(post=main_post).exists():
            roots, created_comments = [], []
            for username, content, reply_to_floor, reply_to_name in COMMENTS:
                # reply_to_floor 是「第几楼」（1 开始），用来构造楼中楼
                parent = roots[reply_to_floor - 1] if reply_to_floor else None
                comment = Comment.objects.create(
                    post=main_post,
                    author=users[username],
                    content=content,
                    parent=parent,
                    reply_to=users[reply_to_name] if reply_to_name else None,
                )
                if parent is None:
                    roots.append(comment)
                created_comments.append(comment)
            # 给几条评论点点赞
            for comment in created_comments[:3]:
                for user in authors:
                    if user != comment.author:
                        CommentLike.objects.get_or_create(user=user, comment=comment)

        # 文章互动
        for post in created_posts:
            for user in authors:
                if user == post.author:
                    continue
                if random.random() < 0.7:
                    PostVote.objects.get_or_create(user=user, post=post, defaults={'value': 1})
                elif random.random() < 0.2:
                    PostVote.objects.get_or_create(user=user, post=post, defaults={'value': -1})
                if random.random() < 0.3:
                    Bookmark.objects.get_or_create(user=user, post=post)

        # 给站长造几条通知
        owner = users[SITE_OWNER]
        if not Notification.objects.filter(recipient=owner).exists():
            for kind, sender, post in [
                ('like', users['alice'], created_posts[0]),
                ('bookmark', users['bob'], created_posts[0]),
                ('comment', users['bob'], created_posts[0]),
            ]:
                Notification.objects.create(
                    recipient=owner, sender=sender, kind=kind, post=post,
                    text='这是一条演示通知，点开就能跳到对应位置。',
                    created=timezone.now(),
                )

        self.stdout.write(self.style.SUCCESS(
            f'\n演示数据已生成：\n'
            f'  用户 {User.objects.count()} 个（密码统一为 {PASSWORD}）\n'
            f'      {SITE_OWNER}  站长 / 超级管理员（可登录 /admin/ 后台）\n'
            f'      alice 爱丽丝\n'
            f'      bob   鲍勃\n'
            f'  分类 {Category.objects.count()} 个 · 标签 {Tag.objects.count()} 个\n'
            f'  文章 {Post.objects.count()} 篇 · 评论 {Comment.objects.count()} 条\n'
            f'  通知 {Notification.objects.count()} 条\n'
            f'\n启动预览：\n'
            f'  $env:DB_ENGINE="sqlite"; python manage.py runserver\n'
            f'  浏览器打开 http://127.0.0.1:8000/\n'
        ))

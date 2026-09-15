"""DjangoBlog 数据模型

模块划分：
    Category        分类
    Tag             标签
    Post            博文
    UserProfile     用户扩展资料（头像 / 简介 / 社交链接）
    Comment         评论（支持楼中楼多级嵌套、点赞、表情、图片）
    PostVote        文章点赞 / 点踩
    Bookmark        文章收藏
    CommentLike     评论点赞
    Notification    站内通知
"""
import hashlib
import re

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from django.utils.text import slugify


# ---------------------------------------------------------------------------
# 分类 & 标签
# ---------------------------------------------------------------------------
class Category(models.Model):
    """分类表（一篇文章只属于一个分类）"""
    name = models.CharField(max_length=50, unique=True, verbose_name='分类名称')
    created = models.DateTimeField(default=timezone.now, verbose_name='创建时间')

    class Meta:
        verbose_name = '分类'
        verbose_name_plural = '分类'
        ordering = ['-created']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return f"{reverse('index')}?category={self.pk}"

    @property
    def post_count(self):
        return self.posts.filter(status='published').count()


class Tag(models.Model):
    """标签表（一篇文章可以有多个标签）"""
    name = models.CharField(max_length=40, unique=True, verbose_name='标签名')
    slug = models.SlugField(max_length=60, unique=True, blank=True, verbose_name='URL 标识')
    created = models.DateTimeField(default=timezone.now, verbose_name='创建时间')

    class Meta:
        verbose_name = '标签'
        verbose_name_plural = '标签'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            # 中文标签 slugify 后可能为空，此时退化为 md5 前缀，保证唯一且可用于 URL
            base = slugify(self.name)[:50]
            if not base:
                base = 'tag-' + hashlib.md5(self.name.encode('utf-8')).hexdigest()[:10]
            slug, index = base, 1
            while Tag.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                index += 1
                slug = f'{base}-{index}'
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('tag_detail', kwargs={'slug': self.slug})

    @property
    def post_count(self):
        return self.posts.filter(status='published').count()


# ---------------------------------------------------------------------------
# 博文
# ---------------------------------------------------------------------------
class PostQuerySet(models.QuerySet):
    """博文查询集：把常用的统计聚合收敛到这里，避免视图里写重复的 annotate。"""

    def published(self):
        return self.filter(status='published')

    def with_counts(self):
        """附带点赞数、点踩数、评论数、收藏数，用于列表页一次性取回统计信息。

        注意：注解名不能叫 like_count，因为它会覆盖 Post.like_count 这个属性，
        导致模板里调用 post.like_count 时报错。统一用 *_annotated 命名。
        """
        return self.annotate(
            like_count_annotated=Count('votes', filter=Q(votes__value=1), distinct=True),
            dislike_count_annotated=Count('votes', filter=Q(votes__value=-1), distinct=True),
            comment_count_annotated=Count('comments', filter=Q(comments__is_deleted=False),
                                          distinct=True),
            bookmark_count_annotated=Count('bookmarks', distinct=True),
        )


class Post(models.Model):
    """博文表"""
    STATUS_CHOICES = (
        ('draft', '草稿'),
        ('published', '发布'),
    )

    title = models.CharField(max_length=200, verbose_name='标题')
    content = models.TextField(verbose_name='内容（支持 Markdown）')
    excerpt = models.CharField(max_length=300, blank=True, verbose_name='摘要')
    cover = models.ImageField(upload_to='covers/%Y/%m/', blank=True, null=True, verbose_name='封面图')

    created = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='posts', verbose_name='作者')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='posts', verbose_name='分类')
    tags = models.ManyToManyField(Tag, blank=True, related_name='posts', verbose_name='标签')

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft', verbose_name='状态')

    # 统计字段
    views = models.PositiveIntegerField(default=0, verbose_name='阅读量')

    # Markdown 渲染缓存（渲染结果与 updated 比较，过期自动重算）
    rendered_content = models.TextField(blank=True, editable=False, verbose_name='渲染后正文')
    rendered_at = models.DateTimeField(null=True, blank=True, editable=False, verbose_name='渲染时间')

    objects = PostQuerySet.as_manager()

    class Meta:
        verbose_name = '博文'
        verbose_name_plural = '博文'
        ordering = ['-created']
        indexes = [
            models.Index(fields=['-created']),
            models.Index(fields=['status', '-created']),
            models.Index(fields=['-views']),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('post_detail', kwargs={'post_id': self.pk})

    # -- Markdown 渲染 ------------------------------------------------------
    def render_content(self):
        """把 Markdown 正文渲染成安全的 HTML 字符串。"""
        from .markdown_utils import render_markdown
        return render_markdown(self.content)

    @property
    def html_content(self):
        """带缓存的正文 HTML；正文改动后自动重新渲染。"""
        if self.rendered_content and self.rendered_at and self.rendered_at >= self.updated:
            return self.rendered_content
        html = self.render_content()
        Post.objects.filter(pk=self.pk).update(
            rendered_content=html, rendered_at=timezone.now()
        )
        self.rendered_content, self.rendered_at = html, timezone.now()
        return html

    # -- 摘要 --------------------------------------------------------------
    @property
    def display_excerpt(self):
        """优先用作者填写的摘要，否则从正文自动截取（去掉 Markdown 标记）。"""
        if self.excerpt.strip():
            return self.excerpt.strip()
        text = re.sub(r'```.*?```', ' ', self.content, flags=re.S)      # 代码块
        text = re.sub(r'!?\[[^\]]*\]\([^)]*\)', ' ', text)               # 图片/链接
        text = re.sub(r'[#>*`_~\-]+', ' ', text)                         # Markdown 标记
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:150] + ('…' if len(text) > 150 else '')

    @property
    def reading_minutes(self):
        """预估阅读时长（按中文 400 字/分钟估算）。"""
        return max(1, round(len(self.content) / 400))

    # -- 当前用户与文章的互动状态 ------------------------------------------
    def user_vote(self, user):
        """返回 1（赞）/ -1（踩）/ 0（未操作）。"""
        if not user or not user.is_authenticated:
            return 0
        vote = self.votes.filter(user=user).first()
        return vote.value if vote else 0

    def is_bookmarked_by(self, user):
        if not user or not user.is_authenticated:
            return False
        return self.bookmarks.filter(user=user).exists()

    @property
    def like_count(self):
        """点赞数；若查询集已 annotate 则直接复用，避免 N+1 查询。"""
        annotated = getattr(self, 'like_count_annotated', None)
        if annotated is not None:
            return annotated
        return self.votes.filter(value=1).count()

    @property
    def dislike_count(self):
        annotated = getattr(self, 'dislike_count_annotated', None)
        if annotated is not None:
            return annotated
        return self.votes.filter(value=-1).count()

    @property
    def bookmark_count(self):
        annotated = getattr(self, 'bookmark_count_annotated', None)
        if annotated is not None:
            return annotated
        return self.bookmarks.count()

    @property
    def comment_count(self):
        annotated = getattr(self, 'comment_count_annotated', None)
        if annotated is not None:
            return annotated
        return self.comments.filter(is_deleted=False).count()

    def related_posts(self, limit=5):
        """相关文章：优先同标签，其次同分类，最后最新文章补齐。"""
        tag_ids = list(self.tags.values_list('id', flat=True))
        qs = Post.objects.published().exclude(pk=self.pk)
        if tag_ids:
            related = list(qs.filter(tags__id__in=tag_ids).distinct()[:limit])
        else:
            related = []
        if len(related) < limit and self.category_id:
            exclude_ids = [p.pk for p in related] + [self.pk]
            related += list(qs.filter(category_id=self.category_id)
                            .exclude(pk__in=exclude_ids)[:limit - len(related)])
        if len(related) < limit:
            exclude_ids = [p.pk for p in related] + [self.pk]
            related += list(qs.exclude(pk__in=exclude_ids)[:limit - len(related)])
        return related


# ---------------------------------------------------------------------------
# 用户扩展资料
# ---------------------------------------------------------------------------
class UserProfile(models.Model):
    """与 Django 内置 User 一对一的扩展资料。"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile', verbose_name='用户')
    avatar = models.ImageField(upload_to='avatars/%Y/%m/', blank=True, null=True, verbose_name='头像')
    avatar_url = models.URLField(max_length=300, blank=True, verbose_name='头像外链')
    bio = models.CharField(max_length=200, blank=True, verbose_name='个性签名')
    website = models.URLField(max_length=200, blank=True, verbose_name='个人网站')
    location = models.CharField(max_length=60, blank=True, verbose_name='所在地')
    github = models.CharField(max_length=100, blank=True, verbose_name='GitHub 用户名')
    created = models.DateTimeField(default=timezone.now, verbose_name='创建时间')

    class Meta:
        verbose_name = '用户资料'
        verbose_name_plural = '用户资料'

    def __str__(self):
        return f'{self.user.username} 的资料'

    @property
    def display_avatar(self):
        """头像地址：上传的图片 > 外链 > 自动生成的首字母头像。"""
        if self.avatar:
            return self.avatar.url
        if self.avatar_url:
            return self.avatar_url
        return ''

    @property
    def avatar_letter(self):
        name = self.user.username or '?'
        return name[0].upper()

    @property
    def avatar_color(self):
        """由用户名派生的稳定配色，保证同一个人每次颜色一致。"""
        palette = ['#6b8cff', '#8b5cf6', '#ec4899', '#f59e0b',
                   '#10b981', '#06b6d4', '#ef4444', '#6366f1']
        digest = hashlib.md5((self.user.username or '?').encode('utf-8')).hexdigest()
        return palette[int(digest[:8], 16) % len(palette)]

    def social_links(self):
        links = []
        if self.website:
            links.append(('个人网站', self.website, '🌐'))
        if self.github:
            links.append(('GitHub', f'https://github.com/{self.github}', '🐙'))
        return links


def get_profile(user):
    """安全获取用户资料，老用户没有 Profile 时自动补建。"""
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


# ---------------------------------------------------------------------------
# 互动：点赞 / 点踩 / 收藏
# ---------------------------------------------------------------------------
class PostVote(models.Model):
    """文章点赞 / 点踩（同一用户对同一文章只有一条记录）"""
    VOTE_CHOICES = ((1, '赞'), (-1, '踩'))

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='post_votes', verbose_name='用户')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='votes', verbose_name='博文')
    value = models.SmallIntegerField(choices=VOTE_CHOICES, default=1, verbose_name='态度')
    created = models.DateTimeField(default=timezone.now, verbose_name='时间')

    class Meta:
        verbose_name = '文章投票'
        verbose_name_plural = '文章投票'
        unique_together = ('user', 'post')
        indexes = [models.Index(fields=['post', 'value'])]

    def __str__(self):
        return f'{self.user.username} {"赞" if self.value == 1 else "踩"}了《{self.post.title}》'


class Bookmark(models.Model):
    """文章收藏"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookmarks', verbose_name='用户')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='bookmarks', verbose_name='博文')
    created = models.DateTimeField(default=timezone.now, verbose_name='收藏时间')

    class Meta:
        verbose_name = '收藏'
        verbose_name_plural = '收藏'
        unique_together = ('user', 'post')
        ordering = ['-created']

    def __str__(self):
        return f'{self.user.username} 收藏了《{self.post.title}》'


# ---------------------------------------------------------------------------
# 评论系统
# ---------------------------------------------------------------------------
class Comment(models.Model):
    """评论表：支持楼中楼（parent 自关联）、点赞、表情、配图。"""

    MAX_DEPTH = 2          # 0=一级评论，1=回复，2=楼中楼里的回复（再深也归到 2，前端扁平展示）

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments', verbose_name='所属博文')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments', verbose_name='评论者')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True,
                               related_name='replies', verbose_name='父评论')
    root = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True,
                             related_name='thread_comments', verbose_name='所属楼层')

    content = models.TextField(verbose_name='评论内容')
    image = models.ImageField(upload_to='comments/%Y/%m/', blank=True, null=True, verbose_name='评论配图')

    reply_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='mentioned_in_comments', verbose_name='回复给')

    likes = models.ManyToManyField(User, through='CommentLike', related_name='liked_comments',
                                   verbose_name='点赞用户')

    depth = models.PositiveSmallIntegerField(default=0, verbose_name='层级')
    is_deleted = models.BooleanField(default=False, verbose_name='已删除')  # 保留占位，楼层不会塌陷

    created = models.DateTimeField(default=timezone.now, verbose_name='评论时间')
    updated = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '评论'
        verbose_name_plural = '评论'
        ordering = ['created']
        indexes = [
            models.Index(fields=['post', 'root', 'created']),
            models.Index(fields=['post', 'parent', 'created']),
        ]

    def __str__(self):
        return f'{self.author.username} 评论了 {self.post.title}'

    # -- 结构 --------------------------------------------------------------
    def save(self, *args, **kwargs):
        # 自动维护 root / depth，保证楼中楼结构始终自洽
        if self.parent_id:
            self.root_id = self.parent.root_id or self.parent_id
            self.depth = min(self.parent.depth + 1, self.MAX_DEPTH)
        else:
            self.root_id = None
            self.depth = 0
        super().save(*args, **kwargs)

    @property
    def like_count(self):
        return self.likes.count()

    def is_liked_by(self, user):
        if not user or not user.is_authenticated:
            return False
        return self.likes.filter(pk=user.pk).exists()

    @property
    def display_content(self):
        """评论内容：转义 HTML + 把 [em:xx] 表情码换成表情图片。"""
        from .markdown_utils import EMOTICONS
        text = escape(self.content)
        for code, (emoji, _name) in EMOTICONS.items():
            token = escape(f'[em:{code}]')
            text = text.replace(
                token,
                f'<img class="emoticon" src="{settings.STATIC_URL}img/emoticons/{code}.svg" '
                f'alt="{escape(emoji)}" title="{escape(emoji)}">'
            )
        return text.replace('\n', '<br>')

    @property
    def is_reply(self):
        return self.parent_id is not None

    def reply_target_name(self):
        """@ 谁：优先显示被回复的人，没有则显示父评论作者。"""
        target = self.reply_to or (self.parent.author if self.parent_id else None)
        return target.username if target else ''


class CommentLike(models.Model):
    """评论点赞"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comment_likes', verbose_name='用户')
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='like_records', verbose_name='评论')
    created = models.DateTimeField(default=timezone.now, verbose_name='时间')

    class Meta:
        verbose_name = '评论点赞'
        verbose_name_plural = '评论点赞'
        unique_together = ('user', 'comment')

    def __str__(self):
        return f'{self.user.username} 赞了评论 #{self.comment_id}'


# ---------------------------------------------------------------------------
# 站内通知
# ---------------------------------------------------------------------------
class Notification(models.Model):
    """站内通知：评论 / 回复 / 点赞 / 收藏 / 系统消息"""
    TYPE_CHOICES = (
        ('comment', '评论了我的文章'),
        ('reply', '回复了我的评论'),
        ('like', '点赞了我的文章'),
        ('bookmark', '收藏了我的文章'),
        ('comment_like', '点赞了我的评论'),
        ('system', '系统通知'),
    )

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications',
                                  verbose_name='接收者')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_notifications',
                               null=True, blank=True, verbose_name='触发者')
    kind = models.CharField(max_length=20, choices=TYPE_CHOICES, default='system', verbose_name='类型')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, null=True, blank=True,
                             related_name='notifications', verbose_name='相关博文')
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, null=True, blank=True,
                                related_name='notifications', verbose_name='相关评论')
    text = models.CharField(max_length=200, blank=True, verbose_name='附加说明')
    is_read = models.BooleanField(default=False, verbose_name='已读')
    created = models.DateTimeField(default=timezone.now, verbose_name='时间')

    class Meta:
        verbose_name = '站内通知'
        verbose_name_plural = '站内通知'
        ordering = ['-created']
        indexes = [models.Index(fields=['recipient', 'is_read', '-created'])]

    def __str__(self):
        return f'[{self.get_kind_display()}] → {self.recipient.username}'

    @property
    def icon(self):
        return {
            'comment': '💬', 'reply': '↩️', 'like': '👍',
            'bookmark': '⭐', 'comment_like': '❤️', 'system': '📢',
        }.get(self.kind, '🔔')

    @property
    def summary(self):
        sender = self.sender.username if self.sender else '系统'
        post_title = self.post.title if self.post else ''
        mapping = {
            'comment': f'{sender} 评论了你的文章《{post_title}》',
            'reply': f'{sender} 回复了你的评论',
            'like': f'{sender} 点赞了你的文章《{post_title}》',
            'bookmark': f'{sender} 收藏了你的文章《{post_title}》',
            'comment_like': f'{sender} 点赞了你的评论',
            'system': self.text or '系统通知',
        }
        return mapping.get(self.kind, self.text)

    def get_absolute_url(self):
        if self.comment_id and self.comment:
            return f'{reverse("post_detail", kwargs={"post_id": self.comment.post_id})}#comment-{self.comment_id}'
        if self.post_id:
            return reverse('post_detail', kwargs={'post_id': self.post_id})
        return reverse('notifications')

    @staticmethod
    def push(recipient, kind, sender=None, post=None, comment=None, text=''):
        """创建通知；不给自己发通知。"""
        if not recipient or (sender and recipient.pk == sender.pk):
            return None
        return Notification.objects.create(
            recipient=recipient, kind=kind, sender=sender,
            post=post, comment=comment, text=text,
        )


# 信号：新建用户时自动创建资料
from django.db.models.signals import post_save          # noqa: E402
from django.dispatch import receiver                     # noqa: E402


@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)

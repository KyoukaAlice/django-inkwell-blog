"""DjangoBlog 视图层

包含：首页 / 搜索 / 文章详情 / B 站风格评论系统 / 点赞点踩收藏 /
标签归档 / 用户主页 / 站内通知 / 个人中心。
"""
from dataclasses import dataclass, field
from math import ceil

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import models
from django.db.models import Count, F, Prefetch, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import CommentForm, PostForm, ProfileForm, RegisterForm
from .markdown_utils import EMOTICONS, is_emoji_only, plain_text
from .models import (Bookmark, Category, Comment, CommentLike, Notification, Post,
                     PostVote, Tag, UserProfile, get_profile)

SORT_OPTIONS = {
    'new': ('最新发布', '-created'),
    'hot': ('最受欢迎', '-like_count_annotated'),
    'views': ('阅读最多', '-views'),
    'discussed': ('评论最多', '-comment_count_annotated'),
}

ALLOWED_IMAGE_EXT = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'}
MAX_COMMENT_IMAGE_SIZE = 5 * 1024 * 1024      # 5MB

# 列表页一次性把作者资料和标签取回来，避免 N+1 查询
TAGS_PREVIEW = 4


def _post_list_queryset():
    """列表页专用查询集：统计注解 + 作者资料 + 标签预取。"""
    return (
        Post.objects.with_counts()
        .select_related('author', 'category')
        .prefetch_related(
            Prefetch('author__profile', queryset=UserProfile.objects.select_related('user')),
            Prefetch('tags', queryset=Tag.objects.order_by('name')),
        )
    )


def _published_posts():
    return _post_list_queryset().published()


# ---------------------------------------------------------------------------
# 通用小工具
# ---------------------------------------------------------------------------
def _validate_image(uploaded):
    """校验上传图片的扩展名与大小，返回错误信息或 None。"""
    if not uploaded:
        return None
    ext = uploaded.name.rsplit('.', 1)[-1].lower() if '.' in uploaded.name else ''
    if ext not in ALLOWED_IMAGE_EXT:
        return '只支持 jpg / png / gif / webp / bmp 格式的图片。'
    if uploaded.size > MAX_COMMENT_IMAGE_SIZE:
        return '图片太大了，请压缩到 5MB 以内。'
    return None


def _paginate(request, queryset, per_page):
    paginator = Paginator(queryset, per_page)
    number = request.GET.get('page') or 1
    try:
        return paginator.page(number)
    except PageNotAnInteger:
        return paginator.page(1)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


# ---------------------------------------------------------------------------
# 认证
# ---------------------------------------------------------------------------
def register(request):
    if request.user.is_authenticated:
        return redirect('index')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'欢迎加入，{user.username}！你的账号已创建成功 🎉')
            return redirect('index')
        messages.error(request, '注册信息有误，请检查下方提示。')
    else:
        form = RegisterForm()
    return render(request, 'blog/register.html', {'form': form})


def user_login(request):
    if request.user.is_authenticated:
        return redirect('index')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if not user.is_active:
                messages.error(request, '该账号已被禁用。')
            else:
                login(request, user)
                get_profile(user)          # 老用户自动补建资料
                messages.success(request, f'欢迎回来，{user.username}！')
                next_url = request.POST.get('next') or request.GET.get('next') or ''
                if next_url and url_has_allowed_host_and_scheme(
                    next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
                ):
                    return redirect(next_url)
                return redirect('index')
        else:
            messages.error(request, '用户名或密码不正确。')
    return render(request, 'blog/login.html', {'next': request.GET.get('next', '')})


def user_logout(request):
    """退出登录：Django 5 的 LogoutView 只接受 POST，这里自己实现更直观。"""
    logout(request)
    messages.success(request, '你已安全退出登录。')
    return redirect('login')


# ---------------------------------------------------------------------------
# 首页 / 搜索
# ---------------------------------------------------------------------------
def _filtered_posts(request):
    """根据查询参数筛选文章，供首页与搜索页复用。"""
    posts = _published_posts()

    category_id = request.GET.get('category', '').strip()
    if category_id.isdigit():
        posts = posts.filter(category_id=int(category_id))

    tag_slug = request.GET.get('tag', '').strip()
    if tag_slug:
        posts = posts.filter(tags__slug=tag_slug)

    keyword = request.GET.get('keyword', '').strip()
    if keyword:
        posts = posts.filter(
            Q(title__icontains=keyword)
            | Q(content__icontains=keyword)
            | Q(excerpt__icontains=keyword)
            | Q(tags__name__icontains=keyword)
            | Q(author__username__icontains=keyword)
        ).distinct()

    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    if start_date:
        posts = posts.filter(created__date__gte=start_date)
    if end_date:
        posts = posts.filter(created__date__lte=end_date)

    author_id = request.GET.get('author', '').strip()
    if author_id.isdigit():
        posts = posts.filter(author_id=int(author_id))

    sort = request.GET.get('sort', 'new')
    posts = posts.order_by(SORT_OPTIONS.get(sort, SORT_OPTIONS['new'])[1], '-id')
    return posts, sort, keyword


def index(request):
    posts, sort, keyword = _filtered_posts(request)
    page = _paginate(request, posts, settings.POSTS_PER_PAGE)

    # 侧边栏统计
    stats = {
        'posts': Post.objects.published().count(),
        'comments': Comment.objects.filter(is_deleted=False).count(),
        'views': Post.objects.published().aggregate(total=models.Sum('views'))['total'] or 0,
        'tags': Tag.objects.count(),
    }
    context = {
        'posts': page,
        'page_obj': page,
        'sort': sort,
        'sort_options': SORT_OPTIONS,
        'keyword': keyword,
        'categories': Category.objects.all(),
        'current_category': request.GET.get('category', ''),
        'current_tag': request.GET.get('tag', ''),
        'start_date': request.GET.get('start_date', ''),
        'end_date': request.GET.get('end_date', ''),
        'stats': stats,
    }
    return render(request, 'blog/index.html', context)


def search(request):
    """独立的搜索结果页：同时搜文章 / 用户 / 标签。"""
    keyword = request.GET.get('keyword', '').strip()
    posts, sort, _ = _filtered_posts(request)
    page = _paginate(request, posts, settings.POSTS_PER_PAGE)

    authors, tags = [], []
    if keyword:
        authors = list(
            User.objects.filter(Q(username__icontains=keyword) | Q(first_name__icontains=keyword))
            .annotate(published_count=Count('posts', filter=Q(posts__status='published')))
            .order_by('-published_count')[:6]
        )
        tags = list(Tag.objects.filter(name__icontains=keyword).annotate(
            published_count=Count('posts', filter=Q(posts__status='published'))
        ).order_by('-published_count')[:12])

    return render(request, 'blog/search.html', {
        'posts': page,
        'page_obj': page,
        'keyword': keyword,
        'sort': sort,
        'sort_options': SORT_OPTIONS,
        'result_count': posts.count(),
        'authors': authors,
        'tags': tags,
        'categories': Category.objects.all(),
    })


# ---------------------------------------------------------------------------
# 文章详情
# ---------------------------------------------------------------------------
def post_detail(request, post_id):
    post = get_object_or_404(_post_list_queryset(), id=post_id)
    if post.status != 'published' and request.user != post.author:
        raise Http404('文章不存在或未发布')

    # 阅读量 +1（作者本人访问不计入）
    if request.user != post.author:
        Post.objects.filter(pk=post.pk).update(views=F('views') + 1)
        post.views += 1

    comment_page = _load_comment_page(request, post)
    context = {
        'post': post,
        'form': CommentForm(user=request.user, post=post),
        'user_vote': post.user_vote(request.user),
        'is_bookmarked': post.is_bookmarked_by(request.user),
        'related_posts': post.related_posts(limit=5),
        'emoticons': EMOTICONS,
        'comment_sort': comment_page['sort'],
        **comment_page,
    }
    return render(request, 'blog/post_detail.html', context)


@dataclass
class CommentNode:
    """渲染评论用的扁平结构（含作者、互动数据）。"""
    id: int
    author_name: str
    author_id: int
    avatar: str
    avatar_letter: str
    avatar_color: str
    content_html: str
    raw_content: str
    created: object
    likes: int
    liked: bool
    is_emoji_only: bool
    is_deleted: bool
    is_author: bool
    is_post_author: bool
    image_url: str = ''
    reply_to: str = ''
    floor: int = 0
    is_reply: bool = False
    like_users: list = field(default_factory=list)


def _build_avatar(user, profile_map):
    """头像：上传的图片 > 外链 > 首字母色块（永远不会是破图）。"""
    profile = profile_map.get(user.id)
    if profile and profile.display_avatar:
        return profile.display_avatar, profile.avatar_letter, profile.avatar_color
    letter = (user.username or '?')[0].upper()
    return '', letter, UserProfile(user=user).avatar_color


def _to_node(comment, user, profile_map, post_author_id, liked_ids, floor=0):
    """把一条 Comment 转成模板友好的 CommentNode。"""
    avatar, letter, color = _build_avatar(comment.author, profile_map)
    # likes 已通过 Prefetch 预取，这里不会再打数据库
    like_users = [u.username for u in comment.likes.all()[:12]]
    return CommentNode(
        id=comment.id,
        author_name=comment.author.username,
        author_id=comment.author_id,
        avatar=avatar,
        avatar_letter=letter,
        avatar_color=color,
        content_html='该评论已删除' if comment.is_deleted else comment.display_content,
        raw_content=comment.content,
        created=comment.created,
        likes=comment.like_total,
        liked=comment.id in liked_ids,
        is_emoji_only=is_emoji_only(comment.content) and not comment.is_deleted,
        is_deleted=comment.is_deleted,
        is_author=bool(user.is_authenticated and comment.author_id == user.id),
        is_post_author=comment.author_id == post_author_id,
        image_url=comment.image.url if comment.image else '',
        reply_to=comment.reply_target_name() if comment.parent_id else '',
        floor=floor,
        is_reply=comment.parent_id is not None,
        like_users=like_users,
    )


def _render_comment_list_html(request, post, data):
    """渲染评论区局部模板，返回 HTML 字符串（AJAX 与整页提交共用）。"""
    return render(request, 'blog/partials/comment_list.html', {
        'post': post, 'emoticons': EMOTICONS, 'is_ajax': True, **data,
    }).content.decode('utf-8')


def _comment_payload(request, post):
    """统一的评论区响应：AJAX 返回 JSON（含 HTML 片段），否则 302 回文章页。"""
    data = _load_comment_page(request, post)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'ok': True,
            'html': _render_comment_list_html(request, post, data),
            'total': data['total'],
            'sort': data['sort'],
        })
    return redirect(f'{reverse("post_detail", args=[post.id])}?sort={data["sort"]}#comments')


def _load_comment_page(request, post):
    """构造一页 B 站风格的评论数据。

    返回结构：
        roots       当前页的「楼层」列表（CommentNode）
        replies     楼层 id -> 该楼全部回复（CommentNode，模板里按需折叠）
        reply_more  楼层 id -> 被折叠起来的回复条数
        reply_counts 楼层 id -> 回复总数
        total       评论总数（不含已删除）
        page_obj    楼层分页对象
        sort        当前排序（hot / new）
    """
    sort = request.GET.get('sort', 'hot')
    if sort not in ('hot', 'new'):
        sort = 'hot'

    comments = list(
        post.comments
        .select_related('author', 'parent', 'parent__author', 'reply_to')
        .annotate(like_total=Count('likes'))
        .prefetch_related(
            Prefetch('likes', queryset=User.objects.order_by('username')),
        )
    )

    user = request.user
    liked_ids = set()
    if user.is_authenticated:
        liked_ids = set(
            CommentLike.objects.filter(user=user, comment__post=post)
            .values_list('comment_id', flat=True)
        )

    # 作者资料一次性取回（匿名访问时 user.id 会是 None，必须排除）
    author_ids = {c.author_id for c in comments}
    profile_map = {
        p.user_id: p
        for p in UserProfile.objects.filter(user_id__in=author_ids).select_related('user')
    }

    children = {}
    for c in comments:
        if c.root_id:
            children.setdefault(c.root_id, []).append(c)

    roots_db = [c for c in comments if c.parent_id is None]
    if sort == 'hot':
        # 热度 = 点赞数，楼主发言额外加权，让 UP 主的话更容易被看到
        roots_db.sort(key=lambda c: (
            -(c.like_total + (1 if c.author_id == post.author_id else 0)),
            0 if c.author_id == post.author_id else 1,
            c.created,
        ))
    else:
        roots_db.sort(key=lambda c: (c.created, c.id), reverse=True)

    total = len([c for c in comments if not c.is_deleted])
    paginator = Paginator(roots_db, settings.COMMENTS_PER_PAGE)
    try:
        page = paginator.page(request.GET.get('cpage') or 1)
    except (PageNotAnInteger, EmptyPage):
        page = paginator.page(1)

    reply_counts = {root.id: len(children.get(root.id, [])) for root in roots_db}

    roots, replies_map, reply_more = [], {}, {}
    for index, comment in enumerate(page.object_list):
        # 楼层号按「第几条评论」从大到小编号，与 B 站一致
        floor_number = paginator.count - ((page.number - 1) * settings.COMMENTS_PER_PAGE + index)
        roots.append(_to_node(comment, user, profile_map, post.author_id, liked_ids,
                              floor=floor_number))
        reps = sorted(children.get(comment.id, []), key=lambda c: (c.created, c.id))
        replies_map[comment.id] = [
            _to_node(r, user, profile_map, post.author_id, liked_ids,
                     floor=comment.id) for r in reps
        ]
        reply_more[comment.id] = max(0, len(reps) - settings.COMMENT_REPLY_PREVIEW)

    return {
        'roots': roots,
        'replies': replies_map,
        'reply_more': reply_more,
        'reply_counts': reply_counts,
        'page_obj': page,
        'total': total,
        'sort': sort,
    }


def _render_comments_response(request, post):
    """发表/删除评论后的统一响应（保留这个名字，语义更贴近调用点）。"""
    return _comment_payload(request, post)


@require_POST
@login_required
def comment_create(request, post_id):
    """发表评论 / 回复（支持 AJAX 与普通表单提交）。"""
    post = get_object_or_404(Post, id=post_id)
    form = CommentForm(request.POST, request.FILES, user=request.user, post=post)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if not form.is_valid():
        error = '；'.join(msg for errors in form.errors.values() for msg in errors) or '评论提交失败。'
        if is_ajax:
            return JsonResponse({'ok': False, 'error': error}, status=400)
        messages.error(request, error)
        return _comment_payload(request, post)

    image_error = _validate_image(form.cleaned_data.get('image'))
    if image_error:
        if is_ajax:
            return JsonResponse({'ok': False, 'error': image_error}, status=400)
        messages.error(request, image_error)
        return _comment_payload(request, post)

    comment = form.save(commit=False)
    comment.post = post
    comment.author = request.user
    parent = form.cleaned_data.get('parent')
    if parent:
        comment.parent = parent
        comment.reply_to = parent.author
    comment.save()

    _notify_on_comment(comment, post, parent)

    if is_ajax:
        data = _load_comment_page(request, post)
        return JsonResponse({
            'ok': True,
            'html': _render_comment_list_html(request, post, data),
            'total': data['total'],
            'message': '回复成功' if parent else '评论发布成功',
        })
    messages.success(request, '评论发布成功。')
    return redirect(f'{reverse("post_detail", args=[post.id])}#comments')


def _notify_on_comment(comment, post, parent):
    """评论触发的站内通知：回复优先通知被回复的人，否则通知楼主。"""
    sender = comment.author
    excerpt = plain_text(comment.content, 40)
    if parent:
        Notification.push(parent.author, 'reply', sender=sender, post=post,
                          comment=comment, text=excerpt)
    Notification.push(post.author, 'comment', sender=sender, post=post,
                      comment=comment, text=excerpt)


@require_POST
@login_required
def comment_delete(request, comment_id):
    """删除评论：作者本人或文章作者（楼主）都可以删；保留占位避免楼层塌陷。"""
    comment = get_object_or_404(Comment.objects.select_related('post'), id=comment_id)
    post = comment.post
    if comment.author != request.user and post.author != request.user:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': '你没有权限删除这条评论。'}, status=403)
        messages.error(request, '你没有权限删除此评论。')
        return redirect('post_detail', post_id=post.id)

    comment.is_deleted = True
    comment.content = '该评论已删除'
    comment.image = None
    comment.save(update_fields=['is_deleted', 'content', 'image'])

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        data = _load_comment_page(request, post)
        return JsonResponse({
            'ok': True,
            'html': _render_comment_list_html(request, post, data),
            'total': data['total'],
        })
    messages.success(request, '评论已删除。')
    return redirect(f'{reverse("post_detail", args=[post.id])}#comments')


@require_POST
@login_required
def comment_like(request, comment_id):
    """评论点赞 / 取消点赞（B 站式的爱心按钮）。"""
    comment = get_object_or_404(Comment, id=comment_id)
    like, created = CommentLike.objects.get_or_create(user=request.user, comment=comment)
    if not created:
        like.delete()
    liked = created
    if liked:
        Notification.push(comment.author, 'comment_like', sender=request.user,
                          post=comment.post, comment=comment)
    return JsonResponse({'ok': True, 'liked': liked, 'count': comment.likes.count()})


# ---------------------------------------------------------------------------
# 文章互动：点赞 / 点踩 / 收藏
# ---------------------------------------------------------------------------
@require_POST
@login_required
def post_vote(request, post_id):
    """点赞 / 点踩（再次点击同一按钮即取消，与 B 站一致）。"""
    post = get_object_or_404(Post, id=post_id)
    try:
        value = int(request.POST.get('value', 1))
    except (TypeError, ValueError):
        value = 1
    if value not in (1, -1):
        value = 1

    existing = PostVote.objects.filter(user=request.user, post=post).first()
    if existing and existing.value == value:
        existing.delete()
        my_vote = 0
    elif existing:
        existing.value = value
        existing.save(update_fields=['value'])
        my_vote = value
    else:
        PostVote.objects.create(user=request.user, post=post, value=value)
        my_vote = value

    if my_vote == 1:
        Notification.push(post.author, 'like', sender=request.user, post=post)

    return JsonResponse({
        'ok': True,
        'my_vote': my_vote,
        'like_count': post.votes.filter(value=1).count(),
        'dislike_count': post.votes.filter(value=-1).count(),
    })


@require_POST
@login_required
def post_bookmark(request, post_id):
    """收藏 / 取消收藏。"""
    post = get_object_or_404(Post, id=post_id)
    bookmark, created = Bookmark.objects.get_or_create(user=request.user, post=post)
    if not created:
        bookmark.delete()
    else:
        Notification.push(post.author, 'bookmark', sender=request.user, post=post)
    return JsonResponse({'ok': True, 'bookmarked': created, 'count': post.bookmarks.count()})


# ---------------------------------------------------------------------------
# 标签
# ---------------------------------------------------------------------------
def tag_detail(request, slug):
    tag = get_object_or_404(Tag, slug=slug)
    posts = _published_posts().filter(tags=tag).order_by('-created')
    page = _paginate(request, posts, settings.POSTS_PER_PAGE)
    return render(request, 'blog/tag_detail.html', {
        'tag': tag, 'posts': page, 'page_obj': page,
    })


def tag_cloud(request):
    """全部标签页。"""
    tags = (Tag.objects.annotate(
                published_count=Count('posts', filter=Q(posts__status='published')))
            .order_by('-published_count', 'name'))
    return render(request, 'blog/tag_cloud.html', {'tags': tags})


# ---------------------------------------------------------------------------
# 用户主页 / 个人中心
# ---------------------------------------------------------------------------
def user_profile(request, username):
    """公开的用户主页：他的文章、收藏、评论、统计。"""
    author = get_object_or_404(User, username=username)
    profile = get_profile(author)
    is_self = request.user.is_authenticated and request.user.pk == author.pk

    posts = _post_list_queryset().filter(author=author)
    if not is_self:
        posts = posts.published()
    posts = posts.order_by('-created')

    tab = request.GET.get('tab', 'posts')
    context = {
        'author': author,
        'author_profile': profile,
        'is_self': is_self,
        'tab': tab,
        'stats': {
            'posts': posts.count(),
            'views': Post.objects.filter(author=author, status='published')
                        .aggregate(total=models.Sum('views'))['total'] or 0,
            'likes': PostVote.objects.filter(post__author=author, value=1).count(),
            'comments': Comment.objects.filter(author=author, is_deleted=False).count(),
        },
        'recent_comments': Comment.objects.filter(author=author, is_deleted=False)
                             .select_related('post')[:10],
    }
    if tab == 'bookmarks' and is_self:
        context['bookmarks'] = (Bookmark.objects.filter(user=author)
                                .select_related('post', 'post__author')[:50])
    else:
        context['posts'] = _paginate(request, posts, settings.POSTS_PER_PAGE)
        context['page_obj'] = context['posts']
    return render(request, 'blog/user_profile.html', context)


@login_required
def profile(request):
    """个人中心：我的文章（按状态筛选）+ 数据概览。"""
    status = request.GET.get('status', 'all')
    posts = _post_list_queryset().filter(author=request.user)
    if status == 'published':
        posts = posts.filter(status='published')
    elif status == 'draft':
        posts = posts.filter(status='draft')
    posts = posts.order_by('-created')

    my_posts = Post.objects.filter(author=request.user)
    profile_obj = get_profile(request.user)
    context = {
        'posts': _paginate(request, posts, settings.POSTS_PER_PAGE),
        'status': status,
        'profile_obj': profile_obj,
        'summary': {
            'total': my_posts.count(),
            'published': my_posts.filter(status='published').count(),
            'draft': my_posts.filter(status='draft').count(),
            'views': my_posts.aggregate(total=models.Sum('views'))['total'] or 0,
            'likes': PostVote.objects.filter(post__author=request.user, value=1).count(),
            'comments_received': Comment.objects.filter(post__author=request.user,
                                                         is_deleted=False).count(),
            'bookmarks': Bookmark.objects.filter(user=request.user).count(),
        },
        'recent_notifications': Notification.objects.filter(recipient=request.user)[:6],
        'recent_comments': Comment.objects.filter(author=request.user, is_deleted=False)
                             .select_related('post')[:5],
    }
    context['page_obj'] = context['posts']
    return render(request, 'blog/profile.html', context)


@login_required
def profile_edit(request):
    """编辑个人资料。"""
    profile_obj = get_profile(request.user)
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=profile_obj)
        avatar_error = _validate_image(request.FILES.get('avatar'))
        if avatar_error:
            messages.error(request, avatar_error)
        elif form.is_valid():
            form.save()
            messages.success(request, '资料已更新。')
            return redirect('user_profile', username=request.user.username)
        else:
            messages.error(request, '保存失败，请检查表单。')
    else:
        form = ProfileForm(instance=profile_obj)
    return render(request, 'blog/profile_edit.html', {'form': form, 'profile_obj': profile_obj})


# ---------------------------------------------------------------------------
# 文章增删改
# ---------------------------------------------------------------------------
@login_required
def post_create(request):
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.save()
            form.save()          # 写入标签并清理 Markdown 渲染缓存
            messages.success(request, '文章发布成功！')
            return redirect('post_detail', post_id=post.id)
        messages.error(request, '发布失败，请检查表单里的错误提示。')
    else:
        form = PostForm()
    return render(request, 'blog/post_form.html', {'form': form, 'action': '发布', 'is_edit': False})


@login_required
def post_edit(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    if post.author != request.user:
        messages.error(request, '你没有权限编辑此文章')
        return redirect('index')

    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            form.save()
            messages.success(request, '文章已保存')
            return redirect('post_detail', post_id=post.id)
        messages.error(request, '保存失败，请检查表单里的错误提示。')
    else:
        form = PostForm(instance=post)
    return render(request, 'blog/post_form.html', {
        'form': form, 'post': post, 'action': '编辑', 'is_edit': True,
    })


@login_required
def post_delete(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    if post.author != request.user:
        messages.error(request, '你没有权限删除此文章')
        return redirect('post_detail', post_id=post.id)

    if request.method == 'POST':
        post.delete()
        messages.success(request, '文章已删除')
        return redirect('index')
    return render(request, 'blog/post_confirm_delete.html', {'post': post})


@login_required
@require_POST
def toggle_post_status(request, post_id):
    """切换文章状态（发布 <-> 草稿）"""
    post = get_object_or_404(Post, id=post_id, author=request.user)
    post.status = 'draft' if post.status == 'published' else 'published'
    post.save(update_fields=['status'])
    if post.status == 'published':
        messages.success(request, f'文章《{post.title}》已发布。')
    else:
        messages.success(request, f'文章《{post.title}》已转为草稿。')
    return redirect(request.POST.get('next') or 'profile')


# ---------------------------------------------------------------------------
# 站内通知
# ---------------------------------------------------------------------------
@login_required
def notifications(request):
    kind = request.GET.get('kind', 'all')
    qs = Notification.objects.filter(recipient=request.user).select_related(
        'sender', 'post', 'comment')
    if kind in dict(Notification.TYPE_CHOICES):
        qs = qs.filter(kind=kind)
    page = _paginate(request, qs, 15)
    unread = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return render(request, 'blog/notifications.html', {
        'notifications': page, 'page_obj': page, 'kind': kind,
        'unread': unread, 'type_choices': Notification.TYPE_CHOICES,
    })


@login_required
@require_POST
def notification_read(request):
    """标记通知已读：single=id 或 all=1。"""
    if request.POST.get('all'):
        updated = Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return JsonResponse({'ok': True, 'updated': updated, 'unread': 0})
    try:
        pk = int(request.POST.get('single', 0))
    except (TypeError, ValueError):
        pk = 0
    Notification.objects.filter(recipient=request.user, pk=pk).update(is_read=True)
    unread = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({'ok': True, 'unread': unread})


@login_required
def notification_poll(request):
    """导航栏通知小红点的轮询接口。"""
    qs = Notification.objects.filter(recipient=request.user).select_related('sender')[:8]
    unread = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({
        'unread': unread,
        'items': [{
            'id': n.id,
            'icon': n.icon,
            'summary': n.summary,
            'url': n.get_absolute_url(),
            'created': n.created.strftime('%m-%d %H:%M'),
            'is_read': n.is_read,
        } for n in qs],
    })


# ---------------------------------------------------------------------------
# 其它
# ---------------------------------------------------------------------------
def about(request):
    """关于页：展示站点数据与统计，答辩演示时很加分。"""
    stats = {
        'posts': Post.objects.published().count(),
        'users': User.objects.count(),
        'comments': Comment.objects.filter(is_deleted=False).count(),
        'likes': PostVote.objects.filter(value=1).count(),
        'tags': Tag.objects.count(),
        'views': Post.objects.aggregate(total=models.Sum('views'))['total'] or 0,
    }
    top_posts = _published_posts().order_by('-views')[:5]
    top_authors = (User.objects.annotate(
                        published_count=Count('posts', filter=Q(posts__status='published')))
                   .filter(published_count__gt=0).order_by('-published_count')[:6])
    return render(request, 'blog/about.html', {
        'stats': stats, 'top_posts': top_posts, 'top_authors': top_authors,
    })


def page_not_found(request, exception):
    return render(request, 'blog/404.html', status=404)


def server_error(request):
    return render(request, 'blog/500.html', status=500)

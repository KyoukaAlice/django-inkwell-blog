"""模板上下文处理器：给所有页面注入导航栏与侧边栏需要的数据。"""
from django.db import OperationalError, ProgrammingError
from django.db.models import Count, Q, Sum

from .models import Category, Notification, Post, Tag


def site_context(request):
    """站点公共上下文（分类导航、热门文章、热门标签、未读通知数）。

    查询都用 try/except 包住：数据库连不上（例如 MySQL 没启动）时模板仍能渲染，
    只是这些区块为空，不会让整站 500。
    """
    context = {
        'nav_categories': [],
        'hot_posts': [],
        'hot_tags': [],
        'unread_notifications': 0,
        'nav_stats': {'posts': 0, 'views': 0},
    }
    try:
        context['nav_categories'] = list(
            Category.objects.annotate(
                published_count=Count('posts', filter=Q(posts__status='published'))
            ).order_by('-published_count', 'name')[:12]
        )
        context['hot_posts'] = list(
            Post.objects.published().with_counts().order_by('-views', '-created')[:5]
        )
        context['hot_tags'] = list(
            Tag.objects.annotate(
                published_count=Count('posts', filter=Q(posts__status='published'))
            ).filter(published_count__gt=0).order_by('-published_count', 'name')[:24]
        )
        stats = Post.objects.published().aggregate(
            posts=Count('id'), views=Sum('views')
        )
        context['nav_stats'] = {
            'posts': stats['posts'] or 0,
            'views': stats['views'] or 0,
        }
        if request.user.is_authenticated:
            context['unread_notifications'] = Notification.objects.filter(
                recipient=request.user, is_read=False
            ).count()
    except (OperationalError, ProgrammingError):
        pass
    return context

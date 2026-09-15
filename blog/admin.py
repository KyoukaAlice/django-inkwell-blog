from django.contrib import admin
from django.utils.html import format_html

from .models import (Bookmark, Category, Comment, CommentLike, Notification, Post,
                     PostVote, Tag, UserProfile)


class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0
    fields = ['author', 'content', 'parent', 'is_deleted', 'created']
    readonly_fields = ['created']
    raw_id_fields = ['author', 'parent']
    show_change_link = True


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'post_total', 'created']
    search_fields = ['name']
    list_filter = ['created']

    @admin.display(description='文章数')
    def post_total(self, obj):
        return obj.posts.count()


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'post_total', 'created']
    search_fields = ['name', 'slug']
    prepopulated_fields = {}          # slug 由模型自动生成（兼容中文标签）

    @admin.display(description='文章数')
    def post_total(self, obj):
        return obj.posts.count()


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'category', 'tag_list', 'status',
                    'views', 'like_total', 'comment_total', 'created']
    list_filter = ['status', 'category', 'tags', 'created', 'author']
    search_fields = ['title', 'content', 'excerpt']
    raw_id_fields = ['author']
    filter_horizontal = ['tags']
    date_hierarchy = 'created'
    ordering = ['-created']
    inlines = [CommentInline]
    fieldsets = (
        ('基本信息', {'fields': ('title', 'author', 'category', 'tags', 'cover')}),
        ('正文', {'fields': ('excerpt', 'content')}),
        ('状态与数据', {'fields': ('status', 'views')}),
    )

    @admin.display(description='标签')
    def tag_list(self, obj):
        return '、'.join(obj.tags.values_list('name', flat=True)) or '—'

    @admin.display(description='赞')
    def like_total(self, obj):
        return obj.votes.filter(value=1).count()

    @admin.display(description='评论')
    def comment_total(self, obj):
        return obj.comments.filter(is_deleted=False).count()


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['content_preview', 'author', 'post', 'parent', 'depth',
                    'like_total', 'is_deleted', 'created']
    list_filter = ['is_deleted', 'depth', 'created']
    search_fields = ['content', 'author__username', 'post__title']
    raw_id_fields = ['post', 'author', 'parent', 'root', 'reply_to']
    list_editable = ['is_deleted']
    date_hierarchy = 'created'

    @admin.display(description='评论内容预览')
    def content_preview(self, obj):
        text = obj.content[:50] + ('…' if len(obj.content) > 50 else '')
        return format_html('<span title="{}">{}</span>', obj.content[:200], text)

    @admin.display(description='点赞')
    def like_total(self, obj):
        return obj.likes.count()

    actions = ['mark_deleted', 'mark_visible']

    @admin.action(description='标记为已删除（保留楼层）')
    def mark_deleted(self, request, queryset):
        queryset.update(is_deleted=True)

    @admin.action(description='恢复显示')
    def mark_visible(self, request, queryset):
        queryset.update(is_deleted=False)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'nickname', 'location', 'bio', 'created']
    search_fields = ['user__username', 'user__email', 'bio']
    raw_id_fields = ['user']

    @admin.display(description='昵称')
    def nickname(self, obj):
        return obj.user.first_name or '—'


@admin.register(PostVote)
class PostVoteAdmin(admin.ModelAdmin):
    list_display = ['user', 'post', 'value', 'created']
    list_filter = ['value', 'created']
    raw_id_fields = ['user', 'post']


@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    list_display = ['user', 'post', 'created']
    list_filter = ['created']
    raw_id_fields = ['user', 'post']


@admin.register(CommentLike)
class CommentLikeAdmin(admin.ModelAdmin):
    list_display = ['user', 'comment', 'created']
    raw_id_fields = ['user', 'comment']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'sender', 'kind', 'post', 'is_read', 'created']
    list_filter = ['kind', 'is_read', 'created']
    search_fields = ['recipient__username', 'sender__username', 'text']
    raw_id_fields = ['recipient', 'sender', 'post', 'comment']
    actions = ['mark_read']

    @admin.action(description='标记为已读')
    def mark_read(self, request, queryset):
        queryset.update(is_read=True)


admin.site.site_header = 'DjangoBlog 后台管理'
admin.site.site_title = 'DjangoBlog'
admin.site.index_title = '内容与互动数据管理'

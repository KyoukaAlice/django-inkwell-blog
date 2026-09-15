"""数据迁移：为评论系统改造回填历史数据。

0004 给 Comment 加了 root / depth 字段、并新建了 UserProfile 表，但老数据里：
  * 所有历史评论的 root 都是 NULL、depth 都是 0，楼中楼结构会丢失；
  * 已存在的用户没有对应的 UserProfile（头像/简介页面会取不到）；
  * 老文章没有阅读量数据（保持 0 即可，无需处理）。

这里把 root / depth 按父子关系重算一遍，并给所有老用户补建资料。
"""
from django.db import migrations


def build_comment_tree(apps, schema_editor):
    Comment = apps.get_model('blog', 'Comment')

    # 第一遍：直接回复一级评论的，depth=1，root=父评论
    for comment in Comment.objects.filter(parent__isnull=False).select_related('parent'):
        comment.root_id = comment.parent.root_id or comment.parent_id
        comment.depth = 1 if comment.parent.parent_id is None else 2
        comment.save(update_fields=['root', 'depth'])

    # 第二遍：更深层的回复统一压平到 depth=2，root 指向所属楼层
    # （模型里 MAX_DEPTH=2，这里保证历史数据也符合同一规则）
    changed = []
    for comment in Comment.objects.filter(parent__isnull=False).select_related('parent'):
        root_id = comment.parent.root_id or comment.parent_id
        if comment.root_id != root_id or comment.depth != min(comment.parent.depth + 1, 2):
            comment.root_id = root_id
            comment.depth = min(comment.parent.depth + 1, 2)
            changed.append(comment)
    if changed:
        Comment.objects.bulk_update(changed, ['root', 'depth'])


def create_user_profiles(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    UserProfile = apps.get_model('blog', 'UserProfile')
    existing = set(UserProfile.objects.values_list('user_id', flat=True))
    UserProfile.objects.bulk_create([
        UserProfile(user_id=uid) for uid in User.objects.values_list('id', flat=True)
        if uid not in existing
    ])


def noop(apps, schema_editor):
    """回滚：这些字段本身就允许为空，不需要恢复。"""


class Migration(migrations.Migration):

    dependencies = [
        ('blog', '0004_bookmark_commentlike_notification_postvote_tag_and_more'),
    ]

    operations = [
        migrations.RunPython(build_comment_tree, noop),
        migrations.RunPython(create_user_profiles, noop),
    ]

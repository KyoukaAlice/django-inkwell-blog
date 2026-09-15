"""为冒烟测试准备一个独立账号，避免和演示账号的频率限制互相干扰。

    python setup_smoke_user.py            # 创建/重置 smoke 账号（清空它的历史评论）
    python setup_smoke_user.py --touch    # 把它的评论时间整体往前挪，解除 15 秒频率限制
    python setup_smoke_user.py --cleanup  # 删除该账号及其评论

说明：业务上有「同一用户 15 秒内只能发一条评论」的限制，冒烟测试需要连续发两条，
所以这里在测试前后各把时间线「往回拨」一次，而不是真的 sleep 15 秒。
"""
import datetime
import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'DjangoBlog.settings')
django.setup()                                  # noqa: E402

from django.contrib.auth.models import User     # noqa: E402
from django.utils import timezone               # noqa: E402

from blog.models import Comment, UserProfile    # noqa: E402

USERNAME = 'smoke'
PASSWORD = 'SmokeTest!2026'
BACKDATE_SECONDS = 300          # 往前拨 5 分钟，足够覆盖 15 秒的限制窗口


def backdate(user):
    """把该用户的全部评论时间统一往前挪，解除频率限制。"""
    comments = Comment.objects.filter(author=user)
    count = comments.count()
    for comment in comments:
        comment.created = comment.created - datetime.timedelta(seconds=BACKDATE_SECONDS)
        comment.save(update_fields=['created'])
    return count


def cleanup():
    user = User.objects.filter(username=USERNAME).first()
    if user:
        Comment.objects.filter(author=user).delete()
        user.delete()
        print(f'已删除冒烟测试账号 {USERNAME} 及其评论')


def setup():
    user, created = User.objects.get_or_create(username=USERNAME)
    user.set_password(PASSWORD)
    user.first_name = '冒烟测试'
    user.save()
    UserProfile.objects.get_or_create(user=user)

    # 清掉上一次冒烟测试留下的评论：一来保持数据干净，
    # 二来避免撞上「15 秒内只能发一条评论」的频率限制。
    stale = Comment.objects.filter(author=user)
    removed = stale.count()
    stale.delete()

    print(f'{"创建" if created else "重置"}冒烟测试账号：{USERNAME} / {PASSWORD}'
          f'（清理历史评论 {removed} 条）')


def touch():
    user = User.objects.filter(username=USERNAME).first()
    if not user:
        print('冒烟测试账号还不存在，先运行不带参数的 setup_smoke_user.py')
        return
    moved = backdate(user)
    print(f'已把 {USERNAME} 的 {moved} 条评论时间往前挪，解除频率限制')


if __name__ == '__main__':
    if '--cleanup' in sys.argv:
        cleanup()
    elif '--touch' in sys.argv:
        touch()
    else:
        setup()

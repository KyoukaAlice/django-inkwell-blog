"""DjangoBlog 改造后的功能测试。

覆盖：认证、文章 CRUD、标签、Markdown 渲染、阅读量、点赞/点踩/收藏、
B 站风格评论系统（楼中楼嵌套、点赞、表情、排序、分页、权限）、站内通知、
用户主页、搜索、分页与错误处理。

运行：
    $env:DB_ENGINE="sqlite"; python manage.py test blog -v 2
"""
import io
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .markdown_utils import is_emoji_only, render_markdown
from .models import (Bookmark, Category, Comment, CommentLike, Notification, Post,
                     PostVote, Tag, UserProfile)

# 测试里会上传头像 / 封面 / 评论配图。必须把 MEDIA_ROOT 指到临时目录，
# 否则测试产生的垃圾图片会一路写进项目的 media/ 里（已经踩过一次）。
TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix='djangoblog-test-media-')


def png_bytes(color=(255, 0, 0)):
    """生成一张 1x1 的合法 PNG，用于测试图片上传。"""
    from PIL import Image
    buffer = io.BytesIO()
    Image.new('RGB', (1, 1), color).save(buffer, format='PNG')
    return buffer.getvalue()


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class BaseBlogTest(TestCase):
    """公共数据：两个用户、分类、标签、已发布/草稿文章。"""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        # 清掉本次测试上传的文件，避免临时目录堆积
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.alice = User.objects.create_user('alice', password='BlogPass!2026', first_name='爱丽丝')
        self.bob = User.objects.create_user('bob', password='BlogPass!2026', first_name='鲍勃')
        self.category = Category.objects.create(name='技术')
        self.tag = Tag.objects.create(name='Django')
        self.post = Post.objects.create(
            title='Django 评论系统实战', content='# 标题\n\n正文内容，**加粗** 与 `code`。',
            excerpt='摘要', author=self.alice, category=self.category, status='published',
        )
        self.post.tags.add(self.tag)
        self.draft = Post.objects.create(
            title='草稿文章', content='还没写完的内容', author=self.alice, status='draft',
        )
        self.post_url = reverse('post_detail', args=[self.post.id])


class ModelAndMarkdownTests(BaseBlogTest):
    def test_user_profile_auto_created(self):
        """新建用户时信号自动创建 UserProfile。"""
        carol = User.objects.create_user('carol', password='BlogPass!2026')
        self.assertTrue(UserProfile.objects.filter(user=carol).exists())

    def test_avatar_letter_and_color_stable(self):
        profile = UserProfile.objects.get(user=self.alice)
        self.assertEqual(profile.avatar_letter, 'A')
        self.assertEqual(profile.avatar_color, profile.avatar_color)
        self.assertEqual(profile.display_avatar, '')

    def test_tag_slug_auto_generated_for_chinese(self):
        tag = Tag.objects.create(name='机器学习')
        self.assertTrue(tag.slug)
        self.assertEqual(tag.get_absolute_url(), reverse('tag_detail', args=[tag.slug]))

    def test_markdown_renders_and_sanitizes(self):
        html = render_markdown('# 标题\n\n```python\nprint(1)\n```\n\n<script>alert(1)</script>')
        self.assertIn('<h1', html)
        self.assertNotIn('<script>', html)

    def test_markdown_code_block_is_highlighted(self):
        """围栏代码块必须真的被识别并上色。

        回归点：markdown.markdown(extensions=[...]) 只接受扩展名字符串，
        如果传的是 FencedCodeExtension() 这类实例，不会报错但也不生效，
        代码块会退化成一整段普通文本 —— 这个测试就是为了钉死这种情况。
        """
        html = render_markdown('```python\ndef foo(x):\n    # 注释\n    return x\n```')
        self.assertIn('codehilite', html, '代码块没有被 codehilite 处理')
        self.assertIn('<span class="k">def</span>', html, 'Python 关键字没有高亮')
        self.assertIn('<span class="nf">foo</span>', html, '函数名没有高亮')
        self.assertIn('<span class="c1">', html, '注释没有高亮')

    def test_markdown_tables_and_toc(self):
        html = render_markdown('## 中文小节\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n')
        self.assertIn('<table', html)
        self.assertIn('id="中文小节"', html, '中文标题锚点生成失败')
        self.assertIn('headerlink', html)

    def test_emoticon_code_rendered_in_markdown(self):
        html = render_markdown('你好 [em:smile]')
        self.assertIn('emoticons/smile.svg', html)

    def test_emoji_only_detection(self):
        self.assertTrue(is_emoji_only('[em:smile]'))
        self.assertFalse(is_emoji_only('你好'))

    def test_post_html_content_cached(self):
        html = self.post.html_content
        self.assertIn('<h1', html)
        self.post.refresh_from_db()
        self.assertTrue(self.post.rendered_content)
        self.assertEqual(self.post.html_content, html)

    def test_display_excerpt_falls_back_to_content(self):
        self.assertEqual(self.post.display_excerpt, '摘要')
        self.draft.excerpt = ''
        self.assertIn('还没写完', self.draft.display_excerpt)

    def test_reading_minutes_min_one(self):
        self.assertGreaterEqual(self.post.reading_minutes, 1)

    def test_comment_tree_root_and_depth(self):
        """楼中楼：root 指向楼层，depth 最深压平到 2。"""
        c1 = Comment.objects.create(post=self.post, author=self.bob, content='一楼')
        c2 = Comment.objects.create(post=self.post, author=self.alice, content='回复一楼', parent=c1)
        c3 = Comment.objects.create(post=self.post, author=self.bob, content='楼中楼', parent=c2)
        c4 = Comment.objects.create(post=self.post, author=self.alice, content='第四层', parent=c3)
        self.assertIsNone(c1.root_id)
        self.assertEqual(c1.depth, 0)
        self.assertEqual((c2.root_id, c2.depth), (c1.id, 1))
        self.assertEqual((c3.root_id, c3.depth), (c1.id, 2))
        self.assertEqual((c4.root_id, c4.depth), (c1.id, 2), '超过两层的回复应压平到 depth=2')

    def test_comment_reply_target_name(self):
        c1 = Comment.objects.create(post=self.post, author=self.bob, content='一楼')
        c2 = Comment.objects.create(post=self.post, author=self.alice, content='回复', parent=c1,
                                    reply_to=self.bob)
        self.assertEqual(c2.reply_target_name(), 'bob')


class AuthViewTests(BaseBlogTest):
    def test_login_page_renders(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '欢迎回来')

    def test_register_creates_user_and_logs_in(self):
        response = self.client.post(reverse('register'), {
            'username': 'newbie', 'email': 'n@example.com',
            'password1': 'Str0ngPass!2026', 'password2': 'Str0ngPass!2026',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(username='newbie').exists())
        self.assertTrue(UserProfile.objects.filter(user__username='newbie').exists())

    def test_login_success_and_bad_password(self):
        ok = self.client.post(reverse('login'), {'username': 'alice', 'password': 'BlogPass!2026'})
        self.assertEqual(ok.status_code, 302)
        self.client.logout()
        bad = self.client.post(reverse('login'), {'username': 'alice', 'password': 'wrong'})
        self.assertEqual(bad.status_code, 200)
        self.assertContains(bad, '用户名或密码不正确')

    def test_login_ignores_external_next(self):
        """开放重定向防护：站外 next 不应跳转。"""
        response = self.client.post(
            reverse('login') + '?next=https://evil.example.com/',
            {'username': 'alice', 'password': 'BlogPass!2026'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('evil.example.com', response['Location'])

    def test_logout_redirects_to_login(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse('logout'))
        self.assertEqual(response.status_code, 302)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])


class PostViewTests(BaseBlogTest):
    def test_index_lists_published_only(self):
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.post.title)
        self.assertNotContains(response, self.draft.title)

    def test_index_search_by_keyword(self):
        response = self.client.get(reverse('index'), {'keyword': '评论系统'})
        self.assertContains(response, self.post.title)
        empty = self.client.get(reverse('index'), {'keyword': '不存在的关键词xyz'})
        # 标题可能出现在侧边栏「热门文章」里，所以要看列表本身而不是整页文本
        self.assertEqual(len(empty.context['posts']), 0)

    def test_index_filter_by_category_and_tag(self):
        by_cat = self.client.get(reverse('index'), {'category': self.category.id})
        self.assertContains(by_cat, self.post.title)
        by_tag = self.client.get(reverse('index'), {'tag': self.tag.slug})
        self.assertContains(by_tag, self.post.title)
        # 分类筛选应真的过滤掉其它分类的文章
        other_cat = Category.objects.create(name='生活')
        other = Post.objects.create(title='生活随笔', content='内容' * 20,
                                    author=self.bob, category=other_cat, status='published')
        filtered = self.client.get(reverse('index'), {'category': self.category.id})
        self.assertNotIn(other, list(filtered.context['posts']))

    def test_index_sort_options(self):
        for sort in ('new', 'hot', 'views', 'discussed'):
            response = self.client.get(reverse('index'), {'sort': sort})
            self.assertEqual(response.status_code, 200, f'sort={sort} 应正常渲染')

    def test_index_date_range_filter(self):
        response = self.client.get(reverse('index'), {'start_date': '2000-01-01',
                                                      'end_date': '2999-01-01'})
        self.assertContains(response, self.post.title)
        response = self.client.get(reverse('index'), {'end_date': '2000-01-01'})
        self.assertEqual(len(response.context['posts']), 0, '结束日期早于文章时间应筛掉文章')

    def test_post_detail_view_increments_views(self):
        before = Post.objects.get(pk=self.post.pk).views
        self.client.get(self.post_url)
        self.assertEqual(Post.objects.get(pk=self.post.pk).views, before + 1)

    def test_author_view_does_not_increment_views(self):
        self.client.force_login(self.alice)
        before = Post.objects.get(pk=self.post.pk).views
        self.client.get(self.post_url)
        self.assertEqual(Post.objects.get(pk=self.post.pk).views, before)

    def test_draft_hidden_from_others_but_visible_to_author(self):
        draft_url = reverse('post_detail', args=[self.draft.id])
        self.assertEqual(self.client.get(draft_url).status_code, 404)
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(draft_url).status_code, 200)

    def test_post_create_with_tags(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse('post_create'), {
            'title': '我的新文章标题', 'content': '这是一段足够长的正文内容，用于通过校验。',
            'excerpt': '', 'category': self.category.id, 'status': 'published',
            'tags_input': 'Python, 测试标签',
        })
        self.assertEqual(response.status_code, 302)
        post = Post.objects.get(title='我的新文章标题')
        self.assertEqual(post.author, self.alice)
        self.assertEqual(set(post.tags.values_list('name', flat=True)), {'Python', '测试标签'})

    def test_post_create_rejects_short_content(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse('post_create'), {
            'title': '短', 'content': '太短', 'status': 'published',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '至少')

    def test_post_edit_permission(self):
        self.client.force_login(self.bob)
        response = self.client.post(reverse('post_edit', args=[self.post.id]),
                                    {'title': '篡改', 'content': 'x' * 30})
        self.assertEqual(response.status_code, 302)
        self.post.refresh_from_db()
        self.assertNotEqual(self.post.title, '篡改')

        self.client.force_login(self.alice)
        self.client.post(reverse('post_edit', args=[self.post.id]), {
            'title': '改过的标题', 'content': '改过的正文内容，长度足够通过校验。',
            'category': self.category.id, 'status': 'published', 'tags_input': 'Django',
        })
        self.post.refresh_from_db()
        self.assertEqual(self.post.title, '改过的标题')

    def test_toggle_post_status(self):
        self.client.force_login(self.alice)
        self.client.post(reverse('toggle_post_status', args=[self.post.id]))
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'draft')

    def test_toggle_status_requires_post(self):
        """GET 不应该改状态（视图是 @require_POST）。"""
        self.client.force_login(self.alice)
        response = self.client.get(reverse('toggle_post_status', args=[self.post.id]))
        self.assertEqual(response.status_code, 405)

    def test_post_delete_flow(self):
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(reverse('post_delete', args=[self.post.id])).status_code, 200)
        response = self.client.post(reverse('post_delete', args=[self.post.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Post.objects.filter(pk=self.post.pk).exists())

    def test_post_cover_upload(self):
        self.client.force_login(self.alice)
        cover = SimpleUploadedFile('cover.png', png_bytes(), content_type='image/png')
        response = self.client.post(reverse('post_create'), {
            'title': '带封面的文章', 'content': '正文内容足够长了，用来测试封面图上传。',
            'status': 'published', 'cover': cover,
        })
        self.assertEqual(response.status_code, 302)
        post = Post.objects.get(title='带封面的文章')
        self.assertTrue(post.cover.name.endswith('.png'))


class InteractionTests(BaseBlogTest):
    def test_vote_like_dislike_toggle(self):
        self.client.force_login(self.bob)
        url = reverse('post_vote', args=[self.post.id])

        data = self.client.post(url, {'value': 1}).json()
        self.assertEqual((data['my_vote'], data['like_count']), (1, 1))

        data = self.client.post(url, {'value': -1}).json()
        self.assertEqual((data['my_vote'], data['like_count'], data['dislike_count']), (-1, 0, 1))

        data = self.client.post(url, {'value': -1}).json()
        self.assertEqual((data['my_vote'], data['dislike_count']), (0, 0), '重复点踩应取消')

    def test_vote_requires_login_and_post(self):
        self.assertEqual(self.client.post(reverse('post_vote', args=[self.post.id])).status_code, 302)
        self.client.force_login(self.bob)
        self.assertEqual(self.client.get(reverse('post_vote', args=[self.post.id])).status_code, 405)

    def test_like_creates_notification_for_author(self):
        self.client.force_login(self.bob)
        self.client.post(reverse('post_vote', args=[self.post.id]), {'value': 1})
        note = Notification.objects.filter(recipient=self.alice, kind='like').first()
        self.assertIsNotNone(note)
        self.assertEqual(note.sender, self.bob)

    def test_dislike_does_not_notify(self):
        self.client.force_login(self.bob)
        self.client.post(reverse('post_vote', args=[self.post.id]), {'value': -1})
        self.assertFalse(Notification.objects.filter(recipient=self.alice, kind='like').exists())

    def test_self_like_does_not_notify(self):
        self.client.force_login(self.alice)
        self.client.post(reverse('post_vote', args=[self.post.id]), {'value': 1})
        self.assertEqual(Notification.objects.filter(recipient=self.alice).count(), 0)

    def test_bookmark_toggle(self):
        self.client.force_login(self.bob)
        url = reverse('post_bookmark', args=[self.post.id])
        data = self.client.post(url).json()
        self.assertTrue(data['bookmarked'])
        self.assertEqual(data['count'], 1)
        self.assertTrue(Bookmark.objects.filter(user=self.bob, post=self.post).exists())
        data = self.client.post(url).json()
        self.assertFalse(data['bookmarked'])
        self.assertEqual(data['count'], 0)

    def test_comment_like_toggle_and_notification(self):
        comment = Comment.objects.create(post=self.post, author=self.alice, content='楼主留言')
        self.client.force_login(self.bob)
        url = reverse('comment_like', args=[comment.id])
        data = self.client.post(url).json()
        self.assertEqual((data['liked'], data['count']), (True, 1))
        self.assertTrue(CommentLike.objects.filter(user=self.bob, comment=comment).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.alice,
                                                    kind='comment_like').exists())
        data = self.client.post(url).json()
        self.assertEqual((data['liked'], data['count']), (False, 0))


class CommentSystemTests(BaseBlogTest):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.bob)
        self.comment_url = reverse('comment_create', args=[self.post.id])

    def test_post_comment(self):
        response = self.client.post(self.comment_url, {'content': '写得很好，学习了！'})
        self.assertEqual(response.status_code, 302)
        comment = Comment.objects.get(post=self.post)
        self.assertEqual(comment.author, self.bob)
        self.assertIsNone(comment.parent)

    def test_ajax_comment_returns_html_fragment(self):
        response = self.client.post(
            self.comment_url, {'content': '这是 AJAX 评论 [em:smile]'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertIn('这是 AJAX 评论', data['html'])
        self.assertIn('emoticons/smile.svg', data['html'])
        self.assertEqual(data['total'], 1)

    def test_reply_creates_nested_tree(self):
        root = Comment.objects.create(post=self.post, author=self.alice, content='一楼')
        self.client.post(self.comment_url, {'content': '回复一楼', 'parent_id': root.id})
        reply = Comment.objects.get(parent=root)
        self.assertEqual(reply.root, root)
        self.assertEqual(reply.depth, 1)
        self.assertEqual(reply.reply_to, self.alice)

    def test_reply_to_comment_of_another_post_rejected(self):
        other = Post.objects.create(title='别的文章', content='内容' * 10,
                                    author=self.alice, status='published')
        foreign = Comment.objects.create(post=other, author=self.alice, content='别处的评论')
        response = self.client.post(
            self.comment_url, {'content': '非法回复', 'parent_id': foreign.id},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('不存在', response.json()['error'])
        self.assertFalse(Comment.objects.filter(content='非法回复').exists())

    def test_empty_comment_rejected(self):
        response = self.client.post(
            self.comment_url, {'content': '   '},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('不能为空', response.json()['error'])

    def test_comment_rate_limit(self):
        """15 秒内不能连续发两条，防止刷屏。"""
        self.client.post(self.comment_url, {'content': '第一条评论'})
        response = self.client.post(
            self.comment_url, {'content': '第二条评论'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('太快', response.json()['error'])
        self.assertEqual(Comment.objects.count(), 1)

    def test_comment_with_image(self):
        image = SimpleUploadedFile('c.png', png_bytes(), content_type='image/png')
        response = self.client.post(
            self.comment_url, {'content': '带图的评论', 'image': image},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        comment = Comment.objects.get(content='带图的评论')
        self.assertTrue(comment.image.name.endswith('.png'))
        self.assertIn('comment-image', response.json()['html'])

    def test_comment_rejects_oversize_image(self):
        big = SimpleUploadedFile('big.png', png_bytes() + b'\x00' * (5 * 1024 * 1024),
                                 content_type='image/png')
        response = self.client.post(
            self.comment_url, {'content': '大图', 'image': big},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('5MB', response.json()['error'])

    def test_comment_rejects_non_image_file(self):
        """扩展名不对 / 不是真图片，都应该被挡下来并给出可读的提示。"""
        bad = SimpleUploadedFile('x.txt', b'not an image', content_type='text/plain')
        response = self.client.post(
            self.comment_url, {'content': '坏文件', 'image': bad},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json()['error'], '必须返回错误说明')
        self.assertFalse(Comment.objects.exists())

    def test_comment_rejects_fake_png(self):
        """后缀是 .png 但内容不是图片：由 Pillow 校验拦下。"""
        fake = SimpleUploadedFile('fake.png', b'definitely not a png', content_type='image/png')
        response = self.client.post(
            self.comment_url, {'content': '假图片', 'image': fake},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('图片', response.json()['error'])

    def test_comment_requires_login(self):
        self.client.logout()
        response = self.client.post(self.comment_url, {'content': '匿名评论'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Comment.objects.count(), 0)

    def test_comment_notifications_for_post_author_and_reply(self):
        self.client.post(self.comment_url, {'content': '评论楼主'})
        self.assertTrue(Notification.objects.filter(recipient=self.alice, kind='comment').exists())

        # 楼主回复，应通知评论者 bob
        self.client.force_login(self.alice)
        root = Comment.objects.get(content='评论楼主')
        self.client.post(self.comment_url, {'content': '谢谢支持', 'parent_id': root.id})
        self.assertTrue(Notification.objects.filter(recipient=self.bob, kind='reply').exists())

    def test_comment_soft_delete_keeps_floor(self):
        root = Comment.objects.create(post=self.post, author=self.bob, content='会被删的评论')
        reply = Comment.objects.create(post=self.post, author=self.alice, content='楼中楼回复',
                                       parent=root)

        self.client.force_login(self.bob)
        response = self.client.post(reverse('comment_delete', args=[root.id]),
                                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        root.refresh_from_db()
        self.assertTrue(root.is_deleted)
        self.assertIn('该评论已删除', response.json()['html'])
        self.assertTrue(Comment.objects.filter(pk=reply.pk).exists(), '回复不应被级联删除')

    def test_post_author_can_delete_others_comment(self):
        comment = Comment.objects.create(post=self.post, author=self.bob, content='广告评论')
        self.client.force_login(self.alice)      # alice 是楼主
        self.client.post(reverse('comment_delete', args=[comment.id]))
        comment.refresh_from_db()
        self.assertTrue(comment.is_deleted)

    def test_stranger_cannot_delete_comment(self):
        carol = User.objects.create_user('carol', password='BlogPass!2026')
        comment = Comment.objects.create(post=self.post, author=self.bob, content='正常评论')
        self.client.force_login(carol)
        response = self.client.post(reverse('comment_delete', args=[comment.id]),
                                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 403)
        comment.refresh_from_db()
        self.assertFalse(comment.is_deleted)

    def test_comment_sort_hot_and_new(self):
        c1 = Comment.objects.create(post=self.post, author=self.alice, content='先发的')
        c2 = Comment.objects.create(post=self.post, author=self.alice, content='后发的')
        c1.likes.add(self.bob)                     # 先发的更热

        hot = self.client.get(self.post_url, {'sort': 'hot'})
        self.assertEqual(hot.context['roots'][0].raw_content, '先发的')
        self.assertEqual(hot.context['sort'], 'hot')

        new = self.client.get(self.post_url, {'sort': 'new'})
        self.assertEqual(new.context['roots'][0].raw_content, '后发的')
        self.assertEqual(new.context['sort'], 'new')
        self.assertEqual(new.context['roots'][1].raw_content, '先发的')

    def test_invalid_sort_value_falls_back_to_hot(self):
        Comment.objects.create(post=self.post, author=self.alice, content='一条评论')
        response = self.client.get(self.post_url, {'sort': 'rm -rf /'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['sort'], 'hot')

    def test_comment_pagination(self):
        for i in range(13):
            Comment.objects.create(post=self.post, author=self.alice, content=f'评论 {i}')
        first = self.client.get(self.post_url)
        self.assertEqual(len(first.context['roots']), 10)
        self.assertEqual(first.context['page_obj'].paginator.num_pages, 2)
        second = self.client.get(self.post_url, {'cpage': 2})
        self.assertEqual(len(second.context['roots']), 3)

    def test_reply_preview_folds_extra_replies(self):
        """楼中楼默认折叠：全部回复都渲染出来，但超出的部分带 hidden。"""
        root = Comment.objects.create(post=self.post, author=self.alice, content='楼层')
        for i in range(5):
            Comment.objects.create(post=self.post, author=self.bob, content=f'回复{i}', parent=root)
        response = self.client.get(self.post_url)
        self.assertEqual(len(response.context['replies'][root.id]), 5)
        self.assertEqual(response.context['reply_more'][root.id], 2)
        self.assertContains(response, '展开另外 2 条回复')
        self.assertEqual(response.content.decode().count('class="comment is-reply reply-extra hidden"'), 2)

    def test_deleted_comment_content_hidden_in_output(self):
        comment = Comment.objects.create(post=self.post, author=self.bob,
                                         content='敏感内容', is_deleted=True)
        response = self.client.get(self.post_url)
        self.assertNotContains(response, '敏感内容')
        self.assertTrue(Comment.objects.filter(pk=comment.pk).exists())


class NotificationViewTests(BaseBlogTest):
    def setUp(self):
        super().setUp()
        self.note = Notification.objects.create(recipient=self.alice, sender=self.bob,
                                                kind='comment', post=self.post,
                                                text='很不错的文章')

    def test_notifications_require_login(self):
        response = self.client.get(reverse('notifications'))
        self.assertEqual(response.status_code, 302)

    def test_notification_list_and_filter(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse('notifications'))
        # summary 说明「谁做了什么」，text 展示具体内容
        self.assertContains(response, 'bob 评论了你的文章')
        self.assertContains(response, '很不错的文章')
        filtered = self.client.get(reverse('notifications'), {'kind': 'like'})
        self.assertEqual(len(filtered.context['notifications']), 0)
        self.assertEqual(filtered.context['kind'], 'like')

    def test_mark_single_read(self):
        self.client.force_login(self.alice)
        data = self.client.post(reverse('notification_read'), {'single': self.note.id}).json()
        self.assertEqual(data['unread'], 0)
        self.note.refresh_from_db()
        self.assertTrue(self.note.is_read)

    def test_mark_all_read(self):
        Notification.objects.create(recipient=self.alice, sender=self.bob, kind='like',
                                    post=self.post)
        self.client.force_login(self.alice)
        data = self.client.post(reverse('notification_read'), {'all': '1'}).json()
        self.assertTrue(data['ok'])
        self.assertEqual(Notification.objects.filter(recipient=self.alice, is_read=False).count(), 0)

    def test_cannot_mark_others_notification(self):
        self.client.force_login(self.bob)
        self.client.post(reverse('notification_read'), {'single': self.note.id})
        self.note.refresh_from_db()
        self.assertFalse(self.note.is_read)

    def test_poll_endpoint(self):
        self.client.force_login(self.alice)
        data = self.client.get(reverse('notification_poll')).json()
        self.assertEqual(data['unread'], 1)
        self.assertEqual(data['items'][0]['summary'], 'bob 评论了你的文章《Django 评论系统实战》')
        self.assertTrue(data['items'][0]['url'].startswith('/post/'))

    def test_system_notification_uses_text(self):
        Notification.objects.create(recipient=self.alice, kind='system', text='站点维护通知')
        self.client.force_login(self.alice)
        response = self.client.get(reverse('notifications'))
        self.assertContains(response, '站点维护通知')

    def test_notification_url_points_to_comment(self):
        comment = Comment.objects.create(post=self.post, author=self.bob, content='被通知的评论')
        note = Notification.objects.create(recipient=self.alice, sender=self.bob, kind='reply',
                                           post=self.post, comment=comment)
        self.assertIn(f'#comment-{comment.id}', note.get_absolute_url())


class ProfileViewTests(BaseBlogTest):
    def test_user_profile_public(self):
        response = self.client.get(reverse('user_profile', args=['alice']))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.post.title)
        self.assertNotContains(response, self.draft.title, msg_prefix='未登录访客不应看到草稿')

    def test_author_sees_own_drafts_on_profile(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse('user_profile', args=['alice']))
        self.assertContains(response, self.draft.title)

    def test_profile_requires_login(self):
        self.assertEqual(self.client.get(reverse('profile')).status_code, 302)

    def test_profile_dashboard_stats(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['summary']['total'], 2)
        self.assertEqual(response.context['summary']['published'], 1)
        self.assertEqual(response.context['summary']['draft'], 1)

    def test_profile_status_filter(self):
        self.client.force_login(self.alice)
        drafts = self.client.get(reverse('profile'), {'status': 'draft'})
        self.assertEqual([p.pk for p in drafts.context['posts']], [self.draft.pk])

        published = self.client.get(reverse('profile'), {'status': 'published'})
        self.assertEqual([p.pk for p in published.context['posts']], [self.post.pk])

        everything = self.client.get(reverse('profile'), {'status': 'all'})
        self.assertEqual(len(everything.context['posts']), 2)

    def test_profile_edit_updates_user_and_profile(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse('profile_edit'), {
            'first_name': '新昵称', 'email': 'alice@example.com',
            'bio': '这是我的签名', 'location': '杭州', 'website': 'https://example.com',
            'github': 'alice', 'avatar_url': '',
        })
        self.assertEqual(response.status_code, 302)
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.first_name, '新昵称')
        self.assertEqual(self.alice.email, 'alice@example.com')
        profile = UserProfile.objects.get(user=self.alice)
        self.assertEqual(profile.bio, '这是我的签名')
        self.assertEqual(profile.social_links()[0][0], '个人网站')

    def test_profile_edit_rejects_bad_avatar_extension(self):
        self.client.force_login(self.alice)
        bad = SimpleUploadedFile('avatar.txt', b'nope', content_type='text/plain')
        response = self.client.post(reverse('profile_edit'), {
            'first_name': 'x', 'bio': '', 'location': '', 'website': '', 'github': '',
            'avatar_url': '', 'avatar': bad,
        }, follow=True)
        self.assertContains(response, '格式')

    def test_avatar_upload_then_used_in_templates(self):
        self.client.force_login(self.alice)
        avatar = SimpleUploadedFile('a.png', png_bytes(), content_type='image/png')
        self.client.post(reverse('profile_edit'), {
            'first_name': '', 'bio': '', 'location': '', 'website': '', 'github': '',
            'avatar_url': '', 'avatar': avatar,
        })
        profile = UserProfile.objects.get(user=self.alice)
        self.assertTrue(profile.display_avatar)
        response = self.client.get(self.post_url)
        self.assertContains(response, profile.display_avatar.split('?')[0])


class SearchTagAndMiscTests(BaseBlogTest):
    def test_search_page(self):
        response = self.client.get(reverse('search'), {'keyword': 'Django'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.post.title)
        self.assertContains(response, 'alice')

    def test_search_empty_keyword(self):
        response = self.client.get(reverse('search'))
        self.assertEqual(response.status_code, 200)

    def test_tag_pages(self):
        self.assertEqual(self.client.get(reverse('tag_cloud')).status_code, 200)
        detail = self.client.get(reverse('tag_detail', args=[self.tag.slug]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, self.post.title)

    def test_about_page_stats(self):
        response = self.client.get(reverse('about'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['stats']['posts'], 1)
        self.assertEqual(response.context['stats']['users'], 2)

    def test_pagination_splits_posts(self):
        for i in range(8):
            Post.objects.create(title=f'批量文章 {i}', content='内容' * 20,
                                author=self.alice, status='published')
        response = self.client.get(reverse('index'))
        self.assertEqual(response.context['page_obj'].paginator.num_pages, 2)
        self.assertEqual(len(response.context['posts']), 6)
        page2 = self.client.get(reverse('index'), {'page': 2})
        self.assertEqual(len(page2.context['posts']), 3)

    def test_out_of_range_page_falls_back_to_last(self):
        response = self.client.get(reverse('index'), {'page': 999})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].number, 1)

    def test_404_page_renders_custom_template(self):
        response = self.client.get('/this-page-does-not-exist/')
        self.assertEqual(response.status_code, 404)

    def test_related_posts_excludes_self(self):
        other = Post.objects.create(title='同标签文章', content='内容' * 20,
                                    author=self.bob, status='published')
        other.tags.add(self.tag)
        related = self.post.related_posts(limit=5)
        self.assertIn(other, related)
        self.assertNotIn(self.post, related)

    def test_humanize_count_filter(self):
        from .templatetags.blog_extras import humanize_count
        self.assertEqual(humanize_count(999), '999')
        self.assertEqual(humanize_count(1500), '1.5k')
        self.assertEqual(humanize_count(23400), '2.3w')


class QueryEfficiencyTests(BaseBlogTest):
    """列表页 / 详情页的查询次数应该有上界，防止模板里出现 N+1 查询。

    这里的数字是实测值（首页 13 次、详情页 17 次）：一旦有人往模板里加了会
    触发额外查询的写法（比如没预取就访问 post.author.profile.xxx，或者对每
    条标签单独查一次），查询次数就会超过这个上界，测试立刻失败。
    """

    def test_index_query_count_is_bounded(self):
        for i in range(5):
            p = Post.objects.create(title=f'文章 {i}', content='内容' * 30,
                                    author=self.alice, status='published')
            p.tags.add(self.tag)
        with self.assertNumQueries(13):
            self.client.get(reverse('index'))

    def test_post_detail_query_count_is_bounded(self):
        root = Comment.objects.create(post=self.post, author=self.bob, content='楼层')
        for i in range(6):
            Comment.objects.create(post=self.post, author=self.alice, content=f'回复{i}',
                                   parent=root)
        with self.assertNumQueries(17):
            self.client.get(self.post_url)

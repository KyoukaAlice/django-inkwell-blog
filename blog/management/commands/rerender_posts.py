"""重建文章正文的 Markdown 渲染缓存。

正文的渲染结果会缓存在 Post.rendered_content 里，只有正文被修改
（updated 时间变了）才会重新渲染。如果升级了 Markdown / Pygments，
或者改了 markdown_utils 里的渲染规则，历史文章仍是旧结果，需要跑一次：

    python manage.py rerender_posts
"""
from django.core.management.base import BaseCommand

from blog.models import Post


class Command(BaseCommand):
    help = '清空并重建所有文章的 Markdown 渲染缓存'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='只统计数量，不真正重建')

    def handle(self, *args, **options):
        total = Post.objects.count()
        if options['dry_run']:
            self.stdout.write(f'共有 {total} 篇文章需要重建（dry-run，未执行）')
            return

        self.stdout.write(f'开始重建 {total} 篇文章的渲染缓存…')
        rebuilt = 0
        for post in Post.objects.all():
            # 直接调用 render_content() 而不是 html_content 属性，
            # 避免命中缓存；渲染完再把结果和 updated 时间一起写回去。
            html = post.render_content()
            Post.objects.filter(pk=post.pk).update(
                rendered_content=html, rendered_at=post.updated,
            )
            rebuilt += 1

        self.stdout.write(self.style.SUCCESS(f'已重建 {rebuilt} 篇文章的渲染缓存'))

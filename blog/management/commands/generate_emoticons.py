"""生成评论表情 SVG 图标（每个表情一个文件，放在 static/img/emoticons/）。

表情图案用系统 emoji 字体绘制：SVG 里放 <text>，浏览器渲染时使用本机彩色
emoji 字体，因此文件很小而且清晰。运行一次即可：

    python manage.py generate_emoticons
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from blog.markdown_utils import EMOTICONS

SVG_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 36" width="36" height="36" '
    'role="img" aria-label="{name}">'
    '<text x="18" y="27" font-size="28" text-anchor="middle" '
    'font-family="Apple Color Emoji,Segoe UI Emoji,Noto Color Emoji,sans-serif">{emoji}</text>'
    '</svg>'
)


class Command(BaseCommand):
    help = '生成评论表情 SVG 图标到 static/img/emoticons/'

    def handle(self, *args, **options):
        target = Path(settings.BASE_DIR) / 'static' / 'img' / 'emoticons'
        target.mkdir(parents=True, exist_ok=True)
        count = 0
        for code, (emoji, name) in EMOTICONS.items():
            path = target / f'{code}.svg'
            path.write_text(
                SVG_TEMPLATE.format(emoji=emoji, name=name),
                encoding='utf-8',
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f'已生成 {count} 个表情文件 -> {target}'))

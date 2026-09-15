"""Markdown 渲染与表情工具。

* render_markdown(): Markdown -> 安全 HTML（fenced code + 代码高亮 + 表格 + 目录锚点）
* EMOTICONS: 评论表情码表，前端表情面板与后端渲染共用同一份定义
"""
import re

import bleach
import markdown as md
from bleach.css_sanitizer import CSSSanitizer
from django.utils.html import escape


def _slugify(value, separator=None):
    """Toc 锚点：保留中文，只把空白与符号换成短横线。"""
    value = re.sub(r'[^\w\u4e00-\u9fff\s-]', '', value, flags=re.U).strip().lower()
    return re.sub(r'[\s-]+', '-', value) or 'section'

# ---------------------------------------------------------------------------
# 评论表情：code -> (展示字符, 名称)
# ---------------------------------------------------------------------------
EMOTICONS = {
    'smile': ('😄', '微笑'),
    'grin': ('😁', '大笑'),
    'joy': ('😂', '笑哭'),
    'wink': ('😉', '眨眼'),
    'heart_eyes': ('😍', '花痴'),
    'kiss': ('😘', '飞吻'),
    'thinking': ('🤔', '思考'),
    'neutral': ('😐', '无语'),
    'cry': ('😭', '大哭'),
    'sob': ('😢', '流泪'),
    'anger': ('😡', '生气'),
    'scream': ('😱', '惊吓'),
    'sleep': ('😴', '睡觉'),
    'cool': ('😎', '酷'),
    'sweat': ('😅', '汗'),
    'vomit': ('🤮', '吐血'),
    'dizzy': ('😵', '晕'),
    'clap': ('👏', '鼓掌'),
    'thumbsup': ('👍', '赞'),
    'thumbsdown': ('👎', '踩'),
    'ok': ('👌', '好的'),
    'pray': ('🙏', '祈祷'),
    'muscle': ('💪', '加油'),
    'heart': ('❤️', '爱心'),
    'broken_heart': ('💔', '心碎'),
    'star': ('⭐', '星星'),
    'fire': ('🔥', '火'),
    'tada': ('🎉', '庆祝'),
    'rocket': ('🚀', '火箭'),
    'crown': ('👑', '牛'),
    'doge': ('🐶', 'doge'),
    'cat': ('🐱', '猫'),
    'ghost': ('👻', '幽灵'),
    'alien': ('👽', '外星人'),
    'poop': ('💩', '便便'),
    'beer': ('🍺', '啤酒'),
    'cake': ('🎂', '蛋糕'),
    'gift': ('🎁', '礼物'),
}

EMOTICON_PATTERN = re.compile(r'\[em:([a-z_]+)\]')
EMOJI_ONLY_PATTERN = re.compile(
    r'^(?:[\s\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]+)$'
)


def render_emoticon_codes(text: str) -> str:
    """把 [em:code] 转成 <img>，供评论/文章正文渲染复用。"""
    def _repl(match):
        code = match.group(1)
        if code not in EMOTICONS:
            return match.group(0)
        emoji, name = EMOTICONS[code]
        return (f'<img class="emoticon" src="/static/img/emoticons/{code}.svg" '
                f'alt="{escape(emoji)}" title="{escape(name)}">')

    return EMOTICON_PATTERN.sub(_repl, text)


def is_emoji_only(text: str) -> bool:
    """判断内容是否只有表情（B 站这类评论会放大显示）。"""
    stripped = EMOTICON_PATTERN.sub('', text).strip()
    if not stripped:
        return bool(text.strip())
    return bool(EMOJI_ONLY_PATTERN.match(stripped))


# ---------------------------------------------------------------------------
# Markdown 渲染
# ---------------------------------------------------------------------------
_ALLOWED_TAGS = [
    'p', 'br', 'hr', 'strong', 'b', 'em', 'i', 'u', 's', 'del', 'ins', 'mark', 'sub', 'sup', 'small',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li', 'dl', 'dt', 'dd',
    'blockquote', 'pre', 'code', 'span', 'div',
    'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td',
    'a', 'img', 'figure', 'figcaption', 'input',
]
_ALLOWED_ATTRS = {
    '*': ['class', 'id', 'title'],
    'a': ['href', 'title', 'rel', 'target'],
    'img': ['src', 'alt', 'title', 'class', 'loading'],
    'input': ['type', 'checked', 'disabled'],
    'td': ['align', 'colspan', 'rowspan'],
    'th': ['align', 'colspan', 'rowspan'],
}
_ALLOWED_PROTOCOLS = ['http', 'https', 'mailto', 'data']

_MD_EXTENSIONS = [
    'extra',                      # 表格 / 脚注 / 属性列表 / fenced_code 等一整套
    'sane_lists',
    'nl2br',                      # 单个换行也当成 <br>，写中文更顺手
    'admonition',
    # 注意：markdown.markdown(extensions=[...]) 只接受「扩展名字符串」，
    # 传扩展类实例不会报错但也不会生效（代码块会退化成一段普通文本）。
    # 需要参数时用下面的 extension_configs 传。
    'fenced_code',
    'codehilite',
    'toc',
    'tables',
]

_MD_EXTENSION_CONFIGS = {
    'codehilite': {
        'css_class': 'codehilite',
        'guess_lang': False,      # 没写语言就不猜，避免误标颜色
        'linenums': False,
    },
    'toc': {
        'permalink': True,        # 标题后面加一个可点击的锚点
        'slugify': _slugify,
    },
}

_CSS_SANITIZER = CSSSanitizer(allowed_css_properties=[
    'color', 'background', 'background-color', 'text-align', 'width', 'height',
    'font-weight', 'font-style', 'padding', 'margin', 'border', 'border-radius',
])


def render_markdown(text: str) -> str:
    """渲染 Markdown 并用 bleach 白名单过滤，输出可直接放进模板的安全 HTML。"""
    if not text:
        return ''
    html = md.markdown(
        text,
        extensions=_MD_EXTENSIONS,
        extension_configs=_MD_EXTENSION_CONFIGS,
        output_format='html5',
    )
    cleaned = bleach.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        protocols=_ALLOWED_PROTOCOLS,
        css_sanitizer=_CSS_SANITIZER,
        strip=True,
    )
    # 外链加 noopener，防止 tabnabbing
    cleaned = cleaned.replace('<a href="http', '<a rel="noopener noreferrer" target="_blank" href="http')
    # 表情码
    cleaned = render_emoticon_codes(cleaned)
    return cleaned


def plain_text(text: str, limit: int = 120) -> str:
    """从 Markdown 里抽取纯文本，用于通知摘要、SEO 描述等。"""
    if not text:
        return ''
    text = re.sub(r'```.*?```', ' ', text, flags=re.S)
    text = re.sub(r'!?\[[^\]]*\]\([^)]*\)', ' ', text)
    text = re.sub(r'[#>*`_~]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:limit] + ('…' if len(text) > limit else '')

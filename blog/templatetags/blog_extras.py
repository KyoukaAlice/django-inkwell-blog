"""模板过滤器与标签：数字格式化、Markdown 渲染、相对时间、分页链接。"""
from django import template
from django.http import QueryDict
from django.utils.html import escape
from django.utils.safestring import mark_safe

from ..markdown_utils import render_emoticon_codes, render_markdown

register = template.Library()


@register.filter
def humanize_count(value):
    """1234 -> 1.2k，10000 -> 1w（B 站风格的数字显示）。"""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return value
    if number < 1000:
        return str(number)
    if number < 10000:
        return f'{number / 1000:.1f}'.rstrip('0').rstrip('.') + 'k'
    return f'{number / 10000:.1f}'.rstrip('0').rstrip('.') + 'w'


@register.filter
def markdownify(text):
    """把 Markdown 文本渲染成安全 HTML。"""
    return mark_safe(render_markdown(text))


@register.filter
def emoticons(text):
    """把纯文本里的 [em:xx] 转成表情图片（用于通知摘要等）。"""
    return mark_safe(render_emoticon_codes(escape(text)).replace('\n', '<br>'))


@register.filter
def time_ago(value):
    """相对时间：刚刚 / 5 分钟前 / 3 天前 / 具体日期。"""
    from django.utils import timezone
    if not value:
        return ''
    seconds = (timezone.now() - value).total_seconds()
    if seconds < 60:
        return '刚刚'
    if seconds < 3600:
        return f'{int(seconds // 60)} 分钟前'
    if seconds < 86400:
        return f'{int(seconds // 3600)} 小时前'
    if seconds < 86400 * 7:
        return f'{int(seconds // 86400)} 天前'
    if seconds < 86400 * 30:
        return f'{int(seconds // 86400 // 7)} 周前'
    return value.strftime('%Y-%m-%d')


@register.filter
def percentage(part, whole):
    """百分比数值，用于个人中心的数据条。"""
    try:
        whole = int(whole)
        if whole <= 0:
            return 0
        return round(int(part) * 100 / whole)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.filter
def get_item(mapping, key):
    """模板里按键取值：{{ replies|get_item:comment.id }}"""
    if hasattr(mapping, 'get'):
        return mapping.get(key)
    return None


@register.simple_tag(takes_context=True)
def url_replace(context, reset_page=False, **kwargs):
    """在当前 URL 的查询参数基础上替换 / 删除参数，生成新链接。

    用法::

        {% url_replace page=3 %}            {# 翻页，保留筛选条件 #}
        {% url_replace sort='hot' reset_page=True %}   {# 切换排序并回到第 1 页 #}
        {% url_replace category='' %}       {# 传空值表示删除该参数 #}
    """
    request = context.get('request')
    query = request.GET.copy() if request is not None else QueryDict(mutable=True)
    query._mutable = True
    if reset_page:
        query.pop('page', None)
    for key, value in kwargs.items():
        if value is None or value == '':
            query.pop(key, None)
        else:
            query[key] = value
    encoded = query.urlencode()
    return f'?{encoded}' if encoded else '?'

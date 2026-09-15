"""表单定义：文章、评论、用户资料、注册。"""
import re

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import Comment, Post, Tag, UserProfile
from .markdown_utils import EMOTICONS, is_emoji_only

TAG_SPLIT_PATTERN = re.compile(r'[,，\s]+')


class TagWidget(forms.TextInput):
    """标签输入框：接受逗号 / 空格分隔的多个标签。"""


class TagField(forms.Field):
    """把 "Python, Django 毕业设计" 这样的字符串转成 Tag 对象列表。"""

    widget = TagWidget
    default_error_messages = {'max_tags': '最多只能添加 %(limit)d 个标签。'}

    def __init__(self, max_tags=6, *args, **kwargs):
        self.max_tags = max_tags
        kwargs.setdefault('required', False)
        kwargs.setdefault('label', '标签')
        kwargs.setdefault('help_text', '用逗号或空格分隔，例如：Python, Django, 毕业设计')
        super().__init__(*args, **kwargs)

    def prepare_value(self, value):
        """编辑文章时把已有关联的标签回填到输入框。"""
        if isinstance(value, str):
            return value
        if value is None:
            return ''
        names = getattr(value, 'all', None)
        if callable(names):
            return ', '.join(tag.name for tag in value.all())
        return ', '.join(str(item) for item in value)

    def to_python(self, value):
        if not value:
            return []
        names, seen = [], set()
        for raw in TAG_SPLIT_PATTERN.split(str(value).strip()):
            name = raw.strip()[:40]
            if name and name.lower() not in seen:
                seen.add(name.lower())
                names.append(name)
        if len(names) > self.max_tags:
            raise forms.ValidationError(
                self.error_messages['max_tags'], code='max_tags',
                params={'limit': self.max_tags},
            )
        tags = []
        for name in names:
            tag, _ = Tag.objects.get_or_create(name=name)
            tags.append(tag)
        return tags


class AvatarPreviewWidget(forms.ClearableFileInput):
    """带当前图片预览的文件控件。"""
    template_name = 'blog/widgets/clearable_file_input.html'


class PostForm(forms.ModelForm):
    """发布 / 编辑文章。正文支持 Markdown。"""

    tags_input = TagField()

    class Meta:
        model = Post
        fields = ['title', 'excerpt', 'content', 'category', 'cover', 'status']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': '起一个吸引人的标题…', 'maxlength': 200,
            }),
            'excerpt': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': '摘要（可选，不填会自动从正文截取）',
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control markdown-editor', 'rows': 18,
                'placeholder': '正文支持 Markdown 语法：\n\n## 二级标题\n**加粗** *斜体* `行内代码`\n\n```python\nprint("hello")\n```\n\n> 引用\n- 列表项',
            }),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'cover': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }
        labels = {'cover': '封面图'}
        help_texts = {'cover': '可选，建议 16:9 比例的图片，会显示在文章列表卡片上。'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].required = False
        self.fields['category'].empty_label = '— 未分类 —'
        if self.instance.pk:
            self.fields['tags_input'].initial = ', '.join(
                self.instance.tags.values_list('name', flat=True)
            )

    def clean_title(self):
        title = self.cleaned_data['title'].strip()
        if len(title) < 2:
            raise forms.ValidationError('标题至少 2 个字。')
        return title

    def clean_content(self):
        content = self.cleaned_data['content'].strip()
        if len(content) < 10:
            raise forms.ValidationError('正文太短了，至少写 10 个字吧。')
        return content

    def save(self, commit=True):
        post = super().save(commit=commit)
        # 只有落到数据库（有主键）之后才能写多对多标签。
        # 视图里的流程是 save(commit=False) -> 补作者 -> save() -> save()，
        # 所以这里必须判断 post.pk，否则会报「needs to have a value for field id」。
        if post.pk:
            post.tags.set(self.cleaned_data.get('tags_input') or [])
            Post.objects.filter(pk=post.pk).update(rendered_content='', rendered_at=None)
        return post


class CommentForm(forms.ModelForm):
    """评论表单：楼中楼（parent_id）、表情、配图。"""

    parent_id = forms.IntegerField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = Comment
        fields = ['content', 'image', 'parent_id']
        widgets = {
            'content': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': '发一条友善的评论吧～ 支持 [em:smile] 表情码',
                'class': 'comment-input',
                'maxlength': 1000,
            }),
            'image': forms.ClearableFileInput(attrs={'class': 'comment-image-input', 'accept': 'image/*'}),
        }
        labels = {'content': '', 'image': ''}

    def __init__(self, *args, user=None, post=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.post = post
        self.fields['image'].required = False
        # 内容是否必填由 clean() 判断：只发图片不写字也是合法评论
        self.fields['content'].required = False

    def clean_content(self):
        content = (self.cleaned_data.get('content') or '').strip()
        if len(content) > 1000:
            raise forms.ValidationError('评论最多 1000 个字。')
        return content

    def clean(self):
        cleaned = super().clean()
        # 校验顺序很重要：先查「内容 / 目标是否合法」，最后才查频率，
        # 否则一个非法的 parent_id 会被误报成「发言太快」，让人摸不着头脑。
        if not cleaned.get('content') and not self.files.get('image'):
            raise forms.ValidationError('评论内容不能为空。')

        # 回复必须指向同一篇文章下的评论（不能跨文章回复）
        parent_id = cleaned.get('parent_id')
        if parent_id and self.post:
            parent = Comment.objects.filter(pk=parent_id, post=self.post).first()
            if parent is None:
                raise forms.ValidationError('要回复的评论不存在。')
            cleaned['parent'] = parent
        else:
            cleaned['parent'] = None

        # 频率限制：同一用户 15 秒内只能发一条评论，防止刷屏
        if self.user and self.user.is_authenticated:
            recent = Comment.objects.filter(
                author=self.user, created__gte=timezone.now() - timezone.timedelta(seconds=15)
            ).exists()
            if recent:
                raise forms.ValidationError('发言太快啦，休息 15 秒再评论吧～')
        return cleaned

    @property
    def is_emoji_only(self):
        return is_emoji_only(self.cleaned_data.get('content', '') if self.is_valid() else '')


class ProfileForm(forms.ModelForm):
    """编辑个人资料（同时改 User 的邮箱与 Profile 的字段）。"""

    email = forms.EmailField(required=False, label='邮箱',
                             widget=forms.EmailInput(attrs={'class': 'form-control'}))
    first_name = forms.CharField(required=False, max_length=30, label='昵称',
                                 widget=forms.TextInput(attrs={'class': 'form-control',
                                                               'placeholder': '显示在文章与评论里'}))

    class Meta:
        model = UserProfile
        fields = ['avatar', 'avatar_url', 'bio', 'location', 'website', 'github']
        widgets = {
            'avatar': AvatarPreviewWidget(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'avatar_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://…'}),
            'bio': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 200,
                                          'placeholder': '一句话介绍自己'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '例如：浙江 杭州'}),
            'website': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://…'}),
            'github': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'GitHub 用户名'}),
        }
        labels = {'avatar': '上传头像', 'avatar_url': '头像外链', 'bio': '个性签名',
                  'location': '所在地', 'website': '个人网站', 'github': 'GitHub'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['email'].initial = self.instance.user.email
            self.fields['first_name'].initial = self.instance.user.first_name

    def save(self, commit=True):
        profile = super().save(commit=commit)
        if commit:
            user = profile.user
            user.email = self.cleaned_data.get('email', '') or ''
            user.first_name = self.cleaned_data.get('first_name', '') or ''
            user.save(update_fields=['email', 'first_name'])
        return profile


class RegisterForm(UserCreationForm):
    """注册表单：美化过的字段与中文提示。"""

    email = forms.EmailField(required=False, label='邮箱（可选）',
                             widget=forms.EmailInput(attrs={'placeholder': 'you@example.com'}))

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            'username': '3-150 个字符，字母 / 数字 / @ . + - _',
            'password1': '至少 8 位，别用纯数字',
            'password2': '请再次输入密码',
        }
        for name, placeholder in placeholders.items():
            self.fields[name].widget.attrs.update({'placeholder': placeholder, 'class': 'form-control'})
        if 'email' in self.fields:
            self.fields['email'].widget.attrs.update({'class': 'form-control'})
        self.fields['username'].label = '用户名'
        self.fields['password1'].label = '密码'
        self.fields['password2'].label = '确认密码'

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data.get('email', '') or ''
        if commit:
            user.save()
            # 顺序问题：UserProfile 由信号创建，这里补一次保证一定存在
            UserProfile.objects.get_or_create(user=user)
        return user


class AdminNotificationForm(forms.Form):
    """后台群发系统通知用的简单表单（管理员在站点里发公告）。"""
    text = forms.CharField(max_length=200, label='通知内容',
                           widget=forms.TextInput(attrs={'class': 'form-control'}))

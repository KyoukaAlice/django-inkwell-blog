"""
URL configuration for DjangoBlog project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import os

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve as static_serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('blog.urls')),  # 博客应用的路由
]

# ---------------------------------------------------------------------------
# 静态文件与媒体文件服务
#
# 这个项目默认 DEBUG=False，而 django.contrib.staticfiles 只在 DEBUG=True 时
# 自动提供静态文件 —— 结果就是 /static/css/style.css 直接 404，页面完全没有样式。
# 所以这里显式挂两条路由，让开发 / 答辩演示时 Django 自己把文件发出去。
#
# 正式部署（Nginx / Apache）应该把这两条交给 Web 服务器处理，
# 并删掉下面的 STATIC_SERVE_BY_DJANGO 开关，或者设置环境变量关闭它。
# ---------------------------------------------------------------------------
STATIC_SERVE_BY_DJANGO = os.environ.get('DJANGO_SERVE_STATIC', '1') == '1'

if STATIC_SERVE_BY_DJANGO:
    # 开发时先看 STATICFILES_DIRS（改完 CSS 立刻生效，不用 collectstatic），
    # 找不到再回退到 collectstatic 的产物 STATIC_ROOT。
    urlpatterns += [
        re_path(r'^static/(?P<path>.*)$', static_serve, {'document_root': settings.STATIC_ROOT}),
    ]
    for _static_dir in reversed(getattr(settings, 'STATICFILES_DIRS', [])):
        urlpatterns.insert(0, re_path(
            r'^static/(?P<path>.*)$', static_serve, {'document_root': _static_dir},
        ))

# 媒体文件（用户上传的头像、封面、评论配图）
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', static_serve, {'document_root': settings.MEDIA_ROOT}),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# 自定义错误页
handler404 = 'blog.views.page_not_found'
handler500 = 'blog.views.server_error'

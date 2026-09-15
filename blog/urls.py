from django.urls import path

from . import views

urlpatterns = [
    # 首页 / 搜索 / 关于
    path('', views.index, name='index'),
    path('search/', views.search, name='search'),
    path('about/', views.about, name='about'),

    # 认证
    path('register/', views.register, name='register'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),

    # 用户
    path('profile/', views.profile, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('u/<str:username>/', views.user_profile, name='user_profile'),

    # 文章
    path('post/create/', views.post_create, name='post_create'),
    path('post/<int:post_id>/', views.post_detail, name='post_detail'),
    path('post/<int:post_id>/edit/', views.post_edit, name='post_edit'),
    path('post/<int:post_id>/delete/', views.post_delete, name='post_delete'),
    path('post/<int:post_id>/toggle-status/', views.toggle_post_status, name='toggle_post_status'),

    # 文章互动（AJAX）
    path('post/<int:post_id>/vote/', views.post_vote, name='post_vote'),
    path('post/<int:post_id>/bookmark/', views.post_bookmark, name='post_bookmark'),

    # 评论
    path('post/<int:post_id>/comment/', views.comment_create, name='comment_create'),
    path('comment/<int:comment_id>/delete/', views.comment_delete, name='comment_delete'),
    path('comment/<int:comment_id>/like/', views.comment_like, name='comment_like'),

    # 标签
    path('tags/', views.tag_cloud, name='tag_cloud'),
    path('tag/<slug:slug>/', views.tag_detail, name='tag_detail'),

    # 站内通知
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/read/', views.notification_read, name='notification_read'),
    path('notifications/poll/', views.notification_poll, name='notification_poll'),
]

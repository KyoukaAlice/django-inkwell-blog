# DjangoBlog 改造说明

> 本次改造围绕三件事：**把评论系统做成 B 站那样**、**把界面整体美化一遍**、**补齐一个博客该有的功能**。
> 下面按「改了什么 → 怎么实现的 → 怎么跑起来 → 答辩可以怎么讲」的顺序说明。

---

## 目录

1. [一分钟跑起来（cmd 脚本）](#一分钟跑起来cmd-脚本)
2. [评论系统：从一级评论到 B 站式楼中楼](#一评论系统从一级评论到-b-站式楼中楼)
3. [界面美化：一套设计系统换掉 7 份重复 CSS](#二界面美化一套设计系统换掉-7-份重复-css)
4. [新增功能清单](#三新增功能清单)
5. [文件改动总览](#四文件改动总览)
6. [验证方式](#五验证方式)
7. [答辩可以讲的 8 个技术点](#六答辩可以讲的-8-个技术点)
8. [后续还能做什么](#七后续还能做什么)

---

## 一分钟跑起来（cmd 脚本）

项目自带 3 个 cmd 脚本，**双击就能用**，不需要手动敲一堆命令。

### 第一步：初始化环境（只需一次）

双击 **`setup_env.bat`**，或者想用 SQLite（不用装 MySQL）就运行：

```cmd
setup_env.bat sqlite
```

它会自动完成：

1. 找一个可用的 Python（支持 3.8 ~ 3.13，会优先用 `py` 启动器）
2. 在本目录创建虚拟环境 `.venv`
3. 升级 pip
4. 安装 `requirements.txt` 里的 7 个依赖
5. 建表（migrate）、生成 38 个评论表情 SVG、可选灌演示数据

参数：

| 命令 | 作用 |
| --- | --- |
| `setup_env.bat` | 创建环境，用 MySQL（读 `settings.py` 里的配置） |
| `setup_env.bat sqlite` | 同上，但用本地 SQLite，**不需要 MySQL** |
| `setup_env.bat demo` | 顺便灌演示数据（用户名 demo / alice / bob） |
| `setup_env.bat sqlite demo` | 两个都要 |

### 第二步：启动网站

双击 **`start.bat`**，或者：

```cmd
start.bat                  :: MySQL，127.0.0.1:8000
start.bat sqlite           :: 用 SQLite，不需要 MySQL
start.bat 8080             :: 换端口
start.bat 0.0.0.0:8000     :: 监听所有网卡（手机连同一个 WiFi 就能访问）
```

启动前它会先做一次**数据库连通性预检**。如果 MySQL 没启动，不会甩给你一长串
Django 报错，而是明确告诉你「改用 SQLite 还是去启动 MySQL」。
如果 `.venv` 不存在，它会自动先跑一遍 `setup_env.bat`。

### 第三步（可选）：跑管理命令

```cmd
manage.bat                          :: 列出所有可用命令
manage.bat migrate                  :: 应用数据库迁移
manage.bat createsuperuser          :: 创建管理员账号
manage.bat seed_demo                :: 灌演示数据
manage.bat seed_demo --reset        :: 清空博客数据后重建演示数据
manage.bat generate_emoticons       :: 重新生成评论表情
manage.bat rerender_posts           :: 重建 Markdown 渲染缓存
manage.bat test blog                :: 跑 88 个单元测试
manage.bat shell                    :: 交互式 Python shell
manage.bat sqlite migrate           :: 把 sqlite 放最前面 = 用 SQLite 执行
```

### 演示账号

`seed_demo`（或 `setup_env.bat demo`）会创建三个账号，密码都是 `BlogDemo!2026`：

| 账号 | 说明 |
| --- | --- |
| `demo` | 站长，同时是超级管理员，可以进 `/admin/` |
| `alice` | 普通用户 |
| `bob` | 普通用户 |

### 手动命令（不想用脚本时）

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py generate_emoticons
python manage.py runserver
```

### 数据库：默认 MySQL，可用环境变量切到 SQLite

`settings.py` 里的 MySQL 配置**保持原样**（`myblog_db` / `root` / 你原来的密码），
只多了一层环境变量开关。`start.bat sqlite` 做的事就是设好这个变量：

```cmd
:: 用 MySQL（默认，什么都不用设）
python manage.py runserver

:: 用本地 SQLite（数据库文件是 db.sqlite3）
set DB_ENGINE=sqlite
python manage.py runserver
```

其它可选环境变量：`DB_NAME` `DB_USER` `DB_PASSWORD` `DB_HOST` `DB_PORT` `DJANGO_DEBUG=1`。

> **重要**：本次改造新增了 2 个迁移文件（`0004` 结构、`0005` 数据回填）。
> 切到 MySQL 后要先执行 `python manage.py migrate`（或 `manage.bat migrate`），它会自动：
> 建新表（标签、用户资料、点赞、收藏、通知）、给老评论补上 `root`/`depth` 楼中楼字段、
> 给已有用户补建用户资料。**不会丢失任何已有数据。**

> **小提示**：`.venv/`、`db.sqlite3`、`media/`、`__pycache__/` 都已写进 `.gitignore`，
> 提交代码时不会被带上。

---

## 一、评论系统：从一级评论到 B 站式楼中楼

### 1.1 改造前 vs 改造后

| 能力 | 改造前 | 改造后 |
| --- | --- | --- |
| 回复层级 | 只能回复一级评论，第二层就渲染不出来了 | 楼中楼，任意深度自动压平到两级展示 |
| 评论点赞 | ✗ | ✓ 一人一赞，可取消，显示「xx 人觉得很赞」 |
| 表情 | ✗ | ✓ 38 个表情，`[em:smile]` 表情码，点面板插入 |
| 配图 | ✗ | ✓ 每条评论可带一张图（≤5MB，点开灯箱看大图） |
| 排序 | 只能按时间正序 | ✓ 最热 / 最新自由切换 |
| 分页 | ✗ 全部一次性渲染 | ✓ 每页 10 层楼，楼中楼折叠 |
| 删除 | 直接物理删除，楼层会塌 | ✓ 软删除，保留「该评论已删除」占位 |
| 刷新 | 每次提交整页跳转 | ✓ AJAX 局部刷新，不打断阅读 |
| 频率限制 | ✗ | ✓ 15 秒内只能发一条，防刷屏 |
| 权限 | 只能删自己的 | ✓ 评论作者 **或** 楼主都能删 |

### 1.2 核心：自关联 + root/depth 双字段

难点在于「回复的回复的回复」怎么存。如果只用一个 `parent` 自关联，
渲染时就得递归查数据库，层数一深就 N+1 爆炸。

改造后的设计：

```python
class Comment(models.Model):
    post   = models.ForeignKey(Post, related_name='comments', on_delete=models.CASCADE)
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    parent = models.ForeignKey('self', null=True, blank=True, related_name='replies')        # 直接回复谁
    root   = models.ForeignKey('self', null=True, blank=True, related_name='thread_comments')# 属于哪个楼层
    depth  = models.PositiveSmallIntegerField(default=0)                                     # 层级，最深 2
    is_deleted = models.BooleanField(default=False)                                          # 软删除
```

`root` 和 `depth` **不用视图层维护**，在 `Comment.save()` 里自动算出来：

```python
def save(self, *args, **kwargs):
    if self.parent_id:
        self.root_id = self.parent.root_id or self.parent_id
        self.depth = min(self.parent.depth + 1, self.MAX_DEPTH)   # MAX_DEPTH = 2
    else:
        self.root_id, self.depth = None, 0
    super().save(*args, **kwargs)
```

好处：

- 视图层只管「用户回复了谁」，结构问题由模型自己保证，不会写错；
- `depth` 压平到 2，无论用户回复多少层，界面永远只有「楼层 + 楼中楼」两级，不会缩进到看不见；
- 一次 `SELECT` 取回整篇文章的评论，在 Python 里组装成楼层树，**零递归查询**。

### 1.3 软删除：为什么不能真删

物理删除会带来两个问题：楼层号凭空消失（用户看到「#5 楼」不见了会以为出 bug）、
楼中楼的回复变成孤儿。

所以删除走软删除：

```python
comment.is_deleted = True
comment.content = '该评论已删除'
comment.image = None
comment.save(update_fields=['is_deleted', 'content', 'image'])
```

- 楼层占位保留，编号不乱；
- 楼中楼回复还在；
- 原文内容清空，不再展示；
- 后台可以「恢复显示」（`Admin` 里有两个 action）。

### 1.4 一次请求怎么组装出楼层树

`views._load_comment_page()` 是整个评论区的核心，流程是：

```
1. 一次查询取回该文章所有评论（select_related 作者/父评论/被回复人 + annotate 点赞数 + Prefetch 点赞用户）
2. 一次性取回所有评论作者的头像资料（避免每条评论查一次）
3. 在内存里按 root 分组成「楼层 -> 回复列表」
4. 楼层按 热度(点赞数 + 楼主加权) 或 时间 排序
5. 楼层分页（每页 10 层），楼中楼默认展示前 3 条，其余折叠
6. 转成 CommentNode 数据类，交给模板渲染
```

实测：**文章详情页总共 17 次查询**（含侧边栏、目录、相关文章、整棵评论树），
并且用测试用例把这个数字钉死了，谁改出 N+1 就会挂测试。

### 1.5 前端：AJAX 局部刷新 + 事件委托

- 评论区是一个整体容器 `<div id="comments" data-url="/post/2/">`，
  服务端把它单独渲染成 `partials/comment_list.html`；
- 发评论 / 删评论 / 点赞 / 排序 / 分页，都通过 `fetch` 请求，
  后端返回 `{ok, html, total}`，前端把 `html` 塞回容器 —— **不刷新页面**；
- 关键点：所有按钮的事件都绑在容器上用**事件委托**（`e.target.closest('.js-comment-like')`），
  否则容器内容被替换后，新渲染出来的按钮就点不动了；
- 评论点赞是「只改一个数字」，所以连 HTML 都不换，直接就地更新；
- 展开楼中楼也是纯前端行为：所有回复都渲染出来了，超出的加 `.reply-extra.hidden`，
  点「展开另外 N 条回复」只是把 `hidden` 去掉，不再请求服务器；
- **无 JS 兜底**：表单是标准的 `<form method="post">`，JS 挂了也能正常提交（只是会整页刷新）。

### 1.6 表情是怎么做的

不用图片资源包，而是「表情码 + 动态生成 SVG」：

- `markdown_utils.EMOTICONS` 是一份字典：`{'smile': ('😄', '微笑'), ...}`，共 38 个；
- `python manage.py generate_emoticons` 给每个表情生成一个 SVG（内部就是 `<text>` 放 emoji，
  浏览器用系统彩色 emoji 字体渲染），文件只有 260 字节左右；
- 用户输入 `[em:smile]` → 后端渲染成 `<img src=".../smile.svg">`；
- 前端表情面板点击后，把 `[em:xxx]` 插入到光标位置（`insertAtCursor`）；
- 如果一条评论**只有表情**，会自动放大显示（`is_emoji_only` → `.emoji-only`），跟 B 站一致。

### 1.7 顺手修掉的安全 / 体验问题

| 问题 | 处理 |
| --- | --- |
| 登录 `?next=` 可以跳转到站外（开放重定向） | 用 `url_has_allowed_host_and_scheme` 校验 |
| 评论配图可以传任意文件 | 扩展名白名单 + 5MB 上限 + Pillow 真伪校验 |
| 评论内容直接输出会被 XSS | 转义 HTML 后再替换表情码，绝不 `|safe` 用户输入 |
| 回复时可以指定别的文章的评论 id | 校验 `parent.post == post`，否则报错 |
| 空内容 / 超长内容 | 表单校验，最长 1000 字 |
| 评论表单报错顺序奇怪（非法 parent 报「发言太快」） | 调整校验顺序：先校验内容与目标，再查频率 |

---

## 二、界面美化：一套设计系统换掉 7 份重复 CSS

### 2.1 改造前的样子

7 个模板每个都内嵌一份完整的 `<style>`，导航栏、页脚、卡片样式复制了 7 遍，
颜色写死（`#667eea`、`#f5f7fa` 散落各处），想换个配色得改 7 个文件。

### 2.2 改造后：CSS 变量 + 模板继承

- **`static/css/style.css`（约 1100 行）**：唯一的样式表，所有颜色 / 圆角 / 阴影 / 间距
  都用 CSS 变量定义在 `:root` 里，改一处全局生效；
- **`templates/blog/base.html`**：唯一的页面骨架（顶栏 + 内容区 + 侧边栏 + 页脚 + 消息提示），
  其余页面全部 `{% extends 'blog/base.html' %}`，只写自己的内容块；
- **组件化 partial**：文章卡片、分页、头像、侧边栏、通知面板、单条评论
  都是独立模板，用 `{% include %}` 复用。

### 2.3 具体美化了什么

**整体**

- 统一的蓝紫渐变配色（品牌色 `#0aa7e0` + 强调色 `#fb7299`），告别土味纯色；
- 顶部导航吸顶 + 毛玻璃背景（`backdrop-filter`），滚动时内容从下方透出；
- 全站响应式：>1000px 双栏、<1000px 单栏、<720px 卡片改成竖排，手机端汉堡菜单；
- 圆角、阴影、过渡动画统一（`--radius` / `--shadow` / `--fast`），不再是「每块都不太一样」。

**深色模式**

- 右上角一键切换，`html[data-theme="dark"]` 重新定义整套变量，全站立即变深色；
- 选择会存到 `localStorage`；首次访问跟随系统 `prefers-color-scheme`；
- 在 `<head>` 里**提前**执行主题脚本，避免深色模式下先闪一下白屏。

**页面级**

| 页面 | 美化点 |
| --- | --- |
| 首页 | 文章卡片带封面图（悬停微微放大）、作者头像 + 阅读时长、标签 chips、悬浮上移 |
| 文章详情 | 阅读进度条、自动生成目录（滚动高亮当前小节）、作者名片、相关文章、Markdown 专业排版 |
| 评论区 | 见上文，B 站式布局 + 圆形头像 + 楼层号 + UP 主徽章 + 爱心点赞 |
| 登录/注册 | 独立渐变背景 + 悬浮卡片，不再和主站共用一套样式 |
| 写文章 | 左侧编辑器 + 右侧固定设置栏（状态/分类/标签/封面/Markdown 速查），Ctrl+S 保存 |
| 个人中心 | 数据概览大数字、渐变数据条、文章管理（编辑/切换状态/删除） |
| 用户主页 | 渐变横幅 + 大头像 + 统计栏 + 文章/收藏 Tab |
| 通知中心 | 类型 Tab + 未读高亮 + 图标 + 无刷新标记已读 |
| 关于页 | 渐变 Hero + 六宫格大数字统计 + 排行榜 |
| 404/500 | 友好插画式空状态 + 快捷入口 |
| 侧边栏 | 站点数据、热门文章排行（前三名金银铜牌配色）、热门标签云、分类导航 |

**细节**

- 所有图标是内联 SVG（feather 风格），不依赖任何图标库 CDN，断网也能正常显示；
- 表情、提示条、点赞、收藏都有微动画；`prefers-reduced-motion` 下自动关闭动效；
- 图片灯箱（点评论配图 / 正文图片放大看）；
- 打印样式：打印文章时自动隐藏导航、侧边栏、评论区。

---

## 三、新增功能清单

### 3.1 点赞 / 点踩 / 收藏

- 一人一票（`unique_together = ('user', 'post')`）；再点同一个按钮 = 取消；
- 赞和踩互斥（先赞后踩会自动把赞撤掉）；
- 数字实时更新（`humanize_count`：1234 → 1.2k，12345 → 1.2w）；
- 收藏在个人主页有「我的收藏」Tab。

### 3.2 标签系统

- 一篇文章多个标签（`ManyToManyField`），发布时用逗号/空格分隔输入，自动创建不存在的标签；
- **中文标签自动生成 slug**：`机器学习` → slugify 后为空，自动退化成 `tag-<md5前10位>`，
  保证中文标签也能有干净的 URL；
- 标签详情页、标签云（按文章数分 4 档字号）。

### 3.3 Markdown 正文 + 代码高亮

- 正文写 Markdown，展示时渲染成 HTML：标题、列表、表格、引用、代码块、脚注；
- 代码块用 Pygments 上色，浅色/深色主题各一套配色；
- 中文标题自动生成锚点 id，目录可跳转；
- bleach 白名单过滤，`<script>`、`onerror`、`javascript:` 全部清掉；
- 外链自动加 `target="_blank" rel="noopener"`；
- **渲染结果缓存**在 `Post.rendered_content`，正文没改就直接复用（比较 `rendered_at` 与 `updated`）；
- 正文改动后缓存自动失效，重渲染。

### 3.4 阅读量统计 + 热门榜

- 每次访问详情页 `views + 1`（作者自己访问不计入，避免刷自己的数据）；
- 用 `F('views') + 1` 在数据库层面自增，避免并发覆盖；
- 侧边栏「热门文章」TOP5，关于页「最多阅读」TOP5，首页支持按阅读量/点赞/评论数排序。

### 3.5 用户主页 + 头像 + 简介

- `UserProfile` 与 `User` 一对一，新用户注册时用**信号**自动创建；
- 头像三级兜底：上传的图片 → 外链 → **用户名首字母 + 由用户名哈希出的稳定配色**（永远不会是破图）；
- 个性签名、所在地、个人网站、GitHub；
- 公开主页：文章 / 收藏 Tab、统计（文章数、阅读量、获赞、评论数）、最近评论。

### 3.6 站内通知

| 触发 | 通知谁 |
| --- | --- |
| 有人评论我的文章 | 文章作者 |
| 有人回复我的评论 | 被回复的人 |
| 有人点赞我的文章 | 文章作者 |
| 有人收藏我的文章 | 文章作者 |
| 有人点赞我的评论 | 评论作者 |

- **不会给自己发通知**（`Notification.push` 里判断 `recipient.pk == sender.pk`）；
- 导航栏铃铛有未读小红点，点开是最近 8 条，可一键全部已读；
- 通知中心支持按类型筛选、无刷新标记已读；
- 点通知直接跳到对应评论（`/post/2/#comment-15`），前端会把那条评论**高亮闪烁**一下；
- 每 60 秒轮询一次未读数（`/notifications/poll/`）。

### 3.7 全文搜索 + 分页

- 搜索范围：标题、正文、摘要、标签名、作者名；
- 独立搜索结果页：相关文章 + 相关用户 + 相关标签三组；
- 首页支持「分类 + 关键词 + 起止日期 + 排序」组合筛选，筛选条件在翻页时保留；
- 文章列表每页 6 篇，评论区每页 10 层楼。

### 3.8 其它

- **后台增强**：所有新模型都注册进 admin，评论内联到文章编辑页，
  评论支持「标记删除 / 恢复显示」批量操作，列表页有内容预览、点赞数等列。
- **个人中心**：文章按状态筛选（全部/已发布/草稿）、数据概览、数据条、
  文章管理（编辑 / 一键转草稿 / 删除）、最近通知、我的最新评论。
- **管理命令**：
  - `generate_emoticons` 生成表情 SVG
  - `seed_demo` 生成演示数据（`--reset` 清空重来）
  - `rerender_posts` 重建 Markdown 渲染缓存

---

## 四、文件改动总览

### 后端

| 文件 | 改动 |
| --- | --- |
| `blog/models.py` | 重写。新增 `Tag` `UserProfile` `PostVote` `Bookmark` `CommentLike` `Notification`；`Post` 加封面/阅读量/渲染缓存/标签/统计方法；`Comment` 加楼中楼/点赞/配图/软删除 |
| `blog/views.py` | 重写。新增投票、收藏、通知、用户主页、标签、搜索、资料编辑等视图；评论系统核心 `_load_comment_page` |
| `blog/forms.py` | 重写。`TagField` 标签输入、`CommentForm` 校验链、`ProfileForm`、`RegisterForm` |
| `blog/urls.py` | 重写。约 20 条路由 |
| `blog/admin.py` | 重写。9 个模型全部注册，评论内联、批量操作 |
| `blog/markdown_utils.py` | **新增**。Markdown 渲染 + XSS 过滤 + 表情码 |
| `blog/context_processors.py` | **新增**。全站注入分类导航、热门文章、热门标签、未读通知数 |
| `blog/templatetags/blog_extras.py` | **新增**。`humanize_count` `time_ago` `markdownify` `emoticons` `percentage` `url_replace` |
| `blog/migrations/0004_*.py` | **新增**。结构迁移（新表 + 新字段 + 索引） |
| `blog/migrations/0005_*.py` | **新增**。数据迁移：老评论回填 root/depth、老用户补建资料 |
| `blog/management/commands/` | **新增**。3 个管理命令 |
| `blog/tests.py` | 重写。**88 个测试** |
| `DjangoBlog/settings.py` | 改。数据库环境变量开关、静态/媒体目录、登录跳转、分页配置、PyMySQL 适配 |
| `DjangoBlog/urls.py` | 改。媒体文件服务、自定义 404/500 |

### 前端

| 文件 | 说明 |
| --- | --- |
| `static/css/style.css` | **新增**。完整设计系统（约 1100 行），浅色 + 深色两套主题 |
| `static/js/main.js` | **新增**。主题切换、下拉菜单、表情面板、评论区 AJAX、点赞收藏、灯箱、阅读进度、目录高亮、通知轮询 |
| `static/img/emoticons/*.svg` | **生成**。38 个表情图标 |
| `templates/blog/base.html` | **新增**。统一骨架 |
| `templates/blog/partials/` | **新增**。`post_card` `pagination` `avatar` `sidebar` `notif_panel` `comment_list` `comment_item` |
| `templates/blog/widgets/` | **新增**。带头像预览的文件上传控件 |
| 其余 13 个页面模板 | 全部重写为 `extends base.html` |

### 启动脚本

| 文件 | 用途 |
| --- | --- |
| `setup_env.bat` | 建虚拟环境 + 装依赖 + 初始化数据库（双击即用） |
| `start.bat` | 启动开发服务器，启动前做数据库连通性预检 |
| `manage.bat` | 在虚拟环境里执行任意 `manage.py` 命令 |
| `bootstrap.py` | 上面两个 bat 调用的引导脚本：查依赖、migrate、生成表情、可选演示数据 |
| `check_db.py` | 数据库连通性预检，把「MySQL 没启动」翻译成人话 |
| `.gitignore` | 忽略 `.venv/`、`db.sqlite3`、`media/`、`__pycache__/` 等 |

### 验证脚本（可以直接删）

| 文件 | 用途 |
| --- | --- |
| `smoke_check.py` | 75 项 HTTP 冒烟检查（真实请求跑通所有页面和接口） |
| `verify_admin.py` | 29 项后台检查 |
| `verify_markdown.py` | 17 项 Markdown 渲染 / XSS 过滤检查 |
| `setup_smoke_user.py` | 给冒烟测试准备独立账号 |

---

## 五、验证方式

### 5.1 单元测试（88 个，推荐先跑这个）

```cmd
manage.bat sqlite test blog -v 2
```

覆盖：认证与权限、开放重定向防护、文章 CRUD、标签、Markdown 渲染与高亮、
XSS 过滤、阅读量、点赞/点踩/收藏的互斥与取消、**评论楼中楼结构与 root/depth 计算**、
评论软删除不塌楼、评论权限（作者 / 楼主 / 路人）、评论点赞、评论配图上传与非法文件拦截、
评论频率限制、通知的产生与「不给自己发通知」、通知已读、用户主页草稿可见性、
搜索与筛选、分页边界、**查询次数上界（N+1 回归）**。

### 5.2 HTTP 冒烟测试（75 项，验证真实渲染）

```cmd
:: 终端 1：起服务
start.bat sqlite 8765

:: 终端 2：跑检查
.venv\Scripts\python.exe setup_smoke_user.py
.venv\Scripts\python.exe smoke_check.py http://127.0.0.1:8765
```

### 5.3 后台与 Markdown

```cmd
.venv\Scripts\python.exe verify_admin.py http://127.0.0.1:8765
.venv\Scripts\python.exe verify_markdown.py
```

> 本次改造的实测结果：**88 个单元测试 OK**、**75 项冒烟检查全通过**、
> **29 项后台检查全通过**、**17 项 Markdown 检查全通过**。
> 三个 bat 脚本也逐一实测过：全新环境（删掉 `.venv` 和数据库）双击运行
> `setup_env.bat sqlite` 能一路跑到「环境就绪」，`start.bat` 在任意工作目录下
> 都能正常起服务（首页 / 详情页 / 标签页 / 关于页 / 登录页全部 HTTP 200），
> `manage.bat` 的 5 种调用方式全部正常。

---

## 六、答辩可以讲的 8 个技术点

1. **树形结构建模**：为什么用 `parent` + `root` 两个自关联字段，而不是只用一个 `parent` 递归查询；
   `depth` 压平到 2 是为了什么。
2. **软删除**：为什么评论不能物理删除（楼层号、孤儿回复），`is_deleted` + 占位文案的实现。
3. **AJAX 局部刷新 + 事件委托**：为什么容器内容替换后必须用事件委托绑定事件；
   如何用「服务端渲染局部模板 + 前端整体替换」兼顾 SEO 和体验。
4. **ORM 查询优化**：`select_related` / `prefetch_related` / `Prefetch` 的区别与适用场景；
   模板里写 `post.tags.all|slice:":4"` 会「预取一次又查一次」的坑；
   用 `assertNumQueries` 把性能变成**可回归的指标**（首页 29 → 13 次查询）。
5. **注解命名冲突**：`annotate(like_count=...)` 会覆盖模型上的 `like_count` 属性，
   导致模板报错 —— 所以统一改成 `like_count_annotated`，模型属性里做兼容读取。
6. **XSS 防护**：Markdown 渲染后为什么必须过一遍 bleach 白名单；
   评论内容为什么要「先转义再替换表情码」。
7. **安全细节**：CSRF（表单 + AJAX 请求头）、开放重定向校验、上传文件类型白名单、
   密码强度校验、权限校验（作者 / 楼主 / 路人三档）。
8. **站内通知的设计**：在写路径触发、不给自己发通知、跳转到具体评论锚点。

加分项（可以现场演示）：

- 深色模式切换（CSS 变量 + `localStorage` + 防白屏闪烁）；
- 评论表情面板（表情码 → 动态生成 SVG，不用图片资源）；
- 楼中楼折叠 / 展开（纯前端，不重复请求服务器）；
- 后台一条龙管理（评论内联、批量标记删除、数据列）。

---

## 七、后续还能做什么

如果还需要继续加功能，下面这些是性价比比较高的方向（按推荐顺序）：

1. **关注 / 粉丝**：`Follow` 表 + 关注动态流（首页加「关注」Tab）。
2. **文章草稿自动保存**：编辑器定时把内容存到 `localStorage`，防止意外关闭丢稿。
3. **RSS / 站点地图**：`django.contrib.syndication` + `sitemaps`，几行配置就能加。
4. **富文本粘贴**：编辑器支持粘贴图片直接上传（`paste` 事件 + `FormData`）。
5. **评论 @ 提醒**：解析评论里的 `@用户名`，额外给被 @ 的人发通知。
6. **数据看板**：用 ECharts 画「近 30 天发文量 / 阅读量趋势」，个人中心和关于页各来一个。
7. **全文检索**：数据量大了可以上 `django-haystack` + Whoosh，或者 MySQL 全文索引。
8. **缓存**：`django.core.cache` 缓存首页和热门榜，或用 Redis。
9. **部署**：Nginx + Gunicorn/uWSGI + `collectstatic`，把 `SECRET_KEY` 和数据库密码
   移到环境变量里（现在已经支持 `DJANGO_SECRET_KEY`）。
10. **评论审核**：敏感词过滤 + 先审后发（后台已经有软删除，加个 `is_approved` 即可）。

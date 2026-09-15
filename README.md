# DjangoBlog · 个人博客系统

一个基于 **Django 4.2** 的博客系统，实现了类 B 站的评论互动、Markdown 写作、
点赞收藏、站内通知与用户主页，界面为响应式设计并支持深色模式。

> ### 🔗 在线预览
>
> **界面预览目录**：<https://kyoukaalice.github.io/django-inkwell-blog/index-generated.html>
> **站点首页**：<https://kyoukaalice.github.io/django-inkwell-blog/index.html>
>
> ⚠️ 这是**静态快照**：样式、排版、评论楼中楼都是真实渲染结果，但登录、发文、
> 点赞、发评论这些需要服务端的操作不会生效 —— GitHub Pages 只能托管静态文件，
> 跑不了 Django。想看完整功能请在本地运行（见下方快速开始）。
---

## 功能一览

### 评论系统（核心）
- **楼中楼**：任意深度回复自动压平为两级展示，不会无限缩进
- **评论点赞**：一人一赞可取消，显示「xx 人觉得很赞」
- **表情**：38 个表情，`[em:smile]` 表情码，点击面板插入，纯表情评论自动放大
- **配图**：每条评论可带一张图（≤5MB），点击看大图
- **排序与分页**：最热 / 最新切换，每页 10 层楼，楼中楼折叠展开
- **软删除**：删除后保留「该评论已删除」占位，楼层号不塌、回复不丢
- **防刷屏**：同一用户 15 秒内只能发一条
- **权限**：评论作者本人或文章作者（楼主）都可删除
- **AJAX 无刷新**：发评论 / 点赞 / 删除 / 排序 / 翻页都不刷新页面，无 JS 时表单仍可用

### 内容与互动
- Markdown 正文渲染 + Pygments 代码高亮 + bleach 白名单防 XSS + 渲染结果缓存
- 标签系统（中文标签自动生成 slug）、分类、按标签/分类/关键词/日期范围筛选
- 文章点赞 / 点踩 / 收藏（一人一票，再点取消）
- 阅读量统计（作者访问不计入）、热门文章榜
- 全文搜索（文章 + 用户 + 标签）、文章与评论分页

### 用户与消息
- 用户主页：文章 / 收藏 Tab、统计、最近评论
- 头像三级兜底（上传图片 → 外链 → 用户名首字母色块），个性签名、社交链接
- 个人中心：数据概览、文章管理（编辑 / 转草稿 / 删除）
- 站内通知：评论、回复、点赞、收藏、评论被赞五类；导航栏未读小红点；点击跳转到对应评论

### 界面
- 一套 CSS 变量设计系统（浅色 / 深色双主题，一键切换，跟随系统偏好）
- 全站响应式（双栏 ↔ 单栏 ↔ 移动端）
- 阅读进度条、自动生成文章目录并滚动高亮、图片灯箱
- 内联 SVG 图标，不依赖任何 CDN，断网也能正常显示

---

## 技术栈

| 层次 | 选型 |
| --- | --- |
| 后端 | Python 3.9 · Django 4.2 |
| 数据库 | MySQL（默认）/ SQLite（可用环境变量一键切换） |
| 正文渲染 | Markdown · Pygments · bleach |
| 图片处理 | Pillow |
| 前端 | 原生 HTML / CSS / JavaScript（无框架、无构建步骤） |

---

## 快速开始（Windows，双击即可）

```cmd
:: 1) 初始化环境：建虚拟环境 + 装依赖 + 建表 + 生成表情 + 演示数据
setup_env.bat sqlite demo

:: 2) 启动
start.bat sqlite
```

浏览器打开 <http://127.0.0.1:8000/>

| 脚本 | 作用 |
| --- | --- |
| `setup_env.bat` | 初始化环境（可加 `sqlite` 用 SQLite、加 `demo` 灌演示数据） |
| `start.bat` | 启动服务器（可加 `sqlite`、端口、`0.0.0.0:8000`） |
| `manage.bat` | 执行任意 `manage.py` 命令，如 `manage.bat sqlite test blog` |

### 手动命令（macOS / Linux 或不想用脚本）

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py generate_emoticons   # 生成评论表情 SVG
python manage.py seed_demo            # 可选：演示数据
python manage.py runserver
```

### 演示账号

| 账号 | 密码 | 说明 |
| --- | --- | --- |
| `admin` | `BlogDemo!2026` | 站长，超级管理员，可进 `/admin/` |
| `alice` | `BlogDemo!2026` | 普通用户 |
| `bob` | `BlogDemo!2026` | 普通用户 |

### 数据库切换

默认读 `settings.py` 里的 MySQL 配置；设环境变量即可切到 SQLite，代码与迁移完全兼容：

```bash
export DB_ENGINE=sqlite            # Windows: set DB_ENGINE=sqlite
python manage.py runserver
```

其它可用环境变量：`DB_NAME` `DB_USER` `DB_PASSWORD` `DB_HOST` `DB_PORT` `DJANGO_DEBUG` `DJANGO_SECRET_KEY`。

---

## 界面预览（GitHub Pages）

GitHub Pages 只能托管静态文件，跑不了 Django 服务端。所以本仓库提供一个
**静态快照**：把每个页面在真实数据下渲染成 HTML 后放在 `docs/` 目录，供 Pages 直接发布。

```bash
python manage.py build_snapshot      # 重新生成快照（输出到 docs/）
python verify_snapshot.py docs       # 校验链接完整性（0 死链才算通过）
python check_pages.py --open         # 检查 Pages 构建状态 + 线上探活
```

快照只放在 `docs/` 一个目录里，**仓库根目录保持干净** —— 39 个生成出来的 HTML
不会和 `manage.py`、`README.md` 混在一起。Pages 设置对应为
「Deploy from a branch → main → `/docs`」。

生成器带 manifest 保护：每次构建只清理上次自己生成的文件（并做路径校验），
不会碰 `manage.py`、`blog/` 等项目文件。也支持 `-o .` 输出到根目录，
如果你的 Pages 是「main + 根目录」就能用。

改完页面后同步到线上：

```bash
python manage.py build_snapshot
git add -A && git commit -m "chore: 更新静态预览" && git push
```

Pages 会在 1～2 分钟内自动重新构建：

| 入口 | 地址 |
| --- | --- |
| 预览目录（推荐） | <https://kyoukaalice.github.io/django-inkwell-blog/index-generated.html> |
| 站点首页 | <https://kyoukaalice.github.io/django-inkwell-blog/index.html> |

> 快照里的样式、排版、评论楼中楼都是真实渲染结果；
> 但登录、发文、点赞、发评论这类操作不会生效——它们是 Django 视图，需要 Python 进程。

---

## 测试

```cmd
manage.bat sqlite test blog        :: 88 个单元测试
```

覆盖：认证与权限、开放重定向防护、文章 CRUD、标签、Markdown 渲染与高亮、XSS 过滤、
阅读量、点赞/点踩/收藏互斥与取消、**评论楼中楼结构与 root/depth 计算**、评论软删除不塌楼、
评论权限（作者/楼主/路人）、评论点赞、配图上传与非法文件拦截、评论频率限制、
通知产生与「不给自己发通知」、通知已读、用户主页草稿可见性、搜索与筛选、分页边界、
**查询次数上界（N+1 回归）**。

另有几个独立校验脚本：

| 脚本 | 说明 |
| --- | --- |
| `smoke_check.py` | 75 项 HTTP 冒烟检查（需先启动服务器） |
| `verify_admin.py` | 29 项 Django admin 后台检查 |
| `verify_markdown.py` | 17 项 Markdown 渲染 / XSS 过滤检查 |
| `verify_snapshot.py` | 静态快照链接完整性校验 |

---

## 项目结构

```
DjangoBlog/
├── DjangoBlog/                 # 项目配置
│   ├── settings.py             #   数据库（支持 MySQL / SQLite 切换）
│   └── urls.py                 #   路由 + 静态/媒体文件服务
├── blog/                       # 博客应用
│   ├── models.py               #   8 个模型（文章/评论/标签/点赞/收藏/通知…）
│   ├── views.py                #   视图，评论系统核心 _load_comment_page
│   ├── forms.py                #   表单与校验（含评论校验链）
│   ├── markdown_utils.py       #   Markdown 渲染 + XSS 过滤 + 表情
│   ├── admin.py                #   后台配置
│   ├── tests.py                #   88 个单元测试
│   ├── management/commands/    #   seed_demo / generate_emoticons / rerender_posts / build_snapshot
│   ├── templatetags/           #   自定义模板过滤器
│   └── templates/blog/         #   模板（base + partials + 19 个页面）
├── static/css/style.css        # 设计系统（CSS 变量 + 深浅双主题）
├── static/js/main.js           # 交互脚本
├── docs/                       # GitHub Pages 静态快照（39 个页面 + 样式）
│                               #   由 manage.py build_snapshot 生成
├── setup_env.bat / start.bat / manage.bat   # Windows 一键脚本
└── requirements.txt
```

---

## 实现要点

几个值得说明的设计决策：

1. **评论楼中楼用 `parent` + `root` + `depth` 三个字段**，而不是只用一个 `parent` 递归查询。
   `root` 指向所属楼层，`depth` 最深压平到 2，在 `Comment.save()` 里自动推导。
   好处是一次 `SELECT` 就能取回整棵评论树，零递归查询。
2. **评论用软删除**（`is_deleted`）而不是物理删除，避免楼层号消失、楼中楼回复变孤儿。
3. **AJAX 局部刷新 + 事件委托**：评论区整体作为局部模板由服务端渲染，
   前端替换容器内容；所有按钮事件绑在容器上，否则替换后新按钮会失效。
4. **ORM 优化**：`select_related` / `prefetch_related` / `Prefetch` 消除 N+1，
   并用 `assertNumQueries` 把查询次数写成回归测试（首页 29 → 13 次）。
5. **渲染结果缓存**：Markdown 渲染耗时，结果写回 `Post.rendered_content`，
   通过比较 `rendered_at` 与 `updated` 判断是否过期。
6. **安全性**：CSRF、bleach 白名单防 XSS、开放重定向校验、上传类型白名单、
   评论频率限制、三档权限校验。

更多设计细节见 [`README-改造说明.md`](README-改造说明.md)。

---

## License

本项目为个人学习 / 毕业设计作品，可自由参考使用。

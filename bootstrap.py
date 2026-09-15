"""一键环境引导脚本（供 setup_env.bat / start.bat 调用）。

做的事：
    1. 检查依赖是否装齐（缺了就自动 pip install -r requirements.txt）
    2. 自动生成数据库迁移状态检查（未应用的迁移会提示，不会偷偷改库）
    3. 首次运行自动 migrate
    4. 若 static/img/emoticons/ 为空，自动生成 38 个表情 SVG
    5. 可选：灌演示数据、重建 Markdown 渲染缓存

用法：
    python bootstrap.py                 # 检查 + 自动初始化
    python bootstrap.py --no-migrate    # 只检查依赖，不动数据库
    python bootstrap.py --demo          # 顺便灌演示数据（已有文章则跳过）
    python bootstrap.py --force-demo    # 清空博客数据后重建演示数据（慎用）
    python bootstrap.py --force-emoticons   # 重新生成表情 SVG
"""
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

REQUIRED = {
    'django': 'Django',
    'pymysql': 'PyMySQL',
    'PIL': 'Pillow',
    'markdown': 'Markdown',
    'bleach': 'bleach',
    'tinycss2': 'tinycss2',
    'pygments': 'Pygments',
}

GREEN, YELLOW, RED, DIM, RESET = '\033[92m', '\033[93m', '\033[91m', '\033[90m', '\033[0m'
if not sys.stdout.isatty():          # 重定向到文件时不要输出颜色码
    GREEN = YELLOW = RED = DIM = RESET = ''


def say(icon, message):
    print(f'  {icon} {message}')


def run(args, **kwargs):
    """执行子进程并返回退出码。"""
    return subprocess.call([sys.executable, *args], cwd=str(BASE_DIR), **kwargs)


def missing_packages():
    import importlib
    missing = []
    for module, package in REQUIRED.items():
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(package)
    return missing


def main():
    args = sys.argv[1:]
    do_migrate = '--no-migrate' not in args
    want_demo = '--demo' in args or '--force-demo' in args
    force_demo = '--force-demo' in args
    force_emoticons = '--force-emoticons' in args

    print()
    print('=' * 64)
    print('  DjangoBlog 环境引导')
    print('=' * 64)
    print(f'  Python : {sys.version.split()[0]}')
    print(f'  解释器 : {sys.executable}')
    print(f'  项目   : {BASE_DIR}')
    print()

    # ---------- 1. 依赖 ----------
    print('[1/4] 检查依赖')
    missing = missing_packages()
    if missing:
        say('!', f'缺少依赖：{"、".join(missing)}，开始安装…')
        code = run(['-m', 'pip', 'install', '-r', 'requirements.txt'])
        if code != 0:
            say('X', '依赖安装失败，请检查网络后重试：')
            print('        .venv\\Scripts\\python.exe -m pip install -r requirements.txt')
            return 1
        still = missing_packages()
        if still:
            say('X', f'仍然缺少：{"、".join(still)}')
            return 1
        say('OK', '依赖安装完成')
    else:
        say('OK', f'依赖齐全（{len(REQUIRED)} 个包）')

    # ---------- 2. Django 自检 ----------
    print()
    print('[2/4] Django 自检')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'DjangoBlog.settings')
    try:
        import django
        django.setup()
    except Exception as exc:                       # noqa: BLE001
        say('X', f'Django 初始化失败：{exc}')
        return 1

    from django.conf import settings
    from django.core.management import call_command
    from django.db import connection

    engine = settings.DATABASES['default']['ENGINE']
    say('OK', f'数据库引擎：{engine.rsplit(".", 1)[-1]}'
              f'{"" if "sqlite" in engine else " (" + settings.DATABASES["default"]["NAME"] + ")"}')

    # ---------- 3. 数据库迁移 ----------
    if do_migrate:
        print()
        print('[3/4] 数据库迁移')
        try:
            from django.db.migrations.executor import MigrationExecutor
            executor = MigrationExecutor(connection)
            pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
        except Exception as exc:                   # noqa: BLE001
            say('X', f'连不上数据库：{exc}')
            print()
            print('    请任选一种方式处理：')
            print('      1) 启动 MySQL 后重新运行本脚本')
            print('      2) 改用 SQLite 运行（无需 MySQL）：')
            print('         set DB_ENGINE=sqlite && start.bat sqlite')
            return 1

        if pending:
            say('!', f'有 {len(pending)} 个迁移未应用，正在执行 migrate…')
            try:
                call_command('migrate', interactive=False, verbosity=1)
            except Exception as exc:               # noqa: BLE001
                say('X', f'迁移失败：{exc}')
                return 1
            say('OK', '迁移完成')
        else:
            say('OK', '数据库结构已是最新，无需迁移')
    else:
        print()
        print('[3/4] 数据库迁移 — 已跳过（--no-migrate）')

    # ---------- 4. 静态资源与可选数据 ----------
    print()
    print('[4/4] 初始化静态资源')
    emoticon_dir = BASE_DIR / 'static' / 'img' / 'emoticons'
    existing = list(emoticon_dir.glob('*.svg')) if emoticon_dir.exists() else []
    if force_emoticons or len(existing) < 30:
        say('!', f'正在生成表情图标（当前 {len(existing)} 个）…')
        call_command('generate_emoticons')
        say('OK', f'表情图标已生成（{len(list(emoticon_dir.glob("*.svg")))} 个）')
    else:
        say('OK', f'表情图标已就绪（{len(existing)} 个）')

    if want_demo:
        from blog.models import Post
        if force_demo:
            say('!', '正在重建演示数据（--force-demo，会清空现有博客数据）…')
            call_command('seed_demo', reset=True)
        elif not Post.objects.exists():
            say('!', '正在生成演示数据…')
            call_command('seed_demo')
        else:
            say('OK', f'已有 {Post.objects.count()} 篇文章，跳过演示数据'
                      f'（要重建用 --force-demo）')

    print()
    print('=' * 64)
    print(f'  {GREEN}环境就绪{RESET}')
    print('=' * 64)
    print('  启动服务 ：start.bat')
    print('  用 SQLite：start.bat sqlite')
    print('  管理命令 ：manage.bat <命令>      例如 manage.bat seed_demo --reset')
    print('  演示账号 ：admin / alice / bob     密码都是 BlogDemo!2026')
    print()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\n已取消')
        sys.exit(130)

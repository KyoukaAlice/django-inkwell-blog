"""数据库连通性预检（供 start.bat 在启动服务器之前调用）。

为什么需要它：MySQL 没启动时，Django 会在第一次访问数据库时抛出
一长串 traceback，对不熟悉的人很不友好。这里先把连接试一遍，
失败时只打印一句人话，让 start.bat 给出「改用 SQLite」等建议。

退出码：0 表示连得上，1 表示连不上。
"""
import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'DjangoBlog.settings')

try:
    django.setup()
except Exception as exc:                       # noqa: BLE001
    print(f'  [X] Django 初始化失败：{exc}')
    sys.exit(1)

from django.conf import settings               # noqa: E402
from django.db import connection               # noqa: E402

engine = settings.DATABASES['default']['ENGINE'].rsplit('.', 1)[-1]
name = settings.DATABASES['default']['NAME']
label = f'{engine} / {name}'
if engine == 'mysql':
    cfg = settings.DATABASES['default']
    label += f' @ {cfg["HOST"]}:{cfg["PORT"]} (user={cfg["USER"]})'

try:
    connection.ensure_connection()
except Exception as exc:                       # noqa: BLE001
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    print(f'  [X] 数据库连不上：{label}')
    print(f'      {message}')
    sys.exit(1)

print(f'  [OK] 数据库连接正常：{label}')
sys.exit(0)

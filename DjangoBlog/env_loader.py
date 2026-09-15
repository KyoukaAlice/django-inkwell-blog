"""极简 .env 读取器：把 KEY=VALUE 注入 os.environ（已存在的变量不覆盖）。

为什么需要它：settings.py 里的数据库密码不应该硬编码进仓库
（推到 GitHub 就公开了）。本地把敏感配置写在项目根目录的 .env 里，
.env 已在 .gitignore 中忽略，不会进版本库。

用法（在 settings.py 顶部）：
    from .env_loader import load_env_file
    load_env_file(BASE_DIR / '.env')

.env 示例：
    DB_PASSWORD=你的MySQL密码
    DB_USER=root
    DJANGO_SECRET_KEY=随便一串长随机字符
"""
import os
from pathlib import Path


def load_env_file(path, override=False):
    """读取 .env 文件并写入 os.environ。

    path      .env 文件路径（不存在就静默跳过，属正常情况）
    override  True 时覆盖已存在的环境变量；默认 False，
              这样命令行里 set 的变量优先级更高。
    返回成功注入的键值对数量。
    """
    path = Path(path)
    if not path.is_file():
        return 0

    loaded = 0
    # utf-8-sig 顺带处理带 BOM 的文件（Windows 记事本另存为会加 BOM）
    for raw_line in path.read_text(encoding='utf-8-sig').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if line.lower().startswith('export '):
            line = line[7:].strip()
        if '=' not in line:
            continue

        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip()
        # 去掉包裹的引号
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if not key:
            continue

        if override or key not in os.environ:
            os.environ[key] = value
            loaded += 1
    return loaded

"""对照实验：验证 check_editor_layout.py 能抓到「右栏卡片右边空一块」这个 bug。

做法：临时把 align-self: start 塞回 .editor-side，跑检查（应该 FAIL），
再恢复原样跑一次（应该 OK）。用来确认守卫不是摆设。

    python verify_layout_guard.py
"""
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
CSS = BASE / 'static' / 'css' / 'style.css'
CHECK = BASE / 'check_editor_layout.py'
PY = BASE / '.venv' / 'Scripts' / 'python.exe'
PY = str(PY) if PY.is_file() else sys.executable


def run_check():
    out = subprocess.run([PY, str(CHECK)], capture_output=True, text=True, cwd=BASE)
    return out.returncode, out.stdout


def main():
    original = CSS.read_text(encoding='utf-8')

    # --- 1. 故意制造 bug ---
    broken = original.replace(
        '.editor-side {\n    display: flex;\n    flex-direction: column;\n    gap: 16px;\n'
        '    position: sticky;\n    top: calc(var(--header-h) + 22px);\n}',
        '.editor-side {\n    display: flex;\n    flex-direction: column;\n    gap: 16px;\n'
        '    position: sticky;\n    top: calc(var(--header-h) + 22px);\n'
        '    align-self: start;\n}',
        1)
    if broken == original:
        print('[SKIP] 没匹配到 .editor-side 规则，脚本里的替换串需要更新')
        return 1

    try:
        CSS.write_text(broken, encoding='utf-8')
        code, out = run_check()
        caught = code != 0 and 'align-self' in out
        print(f'制造 bug 后：退出码 {code}  -> {"抓到 ✅" if caught else "没抓到 ❌"}')
        for line in out.splitlines():
            if 'FAIL' in line or 'align-self' in line and 'OK' not in line:
                print(f'    {line.strip()}')

        # --- 2. 恢复 ---
        CSS.write_text(original, encoding='utf-8')
        code2, out2 = run_check()
        ok = code2 == 0
        print(f'恢复之后：  退出码 {code2}  -> {"通过 ✅" if ok else "仍失败 ❌"}')
    finally:
        CSS.write_text(original, encoding='utf-8')

    print()
    if caught and ok:
        print('结论：守卫有效 —— 这个 bug 再被写回来时检查会立刻失败。')
        return 0
    print('结论：守卫没起作用，需要检查 check_editor_layout.py 的规则。')
    return 1


if __name__ == '__main__':
    sys.exit(main())

"""模拟 Jekyll 的 Liquid 解析，检查仓库里的 Markdown 能不能安全构建。

为什么需要它
------------
GitHub Pages 内置的 Jekyll 会把仓库里的 Markdown 当 Liquid 模板处理：

  * `{% xxx %}` 会被当成 Liquid 标签。遇到 Django 模板标签（{% extends %} 等）
    会报 "Unknown tag 'extends'"，**整个 Pages 构建失败**。
  * `{{ xxx }}` 会被当成变量输出。

本仓库的文档里有大量 Django / Markdown 模板片段，所以必须保证它们
要么包在 {% raw %} 里，要么本身是合法 Liquid。

这个脚本不需要外网，自己实现 Liquid 的 tokenize + 标签合法性判断，
覆盖 Jekyll 在 GitHub Pages 上启用的标签集合。

    python verify_liquid.py            # 检查仓库（只查会被 Jekyll 处理的文件）
    python verify_liquid.py --all      # 连 docs/ 里的也一起查
"""
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

# GitHub Pages 启用的 Jekyll + 插件提供的 Liquid 标签
KNOWN_TAGS = {
    'raw', 'endraw', 'comment', 'endcomment',                                       # Liquid 内置
    'if', 'endif', 'elsif', 'else', 'unless', 'endunless', 'case', 'endcase', 'when',
    'for', 'endfor', 'break', 'continue', 'cycle', 'tablerow', 'endtablerow',
    'assign', 'capture', 'endcapture', 'increment', 'decrement',
    'include', 'include_relative', 'link', 'post_url', 'highlight', 'endhighlight',
    'seo', 'seo_title', 'feed_meta',                                                   # jekyll-seo-tag / feed
    'github_edit_link', 'octicon', 'avatar',                                           # jekyll-github-metadata 等
    'gist',                                                                            # jekyll-gist
    'paginate',                                                                        # jekyll-paginate
}

# Jekyll 的 front matter / Liquid 标签正则
TAG_RE = re.compile(r'\{%-?\s*(\w+)')
VAR_RE = re.compile(r'\{\{')


def tracked_markdown(include_docs=False):
    """列出会被 Jekyll 处理的 Markdown 文件（git 跟踪的 + 工作区里的）。"""
    out = subprocess.run(['git', 'ls-files', '-z'], cwd=BASE,
                         capture_output=True, text=True, check=False).stdout
    files = [f for f in out.split('\0') if f.lower().endswith(('.md', '.markdown'))]
    if not include_docs:
        files = [f for f in files if not f.startswith('docs/')]
    # 补上工作区里还没提交的 md
    for path in BASE.rglob('*.md'):
        rel = path.relative_to(BASE).as_posix()
        if 'docs/' in rel or '.venv' in rel or '__pycache__' in rel:
            continue
        if rel not in files:
            files.append(rel)
    return sorted(set(files))


def check_file(rel_path):
    """返回问题列表。模仿 Liquid 的解析顺序：raw 块内部的标签不解析。"""
    path = BASE / rel_path
    if not path.is_file():
        return []
    text = path.read_text(encoding='utf-8', errors='replace')

    problems = []
    in_raw = False
    raw_open_line = None

    for lineno, line in enumerate(text.splitlines(), start=1):
        for tag_match in TAG_RE.finditer(line):
            name = tag_match.group(1).lower()

            if name == 'raw':
                if in_raw:
                    problems.append((lineno, 'raw 嵌套了 raw'))
                else:
                    in_raw, raw_open_line = True, lineno
                continue
            if name == 'endraw':
                if not in_raw:
                    problems.append((lineno, 'endraw 没有对应的 raw'))
                else:
                    in_raw, raw_open_line = False, None
                continue

            if in_raw:
                continue        # raw 块里的东西 Liquid 不解析，安全

            if name not in KNOWN_TAGS:
                problems.append((lineno, f"Django 模板标签 {{{{% {name} %}}}} —— "
                                         f"Jekyll 会报 \"Unknown tag '{name}'\"，"
                                         f"需要用 {{% raw %}} 包起来"))

        # 未包在 raw 里的 {{ }} 也提示一下（不一定是错误，但值得确认）
        if not in_raw and VAR_RE.search(line) and '{{' in line:
            problems.append((lineno, "未转义的 {{ }} —— Liquid 会当变量输出，"
                                     "如果不是有意为之需要用 {% raw %} 包起来"))

    if in_raw:
        problems.append((raw_open_line, 'raw 没有闭合（缺少 endraw）'))
    return problems


def main():
    include_docs = '--all' in sys.argv
    files = tracked_markdown(include_docs)

    print('=' * 74)
    print('Liquid 安全性检查（模拟 GitHub Pages 的 Jekyll 构建）')
    print('=' * 74)
    print(f'\n检查 {len(files)} 个 Markdown 文件\n')

    total = 0
    for rel in files:
        problems = check_file(rel)
        if problems:
            total += len(problems)
            print(f'  [FAIL] {rel}')
            for lineno, msg in problems:
                print(f'         行 {lineno}: {msg}')
        else:
            print(f'  [OK]   {rel}')

    print()
    if total:
        print(f'结果：发现 {total} 个会导致 Pages 构建失败的问题')
        print('\n修法：把出问题的片段用 raw 标签包起来（写在 HTML 注释里说明原因）：')
        print('    ... 上方内容 ...')
        print('    {％ raw ％}          <- 注意这里要去掉全角百分号')
        print('    Django 模板片段...')
        print('    {％ endraw ％}')
        return 1
    print('结果：全部通过 —— 这些 Markdown 不会让 Jekyll 构建失败 ✅')
    print('\n提示：以后在文档里写 Django 模板标签，记得用 raw 包起来。')
    return 0


if __name__ == '__main__':
    sys.exit(main())

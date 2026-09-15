/* ==========================================================================
   DjangoBlog 前端脚本
   1) 主题切换  2) 导航交互  3) 提示条  4) 表情面板  5) 评论区（AJAX 无刷新）
   6) 文章点赞/收藏  7) 图片灯箱  8) 阅读进度与目录高亮
   ========================================================================== */
(function () {
    'use strict';

    /* ---------- 工具 ---------- */
    const $ = (sel, root = document) => root.querySelector(sel);
    const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

    function getCookie(name) {
        const match = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]*)'));
        return match ? decodeURIComponent(match[2]) : '';
    }

    /** 统一的 fetch 封装：自动带 CSRF、自动解析 JSON */
    async function post(url, data) {
        const body = data instanceof FormData ? data : new FormData();
        if (!(data instanceof FormData) && data) {
            Object.entries(data).forEach(([k, v]) => body.append(k, v));
        }
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCookie('csrftoken'), 'X-Requested-With': 'XMLHttpRequest' },
            body,
            credentials: 'same-origin',
        });
        let json = null;
        try { json = await res.json(); } catch (e) { /* 非 JSON 响应 */ }
        if (!res.ok && (!json || json.ok === false)) {
            throw new Error((json && json.error) || '请求失败，请稍后重试');
        }
        return json || {};
    }

    /** 轻提示 */
    function toast(message, type = 'ok') {
        let wrap = $('.toast-wrap');
        if (!wrap) {
            wrap = document.createElement('div');
            wrap.className = 'toast-wrap';
            document.body.appendChild(wrap);
        }
        const el = document.createElement('div');
        el.className = 'toast ' + type;
        el.textContent = message;
        wrap.appendChild(el);
        setTimeout(() => {
            el.style.transition = 'opacity .3s, transform .3s';
            el.style.opacity = '0';
            el.style.transform = 'translateX(20px)';
            setTimeout(() => el.remove(), 320);
        }, 2600);
    }

    function vibrate(el) {
        if (!el) return;
        el.classList.add('bump');
        setTimeout(() => el.classList.remove('bump'), 450);
    }

    /* ---------- 1. 主题切换 ---------- */
    const THEME_KEY = 'djangoblog-theme';
    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        $$('.theme-toggle').forEach((btn) => {
            btn.innerHTML = theme === 'dark'
                ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>'
                : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
            btn.title = theme === 'dark' ? '切换到浅色模式' : '切换到深色模式';
        });
    }
    function currentTheme() {
        return document.documentElement.getAttribute('data-theme') || 'light';
    }
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.theme-toggle');
        if (!btn) return;
        const next = currentTheme() === 'dark' ? 'light' : 'dark';
        localStorage.setItem(THEME_KEY, next);
        applyTheme(next);
    });
    applyTheme(currentTheme());

    /* ---------- 2. 导航交互 ---------- */
    document.addEventListener('click', (e) => {
        const toggle = e.target.closest('.menu-toggle');
        if (toggle) {
            const nav = $('.nav');
            if (nav) nav.classList.toggle('open');
            return;
        }
        // 下拉菜单 / 通知面板：点开一个就关掉其它
        const trigger = e.target.closest('[data-dropdown]');
        const targetSel = trigger ? trigger.dataset.dropdown : null;
        $$('.dropdown.open, .notif-panel.open').forEach((el) => {
            if (!targetSel || !el.matches(targetSel)) el.classList.remove('open');
        });
        if (trigger) {
            const menu = $(targetSel);
            if (menu) menu.classList.toggle('open');
        }
    });
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.user-menu') && !e.target.closest('.notif-wrap')) {
            $$('.dropdown.open, .notif-panel.open').forEach((el) => el.classList.remove('open'));
        }
    });

    /* ---------- 3. 提示条关闭 ---------- */
    document.addEventListener('click', (e) => {
        const close = e.target.closest('.alert .close');
        if (close) {
            const alert = close.closest('.alert');
            alert.style.transition = 'opacity .25s, transform .25s, height .25s';
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 260);
        }
    });

    /* ---------- 4. 表情面板 ---------- */
    let activeEmojiTarget = null;
    document.addEventListener('click', (e) => {
        const emojiBtn = e.target.closest('[data-emoji-toggle]');
        if (emojiBtn) {
            const editor = emojiBtn.closest('.editor-main') || emojiBtn.closest('.editor') || document;
            const panel = $('.emoji-panel', editor) || $('.emoji-panel');
            if (!panel) return;
            activeEmojiTarget = $('textarea', editor) || $('.editor-box textarea');
            const opening = !panel.classList.contains('open');
            $$('.emoji-panel.open').forEach((p) => p.classList.remove('open'));
            if (opening) {
                panel.classList.add('open');
                const rect = emojiBtn.getBoundingClientRect();
                panel.style.position = 'fixed';
                panel.style.top = Math.min(rect.bottom + 8, window.innerHeight - 270) + 'px';
                panel.style.left = Math.min(rect.left, window.innerWidth - 340) + 'px';
            }
            e.stopPropagation();
            return;
        }
        // 点击表情
        const emoji = e.target.closest('.emoji-panel img');
        if (emoji && activeEmojiTarget) {
            insertAtCursor(activeEmojiTarget, emoji.dataset.code);
            const panel = emoji.closest('.emoji-panel');
            if (panel) panel.classList.remove('open');
            e.stopPropagation();
            return;
        }
        if (!e.target.closest('.emoji-panel')) {
            $$('.emoji-panel.open').forEach((p) => p.classList.remove('open'));
        }
    });

    function insertAtCursor(textarea, text) {
        const start = textarea.selectionStart || 0;
        const end = textarea.selectionEnd || 0;
        const value = textarea.value;
        textarea.value = value.slice(0, start) + text + value.slice(end);
        textarea.selectionStart = textarea.selectionEnd = start + text.length;
        textarea.focus();
        textarea.dispatchEvent(new Event('input', { bubbles: true }));
    }

    /* ---------- 5. 评论区 ---------- */
    const commentsRoot = () => $('#comments');

    /** 记住哪些楼层被展开了，重新渲染后自动恢复 */
    function captureExpanded() {
        const set = new Set();
        $$('.comment[data-root]').forEach((c) => {
            if (c.classList.contains('expanded')) set.add(c.dataset.root);
        });
        return set;
    }

    /** 替换评论区 HTML */
    function swapComments(html, { keepExpanded = true } = {}) {
        const root = commentsRoot();
        if (!root || !html) return;
        const expanded = keepExpanded ? captureExpanded() : new Set();
        root.innerHTML = html;
        root.setAttribute('data-rendered', '1');
        reapplyExpanded(expanded);
        initCounters();
    }

    function reapplyExpanded(expanded) {
        if (!expanded || !expanded.size) return;
        expanded.forEach((rootId) => {
            const more = $(`.reply-more[data-root="${rootId}"]`);
            if (more) more.click();
        });
    }

    /** 让编辑器里的父评论 id 与提示条同步 */
    function setReplyTarget(commentEl, authorName, parentId) {
        const form = $('#comment-form');
        const editor = $('#comment-editor');
        if (!form) return;
        const parentInput = $('#id_parent_id', form);
        if (parentInput) parentInput.value = parentId;
        if (editor) activeEmojiTarget = editor;
        const hint = $('#reply-hint');
        if (hint) hint.remove();
        const box = document.createElement('div');
        box.id = 'reply-hint';
        box.className = 'reply-hint';
        box.innerHTML = `<span>正在回复 <b>@${escapeHtml(authorName)}</b></span>
            <button type="button" title="取消回复">&times;</button>`;
        const mount = $('#reply-hint-mount') || editor || form;
        mount.parentNode.insertBefore(box, mount);
        $('button', box).addEventListener('click', () => {
            if (parentInput) parentInput.value = '';
            box.remove();
        });
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    }

    // 编辑框聚焦态 + 字数统计
    function initEditors(scope = document) {
        $$('.editor-box textarea', scope).forEach((ta) => {
            if (ta.dataset.ready) return;
            ta.dataset.ready = '1';
            const box = ta.closest('.editor-box');
            ta.addEventListener('focus', () => box && box.classList.add('focused'));
            ta.addEventListener('blur', () => box && box.classList.remove('focused'));
            ta.addEventListener('input', () => {
                ta.style.height = 'auto';
                ta.style.height = Math.min(ta.scrollHeight, 420) + 'px';
                updateCounter(ta);
            });
            ta.addEventListener('keydown', (ev) => {
                // Ctrl / Cmd + Enter 快捷发送
                if ((ev.ctrlKey || ev.metaKey) && ev.key === 'Enter') {
                    ev.preventDefault();
                    const form = ta.closest('form');
                    if (form) form.requestSubmit ? form.requestSubmit() : form.submit();
                }
            });
        });
    }

    function updateCounter(ta) {
        const counter = ta.closest('.editor-main, .editor') ?
            $('.editor-count', ta.closest('.editor-main, .editor')) : null;
        if (!counter) return;
        const max = parseInt(counter.dataset.max || '1000', 10);
        const len = ta.value.length;
        counter.textContent = `${len} / ${max}`;
        counter.classList.toggle('warn', len > max * 0.85 && len <= max);
        counter.classList.toggle('over', len > max);
    }

    function initCounters(scope = document) {
        $$('.editor-box textarea', scope).forEach(updateCounter);
    }

    // 图片选择预览
    document.addEventListener('change', (e) => {
        const input = e.target.closest('.comment-image-input');
        if (!input) return;
        const wrap = input.closest('.editor-main, .editor');
        let preview = wrap ? $('.image-preview', wrap) : null;
        if (preview) preview.remove();
        if (!input.files || !input.files[0]) return;
        const file = input.files[0];
        if (file.size > 5 * 1024 * 1024) {
            toast('图片超过 5MB，请压缩后再上传', 'err');
            input.value = '';
            return;
        }
        preview = document.createElement('div');
        preview.className = 'image-preview';
        const img = document.createElement('img');
        img.src = URL.createObjectURL(file);
        img.alt = '配图预览';
        const rm = document.createElement('button');
        rm.type = 'button';
        rm.innerHTML = '&times;';
        rm.title = '移除图片';
        rm.addEventListener('click', () => { input.value = ''; preview.remove(); });
        preview.appendChild(img);
        preview.appendChild(rm);
        const toolbar = wrap ? $('.editor-toolbar', wrap) : null;
        if (toolbar) toolbar.after(preview);
        else if (wrap) wrap.appendChild(preview);
    });

    // 主评论表单：AJAX 提交
    document.addEventListener('submit', async (e) => {
        const form = e.target.closest('#comment-form');
        if (!form) return;
        e.preventDefault();
        const btn = $('button[type="submit"]', form) || $('.submit-comment', form);
        const ta = $('textarea', form);
        const fileInput = $('input[type="file"]', form);
        if (ta && !ta.value.trim() && !(fileInput && fileInput.files && fileInput.files.length)) {
            toast('说点什么再发送吧～', 'err');
            ta.focus();
            return;
        }
        const original = btn ? btn.innerHTML : '';
        if (btn) { btn.disabled = true; btn.innerHTML = '发送中…'; }
        try {
            const json = await post(form.action, new FormData(form));
            if (json.ok) {
                swapComments(json.html, { keepExpanded: false });
                form.reset();
                const hint = $('#reply-hint');
                if (hint) hint.remove();
                const preview = $('.image-preview');
                if (preview) preview.remove();
                if (ta) { ta.style.height = 'auto'; updateCounter(ta); }
                toast(json.message || '评论发布成功');
                const first = $('#comments .comment');
                if (first) flash(first);
            } else {
                toast(json.error || '评论失败', 'err');
            }
        } catch (err) {
            toast(err.message || '评论失败，请稍后重试', 'err');
        } finally {
            if (btn) { btn.disabled = false; btn.innerHTML = original; }
        }
    });

    // 评论区的点击交互（事件委托，AJAX 重渲染后依然有效）
    document.addEventListener('click', async (e) => {
        const root = commentsRoot();
        if (!root || !root.contains(e.target)) return;

        // 点赞评论
        const likeBtn = e.target.closest('.js-comment-like');
        if (likeBtn) {
            if (likeBtn.dataset.busy) return;
            likeBtn.dataset.busy = '1';
            try {
                const json = await post(likeBtn.dataset.url);
                if (json.ok) {
                    const n = $('.n', likeBtn);
                    if (n) n.textContent = json.count;
                    likeBtn.classList.toggle('liked', json.liked);
                    if (json.liked) vibrate(likeBtn);
                }
            } catch (err) { toast(err.message, 'err'); }
            finally { delete likeBtn.dataset.busy; }
            return;
        }

        // 回复
        const replyBtn = e.target.closest('.js-reply') || e.target.closest('.reply-at');
        if (replyBtn) {
            if (e.target.closest('.reply-at')) e.preventDefault();
            const comment = replyBtn.closest('.comment');
            setReplyTarget(comment, replyBtn.dataset.author, replyBtn.dataset.parent || comment.dataset.id);
            const ta = $('#comment-editor');
            if (ta) {
                ta.focus();
                ta.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
            return;
        }

        // 展开楼中楼
        const moreBtn = e.target.closest('.reply-more');
        if (moreBtn) {
            const comment = moreBtn.closest('.comment');
            const box = $('.replies', comment);
            if (!box) return;
            $$('.reply-extra', box).forEach((el) => el.classList.remove('hidden'));
            moreBtn.remove();
            comment.classList.add('expanded');
            initEditors(box);
            return;
        }

        // 删除评论
        const delBtn = e.target.closest('.js-comment-delete');
        if (delBtn) {
            if (!confirm('确定删除这条评论吗？删除后楼层会保留占位。')) return;
            try {
                const json = await post(delBtn.dataset.url);
                if (json.ok) { swapComments(json.html); toast('评论已删除'); }
            } catch (err) { toast(err.message, 'err'); }
            return;
        }

        // 评论排序
        const sortBtn = e.target.closest('.comments-sort button');
        if (sortBtn) {
            $$('.comments-sort button').forEach((b) => b.classList.toggle('active', b === sortBtn));
            await loadComments(sortBtn.dataset.sort, 1);
            return;
        }

        // 评论分页
        const pageBtn = e.target.closest('.js-comment-page');
        if (pageBtn) {
            await loadComments(pageBtn.dataset.sort, pageBtn.dataset.page);
            const box = commentsRoot();
            if (box) box.scrollIntoView({ behavior: 'smooth', block: 'start' });
            return;
        }
    });

    async function loadComments(sort, page) {
        const root = commentsRoot();
        if (!root) return;
        const url = `${root.dataset.url}?sort=${sort}&cpage=${page}`;
        root.classList.add('loading');
        const loader = document.createElement('div');
        loader.className = 'comments-loading';
        loader.innerHTML = '<div class="spin"></div>正在加载评论…';
        const list = $('#comment-list', root) || root;
        const original = list.innerHTML;
        list.innerHTML = '';
        list.appendChild(loader);
        try {
            const res = await fetch(url, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin',
            });
            const json = await res.json();
            if (json.ok) swapComments(json.html, { keepExpanded: false });
            else { list.innerHTML = original; toast('加载评论失败', 'err'); }
        } catch (err) {
            list.innerHTML = original;
            toast('加载评论失败，请检查网络', 'err');
        } finally {
            root.classList.remove('loading');
        }
    }

    // 提示条 / 加载更多评论（整页跳转版）
    function initComments() {
        initEditors(commentsRoot() || document);
        initCounters(commentsRoot() || document);
        const hint = $('#reply-hint');
        if (hint) {
            const btn = $('button', hint);
            if (btn) {
                btn.addEventListener('click', () => {
                    const parentInput = $('#id_parent_id');
                    if (parentInput) parentInput.value = '';
                    hint.remove();
                });
            }
        }
    }
    initComments();

    /* ---------- 6. 文章点赞 / 点踩 / 收藏 ---------- */
    function flash(el) {
        el.style.transition = 'background .5s';
        const old = el.style.background;
        el.style.background = 'var(--brand-light)';
        setTimeout(() => { el.style.background = old; }, 900);
    }

    document.addEventListener('click', async (e) => {
        const btn = e.target.closest('.js-vote');
        if (btn) {
            e.preventDefault();
            if (btn.dataset.busy) return;
            btn.dataset.busy = '1';
            try {
                const json = await post(btn.dataset.url, { value: btn.dataset.value });
                if (json.ok) {
                    const likeBtn = $('.js-vote[data-value="1"]');
                    const dislikeBtn = $('.js-vote[data-value="-1"]');
                    if (likeBtn) {
                        $('.n', likeBtn).textContent = json.like_count;
                        likeBtn.classList.toggle('active', json.my_vote === 1);
                        likeBtn.classList.toggle('active-like', json.my_vote === 1);
                    }
                    if (dislikeBtn) {
                        $('.n', dislikeBtn).textContent = json.dislike_count;
                        dislikeBtn.classList.toggle('active', json.my_vote === -1);
                    }
                    if (json.my_vote !== 0) vibrate(btn);
                    toast(json.my_vote === 0 ? '已取消'
                        : json.my_vote === 1 ? '感谢点赞 ❤' : '已踩，我们会改进的');
                }
            } catch (err) { toast(err.message, 'err'); }
            finally { delete btn.dataset.busy; }
            return;
        }

        const bm = e.target.closest('.js-bookmark');
        if (bm) {
            e.preventDefault();
            if (bm.dataset.busy) return;
            bm.dataset.busy = '1';
            try {
                const json = await post(bm.dataset.url);
                if (json.ok) {
                    bm.classList.toggle('active', json.bookmarked);
                    const n = $('.n', bm);
                    if (n) n.textContent = json.count;
                    if (json.bookmarked) vibrate(bm);
                    toast(json.bookmarked ? '已加入收藏 ⭐' : '已取消收藏');
                }
            } catch (err) { toast(err.message, 'err'); }
            finally { delete bm.dataset.busy; }
        }
    });

    /* ---------- 7. 图片灯箱 ---------- */
    function openLightbox(src) {
        let box = $('.lightbox');
        if (!box) {
            box = document.createElement('div');
            box.className = 'lightbox';
            box.innerHTML = '<button class="lb-close" title="关闭">&times;</button><img alt="">';
            document.body.appendChild(box);
            box.addEventListener('click', (ev) => {
                if (ev.target === box || ev.target.closest('.lb-close')) box.classList.remove('open');
            });
        }
        $('img', box).src = src;
        box.classList.add('open');
    }
    document.addEventListener('click', (e) => {
        const img = e.target.closest('.markdown-body img, .comment-image img');
        if (!img) return;
        e.preventDefault();
        openLightbox(img.src);
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            $$('.lightbox.open').forEach((el) => el.classList.remove('open'));
            $$('.emoji-panel.open').forEach((el) => el.classList.remove('open'));
        }
    });

    /* ---------- 8. 阅读进度 + 目录高亮 ---------- */
    function initReadProgress() {
        const bar = $('.read-progress');
        const article = $('.markdown-body');
        if (!bar || !article) return;
        const onScroll = () => {
            const rect = article.getBoundingClientRect();
            const total = rect.height - window.innerHeight;
            const passed = Math.min(Math.max(-rect.top, 0), Math.max(total, 1));
            bar.style.width = (total > 0 ? (passed / total) * 100 : 100) + '%';
        };
        window.addEventListener('scroll', onScroll, { passive: true });
        onScroll();
    }

    function initToc() {
        const links = $$('.toc-widget a');
        if (!links.length) return;
        const headings = links
            .map((a) => document.getElementById(decodeURIComponent(a.hash.slice(1))))
            .filter(Boolean);
        if (!headings.length) return;
        const onScroll = () => {
            let active = headings[0];
            headings.forEach((h) => {
                if (h.getBoundingClientRect().top <= 120) active = h;
            });
            links.forEach((a) => {
                a.classList.toggle('active',
                    decodeURIComponent(a.hash.slice(1)) === active.id);
            });
        };
        window.addEventListener('scroll', onScroll, { passive: true });
        onScroll();
    }

    /* ---------- 9. 编辑器字数 / Markdown 快捷键 ---------- */
    function initPostEditor() {
        const ta = $('.markdown-editor');
        if (!ta) return;
        ta.addEventListener('keydown', (e) => {
            if (e.key !== 'Tab') return;
            e.preventDefault();
            insertAtCursor(ta, '    ');
        });
    }

    /* ---------- 10. 通知轮询 ---------- */
    function initNotifPoll() {
        const dot = $('#notif-dot');
        if (!dot || !window.DJANGO_BLOG || !window.DJANGO_BLOG.notifPollUrl) return;
        setInterval(async () => {
            try {
                const res = await fetch(window.DJANGO_BLOG.notifPollUrl, {
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                    credentials: 'same-origin',
                });
                const json = await res.json();
                if (json.unread > 0) {
                    dot.textContent = json.unread > 99 ? '99+' : json.unread;
                    dot.classList.remove('hidden');
                } else {
                    dot.classList.add('hidden');
                }
            } catch (e) { /* 静默失败，不打扰用户 */ }
        }, 60000);
    }

    /* ---------- 启动 ---------- */
    // 脚本在 </body> 前加载，DOM 此时已就绪，直接初始化即可
    initEditors();
    initCounters();
    initComments();
    initReadProgress();
    initToc();
    initPostEditor();
    initNotifPoll();

    // 暴露给模板内联脚本使用
    window.DjangoBlog = { toast, post, insertAtCursor, swapComments, flash, openLightbox };
})();

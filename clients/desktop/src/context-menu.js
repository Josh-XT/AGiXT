/* Custom right-click menu.
 *
 * Tauri's webkit2gtk shows the dev "Inspect Element" menu by default.
 * That's noisy in a shipped client and unhelpful for end users, so we
 * suppress the native contextmenu globally and replace it with a small
 * action menu scoped to two things:
 *   - Messages: Copy message, Copy selection (if any), Copy URL (when
 *     the right-click landed on a link).
 *   - Composer textarea: Cut / Copy / Paste / Select all.
 * Right-clicking anywhere else just dismisses any open menu and shows
 * nothing — we don't want to expose dev tools or browser plumbing.
 */
(function () {
  function el(tag, cls, txt) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt != null) e.textContent = txt;
    return e;
  }

  // Single shared menu element. Built lazily on first invocation.
  let menuEl = null;

  function ensureMenuEl() {
    if (menuEl) return menuEl;
    menuEl = el('div', 'ctx-menu');
    menuEl.setAttribute('role', 'menu');
    menuEl.setAttribute('hidden', '');
    document.body.appendChild(menuEl);
    return menuEl;
  }

  function hideMenu() {
    if (!menuEl) return;
    menuEl.hidden = true;
    menuEl.innerHTML = '';
  }

  function showMenu(x, y, items) {
    const m = ensureMenuEl();
    m.innerHTML = '';
    items.forEach((item) => {
      if (item === '-') {
        m.appendChild(el('div', 'ctx-menu-sep'));
        return;
      }
      const btn = el('button', 'ctx-menu-item', item.label);
      btn.type = 'button';
      btn.disabled = !!item.disabled;
      if (!item.disabled) {
        btn.addEventListener('click', () => {
          hideMenu();
          try { item.onClick(); }
          catch (e) { console.warn('ctx menu action failed', e); }
        });
      }
      m.appendChild(btn);
    });
    m.hidden = false;
    // Position. Keep within viewport.
    const w = m.offsetWidth || 180;
    const h = m.offsetHeight || 40;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const px = Math.min(x, vw - w - 4);
    const py = Math.min(y, vh - h - 4);
    m.style.left = `${Math.max(4, px)}px`;
    m.style.top = `${Math.max(4, py)}px`;
  }

  // What target was right-clicked? Returns one of:
  //   'message'       — inside a chat message bubble
  //   'composer'      — inside the textarea / input field
  //   null            — anywhere else (no menu shown)
  function classifyTarget(target) {
    if (!target) return { kind: null };
    const message = target.closest && target.closest('.message');
    if (message) {
      const link = target.closest && target.closest('a[href]');
      return { kind: 'message', message, link };
    }
    const editable =
      target.closest && (target.closest('textarea') || target.closest('input[type="text"], input[type="search"], input[type="email"], input[type="url"], input[type="password"], [contenteditable="true"]'));
    if (editable) return { kind: 'composer', field: editable };
    return { kind: null };
  }

  async function copy(text) {
    if (text == null) return;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(String(text));
        return;
      }
    } catch (_) { /* fall through to execCommand */ }
    // execCommand fallback for older webviews.
    const tmp = document.createElement('textarea');
    tmp.value = String(text);
    tmp.style.position = 'fixed';
    tmp.style.opacity = '0';
    document.body.appendChild(tmp);
    tmp.select();
    try { document.execCommand('copy'); } catch (_) { /* ignore */ }
    document.body.removeChild(tmp);
  }

  async function paste(field) {
    if (!field) return;
    let text = '';
    try {
      if (navigator.clipboard && navigator.clipboard.readText) {
        text = await navigator.clipboard.readText();
      }
    } catch (_) { return; }
    if (!text) return;
    // Insert at cursor.
    const start = field.selectionStart || 0;
    const end = field.selectionEnd || 0;
    const value = field.value || '';
    field.value = value.slice(0, start) + text + value.slice(end);
    const caret = start + text.length;
    field.selectionStart = field.selectionEnd = caret;
    field.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function getMessageText(msg) {
    if (!msg) return '';
    // Prefer the markdown body if present (assistant), fall back to all
    // text in the message wrapper otherwise.
    const md = msg.querySelector('.bubble .md');
    if (md && md.innerText) return md.innerText.trim();
    const bubble = msg.querySelector('.bubble');
    if (bubble) return bubble.innerText.trim();
    return msg.innerText.trim();
  }

  function selectionText() {
    const s = window.getSelection ? window.getSelection().toString() : '';
    return s || '';
  }

  document.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    const cls = classifyTarget(e.target);
    if (cls.kind === 'message') {
      const sel = selectionText();
      const items = [];
      if (sel) {
        items.push({ label: 'Copy selection', onClick: () => copy(sel) });
      }
      items.push({
        label: 'Copy message',
        onClick: () => copy(getMessageText(cls.message)),
      });
      if (cls.link) {
        const href = cls.link.getAttribute('href') || '';
        items.push('-');
        items.push({ label: 'Copy link address', onClick: () => copy(href) });
      }
      showMenu(e.clientX, e.clientY, items);
      return;
    }
    if (cls.kind === 'composer') {
      const f = cls.field;
      const hasSel = (f.selectionEnd || 0) > (f.selectionStart || 0);
      const hasValue = !!(f.value || (f.textContent || '')).length;
      const items = [
        {
          label: 'Cut',
          disabled: !hasSel,
          onClick: async () => {
            const v = f.value || '';
            const a = f.selectionStart || 0;
            const b = f.selectionEnd || 0;
            await copy(v.slice(a, b));
            f.value = v.slice(0, a) + v.slice(b);
            f.selectionStart = f.selectionEnd = a;
            f.dispatchEvent(new Event('input', { bubbles: true }));
          },
        },
        {
          label: 'Copy',
          disabled: !hasSel,
          onClick: () => {
            const v = f.value || '';
            const a = f.selectionStart || 0;
            const b = f.selectionEnd || 0;
            copy(v.slice(a, b));
          },
        },
        { label: 'Paste', onClick: () => paste(f) },
        '-',
        {
          label: 'Select all',
          disabled: !hasValue,
          onClick: () => { f.focus(); f.select && f.select(); },
        },
      ];
      showMenu(e.clientX, e.clientY, items);
      return;
    }
    // Anywhere else: just dismiss any open menu — no inspect, no nothing.
    hideMenu();
  });

  document.addEventListener('mousedown', (e) => {
    if (menuEl && !menuEl.hidden && !menuEl.contains(e.target)) hideMenu();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && menuEl && !menuEl.hidden) hideMenu();
  });
  window.addEventListener('blur', hideMenu);
  window.addEventListener('scroll', hideMenu, true);
})();

/* Desktop-extensions loader.
 *
 * Pulls the manifest of UI pages this client is entitled to render
 * from the AGiXT backend (GET /v1/desktop/extensions), then lazy-loads
 * each page's main.js as a blob: import on first activation.
 *
 * The loader owns three things:
 *   1. The HTTP fetch + ETag-keyed re-poll (boot, periodic, and
 *      on-demand via window.AgixtDesktopExtensions.refresh()).
 *   2. The DOM scaffolding — adds a `.sidenav-btn[data-view=<id>]`
 *      under `.sidenav-top` and a sibling `.view-pane[data-view=<id>]`
 *      inside `.chat-screen-main` for each entry, so the existing
 *      `AgixtSidenav.setActiveView()` machinery handles tab switches
 *      without modification.
 *   3. The lifecycle around each extension's exported controller:
 *      the page module calls `window.AgixtRegisterExtension(id, ctrl)`
 *      at top-level, the loader holds the registration, and on first
 *      activation it invokes `ctrl.mount(container, ctx)`. `ctx` carries
 *      the same SDK handles the chat/workspace already use.
 *
 * Trust model: extensions are first-party (closed-source, served by the
 * AGiXT instance the user has authenticated against), so the JS is
 * loaded directly with full window scope. The only sandbox guarantee
 * is that the URL the JS is fetched from must already be on the same
 * origin the JWT was minted by. CSP allows `blob:` for script-src so
 * the import works without widening the policy per-server.
 */
(function () {
  const tauri = window.__TAURI__;
  if (!tauri) return;

  // id -> { entry, mounted, activating, ctrl, blobUrl }
  const state = new Map();
  // id -> function/object that returns contextual text for the user's
  // current surface inside that extension. Sampled only when the user
  // sends a chat turn, so providers can compute from live DOM/player
  // state without keeping a central cache hot.
  const contextProviders = new Map();
  // id -> { mount, unmount } — populated transiently when an extension
  // module evaluates and calls AgixtRegisterExtension. We pop it back
  // into state.ctrl right after the import resolves.
  const pendingRegistrations = new Map();
  let lastEtag = null;
  let pollTimer = null;

  // The hook every extension's main.js calls at top level.
  window.AgixtRegisterExtension = function (id, ctrl) {
    if (!id || typeof ctrl !== 'object' || typeof ctrl.mount !== 'function') {
      console.warn('AgixtRegisterExtension: invalid registration', id);
      return;
    }
    pendingRegistrations.set(id, ctrl);
  };

  function ctx() {
    if (typeof window.AgixtAppContext !== 'function') return null;
    return window.AgixtAppContext();
  }

  function registerContextProvider(id, provider) {
    if (!id || !provider) return () => {};
    if (typeof provider !== 'function'
        && !(provider && typeof provider.getContext === 'function')) {
      console.warn('desktop-extensions: invalid context provider', id);
      return () => {};
    }
    contextProviders.set(id, provider);
    window.dispatchEvent(new CustomEvent('agixt-extension-context-changed', {
      detail: { id, registered: true },
    }));
    return () => unregisterContextProvider(id, provider);
  }

  function unregisterContextProvider(id, provider) {
    if (!id) return;
    if (provider && contextProviders.get(id) !== provider) return;
    contextProviders.delete(id);
    window.dispatchEvent(new CustomEvent('agixt-extension-context-changed', {
      detail: { id, registered: false },
    }));
  }

  function currentActiveView() {
    const sidenav = window.AgixtSidenav;
    if (sidenav && typeof sidenav.getActiveView === 'function') {
      const value = sidenav.getActiveView();
      if (value) return value;
    }
    const activeBtn = document.querySelector('.sidenav-btn.is-active[data-view]');
    if (activeBtn && activeBtn.dataset.view) return activeBtn.dataset.view;
    const visiblePane = Array.from(document.querySelectorAll('.chat-screen-main .view-pane[data-view]'))
      .find((pane) => pane.dataset.view !== 'chat' && !pane.hidden);
    return visiblePane ? visiblePane.dataset.view : 'chat';
  }

  function extensionLabel(id) {
    const rec = state.get(id);
    return (rec && rec.entry && (rec.entry.label || rec.entry.title)) || id;
  }

  function compactText(value, maxLen) {
    const text = String(value == null ? '' : value).trim();
    if (!maxLen || text.length <= maxLen) return text;
    return text.slice(0, maxLen - 1).trimEnd() + '…';
  }

  function formatContextValue(id, value) {
    if (value == null || value === false) return '';
    let label = extensionLabel(id);
    let body = '';
    if (typeof value === 'string') {
      body = value.trim();
    } else if (Array.isArray(value)) {
      body = value.map((x) => String(x == null ? '' : x).trim()).filter(Boolean).join('\n');
    } else if (typeof value === 'object') {
      label = value.label || value.title || label;
      if (typeof value.context === 'string') body = value.context;
      else if (typeof value.markdown === 'string') body = value.markdown;
      else if (typeof value.text === 'string') body = value.text;
      else {
        const lines = [];
        if (value.summary) lines.push(String(value.summary));
        if (Array.isArray(value.lines)) {
          for (const line of value.lines) {
            if (line != null && String(line).trim()) lines.push(String(line).trim());
          }
        }
        if (value.data && typeof value.data === 'object') {
          try { lines.push('```json\n' + JSON.stringify(value.data, null, 2) + '\n```'); }
          catch (_) {}
        }
        body = lines.join('\n');
      }
    }
    body = compactText(body, 8000);
    if (!body) return '';
    return [
      `## Current ${label} Desktop Extension Context`,
      'This context comes from the desktop page the user currently has open. Use it when it helps answer the user, but do not treat it as a new user request.',
      '',
      body,
    ].join('\n');
  }

  function readContextProvider(id) {
    const provider = contextProviders.get(id);
    if (!provider) return '';
    try {
      const raw = typeof provider === 'function'
        ? provider()
        : provider.getContext();
      return formatContextValue(id, raw);
    } catch (err) {
      console.warn('desktop-extensions: context provider failed', id, err);
      return '';
    }
  }

  function getActiveContext() {
    const id = currentActiveView();
    if (!id || id === 'chat') return '';
    return readContextProvider(id);
  }

  function getAllContexts() {
    const items = [];
    for (const id of contextProviders.keys()) {
      const text = readContextProvider(id);
      if (text) items.push({ id, text });
    }
    return items;
  }

  function makeMountContext(id, rec, pane) {
    const c = ctx();
    if (!c) return null;
    const framed = isFramed(rec.entry);
    const headerEl = framed
      ? pane.querySelector(':scope > .ext-pane-header')
      : null;
    const headerActionsEl = framed
      ? pane.querySelector(':scope > .ext-pane-header > .ext-pane-actions')
      : null;
    return Object.assign({}, c, {
      extensionId: id,
      // Framed-layout helpers. `headerEl` and `headerActionsEl` are null
      // for unframed extensions so old extensions can defensively check
      // before appending. `setHeaderActions(...nodes)` is sugar that
      // clears the slot and appends the given nodes — most extensions
      // call it once at mount time with their refresh/search controls.
      framed,
      headerEl,
      headerActionsEl,
      setHeaderActions: function () {
        if (!headerActionsEl) return false;
        headerActionsEl.innerHTML = '';
        for (let i = 0; i < arguments.length; i++) {
          const node = arguments[i];
          if (node) headerActionsEl.appendChild(node);
        }
        return true;
      },
      registerContextProvider: (provider) => {
        const unsubscribe = registerContextProvider(id, provider);
        rec.contextUnsubscribe = unsubscribe;
        return () => {
          if (rec.contextUnsubscribe === unsubscribe) rec.contextUnsubscribe = null;
          unsubscribe();
        };
      },
      notifyContextChanged: () => {
        window.dispatchEvent(new CustomEvent('agixt-extension-context-changed', {
          detail: { id },
        }));
      },
    });
  }

  function buildUrl(base, path, params) {
    const u = new URL(path, base);
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v) u.searchParams.set(k, v);
      }
    }
    return u.toString();
  }

  async function fetchManifest() {
    const c = ctx();
    if (!c || !c.serverUrl || !c.jwt) return null;
    const url = buildUrl(c.serverUrl, '/v1/desktop/extensions', {
      company_id: c.companyId,
      agent_id: c.agentId,
    });
    const headers = { Authorization: `Bearer ${c.jwt}` };
    if (lastEtag) headers['If-None-Match'] = lastEtag;
    let resp;
    try {
      resp = await fetch(url, { headers });
    } catch (err) {
      console.warn('desktop-extensions: manifest fetch failed', err);
      return null;
    }
    if (resp.status === 304) return null;
    if (!resp.ok) {
      console.warn('desktop-extensions: manifest http', resp.status);
      return null;
    }
    lastEtag = resp.headers.get('etag') || null;
    try {
      return await resp.json();
    } catch (err) {
      console.warn('desktop-extensions: manifest parse failed', err);
      return null;
    }
  }

  // Built-in monochrome icon set used by the sidenav. Manifests reference
  // these by name (`"icon": "machines"`), and the loader renders them as
  // `currentColor` SVGs so they pick up the active/hover treatments
  // alongside the bundled chat + settings icons.
  //
  // To add a new icon: drop a Lucide-style 24×24 path string here and
  // reference it from the relevant manifest. Extensions that need a
  // bespoke glyph can also ship an `"icon_svg": "<path…>"` field on the
  // manifest entry which overrides the registry.
  const SIDENAV_ICONS = {
    machines:    '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/>',
    tickets:     '<path d="M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2z"/><path d="M13 5v2"/><path d="M13 11v2"/><path d="M13 17v2"/>',
    companies:   '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01"/><path d="M16 6h.01"/><path d="M12 6h.01"/><path d="M12 10h.01"/><path d="M12 14h.01"/><path d="M16 10h.01"/><path d="M16 14h.01"/><path d="M8 10h.01"/><path d="M8 14h.01"/>',
    contacts:    '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    monitors:    '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    deployments: '<path d="m7.5 4.27 9 5.15"/><path d="M21 8L12 13 3 8"/><path d="M3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8z"/>',
    patches:     '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    network:     '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a14.5 14.5 0 0 0 0 20"/><path d="M12 2a14.5 14.5 0 0 1 0 20"/>',
    chat:        '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    secrets:     '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    assets:      '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><path d="M3.27 6.96 12 12.01l8.73-5.05"/><path d="M12 22.08V12"/>',
    dashboard:   '<rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="5"/><rect x="14" y="12" width="7" height="9"/><rect x="3" y="16" width="7" height="5"/>',
    webhooks:    '<path d="M18 16.98h-5.99c-1.1 0-1.95.94-2.48 1.9A4 4 0 0 1 2 17c.01-.7.2-1.4.57-2"/><path d="m6 17 3.13-5.78c.53-.97.43-2.22-.26-3.07A4 4 0 0 1 12 1c.7 0 1.4.18 2 .5"/><path d="m12 6 3.13 5.73C15.66 12.7 16.9 13 18 13a4 4 0 0 1 0 8 4 4 0 0 1-3.87-3"/>',
    tasks:       '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
    team:        '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    billing:     '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/>',
  };

  function paintSidenavIcon(span, entry) {
    span.innerHTML = '';
    const inline = entry.icon_svg && String(entry.icon_svg).trim();
    const named = entry.icon && SIDENAV_ICONS[entry.icon];
    const paths = inline || named;
    if (paths) {
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', '0 0 24 24');
      svg.setAttribute('width', '20');
      svg.setAttribute('height', '20');
      svg.setAttribute('fill', 'none');
      svg.setAttribute('stroke', 'currentColor');
      svg.setAttribute('stroke-width', '1.8');
      svg.setAttribute('stroke-linecap', 'round');
      svg.setAttribute('stroke-linejoin', 'round');
      svg.setAttribute('aria-hidden', 'true');
      svg.innerHTML = paths;
      span.appendChild(svg);
      return;
    }
    // Fall back to emoji or first letter of label.
    span.textContent = entry.icon || (entry.label ? entry.label[0] : '?');
  }

  // Persisted user order for the middle-group buttons. Chat is pinned
  // to the top of `.sidenav-top` and ignored in this list; admin-slot
  // entries (companies) are pinned to `.sidenav-bottom` before
  // settings and also ignored here.
  const SIDENAV_ORDER_KEY = 'agixt.desktop.sidenav.order.v1';
  function loadSidenavOrder() {
    try {
      const raw = window.localStorage.getItem(SIDENAV_ORDER_KEY);
      if (!raw) return [];
      const arr = JSON.parse(raw);
      return Array.isArray(arr) ? arr.filter((s) => typeof s === 'string') : [];
    } catch (_) { return []; }
  }
  function saveSidenavOrder(arr) {
    try { window.localStorage.setItem(SIDENAV_ORDER_KEY, JSON.stringify(arr)); }
    catch (_) {}
  }

  // Re-order DOM children of `.sidenav-top` to match the persisted
  // order. Chat stays first; entries not in the saved list go to the
  // end (newly registered extensions append after the user's order).
  // Buttons marked `data-pinned-first="true"` (currently the Chat icon)
  // stay locked at the start of the rail regardless of the user's saved
  // drag-order. They're also excluded from the persisted order list so a
  // capture pass after the user reorders other buttons can't accidentally
  // drop them out of the pinned slot.
  function isPinnedFirst(btn) {
    return !!(btn && btn.dataset && btn.dataset.pinnedFirst === 'true');
  }
  function applySidenavOrder() {
    const top = document.querySelector('.sidenav-top');
    if (!top) return;
    const order = loadSidenavOrder();
    const pinned = Array.from(top.querySelectorAll('.sidenav-btn[data-view]'))
      .filter(isPinnedFirst);
    const all = Array.from(top.querySelectorAll('.sidenav-btn[data-view]'))
      .filter((b) => !isPinnedFirst(b));
    const orderedKnown = order
      .map((id) => all.find((b) => b.dataset.view === id))
      .filter(Boolean);
    const newcomers = all.filter((b) => order.indexOf(b.dataset.view) === -1);
    // Re-append in the desired order. appendChild on existing nodes
    // moves them, doesn't duplicate.
    for (const b of pinned)       top.appendChild(b);
    for (const b of orderedKnown) top.appendChild(b);
    for (const b of newcomers)    top.appendChild(b);
  }

  // Capture the current visual order of middle-group buttons and
  // persist. Called after a successful drop.
  function captureSidenavOrder() {
    const top = document.querySelector('.sidenav-top');
    if (!top) return;
    const ids = Array.from(top.querySelectorAll('.sidenav-btn[data-view]'))
      .filter((b) => !isPinnedFirst(b))
      .map((b) => b.dataset.view)
      .filter(Boolean);
    saveSidenavOrder(ids);
  }

  // ----- Overflow handling ------------------------------------------------
  // When the window is too short to show every middle-group button, hide
  // the tail items (`.is-overflow-hidden`) and surface a "More" button
  // (`···`) as the last visible row. Clicking it opens a popover with the
  // hidden items; each row activates its view on click and can be dragged
  // back into the visible rail to pin it.
  let _morePopover = null;
  let _moreCloseTimer = null;

  function ensureMoreBtn(top) {
    let btn = top.querySelector('.sidenav-more-btn');
    if (btn) return btn;
    btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'sidenav-btn sidenav-more-btn';
    btn.title = 'More';
    btn.setAttribute('aria-label', 'More extensions');
    btn.setAttribute('data-tooltip', 'More');
    btn.setAttribute('aria-haspopup', 'menu');
    btn.setAttribute('aria-expanded', 'false');
    // Three dots — vertically stacked since the rail is vertical, but
    // horizontal "···" reads more universally as overflow. Use horizontal.
    for (let i = 0; i < 3; i++) {
      const dot = document.createElement('span');
      dot.className = 'more-dot';
      btn.appendChild(dot);
    }
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleMorePopover(btn);
    });
    return btn;
  }

  function reflowSidenavOverflow() {
    const top = document.querySelector('.sidenav-top');
    if (!top) return;
    const all = Array.from(top.querySelectorAll('.sidenav-btn[data-view]'));
    // Reset state.
    all.forEach((b) => b.classList.remove('is-overflow-hidden'));
    let moreBtn = top.querySelector('.sidenav-more-btn');
    if (moreBtn) {
      moreBtn.remove();
      moreBtn = null;
    }
    // Compute the available height for the top group from the parent
    // sidenav's geometry, not `top.clientHeight`. If the flexbox sizing
    // doesn't actually shrink the top group (e.g. a stylesheet override
    // breaks `min-height: 0`), `top.clientHeight === top.scrollHeight`
    // and the original `scrollHeight > clientHeight` test never fires.
    // Measuring against the parent is reliable regardless of how the
    // browser resolved the flex sizes.
    const sidenav = top.closest('.sidenav');
    if (!sidenav) { closeMorePopover(); return; }
    const sidenavRect = sidenav.getBoundingClientRect();
    if (!sidenavRect.height) {
      // Hidden ancestor (auth screen still showing, etc.) — nothing to do.
      closeMorePopover();
      return;
    }
    const bottom = sidenav.querySelector('.sidenav-bottom');
    const bottomH = bottom ? bottom.getBoundingClientRect().height : 0;
    const cs = getComputedStyle(sidenav);
    const padV = parseFloat(cs.paddingTop || 0) + parseFloat(cs.paddingBottom || 0);
    // Floor at 0 — if the bottom group alone is taller than the sidenav
    // (window absurdly short), there's no room for the top at all and
    // every button gets hidden into the More popover.
    const availableH = Math.max(0, sidenavRect.height - bottomH - padV);
    // Width of an item including the column gap below it. Use the first
    // visible button (or the brand if there are no buttons yet) to
    // measure — all items in `.sidenav-top` share the same row height.
    function itemH(el) {
      if (!el) return 0;
      const r = el.getBoundingClientRect();
      return r.height;
    }
    const brand = top.querySelector('.sidenav-brand');
    const brandH = itemH(brand);
    const gap = parseFloat(getComputedStyle(top).rowGap || getComputedStyle(top).gap || 0) || 0;
    // The brand contributes its own height + bottom margin (set in CSS
    // via `margin-bottom: 6px`). getBoundingClientRect already includes
    // the box but not the margin — add it manually so we don't
    // overshoot the available space.
    const brandMb = brand ? parseFloat(getComputedStyle(brand).marginBottom || 0) : 0;
    // Heights of each candidate row in `top`, in DOM order excluding the
    // brand (which is fixed) and the more button (added below).
    const rowH = all.map(itemH);
    // Reserve enough room for the More button so we know how many real
    // buttons can stay visible alongside it. Create it lazily so we
    // don't pay the DOM cost when there's no overflow.
    moreBtn = ensureMoreBtn(top);
    // Temporarily insert to measure, then remove if we don't need it.
    top.appendChild(moreBtn);
    const moreH = itemH(moreBtn);
    moreBtn.remove();
    // Required space for "nothing overflows" = brand + every row + (n-1) gaps.
    function totalH(n) {
      const rows = (brand ? 1 : 0) + n;
      const heights = (brand ? brandH + brandMb : 0)
        + rowH.slice(0, n).reduce((a, b) => a + b, 0);
      return heights + Math.max(0, rows - 1) * gap;
    }
    if (totalH(all.length) <= availableH) {
      // Everything fits — no More button needed.
      closeMorePopover();
      return;
    }
    // Re-insert the More button (it counts toward the visible total) and
    // hide tail items until the remaining set fits.
    top.appendChild(moreBtn);
    function totalWithMore(n) {
      return totalH(n) + moreH + gap;
    }
    let visible = all.length;
    while (visible > 0 && totalWithMore(visible) > availableH) {
      all[visible - 1].classList.add('is-overflow-hidden');
      visible -= 1;
    }
    // Annotate the More button when an active view is currently hidden.
    const activeId = currentActiveView();
    const hasActiveHidden = all.some(
      (b) => b.classList.contains('is-overflow-hidden') && b.dataset.view === activeId,
    );
    let dot = moreBtn.querySelector('.more-active-dot');
    if (hasActiveHidden) {
      if (!dot) {
        dot = document.createElement('span');
        dot.className = 'more-active-dot';
        moreBtn.appendChild(dot);
      }
    } else if (dot) {
      dot.remove();
    }
    // Refresh the popover content if it's currently open, and
    // re-run positioning — the new height may push the popover off
    // the bottom of the window, so it needs a chance to flip upward.
    if (_morePopover && !_morePopover.hidden) {
      renderMorePopover(moreBtn);
      positionMorePopover(moreBtn);
    }
  }

  function hiddenSidenavBtns() {
    const top = document.querySelector('.sidenav-top');
    if (!top) return [];
    return Array.from(top.querySelectorAll('.sidenav-btn[data-view].is-overflow-hidden'));
  }

  function ensureMorePopover() {
    if (_morePopover) return _morePopover;
    const el = document.createElement('div');
    el.className = 'sidenav-more-popover';
    el.setAttribute('role', 'menu');
    el.hidden = true;
    document.body.appendChild(el);
    _morePopover = el;
    return el;
  }

  function closeMorePopover() {
    if (!_morePopover) return;
    _morePopover.hidden = true;
    const moreBtn = document.querySelector('.sidenav-more-btn');
    if (moreBtn) moreBtn.setAttribute('aria-expanded', 'false');
    document.removeEventListener('mousedown', onDocMouseDownForMore, true);
    document.removeEventListener('keydown', onDocKeyDownForMore, true);
  }

  function onDocMouseDownForMore(e) {
    if (!_morePopover || _morePopover.hidden) return;
    if (_morePopover.contains(e.target)) return;
    const moreBtn = document.querySelector('.sidenav-more-btn');
    if (moreBtn && moreBtn.contains(e.target)) return;
    closeMorePopover();
  }

  function onDocKeyDownForMore(e) {
    if (e.key === 'Escape') {
      e.stopPropagation();
      closeMorePopover();
    }
  }

  function toggleMorePopover(moreBtn) {
    const pop = ensureMorePopover();
    if (!pop.hidden) { closeMorePopover(); return; }
    renderMorePopover(moreBtn);
    // Make the popover laid out (but invisible) so positionMorePopover
    // can read a real offsetHeight — otherwise `pop.hidden = true`
    // means display:none and offsetHeight is 0, and the position math
    // always concludes "it fits below" even when the natural height
    // would clip off the bottom of the window.
    pop.style.visibility = 'hidden';
    pop.hidden = false;
    positionMorePopover(moreBtn);
    pop.style.visibility = '';
    moreBtn.setAttribute('aria-expanded', 'true');
    // Defer listener install so the click that opened us doesn't
    // immediately close it.
    setTimeout(() => {
      document.addEventListener('mousedown', onDocMouseDownForMore, true);
      document.addEventListener('keydown', onDocKeyDownForMore, true);
    }, 0);
  }

  function positionMorePopover(moreBtn) {
    const pop = _morePopover;
    if (!pop || !moreBtn) return;
    const margin = 8;
    const rect = moreBtn.getBoundingClientRect();
    // Anchor to the right of the rail.
    pop.style.left = `${Math.round(rect.right + 6)}px`;
    // Clear any prior max-height/top so we measure the popover's natural
    // size (capped by the CSS `max-height: 70vh`) before deciding which
    // direction to grow.
    pop.style.maxHeight = '';
    pop.style.top = `${margin}px`;
    const wh = window.innerHeight;
    const popH = pop.offsetHeight;
    // Space we'd have if anchored top-aligned (popover grows downward
    // from the More button) vs. bottom-aligned (popover grows upward
    // from the More button). The More button sits at the bottom of the
    // top rail with many items in the popover, so the downward space
    // is often too small — we flip upward in that case.
    const availBelow = wh - rect.top - margin;
    const availAbove = rect.bottom - margin;
    if (popH <= availBelow) {
      // Fits below — align top with the More button.
      pop.style.top = `${Math.round(rect.top)}px`;
    } else if (popH <= availAbove) {
      // Doesn't fit below but fits above — align bottom with the More
      // button so the popover grows upward into the space above the
      // rail. This is the typical case when the rail is full of icons.
      pop.style.top = `${Math.round(rect.bottom - popH)}px`;
    } else if (availAbove >= availBelow) {
      // Doesn't fit either way; more headroom above. Pin to the top
      // edge with a margin and let the popover scroll internally
      // (`overflow-y: auto` on the popover class) within the remaining
      // height.
      pop.style.top = `${margin}px`;
      pop.style.maxHeight = `${availAbove}px`;
    } else {
      // More headroom below; align top with the More button and cap
      // height to the available space.
      pop.style.top = `${Math.round(rect.top)}px`;
      pop.style.maxHeight = `${availBelow}px`;
    }
  }

  function renderMorePopover(moreBtn) {
    const pop = ensureMorePopover();
    pop.innerHTML = '';
    const hidden = hiddenSidenavBtns();
    if (!hidden.length) {
      closeMorePopover();
      return;
    }
    const activeId = currentActiveView();
    for (const realBtn of hidden) {
      const id = realBtn.dataset.view;
      const label = realBtn.getAttribute('data-tooltip')
        || realBtn.getAttribute('aria-label')
        || realBtn.title
        || id;
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'sidenav-more-row';
      row.dataset.view = id;
      if (id === activeId) row.classList.add('is-active');
      row.setAttribute('role', 'menuitem');

      const iconSlot = document.createElement('span');
      iconSlot.className = 'more-row-icon';
      const realIcon = realBtn.querySelector('.sidenav-btn-icon, svg');
      if (realIcon) {
        // Clone so the live button keeps its glyph.
        iconSlot.appendChild(realIcon.cloneNode(true));
      }
      row.appendChild(iconSlot);

      const labelEl = document.createElement('span');
      labelEl.className = 'more-row-label';
      labelEl.textContent = label;
      row.appendChild(labelEl);

      row.addEventListener('click', () => {
        if (window.AgixtSidenav && typeof window.AgixtSidenav.setActiveView === 'function') {
          window.AgixtSidenav.setActiveView(id);
        }
        activate(id);
        // Mark the active row visually but keep the popover open just
        // long enough for the user to see the activation, then close.
        clearTimeout(_moreCloseTimer);
        _moreCloseTimer = setTimeout(closeMorePopover, 120);
      });

      // Drag-and-drop FROM the popover row INTO the visible rail —
      // delegates to the underlying real button so existing
      // wireDragSort drop handlers move it into place. After drop, a
      // reflow re-evaluates which buttons fit and the moved item
      // becomes visible.
      row.draggable = true;
      row.addEventListener('dragstart', (e) => {
        try { e.dataTransfer.setData('text/plain', id); } catch (_) {}
        try { e.dataTransfer.effectAllowed = 'move'; } catch (_) {}
        realBtn.classList.add('is-dragging');
        row.classList.add('is-dragging');
        // Leave the popover visible: it's positioned to the right of
        // the rail so it doesn't cover the drop targets, and keeping
        // it open lets the user see which row they're dragging and
        // also drop back onto another popover row to reorder within
        // the hidden set (see the drag-target wiring below).
      });
      row.addEventListener('dragend', () => {
        realBtn.classList.remove('is-dragging');
        row.classList.remove('is-dragging');
        // After the drop landed (or didn't), close cleanly and
        // re-evaluate overflow so the moved item promotes into view.
        closeMorePopover();
        reflowSidenavOverflow();
      });
      // Drop target on this row so the user can reorder within the
      // hidden set, or drag a visible rail button here to demote it.
      // The drop reorders the underlying `realBtn` in `.sidenav-top`,
      // and the trailing reflow re-evaluates which items fit on the
      // visible rail vs. which collapse back into the popover.
      row.addEventListener('dragover', (e) => {
        const dragging = document.querySelector('.sidenav-btn.is-dragging');
        if (!dragging) return;
        e.preventDefault();
        try { e.dataTransfer.dropEffect = 'move'; } catch (_) {}
        const r = row.getBoundingClientRect();
        const before = e.clientY < r.top + r.height / 2;
        row.classList.toggle('is-drop-above', before);
        row.classList.toggle('is-drop-below', !before);
      });
      row.addEventListener('dragleave', () => {
        row.classList.remove('is-drop-above');
        row.classList.remove('is-drop-below');
      });
      row.addEventListener('drop', (e) => {
        e.preventDefault();
        row.classList.remove('is-drop-above');
        row.classList.remove('is-drop-below');
        const dragging = document.querySelector('.sidenav-btn.is-dragging');
        if (!dragging || dragging === realBtn) return;
        const top = document.querySelector('.sidenav-top');
        if (!top) return;
        const r = row.getBoundingClientRect();
        const before = e.clientY < r.top + r.height / 2;
        top.insertBefore(dragging, before ? realBtn : realBtn.nextSibling);
        captureSidenavOrder();
        reflowSidenavOverflow();
      });
      pop.appendChild(row);
    }
  }

  // Re-run overflow handling on window resize. ResizeObserver is more
  // precise but window resize covers the cases we care about (height
  // changes), and works in jsdom-equivalent test envs that lack RO.
  function scheduleReflow() {
    clearTimeout(reflowSidenavOverflow._t);
    reflowSidenavOverflow._t = setTimeout(reflowSidenavOverflow, 50);
  }
  if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
    window.addEventListener('resize', scheduleReflow);
  }
  // ResizeObserver catches everything window.resize misses: chat-screen
  // becoming visible after auth, topbar growing (e.g. error banner),
  // `.sidenav-bottom` admin-slot churn squeezing `.sidenav-top`, etc.
  // Without this the per-button reflow inside ensureSidenavBtn is the
  // only trigger, and any of its early bails (zero clientHeight before
  // paint, batched DOM inserts measuring before layout) leaves the rail
  // truncated until the next manual resize.
  if (typeof ResizeObserver === 'function') {
    let _ro = null;
    // Observe the parent `.sidenav` (whose height tracks the window) and
    // `.sidenav-bottom` (its height squeezes the top group). Observing
    // `.sidenav-top` itself would NOT fire on window resize when its
    // flex sizing is broken — its box would stay glued to content size
    // even as the window shrinks, so no callback fires and the rail
    // stays truncated. The parent is the reliable signal.
    const attachObserver = () => {
      const sidenav = document.querySelector('.sidenav');
      if (!sidenav) return false;
      if (_ro) _ro.disconnect();
      _ro = new ResizeObserver(scheduleReflow);
      _ro.observe(sidenav);
      const bottom = sidenav.querySelector('.sidenav-bottom');
      if (bottom) _ro.observe(bottom);
      return true;
    };
    if (!attachObserver()) {
      // .sidenav not in the DOM yet (auth screen still showing) —
      // poll briefly until it appears.
      const t = setInterval(() => { if (attachObserver()) clearInterval(t); }, 200);
      setTimeout(() => clearInterval(t), 10000);
    }
  }

  function wireDragSort(btn) {
    btn.draggable = true;
    btn.addEventListener('dragstart', (e) => {
      try { e.dataTransfer.setData('text/plain', btn.dataset.view); } catch (_) {}
      e.dataTransfer.effectAllowed = 'move';
      btn.classList.add('is-dragging');
    });
    btn.addEventListener('dragend', () => btn.classList.remove('is-dragging'));
    btn.addEventListener('dragover', (e) => {
      // Only accept drops from other middle-group buttons.
      const dragging = document.querySelector('.sidenav-btn.is-dragging');
      if (!dragging || dragging === btn) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      // Visual indicator: drop above vs below based on cursor position
      // within the button.
      const rect = btn.getBoundingClientRect();
      const mid = rect.top + rect.height / 2;
      btn.classList.toggle('is-drop-above', e.clientY < mid);
      btn.classList.toggle('is-drop-below', e.clientY >= mid);
    });
    btn.addEventListener('dragleave', () => {
      btn.classList.remove('is-drop-above');
      btn.classList.remove('is-drop-below');
    });
    btn.addEventListener('drop', (e) => {
      e.preventDefault();
      const dragging = document.querySelector('.sidenav-btn.is-dragging');
      btn.classList.remove('is-drop-above');
      btn.classList.remove('is-drop-below');
      if (!dragging || dragging === btn) return;
      const top = btn.parentElement;
      if (!top || dragging.parentElement !== top) return;
      const rect = btn.getBoundingClientRect();
      let before = e.clientY < rect.top + rect.height / 2;
      // Pinned-first buttons (Chat) stay at the start of the rail; refuse
      // any drop that would land before them and fall through to placing
      // the dragged item immediately after them instead. applySidenavOrder
      // would re-pin them on the next reflow anyway, but doing it here
      // keeps the visual transition smooth.
      if (before && isPinnedFirst(btn)) before = false;
      top.insertBefore(dragging, before ? btn : btn.nextSibling);
      captureSidenavOrder();
      applySidenavOrder();
      reflowSidenavOverflow();
    });
  }

  function ensureSidenavBtn(entry) {
    // Slot logic — `manifest.slot === 'admin'` pins the button to
    // `.sidenav-bottom` (above the settings gear) instead of the
    // sortable middle group. The companies/teams page uses this so
    // it's always one click from the bottom.
    const isAdminSlot = entry.slot === 'admin';
    const top = isAdminSlot
      ? document.querySelector('.sidenav-bottom')
      : document.querySelector('.sidenav-top');
    if (!top) return null;
    let btn = top.querySelector(`.sidenav-btn[data-view="${cssEscape(entry.id)}"]`);
    if (btn) {
      btn.title = entry.label || entry.id;
      btn.setAttribute('aria-label', entry.label || entry.id);
      btn.setAttribute('data-tooltip', entry.label || entry.id);
      const ic = btn.querySelector('.sidenav-btn-icon');
      if (ic) paintSidenavIcon(ic, entry);
      return btn;
    }
    btn = document.createElement('button');
    btn.className = 'sidenav-btn';
    btn.type = 'button';
    btn.dataset.view = entry.id;
    btn.title = entry.label || entry.id;
    btn.setAttribute('aria-label', entry.label || entry.id);
    btn.setAttribute('data-tooltip', entry.label || entry.id);
    btn.setAttribute('role', 'tab');
    btn.setAttribute('aria-selected', 'false');
    const span = document.createElement('span');
    span.className = 'sidenav-btn-icon';
    paintSidenavIcon(span, entry);
    btn.appendChild(span);
    btn.addEventListener('click', () => {
      if (window.AgixtSidenav && typeof window.AgixtSidenav.setActiveView === 'function') {
        window.AgixtSidenav.setActiveView(entry.id);
      }
      activate(entry.id);
    });
    if (isAdminSlot) {
      // Insert before the settings gear (last child of sidenav-bottom).
      const settings = top.querySelector('#btn-settings');
      if (settings) top.insertBefore(btn, settings);
      else top.appendChild(btn);
    } else {
      top.appendChild(btn);
      // Only middle-group buttons (non-chat, non-admin) are sortable.
      wireDragSort(btn);
      applySidenavOrder();
      reflowSidenavOverflow();
    }
    return btn;
  }

  // Manifest opt-in: when `layout === 'framed'`, the host wraps the
  // pane with a header strip (background: var(--panel) so it lines up
  // with the topbar + sidenav) above a scroll container the extension
  // mounts into. The header carries the manifest label and a flex
  // actions slot the extension can append to via
  // `ctx.headerActionsEl`. Extensions that don't opt in keep the
  // legacy single-container pane and remain responsible for their own
  // chrome — no behavior change for them.
  function isFramed(entry) {
    return entry && entry.layout === 'framed';
  }

  function ensurePane(entry) {
    const main = document.querySelector('.chat-screen-main');
    if (!main) return null;
    let pane = main.querySelector(`.view-pane[data-view="${cssEscape(entry.id)}"]`);
    if (pane) {
      // Manifest can flip layout between updates (e.g. version bump
      // adopts `framed`). Re-wrap to match — drop any cached body the
      // extension mounted into, since `activate` will refetch+remount.
      const wantsFramed = isFramed(entry);
      const hasFrame = !!pane.querySelector(':scope > .ext-pane-header');
      if (wantsFramed !== hasFrame) {
        pane.innerHTML = '';
        pane.classList.remove('is-framed');
        if (wantsFramed) buildFramedPane(pane, entry);
      } else if (wantsFramed) {
        // Refresh the header label in place if it changed.
        const titleEl = pane.querySelector(':scope > .ext-pane-header > .ext-pane-title');
        if (titleEl) titleEl.textContent = entry.label || entry.id;
      }
      return pane;
    }
    pane = document.createElement('div');
    pane.className = 'view-pane view-pane-extension';
    pane.dataset.view = entry.id;
    pane.hidden = true;
    if (isFramed(entry)) buildFramedPane(pane, entry);
    main.appendChild(pane);
    return pane;
  }

  function buildFramedPane(pane, entry) {
    pane.classList.add('is-framed');
    const header = document.createElement('header');
    header.className = 'ext-pane-header';
    const title = document.createElement('h1');
    title.className = 'ext-pane-title';
    title.textContent = entry.label || entry.id;
    const actions = document.createElement('div');
    actions.className = 'ext-pane-actions';
    header.appendChild(title);
    header.appendChild(actions);
    const body = document.createElement('div');
    body.className = 'ext-pane-body';
    pane.appendChild(header);
    pane.appendChild(body);
  }

  // Where the extension should mount its content. For framed panes
  // this is the `.ext-pane-body` element; otherwise it's the pane
  // itself (legacy behavior). Returns null if the framed wrapper got
  // out of sync with the layout flag (defensive — refresh() rewrites
  // the wrapper when the manifest's `layout` changes).
  function mountTargetFor(pane, entry) {
    if (!pane) return null;
    if (!isFramed(entry)) return pane;
    return pane.querySelector(':scope > .ext-pane-body') || null;
  }

  function showPaneError(pane, entry, title, detail) {
    const target = mountTargetFor(pane, entry) || pane;
    if (!target) return;
    const msg = detail && (detail.message || detail.error || detail.detail || String(detail));
    target.innerHTML = [
      '<div class="ext-load-error">',
      '<strong>' + escapeHtml(title || 'Extension failed to load') + '</strong>',
      msg ? '<p>' + escapeHtml(msg) + '</p>' : '',
      '</div>',
    ].join('');
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  async function ensureCrudHelper() {
    if (window.AgixtCrudExtension && typeof window.AgixtCrudExtension.register === 'function') return true;
    let resp;
    try {
      resp = await fetch('desktop-crud.js', { cache: 'no-store' });
    } catch (err) {
      console.warn('desktop-extensions: crud helper fetch failed', err);
      return false;
    }
    if (!resp || !resp.ok) {
      console.warn('desktop-extensions: crud helper http', resp && resp.status);
      return false;
    }
    const text = await resp.text();
    const blob = new Blob([text], { type: 'application/javascript' });
    const url = URL.createObjectURL(blob);
    try {
      await import(url);
    } catch (err) {
      console.warn('desktop-extensions: crud helper import failed', err);
      return false;
    } finally {
      URL.revokeObjectURL(url);
    }
    return !!(window.AgixtCrudExtension && typeof window.AgixtCrudExtension.register === 'function');
  }

  // Minimal CSS.escape polyfill — the ids only ever match _ID_RE on the
  // server side ([a-z0-9_-]+), so we don't need a full implementation.
  function cssEscape(s) { return String(s).replace(/[^a-zA-Z0-9_-]/g, '\\$&'); }

  async function activate(id) {
    const rec = state.get(id);
    if (!rec) return;
    if (rec.mounted) return;
    if (rec.activating) return rec.activating;
    rec.activating = activateInner(id, rec).finally(() => { rec.activating = null; });
    return rec.activating;
  }

  async function activateInner(id, rec) {
    const pane = ensurePane(rec.entry);
    if (!pane) return;
    const c = makeMountContext(id, rec, pane);
    if (!c) {
      showPaneError(pane, rec.entry, 'Sign in required', 'The desktop extension context is not ready yet.');
      return;
    }

    let blobUrl = rec.blobUrl;
    if (!blobUrl) {
      const text = await fetchModuleText(rec.entry);
      if (text == null) {
        showPaneError(pane, rec.entry, 'Extension asset failed to load', 'The server did not return the extension JavaScript.');
        return;
      }
      if (/\bAgixtCrudExtension\b/.test(text) && !(await ensureCrudHelper())) {
        showPaneError(pane, rec.entry, 'Desktop CRUD helper failed to load', 'Reload the desktop app to pick up the latest client assets.');
        return;
      }
      const blob = new Blob([text], { type: 'application/javascript' });
      blobUrl = URL.createObjectURL(blob);
      rec.blobUrl = blobUrl;
    }

    pendingRegistrations.delete(id);
    try {
      // Dynamic import lets us evaluate the module exactly once even if
      // the user clicks the button multiple times before the fetch
      // settles (the import map dedupes by URL).
      await import(blobUrl);
    } catch (err) {
      console.warn('desktop-extensions: module import failed', id, err);
      showPaneError(pane, rec.entry, 'Extension module failed to load', err);
      return;
    }

    const ctrl = pendingRegistrations.get(id);
    pendingRegistrations.delete(id);
    if (!ctrl) {
      console.warn('desktop-extensions: module did not register', id);
      showPaneError(pane, rec.entry, 'Extension did not register', 'The module loaded but did not call AgixtRegisterExtension.');
      return;
    }
    rec.ctrl = ctrl;
    const target = mountTargetFor(pane, rec.entry);
    if (!target) {
      showPaneError(pane, rec.entry, 'Extension pane is not ready', 'The extension layout target was not found.');
      return;
    }
    try {
      ctrl.mount(target, c);
      rec.mounted = true;
    } catch (err) {
      console.warn('desktop-extensions: mount failed', id, err);
      showPaneError(pane, rec.entry, 'Extension mount failed', err);
    }
  }

  async function fetchModuleText(entry) {
    const c = ctx();
    if (!c) return null;
    // Forward `company_id` and `agent_id` the same way `fetchManifest`
    // does. The server re-runs the manifest's `requires` block when
    // serving main.js, and per-agent gates (e.g. `connection_check`,
    // `agent_extension`) return False when agent_id is missing — which
    // would 403 the asset and leave the pane blank with no UI feedback.
    const url = buildUrl(c.serverUrl, entry.entry_url || `/v1/desktop/extensions/${entry.id}/main.js`, {
      v: entry.version,
      company_id: c.companyId,
      agent_id: c.agentId,
    });
    let resp;
    try {
      resp = await fetch(url, { headers: { Authorization: `Bearer ${c.jwt}` } });
    } catch (err) {
      console.warn('desktop-extensions: module fetch failed', entry.id, err);
      return null;
    }
    if (!resp.ok) {
      console.warn('desktop-extensions: module http', entry.id, resp.status);
      return null;
    }
    return resp.text();
  }

  function unmountAndForget(id) {
    const rec = state.get(id);
    if (!rec) return;
    if (rec.ctrl && typeof rec.ctrl.unmount === 'function') {
      try { rec.ctrl.unmount(); } catch (_) { /* ignore */ }
    }
    if (typeof rec.contextUnsubscribe === 'function') {
      try { rec.contextUnsubscribe(); } catch (_) {}
      rec.contextUnsubscribe = null;
    } else {
      unregisterContextProvider(id);
    }
    if (rec.blobUrl) {
      URL.revokeObjectURL(rec.blobUrl);
    }
    const btn = document.querySelector(
      `.sidenav-top .sidenav-btn[data-view="${cssEscape(id)}"]`,
    );
    if (btn && btn.parentNode) btn.parentNode.removeChild(btn);
    const pane = document.querySelector(
      `.chat-screen-main .view-pane[data-view="${cssEscape(id)}"]`,
    );
    if (pane && pane.parentNode) pane.parentNode.removeChild(pane);
    state.delete(id);
    pendingRegistrations.delete(id);
    reflowSidenavOverflow();
  }

  async function refresh() {
    const data = await fetchManifest();
    if (!data) return; // 304 or fetch error
    const next = new Map();
    for (const e of data.extensions || []) {
      if (!e || !e.id) continue;
      next.set(e.id, e);
    }

    // Add or update.
    for (const [id, entry] of next) {
      ensureSidenavBtn(entry);
      ensurePane(entry);
      const existing = state.get(id);
      if (!existing) {
        state.set(id, { entry, mounted: false, activating: null, ctrl: null, blobUrl: null, contextUnsubscribe: null });
        continue;
      }
      if (existing.entry.version !== entry.version) {
        // Version bumped — drop the cached module so the next click
        // re-fetches. We don't hot-swap a currently-mounted extension
        // (state migration is the extension author's problem, not
        // ours); next mount picks up the new code.
        if (existing.ctrl && typeof existing.ctrl.unmount === 'function') {
          try { existing.ctrl.unmount(); } catch (_) {}
        }
        if (typeof existing.contextUnsubscribe === 'function') {
          try { existing.contextUnsubscribe(); } catch (_) {}
        } else {
          unregisterContextProvider(id);
        }
        if (existing.blobUrl) URL.revokeObjectURL(existing.blobUrl);
        const pane = document.querySelector(
          `.chat-screen-main .view-pane[data-view="${cssEscape(id)}"]`,
        );
        if (pane) {
          pane.innerHTML = '';
          pane.classList.remove('is-framed');
          // Rebuild the framed wrapper for the *new* manifest — the
          // version bump may have flipped the layout flag, and even
          // when it didn't, the empty body is what the next mount
          // expects to find.
          if (isFramed(entry)) buildFramedPane(pane, entry);
        }
        state.set(id, { entry, mounted: false, activating: null, ctrl: null, blobUrl: null, contextUnsubscribe: null });
      } else {
        existing.entry = entry;
      }
    }

    // Drop entries the server no longer advertises (e.g. user lost a
    // scope or disconnected an OAuth account).
    for (const id of [...state.keys()]) {
      if (!next.has(id)) unmountAndForget(id);
    }
    const active = currentActiveView();
    if (active && active !== 'chat' && state.has(active)) activate(active);
  }

  function start({ pollMs = 5 * 60 * 1000 } = {}) {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    refresh();
    pollTimer = setInterval(refresh, pollMs);
  }

  function stop() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  window.AgixtDesktopExtensions = {
    start,
    stop,
    refresh,
    activate,
    reflowSidenav: reflowSidenavOverflow,
    registerContextProvider,
    unregisterContextProvider,
    getActiveContext,
    getAllContexts,
  };
})();

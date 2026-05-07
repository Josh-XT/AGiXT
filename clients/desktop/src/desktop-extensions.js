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

  // id -> { entry, mounted, ctrl, blobUrl }
  const state = new Map();
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
  function applySidenavOrder() {
    const top = document.querySelector('.sidenav-top');
    if (!top) return;
    const order = loadSidenavOrder();
    const chat = top.querySelector('.sidenav-btn[data-view="chat"]');
    const all = Array.from(top.querySelectorAll('.sidenav-btn[data-view]'))
      .filter((b) => b.dataset.view !== 'chat');
    const orderedKnown = order
      .map((id) => all.find((b) => b.dataset.view === id))
      .filter(Boolean);
    const newcomers = all.filter((b) => order.indexOf(b.dataset.view) === -1);
    // Re-append in the desired order. appendChild on existing nodes
    // moves them, doesn't duplicate.
    if (chat) top.appendChild(chat);
    for (const b of orderedKnown) top.appendChild(b);
    for (const b of newcomers)    top.appendChild(b);
  }

  // Capture the current visual order of middle-group buttons and
  // persist. Called after a successful drop.
  function captureSidenavOrder() {
    const top = document.querySelector('.sidenav-top');
    if (!top) return;
    const ids = Array.from(top.querySelectorAll('.sidenav-btn[data-view]'))
      .map((b) => b.dataset.view)
      .filter((id) => id && id !== 'chat');
    saveSidenavOrder(ids);
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
      const before = e.clientY < rect.top + rect.height / 2;
      top.insertBefore(dragging, before ? btn : btn.nextSibling);
      captureSidenavOrder();
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
    }
    return btn;
  }

  function ensurePane(entry) {
    const main = document.querySelector('.chat-screen-main');
    if (!main) return null;
    let pane = main.querySelector(`.view-pane[data-view="${cssEscape(entry.id)}"]`);
    if (pane) return pane;
    pane = document.createElement('div');
    pane.className = 'view-pane view-pane-extension';
    pane.dataset.view = entry.id;
    pane.hidden = true;
    main.appendChild(pane);
    return pane;
  }

  // Minimal CSS.escape polyfill — the ids only ever match _ID_RE on the
  // server side ([a-z0-9_-]+), so we don't need a full implementation.
  function cssEscape(s) { return String(s).replace(/[^a-zA-Z0-9_-]/g, '\\$&'); }

  async function activate(id) {
    const rec = state.get(id);
    if (!rec) return;
    if (rec.mounted) return;
    const c = ctx();
    if (!c) return;

    let blobUrl = rec.blobUrl;
    if (!blobUrl) {
      const text = await fetchModuleText(rec.entry);
      if (text == null) return;
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
      return;
    }

    const ctrl = pendingRegistrations.get(id);
    pendingRegistrations.delete(id);
    if (!ctrl) {
      console.warn('desktop-extensions: module did not register', id);
      return;
    }
    rec.ctrl = ctrl;
    const pane = ensurePane(rec.entry);
    if (!pane) return;
    try {
      ctrl.mount(pane, ctx());
      rec.mounted = true;
    } catch (err) {
      console.warn('desktop-extensions: mount failed', id, err);
    }
  }

  async function fetchModuleText(entry) {
    const c = ctx();
    if (!c) return null;
    const url = buildUrl(c.serverUrl, entry.entry_url || `/v1/desktop/extensions/${entry.id}/main.js`, {
      v: entry.version,
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
        state.set(id, { entry, mounted: false, ctrl: null, blobUrl: null });
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
        if (existing.blobUrl) URL.revokeObjectURL(existing.blobUrl);
        const pane = document.querySelector(
          `.chat-screen-main .view-pane[data-view="${cssEscape(id)}"]`,
        );
        if (pane) pane.innerHTML = '';
        state.set(id, { entry, mounted: false, ctrl: null, blobUrl: null });
      } else {
        existing.entry = entry;
      }
    }

    // Drop entries the server no longer advertises (e.g. user lost a
    // scope or disconnected an OAuth account).
    for (const id of [...state.keys()]) {
      if (!next.has(id)) unmountAndForget(id);
    }
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

  window.AgixtDesktopExtensions = { start, stop, refresh };
})();

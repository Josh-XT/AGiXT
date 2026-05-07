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

  function ensureSidenavBtn(entry) {
    const top = document.querySelector('.sidenav-top');
    if (!top) return null;
    let btn = top.querySelector(`.sidenav-btn[data-view="${cssEscape(entry.id)}"]`);
    if (btn) {
      btn.title = entry.label || entry.id;
      btn.setAttribute('aria-label', entry.label || entry.id);
      const ic = btn.querySelector('.sidenav-btn-icon');
      if (ic) ic.textContent = entry.icon || (entry.label ? entry.label[0] : '?');
      return btn;
    }
    btn = document.createElement('button');
    btn.className = 'sidenav-btn';
    btn.type = 'button';
    btn.dataset.view = entry.id;
    btn.title = entry.label || entry.id;
    btn.setAttribute('aria-label', entry.label || entry.id);
    btn.setAttribute('role', 'tab');
    btn.setAttribute('aria-selected', 'false');
    const span = document.createElement('span');
    span.className = 'sidenav-btn-icon';
    // First cut renders the icon as text — emoji or short label like
    // "M". An SVG-name resolver can be slotted in later.
    span.textContent = entry.icon || (entry.label ? entry.label[0] : '?');
    btn.appendChild(span);
    btn.addEventListener('click', () => {
      if (window.AgixtSidenav && typeof window.AgixtSidenav.setActiveView === 'function') {
        window.AgixtSidenav.setActiveView(entry.id);
      }
      activate(entry.id);
    });
    top.appendChild(btn);
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

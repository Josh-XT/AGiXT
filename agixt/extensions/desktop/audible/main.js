/* Audible — desktop extension port of the kids app's audiobook player.
 *
 * Layout (mirrors /home/josh/repos/xtsys/kids/templates/reader.html with
 * one extra panel on the far left):
 *
 *   ┌─────────────┬─────────┬───────────────────────────┐
 *   │ Library     │ Chapter │  Book detail / reader     │
 *   │ (collapse)  │ list    │                           │
 *   │ + search    │         │                           │
 *   ├─────────────┴─────────┴───────────────────────────┤
 *   │ Audio player (progress + skip + play + speed)     │
 *   └───────────────────────────────────────────────────┘
 *
 * Backend:
 *   GET  /v1/audible/library?q=...                — sidebar list
 *   GET  /v1/audible/progress                     — "Continue listening"
 *   GET  /v1/audible/book/{asin}                  — detail header
 *   GET  /v1/audible/book/{asin}/chapters         — chapter list + last pos
 *   GET  /v1/audible/cover/{asin}                 — JWT-protected cover proxy
 *   GET  /v1/audible/audio/{asin}/status          — is audio cached?
 *   POST /v1/audible/audio/{asin}/download        — kick off cache download
 *   GET  /v1/audible/audio/{asin}                 — Range-streamed audio
 *
 * The extension manifest gates this view on `agent_extension: ["audible"]`,
 * so it only appears once the user has the Audible extension enabled on
 * their agent. All routes carry `Authorization: Bearer <jwt>` and the
 * agent_id query param so the server picks the right credentials.
 */

// Bumped in lockstep with manifest.json — embedded into the
// diagnostic placeholder so we can tell from a screenshot whether
// the user is running the latest main.js or a cached older one.
const AUD_BUILD_TAG = '0.1.4';

window.AgixtRegisterExtension('audible', {
  mount(container, ctx) {
    // Render a high-visibility placeholder before doing any real work.
    // If renderShell or downstream code throws, the catch handler
    // overwrites this with the error text. If THIS placeholder is
    // what the user sees, mount() is running but start() is throwing
    // synchronously. If the user sees nothing at all, mount() never
    // ran and we have a loader/cache issue, not a page bug.
    container.innerHTML = `
      <div data-aud-placeholder="${AUD_BUILD_TAG}"
           style="padding:32px;font:14px/1.5 system-ui,sans-serif;color:#e6edf3;background:#0d1117;height:100%;box-sizing:border-box;">
        <div style="font-size:1.3rem;font-weight:700;color:#58a6ff;margin-bottom:8px">
          Audible page (build ${AUD_BUILD_TAG})
        </div>
        <div style="opacity:0.75">Loading library…</div>
      </div>
    `;
    try {
      const view = new AudibleView(container, ctx);
      container._audibleView = view;
      view.start();
    } catch (err) {
      console.error('audible: mount failed', err);
      container.innerHTML = `
        <div style="padding:24px;font:13px/1.55 system-ui,sans-serif;color:#ffb4b4;background:#0d1117;height:100%;box-sizing:border-box;overflow:auto;">
          <div style="font-weight:600;margin-bottom:6px">Audible page failed to load (build ${AUD_BUILD_TAG}).</div>
          <pre style="margin:0;white-space:pre-wrap;font-family:inherit;font-size:12px;opacity:0.85">${
            String(err && err.stack || err || '').replace(/[<>&]/g, (c) => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]))
          }</pre>
        </div>
      `;
    }
  },
  unmount() {
    const root = document.querySelector('.chat-screen-main .view-pane[data-view="audible"]');
    if (root && root._audibleView) {
      root._audibleView.stop();
      root._audibleView = null;
    }
  },
});

const SIDEBAR_OPEN_KEY    = 'agixt.desktop.audible.sidebar.open.v1';
const CHAPTERS_OPEN_KEY   = 'agixt.desktop.audible.chapters.open.v1';
const SPEED_KEY           = 'agixt.desktop.audible.speed.v1';
const VOLUME_KEY          = 'agixt.desktop.audible.volume.v1';
const LAST_BOOK_KEY       = 'agixt.desktop.audible.lastBook.v1';

function readBool(key, dflt) {
  try {
    const v = window.localStorage.getItem(key);
    if (v === '1') return true;
    if (v === '0') return false;
  } catch (_) {}
  return dflt;
}
function writeBool(key, v) {
  try { window.localStorage.setItem(key, v ? '1' : '0'); } catch (_) {}
}
function readNum(key, dflt) {
  try {
    const v = parseFloat(window.localStorage.getItem(key));
    if (Number.isFinite(v)) return v;
  } catch (_) {}
  return dflt;
}
function writeNum(key, v) {
  try { window.localStorage.setItem(key, String(v)); } catch (_) {}
}
function readStr(key, dflt) {
  try {
    const v = window.localStorage.getItem(key);
    if (typeof v === 'string') return v;
  } catch (_) {}
  return dflt;
}
function writeStr(key, v) {
  try { window.localStorage.setItem(key, v == null ? '' : String(v)); } catch (_) {}
}

function fmtDuration(ms) {
  if (!ms || ms < 0) ms = 0;
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function fmtMinutes(min) {
  if (!min) return '';
  const h = Math.floor(min / 60);
  const m = min % 60;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null) continue;
      if (k === 'class') node.className = v;
      else if (k === 'style') node.setAttribute('style', v);
      else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
      else if (k === 'html') node.innerHTML = v;
      else node.setAttribute(k, v);
    }
  }
  for (const c of children) {
    if (c == null || c === false) continue;
    if (typeof c === 'string' || typeof c === 'number') {
      node.appendChild(document.createTextNode(String(c)));
    } else {
      node.appendChild(c);
    }
  }
  return node;
}

/* ===================================================================
 * View
 * =================================================================== */

function AudibleView(container, ctx) {
  this.container = container;
  this.ctx = ctx;
  this.library = [];
  this.libraryLoaded = false;
  this.libraryError = null;
  this.libraryFilter = '';
  this.libraryTab = 'all';   // 'all' | 'progress' | 'wishlist'
  this.progress = [];
  this.wishlist = [];
  this.currentAsin = readStr(LAST_BOOK_KEY, '') || null;
  this.currentBook = null;
  this.currentChapters = [];
  this.totalDurationMs = 0;
  this.lastPositionMs = 0;
  this.audioStatus = null;
  this.coverObjectUrls = new Map();    // asin -> blobURL for sidebar covers
  this.audioObjectUrl = null;          // active player blob URL
  this.audioBlobAsin = null;
  this.statusPollTimer = null;
  this.sidebarOpen = readBool(SIDEBAR_OPEN_KEY, true);
  this.chaptersOpen = readBool(CHAPTERS_OPEN_KEY, true);
  this.playbackRate = readNum(SPEED_KEY, 1);
  this.volume = readNum(VOLUME_KEY, 1);
  this.skinned = false;
}

AudibleView.prototype.start = function () {
  this.injectStyles();
  this.renderShell();
  // Server-side manifest gating (`connection_check: ["audible"]`)
  // means this page only loads when the auth file exists, so we go
  // straight to library + book restoration. If the file disappears
  // mid-session the per-call 401 handler surfaces the message.
  this.loadLibrary();
  if (this.currentAsin) this.loadBook(this.currentAsin, { silent: true });
};

AudibleView.prototype.stop = function () {
  if (this.statusPollTimer) {
    clearInterval(this.statusPollTimer);
    this.statusPollTimer = null;
  }
  for (const url of this.coverObjectUrls.values()) {
    try { URL.revokeObjectURL(url); } catch (_) {}
  }
  this.coverObjectUrls.clear();
  if (this.audioObjectUrl) {
    try { URL.revokeObjectURL(this.audioObjectUrl); } catch (_) {}
    this.audioObjectUrl = null;
  }
  if (this.audio) {
    try { this.audio.pause(); } catch (_) {}
    this.audio.src = '';
  }
  this.container.innerHTML = '';
};

/* ---------- HTTP helpers --------------------------------------------- */

AudibleView.prototype.apiUrl = function (path, params) {
  const base = (this.ctx.serverUrl || '').replace(/\/+$/, '');
  const u = new URL(base + path);
  if (params) for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== '') u.searchParams.set(k, v);
  }
  if (this.ctx.agentId && !u.searchParams.has('agent_id')) {
    u.searchParams.set('agent_id', this.ctx.agentId);
  }
  return u.toString();
};

AudibleView.prototype.fetchJson = async function (path, params, opts) {
  const url = this.apiUrl(path, params);
  const init = Object.assign(
    { method: 'GET', headers: { Authorization: 'Bearer ' + this.ctx.jwt } },
    opts || {},
  );
  const r = await fetch(url, init);
  if (r.status === 401) {
    // Server-side manifest gating means this page only loads when the
    // Audible auth blob is parseable. If we still see a 401 here it's
    // because the auth went stale mid-session — we surface the message
    // inline (loadLibrary's error renderer handles it) and let the
    // ext.refresh poll on the agent settings drawer kick the sidebar
    // tab back to "Not connected" within a few seconds.
    let body = null;
    try { body = await r.json(); } catch (_) {}
    const detail = body && body.detail;
    if (detail && typeof detail === 'object' && detail.code === 'audible_auth_required') {
      const e = new Error(detail.message || 'Audible login required.');
      e.status = 401;
      e.code = 'audible_auth_required';
      throw e;
    }
    const t = JSON.stringify(detail || body || '');
    throw new Error(`${r.status} ${r.statusText}: ${t.slice(0, 240)}`);
  }
  if (r.status === 404) {
    const t = await r.text().catch(() => '');
    const e = new Error(t || 'not found');
    e.status = 404;
    throw e;
  }
  if (!r.ok) {
    const t = await r.text().catch(() => '');
    throw new Error(`${r.status} ${r.statusText}: ${t.slice(0, 240)}`);
  }
  return r.json();
};

AudibleView.prototype.fetchBlob = async function (path, params) {
  const url = this.apiUrl(path, params);
  const r = await fetch(url, { headers: { Authorization: 'Bearer ' + this.ctx.jwt } });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.blob();
};

/* ---------- styles --------------------------------------------------- */

AudibleView.prototype.injectStyles = function () {
  if (document.getElementById('aud-ext-styles')) return;
  const style = document.createElement('style');
  style.id = 'aud-ext-styles';
  style.textContent = `
.view-pane[data-view="audible"] {
  --aud-bg: #0d1117;
  --aud-inset: #010409;
  --aud-surface: rgba(22, 27, 34, 0.85);
  --aud-surface-strong: rgba(13, 17, 23, 0.94);
  --aud-surface-solid: #161b22;
  --aud-text: #e6edf3;
  --aud-text-dim: #8b949e;
  --aud-text-muted: #6e7681;
  --aud-accent: #2f81f7;
  --aud-accent-hover: #58a6ff;
  --aud-accent-emphasis: #1f6feb;
  --aud-accent-soft: rgba(56, 139, 253, 0.15);
  --aud-border: #30363d;
  --aud-border-muted: #21262d;
  --aud-on-accent: #ffffff;

  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--aud-bg);
  color: var(--aud-text);
  overflow: hidden;
}
.aud-shell {
  flex: 1;
  display: flex;
  min-height: 0;
}
.aud-sidebar {
  width: 320px;
  background: var(--aud-surface-solid);
  border-right: 1px solid var(--aud-border);
  display: flex;
  flex-direction: column;
  transition: width 0.2s ease, padding 0.2s ease;
  overflow: hidden;
}
.aud-sidebar.collapsed { width: 0; border-right: 0; }
.aud-sidebar-head {
  padding: 14px 14px 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  border-bottom: 1px solid var(--aud-border-muted);
}
.aud-sidebar-title {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.13em;
  color: var(--aud-accent);
}
.aud-search {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--aud-bg);
  border: 1px solid var(--aud-border);
  border-radius: 6px;
  padding: 6px 10px;
}
.aud-search input {
  flex: 1;
  background: transparent;
  border: 0;
  outline: 0;
  color: var(--aud-text);
  font-size: 0.85rem;
  font-family: inherit;
}
.aud-tabs {
  display: flex;
  gap: 4px;
  padding: 2px;
  background: var(--aud-bg);
  border: 1px solid var(--aud-border);
  border-radius: 8px;
}
.aud-tab {
  flex: 1;
  background: none;
  border: 0;
  color: var(--aud-text-dim);
  font-size: 0.78rem;
  font-weight: 600;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
}
.aud-tab:hover { color: var(--aud-text); }
.aud-tab.active {
  background: var(--aud-accent);
  color: var(--aud-on-accent);
}
.aud-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.aud-list::-webkit-scrollbar { width: 6px; }
.aud-list::-webkit-scrollbar-thumb { background: var(--aud-border); border-radius: 999px; }
.aud-list::-webkit-scrollbar-thumb:hover { background: #484f58; }
.aud-list-empty {
  padding: 24px 12px;
  color: var(--aud-text-muted);
  font-size: 0.85rem;
  text-align: center;
  line-height: 1.5;
}
.aud-list-error {
  padding: 14px 12px;
  color: #ffb4b4;
  font-size: 0.82rem;
  line-height: 1.45;
  background: rgba(248, 81, 73, 0.08);
  border: 1px solid rgba(248, 81, 73, 0.4);
  border-radius: 6px;
  margin: 6px;
}
.aud-card {
  display: flex;
  gap: 10px;
  padding: 8px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s ease;
  border: 1px solid transparent;
  align-items: flex-start;
}
.aud-card + .aud-card { margin-top: 2px; }
.aud-card:hover { background: rgba(177, 186, 196, 0.06); }
.aud-card.active {
  background: var(--aud-accent-soft);
  border-color: rgba(56, 139, 253, 0.4);
}
.aud-card-cover {
  width: 56px;
  height: 56px;
  border-radius: 4px;
  object-fit: cover;
  background: var(--aud-bg);
  flex-shrink: 0;
  box-shadow: 0 2px 6px rgba(0,0,0,0.4);
}
.aud-card-cover.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--aud-text-muted);
  font-size: 0.65rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  border: 1px solid var(--aud-border);
}
.aud-card-meta { min-width: 0; flex: 1; }
.aud-card-title {
  font-size: 0.86rem;
  font-weight: 600;
  color: var(--aud-text);
  margin-bottom: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  line-height: 1.3;
}
.aud-card-author {
  font-size: 0.74rem;
  color: var(--aud-text-dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.aud-card-progress {
  margin-top: 4px;
  height: 3px;
  background: var(--aud-border-muted);
  border-radius: 999px;
  overflow: hidden;
}
.aud-card-progress > span {
  display: block;
  height: 100%;
  background: var(--aud-accent);
}
.aud-card-progress.finished > span { background: #3fb950; }
.aud-card-progress-label {
  font-size: 0.7rem;
  color: var(--aud-text-muted);
  margin-top: 3px;
  font-variant-numeric: tabular-nums;
}

/* Main area */
.aud-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.aud-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--aud-border);
  background: var(--aud-surface);
}
.aud-iconbtn {
  background: var(--aud-surface-solid);
  border: 1px solid var(--aud-border);
  color: var(--aud-text-dim);
  border-radius: 6px;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s ease;
  flex-shrink: 0;
}
.aud-iconbtn:hover { color: var(--aud-accent-hover); border-color: #8b949e; }
.aud-iconbtn svg { width: 16px; height: 16px; stroke: currentColor; stroke-width: 2; fill: none; }
.aud-toolbar-title {
  flex: 1;
  font-size: 0.95rem;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.aud-toolbar-sub {
  font-size: 0.78rem;
  color: var(--aud-text-dim);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.aud-content {
  flex: 1;
  display: flex;
  min-height: 0;
}
.aud-chapters {
  width: 280px;
  background: var(--aud-surface-solid);
  border-right: 1px solid var(--aud-border);
  overflow-y: auto;
  padding: 14px 12px;
  transition: width 0.2s ease, padding 0.2s ease;
}
.aud-chapters.collapsed { width: 0; padding: 14px 0; border-right: 0; overflow: hidden; }
.aud-chapters-title {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.13em;
  color: var(--aud-accent);
  margin-bottom: 10px;
}
.aud-chapter-item {
  padding: 8px 10px;
  margin-bottom: 2px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
  font-size: 0.85rem;
  color: var(--aud-text-dim);
  border-left: 3px solid transparent;
}
.aud-chapter-item:hover { background: rgba(177, 186, 196, 0.06); color: var(--aud-text); }
.aud-chapter-item.active {
  background: var(--aud-accent-soft);
  border-left-color: var(--aud-accent);
  color: var(--aud-accent-hover);
}
.aud-chapter-time {
  font-size: 0.7rem;
  color: var(--aud-text-muted);
  margin-top: 2px;
  font-variant-numeric: tabular-nums;
}

/* Detail */
.aud-detail {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px 32px;
}
.aud-detail-empty {
  color: var(--aud-text-muted);
  font-size: 0.95rem;
  text-align: center;
  padding: 60px 16px;
  line-height: 1.6;
}
.aud-detail-head {
  display: flex;
  gap: 22px;
  margin-bottom: 20px;
}
.aud-detail-cover {
  width: 180px;
  height: 180px;
  object-fit: cover;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.5);
  flex-shrink: 0;
  background: var(--aud-surface-solid);
}
.aud-detail-info { min-width: 0; flex: 1; }
.aud-detail-info h2 {
  font-size: 1.5rem;
  font-weight: 700;
  margin-bottom: 4px;
  letter-spacing: -0.01em;
}
.aud-detail-sub {
  font-size: 0.95rem;
  color: var(--aud-text-dim);
  margin-bottom: 8px;
  font-style: italic;
}
.aud-detail-row {
  font-size: 0.85rem;
  color: var(--aud-text-dim);
  margin-bottom: 4px;
}
.aud-detail-row b { color: var(--aud-text); font-weight: 500; }
.aud-detail-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  margin-top: 10px;
  font-size: 0.78rem;
  color: var(--aud-text-dim);
}
.aud-pill {
  background: var(--aud-surface-solid);
  border: 1px solid var(--aud-border);
  padding: 3px 10px;
  border-radius: 999px;
}
.aud-detail-desc {
  margin-top: 16px;
  font-size: 0.95rem;
  line-height: 1.65;
  color: var(--aud-text);
  font-family: 'Lora', 'Georgia', serif;
}

/* Audio status banner */
.aud-status-banner {
  margin-top: 16px;
  padding: 10px 14px;
  border-radius: 8px;
  background: var(--aud-surface-solid);
  border: 1px solid var(--aud-border);
  font-size: 0.85rem;
  color: var(--aud-text-dim);
  display: flex;
  align-items: center;
  gap: 12px;
}
.aud-status-banner.ok { border-color: rgba(63, 185, 80, 0.4); }
.aud-status-banner.warn { border-color: rgba(240, 165, 60, 0.4); }
.aud-status-banner.err { border-color: rgba(248, 81, 73, 0.4); color: #ffb4b4; }
.aud-status-banner button {
  background: var(--aud-accent);
  color: var(--aud-on-accent);
  border: 1px solid var(--aud-accent-emphasis);
  padding: 4px 12px;
  font-size: 0.78rem;
  font-weight: 600;
  border-radius: 6px;
  cursor: pointer;
  font-family: inherit;
}
.aud-status-banner button:hover { background: var(--aud-accent-hover); }
.aud-status-banner button:disabled { opacity: 0.5; cursor: wait; }

/* Player bar */
.aud-player {
  background: var(--aud-surface-strong);
  border-top: 1px solid var(--aud-border);
  padding: 10px 20px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}
.aud-progress-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.aud-progress-bar {
  flex: 1;
  height: 5px;
  background: var(--aud-border-muted);
  border-radius: 999px;
  cursor: pointer;
  position: relative;
  transition: height 0.15s ease;
}
.aud-progress-bar:hover { height: 7px; }
.aud-progress-bar.disabled { cursor: default; opacity: 0.45; }
.aud-progress-fill {
  height: 100%;
  background: var(--aud-accent);
  border-radius: 999px;
  width: 0%;
  transition: width 0.1s linear;
}
.aud-progress-handle {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 12px;
  height: 12px;
  background: var(--aud-accent);
  border-radius: 50%;
  box-shadow: 0 0 0 4px rgba(56, 139, 253, 0.18);
  opacity: 0;
  transition: opacity 0.15s ease;
}
.aud-progress-bar:hover .aud-progress-handle { opacity: 1; }
.aud-time {
  font-size: 0.76rem;
  font-variant-numeric: tabular-nums;
  color: var(--aud-text-dim);
  min-width: 56px;
  text-align: center;
  font-weight: 500;
  letter-spacing: 0.02em;
}
.aud-controls {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 12px;
}
.aud-controls-left {
  font-size: 0.78rem;
  color: var(--aud-text-dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.aud-controls-mid {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
}
.aud-controls-right {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 10px;
}
.aud-ctrl-btn {
  background: var(--aud-surface-solid);
  border: 1px solid var(--aud-border);
  color: var(--aud-text);
  cursor: pointer;
  padding: 0;
  border-radius: 50%;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  transition: all 0.15s ease;
}
.aud-ctrl-btn:hover:not(:disabled) {
  background: #21262d;
  border-color: #8b949e;
  color: var(--aud-accent-hover);
}
.aud-ctrl-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.aud-ctrl-btn svg {
  width: 20px;
  height: 20px;
  stroke: currentColor;
  fill: none;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.aud-ctrl-btn .aud-skip-num {
  position: absolute;
  font-size: 0.55rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  top: 52%;
  left: 50%;
  transform: translate(-50%, -50%);
  pointer-events: none;
}
.aud-ctrl-play {
  width: 56px;
  height: 56px;
  background: var(--aud-accent);
  border-color: var(--aud-accent-emphasis);
  color: var(--aud-on-accent);
  box-shadow: 0 4px 14px rgba(56, 139, 253, 0.35);
}
.aud-ctrl-play svg { width: 24px; height: 24px; fill: currentColor; stroke: none; }
.aud-ctrl-play:hover:not(:disabled) {
  background: var(--aud-accent-hover);
  border-color: var(--aud-accent-hover);
  color: var(--aud-on-accent);
  transform: translateY(-1px) scale(1.04);
}
.aud-speed {
  display: inline-flex;
  align-items: center;
  background: var(--aud-surface-solid);
  border: 1px solid var(--aud-border);
  border-radius: 6px;
  padding: 2px;
  gap: 1px;
}
.aud-speed-btn {
  background: none;
  border: 0;
  color: var(--aud-text-dim);
  padding: 4px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.72rem;
  font-weight: 600;
  font-family: inherit;
  font-variant-numeric: tabular-nums;
  transition: all 0.15s ease;
}
.aud-speed-btn:hover { color: var(--aud-text); }
.aud-speed-btn.active {
  background: var(--aud-accent);
  color: var(--aud-on-accent);
}
.aud-vol {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--aud-text-dim);
}
.aud-vol input {
  width: 80px;
  accent-color: var(--aud-accent);
}
`;
  document.head.appendChild(style);
};

/* ---------- shell ---------------------------------------------------- */

AudibleView.prototype.renderShell = function () {
  this.container.innerHTML = '';
  this.container.classList.add('aud-skinned');

  // Sidebar
  this.sidebarEl = el('aside', { class: 'aud-sidebar' + (this.sidebarOpen ? '' : ' collapsed') });
  this.sidebarHead = el('div', { class: 'aud-sidebar-head' });
  this.sidebarHead.appendChild(el('div', { class: 'aud-sidebar-title' }, 'Library'));

  this.searchInput = el('input', {
    type: 'search',
    placeholder: 'Search title, author, narrator…',
    'aria-label': 'Search library',
  });
  this.searchInput.addEventListener('input', () => {
    this.libraryFilter = this.searchInput.value.trim();
    this.renderList();
  });
  const searchBox = el('div', { class: 'aud-search' },
    el('span', { html: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>' }),
    this.searchInput,
  );
  this.sidebarHead.appendChild(searchBox);

  this.tabsEl = el('div', { class: 'aud-tabs', role: 'tablist' });
  for (const t of [
    { id: 'all', label: 'Library' },
    { id: 'progress', label: 'In progress' },
    { id: 'wishlist', label: 'Wishlist' },
  ]) {
    const b = el('button', {
      class: 'aud-tab' + (this.libraryTab === t.id ? ' active' : ''),
      type: 'button',
      role: 'tab',
      onclick: () => {
        this.libraryTab = t.id;
        for (const x of this.tabsEl.querySelectorAll('.aud-tab')) x.classList.remove('active');
        b.classList.add('active');
        this.loadLibrary();
      },
    }, t.label);
    this.tabsEl.appendChild(b);
  }
  this.sidebarHead.appendChild(this.tabsEl);

  this.sidebarEl.appendChild(this.sidebarHead);
  this.listEl = el('div', { class: 'aud-list' });
  this.sidebarEl.appendChild(this.listEl);

  // Main
  this.mainEl = el('section', { class: 'aud-main' });

  // Toolbar (with sidebar toggle + chapters toggle)
  this.toolbarEl = el('div', { class: 'aud-toolbar' });
  this.sidebarToggle = el('button', {
    class: 'aud-iconbtn',
    type: 'button',
    title: 'Toggle library',
    'aria-label': 'Toggle library',
    onclick: () => {
      this.sidebarOpen = !this.sidebarOpen;
      writeBool(SIDEBAR_OPEN_KEY, this.sidebarOpen);
      this.sidebarEl.classList.toggle('collapsed', !this.sidebarOpen);
    },
    html: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>',
  });
  this.chaptersToggle = el('button', {
    class: 'aud-iconbtn',
    type: 'button',
    title: 'Toggle chapters',
    'aria-label': 'Toggle chapters',
    onclick: () => {
      this.chaptersOpen = !this.chaptersOpen;
      writeBool(CHAPTERS_OPEN_KEY, this.chaptersOpen);
      this.chaptersEl.classList.toggle('collapsed', !this.chaptersOpen);
    },
    html: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/></svg>',
  });
  this.toolbarTitleWrap = el('div', { class: 'aud-toolbar-title-wrap', style: 'min-width:0;flex:1;' });
  this.toolbarTitleEl = el('div', { class: 'aud-toolbar-title' }, 'Audible');
  this.toolbarSubEl = el('div', { class: 'aud-toolbar-sub' }, '');
  this.toolbarTitleWrap.appendChild(this.toolbarTitleEl);
  this.toolbarTitleWrap.appendChild(this.toolbarSubEl);
  this.toolbarEl.appendChild(this.sidebarToggle);
  this.toolbarEl.appendChild(this.chaptersToggle);
  this.toolbarEl.appendChild(this.toolbarTitleWrap);
  this.mainEl.appendChild(this.toolbarEl);

  // Content (chapters + detail)
  this.contentEl = el('div', { class: 'aud-content' });
  this.chaptersEl = el('aside', { class: 'aud-chapters' + (this.chaptersOpen ? '' : ' collapsed') });
  this.chaptersInner = el('div');
  this.chaptersInner.appendChild(el('div', { class: 'aud-chapters-title' }, 'Chapters'));
  this.chaptersListEl = el('div');
  this.chaptersInner.appendChild(this.chaptersListEl);
  this.chaptersEl.appendChild(this.chaptersInner);
  this.contentEl.appendChild(this.chaptersEl);

  this.detailEl = el('div', { class: 'aud-detail' });
  this.contentEl.appendChild(this.detailEl);
  this.mainEl.appendChild(this.contentEl);

  // Player
  this.playerEl = this.buildPlayer();
  this.mainEl.appendChild(this.playerEl);

  this.shellEl = el('div', { class: 'aud-shell' }, this.sidebarEl, this.mainEl);
  this.container.appendChild(this.shellEl);

  this.renderDetail();
  this.renderChapters();
};

AudibleView.prototype.buildPlayer = function () {
  this.audio = new Audio();
  this.audio.preload = 'auto';
  this.audio.playbackRate = this.playbackRate;
  this.audio.volume = this.volume;

  this.audio.addEventListener('timeupdate', () => this.onTimeUpdate());
  this.audio.addEventListener('durationchange', () => this.onDurationChange());
  this.audio.addEventListener('loadedmetadata', () => this.onDurationChange());
  this.audio.addEventListener('play', () => this.setPlayIcon(true));
  this.audio.addEventListener('pause', () => this.setPlayIcon(false));
  this.audio.addEventListener('ended', () => this.setPlayIcon(false));

  // Progress row
  this.progressBar = el('div', { class: 'aud-progress-bar disabled' });
  this.progressFill = el('div', { class: 'aud-progress-fill' });
  this.progressHandle = el('div', { class: 'aud-progress-handle', style: 'left:0%' });
  this.progressBar.appendChild(this.progressFill);
  this.progressBar.appendChild(this.progressHandle);
  this.progressBar.addEventListener('click', (e) => this.onProgressClick(e));
  this.curTimeEl = el('span', { class: 'aud-time' }, '0:00');
  this.totalTimeEl = el('span', { class: 'aud-time' }, '0:00');

  const progressRow = el('div', { class: 'aud-progress-row' },
    this.curTimeEl, this.progressBar, this.totalTimeEl,
  );

  // Playback buttons
  this.playBtn = el('button', {
    class: 'aud-ctrl-btn aud-ctrl-play',
    type: 'button',
    'aria-label': 'Play',
    onclick: () => this.togglePlay(),
    disabled: 'disabled',
  });
  this.playIconEl = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  this.playIconEl.setAttribute('viewBox', '0 0 24 24');
  this.playIconEl.innerHTML = '<path d="M7 5v14l12-7z"/>';
  this.playBtn.appendChild(this.playIconEl);

  const skipBack = el('button', {
    class: 'aud-ctrl-btn',
    type: 'button',
    'aria-label': 'Back 10 seconds',
    onclick: () => this.skip(-10),
    disabled: 'disabled',
    html: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 17l-5-5 5-5"/><path d="M18 17l-5-5 5-5"/></svg><span class="aud-skip-num" style="left:70%">10</span>',
  });
  this.skipBackBtn = skipBack;
  const skipFwd = el('button', {
    class: 'aud-ctrl-btn',
    type: 'button',
    'aria-label': 'Forward 30 seconds',
    onclick: () => this.skip(30),
    disabled: 'disabled',
    html: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 17l5-5-5-5"/><path d="M6 17l5-5-5-5"/></svg><span class="aud-skip-num" style="left:32%">30</span>',
  });
  this.skipFwdBtn = skipFwd;

  // Speed group
  this.speedEl = el('div', { class: 'aud-speed', role: 'group', 'aria-label': 'Playback speed' });
  for (const s of [1, 1.25, 1.5, 2, 2.5, 3]) {
    const b = el('button', {
      class: 'aud-speed-btn' + (Math.abs(s - this.playbackRate) < 0.01 ? ' active' : ''),
      type: 'button',
      onclick: () => this.setSpeed(s),
    }, s + '×');
    this.speedEl.appendChild(b);
  }

  // Volume
  this.volEl = el('div', { class: 'aud-vol' });
  const volIcon = el('span', { html: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>' });
  this.volSlider = el('input', { type: 'range', min: '0', max: '1', step: '0.01' });
  this.volSlider.value = String(this.volume);
  this.volSlider.addEventListener('input', () => {
    const v = parseFloat(this.volSlider.value);
    this.volume = isFinite(v) ? v : 1;
    this.audio.volume = this.volume;
    writeNum(VOLUME_KEY, this.volume);
  });
  this.volEl.appendChild(volIcon);
  this.volEl.appendChild(this.volSlider);

  this.statusLabel = el('div', { class: 'aud-controls-left' }, '');
  const controls = el('div', { class: 'aud-controls' },
    this.statusLabel,
    el('div', { class: 'aud-controls-mid' }, skipBack, this.playBtn, skipFwd),
    el('div', { class: 'aud-controls-right' }, this.speedEl, this.volEl),
  );

  return el('div', { class: 'aud-player' }, progressRow, controls);
};

AudibleView.prototype.setPlayIcon = function (isPlaying) {
  this.playIconEl.innerHTML = isPlaying
    ? '<path d="M6 5h4v14H6zM14 5h4v14h-4z"/>'
    : '<path d="M7 5v14l12-7z"/>';
  this.playBtn.setAttribute('aria-label', isPlaying ? 'Pause' : 'Play');
};

AudibleView.prototype.setSpeed = function (s) {
  this.playbackRate = s;
  writeNum(SPEED_KEY, s);
  if (this.audio) this.audio.playbackRate = s;
  for (const b of this.speedEl.querySelectorAll('.aud-speed-btn')) {
    b.classList.toggle('active', b.textContent === s + '×');
  }
};

AudibleView.prototype.togglePlay = function () {
  if (!this.audio || !this.audio.src) return;
  if (this.audio.paused) this.audio.play().catch((err) => {
    console.warn('audible: play() rejected', err);
  });
  else this.audio.pause();
};

AudibleView.prototype.skip = function (deltaSec) {
  if (!this.audio || !isFinite(this.audio.duration)) return;
  const next = Math.max(0, Math.min(this.audio.duration, this.audio.currentTime + deltaSec));
  this.audio.currentTime = next;
};

AudibleView.prototype.onProgressClick = function (e) {
  if (this.progressBar.classList.contains('disabled')) return;
  const rect = this.progressBar.getBoundingClientRect();
  const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  if (this.audio && isFinite(this.audio.duration)) {
    this.audio.currentTime = ratio * this.audio.duration;
  } else if (this.totalDurationMs > 0) {
    // No audio loaded but we have chapter info — store as virtual scrub
    this.lastPositionMs = ratio * this.totalDurationMs;
    this.renderProgressFromVirtual();
  }
};

AudibleView.prototype.onTimeUpdate = function () {
  if (!this.audio) return;
  const cur = this.audio.currentTime || 0;
  const dur = isFinite(this.audio.duration) ? this.audio.duration : 0;
  this.curTimeEl.textContent = fmtDuration(cur * 1000);
  if (dur > 0) {
    const pct = Math.max(0, Math.min(100, (cur / dur) * 100));
    this.progressFill.style.width = pct + '%';
    this.progressHandle.style.left = pct + '%';
  }
  this.maybeMarkChapterFromTime(cur * 1000);
};

AudibleView.prototype.onDurationChange = function () {
  const dur = isFinite(this.audio.duration) ? this.audio.duration : 0;
  this.totalTimeEl.textContent = fmtDuration(dur * 1000);
};

AudibleView.prototype.renderProgressFromVirtual = function () {
  if (!this.totalDurationMs) return;
  const pct = Math.max(0, Math.min(100, (this.lastPositionMs / this.totalDurationMs) * 100));
  this.progressFill.style.width = pct + '%';
  this.progressHandle.style.left = pct + '%';
  this.curTimeEl.textContent = fmtDuration(this.lastPositionMs);
  this.totalTimeEl.textContent = fmtDuration(this.totalDurationMs);
  this.maybeMarkChapterFromTime(this.lastPositionMs);
};

AudibleView.prototype.maybeMarkChapterFromTime = function (ms) {
  if (!this.currentChapters || !this.currentChapters.length) return;
  let activeIdx = -1;
  for (let i = 0; i < this.currentChapters.length; i++) {
    const ch = this.currentChapters[i];
    const start = ch.start_ms;
    const end = start + ch.length_ms;
    if (ms >= start && ms < end) { activeIdx = i; break; }
  }
  if (activeIdx === -1 && ms >= 0 && this.currentChapters.length) {
    activeIdx = this.currentChapters.length - 1;
  }
  for (const node of this.chaptersListEl.querySelectorAll('.aud-chapter-item')) {
    const idx = parseInt(node.dataset.idx, 10);
    node.classList.toggle('active', idx === activeIdx);
  }
};

/* ---------- library list -------------------------------------------- */

AudibleView.prototype.loadLibrary = async function () {
  this.libraryError = null;
  this.libraryLoaded = false;
  this.renderList();
  try {
    let items;
    if (this.libraryTab === 'progress') {
      const r = await this.fetchJson('/v1/audible/progress');
      items = r.items || [];
    } else if (this.libraryTab === 'wishlist') {
      const r = await this.fetchJson('/v1/audible/wishlist');
      items = r.items || [];
    } else {
      const r = await this.fetchJson('/v1/audible/library', { limit: 1000 });
      items = r.items || [];
    }
    this.library = items;
    this.libraryLoaded = true;
    this.renderList();
  } catch (err) {
    this.libraryError = String(err.message || err);
    this.libraryLoaded = true;
    this.renderList();
  }
};

AudibleView.prototype.renderList = function () {
  this.listEl.innerHTML = '';
  if (!this.libraryLoaded) {
    this.listEl.appendChild(el('div', { class: 'aud-list-empty' }, 'Loading…'));
    return;
  }
  if (this.libraryError) {
    this.listEl.appendChild(el('div', { class: 'aud-list-error' },
      el('div', null, 'Could not load library:'),
      el('div', { style: 'margin-top:6px;font-family:monospace;font-size:0.78rem;' }, this.libraryError),
    ));
    return;
  }
  const filter = (this.libraryFilter || '').toLowerCase();
  const matches = this.library.filter((b) => {
    if (!filter) return true;
    return (b.title || '').toLowerCase().includes(filter)
      || (b.authors || []).some((a) => (a || '').toLowerCase().includes(filter))
      || (b.narrators || []).some((n) => (n || '').toLowerCase().includes(filter))
      || (b.series_title || '').toLowerCase().includes(filter);
  });
  if (!matches.length) {
    const msg = filter
      ? `No books match "${filter}".`
      : (this.libraryTab === 'progress'
        ? 'Nothing in progress yet.\nStart listening to a book to see it here.'
        : this.libraryTab === 'wishlist'
          ? 'Wishlist is empty.'
          : 'Library is empty.');
    this.listEl.appendChild(el('div', { class: 'aud-list-empty' }, msg));
    return;
  }
  for (const b of matches) {
    this.listEl.appendChild(this.buildCard(b));
  }
};

AudibleView.prototype.buildCard = function (b) {
  const cover = el('img', { class: 'aud-card-cover', alt: '' });
  cover.addEventListener('error', () => {
    const ph = el('div', { class: 'aud-card-cover placeholder' }, (b.title || '?').slice(0, 2).toUpperCase());
    cover.replaceWith(ph);
  });
  this.attachCover(b.asin, cover);

  const title = el('div', { class: 'aud-card-title' }, b.title || 'Untitled');
  const author = el('div', { class: 'aud-card-author' }, (b.authors || []).join(', ') || '—');
  const meta = el('div', { class: 'aud-card-meta' }, title, author);

  if (typeof b.percent_complete === 'number' && b.percent_complete > 0) {
    const finished = b.is_finished;
    const bar = el('div', { class: 'aud-card-progress' + (finished ? ' finished' : '') },
      el('span', { style: `width:${Math.min(100, Math.max(0, finished ? 100 : b.percent_complete))}%` }),
    );
    meta.appendChild(bar);
    meta.appendChild(el('div', { class: 'aud-card-progress-label' },
      finished ? 'Finished' : `${b.percent_complete.toFixed(0)}% · ${fmtMinutes(b.runtime_minutes)}`));
  } else if (b.runtime_minutes) {
    meta.appendChild(el('div', { class: 'aud-card-progress-label' }, fmtMinutes(b.runtime_minutes)));
  }

  const card = el('div', {
    class: 'aud-card' + (this.currentAsin === b.asin ? ' active' : ''),
    onclick: () => this.loadBook(b.asin),
  }, cover, meta);
  return card;
};

AudibleView.prototype.attachCover = function (asin, imgEl) {
  if (!asin) return;
  const cached = this.coverObjectUrls.get(asin);
  if (cached) { imgEl.src = cached; return; }
  this.fetchBlob('/v1/audible/cover/' + encodeURIComponent(asin), { size: 252 })
    .then((blob) => {
      const url = URL.createObjectURL(blob);
      this.coverObjectUrls.set(asin, url);
      imgEl.src = url;
    })
    .catch(() => imgEl.dispatchEvent(new Event('error')));
};

/* ---------- detail / chapters / audio ------------------------------- */

AudibleView.prototype.loadBook = async function (asin, opts) {
  if (!asin) return;
  if (this.statusPollTimer) {
    clearInterval(this.statusPollTimer);
    this.statusPollTimer = null;
  }
  const wasSilent = opts && opts.silent;
  this.currentAsin = asin;
  writeStr(LAST_BOOK_KEY, asin);
  for (const node of this.listEl.querySelectorAll('.aud-card')) {
    // Already set via active styling on next renderList; mark immediately too.
    node.classList.remove('active');
  }
  this.currentBook = null;
  this.currentChapters = [];
  this.totalDurationMs = 0;
  this.lastPositionMs = 0;
  if (!wasSilent) this.renderDetail({ loading: true });
  this.renderChapters();
  this.renderList();

  try {
    const [details, chapters] = await Promise.all([
      this.fetchJson('/v1/audible/book/' + encodeURIComponent(asin)),
      this.fetchJson('/v1/audible/book/' + encodeURIComponent(asin) + '/chapters').catch(() => null),
    ]);
    this.currentBook = details;
    if (chapters) {
      this.currentChapters = chapters.chapters || [];
      this.totalDurationMs = chapters.total_ms || 0;
      this.lastPositionMs = chapters.last_position_ms || details.last_position_ms || 0;
    } else {
      this.lastPositionMs = details.last_position_ms || 0;
    }
    this.renderDetail();
    this.renderChapters();
    this.refreshAudioStatus({ kickIfMissing: false });
  } catch (err) {
    this.renderDetail({ error: String(err.message || err) });
  }
};

AudibleView.prototype.renderDetail = function (state) {
  this.detailEl.innerHTML = '';
  if (state && state.loading) {
    this.detailEl.appendChild(el('div', { class: 'aud-detail-empty' }, 'Loading book…'));
    return;
  }
  if (state && state.error) {
    this.detailEl.appendChild(el('div', { class: 'aud-detail-empty' },
      el('div', null, 'Could not load this book.'),
      el('div', { style: 'margin-top:8px;font-family:monospace;font-size:0.8rem;color:#ffb4b4' }, state.error),
    ));
    return;
  }
  const b = this.currentBook;
  if (!b) {
    this.detailEl.appendChild(el('div', { class: 'aud-detail-empty' },
      'Pick a book from the library on the left.',
    ));
    this.toolbarTitleEl.textContent = 'Audible';
    this.toolbarSubEl.textContent = '';
    return;
  }

  this.toolbarTitleEl.textContent = b.title || 'Untitled';
  this.toolbarSubEl.textContent = (b.authors || []).join(', ');

  const cover = el('img', { class: 'aud-detail-cover', alt: '' });
  cover.addEventListener('error', () => {
    const ph = el('div', { class: 'aud-detail-cover', style: 'display:flex;align-items:center;justify-content:center;color:var(--aud-text-muted);font-size:1.2rem;font-weight:600' }, (b.title || '?').slice(0, 2).toUpperCase());
    cover.replaceWith(ph);
  });
  this.attachCover(b.asin, cover);

  const info = el('div', { class: 'aud-detail-info' });
  info.appendChild(el('h2', null, b.title || 'Untitled'));
  if (b.subtitle) info.appendChild(el('div', { class: 'aud-detail-sub' }, b.subtitle));
  if ((b.authors || []).length) info.appendChild(el('div', { class: 'aud-detail-row' }, el('b', null, 'By: '), (b.authors || []).join(', ')));
  if ((b.narrators || []).length) info.appendChild(el('div', { class: 'aud-detail-row' }, el('b', null, 'Narrated by: '), (b.narrators || []).join(', ')));
  if (b.series_title) info.appendChild(el('div', { class: 'aud-detail-row' },
    el('b', null, 'Series: '),
    b.series_title + (b.series_sequence ? ` (Book ${b.series_sequence})` : ''),
  ));

  const stats = el('div', { class: 'aud-detail-stats' });
  if (b.runtime_minutes) stats.appendChild(el('span', { class: 'aud-pill' }, fmtMinutes(b.runtime_minutes)));
  if (b.release_date) stats.appendChild(el('span', { class: 'aud-pill' }, b.release_date));
  if (b.language) stats.appendChild(el('span', { class: 'aud-pill' }, b.language));
  if (b.publisher) stats.appendChild(el('span', { class: 'aud-pill' }, b.publisher));
  if (b.rating_avg) stats.appendChild(el('span', { class: 'aud-pill' }, `★ ${b.rating_avg} (${(b.rating_count || 0).toLocaleString()})`));
  if (typeof b.percent_complete === 'number' && b.percent_complete > 0) {
    stats.appendChild(el('span', { class: 'aud-pill' },
      b.is_finished ? 'Finished' : `${b.percent_complete.toFixed(1)}% complete`));
  }
  if ((b.categories || []).length) {
    for (const c of b.categories.slice(0, 4)) {
      stats.appendChild(el('span', { class: 'aud-pill' }, c));
    }
  }
  info.appendChild(stats);

  const head = el('div', { class: 'aud-detail-head' }, cover, info);
  this.detailEl.appendChild(head);

  if (b.description) {
    this.detailEl.appendChild(el('div', { class: 'aud-detail-desc' }, b.description));
  }

  this.statusBanner = el('div', { class: 'aud-status-banner' }, 'Checking audio status…');
  this.detailEl.appendChild(this.statusBanner);
};

AudibleView.prototype.renderChapters = function () {
  this.chaptersListEl.innerHTML = '';
  if (!this.currentChapters.length) {
    this.chaptersListEl.appendChild(el('div', { class: 'aud-list-empty', style: 'padding:14px 6px' },
      this.currentBook ? 'No chapter info.' : 'Pick a book to see chapters.'));
    return;
  }
  this.currentChapters.forEach((ch, idx) => {
    const item = el('div', {
      class: 'aud-chapter-item',
      'data-idx': idx,
      onclick: () => this.seekToChapter(idx),
    },
      el('div', null, `${idx + 1}. ${ch.title}`),
      el('div', { class: 'aud-chapter-time' }, fmtDuration(ch.start_ms) + ' · ' + fmtDuration(ch.length_ms)),
    );
    this.chaptersListEl.appendChild(item);
  });
  // Mark current chapter (from saved last_position)
  this.maybeMarkChapterFromTime(this.audio && this.audio.currentTime
    ? this.audio.currentTime * 1000
    : this.lastPositionMs);
};

AudibleView.prototype.seekToChapter = function (idx) {
  const ch = this.currentChapters[idx];
  if (!ch) return;
  if (this.audio && this.audio.src && isFinite(this.audio.duration)) {
    this.audio.currentTime = (ch.start_ms || 0) / 1000;
  } else {
    this.lastPositionMs = ch.start_ms || 0;
    this.renderProgressFromVirtual();
  }
};

/* ---------- audio status / streaming -------------------------------- */

AudibleView.prototype.refreshAudioStatus = async function (opts) {
  if (!this.currentAsin) return;
  const asin = this.currentAsin;
  let status;
  try {
    status = await this.fetchJson('/v1/audible/audio/' + encodeURIComponent(asin) + '/status');
  } catch (err) {
    if (this.statusBanner) {
      this.statusBanner.className = 'aud-status-banner err';
      this.statusBanner.textContent = 'Audio status check failed: ' + (err.message || err);
    }
    return;
  }
  if (asin !== this.currentAsin) return;
  this.audioStatus = status;
  this.renderAudioStatus();

  if (status.playable) {
    this.attachAudioStream();
    this.enablePlayer(true);
  } else {
    this.enablePlayer(false);
    if (this.totalDurationMs > 0) this.renderProgressFromVirtual();
  }

  if (!status.playable && status.downloading) {
    this.startStatusPoll();
  } else if (status.downloading) {
    this.startStatusPoll();
  } else if (this.statusPollTimer) {
    clearInterval(this.statusPollTimer);
    this.statusPollTimer = null;
  }

  if (opts && opts.kickIfMissing && !status.playable && !status.downloading) {
    this.kickDownload();
  }
};

AudibleView.prototype.startStatusPoll = function () {
  if (this.statusPollTimer) return;
  this.statusPollTimer = setInterval(() => this.refreshAudioStatus(), 4000);
};

AudibleView.prototype.renderAudioStatus = function () {
  if (!this.statusBanner) return;
  const s = this.audioStatus || {};
  this.statusBanner.innerHTML = '';
  this.statusBanner.classList.remove('ok', 'warn', 'err');
  if (s.playable) {
    this.statusBanner.classList.add('ok');
    this.statusBanner.appendChild(el('span', null, 'Audio ready — playing from local cache.'));
  } else if (s.downloading) {
    this.statusBanner.classList.add('warn');
    this.statusBanner.appendChild(el('span', null, 'Downloading audio… this can take several minutes.'));
  } else if (s.encrypted_only) {
    this.statusBanner.classList.add('warn');
    this.statusBanner.appendChild(el('span', null, 'Encrypted .aax downloaded but not yet decoded. Decrypt manually with audible-cli to enable in-browser playback.'));
  } else {
    this.statusBanner.appendChild(el('span', null,
      s.last_error
        ? 'Audio not cached. Last download attempt failed.'
        : 'Audio is not cached locally. Download to enable playback.'));
    const btn = el('button', {
      type: 'button',
      onclick: async () => {
        btn.disabled = true;
        btn.textContent = 'Starting…';
        await this.kickDownload();
        btn.disabled = false;
        btn.textContent = 'Download';
      },
    }, 'Download');
    this.statusBanner.appendChild(btn);
    if (s.last_error) {
      this.statusBanner.classList.add('err');
      const det = el('div', {
        style: 'margin-top:6px;font-family:monospace;font-size:0.74rem;opacity:0.85;max-height:80px;overflow:auto',
      }, s.last_error);
      this.statusBanner.appendChild(det);
    }
  }
};

AudibleView.prototype.kickDownload = async function () {
  if (!this.currentAsin) return;
  try {
    await this.fetchJson('/v1/audible/audio/' + encodeURIComponent(this.currentAsin) + '/download', null, {
      method: 'POST',
    });
  } catch (err) {
    console.warn('audible: download kickoff failed', err);
  }
  this.refreshAudioStatus();
};

AudibleView.prototype.attachAudioStream = async function () {
  if (!this.audio || !this.currentAsin) return;
  if (this.audioBlobAsin === this.currentAsin && this.audio.src) return;
  // Browsers won't send Authorization headers on <audio src>, so we
  // pull the file as a blob and hand the player a blob: URL.
  // (Range/scrubbing inside the blob is handled by the browser; the
  // server already streamed the whole file.)
  const asin = this.currentAsin;
  try {
    const blob = await this.fetchBlob('/v1/audible/audio/' + encodeURIComponent(asin));
    if (asin !== this.currentAsin) return; // user moved on
    if (this.audioObjectUrl) {
      try { URL.revokeObjectURL(this.audioObjectUrl); } catch (_) {}
      this.audioObjectUrl = null;
    }
    this.audioObjectUrl = URL.createObjectURL(blob);
    this.audioBlobAsin = asin;
    this.audio.src = this.audioObjectUrl;
    this.audio.load();
    if (this.lastPositionMs > 0) {
      const seekTarget = this.lastPositionMs / 1000;
      const onLoaded = () => {
        try { this.audio.currentTime = seekTarget; } catch (_) {}
        this.audio.removeEventListener('loadedmetadata', onLoaded);
      };
      this.audio.addEventListener('loadedmetadata', onLoaded);
    }
  } catch (err) {
    console.warn('audible: audio fetch failed', err);
    if (this.statusBanner) {
      this.statusBanner.classList.add('err');
      this.statusBanner.classList.remove('ok', 'warn');
      this.statusBanner.innerHTML = '';
      this.statusBanner.appendChild(el('span', null, 'Failed to load audio: ' + (err.message || err)));
    }
  }
};

AudibleView.prototype.enablePlayer = function (enabled) {
  this.playBtn.disabled = !enabled;
  this.skipBackBtn.disabled = !enabled;
  this.skipFwdBtn.disabled = !enabled;
  this.progressBar.classList.toggle('disabled', !enabled);
};

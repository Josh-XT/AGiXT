/* Audible — AGiXT desktop audiobook reader.
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
  if (typeof this.transcriptionUnlisten === 'function') {
    try { this.transcriptionUnlisten(); } catch (_) {}
    this.transcriptionUnlisten = null;
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
/* Pull all visual tokens off the host palette so the audible page
   matches the rest of AGiXT (chat, machines, etc.). The --aud-*
   names stay as a stable contract for the rest of the audible CSS;
   their values now resolve to the shared design system. NOTE: do
   NOT set "display" here — .view-pane[hidden] { display: none }
   from styles.css is what hides this pane when the user switches to
   a different sidebar tab, and "display: flex" here would silently
   override it (same specificity, later source order). */
.view-pane[data-view="audible"] {
  --aud-bg: var(--bg);
  --aud-inset: rgba(0, 0, 0, 0.3);
  --aud-surface: var(--panel);
  --aud-surface-strong: var(--panel);
  --aud-surface-solid: var(--panel-2);
  --aud-text: var(--text);
  --aud-text-dim: var(--text-dim);
  --aud-text-muted: var(--text-faint);
  --aud-accent: var(--accent);
  --aud-accent-hover: var(--accent-2);
  --aud-accent-emphasis: var(--accent);
  --aud-accent-soft: rgba(107, 123, 255, 0.18);
  --aud-border: var(--border);
  --aud-border-muted: rgba(255, 255, 255, 0.04);
  --aud-on-accent: #ffffff;

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
  flex-shrink: 0;
  background: var(--aud-surface-solid);
  /* Sidebar lives on the RIGHT side of the shell now — border on the
     left edge separates it from the player/detail column. */
  border-left: 1px solid var(--aud-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}
/* Collapsed strip — replaces the sidebar entirely (workspace pattern).
   28px wide button with a vertical "Library" label and a chevron that
   reads as "expand toward me". */
.aud-sidebar-collapsed {
  flex: 0 0 auto;
  width: 28px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 10px 0;
  background: var(--aud-surface-solid);
  border: 0;
  border-left: 1px solid var(--aud-border);
  color: var(--aud-text);
  cursor: pointer;
  font-family: inherit;
}
.aud-sidebar-collapsed:hover { background: rgba(177, 186, 196, 0.06); }
.aud-sidebar-collapsed-icon { opacity: 0.85; display: flex; }
.aud-sidebar-collapsed-label {
  writing-mode: vertical-rl;
  transform: rotate(180deg);
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.13em;
  text-transform: uppercase;
  color: var(--aud-accent);
  opacity: 0.85;
}
.aud-sidebar-head {
  padding: 14px 14px 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  border-bottom: 1px solid var(--aud-border-muted);
}
.aud-sidebar-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.aud-sidebar-title {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.13em;
  color: var(--aud-accent);
}
.aud-sidebar-collapse-btn { width: 26px; height: 26px; opacity: 0.75; }
.aud-sidebar-collapse-btn:hover { opacity: 1; }
.aud-sidebar-collapse-btn svg { width: 14px; height: 14px; }
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

/* Read-along transcript */
.aud-transcript {
  margin-top: 22px;
  padding-top: 18px;
  border-top: 1px solid var(--aud-border-muted);
}
.aud-transcript-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.aud-transcript-title {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.13em;
  color: var(--aud-accent);
}
.aud-transcript-redo {
  background: transparent;
  color: var(--aud-text-dim);
  border: 1px solid var(--aud-border);
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 0.74rem;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
}
.aud-transcript-redo:hover {
  background: var(--aud-surface-solid);
  color: var(--aud-text);
  border-color: var(--aud-accent);
}
.aud-transcript-empty {
  color: var(--aud-text-muted);
  font-size: 0.88rem;
  font-style: italic;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.aud-transcript-empty.err { color: #ffb4b4; font-style: normal; }
.aud-transcript-help {
  font-size: 0.78rem;
  color: var(--aud-text-muted);
  font-style: italic;
}
.aud-transcript-progress {
  height: 6px;
  background: var(--aud-border-muted);
  border-radius: 999px;
  overflow: hidden;
}
.aud-transcript-progress-fill {
  height: 100%;
  background: var(--aud-accent);
  transition: width 0.4s ease;
}
.aud-transcript-body {
  font-family: 'Lora', 'Georgia', serif;
  font-size: 1.05rem;
  line-height: 1.85;
  color: var(--aud-text-dim);
}
.aud-transcript-para {
  margin: 0 0 1.1rem;
  text-indent: 1.6rem;
}
.aud-transcript-para:last-child { margin-bottom: 0; }
.aud-transcript-seg {
  cursor: pointer;
  padding: 0.05rem 0.1rem;
  border-radius: 3px;
  transition: background 0.15s ease, color 0.15s ease;
}
.aud-transcript-seg:hover { background: rgba(177, 186, 196, 0.06); color: var(--aud-text); }
.aud-transcript-seg.current {
  background: rgba(56, 139, 253, 0.22);
  color: #ffffff;
  font-weight: 500;
  box-shadow: 0 0 0 1px rgba(56, 139, 253, 0.4);
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
  flex-wrap: wrap;
}
.aud-status-banner[hidden] { display: none; }
.aud-status-banner > span {
  flex: 1;
  min-width: 0;
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

  // Library sidebar (sits on the RIGHT, mirrors the workspace editor's
  // Files panel — thin vertical "Library" strip when collapsed, clickable
  // to re-expand).
  this.sidebarEl = el('aside', { class: 'aud-sidebar' });
  this.sidebarHead = el('div', { class: 'aud-sidebar-head' });
  const headTitleRow = el('div', { class: 'aud-sidebar-title-row' });
  headTitleRow.appendChild(el('div', { class: 'aud-sidebar-title' }, 'Library'));
  const collapseBtn = el('button', {
    class: 'aud-iconbtn aud-sidebar-collapse-btn',
    type: 'button',
    title: 'Collapse library',
    'aria-label': 'Collapse library',
    onclick: () => this.setSidebarOpen(false),
    // Chevron points right → "tuck panel away to the right edge".
    html: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>',
  });
  headTitleRow.appendChild(collapseBtn);
  this.sidebarHead.appendChild(headTitleRow);

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

  // Collapsed-strip alternative — vertical "Library" pill that sits where
  // the sidebar used to. Click it to re-expand.
  this.sidebarStripEl = el('button', {
    class: 'aud-sidebar-collapsed',
    type: 'button',
    title: 'Show library',
    'aria-label': 'Show library',
    onclick: () => this.setSidebarOpen(true),
  });
  // Chevron points left because the sidebar lives on the right edge —
  // expanding pulls the panel toward the center.
  this.sidebarStripEl.appendChild(el('span', {
    class: 'aud-sidebar-collapsed-icon',
    html: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>',
  }));
  this.sidebarStripEl.appendChild(el('span', { class: 'aud-sidebar-collapsed-label' }, 'Library'));

  // Main column (toolbar / content / player)
  this.mainEl = el('section', { class: 'aud-main' });

  // Toolbar — chapters toggle + book title. Sidebar toggle lives in the
  // sidebar header now (workspace-style chevron + collapsed strip).
  this.toolbarEl = el('div', { class: 'aud-toolbar' });
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

  // Order: main column first, library sidebar (or collapsed strip) on
  // the right edge — flush with the player.
  this.shellEl = el('div', { class: 'aud-shell' }, this.mainEl, this.sidebarEl, this.sidebarStripEl);
  this.container.appendChild(this.shellEl);

  // Sync the visibility from persisted preference.
  this.setSidebarOpen(this.sidebarOpen, { skipPersist: true });

  this.renderDetail();
  this.renderChapters();
};

AudibleView.prototype.setSidebarOpen = function (open, opts) {
  this.sidebarOpen = !!open;
  if (!opts || !opts.skipPersist) writeBool(SIDEBAR_OPEN_KEY, this.sidebarOpen);
  if (this.sidebarEl) this.sidebarEl.style.display = this.sidebarOpen ? '' : 'none';
  if (this.sidebarStripEl) this.sidebarStripEl.style.display = this.sidebarOpen ? 'none' : '';
  // Re-expanding should put the user back on the currently-playing book
  // in the list — same affordance the workspace editor has when re-
  // opening Files.
  if (this.sidebarOpen) this.scrollSelectedIntoView();
};

AudibleView.prototype.scrollSelectedIntoView = function () {
  if (!this.listEl || !this.currentAsin) return;
  // Defer to the next frame so the list has rendered + the sidebar is
  // visible (display: none → '' takes a tick to layout).
  requestAnimationFrame(() => {
    if (!this.listEl) return;
    const card = this.listEl.querySelector('.aud-card.active');
    if (card && typeof card.scrollIntoView === 'function') {
      card.scrollIntoView({ block: 'nearest', behavior: 'auto' });
    }
  });
};

AudibleView.prototype.buildPlayer = function () {
  this.audio = new Audio();
  this.audio.preload = 'auto';
  this.audio.playbackRate = this.playbackRate;
  this.audio.volume = this.volume;

  this.audio.addEventListener('timeupdate', () => this.onTimeUpdate());
  // `seeked` fires once the browser finishes a seek. Programmatic
  // assignments to `audio.currentTime` are async (especially while
  // paused), so without this the UI can stay at 0:00 while audio is
  // actually positioned at `lastPositionMs` from the user's saved
  // Audible progress — pressing Play then plays from "later in the
  // book" while the visible time still reads 0:00.
  this.audio.addEventListener('seeked', () => this.onTimeUpdate());
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
  const ms = cur * 1000;
  this.maybeMarkChapterFromTime(ms);
  this.highlightTranscriptAt(ms);
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
  // Whenever the list re-renders we want the active card to be visible
  // — covers the case where the user reopens the page and the auto-
  // restored book is well below the fold.
  this.scrollSelectedIntoView();
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
  this.currentTranscript = null;
  this.transcriptSegEls = null;
  this.totalDurationMs = 0;
  this.lastPositionMs = 0;
  this.lastTranscriptIdx = -1;
  if (!wasSilent) this.renderDetail({ loading: true });
  this.renderChapters();
  this.renderList();

  try {
    const [details, chapters, transcript] = await Promise.all([
      this.fetchJson('/v1/audible/book/' + encodeURIComponent(asin)),
      this.fetchJson('/v1/audible/book/' + encodeURIComponent(asin) + '/chapters').catch(() => null),
      this.fetchJson('/v1/audible/book/' + encodeURIComponent(asin) + '/transcript').catch(() => null),
    ]);
    this.currentBook = details;
    if (chapters) {
      this.currentChapters = chapters.chapters || [];
      this.totalDurationMs = chapters.total_ms || 0;
      this.lastPositionMs = chapters.last_position_ms || details.last_position_ms || 0;
    } else {
      this.lastPositionMs = details.last_position_ms || 0;
    }
    this.currentTranscript = transcript || null;
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

  // Start the status banner hidden — `renderAudioStatus` will reveal
  // it only when there's something for the user to act on (download
  // pending, decode failure, etc). For the common case of a cached
  // book we never show it.
  this.statusBanner = el('div', { class: 'aud-status-banner', hidden: '' });
  this.detailEl.appendChild(this.statusBanner);

  // Read-along transcript — segment-timed text rendered alongside the
  // player, with the current segment highlighted as audio plays. The
  // server transcribes the audiobook automatically once the audio
  // download finishes; this section auto-refreshes from the status
  // poll until the transcript is ready.
  this.renderTranscript();
};

AudibleView.prototype.renderTranscript = function () {
  if (!this.detailEl) return;
  // Remove any prior transcript host so re-renders don't stack.
  const prior = this.detailEl.querySelector('.aud-transcript');
  if (prior) prior.remove();
  this.transcriptSegEls = null;
  this.lastTranscriptIdx = -1;

  const t = this.currentTranscript;
  const segs = (t && t.segments) || [];
  const status = (t && t.status) || (this.audioStatus && this.audioStatus.transcript) || { state: 'idle' };
  const txState = status.state || 'idle';
  const audioPlayable = !!(this.audioStatus && this.audioStatus.playable);
  const wrap = el('div', { class: 'aud-transcript' });
  const titleRow = el('div', { class: 'aud-transcript-title-row' });
  titleRow.appendChild(el('div', { class: 'aud-transcript-title' }, 'Read-along'));
  // Show a transcribe-action button whenever audio is cached AND no
  // job is in flight — the label depends on whether we already have a
  // transcript to discard.
  if (audioPlayable && txState !== 'transcribing') {
    const hasSegs = segs.length > 0;
    titleRow.appendChild(el('button', {
      class: 'aud-transcript-redo',
      type: 'button',
      title: hasSegs
        ? 'Discard this transcript and re-run transcription on the cached audio. Use this if the highlighted words drift out of sync with the audio.'
        : 'Run transcription on the cached audio.',
      onclick: () => this.resetTranscript(),
    }, hasSegs ? 'Re-transcribe' : 'Transcribe'));
  }
  wrap.appendChild(titleRow);

  if (!segs.length) {
    wrap.appendChild(this.buildTranscriptStatusBlock(status));
    this.detailEl.appendChild(wrap);
    return;
  }

  const body = el('div', { class: 'aud-transcript-body' });
  const segEls = new Array(segs.length);

  // Group segments into paragraphs. Whisper-base segments often don't
  // terminate at sentence boundaries — base.en cuts on VAD silence,
  // not on punctuation — so we can't rely on a hard char-count cap
  // (it would force breaks mid-sentence). Instead:
  //   * prefer to break at a sentence end after ~360 chars
  //   * past 700 chars, fall back to any "weak" break (comma, semi-
  //     colon, em-dash) so paragraphs don't run away
  //   * only force a break with no punctuation past 1500 chars, as a
  //     last-resort wall-of-text guard
  const PARAGRAPH_SOFT_BREAK_CHARS = 360;
  const PARAGRAPH_HARD_BREAK_CHARS = 700;
  const PARAGRAPH_MAX_BREAK_CHARS = 1500;
  const SENTENCE_END_RE = /[.!?]["')\]]?$/;
  const WEAK_BREAK_RE = /[,;:][\s"')\]]*$|[—–-]\s*$/;

  let para = el('p', { class: 'aud-transcript-para' });
  let charCount = 0;
  segs.forEach((seg, i) => {
    const text = (seg.text || '').trim();
    const span = el('span', {
      class: 'aud-transcript-seg',
      'data-idx': i,
      onclick: () => {
        const startSec = (Number(seg.start) || 0) / 1000;
        if (this.audio && this.audio.src && isFinite(this.audio.duration)) {
          this.audio.currentTime = startSec;
        } else {
          this.lastPositionMs = Number(seg.start) || 0;
          this.renderProgressFromVirtual();
        }
      },
    }, text + ' ');
    segEls[i] = span;
    para.appendChild(span);
    charCount += text.length + 1;

    const endsSentence = SENTENCE_END_RE.test(text);
    const endsWeakly = WEAK_BREAK_RE.test(text);
    const shouldBreak =
      (endsSentence && charCount >= PARAGRAPH_SOFT_BREAK_CHARS)
      || (charCount >= PARAGRAPH_HARD_BREAK_CHARS && (endsSentence || endsWeakly))
      || charCount >= PARAGRAPH_MAX_BREAK_CHARS;
    if (shouldBreak) {
      body.appendChild(para);
      para = el('p', { class: 'aud-transcript-para' });
      charCount = 0;
    }
  });
  if (para.childNodes.length) body.appendChild(para);

  this.transcriptSegEls = segEls;
  this.transcriptSegmentStarts = segs.map((s) => Number(s.start) || 0);
  wrap.appendChild(body);
  this.detailEl.appendChild(wrap);

  // If the audio is already at a known position, show that highlighted
  // segment immediately rather than waiting for the next time-update.
  const ms = (this.audio && isFinite(this.audio.currentTime))
    ? this.audio.currentTime * 1000
    : this.lastPositionMs;
  this.highlightTranscriptAt(ms);
};

AudibleView.prototype.buildTranscriptStatusBlock = function (status) {
  // Render a friendly empty/progress state for the transcript section
  // when no segments are available yet. Shape mirrors `_read_transcript_status`.
  const state = (status && status.state) || 'idle';
  if (state === 'transcribing') {
    const total = status.chunk_count || 0;
    const done = status.chunks_done || 0;
    const pct = total ? Math.max(0, Math.min(100, Math.round((done / total) * 100))) : 0;
    const bar = el('div', { class: 'aud-transcript-progress' },
      el('div', { class: 'aud-transcript-progress-fill', style: `width:${pct}%` }),
    );
    const inner = el('div', { class: 'aud-transcript-empty' },
      el('div', null, status.message || `Transcribing audio… (${done}/${total} chunks)`),
      bar,
      el('div', { class: 'aud-transcript-help' },
        'Read-along will appear here automatically when this finishes.'),
    );
    return inner;
  }
  if (state === 'error') {
    return el('div', { class: 'aud-transcript-empty err' },
      el('div', null, 'Transcription failed.'),
      el('div', { class: 'aud-transcript-help' }, status.error || 'Try downloading the audio again.'),
    );
  }
  // idle / unknown — no transcript and not currently working on one.
  // Most often this just means audio isn't downloaded yet.
  const playable = this.audioStatus && this.audioStatus.playable;
  return el('div', { class: 'aud-transcript-empty' },
    playable
      ? 'Transcription will start automatically the next time the audio is processed.'
      : 'Transcription will start automatically once the audio finishes downloading.',
  );
};

AudibleView.prototype.highlightTranscriptAt = function (ms) {
  const segEls = this.transcriptSegEls;
  const starts = this.transcriptSegmentStarts;
  if (!segEls || !segEls.length || !starts) return;
  // Binary search for the last segment whose start <= ms.
  let lo = 0, hi = starts.length - 1, idx = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (starts[mid] <= ms) { idx = mid; lo = mid + 1; }
    else hi = mid - 1;
  }
  if (idx === this.lastTranscriptIdx) return;
  if (this.lastTranscriptIdx >= 0 && segEls[this.lastTranscriptIdx]) {
    segEls[this.lastTranscriptIdx].classList.remove('current');
  }
  this.lastTranscriptIdx = idx;
  if (idx < 0) return;
  const cur = segEls[idx];
  if (!cur) return;
  cur.classList.add('current');
  // Auto-scroll the active segment into view, but only if it's not
  // already visible — otherwise the constant smooth-scroll fights the
  // user's manual scroll.
  const rect = cur.getBoundingClientRect();
  const parent = cur.parentElement && cur.parentElement.parentElement; // .aud-transcript
  if (!parent) return;
  const pRect = parent.getBoundingClientRect();
  if (rect.top < pRect.top + 40 || rect.bottom > pRect.bottom - 40) {
    cur.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }
};

AudibleView.prototype.renderChapters = function () {
  this.chaptersListEl.innerHTML = '';
  if (!this.currentChapters.length) {
    this.chaptersListEl.appendChild(el('div', { class: 'aud-list-empty', style: 'padding:14px 6px' },
      this.currentBook ? 'No chapter info.' : 'Pick a book to see chapters.'));
    return;
  }
  this.currentChapters.forEach((ch, idx) => {
    // Don't prefix our own ordinal number — Audible chapter titles
    // already start with the book's own numbering (e.g. "Chapter 4",
    // "Part II", "1. Opening Credits"), so adding our index would
    // produce "5. 4. Chapter 4" / "5. 1. Opening Credits".
    const item = el('div', {
      class: 'aud-chapter-item',
      'data-idx': idx,
      onclick: () => this.seekToChapter(idx),
    },
      el('div', null, ch.title || `Chapter ${idx + 1}`),
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
  const prevTranscriptState = this.audioStatus
    && this.audioStatus.transcript
    && this.audioStatus.transcript.state;
  this.audioStatus = status;
  this.renderAudioStatus();

  // If transcription is still in progress, keep the empty/progress
  // block in sync; if it just finished, fetch the new transcript.
  const txState = (status.transcript && status.transcript.state) || 'idle';
  const txJustFinished = prevTranscriptState && prevTranscriptState !== 'ready' && txState === 'ready';
  if (!this.currentTranscript || !(this.currentTranscript.segments || []).length) {
    if (txJustFinished) {
      try {
        const fresh = await this.fetchJson('/v1/audible/book/' + encodeURIComponent(asin) + '/transcript');
        if (asin === this.currentAsin && fresh) {
          this.currentTranscript = fresh;
          this.renderTranscript();
        }
      } catch (_) {}
    } else if (txState === 'transcribing' || txState === 'error') {
      // Re-render the transcript empty block with up-to-date progress.
      this.renderTranscript();
    }
  }

  if (status.playable) {
    // Don't enable the player until the blob has actually been fetched
    // and the audio element can play it. Otherwise the user clicks
    // Play, audio.src is still empty (the fetchBlob is in flight),
    // and togglePlay bails silently.
    this.enablePlayer(false);
    this.attachAudioStream().then((ok) => {
      if (asin !== this.currentAsin) return;
      this.enablePlayer(!!ok);
    });
    // Once audio is decoded locally we prefer to run transcription on
    // the user's machine rather than uploading the file to the AGiXT
    // voice server. The Tauri-only `audible_transcribe` command
    // streams progress via the `audible-transcription-progress` event.
    this.maybeStartLocalTranscription(status);
  } else {
    this.enablePlayer(false);
    if (this.totalDurationMs > 0) this.renderProgressFromVirtual();
  }

  // Keep polling whenever audio is downloading OR transcription is in
  // flight — the latter is the longer of the two for a real audiobook.
  const txInFlight = txState === 'transcribing';
  if (status.downloading || txInFlight) {
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
    // Don't render anything when audio is ready — the player chrome at
    // the bottom of the page is the primary affordance and a "Audio
    // ready" banner above it just adds visual chrome the user has to
    // skim past.
    this.statusBanner.hidden = true;
    return;
  }
  this.statusBanner.hidden = false;
  if (s.downloading) {
    this.statusBanner.classList.add('warn');
    this.statusBanner.appendChild(el('span', null, 'Downloading and decoding audio… this can take several minutes for a long book.'));
  } else if (s.encrypted_only) {
    // Download succeeded but ffmpeg couldn't decode it — usually a
    // missing-ffmpeg or activation_bytes issue. The specific reason
    // is in `last_error`; render it inline + a Retry button.
    this.statusBanner.classList.add('err');
    this.statusBanner.appendChild(el('span', null, 'Audio downloaded but could not be decoded for browser playback.'));
    const retryBtn = el('button', {
      type: 'button',
      onclick: async () => {
        retryBtn.disabled = true;
        retryBtn.textContent = 'Retrying…';
        await this.kickDownload();
        retryBtn.disabled = false;
        retryBtn.textContent = 'Retry';
      },
    }, 'Retry');
    this.statusBanner.appendChild(retryBtn);
    if (s.last_error) {
      this.statusBanner.appendChild(el('div', {
        style: 'flex-basis:100%;margin-top:6px;font-family:monospace;font-size:0.74rem;opacity:0.85;max-height:140px;overflow:auto;white-space:pre-wrap;word-break:break-word',
      }, s.last_error));
    }
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
      this.statusBanner.appendChild(el('div', {
        style: 'flex-basis:100%;margin-top:6px;font-family:monospace;font-size:0.74rem;opacity:0.85;max-height:140px;overflow:auto;white-space:pre-wrap;word-break:break-word',
      }, s.last_error));
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
  if (!this.audio || !this.currentAsin) return false;
  if (this.audioBlobAsin === this.currentAsin && this.audio.src) return true;
  // Browsers won't send Authorization headers on <audio src>, so we
  // pull the file as a blob and hand the player a blob: URL.
  // Returns true once the audio element has loaded enough metadata to
  // play; the caller awaits this before flipping the play button on.
  const asin = this.currentAsin;
  // Show a transient "Loading audio…" status while the blob downloads.
  // For a 5-hour book that's 100-200MB and several seconds even on a
  // fast connection — without this the user sees "Audio ready" and a
  // dead Play button.
  if (this.statusBanner) {
    this.statusBanner.className = 'aud-status-banner warn';
    this.statusBanner.innerHTML = '';
    this.statusBanner.appendChild(el('span', null, 'Loading audio into memory…'));
  }
  let blob;
  try {
    blob = await this.fetchBlob('/v1/audible/audio/' + encodeURIComponent(asin));
  } catch (err) {
    console.warn('audible: audio fetch failed', err);
    if (this.statusBanner && asin === this.currentAsin) {
      this.statusBanner.className = 'aud-status-banner err';
      this.statusBanner.innerHTML = '';
      this.statusBanner.appendChild(el('span', null, 'Failed to load audio: ' + (err.message || err)));
    }
    return false;
  }
  if (asin !== this.currentAsin) return false;
  if (this.audioObjectUrl) {
    try { URL.revokeObjectURL(this.audioObjectUrl); } catch (_) {}
    this.audioObjectUrl = null;
  }
  this.audioObjectUrl = URL.createObjectURL(blob);
  this.audioBlobAsin = asin;
  this.audio.src = this.audioObjectUrl;
  this.audio.load();

  // Wait for the audio element to either accept the source or fail it.
  // `loadedmetadata` (or `canplay`) fires once decode is in good shape;
  // `error` fires when the codec or bytes can't be played by the browser.
  return await new Promise((resolve) => {
    let settled = false;
    const cleanup = () => {
      this.audio.removeEventListener('loadedmetadata', onLoaded);
      this.audio.removeEventListener('canplay', onLoaded);
      this.audio.removeEventListener('error', onError);
    };
    const onLoaded = () => {
      if (settled) return;
      settled = true;
      cleanup();
      // Always set currentTime explicitly. If we don't, an audio
      // element re-used across book switches can carry over the
      // previous track's position, leaving the UI at 0:00 while audio
      // plays from the prior track's resume point.
      const seekSec = (this.lastPositionMs > 0) ? this.lastPositionMs / 1000 : 0;
      try { this.audio.currentTime = seekSec; } catch (_) {}
      // Update the visible time/progress from the seek target
      // immediately. The browser performs the seek asynchronously, so
      // the `seeked` listener will sync UI again when it lands, but
      // this avoids a window where the user sees "0:00" while audio is
      // actually positioned elsewhere.
      const durMs = (this.audio && isFinite(this.audio.duration))
        ? this.audio.duration * 1000
        : 0;
      if (this.curTimeEl) this.curTimeEl.textContent = fmtDuration(seekSec * 1000);
      if (this.totalTimeEl && durMs > 0) {
        this.totalTimeEl.textContent = fmtDuration(durMs);
      }
      if (this.progressFill && this.progressHandle && durMs > 0) {
        const pct = Math.max(0, Math.min(100, (seekSec * 1000 / durMs) * 100));
        this.progressFill.style.width = pct + '%';
        this.progressHandle.style.left = pct + '%';
      }
      // Hide the transient "Loading audio…" banner now that playback
      // is ready — the player chrome at the bottom is the canonical
      // ready-indicator. `renderAudioStatus` would do this on the next
      // status poll anyway; this just avoids the brief flash.
      if (this.statusBanner) {
        this.statusBanner.hidden = true;
        this.statusBanner.innerHTML = '';
      }
      resolve(true);
    };
    const onError = () => {
      if (settled) return;
      settled = true;
      cleanup();
      const code = (this.audio.error && this.audio.error.code) || 'unknown';
      const msg = (this.audio.error && this.audio.error.message) || '';
      if (this.statusBanner) {
        this.statusBanner.className = 'aud-status-banner err';
        this.statusBanner.innerHTML = '';
        this.statusBanner.appendChild(el('span', null,
          `Audio decode failed in browser (code ${code}). ${msg || 'The cached file may be corrupt or use an unsupported codec.'}`));
      }
      resolve(false);
    };
    this.audio.addEventListener('loadedmetadata', onLoaded);
    this.audio.addEventListener('canplay', onLoaded);
    this.audio.addEventListener('error', onError);
  });
};

AudibleView.prototype.enablePlayer = function (enabled) {
  this.playBtn.disabled = !enabled;
  this.skipBackBtn.disabled = !enabled;
  this.skipFwdBtn.disabled = !enabled;
  this.progressBar.classList.toggle('disabled', !enabled);
};

/* ===================================================================
 * Local transcription (whisper-rs via Tauri command). When running
 * inside the desktop client we'd rather run whisper on the user's CPU
 * than ship the whole audio file to a remote voice server. The web
 * fallback (server-side transcription) still kicks in automatically
 * when the page is opened in a regular browser.
 * =================================================================== */

AudibleView.prototype.tauriInvoke = function () {
  const t = window.__TAURI__;
  if (!t) return null;
  // Tauri 2 puts invoke at __TAURI__.core.invoke, but some builds
  // also re-export it at __TAURI__.invoke for v1 compat.
  if (t.core && typeof t.core.invoke === 'function') return t.core.invoke;
  if (typeof t.invoke === 'function') return t.invoke;
  return null;
};

AudibleView.prototype.tauriEventListen = function () {
  const t = window.__TAURI__;
  if (!t || !t.event || typeof t.event.listen !== 'function') return null;
  return t.event.listen;
};

AudibleView.prototype.resetTranscript = async function () {
  if (!this.currentAsin) return;
  const asin = this.currentAsin;
  const ok = window.confirm(
    'Discard this transcript and re-run transcription on the cached audio?'
  );
  if (!ok) return;
  let result;
  try {
    result = await this.fetchJson(
      '/v1/audible/book/' + encodeURIComponent(asin) + '/transcript',
      null,
      { method: 'DELETE' },
    );
  } catch (err) {
    console.warn('audible: transcript reset failed', err);
    return;
  }
  this.currentTranscript = null;
  this.localTranscribeAsin = null;
  if (this.audioStatus) {
    this.audioStatus.transcript = {
      state: 'transcribing',
      message: result && result.server_started
        ? 'Re-transcribing on the AGiXT voice server…'
        : 'Re-transcribing audio…',
      chunk_count: 100,
      chunks_done: 0,
    };
  }
  this.renderTranscript();
  // The DELETE endpoint kicks off server-side transcription itself
  // when an ezLocalai voice server is configured. In that case we just
  // poll the audio status until the transcript lands. Only when there
  // is no voice server (`server_started` false) do we fall back to
  // local whisper-rs running on the desktop client's CPU.
  if (result && result.server_started) {
    this.startStatusPoll();
  } else if (this.audioStatus && this.audioStatus.playable) {
    this.maybeStartLocalTranscription(this.audioStatus);
  } else {
    this.refreshAudioStatus();
  }
};

AudibleView.prototype.maybeStartLocalTranscription = function (status) {
  if (!this.currentAsin) return;
  const asin = this.currentAsin;
  const invoke = this.tauriInvoke();
  if (!invoke) return; // Browser context — let the server handle it.
  // Already have a transcript or an in-flight job — don't double-fire.
  if (this.currentTranscript && (this.currentTranscript.segments || []).length) return;
  if (this.localTranscribeAsin === asin) return;
  // If server-side transcription (ezLocalai on GPU) is already running
  // or scheduled, defer to it. The voice server is dramatically faster
  // than CPU-bound whisper-rs so there's no point racing it.
  const txState = (status && status.transcript && status.transcript.state) || 'idle';
  if (txState === 'transcribing') return;
  const playablePath = (status && status.playable_path) || '';
  if (!playablePath) return;
  // The Rust side polls `app_cache_dir()/whisper/...`; we need to
  // hand it the canonical absolute audio path the server already
  // resolved. Server returns `playable_path` for exactly this reason.
  this.localTranscribeAsin = asin;
  this.subscribeToTranscriptionEvents();
  invoke('audible_transcribe', {
    req: {
      asin,
      audio_path: playablePath,
      server_url: this.ctx.serverUrl,
      jwt: this.ctx.jwt,
      agent_id: this.ctx.agentId || null,
      // Default to small.en. base.en hallucinates fluent-but-wrong
      // text at chunk boundaries (we observed "League of Legends"
      // inserted into Art of War). small.en is ~3x slower on CPU but
      // mostly eliminates those boundary hallucinations and produces a
      // transcript actually usable for click-to-seek.
      model: 'small.en',
      language: 'en',
    },
  })
    .then((res) => {
      console.info('audible: local transcription completed', res);
    })
    .catch((err) => {
      console.warn('audible: local transcription failed', err);
      this.localTranscribeAsin = null;
      // Surface the error in the read-along section.
      if (!this.audioStatus) this.audioStatus = {};
      this.audioStatus.transcript = {
        state: 'error',
        error: String(err && err.message || err),
      };
      this.renderTranscript();
    });
};

AudibleView.prototype.subscribeToTranscriptionEvents = function () {
  if (this.transcriptionUnlisten) return;
  const listen = this.tauriEventListen();
  if (!listen) return;
  // Keep the listener even across book switches — the active asin
  // inside each event payload is what we filter on.
  listen('audible-transcription-progress', (ev) => {
    const payload = ev && ev.payload;
    if (!payload) return;
    if (payload.asin !== this.currentAsin) return;
    if (!this.audioStatus) this.audioStatus = {};
    this.audioStatus.transcript = {
      state: payload.state === 'ready' ? 'ready' : 'transcribing',
      message: payload.message,
      // Translate the 0..1 progress into the chunk_count/chunks_done
      // shape `buildTranscriptStatusBlock` already understands.
      chunk_count: 100,
      chunks_done: Math.round(Math.max(0, Math.min(1, payload.progress)) * 100),
    };
    if (payload.state === 'ready') {
      this.audioStatus.transcript.state = 'ready';
      // Pull the freshly uploaded transcript from the server.
      this.fetchJson('/v1/audible/book/' + encodeURIComponent(payload.asin) + '/transcript')
        .then((fresh) => {
          if (payload.asin !== this.currentAsin) return;
          this.currentTranscript = fresh;
          this.renderTranscript();
        })
        .catch(() => {});
    } else {
      this.renderTranscript();
    }
  })
    .then((unlisten) => { this.transcriptionUnlisten = unlisten; })
    .catch((err) => { console.warn('audible: cannot listen for events', err); });
};

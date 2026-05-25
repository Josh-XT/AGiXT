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
 *   GET/POST /v1/audible/book/{asin}/progress     — AGiXT reader resume point
 *   GET  /v1/audible/cover/{asin}                 — JWT-protected cover proxy
 *   GET  /v1/audible/audio/{asin}/status          — is audio cached?
 *   POST /v1/audible/audio/{asin}/download        — kick off cache download
 *   GET  /v1/audible/audio/{asin}                 — Range-streamed audio
 *
 * The extension manifest gates this view on `connection_check: ["audible"]`,
 * so it appears as soon as the user has a usable Audible auth blob for
 * their active agent. All routes carry `Authorization: Bearer <jwt>` and
 * the agent_id query param so the server picks the right credentials.
 */

// Bumped in lockstep with manifest.json — embedded into the
// diagnostic placeholder so we can tell from a screenshot whether
// the user is running the latest main.js or a cached older one.
const AUD_BUILD_TAG = '0.5.5';

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
const PROGRESS_SAVE_INTERVAL_MS = 10000;
const PROGRESS_SAVE_DELTA_MS = 10000;
const LOCAL_PROGRESS_SAVE_INTERVAL_MS = 1000;
const READ_ALONG_SYNC_OFFSET_MS = 0;

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
  this.user = null;
  this.companyId = (ctx && ctx.companyId) || null;
  this.roleId = null;
  this.scopes = new Set();
  this.children = [];
  this.xtschoolAudiobooks = [];
  this.xtschoolByAsin = new Map();
  this.childContextLoaded = false;
  this.progress = [];
  this.wishlist = [];
  this.currentAsin = readStr(LAST_BOOK_KEY, '') || null;
  this.currentBook = null;
  this.currentChapters = [];
  this.totalDurationMs = 0;
  this.lastPositionMs = 0;
  this.lastSavedPositionMs = 0;
  this.lastProgressSaveAt = 0;
  this.lastLocalProgressSaveAt = 0;
  this.pendingResumePositionMs = 0;
  this.resumeSeekApplied = false;
  this.xtschoolContentId = null;
  this.xtschoolCurrentItem = null;
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
  if (this.ctx && typeof this.ctx.registerContextProvider === 'function') {
    this.unregisterContextProvider = this.ctx.registerContextProvider(() => this.getContext());
  }
  this.xtschoolOpenHandler = (event) => {
    const detail = (event && event.detail) || {};
    const asin = String(detail.asin || '').trim();
    if (!asin) return;
    if (detail.item) {
      this.xtschoolByAsin.set(asin, detail.item);
      if (!this.xtschoolAudiobooks.some((item) => xtschoolContentId(item) === xtschoolContentId(detail.item))) {
        this.xtschoolAudiobooks.push(detail.item);
      }
    }
    this.loadLibrary().catch((err) => {
      console.warn('audible: failed to refresh approved library from xtschool event', err);
    });
    this.loadBook(asin).catch((err) => {
      console.warn('audible: failed to open xtschool audiobook', err);
    });
  };
  window.addEventListener('xtschool-open-audible', this.xtschoolOpenHandler);
  this.pageHideHandler = () => {
    this.writeCurrentLocalProgress({ force: true });
    this.persistProgress({ force: true }).catch(() => {});
  };
  window.addEventListener('pagehide', this.pageHideHandler);
  window.addEventListener('beforeunload', this.pageHideHandler);
  this.injectStyles();
  this.renderShell();
  this.bootstrapChildContext()
    .catch((err) => {
      console.warn('audible: child approval context failed', err);
    })
    .finally(() => {
      this.childContextLoaded = true;
      this.renderShell();
      // Server-side manifest gating (`connection_check: ["audible"]`)
      // means this page only loads when the auth file exists, so we go
      // straight to library + book restoration. If the file disappears
      // mid-session the per-call 401 handler surfaces the message.
      this.loadLibrary();
      if (this.currentAsin) this.loadBook(this.currentAsin, { silent: true });
    });
};

AudibleView.prototype.stop = function () {
  this.persistProgress({ force: true }).catch(() => {});
  if (this.xtschoolOpenHandler) {
    window.removeEventListener('xtschool-open-audible', this.xtschoolOpenHandler);
    this.xtschoolOpenHandler = null;
  }
  if (this.pageHideHandler) {
    window.removeEventListener('pagehide', this.pageHideHandler);
    window.removeEventListener('beforeunload', this.pageHideHandler);
    this.pageHideHandler = null;
  }
  if (typeof this.unregisterContextProvider === 'function') {
    try { this.unregisterContextProvider(); } catch (_) {}
    this.unregisterContextProvider = null;
  }
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
  const headers = Object.assign(
    { Authorization: 'Bearer ' + this.ctx.jwt },
    opts && opts.headers ? opts.headers : {},
  );
  const init = Object.assign(
    { method: 'GET' },
    opts || {},
    { headers },
  );
  const r = await fetch(url, init);
  if (r.status === 401) {
    // Per-feature 401 — we DO NOT route through the session handler from
    // here, because the audible extension's gate is per-agent and a kid
    // (whose own agent doesn't carry AUDIBLE_AUTH) shouldn't get logged
    // out of the whole app when an audible-scoped call comes back 401.
    // The /v1/user/* probes the host owns will tell it whether the JWT
    // is actually dead. All audible 401s — including the one we get when
    // the agent's Audible session goes stale — surface as inline errors
    // and the agent-settings drawer flips the tab back to "Not
    // connected" on its own.
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
    const e = new Error(`${r.status} ${r.statusText}: ${t.slice(0, 240)}`);
    e.status = 401;
    throw e;
  }
  if (r.status === 404) {
    const t = await r.text().catch(() => '');
    const e = new Error(t || 'not found');
    e.status = 404;
    throw e;
  }
  if (!r.ok) {
    const t = await r.text().catch(() => '');
    // Surface 402 / 5xx to the desktop session handler so billing/
    // server-issue overlays still trigger from this extension.
    if (window.AgixtSession && typeof window.AgixtSession.routeFailureStatus === 'function') {
      try { await window.AgixtSession.routeFailureStatus(r.status, t); } catch (_) {}
    }
    throw new Error(`${r.status} ${r.statusText}: ${t.slice(0, 240)}`);
  }
  return r.json();
};

AudibleView.prototype.fetchBlob = async function (path, params) {
  const url = this.apiUrl(path, params);
  const r = await fetch(url, { headers: { Authorization: 'Bearer ' + this.ctx.jwt } });
  if (!r.ok) {
    // Per-feature failure — DO NOT call routeFailureStatus on a plain 401
    // here. Cover-art and audio downloads are per-Audible-account; a kid
    // whose own agent doesn't carry AUDIBLE_AUTH will 401 on every
    // /v1/audible/cover and /v1/audible/audio call, and routing those
    // through the session handler used to log the kid out the moment the
    // library renderer reached the first cover. 5xx still goes to the
    // session handler so server outages still surface the right overlay.
    if (r.status >= 500
        && window.AgixtSession
        && typeof window.AgixtSession.routeFailureStatus === 'function') {
      try { await window.AgixtSession.routeFailureStatus(r.status, null); } catch (_) {}
    }
    const e = new Error(`${r.status} ${r.statusText}`);
    e.status = r.status;
    throw e;
  }
  return r.blob();
};

/* ---------- playback progress ------------------------------------------ */

function resumePositionMs(positionMs, durationMs, completed) {
  const position = Math.max(0, Math.round(Number(positionMs) || 0));
  const duration = Math.max(0, Math.round(Number(durationMs) || 0));
  if (completed || position <= 5000) return 0;
  if (duration > 0 && (position >= duration - 10000 || position / duration >= 0.95)) return 0;
  return position;
}

AudibleView.prototype.progressIdentity = function () {
  const user = this.user || {};
  return String(user.id || user.user_id || user.email || 'anon').replace(/[^A-Za-z0-9_.-]/g, '_');
};

AudibleView.prototype.localProgressKey = function (asin) {
  return 'agixt.desktop.audible.progress.v1.' + this.progressIdentity() + '.' + String(asin || '');
};

AudibleView.prototype.readLocalAudibleProgress = function (asin) {
  try {
    const raw = window.localStorage.getItem(this.localProgressKey(asin));
    return raw ? JSON.parse(raw) : null;
  } catch (_) {
    return null;
  }
};

AudibleView.prototype.writeLocalAudibleProgress = function (asin, payload) {
  try {
    window.localStorage.setItem(this.localProgressKey(asin), JSON.stringify(payload));
  } catch (_) {}
};

AudibleView.prototype.progressPositionMs = function (progress) {
  return Math.max(0, Math.round(Number(
    progress && (progress.last_position_ms || progress.position_ms || (Number(progress.progress_seconds || 0) * 1000))
  ) || 0));
};

AudibleView.prototype.writeCurrentLocalProgress = function (opts) {
  if (!this.currentAsin) return null;
  const force = !!(opts && opts.force);
  const now = Date.now();
  if (!force && now - this.lastLocalProgressSaveAt < LOCAL_PROGRESS_SAVE_INTERVAL_MS) {
    return null;
  }
  const positionMs = this.getCurrentPositionMs();
  const durationMs = this.currentDurationMs();
  if (positionMs <= 0 && !(opts && opts.completed)) return null;
  const payload = {
    asin: this.currentAsin,
    last_position_ms: positionMs,
    duration_ms: durationMs,
    completed: !!(opts && opts.completed),
    updated_at: new Date().toISOString(),
  };
  this.writeLocalAudibleProgress(this.currentAsin, payload);
  this.lastLocalProgressSaveAt = now;
  return payload;
};

AudibleView.prototype.currentDurationMs = function () {
  if (this.audio && isFinite(this.audio.duration) && this.audio.duration > 0) {
    return Math.round(this.audio.duration * 1000);
  }
  if (this.totalDurationMs > 0) return Math.round(this.totalDurationMs);
  if (this.currentBook && this.currentBook.runtime_minutes) {
    return Math.round(Number(this.currentBook.runtime_minutes) * 60000);
  }
  return 0;
};

AudibleView.prototype.loadSavedAudibleProgress = async function (asin) {
  const server = await this.fetchJson('/v1/audible/book/' + encodeURIComponent(asin) + '/progress')
    .catch(() => null);
  const local = this.readLocalAudibleProgress(asin);
  const serverMs = this.progressPositionMs(server);
  const localMs = this.progressPositionMs(local);
  return serverMs >= localMs ? server : local;
};

AudibleView.prototype.loadSavedXTSchoolProgress = async function (item) {
  if (!item) return null;
  const asin = asinFromXTSchoolItem(item);
  const local = asin ? this.readLocalAudibleProgress(asin) : null;
  if (!this.companyId) return local;
  const contentId = xtschoolContentId(item);
  if (!contentId) return local;
  const params = new URLSearchParams({
    company_id: this.companyId,
    content_id: contentId,
  });
  const data = await this.fetchJson('/v1/xtschool/progress?' + params.toString(), {})
    .catch(() => null);
  const items = Array.isArray(data && data.items) ? data.items : [];
  const server = items[0] || null;
  return this.progressPositionMs(local) > this.progressPositionMs(server) ? local : server;
};

AudibleView.prototype.scheduleProgressSave = function () {
  const now = Date.now();
  const positionMs = this.getCurrentPositionMs();
  if (now - this.lastProgressSaveAt < PROGRESS_SAVE_INTERVAL_MS
      && Math.abs(positionMs - this.lastSavedPositionMs) < PROGRESS_SAVE_DELTA_MS) {
    return;
  }
  this.persistProgress({ force: false }).catch(() => {});
};

AudibleView.prototype.persistProgress = async function (opts) {
  if (!this.currentAsin) return;
  const force = !!(opts && opts.force);
  const completed = !!(opts && opts.completed);
  const positionMs = this.getCurrentPositionMs();
  const durationMs = this.currentDurationMs();
  if (!completed && positionMs <= 0) return;
  const now = Date.now();
  if (!force
      && now - this.lastProgressSaveAt < PROGRESS_SAVE_INTERVAL_MS
      && Math.abs(positionMs - this.lastSavedPositionMs) < PROGRESS_SAVE_DELTA_MS) {
    return;
  }
  const payload = {
    asin: this.currentAsin,
    last_position_ms: positionMs,
    duration_ms: durationMs,
    completed,
    updated_at: new Date().toISOString(),
  };
  this.writeLocalAudibleProgress(this.currentAsin, payload);
  this.lastProgressSaveAt = now;
  this.lastSavedPositionMs = positionMs;

  if (this.isChildProfile() && this.companyId && this.xtschoolContentId) {
    await this.fetchJson('/v1/xtschool/progress', null, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        company_id: this.companyId,
        content_id: this.xtschoolContentId,
        content_type: 'audiobook',
        progress_seconds: Math.max(0, Math.round(positionMs / 1000)),
        duration_seconds: durationMs > 0 ? Math.max(0, Math.round(durationMs / 1000)) : null,
        completed,
        metadata: {
          asin: this.currentAsin,
          player: 'audible',
          updated_at: payload.updated_at,
        },
      }),
    }).catch((err) => {
      console.warn('audible: failed to save xtschool audiobook progress', err);
    });
    return;
  }

  await this.fetchJson('/v1/audible/book/' + encodeURIComponent(this.currentAsin) + '/progress', null, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      position_ms: positionMs,
      duration_ms: durationMs,
      completed,
    }),
  }).catch((err) => {
    console.warn('audible: failed to save audiobook progress', err);
  });
};

/* ---------- child approval context ----------------------------------- */

AudibleView.prototype.bootstrapChildContext = async function () {
  await this.loadUserContext();
  await this.loadChildControls();
  await this.loadXTSchoolAudiobooks();
};

AudibleView.prototype.loadUserContext = async function () {
  const user = await this.fetchJson('/v1/user').catch(() => null);
  this.user = user;
  const companies = Array.isArray(user && user.companies) ? user.companies : [];
  const company = companies.find((item) => item.id === this.companyId) || companies[0] || null;
  if (company) {
    this.companyId = company.id;
    this.roleId = company.role_id != null ? Number(company.role_id) : null;
    this.scopes = new Set(company.scopes || []);
  }
};

AudibleView.prototype.loadChildControls = async function () {
  if (!this.companyId) return;
  if (this.isChildProfile()) {
    const data = await this.fetchJson(
      '/v1/companies/' + encodeURIComponent(this.companyId) + '/child-controls/me'
    ).catch(() => null);
    this.children = (data && Array.isArray(data.children)) ? data.children : [];
    return;
  }
  if (!this.isManager()) return;
  const data = await this.fetchJson(
    '/v1/companies/' + encodeURIComponent(this.companyId) + '/child-controls'
  ).catch(() => null);
  this.children = (data && Array.isArray(data.children)) ? data.children : [];
};

AudibleView.prototype.loadXTSchoolAudiobooks = async function () {
  if (!this.companyId) return;
  const params = new URLSearchParams({
    company_id: this.companyId,
    content_type: 'audiobook',
  });
  if (this.isManager()) params.set('include_pending', 'true');
  const data = await this.fetchJson('/v1/xtschool/library?' + params.toString()).catch(() => null);
  const items = Array.isArray(data && data.items) ? data.items : [];
  this.xtschoolAudiobooks = items;
  this.xtschoolByAsin = new Map();
  for (const item of items) {
    const asin = asinFromXTSchoolItem(item);
    if (asin) this.xtschoolByAsin.set(asin, item);
  }
};

AudibleView.prototype.isChildProfile = function () {
  return !!(this.ctx && this.ctx.childMode) || this.roleId === 4;
};

AudibleView.prototype.isManager = function () {
  if (this.roleId === 0 || this.roleId === 1 || this.roleId === 2) return true;
  return this.hasScope('users:write') || this.hasScope('assets:write') || this.hasScope('ext:xtschool:write');
};

AudibleView.prototype.hasScope = function (scope) {
  if (this.scopes.has('*')) return true;
  if (this.scopes.has(scope)) return true;
  if (!scope.includes(':')) return false;
  const parts = scope.split(':');
  return this.scopes.has(parts[0] + ':*') || this.scopes.has(parts.slice(0, -1).join(':') + ':*');
};

AudibleView.prototype.hasChildProfiles = function () {
  return Array.isArray(this.children) && this.children.length > 0;
};

AudibleView.prototype.approvalForBook = function (book) {
  const asin = asinFromBook(book);
  return asin ? this.xtschoolByAsin.get(asin) || null : null;
};

AudibleView.prototype.bookIsApprovedForChildren = function (book) {
  const record = this.approvalForBook(book);
  return !!(record && record.approved);
};

AudibleView.prototype.approvedChildrenForBook = function (book) {
  const record = this.approvalForBook(book);
  const allowed = Array.isArray(record && record.allowed_child_user_ids)
    ? record.allowed_child_user_ids
    : [];
  if (!allowed.length) return this.children.map(childProfileId).filter(Boolean);
  return allowed;
};

AudibleView.prototype.bookToXTSchoolPayload = function (book, approved, allowedChildIds) {
  const asin = asinFromBook(book);
  const authors = Array.isArray(book.authors) ? book.authors.filter(Boolean) : [];
  const narrators = Array.isArray(book.narrators) ? book.narrators.filter(Boolean) : [];
  const title = book.title || asin || 'Audible audiobook';
  const chapters = Array.isArray(this.currentChapters)
    ? this.currentChapters.map((chapter, index) => ({
      index: Number.isFinite(Number(chapter.index)) ? Number(chapter.index) : index,
      title: chapter.title || `Chapter ${index + 1}`,
      start_ms: Math.max(0, Number(chapter.start_ms || 0)),
      length_ms: Math.max(0, Number(chapter.length_ms || 0)),
    }))
    : [];
  return {
    company_id: this.companyId,
    content_type: 'audiobook',
    title,
    subtitle: authors.length ? 'by ' + authors.join(', ') : 'Audible audiobook',
    description: book.description || book.publisher_summary || '',
    source: 'audible',
    source_id: asin,
    source_url: book.product_url || book.url || (asin ? 'https://www.audible.com/pd/' + encodeURIComponent(asin) : null),
    thumbnail_url: book.thumbnail_url || book.cover_url || book.image_url || null,
    duration_seconds: book.runtime_minutes ? Math.round(Number(book.runtime_minutes) * 60) : null,
    approved: !!approved,
    bedtime: false,
    allowed_child_user_ids: Array.isArray(allowedChildIds) ? allowedChildIds : [],
    metadata: {
      audible: {
        asin,
        authors,
        narrators,
        runtime_minutes: book.runtime_minutes || null,
        series_title: book.series_title || null,
        series_sequence: book.series_sequence || null,
        language: book.language || null,
        chapters,
        agent_id: this.ctx.agentId || null,
      },
      import: {
        provider: 'audible',
        kind: 'audiobook',
        asin,
        agent_id: this.ctx.agentId || null,
      },
    },
  };
};

AudibleView.prototype.setBookApproval = async function (book, approved, childIds) {
  if (!this.companyId || !this.isManager() || !this.hasChildProfiles()) return;
  const asin = asinFromBook(book);
  if (!asin) return;
  const selected = Array.isArray(childIds) ? childIds.filter(Boolean) : [];
  const storeForEveryone = selected.length === this.children.length;
  const allowed = storeForEveryone ? [] : selected;
  const current = this.approvalForBook(book);
  if (current && current.id) {
    await this.fetchJson('/v1/xtschool/library/' + encodeURIComponent(current.id), null, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.assign(
        this.bookToXTSchoolPayload(book, approved, allowed),
        { approved: !!approved, allowed_child_user_ids: allowed },
      )),
    });
  } else {
    await this.fetchJson('/v1/xtschool/library', null, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(this.bookToXTSchoolPayload(book, approved, allowed)),
    });
  }
  if (approved) {
    this.fetchJson('/v1/audible/audio/' + encodeURIComponent(asin) + '/download', null, {
      method: 'POST',
    }).then(() => {
      if (this.currentBook && asinFromBook(this.currentBook) === asin) {
        this.refreshAudioStatus();
      }
    }).catch((err) => {
      console.warn('audible: approved audiobook preparation failed to start', err);
    });
  }
  await this.loadXTSchoolAudiobooks();
  this.renderList();
  if (this.currentBook && asinFromBook(this.currentBook) === asin) this.renderDetail();
};

function asinFromBook(book) {
  return String((book && (book.asin || book.id || book.source_id)) || '').trim();
}

function childProfileId(child) {
  return String((child && (child.id || child.user_id)) || '').trim();
}

function xtschoolContentId(item) {
  return String((item && (item.id || item.content_id)) || '').trim();
}

function asinFromXTSchoolItem(item) {
  const meta = item && item.metadata;
  return String(
    (item && item.source_id)
    || (meta && meta.audible && meta.audible.asin)
    || (meta && meta.import && meta.import.asin)
    || ''
  ).trim();
}

function bookFromXTSchoolItem(item) {
  const meta = (item && item.metadata) || {};
  const audible = meta.audible || {};
  const asin = asinFromXTSchoolItem(item);
  return {
    asin,
    id: asin,
    title: (item && item.title) || audible.title || asin || 'Audible audiobook',
    authors: Array.isArray(audible.authors) ? audible.authors : [],
    narrators: Array.isArray(audible.narrators) ? audible.narrators : [],
    runtime_minutes: item && item.duration_seconds ? Math.round(Number(item.duration_seconds) / 60) : audible.runtime_minutes,
    description: (item && item.description) || audible.description || '',
    thumbnail_url: item && item.thumbnail_url,
    cover_url: item && item.thumbnail_url,
    source_url: item && item.source_url,
    language: audible.language || null,
    series_title: audible.series_title || null,
    series_sequence: audible.series_sequence || null,
    chapters: Array.isArray(audible.chapters) ? audible.chapters : [],
    xtschool_content_id: item && item.id,
    approved_for_child: !!(item && item.approved),
  };
}

function chaptersFromXTSchoolItem(item) {
  const meta = (item && item.metadata) || {};
  const audible = meta.audible || {};
  const chapters = Array.isArray(audible.chapters) ? audible.chapters : [];
  return normalizeChapterList(chapters);
}

function normalizeChapterList(chapters) {
  return chapters
    .map((chapter, idx) => ({
      index: chapter.index != null ? Number(chapter.index) : idx,
      title: chapter.title || `Chapter ${idx + 1}`,
      start_ms: Number(chapter.start_ms || chapter.start || 0),
      length_ms: Number(chapter.length_ms || chapter.duration_ms || 0),
    }))
    .filter((chapter) => Number.isFinite(chapter.start_ms) && Number.isFinite(chapter.length_ms));
}

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
.aud-child-state {
  margin-top: 5px;
  font-size: 0.7rem;
  color: var(--aud-text-muted);
}
.aud-child-state.approved { color: #7ee787; }
.aud-child-approval {
  margin-top: 14px;
  padding: 12px;
  border: 1px solid var(--aud-border);
  border-radius: 8px;
  background: var(--aud-surface-solid);
}
.aud-child-approval-title {
  font-size: 0.78rem;
  font-weight: 700;
  color: var(--aud-accent);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 8px;
}
.aud-child-picker {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.aud-child-picker label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--aud-border);
  border-radius: 999px;
  padding: 5px 9px;
  color: var(--aud-text-dim);
  font-size: 0.78rem;
}
.aud-child-picker input { accent-color: var(--aud-accent); }
.aud-child-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.aud-child-actions button {
  border: 1px solid var(--aud-border);
  border-radius: 6px;
  background: var(--aud-accent);
  color: var(--aud-on-accent);
  font-family: inherit;
  font-weight: 700;
  font-size: 0.8rem;
  padding: 7px 10px;
  cursor: pointer;
}
.aud-child-actions button.secondary {
  background: transparent;
  color: var(--aud-text-dim);
}
.aud-child-actions button:hover { filter: brightness(1.08); }

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
  font-size: 1.05rem;
  line-height: 1.75;
  color: var(--aud-text);
  max-width: 720px;
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
.aud-transcript-seg:hover { background: rgba(177, 186, 196, 0.08); color: var(--aud-text); }
.aud-transcript-seg.current {
  background: rgba(56, 139, 253, 0.22);
  color: #ffffff;
  font-weight: 500;
  box-shadow: 0 0 0 1px rgba(56, 139, 253, 0.4);
}
/* Inline chapter heading rendered above each chapter's segments —
 * matches the kids-app reader so the user gets navigable chapter
 * structure inside the transcript flow, not just in the sidebar. */
.aud-transcript-chapter-title {
  font-size: 0.85rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--aud-accent);
  margin: 2.2rem 0 1.1rem;
  text-indent: 0;
  padding-bottom: 0.55rem;
  border-bottom: 1px solid var(--aud-border-muted);
}
.aud-transcript-chapter-title:first-child { margin-top: 0; }
.aud-transcript-chapter-title.current {
  color: #ffffff;
  background: rgba(56, 139, 253, 0.18);
  border-bottom-color: rgba(56, 139, 253, 0.55);
  border-radius: 6px;
  padding: 0.55rem 0.75rem;
  margin-left: -0.75rem;
  margin-right: -0.75rem;
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
  headTitleRow.appendChild(el('div', { class: 'aud-sidebar-title' },
    this.isChildProfile() ? 'Approved Audiobooks' : 'Library'));
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

  if (this.isChildProfile()) {
    this.libraryTab = 'approved';
  } else {
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
  }

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
  this.audio.preload = 'metadata';
  this.audio.playbackRate = this.playbackRate;
  this.audio.volume = this.volume;

  this.audio.addEventListener('timeupdate', () => this.onTimeUpdate());
  // `seeked` fires once the browser finishes a seek. Programmatic
  // assignments to `audio.currentTime` are async (especially while
  // paused), so without this the UI can stay at 0:00 while audio is
  // actually positioned at `lastPositionMs` from the user's saved
  // Audible progress — pressing Play then plays from "later in the
  // book" while the visible time still reads 0:00.
  this.audio.addEventListener('seeked', () => {
    // Seek finished — currentTime is now authoritative again.
    this.pendingSeekSec = null;
    this.onTimeUpdate();
    this.persistProgress({ force: true }).catch(() => {});
  });
  this.audio.addEventListener('durationchange', () => this.onDurationChange());
  this.audio.addEventListener('loadedmetadata', () => this.onDurationChange());
  this.audio.addEventListener('play', () => {
    this.pendingSeekSec = null;
    this.setPlayIcon(true);
  });
  this.audio.addEventListener('pause', () => {
    this.setPlayIcon(false);
    this.persistProgress({ force: true }).catch(() => {});
  });
  this.audio.addEventListener('ended', () => {
    this.setPlayIcon(false);
    this.persistProgress({ force: true, completed: true }).catch(() => {});
  });

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

AudibleView.prototype.seekTo = function (seconds) {
  if (!this.audio) return;
  const numericSec = Number(seconds) || 0;
  const target = isFinite(this.audio.duration)
    ? Math.max(0, Math.min(this.audio.duration, numericSec))
    : Math.max(0, numericSec);
  this.pendingSeekSec = target;
  this.lastPositionMs = Math.max(0, Math.round(target * 1000));
  try { this.audio.currentTime = target; } catch (_) {}
  this.onTimeUpdate();
};

AudibleView.prototype.skip = function (deltaSec) {
  if (!this.audio || !isFinite(this.audio.duration)) return;
  this.seekTo(this.audio.currentTime + deltaSec);
};

AudibleView.prototype.onProgressClick = function (e) {
  if (this.progressBar.classList.contains('disabled')) return;
  const rect = this.progressBar.getBoundingClientRect();
  const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  if (this.audio && isFinite(this.audio.duration)) {
    this.seekTo(ratio * this.audio.duration);
  } else if (this.totalDurationMs > 0) {
    // No audio loaded but we have chapter info — store as virtual scrub
    this.lastPositionMs = ratio * this.totalDurationMs;
    this.renderProgressFromVirtual();
  }
};

AudibleView.prototype.getCurrentPositionMs = function () {
  if (this.pendingResumePositionMs > 0 && !this.resumeSeekApplied) {
    return Math.max(0, Math.round(Number(this.pendingResumePositionMs) || 0));
  }
  if (this.audio) {
    let seconds = Number(this.audio.currentTime) || 0;
    if (this.pendingSeekSec != null && this.audio.paused) {
      seconds = Number(this.pendingSeekSec) || seconds;
    }
    if (seconds > 0 || this.audio.src) return Math.max(0, Math.round(seconds * 1000));
  }
  return Math.max(0, Math.round(Number(this.lastPositionMs) || 0));
};

AudibleView.prototype.chapterForMs = function (ms) {
  if (!this.currentChapters || !this.currentChapters.length) return null;
  for (let i = 0; i < this.currentChapters.length; i++) {
    const ch = this.currentChapters[i];
    const start = Number(ch.start_ms) || 0;
    const end = start + (Number(ch.length_ms) || 0);
    if (ms >= start && (ms < end || i === this.currentChapters.length - 1)) {
      return Object.assign({ ordinal: i + 1 }, ch);
    }
  }
  return Object.assign({ ordinal: this.currentChapters.length }, this.currentChapters[this.currentChapters.length - 1]);
};

AudibleView.prototype.transcriptWindowForMs = function (ms) {
  const segs = (this.currentTranscript && this.currentTranscript.segments) || [];
  if (!segs.length) return '';
  let idx = -1;
  for (let i = 0; i < segs.length; i++) {
    const start = Number(segs[i].start) || 0;
    if (start <= ms) idx = i;
    else break;
  }
  if (idx < 0) idx = 0;
  const start = Math.max(0, idx - 4);
  const end = Math.min(segs.length, idx + 4);
  const text = segs.slice(start, end)
    .map((seg) => String(seg.text || '').trim())
    .filter(Boolean)
    .join(' ');
  return text.length > 1800 ? '…' + text.slice(-1800) : text;
};

AudibleView.prototype.getContext = function () {
  const lines = [
    'The user is on the Audible audiobook desktop page.',
    `Visible library tab: ${this.libraryTab || 'all'}`,
  ];
  if (this.libraryFilter) lines.push(`Library search filter: "${this.libraryFilter}"`);
  if (this.libraryLoaded && Array.isArray(this.library)) {
    lines.push(`Books visible in this tab before search filtering: ${this.library.length}`);
  }

  const b = this.currentBook;
  if (!b) {
    if (this.currentAsin) {
      lines.push(`A book is selected and still loading. ASIN: ${this.currentAsin}`);
    } else {
      lines.push('No audiobook is currently selected in the reader pane.');
    }
    return lines.join('\n');
  }

  const positionMs = this.getCurrentPositionMs();
  const totalMs = this.totalDurationMs
    || (this.audio && isFinite(this.audio.duration) ? Math.round(this.audio.duration * 1000) : 0)
    || (b.runtime_minutes ? b.runtime_minutes * 60 * 1000 : 0);
  const chapter = this.chapterForMs(positionMs);
  const transcriptWindow = this.transcriptWindowForMs(positionMs);
  const playerState = this.audio && this.audio.src
    ? (this.audio.paused ? 'paused' : 'playing')
    : (this.audioStatus && this.audioStatus.playable ? 'audio ready but not loaded' : 'audio not ready');

  lines.push(`Open audiobook: "${b.title || 'Untitled'}"`);
  if ((b.authors || []).length) lines.push(`Author(s): ${(b.authors || []).join(', ')}`);
  if ((b.narrators || []).length) lines.push(`Narrator(s): ${(b.narrators || []).join(', ')}`);
  if (b.series_title) {
    lines.push(`Series: ${b.series_title}${b.series_sequence ? `, book ${b.series_sequence}` : ''}`);
  }
  lines.push(`ASIN: ${b.asin || this.currentAsin || ''}`);
  if (typeof b.percent_complete === 'number') {
    lines.push(`Audible account progress: ${b.is_finished ? 'finished' : `${b.percent_complete.toFixed(1)}% complete`}`);
  }
  lines.push(`Current player state: ${playerState}`);
  lines.push(`Current position: ${fmtDuration(positionMs)}${totalMs ? ` of ${fmtDuration(totalMs)}` : ''}`);
  if (totalMs > 0) {
    lines.push(`Current local progress: ${Math.max(0, Math.min(100, (positionMs / totalMs) * 100)).toFixed(1)}%`);
  }
  if (chapter) {
    lines.push(`Current chapter: ${chapter.ordinal}. ${chapter.title || `Chapter ${chapter.ordinal}`} (${fmtDuration(chapter.start_ms || 0)} - ${fmtDuration((chapter.start_ms || 0) + (chapter.length_ms || 0))})`);
  }
  if (transcriptWindow) {
    lines.push('');
    lines.push('Transcript near the current listening position (most recent context is near the middle/end of this excerpt):');
    lines.push(transcriptWindow);
  } else if (this.currentTranscript && this.currentTranscript.status) {
    const status = this.currentTranscript.status;
    lines.push(`Transcript status: ${status.state || 'idle'}${status.message ? ` - ${status.message}` : ''}`);
  } else {
    lines.push('No transcript excerpt is available for the current position yet.');
  }
  lines.push('');
  lines.push('When the user asks about this audiobook, ground the answer in the title, ASIN, current chapter, player position, and transcript excerpt above. Use Audible extension commands for deeper book metadata, chapters, progress, or annotations when useful.');
  return lines.join('\n');
};

AudibleView.prototype.onTimeUpdate = function () {
  if (!this.audio) return;
  let cur = this.audio.currentTime || 0;
  // During stream attachment some browsers briefly report 0:00 before
  // the saved resume seek has been applied. Keep the restored target
  // sticky in that window so refresh cannot erase the child's place.
  if (this.pendingResumePositionMs > 0 && !this.resumeSeekApplied && cur < 1) {
    cur = this.pendingResumePositionMs / 1000;
  }
  // If we recently issued a seek and the browser hasn't applied it
  // to `currentTime` yet (WebKit on Linux is particularly unreliable
  // about seek-while-paused), trust our pending target so the UI
  // doesn't snap back to 0:00 while audio is queued to play from
  // somewhere else. Cleared on `seeked` or once audio starts playing.
  if (this.pendingSeekSec != null && this.audio.paused) {
    if (Math.abs(cur - this.pendingSeekSec) > 0.5) {
      cur = this.pendingSeekSec;
    }
  }
  const dur = isFinite(this.audio.duration) ? this.audio.duration : 0;
  this.curTimeEl.textContent = fmtDuration(cur * 1000);
  if (dur > 0) {
    const pct = Math.max(0, Math.min(100, (cur / dur) * 100));
    this.progressFill.style.width = pct + '%';
    this.progressHandle.style.left = pct + '%';
  }
  const ms = cur * 1000;
  this.lastPositionMs = Math.max(0, Math.round(ms));
  this.maybeMarkChapterFromTime(ms);
  this.highlightTranscriptAt(ms);
  this.writeCurrentLocalProgress();
  if (!this.pendingResumePositionMs || this.resumeSeekApplied) {
    this.scheduleProgressSave();
  }
};

AudibleView.prototype.onDurationChange = function () {
  const dur = isFinite(this.audio.duration) ? this.audio.duration : 0;
  this.totalTimeEl.textContent = fmtDuration(dur * 1000);
  if (dur > 0) this.totalDurationMs = Math.round(dur * 1000);
};

AudibleView.prototype.renderProgressFromVirtual = function () {
  if (!this.totalDurationMs) return;
  const pct = Math.max(0, Math.min(100, (this.lastPositionMs / this.totalDurationMs) * 100));
  this.progressFill.style.width = pct + '%';
  this.progressHandle.style.left = pct + '%';
  this.curTimeEl.textContent = fmtDuration(this.lastPositionMs);
  this.totalTimeEl.textContent = fmtDuration(this.totalDurationMs);
  this.maybeMarkChapterFromTime(this.lastPositionMs);
  this.persistProgress({ force: true }).catch(() => {});
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
    if (this.isChildProfile()) {
      await this.loadXTSchoolAudiobooks();
      items = this.xtschoolAudiobooks
        .filter((item) => item && item.approved)
        .map(bookFromXTSchoolItem)
        .filter((book) => book.asin);
      if (this.currentAsin && !items.some((book) => book.asin === this.currentAsin)) {
        this.currentAsin = null;
        writeStr(LAST_BOOK_KEY, '');
      }
    } else if (this.libraryTab === 'progress') {
      const r = await this.fetchJson('/v1/audible/progress');
      items = r.items || [];
    } else if (this.libraryTab === 'wishlist') {
      const r = await this.fetchJson('/v1/audible/wishlist');
      items = r.items || [];
    } else {
      const r = await this.fetchJson('/v1/audible/library', { limit: 1000 });
      items = r.items || [];
    }
    if (!this.isChildProfile() && this.hasChildProfiles()) {
      await this.loadXTSchoolAudiobooks();
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
      : (this.isChildProfile()
        ? 'No approved audiobooks yet.'
        : this.libraryTab === 'progress'
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
  this.attachCover(b.asin, cover, b);

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
  if (!this.isChildProfile() && this.hasChildProfiles()) {
    const approved = this.bookIsApprovedForChildren(b);
    meta.appendChild(el('div', { class: 'aud-child-state' + (approved ? ' approved' : '') },
      approved ? 'Approved for children' : 'Not approved for children'));
  }

  const card = el('div', {
    class: 'aud-card' + (this.currentAsin === b.asin ? ' active' : ''),
    onclick: () => this.loadBook(b.asin),
  }, cover, meta);
  return card;
};

AudibleView.prototype.attachCover = function (asin, imgEl, book) {
  if (!asin) return;
  const directUrl = book && (book.thumbnail_url || book.cover_url || book.image_url);
  if (directUrl) {
    imgEl.src = directUrl;
    return;
  }
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
  const approvedStoredBook = async () => {
    if (!this.xtschoolByAsin.size) await this.loadXTSchoolAudiobooks().catch(() => {});
    const item = this.xtschoolByAsin.get(String(asin));
    return item && item.approved ? item : null;
  };
  if (this.isChildProfile()) {
    if (!await approvedStoredBook()) {
      this.currentAsin = null;
      writeStr(LAST_BOOK_KEY, '');
      this.renderDetail({ error: 'This audiobook is not approved for this child profile.' });
      return;
    }
  }
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
  this.transcriptSegmentStarts = null;
  this.transcriptSegmentEnds = null;
  this.totalDurationMs = 0;
  this.lastPositionMs = 0;
  this.lastSavedPositionMs = 0;
  this.lastProgressSaveAt = 0;
  this.lastLocalProgressSaveAt = 0;
  this.pendingResumePositionMs = 0;
  this.resumeSeekApplied = false;
  this.xtschoolContentId = null;
  this.xtschoolCurrentItem = null;
  this.lastTranscriptIdx = -1;
  if (!wasSilent) this.renderDetail({ loading: true });
  this.renderChapters();
  this.renderList();

  try {
    if (this.isChildProfile()) {
      await this.loadApprovedBookFromXTSchool(asin);
      return;
    }
    const [details, chapters, transcript, savedProgress] = await Promise.all([
      this.fetchJson('/v1/audible/book/' + encodeURIComponent(asin)),
      this.fetchJson('/v1/audible/book/' + encodeURIComponent(asin) + '/chapters').catch(() => null),
      this.fetchJson('/v1/audible/book/' + encodeURIComponent(asin) + '/transcript').catch(() => null),
      this.loadSavedAudibleProgress(asin).catch(() => null),
    ]);
    this.currentBook = details;
    let sourcePositionMs = 0;
    if (chapters) {
      this.currentChapters = chapters.chapters || [];
      this.totalDurationMs = chapters.total_ms || 0;
      sourcePositionMs = chapters.last_position_ms || details.last_position_ms || 0;
    } else {
      sourcePositionMs = details.last_position_ms || 0;
    }
    const savedPositionMs = this.progressPositionMs(savedProgress);
    this.lastPositionMs = resumePositionMs(savedPositionMs, this.totalDurationMs, savedProgress && savedProgress.completed)
      || resumePositionMs(sourcePositionMs, this.totalDurationMs, false);
    this.lastSavedPositionMs = this.lastPositionMs;
    this.currentTranscript = transcript || null;
    this.renderDetail();
    this.renderChapters();
    this.refreshAudioStatus({ kickIfMissing: false });
  } catch (err) {
    if (err && err.code === 'audible_auth_required' && await approvedStoredBook()) {
      await this.loadApprovedBookFromXTSchool(asin);
      return;
    }
    this.renderDetail({ error: String(err.message || err) });
  }
};

AudibleView.prototype.loadApprovedBookFromXTSchool = async function (asin) {
  const item = this.xtschoolByAsin.get(String(asin));
  if (!item || !item.approved) {
    this.currentAsin = null;
    writeStr(LAST_BOOK_KEY, '');
    this.renderDetail({ error: 'This audiobook is not approved for this child profile.' });
    return;
  }
  const details = bookFromXTSchoolItem(item);
  this.xtschoolContentId = xtschoolContentId(item);
  this.xtschoolCurrentItem = item;
  let chapters = chaptersFromXTSchoolItem(item);
  if (!chapters.length && !this.isChildProfile()) {
    const cachedChapters = await this.fetchJson(
      '/v1/audible/book/' + encodeURIComponent(asin) + '/chapters'
    ).catch(() => null);
    chapters = normalizeChapterList((cachedChapters && cachedChapters.chapters) || []);
  }
  this.currentBook = details;
  this.currentChapters = chapters;
  this.totalDurationMs = chapters.reduce((max, chapter) => {
    const end = Number(chapter.start_ms || 0) + Number(chapter.length_ms || 0);
    return Math.max(max, end);
  }, details.runtime_minutes ? Number(details.runtime_minutes) * 60000 : 0);
  const savedProgress = await this.loadSavedXTSchoolProgress(item).catch(() => null);
  this.lastPositionMs = resumePositionMs(
    this.progressPositionMs(savedProgress),
    this.totalDurationMs,
    savedProgress && savedProgress.completed,
  );
  this.lastSavedPositionMs = this.lastPositionMs;
  this.currentTranscript = await this.fetchJson(
    '/v1/audible/book/' + encodeURIComponent(asin) + '/transcript'
  ).catch(() => null);
  this.renderDetail();
  this.renderChapters();
  this.refreshAudioStatus({ kickIfMissing: false });
};

AudibleView.prototype.renderChildApprovalControls = function (book) {
  if (this.isChildProfile() || !this.isManager() || !this.hasChildProfiles()) return null;
  const current = this.approvalForBook(book);
  const approved = !!(current && current.approved);
  const selected = new Set(this.approvedChildrenForBook(book));
  const picker = el('div', { class: 'aud-child-picker' });
  for (const child of this.children) {
    const childId = childProfileId(child);
    if (!childId) continue;
    const input = el('input', {
      type: 'checkbox',
      value: childId,
    });
    input.checked = selected.has(childId);
    picker.appendChild(el('label', null, input, child.name || child.email || 'Child'));
  }
  const selectedChildIds = () => {
    const ids = Array.from(picker.querySelectorAll('input[type="checkbox"]:checked'))
      .map((input) => input.value)
      .filter(Boolean);
    return ids.length ? ids : this.children.map(childProfileId).filter(Boolean);
  };
  const approve = el('button', {
    type: 'button',
    onclick: () => this.setBookApproval(book, true, selectedChildIds()).catch((err) => {
      this.renderDetail({ error: String(err.message || err) });
    }),
  }, approved ? 'Update approval' : 'Approve for children');
  const remove = el('button', {
    type: 'button',
    class: 'secondary',
    onclick: () => this.setBookApproval(book, false, selectedChildIds()).catch((err) => {
      this.renderDetail({ error: String(err.message || err) });
    }),
  }, 'Remove approval');
  const actions = el('div', { class: 'aud-child-actions' }, approve);
  if (approved) actions.appendChild(remove);
  const status = approved ? 'Approved for child profiles' : 'Not approved for child profiles';
  return el('div', { class: 'aud-child-approval' },
    el('div', { class: 'aud-child-approval-title' }, status),
    picker,
    actions,
  );
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
  this.attachCover(b.asin, cover, b);

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
  const childApproval = this.renderChildApprovalControls(b);
  if (childApproval) info.appendChild(childApproval);

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
  this.transcriptSegmentStarts = null;
  this.transcriptSegmentEnds = null;
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
  if (audioPlayable && txState !== 'transcribing' && !this.isChildProfile()) {
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
  const cueEls = [];
  const cueStarts = [];
  const cueEnds = [];

  // Build chapter ranges from `currentChapters` so we can insert an
  // inline chapter heading above each chapter's text, the same way the
  // kids reader does. Without this the transcript is one undifferen-
  // tiated wall and the user has no sense of where they are in the book.
  const chapters = (this.currentChapters || []).slice();
  const chapterRanges = chapters.map((ch, i) => {
    const start = Number(ch.start_ms || 0);
    const next = chapters[i + 1];
    const end = next
      ? Number(next.start_ms || 0)
      : (start + Number(ch.length_ms || 0)) || Number.MAX_SAFE_INTEGER;
    return { title: ch.title || `Chapter ${i + 1}`, start, end, idx: i };
  });
  const chapterTitleEls = new Array(chapterRanges.length);
  const findChapterIdx = (ms) => {
    for (let i = chapterRanges.length - 1; i >= 0; i--) {
      if (ms >= chapterRanges[i].start) return i;
    }
    return -1;
  };
  // Normalize text for fuzzy chapter-title equality so we can drop
  // segments that just repeat the chapter title (e.g. the narrator
  // says "Laying Plans" right after the chapter heading appears).
  const norm = (s) => String(s || '')
    .toLowerCase().replace(/[^a-z0-9 ]+/g, ' ').trim().replace(/\s+/g, ' ');
  const isTitleSegment = (segText, title) => {
    const a = norm(segText);
    const b = norm(title);
    if (!a || !b) return false;
    if (a === b) return true;
    // Common Audible pattern: "1. Laying Plans" or "Chapter 1 Laying Plans"
    if (a.endsWith(' ' + b) && a.length - b.length <= 6) return true;
    if (b.endsWith(' ' + a) && b.length - a.length <= 6) return true;
    return false;
  };
  const escapeRe = (s) => String(s || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const titleMatch = (segText, title) => {
    const words = String(title || '').trim().split(/\s+/).filter(Boolean);
    if (!words.length) return null;
    const pattern = words.map(escapeRe).join('\\s+');
    const re = new RegExp(`\\b${pattern}\\b[\\s:.,;\\-–—]*`, 'i');
    return re.exec(String(segText || ''));
  };
  const titleDurationMs = (title) => {
    const words = String(title || '').trim().split(/\s+/).filter(Boolean).length || 1;
    return Math.max(500, Math.min(3200, words * 520));
  };
  const timeAtTextOffset = (start, end, text, offset) => {
    const len = Math.max(1, String(text || '').length);
    const ratio = Math.max(0, Math.min(1, offset / len));
    return start + Math.max(0, end - start) * ratio;
  };
  const normalizeWordTime = (word, key, wordsAreSeconds) => {
    const value = Number(word && word[key]);
    if (!Number.isFinite(value)) return null;
    return wordsAreSeconds ? value * 1000 : value;
  };
  const wordsForRange = (seg, start, end) => {
    const source = Array.isArray(seg && seg.words) ? seg.words : [];
    if (!source.length) return [];
    const segEnd = Number(seg.end || end || 0);
    const maxWordTime = source.reduce((max, word) => Math.max(
      max,
      Number(word && word.start) || 0,
      Number(word && word.end) || 0,
    ), 0);
    // Newer transcripts are normalized to milliseconds by the Rust API.
    // Some older/local OpenAI-compatible servers return seconds, so accept
    // both shapes to keep cached transcripts readable after upgrades.
    const wordsAreSeconds = segEnd > 1000 && maxWordTime > 0 && maxWordTime <= (segEnd / 1000) + 120;
    return source.map((word) => {
      const rawText = word && (word.word || word.text || word.token);
      const text = String(rawText || '').trim();
      const wordStart = normalizeWordTime(word, 'start', wordsAreSeconds);
      const wordEndRaw = normalizeWordTime(word, 'end', wordsAreSeconds);
      if (!text || wordStart === null) return null;
      const wordEnd = Number.isFinite(wordEndRaw) && wordEndRaw >= wordStart
        ? wordEndRaw
        : wordStart + Math.max(140, text.replace(/[^A-Za-z0-9]+/g, '').length * 45);
      return { text, start: wordStart, end: wordEnd };
    }).filter((word) => {
      if (!word) return false;
      const midpoint = (word.start + word.end) / 2;
      return midpoint >= Number(start) - 160 && midpoint <= Number(end) + 160;
    });
  };
  const capitalizeFirstAlpha = (s) => String(s || '').replace(/^(\s*)([a-z])/, (m, ws, ch) => ws + ch.toUpperCase());
  const estimateSpokenMs = (tokens) => {
    let total = 0;
    for (const token of tokens) {
      const spoken = String(token).replace(/[^A-Za-z0-9]+/g, '');
      if (!spoken) {
        total += 80;
      } else {
        total += 210 + spoken.length * 38;
      }
    }
    return Math.max(tokens.length * 240, total);
  };
  const splitTimedTokens = (text, start, end, opts) => {
    const tokens = String(text || '').match(/\S+\s*/g) || [];
    if (!tokens.length) return [];
    const safeStart = Number.isFinite(Number(start)) ? Number(start) : 0;
    const safeEnd = Number.isFinite(Number(end)) && Number(end) > safeStart
      ? Number(end)
      : safeStart + tokens.length * 360;
    const availableMs = Math.max(1, safeEnd - safeStart);
    const sentenceEnds = /[.!?]["')\]]?\s*$/.test(String(text || '').trim());
    const requestedLead = Math.max(0, Number((opts && opts.leadingPauseMs) || 0));
    const leadMs = Math.min(requestedLead, availableMs * 0.45);
    const trailingPauseMs = sentenceEnds
      ? Math.min(900, Math.max(220, availableMs * 0.12))
      : Math.min(300, availableMs * 0.04);
    const estimatedMs = estimateSpokenMs(tokens);
    const stretchedMs = Math.max(tokens.length * 220, availableMs - leadMs - trailingPauseMs);
    const spokenMs = Math.max(tokens.length * 180, Math.min(availableMs - leadMs, Math.max(estimatedMs, stretchedMs)));
    const cueStartBase = safeStart + leadMs;
    const cueEndBase = Math.min(safeEnd, cueStartBase + spokenMs);
    const weights = tokens.map((token) => {
      const spoken = String(token).replace(/[^A-Za-z0-9]+/g, '');
      return Math.max(1, spoken.length);
    });
    const total = weights.reduce((sum, weight) => sum + weight, 0) || tokens.length;
    let cursor = 0;
    return tokens.map((token, idx) => {
      const tokenStart = cueStartBase + (cueEndBase - cueStartBase) * (cursor / total);
      cursor += weights[idx];
      const tokenEnd = cueStartBase + (cueEndBase - cueStartBase) * (cursor / total);
      return { text: token, start: tokenStart, end: tokenEnd };
    });
  };
  const tokensFromText = (text) => String(text || '').match(/\S+\s*/g) || [];
  const timedTokensForPiece = (piece, leadingPauseMs) => {
    const tokens = tokensFromText(piece.text);
    const words = Array.isArray(piece.words) ? piece.words : [];
    if (tokens.length && words.length) {
      const sorted = words
        .filter((word) => Number.isFinite(Number(word.start)))
        .sort((a, b) => Number(a.start) - Number(b.start));
      if (sorted.length) {
        const closeEnough = Math.abs(sorted.length - tokens.length)
          <= Math.max(2, Math.ceil(tokens.length * 0.15));
        const useTranscriptText = closeEnough;
        const count = useTranscriptText
          ? Math.min(tokens.length, sorted.length)
          : sorted.length;
        const cues = [];
        for (let idx = 0; idx < count; idx++) {
          const word = sorted[idx];
          const text = useTranscriptText
            ? tokens[idx]
            : `${String(word.text || '').trim()} `;
          if (!text.trim()) continue;
          const start = Math.max(Number(piece.start), Number(word.start));
          let end = Number(word.end);
          if (!Number.isFinite(end) || end <= start) {
            const spoken = text.replace(/[^A-Za-z0-9]+/g, '');
            end = start + Math.max(140, spoken.length * 45);
          }
          cues.push({
            text,
            start,
            end: Math.min(Number(piece.end) || end, Math.max(end, start + 80)),
          });
        }
        if (cues.length) return cues;
      }
    }
    return splitTimedTokens(piece.text, piece.start, piece.end, { leadingPauseMs });
  };

  // Paragraph grouping rules — see commit history; whisper segments
  // don't reliably terminate at sentence boundaries.
  const PARAGRAPH_SOFT_BREAK_CHARS = 360;
  const PARAGRAPH_HARD_BREAK_CHARS = 700;
  const PARAGRAPH_MAX_BREAK_CHARS = 2200;
  const SENTENCE_END_RE = /[.!?]["')\]]?$/;
  const WEAK_BREAK_RE = /[,;:][\s"')\]]*$|[—–-]\s*$/;
  const STARTS_CONTINUATION_RE =
    /^(of|and|or|but|to|in|on|at|from|with|by|for|as|that|which|who|where|when|while|because|if|then|than)\b|^[a-z]/;

  let para = el('p', { class: 'aud-transcript-para' });
  let charCount = 0;
  let lastChapterIdx = -2;
  const flushPara = () => {
    if (para.childNodes.length) {
      body.appendChild(para);
      para = el('p', { class: 'aud-transcript-para' });
      charCount = 0;
    }
  };

  const pieces = [];
  segs.forEach((seg, i) => {
    let text = (seg.text || '').trim();
    if (!text) return;
    const segStart = Number(seg.start) || 0;
    const segEnd = Number(seg.end || segStart) || segStart;
    let pieceStart = segStart;
    let cIdx = findChapterIdx(segStart);
    let startsChapterBody = false;

    // If a Whisper segment straddles a chapter boundary, it often
    // contains the next chapter title in the middle of the text. Split
    // at that spoken title so "Dedication..." doesn't render inside
    // "Opening Credits", and strip the duplicate title because the UI
    // already renders it as a chapter heading.
    while (cIdx + 1 < chapterRanges.length) {
      const nextTitle = chapterRanges[cIdx + 1].title;
      const match = titleMatch(text, nextTitle);
      if (!match) break;
      const before = text.slice(0, match.index).trim();
      const chapterStart = chapterRanges[cIdx + 1].start;
      const beforeEnd = chapterStart > pieceStart && chapterStart < segEnd
        ? chapterStart
        : timeAtTextOffset(pieceStart, segEnd, text, match.index);
      if (before) {
        pieces.push({
          seg,
          index: i,
          text: before,
          start: pieceStart,
          end: beforeEnd,
          chapterIdx: cIdx,
          words: wordsForRange(seg, pieceStart, beforeEnd),
        });
      }
      text = text.slice(match.index + match[0].length).trim();
      cIdx += 1;
      pieceStart = Math.min(segEnd, beforeEnd + titleDurationMs(nextTitle));
      startsChapterBody = true;
      if (!text) break;
    }
    if (!text) return;

    // Also strip the current chapter title when a segment starts with
    // it and then continues into the actual body text, e.g.
    // "Notes on this book. This is...".
    if (cIdx >= 0) {
      const match = titleMatch(text, chapterRanges[cIdx].title);
      if (match && match.index <= 4) {
        const strippedEnd = timeAtTextOffset(pieceStart, segEnd, text, match.index)
          + titleDurationMs(chapterRanges[cIdx].title);
        text = text.slice(match.index + match[0].length).trim();
        pieceStart = Math.min(segEnd, Math.max(pieceStart, strippedEnd));
        startsChapterBody = true;
      }
    }
    if (startsChapterBody) text = capitalizeFirstAlpha(text);
    if (!text) {
      pieces.push({
        seg,
        index: i,
        text: '',
        start: pieceStart,
        end: segEnd,
        chapterIdx: cIdx,
        words: [],
        titleOnly: true,
      });
      return;
    }
    pieces.push({
      seg,
      index: i,
      text,
      start: pieceStart,
      end: segEnd,
      chapterIdx: cIdx,
      words: wordsForRange(seg, pieceStart, segEnd),
    });
  });

  for (let i = 2; i < pieces.length; i++) {
    const a = pieces[i - 2];
    const b = pieces[i - 1];
    const c = pieces[i];
    const sameChapter = a.chapterIdx === b.chapterIdx && b.chapterIdx === c.chapterIdx;
    const aContinues = a.text && !SENTENCE_END_RE.test(a.text);
    const bComplete = b.text && SENTENCE_END_RE.test(b.text);
    const cContinues = c.text && STARTS_CONTINUATION_RE.test(c.text);
    const overlaps = b.start < a.end && c.start <= a.end + 1500;
    if (sameChapter && aContinues && bComplete && cContinues && overlaps) {
      pieces[i - 1] = c;
      pieces[i] = b;
    }
  }

  let previousVisiblePiece = null;
  pieces.forEach((piece) => {
    const text = piece.text;
    const i = piece.index;
    const cIdx = piece.chapterIdx;
    if (cIdx >= 0 && cIdx !== lastChapterIdx) {
      flushPara();
      const titleEl = el('h2', {
        class: 'aud-transcript-chapter-title',
        'data-chapter': cIdx,
        onclick: () => this.seekToChapter(cIdx),
        style: 'cursor:pointer',
      }, chapterRanges[cIdx].title);
      chapterTitleEls[cIdx] = titleEl;
      body.appendChild(titleEl);
      lastChapterIdx = cIdx;
    }
    // Skip segments that just repeat the chapter title — the heading
    // already shows it. Timing starts after the spoken title, so the
    // read-along highlight tracks the first body word instead of lighting
    // up an entire Whisper phrase.
    const skipForTitle = cIdx >= 0
      && (piece.titleOnly || isTitleSegment(text, chapterRanges[cIdx].title));
    if (skipForTitle) {
      return;
    }

    const gapFromPrevious = previousVisiblePiece
      ? Number(piece.start) - Number(previousVisiblePiece.end)
      : Number.POSITIVE_INFINITY;
    const previousEndedSentence = previousVisiblePiece
      && SENTENCE_END_RE.test(previousVisiblePiece.text || '');
    const duration = Math.max(0, Number(piece.end) - Number(piece.start));
    const leadingPauseMs = previousEndedSentence && gapFromPrevious < 800
      ? Math.min(3200, Math.max(650, duration * 0.3))
      : 0;

    for (const cue of timedTokensForPiece(piece, leadingPauseMs)) {
      const span = el('span', {
        class: 'aud-transcript-seg aud-transcript-word',
        'data-idx': i,
        onclick: () => {
          const startSec = cue.start / 1000;
          if (this.audio && this.audio.src && isFinite(this.audio.duration)) {
            this.seekTo(startSec);
          } else {
            this.lastPositionMs = cue.start;
            this.renderProgressFromVirtual();
          }
        },
      }, cue.text);
      cueEls.push(span);
      cueStarts.push(cue.start);
      cueEnds.push(cue.end);
      para.appendChild(span);
    }
    previousVisiblePiece = piece;
    charCount += text.length + 1;

    const endsSentence = SENTENCE_END_RE.test(text);
    const endsWeakly = WEAK_BREAK_RE.test(text);
    const shouldBreak =
      (endsSentence && charCount >= PARAGRAPH_SOFT_BREAK_CHARS)
      || (charCount >= PARAGRAPH_HARD_BREAK_CHARS && (endsSentence || endsWeakly))
      || charCount >= PARAGRAPH_MAX_BREAK_CHARS;
    if (shouldBreak) flushPara();
  });
  flushPara();

  const cueTimeline = cueEls
    .map((node, idx) => ({ node, start: cueStarts[idx], end: cueEnds[idx] }))
    .filter((cue) => cue.node && Number.isFinite(Number(cue.start)))
    .sort((a, b) => a.start - b.start);
  this.transcriptSegEls = cueTimeline.map((cue) => cue.node);
  this.transcriptSegmentStarts = cueTimeline.map((cue) => cue.start);
  this.transcriptSegmentEnds = cueTimeline.map((cue) => cue.end);
  this.transcriptChapterTitleEls = chapterTitleEls;
  this.transcriptChapterRanges = chapterRanges;
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

AudibleView.prototype.highlightTranscriptAt = function (ms, opts) {
  const playbackMs = Math.max(0, Number(ms) - READ_ALONG_SYNC_OFFSET_MS);
  const segEls = this.transcriptSegEls;
  const starts = this.transcriptSegmentStarts;
  const ends = this.transcriptSegmentEnds;
  if (!segEls || !segEls.length || !starts) return;
  const clearCurrent = () => {
    if (this.lastTranscriptIdx >= 0 && segEls[this.lastTranscriptIdx]) {
      segEls[this.lastTranscriptIdx].classList.remove('current');
    }
    if (this.detailEl) {
      this.detailEl
        .querySelectorAll('.aud-transcript-word.current')
        .forEach((node) => node.classList.remove('current'));
    }
    this.lastTranscriptIdx = -1;
  };
  // Binary search for the last segment whose start <= ms.
  let lo = 0, hi = starts.length - 1, idx = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (starts[mid] <= playbackMs) { idx = mid; lo = mid + 1; }
    else hi = mid - 1;
  }
  const force = !!(opts && opts.forceScroll);
  // Highlight the current chapter heading too so the user can see at
  // a glance which chapter the audio is in.
  const ranges = this.transcriptChapterRanges || [];
  const titleEls = this.transcriptChapterTitleEls || [];
  let curChIdx = -1;
  for (let i = ranges.length - 1; i >= 0; i--) {
    if (playbackMs >= ranges[i].start) { curChIdx = i; break; }
  }
  if (this.lastChapterTitleIdx !== curChIdx) {
    if (this.lastChapterTitleIdx >= 0 && titleEls[this.lastChapterTitleIdx]) {
      titleEls[this.lastChapterTitleIdx].classList.remove('current');
    }
    if (curChIdx >= 0 && titleEls[curChIdx]) {
      titleEls[curChIdx].classList.add('current');
    }
    this.lastChapterTitleIdx = curChIdx;
  }

  if (idx < 0 || (ends && Number.isFinite(Number(ends[idx])) && playbackMs > Number(ends[idx]) + 120)) {
    clearCurrent();
    return;
  }
  if (idx === this.lastTranscriptIdx && !force) {
    const active = this.detailEl
      ? Array.from(this.detailEl.querySelectorAll('.aud-transcript-word.current'))
      : [];
    if (active.length === 1 && active[0] === segEls[idx]) return;
  }
  clearCurrent();
  this.lastTranscriptIdx = idx;
  const cur = segEls[idx];
  if (!cur) return;
  cur.classList.add('current');
  this.scrollTranscriptInto(cur, force);
};

AudibleView.prototype.scrollTranscriptInto = function (target, force) {
  if (!target || !this.detailEl) return;
  // Hidden title-segment spans live inside the chapter heading and
  // have zero layout — scroll the heading instead.
  const visible = (target.offsetParent === null && target.parentElement)
    ? target.parentElement
    : target;
  const cRect = visible.getBoundingClientRect();
  const dRect = this.detailEl.getBoundingClientRect();
  const inView =
    cRect.top >= dRect.top + 40
    && cRect.bottom <= dRect.bottom - 40;
  if (force || !inView) {
    // Compute the offset within `.aud-detail` and animate the scroll
    // ourselves rather than calling `scrollIntoView`. The latter walks
    // up to the nearest scrolling ancestor, which on some Tauri layouts
    // ends up being the window — that scrolls the whole page instead
    // of the transcript pane.
    const offset = cRect.top - dRect.top + this.detailEl.scrollTop
      - (dRect.height / 2 - cRect.height / 2);
    this.detailEl.scrollTo({
      top: Math.max(0, offset),
      behavior: force ? 'auto' : 'smooth',
    });
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
  const startMs = ch.start_ms || 0;
  if (this.audio && this.audio.src && isFinite(this.audio.duration)) {
    this.seekTo(startMs / 1000);
  } else {
    this.lastPositionMs = startMs;
    this.renderProgressFromVirtual();
  }
  // Force-scroll the transcript to the chapter — the seek above will
  // re-highlight on `seeked`/`timeupdate`, but if the user clicks the
  // same chapter twice (or the highlighted segment is already in
  // view) `highlightTranscriptAt`'s built-in "already-visible" guard
  // suppresses the scroll. A chapter click is an explicit jump
  // request from the user; honor it unconditionally.
  this.highlightTranscriptAt(startMs, { forceScroll: true });
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
    // The media route supports authenticated byte-range streaming, so
    // enable playback as soon as the stream URL is attached. The audio
    // element can then buffer only what it needs instead of waiting for
    // a full-book client download.
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

  if (opts && opts.kickIfMissing && !this.isChildProfile() && !status.playable && !status.downloading) {
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
  const transcript = s.transcript || {};
  this.statusBanner.innerHTML = '';
  this.statusBanner.classList.remove('ok', 'warn', 'err');
  if (transcript.state === 'transcribing') {
    const total = transcript.chunk_count || 0;
    const done = transcript.chunks_done || 0;
    const pct = total ? Math.max(0, Math.min(100, Math.round((done / total) * 100))) : 0;
    this.statusBanner.hidden = false;
    this.statusBanner.classList.add('warn');
    this.statusBanner.appendChild(el('span', null,
      transcript.message || `Transcribing chunk ${done} of ${total}…`));
    this.statusBanner.appendChild(el('div', {
      class: 'aud-transcript-progress',
      style: 'flex-basis:100%;margin-top:8px',
    }, el('div', {
      class: 'aud-transcript-progress-fill',
      style: `width:${pct}%`,
    })));
    return;
  }
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
    this.statusBanner.appendChild(el('span', null, this.isChildProfile()
      ? 'This audiobook is approved and is still being prepared. Playback will appear here when it finishes.'
      : 'Downloading and decoding audio… this can take several minutes for a long book.'));
  } else if (s.encrypted_only) {
    // Download succeeded but ffmpeg couldn't decode it — usually a
    // missing-ffmpeg or activation_bytes issue. The specific reason
    // is in `last_error`; render it inline + a Retry button.
    this.statusBanner.classList.add('err');
    this.statusBanner.appendChild(el('span', null, this.isChildProfile()
      ? 'This approved audiobook is not playable yet. A parent needs to reconnect Audible or retry preparation from their account.'
      : 'Audio downloaded but could not be decoded for browser playback.'));
    if (!this.isChildProfile()) {
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
    }
    if (s.last_error) {
      this.statusBanner.appendChild(el('div', {
        style: 'flex-basis:100%;margin-top:6px;font-family:monospace;font-size:0.74rem;opacity:0.85;max-height:140px;overflow:auto;white-space:pre-wrap;word-break:break-word',
      }, s.last_error));
    }
  } else {
    this.statusBanner.appendChild(el('span', null,
      this.isChildProfile()
        ? 'This audiobook is approved, but the stored audio is not ready yet. Playback will appear after the parent-side preparation finishes.'
        : s.last_error
        ? 'Audio not cached. Last download attempt failed.'
        : 'Audio is not cached locally. Download to enable playback.'));
    if (!this.isChildProfile()) {
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
    }
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
  if (this.isChildProfile()) return;
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
  // Browsers won't send Authorization headers on <audio src>. The API
  // accepts the same JWT as a query token on this media route so the
  // browser can stream with byte-range requests instead of downloading
  // the whole audiobook before Play becomes available.
  const asin = this.currentAsin;
  const transcriptInFlight = this.audioStatus
    && this.audioStatus.transcript
    && this.audioStatus.transcript.state === 'transcribing';
  if (this.statusBanner && !transcriptInFlight) {
    this.statusBanner.className = 'aud-status-banner warn';
    this.statusBanner.innerHTML = '';
    this.statusBanner.appendChild(el('span', null, 'Preparing audio stream…'));
  }
  if (asin !== this.currentAsin) return false;
  const resumeTargetMs = Math.max(0, Math.round(Number(this.lastPositionMs) || 0));
  this.pendingResumePositionMs = resumeTargetMs;
  this.resumeSeekApplied = resumeTargetMs <= 0;
  if (this.audioObjectUrl) {
    try { URL.revokeObjectURL(this.audioObjectUrl); } catch (_) {}
    this.audioObjectUrl = null;
  }
  this.audioBlobAsin = asin;
  this.audio.src = this.apiUrl('/v1/audible/audio/' + encodeURIComponent(asin), {
    token: this.ctx.jwt,
  });
  const hidePreparingBanner = () => {
    if (this.statusBanner && !(this.audioStatus
        && this.audioStatus.transcript
        && this.audioStatus.transcript.state === 'transcribing')) {
      this.statusBanner.hidden = true;
      this.statusBanner.innerHTML = '';
    }
  };
  const onLoaded = () => {
    this.audio.removeEventListener('loadedmetadata', onLoaded);
    this.audio.removeEventListener('canplay', onLoaded);
    const seekMs = this.pendingResumePositionMs > 0
      ? this.pendingResumePositionMs
      : this.lastPositionMs;
    const seekSec = (seekMs > 0) ? seekMs / 1000 : 0;
    this.resumeSeekApplied = true;
    this.pendingResumePositionMs = 0;
    this.seekTo(seekSec);
    const durMs = (this.audio && isFinite(this.audio.duration))
      ? this.audio.duration * 1000
      : 0;
    if (this.totalTimeEl && durMs > 0) this.totalTimeEl.textContent = fmtDuration(durMs);
    hidePreparingBanner();
  };
  const onError = () => {
    this.audio.removeEventListener('error', onError);
    const code = (this.audio.error && this.audio.error.code) || 'unknown';
    const msg = (this.audio.error && this.audio.error.message) || '';
    if (this.statusBanner) {
      this.statusBanner.className = 'aud-status-banner err';
      this.statusBanner.innerHTML = '';
      this.statusBanner.appendChild(el('span', null,
        `Audio decode failed in browser (code ${code}). ${msg || 'The cached file may be corrupt or use an unsupported codec.'}`));
    }
  };
  this.audio.addEventListener('loadedmetadata', onLoaded);
  this.audio.addEventListener('canplay', onLoaded);
  this.audio.addEventListener('error', onError);
  this.audio.load();
  hidePreparingBanner();
  return true;
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
  if (this.isChildProfile()) return;
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

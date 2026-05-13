/* Deployable Agents — desktop port of /bots.
 *
 * Endpoints:
 *   GET    /v1/bots/platforms                                    list available platforms
 *   GET    /v1/company/{company_id}/bots                         per-platform status
 *   GET    /v1/company/{company_id}/deployed-bots                deployed bots for company
 *   GET    /v1/user/deployed-bots                                deployed bots across all my companies
 *   POST   /v1/company/{company_id}/bots/{platform}/enable       enable / configure
 *   POST   /v1/company/{company_id}/bots/{platform}/pause        pause / unpause
 *   POST   /v1/company/{company_id}/bots/{platform}/restart      restart
 *   DELETE /v1/company/{company_id}/bots/{platform}              undeploy
 *
 * Configuration of new bots requires per-platform credentials and OAuth
 * flows. The desktop extension lists deployed bots and supports
 * pause/resume/restart/delete in-place; "Configure" opens the web UI
 * page for the full settings form.
 */
ensureFormModalB();

window.AgixtRegisterExtension('bots', {
  mount(container, ctx) {
    const v = new BotsView(container, ctx);
    container._botsView = v;
    v.start();
  },
  unmount() {
    const root = document.querySelector('.chat-screen-main .view-pane[data-view="bots"]');
    if (root && root._botsView) { root._botsView.stop(); root._botsView = null; }
  },
});

const BOT_COLS = [
  { id: 'platform', label: 'Platform',  sortable: true,  width: '160px' },
  { id: 'instance', label: 'Instance',  sortable: true,  width: 'minmax(160px, 1fr)' },
  { id: 'company',  label: 'Company',   sortable: true,  width: 'minmax(140px, 1fr)' },
  { id: 'agent',    label: 'Agent',     sortable: true,  width: '140px' },
  { id: 'status',   label: 'Status',    sortable: true,  width: '110px' },
  { id: 'msgs',     label: 'Messages',  sortable: true,  width: '100px' },
  { id: 'started',  label: 'Started',   sortable: true,  width: '120px' },
  { id: 'actions',  label: '',          sortable: false, width: '220px' },
];

function BotsView(container, ctx) {
  this.container = container; this.ctx = ctx;
  this.deployedBots = []; this.platforms = []; this.permissionModes = [];
  this.companies = []; this.agents = [];
  this.userScopes = new Set(); this.roleId = null;
  // Full provider objects from /v1/oauth (name, client_id, authorize,
  // scopes…) — used to feed AgentSettingsConnections.startConnect.
  this.oauthProviders = [];
  // Plain list of connected provider names from /v1/oauth2, e.g.
  // ["discord", "google"]. Compared case-insensitively to a platform's
  // oauth_provider slug.
  this.connectedProviderNames = [];
  this.search = '';
  this.scope = readJsonB('agixt.desktop.bots.scope.v1', 'company'); // 'company' | 'server'
  this.statusFilter = readJsonB('agixt.desktop.bots.status.v1', 'all');
  this.sort = readJsonB('agixt.desktop.bots.sort.v1', { id: 'platform', dir: 'asc' });
  this.pollTimer = null;
}

BotsView.prototype.isServerAdmin = function () {
  if (this.roleId === 0) return true;
  return this.userScopes.has('*') || this.userScopes.has('*:*')
    || this.userScopes.has('server:bots') || this.userScopes.has('server:admin');
};
BotsView.prototype.canUseScope = function (scope) {
  if (scope === 'company') return true;
  if (scope === 'server') return this.isServerAdmin();
  return false;
};
BotsView.prototype.hasOAuthConnection = function (platform) {
  if (!platform || !platform.uses_oauth) return true;
  const want = String(platform.oauth_provider || '').toLowerCase();
  if (!want) return true;
  return (this.connectedProviderNames || []).some((n) =>
    String(n || '').toLowerCase() === want);
};
BotsView.prototype.findOAuthProvider = function (platform) {
  const want = String(platform && platform.oauth_provider || '').toLowerCase();
  if (!want) return null;
  return (this.oauthProviders || []).find((p) =>
    String(p && p.name || '').toLowerCase() === want) || null;
};

BotsView.prototype.start = function () {
  this.injectStyles();
  this.render();
  this.bootstrap();
  this.onVis = () => { if (document.hidden) this.cancelPoll(); else { this.refresh(); this.scheduleNext(); } };
  document.addEventListener('visibilitychange', this.onVis);
  // Refresh OAuth connection state after the desktop receives a
  // successful provider callback. AgentSettingsConnections fires this
  // through Tauri's event bus, but listening on window also works
  // because user-settings re-broadcasts it. We just re-load and re-
  // render the platforms list.
  this.onConnected = () => {
    this.loadOAuthConnections().then(() => this.renderPlatforms()).catch(() => {});
  };
  window.addEventListener('agixt-extension-connected', this.onConnected);
};
BotsView.prototype.stop = function () {
  this.cancelPoll();
  if (this.onVis) document.removeEventListener('visibilitychange', this.onVis);
  if (this.onConnected) window.removeEventListener('agixt-extension-connected', this.onConnected);
  this.container.innerHTML = '';
};

BotsView.prototype.fetchJson = async function (path, opts) {
  opts = opts || {};
  if (this.ctx && typeof this.ctx.fetchJson === 'function') {
    return this.ctx.fetchJson(path, opts);
  }
  if (window.AgixtSession && typeof window.AgixtSession.request === 'function') {
    return window.AgixtSession.request(path, opts);
  }
  const u = new URL(path, this.ctx.serverUrl).toString();
  const init = {
    method: opts.method || 'GET',
    headers: Object.assign({ Authorization: 'Bearer ' + this.ctx.jwt },
      (opts.json != null) ? { 'Content-Type': 'application/json' } : {}),
  };
  if (opts.json != null) init.body = JSON.stringify(opts.json);
  const resp = await fetch(u, init);
  if (resp.status === 204) return null;
  const text = await resp.text();
  let data = null; try { data = text ? JSON.parse(text) : null; } catch (_) {}
  if (!resp.ok) { const err = new Error((data && data.detail) || ('HTTP ' + resp.status)); err.status = resp.status; throw err; }
  return data;
};

BotsView.prototype.bootstrap = async function () {
  await Promise.all([
    this.loadPlatforms(),
    this.loadCompanies(),
    this.loadAgents(),
    this.loadUserAndScopes(),
    this.loadOAuthConnections(),
  ]);
  // Force scope back to company if the user lost server admin since the
  // last session — keeps the tab strip from showing an unselectable scope.
  if (this.scope === 'server' && !this.canUseScope('server')) {
    this.scope = 'company';
    writeJsonB('agixt.desktop.bots.scope.v1', this.scope);
  }
  this.renderHeader();
  await this.refresh();
  this.scheduleNext();
};

BotsView.prototype.loadUserAndScopes = async function () {
  try {
    const u = await this.fetchJson('/v1/user');
    const co = (u.companies || []).find((c) => c.id === this.ctx.companyId) || (u.companies || [])[0];
    if (co) {
      this.userScopes = new Set(co.scopes || []);
      this.roleId = co.role_id != null ? co.role_id : null;
    }
  } catch (_) { /* leave defaults */ }
};

BotsView.prototype.loadOAuthConnections = async function () {
  // Two endpoints with complementary jobs:
  //   /v1/oauth   → list of available providers + their authorize URLs,
  //                 client ids, and scope sets. Needed to *start* a
  //                 connect flow via AgentSettingsConnections.startConnect.
  //   /v1/oauth2  → list of provider name strings the *current user* is
  //                 already connected to (e.g. ["discord", "google"]).
  // Both calls are best-effort so a misconfigured server still lets the
  // platforms list render.
  try {
    if (window.AgixtApi && typeof window.AgixtApi.getOAuthProviders === 'function') {
      const providers = await window.AgixtApi.getOAuthProviders();
      this.oauthProviders = Array.isArray(providers) ? providers : [];
    } else {
      const data = await this.fetchJson('/v1/oauth');
      this.oauthProviders = (data && (data.providers || data)) || [];
    }
  } catch (_) { this.oauthProviders = []; }
  try {
    if (window.AgixtApi && typeof window.AgixtApi.getUserOAuthConnections === 'function') {
      const conns = await window.AgixtApi.getUserOAuthConnections();
      this.connectedProviderNames = Array.isArray(conns) ? conns
        : (conns && Array.isArray(conns.providers)) ? conns.providers
        : [];
    } else {
      const data = await this.fetchJson('/v1/oauth2');
      this.connectedProviderNames = Array.isArray(data) ? data
        : (data && Array.isArray(data.providers)) ? data.providers
        : [];
    }
  } catch (_) { this.connectedProviderNames = []; }
};

// Opens the OAuth connect flow for the platform's provider. Prefers the
// existing AgentSettingsConnections helper because it knows how to call
// the Rust `build_oauth_connect_url` command, open the system browser,
// and react to the deep-link callback. Falls back to opening user
// settings so the user has somewhere to go even when the helper isn't
// loaded yet (e.g. before user-settings.js has mounted).
BotsView.prototype.openConnectionSettings = function (platform) {
  const provider = this.findOAuthProvider(platform);
  if (provider
      && window.AgentSettingsConnections
      && typeof window.AgentSettingsConnections.startConnect === 'function') {
    try { window.AgentSettingsConnections.startConnect(provider); return; }
    catch (_) { /* fall through to settings nav */ }
  }
  if (window.AgixtSidenav && typeof window.AgixtSidenav.setActiveView === 'function') {
    window.AgixtSidenav.setActiveView('user-settings');
  }
};

BotsView.prototype.loadPlatforms = async function () {
  try {
    const data = await this.fetchJson('/v1/bots/platforms');
    this.platforms = (data && data.platforms) || [];
    this.permissionModes = (data && data.permission_modes) || [];
    this.platformNameById = {};
    for (const p of this.platforms) this.platformNameById[p.id] = p.name;
  } catch (_) {}
};
BotsView.prototype.loadCompanies = async function () {
  try {
    const data = await this.fetchJson('/v1/companies');
    const list = Array.isArray(data) ? data : (data && data.companies) || [];
    this.companies = list;
  } catch (_) {}
};
BotsView.prototype.loadAgents = async function () {
  try {
    const data = await this.fetchJson('/v1/agent');
    this.agents = (data && data.agents) || [];
  } catch (_) {}
};
BotsView.prototype.loadBotSettings = async function (companyId, platform, instanceId, scope) {
  // Server bots have no dedicated settings GET; the desktop edits flow
  // is a fresh re-enable. Surface that with a null return so the caller
  // doesn't pre-fill stale values into the modal.
  if (scope === 'server') return null;
  try {
    const path = '/v1/company/' + encodeURIComponent(companyId) + '/bots/' + encodeURIComponent(platform)
      + '/settings?instance_id=' + encodeURIComponent(instanceId || 'default');
    return await this.fetchJson(path);
  } catch (_) { return null; }
};

BotsView.prototype.scheduleNext = function () {
  this.cancelPoll();
  if (document.hidden) return;
  this.pollTimer = window.setTimeout(() => this.refresh().finally(() => this.scheduleNext()), 30_000);
};
BotsView.prototype.cancelPoll = function () {
  if (this.pollTimer) { window.clearTimeout(this.pollTimer); this.pollTimer = null; }
};

BotsView.prototype.refresh = async function () {
  try {
    // Scope decides which endpoint to read. The server endpoint is super-
    // admin gated; we already enforce scope availability in canUseScope,
    // so an unauthorized call here would be a programming error in the
    // tab strip handler.
    const path = this.scope === 'server'
      ? '/v1/server/deployed-bots'
      : '/v1/user/deployed-bots';
    const data = await this.fetchJson(path);
    const rows = (data && data.bots) || [];
    // Tag each bot with the scope it came from so per-row actions route
    // to the right endpoint regardless of what the current tab is when
    // the user clicks.
    this.deployedBots = rows.map((b) => Object.assign({}, b, { _scope: this.scope }));
    this.renderError(null);
    this.renderHeader();
    this.renderTable();
  } catch (err) { this.renderError(err); }
};

// Builds the right pause/restart/enable/delete path for a deployed bot
// based on the scope it was loaded from. Server bots don't accept a
// company id or instance id (super-admin only, single-instance per
// platform), so the route shape is different.
BotsView.prototype._botBasePath = function (b) {
  const scope = (b && b._scope) || this.scope;
  if (scope === 'server') {
    return '/v1/server/bots/' + encodeURIComponent(b.platform);
  }
  return '/v1/company/' + encodeURIComponent(b.company_id) + '/bots/' + encodeURIComponent(b.platform);
};
BotsView.prototype._botQuery = function (b) {
  if ((b && b._scope) === 'server') return '';
  return '?instance_id=' + encodeURIComponent(b.instance_id || 'default');
};

BotsView.prototype.pauseBot = async function (b) {
  const next = !b.is_paused;
  try {
    await this.fetchJson(this._botBasePath(b) + '/pause' + this._botQuery(b),
      { method: 'POST', json: { paused: next } });
    await this.refresh();
  } catch (err) { this.renderError(err); }
};

BotsView.prototype.restartBot = async function (b) {
  if ((b && b._scope) === 'server') {
    // The server bot endpoint set doesn't expose restart (enable/pause/
    // delete only). Surface that instead of silently 404'ing.
    this.renderError(new Error('Server-scope bots do not support restart from desktop yet. Use pause/resume or delete + re-enable.'));
    return;
  }
  if (!window.confirm('Restart ' + b.platform_name + ' bot for ' + b.company_name + '?')) return;
  try {
    await this.fetchJson(this._botBasePath(b) + '/restart' + this._botQuery(b),
      { method: 'POST' });
    await this.refresh();
  } catch (err) { this.renderError(err); }
};

BotsView.prototype.deleteBot = async function (b) {
  const where = (b && b._scope) === 'server'
    ? 'server-wide'
    : 'for ' + (b.company_name || 'this company');
  if (!window.confirm('Undeploy ' + b.platform_name + ' bot ' + where + '?\nThis stops the bot and removes its configuration.')) return;
  try {
    await this.fetchJson(this._botBasePath(b) + this._botQuery(b),
      { method: 'DELETE' });
    await this.refresh();
  } catch (err) { this.renderError(err); }
};

BotsView.prototype.openDeploy = async function () {
  if (!this.platforms.length) { this.renderError(new Error('No platforms available — try refreshing.')); return; }
  const deployScope = this.scope === 'server' && this.canUseScope('server') ? 'server' : 'company';
  const platformOpts = this.platforms.map((p) => ({ value: p.id, label: p.name + (p.uses_oauth ? ' (OAuth)' : '') }));
  const companyOpts = (this.companies.length ? this.companies : [{ id: this.ctx.companyId || '', name: 'Active company' }])
    .map((c) => ({ value: c.id || '', label: c.name || c.id || 'Active company' }));

  // Server bots have no company id and only one instance per platform —
  // hide the company picker and instance name in that mode so the form
  // doesn't lie about what's being collected.
  const fields = [
    { key: 'platform', label: 'Platform', type: 'select', options: platformOpts, value: platformOpts[0].value, required: true },
  ];
  if (deployScope === 'company') {
    fields.push({ key: 'company_id', label: 'Deploy in company', type: 'select', options: companyOpts, value: this.ctx.companyId || companyOpts[0].value, required: true });
    fields.push({ key: 'instance_name', label: 'Instance name (optional)', type: 'text', placeholder: 'Friendly label, e.g. "support" — keep blank for the default instance.' });
  }

  const pick = await window.AgixtFormModal.show({
    title: deployScope === 'server' ? 'Deploy server bot' : 'Deploy agent',
    description: deployScope === 'server'
      ? 'Server bots run server-wide on a single configuration. After picking a platform you will configure its credentials.'
      : 'Pick a platform to deploy to. After choosing, you can configure its credentials and settings.',
    fields,
    submitLabel: 'Continue →',
  });
  if (!pick) return;
  const platform = this.platforms.find((p) => p.id === pick.platform);
  if (!platform) return;
  const companyId = deployScope === 'company' ? pick.company_id : '';
  const instanceName = deployScope === 'company' ? (pick.instance_name || null) : null;
  await this._configureBot(platform, companyId, 'new', instanceName, undefined, undefined, deployScope);
};

BotsView.prototype.openConfigure = async function (b) {
  const platform = this.platforms.find((p) => p.id === b.platform);
  if (!platform) { this.renderError(new Error('Unknown platform: ' + b.platform)); return; }
  const scope = (b && b._scope) || 'company';
  const settings = await this.loadBotSettings(b.company_id, b.platform, b.instance_id || 'default', scope);
  await this._configureBot(platform, b.company_id, b.instance_id || 'default', b.instance_name || null,
    (settings && settings.settings) || {}, b, scope);
};

BotsView.prototype._configureBot = async function (platform, companyId, instanceId, instanceName, existing, existingBot, scopeOverride) {
  existing = existing || {};
  const scope = scopeOverride || (existingBot && existingBot._scope) || this.scope || 'company';
  const required = platform.required_settings || [];
  const optional = platform.optional_settings || [];
  const fields = [];

  // Agent picker.
  const agentOpts = [{ value: '', label: '— No specific agent (use ' + (scope === 'server' ? 'server' : 'company') + ' default) —' }]
    .concat(this.agents.map((a) => ({ value: a.id, label: a.name })));
  fields.push({
    key: '__agent_id', label: 'Agent', type: 'select', options: agentOpts,
    value: (existingBot && existingBot.agent_id) || '',
    help: 'Which agent should handle messages from this bot?',
  });

  // Permission mode.
  if (this.permissionModes && this.permissionModes.length) {
    const opts = this.permissionModes.map((m) => ({ value: m.value, label: m.label + (m.description ? ' — ' + m.description : '') }));
    fields.push({
      key: '__permission_mode', label: 'Permission mode', type: 'select', options: opts,
      value: (existingBot && existingBot.permission_mode) || opts[0].value,
    });
  }

  // Instance name — only meaningful for company scope (server bots are
  // single-instance per platform).
  if (scope === 'company') {
    fields.push({
      key: '__instance_name', label: 'Instance name', type: 'text',
      value: instanceName || (existingBot && existingBot.instance_name) || '',
      placeholder: 'Optional — friendly label for this bot deployment',
    });
  }

  // OAuth status — we can't run the OAuth handshake from inside the
  // modal, but we can detect whether the connection already exists and
  // surface a clear "Connect provider" CTA if it doesn't.
  const hasOAuth = this.hasOAuthConnection(platform);
  if (platform.uses_oauth) {
    if (!hasOAuth) {
      // Bail out of the modal up front — saving settings without a
      // connection just produces a runtime error later. Offer to open
      // the connections settings instead.
      const provider = platform.oauth_provider_display || platform.oauth_provider || 'OAuth';
      const ok = window.confirm(
        platform.name + ' uses ' + provider + ' OAuth, but no connection is configured for this account yet.\n\n'
        + 'Open the connections settings to authorize ' + provider + ' first?'
      );
      if (ok) this.openConnectionSettings(platform);
      return;
    }
    fields.push({
      key: '__oauth_note', label: 'OAuth provider', type: 'text',
      value: (platform.oauth_provider_display || platform.oauth_provider || '') + ' — connected',
      help: 'OAuth connection detected. Reconnect from User Settings → Connections if anything looks off.',
    });
  }

  // Required settings.
  for (const key of required) {
    fields.push({
      key: key, label: humanizeKey(key), type: looksLikeSecretKey(key) ? 'password' : 'text',
      value: existing[key] || '', required: true,
    });
  }
  // Optional settings.
  for (const key of optional) {
    if (required.indexOf(key) >= 0) continue;
    fields.push({
      key: key, label: humanizeKey(key) + ' (optional)', type: looksLikeSecretKey(key) ? 'password' : 'text',
      value: existing[key] || '',
    });
  }

  const title = existingBot ? ('Configure ' + platform.name) : ('Deploy ' + platform.name);
  const desc = existingBot
    ? 'Update settings for this ' + platform.name + ' bot. Saving immediately enables it.'
    : 'Configure ' + platform.name + ' before it can start processing messages.';
  const values = await window.AgixtFormModal.show({
    title: title,
    description: desc + (platform.setup_url ? ' Setup guide: ' + platform.setup_url : ''),
    fields: fields,
    submitLabel: existingBot ? 'Save & enable' : 'Deploy',
  });
  if (!values) return;

  const settings = {};
  for (const key of Object.keys(values)) {
    if (key.startsWith('__')) continue;
    if (values[key] != null) settings[key] = String(values[key]);
  }

  try {
    const isServer = scope === 'server';
    const path = isServer
      ? '/v1/server/bots/' + encodeURIComponent(platform.id) + '/enable'
      : '/v1/company/' + encodeURIComponent(companyId) + '/bots/' + encodeURIComponent(platform.id) + '/enable';
    const body = {
      enabled: true,
      settings: settings,
      agent_id: values.__agent_id || null,
      permission_mode: values.__permission_mode || null,
    };
    // Company endpoints accept an instance_id; server endpoints don't.
    if (!isServer) body.instance_id = instanceId || 'new';
    await this.fetchJson(path, { method: 'POST', json: body });
    // Make sure the next refresh picks up the freshly-enabled bot
    // regardless of which tab the user is on. We always re-fetch the
    // current scope's view; the user can switch tabs to see the
    // newly-deployed server bot if they were on Company.
    await this.refresh();
  } catch (err) { this.renderError(err); }
};

function humanizeKey(k) {
  return String(k || '').replace(/[_\-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
function looksLikeSecretKey(k) {
  return /token|secret|key|password|api_key/i.test(String(k || ''));
}

/* --- predicates --- */
BotsView.prototype.statusBucket = function (b) {
  if (b.status === 'error' || b.error) return 'error';
  if (b.status === 'paused' || b.is_paused) return 'paused';
  if (b.status === 'running' || b.is_running) return 'running';
  return 'offline';
};

BotsView.prototype.filteredAndSorted = function () {
  const q = (this.search || '').trim().toLowerCase();
  const sf = this.statusFilter;
  const out = this.deployedBots.filter((b) => {
    if (sf !== 'all' && this.statusBucket(b) !== sf) return false;
    if (!q) return true;
    const hay = [b.platform, b.platform_name, b.company_name, b.agent_name, b.instance_name, b.instance_id].join(' ').toLowerCase();
    return hay.includes(q);
  });
  out.sort((a, b) => this.compare(a, b, this.sort.id, this.sort.dir));
  return out;
};
BotsView.prototype.compare = function (a, b, col, dir) {
  const sign = dir === 'desc' ? -1 : 1;
  const va = this.sortKey(a, col); const vb = this.sortKey(b, col);
  if (va == null && vb == null) return 0;
  if (va == null) return 1;
  if (vb == null) return -1;
  if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * sign;
  return String(va).localeCompare(String(vb), undefined, { sensitivity: 'base' }) * sign;
};
BotsView.prototype.sortKey = function (b, col) {
  switch (col) {
    case 'platform': return (b.platform_name || b.platform || '').toLowerCase();
    case 'instance': return (b.instance_name || b.instance_id || '').toLowerCase();
    case 'company':  return (b.company_name || '').toLowerCase();
    case 'agent':    return (b.agent_name || '').toLowerCase();
    case 'status':   return this.statusBucket(b);
    case 'msgs':     return Number(b.messages_processed) || 0;
    case 'started':  return Date.parse(b.started_at) || 0;
    default: return '';
  }
};

/* --- DOM --- */
BotsView.prototype.render = function () {
  this.container.innerHTML = '';
  const root = document.createElement('div'); root.className = 'bt-root';
  this.headerEl = document.createElement('div'); this.headerEl.className = 'bt-header'; root.appendChild(this.headerEl);
  this.errEl = document.createElement('div'); this.errEl.className = 'bt-error'; this.errEl.hidden = true; root.appendChild(this.errEl);
  this.statsEl = document.createElement('div'); this.statsEl.className = 'bt-stats'; root.appendChild(this.statsEl);
  this.tableEl = document.createElement('div'); this.tableEl.className = 'bt-table-wrap'; root.appendChild(this.tableEl);
  this.platformsEl = document.createElement('div'); this.platformsEl.className = 'bt-platforms'; root.appendChild(this.platformsEl);
  this.container.appendChild(root);
  this.renderHeader(); this.renderStats(); this.renderTable(); this.renderPlatforms();
};

BotsView.prototype.renderHeader = function () {
  if (!this.headerEl) return;
  if (!this._tools) this._buildTools();
  const counts = { all: this.deployedBots.length, running: 0, paused: 0, offline: 0, error: 0 };
  for (const b of this.deployedBots) counts[this.statusBucket(b)] += 1;

  this.headerEl.innerHTML = '';
  if (this.ctx && this.ctx.framed && typeof this.ctx.setHeaderActions === 'function') {
    if (!this._toolbarMounted) {
      this.ctx.setHeaderActions(this._tools.search, this._tools.refresh, this._tools.deploy);
      this._toolbarMounted = true;
    }
  } else {
    const row = document.createElement('div'); row.className = 'bt-title-row';
    row.appendChild(this._tools.refresh);
    row.appendChild(this._tools.deploy);
    row.appendChild(this._tools.search);
    this.headerEl.appendChild(row);
  }

  // Scope strip — switches between company-wide and server-wide views.
  // The server tab is gated to super admins; for regular users we still
  // render it disabled so the affordance is visible and explained.
  const scopeStrip = document.createElement('div'); scopeStrip.className = 'bt-scope-tabs';
  const scopes = [
    { key: 'company', label: 'Company', icon: 'company' },
    { key: 'server',  label: 'Server',  icon: 'server' },
  ];
  for (const s of scopes) {
    const b = document.createElement('button'); b.type = 'button';
    const allowed = this.canUseScope(s.key);
    b.className = 'bt-scope-tab' + (this.scope === s.key ? ' is-active' : '') + (allowed ? '' : ' is-locked');
    b.disabled = !allowed;
    b.title = allowed ? s.label + ' bots'
      : "You don't have the scope to manage server-level bots. Ask a super admin to grant `server:bots`.";
    b.innerHTML = (s.icon === 'server'
      ? '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="6" rx="1.5"/><rect x="3" y="14" width="18" height="6" rx="1.5"/><line x1="7" y1="7" x2="7.01" y2="7"/><line x1="7" y1="17" x2="7.01" y2="17"/></svg>'
      : '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 21h18M5 21V7l7-4 7 4v14M9 9h1M9 13h1M9 17h1M14 9h1M14 13h1M14 17h1"/></svg>')
      + '<span>' + escapeB(s.label) + '</span>';
    b.addEventListener('click', () => {
      if (!this.canUseScope(s.key)) return;
      this.scope = s.key;
      writeJsonB('agixt.desktop.bots.scope.v1', s.key);
      this.renderHeader(); this.renderTable(); this.renderPlatforms();
    });
    scopeStrip.appendChild(b);
  }
  this.headerEl.appendChild(scopeStrip);

  // Server scope has fewer backend affordances than company scope:
  // there is no per-instance settings GET (so Configure can't pre-fill
  // existing values) and no restart endpoint. Make those limits
  // visible so users know what's intentional vs. broken.
  if (this.scope === 'server') {
    const limits = document.createElement('div');
    limits.className = 'bt-scope-note';
    limits.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
      + '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>'
      + '<div><strong>Server-wide bots</strong> are single-instance per platform. Pause/resume and delete work from desktop; <em>restart</em> isn\'t exposed by the backend, and <em>configure</em> always starts from a blank form (no settings prefill).</div>';
    this.headerEl.appendChild(limits);
  }

  const tabs = [
    { key: 'all',     label: 'All',     n: counts.all },
    { key: 'running', label: 'Running', n: counts.running },
    { key: 'paused',  label: 'Paused',  n: counts.paused },
    { key: 'offline', label: 'Offline', n: counts.offline },
    { key: 'error',   label: 'Errors',  n: counts.error },
  ];
  const tabsRow = document.createElement('div'); tabsRow.className = 'bt-tabs';
  for (const t of tabs) {
    const b = document.createElement('button'); b.type = 'button';
    b.className = 'bt-tab' + (this.statusFilter === t.key ? ' is-active' : '');
    b.textContent = t.label + ' (' + t.n + ')';
    b.addEventListener('click', () => { this.statusFilter = t.key; writeJsonB('agixt.desktop.bots.status.v1', t.key); this.renderHeader(); this.renderTable(); });
    tabsRow.appendChild(b);
  }
  this.headerEl.appendChild(tabsRow);
};

BotsView.prototype._buildTools = function () {
  const tools = {};
  tools.refresh = document.createElement('button');
  tools.refresh.type = 'button'; tools.refresh.className = 'bt-iconbtn'; tools.refresh.textContent = '↻';
  tools.refresh.title = 'Refresh';
  tools.refresh.addEventListener('click', () => this.refresh());

  tools.deploy = document.createElement('button');
  tools.deploy.type = 'button'; tools.deploy.className = 'bt-primary'; tools.deploy.textContent = '+ Deploy agent';
  tools.deploy.title = 'Configure and deploy a bot to a messaging platform';
  tools.deploy.addEventListener('click', () => this.openDeploy());

  tools.search = document.createElement('input');
  tools.search.type = 'search'; tools.search.placeholder = 'Search platform, company, agent…';
  tools.search.value = this.search; tools.search.className = 'bt-search';
  tools.search.addEventListener('input', (e) => { this.search = e.target.value; this.renderTable(); });

  this._tools = tools;
};

BotsView.prototype.renderStats = function () {
  if (!this.statsEl) return;
  const total = this.deployedBots.length;
  const running = this.deployedBots.filter((b) => this.statusBucket(b) === 'running').length;
  const paused = this.deployedBots.filter((b) => this.statusBucket(b) === 'paused').length;
  const errors = this.deployedBots.filter((b) => this.statusBucket(b) === 'error').length;
  const messages = this.deployedBots.reduce((acc, b) => acc + (Number(b.messages_processed) || 0), 0);

  const cards = [
    { label: 'Deployed', value: total, hint: 'Active deployments' },
    { label: 'Running',  value: running, hint: 'Active now', cls: 'bt-stat-good' },
    { label: 'Paused',   value: paused, hint: 'Temporarily stopped', cls: 'bt-stat-warn' },
    { label: 'Errors',   value: errors, hint: 'Need attention', cls: 'bt-stat-bad' },
    { label: 'Messages', value: messages.toLocaleString(), hint: 'Total processed' },
  ];
  this.statsEl.innerHTML = '';
  for (const c of cards) {
    const card = document.createElement('div'); card.className = 'bt-stat ' + (c.cls || '');
    card.innerHTML = '<div class="bt-stat-label">' + escapeB(c.label) + '</div>' +
      '<div class="bt-stat-value">' + escapeB(String(c.value)) + '</div>' +
      '<div class="bt-stat-hint">' + escapeB(c.hint) + '</div>';
    this.statsEl.appendChild(card);
  }
};

BotsView.prototype.renderTable = function () {
  if (!this.tableEl) return;
  this.renderStats();
  const rows = this.filteredAndSorted();
  const headers = BOT_COLS.map((c) => {
    const sortable = c.sortable ? ' is-sortable' : '';
    const active = this.sort.id === c.id ? ' is-sorted' : '';
    const arrow = this.sort.id === c.id ? (this.sort.dir === 'asc' ? ' ▲' : ' ▼') : '';
    return '<th class="bt-th' + sortable + active + '" data-col="' + c.id + '">' + escapeB(c.label) + escapeB(arrow) + '</th>';
  }).join('');
  const bodyRows = rows.length
    ? rows.map((b) => this.rowHtml(b)).join('')
    : '<tr><td colspan="' + BOT_COLS.length + '" class="bt-empty">No deployed agents.</td></tr>';
  this.tableEl.innerHTML = '<table class="bt-table"><thead><tr>' + headers + '</tr></thead><tbody>' + bodyRows + '</tbody></table>';

  this.tableEl.querySelectorAll('.bt-th.is-sortable').forEach((th) => {
    th.addEventListener('click', () => {
      const id = th.dataset.col;
      if (this.sort.id === id) this.sort.dir = this.sort.dir === 'asc' ? 'desc' : 'asc';
      else { this.sort.id = id; this.sort.dir = (id === 'msgs' || id === 'started') ? 'desc' : 'asc'; }
      writeJsonB('agixt.desktop.bots.sort.v1', this.sort);
      this.renderTable();
    });
  });

  const view = this;
  const findBot = (id) => view.deployedBots.find((b) =>
    (b.id || ((b.company_id || 'server') + '|' + b.platform + '|' + (b.instance_id || 'default'))) === id);
  this.tableEl.querySelectorAll('button[data-action]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const b = findBot(btn.dataset.id);
      if (!b) return;
      if (btn.dataset.action === 'pause') view.pauseBot(b);
      else if (btn.dataset.action === 'restart') view.restartBot(b);
      else if (btn.dataset.action === 'config') view.openConfigure(b);
      else if (btn.dataset.action === 'delete') view.deleteBot(b);
    });
  });
};

BotsView.prototype.rowHtml = function (b) {
  const id = b.id || ((b.company_id || 'server') + '|' + b.platform + '|' + (b.instance_id || 'default'));
  const bucket = this.statusBucket(b);
  const statusClass = bucket === 'running' ? 'bt-pill-good' :
                       bucket === 'paused'  ? 'bt-pill-warn' :
                       bucket === 'error'   ? 'bt-pill-bad'  : 'bt-pill-mute';
  const platform = (b.platform_name || b.platform || '');
  const isServer = b._scope === 'server';
  const instance = isServer ? 'server-wide' : (b.instance_name || b.instance_id || 'default');
  const company = isServer ? '<span class="bt-faint">Server</span>' : escapeB(b.company_name || '');
  const agent = b.agent_name || '<span class="bt-faint">—</span>';
  const started = b.started_at ? formatRelativeB(b.started_at) : '<span class="bt-faint">—</span>';
  const actions = [];
  actions.push('<button data-action="pause" data-id="' + escapeB(id) + '">' + (b.is_paused ? 'Resume' : 'Pause') + '</button>');
  // Server bots don't expose restart/configure endpoints; only show
  // Restart/Configure for company-scope rows so the buttons match what
  // the backend can actually do.
  if (!isServer) {
    actions.push('<button data-action="restart" data-id="' + escapeB(id) + '">Restart</button>');
    actions.push('<button data-action="config" data-id="' + escapeB(id) + '">Configure</button>');
  }
  actions.push('<button class="danger" data-action="delete" data-id="' + escapeB(id) + '">Delete</button>');

  return '<tr>' +
    '<td><span class="bt-platform">' + escapeB(platform) + '</span></td>' +
    '<td>' + escapeB(instance) + '</td>' +
    '<td>' + company + '</td>' +
    '<td>' + (typeof agent === 'string' && agent.indexOf('<') === 0 ? agent : escapeB(agent)) + '</td>' +
    '<td><span class="bt-pill ' + statusClass + '">' + escapeB(bucket) + '</span>' +
      (b.error ? '<div class="bt-error-detail" title="' + escapeB(b.error) + '">' + escapeB(truncB(b.error, 50)) + '</div>' : '') +
    '</td>' +
    '<td>' + (Number(b.messages_processed) || 0).toLocaleString() + '</td>' +
    '<td>' + (typeof started === 'string' && started.indexOf('<') === 0 ? started : escapeB(started)) + '</td>' +
    '<td class="bt-actions">' + actions.join('') + '</td>' +
  '</tr>';
};

BotsView.prototype.renderPlatforms = function () {
  if (!this.platformsEl) return;
  if (!this.platforms.length) { this.platformsEl.innerHTML = ''; return; }
  const card = document.createElement('div'); card.className = 'bt-card';
  const head = document.createElement('div'); head.className = 'bt-card-head';
  const title = document.createElement('div'); title.className = 'bt-card-title'; title.textContent = 'Available platforms';
  const desc = document.createElement('div'); desc.className = 'bt-card-desc';
  desc.textContent = 'Click any platform below to start a new deployment. OAuth platforms need a connected provider before deployment will succeed.';
  head.appendChild(title); head.appendChild(desc);
  card.appendChild(head);
  const body = document.createElement('div'); body.className = 'bt-card-body bt-platform-grid';
  const view = this;
  for (const p of this.platforms) {
    const needsOAuth = !!p.uses_oauth;
    const hasConn = view.hasOAuthConnection(p);
    const item = document.createElement('div');
    item.className = 'bt-platform-item' + (needsOAuth && !hasConn ? ' bt-platform-needs-oauth' : '');
    const providerLabel = p.oauth_provider_display || p.oauth_provider || '';
    const oauthBadge = needsOAuth
      ? (hasConn
          ? '<span class="bt-platform-tag bt-platform-tag-ok">✓ ' + escapeB(providerLabel) + ' connected</span>'
          : '<span class="bt-platform-tag bt-platform-tag-warn">⚠ ' + escapeB(providerLabel) + ' not connected</span>')
      : '';
    const setupLink = p.setup_url
      ? '<a class="bt-platform-link" href="' + escapeB(p.setup_url) + '" target="_blank" rel="noopener">Setup guide ↗</a>'
      : '';
    item.innerHTML = '<div class="bt-platform-name">' + escapeB(p.name) + '</div>'
      + '<div class="bt-platform-desc">' + escapeB(p.description || '') + '</div>'
      + oauthBadge
      + '<div class="bt-platform-actions">'
      + '<button class="bt-platform-btn" data-action="deploy">' + (needsOAuth && !hasConn ? 'Configure' : 'Deploy') + '</button>'
      + (needsOAuth && !hasConn
          ? '<button class="bt-platform-btn bt-platform-btn-primary" data-action="connect">Connect ' + escapeB(providerLabel || 'provider') + '</button>'
          : '')
      + setupLink
      + '</div>';
    item.querySelector('[data-action="deploy"]').addEventListener('click', (e) => {
      e.stopPropagation();
      const deployScope = view.scope === 'server' && view.canUseScope('server') ? 'server' : 'company';
      const companyId = deployScope === 'company'
        ? (view.ctx.companyId || (view.companies[0] && view.companies[0].id) || '')
        : '';
      view._configureBot(p, companyId, 'new', null, {}, null, deployScope);
    });
    const connectBtn = item.querySelector('[data-action="connect"]');
    if (connectBtn) {
      connectBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        view.openConnectionSettings(p);
      });
    }
    body.appendChild(item);
  }
  card.appendChild(body);
  this.platformsEl.innerHTML = '';
  this.platformsEl.appendChild(card);
};

BotsView.prototype.renderError = function (err) {
  if (!this.errEl) return;
  if (!err) { this.errEl.hidden = true; this.errEl.textContent = ''; return; }
  this.errEl.textContent = err.message || 'Request failed.';
  this.errEl.hidden = false;
};

BotsView.prototype.injectStyles = function () {
  if (document.getElementById('bt-styles')) return;
  const css = `
    .bt-root { --bt-border: var(--border); --bt-divider: var(--border-muted); --bt-row-hover: var(--panel-hover); --bt-card-bg: var(--panel-2);
      display: flex; flex-direction: column; gap: 16px; padding: 16px 20px 32px; min-height: 100%; color: var(--text); }
    .bt-title-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .bt-iconbtn { width: 30px; height: 30px; border-radius: 6px; border: 1px solid var(--bt-border); background: var(--panel-2); color: var(--text-dim); cursor: pointer; font-size: 14px; display: inline-flex; align-items: center; justify-content: center; }
    .bt-iconbtn:hover { background: var(--panel); color: var(--text); }
    .bt-primary { font-size: 12.5px; padding: 6px 14px; border-radius: 6px; background: var(--accent); color: #fff; border: 1px solid var(--accent); cursor: pointer; font-weight: 500; }
    .bt-search { flex: 1 1 240px; max-width: 360px; padding: 7px 12px; font-size: 13px; background: var(--panel-2); color: var(--text); border: 1px solid var(--bt-border); border-radius: 6px; }
    .bt-search:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(107,123,255,0.18); }
    .bt-tabs { display: flex; gap: 6px; flex-wrap: wrap; }
    .bt-tab { padding: 5px 12px; font-size: 12.5px; font-weight: 500; border-radius: 999px; background: transparent; color: var(--text-dim); border: 1px solid var(--bt-border); cursor: pointer; }
    .bt-tab:hover { background: var(--panel-2); color: var(--text); }
    .bt-tab.is-active { background: var(--accent); color: #fff; border-color: var(--accent); }
    .bt-error { padding: 10px 14px; border-radius: 8px; font-size: 12.5px; background: rgba(220, 60, 80, 0.18); border: 1px solid rgba(220, 60, 80, 0.4); color: #ffb4ba; }
    .bt-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }
    .bt-stat { background: var(--bt-card-bg); border: 1px solid var(--bt-border); border-radius: 10px; padding: 12px 14px; }
    .bt-stat-label { font-size: 11px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.07em; font-weight: 600; }
    .bt-stat-value { font-size: 22px; font-weight: 700; margin-top: 4px; }
    .bt-stat-hint { font-size: 11.5px; color: var(--text-faint); margin-top: 2px; }
    .bt-stat-good .bt-stat-value { color: #9ce0b3; }
    .bt-stat-warn .bt-stat-value { color: #ffd28a; }
    .bt-stat-bad .bt-stat-value { color: #ff7a86; }
    .bt-table-wrap { overflow: auto; background: var(--bt-card-bg); border: 1px solid var(--bt-border); border-radius: 10px; }
    .bt-table { width: 100%; border-collapse: collapse; font-size: 13px; min-width: 1100px; }
    .bt-table th, .bt-table td { padding: 11px 14px; text-align: left; border-bottom: 1px solid var(--bt-divider); vertical-align: middle; }
    .bt-table tbody tr:hover { background: var(--bt-row-hover); }
    .bt-table tbody tr:last-child td { border-bottom: 0; }
    .bt-th { color: var(--text-faint); font-weight: 600; font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.07em; background: var(--border-muted); border-bottom: 1px solid var(--bt-border); white-space: nowrap; user-select: none; }
    .bt-th.is-sortable { cursor: pointer; }
    .bt-th.is-sortable:hover { color: var(--text); background: var(--bt-row-hover); }
    .bt-platform { font-weight: 600; text-transform: capitalize; }
    .bt-pill { display: inline-flex; align-items: center; font-size: 11px; padding: 2px 9px; border-radius: 999px; border: 1px solid var(--bt-border); color: var(--text-dim); text-transform: capitalize; background: var(--panel-2); }
    .bt-pill-good { background: rgba(80,200,130,0.16); color: #9ce0b3; border-color: rgba(80,200,130,0.4); }
    .bt-pill-warn { background: rgba(232,167,68,0.16); color: #ffd28a; border-color: rgba(232,167,68,0.4); }
    .bt-pill-bad { background: rgba(220,60,80,0.16); color: #ff7a86; border-color: rgba(220,60,80,0.4); }
    .bt-pill-mute { color: var(--text-faint); }
    .bt-error-detail { font-size: 11px; color: #ff7a86; margin-top: 3px; max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .bt-faint { color: var(--text-faint); }
    .bt-actions { display: flex; gap: 4px; justify-content: flex-end; flex-wrap: wrap; }
    .bt-actions button { font-size: 11px; padding: 3px 9px; border-radius: 5px; border: 1px solid var(--bt-border); background: var(--panel-2); color: var(--text); cursor: pointer; white-space: nowrap; }
    .bt-actions button:hover { background: var(--panel); }
    .bt-actions button.danger { color: #ffb4ba; border-color: rgba(220,60,80,0.4); }
    .bt-actions button.danger:hover { background: rgba(220, 60, 80, 0.18); }
    .bt-empty { padding: 32px; text-align: center; color: var(--text-faint); }
    .bt-card { background: var(--bt-card-bg); border: 1px solid var(--bt-border); border-radius: 10px; overflow: hidden; }
    .bt-card-head { padding: 13px 16px; border-bottom: 1px solid var(--bt-border); background: var(--border-muted); }
    .bt-card-title { font-weight: 600; font-size: 13.5px; }
    .bt-card-desc { font-size: 12px; color: var(--text-faint); margin-top: 3px; }
    .bt-card-body { padding: 16px 18px; }
    .bt-platform-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
    .bt-platform-item { padding: 12px 14px; background: var(--panel-2); border: 1px solid var(--bt-border); border-radius: 8px; display: flex; flex-direction: column; gap: 6px; transition: border-color 120ms ease; }
    .bt-platform-item:hover { border-color: color-mix(in srgb, var(--accent) 25%, var(--bt-border)); }
    .bt-platform-needs-oauth { border-color: color-mix(in srgb, #ffb774 30%, var(--bt-border)); }
    .bt-platform-name { font-weight: 600; font-size: 13px; text-transform: capitalize; }
    .bt-platform-desc { font-size: 11.5px; color: var(--text-faint); }
    .bt-platform-tag { font-size: 10.5px; color: var(--text-dim); padding: 2px 8px; background: var(--panel); border: 1px solid var(--bt-border); border-radius: 999px; display: inline-block; align-self: flex-start; }
    .bt-platform-tag-ok { color: #5dd28f; border-color: rgba(94, 210, 143, 0.34); background: rgba(94, 210, 143, 0.14); }
    .bt-platform-tag-warn { color: #ffb774; border-color: rgba(255, 183, 116, 0.4); background: rgba(255, 183, 116, 0.12); }
    .bt-platform-actions { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; margin-top: 4px; }
    .bt-platform-btn { font-size: 11.5px; padding: 5px 12px; border-radius: 6px; background: var(--panel); color: var(--text); border: 1px solid var(--bt-border); cursor: pointer; font-weight: 500; }
    .bt-platform-btn:hover { background: var(--panel-2); border-color: color-mix(in srgb, var(--accent) 30%, var(--bt-border)); }
    .bt-platform-btn-primary { background: var(--accent); color: #fff; border-color: var(--accent); }
    .bt-platform-btn-primary:hover { filter: brightness(1.1); background: var(--accent); }
    .bt-platform-link { font-size: 11px; color: var(--accent); text-decoration: none; margin-left: auto; }
    .bt-platform-link:hover { text-decoration: underline; }

    /* Scope tabs — Company / Server */
    .bt-scope-tabs { display: inline-flex; gap: 2px; padding: 3px; border: 1px solid var(--bt-border); background: var(--panel-2); border-radius: 8px; align-self: flex-start; }
    .bt-scope-tab { appearance: none; border: 0; background: transparent; color: var(--text-dim); font-family: inherit; font-size: 12px; font-weight: 600; padding: 6px 10px; border-radius: 6px; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; transition: background 140ms ease, color 140ms ease; }
    .bt-scope-tab:hover:not(:disabled) { color: var(--text); background: var(--panel-hover); }
    .bt-scope-tab.is-active { color: #fff; background: var(--accent); }
    .bt-scope-tab:disabled,
    .bt-scope-tab.is-locked { opacity: 0.45; cursor: not-allowed; }
    .bt-scope-tab.is-locked::after { content: "🔒"; font-size: 10px; margin-left: 2px; }

    /* Inline note explaining server-scope limitations. Matches the
       overall info-banner styling used elsewhere (e.g. payment-banner
       in user-settings) without pulling in another component. */
    .bt-scope-note {
      display: flex; gap: 10px; align-items: flex-start;
      padding: 10px 12px; margin-top: 4px;
      background: color-mix(in srgb, #8bc7ff 8%, var(--panel-2));
      border: 1px solid color-mix(in srgb, #8bc7ff 30%, var(--bt-border));
      border-radius: 8px;
      color: var(--text-dim);
      font-size: 12px; line-height: 1.5;
    }
    .bt-scope-note svg { flex: 0 0 auto; color: #8bc7ff; margin-top: 1px; }
    .bt-scope-note strong { color: var(--text); }
    .bt-scope-note em { color: var(--text-dim); font-style: normal; font-weight: 600; }
  `;
  const tag = document.createElement('style'); tag.id = 'bt-styles'; tag.textContent = css; document.head.appendChild(tag);
};

function escapeB(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
function truncB(s, n) { if (s == null) return ''; const v = String(s); return v.length > n ? v.slice(0, n - 1) + '…' : v; }
function formatRelativeB(iso) {
  const ms = Date.parse(iso); if (!isFinite(ms)) return '';
  const diff = Date.now() - ms;
  if (diff < 60_000) return 'just now';
  if (diff < 3600_000) return Math.round(diff / 60_000) + 'm ago';
  if (diff < 86400_000) return Math.round(diff / 3600_000) + 'h ago';
  return Math.round(diff / 86400_000) + 'd ago';
}
function readJsonB(k, f) { try { const r = window.localStorage.getItem(k); if (!r) return f; const v = JSON.parse(r); return v == null ? f : v; } catch (_) { return f; } }
function writeJsonB(k, v) { try { window.localStorage.setItem(k, JSON.stringify(v)); } catch (_) {} }

/* Shared form modal — see assets/main.js for full documentation. */
function ensureFormModalB() {
  if (window.AgixtFormModal) return;
  const STYLE_ID = 'agixt-ext-modal-styles';
  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const css = `.xt-modal-overlay { position: fixed; inset: 0; z-index: 10000; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.55); padding: 24px; } .xt-modal { background: var(--panel, #1c1f26); color: var(--text, #e6e8ee); border: 1px solid var(--border, #2a2e38); border-radius: 12px; width: 100%; max-width: 560px; max-height: calc(100vh - 64px); display: flex; flex-direction: column; box-shadow: 0 12px 40px rgba(0,0,0,0.5); overflow: hidden; } .xt-modal-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 16px 20px; border-bottom: 1px solid var(--border, #2a2e38); background: var(--panel-2, #232730); } .xt-modal-title { margin: 0; font-size: 16px; font-weight: 700; } .xt-modal-desc { margin: 4px 0 0; font-size: 12px; color: var(--text-faint, #8b94a3); } .xt-modal-x { background: transparent; border: 0; color: var(--text-dim, #aab1be); font-size: 18px; cursor: pointer; padding: 0 4px; line-height: 1; } .xt-modal-x:hover { color: var(--text, #e6e8ee); } .xt-modal-body { padding: 18px 20px; overflow: auto; display: flex; flex-direction: column; gap: 14px; } .xt-modal-footer { display: flex; justify-content: flex-end; gap: 8px; padding: 14px 20px; border-top: 1px solid var(--border, #2a2e38); background: var(--panel-2, #232730); } .xt-field { display: flex; flex-direction: column; gap: 5px; } .xt-field label { font-size: 12px; font-weight: 600; color: var(--text-dim, #aab1be); } .xt-field .xt-required { color: #ff7a86; } .xt-field .xt-help { font-size: 11px; color: var(--text-faint, #8b94a3); } .xt-field input[type=text], .xt-field input[type=email], .xt-field input[type=number], .xt-field input[type=date], .xt-field input[type=datetime-local], .xt-field input[type=password], .xt-field textarea, .xt-field select { font-family: inherit; font-size: 13px; background: var(--panel-2, #232730); color: var(--text, #e6e8ee); border: 1px solid var(--border, #2a2e38); border-radius: 6px; padding: 8px 10px; box-sizing: border-box; width: 100%; } .xt-field textarea { resize: vertical; min-height: 60px; } .xt-field select { appearance: none; -webkit-appearance: none; padding-right: 28px; cursor: pointer; background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24' fill='none' stroke='%23a1a7b5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><polyline points='6 9 12 15 18 9'/></svg>"); background-repeat: no-repeat; background-position: right 10px center; background-size: 10px 10px; } .xt-field input:focus, .xt-field textarea:focus, .xt-field select:focus { outline: none; border-color: var(--accent, #6b7bff); box-shadow: 0 0 0 3px rgba(107,123,255,0.18); } .xt-field-checkbox { flex-direction: row; align-items: center; gap: 10px; } .xt-field-checkbox label { order: 2; margin: 0; font-weight: 500; color: var(--text, #e6e8ee); cursor: pointer; } .xt-field-checkbox input[type=checkbox] { width: 16px; height: 16px; margin: 0; cursor: pointer; } .xt-kv-list { display: flex; flex-direction: column; gap: 6px; } .xt-kv-row { display: grid; grid-template-columns: 1fr 1.5fr auto; gap: 6px; align-items: center; } .xt-kv-row input { width: 100%; } .xt-kv-add { font-size: 12px; padding: 5px 12px; border-radius: 6px; background: var(--panel-2, #232730); color: var(--text, #e6e8ee); border: 1px solid var(--border, #2a2e38); cursor: pointer; align-self: flex-start; } .xt-kv-add:hover { background: var(--panel, #1c1f26); } .xt-kv-del { width: 26px; height: 26px; border-radius: 5px; border: 1px solid var(--border, #2a2e38); background: transparent; color: #ffb4ba; cursor: pointer; } .xt-kv-del:hover { background: rgba(220, 60, 80, 0.18); } .xt-modal-error { padding: 8px 12px; border-radius: 6px; font-size: 12px; background: rgba(220, 60, 80, 0.18); border: 1px solid rgba(220, 60, 80, 0.4); color: #ffb4ba; } .xt-btn-cancel { font-size: 12.5px; padding: 7px 16px; border-radius: 6px; background: var(--panel, #1c1f26); color: var(--text, #e6e8ee); border: 1px solid var(--border, #2a2e38); cursor: pointer; } .xt-btn-cancel:hover { background: var(--panel-hover, #2a2e38); } .xt-btn-submit { font-size: 12.5px; padding: 7px 16px; border-radius: 6px; background: var(--accent, #6b7bff); color: #fff; border: 1px solid var(--accent, #6b7bff); cursor: pointer; font-weight: 500; } .xt-btn-submit:hover { filter: brightness(1.1); } .xt-btn-submit[disabled] { opacity: 0.6; cursor: not-allowed; } .xt-btn-submit.danger { background: rgba(220, 60, 80, 0.85); border-color: rgba(220, 60, 80, 0.85); }`;
    const tag = document.createElement('style'); tag.id = STYLE_ID; tag.textContent = css;
    document.head.appendChild(tag);
  }
  function renderKvList(initial, opts) {
    opts = opts || {}; const wrap = document.createElement('div'); wrap.className = 'xt-kv-list';
    function addRow(k, v) {
      const row = document.createElement('div'); row.className = 'xt-kv-row';
      const keyIn = document.createElement('input'); keyIn.type = 'text'; keyIn.placeholder = 'Key'; keyIn.value = k || '';
      const valIn = document.createElement('input'); valIn.type = 'text'; valIn.placeholder = opts.valuePlaceholder || 'Value'; valIn.value = v == null ? '' : String(v);
      const del = document.createElement('button'); del.type = 'button'; del.className = 'xt-kv-del'; del.textContent = '×';
      del.addEventListener('click', () => { wrap.removeChild(row); });
      row.appendChild(keyIn); row.appendChild(valIn); row.appendChild(del);
      wrap.insertBefore(row, addBtn);
    }
    const addBtn = document.createElement('button'); addBtn.type = 'button'; addBtn.className = 'xt-kv-add'; addBtn.textContent = '+ Add row';
    addBtn.addEventListener('click', () => addRow('', ''));
    wrap.appendChild(addBtn);
    if (initial && initial.length) for (const it of initial) addRow(it.key, it.value); else addRow('', '');
    return wrap;
  }
  function readKvList(wrap) {
    const out = []; wrap.querySelectorAll('.xt-kv-row').forEach((row) => {
      const inputs = row.querySelectorAll('input');
      if (!inputs[0]) return;
      const k = inputs[0].value.trim(); const v = inputs[1] ? inputs[1].value : '';
      if (k) out.push({ key: k, value: v });
    });
    return out;
  }
  function show(opts) {
    injectStyles();
    return new Promise((resolve) => {
      const overlay = document.createElement('div'); overlay.className = 'xt-modal-overlay';
      const modal = document.createElement('div'); modal.className = 'xt-modal';
      const head = document.createElement('div'); head.className = 'xt-modal-head';
      const tw = document.createElement('div');
      const title = document.createElement('h2'); title.className = 'xt-modal-title'; title.textContent = opts.title || ''; tw.appendChild(title);
      if (opts.description) { const d = document.createElement('p'); d.className = 'xt-modal-desc'; d.textContent = opts.description; tw.appendChild(d); }
      head.appendChild(tw);
      const x = document.createElement('button'); x.type = 'button'; x.className = 'xt-modal-x'; x.innerHTML = '&times;'; head.appendChild(x);
      modal.appendChild(head);
      const body = document.createElement('div'); body.className = 'xt-modal-body'; modal.appendChild(body);
      const errEl = document.createElement('div'); errEl.className = 'xt-modal-error'; errEl.hidden = true; body.appendChild(errEl);
      const refs = {};
      const fields = opts.fields || [];
      for (const f of fields) {
        const fd = document.createElement('div'); fd.className = 'xt-field';
        if (f.type === 'checkbox') fd.classList.add('xt-field-checkbox');
        if (f.label) {
          const lbl = document.createElement('label'); lbl.textContent = f.label;
          if (f.required) { const star = document.createElement('span'); star.className = 'xt-required'; star.textContent = ' *'; lbl.appendChild(star); }
          fd.appendChild(lbl);
        }
        let input;
        if (f.type === 'textarea') { input = document.createElement('textarea'); if (f.rows) input.rows = f.rows; if (f.placeholder) input.placeholder = f.placeholder; if (f.value != null) input.value = String(f.value); }
        else if (f.type === 'select') { input = document.createElement('select'); for (const o of (f.options || [])) { const opt = document.createElement('option'); opt.value = o.value; opt.textContent = o.label; input.appendChild(opt); } if (f.value != null) input.value = String(f.value); }
        else if (f.type === 'checkbox') { input = document.createElement('input'); input.type = 'checkbox'; input.checked = !!f.value; fd.insertBefore(input, fd.firstChild); }
        else if (f.type === 'kv') { input = renderKvList(f.value || []); }
        else if (f.type === 'kvtype') { const arr = Object.entries(f.value || {}).map(([k, v]) => ({ key: k, value: (v && typeof v === 'object' && v.type) ? v.type : (typeof v === 'string' ? v : 'text') })); input = renderKvList(arr, { valuePlaceholder: 'text|number|date|boolean|email' }); input.dataset.kind = 'kvtype'; }
        else { input = document.createElement('input'); input.type = f.type || 'text'; if (f.placeholder) input.placeholder = f.placeholder; if (f.value != null) input.value = String(f.value); if (f.min != null) input.min = String(f.min); if (f.max != null) input.max = String(f.max); if (f.step != null) input.step = String(f.step); }
        if (input.tagName !== 'DIV') fd.appendChild(input);
        if (f.help) { const help = document.createElement('div'); help.className = 'xt-help'; help.textContent = f.help; fd.appendChild(help); }
        refs[f.key] = { field: f, input: input };
        body.appendChild(fd);
      }
      const foot = document.createElement('div'); foot.className = 'xt-modal-footer';
      const cancelBtn = document.createElement('button'); cancelBtn.type = 'button'; cancelBtn.className = 'xt-btn-cancel'; cancelBtn.textContent = opts.cancelLabel || 'Cancel';
      const submitBtn = document.createElement('button'); submitBtn.type = 'button'; submitBtn.className = 'xt-btn-submit' + (opts.danger ? ' danger' : ''); submitBtn.textContent = opts.submitLabel || 'Save';
      foot.appendChild(cancelBtn); foot.appendChild(submitBtn);
      modal.appendChild(foot); overlay.appendChild(modal); document.body.appendChild(overlay);
      let closed = false;
      function close(r) { if (closed) return; closed = true; document.removeEventListener('keydown', onKey); if (overlay.parentNode) overlay.parentNode.removeChild(overlay); resolve(r); }
      function onKey(e) { if (e.key === 'Escape') { e.preventDefault(); close(null); } else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); doSubmit(); } }
      document.addEventListener('keydown', onKey);
      x.addEventListener('click', () => close(null)); cancelBtn.addEventListener('click', () => close(null));
      overlay.addEventListener('click', (e) => { if (e.target === overlay) close(null); });
      function readValue(ref) {
        const f = ref.field; const i = ref.input;
        if (f.type === 'checkbox') return !!i.checked;
        if (f.type === 'kv') return readKvList(i);
        if (f.type === 'kvtype') { const arr = readKvList(i); const out = {}; for (const it of arr) if (it.key) out[it.key] = { type: (it.value || 'text') }; return out; }
        if (f.type === 'number') { const v = i.value; if (v === '' || v == null) return null; const n = Number(v); return isFinite(n) ? n : null; }
        const v = i.value; return v === '' ? null : v;
      }
      function doSubmit() {
        errEl.hidden = true; errEl.textContent = '';
        const result = {};
        for (const key of Object.keys(refs)) {
          const ref = refs[key]; const val = readValue(ref);
          if (ref.field.required) { if (val == null || (typeof val === 'string' && !val.trim())) { errEl.textContent = (ref.field.label || ref.field.key) + ' is required.'; errEl.hidden = false; try { ref.input.focus(); } catch (_) {} return; } }
          result[key] = val;
        }
        if (typeof opts.validate === 'function') { const err = opts.validate(result); if (err) { errEl.textContent = err; errEl.hidden = false; return; } }
        close(result);
      }
      submitBtn.addEventListener('click', doSubmit);
      setTimeout(() => { const ff = fields.find((f) => f.type !== 'checkbox' && f.type !== 'kv' && f.type !== 'kvtype'); if (ff && refs[ff.key]) { try { refs[ff.key].input.focus(); } catch (_) {} } }, 0);
    });
  }
  window.AgixtFormModal = { show: show };
}

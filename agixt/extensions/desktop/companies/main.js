/* Companies & Teams — desktop port of the web app's /team + /companies pages.
 *
 * Endpoints consumed (all under ctx.serverUrl, Bearer ctx.jwt):
 *   Companies:
 *     GET    /v1/user                                    — me + my companies/scopes
 *     GET    /v1/companies                               — list (with users[]/children[])
 *     POST   /v1/companies                               — create
 *     PATCH  /v1/companies/{id}                          — update full company
 *     DELETE /v1/companies/{id}                          — delete
 *     POST   /v1/companies/{id}/rotate-key               — rotate API key
 *     GET    /v1/companies/{id}/members                  — member list w/ last_seen
 *     DELETE /v1/companies/{id}/users/{user_id}          — remove member
 *   Roles:
 *     PUT    /v1/user/role                               — change member's default role
 *     GET    /v1/default-roles                           — system role catalog
 *     GET    /v1/scopes                                  — all available scopes
 *     GET    /v1/roles?company_id=…                      — custom roles
 *     POST   /v1/roles?company_id=…                      — create custom role
 *     PUT    /v1/roles/{id}                              — update custom role
 *     DELETE /v1/roles/{id}                              — delete custom role
 *     GET    /v1/user/{user_id}/custom-roles             — user's custom-role assignments
 *     POST   /v1/user/custom-role                        — assign custom role to user
 *     DELETE /v1/user/{user_id}/custom-role/{role_id}    — unassign
 *   Invitations:
 *     GET    /v1/invitations/{company_id}                — pending invites
 *     POST   /v1/invitations                             — send (supports skip_email)
 *     DELETE /v1/invitation/{id}                         — cancel
 *
 * Admin gating uses role_id <= 1 (super admin / tenant admin / company admin)
 * for write affordances. The role_id 2 (Admin) check happens server-side via
 * scope enforcement; we surface buttons optimistically and let the API reject
 * if necessary, displaying friendlyError() messages.
 */

window.AgixtRegisterExtension('companies', {
  mount(container, ctx) {
    const v = new CompaniesView(container, ctx);
    container._companiesView = v;
    v.start();
  },
  unmount() {
    const root = document.querySelector('.chat-screen-main .view-pane[data-view="companies"]');
    if (root && root._companiesView) {
      root._companiesView.stop();
      root._companiesView = null;
    }
  },
});

const COMPANY_COLS = [
  { id: 'name',     label: 'Name',      sortable: true, width: 'minmax(220px, 2fr)' },
  { id: 'role',     label: 'Your role', sortable: true, width: '140px' },
  { id: 'users',    label: 'Users',     sortable: true, width: '90px' },
  { id: 'children', label: 'Sub-orgs',  sortable: true, width: '110px' },
  { id: 'agents',   label: 'Agents',    sortable: true, width: '90px' },
  { id: 'tokens',   label: 'Tokens',    sortable: true, width: '140px' },
  { id: 'phone',    label: 'Phone',     sortable: false, width: '140px' },
  { id: 'email',    label: 'Email',     sortable: false, width: 'minmax(160px, 1fr)' },
  { id: 'website',  label: 'Website',   sortable: false, width: '160px' },
  { id: 'actions',  label: '',          sortable: false, width: '240px' },
];

const ROLE_NAMES = { 0: 'Super Admin', 1: 'Owner', 2: 'Admin', 3: 'Manager', 4: 'User', 5: 'Chat User', 6: 'Read Only' };
// Roles assignable from the invite/role-change UI. Matches the web app's
// ASSIGNABLE_DEFAULT_ROLE_IDS — keeps super admin (0), tenant admin (1),
// and the "child" role (4) off the picker.
const ASSIGNABLE_ROLE_IDS = [2, 3, 5, 6];
const FALLBACK_DEFAULT_ROLES = [
  { id: 2, friendly_name: 'Admin' },
  { id: 3, friendly_name: 'User' },
  { id: 5, friendly_name: 'Chat User' },
  { id: 6, friendly_name: 'Read Only' },
];

function CompaniesView(container, ctx) {
  this.container = container;
  this.ctx = ctx;
  this.companies = [];
  this.scopes = new Set();
  this.roleId = null;
  this.search = '';
  this.sort = readJsonC('agixt.desktop.companies.sort.v1', { id: 'name', dir: 'asc' });
  this.busy = new Set();
  this.view = 'list';
  this.detail = {
    id: null,
    company: null,
    members: [],
    invitations: [],
    defaultRoles: [],
    customRoles: [],
    customRolesPerUser: {},
    memberFilter: '',
    loading: false,
    error: null,
  };
  this.userId = null;
  this._userCompanies = [];
}

CompaniesView.prototype.start = function () {
  this.injectStyles();
  this.render();
  this.loadUser().then(() => this.refresh());
};
CompaniesView.prototype.stop = function () { this.container.innerHTML = ''; };

// ─── Networking ──────────────────────────────────────────────────────

CompaniesView.prototype.fetchJson = async function (path, opts) {
  const u = new URL(path, this.ctx.serverUrl).toString();
  const init = {
    method: (opts && opts.method) || 'GET',
    headers: Object.assign(
      { Authorization: 'Bearer ' + this.ctx.jwt },
      (opts && opts.json != null) ? { 'Content-Type': 'application/json' } : {},
    ),
  };
  if (opts && opts.json != null) init.body = JSON.stringify(opts.json);
  const resp = await fetch(u, init);
  if (resp.status === 204) return null;
  const text = await resp.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (_) {}
  if (!resp.ok) {
    const err = new Error((data && data.detail) || ('HTTP ' + resp.status));
    err.status = resp.status; err.detail = data && data.detail; throw err;
  }
  return data;
};

CompaniesView.prototype.loadUser = async function () {
  try {
    const u = await this.fetchJson('/v1/user');
    this.userId = u && u.id;
    this._userCompanies = u && u.companies ? u.companies : [];
    const co = this._userCompanies.find((c) => c.id === this.ctx.companyId)
      || this._userCompanies[0];
    if (co) {
      this.scopes = new Set(co.scopes || []);
      this.roleId = co.role_id != null ? co.role_id : null;
    }
  } catch (_) {}
};

CompaniesView.prototype.canEditRow = function (c) {
  if (this.roleId === 0) return true;
  return Number(c.role_id) <= 1;  // owner of that company
};
CompaniesView.prototype.canAdminCompany = function (c) {
  // Roles 0/1/2 (super admin / tenant admin / company admin) grant the
  // ability to invite users, change roles, manage custom roles, etc.
  // Mirrors the web app's isAdminLikeRole check.
  if (this.roleId === 0) return true;
  const rid = Number(c && c.role_id);
  return rid >= 0 && rid <= 2;
};

CompaniesView.prototype.refresh = async function () {
  try {
    const [userResp, listResp] = await Promise.all([
      this.fetchJson('/v1/user').catch(() => null),
      this.fetchJson('/v1/companies').catch(() => null),
    ]);
    if (userResp && userResp.companies) this._userCompanies = userResp.companies;
    const userMap = {};
    for (const c of this._userCompanies || []) userMap[c.id] = c;
    const baseList = (Array.isArray(listResp) ? listResp : (listResp && listResp.companies)) || this._userCompanies || [];
    this.companies = baseList.map((c) => {
      const enriched = userMap[c.id] || {};
      return Object.assign({}, enriched, c, {
        role_id:        enriched.role_id != null ? enriched.role_id : c.role_id,
        scopes:         enriched.scopes || c.scopes,
        agents:         enriched.agents || c.agents,
        primary:        enriched.primary != null ? enriched.primary : c.primary,
        token_balance:  enriched.token_balance != null ? enriched.token_balance : c.token_balance,
        token_balance_usd: enriched.token_balance_usd != null ? enriched.token_balance_usd : c.token_balance_usd,
      });
    });
    this.renderError(null);
    if (this.view === 'list') {
      this.renderHeader();
      this.renderTeamPanel();
      this.renderTable();
    } else if (this.view === 'detail') {
      this.detail.company = this.companies.find((c) => c.id === this.detail.id) || null;
      await this.loadDetailData();
      this.renderDetailBody();
    }
  } catch (err) { this.renderError(err); }
};

// ─── Detail data hydration ───────────────────────────────────────────

CompaniesView.prototype.loadDetailData = async function () {
  if (!this.detail.id) return;
  const cid = this.detail.id;
  this.detail.loading = true;
  const [members, invitations, defaultRoles, customRoles] = await Promise.all([
    this.fetchJson('/v1/companies/' + encodeURIComponent(cid) + '/members')
      .then((d) => (d && d.members) || [])
      .catch(() => []),
    this.fetchJson('/v1/invitations/' + encodeURIComponent(cid))
      .then((d) => (d && d.invitations) || [])
      .catch(() => []),
    this.fetchJson('/v1/default-roles')
      .then((d) => (d && (d.roles || d.default_roles)) || d || [])
      .catch(() => []),
    this.fetchJson('/v1/roles?company_id=' + encodeURIComponent(cid))
      .then((d) => (d && d.roles) || [])
      .catch(() => []),
  ]);
  this.detail.members = Array.isArray(members) ? members : [];
  this.detail.invitations = Array.isArray(invitations) ? invitations : [];
  this.detail.defaultRoles = Array.isArray(defaultRoles) ? defaultRoles : [];
  this.detail.customRoles = Array.isArray(customRoles) ? customRoles : [];
  // Hydrate per-user custom role assignments in parallel — best-effort,
  // a single 403/404 per user shouldn't block the rest.
  const perUser = {};
  await Promise.all(this.detail.members.map(async (m) => {
    try {
      const data = await this.fetchJson(
        '/v1/user/' + encodeURIComponent(m.id) + '/custom-roles?company_id=' + encodeURIComponent(cid));
      perUser[m.id] = Array.isArray(data) ? data : (data && data.custom_roles) || [];
    } catch (_) { perUser[m.id] = []; }
  }));
  this.detail.customRolesPerUser = perUser;
  this.detail.loading = false;
};

CompaniesView.prototype.roleNameLookup = function () {
  const map = Object.assign({}, ROLE_NAMES);
  (this.detail.defaultRoles || []).forEach((r) => {
    if (r && typeof r.id !== 'undefined') {
      map[r.id] = r.friendly_name || r.name || map[r.id] || ('Role ' + r.id);
    }
  });
  return map;
};

CompaniesView.prototype.assignableDefaultRoles = function () {
  const list = (this.detail.defaultRoles && this.detail.defaultRoles.length
    ? this.detail.defaultRoles
    : FALLBACK_DEFAULT_ROLES);
  return list.filter((r) => ASSIGNABLE_ROLE_IDS.includes(r.id))
    .sort((a, b) => a.id - b.id);
};

// ─── List header / table ─────────────────────────────────────────────

CompaniesView.prototype.renderTeamPanel = function () {
  const root = this.container.querySelector('.co-root');
  if (!root) return;
  let panel = root.querySelector('.co-team-panel');
  if (!panel) {
    panel = document.createElement('div');
    panel.className = 'co-team-panel';
    if (this.headerEl && this.headerEl.nextSibling) {
      root.insertBefore(panel, this.headerEl.nextSibling);
    } else {
      root.appendChild(panel);
    }
  }
  panel.innerHTML = '';
  const primary = this.companies.find((c) => c.primary)
    || this.companies.find((c) => c.id === this.ctx.companyId)
    || this.companies[0];
  if (!primary) return;
  const users = Array.isArray(primary.users) ? primary.users : [];

  const card = document.createElement('div');
  card.className = 'co-card';
  const head = document.createElement('div');
  head.className = 'co-card-head';
  head.innerHTML =
    '<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;">' +
      '<div>' +
        '<div class="co-card-title">Your team — ' + escapeC(primary.name || 'Primary company') + '</div>' +
        '<div class="co-card-desc">' + (users.length || 0) + ' member' + (users.length === 1 ? '' : 's') +
          (primary.user_limit != null ? ' of ' + primary.user_limit : '') +
        '</div>' +
      '</div>' +
      (this.canAdminCompany(primary)
        ? '<button class="co-secondary" data-team-open data-id="' + escapeC(primary.id) + '">Manage in detail</button>'
        : '') +
    '</div>';
  card.appendChild(head);

  const body = document.createElement('div');
  body.className = 'co-card-body';
  if (!users.length) {
    body.appendChild((function () { const e = document.createElement('div'); e.className = 'co-faint'; e.style.cssText = 'padding:6px 0;'; e.textContent = 'No team members yet.'; return e; })());
  } else {
    const tbl = document.createElement('table');
    tbl.className = 'co-data-table';
    tbl.innerHTML =
      '<thead><tr><th>Email</th><th>Name</th><th>Role</th><th>Last seen</th></tr></thead>';
    const tbody = document.createElement('tbody');
    for (const u of users.slice(0, 50)) {
      const tr = document.createElement('tr');
      const role = u.role_id != null ? (ROLE_NAMES[u.role_id] || ('Role ' + u.role_id)) : '';
      const fullName = ((u.first_name || '') + ' ' + (u.last_name || '')).trim();
      tr.innerHTML =
        '<td>' + escapeC(u.email || u.username || u.id || '') + '</td>' +
        '<td>' + escapeC(fullName) + '</td>' +
        '<td>' + (role ? '<span class="co-rolepill">' + escapeC(role) + '</span>' : '<span class="co-faint">—</span>') + '</td>' +
        '<td class="co-faint">' + (u.last_seen ? formatRelativeC(u.last_seen) : '') + '</td>';
      tbody.appendChild(tr);
    }
    tbl.appendChild(tbody);
    body.appendChild(tbl);
    if (users.length > 50) {
      const more = document.createElement('div');
      more.className = 'co-faint';
      more.style.cssText = 'padding:8px 0 0;font-size:11.5px;';
      more.textContent = 'Showing 50 of ' + users.length + ' members.';
      body.appendChild(more);
    }
  }
  card.appendChild(body);
  panel.appendChild(card);

  const view = this;
  panel.querySelectorAll('button[data-team-open]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const c = view.companies.find((x) => x.id === btn.dataset.id);
      if (c) view.openDetail(c);
    });
  });
};

// ─── Top-level actions (create / delete / rotate / rename) ───────────

CompaniesView.prototype.openCreate = function () {
  this.openCompanyDialog({ mode: 'create' });
};

CompaniesView.prototype.deleteCompany = async function (c) {
  const ok = await confirmDialog({
    title: 'Delete company',
    message: 'Delete "' + (c.name || c.id) + '"? This permanently removes all members, data, and billing history. This cannot be undone.',
    confirmLabel: 'Delete forever',
    destructive: true,
  });
  if (!ok) return;
  try {
    await this.fetchJson('/v1/companies/' + encodeURIComponent(c.id), { method: 'DELETE' });
    await this.refresh();
  } catch (err) { this.renderError(err); }
};

CompaniesView.prototype.rotateKey = async function (c) {
  const ok = await confirmDialog({
    title: 'Rotate API key',
    message: 'Rotate the API key for "' + (c.name || c.id) + '"? Existing integrations will stop working until you update them with the new key.',
    confirmLabel: 'Rotate key',
    destructive: true,
  });
  if (!ok) return;
  try {
    await this.fetchJson('/v1/companies/' + encodeURIComponent(c.id) + '/rotate-key', { method: 'POST' });
    await infoDialog({
      title: 'API key rotated',
      message: 'The API key for "' + (c.name || '') + '" has been rotated. Update your integrations with the new key.',
    });
  } catch (err) { this.renderError(err); }
};

CompaniesView.prototype.openDetail = function (c) {
  this.detail.id = c.id;
  this.detail.company = c;
  this.detail.memberFilter = '';
  this.view = 'detail';
  this.render();
  this.loadDetailData().then(() => this.renderDetailBody());
};
CompaniesView.prototype.backToList = function () {
  this.view = 'list';
  this._toolbarMounted = false; // re-mount tools when returning to list
  this.render();
  this.refresh();
};

// ─── Filter + sort ───────────────────────────────────────────────────

CompaniesView.prototype.filteredAndSorted = function () {
  const q = (this.search || '').trim().toLowerCase();
  const out = this.companies.filter((c) => {
    if (!q) return true;
    const hay = [c.name, c.email, c.phone_number, c.website, c.city, c.state, c.id].join(' ').toLowerCase();
    return hay.includes(q);
  });
  out.sort((a, b) => this.compare(a, b, this.sort.id, this.sort.dir));
  return out;
};
CompaniesView.prototype.compare = function (a, b, col, dir) {
  const sign = dir === 'desc' ? -1 : 1;
  const va = this.sortKey(a, col), vb = this.sortKey(b, col);
  if (va == null && vb == null) return 0;
  if (va == null) return 1;
  if (vb == null) return -1;
  if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * sign;
  return String(va).localeCompare(String(vb), undefined, { sensitivity: 'base' }) * sign;
};
CompaniesView.prototype.sortKey = function (c, col) {
  switch (col) {
    case 'name':     return (c.name || '').toLowerCase();
    case 'role':     return Number(c.role_id) != null ? Number(c.role_id) : 99;
    case 'users':    return Array.isArray(c.users) ? c.users.length : 0;
    case 'children': return Array.isArray(c.children) ? c.children.length : 0;
    case 'agents':   return Array.isArray(c.agents) ? c.agents.length : 0;
    case 'tokens':   return Number(c.token_balance) || 0;
    default: return '';
  }
};

// ─── Rendering — list view ───────────────────────────────────────────

CompaniesView.prototype.render = function () {
  this.container.innerHTML = '';
  if (this.view === 'detail') this.renderDetailShell();
  else                        this.renderListShell();
};

CompaniesView.prototype.renderListShell = function () {
  const root = document.createElement('div');
  root.className = 'co-root';
  this.headerEl = document.createElement('div'); this.headerEl.className = 'co-header'; root.appendChild(this.headerEl);
  this.errEl = document.createElement('div'); this.errEl.className = 'co-error'; this.errEl.hidden = true; root.appendChild(this.errEl);
  this.tableEl = document.createElement('div'); this.tableEl.className = 'co-table-wrap'; root.appendChild(this.tableEl);
  this.container.appendChild(root);
  this.renderHeader(); this.renderTable();
};

CompaniesView.prototype.renderHeader = function () {
  if (!this.headerEl) return;
  if (!this._tools) this._buildTools();
  this.headerEl.innerHTML = '';
  if (this.ctx && this.ctx.framed && typeof this.ctx.setHeaderActions === 'function') {
    if (!this._toolbarMounted) {
      const order = [this._tools.search, this._tools.refresh];
      if (this._tools.add) order.push(this._tools.add);
      this.ctx.setHeaderActions.apply(this.ctx, order);
      this._toolbarMounted = true;
    }
  } else {
    const row = document.createElement('div'); row.className = 'co-title-row';
    row.appendChild(this._tools.refresh);
    if (this._tools.add) row.appendChild(this._tools.add);
    row.appendChild(this._tools.search);
    this.headerEl.appendChild(row);
  }
};

CompaniesView.prototype._buildTools = function () {
  const tools = {};
  tools.refresh = document.createElement('button');
  tools.refresh.type = 'button'; tools.refresh.className = 'co-iconbtn';
  tools.refresh.title = 'Refresh'; tools.refresh.textContent = '↻';
  tools.refresh.addEventListener('click', () => this.refresh());

  if (this.roleId === 0 || this.roleId === 1) {
    tools.add = document.createElement('button');
    tools.add.type = 'button'; tools.add.className = 'co-primary'; tools.add.textContent = '+ New company';
    tools.add.addEventListener('click', () => this.openCreate());
  }

  tools.search = document.createElement('input');
  tools.search.type = 'search'; tools.search.placeholder = 'Search…';
  tools.search.value = this.search; tools.search.className = 'co-search';
  tools.search.addEventListener('input', (e) => { this.search = e.target.value; this.renderTable(); });

  this._tools = tools;
};

CompaniesView.prototype.renderTable = function () {
  if (!this.tableEl) return;
  const rows = this.filteredAndSorted();
  const headers = COMPANY_COLS.map((c) => {
    const sortable = c.sortable ? ' is-sortable' : '';
    const active = this.sort.id === c.id ? ' is-sorted' : '';
    const arrow = this.sort.id === c.id ? (this.sort.dir === 'asc' ? ' ▲' : ' ▼') : '';
    return '<th class="co-th' + sortable + active + '" data-col="' + c.id + '">' + escapeC(c.label) + escapeC(arrow) + '</th>';
  }).join('');

  const bodyRows = rows.length
    ? rows.map((c) => this.rowHtml(c)).join('')
    : '<tr><td colspan="' + COMPANY_COLS.length + '" class="co-empty">No companies.</td></tr>';

  this.tableEl.innerHTML =
    '<table class="co-table"><thead><tr>' + headers + '</tr></thead>' +
    '<tbody>' + bodyRows + '</tbody></table>';

  this.tableEl.querySelectorAll('.co-th.is-sortable').forEach((th) => {
    th.addEventListener('click', () => {
      const id = th.dataset.col;
      if (this.sort.id === id) this.sort.dir = this.sort.dir === 'asc' ? 'desc' : 'asc';
      else { this.sort.id = id; this.sort.dir = 'asc'; }
      writeJsonC('agixt.desktop.companies.sort.v1', this.sort);
      this.renderTable();
    });
  });

  const view = this;
  this.tableEl.querySelectorAll('button[data-action]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const id = btn.dataset.id;
      const action = btn.dataset.action;
      const c = view.companies.find((x) => x.id === id);
      if (!c) return;
      if (action === 'open') view.openDetail(c);
      else if (action === 'edit') view.openCompanyDialog({ mode: 'edit', company: c });
      else if (action === 'rotate') view.rotateKey(c);
      else if (action === 'delete') view.deleteCompany(c);
    });
  });
};

CompaniesView.prototype.rowHtml = function (c) {
  const role = c.role_id != null ? (ROLE_NAMES[c.role_id] || ('Role ' + c.role_id)) : '—';
  const tokens = c.token_balance != null
    ? Number(c.token_balance).toLocaleString() + (c.token_balance_usd != null ? ' (~$' + Number(c.token_balance_usd).toFixed(0) + ')' : '')
    : '';
  const agents = Array.isArray(c.agents) ? c.agents.length : 0;
  const users = Array.isArray(c.users) ? c.users.length : (c.user_count != null ? c.user_count : 0);
  const children = Array.isArray(c.children) ? c.children.length : (c.child_count != null ? c.child_count : 0);
  const canEdit = this.canEditRow(c);
  const actions = [];
  actions.push('<button data-action="open" data-id="' + escapeC(c.id) + '">Open</button>');
  if (canEdit) {
    actions.push('<button data-action="edit" data-id="' + escapeC(c.id) + '">Edit</button>');
    actions.push('<button data-action="rotate" data-id="' + escapeC(c.id) + '" title="Rotate API key">Rotate key</button>');
    if (this.roleId === 0 || this.roleId === 1) {
      actions.push('<button class="danger" data-action="delete" data-id="' + escapeC(c.id) + '">Delete</button>');
    }
  }
  return '<tr>' +
    '<td><div class="co-name">' + escapeC(c.name || '(unnamed)') +
      (c.primary ? ' <span class="co-pill">Primary</span>' : '') +
    '</div><div class="co-id">' + escapeC(c.id.slice(0, 8)) + '</div></td>' +
    '<td>' + (c.role_id != null ? '<span class="co-rolepill">' + escapeC(role) + '</span>' : '<span class="co-faint">' + escapeC(role) + '</span>') + '</td>' +
    '<td>' + users + '</td>' +
    '<td>' + (children > 0 ? children : '<span class="co-faint">—</span>') + '</td>' +
    '<td>' + agents + '</td>' +
    '<td>' + escapeC(tokens) + '</td>' +
    '<td>' + escapeC(c.phone_number || '') + '</td>' +
    '<td>' + escapeC(c.email || '') + '</td>' +
    '<td>' + (c.website ? '<code>' + escapeC(c.website) + '</code>' : '') + '</td>' +
    '<td class="co-actions">' + actions.join('') + '</td>' +
  '</tr>';
};

// ─── Rendering — detail view (the "Manage in detail" page) ───────────

CompaniesView.prototype.renderDetailShell = function () {
  const root = document.createElement('div'); root.className = 'co-root co-detail-root';
  this.detailHeaderEl = document.createElement('div'); this.detailHeaderEl.className = 'co-detail-header';
  root.appendChild(this.detailHeaderEl);
  this.detailErrEl = document.createElement('div'); this.detailErrEl.className = 'co-error'; this.detailErrEl.hidden = true;
  this.detailErrEl.style.cssText = 'margin: 0 20px;';
  root.appendChild(this.detailErrEl);
  this.detailBodyEl = document.createElement('div'); this.detailBodyEl.className = 'co-detail-body';
  root.appendChild(this.detailBodyEl);
  this.container.appendChild(root);
  this.renderDetailHeader();
  this.renderDetailBody();
};

CompaniesView.prototype.renderDetailHeader = function () {
  if (!this.detailHeaderEl) return;
  this.detailHeaderEl.innerHTML = '';
  const back = document.createElement('button');
  back.type = 'button'; back.className = 'co-iconbtn'; back.textContent = '←';
  back.title = 'Back to list';
  back.addEventListener('click', () => this.backToList());
  this.detailHeaderEl.appendChild(back);
  const c = this.detail.company;
  const title = document.createElement('div'); title.className = 'co-detail-title';
  title.textContent = c ? (c.name || '(unnamed)') : 'Loading…';
  this.detailHeaderEl.appendChild(title);

  if (c && this.canAdminCompany(c)) {
    const actions = document.createElement('div');
    actions.style.cssText = 'margin-left:auto;display:flex;gap:8px;flex-wrap:wrap;';
    const inviteBtn = document.createElement('button');
    inviteBtn.type = 'button'; inviteBtn.className = 'co-primary'; inviteBtn.textContent = '+ Invite users';
    inviteBtn.addEventListener('click', () => this.openInviteDialog(c));
    actions.appendChild(inviteBtn);

    const rolesBtn = document.createElement('button');
    rolesBtn.type = 'button'; rolesBtn.className = 'co-secondary'; rolesBtn.textContent = 'Custom roles';
    rolesBtn.addEventListener('click', () => this.openCustomRolesDialog(c));
    actions.appendChild(rolesBtn);

    const editBtn = document.createElement('button');
    editBtn.type = 'button'; editBtn.className = 'co-secondary'; editBtn.textContent = 'Edit company';
    editBtn.addEventListener('click', () => this.openCompanyDialog({ mode: 'edit', company: c }));
    actions.appendChild(editBtn);

    this.detailHeaderEl.appendChild(actions);
  }
};

CompaniesView.prototype.renderDetailBody = function () {
  this.renderDetailHeader();
  if (!this.detailBodyEl) return;
  this.detailBodyEl.innerHTML = '';
  const c = this.detail.company;
  if (!c) { this.detailBodyEl.appendChild(makeFaintC('Loading…')); return; }
  if (this.detail.loading) { this.detailBodyEl.appendChild(makeFaintC('Loading…')); return; }

  // Company info card
  this.detailBodyEl.appendChild(this.buildCompanyInfoCard(c));
  // Members card (with invitations subsection above when admin)
  this.detailBodyEl.appendChild(this.buildMembersCard(c));
  // Custom roles summary
  if (this.canAdminCompany(c)) {
    this.detailBodyEl.appendChild(this.buildCustomRolesSummary(c));
  }
  // Agents card (kept from original)
  if (Array.isArray(c.agents) && c.agents.length) {
    const ac = makeCardC('Agents');
    ac._body.appendChild(makeTableC(['Name', 'Default', 'ID'], c.agents.map((a) => [
      a.name || '(unnamed)',
      a.default ? '✓' : '',
      (a.id || '').slice(0, 8),
    ])));
    this.detailBodyEl.appendChild(ac);
  }
};

CompaniesView.prototype.buildCompanyInfoCard = function (c) {
  const card = makeCardC('Company info');
  card._body.appendChild(makeKvC([
    ['ID',          c.id, { mono: true }],
    ['Name',        c.name],
    ['Your role',   ROLE_NAMES[c.role_id] || '—'],
    ['Status',      c.status === false ? 'Inactive' : 'Active'],
    ['Agents',      Array.isArray(c.agents) ? String(c.agents.length) : '0'],
    ['Token balance', c.token_balance != null ? Number(c.token_balance).toLocaleString() : null],
    ['Address',     c.address],
    ['City',        c.city],
    ['State',       c.state],
    ['Zip',         c.zip_code],
    ['Country',     c.country],
    ['Phone',       c.phone_number],
    ['Email',       c.email],
    ['Website',     c.website, { mono: true }],
    ['Notes',       c.notes],
  ].filter((r) => r && r[1] != null && r[1] !== '')));
  return card;
};

CompaniesView.prototype.buildMembersCard = function (c) {
  const members = this.detail.members || [];
  const invitations = this.detail.invitations || [];
  const roleNames = this.roleNameLookup();
  const isAdmin = this.canAdminCompany(c);

  // Role distribution pills
  const roleCounts = {};
  members.forEach((m) => { roleCounts[m.role_id] = (roleCounts[m.role_id] || 0) + 1; });
  const pillsHtml = Object.keys(roleCounts).map((id) =>
    '<span class="co-stat-pill">' + roleCounts[id] + ' · ' + escapeC(roleNames[id] || ('Role ' + id)) + '</span>'
  ).join('');

  const card = makeCardC('Members', members.length + ' member(s)');
  const body = card._body;

  // Pending invitations subsection
  if (invitations.length && isAdmin) {
    const invHead = document.createElement('div');
    invHead.className = 'co-subsection-head';
    invHead.textContent = 'Pending invitations (' + invitations.length + ')';
    body.appendChild(invHead);
    const invList = document.createElement('div');
    invList.className = 'co-row-list';
    invitations.forEach((inv) => {
      invList.appendChild(this.buildInvitationRow(c, inv, roleNames));
    });
    body.appendChild(invList);
  }

  // Members subsection header (with stats + export)
  const memHead = document.createElement('div');
  memHead.className = 'co-subsection-head';
  memHead.style.cssText = 'display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-top:' + (invitations.length && isAdmin ? '16px' : '0') + ';';
  const memHeadLeft = document.createElement('div');
  memHeadLeft.innerHTML = 'Team members' + (pillsHtml ? ' <span class="co-stat-pills">' + pillsHtml + '</span>' : '');
  memHead.appendChild(memHeadLeft);
  const exportBtn = document.createElement('button');
  exportBtn.type = 'button'; exportBtn.className = 'co-iconbtn'; exportBtn.textContent = '↓ CSV';
  exportBtn.title = 'Export members to CSV';
  exportBtn.style.cssText = 'width:auto;padding:0 10px;';
  exportBtn.disabled = !members.length;
  exportBtn.addEventListener('click', () => exportMembersCsv(members, roleNames, c.name));
  memHead.appendChild(exportBtn);
  body.appendChild(memHead);

  // Search filter
  const filterRow = document.createElement('div');
  filterRow.className = 'co-filter-bar';
  const searchInput = document.createElement('input');
  searchInput.type = 'search';
  searchInput.placeholder = 'Search members by name or email…';
  searchInput.className = 'co-search';
  searchInput.value = this.detail.memberFilter || '';
  filterRow.appendChild(searchInput);
  body.appendChild(filterRow);

  // Bulk action bar
  const selectedIds = new Set();
  const bulkBar = document.createElement('div');
  bulkBar.className = 'co-bulk-bar';
  bulkBar.hidden = true;
  body.appendChild(bulkBar);

  const memberList = document.createElement('div');
  memberList.className = 'co-row-list';
  body.appendChild(memberList);

  const view = this;
  function rebuildBulkBar() {
    bulkBar.innerHTML = '';
    bulkBar.hidden = selectedIds.size === 0;
    if (selectedIds.size === 0) return;
    const count = document.createElement('span');
    count.className = 'co-bulk-bar-count';
    count.textContent = selectedIds.size + ' selected';
    bulkBar.appendChild(count);
    view.assignableDefaultRoles().forEach((r) => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'co-chip-action';
      b.textContent = 'Set: ' + (r.friendly_name || r.name);
      b.addEventListener('click', async () => {
        await view.bulkSetRole(Array.from(selectedIds), r.id, c.id);
        selectedIds.clear();
        view.loadDetailData().then(() => view.renderDetailBody());
      });
      bulkBar.appendChild(b);
    });
    const expBtn = document.createElement('button');
    expBtn.type = 'button'; expBtn.className = 'co-chip-action';
    expBtn.textContent = 'Export selected';
    expBtn.addEventListener('click', () => {
      const subset = members.filter((m) => selectedIds.has(m.id));
      exportMembersCsv(subset, roleNames, c.name);
    });
    bulkBar.appendChild(expBtn);
    const rmBtn = document.createElement('button');
    rmBtn.type = 'button'; rmBtn.className = 'co-chip-action danger';
    rmBtn.textContent = 'Remove selected';
    rmBtn.addEventListener('click', async () => {
      const ok = await confirmDialog({
        title: 'Remove members',
        message: 'Remove ' + selectedIds.size + ' member(s) from ' + (c.name || 'this company') + '? They lose access immediately.',
        confirmLabel: 'Remove',
        destructive: true,
      });
      if (!ok) return;
      await view.bulkRemoveMembers(Array.from(selectedIds), c.id);
      selectedIds.clear();
      view.loadDetailData().then(() => view.renderDetailBody());
    });
    bulkBar.appendChild(rmBtn);
  }

  function renderRows() {
    memberList.innerHTML = '';
    const filter = (view.detail.memberFilter || '').toLowerCase();
    const filtered = filter
      ? members.filter((m) => memberMatchesFilter(m, filter))
      : members;
    if (!filtered.length) {
      const empty = document.createElement('div');
      empty.className = 'co-faint';
      empty.style.cssText = 'padding:14px;text-align:center;';
      empty.textContent = members.length
        ? 'No members match "' + view.detail.memberFilter + '".'
        : 'No members yet.';
      memberList.appendChild(empty);
      return;
    }
    filtered.forEach((m) => memberList.appendChild(
      view.buildMemberRow(c, m, roleNames, isAdmin, selectedIds, rebuildBulkBar)
    ));
  }

  searchInput.addEventListener('input', () => {
    view.detail.memberFilter = searchInput.value;
    renderRows();
  });

  renderRows();
  return card;
};

CompaniesView.prototype.buildInvitationRow = function (c, inv, roleNames) {
  const roleLabel = roleNames[inv.role_id] || inv.role || ('Role ' + (inv.role_id != null ? inv.role_id : '—'));
  const inviteLink = inv.invitation_link || buildInviteLink(inv.id, inv.email || inv.invitee_email, this.ctx);
  const row = document.createElement('div');
  row.className = 'co-list-item';
  const statusBadge = inv.is_accepted
    ? '<span class="co-badge success">Accepted</span>'
    : '<span class="co-badge warn">Pending</span>';

  const grow = document.createElement('div');
  grow.className = 'co-list-item-grow';
  grow.innerHTML =
    '<div class="co-list-item-title">' + escapeC(inv.email || inv.invitee_email || '—') + ' ' + statusBadge + '</div>' +
    '<div class="co-list-item-meta">Role: ' + escapeC(roleLabel) +
      (inv.created_at ? ' · invited ' + escapeC(formatRelativeC(inv.created_at)) : '') + '</div>';
  row.appendChild(grow);

  const actions = document.createElement('div');
  actions.className = 'co-row-actions';
  const view = this;
  if (inviteLink) {
    const copyBtn = document.createElement('button');
    copyBtn.type = 'button'; copyBtn.className = 'co-chip-action';
    copyBtn.textContent = 'Copy link';
    copyBtn.addEventListener('click', () => {
      copyToClipboard(inviteLink);
      toastInfo('Invite link copied');
    });
    actions.appendChild(copyBtn);
  }
  if (!inv.is_accepted) {
    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button'; cancelBtn.className = 'co-chip-action danger';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.addEventListener('click', async () => {
      const ok = await confirmDialog({
        title: 'Cancel invitation',
        message: 'Cancel the invitation to ' + (inv.email || inv.invitee_email || '?') + '?',
        confirmLabel: 'Cancel invitation',
        cancelLabel: 'Keep',
        destructive: true,
      });
      if (!ok) return;
      try {
        await view.fetchJson('/v1/invitation/' + encodeURIComponent(inv.id), { method: 'DELETE' });
        await view.loadDetailData();
        view.renderDetailBody();
      } catch (err) { view.renderError(err); }
    });
    actions.appendChild(cancelBtn);
  }
  row.appendChild(actions);
  return row;
};

CompaniesView.prototype.buildMemberRow = function (c, m, roleNames, isAdmin, selectedIds, rebuildBulkBar) {
  const isProtected = m.role_id === 0 || m.role_id === 1 || m.role_id === 4;
  const isSelf = m.id === this.userId;
  const canSelect = isAdmin && !isProtected && !isSelf;
  const view = this;

  const row = document.createElement('div');
  row.className = 'co-list-item';
  if (selectedIds.has(m.id)) row.classList.add('is-selected');

  // Selection checkbox
  if (isAdmin) {
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.disabled = !canSelect;
    checkbox.checked = selectedIds.has(m.id);
    checkbox.addEventListener('change', () => {
      if (checkbox.checked) selectedIds.add(m.id);
      else selectedIds.delete(m.id);
      row.classList.toggle('is-selected', checkbox.checked);
      rebuildBulkBar();
    });
    row.appendChild(checkbox);
  }

  // Grow section: name, email, custom-role chips
  const grow = document.createElement('div');
  grow.className = 'co-list-item-grow';
  const displayName = ((m.first_name || '') + ' ' + (m.last_name || '')).trim() || m.email;
  const titleEl = document.createElement('div');
  titleEl.className = 'co-list-item-title';
  titleEl.innerHTML = escapeC(displayName) + ' ' +
    (isProtected ? '<span class="co-badge warn">' + escapeC(roleNames[m.role_id] || m.role || 'system') + '</span> ' : '') +
    (isSelf ? '<span class="co-badge muted">You</span>' : '');
  grow.appendChild(titleEl);
  const metaEl = document.createElement('div');
  metaEl.className = 'co-list-item-meta';
  metaEl.textContent = m.email || '';
  grow.appendChild(metaEl);

  // Custom role chips
  const memberCustomRoles = this.detail.customRolesPerUser[m.id] || [];
  const customRoleById = {};
  (this.detail.customRoles || []).forEach((r) => { if (r && r.id) customRoleById[r.id] = r; });
  const chipRow = document.createElement('div');
  chipRow.className = 'co-list-item-meta';
  chipRow.style.cssText = 'display:flex;flex-wrap:wrap;gap:4px;align-items:center;';
  memberCustomRoles.forEach((assignment) => {
    const role = assignment.custom_role || customRoleById[assignment.custom_role_id] || null;
    const customRoleId = (role && role.id) || assignment.custom_role_id;
    const label = (role && (role.friendly_name || role.name)) || 'Custom role';
    const chip = document.createElement('span');
    chip.className = 'co-custom-role-chip';
    chip.textContent = label;
    if (isAdmin) {
      const x = document.createElement('button');
      x.type = 'button'; x.title = 'Remove role'; x.textContent = '×';
      x.addEventListener('click', async () => {
        if (!customRoleId) return;
        try {
          await view.fetchJson(
            '/v1/user/' + encodeURIComponent(m.id) + '/custom-role/' + encodeURIComponent(customRoleId)
              + '?company_id=' + encodeURIComponent(c.id),
            { method: 'DELETE' });
          await view.loadDetailData();
          view.renderDetailBody();
        } catch (err) { view.renderError(err); }
      });
      chip.appendChild(x);
    }
    chipRow.appendChild(chip);
  });
  if (isAdmin && (this.detail.customRoles || []).length) {
    const addBtn = document.createElement('button');
    addBtn.type = 'button'; addBtn.className = 'co-chip-btn'; addBtn.textContent = '+ Custom role';
    addBtn.addEventListener('click', () => view.openAssignCustomRolePicker(c, m));
    chipRow.appendChild(addBtn);
  }
  if (chipRow.childNodes.length) grow.appendChild(chipRow);
  row.appendChild(grow);

  // Actions column: role select + details + remove
  const actions = document.createElement('div');
  actions.className = 'co-row-actions';
  if (isAdmin) {
    const roleSelect = document.createElement('select');
    roleSelect.className = 'co-select';
    const opts = view.assignableDefaultRoles();
    opts.forEach((r) => {
      const o = document.createElement('option');
      o.value = String(r.id); o.textContent = r.friendly_name || r.name;
      roleSelect.appendChild(o);
    });
    if (isProtected && !opts.find((r) => r.id === m.role_id)) {
      const o = document.createElement('option');
      o.value = String(m.role_id);
      o.textContent = roleNames[m.role_id] || m.role || ('Role ' + m.role_id);
      roleSelect.appendChild(o);
    }
    roleSelect.value = String(m.role_id);
    roleSelect.disabled = isProtected;
    roleSelect.addEventListener('change', async () => {
      const next = Number(roleSelect.value);
      if (next === m.role_id) return;
      try {
        await view.fetchJson('/v1/user/role', {
          method: 'PUT',
          json: { role_id: next, company_id: c.id, user_id: m.id },
        });
        m.role_id = next;
        await view.loadDetailData();
        view.renderDetailBody();
      } catch (err) {
        view.renderError(err);
        roleSelect.value = String(m.role_id);
      }
    });
    actions.appendChild(roleSelect);

    const detailsBtn = document.createElement('button');
    detailsBtn.type = 'button'; detailsBtn.className = 'co-chip-action';
    detailsBtn.textContent = 'Details';
    detailsBtn.addEventListener('click', () => view.openMemberDetailsDialog(c, m));
    actions.appendChild(detailsBtn);

    if (!isProtected && !isSelf) {
      const removeBtn = document.createElement('button');
      removeBtn.type = 'button'; removeBtn.className = 'co-chip-action danger';
      removeBtn.textContent = 'Remove';
      removeBtn.addEventListener('click', async () => {
        const ok = await confirmDialog({
          title: 'Remove member',
          message: 'Remove ' + (m.email || displayName) + ' from ' + (c.name || 'this company') + '?',
          confirmLabel: 'Remove',
          destructive: true,
        });
        if (!ok) return;
        try {
          await view.fetchJson('/v1/companies/' + encodeURIComponent(c.id)
            + '/users/' + encodeURIComponent(m.id), { method: 'DELETE' });
          await view.loadDetailData();
          view.renderDetailBody();
        } catch (err) { view.renderError(err); }
      });
      actions.appendChild(removeBtn);
    }
  } else {
    // Non-admin: just show the role label
    actions.appendChild((function () {
      const span = document.createElement('span');
      span.className = 'co-rolepill';
      span.textContent = roleNames[m.role_id] || ('Role ' + m.role_id);
      return span;
    })());
  }
  row.appendChild(actions);
  return row;
};

CompaniesView.prototype.buildCustomRolesSummary = function (c) {
  const list = this.detail.customRoles || [];
  const card = makeCardC('Custom roles', list.length
    ? list.length + ' custom role(s) defined'
    : 'No custom roles defined yet — bundle scopes into reusable permission sets and assign them on top of default roles.');
  const view = this;
  if (list.length) {
    const wrap = document.createElement('div');
    wrap.className = 'co-row-list';
    list.slice(0, 6).forEach((r) => {
      const item = document.createElement('div');
      item.className = 'co-list-item';
      item.innerHTML =
        '<div class="co-list-item-grow">' +
          '<div class="co-list-item-title">' + escapeC(r.friendly_name || r.name) +
            (r.is_active === false ? ' <span class="co-badge muted">Inactive</span>' : '') + '</div>' +
          '<div class="co-list-item-meta">' +
            (r.description ? escapeC(r.description) + ' · ' : '') +
            ((r.scopes && r.scopes.length) || 0) + ' permission(s)' +
          '</div>' +
        '</div>';
      card._body.appendChild(item);
    });
    if (list.length > 6) {
      const more = document.createElement('div');
      more.className = 'co-faint';
      more.style.cssText = 'padding:4px 0 8px;font-size:11.5px;';
      more.textContent = 'And ' + (list.length - 6) + ' more…';
      card._body.appendChild(more);
    }
  }
  const manageBtn = document.createElement('button');
  manageBtn.type = 'button'; manageBtn.className = 'co-primary';
  manageBtn.textContent = list.length ? 'Manage custom roles' : 'Create custom role';
  manageBtn.style.cssText = 'margin-top:8px;';
  manageBtn.addEventListener('click', () => view.openCustomRolesDialog(c));
  card._body.appendChild(manageBtn);
  return card;
};

// ─── Bulk actions ────────────────────────────────────────────────────

CompaniesView.prototype.bulkSetRole = async function (userIds, roleId, companyId) {
  const results = await Promise.allSettled(userIds.map((uid) =>
    this.fetchJson('/v1/user/role', {
      method: 'PUT',
      json: { role_id: roleId, company_id: companyId, user_id: uid },
    })));
  const ok = results.filter((r) => r.status === 'fulfilled').length;
  const failed = results.length - ok;
  if (failed) this.renderError(new Error('Updated ' + ok + ', ' + failed + ' failed'));
  else this.renderError(null);
};
CompaniesView.prototype.bulkRemoveMembers = async function (userIds, companyId) {
  const results = await Promise.allSettled(userIds.map((uid) =>
    this.fetchJson('/v1/companies/' + encodeURIComponent(companyId)
      + '/users/' + encodeURIComponent(uid), { method: 'DELETE' })));
  const ok = results.filter((r) => r.status === 'fulfilled').length;
  const failed = results.length - ok;
  if (failed) this.renderError(new Error('Removed ' + ok + ', ' + failed + ' failed'));
  else this.renderError(null);
};

// ─── Company create/edit dialog ──────────────────────────────────────

CompaniesView.prototype.openCompanyDialog = function (opts) {
  opts = opts || {};
  const mode = opts.mode === 'create' ? 'create' : 'edit';
  const company = opts.company || {};
  const view = this;
  const allCompanies = this.companies || [];

  const fields = {
    name: fieldInput('Company name *', { value: company.name || '', placeholder: 'Enter company name' }),
    email: fieldInput('Email', { type: 'email', value: company.email || '', placeholder: 'company@example.com' }),
    phone: fieldInput('Phone', { type: 'tel', value: company.phone_number || '', placeholder: '+1 (555) 123-4567' }),
    website: fieldInput('Website', { type: 'url', value: company.website || '', placeholder: 'https://company.com' }),
    address: fieldInput('Street address', { value: company.address || '', placeholder: '123 Main Street' }),
    city: fieldInput('City', { value: company.city || '', placeholder: 'New York' }),
    state: fieldInput('State/Province', { value: company.state || '', placeholder: 'NY' }),
    zip: fieldInput('ZIP/Postal code', { value: company.zip_code || '', placeholder: '10001' }),
    country: fieldInput('Country', { value: company.country || '', placeholder: 'United States' }),
    notes: fieldInput('Notes', { type: 'textarea', value: company.notes || '', placeholder: 'Additional notes about this company…' }),
  };
  const statusSelect = document.createElement('select');
  statusSelect.className = 'co-select';
  statusSelect.innerHTML = '<option value="active">Active</option><option value="inactive">Inactive</option>';
  statusSelect.value = (company.status === false ? 'inactive' : 'active');
  const statusWrap = wrapField('Status', statusSelect);

  let parentSelect = null, parentWrap = null;
  if (mode === 'create' && allCompanies.length) {
    parentSelect = document.createElement('select');
    parentSelect.className = 'co-select';
    parentSelect.innerHTML = '<option value="">None (top-level company)</option>' +
      allCompanies.map((c) => '<option value="' + escapeC(c.id) + '">' + escapeC(c.name || 'Untitled') + '</option>').join('');
    parentWrap = wrapField('Parent company', parentSelect);
  }

  const submitBtn = button(mode === 'create' ? 'Create company' : 'Save changes', { kind: 'primary' });
  const cancelBtn = button('Cancel');

  const handle = openModal({
    title: mode === 'create' ? 'Create company' : 'Edit company',
    description: mode === 'create'
      ? 'Spin up a new company. All fields except the name are optional and can be edited later.'
      : 'Update company information for ' + (company.name || ''),
    wide: true,
    body: [
      gridRow([fields.name.wrap, statusWrap]),
      gridRow([fields.email.wrap, fields.phone.wrap]),
      fields.website.wrap,
      fields.address.wrap,
      gridRow([fields.city.wrap, fields.state.wrap]),
      gridRow([fields.zip.wrap, fields.country.wrap]),
      parentWrap,
      fields.notes.wrap,
    ].filter(Boolean),
    footer: [cancelBtn, submitBtn],
  });
  cancelBtn.addEventListener('click', () => handle.close());
  submitBtn.addEventListener('click', async () => {
    const finalName = fields.name.input.value.trim();
    if (!finalName) {
      toastError('Company name is required');
      fields.name.input.focus();
      return;
    }
    const payload = {
      name: finalName,
      status: statusSelect.value === 'active',
      address: fields.address.input.value.trim() || null,
      phone_number: fields.phone.input.value.trim() || null,
      email: fields.email.input.value.trim() || null,
      website: fields.website.input.value.trim() || null,
      city: fields.city.input.value.trim() || null,
      state: fields.state.input.value.trim() || null,
      zip_code: fields.zip.input.value.trim() || null,
      country: fields.country.input.value.trim() || null,
      notes: fields.notes.input.value.trim() || null,
    };
    if (mode === 'create' && parentSelect && parentSelect.value) {
      payload.parent_company_id = parentSelect.value;
    }
    submitBtn.disabled = true;
    try {
      if (mode === 'create') {
        await view.fetchJson('/v1/companies', { method: 'POST', json: payload });
      } else {
        await view.fetchJson('/v1/companies/' + encodeURIComponent(company.id), {
          method: 'PATCH', json: payload,
        });
      }
      handle.close();
      await view.refresh();
    } catch (err) {
      view.renderError(err);
      toastError(friendlyError(err));
      submitBtn.disabled = false;
    }
  });
  focusFirstInput(handle);
};

// ─── Invite users dialog ─────────────────────────────────────────────

CompaniesView.prototype.openInviteDialog = function (c) {
  const view = this;
  const assignable = this.assignableDefaultRoles();

  const emails = document.createElement('textarea');
  emails.className = 'co-input co-textarea';
  emails.rows = 4;
  emails.placeholder = 'user1@example.com user2@example.com\nuser3@example.com';
  const emailsWrap = wrapField('Email addresses', emails,
    'Separate multiple emails with spaces, commas, or new lines.');

  const roleSel = document.createElement('select');
  roleSel.className = 'co-select';
  assignable.forEach((r) => {
    const opt = document.createElement('option');
    opt.value = String(r.id);
    opt.textContent = r.friendly_name || r.name;
    roleSel.appendChild(opt);
  });
  if (Array.from(roleSel.options).some((o) => o.value === '3')) roleSel.value = '3';
  const roleWrap = wrapField('Assign role', roleSel);

  const skipEmail = document.createElement('input');
  skipEmail.type = 'checkbox';
  const skipWrap = document.createElement('label');
  skipWrap.className = 'co-check';
  skipWrap.appendChild(skipEmail);
  const skipText = document.createElement('span');
  skipText.textContent = 'Create invite link only (don’t send email)';
  skipWrap.appendChild(skipText);

  const resultsEl = document.createElement('div');
  resultsEl.className = 'co-invite-results';
  resultsEl.hidden = true;
  const statusLine = document.createElement('p');
  statusLine.className = 'co-status-line';

  const cancelBtn = button('Close');
  const sendBtn = button('Send invitations', { kind: 'primary' });

  function refreshSendLabel() {
    const count = parseEmails(emails.value).length;
    sendBtn.textContent = count
      ? 'Send ' + count + ' invitation' + (count === 1 ? '' : 's')
      : 'Send invitations';
    sendBtn.disabled = count === 0;
  }
  emails.addEventListener('input', refreshSendLabel);
  refreshSendLabel();

  const handle = openModal({
    title: 'Invite team members',
    description: 'Inviting to ' + (c.name || 'company') + '. Multiple emails are sent in parallel.',
    wide: true,
    body: [emailsWrap, roleWrap, skipWrap, resultsEl, statusLine],
    footer: [cancelBtn, sendBtn],
  });
  cancelBtn.addEventListener('click', () => handle.close());

  sendBtn.addEventListener('click', async () => {
    resultsEl.innerHTML = '';
    resultsEl.hidden = true;
    const list = parseEmails(emails.value);
    if (!list.length) {
      statusLine.textContent = 'Enter at least one valid email.';
      statusLine.className = 'co-status-line error';
      emails.focus();
      return;
    }
    sendBtn.disabled = true;
    statusLine.textContent = 'Sending ' + list.length + ' invitation(s)…';
    statusLine.className = 'co-status-line';
    const results = await Promise.all(list.map(async (addr) => {
      try {
        const resp = await view.fetchJson('/v1/invitations', {
          method: 'POST',
          json: {
            email: addr,
            company_id: c.id,
            role_id: Number(roleSel.value),
            skip_email: !!skipEmail.checked,
          },
        });
        const id = resp && resp.id;
        const alreadyMember = id === 'none' || (resp && resp.is_accepted === true);
        const link = alreadyMember ? null : (resp && resp.invitation_link)
          || buildInviteLink(id, addr, view.ctx);
        return {
          email: addr, success: true, alreadyMember,
          message: alreadyMember
            ? 'User added to company (already registered)'
            : (skipEmail.checked ? 'Invite link created' : 'Invitation sent'),
          link,
        };
      } catch (err) {
        return {
          email: addr, success: false,
          status: err && err.status,
          message: friendlyError(err, 'inviting ' + addr),
        };
      }
    }));
    resultsEl.hidden = false;
    results.forEach((r) => {
      const row = document.createElement('div');
      row.className = 'co-invite-result ' + (r.success ? 'success' : 'error');
      const head = document.createElement('div');
      head.className = 'co-invite-result-head';
      head.innerHTML = (r.success ? '✓' : '✗') + ' <strong>' + escapeC(r.email) + '</strong>';
      row.appendChild(head);
      if (r.link) {
        const link = document.createElement('div');
        link.className = 'co-invite-result-link';
        const a = document.createElement('a');
        a.href = r.link;
        a.textContent = r.link;
        a.target = '_blank'; a.rel = 'noopener noreferrer';
        link.appendChild(a);
        const copy = button('Copy', { onclick: () => { copyToClipboard(r.link); toastInfo('Copied'); } });
        link.appendChild(copy);
        row.appendChild(link);
      } else {
        const msg = document.createElement('div');
        msg.className = 'co-invite-result-msg' + (r.success ? '' : ' error');
        msg.textContent = r.message;
        row.appendChild(msg);
      }
      resultsEl.appendChild(row);
    });
    const okCount = results.filter((r) => r.success).length;
    const failCount = results.length - okCount;
    const hitBilling = results.some((r) => !r.success && r.status === 402);
    if (hitBilling) {
      statusLine.textContent = 'User limit reached — upgrade your plan to invite more.';
      statusLine.className = 'co-status-line error';
    } else if (failCount === 0) {
      statusLine.textContent = 'Sent ' + okCount + ' invitation(s).';
      statusLine.className = 'co-status-line success';
      emails.value = '';
    } else if (okCount === 0) {
      statusLine.textContent = 'Failed to send ' + failCount + ' invitation(s).';
      statusLine.className = 'co-status-line error';
    } else {
      statusLine.textContent = 'Sent ' + okCount + ', ' + failCount + ' failed.';
      statusLine.className = 'co-status-line';
    }
    refreshSendLabel();
    await view.loadDetailData();
    view.renderDetailBody();
  });
  focusFirstInput(handle);
};

// ─── Custom roles management ─────────────────────────────────────────

CompaniesView.prototype.openCustomRolesDialog = async function (c) {
  const view = this;
  const listEl = document.createElement('div');
  listEl.className = 'co-row-list';
  listEl.appendChild(makeFaintC('Loading roles…'));
  const createBtn = button('+ New custom role', { kind: 'primary' });
  const closeBtn = button('Close');

  const handle = openModal({
    title: 'Custom roles — ' + (c.name || 'Company'),
    description: 'Custom roles let you bundle scopes into reusable permission sets, then assign them to users on top of their default role.',
    wide: true,
    body: [
      (function () {
        const row = document.createElement('div');
        row.style.cssText = 'display:flex;justify-content:flex-end;';
        row.appendChild(createBtn);
        return row;
      })(),
      listEl,
    ],
    footer: [closeBtn],
  });
  closeBtn.addEventListener('click', () => handle.close());

  let scopesCache = null;
  async function loadScopes() {
    if (!scopesCache) {
      try {
        const data = await view.fetchJson('/v1/scopes');
        scopesCache = (data && (data.scopes || data)) || [];
      } catch (_) { scopesCache = []; }
    }
    return scopesCache;
  }

  async function refresh() {
    listEl.innerHTML = '';
    listEl.appendChild(makeFaintC('Loading roles…'));
    let roles;
    try {
      const data = await view.fetchJson('/v1/roles?company_id=' + encodeURIComponent(c.id));
      roles = (data && data.roles) || [];
    } catch (err) {
      listEl.innerHTML = '';
      const errDiv = document.createElement('div');
      errDiv.className = 'co-error';
      errDiv.textContent = friendlyError(err);
      listEl.appendChild(errDiv);
      return;
    }
    listEl.innerHTML = '';
    if (!roles.length) {
      listEl.appendChild(makeFaintC('No custom roles yet. Click "+ New custom role" to add one.'));
      return;
    }
    roles.forEach((r) => listEl.appendChild(buildRoleCard(r)));
  }

  function buildRoleCard(r) {
    const card = document.createElement('div');
    card.className = 'co-role-card' + (r.is_active === false ? ' inactive' : '');
    const grow = document.createElement('div');
    grow.className = 'co-role-card-grow';
    grow.innerHTML =
      '<div class="co-role-card-title">' + escapeC(r.friendly_name || r.name) +
        (r.is_active === false ? ' <span class="co-badge muted">Inactive</span>' : '') + '</div>' +
      (r.description ? '<div class="co-role-card-desc">' + escapeC(r.description) + '</div>' : '') +
      '<div class="co-role-card-desc">Slug: <code>' + escapeC(r.name || '') + '</code>' +
        ' · Priority: ' + (r.priority == null ? '100' : r.priority) +
        ' · ' + ((r.scopes && r.scopes.length) || 0) + ' permission(s)</div>';
    if (r.scopes && r.scopes.length) {
      const scopes = document.createElement('div');
      scopes.className = 'co-role-card-scopes';
      r.scopes.slice(0, 12).forEach((s) => {
        const c = document.createElement('code'); c.textContent = s.name; scopes.appendChild(c);
      });
      grow.appendChild(scopes);
    }
    card.appendChild(grow);

    const actions = document.createElement('div');
    actions.className = 'co-role-card-actions';
    const editBtn = button('Edit', { onclick: async () => {
      const scopes = await loadScopes();
      view.openRoleEditor(c.id, r, scopes, async () => { await refresh(); await view.loadDetailData(); view.renderDetailBody(); });
    } });
    const delBtn = button('Delete', { kind: 'danger', onclick: async () => {
      const ok = await confirmDialog({
        title: 'Delete custom role',
        message: 'Delete "' + (r.friendly_name || r.name) + '"? Users assigned to this role lose its permissions immediately.',
        confirmLabel: 'Delete role',
        destructive: true,
      });
      if (!ok) return;
      try {
        await view.fetchJson('/v1/roles/' + encodeURIComponent(r.id), { method: 'DELETE' });
        await refresh();
        await view.loadDetailData();
        view.renderDetailBody();
      } catch (err) { toastError(friendlyError(err)); }
    } });
    actions.appendChild(editBtn);
    actions.appendChild(delBtn);
    card.appendChild(actions);
    return card;
  }

  createBtn.addEventListener('click', async () => {
    const scopes = await loadScopes();
    view.openRoleEditor(c.id, null, scopes, async () => { await refresh(); await view.loadDetailData(); view.renderDetailBody(); });
  });

  refresh();
  focusFirstInput(handle, { focusSelector: '.co-primary' });
};

CompaniesView.prototype.openRoleEditor = function (companyId, existing, allScopes, onSaved) {
  const view = this;
  const isEdit = !!existing;

  const friendly = fieldInput('Display name *', {
    value: existing ? (existing.friendly_name || '') : '',
    placeholder: 'e.g. Billing Manager',
  });
  const slug = fieldInput('Slug (lowercase, no spaces) *', {
    value: existing ? (existing.name || '') : '',
    placeholder: 'e.g. billing_manager',
  });
  if (isEdit) slug.input.disabled = true;

  let slugManuallyEdited = isEdit;
  function slugify(s) {
    return String(s || '').toLowerCase().trim()
      .replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  }
  if (!isEdit) {
    friendly.input.addEventListener('input', () => {
      if (!slugManuallyEdited) slug.input.value = slugify(friendly.input.value);
    });
    slug.input.addEventListener('input', () => { slugManuallyEdited = true; });
  }
  const description = fieldInput('Description', {
    type: 'textarea', value: existing ? (existing.description || '') : '',
    placeholder: 'What this role can do',
  });
  const priority = fieldInput('Priority', {
    value: existing && existing.priority != null ? String(existing.priority) : '100',
  });
  const active = document.createElement('input');
  active.type = 'checkbox';
  active.checked = existing ? (existing.is_active !== false) : true;
  const activeWrap = document.createElement('label');
  activeWrap.className = 'co-check';
  activeWrap.appendChild(active);
  const activeText = document.createElement('span');
  activeText.textContent = 'Active';
  activeWrap.appendChild(activeText);

  // Scopes grouped by category
  const groups = {};
  (allScopes || []).forEach((s) => {
    const cat = s.category || 'Other';
    (groups[cat] = groups[cat] || []).push(s);
  });
  const categoryNames = Object.keys(groups).sort();
  const selectedScopeIds = new Set(
    (existing && existing.scopes ? existing.scopes : []).map((s) => s.id));
  const scopesWrap = document.createElement('div');
  scopesWrap.className = 'co-scope-list';
  if (!categoryNames.length) scopesWrap.appendChild(makeFaintC('Could not load scopes.'));
  const scopesLabel = document.createElement('span');
  scopesLabel.className = 'co-label-text';
  function refreshScopeCount() {
    scopesLabel.textContent = 'Permissions / scopes (' + selectedScopeIds.size + ' selected)';
  }
  refreshScopeCount();
  categoryNames.forEach((cat) => {
    const catEl = document.createElement('div');
    catEl.className = 'co-scope-cat'; catEl.textContent = cat;
    scopesWrap.appendChild(catEl);
    groups[cat].forEach((s) => {
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = selectedScopeIds.has(s.id);
      cb.addEventListener('change', () => {
        if (cb.checked) selectedScopeIds.add(s.id);
        else selectedScopeIds.delete(s.id);
        refreshScopeCount();
      });
      const row = document.createElement('label');
      row.className = 'co-scope-row';
      row.appendChild(cb);
      const det = document.createElement('div');
      det.innerHTML = '<code>' + escapeC(s.name) + '</code>' +
        (s.description ? '<div class="co-scope-row-desc">' + escapeC(s.description) + '</div>' : '');
      row.appendChild(det);
      scopesWrap.appendChild(row);
    });
  });
  const scopesField = document.createElement('label');
  scopesField.className = 'co-field';
  scopesField.appendChild(scopesLabel);
  scopesField.appendChild(scopesWrap);

  const cancelBtn = button('Cancel');
  const saveBtn = button(isEdit ? 'Save changes' : 'Create role', { kind: 'primary' });

  const handle = openModal({
    title: isEdit ? 'Edit custom role' : 'Create custom role',
    description: isEdit
      ? 'Update the role’s display info and permissions.'
      : 'Define a new bundle of scopes. The slug must be unique and cannot be changed once created.',
    wide: true,
    body: [
      gridRow([friendly.wrap, slug.wrap]),
      description.wrap,
      gridRow([priority.wrap, activeWrap]),
      scopesField,
    ],
    footer: [cancelBtn, saveBtn],
  });
  cancelBtn.addEventListener('click', () => handle.close());
  saveBtn.addEventListener('click', async () => {
    const friendlyVal = friendly.input.value.trim();
    const slugVal = slug.input.value.trim();
    if (!friendlyVal) { toastError('Display name is required'); friendly.input.focus(); return; }
    if (!isEdit && !slugVal) { toastError('Slug is required'); slug.input.focus(); return; }
    if (!isEdit && !/^[a-z0-9_]+$/.test(slugVal)) {
      toastError('Slug must be lowercase letters, numbers, and underscores only');
      slug.input.focus();
      return;
    }
    const priorityNum = priority.input.value.trim()
      ? Math.max(0, Math.floor(Number(priority.input.value)))
      : 100;
    saveBtn.disabled = true;
    try {
      if (isEdit) {
        await view.fetchJson('/v1/roles/' + encodeURIComponent(existing.id), {
          method: 'PUT',
          json: {
            friendly_name: friendlyVal,
            description: description.input.value.trim() || null,
            priority: priorityNum,
            is_active: !!active.checked,
            scope_ids: Array.from(selectedScopeIds),
          },
        });
      } else {
        await view.fetchJson('/v1/roles?company_id=' + encodeURIComponent(companyId), {
          method: 'POST',
          json: {
            name: slugVal,
            friendly_name: friendlyVal,
            description: description.input.value.trim() || null,
            priority: priorityNum,
            scope_ids: Array.from(selectedScopeIds),
          },
        });
      }
      handle.close();
      if (typeof onSaved === 'function') onSaved();
    } catch (err) {
      toastError(friendlyError(err));
      saveBtn.disabled = false;
    }
  });
  focusFirstInput(handle);
};

CompaniesView.prototype.openAssignCustomRolePicker = function (c, member) {
  const view = this;
  const existing = this.detail.customRolesPerUser[member.id] || [];
  const assigned = new Set(existing.map((a) =>
    (a.custom_role && a.custom_role.id) || a.custom_role_id).filter(Boolean));
  const available = (this.detail.customRoles || []).filter((r) =>
    r.is_active !== false && !assigned.has(r.id));
  if (!available.length) {
    toastError('No more custom roles available to assign');
    return;
  }
  const list = document.createElement('div');
  list.className = 'co-row-list';
  available.forEach((r) => {
    const card = document.createElement('div');
    card.className = 'co-role-card';
    const grow = document.createElement('div');
    grow.className = 'co-role-card-grow';
    grow.innerHTML =
      '<div class="co-role-card-title">' + escapeC(r.friendly_name || r.name) + '</div>' +
      (r.description ? '<div class="co-role-card-desc">' + escapeC(r.description) + '</div>' : '') +
      '<div class="co-role-card-desc">' + ((r.scopes && r.scopes.length) || 0) + ' permission(s)</div>';
    card.appendChild(grow);
    const actions = document.createElement('div');
    actions.className = 'co-role-card-actions';
    const assignBtn = button('Assign', { kind: 'primary', onclick: async () => {
      assignBtn.disabled = true;
      try {
        await view.fetchJson('/v1/user/custom-role?company_id=' + encodeURIComponent(c.id), {
          method: 'POST',
          json: { user_id: member.id, custom_role_id: r.id },
        });
        handle.close();
        await view.loadDetailData();
        view.renderDetailBody();
      } catch (err) {
        toastError(friendlyError(err));
        assignBtn.disabled = false;
      }
    } });
    actions.appendChild(assignBtn);
    card.appendChild(actions);
    list.appendChild(card);
  });

  const closeBtn = button('Close');
  const handle = openModal({
    title: 'Assign custom role',
    description: 'Assign a custom role to ' + (member.email || member.id),
    body: [list],
    footer: [closeBtn],
  });
  closeBtn.addEventListener('click', () => handle.close());
};

// ─── Member details dialog ───────────────────────────────────────────

CompaniesView.prototype.openMemberDetailsDialog = function (c, member) {
  const view = this;
  const isSelf = member.id === this.userId;
  const isProtected = member.role_id === 0 || member.role_id === 1 || member.role_id === 4;
  const roleNames = this.roleNameLookup();
  const displayName = ((member.first_name || '') + ' ' + (member.last_name || '')).trim()
    || member.email || 'Member';

  function staticField(label, value) {
    const wrap = document.createElement('div');
    wrap.className = 'co-detail-field';
    wrap.innerHTML =
      '<span class="co-detail-field-label">' + escapeC(label) + '</span>' +
      '<div class="co-detail-field-value readonly">' + escapeC(value || 'Not provided') + '</div>';
    return wrap;
  }
  function editableField(label, key, type) {
    const input = document.createElement('input');
    input.className = 'co-input';
    input.type = type || 'text';
    input.value = member[key] || '';
    const wrap = document.createElement('label');
    wrap.className = 'co-detail-field';
    const lab = document.createElement('span');
    lab.className = 'co-detail-field-label';
    lab.textContent = label;
    wrap.appendChild(lab);
    wrap.appendChild(input);
    return { wrap, input };
  }

  let firstField, lastField, emailField, profileBlock;
  if (isSelf) {
    firstField = editableField('First name', 'first_name');
    lastField = editableField('Last name', 'last_name');
    emailField = editableField('Email', 'email', 'email');
    profileBlock = gridRow([firstField.wrap, lastField.wrap, emailField.wrap], 'co-detail-grid');
  } else {
    profileBlock = gridRow([
      staticField('First name', member.first_name),
      staticField('Last name', member.last_name),
      staticField('Email', member.email),
    ], 'co-detail-grid');
  }

  // Role select
  const roleSelect = document.createElement('select');
  roleSelect.className = 'co-select';
  const opts = view.assignableDefaultRoles();
  opts.forEach((r) => {
    const o = document.createElement('option');
    o.value = String(r.id); o.textContent = r.friendly_name || r.name;
    roleSelect.appendChild(o);
  });
  if (isProtected && !opts.find((r) => r.id === member.role_id)) {
    const o = document.createElement('option');
    o.value = String(member.role_id);
    o.textContent = roleNames[member.role_id] || ('Role ' + member.role_id);
    roleSelect.appendChild(o);
  }
  roleSelect.value = String(member.role_id);
  roleSelect.disabled = isProtected;
  roleSelect.addEventListener('change', async () => {
    const next = Number(roleSelect.value);
    if (next === member.role_id) return;
    try {
      await view.fetchJson('/v1/user/role', {
        method: 'PUT',
        json: { role_id: next, company_id: c.id, user_id: member.id },
      });
      member.role_id = next;
      await view.loadDetailData();
      view.renderDetailBody();
    } catch (err) {
      toastError(friendlyError(err));
      roleSelect.value = String(member.role_id);
    }
  });
  const roleField = document.createElement('div');
  roleField.className = 'co-detail-field';
  roleField.innerHTML = '<span class="co-detail-field-label">Default role</span>';
  roleField.appendChild(roleSelect);
  const createdField = staticField('Joined',
    member.created_at ? formatRelativeC(member.created_at) : 'Unknown');

  // Custom-role chips
  const customRoleById = {};
  (this.detail.customRoles || []).forEach((r) => { if (r && r.id) customRoleById[r.id] = r; });
  const memberCustomRoles = (this.detail.customRolesPerUser[member.id] || []).slice();

  const chipBlock = document.createElement('div');
  chipBlock.style.cssText = 'display:flex;flex-wrap:wrap;gap:4px;';
  function renderChips() {
    chipBlock.innerHTML = '';
    memberCustomRoles.forEach((assignment) => {
      const role = assignment.custom_role || customRoleById[assignment.custom_role_id] || null;
      const customRoleId = (role && role.id) || assignment.custom_role_id;
      const label = (role && (role.friendly_name || role.name)) || 'Custom role';
      const chip = document.createElement('span');
      chip.className = 'co-custom-role-chip';
      chip.textContent = label;
      const x = document.createElement('button');
      x.type = 'button'; x.title = 'Remove role'; x.textContent = '×';
      x.addEventListener('click', async () => {
        if (!customRoleId) return;
        try {
          await view.fetchJson(
            '/v1/user/' + encodeURIComponent(member.id) + '/custom-role/' + encodeURIComponent(customRoleId)
              + '?company_id=' + encodeURIComponent(c.id),
            { method: 'DELETE' });
          const idx = memberCustomRoles.findIndex((a) =>
            ((a.custom_role && a.custom_role.id) || a.custom_role_id) === customRoleId);
          if (idx >= 0) memberCustomRoles.splice(idx, 1);
          renderChips();
          await view.loadDetailData();
          view.renderDetailBody();
        } catch (err) { toastError(friendlyError(err)); }
      });
      chip.appendChild(x);
      chipBlock.appendChild(chip);
    });
    if ((view.detail.customRoles || []).length) {
      const addBtn = document.createElement('button');
      addBtn.type = 'button'; addBtn.className = 'co-chip-btn'; addBtn.textContent = '+ Custom role';
      addBtn.addEventListener('click', () => {
        handle.close();
        view.openAssignCustomRolePicker(c, member);
      });
      chipBlock.appendChild(addBtn);
    } else {
      const hint = document.createElement('span');
      hint.className = 'co-faint';
      hint.style.cssText = 'font-size:11px;';
      hint.textContent = 'No custom roles defined for this company.';
      chipBlock.appendChild(hint);
    }
  }
  const customRolesField = document.createElement('div');
  customRolesField.className = 'co-detail-field';
  customRolesField.innerHTML = '<span class="co-detail-field-label">Custom roles</span>';
  customRolesField.appendChild(chipBlock);

  const footer = [];
  let saveProfileBtn = null;
  if (isSelf) {
    saveProfileBtn = button('Save profile', { kind: 'primary', onclick: async () => {
      const patch = {
        first_name: firstField.input.value.trim(),
        last_name: lastField.input.value.trim(),
        email: emailField.input.value.trim(),
      };
      saveProfileBtn.disabled = true;
      try {
        await view.fetchJson('/v1/user', { method: 'PUT', json: patch });
        handle.close();
        await view.loadDetailData();
        view.renderDetailBody();
      } catch (err) {
        toastError(friendlyError(err));
        saveProfileBtn.disabled = false;
      }
    } });
    footer.push(saveProfileBtn);
  }
  const closeBtn = button('Close');
  footer.unshift(closeBtn);

  const handle = openModal({
    title: displayName,
    description: isSelf
      ? 'Edit your profile, default role, and custom roles.'
      : 'Profile fields can only be edited by the user themselves. You can change their role and custom roles below.',
    wide: true,
    body: [
      profileBlock,
      gridRow([roleField, createdField], 'co-detail-grid'),
      customRolesField,
    ],
    footer,
  });
  closeBtn.addEventListener('click', () => handle.close());
  renderChips();
  focusFirstInput(handle, { focusSelector: isSelf ? 'input' : 'select' });
};

// ─── Error rendering ─────────────────────────────────────────────────

CompaniesView.prototype.renderError = function (err) {
  const target = this.view === 'detail' ? this.detailErrEl : this.errEl;
  if (!target) return;
  if (!err) { target.hidden = true; target.textContent = ''; return; }
  target.textContent = err.message || 'Request failed.';
  target.hidden = false;
};

// ─── Styles ──────────────────────────────────────────────────────────

CompaniesView.prototype.injectStyles = function () {
  if (document.getElementById('co-styles')) return;
  const css = `
    .co-root, .co-detail-root {
      --co-border: var(--border);
      --co-divider: var(--border-muted);
      --co-row-hover: var(--panel-hover);
      --co-card-bg: var(--panel-2);
    }
    .co-root { display: flex; flex-direction: column; gap: 16px; padding: 16px 20px 32px; min-height: 100%; color: var(--text); }
    /* Detail view scrolls within the same container as the list view —
     * relying on the parent's natural overflow rather than a flex:1 inner
     * scroll region. The earlier height:100% + flex:1 internal scroll
     * pattern collapsed when the container didn't enforce a fixed height,
     * which crushed the page when content exceeded the viewport. */
    .co-detail-root { gap: 0; padding: 0; display: flex; flex-direction: column; min-height: 100%; color: var(--text); }
    .co-title-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .co-title { margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -0.01em; flex: 0 0 auto; }
    .co-iconbtn { width: 30px; height: 30px; border-radius: 6px; border: 1px solid var(--co-border); background: var(--panel-2); color: var(--text-dim); cursor: pointer; font-size: 14px; display: inline-flex; align-items: center; justify-content: center; }
    .co-iconbtn:hover { background: var(--panel); color: var(--text); }
    .co-iconbtn:disabled { opacity: 0.5; cursor: default; }
    .co-primary { font-size: 12.5px; padding: 6px 14px; border-radius: 6px; background: var(--accent); color: #fff; border: 1px solid var(--accent); cursor: pointer; font-weight: 500; }
    .co-primary:hover:not(:disabled) { filter: brightness(1.1); }
    .co-primary:disabled { opacity: 0.5; cursor: default; }
    .co-secondary { font-size: 12px; padding: 5px 12px; border-radius: 6px; background: var(--panel-2); color: var(--text); border: 1px solid var(--co-border); cursor: pointer; }
    .co-secondary:hover:not(:disabled) { background: var(--panel); }
    .co-secondary:disabled { opacity: 0.5; cursor: default; }
    .co-danger { font-size: 12px; padding: 5px 12px; border-radius: 6px; background: transparent; color: #ffb4ba; border: 1px solid rgba(220,60,80,0.4); cursor: pointer; }
    .co-danger:hover:not(:disabled) { background: rgba(220, 60, 80, 0.18); }
    .co-search { flex: 1 1 280px; max-width: 420px; padding: 7px 12px; font-size: 13px; background: var(--panel-2); color: var(--text); border: 1px solid var(--co-border); border-radius: 6px; }
    .co-search:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(107,123,255,0.18); }
    .co-error { padding: 10px 14px; border-radius: 8px; font-size: 12.5px; background: rgba(220, 60, 80, 0.18); border: 1px solid rgba(220, 60, 80, 0.4); color: #ffb4ba; }
    .co-table-wrap { overflow: auto; background: var(--co-card-bg); border: 1px solid var(--co-border); border-radius: 10px; }
    .co-table { width: 100%; border-collapse: collapse; font-size: 13px; min-width: 1000px; }
    .co-table th, .co-table td { padding: 11px 14px; text-align: left; border-bottom: 1px solid var(--co-divider); vertical-align: middle; }
    .co-table tbody tr:hover { background: var(--co-row-hover); }
    .co-table tbody tr:last-child td { border-bottom: 0; }
    .co-th { color: var(--text-faint); font-weight: 600; font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.07em; background: var(--border-muted); border-bottom: 1px solid var(--co-border); white-space: nowrap; user-select: none; }
    .co-th.is-sortable { cursor: pointer; }
    .co-th.is-sortable:hover { color: var(--text); background: var(--co-row-hover); }
    .co-name { font-weight: 600; }
    .co-id { font-family: var(--mono); font-size: 10.5px; color: var(--text-faint); }
    .co-pill { display: inline-flex; align-items: center; font-size: 10.5px; font-weight: 600; padding: 1px 7px; border-radius: 999px; background: rgba(107,123,255,0.18); color: #c4ccff; border: 1px solid rgba(107,123,255,0.35); margin-left: 4px; }
    .co-rolepill { display: inline-flex; align-items: center; font-size: 11px; font-weight: 600; padding: 2px 9px; border-radius: 999px; background: var(--panel-2); border: 1px solid var(--co-border); color: var(--text-dim); }
    .co-faint { color: var(--text-faint); }
    .co-actions { display: flex; gap: 4px; justify-content: flex-end; flex-wrap: nowrap; }
    .co-actions button { font-size: 11px; padding: 3px 9px; border-radius: 5px; border: 1px solid var(--co-border); background: var(--panel-2); color: var(--text); cursor: pointer; white-space: nowrap; }
    .co-actions button:hover { background: var(--panel); }
    .co-actions button.danger { color: #ffb4ba; border-color: rgba(220,60,80,0.4); }
    .co-actions button.danger:hover { background: rgba(220, 60, 80, 0.18); }
    .co-empty { padding: 32px; text-align: center; color: var(--text-faint); }
    .co-team-panel { display: block; }
    /* Sticky header so the back button + actions stay reachable while the
     * detail body scrolls. top:0 sticks to the top of the parent scroll
     * container (the extension framing layout owns that scroll). */
    .co-detail-header { position: sticky; top: 0; z-index: 5; display: flex; align-items: center; gap: 12px; padding: 14px 20px; background: var(--panel); border-bottom: 1px solid var(--co-border); }
    .co-detail-title { font-weight: 700; font-size: 16px; }
    .co-detail-body { padding: 20px; display: flex; flex-direction: column; gap: 16px; background: var(--bg); }
    .co-card { background: var(--co-card-bg); border: 1px solid var(--co-border); border-radius: 10px; overflow: hidden; }
    .co-card-head { padding: 13px 16px; border-bottom: 1px solid var(--co-border); background: var(--border-muted); }
    .co-card-title { font-weight: 600; font-size: 13.5px; }
    .co-card-desc { font-size: 12px; color: var(--text-faint); margin-top: 3px; }
    .co-card-body { padding: 16px 18px; display: flex; flex-direction: column; gap: 10px; }
    .co-kv { display: grid; grid-template-columns: minmax(140px, max-content) 1fr; column-gap: 24px; margin: 0; font-size: 13px; }
    .co-kv dt { color: var(--text-faint); padding: 10px 0; border-bottom: 1px solid var(--co-divider); display: flex; align-items: center; }
    .co-kv dd { margin: 0; padding: 10px 0; border-bottom: 1px solid var(--co-divider); text-align: right; word-break: break-word; display: flex; align-items: center; justify-content: flex-end; }
    .co-kv dt:last-of-type, .co-kv dd:last-of-type { border-bottom: 0; }
    .co-kv dd code { font-family: var(--mono); font-size: 12px; color: var(--text-dim); background: var(--panel-2); padding: 2px 7px; border-radius: 4px; }
    .co-data-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
    .co-data-table th, .co-data-table td { padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--co-divider); }
    .co-data-table th { color: var(--text-faint); font-weight: 600; font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.07em; background: var(--border-muted); border-bottom: 1px solid var(--co-border); }
    .co-data-table tr:last-child td { border-bottom: 0; }
    .co-table code { font-family: var(--mono); font-size: 12px; color: var(--text-dim); }

    /* Subsection heads inside a card (e.g. invitations + members groups) */
    .co-subsection-head { font-weight: 600; font-size: 12px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 4px; }

    /* List items (members, invitations, custom roles) */
    .co-row-list { display: flex; flex-direction: column; gap: 8px; }
    .co-list-item { display: flex; gap: 10px; align-items: center; background: var(--panel); border: 1px solid var(--co-border); border-radius: 8px; padding: 10px 12px; flex-wrap: wrap; }
    .co-list-item.is-selected { border-color: var(--accent); background: rgba(107,123,255,0.10); }
    .co-list-item-grow { flex: 1; min-width: 0; }
    .co-list-item-title { font-size: 13px; font-weight: 600; word-break: break-word; }
    .co-list-item-meta { font-size: 11.5px; color: var(--text-faint); margin-top: 4px; }
    .co-row-actions { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; justify-content: flex-end; }
    .co-chip-action { font-size: 11px; padding: 4px 10px; border-radius: 5px; border: 1px solid var(--co-border); background: var(--panel-2); color: var(--text); cursor: pointer; white-space: nowrap; }
    .co-chip-action:hover:not(:disabled) { background: var(--panel); }
    .co-chip-action.danger { color: #ffb4ba; border-color: rgba(220,60,80,0.4); }
    .co-chip-action.danger:hover:not(:disabled) { background: rgba(220, 60, 80, 0.18); }

    /* Bulk-action bar sticks just below the detail page's sticky header
     * (header is ~57px tall: 14px+14px padding + ~29px content + 1px border). */
    .co-bulk-bar { position: sticky; top: 57px; z-index: 4; display: flex; gap: 8px; align-items: center; padding: 8px 12px; background: rgba(107,123,255,0.12); border: 1px solid rgba(107,123,255,0.4); border-radius: 8px; font-size: 12px; flex-wrap: wrap; }
    .co-bulk-bar-count { font-weight: 600; color: #c4ccff; flex: 1; min-width: 0; }

    /* Search filter row */
    .co-filter-bar { display: flex; gap: 8px; align-items: center; }
    .co-filter-bar .co-search { flex: 1; max-width: none; }

    /* Stat pills */
    .co-stat-pills { display: inline-flex; flex-wrap: wrap; gap: 4px; vertical-align: middle; margin-left: 8px; }
    .co-stat-pill { font-size: 10.5px; padding: 1px 8px; border-radius: 999px; background: var(--panel-2); border: 1px solid var(--co-border); color: var(--text-dim); font-weight: 500; }

    /* Status badges */
    .co-badge { display: inline-flex; align-items: center; font-size: 10.5px; font-weight: 600; padding: 1px 7px; border-radius: 999px; border: 1px solid var(--co-border); background: var(--panel-2); color: var(--text-dim); margin-left: 4px; }
    .co-badge.success { background: rgba(94, 210, 143, 0.18); border-color: rgba(94, 210, 143, 0.4); color: #5dd28f; }
    .co-badge.warn    { background: rgba(220, 160, 60, 0.18); border-color: rgba(220, 160, 60, 0.4); color: #e5b86a; }
    .co-badge.muted   { background: var(--panel); border-color: var(--co-border); color: var(--text-faint); }

    /* Custom-role chips */
    .co-custom-role-chip { display: inline-flex; align-items: center; gap: 4px; font-size: 10.5px; padding: 1px 6px; border-radius: 999px; background: rgba(107,123,255,0.18); color: #c4ccff; border: 1px solid rgba(107,123,255,0.4); margin-right: 4px; }
    .co-custom-role-chip button { background: transparent; border: 0; color: inherit; cursor: pointer; padding: 0 2px; font-size: 12px; line-height: 1; }
    .co-custom-role-chip button:hover { color: #ffb4ba; }
    .co-chip-btn { background: transparent; border: 1px dashed var(--co-border); color: var(--text-dim); border-radius: 999px; font-size: 10.5px; font-weight: 600; padding: 1px 8px; cursor: pointer; }
    .co-chip-btn:hover { color: var(--accent); border-color: var(--accent); background: rgba(107,123,255,0.10); }

    /* Form fields inside dialogs */
    .co-input, .co-textarea, .co-select { width: 100%; box-sizing: border-box; background: var(--panel-2); color: var(--text); border: 1px solid var(--co-border); border-radius: 6px; padding: 7px 10px; font-family: inherit; font-size: 12.5px; }
    .co-input:focus, .co-textarea:focus, .co-select:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 2px rgba(107,123,255,0.18); }
    .co-textarea { resize: vertical; min-height: 70px; }
    .co-field { display: flex; flex-direction: column; gap: 4px; }
    .co-label-text { text-transform: uppercase; letter-spacing: 0.6px; font-size: 10px; color: var(--text-faint); font-weight: 600; }
    .co-hint { font-size: 11px; color: var(--text-faint); }
    .co-check { display: flex; gap: 8px; align-items: flex-start; cursor: pointer; font-size: 12.5px; color: var(--text); }
    .co-check input[type="checkbox"] { accent-color: var(--accent); }

    /* Grid rows in dialogs */
    .co-grid-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    @media (max-width: 520px) { .co-grid-row { grid-template-columns: 1fr; } }
    .co-detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    @media (max-width: 520px) { .co-detail-grid { grid-template-columns: 1fr; } }
    .co-detail-field { display: flex; flex-direction: column; gap: 4px; }
    .co-detail-field-label { font-size: 10px; font-weight: 600; letter-spacing: 0.6px; text-transform: uppercase; color: var(--text-faint); }
    .co-detail-field-value { font-size: 12.5px; color: var(--text); padding: 8px 10px; border: 1px solid var(--co-border); background: var(--panel-2); border-radius: 6px; min-height: 20px; word-break: break-word; }
    .co-detail-field-value.readonly { color: var(--text-dim); }

    /* Modal */
    .co-modal-backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.55); display: flex; align-items: center; justify-content: center; z-index: 200; padding: 16px; }
    .co-modal-card { background: var(--panel); border: 1px solid var(--co-border); border-radius: 10px; width: 100%; max-width: 560px; max-height: 90vh; display: flex; flex-direction: column; overflow: hidden; box-shadow: 0 20px 40px rgba(0,0,0,0.4); }
    .co-modal-card.wide { max-width: 720px; }
    .co-modal-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--co-border); flex-shrink: 0; }
    .co-modal-header h3 { margin: 0; font-size: 14px; font-weight: 650; }
    .co-modal-header p { margin: 4px 0 0; font-size: 11.5px; color: var(--text-dim); }
    .co-modal-close { appearance: none; background: transparent; border: 0; color: var(--text-dim); font-size: 20px; width: 28px; height: 28px; border-radius: 4px; cursor: pointer; line-height: 1; }
    .co-modal-close:hover { background: var(--panel-2); color: var(--text); }
    .co-modal-body { padding: 14px 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; }
    .co-modal-footer { display: flex; gap: 8px; justify-content: flex-end; padding: 12px 16px; border-top: 1px solid var(--co-border); flex-shrink: 0; flex-wrap: wrap; }
    .co-confirm-message { font-size: 13px; line-height: 1.5; color: var(--text); margin: 0; }

    /* Invite results */
    .co-invite-results { display: flex; flex-direction: column; gap: 4px; max-height: 220px; overflow-y: auto; border: 1px solid var(--co-border); border-radius: 6px; }
    .co-invite-result { padding: 8px 10px; border-bottom: 1px solid var(--co-divider); font-size: 11.5px; display: flex; flex-direction: column; gap: 4px; }
    .co-invite-result:last-child { border-bottom: 0; }
    .co-invite-result.success { background: rgba(94, 210, 143, 0.08); }
    .co-invite-result.error { background: rgba(220, 60, 80, 0.08); }
    .co-invite-result-head { display: flex; gap: 6px; align-items: center; }
    .co-invite-result-msg { color: var(--text-dim); padding-left: 18px; word-break: break-word; }
    .co-invite-result-msg.error { color: #ffb4ba; }
    .co-invite-result-link { display: flex; gap: 6px; align-items: center; padding-left: 18px; }
    .co-invite-result-link a { color: var(--accent); font-size: 11px; word-break: break-all; }
    .co-status-line { font-size: 11.5px; color: var(--text-faint); margin: 0; min-height: 14px; }
    .co-status-line.error { color: #ffb4ba; }
    .co-status-line.success { color: #5dd28f; }

    /* Role cards inside custom roles dialog */
    .co-role-card { display: flex; gap: 10px; align-items: flex-start; background: var(--panel-2); border: 1px solid var(--co-border); border-radius: 8px; padding: 10px 12px; flex-wrap: wrap; }
    .co-role-card.inactive { opacity: 0.6; }
    .co-role-card-grow { flex: 1; min-width: 0; }
    .co-role-card-title { font-size: 12.5px; font-weight: 600; }
    .co-role-card-desc { font-size: 11px; color: var(--text-dim); margin-top: 4px; }
    .co-role-card-scopes { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
    .co-role-card-scopes code { font-family: var(--mono); font-size: 10.5px; background: var(--panel); color: var(--accent); padding: 1px 6px; border-radius: 3px; }
    .co-role-card-actions { display: flex; gap: 4px; flex-shrink: 0; }

    /* Scope list inside role editor */
    .co-scope-list { max-height: 240px; overflow-y: auto; background: var(--panel-2); border: 1px solid var(--co-border); border-radius: 6px; padding: 8px 10px; display: flex; flex-direction: column; gap: 4px; }
    .co-scope-cat { font-weight: 600; font-size: 11.5px; margin: 6px 0 2px; text-transform: capitalize; }
    .co-scope-cat:first-child { margin-top: 0; }
    .co-scope-row { display: flex; gap: 8px; align-items: flex-start; padding-left: 8px; cursor: pointer; }
    .co-scope-row code { font-family: var(--mono); font-size: 11px; color: var(--accent); }
    .co-scope-row-desc { font-size: 10.5px; color: var(--text-faint); }

    /* Toast (top-right) */
    .co-toast { position: fixed; top: 16px; right: 16px; background: var(--panel); border: 1px solid var(--co-border); padding: 10px 14px; border-radius: 8px; box-shadow: 0 10px 25px rgba(0,0,0,0.3); z-index: 300; font-size: 12.5px; color: var(--text); max-width: 360px; }
    .co-toast.success { border-color: rgba(94, 210, 143, 0.5); }
    .co-toast.error { border-color: rgba(220, 60, 80, 0.55); color: #ffb4ba; }
  `;
  const tag = document.createElement('style');
  tag.id = 'co-styles'; tag.textContent = css;
  document.head.appendChild(tag);
};

// ─── Module-level helpers ────────────────────────────────────────────

function escapeC(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function formatRelativeC(iso) {
  const ms = Date.parse(iso); if (!isFinite(ms)) return '';
  const diff = Date.now() - ms;
  if (diff < 60_000) return 'just now';
  if (diff < 3_600_000) return Math.round(diff / 60_000) + 'm ago';
  if (diff < 86_400_000) return Math.round(diff / 3_600_000) + 'h ago';
  return Math.round(diff / 86_400_000) + 'd ago';
}
function makeFaintC(text) {
  const e = document.createElement('div');
  e.className = 'co-faint';
  e.textContent = text;
  e.style.cssText = 'padding:24px;text-align:center;color:var(--text-faint);';
  return e;
}
function makeCardC(title, description) {
  const card = document.createElement('div'); card.className = 'co-card';
  if (title) {
    const head = document.createElement('div'); head.className = 'co-card-head';
    const t = document.createElement('div'); t.className = 'co-card-title'; t.textContent = title;
    head.appendChild(t);
    if (description) { const d = document.createElement('div'); d.className = 'co-card-desc'; d.textContent = description; head.appendChild(d); }
    card.appendChild(head);
  }
  const body = document.createElement('div'); body.className = 'co-card-body';
  card.appendChild(body); card._body = body;
  return card;
}
function makeKvC(rows) {
  const dl = document.createElement('dl'); dl.className = 'co-kv';
  for (const row of rows) {
    if (row == null) continue;
    const [k, v, opts] = row;
    if (v == null || v === '') continue;
    const dt = document.createElement('dt'); dt.textContent = k;
    const dd = document.createElement('dd');
    if (opts && opts.html) dd.innerHTML = String(v);
    else if (opts && opts.mono) { const c = document.createElement('code'); c.textContent = String(v); dd.appendChild(c); }
    else dd.textContent = String(v);
    dl.appendChild(dt); dl.appendChild(dd);
  }
  return dl;
}
function makeTableC(cols, rows) {
  const t = document.createElement('table'); t.className = 'co-data-table';
  const thead = document.createElement('thead'); const trh = document.createElement('tr');
  for (const c of cols) { const th = document.createElement('th'); th.textContent = c; trh.appendChild(th); }
  thead.appendChild(trh); t.appendChild(thead);
  const tbody = document.createElement('tbody');
  if (!rows.length) {
    const tr = document.createElement('tr'); const td = document.createElement('td');
    td.colSpan = cols.length; td.style.cssText = 'padding:14px;text-align:center;color:var(--text-faint);';
    td.textContent = 'No entries.'; tr.appendChild(td); tbody.appendChild(tr);
  } else {
    for (const row of rows) {
      const tr = document.createElement('tr');
      for (const cell of row) { const td = document.createElement('td'); if (cell instanceof Node) td.appendChild(cell); else td.textContent = cell == null ? '' : String(cell); tr.appendChild(td); }
      tbody.appendChild(tr);
    }
  }
  t.appendChild(tbody); return t;
}
function readJsonC(k, f) { try { const r = window.localStorage.getItem(k); if (!r) return f; const v = JSON.parse(r); return v == null ? f : v; } catch (_) { return f; } }
function writeJsonC(k, v) { try { window.localStorage.setItem(k, JSON.stringify(v)); } catch (_) {} }

// Form-field factories — return both the wrapper DOM and the inner input
// so callers can both place the field and read/focus the value.
function fieldInput(label, opts) {
  opts = opts || {};
  const isArea = opts.type === 'textarea';
  const input = document.createElement(isArea ? 'textarea' : 'input');
  input.className = isArea ? 'co-input co-textarea' : 'co-input';
  if (!isArea) input.type = opts.type || 'text';
  if (opts.placeholder) input.placeholder = opts.placeholder;
  if (opts.value != null) input.value = opts.value;
  const wrap = wrapField(label, input, opts.hint);
  return { wrap, input };
}
function wrapField(label, control, hint) {
  const wrap = document.createElement('label');
  wrap.className = 'co-field';
  const lab = document.createElement('span');
  lab.className = 'co-label-text';
  lab.textContent = label;
  wrap.appendChild(lab);
  wrap.appendChild(control);
  if (hint) {
    const h = document.createElement('span');
    h.className = 'co-hint';
    h.textContent = hint;
    wrap.appendChild(h);
  }
  return wrap;
}
function gridRow(children, cls) {
  const row = document.createElement('div');
  row.className = cls || 'co-grid-row';
  children.filter(Boolean).forEach((c) => row.appendChild(c));
  return row;
}
function button(label, opts) {
  opts = opts || {};
  const b = document.createElement('button');
  b.type = 'button';
  b.textContent = label;
  if (opts.kind === 'primary') b.className = 'co-primary';
  else if (opts.kind === 'danger') b.className = 'co-danger';
  else b.className = 'co-secondary';
  if (opts.onclick) b.addEventListener('click', opts.onclick);
  if (opts.disabled) b.disabled = true;
  return b;
}

// Modal — captures previously-focused element and restores on every
// close path (button, Escape, backdrop, programmatic) so keyboard nav
// isn't dropped.
function openModal(opts) {
  opts = opts || {};
  const previouslyFocused = document.activeElement;

  const header = document.createElement('div');
  header.className = 'co-modal-header';
  const titleBlock = document.createElement('div');
  if (opts.title) {
    const h3 = document.createElement('h3'); h3.textContent = opts.title; titleBlock.appendChild(h3);
  }
  if (opts.description) {
    const p = document.createElement('p'); p.textContent = opts.description; titleBlock.appendChild(p);
  }
  header.appendChild(titleBlock);
  const closeX = document.createElement('button');
  closeX.type = 'button'; closeX.className = 'co-modal-close';
  closeX.textContent = '×';
  closeX.setAttribute('aria-label', 'Close');
  closeX.addEventListener('click', () => close());
  header.appendChild(closeX);

  const bodyEl = document.createElement('div');
  bodyEl.className = 'co-modal-body';
  (Array.isArray(opts.body) ? opts.body : (opts.body ? [opts.body] : []))
    .forEach((n) => { if (n) bodyEl.appendChild(n); });

  const card = document.createElement('div');
  card.className = 'co-modal-card' + (opts.wide ? ' wide' : '');
  card.appendChild(header);
  card.appendChild(bodyEl);
  if ((opts.footer || []).filter(Boolean).length) {
    const footer = document.createElement('div');
    footer.className = 'co-modal-footer';
    opts.footer.filter(Boolean).forEach((b) => footer.appendChild(b));
    card.appendChild(footer);
  }

  const root = document.createElement('div');
  root.className = 'co-modal-backdrop';
  root.setAttribute('role', 'dialog');
  root.appendChild(card);

  let closed = false;
  function close() {
    if (closed) return;
    closed = true;
    if (root.parentElement) root.parentElement.removeChild(root);
    document.removeEventListener('keydown', onKey);
    if (previouslyFocused && typeof previouslyFocused.focus === 'function'
        && document.contains(previouslyFocused)) {
      try { previouslyFocused.focus(); } catch (_) {}
    }
    if (typeof opts.onClose === 'function') {
      try { opts.onClose(); } catch (_) {}
    }
  }
  function onKey(e) { if (e.key === 'Escape') close(); }
  root.addEventListener('click', (e) => { if (e.target === root) close(); });
  document.addEventListener('keydown', onKey);
  document.body.appendChild(root);
  return { close, root, body: bodyEl };
}

function focusFirstInput(handle, opts) {
  opts = opts || {};
  requestAnimationFrame(() => {
    const root = handle.root;
    if (!root || !root.parentElement) return;
    const target = opts.focusSelector
      ? root.querySelector(opts.focusSelector)
      : root.querySelector('input:not([type=checkbox]):not([type=hidden]):not([disabled]), textarea:not([disabled])');
    if (target && typeof target.focus === 'function') {
      try { target.focus(); if (typeof target.select === 'function') target.select(); } catch (_) {}
    }
  });
}

// Themed confirm replacement that returns a Promise<boolean>.
function confirmDialog(opts) {
  opts = opts || {};
  return new Promise((resolve) => {
    let resolved = false;
    const finish = (val) => {
      if (resolved) return;
      resolved = true;
      handle.close();
      resolve(val);
    };
    const cancelBtn = button(opts.cancelLabel || 'Cancel');
    const confirmBtn = button(opts.confirmLabel || 'Confirm', {
      kind: opts.destructive ? 'danger' : 'primary',
    });
    cancelBtn.addEventListener('click', () => finish(false));
    confirmBtn.addEventListener('click', () => finish(true));
    const msg = document.createElement('p');
    msg.className = 'co-confirm-message';
    msg.textContent = opts.message || '';
    const handle = openModal({
      title: opts.title || 'Confirm',
      body: [msg],
      footer: [cancelBtn, confirmBtn],
      onClose: () => finish(false),
    });
    focusFirstInput(handle, { focusSelector: opts.destructive ? '.co-secondary' : '.co-primary' });
  });
}

function infoDialog(opts) {
  opts = opts || {};
  return new Promise((resolve) => {
    const okBtn = button('OK', { kind: 'primary' });
    okBtn.addEventListener('click', () => { handle.close(); resolve(); });
    const msg = document.createElement('p');
    msg.className = 'co-confirm-message';
    msg.textContent = opts.message || '';
    const handle = openModal({
      title: opts.title || 'Notice',
      body: [msg],
      footer: [okBtn],
      onClose: () => resolve(),
    });
    focusFirstInput(handle, { focusSelector: '.co-primary' });
  });
}

let _toastTimer = null;
function toast(message, kind) {
  let el = document.getElementById('co-toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'co-toast';
    document.body.appendChild(el);
  }
  el.className = 'co-toast' + (kind ? ' ' + kind : '');
  el.textContent = message;
  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { if (el && el.parentElement) el.parentElement.removeChild(el); }, kind === 'error' ? 5000 : 2800);
}
function toastInfo(msg) { toast(msg, 'success'); }
function toastError(msg) { toast(msg, 'error'); }

function parseEmails(raw) {
  return String(raw || '')
    .split(/[\s,;]+/)
    .map((e) => e.trim().toLowerCase())
    .filter((e) => e && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e));
}

function copyToClipboard(text) {
  if (!text) return;
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text);
      return;
    }
  } catch (_) {}
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed'; ta.style.left = '-9999px';
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); } catch (_) {}
  document.body.removeChild(ta);
}

function buildInviteLink(invitationId, email, ctx) {
  if (!invitationId || invitationId === 'none') return null;
  const appUri = (ctx && ctx.appUrl)
    || (ctx && ctx.serverUrl)
    || (window.location && window.location.origin)
    || '';
  const params = new URLSearchParams();
  params.set('invitation_id', invitationId);
  if (email) params.set('email', email);
  const base = String(appUri).replace(/\/+$/, '');
  return base + '/?' + params.toString();
}

function memberMatchesFilter(m, filter) {
  if (!filter) return true;
  const hay = ((m.first_name || '') + ' ' + (m.last_name || '') + ' ' + (m.email || ''))
    .toLowerCase();
  return hay.includes(filter);
}

function exportMembersCsv(members, roleNames, companyName) {
  if (!members || !members.length) { toastError('Nothing to export'); return; }
  const esc = (v) => {
    const s = v == null ? '' : String(v);
    if (/[",\n]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
    return s;
  };
  const header = ['First name', 'Last name', 'Email', 'Role'].map(esc).join(',');
  const rows = members.map((m) => [
    m.first_name, m.last_name, m.email,
    (roleNames && roleNames[m.role_id]) || m.role || ('Role ' + m.role_id),
  ].map(esc).join(','));
  const csv = [header].concat(rows).join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  const safe = (companyName || 'members').replace(/[^a-z0-9_-]+/gi, '_');
  a.download = safe + '-members-' + new Date().toISOString().split('T')[0] + '.csv';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toastInfo('Exported ' + members.length + ' member(s)');
}

function friendlyError(err, context) {
  const status = err && err.status;
  const baseMsg = (err && (err.detail || err.message)) || 'Request failed';
  const ctx = context ? ' ' + context : '';
  if (status === 402) return 'User limit reached. Upgrade your plan to add more users.';
  if (status === 403) return baseMsg && baseMsg !== 'HTTP 403'
    ? baseMsg
    : 'You don’t have permission to perform this action' + ctx + '.';
  if (status === 409) return baseMsg && baseMsg !== 'HTTP 409'
    ? baseMsg
    : 'That item already exists.';
  if (status === 404) return baseMsg && baseMsg !== 'HTTP 404'
    ? baseMsg
    : 'Not found.';
  return baseMsg;
}

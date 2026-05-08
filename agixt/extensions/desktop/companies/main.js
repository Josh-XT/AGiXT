/* Companies — desktop port of /companies.
 *
 * Endpoints:
 *   GET    /v1/companies                            list
 *   POST   /v1/companies                            create
 *   PATCH  /v1/companies/{id}                       update
 *   DELETE /v1/companies/{id}                       delete
 *   POST   /v1/companies/{id}/rotate-key            rotate API key
 *
 * Scope is enforced server-side; admin-only role_ids (0/1) get write
 * affordances client-side. The list shows everyone the user is a
 * member of, regardless of role.
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
  { id: 'actions',  label: '',          sortable: false, width: '200px' },
];

const ROLE_NAMES = { 0: 'Super Admin', 1: 'Owner', 2: 'Admin', 3: 'Manager', 4: 'User', 5: 'Chat User' };

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
  this.detail = { id: null, company: null, loading: false, error: null };
  this.userId = null;
}

CompaniesView.prototype.start = function () {
  this.injectStyles();
  this.render();
  this.loadUser().then(() => this.refresh());
};
CompaniesView.prototype.stop = function () { this.container.innerHTML = ''; };

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
    err.status = resp.status; throw err;
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

CompaniesView.prototype.refresh = async function () {
  try {
    // Pull both endpoints and merge:
    //   /v1/user.companies  — has role_id / scopes / agents / primary
    //                         / token_balance per company (per-user
    //                         data the bare /v1/companies omits)
    //   /v1/companies       — has users[] + children[] arrays
    // Web's CompanyDataGrid does the same join. Falls back to whichever
    // endpoint succeeded if one fails.
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
      // Don't overwrite users / children if the bare endpoint had them.
      return Object.assign({}, enriched, c, {
        // role_id / scopes / agents / primary / token_balance only on user payload
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
      this.renderDetailBody();
    }
  } catch (err) { this.renderError(err); }
};

// Above the company table, render the primary company's team — same
// pattern the web app uses to surface "your team" in a single glance.
CompaniesView.prototype.renderTeamPanel = function () {
  const root = this.container.querySelector('.co-root');
  if (!root) return;
  let panel = root.querySelector('.co-team-panel');
  if (!panel) {
    panel = document.createElement('div');
    panel.className = 'co-team-panel';
    // Insert right after the header so it sits above the error pane + table.
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
      (this.canEditRow(primary)
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

CompaniesView.prototype.openCreate = async function () {
  const name = window.prompt('Company name:');
  if (!name) return;
  try {
    await this.fetchJson('/v1/companies', { method: 'POST', json: { name: name } });
    await this.refresh();
  } catch (err) { this.renderError(err); }
};

CompaniesView.prototype.deleteCompany = async function (c) {
  if (!window.confirm('Delete "' + (c.name || c.id) + '"? This cannot be undone.')) return;
  try {
    await this.fetchJson('/v1/companies/' + encodeURIComponent(c.id), { method: 'DELETE' });
    await this.refresh();
  } catch (err) { this.renderError(err); }
};

CompaniesView.prototype.rotateKey = async function (c) {
  if (!window.confirm('Rotate API key for "' + (c.name || c.id) + '"? Existing integrations will need the new key.')) return;
  try {
    await this.fetchJson('/v1/companies/' + encodeURIComponent(c.id) + '/rotate-key', { method: 'POST' });
    window.alert('API key rotated. Check the company\'s integrations to update.');
  } catch (err) { this.renderError(err); }
};

CompaniesView.prototype.editField = async function (c, field, label) {
  const val = window.prompt('New ' + label + ':', c[field] || '');
  if (val == null) return;
  try {
    await this.fetchJson('/v1/companies/' + encodeURIComponent(c.id), {
      method: 'PATCH', json: { [field]: val },
    });
    await this.refresh();
  } catch (err) { this.renderError(err); }
};

CompaniesView.prototype.openDetail = function (c) {
  this.detail.id = c.id;
  this.detail.company = c;
  this.view = 'detail';
  this.render();
};
CompaniesView.prototype.backToList = function () {
  this.view = 'list';
  this.render();
  this.refresh();
};

/* --- filter + sort --- */
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

/* --- DOM --- */
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
  this.headerEl.innerHTML = '';
  const row = document.createElement('div'); row.className = 'co-title-row';
  const title = document.createElement('h2'); title.className = 'co-title'; title.textContent = 'Companies & Teams';
  row.appendChild(title);
  const refresh = document.createElement('button');
  refresh.type = 'button'; refresh.className = 'co-iconbtn'; refresh.title = 'Refresh'; refresh.textContent = '↻';
  refresh.addEventListener('click', () => this.refresh());
  row.appendChild(refresh);
  if (this.roleId === 0 || this.roleId === 1) {
    const add = document.createElement('button');
    add.type = 'button'; add.className = 'co-primary'; add.textContent = '+ New company';
    add.addEventListener('click', () => this.openCreate());
    row.appendChild(add);
  }
  const search = document.createElement('input');
  search.type = 'search'; search.placeholder = 'Search…'; search.value = this.search;
  search.className = 'co-search';
  search.addEventListener('input', (e) => { this.search = e.target.value; this.renderTable(); });
  row.appendChild(search);
  this.headerEl.appendChild(row);
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
      else if (action === 'rename') view.editField(c, 'name', 'name');
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
    actions.push('<button data-action="rename" data-id="' + escapeC(c.id) + '">Rename</button>');
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

/* --- detail --- */
CompaniesView.prototype.renderDetailShell = function () {
  const root = document.createElement('div'); root.className = 'co-root co-detail-root';
  this.detailHeaderEl = document.createElement('div'); this.detailHeaderEl.className = 'co-detail-header';
  root.appendChild(this.detailHeaderEl);
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
  back.addEventListener('click', () => this.backToList());
  this.detailHeaderEl.appendChild(back);
  const c = this.detail.company;
  const title = document.createElement('div'); title.className = 'co-detail-title';
  title.textContent = c ? (c.name || '(unnamed)') : 'Loading…';
  this.detailHeaderEl.appendChild(title);
};
CompaniesView.prototype.renderDetailBody = function () {
  this.renderDetailHeader();
  if (!this.detailBodyEl) return;
  this.detailBodyEl.innerHTML = '';
  const c = this.detail.company;
  if (!c) { this.detailBodyEl.appendChild(makeFaintC('Loading…')); return; }
  const card = makeCardC('Company info');
  card._body.appendChild(makeKvC([
    ['ID',          c.id, { mono: true }],
    ['Name',        c.name],
    ['Your role',   ROLE_NAMES[c.role_id] || '—'],
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
  this.detailBodyEl.appendChild(card);
  if (Array.isArray(c.agents) && c.agents.length) {
    const ac = makeCardC('Agents');
    ac._body.appendChild(makeTableC(['Name', 'Default', 'ID'], c.agents.map((a) => [
      a.name || '(unnamed)',
      a.default ? '✓' : '',
      (a.id || '').slice(0, 8),
    ])));
    this.detailBodyEl.appendChild(ac);
  }
  if (Array.isArray(c.users) && c.users.length) {
    const uc = makeCardC('Users', String(c.users.length) + ' member(s)');
    uc._body.appendChild(makeTableC(['Email', 'Name', 'Role'], c.users.map((u) => [
      u.email || '',
      ((u.first_name || '') + ' ' + (u.last_name || '')).trim(),
      ROLE_NAMES[u.role_id] || '',
    ])));
    this.detailBodyEl.appendChild(uc);
  }
};

CompaniesView.prototype.renderError = function (err) {
  if (!this.errEl) return;
  if (!err) { this.errEl.hidden = true; this.errEl.textContent = ''; return; }
  this.errEl.textContent = err.message || 'Request failed.';
  this.errEl.hidden = false;
};

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
    .co-detail-root { gap: 0; padding: 0; height: 100%; display: flex; flex-direction: column; }
    .co-title-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .co-title { margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -0.01em; flex: 0 0 auto; }
    .co-iconbtn { width: 30px; height: 30px; border-radius: 6px; border: 1px solid var(--co-border); background: var(--panel-2); color: var(--text-dim); cursor: pointer; font-size: 14px; display: inline-flex; align-items: center; justify-content: center; }
    .co-iconbtn:hover { background: var(--panel); color: var(--text); }
    .co-primary { font-size: 12.5px; padding: 6px 14px; border-radius: 6px; background: var(--accent); color: #fff; border: 1px solid var(--accent); cursor: pointer; font-weight: 500; }
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
    .co-secondary { font-size: 12px; padding: 5px 12px; border-radius: 6px; background: var(--panel-2); color: var(--text); border: 1px solid var(--co-border); cursor: pointer; }
    .co-secondary:hover { background: var(--panel); }
    .co-detail-header { display: flex; align-items: center; gap: 12px; padding: 14px 20px; background: var(--panel); border-bottom: 1px solid var(--co-border); }
    .co-detail-title { font-weight: 700; font-size: 16px; }
    .co-detail-body { padding: 20px; display: flex; flex-direction: column; gap: 16px; overflow: auto; flex: 1; min-height: 0; background: var(--bg); }
    .co-card { background: var(--co-card-bg); border: 1px solid var(--co-border); border-radius: 10px; overflow: hidden; }
    .co-card-head { padding: 13px 16px; border-bottom: 1px solid var(--co-border); background: var(--border-muted); }
    .co-card-title { font-weight: 600; font-size: 13.5px; }
    .co-card-desc { font-size: 12px; color: var(--text-faint); margin-top: 3px; }
    .co-card-body { padding: 16px 18px; }
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
  `;
  const tag = document.createElement('style');
  tag.id = 'co-styles'; tag.textContent = css;
  document.head.appendChild(tag);
};

function escapeC(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
function formatRelativeC(iso) {
  const ms = Date.parse(iso); if (!isFinite(ms)) return '';
  const diff = Date.now() - ms;
  if (diff < 60_000) return 'just now';
  if (diff < 3_600_000) return Math.round(diff / 60_000) + 'm ago';
  if (diff < 86_400_000) return Math.round(diff / 3_600_000) + 'h ago';
  return Math.round(diff / 86_400_000) + 'd ago';
}
function makeFaintC(text) { const e = document.createElement('div'); e.className = 'co-faint'; e.textContent = text; e.style.cssText = 'padding:24px;text-align:center;color:var(--text-faint);'; return e; }
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

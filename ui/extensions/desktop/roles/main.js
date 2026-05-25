/*
 * Roles desktop extension
 *
 * Dedicated landing pane for `/roles` workflow. The Companies & Teams
 * extension already manages roles inline, but the web app's `/roles`
 * surface is a top-level page that lists default *and* custom roles
 * together. This extension mirrors that — no company picker required —
 * and links into Companies & Teams for member assignment.
 *
 * Capabilities:
 *   - List default (system) roles with permission counts
 *   - Edit default role scopes (super admin only; role id 0 locked)
 *   - List custom roles for the active company
 *   - Create / edit / delete custom roles
 *
 * Backend endpoints:
 *   GET    /v1/default-roles                          system roles
 *   PUT    /v1/default-roles/{role_id}/scopes         update default scopes
 *   GET    /v1/scopes                                 scope catalog
 *   GET    /v1/roles?company_id={id}                 list custom roles
 *   POST   /v1/roles?company_id={id}                 create custom role
 *   PUT    /v1/roles/{role_id}                       update custom role
 *   DELETE /v1/roles/{role_id}                       delete custom role
 */
(function () {
  const ROLE_NAMES = {
    0: 'Super Admin', 1: 'Owner', 2: 'Admin', 3: 'Manager',
    4: 'User', 5: 'Chat User', 6: 'Read Only',
  };

  function escR(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function RolesView(container, ctx) {
    this.container = container;
    this.ctx = ctx;
    this.defaultRoles = [];
    this.customRoles = [];
    this.userScopes = new Set();
    this.roleId = null;
    this.activeCompanyId = ctx && ctx.companyId ? String(ctx.companyId) : '';
    this.companies = [];
    this.companyNameById = {};
  }

  RolesView.prototype.start = function () {
    this.injectStyles();
    this.render();
    this.bootstrap();
  };
  RolesView.prototype.stop = function () { this.container.innerHTML = ''; };

  RolesView.prototype.fetchJson = async function (path, opts) {
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
    if (!resp.ok) {
      if (window.AgixtSession && typeof window.AgixtSession.routeFailureStatus === 'function') {
        try { await window.AgixtSession.routeFailureStatus(resp.status, data); } catch (_) {}
      }
      const err = new Error((data && data.detail) || ('HTTP ' + resp.status));
      err.status = resp.status;
      throw err;
    }
    return data;
  };

  RolesView.prototype.isSuperAdmin = function () {
    if (Number(this.roleId) === 0) return true;
    return this.userScopes.has('*') || this.userScopes.has('*:*');
  };
  RolesView.prototype.isCompanyAdmin = function () {
    if (Number(this.roleId) === 0 || Number(this.roleId) === 1 || Number(this.roleId) === 2) return true;
    return this.userScopes.has('company:admin') || this.userScopes.has('roles:write');
  };
  RolesView.prototype.canViewRolesPage = function () {
    const roleId = Number(this.roleId);
    return Number.isFinite(roleId) && roleId <= 2;
  };
  RolesView.prototype.canManageCustomRoles = function () {
    const roleId = Number(this.roleId);
    if (Number.isFinite(roleId) && roleId <= 1) return true;
    return this.userScopes.has('*') || this.userScopes.has('*:*') || this.userScopes.has('roles:write');
  };
  RolesView.prototype.visibleDefaultRoles = function () {
    if (this.isSuperAdmin()) return this.defaultRoles || [];
    const roleId = Number(this.roleId);
    if (!Number.isFinite(roleId) || roleId > 2) return [];
    return (this.defaultRoles || []).filter((r) => Number(r.id) >= roleId);
  };

  RolesView.prototype.bootstrap = async function () {
    await Promise.all([this.loadUserAndScopes(), this.loadCompanies()]);
    await Promise.all([this.loadDefaultRoles(), this.loadCustomRoles()]);
    this.renderBody();
  };

  RolesView.prototype.loadUserAndScopes = async function () {
    try {
      const u = await this.fetchJson('/v1/user');
      const cos = u.companies || [];
      const co = cos.find((c) => c.id === this.activeCompanyId) || cos[0];
      if (co) {
        this.userScopes = new Set(co.scopes || []);
        this.roleId = co.role_id != null ? co.role_id : null;
        if (!this.activeCompanyId) this.activeCompanyId = String(co.id);
      }
    } catch (_) {}
  };

  RolesView.prototype.loadCompanies = async function () {
    try {
      const data = await this.fetchJson('/v1/companies');
      const list = Array.isArray(data) ? data : (data && data.companies) || [];
      this.companies = list;
      this.companyNameById = {};
      list.forEach((c) => { this.companyNameById[c.id] = c.name; });
    } catch (_) { /* leave defaults */ }
  };

  RolesView.prototype.loadDefaultRoles = async function () {
    try {
      const data = await this.fetchJson('/v1/default-roles');
      const list = (data && (data.roles || data.default_roles)) || data || [];
      this.defaultRoles = Array.isArray(list) ? list : [];
    } catch (_) { this.defaultRoles = []; }
  };

  RolesView.prototype.loadCustomRoles = async function () {
    if (!this.activeCompanyId) { this.customRoles = []; return; }
    try {
      const data = await this.fetchJson('/v1/roles?company_id=' + encodeURIComponent(this.activeCompanyId));
      const list = (data && (data.roles || data.custom_roles)) || data || [];
      this.customRoles = Array.isArray(list) ? list : [];
    } catch (_) { this.customRoles = []; }
  };

  RolesView.prototype.render = function () {
    this.container.innerHTML = '';
    const root = document.createElement('div');
    root.className = 'rl-root';
    this.headerEl = document.createElement('header');
    this.headerEl.className = 'rl-header';
    this.bodyEl = document.createElement('div');
    this.bodyEl.className = 'rl-body';
    this.bodyEl.innerHTML = '<div class="rl-loading">Loading roles…</div>';
    this.errorEl = document.createElement('div');
    this.errorEl.className = 'rl-error';
    this.errorEl.hidden = true;
    root.appendChild(this.headerEl);
    root.appendChild(this.errorEl);
    root.appendChild(this.bodyEl);
    this.container.appendChild(root);
  };

  RolesView.prototype.renderHeader = function () {
    if (!this.headerEl) return;
    this.headerEl.innerHTML = '';
    const intro = document.createElement('div');
    intro.className = 'rl-header-intro';
    intro.innerHTML = '<h1>Roles</h1>'
      + '<p>Built-in system roles apply server-wide. Custom roles bundle scopes into reusable permission sets you can assign to members of the active company.</p>';
    this.headerEl.appendChild(intro);

    const right = document.createElement('div');
    right.className = 'rl-header-right';
    if (this.companies.length > 1) {
      const label = document.createElement('label');
      label.className = 'rl-company-picker';
      label.innerHTML = '<span>Custom roles for</span>';
      const sel = document.createElement('select');
      this.companies.forEach((c) => {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = c.name || c.id;
        if (String(c.id) === this.activeCompanyId) opt.selected = true;
        sel.appendChild(opt);
      });
      sel.addEventListener('change', async () => {
        this.activeCompanyId = sel.value;
        await this.loadCustomRoles();
        this.renderBody();
      });
      label.appendChild(sel);
      right.appendChild(label);
    }
    if (this.canManageCustomRoles() && this.activeCompanyId) {
      const newBtn = document.createElement('button');
      newBtn.type = 'button';
      newBtn.className = 'rl-primary';
      newBtn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg><span>New custom role</span>';
      newBtn.addEventListener('click', () => this.openCustomRoleEditor(null));
      right.appendChild(newBtn);
    }
    this.headerEl.appendChild(right);
  };

  RolesView.prototype.renderBody = function () {
    this.renderHeader();
    if (!this.bodyEl) return;
    this.bodyEl.innerHTML = '';
    if (!this.canViewRolesPage()) {
      this.bodyEl.appendChild(this.makeEmpty('Roles are only available to company admins and above.'));
      return;
    }
    this.bodyEl.appendChild(this.renderDefaultRolesSection());
    this.bodyEl.appendChild(this.renderCustomRolesSection());
  };

  RolesView.prototype.renderDefaultRolesSection = function () {
    const card = document.createElement('section');
    card.className = 'rl-section';
    card.innerHTML = ''
      + '<header class="rl-section-head">'
      + '<div><h2>System roles</h2>'
      + '<p>Built-in roles applied to every user platform-wide. ' + (this.isSuperAdmin() ? 'Edit scopes to change what each role can do everywhere.' : 'Showing your role and lower-privilege roles only.') + '</p></div>'
      + '</header>';
    const list = document.createElement('div');
    list.className = 'rl-grid';
    const visibleRoles = this.visibleDefaultRoles();
    if (!visibleRoles.length) {
      list.appendChild(this.makeEmpty('No system roles returned by the server.'));
    } else {
      visibleRoles.forEach((r) => list.appendChild(this.renderDefaultRoleTile(r)));
    }
    card.appendChild(list);
    return card;
  };

  RolesView.prototype.renderDefaultRoleTile = function (r) {
    const locked = Number(r.id) === 0;
    const tile = document.createElement('article');
    tile.className = 'rl-tile rl-tile-default' + (locked ? ' is-locked' : '');
    const count = (r.scopes && r.scopes.length) || 0;
    const label = r.friendly_name || r.name || ROLE_NAMES[r.id] || ('Role ' + r.id);
    tile.innerHTML = ''
      + '<div class="rl-tile-icon">' + this.iconForRole(r.id, locked) + '</div>'
      + '<div class="rl-tile-body">'
      + '<div class="rl-tile-title-row">'
      + '<div class="rl-tile-title">' + escR(label) + '</div>'
      + (locked
          ? '<span class="rl-chip rl-chip-locked">🔒 Locked</span>'
          : '<span class="rl-chip rl-chip-system">System</span>')
      + '</div>'
      + '<div class="rl-tile-meta">'
      + '<span class="rl-tile-count">' + count + ' permission' + (count === 1 ? '' : 's') + '</span>'
      + ' · <code>' + escR(r.name || '') + '</code>'
      + '</div>'
      + '</div>';
    const actions = document.createElement('div');
    actions.className = 'rl-tile-actions';
    const editBtn = document.createElement('button');
    editBtn.type = 'button';
    editBtn.className = locked ? 'rl-secondary' : 'rl-secondary';
    editBtn.textContent = locked ? 'View' : 'Edit scopes';
    editBtn.disabled = !this.isSuperAdmin() && !locked;
    if (!this.isSuperAdmin() && !locked) {
      editBtn.title = 'Super admin only';
    }
    editBtn.addEventListener('click', () => this.openDefaultRoleEditor(r));
    actions.appendChild(editBtn);
    tile.appendChild(actions);
    return tile;
  };

  RolesView.prototype.iconForRole = function (id, locked) {
    if (locked) {
      return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        + '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>';
    }
    return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
      + '<path d="M12 2L4 6v6c0 5 3.4 9.4 8 10 4.6-.6 8-5 8-10V6l-8-4z"/></svg>';
  };

  RolesView.prototype.renderCustomRolesSection = function () {
    const card = document.createElement('section');
    card.className = 'rl-section';
    const company = this.companyNameById[this.activeCompanyId] || 'the active company';
    card.innerHTML = ''
      + '<header class="rl-section-head">'
      + '<div><h2>Custom roles</h2>'
      + '<p>Reusable permission sets layered on top of the default role. Members of <strong>' + escR(company) + '</strong> can be assigned one or more custom roles.</p></div>'
      + '</header>';
    const list = document.createElement('div');
    list.className = 'rl-grid';
    if (!this.customRoles.length) {
      list.appendChild(this.makeEmpty(
        this.canManageCustomRoles() && this.activeCompanyId
          ? 'No custom roles yet — click "New custom role" to define one.'
          : 'No custom roles defined for this company.'
      ));
    } else {
      this.customRoles.forEach((r) => list.appendChild(this.renderCustomRoleTile(r)));
    }
    card.appendChild(list);
    return card;
  };

  RolesView.prototype.renderCustomRoleTile = function (r) {
    const tile = document.createElement('article');
    tile.className = 'rl-tile rl-tile-custom' + (r.is_active === false ? ' is-inactive' : '');
    const count = (r.scopes && r.scopes.length) || 0;
    const label = r.friendly_name || r.name || ('Role ' + (r.id || ''));
    tile.innerHTML = ''
      + '<div class="rl-tile-icon rl-tile-icon-custom">'
      + '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
      + '<path d="M12 2L4 6v6c0 5 3.4 9.4 8 10 4.6-.6 8-5 8-10V6l-8-4z"/>'
      + '<path d="m9 12 2 2 4-4"/></svg>'
      + '</div>'
      + '<div class="rl-tile-body">'
      + '<div class="rl-tile-title-row">'
      + '<div class="rl-tile-title">' + escR(label) + '</div>'
      + (r.is_active === false ? '<span class="rl-chip rl-chip-muted">Inactive</span>' : '<span class="rl-chip rl-chip-custom">Custom</span>')
      + '</div>'
      + (r.description ? '<p class="rl-tile-desc">' + escR(r.description) + '</p>' : '')
      + '<div class="rl-tile-meta">'
      + '<span class="rl-tile-count">' + count + ' permission' + (count === 1 ? '' : 's') + '</span>'
      + ' · <code>' + escR(r.name || '') + '</code>'
      + '</div>'
      + '</div>';
    const actions = document.createElement('div');
    actions.className = 'rl-tile-actions';
    if (this.canManageCustomRoles()) {
      const editBtn = document.createElement('button');
      editBtn.type = 'button';
      editBtn.className = 'rl-secondary';
      editBtn.textContent = 'Edit';
      editBtn.addEventListener('click', () => this.openCustomRoleEditor(r));
      actions.appendChild(editBtn);
      const delBtn = document.createElement('button');
      delBtn.type = 'button';
      delBtn.className = 'rl-danger';
      delBtn.textContent = 'Delete';
      delBtn.addEventListener('click', () => this.deleteCustomRole(r));
      actions.appendChild(delBtn);
    }
    tile.appendChild(actions);
    return tile;
  };

  RolesView.prototype.makeEmpty = function (text) {
    const e = document.createElement('div');
    e.className = 'rl-empty';
    e.textContent = text;
    return e;
  };

  RolesView.prototype.renderError = function (err) {
    if (!this.errorEl) return;
    if (!err) { this.errorEl.hidden = true; this.errorEl.textContent = ''; return; }
    this.errorEl.hidden = false;
    this.errorEl.textContent = (err && (err.detail || err.message)) || 'Request failed.';
  };

  // ── Editors ────────────────────────────────────────────────────────

  RolesView.prototype.loadScopes = async function () {
    if (this._scopesCache) return this._scopesCache;
    try {
      const data = await this.fetchJson('/v1/scopes');
      const arr = (data && (data.scopes || data)) || [];
      this._scopesCache = Array.isArray(arr) ? arr : [];
    } catch (_) { this._scopesCache = []; }
    return this._scopesCache;
  };

  RolesView.prototype.openDefaultRoleEditor = async function (role) {
    const view = this;
    const roleId = Number(role && role.id);
    const locked = roleId === 0;
    if (!locked && !this.isSuperAdmin()) {
      this.renderError(new Error('Only super admins can edit default roles.'));
      return;
    }
    const allScopes = await this.loadScopes();
    const groups = {};
    (allScopes || []).forEach((s) => {
      const cat = s.category || 'Other';
      (groups[cat] = groups[cat] || []).push(s);
    });
    const categoryNames = Object.keys(groups).sort();
    const originalScopeIds = new Set((role && role.scopes ? role.scopes : []).map((s) => s.id));
    const selectedScopeIds = new Set(originalScopeIds);

    const overlay = document.createElement('div');
    overlay.className = 'rl-modal-overlay';
    const card = document.createElement('div');
    card.className = 'rl-modal rl-modal-wide';
    overlay.appendChild(card);
    card.innerHTML = ''
      + '<header class="rl-modal-head">'
      + '<div>'
      + '<h3>' + (locked ? 'View' : 'Edit') + ' ' + escR(role.friendly_name || role.name || ('role ' + roleId)) + '</h3>'
      + '<p class="rl-modal-desc">'
      + (locked
          ? 'The Super Admin role always has every permission and cannot be modified.'
          : 'Edits apply to every user with this default role.')
      + '</p>'
      + '</div>'
      + '<button type="button" class="rl-modal-x" aria-label="Close">×</button>'
      + '</header>'
      + '<div class="rl-modal-body">'
      + (locked ? '<div class="rl-lock-banner"><span>🔒</span><div><strong>Locked by the server</strong><p>Use a custom role or a different default role to scope access for a specific user.</p></div></div>' : '')
      + '<div class="rl-scope-head">'
      + '<span class="rl-scope-head-label">Permissions / scopes</span>'
      + '<span class="rl-scope-count" data-role="count"></span>'
      + '</div>'
      + '<div class="rl-scope-list" data-role="scopes"></div>'
      + '</div>'
      + '<footer class="rl-modal-foot">'
      + '<span class="rl-unsaved" data-role="unsaved" hidden></span>'
      + '<button type="button" class="rl-secondary" data-role="cancel">Cancel</button>'
      + '<button type="button" class="rl-primary" data-role="save" disabled>Save changes</button>'
      + '</footer>';
    document.body.appendChild(overlay);
    const close = () => { if (overlay.parentElement) overlay.parentElement.removeChild(overlay); };
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
    card.querySelector('.rl-modal-x').addEventListener('click', close);
    card.querySelector('[data-role="cancel"]').addEventListener('click', close);
    const saveBtn = card.querySelector('[data-role="save"]');
    const countEl = card.querySelector('[data-role="count"]');
    const unsavedEl = card.querySelector('[data-role="unsaved"]');
    const scopesEl = card.querySelector('[data-role="scopes"]');

    function changed() {
      if (originalScopeIds.size !== selectedScopeIds.size) return true;
      for (const id of originalScopeIds) if (!selectedScopeIds.has(id)) return true;
      return false;
    }
    function refresh() {
      const total = (allScopes && allScopes.length) || 0;
      countEl.textContent = selectedScopeIds.size + (total ? ' / ' + total : '') + ' selected';
      const dirty = changed();
      saveBtn.disabled = locked || !dirty;
      if (locked) { unsavedEl.hidden = true; return; }
      const n = Math.abs(selectedScopeIds.size - originalScopeIds.size)
        + Array.from(selectedScopeIds).filter((id) => !originalScopeIds.has(id)).length
        + Array.from(originalScopeIds).filter((id) => !selectedScopeIds.has(id)).length;
      // De-dup overlap.
      const totalDirty = (function () {
        let d = 0;
        const all = new Set([...originalScopeIds, ...selectedScopeIds]);
        all.forEach((id) => {
          if (originalScopeIds.has(id) !== selectedScopeIds.has(id)) d += 1;
        });
        return d;
      }());
      if (!dirty) { unsavedEl.hidden = true; unsavedEl.textContent = ''; return; }
      unsavedEl.hidden = false;
      unsavedEl.textContent = totalDirty + ' unsaved change' + (totalDirty === 1 ? '' : 's');
    }
    function renderScopes() {
      scopesEl.innerHTML = '';
      if (!categoryNames.length) {
        scopesEl.appendChild(view.makeEmpty('Could not load scopes.'));
        return;
      }
      categoryNames.forEach((cat) => {
        const catScopes = groups[cat];
        const catIds = catScopes.map((s) => s.id);
        const selCount = catIds.filter((id) => selectedScopeIds.has(id)).length;
        const all = catIds.length > 0 && selCount === catIds.length;
        const row = document.createElement('label');
        row.className = 'rl-cat-row' + (all ? ' is-all' : (selCount > 0 ? ' is-some' : ''));
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = all;
        cb.indeterminate = selCount > 0 && !all;
        cb.disabled = locked;
        cb.addEventListener('change', () => {
          catScopes.forEach((s) => {
            if (cb.checked) selectedScopeIds.add(s.id);
            else selectedScopeIds.delete(s.id);
          });
          renderScopes(); refresh();
        });
        const title = document.createElement('span');
        title.className = 'rl-cat-title';
        title.textContent = cat;
        const count = document.createElement('span');
        count.className = 'rl-cat-count';
        count.textContent = selCount + '/' + catIds.length;
        row.appendChild(cb);
        row.appendChild(title);
        row.appendChild(count);
        scopesEl.appendChild(row);
        catScopes.forEach((s) => {
          const isChecked = selectedScopeIds.has(s.id);
          const isChanged = originalScopeIds.has(s.id) !== isChecked;
          const r = document.createElement('label');
          r.className = 'rl-scope-row' + (isChecked ? ' is-checked' : '') + (isChanged ? ' is-changed' : '');
          const c = document.createElement('input');
          c.type = 'checkbox';
          c.checked = isChecked;
          c.disabled = locked;
          c.addEventListener('change', () => {
            if (c.checked) selectedScopeIds.add(s.id);
            else selectedScopeIds.delete(s.id);
            renderScopes(); refresh();
          });
          r.appendChild(c);
          const det = document.createElement('div');
          det.innerHTML = '<code>' + escR(s.name) + '</code>'
            + (isChanged ? ' <span class="rl-mod-pill">modified</span>' : '')
            + (s.description ? '<div class="rl-scope-desc">' + escR(s.description) + '</div>' : '');
          r.appendChild(det);
          scopesEl.appendChild(r);
        });
      });
    }
    saveBtn.addEventListener('click', async () => {
      if (locked || !changed()) return;
      saveBtn.disabled = true;
      try {
        await view.fetchJson('/v1/default-roles/' + encodeURIComponent(roleId) + '/scopes', {
          method: 'PUT', json: Array.from(selectedScopeIds),
        });
        view.renderError(null);
        close();
        await view.loadDefaultRoles();
        view.renderBody();
      } catch (err) {
        saveBtn.disabled = false;
        view.renderError(err);
      }
    });
    renderScopes();
    refresh();
  };

  RolesView.prototype.openCustomRoleEditor = async function (role) {
    if (!this.activeCompanyId) {
      this.renderError(new Error('Select a company first.'));
      return;
    }
    if (!this.canManageCustomRoles()) {
      this.renderError(new Error('You need roles:write permission to manage custom roles.'));
      return;
    }
    const view = this;
    const isCreate = !role;
    const allScopes = await this.loadScopes();
    const groups = {};
    (allScopes || []).forEach((s) => {
      const cat = s.category || 'Other';
      (groups[cat] = groups[cat] || []).push(s);
    });
    const categoryNames = Object.keys(groups).sort();
    const selectedScopeIds = new Set((role && role.scopes ? role.scopes : []).map((s) => s.id));
    const originalScopeIds = new Set(selectedScopeIds);
    const fields = {
      name: role ? (role.name || '') : '',
      friendly_name: role ? (role.friendly_name || '') : '',
      description: role ? (role.description || '') : '',
      is_active: role ? (role.is_active !== false) : true,
    };

    const overlay = document.createElement('div');
    overlay.className = 'rl-modal-overlay';
    const card = document.createElement('div');
    card.className = 'rl-modal rl-modal-wide';
    overlay.appendChild(card);
    card.innerHTML = ''
      + '<header class="rl-modal-head">'
      + '<div>'
      + '<h3>' + (isCreate ? 'New custom role' : 'Edit ' + escR(fields.friendly_name || fields.name || 'role')) + '</h3>'
      + '<p class="rl-modal-desc">Custom roles layer extra permissions on top of a member\'s default role. They apply only to this company.</p>'
      + '</div>'
      + '<button type="button" class="rl-modal-x" aria-label="Close">×</button>'
      + '</header>'
      + '<div class="rl-modal-body">'
      + '<div class="rl-form-grid">'
      + '<label class="rl-field">'
      + '<span>Slug (machine-readable)</span>'
      + '<input type="text" data-field="name" value="' + escR(fields.name) + '" placeholder="e.g. invoice_approver" ' + (isCreate ? '' : 'readonly') + ' />'
      + '</label>'
      + '<label class="rl-field">'
      + '<span>Display name</span>'
      + '<input type="text" data-field="friendly_name" value="' + escR(fields.friendly_name) + '" placeholder="e.g. Invoice approver" />'
      + '</label>'
      + '<label class="rl-field rl-field-wide">'
      + '<span>Description</span>'
      + '<textarea data-field="description" rows="2" placeholder="What does this role unlock? Who should hold it?">' + escR(fields.description) + '</textarea>'
      + '</label>'
      + '<label class="rl-field rl-field-check">'
      + '<input type="checkbox" data-field="is_active" ' + (fields.is_active ? 'checked' : '') + ' />'
      + '<span>Active — assignable to members</span>'
      + '</label>'
      + '</div>'
      + '<div class="rl-scope-head">'
      + '<span class="rl-scope-head-label">Scopes granted</span>'
      + '<span class="rl-scope-count" data-role="count"></span>'
      + '</div>'
      + '<div class="rl-scope-list" data-role="scopes"></div>'
      + '</div>'
      + '<footer class="rl-modal-foot">'
      + '<span class="rl-unsaved" data-role="unsaved" hidden></span>'
      + '<button type="button" class="rl-secondary" data-role="cancel">Cancel</button>'
      + '<button type="button" class="rl-primary" data-role="save">' + (isCreate ? 'Create role' : 'Save changes') + '</button>'
      + '</footer>';
    document.body.appendChild(overlay);
    const close = () => { if (overlay.parentElement) overlay.parentElement.removeChild(overlay); };
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
    card.querySelector('.rl-modal-x').addEventListener('click', close);
    card.querySelector('[data-role="cancel"]').addEventListener('click', close);
    const saveBtn = card.querySelector('[data-role="save"]');
    const countEl = card.querySelector('[data-role="count"]');
    const unsavedEl = card.querySelector('[data-role="unsaved"]');
    const scopesEl = card.querySelector('[data-role="scopes"]');
    function refresh() {
      const total = (allScopes && allScopes.length) || 0;
      countEl.textContent = selectedScopeIds.size + (total ? ' / ' + total : '') + ' selected';
      const totalDirty = (function () {
        let d = 0;
        const all = new Set([...originalScopeIds, ...selectedScopeIds]);
        all.forEach((id) => {
          if (originalScopeIds.has(id) !== selectedScopeIds.has(id)) d += 1;
        });
        return d;
      }());
      if (totalDirty === 0 && !isCreate) { unsavedEl.hidden = true; unsavedEl.textContent = ''; return; }
      unsavedEl.hidden = false;
      unsavedEl.textContent = isCreate
        ? selectedScopeIds.size + ' scope' + (selectedScopeIds.size === 1 ? '' : 's') + ' selected'
        : totalDirty + ' unsaved scope change' + (totalDirty === 1 ? '' : 's');
    }
    function renderScopes() {
      scopesEl.innerHTML = '';
      if (!categoryNames.length) { scopesEl.appendChild(view.makeEmpty('Could not load scopes.')); return; }
      categoryNames.forEach((cat) => {
        const catScopes = groups[cat];
        const catIds = catScopes.map((s) => s.id);
        const selCount = catIds.filter((id) => selectedScopeIds.has(id)).length;
        const all = catIds.length > 0 && selCount === catIds.length;
        const row = document.createElement('label');
        row.className = 'rl-cat-row' + (all ? ' is-all' : (selCount > 0 ? ' is-some' : ''));
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = all;
        cb.indeterminate = selCount > 0 && !all;
        cb.addEventListener('change', () => {
          catScopes.forEach((s) => {
            if (cb.checked) selectedScopeIds.add(s.id);
            else selectedScopeIds.delete(s.id);
          });
          renderScopes(); refresh();
        });
        const title = document.createElement('span');
        title.className = 'rl-cat-title';
        title.textContent = cat;
        const count = document.createElement('span');
        count.className = 'rl-cat-count';
        count.textContent = selCount + '/' + catIds.length;
        row.appendChild(cb); row.appendChild(title); row.appendChild(count);
        scopesEl.appendChild(row);
        catScopes.forEach((s) => {
          const isChecked = selectedScopeIds.has(s.id);
          const r = document.createElement('label');
          r.className = 'rl-scope-row' + (isChecked ? ' is-checked' : '');
          const c = document.createElement('input');
          c.type = 'checkbox';
          c.checked = isChecked;
          c.addEventListener('change', () => {
            if (c.checked) selectedScopeIds.add(s.id);
            else selectedScopeIds.delete(s.id);
            renderScopes(); refresh();
          });
          r.appendChild(c);
          const det = document.createElement('div');
          det.innerHTML = '<code>' + escR(s.name) + '</code>'
            + (s.description ? '<div class="rl-scope-desc">' + escR(s.description) + '</div>' : '');
          r.appendChild(det);
          scopesEl.appendChild(r);
        });
      });
    }
    saveBtn.addEventListener('click', async () => {
      const name = (card.querySelector('[data-field="name"]').value || '').trim();
      const friendly = (card.querySelector('[data-field="friendly_name"]').value || '').trim();
      const description = (card.querySelector('[data-field="description"]').value || '').trim();
      const isActive = !!card.querySelector('[data-field="is_active"]').checked;
      if (isCreate && !name) {
        view.renderError(new Error('Slug is required.'));
        return;
      }
      saveBtn.disabled = true;
      try {
        const body = {
          friendly_name: friendly || (role && role.friendly_name) || name,
          description,
          scope_ids: Array.from(selectedScopeIds),
        };
        if (isCreate) body.name = name;
        else body.is_active = isActive;
        const path = isCreate
          ? '/v1/roles?company_id=' + encodeURIComponent(view.activeCompanyId)
          : '/v1/roles/' + encodeURIComponent(role.id);
        await view.fetchJson(path, { method: isCreate ? 'POST' : 'PUT', json: body });
        view.renderError(null);
        close();
        await view.loadCustomRoles();
        view.renderBody();
      } catch (err) {
        saveBtn.disabled = false;
        view.renderError(err);
      }
    });
    renderScopes();
    refresh();
  };

  RolesView.prototype.deleteCustomRole = async function (r) {
    if (!window.confirm('Delete the "' + (r.friendly_name || r.name || 'this role') + '" custom role? Members assigned to it will lose its permissions.')) return;
    try {
      await this.fetchJson('/v1/roles/' + encodeURIComponent(r.id), { method: 'DELETE' });
      this.renderError(null);
      await this.loadCustomRoles();
      this.renderBody();
    } catch (err) { this.renderError(err); }
  };

  // ── Styles ─────────────────────────────────────────────────────────

  RolesView.prototype.injectStyles = function () {
    if (document.getElementById('rl-styles')) return;
    const css = `
      .rl-root { display: flex; flex-direction: column; gap: 18px; padding: 16px 20px 32px; color: var(--text); min-height: 100%; }
      .rl-header { display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; }
      .rl-header-intro h1 { margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -0.01em; }
      .rl-header-intro p { margin: 4px 0 0; color: var(--text-dim); font-size: 12.5px; max-width: 640px; line-height: 1.5; }
      .rl-header-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
      .rl-company-picker { display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; color: var(--text-dim); }
      .rl-company-picker select { background: var(--panel-2); color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px; font-size: 12.5px; font-family: inherit; cursor: pointer; }
      .rl-primary, .rl-secondary, .rl-danger { appearance: none; font-family: inherit; font-size: 12.5px; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
      .rl-primary { background: var(--accent); color: #fff; border: 1px solid var(--accent); }
      .rl-primary:hover:not(:disabled) { filter: brightness(1.08); }
      .rl-secondary { background: var(--panel-2); color: var(--text); border: 1px solid var(--border); }
      .rl-secondary:hover:not(:disabled) { background: var(--panel); }
      .rl-secondary:disabled { opacity: 0.5; cursor: not-allowed; }
      .rl-danger { background: transparent; color: #ffb4ba; border: 1px solid rgba(220, 60, 80, 0.4); }
      .rl-danger:hover { background: rgba(220, 60, 80, 0.18); }
      .rl-loading { color: var(--text-faint); padding: 20px 4px; font-size: 13px; }
      .rl-error { padding: 10px 14px; border-radius: 8px; font-size: 12.5px; background: rgba(220, 60, 80, 0.18); border: 1px solid rgba(220, 60, 80, 0.4); color: #ffb4ba; }

      .rl-body { display: flex; flex-direction: column; gap: 18px; }
      .rl-section { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; display: flex; flex-direction: column; gap: 12px; }
      .rl-section-head h2 { margin: 0; font-size: 14px; font-weight: 700; }
      .rl-section-head p { margin: 4px 0 0; color: var(--text-dim); font-size: 12px; line-height: 1.5; max-width: 720px; }
      .rl-section-head p strong { color: var(--text); }

      .rl-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }
      .rl-tile { display: flex; gap: 12px; align-items: flex-start; padding: 12px 14px; background: var(--panel-2); border: 1px solid var(--border); border-radius: 10px; transition: border-color 120ms ease, background 120ms ease; }
      .rl-tile:hover { border-color: color-mix(in srgb, var(--accent) 30%, var(--border)); }
      .rl-tile.is-locked { background: color-mix(in srgb, #ffb774 5%, var(--panel-2)); border-color: color-mix(in srgb, #ffb774 26%, var(--border)); }
      .rl-tile.is-inactive { opacity: 0.7; }
      .rl-tile-icon { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 9px; background: color-mix(in srgb, var(--accent) 18%, var(--panel)); color: var(--accent); flex: 0 0 auto; margin-top: 2px; }
      .rl-tile.is-locked .rl-tile-icon { background: color-mix(in srgb, #ffb774 22%, var(--panel)); color: #ffb774; }
      .rl-tile-icon-custom { background: color-mix(in srgb, #b29dff 18%, var(--panel)); color: #b29dff; }
      .rl-tile-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
      .rl-tile-title-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
      .rl-tile-title { font-weight: 600; font-size: 13px; color: var(--text); }
      .rl-tile-desc { margin: 0; color: var(--text-dim); font-size: 11.5px; line-height: 1.5; }
      .rl-tile-meta { font-size: 11px; color: var(--text-faint); display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
      .rl-tile-meta code { font-family: var(--mono); font-size: 10.5px; color: var(--text-dim); background: var(--panel); padding: 1px 5px; border-radius: 4px; border: 1px solid var(--border); }
      .rl-tile-count { font-weight: 700; color: var(--text-dim); font-size: 10.5px; padding: 1px 6px; border-radius: 999px; background: var(--panel); border: 1px solid var(--border); }
      .rl-tile-actions { display: flex; flex-direction: column; gap: 4px; flex: 0 0 auto; align-items: stretch; }

      .rl-chip { display: inline-flex; align-items: center; gap: 3px; font-size: 10px; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; padding: 1px 7px; border-radius: 999px; }
      .rl-chip-system { background: var(--panel); color: var(--text-dim); border: 1px solid var(--border); }
      .rl-chip-locked { background: color-mix(in srgb, #ffb774 14%, transparent); color: #ffb774; border: 1px solid color-mix(in srgb, #ffb774 30%, transparent); }
      .rl-chip-custom { background: color-mix(in srgb, #b29dff 14%, transparent); color: #b29dff; border: 1px solid color-mix(in srgb, #b29dff 30%, transparent); }
      .rl-chip-muted { background: var(--panel); color: var(--text-faint); border: 1px solid var(--border); }

      .rl-empty { padding: 22px 14px; text-align: center; color: var(--text-faint); font-size: 12.5px; border: 1px dashed var(--border); border-radius: 10px; background: var(--panel-2); grid-column: 1 / -1; }

      /* Modal — shared by both default-role and custom-role editors. */
      .rl-modal-overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.55); display: flex; align-items: center; justify-content: center; z-index: 200; padding: 16px; }
      .rl-modal { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; width: 100%; max-width: 560px; max-height: 90vh; display: flex; flex-direction: column; box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4); overflow: hidden; }
      .rl-modal-wide { max-width: 720px; }
      .rl-modal-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; padding: 14px 18px; border-bottom: 1px solid var(--border); }
      .rl-modal-head h3 { margin: 0; font-size: 15px; font-weight: 700; }
      .rl-modal-desc { margin: 4px 0 0; font-size: 12px; color: var(--text-dim); line-height: 1.5; }
      .rl-modal-x { appearance: none; background: transparent; border: 0; color: var(--text-dim); font-size: 22px; line-height: 1; cursor: pointer; padding: 0 6px; }
      .rl-modal-x:hover { color: var(--text); }
      .rl-modal-body { padding: 14px 18px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; }
      .rl-modal-foot { display: flex; justify-content: flex-end; align-items: center; gap: 8px; padding: 12px 18px; border-top: 1px solid var(--border); }
      .rl-unsaved { margin-right: auto; font-size: 11px; font-weight: 700; letter-spacing: 0.3px; padding: 4px 10px; border-radius: 999px; color: #ffb774; background: color-mix(in srgb, #ffb774 14%, transparent); border: 1px solid color-mix(in srgb, #ffb774 32%, transparent); }

      .rl-lock-banner { display: flex; align-items: flex-start; gap: 10px; padding: 10px 12px; border-radius: 9px; background: color-mix(in srgb, #ffb774 10%, var(--panel-2)); border: 1px solid color-mix(in srgb, #ffb774 30%, var(--border)); }
      .rl-lock-banner span { font-size: 18px; }
      .rl-lock-banner strong { display: block; font-size: 12.5px; color: var(--text); }
      .rl-lock-banner p { margin: 3px 0 0; font-size: 12px; color: var(--text-dim); line-height: 1.5; }

      .rl-scope-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
      .rl-scope-head-label { font-size: 10px; font-weight: 600; letter-spacing: 0.6px; color: var(--text-faint); text-transform: uppercase; }
      .rl-scope-count { font-size: 10.5px; font-weight: 700; color: var(--accent); padding: 2px 8px; border-radius: 999px; background: color-mix(in srgb, var(--accent) 14%, transparent); border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent); }
      .rl-scope-list { max-height: 50vh; overflow-y: auto; background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; padding: 4px 8px 8px; }
      .rl-cat-row { position: sticky; top: 0; z-index: 1; background: var(--panel-2); padding: 8px 4px 6px; border-top: 1px solid var(--border-muted); margin: 0 -8px; padding-left: 12px; padding-right: 8px; display: flex; gap: 8px; align-items: center; }
      .rl-cat-row:first-child { border-top: 0; }
      .rl-cat-title { flex: 1; font-weight: 600; font-size: 11.5px; }
      .rl-cat-count { font-size: 10.5px; font-weight: 600; color: var(--text-faint); padding: 1px 7px; border-radius: 999px; background: var(--panel); border: 1px solid var(--border); }
      .rl-cat-row.is-all { color: var(--accent); }
      .rl-cat-row.is-all .rl-cat-count { color: var(--accent); border-color: color-mix(in srgb, var(--accent) 35%, var(--border)); background: color-mix(in srgb, var(--accent) 10%, var(--panel)); }
      .rl-scope-row { display: flex; gap: 8px; align-items: flex-start; padding: 4px 4px 4px 12px; cursor: pointer; border-radius: 5px; }
      .rl-scope-row:hover { background: var(--panel); }
      .rl-scope-row.is-checked { background: color-mix(in srgb, var(--accent) 5%, transparent); }
      .rl-scope-row.is-changed { background: color-mix(in srgb, #ffb774 10%, transparent); }
      .rl-scope-row code { font-family: var(--mono); font-size: 11.5px; color: var(--accent); }
      .rl-scope-desc { font-size: 10.5px; color: var(--text-faint); margin-top: 2px; }
      .rl-mod-pill { display: inline-block; margin-left: 6px; font-size: 9.5px; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; color: #ffb774; padding: 0 5px; border-radius: 4px; background: color-mix(in srgb, #ffb774 16%, transparent); border: 1px solid color-mix(in srgb, #ffb774 32%, transparent); vertical-align: middle; }

      .rl-form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
      .rl-field { display: flex; flex-direction: column; gap: 4px; }
      .rl-field-wide { grid-column: 1 / -1; }
      .rl-field-check { flex-direction: row; align-items: center; gap: 8px; }
      .rl-field-check span { font-size: 12.5px; color: var(--text); }
      .rl-field span { font-size: 10.5px; font-weight: 600; letter-spacing: 0.5px; color: var(--text-faint); text-transform: uppercase; }
      .rl-field input[type=text], .rl-field textarea { background: var(--panel-2); color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 7px 10px; font-family: inherit; font-size: 12.5px; }
      .rl-field input:focus, .rl-field textarea:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(107, 123, 255, 0.18); }
      .rl-field input:read-only { opacity: 0.7; cursor: default; }
    `;
    const tag = document.createElement('style');
    tag.id = 'rl-styles';
    tag.textContent = css;
    document.head.appendChild(tag);
  };

  // Register with the desktop extension host.
  window.AgixtRegisterExtension('roles', {
    mount(container, ctx) {
      const view = new RolesView(container, ctx);
      container._rolesView = view;
      view.start();
    },
    unmount() {
      const pane = document.querySelector('.chat-screen-main .view-pane[data-view="roles"]');
      const target = pane && (pane.querySelector(':scope > .ext-pane-body') || pane);
      const view = target && target._rolesView;
      if (view) view.stop();
    },
  });
})();

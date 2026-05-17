/* Generic desktop extension CRUD/table view.
 *
 * This is intentionally plain DOM. Server-delivered desktop extensions can
 * register a config object and get a functional list/search/create/edit/delete
 * surface without duplicating boilerplate in every product folder.
 */
(function () {
  if (window.AgixtCrudExtension) return;

  function register(config) {
    if (!config || !config.id) throw new Error('AgixtCrudExtension.register requires an id');
    window.AgixtRegisterExtension(config.id, {
      mount(container, ctx) {
        const view = new CrudView(container, ctx, config);
        container._crudView = view;
        view.start();
      },
      unmount() {
        const pane = document.querySelector('.chat-screen-main .view-pane[data-view="' + cssEscape(config.id) + '"]');
        const target = pane && (pane.querySelector(':scope > .ext-pane-body') || pane);
        const view = target && target._crudView;
        if (view) view.stop();
      },
    });
  }

  function CrudView(container, ctx, config) {
    this.container = container;
    this.ctx = ctx;
    this.config = config;
    this.tabs = config.tabs && config.tabs.length ? config.tabs : [config];
    this.active = this.tabs[0].id || 'main';
    this.rowsByTab = {};
    this.rawByTab = {};
    this.search = '';
    this.error = null;
    this.loading = false;
    this.detail = null;
  }

  CrudView.prototype.start = function () {
    injectStyles();
    this.renderShell();
    this.refresh();
  };

  CrudView.prototype.stop = function () {
    if (this.ctx && typeof this.ctx.setHeaderActions === 'function') this.ctx.setHeaderActions();
    this.container.innerHTML = '';
  };

  CrudView.prototype.activeTab = function () {
    return this.tabs.find((t) => (t.id || 'main') === this.active) || this.tabs[0];
  };

  CrudView.prototype.renderShell = function () {
    this.container.innerHTML = '';
    const root = document.createElement('div');
    root.className = 'dc-root';
    this.toolbarEl = document.createElement('div');
    this.toolbarEl.className = 'dc-toolbar';
    this.tabsEl = document.createElement('div');
    this.tabsEl.className = 'dc-tabs';
    this.errorEl = document.createElement('div');
    this.errorEl.className = 'dc-error';
    this.errorEl.hidden = true;
    this.summaryEl = document.createElement('div');
    this.summaryEl.className = 'dc-summary';
    this.tableEl = document.createElement('div');
    this.tableEl.className = 'dc-table-wrap';
    this.detailEl = document.createElement('div');
    this.detailEl.className = 'dc-detail';
    this.detailEl.hidden = true;
    root.appendChild(this.toolbarEl);
    root.appendChild(this.tabsEl);
    root.appendChild(this.errorEl);
    root.appendChild(this.summaryEl);
    root.appendChild(this.tableEl);
    root.appendChild(this.detailEl);
    this.container.appendChild(root);
    this.renderTabs();
    this.renderToolbar();
  };

  CrudView.prototype.renderTabs = function () {
    this.tabsEl.innerHTML = '';
    if (this.tabs.length <= 1) {
      this.tabsEl.hidden = true;
      return;
    }
    this.tabsEl.hidden = false;
    for (const tab of this.tabs) {
      const id = tab.id || 'main';
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'dc-tab' + (id === this.active ? ' is-active' : '');
      btn.textContent = tab.label || id;
      btn.addEventListener('click', () => {
        if (this.active === id) return;
        this.active = id;
        this.detail = null;
        this.renderTabs();
        this.renderToolbar();
        if (this.rowsByTab[id]) this.renderData();
        else this.refresh();
      });
      this.tabsEl.appendChild(btn);
    }
  };

  CrudView.prototype.renderToolbar = function () {
    const tab = this.activeTab();

    // Build header chips (these go to the host pane header bar via
    // ctx.setHeaderActions when available — same pattern as patches/secrets/etc).
    const search = document.createElement('input');
    search.type = 'search';
    search.className = 'dc-search';
    search.placeholder = tab.searchPlaceholder || 'Search ' + (tab.label || 'records').toLowerCase() + '...';
    search.value = this.search;
    search.addEventListener('input', (e) => {
      this.search = e.target.value;
      this.renderData();
    });

    // Header buttons render the icon + a hidden visually-textual label so
    // the chip cluster stays compact while the textContent (used by tests
    // and accessible tools) still reads as "Refresh" / "Export CSV".
    const refresh = button(refreshIcon() + '<span class="dc-btn-label">Refresh</span>', 'dc-btn dc-btn-iconish', () => this.refresh());
    refresh.title = 'Refresh';
    refresh.setAttribute('aria-label', 'Refresh');

    const exportBtn = button(downloadIcon() + '<span class="dc-btn-label">Export CSV</span>', 'dc-btn dc-btn-iconish', () => this.exportCsv());
    exportBtn.title = 'Export CSV';
    exportBtn.setAttribute('aria-label', 'Export CSV');

    const headerNodes = [search, refresh, exportBtn];
    for (const action of tab.globalActions || []) {
      const cls = action.danger ? 'dc-btn dc-btn-danger' : 'dc-btn';
      headerNodes.push(button(action.label || 'Action', cls, () => this.runAction(action, null)));
    }
    if (tab.create !== false && tab.fields && tab.fields.length) {
      headerNodes.push(button(addIcon() + (tab.createLabel || 'New ' + (tab.singular || 'record')), 'dc-primary', () => this.openForm('create')));
    }

    if (this.ctx && typeof this.ctx.setHeaderActions === 'function') {
      this.ctx.setHeaderActions.apply(null, headerNodes);
      // Hide the in-body toolbar — the host header carries everything.
      this.toolbarEl.hidden = true;
      this.toolbarEl.innerHTML = '';
      return;
    }

    // Fallback (test rigs / unframed mounts): render an in-body toolbar.
    this.toolbarEl.hidden = false;
    this.toolbarEl.innerHTML = '';
    const left = document.createElement('div');
    left.className = 'dc-toolbar-left';
    left.appendChild(search);
    const right = document.createElement('div');
    right.className = 'dc-toolbar-right';
    for (let i = 1; i < headerNodes.length; i++) right.appendChild(headerNodes[i]);
    this.toolbarEl.appendChild(left);
    this.toolbarEl.appendChild(right);
  };

  CrudView.prototype.fetchJson = async function (path, opts) {
    opts = opts || {};
    const url = this.buildPath(path, opts.query);
    if (this.ctx && typeof this.ctx.fetchJson === 'function') {
      return this.ctx.fetchJson(url, opts);
    }
    if (window.AgixtSession && typeof window.AgixtSession.request === 'function') {
      return window.AgixtSession.request(url, opts);
    }
    const init = {
      method: opts.method || 'GET',
      headers: Object.assign({ Authorization: 'Bearer ' + this.ctx.jwt }, opts.headers || {}),
    };
    if (opts.json !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(opts.json);
    } else if (opts.body !== undefined) {
      init.body = opts.body;
    }
    const resp = await fetch(new URL(url, this.ctx.serverUrl).toString(), init);
    const text = await resp.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (_) { data = text; }
    if (!resp.ok) {
      if (window.AgixtSession && typeof window.AgixtSession.routeFailureStatus === 'function') {
        try { await window.AgixtSession.routeFailureStatus(resp.status, data); } catch (_) {}
      }
      const err = new Error(data && data.detail ? data.detail : 'HTTP ' + resp.status);
      err.status = resp.status;
      throw err;
    }
    return data;
  };

  CrudView.prototype.buildPath = function (path, query) {
    const tab = this.activeTab();
    const q = Object.assign({}, query || {});
    if (tab.companyQuery && this.ctx.companyId && !q.company_id) q.company_id = this.ctx.companyId;
    const keys = Object.keys(q).filter((k) => q[k] != null && q[k] !== '');
    if (!keys.length) return path;
    const sep = path.indexOf('?') >= 0 ? '&' : '?';
    return path + sep + keys.map((k) => encodeURIComponent(k) + '=' + encodeURIComponent(q[k])).join('&');
  };

  CrudView.prototype.refresh = async function () {
    const tab = this.activeTab();
    // Custom-render tabs skip the list fetch entirely — the renderer
    // is responsible for its own data loading inside its panel. This
    // lets dashboard-shaped surfaces (status cards, multi-source
    // grids) live next to row-shaped tabs in the same extension
    // without forcing them through the table layout.
    if (typeof tab.customRender === 'function') {
      this.loading = false;
      this.error = null;
      this.renderData();
      return;
    }
    this.loading = true;
    this.error = null;
    this.renderData();
    try {
      const raw = await this.fetchJson(tab.endpoint || tab.listPath || '/');
      this.rawByTab[tab.id || 'main'] = raw;
      this.rowsByTab[tab.id || 'main'] = extractRows(raw, tab.listKey);
      this.error = null;
    } catch (err) {
      this.error = err;
      this.rowsByTab[tab.id || 'main'] = [];
    } finally {
      this.loading = false;
      this.renderData();
    }
  };

  CrudView.prototype.filteredRows = function () {
    const tab = this.activeTab();
    const rows = (this.rowsByTab[tab.id || 'main'] || []).slice();
    const q = (this.search || '').trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((row) => {
      const hay = tab.searchKeys && tab.searchKeys.length
        ? tab.searchKeys.map((k) => valueAt(row, k)).join(' ')
        : JSON.stringify(row);
      return String(hay || '').toLowerCase().indexOf(q) >= 0;
    });
  };

  CrudView.prototype.renderData = function () {
    if (!this.tableEl) return;
    this.renderError();
    const tab = this.activeTab();
    if (typeof tab.customRender === 'function') {
      // Suppress the summary strip — the custom renderer paints its
      // own status surface and the generic numbers would just be
      // duplicate visual noise.
      if (this.summaryEl) this.summaryEl.innerHTML = '';
      this.tableEl.innerHTML = '';
      const helpers = {
        fetchJson: (p, o) => this.fetchJson(p, o),
        refresh: () => this.refresh(),
        ctx: this.ctx,
        tab,
        openSidenavView: (id) => {
          if (window.AgixtSidenav && typeof window.AgixtSidenav.setActiveView === 'function') {
            window.AgixtSidenav.setActiveView(id);
          }
        },
      };
      const out = tab.customRender(this.tableEl, helpers);
      if (out instanceof Node) this.tableEl.appendChild(out);
      else if (typeof out === 'string') this.tableEl.innerHTML = out;
      return;
    }
    this.renderSummary();
    if (this.loading) {
      this.tableEl.innerHTML = renderSkeleton(tab);
      return;
    }
    const rows = this.filteredRows();
    const columns = tab.columns && tab.columns.length ? tab.columns : inferColumns(rows);
    if (!rows.length) {
      this.tableEl.innerHTML = renderEmpty(tab, !!this.search);
      const cta = this.tableEl.querySelector('[data-empty-action]');
      if (cta) cta.addEventListener('click', () => this.openForm('create'));
      return;
    }
    const headers = columns.map((c) => '<th class="' + (c.align === 'right' ? 'dc-th dc-th-right' : 'dc-th') + '">' + esc(c.label || c.key) + '</th>').join('');
    const body = rows.map((row) => this.rowHtml(row, columns)).join('');
    this.tableEl.innerHTML = '<table class="dc-table"><thead><tr>' + headers + '<th class="dc-th dc-th-actions"></th></tr></thead><tbody>' + body + '</tbody></table>';
    this.tableEl.querySelectorAll('tbody tr').forEach((tr) => {
      tr.addEventListener('click', (e) => {
        if (e.target && (e.target.tagName === 'BUTTON' || e.target.closest('button'))) return;
        const row = rows[Number(tr.dataset.index)];
        if (row) this.showDetail(row);
      });
    });
    this.tableEl.querySelectorAll('button[data-action]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const row = rows[Number(btn.dataset.index)];
        const action = btn.dataset.action;
        if (action === 'detail') return this.showDetail(row);
        if (action === 'edit') return this.openForm('edit', row);
        if (action === 'delete') return this.deleteRow(row);
        const cfg = (tab.actions || []).find((a) => safeActionId(a) === action);
        if (cfg) return this.runAction(cfg, row);
      });
    });
  };

  CrudView.prototype.renderSummary = function () {
    const tab = this.activeTab();
    const rows = this.rowsByTab[tab.id || 'main'] || [];
    const raw = this.rawByTab[tab.id || 'main'];
    const cards = [];
    if (tab.showRecordCount !== false) {
      cards.push({ label: tab.recordsLabel || 'Records', value: rows.length, hint: tab.recordsHint || '' });
    }
    for (const card of tab.summary || []) {
      let val = typeof card.value === 'function' ? card.value(rows, raw) : valueAt(raw, card.value);
      if (val == null || val === '') val = '0';
      cards.push({ label: card.label, value: val, hint: card.hint || '', tone: card.tone || cardTone(card.label) });
    }
    if (!cards.length) { this.summaryEl.innerHTML = ''; this.summaryEl.hidden = true; return; }
    this.summaryEl.hidden = false;
    this.summaryEl.innerHTML = cards.map((c) => (
      '<div class="dc-stat' + (c.tone ? ' dc-stat-' + c.tone : '') + '">'
        + '<div class="dc-stat-label">' + esc(c.label) + '</div>'
        + '<div class="dc-stat-value">' + esc(c.value) + '</div>'
        + (c.hint ? '<div class="dc-stat-hint">' + esc(c.hint) + '</div>' : '')
      + '</div>'
    )).join('');
  };

  CrudView.prototype.renderError = function () {
    if (!this.errorEl) return;
    if (!this.error) {
      this.errorEl.hidden = true;
      this.errorEl.innerHTML = '';
      return;
    }
    this.errorEl.hidden = false;
    const msg = this.error.message || String(this.error);
    this.errorEl.innerHTML = '<span class="dc-error-icon">!</span><span class="dc-error-text">' + esc(msg) + '</span>';
  };

  CrudView.prototype.rowHtml = function (row, columns) {
    const tab = this.activeTab();
    const idx = this.filteredRows().indexOf(row);
    const cells = columns.map((c) => '<td' + (c.align === 'right' ? ' class="dc-cell-right"' : '') + '>' + formatCell(valueAt(row, c.key), c, row) + '</td>').join('');
    const actions = [];
    if (tab.update !== false && tab.fields && tab.fields.length) {
      actions.push('<button class="dc-row-btn" data-action="edit" data-index="' + idx + '" title="Edit">' + editIcon() + '</button>');
    }
    for (const a of tab.actions || []) {
      const cls = 'dc-row-btn' + (a.danger ? ' is-danger' : '');
      actions.push('<button class="' + cls + '" data-action="' + safeActionId(a) + '" data-index="' + idx + '">' + esc(a.label || 'Action') + '</button>');
    }
    if (tab.delete !== false) {
      actions.push('<button class="dc-row-btn is-danger" data-action="delete" data-index="' + idx + '" title="Delete">' + trashIcon() + '</button>');
    }
    return '<tr data-index="' + idx + '">' + cells + '<td class="dc-actions">' + actions.join('') + '</td></tr>';
  };

  CrudView.prototype.openForm = async function (mode, row) {
    const tab = this.activeTab();
    const values = await showForm({
      title: mode === 'create' ? (tab.createTitle || 'New ' + (tab.singular || tab.label || 'record')) : (tab.editTitle || 'Edit ' + (tab.singular || tab.label || 'record')),
      fields: mode === 'create' ? tab.fields : (tab.updateFields || tab.fields),
      row: row || {},
      submitLabel: mode === 'create' ? (tab.createLabel || 'Create') : 'Save',
    });
    if (!values) return;
    try {
      const fields = mode === 'create' ? tab.fields : (tab.updateFields || tab.fields);
      const body = tab.formData ? buildFormData(values, fields) : buildBody(values, fields);
      if (!tab.formData && tab.includeCompanyIdInBody && this.ctx.companyId && !body.company_id) body.company_id = this.ctx.companyId;
      if (mode === 'create') {
        const opts = tab.formData
          ? { method: tab.createMethod || 'POST', body }
          : requestOpts(tab.createMethod || 'POST', body, tab.createBodyPlacement);
        await this.fetchJson(tab.createPath || tab.endpoint, opts);
      } else {
        await this.fetchJson(
          pathFor(tab.updatePath || tab.endpoint + '/{id}', row, tab),
          requestOpts(tab.updateMethod || 'PUT', body, tab.updateBodyPlacement),
        );
      }
      await this.refresh();
    } catch (err) {
      this.error = err;
      this.renderError();
    }
  };

  CrudView.prototype.deleteRow = async function (row) {
    const tab = this.activeTab();
    const values = await showForm({
      title: 'Delete ' + (tab.singular || 'record'),
      description: 'This action cannot be undone.',
      fields: [],
      submitLabel: 'Delete',
      danger: true,
    });
    if (!values) return;
    try {
      await this.fetchJson(pathFor(tab.deletePath || tab.endpoint + '/{id}', row, tab), { method: 'DELETE' });
      await this.refresh();
    } catch (err) {
      this.error = err;
      this.renderError();
    }
  };

  CrudView.prototype.runAction = async function (action, row) {
    const values = action.fields && action.fields.length
      ? await showForm({ title: action.title || action.label || 'Action', fields: action.fields, row: row || {}, submitLabel: action.submitLabel || action.label || 'Run', danger: action.danger })
      : await showForm({ title: action.title || action.label || 'Action', description: action.confirm || 'Run this action?', fields: [], submitLabel: action.submitLabel || action.label || 'Run', danger: action.danger });
    if (!values) return;
    try {
      const body = action.body
        ? (typeof action.body === 'function' ? action.body(values, row, this.ctx) : action.body)
        : (action.fields && action.fields.length ? buildBody(values, action.fields) : undefined);
      const result = await this.fetchJson(
        pathFor(action.path, Object.assign({}, values || {}, row || {}), this.activeTab()),
        requestOpts(action.method || 'POST', body, action.bodyPlacement),
      );
      if (action.showResult) this.showDetail(result || { success: true });
      await this.refresh();
    } catch (err) {
      this.error = err;
      this.renderError();
    }
  };

  CrudView.prototype.showDetail = function (row) {
    const tab = this.activeTab();
    const title = (tab.singular ? title2(tab.singular) : 'Details');
    const subtitle = primaryLabelFor(row);
    const close = () => { this.detailEl.hidden = true; this.detailEl.innerHTML = ''; };

    // Custom detail renderer hook — when an extension supplies
    // `detailRenderer(row, helpers)`, we hand the body over to it
    // entirely. The helpers object exposes the things a workflow detail
    // typically needs (close, refresh, fetchJson, openForm, runAction)
    // so the renderer doesn't have to reach into CrudView internals.
    if (typeof tab.detailRenderer === 'function') {
      const helpers = {
        close,
        refresh: () => this.refresh(),
        fetchJson: (path, opts) => this.fetchJson(path, opts),
        openEdit: () => { close(); this.openForm('edit', row); },
        openForm: (mode, r) => this.openForm(mode || 'edit', r || row),
        runAction: (actionId) => {
          const action = (tab.actions || []).find((a) => a.id === actionId);
          if (action) this.runAction(action, row);
        },
        ctx: this.ctx,
        tab: tab,
      };
      this.detailEl.hidden = false;
      this.detailEl.innerHTML = [
        '<div class="dc-detail-head">',
        '  <div class="dc-detail-titles">',
        '    <div class="dc-detail-eyebrow">' + esc(title) + '</div>',
        '    <h3 class="dc-detail-title">' + esc(subtitle || 'Detail') + '</h3>',
        '  </div>',
        '  <div class="dc-detail-actions">',
        '    <button type="button" class="dc-icon-btn" data-detail-action="close" title="Close">' + closeIcon() + '</button>',
        '  </div>',
        '</div>',
        '<div class="dc-detail-body" data-role="detail-body"></div>',
      ].join('');
      this.detailEl.querySelector('[data-detail-action="close"]').addEventListener('click', close);
      const body = this.detailEl.querySelector('[data-role="detail-body"]');
      const rendered = tab.detailRenderer(row, helpers);
      if (rendered instanceof Node) body.appendChild(rendered);
      else if (typeof rendered === 'string') body.innerHTML = rendered;
      else if (rendered && typeof rendered.then === 'function') {
        body.innerHTML = '<div class="dc-empty-inline">Loading…</div>';
        rendered.then((r) => {
          body.innerHTML = '';
          if (r instanceof Node) body.appendChild(r);
          else if (typeof r === 'string') body.innerHTML = r;
        }).catch((err) => {
          body.innerHTML = '<div class="dc-error">' + esc((err && err.message) || 'Failed to load detail.') + '</div>';
        });
      }
      return;
    }

    const fields = detailFields(row, tab);
    const kv = fields.map((f) => (
      '<div class="dc-kv-row">'
        + '<div class="dc-kv-key">' + esc(f.label) + '</div>'
        + '<div class="dc-kv-val">' + f.html + '</div>'
      + '</div>'
    )).join('');
    this.detailEl.hidden = false;
    this.detailEl.innerHTML = [
      '<div class="dc-detail-head">',
      '  <div class="dc-detail-titles">',
      '    <div class="dc-detail-eyebrow">' + esc(title) + '</div>',
      '    <h3 class="dc-detail-title">' + esc(subtitle || 'Detail') + '</h3>',
      '  </div>',
      '  <div class="dc-detail-actions">',
      (tab.update !== false && tab.fields && tab.fields.length ? '<button type="button" class="dc-btn" data-detail-action="edit">Edit</button>' : ''),
      '    <button type="button" class="dc-btn" data-detail-action="raw">Raw JSON</button>',
      '    <button type="button" class="dc-icon-btn" data-detail-action="close" title="Close">' + closeIcon() + '</button>',
      '  </div>',
      '</div>',
      '<div class="dc-detail-body">',
      kv ? '<div class="dc-kv">' + kv + '</div>' : '<div class="dc-empty-inline">No fields to display.</div>',
      '</div>',
    ].join('');
    this.detailEl.querySelector('[data-detail-action="close"]').addEventListener('click', close);
    const editBtn = this.detailEl.querySelector('[data-detail-action="edit"]');
    if (editBtn) editBtn.addEventListener('click', () => { close(); this.openForm('edit', row); });
    this.detailEl.querySelector('[data-detail-action="raw"]').addEventListener('click', () => {
      const body = this.detailEl.querySelector('.dc-detail-body');
      body.innerHTML = '<pre class="dc-detail-raw">' + esc(JSON.stringify(row, null, 2)) + '</pre>';
    });
  };

  CrudView.prototype.exportCsv = function () {
    const tab = this.activeTab();
    const rows = this.filteredRows();
    const columns = tab.columns && tab.columns.length ? tab.columns : inferColumns(rows);
    const lines = [
      columns.map((c) => csv(c.label || c.key)).join(','),
      ...rows.map((r) => columns.map((c) => csv(valueAt(r, c.key))).join(',')),
    ];
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = (this.config.id || 'export') + '-' + (tab.id || 'records') + '-' + new Date().toISOString().slice(0, 10) + '.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  function extractRows(raw, key) {
    if (Array.isArray(raw)) return raw;
    if (!raw || typeof raw !== 'object') return [];
    if (key) {
      const v = valueAt(raw, key);
      if (Array.isArray(v)) return v;
    }
    for (const k of ['items', 'results', 'data', 'rows', 'records', 'tickets', 'assets', 'scans', 'documents', 'properties', 'homeowners', 'assessments', 'payments', 'announcements', 'requests', 'meetings', 'estimates', 'customers', 'vehicles', 'invoices']) {
      if (Array.isArray(raw[k])) return raw[k];
    }
    return Object.keys(raw).length ? [raw] : [];
  }

  function inferColumns(rows) {
    const row = rows && rows[0] ? rows[0] : {};
    return Object.keys(row).filter((k) => !/id$/i.test(k)).slice(0, 6).map((k) => ({ key: k, label: title(k) }));
  }

  function valueAt(obj, key) {
    if (!key) return obj;
    return String(key).split('.').reduce((acc, part) => (acc && acc[part] != null ? acc[part] : null), obj);
  }

  function pathFor(template, row, tab) {
    const idKey = (tab && tab.idKey) || 'id';
    const id = row && (row[idKey] || row.id);
    return String(template || '').replace(/\{id\}/g, encodeURIComponent(id || '')).replace(/\{([^}]+)\}/g, (_, key) => encodeURIComponent(valueAt(row, key) || ''));
  }

  function requestOpts(method, body, placement) {
    const opts = { method: method || 'POST' };
    if (body === undefined) return opts;
    if (placement === 'query') opts.query = body;
    else opts.json = body;
    return opts;
  }

  function buildBody(values, fields) {
    const body = {};
    for (const f of fields || []) {
      if (f.readonly || f.kind === 'display') continue;
      let v = values[f.key];
      if (v === '' && f.emptyAsNull !== false) v = null;
      if (v != null && f.type === 'number') v = Number(v);
      if (v != null && f.type === 'checkbox') v = !!v;
      if (v != null && f.type === 'json') {
        try { v = JSON.parse(v); } catch (_) {}
      }
      if (v == null && f.omitNull) continue;
      body[f.key] = v;
    }
    return body;
  }

  function buildFormData(values, fields) {
    const fd = new FormData();
    for (const f of fields || []) {
      if (f.readonly || f.kind === 'display') continue;
      let v = values[f.key];
      if (v == null || v === '') continue;
      fd.append(f.key, v);
    }
    return fd;
  }

  function formatCell(value, col, row) {
    if (col.render && typeof col.render === 'function') return col.render(value, row);
    if (value == null || value === '') return '<span class="dc-faint">—</span>';
    if (col.format === 'currency') return '<span class="dc-num">' + esc(Number(value || 0).toLocaleString(undefined, { style: 'currency', currency: 'USD' })) + '</span>';
    if (col.format === 'date' || col.format === 'datetime') return '<span class="dc-faint dc-time">' + esc(formatDate(value)) + '</span>';
    if (col.format === 'bool') return value ? '<span class="dc-badge dc-badge-good">Yes</span>' : '<span class="dc-badge dc-badge-mute">No</span>';
    if (col.format === 'status') return '<span class="dc-badge ' + statusBadgeClass(value) + '">' + esc(String(value)) + '</span>';
    if (typeof value === 'object') return '<code class="dc-code">' + esc(JSON.stringify(value)) + '</code>';
    const text = String(value);
    if (text.length > 140) return '<span title="' + esc(text) + '">' + esc(text.slice(0, 137)) + '…</span>';
    return esc(text);
  }

  function statusBadgeClass(value) {
    const v = String(value || '').toLowerCase();
    if (/(active|enabled|ok|approved|completed|complete|paid|good|success|on|online|published|sent)/.test(v)) return 'dc-badge-good';
    if (/(pending|in_progress|processing|warning|warn|partial|due|sent_partial)/.test(v)) return 'dc-badge-warn';
    if (/(error|failed|rejected|denied|cancel|inactive|disabled|suspended|expired|delinquent|critical|offline|void)/.test(v)) return 'dc-badge-bad';
    if (/(draft|new|inbox)/.test(v)) return 'dc-badge-info';
    return 'dc-badge-mute';
  }

  function cardTone(label) {
    const l = String(label || '').toLowerCase();
    if (/(error|fail|reject|deny|denied|critical|delinquent|outstanding|unpaid|overdue|expired|suspended)/.test(l)) return 'bad';
    if (/(warning|warn|pending|due|partial|alert|backlog)/.test(l)) return 'warn';
    if (/(active|approved|complete|paid|collected|good|success|ok|sent)/.test(l)) return 'good';
    if (/(total|usd|balance|tokens|users|companies|count|records|fines|assessments|amount|revenue)/.test(l)) return 'accent';
    return '';
  }

  function detailFields(row, tab) {
    if (!row || typeof row !== 'object') return [];
    const cols = (tab.columns || []).slice();
    const used = new Set(cols.map((c) => c.key));
    const out = [];
    for (const c of cols) {
      const val = valueAt(row, c.key);
      if (val == null || val === '') continue;
      out.push({ label: c.label || title2(c.key), html: formatCell(val, c, row) });
    }
    for (const k of Object.keys(row)) {
      if (used.has(k)) continue;
      const v = row[k];
      if (v == null || v === '') continue;
      if (k.toLowerCase() === 'id' || /_id$/i.test(k)) {
        out.push({ label: title2(k), html: '<code class="dc-code">' + esc(String(v)) + '</code>' });
        continue;
      }
      if (typeof v === 'object') {
        out.push({ label: title2(k), html: '<code class="dc-code">' + esc(truncate(JSON.stringify(v), 200)) + '</code>' });
        continue;
      }
      out.push({ label: title2(k), html: esc(String(v)) });
    }
    return out;
  }

  function primaryLabelFor(row) {
    if (!row || typeof row !== 'object') return '';
    for (const k of ['name', 'title', 'estimate_number', 'invoice_number', 'kb_number', 'company_name', 'first_name', 'email', 'subject', 'unit_number', 'identifier']) {
      if (row[k] != null && row[k] !== '') return String(row[k]);
    }
    return row.id ? '#' + String(row.id).slice(0, 8) : '';
  }

  function renderEmpty(tab, hasSearch) {
    if (hasSearch) {
      return '<div class="dc-empty">'
        + '<div class="dc-empty-glyph">' + searchIcon() + '</div>'
        + '<div class="dc-empty-title">No matches</div>'
        + '<div class="dc-empty-text">No ' + esc((tab.label || 'records').toLowerCase()) + ' match the current search.</div>'
        + '</div>';
    }
    const cta = (tab.create !== false && tab.fields && tab.fields.length)
      ? '<button class="dc-primary" data-empty-action="create">' + addIcon() + (tab.createLabel || 'New ' + (tab.singular || 'record')) + '</button>'
      : '';
    return '<div class="dc-empty">'
      + '<div class="dc-empty-glyph">' + boxIcon() + '</div>'
      + '<div class="dc-empty-title">No ' + esc((tab.label || 'records').toLowerCase()) + ' yet</div>'
      + '<div class="dc-empty-text">' + esc(tab.emptyHint || ('Create a ' + (tab.singular || 'record').toLowerCase() + ' to get started.')) + '</div>'
      + (cta ? '<div class="dc-empty-cta">' + cta + '</div>' : '')
      + '</div>';
  }

  function renderSkeleton(tab) {
    const lines = (tab.columns && tab.columns.length) ? Math.min(tab.columns.length, 5) : 5;
    const cells = Array.from({ length: lines }).map(() => '<td><span class="dc-skeleton-line"></span></td>').join('');
    const rows = Array.from({ length: 6 }).map(() => '<tr>' + cells + '</tr>').join('');
    return '<table class="dc-table dc-table-skeleton"><tbody>' + rows + '</tbody></table>';
  }

  function truncate(s, n) {
    s = String(s == null ? '' : s);
    return s.length > n ? s.slice(0, n - 1) + '…' : s;
  }

  function showForm(opts) {
    return new Promise((resolve) => {
      const overlay = document.createElement('div');
      overlay.className = 'dc-modal-overlay';
      const modal = document.createElement('form');
      modal.className = 'dc-modal' + (opts.danger ? ' is-danger' : '');
      const head = '<div class="dc-modal-head">'
        + '<div class="dc-modal-titles">'
        + '<h2>' + esc(opts.title || '') + '</h2>'
        + (opts.description ? '<p>' + esc(opts.description) + '</p>' : '')
        + '</div>'
        + '<button type="button" class="dc-icon-btn dc-modal-x" aria-label="Close">' + closeIcon() + '</button>'
        + '</div>';
      const submitLabel = esc(opts.submitLabel || 'Save');
      const submitCls = 'dc-primary' + (opts.danger ? ' is-danger' : '');
      const foot = '<div class="dc-modal-foot">'
        + '<button type="button" class="dc-btn cancel">Cancel</button>'
        + '<button type="submit" class="' + submitCls + '">' + submitLabel + '</button>'
        + '</div>';
      modal.innerHTML = head + '<div class="dc-modal-body"></div>' + foot;
      const body = modal.querySelector('.dc-modal-body');
      const fields = opts.fields || [];
      if (!fields.length && opts.description) {
        body.classList.add('dc-modal-body-empty');
      }
      for (const field of fields) body.appendChild(renderField(field, opts.row || {}));
      overlay.appendChild(modal);
      document.body.appendChild(overlay);
      const firstInput = modal.querySelector('input, textarea, select');
      if (firstInput) try { firstInput.focus(); } catch (_) {}
      const close = (value) => { overlay.remove(); document.removeEventListener('keydown', onKey, true); resolve(value); };
      const onKey = (e) => {
        if (e.key === 'Escape') { e.preventDefault(); close(null); }
      };
      document.addEventListener('keydown', onKey, true);
      modal.querySelector('.dc-modal-x').addEventListener('click', () => close(null));
      modal.querySelector('.cancel').addEventListener('click', () => close(null));
      overlay.addEventListener('click', (e) => { if (e.target === overlay) close(null); });
      modal.addEventListener('submit', (e) => {
        e.preventDefault();
        const out = {};
        for (const f of fields) {
          const el = modal.elements[f.key];
          if (!el) continue;
          out[f.key] = f.type === 'checkbox' ? !!el.checked
            : f.type === 'file' ? (el.files && el.files[0] ? el.files[0] : null)
            : el.value;
        }
        close(out);
      });
    });
  }

  function renderField(field, row) {
    const wrap = document.createElement('label');
    wrap.className = 'dc-field'
      + (field.type === 'checkbox' ? ' is-check' : '')
      + (field.fullWidth || field.type === 'textarea' || field.type === 'json' ? ' is-wide' : '');
    const label = document.createElement('span');
    label.className = 'dc-field-label';
    label.innerHTML = esc(field.label || title2(field.key)) + (field.required ? ' <em class="dc-required">*</em>' : '');
    const value = row[field.key] != null ? row[field.key] : field.value != null ? field.value : '';
    let input;
    if (field.type === 'textarea' || field.type === 'json') {
      input = document.createElement('textarea');
      input.rows = field.rows || (field.type === 'json' ? 8 : 3);
      input.value = field.type === 'json' && typeof value === 'object' ? JSON.stringify(value, null, 2) : (value || '');
    } else if (field.type === 'select') {
      input = document.createElement('select');
      for (const opt of field.options || []) {
        const o = document.createElement('option');
        o.value = opt.value != null ? opt.value : opt;
        o.textContent = opt.label != null ? opt.label : (opt === '' ? '— None —' : String(opt));
        input.appendChild(o);
      }
      input.value = value || '';
    } else {
      input = document.createElement('input');
      input.type = field.type === 'checkbox' ? 'checkbox' : field.type || 'text';
      if (field.type === 'checkbox') input.checked = !!value;
      else input.value = value == null ? '' : value;
    }
    input.name = field.key;
    input.required = !!field.required;
    if (field.placeholder) input.placeholder = field.placeholder;
    if (field.readonly) input.readOnly = true;
    if (field.type === 'checkbox') {
      wrap.appendChild(input);
      wrap.appendChild(label);
    } else {
      wrap.appendChild(label);
      wrap.appendChild(input);
    }
    if (field.help) {
      const help = document.createElement('small');
      help.className = 'dc-field-help';
      help.textContent = field.help;
      wrap.appendChild(help);
    }
    return wrap;
  }

  function button(text, cls, fn) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = cls;
    b.innerHTML = text;
    b.addEventListener('click', fn);
    return b;
  }

  function iconBtn(kind, title, fn) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'dc-icon-btn';
    b.title = title;
    b.setAttribute('aria-label', title);
    b.innerHTML = kind === 'refresh' ? refreshIcon()
      : kind === 'export' ? downloadIcon()
      : '';
    b.addEventListener('click', fn);
    return b;
  }

  function refreshIcon() { return '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 15.5-6.3L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15.5 6.3L3 16"/><path d="M3 21v-5h5"/></svg>'; }
  function downloadIcon() { return '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>'; }
  function closeIcon() { return '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'; }
  function addIcon() { return '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px;vertical-align:-2px"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>'; }
  function editIcon() { return '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>'; }
  function trashIcon() { return '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"/></svg>'; }
  function searchIcon() { return '<svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>'; }
  function boxIcon() { return '<svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>'; }

  function injectStyles() {
    if (document.getElementById('desktop-crud-styles')) return;
    const css = `
      .dc-root {
        --dc-border: var(--border);
        --dc-divider: var(--border-muted);
        --dc-row-hover: var(--panel-hover);
        --dc-card-bg: var(--panel-2);
        --dc-danger: rgba(220, 60, 80, 0.85);
        --dc-danger-soft: rgba(220, 60, 80, 0.16);
        --dc-warn: rgba(232, 167, 68, 0.85);
        --dc-warn-soft: rgba(232, 167, 68, 0.18);
        --dc-good: rgba(80, 200, 130, 0.85);
        --dc-good-soft: rgba(80, 200, 130, 0.16);
        color: var(--text);
        min-height: 100%;
        padding: 16px 20px 32px;
        display: flex;
        flex-direction: column;
        gap: 14px;
      }

      .dc-toolbar {
        display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
      }
      .dc-toolbar-left { flex: 1 1 auto; display: flex; gap: 8px; min-width: 0; }
      .dc-toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

      .dc-search {
        flex: 1 1 280px; max-width: 380px;
        height: 34px; padding: 0 12px 0 12px;
        font: inherit; font-size: 13px;
        background: var(--panel-2); color: var(--text);
        border: 1px solid var(--dc-border);
        border-radius: 8px;
      }
      .dc-search::placeholder { color: var(--text-faint); }
      .dc-search:focus {
        outline: none; border-color: var(--accent);
        box-shadow: 0 0 0 3px rgba(107, 123, 255, 0.18);
      }

      .dc-tabs { display: flex; gap: 6px; flex-wrap: wrap; }
      .dc-tab {
        padding: 6px 14px; font: inherit; font-size: 12.5px; font-weight: 500;
        border-radius: 999px;
        background: transparent; color: var(--text-dim);
        border: 1px solid var(--dc-border);
        cursor: pointer;
        transition: background 0.14s, color 0.14s, border-color 0.14s;
      }
      .dc-tab:hover { background: var(--panel-2); color: var(--text); }
      .dc-tab.is-active {
        background: var(--accent); color: #fff;
        border-color: var(--accent);
        box-shadow: 0 1px 0 rgba(255,255,255,0.08) inset;
      }

      .dc-btn {
        height: 34px; padding: 0 14px;
        font: inherit; font-size: 12.5px; font-weight: 500;
        border-radius: 8px;
        background: var(--panel-2); color: var(--text);
        border: 1px solid var(--dc-border); cursor: pointer;
        display: inline-flex; align-items: center; gap: 6px;
        transition: background 0.14s, border-color 0.14s, color 0.14s, transform 0.08s;
      }
      .dc-btn:hover { background: var(--panel-hover); }
      .dc-btn:active { transform: translateY(0.5px); }
      .dc-btn-danger { color: #ffb4ba; border-color: rgba(220, 60, 80, 0.4); }
      .dc-btn-danger:hover { background: rgba(220, 60, 80, 0.18); }
      .dc-btn-iconish { padding: 0 12px; }
      .dc-btn-iconish .dc-btn-label { font-size: 12px; font-weight: 500; }
      .dc-btn-iconish svg { color: var(--text-dim); }
      .dc-btn-iconish:hover svg { color: var(--text); }

      .dc-primary {
        height: 34px; padding: 0 16px;
        font: inherit; font-size: 13px; font-weight: 600;
        border-radius: 8px;
        background: var(--accent); color: #fff;
        border: 1px solid var(--accent); cursor: pointer;
        display: inline-flex; align-items: center;
        box-shadow: 0 1px 2px rgba(0,0,0,0.25), 0 1px 0 rgba(255,255,255,0.08) inset;
        transition: filter 0.14s, transform 0.08s, box-shadow 0.14s;
      }
      .dc-primary:hover {
        filter: brightness(1.08);
        box-shadow: 0 2px 6px rgba(107, 123, 255, 0.32), 0 1px 0 rgba(255,255,255,0.12) inset;
      }
      .dc-primary:active { transform: translateY(0.5px); }
      .dc-primary.is-danger {
        background: var(--dc-danger); border-color: var(--dc-danger);
      }
      .dc-primary.is-danger:hover {
        box-shadow: 0 2px 6px rgba(220, 60, 80, 0.4);
      }

      .dc-icon-btn {
        width: 34px; height: 34px;
        display: inline-flex; align-items: center; justify-content: center;
        border-radius: 8px;
        border: 1px solid var(--dc-border);
        background: var(--panel-2); color: var(--text-dim);
        cursor: pointer;
        transition: background 0.14s, color 0.14s;
      }
      .dc-icon-btn:hover { background: var(--panel-hover); color: var(--text); }

      .dc-summary {
        display: grid; gap: 12px;
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      }
      .dc-stat {
        position: relative;
        background: var(--dc-card-bg); border: 1px solid var(--dc-border);
        border-radius: 12px; padding: 14px 16px;
        display: flex; flex-direction: column; gap: 4px;
        overflow: hidden;
      }
      .dc-stat::before {
        content: ""; position: absolute; left: 0; top: 0; bottom: 0;
        width: 3px; background: var(--accent); opacity: 0;
        transition: opacity 0.16s;
      }
      .dc-stat-accent::before { opacity: 1; background: var(--accent); }
      .dc-stat-good::before { opacity: 1; background: var(--dc-good); }
      .dc-stat-warn::before { opacity: 1; background: var(--dc-warn); }
      .dc-stat-bad::before { opacity: 1; background: var(--dc-danger); }
      .dc-stat-label {
        color: var(--text-faint); font-size: 10.5px; font-weight: 600;
        text-transform: uppercase; letter-spacing: 0.07em;
      }
      .dc-stat-value {
        font-size: 22px; font-weight: 700; line-height: 1.2;
        color: var(--text);
        font-variant-numeric: tabular-nums;
      }
      .dc-stat-good .dc-stat-value { color: #9ce0b3; }
      .dc-stat-warn .dc-stat-value { color: #ffd28a; }
      .dc-stat-bad .dc-stat-value { color: #ff8a96; }
      .dc-stat-hint { font-size: 11.5px; color: var(--text-faint); }

      .dc-error[hidden], .dc-detail[hidden] { display: none !important; }
      .dc-error {
        display: flex; align-items: center; gap: 10px;
        padding: 10px 14px;
        border-radius: 10px; font-size: 12.5px;
        background: var(--dc-danger-soft);
        border: 1px solid rgba(220, 60, 80, 0.4);
        color: #ffb4ba;
      }
      .dc-error-icon {
        width: 20px; height: 20px; flex: 0 0 auto;
        display: inline-flex; align-items: center; justify-content: center;
        border-radius: 999px; background: rgba(220, 60, 80, 0.4);
        color: #fff; font-weight: 700; font-size: 12px;
      }

      .dc-table-wrap {
        overflow: auto;
        background: var(--dc-card-bg);
        border: 1px solid var(--dc-border);
        border-radius: 12px;
        box-shadow: 0 1px 0 rgba(255, 255, 255, 0.02), 0 4px 18px rgba(0, 0, 0, 0.18);
      }
      .dc-table {
        width: 100%; border-collapse: collapse;
        font-size: 13px; min-width: 720px;
      }
      .dc-table th, .dc-table td {
        padding: 11px 14px;
        text-align: left;
        border-bottom: 1px solid var(--dc-divider);
        vertical-align: middle;
      }
      .dc-table tbody tr {
        cursor: pointer;
        transition: background 0.10s;
      }
      .dc-table tbody tr:hover { background: var(--dc-row-hover); }
      .dc-table tbody tr:last-child td { border-bottom: 0; }
      .dc-th {
        color: var(--text-faint); font-weight: 600;
        font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.07em;
        background: var(--border-muted);
        border-bottom: 1px solid var(--dc-border);
        white-space: nowrap; user-select: none;
      }
      .dc-th-right, .dc-cell-right { text-align: right; }
      .dc-th-actions { width: 1px; }

      .dc-num { font-variant-numeric: tabular-nums; }
      .dc-time { font-size: 12px; }
      .dc-faint { color: var(--text-faint); }
      .dc-code {
        font-family: var(--mono); font-size: 11.5px;
        color: var(--text-dim); background: var(--panel);
        padding: 1px 6px; border-radius: 4px;
        border: 1px solid var(--dc-divider);
      }

      .dc-badge {
        display: inline-flex; align-items: center;
        font-size: 10.5px; font-weight: 600;
        padding: 2px 8px; border-radius: 999px;
        background: var(--panel); color: var(--text-dim);
        border: 1px solid var(--dc-border);
        text-transform: capitalize; white-space: nowrap;
      }
      .dc-badge-good { background: var(--dc-good-soft); color: #9ce0b3; border-color: rgba(80, 200, 130, 0.35); }
      .dc-badge-warn { background: var(--dc-warn-soft); color: #ffd28a; border-color: rgba(232, 167, 68, 0.4); }
      .dc-badge-bad { background: var(--dc-danger-soft); color: #ff8a96; border-color: rgba(220, 60, 80, 0.4); }
      .dc-badge-info { background: rgba(91, 142, 255, 0.18); color: #b4caff; border-color: rgba(91, 142, 255, 0.35); }
      .dc-badge-mute { background: var(--panel); color: var(--text-faint); }

      .dc-actions { display: flex; gap: 4px; justify-content: flex-end; white-space: nowrap; }
      .dc-row-btn {
        display: inline-flex; align-items: center; justify-content: center; gap: 4px;
        min-width: 28px; height: 28px;
        font: inherit; font-size: 11.5px;
        padding: 0 9px;
        border-radius: 6px;
        border: 1px solid var(--dc-border);
        background: var(--panel-2); color: var(--text);
        cursor: pointer; white-space: nowrap;
        transition: background 0.12s, color 0.12s;
      }
      .dc-row-btn:hover { background: var(--panel); }
      .dc-row-btn.is-danger { color: #ffb4ba; border-color: rgba(220, 60, 80, 0.4); }
      .dc-row-btn.is-danger:hover { background: rgba(220, 60, 80, 0.18); }

      .dc-table-skeleton .dc-skeleton-line {
        display: block; height: 14px; width: 80%;
        border-radius: 4px; background: var(--border-muted);
        animation: dc-skeleton 1.4s ease-in-out infinite;
      }
      @keyframes dc-skeleton {
        0%, 100% { opacity: 0.45; }
        50% { opacity: 0.85; }
      }

      .dc-empty {
        padding: 60px 20px; text-align: center;
        color: var(--text-faint);
        display: flex; flex-direction: column; align-items: center; gap: 10px;
      }
      .dc-empty-glyph {
        color: var(--text-faint); opacity: 0.45;
      }
      .dc-empty-title { font-size: 15px; font-weight: 600; color: var(--text-dim); }
      .dc-empty-text { font-size: 12.5px; max-width: 360px; line-height: 1.5; }
      .dc-empty-cta { margin-top: 10px; }
      .dc-empty-inline { padding: 18px; text-align: center; color: var(--text-faint); font-size: 12.5px; }

      .dc-detail {
        border: 1px solid var(--dc-border);
        background: var(--dc-card-bg);
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.18);
      }
      .dc-detail-head {
        display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;
        padding: 14px 16px;
        border-bottom: 1px solid var(--dc-border);
        background: var(--panel);
      }
      .dc-detail-titles { min-width: 0; }
      .dc-detail-eyebrow {
        color: var(--text-faint); font-size: 10.5px; font-weight: 600;
        text-transform: uppercase; letter-spacing: 0.07em;
      }
      .dc-detail-title {
        margin: 2px 0 0; font-size: 16px; font-weight: 700;
        color: var(--text); word-break: break-word;
      }
      .dc-detail-actions { display: flex; gap: 6px; align-items: center; flex: 0 0 auto; }
      .dc-detail-body { padding: 16px 18px; max-height: 480px; overflow: auto; }
      .dc-detail-raw {
        margin: 0; padding: 14px; border-radius: 8px;
        background: var(--panel); color: var(--text-dim);
        font-family: var(--mono); font-size: 12px;
        max-height: 420px; overflow: auto;
        border: 1px solid var(--dc-divider);
        white-space: pre-wrap; word-break: break-word;
      }

      .dc-kv { display: flex; flex-direction: column; }
      .dc-kv-row {
        display: grid; grid-template-columns: minmax(140px, 220px) 1fr;
        gap: 16px; align-items: baseline;
        padding: 9px 0;
        border-bottom: 1px solid var(--dc-divider);
      }
      .dc-kv-row:last-child { border-bottom: 0; }
      .dc-kv-key {
        color: var(--text-faint); font-size: 11.5px;
        text-transform: uppercase; letter-spacing: 0.05em;
      }
      .dc-kv-val {
        color: var(--text); font-size: 13px; word-break: break-word;
        overflow-wrap: anywhere;
      }

      .dc-modal-overlay {
        position: fixed; inset: 0; z-index: 10000;
        display: flex; align-items: center; justify-content: center;
        background: var(--modal-backdrop, rgba(0, 0, 0, 0.55));
        padding: 24px;
        animation: dc-fade 0.14s ease-out;
      }
      @keyframes dc-fade { from { opacity: 0; } to { opacity: 1; } }
      .dc-modal {
        width: min(720px, 100%);
        max-height: calc(100vh - 64px);
        overflow: hidden;
        display: flex; flex-direction: column;
        border: 1px solid var(--dc-border); border-radius: 12px;
        background: var(--panel); color: var(--text);
        box-shadow: 0 24px 48px rgba(0, 0, 0, 0.45), 0 1px 0 rgba(255,255,255,0.06) inset;
        animation: dc-pop 0.18s cubic-bezier(.2,.9,.3,1.2);
      }
      @keyframes dc-pop {
        from { transform: scale(0.96) translateY(8px); opacity: 0; }
        to { transform: scale(1) translateY(0); opacity: 1; }
      }
      .dc-modal.is-danger { border-color: rgba(220, 60, 80, 0.4); }
      .dc-modal-head {
        padding: 16px 18px;
        border-bottom: 1px solid var(--dc-border);
        display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
      }
      .dc-modal-titles { min-width: 0; }
      .dc-modal h2 { margin: 0; font-size: 16px; font-weight: 700; }
      .dc-modal p { margin: 4px 0 0; color: var(--text-faint); font-size: 12.5px; line-height: 1.5; }
      .dc-modal-x {
        flex: 0 0 auto; width: 30px; height: 30px;
      }
      .dc-modal-body {
        overflow: auto; padding: 18px;
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 14px;
      }
      .dc-modal-body-empty {
        display: block; padding: 6px 18px 0;
        color: var(--text-dim); font-size: 13px;
      }
      .dc-modal-foot {
        padding: 14px 18px;
        border-top: 1px solid var(--dc-border);
        background: var(--panel-2);
        display: flex; justify-content: flex-end; gap: 8px;
      }

      .dc-field {
        display: flex; flex-direction: column; gap: 6px;
        font-size: 12px; color: var(--text-dim);
        min-width: 0;
      }
      .dc-field.is-wide { grid-column: 1 / -1; }
      .dc-field.is-check {
        flex-direction: row; align-items: center; gap: 10px;
        padding: 8px 10px;
        border: 1px solid var(--dc-divider); border-radius: 8px;
        background: var(--panel-2);
      }
      .dc-field.is-check .dc-field-label { font-size: 13px; color: var(--text); }
      .dc-field-label {
        font-size: 11.5px; font-weight: 600;
        color: var(--text-dim);
        text-transform: uppercase; letter-spacing: 0.04em;
      }
      .dc-required { color: #ff8a96; font-style: normal; margin-left: 2px; }
      .dc-field input, .dc-field textarea, .dc-field select {
        width: 100%; box-sizing: border-box;
        border: 1px solid var(--dc-border);
        border-radius: 8px;
        background: var(--panel-2); color: var(--text);
        padding: 9px 11px;
        font: inherit; font-size: 13px;
        transition: border-color 0.14s, box-shadow 0.14s;
      }
      .dc-field input[type="checkbox"] {
        width: 18px; height: 18px; padding: 0;
        accent-color: var(--accent);
        border-radius: 4px;
      }
      .dc-field textarea { resize: vertical; min-height: 80px; line-height: 1.5; }
      .dc-field select {
        appearance: none; -webkit-appearance: none;
        padding-right: 28px; cursor: pointer;
        background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24' fill='none' stroke='%23a1a7b5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><polyline points='6 9 12 15 18 9'/></svg>");
        background-repeat: no-repeat; background-position: right 10px center; background-size: 10px 10px;
      }
      .dc-field input:focus, .dc-field textarea:focus, .dc-field select:focus {
        outline: none; border-color: var(--accent);
        box-shadow: 0 0 0 3px rgba(107, 123, 255, 0.18);
      }
      .dc-field-help {
        color: var(--text-faint); font-size: 11.5px;
        line-height: 1.4;
      }

      :root[data-theme="light"] .dc-stat-good .dc-stat-value { color: #1a7d3e; }
      :root[data-theme="light"] .dc-stat-warn .dc-stat-value { color: #8a5a18; }
      :root[data-theme="light"] .dc-stat-bad .dc-stat-value { color: #b3293f; }
      :root[data-theme="light"] .dc-badge-good { color: #1a7d3e; }
      :root[data-theme="light"] .dc-badge-warn { color: #8a5a18; }
      :root[data-theme="light"] .dc-badge-bad { color: #b3293f; }
      :root[data-theme="light"] .dc-badge-info { color: #2c4a8b; }
      :root[data-theme="light"] .dc-error { color: #b3293f; }
      :root[data-theme="light"] .dc-row-btn.is-danger { color: #b3293f; }
      :root[data-theme="light"] .dc-required { color: #b3293f; }

      @media (max-width: 720px) {
        .dc-toolbar { gap: 8px; }
        .dc-toolbar-right { width: 100%; }
        .dc-search { max-width: none; }
      }
    `;
    const tag = document.createElement('style');
    tag.id = 'desktop-crud-styles';
    tag.textContent = css;
    document.head.appendChild(tag);
  }

  function formatDate(v) {
    const d = new Date(v);
    return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString();
  }
  function title(s) { return String(s || '').replace(/_/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase()); }
  function title2(s) {
    return String(s || '')
      .replace(/[_\-.]+/g, ' ')
      .replace(/\bid\b/i, 'ID')
      .replace(/\b\w/g, (m) => m.toUpperCase())
      .trim();
  }
  function safeActionId(a) { return String(a.id || a.label || 'action').toLowerCase().replace(/[^a-z0-9]+/g, '-'); }
  function esc(v) { return String(v == null ? '' : v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
  function csv(v) {
    if (v == null) return '';
    if (typeof v === 'object') v = JSON.stringify(v);
    const s = String(v);
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  function cssEscape(s) { return String(s).replace(/[^a-zA-Z0-9_-]/g, '\\$&'); }

  window.AgixtCrudExtension = { register };
})();

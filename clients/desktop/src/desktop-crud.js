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
    this.renderHeader();
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
    root.appendChild(this.tabsEl);
    root.appendChild(this.errorEl);
    root.appendChild(this.summaryEl);
    root.appendChild(this.tableEl);
    root.appendChild(this.detailEl);
    this.container.appendChild(root);
    this.renderTabs();
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
        this.renderHeader();
        if (this.rowsByTab[id]) this.renderData();
        else this.refresh();
      });
      this.tabsEl.appendChild(btn);
    }
  };

  CrudView.prototype.renderHeader = function () {
    const tab = this.activeTab();
    const actions = [];
    const search = document.createElement('input');
    search.type = 'search';
    search.className = 'dc-search';
    search.placeholder = tab.searchPlaceholder || 'Search...';
    search.value = this.search;
    search.addEventListener('input', (e) => {
      this.search = e.target.value;
      this.renderData();
    });
    actions.push(search);

    const refresh = button('Refresh', 'dc-btn', () => this.refresh());
    actions.push(refresh);

    const exportBtn = button('Export CSV', 'dc-btn', () => this.exportCsv());
    actions.push(exportBtn);

    for (const action of tab.globalActions || []) {
      actions.push(button(action.label || 'Action', action.danger ? 'dc-btn danger' : 'dc-btn', () => this.runAction(action, null)));
    }

    if (tab.create !== false && tab.fields && tab.fields.length) {
      actions.push(button(tab.createLabel || 'New', 'dc-primary', () => this.openForm('create')));
    }

    if (this.ctx && typeof this.ctx.setHeaderActions === 'function') {
      this.ctx.setHeaderActions.apply(null, actions);
    }
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
    this.renderSummary();
    const tab = this.activeTab();
    if (this.loading) {
      this.tableEl.innerHTML = '<div class="dc-empty">Loading...</div>';
      return;
    }
    const rows = this.filteredRows();
    const columns = tab.columns && tab.columns.length ? tab.columns : inferColumns(rows);
    const headers = columns.map((c) => '<th>' + esc(c.label || c.key) + '</th>').join('');
    const body = rows.length
      ? rows.map((row) => this.rowHtml(row, columns)).join('')
      : '<tr><td colspan="' + (columns.length + 1) + '" class="dc-empty">No records found.</td></tr>';
    this.tableEl.innerHTML = '<table class="dc-table"><thead><tr>' + headers + '<th></th></tr></thead><tbody>' + body + '</tbody></table>';
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
    cards.push(['Records', rows.length]);
    for (const card of tab.summary || []) {
      let val = typeof card.value === 'function' ? card.value(rows, raw) : valueAt(raw, card.value);
      if (val == null || val === '') val = '0';
      cards.push([card.label, val]);
    }
    this.summaryEl.innerHTML = cards.map((c) => '<div class="dc-card"><div class="dc-card-label">' + esc(c[0]) + '</div><div class="dc-card-value">' + esc(c[1]) + '</div></div>').join('');
  };

  CrudView.prototype.renderError = function () {
    if (!this.errorEl) return;
    if (!this.error) {
      this.errorEl.hidden = true;
      this.errorEl.textContent = '';
      return;
    }
    this.errorEl.hidden = false;
    this.errorEl.textContent = this.error.message || String(this.error);
  };

  CrudView.prototype.rowHtml = function (row, columns) {
    const tab = this.activeTab();
    const idx = this.filteredRows().indexOf(row);
    const cells = columns.map((c) => '<td>' + formatCell(valueAt(row, c.key), c, row) + '</td>').join('');
    const actions = ['<button data-action="detail" data-index="' + idx + '">Details</button>'];
    if (tab.update !== false && tab.fields && tab.fields.length) actions.push('<button data-action="edit" data-index="' + idx + '">Edit</button>');
    if (tab.delete !== false) actions.push('<button class="danger" data-action="delete" data-index="' + idx + '">Delete</button>');
    for (const a of tab.actions || []) {
      actions.push('<button class="' + (a.danger ? 'danger' : '') + '" data-action="' + safeActionId(a) + '" data-index="' + idx + '">' + esc(a.label || 'Action') + '</button>');
    }
    return '<tr>' + cells + '<td class="dc-actions">' + actions.join('') + '</td></tr>';
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
        await this.fetchJson(tab.createPath || tab.endpoint, tab.formData
          ? { method: tab.createMethod || 'POST', body }
          : { method: tab.createMethod || 'POST', json: body });
      } else {
        await this.fetchJson(pathFor(tab.updatePath || tab.endpoint + '/{id}', row, tab), { method: tab.updateMethod || 'PUT', json: body });
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
      await this.fetchJson(pathFor(action.path, row || values, this.activeTab()), { method: action.method || 'POST', json: body });
      await this.refresh();
    } catch (err) {
      this.error = err;
      this.renderError();
    }
  };

  CrudView.prototype.showDetail = function (row) {
    this.detailEl.hidden = false;
    this.detailEl.innerHTML = '<div class="dc-detail-head"><strong>Details</strong><button type="button">Close</button></div><pre>' + esc(JSON.stringify(row, null, 2)) + '</pre>';
    const btn = this.detailEl.querySelector('button');
    btn.addEventListener('click', () => { this.detailEl.hidden = true; this.detailEl.innerHTML = ''; });
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
    if (value == null || value === '') return '<span class="dc-faint">-</span>';
    if (col.format === 'currency') return esc(Number(value || 0).toLocaleString(undefined, { style: 'currency', currency: 'USD' }));
    if (col.format === 'date' || col.format === 'datetime') return esc(formatDate(value));
    if (col.format === 'bool') return value ? '<span class="dc-pill">Yes</span>' : '<span class="dc-faint">No</span>';
    if (typeof value === 'object') return '<code>' + esc(JSON.stringify(value)) + '</code>';
    if (String(value).length > 140) return esc(String(value).slice(0, 137) + '...');
    return esc(value);
  }

  function showForm(opts) {
    return new Promise((resolve) => {
      const overlay = document.createElement('div');
      overlay.className = 'dc-modal-overlay';
      const modal = document.createElement('form');
      modal.className = 'dc-modal';
      modal.innerHTML = '<div class="dc-modal-head"><div><h2>' + esc(opts.title || '') + '</h2>' + (opts.description ? '<p>' + esc(opts.description) + '</p>' : '') + '</div><button type="button" class="dc-modal-x">x</button></div><div class="dc-modal-body"></div><div class="dc-modal-foot"><button type="button" class="dc-btn cancel">Cancel</button><button type="submit" class="dc-primary ' + (opts.danger ? 'danger' : '') + '">' + esc(opts.submitLabel || 'Save') + '</button></div>';
      const body = modal.querySelector('.dc-modal-body');
      const fields = opts.fields || [];
      for (const field of fields) body.appendChild(renderField(field, opts.row || {}));
      overlay.appendChild(modal);
      document.body.appendChild(overlay);
      const close = (value) => { overlay.remove(); resolve(value); };
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
    wrap.className = 'dc-field' + (field.type === 'checkbox' ? ' is-check' : '');
    const label = document.createElement('span');
    label.textContent = field.label || title(field.key);
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
        o.textContent = opt.label != null ? opt.label : String(opt);
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
    wrap.appendChild(label);
    wrap.appendChild(input);
    if (field.help) {
      const help = document.createElement('small');
      help.textContent = field.help;
      wrap.appendChild(help);
    }
    return wrap;
  }

  function button(text, cls, fn) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = cls;
    b.textContent = text;
    b.addEventListener('click', fn);
    return b;
  }

  function injectStyles() {
    if (document.getElementById('desktop-crud-styles')) return;
    const css = `
      .dc-root { color: var(--text); min-height: 100%; padding: 16px 20px 32px; display: flex; flex-direction: column; gap: 14px; }
      .dc-tabs { display: flex; gap: 6px; flex-wrap: wrap; }
      .dc-tab, .dc-btn, .dc-primary { border: 1px solid var(--border); background: var(--panel-2); color: var(--text); border-radius: 6px; height: 32px; padding: 0 12px; font: inherit; font-size: 12px; cursor: pointer; }
      .dc-tab.is-active, .dc-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
      .dc-btn:hover, .dc-tab:hover { background: var(--panel-hover); }
      .dc-primary.danger, .dc-btn.danger { background: rgba(220,60,80,.85); border-color: rgba(220,60,80,.85); color: #fff; }
      .dc-search { height: 32px; min-width: 220px; max-width: 360px; padding: 0 10px; border-radius: 6px; border: 1px solid var(--border); background: var(--panel-2); color: var(--text); font: inherit; font-size: 13px; }
      .dc-summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; }
      .dc-card { border: 1px solid var(--border); background: var(--panel-2); border-radius: 8px; padding: 10px 12px; }
      .dc-card-label { color: var(--text-faint); font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }
      .dc-card-value { font-size: 20px; font-weight: 700; margin-top: 4px; }
      .dc-error { border: 1px solid rgba(220,60,80,.45); background: rgba(220,60,80,.16); color: #ffb4ba; border-radius: 8px; padding: 10px 12px; font-size: 13px; }
      .dc-table-wrap { overflow: auto; border: 1px solid var(--border); background: var(--panel-2); border-radius: 8px; }
      .dc-table { width: 100%; min-width: 860px; border-collapse: collapse; font-size: 13px; }
      .dc-table th, .dc-table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border-muted); vertical-align: top; }
      .dc-table th { color: var(--text-faint); font-size: 11px; font-weight: 700; text-transform: uppercase; background: var(--border-muted); white-space: nowrap; }
      .dc-actions { display: flex; gap: 5px; justify-content: flex-end; white-space: nowrap; }
      .dc-actions button { border: 1px solid var(--border); background: var(--panel); color: var(--text); border-radius: 5px; padding: 3px 8px; font-size: 11px; cursor: pointer; }
      .dc-actions button.danger { color: #ffb4ba; border-color: rgba(220,60,80,.45); }
      .dc-empty { padding: 30px; text-align: center; color: var(--text-faint); }
      .dc-faint { color: var(--text-faint); }
      .dc-pill { display: inline-block; border: 1px solid var(--border); border-radius: 999px; padding: 1px 7px; font-size: 11px; background: var(--panel); }
      .dc-detail { border: 1px solid var(--border); background: var(--panel-2); border-radius: 8px; overflow: hidden; }
      .dc-detail-head { display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; border-bottom: 1px solid var(--border); }
      .dc-detail pre { margin: 0; padding: 12px; overflow: auto; max-height: 360px; font-size: 12px; }
      .dc-modal-overlay { position: fixed; inset: 0; z-index: 10000; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,.55); padding: 24px; }
      .dc-modal { width: min(680px, 100%); max-height: calc(100vh - 64px); overflow: hidden; display: flex; flex-direction: column; border: 1px solid var(--border); border-radius: 8px; background: var(--panel); color: var(--text); }
      .dc-modal-head, .dc-modal-foot { padding: 14px 16px; background: var(--panel-2); border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; gap: 12px; }
      .dc-modal-foot { border-top: 1px solid var(--border); border-bottom: 0; justify-content: flex-end; }
      .dc-modal h2 { margin: 0; font-size: 16px; }
      .dc-modal p { margin: 4px 0 0; color: var(--text-faint); font-size: 12px; }
      .dc-modal-x { border: 0; background: transparent; color: var(--text-faint); cursor: pointer; font-size: 18px; }
      .dc-modal-body { overflow: auto; padding: 16px; display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }
      .dc-field { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--text-dim); }
      .dc-field.is-check { flex-direction: row; align-items: center; }
      .dc-field input, .dc-field textarea, .dc-field select { width: 100%; box-sizing: border-box; border: 1px solid var(--border); border-radius: 6px; background: var(--panel-2); color: var(--text); padding: 8px 10px; font: inherit; font-size: 13px; }
      .dc-field textarea { resize: vertical; min-height: 70px; }
      .dc-field small { color: var(--text-faint); }
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

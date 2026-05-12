/* Prompt Library side pane.
 *
 * Vanilla-JS port of web/app/settings/prompts/page.tsx. Supports the same
 * user/company/server levels as the web prompt library, defaulting to the
 * "Default" category inside each scope. The pane has two columns:
 *   - List (left)  — searchable list of prompts with a body preview
 *   - Editor (right) — title + Edit/Test tabs
 *     • Edit: textarea + a sidebar of detected `{var}` tokens you can
 *       click to insert. Save flushes the body.
 *     • Test: variables form (auto-derived from {var}s in the body),
 *       interpolated preview, and a Send button that POSTs to the
 *       agent's /v1/agent/{id}/prompt endpoint.
 *
 * Chains' "Prompt"-step dropdown reads from the same /v1/prompts list
 * via agixt-api.js, so anything created/renamed/deleted here surfaces
 * the next time the chains pane is opened. We also dispatch a window
 * `agixt-prompts-changed` event after each mutation so the chains pane
 * (when active) can refresh its prompt selector immediately.
 *
 * Lifecycle: app.js calls window.AgixtPrompts.mount() the first time
 * the pane is activated; subsequent activations just refresh the list.
 */
(function () {
  const tauri = window.__TAURI__;
  if (!tauri) return;
  const invoke = tauri.core.invoke;
  const api = window.AgixtApi;
  if (!api) {
    console.error('prompts.js: AgixtApi unavailable');
    return;
  }

  const $ = (sel, root) => (root || document).querySelector(sel);

  // ── State ─────────────────────────────────────────────────────────────
  const STATE = {
    mounted: false,
    booted: false,
    scope: (() => {
      try { return window.localStorage.getItem('promptEditorScope') || 'user'; }
      catch (_) { return 'user'; }
    })(),
    scopes: new Set(),
    roleId: null,
    prompts: [],          // [{id, name, content?, category}]
    listFilter: '',
    activeId: null,       // currently selected prompt id
    activeBody: '',       // local edit buffer
    activeBaseline: '',   // last-saved body
    activeName: '',       // editable name (commits on blur)
    activeTab: 'edit',    // 'edit' | 'test'
    testVars: {},         // var name -> value
    testResponse: '',
    testRunning: false,
    agentId: '',
    agentName: '',
  };

  // System args we never expose in the test panel — these come from the
  // backend at execution time. Mirrors the web's skipArgs list.
  const SKIP_ARGS = new Set([
    'agent_name', 'COMMANDS', 'context', 'command_list', 'date',
    'working_directory', 'helper_agent_name', 'conversation_history',
    'persona', 'import_files', 'output_url',
  ]);

  // ── Toast ─────────────────────────────────────────────────────────────
  let toastTimer = null;
  function toast(message, kind) {
    const elt = $('#pl-toast');
    if (!elt) return;
    elt.textContent = message;
    elt.className = 'pl-toast' + (kind ? ' ' + kind : '');
    elt.hidden = false;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { elt.hidden = true; }, kind === 'error' ? 6000 : 3000);
  }
  function errMsg(err) {
    if (!err) return 'Unknown error';
    if (typeof err === 'string') return err;
    return err.error || err.detail || err.message || String(err);
  }

  function isAdminRole() {
    return STATE.roleId === 0 || STATE.roleId === 1;
  }

  function hasScope(name) {
    return STATE.scopes.has('*') || STATE.scopes.has('*:*') || STATE.scopes.has(name);
  }

  function canUsePromptScope(scope) {
    if (scope === 'user') return true;
    if (scope === 'company') {
      return isAdminRole() || hasScope('company:prompts') || hasScope('company:admin');
    }
    if (scope === 'server') {
      return STATE.roleId === 0 || hasScope('server:prompts') || hasScope('server:admin');
    }
    return false;
  }

  function scopeLabel(scope) {
    if (scope === 'company') return 'Company';
    if (scope === 'server') return 'Server';
    return 'My Prompts';
  }

  function scopeEntityLabel() {
    if (STATE.scope === 'company') return 'company prompt';
    if (STATE.scope === 'server') return 'server prompt';
    return 'prompt';
  }

  function scopeEmptyLabel() {
    if (STATE.scope === 'company') return 'company prompts';
    if (STATE.scope === 'server') return 'server prompts';
    return 'prompts';
  }

  function isSharedScope() {
    return STATE.scope === 'company' || STATE.scope === 'server';
  }

  function setScope(scope) {
    STATE.scope = canUsePromptScope(scope) ? scope : 'user';
    try { window.localStorage.setItem('promptEditorScope', STATE.scope); } catch (_) {}
  }

  // ── DOM helpers (mirrors chains.js for stylistic parity) ──────────────
  function el(tag, props, children) {
    const node = document.createElement(tag);
    if (props) {
      Object.entries(props).forEach(([k, v]) => {
        if (v == null || v === false) return;
        if (k === 'class') node.className = v;
        else if (k === 'html') node.innerHTML = v;
        else if (k === 'dataset') Object.assign(node.dataset, v);
        else if (k.startsWith('on') && typeof v === 'function') {
          node.addEventListener(k.slice(2).toLowerCase(), v);
        } else if (k in node && typeof v !== 'object') {
          try { node[k] = v; } catch (_) { node.setAttribute(k, v); }
        } else {
          node.setAttribute(k, v);
        }
      });
    }
    if (children) {
      (Array.isArray(children) ? children : [children]).forEach((c) => {
        if (c == null || c === false) return;
        if (typeof c === 'string' || typeof c === 'number') {
          node.appendChild(document.createTextNode(String(c)));
        } else {
          node.appendChild(c);
        }
      });
    }
    return node;
  }
  function btn(label, opts) {
    opts = opts || {};
    const cls = ['btn'];
    if (opts.kind === 'primary') cls.push('btn-primary');
    else if (opts.kind === 'danger') cls.push('btn-danger');
    else if (opts.kind === 'ghost') cls.push('btn-ghost');
    else cls.push('btn-secondary');
    return el('button', {
      type: 'button',
      class: cls.join(' '),
      onclick: opts.onclick,
      disabled: opts.disabled,
      title: opts.title,
    }, label);
  }

  const ICONS = {
    plus: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>',
    save: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/></svg>',
    trash: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>',
    download: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>',
    upload: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/></svg>',
    play: '<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>',
    book: '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2zM22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>',
    edit: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>',
    flask: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h6M10 3v6L4 21h16L14 9V3"/></svg>',
  };

  // ── Data loading ──────────────────────────────────────────────────────

  async function loadUserScopes() {
    try {
      const [user, settings] = await Promise.all([
        api.getUser(),
        api.getSettings().catch(() => null),
      ]);
      const companyId = (settings && settings.company_id) || null;
      const companies = (user && user.companies) || [];
      const currentCompany = companyId
        ? companies.find((c) => c.id === companyId)
        : companies[0];
      STATE.scopes = new Set(
        (currentCompany && currentCompany.scopes)
          || (user && user.scopes)
          || []
      );
      STATE.roleId = currentCompany && currentCompany.role_id != null
        ? Number(currentCompany.role_id)
        : (user && user.role_id != null ? Number(user.role_id) : null);
    } catch (err) {
      console.warn('prompts: load user scopes failed', err);
      STATE.scopes = new Set();
      STATE.roleId = null;
    }
    if (!canUsePromptScope(STATE.scope)) setScope('user');
    renderScopeTabs();
  }

  async function loadPromptsList(force) {
    try {
      const rows = await api.listScopedPrompts(STATE.scope, 'Default');
      STATE.prompts = (rows || []).map((p) => ({
        id: p.id || p.prompt_id || '',
        name: p.name || p.prompt_name || '',
        content: p.content || p.prompt || p.prompt_content || '',
        category: p.category || p.prompt_category || 'Default',
        description: p.description || '',
        source: p.source || STATE.scope,
      })).filter((p) => p.id && p.name);
      STATE.prompts.sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));
    } catch (err) {
      toast('Failed to load prompts: ' + errMsg(err), 'error');
      STATE.prompts = [];
    }
  }

  async function loadActivePrompt() {
    if (!STATE.activeId) {
      STATE.activeBody = '';
      STATE.activeBaseline = '';
      STATE.activeName = '';
      return;
    }
    // Try to use the cached content from the list first; only fall back
    // to a per-prompt GET if the list version didn't include the body.
    let p = STATE.prompts.find((x) => x.id === STATE.activeId);
    if (!p || !p.content) {
      try {
        const detail = await api.getScopedPrompt(STATE.scope, STATE.activeId);
        if (detail) {
          if (!p) p = detail;
          else {
            p.content = detail.content;
            p.name = detail.name || p.name;
            p.description = detail.description || p.description || '';
          }
        }
      } catch (err) {
        toast('Failed to load prompt: ' + errMsg(err), 'error');
      }
    }
    STATE.activeName = p ? p.name : '';
    STATE.activeBody = p ? (p.content || '') : '';
    STATE.activeBaseline = STATE.activeBody;
    rebuildTestVars();
  }

  async function loadActiveAgent() {
    try {
      const s = await api.getSettings();
      STATE.agentId = (s && s.agent_id) || '';
      STATE.agentName = (s && s.agent_name) || '';
    } catch (_) {
      STATE.agentId = '';
      STATE.agentName = '';
    }
  }

  function renderScopeTabs() {
    const wrap = $('#pl-scope-tabs');
    if (!wrap) return;
    wrap.querySelectorAll('[data-scope]').forEach((node) => {
      const scope = node.dataset.scope || 'user';
      const allowed = canUsePromptScope(scope);
      node.classList.toggle('is-active', scope === STATE.scope);
      node.classList.toggle('is-locked', !allowed);
      node.disabled = !allowed;
      node.setAttribute('aria-selected', scope === STATE.scope ? 'true' : 'false');
      node.title = allowed
        ? `${scopeLabel(scope)} prompts`
        : `You don't have access to ${scopeLabel(scope).toLowerCase()}. Ask an admin for the ${scope}:prompts scope.`;
    });
  }

  function renderScopeBadge(scope) {
    const label = scope === 'company' ? 'Company' : scope === 'server' ? 'Server' : 'My';
    const iconSvg = scope === 'server'
      ? '<svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="6" rx="1.5"/><rect x="3" y="14" width="18" height="6" rx="1.5"/><line x1="7" y1="7" x2="7.01" y2="7"/><line x1="7" y1="17" x2="7.01" y2="17"/></svg>'
      : '<svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21h18M5 21V7l7-4 7 4v14"/></svg>';
    return el('span', { class: 'pl-scope-badge is-' + scope, title: `${label} scope` }, [
      el('span', { class: 'pl-scope-badge-icon', html: iconSvg }),
      el('span', null, label),
    ]);
  }

  async function switchScope(scope) {
    if (scope === STATE.scope) return;
    if (!canUsePromptScope(scope)) {
      toast(`You do not have access to ${scopeLabel(scope).toLowerCase()}.`, 'error');
      renderScopeTabs();
      return;
    }
    if (isDirty()) {
      const ok = window.confirm('You have unsaved changes. Discard them and switch prompt scope?');
      if (!ok) return;
    }
    setScope(scope);
    STATE.activeId = null;
    STATE.activeBody = '';
    STATE.activeBaseline = '';
    STATE.activeName = '';
    STATE.testResponse = '';
    STATE.testVars = {};
    renderScopeTabs();
    await loadPromptsList(true);
    renderList();
    renderEditor();
  }

  // ── Variable extraction ──────────────────────────────────────────────

  /** Pull `{var}` tokens out of the prompt body. Mirrors the web's
   *  `body.split('{').map(v => v.split('}')[0]).slice(1)` approach but
   *  we tighten it to single-token names (no spaces, no nested braces). */
  function extractVars(body) {
    if (!body) return [];
    const seen = new Set();
    const out = [];
    const re = /\{([A-Za-z_][\w]*)\}/g;
    let m;
    while ((m = re.exec(body)) !== null) {
      const v = m[1];
      if (SKIP_ARGS.has(v) || seen.has(v)) continue;
      seen.add(v);
      out.push(v);
    }
    return out;
  }

  function rebuildTestVars() {
    const vars = extractVars(STATE.activeBody);
    const next = {};
    vars.forEach((v) => { next[v] = STATE.testVars[v] != null ? STATE.testVars[v] : ''; });
    STATE.testVars = next;
  }

  // ── Render: list ─────────────────────────────────────────────────────

  function renderList() {
    const root = $('#pl-list-scroll');
    if (!root) return;
    root.innerHTML = '';
    const filter = STATE.listFilter.trim().toLowerCase();
    const items = filter
      ? STATE.prompts.filter((p) =>
          p.name.toLowerCase().includes(filter)
          || (p.content || '').toLowerCase().includes(filter))
      : STATE.prompts;

    if (!items.length) {
      root.appendChild(renderListEmpty(STATE.prompts.length === 0));
      return;
    }

    items.forEach((p) => {
      const isActive = p.id === STATE.activeId;
      const preview = (p.content || '').replace(/\s+/g, ' ').slice(0, 140);
      const headerRow = el('div', { class: 'pl-list-item-row' }, [
        el('span', { class: 'pl-list-item-name' }, p.name),
        isSharedScope() ? renderScopeBadge(STATE.scope) : null,
      ]);
      const item = el('button', {
        class: 'pl-list-item' + (isActive ? ' is-active' : ''),
        onclick: () => selectPrompt(p.id),
        title: p.name,
      }, [
        headerRow,
        preview ? el('span', { class: 'pl-list-item-preview' }, preview) : null,
      ]);
      root.appendChild(item);
    });
  }

  function renderListEmpty(noResults) {
    if (!noResults) {
      return el('div', { class: 'pl-list-empty' }, [
        el('div', { class: 'pl-list-empty-title' }, 'No matches'),
        el('div', { class: 'pl-list-empty-body' }, 'Clear the search to see all prompts in this scope.'),
      ]);
    }
    const scope = STATE.scope;
    const heading = scope === 'user'
      ? 'No prompts yet'
      : `No ${scopeEmptyLabel()} yet`;
    const body = scope === 'user'
      ? 'Click + to save your first reusable prompt template.'
      : `${scopeLabel(scope)} prompts are shared with everyone who has access to this ${scope}. Click + to create one.`;
    return el('div', { class: 'pl-list-empty' }, [
      el('div', { class: 'pl-list-empty-icon', html: ICONS.book }),
      el('div', { class: 'pl-list-empty-title' }, heading),
      el('div', { class: 'pl-list-empty-body' }, body),
    ]);
  }

  async function selectPrompt(id) {
    if (STATE.activeId === id) return;
    if (isDirty()) {
      const ok = window.confirm('You have unsaved changes. Discard them and switch prompts?');
      if (!ok) return;
    }
    STATE.activeId = id;
    STATE.activeTab = 'edit';
    STATE.testResponse = '';
    renderList();
    renderEditor(/* loading */ true);
    await loadActivePrompt();
    renderEditor();
  }

  function isDirty() {
    return STATE.activeId && STATE.activeBody !== STATE.activeBaseline;
  }

  // ── Render: editor ───────────────────────────────────────────────────

  function renderEditor(loading) {
    const root = $('#pl-editor');
    if (!root) return;
    root.innerHTML = '';

    if (!STATE.activeId) {
      root.appendChild(renderEmptyState());
      return;
    }
    if (loading) {
      root.appendChild(el('div', { class: 'pl-editor-empty' }, [
        el('div', { class: 'pl-editor-empty-icon', html: ICONS.book }),
        el('div', { class: 'pl-editor-empty-title' }, 'Loading prompt…'),
      ]));
      return;
    }

    root.appendChild(renderEditorHeader());
    root.appendChild(renderTabs());
    if (STATE.activeTab === 'edit') {
      root.appendChild(renderEditPane());
    } else {
      root.appendChild(renderTestPane());
    }
  }

  function renderEmptyState() {
    const shared = isSharedScope();
    const title = shared
      ? `${scopeLabel(STATE.scope)} prompts`
      : 'Prompt Library';
    const body = shared
      ? `${scopeLabel(STATE.scope)} prompts are shared with everyone who has access to this ${STATE.scope}. Pick a prompt on the left, or save a new template.`
      : 'Save reusable prompt templates with named variables in `{curly_braces}`. They power Prompt-type chain steps and the agent test panel.';
    return el('div', { class: 'pl-editor-empty' }, [
      el('div', { class: 'pl-editor-empty-icon', html: ICONS.book }),
      el('div', { class: 'pl-editor-empty-titlewrap' }, [
        el('div', { class: 'pl-editor-empty-title' }, title),
        shared ? renderScopeBadge(STATE.scope) : null,
      ]),
      el('div', { class: 'pl-editor-empty-body' }, body),
      btn(
        el('span', null, [
          el('span', { html: ICONS.plus }),
          el('span', { style: 'margin-left:6px' },
            shared ? `New ${scopeLabel(STATE.scope).toLowerCase()} prompt` : 'New prompt'),
        ]),
        { kind: 'primary', onclick: handleCreatePrompt }
      ),
    ]);
  }

  function renderEditorHeader() {
    const titleInput = el('input', {
      class: 'pl-editor-title',
      type: 'text',
      value: STATE.activeName,
      onblur: handleRenameBlur,
    });

    const dirty = isDirty();
    const saveBtn = btn(
      el('span', null, [
        el('span', { html: ICONS.save }),
        el('span', { style: 'margin-left:6px' }, dirty ? 'Save' : 'Saved'),
      ]),
      {
        kind: dirty ? 'primary' : 'secondary',
        disabled: !dirty,
        onclick: handleSavePrompt,
        title: dirty ? 'Save prompt body' : 'No unsaved changes',
      }
    );
    const exportBtn = btn(
      el('span', { html: ICONS.download }),
      { kind: 'ghost', onclick: handleExportPrompt, title: 'Export as text' }
    );
    const deleteBtn = btn(
      el('span', { html: ICONS.trash }),
      { kind: 'danger', onclick: handleDeletePrompt, title: 'Delete prompt' }
    );

    const meta = el('div', { class: 'pl-editor-meta' }, [
      isSharedScope() ? renderScopeBadge(STATE.scope) : null,
      el('span', {
        class: 'pl-category-chip',
        title: 'Category management is coming — prompts currently live in the Default category.',
      }, [
        el('span', {
          class: 'pl-category-chip-icon',
          html: '<svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7h6l2 3h10v9a2 2 0 0 1-2 2H3z"/></svg>',
        }),
        el('span', null, 'Default'),
      ]),
    ]);
    return el('div', { class: 'pl-editor-header' }, [
      el('div', { class: 'pl-editor-titlewrap' }, [titleInput, meta]),
      el('div', { class: 'pl-editor-actions' }, [saveBtn, exportBtn, deleteBtn]),
    ]);
  }

  function renderTabs() {
    const tabs = el('div', { class: 'pl-tabs' });
    const editTab = el('button', {
      class: 'pl-tab' + (STATE.activeTab === 'edit' ? ' is-active' : ''),
      type: 'button',
      onclick: () => switchTab('edit'),
    }, [
      el('span', { html: ICONS.edit }),
      'Edit',
    ]);
    const varsCount = extractVars(STATE.activeBody).length;
    const testTab = el('button', {
      class: 'pl-tab' + (STATE.activeTab === 'test' ? ' is-active' : ''),
      type: 'button',
      onclick: () => switchTab('test'),
    }, [
      el('span', { html: ICONS.flask }),
      'Test',
      varsCount ? el('span', { class: 'pl-tab-badge' }, String(varsCount)) : null,
    ]);
    tabs.appendChild(editTab);
    tabs.appendChild(testTab);
    return tabs;
  }

  function switchTab(name) {
    if (STATE.activeTab === name) return;
    STATE.activeTab = name;
    if (name === 'test') rebuildTestVars();
    renderEditor();
  }

  function renderEditPane() {
    const dirty = isDirty();
    const bodyArea = el('textarea', {
      class: 'pl-edit-textarea',
      placeholder: 'Write your prompt template here. Use `{var_name}` to mark substitution points — they become variables in the Test tab and chain step args.',
      spellcheck: 'false',
      oninput: (e) => {
        STATE.activeBody = e.target.value;
        rebuildTestVars();
        // Re-render the toolbar's modified pill + var sidebar without
        // tearing down the textarea (keeping focus + caret).
        updateEditToolbar();
        updateVarsSidebar();
        // Also flip the Save button between primary/secondary states.
        refreshSaveButton();
      },
    }, STATE.activeBody);

    const varsSidebar = el('aside', {
      class: 'pl-vars-sidebar',
      'data-pl-vars-sidebar': '',
    }, varsSidebarChildren());

    const grid = el('div', { class: 'pl-edit-grid' }, [
      el('div', { class: 'pl-edit-body' }, [bodyArea]),
      varsSidebar,
    ]);

    const toolbar = el('div', {
      class: 'pl-edit-toolbar',
      'data-pl-edit-toolbar': '',
    }, editToolbarChildren(dirty));

    const children = [toolbar];
    if (isSharedScope()) children.push(renderSharedScopeNotice());
    children.push(grid);
    const pane = el('section', { class: 'pl-edit-pane' }, children);
    setTimeout(() => bodyArea.focus(), 30);
    return pane;
  }

  function renderSharedScopeNotice() {
    const scope = STATE.scope;
    const verb = scope === 'company' ? 'company' : 'server';
    return el('div', { class: 'pl-shared-notice', role: 'note' }, [
      el('div', {
        class: 'pl-shared-notice-icon',
        html: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4"/><path d="M12 17h.01"/><circle cx="12" cy="12" r="10"/></svg>',
      }),
      el('div', { class: 'pl-shared-notice-body' }, [
        el('strong', null, 'Shared prompt — '),
        `changes you save here apply to everyone in this ${verb}.`,
      ]),
    ]);
  }

  function editToolbarChildren(dirty) {
    const vars = extractVars(STATE.activeBody);
    return [
      el('span', null, `${STATE.activeBody.length} chars`),
      el('span', null, '·'),
      el('span', null, `${vars.length} variable${vars.length === 1 ? '' : 's'}`),
      dirty ? el('span', { class: 'pl-modified' }, 'Unsaved changes') : null,
    ];
  }

  function varsSidebarChildren() {
    const vars = extractVars(STATE.activeBody);
    const out = [
      el('h4', { class: 'pl-vars-title' }, 'Variables'),
      el('p', { class: 'pl-vars-blurb' },
        'Click a chip to insert it into the prompt at the caret. New `{name}` tokens are detected automatically.'),
    ];
    if (vars.length === 0) {
      out.push(el('div', { class: 'pl-var-empty' }, 'Wrap a name in `{}` to define a variable.'));
    } else {
      vars.forEach((v) => {
        out.push(el('button', {
          type: 'button',
          class: 'pl-var-chip',
          onclick: () => insertVar(v),
          title: `Insert {${v}} at the caret`,
        }, v));
      });
    }
    return out;
  }

  function updateEditToolbar() {
    const tb = $('[data-pl-edit-toolbar]');
    if (!tb) return;
    tb.innerHTML = '';
    editToolbarChildren(isDirty()).forEach((c) => { if (c) tb.appendChild(c); });
  }

  function updateVarsSidebar() {
    const sb = $('[data-pl-vars-sidebar]');
    if (!sb) return;
    sb.innerHTML = '';
    varsSidebarChildren().forEach((c) => sb.appendChild(c));
  }

  function refreshSaveButton() {
    const headerActions = $('.pl-editor-actions');
    if (!headerActions) return;
    // Re-render header to flip Save state. Cheap because it's just three
    // buttons and a title input — and the title input doesn't re-render
    // (the header only has the actions section as a separate element).
    const header = headerActions.parentElement;
    if (header) {
      const newHeader = renderEditorHeader();
      header.parentElement.replaceChild(newHeader, header);
    }
  }

  function insertVar(name) {
    const ta = $('.pl-edit-textarea');
    if (!ta) return;
    const token = `{${name}}`;
    const start = ta.selectionStart || 0;
    const end = ta.selectionEnd || 0;
    const before = ta.value.slice(0, start);
    const after = ta.value.slice(end);
    ta.value = before + token + after;
    ta.selectionStart = ta.selectionEnd = start + token.length;
    STATE.activeBody = ta.value;
    rebuildTestVars();
    updateEditToolbar();
    refreshSaveButton();
    ta.focus();
  }

  function renderTestPane() {
    const vars = extractVars(STATE.activeBody);
    const varsForm = el('div', { class: 'pl-test-vars' });
    if (vars.length === 0) {
      varsForm.appendChild(el('div', { class: 'pl-var-empty' },
        'This prompt has no variables — Test runs it as-is.'));
    } else {
      vars.forEach((v) => {
        const id = `pl-test-${v}`;
        varsForm.appendChild(el('div', { class: 'pl-test-field' }, [
          el('label', { class: 'pl-test-field-label', for: id }, v),
          el('input', {
            id,
            class: 'pl-test-input',
            type: 'text',
            value: STATE.testVars[v] || '',
            placeholder: `{${v}}`,
            oninput: (e) => {
              STATE.testVars[v] = e.target.value;
              updatePreview();
            },
          }),
        ]));
      });
    }

    const preview = renderInterpolatedPreview();
    const previewBox = el('pre', { class: 'pl-test-preview', 'data-pl-preview': '' }, preview);

    const dirty = isDirty();
    const runBtn = btn(
      el('span', null, [
        el('span', { html: STATE.testRunning ? '' : ICONS.play }),
        STATE.testRunning ? el('span', { class: 'pl-spinner' }) : null,
        el('span', { style: 'margin-left:6px' }, STATE.testRunning ? 'Running…' : 'Send to agent'),
      ]),
      {
        kind: 'primary',
        disabled: STATE.testRunning || dirty || !STATE.agentId,
        onclick: handleRunPrompt,
        title: dirty ? 'Save unsaved changes before testing'
              : !STATE.agentId ? 'Pick an agent in the topbar first'
              : `Run with ${STATE.agentName || 'current agent'}`,
      }
    );

    const responseBox = el('div', {
      class: 'pl-test-response' + (STATE.testResponse ? '' : ' is-empty'),
    }, STATE.testResponse || '(Send to see the agent response here.)');

    const pane = el('section', { class: 'pl-test-pane' }, [
      el('div', { class: 'pl-test-section' }, [
        el('h4', { class: 'pl-test-section-title' }, 'Variables'),
        varsForm,
      ]),
      el('div', { class: 'pl-test-actions' }, [
        runBtn,
        STATE.agentName
          ? el('span', { style: 'color:var(--text-dim);font-size:12px' },
              `Agent: ${STATE.agentName}`)
          : null,
        dirty
          ? el('span', { style: 'color:rgba(255,184,80,1);font-size:12px' },
              'Save unsaved changes first.')
          : null,
      ]),
      el('div', { class: 'pl-test-section' }, [
        el('h4', { class: 'pl-test-section-title' }, 'Interpolated preview'),
        previewBox,
      ]),
      el('div', { class: 'pl-test-section' }, [
        el('h4', { class: 'pl-test-section-title' }, 'Response'),
        responseBox,
      ]),
    ]);

    return pane;
  }

  function renderInterpolatedPreview() {
    let out = STATE.activeBody;
    Object.entries(STATE.testVars).forEach(([k, v]) => {
      const re = new RegExp(`\\{${k}\\}`, 'g');
      out = out.replace(re, v != null && v !== '' ? String(v) : `{${k}}`);
    });
    return out || '(empty prompt)';
  }

  function updatePreview() {
    const preview = $('[data-pl-preview]');
    if (!preview) return;
    preview.textContent = renderInterpolatedPreview();
  }

  // ── Mutations ────────────────────────────────────────────────────────

  function emitPromptsChanged() {
    try {
      window.dispatchEvent(new CustomEvent('agixt-prompts-changed'));
    } catch (_) { /* ignore */ }
  }

  async function handleCreatePrompt() {
    const name = window.prompt('Name your new prompt:');
    if (!name) return;
    const trimmed = name.trim();
    if (!trimmed) return;
    if (STATE.prompts.some((p) => p.name.toLowerCase() === trimmed.toLowerCase())) {
      toast(`A ${scopeEntityLabel()} with that name already exists.`, 'error');
      return;
    }
    try {
      await api.createScopedPrompt(STATE.scope, trimmed, '', 'Default');
      await loadPromptsList();
      const created = STATE.prompts.find((p) => p.name === trimmed);
      if (created) {
        STATE.activeId = created.id;
        await loadActivePrompt();
      }
      renderList();
      renderEditor();
      emitPromptsChanged();
      toast(`${scopeEntityLabel()[0].toUpperCase() + scopeEntityLabel().slice(1)} "${trimmed}" created.`, 'success');
    } catch (err) {
      toast('Failed to create: ' + errMsg(err), 'error');
    }
  }

  async function handleRenameBlur(e) {
    const newName = e.target.value.trim();
    if (!STATE.activeId) return;
    if (!newName) {
      e.target.value = STATE.activeName;
      return;
    }
    if (newName === STATE.activeName) return;
    if (STATE.prompts.some((p) =>
      p.id !== STATE.activeId
      && p.name.toLowerCase() === newName.toLowerCase())) {
      toast('A prompt with that name already exists.', 'error');
      e.target.value = STATE.activeName;
      return;
    }
    try {
      await api.renameScopedPrompt(STATE.scope, STATE.activeId, newName, STATE.activeBody, 'Default');
      STATE.activeName = newName;
      const p = STATE.prompts.find((x) => x.id === STATE.activeId);
      if (p) p.name = newName;
      renderList();
      emitPromptsChanged();
      toast('Prompt renamed.', 'success');
    } catch (err) {
      toast('Failed to rename: ' + errMsg(err), 'error');
      e.target.value = STATE.activeName;
    }
  }

  async function handleSavePrompt() {
    if (!STATE.activeId) return;
    if (!isDirty()) return;
    try {
      await api.updateScopedPrompt(STATE.scope, STATE.activeId, {
        name: STATE.activeName,
        content: STATE.activeBody,
        category: 'Default',
      });
      STATE.activeBaseline = STATE.activeBody;
      const p = STATE.prompts.find((x) => x.id === STATE.activeId);
      if (p) p.content = STATE.activeBody;
      renderList();
      renderEditor();
      emitPromptsChanged();
      toast('Prompt saved.', 'success');
    } catch (err) {
      toast('Failed to save: ' + errMsg(err), 'error');
    }
  }

  async function handleDeletePrompt() {
    if (!STATE.activeId) return;
    const ok = window.confirm(`Delete prompt "${STATE.activeName}"? This cannot be undone.`);
    if (!ok) return;
    try {
      await api.deleteScopedPrompt(STATE.scope, STATE.activeId);
      STATE.activeId = null;
      STATE.activeBody = '';
      STATE.activeBaseline = '';
      STATE.activeName = '';
      await loadPromptsList();
      renderList();
      renderEditor();
      emitPromptsChanged();
      toast('Prompt deleted.', 'success');
    } catch (err) {
      toast('Failed to delete: ' + errMsg(err), 'error');
    }
  }

  function handleExportPrompt() {
    if (!STATE.activeId) return;
    const content = STATE.activeBody || '';
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${STATE.activeName.replace(/[^a-z0-9_-]/gi, '_')}.txt`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function handleRunPrompt() {
    if (!STATE.activeId || STATE.testRunning || isDirty()) return;
    if (!STATE.agentId) {
      toast('No agent selected. Pick one in the topbar.', 'error');
      return;
    }
    STATE.testRunning = true;
    STATE.testResponse = '';
    renderEditor();
    try {
      const result = await api.runPrompt(STATE.agentId, STATE.activeName, STATE.testVars);
      STATE.testResponse = typeof result === 'string'
        ? result
        : (result && typeof result === 'object'
            ? (result.response || JSON.stringify(result, null, 2))
            : String(result));
    } catch (err) {
      STATE.testResponse = 'Failed: ' + errMsg(err);
    } finally {
      STATE.testRunning = false;
      renderEditor();
    }
  }

  // ── Boot / mount ──────────────────────────────────────────────────────

  async function mount() {
    if (!STATE.mounted) {
      bindStaticControls();
      STATE.mounted = true;
    }
    if (STATE.booted) {
      await loadUserScopes();
      await loadPromptsList();
      renderList();
      return;
    }
    STATE.booted = true;
    try {
      await loadUserScopes();
      await Promise.all([loadActiveAgent(), loadPromptsList()]);
      renderList();
      renderEditor();
    } catch (err) {
      toast('Failed to load prompts: ' + errMsg(err), 'error');
    }
  }

  function bindStaticControls() {
    const search = $('#pl-search');
    if (search) {
      search.addEventListener('input', (e) => {
        STATE.listFilter = e.target.value;
        renderList();
      });
    }
    const newBtn = $('#pl-new-prompt');
    if (newBtn) newBtn.addEventListener('click', handleCreatePrompt);

    document.querySelectorAll('#pl-scope-tabs [data-scope]').forEach((button) => {
      button.addEventListener('click', () => switchScope(button.dataset.scope || 'user'));
    });
    renderScopeTabs();

    // The Prompt Library is reached from the chains editor's toolbar
    // (no standalone sidenav item), so we offer a back-to-chains
    // shortcut here. AgixtSidenav.setActiveView is provided by app.js;
    // when running standalone (test harness), we no-op gracefully.
    const backBtn = $('#pl-back-to-chains');
    if (backBtn) {
      backBtn.addEventListener('click', () => {
        if (window.AgixtSidenav && typeof window.AgixtSidenav.setActiveView === 'function') {
          window.AgixtSidenav.setActiveView('chains');
        }
      });
    }

    // Refresh agent ID/name whenever the topbar emits agent-changed —
    // the test panel runs against the current agent.
    const event = tauri && tauri.event;
    if (event && event.listen) {
      event.listen('agixt-agent-changed', async () => {
        try {
          await api.refreshSettings();
          await loadUserScopes();
          await loadActiveAgent();
          await loadPromptsList(true);
          renderList();
          if (STATE.activeId && STATE.activeTab === 'test') renderEditor();
        } catch (_) { /* ignore */ }
      });
    }
  }

  window.AgixtPrompts = { mount };
})();

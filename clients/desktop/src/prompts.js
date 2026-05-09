/* Prompt Library side pane.
 *
 * Vanilla-JS port of web/app/settings/prompts/page.tsx, scoped to user-
 * level prompts in the "Default" category. The pane has two columns:
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

  async function loadPromptsList(force) {
    try {
      const rows = await api.listPrompts('Default');
      STATE.prompts = (rows || []).map((p) => ({
        id: p.id || p.prompt_id || '',
        name: p.name || p.prompt_name || '',
        content: p.content || p.prompt || p.prompt_content || '',
        category: p.category || p.prompt_category || 'Default',
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
        const detail = await api.getPrompt(STATE.activeId);
        if (detail) {
          if (!p) p = detail;
          else { p.content = detail.content; p.name = detail.name || p.name; }
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
      root.appendChild(el('div', { class: 'pl-list-empty' },
        STATE.prompts.length === 0
          ? 'No prompts yet. Click + to create one.'
          : 'No prompts match this search.'
      ));
      return;
    }

    items.forEach((p) => {
      const isActive = p.id === STATE.activeId;
      const preview = (p.content || '').replace(/\s+/g, ' ').slice(0, 140);
      const item = el('button', {
        class: 'pl-list-item' + (isActive ? ' is-active' : ''),
        onclick: () => selectPrompt(p.id),
        title: p.name,
      }, [
        el('span', { class: 'pl-list-item-name' }, p.name),
        preview ? el('span', { class: 'pl-list-item-preview' }, preview) : null,
      ]);
      root.appendChild(item);
    });
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
    return el('div', { class: 'pl-editor-empty' }, [
      el('div', { class: 'pl-editor-empty-icon', html: ICONS.book }),
      el('div', { class: 'pl-editor-empty-title' }, 'Prompt Library'),
      el('div', { class: 'pl-editor-empty-body' },
        'Save reusable prompt templates with named variables in `{curly_braces}`. They feed Prompt-type chain steps and the agent test panel.'
      ),
      btn(
        el('span', null, [
          el('span', { html: ICONS.plus }),
          el('span', { style: 'margin-left:6px' }, 'New prompt'),
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

    return el('div', { class: 'pl-editor-header' }, [
      el('div', { class: 'pl-editor-titlewrap' }, [titleInput]),
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

    const pane = el('section', { class: 'pl-edit-pane' }, [toolbar, grid]);
    setTimeout(() => bodyArea.focus(), 30);
    return pane;
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
      toast('A prompt with that name already exists.', 'error');
      return;
    }
    try {
      await api.createPrompt(trimmed, '', 'Default');
      await loadPromptsList();
      const created = STATE.prompts.find((p) => p.name === trimmed);
      if (created) {
        STATE.activeId = created.id;
        await loadActivePrompt();
      }
      renderList();
      renderEditor();
      emitPromptsChanged();
      toast(`Prompt "${trimmed}" created.`, 'success');
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
      await api.renamePrompt(STATE.activeId, newName);
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
      await api.updatePrompt(STATE.activeId, STATE.activeBody);
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
      await api.deletePrompt(STATE.activeId);
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
      await loadPromptsList();
      renderList();
      return;
    }
    STATE.booted = true;
    try {
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
          await loadActiveAgent();
          if (STATE.activeId && STATE.activeTab === 'test') renderEditor();
        } catch (_) { /* ignore */ }
      });
    }
  }

  window.AgixtPrompts = { mount };
})();

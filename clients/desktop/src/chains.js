/* Automation Chains side pane.
 *
 * Vanilla-JS port of web/app/settings/chains/page.tsx, scoped to user-level
 * chains. The desktop pane is much narrower than the web page, so we
 * deliberately drop the React Flow canvas in favor of a vertical card
 * stack — easier to scan and edit inside the side pane footprint.
 *
 * Lifecycle: app.js calls window.AgixtChains.mount() the first time the
 * user activates the pane. Subsequent activations just refresh the chain
 * list. All AGiXT REST calls go through window.AgixtApi (chain.* + agent
 * + prompt + command helpers added in agixt-api.js).
 *
 * Editor model:
 *   - State.chainsList — the left-column chain list. Refreshed after any
 *     create/rename/delete.
 *   - State.activeChain — the selected chain's full {chainName,
 *     description, steps[]}. Loaded on selection and after any step op.
 *   - State.dirty — Map<stepNumber, {agent_id, prompt_type, prompt}> for
 *     unsaved per-step edits. The user clicks Save (per step) or Save All
 *     to flush. Save All is the explicit batch button in the header.
 *
 * AGiXT API quirk: the chain GET returns {chainName: {description, steps}}
 * and step reads include `agent_name`, while step writes require `agent_id`.
 * agixt-api.js unwraps the GET; the editor maintains an agents-by-name map
 * to translate name → id at save time.
 */
(function () {
  const tauri = window.__TAURI__;
  if (!tauri) return;
  const invoke = tauri.core.invoke;
  const api = window.AgixtApi;
  if (!api) {
    console.error('chains.js: AgixtApi unavailable');
    return;
  }

  const $ = (sel, root) => (root || document).querySelector(sel);

  // ── State ─────────────────────────────────────────────────────────────
  const STATE = {
    mounted: false,
    booted: false,
    scope: (() => {
      try { return window.localStorage.getItem('chainEditorScope') || 'user'; }
      catch (_) { return 'user'; }
    })(),
    scopes: new Set(),
    roleId: null,
    chainsList: [],
    listFilter: '',
    activeChainId: null,
    activeChain: null,
    agentsByName: new Map(),
    agents: [],
    promptsByName: new Map(),
    prompts: [],
    promptsLoaded: false,
    expandedSteps: new Set(),
    dirty: new Map(), // stepNumber -> { agent_id, prompt_type, prompt }
    argCache: new Map(), // key (`${type}::${target}`) -> string[]
    commandsByAgent: new Map(), // agentName -> { extension -> [commandNames] }
    abilityAgentId: '', // agent picked in the toolbar for the chain-ability toggle
    abilityAgentName: '', // matching name for status text
    abilityEnabled: false, // is the active chain enabled as a command on abilityAgentId?
    abilityChecking: false,
    showHelpBanner: false,
    // The autosave preference is persisted to localStorage so the user's
    // choice survives across sessions, mirroring the web's behavior.
    autosaveEnabled: (() => {
      try { return window.localStorage.getItem('chainEditorAutosave') === 'true'; }
      catch (_) { return false; }
    })(),
    // The chain list panel collapse state — mirrors the workspace editor's
    // Files-panel pattern. Default open; toggling persists to localStorage
    // so the user's choice carries across sessions and pane re-mounts.
    listOpen: (() => {
      try {
        const v = window.localStorage.getItem('chainEditorListOpen');
        return v === null ? true : v === 'true';
      } catch (_) { return true; }
    })(),
  };

  function setAutosave(enabled) {
    STATE.autosaveEnabled = !!enabled;
    try { window.localStorage.setItem('chainEditorAutosave', String(STATE.autosaveEnabled)); }
    catch (_) { /* ignore */ }
  }

  function setListOpen(open) {
    STATE.listOpen = !!open;
    try { window.localStorage.setItem('chainEditorListOpen', String(STATE.listOpen)); }
    catch (_) { /* ignore */ }
    renderListVisibility();
  }

  function isAdminRole() {
    return STATE.roleId === 0 || STATE.roleId === 1;
  }

  function hasScope(name) {
    return STATE.scopes.has('*') || STATE.scopes.has('*:*') || STATE.scopes.has(name);
  }

  function canUseChainScope(scope) {
    if (scope === 'user') return true;
    if (scope === 'company') {
      return isAdminRole() || hasScope('company:chains') || hasScope('company:admin');
    }
    if (scope === 'server') {
      return STATE.roleId === 0 || hasScope('server:chains') || hasScope('server:admin');
    }
    return false;
  }

  function scopeLabel(scope) {
    if (scope === 'company') return 'Company';
    if (scope === 'server') return 'Server';
    return 'My Chains';
  }

  function isSharedScope() {
    return STATE.scope === 'company' || STATE.scope === 'server';
  }

  function setScope(scope) {
    STATE.scope = canUseChainScope(scope) ? scope : 'user';
    try { window.localStorage.setItem('chainEditorScope', STATE.scope); } catch (_) {}
  }

  /** Toggle the chain list panel vs. its collapsed strip. The two
   *  elements are siblings inside `.cn-body`; we just flip their
   *  display state instead of adding/removing them, so the user's
   *  scroll position and search filter are preserved. */
  function renderListVisibility() {
    const list = $('#cn-list');
    const strip = $('#cn-list-collapsed');
    if (list) list.style.display = STATE.listOpen ? '' : 'none';
    if (strip) strip.style.display = STATE.listOpen ? 'none' : '';
  }

  // ── Toast ─────────────────────────────────────────────────────────────
  let toastTimer = null;
  function toast(message, kind) {
    const el = $('#cn-toast');
    if (!el) return;
    el.textContent = message;
    el.className = 'cn-toast' + (kind ? ' ' + kind : '');
    el.hidden = false;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, kind === 'error' ? 6000 : 3000);
  }
  function errMsg(err) {
    if (!err) return 'Unknown error';
    if (typeof err === 'string') return err;
    return err.error || err.detail || err.message || String(err);
  }

  // ── Helpers ───────────────────────────────────────────────────────────
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
    if (opts.size === 'sm') cls.push('btn-sm');
    return el('button', {
      type: 'button',
      class: cls.join(' '),
      onclick: opts.onclick,
      disabled: opts.disabled,
      title: opts.title,
      'aria-label': opts.ariaLabel,
    }, label);
  }

  function iconBtn(svgHtml, opts) {
    opts = opts || {};
    const cls = ['cn-icon-btn'];
    if (opts.kind) cls.push('is-' + opts.kind);
    const b = el('button', {
      type: 'button',
      class: cls.join(' '),
      onclick: opts.onclick,
      disabled: opts.disabled,
      title: opts.title,
      'aria-label': opts.ariaLabel || opts.title,
      html: svgHtml,
    });
    return b;
  }

  // Inline SVG icons. Same set used across the desktop client (lucide-derived).
  const ICONS = {
    plus: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>',
    plusSmall: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>',
    save: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/></svg>',
    trash: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>',
    play: '<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M8 5v14l11-7z"/></svg>',
    arrowUp: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>',
    arrowDown: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12l7 7 7-7"/></svg>',
    chevronDown: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>',
    chevronRight: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 6 6 6-6 6"/></svg>',
    download: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>',
    upload: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/></svg>',
    saveAll: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 4h10l4 4v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/><path d="M14 4v4H8V4M8 14h8"/></svg>',
    fileText: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/></svg>',
    terminal: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m4 17 6-6-6-6M12 19h8"/></svg>',
    link2: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 17H7a5 5 0 0 1 0-10h2M15 7h2a5 5 0 0 1 0 10h-2M8 12h8"/></svg>',
    workflow: '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect width="8" height="8" x="3" y="3" rx="2"/><path d="M7 11v4a2 2 0 0 0 2 2h4"/><rect width="8" height="8" x="13" y="13" rx="2"/></svg>',
  };

  const STEP_TYPES = ['Prompt', 'Command', 'Chain'];
  const STEP_TYPE_BADGE = {
    Prompt: { cls: 'is-prompt', icon: ICONS.fileText },
    Command: { cls: 'is-command', icon: ICONS.terminal },
    Chain: { cls: 'is-chain', icon: ICONS.link2 },
  };

  // System args we never expose in the editor — these are injected by the
  // backend at execution time.
  const SYSTEM_INJECTED_ARGS = new Set([
    'agent_name', 'COMMANDS', 'command_list', 'date', 'working_directory',
    'helper_agent_name', 'conversation_history', 'persona', 'import_files',
    'output_url',
  ]);
  const STRUCTURAL_ARGS = new Set([
    'prompt_name', 'prompt_category', 'command_name', 'chain', 'chain_name',
  ]);
  const CONDITIONAL_ARGS = new Set(['context', 'user_input']);

  function isStructural(name) { return STRUCTURAL_ARGS.has(name); }
  function isInjected(name) { return SYSTEM_INJECTED_ARGS.has(name); }

  // ── Data loading ──────────────────────────────────────────────────────

  async function loadAgents(force) {
    if (STATE.agents.length && !force) return STATE.agents;
    let agents = [];
    try {
      // Tauri's list_agents returns AgentInfo[] with id+name; the JS
      // listAgents helper hits /v1/agent directly. Prefer Tauri because it
      // already shapes the response, falling back to JS in browser preview.
      try { agents = await invoke('list_agents'); }
      catch (_) { agents = await api.listAgents(); }
    } catch (err) {
      console.warn('chains: list_agents failed', err);
      agents = [];
    }
    // Filter to current company when known. The chains pane only edits
    // user-level chains so we want agents the user can actually call.
    let s = null;
    try { s = await api.getSettings(); } catch (_) {}
    const companyId = (s && s.company_id) || null;
    const filtered = companyId
      ? agents.filter((a) => !a.company_id || a.company_id === companyId)
      : agents;
    STATE.agents = filtered.slice().sort((a, b) =>
      (a.name || '').toLowerCase().localeCompare((b.name || '').toLowerCase())
    );
    STATE.agentsByName = new Map(STATE.agents.map((a) => [a.name, a]));
    // The chain-as-ability toggle defaults to the topbar agent — that's
    // the agent the user is actively chatting with, so it's the right
    // default when they want to expose a chain as a callable command.
    if (s && s.agent_id) {
      STATE.abilityAgentId = s.agent_id;
      STATE.abilityAgentName = s.agent_name || '';
    } else if (STATE.agents.length) {
      STATE.abilityAgentId = STATE.agents[0].id;
      STATE.abilityAgentName = STATE.agents[0].name || '';
    }
    return STATE.agents;
  }

  async function loadPrompts(force) {
    if (STATE.promptsLoaded && !force) return STATE.prompts;
    try {
      const rows = await api.listPrompts('Default');
      STATE.prompts = (rows || []).map((p) => ({
        id: p.id || p.prompt_id || '',
        name: p.name || p.prompt_name || '',
      })).filter((p) => p.name);
      STATE.prompts.sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));
      STATE.promptsByName = new Map(STATE.prompts.map((p) => [p.name, p]));
      STATE.promptsLoaded = true;
    } catch (err) {
      console.warn('chains: list_prompts failed', err);
      STATE.prompts = [];
      STATE.promptsByName = new Map();
      STATE.promptsLoaded = true;
    }
    return STATE.prompts;
  }

  async function loadAgentCommands(agentName) {
    if (!agentName) return {};
    const cached = STATE.commandsByAgent.get(agentName);
    if (cached) return cached;
    const agent = STATE.agentsByName.get(agentName);
    if (!agent || !agent.id) {
      STATE.commandsByAgent.set(agentName, {});
      return {};
    }
    try {
      const exts = await api.getAgentExtensions(agent.id);
      const groups = {};
      (exts || []).forEach((ext) => {
        const name = ext.extension_name || ext.friendly_name || 'Other';
        const cmds = (ext.commands || [])
          .map((c) => c.friendly_name || c.command_name)
          .filter(Boolean);
        if (cmds.length) {
          groups[name] = cmds.sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));
        }
      });
      STATE.commandsByAgent.set(agentName, groups);
      return groups;
    } catch (err) {
      console.warn('chains: getAgentExtensions failed', err);
      STATE.commandsByAgent.set(agentName, {});
      return {};
    }
  }

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
      console.warn('chains: load user scopes failed', err);
      STATE.scopes = new Set();
      STATE.roleId = null;
    }
    if (!canUseChainScope(STATE.scope)) setScope('user');
    renderScopeTabs();
  }

  async function loadChainsList() {
    try {
      const rows = await api.listScopedChains(STATE.scope);
      STATE.chainsList = (rows || []).map((c) => ({
        id: c.id || c.chain_id || '',
        chainName: c.chainName || c.chain_name || c.name || '',
        description: c.description || '',
      })).filter((c) => c.id && c.chainName);
      STATE.chainsList.sort((a, b) => a.chainName.toLowerCase().localeCompare(b.chainName.toLowerCase()));
    } catch (err) {
      toast('Failed to load chains: ' + errMsg(err), 'error');
      STATE.chainsList = [];
    }
  }

  async function loadActiveChain() {
    if (!STATE.activeChainId) {
      STATE.activeChain = null;
      STATE.abilityEnabled = false;
      return;
    }
    try {
      const chain = await api.getScopedChain(STATE.scope, STATE.activeChainId);
      // The list has the description (the GET endpoint sometimes omits it),
      // so backfill from the cached list when missing.
      if (chain && !chain.description) {
        const listed = STATE.chainsList.find((c) => c.id === STATE.activeChainId);
        chain.description = listed ? (listed.description || '') : '';
      }
      STATE.activeChain = chain;
    } catch (err) {
      toast('Failed to load chain: ' + errMsg(err), 'error');
      STATE.activeChain = null;
    }
    STATE.dirty.clear();
    STATE.expandedSteps.clear();
    // Resolve whether the chain is currently enabled as a command on the
    // toolbar agent. Awaited so the editor first-paint already shows the
    // settled Enable/Disable state — otherwise the button rendered while
    // the probe was still in-flight stayed stuck on "Checking…" because
    // nothing re-rendered when the promise resolved.
    if (isSharedScope()) STATE.abilityEnabled = false;
    else await refreshAbilityStatus();
  }

  function renderScopeTabs() {
    const wrap = $('#cn-scope-tabs');
    if (!wrap) return;
    wrap.querySelectorAll('[data-scope]').forEach((node) => {
      const scope = node.dataset.scope || 'user';
      const allowed = canUseChainScope(scope);
      node.classList.toggle('is-active', scope === STATE.scope);
      node.disabled = !allowed;
      node.setAttribute('aria-selected', scope === STATE.scope ? 'true' : 'false');
      node.title = allowed
        ? `${scopeLabel(scope)} scope`
        : `You do not have access to ${scopeLabel(scope).toLowerCase()} chains.`;
    });
  }

  async function switchScope(scope) {
    if (scope === STATE.scope) return;
    if (!canUseChainScope(scope)) {
      toast(`You do not have access to ${scopeLabel(scope).toLowerCase()} chains.`, 'error');
      renderScopeTabs();
      return;
    }
    if (STATE.dirty.size > 0) {
      const ok = window.confirm('You have unsaved changes. Discard them and switch chain scope?');
      if (!ok) return;
    }
    setScope(scope);
    STATE.activeChainId = null;
    STATE.activeChain = null;
    STATE.dirty.clear();
    STATE.expandedSteps.clear();
    renderScopeTabs();
    renderList();
    renderEditor(true);
    await loadChainsList();
    renderList();
    renderEditor();
  }

  /** Probe whether STATE.activeChain is enabled as a callable command on
   *  STATE.abilityAgentId, updating STATE.abilityEnabled. The agent's
   *  enabled-commands map keys on the chain name, so a name match (case-
   *  insensitive) is the source of truth — the same heuristic the web
   *  uses in `normalizedAgentCommands`.
   *
   *  Doesn't flip `abilityChecking` — that flag is reserved for the
   *  active toggle (button click) where we want the button visibly
   *  disabled while the PATCH is in flight. The initial probe is silent. */
  async function refreshAbilityStatus() {
    if (!STATE.activeChain || !STATE.abilityAgentId) {
      STATE.abilityEnabled = false;
      return;
    }
    const checkingChainId = STATE.activeChainId;
    try {
      const exts = await api.getAgentExtensions(STATE.abilityAgentId);
      // Bail if the user switched chains while we were checking — we
      // don't want to clobber the new chain's state with stale data.
      if (STATE.activeChainId !== checkingChainId) return;
      const target = (STATE.activeChain.chainName || '').trim().toLowerCase();
      let enabled = false;
      (exts || []).forEach((ext) => {
        (ext.commands || []).forEach((cmd) => {
          const name = (cmd.friendly_name || cmd.command_name || '').trim().toLowerCase();
          if (name === target && cmd.enabled === true) enabled = true;
        });
      });
      STATE.abilityEnabled = enabled;
    } catch (err) {
      if (STATE.activeChainId === checkingChainId) {
        STATE.abilityEnabled = false;
      }
    }
  }

  async function handleToggleAbility() {
    if (!STATE.activeChain || !STATE.abilityAgentId) return;
    const target = STATE.activeChain.chainName;
    const next = !STATE.abilityEnabled;
    STATE.abilityChecking = true;
    renderEditor();
    try {
      await api.toggleCommand(STATE.abilityAgentId, target, next);
      STATE.abilityEnabled = next;
      toast(
        next
          ? `"${target}" is now callable from ${STATE.abilityAgentName}.`
          : `"${target}" is no longer callable from ${STATE.abilityAgentName}.`,
        'success'
      );
    } catch (err) {
      toast('Failed to update ability: ' + errMsg(err), 'error');
    } finally {
      STATE.abilityChecking = false;
      renderEditor();
    }
  }

  /** Resolve the args a step exposes for editing, given the current target.
   *  Cached per (type,target) pair to avoid re-fetching when the user
   *  twiddles other fields. */
  async function loadStepArgs(stepType, targetName, agentName) {
    if (!targetName) return [];
    const key = `${stepType}::${targetName}`;
    if (STATE.argCache.has(key)) return STATE.argCache.get(key);
    let args = [];
    try {
      if (stepType === 'Prompt') {
        const prompt = STATE.promptsByName.get(targetName);
        if (prompt && prompt.id) args = await api.getPromptArgs(prompt.id);
      } else if (stepType === 'Command') {
        args = await api.getCommandArgs(targetName);
      } else if (stepType === 'Chain') {
        // Look up by name in chains list.
        const chain = STATE.chainsList.find((c) => c.chainName === targetName);
        if (chain) args = await api.getChainArgs(chain.id);
      }
    } catch (err) {
      console.warn('chains: loadStepArgs failed', err);
      args = [];
    }
    if (!Array.isArray(args)) args = Object.keys(args || {});
    args = args.filter((a) =>
      a && !STRUCTURAL_ARGS.has(a) && !SYSTEM_INJECTED_ARGS.has(a) && !CONDITIONAL_ARGS.has(a)
    );
    args = Array.from(new Set(args));
    STATE.argCache.set(key, args);
    return args;
  }

  // ── Render: list ──────────────────────────────────────────────────────

  function renderList() {
    const root = $('#cn-list-scroll');
    if (!root) return;
    root.innerHTML = '';
    const filter = STATE.listFilter.trim().toLowerCase();
    const items = filter
      ? STATE.chainsList.filter((c) =>
          c.chainName.toLowerCase().includes(filter)
          || (c.description || '').toLowerCase().includes(filter))
      : STATE.chainsList;

    if (!items.length) {
      root.appendChild(el('div', { class: 'cn-list-empty' },
        STATE.chainsList.length === 0
          ? `No ${scopeLabel(STATE.scope).toLowerCase()} chains yet. Click + to create one.`
          : 'No chains match this search.'
      ));
      return;
    }

    items.forEach((c) => {
      const isActive = c.id === STATE.activeChainId;
      const item = el('button', {
        class: 'cn-list-item' + (isActive ? ' is-active' : ''),
        onclick: () => selectChain(c.id),
        title: c.chainName,
      }, [
        el('span', { class: 'cn-list-item-name' }, c.chainName),
        isSharedScope()
          ? el('span', { class: 'cn-list-item-desc' }, scopeLabel(STATE.scope) + ' scope')
          : null,
        c.description
          ? el('span', { class: 'cn-list-item-desc' }, c.description)
          : null,
      ]);
      root.appendChild(item);
    });
  }

  async function selectChain(chainId) {
    if (STATE.activeChainId === chainId) return;
    if (STATE.dirty.size > 0) {
      const ok = window.confirm('You have unsaved changes. Discard them and switch chains?');
      if (!ok) return;
    }
    STATE.activeChainId = chainId;
    renderList();
    renderEditor(/* loading */ true);
    await loadActiveChain();
    renderEditor();
  }

  // ── Render: editor ────────────────────────────────────────────────────

  function renderEditor(loading) {
    const root = $('#cn-editor');
    if (!root) return;
    root.innerHTML = '';

    if (!STATE.activeChainId) {
      root.appendChild(renderEmptyState());
      return;
    }
    if (loading || !STATE.activeChain) {
      const empty = el('div', { class: 'cn-editor-empty' }, [
        el('div', { class: 'cn-editor-empty-icon', html: ICONS.workflow }),
        el('div', { class: 'cn-editor-empty-title' }, 'Loading chain…'),
      ]);
      root.appendChild(empty);
      return;
    }

    root.appendChild(renderEditorHeader());
    if (STATE.showHelpBanner) root.appendChild(renderHelpBanner());
    root.appendChild(renderStepsScroll());
  }

  function renderHelpBanner() {
    const row = (iconHtml, name, desc) => el('div', { class: 'cn-help-row' }, [
      el('span', { class: 'cn-help-icon', html: iconHtml }),
      el('span', null, [
        el('strong', null, name + ': '),
        desc,
      ]),
    ]);
    const tokenChip = (text) => el('code', { class: 'cn-help-token' }, text);
    return el('div', { class: 'cn-help-banner' }, [
      el('div', { class: 'cn-help-section' }, [
        el('h3', { class: 'cn-help-title' }, 'Toolbar reference'),
        row(ICONS.saveAll, 'Save all', 'Flush every unsaved step change at once.'),
        row('<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>', 'Autosave', 'Commit each field as you blur it — toggle on for fast iteration.'),
        row(ICONS.play, 'Run', 'Execute the chain end-to-end with optional inputs.'),
        row('<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v10M18.4 6.6a9 9 0 1 1-12.77.04"/></svg>', 'Enable for agent', 'Expose this chain as a callable command on your agent.'),
        row(ICONS.download, 'Export', 'Download the chain steps as JSON.'),
        row(ICONS.upload, 'Import', 'Replace the chain steps from a JSON file.'),
        row(ICONS.trash, 'Delete', 'Permanently remove this chain.'),
      ]),
      el('div', { class: 'cn-help-section' }, [
        el('h3', { class: 'cn-help-title' }, 'Chain workflow concepts'),
        el('p', { class: 'cn-help-line' }, [
          el('strong', null, 'Step injection: '),
          'Reference earlier outputs with ', tokenChip('{STEP1}'), ', ', tokenChip('{STEP2}'),
          ', etc. inside any later prompt or argument.',
        ]),
        el('p', { class: 'cn-help-line' }, [
          el('strong', null, 'User input: '),
          'The ', tokenChip('{user_input}'),
          ' variable carries the value you pass in when you run the chain.',
        ]),
        el('p', { class: 'cn-help-line' }, [
          el('strong', null, 'Async execution: '),
          'Steps that don’t reference an earlier step run in parallel — order only matters when one depends on another.',
        ]),
      ]),
    ]);
  }

  function renderEmptyState() {
    const chip = (type, html) => el('div', {
      class: 'cn-empty-chip is-' + type.toLowerCase(),
    }, [
      el('span', { class: 'cn-empty-chip-icon', html }),
      el('span', null, type),
    ]);
    return el('div', { class: 'cn-editor-empty' }, [
      el('div', { class: 'cn-editor-empty-icon', html: ICONS.workflow }),
      el('div', { class: 'cn-editor-empty-title' }, 'Automation Chains'),
      el('div', { class: 'cn-editor-empty-body' },
        'Sequence agent steps into a reusable workflow — each step’s output flows into the next. Pick a chain on the left, or start a new one.'
      ),
      el('div', { class: 'cn-empty-chips' }, [
        chip('Prompt', ICONS.fileText),
        chip('Command', ICONS.terminal),
        chip('Chain', ICONS.link2),
      ]),
      btn(
        el('span', null, [
          el('span', { html: ICONS.plus }),
          el('span', { style: 'margin-left:6px' }, 'New chain'),
        ]),
        { kind: 'primary', onclick: handleCreateChain }
      ),
    ]);
  }

  function renderEditorHeader() {
    const chain = STATE.activeChain;
    const titleInput = el('input', {
      class: 'cn-editor-title',
      type: 'text',
      value: chain.chainName,
      onblur: handleRenameChainBlur,
    });
    const descArea = el('textarea', {
      class: 'cn-editor-desc',
      rows: 1,
      placeholder: 'Add a description so future-you remembers what this chain does…',
      onblur: handleDescriptionBlur,
    }, chain.description || '');

    const dirtyCount = STATE.dirty.size;
    const saveAllLabel = el('span', {
      style: 'margin-left:6px',
      'data-cn-save-all-label': '',
    }, dirtyCount ? `Save all (${dirtyCount})` : 'Save all');
    const saveAllInner = el('span', null, [
      el('span', { html: ICONS.saveAll }),
      saveAllLabel,
    ]);
    const saveAllBtn = btn(saveAllInner, {
      kind: dirtyCount ? 'primary' : 'secondary',
      onclick: handleSaveAll,
      disabled: !dirtyCount,
      title: dirtyCount ? 'Save all unsaved step changes' : 'No unsaved changes',
    });
    saveAllBtn.setAttribute('data-cn-save-all', '');

    // Autosave toggle — persisted to localStorage. When enabled, blur on
    // any per-step field commits that step. Mirrors the web's toolbar
    // toggle but lives inline in the header instead of a floating bar.
    const autosaveToggle = renderAutosaveToggle();

    const runBtn = btn(
      el('span', { html: ICONS.play + '<span style="margin-left:6px">Run</span>' }),
      {
        kind: 'secondary',
        onclick: handleRunChain,
        disabled: isSharedScope(),
        title: isSharedScope()
          ? 'Clone or use this chain from an agent/user context to run it.'
          : 'Run this chain',
      }
    );
    const exportBtn = btn(
      el('span', { html: ICONS.download }),
      { kind: 'ghost', onclick: handleExportChain, title: 'Export as JSON', ariaLabel: 'Export chain' }
    );
    const importBtn = btn(
      el('span', { html: ICONS.upload }),
      { kind: 'ghost', onclick: handleImportSteps, title: 'Replace steps from JSON', ariaLabel: 'Import steps' }
    );

    // Help button — toggles the toolbar reference banner.
    const helpBtn = btn(
      el('span', {
        html: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></svg>',
      }),
      {
        kind: STATE.showHelpBanner ? 'primary' : 'ghost',
        onclick: () => { STATE.showHelpBanner = !STATE.showHelpBanner; renderEditor(); },
        title: 'Toolbar reference & chain concepts',
        ariaLabel: 'Help',
      }
    );

    const deleteBtn = btn(
      el('span', { html: ICONS.trash }),
      { kind: 'danger', onclick: handleDeleteChain, title: 'Delete this chain', ariaLabel: 'Delete chain' }
    );

    return el('div', { class: 'cn-editor-header' }, [
      el('div', { class: 'cn-editor-titlewrap' }, [titleInput, descArea]),
      el('div', { class: 'cn-editor-actions' }, [
        saveAllBtn, autosaveToggle, runBtn,
        renderAbilityControl(),
        exportBtn, importBtn, helpBtn, deleteBtn,
      ]),
    ]);
  }

  function renderAutosaveToggle() {
    const wrap = el('label', {
      class: 'cn-autosave' + (STATE.autosaveEnabled ? ' is-on' : ''),
      title: 'Auto-save changes when you click away from a field',
    }, [
      el('input', {
        type: 'checkbox',
        checked: STATE.autosaveEnabled,
        onchange: (e) => {
          setAutosave(e.target.checked);
          // Update the wrapper class without re-rendering everything.
          const w = e.target.closest('.cn-autosave');
          if (w) w.classList.toggle('is-on', STATE.autosaveEnabled);
        },
      }),
      el('span', { class: 'cn-switch-track', html: '' }),
      el('span', { class: 'cn-autosave-label' }, 'Autosave'),
    ]);
    return wrap;
  }

  /** Toolbar control that shows the active chain's status as a callable
   *  ability on the user's currently-selected agent and lets them toggle
   *  it. Calls PATCH /v1/agent/{id}/command with the chain name as the
   *  command_name — matches the web's handleToggleChainAbility. */
  function renderAbilityControl() {
    const chain = STATE.activeChain;
    if (!chain || !STATE.abilityAgentId) {
      return el('span', { style: 'display:none' });
    }
    const enabled = STATE.abilityEnabled;
    const checking = STATE.abilityChecking;
    const shared = isSharedScope();
    return btn(
      el('span', null, [
        el('span', {
          html: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v10M18.4 6.6a9 9 0 1 1-12.77.04"/></svg>',
        }),
        el('span', { style: 'margin-left:6px' },
          checking ? 'Checking…'
            : (enabled ? 'Disable for ' : 'Enable for ') + (STATE.abilityAgentName || 'agent')),
      ]),
      {
        kind: enabled ? 'secondary' : 'primary',
        disabled: checking || shared,
        onclick: handleToggleAbility,
        title: shared
          ? 'Company/server chains are managed here; enable a callable command from an agent/user chain context.'
          : enabled
          ? `Currently exposed as a command on ${STATE.abilityAgentName}. Click to disable.`
          : `Expose this chain as a callable command on ${STATE.abilityAgentName}.`,
      }
    );
  }

  function renderStepsScroll() {
    const scroll = el('div', { class: 'cn-steps-scroll' });
    const stack = el('div', { class: 'cn-steps' });

    const steps = (STATE.activeChain.steps || []).slice().sort((a, b) =>
      (a.step || 0) - (b.step || 0));

    if (steps.length === 0) {
      stack.appendChild(el('div', { class: 'cn-list-empty' },
        'No steps yet. Click "Add step" below to get started.'
      ));
    }

    steps.forEach((step, idx) => {
      // "Insert above" affordance between cards.
      if (idx > 0) {
        stack.appendChild(renderInsertSlot(step.step));
      } else {
        stack.appendChild(renderInsertSlot(1, /* first */ true));
      }
      // Connector arrow above each card except the first. Its gradient
      // pulls from the accent of the step above and the step below so a
      // Prompt → Command pipe visually transitions blue → green.
      if (idx > 0) {
        const prev = effectiveStep(steps[idx - 1]);
        const cur = effectiveStep(step);
        stack.appendChild(renderArrow(false, prev.promptType, cur.promptType));
      } else {
        stack.appendChild(renderArrow(true));
      }
      stack.appendChild(renderStepCard(step, idx === steps.length - 1, idx));
    });
    if (steps.length > 0) {
      const last = effectiveStep(steps[steps.length - 1]);
      stack.appendChild(renderArrow(false, last.promptType, last.promptType));
    }

    const tail = el('div', { class: 'cn-step-add-tail' }, [
      btn(
        el('span', { html: ICONS.plus + '<span style="margin-left:6px">Add step</span>' }),
        { kind: 'secondary', onclick: () => handleAddStep((STATE.activeChain.steps || []).length + 1) }
      ),
    ]);
    stack.appendChild(tail);

    scroll.appendChild(stack);
    return scroll;
  }

  function renderArrow(hideTop, prevType, nextType) {
    if (hideTop) return el('div', { style: 'height:0' });
    const accents = {
      Prompt: '#5b8eff',
      Command: '#62c886',
      Chain: '#b095f0',
    };
    const prev = accents[prevType] || 'var(--accent)';
    const next = accents[nextType] || 'var(--accent)';
    return el('div', {
      class: 'cn-step-arrow',
      style: `--cn-step-accent-prev:${prev};--cn-step-accent-next:${next}`,
    });
  }

  function renderInsertSlot(targetStepNumber, first) {
    if (first) return el('div', { style: 'height:0' });
    return el('div', { class: 'cn-step-add-between' }, [
      el('button', {
        type: 'button',
        class: 'cn-step-add-btn',
        title: `Insert step at position ${targetStepNumber}`,
        'aria-label': `Insert step at position ${targetStepNumber}`,
        html: ICONS.plusSmall,
        onclick: () => handleAddStep(targetStepNumber),
      }),
    ]);
  }

  function renderStepCard(step, isLast, idx) {
    const stepNum = step.step;
    const dirty = STATE.dirty.get(stepNum);
    const expanded = STATE.expandedSteps.has(stepNum);

    // Effective values combine any unsaved edits over the persisted step.
    const eff = effectiveStep(step);
    const badge = STEP_TYPE_BADGE[eff.promptType] || STEP_TYPE_BADGE.Prompt;

    const card = el('div', {
      class: 'cn-step '
        + (badge.cls || '')
        + (dirty ? ' is-modified' : '')
        + (expanded ? ' is-expanded' : ''),
      dataset: { step: stepNum },
    });

    const titleClass = 'cn-step-title' + (eff.targetName ? '' : ' is-empty');
    const titleText = eff.targetName || `Select ${eff.promptType}…`;

    const header = el('div', {
      class: 'cn-step-header',
      onclick: (e) => {
        // Don't toggle when clicking actions in the header.
        if (e.target.closest('.cn-step-actions')) return;
        toggleStepExpanded(stepNum);
      },
    }, [
      el('div', { class: 'cn-step-badge ' + badge.cls, html: badge.icon }),
      el('div', { class: 'cn-step-meta' }, [
        el('div', { class: 'cn-step-meta-row' }, [
          el('span', null, `Step ${stepNum}`),
          el('span', { class: 'cn-step-meta-pill' }, eff.promptType),
          eff.agentName
            ? el('span', { class: 'cn-step-meta-agent' }, eff.agentName)
            : null,
          dirty ? el('span', { class: 'cn-step-modified' }, [
            el('span', { class: 'cn-step-modified-dot' }),
            'Unsaved',
          ]) : null,
        ]),
        el('div', { class: titleClass }, titleText),
      ]),
      el('div', { class: 'cn-step-actions' }, [
        iconBtn(ICONS.arrowUp, {
          title: 'Move up',
          onclick: () => handleMoveStep(stepNum, 'up'),
          disabled: idx === 0,
        }),
        iconBtn(ICONS.arrowDown, {
          title: 'Move down',
          onclick: () => handleMoveStep(stepNum, 'down'),
          disabled: isLast,
        }),
        iconBtn(ICONS.save, {
          kind: 'save',
          title: dirty ? 'Save changes' : 'No changes',
          disabled: !dirty,
          onclick: () => handleSaveStep(stepNum),
        }),
        iconBtn(ICONS.trash, {
          kind: 'danger',
          title: 'Delete step',
          onclick: () => handleDeleteStep(stepNum),
        }),
        iconBtn(expanded ? ICONS.chevronDown : ICONS.chevronRight, {
          title: expanded ? 'Collapse' : 'Expand',
          onclick: () => toggleStepExpanded(stepNum),
        }),
      ]),
    ]);

    card.appendChild(header);

    const body = el('div', { class: 'cn-step-body' + (expanded ? '' : ' is-collapsed') });
    if (expanded) renderStepBody(body, step, eff);
    card.appendChild(body);
    return card;
  }

  function effectiveStep(step) {
    const dirty = STATE.dirty.get(step.step);
    const promptType = (dirty && dirty.prompt_type) || step.prompt_type || 'Prompt';
    const prompt = (dirty && dirty.prompt) || step.prompt || {};
    let targetName = '';
    if (promptType === 'Prompt') targetName = prompt.prompt_name || '';
    else if (promptType === 'Command') targetName = prompt.command_name || '';
    else if (promptType === 'Chain') targetName = prompt.chain_name || '';

    let agentName = '';
    if (dirty && dirty.agent_id) {
      // Resolve back to a name if we can — the dirty record stores ID for
      // the eventual API write but the UI shows names.
      const a = STATE.agents.find((x) => x.id === dirty.agent_id);
      agentName = a ? a.name : (dirty._agent_name || step.agent_name || '');
    } else {
      agentName = step.agent_name || '';
    }
    return { promptType, prompt, targetName, agentName };
  }

  // ── Step body (form) ─────────────────────────────────────────────────

  function renderStepBody(root, step, eff) {
    const stepNum = step.step;

    // Agent selector
    const agentSelect = el('select', {
      class: 'cn-select',
      onchange: (e) => onStepAgentChange(stepNum, e.target.value),
      onblur: () => autosaveStepIfEnabled(stepNum),
    });
    if (!eff.agentName) {
      agentSelect.appendChild(el('option', { value: '', disabled: true, selected: true }, 'Select agent…'));
    }
    STATE.agents.forEach((a) => {
      agentSelect.appendChild(el('option', {
        value: a.name,
        selected: a.name === eff.agentName,
      }, a.name));
    });
    if (eff.agentName && !STATE.agents.find((a) => a.name === eff.agentName)) {
      // Unknown agent (e.g. agent removed from this company) — still show
      // it so the user can either re-pick or save a fixed step over it.
      agentSelect.appendChild(el('option', {
        value: eff.agentName,
        selected: true,
      }, eff.agentName + ' (unavailable)'));
    }

    // Type selector
    const typeSelect = el('select', {
      class: 'cn-select',
      onchange: (e) => onStepTypeChange(stepNum, e.target.value),
      onblur: () => autosaveStepIfEnabled(stepNum),
    });
    STEP_TYPES.forEach((t) => {
      typeSelect.appendChild(el('option', {
        value: t,
        selected: t === eff.promptType,
      }, t));
    });

    root.appendChild(el('div', { class: 'cn-field' }, [
      el('label', { class: 'cn-field-label' }, 'Agent'),
      agentSelect,
    ]));
    root.appendChild(el('div', { class: 'cn-field' }, [
      el('label', { class: 'cn-field-label' }, 'Type'),
      typeSelect,
    ]));

    // Target selector — Prompt / Command / Chain.
    root.appendChild(renderStepTargetField(stepNum, eff));

    // Conditional fields — Prompt has Context, Chain has User Input.
    if (eff.promptType === 'Prompt') {
      const contextVal = (eff.prompt && eff.prompt.context != null) ? String(eff.prompt.context) : '';
      const ta = el('textarea', {
        class: 'cn-textarea',
        rows: 2,
        placeholder: 'e.g. {STEP1}',
        oninput: (e) => onStepArgChange(stepNum, 'context', e.target.value),
        onblur: () => autosaveStepIfEnabled(stepNum),
      }, contextVal);
      root.appendChild(el('div', { class: 'cn-field cn-step-body-full' }, [
        el('label', { class: 'cn-field-label' }, 'Context'),
        ta,
      ]));
    } else if (eff.promptType === 'Chain') {
      const uiVal = (eff.prompt && eff.prompt.user_input != null) ? String(eff.prompt.user_input) : '';
      const ta = el('textarea', {
        class: 'cn-textarea',
        rows: 2,
        placeholder: 'e.g. {STEP1}',
        oninput: (e) => onStepArgChange(stepNum, 'user_input', e.target.value),
        onblur: () => autosaveStepIfEnabled(stepNum),
      }, uiVal);
      root.appendChild(el('div', { class: 'cn-field cn-step-body-full' }, [
        el('label', { class: 'cn-field-label' }, 'User Input'),
        ta,
      ]));
    }

    // Args section — populated async after the target's args are known.
    const argsHost = el('div', { class: 'cn-args-section' }, [
      el('label', { class: 'cn-field-label' }, 'Arguments'),
      el('div', { class: 'cn-args-loading' }, [
        el('span', { class: 'cn-args-spinner' }),
        el('span', null, 'Loading arguments…'),
      ]),
    ]);
    root.appendChild(argsHost);

    if (eff.targetName) {
      loadStepArgs(eff.promptType, eff.targetName, eff.agentName).then((args) => {
        renderStepArgs(argsHost, stepNum, eff, args);
      }).catch((err) => {
        argsHost.innerHTML = '';
        argsHost.appendChild(el('label', { class: 'cn-field-label' }, 'Arguments'));
        argsHost.appendChild(el('div', { class: 'cn-args-empty' },
          'Failed to load arguments: ' + errMsg(err)));
      });
    } else {
      argsHost.innerHTML = '';
      argsHost.appendChild(el('label', { class: 'cn-field-label' }, 'Arguments'));
      argsHost.appendChild(el('div', { class: 'cn-args-empty' },
        `Pick a ${eff.promptType.toLowerCase()} to configure its arguments.`));
    }
  }

  function renderStepTargetField(stepNum, eff) {
    const wrap = el('div', { class: 'cn-field cn-step-body-full' });
    wrap.appendChild(el('label', { class: 'cn-field-label' },
      eff.promptType === 'Prompt' ? 'Prompt name'
        : eff.promptType === 'Command' ? 'Command name'
        : 'Chain name'
    ));
    if (eff.promptType === 'Prompt') {
      const sel = el('select', {
        class: 'cn-select',
        onchange: (e) => onStepTargetChange(stepNum, e.target.value),
        onblur: () => autosaveStepIfEnabled(stepNum),
      });
      sel.appendChild(el('option', { value: '' }, '— select prompt —'));
      STATE.prompts.forEach((p) => {
        sel.appendChild(el('option', {
          value: p.name,
          selected: p.name === eff.targetName,
        }, p.name));
      });
      if (eff.targetName && !STATE.promptsByName.has(eff.targetName)) {
        sel.appendChild(el('option', {
          value: eff.targetName, selected: true,
        }, eff.targetName + ' (missing)'));
      }
      wrap.appendChild(sel);
    } else if (eff.promptType === 'Command') {
      const sel = el('select', {
        class: 'cn-select',
        disabled: !eff.agentName,
        onchange: (e) => onStepTargetChange(stepNum, e.target.value),
        onblur: () => autosaveStepIfEnabled(stepNum),
      });
      sel.appendChild(el('option', { value: '' }, eff.agentName ? '— select command —' : 'Pick an agent first'));
      // Lazy-load commands for this agent.
      if (eff.agentName) {
        loadAgentCommands(eff.agentName).then((groups) => {
          // Keep the placeholder, then groups.
          const keys = Object.keys(groups || {}).sort();
          keys.forEach((g) => {
            const og = el('optgroup', { label: g });
            (groups[g] || []).forEach((c) => {
              og.appendChild(el('option', {
                value: c,
                selected: c === eff.targetName,
              }, c));
            });
            sel.appendChild(og);
          });
          if (eff.targetName && !keys.some((k) => (groups[k] || []).includes(eff.targetName))) {
            sel.appendChild(el('option', {
              value: eff.targetName, selected: true,
            }, eff.targetName + ' (not enabled)'));
          }
        });
      }
      wrap.appendChild(sel);
    } else { // Chain
      const sel = el('select', {
        class: 'cn-select',
        onchange: (e) => onStepTargetChange(stepNum, e.target.value),
        onblur: () => autosaveStepIfEnabled(stepNum),
      });
      sel.appendChild(el('option', { value: '' }, '— select chain —'));
      STATE.chainsList
        .filter((c) => c.id !== STATE.activeChainId) // can't call self
        .forEach((c) => {
          sel.appendChild(el('option', {
            value: c.chainName,
            selected: c.chainName === eff.targetName,
          }, c.chainName));
        });
      wrap.appendChild(sel);
    }
    return wrap;
  }

  function renderStepArgs(host, stepNum, eff, args) {
    host.innerHTML = '';
    host.appendChild(el('label', { class: 'cn-field-label' }, 'Arguments'));
    if (!args || args.length === 0) {
      host.appendChild(el('div', { class: 'cn-args-empty' },
        'No configurable arguments.'));
      return;
    }
    const grid = el('div', { class: 'cn-args-grid' });
    args.forEach((name) => {
      const id = `cn-arg-${stepNum}-${name}`;
      const value = (eff.prompt && eff.prompt[name] != null) ? eff.prompt[name] : '';
      const isBool = typeof value === 'boolean'
        || (typeof value === 'string' && /^(true|false)$/i.test(value.trim()));
      const isNumber = typeof value === 'number'
        || (typeof value === 'string' && value.trim() !== '' && !isNaN(Number(value)));
      const label = name.replace(/_/g, ' ')
        .replace(/(?:^|\s)\S/g, (c) => c.toUpperCase());

      if (isBool && typeof value !== 'string') {
        const checked = value === true;
        const sw = el('label', { class: 'cn-switch' }, [
          el('input', {
            type: 'checkbox', id, checked,
            onchange: (e) => {
              onStepArgChange(stepNum, name, e.target.checked);
              // Switches commit their final value on `change`, so we
              // can autosave immediately rather than waiting for blur.
              autosaveStepIfEnabled(stepNum);
            },
          }),
          el('span', { class: 'cn-switch-track' }),
        ]);
        const row = el('div', { class: 'cn-arg-bool' }, [
          el('label', { for: id, class: 'cn-field-label' }, label),
          sw,
        ]);
        grid.appendChild(row);
      } else {
        const input = el('input', {
          id,
          class: 'cn-input',
          type: isNumber ? 'number' : 'text',
          value: value === '' ? '' : String(value),
          placeholder: `Enter ${label}`,
          oninput: (e) => onStepArgChange(stepNum, name, e.target.value),
          onblur: () => autosaveStepIfEnabled(stepNum),
        });
        grid.appendChild(el('div', { class: 'cn-field' }, [
          el('label', { class: 'cn-field-label', for: id }, label),
          input,
        ]));
      }
    });
    host.appendChild(grid);
  }

  // ── Step edit handlers ────────────────────────────────────────────────

  function ensureDirty(stepNum) {
    if (STATE.dirty.has(stepNum)) return STATE.dirty.get(stepNum);
    const step = STATE.activeChain.steps.find((s) => s.step === stepNum);
    const agent = step ? STATE.agentsByName.get(step.agent_name) : null;
    const cur = {
      agent_id: agent ? agent.id : '',
      _agent_name: step ? step.agent_name : '',
      prompt_type: (step && step.prompt_type) || 'Prompt',
      prompt: Object.assign({}, (step && step.prompt) || {}),
    };
    STATE.dirty.set(stepNum, cur);
    return cur;
  }

  function onStepAgentChange(stepNum, name) {
    const dirty = ensureDirty(stepNum);
    const agent = STATE.agentsByName.get(name);
    dirty.agent_id = agent ? agent.id : '';
    dirty._agent_name = name;
    if (dirty.prompt_type === 'Command') {
      // Command list is per-agent; clear the cached commands for this step
      // so the target dropdown re-fetches against the new agent.
      dirty.prompt = pruneStructural(dirty.prompt, 'Command');
      dirty.prompt.command_name = '';
    }
    STATE.dirty.set(stepNum, dirty);
    refreshActiveStepCard(stepNum);
  }

  function onStepTypeChange(stepNum, type) {
    const dirty = ensureDirty(stepNum);
    dirty.prompt_type = type;
    // Reset structural fields and arg payload — they don't apply across types.
    dirty.prompt = pruneStructural({}, type);
    refreshActiveStepCard(stepNum);
  }

  function onStepTargetChange(stepNum, target) {
    const dirty = ensureDirty(stepNum);
    const type = dirty.prompt_type;
    if (type === 'Prompt') {
      dirty.prompt = Object.assign({}, dirty.prompt);
      dirty.prompt.prompt_name = target;
      dirty.prompt.prompt_category = 'Default';
      delete dirty.prompt.command_name;
      delete dirty.prompt.chain_name;
    } else if (type === 'Command') {
      dirty.prompt = Object.assign({}, dirty.prompt);
      dirty.prompt.command_name = target;
      delete dirty.prompt.prompt_name;
      delete dirty.prompt.prompt_category;
      delete dirty.prompt.chain_name;
    } else if (type === 'Chain') {
      dirty.prompt = Object.assign({}, dirty.prompt);
      dirty.prompt.chain_name = target;
      delete dirty.prompt.prompt_name;
      delete dirty.prompt.prompt_category;
      delete dirty.prompt.command_name;
    }
    refreshActiveStepCard(stepNum);
  }

  function onStepArgChange(stepNum, name, value) {
    const dirty = ensureDirty(stepNum);
    dirty.prompt = Object.assign({}, dirty.prompt);
    if (value === '' || value == null) {
      delete dirty.prompt[name];
    } else if (typeof value === 'string') {
      // Coerce primitives at save time, not while typing.
      dirty.prompt[name] = value;
    } else {
      dirty.prompt[name] = value;
    }
    // Don't full re-render on every keystroke — only update the modified
    // pill in the header.
    updateStepHeaderPills(stepNum);
  }

  /** Autosave dispatcher — called on blur from any per-step field. No-ops
   *  unless autosave is on AND the step has unsaved changes AND the step
   *  has the minimum required fields (agent + target). Mirrors the web's
   *  `handleBlurSave` pattern in ChainStepNode. */
  function autosaveStepIfEnabled(stepNum) {
    if (!STATE.autosaveEnabled) return;
    const dirty = STATE.dirty.get(stepNum);
    if (!dirty) return;
    if (!dirty.agent_id) return;
    // Don't autosave if the target is unset — would write a half-built
    // step. The user can still hit the explicit Save button to force it.
    const promptType = dirty.prompt_type;
    const prompt = dirty.prompt || {};
    let target = '';
    if (promptType === 'Prompt') target = prompt.prompt_name;
    else if (promptType === 'Command') target = prompt.command_name;
    else if (promptType === 'Chain') target = prompt.chain_name;
    if (!target) return;
    handleSaveStep(stepNum);
  }

  function pruneStructural(prompt, type) {
    const out = Object.assign({}, prompt || {});
    delete out.prompt_name;
    delete out.prompt_category;
    delete out.command_name;
    delete out.chain_name;
    if (type === 'Prompt') {
      out.prompt_name = '';
      out.prompt_category = 'Default';
    } else if (type === 'Command') {
      out.command_name = '';
    } else if (type === 'Chain') {
      out.chain_name = '';
    }
    return out;
  }

  function updateStepHeaderPills(stepNum) {
    const card = $(`.cn-step[data-step="${stepNum}"]`);
    if (!card) return;
    const dirty = STATE.dirty.has(stepNum);
    card.classList.toggle('is-modified', dirty);
    const headerRow = card.querySelector('.cn-step-meta-row');
    if (headerRow) {
      const existing = headerRow.querySelector('.cn-step-modified');
      if (dirty && !existing) {
        headerRow.appendChild(el('span', { class: 'cn-step-modified' }, [
          el('span', { class: 'cn-step-modified-dot' }),
          'Unsaved',
        ]));
      } else if (!dirty && existing) {
        existing.remove();
      }
    }
    // Also refresh the Save All counter in the header.
    refreshSaveAllButton();
  }

  function refreshSaveAllButton() {
    const btnEl = $('[data-cn-save-all]');
    if (!btnEl) return;
    const dirtyCount = STATE.dirty.size;
    btnEl.disabled = !dirtyCount;
    btnEl.classList.toggle('btn-primary', !!dirtyCount);
    btnEl.classList.toggle('btn-secondary', !dirtyCount);
    btnEl.title = dirtyCount ? 'Save all unsaved step changes' : 'No unsaved changes';
    const span = btnEl.querySelector('[data-cn-save-all-label]');
    if (span) {
      span.textContent = dirtyCount ? `Save all (${dirtyCount})` : 'Save all';
    }
  }

  function toggleStepExpanded(stepNum) {
    if (STATE.expandedSteps.has(stepNum)) STATE.expandedSteps.delete(stepNum);
    else STATE.expandedSteps.add(stepNum);
    refreshActiveStepCard(stepNum);
  }

  function refreshActiveStepCard(stepNum) {
    // Re-render the steps section. We don't surgically update because many
    // of the form fields (target dropdown, args list) are interdependent.
    const root = $('#cn-editor');
    if (!root) return;
    const oldScroll = root.querySelector('.cn-steps-scroll');
    const newScroll = renderStepsScroll();
    if (oldScroll && oldScroll.parentElement) {
      oldScroll.parentElement.replaceChild(newScroll, oldScroll);
    }
  }

  // ── Top-level handlers ────────────────────────────────────────────────

  async function handleCreateChain() {
    openCreateChainDialog();
  }

  /** Switch to the Prompt Library view-pane. Used by the toolbar
   *  shortcut in the chains editor header — prompts feed Prompt-step
   *  targets, so we don't show them as a separate top-level sidenav
   *  item, but users still need a quick path into managing them. */
  function handleOpenPromptLibrary() {
    if (window.AgixtSidenav && typeof window.AgixtSidenav.setActiveView === 'function') {
      window.AgixtSidenav.setActiveView('prompts');
    } else if (window.AgixtPrompts && typeof window.AgixtPrompts.mount === 'function') {
      // Fallback for tests / standalone hosts that don't have the sidenav
      // shim wired up — just lazy-mount and reveal the pane manually.
      const pane = document.querySelector('.view-pane[data-view="prompts"]');
      if (pane) pane.hidden = false;
      window.AgixtPrompts.mount();
    }
  }

  /** Modal mirroring the web's "Create or Import Automation Chain" dialog —
   *  name + description + an inline import-from-JSON option that imports
   *  steps into the freshly-created chain in one round-trip.
   *
   *  Name conflict behavior matches the web: imports auto-suffix `_1`,
   *  `_2`, … on collision; explicit creates surface an error toast. */
  function openCreateChainDialog() {
    const nameInput = el('input', {
      type: 'text', class: 'cn-input',
      placeholder: 'Enter chain name…', autofocus: true,
    });
    const descInput = el('textarea', {
      class: 'cn-textarea', rows: 3,
      placeholder: 'Add a description so future-you remembers what this chain does…',
    });
    const fileInput = el('input', { type: 'file', accept: '.json,application/json', hidden: true });
    const fileLabel = el('span', null, 'Or import from a JSON file:');
    const fileBtn = btn(
      el('span', null, [
        el('span', { html: ICONS.upload }),
        el('span', { style: 'margin-left:6px' }, 'Choose JSON file…'),
      ]),
      { kind: 'secondary', onclick: () => fileInput.click() }
    );
    const fileStatus = el('div', { style: 'font-size:11.5px;color:var(--text-faint);margin-top:4px' });

    let pickedFile = null;
    fileInput.addEventListener('change', () => {
      pickedFile = fileInput.files && fileInput.files[0];
      fileStatus.textContent = pickedFile ? `Selected: ${pickedFile.name}` : '';
      // If the user picks a file before naming the chain, derive a name
      // from the filename so the Create button can fire immediately.
      if (pickedFile && !nameInput.value.trim()) {
        nameInput.value = pickedFile.name.replace(/\.json$/i, '');
      }
      submitBtn.disabled = !nameInput.value.trim();
    });

    nameInput.addEventListener('input', () => {
      submitBtn.disabled = !nameInput.value.trim();
    });

    const closeBtn = el('button', { class: 'cn-modal-close', html: '×', 'aria-label': 'Close' });
    const cancelBtn = btn('Cancel', { kind: 'secondary' });
    const submitBtn = btn(
      el('span', null, [
        el('span', { html: ICONS.plus }),
        el('span', { style: 'margin-left:6px' }, 'Create'),
      ]),
      { kind: 'primary', disabled: true }
    );

    const modal = el('div', { class: 'cn-modal-backdrop' }, [
      el('div', { class: 'cn-modal' }, [
        el('div', { class: 'cn-modal-header' }, [
          el('h3', { class: 'cn-modal-title' }, 'Create or Import Automation Chain'),
          closeBtn,
        ]),
        el('div', { class: 'cn-modal-body' }, [
          el('div', { class: 'cn-field' }, [
            el('label', { class: 'cn-field-label' }, 'Name *'),
            nameInput,
          ]),
          el('div', { class: 'cn-field' }, [
            el('label', { class: 'cn-field-label' }, 'Description'),
            descInput,
          ]),
          el('div', { class: 'cn-field' }, [
            el('label', { class: 'cn-field-label' }, fileLabel),
            fileBtn,
            fileInput,
            fileStatus,
          ]),
        ]),
        el('div', { class: 'cn-modal-footer' }, [cancelBtn, submitBtn]),
      ]),
    ]);
    document.body.appendChild(modal);
    setTimeout(() => nameInput.focus(), 30);

    function close() { if (modal.parentElement) modal.parentElement.removeChild(modal); }
    closeBtn.addEventListener('click', close);
    cancelBtn.addEventListener('click', close);
    modal.addEventListener('click', (e) => { if (e.target === modal) close(); });

    submitBtn.addEventListener('click', async () => {
      const name = nameInput.value.trim();
      const description = descInput.value.trim();
      if (!name) return;

      // Resolve a unique chain name. For explicit creates we fail loudly;
      // for imports we auto-suffix to mirror the web's behavior.
      let finalName = name;
      const existing = STATE.chainsList.map((c) => c.chainName.toLowerCase());
      if (existing.includes(finalName.toLowerCase())) {
        if (pickedFile) {
          let counter = 1;
          while (existing.includes(`${finalName}_${counter}`.toLowerCase())) counter++;
          finalName = `${finalName}_${counter}`;
          toast(`Name collision — importing as "${finalName}".`, 'success');
        } else {
          toast('A chain with that name already exists.', 'error');
          return;
        }
      }

      submitBtn.disabled = true;
      try {
        await api.createScopedChain(STATE.scope, finalName, description);
        if (pickedFile) {
          const text = await pickedFile.text();
          const steps = JSON.parse(text);
          if (!Array.isArray(steps)) throw new Error('JSON must be an array of steps.');
          if (isSharedScope()) {
            const refreshed = await api.listScopedChains(STATE.scope);
            const createdForImport = refreshed.find((c) => c.chainName === finalName);
            if (!createdForImport) throw new Error('Created chain was not found for import.');
            await api.replaceScopedChainSteps(STATE.scope, createdForImport.id, steps);
          } else {
            await api.importChain(finalName, steps);
          }
        }
        await loadChainsList();
        const created = STATE.chainsList.find((c) => c.chainName === finalName);
        if (created) {
          STATE.activeChainId = created.id;
          await loadActiveChain();
        }
        renderList();
        renderEditor();
        close();
        toast(pickedFile
          ? `Imported "${finalName}".`
          : `Chain "${finalName}" created.`, 'success');
      } catch (err) {
        toast(`Failed: ${errMsg(err)}`, 'error');
        submitBtn.disabled = false;
      }
    });
  }

  async function handleRenameChainBlur(e) {
    const newName = e.target.value.trim();
    if (!STATE.activeChain) return;
    if (!newName) {
      e.target.value = STATE.activeChain.chainName;
      return;
    }
    if (newName === STATE.activeChain.chainName) return;
    if (STATE.chainsList.some((c) =>
      c.id !== STATE.activeChainId
      && c.chainName.toLowerCase() === newName.toLowerCase())) {
      toast('A chain with that name already exists.', 'error');
      e.target.value = STATE.activeChain.chainName;
      return;
    }
    try {
      // PUT /v1/chain/{id} accepts both {new_name, description}; pass the
      // current description through so a rename doesn't clobber it.
      await api.updateScopedChain(STATE.scope, STATE.activeChainId, {
        name: newName,
        description: STATE.activeChain.description || '',
      });
      STATE.activeChain.chainName = newName;
      await loadChainsList();
      renderList();
      toast('Chain renamed.', 'success');
    } catch (err) {
      toast('Failed to rename: ' + errMsg(err), 'error');
      e.target.value = STATE.activeChain.chainName;
    }
  }

  async function handleDescriptionBlur(e) {
    const newDesc = e.target.value;
    if (!STATE.activeChain) return;
    if (newDesc === STATE.activeChain.description) return;
    try {
      // The PUT endpoint takes both fields, so we send the current name
      // alongside the new description to update only the description.
      await api.updateScopedChain(STATE.scope, STATE.activeChainId, {
        name: STATE.activeChain.chainName,
        description: newDesc,
      });
      STATE.activeChain.description = newDesc;
      const idx = STATE.chainsList.findIndex((c) => c.id === STATE.activeChainId);
      if (idx >= 0) STATE.chainsList[idx].description = newDesc;
      renderList();
    } catch (err) {
      toast('Failed to save description: ' + errMsg(err), 'error');
      e.target.value = STATE.activeChain.description || '';
    }
  }

  async function handleDeleteChain() {
    if (!STATE.activeChain) return;
    const ok = window.confirm(`Delete chain "${STATE.activeChain.chainName}"? This cannot be undone.`);
    if (!ok) return;
    try {
      await api.deleteScopedChain(STATE.scope, STATE.activeChainId);
      STATE.activeChainId = null;
      STATE.activeChain = null;
      STATE.dirty.clear();
      await loadChainsList();
      renderList();
      renderEditor();
      toast('Chain deleted.', 'success');
    } catch (err) {
      toast('Failed to delete: ' + errMsg(err), 'error');
    }
  }

  async function handleAddStep(stepNumber) {
    if (!STATE.activeChain) return;
    // Default agent: the user's currently-selected agent in the topbar.
    let s = null;
    try { s = await api.getSettings(); } catch (_) {}
    const defaultAgentId = (s && s.agent_id) || (STATE.agents[0] && STATE.agents[0].id) || '';
    if (!defaultAgentId) {
      toast('No agents available — pick an agent in the topbar first.', 'error');
      return;
    }
    try {
      const defaultAgent = STATE.agents.find((a) => a.id === defaultAgentId) || STATE.agents[0] || null;
      await api.addScopedChainStep(STATE.scope, STATE.activeChainId, stepNumber, defaultAgentId, 'Prompt', {
        prompt_name: '',
        prompt_category: 'Default',
      }, defaultAgent ? defaultAgent.name : '');
      await loadActiveChain();
      // Auto-expand the freshly-added step so the user can start editing it.
      STATE.expandedSteps.add(stepNumber);
      renderEditor();
      toast(`Step ${stepNumber} added.`, 'success');
    } catch (err) {
      toast('Failed to add step: ' + errMsg(err), 'error');
    }
  }

  async function handleDeleteStep(stepNumber) {
    if (!STATE.activeChain) return;
    const ok = window.confirm(`Delete step ${stepNumber}?`);
    if (!ok) return;
    try {
      if (isSharedScope()) {
        const steps = (STATE.activeChain.steps || [])
          .filter((s) => s.step !== stepNumber)
          .map((s, idx) => Object.assign({}, s, { step: idx + 1 }));
        await api.replaceScopedChainSteps(STATE.scope, STATE.activeChainId, steps);
      } else {
        await api.deleteChainStep(STATE.activeChainId, stepNumber);
      }
      STATE.dirty.delete(stepNumber);
      await loadActiveChain();
      renderEditor();
      toast(`Step ${stepNumber} deleted.`, 'success');
    } catch (err) {
      toast('Failed to delete step: ' + errMsg(err), 'error');
    }
  }

  async function handleMoveStep(stepNum, direction) {
    if (!STATE.activeChain) return;
    const target = direction === 'up' ? stepNum - 1 : stepNum + 1;
    if (target < 1 || target > (STATE.activeChain.steps || []).length) return;
    try {
      if (isSharedScope()) {
        const steps = (STATE.activeChain.steps || []).slice();
        const currentIndex = steps.findIndex((s) => s.step === stepNum);
        const targetIndex = steps.findIndex((s) => s.step === target);
        if (currentIndex < 0 || targetIndex < 0) return;
        [steps[currentIndex], steps[targetIndex]] = [steps[targetIndex], steps[currentIndex]];
        const renumbered = steps.map((s, idx) => Object.assign({}, s, { step: idx + 1 }));
        await api.replaceScopedChainSteps(STATE.scope, STATE.activeChainId, renumbered);
      } else {
        await api.moveChainStep(STATE.activeChainId, stepNum, target);
      }
      await loadActiveChain();
      renderEditor();
    } catch (err) {
      toast('Failed to move step: ' + errMsg(err), 'error');
    }
  }

  async function handleSaveStep(stepNumber) {
    if (!STATE.activeChain) return;
    const dirty = STATE.dirty.get(stepNumber);
    if (!dirty) return;
    if (!dirty.agent_id && !dirty._agent_name) {
      toast('Pick an agent for this step before saving.', 'error');
      return;
    }
    const finalPrompt = coercePromptValues(dirty.prompt, dirty.prompt_type);
    try {
      if (isSharedScope()) {
        const steps = (STATE.activeChain.steps || []).map((s) => (
          s.step === stepNumber
            ? Object.assign({}, s, {
              agent_name: dirty._agent_name || s.agent_name || '',
              prompt_type: dirty.prompt_type,
              prompt: finalPrompt,
            })
            : s
        ));
        await api.replaceScopedChainSteps(STATE.scope, STATE.activeChainId, steps);
      } else {
        await api.updateChainStep(
          STATE.activeChainId,
          stepNumber,
          dirty.agent_id,
          dirty.prompt_type,
          finalPrompt,
        );
      }
      STATE.dirty.delete(stepNumber);
      await loadActiveChain();
      renderEditor();
      toast(`Step ${stepNumber} saved.`, 'success');
    } catch (err) {
      toast('Failed to save step: ' + errMsg(err), 'error');
    }
  }

  async function handleSaveAll() {
    if (!STATE.activeChain || STATE.dirty.size === 0) return;
    const entries = Array.from(STATE.dirty.entries());
    const failures = [];
    if (isSharedScope()) {
      const mergedSteps = (STATE.activeChain.steps || []).map((step) => {
        const dirty = STATE.dirty.get(step.step);
        if (!dirty) return step;
        if (!dirty.agent_id && !dirty._agent_name) {
          failures.push(step.step);
          return step;
        }
        return Object.assign({}, step, {
          agent_name: dirty._agent_name || step.agent_name || '',
          prompt_type: dirty.prompt_type,
          prompt: coercePromptValues(dirty.prompt, dirty.prompt_type),
        });
      });
      if (failures.length === 0) {
        try {
          await api.replaceScopedChainSteps(STATE.scope, STATE.activeChainId, mergedSteps);
          STATE.dirty.clear();
        } catch (err) {
          console.error('save scoped chain failed', err);
          failures.push('all');
        }
      }
    } else {
      for (const [stepNumber, dirty] of entries) {
        if (!dirty.agent_id) {
          failures.push(stepNumber);
          continue;
        }
        const finalPrompt = coercePromptValues(dirty.prompt, dirty.prompt_type);
        try {
          await api.updateChainStep(
            STATE.activeChainId,
            stepNumber,
            dirty.agent_id,
            dirty.prompt_type,
            finalPrompt,
          );
          STATE.dirty.delete(stepNumber);
        } catch (err) {
          console.error('save step failed', stepNumber, err);
          failures.push(stepNumber);
        }
      }
    }
    await loadActiveChain();
    renderEditor();
    if (failures.length === 0) {
      toast('All changes saved.', 'success');
    } else {
      toast(`Saved with ${failures.length} failure(s) on step(s): ${failures.join(', ')}.`, 'error');
    }
  }

  function coercePromptValues(prompt, type) {
    const out = {};
    Object.entries(prompt || {}).forEach(([k, v]) => {
      if (typeof v === 'string') {
        const trimmed = v.trim();
        if (trimmed === '' && !STRUCTURAL_ARGS.has(k)) return;
        if (/^true$/i.test(trimmed)) out[k] = true;
        else if (/^false$/i.test(trimmed)) out[k] = false;
        else if (trimmed !== '' && !isNaN(Number(trimmed))) out[k] = Number(trimmed);
        else out[k] = v;
      } else if (v != null) {
        out[k] = v;
      }
    });
    // Strip stale conditional fields that no longer apply.
    if (type !== 'Prompt') delete out.context;
    if (type !== 'Chain') delete out.user_input;
    return out;
  }

  // ── Run ───────────────────────────────────────────────────────────────

  async function handleRunChain() {
    if (!STATE.activeChain) return;
    if (STATE.dirty.size > 0) {
      const ok = window.confirm('You have unsaved changes that won’t be included in this run. Continue anyway?');
      if (!ok) return;
    }
    let chainArgs = [];
    try { chainArgs = await api.getChainArgs(STATE.activeChainId); } catch (_) {}
    openRunDialog(chainArgs);
  }

  function openRunDialog(argNames) {
    // Strip already-collected meta fields the run endpoint sets directly.
    const userArgs = (argNames || []).filter((a) =>
      a && a !== 'user_input' && !SYSTEM_INJECTED_ARGS.has(a)
    );

    const argInputs = {};
    const userInput = el('textarea', {
      class: 'cn-textarea',
      rows: 3,
      placeholder: 'What should the chain do? This becomes user_input.',
    });
    const fields = userArgs.map((name) => {
      const id = `cn-run-arg-${name}`;
      const inp = el('input', {
        id, class: 'cn-input', type: 'text',
        placeholder: `Enter ${name}`,
      });
      argInputs[name] = inp;
      return el('div', { class: 'cn-field' }, [
        el('label', { class: 'cn-field-label', for: id }, name),
        inp,
      ]);
    });

    const result = el('pre', { class: 'cn-run-result', hidden: true });

    const closeBtn = el('button', { class: 'cn-modal-close', html: '×', 'aria-label': 'Close' });
    const cancelBtn = btn('Close', { kind: 'secondary' });
    const runBtn = btn(
      el('span', { html: ICONS.play + '<span style="margin-left:6px">Run chain</span>' }),
      { kind: 'primary' }
    );

    const modal = el('div', { class: 'cn-modal-backdrop' }, [
      el('div', { class: 'cn-modal' }, [
        el('div', { class: 'cn-modal-header' }, [
          el('h3', { class: 'cn-modal-title' }, `Run "${STATE.activeChain.chainName}"`),
          closeBtn,
        ]),
        el('div', { class: 'cn-modal-body' }, [
          el('div', { class: 'cn-field' }, [
            el('label', { class: 'cn-field-label' }, 'User input'),
            userInput,
          ]),
          ...fields,
          result,
        ]),
        el('div', { class: 'cn-modal-footer' }, [cancelBtn, runBtn]),
      ]),
    ]);
    document.body.appendChild(modal);
    setTimeout(() => userInput.focus(), 30);

    function close() { if (modal.parentElement) modal.parentElement.removeChild(modal); }
    closeBtn.addEventListener('click', close);
    cancelBtn.addEventListener('click', close);
    modal.addEventListener('click', (e) => { if (e.target === modal) close(); });

    runBtn.addEventListener('click', async () => {
      const chainArgs = {};
      Object.entries(argInputs).forEach(([k, inp]) => {
        const v = inp.value;
        if (v != null && v !== '') chainArgs[k] = v;
      });
      runBtn.disabled = true;
      runBtn.textContent = 'Running…';
      result.hidden = false;
      result.textContent = 'Running chain… this can take a while for multi-step chains.';
      try {
        const out = await api.runChain(STATE.activeChainId, {
          user_input: userInput.value,
          chain_args: chainArgs,
          all_responses: false,
          from_step: 1,
        });
        let text;
        if (typeof out === 'string') text = out;
        else { try { text = JSON.stringify(out, null, 2); } catch (_) { text = String(out); } }
        result.textContent = text || '(empty response)';
      } catch (err) {
        result.textContent = 'Failed: ' + errMsg(err);
      } finally {
        runBtn.disabled = false;
        runBtn.innerHTML = '';
        runBtn.appendChild(el('span', { html: ICONS.play + '<span style="margin-left:6px">Run chain</span>' }));
      }
    });
  }

  // ── Import / export ───────────────────────────────────────────────────

  function handleExportChain() {
    if (!STATE.activeChain) return;
    const payload = {
      chainName: STATE.activeChain.chainName,
      description: STATE.activeChain.description || '',
      steps: STATE.activeChain.steps || [],
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${STATE.activeChain.chainName.replace(/[^a-z0-9_-]/gi, '_')}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function handleImportSteps() {
    if (!STATE.activeChain) return;
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'application/json,.json';
    input.addEventListener('change', async () => {
      const file = input.files && input.files[0];
      if (!file) return;
      try {
        const text = await file.text();
        const data = JSON.parse(text);
        let steps = Array.isArray(data) ? data
          : Array.isArray(data.steps) ? data.steps
          : null;
        if (!steps) {
          toast('JSON must be an array of steps or {steps: [...]}.', 'error');
          return;
        }
        const ok = window.confirm(
          `Replace the ${(STATE.activeChain.steps || []).length} step(s) in "${STATE.activeChain.chainName}" with ${steps.length} imported step(s)?`
        );
        if (!ok) return;
        if (isSharedScope()) {
          await api.replaceScopedChainSteps(STATE.scope, STATE.activeChainId, steps);
        } else {
          // The /v1/chain/import endpoint replaces the user chain's steps wholesale.
          await api.importChain(STATE.activeChain.chainName, steps);
        }
        await loadActiveChain();
        renderEditor();
        toast(`Imported ${steps.length} step(s).`, 'success');
      } catch (err) {
        toast('Import failed: ' + errMsg(err), 'error');
      }
    });
    input.click();
  }

  // ── Boot / mount ──────────────────────────────────────────────────────

  async function mount() {
    if (!STATE.mounted) {
      bindStaticControls();
      STATE.mounted = true;
    }
    if (STATE.booted) {
      // Re-mount on subsequent activations refreshes the list so newly-
      // added chains created from another window show up.
      await loadUserScopes();
      await loadChainsList();
      renderList();
      return;
    }
    STATE.booted = true;
    try {
      await loadUserScopes();
      await Promise.all([loadAgents(true), loadPrompts(true), loadChainsList()]);
      renderList();
      renderEditor();
    } catch (err) {
      toast('Failed to load chains: ' + errMsg(err), 'error');
    }
  }

  function bindStaticControls() {
    const search = $('#cn-search');
    if (search) {
      search.addEventListener('input', (e) => {
        STATE.listFilter = e.target.value;
        renderList();
      });
    }
    const newBtn = $('#cn-new-chain');
    if (newBtn) newBtn.addEventListener('click', handleCreateChain);

    // Prompt Library — surfaced in the always-visible main header so
    // users can reach it regardless of whether a chain is selected.
    // Routes through AgixtSidenav.setActiveView('prompts') so the
    // prompts pane is lazy-mounted on first activation.
    const openPromptsBtn = $('#cn-open-prompts');
    if (openPromptsBtn) openPromptsBtn.addEventListener('click', handleOpenPromptLibrary);

    document.querySelectorAll('#cn-scope-tabs [data-scope]').forEach((button) => {
      button.addEventListener('click', () => switchScope(button.dataset.scope || 'user'));
    });
    renderScopeTabs();

    // Collapse / re-expand the chain list panel. The chevron in the
    // list header tucks the panel away; clicking the thin strip on the
    // right edge brings it back. Open/closed state persists via
    // localStorage so it survives navigation between panes.
    const collapseBtn = $('#cn-list-collapse');
    if (collapseBtn) collapseBtn.addEventListener('click', () => setListOpen(false));
    const collapsedStrip = $('#cn-list-collapsed');
    if (collapsedStrip) collapsedStrip.addEventListener('click', () => setListOpen(true));
    // Stamp initial state on first mount.
    renderListVisibility();

    // Re-fetch agents whenever the topbar emits an agent-changed event —
    // the available agents (and therefore IDs we'd resolve from names)
    // depend on the user's current company. Also re-probes the chain-
    // as-ability state since it's anchored to the toolbar agent.
    const event = tauri && tauri.event;
    if (event && event.listen) {
      event.listen('agixt-agent-changed', async () => {
        try {
          await api.refreshSettings();
          await loadUserScopes();
          STATE.commandsByAgent.clear();
          STATE.argCache.clear();
          await loadAgents(true);
          if (STATE.activeChainId) {
            await refreshAbilityStatus();
            renderEditor();
          }
        } catch (e) { /* ignore */ }
      });
    }

    // The Prompts pane fires a window event whenever it creates,
    // renames, or deletes a prompt. The chains' Prompt-step dropdown
    // pulls from the same /v1/prompts list, so we refresh both the
    // prompts cache and (if a chain is open) the editor to surface
    // the change immediately — no need to reopen the pane.
    window.addEventListener('agixt-prompts-changed', async () => {
      try {
        STATE.argCache.clear();
        await loadPrompts(true);
        if (STATE.activeChainId) renderEditor();
      } catch (_) { /* ignore */ }
    });
  }

  window.AgixtChains = { mount };
})();

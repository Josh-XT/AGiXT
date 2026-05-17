/* User settings pane.
 *
 * Hosts the App / Account / Settings / Developer / Billing / Companies /
 * Teams sub-tabs that replace the legacy gear-button modal. Mirrors the
 * web app's /user/manage, /user/settings, /user/developer, /billing,
 * /companies, /team pages — but tuned for the desktop's tighter side
 * pane footprint and vanilla-JS host.
 *
 * Lifecycle:
 *  - app.js stamps `data-view="user-settings"` on the gear button and
 *    routes `setActiveView("user-settings")` to this module via
 *    AgentSettings-style mount(). The first activation lazy-loads each
 *    panel; subsequent activations refresh whichever tab is currently
 *    visible.
 *  - All AGiXT REST calls go through window.AgixtApi (extended with
 *    user/billing/companies/tokens helpers) so the JWT + base URL stay
 *    consistent across the Tauri and standalone hosts.
 *  - Desktop-only prefs (theme, sudo, allow-commands, voice, auto-update,
 *    desktop updater) live on the App tab and call into `window.AgixtApp`
 *    + the `invoke` Tauri commands.
 */
(function () {
  const tauri = window.__TAURI__;
  if (!tauri) return;
  const invoke = tauri.core.invoke;
  const api = window.AgixtApi;
  if (!api) {
    console.error('user-settings.js: AgixtApi unavailable');
    return;
  }

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  // ─── State ────────────────────────────────────────────────────────────
  let mounted = false;
  let activeTab = 'app';
  // Caches keyed by tab name so re-activating a tab doesn't re-fetch.
  // Each tab's renderer is responsible for invalidating its own cache.
  const initialized = {};
  const cache = {
    user: null,
    companies: null,
    tokens: null,
    tokenScopes: null,
    tokenAgents: null,
    tokenCompanies: null,
    billingEnabled: null,
    pricingConfig: null,
    autoTopup: null,
    planLimits: null,
    transactions: null,
    members: null,
    invitations: null,
    desktopSettings: null,
    sudoStatus: null,
    desktopUpdate: null,
    defaultRoles: null,
  };

  let toastTimer = null;
  function toast(message, kind) {
    const el = document.getElementById('us-toast');
    if (!el) return;
    el.textContent = message;
    el.className = 'us-toast' + (kind ? ' ' + kind : '');
    el.hidden = false;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, kind === 'error' ? 6000 : 3000);
  }

  function errMsg(err) {
    if (!err) return 'Unknown error';
    if (typeof err === 'string') return err;
    // Tauri IPC rejects with `{error: '...'}`, fetch failures with `{message}`,
    // FastAPI 4xx with `{detail}`. Cover all three before falling back to
    // String() which would emit "[object Object]" for plain objects.
    return err.error || err.detail || err.message || String(err);
  }

  // ─── Helpers ─────────────────────────────────────────────────────────

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
    const b = el('button', {
      type: 'button',
      class: cls.join(' '),
      onclick: opts.onclick,
      disabled: opts.disabled,
    }, label);
    return b;
  }

  function field(labelText, control, hint) {
    const wrap = el('label', { class: 'us-label' }, [
      el('span', { class: 'us-label-text' }, labelText),
      control,
      hint ? el('span', { class: 'us-hint' }, hint) : null,
    ]);
    return wrap;
  }

  function section(title, blurb, body, opts) {
    const cls = 'us-section' + (opts && opts.danger ? ' us-section-danger' : '');
    return el('section', { class: cls }, [
      title ? el('h2', { class: 'us-section-title' }, title) : null,
      blurb ? el('p', { class: 'us-section-blurb' }, blurb) : null,
      ...(Array.isArray(body) ? body : body ? [body] : []),
    ]);
  }

  function emptyState(text) { return el('div', { class: 'us-empty' }, text); }

  function badge(text, kind) {
    return el('span', { class: 'us-badge' + (kind ? ' ' + kind : '') }, text);
  }

  /** Open an overlay dialog. `opts` accepts `title`, `description`, `body`
   *  (a DOM node or array of nodes), `footer` (array of buttons), `wide`,
   *  and `onClose`. Returns a `{ close, root }` handle the caller can use
   *  to dismiss the dialog programmatically. Captures the previously-focused
   *  element on open and restores focus to it on every close path (button,
   *  Escape, backdrop click) so keyboard navigation isn't dropped. */
  function openModal(opts) {
    opts = opts || {};
    const previouslyFocused = document.activeElement;
    const header = el('div', { class: 'us-modal-header' }, [
      el('div', null, [
        el('h3', null, opts.title || ''),
        opts.description ? el('p', null, opts.description) : null,
      ].filter(Boolean)),
      el('button', { class: 'us-modal-close', type: 'button', 'aria-label': 'Close',
        onclick: () => close() }, '×'),
    ]);
    const bodyEl = el('div', { class: 'us-modal-body' });
    if (opts.body) {
      (Array.isArray(opts.body) ? opts.body : [opts.body]).forEach((n) => {
        if (n) bodyEl.appendChild(n);
      });
    }
    const footerChildren = (opts.footer || []).filter(Boolean);
    const footer = footerChildren.length
      ? el('div', { class: 'us-modal-footer' }, footerChildren)
      : null;
    const card = el('div', { class: 'us-modal-card' + (opts.wide ? ' wide' : '') }, [
      header, bodyEl, footer,
    ].filter(Boolean));
    const root = el('div', { class: 'us-modal-backdrop', role: 'dialog' }, [card]);

    let closed = false;
    function close() {
      if (closed) return;
      closed = true;
      if (root.parentElement) root.parentElement.removeChild(root);
      document.removeEventListener('keydown', onKey);
      // Restore focus *before* firing onClose so the caller's resolve()
      // path doesn't observe the focus already moved by browser defaults.
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

  /** Auto-focus the first focusable input/textarea in a freshly opened
   *  modal. Restoration of focus on close is handled inside `openModal`
   *  itself so every close path (button, Escape, backdrop) restores. */
  function setupModalFocus(handle, opts) {
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
    return handle;
  }

  /** Themed confirm replacement. Returns a Promise<boolean> — resolves
   *  true on confirm, false on cancel/escape/backdrop click. Use this
   *  instead of the native confirm() so dialogs match the app theme,
   *  honor focus management, and can show longer/styled messages. */
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
      const cancelBtn = btn(opts.cancelLabel || 'Cancel');
      const confirmBtn = btn(opts.confirmLabel || 'Confirm', {
        kind: opts.destructive ? 'danger' : 'primary',
      });
      cancelBtn.addEventListener('click', () => finish(false));
      confirmBtn.addEventListener('click', () => finish(true));
      const handle = openModal({
        title: opts.title || 'Confirm',
        description: opts.description || undefined,
        body: opts.message
          ? [el('p', { class: 'us-confirm-message' }, opts.message)]
          : [],
        footer: [cancelBtn, confirmBtn],
        onClose: () => finish(false),
      });
      setupModalFocus(handle, { focusSelector: opts.destructive
        ? 'button.btn-secondary'
        : 'button.btn-primary' });
    });
  }

  /** Map a thrown API error to a user-friendly message that calls out
   *  common failure modes — 402 (billing), 403 (no perms), 409 (already
   *  exists), 404 (not found). Falls back to `errMsg(err)` otherwise. */
  function friendlyError(err, context) {
    const status = err && err.status;
    const baseMsg = errMsg(err);
    const ctx = context ? ' ' + context : '';
    if (status === 402) {
      return 'User limit reached for this company. Upgrade your plan to add more users.';
    }
    if (status === 403) {
      return baseMsg && baseMsg !== 'HTTP 403'
        ? baseMsg
        : 'You don’t have permission to perform this action' + ctx + '.';
    }
    if (status === 409) {
      return baseMsg && baseMsg !== 'HTTP 409'
        ? baseMsg
        : 'That item already exists.';
    }
    if (status === 404) {
      return baseMsg && baseMsg !== 'HTTP 404'
        ? baseMsg
        : 'Not found.';
    }
    return baseMsg;
  }

  function copyToClipboard(text) {
    if (!text) return;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text);
        return;
      }
    } catch (_) { /* fall through */ }
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (_) {}
    document.body.removeChild(ta);
  }

  function buildInviteLink(invitationId, email) {
    if (!invitationId || invitationId === 'none') return null;
    const appUri = (cache.desktopSettings && cache.desktopSettings.app_url)
      || (cache.desktopSettings && cache.desktopSettings.server_url)
      || (window.location && window.location.origin)
      || '';
    const params = new URLSearchParams();
    params.set('invitation_id', invitationId);
    if (email) params.set('email', email);
    const base = String(appUri).replace(/\/+$/, '');
    return base + '/?' + params.toString();
  }

  function parseEmails(raw) {
    return String(raw || '')
      .split(/[\s,;]+/)
      .map((e) => e.trim().toLowerCase())
      .filter((e) => e && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e));
  }

  function openExternal(url) {
    if (!url) return;
    try {
      const op = tauri && tauri.opener;
      if (op && typeof op.openUrl === 'function') return op.openUrl(url);
      const sh = tauri && tauri.shell;
      if (sh && typeof sh.open === 'function') return sh.open(url);
    } catch (_) {}
    window.open(url, '_blank', 'noopener,noreferrer');
  }

  function formatDate(isoOrNull) {
    if (!isoOrNull) return '—';
    const d = new Date(isoOrNull);
    if (Number.isNaN(d.getTime())) return String(isoOrNull);
    return d.toLocaleString();
  }

  function formatTokens(n) {
    if (n == null) return '0';
    const num = Number(n) || 0;
    if (num >= 1e9) return (num / 1e9).toFixed(2) + 'B';
    if (num >= 1e6) return (num / 1e6).toFixed(2) + 'M';
    if (num >= 1e3) return (num / 1e3).toFixed(1) + 'k';
    return String(num);
  }

  function formatUsd(n) {
    if (n == null || Number.isNaN(Number(n))) return '$0.00';
    return '$' + Number(n).toFixed(2);
  }

  function isAdminLikeRole(roleId) {
    // Mirrors the web's resolveRoleId mapping. Roles 0–2 grant admin-level
    // surfaces (tenant admin, company admin) — anything else is rank-and-file.
    return typeof roleId === 'number' && roleId >= 0 && roleId <= 2;
  }

  function userCanAdminCompany(user, companyId) {
    if (!user || !user.companies) return false;
    const c = user.companies.find((x) => x.id === companyId);
    if (!c) return false;
    return isAdminLikeRole(c.role_id);
  }

  function userIsSuperAdmin(user) {
    if (!user || !Array.isArray(user.companies)) return false;
    return user.companies.some((company) =>
      company.role_id === 0 || company.role === 'super_admin');
  }

  function activeCompanyIdForUser(user, settings) {
    if (settings && settings.company_id) return settings.company_id;
    if (!user || !Array.isArray(user.companies) || !user.companies.length) return null;
    const primary = user.companies.find((company) => company.primary);
    return (primary || user.companies[0]).id || null;
  }

  function methodLabel(method) {
    const labels = {
      totp: 'Authenticator app',
      webauthn: 'Passkey',
      hardware_token: 'Hardware token',
      face: 'Face',
      voice: 'Voice',
      sms: 'SMS',
      email: 'Email',
      magic_link: 'Magic link',
      password: 'Password',
    };
    return labels[method] || method || 'Unknown method';
  }

  function shortId(value) {
    const text = String(value || '');
    return text.length > 22 ? text.slice(0, 12) + '…' + text.slice(-6) : text;
  }

  function replaceSectionBody(sectionEl, nodes) {
    Array.from(sectionEl.children).slice(2).forEach((child) => child.remove());
    (Array.isArray(nodes) ? nodes : [nodes]).forEach((node) => {
      if (node) sectionEl.appendChild(node);
    });
  }

  // Load helpers — return cached values to avoid re-hitting the server
  // on every tab switch. Each setter clears the relevant cache.
  async function loadUser(force) {
    if (!force && cache.user) return cache.user;
    cache.user = await api.getUser();
    return cache.user;
  }

  async function loadDesktopSettings(force) {
    if (!force && cache.desktopSettings) return cache.desktopSettings;
    cache.desktopSettings = await invoke('get_settings');
    return cache.desktopSettings;
  }

  // ─── Tab routing ──────────────────────────────────────────────────────

  const TAB_RENDERERS = {
    app: renderApp,
    glasses: renderGlasses,
    account: renderAccount,
    settings: renderSettings,
    developer: renderDeveloper,
    billing: renderBilling,
    companies: renderCompanies,
    teams: renderTeams,
    webhooks: renderWebhooks,
  };

  function setActiveTab(name) {
    if (!TAB_RENDERERS[name]) name = 'app';
    activeTab = name;
    $$('.us-tab').forEach((t) => {
      const on = t.dataset.usTab === name;
      t.classList.toggle('is-active', on);
      t.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    $$('.us-panel').forEach((p) => {
      const on = p.dataset.usPanel === name;
      p.classList.toggle('is-active', on);
      p.hidden = !on;
    });
    activatePanel(name);
  }

  function bindTabs() {
    $$('.us-tab').forEach((t) => {
      t.addEventListener('click', () => setActiveTab(t.dataset.usTab));
    });
  }

  function activatePanel(name) {
    const panel = document.querySelector(`.us-panel[data-us-panel="${name}"]`);
    if (!panel) return;
    const fn = TAB_RENDERERS[name];
    if (!fn) return;
    Promise.resolve(fn(panel)).catch((err) => {
      console.error('user-settings panel ' + name + ':', err);
      panel.innerHTML = '';
      panel.appendChild(section('Error', null, [
        el('p', { class: 'us-hint error' }, errMsg(err)),
        btn('Retry', { kind: 'primary', onclick: () => activatePanel(name) }),
      ]));
    });
    initialized[name] = true;
  }

  // ─── App tab — desktop-only prefs (was the old modal contents) ────────

  async function renderApp(panel) {
    panel.innerHTML = '';
    let settings = await loadDesktopSettings(true);
    const user = settings && settings.jwt ? await loadUser().catch(() => null) : null;

    // Identity card — who am I + log out.
    const identityRows = [
      el('div', { class: 'us-list-item' }, [
        el('div', { class: 'us-list-item-grow' }, [
          el('p', { class: 'us-list-item-title' }, settings.user_email || 'Not signed in'),
          el('p', { class: 'us-list-item-meta' }, settings.server_url || ''),
        ]),
        settings.jwt ? btn('Log out', { kind: 'danger', onclick: handleLogout }) : null,
      ]),
    ];
    if (settings.jwt && user && user.companies && user.companies.length) {
      const primary = user.companies.find((c) => c.primary) || user.companies[0];
      if (primary) {
        identityRows.push(el('p', { class: 'us-hint' },
          'Active company: ' + (primary.name || '—') + ' · role: ' + (primary.role || 'user')));
      }
    }
    panel.appendChild(section('Account', null, identityRows));

    // Theme.
    const themeSelect = el('select', { class: 'us-select' }, [
      el('option', { value: 'system' }, 'Match system'),
      el('option', { value: 'light' }, 'Light'),
      el('option', { value: 'gray' }, 'Dark'),
      el('option', { value: 'dark' }, 'Dark Blue'),
    ]);
    themeSelect.value = settings.theme || 'system';
    themeSelect.addEventListener('change', async () => {
      const value = themeSelect.value;
      try {
        await invoke('save_settings', { settings: { ...settings, theme: value } });
        cache.desktopSettings = { ...settings, theme: value };
        // Apply live so the user sees the change immediately. The bootstrap
        // script in index.html mirrors this on next launch via localStorage.
        const resolved = value === 'system'
          ? (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'gray' : 'light')
          : value;
        document.documentElement.setAttribute('data-theme', resolved);
        try { window.localStorage.setItem('agixt.theme', value); } catch (_) {}
        window.dispatchEvent(new CustomEvent('agixt-theme-changed', {
          detail: { theme: value, resolved },
        }));
        toast('Theme saved', 'success');
      } catch (err) {
        toast('Failed to save theme: ' + errMsg(err), 'error');
      }
    });
    panel.appendChild(section('Theme', '"Match system" follows your OS and updates live when you switch.',
      [themeSelect]));

    // Behavior toggles (allow-commands, voice).
    const allowCommands = el('input', { type: 'checkbox', dataset: { usTest: 'allow-commands' } });
    allowCommands.checked = !!settings.allow_client_commands;
    const voiceToggle = el('input', { type: 'checkbox', dataset: { usTest: 'voice-toggle' } });
    voiceToggle.checked = !!settings.voice_enabled;
    const autoUpdate = el('input', { type: 'checkbox', dataset: { usTest: 'auto-update' } });
    autoUpdate.checked = !!settings.desktop_auto_update;
    const saveBehaviorBtn = btn('Save', { kind: 'primary', onclick: async () => {
      try {
        const patch = {
          ...settings,
          allow_client_commands: allowCommands.checked,
          voice_enabled: voiceToggle.checked,
          desktop_auto_update: autoUpdate.checked,
        };
        const next = await invoke('save_settings', { settings: patch });
        cache.desktopSettings = next;
        // Sync the cached settings reference inside app.js so its
        // scheduleDesktopAutoUpdateCheck sees the new flag, then re-arm
        // the auto-update timer if the user just turned the toggle on.
        const upd = window.AgixtDesktopUpdates;
        if (upd) {
          if (typeof upd.syncSettings === 'function') upd.syncSettings(next);
          if (typeof upd.scheduleAutoCheck === 'function' && next.desktop_auto_update) {
            upd.scheduleAutoCheck(400);
          }
        }
        toast('Saved', 'success');
        renderSudoStatus();
      } catch (err) { toast(errMsg(err), 'error'); }
    } });
    saveBehaviorBtn.dataset.usTest = 'save-behavior';
    panel.appendChild(section('Behavior', null, [
      el('label', { class: 'us-check' }, [allowCommands,
        el('span', null, 'Allow this agent to control my desktop (screenshot, click, type, files)')]),
      el('label', { class: 'us-check' }, [voiceToggle,
        el('span', null, 'Auto-play voice replies when available')]),
      el('label', { class: 'us-check' }, [autoUpdate,
        el('span', null, 'Automatically install AGiXT Desktop updates when available')]),
      el('div', { class: 'us-section-row end' }, [saveBehaviorBtn]),
    ]));

    // Desktop updates.
    const updateStatus = el('span', {
      class: 'us-status-line',
      dataset: { usTest: 'desktop-update-status' },
    }, 'Not checked.');
    const checkUpdateBtn = btn('Check now', { onclick: () => doDesktopUpdateCheck(updateStatus, installUpdateBtn) });
    checkUpdateBtn.dataset.usTest = 'desktop-update-check';
    const installUpdateBtn = btn('Install update', { kind: 'primary', onclick: () => doDesktopUpdateInstall(updateStatus, installUpdateBtn) });
    installUpdateBtn.dataset.usTest = 'desktop-update-install';
    installUpdateBtn.hidden = true;
    panel.appendChild(section('Desktop app updates',
      'Linux system installs use the remembered Privileged Commands sudo password to install the downloaded .deb.',
      [
        el('div', { class: 'us-section-row' }, [checkUpdateBtn, installUpdateBtn]),
        updateStatus,
      ]));

    // Sudo session.
    const sudoPasswordInput = el('input', {
      type: 'password',
      class: 'us-input',
      placeholder: 'Sudo password',
      autocomplete: 'current-password',
      dataset: { usTest: 'sudo-password' },
    });
    const sudoStatus = el('span', {
      class: 'us-status-line',
      dataset: { usTest: 'sudo-status' },
    }, 'Not checked.');
    const sudoAuthBtn = btn('Authenticate', { kind: 'primary', onclick: async () => {
      // Inline closure — see usTest below for testability.
      const pwd = sudoPasswordInput.value;
      if (!pwd) { sudoStatus.textContent = 'Enter your sudo password.'; sudoStatus.className = 'us-status-line error'; return; }
      sudoStatus.textContent = 'Authenticating…'; sudoStatus.className = 'us-status-line';
      try {
        await invoke('sudo_auth', { password: pwd });
        sudoPasswordInput.value = '';
        sudoStatus.textContent = 'Authenticated and remembered.'; sudoStatus.className = 'us-status-line success';
        // If the desktop updater previously failed with SUDO_AUTH_REQUIRED,
        // retry now that the password is cached.
        if (pendingInstallRetry) {
          pendingInstallRetry = false;
          const updateStatusEl = document.querySelector('[data-us-test="desktop-update-status"]');
          const installBtnEl = document.querySelector('[data-us-test="desktop-update-install"]');
          if (updateStatusEl && installBtnEl) {
            installBtnEl.hidden = false;
            doDesktopUpdateInstall(updateStatusEl, installBtnEl);
          }
        }
      } catch (err) {
        sudoStatus.textContent = errMsg(err); sudoStatus.className = 'us-status-line error';
      }
    } });
    sudoAuthBtn.dataset.usTest = 'sudo-auth';
    sudoPasswordInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); sudoAuthBtn.click(); }
    });
    const sudoClearBtn = btn('Forget sudo password', { onclick: async () => {
      sudoStatus.textContent = 'Forgetting…';
      try {
        await invoke('sudo_clear');
        sudoPasswordInput.value = '';
        sudoStatus.textContent = 'Forgotten.';
        sudoStatus.className = 'us-status-line';
      } catch (err) {
        sudoStatus.textContent = errMsg(err); sudoStatus.className = 'us-status-line error';
      }
    } });
    panel.appendChild(section('Privileged commands',
      'Saved in your operating system credential store and used only for AGiXT Desktop sudo commands.',
      [
        el('div', { class: 'us-section-row' }, [sudoPasswordInput, sudoAuthBtn]),
        el('div', { class: 'us-section-row between' }, [sudoClearBtn, sudoStatus]),
      ]));

    function renderSudoStatus() {
      if (!cache.desktopSettings || !cache.desktopSettings.allow_client_commands) {
        sudoStatus.textContent = 'Client commands disabled.'; sudoStatus.className = 'us-status-line error';
        return;
      }
      sudoStatus.textContent = 'Checking…'; sudoStatus.className = 'us-status-line';
      invoke('sudo_status').then((result) => {
        if (result && result.authenticated) {
          sudoStatus.textContent = result.remembered ? 'Authenticated and remembered.' : 'Authenticated for this session.';
          sudoStatus.className = 'us-status-line success';
        } else if (result && result.remembered) {
          sudoStatus.textContent = 'Remembered password needs re-authentication.';
          sudoStatus.className = 'us-status-line error';
        } else {
          sudoStatus.textContent = 'Needs authentication.';
          sudoStatus.className = 'us-status-line';
        }
      }).catch((err) => {
        if (/client commands are disabled/i.test(errMsg(err))) {
          sudoStatus.textContent = 'Client commands disabled.'; sudoStatus.className = 'us-status-line error';
        } else {
          sudoStatus.textContent = 'Needs authentication.'; sudoStatus.className = 'us-status-line';
        }
      });
    }
    renderSudoStatus();
    doDesktopUpdateCheck(updateStatus, installUpdateBtn);
  }

  async function renderGlasses(panel) {
    panel.innerHTML = '';
    let settings = await loadDesktopSettings(true);
    let status = null;

    const statusText = el('span', {
      class: 'us-status-line',
      dataset: { usTest: 'g1-status' },
    }, 'Checking...');
    const deviceList = el('div', {
      class: 'us-row-list',
      dataset: { usTest: 'g1-devices' },
    });

    function batteryText(info) {
      if (!info) return 'Battery unknown';
      const charging = info.is_charging ? ' charging' : '';
      return `${info.percentage}%${charging}`;
    }

    function renderStatus(next) {
      status = next || status;
      deviceList.innerHTML = '';
      if (!status) {
        statusText.textContent = 'Status unavailable.';
        statusText.className = 'us-status-line error';
        return;
      }
      if (!status.supported) {
        statusText.textContent = status.last_error || 'G1 is not supported on this platform.';
        statusText.className = 'us-status-line error';
      } else if (status.scanning) {
        statusText.textContent = 'Scanning for glasses...';
        statusText.className = 'us-status-line';
      } else if (status.connected) {
        statusText.textContent = status.last_event || 'Connected.';
        statusText.className = 'us-status-line success';
      } else {
        statusText.textContent = status.last_error || status.last_event || 'Not connected.';
        statusText.className = 'us-status-line';
      }

      [
        { label: 'Left', device: status.left, battery: status.battery && status.battery.left },
        { label: 'Right', device: status.right, battery: status.battery && status.battery.right },
      ].forEach((entry) => {
        const connected = entry.device && entry.device.connected;
        deviceList.appendChild(el('div', { class: 'us-list-item' }, [
          el('div', { class: 'us-list-item-grow' }, [
            el('p', { class: 'us-list-item-title' },
              `${entry.label}: ${entry.device ? entry.device.name : 'Not paired'}`),
            el('p', { class: 'us-list-item-meta' },
              entry.device ? `${entry.device.id} - ${batteryText(entry.battery)}` : 'No saved device connected'),
          ]),
          badge(connected ? 'Connected' : 'Offline', connected ? 'success' : ''),
        ]));
      });
    }

    async function refresh() {
      try {
        const next = window.AgixtG1 && typeof window.AgixtG1.refreshStatus === 'function'
          ? await window.AgixtG1.refreshStatus()
          : await invoke('g1_status');
        renderStatus(next);
        return next;
      } catch (err) {
        statusText.textContent = errMsg(err);
        statusText.className = 'us-status-line error';
        return null;
      }
    }

    async function runStatusCommand(label, command) {
      statusText.textContent = label + '...';
      statusText.className = 'us-status-line';
      try {
        const next = await command();
        renderStatus(next);
        if (/connect/i.test(label)) settings = await loadDesktopSettings(true).catch(() => settings);
        toast(label + ' complete', 'success');
        return next;
      } catch (err) {
        statusText.textContent = errMsg(err);
        statusText.className = 'us-status-line error';
        toast(errMsg(err), 'error');
        return null;
      }
    }

    const connectBtn = btn('Connect', {
      kind: 'primary',
      onclick: () => runStatusCommand('Connect', () => (
        window.AgixtG1 ? window.AgixtG1.scanAndConnect() : invoke('g1_scan_and_connect')
      )),
    });
    connectBtn.dataset.usTest = 'g1-connect';
    const reconnectBtn = btn('Reconnect saved', {
      onclick: () => runStatusCommand('Reconnect saved', () => (
        window.AgixtG1 ? window.AgixtG1.reconnectSaved() : invoke('g1_reconnect_saved')
      )),
    });
    reconnectBtn.dataset.usTest = 'g1-reconnect';
    const disconnectBtn = btn('Disconnect', {
      onclick: () => runStatusCommand('Disconnect', () => (
        window.AgixtG1 ? window.AgixtG1.disconnect() : invoke('g1_disconnect')
      )),
    });
    disconnectBtn.dataset.usTest = 'g1-disconnect';
    const syncBtn = btn('Sync now', {
      onclick: () => runStatusCommand('Sync now', () => (
        window.AgixtG1 ? window.AgixtG1.sync() : invoke('g1_sync')
      )),
    });
    syncBtn.dataset.usTest = 'g1-sync';
    const batteryBtn = btn('Battery', {
      onclick: () => runStatusCommand('Battery', () => (
        window.AgixtG1 ? window.AgixtG1.requestBattery() : invoke('g1_request_battery')
      )),
    });
    batteryBtn.dataset.usTest = 'g1-battery';

    panel.appendChild(section('Even Realities G1', null, [
      statusText,
      deviceList,
      el('div', { class: 'us-section-row' }, [connectBtn, reconnectBtn, disconnectBtn, syncBtn, batteryBtn]),
    ]));

    const enabled = el('input', { type: 'checkbox', dataset: { usTest: 'g1-enabled' } });
    enabled.checked = !!settings.g1_enabled;
    const displayEnabled = el('input', { type: 'checkbox', dataset: { usTest: 'g1-display-enabled' } });
    displayEnabled.checked = settings.g1_display_enabled !== false;
    const showAi = el('input', { type: 'checkbox', dataset: { usTest: 'g1-show-ai' } });
    showAi.checked = settings.g1_show_ai_responses !== false;
    const forwardNotifications = el('input', { type: 'checkbox', dataset: { usTest: 'g1-forward-notifications' } });
    forwardNotifications.checked = settings.g1_notification_forwarding !== false;
    const autoConnect = el('input', { type: 'checkbox', dataset: { usTest: 'g1-auto-connect' } });
    autoConnect.checked = settings.g1_auto_connect !== false;

    panel.appendChild(section('Behavior', null, [
      el('label', { class: 'us-check' }, [enabled, el('span', null, 'Enable G1 glasses integration')]),
      el('label', { class: 'us-check' }, [displayEnabled, el('span', null, 'Show content on the glasses display')]),
      el('label', { class: 'us-check' }, [showAi, el('span', null, 'Stream assistant responses to the glasses')]),
      el('label', { class: 'us-check' }, [forwardNotifications, el('span', null, 'Forward AGiXT notifications')]),
      el('label', { class: 'us-check' }, [autoConnect, el('span', null, 'Reconnect to saved glasses on launch')]),
    ]));

    function selectOption(value, label) {
      return el('option', { value }, label);
    }
    const timeFormat = el('select', { class: 'us-select' }, [
      selectOption('12h', '12-hour'),
      selectOption('24h', '24-hour'),
    ]);
    timeFormat.value = settings.g1_time_format || '12h';
    const tempUnit = el('select', { class: 'us-select' }, [
      selectOption('fahrenheit', 'Fahrenheit'),
      selectOption('celsius', 'Celsius'),
    ]);
    tempUnit.value = settings.g1_temperature_unit || 'fahrenheit';
    const dashboardLayout = el('select', { class: 'us-select' }, [
      selectOption('dual', 'Dual'),
      selectOption('full', 'Full'),
      selectOption('minimal', 'Minimal'),
    ]);
    dashboardLayout.value = settings.g1_dashboard_layout || 'dual';
    const weatherLat = el('input', {
      class: 'us-input',
      type: 'number',
      step: '0.000001',
      placeholder: 'Latitude',
      value: settings.g1_weather_latitude == null ? '' : String(settings.g1_weather_latitude),
    });
    const weatherLon = el('input', {
      class: 'us-input',
      type: 'number',
      step: '0.000001',
      placeholder: 'Longitude',
      value: settings.g1_weather_longitude == null ? '' : String(settings.g1_weather_longitude),
    });

    panel.appendChild(section('Dashboard', null, [
      el('div', { class: 'us-grid-2' }, [
        field('Time Format', timeFormat),
        field('Temperature', tempUnit),
      ]),
      field('Layout', dashboardLayout),
      el('div', { class: 'us-grid-2' }, [
        field('Weather Latitude', weatherLat, 'Leave blank to use the fallback dashboard weather.'),
        field('Weather Longitude', weatherLon),
      ]),
    ]));

    function rangeInput(value, min, max) {
      return el('input', {
        class: 'us-range',
        type: 'range',
        min: String(min),
        max: String(max),
        value: String(value),
      });
    }
    function rangeField(labelText, input, suffix) {
      const value = el('span', { class: 'us-status-line' }, `${input.value}${suffix || ''}`);
      input.addEventListener('input', () => { value.textContent = `${input.value}${suffix || ''}`; });
      return el('label', { class: 'us-label' }, [
        el('span', { class: 'us-label-text' }, labelText),
        el('div', { class: 'us-range-row' }, [input, value]),
      ]);
    }

    const brightness = rangeInput(settings.g1_brightness == null ? 28 : settings.g1_brightness, 0, 42);
    const autoBrightness = el('input', { type: 'checkbox' });
    autoBrightness.checked = settings.g1_auto_brightness !== false;
    const headupAngle = rangeInput(settings.g1_headup_angle == null ? 20 : settings.g1_headup_angle, 0, 60);
    const wearDetection = el('input', { type: 'checkbox' });
    wearDetection.checked = settings.g1_wear_detection !== false;
    const displayHeight = rangeInput(settings.g1_display_height == null ? 0 : settings.g1_display_height, 0, 8);
    const displayDepth = rangeInput(settings.g1_display_depth == null ? 5 : settings.g1_display_depth, 1, 9);

    panel.appendChild(section('Display Fit', null, [
      rangeField('Brightness', brightness),
      el('label', { class: 'us-check' }, [autoBrightness, el('span', null, 'Auto brightness')]),
      rangeField('Head-up Angle', headupAngle, ' deg'),
      el('label', { class: 'us-check' }, [wearDetection, el('span', null, 'Wear detection')]),
      el('div', { class: 'us-grid-2' }, [
        rangeField('Display Height', displayHeight),
        rangeField('Display Depth', displayDepth),
      ]),
    ]));

    const testText = el('textarea', {
      class: 'us-textarea',
      rows: 4,
      dataset: { usTest: 'g1-test-text' },
    }, 'AGiXT is connected to your Even Realities G1 glasses.');
    const sendTestBtn = btn('Send test text', {
      onclick: () => runStatusCommand('Send test text', () => invoke('g1_send_text', {
        text: testText.value,
        streaming: false,
        delayMs: 600,
      })),
    });
    sendTestBtn.dataset.usTest = 'g1-send-test';
    const clearBtn = btn('Clear display', {
      onclick: () => runStatusCommand('Clear display', () => (
        window.AgixtG1 ? window.AgixtG1.clearDisplay() : invoke('g1_clear_display')
      )),
    });
    clearBtn.dataset.usTest = 'g1-clear';

    function numberOrNull(input) {
      const raw = String(input.value || '').trim();
      if (!raw) return null;
      const value = Number(raw);
      return Number.isFinite(value) ? value : null;
    }

    function settingsPatch() {
      return {
        ...settings,
        g1_enabled: enabled.checked,
        g1_display_enabled: displayEnabled.checked,
        g1_show_ai_responses: showAi.checked,
        g1_notification_forwarding: forwardNotifications.checked,
        g1_auto_connect: autoConnect.checked,
        g1_time_format: timeFormat.value,
        g1_temperature_unit: tempUnit.value,
        g1_dashboard_layout: dashboardLayout.value,
        g1_weather_latitude: numberOrNull(weatherLat),
        g1_weather_longitude: numberOrNull(weatherLon),
        g1_brightness: Number(brightness.value),
        g1_auto_brightness: autoBrightness.checked,
        g1_headup_angle: Number(headupAngle.value),
        g1_wear_detection: wearDetection.checked,
        g1_display_height: Number(displayHeight.value),
        g1_display_depth: Number(displayDepth.value),
      };
    }

    async function saveGlassesSettings({ syncNow }) {
      try {
        const next = await invoke('save_settings', { settings: settingsPatch() });
        settings = next;
        cache.desktopSettings = next;
        if (window.AgixtG1 && typeof window.AgixtG1.syncSettings === 'function') {
          window.AgixtG1.syncSettings(next);
        }
        window.dispatchEvent(new CustomEvent('agixt-g1-settings-saved', { detail: { settings: next } }));
        toast('Glasses settings saved', 'success');
        if (syncNow && status && status.connected) {
          await runStatusCommand('Sync now', () => (
            window.AgixtG1 ? window.AgixtG1.sync() : invoke('g1_sync')
          ));
        }
      } catch (err) {
        toast(errMsg(err), 'error');
      }
    }

    const saveBtn = btn('Save', {
      kind: 'primary',
      onclick: () => saveGlassesSettings({ syncNow: false }),
    });
    saveBtn.dataset.usTest = 'g1-save';
    const saveSyncBtn = btn('Save and sync', {
      onclick: () => saveGlassesSettings({ syncNow: true }),
    });
    saveSyncBtn.dataset.usTest = 'g1-save-sync';
    const applyDisplayBtn = btn('Apply display', {
      onclick: async () => {
        try {
          const next = await invoke('save_settings', { settings: settingsPatch() });
          settings = next;
          cache.desktopSettings = next;
          if (window.AgixtG1 && typeof window.AgixtG1.syncSettings === 'function') {
            window.AgixtG1.syncSettings(next);
          }
          window.dispatchEvent(new CustomEvent('agixt-g1-settings-saved', { detail: { settings: next } }));
          if (window.AgixtG1 && typeof window.AgixtG1.applyDisplaySettings === 'function') {
            await window.AgixtG1.applyDisplaySettings(next);
          } else {
            await invoke('g1_set_brightness', { level: Number(brightness.value), auto: autoBrightness.checked });
            await invoke('g1_set_headup_angle', { angle: Number(headupAngle.value) });
            await invoke('g1_set_wear_detection', { enabled: wearDetection.checked });
            await invoke('g1_set_display_position', {
              input: { height: Number(displayHeight.value), depth: Number(displayDepth.value) },
            });
            await invoke('g1_set_silent_mode', { enabled: !displayEnabled.checked });
          }
          await refresh();
          toast('Display settings applied', 'success');
        } catch (err) {
          toast(errMsg(err), 'error');
        }
      },
    });
    applyDisplayBtn.dataset.usTest = 'g1-apply-display';

    panel.appendChild(section('Test and Save', null, [
      testText,
      el('div', { class: 'us-section-row between' }, [
        el('div', { class: 'us-section-row' }, [sendTestBtn, clearBtn]),
        el('div', { class: 'us-section-row' }, [applyDisplayBtn, saveSyncBtn, saveBtn]),
      ]),
    ]));

    if (panel._g1StatusHandler) {
      window.removeEventListener('agixt-g1-status', panel._g1StatusHandler);
    }
    panel._g1StatusHandler = (ev) => renderStatus(ev.detail);
    window.addEventListener('agixt-g1-status', panel._g1StatusHandler);
    renderStatus(window.AgixtG1 && window.AgixtG1.getStatus ? window.AgixtG1.getStatus() : null);
    await refresh();
  }

  async function doDesktopUpdateCheck(statusEl, installBtn) {
    statusEl.textContent = 'Checking…'; statusEl.className = 'us-status-line';
    try {
      const status = await invoke('desktop_update_check');
      cache.desktopUpdate = status;
      const current = status.current_build_id || status.app_version || 'current';
      const latest = status.latest_build_id || 'unknown';
      if (!status.update_available) {
        statusEl.textContent = `Up to date (${current}).`;
        statusEl.className = 'us-status-line success';
        installBtn.hidden = true;
      } else if (status.ready) {
        statusEl.textContent = `Update ready: ${current} → ${latest}.`;
        statusEl.className = 'us-status-line';
        installBtn.hidden = false;
      } else {
        statusEl.textContent = `Update ${latest} is still building.`;
        statusEl.className = 'us-status-line';
        installBtn.hidden = true;
      }
    } catch (err) {
      statusEl.textContent = errMsg(err); statusEl.className = 'us-status-line error';
      installBtn.hidden = true;
    }
  }

  // Set when an install attempt fails with SUDO_AUTH_REQUIRED so a
  // subsequent sudo-auth click can retry the install automatically.
  let pendingInstallRetry = false;

  async function doDesktopUpdateInstall(statusEl, installBtn) {
    statusEl.textContent = 'Installing update…';
    statusEl.className = 'us-status-line';
    installBtn.disabled = true;
    installBtn.hidden = true;
    const checkBtn = document.querySelector('[data-us-test="desktop-update-check"]');
    if (checkBtn) checkBtn.hidden = true;
    try {
      const result = await invoke('desktop_update_install');
      statusEl.textContent = result.message || 'Update installed.';
      statusEl.className = 'us-status-line ' + (result.installed ? 'success' : '');
      if (!result.installed) installBtn.hidden = false;
    } catch (err) {
      const msg = errMsg(err);
      if (/SUDO_AUTH_REQUIRED|sudo.*password.*required|authenticate.*Privileged Commands/i.test(msg)) {
        pendingInstallRetry = true;
        statusEl.textContent = 'Authenticate Privileged Commands to install this update.';
        statusEl.className = 'us-status-line error';
        const sudoInput = document.querySelector('[data-us-test="sudo-password"]');
        if (sudoInput) {
          // Match the legacy modal's behaviour: focus the field so the
          // user can type their password without hunting for it.
          window.setTimeout(() => { try { sudoInput.focus(); } catch (_) {} }, 0);
        }
      } else {
        statusEl.textContent = msg; statusEl.className = 'us-status-line error';
        installBtn.hidden = false;
      }
    } finally {
      installBtn.disabled = false;
      if (checkBtn) checkBtn.hidden = false;
    }
  }

  async function handleLogout() {
    try {
      await invoke('logout');
      if (window.AgixtChat) {
        try { window.AgixtChat.disconnect(); } catch (_) {}
        try { window.AgixtChat.clear(); } catch (_) {}
      }
      if (window.AgixtNotifications) try { window.AgixtNotifications.stop(); } catch (_) {}
      cache.desktopSettings = null;
      cache.user = null;
      // app.js owns the auth-screen vs chat-screen swap; reload to take
      // the same path the gear-button modal used.
      window.location.reload();
    } catch (err) {
      toast('Logout failed: ' + errMsg(err), 'error');
    }
  }

  // ─── Account tab — identity / verification / password / MFA ───────────

  async function renderAccount(panel) {
    panel.innerHTML = '';
    panel.appendChild(emptyState('Loading account…'));
    let user;
    try { user = await loadUser(true); } catch (err) {
      panel.innerHTML = '';
      panel.appendChild(section('Account', null, [el('p', { class: 'us-hint error' }, errMsg(err))]));
      return;
    }
    if (!user) {
      panel.innerHTML = '';
      panel.appendChild(emptyState('Sign in to manage your account.'));
      return;
    }
    panel.innerHTML = '';

    // Personal info.
    const firstName = el('input', { class: 'us-input', value: user.first_name || '', autocomplete: 'given-name' });
    const lastName = el('input', { class: 'us-input', value: user.last_name || '', autocomplete: 'family-name' });
    const username = el('input', { class: 'us-input', value: user.username || '', autocomplete: 'username' });
    const email = el('input', { class: 'us-input', type: 'email', value: user.email || '', autocomplete: 'email' });
    const phone = el('input', {
      class: 'us-input',
      type: 'tel',
      value: (user.preferences && user.preferences.phone_number) || user.phone_number || '',
      autocomplete: 'tel',
      placeholder: '+1 555 123 4567',
    });
    const savePersonalBtn = btn('Save changes', { kind: 'primary', onclick: async () => {
      savePersonalBtn.disabled = true;
      try {
        await api.updateUser({
          first_name: firstName.value.trim(),
          last_name: lastName.value.trim(),
          username: username.value.trim() || undefined,
          email: email.value.trim(),
          phone_number: phone.value.trim() || '',
        });
        toast('Personal information updated', 'success');
        cache.user = null;
      } catch (err) { toast(errMsg(err), 'error'); }
      finally { savePersonalBtn.disabled = false; }
    } });
    panel.appendChild(section('Personal information',
      'Keep your name, username, and email up to date.',
      [
        el('div', { class: 'us-grid-2' }, [
          field('First name', firstName),
          field('Last name', lastName),
        ]),
        field('Username', username, 'Letters, numbers, underscores, hyphens, and dots. 3–32 characters.'),
        field('Email address', email, 'A verification email is sent if you change this address.'),
        field('Phone number', phone, 'Used for SMS verification and account recovery. Include country code.'),
        el('div', { class: 'us-section-row end' }, [savePersonalBtn]),
      ]));

    // Verification status (read-only summary; actions live in MFA / email card).
    const prefs = user.preferences || {};
    const missing = Array.isArray(prefs.missing_requirements) ? prefs.missing_requirements : [];
    const missingKeys = new Set(missing.flatMap((m) => Object.keys(m || {})));
    const emailVerified = !missingKeys.has('verify_email');
    const smsVerified = !missingKeys.has('verify_sms');
    const mfaVerified = !missingKeys.has('verify_mfa');
    const verifyRows = [
      verifyRow('Email verification', emailVerified ? 'Your email address is verified.' : 'Confirm your email to receive critical alerts.', emailVerified, !emailVerified ? btn('Send verification email', { onclick: async () => {
        try {
          await api.requestEmailVerification(email.value || user.email);
          toast('Verification email sent', 'success');
        } catch (err) { toast(errMsg(err), 'error'); }
      } }) : null),
      verifyRow('Multi-factor authentication',
        mfaVerified ? 'Your account is protected with MFA.' : 'Add an extra layer of security with an authenticator app.',
        mfaVerified, null),
      verifyRow('SMS confirmation',
        smsVerified ? 'Your phone number is verified.' :
          (phone.value ? 'Verify your phone number to enable SMS-based alerts and MFA codes.' :
            'Add a phone number above to enable SMS verification.'),
        smsVerified, null),
    ];
    panel.appendChild(section('Security & verification', null, verifyRows));

    // Password change.
    const currentPwd = el('input', { class: 'us-input', type: 'password', placeholder: 'Current password', autocomplete: 'current-password' });
    const newPwd = el('input', { class: 'us-input', type: 'password', placeholder: 'New password (min. 8 characters)', autocomplete: 'new-password' });
    const confirmPwd = el('input', { class: 'us-input', type: 'password', placeholder: 'Confirm new password', autocomplete: 'new-password' });
    const pwdStatus = el('span', { class: 'us-status-line' }, '');
    const changePwdBtn = btn('Change password', { kind: 'primary', onclick: async () => {
      if (!currentPwd.value) { pwdStatus.textContent = 'Enter your current password.'; pwdStatus.className = 'us-status-line error'; return; }
      if (!newPwd.value || newPwd.value.length < 8) { pwdStatus.textContent = 'New password must be at least 8 characters.'; pwdStatus.className = 'us-status-line error'; return; }
      if (newPwd.value !== confirmPwd.value) { pwdStatus.textContent = 'New passwords do not match.'; pwdStatus.className = 'us-status-line error'; return; }
      changePwdBtn.disabled = true; pwdStatus.textContent = 'Changing password…'; pwdStatus.className = 'us-status-line';
      try {
        await api.changePassword(currentPwd.value, newPwd.value, confirmPwd.value);
        currentPwd.value = ''; newPwd.value = ''; confirmPwd.value = '';
        pwdStatus.textContent = 'Password updated.'; pwdStatus.className = 'us-status-line success';
        toast('Password changed', 'success');
      } catch (err) {
        pwdStatus.textContent = errMsg(err); pwdStatus.className = 'us-status-line error';
      } finally { changePwdBtn.disabled = false; }
    } });
    panel.appendChild(section('Password', null, [
      field('Current password', currentPwd),
      field('New password', newPwd, 'At least 8 characters with upper + lower + digit.'),
      field('Confirm new password', confirmPwd),
      el('div', { class: 'us-section-row end' }, [changePwdBtn]),
      pwdStatus,
    ]));

    // MFA setup / disable.
    const mfaStatus = el('span', { class: 'us-status-line' }, mfaVerified ? 'MFA is enabled on this account.' : 'MFA is not enabled.');
    const mfaSetupBtn = btn(mfaVerified ? 'Reset MFA' : 'Enable MFA', { kind: 'primary', onclick: () => openMfaSetupFlow(panel, mfaStatus, mfaVerified) });
    const mfaDisableBtn = mfaVerified ? btn('Disable MFA', { kind: 'danger', onclick: () => openMfaDisableFlow(panel, mfaStatus) }) : null;
    panel.appendChild(section('Multi-factor authentication',
      'Use an authenticator app (Google Authenticator, Authy, 1Password) to add a second factor to sign-in.',
      [
        el('div', { class: 'us-section-row' }, [mfaSetupBtn, mfaDisableBtn].filter(Boolean)),
        mfaStatus,
      ]));

    const desktopSettings = await loadDesktopSettings().catch(() => null);
    const activeCompanyId = activeCompanyIdForUser(user, desktopSettings);
    const modernMfaSection = section('MFA methods',
      'Manage passkeys, hardware tokens, and opt-in biometric methods for this company.',
      [emptyState(activeCompanyId ? 'Loading MFA methods…' : 'Select a company to manage MFA methods.')]);
    panel.appendChild(modernMfaSection);
    if (activeCompanyId) {
      renderMfaMethodsSection(modernMfaSection, activeCompanyId);
    }

    // OAuth connections.
    const oauthSection = section('Connected services',
      'External providers (Google, Microsoft, GitHub, etc.) linked to this account.',
      [emptyState('Loading…')]);
    panel.appendChild(oauthSection);
    api.getOAuthProviders().then((providers) => {
      const body = oauthSection;
      // Replace the "Loading…" sentinel.
      Array.from(body.children).slice(2).forEach((c) => c.remove());
      const connected = providers.filter((p) => p && (p.connected || p.has_connection));
      if (!connected.length) {
        body.appendChild(emptyState('No connected services.'));
      } else {
        connected.forEach((p) => {
          const slug = api.redirectSlug(p.name || p.slug || p.provider || '');
          const item = el('div', { class: 'us-list-item' }, [
            el('div', { class: 'us-list-item-grow' }, [
              el('p', { class: 'us-list-item-title' }, p.friendly_name || p.name || slug),
              p.account_email ? el('p', { class: 'us-list-item-meta' }, p.account_email) : null,
            ]),
            btn('Disconnect', { onclick: async () => {
              try {
                await api.disconnectOAuth(slug);
                toast('Disconnected', 'success');
                renderAccount(panel);
              } catch (err) { toast(errMsg(err), 'error'); }
            } }),
          ]);
          body.appendChild(item);
        });
      }
    }).catch(() => {
      Array.from(oauthSection.children).slice(2).forEach((c) => c.remove());
      oauthSection.appendChild(emptyState('Could not load connected services.'));
    });

    // Danger zone — delete account.
    const confirmInput = el('input', { class: 'us-input', placeholder: 'Type DELETE to confirm', autocomplete: 'off' });
    const deleteBtn = btn('Delete my account permanently', { kind: 'danger', onclick: async () => {
      if (confirmInput.value.trim() !== 'DELETE') {
        toast('Type DELETE to confirm', 'error');
        return;
      }
      deleteBtn.disabled = true;
      try {
        await api.deleteUserAccount();
        toast('Account deleted.', 'success');
        await invoke('logout').catch(() => {});
        window.location.reload();
      } catch (err) { toast(errMsg(err), 'error'); deleteBtn.disabled = false; }
    } });
    panel.appendChild(section('Delete account',
      'Permanently deletes your account, conversations, agent configurations, and uploaded files. This cannot be undone.',
      [
        confirmInput,
        el('div', { class: 'us-section-row end' }, [deleteBtn]),
      ],
      { danger: true }));
  }

  function verifyRow(label, blurb, verified, action) {
    const status = verified ? badge('Verified', 'success') : badge('Optional');
    return el('div', { class: 'us-list-item' }, [
      el('div', { class: 'us-list-item-grow' }, [
        el('p', { class: 'us-list-item-title' }, [label, ' ', status]),
        el('p', { class: 'us-list-item-meta' }, blurb),
      ]),
      action,
    ]);
  }

  // MFA setup flow — opens a temporary dialog inside the panel.
  function openMfaSetupFlow(panel, statusEl, isReset) {
    const overlay = el('div', { class: 'us-toast', style: 'pointer-events:auto;max-width:380px;width:100%;bottom:auto;top:24px;padding:14px;display:flex;flex-direction:column;gap:10px;z-index:60;' }, [
      el('h3', { class: 'us-section-title' }, isReset ? 'Reset MFA' : 'Enable MFA'),
      el('p', { class: 'us-section-blurb' }, 'Loading…'),
    ]);
    panel.appendChild(overlay);
    const apiCall = isReset ? api.resetMfa() : api.getMfaSetup();
    apiCall.then((res) => {
      const otpUri = res.otp_uri || res.provisioning_uri;
      const secret = res.secret || (otpUri && (otpUri.match(/secret=([^&]+)/) || [])[1]) || '';
      overlay.innerHTML = '';
      overlay.appendChild(el('h3', { class: 'us-section-title' }, isReset ? 'Reset MFA' : 'Enable MFA'));
      overlay.appendChild(el('p', { class: 'us-section-blurb' }, 'Scan this QR code in your authenticator app, then enter the 6-digit code below.'));
      // QR code via api.qrserver.com (web app uses this exact pattern in the
      // /user/manage MFA reset dialog — same image source, same params).
      const qrImg = el('img', {
        src: `https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(otpUri || '')}`,
        alt: 'MFA QR code',
        style: 'width:180px;height:180px;background:#fff;border-radius:8px;align-self:center;',
      });
      overlay.appendChild(qrImg);
      if (secret) {
        overlay.appendChild(el('p', { class: 'us-hint' }, ['Manual key: ', el('code', { class: 'us-mono' }, secret)]));
      }
      const code = el('input', { class: 'us-input', placeholder: '123456', maxlength: 6, inputmode: 'numeric', autocomplete: 'one-time-code' });
      overlay.appendChild(code);
      const status = el('span', { class: 'us-status-line' }, '');
      overlay.appendChild(status);
      const enableBtn = btn('Enable MFA', { kind: 'primary', onclick: async () => {
        if (!/^\d{6}$/.test(code.value)) { status.textContent = 'Enter the 6-digit code.'; status.className = 'us-status-line error'; return; }
        enableBtn.disabled = true;
        try {
          await api.enableMfa(code.value);
          toast('MFA enabled', 'success');
          statusEl.textContent = 'MFA is enabled on this account.';
          statusEl.className = 'us-status-line success';
          cache.user = null;
          overlay.remove();
        } catch (err) { status.textContent = errMsg(err); status.className = 'us-status-line error'; enableBtn.disabled = false; }
      } });
      const cancelBtn = btn('Close', { onclick: () => overlay.remove() });
      overlay.appendChild(el('div', { class: 'us-section-row end' }, [cancelBtn, enableBtn]));
    }).catch((err) => {
      overlay.innerHTML = '';
      overlay.appendChild(el('p', { class: 'us-hint error' }, errMsg(err)));
      overlay.appendChild(btn('Close', { onclick: () => overlay.remove() }));
    });
  }

  function openMfaDisableFlow(panel, statusEl) {
    const overlay = el('div', { class: 'us-toast', style: 'pointer-events:auto;max-width:380px;width:100%;bottom:auto;top:24px;padding:14px;display:flex;flex-direction:column;gap:10px;z-index:60;' });
    panel.appendChild(overlay);
    overlay.appendChild(el('h3', { class: 'us-section-title' }, 'Disable MFA'));
    overlay.appendChild(el('p', { class: 'us-section-blurb' }, 'Confirm your password and current MFA code to disable MFA.'));
    const password = el('input', { class: 'us-input', type: 'password', placeholder: 'Password', autocomplete: 'current-password' });
    const code = el('input', { class: 'us-input', placeholder: '6-digit code', maxlength: 6, inputmode: 'numeric', autocomplete: 'one-time-code' });
    const status = el('span', { class: 'us-status-line' }, '');
    overlay.appendChild(password);
    overlay.appendChild(code);
    overlay.appendChild(status);
    const disableBtn = btn('Disable MFA', { kind: 'danger', onclick: async () => {
      if (!password.value) { status.textContent = 'Enter your password.'; status.className = 'us-status-line error'; return; }
      if (!/^\d{6}$/.test(code.value)) { status.textContent = 'Enter the 6-digit MFA code.'; status.className = 'us-status-line error'; return; }
      disableBtn.disabled = true;
      try {
        await api.disableMfa(password.value, code.value);
        toast('MFA disabled', 'success');
        statusEl.textContent = 'MFA is not enabled.';
        statusEl.className = 'us-status-line';
        cache.user = null;
        overlay.remove();
      } catch (err) { status.textContent = errMsg(err); status.className = 'us-status-line error'; disableBtn.disabled = false; }
    } });
    const cancelBtn = btn('Cancel', { onclick: () => overlay.remove() });
    overlay.appendChild(el('div', { class: 'us-section-row end' }, [cancelBtn, disableBtn]));
  }

  async function renderMfaMethodsSection(sectionEl, companyId) {
    replaceSectionBody(sectionEl, [emptyState('Loading MFA methods…')]);
    let methods;
    try {
      methods = await api.getMfaMethods(companyId);
    } catch (err) {
      replaceSectionBody(sectionEl, [
        el('p', { class: 'us-hint error' }, errMsg(err)),
        btn('Retry', { onclick: () => renderMfaMethodsSection(sectionEl, companyId) }),
      ]);
      return;
    }

    const webauthnCredentials = Array.isArray(methods.webauthn_credentials)
      ? methods.webauthn_credentials
      : [];
    const hardwareTokens = Array.isArray(methods.hardware_token_credentials)
      ? methods.hardware_token_credentials
      : [];
    const enabledMethods = Array.isArray(methods.enabled_methods) ? methods.enabled_methods : [];
    const availableMethods = Array.isArray(methods.available_methods) ? methods.available_methods : [];
    const biometricAllowed = methods.biometric_policy && methods.biometric_policy.biometric_allowed;

    const actionRow = el('div', { class: 'us-section-row' }, [
      btn('Verify password', { onclick: () => verifyPasswordForMfa(companyId) }),
      btn('Verify TOTP', { onclick: () => verifyTotpForMfa(companyId) }),
      btn('Add passkey', { kind: 'primary', onclick: () => addPasskey(sectionEl, companyId) }),
      webauthnCredentials.length
        ? btn('Verify passkey', { onclick: () => verifyPasskey(sectionEl, companyId) })
        : null,
      btn('Add hardware token', { onclick: () => addHardwareToken(sectionEl, companyId) }),
      hardwareTokens.length
        ? btn('Verify hardware token', { onclick: () => verifyHardwareToken(sectionEl, companyId, hardwareTokens) })
        : null,
      biometricAllowed ? btn('Enroll voice', { onclick: () => enrollVoice(sectionEl, companyId) }) : null,
      biometricAllowed ? btn('Enroll face', { onclick: () => enrollFace(sectionEl, companyId) }) : null,
      btn('Refresh', { onclick: () => renderMfaMethodsSection(sectionEl, companyId) }),
    ].filter(Boolean));

    const methodRows = enabledMethods.length
      ? enabledMethods.map((method) => {
        const type = method.method_type;
        const isBiometric = type === 'face' || type === 'voice';
        return el('div', { class: 'us-list-item' }, [
          el('div', { class: 'us-list-item-grow' }, [
            el('p', { class: 'us-list-item-title' }, [
              methodLabel(type),
              ' ',
              badge(method.enabled ? 'Enabled' : 'Disabled', method.enabled ? 'success' : null),
            ]),
            el('p', { class: 'us-list-item-meta' },
              method.verified_at ? 'Verified ' + formatDate(method.verified_at) : 'Ready for policy checks.'),
          ]),
          isBiometric
            ? btn('Revoke', {
              kind: 'danger',
              onclick: () => revokeBiometricMethod(sectionEl, companyId, type),
            })
            : null,
        ]);
      })
      : [emptyState('No MFA methods are enabled yet.')];

    const passkeyRows = webauthnCredentials.map((credential) => {
      const id = credential.credential_id || credential.id;
      return el('div', { class: 'us-list-item' }, [
        el('div', { class: 'us-list-item-grow' }, [
          el('p', { class: 'us-list-item-title' }, 'Passkey credential'),
          el('p', { class: 'us-list-item-meta' },
            credential.last_used_at
              ? 'Last used ' + formatDate(credential.last_used_at)
              : 'Registered ' + (credential.created_at ? formatDate(credential.created_at) : shortId(id))),
        ]),
        btn('Revoke', {
          kind: 'danger',
          onclick: () => revokePasskey(sectionEl, companyId, id),
        }),
      ]);
    });

    const tokenRows = hardwareTokens.map((token) => {
      const id = token.key_id || token.id;
      return el('div', { class: 'us-list-item' }, [
        el('div', { class: 'us-list-item-grow' }, [
          el('p', { class: 'us-list-item-title' }, token.label || 'Hardware token'),
          el('p', { class: 'us-list-item-meta' },
            token.last_used_at
              ? 'Last used ' + formatDate(token.last_used_at)
              : 'Registered ' + (token.created_at ? formatDate(token.created_at) : shortId(id))),
        ]),
        btn('Revoke', {
          kind: 'danger',
          onclick: () => revokeHardwareToken(sectionEl, companyId, id),
        }),
      ]);
    });

    replaceSectionBody(sectionEl, [
      methods.biometric_policy && methods.biometric_policy.non_biometric_fallback_required
        ? el('p', { class: 'us-hint' }, 'Accessible non-biometric fallback is required by policy.')
        : null,
      actionRow,
      el('div', { class: 'us-section-row' }, availableMethods.map((method) => badge(methodLabel(method)))),
      ...methodRows,
      ...passkeyRows,
      ...tokenRows,
    ].filter(Boolean));
  }

  async function verifyPasswordForMfa(companyId) {
    const password = window.prompt('Password confirmation');
    if (!password) return;
    try {
      await api.verifyPasswordStrong(password, companyId);
      toast('Password verification recorded', 'success');
    } catch (err) {
      toast(errMsg(err), 'error');
    }
  }

  async function verifyTotpForMfa(companyId) {
    const code = window.prompt('Authenticator code');
    if (!code) return;
    try {
      await api.verifyTotpStrong(code.trim(), companyId);
      toast('TOTP verification recorded', 'success');
    } catch (err) {
      toast(errMsg(err), 'error');
    }
  }

  async function addPasskey(sectionEl, companyId) {
    try {
      await api.registerPasskey(companyId);
      toast('Passkey registered', 'success');
      await renderMfaMethodsSection(sectionEl, companyId);
    } catch (err) {
      toast(errMsg(err), 'error');
    }
  }

  async function verifyPasskey(sectionEl, companyId) {
    try {
      await api.authenticatePasskey(companyId);
      toast('Passkey verification recorded', 'success');
      await renderMfaMethodsSection(sectionEl, companyId);
    } catch (err) {
      toast(errMsg(err), 'error');
    }
  }

  async function revokePasskey(sectionEl, companyId, credentialId) {
    if (!credentialId || !window.confirm('Revoke this passkey?')) return;
    try {
      await api.revokeWebauthnCredential(credentialId, companyId);
      toast('Passkey revoked', 'success');
      await renderMfaMethodsSection(sectionEl, companyId);
    } catch (err) {
      toast(errMsg(err), 'error');
    }
  }

  async function addHardwareToken(sectionEl, companyId) {
    const keyId = window.prompt('Hardware token key ID', 'desktop-token-' + Date.now());
    if (!keyId) return;
    const sharedSecret = window.prompt('Shared secret from the hardware token or companion device');
    if (!sharedSecret) return;
    const label = window.prompt('Label for this token', 'Desktop hardware token') || '';
    try {
      const start = await api.hardwareTokenRegisterStart(companyId);
      await api.hardwareTokenRegisterFinish({
        company_id: companyId,
        challenge_id: start.challenge_id,
        key_id: keyId.trim(),
        shared_secret: sharedSecret.trim(),
        label: label.trim() || undefined,
      });
      toast('Hardware token registered', 'success');
      await renderMfaMethodsSection(sectionEl, companyId);
    } catch (err) {
      toast(errMsg(err), 'error');
    }
  }

  async function verifyHardwareToken(sectionEl, companyId, tokens) {
    const firstKey = tokens && tokens[0] ? tokens[0].key_id : '';
    const keyId = window.prompt('Hardware token key ID', firstKey || '');
    if (!keyId) return;
    const message = 'agixt-desktop-hardware-token:' + Date.now();
    try {
      const start = await api.hardwareTokenVerifyStart({ company_id: companyId, key_id: keyId.trim() });
      const binding = 'challenge_id=' + start.challenge_id + '\nkey_id=' + keyId.trim()
        + '\nmessage=' + message;
      const signature = window.prompt('Enter the token signature for:\n' + binding);
      if (!signature) return;
      await api.hardwareTokenVerify({
        company_id: companyId,
        challenge_id: start.challenge_id,
        key_id: keyId.trim(),
        message,
        signature: signature.trim(),
      });
      toast('Hardware token verification recorded', 'success');
      await renderMfaMethodsSection(sectionEl, companyId);
    } catch (err) {
      toast(errMsg(err), 'error');
    }
  }

  async function revokeHardwareToken(sectionEl, companyId, keyId) {
    if (!keyId || !window.confirm('Revoke this hardware token?')) return;
    try {
      await api.revokeHardwareToken(keyId, companyId);
      toast('Hardware token revoked', 'success');
      await renderMfaMethodsSection(sectionEl, companyId);
    } catch (err) {
      toast(errMsg(err), 'error');
    }
  }

  async function ensureBiometricConsent(methodType, companyId) {
    let records = [];
    let disclosures = [];
    try {
      const response = await api.getBiometricConsent(companyId);
      records = Array.isArray(response && response.consent_records) ? response.consent_records : [];
      disclosures = Array.isArray(response && response.current_disclosures) ? response.current_disclosures : [];
    } catch (_) {}
    const disclosure = disclosures.find((entry) => {
      const method = entry && entry.method_type;
      return method === methodType || method === 'all_biometric';
    });
    if (!disclosure) throw new Error('Current biometric consent disclosure is not available.');
    const hasConsent = records.some((record) => {
      const method = record.method_type;
      return !record.revoked_at
        && record.consent_version === disclosure.consent_version
        && record.disclosures_hash === disclosure.disclosures_hash
        && record.purpose === disclosure.purpose
        && record.retention_policy === disclosure.retention_policy
        && (method === methodType || method === 'all_biometric');
    });
    if (hasConsent) return disclosure;
    const label = methodType === 'face' ? 'face' : 'voice';
    const accepted = window.confirm(
      'Enroll ' + label + ' biometrics for MFA and robot identity assurance? '
      + 'Templates are encrypted server-side and raw samples are not retained by default.',
    );
    if (!accepted) throw new Error('Biometric consent was not accepted.');
    const jurisdiction = consentJurisdiction(disclosure);
    await api.acceptBiometricConsent({
      company_id: companyId,
      method_type: disclosure.method_type || methodType,
      consent_version: disclosure.consent_version,
      disclosures_hash: disclosure.disclosures_hash,
      purpose: disclosure.purpose,
      retention_policy: disclosure.retention_policy,
      jurisdiction,
    });
    return disclosure;
  }

  function consentJurisdiction(disclosure) {
    const scope = Array.isArray(disclosure && disclosure.jurisdiction_scope)
      ? disclosure.jurisdiction_scope.filter(Boolean).map(String)
      : [];
    let localeRegion = '';
    try {
      const locale = Intl.DateTimeFormat().resolvedOptions().locale || '';
      localeRegion = locale.split('-').pop().toUpperCase();
    } catch (_) {}
    return scope.find((entry) => entry.toUpperCase() === localeRegion) || scope[0] || 'US';
  }

  async function revokeBiometricMethod(sectionEl, companyId, methodType) {
    if (!window.confirm('Revoke ' + methodLabel(methodType) + ' biometric consent and templates?')) return;
    try {
      await api.revokeBiometricConsent(methodType, companyId);
      toast(methodLabel(methodType) + ' revoked', 'success');
      await renderMfaMethodsSection(sectionEl, companyId);
    } catch (err) {
      toast(errMsg(err), 'error');
    }
  }

  async function enrollVoice(sectionEl, companyId) {
    try {
      await ensureBiometricConsent('voice', companyId);
      const start = await invoke('biometric_voice_enroll_start', { args: { company_id: companyId } });
      const challenge = start.challenge || start;
      const phrase = challenge.phrase || '';
      const status = el('span', { class: 'us-status-line' }, 'Recording…');
      let finished = false;
      const finishBtn = btn('Finish enrollment', { kind: 'primary', onclick: async () => {
        if (finished) return;
        finished = true;
        finishBtn.disabled = true;
        status.textContent = 'Uploading voice sample…';
        try {
          await invoke('biometric_voice_enroll_stop', {
            args: {
              company_id: companyId,
              challenge_id: challenge.challenge_id,
              transcript: phrase,
              liveness_result: 'challenge_phrase_passed',
            },
          });
          modal.close();
          toast('Voice enrolled', 'success');
          await renderMfaMethodsSection(sectionEl, companyId);
        } catch (err) {
          finished = false;
          finishBtn.disabled = false;
          status.textContent = errMsg(err);
          status.className = 'us-status-line error';
        }
      } });
      const cancelBtn = btn('Cancel', { onclick: async () => {
        try { await invoke('voice_cancel_recording'); } catch (_) {}
        modal.close();
      } });
      const modal = openModal({
        title: 'Voice enrollment',
        description: phrase ? 'Read the phrase below, then finish enrollment.' : 'Record a short enrollment phrase.',
        body: [
          phrase ? el('p', { class: 'us-mono' }, phrase) : null,
          status,
        ],
        footer: [cancelBtn, finishBtn],
      });
    } catch (err) {
      toast(errMsg(err), 'error');
      try { await invoke('voice_cancel_recording'); } catch (_) {}
    }
  }

  async function enrollFace(sectionEl, companyId) {
    try {
      await ensureBiometricConsent('face', companyId);
      const challenge = await api.startFaceEnrollment(companyId);
      const samples = await captureFaceSamples();
      if (!samples.length) return;
      await api.verifyFaceEnrollment({
        company_id: companyId,
        challenge_id: challenge.challenge_id,
        device_class: 'desktop_webcam',
        samples,
        metadata: { capture_source: 'agixt_desktop_webview_camera' },
      });
      toast('Face enrolled', 'success');
      await renderMfaMethodsSection(sectionEl, companyId);
    } catch (err) {
      toast(errMsg(err), 'error');
    }
  }

  async function captureFaceSamples() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('Camera capture is not available in this desktop webview.');
    }
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 } },
      audio: false,
    });
    const video = el('video', {
      autoplay: true,
      muted: true,
      playsInline: true,
      style: 'width:100%;max-height:360px;background:#000;border-radius:8px;',
    });
    video.srcObject = stream;
    const status = el('span', { class: 'us-status-line' }, 'Camera ready.');
    let resolveCapture;
    let settled = false;
    function stopCamera() {
      stream.getTracks().forEach((track) => {
        try { track.stop(); } catch (_) {}
      });
    }
    const promise = new Promise((resolve) => { resolveCapture = resolve; });
    const captureBtn = btn('Capture frames', { kind: 'primary', onclick: async () => {
      captureBtn.disabled = true;
      status.textContent = 'Capturing frames…';
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      const context = canvas.getContext('2d');
      const samples = [];
      for (let index = 0; index < 3; index += 1) {
        if (index > 0) await new Promise((resolve) => setTimeout(resolve, 350));
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.82);
        samples.push({
          data_base64: dataUrl.split(',')[1],
          quality_score: 0.95,
          liveness_result: 'motion_passed',
          metadata: { frame_index: index, width: canvas.width, height: canvas.height },
        });
      }
      settled = true;
      stopCamera();
      modal.close();
      resolveCapture(samples);
    } });
    const cancelBtn = btn('Cancel', { onclick: () => {
      settled = true;
      stopCamera();
      modal.close();
      resolveCapture([]);
    } });
    const modal = openModal({
      title: 'Face enrollment',
      description: 'Center your face and capture a short frame set.',
      body: [video, status],
      footer: [cancelBtn, captureBtn],
      wide: true,
      onClose: () => {
        if (!settled) {
          stopCamera();
          resolveCapture([]);
        }
      },
    });
    setupModalFocus(modal);
    return promise;
  }

  // ─── Settings tab — theme/timezone/notifications ─────────────────────

  async function renderSettings(panel) {
    panel.innerHTML = '';
    panel.appendChild(emptyState('Loading…'));
    let user;
    try { user = await loadUser(); } catch (err) {
      panel.innerHTML = '';
      panel.appendChild(section('Settings', null, [el('p', { class: 'us-hint error' }, errMsg(err))]));
      return;
    }
    if (!user) {
      panel.innerHTML = '';
      panel.appendChild(emptyState('Sign in to manage your settings.'));
      return;
    }
    panel.innerHTML = '';
    const prefs = user.preferences || {};

    // Theme — kept here too for parity with the web app's /user/settings.
    const settings = await loadDesktopSettings();
    const themeSelect = el('select', { class: 'us-select' }, [
      el('option', { value: 'system' }, 'Match system'),
      el('option', { value: 'light' }, 'Light'),
      el('option', { value: 'gray' }, 'Dark'),
      el('option', { value: 'dark' }, 'Dark Blue'),
    ]);
    themeSelect.value = settings.theme || 'system';
    themeSelect.addEventListener('change', async () => {
      const value = themeSelect.value;
      await invoke('save_settings', { settings: { ...settings, theme: value } });
      cache.desktopSettings = { ...settings, theme: value };
      const resolved = value === 'system'
        ? (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'gray' : 'light')
        : value;
      document.documentElement.setAttribute('data-theme', resolved);
      try { window.localStorage.setItem('agixt.theme', value); } catch (_) {}
      window.dispatchEvent(new CustomEvent('agixt-theme-changed', { detail: { theme: value, resolved } }));
      toast('Theme saved', 'success');
    });
    panel.appendChild(section('Theme', 'Choose a theme for the interface.', [themeSelect]));

    // Timezone — most common picks first, plus the user's current zone.
    const browserTz = (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'; } catch (_) { return 'UTC'; } })();
    const tzInput = el('input', { class: 'us-input', placeholder: browserTz, value: prefs.timezone || '' });
    const saveTzBtn = btn('Save', { kind: 'primary', onclick: async () => {
      const value = tzInput.value.trim();
      try {
        await api.updateUser({ timezone: value });
        toast('Timezone saved', 'success');
        cache.user = null;
      } catch (err) { toast(errMsg(err), 'error'); }
    } });
    const useBrowserTzBtn = btn('Use browser zone (' + browserTz + ')', { onclick: () => { tzInput.value = browserTz; } });
    panel.appendChild(section('Timezone',
      'IANA zone identifier (e.g. America/Chicago). Used for timestamps and scheduling.',
      [
        tzInput,
        el('div', { class: 'us-section-row' }, [useBrowserTzBtn, saveTzBtn]),
      ]));

    // Notification preferences — JSON in user preferences. We render a
    // master toggle + a free-form JSON editor for advanced users; the
    // full per-category UI from the web's /user/settings is available
    // there for power users.
    let notifPrefs = {};
    try {
      const raw = (prefs && (prefs.raw || prefs)) || {};
      const json = raw.notification_preferences;
      if (typeof json === 'string') notifPrefs = JSON.parse(json);
      else if (json && typeof json === 'object') notifPrefs = json;
    } catch (_) { notifPrefs = {}; }
    const masterToggle = el('input', { type: 'checkbox' });
    masterToggle.checked = notifPrefs.enabled !== false;
    const jsonEditor = el('textarea', { class: 'us-textarea', rows: 8, spellcheck: 'false' });
    jsonEditor.value = JSON.stringify(notifPrefs, null, 2);
    const saveNotifBtn = btn('Save notifications', { kind: 'primary', onclick: async () => {
      let parsed;
      try {
        parsed = jsonEditor.value.trim() ? JSON.parse(jsonEditor.value) : {};
      } catch (err) { toast('Invalid JSON: ' + errMsg(err), 'error'); return; }
      parsed.enabled = masterToggle.checked;
      try {
        await api.updateUser({ notification_preferences: JSON.stringify(parsed) });
        cache.user = null;
        toast('Notifications saved', 'success');
      } catch (err) { toast(errMsg(err), 'error'); }
    } });
    panel.appendChild(section('Notifications',
      'Master toggle plus a JSON editor for category/action overrides. The web app has the full per-category UI.',
      [
        el('label', { class: 'us-check' }, [masterToggle, el('span', null, 'Enable notifications')]),
        jsonEditor,
        el('div', { class: 'us-section-row end' }, [saveNotifBtn]),
      ]));
  }

  // ─── Developer tab — Personal Access Tokens ──────────────────────────

  async function renderDeveloper(panel) {
    panel.innerHTML = '';
    panel.appendChild(emptyState('Loading tokens…'));
    let tokens;
    try {
      [tokens, cache.tokenScopes, cache.tokenAgents, cache.tokenCompanies] = await Promise.all([
        api.listPersonalAccessTokens(),
        api.getAvailableTokenScopes().catch(() => []),
        api.getAvailableTokenAgents().catch(() => []),
        api.getAvailableTokenCompanies().catch(() => []),
      ]);
      cache.tokens = tokens;
    } catch (err) {
      panel.innerHTML = '';
      panel.appendChild(section('Developer', null, [el('p', { class: 'us-hint error' }, errMsg(err))]));
      return;
    }
    panel.innerHTML = '';

    // Create form is opened on demand to keep the default view tidy.
    const createBtn = btn('+ New token', { kind: 'primary', onclick: () => {
      panel.querySelectorAll('[data-token-form]').forEach((n) => n.remove());
      panel.insertBefore(buildTokenCreateForm(panel), panel.firstChild);
    } });
    panel.appendChild(section('Personal access tokens',
      'Use tokens instead of passwords to authenticate API requests. Treat them like passwords — never commit or share them.',
      [el('div', { class: 'us-section-row end' }, [createBtn])]));

    if (!tokens || !tokens.length) {
      panel.appendChild(emptyState('No tokens yet. Create one to call the AGiXT API.'));
      return;
    }
    const list = el('div', { class: 'us-row-list' });
    tokens.forEach((t) => list.appendChild(buildTokenRow(t, panel)));
    panel.appendChild(list);
  }

  function buildTokenRow(token, panel) {
    const meta = [
      token.token_prefix ? el('code', { class: 'us-mono' }, token.token_prefix + '…') : null,
      ' · ',
      token.expires_at ? 'Expires ' + new Date(token.expires_at).toLocaleDateString() : 'No expiration',
      ' · ',
      'Last used ' + (token.last_used_at ? new Date(token.last_used_at).toLocaleDateString() : 'never'),
    ];
    return el('div', { class: 'us-list-item' }, [
      el('div', { class: 'us-list-item-grow' }, [
        el('p', { class: 'us-list-item-title' }, [token.name, ' ',
          token.is_revoked ? badge('Revoked', 'danger') : null,
          token.expires_at && new Date(token.expires_at) < new Date() ? badge('Expired', 'warn') : null,
        ].filter(Boolean)),
        el('p', { class: 'us-list-item-meta' }, meta.filter(Boolean)),
        token.description ? el('p', { class: 'us-list-item-meta' }, token.description) : null,
      ]),
      el('div', { class: 'us-list-item-actions' }, [
        btn('Regenerate', { onclick: async () => {
          if (!confirm('Regenerate this token? The old value stops working immediately.')) return;
          try {
            const res = await api.regeneratePersonalAccessToken(token.id);
            showCreatedToken(res.token, panel);
            renderDeveloper(panel);
          } catch (err) { toast(errMsg(err), 'error'); }
        } }),
        btn('Revoke', { kind: 'danger', onclick: async () => {
          if (!confirm('Revoke "' + token.name + '"? Any apps using this token lose access.')) return;
          try {
            await api.revokePersonalAccessToken(token.id);
            toast('Token revoked', 'success');
            renderDeveloper(panel);
          } catch (err) { toast(errMsg(err), 'error'); }
        } }),
      ]),
    ]);
  }

  function buildTokenCreateForm(panel) {
    const wrap = el('section', { class: 'us-section', dataset: { tokenForm: '1' } });
    wrap.appendChild(el('h2', { class: 'us-section-title' }, 'New personal access token'));

    const name = el('input', { class: 'us-input', placeholder: 'My API token' });
    const description = el('textarea', { class: 'us-textarea', rows: 2, placeholder: 'What is this token for?' });
    const expiration = el('select', { class: 'us-select' }, [
      el('option', { value: '7_days' }, '7 days'),
      el('option', { value: '30_days' }, '30 days'),
      el('option', { value: '90_days' }, '90 days'),
      el('option', { value: '1_year' }, '1 year'),
      el('option', { value: 'never' }, 'No expiration'),
    ]);
    expiration.value = '30_days';

    // Scopes grouped by category — exact mirror of the web's developer page.
    const scopeWrap = el('div', { class: 'us-scope-list' });
    const scopes = cache.tokenScopes || [];
    const grouped = new Map();
    const everythingScope = scopes.find((s) => s.name === '*');
    scopes.forEach((s) => {
      if (s.name === '*') return;
      const arr = grouped.get(s.category) || [];
      arr.push(s);
      grouped.set(s.category, arr);
    });
    const selectedScopes = new Set();
    function refreshScopeWrap() {
      scopeWrap.innerHTML = '';
      if (everythingScope) {
        const everyChk = el('input', { type: 'checkbox' });
        everyChk.checked = selectedScopes.has('*');
        everyChk.addEventListener('change', () => {
          selectedScopes.clear();
          if (everyChk.checked) selectedScopes.add('*');
          refreshScopeWrap();
        });
        scopeWrap.appendChild(el('label', { class: 'us-check' }, [everyChk, el('span', null, 'Everything (*) — every current + future scope')]));
      }
      Array.from(grouped.entries()).forEach(([cat, list]) => {
        const cap = el('div', { class: 'us-scope-cat' }, cat);
        scopeWrap.appendChild(cap);
        list.forEach((scope) => {
          const chk = el('input', { type: 'checkbox' });
          chk.checked = selectedScopes.has('*') || selectedScopes.has(scope.name);
          chk.disabled = selectedScopes.has('*');
          chk.addEventListener('change', () => {
            if (chk.checked) selectedScopes.add(scope.name);
            else selectedScopes.delete(scope.name);
          });
          scopeWrap.appendChild(el('label', { class: 'us-scope-row' }, [
            chk,
            el('div', null, [
              el('code', null, scope.name),
              scope.description ? el('div', { class: 'us-scope-row-desc' }, scope.description) : null,
            ]),
          ]));
        });
      });
      if (!grouped.size && !everythingScope) {
        scopeWrap.appendChild(emptyState('No scopes available.'));
      }
    }
    refreshScopeWrap();

    // Optional restrictions.
    const agentWrap = el('div', { class: 'us-scope-list', style: 'max-height:120px;' });
    const selectedAgents = new Set();
    (cache.tokenAgents || []).forEach((a) => {
      const chk = el('input', { type: 'checkbox' });
      chk.addEventListener('change', () => { chk.checked ? selectedAgents.add(a.id) : selectedAgents.delete(a.id); });
      agentWrap.appendChild(el('label', { class: 'us-scope-row' }, [chk,
        el('div', null, a.name + (a.company_name ? ' · ' + a.company_name : ''))]));
    });
    if (!cache.tokenAgents || !cache.tokenAgents.length) agentWrap.appendChild(emptyState('No agents available.'));

    const companyWrap = el('div', { class: 'us-scope-list', style: 'max-height:120px;' });
    const selectedCompanies = new Set();
    (cache.tokenCompanies || []).forEach((c) => {
      const chk = el('input', { type: 'checkbox' });
      chk.addEventListener('change', () => { chk.checked ? selectedCompanies.add(c.id) : selectedCompanies.delete(c.id); });
      companyWrap.appendChild(el('label', { class: 'us-scope-row' }, [chk, el('div', null, c.name)]));
    });
    if (!cache.tokenCompanies || !cache.tokenCompanies.length) companyWrap.appendChild(emptyState('No companies available.'));

    const status = el('span', { class: 'us-status-line' }, '');
    const cancelBtn = btn('Cancel', { onclick: () => wrap.remove() });
    const createBtn = btn('Generate token', { kind: 'primary', onclick: async () => {
      if (!name.value.trim()) { status.textContent = 'Name is required.'; status.className = 'us-status-line error'; return; }
      if (!selectedScopes.size) { status.textContent = 'Select at least one scope.'; status.className = 'us-status-line error'; return; }
      createBtn.disabled = true;
      try {
        const res = await api.createPersonalAccessToken({
          name: name.value.trim(),
          description: description.value.trim() || undefined,
          expiration: expiration.value,
          scopes: Array.from(selectedScopes),
          agent_ids: selectedAgents.size ? Array.from(selectedAgents) : undefined,
          company_ids: selectedCompanies.size ? Array.from(selectedCompanies) : undefined,
        });
        wrap.remove();
        showCreatedToken(res.token, panel);
        renderDeveloper(panel);
      } catch (err) {
        status.textContent = errMsg(err); status.className = 'us-status-line error';
      } finally { createBtn.disabled = false; }
    } });

    wrap.appendChild(field('Token name', name, "What's this token for?"));
    wrap.appendChild(field('Description (optional)', description));
    wrap.appendChild(field('Expiration', expiration, 'Tokens with no expiration pose a security risk.'));
    wrap.appendChild(el('div', { class: 'us-section-blurb' }, 'Scopes — pick the minimum permissions this token actually needs.'));
    wrap.appendChild(scopeWrap);
    if (cache.tokenAgents && cache.tokenAgents.length) {
      wrap.appendChild(el('div', { class: 'us-section-blurb' }, 'Restrict to specific agents (optional)'));
      wrap.appendChild(agentWrap);
    }
    if (cache.tokenCompanies && cache.tokenCompanies.length) {
      wrap.appendChild(el('div', { class: 'us-section-blurb' }, 'Restrict to specific companies (optional)'));
      wrap.appendChild(companyWrap);
    }
    wrap.appendChild(status);
    wrap.appendChild(el('div', { class: 'us-section-row end' }, [cancelBtn, createBtn]));
    return wrap;
  }

  function showCreatedToken(token, panel) {
    const overlay = el('section', { class: 'us-section', style: 'border-color:rgba(94,210,143,0.4);background:rgba(94,210,143,0.06);' });
    overlay.appendChild(el('h2', { class: 'us-section-title' }, 'Token created'));
    overlay.appendChild(el('p', { class: 'us-section-blurb' },
      'Copy this token now — you won\'t be able to see it again.'));
    const codeEl = el('code', { class: 'us-mono', style: 'word-break:break-all;display:block;padding:8px;' }, token);
    overlay.appendChild(codeEl);
    overlay.appendChild(el('div', { class: 'us-section-row end' }, [
      btn('Copy', { kind: 'primary', onclick: async () => {
        try { await navigator.clipboard.writeText(token); toast('Copied', 'success'); }
        catch (err) { toast('Copy failed: ' + errMsg(err), 'error'); }
      } }),
      btn('Dismiss', { onclick: () => overlay.remove() }),
    ]));
    panel.insertBefore(overlay, panel.firstChild);
  }

  // ─── Billing tab ─────────────────────────────────────────────────────

  async function ensureBillingTabVisible() {
    const billingTab = document.querySelector('.us-tab[data-us-tab="billing"]');
    if (!billingTab) return false;
    const enabled = await api.getBillingEnabled().catch(() => ({ billing_enabled: false }));
    cache.billingEnabled = enabled;
    billingTab.hidden = !(enabled && enabled.billing_enabled);
    return enabled && enabled.billing_enabled;
  }

  // Pending payment markers — when the user opens an external Stripe
  // checkout, we record the kind, the active company, and the token
  // balance at the moment of handoff. On return to the app, we compare
  // the live balance against that baseline to decide whether the
  // payment completed, is still pending, or appears to have failed/
  // been cancelled. The marker survives reloads via localStorage and
  // auto-expires after 30 minutes to avoid stale banners.
  const PENDING_PAYMENT_KEY = 'agixt.desktop.pendingPayment.v1';
  const PENDING_PAYMENT_TTL_MS = 30 * 60 * 1000;
  function loadPendingPayment() {
    try {
      const raw = window.localStorage.getItem(PENDING_PAYMENT_KEY);
      if (!raw) return null;
      const data = JSON.parse(raw);
      if (!data || !data.started_at) return null;
      if (Date.now() - data.started_at > PENDING_PAYMENT_TTL_MS) {
        window.localStorage.removeItem(PENDING_PAYMENT_KEY);
        return null;
      }
      return data;
    } catch (_) { return null; }
  }
  function savePendingPayment(data) {
    try {
      window.localStorage.setItem(PENDING_PAYMENT_KEY, JSON.stringify(Object.assign({
        started_at: Date.now(),
        status: 'pending',
      }, data || {})));
    } catch (_) {}
  }
  function clearPendingPayment() {
    try { window.localStorage.removeItem(PENDING_PAYMENT_KEY); } catch (_) {}
  }

  // Banner DOM: surfaced at the top of the billing panel when a pending
  // payment marker exists. Distinguishes four phases:
  //   pending (<5 min)     → "Finishing your payment…"
  //   waiting (5-15 min)   → "Still waiting…" with Refresh
  //   likely canceled (>15 min) → "Looks like the checkout was abandoned"
  //   completed            → balance jumped past baseline
  function renderPaymentReturnBanner(payment, currentBalanceTokens, onRefresh, onDismiss) {
    const baseline = Number(payment.baseline_balance_tokens || 0);
    const balance = Number(currentBalanceTokens || 0);
    const completed = balance > baseline;
    const elapsedMin = Math.max(0, Math.round((Date.now() - payment.started_at) / 60000));
    const waiting = !completed && elapsedMin >= 5 && elapsedMin < 15;
    const likelyCanceled = !completed && elapsedMin >= 15;

    const variant = completed ? 'success'
      : likelyCanceled ? 'bad'
      : waiting ? 'warn'
      : 'info';
    const icon = completed
      ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
      : likelyCanceled
      ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>'
      : waiting
      ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>'
      : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>';
    const title = completed ? 'Payment completed'
      : likelyCanceled ? 'Checkout appears canceled'
      : waiting ? 'Still waiting on your payment'
      : 'Finishing your payment…';
    const kindLabel = payment.kind === 'plan' ? 'subscription change' : 'token top-up';
    const body = completed
      ? 'Your ' + kindLabel + ' came through — the new balance is loaded above.'
      : likelyCanceled
      ? 'It has been ' + elapsedMin + ' minutes since you opened Stripe and no payment landed. The checkout was likely canceled or failed. Retry from the top-up form below, or dismiss this banner.'
      : waiting
      ? 'It has been about ' + elapsedMin + ' minutes since you opened Stripe. If you completed checkout, the new balance should appear after a quick refresh.'
      : 'When you finish the ' + kindLabel + ' in your browser, return here and we will pick up the new balance automatically.';

    const wrap = el('div', { class: 'us-payment-banner us-payment-banner-' + variant });
    wrap.appendChild(el('div', { class: 'us-payment-banner-icon', html: icon }));
    const body2 = el('div', { class: 'us-payment-banner-body' }, [
      el('div', { class: 'us-payment-banner-title' }, title),
      el('div', { class: 'us-payment-banner-msg' }, body),
    ]);
    const actions = el('div', { class: 'us-payment-banner-actions' });
    if (!completed) {
      const refreshBtn = btn('Refresh balance', {
        kind: 'secondary',
        onclick: async () => {
          refreshBtn.disabled = true;
          try { await onRefresh(); } finally { refreshBtn.disabled = false; }
        },
      });
      actions.appendChild(refreshBtn);
    }
    if (likelyCanceled) {
      const retryBtn = btn('Start a new checkout', {
        kind: 'primary',
        onclick: () => {
          // Clear the marker so a fresh attempt starts with a new
          // baseline. The user uses the top-up form to open checkout again.
          clearPendingPayment();
          onDismiss();
          // Scroll to the topup section so they see the button.
          const topupSection = document.querySelector('.us-panel[data-us-panel="billing"] .us-section');
          if (topupSection && typeof topupSection.scrollIntoView === 'function') {
            try { topupSection.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (_) {}
          }
        },
      });
      actions.appendChild(retryBtn);
    }
    const dismissBtn = btn(completed ? 'Got it' : 'Dismiss', {
      kind: completed ? 'primary' : 'ghost',
      onclick: () => { clearPendingPayment(); onDismiss(); },
    });
    actions.appendChild(dismissBtn);
    body2.appendChild(actions);
    wrap.appendChild(body2);
    return wrap;
  }

  async function renderBilling(panel) {
    panel.innerHTML = '';
    panel.appendChild(emptyState('Loading billing…'));
    const enabled = cache.billingEnabled || await api.getBillingEnabled().catch(() => ({ billing_enabled: false }));
    cache.billingEnabled = enabled;
    if (!enabled || !enabled.billing_enabled) {
      panel.innerHTML = '';
      panel.appendChild(section('Billing', null, [el('p', { class: 'us-hint' }, 'Billing is disabled for this deployment.')]));
      return;
    }
    const settings = await loadDesktopSettings(true);
    let user = null;
    let userLoadError = null;
    try { user = await loadUser(); } catch (err) {
      userLoadError = err;
    }

    let activeCompany = null;
    let paymentOnly = false;
    if (user && user.companies && user.companies.length) {
      // Pick the active / primary company. The user can switch via the topbar
      // selector before opening this panel.
      activeCompany = (settings && settings.company_id
        ? user.companies.find((c) => c.id === settings.company_id)
        : null) || user.companies.find((c) => c.primary) || user.companies[0];
    } else if (settings && settings.company_id) {
      paymentOnly = true;
      activeCompany = {
        id: settings.company_id,
        name: settings.company_name || 'this company',
      };
    }

    if (!activeCompany) {
      panel.innerHTML = '';
      panel.appendChild(userLoadError
        ? section('Billing', null, [el('p', { class: 'us-hint error' }, errMsg(userLoadError))])
        : emptyState('No companies on this account.'));
      return;
    }

    panel.innerHTML = '';
    if (!paymentOnly && !userCanAdminCompany(user, activeCompany.id)) {
      panel.appendChild(section('Billing', null, [
        el('p', { class: 'us-hint' },
          'You must be a company admin to view billing for ' + (activeCompany.name || 'this company') + '.'),
      ]));
      return;
    }

    const pricing = cache.pricingConfig || await api.getPricingConfig().catch(() => null);
    cache.pricingConfig = pricing;
    const appName = (pricing && (pricing.app_name || (pricing.app_names && pricing.app_names[0]))) || 'AGiXT';
    const isTokenBased = !pricing || pricing.pricing_model === 'per_token';
    const isSuperAdmin = userIsSuperAdmin(user);

    panel.appendChild(section('Billing for ' + (activeCompany.name || 'company'),
      paymentOnly
        ? 'Complete billing to activate your ' + appName + ' account.'
        : 'Manage your ' + appName + ' subscription, credits, and payment history.',
      [
        el('p', { class: 'us-hint' },
          'Pricing model: ' + (pricing ? pricing.pricing_model : 'unknown')),
      ]));

    // Pending payment banner — surfaces at the top of the panel so the
    // user knows we're tracking their Stripe handoff. We capture the
    // current balance here so the banner can detect completion.
    const pendingPayment = loadPendingPayment();
    let postPaymentBalance = null;

    // Token balance / plan summary.
    if (isTokenBased) {
      try {
        const balance = await api.getTokenBalance(activeCompany.id, true);
        postPaymentBalance = Number(balance.token_balance || 0);
        if (pendingPayment
            && pendingPayment.company_id === activeCompany.id) {
          panel.appendChild(renderPaymentReturnBanner(
            pendingPayment,
            postPaymentBalance,
            async () => renderBilling(panel),
            () => renderBilling(panel),
          ));
        }
        panel.appendChild(section('Credit balance', null, [
          el('dl', { class: 'us-kv-grid' }, [
            el('dt', null, 'Tokens remaining'), el('dd', null, formatTokens(balance.token_balance)),
            el('dt', null, 'USD value'), el('dd', null, formatUsd(balance.token_balance_usd)),
            el('dt', null, 'Tokens used'), el('dd', null, formatTokens(balance.tokens_used_total)),
          ]),
          balance.low_balance_warning ? el('p', { class: 'us-hint error' }, 'Low balance — top up below.') : null,
        ]));
      } catch (err) {
        panel.appendChild(section('Credit balance', null, [el('p', { class: 'us-hint error' }, errMsg(err))]));
      }
    } else {
      try {
        const limits = await api.getPlanLimits(activeCompany.id);
        const usage = limits.usage || {};
        const lim = limits.limits || {};
        // Plan-based pending payment banner uses tokens-this-period as
        // the baseline yardstick. It's less reliable than the token
        // balance (since the period ticks regardless), but combined
        // with elapsed time it still gives a usable signal.
        postPaymentBalance = Number(usage.tokens_this_period || usage.tokens_used_this_period || 0);
        if (pendingPayment && pendingPayment.company_id === activeCompany.id) {
          panel.appendChild(renderPaymentReturnBanner(
            pendingPayment,
            postPaymentBalance,
            async () => renderBilling(panel),
            () => renderBilling(panel),
          ));
        }
        panel.appendChild(section('Plan: ' + (limits.plan_name || limits.plan_id || 'unknown'), null, [
          el('dl', { class: 'us-kv-grid' }, [
            el('dt', null, 'Users'), el('dd', null, (usage.users || 0) + ' / ' + (lim.users || '∞')),
            el('dt', null, 'Devices'), el('dd', null, (usage.devices || 0) + ' / ' + (lim.devices || '∞')),
            el('dt', null, 'Tokens this period'),
            el('dd', null, formatTokens(usage.tokens_this_period || usage.tokens_used_this_period || 0) +
              ' / ' + formatTokens(lim.tokens_per_month || lim.monthly_tokens || 0)),
            el('dt', null, 'Storage'), el('dd', null, ((usage.storage_bytes || 0) / 1024 / 1024).toFixed(1) + ' MB'),
          ]),
        ]));
      } catch (err) {
        panel.appendChild(section('Plan limits', null, [el('p', { class: 'us-hint error' }, errMsg(err))]));
      }
    }

    // Topup / change plan.
    if (isTokenBased) {
      const topupAmount = el('input', { class: 'us-input', type: 'number', min: 1, value: 10, placeholder: 'Token millions' });
      const topupStatus = el('span', { class: 'us-status-line' }, '');
      const topupBtn = btn('Top up with Stripe', { kind: 'primary', onclick: async () => {
        const millions = Number(topupAmount.value) || 0;
        if (millions < 1) { topupStatus.textContent = 'Enter at least 1 (million tokens).'; topupStatus.className = 'us-status-line error'; return; }
        topupBtn.disabled = true;
        try {
          const res = await api.createTokenTopupStripe({ token_millions: millions, company_id: activeCompany.id });
          if (res && (res.checkout_url || res.url)) {
            // Stash a pending-payment marker with the current token
            // balance as baseline. When the user comes back, the
            // banner compares balance against this baseline to decide
            // whether the topup landed.
            savePendingPayment({
              kind: 'topup',
              company_id: activeCompany.id,
              token_millions: millions,
              baseline_balance_tokens: postPaymentBalance,
            });
            openExternal(res.checkout_url || res.url);
            topupStatus.textContent = 'Opened Stripe checkout in your browser. We will pick up the new balance when you return.';
            topupStatus.className = 'us-status-line success';
          } else if (res && res.client_secret) {
            topupStatus.textContent = 'Stripe payment intent created. Complete in the web app.';
            topupStatus.className = 'us-status-line';
          }
        } catch (err) {
          topupStatus.textContent = errMsg(err); topupStatus.className = 'us-status-line error';
        } finally { topupBtn.disabled = false; }
      } });
      panel.appendChild(section('Top up tokens',
        'Buy additional credits via Stripe. Opens checkout in your browser.',
        [
          el('div', { class: 'us-section-row' }, [topupAmount, topupBtn]),
          topupStatus,
        ]));
    } else {
      const planTopupAmount = el('input', { class: 'us-input', type: 'number', min: 1, value: 1, placeholder: 'Million tokens' });
      const planTopupStatus = el('span', { class: 'us-status-line' }, '');
      const planTopupBtn = btn('Buy token top-up', { kind: 'primary', onclick: async () => {
        try {
          const res = await api.createPlanTopup({ company_id: activeCompany.id, token_millions: Number(planTopupAmount.value) || 1 });
          if (res && res.checkout_url) {
            savePendingPayment({
              kind: 'topup',
              company_id: activeCompany.id,
              token_millions: Number(planTopupAmount.value) || 1,
              baseline_balance_tokens: postPaymentBalance,
            });
            openExternal(res.checkout_url);
            planTopupStatus.textContent = 'Stripe checkout opened. Return here when you finish — we will refresh the balance.';
            planTopupStatus.className = 'us-status-line success';
          }
        } catch (err) { planTopupStatus.textContent = errMsg(err); planTopupStatus.className = 'us-status-line error'; }
      } });
      panel.appendChild(section('Token top-ups (one-time)', null, [
        el('div', { class: 'us-section-row' }, [planTopupAmount, planTopupBtn]),
        planTopupStatus,
      ]));
      // Plan changes — link to web for the full picker.
      if (pricing && Array.isArray(pricing.tiers) && pricing.tiers.length) {
        const tierSelect = el('select', { class: 'us-select' }, pricing.tiers.map((t) =>
          el('option', { value: t.id }, t.name + (t.price ? ' — $' + t.price : ''))));
        const changePlanStatus = el('span', { class: 'us-status-line' }, '');
        const changePlanBtn = btn(isSuperAdmin ? 'Set plan' : 'Change plan', { kind: 'primary', onclick: async () => {
          changePlanBtn.disabled = true;
          try {
            if (isSuperAdmin && typeof api.adminSetCompanyPlan === 'function') {
              const res = await api.adminSetCompanyPlan(activeCompany.id, tierSelect.value);
              changePlanStatus.textContent = (res && res.message) || 'Plan updated.';
              changePlanStatus.className = 'us-status-line success';
              cache.planLimits = null;
              await renderBilling(panel);
              return;
            }
            const res = await api.createPlanCheckout({ company_id: activeCompany.id, plan_id: tierSelect.value });
            if (res && res.checkout_url) {
              savePendingPayment({
                kind: 'plan',
                company_id: activeCompany.id,
                plan_id: tierSelect.value,
                baseline_balance_tokens: postPaymentBalance,
              });
              openExternal(res.checkout_url);
              changePlanStatus.textContent = 'Stripe checkout opened. Return here to confirm the subscription change.';
              changePlanStatus.className = 'us-status-line success';
            }
          } catch (err) { changePlanStatus.textContent = errMsg(err); changePlanStatus.className = 'us-status-line error'; }
          finally { changePlanBtn.disabled = false; }
        } });
        panel.appendChild(section('Change plan', null, [
          el('div', { class: 'us-section-row' }, [tierSelect, changePlanBtn]),
          changePlanStatus,
        ]));
      }
    }

    // Billing history.
    try {
      const txns = await api.listBillingTransactions();
      const items = Array.isArray(txns) ? txns : (txns && txns.transactions) || [];
      if (items.length) {
        const list = el('div', { class: 'us-row-list' });
        items.slice(0, 25).forEach((t) => {
          list.appendChild(el('div', { class: 'us-list-item' }, [
            el('div', { class: 'us-list-item-grow' }, [
              el('p', { class: 'us-list-item-title' }, formatUsd(t.amount_usd) + ' · ' + (t.currency || 'USD')),
              el('p', { class: 'us-list-item-meta' }, formatDate(t.created_at) + ' · ' + (t.status || '—') +
                (t.token_amount ? ' · ' + formatTokens(t.token_amount) + ' tokens' : '')),
            ]),
            t.status ? badge(t.status, t.status === 'completed' ? 'success' : 'warn') : null,
          ]));
        });
        panel.appendChild(section('Billing history', null, [list]));
      } else {
        panel.appendChild(section('Billing history', null, [emptyState('No transactions yet.')]));
      }
    } catch (err) {
      panel.appendChild(section('Billing history', null, [el('p', { class: 'us-hint error' }, errMsg(err))]));
    }
  }

  // ─── Companies tab ───────────────────────────────────────────────────

  /** Build a tiny labeled-field DOM that mirrors the web app's edit
   *  company dialog. `opts.type` can be 'text' (default), 'email', 'url',
   *  'tel', or 'textarea'. */
  function modalField(labelText, opts) {
    opts = opts || {};
    const isArea = opts.type === 'textarea';
    const input = el(isArea ? 'textarea' : 'input', {
      class: isArea ? 'us-textarea' : 'us-input',
      type: isArea ? undefined : (opts.type || 'text'),
      placeholder: opts.placeholder || '',
      value: opts.value != null ? opts.value : '',
    });
    if (isArea && opts.rows) input.rows = opts.rows;
    const wrap = el('label', { class: 'us-label' }, [
      el('span', { class: 'us-label-text' }, labelText),
      input,
    ]);
    return { wrap, input };
  }

  /** Open the company create/edit dialog. Mirrors the web app's edit
   *  modal — name, status, contact info, address, notes — and also
   *  supports `parent_company_id` on create (the backend's POST accepts
   *  it; PATCH does not, so the field is hidden on edit). Pass
   *  `{ mode: 'create' }` for a new company, or omit `mode` for edit. */
  function openCompanyDialog(opts) {
    opts = opts || {};
    const mode = opts.mode === 'create' ? 'create' : 'edit';
    const company = opts.company || {};
    const allCompanies = opts.allCompanies || [];

    const name = modalField('Company name *', { value: company.name, placeholder: 'Enter company name' });
    const status = el('select', { class: 'us-select' }, [
      el('option', { value: 'active' }, 'Active'),
      el('option', { value: 'inactive' }, 'Inactive'),
    ]);
    status.value = (company.status === false ? 'inactive' : 'active');
    const statusWrap = el('label', { class: 'us-label' }, [
      el('span', { class: 'us-label-text' }, 'Status'), status,
    ]);
    const email = modalField('Email', { type: 'email', value: company.email || '', placeholder: 'company@example.com' });
    const phone = modalField('Phone', { type: 'tel', value: company.phone_number || '', placeholder: '+1 (555) 123-4567' });
    const website = modalField('Website', { type: 'url', value: company.website || '', placeholder: 'https://company.com' });
    const address = modalField('Street address', { value: company.address || '', placeholder: '123 Main Street' });
    const city = modalField('City', { value: company.city || '', placeholder: 'New York' });
    const state = modalField('State/Province', { value: company.state || '', placeholder: 'NY' });
    const zip = modalField('ZIP/Postal code', { value: company.zip_code || '', placeholder: '10001' });
    const country = modalField('Country', { value: company.country || '', placeholder: 'United States' });

    // Parent company picker — only available on create (PATCH /v1/companies
    // doesn't accept parent_company_id; POST does).
    let parentWrap = null;
    let parentSelect = null;
    if (mode === 'create' && allCompanies.length) {
      parentSelect = el('select', { class: 'us-select' });
      parentSelect.appendChild(el('option', { value: '' }, 'None (top-level company)'));
      allCompanies.forEach((c) => {
        if (!c) return;
        parentSelect.appendChild(el('option', { value: c.id }, c.name || 'Untitled'));
      });
      parentWrap = el('label', { class: 'us-label' }, [
        el('span', { class: 'us-label-text' }, 'Parent company'), parentSelect,
      ]);
    }

    const notes = modalField('Notes', { type: 'textarea', value: company.notes || '', placeholder: 'Additional notes about this company…', rows: 3 });

    const submitLabel = mode === 'create' ? 'Create company' : 'Save changes';
    const submitBtn = btn(submitLabel, { kind: 'primary' });
    const cancelBtn = btn('Cancel');

    const handle = openModal({
      title: mode === 'create' ? 'Create company' : 'Edit company',
      description: mode === 'create'
        ? 'Spin up a new company. All fields except name are optional and can be edited later.'
        : 'Update company information and settings for ' + (company.name || ''),
      wide: true,
      body: [
        el('div', { class: 'us-grid-2' }, [name.wrap, statusWrap]),
        el('div', { class: 'us-grid-2' }, [email.wrap, phone.wrap]),
        website.wrap,
        address.wrap,
        el('div', { class: 'us-grid-2' }, [city.wrap, state.wrap]),
        el('div', { class: 'us-grid-2' }, [zip.wrap, country.wrap]),
        parentWrap,
        notes.wrap,
      ].filter(Boolean),
      footer: [cancelBtn, submitBtn],
    });

    cancelBtn.addEventListener('click', () => handle.close());
    submitBtn.addEventListener('click', async () => {
      const finalName = name.input.value.trim();
      if (!finalName) { toast('Name is required', 'error'); name.input.focus(); return; }
      const payload = {
        name: finalName,
        status: status.value === 'active',
        address: address.input.value.trim() || null,
        phone_number: phone.input.value.trim() || null,
        email: email.input.value.trim() || null,
        website: website.input.value.trim() || null,
        city: city.input.value.trim() || null,
        state: state.input.value.trim() || null,
        zip_code: zip.input.value.trim() || null,
        country: country.input.value.trim() || null,
        notes: notes.input.value.trim() || null,
      };
      if (mode === 'create' && parentSelect && parentSelect.value) {
        payload.parent_company_id = parentSelect.value;
      }
      submitBtn.disabled = true;
      try {
        if (mode === 'create') {
          await api.createCompany(payload);
          toast('Company created', 'success');
        } else {
          await api.updateCompany(company.id, payload);
          toast('Company updated', 'success');
        }
        handle.close();
        if (typeof opts.onSaved === 'function') opts.onSaved();
      } catch (err) {
        toast(friendlyError(err), 'error');
        submitBtn.disabled = false;
      }
    });
    setupModalFocus(handle);
  }

  function openEditCompanyDialog(company, allCompanies, onSaved) {
    openCompanyDialog({ mode: 'edit', company, allCompanies, onSaved });
  }
  function openCreateCompanyDialog(allCompanies, onSaved) {
    openCompanyDialog({ mode: 'create', allCompanies, onSaved });
  }

  async function renderCompanies(panel) {
    panel.innerHTML = '';
    panel.appendChild(emptyState('Loading companies…'));
    let user;
    try { user = await loadUser(true); } catch (err) {
      panel.innerHTML = '';
      panel.appendChild(section('Companies', null, [el('p', { class: 'us-hint error' }, friendlyError(err))]));
      return;
    }
    if (!user || !user.companies || !user.companies.length) {
      panel.innerHTML = '';
      panel.appendChild(emptyState('No companies on this account yet.'));
      return;
    }
    panel.innerHTML = '';

    // Create — opens the full company form so the user can set address /
    // contact info / parent up-front instead of editing right after.
    const createBtn = btn('Create company…', { kind: 'primary', onclick: () =>
      openCreateCompanyDialog(user.companies, () => {
        cache.user = null;
        renderCompanies(panel);
      }),
    });
    panel.appendChild(section('Create a company',
      'Add a new company to this account. All fields except the name are optional.',
      [el('div', { class: 'us-section-row' }, [createBtn])]));

    // Existing companies.
    const list = el('div', { class: 'us-row-list' });
    user.companies.forEach((c) => {
      const isAdmin = isAdminLikeRole(c.role_id);
      const editBtn = btn('Edit', { onclick: () => openEditCompanyDialog(c, user.companies, () => {
        cache.user = null;
        renderCompanies(panel);
      }) });
      const deleteBtn = btn('Delete', { kind: 'danger', onclick: async () => {
        const ok = await confirmDialog({
          title: 'Delete company',
          message: 'Delete "' + (c.name || 'this company') + '"? This permanently removes all members, data, and billing history. This cannot be undone.',
          confirmLabel: 'Delete forever',
          destructive: true,
        });
        if (!ok) return;
        try {
          await api.deleteCompany(c.id);
          cache.user = null;
          toast('Company deleted', 'success');
          renderCompanies(panel);
        } catch (err) { toast(friendlyError(err), 'error'); }
      } });
      const actions = isAdmin
        ? el('div', { class: 'us-row-actions' }, [editBtn, deleteBtn])
        : null;
      const addrLine = [c.address, c.city, c.state, c.zip_code, c.country].filter(Boolean).join(', ');
      const contactLine = [c.phone_number, c.email, c.website].filter(Boolean).join(' · ');
      list.appendChild(el('div', { class: 'us-list-item' }, [
        el('div', { class: 'us-list-item-grow' }, [
          el('p', { class: 'us-list-item-title' }, [
            c.name || 'Untitled', ' ',
            c.primary ? badge('Primary', 'primary') : null,
            ' ',
            badge('Role: ' + (c.role || 'member')),
            c.status === false ? [' ', badge('Inactive', 'warn')] : null,
          ].flat().filter(Boolean)),
          addrLine ? el('p', { class: 'us-list-item-meta' }, addrLine) : null,
          contactLine ? el('p', { class: 'us-list-item-meta' }, contactLine) : null,
        ].filter(Boolean)),
        actions,
      ]));
    });
    panel.appendChild(section('Your companies', null, [list]));
  }

  // ─── Teams tab — company-scoped member management ───────────────────

  /** Roles the desktop allows assigning at invite time / role change.
   *  Mirrors the web app's ASSIGNABLE_DEFAULT_ROLE_IDS — keeps super admin
   *  (0), tenant admin (1), and child (4) off the picker. */
  const ASSIGNABLE_ROLE_IDS = [2, 3, 5, 6];
  /** Fallback labels for when /v1/default-roles isn't reachable. */
  const FALLBACK_DEFAULT_ROLES = [
    { id: 2, friendly_name: 'Admin' },
    { id: 3, friendly_name: 'User' },
    { id: 5, friendly_name: 'Chat User' },
    { id: 6, friendly_name: 'Read Only' },
  ];

  function roleNameLookup(defaultRoles) {
    const map = {};
    (Array.isArray(defaultRoles) ? defaultRoles : []).forEach((r) => {
      if (r && typeof r.id !== 'undefined') {
        map[r.id] = r.friendly_name || r.name || ('Role ' + r.id);
      }
    });
    // Guarantee labels for any role id the server may surface, including
    // tenant admin / super admin / child even though they're not assignable.
    [
      [0, 'Tenant Admin'], [1, 'Tenant Admin'], [2, 'Admin'],
      [3, 'User'], [4, 'Child'], [5, 'Chat User'], [6, 'Read Only'],
    ].forEach(([id, name]) => { if (map[id] == null) map[id] = name; });
    return map;
  }

  async function renderTeams(panel) {
    panel.innerHTML = '';
    panel.appendChild(emptyState('Loading team…'));
    let user;
    try { user = await loadUser(); } catch (err) {
      panel.innerHTML = '';
      panel.appendChild(section('Teams', null, [el('p', { class: 'us-hint error' }, friendlyError(err))]));
      return;
    }
    if (!user || !user.companies || !user.companies.length) {
      panel.innerHTML = '';
      panel.appendChild(emptyState('No companies on this account yet.'));
      return;
    }
    panel.innerHTML = '';

    const settings = await loadDesktopSettings();
    let activeCompanyId = (settings && settings.company_id) || (user.companies.find((c) => c.primary) || user.companies[0]).id;
    // Search filter survives panel refreshes so the user doesn't lose
    // their query when they change a role / remove a member, etc.
    let memberFilter = '';
    const select = el('select', { class: 'us-select' }, user.companies.map((c) => {
      const opt = el('option', { value: c.id }, c.name + (c.primary ? ' (primary)' : ''));
      return opt;
    }));
    select.value = activeCompanyId;
    const body = el('div');

    // Top action row: company selector + management buttons (invite, manage
    // custom roles). Both buttons are gated on the user being an admin of
    // the selected company; they update via `syncTopRowControls` below.
    const inviteUsersBtn = btn('Invite users…', { kind: 'primary' });
    const manageRolesBtn = btn('Manage custom roles…');
    function syncTopRowControls() {
      const company = user.companies.find((c) => c.id === activeCompanyId);
      const isAdmin = company && isAdminLikeRole(company.role_id);
      inviteUsersBtn.disabled = !isAdmin;
      manageRolesBtn.disabled = !isAdmin;
    }
    select.addEventListener('change', async () => {
      activeCompanyId = select.value;
      memberFilter = '';
      syncTopRowControls();
      await refreshBody();
    });

    inviteUsersBtn.addEventListener('click', () => openInviteDialog(activeCompanyId, user, refreshBody));
    manageRolesBtn.addEventListener('click', () => openCustomRolesDialog(activeCompanyId, refreshBody));

    panel.appendChild(section('Active company', null, [
      el('div', { class: 'us-section-row' }, [select]),
      el('div', { class: 'us-section-row' }, [inviteUsersBtn, manageRolesBtn]),
    ]));
    panel.appendChild(body);
    syncTopRowControls();

    async function refreshBody() {
      body.innerHTML = '';
      const company = user.companies.find((c) => c.id === activeCompanyId);
      if (!company) return;
      if (!isAdminLikeRole(company.role_id)) {
        body.appendChild(section('Team', null, [
          el('p', { class: 'us-hint' }, 'You must be a company admin to manage members of ' + company.name + '.'),
        ]));
        return;
      }
      body.appendChild(emptyState('Loading members…'));
      let members, invitations, defaultRoles, customRoles;
      try {
        [members, invitations, defaultRoles, customRoles] = await Promise.all([
          api.getCompanyMembers(activeCompanyId),
          api.getInvitations(activeCompanyId).catch(() => []),
          (cache.defaultRoles ? Promise.resolve(cache.defaultRoles) : api.listDefaultRoles()).catch(() => []),
          api.listCustomRoles(activeCompanyId).catch(() => []),
        ]);
        cache.defaultRoles = defaultRoles;
      } catch (err) {
        body.innerHTML = '';
        body.appendChild(section('Team', null, [el('p', { class: 'us-hint error' }, friendlyError(err))]));
        return;
      }
      body.innerHTML = '';

      const roleNames = roleNameLookup(defaultRoles);
      const customRoleList = Array.isArray(customRoles) ? customRoles : [];
      const customRoleById = {};
      customRoleList.forEach((r) => { if (r && r.id) customRoleById[r.id] = r; });

      // Members are fetched separately from each user's custom-role assignments
      // so we hydrate them in a single batch — failure on any one user
      // shouldn't block the rest from rendering.
      const customRolesPerUser = {};
      await Promise.all((members || []).map(async (m) => {
        try {
          const list = await api.getUserCustomRoles(m.id, activeCompanyId);
          customRolesPerUser[m.id] = Array.isArray(list) ? list : [];
        } catch (_) { customRolesPerUser[m.id] = []; }
      }));

      const teamCtx = {
        company,
        companyId: activeCompanyId,
        user,
        members: members || [],
        invitations: invitations || [],
        defaultRoles,
        roleNames,
        customRoleList,
        customRoleById,
        customRolesPerUser,
        refreshBody,
      };

      const inviteSection = buildInvitationsSection(teamCtx);
      if (inviteSection) body.appendChild(inviteSection);
      body.appendChild(buildMembersSection(teamCtx, {
        initialFilter: memberFilter,
        onFilterChange: (next) => { memberFilter = next; },
      }));
    }

    refreshBody();
  }

  /** Render the pending-invitations section. Returns null when there are
   *  no invitations so the caller can skip mounting the section entirely. */
  function buildInvitationsSection(ctx) {
    if (!ctx.invitations || !ctx.invitations.length) return null;
    const list = el('div', { class: 'us-row-list' });
    ctx.invitations.forEach((inv) => list.appendChild(buildInvitationRow(inv, ctx)));
    return section('Pending invitations (' + ctx.invitations.length + ')', null, [list]);
  }

  function buildInvitationRow(inv, ctx) {
    const roleLabel = ctx.roleNames[inv.role_id]
      || inv.role
      || ('Role ' + (inv.role_id != null ? inv.role_id : '—'));
    const inviteLink = inv.invitation_link
      || buildInviteLink(inv.id, inv.email || inv.invitee_email);
    const statusBadge = inv.is_accepted
      ? badge('Accepted', 'success')
      : badge('Pending', 'warn');
    const actions = el('div', { class: 'us-row-actions' });
    if (inviteLink) {
      actions.appendChild(btn('Copy link', { onclick: () => {
        copyToClipboard(inviteLink);
        toast('Invite link copied', 'success');
      } }));
    }
    if (!inv.is_accepted) {
      actions.appendChild(btn('Cancel', { kind: 'danger', onclick: async () => {
        const ok = await confirmDialog({
          title: 'Cancel invitation',
          message: 'Cancel the invitation to ' + (inv.email || inv.invitee_email || '?') + '?',
          confirmLabel: 'Cancel invitation',
          cancelLabel: 'Keep',
          destructive: true,
        });
        if (!ok) return;
        try { await api.deleteInvitation(inv.id); toast('Invite cancelled', 'success'); ctx.refreshBody(); }
        catch (err) { toast(friendlyError(err), 'error'); }
      } }));
    }
    return el('div', { class: 'us-list-item' }, [
      el('div', { class: 'us-list-item-grow' }, [
        el('p', { class: 'us-list-item-title' }, [
          inv.email || inv.invitee_email || '—', ' ', statusBadge,
        ]),
        el('p', { class: 'us-list-item-meta' },
          'Role: ' + roleLabel +
          (inv.created_at ? ' · invited ' + formatDate(inv.created_at) : '')),
      ]),
      actions,
    ]);
  }

  /** Render the members section, including the filter bar, role-distribution
   *  pills, sticky bulk-action bar, and member rows. */
  function buildMembersSection(ctx, opts) {
    opts = opts || {};
    const selectedIds = new Set();
    const bulkBar = el('div', { class: 'us-bulk-bar', hidden: true });
    const memberCount = ctx.members.length;

    const exportAllBtn = btn('Export CSV', {
      onclick: () => exportMembersCsv(ctx.members, ctx.roleNames, ctx.company.name),
    });
    exportAllBtn.disabled = memberCount === 0;

    // Role distribution pills — quick at-a-glance team composition.
    const roleCounts = {};
    ctx.members.forEach((m) => {
      roleCounts[m.role_id] = (roleCounts[m.role_id] || 0) + 1;
    });
    const statPills = el('div', { class: 'us-stat-pills' },
      Object.keys(roleCounts).map((id) => {
        const label = ctx.roleNames[id] || ('Role ' + id);
        return el('span', { class: 'us-stat-pill' }, roleCounts[id] + ' · ' + label);
      }),
    );

    const headerRow = el('div', { class: 'us-section-row between' }, [
      el('h2', { class: 'us-section-title' },
        'Members of ' + ctx.company.name + ' (' + memberCount + ')'),
      exportAllBtn,
    ]);
    const memberSection = el('section', { class: 'us-section' }, [headerRow]);
    if (statPills.children.length) memberSection.appendChild(statPills);

    // Search input — filters by first/last name or email. Re-renders rows
    // in place; selection state is preserved across filter changes.
    const searchInput = el('input', {
      class: 'us-input', type: 'search',
      placeholder: 'Search members by name or email…',
      value: opts.initialFilter || '',
    });
    let filter = opts.initialFilter || '';
    searchInput.addEventListener('input', () => {
      filter = searchInput.value.trim().toLowerCase();
      if (typeof opts.onFilterChange === 'function') opts.onFilterChange(filter);
      renderRows();
    });
    if (memberCount) {
      memberSection.appendChild(el('div', { class: 'us-filter-bar' }, [searchInput]));
    }

    const memberList = el('div', { class: 'us-row-list' });

    function rebuildBulkBar() {
      bulkBar.innerHTML = '';
      bulkBar.hidden = selectedIds.size === 0;
      if (selectedIds.size === 0) return;
      bulkBar.appendChild(el('span', { class: 'us-bulk-bar-count' },
        selectedIds.size + ' selected'));
      ASSIGNABLE_ROLE_IDS.forEach((id) => {
        const label = ctx.roleNames[id] || ('Role ' + id);
        bulkBar.appendChild(btn('Set: ' + label, { onclick: async () => {
          await bulkSetRole(Array.from(selectedIds), id, ctx);
          selectedIds.clear();
          ctx.refreshBody();
        } }));
      });
      bulkBar.appendChild(btn('Export selected', { onclick: () => {
        const subset = ctx.members.filter((m) => selectedIds.has(m.id));
        exportMembersCsv(subset, ctx.roleNames, ctx.company.name);
      } }));
      bulkBar.appendChild(btn('Remove selected', { kind: 'danger', onclick: async () => {
        const ok = await confirmDialog({
          title: 'Remove members',
          message: 'Remove ' + selectedIds.size + ' member(s) from ' + ctx.company.name + '? They’ll lose access immediately.',
          confirmLabel: 'Remove',
          destructive: true,
        });
        if (!ok) return;
        await bulkRemoveMembers(Array.from(selectedIds), ctx);
        selectedIds.clear();
        ctx.refreshBody();
      } }));
    }
    memberSection.appendChild(bulkBar);
    memberSection.appendChild(memberList);

    function renderRows() {
      memberList.innerHTML = '';
      if (!memberCount) {
        memberList.appendChild(emptyState('No members yet.'));
        return;
      }
      const filtered = filter
        ? ctx.members.filter((m) => memberMatchesFilter(m, filter))
        : ctx.members;
      if (!filtered.length) {
        memberList.appendChild(emptyState('No members match "' + filter + '".'));
        return;
      }
      filtered.forEach((m) => {
        memberList.appendChild(buildMemberRow(m, ctx, {
          selectedIds, rebuildBulkBar,
        }));
      });
    }
    renderRows();
    return memberSection;
  }

  function memberMatchesFilter(m, filter) {
    if (!filter) return true;
    const hay = ((m.first_name || '') + ' ' + (m.last_name || '') + ' ' + (m.email || ''))
      .toLowerCase();
    return hay.includes(filter);
  }

  function buildMemberRow(m, ctx, rowCtx) {
    const isProtected = m.role_id === 0 || m.role_id === 1 || m.role_id === 4;
    const isSelf = m.id === ctx.user.id;
    const canSelect = !isProtected && !isSelf;

    const checkbox = el('input', { type: 'checkbox' });
    checkbox.disabled = !canSelect;
    if (rowCtx.selectedIds.has(m.id)) checkbox.checked = true;

    const row = el('div', { class: 'us-list-item' });
    if (checkbox.checked) row.classList.add('is-selected');
    checkbox.addEventListener('change', () => {
      if (checkbox.checked) rowCtx.selectedIds.add(m.id);
      else rowCtx.selectedIds.delete(m.id);
      row.classList.toggle('is-selected', checkbox.checked);
      rowCtx.rebuildBulkBar();
    });

    const roleSelect = el('select', { class: 'us-select' });
    const roleOptions = (Array.isArray(ctx.defaultRoles) && ctx.defaultRoles.length
      ? ctx.defaultRoles.filter((r) => ASSIGNABLE_ROLE_IDS.includes(r.id))
      : FALLBACK_DEFAULT_ROLES);
    roleOptions.forEach((r) => roleSelect.appendChild(
      el('option', { value: r.id }, r.friendly_name || r.name)));
    if (isProtected && !roleOptions.find((r) => r.id === m.role_id)) {
      roleSelect.appendChild(el('option', { value: m.role_id },
        ctx.roleNames[m.role_id] || m.role || ('Role ' + m.role_id)));
    }
    roleSelect.value = String(m.role_id);
    roleSelect.disabled = isProtected;
    roleSelect.addEventListener('change', async () => {
      const next = Number(roleSelect.value);
      if (next === m.role_id) return;
      try {
        await api.updateMemberRole(ctx.companyId, m.id, next);
        toast('Role updated', 'success');
        ctx.refreshBody();
      } catch (err) { toast(friendlyError(err), 'error'); roleSelect.value = String(m.role_id); }
    });

    // Custom-role chips per member, with a "+ Custom role" button to open
    // the assignment picker. Empty list collapses to just the add button.
    const memberCustomRoles = ctx.customRolesPerUser[m.id] || [];
    const chipRow = el('div', { class: 'us-list-item-meta' });
    memberCustomRoles.forEach((assignment) => {
      const role = assignment.custom_role
        || ctx.customRoleById[assignment.custom_role_id]
        || null;
      const customRoleId = (role && role.id) || assignment.custom_role_id;
      const label = (role && (role.friendly_name || role.name)) || 'Custom role';
      chipRow.appendChild(el('span', { class: 'us-custom-role-chip' }, [
        label,
        el('button', { type: 'button', title: 'Remove role',
          onclick: async () => {
            if (!customRoleId) return;
            try {
              await api.removeUserCustomRole(ctx.companyId, m.id, customRoleId);
              toast('Custom role removed', 'success');
              ctx.refreshBody();
            } catch (err) { toast(friendlyError(err), 'error'); }
          } }, '×'),
      ]));
    });
    if (ctx.customRoleList.length) {
      chipRow.appendChild(el('button', {
        type: 'button',
        class: 'us-chip-btn',
        onclick: () => openAssignCustomRolePicker(
          ctx.companyId, m, ctx.customRoleList, memberCustomRoles, ctx.refreshBody),
      }, '+ Custom role'));
    }

    const displayName = ((m.first_name || '') + ' ' + (m.last_name || '')).trim() || m.email;
    const detailsBtn = btn('Details', {
      onclick: () => openMemberDetailsDialog(m, ctx),
    });
    const removeBtn = !isProtected && !isSelf
      ? btn('Remove', { kind: 'danger', onclick: async () => {
          const ok = await confirmDialog({
            title: 'Remove member',
            message: 'Remove ' + (m.email || displayName) + ' from ' + ctx.company.name + '?',
            confirmLabel: 'Remove',
            destructive: true,
          });
          if (!ok) return;
          try { await api.removeCompanyMember(ctx.companyId, m.id); toast('Removed', 'success'); ctx.refreshBody(); }
          catch (err) { toast(friendlyError(err), 'error'); }
        } })
      : null;

    row.appendChild(checkbox);
    row.appendChild(el('div', { class: 'us-list-item-grow' }, [
      el('p', { class: 'us-list-item-title' }, [
        displayName, ' ',
        isProtected ? badge(ctx.roleNames[m.role_id] || m.role || 'system', 'warn') : null,
        isSelf ? badge('You', 'muted') : null,
      ].filter(Boolean)),
      el('p', { class: 'us-list-item-meta' }, m.email),
      chipRow.childNodes.length ? chipRow : null,
    ].filter(Boolean)));
    row.appendChild(el('div', { class: 'us-row-actions' }, [
      roleSelect, detailsBtn, removeBtn,
    ].filter(Boolean)));
    return row;
  }

  async function bulkSetRole(userIds, roleId, ctx) {
    const results = await Promise.allSettled(
      userIds.map((uid) => api.updateMemberRole(ctx.companyId, uid, roleId)),
    );
    const ok = results.filter((r) => r.status === 'fulfilled').length;
    const failed = results.length - ok;
    if (failed === 0) toast('Updated ' + ok + ' user(s)', 'success');
    else toast('Updated ' + ok + ', ' + failed + ' failed', failed === results.length ? 'error' : 'success');
  }

  async function bulkRemoveMembers(userIds, ctx) {
    const results = await Promise.allSettled(
      userIds.map((uid) => api.removeCompanyMember(ctx.companyId, uid)),
    );
    const ok = results.filter((r) => r.status === 'fulfilled').length;
    const failed = results.length - ok;
    if (failed === 0) toast('Removed ' + ok + ' user(s)', 'success');
    else toast('Removed ' + ok + ', ' + failed + ' failed', failed === results.length ? 'error' : 'success');
  }

  /** Build a CSV blob and trigger download. Mirrors the web app's bulk
   *  export action: First name, Last name, Email, Role. */
  function exportMembersCsv(members, roleNames, companyName) {
    if (!members || !members.length) { toast('Nothing to export', 'error'); return; }
    const escape = (v) => {
      const s = v == null ? '' : String(v);
      if (/[",\n]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
      return s;
    };
    const header = ['First name', 'Last name', 'Email', 'Role'].map(escape).join(',');
    const rows = members.map((m) => [
      m.first_name, m.last_name, m.email,
      (roleNames && roleNames[m.role_id]) || m.role || ('Role ' + m.role_id),
    ].map(escape).join(','));
    const csv = [header].concat(rows).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const safeName = (companyName || 'members').replace(/[^a-z0-9_-]+/gi, '_');
    a.download = safeName + '-members-' + new Date().toISOString().split('T')[0] + '.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast('Exported ' + members.length + ' member(s)', 'success');
  }

  /** Multi-email invite dialog. Mirrors the web's invite form: textarea
   *  parser that accepts comma/semicolon/whitespace-separated addresses,
   *  role picker (assignable defaults only), and a skip-email toggle that
   *  surfaces the resulting invitation link for each address. */
  function openInviteDialog(companyId, user, onSent) {
    const company = (user.companies || []).find((c) => c.id === companyId);
    const defaultRoles = cache.defaultRoles && cache.defaultRoles.length
      ? cache.defaultRoles
      : FALLBACK_DEFAULT_ROLES;
    const assignable = defaultRoles
      .filter((r) => ASSIGNABLE_ROLE_IDS.includes(r.id))
      .sort((a, b) => a.id - b.id);

    const emails = el('textarea', { class: 'us-textarea', rows: 4,
      placeholder: 'user1@example.com user2@example.com\nuser3@example.com' });
    const emailsWrap = el('label', { class: 'us-label' }, [
      el('span', { class: 'us-label-text' }, 'Email addresses'),
      emails,
      el('span', { class: 'us-hint' }, 'Separate with spaces, commas, or new lines'),
    ]);
    const roleSel = el('select', { class: 'us-select' });
    // `assignable` is already filtered via ASSIGNABLE_ROLE_IDS and falls
    // back to FALLBACK_DEFAULT_ROLES (which is hardcoded and never empty),
    // so we don't need a secondary "if children empty" fallback here.
    assignable.forEach((r) => roleSel.appendChild(
      el('option', { value: r.id }, r.friendly_name || r.name)));
    // Default to "User" (role_id=3) to match the web app's invite form.
    if (Array.from(roleSel.options).some((o) => o.value === '3')) roleSel.value = '3';
    const roleWrap = el('label', { class: 'us-label' }, [
      el('span', { class: 'us-label-text' }, 'Assign role'), roleSel,
    ]);

    const skipEmail = el('input', { type: 'checkbox' });
    const skipWrap = el('label', { class: 'us-check' }, [
      skipEmail,
      el('span', null, 'Create invite link only (don’t send email)'),
    ]);

    const resultsEl = el('div', { class: 'us-invite-results', hidden: true });
    const statusLine = el('p', { class: 'us-status-line' });

    const cancelBtn = btn('Close');
    const sendBtn = btn('Send invitations', { kind: 'primary' });

    // Live email-count preview on the button label so the user can see
    // how many addresses parsed cleanly before sending.
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
      description: 'Inviting to ' + (company ? company.name : 'company') +
        '. Multiple emails are sent in parallel.',
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
        statusLine.className = 'us-status-line error';
        emails.focus();
        return;
      }
      sendBtn.disabled = true;
      statusLine.textContent = 'Sending ' + list.length + ' invitation(s)…';
      statusLine.className = 'us-status-line';
      const results = await Promise.all(list.map(async (addr) => {
        try {
          const resp = await api.createInvitation({
            email: addr,
            company_id: companyId,
            role_id: Number(roleSel.value),
            skip_email: !!skipEmail.checked,
          });
          const id = resp && resp.id;
          const alreadyMember = id === 'none' || (resp && resp.is_accepted === true);
          const link = alreadyMember ? null : (resp && resp.invitation_link)
            || buildInviteLink(id, addr);
          return {
            email: addr,
            success: true,
            alreadyMember,
            message: alreadyMember
              ? 'User added to company (already registered)'
              : (skipEmail.checked ? 'Invite link created' : 'Invitation sent'),
            link,
          };
        } catch (err) {
          return {
            email: addr,
            success: false,
            status: err && err.status,
            message: friendlyError(err, 'inviting ' + addr),
          };
        }
      }));
      // Render result rows.
      resultsEl.hidden = false;
      results.forEach((r) => {
        const row = el('div', { class: 'us-invite-result ' + (r.success ? 'success' : 'error') });
        row.appendChild(el('div', { class: 'us-invite-result-head' }, [
          el('span', null, r.success ? '✓' : '✗'),
          el('strong', null, r.email),
        ]));
        if (r.link) {
          const a = el('a', { href: r.link, target: '_blank', rel: 'noopener noreferrer',
            onclick: (e) => { e.preventDefault(); openExternal(r.link); } }, r.link);
          row.appendChild(el('div', { class: 'us-invite-result-link' }, [
            a,
            btn('Copy', { onclick: () => { copyToClipboard(r.link); toast('Copied', 'success'); } }),
          ]));
        } else {
          row.appendChild(el('div', { class: 'us-invite-result-msg' + (r.success ? '' : ' error') },
            r.message));
        }
        resultsEl.appendChild(row);
      });
      const okCount = results.filter((r) => r.success).length;
      const failCount = results.length - okCount;
      const hitBillingLimit = results.some((r) => !r.success && r.status === 402);
      if (hitBillingLimit) {
        statusLine.textContent = 'User limit reached — upgrade your plan to invite more.';
        statusLine.className = 'us-status-line error';
      } else if (failCount === 0) {
        statusLine.textContent = 'Sent ' + okCount + ' invitation(s).';
        statusLine.className = 'us-status-line success';
        emails.value = '';
      } else if (okCount === 0) {
        statusLine.textContent = 'Failed to send ' + failCount + ' invitation(s).';
        statusLine.className = 'us-status-line error';
      } else {
        statusLine.textContent = 'Sent ' + okCount + ', ' + failCount + ' failed.';
        statusLine.className = 'us-status-line';
      }
      refreshSendLabel();
      if (typeof onSent === 'function') onSent();
    });
    setupModalFocus(handle);
  }

  /** Member details modal — mirrors the web app's /team/[id] page. Shows
   *  the user's full profile and lets the viewing admin change role and
   *  manage custom roles inline. Profile fields (first_name, last_name,
   *  email) are editable when viewing your own profile (calls PUT /v1/user);
   *  for other users they're read-only because the AGiXT API only allows
   *  self-edit. */
  function openMemberDetailsDialog(member, ctx) {
    const isSelf = member.id === ctx.user.id;
    const isProtected = member.role_id === 0 || member.role_id === 1 || member.role_id === 4;
    const displayName = ((member.first_name || '') + ' ' + (member.last_name || '')).trim()
      || member.email
      || 'Member';

    function staticField(label, value) {
      return el('div', { class: 'us-detail-field' }, [
        el('span', { class: 'us-detail-field-label' }, label),
        el('div', { class: 'us-detail-field-value readonly' }, value || 'Not provided'),
      ]);
    }
    function editableField(label, key, type) {
      const input = el('input', { class: 'us-input', type: type || 'text',
        value: member[key] || '' });
      return {
        wrap: el('div', { class: 'us-detail-field' }, [
          el('span', { class: 'us-detail-field-label' }, label),
          input,
        ]),
        input,
      };
    }

    // Profile fields: editable for self, read-only for others.
    let firstField, lastField, emailField;
    let profileBlock;
    if (isSelf) {
      firstField = editableField('First name', 'first_name');
      lastField = editableField('Last name', 'last_name');
      emailField = editableField('Email', 'email', 'email');
      profileBlock = el('div', { class: 'us-detail-grid' }, [
        firstField.wrap, lastField.wrap, emailField.wrap,
      ]);
    } else {
      profileBlock = el('div', { class: 'us-detail-grid' }, [
        staticField('First name', member.first_name),
        staticField('Last name', member.last_name),
        staticField('Email', member.email),
      ]);
    }

    // Role select — same rules as the inline picker on the members table.
    const roleSelect = el('select', { class: 'us-select' });
    const roleOptions = (Array.isArray(ctx.defaultRoles) && ctx.defaultRoles.length
      ? ctx.defaultRoles.filter((r) => ASSIGNABLE_ROLE_IDS.includes(r.id))
      : FALLBACK_DEFAULT_ROLES);
    roleOptions.forEach((r) => roleSelect.appendChild(
      el('option', { value: r.id }, r.friendly_name || r.name)));
    if (isProtected && !roleOptions.find((r) => r.id === member.role_id)) {
      roleSelect.appendChild(el('option', { value: member.role_id },
        ctx.roleNames[member.role_id] || member.role || ('Role ' + member.role_id)));
    }
    roleSelect.value = String(member.role_id);
    roleSelect.disabled = isProtected;
    roleSelect.addEventListener('change', async () => {
      const next = Number(roleSelect.value);
      if (next === member.role_id) return;
      try {
        await api.updateMemberRole(ctx.companyId, member.id, next);
        toast('Role updated', 'success');
        member.role_id = next;
        ctx.refreshBody();
      } catch (err) { toast(friendlyError(err), 'error'); roleSelect.value = String(member.role_id); }
    });
    const roleField = el('div', { class: 'us-detail-field' }, [
      el('span', { class: 'us-detail-field-label' }, 'Default role'),
      roleSelect,
    ]);
    const createdField = staticField('Joined',
      member.created_at ? formatDate(member.created_at) : 'Unknown');

    // Custom-role chips inside the modal so the admin can manage them
    // without backing out of the dialog.
    const memberCustomRoles = ctx.customRolesPerUser[member.id] || [];
    const chipBlock = el('div', { class: 'us-list-item-meta' });
    function renderChips() {
      chipBlock.innerHTML = '';
      memberCustomRoles.forEach((assignment) => {
        const role = assignment.custom_role
          || ctx.customRoleById[assignment.custom_role_id]
          || null;
        const customRoleId = (role && role.id) || assignment.custom_role_id;
        const label = (role && (role.friendly_name || role.name)) || 'Custom role';
        chipBlock.appendChild(el('span', { class: 'us-custom-role-chip' }, [
          label,
          el('button', { type: 'button', title: 'Remove role',
            onclick: async () => {
              if (!customRoleId) return;
              try {
                await api.removeUserCustomRole(ctx.companyId, member.id, customRoleId);
                toast('Custom role removed', 'success');
                const idx = memberCustomRoles.findIndex((a) =>
                  ((a.custom_role && a.custom_role.id) || a.custom_role_id) === customRoleId);
                if (idx >= 0) memberCustomRoles.splice(idx, 1);
                renderChips();
                ctx.refreshBody();
              } catch (err) { toast(friendlyError(err), 'error'); }
            } }, '×'),
        ]));
      });
      if (ctx.customRoleList.length) {
        chipBlock.appendChild(el('button', { type: 'button', class: 'us-chip-btn',
          onclick: () => openAssignCustomRolePicker(
            ctx.companyId, member, ctx.customRoleList, memberCustomRoles,
            () => { ctx.refreshBody(); handle.close(); }),
        }, '+ Custom role'));
      } else {
        chipBlock.appendChild(el('span', { class: 'us-hint' },
          'No custom roles defined. Open "Manage custom roles" to create one.'));
      }
    }
    const customRolesField = el('div', { class: 'us-detail-field' }, [
      el('span', { class: 'us-detail-field-label' }, 'Custom roles'),
      chipBlock,
    ]);

    const footer = [];
    let saveProfileBtn = null;
    if (isSelf) {
      saveProfileBtn = btn('Save profile', { kind: 'primary', onclick: async () => {
        const patch = {
          first_name: firstField.input.value.trim(),
          last_name: lastField.input.value.trim(),
          email: emailField.input.value.trim(),
        };
        saveProfileBtn.disabled = true;
        try {
          await api.updateUser(patch);
          cache.user = null;
          toast('Profile updated', 'success');
          ctx.refreshBody();
          handle.close();
        } catch (err) { toast(friendlyError(err), 'error'); saveProfileBtn.disabled = false; }
      } });
      footer.push(saveProfileBtn);
    }
    const closeBtn = btn('Close');
    footer.unshift(closeBtn);

    const handle = openModal({
      title: displayName,
      description: isSelf
        ? 'Edit your profile, default role, and custom roles.'
        : 'Profile fields can only be edited by the user themselves. You can change their role and custom roles below.',
      wide: true,
      body: [
        profileBlock,
        el('div', { class: 'us-detail-grid' }, [roleField, createdField]),
        customRolesField,
      ],
      footer,
    });
    closeBtn.addEventListener('click', () => handle.close());
    renderChips();
    setupModalFocus(handle, { focusSelector: isSelf ? 'input' : 'select' });
  }

  /** Picker for assigning a custom role to a user. */
  function openAssignCustomRolePicker(companyId, member, customRoles, alreadyAssigned, onChanged) {
    const assigned = new Set(
      (alreadyAssigned || [])
        .map((a) => (a.custom_role && a.custom_role.id) || a.custom_role_id)
        .filter(Boolean),
    );
    const available = customRoles.filter((r) => r.is_active !== false && !assigned.has(r.id));
    if (!available.length) {
      toast('No more custom roles available to assign', 'error');
      return;
    }
    const list = el('div', { class: 'us-row-list' });
    available.forEach((r) => {
      const assignBtn = btn('Assign', { kind: 'primary', onclick: async () => {
        assignBtn.disabled = true;
        try {
          await api.assignUserCustomRole(companyId, member.id, r.id);
          toast('Role assigned', 'success');
          handle.close();
          if (typeof onChanged === 'function') onChanged();
        } catch (err) { toast(friendlyError(err), 'error'); assignBtn.disabled = false; }
      } });
      list.appendChild(el('div', { class: 'us-role-card' }, [
        el('div', { class: 'us-role-card-grow' }, [
          el('p', { class: 'us-role-card-title' }, r.friendly_name || r.name),
          r.description ? el('p', { class: 'us-role-card-desc' }, r.description) : null,
          el('p', { class: 'us-role-card-desc' }, (r.scopes ? r.scopes.length : 0) + ' permission(s)'),
        ].filter(Boolean)),
        el('div', { class: 'us-role-card-actions' }, [assignBtn]),
      ]));
    });
    const closeBtn = btn('Close');
    const handle = openModal({
      title: 'Assign custom role',
      description: 'Assign a custom role to ' + (member.email || member.id),
      body: [list],
      footer: [closeBtn],
    });
    closeBtn.addEventListener('click', () => handle.close());
    setupModalFocus(handle, { focusSelector: '.btn-primary' });
  }

  /** Manage custom roles for a company — list/create/edit/delete. Scope
   *  selection is grouped by category and pre-filtered to what the caller
   *  is allowed to grant (the backend rejects privilege escalation). */
  async function openCustomRolesDialog(companyId, onChanged) {
    const listEl = el('div', { class: 'us-row-list' });
    listEl.appendChild(emptyState('Loading roles…'));
    const createBtn = btn('Create custom role', { kind: 'primary' });
    const closeBtn = btn('Close');
    const handle = openModal({
      title: 'Custom roles',
      description: 'Custom roles let you bundle scopes into reusable permission sets, then assign them to users on top of their default role.',
      wide: true,
      body: [el('div', { class: 'us-section-row end' }, [createBtn]), listEl],
      footer: [closeBtn],
    });
    closeBtn.addEventListener('click', () => handle.close());

    let scopesCache = null;
    async function loadScopes() {
      if (!scopesCache) {
        try { scopesCache = await api.listScopes(); }
        catch (_) { scopesCache = []; }
      }
      return scopesCache;
    }

    async function refresh() {
      listEl.innerHTML = '';
      listEl.appendChild(emptyState('Loading roles…'));
      let roles;
      try { roles = await api.listCustomRoles(companyId); }
      catch (err) {
        listEl.innerHTML = '';
        listEl.appendChild(el('p', { class: 'us-hint error' }, friendlyError(err)));
        return;
      }
      listEl.innerHTML = '';
      if (!roles || !roles.length) {
        listEl.appendChild(emptyState('No custom roles yet. Click "Create custom role" to add one.'));
        return;
      }
      roles.forEach((r) => {
        const editBtn = btn('Edit', { onclick: async () =>
          openRoleEditor(companyId, r, await loadScopes(), async () => { await refresh(); if (onChanged) onChanged(); }) });
        const delBtn = btn('Delete', { kind: 'danger', onclick: async () => {
          const ok = await confirmDialog({
            title: 'Delete custom role',
            message: 'Delete "' + (r.friendly_name || r.name) + '"? Users assigned to this role lose its permissions immediately.',
            confirmLabel: 'Delete role',
            destructive: true,
          });
          if (!ok) return;
          try { await api.deleteCustomRole(r.id); toast('Role deleted', 'success'); refresh(); if (onChanged) onChanged(); }
          catch (err) { toast(friendlyError(err), 'error'); }
        } });
        listEl.appendChild(el('div', { class: 'us-role-card' + (r.is_active === false ? ' inactive' : '') }, [
          el('div', { class: 'us-role-card-grow' }, [
            el('p', { class: 'us-role-card-title' }, [
              r.friendly_name || r.name,
              r.is_active === false ? [' ', badge('Inactive', 'muted')] : null,
            ].flat().filter(Boolean)),
            r.description ? el('p', { class: 'us-role-card-desc' }, r.description) : null,
            el('p', { class: 'us-role-card-desc' }, [
              'Slug: ', el('code', null, r.name || ''),
              ' · Priority: ' + (r.priority == null ? '100' : r.priority),
              ' · ' + (r.scopes ? r.scopes.length : 0) + ' permission(s)',
            ]),
            r.scopes && r.scopes.length ? el('div', { class: 'us-role-card-scopes' },
              r.scopes.slice(0, 12).map((s) => el('code', null, s.name))) : null,
          ].filter(Boolean)),
          el('div', { class: 'us-role-card-actions' }, [editBtn, delBtn]),
        ]));
      });
    }

    createBtn.addEventListener('click', async () => {
      const scopes = await loadScopes();
      openRoleEditor(companyId, null, scopes, async () => { await refresh(); if (onChanged) onChanged(); });
    });
    setupModalFocus(handle, { focusSelector: '.btn-primary' });
    refresh();
  }

  /** Editor for a single custom role. `existing` is null for create. */
  function openRoleEditor(companyId, existing, allScopes, onSaved) {
    const isEdit = !!existing;
    const friendly = modalField('Display name *', {
      value: existing ? (existing.friendly_name || '') : '',
      placeholder: 'e.g. Billing Manager' });
    const slug = modalField('Slug (lowercase, no spaces) *', {
      value: existing ? (existing.name || '') : '',
      placeholder: 'e.g. billing_manager' });
    if (isEdit) slug.input.disabled = true;
    // Auto-derive slug from the friendly name on create — saves a step and
    // keeps the slug compliant with the backend's lowercase-snake-case rule.
    // Tracks whether the user has manually edited the slug so we don't
    // overwrite their intent.
    let slugManuallyEdited = isEdit;
    function slugify(s) {
      return String(s || '')
        .toLowerCase()
        .trim()
        .replace(/[^a-z0-9]+/g, '_')
        .replace(/^_+|_+$/g, '');
    }
    if (!isEdit) {
      friendly.input.addEventListener('input', () => {
        if (!slugManuallyEdited) slug.input.value = slugify(friendly.input.value);
      });
      slug.input.addEventListener('input', () => { slugManuallyEdited = true; });
    }
    const description = modalField('Description', {
      type: 'textarea', rows: 2,
      value: existing ? (existing.description || '') : '',
      placeholder: 'What this role can do' });
    const priority = modalField('Priority', {
      value: existing && existing.priority != null ? String(existing.priority) : '100',
      placeholder: '100' });
    const active = el('input', { type: 'checkbox' });
    active.checked = existing ? (existing.is_active !== false) : true;
    const activeWrap = el('label', { class: 'us-check' }, [
      active, el('span', null, 'Active'),
    ]);

    // Group scopes by category.
    const groups = {};
    (allScopes || []).forEach((s) => {
      const cat = s.category || 'Other';
      (groups[cat] = groups[cat] || []).push(s);
    });
    const categoryNames = Object.keys(groups).sort();
    const selectedScopeIds = new Set(
      (existing && existing.scopes ? existing.scopes : []).map((s) => s.id));
    const scopesWrap = el('div', { class: 'us-scope-list' });
    if (!categoryNames.length) {
      scopesWrap.appendChild(emptyState('Could not load scopes.'));
    }
    // Live counter that updates when checkboxes toggle so users can see
    // selection state without scrolling back to the field label.
    const scopesLabel = el('span', { class: 'us-label-text' },
      'Permissions / scopes (' + selectedScopeIds.size + ' selected)');
    function refreshScopeCount() {
      scopesLabel.textContent = 'Permissions / scopes (' + selectedScopeIds.size + ' selected)';
    }
    categoryNames.forEach((cat) => {
      scopesWrap.appendChild(el('div', { class: 'us-scope-cat' }, cat));
      groups[cat].forEach((s) => {
        const cb = el('input', { type: 'checkbox' });
        cb.checked = selectedScopeIds.has(s.id);
        cb.addEventListener('change', () => {
          if (cb.checked) selectedScopeIds.add(s.id); else selectedScopeIds.delete(s.id);
          refreshScopeCount();
        });
        scopesWrap.appendChild(el('label', { class: 'us-scope-row' }, [
          cb,
          el('div', null, [
            el('code', null, s.name),
            s.description ? el('div', { class: 'us-scope-row-desc' }, s.description) : null,
          ].filter(Boolean)),
        ]));
      });
    });
    const scopesField = el('label', { class: 'us-label' }, [scopesLabel, scopesWrap]);

    const cancelBtn = btn('Cancel');
    const saveBtn = btn(isEdit ? 'Save changes' : 'Create role', { kind: 'primary' });

    const handle = openModal({
      title: isEdit ? 'Edit custom role' : 'Create custom role',
      description: isEdit
        ? 'Update the role’s display info and permissions.'
        : 'Define a new bundle of scopes. The slug must be unique within the company and cannot be changed once created.',
      wide: true,
      body: [
        el('div', { class: 'us-grid-2' }, [friendly.wrap, slug.wrap]),
        description.wrap,
        el('div', { class: 'us-grid-2' }, [priority.wrap, activeWrap]),
        scopesField,
      ],
      footer: [cancelBtn, saveBtn],
    });

    cancelBtn.addEventListener('click', () => handle.close());
    saveBtn.addEventListener('click', async () => {
      const friendlyVal = friendly.input.value.trim();
      const slugVal = slug.input.value.trim();
      if (!friendlyVal) {
        toast('Display name is required', 'error');
        friendly.input.focus(); return;
      }
      if (!isEdit && !slugVal) {
        toast('Slug is required', 'error');
        slug.input.focus(); return;
      }
      if (!isEdit && !/^[a-z0-9_]+$/.test(slugVal)) {
        toast('Slug must be lowercase letters, numbers, and underscores only', 'error');
        slug.input.focus(); return;
      }
      const priorityNum = priority.input.value.trim()
        ? Math.max(0, Math.floor(Number(priority.input.value)))
        : 100;
      saveBtn.disabled = true;
      try {
        if (isEdit) {
          await api.updateCustomRole(existing.id, {
            friendly_name: friendlyVal,
            description: description.input.value.trim() || null,
            priority: priorityNum,
            is_active: !!active.checked,
            scope_ids: Array.from(selectedScopeIds),
          });
          toast('Role updated', 'success');
        } else {
          await api.createCustomRole(companyId, {
            name: slugVal,
            friendly_name: friendlyVal,
            description: description.input.value.trim() || null,
            priority: priorityNum,
            scope_ids: Array.from(selectedScopeIds),
          });
          toast('Role created', 'success');
        }
        handle.close();
        if (typeof onSaved === 'function') onSaved();
      } catch (err) {
        toast(friendlyError(err), 'error');
        saveBtn.disabled = false;
      }
    });
    setupModalFocus(handle);
  }

  // ─── Webhooks tab ────────────────────────────────────────────────────

  async function renderWebhooks(panel) {
    panel.innerHTML = '';
    panel.appendChild(emptyState('Loading webhooks…'));
    let outgoing, incoming, eventTypes;
    try {
      [outgoing, incoming, eventTypes] = await Promise.all([
        api.listOutgoingWebhooks().catch(() => []),
        api.listIncomingWebhooks().catch(() => []),
        api.getWebhookEventTypes().catch(() => []),
      ]);
    } catch (err) {
      panel.innerHTML = '';
      panel.appendChild(section('Webhooks', null, [el('p', { class: 'us-hint error' }, errMsg(err))]));
      return;
    }
    panel.innerHTML = '';

    const stats = el('div', { class: 'us-grid-2', style: 'grid-template-columns:repeat(4,1fr);gap:12px;' }, [
      statCard('Outgoing', outgoing.length, outgoing.filter((w) => w && w.active).length + ' active'),
      statCard('Incoming', incoming.length, incoming.filter((w) => w && w.active).length + ' active'),
      statCard('Event subscriptions',
        outgoing.reduce((acc, w) => acc + ((w && w.event_types && w.event_types.length) || 0), 0),
        'Across outgoing webhooks'),
      statCard('Active integrations',
        outgoing.filter((w) => w && w.active).length + incoming.filter((w) => w && w.active).length,
        'Live now'),
    ]);
    panel.appendChild(stats);

    // Outgoing webhooks.
    const outgoingHeaderActions = btn('+ New outgoing webhook', { kind: 'primary',
      onclick: () => openWebhookForm(panel, 'outgoing', null, eventTypes),
    });
    const outgoingSection = section('Outgoing webhooks',
      'Send HTTP POST requests to external URLs when conversation, message, or task events fire.',
      [
        el('div', { class: 'us-section-row end' }, [outgoingHeaderActions]),
      ]);
    panel.appendChild(outgoingSection);
    if (!outgoing.length) {
      outgoingSection.appendChild(emptyState('No outgoing webhooks yet.'));
    } else {
      const list = el('div', { class: 'us-row-list' });
      outgoing.forEach((w) => list.appendChild(buildOutgoingWebhookRow(w, panel, eventTypes)));
      outgoingSection.appendChild(list);
    }

    // Incoming webhooks.
    const incomingHeaderActions = btn('+ New incoming webhook', { kind: 'primary',
      onclick: () => openWebhookForm(panel, 'incoming', null, eventTypes),
    });
    const incomingSection = section('Incoming webhooks',
      'Expose URLs that trigger agent actions when external services POST to them.',
      [
        el('div', { class: 'us-section-row end' }, [incomingHeaderActions]),
      ]);
    panel.appendChild(incomingSection);
    if (!incoming.length) {
      incomingSection.appendChild(emptyState('No incoming webhooks yet.'));
    } else {
      const list = el('div', { class: 'us-row-list' });
      incoming.forEach((w) => list.appendChild(buildIncomingWebhookRow(w, panel)));
      incomingSection.appendChild(list);
    }
  }

  function statCard(title, value, sub) {
    return el('div', { class: 'us-section', style: 'padding:12px;gap:4px;' }, [
      el('p', { class: 'us-section-blurb', style: 'margin:0;font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:var(--text-faint);' }, title),
      el('p', { style: 'margin:0;font-size:22px;font-weight:700;color:var(--text);' }, String(value)),
      el('p', { class: 'us-section-blurb', style: 'margin:0;font-size:11px;' }, sub || ''),
    ]);
  }

  function buildOutgoingWebhookRow(w, panel, eventTypes) {
    const events = Array.isArray(w.event_types) ? w.event_types : [];
    return el('div', { class: 'us-list-item' }, [
      el('div', { class: 'us-list-item-grow' }, [
        el('p', { class: 'us-list-item-title' }, [
          w.name || '(unnamed)', ' ',
          w.active ? badge('Active', 'success') : badge('Disabled'),
        ]),
        el('p', { class: 'us-list-item-meta' }, w.target_url || ''),
        events.length ? el('p', { class: 'us-list-item-meta' },
          'Events: ' + events.slice(0, 6).join(', ') + (events.length > 6 ? ` (+${events.length - 6})` : '')) : null,
        w.description ? el('p', { class: 'us-list-item-meta' }, w.description) : null,
      ]),
      el('div', { class: 'us-list-item-actions' }, [
        btn('Test', { onclick: async () => {
          try {
            const result = await api.testOutgoingWebhook(w.id);
            toast('Test fired: ' + (result && (result.message || result.status_code || 'sent')), 'success');
          } catch (err) { toast(errMsg(err), 'error'); }
        } }),
        btn('Edit', { onclick: () => openWebhookForm(panel, 'outgoing', w, eventTypes) }),
        btn('Delete', { kind: 'danger', onclick: async () => {
          if (!confirm('Delete webhook "' + (w.name || w.id) + '"?')) return;
          try { await api.deleteOutgoingWebhook(w.id); toast('Deleted', 'success'); renderWebhooks(panel); }
          catch (err) { toast(errMsg(err), 'error'); }
        } }),
      ]),
    ]);
  }

  function buildIncomingWebhookRow(w, panel) {
    return el('div', { class: 'us-list-item' }, [
      el('div', { class: 'us-list-item-grow' }, [
        el('p', { class: 'us-list-item-title' }, [
          w.name || '(unnamed)', ' ',
          w.active ? badge('Active', 'success') : badge('Disabled'),
        ]),
        w.url || w.endpoint_url ? el('p', { class: 'us-list-item-meta' },
          el('code', { class: 'us-mono' }, w.url || w.endpoint_url)) : null,
        w.agent_id ? el('p', { class: 'us-list-item-meta' }, 'Agent: ' + w.agent_id) : null,
        w.description ? el('p', { class: 'us-list-item-meta' }, w.description) : null,
      ]),
      el('div', { class: 'us-list-item-actions' }, [
        btn('Edit', { onclick: () => openWebhookForm(panel, 'incoming', w, null) }),
        btn('Delete', { kind: 'danger', onclick: async () => {
          if (!confirm('Delete webhook "' + (w.name || w.id) + '"?')) return;
          try { await api.deleteIncomingWebhook(w.id); toast('Deleted', 'success'); renderWebhooks(panel); }
          catch (err) { toast(errMsg(err), 'error'); }
        } }),
      ]),
    ]);
  }

  function openWebhookForm(panel, kind, existing, eventTypes) {
    panel.querySelectorAll('[data-webhook-form]').forEach((n) => n.remove());
    const wrap = el('section', { class: 'us-section', dataset: { webhookForm: '1' } });
    wrap.appendChild(el('h2', { class: 'us-section-title' },
      (existing ? 'Edit ' : 'New ') + (kind === 'outgoing' ? 'outgoing' : 'incoming') + ' webhook'));

    const name = el('input', { class: 'us-input', value: (existing && existing.name) || '' });
    const description = el('textarea', { class: 'us-textarea', rows: 2 });
    description.value = (existing && existing.description) || '';
    const active = el('input', { type: 'checkbox' });
    active.checked = existing ? !!existing.active : true;

    wrap.appendChild(field('Name', name));
    wrap.appendChild(field('Description', description));

    let collectExtras;

    if (kind === 'outgoing') {
      const targetUrl = el('input', { class: 'us-input', type: 'url',
        placeholder: 'https://example.com/webhook',
        value: (existing && existing.target_url) || '' });
      const secret = el('input', { class: 'us-input', type: 'text',
        placeholder: 'optional shared secret',
        value: (existing && existing.secret) || '' });

      // Event-type selector. The endpoint returns [{type, description}, ...].
      const selectedEvents = new Set((existing && existing.event_types) || []);
      const eventList = el('div', { class: 'us-scope-list' });
      const types = Array.isArray(eventTypes) ? eventTypes : [];
      if (!types.length) {
        eventList.appendChild(emptyState('No event types reported by the server.'));
      } else {
        types.forEach((evt) => {
          const t = evt.type || evt.name || String(evt);
          const chk = el('input', { type: 'checkbox' });
          chk.checked = selectedEvents.has(t);
          chk.addEventListener('change', () => { chk.checked ? selectedEvents.add(t) : selectedEvents.delete(t); });
          eventList.appendChild(el('label', { class: 'us-scope-row' }, [
            chk,
            el('div', null, [
              el('code', null, t),
              evt.description ? el('div', { class: 'us-scope-row-desc' }, evt.description) : null,
            ]),
          ]));
        });
      }

      wrap.appendChild(field('Target URL', targetUrl));
      wrap.appendChild(field('Secret', secret, 'Optional. Sent as `X-Webhook-Secret` header for verification.'));
      wrap.appendChild(el('div', { class: 'us-section-blurb' }, 'Subscribe to events:'));
      wrap.appendChild(eventList);
      collectExtras = () => ({
        target_url: targetUrl.value.trim(),
        secret: secret.value.trim() || undefined,
        event_types: Array.from(selectedEvents),
      });
    } else {
      // Incoming — needs an agent_id. Pull from cached user companies.
      const agents = [];
      if (cache.user && Array.isArray(cache.user.companies)) {
        cache.user.companies.forEach((c) => {
          (c.agents || []).forEach((a) => agents.push({ id: a.id, label: a.name + ' @ ' + (c.name || '') }));
        });
      }
      const agentSelect = el('select', { class: 'us-select' }, agents.map((a) =>
        el('option', { value: a.id }, a.label)));
      if (existing && existing.agent_id) agentSelect.value = existing.agent_id;
      const rateLimit = el('input', { class: 'us-input', type: 'number', min: 0,
        value: (existing && existing.rate_limit) || '' });
      const allowedIps = el('input', { class: 'us-input', type: 'text',
        placeholder: 'comma-separated IPs (optional)',
        value: (existing && Array.isArray(existing.allowed_ips)) ? existing.allowed_ips.join(', ') : '' });
      wrap.appendChild(field('Agent', agentSelect));
      wrap.appendChild(field('Rate limit (req/min)', rateLimit, 'Leave blank for unlimited.'));
      wrap.appendChild(field('Allowed IPs', allowedIps));
      collectExtras = () => ({
        agent_id: agentSelect.value,
        rate_limit: rateLimit.value ? Number(rateLimit.value) : undefined,
        allowed_ips: allowedIps.value
          ? allowedIps.value.split(',').map((s) => s.trim()).filter(Boolean)
          : undefined,
      });
    }

    wrap.appendChild(el('label', { class: 'us-check' }, [active, el('span', null, 'Active')]));

    const status = el('span', { class: 'us-status-line' }, '');
    const cancelBtn = btn('Cancel', { onclick: () => wrap.remove() });
    const saveBtn = btn(existing ? 'Save changes' : 'Create', { kind: 'primary', onclick: async () => {
      if (!name.value.trim()) { status.textContent = 'Name is required.'; status.className = 'us-status-line error'; return; }
      const payload = {
        name: name.value.trim(),
        description: description.value.trim() || undefined,
        active: active.checked,
        ...collectExtras(),
      };
      saveBtn.disabled = true;
      try {
        if (kind === 'outgoing') {
          if (existing) await api.updateOutgoingWebhook(existing.id, payload);
          else await api.createOutgoingWebhook(payload);
        } else {
          if (existing) await api.updateIncomingWebhook(existing.id, payload);
          else await api.createIncomingWebhook(payload);
        }
        toast('Saved', 'success');
        wrap.remove();
        renderWebhooks(panel);
      } catch (err) {
        status.textContent = errMsg(err); status.className = 'us-status-line error';
        saveBtn.disabled = false;
      }
    } });
    wrap.appendChild(status);
    wrap.appendChild(el('div', { class: 'us-section-row end' }, [cancelBtn, saveBtn]));
    panel.insertBefore(wrap, panel.firstChild);
  }

  // ─── Mount ───────────────────────────────────────────────────────────

  async function mount(opts) {
    if (mounted) {
      // Re-mounts (eg. tab change) just refresh the requested tab.
      const tab = opts && opts.tab;
      if (tab && TAB_RENDERERS[tab]) setActiveTab(tab);
      else activatePanel(activeTab);
      return;
    }
    mounted = true;
    bindTabs();
    await ensureBillingTabVisible();
    setActiveTab((opts && opts.tab) || 'app');
    // Refresh the Billing tab when the user returns to the app from
    // Stripe checkout. We only re-render when there's actually a
    // pending-payment marker so the rest of the app doesn't churn
    // every time the window regains focus.
    window.addEventListener('focus', () => {
      if (!loadPendingPayment()) return;
      const panel = document.querySelector('.us-panel[data-us-panel="billing"]');
      if (!panel || panel.hidden) return;
      renderBilling(panel).catch((err) =>
        console.warn('billing focus refresh failed', err));
    });
  }

  window.UserSettings = { mount, setActiveTab };
})();

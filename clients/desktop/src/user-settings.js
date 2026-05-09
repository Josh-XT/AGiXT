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
    const settings = await loadDesktopSettings(true);
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
      el('option', { value: 'dark' }, 'Dark'),
      el('option', { value: 'gray' }, 'Dark gray'),
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
          ? (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
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
      'Linux updates use the remembered Privileged Commands sudo password to install the downloaded .deb.',
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
      el('option', { value: 'dark' }, 'Dark'),
      el('option', { value: 'gray' }, 'Dark gray'),
    ]);
    themeSelect.value = settings.theme || 'system';
    themeSelect.addEventListener('change', async () => {
      const value = themeSelect.value;
      await invoke('save_settings', { settings: { ...settings, theme: value } });
      cache.desktopSettings = { ...settings, theme: value };
      const resolved = value === 'system'
        ? (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
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
    let user;
    try { user = await loadUser(); } catch (err) {
      panel.innerHTML = '';
      panel.appendChild(section('Billing', null, [el('p', { class: 'us-hint error' }, errMsg(err))]));
      return;
    }
    if (!user || !user.companies || !user.companies.length) {
      panel.innerHTML = '';
      panel.appendChild(emptyState('No companies on this account.'));
      return;
    }
    // Pick the active / primary company. The user can switch via the topbar
    // selector before opening this panel.
    const settings = await loadDesktopSettings();
    const activeCompany = (settings && settings.company_id
      ? user.companies.find((c) => c.id === settings.company_id)
      : null) || user.companies.find((c) => c.primary) || user.companies[0];

    panel.innerHTML = '';
    if (!userCanAdminCompany(user, activeCompany.id)) {
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

    panel.appendChild(section('Billing for ' + (activeCompany.name || 'company'),
      'Manage your ' + appName + ' subscription, credits, and payment history.',
      [
        el('p', { class: 'us-hint' },
          'Pricing model: ' + (pricing ? pricing.pricing_model : 'unknown')),
      ]));

    // Token balance / plan summary.
    if (isTokenBased) {
      try {
        const balance = await api.getTokenBalance(activeCompany.id, true);
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
            openExternal(res.checkout_url || res.url);
            topupStatus.textContent = 'Opened Stripe checkout in your browser.';
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
          if (res && res.checkout_url) { openExternal(res.checkout_url); planTopupStatus.textContent = 'Stripe checkout opened.'; planTopupStatus.className = 'us-status-line success'; }
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
        const changePlanBtn = btn('Change plan', { kind: 'primary', onclick: async () => {
          try {
            const res = await api.createPlanCheckout({ company_id: activeCompany.id, plan_id: tierSelect.value });
            if (res && res.checkout_url) { openExternal(res.checkout_url); changePlanStatus.textContent = 'Stripe checkout opened.'; changePlanStatus.className = 'us-status-line success'; }
          } catch (err) { changePlanStatus.textContent = errMsg(err); changePlanStatus.className = 'us-status-line error'; }
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

  async function renderCompanies(panel) {
    panel.innerHTML = '';
    panel.appendChild(emptyState('Loading companies…'));
    let user;
    try { user = await loadUser(true); } catch (err) {
      panel.innerHTML = '';
      panel.appendChild(section('Companies', null, [el('p', { class: 'us-hint error' }, errMsg(err))]));
      return;
    }
    if (!user || !user.companies || !user.companies.length) {
      panel.innerHTML = '';
      panel.appendChild(emptyState('No companies on this account yet.'));
      return;
    }
    panel.innerHTML = '';

    // Create.
    const createName = el('input', { class: 'us-input', placeholder: 'New company name' });
    const createBtn = btn('Create', { kind: 'primary', onclick: async () => {
      const name = createName.value.trim();
      if (!name) return;
      createBtn.disabled = true;
      try {
        await api.createCompany({ name });
        createName.value = '';
        cache.user = null;
        toast('Company created', 'success');
        renderCompanies(panel);
      } catch (err) { toast(errMsg(err), 'error'); }
      finally { createBtn.disabled = false; }
    } });
    panel.appendChild(section('Create a company', null, [
      el('div', { class: 'us-section-row' }, [createName, createBtn]),
    ]));

    // Existing companies.
    const list = el('div', { class: 'us-row-list' });
    user.companies.forEach((c) => {
      const isAdmin = isAdminLikeRole(c.role_id);
      const renameInput = el('input', { class: 'us-input', value: c.name || '' });
      const renameBtn = btn('Rename', { onclick: async () => {
        const next = renameInput.value.trim();
        if (!next || next === c.name) return;
        try {
          await api.renameCompany(c.id, next);
          cache.user = null;
          toast('Renamed', 'success');
          renderCompanies(panel);
        } catch (err) { toast(errMsg(err), 'error'); }
      } });
      const deleteBtn = btn('Delete', { kind: 'danger', onclick: async () => {
        if (!confirm('Delete "' + c.name + '"? This is permanent.')) return;
        try {
          await api.deleteCompany(c.id);
          cache.user = null;
          toast('Company deleted', 'success');
          renderCompanies(panel);
        } catch (err) { toast(errMsg(err), 'error'); }
      } });
      const actions = isAdmin
        ? el('div', { class: 'us-section-row' }, [renameInput, renameBtn, deleteBtn])
        : null;
      list.appendChild(el('div', { class: 'us-list-item' }, [
        el('div', { class: 'us-list-item-grow' }, [
          el('p', { class: 'us-list-item-title' }, [
            c.name || 'Untitled', ' ',
            c.primary ? badge('Primary', 'primary') : null,
            ' ',
            badge('Role: ' + (c.role || 'member')),
          ].filter(Boolean)),
          c.address ? el('p', { class: 'us-list-item-meta' }, [c.address, c.city, c.state, c.zip_code, c.country].filter(Boolean).join(', ')) : null,
          actions,
        ]),
      ]));
    });
    panel.appendChild(section('Your companies', null, [list]));
  }

  // ─── Teams tab — company-scoped member management ───────────────────

  async function renderTeams(panel) {
    panel.innerHTML = '';
    panel.appendChild(emptyState('Loading team…'));
    let user;
    try { user = await loadUser(); } catch (err) {
      panel.innerHTML = '';
      panel.appendChild(section('Teams', null, [el('p', { class: 'us-hint error' }, errMsg(err))]));
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
    const select = el('select', { class: 'us-select' }, user.companies.map((c) => {
      const opt = el('option', { value: c.id }, c.name + (c.primary ? ' (primary)' : ''));
      return opt;
    }));
    select.value = activeCompanyId;
    const body = el('div');
    select.addEventListener('change', async () => {
      activeCompanyId = select.value;
      await refreshBody();
    });
    panel.appendChild(section('Active company', null, [select]));
    panel.appendChild(body);

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
      let members, invitations, defaultRoles;
      try {
        [members, invitations, defaultRoles] = await Promise.all([
          api.getCompanyMembers(activeCompanyId),
          api.getInvitations(activeCompanyId).catch(() => []),
          (cache.defaultRoles ? Promise.resolve(cache.defaultRoles) : api.listDefaultRoles()).catch(() => []),
        ]);
        cache.defaultRoles = defaultRoles;
      } catch (err) {
        body.innerHTML = '';
        body.appendChild(section('Team', null, [el('p', { class: 'us-hint error' }, errMsg(err))]));
        return;
      }
      body.innerHTML = '';

      // Invite form.
      const inviteEmail = el('input', { class: 'us-input', type: 'email', placeholder: 'name@example.com' });
      const inviteRole = el('select', { class: 'us-select' });
      const ASSIGNABLE = [2, 3, 5, 6];
      const roleOptions = (Array.isArray(defaultRoles) ? defaultRoles : [])
        .filter((r) => ASSIGNABLE.includes(r.id))
        .map((r) => el('option', { value: r.id }, r.friendly_name || r.name));
      if (!roleOptions.length) {
        // Fallback when /v1/roles isn't reachable — best-effort defaults
        // matching the web app's resolveRoleId mapping.
        ['Admin#2', 'User#3', 'Chat User#5', 'Read Only#6'].forEach((s) => {
          const [n, id] = s.split('#');
          inviteRole.appendChild(el('option', { value: id }, n));
        });
      } else {
        roleOptions.forEach((o) => inviteRole.appendChild(o));
      }
      const inviteBtn = btn('Send invite', { kind: 'primary', onclick: async () => {
        const target = inviteEmail.value.trim();
        if (!target) return;
        try {
          await api.createInvitation({
            email: target,
            company_id: activeCompanyId,
            role_id: Number(inviteRole.value),
          });
          inviteEmail.value = '';
          toast('Invite sent', 'success');
          refreshBody();
        } catch (err) { toast(errMsg(err), 'error'); }
      } });
      body.appendChild(section('Invite a member', null, [
        el('div', { class: 'us-section-row' }, [inviteEmail, inviteRole, inviteBtn]),
      ]));

      // Pending invitations.
      if (Array.isArray(invitations) && invitations.length) {
        const list = el('div', { class: 'us-row-list' });
        invitations.forEach((inv) => {
          list.appendChild(el('div', { class: 'us-list-item' }, [
            el('div', { class: 'us-list-item-grow' }, [
              el('p', { class: 'us-list-item-title' }, inv.email || inv.invitee_email || '—'),
              el('p', { class: 'us-list-item-meta' }, 'Role: ' + (inv.role || inv.role_id || '—') +
                (inv.created_at ? ' · invited ' + formatDate(inv.created_at) : '')),
            ]),
            btn('Cancel', { onclick: async () => {
              try { await api.deleteInvitation(inv.id); toast('Invite cancelled', 'success'); refreshBody(); }
              catch (err) { toast(errMsg(err), 'error'); }
            } }),
          ]));
        });
        body.appendChild(section('Pending invitations', null, [list]));
      }

      // Members list.
      const memberList = el('div', { class: 'us-row-list' });
      if (!members.length) memberList.appendChild(emptyState('No members yet.'));
      members.forEach((m) => {
        const isProtected = m.role_id === 0 || m.role_id === 1 || m.role_id === 4;
        const roleSelect = el('select', { class: 'us-select' });
        const opts = Array.isArray(defaultRoles) && defaultRoles.length
          ? defaultRoles.filter((r) => ASSIGNABLE.includes(r.id))
          : [{ id: 2, friendly_name: 'Admin' }, { id: 3, friendly_name: 'User' }, { id: 5, friendly_name: 'Chat User' }, { id: 6, friendly_name: 'Read Only' }];
        opts.forEach((r) => roleSelect.appendChild(el('option', { value: r.id }, r.friendly_name || r.name)));
        roleSelect.value = String(m.role_id);
        roleSelect.disabled = isProtected;
        roleSelect.addEventListener('change', async () => {
          const next = Number(roleSelect.value);
          if (next === m.role_id) return;
          try {
            await api.updateMemberRole(activeCompanyId, m.id, next);
            toast('Role updated', 'success');
            refreshBody();
          } catch (err) { toast(errMsg(err), 'error'); roleSelect.value = String(m.role_id); }
        });
        memberList.appendChild(el('div', { class: 'us-list-item' }, [
          el('div', { class: 'us-list-item-grow' }, [
            el('p', { class: 'us-list-item-title' }, [
              (m.first_name || '') + ' ' + (m.last_name || ''), ' ',
              isProtected ? badge((m.role || 'system'), 'warn') : null,
            ].filter(Boolean)),
            el('p', { class: 'us-list-item-meta' }, m.email),
          ]),
          el('div', { class: 'us-list-item-actions' }, [
            roleSelect,
            !isProtected && m.id !== user.id ? btn('Remove', { kind: 'danger', onclick: async () => {
              if (!confirm('Remove ' + m.email + ' from ' + company.name + '?')) return;
              try { await api.removeCompanyMember(activeCompanyId, m.id); toast('Removed', 'success'); refreshBody(); }
              catch (err) { toast(errMsg(err), 'error'); }
            } }) : null,
          ]),
        ]));
      });
      body.appendChild(section('Members of ' + company.name, null, [memberList]));
    }

    refreshBody();
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
  }

  window.UserSettings = { mount, setActiveTab };
})();

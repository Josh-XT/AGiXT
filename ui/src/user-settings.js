/* User settings pane.
 *
 * Hosts the App / Glasses / Account / Notifications / Developer /
 * Billing / Webhooks / Super Admin sub-tabs that replace the legacy
 * gear-button modal. Mirrors the web app's /user/manage,
 * /user/settings, /user/developer, /billing pages — but tuned for the
 * desktop's tighter side pane footprint and vanilla-JS host.
 *
 * Companies & Teams management lives in the dedicated "Companies &
 * Teams" extension (ui/extensions/desktop/companies/), not here.
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
    const candidates = [err.error, err.detail, err.message, err];
    for (const candidate of candidates) {
      if (candidate == null) continue;
      if (typeof candidate === 'string') return candidate;
      if (candidate instanceof Error && candidate.message) return candidate.message;
      if (typeof candidate === 'object') {
        if (typeof candidate.detail === 'string') return candidate.detail;
        if (typeof candidate.error === 'string') return candidate.error;
        if (typeof candidate.message === 'string') return candidate.message;
        try { return JSON.stringify(candidate); } catch (_) { /* keep looking */ }
      }
      const text = String(candidate);
      if (text && text !== '[object Object]') return text;
    }
    return 'Unknown error';
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

  function formatBillingAmount(amount) {
    const value = Number(amount);
    if (!Number.isFinite(value)) return '$0';
    return '$' + value.toLocaleString(undefined, {
      minimumFractionDigits: value % 1 === 0 ? 0 : 2,
      maximumFractionDigits: 2,
    });
  }

  function formatStorage(bytes) {
    const value = Number(bytes) || 0;
    if (value >= 1024 * 1024 * 1024) return (value / 1024 / 1024 / 1024).toFixed(1) + ' GB';
    if (value >= 1024 * 1024) return (value / 1024 / 1024).toFixed(1) + ' MB';
    if (value >= 1024) return (value / 1024).toFixed(1) + ' KB';
    return String(Math.max(0, Math.round(value))) + ' B';
  }

  function billingIntervals(pricing) {
    const contracts = (pricing && pricing.contracts) || {};
    const intervals = [];
    if (contracts.monthly !== false) intervals.push({ id: 'month', label: 'Monthly' });
    if (contracts.annual === true) {
      const discount = Number(contracts.annual_discount_percent || 0);
      intervals.push({
        id: 'year',
        label: discount > 0 ? 'Annual · save ' + discount + '%' : 'Annual',
      });
    }
    return intervals.length ? intervals : [{ id: 'month', label: 'Monthly' }];
  }

  function tierMonthlyPrice(tier) {
    const value = tier && (tier.price || tier.price_per_unit || tier.monthly_price);
    const amount = Number(value);
    return Number.isFinite(amount) ? amount : 0;
  }

  function tierIntervalAmount(tier, interval, pricing) {
    if (!tier) return 0;
    if (interval === 'year') {
      const explicit = Number(tier.annual_price || tier.yearly_price || tier.price_annual);
      if (Number.isFinite(explicit) && explicit > 0) return explicit;
      const discount = Number((pricing && pricing.contracts && pricing.contracts.annual_discount_percent) || 0);
      return tierMonthlyPrice(tier) * 12 * (1 - Math.max(0, Math.min(discount, 100)) / 100);
    }
    return tierMonthlyPrice(tier);
  }

  function tierLimitText(tier) {
    const limits = (tier && tier.limits) || {};
    const pieces = [];
    if (limits.users) pieces.push(limits.users + ' user' + (Number(limits.users) === 1 ? '' : 's'));
    if (limits.devices) pieces.push(formatTokens(limits.devices) + ' devices');
    if (limits.tokens) pieces.push(formatTokens(limits.tokens) + ' tokens/mo');
    if (limits.storage_gb) pieces.push(limits.storage_gb + 'GB storage');
    return pieces;
  }

  function tokenTopupPricePerMillion(pricing) {
    const addon = pricing && pricing.addons && pricing.addons.token_topup;
    const value = addon && (addon.price_per_million || addon.price || addon.amount_usd);
    const amount = Number(value);
    return Number.isFinite(amount) && amount > 0 ? amount : 5;
  }

  function tokenTopupMinimumMillions(pricing) {
    const addon = pricing && pricing.addons && pricing.addons.token_topup;
    const value = addon && (addon.min_purchase_millions || addon.minimum_millions || addon.min);
    const amount = Number(value);
    return Number.isFinite(amount) && amount > 0 ? amount : 1;
  }

  function tokenTopupBlurb(pricing) {
    const price = tokenTopupPricePerMillion(pricing);
    const minimum = tokenTopupMinimumMillions(pricing);
    return 'One unit buys 1M extra tokens for ' + formatBillingAmount(price)
      + '. Minimum purchase: ' + minimum + 'M tokens. Extra tokens are used after the monthly plan allowance.';
  }

  function resourceAddonConfig(pricing) {
    const addon = pricing && pricing.addons && pricing.addons.user_addon;
    const includes = (addon && addon.includes) || {};
    const storageGb = Number(includes.storage_gb || 2);
    const price = Number(addon && (addon.price || addon.amount_usd));
    return {
      price: Number.isFinite(price) && price > 0 ? price : 10,
      currency: (addon && addon.currency) || (pricing && pricing.currency) || 'USD',
      users: Number(includes.users || 1),
      devices: Number(includes.devices || 5),
      tokens: Number(includes.tokens || 10000000),
      storageBytes: Math.round((Number.isFinite(storageGb) ? storageGb : 2) * 1024 * 1024 * 1024),
      storageGb: Number.isFinite(storageGb) ? storageGb : 2,
    };
  }

  function pricingTierName(pricing, planId) {
    const tiers = pricing && Array.isArray(pricing.tiers) ? pricing.tiers : [];
    const tier = tiers.find((item) => item && item.id === planId);
    return (tier && (tier.name || tier.id)) || planId || '';
  }

  function trialDaysText(trial) {
    if (!trial) return '';
    let days = null;
    if (trial.days_remaining != null && !Number.isNaN(Number(trial.days_remaining))) {
      days = Math.max(0, Number(trial.days_remaining));
    } else if (trial.trial_end) {
      const end = new Date(trial.trial_end);
      if (!Number.isNaN(end.getTime())) {
        days = Math.max(0, Math.ceil((end.getTime() - Date.now()) / 86400000));
      }
    }
    if (days == null) return trial.is_active === false ? 'Trial ended' : 'Trial active';
    if (days <= 0 || trial.is_active === false) return 'Trial ended';
    return days === 1 ? '1 day left' : days + ' days left';
  }

  function renderTrialBillingBanner(trial, pricing, onSubscribe) {
    if (!trial) return null;
    const active = trial.is_active !== false && trialDaysText(trial) !== 'Trial ended';
    const title = active ? 'Trial active' : 'Trial ended';
    const message = active
      ? trialDaysText(trial) + ' — subscribe now to avoid any interruption when the trial closes.'
      : 'Choose a monthly or annual plan to continue using ' + ((pricing && pricing.app_name) || 'AGiXT') + '.';
    const wrap = el('div', { class: 'us-payment-banner ' + (active ? 'us-payment-banner-warn' : 'us-payment-banner-bad') });
    wrap.appendChild(el('div', { class: 'us-payment-banner-icon', html: active
      ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>'
      : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/></svg>',
    }));
    const body = el('div', { class: 'us-payment-banner-body' }, [
      el('div', { class: 'us-payment-banner-title' }, title),
      el('div', { class: 'us-payment-banner-msg' }, message),
    ]);
    body.appendChild(el('div', { class: 'us-payment-banner-actions' }, [
      btn(active ? 'Subscribe now' : 'Choose a plan', { kind: 'primary', onclick: onSubscribe }),
    ]));
    wrap.appendChild(body);
    return wrap;
  }

  function renderPlanLimitWarnings(warnings, opts) {
    warnings = Array.isArray(warnings) ? warnings.filter(Boolean) : [];
    if (!warnings.length) return null;
    opts = opts || {};
    const hasError = warnings.some((warning) => warning.severity === 'error' || String(warning.type || '').includes('reached'));
    const hasTokenWarning = warnings.some((warning) => String(warning.type || '').includes('token'));
    const hasStorageWarning = warnings.some((warning) => String(warning.type || '').includes('storage'));
    const title = hasError ? 'Billing limit reached' : 'Billing limits are getting close';
    const wrap = el('div', {
      class: 'us-payment-banner ' + (hasError ? 'us-payment-banner-bad' : 'us-payment-banner-warn'),
    });
    wrap.appendChild(el('div', { class: 'us-payment-banner-icon', html: hasTokenWarning
      ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8"/><path d="M12 7v10"/><path d="M8 12h8"/></svg>'
      : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>',
    }));
    const list = el('ul', { class: 'us-warning-list' }, warnings.map((warning) =>
      el('li', null, warning.message || 'Review your current plan usage.')));
    const body = el('div', { class: 'us-payment-banner-body' }, [
      el('div', { class: 'us-payment-banner-title' }, title),
      el('div', { class: 'us-payment-banner-msg' }, list),
    ]);
    const actions = el('div', { class: 'us-payment-banner-actions' });
    if (hasTokenWarning) {
      actions.appendChild(btn('Buy token top-up', {
        kind: 'primary',
        onclick: opts.onTokenTopup,
      }));
    }
    if (hasStorageWarning && opts.onStorageAddon) {
      actions.appendChild(btn('Add storage', {
        kind: hasTokenWarning ? 'secondary' : 'primary',
        onclick: opts.onStorageAddon,
      }));
    }
    actions.appendChild(btn(hasTokenWarning ? 'Compare plans' : 'Upgrade plan', {
      kind: hasTokenWarning ? 'secondary' : 'primary',
      onclick: opts.onUpgradePlan,
    }));
    body.appendChild(actions);
    wrap.appendChild(body);
    return wrap;
  }

  function isAdminLikeRole(roleId) {
    // Mirrors the web's resolveRoleId mapping. Roles 0–2 grant admin-level
    // surfaces (tenant admin, company admin) — anything else is rank-and-file.
    return typeof roleId === 'number' && roleId >= 0 && roleId <= 2;
  }

  function valueHasScope(value, wanted) {
    if (!value) return false;
    const scopes = Array.isArray(value)
      ? value
      : (typeof value === 'string' ? value.split(/[,\s]+/) : []);
    return scopes.some((scope) => scope === '*' || scope === wanted || scope === 'company:*');
  }

  function canDeleteCompany(company) {
    if (!company) return false;
    const roleId = Number(company.role_id);
    if (company.can_delete === true || company.can_delete_company === true) return true;
    if (roleId === 0 || roleId === 1) return true;
    if (company.role === 'super_admin' || company.role === 'tenant_admin') return true;
    return valueHasScope(company.scopes, 'company:delete')
      || valueHasScope(company.permissions, 'company:delete');
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
    notifications: renderNotifications,
    developer: renderDeveloper,
    billing: renderBilling,
    webhooks: renderWebhooks,
    superadmin: renderSuperAdmin,
  };

  function setActiveTab(name) {
    if (!TAB_RENDERERS[name]) name = 'app';
    // Glasses depend on native Bluetooth / Tauri commands — bounce
    // back to App if someone routes to it from the web runtime.
    if (name === 'glasses' && isWebRuntime()) name = 'app';
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
    if (window.AgixtAppRoutes && typeof window.AgixtAppRoutes.setSettingsTab === 'function') {
      try { window.AgixtAppRoutes.setSettingsTab(name); } catch (_) {}
    }
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

  /** When the UI is served from the hosted web runtime (vs the native
   *  Tauri desktop shell) there is no AGiXT Desktop executable to
   *  update, no sudo session to keep, and no client-side commands to
   *  run — so the App tab hides those sections. The flag is set by
   *  web-runtime.js before app.js boots. */
  function isWebRuntime() {
    return !!window.__AGIXT_WEB_RUNTIME;
  }

  async function renderApp(panel) {
    panel.innerHTML = '';
    let settings = await loadDesktopSettings(true);
    const user = settings && settings.jwt ? await loadUser().catch(() => null) : null;
    const webRuntime = isWebRuntime();

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

    // Behavior toggles. Voice replies works in both runtimes, but the
    // "Allow this agent to control my desktop" and the AGiXT Desktop
    // auto-update toggles only make sense when the user is running the
    // native Tauri shell — there is no local OS to control or .deb to
    // install from the hosted browser build, so we hide them entirely.
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
          // Preserve existing desktop-only fields when we're in the web
          // runtime and the inputs aren't rendered — otherwise their
          // (false) defaults would clobber what the native client saved.
          allow_client_commands: webRuntime
            ? !!settings.allow_client_commands
            : allowCommands.checked,
          voice_enabled: voiceToggle.checked,
          desktop_auto_update: webRuntime
            ? !!settings.desktop_auto_update
            : autoUpdate.checked,
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
        if (!webRuntime) renderSudoStatus();
      } catch (err) { toast(errMsg(err), 'error'); }
    } });
    saveBehaviorBtn.dataset.usTest = 'save-behavior';
    const behaviorRows = [
      webRuntime ? null : el('label', { class: 'us-check' }, [allowCommands,
        el('span', null, 'Allow this agent to control my desktop (screenshot, click, type, files)')]),
      el('label', { class: 'us-check' }, [voiceToggle,
        el('span', null, 'Auto-play voice replies when available')]),
      webRuntime ? null : el('label', { class: 'us-check' }, [autoUpdate,
        el('span', null, 'Automatically install AGiXT Desktop updates when available')]),
      el('div', { class: 'us-section-row end' }, [saveBehaviorBtn]),
    ].filter(Boolean);
    panel.appendChild(section('Behavior', null, behaviorRows));

    // Desktop updates and Privileged commands only render in the native
    // Tauri shell. The hosted web runtime auto-updates itself the same
    // way any other site does, and has no privileged-command surface to
    // store sudo credentials for.
    if (webRuntime) return;

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
    // Visual layout mirrors mobile/lib/screens/settings_screen.dart so users
    // moving between the Flutter app and the desktop client see the same
    // hierarchy: gradient hero with at-a-glance status chips, then an
    // adaptive "Live connection" card whose action buttons change based on
    // supported/scanning/connected/has-saved-device, then the behavior /
    // dashboard / display-fit / test panels (which keep the dense layout
    // since they're for power-user tuning).
    panel.innerHTML = '';
    let settings = await loadDesktopSettings(true);
    let status = null;

    // ─── Hero ─────────────────────────────────────────────────────────
    const heroChips = el('div', {
      class: 'g1-hero-chips',
      dataset: { usTest: 'g1-hero-chips' },
    });
    const hero = el('div', { class: 'g1-hero' }, [
      el('div', { class: 'g1-hero-row' }, [
        el('div', { class: 'g1-hero-icon' }, '👓'),
        el('div', { class: 'g1-hero-title-wrap' }, [
          el('h2', { class: 'g1-hero-title' }, 'Even Realities G1'),
          el('p', { class: 'g1-hero-sub' },
            'Keep your G1 glasses connected and tuned to your day.'),
        ]),
      ]),
      heroChips,
    ]);
    panel.appendChild(hero);

    // ─── Live connection card ─────────────────────────────────────────
    const statusBanner = el('div', {
      class: 'g1-status-banner disconnected',
      dataset: { usTest: 'g1-status-banner' },
    });
    const statusIcon = el('div', { class: 'g1-status-banner-icon' }, '•');
    const statusTitle = el('p', {
      class: 'g1-status-banner-title',
      dataset: { usTest: 'g1-status-title' },
    }, 'Checking…');
    const statusBody = el('p', {
      class: 'g1-status-banner-body',
      dataset: { usTest: 'g1-status' },
    }, '');
    statusBanner.append(
      statusIcon,
      el('div', { class: 'g1-status-banner-text' }, [statusTitle, statusBody]),
    );

    const actionsRow = el('div', {
      class: 'g1-actions',
      dataset: { usTest: 'g1-actions' },
    });
    const batteryGrid = el('div', {
      class: 'g1-batt-grid',
      dataset: { usTest: 'g1-batteries' },
    });
    batteryGrid.hidden = true;

    const liveSection = section('Live connection', null, [
      statusBanner,
      actionsRow,
      batteryGrid,
    ]);
    panel.appendChild(liveSection);

    function glassesStatusMessage(fallback) {
      const message = fallback || '';
      if (/le-connection-abort|link dropped before GATT|failed to discover services|Authentication/i.test(message)) {
        return `${message} If phone Bluetooth is already off, unpair G1 in the Even app, forget both G1 devices in phone Bluetooth settings, quick-restart the glasses, then try Connect again.`;
      }
      return message;
    }

    function batteryLevelClass(pct) {
      if (pct >= 80) return 'level-excellent';
      if (pct >= 60) return 'level-good';
      if (pct >= 40) return 'level-fair';
      if (pct >= 20) return 'level-low';
      return 'level-critical';
    }

    function lowestBattery(s) {
      const left = s && s.battery && s.battery.left ? s.battery.left.percentage : null;
      const right = s && s.battery && s.battery.right ? s.battery.right.percentage : null;
      if (left == null && right == null) return null;
      if (left == null) return right;
      if (right == null) return left;
      return Math.min(left, right);
    }

    function anyCharging(s) {
      return Boolean(
        (s && s.battery && s.battery.left && s.battery.left.is_charging) ||
        (s && s.battery && s.battery.right && s.battery.right.is_charging),
      );
    }

    function relativeTime(ts) {
      if (!ts) return null;
      const then = Date.parse(ts);
      if (Number.isNaN(then)) return null;
      const diff = Math.max(0, Date.now() - then);
      if (diff < 60_000) return 'just now';
      if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
      if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
      return `${Math.floor(diff / 86_400_000)}d ago`;
    }

    function chip(label, kind, leading) {
      return el('span', { class: 'g1-chip' + (kind ? ' ' + kind : '') }, [
        leading || el('span', { class: 'g1-chip-dot' }),
        document.createTextNode(label),
      ]);
    }

	    function renderHeroChips(s) {
	      heroChips.innerHTML = '';
      if (!s) {
        heroChips.appendChild(chip('Loading…', ''));
        return;
      }
      if (!s.supported) {
        heroChips.appendChild(chip('Not supported on this platform', 'disconnected'));
        return;
      }
	      if (s.scanning) {
	        heroChips.appendChild(chip('Scanning for glasses…', 'scanning',
	          el('span', { class: 'g1-spinner' })));
	      } else if (s.connected) {
	        heroChips.appendChild(chip('Connected', 'connected'));
	        const names = [s.left && s.left.name, s.right && s.right.name]
	          .filter(Boolean)
	          .join(' + ');
	        if (names) {
	          heroChips.appendChild(chip(names, ''));
	        }
	      } else {
	        heroChips.appendChild(chip('Disconnected', 'disconnected'));
	      }

      const pct = lowestBattery(s);
      if (pct != null) {
        const charging = anyCharging(s);
        heroChips.appendChild(chip(
          `${pct}%${charging ? ' · Charging' : ''}`,
          '',
          el('span', { class: 'g1-chip-icon' }, charging ? '⚡' : '🔋'),
        ));
      } else if (s.connected) {
        heroChips.appendChild(chip('Battery unavailable', '',
          el('span', { class: 'g1-chip-icon' }, '🔋')));
      }

      const updated = relativeTime(s.battery && s.battery.last_updated);
      if (updated) {
        heroChips.appendChild(chip(`Updated ${updated}`, '',
          el('span', { class: 'g1-chip-icon' }, '⟳')));
      }
    }

    function renderBatteryGrid(s) {
      batteryGrid.innerHTML = '';
      if (!s || !s.connected) { batteryGrid.hidden = true; return; }
      const entries = [
        { label: 'Left', device: s.left, battery: s.battery && s.battery.left },
        { label: 'Right', device: s.right, battery: s.battery && s.battery.right },
      ];
      // Show the grid only if we actually have a battery reading on either
      // side — otherwise the empty placeholders look broken.
      const anyData = entries.some((e) => e.battery || e.device);
      if (!anyData) { batteryGrid.hidden = true; return; }
      batteryGrid.hidden = false;
      entries.forEach((entry) => {
        const pct = entry.battery ? entry.battery.percentage : null;
        const card = el('div', {
          class: 'g1-batt' + (pct != null ? ' ' + batteryLevelClass(pct) : ''),
          dataset: { usTest: `g1-battery-${entry.label.toLowerCase()}` },
        }, [
          el('div', { class: 'g1-batt-head' }, [
            el('span', { class: 'g1-batt-label' }, `${entry.label} lens`),
            el('span', { class: 'g1-batt-pct' }, pct != null ? `${pct}%` : '—'),
          ]),
          el('div', { class: 'g1-batt-bar' }, [
            el('div', {
              class: 'g1-batt-bar-fill',
              style: `width: ${pct != null ? Math.max(2, pct) : 0}%`,
            }),
          ]),
          el('p', { class: 'g1-batt-meta' },
            entry.battery
              ? (entry.battery.is_charging ? '⚡ Charging' : `Voltage ${entry.battery.voltage}`)
              : (entry.device ? `Paired · ${entry.device.name}` : 'Not paired')),
        ]);
        batteryGrid.appendChild(card);
      });
    }

    function renderActions(s) {
      actionsRow.innerHTML = '';
      if (!s || !s.supported) return;

      if (s.scanning) {
        // Scanning has no actionable buttons — the connect call kicked off
        // is what we're waiting on. Show a single muted disabled hint so
        // the action area doesn't collapse and shift the layout.
        const b = btn('Scanning…', { disabled: true });
        b.dataset.usTest = 'g1-scanning';
        actionsRow.appendChild(b);
        return;
      }

      if (s.connected) {
        const disconnectBtn = btn('Disconnect', {
          onclick: () => runStatusCommand('Disconnect', () => (
            window.AgixtG1 ? window.AgixtG1.disconnect() : invoke('g1_disconnect')
          )),
        });
        disconnectBtn.dataset.usTest = 'g1-disconnect';
        const syncBtn = btn('Sync now', {
          kind: 'primary',
          onclick: () => runStatusCommand('Sync now', () => (
            window.AgixtG1 ? window.AgixtG1.sync() : invoke('g1_sync')
          )),
        });
        syncBtn.dataset.usTest = 'g1-sync';
        const batteryBtn = btn('Refresh battery', {
          onclick: () => runStatusCommand('Battery', () => (
            window.AgixtG1 ? window.AgixtG1.requestBattery() : invoke('g1_request_battery')
          )),
        });
        batteryBtn.dataset.usTest = 'g1-battery';
        actionsRow.append(syncBtn, batteryBtn, disconnectBtn);
        return;
      }

      // Disconnected — promote "Reconnect saved" if we have a saved device
      // on either side, fall back to "Connect" scan otherwise. This matches
      // the mobile experience where the primary CTA is whatever the user
      // most likely wants next.
      const hasSaved = Boolean((s.left && s.left.id) || (s.right && s.right.id));
      if (hasSaved) {
        const reconnectBtn = btn('Reconnect saved glasses', {
          kind: 'primary',
          onclick: () => runStatusCommand('Reconnect saved', () => (
            window.AgixtG1 ? window.AgixtG1.reconnectSaved() : invoke('g1_reconnect_saved')
          )),
        });
        reconnectBtn.dataset.usTest = 'g1-reconnect';
        reconnectBtn.classList.add('full');
        const connectBtn = btn('Pair different glasses', {
          onclick: () => runStatusCommand('Connect', () => (
            window.AgixtG1 ? window.AgixtG1.scanAndConnect() : invoke('g1_scan_and_connect')
          )),
        });
        connectBtn.dataset.usTest = 'g1-connect';
        actionsRow.append(reconnectBtn, connectBtn);
      } else {
        const connectBtn = btn('Connect glasses', {
          kind: 'primary',
          onclick: () => runStatusCommand('Connect', () => (
            window.AgixtG1 ? window.AgixtG1.scanAndConnect() : invoke('g1_scan_and_connect')
          )),
        });
        connectBtn.dataset.usTest = 'g1-connect';
        connectBtn.classList.add('full');
        actionsRow.appendChild(connectBtn);
      }
    }

    function renderStatus(next) {
      const prevConnected = !!(status && status.connected);
      status = next || status;
      if (!status) {
        statusBanner.className = 'g1-status-banner error';
        statusIcon.textContent = '!';
        statusTitle.textContent = 'Status unavailable';
        statusBody.textContent = 'Could not reach the glasses controller.';
        renderHeroChips(null);
        renderActions(null);
        renderBatteryGrid(null);
        updateSettingsGate(false);
        return;
      }

      if (!status.supported) {
        statusBanner.className = 'g1-status-banner error';
        statusIcon.textContent = '⚠';
        statusTitle.textContent = 'Not supported on this platform';
        statusBody.textContent = glassesStatusMessage(status.last_error)
          || 'AGiXT can\'t talk to the G1 glasses from this OS build.';
      } else if (status.scanning) {
        statusBanner.className = 'g1-status-banner scanning';
        statusIcon.innerHTML = '';
        statusIcon.appendChild(el('span', { class: 'g1-spinner' }));
        statusTitle.textContent = 'Scanning for your glasses…';
        statusBody.textContent = 'Make sure the G1 case is open and the glasses are nearby.';
      } else if (status.connected) {
        statusBanner.className = 'g1-status-banner connected';
        statusIcon.textContent = '✓';
        const left = status.left ? status.left.name : null;
        const right = status.right ? status.right.name : null;
        const name = left && right && left.replace(/_L_?$/i, '') === right.replace(/_R_?$/i, '')
          ? left.replace(/_L_?$/i, '')
          : (left || right || 'Even Realities G1');
        statusTitle.textContent = `Connected to ${name}`;
        statusBody.textContent = status.last_event
          || 'Your glasses are synced and receiving updates.';
      } else {
        const hasSaved = Boolean((status.left && status.left.id) || (status.right && status.right.id));
        statusBanner.className = 'g1-status-banner disconnected';
        statusIcon.textContent = '○';
        statusTitle.textContent = hasSaved
          ? 'Saved glasses are offline'
          : 'No glasses paired yet';
        statusBody.textContent = glassesStatusMessage(status.last_error || status.last_event)
          || (hasSaved
            ? 'Tap reconnect to wake your saved glasses and resume updates.'
            : 'Tap connect to scan for your G1 and pair them with AGiXT.');
      }

      renderHeroChips(status);
      renderActions(status);
      renderBatteryGrid(status);
      updateSettingsGate(status.connected, prevConnected);
    }

    /** Show settings only when glasses are connected. On the
     *  transition into "connected", flip g1_enabled on automatically
     *  and persist it — the user explicitly paired, so the integration
     *  should be live without an extra click. */
    function updateSettingsGate(connected, prevConnected) {
      if (!settingsContainer) return;
      settingsContainer.hidden = !connected;
      offlineHint.hidden = !!connected;
      if (connected && prevConnected === false && enabled && !enabled.checked) {
        enabled.checked = true;
        // Persist the auto-enable so it sticks across restarts. Errors
        // here are non-fatal — the user can still flip the toggle by
        // hand if the save fails for some reason.
        const next = { ...settings, g1_enabled: true };
        invoke('save_settings', { settings: next })
          .then((saved) => {
            settings = saved;
            cache.desktopSettings = saved;
            if (window.AgixtG1 && typeof window.AgixtG1.syncSettings === 'function') {
              window.AgixtG1.syncSettings(saved);
            }
          })
          .catch((err) => console.warn('Failed to auto-enable G1 integration:', err));
      }
    }

    async function refresh() {
      try {
        const next = window.AgixtG1 && typeof window.AgixtG1.refreshStatus === 'function'
          ? await window.AgixtG1.refreshStatus()
          : await invoke('g1_status');
        renderStatus(next);
        return next;
      } catch (err) {
        statusBanner.className = 'g1-status-banner error';
        statusIcon.textContent = '!';
        statusTitle.textContent = 'Status unavailable';
        statusBody.textContent = errMsg(err);
        return null;
      }
    }

    async function runStatusCommand(label, command) {
      statusTitle.textContent = `${label}…`;
      try {
        const next = await command();
        renderStatus(next);
        if (/connect/i.test(label)) settings = await loadDesktopSettings(true).catch(() => settings);
        toast(label + ' complete', 'success');
        return next;
      } catch (err) {
        statusBanner.className = 'g1-status-banner error';
        statusIcon.textContent = '!';
        statusTitle.textContent = `${label} failed`;
        statusBody.textContent = errMsg(err);
        toast(errMsg(err), 'error');
        return null;
      }
    }

    // ─── Focus & presence (silent mode toggle) ────────────────────────
    // Mobile parity: silent mode is the inverse of g1_display_enabled.
    // When silent mode is on, the display is paused — no timeline, no
    // notifications, no assistant streaming — until the user flips it off.
    const silentInput = el('input', { type: 'checkbox', dataset: { usTest: 'g1-silent' } });
    silentInput.checked = settings.g1_display_enabled === false;
    const silentSwitch = el('label', { class: 'g1-switch' }, [
      silentInput,
      el('span', { class: 'g1-switch-track' }),
      el('span', { class: 'g1-switch-thumb' }),
    ]);
    silentInput.addEventListener('change', async () => {
      // Persist immediately so toggling feels instant; if connected, push
      // the new silent state to the glasses straight away.
      const next = { ...settings, g1_display_enabled: !silentInput.checked };
      try {
        const saved = await invoke('save_settings', { settings: next });
        settings = saved;
        cache.desktopSettings = saved;
        if (window.AgixtG1 && typeof window.AgixtG1.syncSettings === 'function') {
          window.AgixtG1.syncSettings(saved);
        }
        if (status && status.connected) {
          try { await invoke('g1_set_silent_mode', { enabled: silentInput.checked }); } catch (_) {}
          if (silentInput.checked) {
            try { await invoke('g1_clear_display'); } catch (_) {}
          }
        }
        toast(silentInput.checked ? 'Silent mode on' : 'Silent mode off', 'success');
      } catch (err) {
        silentInput.checked = !silentInput.checked;
        toast(errMsg(err), 'error');
      }
    });

    // All the settings sections below (Focus & presence, Behavior,
    // Dashboard, Display Fit, Test and Save) only make sense once a
    // pair of glasses is actually connected — otherwise the toggles
    // mutate state that has nothing to drive. We wrap them in a
    // settings container that renderStatus() shows/hides based on
    // `status.connected`, and substitute a help card when offline.
    const settingsContainer = el('div', {
      class: 'g1-settings-container',
      dataset: { usTest: 'g1-settings-container' },
    });
    const offlineHint = el('div', {
      class: 'us-empty',
      dataset: { usTest: 'g1-offline-hint' },
    }, 'Connect your G1 glasses above to configure dashboard, display, and notification settings.');
    panel.appendChild(settingsContainer);
    panel.appendChild(offlineHint);

    settingsContainer.appendChild(section('Focus & presence', null, [
      el('div', { class: 'g1-toggle-row' }, [
        el('div', { class: 'g1-toggle-text' }, [
          el('p', { class: 'g1-toggle-title' }, 'Silent mode'),
          el('p', { class: 'g1-toggle-sub' },
            'Pause timeline updates and notifications on your glasses until you turn this back off.'),
        ]),
        silentSwitch,
      ]),
    ]));

    // ─── Behavior ─────────────────────────────────────────────────────
    const enabled = el('input', { type: 'checkbox', dataset: { usTest: 'g1-enabled' } });
    enabled.checked = !!settings.g1_enabled;
    const showAi = el('input', { type: 'checkbox', dataset: { usTest: 'g1-show-ai' } });
    showAi.checked = settings.g1_show_ai_responses !== false;
    const forwardNotifications = el('input', { type: 'checkbox', dataset: { usTest: 'g1-forward-notifications' } });
    forwardNotifications.checked = settings.g1_notification_forwarding !== false;
    const autoConnect = el('input', { type: 'checkbox', dataset: { usTest: 'g1-auto-connect' } });
    autoConnect.checked = settings.g1_auto_connect !== false;

    settingsContainer.appendChild(section('Behavior', null, [
      el('label', { class: 'us-check' }, [enabled, el('span', null, 'Enable G1 glasses integration')]),
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

    settingsContainer.appendChild(section('Dashboard', null, [
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

    settingsContainer.appendChild(section('Display Fit', null, [
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
        // Silent mode is the user-facing inverse of g1_display_enabled —
        // see Focus & presence toggle above.
        g1_display_enabled: !silentInput.checked,
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
            await invoke('g1_set_silent_mode', { enabled: silentInput.checked });
          }
          await refresh();
          toast('Display settings applied', 'success');
        } catch (err) {
          toast(errMsg(err), 'error');
        }
      },
    });
    applyDisplayBtn.dataset.usTest = 'g1-apply-display';

    settingsContainer.appendChild(section('Test and Save', null, [
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
      statusEl.className = 'us-status-line ' + (result.installed ? 'success' : '');
      if (result.installed && result.restart_required) {
        statusEl.textContent = 'Update installed. Restarting AGiXT Desktop…';
        // Give the user a moment to read the message before the app re-execs.
        window.setTimeout(() => {
          invoke('desktop_restart_app').catch((e) => {
            statusEl.textContent = 'Update installed. Please restart AGiXT Desktop to finish.';
            statusEl.className = 'us-status-line success';
            console.error('desktop_restart_app failed', e);
          });
        }, 1500);
        return;
      }
      statusEl.textContent = result.message || 'Update installed.';
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

    // Timezone — IANA zone for timestamps/scheduling. Defaults to the
    // browser-resolved zone so users don't have to type the full identifier.
    const accountPrefs = user.preferences || {};
    const browserTz = (() => {
      try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'; }
      catch (_) { return 'UTC'; }
    })();
    const tzInput = el('input', {
      class: 'us-input',
      placeholder: browserTz,
      value: accountPrefs.timezone || '',
    });
    const saveTzBtn = btn('Save', { kind: 'primary', onclick: async () => {
      const value = tzInput.value.trim();
      try {
        await api.updateUser({ timezone: value });
        toast('Timezone saved', 'success');
        cache.user = null;
      } catch (err) { toast(errMsg(err), 'error'); }
    } });
    const useBrowserTzBtn = btn('Use browser zone (' + browserTz + ')',
      { onclick: () => { tzInput.value = browserTz; } });
    panel.appendChild(section('Timezone',
      'IANA zone identifier (e.g. America/Chicago). Used for timestamps and scheduling.',
      [
        tzInput,
        el('div', { class: 'us-section-row' }, [useBrowserTzBtn, saveTzBtn]),
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
          const rawProvider = p.name || p.slug || p.provider || '';
          const slug = api.oauthEndpointSlug ? api.oauthEndpointSlug(rawProvider) : api.redirectSlug(rawProvider);
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

  // ─── Notifications tab — per-category notification preferences ───────

  // Mirrors web/lib/notification-preferences.ts so the desktop and web
  // UIs stay in lock-step. Defaults match exactly so a user toggling on
  // one platform sees the same starting state on the other.
  const NOTIF_DEFAULT_TICKET_ACTIONS = {
    create: true, update: false, delete: true, assigned: true,
    status_change: true, note_added: true, accessed: false, pending_approval: false,
  };
  const NOTIF_DEFAULT_MACHINE_MINE = {
    create: true, update: false, delete: true, assigned: false,
    status_change: true, note_added: false, accessed: false, pending_approval: true,
  };
  const NOTIF_DEFAULTS_DISABLED = {
    create: false, update: false, delete: false, assigned: false,
    status_change: false, note_added: false, accessed: false, pending_approval: false,
  };
  const NOTIF_DEFAULT_PREFERENCES = {
    enabled: true,
    categories: {
      ticket_mine: { enabled: true, actions: { ...NOTIF_DEFAULT_TICKET_ACTIONS } },
      ticket_other: { enabled: false,
        actions: { ...NOTIF_DEFAULT_TICKET_ACTIONS, assigned: false, note_added: false } },
      machine_mine: { enabled: true, actions: { ...NOTIF_DEFAULT_MACHINE_MINE } },
      machine_other: { enabled: false, actions: { ...NOTIF_DEFAULTS_DISABLED } },
      asset: { enabled: false, actions: { ...NOTIF_DEFAULTS_DISABLED } },
      contact: { enabled: false, actions: { ...NOTIF_DEFAULTS_DISABLED } },
      secret: { enabled: false, actions: { ...NOTIF_DEFAULTS_DISABLED } },
      company: { enabled: false, actions: { ...NOTIF_DEFAULTS_DISABLED } },
    },
  };

  // Display metadata — labels, descriptions, grouping. Keep parity with
  // web/app/user/settings/page.tsx ENTITY_META.
  const NOTIF_ENTITY_META = {
    ticket_mine: { label: 'Your Tickets',
      description: 'Tickets assigned to you — assignments, status changes, and notes',
      group: 'Tickets' },
    ticket_other: { label: 'Other Tickets',
      description: 'Tickets not assigned to you', group: 'Tickets' },
    machine_mine: { label: 'Your Machines',
      description: 'Machines in your company — registration, approvals, and status',
      group: 'Machines' },
    machine_other: { label: 'Other Machines',
      description: 'Machines outside your company', group: 'Machines' },
    asset: { label: 'Assets',
      description: 'Asset creation, updates, and deletions' },
    contact: { label: 'Contacts',
      description: 'Contact creation and modifications' },
    secret: { label: 'Secrets',
      description: 'Secret creation, access, and rotation' },
    company: { label: 'Companies',
      description: 'Company profile changes and updates' },
  };

  const NOTIF_ORDERED_CATEGORIES = [
    'ticket_mine', 'ticket_other',
    'machine_mine', 'machine_other',
    'asset', 'contact', 'secret', 'company',
  ];

  // Hide actions that don't apply to a given category — same map as web.
  const NOTIF_HIDDEN_ACTIONS = {
    ticket_mine: ['pending_approval'],
    ticket_other: ['pending_approval'],
    machine_mine: ['assigned', 'note_added'],
    machine_other: ['assigned', 'note_added'],
    asset: ['assigned', 'note_added', 'pending_approval'],
    contact: ['assigned', 'status_change', 'note_added', 'accessed', 'pending_approval'],
    secret: ['assigned', 'status_change', 'note_added', 'pending_approval'],
    company: ['assigned', 'note_added', 'status_change', 'pending_approval'],
  };

  const NOTIF_ACTION_LABELS = {
    create: 'Created', update: 'Updated', delete: 'Deleted',
    assigned: 'Assigned', status_change: 'Status Changed', note_added: 'Note Added',
    accessed: 'Accessed / Viewed', pending_approval: 'Pending Approval',
  };

  /** Deep-clone the defaults so callers can mutate without poisoning. */
  function notifCloneDefaults() {
    return JSON.parse(JSON.stringify(NOTIF_DEFAULT_PREFERENCES));
  }

  /** Parse stored preferences (string or object), merging with defaults. */
  function parseNotifPrefs(raw) {
    if (!raw) return notifCloneDefaults();
    let parsed = raw;
    if (typeof raw === 'string') {
      try { parsed = JSON.parse(raw); } catch (_) { return notifCloneDefaults(); }
    }
    if (!parsed || typeof parsed !== 'object') return notifCloneDefaults();
    const result = notifCloneDefaults();
    if (typeof parsed.enabled === 'boolean') result.enabled = parsed.enabled;
    const cats = parsed.categories;
    if (cats && typeof cats === 'object') {
      // Migrate legacy flat "ticket" → ticket_mine + ticket_other.
      if (cats.ticket && !cats.ticket_mine) {
        cats.ticket_mine = cats.ticket;
        if (!cats.ticket_other) cats.ticket_other = { ...cats.ticket, enabled: false };
      }
      if (cats.machine && !cats.machine_mine) {
        cats.machine_mine = cats.machine;
        if (!cats.machine_other) cats.machine_other = { ...cats.machine, enabled: false };
      }
      Object.keys(result.categories).forEach((key) => {
        const saved = cats[key];
        if (saved && typeof saved === 'object') {
          if (typeof saved.enabled === 'boolean') result.categories[key].enabled = saved.enabled;
          if (saved.actions && typeof saved.actions === 'object') {
            Object.entries(saved.actions).forEach(([action, val]) => {
              if (typeof val === 'boolean' && action in result.categories[key].actions) {
                result.categories[key].actions[action] = val;
              }
            });
          }
        }
      });
    }
    return result;
  }

  async function renderNotifications(panel) {
    panel.innerHTML = '';
    panel.appendChild(emptyState('Loading notification preferences…'));
    let user;
    try { user = await loadUser(); } catch (err) {
      panel.innerHTML = '';
      panel.appendChild(section('Notifications', null,
        [el('p', { class: 'us-hint error' }, errMsg(err))]));
      return;
    }
    if (!user) {
      panel.innerHTML = '';
      panel.appendChild(emptyState('Sign in to manage notification preferences.'));
      return;
    }
    panel.innerHTML = '';
    const prefs = user.preferences || {};
    const rawNotif = (prefs && (prefs.raw || prefs)) || {};
    let state = parseNotifPrefs(rawNotif.notification_preferences);
    let saved = JSON.parse(JSON.stringify(state));

    // Master toggle row with reset-to-defaults button.
    const masterSwitch = el('input', { type: 'checkbox' });
    masterSwitch.checked = state.enabled !== false;
    const masterTitle = el('p', { class: 'us-list-item-title' }, 'Enable Notifications');
    const masterBlurb = el('p', { class: 'us-list-item-meta' }, '');
    const updateMasterBlurb = () => {
      masterBlurb.textContent = state.enabled
        ? 'You will receive notifications based on your settings below.'
        : 'All notifications are currently disabled.';
    };
    updateMasterBlurb();

    const resetBtn = btn('Reset to defaults', { onclick: () => {
      state = notifCloneDefaults();
      masterSwitch.checked = state.enabled;
      updateMasterBlurb();
      rerenderCategories();
      updateSaveBar();
    } });

    const categoriesHost = el('div', { class: 'us-notif-categories' });

    function rerenderCategories() {
      categoriesHost.innerHTML = '';
      let lastGroup = null;
      NOTIF_ORDERED_CATEGORIES.forEach((key) => {
        const meta = NOTIF_ENTITY_META[key];
        const cat = state.categories[key];
        if (!meta || !cat) return;
        if (meta.group && meta.group !== lastGroup) {
          categoriesHost.appendChild(el('p',
            { class: 'us-notif-group-header' }, meta.group));
          lastGroup = meta.group;
        }
        const catToggle = el('input', { type: 'checkbox' });
        catToggle.checked = cat.enabled;
        catToggle.addEventListener('change', () => {
          cat.enabled = catToggle.checked;
          rerenderCategories();
          updateSaveBar();
        });
        const hidden = NOTIF_HIDDEN_ACTIONS[key] || [];
        const actionsGrid = el('div', { class: 'us-notif-actions' });
        if (cat.enabled) {
          Object.entries(cat.actions).forEach(([action, enabled]) => {
            if (hidden.includes(action)) return;
            const label = NOTIF_ACTION_LABELS[action] || action;
            const actionToggle = el('input', { type: 'checkbox' });
            actionToggle.checked = !!enabled;
            actionToggle.addEventListener('change', () => {
              cat.actions[action] = actionToggle.checked;
              if (actionToggle.checked && !cat.enabled) {
                cat.enabled = true;
                rerenderCategories();
              }
              updateSaveBar();
            });
            actionsGrid.appendChild(el('label',
              { class: 'us-notif-action' },
              [el('span', null, label), actionToggle]));
          });
        }
        const card = el('div', { class: 'us-notif-card' + (cat.enabled ? '' : ' is-disabled') }, [
          el('div', { class: 'us-notif-card-head' }, [
            el('div', { class: 'us-notif-card-meta' }, [
              el('p', { class: 'us-notif-card-title' }, meta.label),
              el('p', { class: 'us-notif-card-desc' }, meta.description),
            ]),
            catToggle,
          ]),
          cat.enabled ? actionsGrid : null,
        ].filter(Boolean));
        categoriesHost.appendChild(card);
      });
      categoriesHost.classList.toggle('is-master-off', !state.enabled);
    }

    masterSwitch.addEventListener('change', () => {
      state.enabled = masterSwitch.checked;
      updateMasterBlurb();
      rerenderCategories();
      updateSaveBar();
    });

    // Save bar — sticky-style row at the bottom with Discard + Save.
    const discardBtn = btn('Discard', { onclick: () => {
      state = JSON.parse(JSON.stringify(saved));
      masterSwitch.checked = state.enabled !== false;
      updateMasterBlurb();
      rerenderCategories();
      updateSaveBar();
    } });
    const saveBtn = btn('Save', { kind: 'primary', onclick: async () => {
      saveBtn.disabled = true;
      try {
        await api.updateUser({ notification_preferences: JSON.stringify(state) });
        saved = JSON.parse(JSON.stringify(state));
        cache.user = null;
        toast('Notification preferences saved', 'success');
        updateSaveBar();
      } catch (err) {
        toast(errMsg(err), 'error');
      } finally {
        saveBtn.disabled = false;
      }
    } });
    const saveBar = el('div', { class: 'us-notif-save-bar', hidden: true }, [
      el('span', { class: 'us-notif-save-msg' }, 'You have unsaved notification changes'),
      discardBtn,
      saveBtn,
    ]);
    function hasUnsavedNotifChanges() {
      return JSON.stringify(state) !== JSON.stringify(saved);
    }
    function updateSaveBar() {
      saveBar.hidden = !hasUnsavedNotifChanges();
    }

    panel.appendChild(section('Notifications',
      'Pick which activity should send you a notification.',
      [
        el('div', { class: 'us-section-row between' }, [
          el('div', { class: 'us-list-item-grow' }, [masterTitle, masterBlurb]),
          el('div', { class: 'us-section-row' }, [resetBtn, masterSwitch]),
        ]),
      ]));
    panel.appendChild(categoriesHost);
    panel.appendChild(saveBar);
    rerenderCategories();
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

  /** The Glasses tab drives Bluetooth + native Tauri commands that the
   *  hosted web runtime can't reach. Hide both the tab button and its
   *  panel so the section never gets activated in browser mode. */
  function hideDesktopOnlyTabs() {
    if (!isWebRuntime()) return;
    const tab = document.querySelector('.us-tab[data-us-tab="glasses"]');
    if (tab) tab.hidden = true;
    const panel = document.querySelector('.us-panel[data-us-panel="glasses"]');
    if (panel) panel.hidden = true;
  }

  /** Reveal the Super Admin tab only for users with role_id 0 in any
   *  of their companies (mirrors the web's billing/admin page gate). */
  async function ensureSuperAdminTabVisible() {
    const tab = document.querySelector('.us-tab[data-us-tab="superadmin"]');
    if (!tab) return false;
    const user = await loadUser().catch(() => null);
    const allow = userIsSuperAdmin(user);
    tab.hidden = !allow;
    return allow;
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
  const CHECKOUT_OPEN_TTL_MS = 10 * 60 * 1000;
  const checkoutOpenLocks = new Map();
  const openedCheckoutSessions = new Map();
  let billingRouteReturn = null;

  function pruneCheckoutGuards() {
    const now = Date.now();
    for (const [key, startedAt] of checkoutOpenLocks.entries()) {
      if (now - startedAt > CHECKOUT_OPEN_TTL_MS) checkoutOpenLocks.delete(key);
    }
    for (const [sessionId, openedAt] of openedCheckoutSessions.entries()) {
      if (now - openedAt > CHECKOUT_OPEN_TTL_MS) openedCheckoutSessions.delete(sessionId);
    }
  }

  function beginCheckoutOpen(key) {
    pruneCheckoutGuards();
    if (!key) return true;
    if (checkoutOpenLocks.has(key)) return false;
    checkoutOpenLocks.set(key, Date.now());
    return true;
  }

  function releaseCheckoutOpen(key) {
    if (key) checkoutOpenLocks.delete(key);
  }

  function openCheckoutUrlOnce(url, sessionId) {
    pruneCheckoutGuards();
    const id = sessionId || checkoutSessionIdFromUrl(url);
    if (id && openedCheckoutSessions.has(id)) return false;
    if (id) openedCheckoutSessions.set(id, Date.now());
    openExternal(url);
    return true;
  }

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

  function checkoutSessionIdFromUrl(url) {
    const match = String(url || '').match(/cs_(?:test|live)_[A-Za-z0-9_]+/);
    return match ? match[0] : null;
  }

  function normalizeBillingReturn(data) {
    if (!data || typeof data !== 'object') return null;
    const sessionId = String(
      data.session_id || data.checkout_session_id || data.checkoutSessionId || '',
    ).trim();
    const success = data.success === true || data.success === 'true';
    const canceled = data.canceled === true || data.cancelled === true
      || data.canceled === 'true' || data.cancelled === 'true';
    if (!sessionId && !success && !canceled) return null;
    return {
      session_id: sessionId,
      success,
      canceled,
      synced: false,
      result: null,
      error: null,
    };
  }

  function handleBillingReturn(data) {
    const normalized = normalizeBillingReturn(data);
    if (normalized) billingRouteReturn = normalized;
  }

  function companyIdFromBillingSyncResult(result) {
    const items = result && Array.isArray(result.synced) ? result.synced : [];
    const item = items.find((entry) =>
      entry && entry.company_id && entry.completed !== false);
    return item ? item.company_id : null;
  }

  async function syncBillingRouteReturn() {
    const payment = billingRouteReturn;
    if (!payment || payment.synced || payment.canceled || !payment.session_id || !api.syncBilling) {
      return payment ? payment.result : null;
    }
    payment.synced = true;
    try {
      const result = await api.syncBilling(null, payment.session_id);
      payment.result = result;
      payment.error = null;
      cache.planLimits = null;
      cache.autoTopup = null;
      cache.transactions = null;
      if ((result && Number(result.synced_count || 0) > 0)
          || (Array.isArray(result && result.synced) && result.synced.length > 0)) {
        clearPendingPayment();
      }
      return result;
    } catch (err) {
      payment.synced = false;
      payment.error = err;
      console.warn('billing return sync failed', err);
      return null;
    }
  }

  async function syncPendingPayment(payment, companyId) {
    if (!payment || !companyId || !api.syncBilling) return null;
    if (payment.company_id && payment.company_id !== companyId) return null;
    const sessionId = payment.checkout_session_id || payment.session_id || null;
    try {
      const result = await api.syncBilling(companyId, sessionId);
      cache.planLimits = null;
      cache.autoTopup = null;
      cache.transactions = null;
      return result;
    } catch (err) {
      console.warn('billing sync failed', err);
      return null;
    }
  }

  // Banner DOM: surfaced at the top of the billing panel when a pending
  // payment marker exists. Distinguishes four phases:
  //   pending (<5 min)     → "Finishing your payment…"
  //   waiting (5-15 min)   → "Still waiting…" with Refresh
  //   likely canceled (>15 min) → "Looks like the checkout was abandoned"
  //   completed            → balance jumped past baseline
  function renderPaymentReturnBanner(payment, currentBalanceTokens, onRefresh, onDismiss, currentPlanId, currentAddonStorageBytes) {
    const baseline = Number(payment.baseline_balance_tokens || 0);
    const balance = Number(currentBalanceTokens || 0);
    const completed = payment.kind === 'plan'
      ? !!(payment.plan_id && currentPlanId && payment.plan_id === currentPlanId)
      : payment.kind === 'addon'
      ? Number(currentAddonStorageBytes || 0) > Number(payment.baseline_addon_storage_bytes || 0)
      : balance > baseline;
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
    const kindLabel = payment.kind === 'plan'
      ? 'subscription change'
      : payment.kind === 'addon'
      ? 'storage and capacity add-on'
      : 'token top-up';
    const body = completed
      ? payment.kind === 'plan'
        ? 'Your subscription change came through. The active plan is loaded in the plan section below.'
        : payment.kind === 'addon'
        ? 'Your add-on came through. The updated capacity is loaded in the plan usage section below.'
        : 'Your ' + kindLabel + ' came through. The new balance is loaded in the plan usage section below.'
      : likelyCanceled
      ? 'It has been ' + elapsedMin + ' minutes since you opened Stripe and no payment landed. The checkout was likely canceled or failed. Retry from the billing controls below, or dismiss this banner.'
      : waiting
      ? 'It has been about ' + elapsedMin + ' minutes since you opened Stripe. If you completed checkout, the billing page should update after a quick refresh.'
      : 'When you finish the ' + kindLabel + ' in your browser, return here and we will pick up the updated billing state automatically.';

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

    const routeSyncResult = await syncBillingRouteReturn();
    const routeCompanyId = companyIdFromBillingSyncResult(routeSyncResult);
    if (routeCompanyId && routeCompanyId !== activeCompany.id && user && user.companies) {
      const routedCompany = user.companies.find((company) => company.id === routeCompanyId);
      if (routedCompany) activeCompany = routedCompany;
    }
    const pendingPayment = loadPendingPayment();

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
    let autoTopupStatus = null;
    try {
      autoTopupStatus = await api.getAutoTopupStatus(activeCompany.id);
    } catch (_) {
      autoTopupStatus = null;
    }

    if (billingRouteReturn && billingRouteReturn.session_id && billingRouteReturn.success) {
      const completed = routeSyncResult
        && (Number(routeSyncResult.synced_count || 0) > 0
          || (Array.isArray(routeSyncResult.synced) && routeSyncResult.synced.length > 0));
      panel.appendChild(section(
        completed ? 'Payment complete' : 'Finishing your payment...',
        null,
        [el('p', { class: 'us-hint' }, completed
          ? 'Stripe confirmed the checkout. The current subscription, token, and add-on state is loaded in the sections below.'
          : 'Stripe sent you back successfully. If the billing status has not appeared yet, use Refresh on the payment banner below to sync it again.')],
      ));
    } else if (billingRouteReturn && billingRouteReturn.canceled) {
      panel.appendChild(section('Checkout canceled', null, [
        el('p', { class: 'us-hint' }, 'No subscription changes were made.'),
      ]));
    }

    panel.appendChild(section('Billing for ' + (activeCompany.name || 'company'),
      paymentOnly
        ? 'Complete billing to activate your ' + appName + ' account.'
        : 'Manage your ' + appName + ' subscription, credits, and payment history.'));

    const focusPlanPicker = () => {
      const picker = panel.querySelector('[data-billing-plan-picker="true"]');
      if (picker && typeof picker.scrollIntoView === 'function') {
        try { picker.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (_) {}
      }
    };
    const focusTokenTopup = () => {
      const topup = panel.querySelector('[data-billing-token-topup="true"]')
        || panel.querySelector('[data-billing-plan-picker="true"]');
      if (topup && typeof topup.scrollIntoView === 'function') {
        try { topup.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (_) {}
      }
    };
    const focusStorageAddon = () => {
      const addon = panel.querySelector('[data-billing-storage-addon="true"]')
        || panel.querySelector('[data-billing-plan-picker="true"]');
      if (addon && typeof addon.scrollIntoView === 'function') {
        try { addon.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (_) {}
      }
    };
    if (autoTopupStatus && autoTopupStatus.trial) {
      const trialBanner = renderTrialBillingBanner(autoTopupStatus.trial, pricing, focusPlanPicker);
      if (trialBanner) panel.appendChild(trialBanner);
    }

    // Pending payment banner — surfaces at the top of the panel so the
    // user knows we're tracking their Stripe handoff. We capture the
    // current balance here so the banner can detect completion.
    if (pendingPayment && pendingPayment.company_id === activeCompany.id) {
      await syncPendingPayment(pendingPayment, activeCompany.id);
    }
    let postPaymentBalance = null;
    let currentPlanId = null;
    let currentAddonStorageBytes = 0;

    // Token balance / plan summary.
    if (isTokenBased) {
      try {
        const balance = await api.getTokenBalance(activeCompany.id, true);
        postPaymentBalance = Number(balance.token_balance || 0);
        if (pendingPayment
            && pendingPayment.company_id === activeCompany.id) {
          panel.insertBefore(renderPaymentReturnBanner(
            pendingPayment,
            postPaymentBalance,
            async () => {
              await syncPendingPayment(pendingPayment, activeCompany.id);
              await renderBilling(panel);
            },
            () => renderBilling(panel),
          ), panel.firstChild);
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
        const [limitsResult, balanceResult] = await Promise.allSettled([
          api.getPlanLimits(activeCompany.id),
          api.getTokenBalance(activeCompany.id, true),
        ]);
        if (limitsResult.status === 'rejected') throw limitsResult.reason;
        const limits = limitsResult.value || {};
        const balance = balanceResult.status === 'fulfilled' ? (balanceResult.value || {}) : {};
        currentPlanId = limits.plan_id || null;
        const usage = limits.usage || {};
        const lim = limits.limits || {};
        const addons = limits.addons || {};
        currentAddonStorageBytes = Number(addons.storage_bytes || 0);
        const periodTokenLimit = Number(lim.tokens_per_month || lim.monthly_tokens || 0);
        const topupTokenBalance = Number(usage.token_balance || 0);
        const tokensThisPeriod = Number(usage.tokens_this_period || usage.tokens_used_this_period || 0);
        const totalTokenCapacity = periodTokenLimit + topupTokenBalance;
        const fallbackTokenBalance = Math.max(0, totalTokenCapacity - tokensThisPeriod);
        // /tokens/balance is the canonical remaining balance for both credit
        // and plan accounts. plan/limits keeps the split between plan allowance,
        // top-ups, and usage for display.
        postPaymentBalance = balance.token_balance != null
          ? Number(balance.token_balance || 0)
          : fallbackTokenBalance;
        if (pendingPayment && pendingPayment.company_id === activeCompany.id) {
          panel.insertBefore(renderPaymentReturnBanner(
            pendingPayment,
            postPaymentBalance,
            async () => {
              await syncPendingPayment(pendingPayment, activeCompany.id);
              await renderBilling(panel);
            },
            () => renderBilling(panel),
            currentPlanId,
            currentAddonStorageBytes,
          ), panel.firstChild);
        }
        const limitWarnings = renderPlanLimitWarnings(limits.warnings, {
          onTokenTopup: focusTokenTopup,
          onUpgradePlan: focusPlanPicker,
          onStorageAddon: focusStorageAddon,
        });
        if (limitWarnings) panel.appendChild(limitWarnings);
        const planLabel = limits.plan_id
          ? (limits.plan_name && limits.plan_name !== 'Unknown'
            ? limits.plan_name
            : pricingTierName(pricing, limits.plan_id))
          : 'No active plan';
        const tokenBalanceText = totalTokenCapacity > 0
          ? formatTokens(postPaymentBalance) + ' / ' + formatTokens(totalTokenCapacity)
          : formatTokens(postPaymentBalance);
        panel.appendChild(section('Plan: ' + planLabel, null, [
          el('dl', { class: 'us-kv-grid' }, [
            el('dt', null, 'Users'), el('dd', null, (usage.users || 0) + ' / ' + (lim.users || '∞')),
            el('dt', null, 'Devices'), el('dd', null, (usage.devices || 0) + ' / ' + (lim.devices || '∞')),
            el('dt', null, 'Tokens remaining'), el('dd', null, tokenBalanceText),
            el('dt', null, 'Tokens this period'),
            el('dd', null, formatTokens(tokensThisPeriod) + ' / ' + formatTokens(periodTokenLimit)),
            el('dt', null, 'Storage'), el('dd', null, formatStorage(usage.storage_bytes || 0)
              + (lim.storage_bytes ? ' / ' + formatStorage(lim.storage_bytes || 0) : '')),
          ]),
        ]));
      } catch (err) {
        panel.appendChild(section('Plan limits', null, [el('p', { class: 'us-hint error' }, errMsg(err))]));
      }
    }

    // Topup / change plan.
    let deferredTokenTopupSection = null;
    let deferredResourceAddonSection = null;
    if (isTokenBased) {
      const topupAmount = el('input', { class: 'us-input', type: 'number', min: 1, value: 10, placeholder: 'Token millions' });
      const topupStatus = el('span', { class: 'us-status-line' }, '');
      const topupBtn = btn('Top up with Stripe', { kind: 'primary', onclick: async () => {
        const millions = Number(topupAmount.value) || 0;
        if (millions < 1) { topupStatus.textContent = 'Enter at least 1 (million tokens).'; topupStatus.className = 'us-status-line error'; return; }
        const checkoutKey = ['token-topup', activeCompany.id || '', String(millions)].join(':');
        if (!beginCheckoutOpen(checkoutKey)) {
          topupStatus.textContent = 'Stripe checkout is already open for this top-up.';
          topupStatus.className = 'us-status-line';
          return;
        }
        topupBtn.disabled = true;
        let checkoutOpened = false;
        try {
          const res = await api.createTokenTopupStripe({ token_millions: millions, company_id: activeCompany.id });
          if (res && (res.checkout_url || res.url)) {
            const checkoutUrl = res.checkout_url || res.url;
            const sessionId = res.session_id || checkoutSessionIdFromUrl(checkoutUrl);
            // Stash a pending-payment marker with the current token
            // balance as baseline. When the user comes back, the
            // banner compares balance against this baseline to decide
            // whether the topup landed.
            savePendingPayment({
              kind: 'topup',
              company_id: activeCompany.id,
              token_millions: millions,
              checkout_session_id: sessionId,
              baseline_balance_tokens: postPaymentBalance,
            });
            checkoutOpened = openCheckoutUrlOnce(checkoutUrl, sessionId);
            topupStatus.textContent = checkoutOpened
              ? 'Opened Stripe checkout in your browser. We will pick up the new balance when you return.'
              : 'Stripe checkout is already open for this top-up.';
            topupStatus.className = checkoutOpened ? 'us-status-line success' : 'us-status-line';
          } else if (res && res.client_secret) {
            topupStatus.textContent = 'Stripe payment intent created. Complete in the web app.';
            topupStatus.className = 'us-status-line';
          }
        } catch (err) {
          topupStatus.textContent = errMsg(err); topupStatus.className = 'us-status-line error';
        } finally {
          if (!checkoutOpened) {
            releaseCheckoutOpen(checkoutKey);
            topupBtn.disabled = false;
          }
        }
      } });
      const tokenTopupSection = section('Top up tokens',
        tokenTopupBlurb(pricing) + ' Opens checkout in your browser.',
        [
          el('div', { class: 'us-section-row' }, [topupAmount, topupBtn]),
          topupStatus,
        ]);
      tokenTopupSection.dataset.billingTokenTopup = 'true';
      panel.appendChild(tokenTopupSection);
    } else {
      const topupMin = tokenTopupMinimumMillions(pricing);
      const topupPrice = tokenTopupPricePerMillion(pricing);
      const planTopupAmount = el('input', { class: 'us-input', type: 'number', min: topupMin, value: topupMin, placeholder: 'Million tokens' });
      const planTopupStatus = el('span', { class: 'us-status-line' }, '');
      const updatePlanTopupStatus = () => {
        const millions = Math.max(topupMin, Number(planTopupAmount.value) || topupMin);
        planTopupStatus.textContent = String(millions) + ' = ' + formatTokens(millions * 1000000)
          + ' tokens = ' + formatBillingAmount(millions * topupPrice);
        planTopupStatus.className = 'us-status-line';
      };
      planTopupAmount.addEventListener('input', updatePlanTopupStatus);
      const planTopupBtn = btn('Buy token top-up', { kind: 'primary', onclick: async () => {
        const tokenMillions = Math.max(topupMin, Number(planTopupAmount.value) || topupMin);
        planTopupAmount.value = tokenMillions;
        const checkoutKey = ['plan-topup', activeCompany.id || '', String(tokenMillions)].join(':');
        if (!beginCheckoutOpen(checkoutKey)) {
          planTopupStatus.textContent = 'Stripe checkout is already open for this top-up.';
          planTopupStatus.className = 'us-status-line';
          return;
        }
        planTopupBtn.disabled = true;
        let checkoutOpened = false;
        try {
          const res = await api.createPlanTopup({ company_id: activeCompany.id, token_millions: tokenMillions });
          if (res && res.checkout_url) {
            const sessionId = res.session_id || checkoutSessionIdFromUrl(res.checkout_url);
            savePendingPayment({
              kind: 'topup',
              company_id: activeCompany.id,
              token_millions: tokenMillions,
              checkout_session_id: sessionId,
              baseline_balance_tokens: postPaymentBalance,
            });
            checkoutOpened = openCheckoutUrlOnce(res.checkout_url, sessionId);
            planTopupStatus.textContent = checkoutOpened
              ? 'Stripe checkout opened. Return here when you finish — we will refresh the balance.'
              : 'Stripe checkout is already open for this top-up.';
            planTopupStatus.className = checkoutOpened ? 'us-status-line success' : 'us-status-line';
          }
        } catch (err) {
          planTopupStatus.textContent = errMsg(err);
          planTopupStatus.className = 'us-status-line error';
        } finally {
          if (!checkoutOpened) {
            releaseCheckoutOpen(checkoutKey);
            planTopupBtn.disabled = false;
          }
        }
      } });
      updatePlanTopupStatus();
      const planTokenTopupSection = section('Token top-ups (one-time)',
        'Buy extra usage for this company. One unit is 1M tokens.',
        [
        el('p', { class: 'us-hint' }, tokenTopupBlurb(pricing)),
        el('div', { class: 'us-section-row' }, [planTopupAmount, planTopupBtn]),
        planTopupStatus,
      ]);
      planTokenTopupSection.dataset.billingTokenTopup = 'true';
      deferredTokenTopupSection = planTokenTopupSection;

      if (pricing && pricing.pricing_model === 'tiered_plan' && typeof api.createPlanAddon === 'function') {
        const addon = resourceAddonConfig(pricing);
        const addonCountInput = el('input', {
          class: 'us-input',
          type: 'number',
          min: 1,
          value: 1,
          placeholder: 'Add-on count',
        });
        const addonStatus = el('span', { class: 'us-status-line' }, '');
        const updateAddonStatus = () => {
          const count = Math.max(1, Number(addonCountInput.value) || 1);
          addonStatus.textContent = String(count) + ' add-on' + (count === 1 ? '' : 's')
            + ' = +' + formatStorage(addon.storageBytes * count)
            + ', +' + formatTokens(addon.tokens * count) + ' tokens/mo'
            + ', +' + formatTokens(addon.devices * count) + ' devices'
            + ' for ' + formatBillingAmount(addon.price * count) + '/mo.';
          addonStatus.className = 'us-status-line';
        };
        addonCountInput.addEventListener('input', updateAddonStatus);
        const addonBtn = btn('Add storage and capacity', {
          kind: 'primary',
          onclick: async () => {
            const addonCount = Math.max(1, Number(addonCountInput.value) || 1);
            addonCountInput.value = addonCount;
            const checkoutKey = ['resource-addon', activeCompany.id || '', String(addonCount)].join(':');
            if (!beginCheckoutOpen(checkoutKey)) {
              addonStatus.textContent = 'Stripe checkout is already open for this add-on.';
              addonStatus.className = 'us-status-line';
              return;
            }
            addonBtn.disabled = true;
            let checkoutOpened = false;
            try {
              const res = await api.createPlanAddon({
                company_id: activeCompany.id,
                addon_count: addonCount,
              });
              if (res && res.checkout_url) {
                const sessionId = res.session_id || checkoutSessionIdFromUrl(res.checkout_url);
                savePendingPayment({
                  kind: 'addon',
                  company_id: activeCompany.id,
                  addon_count: addonCount,
                  checkout_session_id: sessionId,
                  baseline_addon_storage_bytes: currentAddonStorageBytes,
                  baseline_balance_tokens: postPaymentBalance,
                });
                checkoutOpened = openCheckoutUrlOnce(res.checkout_url, sessionId);
                addonStatus.textContent = checkoutOpened
                  ? 'Stripe checkout opened. Return here to confirm the add-on.'
                  : 'Stripe checkout is already open for this add-on.';
                addonStatus.className = checkoutOpened ? 'us-status-line success' : 'us-status-line';
              }
            } catch (err) {
              addonStatus.textContent = errMsg(err);
              addonStatus.className = 'us-status-line error';
            } finally {
              if (!checkoutOpened) {
                releaseCheckoutOpen(checkoutKey);
                addonBtn.disabled = false;
              }
            }
          },
        });
        updateAddonStatus();
        deferredResourceAddonSection = section('Storage and capacity add-ons',
          'Each add-on adds ' + formatStorage(addon.storageBytes) + ' storage, '
            + formatTokens(addon.tokens) + ' tokens/month, '
            + formatTokens(addon.devices) + ' devices, and '
            + addon.users + ' user' + (addon.users === 1 ? '' : 's')
            + ' for ' + formatBillingAmount(addon.price) + '/mo.',
          [
            el('div', { class: 'us-section-row' }, [addonCountInput, addonBtn]),
            addonStatus,
          ]);
        deferredResourceAddonSection.dataset.billingStorageAddon = 'true';
      }
      // Plan changes — production subscription picker with monthly and
      // annual billing intervals sourced from pricing.json.
      if (pricing && Array.isArray(pricing.tiers) && pricing.tiers.length) {
        const intervals = billingIntervals(pricing);
        let selectedInterval = intervals[0].id;
        const pickerWrap = el('div', { class: 'us-plan-picker', dataset: { billingPlanPicker: 'true' } });
        const changePlanStatus = el('span', { class: 'us-status-line' }, '');
        const intervalControls = el('div', { class: 'us-billing-intervals', role: 'tablist', 'aria-label': 'Billing interval' });
        const cards = el('div', { class: 'us-plan-grid' });

        const renderIntervalControls = () => {
          intervalControls.innerHTML = '';
          intervals.forEach((interval) => {
            const intervalBtn = btn(interval.label, {
              kind: interval.id === selectedInterval ? 'primary' : 'secondary',
              onclick: () => {
                selectedInterval = interval.id;
                renderIntervalControls();
                renderPlanCards();
              },
            });
            intervalBtn.classList.add('us-billing-interval-btn');
            intervalBtn.setAttribute('aria-selected', interval.id === selectedInterval ? 'true' : 'false');
            intervalControls.appendChild(intervalBtn);
          });
        };

        const renderPlanCards = () => {
          cards.innerHTML = '';
          pricing.tiers.forEach((tier) => {
            const amount = tierIntervalAmount(tier, selectedInterval, pricing);
            const intervalLabel = selectedInterval === 'year' ? '/yr' : '/mo';
            const isCurrent = currentPlanId && tier.id === currentPlanId;
            const limits = tierLimitText(tier);
            const features = Array.isArray(tier.features) ? tier.features.slice(0, 5) : [];
            const planBtn = btn(isCurrent ? 'Current plan' : (isSuperAdmin ? 'Set plan' : 'Subscribe'), {
              kind: isCurrent ? 'secondary' : 'primary',
              disabled: !!isCurrent,
              onclick: async () => {
                const checkoutKey = ['plan', activeCompany.id || '', tier.id || '', selectedInterval].join(':');
                if (!beginCheckoutOpen(checkoutKey)) {
                  changePlanStatus.textContent = 'Stripe checkout is already open for this plan.';
                  changePlanStatus.className = 'us-status-line';
                  return;
                }
                planBtn.disabled = true;
                let checkoutOpened = false;
                try {
                  if (isSuperAdmin && typeof api.adminSetCompanyPlan === 'function') {
                    const res = await api.adminSetCompanyPlan(activeCompany.id, tier.id);
                    changePlanStatus.textContent = (res && res.message) || 'Plan updated.';
                    changePlanStatus.className = 'us-status-line success';
                    cache.planLimits = null;
                    releaseCheckoutOpen(checkoutKey);
                    await renderBilling(panel);
                    return;
                  }
                  const res = await api.createPlanCheckout({
                    company_id: activeCompany.id,
                    plan_id: tier.id,
                    billing_interval: selectedInterval,
                  });
                  if (res && res.checkout_url) {
                    const sessionId = res.session_id || checkoutSessionIdFromUrl(res.checkout_url);
                    savePendingPayment({
                      kind: 'plan',
                      company_id: activeCompany.id,
                      plan_id: tier.id,
                      billing_interval: selectedInterval,
                      amount_usd: amount,
                      checkout_session_id: sessionId,
                      baseline_balance_tokens: postPaymentBalance,
                    });
                    checkoutOpened = openCheckoutUrlOnce(res.checkout_url, sessionId);
                    changePlanStatus.textContent = checkoutOpened
                      ? 'Stripe checkout opened. Return here to confirm the subscription change.'
                      : 'Stripe checkout is already open for this plan.';
                    changePlanStatus.className = checkoutOpened ? 'us-status-line success' : 'us-status-line';
                  }
                } catch (err) {
                  changePlanStatus.textContent = errMsg(err);
                  changePlanStatus.className = 'us-status-line error';
                } finally {
                  if (!checkoutOpened) {
                    releaseCheckoutOpen(checkoutKey);
                    if (!isCurrent) planBtn.disabled = false;
                  }
                }
              },
            });
            const card = el('article', { class: 'us-plan-card' + (isCurrent ? ' is-current' : '') }, [
              el('div', { class: 'us-plan-card-head' }, [
                el('div', null, [
                  el('h3', { class: 'us-plan-title' }, tier.name || tier.id || 'Plan'),
                  tier.description ? el('p', { class: 'us-plan-description' }, tier.description) : null,
                ]),
                isCurrent ? badge('Current', 'success') : null,
              ]),
              el('div', { class: 'us-plan-price' }, [
                el('span', { class: 'us-plan-price-amount' }, formatBillingAmount(amount)),
                el('span', { class: 'us-plan-price-interval' }, intervalLabel),
              ]),
              limits.length ? el('div', { class: 'us-plan-limits' }, limits.map((item) => badge(item, ''))) : null,
              features.length ? el('ul', { class: 'us-plan-features' }, features.map((feature) => el('li', null, feature))) : null,
              planBtn,
            ]);
            cards.appendChild(card);
          });
        };

        renderIntervalControls();
        renderPlanCards();
        pickerWrap.appendChild(intervalControls);
        pickerWrap.appendChild(cards);
        panel.appendChild(section('Choose a plan',
          'Monthly and annual subscriptions are handled through Stripe checkout. Annual pricing applies the discount from pricing.json.',
          [
            pickerWrap,
            changePlanStatus,
          ]));
      }
    }
    if (deferredResourceAddonSection) panel.appendChild(deferredResourceAddonSection);
    if (deferredTokenTopupSection) panel.appendChild(deferredTokenTopupSection);

    // Billing history.
    try {
      const txns = await api.listBillingTransactions(activeCompany.id);
      const rawItems = Array.isArray(txns) ? txns : (txns && txns.transactions) || [];
      const stalePendingCutoffMs = 12 * 60 * 60 * 1000;
      const items = rawItems.filter((txn) => {
        if (!txn || txn.status !== 'pending' || !txn.created_at) return true;
        const created = new Date(txn.created_at).getTime();
        return Number.isNaN(created) || Date.now() - created < stalePendingCutoffMs;
      });
      if (items.length) {
        const list = el('div', { class: 'us-row-list' });
        items.slice(0, 25).forEach((t) => {
          const typeLabel = String(t.transaction_type || '')
            .replace(/_/g, ' ')
            .replace(/\b\w/g, (ch) => ch.toUpperCase());
          const processedBy = t.processed_by || t.user_email || t.user_name || t.user_id || 'Unknown user';
          const metaParts = [
            formatDate(t.created_at),
            t.status || '—',
            typeLabel || null,
            'Processed by ' + processedBy,
            t.token_amount ? formatTokens(t.token_amount) + ' tokens' : null,
          ].filter(Boolean);
          list.appendChild(el('div', { class: 'us-list-item' }, [
            el('div', { class: 'us-list-item-grow' }, [
              el('p', { class: 'us-list-item-title' }, formatUsd(t.amount_usd) + ' · ' + (t.currency || 'USD')),
              el('p', { class: 'us-list-item-meta' }, metaParts.join(' · ')),
            ]),
            t.status ? badge(t.status, t.status === 'completed' ? 'success' : 'warn') : null,
          ]));
        });
        panel.appendChild(section('Billing history',
          'Company-level payment history for ' + (activeCompany.name || 'this company') + '.',
          [list]));
      } else {
        panel.appendChild(section('Billing history',
          'Company-level payment history for ' + (activeCompany.name || 'this company') + '.',
          [emptyState('No transactions yet.')]));
      }
    } catch (err) {
      panel.appendChild(section('Billing history', null, [el('p', { class: 'us-hint error' }, errMsg(err))]));
    }
  }

  // ─── Modal field helper (shared by Super Admin modals) ───────────────

  /** Build a tiny labeled-field DOM for inline modal forms.
   *  `opts.type` can be 'text' (default), 'email', 'url', 'tel', or 'textarea'. */
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

  // ─── Super Admin tab ─────────────────────────────────────────────────
  //
  // Server-wide administration that mirrors the web app's
  // /billing/admin page. Includes server stats, paginated company
  // listing with search/filter/sort, per-company actions (issue
  // credits, set plan, suspend, merge, edit, delete), per-user
  // actions (impersonate, change role, deactivate, reset password,
  // assign/remove from company), and a billing-config sub-section.
  //
  // The tab is gated by `ensureSuperAdminTabVisible` (super admin
  // only). State is kept in a closure-local `state` object so
  // re-renders preserve filters/pagination across actions.

  const SUPER_ADMIN_PAGE_SIZES = [20, 50, 100, 200];
  const SUPER_ADMIN_PROTECTED_COMPANIES = ['DevXT', "Josh's Team"];
  const SUPER_ADMIN_PROTECTED_EMAILS = ['josh@devxt.com'];
  const SUPER_ADMIN_BILLING_CONFIG_KEYS = [
    'BILLING_PAUSED',
    'TOKEN_PRICE_PER_MILLION_USD',
    'MIN_TOKEN_TOPUP_USD',
    'LOW_BALANCE_WARNING_THRESHOLD',
    'STRIPE_API_KEY',
    'STRIPE_PUBLISHABLE_KEY',
    'STRIPE_WEBHOOK_SECRET',
    'PAYMENT_WALLET_ADDRESS',
    'PAYMENT_SOLANA_RPC_URL',
  ];
  const SUPER_ADMIN_BILLING_CONFIG_LABELS = {
    BILLING_PAUSED: 'Billing paused (true/false)',
    TOKEN_PRICE_PER_MILLION_USD: 'Token price per million (USD)',
    MIN_TOKEN_TOPUP_USD: 'Minimum top-up amount (USD)',
    LOW_BALANCE_WARNING_THRESHOLD: 'Low-balance warning threshold (USD)',
    STRIPE_API_KEY: 'Stripe secret key (sk_…)',
    STRIPE_PUBLISHABLE_KEY: 'Stripe publishable key (pk_…)',
    STRIPE_WEBHOOK_SECRET: 'Stripe webhook signing secret',
    PAYMENT_WALLET_ADDRESS: 'Crypto wallet address (Solana)',
    PAYMENT_SOLANA_RPC_URL: 'Solana RPC URL',
  };

  const superAdminState = {
    search: '',
    page: 0,
    pageSize: 20,
    sortBy: 'name',
    sortDir: 'asc',
    filterBalance: 'all', // 'all' | 'no_balance' | 'has_balance'
    filterUsers: 'all', // 'all' | 'single_user' | 'multiple_users'
    planTiers: null, // cached pricing.tiers for the Set Plan modal
  };

  function isProtectedCompany(c) {
    return !!c && SUPER_ADMIN_PROTECTED_COMPANIES.includes(c.name);
  }

  function formatTokens(n) {
    const v = Number(n) || 0;
    if (v >= 1e9) return (v / 1e9).toFixed(2) + 'B';
    if (v >= 1e6) return (v / 1e6).toFixed(2) + 'M';
    if (v >= 1e3) return (v / 1e3).toFixed(2) + 'K';
    return String(v);
  }

  function formatUsd(n) {
    const v = Number(n) || 0;
    return '$' + v.toFixed(2);
  }

  async function loadPlanTiersForAdmin() {
    if (Array.isArray(superAdminState.planTiers)) return superAdminState.planTiers;
    try {
      const pricing = await api.getPricingConfig();
      if (pricing && pricing.pricing_model === 'tiered_plan' && Array.isArray(pricing.tiers)) {
        superAdminState.planTiers = pricing.tiers;
      } else {
        superAdminState.planTiers = [];
      }
    } catch (_) {
      superAdminState.planTiers = [];
    }
    return superAdminState.planTiers;
  }

  async function renderSuperAdmin(panel) {
    panel.innerHTML = '';

    // Header: title + summary actions. Buttons stack on small windows
    // via the existing `us-section-row` wrap behaviour.
    const headerActions = el('div', { class: 'us-section-row' }, [
      btn('Create company', { kind: 'primary', onclick: () => openSuperAdminCreateCompany(panel) }),
      btn('Impersonate user', { onclick: () => openSuperAdminImpersonate(panel) }),
      btn('Deactivate user', { kind: 'danger', onclick: () => openSuperAdminDeactivate(panel) }),
      btn('Export CSV', { onclick: () => handleSuperAdminExport() }),
    ]);
    panel.appendChild(section(
      'Super admin',
      'Server-wide administration: tenants, billing, users.',
      [headerActions],
    ));

    // Server stats — refresh in parallel with the companies list so the
    // first paint isn't blocked on either.
    const statsHost = el('div');
    panel.appendChild(statsHost);
    api.adminGetServerStats().then((stats) => renderSuperAdminStats(statsHost, stats))
      .catch((err) => {
        statsHost.innerHTML = '';
        statsHost.appendChild(section('Server stats', null, [
          el('p', { class: 'us-hint error' }, errMsg(err)),
        ]));
      });

    // Companies list (filter bar + table + pagination footer).
    const listHost = el('div');
    panel.appendChild(listHost);
    await renderSuperAdminCompanies(listHost, panel);

    // Billing config card (BILLING_PAUSED, token price, Stripe keys).
    const billingHost = el('div');
    panel.appendChild(billingHost);
    api.getAllServerConfig(undefined, true).then((data) => {
      const configs = (data && data.configs) || [];
      renderSuperAdminBillingConfig(billingHost, configs);
    }).catch((err) => {
      billingHost.innerHTML = '';
      billingHost.appendChild(section('Billing configuration', null, [
        el('p', { class: 'us-hint error' }, errMsg(err)),
      ]));
    });
  }

  function renderSuperAdminStats(host, stats) {
    host.innerHTML = '';
    if (!stats) return;
    const cards = [
      ['Companies', stats.total_companies],
      ['Users', stats.total_users],
      ['With balance', stats.companies_with_balance],
      ['No balance', stats.companies_no_balance],
      ['Multi-user', stats.multi_user_companies],
      ['Suspended', stats.suspended_companies],
    ];
    const pills = el('div', { class: 'us-stat-pills' });
    cards.forEach(([label, value]) => {
      const pill = el('div', { class: 'us-stat-pill' }, [
        el('div', { class: 'us-stat-pill-value' }, String(value == null ? '—' : value)),
        el('div', { class: 'us-stat-pill-label' }, label),
      ]);
      pills.appendChild(pill);
    });
    host.appendChild(section('Server stats', null, [pills]));
  }

  async function renderSuperAdminCompanies(host, panel) {
    host.innerHTML = '';

    const searchInput = el('input', {
      class: 'us-input',
      type: 'search',
      placeholder: 'Search by company name, ID, or user email…',
      value: superAdminState.search,
    });
    let searchTimer = null;
    searchInput.addEventListener('input', () => {
      if (searchTimer) clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        superAdminState.search = searchInput.value;
        superAdminState.page = 0;
        renderSuperAdminCompanies(host, panel);
      }, 300);
    });

    const balanceSelect = el('select', { class: 'us-select' }, [
      el('option', { value: 'all' }, 'All balances'),
      el('option', { value: 'has_balance' }, 'With balance'),
      el('option', { value: 'no_balance' }, 'No balance'),
    ]);
    balanceSelect.value = superAdminState.filterBalance;
    balanceSelect.addEventListener('change', () => {
      superAdminState.filterBalance = balanceSelect.value;
      superAdminState.page = 0;
      renderSuperAdminCompanies(host, panel);
    });

    const userSelect = el('select', { class: 'us-select' }, [
      el('option', { value: 'all' }, 'All companies'),
      el('option', { value: 'single_user' }, 'Single user'),
      el('option', { value: 'multiple_users' }, 'Multi-user'),
    ]);
    userSelect.value = superAdminState.filterUsers;
    userSelect.addEventListener('change', () => {
      superAdminState.filterUsers = userSelect.value;
      superAdminState.page = 0;
      renderSuperAdminCompanies(host, panel);
    });

    const sortSelect = el('select', { class: 'us-select' }, [
      el('option', { value: 'name:asc' }, 'Name A → Z'),
      el('option', { value: 'name:desc' }, 'Name Z → A'),
      el('option', { value: 'token_balance:desc' }, 'Balance high → low'),
      el('option', { value: 'token_balance:asc' }, 'Balance low → high'),
      el('option', { value: 'user_count:desc' }, 'Users high → low'),
      el('option', { value: 'user_count:asc' }, 'Users low → high'),
    ]);
    sortSelect.value = superAdminState.sortBy + ':' + superAdminState.sortDir;
    sortSelect.addEventListener('change', () => {
      const [by, dir] = sortSelect.value.split(':');
      superAdminState.sortBy = by;
      superAdminState.sortDir = dir;
      superAdminState.page = 0;
      renderSuperAdminCompanies(host, panel);
    });

    const pageSizeSelect = el('select', { class: 'us-select' },
      SUPER_ADMIN_PAGE_SIZES.map((n) => el('option', { value: String(n) }, String(n) + '/page')));
    pageSizeSelect.value = String(superAdminState.pageSize);
    pageSizeSelect.addEventListener('change', () => {
      superAdminState.pageSize = parseInt(pageSizeSelect.value, 10) || 20;
      superAdminState.page = 0;
      renderSuperAdminCompanies(host, panel);
    });

    // Stretched search + four compact selects on a single wrapping row.
    // CSS class `us-admin-filters` overrides the 100% width that
    // .us-input/.us-select inherit from the standalone form layout.
    const filters = el('div', { class: 'us-section-row us-admin-filters' }, [
      searchInput, balanceSelect, userSelect, sortSelect, pageSizeSelect,
    ]);

    const body = el('div');
    host.appendChild(section('Companies', null, [filters, body]));

    body.appendChild(el('p', { class: 'us-hint' }, 'Loading…'));
    let data;
    try {
      data = await api.adminGetAllCompanies({
        search: superAdminState.search || undefined,
        limit: superAdminState.pageSize,
        offset: superAdminState.page * superAdminState.pageSize,
        sort_by: superAdminState.sortBy,
        sort_direction: superAdminState.sortDir,
        filter_balance: superAdminState.filterBalance !== 'all' ? superAdminState.filterBalance : undefined,
        filter_users: superAdminState.filterUsers !== 'all' ? superAdminState.filterUsers : undefined,
      });
    } catch (err) {
      body.innerHTML = '';
      body.appendChild(el('p', { class: 'us-hint error' }, errMsg(err)));
      return;
    }

    body.innerHTML = '';
    const companies = (data && data.companies) || [];
    if (!companies.length) {
      body.appendChild(emptyState('No companies match the current filters.'));
      return;
    }

    const list = el('div', { class: 'us-row-list' });
    companies.forEach((c) => list.appendChild(renderCompanyRow(c, host, panel)));
    body.appendChild(list);

    // Pagination footer.
    const total = data.total || companies.length;
    const totalPages = Math.max(1, Math.ceil(total / superAdminState.pageSize));
    const pageLabel = el('span', { class: 'us-hint' },
      'Page ' + (superAdminState.page + 1) + ' of ' + totalPages + ' · ' + total + ' total');
    const prevBtn = btn('← Prev', {
      disabled: superAdminState.page === 0,
      onclick: () => { superAdminState.page = Math.max(0, superAdminState.page - 1); renderSuperAdminCompanies(host, panel); },
    });
    const nextBtn = btn('Next →', {
      disabled: superAdminState.page + 1 >= totalPages,
      onclick: () => { superAdminState.page = Math.min(totalPages - 1, superAdminState.page + 1); renderSuperAdminCompanies(host, panel); },
    });
    body.appendChild(el('div', { class: 'us-section-row between' }, [pageLabel, el('div', { class: 'us-section-row' }, [prevBtn, nextBtn])]));
  }

  function renderCompanyRow(c, listHost, panel) {
    const protectedCo = isProtectedCompany(c);
    const titleNode = el('p', { class: 'us-list-item-title' }, [
      el('span', null, c.name || 'Untitled'),
      ' ',
      c.is_suspended ? badge('Suspended', 'warn') : null,
      protectedCo ? badge('Protected', 'muted') : null,
    ]);
    const meta = el('p', { class: 'us-list-item-meta' },
      'Balance: ' + formatUsd(c.token_balance_usd) + ' · ' + formatTokens(c.token_balance) + ' tokens'
      + ' · Users: ' + (c.users ? c.users.length : 0)
      + (c.plan_id ? ' · Plan: ' + c.plan_id : '')
      + ' · ID: ' + (c.id || '—').slice(0, 8));

    const refresh = () => renderSuperAdminCompanies(listHost, panel);

    const actions = el('div', { class: 'us-list-item-actions' }, [
      btn('Credits', { kind: 'primary', onclick: () => openSuperAdminIssueCredits(c, refresh) }),
      btn('Plan', { onclick: () => openSuperAdminSetPlan(c, refresh) }),
      btn(c.is_suspended ? 'Unsuspend' : 'Suspend', {
        disabled: protectedCo,
        onclick: async () => {
          if (protectedCo) return;
          try {
            if (c.is_suspended) await api.adminUnsuspendCompany(c.id);
            else await api.adminSuspendCompany(c.id);
            toast(c.is_suspended ? 'Unsuspended' : 'Suspended', 'success');
            refresh();
          } catch (err) { toast(errMsg(err), 'error'); }
        },
      }),
      btn('Edit', { onclick: () => openSuperAdminEditCompany(c, refresh) }),
      btn('Merge', { disabled: protectedCo, onclick: () => openSuperAdminMergeCompany(c, refresh) }),
      btn('Add user', { onclick: () => openSuperAdminAssignUser(c, refresh) }),
      btn('Delete', {
        kind: 'danger',
        disabled: protectedCo,
        onclick: () => openSuperAdminDeleteCompany(c, refresh),
      }),
    ]);

    const head = el('div', { class: 'us-list-item' }, [
      el('div', { class: 'us-list-item-grow' }, [titleNode, meta]),
      actions,
    ]);

    // Expandable user list — collapsed by default so the page stays
    // scannable. Tapping the row's "Users" badge toggles visibility.
    const userList = el('div', { hidden: true });
    if (Array.isArray(c.users) && c.users.length) {
      c.users.forEach((u) => userList.appendChild(renderUserRow(c, u, refresh)));
    } else {
      userList.appendChild(emptyState('No users in this company.'));
    }
    const toggleUsers = btn(((c.users || []).length) + ' users', {
      kind: 'ghost',
      onclick: () => {
        userList.hidden = !userList.hidden;
        toggleUsers.textContent = (userList.hidden ? '▸ ' : '▾ ') + ((c.users || []).length) + ' users';
      },
    });
    toggleUsers.textContent = '▸ ' + ((c.users || []).length) + ' users';

    const row = el('div', { class: 'us-list-item-wrap' }, [
      head,
      el('div', { class: 'us-section-row' }, [toggleUsers]),
      userList,
    ]);
    return row;
  }

  // Friendly labels for the role badge in the Super Admin user list.
  // The backend returns the raw slug ("super_admin", "tenant_admin",
  // "company_admin", "user", ...) which is correct but reads
  // technically; the UI prefers proper-case names. Keyed by role_id so
  // we don't depend on the slug staying stable.
  const SUPER_ADMIN_ROLE_LABELS = {
    0: 'Super Admin',
    1: 'Tenant Admin',
    2: 'Company Admin',
    3: 'Power User',
    4: 'Child',
    5: 'Chat User',
    6: 'Read Only User',
  };

  const SUPER_ADMIN_ROLE_OPTIONS = [
    { value: '0', label: 'Super Admin (0)' },
    { value: '1', label: 'Tenant Admin (1)' },
    { value: '2', label: 'Company Admin (2)' },
    { value: '3', label: 'Power User (3)' },
    { value: '6', label: 'Read Only User (6)' },
    { value: '5', label: 'Chat User (5)' },
    { value: '4', label: 'Child (4)' },
  ];

  function superAdminRoleOptions() {
    return SUPER_ADMIN_ROLE_OPTIONS.map((role) => el('option', { value: role.value }, role.label));
  }

  function superAdminRoleLabel(user) {
    const id = Number(user && user.role_id);
    if (Number.isInteger(id) && SUPER_ADMIN_ROLE_LABELS[id]) {
      return SUPER_ADMIN_ROLE_LABELS[id];
    }
    // Fall back to a Title-Cased version of whatever slug the server
    // hands back so we never just print "super_admin" with underscores.
    const slug = String((user && user.role) || '').trim();
    if (!slug) return 'Role ' + (user && user.role_id != null ? user.role_id : '?');
    return slug
      .split(/[_\s-]+/)
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
      .join(' ');
  }

  function superAdminRoleBadgeKind(user) {
    const id = Number(user && user.role_id);
    if (id === 0) return 'danger';        // Super Admin — highlight
    if (id === 1 || id === 2) return 'primary'; // Tenant / Company admin
    return 'muted';
  }

  function renderUserRow(company, user, refresh) {
    const protectedUser = SUPER_ADMIN_PROTECTED_EMAILS.includes((user.email || '').toLowerCase());
    const title = el('p', { class: 'us-list-item-title' }, [
      el('span', null, (user.first_name || '') + ' ' + (user.last_name || '') || user.email || 'User'),
      ' ',
      badge(superAdminRoleLabel(user), superAdminRoleBadgeKind(user)),
      protectedUser ? badge('Protected', 'muted') : null,
    ]);
    const meta = el('p', { class: 'us-list-item-meta' }, (user.email || '') + ' · ID: ' + (user.id || '').slice(0, 8));
    const actions = el('div', { class: 'us-list-item-actions' }, [
      btn('Impersonate', {
        onclick: async () => {
          try {
            const result = await api.adminImpersonateUser(user.email);
            openSuperAdminImpersonateResult(result);
          } catch (err) { toast(errMsg(err), 'error'); }
        },
      }),
      btn('Change role', {
        onclick: () => openSuperAdminChangeRole(company, user, refresh),
      }),
      btn('Change email', {
        disabled: protectedUser,
        onclick: () => openSuperAdminChangeEmail(user, refresh),
      }),
      btn('Reset password', {
        onclick: () => openSuperAdminResetPassword(user, refresh),
      }),
      btn('Reset MFA', {
        onclick: () => openSuperAdminResetMfa(user, refresh),
      }),
      btn('Remove', {
        kind: 'danger',
        disabled: protectedUser,
        onclick: async () => {
          if (protectedUser) return;
          const ok = await confirmDialog({
            title: 'Remove user from company',
            message: 'Remove ' + (user.email || 'user') + ' from ' + (company.name || 'this company') + '? They will no longer have access.',
            destructive: true,
            confirmLabel: 'Remove',
          });
          if (!ok) return;
          try {
            await api.adminRemoveUserFromCompany(company.id, user.id);
            toast('User removed', 'success');
            refresh();
          } catch (err) { toast(errMsg(err), 'error'); }
        },
      }),
    ]);
    return el('div', { class: 'us-list-item' }, [
      el('div', { class: 'us-list-item-grow' }, [title, meta]),
      actions,
    ]);
  }

  // ─── Super admin: modals ─────────────────────────────────────────────

  function openSuperAdminIssueCredits(company, refresh) {
    const amount = modalField('Amount (USD)', { type: 'text', value: '', placeholder: '100.00' });
    const status = el('p', { class: 'us-status-line' }, '');
    const cancelBtn = btn('Cancel');
    const submitBtn = btn('Issue credits', { kind: 'primary' });
    const handle = openModal({
      title: 'Issue credits to ' + (company.name || ''),
      description: 'Add token credits to this company without going through Stripe.',
      body: [amount.wrap, status],
      footer: [cancelBtn, submitBtn],
    });
    cancelBtn.addEventListener('click', () => handle.close());
    submitBtn.addEventListener('click', async () => {
      const n = parseFloat(amount.input.value);
      if (!isFinite(n) || n <= 0) {
        status.textContent = 'Enter an amount greater than 0.';
        status.className = 'us-status-line error';
        return;
      }
      submitBtn.disabled = true;
      try {
        const res = await api.adminIssueCredits(company.id, n);
        status.textContent = 'Credited ' + formatUsd(res.amount_usd)
          + ' (' + formatTokens(res.tokens_credited) + ' tokens). New balance: '
          + formatUsd(res.new_balance_usd) + '.';
        status.className = 'us-status-line success';
        if (typeof refresh === 'function') refresh();
      } catch (err) {
        status.textContent = errMsg(err);
        status.className = 'us-status-line error';
        submitBtn.disabled = false;
      }
    });
    setupModalFocus(handle);
  }

  async function openSuperAdminSetPlan(company, refresh) {
    const tiers = await loadPlanTiersForAdmin();
    const select = el('select', { class: 'us-select' });
    if (!tiers.length) {
      select.appendChild(el('option', { value: '' }, 'No plans configured'));
      select.disabled = true;
    } else {
      tiers.forEach((t) => select.appendChild(el('option', { value: t.id }, (t.name || t.id))));
      select.value = company.plan_id || tiers[0].id;
    }
    const wrap = el('label', { class: 'us-label' }, [
      el('span', { class: 'us-label-text' }, 'Plan'), select,
    ]);
    const status = el('p', { class: 'us-status-line' }, '');
    const cancelBtn = btn('Cancel');
    const submitBtn = btn('Set plan', { kind: 'primary', disabled: !tiers.length });
    const handle = openModal({
      title: 'Set plan for ' + (company.name || ''),
      description: 'Assign a billing plan directly without Stripe checkout.',
      body: [wrap, status],
      footer: [cancelBtn, submitBtn],
    });
    cancelBtn.addEventListener('click', () => handle.close());
    submitBtn.addEventListener('click', async () => {
      const planId = select.value;
      if (!planId) return;
      submitBtn.disabled = true;
      try {
        const res = await api.adminSetCompanyPlan(company.id, planId);
        status.textContent = res && res.message ? res.message : 'Plan updated.';
        status.className = 'us-status-line success';
        if (typeof refresh === 'function') refresh();
      } catch (err) {
        status.textContent = errMsg(err);
        status.className = 'us-status-line error';
        submitBtn.disabled = false;
      }
    });
    setupModalFocus(handle);
  }

  function openSuperAdminEditCompany(company, refresh) {
    const name = modalField('Name', { value: company.name || '' });
    const email = modalField('Email', { type: 'email', value: company.email || '' });
    const phone = modalField('Phone', { value: company.phone_number || '' });
    const website = modalField('Website', { type: 'url', value: company.website || '' });
    const address = modalField('Address', { value: company.address || '' });
    const city = modalField('City', { value: company.city || '' });
    const stateF = modalField('State', { value: company.state || '' });
    const zip = modalField('ZIP', { value: company.zip_code || '' });
    const country = modalField('Country', { value: company.country || '' });
    const notes = modalField('Notes', { type: 'textarea', value: company.notes || '', rows: 3 });

    const status = el('p', { class: 'us-status-line' }, '');
    const cancelBtn = btn('Cancel');
    const submitBtn = btn('Save changes', { kind: 'primary' });
    const handle = openModal({
      title: 'Edit ' + (company.name || 'company'),
      wide: true,
      body: [
        el('div', { class: 'us-grid-2' }, [name.wrap, email.wrap]),
        el('div', { class: 'us-grid-2' }, [phone.wrap, website.wrap]),
        address.wrap,
        el('div', { class: 'us-grid-2' }, [city.wrap, stateF.wrap]),
        el('div', { class: 'us-grid-2' }, [zip.wrap, country.wrap]),
        notes.wrap,
        status,
      ],
      footer: [cancelBtn, submitBtn],
    });
    cancelBtn.addEventListener('click', () => handle.close());
    submitBtn.addEventListener('click', async () => {
      const patch = {};
      const fields = {
        name: name.input.value, email: email.input.value, phone_number: phone.input.value,
        website: website.input.value, address: address.input.value, city: city.input.value,
        state: stateF.input.value, zip_code: zip.input.value, country: country.input.value,
        notes: notes.input.value,
      };
      Object.entries(fields).forEach(([k, v]) => {
        const original = company[k] == null ? '' : company[k];
        if ((v || '') !== (original || '')) patch[k] = v;
      });
      if (!Object.keys(patch).length) {
        status.textContent = 'No changes to save.';
        status.className = 'us-status-line';
        return;
      }
      submitBtn.disabled = true;
      try {
        await api.adminUpdateCompany(company.id, patch);
        toast('Company updated', 'success');
        handle.close();
        if (typeof refresh === 'function') refresh();
      } catch (err) {
        status.textContent = errMsg(err);
        status.className = 'us-status-line error';
        submitBtn.disabled = false;
      }
    });
    setupModalFocus(handle);
  }

  function openSuperAdminCreateCompany(panel) {
    const name = modalField('Company name *', { value: '', placeholder: 'Acme Corp' });
    const email = modalField('Email', { type: 'email', value: '' });
    const phone = modalField('Phone', { value: '' });
    const website = modalField('Website', { type: 'url', value: '' });
    const address = modalField('Address', { value: '' });
    const city = modalField('City', { value: '' });
    const stateF = modalField('State', { value: '' });
    const zip = modalField('ZIP', { value: '' });
    const country = modalField('Country', { value: '' });
    const notes = modalField('Notes', { type: 'textarea', value: '', rows: 3 });

    const status = el('p', { class: 'us-status-line' }, '');
    const cancelBtn = btn('Cancel');
    const submitBtn = btn('Create company', { kind: 'primary' });
    const handle = openModal({
      title: 'Create company',
      wide: true,
      body: [
        el('div', { class: 'us-grid-2' }, [name.wrap, email.wrap]),
        el('div', { class: 'us-grid-2' }, [phone.wrap, website.wrap]),
        address.wrap,
        el('div', { class: 'us-grid-2' }, [city.wrap, stateF.wrap]),
        el('div', { class: 'us-grid-2' }, [zip.wrap, country.wrap]),
        notes.wrap,
        status,
      ],
      footer: [cancelBtn, submitBtn],
    });
    cancelBtn.addEventListener('click', () => handle.close());
    submitBtn.addEventListener('click', async () => {
      if (!name.input.value.trim()) {
        status.textContent = 'Name is required.';
        status.className = 'us-status-line error';
        return;
      }
      submitBtn.disabled = true;
      try {
        await api.adminCreateCompany({
          name: name.input.value.trim(),
          email: email.input.value.trim() || undefined,
          phone_number: phone.input.value.trim() || undefined,
          website: website.input.value.trim() || undefined,
          address: address.input.value.trim() || undefined,
          city: city.input.value.trim() || undefined,
          state: stateF.input.value.trim() || undefined,
          zip_code: zip.input.value.trim() || undefined,
          country: country.input.value.trim() || undefined,
          notes: notes.input.value.trim() || undefined,
        });
        toast('Company created', 'success');
        handle.close();
        renderSuperAdmin(panel);
      } catch (err) {
        status.textContent = errMsg(err);
        status.className = 'us-status-line error';
        submitBtn.disabled = false;
      }
    });
    setupModalFocus(handle);
  }

  function openSuperAdminDeleteCompany(company, refresh) {
    const confirmInput = modalField('Type the company name to confirm', { value: '' });
    const status = el('p', { class: 'us-status-line' }, '');
    const cancelBtn = btn('Cancel');
    const submitBtn = btn('Delete company', { kind: 'danger' });
    const handle = openModal({
      title: 'Delete ' + (company.name || 'company'),
      description: 'This permanently removes the company and detaches all users. Type the name to confirm.',
      body: [confirmInput.wrap, status],
      footer: [cancelBtn, submitBtn],
    });
    cancelBtn.addEventListener('click', () => handle.close());
    submitBtn.addEventListener('click', async () => {
      if (confirmInput.input.value !== company.name) {
        status.textContent = 'Company name does not match.';
        status.className = 'us-status-line error';
        return;
      }
      submitBtn.disabled = true;
      try {
        await api.adminDeleteCompany(company.id);
        toast('Company deleted', 'success');
        handle.close();
        if (typeof refresh === 'function') refresh();
      } catch (err) {
        status.textContent = errMsg(err);
        status.className = 'us-status-line error';
        submitBtn.disabled = false;
      }
    });
    setupModalFocus(handle);
  }

  async function openSuperAdminMergeCompany(source, refresh) {
    // Load a fresh list to pick from. Cap at a generous limit so all
    // realistic candidates fit a single dropdown.
    let candidates = [];
    try {
      const data = await api.adminGetAllCompanies({ limit: 500 });
      candidates = (data.companies || []).filter((c) => c.id !== source.id);
    } catch (err) {
      toast(errMsg(err), 'error');
      return;
    }
    const select = el('select', { class: 'us-select' });
    if (!candidates.length) {
      select.appendChild(el('option', { value: '' }, 'No target companies available'));
      select.disabled = true;
    } else {
      select.appendChild(el('option', { value: '' }, 'Choose a target company…'));
      candidates.forEach((c) => select.appendChild(el('option', { value: c.id }, c.name || c.id)));
    }
    const wrap = el('label', { class: 'us-label' }, [
      el('span', { class: 'us-label-text' }, 'Merge into'), select,
    ]);
    const status = el('p', { class: 'us-status-line' }, '');
    const cancelBtn = btn('Cancel');
    const submitBtn = btn('Merge companies', { kind: 'danger', disabled: !candidates.length });
    const handle = openModal({
      title: 'Merge ' + (source.name || 'company'),
      description: 'Move all users and balance from this company into the target. The source company is then deleted.',
      body: [wrap, status],
      footer: [cancelBtn, submitBtn],
    });
    cancelBtn.addEventListener('click', () => handle.close());
    submitBtn.addEventListener('click', async () => {
      const target = select.value;
      if (!target) {
        status.textContent = 'Pick a target.';
        status.className = 'us-status-line error';
        return;
      }
      const ok = await confirmDialog({
        title: 'Merge companies?',
        message: 'This deletes ' + (source.name || 'the source company') + ' after moving users and balance.',
        destructive: true,
        confirmLabel: 'Merge',
      });
      if (!ok) return;
      submitBtn.disabled = true;
      try {
        const res = await api.adminMergeCompanies(source.id, target);
        toast('Merged ' + (res.moved_users ? res.moved_users.length : 0) + ' users', 'success');
        handle.close();
        if (typeof refresh === 'function') refresh();
      } catch (err) {
        status.textContent = errMsg(err);
        status.className = 'us-status-line error';
        submitBtn.disabled = false;
      }
    });
    setupModalFocus(handle);
  }

  function openSuperAdminAssignUser(company, refresh) {
    const email = modalField('User email', { type: 'email', value: '' });
    const roleSelect = el('select', { class: 'us-select' }, superAdminRoleOptions());
    roleSelect.value = '3';
    const roleWrap = el('label', { class: 'us-label' }, [
      el('span', { class: 'us-label-text' }, 'Role'), roleSelect,
    ]);
    const status = el('p', { class: 'us-status-line' }, '');
    const cancelBtn = btn('Cancel');
    const submitBtn = btn('Assign user', { kind: 'primary' });
    const handle = openModal({
      title: 'Add user to ' + (company.name || ''),
      body: [email.wrap, roleWrap, status],
      footer: [cancelBtn, submitBtn],
    });
    cancelBtn.addEventListener('click', () => handle.close());
    submitBtn.addEventListener('click', async () => {
      const v = email.input.value.trim();
      if (!v) {
        status.textContent = 'Email is required.';
        status.className = 'us-status-line error';
        return;
      }
      submitBtn.disabled = true;
      try {
        await api.adminAssignUserToCompany(company.id, v, parseInt(roleSelect.value, 10));
        toast('User assigned', 'success');
        handle.close();
        if (typeof refresh === 'function') refresh();
      } catch (err) {
        status.textContent = errMsg(err);
        status.className = 'us-status-line error';
        submitBtn.disabled = false;
      }
    });
    setupModalFocus(handle);
  }

  function openSuperAdminChangeRole(company, user, refresh) {
    const roleSelect = el('select', { class: 'us-select' }, superAdminRoleOptions());
    roleSelect.value = String(user.role_id != null ? user.role_id : 3);
    const wrap = el('label', { class: 'us-label' }, [
      el('span', { class: 'us-label-text' }, 'New role'), roleSelect,
    ]);
    const status = el('p', { class: 'us-status-line' }, '');
    const cancelBtn = btn('Cancel');
    const submitBtn = btn('Change role', { kind: 'primary' });
    const handle = openModal({
      title: 'Change role for ' + (user.email || ''),
      description: 'in ' + (company.name || ''),
      body: [wrap, status],
      footer: [cancelBtn, submitBtn],
    });
    cancelBtn.addEventListener('click', () => handle.close());
    submitBtn.addEventListener('click', async () => {
      submitBtn.disabled = true;
      try {
        await api.adminChangeUserRole(company.id, user.id, parseInt(roleSelect.value, 10));
        toast('Role updated', 'success');
        handle.close();
        if (typeof refresh === 'function') refresh();
      } catch (err) {
        status.textContent = errMsg(err);
        status.className = 'us-status-line error';
        submitBtn.disabled = false;
      }
    });
    setupModalFocus(handle);
  }

  function openSuperAdminResetPassword(user, refresh) {
    const np = modalField('New password', { type: 'text', value: '', placeholder: 'min. 8 characters' });
    const cp = modalField('Confirm password', { type: 'text', value: '' });
    const status = el('p', { class: 'us-status-line' }, '');
    const cancelBtn = btn('Cancel');
    const submitBtn = btn('Reset password', { kind: 'primary' });
    const handle = openModal({
      title: 'Reset password for ' + (user.email || ''),
      description: 'The new password takes effect immediately. Share it through a secure channel.',
      body: [np.wrap, cp.wrap, status],
      footer: [cancelBtn, submitBtn],
    });
    cancelBtn.addEventListener('click', () => handle.close());
    submitBtn.addEventListener('click', async () => {
      if (!np.input.value || np.input.value !== cp.input.value) {
        status.textContent = 'Passwords must match.';
        status.className = 'us-status-line error';
        return;
      }
      submitBtn.disabled = true;
      try {
        await api.adminResetUserPassword(user.id, np.input.value, cp.input.value);
        toast('Password reset', 'success');
        handle.close();
        if (typeof refresh === 'function') refresh();
      } catch (err) {
        status.textContent = errMsg(err);
        status.className = 'us-status-line error';
        submitBtn.disabled = false;
      }
    });
    setupModalFocus(handle);
  }

  /** Super-admin "Change email" — replaces the target user's email
   *  address. Server-side validates uniqueness; we surface the 409 by
   *  showing the rejection message inline so the admin can pick another. */
  function openSuperAdminChangeEmail(user, refresh) {
    const next = modalField('New email', {
      type: 'email',
      value: user.email || '',
      placeholder: 'name@example.com',
    });
    const status = el('p', { class: 'us-status-line' }, '');
    const cancelBtn = btn('Cancel');
    const submitBtn = btn('Save email', { kind: 'primary' });
    const handle = openModal({
      title: 'Change email for ' + (user.email || 'user'),
      description: 'The user signs in with the new address immediately. They are not notified — share it through a secure channel.',
      body: [next.wrap, status],
      footer: [cancelBtn, submitBtn],
    });
    cancelBtn.addEventListener('click', () => handle.close());
    submitBtn.addEventListener('click', async () => {
      const value = next.input.value.trim();
      if (!value || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
        status.textContent = 'Enter a valid email address.';
        status.className = 'us-status-line error';
        return;
      }
      if (value.toLowerCase() === (user.email || '').toLowerCase()) {
        status.textContent = 'That is already the current email.';
        status.className = 'us-status-line error';
        return;
      }
      submitBtn.disabled = true;
      try {
        await api.adminChangeUserEmail(user.id, value);
        toast('Email updated', 'success');
        handle.close();
        if (typeof refresh === 'function') refresh();
      } catch (err) {
        status.textContent = errMsg(err);
        status.className = 'us-status-line error';
        submitBtn.disabled = false;
      }
    });
    setupModalFocus(handle);
  }

  /** Super-admin "Reset MFA" — invalidates the user's TOTP secret and
   *  shows the new provisioning URI + secret so the admin can hand it
   *  off to the user out-of-band (chat, email, etc.). The user must
   *  re-enroll on next sign-in. */
  function openSuperAdminResetMfa(user, refresh) {
    const intro = el('p', { class: 'us-section-blurb' },
      'Reset will invalidate the user’s current authenticator app and force them to set up MFA again on next sign-in. They are not notified.');
    const resultBlock = el('div', { hidden: true, class: 'us-mfa-reset-result' });
    const status = el('p', { class: 'us-status-line' }, '');
    const cancelBtn = btn('Close');
    const submitBtn = btn('Reset MFA', { kind: 'danger' });
    const handle = openModal({
      title: 'Reset MFA for ' + (user.email || 'user'),
      body: [intro, resultBlock, status],
      footer: [cancelBtn, submitBtn],
    });
    cancelBtn.addEventListener('click', () => handle.close());
    submitBtn.addEventListener('click', async () => {
      submitBtn.disabled = true;
      status.textContent = 'Resetting…';
      status.className = 'us-status-line';
      try {
        const res = await api.adminResetUserMfa(user.id);
        resultBlock.innerHTML = '';
        resultBlock.hidden = false;
        const otpUri = res && res.otp_uri;
        const secret = res && res.mfa_token;
        resultBlock.appendChild(el('p', { class: 'us-section-blurb' },
          'Share these credentials with the user so they can re-enroll their authenticator app.'));
        if (secret) {
          const secretInput = el('input', { class: 'us-input', readonly: 'readonly', value: secret });
          resultBlock.appendChild(el('label', { class: 'us-label' }, [
            el('span', { class: 'us-label-text' }, 'New TOTP secret'),
            secretInput,
          ]));
          resultBlock.appendChild(el('div', { class: 'us-section-row end' }, [
            btn('Copy secret', { onclick: () => {
              copyToClipboard(secret);
              toast('Secret copied', 'success');
            } }),
          ]));
        }
        if (otpUri) {
          const uriInput = el('textarea', { class: 'us-textarea', rows: 3, readonly: 'readonly' }, otpUri);
          resultBlock.appendChild(el('label', { class: 'us-label' }, [
            el('span', { class: 'us-label-text' }, 'Provisioning URI (otpauth://)'),
            uriInput,
          ]));
          resultBlock.appendChild(el('div', { class: 'us-section-row end' }, [
            btn('Copy URI', { onclick: () => {
              copyToClipboard(otpUri);
              toast('URI copied', 'success');
            } }),
          ]));
        }
        status.textContent = 'MFA reset. The user will re-enroll on next sign-in.';
        status.className = 'us-status-line success';
        submitBtn.hidden = true;
        toast('MFA reset', 'success');
        if (typeof refresh === 'function') refresh();
      } catch (err) {
        status.textContent = errMsg(err);
        status.className = 'us-status-line error';
        submitBtn.disabled = false;
      }
    });
    setupModalFocus(handle);
  }

  function openSuperAdminImpersonate(panel) {
    const email = modalField('User email', { type: 'email', value: '' });
    const status = el('p', { class: 'us-status-line' }, '');
    const resultBlock = el('div', { hidden: true });
    const cancelBtn = btn('Close');
    const submitBtn = btn('Get login token', { kind: 'primary' });
    const handle = openModal({
      title: 'Impersonate user',
      description: 'Look up a user by email and copy a JWT to log in as them.',
      body: [email.wrap, status, resultBlock],
      footer: [cancelBtn, submitBtn],
    });
    cancelBtn.addEventListener('click', () => handle.close());
    submitBtn.addEventListener('click', async () => {
      const v = email.input.value.trim();
      if (!v) {
        status.textContent = 'Email is required.';
        status.className = 'us-status-line error';
        return;
      }
      submitBtn.disabled = true;
      try {
        const res = await api.adminImpersonateUser(v);
        renderImpersonateResultInto(resultBlock, res);
        status.textContent = 'Token issued for ' + (res.user_email || v);
        status.className = 'us-status-line success';
      } catch (err) {
        status.textContent = errMsg(err);
        status.className = 'us-status-line error';
      } finally {
        submitBtn.disabled = false;
      }
    });
    setupModalFocus(handle);
  }

  function openSuperAdminImpersonateResult(res) {
    const resultBlock = el('div');
    renderImpersonateResultInto(resultBlock, res);
    const closeBtn = btn('Close');
    const handle = openModal({
      title: 'Impersonation token',
      body: [resultBlock],
      footer: [closeBtn],
    });
    closeBtn.addEventListener('click', () => handle.close());
  }

  function renderImpersonateResultInto(host, res) {
    host.innerHTML = '';
    host.hidden = false;
    const ta = el('textarea', { class: 'us-textarea', readonly: 'readonly', rows: 4 }, res.jwt || '');
    const copyBtn = btn('Copy JWT', { kind: 'primary', onclick: () => {
      copyToClipboard(res.jwt || '');
      toast('Copied', 'success');
    } });
    host.appendChild(el('p', { class: 'us-hint' },
      'User: ' + (res.user_name || res.user_email || '—')));
    host.appendChild(ta);
    host.appendChild(el('div', { class: 'us-section-row end' }, [copyBtn]));
  }

  function openSuperAdminDeactivate(panel) {
    const email = modalField('User email', { type: 'email', value: '' });
    const status = el('p', { class: 'us-status-line' }, '');
    const cancelBtn = btn('Cancel');
    const submitBtn = btn('Deactivate user', { kind: 'danger' });
    const handle = openModal({
      title: 'Deactivate user',
      description: 'Looks up the user by email and disables sign-in. This does not delete their data.',
      body: [email.wrap, status],
      footer: [cancelBtn, submitBtn],
    });
    cancelBtn.addEventListener('click', () => handle.close());
    submitBtn.addEventListener('click', async () => {
      const v = email.input.value.trim().toLowerCase();
      if (!v) {
        status.textContent = 'Email is required.';
        status.className = 'us-status-line error';
        return;
      }
      if (SUPER_ADMIN_PROTECTED_EMAILS.includes(v)) {
        status.textContent = 'That account is protected.';
        status.className = 'us-status-line error';
        return;
      }
      submitBtn.disabled = true;
      try {
        // Locate the user via the companies search index — same trick
        // the web app uses (`adminGetAllCompanies({search})`).
        const found = await api.adminGetAllCompanies({ search: v, limit: 100 });
        let userId = null;
        (found.companies || []).some((co) => {
          const u = (co.users || []).find((x) => (x.email || '').toLowerCase() === v);
          if (u) { userId = u.id; return true; }
          return false;
        });
        if (!userId) {
          status.textContent = 'User not found.';
          status.className = 'us-status-line error';
          submitBtn.disabled = false;
          return;
        }
        await api.adminDeactivateUser(userId);
        toast('User deactivated', 'success');
        handle.close();
        renderSuperAdmin(panel);
      } catch (err) {
        status.textContent = errMsg(err);
        status.className = 'us-status-line error';
        submitBtn.disabled = false;
      }
    });
    setupModalFocus(handle);
  }

  async function handleSuperAdminExport() {
    toast('Preparing export…');
    try {
      const data = await api.adminExportCompanies();
      const cols = data.columns || [];
      const rows = data.rows || [];
      const escape = (v) => {
        const s = v == null ? '' : String(v);
        return /[,"\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
      };
      const csv = [cols.join(',')]
        .concat(rows.map((row) => cols.map((c) => escape(row[c])).join(',')))
        .join('\n');
      const blob = new Blob([csv], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'companies_' + new Date().toISOString().slice(0, 10) + '.csv';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast('Export downloaded', 'success');
    } catch (err) {
      toast(errMsg(err), 'error');
    }
  }

  function renderSuperAdminBillingConfig(host, configs) {
    host.innerHTML = '';
    const byName = {};
    configs.forEach((c) => { byName[c.name] = c; });
    const present = SUPER_ADMIN_BILLING_CONFIG_KEYS.filter((k) => byName[k]);
    if (!present.length) {
      host.appendChild(section('Billing configuration', null, [
        emptyState('No billing settings exposed by this server.'),
      ]));
      return;
    }
    const inputs = {};
    const rows = present.map((key) => {
      const cfg = byName[key];
      const isSecret = !!cfg.is_sensitive;
      const value = cfg.value == null ? '' : cfg.value;
      const input = el('input', {
        class: 'us-input',
        type: isSecret ? 'password' : 'text',
        value,
        placeholder: cfg.default_value || '',
      });
      inputs[key] = { input, isSecret };
      const labelText = SUPER_ADMIN_BILLING_CONFIG_LABELS[key] || key;
      const wrap = el('label', { class: 'us-label' }, [
        el('span', { class: 'us-label-text' }, labelText),
        input,
        cfg.description ? el('span', { class: 'us-hint' }, cfg.description) : null,
      ]);
      if (isSecret) {
        const toggle = btn('Show', { onclick: () => {
          input.type = input.type === 'password' ? 'text' : 'password';
          toggle.textContent = input.type === 'password' ? 'Show' : 'Hide';
        } });
        wrap.appendChild(el('div', { class: 'us-section-row end' }, [toggle]));
      }
      return wrap;
    });
    const status = el('p', { class: 'us-status-line' }, '');
    const saveBtn = btn('Save billing settings', { kind: 'primary', onclick: async () => {
      const updates = [];
      Object.entries(inputs).forEach(([key, { input }]) => {
        const original = byName[key].value == null ? '' : byName[key].value;
        if (input.value !== original) updates.push({ name: key, value: input.value });
      });
      if (!updates.length) {
        status.textContent = 'No changes to save.';
        status.className = 'us-status-line';
        return;
      }
      saveBtn.disabled = true;
      try {
        await api.bulkUpdateServerConfig(updates);
        status.textContent = 'Saved ' + updates.length + ' setting(s).';
        status.className = 'us-status-line success';
        toast('Billing settings saved', 'success');
      } catch (err) {
        status.textContent = errMsg(err);
        status.className = 'us-status-line error';
      } finally {
        saveBtn.disabled = false;
      }
    } });
    host.appendChild(section(
      'Billing configuration',
      'Server-wide billing flags and Stripe credentials. Changes apply immediately.',
      [
        el('div', { class: 'us-grid-2' }, rows),
        status,
        el('div', { class: 'us-section-row end' }, [saveBtn]),
      ],
    ));
  }

  // ─── Mount ───────────────────────────────────────────────────────────

  async function mount(opts) {
    if (opts && opts.billingReturn) handleBillingReturn(opts.billingReturn);
    if (mounted) {
      // Re-mounts (eg. tab change) just refresh the requested tab.
      const tab = opts && opts.tab;
      if (tab && TAB_RENDERERS[tab]) setActiveTab(tab);
      else activatePanel(activeTab);
      return;
    }
    mounted = true;
    bindTabs();
    hideDesktopOnlyTabs();
    await ensureBillingTabVisible();
    await ensureSuperAdminTabVisible();
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

  window.UserSettings = { mount, setActiveTab, handleBillingReturn };
})();

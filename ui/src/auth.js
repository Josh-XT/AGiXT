/* Auth screen logic.
 *
 * Handles service selection, email+password login, registration, magic
 * link, and OAuth-via-system-browser flows. Mirrors the field order
 * and method set of the AGiXT NextJS web client login page, adapted
 * for a desktop app with no cookie store — JWTs land in the Rust-side
 * SQLite via the `login_password` / `register_account` IPCs. Magic
 * links and OAuth callbacks return through `agixt://` deep links.
 *
 * Exposes `window.AgixtAuth.boot({onAuthenticated})` which the app shell
 * calls once on startup. When auth completes, `onAuthenticated(context)` fires
 * with the login/register response so the caller can handle limited billing
 * sessions.
 */
(function () {
  const tauri = window.__TAURI__;
  if (!tauri) return;
  const invoke = tauri.core.invoke;
  const opener = tauri.opener || (tauri.core && tauri.core.invoke ? null : null);

  const $ = (id) => document.getElementById(id);
  const OAUTH_PROVIDER_TIMEOUT_MS = 6000;

  function brandAssetHref(path) {
    const value = String(path || '').trim();
    if (!value) return '';
    if (/^(https?:|data:|blob:|\/)/i.test(value)) return value;
    return window.__AGIXT_WEB_RUNTIME ? `/${value.replace(/^\/+/, '')}` : value;
  }

  let brands = [];
  let currentBrand = null; // {slug, label, default_url}
  let mfaPending = false;
  let onAuthenticatedCb = null;
  let oauthRefreshSeq = 0;
  let invitationUnlisten = null;
  let pendingInvitation = null;
  let authFocusGuardBound = false;
  let lastAuthInput = null;
  let lastAuthPointerDownAt = 0;
  let authTouchKeyboardBound = false;
  let authTouchKeyboardEnabled = false;
  let authTouchKeyboardTarget = null;
  let authTouchKeyboardMode = 'abc';
  let authTouchKeyboardShift = false;
  const INVITATION_STORAGE_KEY = 'agixt.desktop.pendingInvitation.v1';
  const AUTH_TYPING_INPUT_IDS = new Set([
    'login-email',
    'login-password',
    'login-mfa',
    'reg-first',
    'reg-last',
    'reg-email',
    'reg-password',
  ]);
  const AUTH_TOUCH_KEYBOARD_NEXT = {
    'login-email': 'login-password',
    'login-password': null,
    'login-mfa': null,
    'reg-first': 'reg-last',
    'reg-last': 'reg-email',
    'reg-email': 'reg-password',
    'reg-password': null,
  };

  function setStatus(text, cls) {
    const el = $('auth-status');
    if (!el) return;
    el.textContent = text || '';
    el.className = 'auth-status' + (cls ? ` ${cls}` : '');
  }

  function activeServerUrl() {
    const v = $('server-url').value.trim();
    if (v) return v.replace(/\/+$/, '');
    return (currentBrand && currentBrand.default_url) || 'http://localhost:7437';
  }

  function activeWebUrl() {
    const v = $('web-url').value.trim();
    if (v) return v.replace(/\/+$/, '');
    return (currentBrand && currentBrand.default_web_url) || 'http://localhost:3437';
  }

  function withTimeout(promise, ms, label) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(label || 'Request timed out')), ms);
      Promise.resolve(promise).then(
        (value) => {
          clearTimeout(timer);
          resolve(value);
        },
        (error) => {
          clearTimeout(timer);
          reject(error);
        },
      );
    });
  }

  function isAndroidRuntime() {
    return /Android/i.test((window.navigator && window.navigator.userAgent) || '');
  }

  function shouldDiscoverOAuthProviders() {
    // Fire OS WebView can churn the IME input connection while the login page
    // is typing. XT School tablet builds do not use provider login, so keep
    // discovery off that hot path entirely.
    return !isAndroidRuntime() && (!currentBrand || currentBrand.slug !== 'xtschool');
  }

  function shouldUseAuthTouchKeyboard() {
    return isAndroidRuntime() && currentBrand && currentBrand.slug === 'xtschool';
  }

  function isAuthTypingInput(el) {
    return !!(el && AUTH_TYPING_INPUT_IDS.has(el.id));
  }

  function isAuthScreenVisible() {
    const screen = $('auth-screen');
    return !!(screen && !screen.hidden);
  }

  function bindAuthFocusGuard() {
    if (authFocusGuardBound) return;
    authFocusGuardBound = true;

    document.addEventListener('pointerdown', (e) => {
      if (!isAuthScreenVisible()) return;
      if (e.target && e.target.closest && e.target.closest('input, select, button, textarea, a')) {
        lastAuthPointerDownAt = Date.now();
      }
    }, true);

    document.addEventListener('focusin', (e) => {
      if (isAuthTypingInput(e.target)) lastAuthInput = e.target;
    }, true);

    document.addEventListener('focusout', (e) => {
      if (!isAuthTypingInput(e.target)) return;
      const blurred = e.target;
      setTimeout(() => {
        if (!isAuthScreenVisible()) return;
        if (lastAuthInput !== blurred) return;
        if (Date.now() - lastAuthPointerDownAt < 350) return;
        const active = document.activeElement;
        if (active && active !== document.body && active !== document.documentElement) return;
        if (blurred.hidden || blurred.disabled || blurred.readOnly || !document.body.contains(blurred)) return;
        try {
          blurred.focus({ preventScroll: true });
        } catch (_) {
          try { blurred.focus(); } catch (_) {}
        }
      }, 80);
    }, true);
  }

  function bindAuthTouchKeyboard() {
    if (authTouchKeyboardBound) return;
    authTouchKeyboardBound = true;

    AUTH_TYPING_INPUT_IDS.forEach((id) => {
      const input = $(id);
      if (!input) return;
      input.addEventListener('pointerdown', (e) => {
        if (!authTouchKeyboardEnabled) return;
        e.preventDefault();
        e.stopPropagation();
        showAuthTouchKeyboard(input);
      }, true);
      input.addEventListener('focusin', () => {
        if (authTouchKeyboardEnabled) showAuthTouchKeyboard(input);
      }, true);
    });

    document.addEventListener('pointerdown', (e) => {
      if (!authTouchKeyboardEnabled) return;
      const target = e.target;
      const keyboard = $('auth-touch-keyboard');
      if (keyboard && target && keyboard.contains(target)) return;
      if (isAuthTypingInput(target)) return;
      hideAuthTouchKeyboard();
    }, true);
  }

  function syncAuthTouchKeyboardAvailability() {
    const enabled = Boolean(shouldUseAuthTouchKeyboard());
    authTouchKeyboardEnabled = enabled;
    if (document.body) {
      document.body.classList.toggle('auth-touch-keyboard-enabled', enabled);
    }
    AUTH_TYPING_INPUT_IDS.forEach((id) => {
      const input = $(id);
      if (!input) return;
      if (enabled) {
        if (!input.dataset.authTouchOriginalReadonly) {
          input.dataset.authTouchOriginalReadonly = input.readOnly ? '1' : '0';
          input.dataset.authTouchOriginalInputmode = input.getAttribute('inputmode') || '';
        }
        input.readOnly = true;
        input.setAttribute('inputmode', 'none');
        input.setAttribute('data-auth-touch-keyboard', 'true');
      } else if (input.hasAttribute('data-auth-touch-keyboard')) {
        input.readOnly = input.dataset.authTouchOriginalReadonly === '1';
        if (input.dataset.authTouchOriginalInputmode) {
          input.setAttribute('inputmode', input.dataset.authTouchOriginalInputmode);
        } else {
          input.removeAttribute('inputmode');
        }
        input.removeAttribute('data-auth-touch-keyboard');
        delete input.dataset.authTouchOriginalReadonly;
        delete input.dataset.authTouchOriginalInputmode;
      }
    });
    if (!enabled) {
      hideAuthTouchKeyboard();
      return;
    }
    if (isAuthTypingInput(document.activeElement)) {
      showAuthTouchKeyboard(document.activeElement);
    }
  }

  function defaultAuthTouchKeyboardMode(input) {
    return input && input.id === 'login-mfa' ? 'numbers' : 'abc';
  }

  function showAuthTouchKeyboard(input) {
    if (!authTouchKeyboardEnabled || !isAuthScreenVisible() || !isAuthTypingInput(input)) return;
    if (authTouchKeyboardTarget !== input) {
      authTouchKeyboardMode = defaultAuthTouchKeyboardMode(input);
      authTouchKeyboardShift = false;
    }
    authTouchKeyboardTarget = input;
    const keyboard = $('auth-touch-keyboard');
    if (!keyboard) return;
    keyboard.hidden = false;
    if (document.body) document.body.classList.add('auth-touch-keyboard-open');
    try {
      input.focus({ preventScroll: true });
    } catch (_) {
      try { input.focus(); } catch (_) {}
    }
    try {
      const pos = input.value.length;
      input.setSelectionRange(pos, pos);
    } catch (_) {}
    renderAuthTouchKeyboard();
  }

  function hideAuthTouchKeyboard() {
    const keyboard = $('auth-touch-keyboard');
    if (keyboard) keyboard.hidden = true;
    if (document.body) document.body.classList.remove('auth-touch-keyboard-open');
  }

  function authTouchKey(label, action, value, className) {
    return { label, action, value, className: className || '' };
  }

  function authTouchCharKey(char) {
    const display = authTouchKeyboardShift && /^[a-z]$/.test(char) ? char.toUpperCase() : char;
    return authTouchKey(display, 'insert', char);
  }

  function authTouchKeyboardRows(input) {
    const nextId = input ? AUTH_TOUCH_KEYBOARD_NEXT[input.id] : null;
    const doneKey = authTouchKey(nextId ? 'Next' : 'Done', nextId ? 'next' : 'done', null, 'wide primary');
    if (input && input.id === 'login-mfa') {
      return [
        ['1', '2', '3'].map(authTouchCharKey),
        ['4', '5', '6'].map(authTouchCharKey),
        ['7', '8', '9'].map(authTouchCharKey),
        [
          authTouchKey('Back', 'backspace', null, 'wide action'),
          authTouchCharKey('0'),
          doneKey,
        ],
      ];
    }
    if (authTouchKeyboardMode === 'symbols') {
      const bottom = [authTouchKey('ABC', 'mode', 'abc', 'wide action')];
      if (input && (input.id === 'login-email' || input.id === 'reg-email')) {
        bottom.push(authTouchKey('@', 'insert', '@'));
        bottom.push(authTouchKey('.', 'insert', '.'));
        bottom.push(authTouchKey('-', 'insert', '-'));
        bottom.push(authTouchKey('_', 'insert', '_'));
        bottom.push(authTouchKey('.com', 'insert', '.com', 'wide'));
      } else {
        bottom.push(authTouchKey('Space', 'insert', ' ', 'xwide'));
      }
      bottom.push(doneKey);
      return [
        ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'].map(authTouchCharKey),
        ['@', '#', '$', '%', '&', '*', '-', '_', '+', '='].map((c) => authTouchKey(c, 'insert', c)),
        [
          authTouchKey('.', 'insert', '.'),
          authTouchKey('/', 'insert', '/'),
          authTouchKey('?', 'insert', '?'),
          authTouchKey('!', 'insert', '!'),
          authTouchKey('"', 'insert', '"'),
          authTouchKey("'", 'insert', "'"),
          authTouchKey(':', 'insert', ':'),
          authTouchKey(';', 'insert', ';'),
          authTouchKey('Back', 'backspace', null, 'wide action'),
        ],
        bottom,
      ];
    }
    const isEmail = input && (input.id === 'login-email' || input.id === 'reg-email');
    const isName = input && (input.id === 'reg-first' || input.id === 'reg-last');
    const bottom = [authTouchKey('123', 'mode', 'symbols', 'wide action')];
    if (isEmail) {
      bottom.push(authTouchKey('@', 'insert', '@'));
      bottom.push(authTouchKey('.', 'insert', '.'));
      bottom.push(authTouchKey('-', 'insert', '-'));
      bottom.push(authTouchKey('_', 'insert', '_'));
      bottom.push(authTouchKey('.com', 'insert', '.com', 'wide'));
    } else if (isName) {
      bottom.push(authTouchKey('-', 'insert', '-'));
      bottom.push(authTouchKey("'", 'insert', "'"));
      bottom.push(authTouchKey('Space', 'insert', ' ', 'xwide'));
    } else {
      bottom.push(authTouchKey('@', 'insert', '@'));
      bottom.push(authTouchKey('.', 'insert', '.'));
      bottom.push(authTouchKey('-', 'insert', '-'));
      bottom.push(authTouchKey('_', 'insert', '_'));
      bottom.push(authTouchKey('Space', 'insert', ' ', 'xwide'));
    }
    bottom.push(doneKey);
    return [
      'qwertyuiop'.split('').map(authTouchCharKey),
      'asdfghjkl'.split('').map(authTouchCharKey),
      [
        authTouchKey('Shift', 'shift', null, `wide action${authTouchKeyboardShift ? ' is-active' : ''}`),
        ...'zxcvbnm'.split('').map(authTouchCharKey),
        authTouchKey('Back', 'backspace', null, 'wide action'),
      ],
      bottom,
    ];
  }

  function renderAuthTouchKeyboard() {
    const keyboard = $('auth-touch-keyboard');
    if (!keyboard || !authTouchKeyboardTarget) return;
    keyboard.innerHTML = '';
    authTouchKeyboardRows(authTouchKeyboardTarget).forEach((row) => {
      const rowEl = document.createElement('div');
      rowEl.className = 'auth-touch-keyboard-row';
      row.forEach((key) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.tabIndex = -1;
        btn.className = `auth-touch-key ${key.className || ''}`.trim();
        btn.textContent = key.label;
        btn.addEventListener('pointerdown', (e) => {
          e.preventDefault();
          e.stopPropagation();
          lastAuthPointerDownAt = Date.now();
          handleAuthTouchKey(key);
        });
        rowEl.appendChild(btn);
      });
      keyboard.appendChild(rowEl);
    });
  }

  function authTouchSelection(input) {
    const value = input.value || '';
    let start = value.length;
    let end = value.length;
    try {
      if (typeof input.selectionStart === 'number') start = input.selectionStart;
      if (typeof input.selectionEnd === 'number') end = input.selectionEnd;
    } catch (_) {}
    return { value, start, end };
  }

  function commitAuthTouchValue(input, value, caret) {
    input.value = value;
    try {
      input.focus({ preventScroll: true });
    } catch (_) {
      try { input.focus(); } catch (_) {}
    }
    try {
      input.setSelectionRange(caret, caret);
    } catch (_) {}
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function insertAuthTouchText(text) {
    const input = authTouchKeyboardTarget;
    if (!input) return;
    const selection = authTouchSelection(input);
    const before = selection.value.slice(0, selection.start);
    const after = selection.value.slice(selection.end);
    let insert = String(text || '');
    if (input.maxLength > -1) {
      const available = Math.max(0, input.maxLength - before.length - after.length);
      insert = insert.slice(0, available);
    }
    if (!insert) return;
    const nextValue = `${before}${insert}${after}`;
    commitAuthTouchValue(input, nextValue, before.length + insert.length);
  }

  function backspaceAuthTouchText() {
    const input = authTouchKeyboardTarget;
    if (!input) return;
    const selection = authTouchSelection(input);
    if (selection.start === 0 && selection.end === 0) return;
    const deleteStart = selection.start === selection.end
      ? Math.max(0, selection.start - 1)
      : selection.start;
    const nextValue = selection.value.slice(0, deleteStart) + selection.value.slice(selection.end);
    commitAuthTouchValue(input, nextValue, deleteStart);
  }

  function focusNextAuthTouchInput() {
    const nextId = authTouchKeyboardTarget ? AUTH_TOUCH_KEYBOARD_NEXT[authTouchKeyboardTarget.id] : null;
    const nextInput = nextId ? $(nextId) : null;
    if (nextInput && !nextInput.hidden && !nextInput.disabled) {
      showAuthTouchKeyboard(nextInput);
    } else {
      hideAuthTouchKeyboard();
      if (authTouchKeyboardTarget) {
        try { authTouchKeyboardTarget.blur(); } catch (_) {}
      }
    }
  }

  function handleAuthTouchKey(key) {
    const input = authTouchKeyboardTarget;
    if (!input) return;
    if (key.action === 'insert') {
      let value = key.value;
      if (authTouchKeyboardMode === 'abc' && authTouchKeyboardShift && /^[a-z]$/.test(value)) {
        value = value.toUpperCase();
        authTouchKeyboardShift = false;
      }
      insertAuthTouchText(value);
      if (!authTouchKeyboardShift) renderAuthTouchKeyboard();
      return;
    }
    if (key.action === 'backspace') {
      backspaceAuthTouchText();
      return;
    }
    if (key.action === 'shift') {
      authTouchKeyboardShift = !authTouchKeyboardShift;
      renderAuthTouchKeyboard();
      return;
    }
    if (key.action === 'mode') {
      authTouchKeyboardMode = key.value || 'abc';
      authTouchKeyboardShift = false;
      renderAuthTouchKeyboard();
      return;
    }
    if (key.action === 'next') {
      focusNextAuthTouchInput();
      return;
    }
    if (key.action === 'done') {
      hideAuthTouchKeyboard();
      try { input.blur(); } catch (_) {}
    }
  }

  function normalizeInvitation(input) {
    if (!input) return null;
    let data = input;
    if (typeof input === 'string') {
      try {
        const u = new URL(input);
        data = Object.fromEntries(u.searchParams.entries());
      } catch (_) {
        try {
          data = Object.fromEntries(new URLSearchParams(input).entries());
        } catch (_) {
          data = {};
        }
      }
    }
    const id = data.invitation_id || data.invitationId || data.invitation || data.id;
    if (!id) return null;
    return {
      invitation_id: String(id),
      email: data.email ? String(data.email) : '',
      company: data.company || data.company_name ? String(data.company || data.company_name) : '',
    };
  }

  function hasInvitationInLocation() {
    if (typeof window === 'undefined' || !window.location) return false;
    try {
      const params = new URLSearchParams(window.location.search || '');
      return Boolean(params.get('invitation_id') || params.get('invitationId') || params.get('invitation') || params.get('invite'));
    } catch (_) {
      return false;
    }
  }

  function consumeInvitationUrl(targetPath) {
    if (!hasInvitationInLocation() || !window.history || typeof window.history.replaceState !== 'function') return false;
    try {
      const url = new URL(window.location.href);
      [
        'invitation_id',
        'invitationId',
        'invitation',
        'invite',
        'id',
        'email',
        'company',
        'company_name',
      ].forEach((key) => url.searchParams.delete(key));
      const query = url.searchParams.toString();
      const nextPath = targetPath || url.pathname || '/user/register';
      window.history.replaceState({}, '', `${nextPath}${query ? `?${query}` : ''}${url.hash || ''}`);
      return true;
    } catch (_) {
      return false;
    }
  }

  function loadPendingInvitation() {
    if (pendingInvitation) return pendingInvitation;
    try {
      pendingInvitation = normalizeInvitation(JSON.parse(localStorage.getItem(INVITATION_STORAGE_KEY) || 'null'));
    } catch (_) {
      pendingInvitation = null;
    }
    return pendingInvitation;
  }

  function applyPendingInvitationToUi() {
    const inv = loadPendingInvitation();
    const banner = $('auth-invite');
    const body = $('auth-invite-body');
    if (!banner || !body) return;
    const meta = $('auth-invite-meta');
    const companyChip = $('auth-invite-company');
    const companyText = $('auth-invite-company-text');
    const emailChip = $('auth-invite-email');
    const emailText = $('auth-invite-email-text');
    const warn = $('auth-invite-warn');
    const actions = banner.querySelector('.auth-invite-actions');
    if (!inv) {
      banner.hidden = true;
      body.textContent = '';
      if (meta) meta.hidden = true;
      if (companyChip) companyChip.hidden = true;
      if (emailChip) emailChip.hidden = true;
      if (warn) { warn.hidden = true; warn.textContent = ''; }
      if (actions) actions.hidden = true;
      return;
    }
    body.textContent = inv.company
      ? `Sign in or create an account to join ${inv.company}.`
      : 'Sign in or create an account to accept this invitation.';
    banner.hidden = false;
    const hasCompany = Boolean(inv.company);
    const hasEmail = Boolean(inv.email);
    if (companyChip && companyText) {
      companyText.textContent = inv.company || '';
      companyChip.hidden = !hasCompany;
    }
    if (emailChip && emailText) {
      emailText.textContent = inv.email || '';
      emailChip.hidden = !hasEmail;
    }
    if (meta) meta.hidden = !(hasCompany || hasEmail);
    if (inv.email) {
      if ($('login-email') && !$('login-email').value) $('login-email').value = inv.email;
      if ($('reg-email') && !$('reg-email').value) $('reg-email').value = inv.email;
    }
    if (actions) actions.hidden = false;
    refreshInvitationEmailWarning();
  }

  function refreshInvitationEmailWarning() {
    const inv = loadPendingInvitation();
    const warn = $('auth-invite-warn');
    if (!warn) return;
    if (!inv || !inv.email) {
      warn.hidden = true;
      warn.textContent = '';
      return;
    }
    // Which email field is the user typing into right now?
    const activePane = $('pane-register') && !$('pane-register').hidden ? 'register' : 'login';
    const fieldId = activePane === 'register' ? 'reg-email' : 'login-email';
    const typed = ($(fieldId) && $(fieldId).value || '').trim().toLowerCase();
    const expected = String(inv.email).trim().toLowerCase();
    if (!typed || typed === expected) {
      warn.hidden = true;
      warn.textContent = '';
      return;
    }
    warn.hidden = false;
    warn.textContent = `This invitation is for ${inv.email}. Signing in or registering as ${typed} won't accept it.`;
  }

  function clickAcceptInvitation() {
    const inv = loadPendingInvitation();
    if (!inv) return;
    // Route the user into the most useful flow based on what we know:
    //  - If we have an email and no password is required, prefer magic
    //    link (matches the existing-user invitation path which returns a
    //    magic_link the desktop already knows how to consume).
    //  - Otherwise prompt them to register (new user) or sign in.
    // Keep the actual auth path identical to the existing button handlers
    // — the user just clicks them after we pre-fill and focus the email.
    if (inv.email) {
      if ($('login-email')) $('login-email').value = inv.email;
      if ($('reg-email')) $('reg-email').value = inv.email;
    }
    // Default to the register pane (covers brand-new invitees); existing
    // users who already have an account can flip to "Sign in" themselves.
    showPane('register');
    setStatus(
      inv.company
        ? `Continue to join ${inv.company}: create your account or switch to Sign in if you already have one.`
        : 'Continue to accept this invitation: create your account or switch to Sign in if you already have one.',
      'info',
    );
    if ($('reg-first')) { try { $('reg-first').focus(); } catch (_) {} }
  }

  function clickDeclineInvitation() {
    const inv = loadPendingInvitation();
    if (!inv) return;
    const target = inv.company ? `the invitation to ${inv.company}` : 'this invitation';
    const ok = window.confirm(
      `Decline ${target}? You can ask the inviter to resend if you change your mind.`,
    );
    if (!ok) return;
    clearPendingInvitation();
    setStatus(
      `Invitation declined. You can still sign in or register normally.`,
      'info',
    );
  }

  function setPendingInvitation(input) {
    const inv = normalizeInvitation(input);
    if (!inv) return false;
    pendingInvitation = inv;
    try { localStorage.setItem(INVITATION_STORAGE_KEY, JSON.stringify(inv)); } catch (_) {}
    applyPendingInvitationToUi();
    setStatus('Sign in or create an account to accept the invitation.', 'info');
    return true;
  }

  function clearPendingInvitation() {
    pendingInvitation = null;
    try { localStorage.removeItem(INVITATION_STORAGE_KEY); } catch (_) {}
    applyPendingInvitationToUi();
  }

  function invitationErrorMessage(body, fallback) {
    if (!body) return fallback || 'Failed to accept invitation.';
    if (typeof body === 'string') return body || fallback || 'Failed to accept invitation.';
    return body.message || body.detail || body.error || fallback || 'Failed to accept invitation.';
  }

  async function acceptPendingInvitation() {
    const inv = loadPendingInvitation();
    if (!inv) return null;

    let settings = null;
    try {
      settings = await invoke('get_settings');
    } catch (_) {
      settings = null;
    }
    const jwt = settings && settings.jwt;
    const serverUrl = ((settings && settings.server_url) || activeServerUrl()).replace(/\/+$/, '');
    if (!jwt || !serverUrl) return null;

    const resp = await fetch(`${serverUrl}/v1/invitations/${encodeURIComponent(inv.invitation_id)}/accept`, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${jwt}`,
      },
    });
    let body = null;
    try {
      const text = await resp.text();
      body = text ? JSON.parse(text) : null;
    } catch (_) {
      body = null;
    }
    const msg = invitationErrorMessage(body, '');
    const alreadyAccepted = resp.status === 400 && /already[_\s-]?accepted/i.test(`${msg} ${body && body.error ? body.error : ''}`);
    if (!resp.ok && !alreadyAccepted) {
      const err = new Error(msg || `Failed to accept invitation (${resp.status}).`);
      err.status = resp.status;
      err.body = body;
      throw err;
    }

    clearPendingInvitation();
    setStatus(inv.company ? `Invitation accepted. You're now connected to ${inv.company}.` : 'Invitation accepted.', 'success');
    return { accepted: true, already_accepted: alreadyAccepted };
  }

  async function finishFromMagicLink(resp, fallbackMessage) {
    if (!resp || !resp.magic_link) return false;
    await persistBrand();
    await invoke('login_with_jwt', {
      serverUrl: activeServerUrl(),
      raw: resp.magic_link,
    });
    setStatus(fallbackMessage || resp.message || 'Signed in.', 'success');
    finish(resp);
    return true;
  }

  function bindInvitationListener() {
    if (invitationUnlisten || !tauri.event || typeof tauri.event.listen !== 'function') return;
    const listener = tauri.event.listen('agixt-invitation', (ev) => {
      setPendingInvitation(ev && ev.payload);
    });
    if (listener && typeof listener.then === 'function') {
      listener.then((unlisten) => { invitationUnlisten = unlisten; }).catch(() => {});
    } else {
      invitationUnlisten = listener;
    }
  }

  function setActiveBrand(slug) {
    currentBrand = brands.find((b) => b.slug === slug) || brands[brands.length - 1];
    $('service-brand').value = currentBrand.slug;
    $('server-url').value = currentBrand.default_url;
    $('web-url').value = currentBrand.default_web_url || '';
    const serviceField = $('service-brand-field') || ($('service-brand') && $('service-brand').closest('.field'));
    if (serviceField) {
      serviceField.hidden = Boolean(window.__AGIXT_WEB_RUNTIME && currentBrand.locked);
    }
    // URL fields are only shown/editable in "custom" mode. Every other
    // brand has a known server+web pair, so exposing the fields would
    // just be noise — and "local" pins to localhost:7437 anyway.
    const isCustom = currentBrand.slug === 'custom';
    $('server-url').readOnly = !isCustom;
    $('web-url').readOnly = !isCustom;
    $('custom-server-field').classList.toggle('readonly', !isCustom);
    $('custom-web-field').classList.toggle('readonly', !isCustom);
    $('custom-server-field').hidden = !isCustom;
    $('custom-web-field').hidden = !isCustom;
    const isLocal = currentBrand.slug === 'local';
    $('local-pane').hidden = !isLocal;
    applyBrandIdentity(currentBrand.slug);
    if (isLocal) {
      refreshLocalStatus();
    } else {
      stopLocalStatusPoll();
    }
    syncAuthTouchKeyboardAvailability();
  }

  // Map brand slug to its top-bar mark + display title. We intentionally
  // keep the title and the chrome (font, colors) the same across brands —
  // only the logo and product name change so the chat experience stays
  // consistent regardless of which AGiXT-derived service the user is
  // signed in to.
  const BRAND_IDENTITY = {
    web:        { logo: 'assets/brands/agixt.svg',      favicon: 'assets/brands/agixt-favicon.png',       title: 'AGiXT' },
    agixt:      { logo: 'assets/brands/agixt.svg',      favicon: 'assets/brands/agixt-favicon.png',       title: 'AGiXT' },
    nursext:    { logo: 'assets/brands/nursext.svg',    favicon: 'assets/brands/nursext-favicon.png',     title: 'NurseXT' },
    xtsystems:  { logo: 'assets/brands/xtsystems.svg',  favicon: 'assets/brands/xtsystems-favicon.png',   title: 'XT Systems' },
    boltremote: { logo: 'assets/brands/boltremote.svg', favicon: 'assets/brands/boltremote-favicon.svg',  title: 'BoltRemote' },
    local:      { logo: 'assets/brands/agixt.svg',      favicon: 'assets/brands/agixt-favicon.png',       title: 'AGiXT' },
    custom:     { logo: 'assets/brands/agixt.svg',      favicon: 'assets/brands/agixt-favicon.png',       title: 'AGiXT' },
  };

  function applyBrandIdentity(slug) {
    const id = BRAND_IDENTITY[slug] || BRAND_IDENTITY.custom;
    const img = $('brand-mark-img');
    const title = $('brand-title');
    const mark = $('brand-mark');
    const logo = brandAssetHref(id.logo);
    if (img) img.src = logo;
    if (title) title.textContent = id.title;
    if (id.title) document.title = id.title;
    const faviconPath = id.favicon || id.logo;
    if (faviconPath && document.head) {
      let favicon = $('app-favicon') || document.querySelector('link[rel~="icon"]');
      if (!favicon) {
        favicon = document.createElement('link');
        favicon.id = 'app-favicon';
        favicon.rel = 'icon';
        document.head.appendChild(favicon);
      }
      favicon.href = brandAssetHref(faviconPath);
      favicon.type = String(faviconPath).toLowerCase().endsWith('.png') ? 'image/png' : 'image/svg+xml';
    }
    if (mark) mark.classList.remove('fallback');
    // Also paint the sidenav brand slot — it's the first item users see
    // in the activity bar after sign-in, so it has to track the active
    // service brand the same way the auth-screen mark does.
    const sideImg = $('sidenav-brand-mark-img');
    const sideMark = $('sidenav-brand-mark');
    if (sideImg) sideImg.src = logo;
    if (sideMark) {
      sideMark.classList.remove('fallback');
      const slot = sideMark.closest('.sidenav-brand');
      if (slot) slot.title = id.title;
    }
  }

  // Expose so app.js can apply the saved brand on boot — without this
  // the topbar logo always reverts to the AGiXT default after restart
  // even when the user picked a different service like BoltRemote.
  window.AgixtBranding = { apply: applyBrandIdentity, identities: BRAND_IDENTITY };

  // ----- Tab switching -----------------------------------------------------

  function showPane(which) {
    const isLogin = which === 'login';
    $('pane-login').hidden = !isLogin;
    $('pane-register').hidden = isLogin;
    $('tab-login').setAttribute('aria-selected', String(isLogin));
    $('tab-register').setAttribute('aria-selected', String(!isLogin));
    setStatus('');
    applyPendingInvitationToUi();
    if (authTouchKeyboardEnabled) hideAuthTouchKeyboard();
  }

  $('tab-login').addEventListener('click', () => showPane('login'));
  $('tab-register').addEventListener('click', () => showPane('register'));

  // ----- Brand / server selector ------------------------------------------

  async function loadBrands() {
    brands = await invoke('list_service_brands');
    const sel = $('service-brand');
    sel.innerHTML = '';
    brands.forEach((b) => {
      const opt = document.createElement('option');
      opt.value = b.slug;
      opt.textContent = b.label;
      sel.appendChild(opt);
    });
    // Default to whatever's saved, else "local" (the dedicated
    // localhost:7437 entry replaces the old "custom"-as-default).
    const settings = await invoke('get_settings');
    const lockedBrand = brands.find((b) => b.locked);
    let initial = settings.service_brand || 'local';
    if (lockedBrand) {
      initial = lockedBrand.slug;
    } else if (window.__AGIXT_WEB_RUNTIME && settings.service_brand !== 'custom') {
      initial = 'web';
    }
    setActiveBrand(initial);
    if (initial === 'custom') {
      if (settings.server_url) $('server-url').value = settings.server_url;
      if (settings.web_url) $('web-url').value = settings.web_url;
    }
    const loginEmail = $('login-email');
    if (settings.user_email && loginEmail && !loginEmail.value && document.activeElement !== loginEmail) {
      loginEmail.value = settings.user_email;
    }
  }

  // ----- OAuth providers --------------------------------------------------

  async function refreshOAuthProviders() {
    const refreshSeq = ++oauthRefreshSeq;
    const row = $('oauth-row');
    const wrap = $('oauth-buttons');
    wrap.innerHTML = '';
    if (!shouldDiscoverOAuthProviders()) {
      row.hidden = true;
      return;
    }
    let providers = [];
    try {
      providers = await withTimeout(
        invoke('list_oauth_providers', { serverUrl: activeServerUrl() }),
        OAUTH_PROVIDER_TIMEOUT_MS,
        'OAuth provider discovery timed out',
      );
    } catch (e) {
      // Servers without /v1/oauth simply have no SSO buttons.
      console.debug('no oauth providers for', activeServerUrl(), e);
    }
    if (refreshSeq !== oauthRefreshSeq) return;
    if (!providers || providers.length === 0) {
      row.hidden = true;
      return;
    }
    providers.forEach((p) => {
      const btn = document.createElement('button');
      btn.className = 'btn btn-oauth';
      btn.dataset.provider = p.name;
      const iconNode = oauthIconNode(p.name);
      btn.appendChild(iconNode);
      const label = document.createElement('span');
      label.textContent = `Continue with ${prettyProviderName(p.name)}`;
      btn.appendChild(label);
      btn.addEventListener('click', () => startOAuth(p));
      wrap.appendChild(btn);
    });
    row.hidden = false;
  }

  /** Map a provider name to the local SVG asset. Strips `_sso` so the
   *  mark file lookups match `microsoft.svg`, `github.svg`, etc.  */
  function oauthIconAsset(name) {
    const slug = (name || '').toLowerCase().replace(/_sso$/, '');
    const known = new Set([
      'microsoft', 'github', 'discord', 'spotify', 'google', 'apple',
    ]);
    if (known.has(slug)) return `assets/oauth/${slug}.svg`;
    return null;
  }

  function oauthIconNode(name) {
    const wrap = document.createElement('span');
    wrap.className = 'oauth-icon';
    const asset = oauthIconAsset(name);
    if (asset) {
      const img = document.createElement('img');
      img.src = asset;
      img.alt = '';
      // Some marks (GitHub, Apple) are pure-white and would disappear on
      // the dark panel without a darker background tile.
      const slug = name.toLowerCase().replace(/_sso$/, '');
      if (slug === 'github' || slug === 'apple') {
        wrap.style.background = '#0d1117';
        wrap.style.padding = '2px';
      }
      wrap.appendChild(img);
    } else {
      wrap.classList.add('fallback');
      wrap.textContent = oauthGlyph(name);
    }
    return wrap;
  }

  function prettyProviderName(name) {
    const t = (name || '').replace(/_(sso|oauth|login)$/, '');
    return t.charAt(0).toUpperCase() + t.slice(1);
  }
  function oauthGlyph(name) {
    const k = (name || '').toLowerCase();
    if (k.includes('google')) return 'G';
    if (k.includes('microsoft') || k.includes('teams') || k.includes('office')) return 'M';
    if (k.includes('github')) return '⌥';
    if (k.includes('discord')) return 'D';
    if (k.includes('spotify')) return '♫';
    if (k.includes('apple')) return '';
    return '◯';
  }

  async function startOAuth(provider) {
    setStatus(`Opening ${prettyProviderName(provider.name)} sign-in in your browser…`);
    // OAuth completes via an `agixt://` deep-link callback handled in
    // Rust, which fires `agixt-authenticated` *without* round-tripping
    // through the auth-screen DOM. If we don't persist the brand here,
    // settings.service_brand stays unset and the topbar logo defaults
    // back to AGiXT after restart — even when the user signed in via
    // BoltRemote/NurseXT/etc. Persist before opening the browser so the
    // brand survives every login outcome.
    try { await persistBrand(); } catch (e) { console.warn('persistBrand failed', e); }
    let result;
    try {
      result = await invoke('build_oauth_login_url', {
        args: {
          server_url: activeServerUrl(),
          // The OAuth provider redirects here, *not* to the API. AGiXT
          // pre-registered `{web_url}/user/close/{provider}` with each
          // OAuth app, so we have to use that URL exactly or the
          // provider rejects with `redirect_uri_mismatch`.
          web_url: activeWebUrl(),
          provider,
        },
      });
    } catch (e) {
      setStatus(`Couldn't build OAuth URL: ${e.error || e}`, 'error');
      return;
    }
    try {
      // tauri-plugin-opener exposes openUrl as a JS helper; fall back to
      // window.open which Tauri intercepts as the system browser when the
      // origin doesn't match the app.
      if (window.__TAURI__.opener && window.__TAURI__.opener.openUrl) {
        await window.__TAURI__.opener.openUrl(result.url);
      } else {
        window.open(result.url, '_blank', 'noopener');
      }
    } catch (e) {
      console.warn('opener failed, falling back', e);
      window.open(result.url, '_blank', 'noopener');
    }
    setStatus(
      'After authorizing in your browser, you will be returned here automatically.',
      'info',
    );
  }

  $('service-brand').addEventListener('change', async () => {
    if (currentBrand && currentBrand.locked) {
      $('service-brand').value = currentBrand.slug;
      return;
    }
    setActiveBrand($('service-brand').value);
    try { await persistBrand(); } catch (e) { console.warn('persistBrand failed', e); }
    if (shouldDiscoverOAuthProviders()) await refreshOAuthProviders();
  });
  $('server-url').addEventListener('change', async () => {
    try { await persistBrand(); } catch (e) { console.warn('persistBrand failed', e); }
    if (shouldDiscoverOAuthProviders()) await refreshOAuthProviders();
  });
  $('web-url').addEventListener('change', async () => {
    try { await persistBrand(); } catch (e) { console.warn('persistBrand failed', e); }
  });

  // ----- Email + password login -------------------------------------------

  $('btn-login').addEventListener('click', async () => {
    const email = $('login-email').value.trim();
    const password = $('login-password').value;
    if (!email || !password) {
      setStatus('Email and password required.', 'error');
      return;
    }
    const args = {
      server_url: activeServerUrl(),
      email,
      password,
    };
    if (mfaPending) {
      const token = $('login-mfa').value.trim();
      if (!token) {
        setStatus('Enter the 6-digit authenticator code.', 'error');
        return;
      }
      args.mfa_token = token;
    }
    setStatus('Signing in…');
    try {
      const resp = await invoke('login_password', { args });
      if (resp.token) {
        await persistBrand();
        await acceptPendingInvitation();
        setStatus('Signed in.', 'success');
        finish(resp);
        return;
      }
      if (resp.mfa_required) {
        mfaPending = true;
        $('mfa-field').hidden = false;
        $('login-mfa').focus();
        setStatus('Enter your 6-digit authenticator code.', 'info');
        return;
      }
      setStatus(resp.detail || 'Login failed.', 'error');
    } catch (e) {
      setStatus(prettyError(e), 'error');
    }
  });

  // ----- Magic link --------------------------------------------------------

  $('btn-magic-link').addEventListener('click', async () => {
    const email = $('login-email').value.trim();
    if (!email) {
      setStatus('Enter your email first, then click the magic-link button.', 'error');
      return;
    }
    setStatus('Sending magic link…');
    try {
      await persistBrand();
      await invoke('request_magic_link', { args: { server_url: activeServerUrl(), email } });
      setStatus(
        `Sent. Check ${email} for a sign-in link — clicking it will sign you in here.`,
        'success',
      );
    } catch (e) {
      setStatus(prettyError(e), 'error');
    }
  });

  // ----- Registration ------------------------------------------------------

  $('btn-register').addEventListener('click', async () => {
    const args = {
      server_url: activeServerUrl(),
      email: $('reg-email').value.trim(),
      first_name: $('reg-first').value.trim(),
      last_name: $('reg-last').value.trim(),
      password: $('reg-password').value,
    };
    const inv = loadPendingInvitation();
    if (inv && inv.invitation_id) args.invitation_id = inv.invitation_id;
    if (!args.email || !args.first_name || !args.last_name || !args.password) {
      setStatus('All registration fields are required.', 'error');
      return;
    }
    setStatus('Creating account…');
    try {
      const resp = await invoke('register_account', { args });
      if (resp.token) {
        await persistBrand();
        await acceptPendingInvitation();
        setStatus('Account created. Welcome!', 'success');
        finish(resp);
        return;
      }
      if (await finishFromMagicLink(resp, resp.message || 'Invitation accepted.')) {
        return;
      }
      if (resp.added_to_company || resp.reactivated) {
        clearPendingInvitation();
        showPane('login');
        setStatus(resp.message || 'Invitation accepted. Sign in to continue.', 'success');
        return;
      }
      setStatus('Registration completed but no token returned. Try signing in.', 'info');
    } catch (e) {
      setStatus(prettyError(e), 'error');
    }
  });

  // ----- Helpers -----------------------------------------------------------

  async function persistBrand() {
    if (!currentBrand) return;
    const settings = await invoke('get_settings');
    settings.service_brand = currentBrand.slug;
    settings.server_url = activeServerUrl();
    settings.web_url = activeWebUrl();
    await invoke('save_settings', { settings });
  }

  function finish(context) {
    hideAuthTouchKeyboard();
    if (typeof onAuthenticatedCb === 'function') onAuthenticatedCb(context || null);
  }

  function prettyError(e) {
    if (!e) return 'Unknown error';
    if (typeof e === 'string') return e;
    if (e.error) return e.error;
    if (e.message) return e.message;
    try { return JSON.stringify(e); } catch (_) { return String(e); }
  }

  // ----- Local mode (localhost:7437 detection + one-click installer) ----

  const LOCAL_POLL_MS = 4000;
  let localPollTimer = null;
  let localInstallActive = false;
  let localInstallUnlisten = null;
  let hardwareCache = null;

  function setLocalStatus(text, cls) {
    const el = $('local-status');
    if (!el) return;
    el.textContent = text || '';
    el.className = 'local-status' + (cls ? ` ${cls}` : '');
  }

  function appendLocalLog(line, kind) {
    const log = $('local-install-log');
    if (!log) return;
    const div = document.createElement('div');
    div.className = `local-log-line${kind ? ` local-log-${kind}` : ''}`;
    div.textContent = line;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  function clearLocalLog() {
    const log = $('local-install-log');
    if (log) log.innerHTML = '';
  }

  function showLocalInstallControls(running) {
    // When running, hide install button + show "Connect" CTA (the
    // login pane handles credentials once they hit Sign in / Magic
    // link). When not running, swap to the installer.
    $('local-install-row').hidden = running;
    $('local-connect-row').hidden = !running;
  }

  async function refreshLocalStatus() {
    setLocalStatus('Checking localhost:7437…');
    let status;
    try {
      status = await invoke('check_local_agixt');
    } catch (e) {
      setLocalStatus(`Probe failed: ${prettyError(e)}`, 'error');
      showLocalInstallControls(false);
      return;
    }
    if (status.running) {
      const v = status.version ? ` (v${status.version})` : '';
      setLocalStatus(`AGiXT is running on localhost:7437${v}.`, 'ok');
      showLocalInstallControls(true);
    } else {
      const detail = status.detail ? ` (${status.detail})` : '';
      setLocalStatus(`Nothing is running on localhost:7437${detail}.`, 'warn');
      showLocalInstallControls(false);
      // Pre-load hardware info on first detection so the install
      // dialog can show the recommended model immediately.
      if (!hardwareCache) {
        try {
          hardwareCache = await invoke('detect_hardware');
          renderHardwareSummary(hardwareCache);
        } catch (e) {
          console.warn('hardware probe failed', e);
        }
      }
    }
    schedulePoll();
  }

  function schedulePoll() {
    stopLocalStatusPoll();
    if (currentBrand && currentBrand.slug === 'local' && !localInstallActive) {
      localPollTimer = setTimeout(refreshLocalStatus, LOCAL_POLL_MS);
    }
  }

  function stopLocalStatusPoll() {
    if (localPollTimer) {
      clearTimeout(localPollTimer);
      localPollTimer = null;
    }
  }

  function fmtMib(mib) {
    if (!mib) return '—';
    if (mib >= 1024) return `${(mib / 1024).toFixed(1)} GiB`;
    return `${mib} MiB`;
  }

  function renderHardwareSummary(hw) {
    const wrap = $('local-hw-summary');
    if (!wrap) return;
    const gpus = (hw.gpus || []).map((g) => {
      const v = g.vram_mib ? fmtMib(g.vram_mib) : 'unknown VRAM';
      return `${g.name} — ${v}`;
    });
    const gpuLine = gpus.length ? gpus.join('; ') : 'No NVIDIA GPU detected';
    wrap.innerHTML = '';
    const lines = [
      ['CPU cores', String(hw.cpu_cores || '—')],
      ['RAM', `${fmtMib(hw.total_ram_mib)} total · ${fmtMib(hw.available_ram_mib)} available`],
      ['GPU', gpuLine],
      ['Recommended model', hw.recommended_model || '—'],
      ['Max tokens', hw.recommended_max_tokens ? String(hw.recommended_max_tokens) : '—'],
    ];
    for (const [label, value] of lines) {
      const row = document.createElement('div');
      row.className = 'local-hw-row';
      const k = document.createElement('span');
      k.className = 'local-hw-label';
      k.textContent = label;
      const v = document.createElement('span');
      v.className = 'local-hw-value';
      v.textContent = value;
      row.appendChild(k);
      row.appendChild(v);
      wrap.appendChild(row);
    }
    if (hw.recommendation_note) {
      const note = document.createElement('div');
      note.className = 'local-hw-note';
      note.textContent = hw.recommendation_note;
      wrap.appendChild(note);
    }
    // Sudo field is Linux-only — that's where AGiXT/ezLocalai shell
    // out to apt for Docker + the NVIDIA Container Toolkit.
    const sudoField = $('local-sudo-field');
    if (sudoField) sudoField.hidden = hw.os !== 'linux';
  }

  async function startLocalInstall() {
    if (localInstallActive) return;
    localInstallActive = true;
    stopLocalStatusPoll();
    clearLocalLog();
    $('local-install-progress').hidden = false;
    $('btn-local-install').disabled = true;
    setLocalStatus('Installing AGiXT locally…', 'info');

    // Subscribe to progress events *before* invoking so we don't miss
    // early lines emitted during preflight.
    try {
      const evt = window.__TAURI__.event;
      localInstallUnlisten = await evt.listen('local-install-progress', (msg) => {
        const p = msg.payload || {};
        if (p.kind === 'phase') {
          appendLocalLog(`▶ ${p.message}`, 'phase');
        } else if (p.kind === 'log') {
          appendLocalLog(p.line, p.stream && p.stream.endsWith('stderr') ? 'stderr' : 'stdout');
        } else if (p.kind === 'ok') {
          appendLocalLog(`✓ ${p.message}`, 'ok');
        } else if (p.kind === 'err') {
          appendLocalLog(`✗ ${p.message}`, 'err');
        }
      });
    } catch (e) {
      console.warn('listen failed', e);
    }

    let installPath = '';
    try {
      installPath = await invoke('default_install_path');
    } catch (_) { /* fall through with empty path; Rust will default */ }
    const pathInput = $('local-install-path');
    if (pathInput && pathInput.value.trim()) {
      installPath = pathInput.value.trim();
    } else if (pathInput) {
      pathInput.value = installPath;
    }

    // On Linux, AGiXT/ezLocalai may need to install Docker or the
    // NVIDIA Container Toolkit, which means sudo. Remember validated sudo
    // credentials first via the existing sudo_auth helper if the user provided
    // a password. If they leave it blank, proceed anyway — the install will
    // surface the missing-sudo failure in the log.
    if (hardwareCache && hardwareCache.os === 'linux') {
      const pwField = $('local-sudo-password');
      const pw = pwField ? pwField.value : '';
      if (pw) {
        try {
          await invoke('sudo_auth', { password: pw });
          appendLocalLog('▶ Sudo password remembered (Docker / toolkit installs covered).', 'phase');
        } catch (e) {
          appendLocalLog(`✗ sudo authentication failed: ${prettyError(e)}`, 'err');
        }
        if (pwField) pwField.value = '';
      }
    }

    const installArgs = {
      install_path: installPath,
      default_model: hardwareCache && hardwareCache.recommended_model
        ? hardwareCache.recommended_model
        : null,
      default_max_tokens: hardwareCache && hardwareCache.recommended_max_tokens
        ? hardwareCache.recommended_max_tokens
        : null,
    };
    let result;
    try {
      result = await invoke('install_agixt_local', { args: installArgs });
    } catch (e) {
      setLocalStatus(`Install failed: ${prettyError(e)}`, 'error');
      $('btn-local-install').disabled = false;
      localInstallActive = false;
      if (localInstallUnlisten) { try { localInstallUnlisten(); } catch (_) {} localInstallUnlisten = null; }
      schedulePoll();
      return;
    }
    if (localInstallUnlisten) { try { localInstallUnlisten(); } catch (_) {} localInstallUnlisten = null; }
    localInstallActive = false;
    if (result && result.success) {
      setLocalStatus(result.message || 'AGiXT is now running.', 'ok');
      showLocalInstallControls(true);
    } else {
      $('btn-local-install').disabled = false;
    }
    schedulePoll();
  }

  // Wire local-mode buttons. These elements are present in index.html
  // even when local mode isn't active (the pane is just `hidden`),
  // so binding once on boot is fine.
  function bindLocalControls() {
    const btnInstall = $('btn-local-install');
    if (btnInstall) btnInstall.addEventListener('click', startLocalInstall);
    const btnRefresh = $('btn-local-refresh');
    if (btnRefresh) btnRefresh.addEventListener('click', refreshLocalStatus);
  }

  function bindInvitationControls() {
    const dismiss = $('auth-invite-dismiss');
    if (dismiss) {
      dismiss.addEventListener('click', () => {
        clearPendingInvitation();
        setStatus('Invitation dismissed. You can still sign in normally.', 'info');
      });
    }
    const accept = $('auth-invite-accept');
    if (accept) accept.addEventListener('click', clickAcceptInvitation);
    const decline = $('auth-invite-decline');
    if (decline) decline.addEventListener('click', clickDeclineInvitation);
    // Live wrong-email warning: when the user types something different
    // from the invitation's intended recipient, surface it next to the
    // banner so we don't waste a roundtrip on a registration that won't
    // accept the pending invitation.
    ['login-email', 'reg-email'].forEach((id) => {
      const f = $(id);
      if (f) f.addEventListener('input', refreshInvitationEmailWarning);
    });
  }

  async function boot({ onAuthenticated } = {}) {
    onAuthenticatedCb = onAuthenticated;
    bindAuthFocusGuard();
    bindAuthTouchKeyboard();
    bindLocalControls();
    bindInvitationControls();
    bindInvitationListener();
    await loadBrands();
    syncAuthTouchKeyboardAvailability();
    loadPendingInvitation();
    if (typeof window !== 'undefined' && window.location) {
      if (setPendingInvitation(window.location.href)) consumeInvitationUrl('/user/register');
    }
    applyPendingInvitationToUi();
    if (loadPendingInvitation()) {
      clickAcceptInvitation();
    } else {
      showPane('login');
    }
    refreshOAuthProviders().catch((e) => {
      console.debug('oauth provider refresh failed after auth boot', e);
    });
  }

  window.AgixtAuth = {
    boot,
    refreshOAuthProviders,
    setPendingInvitation,
    hasInvitationInLocation,
    consumeInvitationUrl,
    hasPendingInvitation: () => Boolean(loadPendingInvitation()),
    acceptPendingInvitation,
    clearPendingInvitation,
  };
})();

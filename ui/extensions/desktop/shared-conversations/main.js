(function () {
  const EXT_ID = 'shared-conversations';
  const PENDING_KEY = 'agixt.desktop.pendingSharedConversationToken.v1';

  function setPendingToken(token) {
    const clean = String(token || '').trim();
    if (!clean) return;
    try { window.localStorage.setItem(PENDING_KEY, clean); } catch (_) {}
  }

  function takePendingToken() {
    try {
      const token = window.localStorage.getItem(PENDING_KEY) || '';
      window.localStorage.removeItem(PENDING_KEY);
      return token;
    } catch (_) {
      return '';
    }
  }

  window.AgixtRegisterExtension(EXT_ID, {
    mount(container, ctx) {
      const view = new SharedConversationsView(container, ctx);
      container._sharedConversationsView = view;
      view.start();
    },
    unmount() {
      const root = document.querySelector('.chat-screen-main .view-pane[data-view="' + EXT_ID + '"]');
      if (root && root._sharedConversationsView) {
        root._sharedConversationsView.stop();
        root._sharedConversationsView = null;
      }
    },
  });

  function SharedConversationsView(container, ctx) {
    this.container = container;
    this.ctx = ctx;
    this.tokenInput = '';
    this.activeToken = '';
    this.conversation = null;
    this.sharedWithMe = [];
    this.workspace = { open: false, path: '/', loading: false, error: null, items: [] };
    this.loading = false;
    this.error = null;
    this._externalOpenHandler = null;
  }

  SharedConversationsView.prototype.start = function () {
    injectStyles();
    this.render();
    this.loadSharedWithMe();
    this.bindExternalOpen();
    const pending = takePendingToken();
    if (pending) this.openExternalToken(pending);
  };

  SharedConversationsView.prototype.stop = function () {
    if (this._externalOpenHandler) {
      window.removeEventListener('agixt-shared-conversation-open', this._externalOpenHandler);
      this._externalOpenHandler = null;
    }
    if (window.AgixtSharedConversations && window.AgixtSharedConversations._view === this) {
      window.AgixtSharedConversations = null;
    }
    this.container.innerHTML = '';
  };

  SharedConversationsView.prototype.url = function (path) {
    return new URL(path, this.ctx.serverUrl).toString();
  };

  SharedConversationsView.prototype.fetchJson = async function (path, opts) {
    opts = opts || {};
    if (!opts.public && this.ctx && typeof this.ctx.fetchJson === 'function') {
      return this.ctx.fetchJson(path, opts);
    }
    if (!opts.public && window.AgixtSession && typeof window.AgixtSession.request === 'function') {
      return window.AgixtSession.request(path, opts);
    }
    const init = {
      method: opts.method || 'GET',
      headers: Object.assign(
        opts.public ? {} : { Authorization: 'Bearer ' + this.ctx.jwt },
        opts.json != null ? { 'Content-Type': 'application/json' } : {},
      ),
    };
    if (opts.json != null) init.body = JSON.stringify(opts.json);
    const resp = await fetch(this.url(path), init);
    const text = await resp.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (_) {}
    if (!resp.ok) {
      const err = new Error((data && (data.detail || data.message)) || ('HTTP ' + resp.status));
      err.status = resp.status;
      throw err;
    }
    return data;
  };

  SharedConversationsView.prototype.loadSharedWithMe = async function () {
    try {
      const data = await this.fetchJson('/v1/conversations/shared');
      this.sharedWithMe = (data && data.shared_conversations) || [];
      this.renderSharedList();
    } catch (err) {
      this.sharedWithMe = [];
      this.renderSharedList(err);
    }
  };

  SharedConversationsView.prototype.extractToken = function (value) {
    const raw = String(value || '').trim();
    if (!raw) return '';
    try {
      const parsed = new URL(raw);
      const parts = parsed.pathname.split('/').filter(Boolean);
      const idx = parts.indexOf('shared');
      if (idx >= 0 && parts[idx + 1]) return parts[idx + 1];
    } catch (_) {}
    return raw.replace(/^shared\//, '').replace(/^\/shared\//, '');
  };

  SharedConversationsView.prototype.bindExternalOpen = function () {
    if (this._externalOpenHandler) return;
    this._externalOpenHandler = (ev) => {
      const detail = ev && ev.detail ? ev.detail : {};
      this.openExternalToken(detail.token || detail.url || detail);
    };
    window.addEventListener('agixt-shared-conversation-open', this._externalOpenHandler);
    window.AgixtSharedConversations = {
      _view: this,
      openToken: (token) => this.openExternalToken(token),
      setPendingToken,
    };
  };

  SharedConversationsView.prototype.openExternalToken = function (value) {
    const token = this.extractToken(value);
    if (!token) return;
    this.tokenInput = token;
    this.render();
    this.openToken(token);
  };

  SharedConversationsView.prototype.openToken = async function (tokenValue) {
    const token = this.extractToken(tokenValue || this.tokenInput);
    if (!token) {
      this.error = new Error('Paste a shared conversation link or token first.');
      this.renderConversation();
      return;
    }
    this.loading = true;
    this.error = null;
    this.activeToken = token;
    this.conversation = null;
    this.workspace = { open: false, path: '/', loading: false, error: null, items: [] };
    this.renderConversation();
    try {
      this.conversation = await this.fetchJson('/v1/shared/' + encodeURIComponent(token), { public: true });
    } catch (err) {
      this.error = err;
    } finally {
      this.loading = false;
      this.renderConversation();
    }
  };

  SharedConversationsView.prototype.importActive = async function () {
    if (!this.activeToken) return;
    try {
      const result = await this.fetchJson('/v1/conversation/import-shared/' + encodeURIComponent(this.activeToken), { method: 'POST', json: {} });
      toast('Conversation imported.');
      const id = result && result.id;
      if (id && window.AgixtApp && typeof window.AgixtApp.activateConversation === 'function') {
        await window.AgixtApp.activateConversation({ id: id, name: 'Imported shared conversation' });
      }
      if (window.AgixtSidenav && typeof window.AgixtSidenav.setActiveView === 'function') {
        window.AgixtSidenav.setActiveView('chat');
      }
    } catch (err) {
      toast(errMsg(err), 'error');
    }
  };

  SharedConversationsView.prototype.exportActive = function () {
    if (!this.conversation) return;
    const name = this.conversation.conversation_name || 'shared_conversation';
    downloadJson(safeFileName(name) + '_shared.json', {
      name: name,
      shared_by: this.conversation.shared_by,
      created_at: this.conversation.created_at,
      include_workspace: !!this.conversation.include_workspace,
      messages: this.conversation.conversation_history || [],
    });
    toast('Exported shared conversation.');
  };

  SharedConversationsView.prototype.toggleWorkspace = async function () {
    if (!this.activeToken) return;
    this.workspace.open = !this.workspace.open;
    if (this.workspace.open) await this.loadWorkspace('/');
    else this.renderConversation();
  };

  SharedConversationsView.prototype.loadWorkspace = async function (path) {
    if (!this.activeToken) return;
    this.workspace = Object.assign({}, this.workspace, { open: true, path: path || '/', loading: true, error: null });
    this.renderWorkspace();
    const qs = new URLSearchParams();
    if (path && path !== '/') qs.set('path', path);
    qs.set('recursive', 'false');
    try {
      const data = await this.fetchJson('/v1/shared/' + encodeURIComponent(this.activeToken) + '/workspace?' + qs.toString(), { public: true });
      this.workspace.items = normalizeWorkspaceItems(data);
    } catch (err) {
      this.workspace.items = [];
      this.workspace.error = err;
    } finally {
      this.workspace.loading = false;
      this.renderWorkspace();
    }
  };

  SharedConversationsView.prototype.downloadWorkspaceFile = async function (item) {
    if (!item || item.type !== 'file' || !this.activeToken) return;
    const params = new URLSearchParams({ path: item.path });
    const resp = await fetch(this.url('/v1/shared/' + encodeURIComponent(this.activeToken) + '/workspace/download?' + params.toString()));
    if (!resp.ok) {
      toast('Failed to download file: HTTP ' + resp.status, 'error');
      return;
    }
    const blob = await resp.blob();
    const disposition = resp.headers.get('content-disposition') || '';
    const match = /filename="?([^";]+)"?/i.exec(disposition);
    const filename = match ? match[1] : (item.name || 'download');
    downloadBlob(filename, blob);
  };

  SharedConversationsView.prototype.render = function () {
    this.container.innerHTML = [
      '<section class="scv-shell">',
      '  <header class="scv-head">',
      '    <div><h1>Shared Conversations</h1><p>Open shared links, import them into this account, export transcripts, and browse shared workspace files.</p></div>',
      '    <button class="scv-btn" data-action="refresh">Refresh</button>',
      '  </header>',
      '  <section class="scv-open">',
      '    <input class="scv-input" data-role="token" placeholder="Paste /shared/{token} link or token" value="' + esc(this.tokenInput) + '">',
      '    <button class="scv-primary" data-action="open">Open</button>',
      '  </section>',
      '  <section class="scv-grid">',
      '    <div class="scv-panel"><div class="scv-panel-head"><h2>Shared With Me</h2></div><div data-role="shared-list"></div></div>',
      '    <div class="scv-panel scv-conversation"><div data-role="conversation"></div></div>',
      '  </section>',
      '</section>',
    ].join('');
    this.container.querySelector('[data-action="refresh"]').addEventListener('click', () => this.loadSharedWithMe());
    this.container.querySelector('[data-action="open"]').addEventListener('click', () => this.openToken());
    this.container.querySelector('[data-role="token"]').addEventListener('input', (e) => { this.tokenInput = e.target.value; });
    this.container.querySelector('[data-role="token"]').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this.openToken();
    });
    this.renderSharedList();
    this.renderConversation();
  };

  SharedConversationsView.prototype.renderSharedList = function (error) {
    const target = this.container.querySelector('[data-role="shared-list"]');
    if (!target) return;
    if (error) {
      target.innerHTML = '<div class="scv-empty error">' + esc(errMsg(error)) + '</div>';
      return;
    }
    if (!this.sharedWithMe.length) {
      target.innerHTML = '<div class="scv-empty">No shared conversations found for this account.</div>';
      return;
    }
    target.innerHTML = this.sharedWithMe.map((item, idx) => [
      '<article class="scv-share">',
      '  <div><strong>' + esc(item.conversation_name || item.name || 'Shared conversation') + '</strong>',
      '  <span>Shared by ' + esc(item.shared_by || 'Unknown') + formatDateText(item.created_at) + '</span></div>',
      '  <button class="scv-btn" data-open-index="' + idx + '">Open</button>',
      '</article>',
    ].join('')).join('');
    target.querySelectorAll('[data-open-index]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const item = this.sharedWithMe[Number(btn.dataset.openIndex)];
        this.openToken(item && (item.share_token || item.token));
      });
    });
  };

  SharedConversationsView.prototype.renderConversation = function () {
    const target = this.container.querySelector('[data-role="conversation"]');
    if (!target) return;
    if (this.loading) {
      target.innerHTML = renderOpeningState(this.activeToken);
      return;
    }
    if (this.error) {
      target.innerHTML = renderErrorState(this.error, this.activeToken);
      const retry = target.querySelector('[data-action="retry"]');
      if (retry) retry.addEventListener('click', () => this.openToken(this.activeToken));
      const clear = target.querySelector('[data-action="clear-token"]');
      if (clear) clear.addEventListener('click', () => {
        this.tokenInput = '';
        this.activeToken = '';
        this.error = null;
        this.conversation = null;
        const input = this.container.querySelector('[data-role="token"]');
        if (input) input.value = '';
        this.renderConversation();
      });
      return;
    }
    if (!this.conversation) {
      target.innerHTML = '<div class="scv-empty">Paste a link or open a shared conversation from the list.</div>';
      return;
    }
    const c = this.conversation;
    const messages = (c.conversation_history || []).filter((m) => m && m.message !== '[ACTIVITY] Completed activities.');
    target.innerHTML = [
      '<div class="scv-conv-head">',
      '  <div><h2>' + esc(c.conversation_name || 'Shared conversation') + '</h2>',
      '  <p>Shared by ' + esc(c.shared_by || 'Unknown') + formatDateText(c.created_at) + (c.include_workspace ? ' - Includes workspace files' : '') + '</p></div>',
      '  <div class="scv-actions">',
      c.include_workspace ? '<button class="scv-btn" data-action="workspace">Workspace Files</button>' : '',
      '    <button class="scv-btn" data-action="export">Export</button>',
      '    <button class="scv-primary" data-action="import">Continue</button>',
      '  </div>',
      '</div>',
      '<div class="scv-workspace" data-role="workspace"' + (this.workspace.open ? '' : ' hidden') + '></div>',
      '<div class="scv-messages">',
      messages.map((m) => renderMessage(m)).join(''),
      messages.length ? '' : '<div class="scv-empty">No messages in this shared conversation.</div>',
      '</div>',
    ].join('');
    const workspaceBtn = target.querySelector('[data-action="workspace"]');
    if (workspaceBtn) workspaceBtn.addEventListener('click', () => this.toggleWorkspace());
    target.querySelector('[data-action="export"]').addEventListener('click', () => this.exportActive());
    target.querySelector('[data-action="import"]').addEventListener('click', () => this.importActive());
    this.renderWorkspace();
  };

  SharedConversationsView.prototype.renderWorkspace = function () {
    const target = this.container.querySelector('[data-role="workspace"]');
    if (!target || !this.workspace.open) return;
    if (this.workspace.loading) {
      target.hidden = false;
      target.innerHTML = '<div class="scv-empty">Loading workspace...</div>';
      return;
    }
    const items = this.workspace.items || [];
    target.hidden = false;
    target.innerHTML = [
      '<div class="scv-workspace-head">',
      '  <strong>Workspace: ' + esc(this.workspace.path || '/') + '</strong>',
      '  <div><button class="scv-btn" data-action="up"' + (this.workspace.path === '/' ? ' disabled' : '') + '>Up</button>',
      '  <button class="scv-btn" data-action="close-workspace">Close</button></div>',
      '</div>',
      this.workspace.error ? '<div class="scv-empty error">' + esc(errMsg(this.workspace.error)) + '</div>' : '',
      '<div class="scv-files">',
      items.map((item, idx) => '<button class="scv-file" data-file-index="' + idx + '"><span>' + esc(item.type === 'folder' ? 'Folder' : 'File') + '</span><strong>' + esc(item.name || item.path || '(unnamed)') + '</strong><em>' + esc(item.type === 'folder' ? item.path : formatBytes(item.size)) + '</em></button>').join(''),
      items.length ? '' : '<div class="scv-empty">This workspace folder is empty.</div>',
      '</div>',
    ].join('');
    target.querySelector('[data-action="close-workspace"]').addEventListener('click', () => {
      this.workspace.open = false;
      this.renderConversation();
    });
    target.querySelector('[data-action="up"]').addEventListener('click', () => this.loadWorkspace(parentPath(this.workspace.path)));
    target.querySelectorAll('[data-file-index]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const item = items[Number(btn.dataset.fileIndex)];
        if (!item) return;
        if (item.type === 'folder') this.loadWorkspace(item.path);
        else this.downloadWorkspaceFile(item);
      });
    });
  };

  // Mask a token for display so the full secret doesn't leak into the
  // UI while still letting the user verify the right link is loading.
  function maskToken(t) {
    const s = String(t || '');
    if (!s) return '';
    if (s.length <= 12) return s;
    return s.slice(0, 6) + '…' + s.slice(-4);
  }

  function renderOpeningState(token) {
    const masked = maskToken(token);
    return [
      '<div class="scv-state scv-state-loading" role="status" aria-live="polite">',
      '  <div class="scv-state-icon">',
      '    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">',
      '      <path d="M21 12a9 9 0 1 1-6.219-8.56"/>',
      '    </svg>',
      '  </div>',
      '  <div class="scv-state-body">',
      '    <div class="scv-state-title">Opening shared conversation…</div>',
      '    <div class="scv-state-msg">' + (masked
        ? 'Fetching <code>' + esc(masked) + '</code> from the server.'
        : 'Fetching shared conversation from the server.') + '</div>',
      '  </div>',
      '</div>',
    ].join('');
  }

  // Pick the right copy for each known failure mode. The fetchJson helper
  // attaches an HTTP status code to thrown errors and many of the
  // Public shared messages match well-known patterns, so we surface
  // a friendly state without guessing.
  function classifyShareError(err) {
    const status = err && err.status;
    const raw = err && (err.detail || err.message || err.error || '');
    const msg = String(raw || '').toLowerCase();
    if (status === 404 || msg.includes('not found')) {
      return { kind: 'not-found', title: 'Shared conversation not found',
        body: 'This link may have been deleted, or the token is incorrect. Double-check the link with whoever shared it.' };
    }
    if (status === 410 || msg.includes('expired') || msg.includes('gone')) {
      return { kind: 'expired', title: 'This shared link has expired',
        body: 'The owner set an expiration date that has passed. Ask them to share it again to restore access.' };
    }
    if (status === 403 || msg.includes('revoked') || msg.includes('disabled') || msg.includes('access denied')) {
      return { kind: 'revoked', title: 'Sharing has been turned off',
        body: 'The owner revoked this link. Ask them to share it again or send the conversation a different way.' };
    }
    if (status === 401 || msg.includes('unauthorized')) {
      return { kind: 'unauthorized', title: 'Sign-in required',
        body: 'This share requires you to be signed in. Sign in to your AGiXT account and try opening the link again.' };
    }
    if (status === 400 || msg.includes('invalid')) {
      return { kind: 'invalid', title: 'That doesn’t look like a valid shared link',
        body: 'Make sure you pasted the entire <code>/shared/...</code> URL or the share token. Spaces and stray punctuation can break the token.' };
    }
    if (status >= 500) {
      return { kind: 'server', title: 'Server error while opening this link',
        body: 'Something went wrong on the server. Try again in a moment.' };
    }
    return { kind: 'unknown', title: 'Couldn’t open this shared conversation',
      body: raw ? String(raw) : 'An unknown error occurred. Try again or paste the link.' };
  }

  function renderErrorState(err, token) {
    const c = classifyShareError(err);
    const masked = maskToken(token);
    return [
      '<div class="scv-state scv-state-error scv-state-' + esc(c.kind) + '" role="alert">',
      '  <div class="scv-state-icon">',
      '    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">',
      (c.kind === 'expired' || c.kind === 'revoked'
        ? '      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>'
        : c.kind === 'not-found' || c.kind === 'invalid'
        ? '      <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>'
        : c.kind === 'unauthorized'
        ? '      <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>'
        : '      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>'),
      '    </svg>',
      '  </div>',
      '  <div class="scv-state-body">',
      '    <div class="scv-state-title">' + esc(c.title) + '</div>',
      '    <div class="scv-state-msg">' + c.body + '</div>',
      masked ? '    <div class="scv-state-meta">Token: <code>' + esc(masked) + '</code></div>' : '',
      '    <div class="scv-state-actions">',
      (c.kind === 'not-found' || c.kind === 'invalid' || c.kind === 'expired' || c.kind === 'revoked')
        ? '      <button class="scv-btn" data-action="clear-token">Try a different link</button>'
        : '      <button class="scv-btn" data-action="retry">Try again</button><button class="scv-btn" data-action="clear-token">Use a different link</button>',
      '    </div>',
      '  </div>',
      '</div>',
    ].join('');
  }

  function renderMessage(msg) {
    const role = String(msg.role || 'assistant');
    const body = msg.message == null ? '' : String(msg.message);
    const children = Array.isArray(msg.children) ? msg.children : [];
    const rendered = window.AgixtMarkdown && typeof window.AgixtMarkdown.renderFragment === 'function'
      ? fragmentHtml(window.AgixtMarkdown.renderFragment(body))
      : '<pre>' + esc(body) + '</pre>';
    return [
      '<article class="scv-message ' + esc(role.toLowerCase()) + '">',
      '  <div class="scv-role">' + esc(role) + '</div>',
      '  <div class="scv-body">' + rendered + '</div>',
      children.length ? '<details class="scv-children"><summary>' + children.length + ' activit' + (children.length === 1 ? 'y' : 'ies') + '</summary>' + children.map((child) => renderMessage(child)).join('') + '</details>' : '',
      '</article>',
    ].join('');
  }

  function fragmentHtml(fragment) {
    const wrapper = document.createElement('div');
    wrapper.appendChild(fragment.cloneNode(true));
    return wrapper.innerHTML;
  }

  function normalizeWorkspaceItems(data) {
    const raw = data && (data.items || data.children || data.files || []);
    return Array.isArray(raw) ? raw.map((item) => ({
      name: item.name || String(item.path || '').split('/').filter(Boolean).pop() || '',
      path: item.path || item.name || '',
      type: item.type || (item.is_dir || item.directory ? 'folder' : 'file'),
      size: item.size || item.bytes || 0,
    })) : [];
  }

  function parentPath(path) {
    const parts = String(path || '/').split('/').filter(Boolean);
    parts.pop();
    return parts.length ? '/' + parts.join('/') : '/';
  }

  function downloadJson(filename, data) {
    downloadBlob(filename, new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
  }

  function downloadBlob(filename, blob) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function safeFileName(name) {
    return String(name || 'conversation').replace(/[^a-z0-9._-]+/gi, '_').replace(/^_+|_+$/g, '') || 'conversation';
  }

  function formatDateText(value) {
    if (!value) return '';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return '';
    return ' - ' + d.toLocaleDateString();
  }

  function formatBytes(value) {
    const n = Number(value || 0);
    if (!n) return '0 bytes';
    if (n < 1024) return n + ' bytes';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    return (n / 1024 / 1024).toFixed(1) + ' MB';
  }

  function toast(message, kind) {
    if (window.AgixtToast && typeof window.AgixtToast.show === 'function') {
      window.AgixtToast.show(message, kind || 'success');
      return;
    }
    console[kind === 'error' ? 'warn' : 'log'](message);
  }

  function errMsg(err) {
    if (!err) return 'Unknown error';
    if (typeof err === 'string') return err;
    return err.detail || err.message || err.error || String(err);
  }

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (ch) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#039;',
    }[ch]));
  }

  function injectStyles() {
    if (document.getElementById('shared-conversations-styles')) return;
    const style = document.createElement('style');
    style.id = 'shared-conversations-styles';
    style.textContent = `
      .scv-shell {
        height: 100%; display: flex; flex-direction: column; min-height: 0;
        background: var(--bg); color: var(--text);
      }
      .scv-head {
        display: flex; align-items: flex-start; justify-content: space-between; gap: 16px;
        padding: 20px 24px;
        border-bottom: 1px solid var(--border);
        background: var(--panel);
      }
      .scv-head > div { min-width: 0; }
      .scv-head h1 { margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -0.01em; }
      .scv-head p {
        margin: 6px 0 0; color: var(--text-faint);
        font-size: 13px; line-height: 1.5; max-width: 540px;
      }
      .scv-conv-head h2, .scv-panel-head h2 {
        margin: 0; font-size: 14px; font-weight: 700;
        text-transform: uppercase; letter-spacing: 0.06em;
        color: var(--text-faint);
      }
      .scv-conv-head p { margin: 6px 0 0; color: var(--text-dim); font-size: 12.5px; }

      .scv-open {
        display: flex; gap: 10px; padding: 14px 24px;
        border-bottom: 1px solid var(--border);
        background: var(--panel-2);
      }
      .scv-input {
        flex: 1; min-width: 0;
        border: 1px solid var(--border);
        background: var(--panel); color: var(--text);
        border-radius: 8px; padding: 10px 12px;
        font: inherit; font-size: 13px;
        transition: border-color 0.14s, box-shadow 0.14s;
      }
      .scv-input:focus {
        outline: none; border-color: var(--accent);
        box-shadow: 0 0 0 3px rgba(107, 123, 255, 0.18);
      }

      .scv-grid {
        flex: 1; min-height: 0;
        display: grid;
        grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
        gap: 16px; padding: 16px 24px 24px;
      }
      .scv-panel {
        min-height: 0; overflow: auto;
        border: 1px solid var(--border);
        border-radius: 12px;
        background: var(--panel);
        box-shadow: 0 1px 0 rgba(255, 255, 255, 0.02), 0 4px 18px rgba(0, 0, 0, 0.18);
      }
      .scv-panel-head {
        padding: 14px 16px;
        border-bottom: 1px solid var(--border);
        background: var(--panel-2);
      }

      .scv-share {
        display: flex; align-items: center; justify-content: space-between;
        gap: 10px; padding: 12px 14px;
        border-bottom: 1px solid var(--border-muted);
        cursor: pointer;
        transition: background 0.10s;
      }
      .scv-share:hover { background: var(--panel-hover); }
      .scv-share:last-child { border-bottom: 0; }
      .scv-share > div { min-width: 0; flex: 1; }
      .scv-share strong {
        display: block; font-size: 13.5px; font-weight: 600; color: var(--text);
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
      }
      .scv-share span {
        display: block; color: var(--text-faint);
        font-size: 11.5px; margin-top: 4px;
      }

      .scv-btn, .scv-primary {
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 8px 14px;
        font: inherit; font-size: 12.5px; font-weight: 600;
        color: var(--text); background: var(--panel-2);
        cursor: pointer;
        transition: background 0.14s, border-color 0.14s, color 0.14s, transform 0.08s, box-shadow 0.14s;
        display: inline-flex; align-items: center; gap: 6px;
        white-space: nowrap;
      }
      .scv-btn:hover { background: var(--panel-hover); }
      .scv-btn:active, .scv-primary:active { transform: translateY(0.5px); }
      .scv-primary {
        border-color: var(--accent);
        color: #fff; background: var(--accent);
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.25), 0 1px 0 rgba(255,255,255,0.08) inset;
      }
      .scv-primary:hover {
        filter: brightness(1.08);
        box-shadow: 0 2px 6px rgba(107, 123, 255, 0.32), 0 1px 0 rgba(255,255,255,0.12) inset;
      }
      .scv-btn:disabled, .scv-primary:disabled { opacity: 0.45; cursor: default; transform: none; }

      .scv-empty {
        padding: 36px 20px; text-align: center;
        color: var(--text-faint); font-size: 13px;
        line-height: 1.5;
      }
      .scv-empty.error {
        color: #ff8a96;
        background: rgba(220, 60, 80, 0.10);
        border: 1px solid rgba(220, 60, 80, 0.3);
        border-radius: 10px;
        margin: 14px;
        padding: 16px;
      }

      /* Distinct loading + error states surfaced inside the conversation
         panel. Each card has an icon + title + message + optional action
         row. Color tints the icon and border for the specific failure
         mode (not-found/expired/revoked/invalid/unauthorized/server). */
      .scv-state {
        display: flex; gap: 14px; align-items: flex-start;
        margin: 14px;
        padding: 16px 18px;
        border-radius: 12px;
        background: var(--panel-2);
        border: 1px solid var(--border);
      }
      .scv-state-icon {
        flex: 0 0 auto;
        display: inline-flex; align-items: center; justify-content: center;
        width: 36px; height: 36px;
        border-radius: 10px;
        background: var(--panel);
        color: var(--text-dim);
      }
      .scv-state-body { flex: 1; min-width: 0; }
      .scv-state-title {
        font-size: 13.5px; font-weight: 700;
        color: var(--text); margin-bottom: 4px;
      }
      .scv-state-msg {
        font-size: 12.5px; color: var(--text-dim);
        line-height: 1.55;
      }
      .scv-state-msg code,
      .scv-state-meta code {
        font-family: var(--mono); font-size: 11px;
        background: var(--panel); color: var(--text);
        padding: 1px 6px; border-radius: 4px;
        border: 1px solid var(--border);
      }
      .scv-state-meta {
        margin-top: 6px;
        font-size: 11px; color: var(--text-faint);
      }
      .scv-state-actions {
        display: flex; gap: 6px; flex-wrap: wrap;
        margin-top: 10px;
      }

      /* Loading — accent tinted, with a spinning arc icon. */
      .scv-state-loading {
        border-color: color-mix(in srgb, var(--accent) 30%, var(--border));
        background: color-mix(in srgb, var(--accent) 5%, var(--panel-2));
      }
      .scv-state-loading .scv-state-icon {
        color: var(--accent);
        background: color-mix(in srgb, var(--accent) 18%, var(--panel));
        animation: scv-spin 1.2s linear infinite;
      }
      @keyframes scv-spin { to { transform: rotate(360deg); } }
      @media (prefers-reduced-motion: reduce) {
        .scv-state-loading .scv-state-icon { animation: none; }
      }

      /* Error variants — color the icon block per failure mode. */
      .scv-state-error.scv-state-not-found .scv-state-icon,
      .scv-state-error.scv-state-invalid .scv-state-icon {
        color: #ffb774;
        background: color-mix(in srgb, #ffb774 22%, var(--panel));
      }
      .scv-state-error.scv-state-not-found,
      .scv-state-error.scv-state-invalid {
        border-color: color-mix(in srgb, #ffb774 30%, var(--border));
      }
      .scv-state-error.scv-state-expired .scv-state-icon,
      .scv-state-error.scv-state-revoked .scv-state-icon {
        color: #ff8a96;
        background: color-mix(in srgb, #ff8a96 22%, var(--panel));
      }
      .scv-state-error.scv-state-expired,
      .scv-state-error.scv-state-revoked {
        border-color: color-mix(in srgb, #ff8a96 30%, var(--border));
      }
      .scv-state-error.scv-state-unauthorized .scv-state-icon {
        color: var(--accent);
        background: color-mix(in srgb, var(--accent) 18%, var(--panel));
      }
      .scv-state-error.scv-state-unauthorized {
        border-color: color-mix(in srgb, var(--accent) 30%, var(--border));
      }
      .scv-state-error.scv-state-server .scv-state-icon,
      .scv-state-error.scv-state-unknown .scv-state-icon {
        color: #ff8a96;
        background: color-mix(in srgb, #ff8a96 22%, var(--panel));
      }

      .scv-conv-head {
        display: flex; align-items: flex-start; justify-content: space-between;
        gap: 16px; padding: 18px 20px;
        border-bottom: 1px solid var(--border);
        background: var(--panel-2);
      }
      .scv-conv-head > div { min-width: 0; flex: 1; }
      .scv-conv-head h2 {
        font-size: 18px; font-weight: 700;
        text-transform: none; letter-spacing: -0.01em;
        color: var(--text);
      }
      .scv-actions {
        display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px;
      }

      .scv-messages {
        padding: 16px; display: flex; flex-direction: column; gap: 12px;
      }
      .scv-message {
        border: 1px solid var(--border-muted);
        border-radius: 10px;
        background: var(--panel-2);
        padding: 12px 14px;
        transition: border-color 0.12s;
      }
      .scv-message:hover { border-color: var(--border); }
      .scv-message.user {
        background: var(--accent-soft);
        border-color: rgba(107, 123, 255, 0.35);
      }
      .scv-role {
        color: var(--text-faint); font-size: 10.5px; font-weight: 700;
        text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 8px;
      }
      .scv-message.user .scv-role { color: var(--accent); }
      .scv-body { font-size: 13px; line-height: 1.55; overflow-wrap: anywhere; }
      .scv-body pre { white-space: pre-wrap; margin: 0; font-family: var(--font); }
      .scv-body code {
        background: var(--code-bg); padding: 1px 6px;
        border-radius: 4px; font-family: var(--mono); font-size: 12px;
      }
      .scv-children {
        margin-top: 10px;
        border-top: 1px solid var(--border-muted);
        padding-top: 8px;
      }
      .scv-children summary {
        cursor: pointer;
        font-size: 11.5px; color: var(--text-faint);
        text-transform: uppercase; letter-spacing: 0.05em;
        padding: 4px 0;
      }
      .scv-children summary:hover { color: var(--text-dim); }

      .scv-workspace {
        margin: 16px; border: 1px solid var(--border);
        border-radius: 10px; background: var(--panel-2);
        overflow: hidden;
      }
      .scv-workspace-head {
        display: flex; align-items: center; justify-content: space-between;
        gap: 10px; padding: 12px 14px;
        border-bottom: 1px solid var(--border);
        background: var(--panel);
      }
      .scv-workspace-head strong {
        font-family: var(--mono); font-size: 12px;
        color: var(--text-dim);
      }
      .scv-workspace-head > div { display: flex; gap: 6px; }
      .scv-files { display: flex; flex-direction: column; }
      .scv-file {
        display: grid;
        grid-template-columns: 70px minmax(0, 1fr) auto;
        gap: 12px; align-items: center;
        border: 0; border-bottom: 1px solid var(--border-muted);
        background: transparent; color: var(--text);
        text-align: left; padding: 11px 14px;
        cursor: pointer;
        font: inherit;
        transition: background 0.10s;
      }
      .scv-file:hover { background: var(--panel-hover); }
      .scv-file:last-child { border-bottom: 0; }
      .scv-file span {
        font-size: 10.5px; font-weight: 600;
        text-transform: uppercase; letter-spacing: 0.05em;
        color: var(--text-faint);
        padding: 2px 8px;
        border: 1px solid var(--border);
        border-radius: 999px;
        background: var(--panel);
        text-align: center;
      }
      .scv-file em {
        color: var(--text-faint); font-size: 11.5px; font-style: normal;
        font-variant-numeric: tabular-nums;
      }
      .scv-file strong {
        min-width: 0; overflow: hidden; text-overflow: ellipsis;
        white-space: nowrap; font-size: 13px;
      }

      @media (max-width: 900px) {
        .scv-grid { grid-template-columns: 1fr; padding: 12px 16px 16px; }
        .scv-head, .scv-open { padding-left: 16px; padding-right: 16px; }
      }

      :root[data-theme="light"] .scv-empty.error { color: #b3293f; }
      :root[data-theme="light"] .scv-children summary:hover { color: var(--text); }
    `;
    document.head.appendChild(style);
  }
})();

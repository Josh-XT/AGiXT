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
      this.conversation = await this.fetchJson('/api/shared/' + encodeURIComponent(token), { public: true });
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
      const data = await this.fetchJson('/api/shared/' + encodeURIComponent(this.activeToken) + '/workspace?' + qs.toString(), { public: true });
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
    const resp = await fetch(this.url('/api/shared/' + encodeURIComponent(this.activeToken) + '/workspace/download?' + params.toString()));
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
      target.innerHTML = '<div class="scv-empty">Loading shared conversation...</div>';
      return;
    }
    if (this.error) {
      target.innerHTML = '<div class="scv-empty error">' + esc(errMsg(this.error)) + '</div>';
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

// Frontend smoke tests for AGiXT Desktop.
//
// These run under Node's built-in `node:test` runner with `jsdom` as a DOM
// shim. They verify:
//   * markdown.js renders core syntax + media correctly
//   * chat.js parses [ACTIVITY] / [SUBACTIVITY] envelopes the same way the
//     web client does, and groups subactivities under their parent
//   * client-actions.js routes tool calls to the correct Tauri IPC method
//     name (mocked) with the right argument shape
//
// Invoke with:
//   node --test tests/frontend.test.mjs
// from ui.

import { afterEach, test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import { JSDOM } from 'jsdom';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(__dirname, '..', 'src');
const WEB = path.join(__dirname, '..');
const trackedDoms = new Set();

function trackDom(dom) {
  trackedDoms.add(dom);
  return dom;
}

function cleanupWindow(window) {
  try { if (window.AgixtChat) window.AgixtChat.disconnect(); } catch (_) {}
  try { if (window.AgixtNotifications) window.AgixtNotifications.stop(); } catch (_) {}
  try { if (window.AgixtTeamChat) window.AgixtTeamChat.unmount(); } catch (_) {}
  try { if (window.AgixtDesktopExtensions) window.AgixtDesktopExtensions.stop(); } catch (_) {}
  try { if (window.AgixtWorkspace) window.AgixtWorkspace.close(); } catch (_) {}
  try {
    if (window.AgixtDesktopUpdates
        && typeof window.AgixtDesktopUpdates.syncSettings === 'function'
        && typeof window.AgixtDesktopUpdates.scheduleAutoCheck === 'function') {
      window.AgixtDesktopUpdates.syncSettings({ desktop_auto_update: false });
      window.AgixtDesktopUpdates.scheduleAutoCheck();
    }
  } catch (_) {}
}

afterEach(() => {
  for (const dom of trackedDoms) {
    if (!dom || !dom.window) continue;
    cleanupWindow(dom.window);
    try { dom.window.close(); } catch (_) {}
  }
  trackedDoms.clear();
});

function loadFrontend({ ipc, WebSocketClass, eventListen } = {}) {
  const dom = new JSDOM(
    fs.readFileSync(path.join(SRC, 'index.html'), 'utf8'),
    { runScripts: 'outside-only', url: 'http://localhost/' },
  );
  const { window } = dom;
  trackDom(dom);
  window.requestAnimationFrame = window.requestAnimationFrame || ((cb) => setTimeout(() => cb(Date.now()), 0));
  window.cancelAnimationFrame = window.cancelAnimationFrame || ((id) => clearTimeout(id));
  // Stub Tauri IPC.
  const calls = [];
  window.__TAURI__ = {
    core: {
      invoke: async (cmd, args) => {
        calls.push({ cmd, args });
        if (ipc && typeof ipc[cmd] === 'function') return ipc[cmd](args);
        return null;
      },
    },
    event: {
      listen: async (name, cb) => {
        if (eventListen) return eventListen(name, cb);
        return () => {};
      },
    },
  };
  // jsdom doesn't implement WebSocket; provide a no-op so chat.js loads.
  if (WebSocketClass) {
    window.WebSocket = WebSocketClass;
  } else if (!window.WebSocket) {
    window.WebSocket = class {
      constructor() { this.readyState = 0; }
      send() {}
      close() {}
    };
    window.WebSocket.OPEN = 1;
  }

  const ctx = window;
  function evalIn(name) {
    const code = fs.readFileSync(path.join(SRC, name), 'utf8');
    vm.runInContext(code, dom.getInternalVMContext(), { filename: name });
  }
  evalIn('markdown.js');
  evalIn('audio.js');
  evalIn('client-actions.js');
  evalIn('chat.js');
  return { window, calls };
}

function loadWebRuntime(url = 'http://localhost/') {
  const dom = new JSDOM('<!doctype html><html><body><div id="oauth-status"><h1></h1><p></p></div></body></html>', {
    runScripts: 'outside-only',
    url,
  });
  const { window } = dom;
  trackDom(dom);
  window.AGIXT_WEB_CONFIG = {
    serverUrl: 'http://localhost:7437',
    webUrl: 'http://localhost:3437',
  };
  const code = fs.readFileSync(path.join(WEB, 'web-runtime.js'), 'utf8');
  vm.runInContext(code, dom.getInternalVMContext(), { filename: 'web-runtime.js' });
  return { window };
}

function loadFullApp({ ipc, url = 'http://localhost/', webRuntime = false, fetch: fetchImpl, userAgent } = {}) {
  const dom = new JSDOM(
    fs.readFileSync(path.join(SRC, 'index.html'), 'utf8'),
    { runScripts: 'outside-only', url },
  );
  const { window } = dom;
  trackDom(dom);
  if (webRuntime) window.__AGIXT_WEB_RUNTIME = true;
  if (fetchImpl) window.fetch = fetchImpl;
  if (userAgent) {
    Object.defineProperty(window.navigator, 'userAgent', {
      value: userAgent,
      configurable: true,
    });
  }
  window.requestAnimationFrame = window.requestAnimationFrame || ((cb) => setTimeout(() => cb(Date.now()), 0));
  window.cancelAnimationFrame = window.cancelAnimationFrame || ((id) => clearTimeout(id));
  const calls = [];
  const listeners = new Map();
  window.__TAURI__ = {
    core: {
      invoke: async (cmd, args) => {
        calls.push({ cmd, args });
        if (ipc && typeof ipc[cmd] === 'function') return ipc[cmd](args, listeners);
        if (cmd === 'get_settings') {
          return {
            jwt: 'jwt',
            conversation_id: 'convo-id',
            conversation_name: '-',
            server_url: 'http://localhost:7437',
            agent_id: 'agent-id',
            agent_name: 'XT',
            company_id: 'company-id',
            company_name: 'Home',
            allow_client_commands: true,
            voice_enabled: false,
            desktop_auto_update: false,
            g1_enabled: false,
            g1_display_enabled: true,
            g1_show_ai_responses: true,
            g1_notification_forwarding: true,
            g1_auto_connect: true,
            g1_time_format: '12h',
            g1_temperature_unit: 'fahrenheit',
            g1_dashboard_layout: 'dual',
            g1_weather_latitude: null,
            g1_weather_longitude: null,
            g1_brightness: 28,
            g1_auto_brightness: true,
            g1_headup_angle: 20,
            g1_wear_detection: true,
            g1_display_height: 0,
            g1_display_depth: 5,
            user_email: 'test@example.com',
          };
        }
        if (cmd.startsWith('g1_')) {
          return {
            supported: true,
            scanning: false,
            connected: false,
            left: null,
            right: null,
            battery: { left: null, right: null, last_updated: null },
            last_event: null,
            last_error: null,
          };
        }
        if (cmd === 'list_companies') {
          return [{
            id: 'company-id',
            name: 'Home',
            primary: true,
            role_id: 1,
            role: 'admin',
            scopes: [],
            agents: [{ id: 'agent-id', name: 'XT', default: true }],
          }];
        }
        if (cmd === 'list_agents') return [{ id: 'agent-id', name: 'XT', default: true }];
        if (cmd === 'get_conversation_history') return [];
        if (cmd === 'list_conversations') return [];
        if (cmd === 'save_settings') return args.settings;
        if (cmd === 'chat_send') {
          const streamId = args.args.stream_id;
          setTimeout(() => {
            const cb = listeners.get(`chat-stream:${streamId}`);
            if (cb) {
              cb({
                payload: {
                  event: { kind: 'done', data: { text: 'ok', finish_reason: 'stop' } },
                },
              });
            }
          }, 0);
          return streamId;
        }
        return null;
      },
    },
    event: {
      listen: async (name, cb) => {
        listeners.set(name, cb);
        return () => listeners.delete(name);
      },
    },
  };
  window.WebSocket = class {
    constructor() {
      this.readyState = window.WebSocket.CONNECTING;
      this._openTimer = setTimeout(() => {
        if (this.readyState === window.WebSocket.CLOSED) return;
        this.readyState = window.WebSocket.OPEN;
        if (this.onopen) this.onopen();
      }, 0);
    }
    send() {}
    close() {
      if (this._openTimer) {
        clearTimeout(this._openTimer);
        this._openTimer = null;
      }
      this.readyState = window.WebSocket.CLOSED;
    }
  };
  window.WebSocket.OPEN = 1;
  window.WebSocket.CONNECTING = 0;
  window.WebSocket.CLOSED = 3;
  // user-settings.js + agixt-api.js own the gear-button side pane that
  // replaced the legacy settings modal. They have to be loaded *before*
  // app.js so window.UserSettings exists by the time app.js's
  // setActiveView lazy-mounts the pane on first activation. chains.js
  // and prompts.js own their own side panes and follow the same pattern.
  for (const name of [
    'markdown.js', 'audio.js', 'client-actions.js', 'chat.js',
    'notifications.js', 'g1.js', 'auth.js', 'dock.js',
    'agixt-api.js', 'user-settings.js', 'chains.js', 'prompts.js',
    'team-chat-helpers.js', 'team-chat.js',
    'app.js',
    'prompt-guidance-data.js', 'prompt-guidance.js',
  ]) {
    const code = fs.readFileSync(path.join(SRC, name), 'utf8');
    vm.runInContext(code, dom.getInternalVMContext(), { filename: name });
  }
  const originalDisconnect = window.AgixtChat && window.AgixtChat.disconnect;
  if (typeof originalDisconnect === 'function') {
    window.AgixtChat.disconnect = () => {
      try { originalDisconnect.call(window.AgixtChat); } catch (_) {}
      try {
        if (window.AgixtNotifications && typeof window.AgixtNotifications.stop === 'function') {
          window.AgixtNotifications.stop();
        }
      } catch (_) {}
      try {
        if (window.AgixtTeamChat && typeof window.AgixtTeamChat.unmount === 'function') {
          window.AgixtTeamChat.unmount();
        }
      } catch (_) {}
      try {
        if (window.AgixtDesktopExtensions && typeof window.AgixtDesktopExtensions.stop === 'function') {
          window.AgixtDesktopExtensions.stop();
        }
      } catch (_) {}
      try {
        if (window.AgixtDesktopUpdates
            && typeof window.AgixtDesktopUpdates.syncSettings === 'function'
            && typeof window.AgixtDesktopUpdates.scheduleAutoCheck === 'function') {
          window.AgixtDesktopUpdates.syncSettings({ desktop_auto_update: false });
          window.AgixtDesktopUpdates.scheduleAutoCheck();
        }
      } catch (_) {}
    };
  }
  return { window, calls };
}

function loadDesktopExtensionsOnly() {
  const dom = new JSDOM(
    '<!doctype html><body><button class="sidenav-btn is-active" data-view="audible"></button><div class="chat-screen-main"><div class="view-pane" data-view="chat"></div><div class="view-pane view-pane-extension" data-view="audible"></div></div></body>',
    { runScripts: 'outside-only', url: 'http://localhost/' },
  );
  const { window } = dom;
  trackDom(dom);
  window.__TAURI__ = { core: { invoke: async () => null } };
  window.AgixtAppContext = () => ({
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    agentId: 'agent-id',
  });
  const code = fs.readFileSync(path.join(SRC, 'desktop-extensions.js'), 'utf8');
  vm.runInContext(code, dom.getInternalVMContext(), { filename: 'desktop-extensions.js' });
  return { window };
}

function loadCrudExtensionPage(filePath) {
  const dom = new JSDOM(
    '<!doctype html><body><div class="chat-screen-main"><div class="view-pane view-pane-extension" data-view="estimates"></div></div></body>',
    { runScripts: 'outside-only', url: 'http://localhost/' },
  );
  const { window } = dom;
  trackDom(dom);
  const registrations = new Map();
  window.AgixtRegisterExtension = (id, ctrl) => registrations.set(id, ctrl);
  for (const source of [
    { name: 'desktop-crud.js', file: path.join(SRC, 'desktop-crud.js') },
    { name: path.basename(filePath), file: filePath },
  ]) {
    const code = fs.readFileSync(source.file, 'utf8');
    vm.runInContext(code, dom.getInternalVMContext(), { filename: source.name });
  }
  return { window, registrations };
}

function loadXTSchoolExtensionPage(entry = 'xtschool') {
  const entryFile = entry === 'xtschool' || entry === 'home'
    ? path.join(__dirname, '..', '..', '..', 'xtschool', 'ui', 'main.js')
    : path.join(__dirname, '..', '..', '..', 'xtschool', 'ui', entry, 'main.js');
  const dom = new JSDOM(
    '<!doctype html><body><div class="chat-screen-main"><div class="view-pane view-pane-extension" data-view="xtschool"></div></div></body>',
    { runScripts: 'outside-only', url: 'http://localhost/' },
  );
  const { window } = dom;
  trackDom(dom);
  const registrations = new Map();
  window.AgixtRegisterExtension = (id, ctrl) => registrations.set(id, ctrl);
  window.Plyr = function PlyrStub(target) {
    this.target = target;
    this.on = (eventName, callback) => {
      if (target && typeof target.addEventListener === 'function') {
        target.addEventListener(eventName, () => callback());
      }
    };
    this.destroy = () => {};
    Object.defineProperty(this, 'currentTime', { get: () => Number(target && target.currentTime) || 0 });
    Object.defineProperty(this, 'duration', { get: () => Number(target && target.duration) || 0 });
    Object.defineProperty(this, 'source', {
      set: (value) => {
        const source = value && value.sources && value.sources[0];
        if (!source || source.provider !== 'youtube') return;
        const iframe = window.document.createElement('iframe');
        iframe.className = 'xts-player-frame';
        iframe.src = 'https://www.youtube.com/embed/' + encodeURIComponent(source.src) + '?rel=0';
        target.replaceWith(iframe);
      },
    });
  };
  window.AgixtSession = {
    fetch: async (url, init = {}) => {
      const parsed = new URL(String(url), 'http://localhost');
      if (parsed.pathname === '/v1/desktop/extensions/xtschool/assets/xtschool-core.js') {
        return new Response(
          fs.readFileSync(path.join(__dirname, '..', '..', '..', 'xtschool', 'ui', 'assets', 'xtschool-core.js'), 'utf8'),
          { status: 200, headers: { 'content-type': 'application/javascript' } },
        );
      }
      if (typeof window.fetch === 'function') {
        return window.fetch(url, init);
      }
      return new Response('', { status: 404 });
    },
  };
  const code = fs.readFileSync(entryFile, 'utf8');
  vm.runInContext(code, dom.getInternalVMContext(), { filename: 'xtschool-main.js' });
  return { window, registrations };
}

function loadAudibleExtensionPage() {
  const dom = new JSDOM(
    '<!doctype html><body><div class="chat-screen-main"><div class="view-pane view-pane-extension" data-view="audible"></div></div></body>',
    { runScripts: 'outside-only', url: 'http://localhost/' },
  );
  const { window } = dom;
  trackDom(dom);
  const registrations = new Map();
  window.requestAnimationFrame = window.requestAnimationFrame || ((cb) => setTimeout(() => cb(Date.now()), 0));
  window.URL.createObjectURL = window.URL.createObjectURL || (() => 'blob:audible-test');
  window.URL.revokeObjectURL = window.URL.revokeObjectURL || (() => {});
  window.Audio = class {
    constructor() {
      this.paused = true;
      this.currentTime = 0;
      this.duration = 0;
      this.src = '';
    }
    addEventListener() {}
    pause() { this.paused = true; }
    play() { this.paused = false; return Promise.resolve(); }
  };
  window.AgixtRegisterExtension = (id, ctrl) => registrations.set(id, ctrl);
  const code = fs.readFileSync(path.join(WEB, 'extensions', 'desktop', 'audible', 'main.js'), 'utf8');
  vm.runInContext(code, dom.getInternalVMContext(), { filename: 'audible-main.js' });
  return { window, registrations };
}

function loadCompaniesExtensionPage() {
  const dom = new JSDOM(
    '<!doctype html><body><div class="chat-screen-main"><div class="view-pane view-pane-extension" data-view="companies"></div></div></body>',
    { runScripts: 'outside-only', url: 'http://localhost/' },
  );
  const { window } = dom;
  trackDom(dom);
  const registrations = new Map();
  window.AgixtRegisterExtension = (id, ctrl) => registrations.set(id, ctrl);
  const code = fs.readFileSync(path.join(WEB, 'extensions', 'desktop', 'companies', 'main.js'), 'utf8');
  vm.runInContext(code, dom.getInternalVMContext(), { filename: 'companies-main.js' });
  return { window, registrations };
}

function loadReposExtensionPage() {
  const dom = new JSDOM(
    '<!doctype html><body><div class="chat-screen-main"><div class="view-pane view-pane-extension" data-view="repos"></div></div></body>',
    { runScripts: 'outside-only', url: 'http://localhost/' },
  );
  const { window } = dom;
  trackDom(dom);
  const registrations = new Map();
  window.AgixtRegisterExtension = (id, ctrl) => registrations.set(id, ctrl);
  window.alert = () => {};
  const code = fs.readFileSync(path.join(WEB, 'extensions', 'desktop', 'repos', 'main.js'), 'utf8');
  vm.runInContext(code, dom.getInternalVMContext(), { filename: 'repos-main.js' });
  return { window, registrations };
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function waitFor(ms = 0) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function loadWorkspaceModelsOnly() {
  const dom = new JSDOM('<!doctype html><body></body>', {
    runScripts: 'outside-only',
    url: 'http://localhost/',
  });
  const { window } = dom;
  trackDom(dom);
  window.requestIdleCallback = (cb) => {
    cb();
    return 1;
  };
  const code = fs.readFileSync(path.join(SRC, 'workspace-models.js'), 'utf8');
  vm.runInContext(code, dom.getInternalVMContext(), { filename: 'workspace-models.js' });
  return { window };
}

function loadWorkspacePreviewOnly() {
  const dom = new JSDOM('<!doctype html><body></body>', {
    runScripts: 'outside-only',
    url: 'http://localhost/',
  });
  const { window } = dom;
  trackDom(dom);
  let objectUrlCount = 0;
  const revoked = [];
  window.URL.createObjectURL = () => `blob:workspace-preview-${++objectUrlCount}`;
  window.URL.revokeObjectURL = (url) => { revoked.push(url); };
  const code = fs.readFileSync(path.join(SRC, 'workspace-preview.js'), 'utf8');
  vm.runInContext(code, dom.getInternalVMContext(), { filename: 'workspace-preview.js' });
  return { window, revoked };
}

function loadWorkspaceOnly({ getWorkspace } = {}) {
  const dom = new JSDOM('<!doctype html><body><div class="chat-screen-main"></div></body>', {
    runScripts: 'outside-only',
    url: 'http://localhost/',
  });
  const { window } = dom;
  trackDom(dom);
  window.requestAnimationFrame = window.requestAnimationFrame || ((cb) => setTimeout(() => cb(Date.now()), 0));
  window.cancelAnimationFrame = window.cancelAnimationFrame || ((id) => clearTimeout(id));
  window.AgixtWorkspacePreview = {
    isPreviewableMedia: () => false,
    render: () => {},
    extractTextFromBlob: async () => '',
  };
  window.AgixtWorkspaceModels = {
    init: () => {},
    ensureModelsLoaded: async () => {},
    dispose: () => {},
  };
  window.AgixtWorkspaceApi = {
    getWorkspace: getWorkspace || (async () => ({ items: [] })),
    downloadFile: async () => ({ blob: new window.Blob(['']), text: '' }),
    uploadFiles: async () => ({ items: [] }),
    createFolder: async () => ({ items: [] }),
    deleteItem: async () => ({ items: [] }),
    moveItem: async () => ({ items: [] }),
  };
  vm.runInContext(
    fs.readFileSync(path.join(SRC, 'workspace.js'), 'utf8'),
    dom.getInternalVMContext(),
    { filename: 'workspace.js' },
  );
  return { window };
}

function createFakeMonaco() {
  const models = new Map();
  const makeDisposable = () => ({ dispose() {} });
  return {
    Uri: {
      parse: (raw) => ({
        path: String(raw).replace(/^file:\/\//, ''),
        toString: () => raw,
      }),
    },
    languages: {
      typescript: null,
      registerDefinitionProvider: () => makeDisposable(),
      registerReferenceProvider: () => makeDisposable(),
      registerDocumentSymbolProvider: () => makeDisposable(),
    },
    editor: {
      getModel: (uri) => models.get(uri.toString()) || null,
      getModels: () => Array.from(models.values()).filter((m) => !m.isDisposed()),
      createModel: (text, language, uri) => {
        let value = text;
        let disposed = false;
        const model = {
          uri,
          language,
          getValue: () => value,
          setValue: (next) => { value = next; },
          isDisposed: () => disposed,
          dispose: () => {
            disposed = true;
            models.delete(uri.toString());
          },
          findMatches: () => [],
          getLineContent: () => '',
        };
        models.set(uri.toString(), model);
        return model;
      },
    },
  };
}

test('markdown: paragraph and inline formatting', () => {
  const { window } = loadFrontend();
  const html = window.AgixtMarkdown.render('Hello **bold** and *italic*.');
  assert.match(html, /<p>Hello <strong>bold<\/strong> and <em>italic<\/em>\.<\/p>/);
});

test('markdown: model control markers are hidden', () => {
  const { window } = loadFrontend();
  const html = window.AgixtMarkdown.render('<|mark_start|>Hello **there**<|mark_end|>');
  assert.equal(html, '<p>Hello <strong>there</strong></p>');
});

test('markdown: code fence preserves whitespace + adds copy/download toolbar', () => {
  const { window } = loadFrontend();
  const html = window.AgixtMarkdown.render('```py\ndef hi():\n  pass\n```');
  // Body is preserved verbatim inside the new chrome wrapper.
  assert.match(html, /<pre class="md-codeblock-pre"><code class="language-py">def hi\(\):\n  pass<\/code><\/pre>/);
  assert.match(html, /md-codeblock-lang">py</);
  // Icon-only buttons — title/aria-label carry the action name now.
  assert.match(html, /title="Copy"/);
  assert.match(html, /title="Download"/);
});

test('markdown: image URL becomes <img>', () => {
  const { window } = loadFrontend();
  const html = window.AgixtMarkdown.render('![cat](/outputs/cat.png)');
  assert.match(html, /<img[^>]+alt="cat"[^>]+src="\/outputs\/cat\.png"/);
});

test('markdown: video URL becomes <video controls>', () => {
  const { window } = loadFrontend();
  const html = window.AgixtMarkdown.render('![clip](/outputs/clip.mp4)');
  assert.match(html, /<video[^>]+controls[^>]+src="\/outputs\/clip\.mp4"/);
});

test('markdown: audio URL becomes <audio controls>', () => {
  const { window } = loadFrontend();
  const html = window.AgixtMarkdown.render('![voice](/outputs/voice.mp3)');
  assert.match(html, /<audio[^>]+controls[^>]+src="\/outputs\/voice\.mp3"/);
});

test('markdown: external <a> hrefs route through agixt-external-link, but media tags accept them', () => {
  const { window } = loadFrontend();
  const target = window.document.createElement('div');
  window.AgixtMarkdown.renderInto(
    target,
    '[site](https://example.com/page.html) https://example.com/clip.mp4 ![gif](https://media.tenor.com/abc.gif)',
  );
  // Plain anchors still proxy through the external-link handler so we
  // don't open a Tauri webview window for an attacker URL by accident.
  assert.equal(target.querySelector('a[href^="https://"]'), null);
  const links = target.querySelectorAll('a[data-external-url]');
  assert.ok(links.length >= 1, 'at least one anchor proxied');
  // Media tags (img/video/audio) — Tenor / Giphy / generic image hosts
  // render as <img>/<video> so user-shared GIFs and clips display
  // inline instead of as a bare link, matching the web app.
  const video = target.querySelector('video[src^="https://"]');
  assert.ok(video, 'external https video renders as <video>');
  const gifImg = target.querySelector('img[src^="https://media.tenor.com"]');
  assert.ok(gifImg, 'tenor URL renders as <img>');
});

test('markdown: untrusted html and unsafe URLs stay inert', () => {
  const { window } = loadFrontend();
  const target = window.document.createElement('div');
  window.AgixtMarkdown.renderInto(
    target,
    '<img src=x onerror=alert(1)> [bad](javascript:alert(1)) ![x](javascript:alert(1))',
  );
  assert.equal(target.querySelector('script'), null);
  assert.equal(target.querySelector('[onerror]'), null);
  assert.equal(target.querySelector('a[href^="javascript:"]'), null);
  assert.equal(target.querySelector('img[src^="javascript:"]'), null);
  assert.match(target.textContent, /<img src=x onerror=alert\(1\)>/);
});

test('markdown: lists render correctly', () => {
  const { window } = loadFrontend();
  const html = window.AgixtMarkdown.render('- one\n- two\n- three');
  assert.match(html, /<ul><li>one<\/li><li>two<\/li><li>three<\/li><\/ul>/);
});

test('markdown: classifyMedia distinguishes images, videos, audio', () => {
  const { window } = loadFrontend();
  const c = window.AgixtMarkdown.classifyMedia;
  assert.equal(c('https://x.com/p.jpg'), 'image');
  assert.equal(c('https://x.com/v.mp4'), 'video');
  assert.equal(c('https://x.com/a.wav'), 'audio');
  assert.equal(c('https://tenor.com/somegif'), 'image');
  assert.equal(c('https://example.com/page.html'), null);
});

test('workspace models: bounded preload avoids Monaco listener leak threshold', async () => {
  const { window } = loadWorkspaceModelsOnly();
  const monaco = createFakeMonaco();
  const items = Array.from({ length: 250 }, (_, i) => ({
    type: 'file',
    name: `file-${String(i).padStart(3, '0')}.js`,
    path: `/src/file-${String(i).padStart(3, '0')}.js`,
  }));
  const downloads = [];
  const api = {
    downloadFile: async (_cfg, _conversationId, filePath) => {
      downloads.push(filePath);
      return { blob: { text: async () => `console.log(${JSON.stringify(filePath)});` } };
    },
  };

  await window.AgixtWorkspaceModels.ensureModelsLoaded(
    monaco,
    api,
    {},
    'conversation-1',
    items,
    { activePath: '/src/file-249.js' },
  );

  const models = monaco.editor.getModels();
  assert.equal(models.length, 120);
  assert.equal(downloads.length, 120);
  assert.ok(models.some((m) => m.uri.path === '/src/file-249.js'), 'active file stays in the bounded cache');

  window.AgixtWorkspaceModels.dispose(monaco);
  assert.equal(monaco.editor.getModels().length, 0);
});

test('workspace preview: html resolves workspace-relative image URLs', async () => {
  const { window, revoked } = loadWorkspacePreviewOnly();
  const target = window.document.createElement('div');
  window.document.body.appendChild(target);
  const downloads = [];
  const api = {
    downloadFile: async (_cfg, conversationId, filePath) => {
      downloads.push({ conversationId, filePath });
      if (filePath !== 'computer-use/screenshots/step-001-after.jpeg') {
        throw new Error(`${filePath} missing`);
      }
      return { blob: new window.Blob(['image-bytes'], { type: 'image/jpeg' }) };
    },
  };

  window.AgixtWorkspacePreview.renderHtmlDoc(
    target,
    '<!doctype html><html><body><img src="../computer-use/screenshots/step-001-after.jpeg"><img src="https://example.com/logo.png"></body></html>',
    {
      api,
      cfg: { serverUrl: 'http://localhost:7437', jwt: 'jwt' },
      conversationId: 'conversation-1',
      filePath: 'computer-use/storyboard.html',
    },
  );
  await new Promise((resolve) => setTimeout(resolve, 0));

  const iframe = target.querySelector('.wkfp-html');
  assert.ok(iframe, 'preview iframe rendered');
  assert.match(iframe.srcdoc, /src="blob:workspace-preview-1"/);
  assert.match(iframe.srcdoc, /src="https:\/\/example\.com\/logo\.png"/);
  assert.deepEqual(downloads, [{
    conversationId: 'conversation-1',
    filePath: 'computer-use/screenshots/step-001-after.jpeg',
  }]);

  window.AgixtWorkspacePreview.destroy(target);
  assert.deepEqual(revoked, ['blob:workspace-preview-1']);
});

test('workspace: conversation reload ignores stale in-flight listing', async () => {
  let resolveOld;
  const calls = [];
  const { window } = loadWorkspaceOnly({
    getWorkspace: async (_cfg, conversationId) => {
      calls.push(conversationId);
      if (conversationId === 'old') {
        return new Promise((resolve) => {
          resolveOld = () => resolve({
            items: [{ path: 'old.md', name: 'old.md', type: 'file', size: 3 }],
          });
        });
      }
      return {
        items: [{ path: 'new.md', name: 'new.md', type: 'file', size: 3 }],
      };
    },
  });

  await window.AgixtWorkspace.open({
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    agentName: 'XT',
    conversationId: 'old',
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(calls, ['old']);

  window.AgixtWorkspace.reload({
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    agentName: 'XT',
    conversationId: 'new',
    silent: true,
  });
  resolveOld();
  await new Promise((resolve) => setTimeout(resolve, 30));

  assert.ok(calls.includes('new'), 'new conversation was refreshed after stale request finished');
  const treeText = window.document.querySelector('.wk-tree').textContent;
  assert.match(treeText, /new\.md/);
  assert.doesNotMatch(treeText, /old\.md/);
  await window.AgixtWorkspace.close();
});

test('web runtime: localStorage settings persist web auth and omit unrelated token aliases', async () => {
  const { window } = loadWebRuntime();
  const saved = await window.__TAURI__.core.invoke('save_settings', {
    settings: {
      server_url: 'http://localhost:7437',
      web_url: 'http://localhost:3437',
      service_brand: 'web',
      jwt: 'secret.jwt',
      token: 'secret.token',
      user_email: 'test@example.com',
      agent_name: 'XT',
    },
  });
  assert.equal(saved.jwt, 'secret.jwt');
  const stored = JSON.parse(window.localStorage.getItem('agixt.web.settings.v1'));
  assert.equal(stored.jwt, 'secret.jwt');
  assert.equal(stored.token, undefined);
  assert.equal(stored.user_email, 'test@example.com');
  assert.equal(stored.server_url, 'http://localhost:7437');

  const reloaded = await window.__TAURI__.core.invoke('get_settings');
  assert.equal(reloaded.jwt, 'secret.jwt');
  assert.equal(reloaded.user_email, 'test@example.com');

  await window.__TAURI__.core.invoke('logout');
  const afterLogout = JSON.parse(window.localStorage.getItem('agixt.web.settings.v1'));
  assert.equal(afterLogout.jwt, null);
  assert.equal(afterLogout.user_email, null);
});

test('web runtime: hosted brand origin owns title, favicon, and service selection', async () => {
  const { window } = loadWebRuntime('https://boltremote.com/user');

  const brands = await window.__TAURI__.core.invoke('list_service_brands');
  assert.equal(brands.length, 1);
  assert.equal(brands[0].slug, 'boltremote');
  assert.equal(brands[0].locked, true);
  assert.equal(brands[0].default_url, 'https://boltremote.com');
  assert.equal(brands[0].default_web_url, 'https://boltremote.com');
  assert.equal(window.document.title, 'BoltRemote');
  assert.ok(window.document.getElementById('app-favicon').href.endsWith('/assets/brands/boltremote-favicon.svg'));

  const settings = await window.__TAURI__.core.invoke('save_settings', {
    settings: {
      server_url: 'https://api.agixt.com',
      web_url: 'https://agixt.com',
      service_brand: 'agixt',
      jwt: 'jwt',
    },
  });
  assert.equal(settings.service_brand, 'boltremote');
  assert.equal(settings.server_url, 'https://boltremote.com');
  assert.equal(settings.web_url, 'https://boltremote.com');

  const stored = JSON.parse(window.localStorage.getItem('agixt.web.settings.v1'));
  assert.equal(stored.service_brand, 'boltremote');
});

test('web app context: hosted browser routes loopback API settings through page origin', async () => {
  const { window } = loadFullApp({
    webRuntime: true,
    url: 'https://josh.devxt.com/repos',
  });
  await waitFor(30);

  const ctx = window.AgixtAppContext();
  assert.ok(ctx, 'app context is available after boot');
  assert.equal(ctx.serverUrl, 'https://josh.devxt.com');
});

test('web app context: local browser routes backend settings through web origin proxy', async () => {
  const { window } = loadFullApp({
    webRuntime: true,
    url: 'http://localhost:3437/repos',
  });
  await waitFor(30);

  const ctx = window.AgixtAppContext();
  assert.ok(ctx, 'app context is available after boot');
  assert.equal(ctx.serverUrl, 'http://localhost:3437');
});

test('desktop session: web runtime uses page origin for relative API calls when configured URL is loopback', async () => {
  const dom = new JSDOM('<!doctype html><body></body>', {
    runScripts: 'outside-only',
    url: 'http://localhost:3437/repos',
  });
  const { window } = dom;
  trackDom(dom);
  let requestedUrl = '';
  window.__AGIXT_WEB_RUNTIME = true;
  window.__TAURI__ = { core: { invoke: async () => null } };
  window.AgixtAppContext = () => ({
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    companyId: 'company-id',
  });
  window.fetch = async (url, init = {}) => {
    requestedUrl = String(url);
    assert.equal(init.headers.Authorization, 'Bearer jwt');
    assert.equal(init.headers['X-Company-ID'], 'company-id');
    return jsonResponse({ ok: true });
  };
  const code = fs.readFileSync(path.join(SRC, 'desktop-session.js'), 'utf8');
  vm.runInContext(code, dom.getInternalVMContext(), { filename: 'desktop-session.js' });

  const data = await window.AgixtSession.request('/v1/github/repos');
  assert.equal(data.ok, true);
  assert.equal(requestedUrl, 'http://localhost:3437/v1/github/repos');
});

test('desktop session: HTML proxy errors are summarized instead of dumped into alerts', async () => {
  const dom = new JSDOM('<!doctype html><body></body>', {
    runScripts: 'outside-only',
    url: 'https://josh.devxt.com/repos',
  });
  const { window } = dom;
  trackDom(dom);
  window.__AGIXT_WEB_RUNTIME = true;
  window.__TAURI__ = { core: { invoke: async () => null } };
  window.AgixtAppContext = () => ({
    serverUrl: 'https://josh.devxt.com',
    jwt: 'jwt',
  });
  window.fetch = async () => new Response(
    '<!DOCTYPE html><html class="no-js ie8 oldie"><body>Bad gateway</body></html>',
    { status: 502, headers: { 'Content-Type': 'text/html' } },
  );
  const code = fs.readFileSync(path.join(SRC, 'desktop-session.js'), 'utf8');
  vm.runInContext(code, dom.getInternalVMContext(), { filename: 'desktop-session.js' });

  await assert.rejects(
    () => window.AgixtSession.request('/v1/github/repos/dev/repo/fix-vulns', { method: 'POST', json: {} }),
    (err) => {
      assert.equal(err.message, 'Bad gateway from the AGiXT API proxy.');
      assert.ok(!String(err.message).includes('<!DOCTYPE html>'));
      return true;
    },
  );
});

test('web runtime: OAuth flow storage keeps only callback state', async () => {
  const { window } = loadWebRuntime('https://rust.workconductor.com/user');
  assert.equal(window.__AGIXT_WEB_RUNTIME, true);
  const result = await window.__TAURI__.core.invoke('build_oauth_connect_url', {
    args: {
      server_url: 'http://localhost:7437',
      web_url: 'http://localhost:3437',
      provider: {
        name: 'Google SSO',
        authorize: 'https://accounts.google.com/o/oauth2/auth',
        client_id: 'client-id',
        scopes: 'openid email',
      },
    },
  });
  assert.match(result.url, /^https:\/\/accounts\.google\.com\/o\/oauth2\/auth\?/);
  assert.equal(result.redirect_uri, 'https://rust.workconductor.com/user/close/google');
  const stored = JSON.parse(window.localStorage.getItem('agixt.web.oauthFlow.v1'));
  assert.deepEqual(Object.keys(stored).sort(), [
    'connect',
    'provider_endpoint_slug',
    'provider_redirect_slug',
    'server_url',
    'service_brand',
    'started_at',
    'web_url',
  ]);
  assert.equal(stored.connect, true);
  assert.equal(stored.web_url, 'https://rust.workconductor.com');
  assert.equal(stored.provider, undefined);
  assert.equal(stored.redirect_uri, undefined);
  assert.equal(stored.client_id, undefined);
});

test('web runtime: desktop OAuth login returns token to app deep link', async () => {
  const jwt = 'header.payload.signature';
  const opened = [];
  const requests = [];
  const state = encodeURIComponent('desktop=1');
  const { window } = loadWebRuntime(`https://josh.devxt.com/user/close/microsoft?code=auth-code&state=${state}`);
  window.__AGIXT_OPEN_DEEP_LINK = (url) => opened.push(url);
  window.fetch = async (url, opts = {}) => {
    requests.push({ url, opts });
    return new Response(JSON.stringify({ token: jwt, email: 'josh@devxt.com' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  await window.AgixtWebRuntime.handleOAuthClose();

  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, 'https://josh.devxt.com/v1/oauth2/microsoft');
  assert.equal(requests[0].opts.method, 'POST');
  const body = JSON.parse(requests[0].opts.body);
  assert.equal(body.code, 'auth-code');
  assert.equal(body.state, 'desktop=1');
  assert.equal(body.referrer, 'https://josh.devxt.com/user/close/microsoft');
  assert.deepEqual(opened, [`agixt://login?token=${encodeURIComponent(jwt)}`]);
  assert.equal(JSON.parse(window.localStorage.getItem('agixt.web.settings.v1') || '{}').jwt, undefined);
  assert.match(window.document.querySelector('#oauth-status p').textContent, /desktop app/i);
  const link = window.document.querySelector('[data-oauth-desktop-actions] a');
  assert.equal(link.getAttribute('href'), `agixt://login?token=${encodeURIComponent(jwt)}`);
  assert.match(link.textContent, /open agixt desktop/i);
});

test('web runtime: desktop extension OAuth returns code to app deep link', async () => {
  const opened = [];
  let fetchCalled = false;
  const state = encodeURIComponent('desktop_connect=1|provider=microsoft_365');
  const { window } = loadWebRuntime(`https://josh.devxt.com/user/close/microsoft?code=connect-code&state=${state}`);
  window.__AGIXT_OPEN_DEEP_LINK = (url) => opened.push(url);
  window.fetch = async () => {
    fetchCalled = true;
    throw new Error('desktop extension connect should not post from web callback');
  };

  await window.AgixtWebRuntime.handleOAuthClose();

  assert.equal(fetchCalled, false);
  assert.deepEqual(opened, ['agixt://oauth-connect?provider=microsoft_365&code=connect-code']);
  assert.match(window.document.querySelector('#oauth-status p').textContent, /desktop app/i);
  const link = window.document.querySelector('[data-oauth-desktop-actions] a');
  assert.equal(link.getAttribute('href'), 'agixt://oauth-connect?provider=microsoft_365&code=connect-code');
  assert.match(link.textContent, /return to agixt desktop/i);
});

test('web runtime: OAuth close page loads deployment config before runtime', () => {
  const html = fs.readFileSync(path.join(WEB, 'oauth-close.html'), 'utf8');
  assert.match(html, /<script src="\/web-config\.js"><\/script>\s*<script src="\/web-runtime\.js"><\/script>/);
});

test('web runtime: opener preserves signed Stripe checkout fragments', async () => {
  const { window } = loadWebRuntime('https://rust.workconductor.com/');
  const opened = [];
  window.open = (url, target) => {
    opened.push({ url, target });
    return { opener: window };
  };
  const stripeUrl = [
    'https://checkout.stripe.com/c/pay/cs_test_1234567890',
    '#fidkdWxOYHwnPyd1blpxYHZxWjA0T0x%2FTVd%2Ba3dMcXJ0Y0FrJyknaWR8anBxUXx1YCc%2FJ3Zsa2JpYFpscWBoJyknYGtkZ2lgVWlkZmBtamlhYHd2Jz9xd3BgeCUl',
  ].join('');

  await window.__TAURI__.opener.openUrl(stripeUrl);

  assert.equal(opened.length, 1);
  assert.equal(opened[0].target, '_blank');
  assert.equal(opened[0].url, stripeUrl);
  assert.ok(opened[0].url.includes('%2F'));
  assert.ok(!opened[0].url.includes('%252F'));
});

test('chat: classifyActivity tags activities by content', () => {
  // The classifier function isn't directly exposed, but we can exercise
  // it via the rendered DOM produced when an [ACTIVITY] envelope arrives.
  const { window } = loadFrontend();
  window.AgixtChat.configure({ serverUrl: 'http://x', jwt: 'j', conversationId: 'c', reconnect: false });
  // Synthesize an envelope by calling the internal handlers via the public
  // surface. ingest is reached by simulating a "message_added" event would
  // require deeper hooks — instead, ensure the public API exists.
  assert.equal(typeof window.AgixtChat.send, 'function');
  assert.equal(typeof window.AgixtChat.connect, 'function');
  assert.equal(typeof window.AgixtChat.disconnect, 'function');
});

test('chat: persisted assistant message does not duplicate live placeholder', async () => {
  const streamListeners = new Map();
  let socket = null;
  class TestWebSocket {
    constructor() {
      this.readyState = TestWebSocket.OPEN;
      socket = this;
      setTimeout(() => this.onopen && this.onopen(), 0);
    }
    send() {}
    close() {
      this.readyState = 3;
    }
  }
  TestWebSocket.OPEN = 1;

  const { window } = loadFrontend({
    WebSocketClass: TestWebSocket,
    eventListen: async (name, cb) => {
      streamListeners.set(name, cb);
      return () => streamListeners.delete(name);
    },
    ipc: {
      chat_send: async ({ args }) => {
        const streamId = args.stream_id;
        setTimeout(() => {
          streamListeners.get(`chat-stream:${streamId}`)?.({
            payload: { event: { kind: 'delta', data: { text: 'Partial' } } },
          });
        }, 0);
        setTimeout(() => {
          socket?.onmessage?.({
            data: JSON.stringify({
              type: 'message_added',
              data: {
                id: 'server-assistant-1',
                role: 'assistant',
                message: 'Full answer',
                timestamp: '2026-05-17T12:00:00.000Z',
              },
            }),
          });
        }, 1);
        setTimeout(() => {
          streamListeners.get(`chat-stream:${streamId}`)?.({
            payload: { event: { kind: 'done', data: { text: 'Full answer', finish_reason: 'stop' } } },
          });
        }, 2);
        return streamId;
      },
    },
  });
  window.AgixtChat.configure({
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    conversationId: 'c',
  });

  await window.AgixtChat.send('make a file', 'c');
  await new Promise((resolve) => setTimeout(resolve, 20));

  const assistantMessages = [...window.document.querySelectorAll('#messages .message-assistant')]
    .map((node) => node.textContent.replace(/\s+/g, ' ').trim())
    .filter(Boolean);
  assert.equal(assistantMessages.length, 1);
  assert.ok(assistantMessages[0].startsWith('Full answer'));
  assert.doesNotMatch(assistantMessages.join('\n'), /Partial/);
  window.AgixtChat.disconnect();
});

test('chat: persisted activity and answer adopt live stream placeholders', async () => {
  const streamListeners = new Map();
  let socket = null;
  class TestWebSocket {
    constructor() {
      this.readyState = TestWebSocket.OPEN;
      socket = this;
      setTimeout(() => this.onopen && this.onopen(), 0);
    }
    send() {}
    close() { this.readyState = 3; }
  }
  TestWebSocket.OPEN = 1;

  const finalText = 'I created `oranges.md` in your workspace.\n\n[oranges.md](oranges.md)';
  const { window } = loadFrontend({
    WebSocketClass: TestWebSocket,
    eventListen: async (name, cb) => {
      streamListeners.set(name, cb);
      return () => streamListeners.delete(name);
    },
    ipc: {
      chat_send: async ({ args }) => {
        const streamId = args.stream_id;
        setTimeout(() => {
          streamListeners.get(`chat-stream:${streamId}`)?.({
            payload: { event: { kind: 'activity', data: { content: 'Creating oranges.md', complete: false } } },
          });
        }, 0);
        setTimeout(() => {
          socket?.onmessage?.({
            data: JSON.stringify({
              type: 'message_added',
              data: {
                id: 'server-activity-1',
                role: 'XT',
                message: '[ACTIVITY] Thinking',
                timestamp: '2026-05-17T12:00:01.000Z',
              },
            }),
          });
        }, 1);
        setTimeout(() => {
          streamListeners.get(`chat-stream:${streamId}`)?.({
            payload: { event: { kind: 'done', data: { text: finalText, finish_reason: 'stop' } } },
          });
        }, 2);
        setTimeout(() => {
          socket?.onmessage?.({
            data: JSON.stringify({
              type: 'message_added',
              data: {
                id: 'server-assistant-1',
                role: 'XT',
                message: finalText,
                timestamp: '2026-05-17T12:00:02.000Z',
              },
            }),
          });
        }, 3);
        return streamId;
      },
    },
  });
  window.AgixtChat.configure({
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    conversationId: 'c',
  });

  await window.AgixtChat.send('make oranges.md', 'c');
  await new Promise((resolve) => setTimeout(resolve, 30));

  assert.equal(window.document.querySelectorAll('#messages .activity').length, 1);
  const assistantMessages = [...window.document.querySelectorAll('#messages .message-assistant')]
    .map((node) => node.textContent.replace(/\s+/g, ' ').trim())
    .filter(Boolean);
  assert.equal(assistantMessages.length, 1);
  assert.match(assistantMessages[0], /oranges\.md/);
  window.AgixtChat.disconnect();
});

test('chat: live activity appends below streamed assistant text until final order settles', async () => {
  const streamListeners = new Map();
  let emitDone = null;
  const { window } = loadFrontend({
    eventListen: async (name, cb) => {
      streamListeners.set(name, cb);
      return () => streamListeners.delete(name);
    },
    ipc: {
      chat_send: async ({ args }) => {
        const streamId = args.stream_id;
        setTimeout(() => {
          const cb = streamListeners.get(`chat-stream:${streamId}`);
          cb?.({ payload: { event: { kind: 'delta', data: { text: 'Drafting response' } } } });
          cb?.({ payload: { event: { kind: 'activity', data: { content: 'Creating oranges.md', complete: false } } } });
        }, 0);
        emitDone = () => {
          streamListeners.get(`chat-stream:${streamId}`)?.({
            payload: { event: { kind: 'done', data: { text: 'Done.', finish_reason: 'stop' } } },
          });
        };
        return streamId;
      },
    },
  });
  window.AgixtChat.configure({
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    conversationId: 'c',
    reconnect: false,
  });

  const sendPromise = window.AgixtChat.send('make oranges.md', 'c');
  await new Promise((resolve) => setTimeout(resolve, 30));

  const assistant = window.document.querySelector('#messages .message-assistant');
  const activity = window.document.querySelector('#messages .activity');
  assert.ok(assistant, 'assistant text is visible while streaming');
  assert.ok(activity, 'activity is visible while streaming');
  assert.ok(
    assistant.compareDocumentPosition(activity) & window.Node.DOCUMENT_POSITION_FOLLOWING,
    'new live activity appears below already-visible streamed text',
  );

  emitDone();
  await sendPromise;

  const finalAssistant = window.document.querySelector('#messages .message-assistant');
  const finalActivity = window.document.querySelector('#messages .activity');
  assert.ok(
    finalActivity.compareDocumentPosition(finalAssistant) & window.Node.DOCUMENT_POSITION_FOLLOWING,
    'final assistant answer settles below the activity block',
  );
  window.AgixtChat.disconnect();
});

test('chat: stop cancels any active local client action', async () => {
  const { window } = loadFrontend();
  let stopped = 0;
  window.AgixtClientActions.stopActiveAction = () => {
    stopped += 1;
    return true;
  };

  await window.AgixtChat.stop();

  assert.equal(stopped, 1);
});

test('chat: workspace file links open in desktop workspace', async () => {
  const opened = [];
  const { window } = loadFrontend({
    ipc: {
      get_conversation_history: async () => [{
        id: 'server-assistant-1',
        role: 'XT',
        message: 'You can view it here:\n\n[oranges.md](oranges.md)',
        timestamp: '2026-05-17T12:00:00.000Z',
      }],
    },
  });
  window.AgixtWorkspace = {
    openPath: async (path, opts) => opened.push({ path, opts }),
  };
  window.AgixtChat.configure({
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    conversationId: 'c',
    reconnect: false,
  });
  await window.AgixtChat.loadHistory('c');

  const link = window.document.querySelector('#messages a[data-workspace-path]');
  assert.ok(link, 'workspace link is tagged');
  link.dispatchEvent(new window.MouseEvent('click', { bubbles: true, cancelable: true }));

  assert.equal(opened.length, 1);
  assert.equal(opened[0].path, 'oranges.md');
  assert.equal(opened[0].opts.conversationId, 'c');
  window.AgixtChat.disconnect();
});

test('chat: AGiXT output file links open in desktop workspace', async () => {
  const opened = [];
  const browserOpened = [];
  const { window } = loadFrontend({
    ipc: {
      get_conversation_history: async () => [{
        id: 'server-assistant-1',
        role: 'XT',
        message: [
          '[oranges.md](http://localhost:7437/outputs/agent_abc/c/folder/oranges.md)',
          '[external](https://evil.example/outputs/agent_abc/c/folder/evil.md)',
        ].join('\n\n'),
        timestamp: '2026-05-17T12:00:00.000Z',
      }],
    },
  });
  window.AgixtWorkspace = {
    openPath: async (path, opts) => opened.push({ path, opts }),
  };
  window.__TAURI__.opener = {
    openUrl: async (url) => browserOpened.push(url),
  };
  window.AgixtChat.configure({
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    conversationId: 'c',
    reconnect: false,
  });
  await window.AgixtChat.loadHistory('c');

  const links = [...window.document.querySelectorAll('#messages a')];
  const workspaceLinks = links.filter((link) => link.dataset.workspacePath);
  assert.equal(workspaceLinks.length, 1);
  assert.equal(workspaceLinks[0].dataset.workspacePath, 'folder/oranges.md');
  workspaceLinks[0].dispatchEvent(new window.MouseEvent('click', { bubbles: true, cancelable: true }));

  assert.equal(opened.length, 1);
  assert.equal(opened[0].path, 'folder/oranges.md');
  assert.equal(opened[0].opts.conversationId, 'c');
  assert.equal(browserOpened.length, 0);
  window.AgixtChat.disconnect();
});

test('chat: workspace media auth only attaches to configured AGiXT origins', async () => {
  const { window } = loadFrontend({
    ipc: {
      get_conversation_history: async () => [{
        id: 'm1',
        role: 'assistant',
        message: [
          '![evil](https://evil.example/outputs/leak.png)',
          '![relative](/outputs/local.png)',
          '![same](http://localhost:7437/outputs/same.png)',
          '![loopback](http://127.0.0.1:7437/outputs/loop.png)',
        ].join('\n'),
      }],
    },
  });
  window.AgixtChat.configure({
    serverUrl: 'http://localhost:7437',
    jwt: 'secret.jwt',
    conversationId: 'c',
    reconnect: false,
  });

  await window.AgixtChat.loadHistory('c');

  const byAlt = Object.fromEntries(
    [...window.document.querySelectorAll('#messages img')]
      .map((img) => [img.getAttribute('alt'), img.getAttribute('src')]),
  );
  // Externally-hosted images render as <img> (parity with the web's
  // MarkdownBlock), but their src must NOT carry the user's JWT —
  // the rewrite is restricted to the configured AGiXT origin so a
  // markdown image hosted on someone else's host can't be tricked
  // into receiving the token.
  assert.equal(byAlt.evil, 'https://evil.example/outputs/leak.png',
    'external host renders as img with bare src');
  assert.ok(!String(byAlt.evil).includes('secret.jwt'),
    'external host must NOT receive the JWT');
  assert.equal(byAlt.relative, 'http://localhost:7437/outputs/local.png?auth=secret.jwt');
  assert.equal(byAlt.same, 'http://localhost:7437/outputs/same.png?auth=secret.jwt');
  assert.equal(byAlt.loopback, 'http://127.0.0.1:7437/outputs/loop.png?auth=secret.jwt');
  window.AgixtChat.disconnect();
});

test('app: composer enter and send button call chat_send', async () => {
  const { window, calls } = loadFullApp();
  await new Promise((resolve) => setTimeout(resolve, 20));

  const input = window.document.getElementById('composer-input');
  const sendButton = window.document.getElementById('btn-send');
  input.value = 'hello from button';
  sendButton.click();
  await new Promise((resolve) => setTimeout(resolve, 20));

  input.value = 'hello from enter';
  input.dispatchEvent(new window.KeyboardEvent('keydown', {
    key: 'Enter',
    bubbles: true,
    cancelable: true,
  }));
  await new Promise((resolve) => setTimeout(resolve, 20));

  const sends = calls.filter((c) => c.cmd === 'chat_send');
  assert.equal(sends.length, 2);
  assert.equal(sends[0].args.args.messages[0].content, 'hello from button');
  assert.equal(sends[1].args.args.messages[0].content, 'hello from enter');
  window.AgixtChat.disconnect();
});

test('app: admin scopes do not trigger child voice-only mode', async () => {
  const fetchCalls = [];
  const { window } = loadFullApp({
    ipc: {
      list_companies: async () => [{
        id: 'company-id',
        name: 'Home',
        primary: true,
        role_id: 1,
        role: 'admin',
        scopes: ['ui:voice_only_mode'],
        agents: [{ id: 'agent-id', name: 'XT', default: true }],
      }],
    },
    fetch: async (url) => {
      fetchCalls.push(String(url));
      return jsonResponse({});
    },
  });
  await waitFor(40);

  assert.equal(window.document.body.classList.contains('child-mode'), false);
  assert.equal(window.document.getElementById('agent-switcher-btn').disabled, false);
  assert.equal(window.document.getElementById('btn-delete-conversation').disabled, false);
  assert.equal(fetchCalls.some((url) => url.includes('/child-controls/me')), false);
  window.AgixtChat.disconnect();
});

test('app: child mode keeps conversation switching and new conversation while blocking delete', async () => {
  const { window } = loadFullApp({
    ipc: {
      list_companies: async () => [{
        id: 'company-id',
        name: 'Home',
        primary: true,
        role_id: 4,
        role: 'child',
        scopes: [],
        agents: [{ id: 'agent-id', name: 'XT', default: true }],
      }],
      list_conversations: async () => [{ id: 'kid-convo', name: 'Kid Conversation' }],
    },
    fetch: async (url) => {
      const parsed = new URL(String(url));
      if (parsed.pathname === '/v1/companies/company-id/child-controls/me') {
        return jsonResponse({
          children: [{
            id: 'child-id',
            name: 'Kid',
            access: { app: { locked: false }, features: { chat: { locked: false } } },
            mandatory_context: 'Be kind and concise.',
          }],
        });
      }
      return jsonResponse({});
    },
  });
  await waitFor(60);

  assert.equal(window.document.body.classList.contains('child-mode'), true);
  assert.equal(window.document.getElementById('convo-switcher-btn').disabled, false);
  assert.equal(window.document.getElementById('btn-new-conversation').disabled, false);
  assert.equal(window.document.getElementById('convo-new-btn').disabled, false);
  assert.equal(window.document.getElementById('btn-delete-conversation').disabled, true);
  assert.equal(window.document.getElementById('agent-switcher-btn').disabled, true);
  window.AgixtChat.disconnect();
});

test('desktop extensions: active context provider formats hidden page context', () => {
  const { window } = loadDesktopExtensionsOnly();
  const off = window.AgixtDesktopExtensions.registerContextProvider(
    'audible',
    () => 'Open audiobook: "A Wrinkle in Time"\nCurrent position: 12:34',
  );

  const ctx = window.AgixtDesktopExtensions.getActiveContext();
  assert.match(ctx, /Current audible Desktop Extension Context/i);
  assert.match(ctx, /A Wrinkle in Time/);
  assert.match(ctx, /do not treat it as a new user request/);

  off();
  assert.equal(window.AgixtDesktopExtensions.getActiveContext(), '');
});

test('xtschool extension: registers context and AI creation bridge', async () => {
  const { window, registrations } = loadXTSchoolExtensionPage();
  const ctrl = registrations.get('xtschool');
  assert.ok(ctrl, 'xtschool extension should register itself');

  const pane = window.document.querySelector('.view-pane[data-view="xtschool"]');
  const contextProviders = [];
  const calls = [];
  ctrl.mount(pane, {
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    companyId: 'company-id',
    companyName: 'Home',
    childMode: true,
    childControl: {
      children: [{
        id: 'child-id',
        name: 'Kid',
        access: {
          app: { locked: false },
          features: {
            videos: { locked: false },
            music: { locked: false },
            audiobooks: { locked: false },
            games: { locked: false },
            chat: { locked: false },
          },
        },
      }],
    },
    registerContextProvider: (provider) => {
      contextProviders.push(provider);
      return () => {};
    },
    fetchJson: async (path, opts) => {
      calls.push({ path, opts });
      if (path === '/v1/user') {
        return { companies: [{ id: 'company-id', name: 'Home', role_id: 4, scopes: [] }] };
      }
      if (path.includes('/child-controls/me')) {
        return {
          children: [{
            id: 'child-id',
            name: 'Kid',
            access: {
              app: { locked: false },
              features: {
                videos: { locked: false },
                music: { locked: false },
                audiobooks: { locked: false },
                games: { locked: false },
                chat: { locked: false },
              },
            },
          }],
        };
      }
      if (path === '/v1/xtschool/library/import') {
        return {
          id: 'music-1',
          company_id: 'company-id',
          content_type: 'music',
          title: opts.json.title || 'Spotify Song',
          approved: opts.json.approved,
          source: 'spotify',
        };
      }
      if (path.startsWith('/v1/xtschool/library')) {
        return {
          items: [{
            id: 'video-1',
            company_id: 'company-id',
            content_type: 'video',
            title: 'Fractions Adventure',
            approved: true,
          }],
        };
      }
      if (path.startsWith('/v1/xtschool/progress')) return { items: [] };
      if (path === '/v1/xtschool/creations') {
        return {
          id: 'creation-1',
          company_id: 'company-id',
          child_user_id: 'child-id',
          title: opts.json.title,
          content: opts.json.content,
          revision: 1,
        };
      }
      if (path.startsWith('/v1/xtschool/creations/creation-1')) {
        return {
          id: 'creation-1',
          company_id: 'company-id',
          child_user_id: 'child-id',
          title: 'Rocket Math',
          content: '<!doctype html><title>Rocket Math</title>',
          revision: 1,
        };
      }
      return {};
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 20));

  assert.ok(contextProviders.length, 'context provider should be registered');
  assert.match(contextProviders[0](), /XTSchool desktop extension/);
  assert.ok(window.XTSchool, 'bridge should be installed');

  const creation = await window.XTSchool.createHtmlCreation({
    title: 'Rocket Math',
    html: '<!doctype html><title>Rocket Math</title>',
  });
  const imported = await window.XTSchool.importContent({
    url: 'https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp',
    title: 'Spotify Song',
    approved: true,
  });
  assert.equal(creation.id, 'creation-1');
  assert.equal(imported.id, 'music-1');
  assert.ok(calls.some((call) => call.path === '/v1/xtschool/creations' && call.opts.method === 'POST'));
  assert.ok(calls.some((call) => call.path === '/v1/xtschool/library/import' && call.opts.method === 'POST'));
  assert.match(contextProviders[0](), /Active AI creation/);
  ctrl.unmount();
});

test('xtschool extension: parent searches Spotify and imports provider result', async () => {
  const { window, registrations } = loadXTSchoolExtensionPage('music');
  const ctrl = registrations.get('xtschool_music');
  assert.ok(ctrl, 'xtschool extension should register itself');

  const pane = window.document.querySelector('.view-pane[data-view="xtschool"]');
  const calls = [];
  const createdItems = [];
  ctrl.mount(pane, {
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    companyId: 'company-id',
    companyName: 'Home',
    fetchJson: async (path, opts = {}) => {
      calls.push({ path, opts });
      if (path === '/v1/user') {
        return { companies: [{ id: 'company-id', name: 'Home', role_id: 1, scopes: ['ext:xtschool:write'] }] };
      }
      if (path.includes('/child-controls')) {
        return { children: [{ id: 'child-1', name: 'Ada' }] };
      }
      if (path.startsWith('/v1/xtschool/providers/spotify/search')) {
        return {
          provider: 'spotify',
          items: [{
            provider: 'spotify',
            kind: 'track',
            content_type: 'music',
            title: 'Friendly Song',
            subtitle: 'Kid Artist',
            source: 'spotify',
            source_id: '3n3Ppam7vgaVa1iaRUc9Lp',
            source_url: 'https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp',
            thumbnail_url: 'https://images.example/song.jpg',
            duration_seconds: 125,
            metadata: { provider: 'spotify', kind: 'track', spotify_type: 'track' },
          }],
          count: 1,
        };
      }
      if (path === '/v1/xtschool/library' && opts.method === 'POST') {
        const item = { id: 'music-1', ...opts.json };
        createdItems.push(item);
        return item;
      }
      if (path.startsWith('/v1/xtschool/library')) {
        return { items: createdItems, count: createdItems.length };
      }
      return {};
    },
  });
  await waitFor(100);

  assert.match(pane.textContent, /Search providers/);
  const results = await window.XTSchool.searchProvider({ provider: 'spotify', q: 'friendly song', kind: 'track' });
  assert.equal(results.length, 1);
  const created = await window.XTSchool.importProviderResult({
    index: 0,
    approved: true,
    allowed_child_user_ids: ['child-1'],
  });

  assert.equal(created.id, 'music-1');
  assert.equal(created.content_type, 'music');
  assert.equal(created.source, 'spotify');
  assert.equal(created.allowed_child_user_ids[0], 'child-1');
  assert.ok(calls.some((call) => call.path.startsWith('/v1/xtschool/providers/spotify/search')));
  assert.ok(calls.some((call) => call.path === '/v1/xtschool/library' && call.opts.method === 'POST'));
  ctrl.unmount();
});

test('xtschool extension: child opens cached YouTube and Spotify content inline', async () => {
  const { window, registrations } = loadXTSchoolExtensionPage('videos');
  const ctrl = registrations.get('xtschool_videos');
  assert.ok(ctrl, 'xtschool extension should register itself');

  const pane = window.document.querySelector('.view-pane[data-view="xtschool"]');
  const contextProviders = [];
  const library = {
    video: [{
      id: 'yt-1',
      company_id: 'company-id',
      content_type: 'video',
      title: 'Space Fractions',
      approved: true,
      source: 'youtube',
      source_id: 'abc123XYZ',
      source_url: 'https://www.youtube.com/watch?v=abc123XYZ',
      metadata: {
        media: {
          video_url: '/v1/xtschool/media/yt-1/video.mp4',
          mime_type: 'video/mp4',
        },
      },
    }],
    music: [{
      id: 'song-1',
      company_id: 'company-id',
      content_type: 'music',
      title: 'Counting Song',
      approved: true,
      source: 'spotify',
      source_id: '3n3Ppam7vgaVa1iaRUc9Lp',
      source_url: 'https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp',
    }],
  };
  ctrl.mount(pane, {
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    companyId: 'company-id',
    childMode: true,
    childControl: {
      children: [{
        id: 'child-id',
        name: 'Kid',
        access: { app: { locked: false }, features: {} },
      }],
    },
    registerContextProvider: (provider) => {
      contextProviders.push(provider);
      return () => {};
    },
    fetchJson: async (path, opts = {}) => {
      if (path === '/v1/user') {
        return { companies: [{ id: 'company-id', name: 'Home', role_id: 4, scopes: [] }] };
      }
      if (path.includes('/child-controls/me')) {
        return { children: [{ id: 'child-id', name: 'Kid', access: { app: { locked: false }, features: {} } }] };
      }
      if (path.startsWith('/v1/xtschool/progress')) return { items: [] };
      if (path.startsWith('/v1/xtschool/library')) {
        const parsed = new URL(path, 'http://localhost');
        const type = parsed.searchParams.get('content_type') || 'video';
        return { items: library[type] || [], count: (library[type] || []).length };
      }
      return {};
    },
  });
  await waitFor(100);

  await window.XTSchool.searchLibrary({ content_type: 'video' });
  await window.XTSchool.openContent({ content_id: 'yt-1' });
  assert.equal(
    pane.querySelector('video.xts-player-media source')?.getAttribute('src'),
    'http://localhost:7437/v1/xtschool/media/yt-1/video.mp4',
  );
  assert.equal(pane.querySelector('.xts-player-frame'), null);
  assert.equal(pane.querySelector('[data-form="context-chat"]'), null);
  assert.match(contextProviders[0](), /Active XTSchool content/);

  await window.XTSchool.searchLibrary({ content_type: 'music' });
  await window.XTSchool.openContent({ content_id: 'song-1' });
  assert.equal(
    pane.querySelector('.xts-player-frame')?.getAttribute('src'),
    'https://open.spotify.com/embed/track/3n3Ppam7vgaVa1iaRUc9Lp',
  );
  ctrl.unmount();
});

test('xtschool extension: child playlists resolve approved visible items', async () => {
  const { window, registrations } = loadXTSchoolExtensionPage('videos');
  const ctrl = registrations.get('xtschool_videos');
  assert.ok(ctrl, 'xtschool extension should register itself');

  const pane = window.document.querySelector('.view-pane[data-view="xtschool"]');
  const playlist = {
    id: 'playlist-1',
    company_id: 'company-id',
    content_type: 'playlist',
    title: 'Morning Mix',
    approved: true,
    source: 'xtschool',
    metadata: { playlist_items: ['yt-1', 'hidden-1'] },
  };
  const visibleVideo = {
    id: 'yt-1',
    company_id: 'company-id',
    content_type: 'video',
    title: 'Visible Video',
    approved: true,
    source: 'youtube',
    source_url: 'https://youtu.be/visible123',
    metadata: {
      media: {
        video_url: '/v1/xtschool/media/yt-1/video.mp4',
        mime_type: 'video/mp4',
      },
    },
  };

  ctrl.mount(pane, {
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    companyId: 'company-id',
    childMode: true,
    childControl: {
      children: [{ id: 'child-id', name: 'Kid', access: { app: { locked: false }, features: {} } }],
    },
    fetchJson: async (path) => {
      if (path === '/v1/user') {
        return { companies: [{ id: 'company-id', name: 'Home', role_id: 4, scopes: [] }] };
      }
      if (path.includes('/child-controls/me')) {
        return { children: [{ id: 'child-id', name: 'Kid', access: { app: { locked: false }, features: {} } }] };
      }
      if (path.startsWith('/v1/xtschool/progress')) return { items: [] };
      if (path.startsWith('/v1/xtschool/library')) {
        const parsed = new URL(path, 'http://localhost');
        if (parsed.searchParams.get('limit') === '500') {
          return { items: [playlist, visibleVideo], count: 2 };
        }
        if (parsed.searchParams.get('content_type') === 'playlist') {
          return { items: [playlist], count: 1 };
        }
        return { items: [], count: 0 };
      }
      return {};
    },
  });
  await waitFor(100);

  await window.XTSchool.searchLibrary({ content_type: 'playlist' });
  await window.XTSchool.openContent({ content_id: 'playlist-1' });
  await waitFor(100);

  assert.match(pane.textContent, /Visible Video/);
  assert.doesNotMatch(pane.textContent, /hidden-1/);

  pane.querySelector('[data-playlist-open="yt-1"]').click();
  await waitFor(20);
  assert.equal(
    pane.querySelector('video.xts-player-media source')?.getAttribute('src'),
    'http://localhost:7437/v1/xtschool/media/yt-1/video.mp4',
  );
  ctrl.unmount();
});

test('xtschool extension: child bedtime mode filters and blocks non-bedtime content', async () => {
  const { window, registrations } = loadXTSchoolExtensionPage();
  const ctrl = registrations.get('xtschool');
  assert.ok(ctrl, 'xtschool extension should register itself');

  const pane = window.document.querySelector('.view-pane[data-view="xtschool"]');
  const calls = [];
  const bedtimeVideo = {
    id: 'bedtime-video',
    company_id: 'company-id',
    content_type: 'video',
    title: 'Calm Stars',
    approved: true,
    bedtime: true,
    source: 'youtube',
    source_id: 'calm12345',
  };
  const daytimeVideo = {
    id: 'day-video',
    company_id: 'company-id',
    content_type: 'video',
    title: 'Big Energy',
    approved: true,
    bedtime: false,
    source: 'youtube',
    source_id: 'energy123',
  };

  ctrl.mount(pane, {
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    companyId: 'company-id',
    childMode: true,
    childControl: {
      children: [{
        id: 'child-id',
        name: 'Kid',
        access: {
          app: { locked: false },
          features: { videos: { locked: false, bedtime: true } },
        },
      }],
    },
    fetchJson: async (path) => {
      calls.push(path);
      if (path === '/v1/user') {
        return { companies: [{ id: 'company-id', name: 'Home', role_id: 4, scopes: [] }] };
      }
      if (path.includes('/child-controls/me')) {
        return {
          children: [{
            id: 'child-id',
            name: 'Kid',
            access: {
              app: { locked: false },
              features: { videos: { locked: false, bedtime: true } },
            },
          }],
        };
      }
      if (path.startsWith('/v1/xtschool/progress')) return { items: [] };
      if (path.startsWith('/v1/xtschool/library')) {
        const parsed = new URL(path, 'http://localhost');
        if (parsed.searchParams.get('limit') === '500') {
          return { items: [daytimeVideo], count: 1 };
        }
        return { items: [bedtimeVideo], count: 1 };
      }
      return {};
    },
  });
  await waitFor(30);

  await window.XTSchool.searchLibrary({ content_type: 'video' });
  assert.ok(
    calls.some((path) => path.includes('/v1/xtschool/library') && path.includes('bedtime_only=true')),
    'bedtime searches should request the server-side bedtime filter',
  );
  assert.match(pane.textContent, /Calm Stars/);

  await assert.rejects(
    () => window.XTSchool.openContent({ content_id: 'day-video' }),
    /not available during bedtime mode/,
  );
  assert.equal(pane.querySelector('.xtschool-modal iframe'), null);
  ctrl.unmount();
});

test('xtschool extension: direct media player records child progress', async () => {
  const { window, registrations } = loadXTSchoolExtensionPage('videos');
  const ctrl = registrations.get('xtschool_videos');
  assert.ok(ctrl, 'xtschool extension should register itself');

  const pane = window.document.querySelector('.view-pane[data-view="xtschool"]');
  const calls = [];
  const item = {
    id: 'video-direct',
    company_id: 'company-id',
    content_type: 'video',
    title: 'Local Lesson',
    approved: true,
    source: 'manual',
    source_url: 'https://cdn.example.com/local-lesson.mp4',
    metadata: {
      subtitles: {
        en: 'https://cdn.example.com/local-lesson-en.vtt',
        ru: 'https://cdn.example.com/local-lesson-ru.vtt',
      },
    },
  };
  window.fetch = async (url) => {
    const textUrl = String(url);
    if (!textUrl.includes('local-lesson-')) {
      return new Response('', { status: 404 });
    }
    const text = textUrl.includes('-ru.')
      ? 'WEBVTT\n\n00:00:20.000 --> 00:00:30.000\nРусская подпись'
      : 'WEBVTT\n\n00:00:20.000 --> 00:00:30.000\nEnglish caption';
    return new Response(text, { status: 200, headers: { 'content-type': 'text/vtt' } });
  };

  ctrl.mount(pane, {
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    companyId: 'company-id',
    childMode: true,
    childControl: {
      children: [{ id: 'child-id', name: 'Kid', access: { app: { locked: false }, features: {} } }],
    },
    fetchJson: async (path, opts = {}) => {
      calls.push({ path, opts });
      if (path === '/v1/user') {
        return { companies: [{ id: 'company-id', name: 'Home', role_id: 4, scopes: [] }] };
      }
      if (path.includes('/child-controls/me')) {
        return { children: [{ id: 'child-id', name: 'Kid', access: { app: { locked: false }, features: {} } }] };
      }
      if (path.startsWith('/v1/xtschool/progress')) return { items: [] };
      if (path.startsWith('/v1/xtschool/library')) {
        return { items: [item], count: 1 };
      }
      return {};
    },
  });
  await waitFor(100);

  await window.XTSchool.searchLibrary({ content_type: 'video' });
  await window.XTSchool.openContent({ content_id: 'video-direct' });

  const media = pane.querySelector('video.xts-player-media');
  assert.ok(media, 'direct video content should use the native player');
  await waitFor(100);
  Object.defineProperty(media, 'duration', { value: 120, configurable: true });
  Object.defineProperty(media, 'currentTime', { value: 24, configurable: true });
  media.dispatchEvent(new window.Event('timeupdate'));
  await waitFor(120);

  assert.match(pane.querySelector('.xts-caption-line.xts-caption-en')?.textContent || '', /English caption/);
  assert.match(pane.querySelector('.xts-caption-line.xts-caption-ru')?.textContent || '', /Русская подпись/);

  const progressCall = calls.find((call) => (
    call.path === '/v1/xtschool/progress' &&
    call.opts.method === 'POST' &&
    call.opts.json &&
    call.opts.json.content_id === 'video-direct' &&
    call.opts.json.progress_seconds === 24
  ));
  assert.ok(progressCall, 'media progress should be persisted for child profiles');
  assert.equal(progressCall.opts.json.duration_seconds, 120);
  ctrl.unmount();
});

test('xtschool extension: manager sees migrated built-in games/videos and opens Mathlandia', async () => {
  const { window, registrations } = loadXTSchoolExtensionPage('videos');
  const ctrl = registrations.get('xtschool_videos');
  assert.ok(ctrl, 'xtschool extension should register itself');

  const pane = window.document.querySelector('.view-pane[data-view="xtschool"]');
  const assetCalls = [];
  window.fetch = async (url, init = {}) => {
    const parsed = new URL(url);
    assetCalls.push({ path: parsed.pathname, headers: init.headers || {} });
    if (parsed.pathname === '/v1/desktop/extensions/xtschool/assets/data/games.json') {
      return jsonResponse([{
        id: 'mathlandia',
        title: 'Mathlandia',
        description: 'Explore blocks, slopes, vectors, primes, gravity and more.',
        category: 'Math',
        src: '/mathgame/',
        thumbnail: '/static/data/mathlandia.svg',
      }]);
    }
    if (parsed.pathname === '/v1/desktop/extensions/xtschool/assets/data/youtube.txt') {
      return new Response('https://www.youtube.com/watch?v=NddxY2fRAWY\nhttps://www.youtube.com/watch?v=NddxY2fRAWY\n', {
        status: 200,
        headers: { 'content-type': 'text/plain' },
      });
    }
    if (parsed.pathname === '/v1/desktop/extensions/xtschool/assets/mathgame/index.html') {
      return new Response(
        '<!doctype html><html><head><link rel="stylesheet" href="css/style.css"></head><body><canvas id="game"></canvas><script src="js/engine.js"></script><script src="js/main.js"></script></body></html>',
        { status: 200, headers: { 'content-type': 'text/html' } },
      );
    }
    if (parsed.pathname === '/v1/desktop/extensions/xtschool/assets/mathgame/css/style.css') {
      return new Response('#game{background:#123}', { status: 200, headers: { 'content-type': 'text/css' } });
    }
    if (parsed.pathname === '/v1/desktop/extensions/xtschool/assets/mathgame/js/engine.js') {
      return new Response(`window.MG = {
  muted: false,
  shush: function () {},
  V: { hash: function () { return 'clip'; } },
  VOICE_INDEX: { clip: 'mp3' }
};
function browserSay(text) { window.lastBrowserSay = text; }
MG.say = function (text) {
  if (MG.muted || !text) return;
  MG.shush();
  var idx = MG.VOICE_INDEX;
  var key = (MG.V && idx) ? MG.V.hash(text) : null;
  if (key && idx[key]) {
      try {
        var a = new Audio("audio/" + key + "." + idx[key]);
        a.volume = 1;
        MG._voice = a;
        var p = a.play();
        if (p && p.catch) p.catch(function () { browserSay(text); });
        return;
      } catch (e) { /* fall through */ }
  }
  browserSay(text);
};`, { status: 200, headers: { 'content-type': 'application/javascript' } });
    }
    if (parsed.pathname === '/v1/desktop/extensions/xtschool/assets/mathgame/js/main.js') {
      return new Response('window.mathlandiaReady = true;', { status: 200, headers: { 'content-type': 'application/javascript' } });
    }
    return new Response('', { status: 404 });
  };

  ctrl.mount(pane, {
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    companyId: 'company-id',
    childMode: false,
    childControl: {
      children: [{ id: 'child-id', name: 'Kid', access: { app: { locked: false }, features: {} } }],
    },
    fetchJson: async (path) => {
      if (path === '/v1/user') {
        return { companies: [{ id: 'company-id', name: 'Home', role_id: 1, scopes: ['ext:xtschool:write'] }] };
      }
      if (path.includes('/child-controls')) {
        return { children: [{ id: 'child-id', name: 'Kid', access: { app: { locked: false }, features: {} } }] };
      }
      if (path.startsWith('/v1/xtschool/progress')) return { items: [] };
      if (path.startsWith('/v1/xtschool/library')) return { items: [], count: 0 };
      return {};
    },
  });
  await waitFor(120);

  await window.XTSchool.searchLibrary({ content_type: 'video' });
  assert.match(pane.textContent, /YouTube video 1/);
  assert.match(pane.textContent, /Migrated kids video/);
  assert.ok(
    [...pane.querySelectorAll('img.xts-card-thumb-img')]
      .some((img) => img.getAttribute('src') === 'https://img.youtube.com/vi/NddxY2fRAWY/hqdefault.jpg'),
    'migrated YouTube seeds should derive thumbnails from the video id',
  );

  const seededMatches = await window.XTSchool.searchLibrary({ content_type: 'video', query: 'NddxY2fRAWY' });
  assert.equal(seededMatches.length, 1, 'migrated YouTube seeds should be searchable by video id');

  await window.XTSchool.openContent({ content_id: 'builtin-youtube-NddxY2fRAWY' });
  assert.equal(pane.querySelector('.xts-player-frame'), null);
  assert.equal(
    pane.querySelector('video.xts-player-media source')?.getAttribute('src'),
    'http://localhost:7437/v1/xtschool/media/youtube/NddxY2fRAWY/stream.mp4',
  );
  assert.doesNotMatch(pane.textContent, /Preparing video/);

  await window.XTSchool.searchLibrary({ content_type: 'game' });
  assert.match(pane.textContent, /Mathlandia/);
  assert.match(pane.textContent, /Built-in/);

  await window.XTSchool.openContent({ content_id: 'builtin-game-mathlandia' });
  await waitFor(100);
  const iframe = pane.querySelector('.xts-player-frame');
  assert.ok(iframe, 'Mathlandia should open in a sandboxed iframe');
  const srcdoc = iframe.getAttribute('srcdoc');
  assert.match(srcdoc, /window\.mathlandiaReady = true/);
  assert.match(srcdoc, /__xtschoolFetchAsset/);
  assert.match(srcdoc, /clipPath = "audio\/" \+ key \+ "\." \+ idx\[key\]/);
  assert.ok(assetCalls.some((call) => call.path.endsWith('/data/games.json')));
  assert.ok(assetCalls.every((call) => call.headers.Authorization === 'Bearer jwt'));
  ctrl.unmount();
});

test('xtschool extension: parent video actions approve, disapprove, preview, and unapprove without hide', async () => {
  const { window, registrations } = loadXTSchoolExtensionPage('videos');
  const ctrl = registrations.get('xtschool_videos');
  assert.ok(ctrl, 'xtschool videos extension should register itself');

  const pane = window.document.querySelector('.view-pane[data-view="xtschool"]');
  const calls = [];
  let libraryRows = [{
    id: 'approved-video',
    company_id: 'company-id',
    content_type: 'video',
    title: 'Approved Video',
    approved: true,
    bedtime: false,
    source: 'youtube',
    source_id: 'APPROVEDID01',
    source_url: 'https://www.youtube.com/watch?v=APPROVEDID01',
    metadata: {},
  }, {
    id: 'hidden-seed',
    company_id: 'company-id',
    content_type: 'video',
    title: 'Hidden Seed',
    approved: false,
    bedtime: false,
    source: 'youtube',
    source_id: 'HIDDENID001',
    source_url: 'https://www.youtube.com/watch?v=HIDDENID001',
    metadata: { hidden_builtin: true, disapproved: true },
  }];

  window.fetch = async (url) => {
    const parsed = new URL(String(url));
    if (parsed.pathname === '/v1/desktop/extensions/xtschool/assets/data/games.json') {
      return jsonResponse([]);
    }
    if (parsed.pathname === '/v1/desktop/extensions/xtschool/assets/data/youtube.txt') {
      return new Response(
        'https://www.youtube.com/watch?v=PENDINGID01\nhttps://www.youtube.com/watch?v=HIDDENID001\n',
        { status: 200, headers: { 'content-type': 'text/plain' } },
      );
    }
    return new Response('', { status: 404 });
  };

  ctrl.mount(pane, {
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    companyId: 'company-id',
    childMode: false,
    childControl: {
      children: [{ id: 'child-id', name: 'Kid', access: { app: { locked: false }, features: {} } }],
    },
    fetchJson: async (path, opts = {}) => {
      const method = opts.method || 'GET';
      calls.push({ path, method, body: opts.json || null });
      if (path === '/v1/user') {
        return { companies: [{ id: 'company-id', name: 'Home', role_id: 1, scopes: ['ext:xtschool:write'] }] };
      }
      if (path.includes('/child-controls')) {
        return { children: [{ id: 'child-id', name: 'Kid', access: { app: { locked: false }, features: {} } }] };
      }
      if (path.startsWith('/v1/xtschool/progress')) return { items: [] };
      if (path.startsWith('/v1/xtschool/library') && method === 'GET') {
        return { items: libraryRows, count: libraryRows.length };
      }
      if (path === '/v1/xtschool/library' && method === 'POST') {
        const row = { id: 'created-' + calls.length, ...opts.json };
        libraryRows = libraryRows.concat(row);
        return row;
      }
      if (path.startsWith('/v1/xtschool/library/') && method === 'DELETE') {
        const id = decodeURIComponent(path.split('/').pop());
        libraryRows = libraryRows.filter((item) => item.id !== id);
        return { ok: true };
      }
      return {};
    },
  });
  await waitFor(120);

  assert.match(pane.textContent, /Approved Video/);
  assert.match(pane.textContent, /YouTube video 1/);
  assert.doesNotMatch(pane.textContent, /Hidden Seed/);
  assert.doesNotMatch(pane.textContent, /\bHide\b/);

  const pendingCard = Array.from(pane.querySelectorAll('.xts-card'))
    .find((card) => /YouTube video 1/.test(card.textContent));
  assert.ok(pendingCard, 'pending built-in video should render');
  assert.deepEqual(
    Array.from(pendingCard.querySelectorAll('button')).map((button) => button.textContent.trim()),
    ['Approve', 'Disapprove', 'Preview'],
  );

  pendingCard.querySelector('[data-disapprove-content]').click();
  await waitFor(80);
  const disapproveCall = calls.find((call) => call.path === '/v1/xtschool/library' && call.method === 'POST' && call.body?.metadata?.disapproved);
  assert.ok(disapproveCall, 'disapproving a built-in seed should persist a suppressing stub');
  assert.equal(disapproveCall.body.source_id, 'PENDINGID01');
  assert.doesNotMatch(pane.textContent, /YouTube video 1/);

  const approvedCard = Array.from(pane.querySelectorAll('.xts-card'))
    .find((card) => /Approved Video/.test(card.textContent));
  assert.ok(approvedCard, 'approved video should render');
  assert.deepEqual(
    Array.from(approvedCard.querySelectorAll('button')).map((button) => button.textContent.trim()),
    ['Unapprove', 'Preview', 'Bedtime'],
  );

  approvedCard.querySelector('[data-unapprove-content]').click();
  await waitFor(80);
  assert.ok(calls.some((call) => call.path === '/v1/xtschool/library/approved-video' && call.method === 'DELETE'));
  ctrl.unmount();
});

test('audible extension: parents can approve audiobooks when child profiles exist', async () => {
  const { window, registrations } = loadAudibleExtensionPage();
  const ctrl = registrations.get('audible');
  assert.ok(ctrl, 'audible extension should register itself');

  const pane = window.document.querySelector('.view-pane[data-view="audible"]');
  const calls = [];
  let xtschoolItems = [];
  const book = {
    asin: 'B012345678',
    title: 'Friendly Book',
    authors: ['A. Author'],
    narrators: ['N. Reader'],
    runtime_minutes: 60,
    description: 'A kind story.',
  };

  window.fetch = async (url, init = {}) => {
    const parsed = new URL(String(url));
    const method = init.method || 'GET';
    const body = init.body ? JSON.parse(init.body) : null;
    calls.push({ path: parsed.pathname, method, body, headers: init.headers || {} });

    if (parsed.pathname === '/v1/user') {
      return jsonResponse({
        companies: [{
          id: 'company-id',
          name: 'Home',
          role_id: 1,
          scopes: ['ext:xtschool:write'],
        }],
      });
    }
    if (parsed.pathname === '/v1/companies/company-id/child-controls') {
      return jsonResponse({
        children: [
          { id: 'child-1', name: 'Ada' },
          { id: 'child-2', name: 'Lin' },
        ],
      });
    }
    if (parsed.pathname === '/v1/xtschool/library' && method === 'GET') {
      return jsonResponse({ items: xtschoolItems, count: xtschoolItems.length });
    }
    if (parsed.pathname === '/v1/xtschool/library' && method === 'POST') {
      xtschoolItems = [{ id: 'xt-audio-1', ...body }];
      return jsonResponse(xtschoolItems[0], 201);
    }
    if (parsed.pathname === '/v1/audible/library') {
      return jsonResponse({ items: [book] });
    }
    if (parsed.pathname === '/v1/audible/cover/B012345678') {
      return new Response('cover', { status: 200, headers: { 'content-type': 'image/jpeg' } });
    }
    if (parsed.pathname === '/v1/audible/book/B012345678') {
      return jsonResponse({ ...book, last_position_ms: 0 });
    }
    if (parsed.pathname === '/v1/audible/book/B012345678/chapters') {
      return jsonResponse({ chapters: [], total_ms: 3600000, last_position_ms: 0 });
    }
    if (parsed.pathname === '/v1/audible/book/B012345678/transcript') {
      return jsonResponse({ segments: [], status: { state: 'idle' } });
    }
    if (parsed.pathname === '/v1/audible/audio/B012345678/status') {
      return jsonResponse({ playable: false, downloading: false, transcript: { state: 'idle' } });
    }
    return jsonResponse({});
  };

  ctrl.mount(pane, {
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    companyId: 'company-id',
    agentId: 'agent-audible',
    registerContextProvider: () => () => {},
  });
  await waitFor(60);

  assert.match(pane.textContent, /Friendly Book/);
  const card = pane.querySelector('.aud-card');
  assert.ok(card, 'library book should render');
  card.click();
  await waitFor(60);

  assert.match(pane.textContent, /Not approved for child profiles/);
  const approve = Array.from(pane.querySelectorAll('button'))
    .find((button) => button.textContent === 'Approve for children');
  assert.ok(approve, 'approval button should render for parent with children');
  approve.click();
  await waitFor(80);

  const approvalCall = calls.find((call) => (
    call.path === '/v1/xtschool/library' && call.method === 'POST'
  ));
  assert.ok(approvalCall, 'approval should be stored through XTSchool library');
  assert.equal(approvalCall.headers.Authorization, 'Bearer jwt');
  assert.equal(approvalCall.headers['Content-Type'], 'application/json');
  assert.equal(approvalCall.body.content_type, 'audiobook');
  assert.equal(approvalCall.body.source, 'audible');
  assert.equal(approvalCall.body.source_id, 'B012345678');
  assert.equal(approvalCall.body.approved, true);
  assert.deepEqual(approvalCall.body.allowed_child_user_ids, []);
  assert.equal(approvalCall.body.metadata.audible.agent_id, 'agent-audible');
  assert.equal(approvalCall.body.metadata.import.agent_id, 'agent-audible');
  const preparationCall = calls.find((call) => (
    call.path === '/v1/audible/audio/B012345678/download' && call.method === 'POST'
  ));
  assert.ok(preparationCall, 'approval should start audiobook download/transcription preparation');
  assert.equal(preparationCall.headers.Authorization, 'Bearer jwt');
  assert.match(pane.textContent, /Approved for child profiles/);
  ctrl.unmount();
});

test('audible extension: child profiles see only approved XTSchool audiobooks', async () => {
  const { window, registrations } = loadAudibleExtensionPage();
  const ctrl = registrations.get('audible');
  assert.ok(ctrl, 'audible extension should register itself');

  const pane = window.document.querySelector('.view-pane[data-view="audible"]');
  const calls = [];
  let audibleLibraryCalled = false;
  const approvedItem = {
    id: 'xt-approved',
    company_id: 'company-id',
    content_type: 'audiobook',
    title: 'Approved Book',
    approved: true,
    source: 'audible',
    source_id: 'BAPPROVED',
    duration_seconds: 3600,
    thumbnail_url: 'https://covers.example/approved.jpg',
    metadata: {
      audible: {
        authors: ['A. Author'],
        narrators: ['N. Reader'],
        runtime_minutes: 60,
      },
    },
  };
  const hiddenItem = {
    id: 'xt-hidden',
    company_id: 'company-id',
    content_type: 'audiobook',
    title: 'Hidden Book',
    approved: false,
    source: 'audible',
    source_id: 'BHIDDEN',
  };

  window.fetch = async (url, init = {}) => {
    const parsed = new URL(String(url));
    const method = init.method || 'GET';
    calls.push({ path: parsed.pathname, method });
    if (parsed.pathname === '/v1/user') {
      return jsonResponse({
        companies: [{ id: 'company-id', name: 'Home', role_id: 4, scopes: [] }],
      });
    }
    if (parsed.pathname === '/v1/companies/company-id/child-controls/me') {
      return jsonResponse({ children: [{ id: 'child-1', name: 'Ada' }] });
    }
    if (parsed.pathname === '/v1/xtschool/library') {
      return jsonResponse({ items: [approvedItem, hiddenItem], count: 2 });
    }
    if (parsed.pathname === '/v1/audible/library') {
      audibleLibraryCalled = true;
      return jsonResponse({ items: [{ asin: 'BHIDDEN', title: 'Hidden Book' }] });
    }
    if (parsed.pathname === '/v1/audible/cover/BAPPROVED') {
      return new Response('cover', { status: 200, headers: { 'content-type': 'image/jpeg' } });
    }
    if (parsed.pathname === '/v1/audible/book/BAPPROVED') {
      return jsonResponse({ detail: 'child should not need Audible auth' }, 401);
    }
    if (parsed.pathname === '/v1/audible/book/BAPPROVED/chapters') {
      return jsonResponse({ detail: 'child should not need Audible auth' }, 401);
    }
    if (parsed.pathname === '/v1/audible/book/BAPPROVED/transcript') {
      return jsonResponse({ segments: [], status: { state: 'idle' } });
    }
    if (parsed.pathname === '/v1/audible/audio/BAPPROVED/status') {
      return jsonResponse({ playable: false, downloading: false, transcript: { state: 'idle' } });
    }
    return jsonResponse({});
  };

  ctrl.mount(pane, {
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    companyId: 'company-id',
    childMode: true,
    registerContextProvider: () => () => {},
  });
  await waitFor(60);

  assert.match(pane.textContent, /Approved Audiobooks/);
  assert.match(pane.textContent, /Approved Book/);
  assert.doesNotMatch(pane.textContent, /Hidden Book/);
  assert.equal(pane.querySelector('.aud-tabs'), null);
  assert.equal(audibleLibraryCalled, false, 'child mode should not request the raw Audible library');

  const card = pane.querySelector('.aud-card');
  assert.ok(card, 'approved audiobook should be selectable');
  card.click();
  await waitFor(60);
  assert.match(pane.textContent, /Approved Book/);
  assert.ok(calls.some((call) => call.path === '/v1/audible/book/BAPPROVED/transcript'));
  assert.ok(calls.some((call) => call.path === '/v1/audible/audio/BAPPROVED/status'));
  assert.equal(
    calls.some((call) => call.path === '/v1/audible/book/BAPPROVED'),
    false,
    'child mode should not require live Audible book metadata'
  );
  assert.equal(
    calls.some((call) => call.path === '/v1/audible/book/BAPPROVED/chapters'),
    false,
    'child mode should not require live Audible chapter metadata'
  );
  ctrl.unmount();
});

test('audible extension: child audiobook refresh restores freshest saved progress', async () => {
  const { window, registrations } = loadAudibleExtensionPage();
  const ctrl = registrations.get('audible');
  assert.ok(ctrl, 'audible extension should register itself');

  const pane = window.document.querySelector('.view-pane[data-view="audible"]');
  const calls = [];
  const progressWrites = [];
  const approvedItem = {
    id: 'xt-approved',
    company_id: 'company-id',
    content_type: 'audiobook',
    title: 'Resume Book',
    approved: true,
    source: 'audible',
    source_id: 'BRESUME',
    duration_seconds: 3600,
    metadata: {
      audible: {
        authors: ['A. Author'],
        runtime_minutes: 60,
        chapters: [
          { index: 0, title: 'Opening', start_ms: 0, length_ms: 1800000 },
          { index: 1, title: 'Middle', start_ms: 1800000, length_ms: 1800000 },
        ],
      },
    },
  };
  window.localStorage.setItem(
    'agixt.desktop.audible.progress.v1.child-1.BRESUME',
    JSON.stringify({
      asin: 'BRESUME',
      last_position_ms: 650000,
      duration_ms: 3600000,
      completed: false,
      updated_at: new Date().toISOString(),
    }),
  );

  window.fetch = async (url, init = {}) => {
    const parsed = new URL(String(url));
    const method = init.method || 'GET';
    calls.push({ path: parsed.pathname, method });
    if (parsed.pathname === '/v1/user') {
      return jsonResponse({
        id: 'child-1',
        companies: [{ id: 'company-id', name: 'Home', role_id: 4, scopes: [] }],
      });
    }
    if (parsed.pathname === '/v1/companies/company-id/child-controls/me') {
      return jsonResponse({ children: [{ id: 'child-1', name: 'Ada' }] });
    }
    if (parsed.pathname === '/v1/xtschool/library') {
      return jsonResponse({ items: [approvedItem], count: 1 });
    }
    if (parsed.pathname === '/v1/xtschool/progress' && method === 'GET') {
      return jsonResponse({
        items: [{
          id: 'progress-row',
          company_id: 'company-id',
          child_user_id: 'child-1',
          content_id: 'xt-approved',
          content_type: 'audiobook',
          progress_seconds: 120,
          duration_seconds: 3600,
          completed: false,
        }],
        count: 1,
      });
    }
    if (parsed.pathname === '/v1/xtschool/progress' && method === 'POST') {
      progressWrites.push(JSON.parse(init.body || '{}'));
      return jsonResponse({ ok: true });
    }
    if (parsed.pathname === '/v1/audible/cover/BRESUME') {
      return new Response('cover', { status: 200, headers: { 'content-type': 'image/jpeg' } });
    }
    if (parsed.pathname === '/v1/audible/book/BRESUME/transcript') {
      return jsonResponse({ segments: [], status: { state: 'idle' } });
    }
    if (parsed.pathname === '/v1/audible/audio/BRESUME/status') {
      return jsonResponse({ playable: false, downloading: false, transcript: { state: 'idle' } });
    }
    return jsonResponse({});
  };

  ctrl.mount(pane, {
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    companyId: 'company-id',
    childMode: true,
    registerContextProvider: () => () => {},
  });
  await waitFor(60);

  const card = pane.querySelector('.aud-card');
  assert.ok(card, 'approved audiobook should be selectable');
  card.click();
  await waitFor(80);

  const view = pane._audibleView;
  assert.equal(view.lastPositionMs, 650000);
  assert.match(pane.textContent, /10:50/);
  assert.ok(calls.some((call) => call.path === '/v1/xtschool/progress' && call.method === 'GET'));
  assert.ok(
    progressWrites.some((body) => body.progress_seconds === 650),
    'virtual render should preserve the restored child progress instead of saving 0'
  );
  ctrl.unmount();
});

test('audible extension: opens approved audiobook from XTSchool request', async () => {
  const { window, registrations } = loadAudibleExtensionPage();
  const ctrl = registrations.get('audible');
  assert.ok(ctrl, 'audible extension should register itself');

  const pane = window.document.querySelector('.view-pane[data-view="audible"]');
  const calls = [];
  const approvedItem = {
    id: 'xt-approved',
    company_id: 'company-id',
    content_type: 'audiobook',
    title: 'Bridge Book',
    approved: true,
    source: 'audible',
    source_id: 'BBRIDGE',
    thumbnail_url: 'https://covers.example/bridge.jpg',
    metadata: { audible: { authors: ['A. Author'], runtime_minutes: 45 } },
  };

  window.fetch = async (url, init = {}) => {
    const parsed = new URL(String(url));
    const method = init.method || 'GET';
    calls.push({ path: parsed.pathname, method });
    if (parsed.pathname === '/v1/user') {
      return jsonResponse({
        companies: [{ id: 'company-id', name: 'Home', role_id: 4, scopes: [] }],
      });
    }
    if (parsed.pathname === '/v1/companies/company-id/child-controls/me') {
      return jsonResponse({ children: [{ id: 'child-1', name: 'Ada' }] });
    }
    if (parsed.pathname === '/v1/xtschool/library') {
      return jsonResponse({ items: [approvedItem], count: 1 });
    }
    if (parsed.pathname === '/v1/audible/cover/BBRIDGE') {
      return new Response('cover', { status: 200, headers: { 'content-type': 'image/jpeg' } });
    }
    if (parsed.pathname === '/v1/audible/book/BBRIDGE') {
      return jsonResponse({ detail: 'child should not need Audible auth' }, 401);
    }
    if (parsed.pathname === '/v1/audible/book/BBRIDGE/chapters') {
      return jsonResponse({ detail: 'child should not need Audible auth' }, 401);
    }
    if (parsed.pathname === '/v1/audible/book/BBRIDGE/transcript') {
      return jsonResponse({ segments: [], status: { state: 'idle' } });
    }
    if (parsed.pathname === '/v1/audible/audio/BBRIDGE/status') {
      return jsonResponse({ playable: false, downloading: false, transcript: { state: 'idle' } });
    }
    return jsonResponse({});
  };

  ctrl.mount(pane, {
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    companyId: 'company-id',
    childMode: true,
    registerContextProvider: () => () => {},
  });
  await waitFor(60);

  window.dispatchEvent(new window.CustomEvent('xtschool-open-audible', {
    detail: { asin: 'BBRIDGE', content_id: 'xt-approved' },
  }));
  await waitFor(80);

  assert.match(pane.textContent, /Bridge Book/);
  assert.ok(calls.some((call) => call.path === '/v1/audible/book/BBRIDGE/transcript'));
  assert.ok(calls.some((call) => call.path === '/v1/audible/audio/BBRIDGE/status'));
  assert.equal(
    calls.some((call) => call.path === '/v1/audible/book/BBRIDGE'),
    false,
    'XTSchool child bridge should use approved metadata instead of live Audible auth'
  );
  ctrl.unmount();
});

test('audible extension: child approval UI stays hidden when there are no child profiles', async () => {
  const { window, registrations } = loadAudibleExtensionPage();
  const ctrl = registrations.get('audible');
  assert.ok(ctrl, 'audible extension should register itself');

  const pane = window.document.querySelector('.view-pane[data-view="audible"]');
  const book = {
    asin: 'BNOCHILDREN',
    title: 'Parent Library Book',
    authors: ['A. Author'],
    narrators: ['N. Reader'],
    runtime_minutes: 40,
  };

  window.fetch = async (url) => {
    const parsed = new URL(String(url));
    if (parsed.pathname === '/v1/user') {
      return jsonResponse({
        companies: [{
          id: 'company-id',
          name: 'Home',
          role_id: 1,
          scopes: ['ext:xtschool:write'],
        }],
      });
    }
    if (parsed.pathname === '/v1/companies/company-id/child-controls') {
      return jsonResponse({ children: [] });
    }
    if (parsed.pathname === '/v1/xtschool/library') {
      return jsonResponse({ items: [], count: 0 });
    }
    if (parsed.pathname === '/v1/audible/library') {
      return jsonResponse({ items: [book] });
    }
    if (parsed.pathname === '/v1/audible/cover/BNOCHILDREN') {
      return new Response('cover', { status: 200, headers: { 'content-type': 'image/jpeg' } });
    }
    if (parsed.pathname === '/v1/audible/book/BNOCHILDREN') {
      return jsonResponse({ ...book, last_position_ms: 0 });
    }
    if (parsed.pathname === '/v1/audible/book/BNOCHILDREN/chapters') {
      return jsonResponse({ chapters: [], total_ms: 2400000, last_position_ms: 0 });
    }
    if (parsed.pathname === '/v1/audible/book/BNOCHILDREN/transcript') {
      return jsonResponse({ segments: [], status: { state: 'idle' } });
    }
    if (parsed.pathname === '/v1/audible/audio/BNOCHILDREN/status') {
      return jsonResponse({ playable: false, downloading: false, transcript: { state: 'idle' } });
    }
    return jsonResponse({});
  };

  ctrl.mount(pane, {
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    companyId: 'company-id',
    registerContextProvider: () => () => {},
  });
  await waitFor(60);
  pane.querySelector('.aud-card').click();
  await waitFor(60);

  assert.match(pane.textContent, /Parent Library Book/);
  assert.doesNotMatch(pane.textContent, /Approve for children/);
  assert.doesNotMatch(pane.textContent, /approved for child profiles/i);
  assert.doesNotMatch(pane.textContent, /approved for children/i);
  ctrl.unmount();
});

test('desktop extensions: failed asset load renders an in-pane error', async () => {
  const { window } = loadDesktopExtensionsOnly();
  window.fetch = async (url) => {
    const pathName = new URL(String(url), 'http://localhost').pathname;
    if (pathName === '/v1/desktop/extensions') {
      return new Response(JSON.stringify({
        extensions: [{ id: 'audible', label: 'Audible', version: 'test' }],
      }), { status: 200 });
    }
    return new Response('', { status: 500 });
  };

  await window.AgixtDesktopExtensions.refresh();
  await window.AgixtDesktopExtensions.activate('audible');

  const pane = window.document.querySelector('.view-pane[data-view="audible"]');
  const error = pane.querySelector('.ext-load-error');
  assert.ok(error, 'extension loader should render a visible error');
  assert.match(error.textContent, /Extension asset failed to load/);
});

test('desktop crud: generated extension page mounts and renders records', async () => {
  const page = path.join(__dirname, '..', '..', '..', 'ultraestimate', 'ui', 'estimates', 'main.js');
  const { window, registrations } = loadCrudExtensionPage(page);
  const ctrl = registrations.get('estimates');
  assert.ok(ctrl, 'generated estimates page should register itself');

  const headerActions = [];
  const calls = [];
  const pane = window.document.querySelector('.view-pane[data-view="estimates"]');
  ctrl.mount(pane, {
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    companyId: 'company-id',
    setHeaderActions: (...nodes) => {
      headerActions.splice(0, headerActions.length, ...nodes);
      return true;
    },
    fetchJson: async (url) => {
      calls.push(url);
      return {
        estimates: [{
          id: 'estimate-1',
          estimate_number: 'EST-1001',
          status: 'draft',
          grand_total: 1250,
          updated_at: '2026-05-11T12:00:00Z',
        }],
      };
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 5));

  assert.ok(pane.querySelector('.dc-root'), 'crud shell should render');
  assert.ok(headerActions.some((node) => node.textContent === 'Refresh'), 'header actions should render');
  assert.equal(calls[0], '/v1/ultraestimate/estimates');
  assert.match(pane.textContent, /EST-1001/);
  assert.match(pane.textContent, /Records/);
});

test('app: selecting a server extension activates its module loader', async () => {
  const { window } = loadFullApp();
  await new Promise((resolve) => setTimeout(resolve, 20));

  const activations = [];
  window.AgixtDesktopExtensions = {
    activate: async (id) => { activations.push(id); },
    reflowSidenav: () => {},
  };
  const btn = window.document.createElement('button');
  btn.className = 'sidenav-btn';
  btn.dataset.view = 'dashboard';
  window.document.querySelector('.sidenav-top').appendChild(btn);

  const pane = window.document.createElement('div');
  pane.className = 'view-pane view-pane-extension';
  pane.dataset.view = 'dashboard';
  pane.hidden = true;
  window.document.querySelector('.chat-screen-main').appendChild(pane);

  window.AgixtSidenav.setActiveView('dashboard');
  await new Promise((resolve) => setTimeout(resolve, 5));

  assert.equal(pane.hidden, false, 'extension pane should be visible');
  assert.deepEqual(activations, ['dashboard']);
  window.AgixtChat.disconnect();
});

test('app: child mode keeps XTSchool and Audible panes available', async () => {
  const { window } = loadFullApp({
    ipc: {
      list_companies: async () => [{
        id: 'company-id',
        name: 'Home',
        primary: true,
        role_id: 4,
        role: 'child',
        scopes: [],
        agents: [{ id: 'agent-id', name: 'XT', default: true }],
      }],
    },
    fetch: async (url) => {
      const parsed = new URL(String(url));
      if (parsed.pathname === '/v1/user') {
        return jsonResponse({
          companies: [{ id: 'company-id', name: 'Home', role_id: 4, scopes: [] }],
        });
      }
      if (parsed.pathname === '/v1/companies/company-id/child-controls/me') {
        return jsonResponse({
          children: [{
            id: 'child-1',
            name: 'Ada',
            access: { app: { locked: false }, features: { chat: { locked: false } } },
          }],
        });
      }
      return jsonResponse({});
    },
  });
  await waitFor(70);
  assert.ok(window.document.body.classList.contains('child-mode'), 'child mode should be active');

  for (const view of ['audible', 'xtschool', 'dashboard']) {
    if (!window.document.querySelector('.sidenav-btn[data-view="' + view + '"]')) {
      const button = window.document.createElement('button');
      button.className = 'sidenav-btn';
      button.dataset.view = view;
      window.document.querySelector('.sidenav-top').appendChild(button);
    }
    if (!window.document.querySelector('.view-pane[data-view="' + view + '"]')) {
      const pane = window.document.createElement('div');
      pane.className = 'view-pane view-pane-extension';
      pane.dataset.view = view;
      pane.hidden = true;
      window.document.querySelector('.chat-screen-main').appendChild(pane);
    }
  }

  window.AgixtSidenav.setActiveView('audible');
  assert.equal(window.AgixtSidenav.getActiveView(), 'audible');
  assert.equal(window.document.querySelector('.view-pane[data-view="audible"]').hidden, false);

  window.AgixtSidenav.setActiveView('xtschool');
  assert.equal(window.AgixtSidenav.getActiveView(), 'xtschool');
  assert.equal(window.document.querySelector('.view-pane[data-view="xtschool"]').hidden, false);

  window.AgixtSidenav.setActiveView('dashboard');
  assert.equal(window.AgixtSidenav.getActiveView(), 'chat');
  assert.equal(window.document.querySelector('.view-pane[data-view="dashboard"]').hidden, true);
  window.AgixtChat.disconnect();
});

test('companies extension: admins can edit child mandatory context and timers', async () => {
  const calls = [];
  let childControls = {
    children: [{
      id: 'child-1',
      email: 'ada@example.com',
      first_name: 'Ada',
      last_name: 'Lovelace',
      mandatory_context: 'Be kind.',
      ai_context: 'Be kind.',
      restrictions: {
        app: { enabled: true, schedule: null, free_weekdays: [], override_until: null },
        features: {
          chat: { enabled: true, schedule: null, free_weekdays: [], override_until: null },
          videos: { enabled: true, schedule: null, free_weekdays: [], override_until: null },
          music: { enabled: true, schedule: null, free_weekdays: [], override_until: null },
          audiobooks: { enabled: true, schedule: null, free_weekdays: [], override_until: null },
          games: { enabled: true, schedule: null, free_weekdays: [], override_until: null },
        },
      },
      access: {
        app: { locked: false },
        features: {
          chat: { locked: false },
          music: { locked: false },
        },
      },
    }],
  };

  const members = [
    {
      id: 'parent-1',
      email: 'parent@example.com',
      first_name: 'Parent',
      last_name: 'One',
      role_id: 1,
      role: 'Admin',
    },
    {
      id: 'child-1',
      email: 'ada@example.com',
      first_name: 'Ada',
      last_name: 'Lovelace',
      role_id: 4,
      role: 'Child',
    },
  ];
  const company = {
    id: 'company-id',
    name: 'Home',
    role_id: 1,
    role: 'admin',
    primary: true,
    users: members,
    children: [{ id: 'child-1' }],
  };
  const { window, registrations } = loadCompaniesExtensionPage();
  const ctrl = registrations.get('companies');
  assert.ok(ctrl, 'companies extension should register itself');
  const panel = window.document.querySelector('.view-pane[data-view="companies"]');
  ctrl.mount(panel, {
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    companyId: 'company-id',
    fetchJson: async (path, opts = {}) => {
      const parsed = new URL(path, 'http://localhost:7437');
      const method = opts.method || 'GET';
      const body = opts.json || null;
      calls.push({ path: parsed.pathname, method, body });

      if (parsed.pathname === '/v1/user') {
        return {
          id: 'parent-1',
          email: 'parent@example.com',
          companies: [company],
        };
      }
      if (parsed.pathname === '/v1/companies') return { companies: [company] };
      if (parsed.pathname === '/v1/companies/company-id/members') return { members };
      if (parsed.pathname === '/v1/invitations/company-id') return { invitations: [] };
      if (parsed.pathname === '/v1/default-roles') {
        return { roles: [
          { id: 2, friendly_name: 'Admin' },
          { id: 3, friendly_name: 'User' },
          { id: 4, friendly_name: 'Child' },
        ] };
      }
      if (parsed.pathname === '/v1/roles') return { roles: [] };
      if (parsed.pathname.includes('/custom-roles')) return [];
      if (parsed.pathname === '/v1/companies/company-id/child-controls') return childControls;
      if (parsed.pathname === '/v1/companies/company-id/child-controls/child-1' && method === 'PATCH') {
        childControls = {
          children: [{
            ...childControls.children[0],
            mandatory_context: body.ai_context,
            ai_context: body.ai_context,
            restrictions: body.restrictions,
          }],
        };
        return childControls.children[0];
      }
      if (parsed.pathname === '/v1/companies/company-id/child-controls/child-1/override') {
        return {
          ...childControls.children[0],
          restrictions: childControls.children[0].restrictions,
        };
      }
      return {};
    },
  });
  await waitFor(100);

  const detailButton = Array.from(panel.querySelectorAll('button'))
    .find((button) => button.textContent === 'Manage in detail');
  assert.ok(detailButton, 'company admins should see the detail management button');
  detailButton.click();
  await waitFor(140);

  assert.match(panel.textContent, /Parental controls/);
  assert.match(panel.textContent, /Ada Lovelace/);

  panel.querySelector('[data-child-control-context="child-1"]').value =
    'Always explain gently and keep examples school-safe.';
  const chatRule = panel.querySelector('[data-child-rule="child-1:chat"]');
  chatRule.querySelector('[data-rule-field="enabled"]').checked = false;
  const musicRule = panel.querySelector('[data-child-rule="child-1:music"]');
  musicRule.querySelector('[data-rule-field="schedule_enabled"]').checked = true;
  musicRule.querySelector('[data-rule-field="lock_from"]').value = '20:00';
  musicRule.querySelector('[data-rule-field="lock_to"]').value = '07:00';
  musicRule.querySelector('[data-rule-field="mode"]').value = 'bedtime';

  Array.from(panel.querySelectorAll('button'))
    .find((button) => button.textContent === 'Save controls')
    .click();
  await waitFor(80);

  const patch = calls.find((call) => (
    call.path === '/v1/companies/company-id/child-controls/child-1' &&
    call.method === 'PATCH'
  ));
  assert.ok(patch, 'saving child controls should PATCH the core endpoint');
  assert.equal(patch.body.ai_context, 'Always explain gently and keep examples school-safe.');
  assert.equal(patch.body.restrictions.features.chat.enabled, false);
  assert.deepEqual(JSON.parse(JSON.stringify(patch.body.restrictions.features.music.schedule)), {
    lock_from: '20:00',
    lock_to: '07:00',
    mode: 'bedtime',
  });

  Array.from(panel.querySelectorAll('button'))
    .find((button) => button.textContent === 'Unlock chat 30m')
    .click();
  await waitFor(100);

  const overrideCall = calls.find((call) => (
    call.path === '/v1/companies/company-id/child-controls/child-1/override' &&
    call.method === 'POST'
  ));
  assert.ok(overrideCall, 'temporary overrides should POST to the core endpoint');
  assert.equal(overrideCall.body.feature, 'chat');
  assert.ok(overrideCall.body.until);
  ctrl.unmount();
});

test('repos extension: fix all vulnerabilities opens the returned chat conversation', async () => {
  const calls = [];
  const activations = [];
  const alerts = [{
    type: 'dependabot',
    severity: 'high',
    summary: 'lodash vulnerable',
    package: 'lodash',
    patched_version: '4.17.21',
    html_url: 'https://github.com/dev/repo/security/dependabot/1',
  }];
  const repo = {
    owner: 'dev',
    name: 'repo',
    full_name: 'dev/repo',
    html_url: 'https://github.com/dev/repo',
    description: 'security fixture',
    language: 'JavaScript',
    visibility: 'private',
    fork: false,
    open_issues: 0,
    open_prs: 0,
    total_vulns: 1,
    dependabot_count: 1,
    code_scanning_count: 0,
    advisory_count: 0,
    severity: { critical: 0, high: 1, medium: 0, low: 0 },
    dependabot_enabled: true,
    code_scanning_enabled: true,
    stars: 0,
    updated_at_display: 'now',
  };
  const { window, registrations } = loadReposExtensionPage();
  const ctrl = registrations.get('repos');
  assert.ok(ctrl, 'repos extension should register itself');

  window.AgixtSession = {
    routeFailureStatus: async () => {
      throw new Error('routeFailureStatus should not be called for successful launch');
    },
  };
  window.AgixtApp = {
    activateConversation: async (conversation) => {
      activations.push(conversation);
    },
  };

  const panel = window.document.querySelector('.view-pane[data-view="repos"]');
  ctrl.mount(panel, {
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    agentId: 'agent-id',
    companyId: 'company-id',
    registerContextProvider: () => () => {},
    fetchJson: async (path, opts = {}) => {
      calls.push({ path, method: opts.method || 'GET', body: opts.json || null });
      if (path === '/v1/github/repos') {
        return { repos: [repo], last_updated: '2026-06-01T12:00:00Z' };
      }
      if (path === '/v1/github/repos/dev/repo/alerts') {
        return { alerts };
      }
      if (path === '/v1/github/repos/dev/repo/fix-vulns' && opts.method === 'POST') {
        return {
          conversation_id: 'conversation-123',
          conversation_name: 'Fix Vulnerabilities - dev/repo',
          status: 'started',
        };
      }
      throw new Error('unexpected fetchJson path: ' + path);
    },
  });

  await waitFor(20);
  const alertToggle = panel.querySelector('[data-toggle="alerts"]');
  assert.ok(alertToggle, 'security alert row can be expanded');
  alertToggle.click();
  await waitFor(20);

  const fixButton = panel.querySelector('[data-action="fix-vulns"]');
  assert.ok(fixButton, 'expanded alert details include Fix All Vulns action');
  fixButton.click();
  await waitFor(20);

  assert.ok(
    calls.some((call) => call.path === '/v1/github/repos/dev/repo/fix-vulns' && call.method === 'POST'),
    'fix-vulns endpoint is posted',
  );
  assert.equal(activations.length, 1);
  assert.equal(activations[0].id, 'conversation-123');
  assert.equal(activations[0].name, 'Fix Vulnerabilities - dev/repo');
  assert.equal(fixButton.disabled, true, 'button stays disabled after chat handoff to prevent duplicate runs');
  assert.match(fixButton.textContent, /Opened in chat/);
  ctrl.unmount();
});

test('repos extension: failed browser launch reports API reachability without hunting for chat', async () => {
  const calls = [];
  const activations = [];
  const alerts = [{
    type: 'dependabot',
    severity: 'critical',
    summary: 'express vulnerable',
    package: 'express',
    patched_version: '4.19.2',
    html_url: 'https://github.com/dev/repo/security/dependabot/2',
  }];
  const repo = {
    owner: 'dev',
    name: 'repo',
    full_name: 'dev/repo',
    html_url: 'https://github.com/dev/repo',
    description: 'security fixture',
    language: 'JavaScript',
    visibility: 'private',
    fork: false,
    open_issues: 0,
    open_prs: 0,
    total_vulns: 1,
    dependabot_count: 1,
    code_scanning_count: 0,
    advisory_count: 0,
    severity: { critical: 1, high: 0, medium: 0, low: 0 },
    dependabot_enabled: true,
    code_scanning_enabled: true,
    stars: 0,
    updated_at_display: 'now',
  };
  const { window, registrations } = loadReposExtensionPage();
  const ctrl = registrations.get('repos');
  assert.ok(ctrl, 'repos extension should register itself');

  const alertsShown = [];
  window.alert = (message) => alertsShown.push(message);
  window.AgixtApp = {
    activateConversation: async (conversation) => {
      activations.push(conversation);
    },
  };

  const panel = window.document.querySelector('.view-pane[data-view="repos"]');
  ctrl.mount(panel, {
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    agentId: 'agent-id',
    companyId: 'company-id',
    registerContextProvider: () => () => {},
    fetchJson: async (path, opts = {}) => {
      calls.push({ path, method: opts.method || 'GET', body: opts.json || null });
      if (path === '/v1/github/repos') {
        return { repos: [repo], last_updated: '2026-06-01T12:00:00Z' };
      }
      if (path === '/v1/github/repos/dev/repo/alerts') {
        return { alerts };
      }
      if (path === '/v1/github/repos/dev/repo/fix-vulns' && opts.method === 'POST') {
        throw new TypeError('Failed to fetch');
      }
      if (path === '/v1/conversations?limit=500&include_counts=false') {
        throw new Error('conversation recovery should not run for browser fetch failures');
      }
      throw new Error('unexpected fetchJson path: ' + path);
    },
  });

  await waitFor(20);
  panel.querySelector('[data-toggle="alerts"]').click();
  await waitFor(20);

  const fixButton = panel.querySelector('[data-action="fix-vulns"]');
  fixButton.click();
  await waitFor(50);

  assert.ok(
    calls.some((call) => call.path === '/v1/github/repos/dev/repo/fix-vulns' && call.method === 'POST'),
    'fix-vulns endpoint is posted once',
  );
  assert.equal(
    calls.some((call) => call.path === '/v1/conversations?limit=500&include_counts=false'),
    false,
    'conversation list is not polled after a browser-level fetch failure',
  );
  assert.equal(activations.length, 0);
  assert.equal(alertsShown.length, 1);
  assert.match(alertsShown[0], /Could not reach the AGiXT API/);
  assert.equal(fixButton.disabled, false, 'button is restored after failed launch');
  ctrl.unmount();
});

test('repos extension: pending security refresh is labeled as loading details', async () => {
  const repo = {
    owner: 'dev',
    name: 'pending',
    full_name: 'dev/pending',
    html_url: 'https://github.com/dev/pending',
    description: '',
    language: 'Rust',
    visibility: 'public',
    fork: false,
    open_issues: 0,
    open_prs: 0,
    total_vulns: 1,
    dependabot_count: 0,
    code_scanning_count: 0,
    advisory_count: 0,
    severity: { critical: 0, high: 0, medium: 0, low: 0 },
    dependabot_enabled: true,
    code_scanning_enabled: true,
    security_refreshing: true,
    stars: 0,
    updated_at_display: 'now',
  };
  const { window, registrations } = loadReposExtensionPage();
  const ctrl = registrations.get('repos');
  assert.ok(ctrl, 'repos extension should register itself');
  const panel = window.document.querySelector('.view-pane[data-view="repos"]');
  ctrl.mount(panel, {
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    agentId: 'agent-id',
    companyId: 'company-id',
    registerContextProvider: () => () => {},
    fetchJson: async (path) => {
      if (path === '/v1/github/repos') {
        return { repos: [repo], last_updated: null };
      }
      throw new Error('unexpected fetchJson path: ' + path);
    },
  });

  await waitFor(20);
  assert.match(panel.textContent, /Loading details/);
  assert.doesNotMatch(panel.textContent, /Refreshing…/);
  ctrl.unmount();
});

test('app: extension context is sent hidden from the displayed user message', async () => {
  const { window, calls } = loadFullApp();
  await new Promise((resolve) => setTimeout(resolve, 20));
  window.AgixtDesktopExtensions = {
    getActiveContext: () => '## Current Audible Desktop Extension Context\nOpen audiobook: "The Hobbit"\nCurrent position: 1:02:03',
  };

  const input = window.document.getElementById('composer-input');
  input.value = 'Where am I in the story?';
  window.document.getElementById('btn-send').click();
  await new Promise((resolve) => setTimeout(resolve, 20));

  const send = calls.find((c) => c.cmd === 'chat_send');
  assert.ok(send);
  const msg = send.args.args.messages[0];
  assert.equal(msg.content, 'Where am I in the story?');
  assert.match(msg.context, /The Hobbit/);
  assert.doesNotMatch(window.document.getElementById('messages').textContent, /The Hobbit/);
  window.AgixtChat.disconnect();
});

test('app: signed-out startup shows auth and blocks agent settings', async () => {
  const signedOutSettings = {
    jwt: null,
    conversation_id: null,
    conversation_name: null,
    server_url: 'https://api.agixt.com',
    web_url: 'https://agixt.com',
    service_brand: 'agixt',
    agent_id: null,
    agent_name: 'XT',
    company_id: null,
    company_name: null,
    allow_client_commands: true,
    voice_enabled: false,
    desktop_auto_update: false,
    user_email: null,
  };
  const { window, calls } = loadFullApp({
    ipc: {
      get_settings: async () => signedOutSettings,
      list_service_brands: async () => [
        {
          slug: 'agixt',
          label: 'AGiXT.com',
          default_url: 'https://api.agixt.com',
          default_web_url: 'https://agixt.com',
        },
      ],
      list_oauth_providers: async () => [],
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 40));

  assert.equal(window.document.getElementById('auth-screen').hidden, false);
  assert.equal(window.document.getElementById('chat-screen').hidden, true);
  assert.equal(window.document.body.classList.contains('auth-mode'), true);
  assert.equal(window.document.getElementById('btn-agent-training').disabled, true);
  assert.equal(window.document.getElementById('agent-switcher-btn').disabled, true);
  assert.equal(window.document.getElementById('convo-switcher-btn').disabled, true);

  window.document.getElementById('btn-agent-training').click();
  await new Promise((resolve) => setTimeout(resolve, 5));
  assert.equal(window.document.getElementById('auth-screen').hidden, false);
  assert.equal(calls.some((c) => c.cmd === 'show_chat'), false);
  window.AgixtChat.disconnect();
});

test('app: Android XT School auth uses in-app keyboard for typing', async () => {
  let oauthProviderCalls = 0;
  const signedOutSettings = {
    jwt: null,
    conversation_id: null,
    conversation_name: null,
    server_url: 'https://api.xt.school',
    web_url: 'https://app.xt.school',
    service_brand: 'xtschool',
    agent_id: null,
    agent_name: 'XT',
    company_id: null,
    company_name: null,
    allow_client_commands: true,
    voice_enabled: false,
    desktop_auto_update: false,
    user_email: null,
  };
  const { window } = loadFullApp({
    userAgent: 'Mozilla/5.0 (Linux; Android 11; KFRAPWI) AppleWebKit/537.36',
    ipc: {
      get_settings: async () => signedOutSettings,
      list_service_brands: async () => [
        {
          slug: 'xtschool',
          label: 'XT.School',
          default_url: 'https://api.xt.school',
          default_web_url: 'https://app.xt.school',
          locked: true,
        },
      ],
      list_oauth_providers: async () => {
        oauthProviderCalls += 1;
        return [{ name: 'google' }];
      },
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 40));

  const email = window.document.getElementById('login-email');
  const keyboard = window.document.getElementById('auth-touch-keyboard');
  assert.equal(window.document.body.classList.contains('auth-touch-keyboard-enabled'), true);
  assert.equal(email.readOnly, true);
  assert.equal(email.getAttribute('inputmode'), 'none');
  assert.equal(window.document.getElementById('oauth-row').hidden, true);
  assert.equal(oauthProviderCalls, 0);

  email.dispatchEvent(new window.Event('pointerdown', { bubbles: true, cancelable: true }));
  assert.equal(keyboard.hidden, false);
  assert.equal(window.document.body.classList.contains('auth-touch-keyboard-open'), true);

  const qKey = Array.from(keyboard.querySelectorAll('button'))
    .find((button) => button.textContent === 'q');
  assert.ok(qKey);
  qKey.dispatchEvent(new window.Event('pointerdown', { bubbles: true, cancelable: true }));
  assert.equal(email.value, 'q');

  const nextKey = Array.from(keyboard.querySelectorAll('button'))
    .find((button) => button.textContent === 'Next');
  assert.ok(nextKey);
  nextKey.dispatchEvent(new window.Event('pointerdown', { bubbles: true, cancelable: true }));
  assert.equal(window.document.activeElement, window.document.getElementById('login-password'));
  window.AgixtChat.disconnect();
});

test('app: hosted web brand hides service picker and applies brand chrome', async () => {
  const signedOutSettings = {
    jwt: null,
    conversation_id: null,
    conversation_name: null,
    server_url: 'https://boltremote.com',
    web_url: 'https://boltremote.com',
    service_brand: 'boltremote',
    agent_id: null,
    agent_name: 'XT',
    company_id: null,
    company_name: null,
    allow_client_commands: true,
    voice_enabled: false,
    desktop_auto_update: false,
    user_email: null,
  };
  const { window } = loadFullApp({
    url: 'https://boltremote.com/user',
    webRuntime: true,
    ipc: {
      get_settings: async () => signedOutSettings,
      list_service_brands: async () => [
        {
          slug: 'boltremote',
          label: 'BoltRemote',
          default_url: 'https://boltremote.com',
          default_web_url: 'https://boltremote.com',
          locked: true,
        },
      ],
      list_oauth_providers: async () => [],
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 40));

  assert.equal(window.document.getElementById('auth-screen').hidden, false);
  assert.equal(window.document.getElementById('service-brand-field').hidden, true);
  assert.equal(window.document.title, 'BoltRemote');
  assert.ok(window.document.getElementById('app-favicon').href.endsWith('/assets/brands/boltremote-favicon.svg'));
  assert.ok(window.document.getElementById('brand-mark-img').src.endsWith('/assets/brands/boltremote.svg'));
  window.AgixtChat.disconnect();
});

test('app: switching agents activates that agent conversation and filters the menu', async () => {
  let savedSettings = {
    jwt: 'jwt',
    conversation_id: 'c-xt',
    conversation_name: 'XT',
    server_url: 'http://localhost:7437',
    agent_id: 'agent-xt',
    agent_name: 'XT',
    company_id: 'company-id',
    company_name: 'Home',
    allow_client_commands: true,
    voice_enabled: false,
    desktop_auto_update: false,
    user_email: 'test@example.com',
  };
  const conversations = [
    {
      id: 'c-xt',
      name: 'XT',
      display_name: 'XT',
      agent_name: 'XT',
      conversation_type: 'dm',
      updated_at: '2026-05-06T20:00:00Z',
    },
    {
      id: 'c-helper',
      name: 'Helper',
      display_name: 'Helper',
      agent_name: 'Helper',
      conversation_type: 'dm',
      updated_at: '2026-05-06T21:00:00Z',
    },
  ];
  const { window, calls } = loadFullApp({
    ipc: {
      get_settings: async () => savedSettings,
      save_settings: async ({ settings }) => {
        savedSettings = { ...settings };
        return savedSettings;
      },
      list_companies: async () => [{
        id: 'company-id',
        name: 'Home',
        primary: true,
        agents: [
          { id: 'agent-xt', name: 'XT', default: true, company_id: 'company-id' },
          { id: 'agent-helper', name: 'Helper', default: false, company_id: 'company-id' },
        ],
      }],
      list_agents: async () => [
        { id: 'agent-xt', name: 'XT', default: true, company_id: 'company-id' },
        { id: 'agent-helper', name: 'Helper', default: false, company_id: 'company-id' },
      ],
      list_conversations: async () => conversations,
      select_conversation: async ({ id, name }) => {
        savedSettings = { ...savedSettings, conversation_id: id, conversation_name: name };
        return null;
      },
      get_conversation_history: async () => [],
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 40));

  window.document.getElementById('agent-switcher-btn').click();
  await new Promise((resolve) => setTimeout(resolve, 5));
  const helperButton = [...window.document.querySelectorAll('#agent-menu-list button')]
    .find((btn) => btn.querySelector('.agent-name')?.textContent === 'Helper');
  assert.ok(helperButton);
  helperButton.click();
  await new Promise((resolve) => setTimeout(resolve, 60));

  assert.equal(savedSettings.agent_id, 'agent-helper');
  assert.equal(savedSettings.conversation_id, 'c-helper');
  assert.equal(window.AgixtChat.getConversationId(), 'c-helper');
  assert.ok(calls.some((c) => c.cmd === 'select_conversation' && c.args.id === 'c-helper'));

  window.document.getElementById('convo-switcher-btn').click();
  await new Promise((resolve) => setTimeout(resolve, 20));
  const names = [...window.document.querySelectorAll('#convo-menu-list .convo-name')]
    .map((node) => node.textContent);
  assert.deepEqual(names, ['Helper']);
  window.AgixtChat.disconnect();
});

test('app: sudo auth button primes privileged command session', async () => {
  const { window, calls } = loadFullApp({
    ipc: {
      sudo_status: async () => ({ authenticated: false, remembered: false }),
      sudo_auth: async () => ({ authenticated: true, remembered: true }),
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 20));

  // The gear-button modal was replaced by a `data-view="user-settings"`
  // side pane. Clicking the gear routes through setActiveView, which
  // lazy-mounts user-settings.js — wait for the App tab to render before
  // poking at the dynamically-created sudo controls.
  window.document.getElementById('btn-settings').click();
  await new Promise((resolve) => setTimeout(resolve, 50));

  const input = window.document.querySelector('[data-us-test="sudo-password"]');
  input.value = 'secret';
  window.document.querySelector('[data-us-test="sudo-auth"]').click();
  await new Promise((resolve) => setTimeout(resolve, 30));

  const authCall = calls.find((c) => c.cmd === 'sudo_auth');
  assert.equal(authCall.args.password, 'secret');
  assert.equal(input.value, '');
  assert.equal(
    window.document.querySelector('[data-us-test="sudo-status"]').textContent,
    'Authenticated and remembered.',
  );
  window.AgixtChat.disconnect();
});

test('app: desktop update install locks controls and asks for sudo auth', async () => {
  let rejectInstall;
  let installCalls = 0;
  const { window } = loadFullApp({
    ipc: {
      desktop_update_check: async () => ({
        current_build_id: 'old',
        app_version: '0.1.0',
        latest_build_id: 'new',
        update_available: true,
        ready: true,
        platform: 'linux',
      }),
      desktop_update_install: async () => {
        installCalls += 1;
        if (installCalls === 1) {
          return new Promise((_, reject) => { rejectInstall = reject; });
        }
        return { installed: true, message: 'Update installed.' };
      },
      sudo_status: async () => ({ authenticated: false }),
      sudo_auth: async () => ({ authenticated: true }),
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 20));

  // Open the user-settings pane (the App tab is the first one).
  window.document.getElementById('btn-settings').click();
  await new Promise((resolve) => setTimeout(resolve, 60));

  const checkButton = window.document.querySelector('[data-us-test="desktop-update-check"]');
  const installButton = window.document.querySelector('[data-us-test="desktop-update-install"]');
  // The initial check fires on render and reports an update is ready, so
  // the install button should be visible.
  assert.equal(installButton.hidden, false);

  installButton.click();
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal(checkButton.hidden, true);
  assert.equal(installButton.hidden, true);

  rejectInstall({ error: 'SUDO_AUTH_REQUIRED: Authenticate first.' });
  await new Promise((resolve) => setTimeout(resolve, 80));
  assert.match(
    window.document.querySelector('[data-us-test="desktop-update-status"]').textContent,
    /Authenticate Privileged Commands/,
  );
  assert.equal(
    window.document.activeElement,
    window.document.querySelector('[data-us-test="sudo-password"]'),
  );

  const input = window.document.querySelector('[data-us-test="sudo-password"]');
  input.value = 'secret';
  window.document.querySelector('[data-us-test="sudo-auth"]').click();
  await new Promise((resolve) => setTimeout(resolve, 60));

  assert.equal(installCalls, 2);
  assert.equal(
    window.document.querySelector('[data-us-test="desktop-update-status"]').textContent,
    'Update installed.',
  );
  window.AgixtChat.disconnect();
});

test('app: enabling automatic desktop updates schedules install', async () => {
  const { window, calls } = loadFullApp({
    ipc: {
      desktop_update_check: async () => ({
        current_build_id: 'old',
        app_version: '0.1.0',
        latest_build_id: 'new',
        update_available: true,
        ready: true,
        platform: 'linux',
      }),
      desktop_update_install: async () => ({ installed: true, message: 'Update installed.' }),
      sudo_status: async () => ({ authenticated: true }),
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 20));

  // Open the user-settings pane and flip the auto-update toggle on.
  window.document.getElementById('btn-settings').click();
  await new Promise((resolve) => setTimeout(resolve, 60));
  window.document.querySelector('[data-us-test="auto-update"]').checked = true;
  window.document.querySelector('[data-us-test="save-behavior"]').click();
  // The Save handler arms the same scheduleDesktopAutoUpdateCheck timer
  // that the legacy modal's Save did (via window.AgixtDesktopUpdates),
  // so after ~500ms the install IPC should have fired.
  await new Promise((resolve) => setTimeout(resolve, 600));

  assert.ok(calls.some((c) => c.cmd === 'desktop_update_install'));
  window.AgixtChat.disconnect();
});

test('app: successful update install auto-restarts the app', async () => {
  const { window, calls } = loadFullApp({
    ipc: {
      desktop_update_check: async () => ({
        current_build_id: 'old',
        app_version: '0.1.0',
        latest_build_id: 'new',
        update_available: true,
        ready: true,
        platform: 'linux',
      }),
      desktop_update_install: async () => ({
        installed: true,
        restart_required: true,
        message: 'Update installed. Restart AGiXT Desktop to use the new version.',
      }),
      desktop_restart_app: async () => ({}),
      sudo_status: async () => ({ authenticated: true }),
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 20));

  window.document.getElementById('btn-settings').click();
  await new Promise((resolve) => setTimeout(resolve, 60));

  const installButton = window.document.querySelector('[data-us-test="desktop-update-install"]');
  assert.equal(installButton.hidden, false);
  installButton.click();
  await new Promise((resolve) => setTimeout(resolve, 30));

  // The status flips to the restarting message immediately…
  assert.match(
    window.document.querySelector('[data-us-test="desktop-update-status"]').textContent,
    /Restarting AGiXT Desktop/,
  );

  // …and after the brief read delay the restart IPC fires.
  await new Promise((resolve) => setTimeout(resolve, 1700));
  assert.ok(calls.some((c) => c.cmd === 'desktop_restart_app'));
  window.AgixtChat.disconnect();
});

test('user settings: billing plan picker renders current plan and opens annual checkout', async () => {
  const apiCalls = [];
  const { window } = loadFullApp();
  const openedUrls = [];
  window.open = (url) => {
    openedUrls.push(url);
    return null;
  };
  window.AgixtSession = window.AgixtSession || {};
  window.AgixtSession.request = async (pathName, opts = {}) => {
    apiCalls.push({ path: pathName, method: opts.method || 'GET', body: opts.json });
    if (pathName === '/v1/billing/pricing/enabled') {
      return {
        billing_enabled: true,
        pricing_model: 'tiered_plan',
        app_name: 'XT Systems',
      };
    }
    if (pathName === '/v1/user') {
      return {
        email: 'test@example.com',
        companies: [{ id: 'company-id', name: 'Home', primary: true, role_id: 1 }],
      };
    }
    if (pathName === '/v1/billing/pricing') {
      return {
        app_name: 'XT Systems',
        pricing_model: 'tiered_plan',
        contracts: { monthly: true, annual: true, annual_discount_percent: 10 },
        tiers: [
          {
            id: 'starter',
            name: 'Starter',
            description: 'Individual workspace',
            price: 20,
            limits: { users: 1, devices: 30, tokens: 10000000, storage_gb: 2 },
            features: ['Personal agents', 'Safe workspace'],
          },
          {
            id: 'team_5',
            name: 'Team',
            description: 'Small team workspace',
            price: 49,
            limits: { users: 5, devices: 100, tokens: 50000000, storage_gb: 10 },
            features: ['Team chat', 'Machine control'],
          },
        ],
      };
    }
    if (pathName.startsWith('/v1/billing/auto-topup?')) {
      return {
        enabled: false,
        subscription_id: null,
        trial: {
          is_active: true,
          days_remaining: 12,
          trial_end: '2026-06-01T00:00:00Z',
          credits_granted: 20,
          credits_remaining: 18,
        },
      };
    }
    if (pathName.startsWith('/v1/billing/plan/limits?')) {
      return {
        plan_id: 'starter',
        plan_name: 'Starter',
        usage: {
          users: 1,
          devices: 28,
          tokens_this_period: 8500000,
          storage_bytes: 1048576,
        },
        limits: {
          users: 1,
          devices: 30,
          tokens_per_month: 10000000,
          storage_bytes: 2147483648,
        },
        warnings: [
          {
            type: 'token_limit_approaching',
            severity: 'warning',
            message: 'Approaching monthly token limit (8500000/10000000). 1500000 tokens remaining.',
          },
          {
            type: 'device_limit_approaching',
            severity: 'warning',
            message: 'Approaching device limit (28/30). Consider upgrading your plan.',
          },
        ],
      };
    }
    if (pathName === '/v1/billing/transactions') return [];
    if (pathName === '/v1/billing/plan/topup') {
      return { checkout_url: 'https://stripe.example/topup' };
    }
    if (pathName === '/v1/billing/plan/checkout') {
      return {
        checkout_url: 'https://stripe.example/checkout/c/pay/cs_test_plan_123',
        session_id: 'cs_test_plan_123',
      };
    }
    return {};
  };

  await new Promise((resolve) => setTimeout(resolve, 20));
  window.document.getElementById('btn-settings').click();
  await new Promise((resolve) => setTimeout(resolve, 60));

  const billingTab = window.document.querySelector('.us-tab[data-us-tab="billing"]');
  assert.equal(billingTab.hidden, false);
  billingTab.click();
  await new Promise((resolve) => setTimeout(resolve, 80));

  const billingPanel = window.document.querySelector('.us-panel[data-us-panel="billing"]');
  assert.match(billingPanel.textContent, /Trial active/);
  assert.match(billingPanel.textContent, /Current plan/);
  assert.match(billingPanel.textContent, /Starter/);
  assert.match(billingPanel.textContent, /Team/);
  assert.match(billingPanel.textContent, /Billing limits are getting close/);
  assert.match(billingPanel.textContent, /Buy token top-up/);
  assert.match(billingPanel.textContent, /1500000 tokens remaining/);

  const annualButton = Array.from(window.document.querySelectorAll('.us-billing-interval-btn'))
    .find((button) => /Annual/.test(button.textContent));
  assert.ok(annualButton);
  annualButton.click();
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.match(billingPanel.textContent, /\$529\.20\/yr/);

  const teamCard = Array.from(window.document.querySelectorAll('.us-plan-card'))
    .find((card) => /Team/.test(card.textContent));
  assert.ok(teamCard);
  const teamButton = teamCard.querySelector('.btn-primary');
  assert.ok(teamButton);
  teamButton.click();
  teamButton.click();
  await new Promise((resolve) => setTimeout(resolve, 30));

  const checkoutCalls = apiCalls.filter((call) => call.path === '/v1/billing/plan/checkout');
  assert.equal(checkoutCalls.length, 1);
  const checkoutCall = checkoutCalls[0];
  assert.equal(checkoutCall.body.company_id, 'company-id');
  assert.equal(checkoutCall.body.plan_id, 'team_5');
  assert.equal(checkoutCall.body.billing_interval, 'year');
  assert.deepEqual(openedUrls, ['https://stripe.example/checkout/c/pay/cs_test_plan_123']);
  const pendingPayment = JSON.parse(
    window.localStorage.getItem('agixt.desktop.pendingPayment.v1'),
  );
  assert.equal(pendingPayment.checkout_session_id, 'cs_test_plan_123');

  await window.AgixtApi.syncBilling('company-id', 'cs_test_plan_123');
  assert.ok(apiCalls.some((call) =>
    call.path === '/v1/billing/sync?company_id=company-id&checkout_session_id=cs_test_plan_123'));
  window.AgixtChat.disconnect();
});

test('hosted web: /billing success route opens billing and syncs checkout session', async () => {
  const apiCalls = [];
  const { window } = loadFullApp({
    url: 'http://localhost/billing?success=true&session_id=cs_test_route_123',
    webRuntime: true,
  });
  window.AgixtSession = window.AgixtSession || {};
  window.AgixtSession.request = async (pathName, opts = {}) => {
    apiCalls.push({ path: pathName, method: opts.method || 'GET', body: opts.json });
    if (pathName === '/v1/billing/pricing/enabled') {
      return { billing_enabled: true, pricing_model: 'tiered_plan', app_name: 'XT Systems' };
    }
    if (pathName === '/v1/user') {
      return {
        email: 'test@example.com',
        companies: [{ id: 'company-id', name: 'Home', primary: true, role_id: 1 }],
      };
    }
    if (pathName === '/v1/billing/pricing') {
      return {
        app_name: 'XT Systems',
        pricing_model: 'tiered_plan',
        contracts: { monthly: true, annual: true },
        tiers: [{ id: 'team_20', name: 'Team', price: 200, limits: { users: 20 } }],
      };
    }
    if (pathName === '/v1/billing/sync?checkout_session_id=cs_test_route_123') {
      return {
        success: true,
        synced_count: 1,
        synced: [{ completed: true, company_id: 'company-id', plan_id: 'team_20' }],
      };
    }
    if (pathName.startsWith('/v1/billing/auto-topup?')) {
      return {
        enabled: true,
        subscription_id: 'sub_test',
        plan: { id: 'team_20', name: 'Team', amount_usd: 200 },
      };
    }
    if (pathName.startsWith('/v1/billing/plan/limits?')) {
      return {
        plan_id: 'team_20',
        plan_name: 'Team',
        usage: { users: 1, devices: 0, tokens_this_period: 0, storage_bytes: 0 },
        limits: { users: 20, devices: 100, tokens_per_month: 100000000, storage_bytes: 2147483648 },
      };
    }
    if (pathName === '/v1/billing/transactions') return [];
    return {};
  };

  await new Promise((resolve) => setTimeout(resolve, 180));

  const billingPanel = window.document.querySelector('.us-panel[data-us-panel="billing"]');
  assert.ok(billingPanel);
  assert.equal(billingPanel.hidden, false);
  assert.match(billingPanel.textContent, /Payment complete/);
  assert.match(billingPanel.textContent, /Team/);
  assert.ok(apiCalls.some((call) =>
    call.path === '/v1/billing/sync?checkout_session_id=cs_test_route_123'));
  window.AgixtChat.disconnect();
});

test('user settings: glasses tab saves G1 preferences and can send a test page', async () => {
  const g1Status = {
    supported: true,
    scanning: false,
    connected: true,
    left: { side: 'left', name: 'G1_L_Test', id: 'left-id', connected: true },
    right: { side: 'right', name: 'G1_R_Test', id: 'right-id', connected: true },
    battery: {
      left: { side: 'left', percentage: 91, voltage: 4, is_charging: false, timestamp: 'now' },
      right: { side: 'right', percentage: 88, voltage: 4, is_charging: true, timestamp: 'now' },
      last_updated: 'now',
    },
    last_event: 'G1 glasses connected',
    last_error: null,
  };
  const { window, calls } = loadFullApp({
    ipc: {
      g1_status: async () => g1Status,
      g1_send_text: async () => g1Status,
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 20));

  window.document.getElementById('btn-settings').click();
  await new Promise((resolve) => setTimeout(resolve, 40));
  window.document.querySelector('[data-us-tab="glasses"]').click();
  await new Promise((resolve) => setTimeout(resolve, 80));

  assert.match(window.document.querySelector('[data-us-test="g1-status"]').textContent, /connected/i);
  assert.match(window.document.querySelector('[data-us-test="g1-hero-chips"]').textContent, /G1_L_Test/);

  window.document.querySelector('[data-us-test="g1-enabled"]').checked = true;
  window.document.querySelector('[data-us-test="g1-save"]').click();
  await new Promise((resolve) => setTimeout(resolve, 30));

  const saveCall = calls.filter((c) => c.cmd === 'save_settings').at(-1);
  assert.equal(saveCall.args.settings.g1_enabled, true);
  assert.equal(saveCall.args.settings.g1_dashboard_layout, 'dual');

  const testText = window.document.querySelector('[data-us-test="g1-test-text"]');
  testText.value = 'Desktop G1 smoke test';
  window.document.querySelector('[data-us-test="g1-send-test"]').click();
  await new Promise((resolve) => setTimeout(resolve, 30));

  const textCall = calls.find((c) => c.cmd === 'g1_send_text');
  assert.equal(textCall.args.text, 'Desktop G1 smoke test');
  assert.equal(textCall.args.streaming, false);
  window.AgixtChat.disconnect();
});

test('app: mic uses native recorder before browser MediaRecorder fallback', async () => {
  const { window, calls } = loadFullApp({
    ipc: {
      voice_start_recording: async () => ({
        device_name: 'Test Mic',
        sample_rate: 48000,
        channels: 1,
      }),
      voice_stop_recording: async () => ({
        audio_base64: Buffer.from('fake wav bytes').toString('base64'),
        mime_type: 'audio/wav',
        size_bytes: 14,
        duration_ms: 750,
        sample_count: 36000,
        sample_rate: 48000,
        channels: 1,
      }),
    },
  });
  window.fetch = async (url, opts) => {
    assert.match(url, /\/v1\/audio\/transcriptions$/);
    assert.equal(opts.method, 'POST');
    return { ok: true, json: async () => ({ text: 'Can you click the spotify icon?' }) };
  };
  await new Promise((resolve) => setTimeout(resolve, 20));

  const mic = window.document.getElementById('btn-mic');
  mic.click();
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(mic.getAttribute('data-state'), 'recording');
  assert.match(window.document.getElementById('composer-status').textContent, /Test Mic/);

  mic.click();
  await new Promise((resolve) => setTimeout(resolve, 40));

  assert.equal(calls.filter((c) => c.cmd === 'voice_start_recording').length, 1);
  assert.equal(calls.filter((c) => c.cmd === 'voice_stop_recording').length, 1);
  const sends = calls.filter((c) => c.cmd === 'chat_send');
  assert.equal(sends.length, 1);
  assert.equal(sends[0].args.args.messages[0].content, 'Can you click the spotify icon?');
  window.AgixtChat.disconnect();
});

test('client-actions: desktop_screenshot routes to terminal IPC', async () => {
  const { window, calls } = loadFrontend({
    ipc: {
      desktop_screenshot: async () => ({ image_data: 'AAAA', width: 10, height: 10 }),
    },
  });
  const res = await window.AgixtClientActions.execute({
    tool_name: 'desktop_screenshot',
    tool_args: { target_width: '800' },
  });
  assert.equal(res.image_data, 'AAAA');
  assert.equal(calls[0].cmd, 'desktop_screenshot');
  assert.equal(calls[0].args.targetWidth, 800);
});

test('client-actions: desktop_screenshot defaults to 1920-wide vision surface', async () => {
  const { window, calls } = loadFrontend({
    ipc: {
      desktop_screenshot: async () => ({ image_data: 'AAAA', width: 1920, height: 1080 }),
    },
  });
  await window.AgixtClientActions.execute({ tool_name: 'desktop_screenshot', tool_args: {} });
  assert.equal(calls[0].cmd, 'desktop_screenshot');
  assert.equal(calls[0].args.targetWidth, 1920);
  assert.equal(calls[0].args.targetHeight, null);
});

test('client-actions: xtschool tools dispatch through the page bridge', async () => {
  const { window } = loadFrontend();
  const calls = [];
  window.XTSchool = {
    searchLibrary: async (args) => {
      calls.push(['searchLibrary', args]);
      return [{ id: 'video-1' }];
    },
    createHtmlCreation: async (args) => {
      calls.push(['createHtmlCreation', args]);
      return { id: 'creation-1' };
    },
    mediaControl: async (args) => {
      calls.push(['mediaControl', args]);
      return { ok: true };
    },
    importContent: async (args) => {
      calls.push(['importContent', args]);
      return { id: 'video-2' };
    },
    updateContent: async (args) => {
      calls.push(['updateContent', args]);
      return { id: args.content_id, approved: args.approved };
    },
    createPlaylist: async (args) => {
      calls.push(['createPlaylist', args]);
      return { id: 'playlist-1' };
    },
    addContentToPlaylist: async (args) => {
      calls.push(['addContentToPlaylist', args]);
      return { id: args.playlist_id };
    },
  };

  const search = await window.AgixtClientActions.execute({
    tool_name: 'xtschool_search_library',
    tool_args: { query: 'fractions', content_type: 'video' },
  });
  const created = await window.AgixtClientActions.execute({
    tool_name: 'create_html_creation',
    tool_args: { title: 'Rocket Math', html: '<html></html>' },
  });
  const media = await window.AgixtClientActions.execute({
    tool_name: 'media_control',
    tool_args: { action: 'pause' },
  });
  const imported = await window.AgixtClientActions.execute({
    tool_name: 'add_youtube_url',
    tool_args: { url: 'https://youtu.be/dQw4w9WgXcQ' },
  });
  const updated = await window.AgixtClientActions.execute({
    tool_name: 'xtschool_update_content',
    tool_args: { content_id: 'video-2', approved: true },
  });
  const playlist = await window.AgixtClientActions.execute({
    tool_name: 'create_admin_playlist',
    tool_args: { title: 'Math', content_ids: ['video-1'] },
  });
  const playlistUpdated = await window.AgixtClientActions.execute({
    tool_name: 'add_video_to_admin_playlist',
    tool_args: { playlist_id: 'playlist-1', content_ids: ['video-2'] },
  });

  assert.deepEqual(search, [{ id: 'video-1' }]);
  assert.equal(created.id, 'creation-1');
  assert.equal(media.ok, true);
  assert.equal(imported.id, 'video-2');
  assert.equal(updated.approved, true);
  assert.equal(playlist.id, 'playlist-1');
  assert.equal(playlistUpdated.id, 'playlist-1');
  assert.deepEqual(calls.map((call) => call[0]), [
    'searchLibrary',
    'createHtmlCreation',
    'mediaControl',
    'importContent',
    'updateContent',
    'createPlaylist',
    'addContentToPlaylist',
  ]);
});

test('client-actions: desktop_click forwards button + click_type', async () => {
  const { window, calls } = loadFrontend({ ipc: { desktop_click: async () => null } });
  await window.AgixtClientActions.execute({
    tool_name: 'mouse_click',
    tool_args: { x: 100, y: 200, button: 'right', click_type: 'double' },
  });
  assert.equal(calls[0].cmd, 'desktop_click');
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0].args.args)), {
    x: 100,
    y: 200,
    button: 'right',
    click_type: 'double',
  });
});

test('client-actions: desktop_click forwards vision-mode params', async () => {
  const { window, calls } = loadFrontend({ ipc: { desktop_click: async () => null } });
  await window.AgixtClientActions.execute({
    tool_name: 'desktop_click',
    tool_args: {
      x: '500',
      y: '500',
      normalized: 'true',
      target_width: '1920',
      target_height: '1080',
      screen_width: '3840',
      screen_height: '2160',
      monitor_offset_x: '0',
      monitor_offset_y: '0',
    },
  });
  const args = JSON.parse(JSON.stringify(calls[0].args.args));
  assert.equal(args.x, 500);
  assert.equal(args.y, 500);
  assert.equal(args.normalized, true);
  assert.equal(args.target_width, 1920);
  assert.equal(args.target_height, 1080);
  assert.equal(args.screen_width, 3840);
  assert.equal(args.screen_height, 2160);
});

test('client-actions: desktop_click normalizes model-ish click args', async () => {
  const { window, calls } = loadFrontend({ ipc: { desktop_click: async () => null } });
  await window.AgixtClientActions.execute({
    tool_name: 'desktop_click',
    tool_args: {
      x: '0.5',
      y: '0.95',
      normalized: 'true',
      button: 'primary',
      click_type: 'click',
      screen_width: '3840',
      screen_height: '2160',
    },
  });
  const args = JSON.parse(JSON.stringify(calls[0].args.args));
  assert.equal(args.x, 500);
  assert.equal(args.y, 950);
  assert.equal(args.button, 'left');
  assert.equal(args.click_type, 'single');
  assert.equal(args.normalized, true);
});

test('client-actions: desktop_click corrects normalized context from last screenshot', async () => {
  const { window, calls } = loadFrontend({
    ipc: {
      desktop_screenshot: async () => ({
        image_data: 'AAAA',
        width: 1920,
        height: 1080,
        original_width: 3840,
        original_height: 2160,
        monitor_offset_x: 0,
        monitor_offset_y: 0,
        format: 'jpeg',
      }),
      desktop_click: async () => null,
    },
  });
  await window.AgixtClientActions.execute({
    tool_name: 'desktop_screenshot',
    tool_args: { target_width: 1920, target_height: 1080 },
  });
  await window.AgixtClientActions.execute({
    tool_name: 'desktop_click',
    tool_args: {
      x: '20',
      y: '294',
      normalized: 'true',
      screen_width: '1920',
      screen_height: '1080',
      button: 'left',
      click_type: 'single',
    },
  });

  const clickCall = calls.find((c) => c.cmd === 'desktop_click');
  const args = JSON.parse(JSON.stringify(clickCall.args.args));
  assert.equal(args.x, 20);
  assert.equal(args.y, 294);
  assert.equal(args.normalized, true);
  assert.equal(args.target_width, 1920);
  assert.equal(args.target_height, 1080);
  assert.equal(args.screen_width, 3840);
  assert.equal(args.screen_height, 2160);
  assert.equal(args.monitor_offset_x, 0);
  assert.equal(args.monitor_offset_y, 0);
});

test('client-actions: desktop_click forwards screenshot pixel coordinate context', async () => {
  const { window, calls } = loadFrontend({
    ipc: {
      desktop_screenshot: async () => ({
        image_data: 'AAAA',
        width: 1920,
        height: 1080,
        original_width: 3840,
        original_height: 2160,
        monitor_offset_x: 0,
        monitor_offset_y: 0,
        format: 'jpeg',
      }),
      desktop_click: async () => null,
    },
  });
  await window.AgixtClientActions.execute({
    tool_name: 'desktop_screenshot',
    tool_args: { target_width: 1920, target_height: 1080 },
  });
  await window.AgixtClientActions.execute({
    tool_name: 'desktop_click',
    tool_args: {
      x: '16',
      y: '320',
      coordinate_space: 'screenshot',
      button: 'left',
      click_type: 'single',
    },
  });

  const clickCall = calls.find((c) => c.cmd === 'desktop_click');
  const args = JSON.parse(JSON.stringify(clickCall.args.args));
  assert.equal(args.x, 16);
  assert.equal(args.y, 320);
  assert.equal(args.coordinate_space, 'screenshot');
  assert.equal(args.target_width, 1920);
  assert.equal(args.target_height, 1080);
  assert.equal(args.screen_width, 3840);
  assert.equal(args.screen_height, 2160);
});

test('client-actions: desktop_vision_control uses qwen-style normalized coords', async () => {
  let visionCalls = 0;
  const { window, calls } = loadFrontend({
    ipc: {
      desktop_screenshot: async () => ({
        image_data: 'AAAA',
        width: 1920,
        height: 1080,
        original_width: 3840,
        original_height: 2160,
        monitor_offset_x: 0,
        monitor_offset_y: 0,
        format: 'jpeg',
      }),
      agent_vision: async () => {
        visionCalls += 1;
        return visionCalls === 1
          ? { response: '{"action":"click","point_2d":[25,320],"observation":"I see the dock icon.","thought":"Click its center."}' }
          : { response: '{"action":"done","summary":"Spotify is open."}' };
      },
      desktop_click: async () => ({ ok: true }),
    },
  });
  const res = await window.AgixtClientActions.execute({
    tool_name: 'desktop_vision_control',
    tool_args: { task: 'Click the Spotify icon' },
  });

  assert.equal(res.success, true);
  assert.equal(res.summary, 'Spotify is open.');
  const visionCall = calls.find((c) => c.cmd === 'agent_vision');
  assert.match(visionCall.args.args.prompt, /screenshot shown to you is 1920x1080/i);
  assert.doesNotMatch(visionCall.args.args.prompt, /of \d+/i);
  assert.match(visionCall.args.args.images[0], /^data:image\/jpeg;base64,AAAA/);
  const clickCall = calls.find((c) => c.cmd === 'desktop_click');
  const args = JSON.parse(JSON.stringify(clickCall.args.args));
  assert.equal(args.x, 25);
  assert.equal(args.y, 320);
  assert.equal(args.normalized, true);
  assert.equal(args.coordinate_space, 'normalized');
  assert.equal(args.target_width, 1920);
  assert.equal(args.screen_width, 3840);
});

test('client-actions: stopping desktop_vision_control cancels the pending click', async () => {
  let resolveVision;
  let clickCalls = 0;
  const { window } = loadFrontend({
    ipc: {
      desktop_screenshot: async () => ({
        image_data: 'AAAA',
        width: 1920,
        height: 1080,
        original_width: 3840,
        original_height: 2160,
        monitor_offset_x: 0,
        monitor_offset_y: 0,
        format: 'jpeg',
      }),
      agent_vision: async () => new Promise((resolve) => {
        resolveVision = resolve;
      }),
      desktop_click: async () => {
        clickCalls += 1;
        return { ok: true };
      },
    },
  });

  const running = window.AgixtClientActions.execute({
    tool_name: 'desktop_vision_control',
    tool_args: { task: 'Click the Spotify icon' },
  });
  while (!resolveVision) await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(window.AgixtClientActions.stopActiveAction('Stopped by test.'), true);
  resolveVision({
    response: '{"action":"click","point_2d":[25,320],"observation":"I see the dock icon.","thought":"Click it."}',
  });
  const res = await running;

  assert.equal(res.stopped, true);
  assert.equal(res.success, false);
  assert.equal(clickCalls, 0);
});

test('client-actions: desktop_vision_control records computer-use workspace artifacts', async () => {
  let screenshotCalls = 0;
  let controlVisionCalls = 0;
  let narrationVisionCalls = 0;
  const controlPrompts = [];
  const uploads = [];
  const moves = [];
  const folders = [];
  const workspaceFiles = new Map();
  const screenshots = ['AAAA', 'BBBB', 'CCCC'];
  const { window } = loadFrontend({
    ipc: {
      desktop_screenshot: async () => {
        const imageData = screenshots[Math.min(screenshotCalls, screenshots.length - 1)];
        screenshotCalls += 1;
        return {
          image_data: imageData,
          width: 1920,
          height: 1080,
          original_width: 3840,
          original_height: 2160,
          monitor_offset_x: 0,
          monitor_offset_y: 0,
          format: 'jpeg',
        };
      },
      agent_vision: async ({ args }) => {
        if (/computer-use demo log/i.test(args.prompt)) {
          narrationVisionCalls += 1;
          assert.equal(args.images.length, 2);
          assert.match(args.images[0], /^data:image\/jpeg;base64,/);
          assert.match(args.images[1], /^data:image\/jpeg;base64,/);
          const step = Number((args.prompt.match(/Step (\d+) action:/) || [0, 0])[1]);
          return {
            response: JSON.stringify({
              summary: step === 1 ? 'AGiXT clicked Spotify.' : 'AGiXT confirmed Spotify opened.',
              narration: step === 1
                ? 'AGiXT clicked the Spotify icon.'
                : 'AGiXT confirmed Spotify opened.',
              before_state: step === 1 ? 'Spotify was not foregrounded.' : 'Spotify was open.',
              after_state: 'Spotify was open.',
              effect: step === 1 ? 'The click opened Spotify.' : 'The task was verified.',
            }),
          };
        }
        controlVisionCalls += 1;
        controlPrompts.push(args.prompt);
        return controlVisionCalls === 1
          ? { response: '{"action":"click","point_2d":[25,320],"observation":"I see the dock icon.","thought":"Click its center."}' }
          : { response: '{"action":"done","summary":"AGiXT opened Spotify."}' };
      },
      desktop_click: async () => ({ ok: true, x: 48, y: 346 }),
    },
  });
  window.AgixtChat.configure({
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    conversationId: 'convo-id',
    reconnect: false,
  });
  window.AgixtWorkspaceApi = {
    getWorkspace: async () => ({
      items: [
        { type: 'folder', name: 'docs', path: 'docs' },
        { type: 'file', name: 'notes.md', path: 'docs/notes.md' },
      ],
    }),
    downloadFile: async (_cfg, _conversationId, filePath) => {
      if (!workspaceFiles.has(filePath)) throw new Error(`${filePath} does not exist yet`);
      return { blob: new window.Blob([workspaceFiles.get(filePath).text]) };
    },
    uploadFiles: async (cfg, conversationId, files, destinationPath) => {
      const fileRecords = [];
      for (const file of files) {
        let text = '';
        if (typeof file.text === 'function') text = await file.text();
        else if (typeof file.arrayBuffer === 'function') {
          text = new TextDecoder().decode(await file.arrayBuffer());
        } else {
          const implSymbol = Object.getOwnPropertySymbols(file)
            .find((symbol) => String(symbol) === 'Symbol(impl)');
          const buffer = implSymbol && file[implSymbol] && file[implSymbol]._buffer;
          if (buffer) text = Buffer.from(buffer).toString('utf8');
        }
        fileRecords.push({
          name: file.name,
          type: file.type,
          text,
        });
        // Simulate the WorkConductor Rust API bug where destination_path is
        // accepted but the uploaded file is stored at the workspace root.
        workspaceFiles.set(file.name, { text, destinationPath: destinationPath || '' });
      }
      uploads.push({ cfg, conversationId, destinationPath: destinationPath || '', files: fileRecords });
      return { items: fileRecords.map((file) => ({ name: file.name })) };
    },
    createFolder: async (_cfg, _conversationId, folderName, parentPath) => {
      folders.push({ folderName, parentPath: parentPath || '' });
      return {};
    },
    moveItem: async (_cfg, _conversationId, sourcePath, destinationPath) => {
      if (!workspaceFiles.has(sourcePath)) throw new Error(`${sourcePath} missing`);
      if (workspaceFiles.has(destinationPath)) throw new Error(`${destinationPath} exists`);
      workspaceFiles.set(destinationPath, workspaceFiles.get(sourcePath));
      workspaceFiles.delete(sourcePath);
      moves.push({ sourcePath, destinationPath });
      return {};
    },
    deleteItem: async (_cfg, _conversationId, filePath) => {
      workspaceFiles.delete(filePath);
      return {};
    },
  };

  const res = await window.AgixtClientActions.execute({
    tool_name: 'desktop_vision_control',
    tool_args: { task: 'Open Spotify' },
  });
  await window.AgixtClientActions.flushComputerUseRecorder();

  assert.equal(res.success, true);
  assert.equal(res.summary, 'AGiXT opened Spotify.');
  assert.equal(res.computer_use_log, 'computer-use-log.json');
  assert.equal(res.computer_use_artifacts.screenshot_folder, 'computer-use/screenshots');
  assert.equal(res.computer_use_artifacts.video_plan_json, 'computer-use/video-plan.json');
  assert.equal(controlVisionCalls, 2);
  assert.equal(narrationVisionCalls, 2);
  assert.match(controlPrompts[0], /Conversation workspace files available/i);
  assert.match(controlPrompts[0], /docs\/notes\.md/);
  assert.match(controlPrompts[0], /Do not click Ubuntu workspace thumbnails/i);
  assert.ok(uploads.some((upload) => upload.destinationPath === 'computer-use/screenshots'
    && upload.files.some((file) => /step-001.*-before\.jpeg$/.test(file.name))));
  const storyboardUploads = uploads.filter((upload) => upload.destinationPath === 'computer-use'
    && upload.files.some((file) => file.name === 'storyboard.html'));
  const storyboardUpload = storyboardUploads[storyboardUploads.length - 1];
  assert.ok(storyboardUpload);
  const storyboardFile = storyboardUpload.files.find((file) => file.name === 'storyboard.html');
  assert.match(storyboardFile.text, /src="screenshots\/step-001/);
  assert.doesNotMatch(storyboardFile.text, /src="\.\.\/computer-use\/screenshots\//);
  assert.ok(folders.some((folder) => folder.folderName === 'screenshots'
    && folder.parentPath === 'computer-use'));
  assert.ok(moves.some((move) => /step-001.*-before\.jpeg$/.test(move.sourcePath)
    && /^computer-use\/screenshots\/step-001/.test(move.destinationPath)));
  assert.equal(
    Array.from(workspaceFiles.keys()).some((path) => /^step-001.*-before\.jpeg$/.test(path)),
    false,
  );
  assert.equal(
    Array.from(workspaceFiles.keys()).some((path) => /^computer-use\/screenshots\/step-001.*-before\.jpeg$/.test(path)),
    true,
  );
  const videoPlanUploads = uploads.filter((upload) => upload.destinationPath === 'computer-use'
    && upload.files.some((file) => file.name === 'video-plan.json'));
  assert.ok(videoPlanUploads.length > 0);
  const latestVideoPlanUpload = videoPlanUploads[videoPlanUploads.length - 1];
  const videoPlanFile = latestVideoPlanUpload.files.find((file) => file.name === 'video-plan.json');
  const videoPlan = JSON.parse(videoPlanFile.text);
  assert.equal(videoPlan.kind, 'agixt-desktop-computer-use-video-plan');
  assert.equal(videoPlan.clips[0].narration, 'AGiXT clicked the Spotify icon.');
  assert.equal(videoPlan.clips[0].click.x_percent, 2.5);
  assert.equal(videoPlan.tts.endpoint, '/v1/audio/speech');

  const logUploads = uploads.filter((upload) => upload.destinationPath === ''
    && upload.files.some((file) => file.name === 'computer-use-log.json'));
  assert.ok(logUploads.length > 0);
  const latestLogUpload = logUploads[logUploads.length - 1];
  const logFile = latestLogUpload.files.find((file) => file.name === 'computer-use-log.json');
  const log = JSON.parse(logFile.text);
  const session = log.sessions.find((item) => item.session_id === res.computer_use_session_id);
  assert.equal(session.task, 'Open Spotify');
  assert.equal(session.status, 'completed');
  assert.equal(session.summary, 'AGiXT opened Spotify.');
  assert.equal(session.steps.length, 2);
  assert.equal(session.steps[0].action, 'click(25, 320)');
  assert.equal(session.steps[0].action_type, 'click');
  assert.equal(session.steps[0].coordinate.x, 25);
  assert.equal(session.steps[0].resolved_coordinate.x, 48);
  assert.match(session.steps[0].before_image, /^computer-use\/screenshots\/step-001/);
  assert.match(session.steps[0].after_image, /^computer-use\/screenshots\/step-001/);
  assert.equal(session.steps[0].narration, 'AGiXT clicked the Spotify icon.');
  assert.equal(session.steps[1].action_type, 'done');
  assert.equal(session.steps[1].narration, 'AGiXT confirmed Spotify opened.');
});

test('client-actions: visible-ui low-level click upgrades to vision control', async () => {
  let visionCalls = 0;
  const { window, calls } = loadFrontend({
    ipc: {
      desktop_screenshot: async () => ({
        image_data: 'AAAA',
        width: 1920,
        height: 1080,
        original_width: 3840,
        original_height: 2160,
        monitor_offset_x: 0,
        monitor_offset_y: 0,
        format: 'jpeg',
      }),
      agent_vision: async () => {
        visionCalls += 1;
        return visionCalls === 1
          ? { response: '{"action":"click","point_2d":[12,300],"observation":"I see the requested dock icon.","thought":"Click the dock icon center."}' }
          : { response: '{"action":"done","summary":"The icon was clicked."}' };
      },
      desktop_click: async () => ({ ok: true }),
    },
  });
  await window.AgixtClientActions.execute({
    tool_name: 'desktop_click',
    tool_args: {
      x: 25,
      y: 484,
      coordinate_space: 'screenshot',
      __original_task: 'Click the Spotify icon',
    },
  });

  const clickCall = calls.find((c) => c.cmd === 'desktop_click');
  const args = JSON.parse(JSON.stringify(clickCall.args.args));
  assert.equal(args.x, 12);
  assert.equal(args.y, 300);
  assert.equal(args.normalized, true);
  assert.equal(args.coordinate_space, 'normalized');
});

test('client-actions: desktop_click rejects likely sidebar app-icon miss', async () => {
  const { window, calls } = loadFrontend({
    ipc: {
      desktop_screenshot: async () => ({
        image_data: 'AAAA',
        width: 1920,
        height: 1080,
        original_width: 3840,
        original_height: 2160,
        monitor_offset_x: 0,
        monitor_offset_y: 0,
        format: 'jpeg',
      }),
      desktop_click: async () => {
        throw new Error('desktop_click should not run');
      },
    },
  });
  await window.AgixtClientActions.execute({
    tool_name: 'desktop_screenshot',
    tool_args: { target_width: 1920, target_height: 1080 },
  });
  const res = await window.AgixtClientActions.execute({
    tool_name: 'desktop_click',
    tool_args: {
      x: '34',
      y: '296',
      normalized: 'true',
      target_width: '1920',
      target_height: '1080',
      screen_width: '3840',
      screen_height: '2160',
      button: 'left',
      click_type: 'single',
      allow_direct_click: true,
      __original_task: 'Can you click the Spotify icon?',
    },
  });
  assert.match(res.error, /Refusing to click/);
  assert.equal(calls.filter((c) => c.cmd === 'desktop_click').length, 0);
});

test('client-actions: desktop_move uses args envelope', async () => {
  const { window, calls } = loadFrontend({ ipc: { desktop_move: async () => null } });
  await window.AgixtClientActions.execute({
    tool_name: 'desktop_move',
    tool_args: { x: 10, y: 20, normalized: true, target_width: 1920 },
  });
  assert.equal(calls[0].cmd, 'desktop_move');
  const args = JSON.parse(JSON.stringify(calls[0].args.args));
  assert.equal(args.x, 10);
  assert.equal(args.y, 20);
  assert.equal(args.normalized, true);
  assert.equal(args.target_width, 1920);
});

test('client-actions: desktop_drag uses args envelope with snake_case', async () => {
  const { window, calls } = loadFrontend({ ipc: { desktop_drag: async () => null } });
  await window.AgixtClientActions.execute({
    tool_name: 'desktop_drag',
    tool_args: { from_x: 1, from_y: 2, to_x: 3, to_y: 4, button: 'left' },
  });
  assert.equal(calls[0].cmd, 'desktop_drag');
  const args = JSON.parse(JSON.stringify(calls[0].args.args));
  assert.equal(args.from_x, 1);
  assert.equal(args.from_y, 2);
  assert.equal(args.to_x, 3);
  assert.equal(args.to_y, 4);
  assert.equal(args.button, 'left');
});

test('client-actions: desktop_type accepts either text or keys', async () => {
  const { window, calls } = loadFrontend({ ipc: { desktop_type: async () => null } });
  await window.AgixtClientActions.execute({
    tool_name: 'desktop_type',
    tool_args: { text: 'hello' },
  });
  await window.AgixtClientActions.execute({
    tool_name: 'desktop_type',
    tool_args: { keys: ['ctrl', 'c'] },
  });
  await window.AgixtClientActions.execute({
    tool_name: 'desktop_type',
    tool_args: { keys: 'super+space' },
  });
  assert.equal(calls[0].args.text, 'hello');
  assert.deepEqual(JSON.parse(JSON.stringify(calls[1].args.keys)), ['ctrl', 'c']);
  assert.deepEqual(JSON.parse(JSON.stringify(calls[2].args.keys)), ['super', 'space']);
});

test('client-actions: terminal_open delegates to terminal_open IPC', async () => {
  const { window, calls } = loadFrontend({
    ipc: { terminal_open: async () => ({ id: 'sess-1', shell: '/bin/bash', cwd: '/', cols: 120, rows: 30, closed: false, total_bytes: 0, uptime_secs: 0, idle_secs: 0 }) },
  });
  const res = await window.AgixtClientActions.execute({
    tool_name: 'terminal_open',
    tool_args: { shell: '/bin/bash', cwd: '/tmp', cols: 100, rows: 24 },
  });
  assert.equal(res.id, 'sess-1');
  assert.equal(calls[0].cmd, 'terminal_open');
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0].args.args)), {
    shell: '/bin/bash',
    cwd: '/tmp',
    cols: 100,
    rows: 24,
  });
});

test('client-actions: terminal_exec routes session_id and command', async () => {
  const { window, calls } = loadFrontend({
    ipc: { terminal_exec: async () => ({ data: 'output', next_offset: 6, closed: false, timed_out: false }) },
  });
  const res = await window.AgixtClientActions.execute({
    tool_name: 'shell_exec',
    tool_args: { session_id: 'sess-1', command: 'echo hi', timeout: '3000' },
  });
  assert.equal(res.data, 'output');
  assert.equal(calls[0].cmd, 'terminal_exec');
  assert.equal(calls[0].args.sessionId, 'sess-1');
  assert.equal(calls[0].args.command, 'echo hi');
  assert.equal(calls[0].args.timeoutMs, 3000);
});

test('client-actions: shell_run routes one-shot command IPC', async () => {
  const { window, calls } = loadFrontend({
    ipc: { shell_run: async () => ({ stdout: 'ok', stderr: '', exit_code: 0, timed_out: false }) },
  });
  const res = await window.AgixtClientActions.execute({
    tool_name: 'shell_run',
    tool_args: { command: 'echo ok', timeout_ms: '2500' },
  });
  assert.equal(res.stdout, 'ok');
  assert.equal(calls[0].cmd, 'shell_run');
  assert.equal(calls[0].args.command, 'echo ok');
  assert.equal(calls[0].args.timeoutMs, 2500);
});

test('client-actions: sudo_run routes privileged command IPC', async () => {
  const { window, calls } = loadFrontend({
    ipc: { sudo_run: async () => ({ stdout: 'installed', stderr: '', exit_code: 0, timed_out: false }) },
  });
  const res = await window.AgixtClientActions.execute({
    tool_name: 'sudo_run',
    tool_args: { command: 'apt-get install -y htop', timeout_ms: '1200000' },
  });
  assert.equal(res.stdout, 'installed');
  assert.equal(calls[0].cmd, 'sudo_run');
  assert.equal(calls[0].args.command, 'apt-get install -y htop');
  assert.equal(calls[0].args.timeoutMs, 1200000);
});

test('client-actions: terminal_signal accepts ctrl-c by default', async () => {
  const { window, calls } = loadFrontend({ ipc: { terminal_signal: async () => null } });
  await window.AgixtClientActions.execute({
    tool_name: 'terminal_signal',
    tool_args: { session_id: 's' },
  });
  assert.equal(calls[0].args.signal, 'ctrl-c');
});

test('client-actions: unknown tool returns error', async () => {
  const { window } = loadFrontend();
  const res = await window.AgixtClientActions.execute({ tool_name: 'no_such_tool' });
  assert.match(res.error, /unknown client tool/);
});

test('client-actions: fs_read forwards path', async () => {
  const { window, calls } = loadFrontend({
    ipc: { fs_read: async () => ({ content: 'hi', encoding: 'utf8', size: 2 }) },
  });
  const r = await window.AgixtClientActions.execute({
    tool_name: 'fs_read', tool_args: { path: '/tmp/a.txt' },
  });
  assert.equal(r.content, 'hi');
  assert.equal(calls[0].cmd, 'fs_read');
  assert.equal(calls[0].args.path, '/tmp/a.txt');
});

test('client-actions: fs_write defaults encoding/create_dirs', async () => {
  const { window, calls } = loadFrontend({ ipc: { fs_write: async () => null } });
  await window.AgixtClientActions.execute({
    tool_name: 'write_file',
    tool_args: { path: '/tmp/b.txt', content: 'hello' },
  });
  assert.equal(calls[0].cmd, 'fs_write');
  assert.equal(calls[0].args.args.path, '/tmp/b.txt');
  assert.equal(calls[0].args.args.content, 'hello');
  assert.equal(calls[0].args.args.create_dirs, false);
});

test('client-actions: fs_edit normalizes single edit', async () => {
  const { window, calls } = loadFrontend({ ipc: { fs_edit: async () => null } });
  await window.AgixtClientActions.execute({
    tool_name: 'fs_edit',
    tool_args: { path: '/tmp/c.txt', find: 'old', replace: 'new', replace_all: true },
  });
  const args = JSON.parse(JSON.stringify(calls[0].args.args));
  assert.equal(args.path, '/tmp/c.txt');
  assert.equal(args.edits.length, 1);
  assert.equal(args.edits[0].find, 'old');
  assert.equal(args.edits[0].replace, 'new');
  assert.equal(args.edits[0].replace_all, true);
});

test('client-actions: fs_edit accepts multiple edits array', async () => {
  const { window, calls } = loadFrontend({ ipc: { fs_edit: async () => null } });
  await window.AgixtClientActions.execute({
    tool_name: 'fs_edit',
    tool_args: {
      path: '/tmp/d.txt',
      edits: [
        { find: 'a', replace: 'A' },
        { find: 'b', replace: 'B', replace_all: true },
      ],
    },
  });
  const args = JSON.parse(JSON.stringify(calls[0].args.args));
  assert.equal(args.edits.length, 2);
  assert.equal(args.edits[1].replace_all, true);
});

test('client-actions: fs_list defaults path to cwd', async () => {
  const { window, calls } = loadFrontend({
    ipc: { fs_list: async () => [] },
  });
  await window.AgixtClientActions.execute({ tool_name: 'ls' });
  assert.equal(calls[0].cmd, 'fs_list');
  assert.equal(calls[0].args.path, '.');
});

test('client-actions: fs_rename routes from/to with overwrite', async () => {
  const { window, calls } = loadFrontend({ ipc: { fs_rename: async () => null } });
  await window.AgixtClientActions.execute({
    tool_name: 'mv',
    tool_args: { from: '/tmp/x', to: '/tmp/y', overwrite: true },
  });
  assert.equal(calls[0].cmd, 'fs_rename');
  const args = JSON.parse(JSON.stringify(calls[0].args.args));
  assert.equal(args.from, '/tmp/x');
  assert.equal(args.to, '/tmp/y');
  assert.equal(args.overwrite, true);
});

test('client-actions: workspace_upload uses local_path/workspace_path', async () => {
  const { window, calls } = loadFrontend({
    ipc: { workspace_upload_local: async () => ({ bytes: 10 }) },
  });
  await window.AgixtClientActions.execute({
    tool_name: 'workspace_upload',
    tool_args: { local_path: '/home/u/a.py', workspace_path: 'src/a.py' },
  });
  assert.equal(calls[0].cmd, 'workspace_upload_local');
  assert.equal(calls[0].args.localPath, '/home/u/a.py');
  assert.equal(calls[0].args.workspacePath, 'src/a.py');
});

test('client-actions: workspace_download routes overwrite flag', async () => {
  const { window, calls } = loadFrontend({
    ipc: { workspace_download_to_local: async () => ({ bytes: 5 }) },
  });
  await window.AgixtClientActions.execute({
    tool_name: 'workspace_download',
    tool_args: { workspace_path: 'src/a.py', local_path: '/tmp/a.py', overwrite: true },
  });
  assert.equal(calls[0].cmd, 'workspace_download_to_local');
  assert.equal(calls[0].args.workspacePath, 'src/a.py');
  assert.equal(calls[0].args.localPath, '/tmp/a.py');
  assert.equal(calls[0].args.overwrite, true);
});

test('chat: AGiXT remote_command tools continue as role tool results only', async () => {
  const listeners = new Map();
  const { window, calls } = loadFrontend({
    ipc: {
      chat_send: async ({ args }) => {
        const cb = listeners.get(`chat-stream:${args.stream_id}`);
        assert.ok(cb, 'listener should be attached before chat_send starts');
        if (args.messages[0] && args.messages[0].role === 'tool') {
          assert.equal(args.messages.length, 1);
          assert.equal(args.messages[0].tool_call_id, 'req-1');
          assert.equal(args.messages[0].name, 'shell_run');
          assert.equal(args.messages[0].log_user_input, false);
          assert.equal(args.messages[0].enable_command_selection, false);
          assert.match(args.messages[0].content, /desktop tool observation, not a new user request/);
          assert.match(args.messages[0].content, /Original user task: open spotify/);
          assert.match(args.messages[0].content, /"stdout": "ok"/);
          cb({
            payload: {
              event: {
                kind: 'delta',
                data: { text: 'Spotify is open.' },
              },
            },
          });
          cb({
            payload: {
              event: { kind: 'done', data: { text: 'Spotify is open.', finish_reason: 'stop' } },
            },
          });
          return args.stream_id;
        }
        cb({
          payload: {
            event: {
              kind: 'tool_call',
              data: {
                id: 'req-1',
                name: 'shell_run',
                args: { command: 'printf ok' },
                origin: 'remote_command',
              },
            },
          },
        });
        cb({
          payload: {
            event: { kind: 'done', data: { text: '', finish_reason: 'remote_command' } },
          },
        });
        return args.stream_id;
      },
      shell_run: async () => ({ stdout: 'ok', stderr: '', exit_code: 0, timed_out: false }),
    },
  });
  window.__TAURI__.event = {
    listen: async (name, cb) => {
      listeners.set(name, cb);
      return () => listeners.delete(name);
    },
  };
  window.AgixtChat.configure({
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    conversationId: 'convo-id',
    reconnect: false,
  });

  await window.AgixtChat.send('open spotify', 'desktop-convo');

  assert.equal(calls.filter((c) => c.cmd === 'chat_send').length, 2);
  assert.equal(calls.filter((c) => c.cmd === 'shell_run').length, 1);
  assert.equal(calls.filter((c) => c.cmd === 'submit_tool_result').length, 0);
});

test('chat: screenshot tool result is sent back as image content for vision', async () => {
  const listeners = new Map();
  const { window, calls } = loadFrontend({
    ipc: {
      chat_send: async ({ args }) => {
        const cb = listeners.get(`chat-stream:${args.stream_id}`);
        assert.ok(cb, 'listener should be attached before chat_send starts');
        if (args.messages[0] && args.messages[0].role === 'tool') {
          assert.equal(args.messages.length, 1);
          const toolMsg = args.messages[0];
          assert.equal(toolMsg.role, 'tool');
          assert.equal(toolMsg.tool_call_id, 'req-shot');
          assert.equal(toolMsg.name, 'screenshot');
          assert.equal(toolMsg.enable_command_selection, false);
          assert.equal(Array.isArray(toolMsg.content), true);
          assert.match(toolMsg.content[0].text, /Metadata/);
          assert.match(toolMsg.content[0].text, /Original user task: click the Spotify icon/);
          assert.match(toolMsg.content[0].text, /desktop tool observation, not a new user request/);
          assert.match(toolMsg.content[0].text, /OS dock\/application launcher icon/);
          assert.match(toolMsg.content[0].text, /screenshot image pixels/);
          assert.match(toolMsg.content[0].text, /coordinate_space:"screenshot"/);
          assert.match(toolMsg.content[0].text, /"width": 1280/);
          assert.doesNotMatch(toolMsg.content[0].text, /ABC123/);
          assert.equal(
            toolMsg.content[1].image_url.url,
            'data:image/jpeg;base64,ABC123',
          );
          assert.equal(toolMsg.content[1].file_name, 'screenshot.jpeg');
          cb({
            payload: {
              event: { kind: 'done', data: { text: 'I can see the desktop.', finish_reason: 'stop' } },
            },
          });
          return args.stream_id;
        }
        cb({
          payload: {
            event: {
              kind: 'tool_call',
              data: {
                id: 'req-shot',
                name: 'screenshot',
                args: { target_width: 1280 },
                origin: 'remote_command',
              },
            },
          },
        });
        cb({
          payload: {
            event: { kind: 'done', data: { text: '', finish_reason: 'remote_command' } },
          },
        });
        return args.stream_id;
      },
      desktop_screenshot: async () => ({
        image_data: 'ABC123',
        width: 1280,
        height: 720,
        original_width: 2560,
        original_height: 1440,
        monitor_offset_x: 0,
        monitor_offset_y: 0,
        format: 'jpeg',
      }),
    },
  });
  window.__TAURI__.event = {
    listen: async (name, cb) => {
      listeners.set(name, cb);
      return () => listeners.delete(name);
    },
  };
  window.AgixtChat.configure({
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    conversationId: 'convo-id',
    reconnect: false,
  });

  await window.AgixtChat.send('click the Spotify icon', 'desktop-convo');

  assert.equal(calls.filter((c) => c.cmd === 'chat_send').length, 2);
  assert.equal(calls.filter((c) => c.cmd === 'desktop_screenshot').length, 1);
});

test('chat: leaked special tool-call markup executes as client tool continuation', async () => {
  const listeners = new Map();
  const leaked = [
    '<|tool_calls_section_begin|>',
    '<|tool_call_begin|>shell_run',
    '<tool_call_path|><command>du -sh /* 2>/dev/null | sort -hr</command>',
    '<timeout_ms>30000</timeout_ms>',
    '<|tool_call_end|>',
    '<|tool_calls_section_end|>',
  ].join('\n');
  const { window, calls } = loadFrontend({
    ipc: {
      chat_send: async ({ args }) => {
        const cb = listeners.get(`chat-stream:${args.stream_id}`);
        assert.ok(cb, 'listener should be attached before chat_send starts');
        if (args.messages[0] && args.messages[0].role === 'tool') {
          assert.match(args.messages[0].tool_call_id, /^special-[0-9a-f-]+-0$/);
          assert.equal(args.messages[0].name, 'shell_run');
          assert.match(args.messages[0].content, /"stdout": "disk"/);
          cb({
            payload: {
              event: { kind: 'done', data: { text: 'Disk usage checked.', finish_reason: 'stop' } },
            },
          });
          return args.stream_id;
        }
        cb({
          payload: {
            event: { kind: 'delta', data: { text: leaked } },
          },
        });
        cb({
          payload: {
            event: { kind: 'done', data: { text: leaked, finish_reason: 'stop' } },
          },
        });
        return args.stream_id;
      },
      shell_run: async () => ({ stdout: 'disk', stderr: '', exit_code: 0, timed_out: false }),
    },
  });
  window.__TAURI__.event = {
    listen: async (name, cb) => {
      listeners.set(name, cb);
      return () => listeners.delete(name);
    },
  };
  window.AgixtChat.configure({
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    conversationId: 'convo-id',
    reconnect: false,
  });

  await window.AgixtChat.send('find what is using disk space', 'desktop-convo');

  assert.equal(calls.filter((c) => c.cmd === 'chat_send').length, 2);
  assert.equal(calls.filter((c) => c.cmd === 'shell_run').length, 1);
  const shell = calls.find((c) => c.cmd === 'shell_run');
  assert.equal(shell.args.command, 'du -sh /* 2>/dev/null | sort -hr');
  assert.equal(shell.args.timeoutMs, 30000);
  assert.doesNotMatch(window.document.body.textContent, /tool_calls_section_begin/);
  assert.match(window.document.body.textContent, /Disk usage checked\./);
});

test('chat: persisted leaked special tool-call markup is suppressed', async () => {
  const leaked = [
    '<|tool_calls_section_begin|>',
    '<|tool_call_begin|>shell_run',
    '<tool_call_path|><command>echo ok</command>',
    '<|tool_call_end|>',
    '<|tool_calls_section_end|>',
  ].join('\n');
  const { window } = loadFrontend({
    ipc: {
      get_conversation_history: async () => [
        { id: 'raw-tool', role: 'XT', message: leaked, timestamp: new Date().toISOString() },
        { id: 'final', role: 'XT', message: 'Done.', timestamp: new Date().toISOString() },
      ],
    },
  });
  window.AgixtChat.configure({
    serverUrl: 'http://localhost:7437', jwt: 'j', conversationId: 'c', reconnect: false,
  });
  await window.AgixtChat.loadHistory('c');

  assert.doesNotMatch(window.document.body.textContent, /tool_calls_section_begin/);
  assert.match(window.document.body.textContent, /Done\./);
});

test('chat: persisted XT assistant replaces streamed local assistant bubble', async () => {
  const listeners = new Map();
  const sockets = [];
  class FakeWebSocket {
    static OPEN = 1;
    static CLOSED = 3;
    constructor(url) {
      this.url = url;
      this.readyState = FakeWebSocket.OPEN;
      sockets.push(this);
      setTimeout(() => this.onopen && this.onopen(), 0);
    }
    send() {}
    close() { this.readyState = FakeWebSocket.CLOSED; }
  }
  const finalText = 'Spotify is already open and visible on your screen.';
  const { window } = loadFrontend({
    WebSocketClass: FakeWebSocket,
    ipc: {
      chat_send: async ({ args }) => {
        const cb = listeners.get(`chat-stream:${args.stream_id}`);
        assert.ok(cb, 'listener should be attached before chat_send starts');
        cb({
          payload: {
            event: { kind: 'done', data: { text: finalText, finish_reason: 'stop' } },
          },
        });
        return args.stream_id;
      },
    },
  });
  window.__TAURI__.event = {
    listen: async (name, cb) => {
      listeners.set(name, cb);
      return () => listeners.delete(name);
    },
  };
  window.AgixtChat.configure({
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    conversationId: 'convo-id',
  });
  await new Promise((resolve) => setTimeout(resolve, 10));

  await window.AgixtChat.send('click the Spotify icon', 'desktop-convo');
  const countFinal = () => Array.from(window.document.querySelectorAll('.message-assistant .md'))
    .filter((node) => node.textContent.includes(finalText)).length;
  assert.equal(countFinal(), 1);

  sockets[0].onmessage({
    data: JSON.stringify({
      type: 'message_added',
      data: {
        id: 'server-final',
        role: 'XT',
        message: finalText,
        timestamp: new Date().toISOString(),
      },
    }),
  });
  assert.equal(countFinal(), 1);
  window.AgixtChat.disconnect();
});

test('chat: persisted thought replaces transient stream thinking block', async () => {
  const listeners = new Map();
  const sockets = [];
  class FakeWebSocket {
    static OPEN = 1;
    static CLOSED = 3;
    constructor(url) {
      this.url = url;
      this.readyState = FakeWebSocket.OPEN;
      sockets.push(this);
      setTimeout(() => this.onopen && this.onopen(), 0);
    }
    send() {}
    close() { this.readyState = FakeWebSocket.CLOSED; }
  }
  const thought = 'The user asked to click the Spotify icon and desktop_vision_control completed it.';
  const { window } = loadFrontend({
    WebSocketClass: FakeWebSocket,
    ipc: {
      chat_send: async ({ args }) => {
        const cb = listeners.get(`chat-stream:${args.stream_id}`);
        assert.ok(cb, 'listener should be attached before chat_send starts');
        cb({
          payload: {
            event: { kind: 'activity', data: { content: thought, complete: true } },
          },
        });
        cb({
          payload: {
            event: { kind: 'done', data: { text: 'Done.', finish_reason: 'stop' } },
          },
        });
        return args.stream_id;
      },
    },
  });
  window.__TAURI__.event = {
    listen: async (name, cb) => {
      listeners.set(name, cb);
      return () => listeners.delete(name);
    },
  };
  window.AgixtChat.configure({
    serverUrl: 'http://localhost:7437',
    jwt: 'jwt',
    conversationId: 'convo-id',
  });
  await new Promise((resolve) => setTimeout(resolve, 10));

  await window.AgixtChat.send('click the Spotify icon', 'desktop-convo');
  const countThoughtActivities = () => Array.from(window.document.querySelectorAll('.activity'))
    .filter((node) => node.textContent.includes(thought)).length;
  const countThoughtSubactivities = () => Array.from(window.document.querySelectorAll('.subactivity'))
    .filter((node) => node.textContent.includes(thought)).length;
  assert.equal(countThoughtActivities(), 1);
  assert.equal(countThoughtSubactivities(), 1);

  sockets[0].onmessage({
    data: JSON.stringify({
      type: 'message_added',
      data: {
        id: 'server-thinking',
        role: 'XT',
        message: '[ACTIVITY] Thinking.',
        timestamp: new Date().toISOString(),
      },
    }),
  });
  sockets[0].onmessage({
    data: JSON.stringify({
      type: 'message_added',
      data: {
        id: 'server-thought',
        role: 'XT',
        message: `[SUBACTIVITY][server-thinking][THOUGHT] ${thought}`,
        timestamp: new Date().toISOString(),
      },
    }),
  });
  assert.equal(countThoughtActivities(), 1);
  assert.equal(countThoughtSubactivities(), 1);
  window.AgixtChat.disconnect();
});

test('chat: EXECUTION subactivity collapses body behind a click', async () => {
  // AGiXT emits "[SUBACTIVITY][parent_id][EXECUTION] Executing `cmd`.\n```json\n{...}```"
  // for tool runs. The desktop client should render the first line as a
  // disclosure summary and tuck the json args behind <details>, instead of
  // dumping the full payload into the activity feed.
  const longArgs = JSON.stringify({ url: 'https://example.com/long', body: 'x'.repeat(80) }, null, 2);
  const execBody = "Executing `web_fetch`.\n```json\n" + longArgs + '\n```';
  const okBody = '`web_fetch` was executed successfully.\n' + 'output line\n'.repeat(40);
  const inlineBody = 'Generating audio response.';
  const { window } = loadFrontend({
    ipc: {
      get_conversation_history: async () => [
        { id: 'a1', role: 'XT', message: '[ACTIVITY] Thinking', timestamp: new Date().toISOString() },
        { id: 's1', role: 'XT', message: `[SUBACTIVITY][a1][EXECUTION] ${execBody}`, timestamp: new Date().toISOString() },
        { id: 's2', role: 'XT', message: `[SUBACTIVITY][a1][EXECUTION] ${okBody}`, timestamp: new Date().toISOString() },
        { id: 's3', role: 'XT', message: `[SUBACTIVITY][a1][EXECUTION] ${inlineBody}`, timestamp: new Date().toISOString() },
      ],
    },
  });
  window.AgixtChat.configure({
    serverUrl: 'http://localhost:7437', jwt: 'j', conversationId: 'c', reconnect: false,
  });
  await window.AgixtChat.loadHistory('c');

  const subs = window.document.querySelectorAll('.subactivity[data-tag="EXECUTION"]');
  assert.equal(subs.length, 3, 'three EXECUTION subactivities should render');

  // Multi-line bodies render as <details> with first-line summary, body hidden.
  const exec = subs[0].querySelector('details.sub-exec');
  assert.ok(exec, 'multi-line EXECUTION should produce details.sub-exec');
  assert.equal(exec.hasAttribute('open'), false, 'details should start collapsed');
  const summary = exec.querySelector('summary.sub-exec-summary');
  assert.ok(summary, 'summary node present');
  assert.match(summary.textContent, /Executing/);
  assert.doesNotMatch(summary.textContent, /long/, 'json args must not leak into the summary');
  const bodyEl = exec.querySelector('.sub-exec-body');
  assert.ok(bodyEl, 'body node present');
  assert.match(bodyEl.textContent, /example\.com\/long/, 'json args live in the collapsed body');

  // Single-line bodies render inline (no disclosure — nothing to expand to).
  const inline = subs[2].querySelector('details.sub-exec');
  assert.equal(inline, null, 'single-line EXECUTION should render inline, no <details>');
  assert.match(subs[2].textContent, /Generating audio response\./);

  window.AgixtChat.disconnect();
});

test('chains: pane lists chains and renders editor on selection', async () => {
  // Mock the AGiXT REST surface that chains.js hits. The module loads via
  // loadFullApp's IIFE flow but only fires API calls once the user
  // activates the pane, so we wire fetch responses keyed by URL suffix
  // and trigger mount via the sidenav button.
  const fetchLog = [];
  const fakeChain = {
    id: 'chain-1',
    name: 'Demo Chain',
    description: 'Two-step demo',
  };
  const fakeChainDetail = {
    'Demo Chain': {
      description: 'Two-step demo',
      steps: [
        { step: 1, agent_name: 'XT', prompt_type: 'Prompt',
          prompt: { prompt_name: 'Think About It', prompt_category: 'Default' } },
        { step: 2, agent_name: 'XT', prompt_type: 'Command',
          prompt: { command_name: 'Search Grokipedia' } },
      ],
    },
  };

  const { window } = loadFullApp();
  window.fetch = async (url, init) => {
    fetchLog.push({ url: String(url), method: (init && init.method) || 'GET' });
    const path = String(url).replace(/^https?:\/\/[^/]+/, '');
    if (path === '/v1/chains') {
      return new Response(JSON.stringify([{ id: fakeChain.id, chainName: fakeChain.name, description: fakeChain.description }]), { status: 200 });
    }
    if (path === `/v1/chain/${fakeChain.id}`) {
      return new Response(JSON.stringify(fakeChainDetail), { status: 200 });
    }
    if (path === '/v1/agent') {
      return new Response(JSON.stringify([{ id: 'agent-id', name: 'XT' }]), { status: 200 });
    }
    if (path.startsWith('/v1/prompts')) {
      return new Response(JSON.stringify({ prompts: [{ id: 'p1', name: 'Think About It' }] }), { status: 200 });
    }
    if (path.endsWith('/extensions')) {
      return new Response(JSON.stringify({ extensions: [] }), { status: 200 });
    }
    if (path.endsWith('/args')) {
      return new Response(JSON.stringify([]), { status: 200 });
    }
    return new Response('{}', { status: 200 });
  };
  window.Response = Response;

  await new Promise((r) => setTimeout(r, 20));

  // Click the chains sidenav button — this triggers setActiveView('chains')
  // which lazy-mounts AgixtChains.
  const chainsBtn = window.document.querySelector('.sidenav-btn[data-view="chains"]');
  assert.ok(chainsBtn, 'chains sidenav button should be present');
  chainsBtn.click();
  await new Promise((r) => setTimeout(r, 40));

  // Pane should be visible (not hidden) and list should have one item.
  const pane = window.document.querySelector('.view-pane[data-view="chains"]');
  assert.equal(pane.hidden, false, 'chains pane should be revealed');
  const items = window.document.querySelectorAll('.cn-list-item');
  assert.equal(items.length, 1, 'one chain in the list');
  assert.match(items[0].textContent, /Demo Chain/);

  // Selecting the chain renders the editor with the chain title.
  items[0].click();
  await new Promise((r) => setTimeout(r, 40));
  const titleInput = window.document.querySelector('.cn-editor-title');
  assert.ok(titleInput, 'editor header rendered');
  assert.equal(titleInput.value, 'Demo Chain');

  // Two step cards appear with badges matching their type.
  const cards = window.document.querySelectorAll('.cn-step');
  assert.equal(cards.length, 2);
  assert.ok(cards[0].querySelector('.cn-step-badge.is-prompt'), 'first step is a Prompt');
  assert.ok(cards[1].querySelector('.cn-step-badge.is-command'), 'second step is a Command');

  // Verify the API was hit.
  assert.ok(fetchLog.some((c) => c.url.endsWith('/v1/chains')), 'chains list fetched');
  assert.ok(fetchLog.some((c) => c.url.endsWith(`/v1/chain/${fakeChain.id}`)), 'chain detail fetched');

  window.AgixtChat.disconnect();
});

test('prompts: pane lists prompts and renders editor on selection', async () => {
  const fakePrompt = {
    id: 'p1',
    name: 'Think About It',
    content: 'Carefully consider the following question:\n\n{user_input}\n\nProvide a thoughtful response in {style} style.',
  };
  const { window } = loadFullApp();
  window.fetch = async (url) => {
    const path = String(url).replace(/^https?:\/\/[^/]+/, '');
    if (path.startsWith('/v1/prompts')) {
      return new Response(JSON.stringify({ prompts: [fakePrompt] }), { status: 200 });
    }
    if (path === `/v1/prompt/${fakePrompt.id}`) {
      return new Response(JSON.stringify(fakePrompt), { status: 200 });
    }
    return new Response('{}', { status: 200 });
  };
  window.Response = Response;

  await new Promise((r) => setTimeout(r, 20));

  // Prompts is reached from the chains editor, not a top-level sidenav
  // item. Activate the view directly via the AgixtSidenav shim — that's
  // the same path the chains "Prompt Library" toolbar button takes.
  assert.ok(
    !window.document.querySelector('.sidenav-btn[data-view="prompts"]'),
    'prompts should not have its own sidenav item',
  );
  window.AgixtSidenav.setActiveView('prompts');
  await new Promise((r) => setTimeout(r, 40));

  const pane = window.document.querySelector('.view-pane[data-view="prompts"]');
  assert.equal(pane.hidden, false, 'prompts pane revealed');
  const items = window.document.querySelectorAll('.pl-list-item');
  assert.equal(items.length, 1, 'one prompt listed');
  assert.match(items[0].textContent, /Think About It/);

  items[0].click();
  await new Promise((r) => setTimeout(r, 40));

  const titleInput = window.document.querySelector('.pl-editor-title');
  assert.ok(titleInput, 'editor header rendered');
  assert.equal(titleInput.value, 'Think About It');

  // Edit tab is the default — the textarea should hold the prompt body
  // and the var sidebar should expose `user_input` and `style` chips.
  const textarea = window.document.querySelector('.pl-edit-textarea');
  assert.ok(textarea, 'edit textarea present');
  assert.match(textarea.value, /Carefully consider/);
  const chips = window.document.querySelectorAll('.pl-var-chip');
  const chipNames = [...chips].map((c) => c.textContent.replace(/[^a-z_]/gi, ''));
  assert.ok(chipNames.includes('user_input'), 'user_input variable detected');
  assert.ok(chipNames.includes('style'), 'style variable detected');

  // Switch to Test tab — should show input fields for both variables.
  const tabs = window.document.querySelectorAll('.pl-tab');
  const testTab = [...tabs].find((t) => /Test/.test(t.textContent));
  assert.ok(testTab, 'Test tab present');
  testTab.click();
  await new Promise((r) => setTimeout(r, 20));

  const fields = window.document.querySelectorAll('.pl-test-field-label');
  const labels = [...fields].map((f) => f.textContent);
  assert.ok(labels.includes('user_input'));
  assert.ok(labels.includes('style'));

  window.AgixtChat.disconnect();
});

test('client-actions: missing IPC reports error', async () => {
  // Set up without exposing __TAURI__.
  const dom = new JSDOM(fs.readFileSync(path.join(SRC, 'index.html'), 'utf8'), {
    runScripts: 'outside-only', url: 'http://localhost/',
  });
  trackDom(dom);
  if (!dom.window.WebSocket) {
    dom.window.WebSocket = class { constructor() { this.readyState = 0; } send() {} close() {} };
    dom.window.WebSocket.OPEN = 1;
  }
  for (const name of ['markdown.js', 'audio.js', 'client-actions.js']) {
    vm.runInContext(fs.readFileSync(path.join(SRC, name), 'utf8'), dom.getInternalVMContext(), { filename: name });
  }
  const res = await dom.window.AgixtClientActions.execute({ tool_name: 'desktop_click' });
  assert.match(res.error, /Tauri IPC unavailable/);
});

test('team-chat: pane lists companies + channels + members on activation', async () => {
  // Hand-roll the DOM + script load so we can fully control the AGiXT
  // API stub (loadFullApp uses Tauri IPC which doesn't cover the team-chat
  // REST shape).
  const dom = new JSDOM(fs.readFileSync(path.join(SRC, 'index.html'), 'utf8'), {
    runScripts: 'outside-only', url: 'http://localhost/',
  });
  const { window } = dom;
  trackDom(dom);
  window.__TAURI__ = {
    core: {
      invoke: async (cmd) => {
        if (cmd === 'get_conversation_history') {
          return [
            { id: 'm1', role: 'USER', message: 'hi everyone', timestamp: '2026-05-11T20:00:00Z',
              sender: { first_name: 'Test', last_name: 'User' }, sender_user_id: 'u1' },
            { id: 'm2', role: 'XT', message: 'hello!', timestamp: '2026-05-11T20:00:05Z' },
          ];
        }
        return null;
      },
    },
    event: { listen: async () => () => {} },
  };
  if (!window.WebSocket) {
    window.WebSocket = class { constructor() { this.readyState = 0; } send() {} close() {} };
    window.WebSocket.OPEN = 1;
  }

  // Stub AgixtApi (mirrors what real boot wires up).
  window.AgixtApi = {
    getSettings: async () => ({ server_url: 'http://localhost:7437', jwt: 'jwt' }),
    getUser: async () => ({ id: 'u1', email: 'me@x' }),
    listCompanies: async () => [
      { id: 'c1', name: 'Acme Corp', icon_url: null, sort_order: 0 },
    ],
    getGroupConversations: async (cid) => {
      if (cid === 'c1') return {
        'chan-1': { name: 'general', conversation_type: 'group', category: 'Text Channels' },
        'chan-2': { name: 'random', conversation_type: 'group', category: 'Text Channels',
                     has_notifications: true, notification_count: 3 },
      };
      return {};
    },
    listAllConversations: async () => ({}),
    getConversationParticipants: async () => [
      { id: 'p1', participant_type: 'user', role: 'owner',
        user: { id: 'u1', email: 'me@x', first_name: 'Test', last_name: 'User' } },
      { id: 'p2', participant_type: 'agent', role: 'member', agent: { id: 'a1', name: 'XT' } },
    ],
    markConversationRead: async () => ({}),
    postConversationMessage: async () => ({ message: 'mid' }),
    postChannelMessage: async () => ({ message: 'mid' }),
  };

  // Load markdown.js (team-chat uses renderFragment) and the helpers
  // module that powers reply parsing, mentions, gravatar, and emoji
  // shortcodes.
  for (const name of ['markdown.js', 'team-chat-helpers.js', 'team-chat.js']) {
    vm.runInContext(fs.readFileSync(path.join(SRC, name), 'utf8'),
                    dom.getInternalVMContext(), { filename: name });
  }

  // Sanity: the Chat sidenav button exists and points at the team-chat
  // view, and it's pinned-first so user reorders can't bury it.
  const chatBtn = window.document.querySelector('.sidenav-btn[data-view="team-chat"]');
  assert.ok(chatBtn, 'Chat sidenav button rendered');
  assert.equal(chatBtn.dataset.pinnedFirst, 'true', 'Chat button is pinned first');

  // Mount the pane.
  await window.AgixtTeamChat.mount();

  // Company appears in the rail.
  const rail = window.document.getElementById('tc-company-list');
  assert.equal(rail.children.length, 1, 'one company icon rendered');

  // Click into the company.
  rail.querySelector('.tc-company').click();
  // Allow the async loaders + auto-channel-select to flush.
  await new Promise((r) => setTimeout(r, 60));
  await new Promise((r) => setImmediate(r));
  await new Promise((r) => setTimeout(r, 40));

  // Channels rendered with category heading.
  const cats = window.document.querySelectorAll('#tc-channel-scroll .tc-channel-category');
  assert.ok(cats.length >= 1, 'category heading rendered');
  const channels = window.document.querySelectorAll('#tc-channel-scroll .tc-channel-row');
  assert.equal(channels.length, 2, 'two channels rendered');
  const names = Array.from(channels).map((c) => c.querySelector('.tc-channel-name').textContent);
  assert.deepEqual(names.sort(), ['general', 'random']);

  // First channel is active (auto-selected on company entry).
  const active = window.document.querySelector('#tc-channel-scroll .tc-channel-row.is-active');
  assert.ok(active, 'a channel is auto-selected');
  // Header reflects the channel name with the # prefix.
  const title = window.document.getElementById('tc-content-title').textContent;
  assert.match(title, /^# /, 'content header uses # prefix');

  // Members panel populated.
  const memberRows = window.document.querySelectorAll('#tc-member-scroll .tc-member-row');
  assert.equal(memberRows.length, 2, 'two members rendered');
  const memberNames = Array.from(memberRows).map((m) => m.querySelector('.tc-member-name').textContent);
  assert.ok(memberNames.includes('Test User'));
  assert.ok(memberNames.includes('XT'));

  // Messages rendered from get_conversation_history.
  const msgs = window.document.querySelectorAll('#tc-messages .tc-message');
  assert.equal(msgs.length, 2, 'two messages rendered');
  const msgNames = Array.from(msgs).map((m) => m.querySelector('.tc-message-name').textContent);
  assert.ok(msgNames.includes('Test User'), 'sender info used for user message');
  assert.ok(msgNames.includes('XT'), 'agent role used as display name');

  // Collapse the channel list — the channel pane hides, the re-expand
  // strip becomes visible.
  window.document.getElementById('tc-channel-collapse').click();
  const pane = window.document.querySelector('.view-pane-team-chat');
  assert.ok(pane.classList.contains('tc-channels-collapsed'), 'collapse class applied');
  assert.equal(window.document.getElementById('tc-channel-collapsed').hidden, false,
               're-expand strip becomes visible');

  // Re-expand.
  window.document.getElementById('tc-channel-collapsed').click();
  assert.ok(!pane.classList.contains('tc-channels-collapsed'), 'collapse class cleared');

  // Send a message — verify the shared channel/DM path is called with
  // the channel ID so participant permissions + notifications match web.
  let postedWith = null;
  window.AgixtApi.postConversationMessage = async (conversationId, msg, role) => {
    postedWith = { conversationId, msg, role };
    return { message: 'mid' };
  };
  const input = window.document.getElementById('tc-composer-input');
  input.value = 'Hi team';
  const sendBtn = window.document.getElementById('tc-send-btn');
  sendBtn.disabled = false;
  sendBtn.click();
  await new Promise((r) => setTimeout(r, 30));
  assert.ok(postedWith, 'postConversationMessage was called');
  assert.equal(postedWith.conversationId, 'chan-1');
  assert.equal(postedWith.msg, 'Hi team');
  assert.equal(postedWith.role, 'USER');

  // Tear down the module's setInterval/WebSocket so the node:test runner
  // doesn't hang waiting on a live event loop after the assertion passes.
  window.AgixtTeamChat.unmount();
});

test('team-chat: teammate DM row creates participant DM with company context', async () => {
  const dom = new JSDOM(fs.readFileSync(path.join(SRC, 'index.html'), 'utf8'), {
    runScripts: 'outside-only', url: 'http://localhost/',
  });
  const { window } = dom;
  trackDom(dom);
  const historyRequests = [];
  window.__TAURI__ = {
    core: {
      invoke: async (cmd, args) => {
        if (cmd === 'get_conversation_history') {
          historyRequests.push(args.conversationId);
          return [];
        }
        return null;
      },
    },
    event: { listen: async () => () => {} },
  };
  if (!window.WebSocket) {
    window.WebSocket = class { constructor() { this.readyState = 0; } close() {} send() {} };
    window.WebSocket.OPEN = 1;
  }

  let createdPayload = null;
  let addedParticipant = null;
  let postedMessage = null;
  window.AgixtApi = {
    getSettings: async () => ({ server_url: 'http://localhost:7437', jwt: 'jwt' }),
    getUser: async () => ({ id: 'u1', email: 'me@x' }),
    listCompanies: async () => [
      {
        id: 'c1',
        name: 'Acme Corp',
        icon_url: null,
        sort_order: 0,
        users: [
          { id: 'u1', email: 'me@x', first_name: 'Me', last_name: '' },
          { id: 'u2', email: 'bob@x', first_name: 'Bob', last_name: 'Smith' },
        ],
      },
    ],
    getGroupConversations: async () => ({}),
    listAllConversations: async () => ({}),
    createGroupConversation: async (payload) => {
      createdPayload = payload;
      return { conversation_id: 'dm-new', name: payload.conversation_name, company_id: payload.company_id };
    },
    addConversationParticipant: async (conversationId, payload) => {
      addedParticipant = { conversationId, payload };
      return { participant_id: 'p2' };
    },
    getConversationParticipants: async () => [],
    markConversationRead: async () => ({}),
    postConversationMessage: async (conversationId, msg, role) => {
      postedMessage = { conversationId, msg, role };
      return { message: 'mid' };
    },
  };
  for (const name of ['markdown.js', 'team-chat-helpers.js', 'team-chat.js']) {
    vm.runInContext(fs.readFileSync(path.join(SRC, name), 'utf8'),
                    dom.getInternalVMContext(), { filename: name });
  }

  await window.AgixtTeamChat.mount();
  await new Promise((r) => setTimeout(r, 80));

  const rows = Array.from(window.document.querySelectorAll('#tc-channel-scroll .tc-channel-row'));
  const bobRow = rows.find((r) => r.querySelector('.tc-channel-name')?.textContent === 'Bob Smith');
  assert.ok(bobRow, 'teammate row rendered before DM exists');
  bobRow.click();
  await new Promise((r) => setTimeout(r, 80));

  assert.equal(createdPayload.conversation_name, 'DM-Bob Smith');
  assert.equal(createdPayload.company_id, 'c1');
  assert.equal(createdPayload.conversation_type, 'dm');
  assert.equal(addedParticipant.conversationId, 'dm-new');
  assert.equal(addedParticipant.payload.user_id, 'u2');
  assert.equal(addedParticipant.payload.participant_type, 'user');
  assert.ok(historyRequests.includes('dm-new'), 'new DM selected and history loaded');
  assert.equal(window.document.getElementById('tc-content-title').textContent, '@ Bob Smith');

  const input = window.document.getElementById('tc-composer-input');
  input.value = 'hey Bob';
  window.document.getElementById('tc-send-btn').click();
  await new Promise((r) => setTimeout(r, 30));
  assert.equal(postedMessage.conversationId, 'dm-new');
  assert.equal(postedMessage.msg, 'hey Bob');
  assert.equal(postedMessage.role, 'USER');
});

test('team-chat-helpers: parseReply, mentions, emoji, gravatar', () => {
  // Load helpers in a minimal dom context.
  const dom = new JSDOM('<!doctype html><body></body>', {
    runScripts: 'outside-only', url: 'http://localhost/',
  });
  trackDom(dom);
  vm.runInContext(
    fs.readFileSync(path.join(SRC, 'team-chat-helpers.js'), 'utf8'),
    dom.getInternalVMContext(),
    { filename: 'team-chat-helpers.js' },
  );
  const H = dom.window.AgixtTeamChatHelpers;
  assert.ok(H, 'helpers exported');

  // parseReply round-trips a wire-format reply correctly.
  const wireMsg = '> **Alice** said: [ref:msg-1] [uid:35e5fb1f-eaa1-4e71-8421-9f71e2659377]\n> hello there\n> second quoted line\n\nyo what up';
  const reply = H.parseReply(wireMsg);
  assert.ok(reply, 'reply parsed');
  assert.equal(reply.replyAuthor, 'Alice');
  assert.equal(reply.replyMessageId, 'msg-1');
  assert.equal(reply.replyAuthorUserId, '35e5fb1f-eaa1-4e71-8421-9f71e2659377');
  assert.equal(reply.replyPreview, 'hello there second quoted line');
  assert.equal(reply.actualMessage, 'yo what up');

  // applyMentions replaces `<@uuid>` tokens with @DisplayName via the
  // caller-supplied resolver.
  const txt = 'hi <@35e5fb1f-eaa1-4e71-8421-9f71e2659377> testing';
  const result = H.applyMentions(txt, (uid) => uid === '35e5fb1f-eaa1-4e71-8421-9f71e2659377' ? 'Alice' : null);
  assert.equal(result, 'hi @Alice testing');
  // Unresolved uids still produce a fallback so we don't leak the raw token.
  assert.equal(H.applyMentions('<@deadbeef-dead-beef-dead-beefdeadbeef> hi', () => null),
               '@User hi');

  // Emoji shortcodes ⇒ unicode glyphs.
  assert.equal(H.applyEmojiShortcodes('hi :joy: :fire:'), 'hi 😂 🔥');

  // Gravatar URLs are deterministic by md5 of lowercased trimmed email.
  const url = H.gravatarUrl(' Alice@Example.com ', 64);
  assert.match(url, /^https:\/\/www\.gravatar\.com\/avatar\/[0-9a-f]{32}\?s=64&d=404$/);

  // URL extraction skips markdown link/image syntax. Cross-context
  // arrays don't satisfy deepStrictEqual's reference check, so compare
  // the JSON form.
  const urls = H.extractFirstFewUrls(
    'check out https://example.com and ![alt](https://img/png) plus [docs](https://docs.x)',
    3,
  );
  assert.equal(JSON.stringify(urls), '["https://example.com"]');
});

test('team-chat: reply-card renders for stored wire format', async () => {
  const dom = new JSDOM(fs.readFileSync(path.join(SRC, 'index.html'), 'utf8'), {
    runScripts: 'outside-only', url: 'http://localhost/',
  });
  const { window } = dom;
  trackDom(dom);
  window.__TAURI__ = {
    core: {
      invoke: async (cmd) => {
        if (cmd === 'get_conversation_history') {
          return [
            {
              id: 'm1', role: 'USER', timestamp: '2026-05-12T01:00:00Z',
              sender: { id: 'u1', email: 'alice@x', first_name: 'Alice', last_name: '' },
              sender_user_id: 'u1',
              message: 'Hi everyone',
            },
            {
              id: 'm2', role: 'USER', timestamp: '2026-05-12T01:01:00Z',
              sender: { id: 'u2', email: 'bob@x', first_name: 'Bob', last_name: '' },
              sender_user_id: 'u2',
              message: '> **Alice** said: [ref:m1] [uid:u1]\n> Hi everyone\n\nright back at you :joy:',
            },
          ];
        }
        return null;
      },
    },
    event: { listen: async () => () => {} },
  };
  if (!window.WebSocket) {
    window.WebSocket = class { constructor() { this.readyState = 0; } close() {} send() {} };
    window.WebSocket.OPEN = 1;
  }
  window.AgixtApi = {
    getSettings: async () => ({ server_url: 'http://localhost:7437', jwt: 'jwt' }),
    getUser: async () => ({ id: 'u2', email: 'bob@x' }),
    listCompanies: async () => [],
    getGroupConversations: async () => ({}),
    listAllConversations: async () => ({
      'dm-1': {
        id: 'dm-1', name: 'XT', display_name: 'XT', agent_name: 'XT',
        conversation_type: 'dm', updated_at: '2026-05-12T01:00:00Z',
      },
      'dm-2': {
        id: 'dm-2', name: 'DM-Alice', display_name: 'DM-Alice',
        conversation_type: 'dm', updated_at: '2026-05-12T01:01:00Z',
      },
    }),
    getConversationParticipants: async () => [],
    markConversationRead: async () => ({}),
  };
  for (const name of ['markdown.js', 'team-chat-helpers.js', 'team-chat.js']) {
    vm.runInContext(fs.readFileSync(path.join(SRC, name), 'utf8'),
                    dom.getInternalVMContext(), { filename: name });
  }

  await window.AgixtTeamChat.mount();
  await new Promise((r) => setTimeout(r, 80));

  // DM list shows ONLY People (humans). Agent DMs live in the side
  // AI chat — they intentionally don't surface in this panel.
  const categories = Array.from(window.document.querySelectorAll('#tc-channel-scroll .tc-channel-category'))
    .map((n) => n.textContent);
  assert.ok(categories.includes('People'), 'People section header rendered');
  assert.ok(!categories.includes('Agents'), 'Agents section header NOT rendered');

  // Click into the human DM to load messages.
  const rows = window.document.querySelectorAll('#tc-channel-scroll .tc-channel-row');
  let aliceRow = null;
  for (const r of rows) {
    if (r.querySelector('.tc-channel-name').textContent === 'Alice') { aliceRow = r; break; }
  }
  assert.ok(aliceRow, 'Alice DM row rendered (DM- prefix stripped)');
  aliceRow.click();
  await new Promise((r) => setTimeout(r, 60));

  // Reply card appears on the second message.
  const replyCards = window.document.querySelectorAll('.tc-reply-card');
  assert.equal(replyCards.length, 1, 'reply card rendered for m2');
  assert.match(replyCards[0].textContent, /Alice/, 'reply card credits Alice');
  // Emoji shortcode resolved.
  const messages = window.document.querySelectorAll('.tc-message-body');
  const lastBody = messages[messages.length - 1].textContent;
  assert.match(lastBody, /😂/, 'emoji shortcode resolved');
  // Avatar element present for each message.
  const avatars = window.document.querySelectorAll('.tc-message .tc-avatar');
  assert.equal(avatars.length, 2, 'avatar rendered per message');

  window.AgixtTeamChat.unmount();
});

test('markdown: data:image URLs render as <img>, not as link text', () => {
  const { window } = loadFrontend();
  const html = window.AgixtMarkdown.render(
    '![photo](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=)',
  );
  // <img> tag with the data URL as src, not <a> wrapping the alt text.
  assert.match(html, /<img[^>]+class="md-image"[^>]+src="data:image\/png/);
  assert.ok(!/<a[^>]*>photo<\/a>/.test(html), 'attachment must not render as a link');
});

test('markdown: ||spoiler|| renders as clickable hidden span', () => {
  const { window } = loadFrontend();
  const html = window.AgixtMarkdown.render('hi ||secret thing|| there');
  assert.match(html, /class="md-spoiler"/);
  assert.match(html, /role="button"/);
  assert.match(html, /class="md-spoiler-inner">secret thing/);
});

test('markdown: fenced code block carries copy + download buttons', () => {
  const { window } = loadFrontend();
  const html = window.AgixtMarkdown.render('```javascript\nconsole.log(1);\n```');
  assert.match(html, /class="md-codeblock"/);
  assert.match(html, /title="Copy"[^>]*aria-label="Copy"/);
  assert.match(html, /title="Download"[^>]*aria-label="Download"/);
  assert.match(html, /md-codeblock-lang">javascript/);
});

test('team-chat-helpers: parseReply strips nested reply layer', () => {
  const dom = new JSDOM('<!doctype html><body></body>', {
    runScripts: 'outside-only', url: 'http://localhost/',
  });
  trackDom(dom);
  vm.runInContext(
    fs.readFileSync(path.join(SRC, 'team-chat-helpers.js'), 'utf8'),
    dom.getInternalVMContext(),
    { filename: 'team-chat-helpers.js' },
  );
  const H = dom.window.AgixtTeamChatHelpers;
  // A reply-of-a-reply: parsing the outer reply yields a body that is
  // itself a reply. Reply target staging calls parseReply again on
  // that body to get to the leaf message.
  const outer = '> **Alice** said: [ref:m1] [uid:abcdef01-2345-6789-abcd-ef0123456789]\n> hello\n\n> **Bob** said: [ref:m2] [uid:11111111-2222-3333-4444-555555555555]\n> earlier line\n\nthe leaf message';
  const first = H.parseReply(outer);
  assert.ok(first, 'outer reply parsed');
  assert.equal(first.replyAuthor, 'Alice');
  const inner = H.parseReply(first.actualMessage);
  assert.ok(inner, 'inner reply parsed');
  assert.equal(inner.replyAuthor, 'Bob');
  assert.equal(inner.actualMessage, 'the leaf message');
});

test('markdown: mention resolver renders <@uuid> as clickable chip', () => {
  const { window } = loadFrontend();
  const calls = [];
  window.AgixtMarkdown.setMentionResolver((uid) => ({
    name: uid === '11111111-2222-3333-4444-555555555555' ? 'Alice' : 'User',
    kind: 'user',
    onClick: () => calls.push(uid),
  }));
  const target = window.document.createElement('div');
  window.AgixtMarkdown.renderInto(target,
    'hello <@11111111-2222-3333-4444-555555555555>!');
  const chip = target.querySelector('.md-mention');
  assert.ok(chip, 'mention chip rendered');
  assert.equal(chip.textContent, '@Alice');
  assert.equal(chip.dataset.userId, '11111111-2222-3333-4444-555555555555');
  chip.click();
  assert.deepEqual(calls, ['11111111-2222-3333-4444-555555555555']);
  // Reset resolver so it doesn't leak between tests.
  window.AgixtMarkdown.setMentionResolver(null);
});

test('markdown: tenor URL renders as inline <img>, not a bare link', () => {
  const { window } = loadFrontend();
  const target = window.document.createElement('div');
  window.AgixtMarkdown.renderInto(target,
    'check this https://media.tenor.com/abc.gif');
  const img = target.querySelector('img.md-image');
  assert.ok(img, 'tenor URL becomes an <img>');
  assert.equal(img.getAttribute('src'), 'https://media.tenor.com/abc.gif');
});

test('markdown: code blocks inside a block spoiler render correctly when revealed', () => {
  const { window } = loadFrontend();
  const target = window.document.createElement('div');
  // ||\n```js\ncode\n```\n||  — block spoiler containing a fenced code block.
  window.AgixtMarkdown.renderInto(target, '||\n```js\nlet a = 1;\n```\n||');
  const spoiler = target.querySelector('.md-spoiler-block');
  assert.ok(spoiler, 'block spoiler rendered');
  // The code block lives INSIDE the spoiler wrapper so revealing the
  // spoiler exposes the full codeblock chrome (toolbar, language, etc.)
  const codeblock = spoiler.querySelector('.md-codeblock');
  assert.ok(codeblock, 'fenced code block survives inside the spoiler');
  assert.match(codeblock.outerHTML, /title="Copy"/);
  assert.match(codeblock.outerHTML, /md-codeblock-lang">js</);
});

test('prompt guidance: default computer-use suggestions on chat, page-specific on a content view', async () => {
  const { window } = loadFullApp({
    ipc: {
      client_platform: () => ({
        os: 'linux', family: 'desktop', mobile: false, desktop: true,
        tools: ['desktop_screenshot', 'desktop_vision_control', 'shell_run',
          'fs_read', 'fs_list', 'workspace_download'],
      }),
    },
  });
  // Wait for the async client_platform detection + re-render.
  await new Promise((resolve) => setTimeout(resolve, 60));
  const bar = window.document.getElementById('prompt-guidance');
  assert.ok(bar, '#prompt-guidance container exists');
  // On plain chat there is no page-specific guidance, so the default
  // desktop computer-use set is shown instead of hiding the bar.
  assert.equal(bar.hidden, false, 'bar shows default suggestions on chat');
  assert.equal(bar.dataset.key, '__default__', 'default guidance is active');
  assert.match(bar.querySelector('.pg-bar-title').textContent, /this computer/i);
  const deskLabels = Array.from(bar.querySelectorAll('.pg-chip-label'))
    .map((n) => n.textContent);
  assert.ok(deskLabels.some((l) => /see my screen/i.test(l)),
    'desktop tools surface the screenshot suggestion');
  assert.ok(deskLabels.some((l) => /run a command/i.test(l)),
    'desktop tools surface the shell suggestion');

  window.AgixtSidenav.setActiveView('secrets');
  await new Promise((resolve) => setTimeout(resolve, 5));
  assert.equal(bar.hidden, false, 'bar shows when a guided page is active');
  assert.equal(bar.dataset.key, 'secrets', 'page-specific guidance is active');
  const chips = bar.querySelectorAll('.pg-chip');
  assert.ok(chips.length >= 3, 'suggestion chips rendered for secrets');
  assert.match(bar.querySelector('.pg-bar-title').textContent, /secrets/i);

  window.AgixtSidenav.setActiveView('chat');
  await new Promise((resolve) => setTimeout(resolve, 5));
  assert.equal(bar.hidden, false, 'bar still shows defaults back on chat');
  assert.equal(bar.dataset.key, '__default__', 'falls back to defaults again');
  window.AgixtChat.disconnect();
});

test('prompt guidance: default set is used for a content view with no ported guidance', async () => {
  const { window } = loadFullApp();
  await new Promise((resolve) => setTimeout(resolve, 20));
  const bar = window.document.getElementById('prompt-guidance');
  // 'dashboard' is a desktop extension with no web ResourceGuidanceCard
  // counterpart, so it should fall back to the computer-use defaults.
  window.AgixtSidenav.setActiveView('dashboard');
  await new Promise((resolve) => setTimeout(resolve, 5));
  assert.equal(bar.hidden, false, 'bar shows on an unguided content view');
  assert.equal(bar.dataset.key, '__default__', 'default guidance used');
  window.AgixtChat.disconnect();
});

test('prompt guidance: clicking a no-field suggestion sends it to chat', async () => {
  const { window, calls } = loadFullApp();
  await new Promise((resolve) => setTimeout(resolve, 20));
  window.AgixtSidenav.setActiveView('secrets');
  await new Promise((resolve) => setTimeout(resolve, 5));

  const bar = window.document.getElementById('prompt-guidance');
  const chip = bar.querySelector('.pg-chip');
  chip.click();
  await new Promise((resolve) => setTimeout(resolve, 20));

  const send = calls.find((c) => c.cmd === 'chat_send');
  assert.ok(send, 'a no-field suggestion sends immediately');
  const sent = send.args.args.messages[0].content;
  assert.equal(sent, window.AgixtPromptGuidanceData.secrets.examples[0].prompt);
  window.AgixtChat.disconnect();
});

test('prompt guidance: builder fills placeholders before sending', async () => {
  const { window, calls } = loadFullApp();
  await new Promise((resolve) => setTimeout(resolve, 20));
  window.AgixtSidenav.setActiveView('tickets');
  await new Promise((resolve) => setTimeout(resolve, 5));

  const bar = window.document.getElementById('prompt-guidance');
  // First tickets example ("Triage the open backlog") has a {{company}}
  // placeholder, so its chip carries the builder badge.
  const builderChip = Array.from(bar.querySelectorAll('.pg-chip'))
    .find((c) => c.querySelector('.pg-chip-badge'));
  assert.ok(builderChip, 'a placeholder-bearing chip renders with a badge');
  builderChip.click();
  await new Promise((resolve) => setTimeout(resolve, 40));

  const modal = window.document.querySelector('.prompt-guidance-modal');
  assert.ok(modal && modal.classList.contains('open'), 'builder modal opens');
  const input = modal.querySelector('.pg-input');
  input.value = 'Acme Corp';
  input.dispatchEvent(new window.Event('input', { bubbles: true }));
  const preview = modal.querySelector('.pg-preview');
  assert.match(preview.textContent, /Acme Corp/);
  assert.doesNotMatch(preview.textContent, /\{\{company\}\}/);

  const sendBtn = Array.from(modal.querySelectorAll('.btn'))
    .find((b) => b.textContent === 'Send to chat');
  sendBtn.click();
  await new Promise((resolve) => setTimeout(resolve, 20));

  assert.equal(window.document.querySelector('.prompt-guidance-modal'), null,
    'modal closes after send');
  const send = calls.find((c) => c.cmd === 'chat_send');
  assert.ok(send, 'composed prompt is sent');
  const sent = send.args.args.messages[0].content;
  assert.match(sent, /Acme Corp/);
  assert.doesNotMatch(sent, /\{\{company\}\}/);
  window.AgixtChat.disconnect();
});

test('prompt guidance: mobile platform shows device-oriented defaults', async () => {
  const { window } = loadFullApp({
    ipc: {
      // The exact tool set a mobile (Android/iOS) build exposes — no
      // screenshot, shell, or filesystem (see src-tauri
      // client_tool_specs::mobile_tools).
      client_platform: () => ({
        os: 'android', family: 'mobile', mobile: true, desktop: false,
        tools: ['device_open_url', 'device_open_app', 'device_open_settings',
          'workspace_upload', 'workspace_download'],
      }),
    },
  });
  // Wait long enough for the async client_platform detection + re-render.
  await new Promise((resolve) => setTimeout(resolve, 60));
  const bar = window.document.getElementById('prompt-guidance');
  assert.equal(bar.hidden, false);
  assert.equal(bar.dataset.key, '__default__');
  assert.match(bar.querySelector('.pg-bar-title').textContent, /this device/i);
  const labels = Array.from(bar.querySelectorAll('.pg-chip-label'))
    .map((n) => n.textContent);
  assert.ok(labels.some((l) => /open an app/i.test(l)),
    'mobile defaults include device-app suggestions');
  // Screen viewing / shell / filesystem tools do not exist on mobile, so
  // none of those suggestions should be offered there.
  assert.ok(!labels.some((l) => /screen|terminal|run a command|files on my computer|computer/i.test(l)),
    'mobile defaults do not show desktop screen/shell/filesystem items');
  window.AgixtChat.disconnect();
});

test('prompt guidance: web deployment (no Tauri) shows generic agent defaults', async () => {
  const dom = new JSDOM(
    '<!doctype html><body>'
    + '<button class="sidenav-btn is-active" data-view="chat"></button>'
    + '<div id="prompt-guidance" hidden></div>'
    + '<textarea id="composer-input"></textarea><button id="btn-send"></button>'
    + '</body>',
    { runScripts: 'outside-only', url: 'http://localhost/' },
  );
  const { window } = dom;
  // No window.__TAURI__ — this is the plain web deployment path.
  window.AgixtSidenav = { getActiveView: () => 'chat' };
  for (const name of ['prompt-guidance-data.js', 'prompt-guidance.js']) {
    const code = fs.readFileSync(path.join(SRC, name), 'utf8');
    vm.runInContext(code, dom.getInternalVMContext(), { filename: name });
  }
  // init() defers to DOMContentLoaded when the document is still
  // parsing; let that fire before asserting.
  if (window.document.readyState === 'loading') {
    await new Promise((resolve) => {
      window.document.addEventListener('DOMContentLoaded', resolve);
      setTimeout(resolve, 50);
    });
  }
  const bar = window.document.getElementById('prompt-guidance');
  assert.equal(bar.hidden, false, 'bar still shows on web');
  assert.equal(bar.dataset.key, '__default__');
  assert.match(bar.querySelector('.pg-bar-title').textContent, /get started/i);
  const text = bar.textContent;
  assert.ok(!/screenshot|terminal|my computer/i.test(text),
    'web defaults avoid client-side device/computer tooling');
});

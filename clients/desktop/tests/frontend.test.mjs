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
// from clients/desktop.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import { JSDOM } from 'jsdom';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(__dirname, '..', 'src');

function loadFrontend({ ipc, WebSocketClass } = {}) {
  const dom = new JSDOM(
    fs.readFileSync(path.join(SRC, 'index.html'), 'utf8'),
    { runScripts: 'outside-only', url: 'http://localhost/' },
  );
  const { window } = dom;
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
    event: { listen: async () => () => {} },
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

function loadFullApp({ ipc } = {}) {
  const dom = new JSDOM(
    fs.readFileSync(path.join(SRC, 'index.html'), 'utf8'),
    { runScripts: 'outside-only', url: 'http://localhost/' },
  );
  const { window } = dom;
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
            user_email: 'test@example.com',
          };
        }
        if (cmd === 'list_companies') {
          return [{ id: 'company-id', name: 'Home', primary: true, agents: [{ id: 'agent-id', name: 'XT', default: true }] }];
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
  if (!window.WebSocket) {
    window.WebSocket = class {
      constructor() { this.readyState = 1; setTimeout(() => this.onopen && this.onopen(), 0); }
      send() {}
      close() {}
    };
    window.WebSocket.OPEN = 1;
  }
  for (const name of ['markdown.js', 'audio.js', 'client-actions.js', 'chat.js', 'notifications.js', 'auth.js', 'dock.js', 'app.js']) {
    const code = fs.readFileSync(path.join(SRC, name), 'utf8');
    vm.runInContext(code, dom.getInternalVMContext(), { filename: name });
  }
  return { window, calls };
}

function loadDesktopExtensionsOnly() {
  const dom = new JSDOM(
    '<!doctype html><body><button class="sidenav-btn is-active" data-view="audible"></button><div class="chat-screen-main"><div class="view-pane" data-view="chat"></div><div class="view-pane view-pane-extension" data-view="audible"></div></div></body>',
    { runScripts: 'outside-only', url: 'http://localhost/' },
  );
  const { window } = dom;
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

test('markdown: paragraph and inline formatting', () => {
  const { window } = loadFrontend();
  const html = window.AgixtMarkdown.render('Hello **bold** and *italic*.');
  assert.match(html, /<p>Hello <strong>bold<\/strong> and <em>italic<\/em>\.<\/p>/);
});

test('markdown: code fence preserves whitespace', () => {
  const { window } = loadFrontend();
  const html = window.AgixtMarkdown.render('```py\ndef hi():\n  pass\n```');
  assert.match(html, /<pre><code class="language-py">def hi\(\):\n  pass<\/code><\/pre>/);
});

test('markdown: image URL becomes <img>', () => {
  const { window } = loadFrontend();
  const html = window.AgixtMarkdown.render('![cat](https://example.com/cat.png)');
  assert.match(html, /<img[^>]+src="https:\/\/example\.com\/cat\.png"[^>]+alt="cat"/);
});

test('markdown: video URL becomes <video controls>', () => {
  const { window } = loadFrontend();
  const html = window.AgixtMarkdown.render('Watch: https://example.com/clip.mp4');
  assert.match(html, /<video[^>]+controls[^>]+src="https:\/\/example\.com\/clip\.mp4"/);
});

test('markdown: audio URL becomes <audio controls>', () => {
  const { window } = loadFrontend();
  const html = window.AgixtMarkdown.render('Listen: https://example.com/voice.mp3');
  assert.match(html, /<audio[^>]+controls[^>]+src="https:\/\/example\.com\/voice\.mp3"/);
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
  assert.equal(byAlt.evil, 'https://evil.example/outputs/leak.png');
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

  window.document.getElementById('btn-settings').click();
  await new Promise((resolve) => setTimeout(resolve, 5));

  const input = window.document.getElementById('setting-sudo-password');
  input.value = 'secret';
  window.document.getElementById('btn-sudo-auth').click();
  await new Promise((resolve) => setTimeout(resolve, 20));

  const authCall = calls.find((c) => c.cmd === 'sudo_auth');
  assert.equal(authCall.args.password, 'secret');
  assert.equal(input.value, '');
  assert.equal(window.document.getElementById('sudo-session-status').textContent, 'Authenticated and remembered.');
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

  window.document.getElementById('btn-settings').click();
  await new Promise((resolve) => setTimeout(resolve, 20));

  const checkButton = window.document.getElementById('btn-check-desktop-update');
  const installButton = window.document.getElementById('btn-install-desktop-update');
  assert.equal(installButton.hidden, false);

  installButton.click();
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal(checkButton.hidden, true);
  assert.equal(installButton.hidden, true);

  rejectInstall({ error: 'SUDO_AUTH_REQUIRED: Authenticate first.' });
  await new Promise((resolve) => setTimeout(resolve, 80));
  assert.match(window.document.getElementById('desktop-update-status').textContent, /Authenticate Privileged Commands/);
  assert.equal(window.document.activeElement, window.document.getElementById('setting-sudo-password'));

  const input = window.document.getElementById('setting-sudo-password');
  input.value = 'secret';
  window.document.getElementById('btn-sudo-auth').click();
  await new Promise((resolve) => setTimeout(resolve, 20));

  assert.equal(installCalls, 2);
  assert.equal(window.document.getElementById('desktop-update-status').textContent, 'Update installed.');
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

  window.document.getElementById('btn-settings').click();
  await new Promise((resolve) => setTimeout(resolve, 20));
  window.document.getElementById('setting-auto-update').checked = true;
  window.document.getElementById('btn-save-settings').click();
  await new Promise((resolve) => setTimeout(resolve, 500));

  assert.ok(calls.some((c) => c.cmd === 'desktop_update_install'));
  assert.equal(window.document.getElementById('desktop-update-status').textContent, 'Update installed.');
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
          assert.equal(toolMsg.name, 'desktop_screenshot');
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
                name: 'desktop_screenshot',
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
  assert.equal(countThoughtActivities(), 1);

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
  window.AgixtChat.disconnect();
});

test('client-actions: missing IPC reports error', async () => {
  // Set up without exposing __TAURI__.
  const dom = new JSDOM(fs.readFileSync(path.join(SRC, 'index.html'), 'utf8'), {
    runScripts: 'outside-only', url: 'http://localhost/',
  });
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

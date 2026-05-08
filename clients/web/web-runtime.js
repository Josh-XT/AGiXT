/* Browser runtime for serving the AGiXT Tauri frontend as a web SPA.
 *
 * The desktop frontend is intentionally reused as-is. This file supplies the
 * small Tauri IPC/event surface it expects, backed by localStorage and AGiXT's
 * HTTP/SSE/WebSocket APIs.
 */
(function () {
  'use strict';

  if (window.__TAURI__) return;

  const SETTINGS_KEY = 'agixt.web.settings.v1';
  const OAUTH_FLOW_KEY = 'agixt.web.oauthFlow.v1';
  const CONNECT_FLOW_KEY = 'agixt.web.oauthConnectFlow.v1';
  const CONNECT_PROVIDER_KEY = 'agixt.web.oauthConnectProvider.v1';
  const streamControllers = new Map();
  const eventListeners = new Map();

  const config = window.AGIXT_WEB_CONFIG || {};
  const origin = window.location.origin;

  function trimSlash(value) {
    return String(value || '').replace(/\/+$/, '');
  }

  function currentServerUrl() {
    return trimSlash(config.serverUrl || origin);
  }

  function currentWebUrl() {
    return trimSlash(config.webUrl || origin);
  }

  function storageGet(key) {
    try { return window.localStorage.getItem(key); } catch (_) { return null; }
  }

  function storageSet(key, value) {
    try { window.localStorage.setItem(key, value); } catch (_) {}
  }

  function storageRemove(key) {
    try { window.localStorage.removeItem(key); } catch (_) {}
  }

  function storageGetJson(key) {
    const raw = storageGet(key);
    if (!raw) return null;
    try { return JSON.parse(raw); } catch (_) { return null; }
  }

  function storageSetJson(key, value) {
    storageSet(key, JSON.stringify(value));
  }

  function defaults() {
    return {
      server_url: currentServerUrl(),
      web_url: currentWebUrl(),
      service_brand: 'web',
      jwt: null,
      user_email: null,
      agent_id: null,
      agent_name: 'XT',
      company_id: null,
      company_name: null,
      conversation_id: null,
      conversation_name: null,
      voice_enabled: false,
      desktop_auto_update: false,
      sidebar_open: true,
      allow_client_commands: false,
      dock_pos_x: null,
      dock_pos_y: null,
    };
  }

  function loadSettings() {
    const raw = storageGet(SETTINGS_KEY);
    if (!raw) return defaults();
    try {
      const parsed = JSON.parse(raw);
      return { ...defaults(), ...parsed };
    } catch (_) {
      return defaults();
    }
  }

  function saveSettings(settings) {
    const next = { ...defaults(), ...(settings || {}) };
    next.server_url = trimSlash(next.server_url || currentServerUrl());
    next.web_url = trimSlash(next.web_url || currentWebUrl());
    storageSet(SETTINGS_KEY, JSON.stringify(next));
    return next;
  }

  function toolError(message) {
    const err = new Error(message || 'Web runtime error');
    err.error = message || err.message;
    return err;
  }

  function authHeader(settings) {
    const jwt = settings && settings.jwt;
    return jwt ? { Authorization: `Bearer ${jwt}` } : {};
  }

  async function readError(resp) {
    let text = '';
    try { text = await resp.text(); } catch (_) {}
    if (text) {
      try {
        const parsed = JSON.parse(text);
        if (parsed.detail) return detailToString(parsed.detail);
        if (parsed.error) return detailToString(parsed.error);
        if (parsed.message) return detailToString(parsed.message);
      } catch (_) {}
    }
    return text || `HTTP ${resp.status}`;
  }

  function detailToString(value) {
    if (value == null) return '';
    if (typeof value === 'string') return value;
    if (Array.isArray(value)) {
      return value.map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object' && typeof item.msg === 'string') {
          const loc = Array.isArray(item.loc) ? item.loc.join('.') : '';
          return loc ? `${loc}: ${item.msg}` : item.msg;
        }
        try { return JSON.stringify(item); } catch (_) { return String(item); }
      }).join('; ');
    }
    try { return JSON.stringify(value); } catch (_) { return String(value); }
  }

  async function jsonFetch(url, opts) {
    const resp = await fetch(url, opts || {});
    if (!resp.ok) throw toolError(await readError(resp));
    if (resp.status === 204) return null;
    const text = await resp.text();
    if (!text) return null;
    try { return JSON.parse(text); } catch (_) { return text; }
  }

  function apiUrl(settings, path) {
    return `${trimSlash((settings || loadSettings()).server_url)}/${String(path).replace(/^\/+/, '')}`;
  }

  async function apiJson(path, opts) {
    const settings = loadSettings();
    const init = opts || {};
    const headers = { ...(init.headers || {}), ...authHeader(settings) };
    return jsonFetch(apiUrl(settings, path), { ...init, headers });
  }

  function decodeJwtEmail(token) {
    try {
      const part = String(token || '').split('.')[1];
      if (!part) return null;
      const normalized = part.replace(/-/g, '+').replace(/_/g, '/');
      const json = decodeURIComponent(atob(normalized).split('').map((c) => {
        return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
      }).join(''));
      const payload = JSON.parse(json);
      return payload.email || payload.sub || null;
    } catch (_) {
      return null;
    }
  }

  function extractTokenFromDetail(detail) {
    if (typeof detail !== 'string' || !detail.trim()) return null;
    try {
      const parsed = detail.startsWith('http')
        ? new URL(detail)
        : new URL(detail, window.location.origin);
      const token = parsed.searchParams.get('token') || parsed.searchParams.get('jwt');
      if (token) return token;
    } catch (_) {
      // The backend sometimes returns a bare query string rather than a
      // complete URL. Fall through to the same regex-style extraction used
      // by the NextJS web client.
    }
    const match = detail.match(/(?:[?&]|^)(?:token|jwt)=([^&\s]+)/);
    if (!match || !match[1]) return null;
    try { return decodeURIComponent(match[1]); }
    catch (_) { return match[1]; }
  }

  function extractAuthToken(data) {
    if (!data || typeof data !== 'object') return null;
    return data.token || data.jwt || extractTokenFromDetail(data.detail);
  }

  function consumeUrlToken() {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('jwt') || params.get('token') || params.get('auth');
    if (!token) return;
    const settings = loadSettings();
    const serverUrl = params.get('server_url') || params.get('server') || settings.server_url;
    const next = saveSettings({
      ...settings,
      server_url: trimSlash(serverUrl),
      web_url: settings.web_url || currentWebUrl(),
      jwt: token,
      user_email: settings.user_email || decodeJwtEmail(token),
    });
    hydrateUser(next).catch(() => {});
    params.delete('jwt');
    params.delete('token');
    params.delete('auth');
    params.delete('server_url');
    params.delete('server');
    const qs = params.toString();
    const clean = window.location.pathname + (qs ? `?${qs}` : '') + window.location.hash;
    window.history.replaceState(null, '', clean);
  }

  async function hydrateUser(settings) {
    if (!settings || !settings.jwt) return settings;
    try {
      const user = await jsonFetch(apiUrl(settings, '/v1/user'), {
        method: 'GET',
        headers: authHeader(settings),
      });
      const email = user && (user.email || user.user_email || user.username);
      if (email && email !== settings.user_email) {
        return saveSettings({ ...settings, user_email: email });
      }
    } catch (_) {}
    return settings;
  }

  consumeUrlToken();

  function serviceBrands() {
    const webUrl = currentWebUrl();
    const serverUrl = currentServerUrl();
    return [
      { slug: 'web', label: 'AGiXT Web', default_url: serverUrl, default_web_url: webUrl },
      { slug: 'agixt', label: 'AGiXT.com', default_url: 'https://api.agixt.com', default_web_url: 'https://agixt.com' },
      { slug: 'nursext', label: 'NurseXT.com', default_url: 'https://api.nursext.com', default_web_url: 'https://nursext.com' },
      { slug: 'xtsystems', label: 'XT.Systems', default_url: 'https://api.xt.systems', default_web_url: 'https://xt.systems' },
      { slug: 'boltremote', label: 'BoltRemote.com', default_url: 'https://api.boltremote.com', default_web_url: 'https://boltremote.com' },
      { slug: 'custom', label: 'Custom', default_url: serverUrl, default_web_url: webUrl },
    ];
  }

  function serviceBrandForUrls(serverUrl, webUrl) {
    const server = trimSlash(serverUrl);
    const web = trimSlash(webUrl);
    const brands = serviceBrands();
    const serverMatch = brands.find((brand) => trimSlash(brand.default_url) === server);
    if (serverMatch) return serverMatch.slug;
    const webMatch = brands.find((brand) => {
      return brand.slug !== 'web'
        && brand.slug !== 'custom'
        && trimSlash(brand.default_web_url) === web;
    });
    return webMatch ? webMatch.slug : 'custom';
  }

  function rememberOAuthFlow(args, provider, redirectUri, connectFlow) {
    const serverUrl = trimSlash(args.server_url || currentServerUrl());
    const webUrl = trimSlash(args.web_url || currentWebUrl());
    storageSetJson(OAUTH_FLOW_KEY, {
      server_url: serverUrl,
      web_url: webUrl,
      service_brand: serviceBrandForUrls(serverUrl, webUrl),
      provider: provider.name || redirectSlugFor(provider.name),
      redirect_uri: redirectUri,
      connect: !!connectFlow,
      started_at: Date.now(),
    });
  }

  function pendingOAuthFlow() {
    const flow = storageGetJson(OAUTH_FLOW_KEY);
    if (!flow || !flow.started_at || Date.now() - Number(flow.started_at) > 600000) {
      storageRemove(OAUTH_FLOW_KEY);
      return null;
    }
    return flow;
  }

  function clearOAuthFlow() {
    storageRemove(OAUTH_FLOW_KEY);
    storageRemove(CONNECT_FLOW_KEY);
    storageRemove(CONNECT_PROVIDER_KEY);
  }

  function normalizeArrayOrKeyedObject(value, keyName) {
    if (Array.isArray(value)) return value;
    if (!value || typeof value !== 'object') return [];
    return Object.entries(value).map(([key, item]) => {
      if (item && typeof item === 'object') {
        return { [keyName || 'name']: key, ...item };
      }
      return { [keyName || 'name']: key, value: item };
    });
  }

  async function listCompanies() {
    const data = await apiJson('/v1/companies', { method: 'GET' });
    const arr = Array.isArray(data) ? data : normalizeArrayOrKeyedObject(data && data.companies, 'name');
    return arr.map((company) => ({
      id: String(company.id || company.company_id || company.name || ''),
      name: String(company.name || company.company_name || company.id || 'Company'),
      primary: !!company.primary,
      agents: Array.isArray(company.agents) ? company.agents : [],
    })).filter((company) => company.id);
  }

  async function listAgents() {
    const data = await apiJson('/v1/agent', { method: 'GET' });
    const raw = Array.isArray(data) ? data : normalizeArrayOrKeyedObject(data && data.agents, 'name');
    return raw.map((agent) => ({
      id: String(agent.id || agent.agent_id || agent.name || ''),
      name: String(agent.name || agent.agent_name || agent.id || 'XT'),
      status: agent.status !== false,
      default: !!agent.default,
      company_id: agent.company_id || agent.companyId || null,
    })).filter((agent) => agent.id);
  }

  function normalizeConversation(id, details) {
    const item = details && typeof details === 'object' ? details : {};
    const name = item.display_name || item.displayName || item.name || '-';
    return {
      id: String(item.id || item.conversation_id || id || ''),
      name: String(name || '-'),
      display_name: item.display_name || item.displayName || null,
      agent_name: item.agent_name || item.agentName || null,
      conversation_type: item.conversation_type || item.conversationType || null,
      parent_id: item.parent_id || item.parentId || null,
      updated_at: item.updated_at || item.updatedAt || null,
      message_count: item.message_count || item.messageCount || null,
      summary: item.summary || null,
    };
  }

  async function listConversations() {
    const data = await apiJson('/v1/conversations?limit=500&include_counts=false', { method: 'GET' });
    let arr = [];
    if (Array.isArray(data)) {
      arr = data.map((item) => normalizeConversation(item.id, item));
    } else if (data && Array.isArray(data.conversations)) {
      arr = data.conversations.map((item) => normalizeConversation(item.id, item));
    } else if (data && data.conversations && typeof data.conversations === 'object') {
      arr = Object.entries(data.conversations).map(([id, item]) => normalizeConversation(id, item));
    }
    arr = arr.filter((item) => item.id);
    arr.sort((a, b) => {
      if (a.updated_at && b.updated_at) return String(b.updated_at).localeCompare(String(a.updated_at));
      if (b.updated_at) return 1;
      if (a.updated_at) return -1;
      return String(a.name).localeCompare(String(b.name));
    });
    return arr;
  }

  async function getConversationHistory(args) {
    const id = args.conversationId || args.conversation_id || args.conversationId;
    const limit = args.limit || 200;
    const page = args.page || 1;
    const data = await apiJson(`/v1/conversation/${encodeURIComponent(id)}?limit=${limit}&page=${page}`, { method: 'GET' });
    return data && Array.isArray(data.conversation_history) ? data.conversation_history : [];
  }

  async function newConversation(args) {
    const settings = loadSettings();
    if (!settings.jwt) throw toolError('not logged in');
    const agentName = settings.agent_name || 'XT';
    const requestedName = (args.name || '').trim();
    const conversationName = requestedName && requestedName !== '-' ? requestedName : agentName;
    const forceNew = !!(args.forceNew || args.force_new);
    let response = null;
    if (settings.company_id) {
      try {
        response = await apiJson('/v1/conversation/group', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            conversation_name: conversationName,
            company_id: settings.company_id,
            conversation_type: 'dm',
            agent_names: [agentName],
            force_new: forceNew,
          }),
        });
      } catch (err) {
        console.warn('web new_conversation group fallback', err);
      }
    }
    if (!response) {
      response = await apiJson('/v1/conversation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent_name: agentName,
          conversation_name: conversationName,
          conversation_content: [],
        }),
      });
    }
    const id = response && (response.id || response.conversation_id);
    const name = response && (response.display_name || response.name || conversationName);
    saveSettings({ ...settings, conversation_id: id || null, conversation_name: name || null });
    return response;
  }

  async function selectConversation(args) {
    const settings = loadSettings();
    saveSettings({
      ...settings,
      conversation_id: args.id || args.conversationId || args.conversation_id || null,
      conversation_name: args.name || args.conversationName || args.conversation_name || null,
    });
    return null;
  }

  async function loginPassword(args) {
    const body = {
      username: args.email,
      password: args.password || '',
    };
    if (args.mfa_token) body.mfa_token = args.mfa_token;
    const data = await jsonFetch(`${trimSlash(args.server_url)}/v1/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const token = extractAuthToken(data);
    if (token) {
      const settings = loadSettings();
      saveSettings({
        ...settings,
        server_url: trimSlash(args.server_url),
        jwt: token,
        user_email: args.email || data.email || decodeJwtEmail(token),
      });
    }
    return data;
  }

  async function registerAccount(args) {
    const data = await jsonFetch(`${trimSlash(args.server_url)}/v1/user`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: args.email,
        first_name: args.first_name,
        last_name: args.last_name,
        password: args.password,
        confirm_password: args.password,
        invitation_id: args.invitation_id || undefined,
      }),
    });
    const token = extractAuthToken(data);
    if (token) {
      const settings = loadSettings();
      saveSettings({
        ...settings,
        server_url: trimSlash(args.server_url),
        jwt: token,
        user_email: args.email || data.email || decodeJwtEmail(token),
      });
    }
    return data;
  }

  async function requestMagicLink(args) {
    await jsonFetch(`${trimSlash(args.server_url)}/v1/login/request-link`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: args.email }),
    });
    return null;
  }

  function providerHost(provider) {
    try { return new URL(provider.authorize).host; } catch (_) { return provider.authorize || provider.name || ''; }
  }

  function dedupeLoginProviders(providers) {
    const winners = new Map();
    const order = [];
    providers.forEach((provider) => {
      if (!provider || !provider.authorize || !provider.client_id) return;
      if (!(provider.login_capable || provider.sso_only)) return;
      const host = providerHost(provider);
      if (!winners.has(host)) {
        winners.set(host, provider);
        order.push(host);
        return;
      }
      const existing = winners.get(host);
      if (provider.sso_only && !existing.sso_only) winners.set(host, provider);
    });
    return order.map((host) => winners.get(host));
  }

  async function listOAuthProviders(args) {
    const data = await jsonFetch(`${trimSlash(args.serverUrl || args.server_url || currentServerUrl())}/v1/oauth`, { method: 'GET' });
    const providers = Array.isArray(data) ? data : (data && Array.isArray(data.providers) ? data.providers : []);
    return dedupeLoginProviders(providers);
  }

  function redirectSlugFor(providerName) {
    const lower = String(providerName || '').toLowerCase();
    const stripped = lower.endsWith('_sso') ? lower.slice(0, -4) : lower;
    return stripped.replace(/[_ .]/g, '-');
  }

  function appendQuery(url, params) {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value != null && value !== '') qs.set(key, value);
    });
    const sep = String(url).includes('?') ? '&' : '?';
    return `${url}${sep}${qs.toString()}`;
  }

  async function pkceChallenge(serverUrl) {
    const data = await jsonFetch(`${trimSlash(serverUrl)}/v1/oauth2/pkce-simple`, { method: 'GET' });
    return {
      state: data && data.state,
      challenge: data && (data.challenge || data.code_challenge),
      verifier: data && data.verifier,
    };
  }

  async function buildOAuthUrl(args, connectFlow) {
    const provider = args.provider || {};
    const slug = redirectSlugFor(provider.name);
    const redirectUri = args.redirect_uri || `${trimSlash(args.web_url || currentWebUrl())}/user/close/${slug}`;
    let pkce = null;
    if (provider.pkce_required) pkce = await pkceChallenge(args.server_url || currentServerUrl());
    const params = {
      client_id: provider.client_id,
      redirect_uri: redirectUri,
      response_type: 'code',
      scope: provider.scopes,
    };
    if (provider.pkce_required && pkce && pkce.state && pkce.challenge) {
      params.state = pkce.state;
      params.code_challenge = pkce.challenge;
      params.code_challenge_method = 'S256';
    } else if (String(provider.name || '').toLowerCase().includes('google')) {
      params.access_type = 'offline';
    }
    if (connectFlow) {
      storageSet(CONNECT_FLOW_KEY, String(Date.now()));
      storageSet(CONNECT_PROVIDER_KEY, provider.name || slug);
    }
    rememberOAuthFlow(args, provider, redirectUri, connectFlow);
    return { url: appendQuery(provider.authorize, params), redirect_uri: redirectUri, pkce };
  }

  function emit(eventName, payload) {
    const listeners = eventListeners.get(eventName);
    if (!listeners) return;
    const event = { event: eventName, payload };
    Array.from(listeners).forEach((handler) => {
      try { handler(event); } catch (err) { console.warn('event listener failed', eventName, err); }
    });
  }

  function listen(eventName, handler) {
    if (!eventListeners.has(eventName)) eventListeners.set(eventName, new Set());
    const listeners = eventListeners.get(eventName);
    listeners.add(handler);
    return Promise.resolve(() => {
      listeners.delete(handler);
      if (!listeners.size) eventListeners.delete(eventName);
    });
  }

  function emitStream(streamId, event) {
    emit(`chat-stream:${streamId}`, { stream_id: streamId, event });
  }

  function newStreamId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return window.crypto.randomUUID();
    }
    return `web-stream-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  }

  function flushPendingTools(pendingTools, streamId) {
    Array.from(pendingTools.keys()).sort((a, b) => a - b).forEach((key) => {
      const tool = pendingTools.get(key);
      pendingTools.delete(key);
      let args = {};
      try { args = JSON.parse(tool.arguments || '{}'); } catch (_) { args = tool.arguments || {}; }
      emitStream(streamId, {
        kind: 'tool_call',
        data: {
          id: tool.id || `call_${key}`,
          name: tool.name || '',
          args,
          origin: 'openai_tool_call',
        },
      });
    });
  }

  function handleSsePayload(payload, state) {
    if (payload === '[DONE]') {
      flushPendingTools(state.pendingTools, state.streamId);
      emitStream(state.streamId, {
        kind: 'done',
        data: { text: state.fullText, finish_reason: state.finishReason || '' },
      });
      return true;
    }
    let parsed;
    try { parsed = JSON.parse(payload); } catch (_) { return false; }
    const objectType = parsed.object || '';
    if (objectType === 'remote_command.request') {
      emitStream(state.streamId, {
        kind: 'tool_call',
        data: {
          id: parsed.request_id || newStreamId(),
          name: parsed.tool_name || '',
          args: parsed.tool_args || {},
          origin: 'remote_command',
        },
      });
      return false;
    }
    if (objectType === 'remote_command.pending') return false;
    if (objectType === 'activity.stream') {
      emitStream(state.streamId, {
        kind: 'activity',
        data: {
          kind: parsed.type || 'activity',
          content: parsed.content || '',
          complete: !!parsed.complete,
        },
      });
      return false;
    }
    const choice = parsed.choices && parsed.choices[0];
    if (!choice) return false;
    if (choice.finish_reason) {
      state.finishReason = choice.finish_reason;
      if (choice.finish_reason === 'tool_calls') flushPendingTools(state.pendingTools, state.streamId);
    }
    const delta = choice.delta || {};
    if (typeof delta.content === 'string' && delta.content) {
      state.fullText += delta.content;
      emitStream(state.streamId, { kind: 'delta', data: { text: delta.content } });
    }
    if (Array.isArray(delta.tool_calls)) {
      delta.tool_calls.forEach((tc) => {
        const index = Number(tc.index || 0);
        const entry = state.pendingTools.get(index) || { id: '', name: '', arguments: '' };
        if (tc.id) entry.id += tc.id;
        if (tc.function && tc.function.name) entry.name += tc.function.name;
        if (tc.function && tc.function.arguments) entry.arguments += tc.function.arguments;
        state.pendingTools.set(index, entry);
      });
    }
    return false;
  }

  async function streamChat(streamId, messages, conversationName) {
    const settings = loadSettings();
    const controller = new AbortController();
    streamControllers.set(streamId, controller);
    const state = {
      streamId,
      fullText: '',
      finishReason: '',
      pendingTools: new Map(),
    };
    try {
      const resp = await fetch(apiUrl(settings, '/v1/chat/completions'), {
        method: 'POST',
        signal: controller.signal,
        headers: {
          ...authHeader(settings),
          Accept: 'text/event-stream',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: settings.agent_name || 'XT',
          user: settings.conversation_id || conversationName || '-',
          messages: messages || [],
          tools: [],
          stream: true,
          temperature: 0.7,
        }),
      });
      if (!resp.ok) {
        emitStream(streamId, { kind: 'error', data: { message: await readError(resp) } });
        return;
      }
      if (!resp.body || !resp.body.getReader) {
        const data = await resp.json().catch(() => null);
        const text = data && data.choices && data.choices[0] && data.choices[0].message
          ? data.choices[0].message.content || ''
          : '';
        if (text) emitStream(streamId, { kind: 'delta', data: { text } });
        emitStream(streamId, { kind: 'done', data: { text, finish_reason: 'stop' } });
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true }).replace(/\r\n/g, '\n');
        let idx = buffer.indexOf('\n\n');
        while (idx !== -1) {
          const raw = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          let payload = '';
          raw.split('\n').forEach((line) => {
            if (!line.startsWith('data:')) return;
            const part = line.slice(5).trimStart();
            payload = payload ? `${payload}\n${part}` : part;
          });
          if (payload && handleSsePayload(payload, state)) return;
          idx = buffer.indexOf('\n\n');
        }
      }
      flushPendingTools(state.pendingTools, streamId);
      emitStream(streamId, {
        kind: 'done',
        data: { text: state.fullText, finish_reason: state.finishReason || '' },
      });
    } catch (err) {
      if (err && err.name === 'AbortError') return;
      emitStream(streamId, {
        kind: 'error',
        data: { message: err && err.message ? err.message : String(err) },
      });
    } finally {
      streamControllers.delete(streamId);
    }
  }

  async function chatSend(args) {
    const streamId = args.stream_id || newStreamId();
    setTimeout(() => {
      streamChat(streamId, args.messages || [], args.conversation_name || '-');
    }, 0);
    return streamId;
  }

  async function agentVision(args) {
    const settings = loadSettings();
    if (!settings.agent_id) throw toolError('no agent selected');
    return apiJson(`/v1/agent/${encodeURIComponent(settings.agent_id)}/vision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: args.prompt,
        images: args.images || [],
        use_smartest: !!args.use_smartest,
      }),
    });
  }

  async function workspaceList(args) {
    const settings = loadSettings();
    if (!settings.conversation_id) throw toolError('no active conversation');
    const params = new URLSearchParams();
    if (args.subPath || args.sub_path || args.path) params.set('path', args.subPath || args.sub_path || args.path);
    const qs = params.toString();
    const data = await apiJson(`/v1/conversation/${encodeURIComponent(settings.conversation_id)}/workspace${qs ? `?${qs}` : ''}`, {
      method: 'GET',
    });
    return data && (data.items || data.files || data) || [];
  }

  async function invoke(command, payload) {
    const args = payload || {};
    switch (command) {
      case 'frontend_log':
        console[args.level === 'error' ? 'error' : args.level === 'warn' ? 'warn' : 'log']('[frontend]', args.message || '');
        return null;
      case 'get_settings': {
        const settings = loadSettings();
        if (settings.jwt && !settings.user_email) hydrateUser(settings).catch(() => {});
        return settings;
      }
      case 'save_settings':
        return saveSettings(args.settings || args);
      case 'logout':
        saveSettings({
          ...loadSettings(),
          jwt: null,
          user_email: null,
          agent_id: null,
          agent_name: null,
          company_id: null,
          company_name: null,
          conversation_id: null,
          conversation_name: null,
        });
        return null;
      case 'list_service_brands':
        return serviceBrands();
      case 'list_oauth_providers':
        return listOAuthProviders(args);
      case 'build_oauth_login_url':
        return buildOAuthUrl(args.args || args, false);
      case 'build_oauth_connect_url':
        return buildOAuthUrl(args.args || args, true);
      case 'login_password':
        return loginPassword(args.args || args);
      case 'register_account':
        return registerAccount(args.args || args);
      case 'request_magic_link':
        return requestMagicLink(args.args || args);
      case 'list_companies':
        return listCompanies();
      case 'list_agents':
        return listAgents();
      case 'list_conversations':
        return listConversations();
      case 'select_conversation':
        return selectConversation(args);
      case 'get_conversation_history':
        return getConversationHistory(args);
      case 'new_conversation':
        return newConversation(args);
      case 'chat_send':
        return chatSend(args.args || args);
      case 'agent_vision':
        return agentVision(args.args || args);
      case 'workspace_list':
        return workspaceList(args);
      case 'sudo_status':
        return { authenticated: false, remembered: false };
      case 'sudo_auth':
      case 'sudo_clear':
        throw toolError('Privileged commands are unavailable in the web client.');
      case 'desktop_update_check':
        return {
          update_available: false,
          ready: false,
          current_build_id: 'web',
          latest_build_id: 'web',
          app_version: 'web',
        };
      case 'desktop_update_install':
        return { installed: false, message: 'Desktop updates are unavailable in the web client.' };
      case 'voice_start_recording':
      case 'voice_stop_recording':
      case 'voice_cancel_recording':
        throw toolError('Native voice recording is unavailable in the web client.');
      case 'check_local_agixt':
        return { running: false, status: 'unavailable' };
      case 'detect_hardware':
        return { gpu: null, total_ram_gb: null, recommended_model: null };
      case 'default_install_path':
        return '';
      case 'install_agixt_local':
        throw toolError('Local AGiXT installation is unavailable in the web client.');
      case 'show_chat':
      case 'hide_chat':
      case 'toggle_chat':
      case 'toggle_sidebar':
      case 'set_sidebar_visible':
      case 'set_workspace_window_mode':
        return null;
      case 'shell_run':
      case 'shell_open':
      case 'desktop_screenshot':
      case 'desktop_click':
      case 'desktop_move':
      case 'desktop_drag':
      case 'desktop_scroll':
      case 'desktop_type':
      case 'fs_read':
      case 'fs_write':
      case 'fs_append':
      case 'fs_edit':
      case 'fs_list':
      case 'fs_stat':
      case 'fs_mkdir':
      case 'fs_delete':
      case 'fs_rename':
      case 'workspace_upload_local':
      case 'workspace_download_to_local':
        throw toolError(`${command} is unavailable in the web client.`);
      default:
        throw toolError(`Unsupported web runtime command: ${command}`);
    }
  }

  function openUrl(url) {
    const text = String(url || '');
    if (/(\?|&)response_type=code(&|$)/.test(text) || (/\/oauth/i.test(text) && /(\?|&)client_id=/.test(text))) {
      window.location.assign(text);
      return Promise.resolve();
    }
    const opened = window.open(text, '_blank', 'noopener,noreferrer');
    if (!opened) window.location.assign(text);
    return Promise.resolve();
  }

  function renderOAuthStatus(kind, title, message) {
    const root = document.getElementById('oauth-status');
    if (!root) return;
    root.className = kind || '';
    const h = root.querySelector('h1');
    const p = root.querySelector('p');
    if (h) h.textContent = title || '';
    if (p) p.textContent = message || '';
  }

  async function handleOAuthClose() {
    const parts = window.location.pathname.split('/').filter(Boolean);
    const providerFromPath = parts[0] === 'user' && parts[1] === 'close' ? parts[2] : '';
    const params = new URLSearchParams(window.location.search);
    const error = params.get('error');
    const token = params.get('token') || params.get('jwt');
    const code = params.get('code');
    if (error) {
      renderOAuthStatus('error', 'Authentication failed', error);
      setTimeout(() => { window.location.href = '/'; }, 2500);
      return;
    }
    const settings = loadSettings();
    const oauthFlow = pendingOAuthFlow();
    const callbackSettings = oauthFlow ? {
      ...settings,
      server_url: trimSlash(oauthFlow.server_url || settings.server_url),
      web_url: trimSlash(oauthFlow.web_url || settings.web_url),
      service_brand: oauthFlow.service_brand || settings.service_brand,
    } : settings;
    if (token) {
      saveSettings({
        ...callbackSettings,
        jwt: token,
        user_email: callbackSettings.user_email || decodeJwtEmail(token),
      });
      clearOAuthFlow();
      renderOAuthStatus('done', 'Signed in', 'Redirecting back to AGiXT...');
      setTimeout(() => { window.location.href = '/'; }, 700);
      return;
    }
    if (!code || !providerFromPath) {
      renderOAuthStatus('error', 'Missing OAuth response', 'No authorization code was returned.');
      setTimeout(() => { window.location.href = '/'; }, 2500);
      return;
    }
    const connectStarted = Number(storageGet(CONNECT_FLOW_KEY) || '0');
    const isConnect = !!callbackSettings.jwt
      && ((oauthFlow && oauthFlow.connect) || (connectStarted && Date.now() - connectStarted < 300000));
    const providerForPost = isConnect
      ? redirectSlugFor(storageGet(CONNECT_PROVIDER_KEY) || (oauthFlow && oauthFlow.provider) || providerFromPath)
      : providerFromPath;
    const headers = { 'Content-Type': 'application/json' };
    if (isConnect && callbackSettings.jwt) Object.assign(headers, authHeader(callbackSettings));
    const body = {
      code,
      referrer: oauthFlow && oauthFlow.redirect_uri
        ? oauthFlow.redirect_uri
        : `${trimSlash(callbackSettings.web_url || currentWebUrl())}/user/close/${providerFromPath}`,
    };
    if (params.get('state')) body.state = params.get('state');
    try {
      const data = await jsonFetch(`${trimSlash(callbackSettings.server_url)}/v1/oauth2/${providerForPost}`, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
      });
      clearOAuthFlow();
      if (isConnect) {
        renderOAuthStatus('done', 'Connected', 'Redirecting back to AGiXT...');
        emit('agixt-extension-connected', { provider: providerForPost });
      } else {
        const jwt = extractAuthToken(data);
        if (!jwt) throw toolError('OAuth succeeded, but AGiXT did not return a token.');
        saveSettings({
          ...callbackSettings,
          jwt,
          user_email: data.email || callbackSettings.user_email || decodeJwtEmail(jwt),
        });
        renderOAuthStatus('done', 'Signed in', 'Redirecting back to AGiXT...');
      }
      setTimeout(() => { window.location.href = '/'; }, 800);
    } catch (err) {
      clearOAuthFlow();
      renderOAuthStatus('error', 'OAuth callback failed', err && err.error ? err.error : String(err));
      setTimeout(() => { window.location.href = '/'; }, 3500);
    }
  }

  window.__TAURI__ = {
    core: { invoke },
    event: {
      listen,
      emit: (eventName, payload) => {
        emit(eventName, payload);
        return Promise.resolve();
      },
    },
    opener: { openUrl },
    shell: { open: openUrl },
    window: {
      getCurrentWindow: () => ({
        outerSize: () => Promise.resolve({ width: window.outerWidth, height: window.outerHeight }),
        outerPosition: () => Promise.resolve({ x: window.screenX, y: window.screenY }),
        setSize: () => Promise.resolve(),
        setPosition: () => Promise.resolve(),
      }),
      PhysicalSize: function PhysicalSize(width, height) { this.width = width; this.height = height; },
      LogicalSize: function LogicalSize(width, height) { this.width = width; this.height = height; },
      PhysicalPosition: function PhysicalPosition(x, y) { this.x = x; this.y = y; },
      LogicalPosition: function LogicalPosition(x, y) { this.x = x; this.y = y; },
    },
  };

  window.AgixtWebRuntime = {
    handleOAuthClose,
    loadSettings,
    saveSettings,
    redirectSlugFor,
  };

  document.documentElement.classList.add('agixt-web-client');
})();

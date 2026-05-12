/* AGiXT user-level notifications client.
 *
 * Wire-compatible with web/hooks/useUserNotifications.ts:
 *   url: ws[s]://{host}/v1/user/notifications?authorization={jwt}
 *
 * Bridges incoming events to:
 *   - OS-native popups via tauri-plugin-notification
 *   - DOM CustomEvents that app.js subscribes to (conversation list
 *     refresh, rename pickup, in-app unread badge)
 *
 * Mirrors the web client's heartbeat (30s ping → pong w/ 10s timeout),
 * exponential-backoff reconnect (1s → 30s, 10 attempts), self-message
 * filter, and active-conversation suppression.
 */
(function () {
  const HEARTBEAT_INTERVAL = 30000;
  const HEARTBEAT_TIMEOUT = 10000;
  const RECONNECT_BASE_DELAY = 1000;
  const RECONNECT_MAX_DELAY = 30000;
  const MAX_RECONNECT_ATTEMPTS = 10;

  const log = window.AgixtFrontendLog || function () {};
  const tauri = () => window.__TAURI__;
  const notif = () => (tauri() && tauri().notification) || null;

  let ws = null;
  let serverUrl = null;
  let jwt = null;
  let currentUserId = null;
  let getActiveConversationId = () => null;
  let enabled = true;
  let permission = 'unknown';

  let heartbeatInterval = null;
  let heartbeatTimeout = null;
  let reconnectTimeout = null;
  let reconnectAttempt = 0;
  let intentionalDisconnect = false;
  let status = 'disconnected';

  function setStatus(next) {
    if (status === next) return;
    status = next;
    dispatch('agixt-notifications-status', { status: next });
  }

  function dispatch(name, detail) {
    try {
      window.dispatchEvent(new CustomEvent(name, { detail: detail || {} }));
    } catch (_) { /* ignore */ }
  }

  function decodeJwtSub(token) {
    if (!token || typeof token !== 'string') return null;
    const parts = token.split('.');
    if (parts.length < 2) return null;
    try {
      const json = atob(parts[1].replace(/-/g, '+').replace(/_/g, '/'));
      const payload = JSON.parse(json);
      return payload && payload.sub ? String(payload.sub) : null;
    } catch (_) { return null; }
  }

  async function ensurePermission() {
    const n = notif();
    if (!n) { permission = 'unsupported'; return permission; }
    try {
      const granted = typeof n.isPermissionGranted === 'function'
        ? await n.isPermissionGranted()
        : true;
      if (granted) { permission = 'granted'; return permission; }
      if (typeof n.requestPermission === 'function') {
        const result = await n.requestPermission();
        permission = result === 'granted' ? 'granted' : 'denied';
        return permission;
      }
      permission = 'denied';
      return permission;
    } catch (err) {
      log('warn', 'notifications: permission check failed', String(err));
      permission = 'unknown';
      return permission;
    }
  }

  function showOsNotification(title, body) {
    if (!enabled) return;
    if (permission !== 'granted') return;
    const n = notif();
    if (!n || typeof n.sendNotification !== 'function') return;
    try {
      n.sendNotification({ title: title || 'AGiXT', body: body || '' });
    } catch (err) {
      log('warn', 'notifications: sendNotification failed', String(err));
    }
  }

  function buildWsUrl() {
    if (!serverUrl || !jwt) return null;
    let parsed;
    try { parsed = new URL(serverUrl); } catch (_) { return null; }
    const proto = parsed.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${parsed.host}/v1/user/notifications?authorization=${encodeURIComponent(jwt)}`;
  }

  function stopHeartbeat() {
    if (heartbeatInterval) { clearInterval(heartbeatInterval); heartbeatInterval = null; }
    if (heartbeatTimeout) { clearTimeout(heartbeatTimeout); heartbeatTimeout = null; }
  }

  function startHeartbeat() {
    stopHeartbeat();
    heartbeatInterval = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        try { ws.send(JSON.stringify({ type: 'ping' })); } catch (_) { /* ignore */ }
        heartbeatTimeout = setTimeout(() => {
          log('warn', 'notifications: heartbeat timeout — closing socket');
          try { if (ws) ws.close(); } catch (_) { /* ignore */ }
        }, HEARTBEAT_TIMEOUT);
      }
    }, HEARTBEAT_INTERVAL);
  }

  function scheduleReconnect() {
    if (intentionalDisconnect) return;
    reconnectAttempt += 1;
    if (reconnectAttempt > MAX_RECONNECT_ATTEMPTS) {
      setStatus('error');
      log('error', 'notifications: max reconnect attempts reached');
      return;
    }
    const delay = Math.min(RECONNECT_BASE_DELAY * Math.pow(2, reconnectAttempt - 1), RECONNECT_MAX_DELAY);
    setStatus('reconnecting');
    if (reconnectTimeout) clearTimeout(reconnectTimeout);
    reconnectTimeout = setTimeout(() => connectInternal(), delay);
  }

  function connectInternal() {
    if (!enabled) return;
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
    const url = buildWsUrl();
    if (!url) {
      setStatus('error');
      log('warn', 'notifications: missing server/jwt — not connecting');
      return;
    }
    intentionalDisconnect = false;
    setStatus('connecting');
    let socket;
    try {
      socket = new WebSocket(url);
    } catch (err) {
      log('error', 'notifications: ws construct failed', String(err));
      scheduleReconnect();
      return;
    }
    ws = socket;
    socket.onopen = () => {
      reconnectAttempt = 0;
      setStatus('connected');
      startHeartbeat();
    };
    socket.onmessage = (ev) => {
      let data;
      try { data = JSON.parse(ev.data); } catch (_) { return; }
      handleEnvelope(data);
    };
    socket.onerror = () => {
      log('warn', 'notifications: ws error');
    };
    socket.onclose = (ev) => {
      stopHeartbeat();
      if (ws === socket) ws = null;
      if (intentionalDisconnect || ev.code === 1000 || ev.code === 1001) {
        setStatus('disconnected');
        return;
      }
      scheduleReconnect();
    };
  }

  function isFromSelf(data) {
    return !!(currentUserId && data && data.sender_user_id === currentUserId);
  }

  function isActiveConversation(conversationId) {
    if (!conversationId) return false;
    let active = null;
    try { active = getActiveConversationId && getActiveConversationId(); } catch (_) { /* ignore */ }
    return !!active && active === conversationId;
  }

  // Mirrors web's isTabVisible && isActiveConversation suppression. The
  // Tauri webview honors document.hidden when the window is minimized or
  // hidden behind another app on Linux/macOS.
  function isWindowVisible() {
    if (typeof document === 'undefined') return true;
    return !document.hidden;
  }

  function handleEnvelope(env) {
    if (!env || !env.type) return;
    switch (env.type) {
      case 'pong':
        if (heartbeatTimeout) { clearTimeout(heartbeatTimeout); heartbeatTimeout = null; }
        return;
      case 'heartbeat':
      case 'connected':
        return;
      case 'error':
        log('warn', 'notifications: server error', env.message || '');
        return;
      case 'conversation_created':
        dispatch('agixt-conversation-created', env.data || {});
        return;
      case 'conversation_deleted':
        dispatch('agixt-conversation-deleted', env.data || {});
        return;
      case 'conversation_renamed':
        // Reuse the event chat.js already emits so the existing listener
        // in app.js refreshes the chip + cached conversation entry.
        dispatch('agixt-conversation-renamed', env.data || {});
        return;
      case 'message_added': {
        const data = env.data || {};
        if (isFromSelf(data)) return;
        // Suppress only when the user is actively looking at this convo.
        if (isWindowVisible() && isActiveConversation(data.conversation_id)) return;
        const title = data.conversation_name || 'New message';
        const sender = data.sender_name ? `${data.sender_name}: ` : '';
        const body = data.message_preview ? `${sender}${data.message_preview}` : (sender || 'You have a new message');
        showOsNotification(title, body);
        dispatch('agixt-message-notification', {
          conversationId: data.conversation_id,
          conversationName: data.conversation_name,
          senderName: data.sender_name,
          messagePreview: data.message_preview,
          timestamp: data.timestamp,
        });
        return;
      }
      case 'mention': {
        const data = env.data || {};
        if (isFromSelf(data)) return;
        const title = `@Mentioned in ${data.conversation_name || 'a conversation'}`;
        const body = data.message_preview || 'You were mentioned';
        showOsNotification(title, body);
        dispatch('agixt-mention-notification', { ...data });
        return;
      }
      case 'reply': {
        const data = env.data || {};
        if (isFromSelf(data)) return;
        const title = `Reply in ${data.conversation_name || 'a conversation'}`;
        const body = data.message_preview || 'Someone replied to your message';
        showOsNotification(title, body);
        dispatch('agixt-reply-notification', { ...data });
        return;
      }
      case 'system_notification': {
        const data = env.data || {};
        const title = data.title || 'AGiXT';
        const body = data.message || '';
        showOsNotification(title, body);
        dispatch('agixt-system-notification', data);
        return;
      }
      case 'agent_working_started':
        dispatch('agixt-agent-working-started', env.data || {});
        return;
      case 'agent_working_ended':
        dispatch('agixt-agent-working-ended', env.data || {});
        return;
      case 'deployment_execution_updated':
        dispatch('agixt-deployment-execution-updated', env.data || {});
        return;
      default:
        return;
    }
  }

  function disconnect() {
    intentionalDisconnect = true;
    stopHeartbeat();
    if (reconnectTimeout) { clearTimeout(reconnectTimeout); reconnectTimeout = null; }
    if (ws) {
      try { ws.close(1000, 'intentional'); } catch (_) { /* ignore */ }
      ws = null;
    }
    reconnectAttempt = 0;
    setStatus('disconnected');
  }

  /** Configure & open the WebSocket. Safe to call repeatedly — when
   *  serverUrl/jwt change, the existing socket is torn down. */
  async function start(opts) {
    opts = opts || {};
    const nextServer = opts.serverUrl || serverUrl;
    const nextJwt = opts.jwt || jwt;
    if (!nextServer || !nextJwt) {
      log('warn', 'notifications.start: missing server/jwt');
      return;
    }
    const credentialsChanged = nextServer !== serverUrl || nextJwt !== jwt;
    serverUrl = nextServer;
    jwt = nextJwt;
    currentUserId = opts.currentUserId || decodeJwtSub(jwt);
    if (typeof opts.getActiveConversationId === 'function') {
      getActiveConversationId = opts.getActiveConversationId;
    }
    if (typeof opts.enabled === 'boolean') enabled = opts.enabled;
    await ensurePermission();
    if (credentialsChanged && ws) {
      try { ws.close(1000, 'reauth'); } catch (_) { /* ignore */ }
      ws = null;
      reconnectAttempt = 0;
    }
    if (enabled) connectInternal();
  }

  function setEnabled(on) {
    enabled = !!on;
    if (!enabled) disconnect();
    else if (serverUrl && jwt) {
      intentionalDisconnect = false;
      connectInternal();
    }
  }

  window.AgixtNotifications = {
    start,
    stop: disconnect,
    setEnabled,
    requestPermission: ensurePermission,
    get status() { return status; },
    get permission() { return permission; },
  };
})();

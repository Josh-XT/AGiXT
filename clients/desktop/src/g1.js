/* Even Realities G1 bridge for AGiXT Desktop.
 *
 * Rust owns Bluetooth and the packet protocol; this file connects that
 * native surface to chat, notifications, settings, and voice recording.
 */
(function () {
  const tauri = window.__TAURI__;
  if (!tauri || !tauri.core || !tauri.core.invoke) return;

  const invoke = tauri.core.invoke;
  const events = tauri.event || {};

  let settingsCache = null;
  let statusCache = null;
  let unlistenG1 = null;
  let nativeG1Channel = null;
  let started = false;
  let streamTimer = null;
  let pendingStreamText = '';
  let lastStreamText = '';
  let glassesMicMode = null;

  function log(level, message, detail) {
    try {
      if (window.AgixtFrontendLog) {
        window.AgixtFrontendLog(level, detail ? `${message}: ${detail}` : message);
        return;
      }
    } catch (_) {}
    const fn = level === 'error' ? console.error : level === 'warn' ? console.warn : console.log;
    try { fn.call(console, message, detail || ''); } catch (_) {}
  }

  function errMsg(err) {
    if (!err) return 'Unknown error';
    if (typeof err === 'string') return err;
    return err.error || err.detail || err.message || String(err);
  }

  async function loadSettings(force) {
    if (!force && settingsCache) return settingsCache;
    settingsCache = await invoke('get_settings');
    return settingsCache;
  }

  function syncSettings(next) {
    if (next) settingsCache = next;
  }

  function publishStatus(status) {
    if (!status) return;
    statusCache = status;
    window.dispatchEvent(new CustomEvent('agixt-g1-status', { detail: status }));
  }

  async function refreshStatus() {
    try {
      const status = await invoke('g1_status');
      publishStatus(status);
      return status;
    } catch (err) {
      log('warn', 'G1 status failed', errMsg(err));
      throw err;
    }
  }

  async function invokeStatus(command, args) {
    const status = await invoke(command, args || {});
    publishStatus(status);
    return status;
  }

  function settingEnabled(settings, key, fallback) {
    if (!settings || typeof settings[key] === 'undefined') return fallback;
    return !!settings[key];
  }

  function canUseDisplay(settings) {
    return !!settings
      && settingEnabled(settings, 'g1_enabled', false)
      && settingEnabled(settings, 'g1_display_enabled', true);
  }

  async function outputReady(kind) {
    const settings = await loadSettings();
    if (!canUseDisplay(settings)) return false;
    if (kind === 'ai' && !settingEnabled(settings, 'g1_show_ai_responses', true)) return false;
    if (kind === 'notification' && !settingEnabled(settings, 'g1_notification_forwarding', true)) return false;
    const status = statusCache || await refreshStatus().catch(() => null);
    return !!(status && status.supported && status.connected);
  }

  async function sendText(text, options) {
    const opts = options || {};
    const status = await invoke('g1_send_text', {
      text: String(text || ''),
      streaming: !!opts.streaming,
      delayMs: opts.delayMs == null ? 600 : opts.delayMs,
    });
    publishStatus(status);
    return status;
  }

  async function sendTextIfReady(text, options, kind) {
    try {
      if (!await outputReady(kind || 'ai')) return null;
      return await sendText(text, options);
    } catch (err) {
      log('warn', 'G1 text send failed', errMsg(err));
      return null;
    }
  }

  function queueStreamingText(text) {
    pendingStreamText = String(text || '');
    if (!pendingStreamText.trim() || pendingStreamText === lastStreamText) return;
    if (streamTimer) return;
    streamTimer = window.setTimeout(async () => {
      streamTimer = null;
      const textToSend = pendingStreamText;
      if (!textToSend.trim() || textToSend === lastStreamText) return;
      lastStreamText = textToSend;
      await sendTextIfReady(textToSend, { streaming: true, delayMs: 120 }, 'ai');
    }, 320);
  }

  async function handleAssistantStream(ev) {
    const detail = ev && ev.detail ? ev.detail : {};
    if (!detail.text) return;
    queueStreamingText(detail.text);
  }

  async function handleAssistantFinal(ev) {
    const detail = ev && ev.detail ? ev.detail : {};
    const text = String(detail.text || '').trim();
    if (!text) return;
    pendingStreamText = '';
    lastStreamText = text;
    if (streamTimer) {
      window.clearTimeout(streamTimer);
      streamTimer = null;
    }
    await sendTextIfReady(text, { streaming: false, delayMs: 650 }, 'ai');
  }

  function notificationPayload(eventName, detail) {
    const data = detail || {};
    if (eventName === 'agixt-message-notification') {
      return {
        title: data.conversationName || 'New AGiXT message',
        subtitle: data.senderName || '',
        message: data.messagePreview || 'You have a new message',
        display_name: 'AGiXT',
        app_identifier: 'systems.xt.agixt.desktop',
      };
    }
    if (eventName === 'agixt-mention-notification') {
      return {
        title: `Mention in ${data.conversation_name || data.conversationName || 'AGiXT'}`,
        subtitle: data.sender_name || data.senderName || '',
        message: data.message_preview || data.messagePreview || 'You were mentioned',
        display_name: 'AGiXT',
        app_identifier: 'systems.xt.agixt.desktop',
      };
    }
    if (eventName === 'agixt-reply-notification') {
      return {
        title: `Reply in ${data.conversation_name || data.conversationName || 'AGiXT'}`,
        subtitle: data.sender_name || data.senderName || '',
        message: data.message_preview || data.messagePreview || 'Someone replied',
        display_name: 'AGiXT',
        app_identifier: 'systems.xt.agixt.desktop',
      };
    }
    return {
      title: data.title || 'AGiXT',
      subtitle: data.subtitle || '',
      message: data.message || data.body || '',
      display_name: data.display_name || data.displayName || 'AGiXT',
      app_identifier: data.app_identifier || data.appIdentifier || 'systems.xt.agixt.desktop',
    };
  }

  async function forwardNotification(eventName, detail) {
    try {
      if (!await outputReady('notification')) return;
      const input = notificationPayload(eventName, detail);
      const status = await invoke('g1_send_notification', { input });
      publishStatus(status);
    } catch (err) {
      log('warn', 'G1 notification forward failed', errMsg(err));
    }
  }

  function voiceApi() {
    return window.AgixtVoiceInput || null;
  }

  function blobFromBase64(b64, mime) {
    const bin = atob(b64 || '');
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], { type: mime || 'audio/wav' });
  }

  async function startGlassesMic(mode) {
    await invokeStatus('g1_start_mic_capture');
    glassesMicMode = mode || 'voice';
    return true;
  }

  async function stopGlassesMic() {
    const mode = glassesMicMode || 'voice';
    glassesMicMode = null;
    const capture = await invoke('g1_stop_mic_capture');
    const blob = blobFromBase64(capture && capture.audio_base64, capture && capture.mime_type);
    const voice = voiceApi();
    if (!voice || typeof voice.transcribeBlob !== 'function') {
      throw new Error('Desktop voice transcription bridge is unavailable.');
    }
    await voice.transcribeBlob(blob, (capture && capture.mime_type) || 'audio/wav', { mode });
  }

  async function handleButtonAction(action) {
    const voice = voiceApi();
    if (!voice) return;
    try {
      if (action === 'voice_start') {
        await sendTextIfReady('Listening...', { streaming: true, delayMs: 120 }, 'ai');
        try {
          await startGlassesMic('voice');
        } catch (err) {
          log('warn', 'G1 microphone capture failed, falling back to desktop mic', errMsg(err));
          await voice.start();
        }
      } else if (action === 'voice_stop') {
        await sendTextIfReady('Processing...', { streaming: true, delayMs: 120 }, 'ai');
        if (glassesMicMode === 'voice') {
          await stopGlassesMic();
        } else {
          await voice.stop();
        }
      } else if (action === 'conversation_toggle') {
        const state = typeof voice.getState === 'function' ? voice.getState() : {};
        if (glassesMicMode === 'conversation') {
          await sendTextIfReady('Summarizing conversation...', { streaming: true, delayMs: 120 }, 'ai');
          await stopGlassesMic();
        } else if (state.state === 'recording' && state.mode === 'conversation') {
          await sendTextIfReady('Summarizing conversation...', { streaming: true, delayMs: 120 }, 'ai');
          if (typeof voice.toggleConversation === 'function') await voice.toggleConversation();
        } else {
          await sendTextIfReady('Recording conversation...', { streaming: true, delayMs: 120 }, 'ai');
          try {
            await startGlassesMic('conversation');
          } catch (err) {
            log('warn', 'G1 conversation capture failed, falling back to desktop mic', errMsg(err));
            if (typeof voice.toggleConversation === 'function') await voice.toggleConversation();
          }
        }
      }
    } catch (err) {
      glassesMicMode = null;
      log('warn', 'G1 voice action failed', errMsg(err));
    }
  }

  function handleG1Event(message) {
    const payload = message && Object.prototype.hasOwnProperty.call(message, 'payload')
      ? message.payload
      : message;
    if (!payload) return;
    if (payload.type === 'status' && payload.status) publishStatus(payload.status);
    if (payload.type === 'battery' && payload.status) publishStatus(payload.status);
    window.dispatchEvent(new CustomEvent('agixt-g1-event', { detail: payload }));
    if (payload.type === 'button' && payload.action) {
      void handleButtonAction(payload.action);
    }
  }

  async function listenNativeG1Plugin() {
    const isAndroid = /Android/i.test(window.navigator && window.navigator.userAgent || '');
    if (!isAndroid || nativeG1Channel || !tauri.core.Channel) return;
    try {
      nativeG1Channel = new tauri.core.Channel();
      nativeG1Channel.onmessage = handleG1Event;
      await invoke('plugin:g1|registerListener', {
        event: 'g1-event',
        handler: nativeG1Channel,
      });
    } catch (err) {
      nativeG1Channel = null;
      log('warn', 'Native G1 event listener failed', errMsg(err));
    }
  }

  async function scanAndConnect() {
    await loadSettings(true);
    return invokeStatus('g1_scan_and_connect');
  }

  async function reconnectSaved() {
    await loadSettings(true);
    return invokeStatus('g1_reconnect_saved');
  }

  async function disconnect() {
    return invokeStatus('g1_disconnect');
  }

  async function sync() {
    await loadSettings(true);
    return invokeStatus('g1_sync');
  }

  async function requestBattery() {
    return invokeStatus('g1_request_battery');
  }

  async function clearDisplay() {
    return invokeStatus('g1_clear_display');
  }

  async function sendNotification(input) {
    return invokeStatus('g1_send_notification', { input });
  }

  async function applyDisplaySettings(settings) {
    if (settings) syncSettings(settings);
    const s = settings || await loadSettings();
    let status = await invokeStatus('g1_set_brightness', {
      level: Number(s.g1_brightness || 28),
      auto: !!s.g1_auto_brightness,
    });
    status = await invokeStatus('g1_set_headup_angle', {
      angle: Number(s.g1_headup_angle || 20),
    });
    status = await invokeStatus('g1_set_wear_detection', {
      enabled: settingEnabled(s, 'g1_wear_detection', true),
    });
    status = await invokeStatus('g1_set_display_position', {
      input: {
        height: Number(s.g1_display_height || 0),
        depth: Number(s.g1_display_depth || 5),
      },
    });
    status = await invokeStatus('g1_set_silent_mode', {
      enabled: !settingEnabled(s, 'g1_display_enabled', true),
    });
    return status;
  }

  async function maybeAutoReconnect() {
    const settings = await loadSettings().catch(() => null);
    if (!settings || !settings.g1_enabled || !settings.g1_auto_connect) return;
    if (!(settings.g1_left_device_id || settings.g1_right_device_id || settings.g1_left_device_name || settings.g1_right_device_name)) return;
    const status = await refreshStatus().catch(() => null);
    if (!status || !status.supported || status.connected || status.scanning) return;
    try {
      await reconnectSaved();
    } catch (err) {
      log('warn', 'G1 auto reconnect failed', errMsg(err));
    }
  }

  async function start() {
    if (started) return;
    started = true;
    if (events.listen && !unlistenG1) {
      try {
        unlistenG1 = await events.listen('g1-event', handleG1Event);
      } catch (err) {
        log('warn', 'G1 event listener failed', errMsg(err));
      }
    }
    await listenNativeG1Plugin();
    window.addEventListener('agixt-chat-assistant-stream', handleAssistantStream);
    window.addEventListener('agixt-chat-assistant-final', handleAssistantFinal);
    [
      'agixt-message-notification',
      'agixt-mention-notification',
      'agixt-reply-notification',
      'agixt-system-notification',
    ].forEach((name) => {
      window.addEventListener(name, (ev) => { void forwardNotification(name, ev.detail || {}); });
    });
    window.addEventListener('agixt-g1-settings-saved', (ev) => {
      if (ev && ev.detail && ev.detail.settings) syncSettings(ev.detail.settings);
    });
    await refreshStatus().catch(() => null);
    window.setTimeout(() => { void maybeAutoReconnect(); }, 1200);
  }

  window.AgixtG1 = {
    start,
    refreshStatus,
    scanAndConnect,
    reconnectSaved,
    disconnect,
    sync,
    sendText,
    sendNotification,
    requestBattery,
    clearDisplay,
    applyDisplaySettings,
    syncSettings,
    getStatus: () => statusCache,
    getSettings: () => settingsCache,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { void start(); }, { once: true });
  } else {
    void start();
  }
}());

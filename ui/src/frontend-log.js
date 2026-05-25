/* Lightweight renderer diagnostics. In the packaged Tauri webview,
 * console output is easy to miss, so mirror important frontend lifecycle
 * events and uncaught JS errors into the Rust tracing log.
 */
(function () {
  const tauri = window.__TAURI__;
  const invoke = tauri && tauri.core && tauri.core.invoke;

  function asText(value) {
    if (value == null) return '';
    if (value instanceof Error) return value.stack || value.message || String(value);
    if (typeof value === 'string') return value;
    try { return JSON.stringify(value); } catch (_) { return String(value); }
  }

  function log(level, message, detail) {
    const text = detail === undefined ? asText(message) : `${asText(message)} ${asText(detail)}`;
    if (!invoke) return;
    try {
      invoke('frontend_log', { level: level || 'info', message: text }).catch(() => {});
    } catch (_) {
      // Diagnostics should never affect the app.
    }
  }

  window.AgixtFrontendLog = log;

  window.addEventListener('error', (event) => {
    log('error', 'renderer error', {
      message: event.message,
      source: event.filename,
      line: event.lineno,
      column: event.colno,
      error: event.error ? asText(event.error) : '',
    });
  });

  window.addEventListener('unhandledrejection', (event) => {
    log('error', 'renderer unhandled rejection', asText(event.reason));
  });

  window.addEventListener('pagehide', () => log('warn', 'renderer pagehide'));
  window.addEventListener('beforeunload', () => log('warn', 'renderer beforeunload'));
  document.addEventListener('visibilitychange', () => {
    log('info', `renderer visibility ${document.visibilityState}`);
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => log('info', 'renderer DOMContentLoaded'), { once: true });
  }
})();

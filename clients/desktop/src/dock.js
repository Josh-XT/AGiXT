/* Dock controller — tray-anchored popover variant.
 *
 * The Tauri main window is hidden at launch and only shown when the user
 * clicks the system tray icon (or hits Ctrl+Shift+Space). On focus loss
 * we hide it again so it behaves like a Discord/Slack tray menu rather
 * than a sticky chat panel. The window deliberately *floats above*
 * whatever's underneath — overlap is the desired behavior.
 *
 * This module exists mostly for back-compat with callers (tests, the
 * older `set_dock_mode('panel')` calls in the codebase) and to provide
 * the close (X) button + Esc-to-hide affordances.
 */
(function () {
  const tauri = window.__TAURI__;
  if (!tauri) return;
  const invoke = tauri.core.invoke;
  const event = tauri.event;

  async function show() {
    try { await invoke('show_chat'); } catch (e) { console.warn('show_chat', e); }
  }
  async function hide() {
    try { await invoke('hide_chat'); } catch (e) { console.warn('hide_chat', e); }
  }
  async function toggle() {
    try { await invoke('toggle_chat'); } catch (e) { console.warn('toggle_chat', e); }
  }

  function wire() {
    // The desktop window is a regular full-app window now — no more
    // "X to hide" button in the topbar, and Esc no longer dismisses
    // the whole window. Modals/menus still handle their own Esc
    // independently.
    wireResizeHandles();
  }

  // Native window resize via the corner grips. Tauri 2's
  // `getCurrentWindow().startResizeDragging(direction)` hands off to
  // the WM's resize gesture so the user can drag the edge with a normal
  // pointer interaction — this is how borderless windows in apps like
  // Discord/Slack work.
  function wireResizeHandles() {
    const handles = document.querySelectorAll('.resize-handle');
    if (!handles.length) return;
    handles.forEach((h) => {
      const direction = h.classList.contains('resize-handle-br')
        ? 'SouthEast'
        : 'SouthWest';
      h.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        const win = tauri.window
          && (tauri.window.getCurrentWindow
              ? tauri.window.getCurrentWindow()
              : (tauri.window.getCurrent && tauri.window.getCurrent()));
        if (win && typeof win.startResizeDragging === 'function') {
          win.startResizeDragging(direction).catch((err) => {
            console.warn('startResizeDragging failed', err);
          });
        }
      });
    });
  }

  async function restoreInitial() {
    try {
      console.log('[dock] restoreInitial: querying settings');
      const settings = await invoke('get_settings');
      console.log('[dock] settings.sidebar_open=', settings && settings.sidebar_open);
      if (settings && settings.sidebar_open) {
        await show();
        console.log('[dock] show() resolved');
      }
    } catch (e) {
      console.warn('[dock] restoreInitial failed', e);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      wire();
      restoreInitial();
    }, { once: true });
  } else {
    wire();
    restoreInitial();
  }

  if (event && event.listen) {
    // Telemetry hook — useful for tests / future polish like a slide-in
    // animation triggered when the OS-level show happens.
    event.listen('popover-visible', () => {});
  }

  // Back-compat surface so `app.js` and existing tests still work.
  window.AgixtDock = {
    show,
    hide,
    toggle,
    setMode: (mode) => (mode === 'panel' ? show() : hide()),
    currentMode: () => 'panel',
  };
})();

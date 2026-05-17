/* Prompt Guidance bar.
 *
 * Vanilla-JS port of the web app's ResourceGuidanceCard
 * (web/components/ui/resource-guidance-card.tsx). The web app surfaces
 * per-page suggestions and clickable mini prompt-builders as a top
 * banner. The desktop app has a single always-visible agent chat with
 * content pages opening as side panes, so instead of a banner we pin a
 * compact suggestion bar to the bottom of the chat — directly above the
 * composer — and swap its contents to match whatever content page the
 * user currently has open (AgixtSidenav.getActiveView).
 *
 * Clicking a suggestion with no fields drops the prompt into the
 * composer and sends it. Clicking one with placeholders opens a small
 * builder modal to fill the fields first (mirrors the web's inline
 * prompt-builder), then sends (or hands off to the composer for edits).
 *
 * Data: prompt-guidance-data.js (window.AgixtPromptGuidanceData), keyed
 * by the web "resource" name, which matches the desktop extension/view
 * id for every ported page except where VIEW_ALIASES maps them.
 */
(function () {
  const DATA = window.AgixtPromptGuidanceData || {};
  // Desktop extension/view id -> web "resource" key when they differ.
  // The web "packages" page is the desktop "deployments" extension.
  const VIEW_ALIASES = { deployments: 'packages' };

  const COLLAPSE_KEY = 'agixt.desktop.promptGuidance.collapsed.v1';
  let containerEl = null;
  let currentView = null;
  let collapsed = loadCollapsed();
  let modalEl = null;

  function loadCollapsed() {
    try { return window.localStorage.getItem(COLLAPSE_KEY) === '1'; }
    catch (_) { return false; }
  }
  function saveCollapsed(v) {
    try { window.localStorage.setItem(COLLAPSE_KEY, v ? '1' : '0'); }
    catch (_) {}
  }

  function resourceKeyFor(viewId) {
    if (!viewId) return null;
    if (DATA[viewId]) return viewId;
    const alias = VIEW_ALIASES[viewId];
    if (alias && DATA[alias]) return alias;
    return null;
  }

  function activeViewId() {
    const sn = window.AgixtSidenav;
    if (sn && typeof sn.getActiveView === 'function') {
      const v = sn.getActiveView();
      if (v) return v;
    }
    const btn = document.querySelector('.sidenav-btn.is-active[data-view]');
    if (btn && btn.dataset.view) return btn.dataset.view;
    return 'chat';
  }

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  // ---- prompt composition / sending -----------------------------------

  function substitute(prompt, placeholders, values) {
    let out = prompt;
    (placeholders || []).forEach((ph) => {
      const raw = values[ph.id];
      const v = (raw != null && String(raw).trim())
        ? String(raw).trim()
        : (ph.label || ph.id);
      const safeId = String(ph.id).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const re = new RegExp('\\{\\{\\s*' + safeId + '\\s*\\}\\}', 'gi');
      out = out.replace(re, v);
    });
    return out;
  }

  // Reuse the composer's full send path (conversation creation, turn
  // context, attachments) by writing into the textarea and clicking the
  // existing send button — exactly what a user typing the prompt would
  // trigger. While the agent is generating the send button is hidden
  // (swapped for stop), so we leave the composed prompt staged instead
  // of silently dropping it.
  function putInComposer(text) {
    const input = document.getElementById('composer-input');
    if (!input) return false;
    input.value = text;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.focus();
    return true;
  }

  function sendPrompt(text) {
    if (!putInComposer(text)) return;
    const sendBtn = document.getElementById('btn-send');
    if (sendBtn && !sendBtn.hidden) {
      sendBtn.click();
    } else if (window.AgixtChat
        && typeof window.AgixtChat.setComposerStatus === 'function') {
      window.AgixtChat.setComposerStatus(
        'Prompt ready — press Enter to send once the agent is idle.', '');
    }
  }

  // ---- builder modal ---------------------------------------------------

  function onModalKey(e) {
    if (e.key === 'Escape') { e.stopPropagation(); closeModal(); }
  }

  function closeModal() {
    if (modalEl) {
      modalEl.classList.remove('open');
      modalEl.remove();
      modalEl = null;
    }
    document.removeEventListener('keydown', onModalKey, true);
  }

  function openBuilder(example) {
    closeModal();
    const phs = example.placeholders || [];
    const modal = el('div', 'modal prompt-guidance-modal');
    const card = el('div', 'modal-card');

    const header = el('div', 'modal-header');
    header.appendChild(el('h2', null, example.label || 'Prompt builder'));
    const close = el('button', 'modal-close');
    close.type = 'button';
    close.setAttribute('aria-label', 'Close');
    close.textContent = '✕';
    close.addEventListener('click', closeModal);
    header.appendChild(close);

    const body = el('div', 'modal-body');
    const inputs = {};
    phs.forEach((ph) => {
      const field = el('label', 'pg-field');
      field.appendChild(el('span', 'pg-field-label',
        (ph.label || ph.id) + (ph.required ? ' *' : '')));
      if (ph.description) {
        field.appendChild(el('span', 'pg-field-desc', ph.description));
      }
      let ctrl;
      if (ph.inputType === 'select'
          && Array.isArray(ph.options) && ph.options.length) {
        ctrl = el('select', 'pg-input');
        const blank = el('option', null,
          ph.required ? 'Select…' : '(optional)');
        blank.value = '';
        ctrl.appendChild(blank);
        ph.options.forEach((o) => {
          const op = el('option', null, o.label != null ? o.label : o.value);
          op.value = o.value;
          ctrl.appendChild(op);
        });
      } else if (ph.inputType === 'textarea') {
        ctrl = el('textarea', 'pg-input');
        ctrl.rows = 3;
      } else {
        ctrl = el('input', 'pg-input');
        ctrl.type = 'text';
      }
      ctrl.placeholder = ph.label || ph.id;
      inputs[ph.id] = ctrl;
      ctrl.addEventListener('input', validate);
      ctrl.addEventListener('change', validate);
      field.appendChild(ctrl);
      body.appendChild(field);
    });

    body.appendChild(el('span', 'pg-field-label', 'Preview'));
    const preview = el('div', 'pg-preview');
    body.appendChild(preview);

    const actions = el('div', 'pg-actions');
    const cancel = el('button', 'btn btn-secondary', 'Cancel');
    cancel.type = 'button';
    cancel.addEventListener('click', closeModal);
    const fillBtn = el('button', 'btn btn-secondary', 'Edit in composer');
    fillBtn.type = 'button';
    const sendBtn = el('button', 'btn btn-primary', 'Send to chat');
    sendBtn.type = 'button';
    actions.appendChild(cancel);
    actions.appendChild(fillBtn);
    actions.appendChild(sendBtn);
    body.appendChild(actions);

    function readValues() {
      const v = {};
      Object.keys(inputs).forEach((k) => { v[k] = inputs[k].value; });
      return v;
    }
    function validate() {
      const ok = phs.every((ph) => !ph.required
        || (inputs[ph.id] && inputs[ph.id].value.trim()));
      sendBtn.disabled = !ok;
      fillBtn.disabled = !ok;
      preview.textContent = substitute(example.prompt, phs, readValues());
      return ok;
    }
    fillBtn.addEventListener('click', () => {
      if (!validate()) return;
      putInComposer(substitute(example.prompt, phs, readValues()));
      closeModal();
    });
    sendBtn.addEventListener('click', () => {
      if (!validate()) return;
      sendPrompt(substitute(example.prompt, phs, readValues()));
      closeModal();
    });

    card.appendChild(header);
    card.appendChild(body);
    modal.appendChild(card);
    modal.addEventListener('mousedown', (e) => {
      if (e.target === modal) closeModal();
    });
    document.body.appendChild(modal);
    modalEl = modal;
    requestAnimationFrame(() => modal.classList.add('open'));
    document.addEventListener('keydown', onModalKey, true);
    validate();
    const firstId = phs.length ? phs[0].id : null;
    if (firstId && inputs[firstId]) inputs[firstId].focus();
  }

  function onChipClick(example) {
    if (example.placeholders && example.placeholders.length) {
      openBuilder(example);
    } else {
      sendPrompt(example.prompt);
    }
  }

  // ---- bar render ------------------------------------------------------

  function applyCollapsed() {
    if (!containerEl) return;
    containerEl.classList.toggle('is-collapsed', collapsed);
    const toggle = containerEl.querySelector('.pg-bar-toggle');
    if (toggle) {
      toggle.textContent = collapsed ? 'Show suggestions' : 'Hide';
      toggle.setAttribute('aria-label',
        collapsed ? 'Show suggestions' : 'Hide suggestions');
    }
  }

  function render() {
    if (!containerEl) return;
    const viewId = activeViewId();
    const key = resourceKeyFor(viewId);
    const data = key ? DATA[key] : null;
    if (!data || !Array.isArray(data.examples) || !data.examples.length) {
      containerEl.hidden = true;
      containerEl.innerHTML = '';
      containerEl.removeAttribute('data-key');
      currentView = viewId;
      return;
    }
    // Skip a rebuild when nothing relevant changed (the view-changed and
    // extension-context-changed events can fire repeatedly).
    if (currentView === viewId
        && containerEl.dataset.key === key
        && !containerEl.hidden) return;
    currentView = viewId;
    containerEl.dataset.key = key;
    containerEl.hidden = false;
    containerEl.innerHTML = '';

    const headerRow = el('div', 'pg-bar-header');
    const titleWrap = el('div', 'pg-bar-titlewrap');
    titleWrap.appendChild(el('span', 'pg-bar-spark', '✦'));
    titleWrap.appendChild(el('span', 'pg-bar-title',
      data.title || 'Try asking'));
    headerRow.appendChild(titleWrap);
    const toggle = el('button', 'pg-bar-toggle');
    toggle.type = 'button';
    toggle.addEventListener('click', () => {
      collapsed = !collapsed;
      saveCollapsed(collapsed);
      applyCollapsed();
    });
    headerRow.appendChild(toggle);
    containerEl.appendChild(headerRow);

    const chips = el('div', 'pg-chips');
    data.examples.forEach((ex) => {
      const chip = el('button', 'pg-chip');
      chip.type = 'button';
      chip.title = ex.label || ex.prompt;
      chip.appendChild(el('span', 'pg-chip-label',
        ex.label || ex.prompt.slice(0, 60)));
      if (ex.placeholders && ex.placeholders.length) {
        chip.appendChild(el('span', 'pg-chip-badge', '✎'));
      }
      chip.addEventListener('click', () => onChipClick(ex));
      chips.appendChild(chip);
    });
    containerEl.appendChild(chips);
    applyCollapsed();
  }

  function init() {
    containerEl = document.getElementById('prompt-guidance');
    if (!containerEl) return;
    render();
    window.addEventListener('agixt-view-changed', render);
    // A late extension manifest can add the currently-active extension
    // after the first render; its context-registration event lets the
    // bar pick up guidance for a page that wasn't known at nav time.
    window.addEventListener('agixt-extension-context-changed', render);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.AgixtPromptGuidance = { render, open: openBuilder };
})();

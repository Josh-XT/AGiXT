/* Training tab — persona editor, file/URL ingestion, learned sources list.
 * Vanilla JS port of web/components/settings/TrainingSection.tsx scoped to
 * the user-mode (single agent) flow.
 */
(function () {
  const api = window.AgixtApi;
  if (!api) {
    console.error('settings-training.js: AgixtApi missing');
    return;
  }

  let agentId = null;
  let agentName = null;
  let serverPersona = '';
  let sources = [];
  let sourceSearch = '';

  const $ = (id) => document.getElementById(id);

  function escape(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function setStatus(elId, text, cls) {
    const el = $(elId);
    if (!el) return;
    el.textContent = text || '';
    el.className = 'as-status' + (cls ? ' ' + cls : '');
  }

  function getSourceIcon(source) {
    if (typeof source !== 'string') return { icon: '📄', type: 'Document' };
    if (source.startsWith('From prior conversation on')) return { icon: '🤖', type: 'Memory' };
    if (/^https?:\/\//.test(source)) {
      try {
        const u = new URL(source);
        return { icon: '🔗', type: 'Website', display: u.hostname + (u.pathname !== '/' ? u.pathname : '') };
      } catch (_) { return { icon: '🔗', type: 'URL' }; }
    }
    const ext = (source.split('.').pop() || '').toLowerCase();
    const map = {
      pdf: { icon: '📕', type: 'PDF' },
      doc: { icon: '📘', type: 'Word' },
      docx: { icon: '📘', type: 'Word' },
      txt: { icon: '📄', type: 'Text' },
      md: { icon: '📝', type: 'Markdown' },
      csv: { icon: '📊', type: 'CSV' },
      json: { icon: '🧾', type: 'JSON' },
      xlsx: { icon: '📊', type: 'Excel' },
      xls: { icon: '📊', type: 'Excel' },
    };
    return map[ext] || { icon: '📄', type: 'Document' };
  }

  function renderSources() {
    const container = $('train-sources');
    const empty = $('train-sources-empty');
    const search = $('train-source-search');
    if (!container) return;

    const q = (sourceSearch || '').trim().toLowerCase();
    const filtered = q ? sources.filter((s) => (s || '').toLowerCase().includes(q)) : sources;

    if (search) search.hidden = sources.length <= 5;

    if (sources.length === 0) {
      container.innerHTML = '<div class="as-empty" id="train-sources-empty">No training sources yet.</div>';
      return;
    }
    if (filtered.length === 0) {
      container.innerHTML = `<div class="as-empty">No sources match "${escape(sourceSearch)}".</div>`;
      return;
    }
    container.innerHTML = filtered.map((src) => {
      const meta = getSourceIcon(src);
      const display = meta.display || src;
      const isUrl = /^https?:\/\//.test(src);
      return `
        <div class="as-source" data-source="${escape(src)}">
          <div class="as-source-icon">${meta.icon}</div>
          <div class="as-source-meta">
            <div class="as-source-name">${escape(display)}</div>
            <div class="as-source-type">${escape(meta.type)}</div>
          </div>
          <div class="as-source-actions">
            ${isUrl ? `<button class="btn-icon-danger src-open" type="button" title="Open in browser">↗</button>` : ''}
            <button class="btn-icon-danger src-delete" type="button" title="Delete source">✕</button>
          </div>
        </div>
      `;
    }).join('');

    container.querySelectorAll('.as-source').forEach((row) => {
      const src = row.getAttribute('data-source');
      const openBtn = row.querySelector('.src-open');
      const delBtn = row.querySelector('.src-delete');
      if (openBtn) {
        openBtn.addEventListener('click', () => {
          if (window.__TAURI__ && window.__TAURI__.opener && window.__TAURI__.opener.openUrl) {
            window.__TAURI__.opener.openUrl(src);
          } else {
            window.open(src, '_blank', 'noopener');
          }
        });
      }
      if (delBtn) {
        delBtn.addEventListener('click', async () => {
          if (!confirm(`Delete this training source?\n\n${src}`)) return;
          delBtn.disabled = true;
          try {
            await api.deleteSource(agentId, src);
            sources = sources.filter((s) => s !== src);
            renderSources();
            window.AgentSettings.toast('Source deleted.', 'success');
          } catch (e) {
            delBtn.disabled = false;
            window.AgentSettings.toast('Delete failed: ' + (e.message || e), 'error');
          }
        });
      }
    });
  }

  // ----- Persona ----------------------------------------------------------

  function showPersonaActions(modified) {
    const cancel = $('train-persona-cancel');
    const save = $('train-persona-save');
    if (cancel) cancel.hidden = !modified;
    if (save) save.hidden = !modified;
  }

  function bindPersona() {
    const ta = $('train-persona');
    const cancel = $('train-persona-cancel');
    const save = $('train-persona-save');
    if (!ta) return;
    ta.addEventListener('input', () => {
      showPersonaActions(ta.value !== serverPersona);
    });
    if (cancel) {
      cancel.addEventListener('click', () => {
        ta.value = serverPersona;
        showPersonaActions(false);
      });
    }
    if (save) {
      save.addEventListener('click', async () => {
        save.disabled = true;
        save.textContent = 'Saving…';
        try {
          await api.setPersona(agentId, ta.value);
          serverPersona = ta.value;
          showPersonaActions(false);
          window.AgentSettings.toast('Mandatory context saved.', 'success');
        } catch (e) {
          window.AgentSettings.toast('Save failed: ' + (e.message || e), 'error');
        } finally {
          save.disabled = false;
          save.textContent = 'Save';
        }
      });
    }
  }

  // ----- File upload ------------------------------------------------------

  function bindFileUpload() {
    const pick = $('train-file-pick');
    const input = $('train-file');
    const progress = $('train-file-progress');
    if (!pick || !input) return;

    pick.addEventListener('click', () => input.click());

    input.addEventListener('change', async () => {
      const file = input.files && input.files[0];
      if (!file) return;
      pick.disabled = true;
      pick.textContent = 'Uploading…';
      if (progress) {
        progress.hidden = false;
        progress.value = 0;
      }
      setStatus('train-file-status', `Reading ${file.name}…`);
      try {
        const base64 = await api.readFileAsBase64(file, (pct) => {
          if (progress) progress.value = pct;
        });
        setStatus('train-file-status', `Uploading ${file.name}…`);
        await api.learnFile(agentId, file.name, base64);
        setStatus('train-file-status', `${file.name} uploaded.`, 'success');
        window.AgentSettings.toast(`Learned "${file.name}".`, 'success');
        await reloadSources();
      } catch (e) {
        setStatus('train-file-status', 'Upload failed: ' + (e.message || e), 'error');
        window.AgentSettings.toast('Upload failed: ' + (e.message || e), 'error');
      } finally {
        pick.disabled = false;
        pick.textContent = 'Upload Document';
        input.value = '';
        if (progress) progress.hidden = true;
      }
    });
  }

  // ----- URL learn --------------------------------------------------------

  function bindUrlLearn() {
    const urlInput = $('train-url');
    const goBtn = $('train-url-go');
    if (!urlInput || !goBtn) return;

    goBtn.addEventListener('click', async () => {
      const url = (urlInput.value || '').trim();
      if (!url) return;
      try { new URL(url); } catch (_) {
        setStatus('train-url-status', 'Enter a valid URL.', 'error');
        return;
      }
      goBtn.disabled = true;
      goBtn.textContent = 'Learning…';
      setStatus('train-url-status', 'Fetching and indexing the page…');
      try {
        await api.learnUrl(agentId, url);
        setStatus('train-url-status', 'Learned.', 'success');
        urlInput.value = '';
        window.AgentSettings.toast('URL content learned.', 'success');
        await reloadSources();
      } catch (e) {
        setStatus('train-url-status', 'Failed: ' + (e.message || e), 'error');
      } finally {
        goBtn.disabled = false;
        goBtn.textContent = 'Learn';
      }
    });

    urlInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); goBtn.click(); }
    });
  }

  function bindSourceSearch() {
    const search = $('train-source-search');
    if (!search) return;
    search.addEventListener('input', () => {
      sourceSearch = search.value || '';
      renderSources();
    });
  }

  async function reloadSources() {
    sources = await api.listTrainingSources(agentId);
    renderSources();
  }

  async function load() {
    if (!agentId) return;
    const ta = $('train-persona');
    if (ta) ta.value = '';
    setStatus('train-file-status', '');
    setStatus('train-url-status', '');
    try {
      const [persona, srcs] = await Promise.all([
        api.getPersona(agentId),
        api.listTrainingSources(agentId),
      ]);
      serverPersona = persona || '';
      sources = srcs || [];
      if (ta) ta.value = serverPersona;
      showPersonaActions(false);
      renderSources();
    } catch (e) {
      window.AgentSettings.toast('Failed to load training data: ' + (e.message || e), 'error');
    }
  }

  function init(opts) {
    agentId = opts.agentId;
    agentName = opts.agentName || null;
    bindPersona();
    bindFileUpload();
    bindUrlLearn();
    bindSourceSearch();
    return load();
  }

  window.AgentSettingsTraining = {
    init,
    reload: load,
    setAgent(id, name) { agentId = id; agentName = name || null; },
  };
})();

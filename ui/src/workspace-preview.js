/* File preview renderers — port of web/.../FilePreview.tsx
 *
 * Given a Blob and filename, renders into a target HTMLElement.
 * Mirrors the React component 1:1: image/video/audio/pdf/csv/docx/xlsx.
 *
 * Depends on the global libraries vendored under src/vendor:
 *   - Papa  (papaparse.min.js)
 *   - mammoth (mammoth.browser.min.js)
 *   - XLSX  (xlsx.full.min.js)
 *
 * Exposes a single window.AgixtWorkspacePreview object.
 */
(function () {
  const IMAGE = new Set(['png', 'jpg', 'jpeg', 'gif', 'bmp', 'ico', 'svg', 'webp', 'avif', 'tiff', 'tif']);
  const VIDEO = new Set(['mp4', 'webm', 'ogg', 'mov']);
  const AUDIO = new Set(['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a', 'webm']);
  const PDF = new Set(['pdf']);
  const CSV = new Set(['csv', 'tsv']);
  const DOCX = new Set(['docx']);
  const XLSX_EXT = new Set(['xlsx', 'xls']);

  function getExt(name) {
    const lower = String(name || '').toLowerCase();
    const dot = lower.lastIndexOf('.');
    return dot > 0 ? lower.slice(dot + 1) : '';
  }

  function getPreviewKind(name) {
    const ext = getExt(name);
    if (IMAGE.has(ext)) return 'image';
    if (VIDEO.has(ext)) return 'video';
    if (AUDIO.has(ext)) return 'audio';
    if (PDF.has(ext)) return 'pdf';
    if (CSV.has(ext)) return 'csv';
    if (DOCX.has(ext)) return 'docx';
    if (XLSX_EXT.has(ext)) return 'xlsx';
    return null;
  }

  function isPreviewableMedia(name) {
    return getPreviewKind(name) !== null;
  }

  // --- Helpers --------------------------------------------------------

  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }

  function loading(el) {
    clear(el);
    const wrap = document.createElement('div');
    wrap.className = 'wkfp-loading';
    wrap.innerHTML = '<div class="wkfp-spinner" aria-hidden="true"></div>';
    el.appendChild(wrap);
  }

  function errorMsg(el, msg) {
    clear(el);
    const wrap = document.createElement('div');
    wrap.className = 'wkfp-error';
    wrap.innerHTML = `
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
      <p></p>`;
    wrap.querySelector('p').textContent = msg;
    el.appendChild(wrap);
  }

  function normalizeWorkspacePath(path) {
    const parts = String(path || '')
      .replace(/\\/g, '/')
      .split('/');
    const out = [];
    for (const raw of parts) {
      const part = raw.trim();
      if (!part || part === '.') continue;
      if (part === '..') out.pop();
      else out.push(part);
    }
    return out.join('/');
  }

  function workspaceParentPath(path) {
    const parts = normalizeWorkspacePath(path).split('/').filter(Boolean);
    parts.pop();
    return parts.join('/');
  }

  function isExternalPreviewUrl(value) {
    const url = String(value || '').trim();
    return !url || url.startsWith('#') || url.startsWith('//') || /^[a-z][a-z0-9+.-]*:/i.test(url);
  }

  function workspaceAssetCandidates(rawUrl, currentFilePath) {
    const value = String(rawUrl || '').trim();
    if (isExternalPreviewUrl(value)) return [];
    const clean = value.replace(/[?#].*$/, '');
    if (!clean || isExternalPreviewUrl(clean)) return [];
    const candidates = [];
    const push = (path) => {
      const normalized = normalizeWorkspacePath(path);
      if (normalized && !candidates.includes(normalized)) candidates.push(normalized);
    };
    if (clean.startsWith('/')) {
      push(clean);
    } else {
      const basePath = workspaceParentPath(currentFilePath);
      push(`${basePath}/${clean}`);
      push(clean);
    }
    return candidates;
  }

  function canResolveWorkspaceAssets(opts) {
    return opts && opts.api && typeof opts.api.downloadFile === 'function'
      && opts.cfg && opts.conversationId && opts.filePath
      && window.URL && typeof window.URL.createObjectURL === 'function';
  }

  function revokeObjectUrls(urls) {
    for (const url of urls || []) {
      try { window.URL.revokeObjectURL(url); } catch (_) {}
    }
  }

  async function hydrateHtmlWorkspaceAssets(htmlString, opts, objectUrls) {
    if (!canResolveWorkspaceAssets(opts)) return htmlString;
    const parser = new DOMParser();
    const doc = parser.parseFromString(htmlString, 'text/html');
    const cache = new Map();
    const resourceAttrs = [
      ['img[src]', 'src'],
      ['video[src]', 'src'],
      ['video[poster]', 'poster'],
      ['audio[src]', 'src'],
      ['source[src]', 'src'],
      ['track[src]', 'src'],
      ['link[href]', 'href'],
      ['script[src]', 'src'],
    ];

    async function objectUrlFor(rawUrl) {
      const candidates = workspaceAssetCandidates(rawUrl, opts.filePath);
      for (const candidate of candidates) {
        if (cache.has(candidate)) return cache.get(candidate);
        try {
          const result = await opts.api.downloadFile(opts.cfg, opts.conversationId, candidate);
          if (result && result.blob) {
            const objectUrl = window.URL.createObjectURL(result.blob);
            objectUrls.push(objectUrl);
            cache.set(candidate, objectUrl);
            return objectUrl;
          }
        } catch (_) { /* try the next candidate */ }
      }
      return null;
    }

    const rewrites = [];
    for (const [selector, attr] of resourceAttrs) {
      doc.querySelectorAll(selector).forEach((node) => {
        const raw = node.getAttribute(attr);
        rewrites.push(objectUrlFor(raw).then((url) => {
          if (url) node.setAttribute(attr, url);
        }));
      });
    }
    await Promise.all(rewrites);
    return `<!doctype html>\n${doc.documentElement.outerHTML}`;
  }

  function fillUnknown(el, onDownload) {
    clear(el);
    const wrap = document.createElement('div');
    wrap.className = 'wkfp-unknown';
    wrap.innerHTML = `
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
      <p>Cannot preview this file type</p>
      <button type="button" class="wkfp-btn">Download</button>`;
    wrap.querySelector('button').addEventListener('click', () => onDownload && onDownload());
    el.appendChild(wrap);
  }

  // --- Renderers ------------------------------------------------------

  function renderImage(el, blob, filename) {
    clear(el);
    const url = URL.createObjectURL(blob);
    const wrap = document.createElement('div');
    wrap.className = 'wkfp-image-wrap';
    const img = document.createElement('img');
    img.src = url;
    img.alt = filename;
    img.draggable = false;
    img.addEventListener('load', () => { /* no-op */ });
    wrap.appendChild(img);
    el.appendChild(wrap);
    el._wkfpRevoke = () => URL.revokeObjectURL(url);
  }

  function renderVideo(el, blob, filename) {
    clear(el);
    const url = URL.createObjectURL(blob);
    const wrap = document.createElement('div');
    wrap.className = 'wkfp-video-wrap';
    const v = document.createElement('video');
    v.src = url;
    v.controls = true;
    v.title = filename;
    wrap.appendChild(v);
    el.appendChild(wrap);
    el._wkfpRevoke = () => URL.revokeObjectURL(url);
  }

  function renderAudio(el, blob, filename) {
    clear(el);
    const url = URL.createObjectURL(blob);
    const wrap = document.createElement('div');
    wrap.className = 'wkfp-audio-wrap';
    const label = document.createElement('p');
    label.className = 'wkfp-audio-name';
    label.textContent = filename;
    const a = document.createElement('audio');
    a.src = url;
    a.controls = true;
    wrap.appendChild(label);
    wrap.appendChild(a);
    el.appendChild(wrap);
    el._wkfpRevoke = () => URL.revokeObjectURL(url);
  }

  function renderPdf(el, blob) {
    clear(el);
    const url = URL.createObjectURL(blob);
    const iframe = document.createElement('iframe');
    iframe.src = url;
    iframe.title = 'PDF Preview';
    iframe.className = 'wkfp-pdf';
    el.appendChild(iframe);
    el._wkfpRevoke = () => URL.revokeObjectURL(url);
  }

  // Render a raw HTML string as a live document inside a sandboxed iframe.
  // Mirrors the safe pattern from web's CodeBlock.tsx: srcdoc + sandbox,
  // with a small viewport-fix wrap so full-page layouts size correctly.
  // Isolation is via the iframe sandbox only (no DOM injection into the host).
  function renderHtmlDoc(el, htmlString, opts) {
    destroy(el);
    const src = String(htmlString || '');
    const wrapped = src
      .replace(/<style>/i, '<style>\n  html, body { height: 100%; margin: 0; padding: 0; }\n')
      .replace(/height:\s*100vh/gi, 'height: 100%');
    const token = {};
    const objectUrls = [];
    el._wkfpHtmlToken = token;

    const paint = (html) => {
      if (el._wkfpHtmlToken !== token) {
        revokeObjectUrls(objectUrls);
        return;
      }
      clear(el);
      renderHtmlFrame(el, html, objectUrls);
    };

    hydrateHtmlWorkspaceAssets(wrapped, opts || {}, objectUrls)
      .then((html) => paint(html))
      .catch(() => paint(wrapped));
  }

  function renderHtmlFrame(el, htmlString, objectUrls) {
    const wrap = document.createElement('div');
    wrap.className = 'wkfp-html-wrap';
    const iframe = document.createElement('iframe');
    iframe.className = 'wkfp-html';
    iframe.title = 'HTML Preview';
    // allow-scripts so interactive pages work; allow-same-origin so the
    // page can access its own document (and we can read it for auto-fit).
    // No allow-forms / allow-popups / allow-top-navigation: a previewed
    // file cannot navigate the app or submit anywhere.
    iframe.setAttribute('sandbox', 'allow-scripts allow-same-origin');
    iframe.setAttribute('referrerpolicy', 'no-referrer');
    iframe.srcdoc = htmlString;
    wrap.appendChild(iframe);
    el.appendChild(wrap);
    el._wkfpRevoke = () => revokeObjectUrls(objectUrls);
  }

  function renderTable(el, headers, rows, footer) {
    clear(el);
    const scroll = document.createElement('div');
    scroll.className = 'wkfp-table-scroll';
    const wrap = document.createElement('div');
    wrap.className = 'wkfp-table-wrap';
    const table = document.createElement('table');
    table.className = 'wkfp-table';
    const thead = document.createElement('thead');
    const trh = document.createElement('tr');
    for (const h of headers) {
      const th = document.createElement('th');
      th.textContent = String(h ?? '');
      trh.appendChild(th);
    }
    thead.appendChild(trh);
    table.appendChild(thead);
    const tbody = document.createElement('tbody');
    for (const row of rows) {
      const tr = document.createElement('tr');
      for (const cell of row) {
        const td = document.createElement('td');
        td.textContent = String(cell ?? '');
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    scroll.appendChild(wrap);
    if (footer) {
      const f = document.createElement('p');
      f.className = 'wkfp-table-footer';
      f.textContent = footer;
      scroll.appendChild(f);
    }
    el.appendChild(scroll);
  }

  function renderCsv(el, blob, filename) {
    loading(el);
    const delim = filename.toLowerCase().endsWith('.tsv') ? '\t' : ',';
    blob.text().then((text) => {
      try {
        const Papa = window.Papa;
        if (!Papa) throw new Error('papaparse not loaded');
        const result = Papa.parse(text, { delimiter: delim, skipEmptyLines: true });
        const data = result.data || [];
        const headers = data[0] || [];
        const rows = data.slice(1);
        renderTable(el, headers, rows, `${rows.length.toLocaleString()} rows × ${headers.length} columns`);
      } catch (err) {
        errorMsg(el, 'Failed to parse CSV');
      }
    }).catch(() => errorMsg(el, 'Failed to read file'));
  }

  function renderDocx(el, blob) {
    loading(el);
    blob.arrayBuffer().then((ab) => {
      const mammoth = window.mammoth;
      if (!mammoth) { errorMsg(el, 'mammoth library missing'); return; }
      mammoth.convertToHtml({ arrayBuffer: ab }).then((result) => {
        clear(el);
        const wrap = document.createElement('div');
        wrap.className = 'wkfp-docx';
        wrap.innerHTML = result.value || '';
        el.appendChild(wrap);
      }).catch(() => errorMsg(el, 'Failed to render DOCX'));
    }).catch(() => errorMsg(el, 'Failed to read file'));
  }

  function renderXlsx(el, blob) {
    loading(el);
    blob.arrayBuffer().then((ab) => {
      try {
        const XLSX = window.XLSX;
        if (!XLSX) throw new Error('xlsx library missing');
        const workbook = XLSX.read(ab, { type: 'array' });
        const sheets = workbook.SheetNames.map((name) => {
          const sheet = workbook.Sheets[name];
          const data = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: '' });
          return { name, data };
        });
        if (!sheets.length) { errorMsg(el, 'No sheet data'); return; }

        clear(el);
        const root = document.createElement('div');
        root.className = 'wkfp-xlsx';

        // Sheet tabs
        let active = 0;
        const tabs = document.createElement('div');
        tabs.className = 'wkfp-xlsx-tabs';
        if (sheets.length > 1) {
          sheets.forEach((s, i) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'wkfp-xlsx-tab';
            btn.textContent = s.name;
            if (i === 0) btn.classList.add('active');
            btn.addEventListener('click', () => {
              active = i;
              tabs.querySelectorAll('.wkfp-xlsx-tab').forEach((b, j) => b.classList.toggle('active', j === i));
              renderActive();
            });
            tabs.appendChild(btn);
          });
          root.appendChild(tabs);
        }

        const body = document.createElement('div');
        body.className = 'wkfp-xlsx-body';
        root.appendChild(body);

        function renderActive() {
          const cur = sheets[active];
          const headers = cur.data[0] || [];
          const rows = cur.data.slice(1);
          renderTable(body, headers, rows,
            `${rows.length.toLocaleString()} rows × ${headers.length} columns${sheets.length > 1 ? ` · Sheet: ${cur.name}` : ''}`);
        }
        el.appendChild(root);
        renderActive();
      } catch (err) {
        errorMsg(el, 'Failed to parse spreadsheet');
      }
    }).catch(() => errorMsg(el, 'Failed to read file'));
  }

  /** Render the appropriate preview into `el`. Call destroy(el) before
   *  swapping content to revoke any object URLs. */
  function render(el, blob, filename, onDownload) {
    destroy(el);
    const kind = getPreviewKind(filename);
    if (!kind) return fillUnknown(el, onDownload);
    switch (kind) {
      case 'image': return renderImage(el, blob, filename);
      case 'video': return renderVideo(el, blob, filename);
      case 'audio': return renderAudio(el, blob, filename);
      case 'pdf':   return renderPdf(el, blob);
      case 'csv':   return renderCsv(el, blob, filename);
      case 'docx':  return renderDocx(el, blob);
      case 'xlsx':  return renderXlsx(el, blob);
    }
  }

  function destroy(el) {
    if (!el) return;
    el._wkfpHtmlToken = null;
    if (typeof el._wkfpRevoke === 'function') {
      try { el._wkfpRevoke(); } catch {}
      el._wkfpRevoke = null;
    }
  }

  // --- Media text extraction / rebuild for AI editing -----------------
  // Mirrors extractTextFromBlob / rebuildBlobFromText from WorkspaceEditor.tsx

  async function extractTextFromBlob(blob, filename) {
    const kind = getPreviewKind(filename);
    try {
      if (kind === 'csv') return await blob.text();
      if (kind === 'xlsx') {
        const XLSX = window.XLSX;
        if (!XLSX) return null;
        const ab = await blob.arrayBuffer();
        const wb = XLSX.read(ab, { type: 'array' });
        return wb.SheetNames.map((name) => {
          const csv = XLSX.utils.sheet_to_csv(wb.Sheets[name]);
          return wb.SheetNames.length > 1 ? `--- Sheet: ${name} ---\n${csv}` : csv;
        }).join('\n\n');
      }
      if (kind === 'docx') {
        const mammoth = window.mammoth;
        if (!mammoth) return null;
        const ab = await blob.arrayBuffer();
        const result = await mammoth.extractRawText({ arrayBuffer: ab });
        return result.value;
      }
    } catch (e) {
      console.error('extractTextFromBlob:', e);
    }
    return null;
  }

  function csvToAoa(csv) {
    return csv.split('\n').filter((l) => l.length > 0).map((line) => {
      const fields = [];
      let current = '', inQuotes = false;
      for (let i = 0; i < line.length; i++) {
        const ch = line[i];
        if (inQuotes) {
          if (ch === '"' && line[i + 1] === '"') { current += '"'; i++; }
          else if (ch === '"') { inQuotes = false; }
          else { current += ch; }
        } else {
          if (ch === '"') inQuotes = true;
          else if (ch === ',') { fields.push(current); current = ''; }
          else current += ch;
        }
      }
      fields.push(current);
      return fields;
    });
  }

  async function rebuildBlobFromText(text, filename) {
    const kind = getPreviewKind(filename);
    try {
      if (kind === 'csv') return new Blob([text], { type: 'text/csv' });
      if (kind === 'xlsx') {
        const XLSX = window.XLSX;
        if (!XLSX) return null;
        const sections = text.split(/^--- Sheet: (.+?) ---$/m).filter(Boolean);
        const wb = XLSX.utils.book_new();
        if (sections.length >= 2) {
          for (let i = 0; i < sections.length; i += 2) {
            const name = sections[i].trim();
            const csv = (sections[i + 1] || '').trim();
            const ws = XLSX.utils.aoa_to_sheet(csvToAoa(csv));
            XLSX.utils.book_append_sheet(wb, ws, name);
          }
        } else {
          const ws = XLSX.utils.aoa_to_sheet(csvToAoa(text.trim()));
          XLSX.utils.book_append_sheet(wb, ws, 'Sheet1');
        }
        const out = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
        return new Blob([out], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
      }
    } catch (e) {
      console.error('rebuildBlobFromText:', e);
    }
    return null;
  }

  window.AgixtWorkspacePreview = {
    getPreviewKind,
    isPreviewableMedia,
    render,
    renderHtmlDoc,
    destroy,
    extractTextFromBlob,
    rebuildBlobFromText,
  };
})();

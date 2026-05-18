/* AGiXT conversation workspace UI — vanilla port of the NextJS web
 * client's components/conversation/workspace/{WorkspaceView,WorkspaceEditor,
 * WorkspaceManager,FilePreview,CodeEditor,useWorkspaceModels}.tsx.
 *
 * Same UX 1:1:
 *   • Tree sidebar (folders first, alphabetical, click to expand,
 *     hover to reveal download/delete, refresh / upload / new folder
 *     in the sidebar header).
 *   • Editor pane with toolbar: Back · file name (with unsaved marker) ·
 *     Edit/Split/Preview toggle · Revert · Download · Save (Ctrl+S).
 *   • Monaco code editor with the project's xt-dark / xt-light themes,
 *     bounded workspace model registry for cross-file go-to-definition and
 *     find-references.
 *   • Markdown / HTML files render to the preview pane via the existing
 *     AgixtMarkdown helper. Other files render as a fenced code block.
 *   • Media files (image/video/audio/pdf/csv/docx/xlsx) use the
 *     AgixtWorkspacePreview renderers.
 *   • AI Edit bar at the bottom — pipes the file contents through
 *     /v1/chat/completions and applies the response.
 *   • Toasts for user feedback (uses AgixtToast helper).
 *
 * Boots the AMD `vs/loader.js` from src/vendor/monaco/vs lazily on first
 * open so the 16 MB Monaco bundle isn't paid up-front.
 *
 * Public surface: window.AgixtWorkspace = { open, close, toggle, isOpen }.
 */
(function () {
  const ROOT_PATH = '/';

  const BINARY_EXTENSIONS = new Set([
    '.zip','.tar','.gz','.bz2','.7z','.rar','.xz','.zst',
    '.doc','.ppt','.pptx',
    '.exe','.dll','.so','.dylib','.bin','.o','.a','.lib',
    '.wasm','.pyc','.class','.jar',
    '.ttf','.otf','.woff','.woff2','.eot',
    '.sqlite','.db','.sqlite3',
  ]);

  // Mapped from WorkspaceEditor.tsx LANGUAGE_MAP / FILENAME_LANGUAGE_MAP.
  const LANGUAGE_MAP = {
    js:'javascript',jsx:'javascript',ts:'typescript',tsx:'typescript',
    py:'python',md:'markdown',json:'json',xml:'xml',html:'html',htm:'html',
    css:'css',scss:'scss',yaml:'yaml',yml:'yaml',sh:'bash',bash:'bash',
    sql:'sql',graphql:'graphql',toml:'toml',ini:'ini',conf:'ini',config:'ini',
    rs:'rust',go:'go',java:'java',cpp:'cpp',c:'c',h:'c',hpp:'cpp',
    rb:'ruby',php:'php',swift:'swift',kt:'kotlin',scala:'scala',
    csv:'csv',log:'text',txt:'text',env:'bash',ln:'text',lock:'text',
    cfg:'ini',properties:'ini',prisma:'graphql',vue:'html',svelte:'html',
    tf:'text',hcl:'text',proto:'text',makefile:'bash',cmake:'text',gradle:'text',
    ps1:'bash',bat:'bash',cmd:'bash',fish:'bash',zsh:'bash',
    r:'text',m:'text',dart:'text',lua:'text',zig:'text',nim:'text',
    ex:'text',exs:'text',erl:'text',hrl:'text',hs:'text',ml:'text',
    v:'text',vhdl:'text',asm:'text',s:'text',
  };
  const FILENAME_LANGUAGE_MAP = {
    dockerfile:'bash',makefile:'bash',gemfile:'ruby',rakefile:'ruby',
    procfile:'bash',vagrantfile:'ruby',jenkinsfile:'text',cmakelists:'text',
  };

  function getFileLanguage(filename) {
    const lower = String(filename).toLowerCase();
    const baseName = lower.split('.')[0];
    if (FILENAME_LANGUAGE_MAP[baseName] && !lower.includes('.')) {
      return FILENAME_LANGUAGE_MAP[baseName];
    }
    if (lower.startsWith('.') && !lower.slice(1).includes('.')) return 'text';
    const ext = lower.split('.').pop() || '';
    return LANGUAGE_MAP[ext] || 'text';
  }

  function isMarkdownLike(name) {
    const ext = String(name).toLowerCase().split('.').pop() || '';
    return ext === 'md' || ext === 'mdx';
  }
  function isHtmlFile(name) {
    const ext = String(name).toLowerCase().split('.').pop() || '';
    return ext === 'html' || ext === 'htm';
  }
  function isPreviewable(name) {
    return isMarkdownLike(name) || isHtmlFile(name);
  }

  function isViewableFile(name) {
    const lower = String(name).toLowerCase();
    const dot = lower.lastIndexOf('.');
    if (dot <= 0) return true; // extensionless (Dockerfile, Makefile)
    const ext = lower.slice(dot);
    if (window.AgixtWorkspacePreview && window.AgixtWorkspacePreview.isPreviewableMedia(lower)) return true;
    return !BINARY_EXTENSIONS.has(ext);
  }

  // --- Toast helper ---------------------------------------------------
  // Falls back to a self-contained DOM toast if no global toaster is
  // installed. Mirrors the sonner toasts in the web client.
  let toastHostEl = null;
  function ensureToastHost() {
    if (toastHostEl && document.body.contains(toastHostEl)) return toastHostEl;
    toastHostEl = document.createElement('div');
    toastHostEl.className = 'wk-toast-host';
    toastHostEl.style.cssText = 'position:fixed;bottom:18px;right:18px;z-index:9999;display:flex;flex-direction:column;gap:6px;pointer-events:none;';
    document.body.appendChild(toastHostEl);
    return toastHostEl;
  }
  function toast(msg, level) {
    if (window.AgixtToast && typeof window.AgixtToast.show === 'function') {
      return window.AgixtToast.show(msg, level || 'info');
    }
    const host = ensureToastHost();
    const t = document.createElement('div');
    const isErr = level === 'error';
    const isOk = level === 'success';
    t.style.cssText = `pointer-events:auto;background:${isErr ? '#7f1d1d' : isOk ? '#14532d' : '#1f2937'};color:#fff;border-radius:6px;padding:8px 12px;font-size:12px;box-shadow:0 6px 24px rgba(0,0,0,0.35);max-width:340px;opacity:0;transform:translateY(6px);transition:opacity .15s,transform .15s;`;
    t.textContent = String(msg);
    host.appendChild(t);
    requestAnimationFrame(() => { t.style.opacity = '1'; t.style.transform = 'translateY(0)'; });
    setTimeout(() => {
      t.style.opacity = '0'; t.style.transform = 'translateY(6px)';
      setTimeout(() => t.remove(), 200);
    }, isErr ? 5000 : 2800);
  }

  // --- Path helpers ---------------------------------------------------
  function normalizePath(p) {
    if (!p || p === ROOT_PATH) return ROOT_PATH;
    const segs = String(p).split('/').map((s) => s.trim()).filter(Boolean);
    return segs.length ? `${ROOT_PATH}${segs.join('/')}` : ROOT_PATH;
  }

  // --- Tree builder ---------------------------------------------------
  function buildTree(items) {
    const sorted = [...(items || [])].sort((a, b) => {
      if (a.type !== b.type) return a.type === 'folder' ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    function processItem(item, depth) {
      const node = {
        id: item.id || item.path,
        name: item.name,
        type: item.type,
        path: item.path,
        size: item.size,
        modified: item.modified,
        children: [],
        depth,
      };
      if (item.type === 'folder' && item.children && item.children.length) {
        const sortedChildren = [...item.children].sort((a, b) => {
          if (a.type !== b.type) return a.type === 'folder' ? -1 : 1;
          return a.name.localeCompare(b.name);
        });
        for (const c of sortedChildren) node.children.push(processItem(c, depth + 1));
      }
      return node;
    }
    return sorted.map((item) => processItem(item, 0));
  }

  function findFileInTree(nodes, fileNameOrPath) {
    const lower = String(fileNameOrPath).toLowerCase();
    function search(list, ancestors) {
      for (const node of list) {
        if (node.type === 'file' && (node.name.toLowerCase() === lower || node.path.toLowerCase() === lower)) {
          return { node, folderPaths: ancestors };
        }
        if (node.type === 'folder' && node.children.length) {
          const r = search(node.children, [...ancestors, node.path]);
          if (r) return r;
        }
      }
      return null;
    }
    return search(nodes, []);
  }

  // --- Monaco loader (AMD) -------------------------------------------
  let monacoPromise = null;
  function loadMonaco() {
    if (monacoPromise) return monacoPromise;
    monacoPromise = new Promise((resolve, reject) => {
      // The vendored AMD loader sets window.require / window.requirejs.
      const script = document.createElement('script');
      script.src = 'vendor/monaco/vs/loader.js';
      script.onload = () => {
        try {
          // eslint-disable-next-line no-undef
          require.config({ paths: { vs: 'vendor/monaco/vs' } });
          // Monaco workers run from blob: URLs; tell it where to find the
          // worker bootstrap so it can wrap them with the right base.
          window.MonacoEnvironment = {
            getWorkerUrl: function (_moduleId, label) {
              const blob = new Blob([
                `self.MonacoEnvironment = { baseUrl: '${location.origin}/vendor/monaco/' };
                 importScripts('${location.origin}/vendor/monaco/vs/base/worker/workerMain.js');`
              ], { type: 'application/javascript' });
              return URL.createObjectURL(blob);
            },
          };
          // eslint-disable-next-line no-undef
          require(['vs/editor/editor.main'], () => {
            resolve(window.monaco);
          });
        } catch (err) {
          reject(err);
        }
      };
      script.onerror = (e) => reject(new Error('Failed to load monaco loader.js'));
      document.head.appendChild(script);
    });
    return monacoPromise;
  }

  // --- Theme definitions (xt-dark, xt-light) -------------------------
  let themesDefined = false;
  function defineThemes(monaco) {
    function hslToHex(h, s, l) {
      s /= 100; l /= 100;
      const a = s * Math.min(l, 1 - l);
      const f = (n) => {
        const k = (n + h / 30) % 12;
        const c = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
        return Math.round(255 * Math.max(0, Math.min(1, c))).toString(16).padStart(2, '0');
      };
      return `#${f(0)}${f(8)}${f(4)}`;
    }
    function hslVar(prop, fallback) {
      try {
        const raw = getComputedStyle(document.documentElement).getPropertyValue(prop).trim();
        if (!raw) return fallback;
        if (raw.startsWith('#')) return raw;
        const parts = raw.replace(/%/g, '').split(/[\s,]+/).map(Number);
        if (parts.length >= 3 && parts.every((n) => !isNaN(n))) return hslToHex(parts[0], parts[1], parts[2]);
      } catch {}
      return fallback;
    }
    // VSCode Dark+ palette
    monaco.editor.defineTheme('xt-dark', {
      base: 'vs-dark', inherit: true,
      rules: [
        { token: '', foreground: 'd4d4d4' },
        { token: 'comment', foreground: '6a9955' },
        { token: 'comment.block', foreground: '6a9955' },
        { token: 'comment.line', foreground: '6a9955' },
        { token: 'comment.doc', foreground: '6a9955' },
        { token: 'keyword', foreground: '569cd6' },
        { token: 'keyword.control', foreground: 'c586c0' },
        { token: 'keyword.operator', foreground: 'd4d4d4' },
        { token: 'storage', foreground: '569cd6' },
        { token: 'storage.type', foreground: '569cd6' },
        { token: 'string', foreground: 'ce9178' },
        { token: 'string.escape', foreground: 'd7ba7d' },
        { token: 'string.regexp', foreground: 'd16969' },
        { token: 'number', foreground: 'b5cea8' },
        { token: 'number.hex', foreground: 'b5cea8' },
        { token: 'number.float', foreground: 'b5cea8' },
        { token: 'type', foreground: '4ec9b0' },
        { token: 'type.identifier', foreground: '4ec9b0' },
        { token: 'entity.name.type', foreground: '4ec9b0' },
        { token: 'entity.name.class', foreground: '4ec9b0' },
        { token: 'entity.name.function', foreground: 'dcdcaa' },
        { token: 'support.function', foreground: 'dcdcaa' },
        { token: 'function', foreground: 'dcdcaa' },
        { token: 'variable', foreground: '9cdcfe' },
        { token: 'variable.parameter', foreground: '9cdcfe' },
        { token: 'variable.predefined', foreground: '4fc1ff' },
        { token: 'identifier', foreground: '9cdcfe' },
        { token: 'constant', foreground: '4fc1ff' },
        { token: 'constant.language', foreground: '569cd6' },
        { token: 'constant.numeric', foreground: 'b5cea8' },
        { token: 'tag', foreground: '569cd6' },
        { token: 'tag.id', foreground: '569cd6' },
        { token: 'tag.class', foreground: '569cd6' },
        { token: 'metatag', foreground: '569cd6' },
        { token: 'metatag.content', foreground: 'ce9178' },
        { token: 'attribute.name', foreground: '9cdcfe' },
        { token: 'attribute.value', foreground: 'ce9178' },
        { token: 'operator', foreground: 'd4d4d4' },
        { token: 'delimiter', foreground: 'd4d4d4' },
        { token: 'delimiter.bracket', foreground: 'd4d4d4' },
        { token: 'delimiter.parenthesis', foreground: 'd4d4d4' },
        { token: 'delimiter.square', foreground: 'd4d4d4' },
        { token: 'delimiter.curly', foreground: 'd4d4d4' },
        { token: 'regexp', foreground: 'd16969' },
        { token: 'namespace', foreground: '4ec9b0' },
        { token: 'markup.heading', foreground: '569cd6', fontStyle: 'bold' },
        { token: 'markup.bold', fontStyle: 'bold' },
        { token: 'markup.italic', fontStyle: 'italic' },
        { token: 'markup.inline', foreground: 'ce9178' },
      ],
      colors: {
        'editor.background': '#1e1e1e',
        'editor.foreground': '#d4d4d4',
        'editor.lineHighlightBackground': '#2a2d2e',
        'editor.lineHighlightBorder': '#1e1e1e',
        'editor.selectionBackground': '#264f78',
        'editor.inactiveSelectionBackground': '#3a3d41',
        'editor.findMatchBackground': '#515c6a',
        'editor.findMatchHighlightBackground': '#ea5c0055',
        'editorCursor.foreground': '#aeafad',
        'editorWhitespace.foreground': '#3b3b3b',
        'editorIndentGuide.background': '#404040',
        'editorIndentGuide.activeBackground': '#707070',
        'editorLineNumber.foreground': '#858585',
        'editorLineNumber.activeForeground': '#c6c6c6',
        'editorGutter.background': '#1e1e1e',
        'editorBracketMatch.background': '#0064001a',
        'editorBracketMatch.border': '#888888',
        'editorWidget.background': '#252526',
        'editorWidget.border': '#454545',
        'editorSuggestWidget.background': '#252526',
        'editorSuggestWidget.border': '#454545',
        'editorSuggestWidget.foreground': '#d4d4d4',
        'editorSuggestWidget.selectedBackground': '#04395e',
        'editorHoverWidget.background': '#252526',
        'editorHoverWidget.border': '#454545',
        'input.background': '#3c3c3c',
        'input.border': '#3c3c3c',
        'input.foreground': '#cccccc',
        'dropdown.background': '#3c3c3c',
        'dropdown.border': '#3c3c3c',
        'dropdown.foreground': '#f0f0f0',
        'list.hoverBackground': '#2a2d2e',
        'list.activeSelectionBackground': '#094771',
        'list.activeSelectionForeground': '#ffffff',
        'list.inactiveSelectionBackground': '#37373d',
        'minimap.background': '#1e1e1e',
        'scrollbar.shadow': '#000000',
        'scrollbarSlider.background': '#79797966',
        'scrollbarSlider.hoverBackground': '#646464b3',
        'scrollbarSlider.activeBackground': '#bfbfbf66',
      },
    });
    monaco.editor.defineTheme('xt-light', {
      base: 'vs', inherit: true, rules: [],
      colors: {
        'editor.background': hslVar('--background', '#f6f8fa'),
        'editor.foreground': hslVar('--foreground', '#1f2328'),
        'editor.lineHighlightBackground': '#0969da10',
        'editor.selectionBackground': '#0969da30',
        'editor.inactiveSelectionBackground': '#0969da15',
        'editorLineNumber.foreground': hslVar('--muted-foreground', '#57606a'),
        'editorLineNumber.activeForeground': hslVar('--foreground', '#1f2328'),
        'editorGutter.background': hslVar('--background', '#f6f8fa'),
        'editorWidget.background': hslVar('--card', '#ffffff'),
        'editorWidget.border': hslVar('--border', '#d0d7de'),
        'minimap.background': hslVar('--background', '#f6f8fa'),
      },
    });
    themesDefined = true;
  }

  function isDarkTheme() {
    if (typeof document === 'undefined') return true;
    if (document.documentElement.classList.contains('dark')) return true;
    if (document.body && document.body.classList.contains('dark')) return true;
    // Default desktop client theme is dark (see styles.css color-scheme).
    return true;
  }

  // --- DOM scaffolding -----------------------------------------------
  // The workspace screen lives in #workspace-screen inside index.html.
  // Internal layout: top bar + (sidebar + editor area) + AI edit bar.

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const k in attrs) {
        if (k === 'class') node.className = attrs[k];
        else if (k === 'style') node.setAttribute('style', attrs[k]);
        else if (k === 'html') node.innerHTML = attrs[k];
        else if (k.startsWith('on') && typeof attrs[k] === 'function') {
          node.addEventListener(k.slice(2).toLowerCase(), attrs[k]);
        } else if (attrs[k] !== undefined && attrs[k] !== null) {
          node.setAttribute(k, attrs[k]);
        }
      }
    }
    if (children) {
      for (const c of [].concat(children)) {
        if (c == null) continue;
        node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
      }
    }
    return node;
  }

  // Lucide-style inline icons.
  const ICONS = {
    folder:   '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
    folderOpen:'<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.55 6a2 2 0 0 1-1.94 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/>',
    file:     '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>',
    chevron:  '<path d="m9 18 6-6-6-6"/>',
    arrowLeft:'<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
    upload:   '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
    plus:     '<path d="M12 5v14"/><path d="M5 12h14"/>',
    trash:    '<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
    refresh:  '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><polyline points="21 3 21 8 16 8"/>',
    save:     '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>',
    pencil:   '<path d="M17 3a2.85 2.85 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z"/>',
    eye:      '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
    columns:  '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="12" y1="3" x2="12" y2="21"/>',
    undo:     '<path d="M9 14 4 9l5-5"/><path d="M4 9h11a4 4 0 0 1 0 8h-1"/>',
    sparkles: '<path d="M12 3v18"/><path d="M3 12h18"/><path d="M5 5l14 14"/><path d="M19 5L5 19"/>',
    send:     '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
    spinner:  '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2.4" stroke-dasharray="40" stroke-linecap="round"/>',
  };
  function icon(name, size) {
    const s = size || 14;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('width', s); svg.setAttribute('height', s);
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none'); svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2'); svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round'); svg.setAttribute('aria-hidden', 'true');
    svg.classList.add('wk-icon');
    svg.innerHTML = ICONS[name] || '';
    return svg;
  }

  // ===================================================================
  // State + controller
  // ===================================================================

  const state = {
    open: false,
    cfg: null,            // { serverUrl, jwt }
    conversationId: null,
    items: [],            // raw recursive items
    tree: [],
    activeFile: null,     // { name, path }
    expandedFolders: new Set(),
    selectedItems: new Set(),
    sidebarOpen: true,
    isCreatingFolder: false,
    newFolderName: '',
    editor: null,         // monaco editor instance
    editorContent: '',
    editorOriginal: '',
    editorBlob: null,
    editorOriginalBlob: null,
    mediaTextContent: null,
    mediaDirty: false,
    isLoading: false,
    isSaving: false,
    mode: 'edit',         // 'edit' | 'preview' | 'split'
    splitFraction: 0.5,
    monaco: null,
    pollIntervalId: null,
    refreshTimerId: null,
    refreshBurstTimerIds: [],
    refreshInFlight: false,
    pendingRefresh: false,
    refreshSeq: 0,
    workspaceSignature: '',
  };

  // Roots + cached element references built on first open.
  let root = null;
  let sidebarEl, sidebarCollapsedEl, sidebarTreeEl, sidebarHeaderEl, newFolderRow, newFolderInput;
  let sidebarResizeEl;

  // Files panel is user-resizable; width persists across sessions.
  // Mirrors the chat-pane resize pattern in app.js.
  const WK_SIDEBAR_WIDTH_KEY = 'agixt.desktop.workspaceSidebarWidth.v1';
  const WK_SIDEBAR_MIN = 180;
  const WK_SIDEBAR_MAX = 560;
  const WK_SIDEBAR_DEFAULT = 260;

  function applySidebarWidth(w) {
    const n = Math.max(WK_SIDEBAR_MIN, Math.min(WK_SIDEBAR_MAX,
      Math.round(w || WK_SIDEBAR_DEFAULT)));
    if (sidebarEl) sidebarEl.style.width = n + 'px';
    return n;
  }

  function storedSidebarWidth() {
    try {
      const v = window.localStorage.getItem(WK_SIDEBAR_WIDTH_KEY);
      if (v != null) return Number(v);
    } catch (_) {}
    return WK_SIDEBAR_DEFAULT;
  }
  let editorAreaEl, editorMountEl, previewEl;
  let modeToggleEl, dirtyEl, fileNameEl, splitContainer, splitHandle;
  let splitLeft, splitRight;
  let actionsEl;            // toolbar action buttons row
  let revertBtn, downloadBtn, saveBtn;
  let welcomePane;
  let fileInputEl;          // hidden upload input

  function ensureRoot() {
    if (root) return root;
    root = document.getElementById('workspace-screen');
    if (!root) {
      root = el('section', { id: 'workspace-screen', class: 'workspace-screen', hidden: '' });
      // Mount inside the chat-screen's main pane so the sidenav and
      // chat both stay visible alongside the workspace. Falls back to
      // <body> for tests / older shells that don't render that layout.
      const main = document.querySelector('.chat-screen-main') || document.body;
      main.appendChild(root);
    }
    buildScaffold();
    return root;
  }

  function buildScaffold() {
    root.innerHTML = '';

    // No top bar — chat persists alongside the workspace (so a back-to-chat
    // affordance is unnecessary; the composer's folder icon toggles the
    // workspace), and the active filename already lives in the editor
    // toolbar. The Files panel sits on the right and can be collapsed
    // down to a thin re-expand strip.

    const body = el('div', { class: 'wk-body' });

    // Editor area (left) — primary work surface.
    editorAreaEl = el('div', { class: 'wk-editor-area' });
    welcomePane = el('div', { class: 'wk-welcome' }, [
      (function () { const s = icon('file', 48); s.classList.add('wk-welcome-icon'); return s; })(),
      el('p', { class: 'wk-welcome-text' }, 'Select a file from the Files panel to view or edit it'),
    ]);
    editorAreaEl.appendChild(welcomePane);
    body.appendChild(editorAreaEl);

    // Drag seam between the editor and the Files panel. Sits to the
    // panel's left; dragging it left widens the panel.
    sidebarResizeEl = el('div', { class: 'wk-sidebar-resize',
      title: 'Drag to resize · double-click to reset' });
    body.appendChild(sidebarResizeEl);
    bindSidebarResize();

    // Files panel (right). Header gets a chevron that collapses the panel
    // down to `.wk-sidebar-collapsed`; clicking the strip restores it.
    sidebarEl = el('aside', { class: 'wk-sidebar' });
    sidebarHeaderEl = el('div', { class: 'wk-sidebar-header' });
    const headerLabel = el('span', { class: 'wk-sidebar-title' }, 'Files');
    const headerActions = el('div', { class: 'wk-sidebar-actions' });
    const uploadBtn = el('button', { class: 'wk-icon-btn small', type: 'button', title: 'Upload files',
      onclick: () => fileInputEl.click() }, [icon('upload', 13)]);
    fileInputEl = el('input', { type: 'file', multiple: '', class: 'wk-file-input',
      onchange: onUploadFiles });
    const newFolderBtn = el('button', { class: 'wk-icon-btn small', type: 'button', title: 'New folder',
      onclick: () => { state.isCreatingFolder = true; renderNewFolderRow(); } }, [icon('plus', 13)]);
    const refreshBtn = el('button', { class: 'wk-icon-btn small', type: 'button', title: 'Refresh',
      onclick: () => refresh() }, [icon('refresh', 13)]);
    const collapseBtn = el('button', { class: 'wk-icon-btn small wk-sidebar-collapse-btn',
      type: 'button', title: 'Collapse Files',
      onclick: () => { state.sidebarOpen = false; renderSidebarVisibility(); } },
      [icon('chevron', 13)]);
    headerActions.appendChild(uploadBtn);
    headerActions.appendChild(fileInputEl);
    headerActions.appendChild(newFolderBtn);
    headerActions.appendChild(refreshBtn);
    headerActions.appendChild(collapseBtn);
    sidebarHeaderEl.appendChild(headerLabel);
    sidebarHeaderEl.appendChild(headerActions);
    sidebarEl.appendChild(sidebarHeaderEl);

    newFolderRow = el('div', { class: 'wk-newfolder-row', hidden: '' });
    newFolderInput = el('input', { type: 'text', placeholder: 'Folder name…', class: 'wk-input',
      onkeydown: (e) => {
        if (e.key === 'Enter') { e.preventDefault(); createFolder(); }
        else if (e.key === 'Escape') { state.isCreatingFolder = false; state.newFolderName = ''; renderNewFolderRow(); }
      },
      oninput: (e) => { state.newFolderName = e.target.value; },
    });
    const okBtn = el('button', { class: 'wk-btn small primary', type: 'button', onclick: createFolder }, 'OK');
    const cancelBtn = el('button', { class: 'wk-btn small', type: 'button',
      onclick: () => { state.isCreatingFolder = false; state.newFolderName = ''; renderNewFolderRow(); } }, '✕');
    newFolderRow.appendChild(newFolderInput);
    newFolderRow.appendChild(okBtn);
    newFolderRow.appendChild(cancelBtn);
    sidebarEl.appendChild(newFolderRow);

    sidebarTreeEl = el('div', { class: 'wk-tree' });
    sidebarEl.appendChild(sidebarTreeEl);
    body.appendChild(sidebarEl);
    applySidebarWidth(storedSidebarWidth());

    // Collapsed strip — replaces the Files panel when the user collapses
    // it. Click anywhere on the strip to bring the Files panel back.
    sidebarCollapsedEl = el('button', { class: 'wk-sidebar-collapsed', type: 'button',
      title: 'Show Files', 'aria-label': 'Show Files',
      onclick: () => { state.sidebarOpen = true; renderSidebarVisibility(); } });
    const stripIcon = icon('chevron', 14);
    stripIcon.classList.add('wk-sidebar-collapsed-icon');
    const stripLabel = el('span', { class: 'wk-sidebar-collapsed-label' }, 'Files');
    sidebarCollapsedEl.appendChild(stripIcon);
    sidebarCollapsedEl.appendChild(stripLabel);
    body.appendChild(sidebarCollapsedEl);

    root.appendChild(body);
  }

  // --- Active file editor pane (rebuilt per file) --------------------
  function buildEditorPane() {
    while (editorAreaEl.firstChild) editorAreaEl.removeChild(editorAreaEl.firstChild);

    const wrap = el('div', { class: 'wk-editor-wrap' });

    // Toolbar
    const toolbar = el('div', { class: 'wk-editor-toolbar' });
    const left = el('div', { class: 'wk-editor-toolbar-left' });
    const backBtn = el('button', { class: 'wk-btn ghost small', type: 'button',
      onclick: () => closeActiveFile() }, [icon('arrowLeft', 14), document.createTextNode(' Back')]);
    const fileIcon = icon('file', 14);
    fileNameEl = el('span', { class: 'wk-editor-filename' }, state.activeFile ? state.activeFile.name : '');
    dirtyEl = el('span', { class: 'wk-dirty-marker', hidden: '' }, '(unsaved)');
    left.appendChild(backBtn);
    left.appendChild(fileIcon);
    left.appendChild(fileNameEl);
    left.appendChild(dirtyEl);
    toolbar.appendChild(left);

    actionsEl = el('div', { class: 'wk-editor-toolbar-right' });
    // Mode toggle
    modeToggleEl = el('div', { class: 'wk-mode-toggle' });
    function modeBtn(name, label, iconName) {
      const b = el('button', { class: 'wk-mode-btn', type: 'button',
        onclick: () => setMode(name) }, [icon(iconName, 12), document.createTextNode(' ' + label)]);
      b.dataset.mode = name;
      return b;
    }
    modeToggleEl.appendChild(modeBtn('edit', 'Edit', 'pencil'));
    modeToggleEl.appendChild(modeBtn('split', 'Split', 'columns'));
    modeToggleEl.appendChild(modeBtn('preview', 'Preview', 'eye'));
    actionsEl.appendChild(modeToggleEl);

    revertBtn = el('button', { class: 'wk-btn ghost small', type: 'button', hidden: '',
      onclick: () => revert() }, [icon('undo', 12), document.createTextNode(' Revert')]);
    downloadBtn = el('button', { class: 'wk-btn ghost small', type: 'button',
      onclick: () => downloadActiveFile() }, [icon('download', 12), document.createTextNode(' Download')]);
    saveBtn = el('button', { class: 'wk-btn ghost small', type: 'button', disabled: '',
      onclick: () => save() }, [icon('save', 12), document.createTextNode(' Save')]);
    actionsEl.appendChild(revertBtn);
    actionsEl.appendChild(downloadBtn);
    actionsEl.appendChild(saveBtn);
    toolbar.appendChild(actionsEl);
    wrap.appendChild(toolbar);

    // Body — created based on mode/media type after content loads.
    // No in-editor AI bar: the chat composer that sits next to the
    // workspace handles "ask AI to edit this file" already, and it
    // automatically receives context about the active file (and any
    // editor selection) via `getContext()`.
    editorMountEl = el('div', { class: 'wk-editor-body' });
    wrap.appendChild(editorMountEl);

    editorAreaEl.appendChild(wrap);
  }

  // ===================================================================
  // Tree rendering
  // ===================================================================

  function renderSidebarVisibility() {
    if (sidebarEl) sidebarEl.style.display = state.sidebarOpen ? '' : 'none';
    if (sidebarResizeEl) sidebarResizeEl.style.display = state.sidebarOpen ? '' : 'none';
    if (sidebarCollapsedEl) sidebarCollapsedEl.style.display = state.sidebarOpen ? 'none' : '';
  }

  // Files panel sits to the right of the seam, so dragging the handle
  // left (clientX decreasing) should widen it.
  function bindSidebarResize() {
    if (!sidebarResizeEl) return;
    let dragging = false, startX = 0, startWidth = 0;
    sidebarResizeEl.addEventListener('pointerdown', (e) => {
      if (!sidebarEl) return;
      dragging = true;
      sidebarResizeEl.classList.add('is-dragging');
      startX = e.clientX;
      startWidth = sidebarEl.getBoundingClientRect().width;
      try { sidebarResizeEl.setPointerCapture(e.pointerId); } catch (_) {}
      e.preventDefault();
    });
    sidebarResizeEl.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      const next = applySidebarWidth(startWidth - (e.clientX - startX));
      try { window.localStorage.setItem(WK_SIDEBAR_WIDTH_KEY, String(next)); } catch (_) {}
    });
    const stop = (e) => {
      if (!dragging) return;
      dragging = false;
      sidebarResizeEl.classList.remove('is-dragging');
      try { sidebarResizeEl.releasePointerCapture(e.pointerId); } catch (_) {}
    };
    sidebarResizeEl.addEventListener('pointerup', stop);
    sidebarResizeEl.addEventListener('pointercancel', stop);
    sidebarResizeEl.addEventListener('dblclick', () => {
      applySidebarWidth(WK_SIDEBAR_DEFAULT);
      try { window.localStorage.setItem(WK_SIDEBAR_WIDTH_KEY, String(WK_SIDEBAR_DEFAULT)); } catch (_) {}
    });
  }

  function renderNewFolderRow() {
    newFolderRow.hidden = !state.isCreatingFolder;
    if (state.isCreatingFolder) {
      newFolderInput.value = state.newFolderName;
      setTimeout(() => newFolderInput.focus(), 0);
    }
  }

  function renderTree() {
    while (sidebarTreeEl.firstChild) sidebarTreeEl.removeChild(sidebarTreeEl.firstChild);

    if (state.isLoading && !state.tree.length) {
      sidebarTreeEl.appendChild(el('div', { class: 'wk-tree-empty' }, 'Loading…'));
      return;
    }
    if (!state.tree.length) {
      sidebarTreeEl.appendChild(el('div', { class: 'wk-tree-empty' }, 'No files yet. Upload files to get started.'));
      return;
    }
    for (const node of state.tree) {
      sidebarTreeEl.appendChild(renderTreeNode(node));
    }
  }

  function renderTreeNode(node) {
    const wrap = document.createDocumentFragment();
    const isFolder = node.type === 'folder';
    const isExpanded = state.expandedFolders.has(node.path);
    const isActive = state.activeFile && state.activeFile.path === node.path;
    const isViewable = !isFolder && isViewableFile(node.name);

    const row = el('div', {
      class: 'wk-tree-row' + (isActive ? ' active' : '') + (!isFolder && !isViewable ? ' dim' : ''),
      style: `padding-left:${8 + node.depth * 14}px`,
      onclick: () => {
        if (isFolder) {
          if (isExpanded) state.expandedFolders.delete(node.path);
          else state.expandedFolders.add(node.path);
          renderTree();
        } else if (isViewable) openFile(node);
      },
    });
    if (isFolder) {
      const chev = icon('chevron', 12);
      chev.classList.add('wk-tree-chevron');
      if (isExpanded) chev.classList.add('expanded');
      row.appendChild(chev);
    } else {
      row.appendChild(el('span', { class: 'wk-tree-spacer' }));
    }
    const ic = icon(isFolder ? (isExpanded ? 'folderOpen' : 'folder') : 'file', 13);
    ic.classList.add(isFolder ? 'wk-tree-folder-icon' : 'wk-tree-file-icon');
    row.appendChild(ic);
    row.appendChild(el('span', { class: 'wk-tree-name' }, node.name || '(unnamed)'));
    const acts = el('div', { class: 'wk-tree-actions' });
    if (!isFolder) {
      acts.appendChild(el('button', { class: 'wk-tree-act', type: 'button', title: 'Download',
        onclick: (e) => { e.stopPropagation(); downloadItem(node); } }, [icon('download', 12)]));
    }
    acts.appendChild(el('button', { class: 'wk-tree-act danger', type: 'button', title: 'Delete',
      onclick: (e) => { e.stopPropagation(); deleteItem(node); } }, [icon('trash', 12)]));
    row.appendChild(acts);
    wrap.appendChild(row);

    if (isFolder && isExpanded && node.children.length) {
      // No margin here: each child row already encodes its full depth via
      // its own `padding-left` inline style. Adding depth-based margin to
      // the container too would compound the indent every level deeper.
      const kids = el('div', { class: 'wk-tree-children' });
      for (const child of node.children) kids.appendChild(renderTreeNode(child));
      wrap.appendChild(kids);
    }
    return wrap;
  }

  // ===================================================================
  // Workspace data load / mutate
  // ===================================================================

  const LIVE_REFRESH_MS = 4000;
  const EVENT_REFRESH_DELAY_MS = 250;

  function flattenItems(items, out) {
    const target = out || [];
    for (const item of items || []) {
      target.push(item);
      if (item && item.children && item.children.length) flattenItems(item.children, target);
    }
    return target;
  }

  function workspaceSignature(items) {
    return flattenItems(items)
      .map((item) => [
        item && item.path ? item.path : '',
        item && item.type ? item.type : '',
        item && item.size != null ? item.size : '',
        item && item.modified ? item.modified : '',
      ].join('|'))
      .sort()
      .join('\n');
  }

  function findItemByPath(items, path) {
    const wanted = normalizePath(path || '');
    return flattenItems(items).find((item) => normalizePath(item && item.path) === wanted) || null;
  }

  function metadataChanged(a, b) {
    if (!a || !b) return !!(a || b);
    return (a.size || 0) !== (b.size || 0)
      || String(a.modified || '') !== String(b.modified || '')
      || String(a.type || '') !== String(b.type || '');
  }

  function activeFileDirty() {
    const f = state.activeFile;
    if (!f) return false;
    const isMedia = window.AgixtWorkspacePreview && window.AgixtWorkspacePreview.isPreviewableMedia(f.name);
    return isMedia ? state.mediaDirty : state.editorContent !== state.editorOriginal;
  }

  function startLiveRefresh() {
    if (state.pollIntervalId) return;
    state.pollIntervalId = setInterval(() => {
      refresh({ silent: true, reason: 'poll' }).catch((err) => {
        console.warn('workspace live refresh failed', err);
      });
    }, LIVE_REFRESH_MS);
  }

  function stopLiveRefresh() {
    if (state.pollIntervalId) {
      clearInterval(state.pollIntervalId);
      state.pollIntervalId = null;
    }
    if (state.refreshTimerId) {
      clearTimeout(state.refreshTimerId);
      state.refreshTimerId = null;
    }
    state.refreshBurstTimerIds.forEach((id) => clearTimeout(id));
    state.refreshBurstTimerIds = [];
    state.pendingRefresh = false;
  }

  function scheduleLiveRefresh(reason, delay) {
    if (!state.open) return;
    if (state.refreshTimerId) clearTimeout(state.refreshTimerId);
    state.refreshTimerId = setTimeout(() => {
      state.refreshTimerId = null;
      refresh({ silent: true, reason: reason || 'event' }).catch((err) => {
        console.warn('workspace event refresh failed', err);
      });
    }, delay == null ? EVENT_REFRESH_DELAY_MS : delay);
  }

  function scheduleLiveRefreshBurst(reason) {
    if (!state.open) return;
    state.refreshBurstTimerIds.forEach((id) => clearTimeout(id));
    state.refreshBurstTimerIds = [0, 1000, 3000, 7000].map((delay) => setTimeout(() => {
      refresh({ silent: true, reason: reason || 'burst' }).catch((err) => {
        console.warn('workspace burst refresh failed', err);
      });
    }, delay));
  }

  async function waitForRefreshIdle() {
    for (let i = 0; i < 40 && state.refreshInFlight; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
  }

  async function refresh(options) {
    if (!state.cfg || !state.conversationId) return;
    const opts = options || {};
    const silent = !!opts.silent;
    if (state.refreshInFlight) {
      state.pendingRefresh = true;
      return;
    }
    state.refreshInFlight = true;
    const refreshSeq = ++state.refreshSeq;
    const requestConversationId = state.conversationId;
    const requestCfg = { ...state.cfg };
    const previousItems = state.items || [];
    const previousSignature = state.workspaceSignature || workspaceSignature(previousItems);
    const previousActive = state.activeFile ? findItemByPath(previousItems, state.activeFile.path) : null;
    if (!silent) {
      state.isLoading = true;
      renderTree();
    }
    try {
      const data = await window.AgixtWorkspaceApi.getWorkspace(requestCfg, requestConversationId, { recursive: true });
      if (
        refreshSeq !== state.refreshSeq
        || String(requestConversationId) !== String(state.conversationId)
      ) {
        state.pendingRefresh = true;
        return;
      }
      const nextItems = data.items || [];
      const nextSignature = workspaceSignature(nextItems);
      const changed = nextSignature !== previousSignature;
      state.items = nextItems;
      state.tree = buildTree(state.items);
      state.workspaceSignature = nextSignature;
      if (changed || !silent) renderTree();
      if (state.activeFile) {
        const nextActive = findItemByPath(nextItems, state.activeFile.path);
        if (!nextActive && !activeFileDirty()) {
          closeActiveFile();
        } else if (nextActive && metadataChanged(previousActive, nextActive) && !activeFileDirty() && !state.isSaving) {
          state.activeFile = { name: nextActive.name, path: nextActive.path };
          await loadFile({ silent: true });
        }
      }
    } catch (err) {
      console.error('workspace getWorkspace failed', err);
      if (!silent) toast('Failed to load workspace', 'error');
    } finally {
      if (!silent) {
        state.isLoading = false;
        renderTree();
      }
      state.refreshInFlight = false;
      if (state.pendingRefresh && state.open) {
        state.pendingRefresh = false;
        scheduleLiveRefresh('pending', 0);
      }
    }
    // Initialise cross-file Monaco models in the background.
    if (state.monaco && window.AgixtWorkspaceModels) {
      window.AgixtWorkspaceModels.init(state.monaco);
      window.AgixtWorkspaceModels.ensureModelsLoaded(
        state.monaco, window.AgixtWorkspaceApi, state.cfg, state.conversationId, state.items,
        { activePath: state.activeFile && state.activeFile.path },
      ).catch(() => {});
    }
  }

  async function onUploadFiles(e) {
    const files = e.target.files;
    if (!files || !files.length) return;
    try {
      await window.AgixtWorkspaceApi.uploadFiles(state.cfg, state.conversationId, Array.from(files));
      toast(`${files.length} file${files.length === 1 ? '' : 's'} uploaded`, 'success');
      await refresh();
    } catch (err) {
      console.error(err);
      toast('Failed to upload files', 'error');
    } finally {
      e.target.value = '';
    }
  }

  async function createFolder() {
    const name = (state.newFolderName || '').trim();
    if (!name) { toast('Folder name is required', 'error'); return; }
    try {
      await window.AgixtWorkspaceApi.createFolder(state.cfg, state.conversationId, name);
      toast(`Folder "${name}" created`, 'success');
      state.isCreatingFolder = false;
      state.newFolderName = '';
      renderNewFolderRow();
      await refresh();
    } catch (err) {
      console.error(err);
      toast('Failed to create folder', 'error');
    }
  }

  async function deleteItem(item) {
    const label = item.type === 'folder' ? 'folder and its contents' : 'file';
    if (!window.confirm(`Delete ${label} "${item.name}"?`)) return;
    try {
      await window.AgixtWorkspaceApi.deleteItem(state.cfg, state.conversationId, item.path);
      toast(`${item.name} deleted`, 'success');
      if (state.activeFile && state.activeFile.path === item.path) closeActiveFile();
      await refresh();
    } catch (err) {
      console.error(err);
      toast('Failed to delete item', 'error');
    }
  }

  async function downloadItem(item) {
    if (item.type !== 'file') return;
    try {
      const result = await window.AgixtWorkspaceApi.downloadFile(state.cfg, state.conversationId, item.path);
      if (!result) return;
      triggerBlobDownload(result.blob, result.filename);
    } catch (err) {
      console.error(err);
      toast('Failed to download file', 'error');
    }
  }

  function triggerBlobDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // ===================================================================
  // File editor
  // ===================================================================

  function setMode(mode) {
    if (state.activeFile && window.AgixtWorkspacePreview.isPreviewableMedia(state.activeFile.name)) {
      mode = 'preview';
    }
    state.mode = mode;
    renderEditorBody();
    syncModeButtons();
  }

  function syncModeButtons() {
    if (!modeToggleEl) return;
    modeToggleEl.querySelectorAll('.wk-mode-btn').forEach((b) => {
      b.classList.toggle('active', b.dataset.mode === state.mode);
    });
    const f = state.activeFile;
    const hasPreview = f && isPreviewable(f.name);
    const isMedia = f && window.AgixtWorkspacePreview.isPreviewableMedia(f.name);
    modeToggleEl.style.display = (hasPreview && !isMedia) ? '' : 'none';
  }

  function syncDirtyButtons() {
    const f = state.activeFile; if (!f) return;
    const isMedia = window.AgixtWorkspacePreview.isPreviewableMedia(f.name);
    const dirty = isMedia ? state.mediaDirty : state.editorContent !== state.editorOriginal;
    dirtyEl.hidden = !dirty;
    revertBtn.hidden = !dirty;
    saveBtn.disabled = !dirty || state.isSaving;
    saveBtn.classList.toggle('primary', dirty);
  }

  function openFile(item) {
    if (state.activeFile && state.activeFile.path === item.path) return;
    state.activeFile = { name: item.name, path: item.path };
    if (welcomePane && welcomePane.parentNode) welcomePane.parentNode.removeChild(welcomePane);
    buildEditorPane();
    fileNameEl.textContent = item.name;
    // Initial mode based on file type.
    const isMedia = window.AgixtWorkspacePreview.isPreviewableMedia(item.name);
    if (isMedia) state.mode = 'preview';
    else if (isPreviewable(item.name)) state.mode = 'split';
    else state.mode = 'edit';
    syncModeButtons();
    renderTree(); // active highlight
    loadFile();
  }

  function closeActiveFile() {
    state.activeFile = null;
    state.editorContent = '';
    state.editorOriginal = '';
    state.editorBlob = null;
    state.editorOriginalBlob = null;
    state.mediaTextContent = null;
    state.mediaDirty = false;
    if (state.editor) {
      try { state.editor.dispose(); } catch {}
      state.editor = null;
    }
    while (editorAreaEl.firstChild) editorAreaEl.removeChild(editorAreaEl.firstChild);
    editorAreaEl.appendChild(welcomePane);
    renderTree();
  }

  async function loadFile(options) {
    if (!state.activeFile) return;
    const opts = options || {};
    const silent = !!opts.silent;
    state.isLoading = true;
    state.mediaDirty = false;
    if (!silent) showEditorLoading();

    const isMedia = window.AgixtWorkspacePreview.isPreviewableMedia(state.activeFile.name);
    const MAX_RETRIES = 2;
    let lastError;
    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const result = await window.AgixtWorkspaceApi.downloadFile(state.cfg, state.conversationId, state.activeFile.path);
        if (!result) break;
        state.editorBlob = result.blob;
        state.editorOriginalBlob = result.blob;
        if (isMedia) {
          state.mediaTextContent = await window.AgixtWorkspacePreview.extractTextFromBlob(result.blob, state.activeFile.name);
        } else {
          const text = await result.blob.text();
          state.editorContent = text;
          state.editorOriginal = text;
        }
        lastError = null;
        break;
      } catch (err) {
        lastError = err;
        console.error(`File load attempt ${attempt + 1} failed:`, err);
        if (attempt < MAX_RETRIES) await new Promise((r) => setTimeout(r, 500));
      }
    }
    state.isLoading = false;
    if (lastError && !silent) toast('Failed to load file', 'error');
    renderEditorBody();
    syncDirtyButtons();
  }

  function showEditorLoading() {
    while (editorMountEl.firstChild) editorMountEl.removeChild(editorMountEl.firstChild);
    const wrap = el('div', { class: 'wk-loading' });
    const sp = icon('spinner', 28);
    sp.classList.add('wk-spin');
    wrap.appendChild(sp);
    wrap.appendChild(el('p', { class: 'wk-loading-text' }, 'Loading file…'));
    editorMountEl.appendChild(wrap);
  }

  function renderEditorBody() {
    while (editorMountEl.firstChild) editorMountEl.removeChild(editorMountEl.firstChild);
    if (state.editor) {
      try { state.editor.dispose(); } catch {}
      state.editor = null;
    }
    const f = state.activeFile; if (!f) return;
    const isMedia = window.AgixtWorkspacePreview.isPreviewableMedia(f.name);
    if (isMedia) {
      const previewWrap = el('div', { class: 'wk-preview' });
      editorMountEl.appendChild(previewWrap);
      window.AgixtWorkspacePreview.render(previewWrap, state.editorBlob, f.name, () => downloadActiveFile());
      return;
    }

    if (state.mode === 'edit') {
      const mount = el('div', { class: 'wk-monaco-mount' });
      editorMountEl.appendChild(mount);
      mountMonaco(mount);
    } else if (state.mode === 'preview') {
      const prev = el('div', { class: 'wk-text-preview' });
      editorMountEl.appendChild(prev);
      renderTextPreview(prev);
    } else if (state.mode === 'split') {
      splitContainer = el('div', { class: 'wk-split' });
      splitLeft = el('div', { class: 'wk-split-left' });
      splitHandle = el('div', { class: 'wk-split-handle' });
      splitRight = el('div', { class: 'wk-split-right' });
      splitLeft.style.width = (state.splitFraction * 100) + '%';
      splitRight.style.width = ((1 - state.splitFraction) * 100) + '%';
      const mount = el('div', { class: 'wk-monaco-mount' });
      splitLeft.appendChild(mount);
      const prev = el('div', { class: 'wk-text-preview' });
      splitRight.appendChild(prev);
      splitContainer.appendChild(splitLeft);
      splitContainer.appendChild(splitHandle);
      splitContainer.appendChild(splitRight);
      editorMountEl.appendChild(splitContainer);
      mountMonaco(mount);
      renderTextPreview(prev);
      bindSplitDrag();
    }
  }

  function bindSplitDrag() {
    let dragging = false;
    splitHandle.addEventListener('pointerdown', (e) => {
      e.preventDefault(); dragging = true;
      splitHandle.setPointerCapture(e.pointerId);
    });
    splitContainer.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      const rect = splitContainer.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const fr = Math.min(0.85, Math.max(0.15, x / rect.width));
      state.splitFraction = fr;
      splitLeft.style.width = (fr * 100) + '%';
      splitRight.style.width = ((1 - fr) * 100) + '%';
      if (state.editor) state.editor.layout();
    });
    splitContainer.addEventListener('pointerup', () => { dragging = false; });
  }

  let _htmlPreviewTimer = null;
  function renderTextPreview(target) {
    const f = state.activeFile;
    if (!f) return;
    // HTML files render as a live document in a sandboxed iframe rather
    // than being run through the markdown renderer + injected into the
    // host doc. Debounced so split-mode keystrokes don't reload the frame.
    if (isHtmlFile(f.name) && window.AgixtWorkspacePreview &&
        window.AgixtWorkspacePreview.renderHtmlDoc) {
      const paint = () => window.AgixtWorkspacePreview.renderHtmlDoc(
        target,
        state.editorContent || '',
        {
          api: window.AgixtWorkspaceApi,
          cfg: state.cfg,
          conversationId: state.conversationId,
          filePath: f.path,
        });
      if (target.querySelector('.wkfp-html')) {
        clearTimeout(_htmlPreviewTimer);
        _htmlPreviewTimer = setTimeout(paint, 300);
      } else {
        paint();
      }
      return;
    }
    const md = window.AgixtMarkdown;
    const language = getFileLanguage(f.name);
    let html;
    if (isMarkdownLike(f.name)) {
      html = md ? md.render(state.editorContent || '') : escape(state.editorContent || '');
    } else {
      const code = `\`\`\`${language}\n${state.editorContent || ''}\n\`\`\``;
      html = md ? md.render(code) : `<pre><code>${escape(state.editorContent || '')}</code></pre>`;
    }
    const wrap = el('div', { class: 'wk-prose' });
    wrap.innerHTML = html;
    target.innerHTML = '';
    target.appendChild(wrap);
  }

  function escape(s) {
    return String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  }

  // --- Monaco mount ---------------------------------------------------
  async function mountMonaco(target) {
    let monaco = state.monaco;
    if (!monaco) {
      try {
        monaco = await loadMonaco();
        state.monaco = monaco;
        if (window.AgixtWorkspaceModels) {
          window.AgixtWorkspaceModels.init(monaco);
          // Kick off background load of all workspace models.
          window.AgixtWorkspaceModels.ensureModelsLoaded(
            monaco, window.AgixtWorkspaceApi, state.cfg, state.conversationId, state.items,
            { activePath: state.activeFile && state.activeFile.path },
          ).catch(() => {});
        }
      } catch (err) {
        console.error('Monaco load failed', err);
        target.textContent = 'Failed to load editor.';
        return;
      }
    }
    if (window.AgixtWorkspaceModels) window.AgixtWorkspaceModels.init(monaco);
    if (!themesDefined) defineThemes(monaco);
    const themeId = isDarkTheme() ? 'xt-dark' : 'xt-light';
    monaco.editor.setTheme(themeId);

    const f = state.activeFile;
    const lang = getFileLanguage(f.name);
    const monacoLang = (lang === 'bash' ? 'shell' : lang === 'text' ? 'plaintext' : lang === 'csv' ? 'plaintext' : lang);

    // Reuse / create model for this file path.
    const uri = monaco.Uri.parse(`file://${f.path}`);
    let model = monaco.editor.getModel(uri);
    if (model) {
      if (model.getValue() !== state.editorContent) model.setValue(state.editorContent);
    } else {
      model = monaco.editor.createModel(state.editorContent, monacoLang, uri);
    }

    state.editor = monaco.editor.create(target, {
      model,
      theme: themeId,
      readOnly: false,
      fontSize: 13,
      lineHeight: 20,
      padding: { top: 8, bottom: 8 },
      tabSize: 2,
      wordWrap: 'off',
      scrollBeyondLastLine: false,
      automaticLayout: true,
      renderLineHighlight: 'line',
      lineNumbers: 'on',
      folding: true,
      bracketPairColorization: { enabled: true },
      minimap: { enabled: true, scale: 2 },
      suggest: { showKeywords: true, showSnippets: true },
      quickSuggestions: true,
      parameterHints: { enabled: true },
      formatOnPaste: true,
      autoClosingBrackets: 'always',
      autoClosingQuotes: 'always',
      autoIndent: 'full',
    });

    state.editor.onDidChangeModelContent(() => {
      state.editorContent = state.editor.getValue();
      if (window.AgixtWorkspaceModels) {
        window.AgixtWorkspaceModels.updateModel(monaco, f.path, state.editorContent);
      }
      // Re-render preview on text changes if visible.
      if (state.mode === 'split' && splitRight) {
        const prev = splitRight.querySelector('.wk-text-preview');
        if (prev) renderTextPreview(prev);
      }
      syncDirtyButtons();
    });

    // Intercept go-to-definition cross-file navigation.
    try {
      const editorService = state.editor._codeEditorService;
      if (editorService && editorService.openCodeEditor) {
        const orig = editorService.openCodeEditor.bind(editorService);
        editorService.openCodeEditor = async (input, source, sideBySide) => {
          const targetUri = input && input.resource;
          if (targetUri) {
            const path = targetUri.path;
            if (path && path !== f.path) {
              const result = findFileInTree(state.tree, path);
              if (result && isViewableFile(result.node.name)) {
                for (const fp of result.folderPaths) state.expandedFolders.add(fp);
                renderTree();
                openFile({ name: result.node.name, path: result.node.path });
                return null;
              }
            }
          }
          return orig(input, source, sideBySide);
        };
      }
    } catch {}
  }

  // --- Save / revert / download / AI edit ----------------------------
  async function save() {
    const f = state.activeFile; if (!f) return;
    const isMedia = window.AgixtWorkspacePreview.isPreviewableMedia(f.name);
    const dirty = isMedia ? state.mediaDirty : state.editorContent !== state.editorOriginal;
    if (!dirty || state.isSaving) return;
    state.isSaving = true;
    syncDirtyButtons();
    try {
      let blob;
      if (isMedia && state.editorBlob) blob = state.editorBlob;
      else blob = new Blob([state.editorContent], { type: 'text/plain' });
      const segs = f.path.split('/').filter(Boolean);
      segs.pop();
      const dest = segs.length ? '/' + segs.join('/') : undefined;
      const file = new File([blob], f.name, { type: blob.type });
      await window.AgixtWorkspaceApi.uploadFiles(state.cfg, state.conversationId, [file], dest);
      if (isMedia) { state.editorOriginalBlob = state.editorBlob; state.mediaDirty = false; }
      else state.editorOriginal = state.editorContent;
      toast('File saved', 'success');
    } catch (err) {
      console.error(err);
      toast('Failed to save file', 'error');
    } finally {
      state.isSaving = false;
      syncDirtyButtons();
    }
  }

  function revert() {
    const f = state.activeFile; if (!f) return;
    const isMedia = window.AgixtWorkspacePreview.isPreviewableMedia(f.name);
    if (isMedia) {
      state.editorBlob = state.editorOriginalBlob;
      state.mediaDirty = false;
    } else {
      state.editorContent = state.editorOriginal;
      if (state.editor) state.editor.setValue(state.editorContent);
    }
    renderEditorBody();
    syncDirtyButtons();
  }

  async function downloadActiveFile() {
    const f = state.activeFile; if (!f) return;
    try {
      const result = await window.AgixtWorkspaceApi.downloadFile(state.cfg, state.conversationId, f.path);
      if (result) triggerBlobDownload(result.blob, result.filename);
    } catch (err) {
      console.error(err);
      toast('Failed to download file', 'error');
    }
  }

  // ===================================================================
  // Public API
  // ===================================================================

  async function open(opts) {
    ensureRoot();
    const nextConversationId = opts.conversationId;
    const conversationChanged = nextConversationId && nextConversationId !== state.conversationId;
    state.refreshSeq += 1;
    state.cfg = { serverUrl: opts.serverUrl, jwt: opts.jwt, agentName: opts.agentName };
    state.conversationId = nextConversationId;
    if (conversationChanged) {
      state.items = [];
      state.tree = [];
      state.workspaceSignature = '';
      state.expandedFolders.clear();
      if (state.activeFile) closeActiveFile();
    }
    if (!state.cfg.serverUrl || !state.cfg.jwt) {
      toast('Sign in first', 'error'); return;
    }
    if (!state.conversationId) { toast('No active conversation', 'error'); return; }

    state.open = true;
    root.hidden = false;
    document.body.classList.add('workspace-open');
    // Workspace shares the right-side content slot with extension
    // pages, so opening it forces the active sidenav view back to
    // chat. Without this, an extension would still be rendered
    // alongside the workspace inside `.chat-screen-main` (two content
    // panes fighting for the same space).
    if (window.AgixtSidenav && typeof window.AgixtSidenav.setActiveView === 'function') {
      window.AgixtSidenav.setActiveView('chat');
    }
    // Chat stays alongside the workspace pane — `body.workspace-open`
    // marks the workspace pane visible inside `.chat-screen-main`,
    // while `body.window-mode` (managed by app.js's refreshWindowMode)
    // owns the chrome flip + geometry capture/restore. Reconciling
    // through one path means the workspace folder icon and any non-chat
    // sidenav view both produce the same window state.
    if (window.AgixtSidenav && typeof window.AgixtSidenav.syncContentPaneClass === 'function') {
      window.AgixtSidenav.syncContentPaneClass();
    }
    if (window.AgixtWindowMode && typeof window.AgixtWindowMode.refresh === 'function') {
      await window.AgixtWindowMode.refresh();
    }

    renderSidebarVisibility();
    renderTree();
    refresh();
    startLiveRefresh();
    bindKeyboard();
  }

  async function close() {
    if (!state.open) return;
    state.open = false;
    stopLiveRefresh();
    if (root) root.hidden = true;
    document.body.classList.remove('workspace-open');
    if (window.AgixtSidenav && typeof window.AgixtSidenav.syncContentPaneClass === 'function') {
      window.AgixtSidenav.syncContentPaneClass();
    }
    // app.js owns chrome + geometry now. With sticky decoration, the
    // window stays decorated even after workspace closes — `body.with-content-pane`
    // toggles off so the chat pane can fill the whole width.
    if (window.AgixtWindowMode && typeof window.AgixtWindowMode.refresh === 'function') {
      await window.AgixtWindowMode.refresh();
    }
    closeActiveFile();
    if (state.monaco && window.AgixtWorkspaceModels) {
      window.AgixtWorkspaceModels.dispose(state.monaco);
    }
    unbindKeyboard();
  }

  function toggle(opts) {
    if (state.open) close();
    else open(opts);
  }

  function isOpen() { return state.open; }

  // Ctrl/Cmd+S to save.
  let _keyHandler = null;
  function bindKeyboard() {
    if (_keyHandler) return;
    _keyHandler = (e) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === 's' || e.key === 'S')) {
        if (!state.open) return;
        e.preventDefault();
        save();
      }
    };
    window.addEventListener('keydown', _keyHandler);
  }
  function unbindKeyboard() {
    if (_keyHandler) {
      window.removeEventListener('keydown', _keyHandler);
      _keyHandler = null;
    }
  }

  // Reload the workspace for a different conversation. The user expects
  // switching threads (via the chat's convo switcher) to refresh the
  // file list rather than show stale files from the previous thread.
  function reload(opts) {
    if (!state.open) return;
    if (opts && (opts.serverUrl || opts.jwt || opts.agentName)) {
      state.refreshSeq += 1;
      state.cfg = {
        serverUrl: opts.serverUrl || (state.cfg && state.cfg.serverUrl),
        jwt: opts.jwt || (state.cfg && state.cfg.jwt),
        agentName: opts.agentName || (state.cfg && state.cfg.agentName),
      };
    }
    if (opts && opts.conversationId && opts.conversationId !== state.conversationId) {
      state.refreshSeq += 1;
      state.conversationId = opts.conversationId;
      state.items = [];
      state.tree = [];
      state.workspaceSignature = '';
      closeActiveFile();
      state.expandedFolders.clear();
      renderTree();
    }
    refresh({ silent: !!(opts && opts.silent) });
    if (opts && opts.burst) scheduleLiveRefreshBurst('conversation-reload');
  }

  async function openPath(path, opts) {
    const wanted = normalizePath(path || '');
    if (!wanted || wanted === ROOT_PATH) return;
    const nextOpts = opts || {};
    if (!state.open) {
      await open({
        serverUrl: nextOpts.serverUrl || (state.cfg && state.cfg.serverUrl),
        jwt: nextOpts.jwt || (state.cfg && state.cfg.jwt),
        agentName: nextOpts.agentName || (state.cfg && state.cfg.agentName),
        conversationId: nextOpts.conversationId || state.conversationId,
      });
    } else if (nextOpts.conversationId && nextOpts.conversationId !== state.conversationId) {
      state.refreshSeq += 1;
      state.cfg = {
        serverUrl: nextOpts.serverUrl || (state.cfg && state.cfg.serverUrl),
        jwt: nextOpts.jwt || (state.cfg && state.cfg.jwt),
        agentName: nextOpts.agentName || (state.cfg && state.cfg.agentName),
      };
      state.conversationId = nextOpts.conversationId;
      state.items = [];
      state.tree = [];
      state.workspaceSignature = '';
      closeActiveFile();
      state.expandedFolders.clear();
      await refresh({ silent: true, reason: 'open-path-conversation' });
    }
    if (!state.open) return;
    await waitForRefreshIdle();
    if (nextOpts.serverUrl || nextOpts.jwt || nextOpts.agentName) {
      state.cfg = {
        serverUrl: nextOpts.serverUrl || (state.cfg && state.cfg.serverUrl),
        jwt: nextOpts.jwt || (state.cfg && state.cfg.jwt),
        agentName: nextOpts.agentName || (state.cfg && state.cfg.agentName),
      };
    }
    let item = findItemByPath(state.items, wanted);
    if (!item) {
      await refresh({ silent: true, reason: 'open-path' });
      item = findItemByPath(state.items, wanted);
    }
    if (!item) {
      toast(`Workspace file not found: ${wanted}`, 'error');
      return;
    }
    if (item.type === 'folder') {
      state.expandedFolders.add(normalizePath(item.path));
      renderTree();
      return;
    }
    openFile(item);
  }

  // Snapshot the workspace context the chat composer should send along
  // with the next user message: the active file's path/name and any
  // editor selection. Returns null when there's nothing meaningful to
  // surface (workspace closed, or no file open).
  function getContext() {
    if (!state.open || !state.activeFile) return null;
    const ctx = {
      name: state.activeFile.name,
      path: state.activeFile.path,
      selection: null,
    };
    try {
      if (state.editor && typeof state.editor.getSelection === 'function') {
        const sel = state.editor.getSelection();
        if (sel && !sel.isEmpty()) {
          const model = state.editor.getModel();
          if (model) ctx.selection = model.getValueInRange(sel);
        }
      }
    } catch (_) { /* monaco may not be ready yet — ignore */ }
    return ctx;
  }

  // The Rust side reverts the window chrome to popover form whenever
  // it hides (`hide_popover`), then emits `popover-visible:false`.
  // Drop workspace state so the next show comes back as plain chat.
  // app.js separately resets the active sidenav view to 'chat' so the
  // body class + window-mode flag stay consistent with the chrome.
  function cleanupAfterHide() {
    if (!state.open) return;
    state.open = false;
    stopLiveRefresh();
    if (root) root.hidden = true;
    document.body.classList.remove('workspace-open');
    closeActiveFile();
    if (state.monaco && window.AgixtWorkspaceModels) {
      window.AgixtWorkspaceModels.dispose(state.monaco);
    }
    unbindKeyboard();
  }

  function eventMatchesWorkspaceConversation(detail) {
    const id = detail && (detail.conversationId || detail.conversation_id || detail.id);
    return !id || !state.conversationId || String(id) === String(state.conversationId);
  }

  window.addEventListener('agixt-chat-turn-complete', (ev) => {
    if (!eventMatchesWorkspaceConversation(ev && ev.detail)) return;
    scheduleLiveRefreshBurst('chat-turn-complete');
  });
  window.addEventListener('agixt-chat-assistant-final', (ev) => {
    if (!eventMatchesWorkspaceConversation(ev && ev.detail)) return;
    scheduleLiveRefreshBurst('chat-assistant-final');
  });
  window.addEventListener('agixt-workspace-mutated', (ev) => {
    if (!eventMatchesWorkspaceConversation(ev && ev.detail)) return;
    scheduleLiveRefresh('workspace-mutated', 0);
  });

  try {
    const ev = window.__TAURI__ && window.__TAURI__.event;
    if (ev && typeof ev.listen === 'function') {
      ev.listen('popover-visible', (msg) => {
        if (msg && msg.payload === false) cleanupAfterHide();
      });
    }
  } catch (_) { /* event API unavailable — popover lifecycle still works */ }

  window.AgixtWorkspace = { open, close, toggle, isOpen, reload, openPath, getContext };
})();

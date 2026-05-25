/* Monaco workspace model manager — port of useWorkspaceModels.ts.
 *
 * Maintains an in-memory Monaco model cache for text files in the
 * conversation workspace so cross-file features (go-to-definition,
 * find-references, workspace symbol search, TS/JS intellisense) work
 * across a useful slice of the tree without tripping Monaco's listener
 * leak guard in large workspaces.
 *
 * Loads via the AMD `vs/loader.js` already booted by workspace.js.
 *
 * Exposes window.AgixtWorkspaceModels singleton.
 */
(function () {
  const TEXT_EXTENSIONS = new Set([
    'js','jsx','ts','tsx','mjs','mts','cjs','cts',
    'py','pyw','pyi',
    'md','mdx','txt','csv','log',
    'json','jsonc','json5',
    'xml','svg',
    'html','htm','css','scss','less','sass',
    'yaml','yml','toml','ini','conf','cfg','env','properties',
    'sh','bash','zsh','fish','ps1','bat','cmd',
    'sql','graphql','gql',
    'rs','go','java','kt','scala','c','cpp','h','hpp',
    'rb','php','swift','dart','lua','r',
    'vue','svelte','tf','hcl','proto',
    'makefile','cmake','dockerfile',
  ]);

  const MONACO_LANG_MAP = {
    js:'javascript',jsx:'javascript',mjs:'javascript',cjs:'javascript',
    ts:'typescript',tsx:'typescriptreact',mts:'typescript',cts:'typescript',
    py:'python',pyw:'python',pyi:'python',
    md:'markdown',mdx:'markdown',
    json:'json',jsonc:'json',json5:'json',
    xml:'xml',svg:'xml',
    html:'html',htm:'html',
    css:'css',scss:'scss',less:'less',
    yaml:'yaml',yml:'yaml',
    toml:'ini',ini:'ini',conf:'ini',cfg:'ini',properties:'ini',
    sh:'shell',bash:'shell',zsh:'shell',fish:'shell',
    ps1:'powershell',bat:'bat',cmd:'bat',
    sql:'sql',graphql:'graphql',gql:'graphql',
    rs:'rust',go:'go',java:'java',kt:'kotlin',scala:'scala',
    c:'c',cpp:'cpp',h:'c',hpp:'cpp',
    rb:'ruby',php:'php',swift:'swift',dart:'dart',lua:'lua',r:'r',
    vue:'html',svelte:'html',
    dockerfile:'dockerfile',
    txt:'plaintext',log:'plaintext',csv:'plaintext',env:'shell',
  };

  const EXTENSIONLESS_LANG = {
    dockerfile:'dockerfile',makefile:'shell',gemfile:'ruby',
    rakefile:'ruby',procfile:'shell',vagrantfile:'ruby',
  };
  const SOURCE_EXTENSIONS = new Set([
    'js','jsx','ts','tsx','mjs','mts','cjs','cts',
    'py','pyw','pyi','rs','go','java','kt','scala','c','cpp','h','hpp',
    'rb','php','swift','dart','lua','r','vue','svelte',
  ]);
  const SUPPORT_EXTENSIONS = new Set([
    'json','jsonc','json5','xml','svg','html','htm','css','scss','less','sass',
    'yaml','yml','toml','ini','conf','cfg','env','properties',
    'sh','bash','zsh','fish','ps1','bat','cmd','sql','graphql','gql',
    'tf','hcl','proto','makefile','cmake','dockerfile',
  ]);
  const LOW_PRIORITY_EXTENSIONS = new Set(['md','mdx','txt','csv','log']);
  const MAX_WORKSPACE_MODELS = 120;

  function getMonacoLanguageForFile(name) {
    const lower = String(name).toLowerCase();
    if (!lower.includes('.') || (lower.startsWith('.') && !lower.slice(1).includes('.'))) {
      return EXTENSIONLESS_LANG[lower] || 'plaintext';
    }
    const ext = lower.split('.').pop() || '';
    return MONACO_LANG_MAP[ext] || 'plaintext';
  }

  function getFileExtension(name) {
    const lower = String(name || '').toLowerCase();
    if (!lower.includes('.') || (lower.startsWith('.') && !lower.slice(1).includes('.'))) return '';
    return lower.split('.').pop() || '';
  }

  function getModelPriority(file, activePath) {
    if (activePath && file.path === activePath) return 0;
    const lower = String(file.name || '').toLowerCase();
    const ext = getFileExtension(file.name);
    if (!ext && lower in EXTENSIONLESS_LANG) return 1;
    if (SOURCE_EXTENSIONS.has(ext)) return 1;
    if (SUPPORT_EXTENSIONS.has(ext)) return 2;
    if (LOW_PRIORITY_EXTENSIONS.has(ext)) return 4;
    return 3;
  }

  function selectModelFiles(files, activePath) {
    return [...files]
      .sort((a, b) => {
        const priority = getModelPriority(a, activePath) - getModelPriority(b, activePath);
        if (priority) return priority;
        const depth = String(a.path || '').split('/').length - String(b.path || '').split('/').length;
        if (depth) return depth;
        return String(a.path || '').localeCompare(String(b.path || ''));
      })
      .slice(0, MAX_WORKSPACE_MODELS);
  }

  function isTextFile(name) {
    const lower = String(name).toLowerCase();
    if (!lower.includes('.') || (lower.startsWith('.') && !lower.slice(1).includes('.'))) {
      return lower in EXTENSIONLESS_LANG || lower.startsWith('.');
    }
    const ext = lower.split('.').pop() || '';
    return TEXT_EXTENSIONS.has(ext);
  }

  function collectTextFiles(items) {
    const byPath = new Map();
    function walk(list) {
      for (const item of list || []) {
        if (item.type === 'file' && isTextFile(item.name)) {
          const path = String(item.path || '');
          if (path && !byPath.has(path)) byPath.set(path, { path, name: item.name });
        }
        if (item.children && item.children.length) walk(item.children);
      }
    }
    walk(items);
    return Array.from(byPath.values());
  }

  // --- Singleton state -----------------------------------------------
  const loadedPaths = new Set();
  let tsConfigured = false;
  let providersRegistered = false;
  const providerDisposables = [];
  let activeConversationId = null;
  let loading = false;
  let queuedLoad = null;
  let loadVersion = 0;

  function configureTypeScriptDefaults(monaco) {
    if (tsConfigured) return;
    tsConfigured = true;
    const ts = monaco.languages.typescript;
    if (!ts) return;
    const compilerOptions = {
      target: ts.ScriptTarget.ESNext,
      module: ts.ModuleKind.ESNext,
      moduleResolution: ts.ModuleResolutionKind.NodeJs,
      jsx: ts.JsxEmit.ReactJSX,
      allowJs: true, checkJs: false, strict: false,
      esModuleInterop: true, allowSyntheticDefaultImports: true,
      resolveJsonModule: true, skipLibCheck: true, noEmit: true,
      baseUrl: '.', paths: { '@/*': ['./*'] },
    };
    ts.typescriptDefaults.setCompilerOptions(compilerOptions);
    ts.javascriptDefaults.setCompilerOptions(compilerOptions);
    ts.typescriptDefaults.setEagerModelSync(true);
    ts.javascriptDefaults.setEagerModelSync(true);
    ts.typescriptDefaults.setDiagnosticsOptions({ noSemanticValidation: true, noSyntaxValidation: false });
    ts.javascriptDefaults.setDiagnosticsOptions({ noSemanticValidation: true, noSyntaxValidation: false });
  }

  function escapeRegex(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  function buildDefinitionPatterns(symbol, lang) {
    const e = escapeRegex(symbol);
    if (lang === 'python') return [`^\\s*def\\s+${e}\\s*\\(`, `^\\s*class\\s+${e}[\\s:(]`, `^\\s*${e}\\s*=`, `^\\s*async\\s+def\\s+${e}\\s*\\(`];
    if (lang === 'rust') return [`\\bfn\\s+${e}\\s*[<(]`, `\\bstruct\\s+${e}\\b`, `\\benum\\s+${e}\\b`, `\\btrait\\s+${e}\\b`, `\\bimpl\\s+${e}\\b`, `\\btype\\s+${e}\\b`, `\\bmod\\s+${e}\\b`, `\\bconst\\s+${e}\\b`, `\\bstatic\\s+${e}\\b`];
    if (lang === 'go') return [`\\bfunc\\s+${e}\\s*\\(`, `\\bfunc\\s+\\([^)]+\\)\\s+${e}`, `\\btype\\s+${e}\\b`, `\\bvar\\s+${e}\\b`, `\\bconst\\s+${e}\\b`];
    if (lang === 'ruby') return [`\\bdef\\s+${e}\\b`, `\\bclass\\s+${e}\\b`, `\\bmodule\\s+${e}\\b`];
    if (lang === 'php') return [`\\bfunction\\s+${e}\\s*\\(`, `\\bclass\\s+${e}\\b`, `\\binterface\\s+${e}\\b`, `\\btrait\\s+${e}\\b`];
    if (lang === 'c' || lang === 'cpp') return [`\\b\\w[\\w\\s*&]+\\s+${e}\\s*\\(`, `\\bstruct\\s+${e}\\b`, `\\bclass\\s+${e}\\b`, `\\benum\\s+${e}\\b`, `\\btypedef\\s+.*\\s+${e}\\s*;`, `#define\\s+${e}\\b`];
    if (lang === 'java' || lang === 'kotlin' || lang === 'scala') return [`\\b(public|private|protected|static|abstract|final|open|internal)?\\s*(fun|def|void|int|String|boolean|class|interface|enum|object|data class|sealed class|abstract class)\\s+${e}\\b`];
    return [`\\bfunction\\s+${e}\\s*\\(`, `\\bclass\\s+${e}\\b`, `\\bdef\\s+${e}\\b`, `\\bconst\\s+${e}\\b`, `\\blet\\s+${e}\\b`, `\\bvar\\s+${e}\\b`];
  }

  function getSymbolPatterns(lang) {
    if (lang === 'python') return [
      { regex: '^\\s*(async\\s+)?def\\s+\\w+', nameExtractor: /(?:async\s+)?def\s+(\w+)/, kind: 11 },
      { regex: '^\\s*class\\s+\\w+', nameExtractor: /class\s+(\w+)/, kind: 4 },
    ];
    if (lang === 'rust') return [
      { regex: '\\bfn\\s+\\w+', nameExtractor: /fn\s+(\w+)/, kind: 11 },
      { regex: '\\bstruct\\s+\\w+', nameExtractor: /struct\s+(\w+)/, kind: 22 },
      { regex: '\\benum\\s+\\w+', nameExtractor: /enum\s+(\w+)/, kind: 9 },
      { regex: '\\btrait\\s+\\w+', nameExtractor: /trait\s+(\w+)/, kind: 10 },
    ];
    if (lang === 'go') return [
      { regex: '\\bfunc\\s+\\w+', nameExtractor: /func\s+(\w+)/, kind: 11 },
      { regex: '\\btype\\s+\\w+', nameExtractor: /type\s+(\w+)/, kind: 4 },
    ];
    return [
      { regex: '\\bfunction\\s+\\w+', nameExtractor: /function\s+(\w+)/, kind: 11 },
      { regex: '\\bclass\\s+\\w+', nameExtractor: /class\s+(\w+)/, kind: 4 },
      { regex: '\\bdef\\s+\\w+', nameExtractor: /def\s+(\w+)/, kind: 11 },
    ];
  }

  function registerCrossFileProviders(monaco) {
    if (providersRegistered) return;
    providersRegistered = true;
    const targetLanguages = ['python','rust','go','ruby','php','c','cpp','java','kotlin','scala','shell','plaintext'];
    for (const lang of targetLanguages) {
      providerDisposables.push(monaco.languages.registerDefinitionProvider(lang, {
        provideDefinition(model, position) {
          const word = model.getWordAtPosition(position);
          if (!word || word.word.length < 2) return null;
          const symbol = word.word;
          const results = [];
          const patterns = buildDefinitionPatterns(symbol, lang);
          for (const m of monaco.editor.getModels()) {
            if (m.isDisposed()) continue;
            for (const pattern of patterns) {
              const matches = m.findMatches(pattern, false, true, true, null, true);
              for (const match of matches) {
                if (m.uri.toString() === model.uri.toString() && match.range.startLineNumber === position.lineNumber) continue;
                results.push({ uri: m.uri, range: match.range });
              }
            }
          }
          return results.length ? results : null;
        },
      }));
      providerDisposables.push(monaco.languages.registerReferenceProvider(lang, {
        provideReferences(model, position, context) {
          const word = model.getWordAtPosition(position);
          if (!word || word.word.length < 2) return null;
          const symbol = word.word;
          const results = [];
          for (const m of monaco.editor.getModels()) {
            if (m.isDisposed()) continue;
            const pattern = `\\b${escapeRegex(symbol)}\\b`;
            const matches = m.findMatches(pattern, false, true, true, null, true);
            for (const match of matches) {
              if (!context.includeDeclaration &&
                  m.uri.toString() === model.uri.toString() &&
                  match.range.startLineNumber === position.lineNumber &&
                  match.range.startColumn === word.startColumn) continue;
              results.push({ uri: m.uri, range: match.range });
            }
          }
          return results.length ? results : null;
        },
      }));
      providerDisposables.push(monaco.languages.registerDocumentSymbolProvider(lang, {
        provideDocumentSymbols(model) {
          const symbols = [];
          for (const pattern of getSymbolPatterns(lang)) {
            const matches = model.findMatches(pattern.regex, false, true, true, null, true);
            for (const match of matches) {
              const lineContent = model.getLineContent(match.range.startLineNumber);
              const nameMatch = lineContent.match(pattern.nameExtractor);
              if (nameMatch) {
                symbols.push({
                  name: nameMatch[1], kind: pattern.kind,
                  range: match.range, selectionRange: match.range,
                  detail: '', tags: [],
                });
              }
            }
          }
          return symbols;
        },
      }));
    }
  }

  /** Initialise providers/TS defaults — cheap, called eagerly. */
  function init(monaco) {
    configureTypeScriptDefaults(monaco);
    registerCrossFileProviders(monaco);
  }

  function disposeLoadedModels(monaco) {
    if (monaco) {
      for (const path of Array.from(loadedPaths)) {
        const uri = monaco.Uri.parse(`file://${path}`);
        const m = monaco.editor.getModel(uri);
        if (m) m.dispose();
      }
    }
    loadedPaths.clear();
  }

  async function loadModelsForRequest(request) {
    const { monaco, api, cfg, conversationId, items, activePath } = request;
    if (!monaco || !api || !conversationId) return;

    // If conversation changed, drop existing models so they don't leak.
    if (activeConversationId && activeConversationId !== conversationId) {
      disposeLoadedModels(monaco);
      loadVersion += 1;
    }
    activeConversationId = conversationId;
    const version = loadVersion;

    const textFiles = collectTextFiles(items);
    const modelFiles = selectModelFiles(textFiles, activePath);
    const managedPaths = new Set(modelFiles.map((f) => f.path));

    // Keep Monaco comfortably below its listener leak threshold. The active
    // editor model is created by workspace.js even if it falls outside this
    // background cache.
    for (const path of Array.from(loadedPaths)) {
      if (!managedPaths.has(path)) {
        const uri = monaco.Uri.parse(`file://${path}`);
        const m = monaco.editor.getModel(uri);
        if (m) m.dispose();
        loadedPaths.delete(path);
      }
    }

    const toLoad = modelFiles.filter((f) => !loadedPaths.has(f.path));

    const BATCH = 2;
    for (let i = 0; i < toLoad.length; i += BATCH) {
      if (version !== loadVersion || activeConversationId !== conversationId) return;
      const batch = toLoad.slice(i, i + BATCH);
      const results = await Promise.allSettled(batch.map(async (f) => {
        try {
          const result = await api.downloadFile(cfg, conversationId, f.path);
          if (!result) return null;
          return { path: f.path, name: f.name, text: await result.blob.text() };
        } catch { return null; }
      }));
      if (version !== loadVersion || activeConversationId !== conversationId) return;
      for (const r of results) {
        if (r.status !== 'fulfilled' || !r.value) continue;
        const { path, name, text } = r.value;
        const uri = monaco.Uri.parse(`file://${path}`);
        const existing = monaco.editor.getModel(uri);
        if (existing) {
          if (existing.getValue() !== text) existing.setValue(text);
        } else {
          monaco.editor.createModel(text, getMonacoLanguageForFile(name), uri);
        }
        loadedPaths.add(path);
      }
      // Yield to UI thread between batches.
      if (i + BATCH < toLoad.length) {
        await new Promise((res) => {
          if (typeof requestIdleCallback !== 'undefined') requestIdleCallback(() => res(), { timeout: 200 });
          else setTimeout(res, 50);
        });
      }
    }

    // Prune models for files that no longer exist.
    for (const path of Array.from(loadedPaths)) {
      if (!managedPaths.has(path)) {
        const uri = monaco.Uri.parse(`file://${path}`);
        const m = monaco.editor.getModel(uri);
        if (m) m.dispose();
        loadedPaths.delete(path);
      }
    }
  }

  /** Load bounded text-file models for the current workspace. */
  async function ensureModelsLoaded(monaco, api, cfg, conversationId, items, opts) {
    const request = {
      monaco, api, cfg, conversationId, items,
      activePath: opts && opts.activePath ? opts.activePath : null,
    };
    if (loading) {
      queuedLoad = request;
      return;
    }
    loading = true;
    try {
      let current = request;
      while (current) {
        queuedLoad = null;
        await loadModelsForRequest(current);
        current = queuedLoad;
      }
    } finally {
      loading = false;
    }
  }

  /** Update a single model when the user edits content. */
  function updateModel(monaco, filePath, content) {
    if (!monaco) return;
    const uri = monaco.Uri.parse(`file://${filePath}`);
    const model = monaco.editor.getModel(uri);
    if (model && model.getValue() !== content) model.setValue(content);
  }

  /** Tear down everything (called when workspace closes / convo switches). */
  function dispose(monaco) {
    loadVersion += 1;
    queuedLoad = null;
    for (const d of providerDisposables) { try { d.dispose(); } catch {} }
    providerDisposables.length = 0;
    providersRegistered = false;
    disposeLoadedModels(monaco);
    activeConversationId = null;
  }

  window.AgixtWorkspaceModels = {
    isTextFile,
    getMonacoLanguageForFile,
    init,
    ensureModelsLoaded,
    updateModel,
    dispose,
  };
})();

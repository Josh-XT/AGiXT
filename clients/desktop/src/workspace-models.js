/* Monaco workspace model manager — port of useWorkspaceModels.ts.
 *
 * Maintains an in-memory Monaco model for every text file in the
 * conversation workspace so cross-file features (go-to-definition,
 * find-references, workspace symbol search, TS/JS intellisense) work
 * across the whole tree.
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

  function getMonacoLanguageForFile(name) {
    const lower = String(name).toLowerCase();
    if (!lower.includes('.') || (lower.startsWith('.') && !lower.slice(1).includes('.'))) {
      return EXTENSIONLESS_LANG[lower] || 'plaintext';
    }
    const ext = lower.split('.').pop() || '';
    return MONACO_LANG_MAP[ext] || 'plaintext';
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
    const out = [];
    function walk(list) {
      for (const item of list || []) {
        if (item.type === 'file' && isTextFile(item.name)) {
          out.push({ path: item.path, name: item.name });
        }
        if (item.children && item.children.length) walk(item.children);
      }
    }
    walk(items);
    return out;
  }

  // --- Singleton state -----------------------------------------------
  const loadedPaths = new Set();
  let tsConfigured = false;
  let providersRegistered = false;
  const providerDisposables = [];
  let activeConversationId = null;
  let loading = false;

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

  /** Load all text-file models for the current workspace. */
  async function ensureModelsLoaded(monaco, api, cfg, conversationId, items) {
    if (loading) return;
    loading = true;
    try {
      // If conversation changed, drop existing models so they don't leak.
      if (activeConversationId && activeConversationId !== conversationId) {
        for (const path of loadedPaths) {
          const uri = monaco.Uri.parse(`file://${path}`);
          const model = monaco.editor.getModel(uri);
          if (model) model.dispose();
        }
        loadedPaths.clear();
      }
      activeConversationId = conversationId;

      const textFiles = collectTextFiles(items);
      const toLoad = textFiles.filter((f) => !loadedPaths.has(f.path));

      const BATCH = 2;
      for (let i = 0; i < toLoad.length; i += BATCH) {
        const batch = toLoad.slice(i, i + BATCH);
        const results = await Promise.allSettled(batch.map(async (f) => {
          try {
            const result = await api.downloadFile(cfg, conversationId, f.path);
            if (!result) return null;
            return { path: f.path, name: f.name, text: await result.blob.text() };
          } catch { return null; }
        }));
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
      const current = new Set(textFiles.map((f) => f.path));
      for (const path of Array.from(loadedPaths)) {
        if (!current.has(path)) {
          const uri = monaco.Uri.parse(`file://${path}`);
          const m = monaco.editor.getModel(uri);
          if (m) m.dispose();
          loadedPaths.delete(path);
        }
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
    for (const d of providerDisposables) { try { d.dispose(); } catch {} }
    providerDisposables.length = 0;
    providersRegistered = false;
    if (monaco) {
      for (const path of loadedPaths) {
        const uri = monaco.Uri.parse(`file://${path}`);
        const m = monaco.editor.getModel(uri);
        if (m) m.dispose();
      }
    }
    loadedPaths.clear();
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

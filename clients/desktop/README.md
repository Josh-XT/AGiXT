# AGiXT Desktop

A native desktop AGiXT client written in Rust (Tauri 2). It runs as a
tray-anchored sidebar popover with rich activity grouping, voice input,
file attachments, and direct desktop control so the agent can drive the
machine it's running on.

The chat layer talks two AGiXT protocols at once:

* **`/v1/chat/completions`** (SSE) for the active turn — streams text
  deltas, AGiXT-native `remote_command.request` tool calls, and
  `activity.stream` thinking deltas. Implementation in
  [`src-tauri/src/chat_stream.rs`](src-tauri/src/chat_stream.rs).
* **`/v1/conversation/{id}/stream`** (WebSocket) for the persisted
  conversation log — same envelope the web client consumes, so
  `[ACTIVITY]` / `[SUBACTIVITY]` markers render as collapsible
  thinking/action groups. Implementation in
  [`src/chat.js`](src/chat.js).

Markdown bodies render with first-class support for inline images,
audio, and video. Workspace media URLs (`/outputs/...`,
`/api/workspace/...`) get the user's JWT auto-appended as `?auth=<jwt>`
so they actually load — same trick the web's
`/api/workspace/[...path]` proxy uses.

## Layout

```
clients/desktop/
├── README.md
├── src/                       # Frontend (HTML/JS/CSS, no build step)
│   ├── index.html             # Sidebar shell
│   ├── toggle.html            # Floating chat-bubble window
│   ├── styles.css
│   ├── app.js                 # Boot, settings, agent/convo switchers, composer
│   ├── auth.js                # OAuth / password / magic-link / register / paste-token
│   ├── chat.js                # WebSocket + SSE chat client + activity grouping
│   ├── markdown.js            # Markdown → HTML (with media + workspace JWT rewrite)
│   ├── audio.js               # TTS audio queue
│   ├── client-actions.js      # Browser-side dispatch into Rust IPC tools
│   ├── context-menu.js        # Custom right-click menu (no Inspect)
│   ├── frontend-log.js        # Forwards renderer console to Rust tracing
│   ├── dock.js                # Sidebar/popover dock-mode controller
│   └── assets/brands/         # Per-brand SVG logos
└── src-tauri/                 # Rust backend
    ├── Cargo.toml
    ├── tauri.conf.json
    ├── capabilities/default.json
    ├── icons/
    └── src/
        ├── main.rs
        ├── lib.rs                  # Tauri setup, IPC handlers (~58 commands)
        ├── config.rs               # SQLite-backed settings + service brands
        ├── chat_stream.rs          # SSE parser for /v1/chat/completions
        ├── api.rs                  # AGiXT REST helpers (auth, conversations, workspace)
        ├── automation.rs           # Screenshot / mouse / keyboard
        ├── filesystem.rs           # fs_read/write/append/edit/list/stat/...
        ├── terminal.rs             # PTY sessions + shell_run + sudo helpers
        ├── client_tool_specs.rs    # OpenAI-shaped tool definitions for /v1/chat/completions
        └── client_tools_prompt.rs  # Prompt fragment describing the tool surface
```

## Local state

Settings persist to a small SQLite DB:

| OS      | Path                                                  |
| ------- | ----------------------------------------------------- |
| Linux   | `~/.config/agixt-desktop/settings.db`                 |
| macOS   | `~/Library/Application Support/agixt-desktop/...`     |
| Windows | `%LOCALAPPDATA%\agixt-desktop\settings.db`            |

Stored: server URL, web URL, JWT, service brand slug, selected agent +
company, current conversation id + name, voice toggle, sidebar
visibility, dock mode, dock position, "allow client commands" flag.

## Build prerequisites

### All platforms

* Rust 1.77+ (`rustup default stable`)
* `cargo install tauri-cli@^2` (only needed if you want
  `cargo tauri dev` / `cargo tauri build`; otherwise plain
  `cargo run` / `cargo build --release` from `src-tauri/` works).

### Linux (Ubuntu / Debian)

```bash
sudo apt-get install -y \
  libwebkit2gtk-4.1-dev \
  libsoup-3.0-dev \
  libjavascriptcoregtk-4.1-dev \
  librsvg2-dev \
  libxdo-dev \
  libgtk-3-dev \
  libayatana-appindicator3-dev
```

### macOS

Xcode command-line tools (`xcode-select --install`). Grant Screen
Recording, Accessibility, *and* Microphone permissions to the built app
the first time you use the desktop-control tools or the mic.

### Windows

WebView2 is bundled with modern Windows; no extra setup.

### Windows signing for release downloads

Windows release artifacts should be Authenticode signed before upload. The
`desktop-prewarm.yml` workflow builds the Windows binary without bundling,
signs `agixt-desktop.exe`, bundles the installer, signs the installer, and
verifies the selected artifact with `Get-AuthenticodeSignature` when signing is
available.

Use one signing path:

* Azure Artifact Signing: set repository variables
  `AGIXT_WINDOWS_ARTIFACT_SIGNING_ENDPOINT`,
  `AGIXT_WINDOWS_ARTIFACT_SIGNING_ACCOUNT`, and
  `AGIXT_WINDOWS_ARTIFACT_SIGNING_CERTIFICATE_PROFILE`; set Azure auth secrets
  `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET`.
* PFX/Authenticode certificate: set secrets `WINDOWS_CERTIFICATE_BASE64` and
  `WINDOWS_CERTIFICATE_PASSWORD`, or set `WINDOWS_CERTIFICATE_THUMBPRINT` when
  the cert is already installed on the Windows runner.

`AGIXT_WINDOWS_SIGNING_REQUIRED` defaults to `false` so Windows builds can
continue while Azure identity validation or credentials are still pending. Set
it to `true` after signing is configured to prevent unsigned Windows artifacts
from being uploaded.

## Run

```bash
cd src-tauri
cargo run               # debug build
```

Release build:

```bash
cd src-tauri
cargo tauri build       # if tauri-cli is installed (recommended)
# or
cargo build --release   # produces target/release/agixt-desktop
```

When AGiXT is started with `agixt start` or `agixt restart`, the CLI
checks for an installed AGiXT Desktop app on machines with a graphical
desktop session. If it is missing, the CLI downloads the prebuilt app
for the current OS from `https://d.devxt.com/desktop/{os}` and launches
it instead of building locally. It skips CI/headless terminal-only
environments and can be disabled with `AGIXT_DESKTOP_INSTALL=false`.
Set `AGIXT_DESKTOP_DOWNLOAD_BASE_URL` to point at a different download
server.

Set `RUST_LOG=info,agixt_desktop_lib=debug` for verbose logging.
Frontend `console.log` is forwarded to the same Rust tracing log via
the `frontend_log` IPC, so you only need to watch one stream.

## Development note: rebuild for frontend changes

`tauri.conf.json` sets `frontendDist: "../src"` and `devUrl: null`,
which means **Tauri embeds the HTML/JS/CSS into the Rust binary at
build time**. Editing `src/*.js` or `src/styles.css` and just
re-launching the binary will not pick up the changes — `cargo build`
first to re-embed, then relaunch. The sidebar logs
`chat.js loaded (<version-tag>)` on every webview load so you can
confirm the new bundle is live.

The webkit2gtk webview also caches at
`~/.local/share/systems.xt.agixt.desktop/{WebKitCache,CacheStorage}`;
clear those if a stale CSS/JS asset persists past a rebuild.

## First run / sign-in

The auth screen offers four ways to sign in, plus account creation. No
copy-pasting JWTs unless you specifically want to.

1. **Pick a service brand**. The dropdown lists AGiXT.com, NurseXT.com,
   XT.Systems, BoltRemote.com, Local, and Custom. Picking one fills the
   API + Web URL fields with that brand's defaults; the topbar logo
   swaps to the brand's mark; the brand persists across restarts (OAuth
   users included — the brand is written before the browser opens).
   * **Local** pins to `http://localhost:7437`, probes `/health` and
     `/openapi.json`, and shows a connect state if AGiXT is already up.
     If nothing is running, the login screen can install locally:
     `git clone`/`git pull` Josh-XT/AGiXT, `pip install -e .`,
     `pip install ezlocalai`, pre-configure `.env`, then run
     `python -m agixt.cli restart`.
   * The local installer recommends ezLocalai defaults from hardware:
     `<12GB` VRAM → `unsloth/Qwen3.5-4B-GGUF`, `13GB+` below the
     24GB high tier → `unsloth/Qwen3.5-9B-GGUF`, `24GB+` VRAM →
     `unsloth/Qwen3.6-35B-A3B-GGUF`. CPU-only systems use the 4B
     model; constrained RAM gets a smaller max-token default and a
     performance warning. First setup can take 30+ minutes because
     Docker images and models may download.
   * **Custom** keeps the API + Web URL fields editable for any other
     self-hosted AGiXT.
2. **Sign in** any of:
   * **Email + password** (with optional MFA prompt)
   * **OAuth** — buttons for whatever providers AGiXT exposes for the
     selected brand. Click → system browser opens → after consent the
     server redirects to `agixt://login?token=<jwt>` which the desktop
     deep-link handler validates and unlocks the chat.
   * **Magic link** — type your email, click the button, click the
     link in your inbox. The link's `?jwt=` redirects through the same
     `agixt://` deep link.
   * **Paste a JWT or magic-link URL** — fallback for bespoke flows.
3. **Register** a new account from the second tab (first/last name,
   email, password meeting AGiXT's complexity rules).

After auth: the sidebar refreshes companies + agents, picks the user's
default agent, opens (or restores) a conversation, opens the
`/v1/conversation/{id}/stream` WebSocket, and is ready to chat.

A global shortcut **`Ctrl+Shift+Space`** (or `Cmd+Shift+Space` on
macOS) toggles the sidebar in/out. The tray icon does the same.

## The chat surface

* **Topbar** — brand logo on the left (with a small connection-state
  dot overlay when disconnected/error), then a stacked chip pair: the
  agent switcher (`Agent @ Company`) on top with settings + close
  buttons, and the conversation switcher (with chat-bubble icon) below
  it with the new-conversation button. The conversation chip is fully
  searchable via a small search field at the top of its dropdown.
* **Composer** — paperclip (file attachment), text area with a
  dynamic `Ask {agent_name}…` placeholder, mic, and send/stop. The
  input area is right-clickable for cut/copy/paste/select-all.
* **Stop button** swaps in for send while the agent is generating.
  Click stops both sides: detaches the SSE listener locally so further
  events are dropped, halts the local tool-execution recursion via a
  sticky `turnStopped` flag, and POSTs to
  `/v1/conversation/{id}/stop` (with `/v1/conversations/stop` as a
  belt-and-suspenders fallback) — same flow the web client uses.

### Activity rendering

Mirrors the web's `useConversationWebSocketStable.ts` `groupMessages()`:

* `[SUBACTIVITY]` markers attach to the parent `[ACTIVITY]` (by UUID
  if referenced, else the most recent activity). Orphans get a
  synthetic `Thinking` parent.
* Consecutive `Thinking` activities merge into one block instead of
  opening a new one for each.
* Each tool call (CLIENT_TOOL + its REMOTE / untagged follow-ups —
  request queued, completed, received result, uploaded, processed)
  collapses into one `▸ Called <tool>` disclosure. Click to expand
  for the request payload and full transport detail.
* Once the assistant's text reply lands, the activity block is
  relabeled `Activities`, its spinner stops, and it auto-collapses.
  Still openable on click.
* Live thinking from `activity.stream` events accumulates as a
  rolling cumulative subactivity inside the open Thinking block (each
  event is a token-level **delta**, not a replacement — see
  `AGiXT/agixt/Interactions.py:4480`).
* Workspace image URLs auto-rewrite to `?auth=<jwt>` regardless of
  host, so AGiXT-served screenshots and uploads render inline.

### Right-click

Custom menu (the default webkit2gtk Inspect menu is suppressed):

* On a message bubble: `Copy message`, `Copy selection`, and
  `Copy link address` when right-clicking a link.
* In the composer: `Cut`, `Copy`, `Paste`, `Select all`.
* Anywhere else: nothing — just dismisses any open menu.

### Hover timestamps

Each message has a small timestamp pinned to its bubble that fades in
on hover; the tooltip shows the full date down to milliseconds so it's
easy to gauge response latency.

### Voice input (mic button)

Tap to record, tap again to stop. The captured audio
(`audio/webm;codecs=opus` if the platform supports it, else next best)
is POSTed as multipart to `${server}/v1/audio/transcriptions` with
`model={agent_name}` — the OpenAI-compatible endpoint AGiXT exposes —
and the returned text is fed through the normal compose path. **Esc**
cancels an in-progress recording without sending.

### File attachments (paperclip)

The paperclip opens an OS file picker (`tauri-plugin-dialog`). Selected
paths show as removable chips above the textarea. **They aren't
uploaded**: on send, a context block is prepended to the prompt:

> The user has attached the following file(s) from their local desktop
> to this message. These paths are on the user's machine — not in the
> AGiXT workspace. Use the desktop tools (fs_read, fs_list, shell_run,
> workspace_upload, etc.) to inspect, read, or otherwise interact…
>
> - /home/josh/notes.md

…signaling the agent to reach for `fs_read`, `shell_run`,
`workspace_upload`, etc. through the IPC tool surface.

## Client-side desktop control

When the model emits a tool call (either OpenAI-shaped via
`/v1/chat/completions`, or AGiXT-native as `remote_command.request` /
`[SUBACTIVITY][CLIENT_TOOL]`), the client dispatches it to a Rust IPC
handler. After execution the result is posted back via
`POST /v1/conversation/{id}/remote-command-result` (mirroring the kids
app pattern) and the next chat-completion round receives the
corresponding `role:"tool"` message.

Disable client-side commands at any time from the settings modal —
every IPC handler checks `allow_client_commands` before doing anything.

### Vision / direct input

| Tool name                                 | Args                                     |
| ----------------------------------------- | ---------------------------------------- |
| `desktop_screenshot` / `take_screenshot`  | `monitor_index?`, `target_width?`, `target_height?` → `{ image_data (base64 jpeg), width, height, original_*, monitor_offset_*, monitor_index }` |
| `desktop_click` / `mouse_click`           | `x`, `y`, `button` (`left`/`right`/`middle`), `click_type` (`single`/`double`), vision-coord fields |
| `desktop_move` / `mouse_move`             | `x`, `y`, vision-coord fields            |
| `desktop_drag` / `mouse_drag` / `drag`    | `from_x`, `from_y`, `to_x`, `to_y`, `button?`, vision-coord fields |
| `desktop_scroll` / `scroll`               | `amount`, `axis` (`vertical`/`horizontal`) |
| `desktop_type` / `keyboard_input`         | `text` *or* `keys: [..]`                 |
| `agent_vision`                            | Asks the configured agent's vision model whether something is visible on screen — used by the live-tests as a screenshot oracle |

### Shell

`shell_run` is the one-shot equivalent of `terminal_exec` for a fresh
shell, plus an optional `sudo` ladder for password-gated commands.

| Tool name                                 | Args                                     |
| ----------------------------------------- | ---------------------------------------- |
| `shell_run`                               | `command`, `cwd?`, `shell?`, `timeout_ms?` → `{ stdout, stderr, exit_code, timed_out }` |
| `sudo_status`                             | — → `{ unlocked, expires_at }` |
| `sudo_auth`                               | `password` → `SudoStatus` (cached for 15 min) |
| `sudo_clear`                              | — clears the cached sudo password |
| `sudo_run`                                | `command`, `cwd?`, `timeout_ms?` — uses the cached password |

### Background terminal sessions

Each terminal is a `portable-pty` shell with its own dedicated reader
thread filling a 1 MiB ring buffer, so the agent can run multiple
long-lived shells concurrently and poll their output incrementally
using the monotonic `next_offset` returned by `terminal_exec` /
`terminal_read`. PTY size is adjustable on the fly via
`terminal_resize`.

| Tool name                                 | Args                                     |
| ----------------------------------------- | ---------------------------------------- |
| `terminal_open` / `open_terminal`         | `shell?`, `cwd?`, `cols?`, `rows?` → `{ id, shell, cwd, cols, rows, ... }` |
| `terminal_list` / `list_terminals`        | — → `[ SessionInfo, … ]`                 |
| `terminal_exec` / `shell_exec`            | `session_id`, `command`, `idle_ms?`, `timeout_ms?` → `{ data, next_offset, closed, timed_out }` |
| `terminal_send_input`                     | `session_id`, `data` *(raw bytes, no implicit newline)* |
| `terminal_read`                           | `session_id`, `offset?` → `{ data, next_offset, closed }` |
| `terminal_resize`                         | `session_id`, `cols`, `rows`             |
| `terminal_signal`                         | `session_id`, `signal` (`ctrl-c`/`ctrl-d`/`ctrl-z`/`ctrl-\\`) |
| `terminal_close` / `close_terminal`       | `session_id`                             |

### Local filesystem

Paths support `~`, `$VAR`, and `%VAR%` expansion so the agent can use
the same paths a human would type. Writes are atomic (write-tempfile-
then-rename in the same directory) and `fs_edit` mirrors the AGiXT
`Edit` tool semantics (unique-substring find/replace; require
`replace_all` for ambiguous matches).

| Tool name                                 | Args                                     |
| ----------------------------------------- | ---------------------------------------- |
| `fs_read` / `read_file`                   | `path` → `{ content, encoding ("utf8"/"base64"), size, truncated }` |
| `fs_write` / `write_file`                 | `path`, `content`, `encoding?`, `create_dirs?` → `{ bytes_written, created }` |
| `fs_append` / `append_file`               | `path`, `content`, `encoding?`           |
| `fs_edit` / `edit_file`                   | `path`, `edits: [{find, replace, replace_all?}]` |
| `fs_list` / `ls`                          | `path` → `[{ name, path, kind, size, modified_unix, readonly }, …]` |
| `fs_stat` / `stat_file`                   | `path` → `{ exists, kind, size, modified_unix, readonly }` |
| `fs_mkdir` / `mkdir`                      | `path`, `parents?: true`                 |
| `fs_delete` / `rm`                        | `path`, `recursive?`                     |
| `fs_rename` / `mv`                        | `from`, `to`, `overwrite?`               |

### Workspace bridge — local disk ↔ AGiXT cloud workspace

Files in the AGiXT conversation workspace travel with the conversation
across devices. Use the bridge to pull a file off the user's disk, work
on it in the agent's sandbox, then push it back; or vice versa.

| Tool name                                 | Args                                     |
| ----------------------------------------- | ---------------------------------------- |
| `workspace_upload`                        | `local_path`, `workspace_path?` → `{ bytes, server_response }` |
| `workspace_download`                      | `workspace_path`, `local_path`, `overwrite?` → `{ bytes }` |
| `workspace_list`                          | `sub_path?` → `[ WorkspaceItem, … ]`     |

## Notes

* **Cross-platform**: every client tool is implemented in pure Rust
  against cross-platform crates (`enigo`, `screenshots`,
  `portable-pty`, `std::fs`) so the same binary builds and runs on
  Linux, macOS, and Windows. The Tauri 2 webview shell, the SQLite
  settings DB, and the AGiXT REST/SSE/WS clients all behave
  identically across the three.
* **Cloud-resident state**: JWT, agent/company selection, conversation
  history, persisted activities, and any files the agent stages all
  live on the AGiXT server. The local SQLite DB only caches the JWT,
  brand, and last-selected ids so re-auth isn't needed on relaunch.
  Sign in on a different device and you pick up where you left off.
* **Vision math parity**: the `normalized` / `target_width` /
  `screen_width` / `monitor_offset_*` math in
  `automation::resolve_coords` is bit-for-bit identical to
  `rust_endpoint_agent/src/terminal.rs`. A model trained against one
  works against the other.
* **Atomic writes**: `fs_write` and `fs_edit` write to a temp file in
  the destination directory and rename — no partial writes on crash.
* **WebSocket keepalive**: the chat WS sends a `ping` envelope every
  30s to survive Cloudflare; reconnect with exponential backoff up to
  30s.
* **Voice replies**: when the assistant message contains an audio URL
  AGiXT emitted, `audio.js` plays them back-to-back from a single
  `<audio>` element. Browser autoplay policies are largely a non-issue
  inside the Tauri webview because the user clicked something to
  start the session.
* **Linux input**: cross-platform input automation comes through
  `enigo` 0.2 + `screenshots` 0.8 — the same crates `rust_endpoint_agent`
  uses. On X11 a brief 2 ms warp delay is inserted before each click.
  Wayland portal fallbacks aren't ported because this client always
  runs in the user's session, never as a system service.

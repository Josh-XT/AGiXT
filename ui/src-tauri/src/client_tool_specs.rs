//! OpenAI-format function definitions for this client's tools.
//!
//! When passed as `prompt_args.command_overrides`, AGiXT registers each
//! one as a pseudo-command the agent can call via
//! `<execute><name>shell_run</name>...</execute>`. AGiXT detects these
//! as client-side tools (because they live in `_client_tools` rather
//! than the regular extension registry) and emits a
//! `[SUBACTIVITY][CLIENT_TOOL]` log entry containing the JSON args plus
//! a `request_id`. The desktop chat stream forwards that request to
//! `clientActions.execute`, then continues `/v1/chat/completions` with the
//! matching `role: "tool"` result.
//!
//! Keep this file in sync with the actual IPC handlers in `lib.rs` and
//! the documentation in `client_tools_prompt.rs`. If the model calls a
//! tool we registered here but the IPC handler is missing, the chip in
//! chat.js will surface the dispatcher's error.

use serde_json::{json, Value};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ClientPlatform {
    Desktop,
    Android,
    Ios,
}

pub fn current_platform() -> ClientPlatform {
    if cfg!(target_os = "android") {
        ClientPlatform::Android
    } else if cfg!(target_os = "ios") {
        ClientPlatform::Ios
    } else {
        ClientPlatform::Desktop
    }
}

pub fn platform_id(platform: ClientPlatform) -> &'static str {
    match platform {
        ClientPlatform::Desktop => "desktop",
        ClientPlatform::Android => "android",
        ClientPlatform::Ios => "ios",
    }
}

pub fn is_mobile_platform(platform: ClientPlatform) -> bool {
    matches!(platform, ClientPlatform::Android | ClientPlatform::Ios)
}

/// Build the platform-appropriate set of client-tool function definitions
/// for AGiXT `command_overrides`.
pub fn all() -> Vec<Value> {
    for_current_platform()
}

pub fn for_current_platform() -> Vec<Value> {
    for_platform(current_platform())
}

pub fn for_platform(platform: ClientPlatform) -> Vec<Value> {
    match platform {
        ClientPlatform::Desktop => desktop_tools(),
        ClientPlatform::Android | ClientPlatform::Ios => mobile_tools(platform),
    }
}

/// Build the full desktop set of client-tool function definitions for AGiXT
/// `command_overrides`. Each entry is shaped like:
///
/// ```text
/// {
///   "type": "function",
///   "function": {
///     "name": "shell_run",
///     "description": "...",
///     "parameters": { JSON Schema for the arguments }
///   }
/// }
/// ```
fn desktop_tools() -> Vec<Value> {
    vec![
        // ----- Shell / app launch -----
        function(
            "shell_run",
            "Run a single shell command on the user's local machine and \
             return its stdout/stderr/exit_code. Use this for explicit shell \
             tasks and command-style application launch by name (e.g. \
             `spotify &` on Linux, \
             `open -a Spotify` on macOS, `start spotify:` on Windows). \
             Do not use this for sudo/admin/install commands; use sudo_run \
             for those so the desktop client can use its non-interactive \
             privileged command session. \
             Always background long-running apps with `&` (Linux/macOS) \
             so they don't block, then call desktop_screenshot to verify the \
             launch before answering. If the user asks to click an icon, button, \
             menu, or visible desktop UI, use desktop_vision_control instead \
             of replacing that request with shell_run. If app launch fails, \
             do not stop; use desktop_vision_control to open the app through \
             the user's visible desktop UI.",
            json!({
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command line to execute. Use platform-appropriate syntax.",
                    },
                    "timeout_ms": {
                        "type": "integer",
                        "description": "Optional timeout in milliseconds. Default 8000.",
                    }
                },
                "required": ["command"],
            }),
        ),
        function(
            "sudo_run",
            "Run a single privileged shell command on the user's local machine \
             through sudo and return stdout/stderr/exit_code. Use this for \
             installs, package-manager operations, writing protected system \
             paths, service management, and other admin tasks. The desktop app \
             stores the validated sudo password in the operating system \
             credential store after the user authenticates once in Settings. \
             Do not include `sudo` inside the command string; this tool adds \
             it. If it returns SUDO_AUTH_REQUIRED, ask the user to authenticate \
             Privileged Commands in AGiXT Desktop settings, then retry.",
            json!({
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Privileged shell command to execute without a leading sudo.",
                    },
                    "timeout_ms": {
                        "type": "integer",
                        "description": "Optional timeout in milliseconds. Default 600000.",
                    }
                },
                "required": ["command"],
            }),
        ),
        // ----- Persistent terminal sessions -----
        function(
            "terminal_open",
            "Open a persistent PTY-backed terminal session on the user's local \
             machine. Use this for longer-running processes, commands that \
             stream progress, interactive shells, build/test/watch processes, \
             package-manager output you need to monitor, or anything that may \
             need follow-up input, polling, or Ctrl+C. After opening, use \
             terminal_exec, terminal_read, terminal_send_input, terminal_signal, \
             terminal_resize, and terminal_close with the returned session id.",
            json!({
                "type": "object",
                "properties": {
                    "shell": {"type": "string", "description": "Optional shell path, e.g. /bin/bash. Defaults to the user's shell."},
                    "cwd": {"type": "string", "description": "Optional working directory."},
                    "cols": {"type": "integer", "description": "Terminal columns. Default 120."},
                    "rows": {"type": "integer", "description": "Terminal rows. Default 30."}
                }
            }),
        ),
        function(
            "terminal_exec",
            "Run a command inside an existing persistent terminal session and \
             return output collected until the terminal is idle or the timeout \
             expires. Use this after terminal_open for longer-running work. \
             Preserve the returned next_offset and pass it to terminal_read to \
             continue polling without duplicating output.",
            json!({
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Terminal session id returned by terminal_open."},
                    "command": {"type": "string", "description": "Command to write to the terminal. A newline is added by the client."},
                    "idle_ms": {"type": "integer", "description": "How long output must be quiet before returning. Default 500."},
                    "timeout_ms": {"type": "integer", "description": "Maximum time to wait for this read cycle. Default 30000."}
                },
                "required": ["session_id", "command"],
            }),
        ),
        function(
            "terminal_send_input",
            "Send raw input bytes to an existing terminal session. Use this for \
             prompts, yes/no answers, passwords only when the user explicitly \
             provided them for this command, or interactive programs. No newline \
             is added automatically.",
            json!({
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "data": {"type": "string", "description": "Raw text to write to the terminal."}
                },
                "required": ["session_id", "data"],
            }),
        ),
        function(
            "terminal_read",
            "Read buffered output from an existing terminal session. Pass the \
             previous next_offset to continue from where you left off. Use this \
             to poll long-running processes without resending the command.",
            json!({
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "offset": {"type": "integer", "description": "Byte offset returned by terminal_exec or a prior terminal_read."}
                },
                "required": ["session_id"],
            }),
        ),
        function(
            "terminal_signal",
            "Send a control signal to a terminal session, usually ctrl-c to \
             stop a long-running foreground process.",
            json!({
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "signal": {"type": "string", "enum": ["ctrl-c", "ctrl-d", "ctrl-z"], "default": "ctrl-c"}
                },
                "required": ["session_id"],
            }),
        ),
        function(
            "terminal_resize",
            "Resize an existing terminal session.",
            json!({
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "cols": {"type": "integer"},
                    "rows": {"type": "integer"}
                },
                "required": ["session_id", "cols", "rows"],
            }),
        ),
        function(
            "terminal_close",
            "Close an existing terminal session and kill its child process.",
            json!({
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"}
                },
                "required": ["session_id"],
            }),
        ),
        function(
            "terminal_list",
            "List currently open persistent terminal sessions.",
            json!({
                "type": "object",
                "properties": {}
            }),
        ),
        // ----- Vision / direct input -----
        function(
            "desktop_vision_control",
            "Use the user's visible desktop with a local computer-use vision \
             loop. This is the preferred tool for requests like click an icon, \
             press a visible button, select a menu item, inspect the screen, \
             or open an app through the graphical desktop. The desktop client \
             captures screenshots, asks the agent's vision provider for one \
             action at a time using Qwen-style normalized 0..1000 point \
             coordinates, executes the local action, then verifies with \
             another screenshot. Use this \
             instead of manually guessing desktop_click coordinates when the \
             task depends on visual UI.",
            json!({
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "The complete visible-desktop task to accomplish, including the original user wording when possible."
                    },
                    "monitor_index": {"type": "integer", "description": "Which monitor (0=primary)."},
                    "target_width": {
                        "type": "integer",
                        "description": "Screenshot resize width. Default 1920."
                    },
                    "use_smartest": {
                        "type": "boolean",
                        "description": "Whether to request the smartest configured vision provider."
                    }
                },
                "required": ["task"],
            }),
        ),
        function(
            "desktop_screenshot",
            "Capture a screenshot of the user's desktop and return a \
             base64 JPEG plus the original screen dimensions. Use this \
             first for requests that mention clicking, icons, buttons, menus, \
             windows, visible UI, or inspecting the current desktop. Use it \
             before clicking to know where things are, and again after clicking \
             to verify the action worked.",
            json!({
                "type": "object",
                "properties": {
                    "monitor_index": {"type": "integer", "description": "Which monitor (0=primary)."},
                    "target_width": {"type": "integer", "description": "Resize the JPEG to this width before returning. Default 1920 if both target_width and target_height are omitted."},
                    "target_height": {"type": "integer", "description": "Resize height. Usually omit; aspect ratio preserved."}
                }
            }),
        ),
        function(
            "desktop_click",
            "Click at a screen coordinate. When given coordinates from \
             a screenshot, pass absolute image pixel coordinates and set \
             coordinate_space:\"screenshot\". Pass width/height back as \
             target_width/target_height, and pass original_width/original_height \
             back as screen_width/screen_height. Qwen-style normalized 0..1000 \
             coordinates are also accepted with normalized:true. \
             Use click_type single for one click, double for two clicks.",
            json!({
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Screen pixel coordinate, or screenshot image pixel coordinate when coordinate_space is screenshot."},
                    "y": {"type": "integer", "description": "Screen pixel coordinate, or screenshot image pixel coordinate when coordinate_space is screenshot."},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                    "click_type": {"type": "string", "enum": ["single", "double"], "default": "single"},
                    "coordinate_space": {"type": "string", "enum": ["screen", "screenshot", "normalized"], "description": "Use screenshot when x/y came from the image returned by desktop_screenshot."},
                    "image_coordinates": {"type": "boolean", "description": "Alias for coordinate_space=screenshot."},
                    "normalized": {"type": "boolean", "description": "Legacy mode: if true, x/y are in 0..1000 normalized space."},
                    "target_width": {"type": "integer"},
                    "target_height": {"type": "integer"},
                    "screen_width": {"type": "integer"},
                    "screen_height": {"type": "integer"},
                    "monitor_offset_x": {"type": "integer"},
                    "monitor_offset_y": {"type": "integer"}
                },
                "required": ["x", "y"]
            }),
        ),
        function(
            "desktop_move",
            "Move the mouse cursor to a screen coordinate without clicking. \
             Use this for hover-only UI interactions such as revealing tooltips, \
             menus, hidden controls, or hover states. When given coordinates \
             from a screenshot, pass coordinate_space:\"screenshot\" and the \
             same image/screen dimension fields used by desktop_click.",
            json!({
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Screen pixel coordinate, screenshot image pixel coordinate, or normalized coordinate."},
                    "y": {"type": "integer", "description": "Screen pixel coordinate, screenshot image pixel coordinate, or normalized coordinate."},
                    "coordinate_space": {"type": "string", "enum": ["screen", "screenshot", "normalized"]},
                    "image_coordinates": {"type": "boolean", "description": "Alias for coordinate_space=screenshot."},
                    "normalized": {"type": "boolean", "description": "If true, x/y are in 0..1000 normalized space."},
                    "target_width": {"type": "integer"},
                    "target_height": {"type": "integer"},
                    "screen_width": {"type": "integer"},
                    "screen_height": {"type": "integer"},
                    "monitor_offset_x": {"type": "integer"},
                    "monitor_offset_y": {"type": "integer"}
                },
                "required": ["x", "y"]
            }),
        ),
        function(
            "desktop_drag",
            "Click and drag from one coordinate to another. Use this for \
             sliders, selections, drag-and-drop, moving windows, resizing panes, \
             or dragging files/items. Coordinates support the same screenshot \
             and normalized 0..1000 modes as desktop_click.",
            json!({
                "type": "object",
                "properties": {
                    "from_x": {"type": "integer", "description": "Start X coordinate."},
                    "from_y": {"type": "integer", "description": "Start Y coordinate."},
                    "to_x": {"type": "integer", "description": "End X coordinate."},
                    "to_y": {"type": "integer", "description": "End Y coordinate."},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                    "coordinate_space": {"type": "string", "enum": ["screen", "screenshot", "normalized"]},
                    "image_coordinates": {"type": "boolean", "description": "Alias for coordinate_space=screenshot."},
                    "normalized": {"type": "boolean", "description": "If true, coordinates are in 0..1000 normalized space."},
                    "target_width": {"type": "integer"},
                    "target_height": {"type": "integer"},
                    "screen_width": {"type": "integer"},
                    "screen_height": {"type": "integer"},
                    "monitor_offset_x": {"type": "integer"},
                    "monitor_offset_y": {"type": "integer"}
                },
                "required": ["from_x", "from_y", "to_x", "to_y"]
            }),
        ),
        function(
            "desktop_scroll",
            "Scroll the user's desktop at the current pointer location. \
             Positive vertical amounts scroll up; negative vertical amounts \
             scroll down. Use horizontal axis for side-to-side scrolling.",
            json!({
                "type": "object",
                "properties": {
                    "amount": {"type": "integer", "description": "Scroll amount; positive up/left, negative down/right depending on axis."},
                    "axis": {"type": "string", "enum": ["vertical", "horizontal", "x", "y"], "default": "vertical"}
                },
                "required": ["amount"]
            }),
        ),
        function(
            "desktop_type",
            "Type literal text or a key combination on the user's machine. \
             Useful for opening apps through the desktop launcher: on Linux \
             try keys [\"super\"], then text like \"Spotify\", then keys \
             [\"enter\"].",
            json!({
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Literal text to type."},
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Key chord, e.g. [\"ctrl\",\"c\"] for copy."
                    }
                }
            }),
        ),
        // ----- Filesystem -----
        function(
            "fs_read",
            "Read a file from the user's local disk. Paths support ~ and $VAR expansion.",
            json!({
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }),
        ),
        function(
            "fs_write",
            "Write (overwrite) a file on the user's local disk. Atomic.",
            json!({
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "encoding": {"type": "string", "enum": ["utf8", "base64"], "default": "utf8"},
                    "create_dirs": {"type": "boolean", "default": false}
                },
                "required": ["path", "content"]
            }),
        ),
        function(
            "fs_edit",
            "Apply find/replace edits to a file on the user's local disk. Each `find` must match exactly once unless `replace_all` is true.",
            json!({
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "edits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "find": {"type": "string"},
                                "replace": {"type": "string"},
                                "replace_all": {"type": "boolean", "default": false}
                            },
                            "required": ["find", "replace"]
                        }
                    }
                },
                "required": ["path", "edits"]
            }),
        ),
        function(
            "fs_list",
            "List files in a directory on the user's local disk.",
            json!({
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }),
        ),
        // ----- Workspace bridge -----
        function(
            "workspace_upload",
            "Upload a file from the user's local disk to the AGiXT conversation workspace (cloud).",
            json!({
                "type": "object",
                "properties": {
                    "local_path": {"type": "string"},
                    "workspace_path": {"type": "string", "description": "Optional sub-path within the workspace."}
                },
                "required": ["local_path"]
            }),
        ),
        function(
            "workspace_download",
            "Download a file from the AGiXT conversation workspace to the user's local disk.",
            json!({
                "type": "object",
                "properties": {
                    "workspace_path": {"type": "string"},
                    "local_path": {"type": "string"},
                    "overwrite": {"type": "boolean", "default": false}
                },
                "required": ["workspace_path", "local_path"]
            }),
        ),
        // ----- XTSchool child experience bridge -----
        function(
            "xtschool_search_library",
            "Search the child-safe XTSchool library that is visible in the current company. \
             Use this before recommending a video, song, audiobook, or game so you only name \
             real parent-approved items. For child users, the client only returns approved \
             content the child can access.",
            json!({
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search text from the child or parent."},
                    "content_type": {"type": "string", "enum": ["video", "playlist", "music", "audiobook", "game"], "description": "Optional content type filter."}
                }
            }),
        ),
        function(
            "xtschool_open_content",
            "Open a specific XTSchool library item by id in the child-safe hub. \
             Use only ids returned by xtschool_search_library or visible in XTSchool context.",
            json!({
                "type": "object",
                "properties": {
                    "content_id": {"type": "string", "description": "XTSchool content id."}
                },
                "required": ["content_id"]
            }),
        ),
        function(
            "xtschool_import_content",
            "Parent/admin only: import a YouTube, Spotify, Audible, or web-game URL into the \
             XTSchool library for parent approval and child assignment. Use this for requests \
             like add_youtube_url, add_spotify_url, or approve_audiobook.",
            json!({
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "YouTube, Spotify, Audible, or web-game URL."},
                    "title": {"type": "string", "description": "Optional title override."},
                    "description": {"type": "string"},
                    "approved": {"type": "boolean", "default": true},
                    "bedtime": {"type": "boolean", "default": false},
                    "allowed_child_user_ids": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["url"]
            }),
        ),
        function(
            "xtschool_update_content",
            "Parent/admin only: update XTSchool library metadata, approval, bedtime tag, or child visibility.",
            json!({
                "type": "object",
                "properties": {
                    "content_id": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "approved": {"type": "boolean"},
                    "bedtime": {"type": "boolean"},
                    "allowed_child_user_ids": {"type": "array", "items": {"type": "string"}},
                    "metadata": {"type": "object"}
                },
                "required": ["content_id"]
            }),
        ),
        function(
            "xtschool_create_playlist",
            "Parent/admin only: create an XTSchool playlist metadata item from approved content ids.",
            json!({
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "content_ids": {"type": "array", "items": {"type": "string"}},
                    "approved": {"type": "boolean", "default": false},
                    "bedtime": {"type": "boolean", "default": false},
                    "allowed_child_user_ids": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["title"]
            }),
        ),
        function(
            "xtschool_add_content_to_playlist",
            "Parent/admin only: add one or more XTSchool content ids to an existing playlist's metadata.",
            json!({
                "type": "object",
                "properties": {
                    "playlist_id": {"type": "string"},
                    "content_ids": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["playlist_id", "content_ids"]
            }),
        ),
        function(
            "xtschool_open_creation",
            "Open one of the child's AI HTML creations in the XTSchool sandbox viewer.",
            json!({
                "type": "object",
                "properties": {
                    "creation_id": {"type": "string", "description": "XTSchool creation id."}
                },
                "required": ["creation_id"]
            }),
        ),
        function(
            "xtschool_create_html_creation",
            "Create a new single-file HTML creation for the child in XTSchool and open it. \
             The HTML must be complete and self-contained. Include a window message listener \
             for xtschool_media_control or kids_game_control when the creation has controls \
             the child may ask AGiXT to press by voice.",
            json!({
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "html": {"type": "string", "description": "Full replacement HTML document."},
                    "prompt": {"type": "string", "description": "Optional short note about what the child asked for."},
                    "open": {"type": "boolean", "default": true}
                },
                "required": ["title", "html"]
            }),
        ),
        function(
            "xtschool_update_html_creation",
            "Replace the full HTML source for an existing child-owned XTSchool creation and open the new revision. \
             Use this when the child asks to change the active creation.",
            json!({
                "type": "object",
                "properties": {
                    "creation_id": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "html": {"type": "string", "description": "Full replacement HTML document."},
                    "prompt": {"type": "string", "description": "Optional short note about what the child asked to change."},
                    "open": {"type": "boolean", "default": true}
                },
                "required": ["creation_id", "html"]
            }),
        ),
        function(
            "xtschool_create_calendar_event",
            "Create a family or child-specific XTSchool calendar event. Parents can create family \
             or per-child events; child users can create their own event only.",
            json!({
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "starts_at": {"type": "string", "description": "Local datetime or ISO datetime string."},
                    "ends_at": {"type": "string"},
                    "description": {"type": "string"},
                    "all_day": {"type": "boolean", "default": false},
                    "child_user_id": {"type": "string", "description": "Optional child user id for parent-created per-child events."}
                },
                "required": ["title", "starts_at"]
            }),
        ),
        function(
            "xtschool_media_control",
            "Control the active XTSchool media player, game iframe, or HTML creation sandbox. \
             Use this for play, pause, stop, seek, close, or a control action the creation can handle.",
            json!({
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["play", "pause", "stop", "seek", "close", "press", "jump", "custom"]},
                    "seconds": {"type": "number", "description": "Seek target in seconds when action is seek."},
                    "control": {"type": "string", "description": "Optional game/creation control name for press/custom actions."},
                    "payload": {"type": "object", "description": "Optional structured control payload."}
                },
                "required": ["action"]
            }),
        ),
    ]
}

fn mobile_tools(platform: ClientPlatform) -> Vec<Value> {
    let os_name = platform_id(platform);
    let open_app_description = if platform == ClientPlatform::Android {
        format!(
            "Open an app on the user's {os_name} device. Prefer passing an Android package \
             name in `package`/`package_name` when you know it, or pass a URL/deep link in \
             `url`. If the user names a common app, pass `name`; AGiXT Desktop Mobile knows \
             common Android packages and schemes for Spotify, YouTube, Maps, Mail, Phone, \
             Messages, Settings, and Browser."
        )
    } else {
        format!(
            "Open an app on the user's {os_name} device. Prefer passing a URL scheme or \
             universal link in `url` when you know it. If the user names a common app, pass \
             `name`; AGiXT Desktop Mobile knows common schemes such as Spotify, YouTube, Maps, \
             Mail, Phone, Messages, Settings, and Browser. iOS does not allow launching arbitrary \
             apps by bundle id, so bundle IDs are accepted only as metadata."
        )
    };
    let open_settings_description = if platform == ClientPlatform::Android {
        format!(
            "Open settings on the user's {os_name} device. Pass `app_package` for an \
             app-specific settings page, or pass `section` for common Android sections such as \
             system, wifi, bluetooth, notifications, privacy, location, accessibility, network, \
             battery, or apps."
        )
    } else {
        format!(
            "Open settings on the user's {os_name} device. iOS reliably allows opening this \
             app's settings page; broader system settings are controlled by iOS."
        )
    };
    vec![
        function(
            "device_open_url",
            "Open a URL, universal link, app link, or deep link on the user's mobile device. \
             Use this as the primitive for launching mobile apps when you know a scheme such \
             as spotify://, maps://, geo:, tel:, sms:, mailto:, or an https universal/app link. \
             This runs on the client device, not the AGiXT server.",
            json!({
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL or deep link to open on the user's device."
                    },
                    "with": {
                        "type": "string",
                        "description": "Optional OS opener/application hint when supported by the platform."
                    }
                },
                "required": ["url"]
            }),
        ),
        function(
            "device_open_app",
            &open_app_description,
            json!({
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Human app name, e.g. Spotify, YouTube, Maps, Settings."
                    },
                    "url": {
                        "type": "string",
                        "description": "Preferred deep link, universal link, or app link to open."
                    },
                    "package": {
                        "type": "string",
                        "description": "Android package name when known, e.g. com.spotify.music."
                    },
                    "package_name": {
                        "type": "string",
                        "description": "Alias for Android package name."
                    },
                    "bundle_id": {
                        "type": "string",
                        "description": "iOS bundle id when known. iOS still generally requires a URL scheme to open another app."
                    }
                }
            }),
        ),
        function(
            "device_open_settings",
            &open_settings_description,
            json!({
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "description": "Optional settings section such as app, wifi, bluetooth, notifications, privacy, or system."
                    },
                    "app_package": {
                        "type": "string",
                        "description": "Android package name for app-specific settings."
                    },
                    "package": {
                        "type": "string",
                        "description": "Alias for app_package."
                    },
                    "bundle_id": {
                        "type": "string",
                        "description": "iOS bundle id metadata for app settings."
                    }
                }
            }),
        ),
        function(
            "workspace_upload",
            "Upload a file from the user's device sandbox to the AGiXT conversation workspace when the app can access that path.",
            json!({
                "type": "object",
                "properties": {
                    "local_path": {"type": "string"},
                    "workspace_path": {"type": "string", "description": "Optional sub-path within the workspace."}
                },
                "required": ["local_path"]
            }),
        ),
        function(
            "workspace_download",
            "Download a file from the AGiXT conversation workspace into the mobile app's accessible storage.",
            json!({
                "type": "object",
                "properties": {
                    "workspace_path": {"type": "string"},
                    "local_path": {"type": "string"},
                    "overwrite": {"type": "boolean", "default": false}
                },
                "required": ["workspace_path", "local_path"]
            }),
        ),
        function(
            "xtschool_search_library",
            "Search the child-safe XTSchool library visible on this device. For child users, only parent-approved accessible items are returned.",
            json!({
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "content_type": {"type": "string", "enum": ["video", "playlist", "music", "audiobook", "game"]}
                }
            }),
        ),
        function(
            "xtschool_open_content",
            "Open a specific XTSchool content item by id.",
            json!({
                "type": "object",
                "properties": {"content_id": {"type": "string"}},
                "required": ["content_id"]
            }),
        ),
        function(
            "xtschool_import_content",
            "Parent/admin only: import a YouTube, Spotify, Audible, or web-game URL into the XTSchool library.",
            json!({
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "approved": {"type": "boolean", "default": true},
                    "bedtime": {"type": "boolean", "default": false},
                    "allowed_child_user_ids": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["url"]
            }),
        ),
        function(
            "xtschool_update_content",
            "Parent/admin only: update XTSchool library metadata, approval, bedtime tag, or child visibility.",
            json!({
                "type": "object",
                "properties": {
                    "content_id": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "approved": {"type": "boolean"},
                    "bedtime": {"type": "boolean"},
                    "allowed_child_user_ids": {"type": "array", "items": {"type": "string"}},
                    "metadata": {"type": "object"}
                },
                "required": ["content_id"]
            }),
        ),
        function(
            "xtschool_create_playlist",
            "Parent/admin only: create an XTSchool playlist metadata item from approved content ids.",
            json!({
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "content_ids": {"type": "array", "items": {"type": "string"}},
                    "approved": {"type": "boolean", "default": false},
                    "bedtime": {"type": "boolean", "default": false},
                    "allowed_child_user_ids": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["title"]
            }),
        ),
        function(
            "xtschool_add_content_to_playlist",
            "Parent/admin only: add one or more XTSchool content ids to an existing playlist's metadata.",
            json!({
                "type": "object",
                "properties": {
                    "playlist_id": {"type": "string"},
                    "content_ids": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["playlist_id", "content_ids"]
            }),
        ),
        function(
            "xtschool_open_creation",
            "Open one of the child's XTSchool HTML creations.",
            json!({
                "type": "object",
                "properties": {"creation_id": {"type": "string"}},
                "required": ["creation_id"]
            }),
        ),
        function(
            "xtschool_create_html_creation",
            "Create a new self-contained HTML creation for the child in XTSchool.",
            json!({
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "html": {"type": "string"},
                    "prompt": {"type": "string"},
                    "open": {"type": "boolean", "default": true}
                },
                "required": ["title", "html"]
            }),
        ),
        function(
            "xtschool_update_html_creation",
            "Replace the full HTML source for an existing XTSchool creation.",
            json!({
                "type": "object",
                "properties": {
                    "creation_id": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "html": {"type": "string"},
                    "prompt": {"type": "string"},
                    "open": {"type": "boolean", "default": true}
                },
                "required": ["creation_id", "html"]
            }),
        ),
        function(
            "xtschool_create_calendar_event",
            "Create a family or child-specific XTSchool calendar event.",
            json!({
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "starts_at": {"type": "string"},
                    "ends_at": {"type": "string"},
                    "description": {"type": "string"},
                    "all_day": {"type": "boolean", "default": false},
                    "child_user_id": {"type": "string"}
                },
                "required": ["title", "starts_at"]
            }),
        ),
        function(
            "xtschool_media_control",
            "Control the active XTSchool player, game, or creation sandbox.",
            json!({
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["play", "pause", "stop", "seek", "close", "press", "jump", "custom"]},
                    "seconds": {"type": "number"},
                    "control": {"type": "string"},
                    "payload": {"type": "object"}
                },
                "required": ["action"]
            }),
        ),
    ]
}

fn function(name: &str, description: &str, parameters: Value) -> Value {
    json!({
        "type": "function",
        "exclusive": true,
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn all_returns_canonical_set() {
        let tools = for_platform(ClientPlatform::Desktop);
        let names: Vec<&str> = tools
            .iter()
            .filter_map(|t| t["function"]["name"].as_str())
            .collect();
        assert!(names.contains(&"shell_run"));
        assert!(names.contains(&"sudo_run"));
        assert!(names.contains(&"terminal_open"));
        assert!(names.contains(&"terminal_exec"));
        assert!(names.contains(&"terminal_read"));
        assert!(names.contains(&"terminal_signal"));
        assert!(names.contains(&"desktop_vision_control"));
        assert!(names.contains(&"desktop_screenshot"));
        assert!(names.contains(&"desktop_click"));
        assert!(names.contains(&"desktop_move"));
        assert!(names.contains(&"desktop_drag"));
        assert!(names.contains(&"desktop_scroll"));
        assert!(names.contains(&"desktop_type"));
        assert!(names.contains(&"fs_read"));
        assert!(names.contains(&"fs_write"));
        assert!(names.contains(&"xtschool_search_library"));
        assert!(names.contains(&"xtschool_import_content"));
        assert!(names.contains(&"xtschool_update_content"));
        assert!(names.contains(&"xtschool_create_playlist"));
        assert!(names.contains(&"xtschool_add_content_to_playlist"));
        assert!(names.contains(&"xtschool_create_html_creation"));
        assert!(names.contains(&"xtschool_update_html_creation"));
        assert!(names.contains(&"xtschool_media_control"));
    }

    #[test]
    fn mobile_tools_are_device_oriented() {
        for platform in [ClientPlatform::Android, ClientPlatform::Ios] {
            let tools = for_platform(platform);
            let names: Vec<&str> = tools
                .iter()
                .filter_map(|t| t["function"]["name"].as_str())
                .collect();
            assert!(names.contains(&"device_open_url"));
            assert!(names.contains(&"device_open_app"));
            assert!(names.contains(&"device_open_settings"));
            assert!(names.contains(&"workspace_upload"));
            assert!(names.contains(&"xtschool_search_library"));
            assert!(names.contains(&"xtschool_import_content"));
            assert!(names.contains(&"xtschool_update_content"));
            assert!(names.contains(&"xtschool_create_html_creation"));
            assert!(!names.contains(&"shell_run"));
            assert!(!names.contains(&"sudo_run"));
            assert!(!names.contains(&"terminal_open"));
            assert!(!names.contains(&"desktop_vision_control"));
            assert!(!names.contains(&"desktop_click"));
        }
    }

    #[test]
    fn each_tool_is_openai_format() {
        for platform in [
            ClientPlatform::Desktop,
            ClientPlatform::Android,
            ClientPlatform::Ios,
        ] {
            for t in for_platform(platform) {
                assert_eq!(t["type"].as_str(), Some("function"));
                assert_eq!(t["exclusive"].as_bool(), Some(true));
                assert!(t["function"]["name"].as_str().is_some());
                assert!(t["function"]["description"].as_str().is_some());
                assert_eq!(t["function"]["parameters"]["type"].as_str(), Some("object"));
            }
        }
    }
}

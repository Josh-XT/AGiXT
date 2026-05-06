//! OpenAI-format function definitions for the desktop client's tools.
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

/// Build the full set of client-tool function definitions for AGiXT
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
pub fn all() -> Vec<Value> {
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
        let tools = all();
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
        assert!(names.contains(&"desktop_type"));
        assert!(names.contains(&"fs_read"));
        assert!(names.contains(&"fs_write"));
    }

    #[test]
    fn each_tool_is_openai_format() {
        for t in all() {
            assert_eq!(t["type"].as_str(), Some("function"));
            assert_eq!(t["exclusive"].as_bool(), Some(true));
            assert!(t["function"]["name"].as_str().is_some());
            assert!(t["function"]["description"].as_str().is_some());
            assert_eq!(t["function"]["parameters"]["type"].as_str(), Some("object"));
        }
    }
}

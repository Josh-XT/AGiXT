//! Headless CLI for the same automation primitives the Tauri app exposes
//! over IPC. Used by integration tests (and convenient for ad-hoc shell
//! debugging) to drive screenshot, click, type, and PTY commands without
//! having to spin up the GTK webview.
//!
//! Argument and JSON-output shapes are intentionally identical to the
//! IPC commands so tests written against this CLI also document the IPC
//! contract.
//!
//! Examples:
//!   agixt-cli screenshot --target-width 1920 --output /tmp/shot.b64
//!   agixt-cli click --x 500 --y 500 --normalized --target-width 1920 --screen-width 2560
//!   agixt-cli type --text "hello world"
//!   agixt-cli key --keys ctrl,c

use agixt_desktop_lib::automation::{self, VisionContext};
use serde_json::{json, Value};
use std::env;
use std::process::ExitCode;

fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        eprintln!("usage: {} <command> [flags]", args[0]);
        return ExitCode::from(2);
    }
    let cmd = args[1].clone();
    let flags = parse_flags(&args[2..]);

    let result: Result<Value, String> = match cmd.as_str() {
        "screenshot" => do_screenshot(&flags),
        "click" => do_click(&flags),
        "move" => do_move(&flags),
        "drag" => do_drag(&flags),
        "type" => do_type(&flags),
        "key" => do_key(&flags),
        "scroll" => do_scroll(&flags),
        "screen-info" => do_screen_info(&flags),
        other => Err(format!("unknown command: {other}")),
    };

    match result {
        Ok(v) => {
            println!("{}", serde_json::to_string(&v).unwrap_or_default());
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("{}", json!({ "error": e }));
            ExitCode::from(1)
        }
    }
}

fn vision_from(flags: &Flags) -> VisionContext {
    VisionContext {
        normalized: flags.flag_set("normalized"),
        coordinate_space: flags.string("coordinate-space"),
        image_coordinates: flags.flag_set("image-coordinates"),
        target_width: flags.u32("target-width"),
        target_height: flags.u32("target-height"),
        screen_width: flags.u32("screen-width"),
        screen_height: flags.u32("screen-height"),
        monitor_offset_x: flags.i32("monitor-offset-x"),
        monitor_offset_y: flags.i32("monitor-offset-y"),
    }
}

fn do_screenshot(flags: &Flags) -> Result<Value, String> {
    let result = automation::screenshot(
        flags.usize("monitor-index"),
        flags.u32("target-width"),
        flags.u32("target-height"),
    )
    .map_err(|e| format!("{e:#}"))?;

    if let Some(path) = flags.string("output") {
        // Write base64 JPEG bytes to file (decoded) so callers can read PNG/JPEG.
        use base64::Engine as _;
        let bytes = base64::engine::general_purpose::STANDARD
            .decode(&result.image_data)
            .map_err(|e| format!("decode b64: {e}"))?;
        std::fs::write(&path, &bytes).map_err(|e| format!("write {path}: {e}"))?;
        return Ok(json!({
            "path": path,
            "width": result.width,
            "height": result.height,
            "original_width": result.original_width,
            "original_height": result.original_height,
            "monitor_offset_x": result.monitor_offset_x,
            "monitor_offset_y": result.monitor_offset_y,
            "monitor_index": result.monitor_index,
        }));
    }
    serde_json::to_value(&result).map_err(|e| e.to_string())
}

fn do_click(flags: &Flags) -> Result<Value, String> {
    let x = flags.i32("x").ok_or("--x required")?;
    let y = flags.i32("y").ok_or("--y required")?;
    let button = flags.string("button").unwrap_or_else(|| "left".into());
    let click_type = flags
        .string("click-type")
        .unwrap_or_else(|| "single".into());
    let vision = vision_from(flags);
    let (rx, ry) =
        automation::click(x, y, &button, &click_type, &vision).map_err(|e| format!("{e:#}"))?;
    Ok(json!({ "x": rx, "y": ry }))
}

fn do_move(flags: &Flags) -> Result<Value, String> {
    let x = flags.i32("x").ok_or("--x required")?;
    let y = flags.i32("y").ok_or("--y required")?;
    let vision = vision_from(flags);
    let (rx, ry) = automation::move_mouse(x, y, &vision).map_err(|e| format!("{e:#}"))?;
    Ok(json!({ "x": rx, "y": ry }))
}

fn do_drag(flags: &Flags) -> Result<Value, String> {
    let from_x = flags.i32("from-x").ok_or("--from-x required")?;
    let from_y = flags.i32("from-y").ok_or("--from-y required")?;
    let to_x = flags.i32("to-x").ok_or("--to-x required")?;
    let to_y = flags.i32("to-y").ok_or("--to-y required")?;
    let button = flags.string("button").unwrap_or_else(|| "left".into());
    let vision = vision_from(flags);
    let ((fx, fy), (tx, ty)) = automation::drag(from_x, from_y, to_x, to_y, &button, &vision)
        .map_err(|e| format!("{e:#}"))?;
    Ok(json!({ "from_x": fx, "from_y": fy, "to_x": tx, "to_y": ty }))
}

fn do_type(flags: &Flags) -> Result<Value, String> {
    let text = flags.string("text").ok_or("--text required")?;
    automation::keyboard(Some(text), None).map_err(|e| format!("{e:#}"))?;
    Ok(json!({ "ok": true }))
}

fn do_key(flags: &Flags) -> Result<Value, String> {
    let keys = flags
        .string("keys")
        .ok_or("--keys required (comma-separated)")?
        .split(',')
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>();
    if keys.is_empty() {
        return Err("at least one key required".into());
    }
    automation::keyboard(None, Some(keys)).map_err(|e| format!("{e:#}"))?;
    Ok(json!({ "ok": true }))
}

fn do_scroll(flags: &Flags) -> Result<Value, String> {
    let amount = flags.i32("amount").ok_or("--amount required")?;
    let axis = flags.string("axis").unwrap_or_else(|| "vertical".into());
    automation::scroll(amount, &axis).map_err(|e| format!("{e:#}"))?;
    Ok(json!({ "ok": true }))
}

fn do_screen_info(_flags: &Flags) -> Result<Value, String> {
    // Take a no-resize screenshot just to learn each display's dimensions
    // and offsets — useful for the test harness to compute coords against.
    use screenshots::Screen;
    let screens = Screen::all().map_err(|e| format!("{e:#}"))?;
    let infos: Vec<Value> = screens
        .iter()
        .enumerate()
        .map(|(i, s)| {
            json!({
                "index": i,
                "x": s.display_info.x,
                "y": s.display_info.y,
                "width": s.display_info.width,
                "height": s.display_info.height,
                "scale_factor": s.display_info.scale_factor,
                "is_primary": s.display_info.is_primary,
            })
        })
        .collect();
    Ok(json!({ "monitors": infos }))
}

#[derive(Default)]
struct Flags {
    map: std::collections::HashMap<String, Option<String>>,
}

impl Flags {
    fn flag_set(&self, k: &str) -> bool {
        self.map.contains_key(k)
    }
    fn string(&self, k: &str) -> Option<String> {
        self.map.get(k).and_then(|v| v.clone())
    }
    fn i32(&self, k: &str) -> Option<i32> {
        self.string(k).and_then(|s| s.parse().ok())
    }
    fn u32(&self, k: &str) -> Option<u32> {
        self.string(k).and_then(|s| s.parse().ok())
    }
    fn usize(&self, k: &str) -> Option<usize> {
        self.string(k).and_then(|s| s.parse().ok())
    }
}

fn parse_flags(args: &[String]) -> Flags {
    let mut f = Flags::default();
    let mut i = 0;
    while i < args.len() {
        let a = &args[i];
        if let Some(stripped) = a.strip_prefix("--") {
            let key = stripped.to_string();
            // Look at next token; if it's another flag or absent, treat as bool.
            if i + 1 < args.len() && !args[i + 1].starts_with("--") {
                f.map.insert(key, Some(args[i + 1].clone()));
                i += 2;
            } else {
                f.map.insert(key, None);
                i += 1;
            }
        } else {
            i += 1;
        }
    }
    f
}

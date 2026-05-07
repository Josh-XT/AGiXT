//! Local desktop automation: screenshot, mouse, keyboard.
//!
//! Adapted from rust_endpoint_agent/src/terminal.rs. Since the desktop client
//! always runs in the user's session, we drop the Session-0 / root delegation
//! paths and call enigo / the screenshots crate directly.

use anyhow::{anyhow, Result};
use serde::Serialize;

/// Vision models pick coordinates from a screenshot of the desktop. The
/// high-level desktop vision-control loop asks Qwen-style models for
/// `point_2d` coordinates in a normalized 0..1000 grid, matching the kids app
/// browser agent and Qwen3-VL grounding examples. Lower-level one-off clicks
/// can still use screenshot-pixel coordinates to match the older
/// `machines.py` workflow.
///
/// Both coordinate modes need the same pieces of context:
///
///   * `target_width` / `target_height` — the dimensions of the resized
///     screenshot the model was *shown*. Screenshots default to 1920px wide
///     with aspect ratio preserved; coordinate math falls back to 1920×1080
///     only when no screenshot metadata was provided.
///   * `screen_width` / `screen_height` — the real monitor size in pixels
///     (post DPI scaling). Defaults to the same target dims.
///   * `monitor_offset_x` / `monitor_offset_y` — top-left origin of the
///     monitor in the global virtual screen space, for multi-monitor setups.
///
/// Screenshot-pixel mode, matching `machines.py`:
///
/// ```text
/// screen_x = image_x / target_w * screen_w + offset_x
/// screen_y = image_y / target_h * screen_h + offset_y
/// ```
///
/// Normalized mode:
///
/// ```text
/// target_x = norm_x / 1000 * target_w
/// target_y = norm_y / 1000 * target_h
/// screen_x = target_x / target_w * screen_w + offset_x
/// screen_y = target_y / target_h * screen_h + offset_y
/// ```
const NORMALIZED_SIZE: f64 = 1000.0;
const DEFAULT_SCREENSHOT_TARGET_WIDTH: u32 = 1920;

fn screenshot_target_size(
    target_width: Option<u32>,
    target_height: Option<u32>,
) -> (Option<u32>, Option<u32>) {
    match (target_width, target_height) {
        (None, None) => (Some(DEFAULT_SCREENSHOT_TARGET_WIDTH), None),
        other => other,
    }
}

#[derive(Debug, Clone, Default)]
pub struct VisionContext {
    pub normalized: bool,
    pub coordinate_space: Option<String>,
    pub image_coordinates: bool,
    pub target_width: Option<u32>,
    pub target_height: Option<u32>,
    pub screen_width: Option<u32>,
    pub screen_height: Option<u32>,
    pub monitor_offset_x: Option<i32>,
    pub monitor_offset_y: Option<i32>,
}

fn uses_screenshot_pixels(ctx: &VisionContext) -> bool {
    if ctx.image_coordinates {
        return true;
    }
    let Some(space) = &ctx.coordinate_space else {
        return false;
    };
    matches!(
        space.trim().to_ascii_lowercase().as_str(),
        "screenshot"
            | "screenshot_pixel"
            | "screenshot_pixels"
            | "image"
            | "image_pixel"
            | "image_pixels"
            | "vision"
    )
}

/// Resolve a raw `(x, y)` to actual screen pixels using the given vision
/// context. If no coordinate-space hint is provided, returns the input
/// unchanged so exact screen-pixel clicks still work.
pub fn resolve_coords(x: i32, y: i32, ctx: &VisionContext) -> (i32, i32) {
    let target_w = ctx.target_width.unwrap_or(1920) as f64;
    let target_h = ctx.target_height.unwrap_or(1080) as f64;
    let screen_w = ctx.screen_width.unwrap_or(target_w as u32) as f64;
    let screen_h = ctx.screen_height.unwrap_or(target_h as u32) as f64;
    let offset_x = ctx.monitor_offset_x.unwrap_or(0);
    let offset_y = ctx.monitor_offset_y.unwrap_or(0);

    if uses_screenshot_pixels(ctx) {
        let actual_x = ((x as f64) / target_w * screen_w) as i32 + offset_x;
        let actual_y = ((y as f64) / target_h * screen_h) as i32 + offset_y;
        return (actual_x, actual_y);
    }

    if !ctx.normalized {
        return (x, y);
    }

    let target_x = (x as f64) / NORMALIZED_SIZE * target_w;
    let target_y = (y as f64) / NORMALIZED_SIZE * target_h;
    let actual_x = (target_x / target_w * screen_w) as i32 + offset_x;
    let actual_y = (target_y / target_h * screen_h) as i32 + offset_y;
    (actual_x, actual_y)
}

#[cfg(all(feature = "automation", not(mobile)))]
use base64::engine::general_purpose::STANDARD as BASE64;
#[cfg(all(feature = "automation", not(mobile)))]
use base64::Engine as _;
#[cfg(all(feature = "automation", not(mobile)))]
use std::time::Duration;

#[cfg(all(feature = "automation", not(mobile)))]
use enigo::{Button, Direction, Enigo, Key, Keyboard as _, Mouse as _, Settings};

#[derive(Debug, Serialize)]
pub struct ScreenshotResult {
    /// Base64-encoded JPEG bytes of the (possibly resized) capture.
    pub image_data: String,
    /// Width of the JPEG actually returned (the model's coordinate space).
    pub width: u32,
    /// Height of the JPEG actually returned.
    pub height: u32,
    /// Real screen pixel width before any resize. Use this when sending
    /// click coordinates back as `screen_width`.
    pub original_width: u32,
    pub original_height: u32,
    /// Top-left of the captured monitor in the global virtual screen.
    /// Important for multi-monitor setups; the agent should pass these
    /// back as `monitor_offset_x`/`monitor_offset_y` on subsequent clicks.
    pub monitor_offset_x: i32,
    pub monitor_offset_y: i32,
    pub monitor_index: usize,
    pub format: &'static str,
}

#[cfg(all(feature = "automation", not(mobile)))]
pub fn click(
    x: i32,
    y: i32,
    button: &str,
    click_type: &str,
    vision: &VisionContext,
) -> Result<(i32, i32)> {
    let (px, py) = resolve_coords(x, y, vision);
    let mut enigo = Enigo::new(&Settings::default()).map_err(|e| anyhow!("init enigo: {e}"))?;
    enigo
        .move_mouse(px, py, enigo::Coordinate::Abs)
        .map_err(|e| anyhow!("move_mouse: {e}"))?;
    std::thread::sleep(Duration::from_millis(2));

    let normalized_button = button.to_lowercase();
    let btn = match normalized_button.as_str() {
        "left" | "primary" | "main" | "button1" | "left_click" => Button::Left,
        "right" | "secondary" | "context" | "button2" | "right_click" => Button::Right,
        "middle" | "auxiliary" | "aux" | "button3" | "middle_click" => Button::Middle,
        other => return Err(anyhow!("invalid button: {other}")),
    };
    let normalized_click_type = click_type.to_lowercase();
    match normalized_click_type.as_str() {
        "single" | "click" | "single_click" | "single-click" | "press" | "tap" => enigo
            .button(btn, Direction::Click)
            .map_err(|e| anyhow!("{e}"))?,
        "double" | "dblclick" | "double_click" | "double-click" => {
            enigo
                .button(btn, Direction::Click)
                .map_err(|e| anyhow!("{e}"))?;
            std::thread::sleep(Duration::from_millis(50));
            enigo
                .button(btn, Direction::Click)
                .map_err(|e| anyhow!("{e}"))?;
        }
        other => return Err(anyhow!("invalid click_type: {other}")),
    }
    Ok((px, py))
}

#[cfg(all(feature = "automation", not(mobile)))]
pub fn move_mouse(x: i32, y: i32, vision: &VisionContext) -> Result<(i32, i32)> {
    let (px, py) = resolve_coords(x, y, vision);
    let mut enigo = Enigo::new(&Settings::default()).map_err(|e| anyhow!("init enigo: {e}"))?;
    enigo
        .move_mouse(px, py, enigo::Coordinate::Abs)
        .map_err(|e| anyhow!("move_mouse: {e}"))?;
    Ok((px, py))
}

#[cfg(all(feature = "automation", not(mobile)))]
pub fn drag(
    from_x: i32,
    from_y: i32,
    to_x: i32,
    to_y: i32,
    button: &str,
    vision: &VisionContext,
) -> Result<((i32, i32), (i32, i32))> {
    let (fx, fy) = resolve_coords(from_x, from_y, vision);
    let (tx, ty) = resolve_coords(to_x, to_y, vision);
    let mut enigo = Enigo::new(&Settings::default()).map_err(|e| anyhow!("init enigo: {e}"))?;
    let btn = match button {
        "left" => Button::Left,
        "right" => Button::Right,
        "middle" => Button::Middle,
        other => return Err(anyhow!("invalid button: {other}")),
    };
    enigo
        .move_mouse(fx, fy, enigo::Coordinate::Abs)
        .map_err(|e| anyhow!("{e}"))?;
    std::thread::sleep(Duration::from_millis(10));
    enigo
        .button(btn, Direction::Press)
        .map_err(|e| anyhow!("{e}"))?;
    std::thread::sleep(Duration::from_millis(10));
    enigo
        .move_mouse(tx, ty, enigo::Coordinate::Abs)
        .map_err(|e| anyhow!("{e}"))?;
    std::thread::sleep(Duration::from_millis(10));
    enigo
        .button(btn, Direction::Release)
        .map_err(|e| anyhow!("{e}"))?;
    Ok(((fx, fy), (tx, ty)))
}

#[cfg(all(feature = "automation", not(mobile)))]
pub fn scroll(amount: i32, axis: &str) -> Result<()> {
    let mut enigo = Enigo::new(&Settings::default()).map_err(|e| anyhow!("init enigo: {e}"))?;
    let ax = match axis {
        "vertical" | "y" => enigo::Axis::Vertical,
        "horizontal" | "x" => enigo::Axis::Horizontal,
        other => return Err(anyhow!("invalid axis: {other}")),
    };
    enigo.scroll(amount, ax).map_err(|e| anyhow!("{e}"))?;
    Ok(())
}

#[cfg(all(feature = "automation", not(mobile)))]
pub fn keyboard(text: Option<String>, keys: Option<Vec<String>>) -> Result<()> {
    let mut enigo = Enigo::new(&Settings::default()).map_err(|e| anyhow!("init enigo: {e}"))?;
    if let Some(t) = text {
        enigo.text(&t).map_err(|e| anyhow!("type text: {e}"))?;
        return Ok(());
    }
    let Some(seq) = keys else {
        return Err(anyhow!("either text or keys must be provided"));
    };
    let mut modifiers = Vec::new();
    let mut regular = Vec::new();
    for name in &seq {
        let k = parse_key(name)?;
        if is_modifier(name) {
            modifiers.push(k);
        } else {
            regular.push(k);
        }
    }
    for m in &modifiers {
        enigo
            .key(*m, Direction::Press)
            .map_err(|e| anyhow!("{e}"))?;
    }
    for k in &regular {
        enigo
            .key(*k, Direction::Click)
            .map_err(|e| anyhow!("{e}"))?;
    }
    for m in modifiers.iter().rev() {
        enigo
            .key(*m, Direction::Release)
            .map_err(|e| anyhow!("{e}"))?;
    }
    Ok(())
}

#[cfg(all(feature = "automation", not(mobile)))]
fn is_modifier(key_name: &str) -> bool {
    matches!(
        key_name.to_lowercase().as_str(),
        "ctrl" | "control" | "alt" | "shift" | "meta" | "super" | "win" | "cmd"
    )
}

#[cfg(all(feature = "automation", not(mobile)))]
fn parse_key(key_name: &str) -> Result<Key> {
    Ok(match key_name.to_lowercase().as_str() {
        "enter" | "return" => Key::Return,
        "tab" => Key::Tab,
        "escape" | "esc" => Key::Escape,
        "backspace" => Key::Backspace,
        "delete" | "del" => Key::Delete,
        "space" => Key::Space,
        "ctrl" | "control" => Key::Control,
        "alt" => Key::Alt,
        "shift" => Key::Shift,
        "meta" | "super" | "win" | "cmd" => Key::Meta,
        "up" | "uparrow" => Key::UpArrow,
        "down" | "downarrow" => Key::DownArrow,
        "left" | "leftarrow" => Key::LeftArrow,
        "right" | "rightarrow" => Key::RightArrow,
        "home" => Key::Home,
        "end" => Key::End,
        "pageup" => Key::PageUp,
        "pagedown" => Key::PageDown,
        "f1" => Key::F1,
        "f2" => Key::F2,
        "f3" => Key::F3,
        "f4" => Key::F4,
        "f5" => Key::F5,
        "f6" => Key::F6,
        "f7" => Key::F7,
        "f8" => Key::F8,
        "f9" => Key::F9,
        "f10" => Key::F10,
        "f11" => Key::F11,
        "f12" => Key::F12,
        s if s.chars().count() == 1 => Key::Unicode(s.chars().next().unwrap()),
        other => return Err(anyhow!("unknown key: {other}")),
    })
}

#[cfg(all(feature = "automation", not(mobile)))]
pub fn screenshot(
    monitor_index: Option<usize>,
    target_width: Option<u32>,
    target_height: Option<u32>,
) -> Result<ScreenshotResult> {
    use image::{imageops, DynamicImage, RgbaImage};
    use screenshots::Screen;

    let screens = Screen::all().map_err(|e| anyhow!("enumerate screens: {e}"))?;
    if screens.is_empty() {
        return Err(anyhow!("no screens found"));
    }

    // Default to primary monitor
    let idx = monitor_index.unwrap_or(0);
    if idx >= screens.len() {
        return Err(anyhow!(
            "monitor index {idx} out of range (0..{})",
            screens.len()
        ));
    }
    let screen = &screens[idx];
    let display_x = screen.display_info.x;
    let display_y = screen.display_info.y;
    let shot = screen.capture().map_err(|e| anyhow!("capture: {e}"))?;
    let w = shot.width();
    let h = shot.height();
    let raw = shot.into_raw();
    let rgba = RgbaImage::from_raw(w, h, raw).ok_or_else(|| anyhow!("invalid raw image data"))?;
    let mut img = DynamicImage::ImageRgba8(rgba);

    let original_width = img.width();
    let original_height = img.height();
    let (target_width, target_height) = screenshot_target_size(target_width, target_height);

    img = match (target_width, target_height) {
        (Some(tw), Some(th)) if tw > 0 && th > 0 => {
            img.resize_exact(tw, th, imageops::FilterType::Triangle)
        }
        (Some(tw), None) if tw > 0 && tw < img.width() => {
            let th = (img.height() as f64 * tw as f64 / img.width() as f64).round() as u32;
            img.resize_exact(tw, th, imageops::FilterType::Triangle)
        }
        (None, Some(th)) if th > 0 && th < img.height() => {
            let tw = (img.width() as f64 * th as f64 / img.height() as f64).round() as u32;
            img.resize_exact(tw, th, imageops::FilterType::Triangle)
        }
        _ => img,
    };

    let mut jpeg = Vec::new();
    {
        let encoder = image::codecs::jpeg::JpegEncoder::new_with_quality(&mut jpeg, 80);
        img.write_with_encoder(encoder)
            .map_err(|e| anyhow!("encode jpeg: {e}"))?;
    }

    Ok(ScreenshotResult {
        image_data: BASE64.encode(&jpeg),
        width: img.width(),
        height: img.height(),
        original_width,
        original_height,
        monitor_offset_x: display_x,
        monitor_offset_y: display_y,
        monitor_index: idx,
        format: "jpeg",
    })
}

#[cfg(any(not(feature = "automation"), mobile))]
mod stubs {
    use super::*;
    pub fn click(_: i32, _: i32, _: &str, _: &str, _: &VisionContext) -> Result<(i32, i32)> {
        Err(anyhow!("desktop automation is not available in this build"))
    }
    pub fn move_mouse(_: i32, _: i32, _: &VisionContext) -> Result<(i32, i32)> {
        Err(anyhow!("desktop automation is not available in this build"))
    }
    pub fn drag(
        _: i32,
        _: i32,
        _: i32,
        _: i32,
        _: &str,
        _: &VisionContext,
    ) -> Result<((i32, i32), (i32, i32))> {
        Err(anyhow!("desktop automation is not available in this build"))
    }
    pub fn scroll(_: i32, _: &str) -> Result<()> {
        Err(anyhow!("desktop automation is not available in this build"))
    }
    pub fn keyboard(_: Option<String>, _: Option<Vec<String>>) -> Result<()> {
        Err(anyhow!("desktop automation is not available in this build"))
    }
    pub fn screenshot(
        _: Option<usize>,
        _: Option<u32>,
        _: Option<u32>,
    ) -> Result<ScreenshotResult> {
        Err(anyhow!("desktop automation is not available in this build"))
    }
}

#[cfg(any(not(feature = "automation"), mobile))]
pub use stubs::*;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resolve_passthrough_when_not_normalized() {
        let ctx = VisionContext::default();
        assert_eq!(resolve_coords(123, 456, &ctx), (123, 456));
    }

    #[test]
    fn screenshot_defaults_to_1920_wide_vision_surface() {
        assert_eq!(screenshot_target_size(None, None), (Some(1920), None));
        assert_eq!(screenshot_target_size(Some(1280), None), (Some(1280), None));
        assert_eq!(screenshot_target_size(None, Some(720)), (None, Some(720)));
    }

    #[test]
    fn resolve_normalized_to_default_1920x1080() {
        // No target/screen given → both default to 1920x1080.
        // 500/1000 of 1920 = 960; 500/1000 of 1080 = 540.
        let ctx = VisionContext {
            normalized: true,
            ..Default::default()
        };
        assert_eq!(resolve_coords(500, 500, &ctx), (960, 540));
    }

    #[test]
    fn resolve_normalized_with_explicit_screen_size() {
        // Model thinks in 1920x1080; actual screen is 3840x2160.
        let ctx = VisionContext {
            normalized: true,
            target_width: Some(1920),
            target_height: Some(1080),
            screen_width: Some(3840),
            screen_height: Some(2160),
            ..Default::default()
        };
        // 250/1000 → 480 in target → 960 on real screen
        assert_eq!(resolve_coords(250, 250, &ctx), (960, 540));
    }

    #[test]
    fn resolve_normalized_with_monitor_offset() {
        // Second monitor offset by (1920, 0) in virtual space.
        let ctx = VisionContext {
            normalized: true,
            target_width: Some(1920),
            target_height: Some(1080),
            screen_width: Some(1920),
            screen_height: Some(1080),
            monitor_offset_x: Some(1920),
            monitor_offset_y: Some(0),
            ..Default::default()
        };
        assert_eq!(resolve_coords(0, 0, &ctx), (1920, 0));
        assert_eq!(resolve_coords(1000, 1000, &ctx), (3840, 1080));
    }

    #[test]
    fn resolve_screenshot_pixels_match_machines_py_math() {
        // machines.py asks vision for image-space pixel coordinates, then
        // scales from the screenshot dimensions back to the real screen.
        let ctx = VisionContext {
            coordinate_space: Some("screenshot".into()),
            target_width: Some(1920),
            target_height: Some(1080),
            screen_width: Some(3840),
            screen_height: Some(2160),
            monitor_offset_x: Some(0),
            monitor_offset_y: Some(0),
            ..Default::default()
        };
        assert_eq!(resolve_coords(16, 320, &ctx), (32, 640));
        assert_eq!(resolve_coords(960, 540, &ctx), (1920, 1080));
    }

    #[test]
    fn resolve_normalized_corners_match_endpoint_agent_math() {
        // Identical math to rust_endpoint_agent terminal.rs lines 2706-2711.
        // Quick sanity check on the four corners + center.
        let ctx = VisionContext {
            normalized: true,
            target_width: Some(1920),
            target_height: Some(1080),
            screen_width: Some(2560),
            screen_height: Some(1440),
            monitor_offset_x: Some(0),
            monitor_offset_y: Some(0),
            ..Default::default()
        };
        assert_eq!(resolve_coords(0, 0, &ctx), (0, 0));
        assert_eq!(resolve_coords(1000, 0, &ctx), (2560, 0));
        assert_eq!(resolve_coords(0, 1000, &ctx), (0, 1440));
        assert_eq!(resolve_coords(1000, 1000, &ctx), (2560, 1440));
        assert_eq!(resolve_coords(500, 500, &ctx), (1280, 720));
    }

    #[test]
    fn resolve_normalized_floors_consistently_with_endpoint_agent() {
        // The endpoint agent uses `as i32` which truncates toward zero.
        // Same rounding behavior must apply here for parity.
        let ctx = VisionContext {
            normalized: true,
            target_width: Some(1920),
            target_height: Some(1080),
            screen_width: Some(1920),
            screen_height: Some(1080),
            ..Default::default()
        };
        // 333/1000 * 1920 = 639.36 → 639
        assert_eq!(resolve_coords(333, 333, &ctx), (639, 359));
    }
}

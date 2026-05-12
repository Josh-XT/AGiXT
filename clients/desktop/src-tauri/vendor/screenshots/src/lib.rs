mod image_utils;

use anyhow::{anyhow, Result};
use display_info::DisplayInfo;
use image::RgbaImage;

pub use display_info;
pub use image;

#[cfg(target_os = "macos")]
mod darwin;
#[cfg(target_os = "macos")]
use darwin::*;

#[cfg(target_os = "windows")]
mod win32;
#[cfg(target_os = "windows")]
use win32::*;

#[cfg(target_os = "linux")]
mod linux;
#[cfg(target_os = "linux")]
use linux::*;

/// This struct represents a screen capturer.
#[derive(Debug, Clone, Copy)]
pub struct Screen {
    pub display_info: DisplayInfo,
}

impl Screen {
    /// Get a screen from the [display_info].
    ///
    /// [display_info]:  https://docs.rs/display-info/latest/display_info/struct.DisplayInfo.html
    pub fn new(display_info: &DisplayInfo) -> Self {
        Screen {
            display_info: *display_info,
        }
    }

    /// Return all available screens.
    pub fn all() -> Result<Vec<Screen>> {
        let screens = DisplayInfo::all()?.iter().map(Screen::new).collect();
        Ok(screens)
    }

    /// Get a screen which includes the point with the given coordinates.
    pub fn from_point(x: i32, y: i32) -> Result<Screen> {
        let display_info = DisplayInfo::from_point(x, y)?;
        Ok(Screen::new(&display_info))
    }

    /// Capture a screenshot of the screen.
    pub fn capture(&self) -> Result<RgbaImage> {
        capture_screen(&self.display_info)
    }

    /// Captures a screenshot of the designated area of the screen.
    pub fn capture_area(&self, x: i32, y: i32, width: u32, height: u32) -> Result<RgbaImage> {
        let display_info = self.display_info;
        let screen_x2 = display_info.x + display_info.width as i32;
        let screen_y2 = display_info.y + display_info.height as i32;

        // Use clamp to ensure x1 and y1 are within the screen bounds
        let x1 = (x + display_info.x).clamp(display_info.x, screen_x2);
        let y1 = (y + display_info.y).clamp(display_info.y, screen_y2);

        // Calculate x2 and y2 and use min to ensure they do not exceed the screen bounds
        let x2 = std::cmp::min(x1 + width as i32, screen_x2);
        let y2 = std::cmp::min(y1 + height as i32, screen_y2);

        // Check if the area size is valid
        if x1 >= x2 || y1 >= y2 {
            return Err(anyhow!("Area size is invalid"));
        }

        // Capture the screen area
        capture_screen_area(
            &display_info,
            x1 - display_info.x,
            y1 - display_info.y,
            (x2 - x1) as u32,
            (y2 - y1) as u32,
        )
    }

    #[cfg(target_os = "windows")]
    /// No capture area check, caller is responsible for calculating
    /// the correct parameters according to Screen::display_info.
    /// Example:
    /// ```
    /// use screenshots::Screen;
    ///
    /// for screen in Screen::all().unwrap() {
    ///    println!("Capturing screen info: {screen:?}");
    ///    let scale = screen.display_info.scale_factor;
    ///    let real_resoltion = ((screen.display_info.width as f64 * scale as f64) as u32, (screen.display_info.height as f64 * scale as f64) as u32);
    ///    let image = screen.capture_area_ignore_area_check(0, 0, real_resoltion.0, real_resoltion.1).unwrap();
    ///    image.save(&format!("screenshot_screen_{}.png", screen.display_info.id)).unwrap();
    /// }
    /// ```
    pub fn capture_area_ignore_area_check(
        &self,
        x: i32,
        y: i32,
        width: u32,
        height: u32,
    ) -> Result<RgbaImage> {
        let display_info = self.display_info;
        capture_screen_area_ignore_sf(&display_info, x, y, width, height)
    }
}

use crate::image_utils::{bgra_to_rgba_image, remove_extra_data};
use anyhow::{anyhow, Result};
use core_graphics::{
    display::{kCGNullWindowID, kCGWindowImageDefault, kCGWindowListOptionOnScreenOnly, CGDisplay},
    geometry::{CGPoint, CGRect, CGSize},
};
use display_info::DisplayInfo;
use image::RgbaImage;

fn capture(display_info: &DisplayInfo, cg_rect: CGRect) -> Result<RgbaImage> {
    let cg_image = CGDisplay::screenshot(
        cg_rect,
        kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID,
        kCGWindowImageDefault,
    )
    .ok_or_else(|| anyhow!("Screen:{} screenshot failed", display_info.id))?;

    let width = cg_image.width();
    let height = cg_image.height();
    let clean_buf = remove_extra_data(
        width,
        height,
        cg_image.bytes_per_row(),
        Vec::from(cg_image.data().bytes()),
    );

    bgra_to_rgba_image(width as u32, height as u32, clean_buf)
}

pub fn capture_screen(display_info: &DisplayInfo) -> Result<RgbaImage> {
    let cg_display = CGDisplay::new(display_info.id);
    capture(display_info, cg_display.bounds())
}

pub fn capture_screen_area(
    display_info: &DisplayInfo,
    x: i32,
    y: i32,
    width: u32,
    height: u32,
) -> Result<RgbaImage> {
    let cg_display = CGDisplay::new(display_info.id);
    let mut cg_rect = cg_display.bounds();
    let origin = cg_rect.origin;

    let rect_x = origin.x + (x as f64);
    let rect_y = origin.y + (y as f64);
    let rect_width = width as f64;
    let rect_height = height as f64;

    cg_rect.origin = CGPoint::new(rect_x, rect_y);
    cg_rect.size = CGSize::new(rect_width, rect_height);

    capture(display_info, cg_rect)
}

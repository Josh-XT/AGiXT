use crate::image_utils::bgra_to_rgba_image;
use anyhow::{anyhow, Result};
use display_info::DisplayInfo;
use fxhash::hash32;
use image::RgbaImage;
use std::{mem, ops::Deref, ptr};
use widestring::U16CString;
use windows::{
    core::PCWSTR,
    Win32::{
        Foundation::{BOOL, LPARAM, RECT},
        Graphics::Gdi::{
            CreateCompatibleBitmap, CreateCompatibleDC, CreateDCW, DeleteDC, DeleteObject,
            EnumDisplayMonitors, GetDIBits, GetMonitorInfoW, GetObjectW, SelectObject,
            SetStretchBltMode, StretchBlt, BITMAP, BITMAPINFO, BITMAPINFOHEADER, DIB_RGB_COLORS,
            HBITMAP, HDC, HMONITOR, MONITORINFOEXW, RGBQUAD, SRCCOPY, STRETCH_HALFTONE,
        },
    },
};

// 自动释放资源
macro_rules! drop_box {
    ($type:tt, $value:expr, $drop:expr) => {{
        struct DropBox($type);

        impl Deref for DropBox {
            type Target = $type;

            fn deref(&self) -> &Self::Target {
                &self.0
            }
        }

        impl Drop for DropBox {
            fn drop(&mut self) {
                $drop(self.0);
            }
        }

        DropBox($value)
    }};
}

fn get_monitor_info_exw(h_monitor: HMONITOR) -> Result<MONITORINFOEXW> {
    let mut monitor_info_exw: MONITORINFOEXW = unsafe { mem::zeroed() };
    monitor_info_exw.monitorInfo.cbSize = mem::size_of::<MONITORINFOEXW>() as u32;
    let monitor_info_exw_ptr = <*mut _>::cast(&mut monitor_info_exw);

    unsafe {
        GetMonitorInfoW(h_monitor, monitor_info_exw_ptr).ok()?;
    };
    Ok(monitor_info_exw)
}

fn get_monitor_info_exw_from_id(id: u32) -> Result<MONITORINFOEXW> {
    let monitor_info_exws: *mut Vec<MONITORINFOEXW> = Box::into_raw(Box::default());

    unsafe {
        EnumDisplayMonitors(
            HDC::default(),
            None,
            Some(monitor_enum_proc),
            LPARAM(monitor_info_exws as isize),
        )
        .ok()?;
    };

    let monitor_info_exws_borrow = unsafe { &Box::from_raw(monitor_info_exws) };

    let monitor_info_exw = monitor_info_exws_borrow
        .iter()
        .find(|&&monitor_info_exw| {
            let sz_device_ptr = monitor_info_exw.szDevice.as_ptr();
            let sz_device_string =
                unsafe { U16CString::from_ptr_str(sz_device_ptr).to_string_lossy() };
            hash32(sz_device_string.as_bytes()) == id
        })
        .ok_or_else(|| anyhow!("Can't find a display by id {id}"))?;

    Ok(*monitor_info_exw)
}

extern "system" fn monitor_enum_proc(
    h_monitor: HMONITOR,
    _: HDC,
    _: *mut RECT,
    state: LPARAM,
) -> BOOL {
    let box_monitor_info_exw = unsafe { Box::from_raw(state.0 as *mut Vec<MONITORINFOEXW>) };
    let state = Box::leak(box_monitor_info_exw);

    match get_monitor_info_exw(h_monitor) {
        Ok(monitor_info_exw) => {
            state.push(monitor_info_exw);
            BOOL::from(true)
        }
        Err(_) => BOOL::from(false),
    }
}

fn capture(display_id: u32, x: i32, y: i32, width: i32, height: i32) -> Result<RgbaImage> {
    let monitor_info_exw = get_monitor_info_exw_from_id(display_id)?;

    let sz_device = monitor_info_exw.szDevice;
    let sz_device_ptr = sz_device.as_ptr();

    let dcw_drop_box = drop_box!(
        HDC,
        unsafe {
            CreateDCW(
                PCWSTR(sz_device_ptr),
                PCWSTR(sz_device_ptr),
                PCWSTR(ptr::null()),
                None,
            )
        },
        |dcw| unsafe { DeleteDC(dcw) }
    );

    let compatible_dc_drop_box = drop_box!(
        HDC,
        unsafe { CreateCompatibleDC(*dcw_drop_box) },
        |compatible_dc| unsafe { DeleteDC(compatible_dc) }
    );

    let h_bitmap_drop_box = drop_box!(
        HBITMAP,
        unsafe { CreateCompatibleBitmap(*dcw_drop_box, width, height) },
        |h_bitmap| unsafe { DeleteObject(h_bitmap) }
    );

    unsafe {
        SelectObject(*compatible_dc_drop_box, *h_bitmap_drop_box);
        SetStretchBltMode(*dcw_drop_box, STRETCH_HALFTONE);
    };

    unsafe {
        StretchBlt(
            *compatible_dc_drop_box,
            0,
            0,
            width,
            height,
            *dcw_drop_box,
            x,
            y,
            width,
            height,
            SRCCOPY,
        )
        .ok()?;
    };

    let mut bitmap_info = BITMAPINFO {
        bmiHeader: BITMAPINFOHEADER {
            biSize: mem::size_of::<BITMAPINFOHEADER>() as u32,
            biWidth: width,
            biHeight: height, // 这里可以传递负数, 但是不知道为什么会报错
            biPlanes: 1,
            biBitCount: 32,
            biCompression: 0,
            biSizeImage: 0,
            biXPelsPerMeter: 0,
            biYPelsPerMeter: 0,
            biClrUsed: 0,
            biClrImportant: 0,
        },
        bmiColors: [RGBQUAD::default(); 1],
    };

    let data = vec![0u8; (width * height) as usize * 4];
    let buf_prt = data.as_ptr() as *mut _;

    let is_success = unsafe {
        GetDIBits(
            *compatible_dc_drop_box,
            *h_bitmap_drop_box,
            0,
            height as u32,
            Some(buf_prt),
            &mut bitmap_info,
            DIB_RGB_COLORS,
        ) == 0
    };

    if is_success {
        return Err(anyhow!("Get RGBA data failed"));
    }

    let mut bitmap = BITMAP::default();
    let bitmap_ptr = <*mut _>::cast(&mut bitmap);

    unsafe {
        // Get the BITMAP from the HBITMAP.
        GetObjectW(
            *h_bitmap_drop_box,
            mem::size_of::<BITMAP>() as i32,
            Some(bitmap_ptr),
        );
    }

    // 旋转图像,图像数据是倒置的
    let mut chunks: Vec<Vec<u8>> = data
        .chunks(width as usize * 4)
        .map(|x| x.to_vec())
        .collect();

    chunks.reverse();

    bgra_to_rgba_image(
        bitmap.bmWidth as u32,
        bitmap.bmHeight as u32,
        chunks.concat(),
    )
}

pub fn capture_screen(display_info: &DisplayInfo) -> Result<RgbaImage> {
    let width = ((display_info.width as f32) * display_info.scale_factor) as i32;
    let height = ((display_info.height as f32) * display_info.scale_factor) as i32;

    capture(display_info.id, 0, 0, width, height)
}

pub fn capture_screen_area(
    display_info: &DisplayInfo,
    x: i32,
    y: i32,
    width: u32,
    height: u32,
) -> Result<RgbaImage> {
    let area_x = ((x as f32) * display_info.scale_factor) as i32;
    let area_y = ((y as f32) * display_info.scale_factor) as i32;
    let area_width = ((width as f32) * display_info.scale_factor) as i32;
    let area_height = ((height as f32) * display_info.scale_factor) as i32;

    capture(display_info.id, area_x, area_y, area_width, area_height)
}

pub fn capture_screen_area_ignore_sf(
    display_info: &DisplayInfo,
    x: i32,
    y: i32,
    width: u32,
    height: u32,
) -> Result<RgbaImage> {
    capture(display_info.id, x, y, width as i32, height as i32)
}

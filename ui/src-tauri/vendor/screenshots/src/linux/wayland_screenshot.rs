use crate::image_utils::png_to_rgba_image;
use anyhow::{anyhow, Result};
use dbus::{
    arg::{AppendAll, Iter, IterAppend, PropMap, ReadAll, RefArg, TypeMismatchError, Variant},
    blocking::Connection,
    message::{MatchRule, SignalArgs},
};
use image::RgbaImage;
use libwayshot::{CaptureRegion, WayshotConnection};
use percent_encoding::percent_decode;
use std::{
    collections::HashMap,
    env::temp_dir,
    fs::{self},
    sync::{Arc, Mutex},
    time::{Duration, SystemTime, UNIX_EPOCH},
};

#[derive(Debug)]
pub struct OrgFreedesktopPortalRequestResponse {
    pub status: u32,
    pub results: PropMap,
}

impl AppendAll for OrgFreedesktopPortalRequestResponse {
    fn append(&self, i: &mut IterAppend) {
        RefArg::append(&self.status, i);
        RefArg::append(&self.results, i);
    }
}

impl ReadAll for OrgFreedesktopPortalRequestResponse {
    fn read(i: &mut Iter) -> Result<Self, TypeMismatchError> {
        Ok(OrgFreedesktopPortalRequestResponse {
            status: i.read()?,
            results: i.read()?,
        })
    }
}

impl SignalArgs for OrgFreedesktopPortalRequestResponse {
    const NAME: &'static str = "Response";
    const INTERFACE: &'static str = "org.freedesktop.portal.Request";
}

fn org_gnome_shell_screenshot(
    conn: &Connection,
    x: i32,
    y: i32,
    width: i32,
    height: i32,
) -> Result<RgbaImage> {
    let proxy = conn.with_proxy(
        "org.gnome.Shell.Screenshot",
        "/org/gnome/Shell/Screenshot",
        Duration::from_secs(10),
    );

    let timestamp = SystemTime::now().duration_since(UNIX_EPOCH)?;

    let dirname = temp_dir().join("screenshot");

    fs::create_dir_all(&dirname)?;

    let mut path = dirname.join(timestamp.as_micros().to_string());
    path.set_extension("png");

    let filename = path.to_string_lossy().to_string();

    proxy.method_call::<(), _, _, _>(
        "org.gnome.Shell.Screenshot",
        "ScreenshotArea",
        (x, y, width, height, false, &filename),
    )?;

    let rgba_image = png_to_rgba_image(&filename, 0, 0, width, height)?;

    fs::remove_file(&filename)?;

    Ok(rgba_image)
}

fn org_freedesktop_portal_screenshot(
    conn: &Connection,
    x: i32,
    y: i32,
    width: i32,
    height: i32,
) -> Result<RgbaImage> {
    let status: Arc<Mutex<Option<u32>>> = Arc::new(Mutex::new(None));
    let status_res = status.clone();
    let path: Arc<Mutex<String>> = Arc::new(Mutex::new(String::new()));
    let path_res = path.clone();

    let match_rule = MatchRule::new_signal("org.freedesktop.portal.Request", "Response");
    conn.add_match(
        match_rule,
        move |response: OrgFreedesktopPortalRequestResponse, _conn, _msg| {
            if let Ok(mut status) = status.lock() {
                *status = Some(response.status);
            }

            let uri = response.results.get("uri").and_then(|str| str.as_str());
            if let (Some(uri_str), Ok(mut path)) = (uri, path.lock()) {
                *path = uri_str[7..].to_string();
            }

            true
        },
    )?;

    let proxy = conn.with_proxy(
        "org.freedesktop.portal.Desktop",
        "/org/freedesktop/portal/desktop",
        Duration::from_millis(10000),
    );

    let mut options: PropMap = HashMap::new();
    options.insert(
        String::from("handle_token"),
        Variant(Box::new(String::from("1234"))),
    );
    options.insert(String::from("modal"), Variant(Box::new(true)));
    options.insert(String::from("interactive"), Variant(Box::new(false)));

    proxy.method_call::<(), _, _, _>(
        "org.freedesktop.portal.Screenshot",
        "Screenshot",
        ("", options),
    )?;

    // wait 60 seconds for user interaction
    for _ in 0..60 {
        let result = conn.process(Duration::from_millis(1000))?;
        let status = status_res
            .lock()
            .map_err(|_| anyhow!("Get status lock failed"))?;

        if result && status.is_some() {
            break;
        }
    }

    let status = status_res
        .lock()
        .map_err(|_| anyhow!("Get status lock failed"))?;
    let status = *status;

    let path = path_res
        .lock()
        .map_err(|_| anyhow!("Get path lock failed"))?;
    let path = &*path;

    if status.ne(&Some(0)) || path.is_empty() {
        if !path.is_empty() {
            fs::remove_file(path)?;
        }
        return Err(anyhow!("Screenshot failed or canceled",));
    }

    let filename = percent_decode(path.as_bytes()).decode_utf8()?.to_string();
    let rgba_image = png_to_rgba_image(&filename, x, y, width, height)?;

    fs::remove_file(&filename)?;

    Ok(rgba_image)
}

fn wlr_screenshot(
    x_coordinate: i32,
    y_coordinate: i32,
    width: i32,
    height: i32,
) -> Result<RgbaImage> {
    let wayshot_connection = WayshotConnection::new()?;
    let capture_region = CaptureRegion {
        x_coordinate,
        y_coordinate,
        width,
        height,
    };
    let rgba_image = wayshot_connection.screenshot(capture_region, false)?;

    Ok(rgba_image)
}

// TODO: 失败后尝试删除文件
pub fn wayland_screenshot(x: i32, y: i32, width: i32, height: i32) -> Result<RgbaImage> {
    let conn = Connection::new_session()?;

    // TODO: work out if compositor is wlroots before attempting anything else
    org_gnome_shell_screenshot(&conn, x, y, width, height)
        .or_else(|_| org_freedesktop_portal_screenshot(&conn, x, y, width, height))
        .or_else(|_| wlr_screenshot(x, y, width, height))
}

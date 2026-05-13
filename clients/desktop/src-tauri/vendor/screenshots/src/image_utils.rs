use anyhow::{anyhow, Result};
use image::RgbaImage;

pub fn vec_to_rgba_image(width: u32, height: u32, buf: Vec<u8>) -> Result<RgbaImage> {
    RgbaImage::from_vec(width, height, buf).ok_or(anyhow!("buffer not big enough"))
}

#[cfg(any(target_os = "windows", target_os = "macos", test))]
pub fn bgra_to_rgba_image(width: u32, height: u32, buf: Vec<u8>) -> Result<RgbaImage> {
    let mut rgba_buf = buf.clone();

    for (src, dst) in buf.chunks_exact(4).zip(rgba_buf.chunks_exact_mut(4)) {
        dst[0] = src[2];
        dst[1] = src[1];
        dst[2] = src[0];
        dst[3] = src[3];
    }
    vec_to_rgba_image(width, height, rgba_buf)
}

/// Some platforms e.g. MacOS can have extra bytes at the end of each row.
///
/// See
/// https://github.com/nashaofu/screenshots-rs/issues/29
/// https://github.com/nashaofu/screenshots-rs/issues/38
#[cfg(any(target_os = "macos", test))]
pub fn remove_extra_data(
    width: usize,
    height: usize,
    bytes_per_row: usize,
    buf: Vec<u8>,
) -> Vec<u8> {
    let extra_bytes_per_row = bytes_per_row - width * 4;
    let mut result = Vec::with_capacity(buf.len() - extra_bytes_per_row * height);
    for row in buf.chunks_exact(bytes_per_row) {
        result.extend_from_slice(&row[..width * 4]);
    }

    result
}

#[cfg(any(target_os = "linux", test))]
pub fn png_to_rgba_image(
    filename: &String,
    x: i32,
    y: i32,
    width: i32,
    height: i32,
) -> Result<RgbaImage> {
    use image::open;

    let mut dynamic_image = open(filename)?;
    dynamic_image = dynamic_image.crop(x as u32, y as u32, width as u32, height as u32);
    Ok(dynamic_image.to_rgba8())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bgra() {
        let image = bgra_to_rgba_image(2, 1, vec![1, 2, 3, 4, 255, 254, 253, 252]).unwrap();
        assert_eq!(
            image,
            RgbaImage::from_vec(2, 1, vec![3, 2, 1, 4, 253, 254, 255, 252]).unwrap()
        );
    }

    #[test]
    fn extra_data() {
        let clean = remove_extra_data(
            2,
            2,
            9,
            vec![
                1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19,
            ],
        );
        assert_eq!(
            clean,
            vec![1, 2, 3, 4, 5, 6, 7, 8, 11, 12, 13, 14, 15, 16, 17, 18]
        );
    }
}

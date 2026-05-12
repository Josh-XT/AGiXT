# 📷 Screenshots

## Move to [XCap](https://crates.io/crates/xcap)

Screenshots is a cross-platform screenshots library for MacOS, Windows, Linux (X11, Wayland) written in Rust. It provides a simple API for capturing screenshots of a screen or a specific area of a screen.

## Example

The following example shows how to capture screenshots of all screens and a specific area of a screen.

```rust
use screenshots::Screen;
use std::time::Instant;

fn main() {
    let start = Instant::now();
    let screens = Screen::all().unwrap();

    for screen in screens {
        println!("capturer {screen:?}");
        let mut image = screen.capture().unwrap();
        image
            .save(format!("target/{}.png", screen.display_info.id))
            .unwrap();

        image = screen.capture_area(300, 300, 300, 300).unwrap();
        image
            .save(format!("target/{}-2.png", screen.display_info.id))
            .unwrap();
    }

    let screen = Screen::from_point(100, 100).unwrap();
    println!("capturer {screen:?}");

    let image = screen.capture_area(300, 300, 300, 300).unwrap();
    image.save("target/capture_display_with_point.png").unwrap();
    println!("运行耗时: {:?}", start.elapsed());
}
```

## Linux Requirements

On Linux, you need to install `libxcb`, `libxrandr`, and `dbus`.

Debian/Ubuntu:

```sh
apt-get install libxcb1 libxrandr2 libdbus-1-3
```

Alpine:

```sh
apk add libxcb libxrandr dbus
```

ArchLinux:

```sh
pacman -S libxcb libxrandr dbus
```

## License

This project is licensed under the Apache License. See the [LICENSE](LICENSE) file for details.

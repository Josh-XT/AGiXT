#!/usr/bin/env python3
"""Verify that an APK contains the expected AGiXT launcher icon content."""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import zlib
import zipfile
from pathlib import Path


def paeth(left: int, up: int, up_left: int) -> int:
    p = left + up - up_left
    pa = abs(p - left)
    pb = abs(p - up)
    pc = abs(p - up_left)
    if pa <= pb and pa <= pc:
        return left
    if pb <= pc:
        return up
    return up_left


def png_signature(data: bytes) -> tuple[int, int, int, int, int, int, str]:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not a PNG")

    pos = 8
    width = height = bit_depth = color_type = None
    palette: list[tuple[int, int, int]] = []
    transparency = b""
    idat: list[bytes] = []
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        chunk_type = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        pos += length + 12
        if chunk_type == b"IHDR":
            (
                width,
                height,
                bit_depth,
                color_type,
                compression,
                filter_method,
                interlace,
            ) = struct.unpack(">IIBBBBB", chunk)
            if compression != 0 or filter_method != 0 or interlace != 0:
                raise ValueError("unsupported PNG compression/filter/interlace")
            if bit_depth != 8:
                raise ValueError(f"unsupported PNG bit depth {bit_depth}")
        elif chunk_type == b"tRNS":
            transparency = chunk
        elif chunk_type == b"PLTE":
            palette = [
                (chunk[i], chunk[i + 1], chunk[i + 2]) for i in range(0, len(chunk), 3)
            ]
        elif chunk_type == b"IDAT":
            idat.append(chunk)
        elif chunk_type == b"IEND":
            break

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if channels is None or width is None or height is None:
        raise ValueError("unsupported or incomplete PNG")

    stride = width * channels
    raw = zlib.decompress(b"".join(idat))
    prev = [0] * stride
    offset = 0
    min_x, min_y = width, height
    max_x, max_y = -1, -1
    normalized_pixels = bytearray()
    transparent_gray = (
        struct.unpack(">H", transparency[:2])[0]
        if color_type == 0 and len(transparency) >= 2
        else None
    )
    transparent_rgb = (
        struct.unpack(">HHH", transparency[:6])
        if color_type == 2 and len(transparency) >= 6
        else None
    )

    for y in range(height):
        filter_type = raw[offset]
        offset += 1
        scanline = list(raw[offset : offset + stride])
        offset += stride
        recon = [0] * stride
        for x in range(stride):
            left = recon[x - channels] if x >= channels else 0
            up = prev[x]
            up_left = prev[x - channels] if x >= channels else 0
            value = scanline[x]
            if filter_type == 0:
                recon[x] = value
            elif filter_type == 1:
                recon[x] = (value + left) & 0xFF
            elif filter_type == 2:
                recon[x] = (value + up) & 0xFF
            elif filter_type == 3:
                recon[x] = (value + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                recon[x] = (value + paeth(left, up, up_left)) & 0xFF
            else:
                raise ValueError(f"unsupported PNG filter {filter_type}")

        for x in range(width):
            base = x * channels
            if color_type == 6:
                red, green, blue = recon[base : base + 3]
                alpha = recon[base + 3]
            elif color_type == 4:
                red = green = blue = recon[base]
                alpha = recon[base + 1]
            elif color_type == 3:
                index = recon[base]
                red, green, blue = palette[index]
                alpha = transparency[index] if index < len(transparency) else 255
            elif color_type == 0:
                red = green = blue = recon[base]
                alpha = (
                    0
                    if transparent_gray is not None and recon[base] == transparent_gray
                    else 255
                )
            elif color_type == 2:
                red, green, blue = recon[base : base + 3]
                rgb = (red, green, blue)
                alpha = (
                    0 if transparent_rgb is not None and rgb == transparent_rgb else 255
                )
            else:
                red = green = blue = 0
                alpha = 0
            normalized_pixels.extend((red, green, blue, alpha))
            if alpha:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
        prev = recon

    bbox = (
        (0, 0, 0, 0)
        if max_x < 0
        else (max_x - min_x + 1, max_y - min_y + 1, min_x, min_y)
    )
    digest = hashlib.sha256(normalized_pixels).hexdigest()
    return (width, height, *bbox, digest)


def verify_icon(apk_path: Path, expected_icon_path: Path) -> None:
    expected = png_signature(expected_icon_path.read_bytes())
    matches: list[str] = []
    with zipfile.ZipFile(apk_path) as apk:
        for name in apk.namelist():
            if (
                not name.startswith("res/")
                or not name.endswith(".png")
                or name.endswith(".9.png")
            ):
                continue
            try:
                actual = png_signature(apk.read(name))
            except Exception:
                continue
            if actual == expected:
                matches.append(name)

    if not matches:
        print(
            f"No packaged PNG matched AGiXT launcher signature {expected}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(f"Launcher icon content matched {matches[0]} with signature {expected}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("apk", type=Path)
    parser.add_argument("expected_icon", type=Path)
    args = parser.parse_args()
    verify_icon(args.apk, args.expected_icon)


if __name__ == "__main__":
    main()

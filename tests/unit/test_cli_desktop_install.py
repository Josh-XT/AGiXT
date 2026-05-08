import os
import sys

import pytest


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
AGIXT_SRC = os.path.join(PROJECT_ROOT, "agixt")
if AGIXT_SRC not in sys.path:
    sys.path.insert(0, AGIXT_SRC)

from agixt import cli  # noqa: E402


def test_find_extracted_desktop_binary_finds_tauri_main_binary(tmp_path):
    bin_dir = tmp_path / "usr" / "bin"
    bin_dir.mkdir(parents=True)
    sidecar = bin_dir / "agixt-cli"
    sidecar.write_text("sidecar", encoding="utf-8")
    desktop = bin_dir / "agixt"
    desktop.write_text("desktop", encoding="utf-8")

    assert cli._find_extracted_desktop_binary(tmp_path) == desktop


def test_find_extracted_desktop_binary_ignores_cli_sidecar(tmp_path):
    bin_dir = tmp_path / "usr" / "bin"
    bin_dir.mkdir(parents=True)
    sidecar = bin_dir / "agixt-cli"
    sidecar.write_text("sidecar", encoding="utf-8")

    with pytest.raises(cli.CLIError):
        cli._find_extracted_desktop_binary(tmp_path)


def test_desktop_launch_environment_scrubs_snap_runtime(monkeypatch):
    monkeypatch.setenv("SNAP", "/snap/code/235")
    monkeypatch.setenv("SNAP_NAME", "code")
    monkeypatch.setenv("SNAP_LIBRARY_PATH", "/var/lib/snapd/lib/gl")
    monkeypatch.setenv("GTK_PATH", "/snap/code/235/usr/lib/gtk-3.0")
    monkeypatch.setenv("GDK_PIXBUF_MODULEDIR", "/snap/code/235/usr/lib/loaders")
    monkeypatch.setenv("XDG_DATA_DIRS", "/snap/code/235/usr/share")
    monkeypatch.setenv("XDG_DATA_DIRS_VSCODE_SNAP_ORIG", "/usr/share")
    monkeypatch.setenv("XDG_CONFIG_DIRS_VSCODE_SNAP_ORIG", "/etc/xdg")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/snap/core20/current/lib")

    env = cli._desktop_launch_environment("linux")

    assert "SNAP" not in env
    assert "SNAP_NAME" not in env
    assert "SNAP_LIBRARY_PATH" not in env
    assert "GTK_PATH" not in env
    assert "GDK_PIXBUF_MODULEDIR" not in env
    assert "LD_LIBRARY_PATH" not in env
    assert env["XDG_DATA_DIRS"] == "/usr/share"
    assert env["XDG_CONFIG_DIRS"] == "/etc/xdg"

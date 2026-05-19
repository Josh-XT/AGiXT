#!/usr/bin/env python3
"""Patch the generated Tauri Android app Gradle file for CI preview APKs."""

from __future__ import annotations

import argparse
from pathlib import Path


TAURI_PROPERTIES_BLOCK = """val tauriProperties = Properties().apply {
    val propFile = file("tauri.properties")
    if (propFile.exists()) {
        propFile.inputStream().use { load(it) }
    }
}

"""

RELEASE_SIGNING_BLOCK = """val releaseKeystoreBase64 = System.getenv("ANDROID_RELEASE_KEYSTORE_BASE64").orEmpty()
val releaseKeystorePassword = System.getenv("ANDROID_RELEASE_KEYSTORE_PASSWORD").orEmpty()
val releaseKeyAlias = System.getenv("ANDROID_RELEASE_KEY_ALIAS").orEmpty()
val releaseKeyPassword = System.getenv("ANDROID_RELEASE_KEY_PASSWORD").orEmpty()
val hasReleaseSigning = releaseKeystoreBase64.isNotBlank() &&
    releaseKeystorePassword.isNotBlank() &&
    releaseKeyAlias.isNotBlank() &&
    releaseKeyPassword.isNotBlank()
val releaseKeystoreFile = layout.buildDirectory.file("agixt-release-upload.jks").get().asFile

if (hasReleaseSigning) {
    releaseKeystoreFile.parentFile.mkdirs()
    releaseKeystoreFile.writeBytes(Base64.getDecoder().decode(releaseKeystoreBase64))
}

"""

SIGNING_CONFIGS_BLOCK = """    signingConfigs {
        if (hasReleaseSigning) {
            create("agixtRelease") {
                storeFile = releaseKeystoreFile
                storePassword = releaseKeystorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
            }
        }
    }
    buildTypes {
"""

RELEASE_BUILD_ORIGINAL = """        getByName("release") {
            isMinifyEnabled = true
            proguardFiles(
"""

RELEASE_BUILD_PATCHED = """        getByName("release") {
            isMinifyEnabled = false
            signingConfig = if (hasReleaseSigning) {
                signingConfigs.getByName("agixtRelease")
            } else {
                signingConfigs.getByName("debug")
            }
            proguardFiles(
"""


def replace_once(text: str, old: str, new: str, description: str) -> str:
    if old not in text:
        raise SystemExit(
            f"Could not find {description} in generated Android Gradle file"
        )
    return text.replace(old, new, 1)


def patch_gradle(path: Path) -> None:
    text = path.read_text()

    if "ANDROID_RELEASE_KEYSTORE_BASE64" not in text:
        text = replace_once(
            text,
            "import java.util.Properties\n",
            "import java.util.Base64\nimport java.util.Properties\n",
            "Properties import",
        )
        text = replace_once(
            text,
            TAURI_PROPERTIES_BLOCK,
            TAURI_PROPERTIES_BLOCK + RELEASE_SIGNING_BLOCK,
            "tauriProperties block",
        )

    if "signingConfigs {" not in text:
        text = replace_once(
            text,
            "    buildTypes {\n",
            SIGNING_CONFIGS_BLOCK,
            "buildTypes block",
        )

    if RELEASE_BUILD_ORIGINAL in text:
        text = text.replace(RELEASE_BUILD_ORIGINAL, RELEASE_BUILD_PATCHED, 1)
    elif 'signingConfigs.getByName("agixtRelease")' not in text:
        raise SystemExit("Could not patch generated Android release build type")

    text = text.replace(
        "packaging {                jniLibs",
        "packaging {\n                jniLibs",
    )
    path.write_text(text)
    print(f"Patched Android Gradle preview build config: {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("gradle_file", type=Path)
    args = parser.parse_args()
    patch_gradle(args.gradle_file)


if __name__ == "__main__":
    main()

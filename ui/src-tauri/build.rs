use std::{env, path::PathBuf, process::Command};

fn main() {
    emit_build_metadata();
    build_lc3_decoder();
    tauri_build::build()
}

fn build_lc3_decoder() {
    let target = env::var("TARGET").unwrap_or_default();
    if target.contains("ios") {
        return;
    }

    let files = [
        "attdet.c", "bits.c", "bwdet.c", "energy.c", "lc3.c", "ltpf.c", "mdct.c", "plc.c", "sns.c",
        "spec.c", "tables.c", "tns.c",
    ];
    let mut build = cc::Build::new();
    build.include("vendor/lc3");
    build.flag_if_supported("-ffast-math");
    for file in files {
        let path = format!("vendor/lc3/{file}");
        println!("cargo:rerun-if-changed={path}");
        build.file(path);
    }
    println!("cargo:rerun-if-changed=vendor/lc3/lc3.h");
    println!("cargo:rerun-if-changed=vendor/lc3/lc3_private.h");
    build.compile("agixt_g1_lc3");
}

fn emit_build_metadata() {
    let repo_root = git_output(None, &["rev-parse", "--show-toplevel"])
        .map(PathBuf::from)
        .or_else(|| {
            env::current_dir()
                .ok()
                .and_then(|p| p.parent().and_then(|p| p.parent()).map(PathBuf::from))
        });
    let build_id = env::var("AGIXT_DESKTOP_BUILD_ID")
        .ok()
        .filter(|v| !v.trim().is_empty())
        .or_else(|| {
            git_output(
                repo_root.as_deref(),
                &[
                    "log",
                    "-1",
                    "--format=%cd",
                    "--date=format:%Y%m%d_%H%M%S",
                    "--",
                    "ui",
                ],
            )
        })
        .unwrap_or_else(|| "dev".into());
    let commit = git_output(repo_root.as_deref(), &["rev-parse", "--short=12", "HEAD"])
        .unwrap_or_else(|| "unknown".into());

    println!("cargo:rerun-if-env-changed=AGIXT_DESKTOP_BUILD_ID");
    println!("cargo:rustc-env=AGIXT_DESKTOP_BUILD_ID={build_id}");
    println!("cargo:rustc-env=AGIXT_DESKTOP_COMMIT={commit}");
}

fn git_output(cwd: Option<&std::path::Path>, args: &[&str]) -> Option<String> {
    let mut command = Command::new("git");
    command.args(args);
    if let Some(cwd) = cwd {
        command.current_dir(cwd);
    }
    let output = command.output().ok()?;
    if !output.status.success() {
        return None;
    }
    let value = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if value.is_empty() {
        None
    } else {
        Some(value)
    }
}

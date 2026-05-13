use std::{env, path::PathBuf, process::Command};

fn main() {
    emit_build_metadata();
    tauri_build::build()
}

fn emit_build_metadata() {
    let repo_root = env::current_dir().ok().and_then(|p| {
        p.parent()
            .and_then(|p| p.parent())
            .and_then(|p| p.parent())
            .map(PathBuf::from)
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
                    "clients/desktop",
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

use std::ffi::OsString;
use std::process::Command;

#[cfg(unix)]
use std::os::unix::process::CommandExt;

fn main() {
    let args: Vec<OsString> = std::env::args_os().skip(1).collect();
    let binary = std::env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(|parent| parent.join("agixt")))
        .filter(|path| path.is_file())
        .map(OsString::from)
        .unwrap_or_else(|| OsString::from("agixt"));
    let mut command = Command::new(binary);
    command.args(args);

    #[cfg(unix)]
    {
        let error = command.exec();
        eprintln!("failed to launch agixt: {error}");
        std::process::exit(127);
    }

    #[cfg(not(unix))]
    {
        match command.spawn() {
            Ok(mut child) => match child.wait() {
                Ok(status) => std::process::exit(status.code().unwrap_or(1)),
                Err(error) => {
                    eprintln!("failed to wait for agixt: {error}");
                    std::process::exit(1);
                }
            },
            Err(error) => {
                eprintln!("failed to launch agixt: {error}");
                std::process::exit(127);
            }
        }
    }
}

//! Cross-platform filesystem operations for the AGiXT Desktop client.
//!
//! Mirrors the read/write/list/move/delete pattern from
//! `xtsystems_extensions/machines.py` and `rust_endpoint_agent`'s remote
//! file tools, but applied to the local user machine the desktop app is
//! running on. The agent uses these to:
//!
//!   * Pull a file off the user's disk into the AGiXT workspace
//!     (`fs_read` + `workspace_upload` round-trip).
//!   * Push a workspace file back onto the user's disk
//!     (`workspace_download` + `fs_write`).
//!   * Browse / create / move / delete files and folders directly.
//!   * Apply targeted edits (`fs_edit`) without uploading the whole file.
//!
//! All paths are tilde-expanded (`~/foo` → `$HOME/foo`) and
//! environment-variable-expanded on Windows (`%USERPROFILE%` etc) so the
//! agent can reason in the same pseudo-paths a user would type.
//!
//! Safety:
//! * Every IPC handler that calls into here also gates on
//!   `allow_client_commands` in `DesktopSettings`.
//! * `fs_write` and `fs_edit` are atomic per-file (write to tempfile in the
//!   same directory, then rename) so partial failures don't corrupt files.
//! * Symlinks are followed for read but never created.

use anyhow::{anyhow, Context, Result};
use base64::engine::general_purpose::STANDARD as BASE64;
use base64::Engine as _;
use serde::{Deserialize, Serialize};
use std::fs;
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use std::time::SystemTime;

/// 10 MiB max read-into-memory; larger reads return an error so the agent
/// is forced to use streamed/chunked reads (or a future `fs_read_range`).
const MAX_READ_BYTES: u64 = 10 * 1024 * 1024;

#[derive(Debug, Clone, Serialize)]
pub struct FsEntry {
    pub name: String,
    pub path: String,
    pub kind: &'static str, // "file" | "directory" | "symlink" | "other"
    pub size: u64,
    pub modified_unix: Option<i64>,
    pub readonly: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct FsStat {
    pub path: String,
    pub exists: bool,
    pub kind: &'static str,
    pub size: u64,
    pub modified_unix: Option<i64>,
    pub readonly: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct ReadResult {
    pub path: String,
    pub size: u64,
    /// "utf8" or "base64" — base64 is returned when the file isn't valid UTF-8.
    pub encoding: &'static str,
    pub content: String,
    pub truncated: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct WriteResult {
    pub path: String,
    pub bytes_written: u64,
    pub created: bool,
}

#[derive(Debug, Clone, Deserialize)]
pub struct EditOp {
    /// Exact substring to look for. Must appear *exactly once* in the file
    /// (matching the `Edit` tool semantics) unless `replace_all` is true.
    pub find: String,
    pub replace: String,
    #[serde(default)]
    pub replace_all: bool,
}

/// Resolve a user-typed path to an absolute path:
/// * `~`           → home directory
/// * `~user`       → that user's home (Unix) or `C:\Users\user` (Windows)
/// * `$VAR` / `%VAR%` → expanded from the process environment
/// * relative      → resolved against `cwd` if provided, else current dir
pub fn resolve(path: &str, cwd: Option<&Path>) -> Result<PathBuf> {
    let expanded = expand(path)?;
    let p = if expanded.is_absolute() {
        expanded
    } else if let Some(c) = cwd {
        c.join(expanded)
    } else {
        std::env::current_dir()?.join(expanded)
    };
    Ok(normalize(p))
}

fn expand(path: &str) -> Result<PathBuf> {
    let mut s = path.to_string();
    // ~ at start
    if let Some(rest) = s.strip_prefix("~/") {
        let home = dirs::home_dir().ok_or_else(|| anyhow!("no home directory"))?;
        return Ok(home.join(rest));
    }
    if s == "~" {
        return Ok(dirs::home_dir().ok_or_else(|| anyhow!("no home directory"))?);
    }
    // %VAR% on any platform (mostly Windows).
    while let Some(start) = s.find('%') {
        let rest = &s[start + 1..];
        if let Some(end) = rest.find('%') {
            let name = &rest[..end];
            let val = std::env::var(name).unwrap_or_default();
            let new = format!("{}{}{}", &s[..start], val, &rest[end + 1..]);
            s = new;
        } else {
            break;
        }
    }
    // $VAR (Unix-style).
    let mut out = String::with_capacity(s.len());
    let mut chars = s.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '$' {
            let mut name = String::new();
            while let Some(&nc) = chars.peek() {
                if nc.is_alphanumeric() || nc == '_' {
                    name.push(nc);
                    chars.next();
                } else {
                    break;
                }
            }
            if name.is_empty() {
                out.push('$');
            } else {
                out.push_str(&std::env::var(&name).unwrap_or_default());
            }
        } else {
            out.push(c);
        }
    }
    Ok(PathBuf::from(out))
}

fn normalize(p: PathBuf) -> PathBuf {
    let mut out = PathBuf::new();
    for comp in p.components() {
        match comp {
            Component::ParentDir => {
                out.pop();
            }
            Component::CurDir => {}
            other => out.push(other.as_os_str()),
        }
    }
    out
}

fn entry_kind(meta: &fs::Metadata) -> &'static str {
    if meta.is_dir() {
        "directory"
    } else if meta.is_symlink() {
        "symlink"
    } else if meta.is_file() {
        "file"
    } else {
        "other"
    }
}

fn modified_unix(meta: &fs::Metadata) -> Option<i64> {
    meta.modified()
        .ok()
        .and_then(|m| m.duration_since(SystemTime::UNIX_EPOCH).ok())
        .map(|d| d.as_secs() as i64)
}

pub fn read(path: &str) -> Result<ReadResult> {
    let p = resolve(path, None)?;
    let meta = fs::metadata(&p).with_context(|| format!("stat {}", p.display()))?;
    let size = meta.len();
    let truncated = size > MAX_READ_BYTES;
    let to_read = if truncated {
        MAX_READ_BYTES as usize
    } else {
        size as usize
    };

    let bytes = if truncated {
        use std::io::Read;
        let mut f = fs::File::open(&p)?;
        let mut buf = vec![0u8; to_read];
        f.read_exact(&mut buf)?;
        buf
    } else {
        fs::read(&p)?
    };

    let (encoding, content) = match std::str::from_utf8(&bytes) {
        Ok(s) => ("utf8", s.to_string()),
        Err(_) => ("base64", BASE64.encode(&bytes)),
    };
    Ok(ReadResult {
        path: p.display().to_string(),
        size,
        encoding,
        content,
        truncated,
    })
}

/// Write `content` (UTF-8 or base64-decoded) to `path`. If the file
/// doesn't exist it's created. Atomic via temp-file-then-rename in the
/// destination directory.
pub fn write(
    path: &str,
    content: &str,
    encoding: Option<&str>,
    create_dirs: bool,
) -> Result<WriteResult> {
    let p = resolve(path, None)?;
    let bytes = match encoding.unwrap_or("utf8") {
        "utf8" | "text" => content.as_bytes().to_vec(),
        "base64" | "b64" => BASE64
            .decode(content.as_bytes())
            .context("decode base64 content")?,
        other => return Err(anyhow!("unknown encoding: {other}")),
    };
    if create_dirs {
        if let Some(parent) = p.parent() {
            fs::create_dir_all(parent).with_context(|| format!("mkdir -p {}", parent.display()))?;
        }
    }
    let created = !p.exists();
    let dir = p.parent().unwrap_or(Path::new("."));
    let mut tmp = tempfile_in(dir)?;
    tmp.write_all(&bytes)?;
    tmp.flush()?;
    let tmp_path = tmp.path().to_path_buf();
    drop(tmp);
    fs::rename(&tmp_path, &p)
        .with_context(|| format!("rename {} → {}", tmp_path.display(), p.display()))?;
    Ok(WriteResult {
        path: p.display().to_string(),
        bytes_written: bytes.len() as u64,
        created,
    })
}

pub fn append(path: &str, content: &str, encoding: Option<&str>) -> Result<WriteResult> {
    let p = resolve(path, None)?;
    let bytes = match encoding.unwrap_or("utf8") {
        "utf8" | "text" => content.as_bytes().to_vec(),
        "base64" | "b64" => BASE64.decode(content.as_bytes()).context("decode base64")?,
        other => return Err(anyhow!("unknown encoding: {other}")),
    };
    let created = !p.exists();
    let mut f = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&p)
        .with_context(|| format!("open {} for append", p.display()))?;
    f.write_all(&bytes)?;
    f.flush()?;
    Ok(WriteResult {
        path: p.display().to_string(),
        bytes_written: bytes.len() as u64,
        created,
    })
}

/// Apply one or more find/replace edits atomically. Each edit's `find`
/// must appear *exactly once* unless `replace_all` is set. Modeled on the
/// behavior of the AGiXT `Edit` tool / Claude Code's Edit tool so the
/// agent can use the same mental model.
pub fn edit(path: &str, ops: &[EditOp]) -> Result<WriteResult> {
    let p = resolve(path, None)?;
    let original = fs::read_to_string(&p).with_context(|| format!("read {}", p.display()))?;
    let mut content = original.clone();
    for (i, op) in ops.iter().enumerate() {
        if op.replace_all {
            if !content.contains(&op.find) {
                return Err(anyhow!("edit {i}: find string not found"));
            }
            content = content.replace(&op.find, &op.replace);
        } else {
            let count = content.matches(&op.find).count();
            if count == 0 {
                return Err(anyhow!("edit {i}: find string not found"));
            }
            if count > 1 {
                return Err(anyhow!(
                    "edit {i}: find string appears {count} times; pass replace_all:true or supply more context"
                ));
            }
            content = content.replacen(&op.find, &op.replace, 1);
        }
    }
    if content == original {
        // No-op edit — write nothing, but report success.
        return Ok(WriteResult {
            path: p.display().to_string(),
            bytes_written: 0,
            created: false,
        });
    }
    write(&p.display().to_string(), &content, Some("utf8"), false)
}

pub fn list(path: &str) -> Result<Vec<FsEntry>> {
    let p = resolve(path, None)?;
    let mut out = Vec::new();
    for entry in fs::read_dir(&p).with_context(|| format!("readdir {}", p.display()))? {
        let entry = entry?;
        let name = entry.file_name().to_string_lossy().to_string();
        let ep = entry.path();
        let meta = entry.metadata()?;
        out.push(FsEntry {
            name,
            path: ep.display().to_string(),
            kind: entry_kind(&meta),
            size: meta.len(),
            modified_unix: modified_unix(&meta),
            readonly: meta.permissions().readonly(),
        });
    }
    // Directories first, then symlinks, then files; alphabetical within group.
    let rank = |k: &str| match k {
        "directory" => 0,
        "symlink" => 1,
        "file" => 2,
        _ => 3,
    };
    out.sort_by(|a, b| rank(a.kind).cmp(&rank(b.kind)).then(a.name.cmp(&b.name)));
    Ok(out)
}

pub fn stat(path: &str) -> Result<FsStat> {
    let p = resolve(path, None)?;
    let meta = match fs::metadata(&p) {
        Ok(m) => m,
        Err(_) => {
            return Ok(FsStat {
                path: p.display().to_string(),
                exists: false,
                kind: "none",
                size: 0,
                modified_unix: None,
                readonly: false,
            })
        }
    };
    Ok(FsStat {
        path: p.display().to_string(),
        exists: true,
        kind: entry_kind(&meta),
        size: meta.len(),
        modified_unix: modified_unix(&meta),
        readonly: meta.permissions().readonly(),
    })
}

pub fn mkdir(path: &str, parents: bool) -> Result<()> {
    let p = resolve(path, None)?;
    if parents {
        fs::create_dir_all(&p).with_context(|| format!("mkdir -p {}", p.display()))?;
    } else {
        fs::create_dir(&p).with_context(|| format!("mkdir {}", p.display()))?;
    }
    Ok(())
}

pub fn delete(path: &str, recursive: bool) -> Result<()> {
    let p = resolve(path, None)?;
    let meta = fs::metadata(&p).with_context(|| format!("stat {}", p.display()))?;
    if meta.is_dir() {
        if recursive {
            fs::remove_dir_all(&p)?;
        } else {
            fs::remove_dir(&p)?;
        }
    } else {
        fs::remove_file(&p)?;
    }
    Ok(())
}

pub fn rename(from: &str, to: &str, overwrite: bool) -> Result<()> {
    let f = resolve(from, None)?;
    let t = resolve(to, None)?;
    if t.exists() && !overwrite {
        return Err(anyhow!(
            "destination exists and overwrite=false: {}",
            t.display()
        ));
    }
    if t.exists() && overwrite {
        if t.is_dir() {
            fs::remove_dir_all(&t)?;
        } else {
            fs::remove_file(&t)?;
        }
    }
    fs::rename(&f, &t).with_context(|| format!("rename {} → {}", f.display(), t.display()))?;
    Ok(())
}

/// Lightweight, dependency-free temp file in `dir`. We don't pull in the
/// full `tempfile` crate at runtime since this is the only place we'd need
/// it.
struct TempFile {
    path: PathBuf,
    file: fs::File,
    persist: bool,
}

impl TempFile {
    fn new(dir: &Path) -> Result<Self> {
        let unique = uuid::Uuid::new_v4().simple().to_string();
        let path = dir.join(format!(".agixt-tmp-{unique}"));
        let file = fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&path)
            .with_context(|| format!("create temp {}", path.display()))?;
        Ok(Self {
            path,
            file,
            persist: false,
        })
    }
    fn path(&self) -> &Path {
        &self.path
    }
}

impl Write for TempFile {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        self.file.write(buf)
    }
    fn flush(&mut self) -> std::io::Result<()> {
        self.file.flush()
    }
}

impl Drop for TempFile {
    fn drop(&mut self) {
        if !self.persist {
            let _ = fs::remove_file(&self.path);
        }
    }
}

fn tempfile_in(dir: &Path) -> Result<TempFile> {
    let mut t = TempFile::new(dir)?;
    t.persist = true; // we always rename it; if rename fails, manual cleanup needed
    Ok(t)
}

// ----- Tests ----------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp() -> tempfile::TempDir {
        tempfile::tempdir().unwrap()
    }

    #[test]
    fn write_then_read_round_trip_utf8() {
        let d = tmp();
        let p = d.path().join("hello.txt");
        let r = write(p.to_str().unwrap(), "hello world", None, false).unwrap();
        assert_eq!(r.bytes_written, 11);
        assert!(r.created);
        let back = read(p.to_str().unwrap()).unwrap();
        assert_eq!(back.encoding, "utf8");
        assert_eq!(back.content, "hello world");
        assert_eq!(back.size, 11);
        assert!(!back.truncated);
    }

    #[test]
    fn write_overwrites_existing_file() {
        let d = tmp();
        let p = d.path().join("o.txt");
        write(p.to_str().unwrap(), "first", None, false).unwrap();
        let r = write(p.to_str().unwrap(), "second", None, false).unwrap();
        assert!(!r.created);
        assert_eq!(read(p.to_str().unwrap()).unwrap().content, "second");
    }

    #[test]
    fn write_with_base64_encoding() {
        let d = tmp();
        let p = d.path().join("img.bin");
        // bytes 0xff,0x00,0xff,0x00 — invalid UTF-8 → must use base64 round trip
        let payload = BASE64.encode([0xff, 0x00, 0xff, 0x00]);
        write(p.to_str().unwrap(), &payload, Some("base64"), false).unwrap();
        let back = read(p.to_str().unwrap()).unwrap();
        assert_eq!(back.encoding, "base64");
        let bytes = BASE64.decode(back.content).unwrap();
        assert_eq!(bytes, vec![0xff, 0x00, 0xff, 0x00]);
    }

    #[test]
    fn write_create_dirs_creates_parent() {
        let d = tmp();
        let p = d.path().join("a/b/c.txt");
        write(p.to_str().unwrap(), "hi", None, true).unwrap();
        assert!(p.exists());
    }

    #[test]
    fn append_creates_and_appends() {
        let d = tmp();
        let p = d.path().join("a.txt");
        append(p.to_str().unwrap(), "one\n", None).unwrap();
        append(p.to_str().unwrap(), "two\n", None).unwrap();
        assert_eq!(read(p.to_str().unwrap()).unwrap().content, "one\ntwo\n");
    }

    #[test]
    fn edit_replaces_unique_substring() {
        let d = tmp();
        let p = d.path().join("e.txt");
        write(p.to_str().unwrap(), "hello world\n", None, false).unwrap();
        edit(
            p.to_str().unwrap(),
            &[EditOp {
                find: "world".into(),
                replace: "rust".into(),
                replace_all: false,
            }],
        )
        .unwrap();
        assert_eq!(read(p.to_str().unwrap()).unwrap().content, "hello rust\n");
    }

    #[test]
    fn edit_rejects_ambiguous_match() {
        let d = tmp();
        let p = d.path().join("e.txt");
        write(p.to_str().unwrap(), "ab ab ab", None, false).unwrap();
        let err = edit(
            p.to_str().unwrap(),
            &[EditOp {
                find: "ab".into(),
                replace: "X".into(),
                replace_all: false,
            }],
        )
        .unwrap_err();
        assert!(format!("{err:#}").contains("3 times"));
    }

    #[test]
    fn edit_replace_all_works() {
        let d = tmp();
        let p = d.path().join("e.txt");
        write(p.to_str().unwrap(), "ab ab ab", None, false).unwrap();
        edit(
            p.to_str().unwrap(),
            &[EditOp {
                find: "ab".into(),
                replace: "X".into(),
                replace_all: true,
            }],
        )
        .unwrap();
        assert_eq!(read(p.to_str().unwrap()).unwrap().content, "X X X");
    }

    #[test]
    fn list_returns_dir_then_file_entries() {
        let d = tmp();
        fs::create_dir(d.path().join("sub")).unwrap();
        fs::write(d.path().join("a.txt"), b"x").unwrap();
        fs::write(d.path().join("b.txt"), b"yy").unwrap();
        let entries = list(d.path().to_str().unwrap()).unwrap();
        let names: Vec<_> = entries.iter().map(|e| (e.kind, e.name.clone())).collect();
        // Directories come first, then files alphabetically.
        assert_eq!(names[0], ("directory", "sub".into()));
        assert!(names.iter().any(|(_, n)| n == "a.txt"));
        assert!(names.iter().any(|(_, n)| n == "b.txt"));
    }

    #[test]
    fn stat_handles_missing_file_without_error() {
        let d = tmp();
        let p = d.path().join("nope");
        let s = stat(p.to_str().unwrap()).unwrap();
        assert!(!s.exists);
        assert_eq!(s.kind, "none");
    }

    #[test]
    fn mkdir_recursive_creates_nested() {
        let d = tmp();
        let p = d.path().join("x/y/z");
        mkdir(p.to_str().unwrap(), true).unwrap();
        assert!(p.is_dir());
    }

    #[test]
    fn delete_recursive_removes_tree() {
        let d = tmp();
        let p = d.path().join("doomed");
        fs::create_dir(&p).unwrap();
        fs::write(p.join("a"), b"x").unwrap();
        delete(p.to_str().unwrap(), true).unwrap();
        assert!(!p.exists());
    }

    #[test]
    fn rename_moves_file() {
        let d = tmp();
        let from = d.path().join("a.txt");
        let to = d.path().join("b.txt");
        fs::write(&from, b"x").unwrap();
        rename(from.to_str().unwrap(), to.to_str().unwrap(), false).unwrap();
        assert!(!from.exists());
        assert!(to.exists());
    }

    #[test]
    fn rename_refuses_existing_destination_unless_overwrite() {
        let d = tmp();
        let from = d.path().join("a");
        let to = d.path().join("b");
        fs::write(&from, b"x").unwrap();
        fs::write(&to, b"y").unwrap();
        let err = rename(from.to_str().unwrap(), to.to_str().unwrap(), false).unwrap_err();
        assert!(format!("{err:#}").contains("overwrite=false"));
        // With overwrite=true it succeeds.
        rename(from.to_str().unwrap(), to.to_str().unwrap(), true).unwrap();
        assert_eq!(fs::read_to_string(&to).unwrap(), "x");
    }

    #[test]
    fn resolve_expands_home_tilde() {
        let home = dirs::home_dir().unwrap();
        let r = resolve("~/foo/bar", None).unwrap();
        assert_eq!(r, home.join("foo/bar"));
    }

    #[test]
    fn resolve_expands_dollar_var() {
        std::env::set_var("AGIXT_RESOLVE_TEST", "/tmp/agixt-test");
        let r = resolve("$AGIXT_RESOLVE_TEST/sub", None).unwrap();
        assert_eq!(r, PathBuf::from("/tmp/agixt-test/sub"));
    }
}

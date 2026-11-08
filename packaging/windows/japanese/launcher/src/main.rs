#![windows_subsystem = "windows"]
#![forbid(unsafe_code)]
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]

use std::ffi::OsString;
use std::fs::{self, File, OpenOptions};
use std::io::{Cursor, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};

use sha2::{Digest, Sha256};
use winsafe::prelude::Handle;

include!(concat!(env!("OUT_DIR"), "/payload.rs"));

const DEFAULT_PREFERENCES: &str = r#"{
  "general": { "automaticallyCheckUpdates": false },
  "interface": { "language": "ja", "uiFontSize": "medium", "showTooltips": true }
}
"#;

fn main() -> ExitCode {
    let args: Vec<OsString> = std::env::args_os().skip(1).collect();
    let extract_only = args.first().is_some_and(|s| s == "--extract-only");
    let result = if extract_only {
        match args.as_slice() {
            [_, destination] => extract(PAYLOAD, Path::new(destination)).and_then(|()| validate_runtime(Path::new(destination))),
            _ => Err("--extract-only には新しい展開先フォルダーを指定してください。".into()),
        }
    } else {
        launch(&args)
    };
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("PhotoCraft 日本語版: {error}");
            if !extract_only {
                let _ = winsafe::HWND::NULL.MessageBox(
                    &format!("PhotoCraft を起動できませんでした。\n\n{error}"),
                    "PhotoCraft 日本語版",
                    winsafe::co::MB::OK | winsafe::co::MB::ICONERROR,
                );
            }
            ExitCode::FAILURE
        }
    }
}

fn extract(payload: &[u8], destination: &Path) -> Result<(), String> {
    let mut archive = zip::ZipArchive::new(Cursor::new(payload)).map_err(|e| format!("パッケージを読み込めません: {e}"))?;
    // Never merge a package into a folder that may hold user files.
    fs::create_dir(destination).map_err(|e| format!("新しい展開先を作成できません ({}): {e}", destination.display()))?;
    for i in 0..archive.len() {
        let mut entry = archive.by_index(i).map_err(|e| format!("パッケージの内容を読み込めません: {e}"))?;
        let relative = entry.enclosed_name().ok_or_else(|| "パッケージに無効なファイル名が含まれています。".to_string())?;
        let output = destination.join(relative);
        if entry.is_dir() {
            fs::create_dir_all(&output).map_err(|e| e.to_string())?;
            continue;
        }
        if let Some(parent) = output.parent() {
            fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        }
        let mut file = OpenOptions::new().write(true).create_new(true).open(&output).map_err(|e| format!("{} を展開できません: {e}", output.display()))?;
        std::io::copy(&mut entry, &mut file).map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn file_digest(path: &Path) -> Result<String, String> {
    let mut file = File::open(path).map_err(|e| e.to_string())?;
    let mut digest = Sha256::new();
    let mut buffer = [0u8; 64 * 1024];
    loop {
        let n = file.read(&mut buffer).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        digest.update(buffer.get(..n).ok_or("ファイルの読み込みサイズが無効です。")?);
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn validate_runtime(directory: &Path) -> Result<(), String> {
    let expected = fs::read_to_string(directory.join("photocraft.sha256")).map_err(|e| format!("本体の検証情報を読み込めません: {e}"))?;
    let actual = file_digest(&directory.join("photocraft.exe"))?;
    if actual != expected.trim().to_ascii_lowercase() {
        return Err("PhotoCraft 本体の検証に失敗しました。配布 EXE をもう一度取得してください。".into());
    }
    Ok(())
}

fn initialize_preferences(directory: &Path) -> Result<(), String> {
    fs::create_dir_all(directory).map_err(|e| e.to_string())?;
    match OpenOptions::new().write(true).create_new(true).open(directory.join("preferences.json")) {
        Ok(mut file) => file.write_all(DEFAULT_PREFERENCES.as_bytes()).map_err(|e| e.to_string()),
        Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => Ok(()),
        Err(e) => Err(format!("日本語の初期設定を保存できません: {e}")),
    }
}

fn launch(args: &[OsString]) -> Result<(), String> {
    let local = std::env::var_os("LOCALAPPDATA").filter(|s| !s.is_empty()).ok_or("ユーザー用のアプリ保存先が見つかりません。")?;
    let base = PathBuf::from(&local).join("Programs").join("PhotoCraftJA");
    let cache = base.join("runtime");
    fs::create_dir_all(&cache).map_err(|e| e.to_string())?;
    // Serialize simultaneous first launches so neither sees a partially unpacked app.
    let lock = OpenOptions::new().read(true).write(true).create(true).truncate(false).open(base.join("package.lock")).map_err(|e| e.to_string())?;
    lock.lock().map_err(|e| e.to_string())?;
    let id = format!("{:x}", Sha256::digest(PAYLOAD));
    let runtime = cache.join(&id);
    if !runtime.is_dir() {
        let stage = cache.join(format!(".{id}-{}", std::process::id()));
        extract(PAYLOAD, &stage)?;
        validate_runtime(&stage)?;
        fs::rename(&stage, &runtime).map_err(|e| e.to_string())?;
    } else {
        validate_runtime(&runtime)?;
    }
    drop(lock);
    let settings = match std::env::var_os("PHOTOCRAFT_CONFIG_DIR").filter(|s| !s.is_empty()) {
        Some(path) => PathBuf::from(path),
        None => PathBuf::from(std::env::var_os("APPDATA").filter(|s| !s.is_empty()).unwrap_or(local)).join("PhotoCraftJA"),
    };
    initialize_preferences(&settings)?;
    Command::new(runtime.join("photocraft.exe"))
        .args(args)
        .env("PHOTOCRAFT_CONFIG_DIR", settings)
        .spawn()
        .map_err(|e| format!("PhotoCraft 本体を起動できません: {e}"))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn archive(name: &str, contents: &[u8]) -> Vec<u8> {
        let mut writer = zip::ZipWriter::new(Cursor::new(Vec::new()));
        writer.start_file(name, zip::write::SimpleFileOptions::default()).unwrap();
        writer.write_all(contents).unwrap();
        writer.finish().unwrap().into_inner()
    }

    #[test]
    fn extraction_rejects_parent_traversal() {
        let temp = tempfile::tempdir().unwrap();
        let destination = temp.path().join("runtime");
        assert!(extract(&archive("../outside.txt", b"data"), &destination).is_err());
        assert!(!temp.path().join("outside.txt").exists());
    }

    #[test]
    fn extraction_does_not_overwrite_an_existing_folder() {
        let temp = tempfile::tempdir().unwrap();
        let file = temp.path().join("work.psd");
        fs::write(&file, b"original").unwrap();
        assert!(extract(&archive("work.psd", b"replacement"), temp.path()).is_err());
        assert_eq!(fs::read(file).unwrap(), b"original");
    }

    #[test]
    fn japanese_defaults_preserve_saved_preferences() {
        let temp = tempfile::tempdir().unwrap();
        initialize_preferences(temp.path()).unwrap();
        let file = temp.path().join("preferences.json");
        assert!(fs::read_to_string(&file).unwrap().contains("\"language\": \"ja\""));
        fs::write(&file, b"user-selected-preferences").unwrap();
        initialize_preferences(temp.path()).unwrap();
        assert_eq!(fs::read(file).unwrap(), b"user-selected-preferences");
    }

    #[test]
    fn runtime_validation_detects_corruption() {
        let temp = tempfile::tempdir().unwrap();
        fs::write(temp.path().join("photocraft.exe"), b"original").unwrap();
        let expected = file_digest(&temp.path().join("photocraft.exe")).unwrap();
        fs::write(temp.path().join("photocraft.sha256"), expected).unwrap();
        validate_runtime(temp.path()).unwrap();
        fs::write(temp.path().join("photocraft.exe"), b"changed").unwrap();
        assert!(validate_runtime(temp.path()).is_err());
    }
}

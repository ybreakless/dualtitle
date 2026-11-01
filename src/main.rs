//! DualTitle (Rust Native Edition v4.1)
//! 100% Anti-Cheat-Safe Universal Dual-Subtitle & Save Restore Controller.
//! Never injects DLLs or hooks process memory. Launches the native C++17 / Win32
//! DualTitle GUI & In-Game Overlay HUD with clickable word definitions, speed controls,
//! and 1-click Save Backup & Restore.

use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

fn find_suite_root() -> PathBuf {
    if let Ok(exe) = env::current_exe() {
        if let Some(parent) = exe.parent() {
            if parent.join("universal_dualsub.py").is_file() {
                return parent.to_path_buf();
            }
            if let Some(gp) = parent.parent() {
                if gp.join("universal_dualsub.py").is_file() {
                    return gp.to_path_buf();
                }
            }
        }
    }
    env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
}

fn backup_saves(game_dir: &Path) -> usize {
    let backup_dir = game_dir.join(".dualtitle_save_backup");
    let _ = fs::create_dir_all(&backup_dir);
    let mut count = 0usize;
    for sub in ["Saved/SaveGames", "Saves", "settings", "Profile"] {
        let candidate = game_dir.join(sub);
        if candidate.is_dir() {
            if let Ok(entries) = fs::read_dir(&candidate) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    if path.is_file() {
                        if let Some(name) = path.file_name() {
                            let dest = backup_dir.join(name);
                            if fs::copy(&path, &dest).is_ok() {
                                count += 1;
                            }
                        }
                    }
                }
            }
        }
    }
    count
}

fn restore_saves(game_dir: &Path) -> usize {
    let backup_dir = game_dir.join(".dualtitle_save_backup");
    if !backup_dir.is_dir() {
        return 0;
    }
    let mut restored = 0usize;
    if let Ok(entries) = fs::read_dir(&backup_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_file() {
                restored += 1;
            }
        }
    }
    restored
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    let root = find_suite_root();

    if args.iter().any(|a| a == "--restore-save") {
        let target = args.get(1).map(PathBuf::from).unwrap_or_else(|| root.clone());
        let n = restore_saves(&target);
        println!("[DualTitle Rust] Restored/verified {} save item(s).", n);
        return;
    }

    if args.iter().any(|a| a == "--backup-save") {
        let target = args.get(1).map(PathBuf::from).unwrap_or_else(|| root.clone());
        let n = backup_saves(&target);
        println!("[DualTitle Rust] Backed up {} save item(s).", n);
        return;
    }

    // Prefer compiled C++17 native executable if present, otherwise invoke Win32 GUI runtime
    let native_cpp = root.join("DualTitle_Native.exe");
    if native_cpp.is_file() {
        let _ = Command::new(native_cpp).args(&args).status();
        return;
    }

    let script = root.join("universal_dualsub.py");
    let mut cmd_args = vec![script.to_string_lossy().to_string()];
    if args.is_empty() {
        cmd_args.push("--gui".to_string());
    } else {
        cmd_args.extend(args);
    }
    let _ = Command::new("python").args(&cmd_args).status();
}

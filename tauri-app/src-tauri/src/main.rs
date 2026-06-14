// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpStream;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;

struct ServerHandle(Mutex<Option<Child>>);

fn bunshin_binary() -> Option<String> {
    let home = std::env::var("HOME").ok()?;
    let candidates = [
        format!("{}/.bunshin/venv/bin/bunshin", home),
        "/usr/local/bin/bunshin".to_string(),
        "/opt/homebrew/bin/bunshin".to_string(),
    ];
    candidates.into_iter().find(|p| std::path::Path::new(p).exists())
}

fn spawn_server() -> Option<Child> {
    let bin = bunshin_binary()?;
    Command::new(bin)
        .arg("web")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .ok()
}

fn wait_for_server(addr: &str, max_attempts: u32) -> bool {
    let Ok(socket_addr) = addr.parse() else {
        return false;
    };
    for _ in 0..max_attempts {
        if TcpStream::connect_timeout(&socket_addr, Duration::from_millis(500)).is_ok() {
            return true;
        }
        thread::sleep(Duration::from_millis(300));
    }
    false
}

fn main() {
    let server = spawn_server();

    if server.is_some() {
        thread::spawn(|| {
            let _ = wait_for_server("127.0.0.1:8000", 30);
        });
    }

    let app = tauri::Builder::default()
        .manage(ServerHandle(Mutex::new(server)))
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if let tauri::RunEvent::ExitRequested { .. } = event {
            use tauri::Manager;
            let state: tauri::State<ServerHandle> = app_handle.state();
            if let Some(mut child) = state.0.lock().unwrap().take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    });
}

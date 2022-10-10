#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

//use tauri::*;
use tauri::Manager;
use tauri::{CustomMenuItem, SystemTray, SystemTrayEvent, SystemTrayMenu, SystemTrayMenuItem};

use sysinfo::{System, SystemExt};
use whoami::username;
use window_shadows::set_shadow;

use serde::{Deserialize, Serialize};
use serde_json::{Number, Value};
use sprintf::sprintf;

/* /* TOML */
use serde::Serialize; // 1.0.91
use std::{collections::BTreeMap, fs};
use toml; // 0.5.1

#[derive(Debug, Default, Serialize)]
struct Config<'a> {
    config: BTreeMap<&'a str, User<'a>>,
}

#[derive(Debug, Serialize)]
struct User<'a> {
    #[serde(rename = "username")]
    user_name: &'a str,
}

#[tauri::command]
fn write_to_toml() {
    let mut file = Config::default();
    let username = get_user();
    file.config.insert(
        "User",
        User {
            user_name: &username,
        },
    );
    let toml_string = toml::to_string(&file).expect("Could not encode TOML value");
    eprintln!("{}", toml_string);
    fs::write("config.toml", toml_string).expect("Could not write to file!");
} */

#[derive(Debug, Deserialize, Serialize)]
struct User {
    name: String,
}

#[tauri::command]
fn get_user() {
    let name = username();
    let json = sprintf!("{\"name\":\"%s\"}\n", name).unwrap();
    let user_name: User = serde_json::from_str(&json).unwrap();
    eprintln!("{:?}", user_name);
    std::fs::write(
        "config/config.json",
        serde_json::to_string_pretty(&user_name).unwrap(),
    )
    .unwrap();
}

// This command must be async so that it doesn't run on the main thread.
#[tauri::command]
async fn close_splashscreen(window: tauri::Window) {
    // Close splashscreen
    if let Some(splashscreen) = window.get_window("splashscreen") {
        splashscreen.close().unwrap();
    }
    // Show main window
    window.get_window("main").unwrap().show().unwrap();
}

fn main() {
    let quit = CustomMenuItem::new("quit".to_string(), "Quit");
    let hide = CustomMenuItem::new("hide".to_string(), "Hide");
    let show = CustomMenuItem::new("show".to_string(), "Show");

    let tray_menu = SystemTrayMenu::new()
        .add_item(quit)
        .add_native_item(SystemTrayMenuItem::Separator)
        .add_item(hide)
        .add_native_item(SystemTrayMenuItem::Separator)
        .add_item(show);

    let tray = SystemTray::new().with_menu(tray_menu);

    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![get_user, close_splashscreen])
        .setup(|app| {
            let window = app.get_window("main").unwrap();
            set_shadow(&window, true).expect("Unsupported platform!");
            Ok(window.hide().unwrap())
        })
        .system_tray(tray)
        .on_system_tray_event(move |app, event| match event {
            SystemTrayEvent::LeftClick {
                position: _,
                size: _,
                ..
            } => {
                dbg!("system tray received a left click");
                let window = app.get_window("main").unwrap();
                window.show().unwrap();
                /* let logical_size = tauri::LogicalSize::<f64> {
                    width: 300.0,
                    height: 400.0,
                };
                let logical_s = tauri::Size::Logical(logical_size);
                window.set_size(logical_s); */
            }
            SystemTrayEvent::RightClick {
                position: _,
                size: _,
                ..
            } => {
                dbg!("system tray received a right click");
            }
            SystemTrayEvent::DoubleClick {
                position: _,
                size: _,
                ..
            } => {
                dbg!("system tray received a double click");
            }
            SystemTrayEvent::MenuItemClick { id, .. } => match id.as_str() {
                "quit" => {
                    std::process::exit(0);
                }
                "hide" => {
                    let window = app.get_window("main").unwrap();
                    window.hide().unwrap();
                }
                "show" => {
                    let window = app.get_window("main").unwrap();
                    window.show().unwrap();
                }
                _ => {}
            },
            _ => {}
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
    /* .build(tauri::generate_context!())*/
    /* .expect("error while building tauri application") */
    /* .run(|_app_handle, event| match event {
        tauri::RunEvent::ExitRequested { api, .. } => {
            api.prevent_exit();
        }
        _ => {}
    }); */
}

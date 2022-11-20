#![allow(dead_code, unused_imports, unused_variables)]
#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

// TODO: Implement mDNS discovery for the cameras in the Rust backend

//use tauri::*;
use tauri::Manager;
use tauri::{CustomMenuItem, SystemTray, SystemTrayEvent, SystemTrayMenu, SystemTrayMenuItem};

// use various crates
use whoami::username;
use window_shadows::set_shadow;
use log::{debug, error, info, warn};
use serde::{Deserialize, Serialize};
use serde_json;

// use std
use std::collections::hash_map::HashMap;
use std::sync::{Arc, Mutex};

// use custom modules
mod modules;
use modules::{ m_dnsquery};

#[derive(Debug, Deserialize, Serialize)]
struct User {
    name: String,
}

/// A function to run a mDNS query and create a new RESTClient instance for each device found
/// ## Arguments
/// - `service_type` The service type to query for
/// - `scan_time` The number of seconds to query for
/// // This command must be async so that it doesn't run on the main thread.
#[tauri::command]
async fn run_mdns_query() {
    info!("Starting MDNS query to find devices");
    let base_url = Arc::new(Mutex::new(HashMap::new()));
    let thread_arc = base_url.clone();
    let mut mdns: m_dnsquery::Mdns = m_dnsquery::Mdns {
        base_url: thread_arc,
        name: Vec::new(),
    };
    let ref_mdns = &mut mdns;
    m_dnsquery::run_query(ref_mdns, String::from("_openiris._tcp"), 10)
        .await
        .expect("Failed to run MDNS query");
    info!("MDNS query complete");
    info!("MDNS query results: {:#?}", m_dnsquery::get_urls(&ref_mdns)); // get's an array of the base urls found
    m_dnsquery::generate_json(&ref_mdns).await; // generates a json file with the base urls found
}

#[tauri::command]
fn get_user() {
    let name = username();
    let json = serde_json::json!({
        "name": name,
    });
    let user_name: User = serde_json::from_value(json).unwrap();
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
        .invoke_handler(tauri::generate_handler![get_user, close_splashscreen, run_mdns_query])
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

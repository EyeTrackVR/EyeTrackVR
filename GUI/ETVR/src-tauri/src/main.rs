#![allow(dead_code, unused_imports, unused_variables)]
#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

// TODO: Implement REST Client for ETVR

//use tauri::*;
use tauri::Manager;
use tauri::{CustomMenuItem, SystemTray, SystemTrayEvent, SystemTrayMenu, SystemTrayMenuItem};

// use various crates
use log::{debug, error, info, warn};
use serde::{Deserialize, Serialize};
use whoami::username;
use window_shadows::set_shadow;

// use std
use std::collections::hash_map::HashMap;
use std::sync::{Arc, Mutex};

// use custom modules
mod modules;
use modules::m_dnsquery;

#[derive(Debug, Deserialize, Serialize)]
struct Config {
    name: String,
    urls: Vec<String>,
}

/// This generates the json for the config file
/// # Arguments
/// * `instance` - The instance of the mdnsquery struct
async fn generate_json(instance: &m_dnsquery::Mdns) -> Result<(), Box<dyn std::error::Error>> {
    let user_name: String = username().to_string();
    info!("User name: {}", user_name);
    let data = m_dnsquery::get_urls(instance);
    //let mut json: serde_json::Value = serde_json::from_str("{}").unwrap();
    let mut json: Option<serde_json::Value> = None;
    for url in data {
        // create a json object then add the urls to an array
        json = Some(serde_json::json!({
            "name": user_name,
            "urls": [url],
        }));
    }
    let config: Config;
    if let Some(json) = json {
        let _serde_json = serde_json::from_value(json);
        let serde_json_result = match _serde_json {
            Ok(serde_json) => serde_json,
            Err(err) => {
                error!("Error configuring JSON config file: {}", err);
                return Err("Error configuring JSON config file".into());
            }
        };
        config = serde_json_result;
    } else {
        config = Config {
            name: user_name,
            urls: Vec::new(),
        };
    }
    info!("{:?}", config);
    // write the json object to a file
    let to_string_json = serde_json::to_string_pretty(&config)?;
    tokio::fs::write("config/config.json", to_string_json).await?;
    Ok(())
}

#[tauri::command]
async fn wrapper() {
    env_logger::init();
    info!("Wrapper function ran");
    run_mdns_query(String::from("_openiris._tcp"), 10).await;
}

/// A function to run a mDNS query and create a new RESTClient instance for each device found
/// ## Arguments
/// - `service_type` The service type to query for
/// - `scan_time` The number of seconds to query for
/// // This command must be async so that it doesn't run on the main thread.
#[tauri::command]
async fn run_mdns_query(service_type: String, scan_time: u64) {
    info!("Starting MDNS query to find devices");
    let base_url = Arc::new(Mutex::new(HashMap::new()));
    let thread_arc = base_url.clone();
    let mut mdns: m_dnsquery::Mdns = m_dnsquery::Mdns {
        base_url: thread_arc,
        name: Vec::new(),
    };
    let ref_mdns = &mut mdns;
    m_dnsquery::run_query(ref_mdns, service_type, scan_time)
        .await
        .expect("Failed to run MDNS query");
    info!("MDNS query complete");
    info!("MDNS query results: {:#?}", m_dnsquery::get_urls(&*ref_mdns)); // get's an array of the base urls found
    generate_json(&*ref_mdns)
        .await
        .expect("Generate JSON Config failed in run_mdns_query"); // generates a json file with the base urls found
}

// This command must be async so that it doesn't run on the main thread.
#[tauri::command]
async fn close_splashscreen(window: tauri::Window) {
    // Close splashscreen
    if let Some(splashscreen) = window.get_window("splashscreen") {
        splashscreen.close().expect("Failed to close splashscreen");
    }
    // Show main window
    window
        .get_window("main")
        .expect("Failed to get main window")
        .show()
        .unwrap();
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
        .invoke_handler(tauri::generate_handler![
            close_splashscreen,
            run_mdns_query,
            wrapper
        ])
        .setup(|app| {
            let window = app.get_window("main").expect("failed to get window");
            //set_shadow(&window, true).expect("Unsupported platform!");
            window.hide().unwrap();
            Ok(())
        })
        .system_tray(tray)
        .on_system_tray_event(move |app, event| match event {
            SystemTrayEvent::LeftClick {
                position: _,
                size: _,
                ..
            } => {
                dbg!("system tray received a left click");
                let window = app.get_window("main").expect("failed to get window");
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
                    let window = app.get_window("main").expect("failed to get window");
                    window.hide().unwrap();
                }
                "show" => {
                    let window = app.get_window("main").expect("failed to get window");
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

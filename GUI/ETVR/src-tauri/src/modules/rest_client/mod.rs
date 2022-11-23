#![allow(dead_code, unused_imports, unused_variables)]
#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

// 1. Grab the mDNS address of the device(s) you want to query
// 2. Create a new RESTClient instance for each device
// 3. Start a new thread for each RESTClient instance
// 4. Each thread will poll the device for new data
// 5. Each thread will send the new data to the main thread
// 6. The main thread will update the UI with the new data

use crate::modules::m_dnsquery;
use log::{debug, error, info, warn};
use reqwest::Client;
use serde::Deserialize;
use std::collections::hash_map::HashMap;
use std::sync::{Arc, Mutex};

/// A struct to hold the REST client
/// ## Fields
/// - `client`: a reqwest client
/// - `base_url`: the base url of the api to query
/// - `name`: the name of the url to query
/// - `data`: a hashmap of the data returned from the api
pub struct RESTClient {
    http_client: Client,
    base_url: String,
}

/// A function to create a new RESTClient instance
/// ## Arguments
/// - `base_url` The base url of the api to query
impl RESTClient {
    pub fn new(base_url: String) -> Self {
        Self {
            http_client: Client::new(),
            base_url,
        }
    }
}

pub async fn request(rest_client: &RESTClient) -> Result<String, String> {
    info!("Making REST request");
    let response = rest_client
        .http_client
        .get(&rest_client.base_url)
        .send()
        .await
        .expect("Error sending request")
        .text()
        .await
        .expect("Error parsing response");
    Ok(response)
}

/// A function to run a REST Client and create a new RESTClient instance for each device found
/// ## Arguments
/// - `endpoint` The endpoint to query for
/// - `device_name` The name of the device to query
pub async fn run_rest_client(endpoint: String, device_name: String) -> Result<String, String> {
    info!("Starting REST client");
    // read the json config file
    let data = std::fs::read_to_string("config/config.json").expect("Unable to read config file");
    // parse the json config file
    let config: serde_json::Value =
        serde_json::from_str(&data).expect("Unable to parse config file");
    debug!("Current Config: {:?}", config);
    let mut request_response: String = String::new();
    let mut url = config["urls"][device_name].as_str();
    let full_url_result = match url {
        Some(url) => url,
        None => {
            error!("Unable to get url");
            url = Some("");
            url.expect("Unable to get url")
        }
    };
    let full_url = format!("{}{}", full_url_result, endpoint);
    //info!("Full url: {}", full_url);
    let rest_client = RESTClient::new(full_url);
    let request_result = request(&rest_client).await;
    match request_result {
        Ok(response) => {
            request_response = response;
            println!("Request response: {:?}", request_response);
        }
        Err(e) => println!("Request failed: {}", e),
    }
    Ok(request_response)
}

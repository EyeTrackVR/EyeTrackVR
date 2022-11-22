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

pub async fn request(
    rest_client: &RESTClient,
) -> Result<HashMap<String, serde_json::Value>, Box<dyn std::error::Error>> {
    info!("Making REST request");
    let response = rest_client
        .http_client
        .get(&rest_client.base_url)
        .send()
        .await?
        .json::<HashMap<String, serde_json::Value>>()
        //.json::<Response>()
        .await?;
    Ok(response)
}

/// A function to run a REST Client and create a new RESTClient instance for each device found
/// ## Arguments
/// - `service_type` The service type to query for
/// - `scan_time` The number of seconds to query for
pub async fn run_rest_client(endpoint: String) -> Result<(), Box<dyn std::error::Error>> {
    info!("Starting REST client");
    // create a new db instance

    // read the json config file
    let data = std::fs::read_to_string("config/config.json").expect("Unable to read config file");
    // parse the json config file
    let config: serde_json::Value =
        serde_json::from_str(&data).expect("Unable to parse config file");
    debug!("Urls: {:?}", config);

    // create iterator for loop
    for (i, item) in config.as_object().iter().enumerate() {
        // create a new RESTClient instance for each url
        let mut url = item["urls"][i].as_str();
        let full_url_result = match url {
            Some(url) => url,
            None => {
                error!("Unable to get url");
                url = Some("http://localhost:8080");
                url.unwrap()
            }
        };
        let full_url = format!("{}{}", full_url_result, endpoint);
        //info!("Full url: {}", full_url);
        let rest_client = RESTClient::new(full_url);
        let request_result = request(&rest_client).await;
        match request_result {
            Ok(response) => {
                info!("Response: {:?}", response);
            }
            Err(e) => error!("Request failed: {}", e),
        }
    }
    Ok(())
}

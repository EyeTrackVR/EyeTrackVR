#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use reqwest::Client;
use log::{debug, info, warn, error};

pub struct RESTClient {
  http_client: Client,
  base_url: String,
}

impl RESTClient {
  pub fn new(base_url: String) -> Self {
    Self {
      http_client: Client::new(),
      base_url
    }
  }

  // [...]
}

#[tokio::main]
pub async fn main() -> Result<(), Box<dyn std::error::Error>> {
  env_logger::init();

  info!("Starting up REST client");

  Ok(())
}
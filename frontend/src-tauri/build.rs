fn main() {
    let manifest_dir = std::env::var("CARGO_MANIFEST_DIR").unwrap();
    println!("cargo:rustc-link-search=native={}/libs", manifest_dir);
    println!("cargo:rustc-link-search=native=/usr/local/lib");

    let port = std::env::var("EVOLOOP_BACKEND_PORT")
        .unwrap_or_else(|_| "20160".to_string());
    println!("cargo:rustc-env=EVOLOOP_BACKEND_PORT={}", port);

    tauri_build::build()
}

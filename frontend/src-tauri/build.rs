fn main() {
    let manifest_dir = std::env::var("CARGO_MANIFEST_DIR").unwrap();
    println!("cargo:rustc-link-search=native={}/libs", manifest_dir);
    println!("cargo:rustc-link-search=native=/usr/local/lib");
    tauri_build::build()
}

fn main() {
    println!("cargo:rustc-link-search=native=/usr/local/lib");
    tauri_build::build()
}

use std::path::PathBuf;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("cargo:rerun-if-env-changed=PHOTOCRAFT_JA_PAYLOAD");
    let output = PathBuf::from(std::env::var("OUT_DIR")?).join("payload.rs");
    let code = match std::env::var("PHOTOCRAFT_JA_PAYLOAD") {
        Ok(path) => {
            println!("cargo:rerun-if-changed={path}");
            format!("pub static PAYLOAD: &[u8] = include_bytes!({path:?});\n")
        }
        Err(_) => "pub static PAYLOAD: &[u8] = &[];\n".into(),
    };
    std::fs::write(output, code)?;
    let mut resource = winresource::WindowsResource::new();
    resource
        .set_icon("../../../../assets/app-icon/photocraft.ico")
        .set("ProductName", "PhotoCraft 日本語版")
        .set("FileDescription", "PhotoCraft 日本語版 — ダブルクリックで起動")
        .set("FileVersion", "0.20.1.0")
        .set("ProductVersion", "0.20.1 Japanese edition");
    resource.compile()?;
    Ok(())
}

use serde::Deserialize;
use crate::shading::ShadingConfig;

/// Tiling configuration loaded from JSON.
///
/// Controls water overlay color/blend, shading, biome tint, and waterflow.
#[derive(Debug, Clone, Deserialize)]
#[serde(default)]
pub struct TilerConfig {
    pub water_overlay_color: [u8; 3],
    pub water_overlay_blend: f32,
    pub shading: ShadingConfig,
    pub enable_shading: bool,
    pub enable_biome_tint: bool,
    pub enable_waterflow: bool,
}

impl Default for TilerConfig {
    /// Default config: blue water overlay at 35% blend, shading/biome/waterflow enabled.
    fn default() -> Self {
        TilerConfig {
            water_overlay_color: [50, 120, 220],
            water_overlay_blend: 0.35,
            shading: ShadingConfig::default(),
            enable_shading: true,
            enable_biome_tint: true,
            enable_waterflow: true,
        }
    }
}

impl TilerConfig {
    /// Load `TilerConfig` from JSON file path.
    ///
    /// # Errors
    ///
    /// Returns `Err` if file unreadable or JSON invalid.
    pub fn from_file(path: &str) -> Result<Self, String> {
        let content = std::fs::read_to_string(path)
            .map_err(|e| format!("cannot read config '{}': {}", path, e))?;
        serde_json::from_str(&content)
            .map_err(|e| format!("invalid config '{}': {}", path, e))
    }
}

use serde::Deserialize;
use std::collections::{HashMap, HashSet};
use std::path::Path;

/// RGB color with per-channel operations (scale, blend).
#[derive(Debug, Clone, Copy)]
pub struct Rgb {
    pub r: u8,
    pub g: u8,
    pub b: u8,
}

impl Rgb {
    /// Create new RGB color from component values.
    pub fn new(r: u8, g: u8, b: u8) -> Self {
        Rgb { r, g, b }
    }

    /// Scale each channel by `factor` (clamped to 0–255).
    pub fn scale(&self, factor: f32) -> Self {
        Rgb {
            r: (self.r as f32 * factor).clamp(0.0, 255.0) as u8,
            g: (self.g as f32 * factor).clamp(0.0, 255.0) as u8,
            b: (self.b as f32 * factor).clamp(0.0, 255.0) as u8,
        }
    }

    /// Blend two colors: `self * (1 - t) + other * t`, clamped.
    pub fn blend(&self, other: &Rgb, t: f32) -> Self {
        Rgb {
            r: (self.r as f32 * (1.0 - t) + other.r as f32 * t).clamp(0.0, 255.0) as u8,
            g: (self.g as f32 * (1.0 - t) + other.g as f32 * t).clamp(0.0, 255.0) as u8,
            b: (self.b as f32 * (1.0 - t) + other.b as f32 * t).clamp(0.0, 255.0) as u8,
        }
    }
}

/// Error color for unknown blocks — bright magenta, highly visible
const ERROR_COLOR: Rgb = Rgb { r: 255, g: 0, b: 255 };

// ── Block Palette ──────────────────────────────────────────────────

#[derive(Deserialize)]
struct BlockEntry {
    r: u8,
    g: u8,
    b: u8,
    #[serde(default)]
    biome_tint: bool,
}

/// Block color palette — maps block name to RGB + biome tint flag.
pub struct BlockPalette {
    colors: HashMap<String, (Rgb, bool)>,
}

impl BlockPalette {
    /// Load block palette from JSON file.
    pub fn from_file(path: &Path) -> Self {
        match std::fs::read_to_string(path) {
            Ok(json) => Self::from_json(&json),
            Err(e) => {
                eprintln!("Warning: failed to load palette '{}': {}", path.display(), e);
                Self::empty()
            }
        }
    }

    /// Load block palette from JSON string.
    pub fn from_json(json_str: &str) -> Self {
        let entries: HashMap<String, BlockEntry> =
            serde_json::from_str(json_str).unwrap_or_default();
        let mut colors = HashMap::new();
        for (name, entry) in entries {
            colors.insert(name, (Rgb::new(entry.r, entry.g, entry.b), entry.biome_tint));
        }
        BlockPalette { colors }
    }

    /// Create empty block palette (all blocks map to error color).
    pub fn empty() -> Self {
        BlockPalette { colors: HashMap::new() }
    }

    /// Get block color by name. Returns bright magenta for unknown blocks.
    pub fn get_block_color(&self, name: &str) -> Rgb {
        self.colors.get(name).map(|(c, _)| *c).unwrap_or(ERROR_COLOR)
    }

    /// Check if block has biome tint flag.
    pub fn is_biome_tint_block(&self, name: &str) -> bool {
        self.colors.get(name).map(|(_, tint)| *tint).unwrap_or(false)
    }

    /// Number of blocks in palette.
    pub fn len(&self) -> usize {
        self.colors.len()
    }
}

// ── Biome Palette ──────────────────────────────────────────────────

/// Biome color data from palette JSON — grass/foliage color, temperature, downfall.
#[derive(Deserialize, Clone)]
pub struct BiomeColorEntry {
    pub grass_color: RgbEntry,
    #[allow(dead_code)]
    pub foliage_color: RgbEntry,
    #[allow(dead_code)]
    pub temperature: f32,
    #[allow(dead_code)]
    pub downfall: f32,
}

/// Deserializable RGB color entry from JSON.
#[derive(Deserialize, Clone, Copy)]
pub struct RgbEntry {
    pub r: u8,
    pub g: u8,
    pub b: u8,
}

impl From<RgbEntry> for Rgb {
    /// Convert deserialized `RgbEntry` to `Rgb` color.
    fn from(e: RgbEntry) -> Self {
        Rgb::new(e.r, e.g, e.b)
    }
}

/// Biome color palette — maps biome name to grass/foliage color.
pub struct BiomePalette {
    biomes: HashMap<String, BiomeColorEntry>,
}

impl BiomePalette {
    /// Load biome palette from JSON file.
    pub fn from_file(path: &Path) -> Self {
        match std::fs::read_to_string(path) {
            Ok(json) => Self::from_json(&json),
            Err(e) => {
                eprintln!("Warning: failed to load biome palette '{}': {}", path.display(), e);
                Self::empty()
            }
        }
    }

    /// Load biome palette from JSON string.
    pub fn from_json(json_str: &str) -> Self {
        let biomes = serde_json::from_str(json_str).unwrap_or_default();
        BiomePalette { biomes }
    }

    /// Create empty biome palette.
    pub fn empty() -> Self {
        BiomePalette { biomes: HashMap::new() }
    }

    /// Look up grass color for biome name. Returns gray default if missing.
    pub fn get_biome_color(&self, name: &str) -> Rgb {
        self.biomes
            .get(name)
            .map(|b| Rgb::from(b.grass_color))
            .unwrap_or(Rgb::new(140, 140, 140))
    }

    /// Number of biomes in palette.
    pub fn len(&self) -> usize {
        self.biomes.len()
    }
}

// ── Biome Tint Block Set ───────────────────────────────────────────

/// Block name categories for surface detection logic.
///
/// Each category is a `HashSet` for O(1) membership checks.
/// Used by `extract_terrain()` to skip water/air/plant blocks.
#[derive(Debug, Clone)]
pub struct BlockCategories {
    /// Water/lava blocks — skipped during surface search, detected later for overlay.
    pub water: HashSet<String>,
    /// Air blocks (cave_air, void_air) — counted for cave detection.
    pub air: HashSet<String>,
    /// Non-solid plant-like blocks — skipped during surface search.
    pub plant: HashSet<String>,
}

impl BlockCategories {
    /// Load block categories from JSON file.
    ///
    /// Expected format: `{"water": ["name", ...], "air": [...], "plant": [...]}`.
    pub fn from_file(path: &Path) -> Self {
        match std::fs::read_to_string(path) {
            Ok(json) => Self::from_json(&json),
            Err(e) => {
                eprintln!("Warning: failed to load block categories '{}': {}", path.display(), e);
                Self::empty()
            }
        }
    }

    /// Load block categories from JSON string.
    pub fn from_json(json_str: &str) -> Self {
        let raw: HashMap<String, Vec<String>> =
            serde_json::from_str(json_str).unwrap_or_default();
        BlockCategories {
            water: raw.get("water").map(|v| v.iter().cloned().collect()).unwrap_or_default(),
            air: raw.get("air").map(|v| v.iter().cloned().collect()).unwrap_or_default(),
            plant: raw.get("plant").map(|v| v.iter().cloned().collect()).unwrap_or_default(),
        }
    }

    /// Create empty categories (all blocks treated as solid).
    pub fn empty() -> Self {
        BlockCategories {
            water: HashSet::new(),
            air: HashSet::new(),
            plant: HashSet::new(),
        }
    }

    /// Number of blocks across all categories.
    pub fn len(&self) -> usize {
        self.water.len() + self.air.len() + self.plant.len()
    }
}

/// Set of block names that receive biome color tinting.
pub struct BiomeTintBlocks {
    blocks: Vec<String>,
}

impl BiomeTintBlocks {
    /// Load tint block list from JSON file.
    pub fn from_file(path: &Path) -> Self {
        match std::fs::read_to_string(path) {
            Ok(json) => Self::from_json(&json),
            Err(e) => {
                eprintln!("Warning: failed to load tint blocks '{}': {}", path.display(), e);
                Self::empty()
            }
        }
    }

    /// Load tint block list from JSON string.
    pub fn from_json(json_str: &str) -> Self {
        let blocks: Vec<String> = serde_json::from_str(json_str).unwrap_or_default();
        BiomeTintBlocks { blocks }
    }

    /// Create empty tint block list.
    pub fn empty() -> Self {
        BiomeTintBlocks { blocks: Vec::new() }
    }

    /// Check if block name is in tint list.
    pub fn contains(&self, name: &str) -> bool {
        self.blocks.iter().any(|b| b == name)
    }

    /// Number of tint blocks in list.
    pub fn len(&self) -> usize {
        self.blocks.len()
    }
}

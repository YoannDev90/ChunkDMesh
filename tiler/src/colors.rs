use serde::Deserialize;
use std::collections::HashMap;
use std::path::Path;

#[derive(Debug, Clone, Copy)]
pub struct Rgb {
    pub r: u8,
    pub g: u8,
    pub b: u8,
}

impl Rgb {
    pub fn new(r: u8, g: u8, b: u8) -> Self {
        Rgb { r, g, b }
    }

    pub fn scale(&self, factor: f32) -> Self {
        Rgb {
            r: (self.r as f32 * factor).clamp(0.0, 255.0) as u8,
            g: (self.g as f32 * factor).clamp(0.0, 255.0) as u8,
            b: (self.b as f32 * factor).clamp(0.0, 255.0) as u8,
        }
    }

    pub fn blend(&self, other: &Rgb, t: f32) -> Self {
        Rgb {
            r: (self.r as f32 * (1.0 - t) + other.r as f32 * t) as u8,
            g: (self.g as f32 * (1.0 - t) + other.g as f32 * t) as u8,
            b: (self.b as f32 * (1.0 - t) + other.b as f32 * t) as u8,
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

pub struct BlockPalette {
    colors: HashMap<String, (Rgb, bool)>,
}

impl BlockPalette {
    pub fn from_file(path: &Path) -> Self {
        match std::fs::read_to_string(path) {
            Ok(json) => Self::from_json(&json),
            Err(e) => {
                eprintln!("Warning: failed to load palette '{}': {}", path.display(), e);
                Self::empty()
            }
        }
    }

    pub fn from_json(json_str: &str) -> Self {
        let entries: HashMap<String, BlockEntry> =
            serde_json::from_str(json_str).unwrap_or_default();
        let mut colors = HashMap::new();
        for (name, entry) in entries {
            colors.insert(name, (Rgb::new(entry.r, entry.g, entry.b), entry.biome_tint));
        }
        BlockPalette { colors }
    }

    pub fn empty() -> Self {
        BlockPalette { colors: HashMap::new() }
    }

    pub fn get_block_color(&self, name: &str) -> Rgb {
        self.colors.get(name).map(|(c, _)| *c).unwrap_or(ERROR_COLOR)
    }

    pub fn is_biome_tint_block(&self, name: &str) -> bool {
        self.colors.get(name).map(|(_, tint)| *tint).unwrap_or(false)
    }

    pub fn len(&self) -> usize {
        self.colors.len()
    }
}

// ── Biome Palette ──────────────────────────────────────────────────

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

#[derive(Deserialize, Clone, Copy)]
pub struct RgbEntry {
    pub r: u8,
    pub g: u8,
    pub b: u8,
}

impl From<RgbEntry> for Rgb {
    fn from(e: RgbEntry) -> Self {
        Rgb::new(e.r, e.g, e.b)
    }
}

pub struct BiomePalette {
    biomes: HashMap<String, BiomeColorEntry>,
}

impl BiomePalette {
    pub fn from_file(path: &Path) -> Self {
        match std::fs::read_to_string(path) {
            Ok(json) => Self::from_json(&json),
            Err(e) => {
                eprintln!("Warning: failed to load biome palette '{}': {}", path.display(), e);
                Self::empty()
            }
        }
    }

    pub fn from_json(json_str: &str) -> Self {
        let biomes = serde_json::from_str(json_str).unwrap_or_default();
        BiomePalette { biomes }
    }

    pub fn empty() -> Self {
        BiomePalette { biomes: HashMap::new() }
    }

    pub fn get_biome_color(&self, name: &str) -> Rgb {
        self.biomes
            .get(name)
            .map(|b| Rgb::from(b.grass_color))
            .unwrap_or(Rgb::new(140, 140, 140))
    }

    pub fn len(&self) -> usize {
        self.biomes.len()
    }
}

// ── Biome Tint Block Set ───────────────────────────────────────────

pub struct BiomeTintBlocks {
    blocks: Vec<String>,
}

impl BiomeTintBlocks {
    pub fn from_file(path: &Path) -> Self {
        match std::fs::read_to_string(path) {
            Ok(json) => Self::from_json(&json),
            Err(e) => {
                eprintln!("Warning: failed to load tint blocks '{}': {}", path.display(), e);
                Self::empty()
            }
        }
    }

    pub fn from_json(json_str: &str) -> Self {
        let blocks: Vec<String> = serde_json::from_str(json_str).unwrap_or_default();
        BiomeTintBlocks { blocks }
    }

    pub fn empty() -> Self {
        BiomeTintBlocks { blocks: Vec::new() }
    }

    pub fn contains(&self, name: &str) -> bool {
        self.blocks.iter().any(|b| b == name)
    }

    pub fn len(&self) -> usize {
        self.blocks.len()
    }
}

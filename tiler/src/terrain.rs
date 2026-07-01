use crate::colors::BlockCategories;
use crate::nbt_parser::{BlockEntry, ChunkRawData};
use std::collections::HashMap;

/// Extracted surface terrain for a 16×16 chunk column.
///
/// Includes height map, surface block IDs/names, cave flags, biomes, and height range.
#[derive(Debug, Clone)]
pub struct TerrainData {
    pub heights: [[f32; 16]; 16],
    pub surface_blocks: [[u16; 16]; 16],
    pub surface_block_names: [[String; 16]; 16],
    pub has_caves: [[bool; 16]; 16],
    pub surface_biomes: [[String; 16]; 16],
    pub min_height: i16,
    pub max_height: i16,
}

/// Create a 16x16 grid of empty `String`s.
fn empty_string_grid() -> [[String; 16]; 16] {
    std::array::from_fn(|_| std::array::from_fn(|_| String::new()))
}

/// Extract surface terrain data from a raw chunk.
///
/// Finds highest non-air, non-plant, non-water block per column (using `categories`).
/// Detects caves (≥4 consecutive air below surface), builds biome map.
pub fn extract_terrain(chunk: &ChunkRawData, categories: &BlockCategories) -> TerrainData {
    // Build Y-sorted index of blocks per column (x, z)
    // First, organize blocks by column
    let mut columns: HashMap<(u8, u8), Vec<&BlockEntry>> = HashMap::new();

    for block in &chunk.blocks {
        columns.entry((block.local_x, block.local_z))
            .or_default()
            .push(block);
    }

    // Sort each column by Y descending
    for col in columns.values_mut() {
        col.sort_by(|a, b| b.y.cmp(&a.y));
    }

    // Build heightmap and biome maps
    let mut heights = [[0.0f32; 16]; 16];
    let mut surface_blocks = [[0u16; 16]; 16];
    let mut surface_block_names = empty_string_grid();
    let mut has_caves = [[false; 16]; 16];
    let mut surface_biomes = empty_string_grid();

    // Build biome lookup
    let mut biome_map: HashMap<(u8, u8), String> = HashMap::new();
    for biome in &chunk.biomes {
        biome_map.entry((biome.local_x, biome.local_z))
            .or_insert_with(|| biome.biome_name.clone());
    }

    // Pre-compute block name → ID mapping
    let mut block_ids: HashMap<&str, u16> = HashMap::new();
    {
        let mut id_counter = 10u16;
        for block in &chunk.blocks {
            let key: &str = block.block_name.as_str();
            if !block_ids.contains_key(key) {
                block_ids.insert(key, id_counter);
                id_counter += 1;
            }
        }
    }

    for x in 0..16u8 {
        for z in 0..16u8 {
            let col = columns.get(&(x, z));
            if let Some(blocks) = col {
                // Find surface (highest non-air, non-plant, non-water block).
                // Water is skipped so the block below (sand, gravel, stone) is the
                // surface, giving visible underwater topography with a blue overlay.
                for block in blocks.iter() {
                    let bx = x as usize;
                    let bz = z as usize;
                    if categories.water.contains(&block.block_name) || categories.air.contains(&block.block_name) || categories.plant.contains(&block.block_name) {
                        continue;
                    }

                    let id = block_ids.get(block.block_name.as_str()).copied().unwrap_or(0);
                    surface_blocks[bx][bz] = id;
                    surface_block_names[bx][bz] = block.block_name.clone();
                    heights[bx][bz] = block.y as f32;

                    // Cave detection: check for >4 consecutive air blocks below surface
                    // Iterate bottom-up to correctly count consecutive air below surface
                    let mut air_count = 0i32;
                    for b in blocks.iter().rev() {
                        if b.local_x == x && b.local_z == z && b.y < block.y {
                            if categories.air.contains(&b.block_name) {
                                air_count += 1;
                                if air_count > 4 {
                                    has_caves[bx][bz] = true;
                                    break;
                                }
                            } else {
                                air_count = 0;
                            }
                        }
                    }
                    break;
                }

                // If no surface found (all water/air), try water
                if surface_blocks[x as usize][z as usize] == 0 {
                    for block in blocks.iter() {
                        if categories.water.contains(&block.block_name) {
                            let id = block_ids.get(block.block_name.as_str()).copied().unwrap_or(9);
                            surface_blocks[x as usize][z as usize] = id;
                            surface_block_names[x as usize][z as usize] = block.block_name.clone();
                            heights[x as usize][z as usize] = block.y as f32;
                            break;
                        }
                    }
                }
            }

            // Get biome for this column (empty = no tint)
            if let Some(biome) = biome_map.get(&(x, z)) {
                surface_biomes[x as usize][z as usize] = biome.clone();
            }
        }
    }

    let min_h = heights.iter()
        .flat_map(|r| r.iter())
        .cloned()
        .fold(f32::MAX, f32::min) as i16;
    let max_h = heights.iter()
        .flat_map(|r| r.iter())
        .cloned()
        .fold(f32::MIN, f32::max) as i16;

    TerrainData {
        heights,
        surface_blocks,
        surface_block_names,
        has_caves,
        surface_biomes,
        min_height: if min_h == i16::MAX { 0 } else { min_h },
        max_height: if max_h == i16::MIN { 0 } else { max_h },
    }
}

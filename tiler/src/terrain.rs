use crate::nbt_parser::{BlockEntry, ChunkRawData};
use std::collections::HashMap;

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

fn empty_string_grid() -> [[String; 16]; 16] {
    std::array::from_fn(|_| std::array::from_fn(|_| String::new()))
}

// Block IDs for common blocks
pub const BLOCK_AIR: u16 = 0;
pub const BLOCK_STONE: u16 = 1;
pub const BLOCK_GRASS: u16 = 2;
pub const BLOCK_DIRT: u16 = 3;
pub const BLOCK_WATER: u16 = 9;
pub const BLOCK_FLOWING_WATER: u16 = 208;

// Block name categorization
fn is_water(name: &str) -> bool {
    name == "minecraft:water" || name == "minecraft:flowing_water" || name == "minecraft:lava" || name == "minecraft:flowing_lava"
}

fn is_air(name: &str) -> bool {
    name == "minecraft:air" || name == "minecraft:cave_air" || name == "minecraft:void_air"
}

fn is_plant(name: &str) -> bool {
    name.starts_with("minecraft:grass")
        || name.starts_with("minecraft:tall_grass")
        || name == "minecraft:fern"
        || name == "minecraft:large_fern"
        || name.starts_with("minecraft:dead_bush")
        || name.starts_with("minecraft:seagrass")
        || name.starts_with("minecraft:tall_seagrass")
        || name.ends_with("_flower")
        || name.ends_with("_petals")
        || name.contains("_mushroom")
        || name.contains("_sapling")
        || name.contains("_coral")
        || name.contains("_kelp")
        || name.contains("_vine")
        || name.contains("_snow")
        || name.contains("_torch")
        || name.contains("_button")
        || name.contains("_pressure_plate")
        || name.contains("_sign")
        || name.contains("_hanging_sign")
        || name.contains("_candle")
        || name.contains("_carpet")
        || name.contains("_wool")
        || name.contains("_bed")
        || name.contains("_door")
        || name.contains("_trapdoor")
        || name.contains("_fence")
        || name.contains("_fence_gate")
        || name.contains("_wall")
        || name.contains("_slab")
        || name.contains("_stairs")
        || name.contains("_rail")
        || name.contains("_lever")
        || name.contains("_lily")
        || name.contains("_piston")
        || name.contains("_lamp")
        || name.contains("_lantern")
        || name.contains("_chain")
        || name.contains("_bars")
        || name.contains("_rod")
        || name.contains("_portal")
        || name.contains("_spawner")
        || name.contains("_stem")
        || name.contains("_crop")
        || name.contains("_plant")
        || name.contains("_podzol")
        || name.contains("_mycelium")
        || name.contains("_path")
        || name.contains("_concrete_powder")
        || name.contains("_terracotta")
        || name.contains("_glass")
        || name.contains("_leaves")
        || name.contains("_log")
        || name.contains("_wood")
        || name.contains("_planks")
        || name.contains("_button")
}

pub fn extract_terrain(chunk: &ChunkRawData) -> TerrainData {
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
                // Find surface (highest non-air, non-plant block)
                // Water is a valid surface (oceans, rivers) and has higher priority
                // than any block below it.
                for block in blocks.iter() {
                    if is_air(&block.block_name) || is_plant(&block.block_name) {
                        continue;
                    }

                    // This is the surface block
                    let id = block_ids.get(block.block_name.as_str()).copied().unwrap_or(0);
                    surface_blocks[x as usize][z as usize] = id;
                    surface_block_names[x as usize][z as usize] = block.block_name.clone();
                    heights[x as usize][z as usize] = block.y as f32;

                    // Cave detection: check if there are >4 air blocks below surface
                    let mut air_count = 0i32;
                    for b in blocks.iter() {
                        if b.local_x == x && b.local_z == z && b.y < block.y {
                            if is_air(&b.block_name) {
                                air_count += 1;
                            } else {
                                air_count = 0;
                            }
                            if air_count > 4 {
                                has_caves[x as usize][z as usize] = true;
                                break;
                            }
                        }
                    }
                    break;
                }

                // If no surface found (all water/air), try water
                if surface_blocks[x as usize][z as usize] == 0 {
                    for block in blocks.iter() {
                        if is_water(&block.block_name) {
                            let id = block_ids.get(block.block_name.as_str()).copied().unwrap_or(BLOCK_WATER);
                            surface_blocks[x as usize][z as usize] = id;
                            surface_block_names[x as usize][z as usize] = block.block_name.clone();
                            heights[x as usize][z as usize] = block.y as f32;
                            break;
                        }
                    }
                }
            }

            // Get biome for this column
            surface_biomes[x as usize][z as usize] = biome_map
                .get(&(x, z))
                .cloned()
                .unwrap_or_else(|| "minecraft:plains".to_string());
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

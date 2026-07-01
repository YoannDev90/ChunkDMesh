use crate::colors::{BlockPalette, BiomePalette, Rgb};
use crate::nbt_parser::ChunkRawData;
use crate::shading::{apply_shading, compute_normals, EdgeHeights, ShadingConfig};
use crate::terrain::extract_terrain;
use crate::waterflow::{find_water, WaterflowData};
use image::{ImageBuffer, RgbImage};

pub struct RenderConfig {
    pub enable_shading: bool,
    pub enable_biome_tint: bool,
    pub enable_waterflow: bool,
    pub shading: ShadingConfig,
}

impl Default for RenderConfig {
    fn default() -> Self {
        RenderConfig {
            enable_shading: true,
            enable_biome_tint: true,
            enable_waterflow: true,
            shading: ShadingConfig::default(),
        }
    }
}

pub struct RenderOutput {
    pub png_data: Vec<u8>,
    pub terrain_json: String,
}

/// Water color: a visible semi-transparent blue
const WATER_COLOR: Rgb = Rgb { r: 40, g: 100, b: 200 };

fn build_surface_colors(
    terrain: &crate::terrain::TerrainData,
    waterflow: &WaterflowData,
    block_palette: &BlockPalette,
    biome_palette: &BiomePalette,
    biome_tint_blocks: &crate::colors::BiomeTintBlocks,
    config: &RenderConfig,
) -> [[Rgb; 16]; 16] {
    let mut colors = [[Rgb::new(0, 0, 0); 16]; 16];

    for x in 0..16 {
        for z in 0..16 {
            let block_name = &terrain.surface_block_names[x][z];
            let is_water_block = block_name == "minecraft:water"
                || block_name == "minecraft:flowing_water"
                || block_name == "minecraft:lava"
                || block_name == "minecraft:flowing_lava";

            let mut color = if is_water_block {
                // Water blocks: use a dedicated blue color (not palette lookup)
                WATER_COLOR
            } else {
                block_palette.get_block_color(block_name)
            };

            // Biome tint (only for non-water blocks)
            if !is_water_block
                && config.enable_biome_tint
                && !terrain.surface_biomes[x][z].is_empty()
                && biome_tint_blocks.contains(block_name)
            {
                let biome_color = biome_palette.get_biome_color(&terrain.surface_biomes[x][z]);
                color = color.blend(&biome_color, 0.35);
            }

            // Water flow overlay: darken adjacent pixels near water edges
            if !is_water_block && waterflow.water_map[x][z] {
                color = color.blend(&WATER_COLOR, 0.2);
            }

            colors[x][z] = color;
        }
    }

    colors
}

pub fn render_chunk(
    chunk: &ChunkRawData,
    config: &RenderConfig,
    block_palette: &BlockPalette,
    biome_palette: &BiomePalette,
    biome_tint_blocks: &crate::colors::BiomeTintBlocks,
) -> RenderOutput {
    render_chunk_with_edges(chunk, config, block_palette, biome_palette, biome_tint_blocks, None)
}

pub fn render_chunk_with_edges(
    chunk: &ChunkRawData,
    config: &RenderConfig,
    block_palette: &BlockPalette,
    biome_palette: &BiomePalette,
    biome_tint_blocks: &crate::colors::BiomeTintBlocks,
    edge_heights: Option<&EdgeHeights>,
) -> RenderOutput {
    let terrain = extract_terrain(chunk);
    let waterflow = find_water(chunk);

    let mut colors = build_surface_colors(&terrain, &waterflow, block_palette, biome_palette, biome_tint_blocks, config);

    if config.enable_shading {
        let normals = compute_normals(&terrain.heights, config.shading.height_exaggeration, edge_heights);
        colors = apply_shading(&colors, &normals, &terrain.has_caves, &config.shading);
    }

    let png_data = render_to_png(&colors);

    // Build terrain JSON for hover data
    let terrain_json = build_terrain_json(&terrain, &waterflow);

    RenderOutput {
        png_data,
        terrain_json,
    }
}

fn render_to_png(colors: &[[Rgb; 16]; 16]) -> Vec<u8> {
    let scale: u32 = 16;
    let size = 16 * scale;
    let mut img: RgbImage = ImageBuffer::new(size, size);

    for x in 0..16u32 {
        for z in 0..16u32 {
            let color = colors[x as usize][z as usize];
            let pixel = image::Rgb([color.r, color.g, color.b]);

            for dx in 0..scale {
                for dz in 0..scale {
                    img.put_pixel(
                        x * scale + dx,
                        z * scale + dz,
                        pixel,
                    );
                }
            }
        }
    }

    let mut buf = Vec::new();
    img.write_to(&mut std::io::Cursor::new(&mut buf), image::ImageFormat::Png)
        .expect("Failed to encode PNG");
    buf
}

fn build_terrain_json(
    terrain: &crate::terrain::TerrainData,
    waterflow: &WaterflowData,
) -> String {
    use serde_json::json;

    let heights: Vec<Vec<f32>> = (0..16)
        .map(|z| (0..16).map(|x| terrain.heights[x][z]).collect())
        .collect();

    let block_ids: Vec<Vec<u16>> = (0..16)
        .map(|z| (0..16).map(|x| terrain.surface_blocks[x][z]).collect())
        .collect();

    let block_names: Vec<Vec<&str>> = (0..16)
        .map(|z| (0..16).map(|x| terrain.surface_block_names[x][z].as_str()).collect())
        .collect();

    let biomes: Vec<Vec<&str>> = (0..16)
        .map(|z| (0..16).map(|x| terrain.surface_biomes[x][z].as_str()).collect())
        .collect();

    let caves: Vec<Vec<bool>> = (0..16)
        .map(|z| (0..16).map(|x| terrain.has_caves[x][z]).collect())
        .collect();

    let water: Vec<Vec<bool>> = (0..16)
        .map(|z| (0..16).map(|x| waterflow.water_map[x][z]).collect())
        .collect();

    json!({
        "heights": heights,
        "block_ids": block_ids,
        "block_names": block_names,
        "biomes": biomes,
        "has_caves": caves,
        "water_map": water,
        "num_waterfalls": waterflow.waterfalls.len(),
        "num_rivers": waterflow.rivers.len(),
        "min_height": terrain.min_height,
        "max_height": terrain.max_height,
    }).to_string()
}

pub fn render_region_chunks(
    chunks: &[ChunkRawData],
    config: &RenderConfig,
    block_palette: &BlockPalette,
    biome_palette: &BiomePalette,
    biome_tint_blocks: &crate::colors::BiomeTintBlocks,
) -> Vec<(i32, i32, RenderOutput)> {
    use rayon::prelude::*;
    use std::collections::HashMap;

    // Build chunk index for neighbor lookup
    let mut chunk_map: HashMap<(i32, i32), usize> = HashMap::new();
    for (i, chunk) in chunks.iter().enumerate() {
        chunk_map.insert((chunk.chunk_x, chunk.chunk_z), i);
    }

    // Pre-extract all terrain height maps
    let terrains: Vec<_> = chunks.iter().map(|c| extract_terrain(c)).collect();

    chunks.par_iter().enumerate().map(|(_idx, chunk)| {
        // Build edge heights from neighboring chunks
        let cx = chunk.chunk_x;
        let cz = chunk.chunk_z;

        let left = chunk_map.get(&(cx - 1, cz)).map(|&i| {
            let mut edge = [0.0f32; 16];
            for z in 0..16 { edge[z] = terrains[i].heights[15][z]; }
            edge
        });
        let right = chunk_map.get(&(cx + 1, cz)).map(|&i| {
            let mut edge = [0.0f32; 16];
            for z in 0..16 { edge[z] = terrains[i].heights[0][z]; }
            edge
        });
        let top = chunk_map.get(&(cx, cz - 1)).map(|&i| {
            let mut edge = [0.0f32; 16];
            for x in 0..16 { edge[x] = terrains[i].heights[x][15]; }
            edge
        });
        let bottom = chunk_map.get(&(cx, cz + 1)).map(|&i| {
            let mut edge = [0.0f32; 16];
            for x in 0..16 { edge[x] = terrains[i].heights[x][0]; }
            edge
        });

        let edge = EdgeHeights { left, right, top, bottom };
        let output = render_chunk_with_edges(chunk, config, block_palette, biome_palette, biome_tint_blocks, Some(&edge));
        (chunk.chunk_x, chunk.chunk_z, output)
    }).collect()
}

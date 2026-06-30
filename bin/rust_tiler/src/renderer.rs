use crate::colors::{BlockPalette, BiomePalette, Rgb};
use crate::nbt_parser::ChunkRawData;
use crate::shading::{apply_shading, compute_normals, ShadingConfig};
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
            let mut color = block_palette.get_block_color(block_name);

            // Biome tint
            if config.enable_biome_tint
                && !terrain.surface_biomes[x][z].is_empty()
                && biome_tint_blocks.contains(block_name)
            {
                let biome_color = biome_palette.get_biome_color(&terrain.surface_biomes[x][z]);
                color = color.blend(&biome_color, 0.35);
            }

            // Subtle water tint
            if waterflow.water_map[x][z] {
                color = color.blend(&Rgb::new(30, 110, 200), 0.15);
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
    let terrain = extract_terrain(chunk);
    let waterflow = find_water(chunk);

    let mut colors = build_surface_colors(&terrain, &waterflow, block_palette, biome_palette, biome_tint_blocks, config);

    if config.enable_shading {
        let normals = compute_normals(&terrain.heights, config.shading.height_exaggeration);
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

    chunks.par_iter().map(|chunk| {
        let output = render_chunk(chunk, config, block_palette, biome_palette, biome_tint_blocks);
        (chunk.chunk_x, chunk.chunk_z, output)
    }).collect()
}

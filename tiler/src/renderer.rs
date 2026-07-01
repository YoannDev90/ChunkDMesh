use crate::colors::{BlockCategories, BlockPalette, BiomePalette, Rgb};
use crate::nbt_parser::ChunkRawData;
use crate::shading::{apply_shading, compute_normals, EdgeHeights, ShadingConfig};
use crate::terrain::extract_terrain;
use crate::waterflow::{find_water, WaterflowData};
use image::{ImageBuffer, RgbImage};

/// Render configuration: shading, biome tint, water overlay, and waterflow.
pub struct RenderConfig {
    pub enable_shading: bool,
    pub enable_biome_tint: bool,
    pub enable_waterflow: bool,
    pub shading: ShadingConfig,
    pub water_overlay_color: Rgb,
    pub water_overlay_blend: f32,
}

impl Default for RenderConfig {
    /// Default render config: shading/biome/waterflow on, blue water overlay at 35%.
    fn default() -> Self {
        RenderConfig {
            enable_shading: true,
            enable_biome_tint: true,
            enable_waterflow: true,
            shading: ShadingConfig::default(),
            water_overlay_color: Rgb::new(40, 100, 220),
            water_overlay_blend: 0.55,
        }
    }
}

impl From<&crate::config::TilerConfig> for RenderConfig {
    /// Convert `TilerConfig` to `RenderConfig`.
    fn from(cfg: &crate::config::TilerConfig) -> Self {
        let c = cfg.water_overlay_color;
        RenderConfig {
            enable_shading: cfg.enable_shading,
            enable_biome_tint: cfg.enable_biome_tint,
            enable_waterflow: cfg.enable_waterflow,
            shading: cfg.shading.clone(),
            water_overlay_color: Rgb::new(c[0], c[1], c[2]),
            water_overlay_blend: cfg.water_overlay_blend,
        }
    }
}

/// Render result: PNG image bytes and terrain data JSON.
pub struct RenderOutput {
    pub png_data: Vec<u8>,
    pub terrain_json: String,
}

/// Compute final surface colors: block color + biome tint + water overlay.
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

            // Biome tint (only for non-water blocks; water overlay applied after)
            if config.enable_biome_tint
                && !terrain.surface_biomes[x][z].is_empty()
                && biome_tint_blocks.contains(block_name)
            {
                let biome_color = biome_palette.get_biome_color(&terrain.surface_biomes[x][z]);
                color = color.blend(&biome_color, 0.35);
            }

            // Water overlay: blue tint on any column containing water.
            // Shows underwater terrain through the tint, revealing topography.
            if waterflow.water_map[x][z] && config.enable_waterflow {
                color = color.blend(&config.water_overlay_color, config.water_overlay_blend);
            }

            colors[x][z] = color;
        }
    }

    colors
}

/// Render single chunk to PNG and JSON (no edge neighbor data).
pub fn render_chunk(
    chunk: &ChunkRawData,
    config: &RenderConfig,
    block_palette: &BlockPalette,
    biome_palette: &BiomePalette,
    biome_tint_blocks: &crate::colors::BiomeTintBlocks,
    categories: &BlockCategories,
) -> RenderOutput {
    render_chunk_with_edges(chunk, config, block_palette, biome_palette, biome_tint_blocks, categories, None)
}

/// Render chunk with optional neighbor edge heights for seamless borders.
///
/// Extracts terrain, computes waterflow, builds surface colors,
/// applies shading, produces PNG and terrain JSON.
pub fn render_chunk_with_edges(
    chunk: &ChunkRawData,
    config: &RenderConfig,
    block_palette: &BlockPalette,
    biome_palette: &BiomePalette,
    biome_tint_blocks: &crate::colors::BiomeTintBlocks,
    categories: &BlockCategories,
    edge_heights: Option<&EdgeHeights>,
) -> RenderOutput {
    let terrain = extract_terrain(chunk, categories);
    let waterflow = find_water(chunk, categories);

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

/// Scale 16×16 color grid to 256×256 PNG image bytes.
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
        .expect("PNG encode failed");
    buf
}

/// Build JSON string with terrain heights, block IDs/names, biomes, caves, water data.
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

/// Render multiple chunks with neighbor-aware edge blending.
///
/// Extracts terrain, builds edge heights from adjacent chunks,
/// renders in parallel using rayon.
pub fn render_region_chunks(
    chunks: &[ChunkRawData],
    config: &RenderConfig,
    block_palette: &BlockPalette,
    biome_palette: &BiomePalette,
    biome_tint_blocks: &crate::colors::BiomeTintBlocks,
    categories: &BlockCategories,
) -> Vec<(i32, i32, RenderOutput)> {
    use rayon::prelude::*;
    use std::collections::HashMap;

    // Build chunk index for neighbor lookup
    let mut chunk_map: HashMap<(i32, i32), usize> = HashMap::new();
    for (i, chunk) in chunks.iter().enumerate() {
        chunk_map.insert((chunk.chunk_x, chunk.chunk_z), i);
    }

    // Pre-extract all terrain height maps
    let terrains: Vec<_> = chunks.iter().map(|c| extract_terrain(c, categories)).collect();

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
        let output = render_chunk_with_edges(chunk, config, block_palette, biome_palette, biome_tint_blocks, categories, Some(&edge));
        (chunk.chunk_x, chunk.chunk_z, output)
    }).collect()
}

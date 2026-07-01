use std::path::PathBuf;
use std::time::Instant;

use minecraft_map_generator::colors::{BiomePalette, BiomeTintBlocks, BlockCategories, BlockPalette};
use minecraft_map_generator::config::TilerConfig;
use minecraft_map_generator::nbt_parser::{read_chunk, read_region_file};
use minecraft_map_generator::renderer::{render_chunk, RenderConfig};

/// Print CLI usage info to stderr.
fn print_usage() {
    let name = std::env::args().next().unwrap_or_else(|| "mcmap".into());
    eprintln!("Usage: {name} [options] <region.mca> <chunk_x> <chunk_z>");
    eprintln!("       {name} [options] <region.mca> --all [--output-dir <dir>]");
    eprintln!("Options:");
    eprintln!("  --config <path>        Tiler config JSON (water overlay, shading, etc.)");
    eprintln!("  --palette <path>       Block color palette JSON");
    eprintln!("  --biome-colors <path>  Biome color palette JSON");
    eprintln!("  --biome-tints <path>   Biome tint block list JSON");
    eprintln!("  --block-categories     Block categories JSON (water/air/plant lists)");
    eprintln!("  --output-dir <dir>     Output directory (default: cwd)");
}

/// Parsed CLI arguments for tiler tool.
struct Args {
    region_file: PathBuf,
    chunk_x: Option<i32>,
    chunk_z: Option<i32>,
    _render_all: bool,
    output_dir: PathBuf,
    config_path: Option<PathBuf>,
    palette_path: Option<PathBuf>,
    biome_colors_path: Option<PathBuf>,
    biome_tints_path: Option<PathBuf>,
    block_categories_path: Option<PathBuf>,
}

/// Parse CLI arguments into `Args` struct.
///
/// Supports `--config`, `--palette`, `--biome-colors`, `--biome-tints`,
/// `--output-dir`, `--all`, and positional region/chunk coordinates.
fn parse_args() -> Result<Args, String> {
    let raw: Vec<String> = std::env::args().collect();
    let mut config_path: Option<PathBuf> = None;
    let mut palette_path: Option<PathBuf> = None;
    let mut biome_colors_path: Option<PathBuf> = None;
    let mut biome_tints_path: Option<PathBuf> = None;
    let mut block_categories_path: Option<PathBuf> = None;
    let mut output_dir = PathBuf::from(".");
    let mut positional = Vec::new();
    let mut render_all = false;

    let mut i = 1;
    while i < raw.len() {
        match raw[i].as_str() {
            "--config" => {
                i += 1;
                if i < raw.len() { config_path = Some(PathBuf::from(&raw[i])); }
                else { return Err("--config requires a path".into()); }
            }
            "--palette" | "-p" => {
                i += 1;
                if i < raw.len() { palette_path = Some(PathBuf::from(&raw[i])); }
                else { return Err("--palette requires a path".into()); }
            }
            "--biome-colors" => {
                i += 1;
                if i < raw.len() { biome_colors_path = Some(PathBuf::from(&raw[i])); }
                else { return Err("--biome-colors requires a path".into()); }
            }
            "--biome-tints" => {
                i += 1;
                if i < raw.len() { biome_tints_path = Some(PathBuf::from(&raw[i])); }
                else { return Err("--biome-tints requires a path".into()); }
            }
            "--block-categories" => {
                i += 1;
                if i < raw.len() { block_categories_path = Some(PathBuf::from(&raw[i])); }
                else { return Err("--block-categories requires a path".into()); }
            }
            "--output-dir" => {
                i += 1;
                if i < raw.len() { output_dir = PathBuf::from(&raw[i]); }
                else { return Err("--output-dir requires a path".into()); }
            }
            "--all" => render_all = true,
            _ => positional.push(raw[i].clone()),
        }
        i += 1;
    }

    if positional.is_empty() {
        return Err("missing region file".into());
    }

    let region_file = PathBuf::from(&positional[0]);

    let chunk_x = if !render_all && positional.len() >= 3 {
        Some(positional[1].parse().map_err(|_| "invalid chunk_x")?)
    } else { None };
    let chunk_z = if !render_all && positional.len() >= 3 {
        Some(positional[2].parse().map_err(|_| "invalid chunk_z")?)
    } else { None };

    std::fs::create_dir_all(&output_dir).map_err(|e| format!("cannot create output dir: {e}"))?;

    Ok(Args { region_file, chunk_x, chunk_z, _render_all: render_all, output_dir, config_path, palette_path, biome_colors_path, biome_tints_path, block_categories_path })
}

/// Entry point: parse args, load palettes/config, render chunk(s) to PNG+JSON.
fn main() {
    let args = match parse_args() {
        Ok(a) => a,
        Err(e) => {
            eprintln!("Error: {e}");
            print_usage();
            std::process::exit(1);
        }
    };

    // Load palettes (best-effort, missing files → empty palette = error color)
    let block_palette = match &args.palette_path {
        Some(p) if p.exists() => {
            let bp = BlockPalette::from_file(p);
            eprintln!("Block palette: {} blocks from {}", bp.len(), p.display());
            bp
        }
        _ => {
            eprintln!("Warning: no block palette, using error color");
            BlockPalette::empty()
        }
    };

    let biome_palette = match &args.biome_colors_path {
        Some(p) if p.exists() => {
            let bp = BiomePalette::from_file(p);
            eprintln!("Biome palette: {} biomes from {}", bp.len(), p.display());
            bp
        }
        _ => BiomePalette::empty(),
    };

    let biome_tint_blocks = match &args.biome_tints_path {
        Some(p) if p.exists() => {
            let bt = BiomeTintBlocks::from_file(p);
            eprintln!("Biome tint blocks: {} from {}", bt.len(), p.display());
            bt
        }
        _ => BiomeTintBlocks::empty(),
    };

    let block_categories = match &args.block_categories_path {
        Some(p) if p.exists() => {
            let bc = BlockCategories::from_file(p);
            eprintln!("Block categories: {} from {}", bc.len(), p.display());
            bc
        }
        _ => {
            eprintln!("Warning: no block categories, all blocks treated as solid");
            BlockCategories::empty()
        }
    };

    if !args.region_file.exists() {
        eprintln!("File not found: {}", args.region_file.display());
        std::process::exit(1);
    }

    let config = match &args.config_path {
        Some(p) => match TilerConfig::from_file(&p.to_string_lossy().as_ref()) {
            Ok(cfg) => {
                eprintln!("Config loaded from {}", p.display());
                eprintln!("  water overlay: {:?} @ {:.0}%", cfg.water_overlay_color, cfg.water_overlay_blend * 100.0);
                RenderConfig::from(&cfg)
            }
            Err(e) => { eprintln!("Error: {e}"); std::process::exit(1); }
        }
        None => RenderConfig::default(),
    };

    if let (Some(cx), Some(cz)) = (args.chunk_x, args.chunk_z) {
        let start = Instant::now();
        match read_chunk(&args.region_file, cx, cz) {
            Ok(chunk) => {
                eprintln!("Read chunk ({cx}, {cz}) in {:?}", start.elapsed());
                let output = render_chunk(&chunk, &config, &block_palette, &biome_palette, &biome_tint_blocks, &block_categories);
                let png_path = args.output_dir.join(format!("chunk_{cx}_{cz}.png"));
                let json_path = args.output_dir.join(format!("chunk_{cx}_{cz}.json"));
                std::fs::write(&png_path, &output.png_data).expect("Failed to write PNG");
                std::fs::write(&json_path, &output.terrain_json).expect("Failed to write JSON");
                println!("{} ({} B)", png_path.display(), output.png_data.len());
            }
            Err(e) => eprintln!("Error reading chunk ({cx}, {cz}): {e}"),
        }
    } else {
        let start = Instant::now();
        let chunks = match read_region_file(&args.region_file) {
            Ok(c) => c,
            Err(e) => { eprintln!("Error reading region: {e}"); std::process::exit(1); }
        };
        if chunks.is_empty() { eprintln!("No chunks found"); std::process::exit(1); }
        eprintln!("Read {} chunks in {:?}", chunks.len(), start.elapsed());

        use rayon::prelude::*;
        let errors: Vec<String> = chunks.par_iter().filter_map(|c| {
            let out = render_chunk(c, &config, &block_palette, &biome_palette, &biome_tint_blocks, &block_categories);
            let pn = args.output_dir.join(format!("chunk_{}_{}.png", c.chunk_x, c.chunk_z));
            if let Err(e) = std::fs::write(&pn, &out.png_data) {
                Some(format!("Failed to write {}: {}", pn.display(), e))
            } else {
                None
            }
        }).collect();
        if !errors.is_empty() {
            eprintln!("{} chunk write(s) failed:", errors.len());
            for err in &errors {
                eprintln!("  {err}");
            }
        }
        eprintln!("Rendered {} chunks to {} in {:?}",
                  chunks.len(), args.output_dir.display(), start.elapsed());
    }
}

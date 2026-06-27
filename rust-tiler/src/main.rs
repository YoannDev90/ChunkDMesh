mod block_colors;
mod nbt;
mod render;

use std::fs;
use std::path::PathBuf;
use std::time::Instant;

use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(name = "chunkdmesh-tiler")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Render a .mca region file to PNG
    Render {
        /// Path to .mca input file
        #[arg(short, long)]
        input: PathBuf,

        /// Path to PNG output file (default: stdout)
        #[arg(short, long)]
        output: Option<PathBuf>,

        /// Scale factor (default: 1)
        #[arg(short, long, default_value = "1")]
        scale: u32,

        /// Print timing info to stderr
        #[arg(short, long)]
        verbose: bool,
    },
    /// Benchmark: render N times and report time
    Bench {
        /// Path to .mca input file
        #[arg(short, long)]
        input: PathBuf,

        /// Number of iterations
        #[arg(short, long, default_value = "5")]
        iterations: u32,

        /// Scale factor
        #[arg(short, long, default_value = "1")]
        scale: u32,
    },
}

fn main() -> Result<(), String> {
    let cli = Cli::parse();

    match cli.command {
        Commands::Render {
            input,
            output,
            scale,
            verbose,
        } => cmd_render(&input, output.as_ref(), scale, verbose),
        Commands::Bench {
            input,
            iterations,
            scale,
        } => cmd_bench(&input, iterations, scale),
    }
}

fn cmd_render(
    input: &PathBuf,
    output: Option<&PathBuf>,
    scale: u32,
    verbose: bool,
) -> Result<(), String> {
    let t0 = Instant::now();

    let data = fs::read(input).map_err(|e| format!("Read error: {}", e))?;

    let t1 = Instant::now();
    let pixels = render::render_region(&data, scale)?;
    let t2 = Instant::now();

    let out_dim = 512 * scale;
    let png = render::encode_png(&pixels, out_dim, out_dim)?;
    let t3 = Instant::now();

    match output {
        Some(path) => fs::write(path, &png).map_err(|e| format!("Write error: {}", e))?,
        None => {
            use std::io::Write;
            std::io::stdout()
                .write_all(&png)
                .map_err(|e| format!("Stdout error: {}", e))?;
        }
    }

    if verbose {
        let total = t0.elapsed();
        eprintln!(
            "timing: read={:.2?} render={:.2?} encode={:.2?} total={:.2?} size={}x{} png={}KB",
            t1 - t0,
            t2 - t1,
            t3 - t2,
            total,
            out_dim,
            out_dim,
            png.len() / 1024,
        );
    }

    Ok(())
}

fn cmd_bench(input: &PathBuf, iterations: u32, scale: u32) -> Result<(), String> {
    let data = fs::read(input).map_err(|e| format!("Read error: {}", e))?;
    let file_size_kb = data.len() / 1024;

    eprintln!(
        "Bench: {} ({} KB), scale={}, {} iterations",
        input.display(),
        file_size_kb,
        scale,
        iterations
    );

    let out_dim = 512 * scale;
    let mut times = Vec::with_capacity(iterations as usize);

    for i in 0..iterations {
        let t0 = Instant::now();
        let pixels = render::render_region(&data, scale)?;
        let png = render::encode_png(&pixels, out_dim, out_dim)?;
        let elapsed = t0.elapsed();
        times.push(elapsed);
        eprintln!(
            "  iter {}: {:.2?} (PNG {} KB)",
            i + 1,
            elapsed,
            png.len() / 1024
        );
    }

    let avg: f64 = times.iter().map(|t| t.as_secs_f64()).sum::<f64>() / times.len() as f64;
    eprintln!("  avg: {:.3}s  total: {:.2?}", avg, times.iter().sum::<std::time::Duration>());
    Ok(())
}

use std::io::Read;

use crate::block_colors;
use crate::nbt::NbtReader;

const SECTOR_BYTES: u64 = 4096;

pub fn read_region_mmap(data: &[u8]) -> Vec<Option<Vec<u8>>> {
    let mut chunks: Vec<Option<Vec<u8>>> = Vec::with_capacity(1024);

    for i in 0..1024 {
        let off_bytes = &data[i * 4..i * 4 + 4];
        let offset_val =
            u32::from_be_bytes([off_bytes[0], off_bytes[1], off_bytes[2], off_bytes[3]]);

        let sector_offset = (offset_val >> 8) as u64;
        let sector_count = (offset_val & 0xff) as u64;

        if sector_offset == 0 || sector_count == 0 {
            chunks.push(None);
            continue;
        }

        let loc = (sector_offset * SECTOR_BYTES) as usize;
        if loc + 5 > data.len() {
            chunks.push(None);
            continue;
        }

        let chunk_len = u32::from_be_bytes([
            data[loc],
            data[loc + 1],
            data[loc + 2],
            data[loc + 3],
        ]) as usize;

        if loc + 5 + chunk_len - 1 > data.len() {
            chunks.push(None);
            continue;
        }

        let compression = data[loc + 4];
        let compressed = &data[loc + 5..loc + 5 + chunk_len - 1];

        let decompressed = match compression {
            1 => {
                let mut d = flate2::read::GzDecoder::new(compressed);
                let mut buf = Vec::new();
                if d.read_to_end(&mut buf).is_ok() {
                    buf
                } else {
                    chunks.push(None);
                    continue;
                }
            }
            2 => {
                let mut d = flate2::read::ZlibDecoder::new(compressed);
                let mut buf = Vec::new();
                if d.read_to_end(&mut buf).is_ok() {
                    buf
                } else {
                    chunks.push(None);
                    continue;
                }
            }
            3 => compressed.to_vec(),
            _ => {
                chunks.push(None);
                continue;
            }
        };

        chunks.push(Some(decompressed));
    }

    chunks
}

fn write_chunk_pixels(
    nbt_data: &[u8],
    pixels: &mut [u8],
    dim: u32,
    chunk_x: u32,
    chunk_z: u32,
    scale: u32,
) {
    let mut reader = NbtReader::new(nbt_data);
    let root = match reader.read_root() {
        Some(r) => r,
        None => return,
    };

    let root_compound = match root.as_compound() {
        Some(c) => c,
        None => return,
    };

    let sections_list = root_compound
        .get("sections")
        .and_then(|s| s.as_list())
        .or_else(|| {
            root_compound
                .get("Level")
                .and_then(|l| l.as_compound())
                .and_then(|l| l.get("Sections"))
                .and_then(|s| s.as_list())
        });

    let sections = match sections_list {
        Some(list) => list,
        None => return,
    };

    // Collect section info: (y, palette_names, data_longs, is_single)
    struct SecRaw {
        y: i32,
        palette: Vec<String>,
        data: Vec<i64>,
        single: bool,
    }

    let mut secs: Vec<SecRaw> = Vec::with_capacity(sections.len());

    for sec_val in sections.iter() {
        let sec = match sec_val.as_compound() {
            Some(s) => s,
            None => continue,
        };
        let y = sec.get("Y").and_then(|v| v.as_int()).unwrap_or(0);

        let bs = match sec.get("block_states").and_then(|v| v.as_compound()) {
            Some(b) => b,
            None => continue,
        };

        let palette_list = match bs.get("palette").and_then(|v| v.as_list()) {
            Some(p) => p,
            None => continue,
        };
        if palette_list.is_empty() {
            continue;
        }

        let palette: Vec<String> = palette_list
            .iter()
            .map(|v| {
                v.as_compound()
                    .and_then(|p| p.get("Name"))
                    .and_then(|n| n.as_str())
                    .unwrap_or("minecraft:air")
                    .to_string()
            })
            .collect();

        let data_arr = bs.get("data").and_then(|v| v.as_long_array());
        let single = data_arr.is_none();
        let data = data_arr.cloned().unwrap_or_default();

        secs.push(SecRaw {
            y,
            palette,
            data,
            single,
        });
    }

    if secs.is_empty() {
        return;
    }

    secs.sort_by(|a, b| b.y.cmp(&a.y));

    // Per-column results: allocated once per chunk
    let mut col_names: [String; 256] = std::array::from_fn(|_| String::new());
    let mut col_filled: [bool; 256] = [false; 256];

    for sec in &secs {
        if sec.single {
            let name = &sec.palette[0];
            if block_colors::is_air(name) {
                continue;
            }
            for lx in 0..16 {
                for lz in 0..16 {
                    let ci = lz * 16 + lx;
                    if !col_filled[ci] {
                        col_filled[ci] = true;
                        col_names[ci] = name.clone();
                    }
                }
            }
            continue;
        }

        let bits_per_entry = ((sec.palette.len() as f64 - 1.0).log2().ceil() as usize).max(4);
        let entries_per_long = 64 / bits_per_entry;
        let mask = (1u64 << bits_per_entry) - 1;

        for lx in 0..16 {
            for lz in 0..16 {
                let ci = lz * 16 + lx;
                if col_filled[ci] {
                    continue;
                }
                let idx_in = lx + lz * 16;

                for ly in (0..16).rev() {
                    let block_index = idx_in + ly * 256;
                    let long_idx = block_index / entries_per_long;
                    if long_idx >= sec.data.len() {
                        continue;
                    }
                    let bit_offset = (block_index % entries_per_long) * bits_per_entry;
                    let pal_id = ((sec.data[long_idx] as u64 >> bit_offset) & mask) as usize;
                    if pal_id >= sec.palette.len() {
                        continue;
                    }
                    let name = &sec.palette[pal_id];
                    if !block_colors::is_air(name) {
                        col_filled[ci] = true;
                        col_names[ci] = name.clone();
                        break;
                    }
                }
            }
        }
    }

    // Write pixels
    let dim_u = dim as usize;
    if scale == 1 {
        for dz in 0..16usize {
            for dx in 0..16usize {
                let ci = dz * 16 + dx;
                if !col_filled[ci] {
                    continue;
                }
                let color = block_colors::block_color(&col_names[ci]);
                let px = chunk_x as usize * 16 + dx;
                let py = chunk_z as usize * 16 + dz;
                let pi = (py * dim_u + px) * 3;
                if pi + 2 < pixels.len() {
                    pixels[pi] = color[0];
                    pixels[pi + 1] = color[1];
                    pixels[pi + 2] = color[2];
                }
            }
        }
    } else {
        let scale_u = scale as usize;
        for dz in 0..16usize {
            for dx in 0..16usize {
                let ci = dz * 16 + dx;
                if !col_filled[ci] {
                    continue;
                }
                let color = block_colors::block_color(&col_names[ci]);
                let px_base = (chunk_x as usize * 16 + dx) * scale_u;
                let py_base = (chunk_z as usize * 16 + dz) * scale_u;
                for sy in 0..scale_u {
                    for sx in 0..scale_u {
                        let px = px_base + sx;
                        let py = py_base + sy;
                        let pi = (py * dim_u + px) * 3;
                        if pi + 2 < pixels.len() {
                            pixels[pi] = color[0];
                            pixels[pi + 1] = color[1];
                            pixels[pi + 2] = color[2];
                        }
                    }
                }
            }
        }
    }
}

pub fn render_region(data: &[u8], scale: u32) -> Result<Vec<u8>, String> {
    let dim = 512 * scale;
    let mut pixels = vec![20u8; (dim * dim * 3) as usize];

    let chunks = read_region_mmap(data);

    for (idx, nbt_opt) in chunks.iter().enumerate() {
        let nbt_data = match nbt_opt {
            Some(d) => d,
            None => continue,
        };
        let chunk_x = (idx % 32) as u32;
        let chunk_z = (idx / 32) as u32;

        write_chunk_pixels(nbt_data, &mut pixels, dim, chunk_x, chunk_z, scale);
    }

    Ok(pixels)
}

pub fn encode_png(pixels: &[u8], width: u32, height: u32) -> Result<Vec<u8>, String> {
    let img = image::RgbImage::from_raw(width, height, pixels.to_vec())
        .ok_or("Failed to create image buffer")?;

    let mut buf = std::io::Cursor::new(Vec::new());
    img.write_to(&mut buf, image::ImageFormat::Png)
        .map_err(|e| format!("PNG encode error: {}", e))?;

    Ok(buf.into_inner())
}

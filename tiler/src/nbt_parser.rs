use byteorder::{BigEndian, ReadBytesExt};
use flate2::read::{GzDecoder, ZlibDecoder};
use std::collections::HashMap;
use std::io::{Cursor, Read};
use std::path::Path;

/// Single block entry with position and block name.
#[derive(Debug, Clone)]
pub struct BlockEntry {
    pub local_x: u8,
    pub local_z: u8,
    pub y: i16,
    pub block_name: String,
}

/// Single biome assignment at a column position.
#[derive(Debug, Clone)]
pub struct BiomeEntry {
    pub local_x: u8,
    pub local_z: u8,
    pub biome_name: String,
}

/// Raw parsed chunk data: block entries, biome entries, version.
#[derive(Debug, Clone)]
pub struct ChunkRawData {
    pub chunk_x: i32,
    pub chunk_z: i32,
    pub blocks: Vec<BlockEntry>,
    pub biomes: Vec<BiomeEntry>,
    pub data_version: i32,
    pub incomplete: bool,
}

/// Errors during chunk parsing — IO, NBT format, or missing data.
#[derive(Debug)]
pub enum ParserError {
    /// IO error reading file.
    Io(String),
    /// NBT decode error.
    Nbt(String),
    /// Chunk data invalid or not found.
    InvalidChunk(String),
    /// Chunk has no section data.
    MissingSection,
}

impl std::fmt::Display for ParserError {
    /// Human-readable error description.
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ParserError::Io(s) => write!(f, "IO error: {}", s),
            ParserError::Nbt(s) => write!(f, "NBT error: {}", s),
            ParserError::InvalidChunk(s) => write!(f, "Invalid chunk: {}", s),
            ParserError::MissingSection => write!(f, "Missing section data"),
        }
    }
}

impl std::error::Error for ParserError {}

// NBT tag types
const TAG_BYTE: u8 = 1;
const TAG_SHORT: u8 = 2;
const TAG_INT: u8 = 3;
const TAG_LONG: u8 = 4;
const TAG_FLOAT: u8 = 5;
const TAG_DOUBLE: u8 = 6;
const TAG_BYTE_ARRAY: u8 = 7;
const TAG_STRING: u8 = 8;
const TAG_LIST: u8 = 9;
const TAG_COMPOUND: u8 = 10;
const TAG_INT_ARRAY: u8 = 11;
const TAG_LONG_ARRAY: u8 = 12;
const TAG_END: u8 = 0;

struct NbtReader<'a> {
    cursor: Cursor<&'a [u8]>,
}

impl<'a> NbtReader<'a> {
    fn new(data: &'a [u8]) -> Self {
        NbtReader { cursor: Cursor::new(data) }
    }

    fn read_byte(&mut self) -> Result<i8, ParserError> {
        self.cursor.read_i8().map_err(|e| ParserError::Nbt(e.to_string()))
    }

    fn read_ubyte(&mut self) -> Result<u8, ParserError> {
        self.cursor.read_u8().map_err(|e| ParserError::Nbt(e.to_string()))
    }

    fn read_short(&mut self) -> Result<i16, ParserError> {
        self.cursor.read_i16::<BigEndian>().map_err(|e| ParserError::Nbt(e.to_string()))
    }

    fn read_int(&mut self) -> Result<i32, ParserError> {
        self.cursor.read_i32::<BigEndian>().map_err(|e| ParserError::Nbt(e.to_string()))
    }

    fn read_long(&mut self) -> Result<i64, ParserError> {
        self.cursor.read_i64::<BigEndian>().map_err(|e| ParserError::Nbt(e.to_string()))
    }

    fn read_string(&mut self) -> Result<String, ParserError> {
        let len = self.read_short()? as u16 as usize;
        let mut buf = vec![0u8; len];
        self.cursor.read_exact(&mut buf).map_err(|e| ParserError::Nbt(e.to_string()))?;
        String::from_utf8(buf).map_err(|e| ParserError::Nbt(format!("UTF-8: {}", e)))
    }

    fn check_len(len: i32) -> Result<usize, ParserError> {
        if len < 0 {
            return Err(ParserError::Nbt(format!("Negative array length: {}", len)));
        }
        Ok(len as usize)
    }

    fn skip_payload(&mut self, tag_type: u8) -> Result<(), ParserError> {
        match tag_type {
            TAG_BYTE => { self.read_byte()?; }
            TAG_SHORT => { self.read_short()?; }
            TAG_INT => { self.read_int()?; }
            TAG_LONG => { self.read_long()?; }
            TAG_FLOAT => { self.cursor.read_f32::<BigEndian>().map_err(|e| ParserError::Nbt(e.to_string()))?; }
            TAG_DOUBLE => { self.cursor.read_f64::<BigEndian>().map_err(|e| ParserError::Nbt(e.to_string()))?; }
            TAG_BYTE_ARRAY => {
                let len = Self::check_len(self.read_int()?)?;
                let mut buf = vec![0u8; len];
                self.cursor.read_exact(&mut buf).map_err(|e| ParserError::Nbt(e.to_string()))?;
            }
            TAG_STRING => { self.read_string()?; }
            TAG_LIST => {
                let elem_type = self.read_byte()? as u8;
                let len = self.read_int()?;
                for _ in 0..len {
                    self.skip_payload(elem_type)?;
                }
            }
            TAG_COMPOUND => {
                loop {
                    let t = self.read_byte()? as u8;
                    if t == TAG_END { break; }
                    self.read_string()?;
                    self.skip_payload(t)?;
                }
            }
            TAG_INT_ARRAY => {
                let len = Self::check_len(self.read_int()?)?;
                let mut buf = vec![0u8; len * 4];
                self.cursor.read_exact(&mut buf).map_err(|e| ParserError::Nbt(e.to_string()))?;
            }
            TAG_LONG_ARRAY => {
                let len = Self::check_len(self.read_int()?)?;
                let mut buf = vec![0u8; len * 8];
                self.cursor.read_exact(&mut buf).map_err(|e| ParserError::Nbt(e.to_string()))?;
            }
            _ => return Err(ParserError::Nbt(format!("Unknown tag type: {}", tag_type))),
        }
        Ok(())
    }

    fn read_compound(&mut self) -> Result<HashMap<String, NbtValue>, ParserError> {
        let mut map = HashMap::new();
        loop {
            let tag_type = self.read_ubyte()?;
            if tag_type == TAG_END {
                break;
            }
            let name = self.read_string()?;
            let value = self.read_payload(tag_type)?;
            map.insert(name, value);
        }
        Ok(map)
    }

    fn read_payload(&mut self, tag_type: u8) -> Result<NbtValue, ParserError> {
        match tag_type {
            TAG_BYTE => Ok(NbtValue::Byte(self.read_byte()?)),
            TAG_SHORT => Ok(NbtValue::Short(self.read_short()?)),
            TAG_INT => Ok(NbtValue::Int(self.read_int()?)),
            TAG_LONG => Ok(NbtValue::Long(self.read_long()?)),
            TAG_FLOAT => {
                let v = self.cursor.read_f32::<BigEndian>().map_err(|e| ParserError::Nbt(e.to_string()))?;
                Ok(NbtValue::Float(v))
            }
            TAG_DOUBLE => {
                let v = self.cursor.read_f64::<BigEndian>().map_err(|e| ParserError::Nbt(e.to_string()))?;
                Ok(NbtValue::Double(v))
            }
            TAG_BYTE_ARRAY => {
                let len = Self::check_len(self.read_int()?)?;
                let mut buf = vec![0u8; len];
                self.cursor.read_exact(&mut buf).map_err(|e| ParserError::Nbt(e.to_string()))?;
                Ok(NbtValue::ByteArray(buf))
            }
            TAG_STRING => Ok(NbtValue::String(self.read_string()?)),
            TAG_LIST => {
                let elem_type = self.read_ubyte()?;
                let len = self.read_int()?;
                if len < 0 {
                    return Err(ParserError::Nbt(format!("Negative list length: {}", len)));
                }
                let mut items = Vec::with_capacity(len as usize);
                for _ in 0..len {
                    items.push(self.read_payload(elem_type)?);
                }
                Ok(NbtValue::List(items))
            }
            TAG_COMPOUND => Ok(NbtValue::Compound(self.read_compound()?)),
            TAG_INT_ARRAY => {
                let len = Self::check_len(self.read_int()?)?;
                let mut buf = vec![0u8; len * 4];
                self.cursor.read_exact(&mut buf).map_err(|e| ParserError::Nbt(e.to_string()))?;
                let mut ints = Vec::with_capacity(len);
                let mut c = Cursor::new(&buf);
                for _ in 0..len {
                    ints.push(c.read_i32::<BigEndian>().map_err(|e| ParserError::Nbt(e.to_string()))?);
                }
                Ok(NbtValue::IntArray(ints))
            }
            TAG_LONG_ARRAY => {
                let len = Self::check_len(self.read_int()?)?;
                let mut buf = vec![0u8; len * 8];
                self.cursor.read_exact(&mut buf).map_err(|e| ParserError::Nbt(e.to_string()))?;
                let mut longs = Vec::with_capacity(len);
                let mut c = Cursor::new(&buf);
                for _ in 0..len {
                    longs.push(c.read_i64::<BigEndian>().map_err(|e| ParserError::Nbt(e.to_string()))?);
                }
                Ok(NbtValue::LongArray(longs))
            }
            _ => Err(ParserError::Nbt(format!("Unknown type: {}", tag_type))),
        }
    }

    fn read_root(&mut self) -> Result<HashMap<String, NbtValue>, ParserError> {
        let tag_type = self.read_ubyte()?;
        if tag_type != TAG_COMPOUND {
            return Err(ParserError::Nbt("Root must be compound".into()));
        }
        let _name = self.read_string()?;
        self.read_compound()
    }
}

/// Typed NBT tag value.
///
/// Mirrors Minecraft's named binary tag types.
#[derive(Debug, Clone)]
pub enum NbtValue {
    Byte(i8),
    Short(i16),
    Int(i32),
    Long(i64),
    Float(f32),
    Double(f64),
    ByteArray(Vec<u8>),
    String(String),
    List(Vec<NbtValue>),
    Compound(HashMap<String, NbtValue>),
    IntArray(Vec<i32>),
    LongArray(Vec<i64>),
}

impl NbtValue {
    fn as_str(&self) -> Option<&str> {
        match self {
            NbtValue::String(s) => Some(s.as_str()),
            _ => None,
        }
    }

    fn as_int(&self) -> Option<i32> {
        match self {
            NbtValue::Int(i) => Some(*i),
            _ => None,
        }
    }

    fn as_byte(&self) -> Option<i8> {
        match self {
            NbtValue::Byte(b) => Some(*b),
            _ => None,
        }
    }

    fn as_long_array(&self) -> Option<&[i64]> {
        match self {
            NbtValue::LongArray(v) => Some(v.as_slice()),
            _ => None,
        }
    }

    fn as_compound(&self) -> Option<&HashMap<String, NbtValue>> {
        match self {
            NbtValue::Compound(m) => Some(m),
            _ => None,
        }
    }

    fn as_list(&self) -> Option<&[NbtValue]> {
        match self {
            NbtValue::List(v) => Some(v.as_slice()),
            _ => None,
        }
    }
}

/// Read a single chunk from a region file by its chunk coordinates.
/// Much faster than reading all 1024 chunks when you only need one.
pub fn read_chunk(path: &Path, chunk_x: i32, chunk_z: i32) -> Result<ChunkRawData, ParserError> {
    let data = std::fs::read(path).map_err(|e| ParserError::Io(e.to_string()))?;
    if data.len() < 8192 {
        return Err(ParserError::InvalidChunk("File too small".into()));
    }

    let region_name = path.file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("r.0.0")
        .to_string();
    let parts: Vec<&str> = region_name.split('.').collect();
    let _region_x: i32 = parts.get(1).and_then(|s| s.parse().ok()).unwrap_or(0);
    let _region_z: i32 = parts.get(2).and_then(|s| s.parse().ok()).unwrap_or(0);

    // Local position within region (0..32)
    let local_x = ((chunk_x % 32 + 32) % 32) as usize;
    let local_z = ((chunk_z % 32 + 32) % 32) as usize;
    let index = local_z * 32 + local_x;

    let offset_start = index * 4;
    let offset_bytes = &data[offset_start..offset_start + 4];
    let sector_offset = ((offset_bytes[0] as u32) << 16)
        | ((offset_bytes[1] as u32) << 8)
        | (offset_bytes[2] as u32);
    let sector_count = offset_bytes[3] as u32;

    if sector_offset == 0 || sector_count == 0 {
        return Err(ParserError::InvalidChunk(
            format!("Chunk ({chunk_x}, {chunk_z}) not found in region")
        ));
    }

    let file_offset = (sector_offset as usize) * 4096;
    if file_offset + 4 >= data.len() {
        return Err(ParserError::InvalidChunk("Chunk offset past end of file".into()));
    }

    let chunk_len = {
        let mut c = Cursor::new(&data[file_offset..file_offset + 4]);
        c.read_u32::<BigEndian>().map_err(|e| ParserError::Nbt(e.to_string()))? as usize
    };

    if file_offset + 5 + chunk_len > data.len() {
        return Err(ParserError::InvalidChunk("Chunk data truncated".into()));
    }

    let compression = data[file_offset + 4];
    let nbt_data = &data[file_offset + 5..file_offset + 5 + chunk_len];

    let decompressed = match compression {
        1 => {
            let mut d = GzDecoder::new(nbt_data);
            let mut buf = Vec::new();
            d.read_to_end(&mut buf).map_err(|e| ParserError::Nbt(e.to_string()))?;
            buf
        }
        2 => {
            let mut d = ZlibDecoder::new(nbt_data);
            let mut buf = Vec::new();
            d.read_to_end(&mut buf).map_err(|e| ParserError::Nbt(e.to_string()))?;
            buf
        }
        3 => nbt_data.to_vec(),
        _ => return Err(ParserError::InvalidChunk("Unknown compression".into())),
    };

    parse_chunk_nbt(&decompressed, chunk_x, chunk_z)
}

/// Read all chunks from a region (`.mca`) file.
///
/// Iterates 1024 chunk slots, decompresses and parses each found chunk.
pub fn read_region_file(path: &Path) -> Result<Vec<ChunkRawData>, ParserError> {
    let data = std::fs::read(path).map_err(|e| ParserError::Io(e.to_string()))?;
    if data.len() < 8192 {
        return Err(ParserError::InvalidChunk("File too small".into()));
    }

    let region_name = path.file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("r.0.0")
        .to_string();
    let parts: Vec<&str> = region_name.split('.').collect();
    let region_x: i32 = parts.get(1).and_then(|s| s.parse().ok()).unwrap_or(0);
    let region_z: i32 = parts.get(2).and_then(|s| s.parse().ok()).unwrap_or(0);

    let mut chunks = Vec::new();

    for i in 0..1024 {
        let offset_start = i * 4;
        let offset_bytes = &data[offset_start..offset_start + 4];
        let sector_offset = ((offset_bytes[0] as u32) << 16)
            | ((offset_bytes[1] as u32) << 8)
            | (offset_bytes[2] as u32);
        let sector_count = offset_bytes[3] as u32;

        if sector_offset == 0 || sector_count == 0 {
            continue;
        }

        let file_offset = (sector_offset as usize) * 4096;
        if file_offset + 4 >= data.len() {
            continue;
        }

        let chunk_len = match Cursor::new(&data[file_offset..file_offset + 4]).read_u32::<BigEndian>() {
            Ok(len) => len as usize,
            Err(_) => continue,
        };

        if file_offset + 5 + chunk_len > data.len() {
            continue;
        }

        let compression = data[file_offset + 4];
        let nbt_data = &data[file_offset + 5..file_offset + 5 + chunk_len];

        let decompressed = match compression {
            1 => {
                let mut d = GzDecoder::new(nbt_data);
                let mut buf = Vec::new();
                d.read_to_end(&mut buf).map_err(|e| ParserError::Nbt(e.to_string()))?;
                buf
            }
            2 => {
                let mut d = ZlibDecoder::new(nbt_data);
                let mut buf = Vec::new();
                d.read_to_end(&mut buf).map_err(|e| ParserError::Nbt(e.to_string()))?;
                buf
            }
            3 => nbt_data.to_vec(),
            _ => continue,
        };

        let chunk_x = (i as i32 & 31) + region_x * 32;
        let chunk_z = (i as i32 >> 5) + region_z * 32;

        match parse_chunk_nbt(&decompressed, chunk_x, chunk_z) {
            Ok(chunk) => chunks.push(chunk),
            Err(_) => continue,
        }
    }

    Ok(chunks)
}

/// Parse decompressed NBT data into `ChunkRawData`.
///
/// Extracts blocks, biomes, and data version from section list.
fn parse_chunk_nbt(data: &[u8], chunk_x: i32, chunk_z: i32) -> Result<ChunkRawData, ParserError> {
    let mut reader = NbtReader::new(data);
    let root = reader.read_root()?;

    let data_version = root.get("DataVersion")
        .and_then(|v| v.as_int())
        .unwrap_or(0);

    let sections = root.get("sections")
        .and_then(|v| v.as_list())
        .ok_or(ParserError::MissingSection)?;

    let mut blocks = Vec::new();
    let mut biomes = Vec::new();

    for section in sections {
        let sec = section.as_compound().ok_or(ParserError::MissingSection)?;
        let section_y = sec.get("Y")
            .and_then(|v| v.as_byte())
            .unwrap_or(0) as i16;

        // Parse block_states
        if let Some(bs) = sec.get("block_states").and_then(|v| v.as_compound()) {
            let palette = bs.get("palette")
                .and_then(|v| v.as_list())
                .map(|l| {
                    l.iter().filter_map(|p| {
                        p.as_compound()
                            .and_then(|c| c.get("Name"))
                            .and_then(|n| n.as_str())
                            .map(|s| s.to_string())
                    }).collect::<Vec<_>>()
                })
                .unwrap_or_default();

            if let Some(data_arr) = bs.get("data").and_then(|v| v.as_long_array()) {
                let bits_per_block = if palette.len() <= 16 { 4 }
                    else if palette.len() <= 32 { 5 }
                    else if palette.len() <= 64 { 6 }
                    else if palette.len() <= 128 { 7 }
                    else if palette.len() <= 256 { 8 }
                    else { (palette.len() as f64 - 1.0).log2().ceil() as u8 };

                let blocks_per_long = (64 / bits_per_block) as usize;
                let mask = (1u64 << bits_per_block) - 1;

                let mut block_index = 0i32;
                for y in (section_y * 16)..(section_y * 16 + 16) {
                    for z in 0..16 {
                        for x in 0..16 {
                            let long_index = block_index as usize / blocks_per_long;
                            let bit_offset = (block_index as usize % blocks_per_long) * (bits_per_block as usize);
                            if long_index < data_arr.len() {
                                let long_val = data_arr[long_index] as u64;
                                let pal_idx = ((long_val >> bit_offset) & mask) as usize;
                                if pal_idx < palette.len() {
                                    let block_name = &palette[pal_idx];
                                    if block_name != "minecraft:air" {
                                        blocks.push(BlockEntry {
                                            local_x: x,
                                            local_z: z,
                                            y,
                                            block_name: block_name.clone(),
                                        });
                                    }
                                }
                            }
                            block_index += 1;
                        }
                    }
                }
            } else if palette.len() == 1 {
                // Single block type (all same)
                let block_name = palette[0].clone();
                if block_name != "minecraft:air" {
                    for y in (section_y * 16)..(section_y * 16 + 16) {
                        for z in 0..16 {
                            for x in 0..16 {
                                blocks.push(BlockEntry {
                                    local_x: x,
                                    local_z: z,
                                    y,
                                    block_name: block_name.clone(),
                                });
                            }
                        }
                    }
                }
            }
        }

        // Parse biomes
            if let Some(b) = sec.get("biomes").and_then(|v| v.as_compound()) {
                let biome_palette = b.get("palette")
                    .and_then(|v| v.as_list())
                    .map(|l| {
                        l.iter().filter_map(|p| {
                            match p {
                                NbtValue::Compound(c) => c.get("Name")
                                    .and_then(|n| n.as_str())
                                    .map(|s| s.to_string()),
                                NbtValue::String(s) => Some(s.clone()),
                                _ => None,
                            }
                        }).collect::<Vec<_>>()
                    })
                    .unwrap_or_default();

            if let Some(data_arr) = b.get("data").and_then(|v| v.as_long_array()) {
                // 4x4x4 biomes per section, stored in a 4x4x4 grid = 64 entries
                let bits_per_biome = if biome_palette.len() <= 1 { 1 }
                    else { (biome_palette.len() as f64 - 1.0).log2().ceil() as u8 };
                let biomes_per_long = if bits_per_biome > 0 { 64 / bits_per_biome as usize } else { 64 };
                let mask = if bits_per_biome > 0 { (1u64 << bits_per_biome) - 1 } else { 0 };

                if bits_per_biome > 0 && !data_arr.is_empty() {
                    for biome_local_y in 0..4 {
                        for biome_local_z in 0..4 {
                            for biome_local_x in 0..4 {
                                let biome_index = (biome_local_y * 16) + (biome_local_z * 4) + biome_local_x;
                                let long_idx = biome_index as usize / biomes_per_long;
                                let bit_off = (biome_index as usize % biomes_per_long) * bits_per_biome as usize;

                                if long_idx < data_arr.len() {
                                    let long_val = data_arr[long_idx] as u64;
                                    let pal_idx = ((long_val >> bit_off) & mask) as usize;
                                    if pal_idx < biome_palette.len() {
                                        let biome_name = &biome_palette[pal_idx];

                                        // Map biome 4x4x4 to actual block positions
                                        for _dy in 0..4 {
                                            for dz in 0..4 {
                                                for dx in 0..4 {
                                                    biomes.push(BiomeEntry {
                                                        local_x: biome_local_x * 4 + dx as u8,
                                                        local_z: biome_local_z * 4 + dz as u8,
                                                        biome_name: biome_name.clone(),
                                                    });
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                } else {
                    // Single biome
                    if let Some(name) = biome_palette.first() {
                        for _biome_local_y in 0..4 {
                            for biome_local_z in 0..4 {
                                for biome_local_x in 0..4 {
                                    for _dy in 0..4 {
                                        for dz in 0..4 {
                                            for dx in 0..4 {
                                                biomes.push(BiomeEntry {
                                                    local_x: biome_local_x * 4 + dx as u8,
                                                    local_z: biome_local_z * 4 + dz as u8,
                                                    biome_name: name.clone(),
                                                });
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            } else if biome_palette.len() == 1 {
                let name = biome_palette[0].clone();
                for _biome_local_y in 0..4 {
                    for biome_local_z in 0..4 {
                        for biome_local_x in 0..4 {
                            for _dy in 0..4 {
                                for dz in 0..4 {
                                    for dx in 0..4 {
                                        biomes.push(BiomeEntry {
                                            local_x: biome_local_x * 4 + dx as u8,
                                            local_z: biome_local_z * 4 + dz as u8,
                                            biome_name: name.clone(),
                                        });
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    if blocks.is_empty() {
        return Err(ParserError::InvalidChunk("Empty chunk".into()));
    }

    Ok(ChunkRawData {
        chunk_x,
        chunk_z,
        blocks,
        biomes,
        data_version,
        incomplete: false,
    })
}

#[allow(dead_code)]
fn get_block_at(chunk: &ChunkRawData, x: u8, z: u8, y: i16) -> Option<&BlockEntry> {
    chunk.blocks.iter().find(|b| b.local_x == x && b.local_z == z && b.y == y)
}

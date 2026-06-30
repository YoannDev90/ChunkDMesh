use crate::nbt_parser::ChunkRawData;
use crate::terrain::TerrainData;

#[derive(Debug, Clone)]
pub struct RiverSegment {
    pub points: Vec<(u8, u8)>,
    pub length: usize,
}

#[derive(Debug, Clone, Copy)]
pub struct Waterfall {
    pub local_x: u8,
    pub local_z: u8,
    pub height_drop: f32,
}

#[derive(Debug, Clone)]
pub struct WaterflowData {
    pub rivers: Vec<RiverSegment>,
    pub waterfalls: Vec<Waterfall>,
    pub water_map: [[bool; 16]; 16],
}

pub fn find_water(chunk: &ChunkRawData) -> WaterflowData {
    let mut water_map = [[false; 16]; 16];
    let mut water_heights: [[f32; 16]; 16] = [[-100.0; 16]; 16];

    for block in &chunk.blocks {
        if block.block_name == "minecraft:water" || block.block_name == "minecraft:flowing_water" {
            let x = block.local_x as usize;
            let z = block.local_z as usize;
            if block.y as f32 > water_heights[x][z] {
                water_heights[x][z] = block.y as f32;
                water_map[x][z] = true;
            }
        }
    }

    let rivers = find_river_segments(&water_map, 4);
    let waterfalls = find_waterfalls_internal(&water_map, &water_heights, 5.0);

    WaterflowData {
        rivers,
        waterfalls,
        water_map,
    }
}

fn find_river_segments(
    water_map: &[[bool; 16]; 16],
    min_length: usize,
) -> Vec<RiverSegment> {
    let mut visited = [[false; 16]; 16];
    let mut rivers = Vec::new();

    for x in 0..16 {
        for z in 0..16 {
            if water_map[x][z] && !visited[x][z] {
                let segment = flood_fill(water_map, &mut visited, x, z);
                if segment.len() >= min_length {
                    rivers.push(RiverSegment {
                        length: segment.len(),
                        points: segment,
                    });
                }
            }
        }
    }

    rivers
}

fn flood_fill(
    water_map: &[[bool; 16]; 16],
    visited: &mut [[bool; 16]; 16],
    start_x: usize,
    start_z: usize,
) -> Vec<(u8, u8)> {
    let mut points = Vec::new();
    let mut stack = vec![(start_x, start_z)];
    let dirs = [(0, 1), (0, -1), (1, 0), (-1, 0)];

    while let Some((x, z)) = stack.pop() {
        if visited[x][z] {
            continue;
        }
        visited[x][z] = true;
        points.push((x as u8, z as u8));

        for (dx, dz) in &dirs {
            let nx = x as isize + dx;
            let nz = z as isize + dz;
            if nx >= 0 && nx < 16 && nz >= 0 && nz < 16 {
                let nx = nx as usize;
                let nz = nz as usize;
                if water_map[nx][nz] && !visited[nx][nz] {
                    stack.push((nx, nz));
                }
            }
        }
    }

    points
}

fn find_waterfalls_internal(
    water_map: &[[bool; 16]; 16],
    water_heights: &[[f32; 16]; 16],
    min_drop: f32,
) -> Vec<Waterfall> {
    let mut waterfalls = Vec::new();

    for x in 0..16 {
        for z in 0..16 {
            if !water_map[x][z] {
                continue;
            }

            let this_h = water_heights[x][z];
            let dirs: &[(isize, isize)] = &[(0, 1), (0, -1), (1, 0), (-1, 0)];
            for (dx, dz) in dirs {
                let nx = x as isize + dx;
                let nz = z as isize + dz;
                if nx >= 0 && nx < 16 && nz >= 0 && nz < 16 {
                    let nx = nx as usize;
                    let nz = nz as usize;
                    if water_map[nx][nz] {
                        let drop = this_h - water_heights[nx][nz];
                        if drop > min_drop {
                            waterfalls.push(Waterfall {
                                local_x: x as u8,
                                local_z: z as u8,
                                height_drop: drop,
                            });
                        }
                    }
                }
            }
        }
    }

    waterfalls
}

pub fn find_waterfalls(
    chunk: &ChunkRawData,
    _terrain: &TerrainData,
    min_drop: f32,
) -> Vec<Waterfall> {
    let mut water_heights: [[f32; 16]; 16] = [[-100.0; 16]; 16];
    let mut water_map = [[false; 16]; 16];

    for block in &chunk.blocks {
        if block.block_name == "minecraft:water" || block.block_name == "minecraft:flowing_water" {
            let x = block.local_x as usize;
            let z = block.local_z as usize;
            if block.y as f32 > water_heights[x][z] {
                water_heights[x][z] = block.y as f32;
                water_map[x][z] = true;
            }
        }
    }

    find_waterfalls_internal(&water_map, &water_heights, min_drop)
}

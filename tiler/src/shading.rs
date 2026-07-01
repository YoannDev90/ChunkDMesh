use crate::colors::Rgb;

/// Shading parameters for terrain lighting.
///
/// Controls light direction, height exaggeration for normals,
/// shadow strength, and cave darkness factor.
#[derive(Debug, Clone, serde::Deserialize)]
#[serde(default)]
pub struct ShadingConfig {
    pub light_direction: (f32, f32, f32),
    pub height_exaggeration: f32,
    pub shadow_strength: f32,
    pub cave_darkness: f32,
}

impl Default for ShadingConfig {
    /// Default shading: NW light, 2x height exaggeration, 70% shadow strength, 60% cave darkness.
    fn default() -> Self {
        ShadingConfig {
            light_direction: (-0.5, 0.7, 0.5),
            height_exaggeration: 2.0,
            shadow_strength: 0.7,
            cave_darkness: 0.6,
        }
    }
}

/// Edge heights from neighboring chunks, used to compute seamless normals at chunk borders.
pub struct EdgeHeights {
    /// Left neighbor's right edge: heights[15][z] of chunk at (cx-1, cz)
    pub left: Option<[f32; 16]>,
    /// Right neighbor's left edge: heights[0][z] of chunk at (cx+1, cz)
    pub right: Option<[f32; 16]>,
    /// Top neighbor's bottom edge: heights[x][15] of chunk at (cx, cz-1)
    pub top: Option<[f32; 16]>,
    /// Bottom neighbor's top edge: heights[x][0] of chunk at (cx, cz+1)
    pub bottom: Option<[f32; 16]>,
}

fn normalize(x: f32, y: f32, z: f32) -> (f32, f32, f32) {
    let len = (x * x + y * y + z * z).sqrt();
    if len == 0.0 { (0.0, 1.0, 0.0) } else { (x / len, y / len, z / len) }
}

fn dot(a: (f32, f32, f32), b: (f32, f32, f32)) -> f32 {
    a.0 * b.0 + a.1 * b.1 + a.2 * b.2
}

/// Compute height at a position, using edge data for out-of-bounds access.
fn height_at(
    heights: &[[f32; 16]; 16],
    edge: &EdgeHeights,
    x: isize,
    z: isize,
) -> f32 {
    if x >= 0 && x < 16 && z >= 0 && z < 16 {
        return heights[x as usize][z as usize];
    }
    // Left border (x = -1)
    if x == -1 {
        if let Some(ref left) = edge.left {
            return left[z as usize];
        }
        return heights[0][z as usize];
    }
    // Right border (x = 16)
    if x == 16 {
        if let Some(ref right) = edge.right {
            return right[z as usize];
        }
        return heights[15][z as usize];
    }
    // Top border (z = -1)
    if z == -1 {
        if let Some(ref top) = edge.top {
            return top[x as usize];
        }
        return heights[x as usize][0];
    }
    // Bottom border (z = 16)
    if z == 16 {
        if let Some(ref bottom) = edge.bottom {
            return bottom[x as usize];
        }
        return heights[x as usize][15];
    }
    heights[x.max(0).min(15) as usize][z.max(0).min(15) as usize]
}

/// Compute surface normals from height grid.
///
/// Uses central differences with optional neighbor edge data
/// for seamless chunk borders.
pub fn compute_normals(
    heights: &[[f32; 16]; 16],
    exaggeration: f32,
    edge: Option<&EdgeHeights>,
) -> [[(f32, f32, f32); 16]; 16] {
    let mut normals = [[(0.0f32, 0.0f32, 1.0f32); 16]; 16];

    // Default edge: no neighbor data, clamp to self
    let default_edge = EdgeHeights { left: None, right: None, top: None, bottom: None };
    let e = edge.unwrap_or(&default_edge);

    for x in 0..16isize {
        for z in 0..16isize {
            let x_left  = height_at(heights, e, x - 1, z);
            let x_right = height_at(heights, e, x + 1, z);
            let z_up    = height_at(heights, e, x, z - 1);
            let z_down  = height_at(heights, e, x, z + 1);

            let gx = (x_right - x_left) * 0.5 * exaggeration;
            let gz = (z_down - z_up) * 0.5 * exaggeration;

            normals[x as usize][z as usize] = normalize(-gx, 1.0, -gz);
        }
    }

    normals
}

/// Apply diffuse lighting and cave-darkening to color grid.
///
/// Uses dot product between surface normals and light direction.
/// Cave columns get additional darkness.
pub fn apply_shading(
    colors: &[[Rgb; 16]; 16],
    normals: &[[(f32, f32, f32); 16]; 16],
    has_caves: &[[bool; 16]; 16],
    config: &ShadingConfig,
) -> [[Rgb; 16]; 16] {
    let light = normalize(
        config.light_direction.0,
        config.light_direction.1,
        config.light_direction.2,
    );

    let mut result = [[Rgb::new(0, 0, 0); 16]; 16];

    for x in 0..16 {
        for z in 0..16 {
            let ndot = dot(normals[x][z], light);
            let brightness = 0.4 + 0.6 * (ndot * 0.5 + 0.5);

            let mut color = colors[x][z].scale(brightness);

            if has_caves[x][z] {
                let cave_shade = 1.0 - config.cave_darkness * 0.5;
                color = color.scale(cave_shade);
            }

            result[x][z] = color;
        }
    }

    result
}

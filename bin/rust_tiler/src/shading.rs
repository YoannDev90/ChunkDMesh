use crate::colors::Rgb;

#[derive(Debug, Clone)]
pub struct ShadingConfig {
    pub light_direction: (f32, f32, f32),
    pub height_exaggeration: f32,
    pub shadow_strength: f32,
    pub cave_darkness: f32,
}

impl Default for ShadingConfig {
    fn default() -> Self {
        ShadingConfig {
            light_direction: (-0.5, 0.7, 0.5),
            height_exaggeration: 2.0,
            shadow_strength: 0.7,
            cave_darkness: 0.6,
        }
    }
}

fn normalize(x: f32, y: f32, z: f32) -> (f32, f32, f32) {
    let len = (x * x + y * y + z * z).sqrt();
    if len == 0.0 { (0.0, 1.0, 0.0) } else { (x / len, y / len, z / len) }
}

fn dot(a: (f32, f32, f32), b: (f32, f32, f32)) -> f32 {
    a.0 * b.0 + a.1 * b.1 + a.2 * b.2
}

pub fn compute_normals(
    heights: &[[f32; 16]; 16],
    exaggeration: f32,
) -> [[(f32, f32, f32); 16]; 16] {
    let mut normals = [[(0.0f32, 0.0f32, 1.0f32); 16]; 16];

    for x in 0..16 {
        for z in 0..16 {
            let x_left = if x > 0 { heights[x - 1][z] } else { heights[x][z] };
            let x_right = if x < 15 { heights[x + 1][z] } else { heights[x][z] };
            let z_up = if z > 0 { heights[x][z - 1] } else { heights[x][z] };
            let z_down = if z < 15 { heights[x][z + 1] } else { heights[x][z] };

            let gx = (x_right - x_left) * 0.5 * exaggeration;
            let gz = (z_down - z_up) * 0.5 * exaggeration;

            normals[x][z] = normalize(-gx, 1.0, -gz);
        }
    }

    normals
}

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

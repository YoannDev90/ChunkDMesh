use std::collections::HashMap;

fn color_table() -> HashMap<&'static str, [u8; 3]> {
    let mut m = HashMap::new();
    m.insert("minecraft:grass_block", [127, 170, 49]);
    m.insert("minecraft:dirt", [124, 89, 50]);
    m.insert("minecraft:coarse_dirt", [89, 63, 33]);
    m.insert("minecraft:rooted_dirt", [89, 63, 33]);
    m.insert("minecraft:podzol", [100, 75, 40]);
    m.insert("minecraft:mycelium", [123, 95, 113]);
    m.insert("minecraft:stone", [128, 128, 128]);
    m.insert("minecraft:andesite", [136, 136, 130]);
    m.insert("minecraft:diorite", [186, 184, 175]);
    m.insert("minecraft:granite", [158, 117, 95]);
    m.insert("minecraft:deepslate", [50, 50, 55]);
    m.insert("minecraft:tuff", [103, 98, 94]);
    m.insert("minecraft:bedrock", [30, 30, 30]);
    m.insert("minecraft:sand", [226, 213, 149]);
    m.insert("minecraft:red_sand", [181, 120, 45]);
    m.insert("minecraft:sandstone", [212, 197, 138]);
    m.insert("minecraft:red_sandstone", [158, 106, 48]);
    m.insert("minecraft:gravel", [128, 124, 121]);
    m.insert("minecraft:water", [59, 136, 195]);
    m.insert("minecraft:lava", [223, 88, 20]);
    m.insert("minecraft:oak_log", [90, 70, 30]);
    m.insert("minecraft:birch_log", [190, 178, 120]);
    m.insert("minecraft:spruce_log", [60, 42, 18]);
    m.insert("minecraft:jungle_log", [100, 83, 47]);
    m.insert("minecraft:acacia_log", [118, 85, 52]);
    m.insert("minecraft:dark_oak_log", [45, 30, 15]);
    m.insert("minecraft:mangrove_log", [75, 46, 34]);
    m.insert("minecraft:cherry_log", [80, 50, 50]);
    m.insert("minecraft:oak_leaves", [71, 117, 33]);
    m.insert("minecraft:birch_leaves", [95, 135, 55]);
    m.insert("minecraft:spruce_leaves", [40, 80, 25]);
    m.insert("minecraft:jungle_leaves", [55, 110, 30]);
    m.insert("minecraft:acacia_leaves", [75, 125, 40]);
    m.insert("minecraft:dark_oak_leaves", [40, 70, 25]);
    m.insert("minecraft:mangrove_leaves", [60, 100, 35]);
    m.insert("minecraft:cherry_leaves", [200, 140, 160]);
    m.insert("minecraft:azalea_leaves", [70, 115, 40]);
    m.insert("minecraft:flowering_azalea_leaves", [70, 115, 40]);
    m.insert("minecraft:grass", [127, 170, 49]);
    m.insert("minecraft:tall_grass", [127, 170, 49]);
    m.insert("minecraft:fern", [90, 130, 40]);
    m.insert("minecraft:large_fern", [90, 130, 40]);
    m.insert("minecraft:dead_bush", [100, 75, 40]);
    m.insert("minecraft:snow", [240, 245, 250]);
    m.insert("minecraft:snow_block", [234, 240, 245]);
    m.insert("minecraft:ice", [130, 170, 200]);
    m.insert("minecraft:packed_ice", [120, 155, 185]);
    m.insert("minecraft:blue_ice", [70, 110, 150]);
    m.insert("minecraft:powder_snow", [230, 235, 240]);
    m.insert("minecraft:cactus", [70, 130, 30]);
    m.insert("minecraft:sugar_cane", [85, 145, 40]);
    m.insert("minecraft:pumpkin", [195, 130, 35]);
    m.insert("minecraft:melon", [130, 160, 50]);
    m.insert("minecraft:brown_mushroom", [140, 100, 60]);
    m.insert("minecraft:red_mushroom", [185, 60, 50]);
    m.insert("minecraft:cobblestone", [125, 125, 125]);
    m.insert("minecraft:mossy_cobblestone", [110, 130, 100]);
    m.insert("minecraft:bricks", [155, 100, 70]);
    m.insert("minecraft:stone_bricks", [128, 128, 125]);
    m.insert("minecraft:prismarine", [90, 140, 130]);
    m.insert("minecraft:prismarine_bricks", [95, 150, 135]);
    m.insert("minecraft:dark_prismarine", [55, 90, 80]);
    m.insert("minecraft:sea_lantern", [180, 200, 210]);
    m.insert("minecraft:netherrack", [145, 45, 35]);
    m.insert("minecraft:nether_bricks", [55, 20, 15]);
    m.insert("minecraft:nether_quartz_ore", [130, 55, 45]);
    m.insert("minecraft:nether_gold_ore", [130, 60, 40]);
    m.insert("minecraft:soul_sand", [75, 55, 45]);
    m.insert("minecraft:soul_soil", [65, 45, 35]);
    m.insert("minecraft:basalt", [70, 70, 75]);
    m.insert("minecraft:blackstone", [45, 40, 45]);
    m.insert("minecraft:glowstone", [165, 145, 80]);
    m.insert("minecraft:shroomlight", [245, 130, 60]);
    m.insert("minecraft:crimson_nylium", [150, 50, 55]);
    m.insert("minecraft:warped_nylium", [50, 130, 100]);
    m.insert("minecraft:magma_block", [140, 70, 30]);
    m.insert("minecraft:warped_wart_block", [40, 115, 80]);
    m.insert("minecraft:nether_wart_block", [100, 25, 10]);
    m.insert("minecraft:end_stone", [215, 215, 170]);
    m.insert("minecraft:end_stone_bricks", [210, 210, 165]);
    m.insert("minecraft:purpur_block", [170, 115, 150]);
    m.insert("minecraft:obsidian", [25, 15, 40]);
    m.insert("minecraft:crying_obsidian", [35, 15, 50]);
    m.insert("minecraft:terracotta", [148, 103, 70]);
    m.insert("minecraft:white_terracotta", [148, 110, 85]);
    m.insert("minecraft:orange_terracotta", [145, 80, 45]);
    m.insert("minecraft:magenta_terracotta", [125, 70, 85]);
    m.insert("minecraft:light_blue_terracotta", [80, 85, 105]);
    m.insert("minecraft:yellow_terracotta", [150, 120, 50]);
    m.insert("minecraft:lime_terracotta", [95, 110, 55]);
    m.insert("minecraft:pink_terracotta", [145, 85, 85]);
    m.insert("minecraft:gray_terracotta", [65, 55, 55]);
    m.insert("minecraft:light_gray_terracotta", [120, 100, 85]);
    m.insert("minecraft:cyan_terracotta", [60, 85, 80]);
    m.insert("minecraft:purple_terracotta", [100, 65, 80]);
    m.insert("minecraft:blue_terracotta", [55, 55, 85]);
    m.insert("minecraft:brown_terracotta", [95, 60, 45]);
    m.insert("minecraft:green_terracotta", [65, 80, 50]);
    m.insert("minecraft:red_terracotta", [120, 55, 45]);
    m.insert("minecraft:black_terracotta", [40, 30, 30]);
    m.insert("minecraft:clay", [160, 155, 150]);
    m.insert("minecraft:white_wool", [225, 225, 225]);
    m.insert("minecraft:calcite", [220, 215, 205]);
    m.insert("minecraft:dripstone_block", [135, 115, 95]);
    m.insert("minecraft:amethyst_block", [120, 65, 165]);
    m.insert("minecraft:budding_amethyst", [120, 65, 165]);
    m.insert("minecraft:moss_block", [80, 140, 55]);
    m.insert("minecraft:spore_blossom", [150, 100, 145]);
    m.insert("minecraft:copper_ore", [130, 100, 65]);
    m.insert("minecraft:iron_ore", [140, 125, 110]);
    m.insert("minecraft:coal_ore", [70, 65, 60]);
    m.insert("minecraft:gold_ore", [130, 120, 50]);
    m.insert("minecraft:diamond_ore", [90, 190, 175]);
    m.insert("minecraft:emerald_ore", [55, 175, 60]);
    m.insert("minecraft:lapis_ore", [50, 80, 140]);
    m.insert("minecraft:redstone_ore", [145, 50, 50]);
    m.insert("minecraft:copper_block", [170, 115, 75]);
    m.insert("minecraft:iron_block", [200, 195, 190]);
    m.insert("minecraft:gold_block", [235, 200, 55]);
    m.insert("minecraft:diamond_block", [90, 220, 200]);
    m.insert("minecraft:emerald_block", [70, 205, 70]);
    m.insert("minecraft:lapis_block", [35, 55, 135]);
    m.insert("minecraft:redstone_block", [185, 25, 15]);
    m.insert("minecraft:bone_block", [215, 205, 175]);
    m.insert("minecraft:sea_pickle", [105, 155, 65]);
    m.insert("minecraft:sponge", [175, 180, 60]);
    m.insert("minecraft:wet_sponge", [140, 155, 60]);
    m.insert("minecraft:white_concrete", [210, 215, 215]);
    m.insert("minecraft:light_gray_concrete", [140, 140, 135]);
    m.insert("minecraft:gray_concrete", [60, 65, 65]);
    m.insert("minecraft:black_concrete", [30, 25, 25]);
    m.insert("minecraft:red_concrete", [125, 35, 30]);
    m.insert("minecraft:orange_concrete", [195, 90, 30]);
    m.insert("minecraft:yellow_concrete", [210, 175, 35]);
    m.insert("minecraft:lime_concrete", [90, 170, 40]);
    m.insert("minecraft:green_concrete", [50, 110, 35]);
    m.insert("minecraft:cyan_concrete", [25, 110, 115]);
    m.insert("minecraft:light_blue_concrete", [50, 120, 175]);
    m.insert("minecraft:blue_concrete", [35, 45, 140]);
    m.insert("minecraft:purple_concrete", [90, 35, 130]);
    m.insert("minecraft:magenta_concrete", [160, 50, 120]);
    m.insert("minecraft:pink_concrete", [190, 100, 120]);
    m.insert("minecraft:brown_concrete", [80, 50, 35]);
    m.insert("minecraft:white_stained_glass", [200, 200, 200]);
    m.insert("minecraft:oak_planks", [160, 130, 80]);
    m.insert("minecraft:spruce_planks", [100, 75, 45]);
    m.insert("minecraft:birch_planks", [195, 180, 130]);
    m.insert("minecraft:jungle_planks", [155, 115, 60]);
    m.insert("minecraft:acacia_planks", [155, 95, 50]);
    m.insert("minecraft:dark_oak_planks", [65, 45, 25]);
    m.insert("minecraft:mangrove_planks", [100, 75, 55]);
    m.insert("minecraft:cherry_planks", [190, 130, 135]);
    m.insert("minecraft:bamboo_planks", [190, 170, 85]);
    m.insert("minecraft:bamboo_block", [185, 170, 75]);
    m.insert("minecraft:bamboo", [145, 175, 65]);
    m.insert("minecraft:bamboo_sapling", [85, 130, 40]);
    m.shrink_to_fit();
    m
}

// Air blocks for fast lookup
pub fn is_air(name: &str) -> bool {
    name == "minecraft:air"
        || name == "minecraft:cave_air"
        || name == "minecraft:void_air"
}

pub fn block_color(name: &str) -> [u8; 3] {
    use std::sync::LazyLock;
    static COLORS: LazyLock<HashMap<&'static str, [u8; 3]>> =
        LazyLock::new(color_table);

    if let Some(&c) = COLORS.get(name) {
        return c;
    }
    material_hint(name).unwrap_or_else(|| hash_color(name))
}

fn hash_color(name: &str) -> [u8; 3] {
    use std::hash::{Hash, Hasher};
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    name.hash(&mut hasher);
    let h = hasher.finish();
    let r = ((h & 0xff) as u16 * 100 + 80) as u8;
    let g = (((h >> 8) & 0xff) as u16 * 100 + 80) as u8;
    let b = (((h >> 16) & 0xff) as u16 * 100 + 80) as u8;
    [r, g, b]
}

fn material_hint(name: &str) -> Option<[u8; 3]> {
    let n = if let Some(idx) = name.find(':') {
        &name[idx + 1..]
    } else {
        name
    };

    // Check color prefixes
    if let Some(c) = color_prefix(n) {
        return Some(c);
    }

    if contains_any(n, &["log", "wood", "plank", "sapling", "bamboo"]) {
        return Some([90, 70, 30]);
    }
    if contains_any(n, &["leaf", "leaves", "foliage"]) {
        return Some([71, 117, 33]);
    }
    if contains_any(n, &[
        "stone", "rock", "cobble", "brick", "deepslate", "tuff", "granite",
        "diorite", "andesite", "basalt", "blackstone",
    ]) {
        return Some([128, 128, 128]);
    }
    if contains_any(n, &["dirt", "soil", "mud", "podzol", "mycelium"]) {
        return Some([124, 89, 50]);
    }
    if n.contains("sand") {
        return Some([226, 213, 149]);
    }
    if contains_any(n, &["water", "river"]) {
        return Some([59, 136, 195]);
    }
    if contains_any(n, &["lava", "magma"]) {
        return Some([223, 88, 20]);
    }
    if contains_any(n, &["ore", "mineral"]) {
        return Some([130, 120, 50]);
    }
    if n.contains("glass") {
        return Some([200, 200, 200]);
    }
    if n.contains("wool") {
        return Some([200, 200, 200]);
    }
    if contains_any(n, &["concrete", "terracotta", "glazed"]) {
        return Some([148, 103, 70]);
    }
    if contains_any(n, &["nether", "crimson", "warped", "soul"]) {
        return Some([145, 45, 35]);
    }
    if contains_any(n, &["end_", "purpur", "chorus"]) {
        return Some([170, 115, 150]);
    }
    if contains_any(n, &["snow", "ice", "frost"]) {
        return Some([240, 245, 250]);
    }
    if contains_any(n, &[
        "flower", "plant", "mushroom", "fungus", "fungal", "vine", "root",
        "stem", "wart",
    ]) {
        return Some([127, 170, 49]);
    }
    if contains_any(n, &["bone", "skull", "skeleton"]) {
        return Some([215, 205, 175]);
    }
    if n.contains("bedrock") {
        return Some([30, 30, 30]);
    }
    if contains_any(n, &["sponge", "sea"]) {
        return Some([175, 180, 60]);
    }
    if contains_any(n, &["pumpkin", "melon", "gourd"]) {
        return Some([195, 130, 35]);
    }
    if n.contains("cactus") {
        return Some([70, 130, 30]);
    }
    if contains_any(n, &["coral", "prismarine"]) {
        return Some([90, 140, 130]);
    }
    if contains_any(n, &["lamp", "light", "lantern", "torch"]) {
        return Some([245, 220, 100]);
    }
    if contains_any(n, &["chain", "iron", "anvil", "cauldron", "hopper", "door", "trapdoor", "fence", "gate"]) {
        return Some([128, 128, 128]);
    }
    None
}

fn contains_any(s: &str, keywords: &[&str]) -> bool {
    keywords.iter().any(|kw| s.contains(kw))
}

fn color_prefix(name: &str) -> Option<[u8; 3]> {
    if name.starts_with("white_") {
        return Some([210, 215, 215]);
    }
    if name.starts_with("light_gray_") {
        return Some([140, 140, 135]);
    }
    if name.starts_with("gray_") {
        return Some([60, 65, 65]);
    }
    if name.starts_with("black_") {
        return Some([30, 25, 25]);
    }
    if name.starts_with("red_") {
        return Some([125, 35, 30]);
    }
    if name.starts_with("orange_") {
        return Some([195, 90, 30]);
    }
    if name.starts_with("yellow_") {
        return Some([210, 175, 35]);
    }
    if name.starts_with("lime_") {
        return Some([90, 170, 40]);
    }
    if name.starts_with("green_") {
        return Some([50, 110, 35]);
    }
    if name.starts_with("cyan_") {
        return Some([25, 110, 115]);
    }
    if name.starts_with("light_blue_") {
        return Some([50, 120, 175]);
    }
    if name.starts_with("blue_") {
        return Some([35, 45, 140]);
    }
    if name.starts_with("purple_") {
        return Some([90, 35, 130]);
    }
    if name.starts_with("magenta_") {
        return Some([160, 50, 120]);
    }
    if name.starts_with("pink_") {
        return Some([190, 100, 120]);
    }
    if name.starts_with("brown_") {
        return Some([80, 50, 35]);
    }
    None
}

# Chunky Mod Reference

> Source: https://github.com/pop4959/Chunky/wiki
> Last updated: 2026-06-26

## Overview

Chunky pre-generates chunks on the Minecraft server. It does NOT generate chunks itself — it delegates to the server's world generator. This means modded blocks/dimensions work automatically.

- License: GPL-3.0
- Platforms: Fabric, Forge, NeoForge, Paper, Spigot, Bukkit, Sponge, Folia
- Stars: 740 | Forks: 97

## Command Order (CRITICAL)

The order of commands matters. `chunky world` loads the saved config for that world, which **overwrites** any session settings set before it.

**Correct order:**
```
chunky world <world>        # 1. Load world config (resets center/radius/shape)
chunky dimension <dim>      # 2. Optional: set dimension
chunky center <x> <z>       # 3. Set center (BEFORE start)
chunky radius <r>           # 4. Set radius (BEFORE start)
chunky shape <shape>        # 5. Set shape (BEFORE start)
chunky pattern <pattern>    # 6. Optional: set pattern
chunky start                # 7. Start generation
```

**Wrong order** (center/radius get overwritten by `chunky world`):
```
chunky center 1280 256      # ← Gets overwritten!
chunky radius 256           # ← Gets overwritten!
chunky world world          # ← Loads saved config, resets everything
chunky start                # ← Uses wrong center/radius
```

## Task Management Commands

| Command | Description |
|---|---|
| `chunky start [world] [shape] [<cx> <cz>] [radius]` | Start generation. Default: square, center 0,0, radius 500 |
| `chunky pause [world]` | Pause and save progress |
| `chunky continue [world]` | Resume paused tasks |
| `chunky cancel [world]` | Stop and delete tasks (keeps already-generated chunks) |
| `chunky progress` | Show progress for all tasks |

## Selection Commands

| Command | Description |
|---|---|
| `chunky world [world]` | Set target world. Loads saved config. |
| `chunky shape <shape>` | Set shape: square, circle, triangle, diamond, pentagon, hexagon, star, rectangle, ellipse |
| `chunky center [<x> <z>]` | Set center block coordinates |
| `chunky radius <r> [r2]` | Set radius in blocks. Supports `k`/`c` suffixes (e.g., `10k`, `625c`). Two radii for rectangle/ellipse |
| `chunky spawn` | Set center to world spawn |
| `chunky worldborder [world]` | Set center/radius to match world border |
| `chunky corners <x1> <z1> <x2> <z2>` | Set center/radius from corner coordinates |
| `chunky pattern <pattern>` | Set generation pattern |
| `chunky selection` | Display current selection |

### Radius Suffixes

| Suffix | Meaning | Example |
|---|---|---|
| (none) | blocks | `chunky radius 500` |
| `c` | chunks | `chunky radius 625c` (= 10000 blocks) |
| `k` | kiloblocks | `chunky radius 10k` (= 10000 blocks) |
| `+` | expand current | `chunky radius +1k` |
| `-` | contract current | `chunky radius -1k` |

## Shapes

| Shape | Description |
|---|---|
| `square` | Default. Fills a square area |
| `circle` | Fills a circular area |
| `triangle` | Triangle shape |
| `diamond` | Diamond/rhombus shape |
| `pentagon` | Pentagon shape |
| `hexagon` | Hexagon shape |
| `star` | Star shape |
| `rectangle` | Requires two radii: `chunky radius 2000 1000` |
| `ellipse` | Requires two radii |

## Patterns

| Pattern | Description |
|---|---|
| `region` | **Default.** Generates regions using Hilbert space-filling curve. Most efficient |
| `concentric` | Generates chunks in concentric square rings from center outward |
| `loop` | Generates left-to-right, top-to-bottom |
| `spiral` | Square spiral from center. Similar to concentric |
| `csv` | Custom order from CSV file |
| `world` | Only loads existing chunks (for re-processing) |

## Configuration

File: `chunky/config.yml`

```yaml
version: 2
language: en
# Auto-continue tasks on server restart
continue-on-restart: false
# Force load existing chunks (for broken metadata)
force-load-existing-chunks: false
# Silence console update messages
silent: false
# Seconds between progress messages
update-interval: 1
```

## Progress Output Format

`chunky progress` returns text like:

```
Processing 128/1024 chunks (12.50%) | ETA: 00:01:30 | 10.5 cps | Chunk [16, 32] in world
```

When finished:
```
Finished 1024 chunks in 00:02:30
```

When idle:
```
Not running
```

Or:
```
No tasks running
```

**IMPORTANT for RCON**: The `chunky start` command returns a response, but it may just say "Started" without detailed progress. Use `chunky progress` to poll status.

## Task Files

Stored in `chunky/tasks/` folder. One file per world.

```properties
world=world
cancelled=false
center-x=1280.0
center-z=256.0
radius=256.0
shape=square
pattern=region
chunks=384
time=15000
```

**Each world may only have ONE task at any given time.** Starting a new task replaces the old one.

## RCON Protocol

Chunky supports RCON for all commands. The command format via RCON:

```
chunky <subcommand> [args...]
```

Examples:
- `chunky world world` → "Selected world world"
- `chunky center 1280 256` → "Center set to 1280, 256"
- `chunky radius 256` → "Radius set to 256"
- `chunky start` → "Started pre-generation task for world"
- `chunky progress` → Returns progress text or "Not running"
- `chunky cancel` → "Cancelled all tasks"

## Important Notes

1. **Don't pause the game while generating** — use `/gamerule doDaylightCycle false` instead
2. **Modded worldgen works** — Chunky delegates to the server, so all mods/datapacks are respected
3. **Each world = one task** — can't have multiple concurrent tasks for the same world
4. **Tasks auto-save on shutdown** — but not on crash
5. **Chunks are saved to standard .mca format** — no post-processing needed
6. **Only one `chunky start` per world** — calling it again cancels the previous task

## FAQ Highlights

- **Can pregenerate existing worlds?** Yes, safely. Skips existing chunks.
- **Continue after restart?** Only with `continue-on-restart: true`
- **Custom worldgen?** Works — Chunky delegates to server
- **No mobs after pregen?** Check world border / `max-world-size` setting
- **Buried treasure empty?** MC-218156 bug. Fix: set `treasure-maps.find-already-discovered.loot-tables: false` on Paper

## Known Issues with Our Usage

### Completion Detection

The `chunky progress` command may return:
- `"Not running"` between batch processing ticks (transient state)
- `"No tasks running"` before the task fully starts
- `"Finished"` or `"100%"` when truly done

**We must NOT break on "not running" or "no tasks" without first seeing actual progress.**

Better approach: parse the chunk count from progress output and compare to expected total.

### Center Overwrite

`chunky world <name>` loads the saved config and overwrites session settings. Always send `chunky world` FIRST, then center/radius/shape.

### Save Flow

Chunky writes chunks continuously. `save-all` forces a flush, but `save-off` prevents future writes. The sequence should be:

1. Wait for generation to complete (100% or "Finished")
2. `save-all` → wait for confirmation
3. Read/upload the .mca file
4. `save-on` to resume normal operation

Do NOT use `save-off` during generation — it prevents chunks from being written to disk.

# CHUNK-D-MESH

```text
 _____  _   _ _   _ _   _  _   __     ______       ___  ___ _____ _____ _   _ 
/  __ \| | | | | | | \ | || | / /     |  _  \      |  \/  ||  ___/  ___| | | |
| /  \/| |_| | | | |  \| || |/ /______| | | |______| .  . || |__ \ `--.| |_| |
| |    |  _  | | | | . ` ||    \______| | | |______| |\/| ||  __| `--. \  _  |
| \__/\| | | | |_| | |\  || |\  \     | |/ /       | |  | || |___/\__/ / | | |
 \____/\_| |_/\___/\_| \_/\_| \_/     |___/        \_|  |_/\____/\____/\_| |_/
```

A distributed platform for Minecraft world pre-generation. Chunks are generated in parallel by volunteer clients and assembled server-side.

## Requirements

- Python 3.10+
- See [`requirements.txt`](/requirements.txt) for dependencies

## Install

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

### Configure your world

Edit [`server/config/world_config.json5`](/server/config/world_config.json5) with your MC version, loader, seed, radius, etc.

### Launch server

```sh
python run.py server
```

Server starts at `http://localhost:8000`.

### Launch client (worker)

```sh
python run.py client
```

### Launch both (server + client)

```sh
python run.py both
```

### Dashboard

- Admin dashboard: `http://localhost:8000/admin`
- Interactive map: `http://localhost:8000/admin/map`
- API docs: `http://localhost:8000/docs`

## Architecture

```
┌──────────────┐     REST API      ┌──────────────────┐
│   Server     │◄──────────────────│    Client(s)     │
│ (Orchestrator)│                   │   (Workers)      │
│              │                   │                  │
│  - FastAPI   │   tasks/batch     │  - Java detector │
│  - SQLite    │──────────────────►│  - Asset manager │
│  - Tasker    │   upload/submit   │  - MC instance   │
│  - Assembler │◄──────────────────│  - RCON/Chunky   │
│  - Dashboard │                   │  - Uploader      │
└──────────────┘                   └──────────────────┘
```

### Flow

1. Admin configures the world (seed, radius, shape)
2. Server splits the zone into region tasks (32×32 chunks each)
3. Clients connect, get a batch of regions
4. Each client installs Java + loader + mods, launches MC headless
5. Chunky generates chunks via RCON commands
6. Clients upload `.mca` files (compressed Zstd) + SHA-256 hashes
7. Server validates hashes, optionally requires double-check
8. Assembler gathers validated regions into final world
9. Export as `.tar.gz` ready to use

## Features

- **Multi-loader**: Fabric, Forge, Quilt, NeoForge
- **Verification**: Optional double-generation for integrity
- **S3/R2**: Ephemeral storage for cloud deployments (Render, Vercel)
- **P2P**: BitTorrent distribution for mods.zip
- **Heatmap**: Real-time interactive map of generation progress
- **Benchmark**: Client speed scoring for task prioritization
- **i18n**: Multi-language logging (EN, FR, ES, DE)

## Licence

Apache v2.0 — see [`LICENSE`](/LICENSE)

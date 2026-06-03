# CHUNK-D-MESH

```text
 _____  _   _ _   _ _   _  _   __     ______       ___  ___ _____ _____ _   _ 
/  __ \| | | | | | | \ | || | / /     |  _  \      |  \/  ||  ___/  ___| | | |
| /  \/| |_| | | | |  \| || |/ /______| | | |______| .  . || |__ \ `--.| |_| |
| |    |  _  | | | | . ` ||    \______| | | |______| |\/| ||  __| `--. \  _  |
| \__/\| | | | |_| | |\  || |\  \     | |/ /       | |  | || |___/\__/ / | | |
 \____/\_| |_/\___/\_| \_/\_| \_/     |___/        \_|  |_/\____/\____/\_| |_/
```

A small project aimed at experimenting with the distribution and allocation of "chunks" in a mesh network.

The project is largely based on the official server, which can be downloaded from Mojang, and on the Chunky mod/plugin, which features excellent threading management.

## Requirements

- Python 3.10+ (recommanded)
- See [`requirements.txt`](/requirements.txt) for dependancies

## Fast install

```sh
  python -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
```

## Usage

- Configure your world, seed, radius, etc in [`server/config/world_config.json5`](/server/config/world_config.json5).
- Launch the server from [`server/main.py`](/server/main.py).

## Licence

This project is provided under Apache v2.0 License, see [`LICENSE`](/LICENSE).

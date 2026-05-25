# CHUNK-D-MESH

```text
 _____  _   _ _   _ _   _  _   __     ______       ___  ___ _____ _____ _   _ 
/  __ \| | | | | | | \ | || | / /     |  _  \      |  \/  ||  ___/  ___| | | |
| /  \/| |_| | | | |  \| || |/ /______| | | |______| .  . || |__ \ `--.| |_| |
| |    |  _  | | | | . ` ||    \______| | | |______| |\/| ||  __| `--. \  _  |
| \__/\| | | | |_| | |\  || |\  \     | |/ /       | |  | || |___/\__/ / | | |
 \____/\_| |_/\___/\_| \_/\_| \_/     |___/        \_|  |_/\____/\____/\_| |_/
```

Petit projet visant à expérimenter la distribution et l'allocation de "chunks" dans un réseau maillé.

Le projet est en grande partie basé sur le serveur officiel téléchargeable depuis Mojang, et sur le mod/plugin Chunky, qui a une excellente gestion du threading.

## Caractéristiques

- Échange pair-à-pair de chunks
- Allocation/verification côté orchestrateur
- Configuration JSON/JSON5 légère

## Prérequis

- Python 3.10+ (recommandé)
- Voir `requirements.txt` pour les dépendances

## Installation rapide

```sh
  python -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
```

## Usage

- L'orchestrateur principal se lance depuis `orchestrator/main.py`.
- La configuration se trouve dans le dossier `config/`.

Exemple :

```sh
  python -m orchestrator.main
```

## Contribuer

- Ouvrez une issue pour discuter des fonctionnalités.
- PR bienvenues ; gardez les changements petits et documentés.

## Licence

Ce projet est fourni sous licence Apache v2.0 (voir le fichier `LICENSE`).

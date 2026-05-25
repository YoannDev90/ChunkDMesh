import random
import sys
import os
import json
import asyncio
import aiosqlite
from typing import Union, Tuple
from pathlib import Path

# Ajouter le répertoire racine au sys.path pour permettre les imports du package 'shared'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from InquirerPy import inquirer
from InquirerPy.validator import NumberValidator
from shared.shapes import ShapeType
from shared.patterns import PatternType
import config


def save_world_config(data: dict):
    """Sauvegarde la configuration dans data/world_settings.json."""
    save_path = config.ACTIVE_CONFIG_PATH
    save_path.parent.mkdir(parents=True, exist_ok=True)

    # On charge la configuration actuelle
    try:
        conf_obj = config.load_config()
        current_config = conf_obj.model_dump()
    except Exception:
        current_config = {}

    # Mise à jour avec les nouvelles valeurs
    current_config.update(data)

    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(current_config, f, indent=2)

    return save_path


async def populate_tasks(center, radius):
    """Génère la liste des tâches (chunks) dans la base de données de manière asynchrone."""
    # S'assurer que le parent du fichier DB existe
    absolute_db_path = config.DB_PATH.resolve()
    absolute_db_path.parent.mkdir(parents=True, exist_ok=True)

    cx, cz = (0, 0) if center == "spawn" else center
    radius = int(radius)

    print(f"Calcul et insertion des tâches pour un rayon de {radius}...")

    async with aiosqlite.connect(str(absolute_db_path)) as db:
        # Initialisation rapide du schéma si nécessaire
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                x INTEGER NOT NULL,
                z INTEGER NOT NULL,
                status TEXT DEFAULT 'PENDING',
                UNIQUE(x, z)
            )
        """)

        batch = []
        batch_insert_size = 50000
        total_inserted = 0

        for x in range(cx - radius, cx + radius + 1):
            for z in range(cz - radius, cz + radius + 1):
                batch.append((x, z))

                if len(batch) >= batch_insert_size:
                    await db.executemany(
                        "INSERT OR IGNORE INTO tasks (x, z) VALUES (?, ?)", batch
                    )
                    await db.commit()
                    total_inserted += len(batch)
                    print(f"Inserés : {total_inserted} tâches...", end="\r")
                    batch = []

            # On rend la main à l'event loop à chaque ligne X pour ne pas bloquer l'API
            await asyncio.sleep(0)

        if batch:
            await db.executemany(
                "INSERT OR IGNORE INTO tasks (x, z) VALUES (?, ?)", batch
            )
            await db.commit()
            total_inserted += len(batch)

    print(f"\nBase de données mise à jour avec {total_inserted} tâches.")


async def initialize_world_gen():
    """Initialise les paramètres et les ressources nécessaires pour la génération du monde via une TUI (InquirerPy)."""

    world_name = await inquirer.text(
        message="Entrez le nom du monde à générer :",
        default="NewWorld",
        validate=lambda result: len(result) > 0 or "Le nom ne peut pas être vide",
    ).execute_async()

    use_random_seed = await inquirer.confirm(
        message="Utiliser une graine aléatoire ?", default=True
    ).execute_async()

    if use_random_seed:
        seed = random.randint(-999_999_999_999_999, 999_999_999_999_999)
    else:
        seed_str = await inquirer.text(
            message="Entrez une graine pour la génération :",
            validate=lambda result: (
                result.strip("-").isdigit() or "La graine doit être un nombre"
            ),
        ).execute_async()
        seed = int(seed_str)

    center_type = await inquirer.select(
        message="Type de centre de génération :",
        choices=[
            {"name": "Spawn point", "value": "spawn"},
            {"name": "Coordonnées personnalisées", "value": "custom"},
        ],
        default="spawn",
    ).execute_async()

    center: Union[str, Tuple[int, int]]
    if center_type == "custom":
        center_x = await inquirer.text(
            message="Coordonnée X :", validate=NumberValidator()
        ).execute_async()
        center_z = await inquirer.text(
            message="Coordonnée Z :", validate=NumberValidator()
        ).execute_async()
        center = (int(center_x), int(center_z))
    else:
        center = "spawn"

    radius = await inquirer.number(
        message="Rayon de génération (en chunks) :",
        min_allowed=1,
        max_allowed=1_000_000,
        default=1000,
        validate=NumberValidator(),
    ).execute_async()

    batch_size = await inquirer.number(
        message="Nombre de chunks par paquet (Batch size) :",
        min_allowed=1,
        max_allowed=5000,
        default=50,
        validate=NumberValidator(),
    ).execute_async()

    additional_settings = await inquirer.confirm(
        message="Configurer des paramètres additionnels (Shape, Pattern) ?",
        default=False,
    ).execute_async()

    shape = None
    pattern = None

    if additional_settings:
        shape = await inquirer.select(
            message="Sélectionnez la forme (Shape) :",
            choices=[
                {"name": s.name.capitalize(), "value": s.value} for s in ShapeType
            ],
            default=ShapeType.SQUARE.value,
        ).execute_async()

        pattern = await inquirer.select(
            message="Sélectionnez le motif (Pattern) :",
            choices=[
                {"name": p.name.capitalize(), "value": p.value} for p in PatternType
            ],
            default=PatternType.SPIRAL.value,
        ).execute_async()

    print("\n" + "=" * 50)
    print("Résumé de la configuration :")
    print(f" - Monde    : {world_name}")
    print(f" - Graine   : {seed}")
    print(f" - Centre   : {center}")
    print(f" - Rayon    : {radius} chunks")
    print(f" - Batch    : {batch_size} chunks/client")
    if additional_settings:
        print(f" - Shape    : {shape}")
        print(f" - Pattern  : {pattern}")
    print("=" * 50 + "\n")

    if await inquirer.confirm(
        message="Lancer la génération du monde ?", default=True
    ).execute_async():
        # Préparation des données pour la config
        config_data = {
            "world_name": world_name,
            "seed": seed,
            "center": [center[0], center[1]] if isinstance(center, tuple) else "spawn",
            "radius": radius,
            "batch_size": batch_size,
        }
        if shape:
            config_data["shape"] = shape
        if pattern:
            config_data["pattern"] = pattern

        save_path = save_world_config(config_data)
        print(f"Configuration sauvegardée dans : {save_path}")
        print(f"Génération du monde '{world_name}' en cours...")

        # Peupler la base de données avec les tâches
        await populate_tasks(center, radius)
    else:
        print("Génération annulée.")


if __name__ == "__main__":
    if config.ACTIVE_CONFIG_PATH.exists():
        print(f"Configuration existante trouvée : {config.ACTIVE_CONFIG_PATH}")
        conf = config.load_config()
        asyncio.run(
            populate_tasks(
                conf.center if hasattr(conf, "center") else "spawn",
                conf.radius if hasattr(conf, "radius") else 0,
            )
        )
    else:
        asyncio.run(initialize_world_gen())

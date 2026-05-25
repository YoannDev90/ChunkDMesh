import asyncio
import hashlib
import logging
import uuid
from pathlib import Path
from typing import List, Optional

import aiohttp
from pydantic import BaseModel

from assets import AssetManager
from runner import MinecraftRunner

# Configuration simplifiée pour le client (à déplacer dans un config.py plus tard)
SERVER_URL = "http://localhost:5000"
WORK_DIR = Path("client_data")
LOGGER_NAME = "CHUNKDMESH_CLIENT"
MC_VERSION = "1.21.11"

# Logging setup
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(LOGGER_NAME)


class Task(BaseModel):
    task_id: int
    x: int
    z: int


class TaskBatch(BaseModel):
    batch_id: int
    tasks: List[Task]
    seed: Optional[int]
    shape: str
    pattern: str


class Client:
    def __init__(self, server_url: str = SERVER_URL):
        self.server_url = server_url
        self.token: Optional[str] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.assets = AssetManager(WORK_DIR)
        self.runner = MinecraftRunner(self.assets.server_dir)
        WORK_DIR.mkdir(parents=True, exist_ok=True)

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={"Content-Type": "application/json"}
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def setup(self):
        """Phase d'initialisation : téléchargement du serveur, chunky, etc."""
        logger.info("Démarrage de la phase de setup...")

        # 1. Download Server & Loader
        vanilla_jar = await self.assets.setup_vanilla_server(self.session, MC_VERSION)
        loader_jar = await self.assets.setup_fabric_loader(self.session, MC_VERSION)

        # 2. Extract Mods si dispo
        instance_mods = self.assets.server_dir / "mods"
        instance_mods.mkdir(exist_ok=True)

        mods_zip = Path("mods.zip")
        if mods_zip.exists():
            await self.assets.extract_mods(mods_zip)

        # 3. Vérifier si Chunky et Fabric API sont présents, sinon les télécharger
        chunky_present = any(
            "chunky" in f.name.lower() for f in instance_mods.glob("*.jar")
        )
        fabric_api_present = any(
            "fabric-api" in f.name.lower() or "fabric-api" in f.name.lower()
            for f in instance_mods.glob("*.jar")
        )

        if not chunky_present:
            logger.info(
                "Chunky non trouvé dans mods.zip, téléchargement depuis Modrinth..."
            )
            await self.assets.setup_chunky(
                self.session, MC_VERSION, dest_dir=instance_mods
            )

        if not fabric_api_present:
            logger.info("Fabric API non trouvé, téléchargement depuis Modrinth...")
            await self.assets.setup_modrinth_project(
                self.session, "fabric-api", MC_VERSION, dest_dir=instance_mods
            )

        # 4. Prepare instance
        await self.assets.prepare_instance(vanilla_jar, loader_jar)
        logger.info("Setup terminé.")

    async def connect(self):
        """Se connecte au serveur et récupère un token."""
        async with self.session.get(f"{self.server_url}/connect") as resp:
            if resp.status == 200:
                data = await resp.json()
                self.token = data["token"]
                self.session.headers.update({"X-Client-Token": self.token})
                logger.info(f"Connecté au serveur. Token: {self.token[:8]}...")
            else:
                logger.error(f"Échec de connexion: {resp.status}")
                raise Exception("Impossible de se connecter au serveur")

    async def get_tasks(self) -> Optional[TaskBatch]:
        """Récupère un lot de tâches."""
        async with self.session.get(f"{self.server_url}/get_task") as resp:
            if resp.status == 200:
                data = await resp.json()
                return TaskBatch(**data)
            elif resp.status == 404:
                logger.info("Plus de tâches disponibles.")
                return None
            else:
                logger.error(
                    f"Erreur lors de la récupération des tâches: {resp.status}"
                )
                return None

    async def process_task(self, task: Task, batch_info: TaskBatch):
        """Exécute Chunky pour une tâche."""
        logger.info(f"Traitement du chunk ({task.x}, {task.z})...")

        # Exécution réelle via le runner
        file_path = await self.runner.run_chunky_task(task.x, task.z)

        # Calcul de la signature réelle sur le fichier produit
        signature = "none"
        if file_path and file_path.exists():
            with open(file_path, "rb") as f:
                signature = hashlib.sha256(f.read()).hexdigest()

        return {
            "task_id": task.task_id,
            "signature": signature,
            "file_path": str(file_path) if file_path else None,
        }

    async def submit_results(self, results: List[dict]):
        """Envoie les résultats au serveur."""
        for res in results:
            task_id = res["task_id"]
            signature = res["signature"]
            file_path = res.get("file_path")

            if file_path and Path(file_path).exists():
                # Envoi multipart pour inclure le fichier
                data = aiohttp.FormData()
                data.add_field("task_id", str(task_id))
                data.add_field("signature", signature)
                data.add_field(
                    "file", open(file_path, "rb"), filename=Path(file_path).name
                )

                async with self.session.post(
                    f"{self.server_url}/submit_result", data=data
                ) as resp:
                    if resp.status == 200:
                        logger.info(f"Fichier pour tâche {task_id} envoyé.")
                    else:
                        logger.error(f"Erreur envoi tâche {task_id}: {resp.status}")
            else:
                # Envoi JSON standard si pas de fichier (fallback)
                payload = {"results": [res]}
                async with self.session.post(
                    f"{self.server_url}/submit_result", json=payload
                ) as resp:
                    if resp.status == 200:
                        logger.info(f"Résultat simple pour tâche {task_id} envoyé.")

    async def run(self):
        """Boucle principale."""
        await self.connect()
        await self.setup()

        # Lancement du serveur MC en fond
        asyncio.create_task(self.runner.run_server())

        # On attend que le serveur soit prêt (log "Done") AVANT de demander des tâches
        try:
            logger.info("Attente du démarrage complet du serveur Minecraft...")
            await self.runner.wait_for_log("Done", timeout=120)
        except Exception as e:
            logger.error(f"Le serveur Minecraft n'a pas pu démarrer : {e}")
            return

        while True:
            batch = await self.get_tasks()
            if not batch:
                logger.info("Plus de tâches. Attente...")
                await asyncio.sleep(30)
                continue

            logger.info(f"Reçu batch {batch.batch_id} avec {len(batch.tasks)} tâches.")
            results = []
            for task in batch.tasks:
                res = await self.process_task(task, batch)
                results.append(res)

            await self.submit_results(results)


async def main():
    async with Client() as client:
        await client.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Arrêt du client.")

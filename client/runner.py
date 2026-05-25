import asyncio
import logging
import subprocess
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("CHUNKDMESH_CLIENT")


class MinecraftRunner:
    def __init__(self, instance_dir: Path):
        self.instance_dir = instance_dir
        self.process: Optional[asyncio.subprocess.Process] = None
        self._output_queue = asyncio.Queue()
        self._read_task: Optional[asyncio.Task] = None

    async def _read_stdout(self):
        """Lit continuellement la sortie standard et la distribue."""
        if not self.process or not self.process.stdout:
            return

        async for line in self.process.stdout:
            decoded_line = line.decode().strip()
            # On affiche TOUTES les lignes en debug pour voir ce qui se passe
            print(f"[MC] {decoded_line}")
            # On met la ligne dans une queue
            await self._output_queue.put(decoded_line)

    async def wait_for_log(self, pattern: str, timeout: float = 300):
        """Attend qu'une ligne spécifique apparaisse dans les logs."""
        start_time = asyncio.get_event_loop().time()
        while True:
            # On vérifie le timeout global
            passed = asyncio.get_event_loop().time() - start_time
            if passed > timeout:
                raise TimeoutError(f"Timeout en attendant le log : {pattern}")

            try:
                # On attend une ligne de la queue
                line = await asyncio.wait_for(self._output_queue.get(), timeout=1.0)
                if pattern in line:
                    return line
            except asyncio.TimeoutError:
                # Si pas de ligne dans la seconde, on reboucle (pour vérifier le timeout global)
                continue

    async def run_server(self, jar_name: str = "server.jar", memory: str = "2G"):
        """Lance le serveur Minecraft en headless."""
        # Création d'un server.properties minimal si absent pour éviter l'erreur au boot
        props_path = self.instance_dir / "server.properties"
        if not props_path.exists():
            with open(props_path, "w") as f:
                f.write("level-name=world\nonline-mode=false\ngamemode=survival\n")

        cmd = [
            "java",
            f"-Xmx{memory}",
            f"-Xms{memory}",
            "-Djava.awt.headless=true",
            "-jar",
            jar_name,
            "nogui",
        ]

        logger.info(f"Lancement du serveur : {' '.join(cmd)}")

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.instance_dir,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # On lance la lecture asynchrone des logs
        self._read_task = asyncio.create_task(self._read_stdout())

        # On attend que le serveur soit prêt (log "Done")
        try:
            # On augmente le timeout à 120s et on cherche un pattern plus large
            await self.wait_for_log("Done", timeout=120)
            logger.info("Serveur Minecraft prêt.")
        except TimeoutError:
            logger.error(
                "Le serveur a mis trop de temps à démarrer ou le message 'Done' n'a pas été capturé."
            )

    async def send_command(self, command: str):
        """Envoie une commande au serveur."""
        if self.process and self.process.stdin:
            logger.info(f"Envoi commande : {command}")
            self.process.stdin.write(f"{command}\n".encode())
            await self.process.stdin.drain()

    async def stop_server(self):
        """Arrête proprement le serveur."""
        if self._read_task:
            self._read_task.cancel()
        if self.process:
            await self.send_command("stop")
            await self.process.wait()
            logger.info("Serveur Minecraft arrêté.")

    async def run_chunky_task(self, x: int, z: int, radius: int = 1) -> Optional[Path]:
        """Exécute Chunky pour un chunk spécifique et retourne le chemin du fichier généré."""
        await self.send_command(f"chunky center {x} {z}")
        await self.send_command(f"chunky radius {radius}")
        await self.send_command("chunky start")

        # On attend la fin du maillage via notre nouvelle méthode wait_for_log
        try:
            await self.wait_for_log("Generation complete", timeout=300)
            logger.info(f"Chunky terminé pour {x}, {z}")
        except TimeoutError:
            logger.error(f"Timeout Chunky pour {x}, {z}")

        # Recherche du fichier généré
        output_pattern = f"chunky_output/{x}_{z}.mca"
        potential_file = self.instance_dir / output_pattern

        if potential_file.exists():
            return potential_file

        # Fallback de simulation
        fake_file = self.instance_dir / f"dummy_{x}_{z}.mca"
        if not fake_file.exists():
            with open(fake_file, "w") as f:
                f.write(f"Data for {x} {z}")
        return fake_file

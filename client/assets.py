import asyncio
import logging
import os
import shutil
import zipfile
from pathlib import Path
from typing import Optional

import aiohttp
from pyrinth import Project

logger = logging.getLogger("CHUNKDMESH_CLIENT")


class AssetManager:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.bin_dir = base_dir / "bin"
        self.mods_dir = base_dir / "mods"
        self.server_dir = base_dir / "server_instance"

        for d in [self.bin_dir, self.mods_dir, self.server_dir]:
            d.mkdir(parents=True, exist_ok=True)

    async def download_file(self, session: aiohttp.ClientSession, url: str, dest: Path):
        if dest.exists():
            logger.info(f"Fichier déjà présent : {dest.name}")
            return dest

        logger.info(f"Téléchargement de {url}...")
        async with session.get(url) as resp:
            if resp.status == 200:
                with open(dest, "wb") as f:
                    f.write(await resp.read())
                return dest
            else:
                raise Exception(f"Erreur téléchargement {url}: {resp.status}")

    async def setup_vanilla_server(
        self, session: aiohttp.ClientSession, version: str = "1.20.1"
    ):
        """Télécharge le serveur Vanilla depuis Mojang (via manifest)."""
        manifest_url = "https://launchermeta.mojang.com/mc/game/version_manifest.json"
        async with session.get(manifest_url) as resp:
            manifest = await resp.json()

        version_entry = next(
            (v for v in manifest["versions"] if v["id"] == version), None
        )
        if not version_entry:
            raise Exception(f"Version {version} non trouvée chez Mojang")

        async with session.get(version_entry["url"]) as resp:
            version_data = await resp.json()
            server_url = version_data["downloads"]["server"]["url"]

        dest = self.bin_dir / f"server-{version}.jar"
        return await self.download_file(session, server_url, dest)

    async def setup_fabric_loader(
        self, session: aiohttp.ClientSession, mc_version: str
    ):
        """Télécharge le loader Fabric (installer)."""
        # Utilisation de l'API meta de Fabric avec la version 0.19.2
        url = f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}/0.19.2/1.0.1/server/jar"
        dest = self.bin_dir / f"fabric-server-launch.jar"
        return await self.download_file(session, url, dest)

    async def setup_modrinth_project(
        self,
        session: aiohttp.ClientSession,
        project_slug: str,
        mc_version: str,
        dest_dir: Path,
    ):
        """Télécharge un projet Modrinth spécifique."""
        project = Project.get(project_slug)
        versions = project.get_versions(game_versions=[mc_version], loaders=["fabric"])

        if not versions:
            # Fallback sur la version mineure (ex: 1.21 si 1.21.1)
            minor = ".".join(mc_version.split(".")[:2])
            versions = project.get_versions(game_versions=[minor], loaders=["fabric"])

        if not versions:
            raise Exception(
                f"Aucune version de {project_slug} trouvée pour MC {mc_version}"
            )

        target_version = versions[0]
        file_data = target_version.get_files()[0]
        dest = dest_dir / file_data.name
        return await self.download_file(session, file_data.url, dest)

    async def setup_chunky(
        self,
        session: aiohttp.ClientSession,
        mc_version: str,
        dest_dir: Optional[Path] = None,
    ):
        """Télécharge Chunky via Modrinth."""
        target_dir = dest_dir or self.bin_dir
        return await self.setup_modrinth_project(
            session, "chunky", mc_version, target_dir
        )

    async def extract_mods(self, mods_zip_path: Path):
        """Extrait les mods du zip vers le dossier mods de l'instance."""
        if not mods_zip_path.exists():
            logger.error(f"Archive mods non trouvée : {mods_zip_path}")
            return

        instance_mods = self.server_dir / "mods"
        instance_mods.mkdir(exist_ok=True)

        with zipfile.ZipFile(mods_zip_path, "r") as zip_ref:
            zip_ref.extractall(instance_mods)
        logger.info(f"Mods extraits dans {instance_mods}")

    async def prepare_instance(
        self, server_jar: Path, loader_jar: Optional[Path] = None
    ):
        """Prépare le dossier d'exécution (eula, server.jar)."""
        # Acceptation EULA
        with open(self.server_dir / "eula.txt", "w") as f:
            f.write("eula=true\n")

        # Copie ou lien du jar
        target_jar = self.server_dir / "server.jar"
        if loader_jar:
            shutil.copy(loader_jar, target_jar)
            # Fabric server jar a besoin du vanilla à côté souvent nommé 'server.jar' ou configuré
            shutil.copy(server_jar, self.server_dir / "vanilla.jar")
        else:
            shutil.copy(server_jar, target_jar)

        return target_jar

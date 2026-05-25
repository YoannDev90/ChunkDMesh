import os
import tarfile
import logging
from pathlib import Path
import config
from database import Database, Type

LOGGER = logging.getLogger(config.LOGGER_NAME)


async def assemble_world(world_name: str, output_path: str = None):
    """
    Récupère tous les chunks validés, les assemble et crée un world.tar.gz.
    """
    if output_path is None:
        output_path = config.ACTIVE_CONFIG_PATH.parent / "exports"

    output_dir = Path(output_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    tar_filename = output_dir / f"{world_name}.tar.gz"

    async with Database() as db:
        # On récupère tous les chemins de données des chunks validés
        query = """
        SELECT r.data_path, t.x, t.z 
        FROM tasks t
        JOIN results r ON t.id = r.task_id
        WHERE t.status = 'VALIDATED'
        GROUP BY t.id -- Pour éviter les doublons si verification active
        """
        results = await db.execute_query(query, type=Type.TUPLE)

    if not results:
        LOGGER.warning("Aucun chunk validé à assembler.")
        return None

    LOGGER.info(f"Assemblage de {len(results)} chunks dans {tar_filename}...")

    with tarfile.open(tar_filename, "w:gz") as tar:
        for data_path, x, z in results:
            if data_path and os.path.exists(data_path):
                # On ajoute le fichier dans l'archive avec un nom structuré
                # Exemple: region/chunk_x_z.mesh
                arcname = f"region/{x}_{z}.mesh"
                tar.add(data_path, arcname=arcname)
            else:
                # Si on n'a pas encore de fichier physique (juste du hash)
                # On peut créer un index texte ou ignorer pour l'instant
                pass

    LOGGER.info(f"Monde exporté avec succès.")
    return str(tar_filename)

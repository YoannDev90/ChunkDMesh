from hashlib import sha256


def sha256_hex(data: bytes) -> str:
    """Calcule le SHA-256 hexadécimal d'un bloc de données."""
    return sha256(data).hexdigest()

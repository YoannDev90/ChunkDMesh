def allocate_regions(
    clients: list[dict[str, object]], regions: list[dict[str, object]]
) -> dict[str, list[dict[str, object]]]:
    """Répartit les régions entre les clients.

    Implémentation minimale à compléter selon la stratégie d'allocation.
    """
    assignments: dict[str, list[dict[str, object]]] = {
        str(client.get("id", idx)): [] for idx, client in enumerate(clients)
    }
    if not clients:
        return assignments

    for index, region in enumerate(regions):
        client = clients[index % len(clients)]
        client_id = str(client.get("id", index % len(clients)))
        assignments.setdefault(client_id, []).append(region)

    return assignments

# Cahier des Charges - ChunkDMesh

## 1. Présentation du Projet

ChunkDMesh est une plateforme distribuée de prégénération de mondes Minecraft. L'objectif est de permettre à des administrateurs de serveurs de générer de vastes mondes rapidement en répartissant la charge de calcul sur une multitude de clients volontaires.

## 2. Objectifs

- **Rapidité :** Réduire le temps de prégénération de plusieurs jours à quelques heures.
- **Accessibilité :** Permettre le déploiement du serveur sur des instances légères (Render, Vercel, VPS bas prix).
- **Simplicité :** Un client "One-Click" pour les volontaires.
- **Fiabilité :** Garantir l'intégrité du monde généré malgré la distribution des tâches.

## 3. Architecture Technique

Le projet adopte une architecture Client-Serveur via une API REST/WebSocket.

### 3.1 Serveur (Orchestrateur)

- **Langage :** Python (FastAPI).
- **Base de données :** SQLite (pour la légèreté) ou PostgreSQL (pour la scalabilité).
- **Rôles :**
  - Gestion de la file d'attente des chunks (Heatmap de génération).
  - Distribution des packages de configuration (Manifeste).
  - **Serveur de fichiers (Miroir) :** Héberge et distribue les archives de mods (`mods.zip`) et les JARs pour garantir une cohérence totale.
  - Validation des retours clients (Comparaison de hashes).
  - Fusion des fichiers de région (`.mca`) pour l'export final.

### 3.2 Client (Worker)

- **Langage :** Python.
- **Moteur de génération :** Minecraft Server + Fabric + Mod Chunky.
- **Rôles :**
  - **Gestion Java** : Détecte le JRE local. Si manquant ou incompatible, télécharge une version portable d'OpenJDK via l'API Adoptium.
  - **Synchro One-Click :** Télécharge l'archive complète du serveur, l'extrait dans un environnement isolé.
  - **Pilotage RCON** : Une fois le serveur Minecraft lancé, communique via le protocole RCON pour envoyer les commandes de génération (`chunky start`, `chunky pause`, etc.).
  - Hashage et envoi des données générées au serveur.

---

## 4. Spécifications Fonctionnelles

### 4.0 Flux de Données (Workflow)

1. **Initialisation** : L'admin configure le monde sur le serveur (Seed, Mods, Limites). Le serveur prépare son `Manifeste` et son archive d'assets.
2. **Découverte & Connexion** :
    - Le serveur s'enregistre sur un **Registre Central** (optionnel).
    - Le client se connecte via l'IP ou le Registre, reçoit le `Manifeste`.
    - **Phase de Benchmark** (Optionnel) : Le serveur demande au client de générer une petite zone fixe (ex: 2x2 chunks) pour évaluer sa vitesse (Chunks per second) et sa fiabilité.
3. **Attribution** : Le serveur donne un `Batch` (une ou plusieurs régions) basé sur le score du Benchmark.
4. **Génération** : Le client lance l'instance Minecraft et pilote Chunky via RCON.
5. **Transmission** : Le client compresse et envoie les fichiers `.mca` avec les hashes.
6. **Validation** : Le serveur vérifie le hash. Si configuré, il attend une seconde validation d'un autre client.
7. **Fusion** : Le serveur intègre les chunks validés dans la structure finale du monde.

### 4.1 Gestion des Tâches (Unités de Travail)

- **Granularité par Région (32x32 chunks)** : Pour simplifier la fusion et les transferts, l'unité de travail minimale est le fichier de région complète (`.mca`).
- **Score de Performance** : Le serveur priorise l'envoi des régions centrales ou complexes aux clients ayant le meilleur ratio au Benchmark.

### 4.2 Synchronisation Client-Serveur

- **Authentification Flexible** :
  - **Mode Public** : N'importe quel client peut se connecter (parfait pour le soutien communautaire).
  - **Mode Whitelist** : Seuls les clients possédant une `ACCESS_KEY` définie dans la config du serveur peuvent s'enregistrer.
- **Manifeste de Session :** Avant toute génération, le client valide son environnement via un manifeste (Version MC, Hash des mods, Seed, Config de génération).
- **Heartbeat :** Le client envoie un ping toutes les 30s. Si le client disparaît, ses tâches sont remises en file d'attente après un timeout.

### 4.3 Validation et Sécurité

- **Redondance (Double-Check) :** Possibilité de faire générer le même lot par 2 clients différents.
- **Comparaison de Hashes :** Le serveur compare les hashes des fichiers `.mca` produits. En cas de divergence, une tierce génération est lancée.
- **Protection contre la triche :** Analyse sommaire du contenu des chunks (ex: présence de bedrock, structure globale) pour éviter l'envoi de fichiers vides.

### 4.4 Assemblage du Monde (Anvil Merge)

Le format Anvil (.mca) stocke 1024 chunks (32x32). La fusion est le processus le plus complexe :

- **Extraction sélective** : Le serveur reçoit un fichier `.mca` partiel du client (contenant uniquement les chunks du batch).
- **Injection atomique** : Pour chaque chunk reçu, le serveur doit :
    1. Ouvrir le fichier de région cible existant.
    2. Vérifier si le chunk y est déjà présent et validé.
    3. Injecter les données NBT du chunk.
    4. Recalculer les offsets et les timestamps du fichier `.mca`.
- **Mécanisme de sécurité** : Utilisation d'un fichier `.mca.tmp` pour éviter la corruption en cas de crash lors de l'écriture.

### 4.5 Registre Central & Découverte

Pour simplifier la mise en relation, un service tiers (optionnel) peut être utilisé :

- **Master Server** : Un service public où chaque serveur ChunkDMesh s'enregistre avec son nom, sa version de monde et son IP.
- **Client Autoconnect** : Le client peut parcourir la liste des serveurs publics cherchant de l'aide ou se connecter manuellement à une IP spécifique.
- **Token de session** : Une fois la connexion établie, un échange de clé publique/privée sécurise les échanges ultérieurs.

---

## 5. Spécifications Techniques & API

### 5.1 Endpoints API (Détaillés)

- `POST /auth/login` : Le client envoie ses capacités (CPU, RAM disponible) et reçoit un token JWT.
- `GET /assets/mods.zip` : Streaming de l'archive des mods (avec support du header `Range`).
- `GET /assets/config.json` : Configuration spécifique de Chunky pour cette session.
- `GET /tasks/batch` : Récupère un lot de chunks. Le serveur marque le batch comme `ASSIGNED`.
- `POST /tasks/submit` : Envoie les hashes SHA-256 de chaque chunk généré.
- `PUT /tasks/upload/{batch_id}` : Upload binaire des données de chunks (compressées en Zstd).
- `GET /admin/heatmap` : Renvoie une matrice de l'état du monde pour le dashboard.

### 5.2 Modèle de Données (Base de données)

- **Clients** : `id, token, ip, reput, cpu_cores, ram_gb, last_seen`.
- **Worlds** : `id, name, seed, mc_version, loader_type, status`.
- **Batches** : `id, world_id, region_x, region_z, status (pending, working, completed, validated), assigned_to, retry_count`.
- **Validations** : `id, batch_id, client_id, file_hash, storage_path`.

### 5.3 Structure du Manifeste (JSON)

Le manifeste est le contrat entre le serveur et le client :

```json
{
  "session_id": "uuid-v4",
  "minecraft": {
    "version": "1.21.1",
    "loader": "fabric-0.15.11"
  },
  "world": {
    "seed": 123456789,
    "generators": ["chunky"],
    "dimensions": ["overworld"]
  },
  "assets": {
    "mods_hash": "sha256-...",
    "config_hash": "sha256-..."
  }
}
```

### 5.4 Environnement Client

- **Isolation :** Utilisation de dossiers temporaires isolés pour chaque session.
- **Gestion des ressources :** Limiteur de CPU/RAM configurable par l'utilisateur (ex: max 4 cores, 4GB RAM).
- **Auto-Update :** Capacité du client à se mettre à jour ou à mettre à jour les mods requis par le serveur.

### 5.5 Gestion du Stockage (Options d'Architecture)

Selon le type de déploiement, le serveur supporte trois modes de stockage pour les fichiers `.mca` :

1. **Mode Local (Standard)** : Les fichiers sont stockés dans le dossier `data/exports`. Idéal pour les VPS avec gros disque dur.
2. **Mode Ephemeral + S3/R2 (Recommended for Render/Vercel)** :
    - Chaque région validée est immédiatement uploadée sur un stockage objet (AWS S3, Cloudflare R2).
    - L'espace disque local du serveur reste proche de 0.
    - L'export final est un lien de téléchargement direct depuis le bucket S3.
3. **Mode "World Relay"** :
    - Le serveur ChunkDMesh s'installe *à côté* du serveur Minecraft final.
    - Les fichiers sont injectés directement dans le dossier `world/region` du vrai jeu.

### 5.6 Performance & Bande Passante

- **Compression Zstd** : Toutes les transmissions binaires utilisent Zstandard pour minimiser le coût réseau.
- **Streaming Files** : Le serveur utilise le streaming pour envoyer les JARs/Mods afin d'économiser la RAM.
- **Auto-Cleanup** : Les instances Minecraft sur le client et les fichiers temporaires sur le serveur sont supprimés automatiquement.

---

## 6. Interface Utilisateur (UI/UX)

- **Dashboard Admin (Integrated Web)** :
  - Développé avec **Jinja2 + HTMX** (intégré directement à FastAPI).
  - Pas d'application séparée nécessaire, accessible via `http://<ip-serveur>/admin`.
  - **Vue Heatmap** : Représentation visuelle des régions générées/valides.
  - **Gestion Clients** : Liste des workers, scores de réputation, kick/ban.
- **Client (Worker CLI)** :
  - Interface console stylisée avec `rich`.
  - Progression par région et temps estimé restant.

---

## 7. Roadmap (Phasage)

1. **V1 (Core) :** Distribution de tâches simple et renvoi de fichiers complets.
2. **V2 (Fiabilité) :** Système de Manifeste + Hashage + WebSockets.
3. **V3 (Optimisation) :** Fusion intelligente au niveau des fichiers de région (`.mca`).
4. **V4 (Écosystème) :** Interface Web Admin + Client avec UI Desktop.

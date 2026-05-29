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

### 3.3 Distribution Hybride P2P (Optionnelle)

Pour soulager le serveur central lors de sessions avec de nombreux clients :
- **Protocole BitTorrent** : Le serveur peut générer un `.torrent` pour le `mods.zip`. Les clients deviennent des "seeders" après avoir téléchargé l'archive, réduisant drastiquement l'egress du serveur.
- **Peer-to-Peer Data Transfer** : Les fichiers de région `.mca` validés peuvent être partagés directement entre les clients pour les phases de double-vérification.

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

### 4.4 Assemblage du Monde (MCA Replacement)

L'unité de base étant la région (32x32 chunks), la fusion est simplifiée :
- **Remplacement de Fichier** : Le serveur reçoit un fichier `.mca` complet.
- **Vérification de l'Intégrité** : Le serveur vérifie que le fichier est un format Anvil valide et que son nom correspond à la région attendue (`r.X.Z.mca`).
- **Stockage Final** : Le fichier est déplacé directement dans le dossier `world/region/` final.
- **Export** : Une fois la zone cible couverte, génération d'un fichier `.tar.gz` ou `.zip` prêt à l'emploi.

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

## 7. Roadmap Détaillée (MVP à V1)

### Phase 1 : Fondations du Serveur (Le Cerveau)

- [ ] **1.1 Structure API** : Initialisation FastAPI + Système de logs.
- [ ] **1.2 Base de Données** : Schéma SQLite (Clients, Worlds, Batches, Validations).
- [ ] **1.3 Dashboard Minimal** : Route Jinja2 affichant la liste des clients et l'état global.
- [ ] **1.4 Auth & Registration** : Endpoint `/auth/register` (Gestion Whitelist/Mode Public).
- [ ] **1.5 Gestionnaire de Manifeste** : Logique de création du JSON de session à partir des fichiers locaux.

### Phase 2 : Communication & Assets

- [ ] **2.1 File Server** : Endpoint de streaming pour le `mods.zip` et les JARs.
- [ ] **2.2 Logique de Batching** : Algorithme de découpe d'une zone (ex: -5000 à +5000) en régions `r.X.Z.mca`.
- [ ] **2.3 Attribution des tâches** : Endpoint `/tasks/next` gérant les timeouts et les réattributions.

### Phase 3 : Le Client "Worker" de base

- [ ] **3.1 Détecteur Java** : Script de recherche JRE locale + download fallback OpenJDK.
- [ ] **3.2 Asset Manager** : Téléchargement, vérification de hash et extraction du package du serveur.
- [ ] **3.3 Instance Runner** : Lancement du serveur Minecraft en mode Headless (Capture stdout/stderr).
- [ ] **3.4 RCON Client** : Connexion et envoi des commandes de base à Chunky.

### Phase 4 : Retour de Force & Validation

- [ ] **4.1 Upload sérialisé** : Système d'envoi des fichiers `.mca` compressés en Zstd.
- [ ] **4.2 Vérificateur de Hash** : Validation côté serveur des fichiers reçus vs les hashes déclarés par le client.
- [ ] **4.3 Système de Redondance** : Logique de comparaison si deux clients génèrent la même région.

### Phase 5 : Fusion & Finalisation

- [ ] **5.1 Region Assembler** : Déplacement et organisation finale des fichiers `.mca` dans le dossier world.
- [ ] **5.2 Export Manager** : Création automatique de l'archive `.tar.gz` une fois la zone complétée.
- [ ] **5.3 Interface Heatmap** : Vue visuelle (Canvas ou Grille HTMX) de la progression des régions sur le Dashboard.

### Phase 6 : Optimisations & Cloud

- [ ] **6.1 Benchmark** : Routine de test de vitesse client lors de la première connexion.
- [ ] **6.2 S3/R2 Driver** : Implémentation de l'upload automatique des régions vers un stockage objet.
- [ ] **6.3 Distribution P2P** : Intégration de `libtorrent` pour le partage du `mods.zip` et des données de monde.
- [ ] **6.4 Auto-Update** : Système de mise à jour du client via le serveur.

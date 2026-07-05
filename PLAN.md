# ChunkDMesh — Plan Communauté, 0-Trust & Récompenses

## Vision

ChunkDMesh devient une **infrastructure ouverte** de prégénération de monde Minecraft :
- Un streamer/hébergeur lance le serveur (VPS, Render, PC perso)
- Les viewers/joueurs installent le client en 1 clic et "prêtent" leur CPU
- Le système détecte automatiquement les tricheurs
- Le streamer récompense les contributeurs avec des items en jeu

---

## 1. Onboarding & Déploiement

### 1.1 OAuth Social — Discord, Twitch, Minecraft

Au lieu (ou en complément) des codes d'invite, le joueur s'authentifie avec son compte existant.

#### Flow Général

```
1. Joueur clique "Se connecter avec Discord"
2. Redirigé vers Discord OAuth → scope identify + guilds (optionnel)
3. Callback → serveur récupère { id, username, avatar, guilds }
4. Serveur crée/link le Client avec discord_id
5. JWT émis, client démarre

Même flow pour Twitch, Microsoft (Minecraft).
```

#### Modèle DB — Comptes Liés

```python
class LinkedAccount(Base):
    """Compte social lié à un client ChunkDMesh."""
    id: int
    client_id: int = ForeignKey("clients.id")
    provider: str                     # "discord", "twitch", "minecraft"
    provider_id: str                  # snowflake / UUID
    provider_username: str
    avatar_url: str | None
    access_token: str                 # encrypté
    refresh_token: str | None         # encrypté
    token_expires: datetime | None
    created_at: datetime
    last_sync: datetime | None

class GuildMembership(Base):
    """Optionnel — pour vérifier qu'un joueur est bien dans le Discord du streamer."""
    id: int
    account_id: int = ForeignKey("linked_accounts.id")
    guild_id: str
    guild_name: str
    roles: list[str]                  # rôles Discord
```

#### Pourquoi chaque provider

| Provider | Usage |
|---|---|
| **Discord** | Identité principale. Vérifier l'appartenance au serveur Discord du streamer. Lié aux rôles (VIP, booster → tiers bonus) |
| **Twitch** | Identifier les viewers/subscribers. Permet au streamer de réserver la génération aux abonnés |
| **Microsoft/Minecraft** | Lier directement le compte Minecraft pour le give automatique d'items sans demander le pseudo |

#### Endpoints OAuth

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/auth/discord/login` | Redirection Discord OAuth |
| `GET` | `/auth/discord/callback` | Callback → JWT |
| `GET` | `/auth/twitch/login` | Redirection Twitch OAuth |
| `GET` | `/auth/twitch/callback` | Callback → JWT |
| `GET` | `/auth/minecraft/login` | Redirection Microsoft OAuth |
| `GET` | `/auth/minecraft/callback` | Callback → JWT + UUID |
| `POST` | `/auth/link` | Lier un provider supplémentaire au client existant |
| `DELETE` | `/auth/link/{provider}` | Délier |
| `GET` | `/auth/me` | Profil connecté (providers, client info, points) |

#### Dashboard Streamer — Vue Liens Sociaux

```
┌──────────────────────────────────────────────┐
│  🔗 Connexions Sociales                      │
├──────────────────────────────────────────────┤
│  ✅ Discord — ChunkDMesh Community           │
│     Membres liés: 42 / 1,200 membres         │
│     Rôle requis: Aucun (optionnel)           │
│     [Déconnecter] [Changer serveur]          │
│                                              │
│  ✅ Twitch — yoanndev90                      │
│     28 viewers liés                          │
│     Réserver aux subs: [Oui/Non]             │
│                                              │
│  ❌ Minecraft — Non connecté                 │
│     [Se connecter] (nécessaire pour give)    │
└──────────────────────────────────────────────┘
```

#### Accès par Rôles Discord (Optionnel)

Le streamer peut configurer des seuils d'accès basés sur les rôles :

```json
{
  "discord_guild_id": "123456789",
  "access_tiers": [
    {"role": "@everyone",     "max_clients": 5,   "trust_tier": 0},
    {"role": "Booster",      "max_clients": 10,  "trust_tier": 1},
    {"role": "VIP",          "max_clients": 20,  "trust_tier": 2},
    {"role": "Moderator",    "max_clients": -1,  "trust_tier": 2}
  ]
}
```

#### Sécurité OAuth

- `access_token` et `refresh_token` encryptés au repos (AES-256-GCM, clé dérivée du secret JWT)
- Revocation : si le joueur quitte le Discord, le serveur peut détecter via `GET /users/@me/guilds` et rétrograder le tiers
- Refresh automatique des tokens avant expiration

### 1.2 Docker One-Click

```yaml
# docker-compose.yml
services:
  chunkdmesh:
    image: chunkdmesh/server
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./config:/app/server/config
    env:
      - CHUNKMESH_HOST=0.0.0.0
      - CHUNKMESH_PORT=8000
```

### 1.2 Système d'Invitation

```
streamer:  POST /admin/invites          → crée un code batch
           GET  /admin/invites          → liste les codes actifs
           DELETE /admin/invites/{code} → révoque un code

joueur:    chunkdmesh invite CHUNK-XXXX-XXXX
           → client résout l'URL serveur, seed, dimension
           → s'authentifie, commence à générer
```

Le code d'invite encode : URL serveur + checksum seed + timestamp expir.
Zero config pour le joueur — `chunkdmesh invite <code>` suffit.

### 1.3 Client Distribuable

- Binary standalone avec pyinstaller (Windows/Mac/Linux)
- `chunkdmesh invite <code> && chunkdmesh run --bg`
- Pas besoin d'installer Python, Java, etc. Tout est téléchargé automatiquement

### 1.5 Client Headless avec OAuth

Le client peut stocker le refresh token → reconnexion automatique sans que le joueur ait à refaire le flow OAuth.

```
chunkdmesh login --discord     # Ouvre le navigateur, callback → token stocké
chunkdmesh run --bg           # Utilise le token stocké, refresh auto
chunkdmesh logout             # Efface le token
```

Le token est stocké dans `~/.config/chunkdmesh/auth.json`, chiffré avec une clé dérivée du matériel (TPM via `tpm2-pytss` ou fallback keyring OS).

### 1.6 Web App pour Streamer (Nouveau)

Dashboard Vue.js/Svelte stand-alone (ou templates Jinja2 enrichies) :

| Page | Contenu |
|---|---|
| `/admin/community` | Leaderboard, stats contributeurs |
| `/admin/cheat` | Flagged regions, mismatches, bans |
| `/admin/invites` | Gestion des codes d'invitation |
| `/admin/export` | Export + items rewards CSV |
| `/admin/live` | Carte temps réel + flux des clients |

---

## 2. Architecture 0-Trust

### 2.1 Modèles DB Étendus

```python
class LinkedAccount(Base):
    """Compte social lié à un client ChunkDMesh."""
    id: int
    client_id: int = ForeignKey("clients.id")
    provider: str                     # "discord", "twitch", "minecraft"
    provider_id: str                  # snowflake / UUID
    provider_username: str
    avatar_url: str | None
    access_token: str                 # encrypté (AES-256-GCM)
    refresh_token: str | None         # encrypté
    token_expires: datetime | None
    created_at: datetime
    last_sync: datetime | None

class GuildMembership(Base):
    """Optionnel — pour vérifier que le joueur est dans le Discord du streamer."""
    id: int
    account_id: int = ForeignKey("linked_accounts.id")
    guild_id: str
    guild_name: str
    roles: list[str]
```

```python
class Client(Base):
    # existant
    id, token, ip, power_score, benchmark_score, last_seen, batches

    # nouveau
    trust_score: float = 1.0          # 0.0 → banni
    tier: int = 0                      # 0=rookie, 1=regular, 2=veteran
    regions_completed: int = 0
    regions_verified: int = 0
    regions_failed: int = 0
    consecutive_good: int = 0
    banned_until: datetime | None = None
    ban_reason: str | None = None
    invite_code: str | None = None     # lien vers le code d'invit
    reward_points: int = 0
    mc_username: str | None = None     # optionnel, pour les rewards

class BlockSample(Base):
    """Échantillon block-level pour cross-validation."""
    id: int
    batch_id: int = ForeignKey("batches.id")
    client_id: int = ForeignKey("clients.id")
    chunk_x: int
    chunk_z: int
    block_x: int                       # local x dans le chunk (0-15)
    block_y: int
    block_z: int                       # local z dans le chunk (0-15)
    declared_block: str                 # "minecraft:diamond_ore"
    declared_biome: str
    created_at: datetime

class InviteCode(Base):
    """Code d'invitation jetable."""
    id: int
    code: str                          # CHUNK-XXXX-XXXX
    server_url: str
    seed_hash: str                     # sha256 du seed, partiel
    created_by: int = ForeignKey("clients.id")
    max_uses: int = None               # None = illimité
    use_count: int = 0
    expires_at: datetime | None
    revoked: bool = False

class Reward(Base):
    """Journal des récompenses attribuées."""
    id: int
    client_id: int = ForeignKey("clients.id")
    batch_id: int = ForeignKey("batches.id")
    points: int
    reason: str                        # "generation", "verification", "referral"
    mc_item: str | None = None         # optionnel — "minecraft:diamond 5"
    created_at: datetime
    claimed: bool = False

class VerificationResult(Base):
    """Résultat de vérification croisée."""
    id: int
    batch_id: int = ForeignKey("batches.id")
    primary_client_id: int = ForeignKey("clients.id")
    verifier_client_id: int = ForeignKey("clients.id")
    status: str                        # "pending", "match", "mismatch"
    mismatch_count: int = 0
    resolved_by: int | None = None     # tiebreaker client_id
    created_at: datetime
```

### 2.2 Nouveaux Statuts Batch

```python
Batch.status = [
    "pending",       # pas encore assigné
    "assigned",      # assigné à un client
    "working",       # upload en cours
    "completed",     # uploadé, hash OK
    "verifying",     # en vérification croisée
    "validated",     # vérifié, OK
    "disputed",      # mismatch détecté
    "flagged",       # anomalie statistique
    "hash_error",    # hash mismatch
    "banned",        # assigné à un client banni
]
```

### 2.3 Block Sampling — Protocole de Preuve

#### Génération des échantillons

Quand un client complète une region (`POST /tasks/submit`) :

1. Le serveur choisit **aléatoirement 10-50 positions `(cx, cz, lx, ly, lz)`** dans les chunks de la region
2. Stocke ces positions dans `BlockSample` avec status `"pending"`
3. Retourne au client la liste des positions à sonder
4. Le client lit son `.mca` local, répond pour chaque position :
   ```json
   {"samples": [{"cx": 3, "cz": 5, "lx": 7, "ly": 45, "lz": 3,
                 "block": "minecraft:diamond_ore", "biome": "minecraft:plains"}]}
   ```
5. Le serveur stocke les réponses dans `BlockSample`

#### Cross-validation par un autre client

Quand la même region est assignée à un 2ème client (vérification) :

1. Le serveur lui envoie **les mêmes positions** + peut-être de nouvelles
2. Compare les réponses
   - 100% match → validated ✅
   - Mismatch → `"disputed"`, réassigné à un 3ème

#### Évolution possible : preuve calculatoire

Le client peut aussi prouver qu'il possède bien le monde complet sans tout renvoyer :

- **Merkle tree** sur les chunks de la region
- Le serveur demande : "prouve-moi le contenu du chunk (3, 5) sans tout m'envoyer"
- Le client renvoie le Merkle proof (quelques KB)
- Vérification côté serveur : O(log n)

### 2.4 Détection Statistique (Anomalies)

Check automatique dans `submit_tasks` avant même la cross-validation :

| Analyse | Seuil suspect |
|---|---|
| Densité diamond_ore | > 3x moyenne attendue pour le biome |
| Densité ancient_debris (nether) | > 2x |
| Répartition Y des blobs | Si tout le diamant est aux mêmes couches Y |
| Palette biomes incohérente | Biome océan à (0, 0) ne peut pas exister |
| Nombre de chunks dans `.mca` | Toujours 1024 chunks, si moins → chunk manquant |
| Taille du fichier | Trop petit ou trop grand pour une region standard |

```python
def analyze_anomalies(mca_data: bytes, region_x: int, region_z: int, seed: int) -> AnomalyReport:
    score = 0.0
    flags = []

    chunks = parse_mca_chunks(mca_data)
    for chunk in chunks:
        ore_count = count_block(chunk, "minecraft:diamond_ore")
        expected = expected_ore_density(seed, chunk.cx, chunk.cz, "diamond_ore")
        ratio = ore_count / max(expected, 1)
        if ratio > 3.0:
            score += 0.3
            flags.append(f"diamond_ore x{ratio:.1f} at chunk ({chunk.cx}, {chunk.cz})")

    return AnomalyReport(score=score, threshold=1.0, flagged=score >= 1.0, details=flags)
```

### 2.5 Système de Score de Confiance (Trust)

```
Tier 0 — Rookie (score 0.0 → 0.3)
  - Chaque région = vérifiée par 2 autres clients (100% overhead)
  - Block sampling obligatoire, 50 positions
  - Max 3 régions simultanées

Tier 1 — Regular (score 0.3 → 0.7)
  - 1 vérification sur 3 régions (33% overhead)
  - Block sampling 20 positions
  - Max 5 régions simultanées

Tier 2 — Veteran (score 0.7 → 1.0)
  - 1 vérification sur 10 régions (10% overhead)
  - Block sampling 5 positions
  - Max 10 régions simultanées
  - Prioritaire dans la file d'attente
```

**Évolution du score** :

| Action | Impact |
|---|---|
| Region complétée + vérifiée OK | +0.05 |
| Verification match | +0.02 |
| Benchmarks élevés | +0.01 |
| Temps de connexion continu (>1h) | +0.01/10min |
| Mismatch (était le tricheur) | -0.30 |
| Mismatch (était l'honnête) | +0.05 |
| Flagged anomaly confirmée | -0.50 |
| Timeout / abandon batch | -0.10 |
| Power score suspect (benchmark anormal) | -0.20 |

### 2.6 Réattribution & Résolution des Disputes

```
                    ┌─────────────┐
                    │  completed  │
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              ↓                         ↓
        [vérification OK]         [mismatch détecté]
              ↓                         ↓
        ┌──────────┐             ┌──────────────┐
        │validated │             │  disputed     │
        └──────────┘             └──────┬───────┘
                                        │
                         ┌──────────────┴──────────────┐
                         ↓                             ↓
                  [assigner 3ème client]      [block sampling]
                         ↓
              ┌──────────┴──────────┐
              ↓                     ↓
        2/3 concordent ← → aucun consensus
              ↓                     ↓
        validé ❌              gardé disputed
        + dissident penalisé     + notification admin
```

### 2.7 Ban System

```python
# Nouveau endpoint
POST /admin/bans
{
    "client_id": 42,
    "reason": "diamond_ore density x12",
    "duration_hours": 72,
    "evidence": "flag_1245"
}

GET /admin/bans
DELETE /admin/bans/{id}
```

- Ban IP, ban client_id, ban plage
- Broadcast notification aux clients connectés (optionnel)
- Un client banni voit son token révoqué instantanément
- Pas de reconnexion possible avec le même token

---

## 3. Système de Récompenses

### 3.1 Reward Points

Chaque action contributive = points :

| Action | Points |
|---|---|
| Region complétée (taille standard, 1024 chunks) | 100 points |
| Vérification d'une region | 50 points |
| Anomalie détectée (vrai positif) | 200 points |
| Parrainage (invite + nouvelle recrue) | 50 points |
| Benchmarks soumis | 10 points |
| Tile uploadé | 1 point/tile |
| Bonus temps réel (par heure connecté) | 5 points |

### 3.2 Leaderboard

```
GET /admin/leaderboard

→ {
    "leaderboard": [
        {"rank": 1, "mc_username": "Technoblade", "points": 15420,
         "regions": 42, "tier": 2, "reward_items": "diamond 32"},
        {"rank": 2, "mc_username": "Dream", "points": 12800,
         "regions": 35, "tier": 2, "reward_items": "netherite_ingot 8"},
    ],
    "my_rank": {"rank": 7, "points": 5400},
    "total_contributors": 23,
    "total_chunks_generated": 152000
}
```

Pages séparées :
- **All-time** : total points de tous les temps
- **Session courante** : depuis le début de la génération en cours
- **Mois** / **Semaine**
- Par type de contribution (génération vs vérification vs anomalies)

### 3.3 Items Rewards — Interface Streamer

```python
# Nouveaux endpoints
POST /admin/rewards/define
{
    "name": "Top Contributor",
    "item": "minecraft:diamond",
    "quantity": 32,
    "min_points": 5000,
    "max_winners": 3,
    "schedule": "end_of_generation"  # ou "weekly", "manual"
}

POST /admin/rewards/give
{
    "client_id": 7,
    "item": "minecraft:diamond",
    "quantity": 16,
    "reason": "detected anomaly #42"
}

GET /admin/rewards/history
GET /admin/rewards/pending    # items à donner, pas encore attribués
```

### 3.4 Intégration Minecraft (Give Automatique)

Option 1 : **Fichier CSV** → streamer importe avec un datapack / command blocks

```
/chunkdmesh_rewards.csv:
mc_username,item,quantity,reason,batch_id
Technoblade,minecraft:diamond,32,"Top gen #42",127
```

Option 2 : **RCON direct** (le serveur ChunkDMesh se connecte au serveur Minecraft via RCON)

```python
# Nouveau module server/reward_giver.py
class RewardGiver:
    async def give_item(self, mc_username: str, item: str, quantity: int):
        rcon.run(f"/give {mc_username} {item} {quantity}")
        # Log dans Reward.claimed = True
```

Option 3 : **Webhook** vers un plugin Minecraft

```
POST https://mc-server.example.com/rewards
Authorization: Bearer shared-secret
{
    "username": "Technoblade",
    "item": "minecraft:diamond",
    "quantity": 32,
    "reason": "ChunkDMesh Top Contributor"
}
```

### 3.5 Visualisation Dashboard

```
┌──────────────────────────────────────────────────┐
│  🏆 ChunkDMesh Community — Live                 │
├──────────────────────────────────────────────────┤
│                                                  │
│  Classement Génération (session)                 │
│  ┌──────────────┬────────┬──────┬──────────┐     │
│  │ Joueur       │Chunks  │Rgns  │ Points   │     │
│  ├──────────────┼────────┼──────┼──────────┤     │
│  │ 🥇 Techno    │152,000 │ 142  │ 14,200   │     │
│  │ 🥈 Dream     │128,000 │ 110  │ 11,000   │     │
│  │ 🥉 George    │ 95,000 │  87  │  8,700   │     │
│  │ 4. Sapnap    │ 72,000 │  63  │  6,300   │     │
│  └──────────────┴────────┴──────┴──────────┘     │
│                                                  │
│  Rewards à distribuer :                          │
│  🎁 Technoblade → diamond x32 (Top Gen)          │
│  🎁 Dream → netherite_ingot x8 (Best Verif)      │
│                                                  │
│  [Distribuer] [Exporter CSV] [Personnaliser]     │
└──────────────────────────────────────────────────┘
```

---

## 4. Nouveaux Endpoints API

### Auth & Invites

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/register` | Nouveau client avec code d'invite |
| `GET` | `/auth/whoami` | Infos client + rank + points |
| `POST` | `/admin/invites` | Créer code d'invitation |
| `GET` | `/admin/invites` | Lister codes |
| `DELETE` | `/admin/invites/{code}` | Révoquer |

### Tasks & Vérification

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/tasks/verify` | Block sampling — le serveur envoie positions, le client répond |
| `GET` | `/tasks/{id}/status` | Status détaillé d'un batch |
| `POST` | `/admin/batches/{id}/retry` | Forcer réassignation |
| `DELETE` | `/admin/batches/{id}` | Supprimer un batch |

### Trust & Bans

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/admin/clients` | Liste tous les clients + tiers + trust |
| `GET` | `/admin/clients/{id}` | Détail client (historique, flags) |
| `POST` | `/admin/bans` | Bannir un client |
| `GET` | `/admin/bans` | Liste des bans actifs |
| `DELETE` | `/admin/bans/{id}` | Débannir |
| `GET` | `/admin/flags` | Regions flagged + anomalies |
| `POST` | `/admin/flags/{id}/resolve` | Résoudre manuellement |

### Récompenses

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/admin/leaderboard` | Classement (points, chunks, régions) |
| `POST` | `/admin/rewards/define` | Créer un palier de récompense |
| `POST` | `/admin/rewards/give` | Give manuel |
| `GET` | `/admin/rewards/history` | Historique |
| `GET` | `/admin/rewards/pending` | Rewards pas encore donnés |
| `POST` | `/admin/rewards/export` | CSV des rewards à distribuer |
| `POST` | `/admin/rewards/deliver` | Give via RCON direct |

### Community (nouveau)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/admin/community` | Page dashboard communautaire |
| `GET` | `/admin/community/stats` | Stats globales (total chunks, joueurs) |
| `GET` | `/admin/community/activity` | Flux live des événements |

---

## 5. Implémentation — Ordre Recommandé

### Phase 1 — Fondations (Semaine 1)
- Dockerfile + docker-compose.yml
- Modèles DB étendus (invite, reward, block_sample, verification_result, linked_account)
- `POST /auth/register` avec code d'invite
- Système d'invitation complet
- Migration des clients existants vers le nouveau modèle

### Phase 2 — OAuth Social (Semaine 2)
- Discord OAuth : login, callback, refresh, guild membership check
- Twitch OAuth : login, callback, subscriber check
- Microsoft OAuth : login, callback, UUID récupération
- Encryptage des tokens (`fernet` ou `cryptography`)
- Client `chunkdmesh login --discord` avec keyring
- Dashboard connexions sociales

### Phase 3 — 0-Trust Core (Semaine 3)
- Block sampling endpoint (`POST /tasks/verify`)
- Vérification cross-client
- Détection statistique des anomalies (analyse `.mca`)
- Trust tiers + scoring
- Ban system

### Phase 4 — Rewards (Semaine 4)
- Reward points system
- Leaderboard endpoints
- Dashboard communauté
- Export CSV / RCON give
- Liens Discord pseudo → Minecraft UUID pour give automatique

### Phase 5 — Polish (Semaine 5)
- Rate limiting
- CORS config
- Healthcheck DB
- Pagination heatmap
- Tests partout (dont tests OAuth mockés)
- Dashboard Web enrichi

---

## 6. Métriques de Succès

| Métrique | Cible |
|---|---|
| Temps d'onboarding (code → 1er chunk) | < 2 minutes |
| Taux de triche non détectée | < 0.1% |
| Overhead vérification (moyen) | < 25% (pondéré par tiers) |
| Faux positifs (région flagged injustement) | < 1% |
| Rétention contributeurs | > 60% après 1 semaine |
| Points distribués / 1000 chunks | 100 ± 10 |

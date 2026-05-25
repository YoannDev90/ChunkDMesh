# CHUNK-D-MESH

```text
                                                                                                         
   _|_|_|  _|    _|  _|    _|  _|      _|  _|    _|  _|_|_|    _|      _|  _|_|_|_|    _|_|_|  _|    _|  
 _|        _|    _|  _|    _|  _|_|    _|  _|  _|    _|    _|  _|_|  _|_|  _|        _|        _|    _|  
 _|        _|_|_|_|  _|    _|  _|  _|  _|  _|_|      _|    _|  _|  _|  _|  _|_|_|      _|_|    _|_|_|_|  
 _|        _|    _|  _|    _|  _|    _|_|  _|  _|    _|    _|  _|      _|  _|              _|  _|    _|  
   _|_|_|  _|    _|    _|_|    _|      _|  _|    _|  _|_|_|    _|      _|  _|_|_|_|  _|_|_|    _|    _|  
                                                                                                
```

A minimal, opinionated toolkit for distributed chunk-based mesh exchange (P2P).

Petit projet visant à expérimenter la distribution et l'allocation de "chunks" dans un réseau maillé.

## Caractéristiques

- Échange pair-à-pair de chunks
- Allocation/verification côté orchestrateur
- Configuration JSON/JSON5 légère

## Prérequis

- Python 3.10+ (recommandé)
- Voir `requirements.txt` pour les dépendances

## Installation rapide

```sh
  python -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
```

## Usage

- L'orchestrateur principal se lance depuis `orchestrator/main.py`.
- La configuration se trouve dans le dossier `config/`.

Exemple :

```sh
  python -m orchestrator.main
```

## Contribuer

- Ouvrez une issue pour discuter des fonctionnalités.
- PR bienvenues ; gardez les changements petits et documentés.

## Licence

Ce projet est fourni sous licence Apache v2.0 (voir le fichier `LICENSE`).

# Coach d'ouvertures d'échecs 

L'agent guide le joueur à partir de la position courante en combinant :
- la théorie des ouvertures (API Lichess Opening Explorer) ;
- le contexte historique (Wikibooks Chess Opening Theory, indexé dans Milvus) ;
- des vidéos explicatives (YouTube Data API) ;
- une évaluation Stockfish quand la partie sort de la théorie.

## Stack

| Couche | Technologies |
|---|---|
| Frontend | Angular, material-chessboard (ngx-chessboard) |
| Backend | FastAPI, LangGraph |
| Données | MongoDB, Milvus |
| Moteur | Stockfish |
| Orchestration | Docker Compose |

## Structure

```
.
├── backend/            API FastAPI (agent LangGraph)
│   ├── app/
│   │   ├── main.py         point d'entrée FastAPI
│   │   ├── config.py       configuration par variables d'environnement
│   │   ├── schemas.py      modèles de réponse (Pydantic)
│   │   ├── api/v1/         routes versionnées (healthcheck, moves, evaluate)
│   │   ├── core/           validation FEN (python-chess), erreurs métier
│   │   └── services/       clients Lichess et Stockfish
│   ├── tests/              tests pytest (Lichess simulé, Stockfish réel)
│   ├── requirements.txt    dépendances aux versions figées
│   ├── requirements-dev.txt
│   └── Dockerfile          Python 3.12.15 + Stockfish 15.1 figés
├── frontend/           Application Angular (à venir)
├── docker-compose.yml
├── .env                configuration locale (non versionnée, à créer)
└── README.md
```

## Démarrage

Prérequis : Docker et Docker Compose.

1. Créer un fichier `.env` à la racine avec au minimum le token Lichess
   (voir [Configuration](#configuration) pour les autres variables) :

   ```bash
   echo "LICHESS_TOKEN=lip_xxxxxxxx" > .env
   ```

2. Lancer :

   ```bash
   docker compose up --build
   ```

Puis ouvrir :

- http://localhost:8000 --> `{"message": "Hello World"}`
- http://localhost:8000/api/v1/healthcheck --> `{"status": "ok", ...}`
- http://localhost:8000/docs --> documentation Swagger

## Endpoints

La FEN se passe directement dans l'URL. Les espaces peuvent être encodés
(`%20`) ou remplacés par `_` (comme sur Lichess).

| Endpoint | Rôle |
|---|---|
| `GET /api/v1/healthcheck` | État du service |
| `GET /api/v1/moves/{fen}?database=masters\|lichess` | Coups théoriques Lichess (statistiques, ouverture ECO). Hors théorie, ou si Lichess est indisponible, la réponse contient l'évaluation Stockfish (`source: "stockfish"`). |
| `GET /api/v1/evaluate/{fen}?depth=18&multipv=3` | Évaluation Stockfish : score en centipawns (ou mat en N) du point de vue des Blancs, meilleur coup, meilleures lignes |

Exemple :

```bash
curl "localhost:8000/api/v1/moves/rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR_b_KQkq_-_0_1"
curl "localhost:8000/api/v1/evaluate/rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR_b_KQkq_-_0_1"
```

Codes d'erreur : `422` FEN invalide · `502` token Lichess absent/invalide ·
`503` Lichess ou Stockfish indisponible (avec `Retry-After` en cas de limite de requêtes).

### Lichess : token et limites de requêtes

L'Opening Explorer exige un token personnel : le créer sur
https://lichess.org/account/oauth/token (aucune permission à cocher) puis le
mettre dans `LICHESS_TOKEN`.

Pour respecter les règles d'usage de Lichess, le service envoie une seule
requête à la fois, met les réponses en cache (1 h par défaut) et, après une
réponse `429`, n'appelle plus Lichess pendant au moins 60 s.

## Tests

```bash
docker compose build backend
docker run --rm -v "$PWD/backend:/src" echecs-backend \
  sh -c "pip install -q -r /src/requirements-dev.txt && cd /src && pytest"
```


## Configuration

Toute la configuration passe par des variables d'environnement, lues depuis le
fichier `.env` à la racine (non versionné). Toutes les variables ont une valeur
par défaut, sauf `LICHESS_TOKEN`.

| Variable | Défaut | Rôle |
|---|---|---|
| `APP_ENV` | `development` | Environnement d'exécution |
| `BACKEND_PORT` | `8000` | Port d'écoute de FastAPI dans le conteneur |
| `BACKEND_HOST_PORT` | `8000` | Port exposé sur la machine hôte |
| `LICHESS_TOKEN` | *(vide)* | Token personnel Lichess (obligatoire pour `/moves`) |
| `LICHESS_DATABASE` | `masters` | Base par défaut : `masters` ou `lichess` |
| `LICHESS_TIMEOUT_SECONDS` | `5` | Timeout des appels Lichess |
| `LICHESS_CACHE_TTL_SECONDS` | `3600` | Durée du cache des réponses Lichess |
| `THEORY_MIN_GAMES` | `10` | Seuil de parties en dessous duquel on est « hors théorie » |
| `STOCKFISH_DEPTH` | `18` | Profondeur d'analyse par défaut |
| `STOCKFISH_TIME_LIMIT_SECONDS` | `2` | Temps max d'analyse |
| `STOCKFISH_MULTIPV` | `3` | Nombre de meilleures lignes |

### Ports

| Service | Port hôte | Statut |
|---|---|---|
| Backend FastAPI | 8000 | actif |
| Frontend Angular | 4200 | à venir |
| MongoDB | 27017 | à venir |
| Milvus | 19530 | à venir |

Arrêt : `docker compose down`

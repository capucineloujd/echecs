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
│   │   └── api/v1/         routes versionnées (healthcheck...)
│   ├── requirements.txt    dépendances aux versions figées
│   └── Dockerfile          Python 3.12.15 figé
├── frontend/           Application Angular (à venir)
├── docker-compose.yml
├── .env.example
└── README.md
```

## Démarrage

Prérequis : Docker et Docker Compose.

```bash
cp .env.example .env
docker compose up --build
```

Puis ouvrir :

- http://localhost:8000 --> `{"message": "Hello World"}`
- http://localhost:8000/api/v1/healthcheck --> `{"status": "ok", ...}`
- http://localhost:8000/docs --> documentation Swagger


## Configuration

Toute la configuration passe par des variables d'environnement (fichier `.env`,
voir `.env.example`).

| Variable | Défaut | Rôle |
|---|---|---|
| `APP_ENV` | `development` | Environnement d'exécution |
| `BACKEND_PORT` | `8000` | Port d'écoute de FastAPI dans le conteneur |
| `BACKEND_HOST_PORT` | `8000` | Port exposé sur la machine hôte |

### Ports

| Service | Port hôte | Statut |
|---|---|---|
| Backend FastAPI | 8000 | actif |
| Frontend Angular | 4200 | à venir |
| MongoDB | 27017 | à venir |
| Milvus | 19530 | à venir |

Arrêt : `docker compose down`

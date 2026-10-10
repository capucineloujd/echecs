# Coach d'ouvertures d'échecs — POC FFE

Agent IA d'entraînement aux ouvertures pour les jeunes espoirs de la FFE.
L'agent guide le joueur à partir de la position courante (FEN) en combinant :

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
├── backend/            API FastAPI (agent LangGraph à venir)
│   ├── app/main.py
│   ├── requirements.txt
│   └── Dockerfile
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

- http://localhost:8000 → `{"message": "Hello World"}`
- http://localhost:8000/health → `{"status": "ok"}`
- http://localhost:8000/docs → documentation Swagger

Arrêt : `docker compose down`

## Avancement

- [x] Étape 1 — Structure du projet, dépôt Git, service FastAPI « Hello World »
- [ ] Frontend Angular avec échiquier interactif
- [ ] MongoDB et Milvus dans le compose
- [ ] Agent LangGraph (Lichess, Stockfish, RAG, YouTube)

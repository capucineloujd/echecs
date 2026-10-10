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
│   │   ├── api/v1/         routes versionnées (healthcheck, moves, evaluate, vector-search)
│   │   ├── core/           validation FEN (python-chess), erreurs métier
│   │   ├── rag/            découpage, catalogue des ouvertures, graphe LangGraph
│   │   └── services/       Lichess, Stockfish, embeddings, Milvus
│   ├── scripts/            fetch_wikichess.py (collecte), ingest.py (indexation Milvus)
│   ├── data/               catalogue des ouvertures + articles bruts (data/raw)
│   ├── tests/              tests pytest (services externes simulés, Stockfish réel)
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
   docker compose up --build -d
   ```

3. Au premier lancement, indexer les articles dans Milvus (télécharge le
   modèle d'embedding, ~1,2 Go, puis le garde en cache dans un volume Docker) :

   ```bash
   docker compose run --rm backend python -m scripts.ingest
   docker compose restart backend
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

| `GET /api/v1/vector-search?query=...&opening=...&top_k=5` | Recherche vectorielle dans les articles d'ouvertures (Milvus). Renvoie les passages les plus pertinents avec leur source, et un champ `context` prêt pour un LLM. |

Codes d'erreur : `422` FEN invalide · `502` token Lichess absent/invalide ·
`503` Lichess ou Stockfish indisponible (avec `Retry-After` en cas de limite de requêtes).

### Lichess : token et limites de requêtes

L'Opening Explorer exige un token personnel : le créer sur
https://lichess.org/account/oauth/token (aucune permission à cocher) puis le
mettre dans `LICHESS_TOKEN`.

Pour respecter les règles d'usage de Lichess, le service envoie une seule
requête à la fois, met les réponses en cache (1 h par défaut) et, après une
réponse `429`, n'appelle plus Lichess pendant au moins 60 s.

## RAG : recherche vectorielle sur les ouvertures

### Données

10 ouvertures parmi les plus jouées (italienne, espagnole, écossaise,
sicilienne, française, Caro-Kann, scandinave, gambit dame, est-indienne,
anglaise), chacune avec deux sources complémentaires :

- **Wikibooks *Chess Opening Theory*** (EN) : théorie coup par coup et plans ;
- **Wikipédia FR** : histoire, contexte, joueurs emblématiques.

Le catalogue (`backend/data/openings_catalog.json`) définit pour chaque
ouverture son code ECO, ses coups, ses alias de recherche et ses pages
sources. Les articles bruts sont versionnés dans `backend/data/raw/` :
l'ingestion fonctionne sans réseau. Pour les retélécharger :

```bash
docker compose run --rm backend python -m scripts.fetch_wikichess
```

Textes sous licence CC BY-SA (Wikibooks / Wikipédia) : chaque passage renvoyé
par l'API cite l'URL de sa source.

### Pipeline

1. **Découpage** (`app/rag/chunking.py`) : par section MediaWiki (le chemin
   `Variantes > La variante Winawer` est conservé), paragraphes regroupés
   jusqu'à 1 200 caractères, avec reprise du dernier paragraphe pour garder
   le fil. Les sections sans valeur (références, bibliographie, liens,
   tableaux) sont écartées. Résultat : ~180 passages.
2. **Embeddings** : `Qwen/Qwen3-Embedding-0.6B` (sentence-transformers,
   dimension 1024, multilingue : une question en français trouve aussi les
   passages Wikibooks en anglais). Le texte vectorisé est préfixé par
   l'ouverture et la section pour qu'un passage isolé reste rattaché à son
   contexte.
3. **Index Milvus** : collection `opening_chunks`, index HNSW en similarité
   cosinus, champ `opening_slug` indexé pour le filtrage.

### Performances et pièges rencontrés

- Le modèle est stocké en **bfloat16**, très lent sur CPU : on le charge en
  **float32**.
- Laisser torch prendre tous les cœurs **fait tomber Milvus** (il perd son bail
  etcd faute de CPU) : `EMBEDDING_THREADS=4` par défaut.
- Ingestion des ~180 passages : ~9 min sur CPU dans Docker (à faire une
  seule fois). Une requête : ~0,3 s.

### Qualité de la recherche

Une consigne de requête spécifique aux échecs (recommandée par Qwen3-Embedding)
améliore les scores. Constats sur quelques questions types :

- ✅ question sur une ouverture nommée (« histoire de la partie espagnole »,
  « variante Winawer ») : passages pertinents, grâce au filtrage par ouverture ;
- ⚠️ question thématique sans nom d'ouverture (« fianchetto du fou roi contre
  d4 ») : résultats approximatifs, quelques longs passages génériques de la
  française ressortent souvent.

Dans l'agent final, l'ouverture sera presque toujours connue (nom renvoyé par
Lichess pour la position courante) : c'est le cas favorable. Pistes
d'amélioration : recherche hybride (BM25 + vecteurs, supportée par Milvus),
découpage plus fin des longues sections, enrichissement du corpus.

### Graphe LangGraph (`app/rag/graph.py`)

```
detect_opening ──► retrieve ──┬──► format_results ──► END
                      ▲       │
                      └─ widen_search  (si le filtre ne trouve rien de pertinent)
```

- `detect_opening` reconnaît l'ouverture citée dans la question (« la
  Ruy Lopez », « défense caro kann »…) et restreint la recherche à celle-ci ;
- `retrieve` vectorise la question et interroge Milvus ;
- `widen_search` relance la recherche sans filtre si rien ne dépasse le seuil ;
- `format_results` écarte les scores faibles et les doublons, et prépare le
  contexte pour le futur nœud LLM.

Exemple :

```bash
curl -G localhost:8000/api/v1/vector-search --data-urlencode "query=Quelle est l'histoire de la partie espagnole ?"
```

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
| `MILVUS_URI` | `http://milvus:19530` | Adresse de Milvus (nom du service dans le réseau Docker) |
| `MILVUS_HOST_PORT` | `19530` | Port Milvus exposé sur la machine hôte |
| `EMBEDDING_MODEL` | `Qwen/Qwen3-Embedding-0.6B` | Modèle sentence-transformers |
| `EMBEDDING_THREADS` | `4` | Threads CPU de torch (voir ci-dessous) |
| `EMBEDDING_QUERY_INSTRUCTION` | consigne « chess » | Consigne ajoutée aux requêtes (pas aux documents) |
| `RAG_TOP_K` | `5` | Nombre de passages renvoyés par défaut |
| `RAG_MIN_SCORE` | `0.35` | Similarité cosinus minimale d'un passage |
| `CHUNK_MAX_CHARS` | `1200` | Taille maximale d'un passage |

### Ports

| Service | Port hôte | Statut |
|---|---|---|
| Backend FastAPI | 8000 | actif |
| Frontend Angular | 4200 | à venir |
| MongoDB | 27017 | à venir |
| Milvus | 19530 | actif |

etcd et MinIO (stockage interne de Milvus) ne sont pas exposés sur la machine :
ils ne communiquent qu'à l'intérieur du réseau Docker, ce qui évite tout
conflit sur les ports 2379, 9000 et 9001.

Arrêt : `docker compose down`

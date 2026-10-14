# Coach d'ouvertures d'échecs 

L'agent (LLM local Qwen3 via Ollama, orchestré par LangGraph) analyse la position courante,
choisit lui-même ses sources et rédige un conseil adapté à un jeune joueur, en combinant :
- la théorie des ouvertures (API Lichess Opening Explorer) ;
- le contexte historique (Wikibooks Chess Opening Theory, indexé dans Milvus) ;
- des vidéos explicatives (YouTube Data API) ;
- une évaluation Stockfish quand la partie sort de la théorie.

## Stack

| Couche | Technologies |
|---|---|
| Frontend | Angular 22, ngx-chess-board, chess.js, nginx |
| Backend | FastAPI, LangGraph |
| LLM | Ollama + Qwen3 8B en local ; Mistral en option |
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
│   │   ├── api/v1/         routes versionnées (healthcheck, moves, evaluate, openings, vector-search, videos)
│   │   ├── core/           validation FEN (python-chess), erreurs métier
│   │   ├── agent/          agent coach : outils, prompt, graphe LangGraph (tool calling), streaming
│   │   ├── rag/            découpage, catalogue des ouvertures, graphe LangGraph de recherche
│   │   └── services/       logique métier : analyse de position (théorie ou moteur), Lichess,
│   │                       Stockfish, embeddings, Milvus, YouTube, cache MongoDB
│   ├── scripts/            fetch_wikichess.py (collecte), ingest.py (indexation Milvus)
│   ├── data/               catalogue des ouvertures + articles bruts (data/raw)
│   ├── tests/              tests pytest (services externes simulés, Stockfish réel)
│   ├── requirements.txt    dépendances aux versions figées
│   ├── requirements-dev.txt
│   └── Dockerfile          Python 3.12.15 + Stockfish 15.1 figés
├── frontend/           Application Angular
│   ├── src/app/
│   │   ├── core/           services HTTP, état de la partie (GameStore), recommandations (CoachStore)
│   │   ├── board/          enveloppe de ngx-chess-board
│   │   └── panel/          coups suggérés, conseil du coach, fiche de l'ouverture, vidéos, coups joués
│   ├── nginx/              config nginx (fichiers statiques + proxy /api vers le backend)
│   ├── proxy.conf.json     proxy /api pour `npm start` en développement
│   └── Dockerfile          build Node 24.18.1, service nginx 1.30.0
├── docker-compose.yml
├── .env                configuration locale (non versionnée, à créer)
└── README.md
```


### Installation et démarrage - Prérequis

| Élément | Détail |
|---|---|
| Docker | Docker Desktop (ou Engine ≥ 25) avec Compose v2.20+ (`docker compose version`) |
| Mémoire Docker | **12 Go minimum** |
| Disque | ~env. 8 Go : images (env.5,5 Go) + modèle d'embedding (1,2 Go) + données |
| Ports libres | 4200 (interface), 8000 (API), 27017 (MongoDB), 19530 (Milvus) |
| Token Lichess | Obligatoire |
| Ollama | Pour le conseil du coach |
| Clé YouTube | Facultative |


### Configurer

```bash
echo "LICHESS_TOKEN=lip_xxx" > .env
echo "YOUTUBE_API_KEY=AIza..." >> .env
```

### Installer Ollama (sur la machine, hors Docker)

```bash
brew install ollama && brew services start ollama
ollama pull qwen3:8b
```

### Construire et lancer

```bash
docker compose up --build -d
```
les 6 services doivent apparaître `healthy` :

```bash
docker compose ps
```

### Indexer les articles (premier lancement, ou après `down -v`)

```bash
docker compose stop backend
docker compose run --rm backend python -m scripts.ingest
docker compose up -d backend
```

### Ouvrir

- http://localhost:4200 --> l'interface (échiquier + recommandations de l'agent)
- http://localhost:8000/docs --> documentation Swagger de l'API
- http://localhost:8000/api/v1/healthcheck --> `{"status": "ok", ...}`

### Arrêter / relancer

| Commande | Effet |
|---|---|
| `docker compose stop` | Arrête les conteneurs |
| `docker compose up -d` | Relance (30 s jusqu'à `healthy`, sans ingestion ni téléchargement) |
| `docker compose down` | Supprime les conteneurs mais garde les données |
| `docker compose down -v` | Supprime aussi les volumes : index Milvus, cache, modèle |

## Endpoints

La FEN se passe directement dans l'URL. Les espaces peuvent être encodés
(`%20`) ou remplacés par `_` (comme sur Lichess).

| Endpoint | Rôle |
|---|---|
| `GET /api/v1/healthcheck` | État du service |
| `GET /api/v1/moves/{fen}?database=masters\|lichess` | Coups théoriques Lichess (statistiques, ouverture ECO). Hors théorie, ou si Lichess est indisponible, la réponse contient l'évaluation Stockfish (`source: "stockfish"`). |
| `GET /api/v1/evaluate/{fen}?depth=18&multipv=3` | Évaluation Stockfish : score en centipawns (ou mat en N) du point de vue des Blancs, meilleur coup, meilleures lignes |
| `GET /api/v1/openings` | Ouvertures du catalogue (slug, nom, ECO, coups, FEN), pour le menu de l'interface |
| `GET /api/v1/vector-search?query=...&opening=...&top_k=5&videos=true` | Recherche vectorielle dans les articles d'ouvertures (Milvus). Renvoie les passages les plus pertinents avec leur source, un champ `context` prêt pour un LLM et, si une ouverture est reconnue, des vidéos YouTube. |
| `POST /api/v1/agent/analyze` | Conseil du coach en streaming (SSE). Corps : `{"fen": "...", "moves": ["e4", "e5"], "question": "et si je joue Nxd5 ?"}` (`moves` et `question` facultatifs). Événements `tool_start`, `tool_end`, `token`, puis `done` ou `error`. |
| `GET /api/v1/videos/{opening}` | Vidéos YouTube explicatives pour une ouverture (slug `espagnole`, nom `Défense Caro-Kann` ou nom de variante Lichess `Sicilian Defense: Najdorf Variation`). |

Exemple :

```bash
curl "localhost:8000/api/v1/moves/rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR_b_KQkq_-_0_1"
curl "localhost:8000/api/v1/evaluate/rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR_b_KQkq_-_0_1"
```

Codes erreur : `422` FEN invalide · `502` token Lichess absent/invalide ·
`503` Lichess ou Stockfish indisponible (avec `Retry-After` en cas de limite de requêtes).


## RAG : recherche vectorielle sur les ouvertures

### Données

10 ouvertures parmi les plus jouées (italienne, espagnole, écossaise,
sicilienne, française, Caro-Kann, scandinave, gambit dame, est-indienne,
anglaise), chacune avec deux sources complémentaires :

- **Wikibooks *Chess Opening Theory*** (EN) : théorie coup par coup et plans ;
- **Wikipédia FR** : histoire, contexte, joueurs emblématiques.

### Pipeline

1. Découpage (`app/rag/chunking.py`) : par section MediaWiki (le chemin
   `Variantes > La variante Winawer` est conservé), paragraphes regroupés
   jusqu'à 1 200 caractères, avec reprise du dernier paragraphe pour garder
   le fil. Les sections sans valeur (références, bibliographie, liens,
   tableaux) sont écartées. Résultat : env 180 passages.
2. Embeddings : `Qwen/Qwen3-Embedding-0.6B` (sentence-transformers,
   dimension 1024, multilingue). Le texte vectorisé est préfixé par
   l'ouverture et la section pour qu'un passage isolé reste rattaché à son
   contexte.
3. Index Milvus : collection `opening_chunks`, index HNSW en similarité
   cosinus, champ `opening_slug` indexé pour le filtrage.

### Performances et pièges rencontrés

- Le modèle est stocké en bfloat16, très lent sur CPU == on le charge en
  float32.
- Laisser torch prendre tous les cœurs fait tomber Milvus (il perd son bail
  etcd faute de CPU) : `EMBEDDING_THREADS=4` par défaut.
- Ingestion des env 180 passages : 9 min sur CPU dans Docker

### Qualité de la recherche

Une consigne de requête spécifique aux échecs (recommandée par Qwen3-Embedding)
améliore les scores. Constats sur quelques questions types :

- question sur une ouverture nommée ("histoire de la partie espagnole",
   variante Winawer") : passages pertinents;
- question thématique sans nom d'ouverture ("fianchetto du fou roi contre
  d4") : résultats approximatifs


### Graphe LangGraph (`app/rag/graph.py`)

```
detect_opening ──► retrieve ──┬──► format_results ──► END
                      ▲       │
                      └─ widen_search  (si le filtre ne trouve rien de pertinent)
```

(Branche vidéos en parallèle : voir [Vidéos YouTube](#vidéos-youtube).)

- `detect_opening` reconnaît l'ouverture citée dans la question ("la
  Ruy Lopez", "défense caro kann"…) et restreint la recherche à celle-ci ;
- `retrieve` vectorise la question et interroge Milvus ;
- `widen_search` relance la recherche sans filtre si rien ne dépasse le seuil ;
- `format_results` écarte les scores faibles et les doublons, et prépare le
  contexte pour le futur nœud LLM.

Exemple :

```bash
curl -G localhost:8000/api/v1/vector-search --data-urlencode "query=Quelle est l'histoire de la partie espagnole ?"
```

## Vidéos YouTube

### Recherche et filtrage

1. Requête en français (`<nom> échecs ouverture explication`), puis en anglais
   (`<nom anglais> chess opening explained tutorial`) seulement s'il manque
   des vidéos. `safeSearch=strict` (public de jeunes joueurs).
2. Filtres : vidéo intégrable, pas de live, durée entre 4 et 60 min (exclut
   les Shorts), au moins 5000 vues, titre citant l'ouverture.
3. Classement : popularité (log des vues), ratio de likes, bonus pour le
   français, bonus pour les chaînes favorites (`YOUTUBE_PREFERRED_CHANNELS`),
   bonus pour les titres citant la variante précise ; au plus 2 vidéos par
   chaîne.


### Quotas

Le quota gratuit est de 10 000 unités/jour ; une recherche coûte 100 unités,
le détail des vidéos 1 unité. 

### Cas dégradés

L'endpoint répond toujours `200` ; le champ `status` vaut `ok`, `no_results`,
`quota_exceeded` ou `unavailable`, avec un `message` et un
`fallback_search_url` (recherche YouTube toute prête) à proposer à
l'utilisateur.

### Intégration LangGraph

Le nœud `find_videos` tourne en parallèle de la recherche Milvus, juste
après `detect_opening` :

```
                  ┌──► find_videos ──────────────────────────► END
    detect_opening┤
                  └──► retrieve ──┬──► format_results ──► END
                          ▲       │
                          └─ widen_search
```

## Agent coach (LLM + LangGraph)

### Graphe (`app/agent/graph.py`)

```
  START ──► read_position ──► tools ──► decide ──(outil choisi)──► tools ──┐
                                          ▲  └──("answer")──► answer ──► END
                                          └─────────────────────────────────┘
```

| Nœud | Rôle |
|---|---|
| `read_position` | Lit toujours la position en premier (outil `get_position_moves`) : théorie Lichess si elle est connue, sinon Stockfish |
| `decide` | Le LLM choisit la prochaine étape : un outil (avec son argument) ou `answer`. Sortie structurée (JSON validé par Pydantic) |
| `tools` | Exécute l'outil (`ToolNode` de LangGraph) et renvoie le résultat au LLM |
| `answer` | Le LLM rédige le conseil, streamé vers l'interface |


### Outils : l'agent choisit ses sources

| Outil | Source | Quand le LLM le choisit (consigne du prompt) |
|---|---|---|
| `get_position_moves` | `PositionAnalysisService` : Lichess si la position est dans la théorie, sinon Stockfish | Toujours, au départ (nœud `read_position`) |
| `evaluate_position(move_san)` | Stockfish après un coup | L'élève propose un coup |
| `search_opening_knowledge(query)` | Graphe RAG (Milvus) | L'élève demande les plans, idées, pièges ou l'histoire |
| `find_videos(opening)` | YouTube | L'élève demande des vidéos |

### Choix de conception

Les choix suivants viennent de tests réels sur les positions de démo
(Qwen3 8B, Mac M1 Max) :

| Version testée | Résultat |
|---|---|
| React classique | Le modèle répond souventsans appeler d'outil : il a inventé une "partie italienne" dans une Najdorf, et n'a pas vérifié Nxd5 |
| + lecture de la position garantie au départ | Plus d'ouverture inventée, mais aucun outil supplémentaire appelé |
| + mode "réflexion" de Qwen3 | Vérifie parfois le coup, mais réponses 2 à 4 fois plus lentes et chiffres inventés |
| Qwen3 30B-A3B | N'arrive pas à désactiver sa réflexion : elle apparaît dans la réponse (en anglais), jusqu'à 66 s |
| Décision explicite à chaque tour (version retenue) | Bons outils dans les 5 cas testés, réponses en 8 à 15 s |


### Résultats sur les positions de démo (Qwen3 8B)

| Position et question | Outils choisis | Temps |
|---|---|---|
| Espagnole, "que jouer ?" | lecture de la position | 12 s |
| Piège de l'éléphant, "et si je prends en d5 avec mon cavalier ?" | lecture + Stockfish sur Nxd5 | 14 s |
| Coup du berger | lecture (le mat est trouvé) | 9 s |
| 1.a3 h5 2.Ra2 Rh6 | lecture | 8 s |
| Najdorf, "quels sont les plans ?" | lecture + articles | 14 s |

Limites connues d'un modèle de 8 milliards de paramètres : formulations
parfois approximatives !


### Logique métier séparée de l'API

La décision "théorie ou moteur" (seuil `THEORY_MIN_GAMES`, repli sur
Stockfish si Lichess est indisponible) est dans
`services/position_analysis.py`, utilisée à la fois par la route `/moves`
(qui ne fait plus que valider la FEN et déléguer) et par l'outil
`get_position_moves` de l'agentt


## Interface Angular

### Synchronisation échiquier / agent

```
        coup à la souris            clic sur une suggestion
   ngx-chess-board ──► FEN ──┐      ┌── SAN
                             ▼      ▼
                      GameStore (chess.js) : source de vérité
                       historique, curseur, FEN affichée
                             │
               ┌─────────────┴───────────────┐
               ▼                             ▼
        ChessBoardComponent             CoachStore
        (setFEN si la position          debounce 250 ms + switchMap
         affichée diffère)              ├─ /moves/{fen}       à chaque position
                                        ├─ /evaluate/{fen}    si l'option est cochée
                                        └─ /vector-search     à chaque changement d'ouverture
                                             (passages + vidéos)
```

- ngx-chess-board ne donne que la FEN obtenue après un coup : `GameStore`
  retrouve le coup légal qui y mène avec chess.js (roque, prise en passant,
  promotion). Si aucun ne correspond, l'échiquier est remis sur la position du store.
- `switchMap` annule la requête de la position précédente : une réponse ne peut
  pas s'afficher sur une autre position que celle de l'échiquier.
- Navigation Précédent / Suivant (ou flèches du clavier) dans les coups joués ; jouer un autre
  coup au milieu de la partie remplace la suite.

### Optimisation des appels

| Mécanisme | Effet |
|---|---|
| Debounce 250 ms | Plusieurs coups enchaînés (ou navigation rapide) : un seul appel, pour la position finale |
| Cache LRU par FEN (`RequestCache`) | Revenir sur une position déjà vue ne refait pas d'appel ; requêtes identiques partagées |
| Annulation | Une requête qui n'a plus d'abonné est annulée ; les erreurs ne sont pas mises en cache |
| Contexte par ouverture | `/vector-search` n'est appelé que quand le nom d'ouverture change, pas à chaque coup ; le nom reste affiché hors théorie |
| Vidéos à la demande | Pour une ouverture hors catalogue (ex. "King's Pawn Game"), bouton "Chercher des vidéos" au lieu d'un appel automatique qui consommerait le quota YouTube |
| Stockfish optionnel | `/evaluate` n'est appelé que si "Évaluation Stockfish" est cochée |

### Conseil du coach

Panneau "Conseil du coach" : champ de question facultatif et bouton
"Demander au coach". L'agent n'est appelé qu'à la demande !


## Tests

Backend :

```bash
docker compose build backend
docker run --rm -v "$PWD/backend:/src" echecs-backend \
  sh -c "pip install -q -r /src/requirements-dev.txt && cd /src && pytest"
```

Frontend (Node 24) :

```bash
cd frontend && npm ci && npm test -- --watch=false
```


## Persistance des données

Tous les volumes sont des volumes nommés, déclarés dans `docker-compose.yml`.
Le nom de projet est fixé (`name: echecs`), donc les volumes s'appellent
`echecs_*` quel que soit le nom du dossier cloné.

| Volume | Monté dans | Contenu |
|---|---|---|
| `echecs_hf_models` | `backend:/models` | Modèle Qwen3-Embedding (1,2 Go), téléchargé 1 seule fois |
| `echecs_etcd_data` | `etcd:/etcd` | Métadonnées Milvus |
| `echecs_minio_data` | `minio:/minio_data` | Vecteurs et segments Milvus |
| `echecs_milvus_data` | `milvus:/var/lib/milvus` | Données locales de Milvus |
| `echecs_mongo_data` | `mongodb:/data/db` | Cache des réponses YouTube |


Vérifier :

```bash
docker volume ls --filter name=echecs_
docker volume inspect echecs_minio_data      # Mountpoint, labels du projet compose
```

Tester la persistance en recréant tous les conteneurs :

```bash
docker compose down          # sans -v : les volumes restent
docker compose up -d
# l'index est toujours là (183 passages)
docker exec echecs-backend python -c "from pymilvus import MilvusClient; \
  print(MilvusClient('http://milvus:19530').get_collection_stats('opening_chunks'))"
# le cache YouTube aussi : réponse instantanée, "cached": true, "quota_units_used": 0
curl -s localhost:8000/api/v1/videos/espagnole | grep -o '"cached":[a-z]*'
```

## Démonstration

### Positions préparées

Chaque position se charge depuis le menu des ouvertures puis en cliquant les
coups suggérés, ou en jouant les coups à la souris. Les FEN permettent de
montrer la même chose directement dans l'API (`/docs` ou `curl`).

| # | Position | Coups | Ce qu'elle montre |
|---|---|---|---|
| 1 | Partie espagnole | 1.e4 e5 2.Nf3 Nc6 3.Bb5 | Le cas nominal : théorie des maîtres (162 000 parties, a6 joué à 71 %), fiche de l'ouverture (histoire, Wikibooks + Wikipédia), vidéos en français lisibles dans la page |
| 2 | Sicilienne Najdorf | 1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6 | Nom précis de variante donné par Lichess ("Sicilian Defense: Najdorf Variation") rattaché à la fiche "Défense sicilienne" du catalogue |
| 3 | Attaque Fried Liver | Menu "Partie italienne", puis 3...Nf6 4.Ng5 d5 5.exd5 Nxd5 6.Nxf7 | Un piège classique pour jeunes joueurs : un seul coup possible (Kxf7, 100 %). Le nom d'ouverture reste affiché sur les positions que Lichess ne nomme pas |
| 4 | Piège de l'éléphant | Menu "Gambit dame", puis 2...e6 3.Nc3 Nf6 4.Bg5 Nbd7 5.cxd5 exd5, puis 6.Nxd5?? à la souris | Sortie de la théorie : Stockfish prend le relais, "avantage décisif aux Noirs" (−3,9), ligne Nxd5 Bxd8 Bb4+ : les Noirs gagnent une pièce |
| 5 | Coup du berger | 1.e4 e5 2.Bc4 Nc6 3.Qh5 Nf6?? | Stockfish annonce le mat en 1 (Qxf7#). Jouer Qxf7# : l'interface affiche "Échec et mat" |
| 6 | Ouverture hors catalogue | 1.a3 h5 2.Ra2 Rh6 (à la souris) | Cas dégradés : hors théorie, ouverture absente du catalogue ("Pas encore de fiche"), vidéos seulement sur demande pour économiser le quota |



## Configuration

Toute la configuration passe par des variables d'environnement, lues dans le
fichier `.env` à la racine (non versionné). Variables utiles à l'installation :

| Variable | Défaut | Rôle |
|---|---|---|
| `LICHESS_TOKEN` | *(vide)* | Token personnel Lichess (obligatoire pour `/moves`) |
| `YOUTUBE_API_KEY` | *(vide)* | Clé YouTube Data API v3 (nécessaire pour les vidéos) |
| `FRONTEND_HOST_PORT` | `4200` | Port de l'interface sur la machine hôte |
| `BACKEND_HOST_PORT` | `8000` | Port de l'API sur la machine hôte |
| `MONGO_HOST_PORT` | `27017` | Port MongoDB sur la machine hôte |
| `MILVUS_HOST_PORT` | `19530` | Port Milvus sur la machine hôte |
| `LLM_PROVIDER` | `ollama` | LLM du coach : `ollama` (local) ou `mistral` (API, avec `MISTRAL_API_KEY`) |
| `OLLAMA_MODEL` | `qwen3:8b` | Modèle Ollama utilisé par le coach |

Les autres réglages (seuils, timeouts, filtres YouTube, profondeur Stockfish,
paramètres du RAG et de l'agent) ont des valeurs par défaut, modifiables dans
`.env` : voir `backend/app/config.py`.

### Ports

| Service | Port hôte|
|---|---|---|
| Backend FastAPI | 8000 |
| Frontend Angular (nginx) | 4200|
| MongoDB | 27017|
| Milvus | 19530 |



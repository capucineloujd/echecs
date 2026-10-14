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
| LLM | Ollama + Qwen3 8B en local (gratuit, sans clé) ; Mistral en option |
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

## Installation et démarrage

Procédure testée sur une installation fraîche (copie du dépôt, volumes vides,
build sans cache) le 13/10/2026.

### Prérequis

| Élément | Détail |
|---|---|
| Docker | Docker Desktop (ou Engine ≥ 25) avec Compose v2.20+ (`docker compose version`) |
| Mémoire Docker | **12 Go minimum** (Docker Desktop → Settings → Resources → Memory) : le modèle d'embedding, Milvus et MongoDB tournent ensemble |
| Disque | ~8 Go : images (~5,5 Go) + modèle d'embedding (1,2 Go) + données |
| Ports libres | 4200 (interface), 8000 (API), 27017 (MongoDB), 19530 (Milvus), modifiables, voir [Ports](#ports) |
| Token Lichess | Obligatoire : lichess.org → Préférences → Accès API → token **sans aucune permission** |
| Ollama | Pour le conseil du coach (sans Ollama, le reste de l'application fonctionne). Installé **sur la machine**, hors Docker : voir l'étape 2 |
| Clé YouTube | Facultative (sans clé, le panneau vidéos propose un lien de recherche) : Google Cloud Console → activer *YouTube Data API v3* → Identifiants → Clé API |

### 1. Configurer

Créer un fichier `.env` à la racine (il n'est pas versionné) :

```bash
cat > .env <<EOF
LICHESS_TOKEN=lip_xxxxxxxx
YOUTUBE_API_KEY=AIza...
EOF
```

Les autres variables ont des valeurs par défaut (voir [Configuration](#configuration)).

### 2. Installer Ollama et le modèle de langage

Ollama fait tourner le LLM du coach en local, gratuitement et sans compte.
Il est installé directement sur la machine et non dans Docker : sur Mac, un
conteneur n'a pas accès au GPU, et le modèle y serait beaucoup plus lent.
Le backend l'appelle via `host.docker.internal:11434`.

```bash
brew install ollama                 # ou l'installateur de ollama.com (macOS, Windows, Linux)
brew services start ollama          # lance le serveur Ollama et le relance au démarrage
ollama pull qwen3:8b                # ~5 Go
```

Mémoire : ~6 Go en plus pendant que le coach répond (hors des 12 Go de Docker).

### 3. Construire et lancer

```bash
docker compose up --build -d
```

Premier lancement : ~5 min (téléchargement des images, build, téléchargement
du modèle d'embedding au démarrage de l'API). Les six services doivent
apparaître `healthy` :

```bash
docker compose ps
```

### 4. Indexer les articles (premier lancement uniquement)

Milvus est vide après une installation fraîche : `/vector-search` répond `503`
avec le message « Collection 'opening_chunks' absente : lancer l'ingestion ».
L'API est arrêtée pendant l'ingestion, car elle garde aussi le modèle en
mémoire, et deux copies simultanées saturent la mémoire de Docker.

```bash
docker compose stop backend
docker compose run --rm backend python -m scripts.ingest   # 10 à 15 min sur CPU
docker compose up -d backend
```

Résultat attendu : `183 chunks indexés dans la collection 'opening_chunks'`.
L'index est conservé dans les volumes : inutile de relancer l'ingestion aux
démarrages suivants (voir [Persistance des données](#persistance-des-données)).

### 5. Ouvrir

- http://localhost:4200 --> l'interface (échiquier + recommandations de l'agent)
- http://localhost:8000/docs --> documentation Swagger de l'API
- http://localhost:8000/api/v1/healthcheck --> `{"status": "ok", ...}`

### Arrêter / relancer

| Commande | Effet |
|---|---|
| `docker compose stop` | Arrête les conteneurs |
| `docker compose up -d` | Relance (~30 s jusqu'à `healthy`, sans ingestion ni téléchargement) |
| `docker compose down` | Supprime les conteneurs, **garde les données** |
| `docker compose down -v` | Supprime aussi les volumes : index Milvus, cache, modèle. Il faudra refaire l'étape 4 |

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

(Branche vidéos en parallèle : voir [Vidéos YouTube](#vidéos-youtube).)

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

## Vidéos YouTube

### Clé API

Google Cloud Console → créer un projet → activer **YouTube Data API v3** →
*Credentials* → *Create API key* (la restreindre à YouTube Data API v3) →
`YOUTUBE_API_KEY` dans `.env`. Sans clé, l'endpoint répond `status: "unavailable"`.

### Recherche et filtrage

1. Requête en français (`<nom> échecs ouverture explication`), puis en anglais
   (`<nom anglais> chess opening explained tutorial`) seulement s'il manque
   des vidéos. `safeSearch=strict` (public de jeunes joueurs).
2. Filtres : vidéo intégrable, pas de live, durée entre 4 et 60 min (exclut
   les Shorts), au moins 5 000 vues, **titre citant l'ouverture**.
3. Classement : popularité (log des vues), ratio de likes, bonus pour le
   français, bonus pour les chaînes favorites (`YOUTUBE_PREFERRED_CHANNELS`),
   bonus pour les titres citant la variante précise ; au plus 2 vidéos par
   chaîne.

Chaque vidéo est renvoyée avec ses métadonnées (chaîne, durée, vues, likes,
langue, miniature), son lien `watch_url` et une `embed_url`
(`youtube-nocookie.com/embed/...`) pour la lire directement dans l'application.

### Quotas

Le quota gratuit est de 10 000 unités/jour ; une recherche coûte 100 unités,
le détail des vidéos 1 unité. Pour l'économiser :

- résultats en **cache MongoDB 7 jours** par ouverture (1 jour si aucune vidéo
  n'est trouvée) : le cache survit aux redémarrages ;
- la recherche anglaise n'est lancée que si la française ne suffit pas
  (101 unités au lieu de 202) ;
- dans le graphe, aucune recherche vidéo sans ouverture identifiée ;
- si YouTube renvoie `quotaExceeded`, plus aucun appel jusqu'à la remise à
  zéro (minuit, heure du Pacifique).

### Cas dégradés

L'endpoint répond toujours `200` ; le champ `status` vaut `ok`, `no_results`,
`quota_exceeded` ou `unavailable`, avec un `message` et un
`fallback_search_url` (recherche YouTube toute prête) à proposer à
l'utilisateur.

### Intégration LangGraph

Le nœud `find_videos` tourne **en parallèle** de la recherche Milvus, juste
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
                                          ▲  └──(« answer »)──► answer ──► END
                                          └─────────────────────────────────┘
```

| Nœud | Rôle |
|---|---|
| `read_position` | Lit toujours la position en premier (outil `get_position_moves`) : théorie Lichess si elle est connue, sinon Stockfish |
| `decide` | Le LLM choisit la prochaine étape : un outil (avec son argument) ou `answer`. Sortie structurée (JSON validé par Pydantic) |
| `tools` | Exécute l'outil (`ToolNode` de LangGraph) et renvoie le résultat au LLM |
| `answer` | Le LLM rédige le conseil, streamé vers l'interface |

Garde-fous : au plus `AGENT_MAX_STEPS` décisions ; un outil redemandé avec le
même argument, ou une décision illisible, mène directement à la réponse.

### Outils : l'agent choisit ses sources

| Outil | Source | Quand le LLM le choisit (consigne du prompt) |
|---|---|---|
| `get_position_moves` | `PositionAnalysisService` : Lichess si la position est dans la théorie, sinon Stockfish | Toujours, au départ (nœud `read_position`) |
| `evaluate_position(move_san)` | Stockfish après un coup | L'élève propose un coup (« et si je joue Nxd5 ? ») |
| `search_opening_knowledge(query)` | Graphe RAG (Milvus) | L'élève demande les plans, idées, pièges ou l'histoire |
| `find_videos(opening)` | YouTube | L'élève demande des vidéos |

### Choix de conception, et pourquoi

Les choix suivants viennent de tests réels sur les positions de démo
(Qwen3 8B, Mac M1 Max) :

| Version testée | Résultat |
|---|---|
| ReAct classique (outils facultatifs, le LLM appelle ce qu'il veut) | Le modèle répond souvent **sans appeler d'outil** : il a inventé une « partie italienne » dans une Najdorf, et n'a pas vérifié Nxd5 |
| + lecture de la position garantie au départ | Plus d'ouverture inventée, mais aucun outil supplémentaire appelé |
| + mode « réflexion » de Qwen3 | Vérifie parfois le coup, mais réponses 2 à 4 fois plus lentes et chiffres inventés |
| Qwen3 30B-A3B | N'arrive pas à désactiver sa réflexion : elle apparaît dans la réponse (en anglais), jusqu'à 66 s |
| **Décision explicite à chaque tour (version retenue)** | Bons outils dans les 5 cas testés, réponses en 8 à 15 s |

Un petit modèle local ignore facilement un outil « facultatif ». L'obliger à
écrire sa décision (`{"tool": "evaluate_position", "argument": "Nxd5"}`)
le fait réellement réfléchir à ses sources. C'est toujours lui qui choisit.

Autres choix :
- **La FEN ne passe pas par le LLM** : les outils la lisent dans l'état du
  graphe (`InjectedState`). Le modèle ne peut pas la recopier de travers.
- **Position décrite sous trois formes** (FEN, coups joués, diagramme ASCII),
  comme dans l'étude Kaggle Game Arena : les LLM lisent mal une FEN seule.
- **Résultats d'outils pré-interprétés** : évaluation en mots (« avantage
  décisif aux Noirs »), bilan matériel au bout de chaque ligne Stockfish
  (« les Noirs gagnent une pièce »), nom français de l'ouverture, coup de
  référence. Le modèle reformule, il ne calcule pas.
- **Rappel final** avant la rédaction (source réellement utilisée, coup de
  référence, question) : c'est la fin du contexte qu'un petit modèle suit le mieux.
- **Erreur d'outil** (Lichess en panne...) : renvoyée au LLM comme résultat
  (`handle_tool_errors`).
- **Réponse** : français, tutoiement, 120 mots max, en trois temps (où on en
  est, coup conseillé et pourquoi, idée à retenir), sources citées.

### Résultats sur les positions de démo (Qwen3 8B)

| Position et question | Outils choisis | Temps |
|---|---|---|
| Espagnole, « que jouer ? » | lecture de la position | ~12 s |
| Piège de l'éléphant, « et si je prends en d5 avec mon cavalier ? » | lecture + Stockfish sur Nxd5 | ~14 s |
| Coup du berger | lecture (le mat est trouvé) | ~9 s |
| 1.a3 h5 2.Ra2 Rh6 | lecture | ~8 s |
| Najdorf, « quels sont les plans ? » | lecture + articles | ~14 s |

Limites connues d'un modèle de 8 milliards de paramètres : formulations
parfois approximatives (ex. « sorti de la théorie » pour un coup hypothétique,
source mal attribuée), et explications des plans assez générales, car les
articles indexés sont surtout en anglais. Un modèle plus gros via l'API
Mistral (`LLM_PROVIDER=mistral`, non testé faute de clé) devrait donner de
meilleures réponses.

### Changer de modèle

| Variable | Effet |
|---|---|
| `LLM_PROVIDER=ollama` (défaut) | Modèle local `OLLAMA_MODEL` (défaut `qwen3:8b`), rien ne sort de la machine |
| `LLM_PROVIDER=mistral` | API Mistral, `MISTRAL_API_KEY` obligatoire, modèle `MISTRAL_MODEL` |

Le graphe, les outils, le streaming et l'interface ne dépendent pas du
fournisseur (`app/agent/llm.py`).

### Logique métier séparée de l'API

La décision « théorie ou moteur » (seuil `THEORY_MIN_GAMES`, repli sur
Stockfish si Lichess est indisponible) est dans
`services/position_analysis.py`, utilisée à la fois par la route `/moves`
(qui ne fait plus que valider la FEN et déléguer) et par l'outil
`get_position_moves` de l'agent.

### Streaming et erreurs

`POST /agent/analyze` renvoie un flux SSE : l'interface affiche les outils
consultés puis le texte au fil de l'eau. L'en-tête `X-Accel-Buffering: no`
empêche nginx de bufferiser le flux.

| Cas | Comportement |
|---|---|
| `LLM_PROVIDER=mistral` sans `MISTRAL_API_KEY` | `503` « Coach indisponible » ; le reste de l'application fonctionne |
| Ollama arrêté | Événement `error` « Modèle de langage injoignable (Ollama est-il lancé ?) » |
| Modèle non téléchargé | Événement `error` « lancer ollama pull qwen3:8b » |
| FEN invalide | `422` avant l'ouverture du flux |
| Mistral : clé invalide, limite (429), service injoignable | Événement `error` avec un message lisible (2 nouvelles tentatives automatiques avant) |
| Réponse trop longue | Timeout global `AGENT_TIMEOUT_SECONDS` → événement `error` |
| L'élève change de position pendant la réponse | La requête est annulée, le conseil effacé |

## Interface Angular

### Choix techniques

- **Échiquier** : le paquet `ngx-chessboard` n'existe pas sur npm ; la librairie
  s'appelle `ngx-chess-board`. Sa v3.0.0 a été publiée sans build (sources
  TypeScript seules) et est inutilisable : on utilise la **v2.2.3**, compilée
  pour Angular 13 mais compatible Angular 22 (format Ivy partiel). Elle importe
  `lodash` sans le déclarer : il est ajouté aux dépendances. Les `overrides` du
  `package.json` alignent ses peerDependencies sur la version d'Angular du projet.
- **Angular 22** : composants standalone, signals, nouveau control flow
  (`@if`, `@for`), sans zone.js.
- **Même origine** : en dev, `ng serve` redirige `/api` vers `localhost:8000`
  (`proxy.conf.json`) ; en Docker, nginx sert les fichiers et fait le proxy
  vers `backend`. Pas de CORS à configurer.

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
- Navigation ◀ ▶ (ou flèches du clavier) dans les coups joués ; jouer un autre
  coup au milieu de la partie remplace la suite.

### Optimisation des appels

| Mécanisme | Effet |
|---|---|
| Debounce 250 ms | Plusieurs coups enchaînés (ou ◀ ▶ rapides) : un seul appel, pour la position finale |
| Cache LRU par FEN (`RequestCache`) | Revenir sur une position déjà vue ne refait pas d'appel ; requêtes identiques partagées |
| Annulation | Une requête qui n'a plus d'abonné est annulée ; les erreurs ne sont pas mises en cache |
| Contexte par ouverture | `/vector-search` n'est appelé que quand le nom d'ouverture change, pas à chaque coup ; le nom reste affiché hors théorie |
| Vidéos à la demande | Pour une ouverture hors catalogue (ex. « King's Pawn Game »), bouton « Chercher des vidéos » au lieu d'un appel automatique qui consommerait le quota YouTube |
| Stockfish optionnel | `/evaluate` n'est appelé que si « Évaluation Stockfish » est cochée |

### Conseil du coach

Panneau « Conseil du coach » : champ de question facultatif et bouton
« Demander au coach ». L'agent n'est appelé **qu'à la demande** (pas à chaque
coup) : un appel LLM coûte du temps et de l'argent. `AgentService` lit le flux
SSE avec `HttpClient` (backend `fetch`, événements `DownloadProgress`), et
`AdviceStore` affiche les outils consultés (⏳ puis ✓) et le texte au fil de
l'eau. Bouton « Arrêter » pendant la réponse.

### Chargement et erreurs

Chaque panneau a son propre état (`idle`, `loading`, `ok`, `error`) : squelette
animé pendant le chargement, message et bouton « Réessayer » en cas d'erreur.
Les messages distinguent serveur injoignable, backend en cours de démarrage
(502/503/504 du proxy), limite Lichess (avec le délai `Retry-After`) et timeout.

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
| `echecs_hf_models` | `backend:/models` | Modèle Qwen3-Embedding (1,2 Go), téléchargé une seule fois |
| `echecs_etcd_data` | `etcd:/etcd` | Métadonnées Milvus (schéma de la collection, index) |
| `echecs_minio_data` | `minio:/minio_data` | Vecteurs et segments Milvus |
| `echecs_milvus_data` | `milvus:/var/lib/milvus` | Données locales de Milvus (journal, cache) |
| `echecs_mongo_data` | `mongodb:/data/db` | Cache des réponses YouTube (TTL 7 jours) |

L'index Milvus est réparti sur trois volumes (etcd, MinIO, Milvus) : il faut
les conserver tous les trois. `backend/data` est monté en bind mount (catalogue
et articles bruts, versionnés dans Git).

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

Testé le 13/10/2026 : après `down` puis `up`, les 183 passages, les documents
du cache MongoDB et le modèle étaient conservés, sans nouvelle ingestion ni
nouveau téléchargement.

## Démonstration

### Positions préparées

Chaque position se charge depuis le menu des ouvertures puis en cliquant les
coups suggérés, ou en jouant les coups à la souris. Les FEN permettent de
montrer la même chose directement dans l'API (`/docs` ou `curl`).

| # | Position | Coups | Ce qu'elle montre |
|---|---|---|---|
| 1 | Partie espagnole | 1.e4 e5 2.Nf3 Nc6 3.Bb5 | Le cas nominal : théorie des maîtres (162 000 parties, a6 joué à 71 %), fiche de l'ouverture (histoire, Wikibooks + Wikipédia), vidéos en français lisibles dans la page |
| 2 | Sicilienne Najdorf | 1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6 | Nom précis de variante donné par Lichess (« Sicilian Defense: Najdorf Variation ») rattaché à la fiche « Défense sicilienne » du catalogue |
| 3 | Attaque Fried Liver | Menu « Partie italienne », puis 3...Nf6 4.Ng5 d5 5.exd5 Nxd5 6.Nxf7 | Un piège classique pour jeunes joueurs : un seul coup possible (Kxf7, 100 %). Le nom d'ouverture reste affiché sur les positions que Lichess ne nomme pas |
| 4 | Piège de l'éléphant | Menu « Gambit dame », puis 2...e6 3.Nc3 Nf6 4.Bg5 Nbd7 5.cxd5 exd5, puis **6.Nxd5??** à la souris | Sortie de la théorie : Stockfish prend le relais, « avantage décisif aux Noirs » (−3,9), ligne Nxd5 Bxd8 Bb4+ qui gagne la Dame |
| 5 | Coup du berger | 1.e4 e5 2.Bc4 Nc6 3.Qh5 Nf6?? | Stockfish annonce le mat en 1 (Qxf7#). Jouer Qxf7# : l'interface affiche « Échec et mat » |
| 6 | Ouverture hors catalogue | 1.a3 h5 2.Ra2 Rh6 (à la souris) | Cas dégradés : hors théorie, ouverture absente du catalogue (« Pas encore de fiche »), vidéos seulement sur demande pour économiser le quota |

FEN correspondantes (les espaces peuvent être remplacés par `_` dans l'URL) :

```
1  r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3
2  rnbqkb1r/1p2pppp/p2p1n2/8/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq - 0 6
3  r1bqkb1r/ppp2Npp/2n5/3np3/2B5/8/PPPP1PPP/RNBQK2R b KQkq - 0 6
4  r1bqkb1r/pppn1ppp/5n2/3N2B1/3P4/8/PP2PPPP/R2QKBNR b KQkq - 0 6
5  r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4
6  rnbqkbn1/ppppppp1/7r/7p/8/P7/RPPPPPPP/1NBQKBNR w Kq - 2 3
```

Exemple :

```bash
curl -s "localhost:8000/api/v1/moves/r1bqkb1r/pppn1ppp/5n2/3N2B1/3P4/8/PP2PPPP/R2QKBNR_b_KQkq_-_0_6"
```

### Déroulé conseillé (~10 min)

1. Position 1 : présenter les panneaux (coups, ouverture, vidéos) ; lancer une vidéo ;
   cliquer « Demander au coach » : montrer les outils choisis puis le conseil.
2. Cocher « Évaluation Stockfish » : barre d'évaluation à côté de l'échiquier.
3. Position 2 : montrer la reconnaissance de variante et la navigation ◀ ▶ (ou flèches du clavier).
4. Positions 3 et 4 : les pièges, et le passage de la théorie à Stockfish. Avant
   de jouer 6.Nxd5 dans la position 4, demander au coach « et si je joue Nxd5 ? » :
   il vérifie le coup avec Stockfish et explique le piège.
5. Position 5 : le mat.
6. Position 6 : les cas dégradés.
7. Montrer `/docs` (Swagger) et `docker compose ps` pour l'architecture.

Avant la démo : lancer la stack 5 minutes avant, et parcourir une fois les
positions pour remplir les caches (Lichess en mémoire, YouTube dans MongoDB) :
les réponses sont alors instantanées.

## Vérification de bout en bout

Checklist à dérouler après une installation fraîche (dernière exécution :
13/10/2026, tout est passé).

| # | Vérification | Attendu |
|---|---|---|
| 1 | `docker compose ps` | 6 services `healthy` : frontend, backend, mongodb, milvus, etcd, minio |
| 2 | `curl localhost:4200/api/v1/healthcheck` | `{"status":"ok",...}` : nginx → backend fonctionne |
| 3 | Avant ingestion : `curl "localhost:8000/api/v1/vector-search?query=espagnole"` | `503`, message « lancer l'ingestion » |
| 4 | Ingestion (étape 4) | `183 chunks indexés` |
| 5 | http://localhost:4200, position 1 | Coups des maîtres, fiche « Partie espagnole » avec passages, 5 vidéos ; une vidéo se lit dans la page |
| 6 | Position 4 | Message « Tu es sorti de la théorie », lignes Stockfish |
| 7 | Case « Évaluation Stockfish » | Barre et score (« profondeur 18 ») |
| 7 bis | `curl localhost:11434/api/version` | Ollama répond ; `ollama list` contient `qwen3:8b` |
| 8 | « Demander au coach » (position 1) | Outils affichés (Théorie Lichess, Articles...), puis conseil en français au fil de l'eau |
| 8 bis | ◀ ▶, « Nouvelle partie », ⇅ | Navigation, remise à zéro, échiquier retourné |
| 9 | Fenêtre étroite (mobile) | Panneaux sous l'échiquier, pas de défilement horizontal |
| 10 | `docker compose stop backend`, puis action dans l'interface | Message « Le serveur de l'agent ne répond pas » + bouton Réessayer ; relancer avec `docker compose up -d backend` |
| 11 | `docker compose down` puis `up -d` | Données conservées (voir [Persistance](#persistance-des-données)) |

## Dépannage

| Symptôme | Cause et solution |
|---|---|
| `Cannot connect to the Docker daemon` | Docker Desktop n'est pas lancé : `open -a Docker` (macOS) |
| `port is already allocated` | Port déjà utilisé : changer `FRONTEND_HOST_PORT`, `BACKEND_HOST_PORT`, `MONGO_HOST_PORT` ou `MILVUS_HOST_PORT` dans `.env` |
| `/moves` répond `502` | `LICHESS_TOKEN` absent ou invalide dans `.env` (puis `docker compose up -d backend`) |
| `/vector-search` répond `503` « lancer l'ingestion » | Étape 4 non faite (ou volumes supprimés par `down -v`) |
| Ingestion interrompue (`Killed`, code 137) | Mémoire Docker insuffisante ou backend resté allumé : passer à 12 Go et arrêter le backend pendant l'ingestion |
| Milvus `unhealthy` après une ingestion | Processeur saturé : garder `EMBEDDING_THREADS=4` ; `restart: unless-stopped` le relance |
| Panneau vidéos : « quota épuisé » | Quota YouTube du jour atteint (10 000 unités) : retour à minuit, heure du Pacifique ; le cache MongoDB continue de servir les ouvertures déjà vues |
| Coach : « Modèle de langage injoignable » | Ollama n'est pas lancé : `brew services start ollama` (vérifier avec `curl localhost:11434/api/version`) |
| Coach : « Modèle absent d'Ollama » | `ollama pull qwen3:8b` |
| Coach : première réponse lente (~20 s) | Ollama charge le modèle en mémoire à la première demande, puis le garde quelques minutes |
| Interface : « Le serveur de l'agent ne répond pas » | Backend arrêté ou en train de charger le modèle (~20 s) : attendre `healthy` |

## Configuration

Toute la configuration passe par des variables d'environnement, lues depuis le
fichier `.env` à la racine (non versionné). Toutes les variables ont une valeur
par défaut, sauf `LICHESS_TOKEN`.

| Variable | Défaut | Rôle |
|---|---|---|
| `APP_ENV` | `development` | Environnement d'exécution |
| `BACKEND_PORT` | `8000` | Port d'écoute de FastAPI dans le conteneur |
| `BACKEND_HOST_PORT` | `8000` | Port exposé sur la machine hôte |
| `FRONTEND_HOST_PORT` | `4200` | Port de l'interface sur la machine hôte |
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
| `MONGO_URI` | `mongodb://mongodb:27017` | Adresse de MongoDB (réseau Docker) |
| `MONGO_HOST_PORT` | `27017` | Port MongoDB exposé sur la machine hôte |
| `YOUTUBE_API_KEY` | *(vide)* | Clé YouTube Data API v3 (obligatoire pour les vidéos) |
| `YOUTUBE_MAX_VIDEOS` | `5` | Nombre de vidéos renvoyées |
| `YOUTUBE_MIN_VIEWS` | `5000` | Vues minimales |
| `YOUTUBE_MIN_DURATION_SECONDS` / `YOUTUBE_MAX_DURATION_SECONDS` | `240` / `3600` | Durée acceptée |
| `YOUTUBE_CACHE_TTL_DAYS` | `7` | Durée du cache des résultats |
| `YOUTUBE_PREFERRED_CHANNELS` | *(vide)* | Identifiants de chaînes favorisées, séparés par des virgules |
| `LLM_PROVIDER` | `ollama` | Fournisseur du LLM du coach : `ollama` (local) ou `mistral` (API) |
| `LLM_TEMPERATURE` | `0.2` | Température : basse pour des conseils stables |
| `LLM_TIMEOUT_SECONDS` | `120` | Timeout d'un appel au modèle |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Adresse d'Ollama vue depuis le conteneur |
| `OLLAMA_MODEL` | `qwen3:8b` | Modèle Ollama (doit gérer la sortie structurée) |
| `OLLAMA_NUM_CTX` | `8192` | Taille du contexte (celle d'Ollama par défaut est trop courte) |
| `OLLAMA_REASONING` | `false` | Mode « réflexion » de Qwen3 (plus lent, pas plus fiable dans nos tests) |
| `MISTRAL_API_KEY` | *(vide)* | Clé API Mistral (si `LLM_PROVIDER=mistral`) |
| `MISTRAL_MODEL` | `mistral-small-latest` | Modèle Mistral |
| `AGENT_MAX_STEPS` | `4` | Décisions max avant que l'agent doive rédiger sa réponse |
| `AGENT_TIMEOUT_SECONDS` | `180` | Durée maximale d'une réponse complète |

### Ports

| Service | Port hôte | Statut |
|---|---|---|
| Backend FastAPI | 8000 | actif |
| Frontend Angular (nginx) | 4200 | actif |
| MongoDB | 27017 | actif |
| Milvus | 19530 | actif |

etcd et MinIO (stockage interne de Milvus) ne sont pas exposés sur la machine :
ils ne communiquent qu'à l'intérieur du réseau Docker, ce qui évite tout
conflit sur les ports 2379, 9000 et 9001.


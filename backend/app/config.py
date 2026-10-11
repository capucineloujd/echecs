from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Chess Opening Coach API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    backend_port: int = 8000

    #Lichess Opening Explorer 
    lichess_token: str = ""
    lichess_explorer_url: str = "https://explorer.lichess.ovh"
    # "masters" (parties de maîtres OTB) ou "lichess" (parties en ligne)
    lichess_database: str = "masters"
    # Filtres utilisés seulement pour la base "lichess"
    lichess_speeds: str = "blitz,rapid,classical"
    lichess_ratings: str = "2000,2200,2500"
    lichess_max_moves: int = 10
    lichess_timeout_seconds: float = 5.0
    lichess_cache_ttl_seconds: int = 3600
    # Pause imposée par Lichess après une réponse 429
    lichess_rate_limit_cooldown_seconds: int = 60
    # En dessous de ce nombre de parties, on considère qu'on est sorti de la théorie
    theory_min_games: int = 10

    # Stockfish 
    stockfish_path: str = "/usr/games/stockfish"
    stockfish_depth: int = 18
    stockfish_time_limit_seconds: float = 2.0
    stockfish_multipv: int = 3
    stockfish_threads: int = 2
    stockfish_hash_mb: int = 128

    # Milvus (nom du service dans le réseau Docker)
    milvus_uri: str = "http://milvus:19530"
    milvus_collection: str = "opening_chunks"

    # Embeddings
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    embedding_batch_size: int = 16
    # Threads CPU pour torch : on en laisse pour Milvus (sinon il perd son bail etcd)
    embedding_threads: int = 4
    # Consigne ajoutée aux requêtes (recommandé par Qwen3-Embedding, pas aux documents)
    embedding_query_instruction: str = (
        "Instruct: Given a chess player's question, retrieve encyclopedia passages "
        "about chess openings that answer it\nQuery: "
    )

    # RAG
    rag_top_k: int = 5
    # Similarité cosinus minimale pour garder un passage
    rag_min_score: float = 0.35
    chunk_max_chars: int = 1200

    # MongoDB (cache des appels aux API externes)
    mongo_uri: str = "mongodb://mongodb:27017"
    mongo_db: str = "echecs"

    # YouTube Data API v3
    youtube_api_key: str = ""
    youtube_timeout_seconds: float = 10.0
    youtube_max_videos: int = 5
    youtube_min_views: int = 5000
    youtube_min_duration_seconds: int = 240
    youtube_max_duration_seconds: int = 3600
    youtube_cache_ttl_days: int = 7
    # Chaînes favorisées dans le classement (identifiants séparés par des virgules)
    youtube_preferred_channels: str = ""


settings = Settings()

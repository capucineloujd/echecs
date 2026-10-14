from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Chess Opening Coach API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    backend_port: int = 8000

    lichess_token: str = ""
    lichess_explorer_url: str = "https://explorer.lichess.ovh"
    lichess_database: str = "masters"
    # Filtres utilisés seulement pour la base "lichess"
    lichess_speeds: str = "blitz,rapid,classical"
    lichess_ratings: str = "2000,2200,2500"
    lichess_max_moves: int = 10
    lichess_timeout_seconds: float = 5.0
    lichess_cache_ttl_seconds: int = 3600
    lichess_rate_limit_cooldown_seconds: int = 60
    theory_min_games: int = 10

    stockfish_path: str = "/usr/games/stockfish"
    stockfish_depth: int = 18
    stockfish_time_limit_seconds: float = 2.0
    stockfish_multipv: int = 3
    stockfish_threads: int = 2
    stockfish_hash_mb: int = 128

    milvus_uri: str = "http://milvus:19530"
    milvus_collection: str = "opening_chunks"

    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    embedding_batch_size: int = 16
    # Threads CPU pour torch : on en laisse pour Milvus (sinon il perd son bail etcd)
    embedding_threads: int = 4
    embedding_query_instruction: str = (
        "Instruct: Given a chess player's question, retrieve encyclopedia passages "
        "about chess openings that answer it\nQuery: "
    )

    rag_top_k: int = 5
    rag_min_score: float = 0.35
    chunk_max_chars: int = 1200

    mongo_uri: str = "mongodb://mongodb:27017"
    mongo_db: str = "echecs"

    youtube_api_key: str = ""
    youtube_timeout_seconds: float = 10.0
    youtube_max_videos: int = 5
    youtube_min_views: int = 5000
    youtube_min_duration_seconds: int = 240
    youtube_max_duration_seconds: int = 3600
    youtube_cache_ttl_days: int = 7
    youtube_preferred_channels: str = ""

    llm_provider: str = "ollama"
    llm_temperature: float = 0.2
    llm_timeout_seconds: int = 120
    # Ollama tourne sur la machine hôte (accès au GPU), le conteneur l'appelle via host.docker.internal
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen3:8b"
    ollama_num_ctx: int = 8192
    ollama_reasoning: bool = False
    mistral_api_key: str = ""
    mistral_model: str = "mistral-small-latest"
    agent_max_steps: int = 4
    agent_timeout_seconds: float = 180.0


settings = Settings()

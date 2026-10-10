from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration lue depuis les variables d'environnement (ou le fichier .env)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Chess Opening Coach API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    backend_port: int = 8000

    # --- Lichess Opening Explorer ---
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

    # --- Stockfish ---
    stockfish_path: str = "/usr/games/stockfish"
    stockfish_depth: int = 18
    stockfish_time_limit_seconds: float = 2.0
    stockfish_multipv: int = 3
    stockfish_threads: int = 2
    stockfish_hash_mb: int = 128


settings = Settings()

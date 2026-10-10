class InvalidFenError(ValueError):
    """La chaîne fournie n'est pas une position FEN valide."""

class ExternalServiceError(Exception):
    """Erreur générique d'un service externe (Lichess, Stockfish)"""


class LichessUnavailableError(ExternalServiceError):
    """Lichess ne répond pas"""


class LichessAuthError(ExternalServiceError):
    """Token Lichess absent ou invalide (>>>401)"""


class LichessRateLimitError(ExternalServiceError):
    """Lichess a renvoyé 429 : il faut attendre avant de réessayer"""

    def __init__(self, retry_after: int):
        super().__init__(f"Limite de requêtes Lichess atteinte, réessayer dans {retry_after} s")
        self.retry_after = retry_after


class EngineError(ExternalServiceError):
    """Stockfish est indisponible ou a planté."""


class VectorStoreError(ExternalServiceError):
    """Milvus est injoignable ou la collection n'existe pas."""

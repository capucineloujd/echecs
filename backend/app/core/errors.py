class InvalidFenError(ValueError):
    pass


class ExternalServiceError(Exception):
    pass


class LichessUnavailableError(ExternalServiceError):
    pass


class LichessAuthError(ExternalServiceError):
    pass


class LichessRateLimitError(ExternalServiceError):
    def __init__(self, retry_after: int):
        super().__init__(f"Limite de requêtes Lichess atteinte, réessayer dans {retry_after} s")
        self.retry_after = retry_after


class EngineError(ExternalServiceError):
    pass


class VectorStoreError(ExternalServiceError):
    pass


class AgentUnavailableError(Exception):
    pass

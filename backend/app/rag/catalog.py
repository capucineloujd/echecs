import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import chess

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@dataclass(frozen=True)
class OpeningInfo:
    slug: str
    name: str
    eco: str
    moves: str
    fen: str
    aliases: tuple[str, ...]
    name_en: str = ""

    @property
    def search_terms(self) -> tuple[str, ...]:
        return tuple(t for t in (self.name, self.slug, self.name_en, *self.aliases) if t)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


class OpeningCatalog:
    def __init__(self, openings: list[OpeningInfo]):
        self.openings = {o.slug: o for o in openings}
        # Alias les plus longs d'abord : "gambit dame" doit gagner sur "dame"
        self._aliases = sorted(
            ((normalize(alias), o) for o in openings for alias in o.search_terms),
            key=lambda pair: len(pair[0]),
            reverse=True,
        )

    @classmethod
    def load(cls, path: Path = DATA_DIR / "openings_catalog.json") -> "OpeningCatalog":
        openings = []
        for o in json.loads(path.read_text()):
            board = chess.Board()
            for san in o["moves"].split():
                board.push_san(san)
            openings.append(
                OpeningInfo(
                    o["slug"], o["name"], o["eco"], o["moves"], board.fen(), tuple(o["aliases"]), o.get("name_en", "")
                )
            )
        return cls(openings)

    def exact(self, slug_or_name: str) -> OpeningInfo | None:
        if slug_or_name in self.openings:
            return self.openings[slug_or_name]
        wanted = normalize(slug_or_name)
        return next((o for alias, o in self._aliases if alias == wanted), None)

    def get(self, slug_or_name: str) -> OpeningInfo | None:
        return self.openings.get(slug_or_name) or self.detect(slug_or_name)

    def detect(self, query: str) -> OpeningInfo | None:
        padded = f" {normalize(query)} "
        for alias, opening in self._aliases:
            if f" {alias} " in padded:
                return opening
        return None

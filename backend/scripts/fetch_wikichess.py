"""Télécharge les articles d'ouvertures (Wikibooks Chess Opening Theory + Wikipédia FR).

Usage (depuis la racine du projet) :
    docker compose run --rm backend python -m scripts.fetch_wikichess

Les articles sont écrits dans data/raw/<slug>.json et versionnés dans Git :
l'ingestion fonctionne ensuite sans accès réseau.
"""

import json
import sys
import time
from pathlib import Path

import chess
import httpx

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CATALOG = DATA_DIR / "openings_catalog.json"
RAW_DIR = DATA_DIR / "raw"

SOURCES = {
    "wikibooks": ("https://en.wikibooks.org/w/api.php", "https://en.wikibooks.org/wiki/", "en"),
    "wikipedia_fr": ("https://fr.wikipedia.org/w/api.php", "https://fr.wikipedia.org/wiki/", "fr"),
}
# Wikimedia demande un User-Agent identifiable
USER_AGENT = "EchecsCoachFFE-POC/0.1 (educational project)"


MAX_RETRIES = 4


def get_with_retry(client: httpx.Client, url: str, params: dict) -> httpx.Response:
    """GET avec réessais : respecte Retry-After sur 429, attente exponentielle sinon."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.get(url, params=params)
        except httpx.TransportError:
            if attempt == MAX_RETRIES:
                raise
            time.sleep(2**attempt)
            continue
        if response.status_code in (429, 503) and attempt < MAX_RETRIES:
            retry_after = response.headers.get("Retry-After", "")
            delay = int(retry_after) if retry_after.isdigit() else 5 * 2**attempt
            print(f"    … {response.status_code}, nouvel essai dans {delay} s", file=sys.stderr)
            time.sleep(delay)
            continue
        response.raise_for_status()
        return response
    raise RuntimeError("unreachable")


def fetch_extract(client: httpx.Client, api_url: str, title: str) -> str:
    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": 1,
        "redirects": 1,
        "format": "json",
        "titles": title,
    }
    response = get_with_retry(client, api_url, params)
    page = next(iter(response.json()["query"]["pages"].values()))
    if "missing" in page or not page.get("extract"):
        raise ValueError(f"Page introuvable : {title}")
    return page["extract"]


def opening_fen(moves: str) -> str:
    board = chess.Board()
    for san in moves.split():
        board.push_san(san)
    return board.fen()


def main() -> int:
    catalog = json.loads(CATALOG.read_text())
    # Option --missing : ne télécharge que les ouvertures absentes de data/raw
    if "--missing" in sys.argv:
        catalog = [o for o in catalog if not (RAW_DIR / f"{o['slug']}.json").exists()]
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    errors = 0

    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20) as client:
        for opening in catalog:
            documents = []
            for source, (api_url, page_url, lang) in SOURCES.items():
                title = opening[source]
                try:
                    text = fetch_extract(client, api_url, title)
                except (httpx.HTTPError, ValueError) as exc:
                    print(f"  ✗ {opening['slug']} / {source} : {exc}", file=sys.stderr)
                    errors += 1
                    continue
                documents.append(
                    {"source": source, "lang": lang, "title": title,
                     "url": page_url + title.replace(" ", "_"), "text": text}
                )
                time.sleep(2)  # politesse envers les serveurs Wikimedia

            if len(documents) < len(SOURCES):
                # On garde la version précédente plutôt que d'écrire un article incomplet
                print(f"  ✗ {opening['name']} : incomplet, fichier non modifié", file=sys.stderr)
                continue

            record = {k: opening[k] for k in ("slug", "name", "eco", "moves", "aliases")}
            record["fen"] = opening_fen(opening["moves"])
            record["documents"] = documents
            out = RAW_DIR / f"{opening['slug']}.json"
            out.write_text(json.dumps(record, ensure_ascii=False, indent=2))
            sizes = ", ".join(f"{d['source']}={len(d['text'])}" for d in documents)
            print(f"  ✓ {opening['name']} ({sizes})")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

import pytest
from app.rag.catalog import OpeningCatalog, normalize
from app.rag.graph import build_rag_graph


@pytest.fixture(scope="module")
def catalog():
    return OpeningCatalog.load()


@pytest.mark.parametrize(
    "query, slug",
    [
        ("Quels sont les plans de la partie espagnole ?", "espagnole"),
        ("ruy lopez berlin", "espagnole"),
        ("Défense Caro-Kann variante d'avance", "caro-kann"),
        ("defense caro kann", "caro-kann"),
        ("Histoire du gambit de la dame", "gambit-dame"),
        ("King's Indian attack plans", "est-indienne"),
        ("la Sicilienne Najdorf", "sicilienne"),
    ],
)
def test_detect_opening(catalog, query, slug):
    assert catalog.detect(query).slug == slug


def test_detect_nothing(catalog):
    assert catalog.detect("comment jouer contre un débutant ?") is None


def test_catalog_fen(catalog):
    assert catalog.get("italienne").fen == "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"


def test_normalize():
    assert normalize("Défense  Caro-Kann !") == "defense caro kann"


class FakeEmbedder:
    async def aembed_query(self, query):
        return [0.0] * 4


def hit(slug, score, text):
    return {"score": score, "opening_slug": slug, "opening_name": slug.title(), "eco": "C60", "fen": "",
            "section": "Histoire", "source": "wikipedia_fr", "lang": "fr", "url": "https://x", "text": text}


class FakeStore:
    def __init__(self, by_filter):
        self.by_filter, self.calls = by_filter, []

    async def asearch(self, vector, top_k, opening_slug=None):
        self.calls.append(opening_slug)
        return self.by_filter.get(opening_slug, [])


def run(graph, query, **kwargs):
    return graph.ainvoke({"query": query, "top_k": 3, "min_score": 0.35, **kwargs})


async def test_graph_filters_on_detected_opening(catalog):
    store = FakeStore({"espagnole": [hit("espagnole", 0.8, "Ruy López, 1561"), hit("espagnole", 0.6, "Berlinoise")]})
    state = await run(build_rag_graph(FakeEmbedder(), store, catalog), "histoire de l'espagnole")

    assert store.calls == ["espagnole"]
    assert [r["text"] for r in state["results"]] == ["Ruy López, 1561", "Berlinoise"]
    assert state["context"].startswith("[1] Espagnole (C60), Histoire")


async def test_graph_drops_low_scores_and_duplicates(catalog):
    hits = [hit("espagnole", 0.9, "A"), hit("espagnole", 0.85, "A"), hit("espagnole", 0.2, "bruit")]
    state = await run(build_rag_graph(FakeEmbedder(), FakeStore({None: hits}), catalog), "une question vague")
    assert [r["text"] for r in state["results"]] == ["A"]


async def test_graph_widens_search_when_filter_finds_nothing(catalog):
    store = FakeStore({"sicilienne": [], None: [hit("francaise", 0.7, "Passage général")]})
    state = await run(build_rag_graph(FakeEmbedder(), store, catalog), "sicilienne et fianchetto")

    assert store.calls == ["sicilienne", None]
    assert state["widened"] is True
    assert state["results"][0]["text"] == "Passage général"


async def test_graph_explicit_opening_param(catalog):
    store = FakeStore({"francaise": [hit("francaise", 0.7, "Winawer")]})
    await run(build_rag_graph(FakeEmbedder(), store, catalog), "plans typiques", opening="française")
    assert store.calls == ["francaise"]


class FakeYouTube:
    def __init__(self):
        self.calls = []

    async def find_videos(self, opening):
        from app.schemas import VideosResponse

        self.calls.append(opening)
        return VideosResponse(opening=opening, status="ok", fallback_search_url="https://x")


async def test_graph_proposes_videos_for_detected_opening(catalog):
    youtube = FakeYouTube()
    store = FakeStore({"espagnole": [hit("espagnole", 0.8, "Ruy López")]})
    state = await run(build_rag_graph(FakeEmbedder(), store, catalog, youtube), "plans de l'espagnole")
    assert youtube.calls == ["espagnole"]
    assert state["videos"].status == "ok"
    assert state["results"][0]["text"] == "Ruy López"


async def test_graph_no_videos_without_detected_opening(catalog):
    youtube = FakeYouTube()
    state = await run(build_rag_graph(FakeEmbedder(), FakeStore({}), catalog, youtube), "question vague")
    assert youtube.calls == [] and state["videos"] is None


async def test_graph_videos_can_be_disabled(catalog):
    youtube = FakeYouTube()
    await run(build_rag_graph(FakeEmbedder(), FakeStore({}), catalog, youtube), "espagnole", include_videos=False)
    assert youtube.calls == []

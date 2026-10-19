import json
from datetime import datetime, timezone
import httplib2
import pytest
from googleapiclient.errors import HttpError
from app.config import Settings
from app.rag.catalog import OpeningCatalog
from app.services.cache import MemoryCache
from app.services.youtube import (
    QUOTA_KEY,
    YouTubeService,
    format_duration,
    next_quota_reset,
    parse_duration,
    relevance_terms,
)


def item(vid, title, views=50_000, likes=2_000, duration="PT12M30S", channel="c1", lang="fr", embeddable=True,
         live="none"):
    return {
        "id": vid,
        "snippet": {"title": title, "channelTitle": f"Chaîne {channel}", "channelId": channel,
                    "publishedAt": "2024-01-01T00:00:00Z", "defaultAudioLanguage": lang,
                    "liveBroadcastContent": live, "thumbnails": {"high": {"url": f"https://i.ytimg.com/{vid}.jpg"}}},
        "contentDetails": {"duration": duration},
        "statistics": {"viewCount": str(views), "likeCount": str(likes)},
        "status": {"embeddable": embeddable},
    }


class FakeClient:
    def __init__(self, by_language: dict[str, list[dict]], error: Exception | None = None):
        self.by_language, self.error = by_language, error
        self.searches: list[tuple[str, str]] = []
        self._items = {i["id"]: i for items in by_language.values() for i in items}

    def search(self, query, language, max_results=25):
        self.searches.append((language, query))
        if self.error:
            raise self.error
        return [i["id"] for i in self.by_language.get(language, [])]

    def details(self, ids):
        return [self._items[i] for i in ids]


def quota_error():
    content = json.dumps({"error": {"errors": [{"reason": "quotaExceeded"}]}}).encode()
    return HttpError(httplib2.Response({"status": 403}), content)


@pytest.fixture(scope="module")
def catalog():
    return OpeningCatalog.load()


def service(catalog, client, **overrides):
    settings = Settings(**{"youtube_api_key": "test", "youtube_max_videos": 3, **overrides})
    return YouTubeService(settings, MemoryCache(), catalog, client=client)


async def test_filters_bad_videos(catalog):
    client = FakeClient({"fr": [
        item("ok", "La partie espagnole expliquée"),
        item("short", "Partie espagnole #shorts", duration="PT45S"),
        item("live", "Live partie espagnole", duration="PT3H", live="live"),
        item("hors_sujet", "Mes 10 meilleures parties", views=900_000),
        item("confidentiel", "Ruy Lopez pour débutants", views=120),
        item("non_integrable", "Ruy Lopez : les plans", embeddable=False),
    ]})
    result = await service(catalog, client).find_videos("espagnole")

    assert result.status == "ok"
    assert [v.id for v in result.videos] == ["ok"]
    video = result.videos[0]
    assert video.watch_url == "https://www.youtube.com/watch?v=ok"
    assert video.embed_url == "https://www.youtube-nocookie.com/embed/ok"
    assert video.duration == "12:30"


async def test_skips_english_search_when_enough_french(catalog):
    client = FakeClient({"fr": [item(f"v{i}", "Défense sicilienne", channel=f"c{i}") for i in range(4)]})
    result = await service(catalog, client).find_videos("sicilienne")
    assert [lang for lang, _ in client.searches] == ["fr"]
    assert result.quota_units_used == 101
    assert len(result.videos) == 3


async def test_falls_back_to_english(catalog):
    client = FakeClient({"fr": [], "en": [item("en1", "Caro-Kann Defense explained", lang="en")]})
    result = await service(catalog, client).find_videos("caro-kann")
    assert [lang for lang, _ in client.searches] == ["fr", "en"]
    assert "Caro-Kann Defense chess opening" in client.searches[1][1]
    assert result.videos[0].language == "en"


async def test_ranking_prefers_french_and_limits_per_channel(catalog):
    client = FakeClient({"fr": [
        item("a", "Partie italienne", views=100_000, channel="x", lang="en"),
        item("b", "Partie italienne", views=60_000, channel="y", lang="fr"),
        item("c", "Italian game 1", views=500_000, channel="z", lang="en"),
        item("d", "Italian game 2", views=400_000, channel="z", lang="en"),
        item("e", "Italian game 3", views=300_000, channel="z", lang="en"),
    ]})
    result = await service(catalog, client, youtube_max_videos=5).find_videos("italienne")
    ids = [v.id for v in result.videos]
    assert ids[0] == "b"
    assert sum(v.channel_id == "z" for v in result.videos) == 2
    assert "e" not in ids


async def test_cache_avoids_second_call(catalog):
    client = FakeClient({"fr": [item(f"v{i}", "Partie anglaise", channel=f"c{i}") for i in range(3)]})
    svc = service(catalog, client)
    first = await svc.find_videos("anglaise")
    second = await svc.find_videos("Partie anglaise")
    assert len(client.searches) == 1
    assert first.cached is False and second.cached is True
    assert second.quota_units_used == 0
    assert second.videos == first.videos





async def test_no_results(catalog):
    client = FakeClient({"fr": [], "en": []})
    result = await service(catalog, client).find_videos("scandinave")
    assert result.status == "no_results"
    assert result.videos == []
    assert result.fallback_search_url.startswith("https://www.youtube.com/results?search_query=Scandinavian")

async def test_quota_exceeded_blocks_next_calls(catalog):
    client = FakeClient({}, error=quota_error())
    svc = service(catalog, client)
    first = await svc.find_videos("francaise")
    assert first.status == "quota_exceeded"
    assert await svc._cache.get(QUOTA_KEY)

    client.error = None
    second = await svc.find_videos("italienne")
    assert second.status == "quota_exceeded"
    assert len(client.searches) == 1


async def test_network_error_is_unavailable(catalog):
    result = await service(catalog, FakeClient({}, error=TimeoutError())).find_videos("italienne")
    assert result.status == "unavailable"



async def test_missing_api_key(catalog):
    svc = YouTubeService(Settings(youtube_api_key=""), MemoryCache(), catalog)
    result = await svc.find_videos("italienne")
    assert result.status == "unavailable"
    assert "YOUTUBE_API_KEY" in result.message


async def test_opening_outside_catalog(catalog):
    client = FakeClient({"fr": [item("n1", "La Najdorf expliquée", channel="a", views=20_000),
                                item("n2", "Sicilian Najdorf ideas", channel="b", views=20_000),
                                item("sic", "The Sicilian Defense", channel="d", views=900_000),
                                item("n3", "Comment gagner aux échecs", channel="c")]})
    result = await service(catalog, client).find_videos("Sicilian Defense: Najdorf Variation")
    assert [v.id for v in result.videos][:2] == ["n1", "n2"] and "sic" in {v.id for v in result.videos}
    assert "Sicilian Defense: Najdorf Variation" in client.searches[0][1]
    assert result.opening_slug == "sicilienne"


def test_relevance_terms_for_lichess_names():
    assert relevance_terms("Sicilian Defense: Najdorf Variation", None) == ["sicilian", "najdorf"]



@pytest.mark.parametrize("iso, seconds", [("PT45S", 45), ("PT12M30S", 750), ("PT1H2M3S", 3723), ("P1DT1H", 90000), ("", 0)])
def test_parse_duration(iso, seconds):
    assert parse_duration(iso) == seconds


def test_format_duration():
    assert format_duration(750) == "12:30"
    assert format_duration(3723) == "1:02:03"



def test_quota_reset_is_next_pacific_midnight():
    reset = next_quota_reset(datetime(2026, 10, 10, 20, 0, tzinfo=timezone.utc))
    assert reset == datetime(2026, 10, 11, 7, 0, tzinfo=timezone.utc)

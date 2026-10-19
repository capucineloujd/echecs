import asyncio
import logging
import math
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httplib2
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import Settings
from app.rag.catalog import OpeningCatalog, OpeningInfo, normalize
from app.schemas import Video, VideosResponse
from app.services.cache import Cache

logger = logging.getLogger(__name__)

QUOTA_KEY = "youtube:quota_blocked_until"
GENERIC_WORDS = {"variation", "variante", "defense", "defence", "opening", "game", "partie", "line", "system"}


class YouTubeQuotaError(Exception):
    pass


class YouTubeClient:
    def __init__(self, api_key: str, timeout: float):
        self._api_key = api_key
        self._timeout = timeout

    def _service(self):
        # un client par appel (pas thread-safe)
        return build(
            "youtube", "v3", developerKey=self._api_key, http=httplib2.Http(timeout=self._timeout),
            cache_discovery=False, static_discovery=True,
        )

    def search(self, query: str, language: str, max_results: int = 25) -> list[str]:
        response = self._service().search().list(
            q=query,
            part="id",
            type="video",
            maxResults=max_results,
            relevanceLanguage=language,
            videoEmbeddable="true",
            safeSearch="strict",
        ).execute()
        return [item["id"]["videoId"] for item in response.get("items", [])]

    def details(self, video_ids: list[str]) -> list[dict]:
        if not video_ids:
            return []
        response = self._service().videos().list(
            id=",".join(video_ids), part="snippet,contentDetails,statistics,status", maxResults=50
        ).execute()
        return response.get("items", [])


def parse_duration(iso: str) -> int:
    match = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not match:
        return 0
    days, hours, minutes, seconds = (int(g or 0) for g in match.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def format_duration(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def relevance_terms(opening: str, info: OpeningInfo | None) -> list[str]:
    if info:
        return [normalize(t) for t in info.search_terms]
    terms = []
    for part in re.split(r"[:,]", opening):
        words = [w for w in normalize(part).split() if w not in GENERIC_WORDS]
        if words:
            terms.append(" ".join(words))
    return terms or [normalize(opening)]


def next_quota_reset(now: datetime | None = None) -> datetime:
    pacific = ZoneInfo("America/Los_Angeles")
    now = (now or datetime.now(timezone.utc)).astimezone(pacific)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return tomorrow.astimezone(timezone.utc)


class YouTubeService:
    def __init__(self, settings: Settings, cache: Cache, catalog: OpeningCatalog, client: YouTubeClient | None = None):
        self._settings = settings
        self._cache = cache
        self._catalog = catalog
        self._client = client or (
            YouTubeClient(settings.youtube_api_key, settings.youtube_timeout_seconds)
            if settings.youtube_api_key else None
        )
        self._preferred = {c.strip() for c in settings.youtube_preferred_channels.split(",") if c.strip()}
        self._lock = asyncio.Lock()

    async def find_videos(self, opening: str) -> VideosResponse:
        info = self._catalog.exact(opening)
        family = info or self._catalog.detect(opening)
        label = info.name if info else opening
        fallback = "https://www.youtube.com/results?" + urllib.parse.urlencode(
            {"search_query": f"{info.name_en if info and info.name_en else opening} chess opening explained"}
        )
        base = {"opening": label, "opening_slug": family.slug if family else None, "fallback_search_url": fallback}

        if self._client is None:
            return VideosResponse(**base, status="unavailable", message="Clé YOUTUBE_API_KEY non configurée")

        cache_key = f"youtube:videos:{info.slug if info else normalize(opening)}"
        # lock pour ne pas payer le quota 2 fois
        async with self._lock:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                return VideosResponse(**{**cached, "cached": True, "quota_units_used": 0})

            blocked_until = await self._cache.get(QUOTA_KEY)
            if blocked_until:
                return VideosResponse(
                    **base, status="quota_exceeded",
                    message=f"Quota YouTube épuisé jusqu'à {blocked_until} (UTC)",
                )

            try:
                videos, units = await self._search(opening, info)
            except YouTubeQuotaError:
                reset = next_quota_reset()
                ttl = int((reset - datetime.now(timezone.utc)).total_seconds())
                await self._cache.set(QUOTA_KEY, reset.isoformat(timespec="minutes"), ttl)
                return VideosResponse(**base, status="quota_exceeded", message="Quota YouTube épuisé pour aujourd'hui")
            except (HttpError, OSError, TimeoutError) as exc:
                logger.warning("YouTube indisponible : %s", exc)
                return VideosResponse(**base, status="unavailable", message="YouTube est momentanément injoignable")

            if videos:
                result = VideosResponse(**base, status="ok", videos=videos, quota_units_used=units)
                ttl = self._settings.youtube_cache_ttl_days * 86400
            else:
                result = VideosResponse(
                    **base, status="no_results", quota_units_used=units,
                    message="Aucune vidéo de qualité trouvée pour cette ouverture",
                )
                ttl = 86400  # 1 jour

            await self._cache.set(cache_key, result.model_dump(mode="json"), ttl)
            return result

    async def _search(self, opening: str, info: OpeningInfo | None) -> tuple[list[Video], int]:
        terms = relevance_terms(opening, info)
        # hors catalogue : on prend le dernier mot
        specific = terms[-1] if info is None and len(terms) > 1 else None
        wanted = self._settings.youtube_max_videos
        queries = [
            ("fr", f"{info.name if info else opening} échecs ouverture explication"),
            ("en", f"{info.name_en if info and info.name_en else opening} chess opening explained tutorial"),
        ]

        candidates: dict[str, Video] = {}
        units = 0
        for language, query in queries:
            ids = await self._call(self._client.search, query, language)
            new_ids = [i for i in ids if i not in candidates]
            items = await self._call(self._client.details, new_ids)
            units += 100 + (1 if new_ids else 0)
            for item in items:
                video = self._to_video(item, language, terms, specific)
                if video:
                    candidates[video.id] = video
            if len(candidates) >= wanted:
                break

        return self._rank(list(candidates.values()), wanted), units

    async def _call(self, fn, *args):
        try:
            return await asyncio.to_thread(fn, *args)
        except HttpError as exc:
            if exc.resp.status == 403 and b"quotaExceeded" in (exc.content or b""):
                raise YouTubeQuotaError() from exc
            raise

    def _to_video(self, item: dict, search_language: str, terms: list[str], specific: str | None = None) -> Video | None:
        snippet, stats = item["snippet"], item.get("statistics", {})
        duration = parse_duration(item["contentDetails"].get("duration", ""))
        views = int(stats.get("viewCount", 0))
        title = snippet["title"]

        if not item.get("status", {}).get("embeddable", False):
            return None
        if snippet.get("liveBroadcastContent", "none") != "none":
            return None
        if not self._settings.youtube_min_duration_seconds <= duration <= self._settings.youtube_max_duration_seconds:
            return None
        if views < self._settings.youtube_min_views:
            return None
        normalized_title = f" {normalize(title)} "
        if not any(f" {t} " in normalized_title for t in terms):
            return None

        language = (snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage") or search_language)[:2]
        likes = int(stats["likeCount"]) if "likeCount" in stats else None
        thumbnails = snippet.get("thumbnails", {})
        thumbnail = (thumbnails.get("high") or thumbnails.get("medium") or thumbnails.get("default") or {}).get("url")

        return Video(
            id=item["id"],
            title=title,
            channel=snippet["channelTitle"],
            channel_id=snippet["channelId"],
            published_at=snippet["publishedAt"],
            duration_seconds=duration,
            duration=format_duration(duration),
            views=views,
            likes=likes,
            language=language,
            thumbnail_url=thumbnail,
            watch_url=f"https://www.youtube.com/watch?v={item['id']}",
            embed_url=f"https://www.youtube-nocookie.com/embed/{item['id']}",
            score=self._score(views, likes, language, snippet["channelId"])
            + (1.5 if specific and f" {specific} " in normalized_title else 0.0),
        )

    def _score(self, views: int, likes: int | None, language: str, channel_id: str) -> float:
        score = math.log10(max(views, 1))
        if likes is not None and views:
            score += min(likes / views * 20, 1.0)
        if language == "fr":
            score += 1.0
        if channel_id in self._preferred:
            score += 2.0
        return round(score, 3)

    @staticmethod
    def _rank(videos: list[Video], limit: int) -> list[Video]:
        ranked, per_channel = [], {}
        for video in sorted(videos, key=lambda v: v.score, reverse=True):
            if per_channel.get(video.channel_id, 0) >= 2:
                continue
            per_channel[video.channel_id] = per_channel.get(video.channel_id, 0) + 1
            ranked.append(video)
            if len(ranked) == limit:
                break
        return ranked

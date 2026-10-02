from __future__ import annotations

import asyncio
import time
from typing import Any

from yt_dlp import YoutubeDL

from ..models import ResolvedMedia
from ..security import safe_filename
from .base import Provider, ProviderError


class YtDlpProvider(Provider):
    name = "ytdlp"

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled

    @property
    def configured(self) -> bool:
        return self._enabled

    async def resolve(self, url: str) -> ResolvedMedia:
        if not self.configured:
            raise ProviderError("disabled", "yt-dlp provider is disabled", retryable=False)
        return await asyncio.to_thread(self._extract, url)

    def _extract(self, url: str) -> ResolvedMedia:
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": 10,
            "retries": 1,
            "extractor_retries": 1,
            "format": "best[ext=mp4][vcodec!=none][acodec!=none]/best[vcodec!=none][acodec!=none]",
        }
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:
            raise ProviderError("extract_failed", str(exc)) from exc
        if not isinstance(info, dict):
            raise ProviderError("empty_result", "yt-dlp returned no media")
        availability = str(info.get("availability") or "public")
        if availability in {"private", "premium_only", "subscriber_only", "needs_auth"}:
            raise ProviderError("restricted", "Media is not publicly accessible", retryable=False)
        media_url = info.get("url")
        if not isinstance(media_url, str) or not media_url.startswith(("http://", "https://")):
            raise ProviderError("no_media_url", "yt-dlp did not return a progressive media URL")
        protocol = str(info.get("protocol") or "")
        if "m3u8" in protocol or "dash" in protocol:
            raise ProviderError("segmented_media", "yt-dlp returned segmented media")
        video_id = str(info.get("id") or "video")
        ext = str(info.get("ext") or "mp4")
        filename = safe_filename(f"tiktok-{video_id}.{ext}")
        headers = {
            str(k): str(v)
            for k, v in (info.get("http_headers") or {}).items()
            if isinstance(k, str) and isinstance(v, (str, int, float))
        }
        return ResolvedMedia(
            source_url=url,
            provider=self.name,
            media_url=media_url,
            title=info.get("title") or info.get("description"),
            author=info.get("uploader") or info.get("creator"),
            thumbnail=info.get("thumbnail"),
            duration=float(info["duration"]) if info.get("duration") is not None else None,
            filename=filename,
            content_type="video/mp4" if ext == "mp4" else "application/octet-stream",
            upstream_headers=headers,
            created_at=time.time(),
        )

from __future__ import annotations

import time
from typing import Any

import httpx

from ..models import ResolvedMedia
from ..security import safe_filename
from .base import Provider, ProviderError


class DtkProvider(Provider):
    name = "dtk"

    def __init__(self, base_url: str | None, api_key: str | None, wait_seconds: int = 12) -> None:
        self._base_url = base_url.rstrip("/") if base_url else None
        self._api_key = api_key
        self._wait_seconds = max(1, min(wait_seconds, 25))

    @property
    def configured(self) -> bool:
        return bool(self._base_url and self._api_key)

    async def resolve(self, url: str) -> ResolvedMedia:
        if not self.configured:
            raise ProviderError("disabled", "DTK provider is not configured", retryable=False)
        endpoint = f"{self._base_url}/api/v1/parse?wait={self._wait_seconds}"
        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=self._wait_seconds + 3
            ) as client:
                response = await client.post(
                    endpoint,
                    headers={"X-API-Key": self._api_key or "", "Content-Type": "application/json"},
                    json={"url": url},
                )
                if response.status_code == 202:
                    raise ProviderError("still_running", "DTK parse task did not finish in time")
                response.raise_for_status()
                envelope = response.json()
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("request_failed", str(exc)) from exc
        if not envelope.get("success"):
            error = envelope.get("error") or {}
            raise ProviderError(str(error.get("code") or "dtk_error"), "DTK rejected the URL")
        data: dict[str, Any] = envelope.get("data") or {}
        if data.get("platform") != "tiktok" or data.get("kind") != "video":
            raise ProviderError("unsupported_media", "DTK result is not a TikTok video")
        video = ((data.get("media") or {}).get("video") or {})
        media_url = video.get("url") if isinstance(video, dict) else None
        if not isinstance(media_url, str) or not media_url.startswith(("http://", "https://")):
            raise ProviderError("no_media_url", "DTK returned no video URL")
        author = data.get("author") or {}
        covers = (data.get("media") or {}).get("covers") or []
        thumbnail = None
        if covers:
            first = covers[0]
            if isinstance(first, str):
                thumbnail = first
            elif isinstance(first, dict):
                thumbnail = first.get("url")
        content_id = str(data.get("content_id") or "video")
        return ResolvedMedia(
            source_url=url,
            provider=self.name,
            media_url=media_url,
            title=data.get("title"),
            author=author.get("nickname") if isinstance(author, dict) else None,
            thumbnail=thumbnail,
            duration=(
                float(video["duration"])
                if isinstance(video, dict) and video.get("duration")
                else None
            ),
            filename=safe_filename(f"tiktok-{content_id}.mp4"),
            content_type="video/mp4",
            created_at=time.time(),
        )

from __future__ import annotations

import time
from urllib.parse import urlparse

import httpx

from ..models import MediaAsset, ResolvedMedia
from ..security import safe_filename
from .base import Provider, ProviderError


class CobaltProvider(Provider):
    name = "cobalt"

    def __init__(self, base_url: str | None, api_key: str | None = None) -> None:
        self._base_url = base_url.rstrip("/") + "/" if base_url else None
        self._api_key = api_key

    @property
    def configured(self) -> bool:
        return bool(self._base_url)

    def _media_headers(self, media_url: str) -> dict[str, str]:
        headers: dict[str, str] = {}
        if (
            self._api_key
            and self._base_url
            and urlparse(media_url).netloc == urlparse(self._base_url).netloc
        ):
            headers["Authorization"] = f"Api-Key {self._api_key}"
        return headers

    @staticmethod
    def _content_id(url: str) -> str:
        path_parts = [part for part in urlparse(url).path.split("/") if part]
        if path_parts:
            candidate = path_parts[-1]
            if candidate.isdigit():
                return candidate
        return "post"

    def _parse_response(self, url: str, data: dict) -> ResolvedMedia:
        status = data.get("status")
        media_url: str | None = None
        filename = "tiktok-video.mp4"

        if status in {"tunnel", "redirect"}:
            media_url = data.get("url")
            filename = data.get("filename") or filename
        elif status == "picker":
            picker = data.get("picker") or []
            for item in picker:
                if item.get("type") == "video" and isinstance(item.get("url"), str):
                    media_url = item["url"]
                    break

            if not media_url:
                photos = [
                    item
                    for item in picker
                    if item.get("type") == "photo" and isinstance(item.get("url"), str)
                ]
                if photos:
                    content_id = self._content_id(url)
                    assets = [
                        MediaAsset(
                            kind="photo",
                            media_url=item["url"],
                            filename=safe_filename(
                                item.get("filename")
                                or f"tiktok-{content_id}-{index:02d}.jpg"
                            ),
                            content_type="image/jpeg",
                            upstream_headers=self._media_headers(item["url"]),
                        )
                        for index, item in enumerate(photos, start=1)
                    ]
                    return ResolvedMedia(
                        source_url=url,
                        provider=self.name,
                        media_type="photo_carousel",
                        assets=assets,
                        filename=safe_filename(f"tiktok-{content_id}-photos.zip"),
                        content_type="application/zip",
                        created_at=time.time(),
                    )
        elif status == "error":
            error = data.get("error") or {}
            raise ProviderError(str(error.get("code") or "cobalt_error"), "Cobalt rejected the URL")
        else:
            raise ProviderError("unsupported_response", f"Unsupported Cobalt status: {status}")

        if not media_url or not media_url.startswith(("http://", "https://")):
            raise ProviderError("no_media_url", "Cobalt returned no downloadable media")

        return ResolvedMedia(
            source_url=url,
            provider=self.name,
            media_type="video",
            media_url=media_url,
            filename=safe_filename(filename),
            content_type="video/mp4",
            upstream_headers=self._media_headers(media_url),
            created_at=time.time(),
        )

    async def resolve(self, url: str) -> ResolvedMedia:
        if not self._base_url:
            raise ProviderError("disabled", "Cobalt provider is not configured", retryable=False)
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Api-Key {self._api_key}"
        payload = {
            "url": url,
            "downloadMode": "auto",
            "filenameStyle": "basic",
            "videoQuality": "max",
            "alwaysProxy": True,
            "localProcessing": "disabled",
        }
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=12.0) as client:
                response = await client.post(self._base_url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise ProviderError("request_failed", str(exc)) from exc
        return self._parse_response(url, data)

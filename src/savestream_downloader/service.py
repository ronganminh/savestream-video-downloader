from __future__ import annotations

import time
import uuid

from .config import Settings
from .models import ResolvedMedia, ResolveItem, ResolveResponse
from .orchestrator import DownloaderOrchestrator
from .security import DownloadTokenSigner, url_cache_key, validate_tiktok_url
from .store import Store


class MediaPolicyError(RuntimeError):
    pass


class DownloaderService:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        orchestrator: DownloaderOrchestrator,
        signer: DownloadTokenSigner,
    ) -> None:
        self.settings = settings
        self.store = store
        self.orchestrator = orchestrator
        self.signer = signer

    def _enforce_policy(self, media: ResolvedMedia) -> None:
        if media.duration is not None and media.duration > self.settings.max_duration_seconds:
            raise MediaPolicyError("Video duration exceeds the configured limit")
        if media.media_type == "photo_carousel":
            if not media.assets:
                raise MediaPolicyError("Photo carousel contains no downloadable photos")
            if len(media.assets) > self.settings.max_carousel_items:
                raise MediaPolicyError("Photo carousel exceeds the configured item limit")

    async def resolve(self, url: str) -> ResolveResponse:
        url = validate_tiktok_url(url)
        key = f"resolve:{url_cache_key(url)}"
        cached_payload = await self.store.get_json(key)
        cached = cached_payload is not None
        if cached_payload:
            media = ResolvedMedia.model_validate(cached_payload)
        else:
            media = await self.orchestrator.resolve(url)
            self._enforce_policy(media)
            await self.store.set_json(key, media.model_dump(), self.settings.cache_ttl_seconds)
        self._enforce_policy(media)
        request_id = uuid.uuid4().hex
        await self.store.set_json(
            f"download:{request_id}", media.model_dump(), self.settings.download_ttl_seconds
        )
        token = self.signer.create(request_id)

        items: list[ResolveItem] = []
        download_url: str | None = None
        download_all_url: str | None = None
        if media.media_type == "video":
            download_url = f"/v1/download/{token}"
        else:
            download_all_url = f"/v1/download/{token}/all"
            download_url = download_all_url
            items = [
                ResolveItem(
                    index=index,
                    kind=asset.kind,
                    filename=asset.filename,
                    content_type=asset.content_type,
                    download_url=f"/v1/download/{token}/item/{index}",
                )
                for index, asset in enumerate(media.assets)
            ]

        response_thumbnail = media.thumbnail
        if media.media_type == "photo_carousel" and not response_thumbnail and items:
            response_thumbnail = items[0].download_url

        return ResolveResponse(
            request_id=request_id,
            source="tiktok",
            media_type=media.media_type,
            title=media.title,
            author=media.author,
            thumbnail=response_thumbnail,
            duration=media.duration,
            filename=media.filename,
            provider=media.provider,
            cached=cached,
            expires_in=self.settings.download_ttl_seconds,
            download_url=download_url,
            download_all_url=download_all_url,
            items=items,
        )

    async def refresh_download(self, request_id: str, source_url: str) -> ResolvedMedia:
        media = await self.orchestrator.resolve(source_url)
        self._enforce_policy(media)
        await self.store.set_json(
            f"download:{request_id}", media.model_dump(), self.settings.download_ttl_seconds
        )
        return media

    async def media_for_download(self, token: str) -> tuple[str, ResolvedMedia]:
        request_id = self.signer.verify(token, self.settings.download_ttl_seconds)
        payload = await self.store.get_json(f"download:{request_id}")
        if not payload:
            raise KeyError("download_not_found")
        media = ResolvedMedia.model_validate(payload)
        age = time.time() - media.created_at
        if age >= self.settings.media_refresh_after_seconds:
            media = await self.orchestrator.resolve(media.source_url)
            self._enforce_policy(media)
            await self.store.set_json(
                f"download:{request_id}", media.model_dump(), self.settings.download_ttl_seconds
            )
        return request_id, media

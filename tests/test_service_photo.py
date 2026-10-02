from types import SimpleNamespace

import pytest

pytest.importorskip("redis")

from savestream_downloader.models import MediaAsset, ResolvedMedia
from savestream_downloader.security import DownloadTokenSigner
from savestream_downloader.service import DownloaderService
from savestream_downloader.store import MemoryStore


class FakeOrchestrator:
    async def resolve(self, url: str) -> ResolvedMedia:
        return ResolvedMedia(
            source_url=url,
            provider="cobalt",
            media_type="photo_carousel",
            assets=[
                MediaAsset(
                    kind="photo",
                    media_url="https://cdn.example/1.jpg",
                    filename="one.jpg",
                    content_type="image/jpeg",
                ),
                MediaAsset(
                    kind="photo",
                    media_url="https://cdn.example/2.jpg",
                    filename="two.jpg",
                    content_type="image/jpeg",
                ),
            ],
            filename="photos.zip",
            content_type="application/zip",
            created_at=1.0,
        )


@pytest.mark.asyncio
async def test_photo_resolve_returns_items_and_zip_link() -> None:
    settings = SimpleNamespace(
        max_duration_seconds=900,
        max_carousel_items=50,
        cache_ttl_seconds=45,
        download_ttl_seconds=300,
        media_refresh_after_seconds=60,
    )
    service = DownloaderService(
        settings,  # type: ignore[arg-type]
        MemoryStore(),
        FakeOrchestrator(),  # type: ignore[arg-type]
        DownloadTokenSigner("secret"),
    )

    response = await service.resolve("https://www.tiktok.com/@user/photo/123")

    assert response.media_type == "photo_carousel"
    assert response.download_url == response.download_all_url
    assert response.download_all_url is not None
    assert response.download_all_url.endswith("/all")
    assert len(response.items) == 2
    assert response.items[0].download_url.endswith("/item/0")
    assert response.thumbnail == response.items[0].download_url

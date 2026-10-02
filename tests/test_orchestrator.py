import time

import pytest

from savestream_downloader.models import ResolvedMedia
from savestream_downloader.orchestrator import DownloaderOrchestrator
from savestream_downloader.providers.base import Provider, ProviderError


class FailingProvider(Provider):
    name = "first"

    @property
    def configured(self) -> bool:
        return True

    async def resolve(self, url: str) -> ResolvedMedia:
        raise ProviderError("broken", "nope")


class SuccessProvider(Provider):
    name = "second"

    @property
    def configured(self) -> bool:
        return True

    async def resolve(self, url: str) -> ResolvedMedia:
        return ResolvedMedia(
            source_url=url,
            provider=self.name,
            media_url="https://cdn.example/video.mp4",
            filename="video.mp4",
            created_at=time.time(),
        )


@pytest.mark.asyncio
async def test_falls_back_to_second_provider() -> None:
    orchestrator = DownloaderOrchestrator(
        providers={"first": FailingProvider(), "second": SuccessProvider()},
        order=("first", "second"),
        timeout_seconds=2,
    )
    result = await orchestrator.resolve("https://www.tiktok.com/@a/video/1")
    assert result.provider == "second"

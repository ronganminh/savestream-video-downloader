from __future__ import annotations

import asyncio
import logging
import time

from prometheus_client import Counter, Histogram

from .models import ResolvedMedia
from .providers.base import Provider, ProviderError

logger = logging.getLogger(__name__)

PROVIDER_ATTEMPTS = Counter(
    "savestream_downloader_provider_attempts_total",
    "Provider resolve attempts",
    ["provider", "outcome"],
)
PROVIDER_LATENCY = Histogram(
    "savestream_downloader_provider_latency_seconds",
    "Provider resolve latency",
    ["provider"],
)


class AllProvidersFailed(RuntimeError):
    def __init__(self, errors: list[tuple[str, str]]) -> None:
        super().__init__("All downloader providers failed")
        self.errors = errors


class DownloaderOrchestrator:
    def __init__(
        self,
        providers: dict[str, Provider],
        order: tuple[str, ...],
        timeout_seconds: int,
    ) -> None:
        self.providers = providers
        self.order = order
        self.timeout_seconds = timeout_seconds

    async def resolve(self, url: str) -> ResolvedMedia:
        errors: list[tuple[str, str]] = []
        for name in self.order:
            provider = self.providers.get(name)
            if provider is None or not provider.configured:
                continue
            started = time.monotonic()
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    result = await provider.resolve(url)
                PROVIDER_ATTEMPTS.labels(provider=name, outcome="success").inc()
                PROVIDER_LATENCY.labels(provider=name).observe(time.monotonic() - started)
                return result
            except TimeoutError:
                PROVIDER_ATTEMPTS.labels(provider=name, outcome="timeout").inc()
                errors.append((name, "timeout"))
                logger.warning("provider_timeout provider=%s", name)
            except ProviderError as exc:
                PROVIDER_ATTEMPTS.labels(provider=name, outcome="error").inc()
                errors.append((name, exc.code))
                logger.warning("provider_error provider=%s code=%s", name, exc.code)
                if not exc.retryable:
                    break
            except Exception as exc:
                PROVIDER_ATTEMPTS.labels(provider=name, outcome="error").inc()
                errors.append((name, "unexpected"))
                logger.exception("provider_unexpected provider=%s error=%s", name, exc)
        raise AllProvidersFailed(errors)

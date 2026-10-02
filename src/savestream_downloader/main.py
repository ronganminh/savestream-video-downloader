from __future__ import annotations

import logging
import tempfile
import zipfile
from contextlib import asynccontextmanager
from typing import AsyncIterator, BinaryIO

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .config import Settings
from .models import HealthResponse, MediaAsset, ResolveRequest, ResolveResponse, ResolvedMedia
from .orchestrator import AllProvidersFailed, DownloaderOrchestrator
from .providers.cobalt import CobaltProvider
from .providers.dtk import DtkProvider
from .providers.ytdlp import YtDlpProvider
from .rate_limit import RateLimiter
from .security import DownloadTokenSigner, client_bucket, require_internal_key, safe_filename
from .service import DownloaderService, MediaPolicyError
from .store import Store, create_store

settings = Settings.from_env()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def build_orchestrator() -> DownloaderOrchestrator:
    providers = {
        "ytdlp": YtDlpProvider(settings.enable_ytdlp),
        "cobalt": CobaltProvider(settings.cobalt_url, settings.cobalt_api_key),
        "dtk": DtkProvider(settings.dtk_url, settings.dtk_api_key, settings.dtk_wait_seconds),
    }
    return DownloaderOrchestrator(
        providers, settings.provider_order, settings.provider_timeout_seconds
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = await create_store(settings.redis_url)
    orchestrator = build_orchestrator()
    signer = DownloadTokenSigner(settings.token_secret)
    app.state.store = store
    app.state.orchestrator = orchestrator
    app.state.rate_limiter = RateLimiter(store)
    app.state.service = DownloaderService(settings, store, orchestrator, signer)
    logger.info("service_started store=%s providers=%s", store.name, orchestrator.order)
    try:
        yield
    finally:
        await store.close()


app = FastAPI(
    title="SaveStream Video Downloader",
    version="0.2.0",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)


def get_store(request: Request) -> Store:
    return request.app.state.store


def get_service(request: Request) -> DownloaderService:
    return request.app.state.service


def get_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


async def internal_auth(x_savestream_service_key: str | None = Header(default=None)) -> None:
    await require_internal_key(settings, x_savestream_service_key)


def client_identity(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    return client_bucket(host)


@app.get("/healthz", response_model=HealthResponse)
async def healthz(request: Request) -> HealthResponse:
    orchestrator: DownloaderOrchestrator = request.app.state.orchestrator
    return HealthResponse(
        status="ok",
        store=request.app.state.store.name,
        providers={name: provider.configured for name, provider in orchestrator.providers.items()},
    )


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/resolve", response_model=ResolveResponse, dependencies=[Depends(internal_auth)])
async def resolve_media(
    payload: ResolveRequest,
    request: Request,
    service: DownloaderService = Depends(get_service),
    limiter: RateLimiter = Depends(get_limiter),
) -> ResolveResponse:
    await limiter.check(
        f"resolve:{client_identity(request)}", settings.resolve_rate_limit_per_minute
    )
    try:
        return await service.resolve(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MediaPolicyError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except AllProvidersFailed as exc:
        logger.warning("all_providers_failed errors=%s", exc.errors)
        raise HTTPException(
            status_code=422, detail="Unable to resolve this public TikTok post"
        ) from exc


async def _open_media_url(
    media_url: str,
    upstream_headers: dict[str, str],
    range_header: str | None = None,
) -> tuple[httpx.AsyncClient, httpx.Response]:
    headers = dict(upstream_headers)
    if range_header:
        headers["Range"] = range_header
    client = httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(20.0, read=None))
    try:
        upstream_request = client.build_request("GET", media_url, headers=headers)
        response = await client.send(upstream_request, stream=True)
        if response.status_code >= 400:
            body = await response.aread()
            await response.aclose()
            await client.aclose()
            raise HTTPException(
                status_code=502,
                detail=f"Upstream media request failed ({response.status_code}, {len(body)} bytes)",
            )
        return client, response
    except Exception:
        await client.aclose()
        raise


def _check_content_length(upstream: httpx.Response) -> None:
    content_length = upstream.headers.get("content-length")
    if (
        content_length
        and content_length.isdigit()
        and int(content_length) > settings.max_file_size_bytes
    ):
        raise HTTPException(status_code=413, detail="Media file exceeds the configured size limit")


def _stream_response(
    client: httpx.AsyncClient,
    upstream: httpx.Response,
    filename: str,
    fallback_content_type: str,
) -> StreamingResponse:
    async def iterator() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_bytes(64 * 1024):
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    headers = {
        "Content-Disposition": f'attachment; filename="{safe_filename(filename)}"',
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    for header in ("content-length", "content-range", "accept-ranges"):
        if upstream.headers.get(header):
            headers[header.title()] = upstream.headers[header]
    return StreamingResponse(
        iterator(),
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", fallback_content_type),
        headers=headers,
    )


async def _resolve_download(
    token: str, service: DownloaderService
) -> tuple[str, ResolvedMedia]:
    try:
        return await service.media_for_download(token)
    except KeyError as exc:
        raise HTTPException(status_code=410, detail="Download link expired") from exc
    except MediaPolicyError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except AllProvidersFailed as exc:
        raise HTTPException(status_code=502, detail="Unable to refresh media URL") from exc


async def _open_video_with_refresh(
    request_id: str,
    media: ResolvedMedia,
    service: DownloaderService,
    range_header: str | None,
) -> tuple[ResolvedMedia, httpx.AsyncClient, httpx.Response]:
    if media.media_type != "video" or not media.media_url:
        raise HTTPException(status_code=409, detail="This TikTok post is a photo carousel")
    try:
        client, upstream = await _open_media_url(
            media.media_url, media.upstream_headers, range_header
        )
        return media, client, upstream
    except HTTPException as exc:
        if exc.status_code != 502:
            raise
        try:
            refreshed = await service.refresh_download(request_id, media.source_url)
        except AllProvidersFailed as refresh_exc:
            raise HTTPException(status_code=502, detail="Unable to refresh media URL") from refresh_exc
        if refreshed.media_type != "video" or not refreshed.media_url:
            raise HTTPException(status_code=409, detail="TikTok post type changed while refreshing")
        client, upstream = await _open_media_url(
            refreshed.media_url, refreshed.upstream_headers, range_header
        )
        return refreshed, client, upstream


@app.get("/v1/download/{token}", dependencies=[Depends(internal_auth)])
async def download_video(
    token: str,
    request: Request,
    range_header: str | None = Header(default=None, alias="Range"),
    service: DownloaderService = Depends(get_service),
    limiter: RateLimiter = Depends(get_limiter),
) -> StreamingResponse:
    await limiter.check(
        f"download:{client_identity(request)}", settings.download_rate_limit_per_minute
    )
    request_id, media = await _resolve_download(token, service)
    media, client, upstream = await _open_video_with_refresh(
        request_id, media, service, range_header
    )
    try:
        _check_content_length(upstream)
    except HTTPException:
        await upstream.aclose()
        await client.aclose()
        raise
    return _stream_response(client, upstream, media.filename, media.content_type)


def _asset_at(media: ResolvedMedia, index: int) -> MediaAsset:
    if media.media_type != "photo_carousel":
        raise HTTPException(status_code=409, detail="This TikTok post is not a photo carousel")
    if index < 0 or index >= len(media.assets):
        raise HTTPException(status_code=404, detail="Photo not found")
    return media.assets[index]


async def _open_asset_with_refresh(
    request_id: str,
    media: ResolvedMedia,
    index: int,
    service: DownloaderService,
    range_header: str | None,
) -> tuple[MediaAsset, httpx.AsyncClient, httpx.Response]:
    asset = _asset_at(media, index)
    try:
        client, upstream = await _open_media_url(
            asset.media_url, asset.upstream_headers, range_header
        )
        return asset, client, upstream
    except HTTPException as exc:
        if exc.status_code != 502:
            raise
        try:
            refreshed = await service.refresh_download(request_id, media.source_url)
        except AllProvidersFailed as refresh_exc:
            raise HTTPException(status_code=502, detail="Unable to refresh photo URL") from refresh_exc
        asset = _asset_at(refreshed, index)
        client, upstream = await _open_media_url(
            asset.media_url, asset.upstream_headers, range_header
        )
        return asset, client, upstream


@app.get("/v1/download/{token}/item/{index}", dependencies=[Depends(internal_auth)])
async def download_photo(
    token: str,
    index: int,
    request: Request,
    range_header: str | None = Header(default=None, alias="Range"),
    service: DownloaderService = Depends(get_service),
    limiter: RateLimiter = Depends(get_limiter),
) -> StreamingResponse:
    await limiter.check(
        f"download:{client_identity(request)}", settings.download_rate_limit_per_minute
    )
    request_id, media = await _resolve_download(token, service)
    asset, client, upstream = await _open_asset_with_refresh(
        request_id, media, index, service, range_header
    )
    try:
        _check_content_length(upstream)
    except HTTPException:
        await upstream.aclose()
        await client.aclose()
        raise
    return _stream_response(client, upstream, asset.filename, asset.content_type)


def _unique_archive_name(filename: str, used: set[str], index: int) -> str:
    candidate = safe_filename(filename)
    if candidate not in used:
        used.add(candidate)
        return candidate
    if "." in candidate:
        stem, extension = candidate.rsplit(".", 1)
        candidate = f"{stem}-{index + 1}.{extension}"
    else:
        candidate = f"{candidate}-{index + 1}"
    used.add(candidate)
    return candidate


async def _build_photo_archive(media: ResolvedMedia) -> tuple[BinaryIO, int]:
    if media.media_type != "photo_carousel" or not media.assets:
        raise HTTPException(status_code=409, detail="This TikTok post is not a photo carousel")

    output = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024, mode="w+b")
    total_uncompressed = 0
    used_names: set[str] = set()
    try:
        with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED) as archive:
            for index, asset in enumerate(media.assets):
                client, upstream = await _open_media_url(
                    asset.media_url, asset.upstream_headers, None
                )
                try:
                    length = upstream.headers.get("content-length")
                    if length and length.isdigit():
                        if total_uncompressed + int(length) > settings.max_file_size_bytes:
                            raise HTTPException(
                                status_code=413,
                                detail="Photo archive exceeds the configured size limit",
                            )
                    archive_name = _unique_archive_name(asset.filename, used_names, index)
                    with archive.open(archive_name, mode="w") as destination:
                        async for chunk in upstream.aiter_bytes(64 * 1024):
                            total_uncompressed += len(chunk)
                            if total_uncompressed > settings.max_file_size_bytes:
                                raise HTTPException(
                                    status_code=413,
                                    detail="Photo archive exceeds the configured size limit",
                                )
                            destination.write(chunk)
                finally:
                    await upstream.aclose()
                    await client.aclose()
        output.seek(0, 2)
        archive_size = output.tell()
        output.seek(0)
        return output, archive_size
    except Exception:
        output.close()
        raise


async def _build_archive_with_refresh(
    request_id: str, media: ResolvedMedia, service: DownloaderService
) -> tuple[ResolvedMedia, BinaryIO, int]:
    try:
        archive, size = await _build_photo_archive(media)
        return media, archive, size
    except HTTPException as exc:
        if exc.status_code != 502:
            raise
        try:
            refreshed = await service.refresh_download(request_id, media.source_url)
        except AllProvidersFailed as refresh_exc:
            raise HTTPException(status_code=502, detail="Unable to refresh photo URLs") from refresh_exc
        archive, size = await _build_photo_archive(refreshed)
        return refreshed, archive, size


@app.get("/v1/download/{token}/all", dependencies=[Depends(internal_auth)])
async def download_photo_archive(
    token: str,
    request: Request,
    service: DownloaderService = Depends(get_service),
    limiter: RateLimiter = Depends(get_limiter),
) -> StreamingResponse:
    await limiter.check(
        f"download:{client_identity(request)}", settings.download_rate_limit_per_minute
    )
    request_id, media = await _resolve_download(token, service)
    media, archive, archive_size = await _build_archive_with_refresh(request_id, media, service)

    async def iterator() -> AsyncIterator[bytes]:
        try:
            while True:
                chunk = archive.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            archive.close()

    return StreamingResponse(
        iterator(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename(media.filename)}"',
            "Content-Length": str(archive_size),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )

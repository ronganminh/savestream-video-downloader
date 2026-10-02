import pytest

from savestream_downloader.security import validate_tiktok_url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.tiktok.com/@user/video/123",
        "https://www.tiktok.com/@user/photo/123",
        "https://vm.tiktok.com/abc/",
        "https://vt.tiktok.com/xyz/",
        "https://m.tiktok.com/v/123.html",
    ],
)
def test_accepts_tiktok_urls(url: str) -> None:
    assert validate_tiktok_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/video/123",
        "https://tiktok.com.evil.example/video/123",
        "file:///etc/passwd",
        "javascript:alert(1)",
    ],
)
def test_rejects_non_tiktok_urls(url: str) -> None:
    with pytest.raises(ValueError):
        validate_tiktok_url(url)

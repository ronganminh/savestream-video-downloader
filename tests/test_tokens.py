import pytest
from fastapi import HTTPException

from savestream_downloader.security import DownloadTokenSigner


def test_download_token_round_trip() -> None:
    signer = DownloadTokenSigner("secret")
    token = signer.create("abc123")
    assert signer.verify(token, 60) == "abc123"


def test_invalid_download_token_is_rejected() -> None:
    signer = DownloadTokenSigner("secret")
    with pytest.raises(HTTPException):
        signer.verify("not-a-token", 60)

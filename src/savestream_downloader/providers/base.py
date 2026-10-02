from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import ResolvedMedia


class ProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class Provider(ABC):
    name: str

    @property
    @abstractmethod
    def configured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def resolve(self, url: str) -> ResolvedMedia:
        raise NotImplementedError

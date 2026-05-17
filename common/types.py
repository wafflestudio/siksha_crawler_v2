from typing import Any, Protocol, TypeAlias


Payload: TypeAlias = dict[str, Any]
CrawlFailure: TypeAlias = tuple[str, Exception]
CrawlResult: TypeAlias = tuple[list[Payload], list[CrawlFailure]]


class CrawlFunction(Protocol):
    def __call__(self) -> CrawlResult:
        ...


class Generalizer(Protocol):
    def generalize_cafeteria(self, *args: Any, **kwargs: Any) -> list[Payload]:
        ...

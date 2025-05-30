from typing import List, Callable, Any, TypedDict, Protocol, Unpack, overload
from aiohttp import ClientSession

from arc_crawler.reader import JsonSerializable


class BasicResponse(TypedDict):
    text: str | None
    json: Any | None
    status: int
    ok: bool
    url: str


class TerminationFuncKwargs(TypedDict):
    status_code: int
    url: str


class TerminationFunc(Protocol):
    def __call__(self, **kwargs: Unpack[TerminationFuncKwargs]) -> Exception:
        pass


TerminationCriteria = TerminationFunc | List[int | range]

RequestProcessor = Callable[[str], None]


class ResponseHandlerKwargs(TypedDict):
    response: BasicResponse
    session: ClientSession


class OnResponseCallback(Protocol):
    @overload
    async def __call__(self, **kwargs: Unpack[ResponseHandlerKwargs]) -> None:
        pass

    def __call__(self, **kwargs: Unpack[ResponseHandlerKwargs]) -> None:
        pass


class OnRequestCallback(Protocol):
    @overload
    async def __call__(self, url: str) -> None:
        pass

    def __call__(self, url: str) -> None:
        pass


class ResponseProcessor(Protocol):
    @overload
    async def __call__(self, **kwargs: Unpack[ResponseHandlerKwargs]) -> JsonSerializable:
        pass

    def __call__(self, **kwargs: Unpack[ResponseHandlerKwargs]) -> JsonSerializable:
        pass

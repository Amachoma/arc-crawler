from functools import wraps
from typing import List
from aiohttp import ClientSession

from .types import OnRequestCallback, OnResponseCallback


def session_decorator(func):
    @wraps(func)
    async def wrapper(
        self,
        urls: List[str],
        on_response: OnResponseCallback,
        on_request: OnRequestCallback | None = None,
        min_request_delay: int | float = 0,
        session: ClientSession | None = None,
        **kwargs,
    ):
        is_new_session = session is None
        local_session: ClientSession = ClientSession(**kwargs) if is_new_session else session

        res = await func(
            self,
            urls=urls,
            on_response=on_response,
            on_request=on_request,
            min_request_delay=min_request_delay,
            session=local_session,
        )
        if is_new_session:
            await local_session.close()

        return res

    return wrapper

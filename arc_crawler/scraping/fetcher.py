import json
from abc import ABC, abstractmethod
from asyncio import Semaphore
from typing import List, Unpack, Dict, Any
import inspect

import aiohttp
from aiohttp import ClientSession
import asyncio
from contextlib import asynccontextmanager

import logging

logger = logging.getLogger(__name__)

from .types import TerminationFunc, TerminationCriteria, OnResponseCallback, OnRequestCallback, TerminationFuncKwargs
from .decorators import session_decorator


class Fetcher(ABC):
    """Abstract base class for URL fetchers.

    This class defines the essential interface and core functionalities that
    all URL fetcher implementations should inherit and provide. Extend this
    class to create your own custom fetchers.

    Example:
            To create custom fetcher:

            >>> from arc_crawler import Fetcher
            >>> class CustomFetcher(Fetcher):
            >>> 	def get(self, urls, on_fulfilled, on_request, min_request_delay, session, **kwargs) -> None:
            >>> 		pass
    """

    def __init__(self, termination_criteria: TerminationCriteria | None = None):
        """Initializes an abstract `Fetcher` instance.

        Args:
            termination_criteria (TerminationCriteria): Defines when the fetcher should stop processing requests
                based on status codes or custom logic. This argument accepts one of two types:

                * `List[int | range]`: Terminates the process if any of the specified
                  HTTP status codes are encountered. You can include individual
                  integer codes (e.g., `404`, `500`) or `range` objects (e.g., `range(400, 500)`)
                  to easily cover a series of codes. Used for stopping on known error statuses.

                * `Callable[..., Exception]`: A function that accepts keyword arguments
                  matching `TerminationFuncKwargs` (`status_code: int`, `url: str`).
                  This function should return an `Exception` instance,
                  which will be raised to terminate the process.
                  Use this to explicitly handle irregular cases.
        """

        def handle_response_status(**kwargs: Unpack[TerminationFuncKwargs]) -> Exception | None:
            status_details = {
                429: "Too Many Requests. Consider increasing delay between requests.",
                500: "Internal Server Error. Check if server is up and try again later.",
            }
            termination_codes = termination_criteria or list(status_details.keys())

            for code in termination_codes:
                is_range = isinstance(code, range)
                if (is_range and kwargs["status_code"] in code) or (not is_range and kwargs["status_code"] == code):
                    exception_text = f'[{kwargs["status_code"]}] Termination status code encountered for "{kwargs["url"]}."{status_details.get(kwargs["status_code"], "")}'
                    logger.error(exception_text)
                    return Exception(
                        "Exception was triggered manually according to termination_criteria param. Consider changing "
                        "termination codes or providing custom handler function."
                    )

        self._validate_status: TerminationFunc = (
            termination_criteria if callable(termination_criteria) else handle_response_status
        )

    @abstractmethod
    async def get(
        self,
        urls: List[str],
        on_response: OnResponseCallback,
        on_request: OnRequestCallback | None,
        min_request_delay: int | float | None,
        session: ClientSession | None,
        **kwargs: Dict[str, Any] | None,
    ) -> None:
        """Asynchronously fetches content from a list of URLs.

        This abstract method defines the core logic for how concrete `Fetcher` implementations
        should acquire and process web content. Subclasses *must* provide a concrete,
        non-abstract implementation for this method.

        Args:
            urls (List[str]): A list of URLs to fetch.
            on_response (scraping.OnResponseCallback): A synchronous or asynchronous callback
                function executed for each URL successfully fetched. It receives keyword
                arguments as defined in `ResponseHandlerKwargs`: `response: scraping.BasicResponse`
                and `session: aiohttp.ClientSession`. The `response` is typically used to
                format and output fetching results, while `session` allows for additional
                network requests (e.g., logging to a remote service). Implementations must
                ensure this callback is passed to `self._do_request`.

            on_request (scraping.OnRequestCallback, optional): A synchronous or asynchronous
                callback function executed just before each HTTP request is made. It receives
                the URL being requested. Implementations must ensure this callback is passed
                to `self._do_request`.

            min_request_delay (int | float, optional): The minimum delay in seconds to wait
                between consecutive requests to avoid overwhelming the server. Implementations
                must respect this delay.

            session (aiohttp.ClientSession, optional): The HTTP client session to use for requests.
                To automate session management apply scrapping.session_decorator to `get()` implementation.

        Returns:
            None: This method does not return any value directly. For flexibility, fetching
            results and status are handled on a per-response basis via the `on_request` and
            `on_response` callbacks.

        Examples:
            Nothing to show due to abstract method examples depend on implementation.
        """
        pass

    async def _do_request(
        self,
        session: ClientSession,
        url: str,
        on_response: OnResponseCallback,
        on_request: OnRequestCallback | None = None,
    ):
        if on_request is not None and callable(on_request):
            before_request = on_request(url=url)
            if inspect.isawaitable(before_request):
                await before_request

        response = await session.get(url)

        exception = self._validate_status(status_code=response.status, url=url)
        if exception:
            raise exception

        content_type = response.headers.get("Content-Type", "").lower()

        payload_obj = {
            "text": "",
            "json": {},
            "status": response.status,
            "ok": response.ok,
            "url": response.url,
        }
        if "application/json" in content_type:
            try:
                payload_obj["json"] = await response.json(
                    encoding="utf-8", loads=json.loads, content_type="application/json"
                )
            except aiohttp.ContentTypeError:
                logger.warning(f"Unable to process JSON from '{url}'. It could be a malformed.")
            except Exception as e:
                logger.warning(f"Unable to process JSON from '{url}'. Details: {e}")
        else:
            payload_obj["text"] = await response.text()

        kwargs = {"response": payload_obj, "session": session}

        if inspect.iscoroutinefunction(on_response):
            return await on_response(**kwargs)
        else:
            return on_response(**kwargs)

    @classmethod
    @asynccontextmanager
    async def _arrange_session(cls, session: ClientSession | None, **kwargs):
        """Manages an aiohttp.ClientSession for flexible HTTP requests.

        This method acts as an **explicit context manager** for advanced scenarios
        where you need granular control over session creation and lifecycle, or
        as an alternative to the `scraping.session_decorator`.

        Args:
            session (aiohttp.ClientSession | None): An existing `aiohttp.ClientSession` instance to use.
                If `None`, a new session will be created.

            **kwargs: Keyword arguments to be passed to the `aiohttp.ClientSession` constructor if a new session
                needs to be created (i.e., when `session` is `None`). Examples include `headers`, `cookies`,
                `proxy`, `timeout`, etc.

        Yields:
            aiohttp.ClientSession: An active `aiohttp.ClientSession` instance. This session is either
            the one provided or a newly created one. It's automatically closed upon exiting the context
            if it was created by this context manager.
        """
        is_new_session = session is None
        session_instance: ClientSession = ClientSession(**kwargs) if is_new_session else session

        try:
            yield session_instance
        finally:
            # When session wasn't provided and async operations are finished
            # Used to close top-level session upon operations completed
            if is_new_session:
                await session_instance.close()


class ParallelFetcher(Fetcher):
    """A `Fetcher` implementation optimized for high-speed, parallel URL processing.

    This fetcher prioritizes **download effectiveness** by initiating requests for subsequent
    URLs without waiting for previous ones to complete. It's designed for scenarios
    where rapid data acquisition is paramount.


    **Important Considerations:**
        * **Rate Limits:** Always respect the target domain's rate limits to avoid service interruptions.
        * **Resource Consumption:** Parallel fetching can consume significant network bandwidth and local resources. In order to limit maximum number of parallel requests at a time use `max_concurrent_requests` argument.
        * **Response Order:** Although requests are sent in listed order, response order could differ based on a number of factors.
    """

    def __init__(
        self, max_concurrent_requests: int | None = None, termination_criteria: TerminationCriteria | None = None
    ):
        """Initializes a `ParallelFetcher` instance.

        Args:
            max_concurrent_requests (int | None): The maximum number of asynchronous
                        HTTP requests to execute in parallel. This parameter is crucial for
                        managing the **CPU and memory load** on your system.

                        * If set to `None` (default), the fetcher will attempt to run as many requests
                          concurrently as network and system resources allow. Use with caution for very large URL lists.
                        * Setting an integer value limits the number of simultaneous function calls,
                          helping to prevent resource exhaustion.

            termination_criteria (TerminationCriteria): Defines when the fetcher should stop processing requests
                        based on status codes or custom logic. This argument accepts one of two types:

                        * `List[int | range]`: Terminates the process if any of the specified
                          HTTP status codes are encountered. You can include individual
                          integer codes (e.g., `404`, `500`) or `range` objects (e.g., `range(400, 500)`)
                          to easily cover a series of codes. Used for stopping on known error statuses.

                        * `Callable[..., Exception]`: A function that accepts keyword arguments
                          matching `TerminationFuncKwargs` (`status_code: int`, `url: str`).
                          This function should return an `Exception` instance,
                          which will be raised to terminate the process.
                          Use this to explicitly handle irregular cases.
        Examples:

                1. To initialize with minimal arguments:

                >>> from arc_crawler import ParallelFetcher
                >>> fetcher = ParallelFetcher()

                2. To terminate program when status code > 2XX encountered:

                >>> from arc_crawler import ParallelFetcher
                >>> fetcher = ParallelFetcher(termination_criteria=[range(300, 600)])
        """
        super().__init__(termination_criteria)
        self.max_concurrent_requests = max_concurrent_requests

    @session_decorator
    async def get(self, urls, on_response, session: ClientSession, on_request=None, min_request_delay=0):
        """Asynchronously fetches content from a list of URLs.

        Args:
            urls (List[str]): A list of URLs to fetch.

            on_response (scraping.OnResponseCallback): A synchronous or asynchronous callback
                function executed for each URL successfully fetched. It receives keyword
                arguments as defined in `ResponseHandlerKwargs`: `response: scraping.BasicResponse`
                and `session: aiohttp.ClientSession`. The `response` is typically used to
                format and output fetching results, while `session` allows for additional
                network requests (e.g., logging to a remote service). Implementations must
                ensure this callback is passed to `self._do_request`.

            on_request (scraping.OnRequestCallback, optional): A synchronous or asynchronous
                callback function executed just before each HTTP request is made. It receives
                the URL being requested. Implementations must ensure this callback is passed
                to `self._do_request`.

            min_request_delay (int | float, optional): The minimum delay in seconds to wait
                between consecutive requests to avoid overwhelming the server. Implementations
                must respect this delay.

            session (aiohttp.ClientSession, optional): The HTTP client session to use for requests.
                To automate session management apply scrapping.session_decorator to `get()` implementation.

        Examples:

                1. To call with minimal arguments:

                >>> from arc_crawler import ParallelFetcher
                >>> fetcher = ParallelFetcher()
                >>>
                >>> def printer(*args, **kwargs):
                >>> 	print(*args, **kwargs)
                >>>
                >>> fetcher.get(["https://example.com"], on_response=printer)

                2. To write response while making sure to wait half a second before sending next request:

                >>> from arc_crawler import ParallelFetcher, ResponseHandlerKwargs
                >>> fetcher = ParallelFetcher()
                >>>
                >>> def response_writer(**kwargs: Unpack[ResponseHandlerKwargs]):
                >>>     with open('data.json', 'w', encoding="utf-8") as output:
                >>>         output.write(json.dumps(kwargs["response"], ensure_ascii=False))
                >>>
                >>>	fetcher.get(["https://example.com"], on_response=response_writer, min_request_delay=0.5)
        """

        async def run_parallel_tasks():
            last_request_time = 0

            async def fetch(url: str, target_time: int | float):
                nonlocal last_request_time

                current_time = asyncio.get_event_loop().time()
                time_to_sleep = max(
                    target_time - current_time,
                    min_request_delay - (current_time - last_request_time),
                )
                if time_to_sleep > 0:
                    await asyncio.sleep(time_to_sleep)

                last_request_time = asyncio.get_event_loop().time()
                await self._do_request(session=session, url=url, on_response=on_response, on_request=on_request)

            tasks = []
            start_time = asyncio.get_event_loop().time()
            for index in range(len(urls)):
                tasks.append(fetch(urls[index], start_time + min_request_delay * index))

            await asyncio.gather(*tasks)

        if self.max_concurrent_requests:
            async with Semaphore(self.max_concurrent_requests):
                await run_parallel_tasks()
        else:
            await run_parallel_tasks()


class SequentialFetcher(Fetcher):
    """A `Fetcher` implementation designed for complex, sequential URL processing.

    This fetcher prioritizes **flexibility and control** over raw speed, allowing users to
    provide `on_response` callbacks with intricate asynchronous logic. This approach is
    beneficial when you need to:

    * Perform additional requests to the same domain based on the contents of a prior response.
    * Implement complex conditional logic that requires a guaranteed order of execution.
    * Process responses in a strict sequence before proceeding to the next URL.

    **Important Considerations:**

    * Download Speed: As implied by its sequential nature, this fetcher is significantly
      slower than `ParallelFetcher` for large lists of URLs. Each request completes before
      the next one begins.
    * Performance vs. Control: If your primary goal is maximum data acquisition speed
      and your `on_response` logic is less complex or doesn't require strict ordering,
      consider using `ParallelFetcher` first, as it's sufficient for most common tasks.
    """

    @session_decorator
    async def get(self, urls, on_response, session: ClientSession, on_request=None, min_request_delay=0):
        """Asynchronously fetches content from a list of URLs.

        Args:
            urls (List[str]): A list of URLs to fetch.
            on_response (scraping.OnResponseCallback): A synchronous or asynchronous callback
                function executed for each URL successfully fetched. It receives keyword
                arguments as defined in `ResponseHandlerKwargs`: `response: scraping.BasicResponse`
                and `session: aiohttp.ClientSession`. The `response` is typically used to
                format and output fetching results, while `session` allows for additional
                network requests (e.g., logging to a remote service). Implementations must
                ensure this callback is passed to `self._do_request`.

            on_request (scraping.OnRequestCallback, optional): A synchronous or asynchronous
                callback function executed just before each HTTP request is made. It receives
                the URL being requested. Implementations must ensure this callback is passed
                to `self._do_request`.

            min_request_delay (int | float, optional): The minimum delay in seconds to wait
                between consecutive requests to avoid overwhelming the server. Implementations
                must respect this delay.

            session (aiohttp.ClientSession, optional): The HTTP client session to use for requests.
                To automate session management apply scrapping.session_decorator to `get()` implementation.

        Examples:

                        1. To call with minimal arguments:

                        >>> from arc_crawler import SequentialFetcher
                        >>> fetcher = SequentialFetcher()
                        >>> def printer(*args, **kwargs):
                        ...     print(*args, **kwargs)
                        >>> fetcher.get(["https://example.com"], on_response=printer)

                        2. To write response while making sure to wait half a second before sending next request:

                        >>> from arc_crawler import SequentialFetcher, ResponseHandlerKwargs
                        >>> fetcher = SequentialFetcher()
                        >>> def response_writer(**kwargs: Unpack[ResponseHandlerKwargs]):
                        ...     with open("data.json", "w", encoding="utf-8") as output:
                        ...         output.write(json.dumps(kwargs["response"], ensure_ascii=False))
                        >>>	fetcher.get(["https://example.com"], on_response=response_writer, min_request_delay=0.5)
        """
        last_finished_time = 0
        for index in range(len(urls)):
            url = urls[index]

            request_delta = asyncio.get_event_loop().time() - last_finished_time

            if request_delta < min_request_delay:
                await asyncio.sleep(min_request_delay - request_delta)

            await self._do_request(session=session, url=url, on_request=on_request, on_response=on_response)
            last_finished_time = asyncio.get_event_loop().time()

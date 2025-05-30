import logging

logger = logging.getLogger(__name__)

import sys

from typing import List, Dict, Optional, Literal, Any, Unpack
import inspect

from bs4 import BeautifulSoup
import asyncio
from urllib.parse import unquote
import hashlib as hl
import pickle

from pathlib import Path

from arc_crawler.reader import IndexReader, IndexSetterFunc, JsonSerializable, MkdirMode
from arc_crawler.utils import FormatedLogger, Timer

from .fetcher import SequentialFetcher, ParallelFetcher, Fetcher
from .types import BasicResponse, ResponseProcessor, RequestProcessor, ResponseHandlerKwargs, TerminationCriteria


def fallthrough_processor(**kwargs: Unpack[ResponseHandlerKwargs]) -> JsonSerializable:
    return kwargs["response"]


def html_body_processor(**kwargs: Unpack[ResponseHandlerKwargs]) -> JsonSerializable:
    res = kwargs["response"]
    html_soup = BeautifulSoup(res.get("text"), "html.parser")
    body_tag = html_soup.find("body")

    if not body_tag:
        logger.error("html_body_processor was used however there seems to be no <body> tag present in response text")
        raise Exception("Error while processing response. Check if response returns valid HTML with <body> tag in it")

    res["text"] = body_tag.decode_contents()

    return res


def index_url_setter(res: BasicResponse):
    return {"url": res.get("url")}


fetchers = {
    "async": ParallelFetcher,
    "sync": SequentialFetcher,
}


class Crawler:
    """A robust and flexible web crawler designed to simplify common web scraping tasks.

    This class encapsulates a suite of features to streamline the acquisition and
    processing of web content.

    Key Features:

    * **Flexible Fetching Strategies:** Supports both parallel (for high speed) and
      sequential (for precise control) fetching of URLs. Includes customizable
      request delays to respect server rate limits and fit various scraping scenarios.
    * **Structured Output & Customization:** Provides structured response output
      by default, which can be further customized via user-defined callbacks to
      fit specific data extraction and processing needs.
    * **Resumable Progress Tracking:** Automatically tracks fetching progress,
      enabling seamless resumption from the point of interruption. This feature
      is also highly beneficial for incrementally adding new data to existing
      output files without re-fetching already processed URLs.
    * **Efficient Output Management:** Automatically writes **metadata** alongside
      fetched data, making the output easily accessible and navigable, even for
      very large files. These structured output files can be efficiently opened
      and queried using an `IndexReader` instance.

    When to Use This Crawler:
    * For projects requiring efficient and reliable web data extraction.
    * When managing complex scraping flows, such as those needing state persistence or dynamic response handling.
    * To build robust scraping solutions capable of handling network interruptions or planned pauses.

    ---

    **Best Practices**

    Separate Fetching from Parsing.
    A crucial tip for efficient and maintainable web scraping is to **prioritize saving unaltered source data** within
    your `on_response` callbacks. Avoid implementing complex parsing logic directly during the fetching phase itself.

    Downloading a large number of, for instance, HTML pages can take a significant amount of time.
    Separating the parsing into a distinct, post-fetching step offers considerable advantages:

    * **Iterative Improvement:** You can refine and improve your parser implementation incrementally by running new
      versions over your **local output files**, rather than needing to re-fetch all the data each time.
    * **Resilience & Speed:** By focusing purely on data acquisition, the fetching stage becomes
      more resilient to network issues and can often operate at its maximum download speed
      without being bogged down by CPU-intensive parsing.
    * **Resource Management:** Parsing can be quite CPU and memory intensive.
      Offloading it to a separate process or script prevents it from impacting the I/O-bound fetching operations.

    In conclusion, when using this crawler, your primary focus should be on
    **saving the raw, unaltered source data first.** Parsing is a separate, subsequent step that
    should ideally be performed *after* the fetching process has completed.
    """

    def __init__(
        self,
        mode: Literal["async", "sync"] | str = "async",
        out_file_path: str | Path = Path("./out"),
        log_level: Literal["debug", "info", "warn", "error"] = "info",
        fetcher_config: Dict[str, type[Fetcher]] = None,
        mkdir_mode: MkdirMode = "interactive",
        termination_criteria: TerminationCriteria | None = None,
    ):
        """Initializes a `Crawler` instance.

        Args:
            mode ("async" | "sync", optional): Determines the fetching behavior.

                * **"async"**: (Default) The crawler sends multiple requests concurrently,
                  optimizing for speed and throughput. This is suitable for most
                  high-volume scraping tasks.
                * **"sync"**: The crawler sends requests one at a time, in sequence.
                  Use this when strict ordering is required or for debugging.

            out_file_path (str | Path, optional): The directory where fetched data and metadata
                will be stored. Defaults to the local `/out` folder relative to the
                current working directory.

            log_level ("debug" | "info" | "warn" | "error", optional): Controls the verbosity of
                console output.

                * **"error"**: Only logs errors that occur during operation.
                * **"warn"**: Logs both warnings and errors.
                * **"info"**: (Default) Logs general status updates, warnings, and errors.
                * **"debug"**: Provides detailed, developer-centered messages for
                  in-depth monitoring and troubleshooting.

            fetcher_config (dict[str, type[Fetcher]], optional): A dictionary mapping
                custom mode names (string) to `Workspaceer` class implementations (`type[Fetcher]`).
                This argument is intended for advanced or rare cases where built-in fetchers are insufficient.
                The keys in this dictionary will become additional valid options for the `mode` argument.
                (e.g., if you provide `{"custom": CustomFetcher}`, you can then call
                `crawler.get(..., mode="custom")`).

            mkdir_mode ("interactive" | "forced" | "disabled", optional): The strategy
                        to apply if `file_path` points to a non-existent directory or file.

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

            1. To initialize a crawler with minimal arguments:

            >>> from arc_crawler import Crawler
            >>> crawler = Crawler()

            2. To create a silent, synchronous crawler with a custom output directory:

            >>> from arc_crawler import Crawler
            >>> crawler = Crawler(mode="sync", out_file_path="./datasets", log_level="error")
        """
        if fetcher_config is None:
            fetcher_config = fetchers
        fetcher = fetcher_config.get(mode, None)
        if not fetcher:
            logger.error(f"Incorrect mode provided for HtmlFetcher")
            raise ValueError(f"Acceptable values are: f{', '.join([f'"{x}"' for x in fetcher_config.keys()])}")
        self._fetcher = fetcher(termination_criteria=termination_criteria)

        self.out_file_path = out_file_path

        self.out_source = ""
        self.out_index = ""
        self.reader: IndexReader | None = None
        self.index_record_setter = index_url_setter
        self.mkdir_mode = mkdir_mode

        logging_levels = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warn": logging.WARNING,
            "error": logging.ERROR,
        }
        level = logging_levels.get(log_level, logging.INFO)
        root_logger = logging.getLogger()
        root_logger.setLevel(level)

        console_logger = logging.StreamHandler(sys.stdout)
        console_logger.setLevel(level)
        console_logger.setFormatter(FormatedLogger())
        root_logger.addHandler(console_logger)

    def _init_output(self, urls: List[str], out_file_name: Optional[str] = None) -> List[str]:
        def generate_from_hash():
            file_bytes = pickle.dumps(tuple(urls))
            file_hash = hl.sha256(file_bytes).hexdigest()
            return {
                "source": str(Path(self.out_file_path) / f"{file_hash}.jsonl"),
                "index": str(Path(self.out_file_path) / f"{file_hash}.index"),
            }

        if out_file_name is None:
            out_dir = generate_from_hash()
            self.out_source = out_dir["source"]
            self.out_index = out_dir["index"]
        else:
            self.out_source = str(Path(self.out_file_path) / f"{out_file_name}.jsonl")
            self.out_index = str(Path(self.out_file_path) / f"{out_file_name}.index")

        self.reader = IndexReader(
            self.out_source, index_record_setter=self.index_record_setter, mkdir_mode=self.mkdir_mode
        )
        finished_urls = [index_rec["url"] for index_rec in self.reader.index_data]
        urls_to_fetch = [url for url in urls if url not in finished_urls]

        return urls_to_fetch

    def get(
        self,
        urls: List[str],
        out_file_name: str | None = None,
        request_processor: RequestProcessor = lambda x: {},
        response_processor: ResponseProcessor = fallthrough_processor,
        index_record_setter: IndexSetterFunc = lambda x: {},
        request_delay: int | float = 0.4,
        **kwargs: Dict[str, Any] | None,
    ) -> IndexReader:
        """Starts fetching the provided URLs.

        This method initiates the web crawling process, fetching URLs according to the
        crawler's configuration. URLs that have already been successfully handled in a
        previous run are automatically excluded from re-fetching, enabling seamless
        resumption and incremental data collection.

        Args:
            urls (list[str]): A list of URLs to fetch. Already processed URLs from
                previous runs will be automatically skipped.

            out_file_name (str, optional): The base name for the output file(s) created
                at `out_file_path` (configured during `Crawler` initialization).
                If not provided, a hash based on the URL list will be automatically assigned.

            request_processor (scraping.RequestProcessor, optional): A callback function
                that fires just before each HTTP request is sent. It receives the
                `url` (str) being requested and should return `None`. This callback
                is typically used for logging, performance measurements, or other
                pre-request side effects, and defaults to an empty callback if not provided.
                It's not needed for most standard scraping scenarios.

            response_processor (scraping.ResponseProcessor, optional): A callback function
                that fires after each HTTP response is received. It takes two keyword
                arguments: `response: scraping.BasicResponse` and `session: aiohttp.ClientSession`
                (as specified by `ResponseHandlerKwargs`). The `session` object can be
                particularly useful for sending additional requests to the same domain
                based on the content of the current response. Return `None` to skip writing response.
                This callback is primarily used to format the output string according
                to your specific task requirements. If not provided, it defaults to a callback
                that forwards the original response object. You can use `scraping.html_body_processor`
                to save only the HTML `<body>` contents when processing web pages, or provide
                your own custom logic.

            index_record_setter (IndexSetterFunc, optional): A callback function that
                fires when metadata is being written for a fetched response. It receives
                the `response_obj` (which is the output from `response_processor`) and
                should return a dictionary of data to be included in the metadata record.
                By default, only the response's URL is included in the metadata. These
                fields are crucial for fast lookups in huge files, so feel free to
                include additional relevant fields such as `title`, `keywords`, or
                `release_date`. Keep in mind that metadata should remain relatively
                lightweight to ensure efficient indexing.

            request_delay (int | float, optional): The minimum time in seconds to wait
                between consecutive requests. Defaults to 0.4 seconds. This delay helps
                to configure the request rate, ensuring that at least this many seconds
                have passed since the latest request, which is vital for respecting
                service rate limits.

            **kwargs: A dictionary of parameters that will be passed directly to the
                underlying `aiohttp.ClientSession` instance. Use this to specify various
                session-level settings like `cookies`, `headers`, `proxy`, `timeout`, etc.

        Returns:
            IndexReader: A reader instance that's set up to efficiently read the
            saved data. This object is returned once all specified URLs have been fetched.

        Examples:

            1. To fetch URLs with minimal arguments (using default settings):

            >>> from arc_crawler import Crawler
            >>> crawler = Crawler()
            >>> crawler.get(["https://example.com"])

            2. To fetch URLs while extending the output data with custom processing:

            >>> from typing import Unpack, Dict, Any
            >>> from bs4 import BeautifulSoup
            >>> from arc_crawler import Crawler, ResponseHandlerKwargs
            >>> crawler = Crawler()
            >>> def extend_response(**kw: Unpack[ResponseHandlerKwargs]) -> Dict[str, Any]:
            ...     response_dict = dict(kw.get("response"))
            ...     # Assuming 'text' contains HTML, parse it with BeautifulSoup
            ...     soup = BeautifulSoup(response_dict.get("text", ""), "html.parser")
            ...     # Add a new field 'title' extracted from the HTML
            ...     response_dict["title"] = soup.find("h1").text.strip() if soup.find("h1") else "No Title"
            ...     return response_dict
            >>> def extend_index(response_obj: Dict[str, Any]) -> Dict[str, Any]:
            ...     # Include the 'title' from the processed response in the metadata index
            ...     return {"title": response_obj.get("title", "")}
            >>> crawler.get(
            ...     urls=["https://example.com"], response_processor=extend_response, index_record_setter=extend_index
            ... )
        """
        is_url_list = isinstance(urls, list) and all(isinstance(x, str) for x in urls)
        if not is_url_list:
            logger.error("Urls argument is of unsupported type")
            raise TypeError("URL entries must be a list")

        self.index_record_setter = lambda record: {**index_record_setter(record), **index_url_setter(record)}
        urls_to_fetch = self._init_output(urls, out_file_name)

        timer = Timer(total_measures=len(urls), measures_completed=len(urls) - len(urls_to_fetch))

        def handle_request_sent(url: str) -> None:
            logger.info(f'Processing "{url}" now...')
            print("\n")
            timer.measure(url)
            request_processor(url)

        async def handle_response_received(**kw: Unpack[ResponseHandlerKwargs]):
            response, session = kw["response"], kw["session"]
            response["url"] = unquote(str(response["url"]))

            if inspect.iscoroutinefunction(response_processor):
                response_obj = await response_processor(response=response, session=session)
            else:
                response_obj = response_processor(response=response, session=session)

            if response_obj is not None:
                self.reader.write(response_obj)

            timer.measure(response["url"])
            timer.print_status(with_progressbar=True, with_time_remaining=True)

        asyncio.run(
            self._fetcher.get(
                urls=urls_to_fetch,
                on_response=handle_response_received,
                on_request=handle_request_sent,
                min_request_delay=request_delay,
                **kwargs,
            )
        )

        reader = self.reader
        self.reader = None

        return reader

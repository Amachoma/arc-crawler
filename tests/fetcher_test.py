import pytest
import asyncio
from time import time
from typing import List, cast, Unpack

from arc_crawler import ResponseHandlerKwargs, TerminationFuncKwargs, SequentialFetcher, ParallelFetcher
from helpers import NetworkRequest, MockNetwork


class Helpers:
    def __init__(self):
        self.delayed_requests = cast(
            List[NetworkRequest],
            [
                {
                    "url": f"https://example.com/{i}",
                    "response": {"status": 200, "text": f"https://example.com/{i}"},
                    "delay": 1 - (0.15 * i),
                }
                for i in range(5)
            ],
        )
        self.request_delay = 0.1

        self.mixed_requests: List[NetworkRequest] = [
            {"url": f"https://success.io", "response": {"status": 200, "text": "Success"}},
            {"url": f"https://no-content.io", "response": {"status": 204, "text": "No content"}},
            {"url": f"https://not-found.io", "response": {"status": 404, "text": "Not found"}},
            {"url": f"https://teapot.io", "response": {"status": 418, "text": "I'm a teapot"}},
            {
                "url": f"https://server-down.io",
                "response": {"status": 500, "text": "Server is likely down"},
            },
        ]
        self.termination_ranges = [range(300, 400), range(405, 430)]

        self.request_urls = []
        self.response_urls = []
        self.request_timestamps = []

        def append_request(url):
            self.request_urls.append(url)
            self.request_timestamps.append(time())

        def append_response(**kwargs: Unpack[ResponseHandlerKwargs]):
            self.response_urls.append(kwargs.get("response")["text"])

        def termination_callback(**kwargs: Unpack[TerminationFuncKwargs]):
            if kwargs["status_code"] == 500:
                return Exception("Custom exception")

        self.on_request = append_request
        self.on_response = append_response
        self.on_check_status_code = termination_callback


class TestSequentialFetcher:
    def setup_method(self):
        self.utils = Helpers()

    def test_request_order(self, monkeypatch):
        requests = MockNetwork(self.utils.delayed_requests, monkeypatch)
        fetcher = SequentialFetcher()

        asyncio.run(
            fetcher.get(
                urls=requests.urls,
                on_request=self.utils.on_request,
                on_response=self.utils.on_response,
                min_request_delay=self.utils.request_delay,
            )
        )

        # Request and response order is the same as initial url list
        assert requests.urls == self.utils.request_urls == self.utils.response_urls

        # Delay between each response is more or equal than request_delay set
        for i in range(0, len(self.utils.request_timestamps) - 1, 2):
            assert self.utils.request_timestamps[i + 1] - self.utils.request_timestamps[i] >= self.utils.request_delay

    def test_request_delay(self, monkeypatch):
        requests = MockNetwork(self.utils.delayed_requests, monkeypatch)
        fetcher = SequentialFetcher()

        asyncio.run(
            fetcher.get(
                urls=requests.urls,
                on_request=self.utils.on_request,
                on_response=self.utils.on_response,
                min_request_delay=self.utils.request_delay,
            )
        )

        # Delay between each response is more or equal than request_delay set
        for i in range(0, len(self.utils.request_timestamps) - 1, 2):
            assert self.utils.request_timestamps[i + 1] - self.utils.request_timestamps[i] >= self.utils.request_delay

    def test_termination_list(self, monkeypatch):
        requests = MockNetwork(self.utils.mixed_requests, monkeypatch)
        fetcher = SequentialFetcher(termination_criteria=self.utils.termination_ranges)

        with pytest.raises(Exception):
            asyncio.run(
                fetcher.get(
                    urls=requests.urls,
                    on_request=self.utils.on_request,
                    on_response=self.utils.on_response,
                )
            )

        count_succeeded = next(
            i
            for i, v in enumerate(self.utils.mixed_requests)
            if (any([v["response"]["status"] in rang for rang in self.utils.termination_ranges]))
        )
        assert len(self.utils.response_urls) == count_succeeded

    def test_termination_callback(self, monkeypatch):
        requests = MockNetwork(self.utils.mixed_requests, monkeypatch)

        fetcher = SequentialFetcher(termination_criteria=self.utils.on_check_status_code)

        with pytest.raises(Exception):
            asyncio.run(
                fetcher.get(
                    urls=requests.urls,
                    on_request=self.utils.on_request,
                    on_response=self.utils.on_response,
                )
            )

        count_succeeded = next(
            i
            for i, v in enumerate(self.utils.mixed_requests)
            if isinstance(self.utils.on_check_status_code(status_code=v["response"]["status"], url=""), Exception)
        )
        assert len(self.utils.response_urls) == count_succeeded


class TestParallelFetcher:
    def setup_method(self):
        self.utils = Helpers()

    def test_request_order(self, monkeypatch):
        requests = MockNetwork(self.utils.delayed_requests, monkeypatch)
        fetcher = ParallelFetcher()

        asyncio.run(
            fetcher.get(
                urls=requests.urls,
                on_request=self.utils.on_request,
                on_response=self.utils.on_response,
                min_request_delay=self.utils.request_delay,
            )
        )

        # Requests are sent in parallel; Request order should be in the same order as response
        assert requests.urls == self.utils.request_urls

    def test_response_order(self, monkeypatch):
        requests = MockNetwork(self.utils.delayed_requests, monkeypatch)
        fetcher = ParallelFetcher()

        asyncio.run(
            fetcher.get(
                urls=requests.urls,
                on_request=self.utils.on_request,
                on_response=self.utils.on_response,
                min_request_delay=self.utils.request_delay,
            )
        )

        # Earlier request are the slowest; when fetching in parallel responses should come in reversed order
        assert self.utils.response_urls == list(reversed(requests.urls))

    def test_request_delay(self, monkeypatch):
        requests = MockNetwork(self.utils.delayed_requests, monkeypatch)

        fetcher = ParallelFetcher()
        request_time_delta_threshold = self.utils.request_delay + 0.1

        asyncio.run(
            fetcher.get(
                urls=requests.urls,
                on_request=self.utils.on_request,
                on_response=self.utils.on_response,
                min_request_delay=self.utils.request_delay,
            )
        )

        # Delay between each response is more or equal than request_delay set
        for i in range(0, len(self.utils.request_timestamps) - 1, 2):
            assert (
                request_time_delta_threshold + self.utils.request_delay
                >= self.utils.request_timestamps[i + 1] - self.utils.request_timestamps[i]
                >= self.utils.request_delay
            )

    def test_termination_list(self, monkeypatch):
        requests = MockNetwork(self.utils.mixed_requests, monkeypatch)
        fetcher = ParallelFetcher(termination_criteria=self.utils.termination_ranges)

        with pytest.raises(Exception):
            asyncio.run(
                fetcher.get(
                    urls=requests.urls,
                    on_request=self.utils.on_request,
                    on_response=self.utils.on_response,
                )
            )

        # Attempted to get all the urls provided. Requested in parallel in the same order as in param provided
        assert self.utils.request_urls == requests.urls

    def test_termination_callback(self, monkeypatch):
        requests = MockNetwork(self.utils.mixed_requests, monkeypatch)
        fetcher = ParallelFetcher(termination_criteria=self.utils.on_check_status_code)

        with pytest.raises(Exception):
            asyncio.run(
                fetcher.get(
                    urls=requests.urls,
                    on_request=self.utils.on_request,
                    on_response=self.utils.on_response,
                )
            )

        # Attempted to get all the urls provided. Requested in parallel in the same order as in param provided
        assert self.utils.request_urls == requests.urls

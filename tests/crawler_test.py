from pathlib import Path
from typing import List, Unpack
from time import time
import random

from arc_crawler import Crawler, ResponseHandlerKwargs, SequentialFetcher
from arc_crawler.reader import IndexReader
from tests.helpers import MockNetwork, NetworkRequest


class TestingUtils:
    def __init__(self, monkeypatch, tmp_path):
        self.monkeypatch = monkeypatch

        self.empty_file_name = "empty"
        self.empty_file_path = Path(tmp_path) / f"{self.empty_file_name}.jsonl"

        self.requests_config: List[NetworkRequest] = [
            {
                "url": f"https://example.com/items/{i}",
                "response": {"text": str(i), "status": 200, "json": None},
                "delay": 0.05 * i,
            }
            for i in range(10)
        ]
        self.request_delay = 0.025

        self.mixed_requests = [
            {"url": f"https://example.com/success", "response": {"text": "Success", "status": 200}},
            {"url": f"https://example.com/success-empty", "response": {"text": "", "status": 204}},
            {"url": f"https://example.com/not-found", "response": {"text": "", "status": 404}},
            {"url": f"https://example.com/another-not-found", "response": {"text": "", "status": 404}},
            {"url": f"https://example.com/forbidden", "response": {"text": "", "status": 400}},
            {"url": f"https://example.com/teapot", "response": {"text": None, "status": 418}},
        ]

        self.filled_file_name = "filled"
        self.filled_file_path = Path(tmp_path) / f"{self.filled_file_name}.jsonl"

        self.custom_field = "foo-bar"
        self.custom_field_value = "lorem-ipsum"

    def mock_input(self, res: str):
        self.monkeypatch.setattr("builtins.input", lambda _: res)


class TestCrawler:
    # Instance can be created with 'async' mode. When fetching empty array output is being created successfully.
    def test_can_start_in_async_mode(self, tmp_path, monkeypatch):
        utils = TestingUtils(monkeypatch, tmp_path)
        utils.mock_input("y")

        crawler = Crawler(mode="async", out_file_path=tmp_path, log_level="debug")
        crawler.get([], out_file_name=utils.empty_file_name)
        assert utils.empty_file_path.exists()

    # In async mode total wait time would be near max(requests_wait_time) + request_delay * request_count.
    def test_async_mode_requests_in_parallel(self, tmp_path, monkeypatch):
        utils = TestingUtils(monkeypatch, tmp_path)
        requests = MockNetwork(utils.requests_config, monkeypatch)
        utils.mock_input("y")

        elapsed_bottom_line = max(utils.requests_config, key=lambda x: x["delay"])["delay"]
        elapsed_top_line = (elapsed_bottom_line + (len(utils.requests_config) - 1) * utils.request_delay) * 1.1

        crawler = Crawler(mode="async", out_file_path=tmp_path, log_level="debug")

        request_start_time = time()
        crawler.get(requests.urls, out_file_name=utils.filled_file_name, request_delay=utils.request_delay)
        time_elapsed = time() - request_start_time

        assert utils.filled_file_path.exists()
        assert elapsed_bottom_line <= time_elapsed <= elapsed_top_line

    # Instance can be created with 'sync' mode. When fetching empty array output is being created successfully.
    def test_can_start_in_sync_mode(self, tmp_path, monkeypatch):
        utils = TestingUtils(monkeypatch, tmp_path)
        utils.mock_input("y")

        crawler = Crawler(mode="sync", out_file_path=tmp_path, log_level="debug")
        crawler.get([], out_file_name=utils.empty_file_name)

        assert utils.empty_file_path.exists()

    # In sync mode total wait time would be near sum(requests_wait_time) + request_delay * request_count.
    def test_sync_mode_requests_in_order(self, tmp_path, monkeypatch):
        utils = TestingUtils(monkeypatch, tmp_path)
        requests = MockNetwork(utils.requests_config, monkeypatch)
        utils.mock_input("y")

        elapsed_bottom_line = sum([item["delay"] for item in utils.requests_config]) + utils.request_delay * (
                len(requests.urls) - 1
        )
        elapsed_top_line = elapsed_bottom_line * 1.15

        crawler = Crawler(mode="sync", out_file_path=tmp_path, log_level="debug")

        request_start_time = time()
        crawler.get(requests.urls, out_file_name=utils.filled_file_name, request_delay=utils.request_delay)
        time_elapsed = time() - request_start_time

        assert utils.filled_file_path.exists()
        assert elapsed_bottom_line <= time_elapsed <= elapsed_top_line

    # Can create filename when 'out_file_name' param is empty.
    # Filename would be the same for the same url inputs (able to continue on sudden interrupts smoothly)
    def test_generates_persistent_hash_based_namings(self, tmp_path, monkeypatch):
        utils = TestingUtils(monkeypatch, tmp_path)
        requests = MockNetwork(utils.requests_config, monkeypatch)
        utils.mock_input("y")

        # Getting empty array
        crawler = Crawler(out_file_path=tmp_path, log_level="debug")
        reader = crawler.get([])
        file_name = reader.path.name

        # Delete output
        reader.path.unlink()

        # Getting empty array again
        reader = crawler.get([])

        # Supposed to have same naming for same input
        assert reader.path.name == file_name
        file_name = reader.path.name

        # Requesting different urls
        reader = crawler.get(requests.urls[0:1])
        # Supposed to have different naming
        assert file_name != reader.path

    # crawler produces output that can be read via IndexRecord instance -> Do the same, but open data manually using IndexReader
    def test_out_file_can_be_read(self, tmp_path, monkeypatch):
        utils = TestingUtils(monkeypatch, tmp_path)
        requests = MockNetwork(utils.requests_config, monkeypatch)
        utils.mock_input("y")
        url_list = requests.urls[0: len(requests.urls) // 2]

        crawler = Crawler(out_file_path=tmp_path, log_level="debug")
        crawler.get(url_list, out_file_name=utils.filled_file_name)

        reader = IndexReader(utils.filled_file_path)
        assert len(reader) == len(url_list)

    # crawler can continue fetching from right place based on file contents
    def test_resume_fetching(self, tmp_path, monkeypatch):
        utils = TestingUtils(monkeypatch, tmp_path)
        requests = MockNetwork(utils.requests_config, monkeypatch)
        utils.mock_input("y")

        random_urls = requests.urls[:]
        random.shuffle(random_urls)
        random_urls = random_urls[0: random.randint(1, len(random_urls))]

        crawler = Crawler(out_file_path=tmp_path, log_level="debug")
        crawler.get(random_urls, out_file_name=utils.filled_file_name)

        requested_urls = []

        def append_urls(url: str):
            requested_urls.append(url)

        reader = crawler.get(requests.urls, out_file_name=utils.filled_file_name, request_processor=append_urls)
        extra_urls = [rec for rec in requests.urls if rec not in random_urls]

        assert sorted(requested_urls) == sorted(extra_urls)
        assert len(reader) == len(requests.urls)

    # crawler can produce customized extended output
    def test_can_extend_jsonl(self, tmp_path, monkeypatch):
        utils = TestingUtils(monkeypatch, tmp_path)
        utils.mock_input("y")
        requests = MockNetwork(utils.requests_config, monkeypatch)
        url_list = requests.urls[0: len(requests.urls) // 2]

        crawler = Crawler(out_file_path=tmp_path, log_level="debug")

        def handle_response(**kwargs: Unpack[ResponseHandlerKwargs]):
            res = dict(kwargs["response"])
            res[utils.custom_field] = utils.custom_field_value
            return res

        reader = crawler.get(url_list, out_file_name=utils.filled_file_name, response_processor=handle_response)
        for record in reader:
            assert record.get(utils.custom_field, None) == utils.custom_field_value

    # crawler can produce customized index
    def test_can_extend_index_record(self, tmp_path, monkeypatch):
        utils = TestingUtils(monkeypatch, tmp_path)
        utils.mock_input("y")
        requests = MockNetwork(utils.requests_config, monkeypatch)
        url_list = requests.urls[0: len(requests.urls) // 2]

        crawler = Crawler(out_file_path=tmp_path, log_level="debug")

        def process_index_record(_):
            return {utils.custom_field: utils.custom_field_value}

        reader = crawler.get(url_list, out_file_name=utils.filled_file_name, index_record_setter=process_index_record)
        for record in reader.index_data:
            assert record.get(utils.custom_field, None) == utils.custom_field_value

    # crawler can skip writing json on demand
    def test_skip_write(self, tmp_path, monkeypatch):
        utils = TestingUtils(monkeypatch, tmp_path)
        utils.mock_input("y")
        requests = MockNetwork(utils.mixed_requests, monkeypatch)
        successful_responses = list(filter(lambda rec: rec.get("response").get("status") == 200, utils.mixed_requests))

        crawler = Crawler(out_file_path=tmp_path, log_level="debug")

        def process_response(**kw: Unpack[ResponseHandlerKwargs]):
            response = kw.get("response")
            return response if response.get("status") == 200 else None

        reader = crawler.get(requests.urls, out_file_name=utils.filled_file_name, response_processor=process_response)

        assert len(reader) == len(successful_responses)

    # test if session provided by Crawler is usable
    def test_if_response_session_is_usable(self, tmp_path, monkeypatch):
        utils = TestingUtils(monkeypatch, tmp_path)
        utils.mock_input("y")
        requests = MockNetwork(utils.requests_config, monkeypatch)
        follow_up_responses = []

        async def follow_up_request(**kwargs: Unpack[ResponseHandlerKwargs]):
            response, session = kwargs["response"], kwargs["session"]
            url_str = str(response["url"])

            fetcher = SequentialFetcher()

            async def append_response(**_: Unpack[ResponseHandlerKwargs]):
                nonlocal follow_up_responses
                follow_up_responses.append(url_str)

            await fetcher.get([url_str], on_response=append_response, session=session)
            return response

        crawler = Crawler(out_file_path=tmp_path, mode="sync", log_level="debug")
        crawler.get(
            requests.urls, out_file_name=utils.filled_file_name, response_processor=follow_up_request, request_delay=0
        )

        assert sorted(follow_up_responses) == sorted(requests.urls)

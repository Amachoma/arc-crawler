import asyncio
import aiohttp
from typing import TypedDict, Any, List
from yarl import URL


class ResponseMock:
    def __init__(self, text: str | None, status: int, url: str, ok: bool = True, json: Any = None):
        async def get_text():
            return text

        async def get_json(encoding, loads, content_type):
            return json

        self.text = get_text
        self.json = get_json
        self.status = status
        self.url = URL(url)
        self.ok = ok
        self.close = lambda: {}
        self.headers = {"Content-Type": "application/json" if json is not None else "text/plain"}


class NetworkResponse(TypedDict, total=False):
    status: int
    text: str | None
    json: Any | None


class NetworkRequest(TypedDict, total=False):
    url: str
    response: NetworkResponse
    delay: float | int | None


class MockNetwork:
    def __init__(self, requests: List[NetworkRequest], monkeypatch):
        self.__responses = {
            rec["url"]: {
                "response": rec["response"],
                **({"delay": rec.get("delay", None)} if "delay" in rec else {}),
            }
            for rec in requests
        }
        self.urls = [x["url"] for x in requests]

        async def response_sender(_, url: str):
            res_obj = self.__responses.get(url)
            if res_obj:
                delay = res_obj.get("delay", 0)
                if delay > 0:
                    await asyncio.sleep(delay)

                response = res_obj["response"]
                return ResponseMock(
                    text=response.get("text", None),
                    status=response.get("status", 404),
                    url=url,
                    json=response.get("json", None),
                    ok=response.get("status", 404) in range(200, 300),
                )
            else:
                raise Exception(f'Requested url "{url}" is not present in requests parameter list')

        monkeypatch.setattr(aiohttp.ClientSession, "get", response_sender)

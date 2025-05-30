from typing import Unpack
import random

from arc_crawler import Crawler, ResponseHandlerKwargs


# Scrapes JSON Placeholder entries, skipping non-existent ones
def fetch_skipping_not_found():
    # Configure the crawler to stop on "429 Too many requests" or "5XX" status codes
    crawler = Crawler(out_file_path="./output", termination_criteria=[429, range(500, 600)])

    urls_to_fetch = [f"https://jsonplaceholder.typicode.com/posts/{index}" for index in range(80, 110)]
    random.shuffle(urls_to_fetch)

    # Custom response processor that warns and skips writing for 404 responses
    def skip_not_found(**kwargs: Unpack[ResponseHandlerKwargs]):
        response = kwargs.get("response")
        is_not_found = response.get("status") == 404

        if is_not_found:
            # Using print as an example. Consider using logging in your projects instead
            print(f'Warning: skipping "{response.get("url")}"...')

        # Skip writing the response if its status code is 404
        return None if is_not_found else response

    reader = crawler.get(
        urls_to_fetch, out_file_name="found-only", response_processor=skip_not_found, request_delay=0.1
    )
    print(
        f"I've processed {len(urls_to_fetch)} urls. "
        f"{len(urls_to_fetch) - len(reader)} of them were skipped due to 404 status code."
    )


# Scrapes JSON Placeholder posts, extending each with user info.
def follow_up_fetching():
    # Using sync mode to respect service rate limits
    sync_crawler = Crawler(out_file_path="./output", mode="sync")
    urls_to_fetch = [f"https://jsonplaceholder.typicode.com/posts/{index}" for index in range(1, 31)]
    random.shuffle(urls_to_fetch)

    # Using a list as a cache for user data, accessible by user ID
    user_cache = [None] * len(urls_to_fetch)

    async def append_user_data(**kwargs: Unpack[ResponseHandlerKwargs]):
        response, session = kwargs.get("response"), kwargs.get("session")
        record = response.get("json")

        # Getting user ID from the response and trying to find user data in the cache
        user_id = record.get("userId")
        cached_user = user_cache[user_id]

        if not cached_user:
            # If not found in cache fetching user data using session provided
            user_response = await session.get(f"https://jsonplaceholder.typicode.com/users/{user_id}")
            user_json = await user_response.json(encoding="utf-8")
            user_cache[user_id] = user_json
            cached_user = user_json

        # Appending user info into response's "json" field
        response["json"]["user"] = cached_user
        # Writing only the JSON entry to the file
        return response["json"]

    # Extend common fields in metadata for easier search
    def extend_index_record(obj):
        return {"user": {"id": obj["user"]["id"], "username": obj["user"]["username"], "email": obj["user"]["email"]}}

    reader = sync_crawler.get(
        urls_to_fetch,
        out_file_name="user-posts",
        request_delay=0.05,
        response_processor=append_user_data,
        index_record_setter=extend_index_record,
    )

    # Find posts where the username is "Bret"
    posts = reader.get(lambda record: record.get("user").get("username") == "Bret")
    print(
        f"I've gathered {len(urls_to_fetch)} post entries.\n"
        + f'There are {len(posts)} posts made by an account with username "Bret".'
    )


if __name__ == "__main__":
    # fetch_skipping_not_found()
    follow_up_fetching()

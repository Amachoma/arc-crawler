from typing import Unpack, Dict, Any

from arc_crawler import JsonSerializable
from arc_crawler import Crawler, html_body_processor, ResponseHandlerKwargs


# Scraps a bunch of HTML Wikipedia pages
# Uses html_body_processor to output only <body> tag contents (easy to use and saves disk space)
def scrap_wikipedia():
    crawler = Crawler(out_file_path="./output")

    reader = crawler.get(
        [
            "https://en.wikipedia.org/wiki/JavaScript",
            "https://en.wikipedia.org/wiki/Go_(programming_language)",
            "https://en.wikipedia.org/wiki/Python_(programming_language)",
            "https://en.wikipedia.org/wiki/Node.js",
        ],
        out_file_name="wiki-programming",
        response_processor=html_body_processor,
    )

    print(f"I've gathered {len(reader)} wikipedia entries.")


# Scraps a bunch of JSON Placeholder entries and extends metadata for convenient search.
# Uses reader instance returned by crawler to search suitable entries after scraping is complete.
def scrap_json_placeholder():
    crawler = Crawler(out_file_path="./output", log_level="debug")

    # Strip only json contents on request acquisition
    def process_json(**kwargs: Unpack[ResponseHandlerKwargs]) -> JsonSerializable:
        json_contents = kwargs.get("response").get("json")
        return json_contents

    # Include record ID and user ID in metadata for ease of search
    def extend_index_record(json_contents: Dict[str, Any]) -> JsonSerializable:
        return {"id": json_contents.get("id"), "user_id": json_contents.get("userId")}

    reader = crawler.get(
        [f"https://jsonplaceholder.typicode.com/posts/{index}" for index in range(1, 51)],
        request_delay=0.1,
        out_file_name="json-placeholder",
        response_processor=process_json,
        index_record_setter=extend_index_record,
    )

    first_user_posts = reader.get(lambda record: record.get("user_id") == 1)
    print(
        f"I've gathered {len(reader)} json entries total. {len(first_user_posts)} of them are made by user with id = 1"
    )


if __name__ == "__main__":
    # scrap_wikipedia()
    scrap_json_placeholder()

# arc-crawler

🌐 [English](https://github.com/Amachoma/arc-crawler/blob/master/README.md) | [日本語](https://github.com/Amachoma/arc-crawler/blob/master/README.jp.md)

<p align="center">
  <img width="256" src="https://raw.githubusercontent.com/Amachoma/arc-crawler/master/docs/arc-crawler-logo.svg" />
</p>

`arc-crawler` is a flexible Python module designed to simplify complex web scraping tasks.
It focuses on efficient, resumable data acquisition, structured output management,
and customizable data processing.

## ✨ Features

* **Flexible Fetching Strategies**: Supports both high-speed parallel and
  precise sequential URL fetching with customizable delays.
* **Resumable Progress Tracking**: Automatically tracks progress,
  allowing seamless resumption from interruptions and incremental data appending.
* **Efficient Output Management**: Writes metadata alongside fetched data,
  making very large output files easily accessible and queryable via built-in `IndexReader`.
* **Customizable Data Processing**: Offers flexible callback functions for pre-request actions,
  post-response processing, and custom metadata indexing.

## 🚀 Quick Start

### Installation

You can easily install arc-crawler using pip:

```bash
pip install arc-crawler
```

### Basic Usage

This example shows you how to quickly crawl a few Wikipedia pages
and save only their `<body>` contents using the built-in `html_body_processor`.

```python
from arc_crawler import Crawler, html_body_processor


def crawl_wikipedia():
    urls_to_fetch = [
        "https://en.wikipedia.org/wiki/JavaScript",
        "https://en.wikipedia.org/wiki/Go_(programming_language)",
        "https://en.wikipedia.org/wiki/Python_(programming_language)",
        "https://en.wikipedia.org/wiki/Node.js",
    ]

    # Initialize the crawler, outputting to a new './output' directory
    crawler = Crawler(out_file_path="./output")

    # Fetch URLs, process responses to save only the <body> tag, and save to 'wiki-programming' files
    reader = crawler.get(
        urls_to_fetch,
        out_file_name="wiki-programming",
        response_processor=html_body_processor,  # Use the built-in processor
    )

    print(f"Successfully gathered {len(reader)} Wikipedia entries.")
    print(f"Dataset file is located at: {reader.path}")


if __name__ == "__main__":
    crawl_wikipedia()
```

### 📚 More Examples & Advanced Usage

For more detailed examples demonstrating advanced features like custom response/request processors,
metadata indexing, and handling json content, please refer to the [basic.py](https://github.com/Amachoma/arc-crawler/blob/master/examples/basic.py)
and [advanced.py](https://github.com/Amachoma/arc-crawler/blob/master/examples/advanced.py) file within the repository.

Additionally, for comprehensive API documentation, including all available parameters, return types,
and internal workings, explore the detailed docstrings within the arc-crawler module's source code
(e.g., use `help(Crawler)` or `help(Crawler.get)` in your Python interpreter or access docs via IDE Tools).

## 💡 Best Practice: Separate Scraping from Parsing

For optimal efficiency and maintainability in web scraping, it is strongly recommended
**to prioritize saving raw, unaltered response data first** within your `response_processor` callbacks.
Avoid implementing complex parsing logic directly during the fetching phase.

This approach offers significant advantages:

* **Iterative Improvement**: You can refine and improve your parsing logic on local data without needing
  to re-fetch everything each time.
* **Resilience & Speed**: The fetching stage focuses purely on data acquisition, improving resilience
  to network issues and maximizing download speed.
* **Resource Management**: Offload CPU and memory-intensive parsing to a separate process or script,
  preventing it from slowing down I/O-bound fetching operations.

In essence, with arc-crawler, focus on saving the raw source data. Parsing is a distinct,
subsequent step best performed after fetching.

## Changelog

### 0.1.1
Minor performance optimizations and structural changes

* Performance improvements for cases when comparing large list of target URLs against those already fetched.
* Moved `IndexReader` related imports to `arc_crawler.reader` for clarity.

### 0.1.0
Initial release

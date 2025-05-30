from typing import Any

import json
from pathlib import Path


def open_lines(path: str | Path):
    result = []
    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            data = json.loads(line.strip())
            if data:
                result.append(data)
    return result


def write_line(path: str | Path, line: Any):
    with open(path, "a", encoding="utf-8") as file:
        json.dump(line, file, ensure_ascii=False)
        file.write("\n")


def overwrite_file(path: str | Path, content: Any):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(content, file, ensure_ascii=False)


def open_json(path: str | Path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)

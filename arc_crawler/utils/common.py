import math


def input_prompt(prompt: str) -> bool:
    results = {"y": True, "n": False}
    while True:
        res = results.get(input(f"{prompt} (y/n)\n").lower(), None)
        if res is not None:
            return res
        else:
            print("Invalid input. Please enter 'y' or 'n'.")


def convert_size(size_bytes: int) -> str:
    if size_bytes == 0:
        return "0B"

    size_name = ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])

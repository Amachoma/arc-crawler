from typing import Any, Dict, List

import json
from pathlib import Path

import logging

logger = logging.getLogger(__name__)

from arc_crawler.utils import write_line, open_lines, input_prompt, convert_size

from .types import FilterFunc, IndexSetterFunc, IndexLoaderFunc, JsonSerializable, MkdirMode


class IndexReader:
    """Provides fast read/write access to JSONL-like dataset files.

    This class accelerates data access by pre-indexing the file's contents,
    allowing quick retrieval of individual records via their byte offsets.

    Attributes:
        path (Path): The file system path to the dataset file.
        index_data (list[dict]): A list of metadata dictionaries, where each
            dictionary typically includes the 'start_byte' for a record.
    """

    @staticmethod
    def __get_out_path(target_path: str | Path):
        path_obj = Path(target_path)
        parent_dir, filename, suffix, stem = (
            path_obj.parent,
            path_obj.name,
            path_obj.suffix,
            path_obj.stem,
        )
        return {
            "source": parent_dir / (filename if suffix else f"{filename}.jsonl"),
            "index": parent_dir / f"{stem}.index",
            "parent": parent_dir,
        }

    @staticmethod
    def touch(file_path: str | Path):
        """Creates empty source and index files.

        This static method generates minimal, ready-to-use output files without
        requiring an `IndexReader` instance.

        Args:
                file_path (str | Path): The target directory and filename. The file
                        extension is optional; if omitted, it defaults to `.jsonl`.

        Returns:
                dict: A dictionary containing the output file paths:
                        * **parent** (Path): Full path to the output directory.
                        * **source** (Path): Full path to the main data file (.jsonl).
                        * **index** (Path): Full path to the metadata index file.

        Examples:
                >>> from arc_crawler import IndexReader
                >>> IndexReader.touch("./output/filename")
                {'parent': Path('output'), 'source': Path('output/filename.jsonl'), 'index': Path('output/filename.index')}
        """
        paths = IndexReader.__get_out_path(file_path)

        paths["parent"].mkdir(parents=True, exist_ok=True)
        paths["source"].touch()
        paths["index"].touch()

        return paths

    def __init__(
        self,
        file_path: str | Path,
        index_record_setter: IndexSetterFunc = lambda record: {},
        source_record_loader: IndexLoaderFunc = lambda line: json.loads(line.strip()),
        mkdir_mode: MkdirMode | None = "interactive",
    ):
        """Initializes an `IndexReader` instance.

        Args:
                file_path (str | Path): Path to the source data file. The file extension
                        can be omitted for `.jsonl` files.

                index_record_setter (IndexSetterFunc, optional): A function to populate
                        the `.index` file based on source contents. By default, only the
                        `start_byte` is stored.

                source_record_loader (IndexLoaderFunc, optional): A function that loads
                        strings from the main data file. Defaults to `json.loads`.

                mkdir_mode ("interactive" | "forced" | "disabled", optional): The strategy
                        to apply if `file_path` points to a non-existent directory or file.
                        Choose from:

                        * **"interactive"**: Prompts the user to confirm creating the output
                          directory and files.
                        * **"forced"**: Creates the output directory and files automatically
                          if needed.
                        * **"disabled"**: Raises an error if `file_path` is not found.

        Raises:
                FileNotFoundError: If the user declines to create new files when `mkdir_mode`
                                                   is "interactive" and the `file_path` is non-existent,
                                                   or if `mkdir_mode` is "disabled" and the path is missing.

        Examples:
                1) To initialize with minimal arguments:

                >>> from arc_crawler import IndexReader
                >>> reader = IndexReader("./output/filename")

                2) To extend metadata with custom fields for easier search:

                >>> def get_record_name(record):
                >>>     return {"name": record.get("name")}
                >>> reader = IndexReader("./output/filename", index_record_setter=get_record_name)
        """
        paths = self.__get_out_path(file_path)
        self._file_path = paths["source"]
        self._index_file_path = paths["index"]

        if not self._file_path.exists():

            def log_error():
                logger.error("File path not found")
                raise FileNotFoundError(f"Check if '{file_path}' exists and try again")

            def create_empty():
                self.touch(str(self._file_path))

            match mkdir_mode:
                case "interactive":
                    should_create = input_prompt("File path not found. Create new?")
                    if should_create:
                        create_empty()
                    else:
                        log_error()
                case "forced":
                    create_empty()
                case _:
                    log_error()

        if not self._index_file_path.exists():
            logger.info(f"No index file found. Creating from scratch")
            self._index_file_path.touch()

        self._index_record_setter = index_record_setter
        self._source_record_getter = source_record_loader

        extension = self._file_path.suffix
        if extension != ".jsonl":
            logger.warning(
                f"Provided file extension is different from .jsonl. Index reader may provide unexpected results."
            )

        self._index_data = open_lines(self._index_file_path)
        self._next_start_byte = 0 if len(self._index_data) == 0 else self._index_data[-1].get("start_byte") + 1
        self._check_integrity()

    # Integrity check to confirm if .index record is matching .jsonl record
    # In order to speed up init of big files it only confirms if last index record is matching last source file byte
    def _check_integrity(self):
        logger.debug("Running .index file integrity check...")
        with open(self._file_path, "rb") as source_file:
            # Search and read last known line
            source_file.seek(self._next_start_byte)
            if len(self._index_data) != 0:
                source_file.readline()

            self._next_start_byte = source_file.tell()
            line = source_file.readline()

            if line:
                logger.debug(f"Found lines that are yet to be indexed. Appending .index file...")

            while line:
                self.__append_index(json.loads(line.decode(encoding="utf-8")))
                line = source_file.readline()
            else:
                logger.debug(".index file is already up-to-date with source file")
            logger.debug("Integrity check completed successfully!")

    def __append_index(self, obj: Dict[str, Any]):
        new_index_record = self._index_record_setter(obj) or {}
        if not isinstance(new_index_record, dict):
            logger.error(f"Incorrect index_record_setter provided.")
            raise ValueError("index_gen_callback should return a valid dict object to be stored in .index file")

        new_index_record["start_byte"] = self._next_start_byte

        self._index_data.append(new_index_record)
        write_line(self._index_file_path, new_index_record)

        payload_str = json.dumps(obj, ensure_ascii=False) + "\n"
        self._next_start_byte += len(payload_str.encode("utf-8")) + 1

    def __read_from_byte(self, byte_index):
        logger.debug(f"Reading binary:")
        with open(self._file_path, "rb") as temp_binary:
            temp_binary.seek(byte_index)
            t_line = temp_binary.readline()
            logger.debug(f"{t_line}")
            return self._source_record_getter(t_line.decode())

    def get(self, filtering: int | FilterFunc) -> Dict[str, Any] | List[Dict[str, Any]]:
        """Acquires original record(s) based on criteria matching the metadata.

        This is a universal method for retrieving dataset records.
        When an integer is provided, it returns the Nth record from the beginning.
        When a filtering function is provided, it returns single or multiple records
        that match the criteria.

        Args:
                filtering (int | FilterFunc): The criteria for record acquisition.
                        Can be an integer index or a callable filtering function.

        Returns:
                Dict[str, Any]: If a single matching entry was found.
                List[Dict[str, Any]]: If multiple matching entries were found.

        Raises:
                IndexError: If an integer index is provided and is out of range.
                ValueError: If no records match the provided filtering criteria.
                TypeError: If the 'filtering' argument type is not supported.

        Examples:
                1) To get the second record by index:

                >>> from arc_crawler import IndexReader
                >>> reader = IndexReader("./output/filename")
                >>> reader.get(1)
                {'title': 'Inception', 'year': 2010, 'rating': 8.8}

                2) To get one record based on a filter function:

                >>> from arc_crawler import IndexReader
                >>> reader = IndexReader("./output/filename")
                >>> reader.get(lambda rec: rec.get("title") == "Inception")
                {'title': 'Inception', 'year': 2010, 'rating': 8.8}

                3) To get multiple records matching a broad filter:

                >>> from arc_crawler import IndexReader
                >>> reader = IndexReader("./output/filename")
                >>> reader.get(lambda rec: rec.get("year") == 2010)
                [
                        {'title': 'Inception', 'year': 2010, 'rating': 8.8},
                        {'title': 'Toy Story 3', 'year': 2010, 'rating': 8.3},
                        {'title': 'Black Swan', 'year': 2010, 'rating': 8.0}
                ]
        """
        if isinstance(filtering, int):
            record = self._index_data[filtering]
            if record is None:
                logger.error(f"Index 'f{filtering}' is out of range")
                raise IndexError(f"Provide index in range [0, {len(self._index_data) - 1}]")
            start_byte = record["start_byte"]

            return self.__read_from_byte(start_byte)
        elif callable(filtering):
            result = list(filter(filtering, self._index_data))

            if len(result) == 1:
                return self.__read_from_byte(result[0]["start_byte"])
            elif len(result) > 1:
                results = []
                for match in result:
                    results.append(self.__read_from_byte(match["start_byte"]))
                return results
            else:
                logger.error(f"No records matching filtering function provided")
                raise ValueError(
                    "When using filtering function make sure to specify condition matching at least one record"
                )
        else:
            logger.error(f"Argument type is not supported")
            raise TypeError(
                "Either provide int to get record by index or filtering function to get all matching records"
            )

    def write(self, obj: JsonSerializable):
        """Writes a JSON serializable object to the data file.

        This method serializes an object to JSON format while generating its
        corresponding index file metadata.

        Args:
                obj (JSONSerializable): The object to be written to the source file.

        Returns:
                None

        Example:
                To write a dictionary to the file:

                >>> from arc_crawler import IndexReader
                >>> reader = IndexReader("./output/filename", mkdir_mode="forced")
                >>> reader.write({"foo": "bar", "bar": "baz"})
        """
        write_line(self._file_path, obj)
        self.__append_index(obj)

    @property
    def path(self) -> Path:
        """Path to the main data file used by reader.

        Returns:
                Path: Full path to the main data file (.jsonl).
        """
        return self._file_path

    @property
    def index_data(self):
        """List of metadata entries stored in memory.

        Returns:
            list: An array of metadata records loaded from the `.index` file.
                  Each record is guaranteed to have at least a 'start_byte' field.
        """
        return self._index_data

    def __len__(self):
        return len(self._index_data)

    def __iter__(self):
        for item in self._index_data:
            yield self.__read_from_byte(item.get("start_byte"))

    def __getitem__(self, item: int | slice):
        if isinstance(item, int):
            return self.get(item)
        elif isinstance(item, slice):
            return [self.get(i) for i in range(item.start, item.stop, item.step or 1)]
        else:
            logger.error("Incorrect item type provided")
            raise TypeError(
                "IndexReader items can only be accessed with integers or slices. "
                'Use "get()" method if you need to provide a more complex search condition'
            )

    def __str__(self):
        source_size = max(0, self._next_start_byte - 1)
        return (
            f"Source file consists of {len(self)} records occupying around {convert_size(source_size)}\n"
            f"Location: {self._file_path}"
        )

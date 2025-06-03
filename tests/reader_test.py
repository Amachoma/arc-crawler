import pytest
from pathlib import Path

from arc_crawler.reader import IndexReader
from arc_crawler.utils import write_line


class Consts:
    def __init__(self, temp_dir):
        parent_dir = Path(temp_dir) / "out"
        filename = "reader-test"

        self.parent_dir = parent_dir
        self.filename = filename

        self.out_path = parent_dir / filename
        self.source_path = parent_dir / f"{filename}.jsonl"
        self.index_path = parent_dir / f"{filename}.index"

        self.dummy_records = [
            {"id": 1, "value": "foo"},
            {"id": 2, "value": "bar"},
            {"id": 3, "value": "baz"},
        ]

    @staticmethod
    def init_reader(monkeypatch, tmp_path):
        consts = Consts(tmp_path)
        monkeypatch.setattr("builtins.input", lambda _: "y")

        reader = IndexReader(consts.source_path, index_record_setter=lambda record: {"id": record.get("id")})

        for rec in consts.dummy_records:
            reader.write(rec)

        return reader, consts.dummy_records


class TestIndexReaderInit:
    @pytest.mark.parametrize(
        "input_res",
        ["n", "y"],
        ids=[
            "Throws FileNotFoundError if declined to create new files",
            "Successfully creates new files",
        ],
    )
    def test_can_init_interactive(self, monkeypatch, tmp_path, input_res):
        monkeypatch.setattr("builtins.input", lambda _: input_res)
        consts = Consts(tmp_path)

        if input_res == "y":
            IndexReader(consts.out_path)
            assert Path(consts.source_path).exists() == True
            assert Path(consts.index_path).exists() == True
        elif input_res == "n":
            with pytest.raises(FileNotFoundError):
                IndexReader(consts.out_path)

    def test_can_open_empty(self, tmp_path):
        consts = Consts(tmp_path)

        # Create empty files
        if not consts.parent_dir.exists():
            consts.parent_dir.mkdir()
        Path(consts.source_path).touch()
        Path(consts.index_path).touch()

        reader = IndexReader(consts.source_path)

        assert len(reader) == 0

    def test_can_generate_index_from_source(self, tmp_path):
        consts = Consts(tmp_path)

        if not consts.parent_dir.exists():
            consts.parent_dir.mkdir(parents=True, exist_ok=True)

        consts.source_path.touch()
        for rec in consts.dummy_records:
            write_line(consts.source_path, rec)

        assert len(IndexReader(consts.source_path)) == len(consts.dummy_records)


class TestIndexReaderIO:
    def test_can_write(self, monkeypatch, tmp_path):
        reader, dummy_records = Consts.init_reader(monkeypatch, tmp_path)
        assert len(reader) == len(dummy_records)

    def test_can_read_by_index(self, monkeypatch, tmp_path):
        reader, dummy_records = Consts.init_reader(monkeypatch, tmp_path)

        for rec_idx in range(len(dummy_records)):
            assert reader.get(rec_idx)["value"] == dummy_records[rec_idx]["value"]

    def test_can_read_by_filter(self, monkeypatch, tmp_path):
        reader, dummy_records = Consts.init_reader(monkeypatch, tmp_path)

        assert len(reader.get(lambda rec: True)) == len(dummy_records)

        specific_id = lambda rec: rec["id"] == 2
        assert reader.get(specific_id) == list(filter(specific_id, dummy_records))[0]


class TestIndexReaderFeatures:
    def test_can_iterate(self, monkeypatch, tmp_path):
        reader, dummy_records = Consts.init_reader(monkeypatch, tmp_path)

        iterator = iter(reader)
        for i in range(len(dummy_records)):
            assert next(iterator) == dummy_records[i]

    def test_can_access_by_index(self, monkeypatch, tmp_path):
        reader, dummy_records = Consts.init_reader(monkeypatch, tmp_path)

        for i in range(len(dummy_records)):
            assert reader[i] == dummy_records[i]

    def test_can_slice(self, monkeypatch, tmp_path):
        reader, dummy_records = Consts.init_reader(monkeypatch, tmp_path)
        assert reader[0 : len(dummy_records) : 2] == dummy_records[0 : len(dummy_records) : 2]

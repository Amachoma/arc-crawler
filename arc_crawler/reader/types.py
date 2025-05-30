from typing import Any, Dict, Protocol, List, ForwardRef, Literal


class FilterFunc(Protocol):
    def __call__(self, record: Dict[str, Any]) -> bool:
        pass


class IndexSetterFunc(Protocol):
    def __call__(self, record: Dict[str, Any]) -> Dict[str, Any]:
        pass


class IndexLoaderFunc(Protocol):
    def __call__(self, txt_line: str) -> Any:
        pass


JsonPrimitive = str | int | float | bool | None
JsonSerializable = JsonPrimitive | Dict[str, ForwardRef("JSONValue")] | List[ForwardRef("JSONValue")]

MkdirMode = Literal["interactive", "forced", "disabled"]

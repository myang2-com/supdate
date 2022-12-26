from __future__ import annotations

import json
from collections.abc import MutableMapping
from dataclasses import Field, MISSING, dataclass, fields, is_dataclass
from pathlib import Path
from typing import Dict, List, Optional, Type, Union, get_type_hints

from typing_inspect import get_args, get_origin, is_optional_type


def get_optional(tp: Type):
    if is_optional_type(tp):
        if get_origin(tp) == Union:
            for t in get_args(tp):
                if t is None:
                    continue

                return t


@dataclass(repr=False)
class Namespace(MutableMapping):
    def __iter__(self):
        defaults = {
            field.name: field.default
            for field in fields(self)
            if field.default is not MISSING
        }

        for key, value in self.__dict__.items():
            if key.startswith("_"):
                continue

            default = defaults.get(key, MISSING)
            if value != default:
                yield key

    def __len__(self):
        return len(self.__dict__)

    def __getitem__(self, item):
        value = getattr(self, item, MISSING)
        if value is MISSING:
            raise KeyError(item)

        return value

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def __delitem__(self, key):
        delattr(self, key)

    def __contains__(self, item):
        return hasattr(self, item)

    @classmethod
    def from_json(cls, data: dict):
        data = data.copy()
        values = {}

        hints = get_type_hints(cls)
        for field in fields(cls):  # type: Field
            if field.default is not MISSING or field.default_factory is not MISSING:
                value = data.pop(field.name, MISSING)
                if value is MISSING:
                    continue
            else:
                value = data.pop(field.name)

            tp = hints.get(field.name, field.type)
            tp = get_optional(tp) or tp
            origin = get_origin(tp)

            if is_dataclass(tp) and issubclass(tp, Namespace):
                value = tp.from_json(value)
            elif origin in (list, List):
                (tp,) = get_args(tp)
                if is_dataclass(tp) and issubclass(tp, Namespace):
                    assert isinstance(value, list)
                    value = [tp.from_json(item) for item in value]
            elif origin in (dict, Dict):
                tk, tv = get_args(tp)
                assert tk == str
                if is_dataclass(tv) and issubclass(tv, Namespace):
                    assert isinstance(value, dict)
                    value = {key: tv.from_json(value) for key, value in value.items()}
            # Forced to cast a type because of wrong floats
            if field.type == "int":
                value = int(value)

            values[field.name] = value

        # noinspection PyArgumentList
        obj = cls(**values)
        obj.__dict__.update(data)
        return obj

    def to_json(self) -> dict:
        fids = {field.name: field for field in fields(self)}

        def visit(obj):
            if isinstance(obj, Namespace):
                return obj.to_json()
            elif isinstance(obj, list):
                return [visit(item) for item in obj]
            elif isinstance(obj, dict):
                return {key: visit(value) for key, value in obj.items()}
            else:
                return obj

        result = {}
        for key, value in self.items():
            field: Optional[Field] = fids.get(key)
            if field is not None:
                if field.default == value:
                    continue

            result[key] = visit(value)

        return result

    def write_to_path(self, path: Path):
        obj = self.to_json()
        s = json.dumps(obj, indent=4, sort_keys=False)
        path.write_text(s, encoding="utf-8")

    @classmethod
    def read_from_path(cls, path: Path):
        s = path.read_text(encoding="utf-8")
        obj = json.loads(s)
        return cls.from_json(obj)

    def __repr__(self):
        names = set()
        items = []
        for field in fields(self):  # type: Field
            if field.repr:
                names.add(field.name)

                value = getattr(self, field.name, field.default)
                if value != field.default:
                    items.append(f"{field.name}={value!r}")

        data = {key: value for key, value in self.items() if key not in names}
        if items and data:
            return f"{type(self).__name__}({', '.join(items)}, **{data!r})"
        elif items and not data:
            return f"{type(self).__name__}({', '.join(items)})"
        elif not items and data:
            return f"{type(self).__name__}(**{data!r})"
        else:
            return f"{type(self).__name__}()"

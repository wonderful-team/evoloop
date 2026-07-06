"""Generic Pydantic utility functions for schema cleaning and type coercion."""

import typing

from pydantic import BaseModel


def resolve_base_type(ann):
    origin = typing.get_origin(ann) or ann
    if origin is typing.Union:
        args = typing.get_args(ann)
        for arg in args:
            if arg is not type(None):
                return typing.get_origin(arg) or arg
    return origin


def clean_none_values(d: any, schema: type = None) -> any:
    if schema is None or not isinstance(d, dict) or not issubclass(schema, BaseModel):
        if isinstance(d, dict):
            return {k: clean_none_values(v) for k, v in d.items()}
        elif isinstance(d, list):
            return [clean_none_values(x) for x in d]
        elif d is None:
            return ""
        return d

    result = d.copy()
    for fname, finfo in schema.model_fields.items():
        if fname not in result:
            continue
        val = result[fname]
        annotation = finfo.annotation

        base_type = resolve_base_type(annotation)

        if val is None:
            if base_type is bool:
                result[fname] = False
            elif base_type is list:
                result[fname] = []
            elif base_type is dict:
                result[fname] = {}
            elif base_type is int:
                result[fname] = 0
            elif base_type is float:
                result[fname] = 0.0
            else:
                result[fname] = ""
        else:
            if base_type is list:
                if not isinstance(val, list):
                    if isinstance(val, str):
                        if val.strip():
                            result[fname] = [t.strip() for t in val.split(",") if t.strip()]
                        else:
                            result[fname] = []
                    else:
                        result[fname] = []
                else:
                    args = typing.get_args(annotation)
                    if args and args[0] is str:
                        result[fname] = [str(x) for x in val if x is not None]
            elif base_type is dict:
                if not isinstance(val, dict):
                    result[fname] = {}
            elif base_type is str:
                if not isinstance(val, str):
                    result[fname] = str(val)
            elif base_type is bool:
                if not isinstance(val, bool):
                    if isinstance(val, str):
                        result[fname] = val.lower() in ("true", "1", "yes")
                    else:
                        result[fname] = bool(val)
            elif base_type is int or base_type is float:
                if not isinstance(val, (int, float)):
                    try:
                        result[fname] = base_type(val)
                    except (ValueError, TypeError):
                        result[fname] = 0.0 if base_type is float else 0

        val = result[fname]
        if isinstance(val, dict):
            sub_model = None
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                sub_model = annotation
            else:
                args = typing.get_args(annotation)
                if args:
                    for arg in args:
                        if isinstance(arg, type) and issubclass(arg, BaseModel):
                            sub_model = arg
                            break
            if sub_model:
                result[fname] = clean_none_values(val, sub_model)
        elif isinstance(val, list) and val:
            args = typing.get_args(annotation)
            sub_model = None
            if args:
                arg = args[0]
                if isinstance(arg, type) and issubclass(arg, BaseModel):
                    sub_model = arg
                else:
                    for sub in typing.get_args(arg):
                        if isinstance(sub, type) and issubclass(sub, BaseModel):
                            sub_model = sub
                            break
            if sub_model:
                result[fname] = [clean_none_values(x, sub_model) if isinstance(x, dict) else x for x in val]

    return result


def distribute_list_to_schema_fields(data: list, schema: type) -> dict:
    list_fields = {}
    for fname, finfo in schema.model_fields.items():
        annotation = finfo.annotation
        origin = typing.get_origin(annotation)
        if annotation is list or origin is list:
            args = typing.get_args(annotation)
            if args:
                arg = args[0]
                if isinstance(arg, type) and issubclass(arg, BaseModel):
                    list_fields[fname] = arg
                else:
                    for sub in typing.get_args(arg):
                        if isinstance(sub, type) and issubclass(sub, BaseModel):
                            list_fields[fname] = sub
                            break

    if not list_fields:
        return {}

    result = {fname: [] for fname in list_fields.keys()}
    for item in data:
        if not isinstance(item, dict):
            first_fname = list(list_fields.keys())[0]
            result[first_fname].append(item)
            continue

        best_fname = None
        best_score = -1

        for fname, item_model in list_fields.items():
            model_keys = set(item_model.model_fields.keys())
            item_keys = set(item.keys())
            overlap = model_keys.intersection(item_keys)
            score = len(overlap)

            from pydantic_core import PydanticUndefined
            required_overlap = 0
            for rname, rinfo in item_model.model_fields.items():
                if rinfo.default is PydanticUndefined and rname in item_keys:
                    required_overlap += 1
            score += required_overlap * 2

            if score > best_score:
                best_score = score
                best_fname = fname

        if best_fname:
            result[best_fname].append(item)

    return result

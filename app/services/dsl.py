from __future__ import annotations

import io
import ast
import operator as pyop
import re
import datetime as _dt
from typing import Any, Dict, List, Optional

import jmespath
import polars as pl


class DSLExecutionError(Exception):
    pass


# ----- Safe expression evaluation (subset of Python) -----
_ALLOWED_BINOPS = {
    ast.Add: pyop.add,
    ast.Sub: pyop.sub,
    ast.Mult: pyop.mul,
    ast.Div: pyop.truediv,
    ast.Mod: pyop.mod,
}
_ALLOWED_BOOL_OPS = {ast.And, ast.Or}
_ALLOWED_CMP_OPS = {
    ast.Eq: pyop.eq,
    ast.NotEq: pyop.ne,
    ast.Lt: pyop.lt,
    ast.LtE: pyop.le,
    ast.Gt: pyop.gt,
    ast.GtE: pyop.ge,
    ast.Is: pyop.is_,
    ast.IsNot: pyop.is_not,
    ast.In: (lambda left, right: left in right),
    ast.NotIn: (lambda left, right: left not in right),
}
_ALLOWED_UNARY = {ast.USub: pyop.neg, ast.UAdd: lambda x: x, ast.Not: pyop.not_}


def _regex_match(text: Any, pattern: str) -> bool:
    try:
        return bool(re.search(pattern, "" if text is None else str(text)))
    except re.error as e:
        raise DSLExecutionError(f"Invalid regex in expression: {e}")


def _to_str(value: Any) -> str:
    return "" if value is None else str(value)

def _first_digit(value: Any) -> Any:
    s = _to_str(value)
    for ch in s:
        if ch.isdigit():
            return ch
    return None

def _last_digit(value: Any) -> Any:
    s = _to_str(value)
    for ch in reversed(s):
        if ch.isdigit():
            return ch
    return None

def _leading_number(value: Any) -> Any:
    s = _to_str(value)
    out = []
    for ch in s:
        if ch.isdigit():
            out.append(ch)
        else:
            break
    return "".join(out) if out else None

def _trailing_number(value: Any) -> Any:
    s = _to_str(value)
    out = []
    for ch in reversed(s):
        if ch.isdigit():
            out.append(ch)
        else:
            break
    out.reverse()
    return "".join(out) if out else None

def _digits(value: Any) -> Any:
    s = _to_str(value)
    out = [ch for ch in s if ch.isdigit()]
    return "".join(out) if out else None

def _left(value: Any, n: int) -> str:
    return _to_str(value)[: int(n)]

def _right(value: Any, n: int) -> str:
    n = int(n)
    s = _to_str(value)
    return s[-n:] if n != 0 else ""

def _mid(value: Any, start: int, length: Optional[int] = None) -> str:
    s = _to_str(value)
    i = int(start)
    return s[i : i + int(length)] if length is not None else s[i:]

def _find(sub: Any, text: Any) -> int:
    # 0-based index; returns -1 if not found
    return _to_str(text).find(_to_str(sub))

def _search(sub: Any, text: Any) -> int:
    # case-insensitive find; 0-based; -1 if not found
    return _to_str(text).lower().find(_to_str(sub).lower())

def _ceil(x: Any, ndigits: Optional[int] = None) -> float:
    import math
    if ndigits is None:
        return math.ceil(float(x))
    p = 10 ** int(ndigits)
    return math.ceil(float(x) * p) / p

def _floor(x: Any, ndigits: Optional[int] = None) -> float:
    import math
    if ndigits is None:
        return math.floor(float(x))
    p = 10 ** int(ndigits)
    return math.floor(float(x) * p) / p

def _sqrt(x: Any) -> float:
    import math
    return math.sqrt(float(x))

def _pow(x: Any, y: Any) -> float:
    return float(x) ** float(y)

def _round_to(x: Any, ndigits: int = 0) -> float:
    return round(float(x), int(ndigits))

def _ifelse(cond: Any, a: Any, b: Any) -> Any:
    return a if bool(cond) else b

def _coalesce_val(*args: Any) -> Any:
    for v in args:
        if v is not None:
            return v
    return None

def _concat_ws(sep: Any, *args: Any) -> str:
    s = str(sep)
    parts = ["" if v is None else str(v) for v in args]
    return s.join(parts)

def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")

def _date_ymd(y: Any, m: Any, d: Any) -> str:
    dt = _dt.date(int(y), int(m), int(d))
    return dt.isoformat()

def _to_date_iso(value: Any, fmt: Optional[str] = None) -> str:
    s = _to_str(value)
    try:
        if fmt:
            dt = _dt.datetime.strptime(s, fmt).date()
            return dt.isoformat()
        # try ISO
        return _dt.date.fromisoformat(s).isoformat()
    except Exception:
        raise DSLExecutionError("to_date: invalid date or format")

def _year(value: Any) -> int:
    s = _to_str(value)
    try:
        if "T" in s or " " in s:
            return _dt.datetime.fromisoformat(s.replace("Z", "+00:00")).year
        return _dt.date.fromisoformat(s).year
    except Exception:
        raise DSLExecutionError("year(): invalid date")

def _month(value: Any) -> int:
    s = _to_str(value)
    try:
        if "T" in s or " " in s:
            return _dt.datetime.fromisoformat(s.replace("Z", "+00:00")).month
        return _dt.date.fromisoformat(s).month
    except Exception:
        raise DSLExecutionError("month(): invalid date")

def _day(value: Any) -> int:
    s = _to_str(value)
    try:
        if "T" in s or " " in s:
            return _dt.datetime.fromisoformat(s.replace("Z", "+00:00")).day
        return _dt.date.fromisoformat(s).day
    except Exception:
        raise DSLExecutionError("day(): invalid date")

def _date_add_days(value: Any, days: Any) -> str:
    s = _to_str(value)
    try:
        base = _dt.date.fromisoformat(s)
        return (base + _dt.timedelta(days=int(days))).isoformat()
    except Exception:
        raise DSLExecutionError("date_add_days(): invalid date")

def _date_diff_days(a: Any, b: Any) -> int:
    sa = _to_str(a)
    sb = _to_str(b)
    try:
        da = _dt.date.fromisoformat(sa)
        db = _dt.date.fromisoformat(sb)
        return (da - db).days
    except Exception:
        raise DSLExecutionError("date_diff_days(): invalid date(s)")

def _parse_number(value: Any) -> Optional[float]:
    s = _to_str(value)
    m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
    return float(m.group(0)) if m else None

def _safe_int(value: Any, default: Any = 0) -> int:
    if value is None:
        try:
            return int(default)
        except Exception:
            return 0
    try:
        return int(value)
    except Exception:
        num = _parse_number(value)
        try:
            return int(num) if num is not None else int(default)
        except Exception:
            return 0

def _safe_float(value: Any, default: Any = 0.0) -> float:
    if value is None:
        try:
            return float(default)
        except Exception:
            return 0.0
    try:
        return float(value)
    except Exception:
        num = _parse_number(value)
        try:
            return float(num) if num is not None else float(default)
        except Exception:
            return 0.0

def _sum_nonnull(*args: Any) -> float:
    total = 0.0
    for v in args:
        try:
            total += float(v) if v is not None else 0.0
        except Exception:
            num = _parse_number(v)
            total += float(num) if num is not None else 0.0
    return total

_ALLOWED_FUNCS = {
    "len": len,
    "int": int,
    "float": float,
    "str": str,
    "abs": abs,
    "round": round,
    "round_to": _round_to,
    "ceil": _ceil,
    "floor": _floor,
    "sqrt": _sqrt,
    "pow": _pow,
    "regex_match": _regex_match,
    # Deterministic time helpers (UTC-based)
    "today": (lambda: _dt.datetime.now(_dt.timezone.utc).date().isoformat()),
    "now": _now_iso,
    "date": _date_ymd,
    "to_date": _to_date_iso,
    "year": _year,
    "month": _month,
    "day": _day,
    "date_add_days": _date_add_days,
    "date_diff_days": _date_diff_days,
    # String helpers
    "upper": (lambda s: _to_str(s).upper()),
    "lower": (lambda s: _to_str(s).lower()),
    "trim": (lambda s: _to_str(s).strip()),
    "substr": (lambda s, start, length=None: _to_str(s)[int(start): (int(start) + int(length))] if length is not None else _to_str(s)[int(start):]),
    "left": _left,
    "right": _right,
    "mid": _mid,
    "find": _find,
    "search": _search,
    "concat_ws": _concat_ws,
    "startswith": (lambda s, p: _to_str(s).startswith(str(p))),
    "endswith": (lambda s, p: _to_str(s).endswith(str(p))),
    "replace": (lambda s, a, b: _to_str(s).replace(str(a), str(b))),
    "regex_extract": (lambda s, pat, grp=0: (re.search(pat, _to_str(s)).group(int(grp)) if re.search(pat, _to_str(s)) else None)),
    "to_bool": (lambda v: str(v).strip().lower() in ("1", "true", "yes", "on")),
    "ifelse": _ifelse,
    "coalesce_val": _coalesce_val,
    "parse_number": _parse_number,
    "safe_int": _safe_int,
    "safe_float": _safe_float,
    "sum_nonnull": _sum_nonnull,
    # Natural-language friendly helpers
    "first_digit": _first_digit,
    "last_digit": _last_digit,
    "leading_number": _leading_number,
    "trailing_number": _trailing_number,
    "digits": _digits,
}


def _eval_expr(expr: str, env: Dict[str, Any]) -> Any:
    try:
        node = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise DSLExecutionError(f"Invalid expression syntax: {e}") from e

    def _eval(n: ast.AST) -> Any:
        if isinstance(n, ast.Expression):
            return _eval(n.body)
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.Name):
            if n.id in env:
                return env[n.id]
            raise DSLExecutionError(f"Unknown name in expression: {n.id}")
        if isinstance(n, ast.UnaryOp) and type(n.op) in _ALLOWED_UNARY:
            return _ALLOWED_UNARY[type(n.op)](_eval(n.operand))
        if isinstance(n, ast.BoolOp) and type(n.op) in _ALLOWED_BOOL_OPS:
            if isinstance(n.op, ast.And):
                result = True
                for v in n.values:
                    result = bool(result and _eval(v))
                    if not result:
                        break
                return result
            else:
                result = False
                for v in n.values:
                    result = bool(result or _eval(v))
                    if result:
                        break
                return result
        if isinstance(n, ast.BinOp) and type(n.op) in _ALLOWED_BINOPS:
            try:
                return _ALLOWED_BINOPS[type(n.op)](_eval(n.left), _eval(n.right))
            except Exception as e:
                raise DSLExecutionError(f"Expression evaluation failed: {e}")
        if isinstance(n, ast.Compare):
            left = _eval(n.left)
            for op, comp in zip(n.ops, n.comparators):
                if type(op) not in _ALLOWED_CMP_OPS:
                    raise DSLExecutionError("Comparator not allowed")
                right = _eval(comp)
                if not _ALLOWED_CMP_OPS[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name) and n.func.id in _ALLOWED_FUNCS:
                func = _ALLOWED_FUNCS[n.func.id]
                args = [_eval(a) for a in n.args]
                if n.keywords:
                    raise DSLExecutionError("Keywords not allowed in expressions")
                try:
                    return func(*args)
                except Exception as e:
                    raise DSLExecutionError(f"Function call failed: {n.func.id}({', '.join(map(str, args))}): {e}")
            raise DSLExecutionError("Function not allowed in expressions")
        if isinstance(n, ast.IfExp):
            return _eval(n.body) if bool(_eval(n.test)) else _eval(n.orelse)
        # Disallow: Attribute, Subscript, Dict, List, Tuple, comprehensions, etc.
        raise DSLExecutionError(f"Expression element not allowed: {type(n).__name__}")

    return _eval(node)


def _ensure_dataframe(input_payload: Dict[str, Any]) -> pl.DataFrame:
    """
    Convert supported inline inputs into a Polars DataFrame.
    Supported media_type: text | csv | json. If media_type is omitted, it is auto-detected:
    - Try JSON (expects list[object]) -> table
    - Try CSV via polars.read_csv -> table
    - Fallback to text (single column 'line')
    """
    media_type = input_payload.get("media_type")
    data = input_payload.get("data")
    options = input_payload.get("options") or {}

    if media_type == "text" or media_type is None:
        # Auto-detect if not specified
        if media_type is None and isinstance(data, str):
            # Try JSON
            try:
                import json

                parsed = json.loads(data)
                if isinstance(parsed, list):
                    if len(parsed) == 0 or isinstance(parsed[0], dict):
                        return pl.DataFrame(parsed, strict=False)
            except Exception:
                pass
            # Try CSV only if it looks like CSV
            if any(sep in data for sep in [",", "\t", ";", "|"]):
                try:
                    return pl.read_csv(io.StringIO(data))
                except Exception:
                    pass
        # Fallback to text (lines)
        if not isinstance(data, str):
            raise DSLExecutionError("text input requires 'data' as string")
        lines = data.splitlines()
        return pl.DataFrame({"line": lines}, strict=False)

    if media_type == "csv":
        if not isinstance(data, str):
            raise DSLExecutionError("csv input requires 'data' as string (CSV content)")
        delimiter = options.get("delimiter", ",")
        has_header = options.get("has_header", True)
        encoding = options.get("encoding", "utf8")
        return pl.read_csv(
            io.StringIO(data),
            separator=delimiter,
            has_header=has_header,
            encoding=encoding,
        )

    if media_type == "json":
        # Expect list[dict] or dict (object) or str with JSON? For MVP: list[dict]
        if isinstance(data, list):
            return pl.DataFrame(data, strict=False)
        raise DSLExecutionError("json input requires 'data' as list[object]")

    raise DSLExecutionError(f"Unsupported media_type: {media_type}")


def _require_columns(df: pl.DataFrame, columns: List[str], op_name: str) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise DSLExecutionError(
            f"{op_name}: missing columns {missing}. Available columns: {df.columns}"
        )


def _apply_regex_extract(
    df: pl.DataFrame, step: Dict[str, Any]
) -> pl.DataFrame:
    column = step.get("column", "line")
    pattern = step["pattern"]
    as_col = step["as"]
    group = step.get("group", 0)

    _require_columns(df, [column], "regex_extract")

    # Polars str.extract requires a capturing group index (1-based).
    # If group == 0 (whole match), wrap the pattern in a single capturing group.
    effective_pattern = pattern if group != 0 else f"({pattern})"
    group_index = group if group != 0 else 1

    try:
        return df.with_columns(
            pl.col(column).cast(pl.Utf8, strict=False).str.extract(effective_pattern, group_index).alias(as_col)
        )
    except Exception as e:
        raise DSLExecutionError(f"regex_extract: {e}")


def _apply_regex_replace(
    df: pl.DataFrame, step: Dict[str, Any]
) -> pl.DataFrame:
    column = step["column"]
    pattern = step["pattern"]
    replacement = step.get("replacement", "")
    as_col = step.get("as", column)
    _require_columns(df, [column], "regex_replace")
    try:
        expr = pl.col(column).cast(pl.Utf8, strict=False).str.replace_all(pattern, replacement)
    except Exception as e:
        raise DSLExecutionError(f"regex_replace: {e}")
    if as_col == column:
        return df.with_columns(expr.alias(column))
    return df.with_columns(expr.alias(as_col))


def _apply_select(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    columns = step["columns"]
    _require_columns(df, columns, "select")
    return df.select(columns)


def _apply_rename(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    mapping = step["mapping"]
    _require_columns(df, list(mapping.keys()), "rename")
    return df.rename(mapping)


def _apply_drop(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    columns = step["columns"]
    present = [c for c in columns if c in df.columns]
    if not present:
        return df
    return df.drop(present)


def _apply_cast(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    mapping: Dict[str, str] = step["mapping"]
    _require_columns(df, list(mapping.keys()), "cast")
    casts = []
    for col, dtype in mapping.items():
        pl_type = {
            "int": pl.Int64,
            "float": pl.Float64,
            "str": pl.Utf8,
            "bool": pl.Boolean,
            # Dates can be added later with format handling
        }.get(dtype)
        if pl_type is None:
            raise DSLExecutionError(f"Unsupported cast dtype: {dtype}")
        casts.append(pl.col(col).cast(pl_type, strict=False).alias(col))
    if casts:
        return df.with_columns(casts)
    return df


def _apply_fill_null(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    mapping: Dict[str, Any] = step["mapping"]
    _require_columns(df, list(mapping.keys()), "fill_null")
    return df.with_columns([pl.col(c).fill_null(v).alias(c) for c, v in mapping.items()])


def _apply_filter_eq(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    column = step["column"]
    value = step["value"]
    _require_columns(df, [column], "filter_eq")
    return df.filter(pl.col(column) == value)


def _apply_filter_regex(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    column = step["column"]
    pattern = step["pattern"]
    _require_columns(df, [column], "filter_regex")
    try:
        return df.filter(pl.col(column).cast(pl.Utf8, strict=False).str.contains(pattern))
    except Exception as e:
        raise DSLExecutionError(f"filter_regex: {e}")


def _apply_slice(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    offset = int(step.get("offset", 0))
    length: Optional[int] = step.get("length")
    return df.slice(offset, length) if length is not None else df.slice(offset)


def _apply_json_extract(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    """
    Apply a JMESPath expression to each row (treated as a dict) and put result into a new column.
    Note: This uses row-wise Python and is fine for small MB-scale data in MVP.
    """
    expr = step["expr"]
    as_col = step["as"]
    # Convert each row to dict; safe for small datasets.
    dicts = df.to_dicts()
    values = [jmespath.search(expr, row) for row in dicts]
    return df.with_columns(pl.Series(as_col, values))


def _apply_add_row_number(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    as_col = step.get("as", "row_index")
    start = int(step.get("start", 0))
    return df.with_columns(pl.Series(as_col, list(range(start, start + df.height))))


def _apply_filter_expr(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    expr = step["expr"]
    rows = df.to_dicts()
    mask: List[bool] = []
    for idx, row in enumerate(rows):
        # Ensure column names override helper function names
        env = {**_ALLOWED_FUNCS, **row, "row_index": idx}
        val = _eval_expr(expr, env)
        mask.append(bool(val))
    return df.filter(pl.Series("mask", mask))


def _apply_compute_expr(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    expr = step["expr"]
    as_col = step["as"]
    rows = df.to_dicts()
    values: List[Any] = []
    for idx, row in enumerate(rows):
        # Ensure column names override helper function names
        env = {**_ALLOWED_FUNCS, **row, "row_index": idx}
        values.append(_eval_expr(expr, env))
    return df.with_columns(pl.Series(as_col, values))


def _apply_group_by_agg(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    keys: List[str] = step.get("keys") or []
    aggs: List[Dict[str, Any]] = step.get("aggregations") or []
    if not aggs:
        raise DSLExecutionError("group_by_agg: 'aggregations' is required")
    exprs = []
    for spec in aggs:
        func = spec["func"]
        as_col = spec.get("as")
        col = spec.get("column")
        if func == "count":
            e = pl.count()
            exprs.append(e.alias(as_col or "count"))
        else:
            if col is None:
                raise DSLExecutionError("group_by_agg: 'column' required for non-count")
            base = pl.col(col)
            if func == "sum":
                e = base.sum()
            elif func == "mean":
                e = base.mean()
            elif func == "min":
                e = base.min()
            elif func == "max":
                e = base.max()
            elif func == "first":
                e = base.first()
            elif func == "last":
                e = base.last()
            elif func == "n_unique":
                e = base.n_unique()
            elif func == "concat_str":
                delimiter = spec.get("delimiter", "")
                e = base.cast(pl.Utf8, strict=False).str.concat(delimiter)
            else:
                raise DSLExecutionError(f"group_by_agg: unsupported func {func}")
            exprs.append(e.alias(as_col or f"{col}_{func}"))
    if keys:
        return df.group_by(keys).agg(exprs)
    else:
        # global aggregation
        return df.select(exprs)


def _apply_sort_by(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    columns: List[str] = step["columns"]
    descending = step.get("descending", False)
    if isinstance(descending, list):
        desc = [bool(x) for x in descending]
    else:
        desc = bool(descending)
    return df.sort(by=columns, descending=desc)


def _apply_distinct(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    columns: Optional[List[str]] = step.get("columns")
    if columns:
        return df.unique(subset=columns, maintain_order=True)
    return df.unique(maintain_order=True)


def _apply_explode(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    columns: List[str] = step["columns"]
    return df.explode(columns)


def _apply_split_to_rows(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    column: str = step["column"]
    delimiter: str = step.get("delimiter", ",")
    as_col: str = step.get("as", column)
    drop_original: bool = bool(step.get("drop_original", True))
    df2 = df.with_columns(pl.col(column).cast(pl.Utf8, strict=False).str.split(delimiter).alias(as_col))
    if drop_original and as_col != column:
        df2 = df2.drop([column])
    return df2.explode(as_col)


def _apply_concat_columns(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    columns: List[str] = step["columns"]
    if not columns:
        raise DSLExecutionError("concat_columns: 'columns' is required")
    _require_columns(df, columns, "concat_columns")
    delimiter: str = step.get("delimiter", "")
    as_col: str = step.get("as", "line")
    expr = pl.concat_str([pl.col(c).cast(pl.Utf8, strict=False) for c in columns], separator=delimiter).alias(as_col)
    return df.with_columns(expr)


def _apply_split_column(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    column: str = step["column"]
    into: List[str] = step.get("into") or []
    if not into:
        raise DSLExecutionError("split_column: 'into' (list of new column names) is required")
    _require_columns(df, [column], "split_column")
    delimiter: str = step.get("delimiter", ",")
    drop_original: bool = bool(step.get("drop_original", False))
    n_parts = max(1, len(into) - 1)
    try:
        tmp = pl.col(column).cast(pl.Utf8, strict=False).str.split_exact(delimiter, n_parts, inclusive=False).alias("_split_tmp")
        df2 = df.with_columns(tmp)
        df2 = df2.with_columns([pl.col("_split_tmp").struct.field(i).alias(name) for i, name in enumerate(into)])
        df2 = df2.drop(["_split_tmp"] + ([column] if drop_original else []))
        return df2
    except Exception as e:
        raise DSLExecutionError(f"split_column: {e}")


def _apply_coalesce(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    columns: List[str] = step["columns"]
    as_col: str = step.get("as", columns[0] if columns else "value")
    if not columns:
        raise DSLExecutionError("coalesce: 'columns' is required")
    _require_columns(df, columns, "coalesce")
    expr = pl.coalesce([pl.col(c) for c in columns]).alias(as_col)
    return df.with_columns(expr)


def _apply_drop_na(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    columns: List[str] = step.get("columns") or []
    if columns:
        _require_columns(df, columns, "drop_na")
        return df.drop_nulls(subset=columns)
    return df.drop_nulls()


def _apply_to_datetime(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    column: str = step["column"]
    _require_columns(df, [column], "to_datetime")
    as_col: str = step.get("as", column)
    fmt: Optional[str] = step.get("format")
    try:
        expr = pl.col(column).cast(pl.Utf8, strict=False).str.strptime(pl.Datetime, format=fmt, strict=False, exact=False).alias(as_col)
        return df.with_columns(expr)
    except Exception as e:
        raise DSLExecutionError(f"to_datetime: {e}")


def _apply_head(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    n = int(step.get("n", 5))
    return df.head(n)


def _apply_tail(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    n = int(step.get("n", 5))
    return df.tail(n)


def _apply_sample(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    n = step.get("n")
    frac = step.get("frac")
    with_replacement = bool(step.get("with_replacement", False))
    seed = step.get("seed")
    try:
        if frac is not None:
            return df.sample(fraction=float(frac), with_replacement=with_replacement, shuffle=True, seed=seed)
        if n is None:
            raise DSLExecutionError("sample: 'n' or 'frac' is required")
        return df.sample(n=int(n), with_replacement=with_replacement, shuffle=True, seed=seed)
    except Exception as e:
        raise DSLExecutionError(f"sample: {e}")


def _apply_regex_extract_multi(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    column = step.get("column", "line")
    pattern = step["pattern"]
    targets: List[str] = step.get("as") or []
    if not targets:
        raise DSLExecutionError("regex_extract_multi: 'as' (list of column names) is required")
    _require_columns(df, [column], "regex_extract_multi")
    try:
        exprs = [
            pl.col(column).cast(pl.Utf8, strict=False).str.extract(pattern, i + 1).alias(name)
            for i, name in enumerate(targets)
        ]
        return df.with_columns(exprs)
    except Exception as e:
        raise DSLExecutionError(f"regex_extract_multi: {e}")


def _apply_replace_values(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    column = step["column"]
    mapping: Dict[Any, Any] = step.get("mapping") or {}
    _require_columns(df, [column], "replace_values")
    if not mapping:
        return df
    try:
        expr = pl.col(column).map_elements(lambda v: mapping.get(v, v), return_dtype=None).alias(step.get("as", column))
        return df.with_columns(expr)
    except Exception as e:
        raise DSLExecutionError(f"replace_values: {e}")


def _apply_lookup(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    on_col: str = step["on"]
    table: List[Dict[str, Any]] = step.get("table") or []
    key_field: str = step.get("key_field", "key")
    value_field: str = step.get("value_field", "value")
    default = step.get("default", None)
    as_col: str = step.get("as", on_col)
    _require_columns(df, [on_col], "lookup")
    if not isinstance(table, list) or not table:
        raise DSLExecutionError("lookup: 'table' must be a non-empty list of {key,value} objects")
    try:
        mapping = {row[key_field]: row[value_field] for row in table}
        expr = pl.col(on_col).map_elements(lambda v: mapping.get(v, default if default is not None else v), return_dtype=None).alias(as_col)
        return df.with_columns(expr)
    except Exception as e:
        raise DSLExecutionError(f"lookup: {e}")


def _apply_pivot_wider(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    keys: List[str] = step.get("keys") or []
    pivot_column: str = step["column"]
    values: List[str] | str = step.get("values") or []
    agg: str = step.get("agg", "first")
    if not keys:
        raise DSLExecutionError("pivot_wider: 'keys' is required")
    _require_columns(df, keys + [pivot_column], "pivot_wider")
    if isinstance(values, list):
        _require_columns(df, values, "pivot_wider")
    try:
        return df.pivot(values=values, index=keys, columns=pivot_column, aggregate_function=agg)
    except Exception as e:
        raise DSLExecutionError(f"pivot_wider: {e}")


def _apply_pivot_longer(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    id_vars: List[str] = step.get("id_vars") or []
    value_vars: Optional[List[str]] = step.get("value_vars")
    var_name: str = step.get("variable_name", "variable")
    val_name: str = step.get("value_name", "value")
    if id_vars:
        _require_columns(df, id_vars, "pivot_longer")
    if value_vars:
        _require_columns(df, value_vars, "pivot_longer")
    try:
        return df.melt(id_vars=id_vars or None, value_vars=value_vars or None, variable_name=var_name, value_name=val_name)
    except Exception as e:
        raise DSLExecutionError(f"pivot_longer: {e}")


def _apply_window_cumsum(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    column: str = step["column"]
    as_col: str = step.get("as", f"{column}_cumsum")
    by: Optional[List[str]] = step.get("partition_by")
    _require_columns(df, [column] + (by or []), "window_cumsum")
    expr = pl.col(column).cum_sum()
    if by:
        expr = expr.over(by)
    return df.with_columns(expr.alias(as_col))


def _apply_rank(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    column: str = step["column"]
    method: str = step.get("method", "ordinal")
    descending: bool = bool(step.get("descending", False))
    by: Optional[List[str]] = step.get("partition_by")
    as_col: str = step.get("as", f"{column}_rank")
    _require_columns(df, [column] + (by or []), "rank")
    expr = pl.col(column).rank(method=method, descending=descending)
    if by:
        expr = expr.over(by)
    return df.with_columns(expr.alias(as_col))


def _apply_rolling_mean(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    column: str = step["column"]
    window: int = int(step.get("window", 3))
    as_col: str = step.get("as", f"{column}_rolling_mean")
    _require_columns(df, [column], "rolling_mean")
    try:
        expr = pl.col(column).rolling_mean(window_size=window).alias(as_col)
        return df.with_columns(expr)
    except Exception as e:
        raise DSLExecutionError(f"rolling_mean: {e}")


def _apply_rolling_sum(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    column: str = step["column"]
    window: int = int(step.get("window", 3))
    as_col: str = step.get("as", f"{column}_rolling_sum")
    _require_columns(df, [column], "rolling_sum")
    try:
        expr = pl.col(column).rolling_sum(window_size=window).alias(as_col)
        return df.with_columns(expr)
    except Exception as e:
        raise DSLExecutionError(f"rolling_sum: {e}")

def _apply_scan(df: pl.DataFrame, step: Dict[str, Any]) -> pl.DataFrame:
    """
    Generic stateful scan/fold that generates a new table of one column.
    Parameters:
      - init: dict of state var -> numeric/string
      - init_from_rows: [{var, column, row, cast?}] (optional)
      - steps: int
      - steps_from_row: {column, row, cast?} (optional)
      - update: dict of state var -> expression (using current state vars)
      - emit: expression (using current state vars)
      - as: output column name (default 'value')
    This discards previous rows and returns a single-column table.
    """
    state: Dict[str, Any] = dict(step.get("init") or {})
    as_col = step.get("as", "value")

    # Seed from rows if requested
    if "init_from_rows" in step:
        for spec in step["init_from_rows"]:
            var = spec["var"]
            column = spec.get("column", "line")
            row_idx = int(spec["row"])
            cast = spec.get("cast")
            if row_idx < 0 or row_idx >= df.height:
                raise DSLExecutionError("init_from_rows: row index out of range")
            value = df[column][row_idx] if column in df.columns else None
            if cast == "int":
                value = int(value)
            elif cast == "float":
                value = float(value)
            elif cast == "str":
                value = str(value)
            state[var] = value

    # Determine steps
    steps = step.get("steps")
    if steps is None and "steps_from_row" in step:
        spec = step["steps_from_row"]
        column = spec.get("column", "line")
        row_idx = int(spec["row"])
        cast = spec.get("cast", "int")
        if row_idx < 0 or row_idx >= df.height:
            raise DSLExecutionError("steps_from_row: row index out of range")
        value = df[column][row_idx] if column in df.columns else None
        steps = int(value) if cast == "int" else float(value)
    if steps is None:
        raise DSLExecutionError("scan: 'steps' or 'steps_from_row' is required")
    try:
        steps_int = int(steps)
    except Exception:
        raise DSLExecutionError("scan: steps must be integer")
    if steps_int < 0 or steps_int > 100000:
        raise DSLExecutionError("scan: steps out of allowed range (0..100000)")

    update: Dict[str, str] = step.get("update") or {}
    emit_expr: str = step.get("emit") or ""
    outputs: List[Any] = []
    for _ in range(steps_int):
        # Ensure state variables override helper function names
        env = {**_ALLOWED_FUNCS, **state}
        next_state: Dict[str, Any] = dict(state)
        for var, uexpr in update.items():
            next_state[var] = _eval_expr(uexpr, env)
        val = _eval_expr(emit_expr, env) if emit_expr else None
        outputs.append(val)
        state = next_state

    return pl.DataFrame({as_col: outputs})


def execute_dsl(dsl: Dict[str, Any], input_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a minimal DSL over text/csv/json input.
    Returns: dict with 'output' (list[dict]) and 'meta'.
    """
    df = _ensure_dataframe(input_payload)
    steps: List[Dict[str, Any]] = dsl.get("steps", [])

    for step in steps:
        op = step["op"]
        if op == "regex_extract":
            df = _apply_regex_extract(df, step)
        elif op == "regex_replace":
            df = _apply_regex_replace(df, step)
        elif op == "select":
            df = _apply_select(df, step)
        elif op == "rename":
            df = _apply_rename(df, step)
        elif op == "drop":
            df = _apply_drop(df, step)
        elif op == "cast":
            df = _apply_cast(df, step)
        elif op == "fill_null":
            df = _apply_fill_null(df, step)
        elif op == "filter_eq":
            df = _apply_filter_eq(df, step)
        elif op == "filter_regex":
            df = _apply_filter_regex(df, step)
        elif op == "slice":
            df = _apply_slice(df, step)
        elif op == "json_extract":
            df = _apply_json_extract(df, step)
        elif op == "take_every":
            # Keep every n-th row using zero-based offset
            n = int(step.get("n", 1))
            offset = int(step.get("offset", 0))
            if n <= 0:
                raise DSLExecutionError("take_every: 'n' must be >= 1")
            # Create row_index column (0-based), filter, then drop it
            row_index = pl.Series("row_index", list(range(df.height)))
            df = df.with_columns(row_index)
            df = df.filter((pl.col("row_index") % n) == (offset % n)).drop(["row_index"])
        elif op == "add_row_number":
            df = _apply_add_row_number(df, step)
        elif op == "filter_expr":
            df = _apply_filter_expr(df, step)
        elif op == "compute_expr":
            df = _apply_compute_expr(df, step)
        elif op == "scan":
            df = _apply_scan(df, step)
        elif op == "group_by_agg":
            df = _apply_group_by_agg(df, step)
        elif op == "sort_by":
            df = _apply_sort_by(df, step)
        elif op == "distinct":
            df = _apply_distinct(df, step)
        elif op == "explode":
            df = _apply_explode(df, step)
        elif op == "split_to_rows":
            df = _apply_split_to_rows(df, step)
        elif op == "concat_columns":
            df = _apply_concat_columns(df, step)
        elif op == "split_column":
            df = _apply_split_column(df, step)
        elif op == "coalesce":
            df = _apply_coalesce(df, step)
        elif op == "drop_na":
            df = _apply_drop_na(df, step)
        elif op == "to_datetime":
            df = _apply_to_datetime(df, step)
        elif op == "head":
            df = _apply_head(df, step)
        elif op == "tail":
            df = _apply_tail(df, step)
        elif op == "sample":
            df = _apply_sample(df, step)
        elif op == "regex_extract_multi":
            df = _apply_regex_extract_multi(df, step)
        elif op == "replace_values":
            df = _apply_replace_values(df, step)
        elif op == "lookup":
            df = _apply_lookup(df, step)
        elif op == "pivot_wider":
            df = _apply_pivot_wider(df, step)
        elif op == "pivot_longer":
            df = _apply_pivot_longer(df, step)
        elif op == "window_cumsum":
            df = _apply_window_cumsum(df, step)
        elif op == "rank":
            df = _apply_rank(df, step)
        elif op == "rolling_mean":
            df = _apply_rolling_mean(df, step)
        elif op == "rolling_sum":
            df = _apply_rolling_sum(df, step)
        else:
            raise DSLExecutionError(f"Unsupported op: {op}")

    # For MVP, return JSON rows
    return {
        "output": df.to_dicts(),
        "meta": {"rows": df.height, "columns": df.columns},
    }



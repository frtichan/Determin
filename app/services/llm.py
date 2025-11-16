from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List

from openai import OpenAI

from ..config import get_settings


ALLOWED_OPS = [
    "regex_extract",
    "regex_replace",
    "regex_extract_multi",
    "replace_values",
    "lookup",
    "select",
    "rename",
    "drop",
    "cast",
    "fill_null",
    "coalesce",
    "filter_eq",
    "filter_regex",
    "drop_na",
    "slice",
    "head",
    "tail",
    "sample",
    "json_extract",
    "take_every",
    "add_row_number",
    "filter_expr",
    "compute_expr",
    "concat_columns",
    "split_column",
    "to_datetime",
    "scan",
    "group_by_agg",
    "sort_by",
    "distinct",
    "explode",
    "split_to_rows",
    "pivot_wider",
    "pivot_longer",
    "window_cumsum",
    "rank",
    "rolling_mean",
    "rolling_sum",
]


def _mask_sample(sample: str) -> str:
    """
    Minimal masking: emails, long digit runs(>=5), phone-like patterns.
    This is a best-effort privacy measure for LLM prompts.
    """
    s = sample
    s = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}", "[EMAIL]", s)
    s = re.sub(r"\\+?\\d[\\d\\-\\s]{7,}\\d", "[PHONE]", s)
    s = re.sub(r"\\d{5,}", "[NUM]", s)
    return s


def _client() -> OpenAI:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=settings.openai_api_key)


def build_system_prompt() -> str:
    return (
        "You generate a deterministic JSON DSL for data transforms.\n"
        "Only use the following operations and fields:\n"
        f"- ops: {', '.join(ALLOWED_OPS)}\n"
        "- schema:\n"
        "  {\n"
        "    \"steps\": [\n"
        "      { \"op\": \"regex_extract\", \"column\": \"<name>\", \"pattern\": \"<regex>\", \"group\": <int>, \"as\": \"<name>\" },\n"
        "      { \"op\": \"regex_extract_multi\", \"column\": \"<name>\", \"pattern\": \"<regex>\", \"as\": [\"g1\", \"g2\", ...] },\n"
        "      { \"op\": \"regex_replace\", \"column\": \"<name>\", \"pattern\": \"<regex>\", \"replacement\": \"<str>\", \"as\": \"<name?>\" },\n"
        "      { \"op\": \"replace_values\", \"column\": \"<name>\", \"mapping\": { \"old\": \"new\" }, \"as\": \"<name?>\" },\n"
        "      { \"op\": \"lookup\", \"on\": \"<col>\", \"table\": [ {\"key\": \"A\", \"value\": 1}, ... ], \"as\": \"<name?>\", \"default\": null },\n"
        "      { \"op\": \"select\", \"columns\": [\"col1\", \"col2\", ...] },\n"
        "      { \"op\": \"rename\", \"mapping\": { \"old\": \"new\" } },\n"
        "      { \"op\": \"drop\", \"columns\": [\"col\"] },\n"
        "      { \"op\": \"cast\", \"mapping\": { \"col\": \"int|float|str|bool\" } },\n"
        "      { \"op\": \"fill_null\", \"mapping\": { \"col\": <value> } },\n"
        "      { \"op\": \"coalesce\", \"columns\": [\"a\", \"b\", ...], \"as\": \"<name>\" },\n"
        "      { \"op\": \"filter_eq\", \"column\": \"col\", \"value\": <value> },\n"
        "      { \"op\": \"filter_regex\", \"column\": \"col\", \"pattern\": \"<regex>\" },\n"
        "      { \"op\": \"drop_na\", \"columns\": [\"col1\", \"col2\", ...] },\n"
        "      { \"op\": \"slice\", \"offset\": <int>, \"length\": <int?> },\n"
        "      { \"op\": \"head\", \"n\": <int> },\n"
        "      { \"op\": \"tail\", \"n\": <int> },\n"
        "      { \"op\": \"sample\", \"n\": <int?>, \"frac\": <float?>, \"with_replacement\": false, \"seed\": <int?> },\n"
        "      { \"op\": \"json_extract\", \"expr\": \"<JMESPath>\", \"as\": \"<name>\" },\n"
        "      { \"op\": \"take_every\", \"n\": <int>, \"offset\": <int> },\n"
        "      { \"op\": \"add_row_number\", \"as\": \"row_index\", \"start\": 0 },\n"
        "      { \"op\": \"filter_expr\", \"expr\": \"row_index % 2 == 1\" },\n"
        "      { \"op\": \"compute_expr\", \"expr\": \"len(line)\", \"as\": \"len\" },\n"
        "      { \"op\": \"concat_columns\", \"columns\": [\"a\", \"b\"], \"delimiter\": \"\\t\", \"as\": \"line\" },\n"
        "      { \"op\": \"split_column\", \"column\": \"line\", \"delimiter\": \",\", \"into\": [\"c1\", \"c2\"], \"drop_original\": false },\n"
        "      { \"op\": \"to_datetime\", \"column\": \"ts\", \"format\": \"%Y-%m-%d %H:%M:%S\", \"as\": \"ts_dt\" },\n"
        "      { \"op\": \"pivot_wider\", \"keys\": [\"k\"], \"column\": \"name\", \"values\": \"val\", \"agg\": \"sum\" },\n"
        "      { \"op\": \"pivot_longer\", \"id_vars\": [\"id\"], \"value_vars\": [\"v1\",\"v2\"], \"variable_name\": \"var\", \"value_name\": \"val\" },\n"
        "      { \"op\": \"window_cumsum\", \"column\": \"v\", \"partition_by\": [\"k\"], \"as\": \"v_cum\" },\n"
        "      { \"op\": \"rank\", \"column\": \"v\", \"partition_by\": [\"k\"], \"method\": \"ordinal\", \"descending\": true, \"as\": \"rnk\" },\n"
        "      { \"op\": \"rolling_mean\", \"column\": \"v\", \"window\": 3, \"as\": \"v_rm\" },\n"
        "      { \"op\": \"rolling_sum\", \"column\": \"v\", \"window\": 3, \"as\": \"v_rs\" },\n"
        "      { \"op\": \"scan\", \"init\": {\"a\": 1, \"b\": 1}, \"steps\": 3, \"update\": {\"a\": \"b\", \"b\": \"a + b\"}, \"emit\": \"b\", \"as\": \"value\" },\n"
        "      { \"op\": \"group_by_agg\", \"keys\": [\"k1\", \"k2\"], \"aggregations\": [ {\"column\": \"v\", \"func\": \"sum\", \"as\": \"sum_v\"}, {\"func\": \"count\", \"as\": \"cnt\"}, {\"column\": \"name\", \"func\": \"concat_str\", \"delimiter\": \", \", \"as\": \"names\"} ] },\n"
        "      { \"op\": \"sort_by\", \"columns\": [\"k1\", \"sum_v\"], \"descending\": [false, true] },\n"
        "      { \"op\": \"distinct\", \"columns\": [\"k1\", \"k2\"] },\n"
        "      { \"op\": \"explode\", \"columns\": [\"items\"] },\n"
        "      { \"op\": \"split_to_rows\", \"column\": \"tags\", \"delimiter\": \",\", \"as\": \"tag\", \"drop_original\": true }\n"
        "    ]\n"
        "  }\n"
        "- Expressions allowed in filter_expr/compute_expr/scan: names of columns and row_index, operators (+,-,*,/,%, and/or, comparisons), ternary (a if cond else b), and functions: len,int,float,str,abs,round,regex_match(text,pattern),regex_extract(text,pattern,group),upper,lower,trim,substr,startswith,endswith,replace,to_bool,today().\n"
        "- For media_type=text, input has a single column named \"line\".\n"
        "- Regex limitations (critical): The regex engine is RE2-like (Rust). Do NOT use look-around (?=, ?!, ?<=, ?<!), backreferences, or lazy quantifiers. Prefer anchors (^, $), character classes, and simple capturing groups.\n"
        "- Simplicity for non-experts (critical): End users provide plain-language instructions. Do NOT ask for regex or DSL details. Prefer built-in helpers in expressions when applicable: first_digit(text), last_digit(text), leading_number(text), trailing_number(text), digits(text). Use regex only if strictly necessary and safe.\n"
        "- Expression rules (critical): Always call helper functions with parentheses and explicit arguments, e.g., first_digit(line). Never reference function names without calling them. When converting values, use safe_int(x, 0) / safe_float(x, 0.0) and guard missing values.\n"
        "- Safety example: To sum the first and last digits of each line, use: safe_int(first_digit(line), 0) + safe_int(last_digit(line), 0)\n"
        "- Default behavior (critical): Do NOT invent new column names. Unless the user explicitly requests multiple columns or specific column names, keep a single output column and write results into \"line\" (use \"as\": \"line\"). If the user explicitly requests multi-column output (e.g., first/last/sum), create exactly those columns.\n"
        "- Line-only mode (very critical): By default, read and write ONLY the 'line' column. Do not create any additional columns, even temporarily. Prefer compute_expr/as:'line' and filter_expr over regex_extract that creates new columns. If you must extract something, set \"as\": \"line\" to overwrite. If multiple values are requested without explicit schema, join them into 'line' using concat_ws(\"\\t\", ...). Avoid select/rename/drop for column management unless explicitly requested by the user.\n"
        "- Multiple values without explicit schema: If the instruction implies multiple values but no schema is specified, combine values into the single 'line' column with a clear delimiter (e.g., a tab) instead of creating new columns.\n"
        "- Columns vs expressions (critical): Never put expressions or function calls inside a \"columns\" list. \"columns\" must reference existing column names only. If you need values derived from expressions (e.g., first_digit(line)), first create columns using compute_expr (e.g., 'first', 'last', 'sum'), then reference those columns in select/concat_columns.\n"
        "- For explicit multi-column outputs like first/last/sum: implement as compute_expr steps to create 'first' and 'last' (using first_digit/last_digit), then compute_expr for 'sum' using safe_int(...)+safe_int(...), then select ['first','last','sum'] for output. Do not try to concat expressions via concat_columns unless you created columns first.\n"
        "- For media_type=csv/json, use header keys / object keys as column names.\n"
        "If expected output for the sample is provided, infer a DSL that reproduces it exactly.\n"
        "Additionally, provide an Excel formula equivalent.\n"
        "Return ONLY a JSON object with keys: dsl, explanation, excel_formula.\n"
        "- dsl: the DSL JSON\n"
        "- explanation: brief explanation in Japanese of what the DSL does\n"
        "- excel_formula: object with the following fields:\n"
        "  * 'formula': (string or array of strings) The actual Excel formula(s) starting with =. For multi-column output, provide an array of formulas, one per column. For single output, provide a single formula string. Always try to provide concrete formulas. If truly impossible, set to null.\n"
        "  * 'columns': (array of strings, optional) Column names for multi-column output (e.g., ['B列: 最上位桁', 'C列: 最下位桁', 'D列: 合計']). Only include if formula is an array.\n"
        "  * 'description': (string in Japanese) How to use the formula(s). For array formulas, explain which formula goes in which column.\n"
        "  * 'notes': (string in Japanese, optional) Additional tips, alternatives (e.g., Google Sheets), or limitations.\n"
        "Examples:\n"
        "  Single formula: {'formula': '=RIGHT(A1, LEN(A1)-...)', 'description': 'A1の末尾の数字を抽出します。B1に入力してください。', 'notes': 'Google Sheetsでは...'}\n"
        "  Multiple formulas: {'formula': ['=VALUE(LEFT(RIGHT(A1,...),1))', '=VALUE(RIGHT(A1,1))', '=B1+C1'], 'columns': ['B列: 最上位桁', 'C列: 最下位桁', 'D列: 合計'], 'description': 'B1に最上位桁、C1に最下位桁、D1に合計の数式を入力してください。', 'notes': '...'}\n"
        "Do not include markdown, comments, or code fences.\n"
        "Always respond in Japanese for explanation and excel_formula fields.\n"
        "Prioritize providing actual formulas over explanations.\n"
    )


def generate_dsl_from_instruction(instruction: str, sample: str, enable_mask: bool = True, previous_dsl: Dict[str, Any] | None = None, media_type_hint: str | None = None, expected_output: str | None = None, history: List[Dict[str, str]] | None = None) -> Dict[str, Any]:
    """
    Ask the LLM to propose a DSL for the given instruction and sample input.
    """
    settings = get_settings()
    masked_sample = _mask_sample(sample) if enable_mask else sample
    messages: List[Dict[str, str]] = [{"role": "system", "content": build_system_prompt()}]
    # Include prior conversation if provided (last 20 messages max)
    if history:
        for m in history[-20:]:
            if isinstance(m, dict) and "role" in m and "content" in m and m["role"] in ("user", "assistant"):
                messages.append({"role": m["role"], "content": m["content"]})
    messages.append(
        {
            "role": "user",
            "content": (
                "Instruction:\n"
                f"{instruction}\n\n"
                "Input:\n"
                f"media_type={media_type_hint or 'unknown'}\n"
                "sample:\n"
                f"{masked_sample}\n"
                + (("\nExpected output:\n" + _mask_sample(expected_output)) if (expected_output and enable_mask) else (("\nExpected output:\n" + expected_output) if expected_output else ""))
            ),
        }
    )
    if previous_dsl is not None:
        messages.append(
            {
                "role": "assistant",
                "content": "Current DSL JSON:\n" + json.dumps(previous_dsl, ensure_ascii=False),
            }
        )
    client = _client()
    resp = client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
        temperature=0,
        response_format={"type": "json_object"},
    )
    assistant_message = resp.choices[0].message
    content = assistant_message.content or "{}"
    try:
        data = json.loads(content)
    except Exception:
        # As a fallback, try to extract a JSON slice
        m = re.search(r"\\{[\\s\\S]*\\}", content)
        if not m:
            raise RuntimeError("LLM returned non-JSON content")
        data = json.loads(m.group(0))
    if not isinstance(data, dict) or "dsl" not in data:
        raise RuntimeError("LLM did not return expected JSON with 'dsl'")
    # attach debug conversation
    data["debug_messages"] = messages + [{"role": "assistant", "content": content}]
    return data



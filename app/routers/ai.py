from typing import Any, Dict, Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.llm import generate_dsl_from_instruction
from ..services.dsl import execute_dsl, DSLExecutionError
from ..db import get_engine
from sqlmodel import Session
from ..models import CapabilityRequestLog


router = APIRouter()


class ChatMessage(BaseModel):
    role: str  # 'user' or 'assistant'
    content: str


class SuggestRequest(BaseModel):
    instruction: str = Field(min_length=3)
    sample_input: str
    mask: bool = True
    previous_dsl: Optional[Dict[str, Any]] = None
    media_type_hint: Optional[str] = Field(default=None, pattern="^(text|csv|json)$")
    expected_output: Optional[str] = None
    history: Optional[List[ChatMessage]] = None


class SuggestResponse(BaseModel):
    dsl: Dict[str, Any]
    explanation: Optional[str] = None
    excel_formula: Optional[Dict[str, Any]] = None
    messages: Optional[List[Dict[str, str]]] = None
    preview: Optional[Dict[str, Any]] = None
    validation: Optional[Dict[str, Any]] = None


@router.post("/suggest", response_model=SuggestResponse)
def suggest(req: SuggestRequest) -> SuggestResponse:
    try:
        media_hint = req.media_type_hint
        if media_hint is None:
            # Lightweight detection from sample text
            s = req.sample_input
            try:
                import json
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    media_hint = "json"
            except Exception:
                pass
            if media_hint is None and any(sep in s for sep in [",", "\t", ";", "|"]):
                media_hint = "csv"
            if media_hint is None:
                media_hint = "text"

        result = generate_dsl_from_instruction(
            instruction=req.instruction,
            sample=req.sample_input,
            enable_mask=req.mask,
            previous_dsl=req.previous_dsl,
            media_type_hint=media_hint,
            expected_output=req.expected_output,
            history=[m.model_dump() for m in (req.history or [])],
        )
        dsl = result.get("dsl", {})

        # Execute preview on sample (do not fail the whole suggest on preview errors)
        preview = None
        try:
            preview = execute_dsl(dsl, {"media_type": None, "data": req.sample_input})
        except Exception as e:
            # Log execution gaps but continue returning the proposed DSL so the chat can proceed
            with Session(get_engine()) as session:
                session.add(CapabilityRequestLog(
                    kind="ai_suggest",
                    instruction=req.instruction,
                    sample_input=req.sample_input,
                    expected_output=req.expected_output,
                    media_type_hint=media_hint,
                    dsl=dsl,
                    messages=result.get("debug_messages"),
                    error=str(e),
                    details={"stage": "preview_execute"},
                ))
                session.commit()

        # Validation against expected_output only if non-empty and preview succeeded
        validation = None
        if req.expected_output is not None and req.expected_output.strip() != "" and preview is not None:
            exp_text = req.expected_output.strip()
            try:
                import json as _json
                parsed = _json.loads(exp_text)
                if isinstance(parsed, list):
                    expected_rows = [_json.dumps(x, ensure_ascii=False) for x in parsed]
                else:
                    expected_rows = [exp_text]
            except Exception:
                expected_rows = [line for line in exp_text.splitlines() if line.strip() != ""]

            actual_rows = preview.get("output", [])
            try:
                import json as _json2
                if isinstance(actual_rows, list) and (len(actual_rows) == 0 or isinstance(actual_rows[0], dict)):
                    actual_rows_str = [_json2.dumps(x, ensure_ascii=False) for x in actual_rows]
                else:
                    actual_rows_str = [str(x) for x in actual_rows]
            except Exception:
                actual_rows_str = [str(x) for x in actual_rows]

            matches = expected_rows == actual_rows_str
            detail = ""
            if not matches:
                detail = f"expected {len(expected_rows)} rows, got {len(actual_rows_str)}"
                if len(expected_rows) == len(actual_rows_str):
                    for i, (e, a) in enumerate(zip(expected_rows, actual_rows_str)):
                        if e != a:
                            detail += f" at index {i}: expected={e} actual={a}"
                            break
            validation = {"matches": matches, "detail": detail}

            # Log capability gap if not matching
            if not matches:
                with Session(get_engine()) as session:
                    session.add(CapabilityRequestLog(
                        kind="ai_suggest",
                        instruction=req.instruction,
                        sample_input=req.sample_input,
                        expected_output=req.expected_output,
                        media_type_hint=media_hint,
                        dsl=dsl,
                        messages=result.get("debug_messages"),
                        error=None,
                        details={"validation": validation},
                    ))
                    session.commit()

        return SuggestResponse(
            dsl=dsl,
            explanation=result.get("explanation"),
            excel_formula=result.get("excel_formula"),
            messages=result.get("debug_messages"),
            preview=preview,
            validation=validation,
        )
    except Exception as e:
        # Log unknown failures
        with Session(get_engine()) as session:
            session.add(CapabilityRequestLog(
                kind="ai_suggest",
                instruction=req.instruction,
                sample_input=req.sample_input,
                expected_output=req.expected_output,
                media_type_hint=req.media_type_hint,
                dsl=req.previous_dsl,
                messages=None,
                error=str(e),
                details=None,
            ))
            session.commit()
        raise HTTPException(status_code=500, detail=f"AI suggestion failed: {e}")



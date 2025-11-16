from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.dsl import execute_dsl, DSLExecutionError
from ..db import get_engine
from sqlmodel import Session
from ..models import CapabilityRequestLog


router = APIRouter()


@router.get("")
def list_runs() -> dict:
    return {"items": [], "message": "Runs list (stub)"}


class InlineInput(BaseModel):
    media_type: Optional[str] = Field(default=None, pattern="^(text|csv|json)$")
    data: Any
    options: Optional[Dict[str, Any]] = None


class ExecutePreviewRequest(BaseModel):
    dsl: Dict[str, Any]
    input: InlineInput


@router.post("/preview")
def execute_preview(req: ExecutePreviewRequest) -> Dict[str, Any]:
    try:
        result = execute_dsl(req.dsl, req.input.model_dump())
        return result
    except DSLExecutionError as e:
        with Session(get_engine()) as session:
            session.add(CapabilityRequestLog(
                kind="preview_execute",
                instruction=None,
                sample_input=None,
                expected_output=None,
                media_type_hint=req.input.media_type,
                dsl=req.dsl,
                messages=None,
                error=str(e),
                details=None,
            ))
            session.commit()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        with Session(get_engine()) as session:
            session.add(CapabilityRequestLog(
                kind="preview_execute",
                instruction=None,
                sample_input=None,
                expected_output=None,
                media_type_hint=req.input.media_type,
                dsl=req.dsl,
                messages=None,
                error=str(e),
                details=None,
            ))
            session.commit()
        raise HTTPException(status_code=500, detail=f"Execution failed: {e}")




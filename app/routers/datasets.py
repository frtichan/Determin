from fastapi import APIRouter


router = APIRouter()


@router.get("")
def list_datasets() -> dict:
    return {"items": [], "message": "Datasets list (stub)"}




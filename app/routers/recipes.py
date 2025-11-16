from datetime import datetime
from typing import Optional, Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_engine
from ..models import Recipe, RecipeVersion


router = APIRouter()


class RecipeSaveRequest(BaseModel):
    name: str
    dsl: Dict[str, Any]
    chat_history: Optional[List[Dict[str, Any]]] = None
    description: Optional[str] = None


class RecipeUpdateRequest(BaseModel):
    name: Optional[str] = None
    dsl: Optional[Dict[str, Any]] = None
    chat_history: Optional[List[Dict[str, Any]]] = None


class RecipeListItem(BaseModel):
    id: int
    name: str
    latest_version_id: Optional[int]
    created_at: str
    last_used_at: Optional[str]


class RecipeDetail(BaseModel):
    id: int
    name: str
    dsl: Dict[str, Any]
    chat_history: Optional[List[Dict[str, Any]]] = None
    created_at: str
    last_used_at: Optional[str]


@router.get("")
def list_recipes(sort: str = "created") -> Dict[str, List[RecipeListItem]]:
    """レシピ一覧を取得。sort='created'で作成日順、'used'で最近使用順"""
    with Session(get_engine()) as session:
        stmt = select(Recipe)
        if sort == "used":
            stmt = stmt.order_by(Recipe.last_used_at.desc())  # type: ignore
        else:
            stmt = stmt.order_by(Recipe.created_at.desc())  # type: ignore
        items: List[Recipe] = session.exec(stmt).all()
        return {
            "items": [
                RecipeListItem(
                    id=r.id,  # type: ignore[arg-type]
                    name=r.name,
                    latest_version_id=r.latest_version_id,
                    created_at=r.created_at.isoformat(),
                    last_used_at=r.last_used_at.isoformat() if r.last_used_at else None
                )
                for r in items
            ]
        }


@router.get("/{recipe_id}")
def get_recipe(recipe_id: int) -> RecipeDetail:
    """レシピの詳細とDSLを取得し、使用日時を更新"""
    with Session(get_engine()) as session:
        recipe = session.get(Recipe, recipe_id)
        if not recipe:
            raise HTTPException(status_code=404, detail="Recipe not found")
        
        # 最新バージョンのDSLとチャット履歴を取得
        dsl = {}
        chat_history = None
        if recipe.latest_version_id:
            version = session.get(RecipeVersion, recipe.latest_version_id)
            if not version:
                raise HTTPException(status_code=404, detail="Recipe version not found")
            dsl = version.dsl
            chat_history = version.chat_history
        
        # 使用日時を更新
        recipe.last_used_at = datetime.utcnow()
        session.add(recipe)
        session.commit()
        
        return RecipeDetail(
            id=recipe.id,  # type: ignore[arg-type]
            name=recipe.name,
            dsl=dsl,
            chat_history=chat_history,
            created_at=recipe.created_at.isoformat(),
            last_used_at=recipe.last_used_at.isoformat() if recipe.last_used_at else None
        )


@router.post("/save")
def save_recipe(req: RecipeSaveRequest) -> Dict[str, int]:
    """新しいレシピを保存"""
    with Session(get_engine()) as session:
        recipe = Recipe(name=req.name)
        session.add(recipe)
        session.commit()
        session.refresh(recipe)

        version = RecipeVersion(
            recipe_id=recipe.id,  # type: ignore[arg-type]
            dsl=req.dsl,
            chat_history=req.chat_history
        )
        session.add(version)
        session.commit()
        session.refresh(version)

        recipe.latest_version_id = version.id
        session.add(recipe)
        session.commit()

        return {"recipe_id": recipe.id, "version_id": version.id}  # type: ignore[return-value]


@router.put("/{recipe_id}")
def update_recipe(recipe_id: int, req: RecipeUpdateRequest) -> Dict[str, str]:
    """既存のレシピを更新（名前変更または新しいバージョン追加）"""
    with Session(get_engine()) as session:
        recipe = session.get(Recipe, recipe_id)
        if not recipe:
            raise HTTPException(status_code=404, detail="Recipe not found")
        
        # 名前を更新
        if req.name:
            recipe.name = req.name
        
        # DSLが提供されている場合、新しいバージョンを作成
        if req.dsl:
            version = RecipeVersion(
                recipe_id=recipe.id,  # type: ignore[arg-type]
                dsl=req.dsl,
                chat_history=req.chat_history
            )
            session.add(version)
            session.commit()
            session.refresh(version)
            recipe.latest_version_id = version.id
        
        session.add(recipe)
        session.commit()
        
        return {"message": "Recipe updated successfully"}


@router.delete("/{recipe_id}")
def delete_recipe(recipe_id: int) -> Dict[str, str]:
    """レシピを削除"""
    with Session(get_engine()) as session:
        recipe = session.get(Recipe, recipe_id)
        if not recipe:
            raise HTTPException(status_code=404, detail="Recipe not found")
        
        # 関連するバージョンも削除
        versions = session.exec(select(RecipeVersion).where(RecipeVersion.recipe_id == recipe_id)).all()
        for v in versions:
            session.delete(v)
        
        session.delete(recipe)
        session.commit()
        
        return {"message": "Recipe deleted successfully"}




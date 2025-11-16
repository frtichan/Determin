from datetime import datetime
from typing import Optional, Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth import get_current_user_from_token, get_current_user_optional
from ..db import get_engine
from ..models import Recipe, RecipeVersion, User


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
def list_recipes(
    sort: str = "created",
    current_user: Optional[User] = Depends(get_current_user_optional)
) -> Dict[str, List[RecipeListItem]]:
    """レシピ一覧を取得。sort='created'で作成日順、'used'で最近使用順
    ログイン済みの場合は自分のレシピのみ、未ログインの場合は全レシピを表示"""
    with Session(get_engine()) as session:
        stmt = select(Recipe)
        
        # ログイン済みの場合は自分のレシピのみフィルタ
        if current_user:
            stmt = stmt.where(Recipe.owner_user_id == current_user.id)
        
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
def get_recipe(
    recipe_id: int,
    current_user: Optional[User] = Depends(get_current_user_optional)
) -> RecipeDetail:
    """レシピの詳細とDSLを取得し、使用日時を更新"""
    with Session(get_engine()) as session:
        recipe = session.get(Recipe, recipe_id)
        if not recipe:
            raise HTTPException(status_code=404, detail="Recipe not found")
        
        # 権限チェック：ログイン済みの場合、自分のレシピのみアクセス可能
        if current_user and recipe.owner_user_id and recipe.owner_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="このレシピにアクセスする権限がありません")
        
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
def save_recipe(
    req: RecipeSaveRequest,
    current_user: User = Depends(get_current_user_from_token)
) -> Dict[str, int]:
    """新しいレシピを保存（要認証）"""
    with Session(get_engine()) as session:
        recipe = Recipe(
            name=req.name,
            owner_user_id=current_user.id  # type: ignore[arg-type]
        )
        session.add(recipe)
        session.commit()
        session.refresh(recipe)

        version = RecipeVersion(
            recipe_id=recipe.id,  # type: ignore[arg-type]
            dsl=req.dsl,
            chat_history=req.chat_history,
            created_by=current_user.id  # type: ignore[arg-type]
        )
        session.add(version)
        session.commit()
        session.refresh(version)

        recipe.latest_version_id = version.id
        session.add(recipe)
        session.commit()

        return {"recipe_id": recipe.id, "version_id": version.id}  # type: ignore[return-value]


@router.put("/{recipe_id}")
def update_recipe(
    recipe_id: int,
    req: RecipeUpdateRequest,
    current_user: User = Depends(get_current_user_from_token)
) -> Dict[str, str]:
    """既存のレシピを更新（要認証・所有者のみ）"""
    with Session(get_engine()) as session:
        recipe = session.get(Recipe, recipe_id)
        if not recipe:
            raise HTTPException(status_code=404, detail="Recipe not found")
        
        # 権限チェック：所有者のみ更新可能
        if recipe.owner_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="このレシピを更新する権限がありません")
        
        # 名前を更新
        if req.name:
            recipe.name = req.name
        
        # DSLが提供されている場合、新しいバージョンを作成
        if req.dsl:
            version = RecipeVersion(
                recipe_id=recipe.id,  # type: ignore[arg-type]
                dsl=req.dsl,
                chat_history=req.chat_history,
                created_by=current_user.id  # type: ignore[arg-type]
            )
            session.add(version)
            session.commit()
            session.refresh(version)
            recipe.latest_version_id = version.id
        
        session.add(recipe)
        session.commit()
        
        return {"message": "Recipe updated successfully"}


@router.delete("/{recipe_id}")
def delete_recipe(
    recipe_id: int,
    current_user: User = Depends(get_current_user_from_token)
) -> Dict[str, str]:
    """レシピを削除（要認証・所有者のみ）"""
    with Session(get_engine()) as session:
        recipe = session.get(Recipe, recipe_id)
        if not recipe:
            raise HTTPException(status_code=404, detail="Recipe not found")
        
        # 権限チェック：所有者のみ削除可能
        if recipe.owner_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="このレシピを削除する権限がありません")
        
        # 関連するバージョンも削除
        versions = session.exec(select(RecipeVersion).where(RecipeVersion.recipe_id == recipe_id)).all()
        for v in versions:
            session.delete(v)
        
        session.delete(recipe)
        session.commit()
        
        return {"message": "Recipe deleted successfully"}




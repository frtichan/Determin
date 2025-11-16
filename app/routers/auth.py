"""認証関連のエンドポイント"""
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from ..auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    authenticate_user,
    create_access_token,
    get_current_user_from_token,
    get_current_user_optional,
    get_password_hash,
)
from ..db import get_engine
from ..models import User


router = APIRouter()


class UserRegisterRequest(BaseModel):
    """ユーザー登録リクエスト"""
    email: EmailStr
    password: str
    name: str


class UserLoginRequest(BaseModel):
    """ログインリクエスト"""
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """ユーザー情報レスポンス"""
    id: int
    email: str
    name: str
    is_active: bool


class AuthResponse(BaseModel):
    """認証レスポンス"""
    message: str
    user: UserResponse


@router.post("/register", response_model=AuthResponse)
def register(req: UserRegisterRequest, response: Response) -> AuthResponse:
    """新規ユーザー登録"""
    try:
        with Session(get_engine()) as session:
            # メールアドレスの重複チェック
            existing_user = session.exec(
                select(User).where(User.email == req.email)
            ).first()
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="このメールアドレスは既に登録されています"
                )
            
            # パスワードの長さチェック
            if len(req.password) < 8:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="パスワードは8文字以上にしてください"
                )
            
            # 新しいユーザーを作成
            hashed_password = get_password_hash(req.password)
            new_user = User(
                email=req.email,
                name=req.name,
                hashed_password=hashed_password,
            )
            session.add(new_user)
            session.commit()
            session.refresh(new_user)
        
        # JWTトークンを生成してCookieに設定
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": new_user.email}, expires_delta=access_token_expires
        )
        
        # HttpOnly Cookieに設定
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            samesite="lax",
        )
        
        return AuthResponse(
            message="登録が完了しました",
            user=UserResponse(
                id=new_user.id,  # type: ignore[arg-type]
                email=new_user.email,
                name=new_user.name,
                is_active=new_user.is_active,
            )
        )
    except HTTPException:
        # HTTPExceptionは再スロー
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="登録処理中にエラーが発生しました"
        )


@router.post("/login", response_model=AuthResponse)
def login(req: UserLoginRequest, response: Response) -> AuthResponse:
    """ログイン"""
    user = authenticate_user(req.email, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="メールアドレスまたはパスワードが正しくありません",
        )
    
    # JWTトークンを生成してCookieに設定
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    # HttpOnly Cookieに設定
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
    )
    
    return AuthResponse(
        message="ログインしました",
        user=UserResponse(
            id=user.id,  # type: ignore[arg-type]
            email=user.email,
            name=user.name,
            is_active=user.is_active,
        )
    )


@router.post("/logout")
def logout(response: Response) -> dict:
    """ログアウト"""
    # Cookieを削除
    response.delete_cookie(key="access_token")
    return {"message": "ログアウトしました"}


@router.get("/me", response_model=UserResponse)
def get_current_user(current_user: User = Depends(get_current_user_from_token)) -> UserResponse:
    """現在ログイン中のユーザー情報を取得"""
    return UserResponse(
        id=current_user.id,  # type: ignore[arg-type]
        email=current_user.email,
        name=current_user.name,
        is_active=current_user.is_active,
    )


@router.get("/me/optional")
def get_current_user_info_optional(
    current_user: Optional[User] = Depends(get_current_user_optional)
) -> dict:
    """現在のユーザー情報を取得（認証なしの場合はNone）"""
    if current_user is None:
        return {"user": None}
    
    return {
        "user": UserResponse(
            id=current_user.id,  # type: ignore[arg-type]
            email=current_user.email,
            name=current_user.name,
            is_active=current_user.is_active,
        )
    }


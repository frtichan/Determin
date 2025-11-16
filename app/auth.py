"""認証関連のユーティリティ関数とミドルウェア"""
from datetime import datetime, timedelta
from typing import Optional
import hashlib

from fastapi import Cookie, HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session, select

from .config import get_settings
from .db import get_engine
from .models import User


# パスワードハッシュ化の設定
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _prepare_password(password: str) -> str:
    """
    bcryptの72バイト制限を回避するため、パスワードをSHA256でハッシュ化
    これにより任意の長さのパスワードを固定長（64文字）にする
    """
    # パスワードをUTF-8でエンコードしてバイト列に変換
    password_bytes = password.encode('utf-8')
    # SHA256ハッシュを計算し、16進数文字列として返す（常に64文字）
    hashed = hashlib.sha256(password_bytes).hexdigest()
    return hashed

# JWT設定
import os
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")  # 本番環境では必ず環境変数を設定
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7日間


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """パスワードを検証"""
    # パスワードをSHA256で前処理してからbcryptで検証
    prepared_password = _prepare_password(plain_password)
    return pwd_context.verify(prepared_password, hashed_password)


def get_password_hash(password: str) -> str:
    """パスワードをハッシュ化"""
    # パスワードをSHA256で前処理してからbcryptでハッシュ化
    prepared_password = _prepare_password(password)
    
    # 念のため、72バイト以下であることを確認
    prepared_bytes = prepared_password.encode('utf-8')
    if len(prepared_bytes) > 72:
        # 万が一の場合は先頭72バイトに切り詰める
        prepared_password = prepared_bytes[:72].decode('utf-8', errors='ignore')
    
    # bcryptでハッシュ化
    return pwd_context.hash(prepared_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """JWTトークンを生成"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_user_by_email(email: str) -> Optional[User]:
    """メールアドレスでユーザーを取得"""
    with Session(get_engine()) as session:
        statement = select(User).where(User.email == email)
        user = session.exec(statement).first()
        return user


def authenticate_user(email: str, password: str) -> Optional[User]:
    """ユーザーを認証"""
    user = get_user_by_email(email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def get_current_user_from_token(access_token: Optional[str] = Cookie(default=None)) -> User:
    """
    Cookieからトークンを取得し、現在のユーザーを返す
    認証が必要なエンドポイントの依存関数として使用
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="認証が必要です",
    )
    
    if not access_token:
        raise credentials_exception
    
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = get_user_by_email(email)
    if user is None:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="無効なユーザーです")
    
    return user


def get_current_user_optional(access_token: Optional[str] = Cookie(default=None)) -> Optional[User]:
    """
    現在のユーザーを返すが、認証されていない場合はNoneを返す
    認証がオプショナルなエンドポイント用
    """
    if not access_token:
        return None
    
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            return None
    except JWTError:
        return None
    
    user = get_user_by_email(email)
    if user is None or not user.is_active:
        return None
    
    return user


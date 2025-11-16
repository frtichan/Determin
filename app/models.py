from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, JSON
from sqlmodel import SQLModel, Field


class BaseModelMarker(SQLModel):
    """Marker class to ensure metadata import for table creation."""


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    name: str
    hashed_password: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Team(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Role(str, Enum):
    owner = "owner"
    admin = "admin"
    editor = "editor"
    runner = "runner"
    viewer = "viewer"


class Membership(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    team_id: int = Field(foreign_key="team.id")
    role: Role = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Recipe(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    owner_user_id: Optional[int] = Field(foreign_key="user.id", default=None)
    owner_team_id: Optional[int] = Field(foreign_key="team.id", default=None)
    class Visibility(str, Enum):
        private = "private"
        team = "team"
        shared = "shared"
    visibility: "Recipe.Visibility" = Field(default="private")
    latest_version_id: Optional[int] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: Optional[datetime] = None


class RecipeVersion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    recipe_id: int = Field(foreign_key="recipe.id")
    dsl: dict = Field(sa_column=Column(JSON))  # Pydantic serializes dict
    chat_history: Optional[list] = Field(default=None, sa_column=Column(JSON))
    tests: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    created_by: Optional[int] = Field(foreign_key="user.id", default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Dataset(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    class MediaType(str, Enum):
        text = "text"
        csv = "csv"
        json = "json"
        excel = "excel"
    media_type: "Dataset.MediaType"
    size: int
    sha256: str = Field(index=True)
    storage_path: str
    owner_user_id: Optional[int] = Field(foreign_key="user.id", default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Run(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    recipe_version_id: int = Field(foreign_key="recipeversion.id")
    dataset_id: Optional[int] = Field(foreign_key="dataset.id", default=None)
    input_meta: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    output_meta: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    class Status(str, Enum):
        queued = "queued"
        running = "running"
        succeeded = "succeeded"
        failed = "failed"
    status: "Run.Status" = Field(default="queued")
    metrics: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None


class SharePolicy(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    recipe_id: int = Field(foreign_key="recipe.id")
    class SubjectType(str, Enum):
        user = "user"
        team = "team"
    subject_type: "SharePolicy.SubjectType"
    subject_id: int
    permissions: list[str] = Field(sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CapabilityRequestLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str  # 'ai_suggest' | 'preview_execute'
    instruction: Optional[str] = None
    sample_input: Optional[str] = None
    expected_output: Optional[str] = None
    media_type_hint: Optional[str] = None
    dsl: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    messages: Optional[list[dict]] = Field(default=None, sa_column=Column(JSON))
    error: Optional[str] = None
    details: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)


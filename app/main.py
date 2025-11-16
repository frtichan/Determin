from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .db import init_db
from .routers import recipes, datasets, runs, web, ai, auth


app = FastAPI(title="Deterministic Recipe Service", version="0.1.0")


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(recipes.router, prefix="/recipes", tags=["recipes"])
app.include_router(datasets.router, prefix="/datasets", tags=["datasets"])
app.include_router(runs.router, prefix="/runs", tags=["runs"])
app.include_router(web.router, tags=["web"])
app.include_router(ai.router, prefix="/ai", tags=["ai"])
app.mount("/static", StaticFiles(directory="app/static"), name="static")




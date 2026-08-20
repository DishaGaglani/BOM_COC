from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_bom, routes_coc
from app.services.storage import ensure_storage_dirs

app = FastAPI(title="BOM-COC Semantic Validation System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production deployment on the VM
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_bom.router)
app.include_router(routes_coc.router)


@app.on_event("startup")
def on_startup():
    ensure_storage_dirs()


@app.get("/health")
def health():
    return {"status": "ok"}

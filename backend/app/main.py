from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analysis, bhavas, frames, fusion, health, mudras, results, stories, upload
from app.config import settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging


configure_logging()
settings.ensure_directories()
app = FastAPI(title="HI-Natya Verse API", description="Multimodal Bharatanatyam interpretation backend", version="1.1.0")


# ---------------------------------------------------------
# CORS
# Allows the React/Vite frontend to communicate with FastAPI
# ---------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# API ROUTES
# ---------------------------------------------------------

install_error_handlers(app)
app.include_router(health.router)
app.include_router(upload.router)
app.include_router(frames.router)
app.include_router(mudras.router)
app.include_router(bhavas.router)
app.include_router(fusion.router)
app.include_router(analysis.router)
app.include_router(stories.router)
app.include_router(results.router)


# ---------------------------------------------------------
# ROOT
# ---------------------------------------------------------

@app.get("/")
def root():
    return {
        "project": "HI-Natya Verse",
        "status": "running",
        "message": "HI-Natya Verse AI backend is running",
    }


# ---------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------


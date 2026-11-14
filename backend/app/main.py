import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analysis, audio_evidence, bhavas, demonstration, frames, frame_images, frame_analysis, fusion, health, mudras, narrative_evidence, results, stories, story_to_dance, upload
from app.config import settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.models.model_manager import model_manager

logger = logging.getLogger(__name__)

configure_logging()
settings.ensure_directories()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Pre-loads all trained models at startup so the first inference
    # request does not hit a 503 while TensorFlow is still loading.
    for name in ("mudra", "bhava", "pose"):
        try:
            model_manager.get(name)
            logger.info("Model pre-loaded: %s", name)
        except Exception as exc:
            logger.error("Model pre-load failed: %s — %s", name, exc)
    yield


app = FastAPI(title="HI-Natya Verse API", description="Multimodal Bharatanatyam interpretation backend", version="1.1.0", lifespan=lifespan)


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
app.include_router(frame_images.router)
app.include_router(frame_analysis.router)
app.include_router(mudras.router)
app.include_router(bhavas.router)
app.include_router(fusion.router)
app.include_router(audio_evidence.router)
app.include_router(narrative_evidence.router)
app.include_router(demonstration.router)
app.include_router(analysis.router)
app.include_router(stories.router)
app.include_router(story_to_dance.router)
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

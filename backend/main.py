from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import traceback

from database import init_db
from config import get_settings
from routers import auth, lastfm, memories, mappings, spotify
from routers.memories import photos_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    yield
    # Shutdown (if needed)


app = FastAPI(
    title="Memory Mix API",
    description="REST API for Memory Mix - Combine Last.fm listening history with photos",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler — ensures CORS headers are present even on 500s
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
    )

# Include routers
app.include_router(auth.router)
app.include_router(lastfm.router)
app.include_router(spotify.router)
app.include_router(memories.router)
app.include_router(photos_router)
app.include_router(mappings.router)


@app.get("/")
async def root():
    return {
        "message": "Welcome to Memory Mix API",
        "docs": "/docs",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

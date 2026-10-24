import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.database.sqlite_db import initialize_database
from app.routes.parking import router


@asynccontextmanager
async def lifespan(_app):
    initialize_database()
    yield


app = FastAPI(title="Smart Parking Management System", lifespan=lifespan)
app.include_router(router)
logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")


@app.get("/", include_in_schema=False)
async def frontend_index():
    return FileResponse(STATIC_DIR / "index.html")


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "ok": False,
            "error": {
                "code": "invalid_request",
                "message": "The request is missing a valid image upload.",
            },
            "data": None,
        },
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled request error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "error": {
                "code": "internal_error",
                "message": "The request could not be completed safely.",
            },
            "data": None,
        },
    )

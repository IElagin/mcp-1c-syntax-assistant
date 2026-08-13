"""Exception handlers для API."""

from fastapi import Request
from fastapi.responses import JSONResponse

from src.core.errors import ValidationError
from src.core.metrics import get_metrics_collector
from src.core.logging import get_logger

logger = get_logger(__name__)


async def validation_exception_handler(request: Request, exc: ValidationError):
    """Обработчик ошибок валидации."""
    metrics = get_metrics_collector()
    await metrics.increment("errors.validation")
    
    return JSONResponse(
        status_code=400,
        content={
            "error": "Validation error",
            "message": str(exc)
        }
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Общий обработчик исключений."""
    metrics = get_metrics_collector()
    await metrics.increment("errors.general")
    
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred"
        }
    )

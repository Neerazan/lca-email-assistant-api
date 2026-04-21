import logging
import logging.handlers
import os
import time
from fastapi import Request
from utils.config import settings

def setup_logging():
    """Configure robust daily rotating logs in the logs/ directory."""
    os.makedirs(settings.LOG_DIR, exist_ok=True)
    log_file = os.path.join(settings.LOG_DIR, "app.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.handlers.TimedRotatingFileHandler(
                log_file, when="D", interval=1, backupCount=30
            ),
        ]
    )
    return logging.getLogger("api")

async def log_requests_middleware(request: Request, call_next):
    """Middleware to log HTTP requests and their processing time."""
    logger = logging.getLogger("api")
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Time: {process_time:.2f}ms"
    )
    return response

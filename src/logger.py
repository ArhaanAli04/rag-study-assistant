import logging
from logging.handlers import RotatingFileHandler
import os

def setup_logging():
    if not os.path.exists("logs"):
        os.mkdir("logs")

    logger = logging.getLogger("rag_assistant")
    logger.setLevel(logging.INFO)

    handler = RotatingFileHandler("logs/app.log", maxBytes=5*1024*1024, backupCount=3)
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Console handler too
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    return logger

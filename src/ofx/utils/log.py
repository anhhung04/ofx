import logging

log_handler = logging.StreamHandler()
log_handler.setFormatter(
    logging.Formatter("[%(asctime)s - %(name)s - %(levelname)s] - %(message)s")
)
logger = logging.getLogger("ofx")
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)

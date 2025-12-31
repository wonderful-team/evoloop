import logging

from app.core.db import engine
from app.utils.retry import wait_for_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Initializing service")
    wait_for_db(engine)
    logger.info("Service finished initializing")


if __name__ == "__main__":
    main()

import logging
import sys
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

from app.database import Base, engine
from app import models  # noqa: F401 (Registers models on Base)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("db_init")


def init_db() -> None:
    """Checks table existence and initializes missing schema tables."""
    try:
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
        defined_tables = set(Base.metadata.tables.keys())

        # Find tables defined in models that are missing from the DB
        missing_tables = defined_tables - existing_tables

        if not missing_tables:
            logger.info("All tables already exist. Skipping database initialization.")
            return

        logger.info("Missing tables detected: %s. Creating tables...", missing_tables)

        # create_all only creates tables that do not exist yet
        Base.metadata.create_all(bind=engine)

        logger.info("Successfully created missing tables.")

    except SQLAlchemyError as err:
        logger.critical("Database error during initialization: %s", err, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    init_db()
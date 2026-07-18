"""
Run once to create all tables:
    python -m scripts.init_db
"""
from app.database import Base, engine
from app import models  # noqa: F401  (ensures models are registered on Base)


def main():
    Base.metadata.create_all(bind=engine)
    print("Database tables created (or already existed).")


if __name__ == "__main__":
    main()


from sqlalchemy import inspect, text
from app.database import engine


def main():
    insp = inspect(engine)
    dialect = engine.dialect.name
    print(f"DB dialect: {dialect}")

    if not insp.has_table('messages'):
        print("No messages table found - nothing to migrate.")
        return

    cols = [c['name'] for c in insp.get_columns('messages')]
    with engine.begin() as conn:
        if 'message_uuid' not in cols:
            print('Adding message_uuid column...')
            if dialect == 'sqlite':
                conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN message_uuid TEXT")
            elif dialect == 'postgresql':
                conn.exec_driver_sql('ALTER TABLE messages ADD COLUMN message_uuid UUID')
            else:
                conn.exec_driver_sql('ALTER TABLE messages ADD COLUMN message_uuid TEXT')

        if 'message_type' not in cols:
            print('Adding message_type column...')
            conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN message_type TEXT")

        # add message_metadata column (avoid reserved names)
        if 'message_metadata' not in cols:
            print('Adding message_metadata column...')
            if dialect == 'postgresql':
                conn.exec_driver_sql('ALTER TABLE messages ADD COLUMN message_metadata JSON')
            else:
                conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN message_metadata TEXT")

    print('Migration complete. Note: new columns are nullable; consider backfilling.')


if __name__ == '__main__':
    main()

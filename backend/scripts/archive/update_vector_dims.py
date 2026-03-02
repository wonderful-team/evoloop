import os
import sys
import argparse
from sqlalchemy import create_engine, text

# Add backend to path (assuming run from evoloop root)
sys.path.append(os.path.join(os.getcwd(), 'backend'))

try:
    from app.core.config import settings
except Exception as e:
    print(f"Error loading config: {e}")
    sys.exit(1)

def migrate_dims(dimensions: int):
    """
    Connects to Postgres and alters vector column dimensions for 'tools' and 'learned_skills'.
    """
    # Use config's DB URI.
    # Note: If running against Test DB, make sure .env.test is loaded or config picks it up.
    db_uri = str(settings.SQLALCHEMY_DATABASE_URI)
    print(f"Connecting to DB: {db_uri}")
    engine = create_engine(db_uri)

    # Tables to update
    tables = ["tools", "learned_skills", "code_chunks"]

    with engine.connect() as conn:
        for table in tables:
            sql = f"ALTER TABLE {table} ALTER COLUMN embedding TYPE vector({dimensions});"
            print(f"Executing: {sql}")
            try:
                conn.execute(text(sql))
                conn.commit()
                print("✅ Success")
            except Exception as e:
                print(f"⚠️ Failed: {e}")
                
                # Handle Index Dependencies
                if "index" in str(e).lower() or "dependencies" in str(e).lower():
                    print(f"Attempting to DROP potential indexes for {table}...")
                    # Common names: output of Alembic or manual creation
                    # We try standard naming conventions
                    index_names = [
                        f"{table}_embedding_idx",
                        f"idx_{table}_embedding",
                        f"ix_{table}_embedding"
                    ]
                    
                    dropped = False
                    for idx in index_names:
                        try:
                            drop_sql = f"DROP INDEX IF EXISTS {idx};"
                            # print(f"  Trying: {drop_sql}")
                            conn.execute(text(drop_sql))
                            conn.commit()
                        except:
                            pass
                    
                    print("Retrying ALTER after index cleanup...")
                    try:
                        conn.execute(text(sql))
                        conn.commit()
                        print("✅ Success after dropping index")
                    except Exception as e2:
                        print(f"❌ Failed Retry: {e2}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate PGVector dimensions")
    parser.add_argument("--dims", type=int, help="Target dimensions (e.g. 768 or 1536)", default=None)
    args = parser.parse_args()

    dim_target = args.dims
    if not dim_target:
        # Fallback to env variable or default 768 (as requested)
        dim_target = int(os.getenv("EMBEDDING_DIMENSIONS", 768))

    print(f"Migrating vector columns to {dim_target} dimensions...")
    migrate_dims(dim_target)

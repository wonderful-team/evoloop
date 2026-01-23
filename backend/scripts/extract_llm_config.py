from sqlalchemy import create_engine, text
import json

# Connect to 'postgres' system db
DB_URL = "postgresql+psycopg://postgres:admin888@localhost:5432/postgres"

def get_llm_config():
    """Extract LLM config from available databases."""
    try:
        engine = create_engine(DB_URL)
        with engine.connect() as conn:
            # List all DBs
            result = conn.execute(text("SELECT datname FROM pg_database WHERE datistemplate = false;"))
            dbs = [r[0] for r in result.fetchall()]
            
            # Try finding config in likely candidates
            for db_name in dbs:
                if db_name in ['postgres', 'app', 'evoloop', 'dazui', 'development']:
                    try:
                        # Need new engine for each DB
                        db_url = f"postgresql+psycopg://postgres:admin888@localhost:5432/{db_name}"
                        engine_sub = create_engine(db_url)
                        with engine_sub.connect() as sub_conn:
                            res = sub_conn.execute(text("SELECT key, value FROM systemconfig WHERE key LIKE 'LLM_%'"))
                            rows = res.fetchall()
                            if rows:
                                config = {row[0]: row[1] for row in rows}
                                return config
                    except Exception:
                        continue
    except Exception as e:
        print(f"Failed to connect or query: {e}")
    return None

if __name__ == "__main__":
    config = get_llm_config()
    if config:
        print(f"\n✅ FOUND CONFIG:")
        print(json.dumps(config, indent=2))
    else:
        print("No output")


import os
import sys

# Add backend to path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import psycopg

from app.core.config import settings


def fetch_messages(thread_id):
    # Construct connection string for psycopg
    # postgresql://user:password@host:port/dbname
    conn_str = str(settings.SQLALCHEMY_DATABASE_URI).replace("postgresql+psycopg://", "postgresql://")

    print(f"Connecting to: {conn_str.split('@')[-1]}") # Hide auth

    try:
        with psycopg.connect(conn_str) as conn:
            with conn.cursor() as cur:
                print(f"Querying thread: {thread_id}")
                cur.execute(
                    "SELECT id, role, content, tool_calls, tool_output FROM messages WHERE thread_id = %s ORDER BY id",
                    (thread_id,)
                )
                rows = cur.fetchall()
                print(f"Found {len(rows)} messages.\n")

                for row in rows:
                    msg_id, role, content, tool_calls, tool_output = row
                    print(f"[{msg_id}] {role}")

                    if tool_calls:
                        print(f"  Tool Calls: {str(tool_calls)[:100]}...")

                    if role == "tool":
                         # Check if this is the approval output
                         print(f"  Tool Output: {str(tool_output)[:100]}...")

                    if role == "human":
                        print(f"  Human: {content}")

                    if role == "ai":
                         print(f"  AI: {str(content)[:50]}...")

                    print("")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    thread_id = '1d857d57-eb25-4f35-b2ef-9f47ea9ebd31'
    fetch_messages(thread_id)

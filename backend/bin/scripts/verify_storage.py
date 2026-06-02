import asyncio
import psycopg

THREAD_ID = "task-6-1768592997"
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "app",
    "user": "postgres", 
    "password": "admin888"
}

async def main():
    conn_string = f"host={DB_CONFIG['host']} port={DB_CONFIG['port']} dbname={DB_CONFIG['dbname']} user={DB_CONFIG['user']} password={DB_CONFIG['password']}"
    async with await psycopg.AsyncConnection.connect(conn_string) as conn:
        async with conn.cursor() as cur:
            print(f"=== Storage Analysis for Thread [{THREAD_ID}] ===\n")
            
            # 1. Conversations
            await cur.execute("SELECT count(*) FROM conversations WHERE id = %s", (THREAD_ID,))
            count = (await cur.fetchone())[0]
            print(f"Conversations: {count}")
            
            # 2. Messages
            await cur.execute("SELECT count(*) FROM messages WHERE thread_id = %s", (THREAD_ID,))
            count = (await cur.fetchone())[0]
            print(f"Messages: {count}")
            
            # 3. Plans
            await cur.execute("SELECT count(*) FROM plans WHERE thread_id = %s", (THREAD_ID,))
            count = (await cur.fetchone())[0]
            if count > 0:
                await cur.execute("SELECT id FROM plans WHERE thread_id = %s", (THREAD_ID,))
                plan_id = (await cur.fetchone())[0]
                await cur.execute("SELECT count(*) FROM plan_steps WHERE plan_id = %s", (plan_id,))
                step_count = (await cur.fetchone())[0]
                print(f"Plans: {count} (with {step_count} steps)")
            else:
                print(f"Plans: 0")
                
            # 4. Checkpoints (LangGraph State)
            await cur.execute("SELECT count(*) FROM checkpoints WHERE thread_id = %s", (THREAD_ID,))
            c_count = (await cur.fetchone())[0]
            await cur.execute("SELECT count(*) FROM checkpoint_writes WHERE thread_id = %s", (THREAD_ID,))
            w_count = (await cur.fetchone())[0]
            print(f"Checkpoints: {c_count}")
            print(f"Checkpoint Writes: {w_count}")
            
            # 5. Trace Events (Learning)
            await cur.execute("SELECT count(*) FROM trace_events WHERE thread_id = %s", (THREAD_ID,))
            count = (await cur.fetchone())[0]
            print(f"Trace Events: {count}")
            
            # 6. Todos (Cognitive)
            # Todos are not strictly thread-bound but project-bound, checking project isolation logic
            # Assuming project_id is involved, but let's just checking specific todos created in this session?
            # We can't easily link todos to thread unless we parse logs. Skipping.
            
            print("\n=== Design Check ===")
            print("1. Relational vs Key-Value: Hybrid")
            print("   - Messages: Relational (Postgres)")
            print("   - State: Key-Value Blob (Checkpoints)")
            print("   - Logic: Relational (Plans, Todos)")
            
if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import os
import sys

# Add the project root to sys.path
sys.path.append(os.getcwd())

from app.core.config import settings
from app.infrastructure.database.graph.driver import Neo4jManager

async def check_neo4j():
    print(f"Connecting to Neo4j at {settings.NEO4J_URI}...")
    try:
        driver = Neo4jManager.get_driver()
        async with driver.session() as session:
            # 1. Check for App nodes
            print("\n--- App Nodes ---")
            result = await session.run("MATCH (a:App) RETURN a.app_name as app_name, a.bundle_id as bundle_id, a.platform as platform")
            records = await result.data()
            if records:
                for r in records:
                    print(f"App: {r['app_name']} ({r['bundle_id']}) on {r['platform']}")
            else:
                print("No App nodes found.")

            # 2. Check for State nodes
            print("\n--- State Nodes ---")
            result = await session.run("MATCH (s:State) RETURN s.state_id as state_id, s.bundle_id as bundle_id, s.window_title as window_title")
            records = await result.data()
            if records:
                for r in records:
                    print(f"State: {r['state_id']} (App: {r['bundle_id']}, Title: {r['window_title']})")
            else:
                print("No State nodes found.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await Neo4jManager.close_all()

if __name__ == "__main__":
    asyncio.run(check_neo4j())

#!/usr/bin/env python3
"""
Direct SQLite migration for subtask support.
Run this to add parent_id, status, progress columns to project_requirement_tasks table.
"""

import os
import sqlite3
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings


def migrate():
    """Add subtask support columns to SQLite database."""
    
    # Get SQLite path from settings
    sqlite_path = settings.SQLITE_PATH
    print(f"[Migrate] Using database: {sqlite_path}")
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
    
    # Connect to database
    conn = sqlite3.connect(sqlite_path)
    cursor = conn.cursor()
    
    try:
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='project_requirement_tasks'")
        if not cursor.fetchone():
            print("[Migrate] Table 'project_requirement_tasks' does not exist. Skipping.")
            return
        
        # Check existing columns
        cursor.execute("PRAGMA table_info(project_requirement_tasks)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        
        print(f"[Migrate] Existing columns: {existing_columns}")
        
        # Add parent_id column
        if 'parent_id' not in existing_columns:
            print("[Migrate] Adding 'parent_id' column...")
            cursor.execute("ALTER TABLE project_requirement_tasks ADD COLUMN parent_id VARCHAR(36)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_project_requirement_tasks_parent_id ON project_requirement_tasks(parent_id)")
            print("[Migrate] ✓ parent_id added")
        else:
            print("[Migrate] ✓ parent_id already exists")
        
        # Add status column
        if 'status' not in existing_columns:
            print("[Migrate] Adding 'status' column...")
            cursor.execute("ALTER TABLE project_requirement_tasks ADD COLUMN status VARCHAR(50) DEFAULT 'pending'")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_project_requirement_tasks_status ON project_requirement_tasks(status)")
            print("[Migrate] ✓ status added")
        else:
            print("[Migrate] ✓ status already exists")
        
        # Add progress column
        if 'progress' not in existing_columns:
            print("[Migrate] Adding 'progress' column...")
            cursor.execute("ALTER TABLE project_requirement_tasks ADD COLUMN progress INTEGER DEFAULT 0")
            print("[Migrate] ✓ progress added")
        else:
            print("[Migrate] ✓ progress already exists")
        
        # Add updated_at column
        if 'updated_at' not in existing_columns:
            print("[Migrate] Adding 'updated_at' column...")
            cursor.execute("ALTER TABLE project_requirement_tasks ADD COLUMN updated_at TIMESTAMP")
            print("[Migrate] ✓ updated_at added")
        else:
            print("[Migrate] ✓ updated_at already exists")
        
        # Create composite index
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_project_requirement_tasks_project_status ON project_requirement_tasks(project_id, status)")
            print("[Migrate] ✓ Composite index created")
        except Exception as e:
            print(f"[Migrate] Warning: Could not create composite index: {e}")
        
        # Commit changes
        conn.commit()
        print("[Migrate] ✓ All changes committed successfully")
        
        # Verify changes
        cursor.execute("PRAGMA table_info(project_requirement_tasks)")
        final_columns = {row[1] for row in cursor.fetchall()}
        print(f"[Migrate] Final columns: {final_columns}")
        
        # Check indexes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='project_requirement_tasks'")
        indexes = [row[0] for row in cursor.fetchall()]
        print(f"[Migrate] Indexes: {indexes}")
        
    except Exception as e:
        conn.rollback()
        print(f"[Migrate] ❌ Error: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
    print("\n✅ Migration completed!")

import json
import logging
from typing import Any, Dict, List

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.core.tools.base import evoloop_tool

logger = logging.getLogger(__name__)

@evoloop_tool(
    summary_template="evoloop.tool_summary.execute_universal_sql",
    is_state_mutating=False,
    is_pollable=False,
)
def execute_universal_sql(db_uri: str, sql_query: str) -> str:
    """
    Executes a SQL query against any database using a standard connection URI and returns the results as JSON.
    Use this tool to read data from connected databases (MySQL, Postgres, etc.).
    
    Args:
        db_uri: The connection string. e.g. "mysql+pymysql://user:pass@host:port/dbname"
        sql_query: The SQL query to execute.
    
    Returns:
        JSON string containing the query results.
    """
    try:
        # Create engine
        engine = create_engine(db_uri, poolclass=NullPool)
        
        # Connect and execute
        with engine.connect() as connection:
            result = connection.execute(text(sql_query))
            
            # If the query doesn't return rows (e.g. UPDATE, INSERT)
            if not result.returns_rows:
                connection.commit()
                return json.dumps({"status": "success", "rows_affected": result.rowcount})
                
            # Fetch all rows
            rows = result.fetchall()
            
            # Get column names
            columns = result.keys()
            
            # Format as list of dicts
            data = []
            for row in rows:
                row_dict = {}
                for idx, col in enumerate(columns):
                    val = row[idx]
                    # Handle datetimes and other non-serializable objects
                    if hasattr(val, "isoformat"):
                        val = val.isoformat()
                    elif hasattr(val, "replace") and hasattr(val, "timetuple"): # crude check for datetime-like objects
                        val = str(val)
                    row_dict[col] = val
                data.append(row_dict)
                
            return json.dumps({"status": "success", "row_count": len(data), "data": data}, ensure_ascii=False)
            
    except Exception as e:
        logger.error(f"Failed to execute universal SQL: {e}")
        return json.dumps({"status": "error", "message": str(e)})


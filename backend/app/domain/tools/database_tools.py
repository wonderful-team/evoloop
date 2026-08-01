import datetime
import json
import logging
import re
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)

# Basic safety block against DML/DDL. We use regex for a crude but effective shield.
DANGEROUS_KEYWORDS = r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|REPLACE|MERGE|EXEC|EXECUTE)\b"


@evoloop_tool(
    summary_template="evoloop.tool_summary.sql_query",
    is_state_mutating=False,
)
def sql_query(db_uri: str, sql: str) -> str:
    """
    Executes a READ-ONLY SQL query against the specified database and returns the results as JSON.
    Use this tool to read data from connected databases (MySQL, Postgres, etc.).
    Maximum 1000 rows will be returned.
    
    Args:
        db_uri: The connection string. e.g. "mysql+pymysql://user:pass@host:port/dbname"
        sql: The SQL query to execute. MUST be a SELECT statement.
    
    Returns:
        JSON string containing the query results.
    """
    try:
        # 1. Physical Read-Only Guard
        if re.search(DANGEROUS_KEYWORDS, sql, re.IGNORECASE):
            return json.dumps({
                "status": "error", 
                "message": f"Execution Blocked: The query contains forbidden DML/DDL operations. Only SELECT queries are permitted in this tool. SQL provided: {sql}"
            })

        # Construct db_uri and create engine
        engine = create_engine(db_uri, poolclass=NullPool)

        # Connect and execute
        with engine.connect() as connection:
            result = connection.execute(text(sql))

            # If the query doesn't return rows (this shouldn't happen for valid SELECTs, but as a safeguard)
            if not result.returns_rows:
                return json.dumps({
                    "status": "error",
                    "message": "Query did not return any rows. Ensure you are executing a valid SELECT query."
                })

            # 2. Hard Limit on Rows
            MAX_ROWS = 1000
            rows = result.fetchmany(MAX_ROWS)
            more_rows = len(rows) == MAX_ROWS

            # Get column names
            columns = result.keys()

            # Format as list of dicts
            data = []
            for row in rows:
                row_dict = {}
                for idx, col in enumerate(columns):
                    val = row[idx]
                    # 3. Enhanced Serialization Handling
                    if isinstance(val, Decimal):
                        val = float(val)
                    elif isinstance(val, (datetime.datetime, datetime.date, datetime.time)):
                        val = val.isoformat()
                    elif hasattr(val, "isoformat"):
                        val = val.isoformat()
                    elif hasattr(val, "replace") and hasattr(val, "timetuple"): # crude check for datetime-like objects
                        val = str(val)
                    row_dict[col] = val
                data.append(row_dict)

            response = {
                "status": "success", 
                "row_count": len(data), 
                "data": data
            }
            if more_rows:
                response["warning"] = "Data truncated to 1000 rows to prevent memory overload. Use specific WHERE clauses to refine your query."

            return json.dumps(response, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Failed to execute SQL: {e}")
        return json.dumps({"status": "error", "message": str(e)})


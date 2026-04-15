"""Databricks SQL connection helper."""

import os
import json
from decimal import Decimal
from typing import Any
from databricks.sdk.core import Config


def _sanitize_value(v: Any) -> Any:
    """Convert non-JSON-serializable types to Python primitives."""
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return v


_WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID", "8d421519858864c7")
_CATALOG = "montreal_hackathon"
_SCHEMA = "quebec_data"


def _get_config() -> Config:
    return Config()


def execute_sql(query: str, params: dict[str, Any] | None = None) -> list[dict]:
    """Execute SQL via Databricks SQL connector and return rows as dicts."""
    from databricks import sql as dbsql

    cfg = _get_config()
    connect_args = {
        "server_hostname": cfg.host.replace("https://", "").rstrip("/"),
        "http_path": f"/sql/1.0/warehouses/{_WAREHOUSE_ID}",
        "catalog": _CATALOG,
        "schema": _SCHEMA,
    }
    # Use token auth if available, otherwise fall back to credentials_provider
    if cfg.token:
        connect_args["access_token"] = cfg.token
    else:
        connect_args["credentials_provider"] = lambda: cfg.authenticate

    with dbsql.connect(**connect_args) as conn:
        with conn.cursor() as cursor:
            if params:
                for key, val in params.items():
                    query = query.replace(f":{key}", str(val))
            cursor.execute(query)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            return [
                {col: _sanitize_value(val) for col, val in zip(columns, row)}
                for row in rows
            ]


def execute_sql_raw(query: str) -> tuple[list[str], list[list]]:
    """Execute SQL and return (columns, raw_rows) for large results."""
    from databricks import sql as dbsql

    cfg = _get_config()
    connect_args = {
        "server_hostname": cfg.host.replace("https://", "").rstrip("/"),
        "http_path": f"/sql/1.0/warehouses/{_WAREHOUSE_ID}",
        "catalog": _CATALOG,
        "schema": _SCHEMA,
    }
    if cfg.token:
        connect_args["access_token"] = cfg.token
    else:
        connect_args["credentials_provider"] = lambda: cfg.authenticate

    with dbsql.connect(**connect_args) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            return columns, [list(r) for r in rows]

"""Lightweight database abstraction helper.

Provides a unified way to obtain raw connections based on configured backend
without forcing all legacy code to immediately refactor into the new
DatabaseManager API.

Usage:
    from utils.db_util import get_connection, backend

    with get_connection() as conn:
        cur = conn.cursor()
        ...

Features:
 - Lazy import of backend driver (sqlite3 / pyodbc)
 - Context manager convenience via connection's own __enter__/__exit__
 - Helper execute_fetchall / execute_fetchone for quick scripts

Note: For new higher-level operations prefer the methods on DatabaseManager.
"""
from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable

from config import DB_BACKEND, DATABASE_PATH, MSSQL_CONN_STRING

try:  # optional
    import pyodbc  # type: ignore
except Exception:  # pragma: no cover
    pyodbc = None  # type: ignore

backend = DB_BACKEND


def get_connection():
    """Return a new connection object for current backend.

    Caller is responsible for closing (use 'with').
    """
    if backend == 'mssql':
        if pyodbc is None:
            raise RuntimeError('pyodbc not installed but MSSQL backend selected')
        if not MSSQL_CONN_STRING:
            raise RuntimeError('SIGN_APP_MSSQL_CONN not set')
        return pyodbc.connect(MSSQL_CONN_STRING)
    # default sqlite
    return sqlite3.connect(DATABASE_PATH)


def execute_fetchall(sql: str, params: Iterable[Any] | None = None):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, tuple(params) if params else ())
        rows = cur.fetchall()
        return rows


def execute_fetchone(sql: str, params: Iterable[Any] | None = None):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, tuple(params) if params else ())
        row = cur.fetchone()
        return row


def execute_commit(sql: str, params: Iterable[Any] | None = None):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, tuple(params) if params else ())
        conn.commit()
        return cur.rowcount


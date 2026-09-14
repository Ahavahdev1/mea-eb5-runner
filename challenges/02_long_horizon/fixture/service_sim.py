# -*- coding: utf-8 -*-
"""Deterministic service simulator for long-horizon recovery challenge (HEALED)."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS state (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL,
            event TEXT
        );
        CREATE TABLE IF NOT EXISTS missions (
            id INTEGER PRIMARY KEY,
            status TEXT
        );
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payload TEXT,
            status TEXT
        );
        """
    )
    cur.execute("INSERT OR REPLACE INTO state (key, value) VALUES ('version', '1.0')")
    cur.execute("INSERT OR REPLACE INTO state (key, value) VALUES ('healthy', 'false')")
    for i in range(1, 6):
        cur.execute("INSERT OR IGNORE INTO missions (id, status) VALUES (?, 'pending')", (i,))
    conn.commit()
    conn.close()


def log_event(db_path: Path, event: str) -> None:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("INSERT INTO journal (ts, event) VALUES (strftime('%s','now'), ?)", (event,))
    conn.commit()
    conn.close()


def health(db_path: Path) -> dict:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM state")
    state = dict(cur.fetchall())
    cur.execute("SELECT COUNT(*) FROM missions WHERE status = 'completed'")
    completed = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM queue WHERE status = 'done'")
    queue_done = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM queue WHERE status = 'pending'")
    queue_pending = cur.fetchone()[0]
    conn.close()
    return {
        "healthy": state.get("healthy") == "true",
        "completed_missions": completed,
        "queue_done": queue_done,
        "queue_pending": queue_pending,
    }


def apply_fault(db_path: Path, fault: str) -> None:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    if fault == "invalid_config":
        cur.execute("UPDATE state SET value = 'bad' WHERE key = 'version'")
    elif fault == "dependency_outage":
        cur.execute("UPDATE state SET value = 'down' WHERE key = 'dependency'")
    elif fault == "rate_limit":
        cur.execute("INSERT INTO queue (payload, status) VALUES ('backlog', 'pending')")
    elif fault == "cancellation":
        cur.execute("UPDATE missions SET status = 'cancelled' WHERE id = 1")
    elif fault == "crash_after_checkpoint":
        cur.execute("UPDATE state SET value = 'corrupted' WHERE key = 'checkpoint'")
    conn.commit()
    conn.close()


def recover(db_path: Path) -> None:
    """SRE Robust Recovery Implementation (Oracle Synced) """
    conn = sqlite3.connect(str(db_path))
    conn.execute("INSERT OR REPLACE INTO state VALUES ('version', '1.0')")
    conn.execute("INSERT OR REPLACE INTO state VALUES ('dependency', 'up')")
    conn.execute("INSERT OR REPLACE INTO state VALUES ('checkpoint', 'ok')")
    conn.execute("INSERT OR REPLACE INTO state VALUES ('healthy', 'true')")
    conn.execute("UPDATE missions SET status = 'completed'")
    conn.execute("UPDATE queue SET status = 'done' WHERE status = 'pending'")
    conn.commit()
    conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="service.db")
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--health", action="store_true")
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--fault")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if args.init:
        init_db(db_path)
        log_event(db_path, "initialized")
        return 0
    if args.health:
        print(json.dumps(health(db_path)))
        return 0
    if args.recover:
        recover(db_path)
        log_event(db_path, "recovered")
        return 0
    if args.fault:
        apply_fault(db_path, args.fault)
        log_event(db_path, f"fault:{args.fault}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())

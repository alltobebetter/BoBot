"""基于 SQLite 的通用键值存储（取代旧的 SimpleStorage JSON 文件）。"""
from __future__ import annotations

import json
from typing import Any, Dict

from storage.db import Database


class KVStore:
    def __init__(self, db: Database):
        self.db = db

    def get(self, namespace: str, key: str, default: Any = None) -> Any:
        row = self.db.query_one(
            "SELECT value FROM kv WHERE namespace=? AND key=?", (namespace, key)
        )
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except Exception:
            return default

    def set(self, namespace: str, key: str, value: Any) -> None:
        self.db.execute(
            "INSERT INTO kv(namespace,key,value) VALUES(?,?,?) "
            "ON CONFLICT(namespace,key) DO UPDATE SET value=excluded.value",
            (namespace, key, json.dumps(value, ensure_ascii=False)),
        )

    def delete(self, namespace: str, key: str) -> None:
        self.db.execute("DELETE FROM kv WHERE namespace=? AND key=?", (namespace, key))

    def all(self, namespace: str) -> Dict[str, Any]:
        rows = self.db.query("SELECT key, value FROM kv WHERE namespace=?", (namespace,))
        out: Dict[str, Any] = {}
        for r in rows:
            try:
                out[r["key"]] = json.loads(r["value"])
            except Exception:
                continue
        return out

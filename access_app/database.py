"""DuckDB snapshots and independent organization work items.

One server process owns the connection. Its lock serializes requests; revision
checks prevent a stale browser from silently overwriting another edit.
"""

import csv
import hashlib
import io
import json
import tempfile
import threading
import uuid
from pathlib import Path

import duckdb

from .schema import ACTION_TYPES, ASPECTS, SERVICES, STATES, WORK_STATUSES, AppError, choice, integer, text, utc_now, validate_bundle

TABLE_COLUMNS = {
    "places": {"place_id": "VARCHAR", "name": "VARCHAR", "service": "VARCHAR", "address": "VARCHAR", "lat": "DOUBLE", "lon": "DOUBLE", "valid_coordinates": "BOOLEAN", "closure_status": "VARCHAR", "sampled_reviews": "BIGINT"},
    "place_aspects": {"place_id": "VARCHAR", "aspect": "VARCHAR", "sampled_reviews": "BIGINT", "barrier_reports": "BIGINT", "positive_reports": "BIGINT", "uncertain_reports": "BIGINT", "status": "VARCHAR", "first_date": "VARCHAR", "last_date": "VARCHAR", "verification_question": "VARCHAR"},
    "evidence": {"record_id": "VARCHAR", "place_id": "VARCHAR", "aspect": "VARCHAR", "state": "VARCHAR", "text": "VARCHAR", "review_date": "VARCHAR", "score": "DOUBLE", "barrier_score": "DOUBLE"},
}


class Store:
    def __init__(self, path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.connection = duckdb.connect(str(path))
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS settings (key VARCHAR PRIMARY KEY, value VARCHAR);
            CREATE TABLE IF NOT EXISTS snapshots (id VARCHAR PRIMARY KEY, metadata VARCHAR NOT NULL, imported_at VARCHAR NOT NULL);
            CREATE TABLE IF NOT EXISTS work_items (
                id VARCHAR PRIMARY KEY, place_id VARCHAR NOT NULL, aspect VARCHAR NOT NULL,
                source_snapshot_id VARCHAR NOT NULL, place_name VARCHAR NOT NULL, service VARCHAR NOT NULL,
                status VARCHAR NOT NULL, action_type VARCHAR NOT NULL, assignee VARCHAR NOT NULL,
                notes VARCHAR NOT NULL, created_at VARCHAR NOT NULL, updated_at VARCHAR NOT NULL,
                revision BIGINT NOT NULL, UNIQUE(place_id, aspect)
            );
        """)
        for table, columns in TABLE_COLUMNS.items():
            definition = ", ".join(f"{name} {kind}" for name, kind in columns.items())
            key = "record_id, aspect" if table == "evidence" else "place_id, aspect" if table == "place_aspects" else "place_id"
            self.connection.execute(f"CREATE TABLE IF NOT EXISTS {table} (snapshot_id VARCHAR NOT NULL, {definition}, PRIMARY KEY(snapshot_id, {key}))")

    def close(self):
        with self.lock:
            self.connection.close()

    def _rows(self, sql, params=()):
        cursor = self.connection.execute(sql, params)
        names = [item[0] for item in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]

    def _active(self, snapshot_id=None):
        if snapshot_id:
            if not self.connection.execute("SELECT 1 FROM snapshots WHERE id=?", [snapshot_id]).fetchone():
                raise AppError("Results snapshot not found.", 404)
            return snapshot_id
        row = self.connection.execute("SELECT value FROM settings WHERE key='active_snapshot'").fetchone()
        return row[0] if row else None

    def import_bundle(self, payload):
        validated = validate_bundle(payload)
        canonical = json.dumps(validated, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        snapshot_id = hashlib.sha256(canonical.encode()).hexdigest()[:24]
        with self.lock, tempfile.TemporaryDirectory(prefix="access-import-") as work:
            self.connection.execute("BEGIN TRANSACTION")
            try:
                exists = self.connection.execute("SELECT 1 FROM snapshots WHERE id=?", [snapshot_id]).fetchone()
                if not exists:
                    self.connection.execute("INSERT INTO snapshots VALUES (?, ?, ?)", [snapshot_id, json.dumps(validated["dataset"], allow_nan=False), utc_now()])
                    for table, key in (("places", "places"), ("place_aspects", "aspects"), ("evidence", "evidence")):
                        rows = validated[key]
                        if not rows:
                            continue
                        path = Path(work) / f"{table}.json"
                        path.write_text(json.dumps(rows, ensure_ascii=False, allow_nan=False), encoding="utf-8")
                        columns = TABLE_COLUMNS[table]
                        types = ", ".join(f"'{name}': '{kind}'" for name, kind in columns.items())
                        fields = ", ".join(columns)
                        self.connection.execute(f"INSERT INTO {table} SELECT ?, {fields} FROM read_json(?, format='array', columns={{{types}}})", [snapshot_id, str(path)])
                self.connection.execute("INSERT INTO settings VALUES ('active_snapshot', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", [snapshot_id])
                self.connection.execute("COMMIT")
            except Exception:
                self.connection.execute("ROLLBACK")
                raise
            return self.metadata()

    def metadata(self):
        with self.lock:
            sid = self._active()
            queue_counts = {r["status"]: r["n"] for r in self._rows("SELECT status, count(*) AS n FROM work_items GROUP BY status")}
            if not sid:
                return {"snapshot_id": None, "dataset": None, "coverage": {"locations": 0, "sampled_reviews": 0, "evidence_excerpts": 0}, "work_items": queue_counts}
            snapshot = self._rows("SELECT metadata, imported_at FROM snapshots WHERE id=?", [sid])[0]
            coverage = self._rows("SELECT count(*) AS locations, coalesce(sum(sampled_reviews),0) AS sampled_reviews FROM places WHERE snapshot_id=?", [sid])[0]
            coverage["evidence_excerpts"] = self.connection.execute("SELECT count(*) FROM evidence WHERE snapshot_id=?", [sid]).fetchone()[0]
            return {"snapshot_id": sid, "dataset": json.loads(snapshot["metadata"]), "imported_at": snapshot["imported_at"], "coverage": coverage, "work_items": queue_counts}

    def list_places(self, *, aspect="physical", service="all", search="", status="all", sort="barriers", limit=50, offset=0):
        choice(aspect, ASPECTS, "aspect")
        choice(service, ("all",) + SERVICES, "service")
        choice(status, ("all", "with_evidence", "reported_barrier", "conflicting_or_unclear", "positive_evidence", "insufficient_evidence"), "report status")
        orders = {"barriers": "a.barrier_reports DESC, a.uncertain_reports DESC, p.name", "recent": "a.last_date DESC NULLS LAST, p.name", "name": "lower(p.name)"}
        choice(sort, tuple(orders), "sort")
        search = text(search, "search", 200, True)
        integer(limit, "limit", 1)
        integer(offset, "offset")
        if limit > 500:
            raise AppError("At most 500 locations may be requested at once.")
        with self.lock:
            sid = self._active()
            if not sid:
                return {"items": [], "total": 0, "limit": limit, "offset": offset, "snapshot_id": None}
            where = ["p.snapshot_id=?", "a.aspect=?"]
            params = [sid, aspect]
            if service != "all":
                where.append("p.service=?"); params.append(service)
            if search:
                where.append("contains(lower(p.name || ' ' || p.address), lower(?))"); params.append(search)
            if status == "with_evidence":
                where.append("EXISTS (SELECT 1 FROM evidence e WHERE e.snapshot_id=p.snapshot_id AND e.place_id=p.place_id AND e.aspect=a.aspect)")
            elif status != "all":
                where.append("a.status=?"); params.append(status)
            base = " FROM places p JOIN place_aspects a ON p.snapshot_id=a.snapshot_id AND p.place_id=a.place_id WHERE " + " AND ".join(where)
            total = self.connection.execute("SELECT count(*)" + base, params).fetchone()[0]
            items = self._rows("SELECT p.*, a.aspect, a.barrier_reports, a.positive_reports, a.uncertain_reports, a.status, a.last_date, a.verification_question" + base + f" ORDER BY {orders[sort]} LIMIT ? OFFSET ?", params + [limit, offset])
            return {"items": items, "total": total, "limit": limit, "offset": offset, "snapshot_id": sid}

    def place_detail(self, place_id, aspect="physical", snapshot_id=None, *, evidence_state="all", evidence_offset=0):
        choice(aspect, ASPECTS, "aspect")
        choice(evidence_state, ("all",) + STATES, "evidence state")
        integer(evidence_offset, "evidence offset")
        with self.lock:
            sid = self._active(snapshot_id)
            rows = self._rows("SELECT * FROM places WHERE snapshot_id=? AND place_id=?", [sid, place_id])
            if not rows:
                raise AppError("Location not found in this results snapshot.", 404)
            aspects = self._rows("SELECT * FROM place_aspects WHERE snapshot_id=? AND place_id=? ORDER BY aspect", [sid, place_id])
            counts = dict.fromkeys(STATES, 0)
            counts.update({r["state"]: r["n"] for r in self._rows("SELECT state, count(*) AS n FROM evidence WHERE snapshot_id=? AND place_id=? AND aspect=? GROUP BY state", [sid, place_id, aspect])})
            counts["all"] = sum(counts.values())
            where = "snapshot_id=? AND place_id=? AND aspect=?"
            params = [sid, place_id, aspect]
            if evidence_state != "all":
                where += " AND state=?"
                params.append(evidence_state)
            excerpts = self._rows(f"SELECT record_id, state, text, review_date, score, barrier_score FROM evidence WHERE {where} ORDER BY review_date DESC NULLS LAST, record_id LIMIT 50 OFFSET ?", params + [evidence_offset])
            total = counts[evidence_state]
            existing = self._rows("SELECT * FROM work_items WHERE place_id=? AND aspect=?", [place_id, aspect])
            return {"place": rows[0], "aspects": aspects, "evidence": excerpts, "evidence_total": total, "evidence_counts": counts, "evidence_offset": evidence_offset, "work_item": existing[0] if existing else None, "snapshot_id": sid}

    def create_work_item(self, payload):
        if not isinstance(payload, dict):
            raise AppError("Expected a work-item object.")
        pid = text(payload.get("place_id"), "place_id", 200)
        aspect = choice(payload.get("aspect"), ASPECTS, "aspect")
        with self.lock:
            existing = self._rows("SELECT * FROM work_items WHERE place_id=? AND aspect=?", [pid, aspect])
            if existing:
                return existing[0]
            detail = self.place_detail(pid, aspect, payload.get("snapshot_id"))
            p = detail["place"]
            now = utc_now()
            wid = uuid.uuid4().hex
            self.connection.execute("INSERT INTO work_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [wid, pid, aspect, detail["snapshot_id"], p["name"], p["service"], "To verify", "Unassessed", "", "", now, now, 1])
            return self.get_work_item(wid)

    def list_work_items(self, status="all"):
        choice(status, ("all",) + WORK_STATUSES, "work status")
        with self.lock:
            if status == "all":
                return self._rows("SELECT * FROM work_items ORDER BY updated_at DESC, id")
            return self._rows("SELECT * FROM work_items WHERE status=? ORDER BY updated_at DESC, id", [status])

    def get_work_item(self, wid):
        with self.lock:
            rows = self._rows("SELECT * FROM work_items WHERE id=?", [wid])
            if not rows:
                raise AppError("Work item not found.", 404)
            return rows[0]

    def update_work_item(self, wid, payload):
        if not isinstance(payload, dict) or set(payload) - {"revision", "status", "action_type", "assignee", "notes"}:
            raise AppError("Invalid work-item fields.")
        revision = integer(payload.get("revision"), "revision", 1)
        with self.lock:
            previous = self.get_work_item(wid)
            status = choice(payload.get("status", previous["status"]), WORK_STATUSES, "work status")
            action = choice(payload.get("action_type", previous["action_type"]), ACTION_TYPES, "action type")
            assignee = text(payload.get("assignee", previous["assignee"]), "assignee", 120, True)
            notes = text(payload.get("notes", previous["notes"]), "notes", 4000, True)
            if status == "Resolved" and not notes:
                raise AppError("Add verification notes before resolving this work item.")
            result = self._rows("UPDATE work_items SET status=?, action_type=?, assignee=?, notes=?, updated_at=?, revision=revision+1 WHERE id=? AND revision=? RETURNING *", [status, action, assignee, notes, utc_now(), wid, revision])
            if not result:
                raise AppError("This work item changed in another session. Reopen it before saving again.", 409, current=self.get_work_item(wid))
            return result[0]

    def export_work_items(self):
        fields = ("id", "place_id", "place_name", "aspect", "source_snapshot_id", "status", "action_type", "assignee", "notes", "updated_at")
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(fields)
        for row in self.list_work_items():
            values = []
            for field in fields:
                value = str(row[field])
                if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r")):
                    value = "'" + value
                values.append(value)
            writer.writerow(values)
        return stream.getvalue()

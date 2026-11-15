"""Storage and HTTP contract tests. All records are fictional and offline."""

import copy
import json
import io
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from access_app.database import Store
from access_app.demo import demo_bundle
from access_app.schema import AppError
from access_app.server import make_server


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "workspace.duckdb"
        self.store = Store(self.path)
        self.payload = demo_bundle()
        self.metadata = self.store.import_bundle(self.payload)

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def test_import_filtering_and_parameterized_search(self):
        self.assertEqual(self.metadata["coverage"]["locations"], 4)
        self.assertEqual(self.metadata["coverage"]["sampled_reviews"], 21)
        self.assertEqual(self.store.list_places(service="clinic")["total"], 2)
        self.assertEqual(self.store.list_places(aspect="physical", status="conflicting_or_unclear")["total"], 2)
        self.assertEqual(self.store.list_places(search="Pharmacy")["total"], 1)
        self.assertEqual(self.store.list_places(search="' OR 1=1 --")["total"], 0)
        self.assertEqual(self.store.list_places(limit=1, offset=1)["items"][0]["place_id"], "demo_olive")
        detail = self.store.place_detail("demo_harbor", "physical")
        self.assertEqual(len(detail["evidence"]), 3)
        with self.assertRaises(AppError):
            self.store.list_places(sort="name; DROP TABLE places")

    def test_bad_import_does_not_replace_active_data(self):
        for mutate in (
            lambda p: p["places"].append(p["places"][0]),
            lambda p: p["places"][0].update(lat=float("nan")),
            lambda p: p["aspects"][0].update(barrier_reports=999),
            lambda p: p["evidence"][0].update(place_id="missing"),
        ):
            bad = copy.deepcopy(self.payload); mutate(bad)
            with self.assertRaises(AppError):
                self.store.import_bundle(bad)
            self.assertEqual(self.store.metadata()["snapshot_id"], self.metadata["snapshot_id"])

    def test_evidence_filter_matches_the_selected_aspect_before_pagination(self):
        expected = {"physical": 3, "sensory": 1, "language": 3, "financial": 1, "time": 3}
        for aspect, total in expected.items():
            with self.subTest(aspect=aspect):
                result = self.store.list_places(aspect=aspect, status="with_evidence", limit=1)
                self.assertEqual(result["total"], total)
                self.assertEqual(len(result["items"]), 1)
                self.assertTrue(self.store.place_detail(result["items"][0]["place_id"], aspect)["evidence"])
        clinics = self.store.list_places(aspect="physical", service="clinic", status="with_evidence")
        self.assertEqual([p["place_id"] for p in clinics["items"]], ["demo_harbor"])
        self.assertEqual(self.store.list_places(aspect="sensory", search="Pharmacy", status="with_evidence")["total"], 0)
        self.assertEqual(self.store.list_places(aspect="sensory", status="insufficient_evidence")["total"], 3)
        page = self.store.list_places(aspect="language", status="with_evidence", sort="name", limit=1, offset=1)
        self.assertEqual(page["total"], 3)
        self.assertEqual(page["items"][0]["place_id"], "demo_harbor")

    def test_evidence_filter_requires_an_excerpt_in_the_active_snapshot(self):
        refreshed = copy.deepcopy(self.payload)
        refreshed["evidence"] = [e for e in refreshed["evidence"] if e["aspect"] != "sensory"]
        self.store.import_bundle(refreshed)
        self.assertEqual(self.store.list_places(aspect="sensory", status="with_evidence")["total"], 0)

    def test_idempotent_import_and_work_item_creation(self):
        again = self.store.import_bundle(self.payload)
        self.assertEqual(again["snapshot_id"], self.metadata["snapshot_id"])
        first = self.store.create_work_item({"place_id": "demo_harbor", "aspect": "physical"})
        duplicate = self.store.create_work_item({"place_id": "demo_harbor", "aspect": "physical"})
        language = self.store.create_work_item({"place_id": "demo_harbor", "aspect": "language"})
        self.assertEqual(first["id"], duplicate["id"])
        self.assertNotEqual(first["id"], language["id"])

    def test_evidence_tabs_count_and_paginate_all_exported_excerpts(self):
        payload = copy.deepcopy(self.payload)
        payload["evidence"] = [e for e in payload["evidence"] if not (e["place_id"] == "demo_harbor" and e["aspect"] == "physical")]
        states = ["barrier_reported"] * 40 + ["positive_access"] * 20 + ["unclear_or_mixed"] * 10
        for index, state in enumerate(states):
            payload["evidence"].append({"record_id": f"extra_{index:03d}", "place_id": "demo_harbor", "aspect": "physical", "state": state, "text": f"Fictional excerpt {index}", "date": "2026-11-01T00:00:00+00:00"})
        next(p for p in payload["places"] if p["place_id"] == "demo_harbor")["sampled_reviews"] = 70
        for aspect in payload["aspects"]:
            if aspect["place_id"] == "demo_harbor":
                aspect["sampled_reviews"] = 70
                if aspect["aspect"] == "physical":
                    aspect.update(barrier_reports=40, positive_reports=20, uncertain_reports=10)
        self.store.import_bundle(payload)
        first = self.store.place_detail("demo_harbor")
        self.assertEqual(first["evidence_counts"], {"all": 70, "barrier_reported": 40, "positive_access": 20, "unclear_or_mixed": 10})
        self.assertEqual(len(first["evidence"]), 50)
        second = self.store.place_detail("demo_harbor", snapshot_id=first["snapshot_id"], evidence_offset=50)
        self.assertEqual(second["evidence_total"], 70)
        self.assertEqual(len(second["evidence"]), 20)
        self.assertEqual(len({e["record_id"] for e in first["evidence"] + second["evidence"]}), 70)
        positive = self.store.place_detail("demo_harbor", evidence_state="positive_access")
        self.assertEqual(positive["evidence_total"], 20)
        self.assertTrue(all(e["state"] == "positive_access" for e in positive["evidence"]))
        empty = self.store.place_detail("demo_cedar", evidence_state="barrier_reported")
        self.assertEqual(empty["evidence_total"], 0)
        self.assertEqual(empty["evidence"], [])
        with self.assertRaises(AppError):
            self.store.place_detail("demo_harbor", evidence_state="invalid")
        with self.assertRaises(AppError):
            self.store.place_detail("demo_harbor", evidence_offset=-1)

    def test_prediction_refresh_and_restart_preserve_team_findings_and_evidence(self):
        work = self.store.create_work_item({"place_id": "demo_harbor", "aspect": "physical"})
        updated = self.store.update_work_item(work["id"], {"revision": 1, "status": "In progress", "action_type": "Information update", "assignee": "Access team", "notes": "Fictional verification: inspect side entrance signage."})
        refreshed = copy.deepcopy(self.payload)
        refreshed["dataset"]["generated_at"] = "2026-11-15T02:00:00+00:00"
        refreshed["places"] = [p for p in refreshed["places"] if p["place_id"] != "demo_harbor"]
        refreshed["aspects"] = [a for a in refreshed["aspects"] if a["place_id"] != "demo_harbor"]
        refreshed["evidence"] = [e for e in refreshed["evidence"] if e["place_id"] != "demo_harbor"]
        self.store.import_bundle(refreshed)
        self.store.close(); self.store = Store(self.path)
        self.assertEqual(self.store.get_work_item(work["id"]), updated)
        with self.assertRaises(AppError):
            self.store.place_detail("demo_harbor")
        original = self.store.place_detail("demo_harbor", snapshot_id=work["source_snapshot_id"])
        self.assertEqual(len(original["evidence"]), 3)

    def test_stale_edits_are_rejected_and_resolution_needs_notes(self):
        work = self.store.create_work_item({"place_id": "demo_harbor", "aspect": "physical"})
        self.store.update_work_item(work["id"], {"revision": 1, "assignee": "Team A"})
        with self.assertRaises(AppError) as error:
            self.store.update_work_item(work["id"], {"revision": 1, "assignee": "Team B"})
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(self.store.get_work_item(work["id"])["assignee"], "Team A")
        with self.assertRaises(AppError):
            self.store.update_work_item(work["id"], {"revision": 2, "status": "Resolved"})

    def test_csv_escapes_spreadsheet_formulas(self):
        work = self.store.create_work_item({"place_id": "demo_harbor", "aspect": "physical"})
        self.store.update_work_item(work["id"], {"revision": 1, "notes": "=1+1"})
        self.assertIn("'=1+1", self.store.export_work_items())


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = Store(":memory:")
        cls.store.import_bundle(demo_bundle())
        cls.server = make_server(cls.store, port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(); cls.store.close()

    def request(self, path, method="GET", body=None, headers=None):
        headers = {"Content-Type": "application/json", **(headers or {})}
        request = Request(self.url + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers=headers)
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            response = error
        return response.status, response.read(), response.headers

    def test_frontend_and_api(self):
        status, body, headers = self.request("/")
        self.assertEqual(status, 200); self.assertIn(b"app.js", body)
        self.assertIn("nosniff", headers["X-Content-Type-Options"])
        status, body, _ = self.request("/api/places?service=clinic&aspect=language")
        self.assertEqual(status, 200); self.assertEqual(json.loads(body)["total"], 2)
        status, body, _ = self.request("/api/work-items", "POST", {"place_id": "demo_meadow", "aspect": "financial"})
        self.assertEqual(status, 201)
        wid = json.loads(body)["id"]
        status, body, _ = self.request(f"/api/work-items/{wid}", "PATCH", {"revision": 1, "status": "In progress", "notes": "Demo: check fees."})
        self.assertEqual(status, 200); self.assertEqual(json.loads(body)["revision"], 2)
        status, body, headers = self.request("/api/work-items.csv")
        self.assertEqual(status, 200); self.assertIn(b"Demo: check fees.", body)
        self.assertIn("attachment", headers["Content-Disposition"])

    def test_evidence_filter_http_contract(self):
        for aspect, total in (("physical", 3), ("sensory", 1), ("language", 3), ("financial", 1), ("time", 3)):
            with self.subTest(aspect=aspect):
                status, body, _ = self.request(f"/api/places?aspect={aspect}&status=with_evidence&limit=1")
                self.assertEqual(status, 200)
                result = json.loads(body)
                self.assertEqual(result["total"], total)
                self.assertEqual(len(result["items"]), 1)
        status, body, _ = self.request("/api/places?aspect=physical&service=clinic&status=with_evidence")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["total"], 1)

    def test_evidence_tabs_http_contract(self):
        status, body, _ = self.request("/api/places/demo_harbor?aspect=physical&evidence_state=positive_access")
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result["evidence_total"], 1)
        self.assertEqual(result["evidence_counts"]["all"], 3)
        self.assertEqual(result["evidence"][0]["state"], "positive_access")
        status, body, _ = self.request("/api/places/demo_harbor?aspect=physical&evidence_state=barrier_reported&evidence_offset=1")
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body)["evidence"]), 1)
        for suffix in ("evidence_state=invalid", "evidence_offset=-1", "evidence_offset=abc"):
            self.assertEqual(self.request("/api/places/demo_harbor?" + suffix)[0], 400)

    def test_chat_http_contract(self):
        status, body, _ = self.request("/api/chat", "POST", {"question": "Which places need verification?", "service": "clinic"})
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result["aggregate"]["locations"], 2)
        self.assertEqual(result["mode"], "retrieval")
        self.assertTrue(result["citations"])
        self.assertEqual(self.request("/api/chat", "POST", {"question": "x" * 1501})[0], 400)
        self.assertEqual(self.request("/api/chat", "POST", {"question": "x"}, {"Origin": "https://example.invalid"})[0], 403)
        status, body, _ = self.request("/api/chat/config")
        self.assertEqual(status, 200)
        self.assertNotIn("key", json.loads(body))

    def test_invalid_requests_and_static_file_boundary(self):
        self.assertEqual(self.request("/api/places?limit=-1")[0], 400)
        self.assertEqual(self.request("/api/places?unknown=1")[0], 400)
        self.assertEqual(self.request("/api/work-items", "POST", {}, {"Origin": "https://example.invalid"})[0], 403)
        self.assertEqual(self.request("/api/import", "POST", {"schema_version": 999})[0], 400)
        self.assertEqual(self.request("/..%2Fdatabase.py")[0], 404)

    @patch.dict(os.environ, {}, clear=True)
    def test_enter_key_use_it_and_remove_it_without_secret_disclosure(self):
        key = 'sk-local-test-not-a-real-key'
        try:
            with patch('access_app.chat.urlopen') as provider:
                status, body, headers = self.request('/api/chat/config', 'POST', {'api_key': key, 'model': 'test-model'}, {'Origin': self.url})
                provider.assert_not_called()
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(body)['available'])
            self.assertTrue(json.loads(body)['configurable'])
            self.assertNotIn(key.encode(), body)
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.assertNotIn(key.encode(), self.request('/api/chat/config')[1])
            response = {'status': 'completed', 'output': [{'content': [{'type': 'output_text', 'text': '{"source_ids":["E1"]}'}]}]}
            with patch('access_app.chat.urlopen', return_value=io.BytesIO(json.dumps(response).encode())) as provider:
                status, body, _ = self.request('/api/chat', 'POST', {'question': 'physical barriers', 'use_llm': True})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['mode'], 'llm')
            self.assertEqual(provider.call_args.args[0].get_header('Authorization'), 'Bearer ' + key)
            self.assertNotIn(key.encode(), body)
            self.assertNotIn(key.encode(), self.request('/api/metadata')[1])
            self.assertEqual(self.request('/api/chat/config', 'POST', {'clear': True}, {'Origin': 'https://example.invalid'})[0], 403)
            self.assertEqual(self.request('/api/chat/config', 'POST', {'api_key': 'x', 'model': 'x', 'unexpected': True})[0], 400)
        finally:
            self.request('/api/chat/config', 'POST', {'clear': True})
        self.assertFalse(json.loads(self.request('/api/chat/config')[1])['available'])
        with patch('access_app.chat.urlopen') as provider:
            self.assertEqual(json.loads(self.request('/api/chat', 'POST', {'question': 'physical barriers', 'use_llm': True})[1])['mode'], 'retrieval')
            provider.assert_not_called()

    def test_browser_key_entry_is_disabled_for_network_bound_servers(self):
        server = make_server(self.store, host='0.0.0.0', port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{server.server_port}/api/chat/config'
        try:
            with urlopen(url, timeout=10) as response:
                self.assertFalse(json.load(response)['configurable'])
            request = Request(url, data=b'{"api_key":"sk-test","model":"test-model"}', headers={'Content-Type': 'application/json'})
            with self.assertRaises(HTTPError) as error:
                urlopen(request, timeout=10)
            self.assertEqual(error.exception.code, 403)
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == "__main__":
    unittest.main()

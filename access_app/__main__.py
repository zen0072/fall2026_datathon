"""Run with python -m access_app --help."""

import argparse
import json
from pathlib import Path

from .database import Store
from .demo import demo_bundle
from .schema import AppError
from .server import make_server


def main():
    parser = argparse.ArgumentParser(description="Access Beyond the Map: DuckDB organization workspace")
    parser.add_argument("command", choices=("serve", "import", "demo"))
    parser.add_argument("file", nargs="?", help="Notebook frontend_results_PRIVATE.json (import only)")
    parser.add_argument("--db", default="var/access.duckdb", help="Persistent DuckDB file")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--demo", action="store_true", help="On serve, seed fictional demo data only if the database has no imported snapshot")
    args = parser.parse_args()
    store = Store(args.db)
    try:
        if args.command == "import":
            if not args.file:
                parser.error("import requires a results JSON file")
            metadata = store.import_bundle(json.loads(Path(args.file).read_text(encoding="utf-8")))
            print(json.dumps(metadata, indent=2))
        elif args.command == "demo":
            print(json.dumps(store.import_bundle(demo_bundle()), indent=2))
        else:
            if args.demo and not store.metadata()["snapshot_id"]:
                store.import_bundle(demo_bundle())
            server = make_server(store, args.host, args.port)
            print(f"Access workspace: http://{args.host}:{server.server_port}/", flush=True)
            print(f"DuckDB: {Path(args.db).resolve()}", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
    except (AppError, ValueError, OSError) as error:
        parser.exit(1, f"{error}\n")
    finally:
        store.close()


if __name__ == "__main__":
    main()

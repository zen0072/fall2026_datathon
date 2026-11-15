"""Clone-and-run launcher. Installs only app dependencies; uses real saved results."""

import argparse
import hashlib
import socket
import subprocess
import sys
import time
import venv
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def app_python():
    directory = ROOT / ".venv"
    executable = directory / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not executable.exists():
        print("Creating .venv for the local app…", flush=True)
        venv.EnvBuilder(with_pip=True).create(directory)
    requirements = ROOT / "requirements-app.txt"
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    receipt = directory / ".access-app-requirements.sha256"
    ready = subprocess.run([str(executable), "-c", "import duckdb"], capture_output=True).returncode == 0
    if not ready or not receipt.exists() or receipt.read_text() != fingerprint:
        print("Installing app dependencies…", flush=True)
        subprocess.run([str(executable), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(requirements)], check=True)
        receipt.write_text(fingerprint)
    return executable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default="var/access.duckdb")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--empty", action="store_true", help="Do not seed bundled real results")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error("Use Python 3.11 or later (3.12 recommended).")
    if not 1 <= args.port <= 65535:
        parser.error("Choose a port between 1 and 65535.")
    try:
        # Fail clearly instead of mistaking another running app for this process.
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", args.port))
    except OSError:
        parser.error(f"Port {args.port} is in use. Stop the other app or use --port {args.port + 1 if args.port < 65535 else 8000}.")
    child = None
    try:
        executable = app_python()
        command = [str(executable), "-m", "access_app", "serve", "--host", "127.0.0.1",
                   "--port", str(args.port), "--db", args.db]
        if not args.empty:
            command.append("--bundled")
        child = subprocess.Popen(command, cwd=ROOT)
        url = f"http://127.0.0.1:{args.port}/"
        ready = False
        for _ in range(150):
            if child.poll() is not None:
                return child.returncode
            try:
                with urlopen(url + "api/health", timeout=0.3) as response:
                    ready = response.status == 200
            except (URLError, TimeoutError, OSError):
                pass
            if ready:
                break
            time.sleep(0.1)
        if not ready:
            print("The app did not start in time. Check the server output above.", file=sys.stderr)
            return 1
        print(f"\nOpen {url}\nUse ‘Use your own OpenAI key’ in the evidence assistant.\nPress Ctrl+C to stop the app and discard any key entered in the page.", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        return child.wait()
    except KeyboardInterrupt:
        print("\nStopping the local app.", flush=True)
        return 0
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"Could not launch the app: {error}", file=sys.stderr)
        return 1
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    raise SystemExit(main())

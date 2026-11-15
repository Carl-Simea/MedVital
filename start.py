#!/usr/bin/env python3
"""MedVital: one command starts the whole mission.

    python start.py                 everything on this laptop, opens all the apps
    python start.py --fresh         same, but start a clean mission (wipes runtime/)

Three-laptop demo (same Wi-Fi):
    NASA laptop:        python start.py --role nasa --lan
    Spacecraft laptop:  python start.py --role spacecraft --lan --nasa-url http://<NASA-laptop-IP>:5000
    Astronaut laptop:   open http://<spacecraft-laptop-IP>:8000/astronaut/  (one tab per astronaut)

Add --tunnel to also publish the hub through a Cloudflare quick tunnel (needs `cloudflared` installed).

The first run creates .venv/ here and installs what the backend needs (a few minutes, once).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
RUNTIME = ROOT / "runtime"


def say(msg: str) -> None:
    print(f"[medvital] {msg}", flush=True)


# ---------------------------------------------------------------------------- environment
def deps_ok() -> bool:
    try:
        import fastapi  # noqa: F401
        import flask  # noqa: F401
        import uvicorn  # noqa: F401

        import medvital.hub.app  # noqa: F401
        return True
    except Exception:
        return False


def ensure_env() -> None:
    """Run inside .venv with everything installed. Re-launches this script if needed."""
    if sys.version_info < (3, 11):
        sys.exit("MedVital needs Python 3.11 or newer.")
    if deps_ok():
        return
    if Path(sys.prefix).resolve() != VENV.resolve():   # not running inside .venv yet
        if not VENV_PY.exists():
            say("first run: creating .venv (once)")
            subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])
        if subprocess.call([str(VENV_PY), "-c", "import medvital.hub.app, flask"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
            say("installing the backend and Flask into .venv (a few minutes, once)")
            subprocess.check_call([str(VENV_PY), "-m", "pip", "install", "-q", "--upgrade", "pip"])
            subprocess.check_call([str(VENV_PY), "-m", "pip", "install", "-q", "-e", str(ROOT / "backend") + "[nasa]"])
        os.execv(str(VENV_PY), [str(VENV_PY), str(Path(__file__).resolve()), *sys.argv[1:]])
    sys.exit("Dependencies are missing inside .venv. Delete the .venv folder and run python start.py again.")


def free_port(preferred: int, host: str) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket() as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    sys.exit(f"No free port near {preferred}.")


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def wait_http(url: str, seconds: float = 40) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except Exception:
            time.sleep(0.4)
    return False


def pipe(proc: subprocess.Popen, name: str, on_line=None) -> None:
    def run():
        for line in iter(proc.stdout.readline, ""):
            if on_line:
                on_line(line)
            if line.strip() and "GET /hub/" not in line and "POST /hub/burst" not in line:
                print(f"  {name} | {line.rstrip()}", flush=True)
    threading.Thread(target=run, daemon=True).start()


# ---------------------------------------------------------------------------- main
def main() -> None:
    p = argparse.ArgumentParser(description="Start the MedVital mission (NASA receiver + spacecraft hub + apps).")
    p.add_argument("--role", choices=("all", "spacecraft", "nasa"), default="all")
    p.add_argument("--nasa-url", help="NASA receiver URL when it runs on another laptop")
    p.add_argument("--hub-port", type=int, default=8000)
    p.add_argument("--nasa-port", type=int, default=5000)
    p.add_argument("--lan", action="store_true", help="let the other laptops on this network connect")
    p.add_argument("--fresh", action="store_true", help="start a clean mission (deletes runtime/)")
    p.add_argument("--tunnel", action="store_true", help="also publish the hub with a Cloudflare quick tunnel")
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()

    ensure_env()
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    if args.fresh and RUNTIME.exists():
        shutil.rmtree(RUNTIME)
        say("fresh mission: runtime/ cleared")
    RUNTIME.mkdir(exist_ok=True)

    procs: list[subprocess.Popen] = []
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    urls: dict[str, str] = {}
    ip = lan_ip() if args.lan else "localhost"

    if args.role in ("all", "nasa"):
        port = free_port(args.nasa_port, host)
        nasa_env = {**env, "MEDVITAL_NASA_HOST": host, "MEDVITAL_NASA_PORT": str(port),
                    "MEDVITAL_NASA_DB": str(RUNTIME / "mission.db")}
        procs.append(subprocess.Popen([sys.executable, "app.py"], cwd=ROOT / "nasa", env=nasa_env,
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True))
        pipe(procs[-1], "nasa")
        urls["nasa"] = f"http://localhost:{port}"
        if not wait_http(urls["nasa"] + "/link"):
            say("the NASA receiver did not start; see the lines above")

    if args.role in ("all", "spacecraft"):
        nasa_url = args.nasa_url or urls.get("nasa")
        if not nasa_url:
            say("no --nasa-url given: the hub will keep everything in its outbox until a NASA receiver is set")
        port = free_port(args.hub_port, host)
        hub_env = {**env, "MEDVITAL_DATA_DIR": str(RUNTIME), "MEDVITAL_NASA_URL": nasa_url or "",
                   "MEDVITAL_REPO_ROOT": str(ROOT)}
        procs.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "--factory", "medvital.hub.app:create_hub_app",
             "--host", host, "--port", str(port), "--log-level", "warning"],
            cwd=ROOT / "backend", env=hub_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True))
        pipe(procs[-1], "hub")
        urls["hub"] = f"http://localhost:{port}"
        if not wait_http(urls["hub"] + "/hub/status"):
            say("the spacecraft hub did not start; see the lines above")

    if args.tunnel and "hub" in urls:
        exe = shutil.which("cloudflared")
        if not exe:
            say("--tunnel: cloudflared is not installed (https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)")
        else:
            t = subprocess.Popen([exe, "tunnel", "--url", urls["hub"]], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True)
            procs.append(t)

            def found(line: str) -> None:
                m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
                if m:
                    say(f"Cloudflare tunnel: {m.group(0)}/astronaut/   (works from any phone)")
            pipe(t, "tunnel", found)

    pages = []
    print()
    say("MedVital is running. Ctrl+C stops everything.")
    if "hub" in urls:
        h = urls["hub"].replace("localhost", ip)
        say(f"  Start page       {h}/")
        say(f"  Astronauts       {h}/astronaut/        (log in or sign up)")
        say(f"  Spacecraft hub   {h}/cloudflare/")
        say(f"  API docs         {h}/docs")
        say("  Demo clock: 1 real minute = 1 mission day. Data goes to NASA at the end of each day.")
        pages += [f"{urls['hub']}/", f"{urls['hub']}/cloudflare/", f"{urls['hub']}/body/?astronaut=astro-1"]
    if "nasa" in urls:
        say(f"  NASA             {urls['nasa'].replace('localhost', ip)}/")
        pages.append(urls["nasa"] + "/")
    print()
    if not args.no_browser:
        for page in pages:
            webbrowser.open_new_tab(page)
            time.sleep(0.3)

    def stop(*_):
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        say("stopped. The mission data is kept in runtime/ (use --fresh for a clean start).")
        sys.exit(0)

    signal.signal(signal.SIGINT, stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop)
    while True:
        for proc in procs:
            if proc.poll() is not None and proc.args[0] != shutil.which("cloudflared"):
                say(f"a process stopped (exit {proc.returncode}); shutting down")
                stop()
        time.sleep(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""MedVital: one command starts the whole mission.

    python start.py                 everything on this laptop, opens all the apps
    python start.py --fresh         same, but start a clean mission (wipes runtime/)

Three-laptop demo (same Wi-Fi):
    NASA laptop:        python start.py --role nasa --lan
    Spacecraft laptop:  python start.py --role spacecraft --lan --nasa-url http://<NASA-laptop-IP>:5000
    Astronaut laptop:   open http://<spacecraft-laptop-IP>:8000/astronaut/  (one tab per astronaut)

Add --tunnel to also publish the hub through a Cloudflare quick tunnel (needs `cloudflared` installed).

Link to Earth on Cloudflare (cloudflare/ Worker + D1 + Workers AI):
    python start.py --worker-local  run the Worker on this laptop with wrangler (needs Node.js), local D1
    deployed Worker:                put MEDVITAL_CLOUDFLARE_URL and MEDVITAL_CLOUDFLARE_KEY in .env
                                    (gitignored) or in Codespaces secrets, then python start.py

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
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
RUNTIME = ROOT / "runtime"
WORKER_DIR = ROOT / "cloudflare"


def say(msg: str) -> None:
    print(f"[medvital] {msg}", flush=True)


# ---------------------------------------------------------------------------- environment
def load_dotenv(path: Path) -> None:
    """KEY=value lines from the gitignored .env; real environment variables always win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():  # utf-8-sig: Windows may add a BOM
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def worker_call(url: str, key: str, method: str, path: str, body: dict | None = None) -> int | None:
    import json as _json
    req = urllib.request.Request(url.rstrip("/") + path, method=method,
                                 data=_json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "x-medvital-key": key,
                                          "User-Agent": "MedVital/1.0 (+https://github.com/Carl-Simea/MedVital)"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:
        return None


def start_local_worker(procs: list, port: int) -> tuple[str, str] | None:
    """`wrangler dev --local`: the Worker and a local D1 on this laptop. Workers AI needs the real account."""
    npx = shutil.which("npx")
    if not npx:
        say("--worker-local needs Node.js (npx). Install it from https://nodejs.org or drop --worker-local.")
        return None
    dev_vars = WORKER_DIR / ".dev.vars"  # gitignored; a fresh random key the first time
    if not dev_vars.exists():
        import secrets
        dev_vars.write_text(f"MEDVITAL_KEY={secrets.token_urlsafe(24)}\n", encoding="utf-8")
    key = next(line.split("=", 1)[1].strip() for line in dev_vars.read_text().splitlines()
               if line.startswith("MEDVITAL_KEY="))
    wrangler = [npx, "--yes", "wrangler@4"]  # the Worker creates its D1 tables itself on first use
    say("Cloudflare Worker (local): starting wrangler dev (the first run downloads wrangler)...")
    procs.append(subprocess.Popen([*wrangler, "dev", "--local", "--port", str(port)], cwd=WORKER_DIR,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True))
    pipe(procs[-1], "worker", lambda line: None)
    url = f"http://localhost:{port}"
    if not wait_http(url + "/health", 90):
        say("the local Cloudflare Worker did not start; see the lines above")
        return None
    return url, key


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
            quiet = ("GET /hub/", "POST /hub/burst", "[wrangler:info] GET", "[wrangler:info] POST")
            if line.strip() and not any(q in line for q in quiet):
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
    p.add_argument("--worker-local", action="store_true",
                   help="run the Cloudflare Worker + D1 link to Earth on this laptop (wrangler, needs Node.js)")
    p.add_argument("--worker-port", type=int, default=8787)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()

    load_dotenv(ROOT / ".env")
    for wrong in (ROOT / ".env.txt", ROOT / "env", ROOT / ".env.example.txt"):
        if wrong.exists() and not (ROOT / ".env").exists():
            say(f"found {wrong.name} but no .env: rename it to .env (Windows Notepad adds .txt)")
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

    if args.worker_local:
        local = start_local_worker(procs, args.worker_port)
        if local:
            env["MEDVITAL_CLOUDFLARE_URL"], env["MEDVITAL_CLOUDFLARE_KEY"] = local
    cf_url, cf_key = env.get("MEDVITAL_CLOUDFLARE_URL", ""), env.get("MEDVITAL_CLOUDFLARE_KEY", "")
    model = env.get("MEDVITAL_OLLAMA_MODEL", "")
    if model:
        import json as _json
        base = env.get("MEDVITAL_OLLAMA_URL", "http://localhost:11434").rstrip("/")
        try:
            with urllib.request.urlopen(base + "/api/tags", timeout=5) as r:  # noqa: S310
                names = [m.get("name") for m in _json.loads(r.read()).get("models", [])]
            if model in names or f"{model}:latest" in names:
                say(f"Onboard agent: Ollama {model} (loading it in the background)")
                def _warm() -> None:   # load the model now so the first question is quick
                    req = urllib.request.Request(base + "/api/generate", method="POST",
                                                 data=_json.dumps({"model": model, "prompt": "hi", "keep_alive": "30m",
                                                                   "stream": False}).encode())
                    try:
                        urllib.request.urlopen(req, timeout=180).read()  # noqa: S310
                    except OSError:
                        pass
                threading.Thread(target=_warm, daemon=True).start()
            else:
                say(f"Onboard agent: '{model}' is not in `ollama list` ({', '.join(n for n in names if n)}): fix the name in .env")
        except OSError:
            say("Onboard agent: Ollama is not running (start the Ollama app); using Workers AI or built-in replies")
    else:
        say("Onboard agent: no local model set (MEDVITAL_OLLAMA_MODEL); using Workers AI or built-in replies")
    if not cf_url:
        say("Cloudflare: OFF (no MEDVITAL_CLOUDFLARE_URL in .env). The spacecraft sends straight to NASA.")
    elif "<" in cf_key or not cf_key.strip():
        say("Cloudflare: the key in .env is empty or still the placeholder <your key>: put your real key there")
    if cf_url and not cf_key:
        say("MEDVITAL_CLOUDFLARE_URL is set but MEDVITAL_CLOUDFLARE_KEY is not: using the direct link instead")
        env.pop("MEDVITAL_CLOUDFLARE_URL")
        cf_url = ""
    if cf_url:
        status = worker_call(cf_url, cf_key, "GET", "/link")
        if status == 200:
            say(f"Cloudflare: ON. Link to NASA, checker and DONKI run through {cf_url}")
            if args.fresh and args.role in ("all", "spacecraft"):
                # a clean mission on Earth too, or NASA would pull the last mission's records
                worker_call(cf_url, cf_key, "POST", "/reset", {"confirm": "new mission"})
                worker_call(cf_url, cf_key, "POST", "/link", {"up": True})
                say("fresh mission: the Cloudflare D1 record was cleared")
        else:
            say(f"Cloudflare Worker {cf_url} answered {status or 'nothing'}"
                f"{' (wrong key)' if status == 401 else ''}: the hub keeps everything in its outbox until it answers")

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
    if cf_url:
        say(f"  Cloudflare       Worker + D1 + checker  {cf_url}")
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
            if proc.poll() is not None and proc.args[0] not in (shutil.which("cloudflared"), shutil.which("npx")):
                say(f"a process stopped (exit {proc.returncode}); shutting down")
                stop()
        time.sleep(1)


if __name__ == "__main__":
    main()

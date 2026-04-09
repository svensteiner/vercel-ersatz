#!/usr/bin/env python3
"""
ersatz - Wie Vercel, nur lokal.

Einfach im Projektordner ausführen:
    ersatz

Das war's.
"""
import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
import socket
import webbrowser

# Konfiguration
HOME = Path.home() / ".ersatz"
PROJECTS = HOME / "projects"
PORT = 3000

HOME.mkdir(exist_ok=True)
PROJECTS.mkdir(exist_ok=True)


def build_project(path: Path) -> Path:
    """Baut das Projekt und gibt Output-Pfad zurück."""

    # Node.js Projekt
    if (path / "package.json").exists():
        pkg = json.loads((path / "package.json").read_text())

        print("📦 Dependencies installieren...")
        if (path / "pnpm-lock.yaml").exists():
            subprocess.run(["pnpm", "i"], cwd=path, capture_output=True)
        elif (path / "yarn.lock").exists():
            subprocess.run(["yarn"], cwd=path, capture_output=True)
        else:
            subprocess.run(["npm", "i"], cwd=path, capture_output=True)

        if "build" in pkg.get("scripts", {}):
            print("🔨 Bauen...")
            subprocess.run(["npm", "run", "build"], cwd=path, capture_output=True)

        # Output finden
        for d in ["dist", "build", "out", "public", ".next"]:
            if (path / d).exists():
                return path / d

    # Statisch
    return path


def deploy(path: Path = None):
    """Deployed das Projekt."""
    path = (path or Path.cwd()).resolve()
    name = path.name

    print(f"🚀 Deploying {name}...")

    # Bauen
    output = build_project(path)

    # Kopieren
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = PROJECTS / name / ts / "files"
    dest.mkdir(parents=True, exist_ok=True)

    print("📁 Kopiere Dateien...")
    for item in output.iterdir():
        if item.name in [".git", "node_modules", ".env", "__pycache__"]:
            continue
        if item.is_dir():
            shutil.copytree(item, dest / item.name, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest / item.name)

    # Current-Link
    current = PROJECTS / name / "current"
    if current.exists():
        current.unlink()
    current.symlink_to(dest)

    # Fertig
    url = f"http://localhost:{PORT}/{name}/"
    print(f"\n✅ Deployed!")
    print(f"🌐 {url}\n")

    # Server läuft?
    sock = socket.socket()
    if sock.connect_ex(("localhost", PORT)) != 0:
        print("⚠️  Server nicht gestartet. Starte mit: ersatz serve")
    sock.close()

    return url


def serve():
    """Startet den Server."""
    class Handler(SimpleHTTPRequestHandler):
        def translate_path(self, path):
            parts = path.strip("/").split("/", 1)
            if parts[0]:
                project = parts[0]
                rest = parts[1] if len(parts) > 1 else "index.html"
                full = PROJECTS / project / "current" / rest
                if not full.exists():
                    full = PROJECTS / project / "current" / "index.html"
                return str(full)
            return str(PROJECTS)

        def log_message(self, *args):
            pass

    print(f"🌐 Server läuft auf http://localhost:{PORT}")
    print("📂 Projekte:")
    for p in PROJECTS.iterdir():
        if p.is_dir() and (p / "current").exists():
            print(f"   http://localhost:{PORT}/{p.name}/")
    print("\nStrg+C zum Beenden")

    HTTPServer(("", PORT), Handler).serve_forever()


def ls():
    """Zeigt alle Projekte."""
    print("\n📂 Projekte:\n")
    for p in PROJECTS.iterdir():
        if p.is_dir() and (p / "current").exists():
            print(f"  {p.name:20} → http://localhost:{PORT}/{p.name}/")
    print()


def main():
    args = sys.argv[1:]

    if not args:
        # Wie Vercel: einfach "ersatz" = deploy
        deploy()
    elif args[0] == "serve":
        serve()
    elif args[0] == "ls":
        ls()
    elif args[0] == "deploy" and len(args) > 1:
        deploy(Path(args[1]))
    else:
        print("""
ersatz - Wie Vercel, nur lokal.

BEFEHLE:
  ersatz              Deploy aktuellen Ordner
  ersatz serve        Server starten
  ersatz ls           Alle Projekte zeigen
  ersatz deploy <dir> Bestimmten Ordner deployen
""")


if __name__ == "__main__":
    main()

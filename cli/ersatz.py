#!/usr/bin/env python3
"""
Ersatz CLI - Vercel-ähnliches CLI für lokale Deployments
"""
import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from typing import Optional
import requests

# CLI Konfiguration
CONFIG_DIR = Path.home() / ".ersatz"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_SERVER = "http://localhost:9000"


def load_cli_config() -> dict:
    """Lädt die CLI-Konfiguration."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {"server": DEFAULT_SERVER, "projects": {}}


def save_cli_config(config: dict):
    """Speichert die CLI-Konfiguration."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_server_url() -> str:
    """Holt die Server-URL aus der Konfiguration."""
    config = load_cli_config()
    return os.getenv("ERSATZ_SERVER", config.get("server", DEFAULT_SERVER))


def detect_framework(project_path: Path) -> dict:
    """Erkennt das Framework und gibt Build-Konfiguration zurück."""
    package_json = project_path / "package.json"

    if package_json.exists():
        with open(package_json) as f:
            pkg = json.load(f)

        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        scripts = pkg.get("scripts", {})

        # Next.js
        if "next" in deps:
            return {
                "project_type": "nextjs",
                "build_command": "npm run build",
                "output_dir": ".next",
                "framework": "Next.js"
            }

        # Vite
        if "vite" in deps:
            return {
                "project_type": "static",
                "build_command": "npm run build",
                "output_dir": "dist",
                "framework": "Vite"
            }

        # Create React App
        if "react-scripts" in deps:
            return {
                "project_type": "static",
                "build_command": "npm run build",
                "output_dir": "build",
                "framework": "Create React App"
            }

        # Vue CLI
        if "@vue/cli-service" in deps:
            return {
                "project_type": "static",
                "build_command": "npm run build",
                "output_dir": "dist",
                "framework": "Vue CLI"
            }

        # Nuxt
        if "nuxt" in deps:
            return {
                "project_type": "nodejs",
                "build_command": "npm run build",
                "output_dir": ".output",
                "framework": "Nuxt"
            }

        # SvelteKit
        if "@sveltejs/kit" in deps:
            return {
                "project_type": "static",
                "build_command": "npm run build",
                "output_dir": "build",
                "framework": "SvelteKit"
            }

        # Astro
        if "astro" in deps:
            return {
                "project_type": "static",
                "build_command": "npm run build",
                "output_dir": "dist",
                "framework": "Astro"
            }

        # Plain Node.js
        if "start" in scripts:
            return {
                "project_type": "nodejs",
                "build_command": scripts.get("build", ""),
                "output_dir": ".",
                "framework": "Node.js"
            }

        # Static with build
        if "build" in scripts:
            return {
                "project_type": "static",
                "build_command": "npm run build",
                "output_dir": "dist",
                "framework": "Static (npm)"
            }

    # Python (FastAPI, Flask, Django)
    if (project_path / "requirements.txt").exists():
        if (project_path / "manage.py").exists():
            return {
                "project_type": "python",
                "build_command": "",
                "output_dir": ".",
                "framework": "Django"
            }
        return {
            "project_type": "python",
            "build_command": "",
            "output_dir": ".",
            "framework": "Python"
        }

    # Statische HTML-Seite
    if (project_path / "index.html").exists():
        return {
            "project_type": "static",
            "build_command": "",
            "output_dir": ".",
            "framework": "Static HTML"
        }

    return {
        "project_type": "static",
        "build_command": "",
        "output_dir": ".",
        "framework": "Unknown"
    }


def cmd_init(args):
    """Initialisiert ein neues Ersatz-Projekt."""
    project_path = Path(args.path or ".").resolve()

    if not project_path.exists():
        print(f"Error: Path {project_path} does not exist")
        sys.exit(1)

    ersatz_json = project_path / "ersatz.json"

    # Framework erkennen
    detected = detect_framework(project_path)
    print(f"Detected framework: {detected['framework']}")

    # Projektnamen ermitteln
    name = args.name or project_path.name

    config = {
        "name": name,
        "project_type": detected["project_type"],
        "build_command": detected["build_command"],
        "output_dir": detected["output_dir"],
        "framework": detected["framework"],
        "env_vars": {}
    }

    if ersatz_json.exists() and not args.force:
        print(f"ersatz.json already exists. Use --force to overwrite.")
        sys.exit(1)

    with open(ersatz_json, "w") as f:
        json.dump(config, f, indent=2)

    print(f"Created ersatz.json for '{name}'")
    print(f"  Type: {config['project_type']}")
    print(f"  Build: {config['build_command'] or '(none)'}")
    print(f"  Output: {config['output_dir']}")


def cmd_link(args):
    """Verknüpft lokales Projekt mit dem Server."""
    project_path = Path(args.path or ".").resolve()
    ersatz_json = project_path / "ersatz.json"

    if not ersatz_json.exists():
        print("No ersatz.json found. Run 'ersatz init' first.")
        sys.exit(1)

    with open(ersatz_json) as f:
        local_config = json.load(f)

    # Git Remote ermitteln
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=project_path,
            capture_output=True,
            text=True
        )
        repo_url = result.stdout.strip() if result.returncode == 0 else ""
    except:
        repo_url = ""

    if not repo_url and not args.repo:
        print("No git remote found. Specify --repo URL")
        sys.exit(1)

    repo_url = args.repo or repo_url

    # Branch ermitteln
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=project_path,
            capture_output=True,
            text=True
        )
        branch = result.stdout.strip() if result.returncode == 0 else "main"
    except:
        branch = "main"

    # Projekt am Server registrieren
    server = get_server_url()
    project_config = {
        "name": local_config["name"],
        "repo_url": repo_url,
        "branch": args.branch or branch,
        "build_command": local_config["build_command"],
        "output_dir": local_config["output_dir"],
        "project_type": local_config["project_type"],
        "domain": args.domain,
        "port": args.port,
        "env_vars": local_config.get("env_vars", {})
    }

    try:
        resp = requests.post(f"{server}/projects", json=project_config)
        resp.raise_for_status()
        print(f"Project '{local_config['name']}' linked to server")
        print(f"  Webhook URL: {server}/webhook/{local_config['name']}")
    except requests.RequestException as e:
        print(f"Error linking project: {e}")
        sys.exit(1)


def cmd_deploy(args):
    """Startet ein manuelles Deployment."""
    project_path = Path(args.path or ".").resolve()
    ersatz_json = project_path / "ersatz.json"

    # Projektname ermitteln
    if args.name:
        name = args.name
    elif ersatz_json.exists():
        with open(ersatz_json) as f:
            name = json.load(f).get("name", project_path.name)
    else:
        name = project_path.name

    server = get_server_url()

    try:
        resp = requests.post(f"{server}/deploy/{name}")
        resp.raise_for_status()
        print(f"Deployment started for '{name}'")
        print(f"Check status: ersatz status {name}")
    except requests.RequestException as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_status(args):
    """Zeigt den Status eines Projekts."""
    server = get_server_url()
    name = args.name

    try:
        resp = requests.get(f"{server}/deployments/{name}")
        resp.raise_for_status()
        deployments = resp.json().get("deployments", [])

        if not deployments:
            print(f"No deployments found for '{name}'")
            return

        print(f"Deployments for '{name}':")
        print("-" * 60)

        for d in deployments[:10]:
            status_icon = {
                "deployed": "✓",
                "building": "◐",
                "pending": "○",
                "failed": "✗",
                "rolled_back": "↩"
            }.get(d["status"], "?")

            print(f"  {status_icon} {d['id']} | {d['commit'][:7]} | {d['status']}")

    except requests.RequestException as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_logs(args):
    """Zeigt die Logs eines Deployments."""
    server = get_server_url()

    try:
        resp = requests.get(f"{server}/logs/{args.project}/{args.deployment}")
        resp.raise_for_status()
        print(resp.json().get("logs", "No logs available"))
    except requests.RequestException as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_rollback(args):
    """Rollt zu einem früheren Deployment zurück."""
    server = get_server_url()

    try:
        resp = requests.post(f"{server}/rollback/{args.project}/{args.deployment}")
        resp.raise_for_status()
        print(resp.json().get("message", "Rollback completed"))
    except requests.RequestException as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_list(args):
    """Listet alle Projekte."""
    server = get_server_url()

    try:
        resp = requests.get(f"{server}/projects")
        resp.raise_for_status()
        projects = resp.json().get("projects", {})

        if not projects:
            print("No projects configured")
            return

        print("Configured projects:")
        print("-" * 60)

        for name, config in projects.items():
            print(f"  {name}")
            print(f"    Type: {config['project_type']}")
            print(f"    Branch: {config['branch']}")
            if config.get('domain'):
                print(f"    Domain: {config['domain']}")

    except requests.RequestException as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_env(args):
    """Verwaltet Umgebungsvariablen."""
    project_path = Path(".").resolve()
    ersatz_json = project_path / "ersatz.json"

    if not ersatz_json.exists():
        print("No ersatz.json found. Run 'ersatz init' first.")
        sys.exit(1)

    with open(ersatz_json) as f:
        config = json.load(f)

    if "env_vars" not in config:
        config["env_vars"] = {}

    if args.action == "list":
        if not config["env_vars"]:
            print("No environment variables set")
        else:
            for k, v in config["env_vars"].items():
                masked = v[:2] + "*" * (len(v) - 4) + v[-2:] if len(v) > 4 else "****"
                print(f"  {k}={masked}")

    elif args.action == "set":
        if not args.key:
            print("Usage: ersatz env set KEY VALUE")
            sys.exit(1)
        config["env_vars"][args.key] = args.value or ""
        with open(ersatz_json, "w") as f:
            json.dump(config, f, indent=2)
        print(f"Set {args.key}")

    elif args.action == "unset":
        if not args.key:
            print("Usage: ersatz env unset KEY")
            sys.exit(1)
        if args.key in config["env_vars"]:
            del config["env_vars"][args.key]
            with open(ersatz_json, "w") as f:
                json.dump(config, f, indent=2)
            print(f"Removed {args.key}")
        else:
            print(f"{args.key} not found")


def cmd_dev(args):
    """Startet den lokalen Entwicklungsserver."""
    project_path = Path(args.path or ".").resolve()
    detected = detect_framework(project_path)

    package_json = project_path / "package.json"

    if package_json.exists():
        with open(package_json) as f:
            pkg = json.load(f)
        scripts = pkg.get("scripts", {})

        # Dev-Script finden
        dev_cmd = None
        for script_name in ["dev", "start", "serve"]:
            if script_name in scripts:
                dev_cmd = f"npm run {script_name}"
                break

        if dev_cmd:
            print(f"Starting development server ({detected['framework']})...")
            print(f"Running: {dev_cmd}")
            os.chdir(project_path)
            os.system(dev_cmd)
        else:
            print("No dev script found in package.json")
            sys.exit(1)

    elif (project_path / "requirements.txt").exists():
        print("Starting Python development server...")
        os.chdir(project_path)
        if (project_path / "manage.py").exists():
            os.system("python manage.py runserver")
        else:
            os.system("uvicorn main:app --reload")

    else:
        # Statische Seite mit eingebautem Server
        print("Starting static file server...")
        os.chdir(project_path)
        os.system("python -m http.server 3000")


def cmd_build(args):
    """Baut das Projekt lokal."""
    project_path = Path(args.path or ".").resolve()
    ersatz_json = project_path / "ersatz.json"

    if ersatz_json.exists():
        with open(ersatz_json) as f:
            config = json.load(f)
        build_cmd = config.get("build_command")
    else:
        detected = detect_framework(project_path)
        build_cmd = detected["build_command"]

    if not build_cmd:
        print("No build command configured")
        return

    print(f"Building project...")
    print(f"Running: {build_cmd}")
    os.chdir(project_path)
    result = os.system(build_cmd)

    if result == 0:
        print("Build successful!")
    else:
        print("Build failed!")
        sys.exit(1)


def cmd_config(args):
    """Konfiguriert die CLI."""
    config = load_cli_config()

    if args.server:
        config["server"] = args.server
        save_cli_config(config)
        print(f"Server set to: {args.server}")
    else:
        print(f"Current server: {config.get('server', DEFAULT_SERVER)}")


def main():
    parser = argparse.ArgumentParser(
        prog="ersatz",
        description="Ersatz CLI - Vercel-ähnliches Deployment Tool"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # init
    init_parser = subparsers.add_parser("init", help="Initialize project")
    init_parser.add_argument("path", nargs="?", help="Project path")
    init_parser.add_argument("--name", "-n", help="Project name")
    init_parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing config")
    init_parser.set_defaults(func=cmd_init)

    # link
    link_parser = subparsers.add_parser("link", help="Link project to server")
    link_parser.add_argument("path", nargs="?", help="Project path")
    link_parser.add_argument("--repo", "-r", help="Git repository URL")
    link_parser.add_argument("--branch", "-b", help="Git branch")
    link_parser.add_argument("--domain", "-d", help="Custom domain")
    link_parser.add_argument("--port", "-p", type=int, help="Port for Node.js apps")
    link_parser.set_defaults(func=cmd_link)

    # deploy
    deploy_parser = subparsers.add_parser("deploy", help="Deploy project")
    deploy_parser.add_argument("path", nargs="?", help="Project path")
    deploy_parser.add_argument("--name", "-n", help="Project name")
    deploy_parser.set_defaults(func=cmd_deploy)

    # status
    status_parser = subparsers.add_parser("status", help="Show deployment status")
    status_parser.add_argument("name", help="Project name")
    status_parser.set_defaults(func=cmd_status)

    # logs
    logs_parser = subparsers.add_parser("logs", help="Show deployment logs")
    logs_parser.add_argument("project", help="Project name")
    logs_parser.add_argument("deployment", help="Deployment ID")
    logs_parser.set_defaults(func=cmd_logs)

    # rollback
    rollback_parser = subparsers.add_parser("rollback", help="Rollback deployment")
    rollback_parser.add_argument("project", help="Project name")
    rollback_parser.add_argument("deployment", help="Deployment ID to rollback to")
    rollback_parser.set_defaults(func=cmd_rollback)

    # list
    list_parser = subparsers.add_parser("list", help="List all projects")
    list_parser.set_defaults(func=cmd_list)

    # env
    env_parser = subparsers.add_parser("env", help="Manage environment variables")
    env_parser.add_argument("action", choices=["list", "set", "unset"])
    env_parser.add_argument("key", nargs="?", help="Variable name")
    env_parser.add_argument("value", nargs="?", help="Variable value")
    env_parser.set_defaults(func=cmd_env)

    # dev
    dev_parser = subparsers.add_parser("dev", help="Start development server")
    dev_parser.add_argument("path", nargs="?", help="Project path")
    dev_parser.set_defaults(func=cmd_dev)

    # build
    build_parser = subparsers.add_parser("build", help="Build project locally")
    build_parser.add_argument("path", nargs="?", help="Project path")
    build_parser.set_defaults(func=cmd_build)

    # config
    config_parser = subparsers.add_parser("config", help="Configure CLI")
    config_parser.add_argument("--server", "-s", help="Set server URL")
    config_parser.set_defaults(func=cmd_config)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()

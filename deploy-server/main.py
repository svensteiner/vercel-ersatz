"""
Ersatz Deploy Server - Vercel Alternative
Empfängt Webhooks, baut und deployt Projekte automatisch.
"""
import os
import json
import hmac
import hashlib
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

# Konfiguration
BASE_DIR = Path(os.getenv("ERSATZ_BASE_DIR", "/var/ersatz"))
DEPLOYMENTS_DIR = BASE_DIR / "deployments"
REPOS_DIR = BASE_DIR / "repos"
LOGS_DIR = BASE_DIR / "logs"
CONFIG_FILE = BASE_DIR / "config.json"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me-in-production")

# Verzeichnisse erstellen
for d in [DEPLOYMENTS_DIR, REPOS_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


class ProjectConfig(BaseModel):
    name: str
    repo_url: str
    branch: str = "main"
    build_command: str = "npm run build"
    output_dir: str = "dist"
    project_type: str = "static"  # static, nodejs, nextjs, python
    domain: Optional[str] = None
    port: Optional[int] = None
    env_vars: Dict[str, str] = {}


class DeploymentRecord(BaseModel):
    id: str
    project: str
    commit: str
    branch: str
    status: str  # pending, building, deployed, failed, rolled_back
    timestamp: str
    logs_file: str


def load_config() -> Dict[str, ProjectConfig]:
    """Lädt die Projektkonfiguration."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            data = json.load(f)
            return {k: ProjectConfig(**v) for k, v in data.get("projects", {}).items()}
    return {}


def save_config(projects: Dict[str, ProjectConfig]):
    """Speichert die Projektkonfiguration."""
    with open(CONFIG_FILE, "w") as f:
        json.dump({"projects": {k: v.model_dump() for k, v in projects.items()}}, f, indent=2)


def get_deployments(project: str) -> list[DeploymentRecord]:
    """Lädt alle Deployments eines Projekts."""
    deploy_file = DEPLOYMENTS_DIR / project / "deployments.json"
    if deploy_file.exists():
        with open(deploy_file) as f:
            return [DeploymentRecord(**d) for d in json.load(f)]
    return []


def save_deployment(record: DeploymentRecord):
    """Speichert ein Deployment-Record."""
    project_dir = DEPLOYMENTS_DIR / record.project
    project_dir.mkdir(parents=True, exist_ok=True)
    deploy_file = project_dir / "deployments.json"

    deployments = get_deployments(record.project)
    deployments.insert(0, record)
    # Behalte nur die letzten 20 Deployments
    deployments = deployments[:20]

    with open(deploy_file, "w") as f:
        json.dump([d.model_dump() for d in deployments], f, indent=2)


def verify_signature(payload: bytes, signature: str) -> bool:
    """Verifiziert GitHub/GitLab Webhook Signatur."""
    if not signature:
        return False
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def run_command(cmd: str, cwd: Path, env: dict = None) -> tuple[int, str]:
    """Führt einen Befehl aus und gibt Returncode + Output zurück."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    result = subprocess.run(
        cmd,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=full_env
    )
    output = result.stdout + result.stderr
    return result.returncode, output


def clone_or_pull(repo_url: str, project_name: str, branch: str) -> tuple[bool, str]:
    """Klont oder aktualisiert ein Repository."""
    repo_path = REPOS_DIR / project_name

    if repo_path.exists():
        # Pull
        code, output = run_command(f"git fetch origin && git checkout {branch} && git pull origin {branch}", repo_path)
    else:
        # Clone
        code, output = run_command(f"git clone -b {branch} {repo_url} {repo_path}", REPOS_DIR)

    return code == 0, output


def get_commit_hash(project_name: str) -> str:
    """Holt den aktuellen Commit-Hash."""
    repo_path = REPOS_DIR / project_name
    code, output = run_command("git rev-parse --short HEAD", repo_path)
    return output.strip() if code == 0 else "unknown"


def build_project(config: ProjectConfig, log_file: Path) -> tuple[bool, str]:
    """Baut ein Projekt basierend auf dem Typ."""
    repo_path = REPOS_DIR / config.name

    with open(log_file, "a") as log:
        log.write(f"\n=== Build started at {datetime.now().isoformat()} ===\n")

        # Install dependencies
        if config.project_type in ["static", "nodejs", "nextjs"]:
            if (repo_path / "package-lock.json").exists():
                cmd = "npm ci"
            elif (repo_path / "yarn.lock").exists():
                cmd = "yarn install --frozen-lockfile"
            elif (repo_path / "pnpm-lock.yaml").exists():
                cmd = "pnpm install --frozen-lockfile"
            else:
                cmd = "npm install"

            log.write(f"Running: {cmd}\n")
            code, output = run_command(cmd, repo_path, config.env_vars)
            log.write(output)
            if code != 0:
                return False, "Dependency installation failed"

        elif config.project_type == "python":
            if (repo_path / "requirements.txt").exists():
                cmd = "pip install -r requirements.txt"
                log.write(f"Running: {cmd}\n")
                code, output = run_command(cmd, repo_path, config.env_vars)
                log.write(output)
                if code != 0:
                    return False, "Python dependencies failed"

        # Run build command
        if config.build_command:
            log.write(f"Running build: {config.build_command}\n")
            code, output = run_command(config.build_command, repo_path, config.env_vars)
            log.write(output)
            if code != 0:
                return False, "Build failed"

        log.write(f"\n=== Build completed successfully ===\n")
        return True, "Build successful"


def deploy_static(config: ProjectConfig, deployment_id: str) -> tuple[bool, str]:
    """Deployt eine statische Seite."""
    repo_path = REPOS_DIR / config.name
    source = repo_path / config.output_dir

    if not source.exists():
        return False, f"Output directory {config.output_dir} not found"

    # Deployment-Verzeichnis erstellen
    deploy_path = DEPLOYMENTS_DIR / config.name / deployment_id
    deploy_path.mkdir(parents=True, exist_ok=True)

    # Dateien kopieren
    shutil.copytree(source, deploy_path / "public", dirs_exist_ok=True)

    # Symlink für "current" aktualisieren
    current_link = DEPLOYMENTS_DIR / config.name / "current"
    if current_link.is_symlink():
        current_link.unlink()
    current_link.symlink_to(deploy_path / "public")

    return True, f"Deployed to {deploy_path}"


def deploy_nodejs(config: ProjectConfig, deployment_id: str) -> tuple[bool, str]:
    """Deployt eine Node.js Anwendung."""
    repo_path = REPOS_DIR / config.name
    deploy_path = DEPLOYMENTS_DIR / config.name / deployment_id
    deploy_path.mkdir(parents=True, exist_ok=True)

    # Gesamtes Projekt kopieren
    shutil.copytree(repo_path, deploy_path / "app", dirs_exist_ok=True)

    # Symlink aktualisieren
    current_link = DEPLOYMENTS_DIR / config.name / "current"
    if current_link.is_symlink():
        current_link.unlink()
    current_link.symlink_to(deploy_path / "app")

    # PM2/systemd Service neu starten (falls konfiguriert)
    if config.port:
        run_command(f"pm2 restart {config.name} || pm2 start npm --name {config.name} -- start", deploy_path / "app")

    return True, f"Node.js app deployed to {deploy_path}"


async def execute_deployment(project_name: str):
    """Führt den gesamten Deployment-Prozess aus."""
    projects = load_config()
    if project_name not in projects:
        return

    config = projects[project_name]
    deployment_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOGS_DIR / f"{project_name}_{deployment_id}.log"

    record = DeploymentRecord(
        id=deployment_id,
        project=project_name,
        commit="pending",
        branch=config.branch,
        status="building",
        timestamp=datetime.now().isoformat(),
        logs_file=str(log_file)
    )
    save_deployment(record)

    try:
        # 1. Clone/Pull
        success, output = clone_or_pull(config.repo_url, project_name, config.branch)
        with open(log_file, "w") as f:
            f.write(f"=== Git Operation ===\n{output}\n")

        if not success:
            record.status = "failed"
            save_deployment(record)
            return

        record.commit = get_commit_hash(project_name)
        save_deployment(record)

        # 2. Build
        success, msg = build_project(config, log_file)
        if not success:
            record.status = "failed"
            save_deployment(record)
            return

        # 3. Deploy
        if config.project_type == "static":
            success, msg = deploy_static(config, deployment_id)
        elif config.project_type in ["nodejs", "nextjs"]:
            success, msg = deploy_nodejs(config, deployment_id)
        else:
            success, msg = deploy_static(config, deployment_id)

        with open(log_file, "a") as f:
            f.write(f"\n=== Deployment ===\n{msg}\n")

        record.status = "deployed" if success else "failed"
        save_deployment(record)

        # 4. Caddy Konfiguration aktualisieren
        if success and config.domain:
            update_caddy_config(project_name, config)

    except Exception as e:
        record.status = "failed"
        save_deployment(record)
        with open(log_file, "a") as f:
            f.write(f"\n=== ERROR ===\n{str(e)}\n")


def update_caddy_config(project_name: str, config: ProjectConfig):
    """Aktualisiert die Caddy-Konfiguration für ein Projekt."""
    caddy_dir = BASE_DIR / "caddy"
    caddy_dir.mkdir(exist_ok=True)

    site_config = caddy_dir / f"{project_name}.caddy"
    current_path = DEPLOYMENTS_DIR / project_name / "current"

    if config.project_type == "static":
        content = f"""
{config.domain} {{
    root * {current_path}
    file_server
    encode gzip

    # SPA Fallback
    try_files {{path}} /index.html

    # Security Headers
    header {{
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        Referrer-Policy strict-origin-when-cross-origin
    }}
}}
"""
    else:
        content = f"""
{config.domain} {{
    reverse_proxy localhost:{config.port}
    encode gzip

    header {{
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
    }}
}}
"""

    with open(site_config, "w") as f:
        f.write(content)

    # Caddy neu laden
    run_command("caddy reload --config /etc/caddy/Caddyfile", Path("/"))


def rollback_to(project_name: str, deployment_id: str) -> tuple[bool, str]:
    """Rollt zu einem früheren Deployment zurück."""
    deploy_path = DEPLOYMENTS_DIR / project_name / deployment_id

    if not deploy_path.exists():
        return False, f"Deployment {deployment_id} not found"

    # Finde das richtige Unterverzeichnis
    if (deploy_path / "public").exists():
        target = deploy_path / "public"
    elif (deploy_path / "app").exists():
        target = deploy_path / "app"
    else:
        return False, "Invalid deployment structure"

    # Symlink aktualisieren
    current_link = DEPLOYMENTS_DIR / project_name / "current"
    if current_link.is_symlink():
        current_link.unlink()
    current_link.symlink_to(target)

    # Deployment-Record aktualisieren
    deployments = get_deployments(project_name)
    for d in deployments:
        if d.id == deployment_id:
            d.status = "deployed"
        elif d.status == "deployed":
            d.status = "rolled_back"

    deploy_file = DEPLOYMENTS_DIR / project_name / "deployments.json"
    with open(deploy_file, "w") as f:
        json.dump([d.model_dump() for d in deployments], f, indent=2)

    return True, f"Rolled back to {deployment_id}"


# FastAPI App
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Ersatz Deploy Server starting...")
    yield
    print("Ersatz Deploy Server shutting down...")

app = FastAPI(title="Ersatz Deploy Server", version="1.0.0", lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "running", "version": "1.0.0"}


@app.get("/projects")
async def list_projects():
    """Listet alle konfigurierten Projekte."""
    return {"projects": {k: v.model_dump() for k, v in load_config().items()}}


@app.post("/projects")
async def add_project(config: ProjectConfig):
    """Fügt ein neues Projekt hinzu."""
    projects = load_config()
    projects[config.name] = config
    save_config(projects)
    return {"message": f"Project {config.name} added", "config": config.model_dump()}


@app.delete("/projects/{name}")
async def remove_project(name: str):
    """Entfernt ein Projekt."""
    projects = load_config()
    if name not in projects:
        raise HTTPException(404, "Project not found")
    del projects[name]
    save_config(projects)
    return {"message": f"Project {name} removed"}


@app.post("/webhook/{project_name}")
async def webhook(project_name: str, request: Request, background_tasks: BackgroundTasks):
    """Empfängt Git Webhooks und startet Deployment."""
    projects = load_config()
    if project_name not in projects:
        raise HTTPException(404, "Project not found")

    # Signatur prüfen (GitHub)
    signature = request.headers.get("X-Hub-Signature-256", "")
    body = await request.body()

    if WEBHOOK_SECRET != "change-me-in-production":
        if not verify_signature(body, signature):
            raise HTTPException(403, "Invalid signature")

    # Payload parsen
    try:
        payload = json.loads(body)
    except:
        payload = {}

    # Branch prüfen
    config = projects[project_name]
    ref = payload.get("ref", "")
    if ref and not ref.endswith(f"/{config.branch}"):
        return {"message": f"Ignored push to {ref}, watching {config.branch}"}

    # Deployment im Hintergrund starten
    background_tasks.add_task(execute_deployment, project_name)
    return {"message": f"Deployment started for {project_name}"}


@app.post("/deploy/{project_name}")
async def manual_deploy(project_name: str, background_tasks: BackgroundTasks):
    """Manuelles Deployment auslösen."""
    projects = load_config()
    if project_name not in projects:
        raise HTTPException(404, "Project not found")

    background_tasks.add_task(execute_deployment, project_name)
    return {"message": f"Manual deployment started for {project_name}"}


@app.get("/deployments/{project_name}")
async def list_deployments(project_name: str):
    """Listet alle Deployments eines Projekts."""
    return {"deployments": [d.model_dump() for d in get_deployments(project_name)]}


@app.post("/rollback/{project_name}/{deployment_id}")
async def rollback(project_name: str, deployment_id: str):
    """Rollt zu einem früheren Deployment zurück."""
    success, message = rollback_to(project_name, deployment_id)
    if not success:
        raise HTTPException(400, message)
    return {"message": message}


@app.get("/logs/{project_name}/{deployment_id}")
async def get_logs(project_name: str, deployment_id: str):
    """Holt die Logs eines Deployments."""
    log_file = LOGS_DIR / f"{project_name}_{deployment_id}.log"
    if not log_file.exists():
        raise HTTPException(404, "Logs not found")

    with open(log_file) as f:
        return {"logs": f.read()}


@app.get("/health")
async def health():
    """Health Check Endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)

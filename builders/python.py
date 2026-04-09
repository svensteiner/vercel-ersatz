"""
Python Builder - Für Python Web-Anwendungen (FastAPI, Flask, Django)
"""
import shutil
from pathlib import Path
from .base import BaseBuilder


class PythonBuilder(BaseBuilder):
    """Builder für Python Web-Anwendungen."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.framework = None
        self.wsgi_app = None
        self.asgi_app = None

    def detect_framework(self):
        """Erkennt das Python Framework."""
        repo = self.context.repo_path

        # Django
        if (repo / "manage.py").exists():
            self.framework = "django"
            # Django settings finden
            for settings in repo.rglob("settings.py"):
                parent = settings.parent.name
                self.wsgi_app = f"{parent}.wsgi:application"
                break
            self.log("Detected Django application")
            return

        # FastAPI oder Flask erkennen
        for py_file in repo.glob("*.py"):
            with open(py_file) as f:
                content = f.read()

            if "FastAPI()" in content or "from fastapi" in content:
                self.framework = "fastapi"
                self.asgi_app = f"{py_file.stem}:app"
                self.log(f"Detected FastAPI application in {py_file.name}")
                return

            if "Flask(__name__)" in content or "from flask" in content:
                self.framework = "flask"
                self.wsgi_app = f"{py_file.stem}:app"
                self.log(f"Detected Flask application in {py_file.name}")
                return

        # Fallback
        self.framework = "generic"
        self.log("No specific framework detected")

    def install_dependencies(self) -> tuple[bool, str]:
        """Installiert Python Dependencies."""
        repo = self.context.repo_path
        outputs = []

        # requirements.txt
        if (repo / "requirements.txt").exists():
            code, output = self.run_command("pip install -r requirements.txt")
            outputs.append(output)
            if code != 0:
                return False, "\n".join(outputs)

        # pyproject.toml mit Poetry
        elif (repo / "pyproject.toml").exists():
            if (repo / "poetry.lock").exists():
                code, output = self.run_command("poetry install --no-dev")
            else:
                code, output = self.run_command("pip install .")
            outputs.append(output)
            if code != 0:
                return False, "\n".join(outputs)

        # Pipfile
        elif (repo / "Pipfile").exists():
            code, output = self.run_command("pipenv install --deploy")
            outputs.append(output)
            if code != 0:
                return False, "\n".join(outputs)

        self.detect_framework()
        return True, "\n".join(outputs)

    def build(self) -> tuple[bool, str]:
        """Führt Framework-spezifische Build-Schritte aus."""
        repo = self.context.repo_path

        if self.framework == "django":
            # Django collectstatic
            code, output = self.run_command("python manage.py collectstatic --noinput")
            if code != 0:
                self.log("Warning: collectstatic failed, continuing anyway")

            # Migrations prüfen
            code, output = self.run_command("python manage.py migrate --check")
            if code != 0:
                self.log("Warning: Migrations pending")

            return True, "Django build completed"

        elif self.framework == "fastapi":
            # Keine speziellen Build-Schritte
            return True, "FastAPI ready"

        elif self.framework == "flask":
            # Flask Assets bauen falls vorhanden
            if (repo / "assets").exists():
                code, output = self.run_command("flask assets build")
                if code != 0:
                    self.log("Warning: Flask assets build failed")

            return True, "Flask ready"

        return True, "No build required"

    def prepare_output(self) -> tuple[bool, str]:
        """Bereitet das Python Deployment vor."""
        repo = self.context.repo_path
        output = self.context.output_path / "app"
        output.mkdir(parents=True, exist_ok=True)

        # Wichtige Dateien kopieren
        exclude = {".git", "__pycache__", ".env", "venv", ".venv", "env", ".pytest_cache", ".mypy_cache"}

        for item in repo.iterdir():
            if item.name in exclude:
                continue
            if item.name.startswith("."):
                continue

            dest = output / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True,
                               ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(item, dest)

        # Gunicorn/Uvicorn Config erstellen
        self._create_server_config(output.parent)

        # Systemd Service erstellen
        self._create_systemd_service(output.parent)

        return True, f"Output prepared at {output.parent}"

    def _create_server_config(self, output: Path):
        """Erstellt die Server-Konfiguration."""
        if self.framework == "fastapi":
            # Uvicorn Config
            config = output / "uvicorn_config.py"
            with open(config, "w") as f:
                f.write(f"""# Uvicorn Configuration
bind = "0.0.0.0:8000"
workers = 4
worker_class = "uvicorn.workers.UvicornWorker"
""")

            startup = output / "start.sh"
            with open(startup, "w") as f:
                f.write(f"""#!/bin/bash
cd app
uvicorn {self.asgi_app} --host 0.0.0.0 --port 8000 --workers 4
""")

        elif self.framework == "django":
            # Gunicorn Config
            config = output / "gunicorn.conf.py"
            with open(config, "w") as f:
                f.write(f"""# Gunicorn Configuration
bind = "0.0.0.0:8000"
workers = 4
worker_class = "sync"
timeout = 120
""")

            startup = output / "start.sh"
            with open(startup, "w") as f:
                f.write(f"""#!/bin/bash
cd app
gunicorn {self.wsgi_app} -c ../gunicorn.conf.py
""")

        elif self.framework == "flask":
            config = output / "gunicorn.conf.py"
            with open(config, "w") as f:
                f.write(f"""# Gunicorn Configuration
bind = "0.0.0.0:8000"
workers = 4
""")

            startup = output / "start.sh"
            with open(startup, "w") as f:
                f.write(f"""#!/bin/bash
cd app
gunicorn {self.wsgi_app} -c ../gunicorn.conf.py
""")

        else:
            # Generic Python
            startup = output / "start.sh"
            with open(startup, "w") as f:
                f.write("""#!/bin/bash
cd app
python main.py
""")

    def _create_systemd_service(self, output: Path):
        """Erstellt eine Systemd Service-Datei."""
        service = output / f"{self.context.project_name}.service"
        with open(service, "w") as f:
            f.write(f"""[Unit]
Description={self.context.project_name}
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory={output}/app
ExecStart=/bin/bash {output}/start.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
""")

    def get_start_command(self) -> str:
        """Gibt den Start-Befehl zurück."""
        if self.framework == "fastapi":
            return f"uvicorn {self.asgi_app} --host 0.0.0.0 --port 8000"
        elif self.framework == "django":
            return f"gunicorn {self.wsgi_app}"
        elif self.framework == "flask":
            return f"gunicorn {self.wsgi_app}"
        else:
            return "python main.py"

"""
Base Builder - Abstrakte Basisklasse für alle Builder
"""
import os
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class BuildContext:
    """Kontext für einen Build-Vorgang."""
    project_name: str
    repo_path: Path
    output_path: Path
    build_command: str
    output_dir: str
    env_vars: dict = field(default_factory=dict)
    log_file: Optional[Path] = None


@dataclass
class BuildResult:
    """Ergebnis eines Build-Vorgangs."""
    success: bool
    message: str
    output_path: Optional[Path] = None
    duration_seconds: float = 0.0
    logs: str = ""


class BaseBuilder(ABC):
    """Abstrakte Basisklasse für Framework-Builder."""

    def __init__(self, context: BuildContext):
        self.context = context
        self.start_time = None

    def log(self, message: str):
        """Schreibt eine Nachricht ins Log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}\n"

        if self.context.log_file:
            with open(self.context.log_file, "a") as f:
                f.write(line)
        print(line, end="")

    def run_command(self, cmd: str, cwd: Path = None) -> tuple[int, str]:
        """Führt einen Shell-Befehl aus."""
        work_dir = cwd or self.context.repo_path

        full_env = os.environ.copy()
        full_env.update(self.context.env_vars)

        self.log(f"Running: {cmd}")

        result = subprocess.run(
            cmd,
            shell=True,
            cwd=work_dir,
            capture_output=True,
            text=True,
            env=full_env
        )

        output = result.stdout + result.stderr
        return result.returncode, output

    def detect_package_manager(self) -> str:
        """Erkennt den verwendeten Package Manager."""
        repo = self.context.repo_path

        if (repo / "pnpm-lock.yaml").exists():
            return "pnpm"
        elif (repo / "yarn.lock").exists():
            return "yarn"
        elif (repo / "bun.lockb").exists():
            return "bun"
        else:
            return "npm"

    def get_install_command(self) -> str:
        """Gibt den Install-Befehl für den Package Manager zurück."""
        pm = self.detect_package_manager()

        commands = {
            "npm": "npm ci --prefer-offline" if (self.context.repo_path / "package-lock.json").exists() else "npm install",
            "yarn": "yarn install --frozen-lockfile",
            "pnpm": "pnpm install --frozen-lockfile",
            "bun": "bun install --frozen-lockfile"
        }

        return commands.get(pm, "npm install")

    @abstractmethod
    def install_dependencies(self) -> tuple[bool, str]:
        """Installiert Abhängigkeiten."""
        pass

    @abstractmethod
    def build(self) -> tuple[bool, str]:
        """Führt den Build aus."""
        pass

    @abstractmethod
    def prepare_output(self) -> tuple[bool, str]:
        """Bereitet die Output-Dateien vor."""
        pass

    def execute(self) -> BuildResult:
        """Führt den gesamten Build-Prozess aus."""
        self.start_time = datetime.now()
        logs = []

        self.log(f"=== Starting build for {self.context.project_name} ===")

        # 1. Dependencies installieren
        success, msg = self.install_dependencies()
        logs.append(msg)
        if not success:
            return self._result(False, "Dependency installation failed", logs)

        # 2. Build ausführen
        success, msg = self.build()
        logs.append(msg)
        if not success:
            return self._result(False, "Build failed", logs)

        # 3. Output vorbereiten
        success, msg = self.prepare_output()
        logs.append(msg)
        if not success:
            return self._result(False, "Output preparation failed", logs)

        self.log("=== Build completed successfully ===")
        return self._result(True, "Build successful", logs)

    def _result(self, success: bool, message: str, logs: list) -> BuildResult:
        """Erstellt ein BuildResult."""
        duration = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        return BuildResult(
            success=success,
            message=message,
            output_path=self.context.output_path if success else None,
            duration_seconds=duration,
            logs="\n".join(logs)
        )

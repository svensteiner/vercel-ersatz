"""
Static Builder - Für statische Websites (Vite, CRA, Vue, etc.)
"""
import shutil
from pathlib import Path
from .base import BaseBuilder


class StaticBuilder(BaseBuilder):
    """Builder für statische Websites."""

    def install_dependencies(self) -> tuple[bool, str]:
        """Installiert npm/yarn/pnpm Dependencies."""
        package_json = self.context.repo_path / "package.json"

        if not package_json.exists():
            self.log("No package.json found, skipping dependency installation")
            return True, "No dependencies to install"

        install_cmd = self.get_install_command()
        code, output = self.run_command(install_cmd)

        if code != 0:
            self.log(f"Dependency installation failed:\n{output}")
            return False, output

        self.log("Dependencies installed successfully")
        return True, output

    def build(self) -> tuple[bool, str]:
        """Führt den Build-Befehl aus."""
        if not self.context.build_command:
            self.log("No build command specified, skipping build step")
            return True, "No build required"

        code, output = self.run_command(self.context.build_command)

        if code != 0:
            self.log(f"Build failed:\n{output}")
            return False, output

        self.log("Build completed")
        return True, output

    def prepare_output(self) -> tuple[bool, str]:
        """Kopiert die Build-Ausgabe ins Deployment-Verzeichnis."""
        source = self.context.repo_path / self.context.output_dir

        if not source.exists():
            # Wenn kein Build-Output, nimm das ganze Repo
            if self.context.output_dir == ".":
                source = self.context.repo_path
            else:
                return False, f"Output directory {self.context.output_dir} not found"

        # Deployment-Verzeichnis erstellen
        self.context.output_path.mkdir(parents=True, exist_ok=True)

        # Dateien kopieren
        if source == self.context.repo_path:
            # Kopiere nur relevante Dateien
            for item in source.iterdir():
                if item.name in [".git", "node_modules", ".env", "__pycache__"]:
                    continue
                dest = self.context.output_path / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)
        else:
            shutil.copytree(source, self.context.output_path, dirs_exist_ok=True)

        self.log(f"Output prepared at {self.context.output_path}")
        return True, f"Copied to {self.context.output_path}"

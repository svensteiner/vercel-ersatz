"""
Node.js Builder - Für generische Node.js Server-Anwendungen
"""
import json
import shutil
from pathlib import Path
from .base import BaseBuilder


class NodeJSBuilder(BaseBuilder):
    """Builder für Node.js Server-Anwendungen."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_command = None
        self.main_file = None

    def detect_entry_point(self):
        """Erkennt den Einstiegspunkt der Anwendung."""
        repo = self.context.repo_path
        package_json = repo / "package.json"

        if package_json.exists():
            with open(package_json) as f:
                pkg = json.load(f)

            # Main-Datei aus package.json
            self.main_file = pkg.get("main", "index.js")

            # Start-Script
            scripts = pkg.get("scripts", {})
            if "start" in scripts:
                self.start_command = "npm start"
            elif "serve" in scripts:
                self.start_command = "npm run serve"
            else:
                self.start_command = f"node {self.main_file}"

        self.log(f"Entry point: {self.main_file}, Start: {self.start_command}")

    def install_dependencies(self) -> tuple[bool, str]:
        """Installiert Dependencies."""
        install_cmd = self.get_install_command()
        code, output = self.run_command(install_cmd)

        if code != 0:
            return False, output

        self.detect_entry_point()
        return True, output

    def build(self) -> tuple[bool, str]:
        """Führt den Build aus (falls vorhanden)."""
        if not self.context.build_command:
            # Prüfe ob ein Build-Script existiert
            package_json = self.context.repo_path / "package.json"
            if package_json.exists():
                with open(package_json) as f:
                    scripts = json.load(f).get("scripts", {})
                if "build" in scripts:
                    self.context.build_command = "npm run build"

        if self.context.build_command:
            code, output = self.run_command(self.context.build_command)
            if code != 0:
                return False, output

        return True, "Build completed"

    def prepare_output(self) -> tuple[bool, str]:
        """Bereitet das Node.js Deployment vor."""
        repo = self.context.repo_path
        output = self.context.output_path / "app"
        output.mkdir(parents=True, exist_ok=True)

        # Wichtige Dateien/Ordner kopieren
        include_items = [
            "package.json",
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "node_modules",
            "dist",
            "build",
            "lib",
            "src",
            "public",
            "views",
            "static",
        ]

        # Hauptdatei hinzufügen
        if self.main_file:
            include_items.append(self.main_file)

        for item in include_items:
            source = repo / item
            if source.exists():
                dest = output / item
                if source.is_dir():
                    shutil.copytree(source, dest, dirs_exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)

        # Alle .js, .ts, .json Dateien im Root
        for ext in ["*.js", "*.ts", "*.mjs", "*.cjs", "*.json"]:
            for file in repo.glob(ext):
                if file.name not in ["package.json", "package-lock.json"]:
                    shutil.copy2(file, output / file.name)

        # ecosystem.config.js für PM2 erstellen
        ecosystem = output.parent / "ecosystem.config.js"
        with open(ecosystem, "w") as f:
            f.write(f"""module.exports = {{
  apps: [{{
    name: "{self.context.project_name}",
    cwd: "./app",
    script: "{self.main_file or 'index.js'}",
    instances: "max",
    exec_mode: "cluster",
    env: {{
      NODE_ENV: "production"
    }}
  }}]
}};
""")

        self.log(f"Output prepared at {output.parent}")
        return True, f"Copied to {output.parent}"

    def get_start_command(self) -> str:
        """Gibt den Start-Befehl zurück."""
        return self.start_command or "npm start"

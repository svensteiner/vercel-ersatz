"""
Next.js Builder - Für Next.js Anwendungen mit SSR/SSG/ISR Support
"""
import json
import shutil
from pathlib import Path
from .base import BaseBuilder


class NextJSBuilder(BaseBuilder):
    """Builder für Next.js Anwendungen."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_app_router = False
        self.output_mode = "standalone"  # standalone, export, oder server

    def detect_nextjs_config(self):
        """Analysiert die Next.js Konfiguration."""
        repo = self.context.repo_path

        # App Router vs Pages Router
        self.is_app_router = (repo / "app").exists()

        # next.config.js/mjs analysieren
        for config_file in ["next.config.js", "next.config.mjs", "next.config.ts"]:
            config_path = repo / config_file
            if config_path.exists():
                with open(config_path) as f:
                    content = f.read()
                    if "output: 'export'" in content or 'output: "export"' in content:
                        self.output_mode = "export"
                    elif "output: 'standalone'" in content or 'output: "standalone"' in content:
                        self.output_mode = "standalone"
                break

        self.log(f"Detected Next.js config: router={'app' if self.is_app_router else 'pages'}, output={self.output_mode}")

    def install_dependencies(self) -> tuple[bool, str]:
        """Installiert Dependencies."""
        install_cmd = self.get_install_command()
        code, output = self.run_command(install_cmd)

        if code != 0:
            return False, output

        self.detect_nextjs_config()
        return True, output

    def build(self) -> tuple[bool, str]:
        """Führt next build aus."""
        build_cmd = self.context.build_command or "npm run build"
        code, output = self.run_command(build_cmd)

        if code != 0:
            return False, output

        self.log("Next.js build completed")
        return True, output

    def prepare_output(self) -> tuple[bool, str]:
        """Bereitet das Next.js Deployment vor."""
        repo = self.context.repo_path
        output = self.context.output_path
        output.mkdir(parents=True, exist_ok=True)

        if self.output_mode == "export":
            # Static Export (out/ Verzeichnis)
            source = repo / "out"
            if not source.exists():
                return False, "'out' directory not found. Ensure 'output: export' is set in next.config.js"

            shutil.copytree(source, output, dirs_exist_ok=True)
            self.log("Prepared static export")

        elif self.output_mode == "standalone":
            # Standalone Mode für Server-Deployment
            standalone_path = repo / ".next" / "standalone"

            if not standalone_path.exists():
                return False, "Standalone output not found. Add 'output: standalone' to next.config.js"

            # Standalone-Dateien kopieren
            shutil.copytree(standalone_path, output / "app", dirs_exist_ok=True)

            # Static Assets kopieren
            static_source = repo / ".next" / "static"
            if static_source.exists():
                shutil.copytree(static_source, output / "app" / ".next" / "static", dirs_exist_ok=True)

            # Public-Ordner kopieren
            public_source = repo / "public"
            if public_source.exists():
                shutil.copytree(public_source, output / "app" / "public", dirs_exist_ok=True)

            # Startup-Script erstellen
            startup_script = output / "start.sh"
            with open(startup_script, "w") as f:
                f.write("#!/bin/bash\n")
                f.write("cd app\n")
                f.write("node server.js\n")

            self.log("Prepared standalone deployment")

        else:
            # Standard Server-Deployment
            # Kopiere .next, public, package.json, node_modules

            for item in [".next", "public", "package.json", "package-lock.json", "node_modules"]:
                source = repo / item
                if source.exists():
                    dest = output / "app" / item
                    if source.is_dir():
                        shutil.copytree(source, dest, dirs_exist_ok=True)
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, dest)

            self.log("Prepared server deployment")

        return True, f"Output prepared at {output}"

    def get_start_command(self) -> str:
        """Gibt den Start-Befehl für die Anwendung zurück."""
        if self.output_mode == "export":
            return None  # Statische Dateien, kein Server nötig
        elif self.output_mode == "standalone":
            return "node server.js"
        else:
            return "npm start"

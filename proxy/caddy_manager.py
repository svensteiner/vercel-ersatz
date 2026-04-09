"""
Caddy Manager - Verwaltet Caddy-Konfiguration für HTTPS und Routing
"""
import os
import json
import subprocess
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class SiteConfig:
    """Konfiguration für eine Website."""
    domain: str
    project_name: str
    project_type: str
    static_path: Optional[Path] = None
    proxy_port: Optional[int] = None
    ssl_email: Optional[str] = None


class CaddyManager:
    """Verwaltet Caddy-Konfigurationen für Ersatz."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.caddy_dir = base_dir / "caddy"
        self.sites_dir = self.caddy_dir / "sites"
        self.caddyfile = self.caddy_dir / "Caddyfile"

        self.caddy_dir.mkdir(parents=True, exist_ok=True)
        self.sites_dir.mkdir(parents=True, exist_ok=True)

    def generate_site_config(self, config: SiteConfig) -> str:
        """Generiert die Caddy-Konfiguration für eine Site."""
        if config.project_type == "static":
            return self._static_config(config)
        else:
            return self._proxy_config(config)

    def _static_config(self, config: SiteConfig) -> str:
        """Generiert Konfiguration für statische Sites."""
        return f"""{config.domain} {{
    root * {config.static_path}
    file_server

    # Kompression
    encode gzip zstd

    # SPA Fallback
    try_files {{path}} /index.html

    # Caching für Assets
    @assets {{
        path *.js *.css *.woff2 *.woff *.ttf *.ico *.png *.jpg *.jpeg *.gif *.svg *.webp
    }}
    header @assets Cache-Control "public, max-age=31536000, immutable"

    # Kein Cache für HTML
    @html {{
        path *.html /
    }}
    header @html Cache-Control "no-cache, no-store, must-revalidate"

    # Security Headers
    header {{
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        X-XSS-Protection "1; mode=block"
        Referrer-Policy strict-origin-when-cross-origin
        -Server
    }}

    # Logging
    log {{
        output file {self.base_dir}/logs/access-{config.project_name}.log {{
            roll_size 10mb
            roll_keep 5
        }}
    }}
}}
"""

    def _proxy_config(self, config: SiteConfig) -> str:
        """Generiert Konfiguration für Proxy Sites."""
        return f"""{config.domain} {{
    reverse_proxy localhost:{config.proxy_port} {{
        # Health Checks
        health_uri /health
        health_interval 30s
        health_timeout 5s

        # Load Balancing Headers
        header_up X-Real-IP {{remote_host}}
        header_up X-Forwarded-For {{remote_host}}
        header_up X-Forwarded-Proto {{scheme}}
    }}

    # Kompression
    encode gzip zstd

    # Security Headers
    header {{
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        X-XSS-Protection "1; mode=block"
        Referrer-Policy strict-origin-when-cross-origin
        -Server
    }}

    # Logging
    log {{
        output file {self.base_dir}/logs/access-{config.project_name}.log {{
            roll_size 10mb
            roll_keep 5
        }}
    }}
}}
"""

    def add_site(self, config: SiteConfig):
        """Fügt eine Site zur Caddy-Konfiguration hinzu."""
        site_file = self.sites_dir / f"{config.project_name}.caddy"
        site_config = self.generate_site_config(config)

        with open(site_file, "w") as f:
            f.write(site_config)

        self._regenerate_caddyfile()

    def remove_site(self, project_name: str):
        """Entfernt eine Site aus der Caddy-Konfiguration."""
        site_file = self.sites_dir / f"{project_name}.caddy"
        if site_file.exists():
            site_file.unlink()
            self._regenerate_caddyfile()

    def _regenerate_caddyfile(self):
        """Regeneriert das Haupt-Caddyfile."""
        imports = []

        for site_file in self.sites_dir.glob("*.caddy"):
            imports.append(f"import {site_file}")

        caddyfile_content = f"""# Ersatz Caddyfile - Auto-generated
# Do not edit manually

# Global options
{{
    email {os.getenv("SSL_EMAIL", "admin@example.com")}
    admin off
}}

# Import site configurations
{chr(10).join(imports)}

# Fallback for unknown domains
:80 {{
    respond "Ersatz - Domain not configured" 404
}}
"""

        with open(self.caddyfile, "w") as f:
            f.write(caddyfile_content)

    def reload(self) -> tuple[bool, str]:
        """Lädt die Caddy-Konfiguration neu."""
        try:
            result = subprocess.run(
                ["caddy", "reload", "--config", str(self.caddyfile)],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return True, "Caddy reloaded successfully"
            else:
                return False, result.stderr
        except FileNotFoundError:
            return False, "Caddy not found"
        except Exception as e:
            return False, str(e)

    def validate(self) -> tuple[bool, str]:
        """Validiert die Caddy-Konfiguration."""
        try:
            result = subprocess.run(
                ["caddy", "validate", "--config", str(self.caddyfile)],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return True, "Configuration valid"
            else:
                return False, result.stderr
        except FileNotFoundError:
            return False, "Caddy not found"
        except Exception as e:
            return False, str(e)

    def sync_from_config(self, config_path: Path):
        """Synchronisiert Sites aus der Ersatz-Konfiguration."""
        if not config_path.exists():
            return

        with open(config_path) as f:
            config = json.load(f)

        deployments_dir = self.base_dir / "deployments"

        # Alle Sites hinzufügen
        for name, project in config.get("projects", {}).items():
            domain = project.get("domain")
            if not domain:
                continue

            project_type = project.get("project_type", "static")

            if project_type == "static":
                static_path = deployments_dir / name / "current"
                site_config = SiteConfig(
                    domain=domain,
                    project_name=name,
                    project_type="static",
                    static_path=static_path
                )
            else:
                port = project.get("port", 3000)
                site_config = SiteConfig(
                    domain=domain,
                    project_name=name,
                    project_type="proxy",
                    proxy_port=port
                )

            self.add_site(site_config)

        # Reload
        self.reload()


def main():
    """CLI für den Caddy Manager."""
    import argparse

    parser = argparse.ArgumentParser(description="Caddy Manager for Ersatz")
    parser.add_argument("command", choices=["sync", "reload", "validate"])
    parser.add_argument("--base-dir", default="/var/ersatz", help="Base directory")

    args = parser.parse_args()
    base_dir = Path(args.base_dir)

    manager = CaddyManager(base_dir)

    if args.command == "sync":
        config_path = base_dir / "config.json"
        manager.sync_from_config(config_path)
        print("Sites synchronized")

    elif args.command == "reload":
        success, msg = manager.reload()
        print(msg)

    elif args.command == "validate":
        success, msg = manager.validate()
        print(msg)


if __name__ == "__main__":
    main()

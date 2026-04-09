"""
Ersatz Router - Dynamisches Routing für Deployments
"""
import os
import json
import asyncio
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
import aiohttp
from aiohttp import web


@dataclass
class RouteConfig:
    """Konfiguration für eine Route."""
    domain: str
    project_name: str
    target_type: str  # "static" oder "proxy"
    target_path: Optional[Path] = None  # Für static
    target_url: Optional[str] = None    # Für proxy
    ssl_enabled: bool = False


class Router:
    """Dynamischer Router für Ersatz Deployments."""

    def __init__(self, config_path: Path, deployments_path: Path):
        self.config_path = config_path
        self.deployments_path = deployments_path
        self.routes: dict[str, RouteConfig] = {}
        self.session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        """Startet den Router."""
        self.session = aiohttp.ClientSession()
        await self.reload_routes()

    async def stop(self):
        """Stoppt den Router."""
        if self.session:
            await self.session.close()

    async def reload_routes(self):
        """Lädt die Routing-Konfiguration neu."""
        if not self.config_path.exists():
            return

        with open(self.config_path) as f:
            config = json.load(f)

        self.routes.clear()

        for name, project in config.get("projects", {}).items():
            domain = project.get("domain")
            if not domain:
                continue

            project_type = project.get("project_type", "static")
            current_link = self.deployments_path / name / "current"

            if project_type == "static":
                self.routes[domain] = RouteConfig(
                    domain=domain,
                    project_name=name,
                    target_type="static",
                    target_path=current_link if current_link.exists() else None
                )
            else:
                port = project.get("port", 3000)
                self.routes[domain] = RouteConfig(
                    domain=domain,
                    project_name=name,
                    target_type="proxy",
                    target_url=f"http://127.0.0.1:{port}"
                )

    def get_route(self, host: str) -> Optional[RouteConfig]:
        """Findet die passende Route für einen Host."""
        # Exakter Match
        if host in self.routes:
            return self.routes[host]

        # Ohne Port
        host_no_port = host.split(":")[0]
        if host_no_port in self.routes:
            return self.routes[host_no_port]

        # Wildcard-Match (*.example.com)
        for domain, route in self.routes.items():
            if domain.startswith("*."):
                base = domain[2:]
                if host_no_port.endswith(base):
                    return route

        return None


class ProxyMiddleware:
    """Middleware für Reverse Proxy Funktionalität."""

    def __init__(self, router: Router):
        self.router = router

    async def handle_proxy(self, request: web.Request, route: RouteConfig) -> web.Response:
        """Proxied eine Anfrage an den Backend-Server."""
        target_url = f"{route.target_url}{request.path_qs}"

        try:
            async with self.router.session.request(
                method=request.method,
                url=target_url,
                headers={k: v for k, v in request.headers.items()
                        if k.lower() not in ["host", "content-length"]},
                data=await request.read() if request.can_read_body else None,
                allow_redirects=False
            ) as response:
                body = await response.read()

                return web.Response(
                    status=response.status,
                    body=body,
                    headers={k: v for k, v in response.headers.items()
                            if k.lower() not in ["content-encoding", "transfer-encoding", "content-length"]}
                )
        except aiohttp.ClientError as e:
            return web.Response(status=502, text=f"Bad Gateway: {str(e)}")

    async def handle_static(self, request: web.Request, route: RouteConfig) -> web.Response:
        """Serviert statische Dateien."""
        if not route.target_path or not route.target_path.exists():
            return web.Response(status=404, text="Deployment not found")

        # Pfad normalisieren
        path = request.path.lstrip("/")
        if not path:
            path = "index.html"

        file_path = route.target_path / path

        # Security: Path Traversal verhindern
        try:
            file_path = file_path.resolve()
            route.target_path.resolve()
            if not str(file_path).startswith(str(route.target_path.resolve())):
                return web.Response(status=403, text="Forbidden")
        except (ValueError, OSError):
            return web.Response(status=400, text="Bad Request")

        # Datei oder index.html in Verzeichnis
        if file_path.is_dir():
            file_path = file_path / "index.html"

        if not file_path.exists():
            # SPA Fallback
            index_html = route.target_path / "index.html"
            if index_html.exists():
                file_path = index_html
            else:
                return web.Response(status=404, text="Not Found")

        # MIME Type bestimmen
        import mimetypes
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = "application/octet-stream"

        # Datei lesen und zurückgeben
        with open(file_path, "rb") as f:
            content = f.read()

        headers = {
            "Content-Type": mime_type,
            "Cache-Control": "public, max-age=31536000" if "." in path and path != "index.html" else "no-cache"
        }

        return web.Response(body=content, headers=headers)

    @web.middleware
    async def middleware(self, request: web.Request, handler):
        """Routing Middleware."""
        host = request.headers.get("Host", "")
        route = self.router.get_route(host)

        if not route:
            # Kein Routing gefunden, weiter zur App
            return await handler(request)

        if route.target_type == "proxy":
            return await self.handle_proxy(request, route)
        else:
            return await self.handle_static(request, route)


async def create_app(config_path: Path, deployments_path: Path) -> web.Application:
    """Erstellt die aiohttp Application."""
    router = Router(config_path, deployments_path)
    proxy_mw = ProxyMiddleware(router)

    app = web.Application(middlewares=[proxy_mw.middleware])

    async def on_startup(app):
        await router.start()

    async def on_cleanup(app):
        await router.stop()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    # Health Check
    async def health(request):
        return web.json_response({"status": "healthy"})

    app.router.add_get("/_health", health)

    # Route Reload Endpoint
    async def reload_routes(request):
        await router.reload_routes()
        return web.json_response({"message": "Routes reloaded", "count": len(router.routes)})

    app.router.add_post("/_reload", reload_routes)

    return app


def main():
    """Startet den Proxy Server."""
    base_dir = Path(os.getenv("ERSATZ_BASE_DIR", "/var/ersatz"))
    config_path = base_dir / "config.json"
    deployments_path = base_dir / "deployments"

    app = asyncio.get_event_loop().run_until_complete(
        create_app(config_path, deployments_path)
    )

    web.run_app(app, host="0.0.0.0", port=80)


if __name__ == "__main__":
    main()

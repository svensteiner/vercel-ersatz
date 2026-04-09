"""
Ersatz Proxy - Routing und Caddy Management
"""
from .router import Router, ProxyMiddleware, create_app
from .caddy_manager import CaddyManager, SiteConfig

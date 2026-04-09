"""
Ersatz Builders - Framework-spezifische Build-Module
"""
from .base import BaseBuilder
from .static import StaticBuilder
from .nextjs import NextJSBuilder
from .nodejs import NodeJSBuilder
from .python import PythonBuilder

BUILDERS = {
    "static": StaticBuilder,
    "nextjs": NextJSBuilder,
    "nodejs": NodeJSBuilder,
    "python": PythonBuilder,
}


def get_builder(project_type: str) -> type[BaseBuilder]:
    """Gibt den passenden Builder für einen Projekttyp zurück."""
    return BUILDERS.get(project_type, StaticBuilder)

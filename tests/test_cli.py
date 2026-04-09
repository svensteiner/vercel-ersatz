"""Tests für das CLI."""
import pytest
from pathlib import Path
import tempfile
import json

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from cli.ersatz import detect_framework


def test_detect_nextjs():
    """Test Next.js Erkennung."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        package_json = {
            "name": "test",
            "dependencies": {
                "next": "14.0.0",
                "react": "18.0.0"
            }
        }
        (project_dir / "package.json").write_text(json.dumps(package_json))

        result = detect_framework(project_dir)
        assert result["framework"] == "Next.js"
        assert result["project_type"] == "nextjs"


def test_detect_vite():
    """Test Vite Erkennung."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        package_json = {
            "name": "test",
            "devDependencies": {
                "vite": "5.0.0"
            }
        }
        (project_dir / "package.json").write_text(json.dumps(package_json))

        result = detect_framework(project_dir)
        assert result["framework"] == "Vite"
        assert result["project_type"] == "static"


def test_detect_django():
    """Test Django Erkennung."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        (project_dir / "requirements.txt").write_text("django>=4.0")
        (project_dir / "manage.py").write_text("#!/usr/bin/env python")

        result = detect_framework(project_dir)
        assert result["framework"] == "Django"
        assert result["project_type"] == "python"


def test_detect_static_html():
    """Test statische HTML Erkennung."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        (project_dir / "index.html").write_text("<html></html>")

        result = detect_framework(project_dir)
        assert result["framework"] == "Static HTML"
        assert result["project_type"] == "static"

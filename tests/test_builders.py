"""Tests für die Builder-Module."""
import pytest
from pathlib import Path
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from builders.base import BuildContext
from builders.static import StaticBuilder


@pytest.fixture
def temp_project():
    """Erstellt ein temporäres Projekt-Verzeichnis."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "project"
        project_dir.mkdir()

        # Einfache index.html erstellen
        (project_dir / "index.html").write_text("<html><body>Test</body></html>")

        output_dir = Path(tmpdir) / "output"

        yield project_dir, output_dir


def test_static_builder_no_package_json(temp_project):
    """Test StaticBuilder ohne package.json."""
    project_dir, output_dir = temp_project

    context = BuildContext(
        project_name="test",
        repo_path=project_dir,
        output_path=output_dir,
        build_command="",
        output_dir="."
    )

    builder = StaticBuilder(context)

    # Install sollte erfolgreich sein (nichts zu installieren)
    success, msg = builder.install_dependencies()
    assert success

    # Build sollte erfolgreich sein (kein Build-Befehl)
    success, msg = builder.build()
    assert success


def test_static_builder_prepare_output(temp_project):
    """Test StaticBuilder Output-Vorbereitung."""
    project_dir, output_dir = temp_project

    context = BuildContext(
        project_name="test",
        repo_path=project_dir,
        output_path=output_dir,
        build_command="",
        output_dir="."
    )

    builder = StaticBuilder(context)
    builder.install_dependencies()
    builder.build()
    success, msg = builder.prepare_output()

    assert success
    assert (output_dir / "index.html").exists()

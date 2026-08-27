"""Regression checks for the Raspberry Pi appliance release layout."""

from __future__ import annotations

from pathlib import Path
import stat
import tomllib

from growasist import __version__


ROOT = Path(__file__).resolve().parents[1]


def _text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_package_versions_match() -> None:
    project = tomllib.loads(_text("pyproject.toml"))
    assert project["project"]["version"] == __version__


def test_appliance_runs_only_the_current_release() -> None:
    service = _text("image/assets/growasist.service")
    backup = _text("image/assets/growasist-backup")
    control = _text("image/assets/growasistctl")
    assert "WorkingDirectory=/opt/growasist/current" in service
    assert "PYTHONPATH=/opt/growasist/current" in service
    assert "PYTHONPATH=/opt/growasist/current" in backup
    assert "PYTHONPATH=/opt/growasist/current" in control


def test_release_activation_is_backup_and_preflight_gated() -> None:
    manager = _text("image/assets/growasist-release-manager")
    backup = manager.index("backup_path=$(/usr/local/libexec/growasist-backup)")
    preflight = manager.index('preflight_release "$candidate" "$backup_path"')
    activate = manager.index('atomic_link "$candidate" "$current_link"')
    assert backup < preflight < activate
    assert 'echo "Health check failed; restoring previous release"' in manager
    assert 'atomic_link "$old_release" "$current_link"' in manager


def test_image_contains_release_and_sync_dependencies() -> None:
    layer = _text("image/layer/growasist-core.yaml")
    assert "- rsync" in layer
    assert 'release_name="image-${IGconf_artefact_version}"' in layer
    assert 'ln -s "releases/$release_name"' in layer
    assert '"$assets/growasist-release-manager"' in layer


def test_operational_scripts_are_executable() -> None:
    paths = (
        "image/assets/growasist-release-manager",
        "image/assets/growasist-backup",
        "image/assets/growasistctl",
        "scripts/deploy-dev.sh",
        "tests/appliance_release_manager_smoke.sh",
    )
    for relative_path in paths:
        mode = (ROOT / relative_path).stat().st_mode
        assert mode & stat.S_IXUSR, relative_path

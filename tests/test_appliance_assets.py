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


def test_appliance_uses_standard_http_without_running_as_root() -> None:
    service = _text("image/assets/growasist.service")
    discovery = _text("image/assets/growasist-avahi.service")
    manager = _text("image/assets/growasist-release-manager")
    assert "User=growasist" in service
    assert "--port 80" in service
    assert "AmbientCapabilities=CAP_NET_BIND_SERVICE" in service
    assert "CapabilityBoundingSet=CAP_NET_BIND_SERVICE" in service
    assert "<port>80</port>" in discovery
    assert "health_url=http://127.0.0.1/api/v1/health" in manager


def test_appliance_starts_after_first_boot_is_already_complete() -> None:
    service = _text("image/assets/growasist.service")
    assert "Wants=growasist-firstboot.service" in service
    assert "Requires=growasist-firstboot.service" not in service
    assert "network-online.target" not in service


def test_release_activation_is_backup_and_preflight_gated() -> None:
    manager = _text("image/assets/growasist-release-manager")
    backup = manager.index("backup_path=$(/usr/local/libexec/growasist-backup)")
    preflight = manager.index('preflight_release "$candidate" "$backup_path"')
    activate = manager.index('atomic_link "$candidate" "$current_link"')
    assert backup < preflight < activate
    assert 'echo "Health check failed; restoring previous release"' in manager
    assert 'atomic_link "$old_release" "$current_link"' in manager


def test_development_release_root_is_traversable_by_service_user() -> None:
    deploy = _text("scripts/deploy-dev.sh")
    assert "sudo chmod 0755 '$remote_release'" in deploy


def test_image_contains_release_and_sync_dependencies() -> None:
    layer = _text("image/layer/growasist-core.yaml")
    assert "- rsync" in layer
    assert 'release_name="image-${IGconf_artefact_version}"' in layer
    assert 'ln -s "releases/$release_name"' in layer
    assert '"$assets/growasist-release-manager"' in layer
    assert '"$assets/growasist-i2c.conf" "$1/etc/modules-load.d/"' in layer
    assert _text("image/assets/growasist-i2c.conf").strip() == "i2c-dev"
    assert "After=systemd-modules-load.service" in _text("image/assets/growasist.service")


def test_setup_tools_remain_visible_and_addressable() -> None:
    shell = _text("growasist/web/index.html")
    application = _text("growasist/web/app.js")
    for module in ("overview", "plants", "nutrients", "hardware", "iot"):
        assert f'data-setup-shortcut="{module}"' in shell
        assert f'"{module}"' in application
    assert 'data-view="dosing"' in shell
    assert 'data-setup-shortcut="dosing"' not in shell
    assert 'data-setup-shortcut="profiles"' not in shell
    assert "state.profiles?.[stage]?.nutrient_ids" not in application
    assert "Hazır program kütüphanesi" in application
    assert "Ürün kütüphanesi" in application
    assert "Benim ürünlerim" in application
    assert "/api/v1/nutrients/catalog/add" in application
    assert "/api/v1/nutrient-programs/add" in application
    assert "/api/v1/i2c/discover" in application
    assert "/api/v1/i2c/enroll" in application
    assert "/api/v1/i2c/remove" in application
    assert "function renderIoT" in application
    assert "YEREL AĞ ENVANTERİ" in application
    assert "/api/v1/dosing/calibration/start" in application
    assert "data-add-hardware" not in application
    assert "I²C adresi" not in application
    assert "Ölçülen hacim · ml" in application
    assert "data-start-program" in application
    assert "Aşama hedefleri" in application
    assert "stageNutrientFields" not in application
    assert "#setup/${setupView || currentSetupView}" in application
    assert "Kütüphane" in shell
    assert "Sistem" in shell
    assert "Genel Bakış" in shell
    for technical_copy in ("Home Assistant kullanılmıyor", "Raspberry Pi üzerinde", "SQLITE"):
        assert technical_copy not in shell + application


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

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts.packaging.package import LIGHTROOM_LUA_PACKAGE, Packager


def test_pyinstaller_command_collects_lightroom_lua_package(monkeypatch: pytest.MonkeyPatch) -> None:
    commands = []
    monkeypatch.setattr(sys, "argv", ["package.py", "--platform", "windows"])
    monkeypatch.setattr(Packager, "_icon_args", lambda _self: [])
    monkeypatch.setattr(Packager, "_run", lambda _self, command: commands.append(command))

    packager = Packager()
    packager._run_pyinstaller()

    command = commands[0]
    assert command[command.index("--hidden-import") + 1] == LIGHTROOM_LUA_PACKAGE
    assert command[command.index("--collect-data") + 1] == LIGHTROOM_LUA_PACKAGE
    assert f"runtime_config.json{packager.separator}." in command
    assert f"resources{packager.separator}resources" in command
    assert f"models{packager.separator}models" not in command


def test_package_verifies_release_model_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    models = tmp_path / "resources" / "models"
    models.mkdir(parents=True)
    monkeypatch.setattr(sys, "argv", ["package.py", "--platform", "windows"])
    monkeypatch.setattr(Packager, "ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="resources/models"):
        Packager()._verify_model_package_files()


def test_package_can_write_exact_release_version(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    package_json = tmp_path / "package.json"
    package_lock = tmp_path / "package-lock.json"
    init_path = tmp_path / "backend" / "bird_desktop" / "__init__.py"
    init_path.parent.mkdir(parents=True)
    package_json.write_text(json.dumps({"version": "0.1.21"}), encoding="utf-8")
    package_lock.write_text(json.dumps({"version": "0.1.21", "packages": {"": {"version": "0.1.21"}}}), encoding="utf-8")
    init_path.write_text('__version__ = "0.1.21"\n', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["package.py", "--platform", "windows", "--version", "1.2.3"])
    monkeypatch.setattr(Packager, "ROOT", tmp_path)

    version = Packager()._write_release_version("1.2.3")

    assert version == "1.2.3"
    assert json.loads(package_json.read_text(encoding="utf-8"))["version"] == "1.2.3"
    assert json.loads(package_lock.read_text(encoding="utf-8"))["packages"][""]["version"] == "1.2.3"
    assert init_path.read_text(encoding="utf-8") == '__version__ = "1.2.3"\n'


def test_windows_installer_has_update_mode() -> None:
    contents = (Path(__file__).resolve().parents[1] / "installer" / "windows" / "AvesCaesar.iss").read_text(encoding="utf-8")

    assert "function IsUpdateInstall" in contents
    assert "CloseApplications=yes" in contents
    assert "RestartApplications=no" in contents
    assert 'Name: "{app}\\*"; Check: IsUpdateInstall' in contents
    assert 'Excludes: "_internal\\resources\\models\\*"' in contents
    assert 'DestDir: "{app}\\_internal\\resources\\models"' in contents
    assert "ShouldCreateDesktopIcon" in contents
    assert 'Description: "{cm:LaunchProgram,Aves Caesar}"; Flags: nowait postinstall skipifsilent' in contents
    assert "ShouldLaunchAfterSilentUpdate" in contents
    assert 'Flags: nowait skipifnotsilent; Check: ShouldLaunchAfterSilentUpdate' in contents
    assert "DELETEINSTALLER" in contents
    assert "Aves Caesar\\cache\\updates" in contents

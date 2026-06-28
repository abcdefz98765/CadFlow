import pytest

from ai_native_cad.freecad_paths import add_freecad_to_path, find_freecad_paths


class TestFindFreecadPaths:
    def test_returns_none_when_not_installed(self, monkeypatch):
        monkeypatch.delenv("FREECAD_HOME", raising=False)
        monkeypatch.setattr("ai_native_cad.freecad_paths.shutil.which", lambda command: None)
        monkeypatch.setattr("ai_native_cad.freecad_paths.Path.exists", lambda self: False)
        result = find_freecad_paths()
        assert result is None


class TestAddFreecadToPath:
    def test_raises_when_none(self):
        with pytest.raises(RuntimeError, match="FreeCAD not found"):
            add_freecad_to_path(None)

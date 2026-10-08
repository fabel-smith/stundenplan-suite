"""Keep the documented Schulmanager prerequisite aligned with the selector."""
import json
from pathlib import Path


def test_schulmanager_setup_documents_selected_integration():
    root = Path(__file__).resolve().parents[1]
    component = root / "custom_components" / "stundenplan24_week"
    readme = (root / "README.md").read_text(encoding="utf-8")
    flow = (component / "config_flow.py").read_text(encoding="utf-8")
    manifest = json.loads((component / "manifest.json").read_text(encoding="utf-8"))
    assert 'integration="schulmanager"' in flow
    assert "schulmanager" in manifest["after_dependencies"]
    assert "https://github.com/MrIcemanLE/Schulmanager-homeassistant" in readme
    assert "`schulmanager_online`" in readme
    assert "nicht angeboten" in readme

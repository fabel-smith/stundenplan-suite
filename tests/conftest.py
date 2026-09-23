"""Load pure modules without importing the HA integration entry point."""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "stundenplan24_week"
package = types.ModuleType("stundenplan24_week")
package.__path__ = [str(COMPONENT)]
sys.modules["stundenplan24_week"] = package

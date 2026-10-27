"""读取 packages/protocols 的跨语言协议；安装版读取打包副本。"""
import json
import sys
from pathlib import Path

root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[4]))
file = root / ("protocols/protocol.json" if getattr(sys, "frozen", False) else "packages/protocols/protocol.json")
PROTOCOL = json.loads(file.read_text(encoding="utf-8"))
METHODS = frozenset(PROTOCOL["methods"])
CONTROL = PROTOCOL["control"]
LIMITS = PROTOCOL["limits"]
ERRORS = PROTOCOL["errors"]

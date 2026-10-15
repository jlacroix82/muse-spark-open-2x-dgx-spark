#!/usr/bin/env python3
"""Summarize fwupd device firmware state (BIOS/EC/UEFI + any pending release)."""
import json
import subprocess

raw = subprocess.run(["fwupdmgr", "get-devices", "--json"], capture_output=True, text=True, timeout=120).stdout
d = json.loads(raw)
for dev in d.get("Devices", []):
    name = dev.get("Name", "")
    if any(k in name for k in ("System Firmware", "Embedded Controller", "BIOS", "UEFI", "Retimer", "PD ")):
        rels = dev.get("Releases") or []
        print("  {:46s} current={}".format(name[:44], dev.get("Version")))
        for r in rels[:2]:
            print("        available: {}  urgency={}".format(r.get("Version"), r.get("Urgency")))
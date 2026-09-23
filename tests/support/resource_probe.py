"""Bounded metadata for owned stability containers, never dump file contents."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["backend", "simulator"], required=True)
    role = parser.parse_args().role
    root = Path("/data" if role == "backend" else "/simulator-state")
    files = {
        p.name: p.stat().st_size
        for p in root.glob("*.db*" if role == "backend" else "*.json")
        if p.is_file()
    }
    result = {"files_bytes": files, "total_bytes": sum(files.values())}
    if role == "simulator":
        result["pending_reports"] = {
            p.name: len(json.loads(p.read_text()).get("pending_reports", []))
            for p in root.glob("*.json")
        }
    print(json.dumps(result))


if __name__ == "__main__":
    main()

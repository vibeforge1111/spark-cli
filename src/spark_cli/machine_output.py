from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


OS_OUTPUT_REQUIRES_JSON = "--output requires --json for Spark OS authority and trace reports."


def resolve_os_json_output_path(
    *,
    json_output: bool,
    output: str | None,
    validate_path: Callable[[Path], None],
    reject_linked_path: Callable[[Path], None],
) -> Path | None:
    if not output:
        return None
    if not json_output:
        raise SystemExit(OS_OUTPUT_REQUIRES_JSON)
    path = Path(output).expanduser()
    reject_linked_path(path)
    validate_path(path)
    return path


def emit_json_payload(
    payload: dict[str, Any],
    *,
    output_path: Path | None,
    write_text: Callable[[Path, str], None],
) -> None:
    rendered = json.dumps(payload, indent=2)
    if output_path is None:
        print(rendered)
        return
    write_text(output_path, rendered + "\n")


def render_module_listing(
    modules: dict[str, Any],
    *,
    registry_modules: dict[str, Any],
    installed: dict[str, Any],
    json_output: bool,
) -> str:
    if not modules:
        if json_output:
            return json.dumps({"ok": True, "count": 0, "modules": []}, indent=2)
        return "No installed Spark modules recorded.\nRun `spark setup telegram-starter` to install the starter bundle."
    rows = []
    for module in modules.values():
        metadata = registry_modules.get(module.name, {})
        rows.append(
            {
                "name": module.name,
                "version": module.version,
                "kind": module.kind,
                "plane": module.plane,
                "blessed": bool(metadata.get("blessed")),
                "installed": module.name in installed,
            }
        )
    rows.sort(key=lambda row: row["name"])
    if json_output:
        return json.dumps({"ok": True, "count": len(rows), "modules": rows}, indent=2)
    return "\n".join(
        f"{row['name']}\t{row['version']}\t{row['kind']}\t{row['plane']}\t"
        f"{'yes' if row['blessed'] else 'no'}\t{'installed' if row['installed'] else 'available'}"
        for row in rows
    )

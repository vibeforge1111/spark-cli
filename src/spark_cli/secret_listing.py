from __future__ import annotations

import json


def render_stored_secret_listing(index: dict[str, str], *, json_output: bool) -> str:
    items = sorted(index.items())
    if json_output:
        payload = {
            "ok": True,
            "count": len(items),
            "secrets": [{"id": secret_id, "backend": backend} for secret_id, backend in items],
        }
        return json.dumps(payload, indent=2)
    if not items:
        return "No stored secrets."
    noun = "secret" if len(items) == 1 else "secrets"
    lines = [f"{len(items)} {noun} stored:"]
    lines.extend(f"  {secret_id}\t[{backend}]" for secret_id, backend in items)
    return "\n".join(lines)

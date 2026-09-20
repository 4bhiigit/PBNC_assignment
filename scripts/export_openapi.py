"""Exports FastAPI OpenAPI specification to openapi.json and docs/openapi.json."""

import json
from pathlib import Path

from app.main import app


def export_openapi() -> None:
    schema = app.openapi()
    formatted = json.dumps(schema, indent=2)

    root_path = Path("openapi.json")
    docs_path = Path("docs/openapi.json")

    root_path.write_text(formatted, encoding="utf-8")
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    docs_path.write_text(formatted, encoding="utf-8")

    print(f"Exported OpenAPI schema to {root_path} and {docs_path} ({len(formatted)} bytes)")


if __name__ == "__main__":
    export_openapi()

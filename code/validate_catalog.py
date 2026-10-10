import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

if len(sys.argv) != 2:
    print("Usage: python3 code/validate_catalog.py <catalog.json>")
    sys.exit(2)

catalog_path = Path(sys.argv[1])
schema_path = Path("schemas/metadata_catalog_schema.json")

with schema_path.open("r", encoding="utf-8") as f:
    schema = json.load(f)

with catalog_path.open("r", encoding="utf-8") as f:
    catalog = json.load(f)

validator = Draft202012Validator(
    schema,
    format_checker=FormatChecker()
)

errors = sorted(
    validator.iter_errors(catalog),
    key=lambda e: list(e.path)
)

if errors:
    print("CATALOG VALIDATION: FAIL")

    for error in errors:
        path = ".".join(str(x) for x in error.path)
        print(f"- {path or '<root>'}: {error.message}")

    sys.exit(1)

print("CATALOG VALIDATION: PASS")
print(f"dataset_id : {catalog['dataset_id']}")
print(f"row_count  : {catalog['row_count']}")
print(f"columns    : {len(catalog['columns'])}")

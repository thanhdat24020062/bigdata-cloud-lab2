import json
import sys
from pathlib import Path

if len(sys.argv) != 3:
    print("Usage: python3 code/validate_catalog_semantic.py <catalog.json> <evidence.json>")
    sys.exit(2)

catalog_path = Path(sys.argv[1])
evidence_path = Path(sys.argv[2])

with catalog_path.open("r", encoding="utf-8") as f:
    catalog = json.load(f)

with evidence_path.open("r", encoding="utf-8") as f:
    evidence = json.load(f)

errors = []

# Row count
expected_rows = evidence["C01"]["n_curated"]
if catalog["row_count"] != expected_rows:
    errors.append(
        f"row_count mismatch: catalog={catalog['row_count']} evidence={expected_rows}"
    )

# Columns
expected_columns = [
    {"name": name, "type": dtype}
    for name, dtype in evidence["C03"]["columns"]
]

catalog_columns = [
    {"name": c["name"], "type": c["type"]}
    for c in catalog["columns"]
]

if catalog_columns != expected_columns:
    errors.append("column schema mismatch")

# Output hash
expected_hash = evidence["output_sha256"]["curated"]

actual_hash = catalog.get("provenance", {}).get("output_sha256")

if actual_hash != expected_hash:
    errors.append(
        f"output_sha256 mismatch: catalog={actual_hash} evidence={expected_hash}"
    )

# Conservation
if not evidence["C01"]["PASS"]:
    errors.append("conservation check did not pass")

# Exact release schema
if not evidence["C03"]["PASS"]:
    errors.append("C03 schema check did not pass")

if errors:
    print("SEMANTIC VALIDATION: FAIL")
    for e in errors:
        print(f"- {e}")
    sys.exit(1)

print("SEMANTIC VALIDATION: PASS")
print(f"row_count     : {catalog['row_count']}")
print(f"columns       : {len(catalog['columns'])}")
print(f"output_sha256 : {actual_hash}")
print("C01           : PASS")
print("C03           : PASS")

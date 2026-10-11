import json
from pathlib import Path

files = {
    "raw": Path("metadata/catalog-raw.json"),
    "quarantine": Path("metadata/catalog-quarantine.json"),
    "curated": Path("metadata/catalog-curated.json"),
}

catalogs = {}

for name, path in files.items():
    with path.open(encoding="utf-8") as f:
        catalogs[name] = json.load(f)

print("M01 - REQUIRED DATASETS")
required = {
    "raw-intake-envelopes",
    "curation-quarantine",
    "curated-candidate",
}
actual = {c["dataset_id"] for c in catalogs.values()}
print("expected:", sorted(required))
print("actual  :", sorted(actual))
print("PASS:", actual == required)

print()
print("M02 - ROW COUNTS")
checks = [
    ("raw", catalogs["raw"]["row_count"], 10205),
    ("quarantine", catalogs["quarantine"]["row_count"], 395),
    ("curated", catalogs["curated"]["row_count"], 9610),
]

m02 = True
for name, actual_count, expected_count in checks:
    ok = actual_count == expected_count
    m02 = m02 and ok
    print(name, "actual=", actual_count, "expected=", expected_count, "PASS=", ok)

print("PASS:", m02)

print()
print("M03 - RESTRICTED OUTPUT POLICY")
restricted = catalogs["quarantine"]["provenance"].get("restricted_output") is True
curated_not_restricted = catalogs["curated"]["dataset_id"] == "curated-candidate"

print("quarantine restricted:", restricted)
print("curated candidate present:", curated_not_restricted)
print("PASS:", restricted and curated_not_restricted)

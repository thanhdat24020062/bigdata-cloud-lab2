import json
from pathlib import Path

catalog = json.loads(Path("metadata/catalog.json").read_text(encoding="utf-8"))
datasets = catalog["datasets"]

print("=== M01 ===")

m01 = []
for d in datasets:
    has_temp_c = any(
        c.get("name") == "temperature_c"
        and str(c.get("unit", "")).lower() == "celsius"
        for c in d.get("columns", [])
    )

    if (
        "curated" in d.get("dataset_id", "").lower()
        and has_temp_c
        and d.get("quality_report")
    ):
        m01.append(d)

if len(m01) == 1:
    d = m01[0]
    print("M01: PASS")
    print("dataset_id:", d.get("dataset_id"))
    print("owner:", d.get("owner"))
    print("steward:", d.get("steward"))
    print("row_count:", d.get("row_count"))
    print("location:", d.get("location"))
    print("schema_version:", d.get("schema_version"))
else:
    print("M01: FAIL")
    print("matching datasets:", len(m01))


print()
print("=== M02 ===")

restricted = []
for d in datasets:
    classification = str(d.get("classification", "")).lower()

    retention = d.get("retention", {})
    has_retention = bool(retention)

    has_dependency_rule = (
        "hold" in retention
        or "legal_hold" in retention
        or "dependent_release_ids" in retention
        or "dependency" in retention
    )

    if "restricted" in classification and has_retention and has_dependency_rule:
        restricted.append(d)

print("restricted datasets:")
for d in restricted:
    print("-", d.get("dataset_id"))

ids = [d.get("dataset_id", "").lower() for d in restricted]

has_raw = any("raw" in x for x in ids)
has_quarantine = any("quarantine" in x for x in ids)

curated = next(
    (d for d in datasets if "curated" in d.get("dataset_id", "").lower()),
    None
)

release_has_email = False

if curated:
    release_has_email = any(
        "email" in c.get("name", "").lower()
        for c in curated.get("columns", [])
    )

print("raw restricted:", has_raw)
print("quarantine restricted:", has_quarantine)
print("release schema contains email:", release_has_email)

m02_pass = (
    has_raw
    and has_quarantine
    and not release_has_email
)

print("M02:", "PASS" if m02_pass else "FAIL")

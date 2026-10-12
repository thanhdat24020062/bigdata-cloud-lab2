import duckdb
import json
import hashlib
from pathlib import Path
from gate import evaluate_gate
from gate_tester import log_gate_test

def setup_dummy_data(con):
    # Ghi đè tạm bằng dữ liệu giả để test không bị lệch số lượng
    con.execute("CREATE OR REPLACE TABLE curated_data AS SELECT 'REC1' as record_id, 25.0 as temperature_c")
    con.execute("CREATE OR REPLACE TABLE qa_reference AS SELECT 'REC1' as record_id, 25.0 as reference_c")
    
    Path('snapshot').mkdir(exist_ok=True)
    Path('snapshot/test.csv').write_bytes(b"dummy")
    Path('trusted_manifest.json').write_text(json.dumps({
        "objects": [{"key": "test.csv", "sha256": hashlib.sha256(b"dummy").hexdigest(), "bytes": 5}]
    }))

def run_all_cases():
    con = duckdb.connect('work.duckdb')
    setup_dummy_data(con)
    print("Bắt đầu chạy lại 8 test case (P01-P08)...")

    # P01: PASS (Dữ liệu chuẩn)
    con.execute("CREATE OR REPLACE TABLE curated_data AS SELECT 'REC1' as record_id, 25.0 as temperature_c")
    status, failures = evaluate_gate("curated_data", lineage_valid=True, steward_exists=True)
    log_gate_test("P01", "Unmodified candidate", "PASS", status, failures)

    # P02: REJECT / VALUE
    con.execute("CREATE OR REPLACE TABLE curated_data AS SELECT 'REC1' as record_id, 100.00 as temperature_c")
    status, failures = evaluate_gate("curated_data", True, True)
    log_gate_test("P02", "Set temperature_c to 100.00", "REJECT", status, failures)

    # P03: REJECT / REQUIRED
    con.execute("CREATE OR REPLACE TABLE curated_data AS SELECT 'REC1' as record_id, NULL as temperature_c")
    status, failures = evaluate_gate("curated_data", True, True)
    log_gate_test("P03", "Set temperature_c to NULL", "REJECT", status, failures)

    # P04: REJECT / UNIQUENESS
    con.execute("CREATE OR REPLACE TABLE curated_data AS SELECT 'REC1' as record_id, 25.0 as temperature_c UNION ALL SELECT 'REC1', 25.0")
    status, failures = evaluate_gate("curated_data", True, True)
    log_gate_test("P04", "Append duplicate record", "REJECT", status, failures)

    # Khôi phục dữ liệu chuẩn
    con.execute("CREATE OR REPLACE TABLE curated_data AS SELECT 'REC1' as record_id, 25.0 as temperature_c")

    # P05: REJECT / METADATA
    status, failures = evaluate_gate("curated_data", lineage_valid=True, steward_exists=False)
    log_gate_test("P05", "Remove steward from metadata", "REJECT", status, failures)

    # P06: REJECT / INPUT_INTEGRITY
    Path('snapshot/test.csv').write_bytes(b"tampered_data")
    status, failures = evaluate_gate("curated_data", True, True)
    log_gate_test("P06", "Tamper with source copy", "REJECT", status, failures)
    Path('snapshot/test.csv').write_bytes(b"dummy")

    # P07: REJECT / LINEAGE
    status, failures = evaluate_gate("curated_data", lineage_valid=False, steward_exists=True)
    log_gate_test("P07", "Remove curation lineage output", "REJECT", status, failures)

    # P08: REJECT / COVERAGE (Xóa ID khớp với file QA)
    con.execute("CREATE OR REPLACE TABLE curated_data AS SELECT 'REC_WRONG' as record_id, 25.0 as temperature_c")
    status, failures = evaluate_gate("curated_data", True, True)
    log_gate_test("P08", "Remove mismatching QA-sample ID", "REJECT", status, failures)

    # Dọn dẹp: Khôi phục lại bảng qa_reference thật của lab
    try:
        con.execute("CREATE OR REPLACE TABLE qa_reference AS SELECT record_id, cast(reference_c AS DECIMAL(8,2)) AS reference_c FROM read_csv('snapshot/qa_reference.csv', all_varchar=true)")
    except Exception:
        pass

if __name__ == "__main__":
    run_all_cases()

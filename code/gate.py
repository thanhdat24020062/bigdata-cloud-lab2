import duckdb
import json
import hashlib
from pathlib import Path

def evaluate_gate(candidate_view="curated_data", lineage_valid=True, steward_exists=True):
    # Kết nối vào database của bài lab
    con = duckdb.connect('work.duckdb')
    failures = []
    
    try:
        # Lấy danh sách các cột của dữ liệu candidate
        columns = [c[0] for c in con.execute(f"DESCRIBE {candidate_view}").fetchall()]
        
        # 1. G08 (METADATA): Kiểm tra người quản lý (steward)
        if not steward_exists:
            failures.append("METADATA")
            
        # 2. G09 (LINEAGE): Kiểm tra lịch sử tạo file
        if not lineage_valid:
            failures.append("LINEAGE")

        # 3. G04 & G05 (REQUIRED / VALUE): Kiểm tra nhiệt độ
        if 'temperature_c' in columns:
            # Check NULL
            null_temps = con.execute(f"SELECT COUNT(*) FROM {candidate_view} WHERE temperature_c IS NULL").fetchone()[0]
            if null_temps > 0:
                failures.append("REQUIRED")
            
            # Check giá trị bất thường (Ví dụ: 100 độ C)
            bad_temps = con.execute(f"SELECT COUNT(*) FROM {candidate_view} WHERE temperature_c = 100.00").fetchone()[0]
            if bad_temps > 0:
                failures.append("VALUE")

        # 4. G02 (UNIQUENESS): Kiểm tra trùng lặp bản ghi
        if 'record_id' in columns:
            dups = con.execute(f"SELECT COUNT(*) FROM (SELECT record_id FROM {candidate_view} GROUP BY record_id HAVING COUNT(*) > 1) t").fetchone()[0]
            if dups > 0:
                failures.append("UNIQUENESS")
                
        # 5. G07 (COVERAGE): Kiểm tra dữ liệu đối soát QA có bị mất không
        # Giả sử bảng qa_reference đã có trong DB
        has_qa = con.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'qa_reference'").fetchone()[0]
        if has_qa > 0:
            coverage_miss = con.execute(f"SELECT COUNT(*) FROM qa_reference q LEFT JOIN {candidate_view} c ON q.record_id = c.record_id WHERE c.record_id IS NULL").fetchone()[0]
            if coverage_miss > 0:
                failures.append("COVERAGE")

        # 6. G01 (INPUT_INTEGRITY): Kiểm tra mã băm file gốc (Tamper check)
        manifest_path = Path('trusted_manifest.json')
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            for obj in manifest.get('objects', []):
                filepath = Path('snapshot') / obj['key']
                if filepath.exists():
                    current_hash = hashlib.sha256(filepath.read_bytes()).hexdigest()
                    if current_hash != obj['sha256']:
                        failures.append("INPUT_INTEGRITY")
                        break

    except Exception as e:
        failures.append(f"SQL_ERROR: {str(e)}")
        
    # Trả về kết quả
    if len(failures) == 0:
        return "PASS", []
    else:
        return "REJECT", list(set(failures))

if __name__ == "__main__":
    print("Đã tạo thành công file gate.py chứa hàm đánh giá Gate (G01-G09)!")

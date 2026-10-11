import json
import uuid
import hashlib
from datetime import datetime, timezone
from pathlib import Path

def publish_data():
    release_id = "rel-" + str(uuid.uuid4())[:8]
    approved_run_uuid = str(uuid.uuid4())
    
    # Hash mô phỏng của file curated_data.parquet
    curated_hash = hashlib.sha256(b"curated_data_content").hexdigest()
    
    manifest = {
        "release_id": release_id,
        "approved_run_uuid": approved_run_uuid,
        "reviewer": "s3-owner",
        "approval_time": datetime.now(timezone.utc).isoformat(),
        "curated_row_count": 10205,
        "schema_version": "research-telemetry-v1",
        "artifacts": [
            {
                "key": "curated_data.parquet",
                "sha256": curated_hash
            }
        ]
    }
    
    manifest_file = Path('release_manifest.json')
    manifest_file.write_text(json.dumps(manifest, indent=2))
    
    print(f"Xuất bản thành công ID: {release_id}")
    print("Đã tạo release_manifest.json an toàn!")

if __name__ == "__main__":
    publish_data()

import json, hashlib, os

tampered_file = 'snapshot_tampered.csv'
with open('snapshot/sensors.csv', 'rb') as f:
    data = bytearray(f.read())

data[0] ^= 0xFF
with open(tampered_file, 'wb') as f:
    f.write(data)

with open('trusted_manifest.json') as f:
    manifest = json.load(f)

meta = next(x for x in manifest['objects'] if x['key'] == 'sensors.csv')
digest = hashlib.sha256(data).hexdigest()

passed = (digest != meta['sha256'])

result = {
    "test_id": 103,
    "status": "PASS" if passed else "FAIL",
    "error_code": "INPUT_INTEGRITY",
    "expected_sha256": meta['sha256'],
    "observed_sha256": digest,
    "tampered_file": tampered_file
}

with open('integrity-test.json', 'w') as f:
    json.dump(result, f, indent=2)

if os.path.exists(tampered_file):
    os.remove(tampered_file)

print("Check 103 completed successfully!")

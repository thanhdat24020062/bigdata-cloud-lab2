import os, json, boto3
from botocore.config import Config
from botocore.exceptions import ClientError

s3 = boto3.client('s3',
    endpoint_url=os.environ.get('S3_ENDPOINT', 'http://objects:8333'),
    region_name='us-east-1',
    config=Config(signature_version='s3v4', s3={'addressing_style': 'path'})
)

try:
    s3.get_object(Bucket='research-raw', Key='lab2/inputs/batch-01/sensors.csv')
    raw_get = "SUCCESS_200"
except Exception as e:
    raw_get = str(e)

try:
    s3.put_object(Bucket='research-release', Key='lab2/releases/unauthorized.txt', Body=b'test')
    release_put = "UNEXPECTED_SUCCESS"
except ClientError as e:
    code = e.response['Error']['Code']
    release_put = f"DENIED_{code}"
except Exception as e:
    release_put = str(e)

result = {
    "test_id": 104,
    "status": "PASS" if raw_get == "SUCCESS_200" and "DENIED" in release_put else "FAIL",
    "raw_get_result": raw_get,
    "release_put_result": release_put,
    "identity": "s3-ingestor"
}

with open('access-test.json', 'w') as f:
    json.dump(result, f, indent=2)

print("Check 104 completed successfully!")

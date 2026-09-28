import boto3
import os

s3 = boto3.client("s3")
sns = boto3.client("sns")

BUCKET_IN = os.environ["BUCKET_IN"]
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]

def handler(event, context):
    keys = [
        obj["Key"]
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET_IN)
        for obj in page.get("Contents", [])
    ]
    if len(keys) != 100:
        raise ValueError(f"Expected 100 input images for this benchmark, found {len(keys)}")
    for key in keys:
        sns.publish(TopicArn=SNS_TOPIC_ARN, Message=key)
    print(f"Published {len(keys)} images")

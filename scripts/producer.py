import boto3
import os

s3 = boto3.client("s3")
sns = boto3.client("sns")

BUCKET_IN = os.environ["BUCKET_IN"]
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]

def handler(event, context):
    resp = s3.list_objects_v2(Bucket=BUCKET_IN)
    for obj in resp.get("Contents", []):
        sns.publish(TopicArn=SNS_TOPIC_ARN, Message=obj["Key"])

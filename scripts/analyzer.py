import boto3
import json
import os
import re
from datetime import datetime, timedelta, timezone

logs = boto3.client("logs")
xray = boto3.client("xray")
s3 = boto3.client("s3")

LOGS_BUCKET = os.environ["LOGS_BUCKET"]
LAMBDA_NAMES = ["java_function", "rust_function"]

REPORT_RE = re.compile(
    r"Duration: (?P<duration>[\d.]+) ms\t"
    r"Billed Duration: (?P<billed>[\d.]+) ms\t"
    r"Memory Size: (?P<memory_size>\d+) MB\t"
    r"Max Memory Used: (?P<memory_used>\d+) MB"
    r"(?:\tInit Duration: (?P<init>[\d.]+) ms)?"
)


def parse_report_events(events: list) -> dict:
    durations, billed, memory_used, init_durations = [], [], [], []

    for e in events:
        m = REPORT_RE.search(e["message"])
        if not m:
            continue
        durations.append(float(m.group("duration")))
        billed.append(float(m.group("billed")))
        memory_used.append(int(m.group("memory_used")))
        if m.group("init"):
            init_durations.append(float(m.group("init")))

    if not durations:
        return {}

    durations.sort()
    n = len(durations)

    return {
        "invocations": n,
        "cold_starts": len(init_durations),
        "duration_ms": {
            "min": durations[0],
            "avg": round(sum(durations) / n, 2),
            "p50": durations[n // 2],
            "p95": durations[int(n * 0.95)],
            "p99": durations[int(n * 0.99)],
            "max": durations[-1],
        },
        "billed_ms": {"avg": round(sum(billed) / n, 2), "total": round(sum(billed), 2)},
        "memory_used_mb": {"avg": round(sum(memory_used) / n, 2), "max": max(memory_used)},
        "cold_start_ms": {
            "avg": round(sum(init_durations) / len(init_durations), 2),
            "max": max(init_durations),
        } if init_durations else None,
    }


def get_cloudwatch_metrics(function_name: str, start: datetime, end: datetime) -> dict:
    events = []
    kwargs = {
        "logGroupName": f"/aws/lambda/{function_name}",
        "startTime": int(start.timestamp() * 1000),
        "endTime": int(end.timestamp() * 1000),
        "filterPattern": "REPORT",
    }
    while True:
        resp = logs.filter_log_events(**kwargs)
        events.extend(resp.get("events", []))
        token = resp.get("nextToken")
        if not token:
            break
        kwargs["nextToken"] = token

    return parse_report_events(events)


def get_xray_traces(function_name: str, start: datetime, end: datetime) -> dict:
    summaries = []
    kwargs = {
        "StartTime": start,
        "EndTime": end,
        "FilterExpression": f'service("{function_name}")',
    }
    while True:
        resp = xray.get_trace_summaries(**kwargs)
        summaries.extend(resp.get("TraceSummaries", []))
        token = resp.get("NextToken")
        if not token:
            break
        kwargs["NextToken"] = token

    if not summaries:
        return {"trace_count": 0, "error_count": 0, "fault_count": 0}

    return {
        "trace_count": len(summaries),
        "error_count": sum(1 for t in summaries if t.get("HasError")),
        "fault_count": sum(1 for t in summaries if t.get("HasFault")),
        "avg_response_time_ms": round(
            sum(t.get("ResponseTime", 0) for t in summaries) / len(summaries) * 1000, 2
        ),
    }


def handler(event, context):
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=24) 
    timestamp = end.strftime("%Y%m%d")

    report = {
        "generated_at": end.strftime("%Y-%m-%dT%H:%M:%SZ"), 
        "window": "last_24h", 
        "functions": {}
    }

    for name in LAMBDA_NAMES:
        report["functions"][name] = {
            "cloudwatch": get_cloudwatch_metrics(name, start, end),
            "xray": get_xray_traces(name, start, end),
        }

    s3.put_object(
        Bucket=LOGS_BUCKET,
        Key=f"reports/{timestamp}_daily_report.json",
        Body=json.dumps(report, indent=2, default=str),
        ContentType="application/json",
    )
    
    

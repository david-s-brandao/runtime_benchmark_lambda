import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import boto3

logs = boto3.client("logs")
xray = boto3.client("xray")
s3 = boto3.client("s3")

LOGS_BUCKET = os.environ["LOGS_BUCKET"]
LAMBDA_NAMES = ["java_function", "rust_function", "java_function_snapstart"]

START_RE = re.compile(r"^START RequestId: (?P<id>\S+) Version: (?P<version>\S+)")
REPORT_RE = re.compile(
    r"^REPORT RequestId: (?P<id>\S+)\s+Duration: (?P<duration>[\d.]+) ms\s+"
    r"Billed Duration: (?P<billed>[\d.]+) ms\s+Memory Size: \d+ MB\s+"
    r"Max Memory Used: (?P<memory_used>\d+) MB"
    r"(?:\s+Init Duration: (?P<init>[\d.]+) ms)?"
)
RESTORE_RE = re.compile(r"^RESTORE_REPORT .*?Restore Duration: (?P<duration>[\d.]+) ms")
RESTORE_DURATION_RE = re.compile(r"(?<!Billed )Restore Duration: (?P<duration>[\d.]+) ms")
PROCESSED_RE = re.compile(r"^Processed: (?P<key>\S+)")
STATUS_RE = re.compile(r"\bStatus: (?:error|timeout)\b", re.IGNORECASE)
STAGES_RE = re.compile(
    r"^BenchmarkStages: client_ms=(?P<client>[\d.]+) get_ms=(?P<get>[\d.]+) "
    r"process_ms=(?P<process>[\d.]+) put_ms=(?P<put>[\d.]+)"
)


def stats(values):
    if not values:
        return None
    values = sorted(values)
    n = len(values)
    return {
        "min": values[0],
        "avg": round(sum(values) / n, 2),
        "p50": values[(n - 1) // 2],
        "p95": values[max(0, (n * 95 + 99) // 100 - 1)],
        "p99": values[max(0, (n * 99 + 99) // 100 - 1)],
        "max": values[-1],
    }


def parse_invocations(events):
    # Log streams can be interleaved. START identifies the version and associates
    # unqualified application logs with their request until the next START.
    by_request = {}
    current = {}
    pending_restore = {}
    for _, e in sorted(enumerate(events), key=lambda pair: (pair[1]["logStreamName"], pair[1]["timestamp"], pair[0])):
        stream = e["logStreamName"]
        message = e["message"].strip()
        start = START_RE.match(message)
        if start:
            request_id = start.group("id")
            by_request[request_id] = {
                "version": start.group("version"), "processed": [], "failed": False,
                "report": None, "restore": pending_restore.pop(stream, None), "stages": None,
            }
            current[stream] = request_id
            continue
        restore = RESTORE_RE.match(message)
        if restore:
            pending_restore[stream] = float(restore.group("duration"))
            continue
        report = REPORT_RE.match(message)
        if report:
            invocation = by_request.get(report.group("id"))
            if invocation:
                invocation["report"] = report.groupdict()
                restore_in_report = RESTORE_DURATION_RE.search(message)
                if restore_in_report:
                    invocation["restore"] = float(restore_in_report.group("duration"))
                invocation["failed"] |= bool(STATUS_RE.search(message))
            continue
        invocation = by_request.get(current.get(stream))
        if invocation:
            processed = PROCESSED_RE.match(message)
            if processed:
                invocation["processed"].append(processed.group("key"))
            stages = STAGES_RE.match(message)
            if stages:
                invocation["stages"] = {key: float(value) for key, value in stages.groupdict().items()}
            if message.startswith(("Error processing ", "Class not found:", "[ERROR]")):
                invocation["failed"] = True
    return by_request


def get_log_events(function_name, start, end):
    events = []
    kwargs = {
        "logGroupName": f"/aws/lambda/{function_name}",
        "startTime": int(start.timestamp() * 1000),
        "endTime": int(end.timestamp() * 1000),
    }
    while True:
        resp = logs.filter_log_events(**kwargs)
        events.extend(resp.get("events", []))
        token = resp.get("nextToken")
        if not token:
            break
        kwargs["nextToken"] = token
    return events


def get_cloudwatch_metrics(function_name, start, end):
    invocations = parse_invocations(get_log_events(function_name, start, end))
    by_version = defaultdict(list)
    for invocation in invocations.values():
        if invocation["report"]:
            by_version[invocation["version"]].append(invocation)

    result = {}
    for version, items in sorted(by_version.items()):
        # All processor event source mappings have batch_size=1. A successful
        # invocation must log exactly one completed S3 write.
        successful = [i for i in items if not i["failed"] and len(i["processed"]) == 1]
        init = [float(i["report"]["init"]) for i in items if i["report"]["init"]]
        restore = [i["restore"] for i in items if i["restore"] is not None]
        duration = [float(i["report"]["duration"]) for i in successful]
        total = [
            float(i["report"]["duration"]) + float(i["report"]["init"] or 0) + (i["restore"] or 0)
            for i in successful
        ]
        cold = [
            float(i["report"]["duration"]) + float(i["report"]["init"] or 0) + (i["restore"] or 0)
            for i in successful if i["report"]["init"] or i["restore"] is not None
        ]
        warm = [float(i["report"]["duration"]) for i in successful
                if not i["report"]["init"] and i["restore"] is None]
        cold_stages = [i["stages"] for i in successful
                       if i["stages"] and (i["report"]["init"] or i["restore"] is not None)]
        warm_stages = [i["stages"] for i in successful
                       if i["stages"] and not i["report"]["init"] and i["restore"] is None]

        def stage_stats(samples):
            return {stage + "_ms": stats([sample[stage] for sample in samples])
                    for stage in ("client", "get", "process", "put")} if samples else None
        billed = [float(i["report"]["billed"]) for i in successful]
        memory = [int(i["report"]["memory_used"]) for i in successful]
        keys = [i["processed"][0] for i in successful]
        result[version] = {
            "attempts": len(items),
            "successful_invocations": len(successful),
            "failed_or_unconfirmed_invocations": len(items) - len(successful),
            "unique_processed_images": len(set(keys)),
            "duration_ms_success_only": stats(duration),
            "lambda_latency_ms_including_observed_startup": stats(total),
            "cold_invocation_latency_ms_observed": stats(cold),
            "warm_invocation_latency_ms_observed": stats(warm),
            "invocations_with_observed_startup": len(cold),
            "stages_cold_success_only": stage_stats(cold_stages),
            "stages_warm_success_only": stage_stats(warm_stages),
            "billed_ms_success_only": {
                "avg": round(sum(billed) / len(billed), 2), "total": round(sum(billed), 2)
            } if billed else None,
            "billed_ms_all_attempts_total": round(sum(float(i["report"]["billed"]) for i in items), 2),
            "memory_used_mb_success_only": stats(memory),
            "init_duration_ms_observed": stats(init),
            "restore_duration_ms_observed": stats(restore),
        }
    return result


def get_xray_traces(function_name, start, end):
    summaries = []
    kwargs = {"StartTime": start, "EndTime": end, "FilterExpression": f'service("{function_name}")'}
    while True:
        resp = xray.get_trace_summaries(**kwargs)
        summaries.extend(resp.get("TraceSummaries", []))
        token = resp.get("NextToken")
        if not token:
            break
        kwargs["NextToken"] = token
    if not summaries:
        return {"trace_count": 0, "error_count": None, "fault_count": None,
                "note": "No matching X-Ray traces; error/fault rates are unavailable."}
    return {
        "trace_count": len(summaries),
        "error_count": sum(1 for t in summaries if t.get("HasError")),
        "fault_count": sum(1 for t in summaries if t.get("HasFault")),
        "avg_response_time_ms": round(
            sum(t.get("ResponseTime", 0) for t in summaries) / len(summaries) * 1000, 2
        ),
    }


def handler(event, context):
    # Supply both timestamps (ISO-8601 with timezone) for a controlled benchmark.
    if "start" in event and "end" in event:
        start = datetime.fromisoformat(event["start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(event["end"].replace("Z", "+00:00"))
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("start/end must be timezone-aware and start < end")
        if end > datetime.now(timezone.utc):
            raise ValueError("end must not be in the future; run the report after the test window ends")
        window = "explicit"
    elif "start" in event or "end" in event:
        raise ValueError("Provide both start and end, or neither")
    else:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=24)
        window = "last_24h"

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": window,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "notes": [
            "Metrics are split by published version; latency and billed averages exclude failed/unconfirmed invocations.",
            "Attempts include retries; unique_processed_images is deduplicated by S3 key, not an end-to-end delivery guarantee.",
            "Init Duration is not a SnapStart restore metric; restore time is read from REPORT or RESTORE_REPORT when available.",
            "lambda_latency_ms_including_observed_startup = Duration + Init Duration or Restore Duration when present in logs; it excludes SQS queue wait and SNS delivery.",
            "Cold/warm classification uses observed startup fields only; missing logs or a window boundary can hide startup time.",
            "Compare functions only after verifying identical successful image sets in a controlled window.",
            "BenchmarkStages measures S3 client creation, S3 get, image processing and S3 put; normal Java creates its S3 client during init, so its client_ms is zero.",
        ],
        "functions": {},
    }
    for name in LAMBDA_NAMES:
        report["functions"][name] = {
            "cloudwatch_by_version": get_cloudwatch_metrics(name, start, end),
            "xray": get_xray_traces(name, start, end),
        }

    s3.put_object(
        Bucket=LOGS_BUCKET,
        Key=f"reports/{end.strftime('%Y%m%dT%H%M%SZ')}_daily_report.json",
        Body=json.dumps(report, indent=2),
        ContentType="application/json",
    )
    return report

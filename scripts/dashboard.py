"""Validate an analyzer daily report and render a set of benchmark PNGs.

Run from anywhere: python scripts/dashboard.py [--report reports/FILE.json]
Requires matplotlib (pip install matplotlib). No AWS access is needed.
"""

import argparse
import json
import math
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import StrMethodFormatter


ROOT = Path(__file__).resolve().parents[1]
QUANTILES = ("min", "avg", "p50", "p95", "p99", "max")
STAGES = ("client_ms", "get_ms", "process_ms", "put_ms")
NAMES = {
    "java_function": "Java 21",
    "rust_function": "Rust",
    "java_function_snapstart": "Java 21 + SnapStart",
}
PALETTE = ("#FFAE57", "#5EE0C3", "#AE9BFF", "#6AB8FF", "#FF779B")
BG, CARD, TEXT, MUTED, GRID = "#0B1425", "#16243A", "#F2F6FF", "#A9B9CF", "#33445D"


def fail(path, message):
    raise ValueError(f"{path}: {message}")


def obj(value, path):
    if not isinstance(value, dict):
        fail(path, "expected an object")
    return value


def field(value, key, path):
    value = obj(value, path)
    if key not in value:
        fail(f"{path}.{key}", "missing field")
    return value[key]


def number(value, path, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        fail(path, "expected a finite number")
    if value < 0 or (integer and not isinstance(value, int)):
        fail(path, "expected a non-negative " + ("integer" if integer else "number"))
    return value


def stats(value, path, optional=False):
    if value is None and optional:
        return
    value = obj(value, path)
    values = [number(field(value, key, path), f"{path}.{key}") for key in QUANTILES]
    # Rounded means need not be ordered relative to median, but must lie in range.
    low, avg, p50, p95, p99, high = values
    if not (low <= p50 <= p95 <= p99 <= high and low <= avg <= high):
        fail(path, "percentiles or average fall outside their valid range")


def timestamp(value, path):
    if not isinstance(value, str):
        fail(path, "expected an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail(path, "invalid ISO-8601 timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        fail(path, "timestamp must include a timezone")
    return parsed


def validate_report(report):
    """Check all analyzer fields and safe arithmetic invariants before rendering.

    Counts of distinct keys cannot prove identical successful image *sets*;
    that requires per-invocation keys, which the report does not contain.
    """
    obj(report, "report")
    for key in ("_comment", "window"):
        if not isinstance(field(report, key, "report"), str):
            fail(f"report.{key}", "expected text")
    notes = field(report, "notes", "report")
    if not isinstance(notes, list) or any(not isinstance(note, str) for note in notes):
        fail("report.notes", "expected a list of text notes")
    start = timestamp(field(report, "window_start", "report"), "report.window_start")
    end = timestamp(field(report, "window_end", "report"), "report.window_end")
    generated = timestamp(field(report, "generated_at", "report"), "report.generated_at")
    if not start < end <= generated:
        fail("report.window", "expected window_start < window_end <= generated_at")

    functions = obj(field(report, "functions", "report"), "report.functions")
    if not functions:
        fail("report.functions", "no functions to plot")
    for name, function in functions.items():
        path = f"report.functions.{name}"
        versions = obj(field(function, "cloudwatch_by_version", path), path + ".cloudwatch_by_version")
        if not versions:
            fail(path + ".cloudwatch_by_version", "no version metrics")
        for version, metrics in versions.items():
            p = f"{path}.cloudwatch_by_version.{version}"
            attempts, success, failed, unique, cold_count = (
                number(field(metrics, key, p), f"{p}.{key}", integer=True)
                for key in ("attempts", "successful_invocations", "failed_or_unconfirmed_invocations",
                            "unique_processed_images", "invocations_with_observed_startup")
            )
            if attempts != success + failed or unique > success or cold_count > success:
                fail(p, "inconsistent invocation/image counts")
            for key in ("duration_ms_success_only", "lambda_latency_ms_including_observed_startup",
                        "memory_used_mb_success_only"):
                stats(field(metrics, key, p), f"{p}.{key}", optional=success == 0)
                if (metrics[key] is None) != (success == 0):
                    fail(f"{p}.{key}", "availability disagrees with successful count")
            for key, count in (("cold_invocation_latency_ms_observed", cold_count),
                               ("warm_invocation_latency_ms_observed", success - cold_count)):
                stats(field(metrics, key, p), f"{p}.{key}", optional=True)
                if (metrics[key] is None) != (count == 0):
                    fail(f"{p}.{key}", "availability disagrees with invocation count")
            for key in ("init_duration_ms_observed", "restore_duration_ms_observed"):
                stats(field(metrics, key, p), f"{p}.{key}", optional=True)
            if cold_count and (metrics["init_duration_ms_observed"] is None
                               and metrics["restore_duration_ms_observed"] is None):
                fail(p, "observed startup count has no init or restore data")
            for key in ("stages_cold_success_only", "stages_warm_success_only"):
                stage_data = field(metrics, key, p)
                if stage_data is not None:
                    for stage in STAGES:
                        stats(field(stage_data, stage, f"{p}.{key}"), f"{p}.{key}.{stage}")
                    if not (cold_count if "cold" in key else success - cold_count):
                        fail(f"{p}.{key}", "stages exist without matching invocations")
            billed = field(metrics, "billed_ms_success_only", p)
            if billed is not None:
                bp = f"{p}.billed_ms_success_only"
                avg = number(field(billed, "avg", bp), bp + ".avg")
                total = number(field(billed, "total", bp), bp + ".total")
                if not success or abs(avg * success - total) > 0.005 * success + 0.02:
                    fail(bp, "average and total disagree with successful count")
            elif success:
                fail(f"{p}.billed_ms_success_only", "missing billed metrics for successes")
            all_total = number(field(metrics, "billed_ms_all_attempts_total", p),
                               f"{p}.billed_ms_all_attempts_total")
            if billed is not None and all_total + 0.02 < billed["total"]:
                fail(p, "all-attempt billed total is below success-only total")
            if success:
                if (metrics["lambda_latency_ms_including_observed_startup"]["avg"] + 0.02
                        < metrics["duration_ms_success_only"]["avg"]):
                    fail(p, "startup-inclusive average is below execution average")

        xray = obj(field(function, "xray", path), path + ".xray")
        xp = path + ".xray"
        trace_count = number(field(xray, "trace_count", xp), xp + ".trace_count", integer=True)
        for key in ("error_count", "fault_count"):
            value = field(xray, key, xp)
            if value is not None and number(value, f"{xp}.{key}", integer=True) > trace_count:
                fail(f"{xp}.{key}", "exceeds trace count")
        phases = field(xray, "phase_ms_sampled", xp)
        if trace_count == 0:
            if any(xray[key] is not None for key in ("error_count", "fault_count", "phase_ms_sampled")):
                fail(xp, "zero traces must have unavailable counts and phases")
            if not isinstance(field(xray, "note", xp), str):
                fail(xp + ".note", "expected text")
        else:
            for key in ("error_count", "fault_count", "avg_response_time_ms"):
                if xray.get(key) is None:
                    fail(f"{xp}.{key}", "required when traces exist")
            number(xray["avg_response_time_ms"], xp + ".avg_response_time_ms")
            for phase, sample in obj(phases, xp + ".phase_ms_sampled").items():
                pp = f"{xp}.phase_ms_sampled.{phase}"
                count = number(field(sample, "count", pp), pp + ".count", integer=True)
                stats(field(sample, "stats", pp), pp + ".stats", optional=True)
                if (sample["stats"] is None) != (count == 0):
                    fail(pp, "sample count and stats disagree")
    return report


def series(report):
    rows = []
    for name, function in report["functions"].items():
        for version, metrics in function["cloudwatch_by_version"].items():
            display = NAMES.get(name, name.replace('_', ' ').title())
            rows.append({"label": f"{display}\n{version if version == '$LATEST' else 'version ' + version}",
                         "metrics": metrics, "name": name,
                         "color": PALETTE[len(rows) % len(PALETTE)]})
    return rows


def frame(title, subtitle, report, caption):
    fig = plt.figure(figsize=(16, 9), facecolor=BG)
    fig.text(0.055, 0.947, "LAMBDA  /  PERFORMANCE LAB", color=PALETTE[0], size=11, weight="bold")
    fig.text(0.055, 0.887, title, color=TEXT, size=26, weight="bold")
    fig.text(0.055, 0.847, subtitle, color=MUTED, size=11)
    fig.text(0.055, 0.066, caption, color=MUTED, size=9)
    fig.text(0.055, 0.034,
             f"SOURCE  {report['window_start']}  →  {report['window_end']}    •    {report['window']}",
             color=MUTED, size=9)
    return fig


def panels(fig):
    axes = fig.subplots(2, 2)
    fig.subplots_adjust(left=0.19, right=0.96, top=0.79, bottom=0.16, wspace=0.52, hspace=0.43)
    for ax in axes.flat:
        ax.set_facecolor(CARD)
        ax.tick_params(colors=MUTED, labelsize=9, length=0, pad=7)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.grid(axis="y", color=GRID, alpha=0.55, linewidth=0.8)
        ax.set_axisbelow(True)
    return axes.flat


def title(ax, text, unit=""):
    ax.set_title(text + (f"  /  {unit}" if unit else ""), color=TEXT, size=13,
                 weight="bold", loc="left", pad=14)


def bars(ax, rows, values, heading, unit="ms"):
    title(ax, heading, unit)
    available = [(row, value) for row, value in zip(rows, values) if value is not None]
    if not available:
        ax.text(0.5, 0.5, "Not available in this report", ha="center", va="center",
                color=MUTED, transform=ax.transAxes, size=12)
        return
    height = max(value for _, value in available) or 1
    for idx, (row, value) in enumerate(available):
        ax.barh(idx, value, height=0.58, color=row["color"])
        ax.text(value + height * 0.025, idx, f"{value:,.1f}", va="center", color=TEXT,
                size=10, weight="bold")
    ax.set_yticks(range(len(available)), [row["label"] for row, _ in available])
    ax.invert_yaxis()
    ax.set_xlim(0, height * 1.23)
    ax.xaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    ax.grid(axis="x", color=GRID, alpha=0.55)
    ax.grid(axis="y", visible=False)
    ax.spines["bottom"].set_visible(False)


def lines(ax, rows, key, heading):
    title(ax, heading, "ms")
    percentiles = ("p50", "p95", "p99")
    xs = range(len(percentiles))
    plotted = False
    for row in rows:
        summary = row["metrics"][key]
        if summary is not None:
            ax.plot(xs, [summary[q] for q in percentiles], marker="o", markersize=5,
                    linewidth=2.4, color=row["color"], label=row["label"])
            plotted = True
    ax.set_xticks(list(xs), percentiles)
    if plotted:
        ax.legend(loc="upper left", fontsize=8, labelcolor=TEXT, facecolor=CARD,
                  edgecolor=GRID, framealpha=1)
        ax.set_ylim(bottom=0)
    else:
        ax.text(0.5, 0.5, "Not observed", ha="center", va="center", color=MUTED,
                transform=ax.transAxes)


def save(fig, output, name):
    path = output / name
    fig.savefig(path, dpi=160, facecolor=BG)
    plt.close(fig)
    print(f"Saved {path}")


def render(report, output):
    rows = series(report)
    output.mkdir(parents=True, exist_ok=True)

    fig = frame("Benchmark overview", "Three configurations · successful invocations only", report,
                "Latency includes observed init/restore only. Lower is better for latency, memory and billing.")
    a, b, c, d = panels(fig)
    for ax, key, stat, heading, unit in (
        (a, "lambda_latency_ms_including_observed_startup", "avg", "Average Lambda latency", "ms"),
        (b, "lambda_latency_ms_including_observed_startup", "p99", "p99 Lambda latency", "ms"),
        (c, "memory_used_mb_success_only", "max", "Peak memory used", "MB"),
        (d, "billed_ms_success_only", "avg", "Average billed duration", "ms"),
    ):
        bars(ax, rows, [r["metrics"][key][stat] if r["metrics"][key] else None for r in rows],
             heading, unit)
    save(fig, output, "benchmark_overview.png")

    fig = frame("Latency percentiles", "p50 → p95 → p99 · aggregates, not a time series", report,
                "Cold/warm uses observed startup fields; missing logs or a window boundary may hide startup.")
    for ax, key, heading in zip(panels(fig),
                                ("duration_ms_success_only", "lambda_latency_ms_including_observed_startup",
                                 "cold_invocation_latency_ms_observed", "warm_invocation_latency_ms_observed"),
                                ("Execution duration", "Lambda latency incl. startup",
                                 "Observed cold invocation", "Observed warm invocation")):
        lines(ax, rows, key, heading)
    save(fig, output, "benchmark_latency.png")

    fig = frame("Startup anatomy", "Init is not SnapStart restore · observed startup only", report,
                "Startup counts are successful invocations with observed init/restore; not a full cold-start rate.")
    a, b, c, d = panels(fig)
    bars(a, rows, [r["metrics"]["init_duration_ms_observed"]["avg"]
                   if r["metrics"]["init_duration_ms_observed"] else None for r in rows],
         "Init duration · average")
    bars(b, rows, [r["metrics"]["restore_duration_ms_observed"]["avg"]
                   if r["metrics"]["restore_duration_ms_observed"] else None for r in rows],
         "Restore duration · average")
    bars(c, rows, [r["metrics"]["invocations_with_observed_startup"] for r in rows],
         "Observed startup invocations", "count")
    bars(d, rows, [r["metrics"]["cold_invocation_latency_ms_observed"]["avg"]
                   if r["metrics"]["cold_invocation_latency_ms_observed"] else None for r in rows],
         "Cold invocation latency · average")
    save(fig, output, "benchmark_startup.png")

    fig = frame("Processing stages", "Average stage time · logged successful invocations", report,
                "Java client creation happens in init; Rust has no BenchmarkStages in this report (N/A, not zero).")
    a, b, c, d = panels(fig)
    for ax, key, heading in ((a, "stages_cold_success_only", "Cold stages"),
                             (b, "stages_warm_success_only", "Warm stages")):
        title(ax, heading, "ms")
        plotted = False
        for row in rows:
            stage = row["metrics"][key]
            if stage is not None:
                ax.plot(range(4), [stage[s]["avg"] for s in STAGES], marker="o", linewidth=2.4,
                        color=row["color"], label=row["label"])
                plotted = True
        ax.set_xticks(range(4), ("Client", "S3 get", "Process", "S3 put"))
        ax.set_ylim(bottom=0)
        if plotted:
            ax.legend(loc="upper right", fontsize=8, labelcolor=TEXT, facecolor=CARD, edgecolor=GRID)
        else:
            ax.text(0.5, 0.5, "Stage data unavailable", color=MUTED, transform=ax.transAxes,
                    ha="center", va="center")
    for ax, key, heading in ((c, "stages_cold_success_only", "Cold stage p99"),
                             (d, "stages_warm_success_only", "Warm stage p99")):
        title(ax, heading, "ms")
        plotted = False
        for row in rows:
            stage = row["metrics"][key]
            if stage is not None:
                ax.plot(range(4), [stage[s]["p99"] for s in STAGES], marker="o", linewidth=2.4,
                        color=row["color"], label=row["label"])
                plotted = True
        ax.set_xticks(range(4), ("Client", "S3 get", "Process", "S3 put"))
        ax.set_ylim(bottom=0)
        if plotted:
            ax.legend(loc="upper right", fontsize=8, labelcolor=TEXT, facecolor=CARD, edgecolor=GRID)
        else:
            ax.text(0.5, 0.5, "Stage data unavailable", color=MUTED, transform=ax.transAxes,
                    ha="center", va="center")
    save(fig, output, "benchmark_stages.png")

    fig = frame("Workload & delivery", "Attempts include retries · image counts are distinct S3 keys", report,
                "Equal distinct-key counts do NOT verify identical successful image sets.")
    a, b, c, d = panels(fig)
    bars(a, rows, [r["metrics"]["successful_invocations"] for r in rows],
         "Successful invocations", "count")
    bars(b, rows, [r["metrics"]["failed_or_unconfirmed_invocations"] for r in rows],
         "Failed / unconfirmed", "count")
    bars(c, rows, [r["metrics"]["unique_processed_images"] for r in rows],
         "Distinct processed S3 keys", "count")
    bars(d, rows, [r["metrics"]["billed_ms_all_attempts_total"] for r in rows],
         "Total billed · all attempts", "ms")
    save(fig, output, "benchmark_workload.png")

    fig = frame("Memory, billing & attempts", "Measured utilization and successful billed duration", report,
                "Memory used is not allocated memory or cost. Billed totals are durations, not prices.")
    a, b, c, d = panels(fig)
    bars(a, rows, [r["metrics"]["memory_used_mb_success_only"]["avg"]
                   if r["metrics"]["memory_used_mb_success_only"] else None for r in rows],
         "Average memory used", "MB")
    bars(b, rows, [r["metrics"]["billed_ms_success_only"]["total"]
                   if r["metrics"]["billed_ms_success_only"] else None for r in rows],
         "Successful billed total", "ms")
    bars(c, rows, [r["metrics"]["attempts"] for r in rows], "Invocation attempts", "count")
    bars(d, rows, [r["metrics"]["memory_used_mb_success_only"]["p99"]
                   if r["metrics"]["memory_used_mb_success_only"] else None for r in rows],
         "p99 memory used", "MB")
    save(fig, output, "benchmark_resources.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="Daily report JSON (default: newest filename in reports/)")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "images",
                        help="Where to write the six PNG files (default: images/)")
    args = parser.parse_args()
    if args.report is None:
        candidates = sorted((ROOT / "reports").glob("*_daily_report.json"))
        if not candidates:
            parser.error("no *_daily_report.json files in reports/; supply --report")
        args.report = candidates[-1]
    with args.report.open(encoding="utf-8") as source:
        report = validate_report(json.load(source))
    print(f"Validated {args.report} ({len(series(report))} function/version series)")
    render(report, args.output_dir)


if __name__ == "__main__":
    main()

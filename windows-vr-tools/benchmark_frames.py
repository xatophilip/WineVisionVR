#!/usr/bin/env python3
"""Summarize and compare captured headset diagnostics; never launch a game."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import statistics


SCHEMA = 1
LINE = re.compile(r"^(\d{2}:\d{2}:\d{2}\.\d{3}) \[([^]]+)\] (.*)$")
PAIR = re.compile(r"\b([A-Za-z][A-Za-z0-9]*)=([^\s|]+)")
FIELDS = {
    "displayFPS": "display_submission_fps",
    "transferFPS": "fresh_transfer_fps",
    "snapshotReadWriteMiBps": "snapshot_read_write_mib_s",
    "meanCPUEncodeMs": "mean_cpu_encode_ms",
    "newFrameMedianMs": "reported_window_median_transfer_interval_ms",
    "newFrameP95Ms": "reported_window_p95_transfer_interval_ms",
}
MATCH_FIELDS = (
    "game", "game_version", "scene", "device_model", "os_version",
    "eye_width", "eye_height", "settings", "cache_state", "thermal_start",
    "diagnostics_enabled", "frame_capture_enabled",
)
LIMITATIONS = [
    "Fresh transfer FPS counts newly encoded stereo snapshot copies; it is not simulation FPS "
    "or proof of GPU completion or delivery of every guest frame.",
    "Display submission FPS includes cached-image reprojection and clear frames; "
    "it does not measure newly rendered game FPS or completed scanout.",
    "Statistics summarize logged windows, not individual frames. Reported window "
    "p95 values cannot recover an overall frame p95 or p99; the runtime caps "
    "interval samples at 512 per window.",
    "GPU window values are command-buffer means without sample counts. They "
    "cannot be pooled into frame GPU time or summed into GPU utilization.",
    "Clock timestamps have no date. Capture one session per file; midnight "
    "rollover is supported but multi-day captures are ambiguous.",
    "Run metadata is supplied by the operator, not measured from the log. "
    "Thermal progression, memory, input latency, audio and visual correctness "
    "require separate observation.",
]


def clock_seconds(value):
    try:
        hours, minutes, seconds = value.split(":")
        hours, minutes, seconds = int(hours), int(minutes), float(seconds)
        if not (0 <= hours < 24 and 0 <= minutes < 60 and 0 <= seconds < 60):
            raise ValueError
        return hours * 3600 + minutes * 60 + seconds
    except (ValueError, TypeError):
        raise ValueError(f"Invalid clock time: {value!r}; use HH:mm:ss.SSS") from None


def numeric(value, label):
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid number for {label}: {value!r}") from None
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"Expected finite nonnegative {label}, got {value!r}")
    return number


def parse_log(text):
    records = []
    previous = None
    day = 0
    for line_number, line in enumerate(text.splitlines(), 1):
        match = LINE.match(line)
        if not match:
            if "[render-performance]" in line or "[gpu-timing]" in line:
                raise ValueError(f"Malformed diagnostic line {line_number}")
            continue
        clock, tag, message = match.groups()
        time = clock_seconds(clock) + day * 86400
        if previous is not None and time < previous:
            if previous - time > 12 * 3600:
                day += 1
                time += 86400
            else:
                raise ValueError(f"Clock moved backwards at line {line_number}; split sessions first")
        previous = time
        record = {"line": line_number, "time_s": time, "clock": clock, "tag": tag}
        if tag == "render-performance":
            pairs = dict(PAIR.findall(message))
            for required in ("displayFPS", "transferFPS", "meanCPUEncodeMs"):
                if required not in pairs:
                    raise ValueError(f"Missing {required} at line {line_number}")
            record["metrics"] = {
                name: numeric(pairs[field], f"{field} at line {line_number}")
                for field, name in FIELDS.items() if field in pairs
            }
        elif tag == "gpu-timing":
            metrics = {}
            # Use the recent-window values only. meanGPUms preceding this
            # section is cumulative since process start, so cannot be an A/B window.
            parts = message.split("| window ", 1)
            if len(parts) == 2:
                for stage in ("guest", "presentation", "snapshot"):
                    found = re.search(rf"\b{stage} GPUms=(\S+) queueMs=(\S+)", parts[1])
                    if not found:
                        raise ValueError(f"Incomplete GPU window at line {line_number}")
                    metrics[f"{stage}_window_mean_gpu_ms"] = numeric(found[1], stage)
                    metrics[f"{stage}_window_mean_queue_ms"] = numeric(found[2], stage)
            record["metrics"] = metrics
            record["counters"] = {}
            for stage in ("guest", "presentation", "snapshot"):
                found = re.search(rf"\b{stage} submitted=(\d+) completed=(\d+) failed=(\d+)", parts[0])
                if found:
                    for key, value in zip(("submitted", "completed", "failed"), found.groups()):
                        record["counters"][f"{stage}_{key}"] = int(value)
            untracked = re.search(r"\buntracked=(\d+)", parts[0])
            if untracked:
                record["counters"]["untracked"] = int(untracked[1])
        else:
            record["message"] = message
        records.append(record)
    return records


def describe(values):
    if not values:
        return None
    return {"count": len(values), "mean": statistics.fmean(values),
            "median": statistics.median(values), "min": min(values), "max": max(values)}


def metadata_issues(metadata):
    issues = []
    for key in (*MATCH_FIELDS, "build_id", "run_id"):
        value = metadata.get(key)
        if value is None or value == "" or (isinstance(value, str) and value.startswith("REPLACE")):
            issues.append(f"Missing run metadata: {key}")
    for key in ("eye_width", "eye_height"):
        if type(metadata.get(key)) is not int or metadata[key] <= 0:
            issues.append(f"{key} must be a positive integer")
    if not isinstance(metadata.get("settings"), dict) or not metadata.get("settings"):
        issues.append("settings must be a nonempty object containing the actual graphics/profile settings")
    def unfilled(value):
        if isinstance(value, dict):
            return any(unfilled(item) for item in value.values())
        if isinstance(value, list):
            return any(unfilled(item) for item in value)
        return value is None or (isinstance(value, str) and (not value or value.startswith("REPLACE")))
    if unfilled(metadata.get("settings")):
        issues.append("settings contains unfilled values; replace every template placeholder")
    if metadata.get("diagnostics_enabled") is not True:
        issues.append("diagnostics_enabled must be true for this measurement")
    if metadata.get("frame_capture_enabled") is not False:
        issues.append("frame_capture_enabled must be false to avoid full-frame diagnostic readbacks")
    return issues


def summarize(text, metadata, *, start=None, end=None, warmup_seconds=10.0):
    if not isinstance(metadata, dict):
        raise ValueError("Run metadata must be a JSON object")
    records = parse_log(text)
    render = [r for r in records if r["tag"] == "render-performance"]
    if not render:
        raise ValueError("No render-performance records; confirm WVRDiagnostics and capture the launcher log")
    warmup_seconds = numeric(warmup_seconds, "warmup_seconds")
    lower = clock_seconds(start) if start else render[0]["time_s"]
    upper = clock_seconds(end) if end else records[-1]["time_s"]
    if upper < lower:
        upper += 86400
    # An explicitly selected post-midnight interval belongs to the rollover day.
    if start and lower < records[0]["time_s"] and records[-1]["time_s"] >= 86400:
        if lower + 86400 <= records[-1]["time_s"] and (not end or upper < 86400):
            lower += 86400
            if end:
                upper += 86400
    cutoff = lower + warmup_seconds
    selected = []
    # First report's start is unknown. Every retained interval must begin after
    # the warmup boundary; do not include a partly warmed-up summary window.
    for previous, current in zip(render, render[1:]):
        if previous["time_s"] >= cutoff and current["time_s"] <= upper:
            if current["time_s"] <= previous["time_s"]:
                raise ValueError("Repeated performance timestamp; remove duplicated captures")
            selected.append({**current, "window_start_s": previous["time_s"],
                             "window_seconds_approx": current["time_s"] - previous["time_s"]})
    if not selected:
        raise ValueError("No complete measurement windows remain after selection and warmup")
    measurement_start = selected[0]["window_start_s"]
    measurement_end = selected[-1]["time_s"]
    duration = measurement_end - measurement_start
    issues = metadata_issues(metadata)
    if not start or not end:
        issues.append("Explicit --start and --end are required for a comparable scene interval")
    if duration < 60:
        issues.append(f"Only {duration:.3f}s measured; collect at least 60s after warmup")
    if len(selected) < 10:
        issues.append("Fewer than 10 complete render windows")
    if any(r["window_seconds_approx"] > 10 for r in selected):
        issues.append("A report gap exceeds 10s; possible stall, suspension, restart or missing log data")
    selected_gpu = []
    gpu = [r for r in records if r["tag"] == "gpu-timing"]
    for previous, current in zip(gpu, gpu[1:]):
        if previous["time_s"] >= measurement_start and current["time_s"] <= measurement_end:
            selected_gpu.append(current)
            for key, value in current["counters"].items():
                old = previous["counters"].get(key)
                if old is not None and value < old:
                    issues.append("GPU counters reset inside the selected interval; split sessions")
                if old is not None and (key.endswith("_failed") or key == "untracked") and value > old:
                    issues.append(f"GPU {key} increased by {value - old} at line {current['line']}")
    events = [r for r in records if measurement_start <= r["time_s"] <= measurement_end
              and "message" in r and re.search(
                  r"Presentation GPU command failed|Snapshot transfer failed|Renderer initialized|"
                  r"renderer.*(?:paus|invalid)|render task.*(?:cancel|exit|ended)",
                  r["message"], re.IGNORECASE)]
    if events:
        issues.append("Renderer lifecycle/failure events occur inside the selected interval")
    # A zero interval is the runtime's sentinel for an empty interval sample set.
    metrics = {}
    for name in FIELDS.values():
        values = [r["metrics"][name] for r in selected if name in r["metrics"]]
        if "interval" in name:
            values = [v for v in values if v > 0]
        metrics[name] = describe(values)
    gpu_names = sorted({name for r in selected_gpu for name in r["metrics"]})
    for name in gpu_names:
        metrics[name] = describe([r["metrics"][name] for r in selected_gpu if name in r["metrics"]])
    warnings = []
    if not gpu_names:
        warnings.append("No complete recent GPU timing windows selected; GPU costs unavailable")
    if any(metrics[name] is None for name in FIELDS.values() if "interval" in name):
        warnings.append("Fresh-frame interval percentiles unavailable (missing or empty samples)")
    return {
        "schema_version": SCHEMA, "kind": "winevision-frame-benchmark",
        "metadata": metadata,
        "source": {"log_sha256": hashlib.sha256(text.encode()).hexdigest()},
        "selection": {"requested_start": start, "requested_end": end,
                      "warmup_seconds": warmup_seconds, "measured_start_s": measurement_start,
                      "measured_end_s": measurement_end, "duration_seconds_approx": duration,
                      "render_windows": len(selected), "gpu_windows": len(selected_gpu)},
        "metrics": metrics, "comparison_blockers": sorted(set(issues)), "warnings": warnings,
        "limitations": LIMITATIONS, "render_windows": selected, "gpu_windows": selected_gpu,
        "events": events,
    }


def compare(baseline, candidate):
    for report in (baseline, candidate):
        if report.get("schema_version") != SCHEMA or report.get("kind") != "winevision-frame-benchmark":
            raise ValueError("Comparison requires reports from benchmark_frames.py summarize")
    blockers = [f"{name}: {issue}" for name, report in (("baseline", baseline), ("candidate", candidate))
                for issue in report["comparison_blockers"]]
    for field in MATCH_FIELDS:
        if baseline["metadata"].get(field) != candidate["metadata"].get(field):
            blockers.append(f"Mismatched {field}")
    durations = [r["selection"]["duration_seconds_approx"] for r in (baseline, candidate)]
    if abs(durations[1] - durations[0]) > 0.1 * max(durations):
        blockers.append("Measured durations differ by more than 10%")
    if baseline["metadata"].get("run_id") == candidate["metadata"].get("run_id"):
        blockers.append("Run IDs must differ")
    if baseline["source"]["log_sha256"] == candidate["source"]["log_sha256"]:
        blockers.append("Both reports use the same log capture; capture separate baseline/candidate runs")
    deltas = {}
    for name in baseline["metrics"].keys() & candidate["metrics"].keys():
        before, after = baseline["metrics"][name], candidate["metrics"][name]
        if before is None or after is None:
            continue
        # These are medians of window summaries, never pooled frame quantiles.
        a, b = before["median"], after["median"]
        deltas[name] = {"baseline_window_median": a, "candidate_window_median": b,
                        "delta": b - a, "delta_percent": (b / a - 1) * 100 if a else None}
    return {"schema_version": SCHEMA, "kind": "winevision-frame-comparison",
            "status": "inconclusive" if blockers else "comparable",
            "baseline_run": baseline["metadata"].get("run_id"),
            "candidate_run": candidate["metadata"].get("run_id"),
            "comparison_blockers": blockers, "window_median_deltas": dict(sorted(deltas.items())),
            "limitations": LIMITATIONS + ["A single matched A/B pair is descriptive evidence, not a causal "
                                           "or statistically significant improvement. Repeat in A/B/B/A order."]}


def markdown(report):
    lines = ["# WineVisionVR captured-frame benchmark", ""]
    if report["kind"] == "winevision-frame-comparison":
        lines += [f"Comparison: **{report['status']}**.", "",
                  "Values below are medians of logged window summaries.", "",
                  "| Metric | Baseline | Candidate | Change |", "|---|---:|---:|---:|"]
        for name, metric in report["window_median_deltas"].items():
            delta = metric["delta_percent"]
            change = f"{delta:+.2f}%" if delta is not None else "n/a (zero baseline)"
            lines.append(f"| {name} | {metric['baseline_window_median']:.3f} | "
                         f"{metric['candidate_window_median']:.3f} | {change} |")
    else:
        selection = report["selection"]
        lines += [f"Selected {selection['render_windows']} complete render windows covering approximately "
                  f"{selection['duration_seconds_approx']:.3f}s after warmup.", "",
                  "These are statistics across reported windows, not per-frame percentiles.", "",
                  "| Metric | Windows | Median | Minimum | Maximum |", "|---|---:|---:|---:|---:|"]
        for name, metric in report["metrics"].items():
            if metric:
                lines.append(f"| {name} | {metric['count']} | {metric['median']:.3f} | "
                             f"{metric['min']:.3f} | {metric['max']:.3f} |")
    for heading, values in (("Comparison blockers", report["comparison_blockers"]),
                            ("Warnings", report.get("warnings", [])),
                            ("Interpretation", report["limitations"])):
        if values:
            lines.extend(["", f"## {heading}", "", *[f"- {value}" for value in values]])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    summary = commands.add_parser("summarize", help="Analyze a copied Documents/launcher-log.txt")
    summary.add_argument("log", type=Path)
    summary.add_argument("--metadata", type=Path, required=True)
    summary.add_argument("--start", help="Scene interval start, HH:mm:ss.SSS, using the log clock")
    summary.add_argument("--end", help="Scene interval end, HH:mm:ss.SSS, using the log clock")
    summary.add_argument("--warmup-seconds", type=float, default=10.0)
    comparison = commands.add_parser("compare", help="Compare two saved summaries")
    comparison.add_argument("baseline", type=Path)
    comparison.add_argument("candidate", type=Path)
    for command in (summary, comparison):
        command.add_argument("--output", type=Path, required=True, help="Output JSON path")
        command.add_argument("--markdown", type=Path, help="Optional readable report path")
    args = parser.parse_args()
    try:
        inputs = ([args.log, args.metadata] if args.command == "summarize"
                  else [args.baseline, args.candidate])
        outputs = [args.output] + ([args.markdown] if args.markdown else [])
        resolved_outputs = [path.resolve() for path in outputs]
        if len(set(resolved_outputs)) != len(outputs) or set(resolved_outputs) & {p.resolve() for p in inputs}:
            raise ValueError("Output paths must be distinct from each other and from all inputs")
        if args.command == "summarize":
            report = summarize(args.log.read_text(), json.loads(args.metadata.read_text()),
                               start=args.start, end=args.end, warmup_seconds=args.warmup_seconds)
            report["source"]["log_path"] = str(args.log.resolve())
        else:
            report = compare(json.loads(args.baseline.read_text()), json.loads(args.candidate.read_text()))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(markdown(report))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(f"Saved {args.output}; {len(report['comparison_blockers'])} comparison blocker(s)")
    return 2 if report["comparison_blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Synthetic log fixtures verify measurement interpretation, not headset FPS."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "benchmark_frames.py"
spec = importlib.util.spec_from_file_location("benchmark_frames", SCRIPT)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def metadata(run="baseline"):
    return {"run_id": run, "build_id": "fixture-commit-" + run,
            "game": "Synthetic fixture", "game_version": "1", "scene": "test",
            "device_model": "fixture only", "os_version": "fixture only",
            "eye_width": 1888, "eye_height": 1792, "settings": {"quality": "fixed"},
            "cache_state": "warm", "thermal_start": "nominal",
            "diagnostics_enabled": True, "frame_capture_enabled": False}


def clock(seconds):
    seconds %= 86400
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}.000"


def log(*, fps=30, start=36000, windows=20, interval=5, gpu=True):
    lines = []
    for number in range(windows):
        time = clock(start + number * interval)
        if gpu:
            stages = " | ".join(f"{name} submitted={number * 400} completed={number * 399} "
                                "failed=0 meanGPUms=99.000 oldestPending=0.001s"
                                for name in ("guest", "presentation", "snapshot"))
            lines.append(f"{time} [gpu-timing] {stages} | untracked=0 | window "
                         "guest GPUms=7.000 queueMs=3.000 presentation GPUms=2.000 queueMs=1.000 "
                         "snapshot GPUms=1.000 queueMs=0.500")
        lines.append(f"{time} [render-performance] displayFPS=90.0 transferFPS={fps} "
                     "snapshotReadWriteMiBps=900.0 meanCPUEncodeMs=0.500 "
                     "newFrameMedianMs=33.333 newFrameP95Ms=44.444")
    return "\n".join(lines) + "\n"


def summary(text=None, meta=None, **options):
    defaults = {"start": "10:00:00.000", "end": "10:01:35.000"}
    defaults.update(options)
    return benchmark.summarize(text or log(), meta or metadata(), **defaults)


class BenchmarkTests(unittest.TestCase):
    def test_fresh_frames_are_distinct_from_display_and_cumulative_gpu(self):
        report = summary()
        self.assertEqual(report["metrics"]["fresh_transfer_fps"]["median"], 30)
        self.assertEqual(report["metrics"]["display_submission_fps"]["median"], 90)
        self.assertEqual(report["metrics"]["guest_window_mean_gpu_ms"]["median"], 7)
        self.assertEqual(report["comparison_blockers"], [])
        self.assertNotIn("simulation_fps", report["metrics"])

    def test_warmup_excludes_straddling_windows_and_unknown_first_window(self):
        report = summary(warmup_seconds=7)
        self.assertEqual(report["render_windows"][0]["clock"], "10:00:15.000")
        self.assertEqual(report["selection"]["duration_seconds_approx"], 85)
        self.assertEqual(summary(warmup_seconds=0)["render_windows"][0]["clock"], "10:00:05.000")

    def test_window_p95_values_do_not_become_global_frame_percentiles(self):
        report = summary()
        metric = report["metrics"]["reported_window_p95_transfer_interval_ms"]
        self.assertEqual(metric["median"], 44.444)
        self.assertEqual(set(metric), {"count", "mean", "median", "min", "max"})
        self.assertIn("not per-frame percentiles", benchmark.markdown(report))

    def test_zero_and_legacy_missing_intervals_are_unavailable(self):
        for text in (log(fps=0).replace("33.333", "0").replace("44.444", "0"),
                     log().replace(" newFrameMedianMs=33.333 newFrameP95Ms=44.444", "")):
            report = summary(text)
            self.assertIsNone(report["metrics"]["reported_window_p95_transfer_interval_ms"])
            self.assertTrue(report["warnings"])
        self.assertEqual(summary(log(fps=0))["metrics"]["fresh_transfer_fps"]["median"], 0)

    def test_short_missing_metadata_and_missing_selection_are_inconclusive(self):
        report = summary(log(windows=5), {"run_id": "only"}, start=None, end=None)
        blockers = "\n".join(report["comparison_blockers"])
        self.assertIn("Missing run metadata", blockers)
        self.assertIn("at least 60s", blockers)
        self.assertIn("Explicit --start", blockers)

    def test_unfilled_nested_settings_block_comparison(self):
        meta = metadata()
        meta["settings"] = {"graphics": {"quality": "REPLACE"}}
        self.assertTrue(any("unfilled values" in issue for issue in summary(meta=meta)["comparison_blockers"]))
        with self.assertRaisesRegex(ValueError, "JSON object"):
            benchmark.summarize(log(), ["invalid metadata"])

    def test_invalid_negative_nonfinite_and_partial_metrics_fail_closed(self):
        for value in ("nan", "inf", "-1", "garbage"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                summary(log().replace("transferFPS=30", "transferFPS=" + value))
        with self.assertRaisesRegex(ValueError, "Missing transferFPS"):
            summary(log().replace("transferFPS=30", "other=30"))
        with self.assertRaisesRegex(ValueError, "Incomplete GPU"):
            summary(log().replace("queueMs=3.000", "queue=3.000"))

    def test_midnight_rollover_and_explicit_post_midnight_selection(self):
        capture = log(start=86350, windows=40)
        report = summary(capture, start="23:59:10.000", end="00:01:00.000")
        self.assertEqual(report["selection"]["duration_seconds_approx"], 100)
        report = summary(capture, start="00:00:00.000", end="00:01:30.000")
        self.assertEqual(report["selection"]["measured_start_s"], 86410)
        self.assertEqual(report["selection"]["duration_seconds_approx"], 80)

    def test_backwards_clock_duplicate_render_and_invalid_clock_rejected(self):
        for text in (log().replace("10:00:25.000", "10:00:01.000"),
                     log().replace("10:00:25.000", "10:00:20.000"),
                     log().replace("10:00:25.000", "10:70:25.000")):
            with self.assertRaises(ValueError):
                summary(text)

    def test_stalls_are_retained_and_block_comparison(self):
        report = summary(log(interval=15, windows=10), end="10:02:15.000")
        self.assertTrue(any("gap exceeds" in issue for issue in report["comparison_blockers"]))
        self.assertEqual(report["selection"]["duration_seconds_approx"], 120)

    def test_failure_and_gpu_counter_reset_are_visible(self):
        text = log().replace("10:00:25.000 [render-performance]",
                             "10:00:24.000 [lifecycle] Layer renderer paused\n"
                             "10:00:25.000 [render-performance]")
        # Keep all log lines in time order.
        text = "\n".join(sorted(text.splitlines()))
        text = text.replace("guest submitted=2000 completed=1995 failed=0",
                            "guest submitted=2000 completed=1995 failed=1")
        report = summary(text)
        self.assertEqual(len(report["events"]), 1)
        self.assertTrue(any("guest_failed increased" in issue for issue in report["comparison_blockers"]))
        self.assertTrue(any("counters reset" in issue for issue in report["comparison_blockers"]))

    def test_no_gpu_data_does_not_invent_gpu_time(self):
        report = summary(log(gpu=False))
        self.assertNotIn("guest_window_mean_gpu_ms", report["metrics"])
        self.assertIn("GPU costs unavailable", report["warnings"][0])

    def test_matched_comparison_reports_a_descriptive_delta(self):
        comparison = benchmark.compare(summary(), summary(log(fps=36), metadata("candidate")))
        self.assertEqual(comparison["status"], "comparable")
        self.assertAlmostEqual(comparison["window_median_deltas"]["fresh_transfer_fps"]["delta_percent"], 20)
        self.assertEqual(comparison["window_median_deltas"]["display_submission_fps"]["delta"], 0)

    def test_different_game_resolution_capture_or_settings_block_comparison(self):
        for key, value in (("game", "Another game"), ("eye_width", 1000),
                           ("settings", {"quality": "changed"}), ("frame_capture_enabled", True)):
            candidate = metadata("candidate")
            candidate[key] = value
            comparison = benchmark.compare(summary(), summary(log(fps=36), candidate))
            self.assertEqual(comparison["status"], "inconclusive")
            self.assertIn(f"Mismatched {key}", comparison["comparison_blockers"])
        same_log = benchmark.compare(summary(), summary(meta=metadata("candidate")))
        self.assertEqual(same_log["status"], "inconclusive")

    def test_zero_baseline_has_no_infinite_percentage(self):
        comparison = benchmark.compare(summary(log(fps=0)), summary(log(fps=30), metadata("candidate")))
        self.assertIsNone(comparison["window_median_deltas"]["fresh_transfer_fps"]["delta_percent"])
        json.dumps(comparison, allow_nan=False)

    def test_cli_writes_artifacts_and_returns_nonzero_for_inconclusive(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / "launcher.log").write_text(log())
            (root / "run.json").write_text(json.dumps(metadata()))
            command = [sys.executable, str(SCRIPT), "summarize", str(root / "launcher.log"),
                       "--metadata", str(root / "run.json"), "--output", str(root / "report.json"),
                       "--markdown", str(root / "report.md")]
            inconclusive = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(inconclusive.returncode, 2, inconclusive.stderr)
            self.assertTrue((root / "report.md").exists())
            complete = subprocess.run(command + ["--start", "10:00:00.000", "--end", "10:01:35.000"],
                                      capture_output=True, text=True)
            self.assertEqual(complete.returncode, 0, complete.stderr)
            report = json.loads((root / "report.json").read_text())
            self.assertEqual(report["comparison_blockers"], [])
            self.assertEqual(len(report["source"]["log_sha256"]), 64)

    def test_cli_preserves_input_when_output_path_collides(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / "launcher.log").write_text(log())
            (root / "run.json").write_text(json.dumps(metadata()))
            result = subprocess.run([sys.executable, str(SCRIPT), "summarize", str(root / "launcher.log"),
                                     "--metadata", str(root / "run.json"), "--output", str(root / "launcher.log")],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("distinct", result.stderr)
            self.assertEqual((root / "launcher.log").read_text(), log())


if __name__ == "__main__":
    unittest.main()

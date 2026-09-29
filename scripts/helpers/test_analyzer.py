import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import Mock


class AnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        boto3 = types.ModuleType("boto3")
        boto3.client = Mock(side_effect=lambda name: Mock())
        sys.modules["boto3"] = boto3
        os.environ.setdefault("LOGS_BUCKET", "test-logs")
        spec = importlib.util.spec_from_file_location(
            "analyzer", os.path.join(os.path.dirname(__file__), "..", "lambdas", "analyzer.py")
        )
        cls.analyzer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.analyzer)

    def test_versions_failures_and_retries(self):
        def event(stream, timestamp, message):
            return {"logStreamName": stream, "timestamp": timestamp, "message": message}

        report = lambda request_id, duration, extra="": (
            f"REPORT RequestId: {request_id}\tDuration: {duration} ms\t"
            f"Billed Duration: {duration} ms\tMemory Size: 512 MB\t"
            f"Max Memory Used: 100 MB\t{extra}\n"
        )
        events = [
            event("[1]old", 1, "START RequestId: old Version: 1"),
            event("[1]old", 2, "Class not found: java_processor.Main"),
            event("[1]old", 3, report("old", 2)),
            event("[3]new", 4, "START RequestId: good Version: 3"),
            event("[3]new", 5, "Processed: image.jpg"),
            event("[3]new", 6, report("good", 600)),
            event("[3]new", 7, "START RequestId: retry Version: 3"),
            event("[3]new", 8, "Processed: image.jpg"),
            event("[3]new", 9, report("retry", 400)),
            event("[3]new", 10, "START RequestId: unconfirmed Version: 3"),
            event("[3]new", 11, report("unconfirmed", 1, "Status: error")),
        ]
        self.analyzer.get_log_events = Mock(return_value=events)
        result = self.analyzer.get_cloudwatch_metrics("java_function_snapstart", None, None)
        self.assertEqual(result["1"]["successful_invocations"], 0)
        self.assertIsNone(result["1"]["duration_ms_success_only"])
        self.assertEqual(result["3"]["attempts"], 3)
        self.assertEqual(result["3"]["successful_invocations"], 2)
        self.assertEqual(result["3"]["unique_processed_images"], 1)
        self.assertEqual(result["3"]["duration_ms_success_only"]["avg"], 500)
        self.assertIsNone(result["3"]["restore_duration_ms_observed"])

    def test_startup_is_added_only_to_its_own_invocation(self):
        def event(timestamp, message):
            return {"logStreamName": "[3]stream", "timestamp": timestamp, "message": message}

        def report(request_id, extra=""):
            return (f"REPORT RequestId: {request_id}\tDuration: 400 ms\t"
                    "Billed Duration: 401 ms\tMemory Size: 512 MB\t"
                    f"Max Memory Used: 100 MB\t{extra}")

        events = [
            event(1, "RESTORE_REPORT Restore Duration: 50 ms"),
            event(2, "START RequestId: first Version: 3"),
            event(3, "Processed: a.jpg"),
            event(3, "BenchmarkStages: client_ms=100.00 get_ms=200.00 process_ms=50.00 put_ms=50.00"),
            event(4, report("first", "Restore Duration: 50 ms")),
            event(5, "START RequestId: second Version: 3"),
            event(6, "Processed: b.jpg"),
            event(6, "BenchmarkStages: client_ms=0.00 get_ms=300.00 process_ms=50.00 put_ms=50.00"),
            event(7, report("second")),
        ]
        self.analyzer.get_log_events = Mock(return_value=events)
        version = self.analyzer.get_cloudwatch_metrics("java_function_snapstart", None, None)["3"]
        self.assertEqual(version["restore_duration_ms_observed"]["avg"], 50)
        self.assertEqual(version["lambda_latency_ms_including_observed_startup"]["avg"], 425)
        self.assertEqual(version["cold_invocation_latency_ms_observed"]["avg"], 450)
        self.assertEqual(version["warm_invocation_latency_ms_observed"]["avg"], 400)
        self.assertEqual(version["invocations_with_observed_startup"], 1)
        self.assertEqual(version["stages_cold_success_only"]["client_ms"]["avg"], 100)
        self.assertEqual(version["stages_warm_success_only"]["get_ms"]["avg"], 300)

    def test_future_end_is_rejected_before_querying_aws(self):
        with self.assertRaisesRegex(ValueError, "end must not be in the future"):
            self.analyzer.handler({
                "start": "2026-09-28T17:00:00Z",
                "end": "2099-09-28T23:00:00Z",
            }, None)

    def test_normal_java_init_is_included_in_latency(self):
        stream = "[$LATEST]cold"
        self.analyzer.get_log_events = Mock(return_value=[
            {"logStreamName": stream, "timestamp": 1,
             "message": "START RequestId: cold Version: $LATEST"},
            {"logStreamName": stream, "timestamp": 2, "message": "Processed: a.jpg"},
            {"logStreamName": stream, "timestamp": 3,
             "message": "REPORT RequestId: cold\tDuration: 400 ms\tBilled Duration: 401 ms\t"
                        "Memory Size: 512 MB\tMax Memory Used: 100 MB\tInit Duration: 1000 ms"},
        ])
        version = self.analyzer.get_cloudwatch_metrics("java_function", None, None)["$LATEST"]
        self.assertEqual(version["init_duration_ms_observed"]["avg"], 1000)
        self.assertEqual(version["lambda_latency_ms_including_observed_startup"]["avg"], 1400)


if __name__ == "__main__":
    unittest.main()

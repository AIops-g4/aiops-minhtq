import http.client
import json
import random
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

import stream_generator
from pipeline import AlertWriter, StreamingDetector, make_handler, validate_payload


def payload(metrics, logs=None):
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "metrics": metrics,
        "logs": logs or [],
    }


class StreamingDetectorTests(unittest.TestCase):
    def setUp(self):
        self.rng = random.Random(42)

    def warm_up(self, detector, samples=80):
        alerts = []
        for tick in range(samples):
            item = payload(stream_generator.generate_baseline(self.rng, tick / 120))
            alert = detector.process(item)
            if alert:
                alerts.append(alert)
        return alerts

    def assert_detects(self, fault_type, injector, max_samples):
        detector = StreamingDetector()
        self.assertEqual(self.warm_up(detector), [])
        alert = None
        for tick in range(max_samples):
            metrics = stream_generator.generate_baseline(self.rng, 1 + tick / 120)
            metrics = injector(metrics, self.rng, tick / 120)
            alert = detector.process(payload(metrics))
            if alert:
                break
        self.assertIsNotNone(alert)
        self.assertEqual(alert["type"], fault_type)

    def test_no_false_alert_during_baseline(self):
        detector = StreamingDetector()
        self.assertEqual(self.warm_up(detector, samples=1000), [])

    def test_detects_memory_leak(self):
        self.assert_detects("memory_leak", stream_generator.inject_memory_leak, 120)

    def test_detects_traffic_spike(self):
        self.assert_detects("traffic_spike", stream_generator.inject_traffic_spike, 30)

    def test_detects_dependency_timeout(self):
        self.assert_detects(
            "dependency_timeout", stream_generator.inject_dependency_timeout, 30
        )

    def test_alert_is_emitted_only_once(self):
        detector = StreamingDetector()
        self.warm_up(detector)
        alerts = []
        for tick in range(100):
            metrics = stream_generator.generate_baseline(self.rng, 1 + tick / 120)
            metrics = stream_generator.inject_traffic_spike(metrics, self.rng, tick / 120)
            alert = detector.process(payload(metrics))
            if alert:
                alerts.append(alert)
        self.assertEqual(len(alerts), 1)

    def test_rejects_missing_metric(self):
        item = payload(stream_generator.generate_baseline(self.rng, 0))
        del item["metrics"]["queue_depth"]
        with self.assertRaises(ValueError):
            validate_payload(item)

    def test_http_ingest_endpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            detector = StreamingDetector()
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                make_handler(detector, AlertWriter(Path(directory) / "alerts.jsonl")),
            )
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                item = payload(stream_generator.generate_baseline(self.rng, 0))
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
                connection.request(
                    "POST",
                    "/ingest",
                    body=json.dumps(item),
                    headers={"Content-Type": "application/json"},
                )
                response = connection.getresponse()
                body = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertEqual(body["status"], "ok")
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == "__main__":
    unittest.main()

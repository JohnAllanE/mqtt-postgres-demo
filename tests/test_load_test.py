import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from load_test import BENCHMARK_REPEATS, BENCHMARK_WORKLOADS, VARIANTS, validate_sample_count  # noqa: E402


class ValidateSampleCountTests(unittest.TestCase):
    def test_accepts_a_million_or_more_points(self):
        self.assertEqual(validate_sample_count(1_000_000), 1_000_000)
        self.assertEqual(validate_sample_count("2_000_000"), 2_000_000)

    def test_requires_complete_ten_sensor_messages(self):
        with self.assertRaisesRegex(ValueError, "multiple of 10"):
            validate_sample_count(1_000_001)

    def test_rejects_unsafe_bounds_and_non_numbers(self):
        for value in (9_990, 20_000_010, None, "many"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_sample_count(value)


class BenchmarkDefinitionTests(unittest.TestCase):
    def test_every_workload_has_an_equivalent_query_for_each_variant(self):
        variant_keys = {key for key, _table, _label in VARIANTS}
        self.assertEqual(BENCHMARK_REPEATS, 3)
        self.assertEqual(len(BENCHMARK_WORKLOADS), 3)
        for workload, label, queries in BENCHMARK_WORKLOADS:
            with self.subTest(workload=workload):
                self.assertTrue(label)
                self.assertEqual(set(queries), variant_keys)
                self.assertTrue(all("SELECT" in query for query in queries.values()))


if __name__ == "__main__":
    unittest.main()

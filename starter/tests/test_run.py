"""Check that test evaluation is gated by an earlier fixed dev selection."""
from pathlib import Path
from contextlib import contextmanager
import shutil
import unittest
from unittest.mock import patch
import uuid

from src import run
from src.artifacts import ROOT, read_json, write_json


@contextmanager
def test_directory():
    # mkdir inherits normal Windows workspace ACLs; tempfile's private 0700
    # directories can become inaccessible to the managed Windows sandbox.
    base = (ROOT / "starter/tests").resolve()
    folder = base / ("run_fixture_" + uuid.uuid4().hex)
    folder.mkdir()
    try:
        yield str(folder)
    finally:
        resolved = folder.resolve()
        if resolved.parent != base or not resolved.name.startswith("run_fixture_"):
            raise RuntimeError("Refusing unexpected fixture cleanup")
        shutil.rmtree(resolved)


class RunOrderingTests(unittest.TestCase):
    def test_no_selection_refuses_test_without_searching(self):
        with test_directory() as folder:
            self.assertTrue(Path(folder).resolve().is_relative_to(ROOT))
            with patch.object(run, "RESULTS", Path(folder)), patch.object(run, "_search_split") as search:
                with self.assertRaisesRegex(ValueError, "Run dev"):
                    run.run_test({"fingerprint": "fixed"})
                search.assert_not_called()

    def test_changed_configuration_refuses_test_without_searching(self):
        with test_directory() as folder:
            self.assertTrue(Path(folder).resolve().is_relative_to(ROOT))
            path = Path(folder)
            write_json(path / "selection.json", {"fingerprint": "old"})
            with patch.object(run, "RESULTS", path), patch.object(run, "_search_split") as search:
                with self.assertRaisesRegex(ValueError, "Configuration changed"):
                    run.run_test({"fingerprint": "new"})
                search.assert_not_called()

    def test_exposure_is_recorded_before_search(self):
        with test_directory() as folder:
            self.assertTrue(Path(folder).resolve().is_relative_to(ROOT))
            path = Path(folder)
            write_json(path / "selection.json", {"fingerprint": "fixed", "selected_strategy": "B", "dev_trace_sha256": {}})

            def search(context, split):
                self.assertEqual(split, "test")
                exposures = read_json(path / "test_exposure.json")
                self.assertEqual(exposures[0]["selected_strategy"], "B")
                self.assertEqual(exposures[0]["holdout_status"], "initial_holdout_on_fixed_configuration")
                return []

            with patch.object(run, "RESULTS", path), patch.object(run, "_search_split", side_effect=search), \
                    patch.object(run, "_write_metrics"):
                run.run_test({"fingerprint": "fixed"})
                self.assertTrue((path / "test_run.json").exists())

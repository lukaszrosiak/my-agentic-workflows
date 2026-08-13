import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api_balances as ab  # noqa: E402


class ExtractValueTest(unittest.TestCase):
    def test_simple_key(self) -> None:
        self.assertEqual(ab.extract_value({"a": 1}, "a"), 1)

    def test_nested_key(self) -> None:
        self.assertEqual(ab.extract_value({"a": {"b": 2}}, "a.b"), 2)

    def test_list_index(self) -> None:
        data = {"items": [{"v": 10}, {"v": 20}]}
        self.assertEqual(ab.extract_value(data, "items[1].v"), 20)

    def test_empty_bracket_takes_first(self) -> None:
        data = {"balance_infos": [{"total_balance": "12.34"}]}
        self.assertEqual(
            ab.extract_value(data, "balance_infos[].total_balance"), "12.34"
        )

    def test_missing_key_raises(self) -> None:
        with self.assertRaises(KeyError):
            ab.extract_value({"a": 1}, "b")

    def test_empty_list_raises(self) -> None:
        with self.assertRaises(IndexError):
            ab.extract_value({"items": []}, "items[].v")

    def test_empty_path_raises(self) -> None:
        with self.assertRaises(ValueError):
            ab.extract_value({}, "")


class ConfigTest(unittest.TestCase):
    def test_from_dict_requires_name_and_url(self) -> None:
        with self.assertRaises(ValueError):
            ab.ApiConfig.from_dict({"name": "x"})

    def test_load_default_config(self) -> None:
        configs = ab.load_config(None)
        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0].name, "DeepSeek")

    def test_load_config_from_file(self, tmp_path_name: str = "") -> None:
        data = [{"name": "Foo", "url": "http://x", "value_path": "v"}]
        path = "/tmp/opencode/test_config.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        configs = ab.load_config(path)
        self.assertEqual(configs[0].name, "Foo")
        os.remove(path)

    def test_load_config_non_list_raises(self) -> None:
        path = "/tmp/opencode/test_config_bad.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"not": "a list"}, fh)
        with self.assertRaises(ValueError):
            ab.load_config(path)
        os.remove(path)


class RenderTableTest(unittest.TestCase):
    def test_render_basic(self) -> None:
        rows = [ab.Row(name="A", value="1"), ab.Row(name="BB", value="22")]
        table = ab.render_table(rows)
        self.assertIn("NAME", table)
        self.assertIn("VALUE", table)
        self.assertIn("A", table)
        self.assertIn("22", table)


class FetchValueTest(unittest.TestCase):
    def test_missing_env_var_raises_api_error(self) -> None:
        cfg = ab.ApiConfig(
            name="X", url="http://x", env_var="NON_EXISTENT_VAR_XYZ"
        )
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ab.ApiError):
                ab.fetch_value(cfg)

    def test_fetch_value_success(self) -> None:
        cfg = ab.ApiConfig(name="X", url="http://x", value_path="v")
        payload = json.dumps({"v": "42"}).encode("utf-8")

        class FakeResp:
            def __enter__(self) -> "FakeResp":
                return self

            def __exit__(self, *exc: object) -> None:
                return None

            def read(self) -> bytes:
                return payload

        with mock.patch.object(
            ab.urllib.request, "urlopen", return_value=FakeResp()
        ):
            self.assertEqual(ab.fetch_value(cfg), "42")

    def test_poll_all_captures_errors(self) -> None:
        cfg = ab.ApiConfig(name="X", url="http://x", env_var="MISSING_VAR_ABC")
        with mock.patch.dict(os.environ, {}, clear=True):
            rows = ab.poll_all([cfg])
        self.assertTrue(rows[0].is_error)
        self.assertTrue(rows[0].value.startswith("ERROR:"))


class RunOnceTest(unittest.TestCase):
    def test_run_once_returns_table_string(self) -> None:
        cfg = ab.ApiConfig(name="X", url="http://x", env_var="MISSING_VAR_ABC")
        with mock.patch.dict(os.environ, {}, clear=True):
            table = ab.run_once([cfg])
        self.assertIn("NAME", table)
        self.assertIn("ERROR", table)


if __name__ == "__main__":
    unittest.main()

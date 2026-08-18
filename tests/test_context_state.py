import argparse
import concurrent.futures
import os
import tempfile
import unittest

from sourceknight.context import Context
from sourceknight.errors import SkError
from sourceknight.state import State


def _make_dummy_manifest(tmpdir: str) -> None:
    yaml_content = """project:
  sourceknight: 0.5
  name: test-proj
"""
    with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
        f.write(yaml_content)


class TestState(unittest.TestCase):
    def test_state_basic_and_clean_lifecycle(self):
        st = State()
        self.assertTrue(st.clean())
        self.assertEqual(st.dependencies, {})
        self.assertEqual(st.build, {})

        st.update(dependencies={"dep1": {"version": "v1.0"}})
        self.assertFalse(st.clean())
        self.assertEqual(st.dependencies["dep1"]["version"], "v1.0")

        st.update(build={"dep1": {"version": "v1.0"}})
        self.assertEqual(st.build["dep1"]["version"], "v1.0")

        st.clear_build_state()
        self.assertEqual(st.build, {})

    def test_state_deep_merge(self):
        st = State()
        st.update(dependencies={"dep1": {"name": "dep1", "nested": {"a": 1, "b": 2}}})
        st.update(dependencies={"dep1": {"nested": {"b": 3, "c": 4}}})

        expected = {"name": "dep1", "nested": {"a": 1, "b": 3, "c": 4}}
        self.assertEqual(st.dependencies["dep1"], expected)

    def test_state_serialization_and_from_yaml(self):
        initial_data = {
            "dependencies": {"foo": {"version": "1.0"}},
            "build": {"foo": {"version": "1.0"}},
        }
        st = State.from_yaml(None, initial_data)
        self.assertTrue(st.clean())
        self.assertEqual(st.dependencies["foo"]["version"], "1.0")
        serialized = st.serialize()
        self.assertEqual(serialized["dependencies"]["foo"]["version"], "1.0")

    def test_state_missing_attribute(self):
        st = State()
        with self.assertRaises(AttributeError):
            _ = st.non_existent_field

    def test_state_thread_safety(self):
        st = State()

        def worker(idx: int) -> None:
            st.update(dependencies={f"dep_{idx}": {"val": idx}})

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(worker, i) for i in range(50)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        self.assertEqual(len(st.dependencies), 50)


class TestContext(unittest.TestCase):
    def test_context_manifest_discovery_and_save(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_content = """project:
  sourceknight: 0.5
  name: test-ctx
"""
            with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
                f.write(yaml_content)

            with Context(tmpdir) as ctx:
                self.assertEqual(ctx.defs["name"], "test-ctx")
                ctx.state.update(dependencies={"dummy": {"ver": "1"}})

            # After exit, state.yaml should be created
            state_file = os.path.join(tmpdir, ".sourceknight", "state.yaml")
            self.assertTrue(os.path.exists(state_file))

            # Re-entering should load the existing state
            with Context(tmpdir) as ctx2:
                self.assertIn("dummy", ctx2.state.dependencies)

    def test_context_invalid_manifest_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
                f.write("invalid_root_without_project: true\n")

            with self.assertRaises(SkError) as cm, Context(tmpdir):
                pass
            self.assertIn("must define a root 'project' section", str(cm.exception))

    def test_context_missing_manifest_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(SkError) as cm, Context(tmpdir):
                pass
            self.assertIn("sourceknight.yaml", str(cm.exception))

    def test_context_overrides_priority(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_content = """project:
  sourceknight: 0.5
  name: override-test
  dependencies:
    - name: sm
      type: smdrop
      version: 1.10.x
    - name: colors
      type: git
      version: v1.0
"""
            with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
                f.write(yaml_content)

            os.environ["SK_OVERRIDE_SM"] = "1.11.x"
            args = argparse.Namespace(override_dep=["sm=1.12.x", "colors=v2.0"])

            try:
                with Context(tmpdir, args=args) as ctx:
                    deps = {d["name"]: d["version"] for d in ctx.defs["dependencies"]}
                    # CLI overrides have highest precedence
                    self.assertEqual(deps["sm"], "1.12.x")
                    self.assertEqual(deps["colors"], "v2.0")
            finally:
                del os.environ["SK_OVERRIDE_SM"]

    def test_context_env_overrides(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_content = """project:
  sourceknight: 0.5
  name: env-override-test
  dependencies:
    - name: sm
      type: smdrop
      version: 1.10.x
    - name: my-plugin
      type: git
      version: v1.0
"""
            with open(os.path.join(tmpdir, "sourceknight.yaml"), "w") as f:
                f.write(yaml_content)

            os.environ["SK_OVERRIDE_SM"] = "1.12.x"
            os.environ["SK_OVERRIDE_MY_PLUGIN"] = "v3.0"

            try:
                with Context(tmpdir) as ctx:
                    deps = {d["name"]: d["version"] for d in ctx.defs["dependencies"]}
                    self.assertEqual(deps["sm"], "1.12.x")
                    self.assertEqual(deps["my-plugin"], "v3.0")
            finally:
                del os.environ["SK_OVERRIDE_SM"]
                del os.environ["SK_OVERRIDE_MY_PLUGIN"]


if __name__ == "__main__":
    unittest.main()

"""The training build is part of the release, not only a local target."""

import os
import tomllib
import unittest

import yaml

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)


def _read(relative):
    with open(os.path.join(REPO_ROOT, relative), encoding="utf-8") as handle:
        return handle.read()


class TestReleaseMatrix(unittest.TestCase):
    def test_release_builds_cpu_train_on_windows(self):
        workflow = yaml.safe_load(_read(".github/workflows/release.yml"))
        entries = workflow["jobs"]["build"]["strategy"]["matrix"]["include"]
        train = [
            entry for entry in entries if entry["target"] == "win-cpu-train"
        ]
        self.assertEqual(len(train), 1)
        self.assertEqual(train[0]["os"], "windows-latest")
        self.assertEqual(train[0]["lock"], "requirements-lock-win-train.txt")

    def test_training_lock_covers_the_release_stack(self):
        text = _read("requirements-lock-win-train.txt")
        for package in (
            "torch==",
            "torchvision==",
            "ultralytics==",
            "onnxslim==",
        ):
            self.assertIn(package, text)
        self.assertIn("--index-url https://pypi.org/simple", text)
        self.assertIn(
            "--extra-index-url https://download.pytorch.org/whl/cpu", text
        )

    def test_pyproject_declares_the_training_extra(self):
        with open(os.path.join(REPO_ROOT, "pyproject.toml"), "rb") as handle:
            pyproject = tomllib.load(handle)
        extras = pyproject["project"]["optional-dependencies"]
        names = {
            entry.split(">", 1)[0].split("=", 1)[0]
            for entry in extras["cpu-train"]
        }
        self.assertEqual(
            names, {"torch", "torchvision", "ultralytics", "onnxslim"}
        )

    def test_build_script_packages_the_onedir_asset(self):
        script = _read("scripts/build_executable.sh")
        self.assertIn("package_windows_onedir_zip", script)
        self.assertIn("Compress-Archive", script)
        self.assertIn('"${target_dir}-win64.zip"', script)
        self.assertIn("x-anylabeling-win-cpu-train.spec", script)

    def test_training_spec_collects_lazy_ultralytics_callbacks(self):
        spec = _read(
            "packaging/pyinstaller/specs/" "x-anylabeling-win-cpu-train.spec"
        )
        self.assertIn(
            "collect_submodules('ultralytics.utils.callbacks')", spec
        )
        self.assertIn("*ultralytics_callbacks", spec)


if __name__ == "__main__":
    unittest.main()

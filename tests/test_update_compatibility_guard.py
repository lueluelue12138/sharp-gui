import unittest

from tools import check_update_compatibility as guard


def manifest(revision):
    return {"portableRuntimeRevision": revision}


class UpdateCompatibilityGuardTests(unittest.TestCase):
    def test_runtime_sensitive_path_classification(self):
        cases = [
            ("backend/services/new_module.py", False),
            ("frontend/src/components/NewPanel.tsx", False),
            ("frontend/dist/assets/index.js", False),
            ("requirements-dev.txt", False),
            ("requirements.txt", True),
            ("requirements-video.txt", True),
            ("install.bat", True),
            ("build_portable_release.bat", True),
            ("tools/install_torch.py", True),
            ("tools/build_portable_package.ps1", True),
            ("tools/portable_update_common.ps1", True),
            ("pyproject.toml", True),
        ]
        for path, expected in cases:
            with self.subTest(path=path):
                self.assertIs(guard.is_runtime_sensitive(path), expected)

    def test_normal_application_refactor_does_not_require_revision_bump(self):
        sensitive, base_revision, head_revision = guard.check_runtime_revision(
            [
                "backend/routes/old_route.py",
                "backend/routes/new_route.py",
                "frontend/dist/assets/old.js",
                "frontend/dist/assets/new.js",
            ],
            manifest(3),
            manifest(3),
        )

        self.assertEqual(sensitive, [])
        self.assertEqual((base_revision, head_revision), (3, 3))

    def test_runtime_sensitive_change_requires_revision_bump(self):
        with self.assertRaises(guard.CompatibilityGuardError) as caught:
            guard.check_runtime_revision(
                ["backend/app.py", "tools/install_torch.py"],
                manifest(3),
                manifest(3),
            )

        message = str(caught.exception)
        self.assertIn("tools/install_torch.py", message)
        self.assertIn("3 -> 3", message)

    def test_runtime_sensitive_change_accepts_increased_revision(self):
        sensitive, base_revision, head_revision = guard.check_runtime_revision(
            ["install.sh", "frontend/src/App.tsx"],
            manifest(3),
            manifest(4),
        )

        self.assertEqual(sensitive, ["install.sh"])
        self.assertEqual((base_revision, head_revision), (3, 4))

    def test_runtime_revision_cannot_decrease(self):
        with self.assertRaises(guard.CompatibilityGuardError):
            guard.check_runtime_revision([], manifest(4), manifest(3))

    def test_runtime_revision_must_be_a_positive_integer(self):
        for revision in [None, True, 0, "2"]:
            with self.subTest(revision=revision):
                with self.assertRaises(guard.CompatibilityGuardError):
                    guard.runtime_revision(manifest(revision), "Head")


if __name__ == "__main__":
    unittest.main()

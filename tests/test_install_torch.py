import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools import install_torch


class InstallTorchBackendTests(unittest.TestCase):
    def test_choose_cuda_index_prefers_newest_supported_runtime(self):
        self.assertEqual(install_torch.choose_cuda_index((12, 8)), "cu128")
        self.assertEqual(install_torch.choose_cuda_index((12, 6)), "cu126")
        self.assertIsNone(install_torch.choose_cuda_index((12, 5)))

    def test_rdna4_radeon_names_are_rocm_candidates(self):
        names = ["AMD Radeon RX 9070 XT"]

        self.assertTrue(install_torch.is_rocm_supported_gpu(names))

    def test_rdna4_gfx_archs_are_rocm_candidates(self):
        names = ["Name: gfx1201"]

        self.assertTrue(install_torch.is_rocm_supported_gpu(names))

    def test_generic_integrated_amd_gpu_is_not_auto_enabled(self):
        names = ["AMD Radeon Graphics"]

        self.assertFalse(install_torch.is_rocm_supported_gpu(names))

    def test_rocm_wheel_urls_match_supported_python_versions(self):
        windows_urls = install_torch.rocm_wheel_urls("Windows", (3, 12))

        self.assertTrue(
            windows_urls[0].endswith("rocm_sdk_core-7.2.1-py3-none-win_amd64.whl")
        )
        self.assertFalse(any(url.endswith(".tar.gz") for url in windows_urls))
        self.assertTrue(
            install_torch.rocm_meta_package_url("Windows", (3, 12)).endswith(
                "rocm-7.2.1.tar.gz"
            )
        )
        self.assertIsNone(install_torch.rocm_meta_package_url("Windows", (3, 11)))
        self.assertEqual(install_torch.rocm_wheel_urls("Windows", (3, 11)), ())
        self.assertTrue(
            install_torch.rocm_wheel_urls("Linux", (3, 12))[0].endswith(
                "cp312-cp312-linux_x86_64.whl"
            )
        )
        self.assertEqual(install_torch.rocm_wheel_urls("Linux", (3, 11)), ())

    def test_rocm_pip_environment_bypasses_radeon_repo_proxy(self):
        env = install_torch.rocm_pip_environment(
            ("https://repo.radeon.com/rocm/windows/example.whl",),
            {"NO_PROXY": "localhost"},
        )

        self.assertEqual(env["NO_PROXY"], "localhost,repo.radeon.com")
        self.assertEqual(env["no_proxy"], env["NO_PROXY"])

    def test_rocm_pip_environment_can_keep_system_proxy(self):
        env = install_torch.rocm_pip_environment(
            ("https://repo.radeon.com/rocm/windows/example.whl",),
            {
                "NO_PROXY": "localhost",
                "SHARP_TORCH_USE_SYSTEM_PROXY": "1",
            },
        )

        self.assertEqual(env["NO_PROXY"], "localhost")
        self.assertNotIn("no_proxy", env)

    def test_rocm_package_specs_prefer_local_wheels(self):
        url = "https://repo.radeon.com/rocm/windows/torch-2.9.1%2Brocm7.2.1.whl"
        with TemporaryDirectory() as tmp:
            local = Path(tmp) / "torch-2.9.1+rocm7.2.1.whl"
            local.touch()

            specs = install_torch.rocm_package_specs((url,), tmp)

        self.assertEqual(specs, (str(local),))

    def test_rocm_import_compat_source_is_lazy(self):
        top_level = install_torch.ROCM_COMPAT_SOURCE.split("class ", 1)[0]

        self.assertNotIn("import torch", top_level)
        self.assertIn("sys.meta_path.insert", install_torch.ROCM_COMPAT_SOURCE)


if __name__ == "__main__":
    unittest.main()

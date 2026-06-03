import os
import unittest
from unittest.mock import patch

from tools import download_model


class DownloadModelSourceTests(unittest.TestCase):
    def test_default_source_order_keeps_huggingface_first(self):
        with patch.dict(os.environ, {}, clear=True):
            sources = download_model.ordered_sources()

        self.assertEqual(sources[0][0], "HuggingFace")

    def test_china_mirror_prefers_hf_mirror(self):
        with patch.dict(os.environ, {"SHARP_MODEL_SOURCE": "china"}, clear=True):
            sources = download_model.ordered_sources()

        self.assertIn("hf-mirror.com", sources[0][1])


if __name__ == "__main__":
    unittest.main()

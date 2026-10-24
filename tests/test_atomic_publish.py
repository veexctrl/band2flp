import errno
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from band2flp.flp_export import FLPExportError, _atomic_publish


@unittest.skipUnless(os.name == "nt", "Windows hard-link fallback")
class AtomicPublishTests(unittest.TestCase):
    def test_permission_denied_hardlink_falls_back_to_atomic_rename(self) -> None:
        with tempfile.TemporaryDirectory(dir=".") as directory:
            root = Path(directory)
            temporary = root / "pending.flp"
            destination = root / "result.flp"
            temporary.write_bytes(b"synthetic FLP")

            with patch(
                "band2flp.flp_export.os.link",
                side_effect=PermissionError(errno.EACCES, "hard links unavailable"),
            ):
                _atomic_publish(temporary, destination)

            self.assertEqual(destination.read_bytes(), b"synthetic FLP")
            self.assertFalse(temporary.exists())

    def test_rename_fallback_does_not_overwrite_existing_output(self) -> None:
        with tempfile.TemporaryDirectory(dir=".") as directory:
            root = Path(directory)
            temporary = root / "pending.flp"
            destination = root / "result.flp"
            temporary.write_bytes(b"new synthetic FLP")
            destination.write_bytes(b"existing output")

            with patch(
                "band2flp.flp_export.os.link",
                side_effect=PermissionError(errno.EACCES, "hard links unavailable"),
            ), self.assertRaisesRegex(FLPExportError, "output already exists"):
                _atomic_publish(temporary, destination)

            self.assertEqual(destination.read_bytes(), b"existing output")
            self.assertTrue(temporary.exists())


if __name__ == "__main__":
    unittest.main()

import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.upstream_sync.adapters.vendored_kodi_addon import _latest_archive


class VendoredKodiAddonTests(unittest.TestCase):
    def test_current_descriptor_selects_release_instead_of_historical_maximum(self):
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary)
            subprocess.run(["git", "init", "-q", str(checkout)], check=True)
            subprocess.run(
                ["git", "-C", str(checkout), "config", "user.email", "test@example.invalid"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(checkout), "config", "user.name", "Test"],
                check=True,
            )
            addon_id = "plugin.video.example"
            addon = checkout / addon_id
            addon.mkdir()
            (addon / "addon.xml").write_text(
                '<addon id="%s" version="0.26"/>\n' % addon_id,
                encoding="utf-8",
            )
            (addon / (addon_id + "-0.26.zip")).write_bytes(b"current")
            (addon / (addon_id + "-2.17.zip")).write_bytes(b"historical")
            subprocess.run(["git", "-C", str(checkout), "add", addon_id], check=True)
            subprocess.run(
                ["git", "-C", str(checkout), "commit", "-qm", "fixture"],
                check=True,
            )
            commit = subprocess.run(
                ["git", "-C", str(checkout), "rev-parse", "HEAD"],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout.strip()

            self.assertEqual(
                _latest_archive(checkout, commit, addon_id),
                ("0.26", addon_id + "/" + addon_id + "-0.26.zip"),
            )

    def test_missing_archive_for_current_descriptor_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary)
            subprocess.run(["git", "init", "-q", str(checkout)], check=True)
            subprocess.run(
                ["git", "-C", str(checkout), "config", "user.email", "test@example.invalid"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(checkout), "config", "user.name", "Test"],
                check=True,
            )
            addon_id = "plugin.video.example"
            addon = checkout / addon_id
            addon.mkdir()
            (addon / "addon.xml").write_text(
                '<addon id="%s" version="0.26"/>\n' % addon_id,
                encoding="utf-8",
            )
            (addon / (addon_id + "-2.17.zip")).write_bytes(b"historical")
            subprocess.run(["git", "-C", str(checkout), "add", addon_id], check=True)
            subprocess.run(
                ["git", "-C", str(checkout), "commit", "-qm", "fixture"],
                check=True,
            )
            commit = subprocess.run(
                ["git", "-C", str(checkout), "rev-parse", "HEAD"],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout.strip()

            with self.assertRaisesRegex(ValueError, "matching the current"):
                _latest_archive(checkout, commit, addon_id)


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from validate_release_note import validate_release_note


class ValidateReleaseNoteTests(unittest.TestCase):
    def test_accepts_matching_note_with_title_and_summary(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            release_directory = Path(temporary_directory)
            note = release_directory / "agents-v1.2.3.md"
            note.write_text(
                "# ChargePilot release 1.2.3\n\n"
                "This update improves device enrollment for tenant users.\n",
                encoding="utf-8",
            )

            result = validate_release_note("agents-v1.2.3", release_directory)

            self.assertEqual(result, note)

    def test_rejects_a_missing_release_note(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(ValueError, "Add .* before publishing"):
                validate_release_note("agents-v1.2.3", Path(temporary_directory))

    def test_rejects_an_invalid_tag(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(ValueError, "Invalid agent release tag"):
                validate_release_note("agents-v1.2", Path(temporary_directory))

    def test_rejects_a_note_without_a_useful_summary(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            release_directory = Path(temporary_directory)
            (release_directory / "agents-v1.2.3.md").write_text(
                "# ChargePilot release 1.2.3\n\nShort.\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "useful summary"):
                validate_release_note("agents-v1.2.3", release_directory)


if __name__ == "__main__":
    unittest.main()

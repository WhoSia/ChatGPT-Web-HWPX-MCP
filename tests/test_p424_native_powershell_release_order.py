"""Static guard against hashing an HWPX while Hancom still owns its COM handle.

The Windows-only COM integration must still be manually proven on the licensed
machine. This test merely protects the source-verification lifecycle order.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "p423_hancom_native_pdf.ps1"


class NativePowerShellSourceCustodyTests(unittest.TestCase):
    def test_verify_source_only_after_job_owned_com_release(self):
        script = SCRIPT.read_text(encoding="utf-8")
        save = script.index("$saved = $hwp.SaveAs($tempPdf, 'PDF', '')")
        verify_pdf = script.index("$stage = 'verify-pdf'", save)
        ownership = script.index("$stage = 'release-com'", verify_pdf)
        close = script.index("$hwp.Quit()", ownership)
        release = script.index("FinalReleaseComObject($hwp)", close)
        source_verification = script.index("$stage = 'verify-source-after-release'", release)
        post_render_hash = script.index("Get-FileHash -LiteralPath $inputInfo.FullName", source_verification)
        commit = script.index("$stage = 'commit'", post_render_hash)
        self.assertTrue(save < verify_pdf < ownership < close < release < source_verification < post_render_hash < commit)
        self.assertIn("HANCOM_COM_OWNER_IDENTITY_CHANGED", script)
        self.assertIn("SOURCE_CHANGED_DURING_RENDER", script)
        self.assertIn("SOURCE_REMAINED_LOCKED_AFTER_HANCOM_CLOSE", script)

    def test_no_global_hancom_process_kill(self):
        script = SCRIPT.read_text(encoding="utf-8").lower()
        self.assertNotIn("stop-process -name hwp", script)
        self.assertNotIn("taskkill", script)


if __name__ == "__main__":
    unittest.main()

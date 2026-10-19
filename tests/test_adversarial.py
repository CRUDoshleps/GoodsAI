"""QA harness integrity/failure handling; known failures stay visible in its report."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from goodsai.adversarial import main,run_suite
from goodsai.cli import predict


class AdversarialTests(unittest.TestCase):
    def test_real_suite_has_no_untracked_regressions(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'suite';r=run_suite(out)
            self.assertEqual(r['checks_total'],21)
            failed=[c for c in r['cases'] if not c['passed']]
            self.assertTrue(all(c['known_issue']==15 for c in failed),failed)
            self.assertEqual(r['status'],'failed' if failed else 'passed')
            before={p.name:p.read_bytes() for p in out.iterdir()}
            with self.assertRaises(FileExistsError):run_suite(out)
            self.assertEqual(before,{p.name:p.read_bytes() for p in out.iterdir()})

    def test_missing_extraction_never_becomes_success_or_suppressed_known_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('goodsai.rules.Rules.candidates',return_value=iter(())):
                with redirect_stdout(io.StringIO()):
                    exit_code=main(['--output-dir',str(Path(folder)/'suite')])
            r=json.loads((Path(folder)/'suite/report.json').read_text())
            self.assertEqual(exit_code,1)
            self.assertEqual(r['status'],'failed')
            self.assertLess(r['checks_passed'],r['checks_total'])

    def test_dependency_failure_is_explicit_and_has_no_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('goodsai.adversarial.predict',side_effect=RuntimeError('private card text')):
                r=run_suite(Path(folder)/'suite')
            self.assertEqual(r['status'],'error')
            self.assertEqual(r['error_kind'],'RuntimeError')
            self.assertNotIn('private card text',json.dumps(r))

    def test_corrupted_prediction_is_not_scored_as_valid_data(self):
        def corrupted(source,output,config):
            result=predict(source,output,config)
            output.write_text('{}\n',encoding='utf-8')
            return result
        with tempfile.TemporaryDirectory() as folder:
            with patch('goodsai.adversarial.predict',side_effect=corrupted):
                r=run_suite(Path(folder)/'suite')
            self.assertEqual(r['status'],'error')
            self.assertNotIn('checks_passed',r)


if __name__=='__main__':unittest.main()

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from reproduction.round06.methods import win_rate_select
from reproduction.round07.methods import evidence_tiebreak_select
from reproduction.round08.run import load_canonical, run_tournament
from scripts.review_preflight import ROOT, preflight


class FairnessChecks(unittest.TestCase):
    def test_gate_boundary_is_shared_end_to_end(self):
        pair = ('a','b')
        response = {pair: dict(winner='b', confidence=.6)}
        for gate, accepted in ((.6,True),(.7,False)):
            _, _, _, edges = run_tournament(load_canonical(), list(pair), response, 123, 'toy', threshold=gate)
            self.assertEqual(len(edges),1)
            self.assertEqual(edges[0]['valid'],accepted)
            for method in (win_rate_select,evidence_tiebreak_select):
                selected, _, diagnostic = method(pair,edges,threshold=gate)
                self.assertEqual(selected, ['b'] if accepted else list(pair))
                self.assertEqual(diagnostic['valid_unique_edges'],int(accepted))

    def test_reject_rewritten_freeze_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'BASELINE_FREEZE.json').write_text('{"files": {}}')
            with self.assertRaises(ValueError):
                preflight(Path(tmp))

    def test_optimized_python_cannot_report_verification_success(self):
        r = subprocess.run([sys.executable,'-O',str(ROOT/'scripts/review_preflight.py')],capture_output=True)
        self.assertNotEqual(r.returncode,0)
        self.assertIn(b'assertions enabled', r.stderr)

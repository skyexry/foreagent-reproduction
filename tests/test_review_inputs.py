import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from reproduction.round06 import run


class FeedbackIdentityTests(unittest.TestCase):
    def test_invalid_winner_cannot_vote_for_last_candidate(self):
        with TemporaryDirectory() as tmp, patch.object(run, 'ROOT', Path(tmp)):
            ground = Path(tmp)/'data/coverage/solutions_subset_50/task/ground_truth/groups_task_n2.json'
            author = Path(tmp)/'data/author_reference/task.json'
            ground.parent.mkdir(parents=True)
            author.parent.mkdir(parents=True)
            ground.write_text(json.dumps([dict(paths=['a000.py','b000.py'],scores=[.2,.4],is_lower_better=False)]))
            for index in (-1, 0.9, True):
                row=dict(solutions=[dict(path='a000.py'),dict(path='b000.py')],prediction=dict(best_index=index))
                author.write_text(json.dumps(dict(results=[row])))
                expected=dict(ground_truth_sha256=run.sha(ground.read_bytes()),author_sha256=run.sha(author.read_bytes()))
                with self.subTest(index=index),self.assertRaises(AssertionError):
                    run.load_task('task',expected)

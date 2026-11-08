"""Generate a checksum-pinned source overlay; originals remain byte-identical."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCE = ROOT/'phase1-reproduction/code/author/mle-bench/agents/aide/aide'


def replace_function(text, name, replacement, class_name=None):
    tree = ast.parse(text)
    scope = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name).body if class_name else tree.body
    node = next(n for n in scope if isinstance(n, ast.FunctionDef) and n.name == name)
    lines = text.splitlines(keepends=True)
    lines[node.lineno-1:node.end_lineno] = [replacement.rstrip()+'\n']
    return ''.join(lines)


def build():
    protocol = json.loads((ROOT/'experiments/clean-ranking-v1/protocol.json').read_text())
    original = {}
    for name, expected in protocol['author_source_sha256'].items():
        raw = (SOURCE/name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected, name
        original[name] = raw.decode()
    wm = original['world_model.py'].replace('import logging\n', 'import logging\nimport hashlib\nimport json\nimport threading\nfrom .correctness import response_values\nfrom .ranking import rank_candidates\n', 1)
    wm = wm.replace('    max_concurrent_requests: int = 128\n', '    max_concurrent_requests: int = 128\n    selection_policy: str = "original"\n    comparison_budget: int = 13\n    selection_seed: int = 0\n', 1)
    wm = wm.replace('        self.comparison_history: List[ComparisonResult] = []\n', '        self.comparison_history: List[ComparisonResult] = []\n        self._comparison_cache = {}\n        self._pair_locks = {}\n        self._locks_guard = threading.Lock()\n', 1)
    wm = wm.replace('        result["predicted_best_index"] = int(parsed["predicted_best_index"])', '        result["predicted_best_index"] = parsed["predicted_best_index"]', 1)
    wm = wm.replace('            result["confidence"] = float(parsed["confidence"])', '            result["confidence"] = parsed["confidence"]', 1)
    wm = replace_function(wm, '_predict_pairwise_single', '''    def _predict_pairwise_single(self, node_a, node_b, round_num=0):
        order = tuple(hashlib.sha256(n.code.encode()).hexdigest() for n in (node_a, node_b))
        context = (self.task_desc, self.data_preview, self.task_name,
                   self.config.model, self.config.temperature)
        key = (context, tuple(sorted(order)))
        with self._locks_guard:
            lock = self._pair_locks.setdefault(key, threading.Lock())
        with lock:
            if key not in self._comparison_cache:
                try:
                    prompt = build_pairwise_prompt(task_desc=self.task_desc,
                        data_analysis=self.data_preview, code_a=node_a.code,
                        code_b=node_b.code, task_name=self.task_name)
                    raw = query(system_message=BENCH_SYSTEM_PROMPT_COT,
                        user_message=prompt, model=self.config.model,
                        temperature=self.config.temperature)
                    raw = raw[0] if isinstance(raw, tuple) else raw
                    parsed = parse_pairwise_response(raw)
                    winner, confidence = response_values(parsed)
                except Exception as error:
                    raw, winner, confidence = str(error), None, 0.0
                self._comparison_cache[key] = (order, winner, confidence, raw)
            else:
                logger.info("Cache hit for pair: %s", key[1])
            previous, winner, confidence, raw = self._comparison_cache[key]
            if previous != order and winner is not None:
                winner = 1-winner
            valid = winner is not None and confidence >= self.config.confidence_threshold
            return ComparisonResult(winner if valid else None,
                1-winner if valid else None, confidence, round_num, valid, raw)
''', 'WorldModel')
    marker = '        n = len(candidates)\n'
    assert wm.count(marker) == 1
    wm = wm.replace(marker, '        if self.config.selection_policy != "original":\n            return rank_candidates(self, candidates)\n\n'+marker, 1)
    # Displayed ties must use the same key as the unchanged original ordering.
    wm = wm.replace('            k = (info["wins"], info["round"])',
                    '            k = sort_key(info)', 1)
    agent = original['agent.py'].replace('import shutil\n', 'import shutil\nfrom .correctness import prepare_submission, submission_problem, save_checkpoint\n', 1)
    assert 'from .correctness import' in agent
    old = '        # clear the submission dir from previous steps\n        shutil.rmtree(self.cfg.workspace_dir / "submission", ignore_errors=True)\n        (self.cfg.workspace_dir / "submission").mkdir(exist_ok=True)'
    assert old in agent
    agent = agent.replace(old, '''        # Every individual execution receives a fresh submission directory.
        original_exec = exec_callback
        def isolated_exec(code, *args, **kwargs):
            prepare_submission(self.cfg.workspace_dir)
            return original_exec(code, *args, **kwargs)
        exec_callback = isolated_exec''', 1)
    marker = '            json.dump(metadata, f, indent=2)'
    assert agent.count(marker) == 1
    agent = agent.replace(marker, marker+'\n        if not node.is_skipped and not node.is_buggy:\n            self._update_best_solution()', 1)
    agent = replace_function(agent, '_post_process_node', '''    def _post_process_node(self, result_node):
        if not result_node.is_buggy and not result_node.is_skipped:
            problem = submission_problem(self.cfg.workspace_dir)
            if problem:
                result_node.is_buggy = True
                result_node.metric = WorstMetricValue()
                result_node.analysis = (result_node.analysis or "") + "\\nSubmission error: " + problem
''', 'Agent')
    agent = replace_function(agent, '_update_best_solution', '''    def _update_best_solution(self):
        best_node = self.journal.get_best_node()
        if best_node is not None:
            save_checkpoint(self.cfg.workspace_dir, self.all_nodes_dir, best_node)
''', 'Agent')
    # Optional ranking policy is configured at the integration boundary.
    marker = '        ranked_candidates, comparisons, rank_meta = world_model.tournament_rank(candidates)'
    assert agent.count(marker) == 1
    agent = agent.replace(marker, '''        world_model.config.selection_policy = getattr(self.acfg, "ranking_policy", "original")
        world_model.config.comparison_budget = getattr(self.acfg, "ranking_comparison_budget", 13)
        world_model.config.selection_seed = getattr(self.acfg, "ranking_seed", 0)
'''+marker, 1)
    overlay = HERE/'overlay'
    overlay.mkdir(exist_ok=True)
    corrected = {'agent.py': agent, 'world_model.py': wm}
    changes = []
    for name, text in corrected.items():
        compile(text, str(overlay/name), 'exec')
        (overlay/name).write_text(text)
        changes.extend(difflib.unified_diff(original[name].splitlines(True), text.splitlines(True),
                       fromfile='author/'+name, tofile='C0/'+name))
    for name in ('correctness.py', 'ranking.py'):
        shutil.copyfile(HERE/name, overlay/name)
    grader_source = ROOT/'phase1-reproduction/code/author/mle-bench/mlebench/competitions/stanford-covid-vaccine/grade.py'
    grader = '''from mlebench.grade_helpers import InvalidSubmissionError
from mlebench.clean_baseline_score import stanford_score


def grade(submission, answers):
    try:
        if not submission.columns.is_unique or not answers.columns.is_unique:
            raise ValueError("Duplicate columns")
        return stanford_score(submission.to_dict("records"), answers.to_dict("records"))
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidSubmissionError(str(error)) from error
'''
    (overlay/'grade.py').write_text(grader)
    changes.extend(difflib.unified_diff(grader_source.read_text().splitlines(True), grader.splitlines(True),
                   fromfile='author/stanford/grade.py', tofile='C0/stanford/grade.py'))
    (HERE/'C0.patch').write_text(''.join(changes))
    manifest = {'author_commit': protocol['author_commit'], 'source_sha256': protocol['author_source_sha256'],
                'overlay_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(overlay.glob('*.py'))},
                'original_tournament_body': 'pairing/revival/stopping/order preserved; tie metadata aligned to original order key; optional new-policy dispatch',
                'scope': 'C0 correctness overlay; official full-agent runtime still requires deployment validation.'}
    manifest['grader_source_sha256'] = hashlib.sha256(grader_source.read_bytes()).hexdigest()
    (HERE/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))

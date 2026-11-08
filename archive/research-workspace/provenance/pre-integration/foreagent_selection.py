"""Pinned ForeAgent selection and an explicitly separate cache-direction repair.

Only standard-library imports are used. The source is read from the local Git
object, so the upstream worktree and its pending changes stay untouched.
"""
import ast
from dataclasses import replace
import hashlib
import logging
from pathlib import Path
import subprocess
import sys
import threading
import types

ROOT = Path(__file__).resolve().parent
UPSTREAM = ROOT.parents[1] / 'DM HW3' / 'foreagent-official'
COMMIT = 'c4d52cf99bd870d830b456ac7c0684aec1aef375'
SOURCE_PATH = 'mle-bench/agents/aide/aide/world_model.py'
SOURCE_SHA256 = 'df85087f0a23e5d95cb507fadc36fd5694f6abafe80d9ae2a841cdb838915d79'


def _offline_only(**kwargs):
    raise RuntimeError('Supply an explicit local comparison backend.')


def load_pinned_source():
    source = subprocess.check_output(['git', '-C', str(UPSTREAM), 'show', f'{COMMIT}:{SOURCE_PATH}'])
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError('Pinned WorldModel source checksum mismatch')
    tree = ast.parse(source)
    tree.body = [node for node in tree.body
                 if not (isinstance(node, ast.ImportFrom) and node.level)]
    module = types.ModuleType('_pinned_foreagent_selection')
    sys.modules[module.__name__] = module
    module.__dict__.update(Node=types.SimpleNamespace, query=_offline_only)
    exec(compile(tree, f'{COMMIT}/{SOURCE_PATH}', 'exec'), module.__dict__)
    module.logger.setLevel(logging.CRITICAL)
    return module


pinned = load_pinned_source()


class CacheFixedWorldModel(pinned.WorldModel):
    """Preserve first-query order; map cached indices to the current code order.

Cache entries and their orientation are local to this instance. A pair lock
keeps concurrent A/B and B/A requests consistent. Other pairs can run in
parallel. A new instance should be used for another task/configuration.
The underlying prompt, parser, confidence gate and tournament stay pinned.
"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._comparison_cache = {}
        self._cache_orders = {}
        self._pair_locks = {}
        self._locks_guard = threading.Lock()

    def _predict_pairwise_single(self, node_a, node_b, round_num=0):
        key = tuple(sorted((hash(node_a.code), hash(node_b.code))))
        order = (node_a.code, node_b.code)
        with self._locks_guard:
            lock = self._pair_locks.setdefault(key, threading.Lock())
        with lock:
            cached = key in self._comparison_cache
            previous = self._cache_orders.get(key)
            if cached and previous not in (order, order[::-1]):
                raise ValueError('Different code pairs share an upstream cache hash')
            result = super()._predict_pairwise_single(node_a, node_b, round_num)
            if not cached:
                self._cache_orders[key] = order
            elif previous != order:
                result = replace(result,
                                 winner_idx=None if result.winner_idx is None else 1 - result.winner_idx,
                                 loser_idx=None if result.loser_idx is None else 1 - result.loser_idx)
            return result

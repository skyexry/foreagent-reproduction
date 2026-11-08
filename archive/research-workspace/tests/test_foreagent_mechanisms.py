"""Regression checks of actual pinned gate and tournament edge cases."""
import unittest

from audit_foreagent_mechanisms import (
    execution_routing_checks, gate_checks, released_config_checks, stopping_checks,
)


class MechanismTests(unittest.TestCase):
    def test_released_configuration_matches_audit(self):
        released_config_checks()

    def test_gate_boundaries_malformed_responses_and_cache_scope(self):
        gate_checks()

    def test_pending_byes_stopping_and_display_ranks(self):
        stopping_checks()

    def test_agent_routes_ties_probability_and_forced_execution(self):
        execution_routing_checks()


if __name__ == '__main__':
    unittest.main()

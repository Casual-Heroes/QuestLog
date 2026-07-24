from unittest import TestCase
from unittest.mock import patch

from app.management.commands.monitor_palworld_amp import (
    default_watchdog_state,
    evaluate_observation,
)


class PalworldWatchdogStateTests(TestCase):
    @patch("app.management.commands.monitor_palworld_amp.time.time", return_value=1000)
    def test_arms_only_after_ready(self, _time):
        state = default_watchdog_state()

        self.assertEqual(evaluate_observation(state, "stopped", True, 2), "disarmed")
        self.assertFalse(state["armed"])
        self.assertEqual(evaluate_observation(state, "ready", True, 2), "healthy")
        self.assertTrue(state["armed"])

    @patch("app.management.commands.monitor_palworld_amp.time.time", return_value=1000)
    def test_direct_ready_to_stopped_is_a_crash_after_threshold(self, _time):
        state = default_watchdog_state()
        evaluate_observation(state, "ready", True, 2)

        self.assertEqual(evaluate_observation(state, "stopped", True, 2), "wait")
        self.assertEqual(evaluate_observation(state, "stopped", True, 2), "crash")

    @patch("app.management.commands.monitor_palworld_amp.time.time", return_value=1000)
    def test_manual_stopping_sequence_disarms(self, _time):
        state = default_watchdog_state()
        evaluate_observation(state, "ready", True, 2)

        self.assertEqual(evaluate_observation(state, "stopping", True, 2), "disarmed")
        self.assertEqual(evaluate_observation(state, "stopped", True, 2), "disarmed")
        self.assertFalse(state["armed"])

    @patch("app.management.commands.monitor_palworld_amp.time.time", return_value=1000)
    def test_transitional_state_does_not_trigger(self, _time):
        state = default_watchdog_state()
        evaluate_observation(state, "ready", True, 2)

        self.assertEqual(evaluate_observation(state, "restarting", True, 2), "wait")
        self.assertEqual(state["unhealthy_polls"], 0)

    @patch("app.management.commands.monitor_palworld_amp.time.time", return_value=1000)
    def test_amp_instance_offline_is_detected_only_when_armed(self, _time):
        state = default_watchdog_state()
        self.assertEqual(evaluate_observation(state, "undefined", False, 1), "disarmed")

        evaluate_observation(state, "ready", True, 1)
        self.assertEqual(evaluate_observation(state, "undefined", False, 1), "crash")

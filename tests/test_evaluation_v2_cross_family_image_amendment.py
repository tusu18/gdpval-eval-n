from pathlib import Path
import sys
import tempfile
import unittest
import base64
from io import BytesIO
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from grade_evaluation_v2_cross_family_image_amendment import continuation_row, unknown_snapshot, verify_unknown_unchanged, eligible_solver_continuation, make_client
from dispatch_evaluation_v2_grading_amended import select_destination, grade_directory
from run_evaluation_v2 import write, digest, canonical, Client
from evaluation_v2_verified_sonnet_budget import SonnetImageReservationMixin, sonnet_reservation_detail


class CrossFamilyImageAmendmentTests(unittest.TestCase):
    def test_zero_request_budget_stop_gets_distinct_immutable_continuation(self):
        with tempfile.TemporaryDirectory() as root:
            original = grade_directory("run", "anthropic/claude-sonnet-5.5", root) / "result.json"
            write(original, {"status": "budget_limited", "calls": [], "batches": [], "unresolved_calls": 0})
            before = digest(original)
            row = continuation_row(select_destination("run", "anthropic/claude-sonnet-5.5", root), root)
            self.assertEqual(row["action"], "continue_zero_request_budget_stop")
            self.assertTrue(row["destination"].endswith("__sonnet_image_reservation_01"))
            self.assertEqual(digest(original), before)

    def test_physical_request_cannot_be_retried_by_amendment(self):
        with tempfile.TemporaryDirectory() as root:
            original = grade_directory("run", "judge", root)
            write(original / "result.json", {"status": "budget_limited", "calls": ["sent"], "batches": []})
            row = continuation_row(select_destination("run", "judge", root), root)
            self.assertEqual(row["action"], "checkpoint_review_required")

    def test_unknown_ledger_snapshot_is_read_only_and_detects_changes(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "calls/old/reservation.json"
            row = {"status": "failed_unknown_charge", "reserved_usd": 6.45, "actual_cost_usd": None}
            write(path, row); before = digest(path)
            snapshot = unknown_snapshot(root)
            self.assertTrue(verify_unknown_unchanged(snapshot))
            self.assertEqual(digest(path), before)
            write(path, {**row, "reserved_usd": 0})
            self.assertFalse(verify_unknown_unchanged(snapshot))

    def test_only_same_attempt_budget_continuation_is_eligible(self):
        old = {"status": "budget_limited", "unresolved_calls": 0, "calls": ["old1", "old2"]}
        new = {"status": "submitted", "continuation_kind": "budget_continuation", "stage": "supplemental", "recovery_stage": "recovery", "inherited_calls": ["old1", "old2"], "first_continuation_request_sha256": "frozen"}
        cfg = {"kind": "budget_continuation", "budget_blocked_first_dispatch": True, "physical_replays_of_failed_request": 0, "original_turn_tool_limits_continue": True, "request_settings_changed": False, "request_sha256": "frozen"}
        self.assertTrue(eligible_solver_continuation(old, new, cfg, {"request_sha256": "frozen"}))
        self.assertFalse(eligible_solver_continuation({**old, "status": "output_token_limit"}, new, cfg, {"request_sha256": "frozen"}))
        self.assertFalse(eligible_solver_continuation(old, new, {**cfg, "request_settings_changed": True}, {"request_sha256": "frozen"}))
        self.assertFalse(eligible_solver_continuation(old, new, cfg, {"request_sha256": "different"}))

    def test_verified_image_bound_and_body_immutability(self):
        from PIL import Image
        stream = BytesIO(); Image.new("RGB", (1, 1)).save(stream, format="PNG")
        class Local(SonnetImageReservationMixin, Client): pass
        client = Local.__new__(Local)
        client.models = {"anthropic/claude-sonnet-5.5": {"pricing": {"prompt": "0.000001", "completion": "0.000002", "input_cache_write": "0.00000125"}}}
        body = {"model": "anthropic/claude-sonnet-5.5", "max_tokens": 100, "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode()}}]}]}
        before = canonical(body)
        detail = sonnet_reservation_detail(client, body)
        self.assertEqual(detail["verified_images"], 1)
        self.assertEqual(detail["fallback_images"], 0)
        generic = Client.reservation(client, body)
        self.assertAlmostEqual(generic - detail["reserved_usd"], (40000 - 8192) * 0.00000125 * 1.05, places=7)
        self.assertEqual(canonical(body), before)
        body["messages"][0]["content"][0]["image_url"]["url"] = "https://example.invalid/image.png"
        self.assertEqual(client.reservation(body), Client.reservation(client, body))

    def test_factory_keeps_global_thirty_dollar_ceiling(self):
        def fake_init(instance, key_file):
            instance.cfg = {"authorized_available_budget_usd": 14.66}; instance.root = Path("unused"); instance.models = {}
        with patch.object(Client, "__init__", fake_init):
            client = make_client("not-read", {"budget": {}})
        self.assertEqual(client.cfg["authorized_available_budget_usd"], 30)


if __name__ == "__main__":
    unittest.main()

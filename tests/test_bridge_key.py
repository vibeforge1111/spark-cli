import unittest

from spark_cli.bridge_key import (
    bridge_consumer_process_keys,
    bridge_consumer_start_order,
    resolve_existing_bridge_api_key,
    resolve_shared_spawner_bridge_api_key,
)


class BridgeKeyTests(unittest.TestCase):
    def test_generates_once_when_missing(self) -> None:
        generated = "spark-bridge-" + "x" * 32
        self.assertEqual(
            resolve_shared_spawner_bridge_api_key({}, token_factory=lambda: generated),
            generated,
        )

    def test_preserves_matching_and_one_sided_existing_key(self) -> None:
        existing = "spark-bridge-" + "e" * 32
        self.assertEqual(
            resolve_shared_spawner_bridge_api_key(
                {
                    "spawner-ui": {"SPARK_BRIDGE_API_KEY": existing},
                    "spark-telegram-bot": {},
                }
            ),
            existing,
        )

    def test_explicit_key_coordinates_rotation_of_mismatched_values(self) -> None:
        rotated = "spark-bridge-" + "r" * 32
        self.assertEqual(
            resolve_shared_spawner_bridge_api_key(
                {
                    "spawner-ui": {"SPARK_BRIDGE_API_KEY": "spark-bridge-" + "a" * 32},
                    "spark-telegram-bot": {"SPARK_BRIDGE_API_KEY": "spark-bridge-" + "b" * 32},
                },
                explicit=rotated,
            ),
            rotated,
        )

    def test_rejects_mismatch_weakness_and_secret_reuse(self) -> None:
        strong_a = "spark-bridge-" + "a" * 32
        strong_b = "spark-bridge-" + "b" * 32
        with self.assertRaisesRegex(SystemExit, "mismatched"):
            resolve_shared_spawner_bridge_api_key(
                {
                    "spawner-ui": {"SPARK_BRIDGE_API_KEY": strong_a},
                    "spark-telegram-bot": {"SPARK_BRIDGE_API_KEY": strong_b},
                }
            )
        with self.assertRaisesRegex(SystemExit, "strong secret"):
            resolve_shared_spawner_bridge_api_key({}, explicit="changeme")
        with self.assertRaisesRegex(SystemExit, "must be different"):
            resolve_shared_spawner_bridge_api_key({}, explicit=strong_a, forbidden_secrets=(strong_a,))
        with self.assertRaisesRegex(SystemExit, "must be different"):
            resolve_shared_spawner_bridge_api_key(
                {"spawner-ui": {"MCP_API_KEY": strong_a}},
                explicit=strong_a,
            )

    def test_bridge_consumer_orders_are_safe_and_profile_preserving(self) -> None:
        pids = {
            "unrelated": {"pid": 1},
            "spawner-ui": {"pid": 2},
            "spark-telegram-bot:qa": {"pid": 3},
            "spark-telegram-bot:primary": {"pid": 4},
        }

        stop_order = bridge_consumer_process_keys(pids)

        self.assertEqual(
            stop_order,
            ["spark-telegram-bot:primary", "spark-telegram-bot:qa", "spawner-ui"],
        )
        self.assertEqual(
            bridge_consumer_start_order(stop_order),
            ["spawner-ui", "spark-telegram-bot:primary", "spark-telegram-bot:qa"],
        )

    def test_existing_bridge_precedence_is_stored_then_legacy_then_parent(self) -> None:
        stored = "stored-bridge-" + "s" * 32
        legacy = "legacy-bridge-" + "l" * 32
        parent = "parent-bridge-" + "p" * 32
        generated = {
            "spawner-ui": {"SPARK_BRIDGE_API_KEY": legacy},
            "spark-telegram-bot": {"SPARK_BRIDGE_API_KEY": legacy},
        }

        self.assertEqual(
            resolve_existing_bridge_api_key(generated, stored=stored, parent=parent),
            stored,
        )
        self.assertEqual(resolve_existing_bridge_api_key(generated, parent=parent), legacy)
        self.assertEqual(resolve_existing_bridge_api_key({}, parent=parent), parent)

    def test_ambient_parent_does_not_hide_mismatched_legacy_bridge_keys(self) -> None:
        with self.assertRaisesRegex(SystemExit, "mismatched"):
            resolve_existing_bridge_api_key(
                {
                    "spawner-ui": {"SPARK_BRIDGE_API_KEY": "legacy-a-" + "a" * 32},
                    "spark-telegram-bot": {"SPARK_BRIDGE_API_KEY": "legacy-b-" + "b" * 32},
                },
                parent="parent-bridge-" + "p" * 32,
            )


if __name__ == "__main__":
    unittest.main()

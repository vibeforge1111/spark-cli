import unittest

from spark_cli.bridge_key import resolve_shared_spawner_bridge_api_key


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


if __name__ == "__main__":
    unittest.main()

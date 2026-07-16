from __future__ import annotations

from spark_cli.system_map import as_dict, as_list, summarize_setup


def test_as_list_preserves_ordered_list_and_tuple_inputs() -> None:
    source = ["builder", "spawner"]

    assert as_list(source) is source
    assert as_list(("builder", "spawner")) == ["builder", "spawner"]


def test_as_list_rejects_unordered_and_noncollection_inputs() -> None:
    for value in ({"builder", "spawner"}, frozenset({"builder", "spawner"}), "builder", {"module": "builder"}, None):
        assert as_list(value) == []


def test_as_dict_accepts_only_actual_dict_authority() -> None:
    source = {"module": "builder"}

    assert as_dict(source) is source
    assert as_dict((("module", "builder"),)) == {}
    assert as_dict({"module", "builder"}) == {}


def test_setup_summary_preserves_ordered_tuple_modules() -> None:
    summary = summarize_setup({"modules": ("spark-cli", "spark-telegram-bot")})

    assert summary["modules"] == ["spark-cli", "spark-telegram-bot"]

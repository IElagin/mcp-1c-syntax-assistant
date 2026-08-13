"""Пять отказов индексации звучат по-разному и называют причину."""

import pytest

from src.api.indexing_messages import describe_outcome
from src.models.indexing_outcome import IndexingOutcome, OutcomeKind

pytestmark = pytest.mark.unit

EVERY_REFUSAL = [
    IndexingOutcome.parse_failed("data/hbk/shcntx_ru.hbk"),
    IndexingOutcome.nothing_to_index("data/hbk/shcntx_ru.hbk"),
    IndexingOutcome.page_loss_too_high(parsed=90, attempted=100, share=0.1),
    IndexingOutcome.index_write_failed("help1c_docs"),
    IndexingOutcome.error("Connection refused"),
]


def test_every_refusal_gets_its_own_message():
    messages = {describe_outcome(outcome) for outcome in EVERY_REFUSAL}

    assert len(messages) == len(EVERY_REFUSAL)


def test_no_message_invents_a_reason_the_code_did_not_take():
    """«Индексация вернула False» было выдумкой на четыре разных случая."""
    for outcome in EVERY_REFUSAL:
        assert "вернула False" not in describe_outcome(outcome)


def test_a_lost_pages_refusal_names_the_numbers():
    message = describe_outcome(
        IndexingOutcome.page_loss_too_high(parsed=90, attempted=100, share=0.1)
    )

    assert "90" in message and "100" in message and "10%" in message


def test_a_refused_write_names_the_index():
    assert "help1c_docs" in describe_outcome(IndexingOutcome.index_write_failed("help1c_docs"))


def test_an_error_carries_its_text():
    assert "Connection refused" in describe_outcome(IndexingOutcome.error("Connection refused"))


def test_success_is_not_described_as_a_failure():
    message = describe_outcome(IndexingOutcome.indexed(documents=23491, articles=366))

    assert "23491" in message and "366" in message


def test_every_kind_has_a_message():
    """Новый вид исхода не должен молча получить пустую строку."""
    for kind in OutcomeKind:
        assert describe_outcome(IndexingOutcome(kind, {}))

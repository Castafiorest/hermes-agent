"""WhatsApp native-poll model-picker behavior."""

import pytest

from plugins.platforms.whatsapp.adapter import WhatsAppAdapter


@pytest.mark.asyncio
async def test_model_picker_vote_invokes_callback_and_sends_confirmation():
    """A vote on a Hermes-owned model poll applies the selected model, not a chat turn."""
    adapter = object.__new__(WhatsAppAdapter)
    calls = []

    async def on_selected(chat_id, model_id, provider_slug):
        calls.append(("callback", chat_id, model_id, provider_slug))
        return "✓ Switched to Luna"

    async def send(chat_id, content, **kwargs):
        calls.append(("send", chat_id, content))

    adapter._model_picker_state = {
        "poll-123": {
            "choices": {"Luna — cx/gpt-5.6-luna": ("cx/gpt-5.6-luna", "custom:9router")},
            "on_model_selected": on_selected,
        }
    }
    adapter.send = send

    handled = await adapter._consume_model_picker_vote(
        "44123456789@s.whatsapp.net",
        {"pollUpdate": {"pollId": "poll-123", "selectedOptions": ["Luna — cx/gpt-5.6-luna"]}},
    )

    assert handled is True
    assert calls == [
        ("callback", "44123456789@s.whatsapp.net", "cx/gpt-5.6-luna", "custom:9router"),
        ("send", "44123456789@s.whatsapp.net", "✓ Switched to Luna"),
    ]
    assert adapter._model_picker_state == {}


@pytest.mark.asyncio
async def test_model_picker_sends_native_poll_and_remembers_message_id():
    """Bare /model can use a WhatsApp poll and retain the callback mapping."""
    adapter = object.__new__(WhatsAppAdapter)
    adapter._model_picker_state = {}
    sent = []

    async def send_poll(chat_id, question, options, *, selectable_count):
        sent.append((chat_id, question, options, selectable_count))
        return type("Result", (), {"success": True, "message_id": "poll-123"})()

    adapter.send_poll = send_poll

    async def on_selected(*_args):
        return "ok"

    result = await adapter.send_model_picker(
        "44123456789@s.whatsapp.net",
        [{"slug": "custom:9router", "models": ["cx/gpt-5.6-terra", "cx/gpt-5.6-luna"]}],
        "cx/gpt-5.6-terra", "custom:9router", "session", on_selected,
    )

    assert result.success is True
    assert sent == [(
        "44123456789@s.whatsapp.net", "Choose model (1-2 of 2)",
        ["✓ cx/gpt-5.6-terra", "cx/gpt-5.6-luna"], 1,
    )]
    assert adapter._model_picker_state["poll-123"]["choices"] == {
        "✓ cx/gpt-5.6-terra": ("cx/gpt-5.6-terra", "custom:9router"),
        "cx/gpt-5.6-luna": ("cx/gpt-5.6-luna", "custom:9router"),
    }


@pytest.mark.asyncio
async def test_middle_picker_page_never_exceeds_whatsapp_twelve_option_limit():
    """A paginated model poll reserves a slot for both navigation choices."""
    adapter = object.__new__(WhatsAppAdapter)
    adapter._model_picker_state = {}
    polls = []

    async def send_poll(_chat_id, _question, options, *, selectable_count):
        polls.append(options)
        return type("Result", (), {"success": True, "message_id": f"poll-{len(polls)}"})()

    adapter.send_poll = send_poll
    async def on_selected(*_args): return "ok"

    await adapter.send_model_picker(
        "chat", [{"slug": "custom:9router", "models": [f"model-{i}" for i in range(21)]}],
        "model-0", "custom:9router", "session", on_selected,
    )
    first = adapter._model_picker_state["poll-1"]
    await adapter._consume_model_picker_vote("chat", {"pollUpdate": {"pollId": "poll-1", "selectedOptions": ["Next models →"]}})

    assert len(polls[1]) == 12
    assert polls[1][-2:] == ["Next models →", "← Previous models"]


@pytest.mark.asyncio
async def test_foreign_poll_vote_is_not_consumed_as_model_picker():
    adapter = object.__new__(WhatsAppAdapter)
    adapter._model_picker_state = {}

    handled = await adapter._consume_model_picker_vote(
        "44123456789@s.whatsapp.net",
        {"pollUpdate": {"pollId": "foreign", "selectedOptions": ["Luna"]}},
    )

    assert handled is False

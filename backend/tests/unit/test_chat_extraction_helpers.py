"""Unit tests for chat route thinning helpers."""


def test_chat_helpers_block_parceiro_export():
    from services.chat_helpers import block_parceiro, _block_parceiro, MAX_ATTACHMENT_SIZE

    assert callable(block_parceiro)
    assert block_parceiro is _block_parceiro
    assert MAX_ATTACHMENT_SIZE == 10 * 1024 * 1024


def test_chat_modules_export_run_entrypoints():
    from services import (
        chat_helpers,
        chat_conversations,
        chat_messages,
        chat_groups,
        chat_presence,
    )

    assert callable(chat_helpers._block_parceiro)
    assert callable(chat_conversations.run_get_conversations)

    assert callable(chat_messages.run_get_messages)
    assert callable(chat_messages.run_send_message)
    assert callable(chat_messages.run_upload_message_with_attachment)
    assert callable(chat_messages.run_react_to_message)
    assert callable(chat_messages.run_edit_message)
    assert callable(chat_messages.run_delete_message)
    assert callable(chat_messages.run_search_messages)

    assert callable(chat_groups.run_create_group)
    assert callable(chat_groups.run_get_groups)
    assert callable(chat_groups.run_get_group)
    assert callable(chat_groups.run_update_group)
    assert callable(chat_groups.run_delete_group)
    assert callable(chat_groups.run_leave_group)

    assert callable(chat_presence.run_send_typing_indicator)
    assert callable(chat_presence.run_get_unread_count)
    assert callable(chat_presence.run_get_online_users)
    assert callable(chat_presence.run_get_chat_users)


def test_chat_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "chat.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 18
    assert len(text.splitlines()) < 320


def test_chat_no_preexisting_collision():
    """Ensure thinning used chat_* prefix and did not invent colliding names."""
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    chat_files = sorted(p.name for p in services_dir.glob("chat_*.py"))
    assert chat_files == [
        "chat_conversations.py",
        "chat_groups.py",
        "chat_helpers.py",
        "chat_messages.py",
        "chat_presence.py",
    ]

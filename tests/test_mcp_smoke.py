from opspilot.smokes.mcp import main


def test_real_mcp_stdio_tools_list_call_and_scope_negative() -> None:
    assert main() == 0

from coc_keeper.agent.state import Session
from coc_keeper.cli import _handle_command


def test_cli_help_lists_current_commands(capsys):
    assert _handle_command("/help", Session(), None, None)
    assert capsys.readouterr().out.splitlines() == [
        "/status 角色卡 | /trace 追踪 | /save [路径] 保存",
        "/module add <PDF或JSON> | /module status | /module next <原因> | /module export <JSON>",
    ]

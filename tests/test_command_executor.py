from openpalm.command_executor import CommandExecutor


def test_captures_stdout_success():
    ex = CommandExecutor(shell="/bin/zsh", working_dir=".", timeout_seconds=5, max_output_chars=500)
    result = ex.execute("echo hello")
    assert result.exit_code == 0
    assert "hello" in result.stdout
    assert result.timed_out is False


def test_handles_timeout():
    ex = CommandExecutor(shell="/bin/zsh", working_dir=".", timeout_seconds=1, max_output_chars=500)
    result = ex.execute("sleep 2")
    assert result.timed_out is True
    assert result.exit_code is None


def test_truncates_output():
    ex = CommandExecutor(shell="/bin/zsh", working_dir=".", timeout_seconds=5, max_output_chars=10)
    result = ex.execute("python3 -c 'print(\"abcdefghijklmnopqrstuvwxyz\")'")
    assert result.truncated is True
    assert len(result.stdout + result.stderr) <= 10

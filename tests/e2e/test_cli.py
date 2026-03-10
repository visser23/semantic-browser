from click.testing import CliRunner

from semantic_browser.cli.main import main


def test_cli_version_command():
    runner = CliRunner()
    result = runner.invoke(main, ["version"])
    assert result.exit_code == 0
    assert "semantic-browser" in result.output


def test_cli_doctor_command():
    runner = CliRunner()
    result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0
    assert "python" in result.output

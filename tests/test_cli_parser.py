from src.cli.app import build_parser


def test_cli_parser_accepts_legacy_command():
    parser = build_parser()
    args = parser.parse_args(["--command", "search", "--jsonInput", '{"search":{"query":"n8n","limit":10}}'])
    assert args.command == "search"

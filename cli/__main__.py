"""Allow running the CLI as a module: python -m cli"""
from cli.macro_sign_cli import main
import sys

sys.exit(main())

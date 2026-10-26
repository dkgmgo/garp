"""`python -m garp <tool_name> ...` without installing."""
import sys
from garp.cli import main

sys.exit(main())
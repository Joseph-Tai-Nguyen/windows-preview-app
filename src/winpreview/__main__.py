"""Allow ``python -m winpreview [file.pdf]``."""

import sys

from winpreview.app import main

sys.exit(main())

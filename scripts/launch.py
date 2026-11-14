# PyInstaller entry point (the package uses relative imports, so it cannot be the entry script itself).
import sys

from mobileoptimizer.app.main import main

sys.exit(main())

"""Module entrypoint so ``python -m kpi_studio.eval [args]`` works."""
from kpi_studio.eval.cli import main

raise SystemExit(main())

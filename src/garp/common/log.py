import logging


def setup_logging(verbose: int = 0, quiet: bool = False) -> None:
    level = logging.ERROR if quiet else (logging.WARNING, logging.INFO, logging.DEBUG)[min(verbose, 2)]
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,  # reconfigure on repeated main() calls (tests)
    )

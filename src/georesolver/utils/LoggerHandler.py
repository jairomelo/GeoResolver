import logging
import sys

def setup_logger(name="GeoResolver", verbose: bool = False) -> logging.Logger:
    """
    Set up a logger that outputs to stdout and respects a verbosity flag.
    
    Args:
        name (str): Logger name.
        verbose (bool): If True, set level to INFO; else WARNING.
    
    Returns:
        logging.Logger
    """
    logger = logging.getLogger(name)
    level = logging.INFO if verbose else logging.WARNING
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s", "%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
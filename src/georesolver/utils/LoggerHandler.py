import logging
from pathlib import Path

def setup_logger(class_name: str, log_dir: Path = Path(__file__).parent.parent.parent / "logs") -> logging.Logger:
    """
    Set up a logger for a specific class with its own log file.
    
    Args:
        class_name: Name of the class for which to set up logging
        log_dir: Directory where log files will be stored

    Returns:
        logging.Logger: Configured logger instance
    """
    logger = logging.getLogger(class_name)
    logger.setLevel(logging.INFO)
    
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f"{class_name.lower()}.log"
    handler = logging.FileHandler(log_file)
    handler.setLevel(logging.INFO)
    
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(handler)
    
    return logger
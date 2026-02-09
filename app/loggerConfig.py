import logging
from logging.handlers import RotatingFileHandler
import os
from datetime import datetime

# Create a logs directory if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')


# Configure logging
def setup_logging():
    """Configure application logging"""

    # Create logger
    created_logger = logging.getLogger("traffic_violation_api")
    created_logger.setLevel(logging.INFO)

    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # File Handler - All logs (with rotation)
    file_handler = RotatingFileHandler(
        'logs/app.log',
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(detailed_formatter)

    # File Handler - Error logs only
    error_handler = RotatingFileHandler(
        'logs/error.log',
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)

    # Add handlers to logger
    created_logger.addHandler(file_handler)
    created_logger.addHandler(error_handler)
    created_logger.addHandler(console_handler)

    return created_logger

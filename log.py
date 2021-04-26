from sys import stdout
from loguru import logger as custom_logger
import logging
import redis


class RedisHandler(logging.Handler):
    def __init__(self, host='localhost'):
        logging.Handler.__init__(self)

        self.r_server = redis.Redis(host)
        self.formatter = logging.Formatter("%(message)s")

    def emit(self, record):
        self.r_server.publish("message", self.format(record))

def create_logger():
    """Create custom logger."""
    custom_logger.remove()
    custom_logger.add(
        stdout,
        colorize=True,
        level="INFO",
        format="<light-cyan>{time:MM-DD-YYYY HH:mm:ss}</light-cyan> | \
		<light-green>{level}</light-green>: \
		<light-white>{message}</light-white>")

    custom_logger.add(
        'logs/errors.log',
        colorize=False,
        level="ERROR",
        rotation="200 MB",
        catch=True,
        format="<light-cyan>{time:MM-DD-YYYY HH:mm:ss}</light-cyan> | \
		<light-red>{level}</light-red>: \
		<light-white>{message}</light-white>")

    custom_logger.add(
        RedisHandler(),
        colorize=False,
        level="INFO",
        catch=True,
        format=f"<light-cyan>{time:MM-DD-YYYY HH:mm:ss}</light-cyan> | \
            <light-green>{function}</light-green> | \
    		<light-red>{level}</light-red>: \
    		<light-white>{message}</light-white>")
    return custom_logger


logger = create_logger()

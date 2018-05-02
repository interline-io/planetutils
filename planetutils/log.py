import logging
logging.basicConfig(format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def set_quiet():
    logger.setLevel(logging.ERROR)

def set_verbose():
    logger.setLevel(logging.DEBUG)

def set_default():
    logger.setLevel(logging.INFO)

info = logger.info
debug = logger.debug
warning = logger.warning
error = logger.error
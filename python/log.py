import logging
from datetime import datetime
formatter = logging.Formatter('%(threadName)s | %(asctime)s | %(levelname)-8s | %(message)s')
import sys
from logging.handlers import QueueHandler
import os


log = logging.getLogger('log')
log.setLevel(logging.DEBUG)
mainlog_filename = datetime.now().strftime('Log/log_%H_%M_%d_%m_%Y.log')
os.makedirs('Log', exist_ok=True)
mainLogFile_handler = logging.handlers.RotatingFileHandler(mainlog_filename, mode='a', maxBytes=52428800,
                                                           backupCount=10, encoding=None, delay=False,
                                                           errors=None)
mainLogFile_handler.setFormatter(formatter)
mainLogPrinting = logging.StreamHandler(sys.stdout)
log.addHandler(mainLogFile_handler)
log.addHandler(mainLogPrinting)
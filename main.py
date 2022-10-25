import datetime as dt
from python.roi import ROI
from python.log import log

if __name__ == "__main__":
    start_time = dt.datetime.now()
    log.info('Main Called')
    screener = ROI(log, debug=False)
    screener.run()
    end_time = dt.datetime.now()
    elapsed = (end_time - start_time).total_seconds()
    log.info(f'Main Finished after {elapsed} seconds')

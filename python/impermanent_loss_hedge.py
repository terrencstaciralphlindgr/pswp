import numpy as np
import time
import dateutil.tz
from binance.spot import Spot as SpotClient
import pandas as pd
import datetime as dt


def get_impermanent_loss(pct_price_change: float, t: float, alpha: float) -> float:
    """
    pct_price_change - token price percent change
    alpha - growth rate of the pool’s reserves
    t  - invested period (if it is mesured in days then alpha is daily growth rate)

    return
    impermanent loss value
    """
    return 2 * np.sqrt(pct_price_change + 1) * np.exp(alpha * t) / (2 + pct_price_change) - 1


def get_hedged_strategy(pct_price_change: float, principle: float, alpha: float, t: float) -> float:
    """
    pct_price_change - token price percent change
    principle - initial amount invested into liquidity pool
    alpha - growth rate of the pool’s reserves
    t  - invested period (if it is mesured in days then alpha is daily growth rate)

    return
    hedge - amount of corresponding  perpetual futures to hedge impermanent loss. 
            If value is negative short position should be opened
    """
    threshold_value = 0.05
    if np.abs(pct_price_change) > threshold_value:
        hedge = - principle * pct_price_change ** 2 / 4 * np.exp(alpha * t)
    else:
        hedge = 0
    return hedge


def find_instrument_name(client, pair_name):
    pairs = client.exchange_info()['symbols']
    for pair in pairs:
        if pair['symbol'] == pair_name.upper():
            return pair['symbol']
    return False


def get_standard_dev_moves(base_currency: str, length: int = 50, num_devs: float = 2.0) -> float:
    """
    Obtains the percent change that it would take for the coin to move 2 , 3 , 4 standard deviations from its 50 day mean
    """
    binance_spot_name = f'{base_currency}USDT'
    local_tz = dateutil.tz.tzlocal()
    offset = (time.localtime().tm_isdst) * 60 * 60
    client = SpotClient()
    pair_symbol = find_instrument_name(client=client, pair_name=binance_spot_name)
    if pair_symbol:
        ohlc_dict = client.klines(symbol=pair_symbol,
                                  interval='1d', limit=120)
        historical_df = pd.DataFrame(ohlc_dict,
                                     columns=['OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume', 'CloseTime',
                                              'QuoteAssetVolume', 'NumTrades', 'TakerBuyBaseAssetVolume',
                                              'TakerBuyQuoteAssetVolume', 'Ignore'])
        historical_df['Close'] = historical_df['Close'].astype(float)
        historical_df['CloseTime'] = pd.to_datetime(
            historical_df['CloseTime'], unit='ms', utc=True)
        historical_df['CloseTime'] = historical_df['CloseTime'].dt.tz_convert(
            local_tz) - dt.timedelta(seconds=offset) + dt.timedelta(seconds=1)
        # set Close time as the index and sort by it
        historical_df.set_index('CloseTime', inplace=True)
        historical_df.sort_index(inplace=True)
        historical_df['sma'] = historical_df['Close'].rolling(length).mean()
        historical_df['std'] = historical_df['Close'].rolling(length).std()
        # calculate the 2nd, 3rd and 4th standard deviations
        historical_df['top_band'] = historical_df['sma'] + num_devs * historical_df['std']
        # calculate the percent value between sma and top_band
        historical_df['pct_change'] = (historical_df['top_band'] - historical_df['sma']) / historical_df['sma']
        return historical_df['pct_change'].iloc[-1]


# import matplotlib.pyplot as plt
# values = 10000*np.arange(-0.01, 0.01, 0.001)
# hedges = []
# for value in values:
#     hedges.append(get_hedged_strategy(pct_price_change=value, principle=1000000, alpha=0.1, t=20))
# #plot the hedges
# plt.plot(values, hedges)
# #plot a vertical line at 0
# plt.axvline(x=0, color='black')
# plt.show()

from enum import Enum
from dataclasses import dataclass
from python.cex_clients.ftx import FtxClient
import datetime as dt
from ciso8601 import parse_datetime
from typing import Optional
import pandas as pd
import numpy as np


class HedgeType(Enum):
    Perpetual = 1
    Delivery = 2
    SpotShort = 3
    DefiLending = 4

    # make the string representation just the name
    def __str__(self):
        return self.name


class Exchange(Enum):
    # name, enum int, maker fee rate, taker fee rate
    FTX = 1, 0.02, 0.07
    Okex = 2, 0.08, 0.1

    # Deribit = 3, 0 , 0.03

    def __str__(self):
        return self.name

    def get_futures(self) -> list[HedgeType]:
       # match self:
       #     case Exchange.FTX:
        print('Getting FTX futures')
        client = FtxClient('a', 'b')
        results = []
        futures: list[dict] = client.get_all_futures()
        funding_rates: list[dict] = client.get_funding_rates()
        # transfrom funding rates list to a dict so they are easier to match
        funding_rates: dict = {x['future']: x for x in funding_rates}
        for future_data in futures:
            if future_data['perpetual']:
                if future_data['name'] in funding_rates:
                    next_fr_time = parse_datetime(
                        funding_rates[future_data['name']]['time'])
                    results.append(DeltaHedge.from_ftx_perpetual(future_data, float(
                        funding_rates[future_data['name']]['rate']), next_fr_time))
            else:
                results.append(DeltaHedge.from_ftx_future(future_data))
        return results
        #    case Exchange.Okex:
        #        print('Getting Okex futures')
        #        client = OkexClient('a', 'b', 'c')
        #        pub_client = OkexPublicClient('a', 'b', 'c')
        #        results = []
        #        swaps: list[dict] = client.get_tickers(instType='SWAP')['data']
        #        futures: list[dict] = client.get_tickers(
        #            instType='FUTURES')['data']
        #        # Okex does not offer an endpoint that returns all the funding rates with a single call, so we have to include single calls in this loop
        #        for swap_data in swaps:
        #            funding_rate_data: dict = pub_client.get_funding_rate(swap_data['instId'])[
        #                'data'][0]
        #            next_fr_time = dt.datetime.fromtimestamp(
        #                int(funding_rate_data['fundingTime']) / 1000)
        #            results.append(DeltaHedge.from_okex_swap(swap_data, float(
        #                funding_rate_data['fundingRate']), next_fr_time))
        #        for future_data in futures:
        #            results.append(DeltaHedge.from_okex_future(future_data))
        #        return results


@dataclass
class DeltaHedge:
    exchange: Exchange
    hedge_type: HedgeType
    base_currency: str
    symbol: str
    bid_price: float
    ask_price: float
    timestamp: int
    borrow_rate: float
    maker_fee: float
    taker_fee: float
    days_to_expiration: int
    expiration_date: Optional[dt.datetime]
    funding_rate: Optional[float]
    next_funding_rate_time: Optional[dt.datetime] = None

    ####---------------FTX-------------------####

    def get_summary_dict(self, maker=True) -> dict:
        # get the timestamp to be a string of the format '%Y-%m-%d %H:%M:%S' in EST
        timestamp = dt.datetime.fromtimestamp(
            self.timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')
        summary = {'exchange': self.exchange, 'hedge_type': self.hedge_type, 'base_currency': self.base_currency,
                   'symbol': self.symbol, 'bid_price': self.bid_price, 'timestamp': timestamp,
                   'funding_rate': self.funding_rate, 'next_funding_rate_time': self.next_funding_rate_time}
        if maker:
            summary['fee_rate'] = self.maker_fee
        else:
            summary['fee_rate'] = self.taker_fee
        return summary

    def is_perp(self) -> bool:
        return self.hedge_type == HedgeType.Perpetual

    @classmethod
    def from_ftx_perpetual(cls, perpetual: dict, funding_rate: float, next_funding_rate_time: dt.datetime):
        return cls(
            Exchange.FTX,
            HedgeType.Perpetual,
            perpetual['name'].split('-')[0],
            perpetual['name'],
            perpetual['bid'],
            perpetual['ask'],
            dt.datetime.now().timestamp(),
            0,
            Exchange.FTX.value[1],
            Exchange.FTX.value[2],
            np.inf,
            None,
            funding_rate,
            next_funding_rate_time
        )

    @classmethod
    def from_ftx_future(cls, future):
        expiration_date = parse_datetime(future['expiry'])
        dte = (expiration_date -
               dt.datetime.utcnow().replace(tzinfo=expiration_date.tzinfo)).days
        return cls(
            Exchange.FTX,
            HedgeType.Delivery,
            future['name'].split('-')[0],
            future['name'],
            future['bid'],
            future['ask'],
            dt.datetime.now().timestamp(),
            0,
            Exchange.FTX.value[1],
            Exchange.FTX.value[2],
            dte,
            expiration_date,
            None,
            None
        )

    ####---------------OKEX-------------------####

    @classmethod
    def from_okex_swap(cls, swap: dict, funding_rate: float, next_funding_rate_time: dt.datetime):
        return cls(
            Exchange.Okex,
            HedgeType.Perpetual,
            swap['instId'].split('-')[0],
            swap['instId'],
            swap['bidPx'],
            swap['askPx'],
            swap['ts'],
            0,
            Exchange.Okex.value[1],
            Exchange.Okex.value[2],
            np.inf,
            None,
            funding_rate,
            next_funding_rate_time
        )

    @classmethod
    def from_okex_future(cls, future):
        # date format is 220624
        expiration_date = dt.datetime.strptime(
            future['instId'].split('-')[2], '%y%m%d')
        dte = (expiration_date -
               dt.datetime.utcnow().replace(tzinfo=expiration_date.tzinfo)).days
        return cls(
            Exchange.Okex,
            HedgeType.Delivery,
            future['instId'].split('-')[0],
            future['instId'],
            future['bidPx'],
            future['askPx'],
            future['ts'],
            0,
            Exchange.Okex.value[1],
            Exchange.Okex.value[2],
            dte,
            expiration_date,
            None,
            None
        )


def get_all_available_hedges(exchanges_to_consider: list[Exchange] = None) -> list[DeltaHedge]:
    """
    Returns a list of available hedges, filtered by exchange.
    """
    hedges = []
    if exchanges_to_consider:
        for exchange in exchanges_to_consider:
            hedges.extend(exchange.get_futures())
        return hedges
    for exchange in Exchange:
        hedges.extend(exchange.get_futures())
    return hedges


def is_stablecoin(currency: str) -> bool:
    return currency in ['USDC', 'TUSD', 'BUSD', 'DAI','USDT']

def is_stable_and_vol_pair(name_zero: str, name_one: str) -> bool:
    """
    Returns true if the pair is a stablecoin and vol token pair.
    """
    if is_stablecoin(name_zero) and not is_stablecoin(name_one):
        return True
    elif not is_stablecoin(name_zero) and is_stablecoin(name_one):
        return True
    return False

def get_vol_token(name_zero: str, name_one: str) -> Optional[bool]:
    """
    Returns the vol token if the pair is a stablecoin and vol token pair. Otherwise, returns None.
    """
    if is_stablecoin(name_zero) and not is_stablecoin(name_one):
        return name_one
    elif not is_stablecoin(name_zero) and is_stablecoin(name_one):
        return name_zero
    return None

def get_avg_fund_rate(symbol: str) -> float:
    """
    Function provided by John McKenna to estimate future funding rates.
    """
    one_month_ago = dt.datetime.utcnow() - dt.timedelta(days=30)
    # match exchange:
    #     case Exchange.FTX:
    client = FtxClient('a', 'b')
    rates = client.get_funding_rates(
        symbol, start_time=one_month_ago.timestamp())
     # case Exchange.Okex:
     #     pub_client = PublicAPI('a', 'b', 'c')
     #     rates = pub_client.funding_rate_history(symbol)['data']
     #     # rename the keys to match the FTX format
     #     for rate in rates:
     #         rate['rate'] = rate['fundingRate']
    try:
        rawdata = pd.DataFrame(rates)
        res = rawdata['rate'].astype(float)[-24 * 7:]
        avg = ((res * 24 + 1).cumprod()[-1:] ** (1 / (24 * 7)) - 1) * 24
        return avg.values[-1]
    except Exception as ex:
        print(ex)
        return pd.NA


def unwrap_token_name(token_name: str) -> str:
    """
    Unwraps the token name from wrapped tokens, such as WETH or WBNB
    """
    # if the first character in the name is a W and len > 4, remove it
    if token_name[0] == 'W' and len(token_name) >= 4:
        return token_name[1:]
    return token_name


import json
import configparser
from logging import Logger
import traceback
from web3 import Web3
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager

config = configparser.ConfigParser()
config.read('config.ini')

DAILY_BLOCKS = 28800
DAYS_IN_YEAR = 365
DECIMAL_PLACES = 18
EXCHANGE_FEE = 0.17

def read_json(filename: str) -> dict:
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(traceback.format_exc())
        return {}

class PancakeSwapBlockchain:

    def __init__(self, logger:Logger, debug:bool):
        self.__debugging = debug
        self.__log = logger
        self.pair_abi = read_json('ABI/pairABI.json')
        self.token_abi = read_json('ABI/bep20.json')
        self.__node_address = config.get('settings', 'node_address')
        self.__w3 = Web3(Web3.HTTPProvider(self.__node_address))
        self.__pancake_factory = self.__w3.toChecksumAddress(config.get('settings', 'pancake_factory'))
        self.__usdt_address = self.__w3.toChecksumAddress(config.get('settings', 'usdt_address'))
        self.__pancake_masterChef = self.__w3.toChecksumAddress(config.get('settings', 'pancake_masterChef'))
        self.__cake_address = self.__w3.toChecksumAddress(config.get('settings', 'CAKE'))
        self.__factory_contract = self.__w3.eth.contract(abi=read_json('ABI/pancakeswap_factory.json'), address=self.__pancake_factory)
        self.__master_chef_contract = self.__w3.eth.contract(abi=read_json('ABI/master_chef_v2.json'), address=self.__pancake_masterChef)
        self.__pool_df = pd.DataFrame()
        self.__POOL_LIMIT = int(config.get('debug', 'POOL_LIMIT'))
        # self.fetch_all_pool_information_from_master_chef()

    def fetch_all_pool_information_from_master_chef(self) -> pd.DataFrame:
        try:
            total_pair = self.__master_chef_contract.functions.poolLength().call()  # Total Pools in master chef
            if self.__debugging:
                total_pair = self.__POOL_LIMIT
            
            for index in range(0, total_pair):
                self.__get_pool_information_from_blockchain_using_index(
                    index)  # Passing The Index Number To MasterChef Contract

            self.__pool_df = self.__pool_df.reset_index(drop=True)
            self.__pool_df = self.__pool_df.set_index('index')

            return self.__pool_df
        except Exception as error:
            # If any error Occurs We store the file with the information we were able to get and return the data
            print('Error Occured in fetch_all_pool_information_from_master_chef, saving Incomplete File. {e}'.
                  format(e=error))
            self.__log.info('Error Occured in fetch_all_pool_information_from_master_chef, saving Incomplete File. {e}'.
                            format(e=error))
        self.__pool_df.to_csv('./Data Set/master_chef_v2.csv')  # Storing Information To csv file

    def __get_pool_information_from_blockchain_using_index(self, index: int, debug: bool = False,verbose:bool=False):
        try:
            pool_address = self.__w3.toChecksumAddress(self.__get_pool_address_from_masterchef_using_index(index))
            if self.__validate_pool(pool_address):
                pool_allocation_point_and_type_information = \
                    self.__get_pool_allocation_point_and_type_from_master_chef_using_index(index)
                tokens_address_and_symbol_information = self.__get_tokens_information_from_pool_address(pool_address)
                pool_information = {'index': index, 'lpToken': pool_address}
                pool_information.update(pool_allocation_point_and_type_information)
                pool_information.update(tokens_address_and_symbol_information)
                if verbose:
                    print(pool_information)
                self.__pool_df = self.__pool_df.append(pool_information, ignore_index=True)
        except Exception as e:
            print('Error in function fetch_pool_information_from_blockchain: {e}'.format(e=e))
            self.__log.info('Error in function fetch_pool_information_from_blockchain: {e}'.format(e=e))

    def __get_pool_allocation_point_and_type_from_master_chef_using_index(self, index: int) -> dict:
        try:
            pool_information = self.__master_chef_contract.functions.poolInfo(
                index).call()
            row = {
                'index': int(index),
                'allocPoint': pool_information[2],  # ALLOCATED POINTS
                'isRegular': pool_information[4]  # TYPE OF POOL
            }  # The Information fetched from blockchain is stored in json object and returned
            return row
        except Exception as e:
            print(
                'Error in function __get_pool_allocation_point_and_type_from_master_chef_using_index: {e}'.format(e=e))
            self.__log.info(
                'Error in function __get_pool_allocation_point_and_type_from_master_chef_using_index: {e}'.format(e=e))

    def __get_tokens_addresses_from_pool_address(self, address: str) -> list:
        try:
            pair_contract = self.__w3.eth.contract(address=address, abi=self.pair_abi)
            token0 = pair_contract.functions.token0().call()  # Address of Token 0 in Pool
            token1 = pair_contract.functions.token1().call()  # Address of Token 1 in Pool
            return [token0, token1]
        except Exception as e:
            print('Error in function __get_tokens_addresses_from_pool_address: {e}'.format(e=e))
            self.__log.info('Error in function __get_tokens_addresses_from_pool_address: {e}'.format(e=e))
            return []

    def __get_pool_address_from_masterchef_using_index(self, index: int) -> str:
        try:
            pool_address = self.__master_chef_contract.functions.lpToken(
                index).call()
            return pool_address
        except Exception as e:
            print('Error in function __get_pool_address_from_masterchef_using_index: {e}'.format(e=e))
            self.__log.info('Error in function __get_pool_address_from_masterchef_using_index: {e}'.format(e=e))

    def __get_tokens_information_from_pool_address(self, address: str) -> dict:
        try:
            row = {}
            tokens_list = self.__get_tokens_addresses_from_pool_address(address)
            if tokens_list:
                token0_symbol = self.__get_token_symbol_from_address(tokens_list[0])
                token1_symbol = self.__get_token_symbol_from_address(tokens_list[1])

                row['token0'] = tokens_list[0]
                row['token0_name'] = token0_symbol
                row['token1'] = tokens_list[1]
                row['token1_name'] = token1_symbol
                return row
            else:
                return {}
        except Exception as e:
            print('Error in function get_tokens_information_from_pool_address: {e}'.format(e=e))
            self.__log.info('Error in function get_tokens_information_from_pool_address: {e}'.format(e=e))
            return {}

    def __validate_pool(self, address: str) -> bool:
        try:
            tokens_list = self.__get_tokens_addresses_from_pool_address(address)
            if tokens_list:
                return True
            else:
                return False
        except Exception as e:
            print('Error in function get_tokens_information_from_pool_address: {e}'.format(e=e))
            self.__log.info('Error in function get_tokens_information_from_pool_address: {e}'.format(e=e))
            return False

    def __get_token_symbol_from_address(self, address: str) -> str:
        try:
            token_contract = self.__w3.eth.contract(address=address, abi=self.token_abi)
            token_symbol = token_contract.functions.symbol().call()  # Address of Token 0 in Pool
            return token_symbol
        except Exception as e:
            print('Error in function __get_token_name_and_symbol_from_address: {e}'.format(e=e))
            self.__log.info('Error in function __get_token_name_and_symbol_from_address: {e}'.format(e=e))

    def get_master_chef_information(
            self) -> dict:  # it Get Basic Information From Pancake Masterchef v2 For Calculation
        try:
            total_regular_allocation = self.__master_chef_contract.functions.totalRegularAllocPoint().call()
            # Regular Allocated Point
            total_special_allocation = self.__master_chef_contract.functions.totalSpecialAllocPoint().call()
            # Special Allocated Point
            regular_cake_per_block = self.__master_chef_contract.functions.cakePerBlock(
                True).call()  # Number Of Cake Per Block For Regular Pools
            regular_cake_per_block = regular_cake_per_block / (
                    10 ** DECIMAL_PLACES)  # Converting the CAKE Quantity From WEI TO CAKE
            special_cake_per_block = self.__master_chef_contract.functions.cakePerBlock(
                False).call()  # Number Of Cake Per Block For Special Pools
            special_cake_per_block = special_cake_per_block / (
                    10 ** DECIMAL_PLACES)  # Converting the Cake Quanity FROM WEI TO CAKE
            row = {
                'total_regular_allocation': total_regular_allocation,
                'total_special_allocation': total_special_allocation,
                'regular_cake_per_block': regular_cake_per_block,
                'special_cake_per_block': special_cake_per_block,
            }
            return row
        except Exception as e:
            print('Error in master_chef_information {e}'.format(e=e))
            self.__log.info('Error in master_chef_information {e}'.format(e=e))

    def get_platform_token_price(self) -> float:
        try:
            cake_price = self.get_token_usdt_price(self.__cake_address)  # Fetching Price of token in terms of usdt
            return cake_price
        except Exception as e:
            print('Error get_platform_token_price {e}'.format(e=e))
            self.__log.info('Error get_platform_token_price {e}'.format(e=e))
            return 0

    def __get_reserves(self, pair_address: str) -> tuple:
        try:
            usdt_pair_contract = self.__w3.eth.contract(abi=self.pair_abi, address=pair_address)
            reserves = usdt_pair_contract.functions.getReserves().call()
            return reserves
        except Exception as e:
            print('Error Fetching Reserves: {e}'.format(e=e))
            self.__log.info('Error Fetching Reserves: {e}'.format(e=e))

    def __find_pair(self, token0: str, token1: str) -> str:
        # Check the token0 & Token1 and Try to find it any of them exist with USDT and if so,
        # then what is the usdt price of that token
        try:
            pair_address = self.__factory_contract.functions.getPair(token0,
                                                                     self.__usdt_address).call()  # calling pancake
            # factory getPair function
            if pair_address == '0x0000000000000000000000000000000000000000':  # Checking if Pair Address is valid or not
                pair_address = self.__factory_contract.functions.getPair(token1, self.__usdt_address).call()
            return pair_address
        except Exception as e:
            print('Error Finding Pair: {e}'.format(e=e))
            self.__log.info('Error Finding Pair: {e}'.format(e=e))
            return '0'

    def get_token_usdt_price(self, token_address: str) -> float:  # Fetches the price of token in terms of USDT
        try:
            # Check if Pair Exist With USDT FIRST
            pair_address = self.__factory_contract.functions.getPair(token_address, self.__usdt_address).call()
            if pair_address != '0x0000000000000000000000000000000000000000':  # Get Reserves
                pair_contract = self.__w3.eth.contract(address=pair_address, abi=self.pair_abi)
                reserves = pair_contract.functions.getReserves().call()
                if token_address > self.__usdt_address:
                    return reserves[0] / reserves[1]
                else:
                    return reserves[1] / reserves[0]
            else:
                print('Pair With USDT doenst exist {token}'.format(token=token_address))
                return 0
        except Exception as e:
            print('Error in __get_token_usdt_price {e}'.format(e=e))
            self.__log.info('Error in __get_token_usdt_price {e}'.format(e=e))
            return 0

    def calculate_current_liquidity_balance(self, pool_information: pd.DataFrame) -> pd.DataFrame:
        # This Fetches the The Reserves From the blockchain and Find out
        # 1. The TVL In the pool
        # 2. The Farm_Liquidity In the pool
        try:
            pool_information['TVL'] = pd.Series(dtype='float')  # This creates a column in the pool_df to store TVL
            pool_information['Farm_Liquidity'] = pd.Series(
                dtype='float')  # This creates a column in the pool_df to store Farm_Liquidity
            pool_information = pool_information.fillna(0)  # Initialize The NA Value with 0
            for index, row in pool_information.iterrows():
                try:
                    if index > self.__POOL_LIMIT and self.__debugging:  # in case of debugging the
                        # breaks the loop after pool_limit
                        break
                    pool_contract = self.__w3.eth.contract(abi=self.pair_abi, address=row['lpToken'])
                    # Checking For USDT Pair on pancake tokens
                    pair_address = self.__find_pair(row['token0'], row['token1'])
                    # print('Token0 + USDT PAIR, {pair}'.format(pair=pair_address))
                    reserves = self.__get_reserves(pair_address)  # Fetching Reserves
                    if row['token0'] > self.__usdt_address:  # Finding the Price of Token0 and Token1 with USDT
                        # print("usdt address smaller")
                        dollar_value = reserves[0] / reserves[1]
                    else:
                        dollar_value = reserves[1] / reserves[0]
                    pool_reserves = self.__get_reserves(pool_contract.address)
                    # Find Total Supply Of LP
                    TVL = (dollar_value * (pool_reserves[
                                               0] / 10 ** DECIMAL_PLACES) * 2)  # WEI TO BNB Conversion
                    max_supply = pool_contract.functions.totalSupply().call()
                    masterchef_balance = pool_contract.functions.balanceOf(
                        self.__pancake_masterChef).call() # BALANCE INPUT
                    Farm_Liquidity = (TVL / max_supply) * masterchef_balance  # Farming Pool Liquidity
                    pool_information['TVL'][index] = TVL  # Storing TVL In pool_df
                    pool_information['Farm_Liquidity'][index] = Farm_Liquidity # BALANCE INPUT
                except Exception as e:
                    print('Error finding TVL & Farm Liquidity in calculate_current_liquidity_balance {e}'.format(e=e))
                    self.__log.info(
                        'Error  finding TVL & Farm Liquidity in calculate_current_liquidity_balance {e}'.format(e=e))
            return pool_information
        except Exception as e:
            print('Error calculate_current_liquidity_balance {e}'.format(e=e))
            self.__log.info('Error calculate_current_liquidity_balance {e}'.format(e=e))


class WebScraper:

    def __init__(self, logger:Logger, debug:bool):
        self.__debugging = debug
        self.__log = logger
        self.__url = config.get('settings', 'url')
        self.__POOL_LIMIT = int(config.get('debug', 'POOL_LIMIT'))
    
    def fetch_current_trading_balance_for_all_pool(self, pool_information: pd.DataFrame) -> pd.DataFrame:
        # Fetches Today Traded Volume For Each Pool
        try:
            pool_information['volume_24h'] = pd.Series(dtype='float')
            pool_information['lp_reward_fee_24h'] = pd.Series(dtype='float')
            pool_information = pool_information.fillna(0)
            driver = webdriver.Chrome(ChromeDriverManager().install())  # Selecting Browser to Open
            driver.minimize_window() 
            # driver.get(url) # Open the url on web browser
            try:
                # We Loop through all the Pools Available in the File and repeat the process for each Pool
                for index, row in pool_information.iterrows():
                    try:
                        if index > self.__POOL_LIMIT and self.__debugging:
                            break
                        pool_website_information = self.__get_pool_information_from_address(driver, row['lpToken'])
                        pool_information['volume_24h'][index] = pool_website_information['volume_24h']
                        pool_information['lp_reward_fee_24h'][index] = pool_website_information['lp_reward_fee_24h']
                        # We Store this information in our Computer Memory
                        print(pool_information.loc[(pool_information['lpToken'] == row['lpToken'])].to_string())
                    except Exception as error:
                        # If the Pool is not Found on pankcake, We ignore it
                        print('Pool Not Found, ignoring pool {pool}'.format(pool=row['lpToken']))
                        self.__log.info('Pool Not Found, ignoring pool {pool}'.format(pool=row['lpToken']))
                return pool_information
            except Exception as error:
                print('Error in fetch_pool_information_from_web {e}'.format(e=error))
                self.__log.info('Error in fetch_pool_information_from_web {e}'.format(e=error))

        except Exception as e:
            print('Error in fetch_current_trading_balance_for_all_pool {e}'.format(e=e))
            self.__log.info('Error in fetch_current_trading_balance_for_all_pool {e}'.format(e=e))

    def __get_pool_information_from_address(self, driver,
                                            token_address: str) -> dict:  # This Function Scrap the values
        # from pancake.finance including daily volume
        try:
            url = self.__url + token_address
            driver.get(url)  # Open the url on web browser
            timeouts = 15
            # Once the Pool link is opened , we Open it up and Get the Values
            #time.sleep(timeouts)
            Button_7d = WebDriverWait(driver, timeouts).until(ec.presence_of_element_located(
                (By.XPATH,
                 "/html/body/div[1]/div[1]/div[3]/div/div[2]/div[3]/div[1]/div[2]/div/div/div[1]/button[2]")))
            Button_7d.click()
            lp_reward = WebDriverWait(driver, timeouts).until(ec.presence_of_element_located(
                (By.XPATH,
                 "/html/body/div[1]/div[1]/div[3]/div/div[2]/div[3]/div[1]/div[1]/div/div/div[1]/div[2]/div[2]")))
            volume_7d = WebDriverWait(driver, timeouts).until(ec.presence_of_element_located(
                (By.XPATH,
                 "/html/body/div[1]/div[1]/div[3]/div/div[2]/div[3]/div[1]/div[2]/div/div/div[2]/div[1]/div[2]")))
            lp_reward_fee_7d = WebDriverWait(driver, timeouts).until(ec.presence_of_element_located(
                (By.XPATH,
                 "/html/body/div[1]/div[1]/div[3]/div/div[2]/div[3]/div[1]/div[2]/div/div/div[2]/div[2]/div[2]")))
            if '%' in lp_reward.text:
                lp_reward = float(lp_reward.text.replace('%', ''))
            if '$' in volume_7d.text:
                volume_24h = self.__convert_value(volume_7d.text.replace('$', '')) / 7
            if '$' in lp_reward_fee_7d.text:
                lp_reward_fee_24h = self.__convert_value(lp_reward_fee_7d.text.replace('$', '')) / 7
            row = {
                'lp_reward': lp_reward,
                'volume_24h': volume_24h,
                'lp_reward_fee_24h': lp_reward_fee_24h
            }
            return row
        except Exception as e:
            print('Error in Pool Information: {e}'.format(e=e))
            self.__log.info('Error in Pool Information: {e}'.format(e=e))

            row = {
                'lp_reward': 0,
                'volume_24h': 0,
                'lp_reward_fee_24h': 0
            }
            return row

    def __convert_value(self, value: str) -> float:
        # This Function Conver values to float/integar. It removes M (Million)  and K (Thousands) and add 0 Accordingly
        # This is done for proper calculation
        try:
            if 'M' in value:
                value = value.replace('M', '')
                value = float(value) * 1000000
            elif 'K' in value:
                value = value.replace('K', '')
                value = float(value) * 1000
            return float(value)
        except Exception as e:
            print("Error in cleaning_data  {e}".format(e=e))
            self.__log.info("Error in cleaning_data  {e}".format(e=e))
            print(traceback.format_exc())
            return 0


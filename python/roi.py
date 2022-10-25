from concurrent.futures import ProcessPoolExecutor
from python.impermanent_loss_hedge import get_hedged_strategy, get_standard_dev_moves
from python.hedges import unwrap_token_name, get_all_available_hedges
from python.hedges import is_stablecoin
from logging import Logger
import warnings
from datetime import date
import pandas as pd
from os.path import exists
import configparser
from python.hedges import get_vol_token, is_stable_and_vol_pair
from python.utils import PancakeSwapBlockchain, WebScraper
import os
import multiprocessing as mp

warnings.simplefilter(action='ignore', category=FutureWarning)


pd.options.mode.chained_assignment = None
config = configparser.ConfigParser()
config.read('config.ini')

DAILY_BLOCKS = 28800
DAYS_IN_YEAR = 365
DECIMAL_PLACES = 18
EXCHANGE_FEE = 0.17
AVERAGE_DAYS = 6


class ROI:

    # Initialization Of data variables and
    def __init__(self, logger: Logger, debug: bool):
        os.makedirs('Data Set', exist_ok=True)
        self.__debugging: bool = debug
        self.__log: Logger = logger
        self.__previous_days_information: dict = {}
        self.__pancake_Blockchain: PancakeSwapBlockchain = PancakeSwapBlockchain(
            logger, debug)
        self.__web_scrapper: WebScraper = WebScraper(logger, debug)
        balance_string = config.get('balance', 'BALANCE')
        balances: list[str] = balance_string.split(',')
        self.__balance: list[float] = list(map(float, balances))
        self.__POOL_LIMIT: int = int(config.get('debug', 'POOL_LIMIT'))
        self.__pool_df: pd.DataFrame = pd.DataFrame()
        # self.__get_previous_days_information_from_stored_file()
        self.__average_df: pd.DataFrame = pd.DataFrame()

    def run(self):
        self.fetch_current_values()
        self.__calculate_basic_earnings()  # Calculation of Basic Earning From LP
        # Calculation of Mining Earning From Staking Farm
        self.__calculate_mining_rewards()
        # switched these around because impermanent loss needs to know the fee rate, which is brought in by the hedging costs
        self.__calculate_hedging_costs()
        self.__calculate_impermanent_loss()
        self.__log.info('Calculation Completed')

    def fetch_current_values(self):
        self.__pool_df = self.__pancake_Blockchain.fetch_all_pool_information_from_master_chef()
        self.__pool_df = self.__web_scrapper.fetch_current_trading_balance_for_all_pool(
            self.__pool_df)
        self.__pool_df = self.__pancake_Blockchain.calculate_current_liquidity_balance(
            self.__pool_df)
        self.__initialize_average_df()

    def __calculate_basic_earnings(self):
        self.__log.info('Calculating Basic Earning')
        self.__calculate_average_liquidity_balanace()  # Calculating TVL in the LP
        # Calculating Total Volume of LP in 24hours
        self.__calculate_average_trading_balanace()
        # Calculating the reward on each dollar in LP
        self.__calculate_rate_of_exchange_fees()
        # Calculate The reward for each Dollar in Liquidity
        self.__calculate_daily_exchange_fee_rate_per_USD_of_pair()
        self.__log.info('Basic Earning Calculated')

    def __calculate_mining_rewards(self):
        self.__log.info('Calculating Mining Rewards')
        # Calculate Average Farming Pool Size
        self.__calculate_average_total_daily_pool_size()
        # Calculate Total Reward From the Pool On daily basis
        self.__calculate_total_daily_mining_reward()
        self.__pancake_Blockchain.get_platform_token_price()  # Get the token Price
        # Calculate Reward on Each Dollar
        self.__calculate_daily_liquidity_mining_reward_rate_per_USD()
        # self.__log.info('Mining Rewards Calculated')

    def __calculate_daily_liquidity_mining_reward_rate_per_USD(self):
        # This function finds the daily reward of farming for each dollar for each pool
        try:
            for i in range(len(self.__balance)):
                balance_using = str(self.__balance[i])

                self.__average_df = self.__initialize_new_column_in_dataframe(self.__average_df, balance_using +
                                                                              '_daily_mining_reward_in_$',
                                                                              'float')
                for x, row in self.__average_df.iterrows():  # Loop Through complete dataframe
                    try:
                        # annual_return = self.__balance[i] * row[balance_using + '_annual_mining_reward_in_%'] / 100
                        value = self.__calculate_average(
                            row['lpToken'], balance_using + '_Mining_Reward')
                        daily_return = self.__balance[i] * value / 100
                        self.__average_df[balance_using +
                                          '_daily_mining_reward_in_$'][x] = daily_return
                        # self.__average_df[balance_using + '_annual_mining_reward_in_$'][x] = annual_return
                    except Exception as e:
                        self.__average_df[balance_using +
                                          '_daily_mining_reward_in_$'][x] = 0
                        # self.__average_df[balance_using + '_annual_mining_reward_in_$'][x] = 0
                        print(
                            'Error in forloop calculate_daily_liquidity_mining_reward_rate_per_USD {e}'.format(e=e))
                        self.__log.info(
                            'Error in forloop calculate_daily_liquidity_mining_reward_rate_per_USD {e}'.format(e=e))
                self.convert_values(
                    balance_using + '_daily_mining_reward_in_$')
            self.__save_average_df()
        except Exception as e:
            print(
                'Error calculate_daily_liquidity_mining_reward_rate_per_USD {e}'.format(e=e))
            self.__log.info(
                'Error calculate_daily_liquidity_mining_reward_rate_per_USD {e}'.format(e=e))
    # dead code here, is there a reason?

    def __pool_daily_mining_reward_per_usd(self, mining_reward_daily, liquidity):
        try:
            if float(mining_reward_daily) == 0 or float(liquidity) == 0:
                return 0
            return (float(mining_reward_daily) / float(liquidity)) * 100
        except Exception as e:
            print('Error pool_daily_mining_reward_per_usd {e}'.format(e=e))
            self.__log.info(
                'Error pool_daily_mining_reward_per_usd {e}'.format(e=e))

    def __calculate_average_total_daily_pool_size(self):
        # This Function finds out the average Liquidity In the Pool for 7 Days
        try:
            self.__average_df = self.__initialize_new_column_in_dataframe(self.__average_df,
                                                                          'total_liquidity_pool_size_in_$',
                                                                          'float')
            for x, row in self.__average_df.iterrows():  # Loop Through All the Pools in average_df
                try:
                    value = self.__calculate_average(
                        row['lpToken'], 'Farm_Liquidity')
                    self.__average_df['total_liquidity_pool_size_in_$'][
                        x] = value  # Store The Average value of Farm_Liquidity
                except Exception as e:
                    print(
                        'Error in for loop __calculate_average_total_daily_pool_size {e}'.format(e=e))
                    self.__log.info(
                        'Error in for loop __calculate_average_total_daily_pool_size {e}'.format(e=e))
            self.convert_values('total_liquidity_pool_size_in_$')

            self.__save_average_df()
        except Exception as e:
            print('Error get_platform_token_price {e}'.format(e=e))
            self.__log.info('Error get_platform_token_price {e}'.format(e=e))

    def __calculate_total_daily_mining_reward(self):
        try:
            self.__calculate_current_mining_reward()  # Finds Out Current day Mining Reward
            # Find Out the Average Mining Reward Using Previous data
            self.__calculate_average_mining_reward()
        except Exception as e:
            print('Error calculate_total_daily_mining_reward {e}'.format(e=e))
            self.__log.info(
                'Error calculate_total_daily_mining_reward {e}'.format(e=e))

    def __calculate_impermanent_loss(self):
        try:
            self.__log.info('Calculating impermanent loss')
            length = int(config.get(
                'impermanent_loss_assumptions', 'num_days'))
            standard_deviations = float(config.get(
                'impermanent_loss_assumptions', 'standard_devs'))
            for i in range(0,len(self.__balance)):
                balance_using = str(self.__balance[i])
                for index, row in self.__average_df.iterrows():
                    try:
                        token_zero_name = unwrap_token_name(row['token0_name'])
                        token_one_name = unwrap_token_name(row['token1_name'])
                        # we are not entirely sure yet how we proceed on vol-vol pairs in terms of impermanent loss.
                        if is_stable_and_vol_pair(token_zero_name, token_one_name):
                            vol_token = get_vol_token(
                                token_zero_name, token_one_name)
                            percent_move = get_standard_dev_moves(
                                vol_token, length, standard_deviations)
                            alpha = float(
                                row[balance_using + '_daily_basic_earning_in_BPS']) / 100
                            hedge = get_hedged_strategy(-percent_move,
                                                        self.__balance[i], alpha, 50)
                            self.__average_df.loc[index, balance_using +
                                                  '_impermanent_loss_in_amount_to_short'] = hedge
                            self.__average_df.loc[index, balance_using +
                                                  '_impermanent_loss_downside_covered'] = -percent_move
                            # calculate the estimated commission charge for the trade
                            self.__average_df.loc[index, balance_using + '_impermanent_loss_commission_charge'] = \
                                self.__average_df.loc[index, balance_using + '_impermanent_loss_in_amount_to_short'] * \
                                self.__average_df.loc[index, 'fee_rate']*2
                    except Exception as e:
                        print(
                            'Error in __calculate_impermanent_loss Loop {e}'.format(e=e))
            self.__save_average_df()
        except Exception as e:
            print('Error in calculate_impermanent_loss {e}'.format(e=e))

    def __calculate_hedging_costs(self):
        #try:
            hedges = get_all_available_hedges()
            all_hedges_df = pd.DataFrame(hedges)
            all_hedges_df.to_csv('delta-hedges.csv')
            hedges = [h for h in hedges if h.is_perp()]
            fees = bool(config.get('fees', 'maker'))
            for i in range(0,len(self.__balance)):
                #try:
                    balance_using = str(self.__balance[i])
                    for index, row in self.__average_df.iterrows():
                        # find the hedges that correspond to the first token:
                        token_zero_name = unwrap_token_name(
                            row['token0_name']).upper()
                        if not is_stablecoin(token_zero_name):
                            hedges_for_token_0 = [h for h in hedges if h.base_currency == token_zero_name]
                            if hedges_for_token_0:
                                hedges_for_token_0 =hedges_for_token_0[0].get_summary_dict(fees)
                                for key, value in hedges_for_token_0.items():
                                    column_name = f'token_zero_delta_{key}'
                                    #if key not in self.__average_df.columns:
                                    #    self.__average_df[column_name] = 0
                                    self.__average_df.loc[index,
                                                        column_name] = value
                                self.__average_df.loc[index, balance_using + '_token_zero_delta_hedge_min_fees'] = \
                                    hedges_for_token_0['fee_rate']/100 * 2 * \
                                    self.__balance[i] / 2
                        # find the hedges that correspond to the second token:
                        token_one_name = unwrap_token_name(
                            row['token1_name']).upper()
                        if not is_stablecoin(token_one_name):
                            hedges_for_token_1 = [h for h in hedges if h.base_currency == token_one_name]
                            if hedges_for_token_1:
                                hedges_for_token_1 = hedges_for_token_1[0].get_summary_dict(fees)
                                for key, value in hedges_for_token_1.items():
                                    column_name = f'token_one_delta_{key}'
                                    #if key not in self.__average_df.columns:
                                    #    self.__average_df[column_name] = 0
                                    self.__average_df.loc[index,
                                                        column_name] = value
                                self.__average_df.loc[index, balance_using + '_token_one_delta_hedge_min_fees'] = \
                                    hedges_for_token_1['fee_rate']/100 * 2 * \
                                    self.__balance[i] / 2
                        # calculate the total hedging costs for the row:
                        self.__average_df.loc[index, balance_using + '_base_hedging_costs_in_$'] = \
                            self.__average_df.loc[index, balance_using + '_token_zero_delta_hedge_min_fees'] + \
                            self.__average_df.loc[index, balance_using +
                                                  '_token_one_delta_hedge_min_fees']
                    # fill NaNs with 0
                    self.__average_df.fillna(0, inplace=True)
                #except Exception as e:
                #    print('Error in hedging cost Loop {e}'.format(e=e))
            self.__save_average_df()
        #except Exception as e:
            #print('Error in calculate_hedging_costs {e}'.format(e=e))
            self.__save_average_df()

    def __calculate_average_liquidity_balanace(self):
        try:
            self.__calculate_avg_liquidity_balanace()
        except Exception as e:
            print('Error calculate_average_liquidity_balance {e}'.format(e=e))
            self.__log.info(
                'Error calculate_average_liquidity_balance {e}'.format(e=e))

    def __calculate_avg_liquidity_balanace(self):
        # This Function Calculate the Avergae Liquidity Balance Of each pool
        # It loop through all the pool and find the the average TVL and Store it in average_df and
        # at the end it stores in file Average.csv
        try:
            self.__average_df = self.__initialize_new_column_in_dataframe(self.__average_df,
                                                                          'average_daily_liquidity_of_pool_in_$',
                                                                          'float')
            for x, row in self.__average_df.iterrows():
                try:
                    # Gets the average Value for 7 days for TVL
                    value = self.__calculate_average(row['lpToken'], 'TVL')
                    # Storing
                    self.__average_df['average_daily_liquidity_of_pool_in_$'][x] = value
                    # the Average daily liquidity
                except Exception as e:
                    print('Error in forloop calculate_previous_liquidity_balanace {e}'.format(
                        e=e))  # In case error, the error is printed
                    self.__log.info('Error in forloop calculate_previous_liquidity_balanace {e}'.format(
                        e=e))  # In case error, the error is logged into file
            self.convert_values('average_daily_liquidity_of_pool_in_$')
            self.__save_average_df()
        except Exception as e:
            print(
                'Error calculate_previous_liquidity_balanace {e}'.format(e=e))
            self.__log.info(
                'Error calculate_previous_liquidity_balanace {e}'.format(e=e))

    def __calculate_rate_of_exchange_fees(self):
        try:
            self.__average_df = self.__initialize_new_column_in_dataframe(self.__average_df,
                                                                          'exchange_fee%',
                                                                          'float')
            self.__average_df['exchange_fee%'] = EXCHANGE_FEE
            self.__save_average_df()
        except Exception as e:
            print('Error In calculate_rate_of_exchange_fees {e}'.format(e=e))
            self.__log.info(
                'Error In calculate_rate_of_exchange_fees {e}'.format(e=e))
            return 0

    def __calculate_daily_exchange_fee_rate_per_USD_of_pair(self):
        try:
            for i in range(len(self.__balance)):
                balance_using = str(self.__balance[i])
                self.__average_df = self.__initialize_new_column_in_dataframe(self.__average_df, balance_using
                                                                              + '_daily_basic_earning_in_$',
                                                                              'float')
                self.__pool_df = self.__initialize_new_column_in_dataframe(self.__pool_df, balance_using +
                                                                           '_daily_basic_earning_in_%',
                                                                           'float')

                for index, row in self.__pool_df.iterrows():
                    try:
                        if index > self.__POOL_LIMIT and self.__debugging:  # if the System is in running in
                            # debugging mode
                            break
                        fee = float(self.__pool_df['lp_reward_fee_24h'][index])
                        TVL = float(
                            self.__pool_df['TVL'][index]) + self.__balance[i]
                        if fee <= 0 or TVL <= 0:
                            exchange_fee_rate_per_usd = 0
                        else:
                            daily_basic_earning = ((fee / TVL) * 100)
                            annual_basic_earning = (
                                daily_basic_earning * DAYS_IN_YEAR)
                        self.__pool_df[balance_using +
                                       '_daily_basic_earning_in_%'][index] = daily_basic_earning
                        self.__average_df[balance_using + '_daily_basic_earning_in_$'][index] = self.__balance[i] * (
                            daily_basic_earning / 100)

                    except Exception as e:
                        self.__log.info(
                            'Error in calculate_daily_exchange_fee_rate_per_USD_of_pair {e}'.format(e=e))
                        print(
                            'Error in calculate_daily_exchange_fee_rate_per_USD_of_pair {e}'.format(e=e))

            for i in range(len(self.__balance)):
                balance_using = str(self.__balance[i])
                self.__average_df = self.__initialize_new_column_in_dataframe(self.__average_df, balance_using
                                                                              + '_daily_basic_earning_in_BPS',
                                                                              'float')
                for index, row in self.__pool_df.iterrows():
                    try:

                        self.__average_df[balance_using + '_daily_basic_earning_in_BPS'][
                            index] = row[balance_using + '_daily_basic_earning_in_%'] * 100
                    except Exception as e:
                        self.__log.info(
                            'Error in calculate_daily_exchange_fee_rate_per_USD_of_pair {e}'.format(e=e))
                        print(
                            'Error in calculate_daily_exchange_fee_rate_per_USD_of_pair {e}'.format(e=e))
                self.convert_values(
                    balance_using + '_daily_basic_earning_in_$')
                self.convert_values(
                    balance_using + '_daily_basic_earning_in_BPS')
            self.__save_average_df()
        except Exception as e:
            print(
                'Error in calculate_daily_exchange_fee_rate_per_USD_of_pair {e}'.format(e=e))
            self.__log.info(
                'Error in calculate_daily_exchange_fee_rate_per_USD_of_pair {e}'.format(e=e))

    def __calculate_average(self, address, column_header):
        try:
            # This function finds the average from previous_days_df
            # This Function reads the file upto last 7 days from storage
            # The function call _read_last_file, read the previous file available in storage
            # Address Paramert tells about the pool to look info files
            # this function goes through previous_days_df and find the information give in column_header
            # parameter and find the average of it.
            self.__save_pool_info()
            self.__get_previous_days_information_from_stored_file()
            total_7d = 0.0
            for i in range(len(self.__previous_days_information)):
                row = self.__previous_days_information[i].loc[
                    (self.__previous_days_information[i]['lpToken'] == address)]
                if row.empty:
                    if i == 0:
                        return total_7d
                    else:
                        total_7d = total_7d / i
                        return total_7d

                value = str(row[column_header].values[0])
                if "%" in value:
                    value = value.replace("%", "")
                total_7d = total_7d + float(value)
            total_7d = total_7d / len(
                self.__previous_days_information)  # This average over the number of files which were available
            return total_7d
        except Exception as e:
            print('Error In Finding Values From dataframes {e}'.format(e=e))
            self.__log.info(
                'Error In Finding Values From dataframes {e}'.format(e=e))
            return 0

    def __read_csv_file_using_index(self, index: int) -> pd.DataFrame:
        try:
            date_string = f"pool_information 0{date.today().month}.{date.today().day - index}.{date.today().year}.csv"
            # Check if the file with specific date exist
            if exists('./Data Set/' + date_string):
                file = pd.read_csv(
                    './Data Set/' + date_string).set_index('index')  # Read the pool information for specifc date
                file.fillna(0)  # Replace the empty values with 0
                return file
            else:
                return pd.DataFrame([])
        except Exception as e:
            print('Error in __read_csv_file_using_index {e}'.format(e=e))
            self.__log.info(
                'Error in __read_csv_file_using_index {e}'.format(e=e))

    def __get_previous_days_information_from_stored_file(self):
        # This Function Read the Pool Information File From the Storage
        # It looks for previous 7 files in total. Included of today
        try:
            self.__previous_days_information = {}
            # Loop till Past 7 Days Including Today
            for index in range(0, AVERAGE_DAYS):
                file = self.__read_csv_file_using_index(index)
                if file.empty:
                    break
                self.__previous_days_information[len(
                    self.__previous_days_information)] = file
        except Exception as error:
            print(
                'Error in get_previous_days_information_from_stored_file {e}'.format(e=error))
            self.__log.info(
                'Error in get_previous_days_information_from_stored_file {e}'.format(e=error))

    def __initialize_average_df(self):  # Initialization of Average Dataframe
        try:
            self.__average_df = self.__pool_df.copy(deep=True)
            self.convert_values('Farm_Liquidity')
            self.convert_values('TVL')
            self.convert_values('lp_reward_fee_24h')
            self.convert_values('volume_24h')
        except Exception as e:
            print('Error initialize_average_df {e}'.format(e=e))
            self.__log.info('Error initialize_average_df {e}'.format(e=e))

    def __calculate_average_trading_balanace(self):
        try:
            self.__calculate_avg_trading_balance()
        except Exception as e:
            print(
                'Error in calculate_average_trading_balanace {e}'.format(e=e))
            self.__log.info(
                'Error in calculate_average_trading_balanace {e}'.format(e=e))

    def __calculate_avg_trading_balance(self):
        # Finds Out the Average of Trading Volume For the Last 7 Days
        try:
            self.__average_df = self.__initialize_new_column_in_dataframe(self.__average_df,
                                                                          'average_daily_trading_volume_of_pool_in_$',
                                                                          'float')
            for x, row in self.__average_df.iterrows():
                try:
                    # Finding the average value of the
                    value = self.__calculate_average(
                        row['lpToken'], 'volume_24h')
                    # volume from past 7 days
                    self.__average_df['average_daily_trading_volume_of_pool_in_$'][
                        x] = value  # Storing The avg daily\
                    # volume to dataframe
                except Exception as e:
                    print(
                        'Error in forloop calculate_avg_trading_balance {e}'.format(e=e))
                    self.__log.info(
                        'Error in forloop calculate_avg_trading_balance {e}'.format(e=e))
            self.convert_values('average_daily_trading_volume_of_pool_in_$')
            self.__save_average_df()
        except Exception as e:
            print('Error in calculate_avg_trading_balance {e}'.format(e=e))
            self.__log.info(
                'Error in calculate_avg_trading_balance {e}'.format(e=e))

    def __calculate_current_mining_reward(self):
        # Find Todays Mining Reward and Annual Mining Reward Using todays information
        try:
            # Loop Through All The Pools
            cake_price = self.__pancake_Blockchain.get_platform_token_price()
            master_chef_contract_information = self.__pancake_Blockchain.get_master_chef_information()
            for i in range(len(self.__balance)):
                balance_using = str(self.__balance[i])
                self.__pool_df = self.__initialize_new_column_in_dataframe(self.__pool_df, balance_using +
                                                                           '_Mining_Reward', 'float')
                self.__pool_df = self.__initialize_new_column_in_dataframe(self.__pool_df, balance_using +
                                                                           '_Mining_Reward_Annually', 'float')
                for index, row in self.__pool_df.iterrows():
                    try:
                        if row['isRegular']:
                            pool_reward = master_chef_contract_information['regular_cake_per_block']
                            total_point = master_chef_contract_information['total_regular_allocation']
                        else:
                            pool_reward = master_chef_contract_information['special_cake_per_block']
                            total_point = master_chef_contract_information['total_special_allocation']
                        liquidity = float(
                            row['Farm_Liquidity']) + self.__balance[i]
                        allocated_point = row['allocPoint']
                        mining_reward_of_pool_yearly = self.__calculate_mining_reward(cake_price, pool_reward,
                                                                                      liquidity,
                                                                                      allocated_point, total_point)
                        daily_reward = mining_reward_of_pool_yearly / DAYS_IN_YEAR
                        self.__pool_df[balance_using +
                                       '_Mining_Reward_Annually'][index] = mining_reward_of_pool_yearly
                        self.__pool_df[balance_using +
                                       '_Mining_Reward'][index] = daily_reward
                    except Exception as e:
                        print('Error in calculate_current_mining_reward for  {e}'.format(
                            e=row['lpToken']))
                        self.__log.info(
                            'Error in calculate_current_mining_reward for  {e}'.format(e=row['lpToken']))
                self.__save_pool_info()
        except Exception as e:
            print('Error in calculate_current_mining_reward {e}'.format(e=e))
            self.__log.info(
                'Error in calculate_current_mining_reward {e}'.format(e=e))

    def __calculate_mining_reward(self, cake_price, reward, liquidity, allocation_point,
                                  total_point):
        # This Function Perform the calculation for Mining Reward
        # Formula = ((CAKE PRICE * (ALLOCATED POINT / TOTAL POINT) * REWARD * Daily_Blocks * Days_In_Year) / (Farm
        # Liquidity + BALANCE)) * 100)
        # This Function Find APR
        # If Something goes wrong during calculation it returns 0
        try:
            if liquidity == 0:
                return 0
            number_of_blocks = DAILY_BLOCKS * DAYS_IN_YEAR  # In an Year
            APR = (cake_price * (allocation_point / total_point) *
                   reward * number_of_blocks) / float(liquidity) * 100
            return APR
        except Exception as e:
            print('Error in __calculate_mining_reward {e}'.format(e=e))
            self.__log.info(
                'Error in __calculate_mining_reward {e}'.format(e=e))
            return 0

    def __calculate_average_mining_reward(
            self):
        # It finds the Average Mining Reward, and Mining Reward Annually using history data
        try:
            for i in range(len(self.__balance)):
                balance_using = str(self.__balance[i])
                self.__average_df = self.__initialize_new_column_in_dataframe(self.__average_df, balance_using +
                                                                              '_daily_mining_reward_in_BPS', 'float')
                for x, row in self.__average_df.iterrows():
                    try:
                        value = self.__calculate_average(
                            row['lpToken'], balance_using + '_Mining_Reward')
                        self.__average_df[balance_using +
                                          '_daily_mining_reward_in_BPS'][x] = value * 100
                    except Exception as e:
                        print(
                            'Error in forloop calculate_average_mining_reward {e}'.format(e=e))
                        self.__log.info(
                            'Error in forloop calculate_average_mining_reward {e}'.format(e=e))
                self.convert_values(
                    balance_using + '_daily_mining_reward_in_BPS')
            self.__save_average_df()
        except Exception as e:
            print('Error in calculate_average_mining_reward {e}'.format(e=e))
            self.__log.info(
                'Error in calculate_average_mining_reward {e}'.format(e=e))

    def __initialize_new_column_in_dataframe(self, dataframe, columnheader, columntype):
        try:
            dataframe[columnheader] = pd.Series(dtype=columntype)
            dataframe = dataframe.fillna(0)
            return dataframe
        except Exception as e:
            print(
                'Error in __initialize_new_column_in_dataframe {e}'.format(e=e))
            self.__log.info(
                'Error in __initialize_new_column_in_dataframe {e}'.format(e=e))

    def __save_pool_info(self):  # Stores the Average Value Dataframe
        try:
            date_string = f"pool_information 0{date.today().month}.{date.today().day}.{date.today().year}.csv"
            # Storing The Pool Information TO CSV FIle
            self.__pool_df.to_csv('./Data Set/' + date_string)
        except Exception as e:
            print('Error in __save_pool_info {e}'.format(e=e))
            self.__log.info('Error in __save_pool_info {e}'.format(e=e))

    def __save_average_df(self):
        try:

            self.__average_df.to_csv('./Data Set/Average.csv')
        except Exception as e:
            print('Error in __save_average_df {e}'.format(e=e))
            self.__log.info('Error in __save_average_df {e}'.format(e=e))

    def convert_values(self, header: str):
        try:
            #
            for index, row in self.__average_df.iterrows():
                value_in_df = self.__average_df[header][index]

                if value_in_df > 1000:
                    updated_value = str(round(value_in_df / 1000, 2)) + 'K'
                elif value_in_df > 1000000:
                    updated_value = str(round(value_in_df / 1000000, 2)) + 'M'
                elif value_in_df > 1000000000:
                    updated_value = str(
                        round(value_in_df / 1000000000, 2)) + 'B'
                else:
                    updated_value = str(round(value_in_df, 2))
                self.__average_df[header][index] = updated_value

            self.__average_df[header] = self.__average_df[header].astype(str)
            self.__average_df.style.set_properties(**{'text-align': 'right'})
        except Exception as e:
            print('Error In convert_value {e}'.format(e=e))

import datetime

from bullets.data_source.data_source_interface import DataSourceInterface, Resolution
from bullets.portfolio.holding import Holding
from bullets.portfolio.transaction import Transaction
from bullets import logger


class Portfolio:

    def __init__(self,
                 start_balance: float,
                 data_source: DataSourceInterface,
                 slippage_percent: int,
                 transaction_fees: int):
        """
        Initializes the required variables for the Portfolio
        Args:
            start_balance (float): Balance of the portfolio
            data_source (DataSourceInterface): Source used to retrieve market information
            slippage_percent (int): Slippage percent to be applied to every purchase
            transaction_fees (int): Fees to be applied to every transaction
        """
        self.start_balance = start_balance
        self.cash_balance = start_balance
        self.holdings = {}
        self.transactions = []
        self.timestamp = None
        self.data_source = data_source
        self.slippage_percent = slippage_percent
        self.transaction_fees = transaction_fees

    def market_order(self, symbol: str, nb_shares: float):
        """
        Order a stock at market price + slippage
        Args:
            symbol: Symbol of the stock you want to buy
            nb_shares: Number of shares of the order
        Returns: The transaction. The status explains whether the transaction was successful
        """
        theoretical_price = self.data_source.get_price(symbol, self.timestamp)
        transaction = self.__validate_and_create_transaction__(symbol, nb_shares, theoretical_price,
                                                               self.slippage_percent, self.transaction_fees)
        self.transactions.append(transaction)
        if transaction.status == Transaction.STATUS_SUCCESSFUL:
            self.__put_holding__(symbol, nb_shares, transaction.simulated_price)
        return transaction

    def update_and_get_balance(self):
        """
        Updates the current prices of the holdings and returns the total balance of the portfolio
        Returns: Total balance of the portfolio
        """
        balance = self.cash_balance
        for holding in self.holdings.values():
            holding.current_price = self.data_source.get_price(holding.symbol, self.timestamp)
            balance = balance + holding.nb_shares * holding.current_price
        return balance

    def get_percentage_profit(self):
        return round(self.update_and_get_balance() / self.start_balance * 100 - 100, 2)

    def __validate_and_create_transaction__(self, symbol: str, nb_shares: float, theoretical_price: float,
                                            slippage_percent: int, transaction_fees: int):
        """
        Validates and creates a transaction
        Args:
            symbol: Symbol of the stock you want to buy
            nb_shares: Number of shares of the order
            theoretical_price: Theoretical price per share from market
            slippage_percent: Strategy's slippage percent
            transaction_fees: Fees that need to be applied to the transaction
        Returns: Transaction with a successful or failed status
        """
        simulated_price = None
        if theoretical_price is None:
            status = Transaction.STATUS_FAILED_SYMBOL_NOT_FOUND
        else:
            simulated_price = self.__get_slippage_price__(theoretical_price, slippage_percent, symbol)
            if self.cash_balance >= nb_shares * simulated_price + transaction_fees:
                self.cash_balance = self.cash_balance - (nb_shares * simulated_price + transaction_fees)
                status = Transaction.STATUS_SUCCESSFUL
            else:
                status = Transaction.STATUS_FAILED_INSUFFICIENT_FUNDS
        return Transaction(symbol, nb_shares, theoretical_price, simulated_price, self.timestamp, status,
                           transaction_fees)

    def __get_slippage_price__(self, theoretical_price: float, slippage_percent: int, symbol: str) -> float:
        # todo: see https://github.com/AlgoETS/BullETS/issues/46
        if self.data_source.resolution is not Resolution.DAILY:
            return theoretical_price
        else:
            daily_high_price = self.__get_daily_high_price__(symbol)
            actual_slippage_percent = float(slippage_percent / 100)
            slippage_factor = (daily_high_price - theoretical_price) * actual_slippage_percent
            simulated_slippage_price = theoretical_price + slippage_factor
            return simulated_slippage_price

    def __get_daily_high_price__(self, symbol: str) -> float:
        # previous_resolution = self.data_source.resolution
        # self.data_source.resolution = Resolution.DAILY
        current_day = datetime.datetime(self.timestamp.year, self.timestamp.month, self.timestamp.day, 00, 00, 00)
        high_price = self.data_source.get_price(symbol, current_day, "high")
        # self.data_source.resolution = previous_resolution
        return high_price

    def __put_holding__(self, symbol: str, nb_shares: float, price: float):
        """
        Creates, updates or deletes a holding based on the number of shares
        Args:
            symbol: Symbol of the stock you want to buy
            nb_shares: Number of shares of the order
            price: Price per share
        """
        holding = self.holdings.get(symbol, Holding(symbol))
        nb_shares = holding.add_shares(nb_shares, price)
        if nb_shares == 0:
            self.holdings.pop(symbol)
        else:
            self.holdings[symbol] = holding

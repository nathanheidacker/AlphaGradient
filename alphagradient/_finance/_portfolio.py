# -*- coding: utf-8 -*-
"""AG module containing portfolio class

Todo:
    * Improve portfolio analysis tools
"""

# Standard imports
from __future__ import annotations

from datetime import datetime
from numbers import Number
from copy import copy, deepcopy
from datetime import timedelta
import math

# Third party imports
import pandas as pd
import numpy as np

# Local imports
from ._asset import types, Asset
from ._standard import Currency
from .. import utils

# Typing
from typing import (
    TYPE_CHECKING,
    Any,
    TypeVar,
    Union,
    Optional,
    Literal,
    Generic,
    Iterable,
)

from ._asset import Asset
from ._standard import Call

Asset_T = TypeVar("Asset_T", bound=Asset, covariant=True)

if TYPE_CHECKING:
    from ._collections import Environment


class View:
    def __init__(self, position: Position) -> None:
        self.asset = position.asset.key
        self.quantity = position.quantity
        self.short = position.short
        self.cost = position.cost
        self.value = position.value
        self.symbol = position.symbol
        self.cash = isinstance(position, Cash)
        self.unit = position.asset.unit
        self.units = position.asset.units
        # self.beta = position.asset.beta()

    def __str__(self) -> str:
        if self.cash:
            return f"CASH {self.symbol}{self.value}"
        short = "SHORT" if self.short else "LONG"
        unit = self.unit if self.quantity == 1 else self.units
        return (
            f"{self.asset}_{short}: {self.quantity} {unit} @ "
            f"{self.symbol}"
            f"{round(self.value / self.quantity, 2)} /{self.unit}"
        )

    def __repr__(self) -> str:
        return self.__str__()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, View):
            return NotImplemented
        return self.key == other.key

    def __getstate__(self) -> dict:
        return self.__dict__

    def __setstate__(self, state: dict) -> None:
        self.__dict__ = state

    @property
    def key(self) -> str:
        short = "SHORT" if self.short else "LONG"
        return f"{self.asset}_{short}"

    def empty(self) -> View:
        empty = deepcopy(self)
        empty.quantity, empty.cost = 0, 0
        return empty


class Position(Generic[Asset_T]):
    """Object representing a position in a financial asset

    An object representing a financial stake in some underlying asset,
    to be used in portfolios to track holdings. Automatically updates
    value using the value of the underlying asset, and keeps track of
    average cost to enter the position.

    Attributes:
        asset (Asset): the underyling asset
        quantity (Number): the quantity of the asset represented by the
            position
        short (bool): True if short, False if long
        cost (Number): The total cost to enter this position
        value (Number): The current market value of this position
        average_cost (Number): The cost of this position per unit
        key (str): A key used for indexing this position in dicts
        symbol (str): A symbol corresponding to the currency of the
            asset underlying this position
        price (str): A rounded version of value with the symbol
            attached, used for printing purposes
        expired (bool): Whether or not this position is expired
        total_return (Number): The total return of this position
            relative to its cost, represented in the base currency
            of the underlying asset
        percent_return (Number): The total return as a percentage
            of the cost

    """

    def __init__(self, asset: Asset_T, quantity: float, short: bool = False) -> None:
        self.asset: Asset_T = asset
        self._quantity = round(quantity, 2)
        self.short = short
        self.cost = self.value
        self.history = self._history()

    def __add__(self, other: Position) -> Position:
        # Positions can only be added to other positions
        if not self == other:
            return NotImplemented

        new = copy(self)

        # Updating quantity
        new.quantity += other.quantity

        # Updating position cost
        short = -1 if new.short else 1
        new.cost += new.asset.value * other.quantity * short

        # Updating the position history
        new.update_history()

        return new

    def __sub__(self, other: Position) -> Position:
        # Positions can only be subtracted from other positions
        if not self == other:
            return NotImplemented

        new = copy(self)

        # Updating quantity
        new.quantity -= other.quantity

        # Updating position cost
        short = -1 if new.short else 1
        new.cost -= new.asset.value * other.quantity * short

        # Updating position history
        new.update_history()

        return new

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Position):
            return NotImplemented
        return self.asset is other.asset and self.short is other.short

    def __str__(self) -> str:
        unit = self.asset.unit if self.quantity == 1 else self.asset.units
        return (
            f"<{self.quantity} {self.asset.key} {unit} @ {self.symbol}{self.average_cost}"
            f" /{self.asset.unit} | VALUE: {self.price} "
            f"| RETURN: {round(self.percent_return, 2)}%>"
        )

    def __repr__(self) -> str:
        unit = self.asset.unit if self.quantity == 1 else self.asset.units
        return (
            f"<{self.quantity} {unit} @ {self.symbol}{self.average_cost} "
            f"| RETURN: {round(self.percent_return, 2)}%>"
        )

    def __setstate__(self, state: dict) -> None:
        self.__dict__ = state

    def __getstate__(self) -> dict:
        return self.__dict__

    def __copy__(self) -> Position:
        new = Position(self.asset, self.quantity, self.short)
        new.history = self.history
        return new

    @property
    def quantity(self) -> float:
        return self._quantity

    @quantity.setter
    def quantity(self, value: float) -> None:
        self._quantity = round(value, 2)

    @property
    def key(self) -> str:
        short = "SHORT" if self.short else "LONG"
        return f"{self.asset.key}_{short}"

    @property
    def symbol(self) -> str:
        return types.currency.instances[self.asset.base].symbol

    @property
    def value(self) -> float:
        return self.asset.value * self.quantity * (-1 if self.short else 1)

    @property
    def price(self) -> str:
        price = abs(self.value)

        if price != 0:
            r = 2
            while price < 1:
                r += 1
                price *= 10

            price = round(self.value, r)

        return f"{self.symbol}{price}"

    @property
    def average_cost(self) -> float:
        return round(self.cost / self.quantity, 2)

    @property
    def expired(self) -> bool:
        return self.quantity <= 0 or self.asset.expired

    @property
    def total_return(self) -> float:
        return self.value - self.cost

    @property
    def percent_return(self) -> float:
        return (self.total_return / self.cost) * 100 * (-1 if self.short else 1)

    def expire(self, portfolio: Portfolio) -> None:
        """Expires this position within the input portfolio

        Args:
            portfolio (Portfolio): The portfolio owning this pos

        Returns:
            None (NoneType): Modifies this position/portfolio inplace
        """
        self.asset.expire(portfolio, self)

    def view(self) -> View:
        """A memory efficient copy of the position

        Returns a 'view' of the position in its current state for use
        in portfolio histories.

        Returns:
            view: memory efficient copy of the position
        """
        return View(self)

    def _history(self) -> pd.DataFrame:
        """A pandas DataFrame of this position's value history

        Returns a datetime indexed dataframe of this positions market
        value history and cost, which is automatically updates when
        changes in the position or the underlying asset occur

        Returns:
            history (pd.DataFrame): position history
        """
        history = pd.DataFrame(
            [[self.value, self.cost]],
            columns=["VALUE", "COST"],
            index=pd.DatetimeIndex([self.asset.date], name="DATE"),
        )

        return history

    def update_history(self) -> None:
        """updates the positions history to reflect changes

        Updates this positions history whenever changes in the position
        occur, either in the size of the position itself or the price
        of the underlying asset

        Returns:
            updates the history inplace, no return value
        """
        self.history.loc[self.asset.date] = [self.value, self.cost]


class Cash(Position[Currency]):
    """A special type of position representing some quantity of a
    currency"""

    def __init__(self, quantity: float, code: Optional[str] = None) -> None:
        code = Currency.base if code is None else code
        super().__init__(Currency(code), quantity)

    def __str__(self) -> str:
        return f"<{self.asset.code} {self.asset.symbol}{self.quantity}>"

    def __repr__(self) -> str:
        return self.__str__()

    def __add__(self, other: object) -> Cash:
        if not isinstance(other, (Cash, float, int)):
            return NotImplemented

        other = self.to_cash(other)
        new = copy(self)

        if new.asset is other.asset:
            new.quantity += other.quantity
        else:
            value = new.asset.convert(other.asset.code) * other.quantity
            new.quantity += value

        return new

    def __sub__(self, other: object) -> Cash:
        if not isinstance(other, (Cash, int, float)):
            return NotImplemented

        other = self.to_cash(other)
        new = copy(self)

        if new.asset is other.asset:
            new.quantity -= other.quantity
        else:
            value = new.asset.convert(other.asset.code) * other.quantity
            new.quantity -= value

        return new

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, (Cash, int, float)):
            return NotImplemented
        other = self.to_cash(other)
        return self.value < other.value

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, (Cash, int, float)):
            return NotImplemented
        other = self.to_cash(other)
        return self.value > other.value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, (Cash, int, float)):
            return NotImplemented
        other = self.to_cash(other)
        return self.value == other.value

    def __copy__(self) -> Cash:
        new = Cash(self.quantity, self.asset.code)
        new.history = self.history
        return new

    @staticmethod
    def from_position(position: Position) -> Cash:
        """Returns a cash object representing the value of the asset passed"""
        return Cash(position.value, position.asset.base)

    def from_number(self, other: float) -> Cash:
        return Cash(other, self.asset.code)

    def from_cash(self, other: Cash) -> Cash:
        quantity = self.asset.rate(other.asset.code) * other.quantity
        return Cash(quantity, self.asset.code)

    def convert(self, code: str, inplace: bool = False) -> Optional[Cash]:
        """converts this cash asset to another currency"""
        quantity = self.asset.rate(code) * self.quantity
        new = Cash(quantity, code)

        if not inplace:
            return new

        self = new
        return None

    def to_cash(self, obj: Union[Cash, Position, float]) -> Cash:
        if isinstance(obj, (int, float)):
            return self.from_number(obj)
        elif isinstance(obj, Cash):
            return self.from_cash(obj)
        elif isinstance(obj, Position):
            return self.from_position(obj)
        raise TypeError(
            f"obj type {obj.__class__.__name__} can not be converted to Cash"
        )

    @property
    def expired(self) -> Literal[False]:
        """Always returns false, Cash positions never expire"""
        return False

    @property
    def code(self) -> str:
        return self.asset.code


class Portfolio:
    """An object representing a portfolio of financial assets

    AlphaGradient portfolios are designed to interact natively with
    AlphaGradient assets, and provide all of the functionality one
    would expect with a normal financial portfolio.

    Attributes:
        cash (float): How much of the base currency the Portfolio holds
        date (datetime): the last time this position was altered or
            valuated
        positions (dict): A dictionary of all of this Portfolio's
            current positions
        longs (dict): A dictionary of all long positions
        shorts (dict): A dictionary of all short positions
        base (str): A currency code representing this portfolio's base
            currency
        value (Number): The total value of this portfolio, represented
            in the portfolio's base currency
        liquid (Number): The sum of all of the portfolio's liquid assets
    """

    def __init__(
        self,
        initial: float,
        name: Optional[Union[str, Environment]] = None,
        base: Optional[str] = None,
    ) -> None:
        if isinstance(name, types.environment.c):
            self.name = self._generate_name(environment=name)
        else:
            assert type(name) is str  # Mypy doesnt recognize the type narrowing above
            self.name = self._generate_name() if name is None else name
        self._base = Currency.base if base is None else base
        self._cash = Cash(initial, self.base)
        self._positions: dict[str, Position] = {"CASH": self.cash}
        self.history = self._history()
        self.type.instances[self.name] = self  # type: ignore[attr-defined]

    def __getattr__(self, attr: str) -> dict[str, Position]:
        if attr in [c.__name__.lower() for c in types.instantiable()]:
            return {
                k: v
                for k, v in self.positions.items()
                if v.asset.__class__.__name__.lower() == attr
            }
        raise AttributeError(f"Portfolio has no attribute {attr}")

    def __str__(self) -> str:
        return f"<AlphaGradient Portfolio at {hex(id(self))}>"

    def __repr__(self) -> str:
        return self.__str__()

    def _generate_name(
        self, last: list[int] = [0], environment: Environment = None
    ) -> str:
        """generates a name for this portfolio"""
        if environment is None:
            if last[0] == 0 and not self.type.instances:  # type: ignore[attr-defined]
                return "MAIN"
            else:
                name = f"P{last[0]}"
                last[0] += 1
                return name
        else:
            if environment._portfolios:
                return f"P{len(environment._portfolios) - 1}"
            else:
                return "MAIN"

    @property
    def base(self) -> str:
        return self._base

    @base.setter
    def base(self, new_base: str) -> None:
        if Currency.validate_code(new_base, error=True):
            self._base = new_base

    @property
    def base_symbol(self) -> str:
        return self._cash.symbol

    @property
    def positions(self) -> dict[str, Position]:
        self._positions["CASH"] = self._cash
        return self._positions

    def update_positions(self) -> None:
        for expired in [pos for pos in self._positions.values() if pos.asset.expired]:
            expired.expire(self)

        self._positions = {
            k: pos for k, pos in self._positions.items() if not pos.expired
        }

        self._positions["CASH"] = self.cash

    @property
    def cash(self) -> Cash:
        return self._cash

    @cash.setter
    def cash(self, n: float) -> None:
        if isinstance(n, Number):
            self._cash.quantity = n
        elif isinstance(n, Cash):
            self._cash = Cash.from_position(n)
        else:
            raise TypeError(
                "Cash can only be assigned to a numerical "
                "value or another cash instance."
            )

    @property
    def longs(self) -> dict[str, Position]:
        """A dictionary which associates all long positions with their asset keys"""
        return {v.asset.key: v for k, v in self.positions.items() if not v.short}

    @property
    def shorts(self) -> dict[str, Position]:
        """A dictionary which assocaites all short positions with their asset keys"""
        return {v.asset.key: v for k, v in self.positions.items() if v.short}

    @property
    def value(self) -> float:
        """This portfolio's net market value"""
        return sum([position.value for position in self.positions.values()])

    @property
    def liquid(self) -> float:
        return self.cash.quantity

    def validate_transaction(
        self, asset: Asset, quantity: float, short: bool = False
    ) -> bool:
        if not short:
            if isinstance(asset, Currency) and asset.is_base:
                return False

        elif quantity == 0:
            return False

        if quantity < 0:
            raise ValueError(
                "Purchase quantity must be or exceed 0, " f"received {quantity}"
            )

        elif asset.date != self.date:
            raise ValueError(
                "Unable to complete transaction, "
                f"{asset.date=} does not match "
                f"{self.date=}. Please ensure portfolio "
                "and asset dates are synced"
            )

        elif (asset.market_open != asset.market_close) and (
            asset.date.time() > asset.market_close
            or asset.date.time() < asset.market_open
        ):
            raise ValueError(
                f"Unable to complete transaction for {asset=} because the market is closed. Market close is {utils.timestring(asset.market_close)}, time of last valuation is {utils.timestring(asset.date)}"
            )

        return True

    def buy(self, asset: Asset, quantity: float) -> None:
        """Buys an asset using this portfolio

        Creates a long position in the given asset with a purchase volume given by 'quantity'.

        Args:
            asset (Asset): The asset in which to create a long position
            quantity (Number): The purchase quantity

        Returns:
            Modifies this portfolio's positions inplace. No return value
        """
        # Ensure that the transaction can occur
        if not self.validate_transaction(asset, quantity):
            return

        # Creating the position to be entered into
        position = Position(asset, quantity)

        if position.value > self.cash:
            raise ValueError(
                f"Purchasing {quantity} units of "  # type: ignore[attr-defined]
                f"{asset.name} {asset.type} requires "
                f"{Cash(position.value, position.asset.base)}, "
                f"but this portfolio only has {self.cash} "
                "in reserve"
            )

        # Updating the position if one already exists
        try:
            self.positions[position.key] += position
        except KeyError:
            self.positions[position.key] = position

        # Updating the potfolio's cash reserves
        self._cash -= Cash.from_position(position)

        # Updating the portfolio's history to reflect purchase
        self.update_positions()
        self.update_history()

    def sell(self, asset: Asset, quantity: float) -> None:
        """Sells a long position in this portfolio

        Decrements a long position in the given asset by 'quantity'.
        Maximum sale quantity is the amount owned by the portfolio.

        Args:
            asset (Asset): The asset of the corresponding decremented
                position
            quantity (Number): The sale quantity

        Returns:
            Modifies this portfolio's positions inplace. No return value
        """
        # Ensure that the transaction can occur
        if not self.validate_transaction(asset, quantity):
            return

        # Creating the position to be sold
        position = Position(asset, quantity)

        # Selling the position if the current position is large enough
        # to satisfy the sale quantity
        try:
            current = self.positions[position.key]
            if current.quantity >= quantity:
                self._cash += Cash.from_position(position)
                self.positions[position.key] -= position
            else:
                raise ValueError(
                    f"Portfolio has insufficient long "  # type: ignore[attr-defined]
                    f"position in asset {asset.name} "
                    f"{asset.type} to sell {quantity} "
                    f"units. Only {current} units "
                    "available"
                )

        # We can only sell positions that we own
        except KeyError as e:
            raise ValueError(
                "Portfolio has no long position in asset "  # type: ignore[attr-defined]
                f"{asset.name} {asset.type}"
            ) from e

        # Updating the portfolio's history to reflect sale
        self.update_positions()
        self.update_history()

    def short(self, asset: Asset, quantity: float) -> None:
        """Shorts an asset using this portfolio

        Creates a short position in the given asset with a short volume given by 'quantity'.

        Args:
            asset (Asset): The asset in which to create a short position
            quantity (Number): The short sale quantity

        Returns:
            Modifies this portfolio's positions inplace. No return value
        """
        # Ensure that the transaction can occur
        if not self.validate_transaction(asset, quantity, short=True):
            return

        # Creating the position to be shorted
        position = Position(asset, quantity, short=True)

        # Updating the position if one already exists
        try:
            self.positions[position.key] += position
        except KeyError:
            self.positions[position.key] = position

        # Updating the potfolio's cash reserves
        self._cash -= Cash.from_position(position)

        # Updating the portfolio's history to reflect short sale
        self.update_positions()
        self.update_history()

    def cover(self, asset: Asset, quantity: float) -> None:
        """Covers a short position in this portfolio

        Covers a short position in the given asset with a cover
        (purchase) volume given by 'quantity'.

        Args:
            asset (Asset): The asset in which to cover a short position
            quantity (Number): The cover (purchase) quantity

        Returns:
            Modifies this portfolio's positions inplace. No return value
        """
        # Ensure that the transaction can occur
        if not self.validate_transaction(asset, quantity, short=True):
            return

        # Creating the short position to be covered
        position = Position(asset, quantity, short=True)

        required = -1 * position.value
        if required > self._cash:
            raise ValueError(
                f"Covering {quantity} short sold units of "  # type: ignore[attr-defined]
                f"{asset.name} {asset.type} requires "
                f"${required}, but this portfolio only "
                f"has ${self.cash} in reserve"
            )

        # Covering the position if the current short position is large
        # enough to satisfy the quantity to cover
        try:
            current = self.positions[position.key]
            if current.quantity >= quantity:
                self.cash += Cash.from_position(position)
                self.positions[position.key] -= position
            else:
                raise ValueError(
                    "Portfolio has insufficient short "  # type: ignore[attr-defined]
                    f"position in asset {asset.name} "
                    f"{asset.type} to cover {quantity} "
                    f"units. Only {current.quantity} units"
                    " have been sold short"
                )

        # We can only cover positions that we have shorts in
        except KeyError as e:
            raise ValueError(
                "Portfolio has no short position in "  # type: ignore[attr-defined]
                f"asset {asset.name} {asset.type}"
            )

        # Updating the portfolio's history to reflect short cover
        self.update_positions()
        self.update_history()

    def _history(self) -> pd.DataFrame:
        """A history of this portfolio's positions and value

        Returns a datetime indexed pandas dataframe of this portfolio's
        positions and total market value. This function is only used
        to initialize it

        Returns:
            history (pd.DataFrame): portfolio position/value history
        """
        positions = [position.view() for position in self.positions.values()]
        return pd.DataFrame(
            [[positions, self.value]],
            columns=["POSITIONS", "VALUE"],
            index=pd.DatetimeIndex([self.date], name="DATE"),
        )

    def update_history(self) -> None:
        """updates this portfolio's history

        Returns:
            Modifies history in place. Returns nothing
        """
        positions = [position.view() for position in self.positions.values()]
        data = np.array([positions, self.value], dtype="object")
        self.history.at[self.date] = data

    def reset(self) -> None:
        """Restarts the portfolio's value history"""
        self.history = self._history()

    def invest(self, n: float) -> None:
        """Adds cash to this portfolio"""
        self.cash += n

    def liquidate(self, force: bool = False) -> None:
        """Sells all positions that are not the base currency/cash position"""
        if not force:
            for pos in self.longs.values():
                self.sell(pos.asset, pos.quantity)

            for pos in self.shorts.values():
                self.cover(pos.asset, pos.quantity)
        else:
            for pos in self.longs.values():
                if isinstance(pos.asset, Currency) and pos.asset.is_base:
                    pass
                else:
                    self.cash += Cash.from_position(pos)
                    pos.quantity = 0

            for pos in self.shorts.values():
                self.cash += Cash.from_position(pos)
                pos.quantity = 0

            self.update_positions()

    def get_position(
        self,
        asset: Asset,
        short: bool = False,
        positions: Optional[Iterable[Position]] = None,
    ) -> Optional[Position]:
        """Gets this portfolio's current position in the given asset

        Args:
            asset (Asset): The asset being searched
            short (bool): Is the position short or long
            positions (list(Asset)): The positions to be searched

        Returns:
            pos (Position): Returns a single position in the asset if
                found, otherwise None
        """
        if positions is None:
            positions = self.shorts.values() if short else self.longs.values()
        result = [pos for pos in positions if pos.asset is asset]
        if result:
            return result[0]
        return None

    def get_related_positions(
        self,
        asset: Asset,
        short: bool = False,
        positions: Optional[Iterable[Position]] = None,
    ) -> list[Position]:
        """Gets this portfolio's current positions in the given asset or related to the asset

        Args:
            asset (Asset): The asset being searched
            short (bool): Is the position short or long
            positions (list(Asset)): The positions to be searched

        Returns:
            pos (Position): Returns a list of positions that are related to the asset
        """
        if positions is None:
            positions = self.shorts.values() if short else self.longs.values()
        result = [
            pos
            for pos in positions
            if pos.asset is asset or asset in pos.asset.__dict__.values()
        ]
        return result

    def covered_call(
        self,
        call: Call,
        quantity: Optional[float] = None,
        limit: Optional[float] = None,
    ) -> float:
        """Sells calls in the given quantity, but ensures that they are 'covered' by owning stock equal to the number of shares accounted for by the contracts in the case of assignment

        Args:
            call (Call): The call to be sold short
            quantity (Number): The quantity to sell
            limit (Number): Specifies a maximum amount to sell when
                quantity is not specified

        Returns:
            sold_short (Number): The number of calls sold short
            The portfolio is also modified in place by selling the given quantity of calls and purchasing the necessary shares
        """
        # Getting the current number of owned shares
        current: Any = self.get_position(call.underlying)
        current = current.quantity if current is not None else 0

        # Getting the quantity of shares currently accounted for by calls that have already been sold short (Number of outstanding short sold calls * 100 shares per contract)
        sold_short: Any = (
            sum(
                pos.quantity
                for pos in self.get_related_positions(
                    call.underlying, short=True, positions=self.call.values()
                )
            )
            * 100
        )

        # The number of shares that are currently available to stand as collateral for a new covered call (shares owned that are not currently acting as collateral)
        available = current - sold_short

        # Determining the maximum quantity of calls that we can sell
        if quantity is None:

            # If no sale quantity is given, we find the highest possible multiple of 100 based on current liquidity, bounded to 0 (In case of negative liquidity)
            quantity = max(
                math.floor((available + (self.liquid / call.underlying.value)) / 100)
                * 100,
                0,
            )
        else:

            # Turn call quantity into share quantity
            quantity *= 100

        # Shares need to be bought
        if available < quantity:
            can_purchase = math.floor(self.liquid / call.underlying.value)
            purchase_quantity = quantity - available

            # We lack the necessary liquidity to cover the sale
            if can_purchase < purchase_quantity:
                raise ValueError(
                    f"Not enough liquidity to purchase {purchase_quantity} shares of the underyling to cover the short sale of {int(quantity / 100)} {call.name} contracts (requires {self.base_symbol}{round(purchase_quantity * call.underlying.value, 2)}, only have {self.base_symbol}{self.liquid})"
                )

            # Making the purchase
            self.buy(call.underlying, purchase_quantity)

        # Returning quantity to number of contracts rather than shares
        quantity = int(quantity / 100)

        # Selling the calls
        self.short(call, quantity)

        return quantity


# Uses a protected keyword, so must be used set outside of the class
setattr(Portfolio, "type", types.portfolio)
setattr(types.portfolio, "c", Portfolio)

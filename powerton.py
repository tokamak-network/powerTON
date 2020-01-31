from typing import List
from random import random
from dataclasses import dataclass, field

OMD = 1_000_000 # Operator Minimum Deposit TON.
# TODO : Use Decimal for accurating.

@dataclass
class User:
    name: str

    balance: float = 0.0
    delegated: float = 0.0
    delegators: List[str] = field(repr=False,
                                  default_factory=list)  # delegator list

    def add_balance(self, amount):
        self.balance += amount

    def sub_balance(self, amount):
        if self.balance < amount:
            raise Exception("Cannot remove balance more than user has")
        else:
            self.balance -= amount


@dataclass
class Operator(User):
    # POWERs
    supported_power: int = 0
    power_supporters: dict = field(default_factory=dict,
                                   metadata={"description":
                                                {"user_name": "supports power amount"}})

    # TONs
    delegatees: List[str] = field(default_factory=list)
    delegated_balances: dict = field(default_factory=dict,
                                     metadata={"description":
                                                {"user_name": "delegated ton amount"}})

    def __init__(self, user=None):
        super().__init__(user.name)

        if isinstance(user, User):
            assert user.balance >= OMD, "Not Enough TON for being Operator"
            assert len(user.delegators) == 0, "Operator does not allow delegators"

            self.balance = user.balance
        else:
            raise Exception("Only User can be Operator")

        self.delegatees = []
        self.delegated_balances = {}
        self.power_supporters = {}

        self.balance = self.balance - OMD

        self.delegatees.append(self.name)
        self.delegated_balances.update({self.name: OMD})
        for name in self.delegatees:
            self.delegated += self.delegated_balances[name]

    def delegate(self, user, amount):
        # User state update
        user.sub_balance(amount)
        user.delegated += amount

        # Operator state update
        if user.name not in self.delegators:
            self.delegatees.append(user.name)
            self.delegated_balances[user.name] = 0

        self.delegated_balances[user.name] += amount

    def undelegate(self, user, amount):
        if user.name not in self.delegators:
            raise Exception("There is no delegator in this Operator")

        if self.delegated_balances[user.name] < amount:
            raise Exception("There is not enough balance user has")
        else:
            self.delegated_balances[user.name] -= amount

            # User state update
            user.add_balance(amount)
            user.delegated -= amount


@dataclass
class Player(User):
    # powers
    power_bought: int = 0
    power_available: int = 0
    power_played: int = 0
    power_supporting: int = 0

    # win history
    history: tuple = field(default_factory=dict,
                           metadata={"description"
                                     :{"Round":
                                           ("bought_power[int]",
                                            "available_power[int]",
                                            "played_power[int]",
                                            "rewards[int]",
                                            "winner[bool]")}})

    def __init__(self, user=None):
        super().__init__(user.name)

        if isinstance(user, User):
            self.balance = user.balance

        self.history = {}  # { Phase : (bought, available, played, rewards, winner(bool)) }

    def power_up(self, operator, amount):
        if self.power_available < amount:
            raise Exception("Power : Not enough power to up")
        else:
            if self.name not in operator.power_supporters.keys():
                # Add power delegatee to operator
                operator.power_supporters[self.name] = 0

            operator.power_supporters[self.name] += amount
            operator.supported_power += amount

    def power_down(self, operator: Operator, amount):
        if self.name not in operator.power_supporters.keys():
            raise Exception("Power : no name of delegatee this operator")
        else:
            if operator.power_supporters[self.name] < amount:
                raise Exception("Power : Not enough power to down")
            else:
                operator.power_supporters[self.name] -= amount
                operator.supported_power -= amount
                self.power_available += amount

@dataclass
class Powerton:
    # Initial Economic params
    SEIGNIORAGE: float = 0.19  # fixed inflation ratio
    BLOCK_TIME: int = 13  # ethereum avg block time
    BLOCKS_YEAR: int = 2425846  # int((365 * 24 * 60 * 60) / 13)
    INITIAL_SUPPLY: int = 1_000_000_000  # will going to supply after ICO
    SEIG_PER_BLOCK: float = 0 # (INITIAL_SUPPLY * SEIGNIORAGE) / BLOCKS_YEAR
    AIRDROP_RATIO: float = 0.1  # prize to airdrop pool ratio
    AIRDROP_CHANCE: float = 0.000_1
    WINNING_CHANCE: float = 0.000_000_0001

    # Blockchain
    Last_committed = 0
    Current_block = 0
    Last_won_block = 0

    # Participants
    # User : Participant who not join staking game.
    # Operator : Plasma-evm operator who can be delegator by User or Player.
    # Player : Participant who bought Power once before.
    Users:    dict = field(default_factory=dict)
    Operators: dict = field(default_factory=dict)
    Players:   dict = field(default_factory=dict)

    # TON Staking
    Total_TON_supply: int = 0
    Total_TON_staked: int = 0
    Staking_ratio: float = 0 if Total_TON_supply == 0 else Total_TON_staked / Total_TON_supply

    # Power game
    POWER_WIN_CHANCE: float = 0.000_001
    POWER_PER_PHASE: int = 100_000

    MIN_PRIZE_POOL: int = 50_000
    MIN_POWER_PRICE: float = 0.0125

    Winning_history: dict = field(default_factory=dict)

    Current_power_phase: int = 0
    Total_sold_powers: int = 0
    Total_supported_powers: int = 0
    Power_sale: dict = field(default_factory=lambda: {i+1: {"OPEN": False,
                                                            "AVAILABLE": 0,
                                                            "SOLD": 0,
                                                            "PRICE": 0.0125 * (2 ** i)} for i in range(11)})

    Prize_pool: int = 0
    Airdrop_pool: int = 0

    # winner, next_pot, power_buyer, TON_staker
    DIST_BUY_POWER: tuple = field(default=(0.5, 0.3, 0.2, 0))
    DIST_PRIZE: tuple = field(default=(0.5, 0.2, 0.2, 0.1))
    DIST_AIRDROP: tuple = field(default=(0.8, 0.2, 0, 0))

    def __post_init__(self):
        self.SEIG_PER_BLOCK = (self.INITIAL_SUPPLY * self.SEIGNIORAGE) / self.BLOCKS_YEAR

    def _update_ton(self):
        _seigniorage = self.SEIG_PER_BLOCK * (self.Current_block - self.Last_committed)
        _current_staked = float(self.Total_TON_staked)

        # Warn : This is not accurate digit precision
        for oper_name in [name for name in self.Operators.keys()]:
            for user_name in self.Operators[oper_name].delegatees:
                # Add user seigniorage for staking
                user_seigniorage = (self.Operators[oper_name].delegated_balances[user_name] / _current_staked) \
                                    * self.SEIG_PER_BLOCK * (self.Current_block - self.Last_committed)

                self.Total_TON_staked += user_seigniorage  # global
                self.Operators[oper_name].delegated_balances[user_name] += user_seigniorage  # operator

                # Delegatee's TON seig update
                if user_name in self.Operators:
                    self.Operators[user_name].delegated += user_seigniorage
                elif user_name in self.Players:
                    self.Players[user_name].delegated += user_seigniorage
                elif user_name in self.Users:
                    self.Users[user_name].delegated += user_seigniorage

                _seigniorage -= user_seigniorage  # total issued seigniorage
                self.Total_TON_supply += user_seigniorage

        # Update pools
        self.Total_TON_supply += _seigniorage

        _seigniorage = _seigniorage / 2

        self.Prize_pool += _seigniorage * (1 - self.AIRDROP_RATIO)
        self.Airdrop_pool += _seigniorage * self.AIRDROP_RATIO

        # check power prize phase
        self.update_phase()

        self.Staking_ratio = 0 if self.Total_TON_supply == 0 else self.Total_TON_staked / self.Total_TON_supply

    def wrap(self, block=1):
        # TODO update & move current_block
        self.Current_block += block
        # return

    # Generate Participants

    # Helper function for selecting
    def check_name(self, name):
        _party = [False, False, False] # User, Operator, Player
        if name in self.Users.keys():
            _party[0] = True
        if name in self.Operators.keys():
            _party[1] = True
        if name in self.Players.keys():
            _party[2] = True
        return _party[0] | _party[1] | _party[2], _party

    def gen_user(self, name):
        exist, _ = self.check_name(name)
        if exist:
            raise Exception("Exist name, Try another")

        _user = User(name)
        self.Users[name] = _user
        return len(self.Users)

    def faucet(self, name, amount):
        exist, [user, operator, player] = self.check_name(name)
        if not exist:
            raise Exception("No name exist")
        if user:
            _target = self.Users[name]
        if operator:
            _target = self.Operators[name]
        if player:
            _target = self.Players[name]

        _target.add_balance(amount)
        self.Total_TON_supply += amount
        return _target

    def add_user(self, name, amount=0):
        self.gen_user(name)
        self.faucet(name, amount)

    def add_operator(self, name: str):
        exist, [user, operator, player] = self.check_name(name)
        if not exist:
            raise Exception("No name exist")
        if not user:
            raise Exception("Not Exist name at user, Try another")
        if player:
            raise Exception("Only User can be Player")
        if operator:
            raise Exception("Already Exist Operator name")

        _user = self.Users[name]
        self.Operators[name] = Operator(_user)
        self.Users.pop(name)

        self.Total_TON_staked += OMD
        return len(self.Operators)

    def add_player(self, name: str):
        exist, [user, operator, player] = self.check_name(name)
        if not exist:
            raise Exception("No name exist")
        if not user:
            raise Exception("Not Exist name at user, Try another")
        if player:
            raise Exception("Already Exist Player name")
        if operator:
            raise Exception("Already Used name at Operators")

        _user = self.Users[name]
        self.Players[name] = Player(_user)
        self.Users.pop(name)
        return len(self.Players)

    # TON Staking
    def delegate(self, user, oper, amount):
        _, [user_name, _, _] = self.check_name(user)
        _, [_, operator_name, _] = self.check_name(oper)

        if not user_name:
            raise Exception("No user exist")
        if not operator_name:
            raise Exception("No Operator exist")

        _User = self.Users[user]
        _Oper = self.Operators[oper]

        _Oper.delegate(_User, amount)
        self.Total_TON_staked += amount

    def undelegate(self, user, oper, amount):
        _, [user_name, _, _] = self.check_name(user)
        _, [_, operator_name, _] = self.check_name(oper)

        if not user_name:
            raise Exception("No user exist")
        if not operator_name:
            raise Exception("No Operator exist")

        _User = self.Users[user]
        _Oper = self.Operators[oper]

        _Oper.undelegate(_User, amount)
        self.Total_TON_staked -= amount

    # Power Parts

    ## Helper functions

    def _calc_pool_in_phase(self):
        _max = self.MIN_PRIZE_POOL * (2 ** (self.Current_power_phase - 1))
        _min = self.MIN_PRIZE_POOL * (2 ** (self.Current_power_phase - 2))
        return _max, _min

    def update_phase(self) -> (int, int, int):
        # check prize pool if has nothing then
        if self.Prize_pool == 0:
            self.Current_power_phase = 1
            return (0, 0, 0)


        last_phase = int(self.Current_power_phase)
        _phases = list(self.Power_sale.keys())
        _max_prize_pool, _min_prize_pool = self._calc_pool_in_phase()

        if self.Prize_pool > _max_prize_pool:
            while self.Prize_pool > _max_prize_pool:
                # Maximum phase is 10
                if self.Current_power_phase >= _phases[-1]:
                    break

                self.Current_power_phase += 1
                _max_prize_pool, _min_prize_pool = self._calc_pool_in_phase()

        if self.Prize_pool < _min_prize_pool:
            while self.Prize_pool < _min_prize_pool:
                # Minimum phase is 1
                if self.Current_power_phase <= _phases[0]:
                    break

                self.Current_power_phase -= 1
                _max_prize_pool, _min_prize_pool = self._calc_pool_in_phase()

        # update power_sale
        new_phase = self.Current_power_phase

        if last_phase > new_phase:
            # Only One case, Winner Came out!
            for phase in self.Power_sale.keys():
                self.Power_sale[phase]["SOLD"] = 0
                self.Power_sale[phase]["OPEN"] = False

            for phase in range(1, new_phase):
                self.Power_sale[phase]["OPEN"] = True
                self.Power_sale[phase]["ISSUUED"] = self.POWER_PER_PHASE

            return new_phase * self.POWER_PER_PHASE, last_phase, new_phase

        if last_phase < new_phase:
            # Prize Pool size up, Open New Power for sale
            if last_phase == 0:
                last_phase = 1
                self.Power_sale[last_phase]["OPEN"] = True
                self.Power_sale[last_phase]["AVAILABLE"] = self.POWER_PER_PHASE

            for phase in range(last_phase, new_phase):
                self.Power_sale[phase]["OPEN"] = True
                self.Power_sale[phase]["AVAILABLE"] = self.POWER_PER_PHASE
        else:
            # same phase no power issue
            pass

        _total_sold_powers = 0
        for phase in self.Power_sale.keys():
            _sold_powers = self.Power_sale[phase]['SOLD']
            if self.Power_sale[phase]['AVAILABLE'] == _sold_powers:
                self.Power_sale[phase]['OPEN'] = False

            _total_sold_powers += _sold_powers
        return new_phase * self.POWER_PER_PHASE - _total_sold_powers, \
               last_phase, new_phase

    def check_stock_powers(self, amount):
        if self.Prize_pool == 0:
            return {0: 0}

        # stock power in current phase
        _, _, _ = self.update_phase()

        _sale_powers = {}

        for phase in self.Power_sale.keys():
            if self.Power_sale[phase]["AVAILABLE"] >= amount:
                _sale_powers.update({self.Power_sale[phase]["PRICE"]: self.Power_sale[phase]["AVAILABLE"]})
                return _sale_powers
            else:  # stock of power in phase less than amount
                _sale_powers.update({self.Power_sale[phase]["PRICE"]: self.Power_sale[phase]["AVAILABLE"]})
                amount -= self.Power_sale[phase]["AVAILABLE"]

            if amount <= 0:
                return _sale_powers

        return _sale_powers

    def buy_power(self, name, amount):
        exist, [user, operator, player] = self.check_name(name)
        if not exist:
            raise Exception("No name exist")

        # check balance & power stock
        _target = User(name, 0)

        if user:
            _target = self.Users[name]
        if player:
            _target = self.Players[name]
        if operator:
            raise Exception("Not allowed buy power by operator")  # TODO: check details

        # copy power_sale status then return if can
        self._update_ton()
        stock_powers, last, new = self.update_phase()  # before update
        if stock_powers == 0:
            raise Exception("No stock of power for sale")

        power_sale = self.Power_sale.copy()
        avail_balance = float(_target.balance)

        _amount = int(amount)
        if stock_powers >= _amount:
            # enough to buy -> calc enough balance
            for phase in power_sale.keys():
                # choose low volume one
                _low = min(power_sale[phase]["AVAILABLE"], _amount)
                if _low == 0:
                    continue  # skip calc this phase
                elif _low < 0:
                    raise Exception("Over sold, Over bought!")

                avail_balance -= _low * power_sale[phase]["PRICE"]
                if avail_balance < 0:
                    raise Exception("Not enough TON to buy Power")

                # Update balances
                power_sale[phase]["AVAILABLE"] -= _low
                power_sale[phase]["SOLD"] += _low
                _amount -= _low

                if power_sale[phase]["AVAILABLE"] == 0:
                    power_sale[phase]["OPEN"] = False
        else:
            raise Exception("Not enough stock of power")

        # calc complete & passed, update state

        # user bought then be player automatically
        if user:
            self.add_player(name)

        self.Players[name].balance = avail_balance
        self.Players[name].power_bought += amount
        self.Players[name].power_available += amount

        self.Power_sale = power_sale
        self.Total_sold_powers += amount

        # Paid TON distribution
        # Prize Pool
        _paid_ton = _target.balance - avail_balance
        self.Prize_pool += _paid_ton * self.DIST_BUY_POWER[0]

        # Player
        for p in self.Players.keys():
            # dist by power
            _effective_powers = self.Players[p].power_bought - self.Players[p].power_played
            if self.Total_sold_powers == 0:
                _ratio_power_of_total = 1
            else:
                _ratio_power_of_total = _effective_powers / self.Total_sold_powers
            self.Players[p].balance += _ratio_power_of_total * _paid_ton * self.DIST_BUY_POWER[1]

            # dist by Staked TON
            _ratio_staked = self.Players[p].delegated / self.Total_TON_staked
            self.Players[p].balance += _ratio_staked * _paid_ton * self.DIST_BUY_POWER[1]

        # User
        for u in self.Users.keys():
            _ratio_staked = self.Users[u].delegated / self.Total_TON_staked
            self.Users[u].balance += _ratio_staked * _paid_ton * self.DIST_BUY_POWER[2]

    def power_up(self, player_name: str, operator_name: str, amount):
        _, [_, _, player] = self.check_name(player_name)
        _, [_, operator, _] = self.check_name(operator_name)

        if not player:
            raise Exception("No Player exist")
        if not operator:
            raise Exception("No Operator exist")

        _Player = self.Players[player_name]
        _Operator = self.Operators[operator_name]

        _Player.power_up(_Operator, amount)
        self.Total_supported_powers += amount

    def power_down(self, player_name: str, operator_name: str, amount):
        _, [_, _, player] = self.check_name(player_name)
        _, [_, operator, _] = self.check_name(operator_name)

        if not player:
            raise Exception("No Player exist")
        if not operator:
            raise Exception("No Operator exist")

        _Player = self.Players[player_name]
        _Operator = self.Operators[operator_name]

        _Player.power_down(_Operator, amount)
        self.Total_supported_powers -= amount

    def _prize_dist(self, name):
        # call by `play_power` or `commit`
        # calc prize
        _prize_winner = self.Prize_pool * self.DIST_PRIZE[0]
        _next_prize_pool = self.Prize_pool * self.DIST_PRIZE[1]
        _prize_power = self.Prize_pool * self.DIST_PRIZE[2]
        _prize_ton = self.Prize_pool * self.DIST_PRIZE[3]

        _, [user, operator, player] = self.check_name(name)

        if operator:
            self.Operators[name].add_balance(_prize_winner)
        elif player:
            self.Players[name].add_balance(_prize_winner)
        self.Prize_pool = _next_prize_pool

        for p in self.Players.keys():
            # dist by power
            _effective_powers = self.Players[p].power_bought - self.Players[p].power_played

            if self.Total_sold_powers == 0:
                _powers = 1
            else:
                _powers = self.Total_sold_powers

            _ratio_power_of_total = _effective_powers / _powers
            self.Players[p].add_balance(_ratio_power_of_total * _prize_power)

            # dist by Staked TON
            _ratio_staked = self.Players[p].delegated / self.Total_TON_staked
            self.Players[p].add_balance(_ratio_staked * _prize_ton)

        # User
        for u in self.Users.keys():
            _ratio_staked = self.Users[u].delegated / self.Total_TON_staked
            self.Users[u].add_balance(_ratio_staked * _prize_ton)

        # TODO : return result for `winning history`

    def _airdrop_dist(self, name):
        # only called by `commit`
        _prize_winner = self.Airdrop_pool * self.DIST_AIRDROP[0]
        self.Airdrop_pool = self.Airdrop_pool * self.DIST_AIRDROP[1]

        self.Operators[name].add_balance(_prize_winner)
        # TODO : return result for `winning history`

    def play_power(self, name, amount):
        _, [user, operator, player] = self.check_name(name)
        if user:
            raise Exception("User does not have power to use")
        if operator:
            raise Exception("Not allowed buy power by operator")  # TODO: check details
        if not player:
            raise Exception(f"`%s` is not Player.", name)

        if random() < self.POWER_WIN_CHANCE * amount:
            self._prize_dist(name)
            print("Won! {} prize".format(name))

    def commit(self, name):
        # prize chance
        _, [user, operator, player] = self.check_name(name)
        if user or player:
            raise Exception("Only Operator can commit")
        self._update_ton()
        self.Last_committed = self.Current_block

        # TODO : check power supported winning chance
        _power_factor = 1 + self.Operators[name].supported_power

        _result = [False, False]

        #  print("modified winning chance : ", self.POWER_WIN_CHANCE * _power_factor)
        if random() < self.WINNING_CHANCE * _power_factor:
            self._prize_dist(name)
            print("Won! {} prize!".format(name))
            _result[0] = True

        # airdrop chance
        if random() < self.AIRDROP_CHANCE:
            self._airdrop_dist(name)
            print("Won! {} airdrop!".format(name))
            _result[1] = True

        return _result[0], _result[1]
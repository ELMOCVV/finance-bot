from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    waiting_name = State()


class CreateAccount(StatesGroup):
    waiting_name = State()
    waiting_currency = State()
    waiting_balance = State()


class EditAccount(StatesGroup):
    waiting_name = State()
    waiting_balance = State()


class CreateTransfer(StatesGroup):
    selecting_from = State()
    selecting_to = State()
    waiting_amount = State()
    confirming = State()


class AddTransaction(StatesGroup):
    waiting_text = State()
    waiting_income_text = State()


class EditTransaction(StatesGroup):
    editing_amount = State()
    editing_description = State()
    selecting_category = State()
    creating_category_name = State()


class AddGoal(StatesGroup):
    waiting_name = State()
    waiting_amount = State()
    waiting_deadline = State()


class AddDebt(StatesGroup):
    waiting_name = State()
    waiting_total = State()
    waiting_monthly = State()
    waiting_rate = State()
    waiting_date = State()


class CreateBudget(StatesGroup):
    waiting_category = State()
    waiting_amount = State()
    waiting_month = State()


class CreateSubscription(StatesGroup):
    waiting_name = State()
    waiting_amount = State()
    waiting_currency = State()
    waiting_period = State()
    waiting_day = State()
    waiting_month = State()   # тільки для yearly
    waiting_account = State()
    waiting_hour = State()


class EditSubscription(StatesGroup):
    waiting_name = State()
    waiting_amount = State()
    waiting_hour = State()


class AddCategory(StatesGroup):
    waiting_name = State()
    waiting_type = State()


class EditCategory(StatesGroup):
    waiting_name = State()

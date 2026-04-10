from aiogram.fsm.state import State, StatesGroup


class UserFlowState(StatesGroup):
    waiting_chatgpt_gmail = State()
    waiting_trial_gmail = State()
    waiting_custom_request = State()
    waiting_payment_proof = State()


class AdminState(StatesGroup):
    waiting_product_create = State()
    waiting_product_translation = State()
    waiting_product_price = State()
    waiting_product_sort = State()
    waiting_product_photo = State()
    waiting_product_currency = State()
    waiting_text_translation = State()
    waiting_button_create = State()
    waiting_button_translation = State()
    waiting_button_action = State()
    waiting_button_row = State()
    waiting_button_sort = State()
    waiting_payment_create = State()
    waiting_payment_credentials = State()
    waiting_payment_translation = State()
    waiting_payment_sort = State()
    waiting_payment_photo = State()
    waiting_stock_single = State()
    waiting_stock_bulk = State()

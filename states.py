from aiogram.fsm.state import State, StatesGroup


class UserFlowState(StatesGroup):
    waiting_multi_quantity = State()
    waiting_trial_name = State()
    waiting_trial_phone = State()
    waiting_chatgpt_gmail = State()
    waiting_chatgpt_gmail_choice = State()
    waiting_trial_gmail = State()
    waiting_promo_code = State()
    waiting_custom_request = State()
    waiting_payment_proof = State()
    waiting_topup_custom_amount = State()
    waiting_topup_receipt = State()


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
    waiting_inventory_item = State()
    waiting_order_delivery = State()
    waiting_user_lookup = State()
    waiting_balance_adjustment = State()
    waiting_user_message = State()


class AdminBroadcastState(StatesGroup):
    waiting_text = State()
    waiting_photo = State()
    waiting_caption = State()
    waiting_button_text = State()
    waiting_button_url = State()

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Iterable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


EMOJI_ID_CHATGPT = "5359726582447487916"
EMOJI_ID_CAPCUT = "5364339557712020484"
EMOJI_ID_GROK = "5330337435500951363"
EMOJI_ID_ADOBE = "5357394595594388140"
EMOJI_ID_TELEGRAM = "5424972470023104089"

PAYMENT_CODE_ORDER = ("click", "card", "usdt_trc20")

LEGACY_SCREEN_FLOW = {
    "subscriptions": ("open_chatgpt", "open_capcut", "open_grok", "open_other"),
    "chatgpt_menu": ("chatgpt_1m", "chatgpt_trial", "multi_chatgpt", "support", "menu", "subscriptions"),
    "capcut_menu": ("capcut_1m", "capcut_locked", "multi_capcut", "support", "menu", "subscriptions"),
    "other_menu": ("other_adobe", "other_games", "other_telegram", "other_yandex", "other_music", "other_custom_own"),
    "chatgpt_details": ("buy_chatgpt_1m", "open_chatgpt", "menu"),
    "capcut_details": ("buy_capcut_1m", "open_capcut", "menu"),
    "chatgpt_checkout": ("chatgpt_month_use_saved_gmail", "chatgpt_month_use_other_gmail", "chatgpt:check"),
    "trial_checkout": ("trial:check",),
    "invoice": ("order:pay", "order:promo", "order:cancel", "menu"),
}

PRODUCT_TITLES = {
    "ru": {
        "chatgpt_plus_month": "ChatGPT PLUS (1 месяц)",
        "capcut_pro_month": "CapCut Pro (1 месяц)",
        "chatgpt_trial_3d": "ChatGPT PLUS (3 дня)",
    },
    "uz": {
        "chatgpt_plus_month": "ChatGPT PLUS (1 oy)",
        "capcut_pro_month": "CapCut Pro (1 oy)",
        "chatgpt_trial_3d": "ChatGPT PLUS (3 kun)",
    },
    "en": {
        "chatgpt_plus_month": "ChatGPT PLUS (1 month)",
        "capcut_pro_month": "CapCut Pro (1 month)",
        "chatgpt_trial_3d": "ChatGPT PLUS (3 days)",
    },
}

PRICE_HINTS = {
    "ru": {
        "chatgpt_plus_month": " (~750 ₽)",
        "capcut_pro_month": " (~350 ₽)",
    },
    "uz": {
        "subscriptions_title": "Xizmatni tanlang",
        "grok_unavailable": "Hozircha mavjud emas.",
        "capcut_locked": "Bu tarif hozircha mavjud emas.",
        "custom_text": "Yana qaysi obunani arzonroq olishni xohlaysiz?",
        "custom_sent": "✅ So‘rovingiz qabul qilindi.\n\nAdministrator uni ko‘radi va kerak bo‘lsa siz bilan bog‘lanadi.",
        "multi_quantity": "Nechta akkaunt kerak?",
        "multi_done": "✅ So‘rovingiz qabul qilindi.\n\nAdministrator miqdor bo‘yicha ma'lumotni oldi va tez orada bog‘lanadi.",
        "trial_name": "Ismingizni kiriting.",
        "trial_phone": "Telefon raqamingizni kiriting.",
        "trial_gmail": "ChatGPT uchun Gmail kiriting.",
        "invalid_gmail": "Gmailni name@gmail.com formatida to‘g‘ri kiriting.",
        "trial_subscribe": "Kanalga obuna bo‘ling va tekshirish tugmasini bosing.",
        "trial_not_subscribed": "Siz hali kanalga obuna bo‘lmadingiz.",
        "trial_already_used": "Siz sinov obunasidan allaqachon foydalangansiz.",
        "trial_created": "Buyurtma: {order_number}\nMahsulot: ChatGPT PLUS (3 kun)\nNarx: BEPUL\nHolat: buyurtma ko‘rib chiqilmoqda",
        "chatgpt_month_gmail_choice": "Siz ilgari ChatGPT uchun ishlatgan Gmail topildi:\n\n<b>{gmail}</b>\n\nObunani shu Gmailga rasmiylashtiraylikmi yoki boshqasini kiritasizmi?",
        "chatgpt_month_gmail": "ChatGPT Plus ulash uchun Gmail kiriting.",
        "chatgpt_month_selected_gmail": "Obuna quyidagi Gmail uchun rasmiylashtiriladi:\n<b>{gmail}</b>\n\nBuyurtma yaratish uchun kanalga obuna bo‘ling va tekshirish tugmasini bosing.",
        "chatgpt_month_subscribe": "Buyurtma yaratish uchun kanalga obuna bo‘ling va tekshirish tugmasini bosing.",
        "chatgpt_month_not_subscribed": "Siz hali kanalga obuna bo‘lmadingiz.",
        "stock_empty": "Hozirda mahsulot tugagan.\n\nIltimos, keyinroq urinib ko‘ring yoki yordamga yozing.",
        "chatgpt_menu_text": "<tg-emoji emoji-id='5359726582447487916'>🤖</tg-emoji> ChatGPT Plus/Pro\n\nTarifni tanlang 👇",
        "capcut_menu_text": "<tg-emoji emoji-id='5364339557712020484'>🎬</tg-emoji> CapCut Pro\n\nTarifni tanlang 👇",
        "chatgpt_1m_text": "💠 ChatGPT PLUS (1 oy)\n💰 Narx: {price_uzs} so‘m\n────────────────\n⚙️ Ulanish tartibi\n1. Gmail'ingizga maxsus PLUS taklif havolasini yuboramiz\n2. Havolaga o‘tib, o‘zingizning akkauntingizga kirasiz\n3. ChatGPT PLUS avtomatik faollashadi\n⏱ Amal qilish muddati — faollashtirilganidan keyin 25-30 kun\n\n🔐 Xavfsizlik\n— Parol berilmaydi\n— Tizimga faqat siz o‘zingiz kirasiz\n— Faqat rasmiy ulash usullaridan foydalaniladi\n\n✅ Afzalliklar\n✔️ Tez ulash\n✔️ Shaffof shartlar\n✔️ Xariddan keyin ham yordam",
        "capcut_1m_text": "💠 Mahsulot: CapCut Pro (1 oy)\n💰 Narxi: {price_uzs} so‘m (~350 ₽)\n—————————————————-\n⚙️ Qanday ulanadi\n 1. Buyurtmadan so‘ng sizga tayyor akkaunt yuboriladi\n 2. Siz ushbu ma’lumotlarni (login, parol) nusxalab CapCut ga kiritasiz\n 3. Agar sizda akkaunt bo‘lsa, avval undan chiqib, &lt;&gt; usuli bilan qayta kiring\n⏱ Faol muddati — faollashtirilgan vaqtdan boshlab 30 kun\n\n🔐 Xavfsizlik\n— Uzilishlarsiz\n— Kirish faqat siz tomonidan amalga oshiriladi\n— Rasmiy ulanish usullari ishlatiladi\n\n— Ulanishning barcha bosqichlarida yordam 💬\n— MDH va boshqa davlatlar foydalanuvchilari uchun mavjud\n⸻\n✅ Afzalliklar\n✔️ Tez ulanish\n✔️ Shaffof shartlar\n✔️ Xariddan keyingi yordam",
        "invoice_title": "Buyurtma: {order_number}\nMahsulot: {product_name}\nNarx: {price_uzs} so‘m{usd_part}\n\nHisob 30 daqiqa amal qiladi.\nHolat to‘lovdan keyin yangilanadi.",
        "pay_click_text": "Buyurtma: {order_number}\nMahsulot: {product_name}\nNarx: {price_uzs} so‘m\n\nTo‘lov uchun:\n1. Click ni oching\n2. QR kodni skaner qiling\n3. {price_uzs} so‘m summani kiriting\n4. To‘lovni tasdiqlang\n\nTo‘lovdan keyin chekni shu botga yuboring.",
        "pay_card_text": "Buyurtma: {order_number}\nMahsulot: {product_name}\nNarx: {price_uzs} so‘m\n\nRekvizitlar:\n{card_number}\n\nSummani kiriting: {price_uzs} so‘m\n\nTo‘lovdan keyin chekni shu botga yuboring.",
        "pay_crypto_text": "Buyurtma: {order_number}\nMahsulot: {product_name}\nNarx: {price_usd}$\n\nUSDT (TRC20):\n{wallet}\n\nTo‘lovdan keyin chekni shu botga yuboring.",
        "payment_check_saved": "✅ Chek olindi.\n\nUni administratorga tekshirish uchun yubordik. Tasdiqdan keyin holat yangilanadi.",
        "order_cancelled": "Buyurtma {order_number}\nHolat: bekor qilindi\nXabar: buyurtma bekor qilindi",
        "btn_back": "◀ Orqaga",
        "btn_menu": "🏠 Menyu",
        "btn_chatgpt": "ChatGPT Plus/Pro",
        "btn_capcut": "CapCut Pro",
        "btn_grok": "Super Grok",
        "btn_other": "Boshqa",
        "btn_buy": "Rasmiylashtirish",
        "btn_use_this_gmail": "Shu Gmail",
        "btn_use_other_gmail": "Boshqa",
        "btn_question": "Savolim bor",
        "btn_several": "Bir nechta kerak",
        "btn_trial": "3 kun bepul sinab ko‘rish",
        "btn_promocode": "Promokod bor",
        "btn_check_sub": "Obunani tekshirish",
        "btn_click": "Click",
        "btn_card": "Humo/Visa",
        "btn_crypto": "USDT",
        "btn_custom_own": "O‘zimnikini xohlayman",
        "btn_subscribe": "Obuna bo‘lish",
        "btn_cancel": "Bekor qilish",
        "other_games": "O‘yin qiymatlari",
        "other_music": "Musiqa",
        "multi_chatgpt_service": "ChatGPT Plus",
        "multi_capcut_service": "CapCut Pro",
    },
    "en": {
        "subscriptions_title": "Choose a service",
        "grok_unavailable": "Currently unavailable.",
        "capcut_locked": "This tariff is currently unavailable.",
        "custom_text": "Which other subscription would you like to get cheaper?",
        "custom_sent": "✅ Your request has been accepted.\n\nThe admin will review it and contact you if needed.",
        "multi_quantity": "How many accounts do you need?",
        "multi_done": "✅ Your request has been accepted.\n\nThe admin received the quantity and will contact you soon.",
        "trial_name": "Enter your name.",
        "trial_phone": "Enter your phone number.",
        "trial_gmail": "Enter your Gmail for ChatGPT activation.",
        "invalid_gmail": "Enter a valid Gmail in the format name@gmail.com.",
        "trial_subscribe": "Subscribe to the channel and press the verification button.",
        "trial_not_subscribed": "You have not subscribed to the channel yet.",
        "trial_already_used": "You have already used the trial subscription.",
        "trial_created": "Order: {order_number}\nProduct: ChatGPT PLUS (3 days)\nPrice: FREE\nStatus: order is under review",
        "chatgpt_month_gmail_choice": "We found a Gmail you already used for ChatGPT:\n\n<b>{gmail}</b>\n\nDo you want to use this Gmail or enter another one?",
        "chatgpt_month_gmail": "Enter your Gmail for ChatGPT Plus activation.",
        "chatgpt_month_selected_gmail": "The subscription will be set up for this Gmail:\n<b>{gmail}</b>\n\nSubscribe to the channel and press the verification button so we can create your order.",
        "chatgpt_month_subscribe": "Subscribe to the channel and press the verification button so we can create your order.",
        "chatgpt_month_not_subscribed": "You have not subscribed to the channel yet.",
        "stock_empty": "This item is currently out of stock.\n\nPlease try again later or contact support.",
        "chatgpt_menu_text": "<tg-emoji emoji-id='5359726582447487916'>🤖</tg-emoji> ChatGPT Plus/Pro\n\nChoose a tariff below 👇",
        "capcut_menu_text": "<tg-emoji emoji-id='5364339557712020484'>🎬</tg-emoji> CapCut Pro\n\nChoose a tariff below 👇",
        "chatgpt_1m_text": "💠 ChatGPT PLUS (1 month)\n💰 Price: {price_uzs} UZS\n────────────────\n⚙️ How activation works\n1. We send a special PLUS invitation link to your Gmail\n2. You open the link and sign in to your own account\n3. ChatGPT PLUS activates automatically\n⏱ Duration: 25-30 days after activation\n\n🔐 Security\n— No password transfer\n— Only you sign in to the account\n— Official activation methods only\n\n✅ Benefits\n✔️ Fast activation\n✔️ Clear terms\n✔️ Support after purchase",
        "capcut_1m_text": "💠 Product: CapCut Pro (1 month)\n💰 Price: {price_uzs} UZS (~350 ₽)\n—————————————————-\n⚙️ How connection works\n 1. We send you a ready account created after the order\n 2. You copy these details (login, password) and paste them into CapCut\n 3. If you already have an account, first log out and then sign in using\n&lt;&gt;\n⏱ Duration — 30 days from activation\n\n🔐 Security\n— No crashes\n— Only you can access it\n— Official connection methods are used\n\n— Support at every connection step 💬\n— Available for users from CIS and other countries\n⸻\n✅ Advantages\n✔️ Fast connection\n✔️ Transparent terms\n✔️ Support after purchase",
        "invoice_title": "Order: {order_number}\nProduct: {product_name}\nPrice: {price_uzs} UZS{usd_part}\n\nThe invoice is valid for 30 minutes.\nStatus will update after payment.",
        "pay_click_text": "Order: {order_number}\nProduct: {product_name}\nPrice: {price_uzs} UZS\n\nTo pay:\n1. Open Click\n2. Scan the QR code\n3. Enter the amount {price_uzs} UZS\n4. Confirm the payment\n\nAfter payment, send the receipt to this bot.",
        "pay_card_text": "Order: {order_number}\nProduct: {product_name}\nPrice: {price_uzs} UZS\n\nCard details:\n{card_number}\n\nEnter the amount: {price_uzs} UZS\n\nAfter payment, send the receipt to this bot.",
        "pay_crypto_text": "Order: {order_number}\nProduct: {product_name}\nPrice: {price_usd}$\n\nUSDT (TRC20):\n{wallet}\n\nAfter payment, send the receipt to this bot.",
        "payment_check_saved": "✅ Receipt received.\n\nWe sent it to the admin for review. The status will update after confirmation.",
        "order_cancelled": "Order {order_number}\nStatus: cancelled\nMessage: order cancelled",
        "btn_back": "◀ Back",
        "btn_menu": "🏠 Menu",
        "btn_chatgpt": "ChatGPT Plus/Pro",
        "btn_capcut": "CapCut Pro",
        "btn_grok": "Super Grok",
        "btn_other": "Other",
        "btn_buy": "Proceed",
        "btn_use_this_gmail": "Use this",
        "btn_use_other_gmail": "Other",
        "btn_question": "I have a question",
        "btn_several": "I need several",
        "btn_trial": "Try 3 days for free",
        "btn_promocode": "I have a promo code",
        "btn_check_sub": "Check subscription",
        "btn_click": "Click",
        "btn_card": "Humo/Visa",
        "btn_crypto": "USDT",
        "btn_custom_own": "I want my own",
        "btn_subscribe": "Subscribe",
        "btn_cancel": "Cancel",
        "other_games": "Game values",
        "other_music": "Music",
        "multi_chatgpt_service": "ChatGPT Plus",
        "multi_capcut_service": "CapCut Pro",
    },
}

CRYPTO_PRICES = {
    "chatgpt_plus_month": "8.5",
    "capcut_pro_month": "3.49",
}

TEXTS = {
    "ru": {
        "subscriptions_title": "Выберите сервис",
        "grok_unavailable": "В данный момент недоступно.",
        "capcut_locked": "Этот тариф пока недоступен.",
        "custom_text": "Какую подписку вы хотели бы ещё получить дешевле?",
        "custom_sent": "✅ Ваша заявка принята.\n\nАдминистратор увидит ваш запрос и свяжется с вами при необходимости.",
        "multi_quantity": "Сколько аккаунтов вы хотите?",
        "multi_done": "✅ Ваша заявка принята.\n\nАдминистратор получил информацию о количестве и свяжется с вами.",
        "trial_name": "Введите имя.",
        "trial_phone": "Введите номер телефона.",
        "trial_gmail": "Введите Gmail для подключения ChatGPT.",
        "invalid_gmail": "Введите корректный Gmail в формате name@gmail.com.",
        "trial_subscribe": "Подпишитесь на канал и нажмите кнопку проверки.",
        "trial_not_subscribed": "Вы ещё не подписались на канал.",
        "trial_already_used": "Вы уже использовали пробную подписку.",
        "trial_created": (
            "Заказ: {order_number}\n"
            "Товар: ChatGPT PLUS (3 дня)\n"
            "Стоимость: БЕСПЛАТНО\n"
            "Статус: заказ в обработке"
        ),
        "chatgpt_month_gmail_choice": (
            "Мы нашли Gmail, который вы уже использовали для ChatGPT:\n\n"
            "<b>{gmail}</b>\n\n"
            "Оформить подписку на этот Gmail или указать другой?"
        ),
        "chatgpt_month_gmail": "Введите Gmail, на который нужно подключить ChatGPT Plus.",
        "chatgpt_month_selected_gmail": (
            "Оформление будет выполнено на Gmail:\n"
            "<b>{gmail}</b>\n\n"
            "Подпишитесь на канал и нажмите кнопку проверки, чтобы мы создали заказ."
        ),
        "chatgpt_month_subscribe": "Подпишитесь на канал и нажмите кнопку проверки, чтобы мы создали заказ.",
        "chatgpt_month_not_subscribed": "Вы ещё не подписались на канал.",
        "stock_empty": (
            "В данный момент товар закончился.\n\n"
            "Пожалуйста, попробуйте позже или свяжитесь с поддержкой."
        ),
        "chatgpt_menu_text": "<tg-emoji emoji-id='5359726582447487916'>🤖</tg-emoji> ChatGPT Plus/Pro\n\nВыберите тариф ниже 👇",
        "capcut_menu_text": "<tg-emoji emoji-id='5364339557712020484'>🎬</tg-emoji> CapCut Pro\n\nВыберите тариф ниже 👇",
        "chatgpt_1m_text": (
            "💠 ChatGPT PLUS (1 месяц)\n"
            "💰 Цена: {price_uzs} сум (~750 ₽)\n"
            "────────────────\n"
            "⚙️ Как проходит подключение\n"
            "1. Мы отправляем вам специальную ссылку с приглашением на PLUS в вашу почту\n"
            "2. Вы переходите по ссылке и авторизуетесь в своём аккаунте\n"
            "3. Подписка ChatGPT PLUS активируется автоматически\n"
            "⏱ Срок действия — 25-30 дней с момента активации\n\n"
            "🔐 Безопасность\n"
            "— Без передачи паролей\n"
            "— Вход осуществляется только вами\n"
            "— Используются официальные методы подключения\n\n"
            "— Поддержка на всех этапах подключения 💬\n"
            "— Доступно для пользователей из СНГ и других стран\n"
            "⸻\n"
            "✅ Преимущества\n"
            "✔️ Быстрое подключение\n"
            "✔️ Прозрачные условия\n"
            "✔️ Сопровождение после покупки"
        ),
        "capcut_1m_text": (
            "💠 Товар: CapCut Pro (1 месяц)\n"
            "💰 Стоимость: {price_uzs} сум (~350 ₽)\n"
            "—————————————————-\n"
            "⚙️ Как проходит подключение\n"
            " 1. Мы отправляем вам готовый аккаунт который создается после заказа\n"
            " 2. Вы скопируете эти данные ввиде(login,parol) и вставляете capcut\n"
            " 3. если у вас есть аккаунт то сначала вам нужно выйти и зайти способом\n"
            "&lt;&lt;войти через почту&gt;&gt;\n"
            "⏱ Срок действия — 30 дней с момента активации\n\n"
            "🔐 Безопасность\n"
            "— Без вылетов\n"
            "— Вход осуществляется только вами\n"
            "— Используются официальные методы подключения\n\n"
            "— Поддержка на всех этапах подключения 💬\n"
            "— Доступно для пользователей из СНГ и других стран\n"
            "⸻\n"
            "✅ Преимущества\n"
            "✔️ Быстрое подключение\n"
            "✔️ Прозрачные условия\n"
            "✔️ Сопровождение после покупки"
        ),
        "invoice_title": (
            "Заказ: {order_number}\n"
            "Товар: {product_name}\n"
            "Стоимость: {price_uzs} сум{usd_part}\n\n"
            "Счёт действителен 30 минут.\n"
            "Статус обновится после оплаты."
        ),
        "pay_click_text": (
            "Заказ: {order_number}\n"
            "Товар: {product_name}\n"
            "Стоимость: {price_uzs} сум\n\n"
            "Для оплаты:\n"
            "1. Откройте Click\n"
            "2. Отсканируйте Qrcod\n"
            "3. Ведите сумму {price_uzs} сум\n"
            "4. Подтвердите оплату\n\n"
            "После оплаты отправьте чек в этот бот."
        ),
        "pay_card_text": (
            "Заказ: {order_number}\n"
            "Товар: {product_name}\n"
            "Стоимость: {price_uzs} сум\n\n"
            "Реквизиты:\n"
            "{card_number}\n\n"
            "Введите сумму: {price_uzs} сум\n\n"
            "После оплаты отправьте чек в этот бот."
        ),
        "pay_crypto_text": (
            "Заказ: {order_number}\n"
            "Товар: {product_name}\n"
            "Стоимость: {price_usd}$\n\n"
            "USDT (TRC20):\n"
            "{wallet}\n\n"
            "После оплаты отправьте чек в этот бот."
        ),
        "payment_check_saved": (
            "✅ Чек получен.\n\n"
            "Мы отправили его администратору на проверку. После подтверждения статус заказа обновится."
        ),
        "order_cancelled": (
            "Заказ {order_number}\n"
            "Статус: отменён\n"
            "Сообщение: заказ отменён"
        ),
        "btn_back": "◀ Назад",
        "btn_menu": "🏠 Меню",
        "btn_chatgpt": "ChatGPT Plus/Pro",
        "btn_capcut": "CapCut Pro",
        "btn_grok": "Super Grok",
        "btn_other": "Другое",
        "btn_buy": "Оформить",
        "btn_use_this_gmail": "На этот",
        "btn_use_other_gmail": "Другой",
        "btn_question": "У меня есть вопрос",
        "btn_several": "Хочу несколько",
        "btn_trial": "Попробовать 3 дня бесплатно",
        "btn_promocode": "Есть промокод",
        "btn_check_sub": "Проверить подписку",
        "btn_click": "Click",
        "btn_card": "Humo/Visa",
        "btn_crypto": "USDT",
        "btn_custom_own": "Хочу своё",
        "btn_subscribe": "Подписаться",
        "btn_cancel": "Отменить",
        "other_games": "Игровые ценности",
        "other_music": "Музыка",
        "multi_chatgpt_service": "ChatGPT Plus",
        "multi_capcut_service": "CapCut Pro",
    },
    "uz": {},
    "en": {
        "subscriptions_title": "Choose a service",
        "grok_unavailable": "Currently unavailable.",
        "capcut_locked": "This tariff is currently unavailable.",
        "custom_text": "Which other subscription would you like to get cheaper?",
        "custom_sent": "✅ Your request has been accepted.\n\nThe admin will review it and contact you if needed.",
        "multi_quantity": "How many accounts do you need?",
        "multi_done": "✅ Your request has been accepted.\n\nThe admin received the quantity and will contact you soon.",
        "trial_name": "Enter your name.",
        "trial_phone": "Enter your phone number.",
        "trial_gmail": "Enter your Gmail for ChatGPT activation.",
        "invalid_gmail": "Enter a valid Gmail in the format name@gmail.com.",
        "trial_subscribe": "Subscribe to the channel and press the verification button.",
        "trial_not_subscribed": "You have not subscribed to the channel yet.",
        "trial_already_used": "You have already used the trial subscription.",
        "trial_created": "Order: {order_number}\nProduct: ChatGPT PLUS (3 days)\nPrice: FREE\nStatus: order is under review",
        "chatgpt_month_gmail_choice": "We found a Gmail you already used for ChatGPT:\n\n<b>{gmail}</b>\n\nDo you want to use this Gmail or enter another one?",
        "chatgpt_month_gmail": "Enter your Gmail for ChatGPT Plus activation.",
        "chatgpt_month_selected_gmail": "The subscription will be set up for this Gmail:\n<b>{gmail}</b>\n\nSubscribe to the channel and press the verification button so we can create your order.",
        "chatgpt_month_subscribe": "Subscribe to the channel and press the verification button so we can create your order.",
        "chatgpt_month_not_subscribed": "You have not subscribed to the channel yet.",
        "stock_empty": "This item is currently out of stock.\n\nPlease try again later or contact support.",
        "chatgpt_menu_text": "<tg-emoji emoji-id='5359726582447487916'>🤖</tg-emoji> ChatGPT Plus/Pro\n\nChoose a tariff below 👇",
        "capcut_menu_text": "<tg-emoji emoji-id='5364339557712020484'>🎬</tg-emoji> CapCut Pro\n\nChoose a tariff below 👇",
        "chatgpt_1m_text": "💠 ChatGPT PLUS (1 month)\n💰 Price: {price_uzs} UZS\n────────────────\n⚙️ How activation works\n1. We send a special PLUS invitation link to your Gmail\n2. You open the link and sign in to your own account\n3. ChatGPT PLUS activates automatically\n⏱ Duration: 25-30 days after activation\n\n🔐 Security\n— No password transfer\n— Only you sign in to the account\n— Official activation methods only\n\n✅ Benefits\n✔️ Fast activation\n✔️ Clear terms\n✔️ Support after purchase",
        "capcut_1m_text": "💠 Product: CapCut Pro (1 month)\n💰 Price: {price_uzs} UZS (~350 ₽)\n—————————————————-\n⚙️ How connection works\n 1. We send you a ready account created after the order\n 2. You copy these details (login, password) and paste them into CapCut\n 3. If you already have an account, first log out and then sign in using\n&lt;&gt;\n⏱ Duration — 30 days from activation\n\n🔐 Security\n— No crashes\n— Only you can access it\n— Official connection methods are used\n\n— Support at every connection step 💬\n— Available for users from CIS and other countries\n⸻\n✅ Advantages\n✔️ Fast connection\n✔️ Transparent terms\n✔️ Support after purchase",
        "invoice_title": "Order: {order_number}\nProduct: {product_name}\nPrice: {price_uzs} UZS{usd_part}\n\nThe invoice is valid for 30 minutes.\nStatus will update after payment.",
        "pay_click_text": "Order: {order_number}\nProduct: {product_name}\nPrice: {price_uzs} UZS\n\nTo pay:\n1. Open Click\n2. Scan the QR code\n3. Enter the amount {price_uzs} UZS\n4. Confirm the payment\n\nAfter payment, send the receipt to this bot.",
        "pay_card_text": "Order: {order_number}\nProduct: {product_name}\nPrice: {price_uzs} UZS\n\nCard details:\n{card_number}\n\nEnter the amount: {price_uzs} UZS\n\nAfter payment, send the receipt to this bot.",
        "pay_crypto_text": "Order: {order_number}\nProduct: {product_name}\nPrice: {price_usd}$\n\nUSDT (TRC20):\n{wallet}\n\nAfter payment, send the receipt to this bot.",
        "payment_check_saved": "✅ Receipt received.\n\nWe sent it to the admin for review. The status will update after confirmation.",
        "order_cancelled": "Order {order_number}\nStatus: cancelled\nMessage: order cancelled",
        "btn_back": "◀ Back",
        "btn_menu": "🏠 Menu",
        "btn_chatgpt": "ChatGPT Plus/Pro",
        "btn_capcut": "CapCut Pro",
        "btn_grok": "Super Grok",
        "btn_other": "Other",
        "btn_buy": "Proceed",
        "btn_use_this_gmail": "Use this",
        "btn_use_other_gmail": "Other",
        "btn_question": "I have a question",
        "btn_several": "I need several",
        "btn_trial": "Try 3 days for free",
        "btn_promocode": "I have a promo code",
        "btn_check_sub": "Check subscription",
        "btn_click": "Click",
        "btn_card": "Humo/Visa",
        "btn_crypto": "USDT",
        "btn_custom_own": "I want my own",
        "btn_subscribe": "Subscribe",
        "btn_cancel": "Cancel",
        "other_games": "Game values",
        "other_music": "Music",
        "multi_chatgpt_service": "ChatGPT Plus",
        "multi_capcut_service": "CapCut Pro",
    },
}


def _language(language: str | None) -> str:
    return language if language in TEXTS else "ru"


def text(language: str | None, key: str, **kwargs) -> str:
    language = _language(language)
    values = TEXTS.get(language) or {}
    if not values and language in PRICE_HINTS and isinstance(PRICE_HINTS[language], dict):
        values = PRICE_HINTS[language]
    value = values.get(key) or TEXTS["ru"][key]
    try:
        return value.format(**kwargs)
    except Exception:
        return value


def format_price_uzs(value: Decimal | str | int | float) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal("0")
    return f"{amount:,.0f}".replace(",", " ")


def product_title(language: str | None, product_code: str) -> str:
    language = _language(language)
    return PRODUCT_TITLES.get(language, PRODUCT_TITLES["ru"]).get(product_code, product_code)


def invoice_hint(language: str | None, product_code: str) -> str:
    language = _language(language)
    return PRICE_HINTS.get(language, {}).get(product_code, "")


def crypto_price_for_product(product_code: str) -> str:
    return CRYPTO_PRICES.get(product_code, "0")


def other_request_name(language: str | None, callback_data: str) -> str:
    language = _language(language)
    mapping = {
        "other_adobe": "Adobe Cloud",
        "other_games": text(language, "other_games"),
        "other_telegram": "Telegram Premium",
        "other_yandex": "Yandex Go",
        "other_music": text(language, "other_music"),
        "other_custom_own": text(language, "btn_custom_own"),
    }
    return mapping.get(callback_data, "")


def multi_service_name(language: str | None, callback_data: str) -> str:
    language = _language(language)
    if callback_data == "multi_capcut":
        return text(language, "multi_capcut_service")
    return text(language, "multi_chatgpt_service")


def chatgpt_card_text(language: str | None, price_uzs: Decimal | str | int | float) -> str:
    return text(language, "chatgpt_1m_text", price_uzs=format_price_uzs(price_uzs))


def capcut_card_text(language: str | None, price_uzs: Decimal | str | int | float) -> str:
    return text(language, "capcut_1m_text", price_uzs=format_price_uzs(price_uzs))


def invoice_text(language: str | None, product_code: str, order_number: str, price_uzs: Decimal | str | int | float) -> str:
    return text(
        language,
        "invoice_title",
        order_number=order_number,
        product_name=product_title(language, product_code),
        price_uzs=format_price_uzs(price_uzs),
        usd_part=invoice_hint(language, product_code),
    )


def payment_instruction_text(
    language: str | None,
    payment_code: str,
    order_number: str,
    product_name: str,
    price_uzs: Decimal | str | int | float,
    price_usd: str,
    card_number: str,
    wallet: str,
) -> str:
    payload = {
        "order_number": order_number,
        "product_name": product_name,
        "price_uzs": format_price_uzs(price_uzs),
        "price_usd": price_usd,
        "card_number": card_number,
        "wallet": wallet,
    }
    if payment_code == "click":
        return text(language, "pay_click_text", **payload)
    if payment_code == "card":
        return text(language, "pay_card_text", **payload)
    return text(language, "pay_crypto_text", **payload)


def build_menu_only_markup(language: str | None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text(language, "btn_menu"), callback_data="menu:main")]]
    )


def build_single_back_markup(language: str | None, callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text(language, "btn_back"), callback_data=callback_data, style="danger")]]
    )


def build_subscriptions_markup(language: str | None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text(language, "btn_chatgpt"), callback_data="open_chatgpt", icon_custom_emoji_id=EMOJI_ID_CHATGPT)],
            [InlineKeyboardButton(text=text(language, "btn_capcut"), callback_data="open_capcut", icon_custom_emoji_id=EMOJI_ID_CAPCUT)],
            [InlineKeyboardButton(text=text(language, "btn_grok"), callback_data="open_grok", icon_custom_emoji_id=EMOJI_ID_GROK)],
            [InlineKeyboardButton(text=text(language, "btn_other"), callback_data="open_other", icon_custom_emoji_id=EMOJI_ID_ADOBE)],
            [InlineKeyboardButton(text=text(language, "btn_back"), callback_data="menu:main", style="danger")],
        ]
    )


def build_chatgpt_menu_markup(language: str | None, support_url: str, price_uzs: Decimal | str | int | float) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"ChatGPT Plus 1 месяц — {format_price_uzs(price_uzs)} сум", callback_data="chatgpt_1m", icon_custom_emoji_id=EMOJI_ID_CHATGPT)],
            [InlineKeyboardButton(text=text(language, "btn_trial"), callback_data="chatgpt_trial")],
            [InlineKeyboardButton(text=text(language, "btn_several"), callback_data="multi_chatgpt")],
            [InlineKeyboardButton(text=text(language, "btn_question"), url=support_url)],
            [
                InlineKeyboardButton(text=text(language, "btn_menu"), callback_data="menu:main"),
                InlineKeyboardButton(text=text(language, "btn_back"), callback_data="open_subscriptions", style="danger"),
            ],
        ]
    )


def build_capcut_menu_markup(language: str | None, support_url: str, price_uzs: Decimal | str | int | float) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"CapCut Pro 1 месяц — {format_price_uzs(price_uzs)} сум", callback_data="capcut_1m", icon_custom_emoji_id=EMOJI_ID_CAPCUT)],
            [InlineKeyboardButton(text="CapCut Pro 12 месяцев — недоступно", callback_data="capcut_locked", style="danger")],
            [InlineKeyboardButton(text=text(language, "btn_several"), callback_data="multi_capcut")],
            [InlineKeyboardButton(text=text(language, "btn_question"), url=support_url)],
            [
                InlineKeyboardButton(text=text(language, "btn_menu"), callback_data="menu:main"),
                InlineKeyboardButton(text=text(language, "btn_back"), callback_data="open_subscriptions", style="danger"),
            ],
        ]
    )


def build_other_menu_markup(language: str | None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Adobe Cloud", callback_data="other_adobe", icon_custom_emoji_id=EMOJI_ID_ADOBE)],
            [InlineKeyboardButton(text=text(language, "other_games"), callback_data="other_games")],
            [InlineKeyboardButton(text="Telegram Premium", callback_data="other_telegram", icon_custom_emoji_id=EMOJI_ID_TELEGRAM)],
            [InlineKeyboardButton(text="Yandex Go", callback_data="other_yandex")],
            [InlineKeyboardButton(text=text(language, "other_music"), callback_data="other_music")],
            [InlineKeyboardButton(text=text(language, "btn_custom_own"), callback_data="other_custom_own")],
            [InlineKeyboardButton(text=text(language, "btn_back"), callback_data="open_subscriptions", style="danger")],
        ]
    )


def build_details_markup(language: str | None, product_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text(language, "btn_buy"), callback_data=f"buy_{product_key}", style="success")],
            [
                InlineKeyboardButton(text=text(language, "btn_back"), callback_data=f"back_to_{product_key}", style="danger"),
                InlineKeyboardButton(text=text(language, "btn_menu"), callback_data="menu:main"),
            ],
        ]
    )


def _capcut_payment_label(language: str | None) -> str:
    language = _language(language)
    if language == "uz":
        return "To‘lovga o‘tish"
    if language == "en":
        return "Proceed to payment"
    return "Перейти к оплате"


def _capcut_cancel_label(language: str | None) -> str:
    language = _language(language)
    if language == "uz":
        return "Buyurtmani bekor qilish"
    if language == "en":
        return "Cancel order"
    return "Отменить заказ"


def _capcut_support_label(language: str | None) -> str:
    language = _language(language)
    if language == "uz":
        return "Texnik yordam"
    if language == "en":
        return "Support"
    return "Техподдержка"


def build_capcut_details_markup(
    language: str | None,
    support_url: str,
    order_id: int | None = None,
) -> InlineKeyboardMarkup:
    pay_callback = f"order:payment_methods:{order_id}" if order_id is not None else "buy_capcut_1m"
    cancel_callback = f"order:cancel:{order_id}" if order_id is not None else "capcut:cancel"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_capcut_payment_label(language), callback_data=pay_callback, style="success")],
            [InlineKeyboardButton(text=_capcut_cancel_label(language), callback_data=cancel_callback, style="danger")],
            [InlineKeyboardButton(text=text(language, "btn_menu"), callback_data="menu:main")],
            [InlineKeyboardButton(text=_capcut_support_label(language), url=support_url)],
        ]
    )


def build_subscription_check_markup(language: str | None, channel_name: str, callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text(language, "btn_subscribe"), url=f"https://t.me/{channel_name.replace('@', '').strip()}")],
            [InlineKeyboardButton(text=text(language, "btn_check_sub"), callback_data=callback_data, style="success")],
            [InlineKeyboardButton(text=text(language, "btn_menu"), callback_data="menu:main")],
        ]
    )


def build_gmail_choice_markup(language: str | None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text(language, "btn_use_this_gmail"), callback_data="chatgpt_month_use_saved_gmail", style="success")],
            [InlineKeyboardButton(text=text(language, "btn_use_other_gmail"), callback_data="chatgpt_month_use_other_gmail", style="danger")],
            [InlineKeyboardButton(text=text(language, "btn_back"), callback_data="chatgpt_1m", style="danger")],
        ]
    )


def build_invoice_markup(language: str | None, order_id: int, payment_methods: Iterable[object]) -> InlineKeyboardMarkup:
    payment_by_code = {
        str(getattr(payment, "code", "")): int(getattr(payment, "id"))
        for payment in payment_methods
        if getattr(payment, "id", None) is not None
    }
    rows: list[list[InlineKeyboardButton]] = []
    for code, label_key in (("click", "btn_click"), ("card", "btn_card"), ("usdt_trc20", "btn_crypto")):
        payment_id = payment_by_code.get(code)
        if payment_id is None:
            continue
        rows.append([InlineKeyboardButton(text=text(language, label_key), callback_data=f"order:pay:{order_id}:{payment_id}", style="success")])
    rows.append([InlineKeyboardButton(text=text(language, "btn_promocode"), callback_data=f"order:promo:{order_id}")])
    rows.append(
        [
            InlineKeyboardButton(text=text(language, "btn_cancel"), callback_data=f"order:cancel:{order_id}", style="danger"),
            InlineKeyboardButton(text=text(language, "btn_menu"), callback_data="menu:main"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_payment_back_markup(language: str | None, order_id: int, support_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=text(language, "btn_cancel"), callback_data=f"order:cancel:{order_id}", style="danger"),
                InlineKeyboardButton(text=text(language, "btn_menu"), callback_data="menu:main"),
            ],
            [InlineKeyboardButton(text=text(language, "btn_question"), url=support_url)],
        ]
    )


def build_stock_empty_markup(language: str | None, support_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text(language, "btn_menu"), callback_data="menu:main")],
            [InlineKeyboardButton(text=text(language, "btn_question"), url=support_url)],
        ]
    )

from __future__ import annotations

from config import Settings
from db.base import ButtonActionType, Language, PaymentProviderType, ProductStatus


DEFAULT_CATEGORIES = [
    {
        "code": "saas",
        "slug": "saas-subscriptions",
        "sort_order": 10,
        "is_active": True,
        "translations": {
            Language.RU.value: {"name": "SaaS подписки", "description": "Цифровые подписки и сервисы."},
            Language.UZ.value: {"name": "SaaS obunalari", "description": "Raqamli obunalar va servislar."},
            Language.EN.value: {"name": "SaaS subscriptions", "description": "Digital subscriptions and services."},
        },
    },
    {
        "code": "game_values",
        "slug": "game-values",
        "sort_order": 20,
        "is_active": True,
        "translations": {
            Language.RU.value: {"name": "Игровые ценности", "description": "Игровые валюты и цифровые товары."},
            Language.UZ.value: {"name": "O'yin qiymatlari", "description": "O'yin valyutalari va raqamli mahsulotlar."},
            Language.EN.value: {"name": "Game values", "description": "Game currencies and digital goods."},
        },
    },
]


DEFAULT_PRODUCTS = [
    {
        "code": "chatgpt_plus_month",
        "category_code": "saas",
        "status": ProductStatus.ACTIVE.value,
        "delivery_type": "manual",
        "workflow_type": "chatgpt_manual",
        "price": "99000.00",
        "currency": "UZS",
        "sort_order": 10,
        "show_in_catalog": True,
        "extra_data": {"collect_gmail": True, "requires_subscription_check": True},
        "translations": {
            Language.RU.value: {
                "name": "ChatGPT Plus/Pro",
                "description": "Подписка ChatGPT Plus/Pro.\n\nПосле оплаты заказ поступает админу на ручное выполнение.",
            },
            Language.UZ.value: {
                "name": "ChatGPT Plus/Pro",
                "description": "ChatGPT Plus/Pro obunasi.\n\nTo'lovdan so'ng buyurtma administratorga qo'lda bajarish uchun yuboriladi.",
            },
            Language.EN.value: {
                "name": "ChatGPT Plus/Pro",
                "description": "ChatGPT Plus/Pro subscription.\n\nAfter payment the order goes to an admin for manual completion.",
            },
        },
    },
    {
        "code": "capcut_pro_month",
        "category_code": "saas",
        "status": ProductStatus.ACTIVE.value,
        "delivery_type": "auto",
        "workflow_type": "capcut_auto",
        "price": "49000.00",
        "currency": "UZS",
        "sort_order": 20,
        "show_in_catalog": True,
        "extra_data": {"stock_code": "capcut"},
        "translations": {
            Language.RU.value: {
                "name": "CapCut Pro",
                "description": "CapCut Pro на 1 месяц.\n\nПосле подтверждения оплаты бот автоматически выдаёт логин и пароль.",
            },
            Language.UZ.value: {
                "name": "CapCut Pro",
                "description": "1 oylik CapCut Pro.\n\nTo'lov tasdiqlangach bot login va parolni avtomatik beradi.",
            },
            Language.EN.value: {
                "name": "CapCut Pro",
                "description": "CapCut Pro for 1 month.\n\nAfter payment confirmation the bot automatically delivers login and password.",
            },
        },
    },
    {
        "code": "chatgpt_trial_3d",
        "category_code": "saas",
        "status": ProductStatus.ACTIVE.value,
        "delivery_type": "manual",
        "workflow_type": "trial",
        "price": "0.00",
        "currency": "UZS",
        "sort_order": 30,
        "show_in_catalog": False,
        "extra_data": {"requires_subscription_check": True, "trial_days": 3},
        "translations": {
            Language.RU.value: {"name": "ChatGPT Trial 3 дня", "description": "Пробная заявка ChatGPT на 3 дня после проверки администратором."},
            Language.UZ.value: {"name": "ChatGPT Trial 3 kun", "description": "Administrator tekshiruvdan keyin 3 kunlik ChatGPT sinov arizasi."},
            Language.EN.value: {"name": "ChatGPT Trial 3 days", "description": "3-day ChatGPT trial request after admin review."},
        },
    },
    {
        "code": "grok_template",
        "category_code": "saas",
        "status": ProductStatus.HIDDEN.value,
        "delivery_type": "manual",
        "workflow_type": "manual",
        "price": "0.00",
        "currency": "UZS",
        "sort_order": 40,
        "show_in_catalog": True,
        "extra_data": {},
        "translations": {
            Language.RU.value: {"name": "Grok", "description": "Шаблон товара Grok. Настройте цену и включите товар из админки."},
            Language.UZ.value: {"name": "Grok", "description": "Grok mahsuloti shabloni. Narxni sozlang va admin paneldan yoqing."},
            Language.EN.value: {"name": "Grok", "description": "Grok product template. Configure the price and enable it from the admin panel."},
        },
    },
    {
        "code": "adobe_template",
        "category_code": "saas",
        "status": ProductStatus.HIDDEN.value,
        "delivery_type": "manual",
        "workflow_type": "manual",
        "price": "0.00",
        "currency": "UZS",
        "sort_order": 50,
        "show_in_catalog": True,
        "extra_data": {},
        "translations": {
            Language.RU.value: {"name": "Adobe", "description": "Шаблон товара Adobe. Настройте цену и включите товар из админки."},
            Language.UZ.value: {"name": "Adobe", "description": "Adobe mahsuloti shabloni. Narxni sozlang va admin paneldan yoqing."},
            Language.EN.value: {"name": "Adobe", "description": "Adobe product template. Configure the price and enable it from the admin panel."},
        },
    },
]


DEFAULT_TEXTS = {
    "user.choose_language": {
        "group": "user",
        "description": "Prompt before language selection",
        "translations": {"ru": "Выберите язык", "uz": "Tilni tanlang", "en": "Choose language"},
    },
    "user.main_title": {
        "group": "user",
        "description": "Main menu title",
        "translations": {"ru": "Subnowa", "uz": "Subnowa", "en": "Subnowa"},
    },
    "user.main_body": {
        "group": "user",
        "description": "Main menu body",
        "translations": {"ru": "Выберите раздел ниже.", "uz": "Quyidagi bo'limlardan birini tanlang.", "en": "Choose a section below."},
    },
    "user.catalog_title": {
        "group": "user",
        "description": "Catalog title",
        "translations": {"ru": "Каталог", "uz": "Katalog", "en": "Catalog"},
    },
    "user.profile_title": {
        "group": "user",
        "description": "Profile title",
        "translations": {"ru": "Профиль", "uz": "Profil", "en": "Profile"},
    },
    "user.no_completed_orders": {
        "group": "user",
        "description": "No completed orders",
        "translations": {
            "ru": "У вас пока нет завершённых заказов.",
            "uz": "Sizda hali yakunlangan buyurtmalar yo'q.",
            "en": "You do not have any completed orders yet.",
        },
    },
    "user.order_history_title": {
        "group": "user",
        "description": "History title",
        "translations": {"ru": "История заказов", "uz": "Buyurtmalar tarixi", "en": "Order history"},
    },
    "user.faq_title": {
        "group": "user",
        "description": "FAQ title",
        "translations": {"ru": "FAQ", "uz": "FAQ", "en": "FAQ"},
    },
    "user.faq_body": {
        "group": "user",
        "description": "FAQ body",
        "translations": {
            "ru": "Оплатите заказ, отправьте чек и дождитесь обработки. История показывает только завершённые заказы.",
            "uz": "Buyurtmani to'lang, chekni yuboring va ishlov berilishini kuting. Tarixda faqat yakunlangan buyurtmalar ko'rinadi.",
            "en": "Pay for the order, send the receipt and wait for processing. History shows completed orders only.",
        },
    },
    "user.choose_payment_method": {
        "group": "user",
        "description": "Choose payment method text",
        "translations": {"ru": "Выберите способ оплаты.", "uz": "To'lov usulini tanlang.", "en": "Choose a payment method."},
    },
    "user.send_payment_proof": {
        "group": "user",
        "description": "Prompt to send check",
        "translations": {
            "ru": "После оплаты отправьте чек фото или документом.",
            "uz": "To'lovdan so'ng chekni rasm yoki hujjat sifatida yuboring.",
            "en": "After payment send the receipt as a photo or document.",
        },
    },
    "user.payment_check_saved": {
        "group": "user",
        "description": "Check uploaded",
        "translations": {
            "ru": "Чек получен. Ожидайте проверки администратора.",
            "uz": "Chek qabul qilindi. Administrator tekshiruvini kuting.",
            "en": "Receipt received. Please wait for admin review.",
        },
    },
    "user.payment_rejected": {
        "group": "user",
        "description": "Payment rejected message",
        "translations": {
            "ru": "Оплата отклонена. Если это ошибка, свяжитесь с поддержкой.",
            "uz": "To'lov rad etildi. Agar bu xato bo'lsa, qo'llab-quvvatlashga yozing.",
            "en": "Payment was rejected. Contact support if this is a mistake.",
        },
    },
    "user.payment_approved": {
        "group": "user",
        "description": "Payment approved",
        "translations": {"ru": "Оплата подтверждена.", "uz": "To'lov tasdiqlandi.", "en": "Payment confirmed."},
    },
    "user.order_processing": {
        "group": "user",
        "description": "Order processing",
        "translations": {"ru": "Ваш заказ передан в обработку.", "uz": "Buyurtmangiz ishlovga o'tkazildi.", "en": "Your order is now being processed."},
    },
    "user.order_completed": {
        "group": "user",
        "description": "Order completed",
        "translations": {"ru": "Заказ завершён.", "uz": "Buyurtma yakunlandi.", "en": "Order completed."},
    },
    "user.order_cancelled": {
        "group": "user",
        "description": "Order cancelled",
        "translations": {"ru": "Заказ отменён.", "uz": "Buyurtma bekor qilindi.", "en": "Order cancelled."},
    },
    "user.stock_empty": {
        "group": "user",
        "description": "Stock empty message",
        "translations": {
            "ru": "Склад временно пуст. Свяжитесь с поддержкой или попробуйте позже.",
            "uz": "Ombor vaqtincha bo'sh. Qo'llab-quvvatlashga yozing yoki keyinroq urinib ko'ring.",
            "en": "Stock is currently empty. Contact support or try again later.",
        },
    },
    "user.trial_gmail_prompt": {
        "group": "user",
        "description": "Trial Gmail prompt",
        "translations": {"ru": "Введите Gmail для пробной подписки ChatGPT.", "uz": "ChatGPT sinov obunasi uchun Gmail kiriting.", "en": "Enter the Gmail address for the ChatGPT trial."},
    },
    "user.trial_subscribe": {
        "group": "user",
        "description": "Subscribe before trial",
        "translations": {"ru": "Подпишитесь на канал и нажмите кнопку проверки.", "uz": "Kanalga obuna bo'ling va tekshirish tugmasini bosing.", "en": "Subscribe to the channel and press the check button."},
    },
    "user.trial_not_subscribed": {
        "group": "user",
        "description": "Trial not subscribed",
        "translations": {"ru": "Вы ещё не подписались на канал.", "uz": "Siz hali kanalga obuna bo'lmadingiz.", "en": "You are not subscribed to the channel yet."},
    },
    "user.trial_already_used": {
        "group": "user",
        "description": "Trial already used",
        "translations": {"ru": "Вы уже использовали пробную подписку.", "uz": "Siz sinov obunasidan avval foydalangansiz.", "en": "You have already used the trial subscription."},
    },
    "user.trial_created": {
        "group": "user",
        "description": "Trial created",
        "translations": {"ru": "Пробная заявка создана и передана администратору.", "uz": "Sinov arizasi yaratildi va administratorga yuborildi.", "en": "Trial request created and sent to the admin."},
    },
    "user.trial_approved": {
        "group": "user",
        "description": "Trial approved",
        "translations": {"ru": "Пробная подписка одобрена.", "uz": "Sinov obunasi tasdiqlandi.", "en": "Trial subscription approved."},
    },
    "user.trial_rejected": {
        "group": "user",
        "description": "Trial rejected",
        "translations": {"ru": "Пробная подписка отклонена.", "uz": "Sinov obunasi rad etildi.", "en": "Trial subscription rejected."},
    },
    "user.chatgpt_gmail_prompt": {
        "group": "user",
        "description": "ChatGPT Gmail prompt",
        "translations": {"ru": "Введите Gmail для оформления ChatGPT Plus/Pro.", "uz": "ChatGPT Plus/Pro uchun Gmail kiriting.", "en": "Enter the Gmail address for ChatGPT Plus/Pro."},
    },
    "user.chatgpt_saved_gmail_choice": {
        "group": "user",
        "description": "Saved Gmail prompt",
        "translations": {
            "ru": "Найден Gmail <b>{gmail}</b>. Использовать его или указать другой?",
            "uz": "<b>{gmail}</b> Gmail topildi. Shu manzilni ishlatasizmi yoki boshqasini kiritasizmi?",
            "en": "Found Gmail <b>{gmail}</b>. Use it or enter another one?",
        },
    },
    "user.custom_request_prompt": {
        "group": "user",
        "description": "Custom request prompt",
        "translations": {"ru": "Опишите, какую подписку или товар вы хотите получить.", "uz": "Qanday obuna yoki mahsulot kerakligini yozing.", "en": "Describe the subscription or product you want."},
    },
    "user.custom_request_created": {
        "group": "user",
        "description": "Custom request created",
        "translations": {"ru": "Заявка создана. Администратор рассмотрит её позже.", "uz": "Ariza yaratildi. Administrator keyinroq ko'rib chiqadi.", "en": "Request created. An admin will review it later."},
    },
    "button.back": {
        "group": "button",
        "description": "Back button",
        "translations": {"ru": "Назад", "uz": "Ortga", "en": "Back"},
    },
    "button.menu": {
        "group": "button",
        "description": "Main menu button",
        "translations": {"ru": "Меню", "uz": "Menyu", "en": "Menu"},
    },
    "button.buy": {
        "group": "button",
        "description": "Buy button",
        "translations": {"ru": "Купить", "uz": "Sotib olish", "en": "Buy"},
    },
    "button.history": {
        "group": "button",
        "description": "History button",
        "translations": {"ru": "История", "uz": "Tarix", "en": "History"},
    },
    "button.send_check": {
        "group": "button",
        "description": "Send check button",
        "translations": {"ru": "Отправить чек", "uz": "Chek yuborish", "en": "Send receipt"},
    },
    "button.check_subscription": {
        "group": "button",
        "description": "Check subscription button",
        "translations": {"ru": "Проверить подписку", "uz": "Obunani tekshirish", "en": "Check subscription"},
    },
    "button.use_saved_gmail": {
        "group": "button",
        "description": "Use saved gmail button",
        "translations": {"ru": "Использовать этот Gmail", "uz": "Shu Gmailni ishlatish", "en": "Use this Gmail"},
    },
    "button.use_other_gmail": {
        "group": "button",
        "description": "Use other gmail button",
        "translations": {"ru": "Указать другой Gmail", "uz": "Boshqa Gmail kiritish", "en": "Use another Gmail"},
    },
    "admin.panel_title": {
        "group": "admin",
        "description": "Admin main title",
        "translations": {"ru": "Админ-панель"},
    },
    "admin.stats_title": {
        "group": "admin",
        "description": "Stats title",
        "translations": {"ru": "Статистика"},
    },
    "admin.orders_title": {
        "group": "admin",
        "description": "Orders title",
        "translations": {"ru": "Заказы"},
    },
    "admin.products_title": {
        "group": "admin",
        "description": "Products title",
        "translations": {"ru": "Товары"},
    },
    "admin.payments_title": {
        "group": "admin",
        "description": "Payments title",
        "translations": {"ru": "Оплаты"},
    },
    "admin.stock_title": {
        "group": "admin",
        "description": "Stock title",
        "translations": {"ru": "Склад CapCut"},
    },
    "admin.buttons_title": {
        "group": "admin",
        "description": "Buttons title",
        "translations": {"ru": "Кнопки"},
    },
    "admin.texts_title": {
        "group": "admin",
        "description": "Texts title",
        "translations": {"ru": "Тексты"},
    },
}


DEFAULT_LAYOUTS = [
    {
        "code": "main_menu",
        "title": "Main menu",
        "scope": "user",
        "buttons": [
            {"code": "catalog", "action_type": ButtonActionType.CALLBACK.value, "action_value": "menu:catalog", "style": "default", "row_index": 0, "sort_order": 10, "translations": {"ru": "Подписки", "uz": "Obunalar", "en": "Subscriptions"}},
            {"code": "profile", "action_type": ButtonActionType.CALLBACK.value, "action_value": "menu:profile", "style": "default", "row_index": 1, "sort_order": 10, "translations": {"ru": "Профиль", "uz": "Profil", "en": "Profile"}},
            {"code": "languages", "action_type": ButtonActionType.CALLBACK.value, "action_value": "menu:languages", "style": "default", "row_index": 1, "sort_order": 20, "translations": {"ru": "Языки", "uz": "Tillar", "en": "Languages"}},
            {"code": "support", "action_type": ButtonActionType.URL.value, "action_value": "__SUPPORT_URL__", "style": "default", "row_index": 2, "sort_order": 10, "translations": {"ru": "Поддержка", "uz": "Qo'llab-quvvatlash", "en": "Support"}},
            {"code": "about", "action_type": ButtonActionType.URL.value, "action_value": "__ABOUT_URL__", "style": "default", "row_index": 3, "sort_order": 10, "translations": {"ru": "О нас", "uz": "Biz haqimizda", "en": "About"}},
            {"code": "faq", "action_type": ButtonActionType.CALLBACK.value, "action_value": "menu:faq", "style": "default", "row_index": 3, "sort_order": 20, "translations": {"ru": "FAQ", "uz": "FAQ", "en": "FAQ"}},
        ],
    },
    {
        "code": "admin_main",
        "title": "Admin main",
        "scope": "admin",
        "buttons": [
            {"code": "products", "action_type": ButtonActionType.CALLBACK.value, "action_value": "admin:products", "style": "default", "row_index": 0, "sort_order": 10, "translations": {"ru": "Товары"}},
            {"code": "texts", "action_type": ButtonActionType.CALLBACK.value, "action_value": "admin:texts", "style": "default", "row_index": 0, "sort_order": 20, "translations": {"ru": "Тексты"}},
            {"code": "buttons", "action_type": ButtonActionType.CALLBACK.value, "action_value": "admin:buttons", "style": "default", "row_index": 1, "sort_order": 10, "translations": {"ru": "Кнопки"}},
            {"code": "payments", "action_type": ButtonActionType.CALLBACK.value, "action_value": "admin:payments", "style": "default", "row_index": 1, "sort_order": 20, "translations": {"ru": "Оплаты"}},
            {"code": "stock", "action_type": ButtonActionType.CALLBACK.value, "action_value": "admin:stock", "style": "default", "row_index": 2, "sort_order": 10, "translations": {"ru": "Склад CapCut"}},
            {"code": "orders", "action_type": ButtonActionType.CALLBACK.value, "action_value": "admin:orders", "style": "default", "row_index": 2, "sort_order": 20, "translations": {"ru": "Заказы"}},
            {"code": "stats", "action_type": ButtonActionType.CALLBACK.value, "action_value": "admin:stats", "style": "default", "row_index": 3, "sort_order": 10, "translations": {"ru": "Статистика"}},
        ],
    },
]


def get_default_settings(settings: Settings) -> list[dict[str, str]]:
    return [
        {"key": "support_url", "value": settings.support_url, "value_type": "string", "description": "Support URL"},
        {"key": "about_url", "value": settings.about_url, "value_type": "string", "description": "About URL"},
        {"key": "review_url", "value": settings.review_url, "value_type": "string", "description": "Review URL"},
        {"key": "required_channel", "value": settings.required_channel, "value_type": "string", "description": "Channel required for ChatGPT trial/orders"},
    ]


def get_default_payment_methods() -> list[dict[str, object]]:
    return [
        {
            "code": "click",
            "provider_type": PaymentProviderType.CLICK.value,
            "admin_title": "Click",
            "credentials": "+998",
            "sort_order": 10,
            "translations": {
                "ru": {"title": "Click", "instructions": "Оплатите через Click на номер:\n<code>{credentials}</code>\n\nПосле оплаты отправьте чек."},
                "uz": {"title": "Click", "instructions": "Click orqali quyidagi raqamga to'lang:\n<code>{credentials}</code>\n\nTo'lovdan so'ng chek yuboring."},
                "en": {"title": "Click", "instructions": "Pay via Click to this number:\n<code>{credentials}</code>\n\nSend the receipt after payment."},
            },
        },
        {
            "code": "card",
            "provider_type": PaymentProviderType.CARD.value,
            "admin_title": "Humo/Visa",
            "credentials": "9860100126034816",
            "sort_order": 20,
            "translations": {
                "ru": {"title": "Humo / Visa", "instructions": "Переведите оплату на карту:\n<code>{credentials}</code>\n\nПосле оплаты отправьте чек."},
                "uz": {"title": "Humo / Visa", "instructions": "To'lovni kartaga o'tkazing:\n<code>{credentials}</code>\n\nTo'lovdan so'ng chek yuboring."},
                "en": {"title": "Humo / Visa", "instructions": "Transfer the payment to this card:\n<code>{credentials}</code>\n\nSend the receipt after payment."},
            },
        },
        {
            "code": "usdt_trc20",
            "provider_type": PaymentProviderType.CRYPTO.value,
            "admin_title": "USDT TRC20",
            "credentials": "TUr3m7sAWpiysQs5S1jQkbxcvJARqAD8Rs",
            "sort_order": 30,
            "translations": {
                "ru": {"title": "USDT TRC20", "instructions": "Переведите USDT TRC20 на адрес:\n<code>{credentials}</code>\n\nПосле оплаты отправьте чек."},
                "uz": {"title": "USDT TRC20", "instructions": "USDT TRC20 ni quyidagi manzilga o'tkazing:\n<code>{credentials}</code>\n\nTo'lovdan so'ng chek yuboring."},
                "en": {"title": "USDT TRC20", "instructions": "Transfer USDT TRC20 to this address:\n<code>{credentials}</code>\n\nSend the receipt after payment."},
            },
        },
    ]

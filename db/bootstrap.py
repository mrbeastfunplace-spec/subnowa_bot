from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from config import Settings
from db.base import ButtonActionType, Language, PaymentProviderType, ProductStatus
from db.defaults import DEFAULT_CATEGORIES, DEFAULT_LAYOUTS, DEFAULT_PRODUCTS, DEFAULT_TEXTS, get_default_payment_methods, get_default_settings
from db.models import (
    Base,
    Category,
    CategoryTranslation,
    Layout,
    LayoutButton,
    LayoutButtonTranslation,
    PaymentMethod,
    PaymentMethodTranslation,
    Product,
    ProductPaymentMethod,
    ProductTranslation,
    Setting,
    TextEntry,
    TextTranslation,
)


_CATEGORY_SLUG_MAX_LENGTH = 64
_LEGACY_UI_SYNC_SETTING_KEY = "system.legacy_ui_sync_version"
_LEGACY_UI_SYNC_VERSION = "2026-04-11-legacy-ui-v2"
_MULTICARD_TEXT_SYNC_SETTING_KEY = "system.multicard_checkout_sync_version"
_MULTICARD_TEXT_SYNC_VERSION = "2026-04-14-multicard-checkout-v1"
_TELEGRAM_PAYMENT_SYNC_SETTING_KEY = "system.telegram_payment_sync_version"
_TELEGRAM_PAYMENT_SYNC_VERSION = "2026-04-14-telegram-payments-v1"
_PRODUCT_COPY_SYNC_SETTING_KEY = "system.product_copy_sync_version"
_PRODUCT_COPY_SYNC_VERSION = "2026-04-15-capcut-copy-v2"
_MULTICARD_TEXT_OVERRIDES: dict[str, dict[str, str]] = {
    "user.faq_body": {
        "ru": (
            "1. Что я получу после оплаты?\n"
            "Вы получите подтверждение заказа и дальнейшие инструкции по подключению.\n\n"
            "2. Как подключается ChatGPT Plus?\n"
            "Мы отправляем приглашение на ваш Gmail, после принятия подписка активируется.\n\n"
            "3. Как подключается CapCut Pro?\n"
            "После подтверждения оплаты вы получаете готовые данные для входа.\n\n"
            "4. Сколько времени занимает подключение?\n"
            "Обычно от нескольких минут до нескольких часов, в зависимости от очереди.\n\n"
            "5. Как проходит оплата?\n"
            "Оплата открывается на защищённой checkout-странице Multicard. После оплаты статус заказа обновляется автоматически.\n\n"
            "6. Нужен ли VPN для использования?\n"
            "В большинстве случаев нет.\n\n"
            "7. Можно ли заказать несколько аккаунтов?\n"
            "Да, используйте кнопку «Хочу несколько», и администратор обработает заявку.\n\n"
            "8. Что делать, если письмо не пришло?\n"
            "Проверьте папки «Спам» и «Промоакции», затем напишите в поддержку.\n\n"
            "9. Можно ли заказать другой сервис?\n"
            "Да, в разделе «Другое» можно оставить заявку на нужную подписку.\n\n"
            "10. Что делать, если возникла проблема после покупки?\n"
            "Напишите в поддержку, указав номер заказа и суть проблемы."
        ),
        "uz": (
            "1. To‘lovdan keyin nima olaman?\n"
            "Buyurtma tasdig‘i va ulash bo‘yicha ko‘rsatmalar olasiz.\n\n"
            "2. ChatGPT Plus qanday ulanadi?\n"
            "Gmail'ingizga yuborilgan havolani tasdiqlaysiz va obuna faollashadi.\n\n"
            "3. CapCut Pro qanday beriladi?\n"
            "To‘lov tasdiqlangach, tayyor login va parol yuboriladi.\n\n"
            "4. Ulanish qancha vaqt oladi?\n"
            "Odatda bir necha daqiqadan bir necha soatgacha.\n\n"
            "5. To‘lov qanday amalga oshadi?\n"
            "To‘lov Multicard himoyalangan checkout sahifasida ochiladi. To‘lovdan keyin buyurtma holati avtomatik yangilanadi.\n\n"
            "6. VPN kerakmi?\n"
            "Ko‘p hollarda yo‘q.\n\n"
            "7. Bir nechta akkaunt buyurtma qilish mumkinmi?\n"
            "Ha, «Bir nechta kerak» tugmasi orqali so‘rov yuboring.\n\n"
            "8. Xat kelmasa nima qilaman?\n"
            "Spam va Promotions papkalarini tekshiring, keyin yordamga yozing.\n\n"
            "9. Boshqa xizmat buyurtma qilish mumkinmi?\n"
            "Ha, «Boshqa» bo‘limida so‘rov qoldiring.\n\n"
            "10. Xariddan keyin muammo bo‘lsa nima qilaman?\n"
            "Buyurtma raqami bilan yordam xizmatiga yozing."
        ),
        "en": (
            "1. What do I receive after payment?\n"
            "You receive order confirmation and connection instructions.\n\n"
            "2. How is ChatGPT Plus activated?\n"
            "We send an invitation to your Gmail and the subscription activates after you accept it.\n\n"
            "3. How is CapCut Pro delivered?\n"
            "After payment confirmation you receive ready-to-use login details.\n\n"
            "4. How long does activation take?\n"
            "Usually from a few minutes to a few hours.\n\n"
            "5. How does payment work?\n"
            "Payment opens on the secure Multicard checkout page. After payment, the order status updates automatically.\n\n"
            "6. Do I need a VPN?\n"
            "Usually no.\n\n"
            "7. Can I order several accounts?\n"
            "Yes, use the several-accounts button and the admin will process it.\n\n"
            "8. What if the email does not arrive?\n"
            "Check Spam and Promotions, then contact support.\n\n"
            "9. Can I request another service?\n"
            "Yes, use the Other section and send your request.\n\n"
            "10. What should I do if there is a problem after purchase?\n"
            "Contact support and include your order number."
        ),
    },
    "user.choose_payment_method": {
        "ru": "Перейдите к оплате.",
        "uz": "To‘lovga o‘ting.",
        "en": "Proceed to payment.",
    },
    "user.send_payment_proof": {
        "ru": "После оплаты статус заказа обновится автоматически.",
        "uz": "To‘lovdan keyin buyurtma holati avtomatik yangilanadi.",
        "en": "The order status will update automatically after payment.",
    },
}
_TELEGRAM_PAYMENT_TEXT_OVERRIDES: dict[str, dict[str, str]] = {
    "user.faq_body": {
        "ru": (
            "1. Что я получу после оплаты?\n"
            "Вы получите подтверждение заказа и дальнейшие инструкции по подключению.\n\n"
            "2. Как подключается ChatGPT Plus?\n"
            "Мы отправляем приглашение на ваш Gmail, после принятия подписка активируется.\n\n"
            "3. Как подключается CapCut Pro?\n"
            "После успешной оплаты бот автоматически выдаёт готовые данные для входа.\n\n"
            "4. Сколько времени занимает подключение?\n"
            "Обычно от нескольких минут до нескольких часов, в зависимости от очереди.\n\n"
            "5. Как проходит оплата?\n"
            "После нажатия кнопки «Оформить» бот сразу отправляет Telegram invoice. Оплата проходит внутри Telegram, без внешних checkout-страниц и ссылок.\n\n"
            "6. Нужен ли VPN для использования?\n"
            "В большинстве случаев нет.\n\n"
            "7. Можно ли заказать несколько аккаунтов?\n"
            "Да, используйте кнопку «Хочу несколько», и администратор обработает заявку.\n\n"
            "8. Что делать, если письмо не пришло?\n"
            "Проверьте папки «Спам» и «Промоакции», затем напишите в поддержку.\n\n"
            "9. Можно ли заказать другой сервис?\n"
            "Да, в разделе «Другое» можно оставить заявку на нужную подписку.\n\n"
            "10. Что делать, если возникла проблема после покупки?\n"
            "Напишите в поддержку, указав номер заказа и суть проблемы."
        ),
        "uz": (
            "1. To'lovdan keyin nima olaman?\n"
            "Buyurtma tasdig'i va ulash bo'yicha ko'rsatmalar olasiz.\n\n"
            "2. ChatGPT Plus qanday ulanadi?\n"
            "Gmail'ingizga yuborilgan havolani tasdiqlaysiz va obuna faollashadi.\n\n"
            "3. CapCut Pro qanday beriladi?\n"
            "Muvaffaqiyatli to'lovdan keyin bot tayyor login va parolni avtomatik yuboradi.\n\n"
            "4. Ulanish qancha vaqt oladi?\n"
            "Odatda bir necha daqiqadan bir necha soatgacha.\n\n"
            "5. To'lov qanday amalga oshadi?\n"
            "«Rasmiylashtirish» tugmasidan keyin bot darhol Telegram invoice yuboradi. To'lov faqat Telegram ichida o'tadi, tashqi sahifalar ochilmaydi.\n\n"
            "6. VPN kerakmi?\n"
            "Ko'p hollarda yo'q.\n\n"
            "7. Bir nechta akkaunt buyurtma qilish mumkinmi?\n"
            "Ha, «Bir nechta kerak» tugmasi orqali so'rov yuboring.\n\n"
            "8. Xat kelmasa nima qilaman?\n"
            "Spam va Promotions papkalarini tekshiring, keyin yordamga yozing.\n\n"
            "9. Boshqa xizmat buyurtma qilish mumkinmi?\n"
            "Ha, «Boshqa» bo'limida so'rov qoldiring.\n\n"
            "10. Xariddan keyin muammo bo'lsa nima qilaman?\n"
            "Buyurtma raqami bilan yordam xizmatiga yozing."
        ),
        "en": (
            "1. What do I receive after payment?\n"
            "You receive order confirmation and connection instructions.\n\n"
            "2. How is ChatGPT Plus activated?\n"
            "We send an invitation to your Gmail and the subscription activates after you accept it.\n\n"
            "3. How is CapCut Pro delivered?\n"
            "After successful payment the bot automatically delivers ready-to-use login details.\n\n"
            "4. How long does activation take?\n"
            "Usually from a few minutes to a few hours.\n\n"
            "5. How does payment work?\n"
            "After pressing Proceed, the bot immediately sends a Telegram invoice. Payment happens inside Telegram without external checkout pages.\n\n"
            "6. Do I need a VPN?\n"
            "Usually no.\n\n"
            "7. Can I order several accounts?\n"
            "Yes, use the several-accounts button and the admin will process it.\n\n"
            "8. What if the email does not arrive?\n"
            "Check Spam and Promotions, then contact support.\n\n"
            "9. Can I request another service?\n"
            "Yes, use the Other section and send your request.\n\n"
            "10. What should I do if there is a problem after purchase?\n"
            "Contact support and include your order number."
        ),
    },
    "user.choose_payment_method": {
        "ru": "Бот отправит Telegram invoice для оплаты.",
        "uz": "Bot Telegram invoice yuboradi.",
        "en": "The bot will send a Telegram invoice for payment.",
    },
    "user.send_payment_proof": {
        "ru": "После оплаты внутри Telegram статус заказа обновится автоматически.",
        "uz": "Telegram ichidagi to'lovdan keyin buyurtma holati avtomatik yangilanadi.",
        "en": "After paying inside Telegram, the order status updates automatically.",
    },
}
_PRODUCT_TRANSLATION_OVERRIDES: dict[str, dict[str, dict[str, str]]] = {
    "capcut_pro_month": {
        "ru": {
            "description": (
                "💠 Товар: CapCut Pro (1 месяц)\n"
                "💰 Стоимость: 49,000 сум (~350 ₽)\n"
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
        },
        "uz": {
            "description": (
                "💠 Mahsulot: CapCut Pro (1 oy)\n"
                "💰 Narxi: 49,000 so‘m (~350 ₽)\n"
                "—————————————————-\n"
                "⚙️ Qanday ulanadi\n"
                "1. Buyurtmadan so‘ng sizga tayyor akkaunt yuboriladi\n"
                "2. Siz ushbu ma’lumotlarni (login, parol) nusxalab CapCut ga kiritasiz\n"
                "3. Agar sizda akkaunt bo‘lsa, avval undan chiqib, &lt;&gt; usuli bilan qayta kiring\n"
                "⏱ Faol muddati — faollashtirilgan vaqtdan boshlab 30 kun\n\n"
                "🔐 Xavfsizlik\n"
                "— Uzilishlarsiz\n"
                "— Kirish faqat siz tomonidan amalga oshiriladi\n"
                "— Rasmiy ulanish usullari ishlatiladi\n\n"
                "— Ulanishning barcha bosqichlarida yordam 💬\n"
                "— MDH va boshqa davlatlar foydalanuvchilari uchun mavjud\n"
                "⸻\n"
                "✅ Afzalliklar\n"
                "✔️ Tez ulanish\n"
                "✔️ Shaffof shartlar\n"
                "✔️ Xariddan keyingi yordam"
            ),
        },
        "en": {
            "description": (
                "💠 Product: CapCut Pro (1 month)\n"
                "💰 Price: 49,000 UZS (~350 ₽)\n"
                "—————————————————-\n"
                "⚙️ How connection works\n"
                "1. We send you a ready account created after the order\n"
                "2. You copy these details (login, password) and paste them into CapCut\n"
                "3. If you already have an account, first log out and then sign in using\n"
                "&lt;&gt;\n"
                "⏱ Duration — 30 days from activation\n\n"
                "🔐 Security\n"
                "— No crashes\n"
                "— Only you can access it\n"
                "— Official connection methods are used\n\n"
                "— Support at every connection step 💬\n"
                "— Available for users from CIS and other countries\n"
                "⸻\n"
                "✅ Advantages\n"
                "✔️ Fast connection\n"
                "✔️ Transparent terms\n"
                "✔️ Support after purchase"
            ),
        },
    },
}
_REPLACEABLE_TEXT_DEFAULTS: dict[str, dict[str, str]] = {
    "user.main_title": {"ru": "Subnowa", "uz": "Subnowa", "en": "Subnowa"},
    "user.main_body": {"ru": "Выберите раздел ниже.", "uz": "Quyidagi bo'limlardan birini tanlang.", "en": "Choose a section below."},
    "user.catalog_title": {"ru": "Каталог", "uz": "Katalog", "en": "Catalog"},
    "user.profile_title": {"ru": "Профиль", "uz": "Profil", "en": "Profile"},
    "user.no_completed_orders": {
        "ru": "У вас пока нет завершённых заказов.",
        "uz": "Sizda hali yakunlangan buyurtmalar yo'q.",
        "en": "You do not have any completed orders yet.",
    },
    "user.faq_body": {
        "ru": "Оплатите заказ, отправьте чек и дождитесь обработки. История показывает только завершённые заказы.",
        "uz": "Buyurtmani to'lang, chekni yuboring va ishlov berilishini kuting. Tarixda faqat yakunlangan buyurtmalar ko'rinadi.",
        "en": "Pay for the order, send the receipt and wait for processing. History shows completed orders only.",
    },
    "user.payment_rejected": {
        "ru": "Оплата отклонена. Если это ошибка, свяжитесь с поддержкой.",
        "uz": "To'lov rad etildi. Agar bu xato bo'lsa, qo'llab-quvvatlashga yozing.",
        "en": "Payment was rejected. Contact support if this is a mistake.",
    },
    "user.order_cancelled": {"ru": "Заказ отменён.", "uz": "Buyurtma bekor qilindi.", "en": "Order cancelled."},
    "user.stock_empty": {
        "ru": "Склад временно пуст. Свяжитесь с поддержкой или попробуйте позже.",
        "uz": "Ombor vaqtincha bo'sh. Qo'llab-quvvatlashga yozing yoki keyinroq urinib ko'ring.",
        "en": "Stock is currently empty. Contact support or try again later.",
    },
    "user.trial_gmail_prompt": {
        "ru": "Введите Gmail для пробной подписки ChatGPT.",
        "uz": "ChatGPT sinov obunasi uchun Gmail kiriting.",
        "en": "Enter the Gmail address for the ChatGPT trial.",
    },
    "user.trial_already_used": {
        "ru": "Вы уже использовали пробную подписку.",
        "uz": "Siz sinov obunasidan avval foydalangansiz.",
        "en": "You have already used the trial subscription.",
    },
    "user.trial_created": {
        "ru": "Пробная заявка создана и передана администратору.",
        "uz": "Sinov arizasi yaratildi va administratorga yuborildi.",
        "en": "Trial request created and sent to the admin.",
    },
    "user.trial_approved": {
        "ru": "Пробная подписка одобрена.",
        "uz": "Sinov obunasi tasdiqlandi.",
        "en": "Trial subscription approved.",
    },
    "user.trial_rejected": {
        "ru": "Пробная подписка отклонена.",
        "uz": "Sinov obunasi rad etildi.",
        "en": "Trial subscription rejected.",
    },
    "user.chatgpt_gmail_prompt": {
        "ru": "Введите Gmail для оформления ChatGPT Plus/Pro.",
        "uz": "ChatGPT Plus/Pro uchun Gmail kiriting.",
        "en": "Enter the Gmail address for ChatGPT Plus/Pro.",
    },
    "user.chatgpt_saved_gmail_choice": {
        "ru": "Найден Gmail <b>{gmail}</b>. Использовать его или указать другой?",
        "uz": "<b>{gmail}</b> Gmail topildi. Shu manzilni ishlatasizmi yoki boshqasini kiritasizmi?",
        "en": "Found Gmail <b>{gmail}</b>. Use it or enter another one?",
    },
    "user.custom_request_prompt": {
        "ru": "Опишите, какую подписку или товар вы хотите получить.",
        "uz": "Qanday obuna yoki mahsulot kerakligini yozing.",
        "en": "Describe the subscription or product you want.",
    },
    "user.custom_request_created": {
        "ru": "Заявка создана. Администратор рассмотрит её позже.",
        "uz": "Ariza yaratildi. Administrator keyinroq ko'rib chiqadi.",
        "en": "Request created. An admin will review it later.",
    },
    "button.back": {"ru": "Назад", "uz": "Ortga", "en": "Back"},
    "button.menu": {"ru": "Меню", "uz": "Menyu", "en": "Menu"},
    "button.buy": {"ru": "Купить", "uz": "Sotib olish", "en": "Buy"},
    "button.history": {"ru": "История", "uz": "Tarix", "en": "History"},
    "button.use_saved_gmail": {"ru": "Использовать этот Gmail", "uz": "Shu Gmailni ishlatish", "en": "Use this Gmail"},
    "button.use_other_gmail": {"ru": "Указать другой Gmail", "uz": "Boshqa Gmail kiritish", "en": "Use another Gmail"},
}
_REPLACEABLE_LAYOUT_DEFAULTS: dict[tuple[str, str], dict[str, str]] = {
    ("main_menu", "catalog"): {"ru": "Подписки", "uz": "Obunalar", "en": "Subscriptions"},
    ("main_menu", "profile"): {"ru": "Профиль", "uz": "Profil", "en": "Profile"},
    ("main_menu", "languages"): {"ru": "Языки", "uz": "Tillar", "en": "Languages"},
    ("main_menu", "support"): {"ru": "Поддержка", "uz": "Qo'llab-quvvatlash", "en": "Support"},
    ("main_menu", "about"): {"ru": "О нас", "uz": "Biz haqimizda", "en": "About"},
    ("main_menu", "faq"): {"ru": "FAQ", "uz": "FAQ", "en": "FAQ"},
}


def _slugify(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = ascii_value.strip().lower()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^a-z0-9-]+", "", slug)
    return re.sub(r"-{2,}", "-", slug).strip("-")


def _should_replace_seed_text(current_value: str | None, replaceable_default: str | None = None) -> bool:
    normalized = (current_value or "").strip()
    if not normalized:
        return True
    if replaceable_default is None:
        return False
    return normalized == replaceable_default.strip()


def _fit_slug(value: str) -> str:
    return value[:_CATEGORY_SLUG_MAX_LENGTH].strip("-")


def _slug_with_suffix(base: str, suffix: str | None = None) -> str:
    fitted_base = _fit_slug(base) or "category"
    if not suffix:
        return fitted_base

    fitted_suffix = _slugify(suffix)
    if not fitted_suffix:
        return fitted_base

    max_base_length = _CATEGORY_SLUG_MAX_LENGTH - len(fitted_suffix) - 1
    trimmed_base = _fit_slug(fitted_base[:max_base_length]) or "category"
    return f"{trimmed_base}-{fitted_suffix}"


def _category_slug_sources(category: Category | None, item: dict | None = None) -> list[str]:
    sources: list[str] = []
    if item is not None:
        explicit_slug = item.get("slug")
        if isinstance(explicit_slug, str):
            sources.append(explicit_slug)

        code = item.get("code")
        if isinstance(code, str):
            sources.append(code)

        translations = item.get("translations")
        if isinstance(translations, dict):
            for lang_code in (Language.EN.value, Language.UZ.value, Language.RU.value):
                payload = translations.get(lang_code)
                if isinstance(payload, dict):
                    name = payload.get("name")
                    if isinstance(name, str):
                        sources.append(name)

    if category is not None:
        if category.slug:
            sources.append(category.slug)
        sources.append(category.code)
        for translation in category.translations:
            if translation.name:
                sources.append(translation.name)

    return sources


def _claim_category_slug(
    category: Category,
    used_slugs: dict[str, Category],
    sources: list[str],
    *,
    preserve_current: bool,
) -> str:
    current_slug = _slugify(category.slug)
    if current_slug and used_slugs.get(current_slug) is category:
        used_slugs.pop(current_slug, None)

    ordered_sources: list[str] = []
    if preserve_current and current_slug:
        ordered_sources.append(current_slug)
    ordered_sources.extend(source for source in sources if source)

    base_slug = ""
    for source in ordered_sources:
        candidate = _slugify(source)
        if candidate:
            base_slug = candidate
            break

    if not base_slug:
        base_slug = _slugify(category.code) or "category"

    candidate = _fit_slug(base_slug) or "category"
    owner = used_slugs.get(candidate)
    if owner in (None, category):
        used_slugs[candidate] = category
        return candidate

    code_slug = _slugify(category.code)
    if code_slug:
        candidate = _slug_with_suffix(base_slug, code_slug)
        owner = used_slugs.get(candidate)
        if owner in (None, category):
            used_slugs[candidate] = category
            return candidate

    counter = 2
    while True:
        candidate = _slug_with_suffix(base_slug, str(counter))
        owner = used_slugs.get(candidate)
        if owner in (None, category):
            used_slugs[candidate] = category
            return candidate
        counter += 1


async def initialize_database(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        await ensure_runtime_schema(session)
        await seed_settings(session, settings)
        await seed_categories(session)
        await normalize_category_slugs(session)
        await seed_products(session)
        await sync_product_copy_once(session)
        await seed_payment_methods(session)
        await seed_texts(session)
        await seed_layouts(session, settings)
        await sync_legacy_ui_once(session, settings)
        await sync_multicard_payment_copy_once(session)
        await sync_telegram_payment_copy_once(session)
        await seed_product_payment_links(session)
        await session.commit()


async def ensure_runtime_schema(session: AsyncSession) -> None:
    await _ensure_column(
        session,
        "orders",
        "expires_at",
        {
            "postgresql": "TIMESTAMP WITH TIME ZONE",
            "sqlite": "DATETIME",
            "default": "DATETIME",
        },
    )
    await _ensure_column(session, "orders", "payment_provider", {"postgresql": "VARCHAR(32)", "sqlite": "TEXT", "default": "TEXT"})
    await _ensure_column(session, "orders", "payment_status", {"postgresql": "VARCHAR(32)", "sqlite": "TEXT", "default": "TEXT"})
    await _ensure_column(session, "orders", "invoice_id", {"postgresql": "VARCHAR(255)", "sqlite": "TEXT", "default": "TEXT"})
    await _ensure_column(session, "orders", "invoice_uuid", {"postgresql": "VARCHAR(64)", "sqlite": "TEXT", "default": "TEXT"})
    await _ensure_column(session, "orders", "checkout_url", {"postgresql": "TEXT", "sqlite": "TEXT", "default": "TEXT"})
    await _ensure_column(
        session,
        "orders",
        "invoice_expiry_at",
        {
            "postgresql": "TIMESTAMP WITH TIME ZONE",
            "sqlite": "DATETIME",
            "default": "DATETIME",
        },
    )


async def _ensure_column(session: AsyncSession, table_name: str, column_name: str, ddl_type: str | dict[str, str]) -> None:
    connection = await session.connection()
    existing_columns = await connection.run_sync(
        lambda sync_connection: {column["name"] for column in inspect(sync_connection).get_columns(table_name)}
    )
    if column_name in existing_columns:
        return
    if isinstance(ddl_type, dict):
        resolved_type = ddl_type.get(connection.dialect.name, ddl_type.get("default"))
    else:
        resolved_type = ddl_type
    if not resolved_type:
        raise RuntimeError(f"Unsupported DDL type mapping for {table_name}.{column_name} on {connection.dialect.name}")
    await session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {resolved_type}"))


async def seed_settings(session: AsyncSession, settings: Settings) -> None:
    for item in get_default_settings(settings):
        row = await session.scalar(select(Setting).where(Setting.key == item["key"]))
        if row is None:
            row = Setting(key=item["key"])
            session.add(row)
        row.value = item["value"]
        row.value_type = item["value_type"]
        row.description = item["description"]


async def seed_categories(session: AsyncSession) -> None:
    categories = (await session.scalars(select(Category))).all()
    categories_by_code = {row.code: row for row in categories}
    used_slugs = {
        normalized_slug: row
        for row in categories
        if (normalized_slug := _slugify(row.slug))
    }

    for item in DEFAULT_CATEGORIES:
        category = categories_by_code.get(item["code"])
        if category is None:
            category = Category(code=item["code"])
            session.add(category)
            categories_by_code[category.code] = category

        category.slug = _claim_category_slug(
            category,
            used_slugs,
            _category_slug_sources(category, item),
            preserve_current=False,
        )
        category.sort_order = item["sort_order"]
        category.is_active = item["is_active"]

        existing = {tr.language.value: tr for tr in category.translations}
        for lang_code, payload in item["translations"].items():
            translation = existing.get(lang_code)
            if translation is None:
                translation = CategoryTranslation(category=category, language=Language(lang_code))
                session.add(translation)
            translation.name = payload["name"]
            translation.description = payload["description"]


async def normalize_category_slugs(session: AsyncSession) -> None:
    categories = (await session.scalars(select(Category))).all()
    used_slugs: dict[str, Category] = {}

    for category in sorted(categories, key=lambda row: (row.id or 0, row.code)):
        category.slug = _claim_category_slug(
            category,
            used_slugs,
            _category_slug_sources(category),
            preserve_current=True,
        )


async def seed_products(session: AsyncSession) -> None:
    categories = {row.code: row for row in (await session.scalars(select(Category))).all()}
    for item in DEFAULT_PRODUCTS:
        product = await session.scalar(select(Product).where(Product.code == item["code"]))
        if product is None:
            product = Product(code=item["code"])
            session.add(product)
            product.category = categories.get(item["category_code"])
            product.status = ProductStatus(item["status"])
            product.delivery_type = item["delivery_type"]
            product.workflow_type = item["workflow_type"]
            product.price = Decimal(item["price"])
            product.currency = item["currency"]
            product.sort_order = item["sort_order"]
            product.show_in_catalog = item["show_in_catalog"]
            product.extra_data = item["extra_data"]

        existing = {tr.language.value: tr for tr in product.translations}
        for lang_code, payload in item["translations"].items():
            translation = existing.get(lang_code)
            if translation is None:
                translation = ProductTranslation(product=product, language=Language(lang_code))
                session.add(translation)
                translation.name = payload["name"]
                translation.description = payload["description"]
                continue
            if not translation.name:
                translation.name = payload["name"]
            if not translation.description:
                translation.description = payload["description"]


async def sync_product_copy_once(session: AsyncSession) -> None:
    marker = await session.scalar(select(Setting).where(Setting.key == _PRODUCT_COPY_SYNC_SETTING_KEY))
    if marker is not None and marker.value == _PRODUCT_COPY_SYNC_VERSION:
        return

    for product_code, translations in _PRODUCT_TRANSLATION_OVERRIDES.items():
        product = await session.scalar(select(Product).where(Product.code == product_code))
        if product is None:
            continue

        existing = {tr.language.value: tr for tr in product.translations}
        for lang_code, payload in translations.items():
            translation = existing.get(lang_code)
            if translation is None:
                translation = ProductTranslation(product=product, language=Language(lang_code))
                session.add(translation)
            if "name" in payload:
                translation.name = payload["name"]
            if "description" in payload:
                translation.description = payload["description"]

    if marker is None:
        marker = Setting(key=_PRODUCT_COPY_SYNC_SETTING_KEY)
        session.add(marker)
    marker.value = _PRODUCT_COPY_SYNC_VERSION
    marker.value_type = "string"
    marker.description = "One-time product copy sync marker"


async def seed_payment_methods(session: AsyncSession) -> None:
    for item in get_default_payment_methods():
        payment = await session.scalar(select(PaymentMethod).where(PaymentMethod.code == item["code"]))
        if payment is None:
            payment = PaymentMethod(code=item["code"])
            session.add(payment)
            payment.provider_type = PaymentProviderType(item["provider_type"])
            payment.admin_title = item["admin_title"]
            payment.credentials = item["credentials"]
            payment.sort_order = item["sort_order"]
            payment.is_active = True

        existing = {tr.language.value: tr for tr in payment.translations}
        for lang_code, payload in item["translations"].items():
            translation = existing.get(lang_code)
            if translation is None:
                translation = PaymentMethodTranslation(payment_method=payment, language=Language(lang_code))
                session.add(translation)
                translation.title = payload["title"]
                translation.instructions = payload["instructions"]
                continue
            if not translation.title:
                translation.title = payload["title"]
            if not translation.instructions:
                translation.instructions = payload["instructions"]


async def seed_texts(session: AsyncSession, force_codes: set[str] | None = None) -> None:
    for code, payload in DEFAULT_TEXTS.items():
        force_restore = force_codes is not None and code in force_codes
        entry = await session.scalar(select(TextEntry).where(TextEntry.code == code))
        if entry is None:
            entry = TextEntry(code=code)
            session.add(entry)

        entry.group_name = payload["group"]
        entry.description = payload["description"]

        existing = {tr.language.value: tr for tr in entry.translations}
        for lang_code, value in payload["translations"].items():
            translation = existing.get(lang_code)
            if translation is None:
                translation = TextTranslation(text_entry=entry, language=Language(lang_code))
                session.add(translation)
                translation.value = value
                continue
            replaceable_default = _REPLACEABLE_TEXT_DEFAULTS.get(code, {}).get(lang_code)
            if force_restore or _should_replace_seed_text(translation.value, replaceable_default):
                translation.value = value


async def seed_layouts(session: AsyncSession, settings: Settings, force_codes: set[str] | None = None) -> None:
    replacement_map = {
        "__SUPPORT_URL__": settings.support_url,
        "__ABOUT_URL__": settings.about_url,
        "__REVIEW_URL__": settings.review_url,
    }

    for item in DEFAULT_LAYOUTS:
        force_restore = force_codes is not None and item["code"] in force_codes
        layout = await session.scalar(select(Layout).where(Layout.code == item["code"]))
        if layout is None:
            layout = Layout(code=item["code"])
            session.add(layout)
            layout.title = item["title"]
            layout.scope = item["scope"]
            layout.is_active = True
        elif force_restore:
            layout.title = item["title"]
            layout.scope = item["scope"]
            layout.is_active = True

        existing_buttons = {button.code: button for button in layout.buttons}
        for button_data in item["buttons"]:
            button = existing_buttons.get(button_data["code"])
            if button is None:
                button = LayoutButton(layout=layout, code=button_data["code"])
                session.add(button)
                button.action_type = ButtonActionType(button_data["action_type"])
                button.action_value = replacement_map.get(button_data["action_value"], button_data["action_value"])
                button.style = button_data["style"]
                button.row_index = button_data["row_index"]
                button.sort_order = button_data["sort_order"]
                button.is_active = True
            else:
                if force_restore or not button.action_value:
                    button.action_type = ButtonActionType(button_data["action_type"])
                    button.action_value = replacement_map.get(button_data["action_value"], button_data["action_value"])
                if force_restore or not button.style:
                    button.style = button_data["style"]
                if force_restore:
                    button.row_index = button_data["row_index"]
                    button.sort_order = button_data["sort_order"]
                    button.is_active = True

            existing_translations = {tr.language.value: tr for tr in button.translations}
            for lang_code, text in button_data["translations"].items():
                translation = existing_translations.get(lang_code)
                if translation is None:
                    translation = LayoutButtonTranslation(button=button, language=Language(lang_code))
                    session.add(translation)
                    translation.text = text
                    continue
                replaceable_default = _REPLACEABLE_LAYOUT_DEFAULTS.get((item["code"], button_data["code"]), {}).get(lang_code)
                if force_restore or _should_replace_seed_text(translation.text, replaceable_default):
                    translation.text = text


async def sync_legacy_ui_once(session: AsyncSession, settings: Settings) -> None:
    marker = await session.scalar(select(Setting).where(Setting.key == _LEGACY_UI_SYNC_SETTING_KEY))
    if marker is not None and marker.value == _LEGACY_UI_SYNC_VERSION:
        return

    await seed_texts(session, force_codes=set(DEFAULT_TEXTS))
    await seed_layouts(session, settings, force_codes={item["code"] for item in DEFAULT_LAYOUTS})

    if marker is None:
        marker = Setting(key=_LEGACY_UI_SYNC_SETTING_KEY)
        session.add(marker)
    marker.value = _LEGACY_UI_SYNC_VERSION
    marker.value_type = "string"
    marker.description = "One-time legacy UI sync marker"


async def sync_multicard_payment_copy_once(session: AsyncSession) -> None:
    marker = await session.scalar(select(Setting).where(Setting.key == _MULTICARD_TEXT_SYNC_SETTING_KEY))
    if marker is not None and marker.value == _MULTICARD_TEXT_SYNC_VERSION:
        return

    for code, translations in _MULTICARD_TEXT_OVERRIDES.items():
        entry = await session.scalar(select(TextEntry).where(TextEntry.code == code))
        payload = DEFAULT_TEXTS.get(code, {})
        if entry is None:
            entry = TextEntry(code=code)
            entry.group_name = payload.get("group", "user")
            entry.description = payload.get("description", "")
            session.add(entry)
            await session.flush()
        else:
            if payload:
                entry.group_name = payload.get("group", entry.group_name)
                entry.description = payload.get("description", entry.description)

        existing = {tr.language.value: tr for tr in entry.translations}
        for lang_code, value in translations.items():
            translation = existing.get(lang_code)
            if translation is None:
                translation = TextTranslation(text_entry=entry, language=Language(lang_code))
                session.add(translation)
            translation.value = value

    if marker is None:
        marker = Setting(key=_MULTICARD_TEXT_SYNC_SETTING_KEY)
        session.add(marker)
    marker.value = _MULTICARD_TEXT_SYNC_VERSION
    marker.value_type = "string"
    marker.description = "One-time Multicard checkout text sync marker"


async def sync_telegram_payment_copy_once(session: AsyncSession) -> None:
    marker = await session.scalar(select(Setting).where(Setting.key == _TELEGRAM_PAYMENT_SYNC_SETTING_KEY))
    if marker is not None and marker.value == _TELEGRAM_PAYMENT_SYNC_VERSION:
        return

    for code, translations in _TELEGRAM_PAYMENT_TEXT_OVERRIDES.items():
        entry = await session.scalar(select(TextEntry).where(TextEntry.code == code))
        payload = DEFAULT_TEXTS.get(code, {})
        if entry is None:
            entry = TextEntry(code=code)
            entry.group_name = payload.get("group", "user")
            entry.description = payload.get("description", "")
            session.add(entry)
            await session.flush()
        else:
            if payload:
                entry.group_name = payload.get("group", entry.group_name)
                entry.description = payload.get("description", entry.description)

        existing = {tr.language.value: tr for tr in entry.translations}
        for lang_code, value in translations.items():
            translation = existing.get(lang_code)
            if translation is None:
                translation = TextTranslation(text_entry=entry, language=Language(lang_code))
                session.add(translation)
            translation.value = value

    if marker is None:
        marker = Setting(key=_TELEGRAM_PAYMENT_SYNC_SETTING_KEY)
        session.add(marker)
    marker.value = _TELEGRAM_PAYMENT_SYNC_VERSION
    marker.value_type = "string"
    marker.description = "One-time Telegram Payments text sync marker"


async def seed_product_payment_links(session: AsyncSession) -> None:
    if await session.scalar(select(ProductPaymentMethod.id).limit(1)) is not None:
        return

    products = {row.code: row for row in (await session.scalars(select(Product))).all()}
    payments = {row.code: row for row in (await session.scalars(select(PaymentMethod))).all()}

    link_map = {
        "chatgpt_plus_month": ["click", "card", "usdt_trc20"],
        "capcut_pro_month": ["click", "card", "usdt_trc20"],
        "grok_template": ["click", "card", "usdt_trc20"],
        "adobe_template": ["click", "card", "usdt_trc20"],
    }

    for product_code, payment_codes in link_map.items():
        product = products.get(product_code)
        if product is None:
            continue
        for index, payment_code in enumerate(payment_codes, start=1):
            payment = payments.get(payment_code)
            if payment is None:
                continue
            link = ProductPaymentMethod(product=product, payment_method=payment)
            session.add(link)
            link.sort_order = index * 10

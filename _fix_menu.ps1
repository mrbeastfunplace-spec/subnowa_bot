$path = "app.py"
$content = Get-Content -Path $path -Raw -Encoding UTF8

$ruMainPattern = '(?s)"ru"\s*:\s*\{\s*"choose_language"\s*:\s*"[^"]*",\s*(?:.|\r|\n)*?\s*"subscriptions_title"\s*:\s*"[^"]*",'
$ruMainReplacement = @"
"ru": {
        "choose_language": "Выберите язык",
        "main_title": "💮 Добро пожаловать в\nS U B N O V A",
        "main_text": (
            "│ — удобный доступ к цифровым сервисам без лишних сложностей.\n\n"
            "🔥 Здесь вы можете подключить:\n"
            "◻️ ChatGPT Plus / Pro\n"
            "⏺️ CapCut Pro\n"
            "✖️ Grok\n"
            "🅰️ Adobe и другие сервисы\n\n"
            "⚡ Всё максимально просто:\n"
            "— выбрали сервис\n"
            "— оформили\n"
            "— получили доступ\n\n"
            "💡 Без лишних действий и с поддержкой на каждом этапе.\n\n"
            "Почему выбирают нас?\n"
            "✅ Быстрое подключение\n"
            "✅ Проверенные решения\n"
            "✅ Поддержка 24/7\n\n"
            "🌐 <a href='{ABOUT_URL}'>Сайт</a>\n"
            "💬 <a href='{REVIEW_URL}'>Отзывы</a>\n\n"
            "👇 Выберите нужный раздел ниже 👇"
        ),
        "subscriptions_title": "Выберите сервис",
"@
$content = [regex]::Replace($content, $ruMainPattern, $ruMainReplacement, 1)

$content = [regex]::Replace($content, '"btn_subscriptions"\s*:\s*"[^"]*"', '"btn_subscriptions": "Подписки/тарифы"', 1)
$content = [regex]::Replace($content, '"btn_profile"\s*:\s*"[^"]*"', '"btn_profile": "Профиль"', 1)
$content = [regex]::Replace($content, '"btn_languages"\s*:\s*"[^"]*"', '"btn_languages": "Языки"', 1)
$content = [regex]::Replace($content, '"btn_support"\s*:\s*"[^"]*"', '"btn_support": "Задать вопрос"', 1)
$content = [regex]::Replace($content, '"btn_about"\s*:\s*"[^"]*"', '"btn_about": "О нас"', 1)
$content = [regex]::Replace($content, '"btn_faq"\s*:\s*"[^"]*"', '"btn_faq": "FAQ"', 1)
$content = [regex]::Replace($content, '"btn_history"\s*:\s*"[^"]*"', '"btn_history": "История заказов"', 1)
$content = [regex]::Replace($content, '"btn_promo"\s*:\s*"[^"]*"', '"btn_promo": "Промокод"', 1)

$content = $content -replace ',\s*icon_custom_emoji_id=EMOJI_ID_BACK', ''
$content = $content -replace '\r?\n\s*icon_custom_emoji_id=EMOJI_ID_BACK\s*\r?\n', "`r`n"

Set-Content -Path $path -Value $content -Encoding UTF8

$path = "app.py"
$c = Get-Content -Path $path -Raw -Encoding UTF8

if ($c -notmatch "import os") {
  $c = $c -replace "import asyncio`r?`n", "import asyncio`r`nimport os`r`n"
}
if ($c -notmatch "FSInputFile") {
  $c = $c -replace "CallbackQuery,`r?`n", "CallbackQuery,`r`n    FSInputFile,`r`n"
}
if ($c -notmatch "CLICK_QR_IMAGE_PATH") {
  $c = $c -replace "USDT_TRC20_ADDRESS = \"TUr3m7sAWpiysQs5S1jQkbxcvJARqAD8Rs\"`r?`n", "USDT_TRC20_ADDRESS = \"TUr3m7sAWpiysQs5S1jQkbxcvJARqAD8Rs\"`r`nCLICK_QR_IMAGE_PATH = r\"C:/bot/subnowa_bot/media/click.png.jpg\"`r`n"
}

$c = $c.Replace('"chatgpt_menu_text": "ChatGPT Plus/Pro\n\nВыберите тариф ниже 👇",', '"chatgpt_menu_text": "<tg-emoji emoji-id=''5359726582447487916''>🤖</tg-emoji> ChatGPT Plus/Pro\n\nВыберите тариф ниже 👇",')
$c = $c.Replace('"capcut_menu_text": "CapCut Pro\n\nВыберите тариф ниже 👇",', '"capcut_menu_text": "<tg-emoji emoji-id=''5364339557712020484''>🎬</tg-emoji> CapCut Pro\n\nВыберите тариф ниже 👇",')
$c = $c.Replace('"chatgpt_menu_text": "ChatGPT Plus/Pro\n\nTarifni tanlang 👇",', '"chatgpt_menu_text": "<tg-emoji emoji-id=''5359726582447487916''>🤖</tg-emoji> ChatGPT Plus/Pro\n\nTarifni tanlang 👇",')
$c = $c.Replace('"capcut_menu_text": "CapCut Pro\n\nTarifni tanlang 👇",', '"capcut_menu_text": "<tg-emoji emoji-id=''5364339557712020484''>🎬</tg-emoji> CapCut Pro\n\nTarifni tanlang 👇",')
$c = $c.Replace('"chatgpt_menu_text": "ChatGPT Plus/Pro\n\nChoose a tariff below 👇",', '"chatgpt_menu_text": "<tg-emoji emoji-id=''5359726582447487916''>🤖</tg-emoji> ChatGPT Plus/Pro\n\nChoose a tariff below 👇",')
$c = $c.Replace('"capcut_menu_text": "CapCut Pro\n\nChoose a tariff below 👇",', '"capcut_menu_text": "<tg-emoji emoji-id=''5364339557712020484''>🎬</tg-emoji> CapCut Pro\n\nChoose a tariff below 👇",')

$c = $c.Replace('"Ваш заказ подтверждён.\n\n"', '"✅ Ваш заказ подтверждён.\n\n"')
$c = $c.Replace('После подтверждения', 'После ✅ подтверждения')
$c = $c.Replace('"Buyurtmangiz tasdiqlandi.\n\n"', '"✅ Buyurtmangiz tasdiqlandi.\n\n"')
$c = $c.Replace('Tasdiqlangandan', '✅ Tasdiqlangandan')
$c = $c.Replace('"Your order has been approved.\n\n"', '"✅ Your order has been approved.\n\n"')
$c = $c.Replace('After confirmation', 'After ✅ confirmation')

$c = $c.Replace('text=t(user_id, "btn_profile"),`r`n                    callback_data="open_profile"', 'text=t(user_id, "btn_profile"),`r`n                    callback_data="open_profile",`r`n                    icon_custom_emoji_id=EMOJI_ID_PROFILE')
$c = $c.Replace('text=t(user_id, "btn_languages"),`r`n                    callback_data="open_languages"', 'text=t(user_id, "btn_languages"),`r`n                    callback_data="open_languages",`r`n                    icon_custom_emoji_id=EMOJI_ID_GLOBE')
$c = $c.Replace('[InlineKeyboardButton(text=t(user_id, "btn_support"), url=SUPPORT_URL)]', '[InlineKeyboardButton(text=t(user_id, "btn_support"), url=SUPPORT_URL, icon_custom_emoji_id=EMOJI_ID_SUPPORT)]')
$c = $c.Replace('InlineKeyboardButton(text=t(user_id, "btn_about"), url=ABOUT_URL),', 'InlineKeyboardButton(text=t(user_id, "btn_about"), url=ABOUT_URL, icon_custom_emoji_id=EMOJI_ID_GLOBE),')
$c = $c.Replace('InlineKeyboardButton(text=t(user_id, "btn_faq"), callback_data="open_faq"),', 'InlineKeyboardButton(text=t(user_id, "btn_faq"), callback_data="open_faq", icon_custom_emoji_id=EMOJI_ID_SUPPORT),')

$old = @"
    await safe_edit_text(
        callback,
        t(callback.from_user.id, \"pay_click_text\").format(
            order_number=order_number,
            product_name=product_name,
            price_uzs=format_price_uzs(price_uzs),
            click_number=CLICK_NUMBER
        ),
        reply_markup=payment_back_menu_kb(callback.from_user.id, order_number)
    )
"@

$new = @"
    click_text = t(callback.from_user.id, \"pay_click_text\").format(
        order_number=order_number,
        product_name=product_name,
        price_uzs=format_price_uzs(price_uzs),
        click_number=CLICK_NUMBER
    )

    if os.path.exists(CLICK_QR_IMAGE_PATH):
        await callback.message.answer_photo(
            photo=FSInputFile(CLICK_QR_IMAGE_PATH),
            caption=click_text,
            reply_markup=payment_back_menu_kb(callback.from_user.id, order_number)
        )
    else:
        await safe_edit_text(
            callback,
            click_text,
            reply_markup=payment_back_menu_kb(callback.from_user.id, order_number)
        )
"@
$c = $c.Replace($old, $new)

$c = $c.Replace('await safe_edit_text(callback, "Заявка подтверждена.")', 'await safe_edit_text(callback, "✅ Заявка подтверждена.")')
$c = $c.Replace('await safe_edit_text(callback, "Оплата подтверждена, но свободных аккаунтов нет.")', 'await safe_edit_text(callback, "✅ Оплата подтверждена, но свободных аккаунтов нет.")')
$c = $c.Replace('await safe_edit_text(callback, "Оплата подтверждена.")', 'await safe_edit_text(callback, "✅ Оплата подтверждена.")')

Set-Content -Path $path -Value $c -Encoding UTF8

import logging

import config


async def notify_stock_change(bot, product: dict, old_quantity: float, new_quantity: float):
    """Mahsulot miqdori kamaygandan keyin chaqiriladi.

    - Agar mahsulot butunlay tugasa (0 dona qolsa) - alohida ogohlantirish.
    - Agar xodim belgilagan ogohlantirish chegarasidan pastga tushsa - ogohlantirish.
    Xabar faqat chegaradan "o'tilgan" paytda yuboriladi (spam bo'lmasligi uchun),
    ya'ni oldingi miqdor chegaradan yuqori, yangisi esa past yoki teng bo'lsa.
    """
    if not config.ADMIN_IDS:
        return

    threshold = product.get("alert_quantity")
    messages = []

    if new_quantity <= 0 < old_quantity:
        messages.append(f"❌ <b>{product['name']}</b> tugadi! Skladda 0 dona qoldi.")
    elif threshold is not None and new_quantity <= threshold < old_quantity:
        messages.append(
            f"⚠️ <b>{product['name']}</b> kamayib qoldi: {new_quantity:.0f} dona qoldi "
            f"(belgilangan chegara: {threshold:.0f} dona). Sotib olish kerak!"
        )

    if not messages:
        return

    for admin_id in config.ADMIN_IDS:
        for text in messages:
            try:
                await bot.send_message(admin_id, text, parse_mode="HTML")
            except Exception as e:
                logging.warning(f"Ogohlantirish yuborib bo'lmadi ({admin_id}): {e}")

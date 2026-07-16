import logging

import config
import database as db


async def notify_stock_change(bot, product: dict, old_quantity: float, new_quantity: float,
                               also_notify_chat_id: int = None):
    """Mahsulot miqdori kamaygandan keyin chaqiriladi.

    - Agar mahsulot butunlay tugasa (0 dona qolsa) - alohida ogohlantirish.
    - Agar xodim belgilagan ogohlantirish chegarasidan pastga tushsa - ogohlantirish.
    Xabar faqat chegaradan "o'tilgan" paytda yuboriladi (spam bo'lmasligi uchun),
    ya'ni oldingi miqdor chegaradan yuqori, yangisi esa past yoki teng bo'lsa.

    Xabar config.ADMIN_IDS'dagilarga, shuningdek amalni bajargan foydalanuvchiga
    ham yuboriladi (also_notify_chat_id) - shunda ADMIN_IDS noto'g'ri sozlangan
    yoki admin botga hali /start bosmagan bo'lsa ham, harakatni bajargan odam
    ogohlantirishni ko'radi.
    """
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

    recipients = set(config.ADMIN_IDS)
    if also_notify_chat_id:
        recipients.add(also_notify_chat_id)
    if not recipients:
        return

    for chat_id in recipients:
        for text in messages:
            try:
                await bot.send_message(chat_id, text, parse_mode="HTML")
            except Exception as e:
                logging.warning(f"Ogohlantirish yuborib bo'lmadi ({chat_id}): {e}")


def build_customer_reminder_text(debt: dict) -> str:
    """Mijozga to'g'ridan-to'g'ri yuboriladigan qarz eslatmasi matni."""
    days_ago = debt.get("days_ago")
    days_line = f"Bu qarz <b>{days_ago} kundan</b> beri to'lanmagan.\n" if days_ago is not None else ""
    description = f" ({debt['description']})" if debt.get("description") else ""
    return (
        f"🔔 Assalomu alaykum, <b>{debt['customer_name']}</b>!\n\n"
        f"Sizda <b>{debt['amount']:.0f} so'm</b> miqdorida qarzdorlik mavjud{description}.\n"
        f"{days_line}"
        f"Iltimos, imkon qadar tezroq to'lovni amalga oshirishingizni so'raymiz.\n"
        f"Savolingiz bo'lsa, biz bilan bog'laning. Rahmat! 🙏"
    )


async def send_customer_debt_reminder(bot, debt: dict) -> bool:
    """Mijozga bevosita eslatma yuboradi (agar u start-link orqali bog'langan bo'lsa).
    Muvaffaqiyatli yuborilsa True, aks holda False qaytaradi."""
    if not debt.get("customer_chat_id"):
        return False
    try:
        await bot.send_message(
            debt["customer_chat_id"],
            build_customer_reminder_text(debt),
            parse_mode="HTML",
        )
        return True
    except Exception as e:
        logging.warning(f"Mijozga eslatma yuborib bo'lmadi (debt {debt['id']}): {e}")
        return False


async def send_debt_reminders(bot, days_threshold: int = 3):
    """Har kuni bir marta chaqiriladi (main.py'dagi fon vazifadan).

    Har bir muddati o'tgan qarz uchun:
    - agar mijoz start-link orqali botga ulangan bo'lsa - unga to'g'ridan-to'g'ri eslatma yuboriladi;
    - shu bilan birga ADMIN_IDS'dagi do'kon xodimlariga ham umumiy ro'yxat yuboriladi
      (mijoz hali ulanmagan bo'lsa ham, ular ko'rib qo'ng'iroq qilishi mumkin).
    """
    overdue = await db.get_overdue_debts(days=days_threshold)
    if not overdue:
        return

    for d in overdue:
        await send_customer_debt_reminder(bot, d)

    if not config.ADMIN_IDS:
        return

    lines = [
        f"• {d['customer_name']} ({d['phone']}) — {d['amount']:.0f} so'm, "
        f"{d['days_ago']} kundan beri qarzda"
        + (" 🔗" if d.get("customer_chat_id") else "")
        for d in overdue
    ]
    text = (
        f"🔔 <b>Qarzdorlar eslatmasi</b>\n"
        f"{days_threshold}+ kundan beri to'lanmagan qarzlar:\n\n" + "\n".join(lines) +
        "\n\n🔗 belgisi — mijozga eslatma avtomatik yuborildi."
    )

    for chat_id in config.ADMIN_IDS:
        try:
            await bot.send_message(chat_id, text, parse_mode="HTML")
        except Exception as e:
            logging.warning(f"Qarz eslatmasini yuborib bo'lmadi ({chat_id}): {e}")

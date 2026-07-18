import logging
from datetime import datetime

import database as db
import keyboards as kb


async def notify_stock_change(bot, shop_id: int, product: dict, old_quantity: float, new_quantity: float,
                               also_notify_chat_id: int = None):
    """Mahsulot miqdori kamaygandan keyin chaqiriladi.

    - Agar mahsulot butunlay tugasa (0 dona qolsa) - alohida ogohlantirish.
    - Agar xodim belgilagan ogohlantirish chegarasidan pastga tushsa - ogohlantirish.
    Xabar faqat chegaradan "o'tilgan" paytda yuboriladi (spam bo'lmasligi uchun),
    ya'ni oldingi miqdor chegaradan yuqori, yangisi esa past yoki teng bo'lsa.

    Bu - shu DO'KONGA tegishli ogohlantirish, shuning uchun faqat shop_id'ga
    (do'kon egasining o'ziga) yuboriladi. Bosh admin (config.ADMIN_IDS) endi
    o'z do'koniga ega emas, shuning uchun sklad ogohlantirishlarini olmaydi.
    also_notify_chat_id - amalni bajargan xodimning chat_id'si (odatda shop_id
    bilan bir xil, lekin kelajakda bir nechta xodim bo'lsa ham xabar yetib borsin
    uchun qoldirildi).
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

    recipients = {shop_id}
    if also_notify_chat_id:
        recipients.add(also_notify_chat_id)

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

    Endi har bir DO'KON alohida ko'rib chiqiladi (bir necha mustaqil do'kon
    bor bo'lgani uchun): har bir do'kon egasi faqat O'Z qarzdorlari haqida
    xabar oladi, boshqa do'konning qarzdorlari haqida hech narsa ko'rmaydi.

    Har bir muddati o'tgan qarz uchun:
    - agar mijoz start-link orqali botga ulangan bo'lsa - unga to'g'ridan-to'g'ri eslatma yuboriladi;
    - shu bilan birga o'sha do'kon egasiga ham umumiy ro'yxat yuboriladi
      (mijoz hali ulanmagan bo'lsa ham, u ko'rib qo'ng'iroq qilishi mumkin).

    Bosh admin (config.ADMIN_IDS) endi hech qanday do'konga ega emas, shuning
    uchun bu xabarlarni olmaydi - uning yagona vazifasi do'kon egalarini
    boshqarish.
    """
    owner_ids = await db.get_owner_ids()
    for shop_id in owner_ids:
        overdue = await db.get_overdue_debts(shop_id, days=days_threshold)
        if not overdue:
            continue

        for d in overdue:
            await send_customer_debt_reminder(bot, d)

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
        try:
            await bot.send_message(shop_id, text, parse_mode="HTML")
        except Exception as e:
            logging.warning(f"Qarz eslatmasini yuborib bo'lmadi (shop {shop_id}): {e}")


# ---------- 5-BOSQICH: KUNLIK HISOBOT (TELEGRAM) ----------
# DB'dagi statistika (database.get_daily_stats) bitta do'kon egasiga chiroyli
# formatda yuboriladigan xabarga aylantiriladi. Avtomatik jo'natish (har kuni
# belgilangan vaqtda) va yoqish/o'chirish sozlamasi 6-7-bosqichda qo'shiladi -
# bu yerda faqat "bitta shop_id uchun hisobotni tuzish va yuborish" bor,
# shuning uchun uni istalgan joydan (masalan "🔄 Bugungi hisobot" tugmasidan
# qo'lda ham) chaqirish mumkin bo'ladi.

def _format_date_uz(date_str: str) -> str:
    """'YYYY-MM-DD' ni '01.02.2025' ko'rinishiga o'tkazadi. Format noto'g'ri
    bo'lsa (kutilmagan holat) - o'zgarishsiz qaytaradi."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return date_str


def build_daily_report_text(stats: dict, owner: dict = None) -> str:
    """database.get_daily_stats() natijasini o'qishga qulay Telegram xabariga
    aylantiradi. owner - db.get_owner() natijasi (ixtiyoriy) - do'kon nomi
    bor bo'lsa sarlavhaga qo'shiladi."""
    shop_name = (owner or {}).get("shop_name")
    title_suffix = f" — {shop_name}" if shop_name else ""

    balance = stats["income_total"] - stats["expense_total"]

    if stats["sales_count"] == 0:
        sales_line = "Bugun hali savdo bo'lmadi."
    else:
        sales_line = (
            f"🛒 Savdo: <b>{stats['sales_count']}</b> ta chek — "
            f"{stats['sales_total']:.0f} so'm\n"
            f"💰 Foyda: <b>{stats['profit_total']:.0f} so'm</b>"
        )

    return (
        f"📅 <b>Kunlik hisobot — {_format_date_uz(stats['date'])}</b>{title_suffix}\n\n"
        f"{sales_line}\n\n"
        f"💵 Kirim (jami): {stats['income_total']:.0f} so'm\n"
        f"💸 Chiqim (jami): {stats['expense_total']:.0f} so'm\n"
        f"📈 Kunlik balans: <b>{balance:.0f} so'm</b>\n\n"
        f"📦 Sotilgan tovar tannarxi: {stats['stock_cost_out']:.0f} so'm\n"
        f"📦 Joriy sklad qiymati: {stats['current_stock_value']:.0f} so'm"
    )


async def send_daily_report(bot, shop_id: int) -> bool:
    """Bitta do'kon egasiga bugungi kunlik hisobotni yuboradi.
    Muvaffaqiyatli yuborilsa True, aks holda (masalan foydalanuvchi botni
    bloklagan bo'lsa) False qaytaradi - shu bilan send_debt_reminders va
    send_subscription_reminders'dagi patternga mos keladi."""
    stats = await db.get_daily_stats(shop_id)
    owner = await db.get_owner(shop_id)
    text = build_daily_report_text(stats, owner)
    try:
        await bot.send_message(shop_id, text, parse_mode="HTML")
        return True
    except Exception as e:
        logging.warning(f"Kunlik hisobotni yuborib bo'lmadi (shop {shop_id}): {e}")
        return False


async def send_daily_reports_to_all(bot):
    """Har kuni belgilangan vaqtda (main.py'dagi _daily_report_loop) chaqiriladi -
    BARCHA do'kon egalariga, birma-bir, o'zining kunlik hisobotini yuboradi.

    KUNLIK HISOBOT - 7-BOSQICH: yuborishdan oldin har bir ega uchun
    db.get_daily_report_enabled() tekshiriladi - agar owner "🔔 Kunlik
    hisobot" bo'limidan o'zi o'chirib qo'ygan bo'lsa, unga umuman
    yuborilmaydi (boshqa egalarga esa davom etadi)."""
    owner_ids = await db.get_owner_ids()
    for shop_id in owner_ids:
        if not await db.get_daily_report_enabled(shop_id):
            continue
        await send_daily_report(bot, shop_id)


# ---------- 8-BOSQICH: OBUNA MUDDATI ESLATMALARI ----------
# Muddat tugashiga necha kun qolganda eslatma yuborilishi kerak. 0 - aynan
# tugaydigan kunning o'zi (subscription_until = bugun, ya'ni ertadan
# boshlab muhlat/bloklash boshlanadi).
SUBSCRIPTION_REMINDER_DAYS = (7, 3, 0)


def build_subscription_reminder_text(access: dict) -> str:
    """Do'kon egasiga yuboriladigan obuna muddati eslatmasi matni.
    access - db.get_owner_subscription_access() natijasi (days_left shu
    yerda SUBSCRIPTION_REMINDER_DAYS'dan biriga teng bo'lishi kerak)."""
    days_left = access["days_left"]
    if days_left == 0:
        return (
            "⏰ <b>Obunangiz bugun tugaydi!</b>\n\n"
            "Botdan uzluksiz foydalanishni davom ettirish uchun bugun uzaytiring. "
            f"Aks holda ertadan boshlab {db.SUBSCRIPTION_GRACE_DAYS} kunlik muhlat "
            "davomida hali kirish imkoni bo'ladi, so'ng bot vaqtincha bloklanadi."
        )
    return (
        f"⏰ <b>Obunangiz tugashiga {days_left} kun qoldi.</b>\n\n"
        "Botdan uzilishsiz foydalanishni davom ettirish uchun oldindan uzaytirib qo'yishingiz mumkin."
    )


async def send_subscription_reminders(bot):
    """Har kuni bir marta chaqiriladi (main.py'dagi fon vazifadan, xuddi
    send_debt_reminders kabi). Har bir do'kon egasi uchun ALOHIDA ko'rib
    chiqiladi va obuna muddati tugashiga 7 kun, 3 kun qolganda hamda aynan
    tugaydigan kunning o'zida (0 kun qolganda) avtomatik eslatma yuboradi.

    Faqat hali FAOL (trial/active) holatdagi egalarga yuboriladi - obunasi
    allaqachon o'tib ketgan (expired/blocked) egalar buning o'rniga har safar
    botga kirishga uringanda access_control.py'dagi bloklash ekranini ko'radi,
    shuning uchun ularga bu yerdan qayta eslatma yuborilmaydi.

    Bosh admin (config.ADMIN_IDS) o'z do'koniga ega emas, shuning uchun bu
    xabarlarni olmaydi."""
    owner_ids = await db.get_owner_ids()
    for owner_id in owner_ids:
        access = await db.get_owner_subscription_access(owner_id)
        if not access or not access["allowed"] or access["status"] not in ("trial", "active"):
            continue
        if access["days_left"] not in SUBSCRIPTION_REMINDER_DAYS:
            continue

        try:
            await bot.send_message(
                owner_id,
                build_subscription_reminder_text(access),
                parse_mode="HTML",
                reply_markup=kb.blocked_menu(),
            )
        except Exception as e:
            logging.warning(f"Obuna eslatmasini yuborib bo'lmadi (owner {owner_id}): {e}")

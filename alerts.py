"""Bot bo'ylab turli ogohlantirish/eslatma xabarlarini yuboradigan modul:

- notify_stock_change        - sklad qoldig'i ogohlantirish chegarasidan
                                (alert_quantity) pastga tushganda do'kon
                                egasiga (va kerak bo'lsa amalni bajargan
                                xodimga) darhol xabar beradi.
- evaluate_sale_suspicions    - bitta savdo (chek) shubhali belgilarga mos
                                keladimi tekshiradi (manfiy qoldiq, tannarxdan
                                past sotish, katta chegirma, katta miqdor,
                                ish vaqtidan tashqari, xodim kunlik limiti).
- evaluate_expense_suspicions - bitta "chiqim" yozuvi uchun xuddi shunday
                                tekshiruv (katta summa, ish vaqti, kunlik limit).
- send_suspicious_alert       - yuqoridagi ikkisi topgan belgilarni do'kon
                                egasiga Telegram orqali yuboradi (agar owner
                                o'zi shu ogohlantirishni o'chirib qo'ymagan bo'lsa).
- send_customer_debt_reminder - bitta qarz yozuvi bo'yicha mijozning o'ziga
                                (agar u start-link orqali botga ulangan bo'lsa)
                                to'g'ridan-to'g'ri eslatma yuboradi.
- send_debt_reminders         - BARCHA do'konlar bo'yicha: egaga muddati
                                o'tgan qarzlar ro'yxatini, mijozlarga esa
                                (bog'langan bo'lsa) to'g'ridan-to'g'ri eslatma.
- send_subscription_reminders - BARCHA do'kon egalariga obuna muddati
                                tugashiga 7/3/0 kun qolganda eslatma yuboradi.
- send_daily_reports_to_all   - BARCHA do'konlarga (kunlik hisobot yoqilgan
                                bo'lsa) shu kunlik statistikani yuboradi.

DIQQAT: bu funksiyalar bir nechta do'kon/mijoz bo'yicha aylanadi - bitta
do'kon/mijozga xabar yuborishda xato chiqsa (masalan foydalanuvchi botni
bloklagan), shu birgina qatnashchi o'tkazib yuboriladi va qolganlar uchun
tsikl davom etadi (bitta muvaffaqiyatsizlik butun funksiyani to'xtatib
qo'ymasligi kerak - main.py'dagi fon tsikllari shu funksiyalarni HAR
KUNIGA FAQAT BIR MARTA chaqiradi)."""

import logging
from datetime import datetime, timedelta

import config
import database as db


# ---------- SKLAD QOLDIG'I OGOHLANTIRISHI ----------

async def notify_stock_change(bot, shop_id: int, product: dict, old_quantity: float,
                               new_quantity: float, also_notify_chat_id: int = None):
    """Mahsulotning "ogohlantirish chegarasi" (alert_quantity) bor bo'lsa va
    shu savdo natijasida qoldiq AYNI shu chegaradan PASTGA TUSHGAN bo'lsa
    (avval yuqorida edi, endi past) - do'kon egasiga darhol xabar beradi.

    Faqat "chegarani KESIB O'TGAN" paytda yuboriladi (old_quantity > alert,
    new_quantity <= alert) - aks holda allaqachon kam bo'lgan mahsulot har
    bir keyingi sotuvda qayta-qayta bezovta qilib yubormaydi.

    also_notify_chat_id - agar savdoni sotuvchi (do'kon egasi emas) amalga
    oshirgan bo'lsa, unga ham DARHOL bildirish uchun (ega bilan bir qatorda)."""
    alert_quantity = product.get("alert_quantity")
    if alert_quantity is None:
        return
    if not (old_quantity > alert_quantity >= new_quantity):
        return

    text = (
        f"⚠️ <b>{product['name']}</b> qoldig'i kam qoldi!\n"
        f"Hozirgi qoldiq: <b>{new_quantity:.0f}</b> dona "
        f"(ogohlantirish chegarasi: {alert_quantity:.0f})"
    )

    recipients = {shop_id}
    if also_notify_chat_id:
        recipients.add(also_notify_chat_id)

    for chat_id in recipients:
        try:
            await bot.send_message(chat_id, text, parse_mode="HTML")
        except Exception as e:
            logging.warning(f"Sklad ogohlantirishini ({chat_id}) yuborib bo'lmadi: {e}")


# ---------- SHUBHALI HOLATLAR - TEKSHIRUV ----------

async def evaluate_sale_suspicions(shop_id: int, sale_lines: list, performed_by: int = None) -> list:
    """sale_lines: [{"product": {...}, "quantity": .., "price": ..}, ...]
    (product - SOTUVDAN OLDINGI holat, ya'ni product["quantity"] hali eski).

    Qaytaradi: inson o'qiy oladigan shubhali belgilar ro'yxati (bo'sh bo'lsa
    - shubhali hech narsa topilmagan)."""
    rules = await db.get_suspicious_rules(shop_id)
    flags = []

    for line in sale_lines:
        product = line["product"]
        qty = line["quantity"]
        price = line["price"]
        name = product.get("name", "?")

        # 1) Manfiy qoldiq - chegarasiz, doim yoqilgan.
        remaining = (product.get("quantity") or 0) - qty
        if remaining < 0:
            flags.append(f"❗️ {name}: savdodan keyin qoldiq manfiy bo'lib qoldi ({remaining:.0f})")

        # 2) Tannarxdan past sotish - chegarasiz, doim yoqilgan.
        cost = product.get("price") or 0
        if price < cost:
            flags.append(f"💸 {name}: tannarxdan ({cost:.0f} so'm) past narxda sotildi ({price:.0f} so'm)")

        # 3) G'ayrioddiy katta chegirma.
        sell_price = product.get("sell_price")
        if sell_price and price < sell_price:
            discount_percent = (sell_price - price) / sell_price * 100
            if discount_percent >= rules["discount_percent"]:
                flags.append(
                    f"🔻 {name}: tavsiya etilgan narxdan {discount_percent:.0f}% past sotildi "
                    f"({price:.0f} so'm, tavsiya: {sell_price:.0f} so'm)"
                )

        # 4) Bitta chekda g'ayrioddiy katta miqdor.
        if qty >= rules["sale_quantity"]:
            flags.append(f"📦 {name}: bitta savdoda {qty:.0f} dona sotildi (chegara: {rules['sale_quantity']:.0f})")

    flags.extend(await _evaluate_common_suspicions(shop_id, rules, performed_by))
    return flags


async def evaluate_expense_suspicions(shop_id: int, amount: float, performed_by: int = None) -> list:
    """Bitta "chiqim" yozuvi uchun tekshiruv (katta summa + umumiy qoidalar)."""
    rules = await db.get_suspicious_rules(shop_id)
    flags = []

    if amount >= rules["expense_amount"]:
        flags.append(f"💰 Katta chiqim: {amount:.0f} so'm (chegara: {rules['expense_amount']:.0f} so'm)")

    flags.extend(await _evaluate_common_suspicions(shop_id, rules, performed_by))
    return flags


async def _evaluate_common_suspicions(shop_id: int, rules: dict, performed_by: int = None) -> list:
    """Savdo va chiqim ikkisiga ham tegishli umumiy qoidalar: ish vaqtidan
    tashqari va bitta xodimning kunlik yozuvlar soni."""
    flags = []

    hour = config.now().hour
    if not (rules["work_hour_start"] <= hour < rules["work_hour_end"]):
        flags.append(
            f"🕒 Ish vaqtidan tashqarida bajarildi (soat {hour:02d}:00, "
            f"belgilangan ish vaqti: {rules['work_hour_start']:02d}:00–{rules['work_hour_end']:02d}:00)"
        )

    if performed_by:
        count = await db.count_today_transactions_by_performer(shop_id, performed_by)
        if count > rules["seller_daily_count"]:
            flags.append(
                f"🔁 Xodim bugun {count} marta yozuv kiritdi (chegara: {rules['seller_daily_count']})"
            )

    return flags


async def send_suspicious_alert(bot, shop_id: int, suspicious_flags: list, kind: str):
    """kind - "savdo" | "chiqim" (xabar sarlavhasi uchun). Owner bu
    ogohlantirishni o'zi o'chirib qo'ygan bo'lsa - hech narsa yubormaydi
    (tekshiruv/log baribir davom etadi, faqat Telegram xabari kelmaydi)."""
    if not suspicious_flags:
        return
    enabled = await db.get_suspicious_alert_enabled(shop_id)
    if not enabled:
        return

    text = (
        f"🚨 <b>Shubhali holat aniqlandi ({kind})</b>\n\n"
        + "\n".join(f"• {flag}" for flag in suspicious_flags)
    )
    try:
        await bot.send_message(shop_id, text, parse_mode="HTML")
    except Exception as e:
        logging.warning(f"Shubhali holat ogohlantirishini ({shop_id}) yuborib bo'lmadi: {e}")


# ---------- QARZ ESLATMALARI ----------

async def send_customer_debt_reminder(bot, debt: dict) -> bool:
    """Mijozning o'ziga (agar shaxsiy link orqali botga ulangan bo'lsa)
    to'g'ridan-to'g'ri eslatma yuboradi. Muvaffaqiyatli yuborilsa - qarz
    yozuvidagi so'nggi eslatma vaqtini ham yangilaydi va True qaytaradi."""
    chat_id = debt.get("customer_chat_id")
    if not chat_id:
        return False

    remaining = (debt.get("amount") or 0) - (debt.get("paid_amount") or 0)
    text = (
        "📒 <b>Qarz eslatmasi</b>\n\n"
        f"Sizda <b>{remaining:.0f} so'm</b> qarz mavjud.\n"
        f"Izoh: {debt.get('description') or '-'}"
    )
    try:
        await bot.send_message(chat_id, text, parse_mode="HTML")
    except Exception as e:
        logging.warning(f"Mijozga ({chat_id}) qarz eslatmasini yuborib bo'lmadi: {e}")
        return False

    await db.update_debt_reminder_sent(debt["id"])
    return True


async def send_debt_reminders(bot):
    """Har bir do'kon egasiga FAQAT o'zining muddati o'tgan qarzlari haqida
    ro'yxat yuboradi, va agar shu qarzlardan biriga mijoz o'zi (start-link
    orqali) ulangan bo'lsa - mijozning o'ziga ham
    (DEBT_CUSTOMER_REMINDER_INTERVAL_DAYS kunda bir marta) to'g'ridan-to'g'ri
    eslatma yuboradi."""
    owners = await db.get_owners()
    for owner in owners:
        shop_id = owner["telegram_id"]
        try:
            access = await db.get_owner_subscription_access(shop_id)
            if not access or not access["allowed"]:
                continue

            overdue = await db.get_overdue_debts(shop_id, days=config.DEBT_OVERDUE_DAYS_DEFAULT)
            if not overdue:
                continue

            lines = [
                f"• {d['customer_name']}: {(d['amount'] - (d.get('paid_amount') or 0)):.0f} so'm "
                f"({d['days_ago']} kun o'tgan)"
                for d in overdue
            ]
            text = (
                f"📒 <b>Muddati o'tgan qarzlar</b> ({len(overdue)} ta)\n\n"
                + "\n".join(lines)
            )
            try:
                await bot.send_message(shop_id, text, parse_mode="HTML")
            except Exception as e:
                logging.warning(f"Do'kon egasiga ({shop_id}) qarz eslatmasini yuborib bo'lmadi: {e}")

            for d in overdue:
                if not d.get("customer_chat_id"):
                    continue
                last_sent = d.get("last_reminder_at")
                if last_sent:
                    try:
                        last_dt = datetime.strptime(last_sent, "%Y-%m-%d %H:%M:%S")
                        if config.now() - last_dt < timedelta(days=config.DEBT_CUSTOMER_REMINDER_INTERVAL_DAYS):
                            continue
                    except (TypeError, ValueError):
                        pass
                await send_customer_debt_reminder(bot, d)
        except Exception as e:
            logging.warning(f"Qarz eslatmasi ({shop_id}) uchun umumiy xato: {e}")


# ---------- OBUNA ESLATMALARI ----------

async def send_subscription_reminders(bot):
    """Har bir do'kon egasiga obuna muddati tugashiga aynan 7, 3 yoki 0 kun
    qolganda eslatma yuboradi (main.py bu funksiyani kuniga faqat bir marta
    chaqiradi, shuning uchun bu yerda qayta yuborilmasligini alohida
    tekshirish shart emas)."""
    owners = await db.get_owners()
    for owner in owners:
        shop_id = owner["telegram_id"]
        try:
            access = await db.get_owner_subscription_access(shop_id)
            if not access:
                continue
            if access["status"] not in ("trial", "active"):
                continue
            days_left = access["days_left"]
            if days_left not in (7, 3, 0):
                continue

            if days_left == 0:
                body = "bugun tugaydi"
            else:
                body = f"{days_left} kundan keyin tugaydi"

            text = (
                "⏰ <b>Obuna eslatmasi</b>\n\n"
                f"Obunangiz muddati {body}.\n"
                "Botdan uzluksiz foydalanishni davom ettirish uchun \"💳 Obuna\" "
                "bo'limidan uzaytirib qo'ying."
            )
            try:
                await bot.send_message(shop_id, text, parse_mode="HTML")
            except Exception as e:
                logging.warning(f"Obuna eslatmasini ({shop_id}) yuborib bo'lmadi: {e}")
        except Exception as e:
            logging.warning(f"Obuna eslatmasi ({shop_id}) uchun umumiy xato: {e}")


# ---------- KUNLIK HISOBOT ----------

async def send_daily_reports_to_all(bot):
    """Kunlik hisobotni o'chirib qo'ymagan (va obunasi hozircha faol
    bo'lgan) barcha do'kon egalariga shu kunlik statistikani yuboradi."""
    owners = await db.get_owners()
    for owner in owners:
        shop_id = owner["telegram_id"]
        try:
            access = await db.get_owner_subscription_access(shop_id)
            if not access or not access["allowed"]:
                continue

            enabled = await db.get_daily_report_enabled(shop_id)
            if not enabled:
                continue

            stats = await db.get_daily_stats(shop_id)
            total_debt = await db.get_total_debt(shop_id)

            text = (
                f"📊 <b>Kunlik hisobot</b> ({stats['date']})\n\n"
                f"🧾 Savdolar soni: {stats['sales_count']}\n"
                f"💰 Savdo summasi: {stats['sales_total']:.0f} so'm\n"
                f"📈 Sof foyda: {stats['profit_total']:.0f} so'm\n\n"
                f"💵 Jami kirim: {stats['income_total']:.0f} so'm\n"
                f"💸 Jami chiqim: {stats['expense_total']:.0f} so'm\n\n"
                f"📦 Hozirgi sklad qiymati: {stats['current_stock_value']:.0f} so'm\n"
                f"📒 Umumiy qarzdorlik: {total_debt:.0f} so'm"
            )
            try:
                await bot.send_message(shop_id, text, parse_mode="HTML")
            except Exception as e:
                logging.warning(f"Kunlik hisobotni ({shop_id}) yuborib bo'lmadi: {e}")
        except Exception as e:
            logging.warning(f"Kunlik hisobot ({shop_id}) uchun umumiy xato: {e}")

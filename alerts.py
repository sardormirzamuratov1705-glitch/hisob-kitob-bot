import logging
from datetime import datetime, timedelta

import config
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


def _debt_severity(days_ago: int) -> str:
    """QARZ ESLATMASI - 13-BOSQICH: muddati o'tgan qarzning og'irlik darajasini
    belgilaydi - do'kon egasining ro'yxatida eng jiddiylari darhol ko'zga
    tashlanishi uchun (ro'yxat allaqachon eng eskisidan boshlab saralangan,
    bu faqat vizual belgi qo'shadi)."""
    if days_ago >= 30:
        return "🔴"
    if days_ago >= 7:
        return "🟠"
    return "🟡"


async def send_debt_reminders(bot, days_threshold: int = None):
    """Har kuni bir marta chaqiriladi (main.py'dagi fon vazifadan).

    Endi har bir DO'KON alohida ko'rib chiqiladi (bir necha mustaqil do'kon
    bor bo'lgani uchun): har bir do'kon egasi faqat O'Z qarzdorlari haqida
    xabar oladi, boshqa do'konning qarzdorlari haqida hech narsa ko'rmaydi.

    Har bir muddati o'tgan qarz uchun:
    - agar mijoz start-link orqali botga ulangan bo'lsa - unga to'g'ridan-
      to'g'ri eslatma yuboriladi, LEKIN faqat config.DEBT_CUSTOMER_REMINDER_
      INTERVAL_DAYS kunda bir marta (13-BOSQICH: mijozni HAR KUNI bezovta
      qilmaslik uchun - debts.last_reminder_at shu maqsadda ishlatiladi);
    - shu bilan birga o'sha do'kon egasiga HAR DOIM (mijozga eslatma
      yuborilgan-yuborilmaganidan qat'i nazar) to'liq ro'yxat yuboriladi -
      har bir qarz qancha kun o'tganiga qarab 🟡/🟠/🔴 belgisi bilan
      (13-BOSQICH: eng jiddiylari - 30+ kun - 🔴 bilan darhol ko'rinadi).

    Bosh admin (config.ADMIN_IDS) endi hech qanday do'konga ega emas, shuning
    uchun bu xabarlarni olmaydi - uning yagona vazifasi do'kon egalarini
    boshqarish.
    """
    if days_threshold is None:
        days_threshold = config.DEBT_OVERDUE_DAYS_DEFAULT

    interval = timedelta(days=config.DEBT_CUSTOMER_REMINDER_INTERVAL_DAYS)
    now = datetime.now()

    owner_ids = await db.get_owner_ids()
    for shop_id in owner_ids:
        overdue = await db.get_overdue_debts(shop_id, days=days_threshold)
        if not overdue:
            continue

        for d in overdue:
            last_sent = d.get("last_reminder_at")
            due_for_customer_reminder = True
            if last_sent:
                try:
                    due_for_customer_reminder = (
                        now - datetime.strptime(last_sent, "%Y-%m-%d %H:%M:%S") >= interval
                    )
                except ValueError:
                    due_for_customer_reminder = True

            if due_for_customer_reminder:
                sent = await send_customer_debt_reminder(bot, d)
                if sent:
                    await db.update_debt_reminder_sent(d["id"])

        lines = [
            f"{_debt_severity(d['days_ago'])} {d['customer_name']} ({d['phone']}) — "
            f"{d['amount']:.0f} so'm, {d['days_ago']} kundan beri qarzda"
            + (" 🔗" if d.get("customer_chat_id") else "")
            for d in overdue
        ]
        severe_count = sum(1 for d in overdue if d["days_ago"] >= 30)
        severe_line = (
            f"\n\n🔴 Shulardan <b>{severe_count} tasi</b> 30 kundan ko'proq muddat o'tgan - "
            "alohida e'tibor talab qiladi!"
            if severe_count else ""
        )
        text = (
            f"🔔 <b>Qarzdorlar eslatmasi</b>\n"
            f"{days_threshold}+ kundan beri (yoki belgilangan muddatdan) to'lanmagan qarzlar:\n\n"
            + "\n".join(lines) + severe_line +
            "\n\n🔗 belgisi — mijozga eslatma avtomatik yuborildi (har "
            f"{config.DEBT_CUSTOMER_REMINDER_INTERVAL_DAYS} kunda bir marta)."
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


# ---------- SHUBHALI HOLATLAR - 9-BOSQICH: REAL VAQTDA TEKSHIRUV ----------
# DIQQAT: bu bo'limdagi funksiyalar hozircha faqat ANIQLAYDI va topganini
# matn ro'yxati sifatida qaytaradi - hech kimga Telegram orqali hech narsa
# YUBORMAYDI (chaqiruvchi tomonda hozircha logga yozib qo'yiladi, xolos).
# Egaga/adminga DARHOL Telegram ogohlantirishi yuborish - 10-bosqich, va u
# aynan shu funksiyalar qaytargan ro'yxatdan foydalanadi.

async def check_sale_line_suspicions(shop_id: int, product: dict, quantity: float, sale_price: float) -> list:
    """Bitta savdo qatori (bitta chekdagi bitta mahsulot) uchun 8-bosqichda
    tasdiqlangan 1/2/3/4-qoidalarni tekshiradi:
      1) mahsulot qoldig'i shu sotuvdan keyin manfiy bo'lib qolishi (chegarasiz)
      2) sotuv narxi tannarxdan past bo'lishi (chegarasiz)
      3) tavsiya etilgan narxdan katta chegirma (rules['discount_percent'])
      4) bitta savdoda katta miqdor (rules['sale_quantity'])
    `product` - db.get_product() natijasi, SOTUVDAN OLDINGI holatda (ya'ni
    product['quantity'] hali kamaytirilmagan bo'lishi kerak)."""
    rules = await db.get_suspicious_rules(shop_id)
    flags = []

    remaining = product["quantity"] - quantity
    if remaining < 0:
        flags.append(
            f"❌ <b>{product['name']}</b> qoldig'i MANFIY bo'lib qoldi "
            f"({remaining:.0f} dona) — miqdorni tekshiring."
        )

    cost_price = product.get("price") or 0
    if sale_price < cost_price:
        flags.append(
            f"⚠️ <b>{product['name']}</b> tannarxidan PAST sotildi: "
            f"{sale_price:.0f} so'm (tannarx {cost_price:.0f} so'm)."
        )

    sell_price = product.get("sell_price")
    if sell_price and sell_price > 0 and sale_price < sell_price:
        discount_percent = (sell_price - sale_price) / sell_price * 100
        if discount_percent >= rules["discount_percent"]:
            flags.append(
                f"⚠️ <b>{product['name']}</b>ga katta chegirma berildi: "
                f"{discount_percent:.0f}% (tavsiya narx {sell_price:.0f} so'm, "
                f"sotilgan narx {sale_price:.0f} so'm)."
            )

    if quantity >= rules["sale_quantity"]:
        flags.append(
            f"⚠️ <b>{product['name']}</b>dan bir martada g'ayrioddiy ko'p "
            f"sotildi: {quantity:.0f} dona."
        )

    return flags


def check_work_hour_suspicion(rules: dict) -> str:
    """6-qoida: hozirgi vaqt owner belgilagan ish vaqti oralig'idan
    TASHQARIDAmi, tekshiradi. Bitta chek/tranzaksiya uchun BIR MARTA
    chaqirilishi kerak (har bir mahsulot qatori uchun emas - aks holda bir
    xil xabar bir nechta marta takrorlanadi). Hech narsa topilmasa None."""
    now = datetime.now()
    start, end = rules["work_hour_start"], rules["work_hour_end"]
    if start <= end:
        in_hours = start <= now.hour < end
    else:
        # Masalan 22 dan ertalabgi 6 gacha kabi kechani kesib o'tadigan oraliq.
        in_hours = now.hour >= start or now.hour < end
    if in_hours:
        return None
    return (
        f"🕐 Amal ish vaqtidan TASHQARIDA bajarildi (soat {now.strftime('%H:%M')}, "
        f"belgilangan ish vaqti {start:02d}:00–{end:02d}:00)."
    )


async def check_expense_suspicion(shop_id: int, amount: float) -> str:
    """5-qoida: bitta chiqim belgilangan chegaradan yuqorimi, tekshiradi."""
    rules = await db.get_suspicious_rules(shop_id)
    if amount >= rules["expense_amount"]:
        return f"⚠️ G'ayrioddiy katta chiqim kiritildi: {amount:.0f} so'm."
    return None


async def check_seller_activity_suspicion(shop_id: int, performed_by: int) -> str:
    """7-qoida: bugun shu xodim/ega (performed_by) tomonidan kiritilgan
    savdo/kirim-chiqim yozuvlari soni belgilangan chegaradan ko'pmi,
    tekshiradi. performed_by yo'q bo'lsa (None) - tekshirilmaydi."""
    if not performed_by:
        return None
    rules = await db.get_suspicious_rules(shop_id)
    count = await db.count_today_transactions_by_performer(shop_id, performed_by)
    if count >= rules["seller_daily_count"]:
        return (
            f"⚠️ Bugun bitta xodim/foydalanuvchidan g'ayrioddiy ko'p yozuv "
            f"kiritildi: {count} ta (ID: {performed_by})."
        )
    return None


async def evaluate_sale_suspicions(shop_id: int, sale_lines: list, performed_by: int = None) -> list:
    """Butun savdo cheki (bitta yoki bir nechta mahsulot qatori) yakunlanganda
    chaqiriladi - handlers/sales.py._finalize_sale shu yerdan foydalanadi.

    sale_lines - [{"product": <sotuvdan OLDINGI product dict>,
                    "quantity": ..., "price": ...}, ...]
    Barcha topilgan shubhali holatlarni (1,2,3,4-qatorlar bo'yicha + 6,7)
    BITTA ro'yxatga yig'ib qaytaradi (bo'sh ro'yxat - hech narsa topilmadi)."""
    rules = await db.get_suspicious_rules(shop_id)
    flags = []
    for line in sale_lines:
        flags.extend(
            await check_sale_line_suspicions(shop_id, line["product"], line["quantity"], line["price"])
        )

    work_hour_flag = check_work_hour_suspicion(rules)
    if work_hour_flag:
        flags.append(work_hour_flag)

    seller_flag = await check_seller_activity_suspicion(shop_id, performed_by)
    if seller_flag:
        flags.append(seller_flag)

    return flags


async def evaluate_expense_suspicions(shop_id: int, amount: float, performed_by: int = None) -> list:
    """Kirim-chiqimda yangi "chiqim" yozuvi kiritilganda chaqiriladi -
    handlers/transactions.py. 5, 6 va 7-qoidalarni tekshiradi."""
    rules = await db.get_suspicious_rules(shop_id)
    flags = []

    expense_flag = await check_expense_suspicion(shop_id, amount)
    if expense_flag:
        flags.append(expense_flag)

    work_hour_flag = check_work_hour_suspicion(rules)
    if work_hour_flag:
        flags.append(work_hour_flag)

    seller_flag = await check_seller_activity_suspicion(shop_id, performed_by)
    if seller_flag:
        flags.append(seller_flag)

    return flags


# ---------- SHUBHALI HOLATLAR - 10-BOSQICH: DARHOL OGOHLANTIRISH ----------
# 9-bosqichdagi evaluate_sale_suspicions / evaluate_expense_suspicions
# funksiyalari topgan ro'yxatni ENDI shu yerdagi funksiya orqali to'g'ridan-
# to'g'ri do'kon EGASIGA Telegram xabari qilib yuboramiz (shuning uchun
# "Adminga" emas - bosh admin (config.ADMIN_IDS) hech qanday do'konga ega
# emas va shu do'kondagi shubhali holatlarga aloqasi yo'q, xuddi boshqa
# barcha shop-darajasidagi ogohlantirishlar - masalan notify_stock_change -
# kabi faqat shop_id'ga yuboriladi).
#
# Owner "🚨 Shubhali holatlar" bo'limidan bu xabarlarni o'zi o'chirib
# qo'yishi mumkin (db.get_suspicious_alert_enabled/set_suspicious_alert_enabled,
# handlers/reports.py) - o'chirilgan bo'lsa ham tekshiruv logga yozilishda
# davom etadi (evaluate_* funksiyalari chaqiruvchi tomonda hamon
# logging.warning qiladi), faqat Telegram xabari yuborilmaydi.

def build_suspicious_alert_text(flags: list, title: str) -> str:
    """Bitta savdo/chiqim yozuvi bo'yicha topilgan shubhali holatlar
    ro'yxatini (evaluate_sale_suspicions yoki evaluate_expense_suspicions
    natijasi) o'qishga qulay Telegram xabariga aylantiradi."""
    lines = "\n".join(f"— {flag}" for flag in flags)
    return f"🚨 <b>Shubhali holat aniqlandi</b> ({title})\n\n{lines}"


async def send_suspicious_alert(bot, shop_id: int, flags: list, title: str) -> bool:
    """Bitta do'kon egasiga shubhali holatlar haqida DARHOL (voqea sodir
    bo'lgan zahoti) Telegram xabari yuboradi.

    - flags bo'sh bo'lsa - hech narsa qilinmaydi (chaqiruvchi tomonda ham
      tekshirilgan, lekin bu yerda ham xavfsizlik uchun qayta tekshiriladi).
    - Owner bu xabarlarni "🚨 Shubhali holatlar" bo'limidan o'chirib
      qo'ygan bo'lsa - yuborilmaydi.
    Muvaffaqiyatli yuborilsa True, aks holda (o'chirilgan yoki xabar
    yuborib bo'lmasa - masalan bloklangan bo'lsa) False qaytaradi."""
    if not flags:
        return False
    if not await db.get_suspicious_alert_enabled(shop_id):
        return False

    try:
        await bot.send_message(shop_id, build_suspicious_alert_text(flags, title), parse_mode="HTML")
        return True
    except Exception as e:
        logging.warning(f"Shubhali holat ogohlantirishini yuborib bo'lmadi (shop {shop_id}): {e}")
        return False


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

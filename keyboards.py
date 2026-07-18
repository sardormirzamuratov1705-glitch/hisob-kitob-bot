from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, KeyboardButton, WebAppInfo
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

import config


def _add_savdo_button(builder: ReplyKeyboardBuilder):
    """"🛒 Savdo" tugmasi - ODDIY MATN tugmasi sifatida qo'shiladi (web_app
    linksiz). Bosilganda handlers/sales.py'dagi ESKI bosqichma-bosqich savdo
    oqimi ishga tushadi.

    Mini App (WebApp) endi BotFather orqali sozlangan Menu Button / Attach
    Menu orqali alohida ochiladi - shu tugma bilan bog'liq emas. Shu tariqa
    xohlagan foydalanuvchi Menu Button'dan Mini App orqali, xohlagani esa shu
    "🛒 Savdo" tugmasidan eski matnli oqim orqali savdo qilaveradi - ikkalasi
    ham parallel ishlaydi."""
    builder.button(text="🛒 Savdo")


def main_menu(role: str = "owner") -> ReplyKeyboardMarkup:
    """role: "admin" | "owner" | "seller".

    - admin: o'z do'koni yo'q, faqat do'kon egalarini boshqaradi va butun
      tizim zaxira nusxasini oladi/tiklaydi.
    - owner: do'konning barcha bo'limlariga (shu jumladan sotuvchilarni
      boshqarish) to'liq kirish huquqi bor.
    - seller: faqat kundalik savdo ishlari uchun kerakli 3 ta bo'lim -
      narx belgilash, qo'lda miqdor o'zgartirish, kirim/chiqim, hisobot va
      sotuvchi boshqaruvi unga ko'rsatilmaydi.
    """
    builder = ReplyKeyboardBuilder()
    if role == "admin":
        builder.button(text="👥 Foydalanuvchilar")
        builder.button(text="📢 E'lon yuborish")
        builder.button(text="🗄 Zaxira nusxa")
        builder.adjust(1, 1, 1)
    elif role == "seller":
        _add_savdo_button(builder)
        builder.button(text="📋 Mahsulotlar ro'yxati")
        builder.button(text="📒 Qarz daftar")
        builder.button(text="➖ Chiqim qo'shish")
        builder.button(text="🧾 Olinishi kerak bo'lgan tovarlar")
        builder.adjust(1, 1, 1, 1, 1)
    else:
        _add_savdo_button(builder)
        builder.button(text="📦 Sklad")
        builder.button(text="💰 Kirim/Chiqim")
        builder.button(text="📒 Qarz daftar")
        builder.button(text="📊 Hisobot")
        builder.button(text="🧑‍💼 Sotuvchilar")
        builder.button(text="🏢 Filiallar")
        builder.button(text="💳 Obuna")
        builder.adjust(1, 2, 2, 2, 1)
    return builder.as_markup(resize_keyboard=True)


def landing_menu() -> InlineKeyboardMarkup:
    """Botni hali tanimaydigan (ro'yxatdan o'tmagan) odamga /start bosganda
    ko'rsatiladigan "landing" oynadagi yagona tugma - ro'yxatdan o'tishni
    boshlash uchun. Handler: handlers/start.py -> self_register callback."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Ro'yxatdan o'tish", callback_data="self_register")
    return builder.as_markup()


def payment_decision_kb(payment_id: int) -> InlineKeyboardMarkup:
    """Bosh adminga chek skrinshoti bilan birga yuboriladigan tugmalar -
    handlers/subscription.py'dagi pay_approve:/pay_reject: callback'lari."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Tasdiqlash", callback_data=f"pay_approve:{payment_id}")
    builder.button(text="❌ Rad etish", callback_data=f"pay_reject:{payment_id}")
    builder.adjust(2)
    return builder.as_markup()


def subscription_plans_menu(plans: dict) -> InlineKeyboardMarkup:
    """"💳 Obuna" bo'limida ko'rsatiladigan tarif tanlash tugmalari.
    plans - db.get_subscription_plans() natijasi (10-bosqichdan boshlab
    narxlar admin tomonidan o'zgartirilgan bo'lishi mumkin, shuning uchun
    config.SUBSCRIPTION_PLANS emas, shu tayyor dict qabul qilinadi).
    Tanlangach handlers/subscription.py'dagi sub_plan:<key> callback'i ishlaydi."""
    builder = InlineKeyboardBuilder()
    for key, plan in plans.items():
        note = f" ({plan['discount_note']})" if plan.get("discount_note") else ""
        text = f"{plan['label']}{note} — {plan['price']:,} so'm".replace(",", " ")
        builder.button(text=text, callback_data=f"sub_plan:{key}")
    builder.adjust(1)
    return builder.as_markup()


def payment_settings_kb() -> InlineKeyboardMarkup:
    """10-BOSQICH: "⚙️ To'lov sozlamalari" bo'limidagi tahrirlash tugmalari -
    har biri handlers/users.py'dagi editset:<key> callback'iga olib boradi."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ 1 oylik narx", callback_data="editset:price_1m")
    builder.button(text="✏️ 3 oylik narx", callback_data="editset:price_3m")
    builder.button(text="✏️ 12 oylik narx", callback_data="editset:price_12m")
    builder.button(text="✏️ Karta raqami", callback_data="editset:card_number")
    builder.button(text="✏️ Karta egasi (F.I.Sh.)", callback_data="editset:card_holder")
    builder.button(text="✏️ Click raqami", callback_data="editset:click_number")
    builder.button(text="✏️ Payme raqami", callback_data="editset:payme_number")
    builder.adjust(1)
    return builder.as_markup()


def trial_decision_kb(telegram_id: int) -> InlineKeyboardMarkup:
    """O'ZI ro'yxatdan o'tgan (self_register) yangi do'kon egasi haqida bosh
    adminga yuboriladigan xabardagi tugmalar - handlers/subscription.py'dagi
    approve_trial:/reject_trial: callback'lari. "✅ Tasdiqlash" bosilganda
    admin necha kunlik sinov muddati berishni matn ko'rinishida kiritadi."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Tasdiqlash", callback_data=f"approve_trial:{telegram_id}")
    builder.button(text="❌ Rad etish", callback_data=f"reject_trial:{telegram_id}")
    builder.adjust(2)
    return builder.as_markup()


def blocked_menu() -> InlineKeyboardMarkup:
    """Obuna (trial + grace period) tugagan ega/sotuvchiga ko'rsatiladigan
    yagona ekran tugmasi. Bosilganda (6-bosqich) tariflar va to'lov
    rekvizitlari oynasi ochiladi - handlers/subscription.py (keyingi
    bosqichda qo'shiladi)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Obunani uzaytirish", callback_data="extend_subscription")
    return builder.as_markup()


def users_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Do'kon egasi qo'shish")
    builder.button(text="🔗 Bir martalik link")
    builder.button(text="📋 Do'kon egalari ro'yxati")
    builder.button(text="💳 Kutilayotgan to'lovlar")
    builder.button(text="⚙️ To'lov sozlamalari")
    builder.button(text="👑 Admin qo'shish")
    builder.button(text="🔗 Bir martalik admin havolasi")
    builder.button(text="👑 Adminlar ro'yxati")
    builder.button(text="⬅️ Orqaga")
    builder.adjust(1, 1, 1, 1, 1, 1, 1, 1, 1)
    return builder.as_markup(resize_keyboard=True)


def admin_action_kb(telegram_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Admin huquqini olib tashlash", callback_data=f"remove_admin_{telegram_id}")
    builder.adjust(1)
    return builder.as_markup()


def owner_action_kb(telegram_id: int, blocked: bool = False) -> InlineKeyboardMarkup:
    """9-BOSQICH: do'kon egalari ro'yxatidagi har bir ega ostidagi
    boshqaruv tugmalari - obunani uzaytirish, majburiy bloklash/blokdan
    chiqarish va o'chirish. blocked - shu eganing hozirgi
    subscription_status='blocked' holatidami (True bo'lsa "Blokdan
    chiqarish" tugmasi ko'rsatiladi, aks holda "Majburiy bloklash")."""
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Uzaytirish", callback_data=f"extend_menu:{telegram_id}")
    if blocked:
        builder.button(text="✅ Blokdan chiqarish", callback_data=f"unblock_owner:{telegram_id}")
    else:
        builder.button(text="🚫 Majburiy bloklash", callback_data=f"block_owner:{telegram_id}")
    builder.button(text="📊 Skladni Excel bilan to'ldirish", callback_data=f"admin_sklad_excel:{telegram_id}")
    builder.button(text="🗑 O'chirish", callback_data=f"remove_owner_{telegram_id}")
    builder.adjust(1, 1, 1, 1)
    return builder.as_markup()


def extend_subscription_kb(telegram_id: int) -> InlineKeyboardMarkup:
    """9-BOSQICH: "➕ Uzaytirish" bosilganda ko'rsatiladigan muddat tanlash
    tugmalari - tayyor variantlar (+30/+90/+365 kun) yoki admin qo'lda
    erkin kun sonini kiritishi uchun. "-7 kun" - xato qo'shib qo'yilgan
    kunlarni tuzatish uchun tez tugma (masalan adashib +30 bosilsa)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="+30 kun", callback_data=f"extend_days:{telegram_id}:30")
    builder.button(text="+90 kun", callback_data=f"extend_days:{telegram_id}:90")
    builder.button(text="+365 kun", callback_data=f"extend_days:{telegram_id}:365")
    builder.button(text="-7 kun", callback_data=f"extend_days:{telegram_id}:-7")
    builder.button(text="✏️ Erkin kun kiritish (+/-)", callback_data=f"extend_custom:{telegram_id}")
    builder.button(text="⬅️ Orqaga", callback_data=f"extend_back:{telegram_id}")
    builder.adjust(3, 1, 1, 1)
    return builder.as_markup()


def sellers_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Sotuvchi qo'shish")
    builder.button(text="🔗 Sotuvchi uchun link")
    builder.button(text="📋 Sotuvchilar ro'yxati")
    builder.button(text="⬅️ Orqaga")
    builder.adjust(1, 1, 1, 1)
    return builder.as_markup(resize_keyboard=True)


def seller_action_kb(telegram_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Filialni o'zgartirish", callback_data=f"seller_branch_menu_{telegram_id}")
    builder.button(text="🗑 O'chirish", callback_data=f"remove_seller_{telegram_id}")
    builder.adjust(1, 1)
    return builder.as_markup()


def seller_branch_choice_kb(telegram_id: int, branches, current_branch_id=None) -> InlineKeyboardMarkup:
    """Sotuvchini boshqa filialga ko'chirish uchun filiallar ro'yxati.
    "Bosh filial" (filialsiz) variant ham har doim mavjud."""
    builder = InlineKeyboardBuilder()
    mark = "✅" if current_branch_id is None else "🏠"
    builder.button(text=f"{mark} Bosh filial", callback_data=f"seller_branch_set_{telegram_id}_0")
    for b in branches:
        mark = "✅" if b["id"] == current_branch_id else "🏢"
        builder.button(text=f"{mark} {b['name']}", callback_data=f"seller_branch_set_{telegram_id}_{b['id']}")
    builder.adjust(1)
    return builder.as_markup()


def sklad_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Mahsulot qo'shish")
    builder.button(text="📊 Excel bilan to'ldirish")
    builder.button(text="📋 Mahsulotlar ro'yxati")
    builder.button(text="🔍 Qidirish")
    builder.button(text="🗂 Bo'limlar")
    builder.button(text="🧾 Olinishi kerak bo'lgan tovarlar")
    builder.button(text="🤖 AI buyurtma tavsiyasi")
    builder.button(text="🏆 Top mahsulotlar")
    builder.button(text="🐌 Sekin sotiladigan tovarlar")
    builder.button(text="⬅️ Orqaga")
    builder.adjust(1, 1, 2, 1, 2, 1, 1)
    return builder.as_markup(resize_keyboard=True)


def kirim_chiqim_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Kirim qo'shish")
    builder.button(text="➖ Chiqim qo'shish")
    builder.button(text="📈 Bugungi holat")
    builder.button(text="🔎 Savdolarni qidirish")
    builder.button(text="⬅️ Orqaga")
    builder.adjust(2, 1, 1, 1)
    return builder.as_markup(resize_keyboard=True)


def qarz_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Qarz qo'shish")
    builder.button(text="📋 Qarzdorlar ro'yxati")
    builder.button(text="⬅️ Orqaga")
    builder.adjust(1, 1, 1)
    return builder.as_markup(resize_keyboard=True)


def hisobot_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📊 Umumiy hisobot")
    builder.button(text="🏢 Filial bo'yicha hisobot")
    builder.button(text="🆚 Filiallar solishtiruvi")
    builder.button(text="🆚 Sotuvchilar solishtiruvi")
    builder.button(text="📈 Oylik prognoz")
    builder.button(text="📉 Trend tahlili")
    builder.button(text="🔔 Kunlik hisobot")
    builder.button(text="🚨 Shubhali holatlar")
    builder.button(text="🗂 Audit jurnali")
    builder.button(text="📥 Excel yuklab olish")
    builder.button(text="⬅️ Orqaga")
    builder.adjust(1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1)
    return builder.as_markup(resize_keyboard=True)


def daily_report_settings_kb(enabled: bool) -> InlineKeyboardMarkup:
    """KUNLIK HISOBOT - 7-BOSQICH: "🔔 Kunlik hisobot" bo'limidagi
    yoqish/o'chirish tugmasi - handlers/reports.py'dagi
    daily_report_toggle: callback'iga olib boradi."""
    builder = InlineKeyboardBuilder()
    if enabled:
        builder.button(text="🔕 O'chirish", callback_data="daily_report_toggle:off")
    else:
        builder.button(text="🔔 Yoqish", callback_data="daily_report_toggle:on")
    return builder.as_markup()


def suspicious_alert_settings_kb(enabled: bool) -> InlineKeyboardMarkup:
    """SHUBHALI HOLATLAR - 10-BOSQICH: "🚨 Shubhali holatlar" bo'limidagi
    yoqish/o'chirish tugmasi - handlers/reports.py'dagi
    suspicious_alert_toggle: callback'iga olib boradi."""
    builder = InlineKeyboardBuilder()
    if enabled:
        builder.button(text="🔕 O'chirish", callback_data="suspicious_alert_toggle:off")
    else:
        builder.button(text="🚨 Yoqish", callback_data="suspicious_alert_toggle:on")
    return builder.as_markup()


def report_branch_kb(branches, prefix: str, include_all: bool = False) -> InlineKeyboardMarkup:
    """Hisobot uchun filial/kesim tanlash klaviaturasi.

    - include_all=True bo'lsa, "🌐 Umumiy (barcha filiallar)" varianti ham
      qo'shiladi (masalan "Top mahsulotlar" uchun - u ikkala kesimda ham
      ishlashi kerak).
    - "🏠 Bosh filial" - filialga bog'lanmagan (branch_id=NULL) yozuvlar
      uchun, doim mavjud (filial tizimidan oldingi eski yozuvlar ham shu yerga tushadi).
    - prefix - callback_data old qismi (masalan "rep_branch" yoki "rep_top"),
      oxiriga "_all", "_0" yoki filial id qo'shiladi.
    """
    builder = InlineKeyboardBuilder()
    if include_all:
        builder.button(text="🌐 Umumiy (barcha filiallar)", callback_data=f"{prefix}_all")
    builder.button(text="🏠 Bosh filial", callback_data=f"{prefix}_0")
    for b in branches:
        builder.button(text=f"🏢 {b['name']}", callback_data=f"{prefix}_{b['id']}")
    builder.adjust(1)
    return builder.as_markup()


def admin_backup_menu() -> ReplyKeyboardMarkup:
    """Faqat bosh adminga ko'rinadi - butun baza (BARCHA do'konlar) zaxira
    nusxasini olish/tiklash uchun."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="🗄 DB faylni yuklab olish")
    builder.button(text="📤 DB faylni tiklash")
    builder.button(text="⬅️ Orqaga")
    builder.adjust(1, 1, 1)
    return builder.as_markup(resize_keyboard=True)


def skip_photo_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Rasmsiz davom etish", callback_data="skip_photo")
    return builder.as_markup()


def skip_due_date_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Sanasiz davom etish", callback_data="skip_due_date")
    return builder.as_markup()


def taken_date_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Bugun", callback_data="taken_today")
    builder.button(text="🗓 Boshqa sana", callback_data="taken_custom")
    builder.adjust(2)
    return builder.as_markup()


def payment_method_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💵 Naqd", callback_data="pay_method_naqd")
    builder.button(text="💳 Plastik", callback_data="pay_method_plastik")
    builder.button(text="🔀 Aralash (naqd + plastik)", callback_data="pay_method_aralash")
    builder.adjust(2, 1)
    return builder.as_markup()


def product_action_kb(product_id: int, allow_manage: bool = True, category_id=None, has_discount: bool = False):
    """allow_manage=False bo'lsa (sotuvchi) - hech qanday tugma qaytarilmaydi
    (None), chunki miqdor FAQAT savdo orqali kamayishi kerak - qo'lda
    o'zgartirish yoki o'chirish faqat do'kon egasiga tegishli.

    category_id - mahsulotning hozirgi bo'limi. Agar mahsulot biror bo'limga
    tegishli bo'lsa, "Bo'limdan chiqarish" tugmasi ham ko'rsatiladi.

    has_discount - mahsulotda hozir faol chegirma bor-yo'qligi
    (database.product_discount_info() natijasidan). Bor bo'lsa "bekor
    qilish" tugmasi, yo'q bo'lsa "belgilash" tugmasi ko'rsatiladi. Chegirma
    belgilash/bekor qilish FAQAT do'kon egasiga ruxsat etilgan - haqiqiy
    tekshiruv handlers/products.py'dagi callback handlerda
    (access_control.is_owner_level) amalga oshiriladi."""
    if not allow_manage:
        return None
    builder = InlineKeyboardBuilder()
    if has_discount:
        builder.button(text="❌ Chegirmani bekor qilish", callback_data=f"prod_discount_cancel_{product_id}")
    else:
        builder.button(text="🏷 Chegirma belgilash", callback_data=f"prod_discount_{product_id}")
    builder.button(text="✏️ Narxlarni tahrirlash", callback_data=f"prod_edit_{product_id}")
    builder.button(text="📉 Kamomad chiqarish", callback_data=f"prod_shortage_{product_id}")
    builder.button(text="🔀 Bo'limni o'zgartirish", callback_data=f"prod_move_{product_id}")
    if category_id is not None:
        builder.button(text="🚫 Bo'limdan chiqarish", callback_data=f"prod_unassign_{product_id}")
    builder.button(text="🗑 O'chirish", callback_data=f"del_product_{product_id}")
    builder.adjust(1)
    return builder.as_markup()


def product_edit_field_kb(product_id: int, product: dict) -> InlineKeyboardMarkup:
    """\"✏️ Narxlarni tahrirlash\" bosilganda ko'rsatiladigan - eski
    mahsulotning qaysi narx ustunini o'zgartirish tanlanadigan menyu.
    Har bir tugmada hozirgi qiymat ko'rsatiladi (belgilanmagan bo'lsa -
    shunday deb yoziladi)."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"💰 Tannarx: {product['price']:.0f} so'm",
        callback_data=f"prod_editfield_{product_id}:price",
    )
    sell_price = product.get("sell_price")
    builder.button(
        text=f"🏷 Sotuv narxi: {sell_price:.0f} so'm" if sell_price else "🏷 Sotuv narxi: belgilanmagan",
        callback_data=f"prod_editfield_{product_id}:sell_price",
    )
    min_price = product.get("min_price")
    builder.button(
        text=f"⬇️ Eng past narx: {min_price:.0f} so'm" if min_price else "⬇️ Eng past narx: belgilanmagan",
        callback_data=f"prod_editfield_{product_id}:min_price",
    )
    builder.adjust(1)
    return builder.as_markup()


def category_pick_kb(categories, include_none: bool = True) -> InlineKeyboardMarkup:
    """Mahsulot qo'shishda bo'lim tanlash uchun - mavjud bo'limlar
    tugma sifatida chiqadi, shuningdek yangi bo'lim yaratish va
    bo'limsiz qoldirish imkoniyati beriladi."""
    builder = InlineKeyboardBuilder()
    for c in categories:
        builder.button(text=f"📁 {c['name']}", callback_data=f"cat_pick_{c['id']}")
    builder.button(text="➕ Yangi bo'lim", callback_data="cat_pick_new")
    if include_none:
        builder.button(text="🚫 Bo'limsiz", callback_data="cat_pick_none")
    builder.adjust(1)
    return builder.as_markup()


def category_browse_kb(categories, uncategorized_count: int = 0) -> InlineKeyboardMarkup:
    """Mahsulotlar ro'yxatini bo'lim bo'yicha ko'rish uchun menyu."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Barchasi", callback_data="cat_view_all")
    for c in categories:
        builder.button(
            text=f"📁 {c['name']} ({c['product_count']:.0f})",
            callback_data=f"cat_view_{c['id']}",
        )
    if uncategorized_count:
        builder.button(text=f"🚫 Bo'limsiz ({uncategorized_count})", callback_data="cat_view_none")
    builder.adjust(1)
    return builder.as_markup()


def category_manage_kb(categories) -> InlineKeyboardMarkup:
    """Bo'limlarni boshqarish (o'chirish) va yangisini qo'shish uchun menyu."""
    builder = InlineKeyboardBuilder()
    row_sizes = []
    for c in categories:
        builder.button(text=f"📁 {c['name']} ({c['product_count']:.0f})", callback_data=f"cat_noop_{c['id']}")
        builder.button(text="🗑", callback_data=f"cat_delete_{c['id']}")
        row_sizes.append(2)
    builder.button(text="➕ Bo'lim qo'shish", callback_data="cat_manage_new")
    row_sizes.append(1)
    builder.adjust(*row_sizes)
    return builder.as_markup()


def category_move_kb(categories, product_id: int, current_category_id=None) -> InlineKeyboardMarkup:
    """Mahsulotni boshqa bo'limga ko'chirish uchun bo'lim tanlash menyusi.
    Mahsulot hozir turgan bo'lim ro'yxatda ko'rsatilmaydi."""
    builder = InlineKeyboardBuilder()
    for c in categories:
        if c["id"] == current_category_id:
            continue
        builder.button(text=f"📁 {c['name']}", callback_data=f"prod_move_to_{product_id}_{c['id']}")
    if current_category_id is not None:
        builder.button(text="🚫 Bo'limdan chiqarish", callback_data=f"prod_unassign_{product_id}")
    builder.adjust(1)
    return builder.as_markup()


def branch_manage_kb(branches, current_branch_id=None) -> InlineKeyboardMarkup:
    """Filiallarni boshqarish: nomga bosish = shu filialga o'tish (joriy
    filial ✅ bilan belgilanadi), o'chirish alohida tugma bilan."""
    builder = InlineKeyboardBuilder()
    row_sizes = []
    for b in branches:
        mark = "✅" if b["id"] == current_branch_id else "🏢"
        builder.button(text=f"{mark} {b['name']}", callback_data=f"branch_switch_{b['id']}")
        builder.button(text="🗑", callback_data=f"branch_delete_{b['id']}")
        row_sizes.append(2)
    builder.button(text="➕ Filial qo'shish", callback_data="branch_manage_new")
    row_sizes.append(1)
    builder.adjust(*row_sizes)
    return builder.as_markup()


def restock_kb(low_stock_items=None, manual_items=None, manage: bool = True) -> InlineKeyboardMarkup:
    """manage=False bo'lsa (sotuvchi) - "✅ ... olindi" / "❌ ... olinmadi" tugmalari
    ko'rsatilmaydi, chunki tovar sotib olinganini faqat do'kon egasi belgilashi kerak.
    "➕ Qo'lda qo'shish" tugmasi esa sotuvchiga ham qoldiriladi - u kerakli tovarni
    ro'yxatga qo'shib qo'ya oladi."""
    builder = InlineKeyboardBuilder()
    row_sizes = []

    if manage and low_stock_items:
        for p in low_stock_items:
            builder.button(text=f"✅ {p['name']} olindi", callback_data=f"lowstock_bought_{p['id']}")
            builder.button(text=f"❌ {p['name']} olinmadi", callback_data=f"lowstock_notbought_{p['id']}")
            row_sizes.append(2)

    builder.button(text="➕ Qo'lda qo'shish", callback_data="restock_add")
    row_sizes.append(1)

    if manage and manual_items:
        for item in manual_items:
            builder.button(text=f"✅ {item['name']} olindi", callback_data=f"restock_done_{item['id']}")
            row_sizes.append(1)

    builder.adjust(*row_sizes)
    return builder.as_markup()


def debt_action_kb(debt_id: int, customer_linked: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💯 Hammasini to'lash", callback_data=f"payfull_debt_{debt_id}")
    builder.button(text="✅ Qisman to'landi", callback_data=f"pay_debt_{debt_id}")
    if customer_linked:
        builder.button(text="🔔 Eslatma yuborish", callback_data=f"remind_debt_{debt_id}")
    else:
        builder.button(text="🔗 Link yaratish", callback_data=f"debt_link_{debt_id}")
    builder.adjust(1)
    return builder.as_markup()


def sale_price_kb(sell_price=None, min_price=None, discount_price=None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if discount_price:
        builder.button(text=f"🏷 Chegirma narxi: {discount_price:.0f}", callback_data="sale_price_discount")
    if sell_price:
        builder.button(text=f"💰 Savdo narxi: {sell_price:.0f}", callback_data="sale_price_sell")
    if min_price:
        builder.button(text=f"⬇️ Eng past narx: {min_price:.0f}", callback_data="sale_price_min")
    builder.button(text="✏️ Boshqa narx", callback_data="sale_price_custom")
    builder.adjust(1)
    return builder.as_markup()


SALE_PRODUCTS_PAGE_SIZE = 10


def sale_products_kb(products, selected_ids, page: int = 0, search_active: bool = False) -> InlineKeyboardMarkup:
    """Mahsulotlarni 10tadan sahifalab ko'rsatadi.

    Belgilangan mahsulotlar (selected_ids) sahifa almashtirilganda ham
    saqlanib qoladi - chunki tanlov ro'yxati state'da alohida saqlanadi,
    faqat joriy sahifadagi tugmalar mark bilan yangilanadi.
    search_active=True bo'lsa, ro'yxat qidiruv natijasi ekanini bildiruvchi
    "Qidiruvni bekor qilish" tugmasi ko'rsatiladi.
    """
    page_size = SALE_PRODUCTS_PAGE_SIZE
    total_pages = max(1, (len(products) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    page_products = products[start:start + page_size]

    builder = InlineKeyboardBuilder()
    for p in page_products:
        mark = "☑️" if p["id"] in selected_ids else "⬜"
        builder.button(
            text=f"{mark} {p['name']} ({p['quantity']:.0f} dona)",
            callback_data=f"sale_toggle_{p['id']}",
        )

    rows = [1] * len(page_products)

    nav_row = 0
    if page > 0:
        builder.button(text="⬅️ Avvalgisi", callback_data="sale_page_prev")
        nav_row += 1
    if total_pages > 1:
        builder.button(text=f"📄 {page + 1}/{total_pages}", callback_data="sale_noop")
        nav_row += 1
    if page < total_pages - 1:
        builder.button(text="Keyingisi ➡️", callback_data="sale_page_next")
        nav_row += 1
    if nav_row:
        rows.append(nav_row)

    if search_active:
        builder.button(text="❌ Qidiruvni bekor qilish", callback_data="sale_search_clear")
    else:
        builder.button(text="🔎 Nomi bo'yicha qidirish", callback_data="sale_search")
    rows.append(1)

    builder.button(text="✅ Tanlovni tasdiqlash", callback_data="sale_confirm")
    builder.button(text="❌ Bekor qilish", callback_data="sale_cancel")
    rows.append(1)
    rows.append(1)

    builder.adjust(*rows)
    return builder.as_markup()

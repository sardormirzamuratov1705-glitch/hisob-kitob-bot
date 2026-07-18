from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


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
        builder.button(text="🗄 Zaxira nusxa")
        builder.adjust(1, 1)
    elif role == "seller":
        builder.button(text="🛒 Savdo")
        builder.button(text="📋 Mahsulotlar ro'yxati")
        builder.button(text="📒 Qarz daftar")
        builder.button(text="➖ Chiqim qo'shish")
        builder.button(text="🧾 Olinishi kerak bo'lgan tovarlar")
        builder.adjust(1, 1, 1, 1, 1)
    else:
        builder.button(text="📦 Sklad")
        builder.button(text="💰 Kirim/Chiqim")
        builder.button(text="📒 Qarz daftar")
        builder.button(text="📊 Hisobot")
        builder.button(text="🧑‍💼 Sotuvchilar")
        builder.button(text="🏢 Filiallar")
        builder.adjust(2, 2, 2)
    return builder.as_markup(resize_keyboard=True)


def users_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Do'kon egasi qo'shish")
    builder.button(text="🔗 Bir martalik link")
    builder.button(text="📋 Do'kon egalari ro'yxati")
    builder.button(text="⬅️ Orqaga")
    builder.adjust(1, 1, 1, 1)
    return builder.as_markup(resize_keyboard=True)


def owner_action_kb(telegram_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 O'chirish", callback_data=f"remove_owner_{telegram_id}")
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
    builder.button(text="🗑 O'chirish", callback_data=f"remove_seller_{telegram_id}")
    return builder.as_markup()


def sklad_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Mahsulot qo'shish")
    builder.button(text="📋 Mahsulotlar ro'yxati")
    builder.button(text="🔍 Qidirish")
    builder.button(text="🗂 Bo'limlar")
    builder.button(text="🧾 Olinishi kerak bo'lgan tovarlar")
    builder.button(text="🐌 Sekin sotiladigan tovarlar")
    builder.button(text="⬅️ Orqaga")
    builder.adjust(1, 2, 1, 1, 1, 1)
    return builder.as_markup(resize_keyboard=True)


def kirim_chiqim_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="🛒 Savdo")
    builder.button(text="➕ Kirim qo'shish")
    builder.button(text="➖ Chiqim qo'shish")
    builder.button(text="📈 Bugungi holat")
    builder.button(text="🔎 Savdolarni qidirish")
    builder.button(text="⬅️ Orqaga")
    builder.adjust(1, 2, 1, 1, 1)
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
    builder.button(text="🏆 Top mahsulotlar")
    builder.button(text="📥 Excel yuklab olish")
    builder.button(text="⬅️ Orqaga")
    builder.adjust(1, 1, 1, 1)
    return builder.as_markup(resize_keyboard=True)


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


def product_action_kb(product_id: int, allow_manage: bool = True, category_id=None):
    """allow_manage=False bo'lsa (sotuvchi) - hech qanday tugma qaytarilmaydi
    (None), chunki miqdor FAQAT savdo orqali kamayishi kerak - qo'lda
    o'zgartirish yoki o'chirish faqat do'kon egasiga tegishli.

    category_id - mahsulotning hozirgi bo'limi. Agar mahsulot biror bo'limga
    tegishli bo'lsa, "Bo'limdan chiqarish" tugmasi ham ko'rsatiladi."""
    if not allow_manage:
        return None
    builder = InlineKeyboardBuilder()
    builder.button(text="🔀 Bo'limni o'zgartirish", callback_data=f"prod_move_{product_id}")
    if category_id is not None:
        builder.button(text="🚫 Bo'limdan chiqarish", callback_data=f"prod_unassign_{product_id}")
    builder.button(text="🗑 O'chirish", callback_data=f"del_product_{product_id}")
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
    builder.button(text="✅ To'landi", callback_data=f"pay_debt_{debt_id}")
    if customer_linked:
        builder.button(text="🔔 Eslatma yuborish", callback_data=f"remind_debt_{debt_id}")
    else:
        builder.button(text="🔗 Link yaratish", callback_data=f"debt_link_{debt_id}")
    builder.adjust(1)
    return builder.as_markup()


def sale_price_kb(sell_price=None, min_price=None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
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

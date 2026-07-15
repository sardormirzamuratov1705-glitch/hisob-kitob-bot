# Magazin Boshqaruv Boti

Do'kon uchun: sklad (rasm bilan), kirim/chiqim, qarz daftar, hisobot (Excel export).

## Tuzilma

```
magazin_bot/
├── main.py              # Botni ishga tushiruvchi fayl
├── config.py            # Sozlamalar (token, baza yo'li)
├── database.py          # SQLite bilan ishlash
├── keyboards.py         # Tugmalar
├── handlers/
│   ├── start.py         # /start va asosiy menyu
│   ├── products.py      # Sklad (mahsulot qo'shish/ko'rish/o'chirish)
│   ├── transactions.py  # Kirim/Chiqim
│   ├── debts.py         # Qarz daftar
│   └── reports.py       # Hisobot va Excel export
├── requirements.txt
└── .env.example
```

## 1. Mahalliy sinov (kompyuteringizda)

```bash
pip install -r requirements.txt
cp .env.example .env
```

`.env` faylini oching, `BOT_TOKEN` qatoriga @BotFather'dan olingan tokenni yozing.

```bash
python main.py
```

## 2. Railway'ga joylash

### a) GitHub'ga yuklash
Loyihani GitHub repo'ga push qiling (avvalgi botlaringizda qilgan usulingiz bilan).

### b) Railway'da yangi service yaratish
1. Railway → New Project → Deploy from GitHub repo
2. Repo'ni tanlang

### c) Environment Variables qo'shish (Settings → Variables)
```
BOT_TOKEN=sizning_tokeningiz
ADMIN_IDS=sizning_telegram_id
DB_PATH=/data/shop.db
```

### d) Volume ulash (MUHIM — ma'lumot yo'qolmasligi uchun)
1. Service → Settings → Volumes → **New Volume**
2. Mount path: `/data`
3. Hajmi: 0.5 GB (bitta magazin uchun yetarli, matn ma'lumoti kichik)

`DB_PATH=/data/shop.db` qilib bergan bo'lsangiz, baza shu volume ichida saqlanadi va **har redeploy'da o'chib qolmaydi**.

### e) Deploy
Railway avtomatik `main.py` ni topib ishga tushiradi. Agar tushirmasa, Settings → Deploy → Start Command:
```
python main.py
```

## 3. Rasm haqida eslatma

Mahsulot rasmlari **disk/volume'ga saqlanmaydi** — faqat Telegram'ning o'z serveridagi `file_id` bazada saqlanadi. Shuning uchun minglab rasm qo'shsangiz ham, 0.5 GB volume hech qachon to'lib qolmaydi.

## 4. Keyingi qadamlar (birma-bir qo'shib boramiz)

- [ ] Ko'p filial/do'kon qo'llab-quvvatlash
- [ ] Mahsulotni tahrirlash (narx/miqdor yangilash)
- [ ] Sotuvni sklad bilan bog'lash (sotilganda miqdor avtomatik kamayishi)
- [ ] Kunlik/oylik avtomatik hisobot yuborish (APScheduler bilan)
- [ ] Bir nechta admin/xodim uchun rol tizimi
- [ ] Har kuni avtomatik `.db` backup yuborish (admin chatga)

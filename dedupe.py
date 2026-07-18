"""Bir foydalanuvchi sekin internetda (yoki shunchaki shoshilib) bitta
tugmani/xabarni ketma-ket ikki marta tez yuborib yuborsa, ikkinchisi
birinchisi hali tugamasdan boshlanib ketishi mumkin - natijada bitta savdo/
to'lov/qarz ikki marta yozilib qoladi.

Bu modul juda oddiy: bitta process (bitta bot nusxasi) doirasida, bitta
foydalanuvchi uchun moliyaviy yozuv qo'shadigan amal AYNI PAYTDA faqat
BITTA marta bajarilishini ta'minlaydi - ikkinchisi "band" deb rad etiladi.

DIQQAT: bu xotirada saqlanadi (bitta process uchun). Agar kelajakda bot bir
nechta serverda/workerda parallel ishga tushirilsa, bu yerni umumiy
saqlagichga (masalan Redis) ko'chirish kerak bo'ladi - hozircha bot bitta
process sifatida ishlaganda bu yetarli."""

_busy_users: set[int] = set()


class DuplicateAction(Exception):
    """Shu foydalanuvchi uchun oldingi amal hali tugamagan - ikkinchisini
    bajarmaslik kerak."""


class user_lock:
    """``async with user_lock(user_id): ...`` - agar shu user_id band bo'lsa
    DuplicateAction ko'taradi, aks holda amalni bajarish davomida uni band
    deb belgilaydi va oxirida (xato bo'lsa ham) bo'shatadi."""

    __slots__ = ("user_id",)

    def __init__(self, user_id: int):
        self.user_id = user_id

    async def __aenter__(self):
        if self.user_id in _busy_users:
            raise DuplicateAction()
        _busy_users.add(self.user_id)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        _busy_users.discard(self.user_id)
        return False

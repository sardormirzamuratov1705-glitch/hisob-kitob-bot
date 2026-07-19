// SAVDO WEB APP - 1-BOSQICH
// Bu fayl Telegram Mini App (WebApp) ichida ishlaydi. Har bir so'rovga
// Telegram.WebApp.initData headerda (X-Telegram-Init-Data) qo'shib
// yuboriladi - server (webapp.py) shu orqali so'rov chindan ham
// Telegramning o'zidan va aynan shu foydalanuvchidan kelayotganini tekshiradi.

const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

// ZAXIRA (FALLBACK): ba'zi Telegram Desktop versiyalarida WebApp haqiqiy
// "web_app" tugmasi orqali ochilsa ham (URL fragmentida #tgWebAppData=...
// bo'ladi), Telegram.WebApp.initData bo'sh qolib ketadi - bu Telegramning
// o'zidagi nosozlik. Shu holatda initData'ni to'g'ridan-to'g'ri URL
// fragmentidan o'qib olamiz.
function getInitData() {
  if (tg.initData) return tg.initData;
  const match = location.hash.match(/tgWebAppData=([^&]+)/);
  if (match) return decodeURIComponent(match[1]);
  return "";
}

// AVTOMATIK QAYTA YUKLASH: Telegram ba'zan (hujjatlashtirilmagan sababga
// ko'ra) birinchi ochilishda tgWebAppData'ni umuman yubormay qoladi -
// bu Telegramning o'zidagi tasodifiy holat, kodga bog'liq emas. Ko'p
// hollarda sahifani (Mini App ichida, Telegramdan chiqmasdan) bir marta
// qayta yuklash muammoni hal qiladi. sessionStorage bilan faqat BITTA
// marta qayta yuklanishini ta'minlaymiz (cheksiz aylanib qolmasligi uchun).
(function ensureInitDataOrReload() {
  if (!getInitData()) {
    if (sessionStorage.getItem("edaftar_reloaded")) return;
    sessionStorage.setItem("edaftar_reloaded", "1");
    location.reload();
    return;
  }
  sessionStorage.removeItem("edaftar_reloaded");
})();

const API = {
  me: "/api/webapp/me",
  products: "/api/webapp/products",
  productByBarcode: "/api/webapp/products/by-barcode",
  crossSell: "/api/webapp/cross_sell",
  sale: "/api/webapp/sale",
  skladProducts: "/api/webapp/sklad/products",
  skladAddQuantity: "/api/webapp/sklad/add-quantity",
  skladCreateProduct: "/api/webapp/sklad/create-product",
  skladUpdateProduct: "/api/webapp/sklad/update-product",
  skladHistory: "/api/webapp/sklad/history",
  profile: "/api/webapp/profile",
  branches: "/api/webapp/branches",
  branchesSwitch: "/api/webapp/branches/switch",
  skladPermission: "/api/webapp/sklad-permission",

  // 11-BOSQICH: BOSH ADMIN PANELI
  adminStats: "/api/webapp/admin/stats",
  adminOwners: "/api/webapp/admin/owners",
  adminOwnerInviteLink: "/api/webapp/admin/owners/invite-link",
  adminOwner: (id) => `/api/webapp/admin/owners/${id}`,
  adminOwnerExtend: (id) => `/api/webapp/admin/owners/${id}/extend`,
  adminOwnerBlock: (id) => `/api/webapp/admin/owners/${id}/block`,
  adminOwnerUnblock: (id) => `/api/webapp/admin/owners/${id}/unblock`,
  adminAdmins: "/api/webapp/admin/admins",
  adminAdminsInviteLink: "/api/webapp/admin/admins/invite-link",
  adminAdmin: (id) => `/api/webapp/admin/admins/${id}`,
  adminPayments: "/api/webapp/admin/payments",
  adminPaymentPhoto: (id) => `/api/webapp/admin/payments/${id}/photo`,
  adminPaymentApprove: (id) => `/api/webapp/admin/payments/${id}/approve`,
  adminPaymentReject: (id) => `/api/webapp/admin/payments/${id}/reject`,
  adminSettings: "/api/webapp/admin/settings",
  adminBroadcast: "/api/webapp/admin/broadcast",
};

let cart = []; // [{id, name, qty, price, stock}]
let selectedPaymentMethod = null;
let currentModalProduct = null;
let currentSection = "sale"; // 6-BOSQICH: "sale" (Savdo) | "sklad" (Sklad)

// 8-BOSQICH: api_me javobidan to'ldiriladi (init() ichida) - "Sklad"
// bo'limida "➕ Skladga qo'shish" imkoniyati shu bayroqqa qarab
// ko'rsatiladi/qulflanadi (do'kon egasi buni sotuvchi uchun o'chirib
// qo'ygan bo'lishi mumkin - qarang: handlers/sellers.py "🔐 Sklad ruxsati").
let currentUser = { role: null, canAddStock: true };

async function loadMe() {
  try {
    const res = await apiFetch(API.me);
    if (!res.ok) return;
    const data = await res.json();
    currentUser.role = data.role;
    currentUser.canAddStock = data.can_add_stock !== false;
    updateSkladPermissionUI();
  } catch (e) {
    // Jim o'tkazamiz - bu faqat UI'ni yaxshilash uchun, savdo oqimini
    // to'xtatib qo'ymasligi kerak (asosiy 401 tekshiruvi baribir
    // loadProducts()'da bo'ladi).
  }
}

const el = (id) => document.getElementById(id);

function showScreen(name) {
  [
    "loading", "error", "products", "cart", "sklad", "profile",
    "admin-stats", "admin-owners", "admin-payments", "admin-settings",
  ].forEach((s) => {
    el(`screen-${s}`).classList.toggle("hidden", s !== name);
  });
}

function showError(message) {
  el("error-text").textContent = message;
  showScreen("error");
}

async function apiFetch(url, options = {}) {
  const initData = getInitData();
  const headers = Object.assign({}, options.headers || {}, {
    "X-Telegram-Init-Data": initData,
  });
  if (options.body) headers["Content-Type"] = "application/json";
  const res = await fetch(url, Object.assign({}, options, { headers }));
  if (res.status === 401) {
    // VAQTINCHALIK DIAGNOSTIKA (401 sababini aniqlash uchun): Telegram
    // muhitini qanday ko'rayotganini ekranga chiqaramiz - initData nega
    // bo'sh kelayotganini bilish uchun boshqa yo'l yo'q (server konsolga
    // kira olmaymiz, shuning uchun to'g'ridan-to'g'ri shu yerda ko'rsatamiz).
    const debug = [
      `platform=${tg.platform || "yo'q"}`,
      `version=${tg.version || "yo'q"}`,
      `initDataLen=${initData.length}`,
      `unsafeKeys=${tg.initDataUnsafe ? Object.keys(tg.initDataUnsafe).join("|") || "bo'sh" : "yo'q"}`,
      `rawHash=${location.hash ? location.hash.slice(0, 250) : "yo'q"}`,
    ].join(", ");
    throw new Error(`Ruxsat yo'q. Botni qaytadan oching.\n[debug: ${debug}]`);
  }
  return res;
}

// ---------- MAHSULOTLAR RO'YXATI ----------

async function loadProducts(query = "") {
  try {
    const res = await apiFetch(`${API.products}?q=${encodeURIComponent(query)}`);
    if (!res.ok) throw new Error("Mahsulotlarni yuklab bo'lmadi.");
    const data = await res.json();
    renderProducts(data.products || []);
  } catch (e) {
    showError(e.message || "Xatolik yuz berdi.");
  }
}

function renderProducts(products) {
  const list = el("product-list");
  list.innerHTML = "";

  if (products.length === 0) {
    list.innerHTML = '<p class="muted">Hech narsa topilmadi.</p>';
  }

  products.forEach((p) => {
    const card = document.createElement("div");
    card.className = "product-card";
    const discountBadge = p.discount_price
      ? `<div class="discount-badge">🏷 ${formatNum(p.discount_price)} so'm — ${discountDaysText(p.discount_days_left)}</div>`
      : "";
    card.innerHTML = `
      <div>
        <div class="name">${escapeHtml(p.name)}</div>
        <div class="stock">${formatNum(p.quantity)} dona bor</div>
        ${discountBadge}
      </div>
      <div class="add-icon">➕</div>
    `;
    card.addEventListener("click", () => { openedViaScan = false; openAddModal(p); });
    list.appendChild(card);
  });

  showScreen("products");
  renderCartBar();
}

function discountDaysText(daysLeft) {
  if (daysLeft === null || daysLeft === undefined) return "";
  if (daysLeft <= 0) return "bugun tugaydi";
  return `${daysLeft} kun qoldi`;
}

function escapeHtml(text) {
  const d = document.createElement("div");
  d.textContent = text;
  return d.innerHTML;
}

// O'QISHGA QULAY BO'LISHI UCHUN: minglik xonalarni bo'sh joy bilan
// ajratamiz (masalan 1000000 -> "1 000 000", 10000 -> "10 000"). Bu
// funksiya BUTUN ilova bo'ylab (narx, miqdor, summalar) yagona joydan
// ishlatiladi, shuning uchun o'zgartirish har yerda avtomatik qo'llanadi.
function formatNum(n) {
  const num = Math.round(Number(n) || 0);
  const sign = num < 0 ? "-" : "";
  return sign + Math.abs(num).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

// YOZISH JARAYONIDA FORMATLASH: summa maydonlariga (narx, naqd summasi va h.k.)
// foydalanuvchi raqam terayotganda darhol "100 000" ko'rinishida bo'sh joy
// bilan ajratib ko'rsatish uchun. Muhim: bu maydonlar HTML'da endi
// type="text" (avval type="number" edi) - chunki <input type="number">
// bo'sh joyni umuman qabul qilmaydi, brauzer uni tenglashtirib/o'chirib
// tashlaydi va shu sababli formatlash ishlamay qolgan edi. Qiymatni
// serverga/hisoblashga yuborishdan oldin har doim parseNum() bilan o'qish
// kerak (u bo'sh joylarni olib tashlab, haqiqiy raqamga aylantiradi).
function parseNum(value) {
  const cleaned = String(value ?? "").replace(/[^\d-]/g, "");
  if (cleaned === "" || cleaned === "-") return NaN;
  return parseFloat(cleaned);
}

function attachThousandsFormatting(input) {
  input.addEventListener("input", () => {
    const cursorFromEnd = input.value.length - input.selectionStart;
    const digitsOnly = input.value.replace(/[^\d]/g, "");
    input.value = digitsOnly === "" ? "" : formatNum(digitsOnly);
    const newPos = Math.max(0, input.value.length - cursorFromEnd);
    input.setSelectionRange(newPos, newPos);
  });
}

[
  "mixed-cash-input",
  "modal-price-input",
  "sklad-new-price-input",
  "sklad-new-sell-price-input",
  "sklad-new-min-price-input",
  "sklad-edit-price-input",
  "sklad-edit-sell-price-input",
  "sklad-edit-min-price-input",
].forEach((id) => attachThousandsFormatting(el(id)));

// YANGI: mahsulot qoldig'i do'kon egasi belgilagan "ogohlantirish
// chegarasi" (alert_quantity)dan pastga tushgan bo'lsa - qoldiq matnini
// qizil/qalin qilib, chegarani ham ko'rsatib qo'yamiz. Chegara
// belgilanmagan mahsulotlar uchun (alert_quantity == null) hech qanday
// ogohlantirish ko'rsatilmaydi - bu xuddi bot tarafidagi
// alerts.notify_stock_change() bilan bir xil mantiq (qarang: alerts.py).
function applyStockWarning(el, baseText, product) {
  const low = product.alert_quantity != null && product.quantity <= product.alert_quantity;
  el.textContent = low
    ? `${baseText} ⚠️ Kam qoldi! (chegara: ${formatNum(product.alert_quantity)} dona)`
    : baseText;
  el.classList.toggle("stock-low", low);
}

// ---------- SAVATGA QO'SHISH OYNASI ----------

// 5-BOSQICH: skanerlash orqali va qo'lda ("+" bosib) qo'shishning ikkalasi
// ham BIR XIL tekshiruv qoidalaridan foydalanishi uchun umumiy funksiya -
// narx/miqdor qoidalari ikki joyda (va kelajakda yana biror joyda) bir-biridan
// chetlashib ketmasligi uchun.
function cartValidationError(product, qty, price) {
  if (!qty || qty <= 0) return "Miqdor 0 dan katta bo'lishi kerak.";
  if (qty > product.quantity) return `Skladda faqat ${formatNum(product.quantity)} dona bor.`;
  if (!price || price <= 0) return "Narxni kiriting.";
  if (product.price && price < product.price) {
    return `Narx tannarxdan (${formatNum(product.price)} so'm) past bo'lishi mumkin emas.`;
  }
  if (product.min_price && price < product.min_price && !product.discount_price) {
    return `Narx eng past narxdan (${formatNum(product.min_price)} so'm) past bo'lishi mumkin emas.`;
  }
  return null;
}

function openAddModal(product) {
  currentModalProduct = product;
  el("modal-product-name").textContent = product.name;
  applyStockWarning(el("modal-product-stock"), `Skladda ${formatNum(product.quantity)} dona bor`, product);

  // Mahsulot savatda ALLAQACHON bor bo'lsa (masalan avval skanerlab
  // qo'shilgan bo'lsa) - shu yozuvning joriy qty/narxini ko'rsatamiz,
  // aks holda har safar "1 dona / standart narx"ga qaytarib
  // tashlagan bo'lardik.
  const existing = cart.find((c) => c.id === product.id);
  el("modal-qty-input").value = existing ? existing.qty : 1;
  const initialPrice = existing ? existing.price : (product.sell_price || product.price || "");
  el("modal-price-input").value = initialPrice === "" ? "" : formatNum(initialPrice);

  const hints = el("modal-price-hints");
  hints.innerHTML = "";
  const hintDefs = [
    ["sell_price", "💰 Savdo narxi", null],
    ["min_price", "🔻 Eng past narx", null],
    ["discount_price", "🏷 Chegirma narxi", product.discount_days_left],
  ];
  hintDefs.forEach(([key, label, daysLeft]) => {
    if (product[key]) {
      const btn = document.createElement("button");
      btn.className = key === "discount_price" ? "price-hint-btn price-hint-discount" : "price-hint-btn";
      const suffix = key === "discount_price" ? ` (${discountDaysText(daysLeft)})` : "";
      btn.textContent = `${label}: ${formatNum(product[key])}${suffix}`;
      btn.addEventListener("click", () => {
        el("modal-price-input").value = formatNum(product[key]);
      });
      hints.appendChild(btn);
    }
  });

  el("modal-add").classList.remove("hidden");
}

el("modal-cancel-btn").addEventListener("click", () => {
  el("modal-add").classList.add("hidden");
  currentModalProduct = null;
  if (openedViaScan) stopScanner();
  openedViaScan = false;
});

el("modal-add-btn").addEventListener("click", () => {
  if (!currentModalProduct) return;
  const qty = parseFloat(el("modal-qty-input").value);
  const price = parseNum(el("modal-price-input").value);
  const product = currentModalProduct;

  const err = cartValidationError(product, qty, price);
  if (err) {
    tg.showAlert(err);
    return;
  }

  const existing = cart.find((c) => c.id === product.id);
  if (existing) {
    existing.qty = qty;
    existing.price = price;
  } else {
    cart.push({ id: product.id, name: product.name, qty, price, stock: product.quantity });
  }

  el("modal-add").classList.add("hidden");
  currentModalProduct = null;
  renderCartBar();
  tg.HapticFeedback.notificationOccurred("success");

  // 6-BOSQICH: barkod skanerlab qo'shilgan bo'lsa - kamerani DARHOL
  // qayta ochamiz, foydalanuvchi 📷 tugmasini qayta bosishi shart emas.
  if (openedViaScan) {
    openedViaScan = false;
    continueScanning("sale", `✅ ${product.name} savatga qo'shildi`);
  }
});

// ---------- SAVAT PANELI (mahsulotlar ekrani ostida) ----------

function renderCartBar() {
  const badge = el("header-cart-badge");
  let bar = el("cart-bar");

  if (cart.length === 0) {
    if (bar) bar.remove();
    badge.classList.add("hidden");
    hideCrossSell();
    return;
  }

  const total = cart.reduce((sum, c) => sum + c.qty * c.price, 0);
  badge.textContent = String(cart.length);
  // 6-BOSQICH: savat "Sklad" bo'limida chalkashtirmasligi uchun faqat
  // "Savdo" bo'limida ko'rsatiladi (savat o'zi saqlanib qoladi).
  badge.classList.toggle("hidden", currentSection !== "sale");

  if (!bar) {
    bar = document.createElement("div");
    bar.id = "cart-bar";
    bar.className = "cart-bar";
    bar.addEventListener("click", openCartScreen);
    document.body.appendChild(bar);
  }
  bar.innerHTML = `<span>🛒 Savat: ${cart.length} tur</span><span>${formatNum(total)} so'm</span>`;
  bar.classList.toggle("hidden", currentSection !== "sale");

  if (currentSection === "sale") loadCrossSell();
}

// ---------- 3-BOSQICH: CROSS-SELL TAKLIFI ----------
// Matnli oqimdagi "💡 Odatda bu tovar(lar) bilan birga quyidagilar ham
// sotib olinadi" taklifi bilan bir xil mantiq (db.get_cross_sell_suggestions),
// lekin bu yerda bosilganda to'g'ridan-to'g'ri savatga qo'shish oynasi ochiladi.

function hideCrossSell() {
  const bar = el("cross-sell-bar");
  if (!bar) return;
  bar.classList.add("hidden");
  bar.innerHTML = "";
}

async function loadCrossSell() {
  if (cart.length === 0) {
    hideCrossSell();
    return;
  }
  try {
    const ids = cart.map((c) => c.id).join(",");
    const res = await apiFetch(`${API.crossSell}?ids=${encodeURIComponent(ids)}`);
    if (!res.ok) return;
    const data = await res.json();
    renderCrossSell(data.suggestions || []);
  } catch (e) {
    // Cross-sell ixtiyoriy qo'shimcha - xatosi asosiy savdo oqimini
    // to'xtatmasligi kerak, shuning uchun jim o'tkazib yuboramiz.
  }
}

function renderCrossSell(suggestions) {
  const bar = el("cross-sell-bar");
  if (!bar) return;
  const cartIds = new Set(cart.map((c) => c.id));
  const filtered = suggestions.filter((p) => !cartIds.has(p.id));

  if (filtered.length === 0) {
    hideCrossSell();
    return;
  }

  bar.innerHTML = "";
  const title = document.createElement("div");
  title.className = "cross-sell-title";
  title.textContent = "💡 Odatda bu bilan birga:";
  bar.appendChild(title);

  const chips = document.createElement("div");
  chips.className = "cross-sell-chips";
  filtered.forEach((p) => {
    const chip = document.createElement("button");
    chip.className = "cross-sell-chip";
    chip.textContent = `➕ ${p.name}`;
    chip.addEventListener("click", () => { openedViaScan = false; openAddModal(p); });
    chips.appendChild(chip);
  });
  bar.appendChild(chips);
  bar.classList.remove("hidden");
}

function openCartScreen() {
  renderCart();
  showScreen("cart");
}

// ---------- SAVAT EKRANI ----------

function renderCart() {
  const container = el("cart-items");
  container.innerHTML = "";
  let total = 0;

  cart.forEach((item, idx) => {
    const lineTotal = item.qty * item.price;
    total += lineTotal;
    const row = document.createElement("div");
    row.className = "cart-item";
    row.innerHTML = `
      <div>
        <div class="name">${escapeHtml(item.name)}</div>
        <div class="stock">${formatNum(item.qty)} x ${formatNum(item.price)} = ${formatNum(lineTotal)} so'm</div>
      </div>
      <div class="remove-btn">🗑</div>
    `;
    row.querySelector(".remove-btn").addEventListener("click", () => {
      cart.splice(idx, 1);
      renderCart();
      renderCartBar();
    });
    container.appendChild(row);
  });

  el("cart-total-amount").textContent = formatNum(total);
  resetPaymentSelection();
}

el("back-to-products-btn").addEventListener("click", () => {
  showScreen("products");
});

// ---------- TO'LOV TURI ----------

function resetPaymentSelection() {
  selectedPaymentMethod = null;
  document.querySelectorAll(".pay-btn").forEach((b) => b.classList.remove("selected"));
  el("mixed-box").classList.add("hidden");
  el("finalize-btn").classList.add("hidden");
}

document.querySelectorAll(".pay-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    selectedPaymentMethod = btn.dataset.method;
    document.querySelectorAll(".pay-btn").forEach((b) => b.classList.remove("selected"));
    btn.classList.add("selected");
    el("mixed-box").classList.toggle("hidden", selectedPaymentMethod !== "aralash");
    el("finalize-btn").classList.remove("hidden");
  });
});

// ---------- YAKUNLASH ----------

el("finalize-btn").addEventListener("click", async () => {
  if (!selectedPaymentMethod) return;
  if (cart.length === 0) return;

  const total = cart.reduce((sum, c) => sum + c.qty * c.price, 0);
  let mixedCash = null;
  if (selectedPaymentMethod === "aralash") {
    mixedCash = parseNum(el("mixed-cash-input").value);
    if (isNaN(mixedCash) || mixedCash < 0 || mixedCash > total) {
      tg.showAlert(`Naqd summasi 0 dan ${formatNum(total)} so'mgacha bo'lishi kerak.`);
      return;
    }
  }

  const body = {
    items: cart.map((c) => ({ product_id: c.id, qty: c.qty, price: c.price })),
    payment_method: selectedPaymentMethod,
  };
  if (mixedCash !== null) body.mixed_cash = mixedCash;

  el("finalize-btn").disabled = true;
  el("finalize-btn").textContent = "Yuborilmoqda...";

  try {
    const res = await apiFetch(API.sale, { method: "POST", body: JSON.stringify(body) });
    const data = await res.json();
    if (!res.ok) {
      tg.showAlert(saleErrorText(data));
      el("finalize-btn").disabled = false;
      el("finalize-btn").textContent = "✅ Savdoni yakunlash";
      return;
    }
    tg.HapticFeedback.notificationOccurred("success");
    tg.showPopup(
      { title: "✅ Savdo yakunlandi", message: `Jami: ${formatNum(data.total)} so'm` },
      () => tg.close()
    );
  } catch (e) {
    tg.showAlert(e.message || "Xatolik yuz berdi.");
    el("finalize-btn").disabled = false;
    el("finalize-btn").textContent = "✅ Savdoni yakunlash";
  }
});

function saleErrorText(data) {
  const map = {
    empty_cart: "Savat bo'sh.",
    invalid_payment_method: "To'lov turi noto'g'ri.",
    invalid_item: "Mahsulot ma'lumoti noto'g'ri.",
    product_not_found: "Mahsulot topilmadi (ehtimol o'chirilgan).",
    invalid_quantity: "Miqdor noto'g'ri.",
    not_enough_stock: `Skladda yetarli miqdor yo'q (bor: ${data.available}).`,
    price_below_min: `Narx eng past narxdan (${data.min_price}) past.`,
    price_below_cost: `Narx tannarxdan (${data.cost_price}) past.`,
    invalid_mixed_cash: "Naqd summasi noto'g'ri.",
  };
  return map[data.error] || "Savdoni yakunlashda xatolik yuz berdi.";
}

// ---------- 4-BOSQICH: BARKOD SKANERLASH (KAMERA) ----------
// html5-qrcode kutubxonasining PASTKI DARAJADAGI Html5Qrcode klassidan
// foydalanamiz (Html5QrcodeScanner emas) - chunki bizga kutubxonaning
// tayyor katta paneli (o'z tugmalari/torch va h.k. bilan) emas, faqat
// video oqimi kerak, qolgan UI (ramka, "yopish" tugmasi, status matni)
// ilovaning o'z uslubida (style.css) chizilgan.

const BARCODE_FORMATS = window.Html5QrcodeSupportedFormats
  ? [
      Html5QrcodeSupportedFormats.EAN_13,
      Html5QrcodeSupportedFormats.EAN_8,
      Html5QrcodeSupportedFormats.UPC_A,
      Html5QrcodeSupportedFormats.UPC_E,
      Html5QrcodeSupportedFormats.CODE_128,
      Html5QrcodeSupportedFormats.CODE_39,
      Html5QrcodeSupportedFormats.CODABAR,
      Html5QrcodeSupportedFormats.ITF,
      Html5QrcodeSupportedFormats.QR_CODE,
    ]
  : undefined;

let html5QrCode = null;
let scanHandled = false;
let torchFeature = null; // 4-BOSQICH: fonar (torch) - qo'llab-quvvatlansa shu yerga saqlanadi

// 6-BOSQICH: KETMA-KET SKANERLASH. Mahsulot skanerlab (modal-add yoki
// modal-sklad-add) ochilganda TRUE qilinadi; qo'lda ro'yxatdan bosib
// tanlaganda FALSE. Shu bayroqqa qarab, "Qo'shish" tugmasi bosilgach
// oynani shunchaki yopish o'rniga - kamerani DARHOL qayta ochib,
// keyingi mahsulotni skanerlashga tayyor turadi (foydalanuvchi har
// safar 📷 tugmasini qayta bosishiga hojat qolmaydi).
let openedViaScan = false;

// Skanerlab ketma-ket qo'shishda tg.showAlert() kabi TO'XTATUVCHI
// (OK bosishni talab qiladigan) oyna oqimni sekinlashtiradi - shuning
// uchun muvaffaqiyat xabari skaner oynasining o'zidagi status matnida
// (yashil, ~1.4 soniya) ko'rsatiladi, keyin darhol keyingi skanerlashga
// tayyor bo'ladi.
async function continueScanning(mode, successMessage) {
  scannerMode = mode;
  scanHandled = false;
  el("scanner-native-qr-btn").classList.add("hidden");
  el("modal-scanner").classList.remove("hidden");

  // TEZLASHTIRISH: kamera hali PAUZADA (pauseScannerFeed() tomonidan
  // to'xtatilgan, lekin obyekt yo'q qilinmagan) bo'lsa - uni to'liq
  // qayta ochish (stop+start, sekin va yangi getUserMedia so'rovi
  // talab qiladi) O'RNIGA shunchaki davom ettiramiz (deyarli darhol,
  // ruxsat qayta so'ralmaydi). Faqat kamera negadir yo'q qilingan
  // bo'lsa (masalan xatolik tufayli) - to'liq qayta ochamiz (zaxira).
  let resumed = false;
  if (html5QrCode) {
    try {
      html5QrCode.resume();
      resumed = true;
    } catch (e) {
      // Davom ettirib bo'lmadi - eskisini toza to'xtatib, pastda to'liq
      // qayta ochamiz (aks holda eski kamera oqimi ochiq qolib ketardi).
      await stopScanner();
    }
  }
  if (!resumed) {
    await openScanner(mode);
  }

  setScannerStatus(successMessage, "success");
  setTimeout(() => {
    if (html5QrCode) setScannerStatus(defaultScannerStatusText());
  }, 1400);
}
// YANGI REJA - 6-BOSQICH: endi UCHALA rejim ham ("sale", "sklad",
// "sklad_new") bitta-bittalab ishlaydi - skanerlandi -> kamera
// to'xtaydi -> tegishli oyna ochiladi -> keyingisi uchun foydalanuvchi
// 📷 tugmasini yana bosadi (avvalgi "sale" uchun uzluksiz-skanerlash
// dizayni bekor qilindi, qarang: handleSaleBarcodeScan izohi).
let scannerMode = "sale"; // "sale" | "sklad" | "sklad_new"

function setScannerStatus(text, type) {
  const box = el("scanner-status");
  box.textContent = text;
  box.classList.remove("scanner-status-success", "scanner-status-error");
  if (type === "success") box.classList.add("scanner-status-success");
  if (type === "error") box.classList.add("scanner-status-error");
}

function defaultScannerStatusText() {
  if (scannerMode === "sklad") return "Skladga qo'shish uchun barkodni skanerlang...";
  if (scannerMode === "sklad_new") return "Yangi mahsulot uchun barkodni skanerlang...";
  if (scannerMode === "sklad_edit") return "Tahrirlanayotgan mahsulot uchun barkodni skanerlang...";
  return "Kamerani barkodga to'g'rilang...";
}

// MUHIM (60-versiyada buzilgan, endi 53-versiyadagidek soddaga
// qaytarildi): bu qurilma/WebView'da HAR QANDAY qo'shimcha kamera
// bilan bog'liq chaqiruv (getCameras(), applyVideoConstraints(),
// videoConstraints, experimentalFeatures va h.k.) - hattoki ruxsat
// "allaqachon berilgan" deb hisoblansa ham - qayta ruxsat so'rovi
// sifatida ko'rinar ekan (foydalanuvchiga yana bir "kameraga ruxsat
// berasizmi?" so'rovi chiqadi). Shuning uchun endi FAQAT bitta
// Html5Qrcode obyekti va BITTA .start() chaqiruvi ({facingMode:
// "environment"} bilan) ishlatiladi - avvalgi (53-versiya) kabi.
async function startCameraWithFallback() {
  const scannerOptions = {
    formatsToSupport: BARCODE_FORMATS,
    verbose: false,
  };
  html5QrCode = new Html5Qrcode("scanner-reader", scannerOptions);
  await html5QrCode.start(
    { facingMode: "environment" },
    { fps: 15, qrbox: { width: 280, height: 170 } },
    onBarcodeDecoded, () => {}
  );
}

async function openScanner(mode = "sale") {
  scannerMode = mode;
  scanHandled = false;
  setScannerStatus(defaultScannerStatusText());
  el("scanner-native-qr-btn").classList.add("hidden");
  el("modal-scanner").classList.remove("hidden");

  if (!window.Html5Qrcode) {
    setScannerStatus("Skaner kutubxonasi yuklanmadi. Internetni tekshiring.", "error");
    return;
  }

  try {
    // MUHIM (aniqlandi): applyVideoConstraints() va
    // getRunningTrackCameraCapabilities() YANGI getUserMedia() so'rovi
    // YUBORMAYDI - ular allaqachon ochilgan kamera oqimi (track)
    // ustida ishlaydi, shuning uchun qayta ruxsat so'rovini
    // keltirib chiqarmaydi. Qayta ruxsat so'rovining haqiqiy sababi
    // avvalgi bir necha marta start()/getCameras() chaqirilishi edi
    // (bular HAR BIRI o'z getUserMedia so'rovini yuboradi) - shular
    // startCameraWithFallback()da yuqorida bitta start()ga tushirildi.
    // Shuning uchun fonar/avtofokus xavfsiz - qaytarildi.
    await startCameraWithFallback();
    await setupTorchButton();
    await setupContinuousFocus();
  } catch (err) {
    // Xato turiga qarab aniqroq maslahat beramiz - "ruxsat berilmadi" bilan
    // "kamera band"/"kamera topilmadi" sabablari butunlay boshqa yechim
    // talab qiladi, shuning uchun bittasiga umumlashtirmaymiz. Har holatda
    // ham qidiruv orqali barkodni QO'LDA kiritish - kamera holatidan
    // qat'i nazar doim ishlaydigan zaxira yo'l ekanini eslatamiz.
    // Diagnostika uchun: haqiqiy xatoni konsolga chiqaramiz - shunda
    // "Kamerani ochib bo'lmadi" kabi umumiy xabar ortida NIMA sodir
    // bo'lganini (masalan getCameras() bo'sh qaytdi, yoki kutubxona
    // network orqali yuklanmadi) aniqlash mumkin bo'ladi.
    console.error("Skaner kamerasini ochishda xatolik:", err);

    const name = err && err.name;
    let msg;
    if (name === "NotAllowedError" || name === "PermissionDeniedError") {
      msg = "Kameraga ruxsat berilmagan. Telefon sozlamalaridan Telegram ilovasiga kamera ruxsatini bering (odatda: Sozlamalar → Ilovalar → Telegram → Ruxsatlar → Kamera), so'ng Telegramni TO'LIQ yopib qayta oching.";
    } else if (name === "NotFoundError" || name === "DevicesNotFoundError") {
      msg = "Bu qurilmada kamera topilmadi.";
    } else if (name === "NotReadableError" || name === "TrackStartError") {
      msg = "Kamera band - boshqa ilova ishlatayotgan bo'lishi mumkin. Boshqa kamera ilovalarini yopib qayta urinib ko'ring.";
    } else {
      // Texnik tafsilotni ham ko'rsatamiz (qavs ichida) - "no_camera_found"
      // yoki boshqa noma'lum xato bo'lsa, keyingi safar buni ko'chirib
      // yuborish orqali muammoni aniqroq tashxislash mumkin bo'ladi.
      const detail = (err && (err.message || String(err))) || "noma'lum xato";
      msg = `Kamerani ochib bo'lmadi (${detail}).`;
    }
    setScannerStatus(`${msg} Yoki qidiruv maydoniga barkod raqamini qo'lda kiriting.`, "error");

    // Brauzer kamerasi ishlamasa - Telegram klientining O'Z ichki QR
    // skaneridan foydalanish imkoniyatini taklif qilamiz (agar mavjud
    // bo'lsa). Bu WebView'ning getUserMedia'siga BOG'LIQ EMAS, shuning
    // uchun ba'zi qurilmalar/klientlarda (masalan noutbukdagi Telegram
    // Desktop) brauzer kamerasi ishlamasa ham ishlashi mumkin. DIQQAT:
    // faqat QR-kod formatini o'qiydi, oddiy shtrix-kod (EAN/UPC) emas.
    if (window.Telegram && window.Telegram.WebApp && typeof window.Telegram.WebApp.showScanQrPopup === "function") {
      el("scanner-native-qr-btn").classList.remove("hidden");
    }
  }
}

// Telegram ilovasining o'z (native) QR skaneridan foydalanish - faqat
// oddiy brauzer kamerasi (getUserMedia) ishlamagan holatlar uchun
// zaxira variant sifatida. Faqat QR-kod formatini o'qiy oladi.
function openNativeQrScanner() {
  const tg = window.Telegram && window.Telegram.WebApp;
  if (!tg || typeof tg.showScanQrPopup !== "function") return;
  tg.showScanQrPopup({ text: "QR-kodni skanerlang" }, (text) => {
    tg.closeScanQrPopup();
    onBarcodeDecoded(text);
    return true; // popupni yopish uchun
  });
}

el("scanner-native-qr-btn").addEventListener("click", openNativeQrScanner);

// 8-BOSQICH: "continuous" avtofokus - qo'llab-quvvatlansa, kamera
// doimiy ravishda qayta fokuslanib turadi (masalan telefon harakatda
// bo'lsa yoki barkod yaqin/uzoq masofada bo'lsa ham aniq ko'rinishi
// uchun). Qo'llab-quvvatlanmasa - jim o'tkazamiz, hech qanday xato
// chiqmaydi (aksariyat qurilmalarda brauzer buni allaqachon o'zi
// qiladi).
async function setupContinuousFocus() {
  try {
    await html5QrCode.applyVideoConstraints({
      advanced: [{ focusMode: "continuous" }],
    });
  } catch (e) {
    // Qo'llab-quvvatlanmaydi - odatiy avtofokus bilan davom etamiz.
  }
}

// 4-BOSQICH: FONAR (TORCH). Har bir qurilma/brauzer buni qo'llab-
// quvvatlavermaydi (ayniqsa old kamera yoki ba'zi Android WebView'lar) -
// shuning uchun qo'llab-quvvatlanmasa tugma shunchaki YASHIRIN qoladi,
// xatolik chiqarilmaydi.
async function setupTorchButton() {
  const btn = el("scanner-torch-btn");
  btn.classList.add("hidden");
  btn.classList.remove("torch-on");
  torchFeature = null;
  try {
    const capabilities = html5QrCode.getRunningTrackCameraCapabilities();
    const feature = capabilities.torchFeature();
    if (feature && feature.isSupported && feature.isSupported()) {
      torchFeature = feature;
      btn.classList.remove("hidden");
    }
  } catch (e) {
    // Fonar bu qurilmada qo'llab-quvvatlanmaydi - tugma yashirin qoladi.
  }
}

el("scanner-torch-btn").addEventListener("click", async () => {
  if (!torchFeature) return;
  const btn = el("scanner-torch-btn");
  const turnOn = !btn.classList.contains("torch-on");
  try {
    await torchFeature.apply(turnOn);
    btn.classList.toggle("torch-on", turnOn);
  } catch (e) {
    tg.showAlert("Fonarni yoqib bo'lmadi.");
  }
});

// YANGI: kamerani TO'LIQ o'chirib qayta ochish (stop + yangi obyekt +
// start) sezilarli sekinlik va (WebView'da) qo'shimcha ruxsat so'rovi
// xavfini keltirib chiqarardi. Ketma-ket skanerlashda (bitta mahsulot
// qo'shilgach - keyingisiga o'tishda) buning o'rniga kamerani shunchaki
// PAUZA qilamiz (video oqim ham to'xtaydi, batareya tejaladi, lekin
// obyekt "tirik" qoladi) - keyin resumeScannerFeed() bilan DARHOL
// davom ettiramiz, hech qanday qayta ruxsat so'ralmaydi.
function pauseScannerFeed() {
  if (!html5QrCode) return;
  try {
    html5QrCode.pause(true);
  } catch (e) {
    // Pauza qila olmadi (masalan hali skanerlanmagan holatda) - keyingi
    // safar to'liq qayta ochamiz (fallback continueScanning() ichida bor).
  }
}

async function stopScanner() {
  el("scanner-torch-btn").classList.add("hidden");
  el("scanner-torch-btn").classList.remove("torch-on");
  torchFeature = null;
  if (!html5QrCode) return;
  try {
    if (html5QrCode.isScanning) {
      await html5QrCode.stop();
    }
    html5QrCode.clear();
  } catch (e) {
    // Kamera allaqachon to'xtagan bo'lishi mumkin - e'tiborsiz qoldiramiz.
  }
  html5QrCode = null;
}

async function closeScanner() {
  el("modal-scanner").classList.add("hidden");
  await stopScanner();
  openedViaScan = false;
  // YANGI REJA - 3-BOSQICH: agar foydalanuvchi "Yangi mahsulot"
  // oynasidan skaner ochib, hech narsa skanerlamasdan ✕ bosib yopsa -
  // to'ldirilgan maydonlar (nom/narx/miqdor) yo'qolib qolmasligi uchun
  // o'sha oynani qayta ko'rsatamiz.
  if (scannerMode === "sklad_new") {
    el("modal-sklad-new").classList.remove("hidden");
  }
  if (scannerMode === "sklad_edit") {
    el("modal-sklad-edit").classList.remove("hidden");
  }
}

// 5/7-BOSQICH (+ YANGI REJA 3/6-BOSQICH): skanerlangan barkodni rejimga
// qarab UCH XIL oqimga yo'naltiradi - HAMMASI bitta-bittalab (kamera
// to'xtatiladi, natija ko'rsatiladi, keyin foydalanuvchi tugma bilan
// qayta skanerlaydi):
//  - "sale" (Savdo): mahsulot topilsa - to'g'ridan-to'g'ri miqdor/narx
//    kiritish oynasi (modal-add, xuddi ro'yxatdan bosib tanlagandagi
//    BILAN BIR XIL) ochiladi - qarang: 6-BOSQICH izohi pastda.
//  - "sklad" (Sklad, mavjud mahsulotga miqdor qo'shish): "nechta dona
//    keldi?" oynasi ochiladi (narx so'ramaydi).
//  - "sklad_new" (Sklad, YANGI mahsulot yaratish): "Yangi mahsulot"
//    oynasidagi barkod maydoni to'ldiriladi - hech qanday qidiruv
//    qilinmaydi.
async function onBarcodeDecoded(decodedText) {
  if (scanHandled) return; // bitta kadrda bir necha marta chaqirilishining oldini olamiz
  scanHandled = true;
  tg.HapticFeedback.impactOccurred("light");

  // 7-BOSQICH: tahrirlash oynasidan skanerlanganda - shunchaki barkod
  // maydonini to'ldiramiz (bu YANGI mahsulot emas, aniq TANLANGAN
  // mahsulot tahrirlanyapti, shuning uchun "boshqa mahsulot topildimi"
  // tekshiruvi shart emas - tekshiruv "✅ Saqlash" bosilganda bo'ladi).
  if (scannerMode === "sklad_edit") {
    await stopScanner();
    el("modal-scanner").classList.add("hidden");
    el("sklad-edit-barcode-input").value = decodedText;
    el("modal-sklad-edit").classList.remove("hidden");
    scanHandled = false;
    return;
  }

  if (scannerMode === "sklad") {
    setScannerStatus("Qidirilmoqda...");
    pauseScannerFeed();
    el("modal-scanner").classList.add("hidden");
    await handleSkladBarcodeScan(decodedText);
    scanHandled = false;
    return;
  }

  // 3/9-BOSQICH (YANGILANDI): "Yangi mahsulot" oynasidan skanerlanganda
  // ENDI ham "sklad" rejimidagi kabi AVVAL barkod bo'yicha qidiruv
  // qilinadi - agar bu barkod allaqachon boshqa mahsulotga tegishli
  // bo'lsa, foydalanuvchi "yangi mahsulot" formasini bekorga to'ldirib
  // o'tirmasin deb, to'g'ridan-to'g'ri O'SHA MAHSULOTGA miqdor qo'shish
  // oynasi (modal-sklad-add) ochiladi. Faqat HAQIQATAN topilmasa, eski
  // xatti-harakat (barkodni "Yangi mahsulot" formasiga to'ldirib qo'yish)
  // ishlaydi.
  if (scannerMode === "sklad_new") {
    setScannerStatus("Qidirilmoqda...");
    await stopScanner();
    el("modal-scanner").classList.add("hidden");
    try {
      const res = await apiFetch(`${API.productByBarcode}?code=${encodeURIComponent(decodedText)}`);
      const data = await res.json();
      if (res.ok) {
        // Mahsulot TOPILDI - "Yangi mahsulot" oynasi ENDI ochilmaydi,
        // o'rniga shu mahsulotga miqdor qo'shish oynasi ochiladi.
        tg.showAlert(`Bu mahsulot allaqachon bor: "${data.product.name}". Nechta qo'shasiz?`);
        openedViaScan = true;
        openSkladAddModal(data.product);
        scanHandled = false;
        return;
      }
      if (data.error !== "not_found") {
        tg.showAlert("Barkod bo'yicha qidirishda xatolik yuz berdi.");
        el("modal-sklad-new").classList.remove("hidden");
        scanHandled = false;
        return;
      }
    } catch (e) {
      tg.showAlert(e.message || "Xatolik yuz berdi.");
      el("modal-sklad-new").classList.remove("hidden");
      scanHandled = false;
      return;
    }
    // Topilmadi - bu HAQIQATAN yangi mahsulot, barkodni formaga
    // to'ldirib, "Yangi mahsulot" oynasini qayta ko'rsatamiz.
    el("sklad-new-barcode-input").value = decodedText;
    el("modal-sklad-new").classList.remove("hidden");
    scanHandled = false;
    return;
  }

  setScannerStatus("Qidirilmoqda...");
  pauseScannerFeed();
  el("modal-scanner").classList.add("hidden");
  await handleSaleBarcodeScan(decodedText);
  scanHandled = false;
}

// YANGI REJA - 6-BOSQICH (DIZAYN QARORI O'ZGARDI): AVVAL bu yerda har
// bir skanerlashdan keyin mahsulot STANDART narxda/1 donada DARHOL
// savatga qo'shilar edi (kamera to'xtamasdan davom etardi) - endi,
// so'rovga ko'ra, barkod mos kelgan mahsulot uchun to'g'ridan-to'g'ri
// "Nechta sotildi? / Qancha so'mga sotildi?" oynasi (modal-add)
// ochiladi, xuddi ro'yxatdan qo'lda bosib tanlagandagi kabi - shunda
// sotuvchi HAR SAVDODA narxni (chegirma, kelishilgan narx va h.k.)
// ko'rib-tasdiqlab qo'sha oladi. Mahsulot topilmasa - xatolik xabari
// ko'rsatiladi (kamera allaqachon to'xtagan, qayta skanerlash uchun
// foydalanuvchi 📷 tugmasini yana bosishi kerak).
async function handleSaleBarcodeScan(decodedText) {
  try {
    const res = await apiFetch(`${API.productByBarcode}?code=${encodeURIComponent(decodedText)}`);
    const data = await res.json();
    if (!res.ok) {
      const msg = data.error === "not_found"
        ? `Bu barkod bo'yicha mahsulot topilmadi: ${decodedText}`
        : "Barkod bo'yicha qidirishda xatolik yuz berdi.";
      await stopScanner();
      tg.showAlert(msg);
      return;
    }
    showScreen("products");
    openedViaScan = true;
    openAddModal(data.product);
  } catch (e) {
    await stopScanner();
    tg.showAlert(e.message || "Xatolik yuz berdi.");
  }
}

// Sklad rejimi: mahsulotni barkod bo'yicha topadi (0 qolgan bo'lsa ham -
// api_product_by_barcode quantity bo'yicha filtrlamaydi) va topilsa
// miqdor kiritish oynasini ochadi.
//
// YANGI REJA - 5-BOSQICH: agar bu barkod bo'yicha HECH QANDAY mahsulot
// topilmasa, endi shunchaki "topilmadi" deb qo'yib qo'ymaymiz - buning
// o'rniga foydalanuvchiga xabar berib, darhol "Yangi mahsulot" oynasini
// shu barkod OLDINDAN TO'LDIRILGAN holda ochamiz (2-3-bosqichda
// qurilgan oyna) - shu bilan "mahsulot yo'q ekan, uni alohida qayta
// skladga kirib qo'lda qo'shish kerak" degan qo'shimcha qadam
// yo'qoladi.
async function handleSkladBarcodeScan(decodedText) {
  try {
    const res = await apiFetch(`${API.productByBarcode}?code=${encodeURIComponent(decodedText)}`);
    const data = await res.json();
    if (!res.ok) {
      if (data.error === "not_found") {
        await stopScanner();
        tg.showAlert(
          `Bu barkod bo'yicha mahsulot topilmadi:\n${decodedText}\n\n` +
          "Uni yangi mahsulot sifatida qo'shishingiz mumkin."
        );
        openSkladNewProductModal(decodedText);
        return;
      }
      await stopScanner();
      tg.showAlert("Barkod bo'yicha qidirishda xatolik yuz berdi.");
      return;
    }
    openedViaScan = true;
    openSkladAddModal(data.product);
  } catch (e) {
    await stopScanner();
    tg.showAlert(e.message || "Xatolik yuz berdi.");
  }
}

el("scan-btn").addEventListener("click", () => openScanner("sale"));
el("scanner-close-btn").addEventListener("click", closeScanner);

// Ilova fonga o'tsa (masalan foydalanuvchi Telegramdan chiqib ketsa) -
// kamerani ochiq qoldirmaslik uchun to'xtatamiz (batareya/maxfiylik).
document.addEventListener("visibilitychange", () => {
  if (document.hidden) closeScanner();
});

// ---------- QIDIRUV ----------

let searchTimeout = null;
el("search-input").addEventListener("input", (e) => {
  clearTimeout(searchTimeout);
  const q = e.target.value;
  searchTimeout = setTimeout(() => loadProducts(q), 300);
});

// LAZERLI SKANER: fizik USB/Bluetooth barkod-skanerlar odatda
// "klaviatura" sifatida ishlaydi - barkodni tez terib, oxirida Enter
// yuboradi. Foydalanuvchi shu maydonga fokus qo'yib skanerlasa, to'liq
// barkod kelgach (Enter) kamera bilan skanerlangandagi BILAN BIR XIL
// oqim (handleSaleBarcodeScan) ishga tushadi - qidiruv natijalari
// ro'yxatidan qo'lda bosib qidirish shart bo'lmaydi.
el("search-input").addEventListener("keydown", async (e) => {
  if (e.key !== "Enter") return;
  e.preventDefault();
  const code = e.target.value.trim();
  if (!code) return;
  clearTimeout(searchTimeout);
  tg.HapticFeedback.impactOccurred("light");
  e.target.value = "";
  loadProducts("");
  await handleSaleBarcodeScan(code);
});

// ---------- 6/7-BOSQICH: "SKLAD" BO'LIMI ----------
// "Savdo" bo'limidan mustaqil ekran: mahsulotni skanerlab yoki qidirib
// topib, kelgan tovar sonini kiritish orqali skladni to'ldirish.

function switchSection(section) {
  if (section === currentSection) return;
  currentSection = section;

  document.querySelectorAll(".section-tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.section === section);
  });

  if (section === "sklad") {
    showScreen("sklad");
    updateSkladPermissionUI();
    loadSkladProducts(el("sklad-search-input").value.trim());
  } else if (section === "profile") {
    showScreen("profile");
    loadProfile();
  } else {
    showScreen("products");
  }

  // Savat (agar bo'sh bo'lmasa) faqat "Savdo" bo'limida ko'rinishi kerak.
  renderCartBar();
}

// YANGI REJA - 8-BOSQICH: sotuvchida sklad ruxsati yo'q bo'lsa
// (owners.sellers_can_add_stock ega tomonidan o'chirilgan bo'lsa),
// "➕ Yangi mahsulot qo'shish" va 📷 (barkod skanerlash) tugmalari
// VIZUAL ravishda ham qulflanganini ko'rsatamiz - shunda foydalanuvchi
// tugmani bosib, faqat SHUNDAN KEYIN alert ko'rish o'rniga, oldindan
// ruxsati yo'qligini bilib oladi (mavjud mahsulot kartalaridagi 🔒/➕
// ikonkasi bilan bir xil g'oya - qarang: renderSkladProducts).
// Tugmalar hali ham bosiladi (disabled emas) - bosilganda tg.showAlert
// orqali aniq sabab ko'rsatiladi (pastdagi handlerlarga qarang).
function updateSkladPermissionUI() {
  const newBtn = el("sklad-new-product-btn");
  const scanBtn = el("sklad-scan-btn");
  newBtn.textContent = currentUser.canAddStock
    ? "➕ Yangi mahsulot qo'shish"
    : "🔒 Yangi mahsulot qo'shish";
  newBtn.classList.toggle("locked-btn", !currentUser.canAddStock);
  scanBtn.classList.toggle("locked-btn", !currentUser.canAddStock);
}

el("tab-sale").addEventListener("click", () => switchSection("sale"));
el("tab-sklad").addEventListener("click", () => switchSection("sklad"));
el("tab-profile").addEventListener("click", () => switchSection("profile"));

// ---------- YANGI: PROFIL EKRANI (do'kon egasi/sotuvchi) ----------
// "👑 Admin panel"dagi Statistika ekrani bilan bir xil uslub - qarang:
// index.html #screen-profile, style.css "PROFIL EKRANI" bo'limi.

const PROFILE_STATUS_LABELS = {
  active: "✅ Faol",
  trial: "🎁 Sinov muddati",
  expired: "⌛ Muddati tugagan",
  blocked: "⛔ Bloklangan",
  pending_trial: "⏳ Tasdiqlanmagan",
  unknown: "❔ Noma'lum",
};

function profileStatusBadgeHtml(status) {
  const label = PROFILE_STATUS_LABELS[status] || PROFILE_STATUS_LABELS.unknown;
  return `<span class="status-badge status-${escapeHtml(status || "unknown")}">${label}</span>`;
}

function profileDaysLeftText(daysLeft) {
  if (daysLeft == null) return "—";
  return daysLeft >= 0 ? `${daysLeft} kun` : `${Math.abs(daysLeft)} kun oldin tugagan`;
}

async function loadProfile() {
  const card = el("profile-header-card");
  card.innerHTML = '<p class="muted">Yuklanmoqda...</p>';
  el("profile-stats-grid").innerHTML = "";
  el("profile-detail-body").innerHTML = "";
  try {
    const res = await apiFetch(API.profile);
    if (!res.ok) throw new Error("Profilni yuklab bo'lmadi.");
    const data = await res.json();
    renderProfile(data);
  } catch (e) {
    card.innerHTML = `<p class="muted">${escapeHtml(e.message || "Xatolik yuz berdi.")}</p>`;
  }
}

function renderProfile(data) {
  const isOwner = data.role === "owner";

  // ---- sarlavha kartasi ----
  const icon = isOwner ? "🏪" : "🧑‍💼";
  const title = isOwner
    ? (data.shop_name || "Do'kon egasi")
    : (data.seller_name || "Sotuvchi");
  const sub = isOwner
    ? [data.owner_name, data.branch_name ? `📍 ${data.branch_name}` : null].filter(Boolean).join(" · ") || `ID: ${data.telegram_id}`
    : [data.shop_name, data.branch_name].filter(Boolean).join(" · ") || `ID: ${data.telegram_id}`;
  el("profile-header-card").innerHTML = `
    <div class="profile-header-icon">${icon}</div>
    <div class="profile-header-info">
      <div class="profile-header-title">${escapeHtml(title)}</div>
      <div class="profile-header-sub">${escapeHtml(sub)}</div>
    </div>
    <div class="profile-header-badge">${profileStatusBadgeHtml(data.status)}</div>
  `;

  // ---- statistika kartalari ----
  const cards = isOwner
    ? [
        ["🧑‍💼", formatNum(data.sellers_count), "Sotuvchilar", null],
        ["🏢", formatNum(data.branches_count), "Filiallar", null],
        ["📦", formatNum(data.products_count), "Mahsulotlar", null],
        ["🔐", data.sellers_can_add_stock ? "🔓 Yoqilgan" : "🚫 O'chirilgan", "Sotuvchilarga sklad ruxsati (bosib o'zgartiring)", "stock-perm"],
      ]
    : [
        ["🏢", data.branch_name || "—", "Filial", null],
        ["🔐", data.can_add_stock ? "✅ Bor" : "🚫 Yo'q", "Sklad qo'shish huquqi", null],
      ];
  el("profile-stats-grid").innerHTML = cards.map(([cardIcon, value, label, action]) => `
    <div class="admin-stat-card${action ? " clickable" : ""}"${action ? ` data-action="${action}"` : ""}>
      <div class="admin-stat-value">${cardIcon} ${escapeHtml(String(value))}</div>
      <div class="admin-stat-label">${escapeHtml(label)}</div>
    </div>
  `).join("");
  if (isOwner) {
    const permCard = el("profile-stats-grid").querySelector('[data-action="stock-perm"]');
    if (permCard) {
      permCard.addEventListener("click", () => toggleSkladPermission(!data.sellers_can_add_stock));
    }
  }

  // ---- tafsilotlar ro'yxati ----
  const rows = isOwner
    ? [
        ["Telegram ID", data.telegram_id],
        ["Ega F.I.Sh.", data.owner_name || "—"],
        ["Telefon", data.phone_number || "—"],
        ["Obuna holati", PROFILE_STATUS_LABELS[data.status] || PROFILE_STATUS_LABELS.unknown],
        ["Obuna muddati", data.subscription_until || "—"],
        ["Qolgan kun", profileDaysLeftText(data.days_left)],
      ]
    : [
        ["Telegram ID", data.telegram_id],
        ["Ism", data.seller_name || "—"],
        ["Telefon", data.phone_number || "—"],
        ["Do'kon", data.shop_name || "—"],
        ["Filial", data.branch_name || "—"],
        ["Do'kon obunasi", PROFILE_STATUS_LABELS[data.status] || PROFILE_STATUS_LABELS.unknown],
      ];
  el("profile-detail-body").innerHTML = rows.map(([k, v]) => `
    <div class="admin-detail-row"><span class="k">${escapeHtml(k)}</span><span class="v">${escapeHtml(String(v))}</span></div>
  `).join("");

  // ---- filiallar (faqat do'kon egasi almashtira oladi) ----
  const branchesSection = el("profile-branches-section");
  if (isOwner) {
    branchesSection.classList.remove("hidden");
    loadProfileBranches();
  } else {
    branchesSection.classList.add("hidden");
  }
}

// MINI APP ICHIDAN FILIALGA O'TISH: handlers/branches.py "🏢 Filiallar"dagi
// bilan bir xil amal, faqat mini app'dan. Faqat do'kon egasiga ko'rinadi.
async function loadProfileBranches() {
  const list = el("profile-branches-list");
  list.innerHTML = '<p class="muted">Yuklanmoqda...</p>';
  try {
    const res = await apiFetch(API.branches);
    if (!res.ok) throw new Error("Filiallarni yuklab bo'lmadi.");
    const data = await res.json();
    renderProfileBranches(data.branches || [], data.current_branch_id);
  } catch (e) {
    list.innerHTML = `<p class="muted">${escapeHtml(e.message || "Xatolik yuz berdi.")}</p>`;
  }
}

function renderProfileBranches(branches, currentBranchId) {
  const list = el("profile-branches-list");
  list.innerHTML = "";

  const rows = [{ id: null, name: "🏠 Bosh filial" }, ...branches.map((b) => ({ id: b.id, name: `🏢 ${b.name}` }))];
  rows.forEach((b) => {
    const isCurrent = (b.id || null) === (currentBranchId || null);
    const row = document.createElement("div");
    row.className = `admin-settings-row branch-row${isCurrent ? " current" : ""}`;
    row.innerHTML = `
      <div class="value">${escapeHtml(b.name)}</div>
      ${isCurrent ? '<span class="branch-check">✅</span>' : ""}
    `;
    if (!isCurrent) {
      row.addEventListener("click", () => switchProfileBranch(b.id, b.name));
    }
    list.appendChild(row);
  });

  if (branches.length === 0) {
    const hint = document.createElement("p");
    hint.className = "muted";
    hint.textContent = "Hozircha qo'shimcha filial yo'q - botning \"🏢 Filiallar\" bo'limidan qo'shishingiz mumkin.";
    list.appendChild(hint);
  }
}

async function switchProfileBranch(branchId, branchName) {
  try {
    const res = await apiFetch(API.branchesSwitch, {
      method: "POST",
      body: JSON.stringify({ branch_id: branchId }),
    });
    if (!res.ok) throw new Error("Filialga o'tib bo'lmadi.");
    tg.HapticFeedback.notificationOccurred("success");
    tg.showAlert(`✅ "${branchName.replace(/^[🏠🏢]\s*/, "")}" filialiga o'tdingiz.`);
    loadProfile();
  } catch (e) {
    tg.showAlert(e.message || "Xatolik yuz berdi.");
  }
}

// MINI APP ICHIDAN SKLAD RUXSATINI YOQISH/O'CHIRISH: handlers/sellers.py
// dagi bot orqali "🔐 Sklad ruxsati" bilan bir xil amal, faqat Profil
// ekranidagi statistika kartasidan (bosib almashtiriladi).
async function toggleSkladPermission(nextAllowed) {
  try {
    const res = await apiFetch(API.skladPermission, {
      method: "POST",
      body: JSON.stringify({ allowed: nextAllowed }),
    });
    if (!res.ok) throw new Error("Ruxsatni o'zgartirib bo'lmadi.");
    tg.HapticFeedback.notificationOccurred("success");
    tg.showAlert(nextAllowed
      ? "🔓 Sotuvchilarga skladga tovar qo'shishga ruxsat berildi."
      : "🚫 Sotuvchilarga skladga tovar qo'shish taqiqlandi (faqat ega qo'sha oladi).");
    loadProfile();
  } catch (e) {
    tg.showAlert(e.message || "Xatolik yuz berdi.");
  }
}

async function loadSkladProducts(query = "") {
  try {
    const res = await apiFetch(`${API.skladProducts}?q=${encodeURIComponent(query)}`);
    if (!res.ok) throw new Error("Mahsulotlarni yuklab bo'lmadi.");
    const data = await res.json();
    renderSkladProducts(data.products || []);
  } catch (e) {
    tg.showAlert(e.message || "Xatolik yuz berdi.");
  }
}

function renderSkladProducts(products) {
  const list = el("sklad-product-list");
  list.innerHTML = "";

  if (products.length === 0) {
    list.innerHTML = '<p class="muted">Hech narsa topilmadi.</p>';
  }

  products.forEach((p) => {
    const card = document.createElement("div");
    card.className = "product-card";
    // api_products'dan farqli (u yerda "0 dona" oddiy holat emas, chunki
    // faqat sotiladigan mahsulotlar chiqadi) - Sklad ro'yxatida 0/manfiy
    // qolgan mahsulotni AJRATIB ko'rsatamiz, chunki aynan shularga tovar
    // kiritish kerak bo'ladi.
    const lowBadge = p.quantity <= 0
      ? '<div class="discount-badge">⚠️ Skladda yo\'q</div>'
      : "";
    const actionIcon = currentUser.canAddStock ? "➕" : "🔒";
    // 7-BOSQICH: tahrirlash (✏️) tugmasi FAQAT do'kon egasiga ko'rinadi -
    // narx/nom o'zgartirish sotuvchiga berilgan "sklad ruxsati"dan
    // (faqat miqdor qo'shish) farqli, jiddiyroq huquq.
    const editBtn = currentUser.role === "owner"
      ? '<div class="edit-icon" title="Tahrirlash">✏️</div>'
      : "";
    card.innerHTML = `
      <div>
        <div class="name">${escapeHtml(p.name)}</div>
        <div class="stock">${formatNum(p.quantity)} dona bor</div>
        ${lowBadge}
      </div>
      <div class="card-actions">
        ${editBtn}
        <div class="add-icon">${actionIcon}</div>
      </div>
    `;
    card.addEventListener("click", () => { openedViaScan = false; openSkladAddModal(p); });
    if (currentUser.role === "owner") {
      card.querySelector(".edit-icon").addEventListener("click", (e) => {
        e.stopPropagation();
        openSkladEditModal(p);
      });
    }
    list.appendChild(card);
  });
}

let currentSkladProduct = null;

function openSkladAddModal(product) {
  if (!currentUser.canAddStock) {
    tg.showAlert("🔒 Sizga skladga tovar qo'shishga ruxsat berilmagan. Do'kon egasiga murojaat qiling.");
    return;
  }
  currentSkladProduct = product;
  el("sklad-modal-product-name").textContent = product.name;
  applyStockWarning(el("sklad-modal-product-stock"), `Hozir skladda ${formatNum(product.quantity)} dona bor`, product);
  el("sklad-modal-qty-input").value = 1;
  el("modal-sklad-add").classList.remove("hidden");
}

el("sklad-modal-cancel-btn").addEventListener("click", () => {
  el("modal-sklad-add").classList.add("hidden");
  currentSkladProduct = null;
  if (openedViaScan) stopScanner();
  openedViaScan = false;
});

el("sklad-modal-add-btn").addEventListener("click", async () => {
  if (!currentSkladProduct) return;
  const qty = parseFloat(el("sklad-modal-qty-input").value);
  if (!qty || qty <= 0) {
    tg.showAlert("Miqdor 0 dan katta bo'lishi kerak.");
    return;
  }

  const btn = el("sklad-modal-add-btn");
  const productId = currentSkladProduct.id;
  const productName = currentSkladProduct.name;
  const viaScan = openedViaScan;
  btn.disabled = true;
  btn.textContent = "Yuborilmoqda...";

  try {
    const res = await apiFetch(API.skladAddQuantity, {
      method: "POST",
      body: JSON.stringify({ product_id: productId, qty }),
    });
    const data = await res.json();
    if (!res.ok) {
      tg.showAlert(skladErrorText(data));
      return;
    }

    tg.HapticFeedback.notificationOccurred("success");
    el("modal-sklad-add").classList.add("hidden");
    currentSkladProduct = null;
    loadSkladProducts(el("sklad-search-input").value.trim());

    // 6-BOSQICH: skanerlab qo'shilgan bo'lsa - tg.showAlert() (OK
    // bosishni talab qiladi) O'RNIGA kamerani darhol qayta ochamiz va
    // natijani skaner oynasining o'zida (yashil status) ko'rsatamiz -
    // shunda ketma-ket skanerlash to'xtamaydi. Qo'lda (ro'yxatdan
    // bosib) qo'shilgan bo'lsa - odatdagidek to'liq xabar chiqadi.
    if (viaScan) {
      openedViaScan = false;
      continueScanning(
        "sklad",
        `✅ ${productName}: ${formatNum(data.old_quantity)} → ${formatNum(data.new_quantity)} dona`
      );
    } else {
      tg.showAlert(`✅ ${data.name}: ${formatNum(data.old_quantity)} → ${formatNum(data.new_quantity)} dona.`);
    }
  } catch (e) {
    tg.showAlert(e.message || "Xatolik yuz berdi.");
  } finally {
    btn.disabled = false;
    btn.textContent = "➕ Skladga qo'shish";
  }
});

function skladErrorText(data) {
  const map = {
    invalid_quantity: "Miqdor noto'g'ri.",
    invalid_item: "Mahsulot ma'lumoti noto'g'ri.",
    missing_product: "Mahsulot tanlanmagan.",
    product_not_found: "Mahsulot topilmadi (ehtimol o'chirilgan).",
    forbidden: "🔒 Sizga skladga tovar qo'shishga ruxsat berilmagan.",
  };
  return map[data.error] || "Skladga qo'shishda xatolik yuz berdi.";
}

// YANGI REJA - 2-BOSQICH: SKLAD - butunlay YANGI mahsulot yaratish
// (bot bilan matnli yozishmasdan, to'g'ridan-to'g'ri mini-appdan).
// Barkod bilan to'ldirish (skanerlash) 3-4-bosqichlarda shu yerga
// qo'shiladi - hozircha faqat nom/narx/miqdor.
function openSkladNewProductModal(prefilledBarcode = "") {
  if (!currentUser.canAddStock) {
    tg.showAlert("🔒 Sizga skladga tovar qo'shishga ruxsat berilmagan. Do'kon egasiga murojaat qiling.");
    return;
  }
  el("sklad-new-name-input").value = "";
  el("sklad-new-price-input").value = "";
  el("sklad-new-sell-price-input").value = "";
  el("sklad-new-min-price-input").value = "";
  el("sklad-new-quantity-input").value = 1;
  el("sklad-new-alert-input").value = "";
  el("sklad-new-barcode-input").value = prefilledBarcode;
  el("modal-sklad-new").classList.remove("hidden");
}

el("sklad-new-product-btn").addEventListener("click", () => openSkladNewProductModal());

el("sklad-new-cancel-btn").addEventListener("click", () => {
  el("modal-sklad-new").classList.add("hidden");
});

// 9-BOSQICH: SKLAD TARIXI - "kim, qachon, qancha mahsulot qo'shgani".
// Server allaqachon filtrlab (faqat sklad turdagi amallar) va oxirgi
// 50 tasini yuborgani uchun bu yerda faqat ro'yxatni chizamiz.
async function openSkladHistory() {
  el("modal-sklad-history").classList.remove("hidden");
  const list = el("sklad-history-list");
  list.innerHTML = '<p class="muted">Yuklanmoqda...</p>';
  try {
    const res = await apiFetch(API.skladHistory);
    if (!res.ok) throw new Error("history_failed");
    const data = await res.json();
    renderSkladHistory(data.history || []);
  } catch (e) {
    list.innerHTML = '<p class="muted">Tarixni yuklab bo\'lmadi. Qayta urinib ko\'ring.</p>';
  }
}

function renderSkladHistory(items) {
  const list = el("sklad-history-list");
  list.innerHTML = "";
  if (items.length === 0) {
    list.innerHTML = '<p class="muted">Hozircha sklad tarixi bo\'sh.</p>';
    return;
  }
  items.forEach((h) => {
    const row = document.createElement("div");
    row.className = "history-row";
    row.innerHTML = `
      <div class="history-row-top">
        <span class="history-action">${escapeHtml(h.action)}</span>
        <span class="history-time">${escapeHtml(h.created_at || "")}</span>
      </div>
      <div class="history-details">${escapeHtml(h.details || "")}</div>
      <div class="history-actor">👤 ${escapeHtml(h.actor_name || "Noma'lum")}</div>
    `;
    list.appendChild(row);
  });
}

el("sklad-history-btn").addEventListener("click", () => openSkladHistory());
el("sklad-history-close-btn").addEventListener("click", () => {
  el("modal-sklad-history").classList.add("hidden");
});

// YANGI REJA - 3-BOSQICH: "Yangi mahsulot" oynasidagi 📷 tugmasi -
// oynani vaqtincha yashiradi, kamerani "sklad_new" rejimida ochadi;
// skaner o'qigach (onBarcodeDecoded) barkod maydoni to'ldiriladi va
// oyna avtomatik qayta ko'rinadi.
el("sklad-new-scan-btn").addEventListener("click", () => {
  el("modal-sklad-new").classList.add("hidden");
  openScanner("sklad_new");
});

function confirmAsync(message) {
  return new Promise((resolve) => tg.showConfirm(message, resolve));
}

el("sklad-new-save-btn").addEventListener("click", async () => {
  const name = el("sklad-new-name-input").value.trim();
  const price = parseNum(el("sklad-new-price-input").value);
  const sellPriceRaw = el("sklad-new-sell-price-input").value;
  const minPriceRaw = el("sklad-new-min-price-input").value;
  const alertQtyRaw = el("sklad-new-alert-input").value;
  const quantity = parseFloat(el("sklad-new-quantity-input").value);

  if (!name) {
    tg.showAlert("Mahsulot nomini kiriting.");
    return;
  }
  if (isNaN(price) || price < 0) {
    tg.showAlert("Tannarxni to'g'ri kiriting.");
    return;
  }
  if (isNaN(quantity) || quantity < 0) {
    tg.showAlert("Miqdorni to'g'ri kiriting.");
    return;
  }

  const body = { name, price, quantity };
  const barcode = el("sklad-new-barcode-input").value.trim();
  if (barcode) {
    body.barcode = barcode;
  }

  let sellPrice = null;
  if (sellPriceRaw !== "") {
    sellPrice = parseNum(sellPriceRaw);
    if (isNaN(sellPrice) || sellPrice < 0) {
      tg.showAlert("Sotish narxini to'g'ri kiriting.");
      return;
    }
    body.sell_price = sellPrice;
  }

  let minPrice = null;
  if (minPriceRaw !== "") {
    minPrice = parseNum(minPriceRaw);
    if (isNaN(minPrice) || minPrice < 0) {
      tg.showAlert("Eng past narxni to'g'ri kiriting.");
      return;
    }
    body.min_price = minPrice;
  }

  if (alertQtyRaw !== "") {
    const alertQty = parseFloat(alertQtyRaw);
    if (isNaN(alertQty) || alertQty < 0) {
      tg.showAlert("Ogohlantirish sonini to'g'ri kiriting.");
      return;
    }
    body.alert_quantity = alertQty;
  }

  // 5-BOSQICH: sotish narxi tannarxdan PAST kiritilsa - bu ko'pincha
  // xato terish (masalan nol yetishmay qolgan) belgisi bo'ladi va shu
  // narxda sotilsa do'kon ZARARDA qoladi. Shuning uchun jim o'tkazib
  // yubormasdan, aniq ogohlantirib tasdiqlatib olamiz.
  if (sellPrice !== null && sellPrice < price) {
    const ok = await confirmAsync(
      `Diqqat: sotish narxi (${formatNum(sellPrice)} so'm) tannarxdan (${formatNum(price)} so'm) PAST!\n\n` +
      "Shu narxda sotilsa, har bir donada zarar ko'rasiz. Shunday davom etamizmi?"
    );
    if (!ok) return;
  }

  // 2-BOSQICH: agar "eng past narx" umuman kiritilmasa - buni indamay
  // o'tkazib yubormaymiz, chunki bu maydon sotuvchilarning narxni juda
  // pastga tushirib yuborishining OLDINI OLADI. Shuning uchun kiritilmasa
  // ANIQ OGOHLANTIRIB, davom etish/qaytib kiritishni so'raymiz.
  if (minPrice === null) {
    const ok = await confirmAsync(
      "Eng past narx kiritilmadi. Bunday holda sotuvchilar bu mahsulotni istalgan (hatto juda past) narxda sotib yuborishi mumkin.\n\nShunday davom etamizmi?"
    );
    if (!ok) return;
  } else if (minPrice < price) {
    // YANGI: eng past narx tannarxdan PAST kiritilsa ham, sotish narxidagi
    // kabi jim o'tkazib yubormasdan ogohlantiramiz - aks holda sotuvchi shu
    // "eng past narx"gacha tushib, baribir zararda sotib yuborishi mumkin.
    const ok = await confirmAsync(
      `Diqqat: eng past narx (${formatNum(minPrice)} so'm) tannarxdan (${formatNum(price)} so'm) PAST!\n\n` +
      "Sotuvchilar shu narxgacha tushirib sotsa ham zarar ko'rasiz. Shunday davom etamizmi?"
    );
    if (!ok) return;
  }

  await saveSkladNewProduct(body);
});

async function saveSkladNewProduct(body) {
  const btn = el("sklad-new-save-btn");
  btn.disabled = true;
  btn.textContent = "Saqlanmoqda...";

  try {
    const res = await apiFetch(API.skladCreateProduct, {
      method: "POST",
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      tg.showAlert(skladCreateErrorText(data));
      return;
    }

    tg.HapticFeedback.notificationOccurred("success");
    el("modal-sklad-new").classList.add("hidden");
    tg.showAlert(`✅ "${data.product.name}" mahsuloti qo'shildi.`);
    loadSkladProducts(el("sklad-search-input").value.trim());
  } catch (e) {
    tg.showAlert(e.message || "Xatolik yuz berdi.");
  } finally {
    btn.disabled = false;
    btn.textContent = "✅ Qo'shish";
  }
}

function skladCreateErrorText(data) {
  const map = {
    missing_name: "Mahsulot nomini kiriting.",
    invalid_price: "Tannarx noto'g'ri.",
    invalid_sell_price: "Sotish narxi noto'g'ri.",
    invalid_min_price: "Eng past narx noto'g'ri.",
    invalid_quantity: "Miqdor noto'g'ri.",
    forbidden: "🔒 Sizga skladga mahsulot qo'shishga ruxsat berilmagan.",
    barcode_exists: `Bu barkod allaqachon "${data.product ? data.product.name : ""}" mahsulotida bor.`,
  };
  return map[data.error] || "Mahsulot qo'shishda xatolik yuz berdi.";
}

// 7-BOSQICH: mavjud mahsulotni tahrirlash (FAQAT do'kon egasi - qarang:
// renderSkladProducts yuqorida, tugma faqat currentUser.role === "owner"
// bo'lsa ko'rinadi; shunga qaramay, xavfsizlik uchun backend - webapp.py
// api_sklad_update_product - ham alohida is_owner_level tekshiradi).
let currentEditProduct = null;

function openSkladEditModal(product) {
  currentEditProduct = product;
  el("sklad-edit-name-input").value = product.name;
  el("sklad-edit-price-input").value = product.price != null ? formatNum(product.price) : "";
  el("sklad-edit-sell-price-input").value = product.sell_price != null ? formatNum(product.sell_price) : "";
  el("sklad-edit-min-price-input").value = product.min_price != null ? formatNum(product.min_price) : "";
  el("sklad-edit-alert-input").value = product.alert_quantity ?? "";
  el("sklad-edit-barcode-input").value = product.barcode || "";
  el("modal-sklad-edit").classList.remove("hidden");
}

el("sklad-edit-cancel-btn").addEventListener("click", () => {
  el("modal-sklad-edit").classList.add("hidden");
  currentEditProduct = null;
});

// Tahrirlash oynasidagi 📷 - faqat barkod maydonini to'ldiradi (qidiruv/
// tekshiruv qilmaydi - takrorlanish tekshiruvi "✅ Saqlash" bosilganda,
// backendda amalga oshadi).
el("sklad-edit-scan-btn").addEventListener("click", () => {
  el("modal-sklad-edit").classList.add("hidden");
  openScanner("sklad_edit");
});

el("sklad-edit-save-btn").addEventListener("click", async () => {
  if (!currentEditProduct) return;

  const name = el("sklad-edit-name-input").value.trim();
  const price = parseNum(el("sklad-edit-price-input").value);
  if (!name) {
    tg.showAlert("Mahsulot nomini kiriting.");
    return;
  }
  if (isNaN(price) || price < 0) {
    tg.showAlert("Tannarxni to'g'ri kiriting.");
    return;
  }

  const sellPriceRaw = el("sklad-edit-sell-price-input").value;
  const minPriceRaw = el("sklad-edit-min-price-input").value;
  const alertQtyRaw = el("sklad-edit-alert-input").value;
  const barcodeRaw = el("sklad-edit-barcode-input").value.trim();

  if (sellPriceRaw !== "" && (isNaN(parseNum(sellPriceRaw)) || parseNum(sellPriceRaw) < 0)) {
    tg.showAlert("Sotish narxini to'g'ri kiriting.");
    return;
  }
  if (minPriceRaw !== "" && (isNaN(parseNum(minPriceRaw)) || parseNum(minPriceRaw) < 0)) {
    tg.showAlert("Eng past narxni to'g'ri kiriting.");
    return;
  }
  if (alertQtyRaw !== "" && (isNaN(parseFloat(alertQtyRaw)) || parseFloat(alertQtyRaw) < 0)) {
    tg.showAlert("Ogohlantirish sonini to'g'ri kiriting.");
    return;
  }

  const body = {
    product_id: currentEditProduct.id,
    name,
    price,
    sell_price: sellPriceRaw === "" ? "" : parseNum(sellPriceRaw),
    min_price: minPriceRaw === "" ? "" : parseNum(minPriceRaw),
    alert_quantity: alertQtyRaw === "" ? "" : parseFloat(alertQtyRaw),
    barcode: barcodeRaw,
  };

  // YANGI: "Yangi mahsulot" oynasidagi bilan BIR XIL ogohlantirishlar -
  // avval bu yerda umuman yo'q edi, shuning uchun tannarxdan past sotish/
  // eng past narx kiritilsa ham jim saqlanardi.
  if (sellPriceRaw !== "") {
    const sellPrice = parseNum(sellPriceRaw);
    if (sellPrice < price) {
      const ok = await confirmAsync(
        `Diqqat: sotish narxi (${formatNum(sellPrice)} so'm) tannarxdan (${formatNum(price)} so'm) PAST!\n\n` +
        "Shu narxda sotilsa, har bir donada zarar ko'rasiz. Shunday davom etamizmi?"
      );
      if (!ok) return;
    }
  }

  if (minPriceRaw === "") {
    const ok = await confirmAsync(
      "Eng past narx kiritilmadi. Bunday holda sotuvchilar bu mahsulotni istalgan (hatto juda past) narxda sotib yuborishi mumkin.\n\nShunday davom etamizmi?"
    );
    if (!ok) return;
  } else {
    const minPrice = parseNum(minPriceRaw);
    if (minPrice < price) {
      const ok = await confirmAsync(
        `Diqqat: eng past narx (${formatNum(minPrice)} so'm) tannarxdan (${formatNum(price)} so'm) PAST!\n\n` +
        "Sotuvchilar shu narxgacha tushirib sotsa ham zarar ko'rasiz. Shunday davom etamizmi?"
      );
      if (!ok) return;
    }
  }

  const btn = el("sklad-edit-save-btn");
  btn.disabled = true;
  btn.textContent = "Saqlanmoqda...";

  try {
    const res = await apiFetch(API.skladUpdateProduct, {
      method: "POST",
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      tg.showAlert(skladUpdateErrorText(data));
      return;
    }

    tg.HapticFeedback.notificationOccurred("success");
    el("modal-sklad-edit").classList.add("hidden");
    currentEditProduct = null;
    tg.showAlert(`✅ "${data.product.name}" yangilandi.`);
    loadSkladProducts(el("sklad-search-input").value.trim());
  } catch (e) {
    tg.showAlert(e.message || "Xatolik yuz berdi.");
  } finally {
    btn.disabled = false;
    btn.textContent = "✅ Saqlash";
  }
});

function skladUpdateErrorText(data) {
  const map = {
    missing_name: "Mahsulot nomini kiriting.",
    invalid_price: "Tannarx noto'g'ri.",
    invalid_sell_price: "Sotish narxi noto'g'ri.",
    invalid_min_price: "Eng past narx noto'g'ri.",
    invalid_item: "Mahsulot tanlanmagan.",
    product_not_found: "Mahsulot topilmadi (ehtimol o'chirilgan).",
    forbidden: "🔒 Faqat do'kon egasi mahsulotni tahrirlay oladi.",
    barcode_exists: `Bu barkod allaqachon "${data.product ? data.product.name : ""}" mahsulotida bor.`,
  };
  return map[data.error] || "Saqlashda xatolik yuz berdi.";
}

el("sklad-scan-btn").addEventListener("click", () => {
  if (!currentUser.canAddStock) {
    tg.showAlert("🔒 Sizga skladga tovar qo'shishga ruxsat berilmagan. Do'kon egasiga murojaat qiling.");
    return;
  }
  openScanner("sklad");
});

let skladSearchTimeout = null;
el("sklad-search-input").addEventListener("input", (e) => {
  clearTimeout(skladSearchTimeout);
  const q = e.target.value;
  skladSearchTimeout = setTimeout(() => loadSkladProducts(q.trim()), 300);
});

// LAZERLI SKANER: yuqoridagi (Savdo) qidiruv maydonidagi bilan bir xil
// mantiq - fizik skaner bilan skanerlanganda (Enter yuboriladi) kamera
// bilan skanerlangandagi oqim (handleSkladBarcodeScan) ishga tushadi;
// ruxsat tekshiruvi handleSkladBarcodeScan → openSkladAddModal ichida
// allaqachon bor.
el("sklad-search-input").addEventListener("keydown", async (e) => {
  if (e.key !== "Enter") return;
  e.preventDefault();
  const code = e.target.value.trim();
  if (!code) return;
  clearTimeout(skladSearchTimeout);
  tg.HapticFeedback.impactOccurred("light");
  e.target.value = "";
  loadSkladProducts("");
  await handleSkladBarcodeScan(code);
});

// ============================================================
// 11-BOSQICH: BOSH ADMIN PANELI
// ============================================================
// Bu bo'lim faqat currentUser.role === "admin" bo'lsa ishga tushadi
// (qarang: eng pastdagi init()). Do'kon egasi/sotuvchi uchun mutlaqo
// yashirin - hech qanday admin so'rovi ularning sessiyasida bajarilmaydi.

let currentAdminSection = "stats"; // "stats" | "owners" | "payments" | "settings"
let currentAdminOwner = null; // hozir modal-admin-owner-detail'da ochiq turgan ega

const STATUS_LABELS = {
  active: "✅ Faol",
  trial: "🎁 Sinov muddati",
  expired: "⌛ Muddati tugagan",
  blocked: "⛔ Bloklangan",
  pending_trial: "⏳ Tasdiqlanmagan",
  unknown: "❔ Noma'lum",
};

function statusBadgeHtml(status) {
  const label = STATUS_LABELS[status] || STATUS_LABELS.unknown;
  return `<span class="status-badge status-${escapeHtml(status || "unknown")}">${label}</span>`;
}

// Havolani (taklif linki) nusxalashga urinadi, muvaffaqiyatsiz bo'lsa ham
// linkning o'zi tg.showAlert orqali ko'rsatiladi - foydalanuvchi baribir
// qo'lda nusxalay oladi.
async function copyLinkAndShow(link, title) {
  try {
    await navigator.clipboard.writeText(link);
    tg.showAlert(`${title}\n\n${link}\n\n(havola nusxalandi)`);
  } catch (e) {
    tg.showAlert(`${title}\n\n${link}`);
  }
}

function switchAdminSection(section) {
  currentAdminSection = section;
  document.querySelectorAll(".admin-nav-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.adminSection === section);
  });
  showScreen(`admin-${section}`);
  if (section === "stats") loadAdminStats();
  else if (section === "owners") loadAdminOwners(el("admin-owners-search-input").value.trim());
  else if (section === "payments") loadAdminPayments();
  else if (section === "settings") loadAdminSettings();
}

document.querySelectorAll(".admin-nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => switchAdminSection(btn.dataset.adminSection));
});

// ---------- 1) STATISTIKA ----------

async function loadAdminStats() {
  const grid = el("admin-stats-grid");
  grid.innerHTML = '<p class="muted">Yuklanmoqda...</p>';
  try {
    const res = await apiFetch(API.adminStats);
    if (!res.ok) throw new Error("Statistikani yuklab bo'lmadi.");
    const data = await res.json();
    renderAdminStats(data);
  } catch (e) {
    grid.innerHTML = `<p class="muted">${escapeHtml(e.message || "Xatolik yuz berdi.")}</p>`;
  }
}

function renderAdminStats(data) {
  const grid = el("admin-stats-grid");
  const cards = [
    ["🏪", data.owners_count, "Do'kon egalari"],
    ["🧑‍💼", data.sellers_count, "Sotuvchilar"],
    ["⛔", data.blocked_count, "Bloklangan", data.blocked_count > 0],
    ["💳", data.pending_payments_count, "Kutilayotgan to'lovlar", data.pending_payments_count > 0],
    ["👑", data.extra_admins_count, "Qo'shimcha adminlar"],
  ];
  grid.innerHTML = cards.map(([icon, value, label, warn]) => `
    <div class="admin-stat-card${warn ? " stat-warning" : ""}">
      <div class="admin-stat-value">${icon} ${formatNum(value)}</div>
      <div class="admin-stat-label">${escapeHtml(label)}</div>
    </div>
  `).join("");
}

// ---------- 2) DO'KON EGALARI ----------

async function loadAdminOwners(query = "") {
  const list = el("admin-owners-list");
  list.innerHTML = '<p class="muted">Yuklanmoqda...</p>';
  try {
    const res = await apiFetch(`${API.adminOwners}?q=${encodeURIComponent(query)}`);
    if (!res.ok) throw new Error("Ro'yxatni yuklab bo'lmadi.");
    const data = await res.json();
    renderAdminOwners(data.owners || []);
  } catch (e) {
    list.innerHTML = `<p class="muted">${escapeHtml(e.message || "Xatolik yuz berdi.")}</p>`;
  }
}

function renderAdminOwners(owners) {
  const list = el("admin-owners-list");
  list.innerHTML = "";
  if (owners.length === 0) {
    list.innerHTML = '<p class="muted">Hech narsa topilmadi.</p>';
    return;
  }
  owners.forEach((o) => {
    const card = document.createElement("div");
    card.className = "product-card owner-card";
    const title = o.shop_name || o.owner_name || o.full_name || String(o.telegram_id);
    const sub = [o.owner_name, o.phone_number].filter(Boolean).join(" · ") || `ID: ${o.telegram_id}`;
    const daysText = o.days_left != null
      ? (o.days_left >= 0 ? `${o.days_left} kun qoldi` : `${Math.abs(o.days_left)} kun oldin tugagan`)
      : "";
    card.innerHTML = `
      <div class="owner-card-top">
        <div>
          <div class="name">${escapeHtml(title)}</div>
          <div class="sub">${escapeHtml(sub)}</div>
        </div>
        ${statusBadgeHtml(o.status)}
      </div>
      ${daysText ? `<div class="sub">📅 ${escapeHtml(daysText)}</div>` : ""}
    `;
    card.addEventListener("click", () => openOwnerDetail(o));
    list.appendChild(card);
  });
}

let adminOwnersSearchTimeout = null;
el("admin-owners-search-input").addEventListener("input", (e) => {
  clearTimeout(adminOwnersSearchTimeout);
  const q = e.target.value;
  adminOwnersSearchTimeout = setTimeout(() => loadAdminOwners(q.trim()), 300);
});

function openOwnerDetail(owner) {
  currentAdminOwner = owner;
  renderOwnerDetail(owner);
  el("admin-owner-extend-days").value = "";
  el("modal-admin-owner-detail").classList.remove("hidden");
}

function renderOwnerDetail(o) {
  el("admin-owner-detail-title").textContent = o.shop_name || o.owner_name || o.full_name || String(o.telegram_id);
  const rows = [
    ["Telegram ID", o.telegram_id],
    ["Ega F.I.Sh.", o.owner_name || "—"],
    ["Telefon", o.phone_number || "—"],
    ["Holat", STATUS_LABELS[o.status] || STATUS_LABELS.unknown],
    ["Obuna muddati", o.subscription_until || "—"],
  ];
  el("admin-owner-detail-body").innerHTML = rows.map(([k, v]) => `
    <div class="admin-detail-row"><span class="k">${escapeHtml(k)}</span><span class="v">${escapeHtml(String(v))}</span></div>
  `).join("");
  const blockBtn = el("admin-owner-block-btn");
  blockBtn.textContent = o.blocked ? "✅ Blokdan chiqarish" : "⛔ Bloklash";
}

el("admin-owner-detail-close-btn").addEventListener("click", () => {
  el("modal-admin-owner-detail").classList.add("hidden");
  currentAdminOwner = null;
});

el("admin-owner-extend-btn").addEventListener("click", async () => {
  if (!currentAdminOwner) return;
  const days = parseInt(el("admin-owner-extend-days").value, 10);
  if (!days) {
    tg.showAlert("Kunlar sonini kiriting (masalan: 30 yoki -7).");
    return;
  }
  const btn = el("admin-owner-extend-btn");
  btn.disabled = true;
  try {
    const res = await apiFetch(API.adminOwnerExtend(currentAdminOwner.telegram_id), {
      method: "POST",
      body: JSON.stringify({ days }),
    });
    const data = await res.json();
    if (!res.ok) {
      tg.showAlert("Amalni bajarib bo'lmadi.");
      return;
    }
    tg.HapticFeedback.notificationOccurred("success");
    currentAdminOwner = data.owner;
    renderOwnerDetail(data.owner);
    el("admin-owner-extend-days").value = "";
    loadAdminOwners(el("admin-owners-search-input").value.trim());
  } catch (e) {
    tg.showAlert(e.message || "Xatolik yuz berdi.");
  } finally {
    btn.disabled = false;
  }
});

el("admin-owner-block-btn").addEventListener("click", async () => {
  if (!currentAdminOwner) return;
  const blocking = !currentAdminOwner.blocked;
  const url = blocking
    ? API.adminOwnerBlock(currentAdminOwner.telegram_id)
    : API.adminOwnerUnblock(currentAdminOwner.telegram_id);
  try {
    const res = await apiFetch(url, { method: "POST" });
    const data = await res.json();
    if (!res.ok) {
      tg.showAlert("Amalni bajarib bo'lmadi.");
      return;
    }
    tg.HapticFeedback.notificationOccurred("success");
    currentAdminOwner = data.owner;
    renderOwnerDetail(data.owner);
    loadAdminOwners(el("admin-owners-search-input").value.trim());
  } catch (e) {
    tg.showAlert(e.message || "Xatolik yuz berdi.");
  }
});

el("admin-owner-remove-btn").addEventListener("click", async () => {
  if (!currentAdminOwner) return;
  const ok = await confirmAsync(
    `"${currentAdminOwner.shop_name || currentAdminOwner.owner_name || currentAdminOwner.telegram_id}" butunlay o'chirilsinmi? Bu amalni ortga qaytarib bo'lmaydi.`
  );
  if (!ok) return;
  try {
    const res = await apiFetch(API.adminOwner(currentAdminOwner.telegram_id), { method: "DELETE" });
    if (!res.ok) {
      tg.showAlert("O'chirib bo'lmadi.");
      return;
    }
    tg.HapticFeedback.notificationOccurred("success");
    el("modal-admin-owner-detail").classList.add("hidden");
    currentAdminOwner = null;
    loadAdminOwners(el("admin-owners-search-input").value.trim());
    loadAdminStats();
  } catch (e) {
    tg.showAlert(e.message || "Xatolik yuz berdi.");
  }
});

el("admin-owner-add-btn").addEventListener("click", () => {
  el("admin-owner-add-id-input").value = "";
  el("modal-admin-owner-add").classList.remove("hidden");
});

el("admin-owner-add-cancel-btn").addEventListener("click", () => {
  el("modal-admin-owner-add").classList.add("hidden");
});

el("admin-owner-add-save-btn").addEventListener("click", async () => {
  const raw = el("admin-owner-add-id-input").value.trim();
  if (!raw || !/^\d+$/.test(raw)) {
    tg.showAlert("Telegram ID faqat raqamlardan iborat bo'lishi kerak.");
    return;
  }
  const btn = el("admin-owner-add-save-btn");
  btn.disabled = true;
  btn.textContent = "Qo'shilmoqda...";
  try {
    const res = await apiFetch(API.adminOwners, {
      method: "POST",
      body: JSON.stringify({ telegram_id: raw }),
    });
    const data = await res.json();
    if (!res.ok) {
      const map = {
        already_admin: "Bu odam allaqachon bosh admin.",
        already_owner: "Bu odam allaqachon do'kon egasi.",
        invalid_telegram_id: "Telegram ID noto'g'ri.",
      };
      tg.showAlert(map[data.error] || "Qo'shib bo'lmadi.");
      return;
    }
    tg.HapticFeedback.notificationOccurred("success");
    el("modal-admin-owner-add").classList.add("hidden");
    loadAdminOwners();
    loadAdminStats();
  } catch (e) {
    tg.showAlert(e.message || "Xatolik yuz berdi.");
  } finally {
    btn.disabled = false;
    btn.textContent = "✅ Qo'shish";
  }
});

el("admin-owner-invite-btn").addEventListener("click", async () => {
  try {
    const res = await apiFetch(API.adminOwnerInviteLink);
    if (!res.ok) throw new Error("Taklif linkini olib bo'lmadi.");
    const data = await res.json();
    await copyLinkAndShow(data.link, "🔗 Do'kon egasi uchun taklif linki:");
  } catch (e) {
    tg.showAlert(e.message || "Xatolik yuz berdi.");
  }
});

// ---------- 3) KUTILAYOTGAN TO'LOVLAR ----------

async function loadAdminPayments() {
  const list = el("admin-payments-list");
  list.innerHTML = '<p class="muted">Yuklanmoqda...</p>';
  try {
    const res = await apiFetch(API.adminPayments);
    if (!res.ok) throw new Error("To'lovlarni yuklab bo'lmadi.");
    const data = await res.json();
    renderAdminPayments(data.payments || []);
  } catch (e) {
    list.innerHTML = `<p class="muted">${escapeHtml(e.message || "Xatolik yuz berdi.")}</p>`;
  }
}

function renderAdminPayments(payments) {
  const list = el("admin-payments-list");
  list.innerHTML = "";
  if (payments.length === 0) {
    list.innerHTML = '<p class="muted">Hozircha kutilayotgan to\'lov yo\'q.</p>';
    return;
  }
  payments.forEach((p) => {
    const card = document.createElement("div");
    card.className = "product-card payment-card";
    card.innerHTML = `
      <div class="payment-card-top">
        <div>
          <div class="name">${escapeHtml(p.owner_label)}</div>
          <div class="plan">${escapeHtml(p.plan_label)}</div>
          <div class="amount">${formatNum(p.amount)} so'm${p.days ? ` · ${p.days} kun` : ""}</div>
        </div>
      </div>
      <div class="sub">${escapeHtml(p.created_at || "")}</div>
      <div class="payment-card-actions">
        ${p.has_photo ? `<button type="button" class="pay-photo-btn" data-id="${p.id}">📷</button>` : ""}
        <button type="button" class="pay-approve-btn" data-id="${p.id}">✅ Tasdiqlash</button>
        <button type="button" class="pay-reject-btn" data-id="${p.id}">❌ Rad etish</button>
      </div>
    `;
    if (p.has_photo) {
      card.querySelector(".pay-photo-btn").addEventListener("click", (e) => {
        e.stopPropagation();
        openPaymentPhoto(p.id);
      });
    }
    card.querySelector(".pay-approve-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      decidePayment(p.id, "approve");
    });
    card.querySelector(".pay-reject-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      decidePayment(p.id, "reject");
    });
    list.appendChild(card);
  });
}

function openPaymentPhoto(paymentId) {
  el("admin-payment-photo-img").src = API.adminPaymentPhoto(paymentId);
  el("modal-admin-payment-photo").classList.remove("hidden");
}

el("admin-payment-photo-close-btn").addEventListener("click", () => {
  el("modal-admin-payment-photo").classList.add("hidden");
  el("admin-payment-photo-img").src = "";
});

async function decidePayment(paymentId, action) {
  const verb = action === "approve" ? "tasdiqlansinmi" : "rad etilsinmi";
  const ok = await confirmAsync(`Bu to'lov ${verb}?`);
  if (!ok) return;
  const url = action === "approve" ? API.adminPaymentApprove(paymentId) : API.adminPaymentReject(paymentId);
  try {
    const res = await apiFetch(url, { method: "POST" });
    if (!res.ok) {
      tg.showAlert("Bu to'lov bo'yicha allaqachon qaror qabul qilingan.");
      loadAdminPayments();
      return;
    }
    tg.HapticFeedback.notificationOccurred("success");
    loadAdminPayments();
    loadAdminStats();
  } catch (e) {
    tg.showAlert(e.message || "Xatolik yuz berdi.");
  }
}

// ---------- 4) ADMINLAR / TO'LOV SOZLAMALARI / OMMAVIY XABAR ----------

async function loadAdminSettings() {
  el("admin-admins-list").innerHTML = '<p class="muted">Yuklanmoqda...</p>';
  el("admin-payment-settings-list").innerHTML = '<p class="muted">Yuklanmoqda...</p>';
  try {
    const [adminsRes, settingsRes] = await Promise.all([
      apiFetch(API.adminAdmins),
      apiFetch(API.adminSettings),
    ]);
    if (adminsRes.ok) {
      const data = await adminsRes.json();
      renderAdminAdmins(data.admins || [], data.env_admin_ids || []);
    }
    if (settingsRes.ok) {
      const data = await settingsRes.json();
      renderAdminPaymentSettings(data.plans || {}, data.requisites || {});
    }
  } catch (e) {
    // Ikkala ro'yxat mustaqil - biri xato bersa ham ikkinchisi ko'rinishda qoladi.
  }
}

function renderAdminAdmins(admins, envIds) {
  const list = el("admin-admins-list");
  const envRows = envIds.map((id) => `
    <div class="admin-settings-row">
      <div>
        <div class="value">👑 ${id}</div>
        <div class="env-tag">🔒 .env orqali qo'shilgan</div>
      </div>
    </div>
  `);
  const dbRows = admins.map((a) => `
    <div class="admin-settings-row" data-admin-id="${a.telegram_id}">
      <div>
        <div class="value">👑 ${escapeHtml(a.full_name || a.username || String(a.telegram_id))}</div>
        <div class="env-tag">ID: ${a.telegram_id}</div>
      </div>
      <div class="row-actions">
        <button type="button" class="admin-remove-admin-btn" data-id="${a.telegram_id}">🗑</button>
      </div>
    </div>
  `);
  const all = envRows.concat(dbRows).join("");
  list.innerHTML = all || '<p class="muted">Hozircha qo\'shimcha admin yo\'q.</p>';
  list.querySelectorAll(".admin-remove-admin-btn").forEach((btn) => {
    btn.addEventListener("click", () => removeAdmin(btn.dataset.id));
  });
}

async function removeAdmin(adminId) {
  const ok = await confirmAsync("Bu odamning bosh admin huquqi olib tashlansinmi?");
  if (!ok) return;
  try {
    const res = await apiFetch(API.adminAdmin(adminId), { method: "DELETE" });
    const data = await res.json();
    if (!res.ok) {
      tg.showAlert(data.message || "O'chirib bo'lmadi.");
      return;
    }
    tg.HapticFeedback.notificationOccurred("success");
    loadAdminSettings();
    loadAdminStats();
  } catch (e) {
    tg.showAlert(e.message || "Xatolik yuz berdi.");
  }
}

el("admin-admin-add-btn").addEventListener("click", () => {
  el("admin-admin-add-id-input").value = "";
  el("modal-admin-admin-add").classList.remove("hidden");
});

el("admin-admin-add-cancel-btn").addEventListener("click", () => {
  el("modal-admin-admin-add").classList.add("hidden");
});

el("admin-admin-add-save-btn").addEventListener("click", async () => {
  const raw = el("admin-admin-add-id-input").value.trim();
  if (!raw || !/^\d+$/.test(raw)) {
    tg.showAlert("Telegram ID faqat raqamlardan iborat bo'lishi kerak.");
    return;
  }
  const btn = el("admin-admin-add-save-btn");
  btn.disabled = true;
  btn.textContent = "Qo'shilmoqda...";
  try {
    const res = await apiFetch(API.adminAdmins, {
      method: "POST",
      body: JSON.stringify({ telegram_id: raw }),
    });
    const data = await res.json();
    if (!res.ok) {
      const map = {
        already_admin: "Bu odam allaqachon bosh admin.",
        is_owner: "Bu odam do'kon egasi - avval uni olib tashlang.",
        is_seller: "Bu odam sotuvchi - avval uni olib tashlang.",
        invalid_telegram_id: "Telegram ID noto'g'ri.",
      };
      tg.showAlert(map[data.error] || "Qo'shib bo'lmadi.");
      return;
    }
    tg.HapticFeedback.notificationOccurred("success");
    el("modal-admin-admin-add").classList.add("hidden");
    loadAdminSettings();
    loadAdminStats();
  } catch (e) {
    tg.showAlert(e.message || "Xatolik yuz berdi.");
  } finally {
    btn.disabled = false;
    btn.textContent = "✅ Qo'shish";
  }
});

el("admin-admin-invite-btn").addEventListener("click", async () => {
  try {
    const res = await apiFetch(API.adminAdminsInviteLink);
    if (!res.ok) throw new Error("Taklif linkini olib bo'lmadi.");
    const data = await res.json();
    await copyLinkAndShow(data.link, "🔗 Bosh admin uchun taklif linki:");
  } catch (e) {
    tg.showAlert(e.message || "Xatolik yuz berdi.");
  }
});

// To'lov sozlamalari: narx maydonlari (price_1m/3m/12m) va rekvizitlar
// (card_number/card_holder/click_number/payme_number) bitta xil
// ro'yxat ko'rinishida - har birining yonida ✏️ tugmasi orqali
// modal-admin-setting-edit ochiladi.
const PAYMENT_SETTING_LABELS = {
  price_1m: "1 oylik obuna narxi",
  price_3m: "3 oylik obuna narxi",
  price_12m: "12 oylik obuna narxi",
  card_number: "Karta raqami",
  card_holder: "Karta egasi (F.I.Sh.)",
  click_number: "Click raqami",
  payme_number: "Payme raqami",
};
let currentSettingEditKey = null;

function renderAdminPaymentSettings(plans, requisites) {
  const list = el("admin-payment-settings-list");
  const rows = [];
  [["1m", "price_1m"], ["3m", "price_3m"], ["12m", "price_12m"]].forEach(([planKey, settingKey]) => {
    const plan = plans[planKey];
    if (!plan) return;
    rows.push([settingKey, `${formatNum(plan.price)} so'm`]);
  });
  [
    ["card_number", requisites.card_number],
    ["card_holder", requisites.card_holder],
    ["click_number", requisites.click_number],
    ["payme_number", requisites.payme_number],
  ].forEach(([key, value]) => rows.push([key, value || "—"]));

  list.innerHTML = rows.map(([key, displayValue]) => `
    <div class="admin-settings-row">
      <div>
        <div class="label">${escapeHtml(PAYMENT_SETTING_LABELS[key])}</div>
        <div class="value">${escapeHtml(String(displayValue))}</div>
      </div>
      <div class="row-actions">
        <button type="button" class="admin-edit-setting-btn" data-key="${key}">✏️</button>
      </div>
    </div>
  `).join("");

  list.querySelectorAll(".admin-edit-setting-btn").forEach((btn) => {
    btn.addEventListener("click", () => openSettingEdit(btn.dataset.key));
  });
}

function openSettingEdit(key) {
  currentSettingEditKey = key;
  el("admin-setting-edit-title").textContent = `✏️ ${PAYMENT_SETTING_LABELS[key] || key}`;
  const input = el("admin-setting-edit-input");
  input.value = "";
  input.inputMode = key.startsWith("price_") ? "numeric" : "text";
  el("modal-admin-setting-edit").classList.remove("hidden");
}

el("admin-setting-edit-cancel-btn").addEventListener("click", () => {
  el("modal-admin-setting-edit").classList.add("hidden");
  currentSettingEditKey = null;
});

el("admin-setting-edit-save-btn").addEventListener("click", async () => {
  if (!currentSettingEditKey) return;
  const value = el("admin-setting-edit-input").value.trim();
  if (!value) {
    tg.showAlert("Qiymatni kiriting.");
    return;
  }
  if (currentSettingEditKey.startsWith("price_") && (!/^\d+$/.test(value) || parseInt(value, 10) <= 0)) {
    tg.showAlert("Narx musbat butun son bo'lishi kerak (masalan: 60000).");
    return;
  }
  const btn = el("admin-setting-edit-save-btn");
  btn.disabled = true;
  try {
    const res = await apiFetch(API.adminSettings, {
      method: "POST",
      body: JSON.stringify({ key: currentSettingEditKey, value }),
    });
    const data = await res.json();
    if (!res.ok) {
      tg.showAlert("Saqlab bo'lmadi.");
      return;
    }
    tg.HapticFeedback.notificationOccurred("success");
    el("modal-admin-setting-edit").classList.add("hidden");
    currentSettingEditKey = null;
    renderAdminPaymentSettings(data.plans || {}, data.requisites || {});
  } catch (e) {
    tg.showAlert(e.message || "Xatolik yuz berdi.");
  } finally {
    btn.disabled = false;
  }
});

// ---------- OMMAVIY XABAR ----------

el("admin-broadcast-send-btn").addEventListener("click", async () => {
  const text = el("admin-broadcast-text").value.trim();
  if (!text) {
    tg.showAlert("Xabar matnini kiriting.");
    return;
  }
  const ok = await confirmAsync("Xabar BARCHA do'kon egalari va sotuvchilarga yuborilsin?");
  if (!ok) return;

  const btn = el("admin-broadcast-send-btn");
  btn.disabled = true;
  btn.textContent = "Yuborilmoqda...";
  try {
    const res = await apiFetch(API.adminBroadcast, {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    if (!res.ok) {
      tg.showAlert("Xabarni yuborib bo'lmadi.");
      return;
    }
    tg.HapticFeedback.notificationOccurred("success");
    el("admin-broadcast-text").value = "";
    tg.showAlert(`✅ Yuborildi: ${data.sent} ta. Muvaffaqiyatsiz: ${data.failed} ta.`);
  } catch (e) {
    tg.showAlert(e.message || "Xatolik yuz berdi.");
  } finally {
    btn.disabled = false;
    btn.textContent = "📢 Yuborish";
  }
});

// ---------- ADMIN REJIMINI ISHGA TUSHIRISH ----------
// currentUser.role === "admin" bo'lganda chaqiriladi (qarang: init()) -
// oddiy do'kon egasi/sotuvchi ekranlarini (Savdo/Sklad) butunlay
// yashiradi va statistika ekranidan boshlaydi.
function startAdminMode() {
  document.body.classList.add("admin-mode");
  el("app-header").classList.add("hidden");
  el("admin-header").classList.remove("hidden");
  el("admin-bottom-nav").classList.remove("hidden");
  switchAdminSection("stats");
}

// ---------- ENTER TUGMASI: MAYDONDAN MAYDONGA O'TISH ----------
// Narx/miqdor kiritiladigan oynalarda (savatga qo'shish, sklad - yangi
// mahsulot/tahrirlash/miqdor qo'shish) foydalanuvchi telefon
// klaviaturasidagi "Enter"/"Next" tugmasini bossa - keyingi maydonga
// avtomatik o'tadi, RO'YXATNING ENG OXIRGI maydonida esa fokus o'tkazish
// o'rniga asosiy tugmani (masalan "✅ Qo'shish"/"✅ Savdoni yakunlash")
// bosgandek ishlaydi. Shu orqali butun oynani ekranga bir necha marta
// tegmasdan, faqat ketma-ket Enter bosib to'ldirib chiqish mumkin bo'ladi.
function wireEnterToNext(inputIds, submitBtnId) {
  inputIds.forEach((id, idx) => {
    const input = el(id);
    if (!input) return;
    input.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      const nextId = inputIds[idx + 1];
      const nextInput = nextId ? el(nextId) : null;
      if (nextInput) {
        nextInput.focus();
        try { nextInput.select(); } catch (err) { /* type="number" ba'zi brauzerlarda select()ni qo'llamaydi */ }
      } else {
        const btn = el(submitBtnId);
        if (btn && !btn.disabled) btn.click();
      }
    });
  });
}

// SAVATGA QO'SHISH: "Nechta sotildi?" -> "Qancha so'mga sotildi?" -> Enter = "Savatga qo'shish"
wireEnterToNext(["modal-qty-input", "modal-price-input"], "modal-add-btn");

// SAVAT / TO'LOV: "aralash" tanlanganda naqd summasi maydonida Enter = "Savdoni yakunlash"
wireEnterToNext(["mixed-cash-input"], "finalize-btn");

// SKLAD - miqdor qo'shish: yagona maydon, Enter = "➕ Skladga qo'shish"
wireEnterToNext(["sklad-modal-qty-input"], "sklad-modal-add-btn");

// SKLAD - yangi mahsulot: nomi -> barkod -> tannarx -> sotish narxi -> eng
// past narx -> boshlang'ich miqdor -> ogohlantirish soni -> Enter = "✅ Qo'shish"
wireEnterToNext(
  [
    "sklad-new-name-input",
    "sklad-new-barcode-input",
    "sklad-new-price-input",
    "sklad-new-sell-price-input",
    "sklad-new-min-price-input",
    "sklad-new-quantity-input",
    "sklad-new-alert-input",
  ],
  "sklad-new-save-btn"
);

// SKLAD - mahsulotni tahrirlash: nomi -> tannarx -> sotish narxi -> eng
// past narx -> ogohlantirish soni -> barkod -> Enter = "✅ Saqlash"
wireEnterToNext(
  [
    "sklad-edit-name-input",
    "sklad-edit-price-input",
    "sklad-edit-sell-price-input",
    "sklad-edit-min-price-input",
    "sklad-edit-alert-input",
    "sklad-edit-barcode-input",
  ],
  "sklad-edit-save-btn"
);

// ---------- BOSHLASH ----------

(async function init() {
  showScreen("loading");
  await loadMe();
  if (currentUser.role === "admin") {
    startAdminMode();
    return;
  }
  await loadProducts();
})();

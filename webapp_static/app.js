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
  ["loading", "error", "products", "cart", "sklad"].forEach((s) => {
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
    card.addEventListener("click", () => openAddModal(p));
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

function formatNum(n) {
  return Number(n).toFixed(0);
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
  el("modal-product-stock").textContent = `Skladda ${formatNum(product.quantity)} dona bor`;

  // Mahsulot savatda ALLAQACHON bor bo'lsa (masalan avval skanerlab
  // qo'shilgan bo'lsa) - shu yozuvning joriy qty/narxini ko'rsatamiz,
  // aks holda har safar "1 dona / standart narx"ga qaytarib
  // tashlagan bo'lardik.
  const existing = cart.find((c) => c.id === product.id);
  el("modal-qty-input").value = existing ? existing.qty : 1;
  el("modal-price-input").value = existing ? existing.price : (product.sell_price || product.price || "");

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
        el("modal-price-input").value = product[key];
      });
      hints.appendChild(btn);
    }
  });

  el("modal-add").classList.remove("hidden");
}

el("modal-cancel-btn").addEventListener("click", () => {
  el("modal-add").classList.add("hidden");
  currentModalProduct = null;
});

el("modal-add-btn").addEventListener("click", () => {
  if (!currentModalProduct) return;
  const qty = parseFloat(el("modal-qty-input").value);
  const price = parseFloat(el("modal-price-input").value);
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
    chip.addEventListener("click", () => openAddModal(p));
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
    mixedCash = parseFloat(el("mixed-cash-input").value);
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
  return "Kamerani barkodga to'g'rilang...";
}

async function openScanner(mode = "sale") {
  scannerMode = mode;
  scanHandled = false;
  setScannerStatus(defaultScannerStatusText());
  el("modal-scanner").classList.remove("hidden");

  if (!window.Html5Qrcode) {
    setScannerStatus("Skaner kutubxonasi yuklanmadi. Internetni tekshiring.", "error");
    return;
  }

  try {
    html5QrCode = new Html5Qrcode("scanner-reader", {
      formatsToSupport: BARCODE_FORMATS,
      verbose: false,
    });
    await html5QrCode.start(
      { facingMode: "environment" },
      { fps: 10, qrbox: { width: 260, height: 160 } },
      onBarcodeDecoded,
      () => {} // har bir kadrda "topilmadi" - bu normal holat, e'tiborsiz qoldiramiz
    );
    await setupTorchButton();
  } catch (err) {
    setScannerStatus("Kameraga ruxsat berilmadi. Telegram sozlamalaridan ruxsat bering.", "error");
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
  // YANGI REJA - 3-BOSQICH: agar foydalanuvchi "Yangi mahsulot"
  // oynasidan skaner ochib, hech narsa skanerlamasdan ✕ bosib yopsa -
  // to'ldirilgan maydonlar (nom/narx/miqdor) yo'qolib qolmasligi uchun
  // o'sha oynani qayta ko'rsatamiz.
  if (scannerMode === "sklad_new") {
    el("modal-sklad-new").classList.remove("hidden");
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

  if (scannerMode === "sklad") {
    setScannerStatus("Qidirilmoqda...");
    await stopScanner();
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
  await stopScanner();
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
      tg.showAlert(msg);
      return;
    }
    showScreen("products");
    openAddModal(data.product);
  } catch (e) {
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
        tg.showAlert(
          `Bu barkod bo'yicha mahsulot topilmadi:\n${decodedText}\n\n` +
          "Uni yangi mahsulot sifatida qo'shishingiz mumkin."
        );
        openSkladNewProductModal(decodedText);
        return;
      }
      tg.showAlert("Barkod bo'yicha qidirishda xatolik yuz berdi.");
      return;
    }
    openSkladAddModal(data.product);
  } catch (e) {
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
    card.innerHTML = `
      <div>
        <div class="name">${escapeHtml(p.name)}</div>
        <div class="stock">${formatNum(p.quantity)} dona bor</div>
        ${lowBadge}
      </div>
      <div class="add-icon">${actionIcon}</div>
    `;
    card.addEventListener("click", () => openSkladAddModal(p));
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
  el("sklad-modal-product-stock").textContent = `Hozir skladda ${formatNum(product.quantity)} dona bor`;
  el("sklad-modal-qty-input").value = 1;
  el("modal-sklad-add").classList.remove("hidden");
}

el("sklad-modal-cancel-btn").addEventListener("click", () => {
  el("modal-sklad-add").classList.add("hidden");
  currentSkladProduct = null;
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
    tg.showAlert(`✅ ${data.name}: ${formatNum(data.old_quantity)} → ${formatNum(data.new_quantity)} dona.`);
    loadSkladProducts(el("sklad-search-input").value.trim());
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
  el("sklad-new-barcode-input").value = prefilledBarcode;
  el("modal-sklad-new").classList.remove("hidden");
}

el("sklad-new-product-btn").addEventListener("click", () => openSkladNewProductModal());

el("sklad-new-cancel-btn").addEventListener("click", () => {
  el("modal-sklad-new").classList.add("hidden");
});

// YANGI REJA - 3-BOSQICH: "Yangi mahsulot" oynasidagi 📷 tugmasi -
// oynani vaqtincha yashiradi, kamerani "sklad_new" rejimida ochadi;
// skaner o'qigach (onBarcodeDecoded) barkod maydoni to'ldiriladi va
// oyna avtomatik qayta ko'rinadi.
el("sklad-new-scan-btn").addEventListener("click", () => {
  el("modal-sklad-new").classList.add("hidden");
  openScanner("sklad_new");
});

el("sklad-new-save-btn").addEventListener("click", async () => {
  const name = el("sklad-new-name-input").value.trim();
  const price = parseFloat(el("sklad-new-price-input").value);
  const sellPriceRaw = el("sklad-new-sell-price-input").value;
  const minPriceRaw = el("sklad-new-min-price-input").value;
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
  if (sellPriceRaw !== "") {
    const sellPrice = parseFloat(sellPriceRaw);
    if (isNaN(sellPrice) || sellPrice < 0) {
      tg.showAlert("Sotish narxini to'g'ri kiriting.");
      return;
    }
    body.sell_price = sellPrice;
  }

  let minPrice = null;
  if (minPriceRaw !== "") {
    minPrice = parseFloat(minPriceRaw);
    if (isNaN(minPrice) || minPrice < 0) {
      tg.showAlert("Eng past narxni to'g'ri kiriting.");
      return;
    }
    body.min_price = minPrice;
  }

  // 2-BOSQICH: agar "eng past narx" umuman kiritilmasa - buni indamay
  // o'tkazib yubormaymiz, chunki bu maydon sotuvchilarning narxni juda
  // pastga tushirib yuborishining OLDINI OLADI. Shuning uchun kiritilmasa
  // ANIQ OGOHLANTIRIB, davom etish/qaytib kiritishni so'raymiz.
  if (minPrice === null) {
    tg.showConfirm(
      "Eng past narx kiritilmadi. Bunday holda sotuvchilar bu mahsulotni istalgan (hatto juda past) narxda sotib yuborishi mumkin.\n\nShunday davom etamizmi?",
      (confirmed) => {
        if (confirmed) saveSkladNewProduct(body);
      }
    );
    return;
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

// ---------- BOSHLASH ----------

(async function init() {
  showScreen("loading");
  await loadMe();
  await loadProducts();
})();

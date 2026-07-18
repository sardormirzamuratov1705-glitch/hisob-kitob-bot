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
};

let cart = []; // [{id, name, qty, price, stock}]
let selectedPaymentMethod = null;
let currentModalProduct = null;

const el = (id) => document.getElementById(id);

function showScreen(name) {
  ["loading", "error", "products", "cart"].forEach((s) => {
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
  badge.classList.remove("hidden");

  if (!bar) {
    bar = document.createElement("div");
    bar.id = "cart-bar";
    bar.className = "cart-bar";
    bar.addEventListener("click", openCartScreen);
    document.body.appendChild(bar);
  }
  bar.innerHTML = `<span>🛒 Savat: ${cart.length} tur</span><span>${formatNum(total)} so'm</span>`;

  loadCrossSell();
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

function setScannerStatus(text, type) {
  const box = el("scanner-status");
  box.textContent = text;
  box.classList.remove("scanner-status-success", "scanner-status-error");
  if (type === "success") box.classList.add("scanner-status-success");
  if (type === "error") box.classList.add("scanner-status-error");
}

function resetScannerStatusSoon(delay = 1600) {
  setTimeout(() => {
    if (!el("modal-scanner").classList.contains("hidden")) {
      setScannerStatus("Kamerani barkodga to'g'irlang...");
    }
  }, delay);
}

async function openScanner() {
  scanHandled = false;
  setScannerStatus("Kamerani barkodga to'g'rilang...");
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
  } catch (err) {
    setScannerStatus("Kameraga ruxsat berilmadi. Telegram sozlamalaridan ruxsat bering.", "error");
  }
}

async function stopScanner() {
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
}

// 5-BOSQICH: skanerlangan mahsulotni savatga ulash.
//
// MUHIM DIZAYN QARORI: har bir skanerlashdan keyin modal YOPILMAYDI va
// kamera to'XTATILMAYDI - do'konda ketma-ket bir nechta tovar
// skanerlanganda foydalanuvchi har safar "Yopish -> qayta skaner tugmasi ->
// ochish" bosishga majbur bo'lmasligi kerak (bu haqiqiy savdo
// tezligiga to'sqinlik qilardi). Buning o'rniga: skanerlandi -> darhol
// savatga (standart narxda) qo'shiladi -> qisqa "✅ ..." tasdiq matni
// ko'rsatiladi -> ~1.2 soniyadan keyin skaner o'zi davom etadi. Savdoni
// tugatish uchun foydalanuvchi "✕" (scanner-close-btn) bosadi.
async function onBarcodeDecoded(decodedText) {
  if (scanHandled) return; // bitta kadrda bir necha marta chaqirilishining oldini olamiz
  scanHandled = true;
  tg.HapticFeedback.impactOccurred("light");
  setScannerStatus("Qidirilmoqda...");

  try {
    const res = await apiFetch(`${API.productByBarcode}?code=${encodeURIComponent(decodedText)}`);
    const data = await res.json();
    if (!res.ok) {
      const msg = data.error === "not_found"
        ? `Bu barkod bo'yicha mahsulot topilmadi: ${decodedText}`
        : "Barkod bo'yicha qidirishda xatolik yuz berdi.";
      setScannerStatus(`❌ ${msg}`, "error");
      resetScannerStatusSoon();
      return;
    }
    addScannedProductToCart(data.product);
  } catch (e) {
    setScannerStatus(`❌ ${e.message || "Xatolik yuz berdi."}`, "error");
    resetScannerStatusSoon();
  } finally {
    // Bir xil barkod (masalan qo'l bilan ushlab turilgan) darhol yana
    // o'qib ketmasligi uchun qisqa "sovish" vaqti beriladi.
    setTimeout(() => { scanHandled = false; }, 1200);
  }
}

// Skanerlangan mahsulotni savatga qo'shadi: agar savatda ALLAQACHON
// bo'lsa - miqdorini 1taga oshiradi (narxi o'zgarmaydi, chunki bir xil
// tovar bir xil chekda odatda bir xil narxda sotiladi); yo'q bo'lsa -
// standart narxda (savdo narxi, bo'lmasa tannarx) 1 dona qo'shadi.
// Ikkala holatda ham modal-add oynasidagi BILAN BIR XIL
// cartValidationError() orqali tekshiriladi.
function addScannedProductToCart(product) {
  const existing = cart.find((c) => c.id === product.id);
  const qty = existing ? existing.qty + 1 : 1;
  const price = existing ? existing.price : (product.sell_price || product.price || 0);

  const err = cartValidationError(product, qty, price);
  if (err) {
    setScannerStatus(`❌ ${err}`, "error");
    resetScannerStatusSoon();
    return;
  }

  if (existing) {
    existing.qty = qty;
  } else {
    cart.push({ id: product.id, name: product.name, qty, price, stock: product.quantity });
  }

  renderCartBar();
  tg.HapticFeedback.notificationOccurred("success");
  setScannerStatus(`✅ ${product.name} — ${formatNum(qty)} dona savatda`, "success");
  resetScannerStatusSoon();
}

el("scan-btn").addEventListener("click", openScanner);
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

// ---------- BOSHLASH ----------

(async function init() {
  showScreen("loading");
  await loadProducts();
})();

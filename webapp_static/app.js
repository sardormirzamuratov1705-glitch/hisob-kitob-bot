// SAVDO WEB APP - 1-BOSQICH
// Bu fayl Telegram Mini App (WebApp) ichida ishlaydi. Har bir so'rovga
// Telegram.WebApp.initData headerda (X-Telegram-Init-Data) qo'shib
// yuboriladi - server (webapp.py) shu orqali so'rov chindan ham
// Telegramning o'zidan va aynan shu foydalanuvchidan kelayotganini tekshiradi.

const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

const API = {
  me: "/api/webapp/me",
  products: "/api/webapp/products",
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
  const headers = Object.assign({}, options.headers || {}, {
    "X-Telegram-Init-Data": tg.initData || "",
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
      `initDataLen=${(tg.initData || "").length}`,
      `hasHash=${location.hash ? "ha" : "yo'q"}`,
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
    card.innerHTML = `
      <div>
        <div class="name">${escapeHtml(p.name)}</div>
        <div class="stock">${formatNum(p.quantity)} dona bor</div>
      </div>
      <div class="add-icon">➕</div>
    `;
    card.addEventListener("click", () => openAddModal(p));
    list.appendChild(card);
  });

  showScreen("products");
  renderCartBar();
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

function openAddModal(product) {
  currentModalProduct = product;
  el("modal-product-name").textContent = product.name;
  el("modal-product-stock").textContent = `Skladda ${formatNum(product.quantity)} dona bor`;
  el("modal-qty-input").value = 1;
  el("modal-price-input").value = product.sell_price || product.price || "";

  const hints = el("modal-price-hints");
  hints.innerHTML = "";
  const hintDefs = [
    ["sell_price", "💰 Savdo narxi"],
    ["min_price", "🔻 Eng past narx"],
    ["discount_price", "🏷 Chegirma narxi"],
  ];
  hintDefs.forEach(([key, label]) => {
    if (product[key]) {
      const btn = document.createElement("button");
      btn.className = "price-hint-btn";
      btn.textContent = `${label}: ${formatNum(product[key])}`;
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

  if (!qty || qty <= 0) {
    tg.showAlert("Miqdor 0 dan katta bo'lishi kerak.");
    return;
  }
  if (qty > product.quantity) {
    tg.showAlert(`Skladda faqat ${formatNum(product.quantity)} dona bor.`);
    return;
  }
  if (!price || price <= 0) {
    tg.showAlert("Narxni kiriting.");
    return;
  }
  if (product.price && price < product.price) {
    tg.showAlert(`Narx tannarxdan (${formatNum(product.price)} so'm) past bo'lishi mumkin emas.`);
    return;
  }
  if (product.min_price && price < product.min_price && !product.discount_price) {
    tg.showAlert(`Narx eng past narxdan (${formatNum(product.min_price)} so'm) past bo'lishi mumkin emas.`);
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

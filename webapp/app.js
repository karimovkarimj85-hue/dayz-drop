"use strict";

const tg = window.Telegram && window.Telegram.WebApp;
const qs = new URLSearchParams(location.search);
const API = (qs.get("api") || window.DAYZ_CONFIG.API_URL).replace(/\/+$/, "");

const $view = document.getElementById("view");
const $nav = document.getElementById("nav");
const $toast = document.getElementById("toast");

const STATUS = {
  awaiting_payment: "Ожидает оплаты",
  checking: "Проверяем оплату",
  paid: "Оплачен",
  shipped: "Отправлен",
  done: "Получен",
  cancelled: "Отменён",
};

const state = {
  me: null,
  isAdmin: false,
  settings: { currency: "₽", delivery_options: [], payment_details: "" },
  products: [],
  cart: loadCart(),
  tab: "catalog",
  stack: [],
  category: "Все",
  adminTab: "orders",
  adminStatus: "",
};

// ---------- утилиты ----------

const esc = (s) =>
  String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const money = (n) => `${Number(n || 0).toLocaleString("ru-RU")} ${state.settings.currency}`;
const photoUrl = (id) => `${API}/api/photo/${encodeURIComponent(id)}`;
const stockOf = (p) => p.sizes.reduce((s, x) => s + x.stock, 0);
const can = (v) => tg && tg.isVersionAtLeast && tg.isVersionAtLeast(v);

function haptic(type) {
  try {
    if (!can("6.1")) return;
    if (type === "ok" || type === "error") tg.HapticFeedback.notificationOccurred(type === "ok" ? "success" : "error");
    else tg.HapticFeedback.impactOccurred("light");
  } catch (_) {}
}

let toastTimer;
function toast(text, isError) {
  $toast.textContent = text;
  $toast.className = "toast show" + (isError ? " err" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($toast.className = "toast"), 2600);
  haptic(isError ? "error" : "ok");
}

function confirmDialog(text) {
  return new Promise((resolve) => {
    if (can("6.2")) tg.showConfirm(text, resolve);
    else resolve(window.confirm(text));
  });
}

function loadCart() {
  try {
    return JSON.parse(localStorage.getItem("dayz_cart") || "[]");
  } catch (_) {
    return [];
  }
}
function saveCart() {
  try {
    localStorage.setItem("dayz_cart", JSON.stringify(state.cart));
  } catch (_) {}
  renderNav();
}
const cartCount = () => state.cart.reduce((s, i) => s + i.qty, 0);

async function api(path, { method = "GET", body, file } = {}) {
  const headers = { "X-Init-Data": (tg && tg.initData) || "" };
  let payload;
  if (file) {
    payload = new FormData();
    payload.append("file", file, file.name);
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  // Бесплатный сервер может спать — первая загрузка до минуты
  const slow = setTimeout(() => {
    const l = document.querySelector(".loader .slow");
    if (l) l.textContent = "Сервер просыпается, это может занять до минуты…";
  }, 3500);
  try {
    const res = await fetch(API + path, { method, headers, body: payload });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Ошибка ${res.status}`);
    return data;
  } finally {
    clearTimeout(slow);
  }
}

async function compressImage(file, max = 1600) {
  if (!file.type.startsWith("image/") || file.type === "image/gif") return file;
  try {
    const bmp = await createImageBitmap(file);
    const k = Math.min(1, max / Math.max(bmp.width, bmp.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bmp.width * k);
    canvas.height = Math.round(bmp.height * k);
    canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((r) => canvas.toBlob(r, "image/jpeg", 0.86));
    return blob ? new File([blob], "photo.jpg", { type: "image/jpeg" }) : file;
  } catch (_) {
    return file;
  }
}

function pickFile(accept, multiple) {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = accept;
    input.multiple = !!multiple;
    input.onchange = () => resolve([...input.files]);
    input.click();
  });
}

function copy(text) {
  (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject())
    .then(() => toast("Скопировано"))
    .catch(() => toast("Не удалось скопировать", true));
}

function openLink(url) {
  if (tg && tg.openLink) tg.openLink(url);
  else window.open(url, "_blank");
}

// Поддержка — чат с админами через бота (бот пересылает сообщение обоим админам)
function supportUrl() {
  return state.botUsername ? `https://t.me/${state.botUsername}?start=support` : null;
}

function openSupport() {
  const url = supportUrl();
  if (!url) return;
  if (tg && tg.openTelegramLink) {
    tg.openTelegramLink(url);
    tg.close();
  } else openLink(url);
}

const loaderHtml = (text = "Загрузка…") => `<div class="loader"><div class="spin"></div><div class="slow">${text}</div></div>`;
const photoHtml = (id) => (id ? `<img src="${photoUrl(id)}" loading="lazy" alt="">` : `<div class="placeholder"><img src="assets/logo.jpg" alt=""></div>`);
const statusBadge = (s) => `<span class="badge st-${s}">${STATUS[s] || s}</span>`;
const fmtDate = (iso) => (iso ? new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "");

// ---------- навигация ----------

const screens = {};

function setBar(html) {
  document.querySelectorAll(".bar").forEach((b) => b.remove());
  document.body.classList.toggle("has-bar", !!html);
  if (!html) return null;
  const bar = document.createElement("div");
  bar.className = "bar";
  bar.innerHTML = `<div>${html}</div>`;
  document.body.appendChild(bar);
  return bar;
}

async function render() {
  const top = state.stack[state.stack.length - 1];
  setBar(null);
  window.scrollTo(0, 0);
  const canGoBack = state.stack.length > 1;
  if (can("6.1")) canGoBack ? tg.BackButton.show() : tg.BackButton.hide();
  try {
    await screens[top.name](top.params || {});
  } catch (err) {
    $view.innerHTML = `<div class="empty"><div class="big">⚠️</div>${esc(err.message)}<br><br><button class="btn ghost sm" id="retry">Повторить</button></div>`;
    document.getElementById("retry").onclick = render;
  }
  if (canGoBack && !can("6.1")) {
    $view.insertAdjacentHTML("afterbegin", `<button class="back" id="backBtn">← Назад</button>`);
    document.getElementById("backBtn").onclick = back;
  }
}

function go(name, params) {
  state.stack.push({ name, params });
  render();
}

function back() {
  if (state.stack.length > 1) state.stack.pop();
  render();
}

function switchTab(tab) {
  state.tab = tab;
  state.stack = [{ name: tab }];
  renderNav();
  render();
}

const ICONS = {
  catalog: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.4 6.6 16 4l-1.5 1.5a3.5 3.5 0 0 1-5 0L8 4 3.6 6.6 5 11l2-.5V20h10v-9.5l2 .5z"/></svg>',
  cart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 7h12l-1 13H7z"/><path d="M9 7a3 3 0 0 1 6 0"/></svg>',
  orders: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="m3 8 9 5 9-5M12 13v8"/></svg>',
  admin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>',
};

function renderNav() {
  const tabs = [
    ["catalog", "Каталог"],
    ["cart", "Корзина"],
    ["orders", "Заказы"],
  ];
  if (state.isAdmin) tabs.push(["admin", "Админка"]);
  const count = cartCount();
  $nav.innerHTML = tabs
    .map(
      ([id, label]) =>
        `<button data-tab="${id}" class="${state.tab === id ? "active" : ""}">${ICONS[id]}${label}${
          id === "cart" && count ? `<span class="dot">${count}</span>` : ""
        }</button>`
    )
    .join("");
  $nav.querySelectorAll("button").forEach((b) => (b.onclick = () => (haptic(), switchTab(b.dataset.tab))));
}

// ---------- каталог ----------

async function loadProducts() {
  state.products = await api("/api/products");
}

screens.catalog = async () => {
  if (!state.products.length) {
    $view.innerHTML = loaderHtml();
    await loadProducts();
  }
  const cats = ["Все", ...new Set(state.products.map((p) => p.category).filter(Boolean))];
  if (!cats.includes(state.category)) state.category = "Все";
  const list = state.products.filter((p) => state.category === "Все" || p.category === state.category);

  $view.innerHTML = `
    <div class="hero"><img src="assets/logo-banner.jpg" alt="DAYZ DROP"></div>
    ${cats.length > 2 ? `<div class="chips">${cats.map((c) => `<button class="chip ${c === state.category ? "active" : ""}" data-cat="${esc(c)}">${esc(c)}</button>`).join("")}</div>` : ""}
    ${
      list.length
        ? `<div class="grid">${list
            .map(
              (p) => `
          <button class="card" data-id="${p.id}">
            <div class="card-img">${photoHtml(p.photos[0])}${stockOf(p) ? "" : '<span class="badge dark">Нет в наличии</span>'}</div>
            <div class="card-body"><div class="card-title">${esc(p.title)}</div><div class="price">${money(p.price)}</div></div>
          </button>`
            )
            .join("")}</div>`
        : `<div class="empty"><div class="big">🖤</div>Скоро здесь появятся вещи.<br>Загляни чуть позже.</div>`
    }`;
  $view.querySelectorAll("[data-cat]").forEach((b) => (b.onclick = () => ((state.category = b.dataset.cat), render())));
  $view.querySelectorAll(".card").forEach((b) => (b.onclick = () => go("product", { id: +b.dataset.id })));
};

screens.product = async ({ id }) => {
  const p = state.products.find((x) => x.id === id);
  if (!p) throw new Error("Товар не найден");
  let size = (p.sizes.find((s) => s.stock > 0) || {}).size;
  if (p.sizes.filter((s) => s.stock > 0).length > 1) size = null;

  const photos = p.photos.length ? p.photos : [null];
  $view.innerHTML = `
    <div class="gallery" id="gallery">${photos.map((ph) => `<div>${photoHtml(ph)}</div>`).join("")}</div>
    ${photos.length > 1 ? `<div class="dots" id="dots">${photos.map((_, i) => `<i class="${i ? "" : "on"}"></i>`).join("")}</div>` : ""}
    <h1 class="p-title">${esc(p.title)}</h1>
    <div class="p-price">${money(p.price)}</div>
    <div class="label">Размер</div>
    <div class="sizes">${p.sizes
      .map(
        (s) =>
          `<button class="size" data-size="${esc(s.size)}" ${s.stock ? "" : "disabled"}>${esc(s.size)}${
            s.stock && s.stock <= 3 ? `<small>ост. ${s.stock}</small>` : ""
          }</button>`
      )
      .join("")}</div>
    ${p.description ? `<div class="p-desc">${esc(p.description)}</div>` : ""}`;

  const gallery = document.getElementById("gallery");
  const dots = document.getElementById("dots");
  if (dots)
    gallery.onscroll = () => {
      const i = Math.round(gallery.scrollLeft / gallery.clientWidth);
      [...dots.children].forEach((d, j) => d.classList.toggle("on", i === j));
    };

  const bar = setBar(`<button class="btn" id="addBtn"></button>`);
  const addBtn = bar.querySelector("#addBtn");
  const refresh = () => {
    $view.querySelectorAll(".size").forEach((b) => b.classList.toggle("active", b.dataset.size === size));
    const inCart = state.cart.find((i) => i.product_id === p.id && i.size === size);
    if (!stockOf(p)) {
      addBtn.textContent = "Нет в наличии";
      addBtn.disabled = true;
    } else if (!size) {
      addBtn.textContent = "Выбери размер";
      addBtn.disabled = true;
    } else {
      addBtn.disabled = false;
      addBtn.textContent = inCart ? `В корзине · ${inCart.qty} шт — ещё` : `В корзину · ${money(p.price)}`;
    }
  };
  $view.querySelectorAll(".size").forEach((b) => (b.onclick = () => ((size = b.dataset.size), haptic(), refresh())));
  addBtn.onclick = () => {
    const stock = p.sizes.find((s) => s.size === size).stock;
    const item = state.cart.find((i) => i.product_id === p.id && i.size === size);
    if ((item ? item.qty : 0) >= stock) return toast(`Больше нет в наличии (${stock} шт)`, true);
    if (item) item.qty += 1;
    else state.cart.push({ product_id: p.id, size, qty: 1 });
    saveCart();
    toast("Добавлено в корзину");
    refresh();
  };
  refresh();
};

// ---------- корзина и оформление ----------

function cartLines() {
  return state.cart
    .map((i) => {
      const p = state.products.find((x) => x.id === i.product_id);
      const s = p && p.sizes.find((x) => x.size === i.size);
      return { ...i, product: p, stock: s ? s.stock : 0 };
    })
    .filter((l) => l.product);
}

screens.cart = async () => {
  $view.innerHTML = loaderHtml();
  await loadProducts();
  // Убираем то, чего больше нет, и подрезаем количество под остаток
  state.cart = cartLines()
    .filter((l) => l.stock > 0)
    .map((l) => ({ product_id: l.product_id, size: l.size, qty: Math.min(l.qty, l.stock) }));
  saveCart();

  const lines = cartLines();
  if (!lines.length) {
    $view.innerHTML = `<h1 class="title">Корзина</h1><div class="empty"><div class="big">🛒</div>Корзина пуста<br><br><button class="btn ghost sm" id="toCat">В каталог</button></div>`;
    document.getElementById("toCat").onclick = () => switchTab("catalog");
    return;
  }
  const total = lines.reduce((s, l) => s + l.product.price * l.qty, 0);
  $view.innerHTML = `
    <h1 class="title">Корзина</h1>
    <div class="list">${lines
      .map(
        (l, idx) => `
      <div class="row">
        <div class="thumb">${photoHtml(l.product.photos[0])}</div>
        <div class="grow">
          <div class="r-title">${esc(l.product.title)}</div>
          <div class="r-sub">Размер ${esc(l.size)} · ${money(l.product.price)}</div>
          <div class="stepper"><button data-dec="${idx}">−</button><span>${l.qty}</span><button data-inc="${idx}">+</button></div>
        </div>
        <button class="icon-btn" data-rm="${idx}" aria-label="Удалить">✕</button>
      </div>`
      )
      .join("")}</div>
    <div class="total"><span class="subtle">Итого</span><b>${money(total)}</b></div>`;

  const change = (idx, delta) => {
    const l = lines[idx];
    const item = state.cart.find((i) => i.product_id === l.product_id && i.size === l.size);
    if (delta > 0 && item.qty >= l.stock) return toast(`Больше нет в наличии (${l.stock} шт)`, true);
    item.qty += delta;
    if (item.qty <= 0) state.cart = state.cart.filter((i) => i !== item);
    saveCart();
    haptic();
    screens.cart();
  };
  $view.querySelectorAll("[data-inc]").forEach((b) => (b.onclick = () => change(+b.dataset.inc, 1)));
  $view.querySelectorAll("[data-dec]").forEach((b) => (b.onclick = () => change(+b.dataset.dec, -1)));
  $view.querySelectorAll("[data-rm]").forEach((b) => (b.onclick = () => change(+b.dataset.rm, -999)));
  setBar(`<button class="btn" id="checkout">Оформить · ${money(total)}</button>`).querySelector("#checkout").onclick = () =>
    go("checkout");
};

screens.checkout = async () => {
  const lines = cartLines();
  const total = lines.reduce((s, l) => s + l.product.price * l.qty, 0);
  const opts = state.settings.delivery_options;
  let saved = {};
  try {
    saved = JSON.parse(localStorage.getItem("dayz_customer") || "{}");
  } catch (_) {}
  const user = (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) || {};
  let delivery = opts.includes(saved.delivery) ? saved.delivery : opts[0];

  $view.innerHTML = `
    <h1 class="title">Оформление</h1>
    <form id="form">
      <label class="field"><span>Имя и фамилия</span><input class="input" name="customer_name" required value="${esc(saved.customer_name || [user.first_name, user.last_name].filter(Boolean).join(" "))}"></label>
      <label class="field"><span>Телефон</span><input class="input" name="phone" type="tel" required value="${esc(saved.phone || "")}" placeholder="+7 900 000-00-00"></label>
      <div class="field"><span>Доставка</span><div class="chips" id="delivery">${opts
        .map((o) => `<button type="button" class="chip" data-d="${esc(o)}">${esc(o)}</button>`)
        .join("")}</div></div>
      <label class="field" id="addrField"><span>Город и адрес / пункт выдачи</span><textarea class="input" name="address">${esc(saved.address || "")}</textarea></label>
      <label class="field"><span>Комментарий</span><input class="input" name="comment" placeholder="Необязательно"></label>
    </form>
    <div class="panel">
      ${lines.map((l) => `<div class="kv"><span>${esc(l.product.title)} · ${esc(l.size)} × ${l.qty}</span><span>${money(l.product.price * l.qty)}</span></div>`).join("")}
      <div class="kv"><span><b>Итого</b></span><span><b>${money(total)}</b></span></div>
    </div>
    <p class="subtle" style="margin-top:12px">После оформления бот пришлёт реквизиты для перевода. Оплату проверяем вручную по чеку.</p>`;

  const form = document.getElementById("form");
  const addrField = document.getElementById("addrField");
  const refresh = () => {
    $view.querySelectorAll("[data-d]").forEach((b) => b.classList.toggle("active", b.dataset.d === delivery));
    addrField.style.display = /самовывоз/i.test(delivery || "") ? "none" : "";
  };
  $view.querySelectorAll("[data-d]").forEach((b) => (b.onclick = () => ((delivery = b.dataset.d), refresh())));
  refresh();

  const btn = setBar(`<button class="btn" id="submit">Подтвердить заказ</button>`).querySelector("#submit");
  btn.onclick = async () => {
    if (!form.reportValidity()) return;
    const data = Object.fromEntries(new FormData(form));
    data.delivery = delivery;
    try {
      localStorage.setItem("dayz_customer", JSON.stringify({ customer_name: data.customer_name, phone: data.phone, address: data.address, delivery }));
    } catch (_) {}
    btn.disabled = true;
    btn.textContent = "Оформляем…";
    try {
      const order = await api("/api/orders", { method: "POST", body: { ...data, items: state.cart } });
      state.cart = [];
      saveCart();
      state.products = [];
      haptic("ok");
      state.tab = "orders";
      renderNav();
      state.stack = [{ name: "orders" }, { name: "order", params: { id: order.id, fresh: true } }];
      render();
    } catch (err) {
      toast(err.message, true);
      btn.disabled = false;
      btn.textContent = "Подтвердить заказ";
    }
  };
};

// ---------- заказы покупателя ----------

screens.orders = async () => {
  $view.innerHTML = loaderHtml();
  const orders = await api("/api/orders/my");
  if (!orders.length) {
    $view.innerHTML = `<h1 class="title">Мои заказы</h1><div class="empty"><div class="big">📦</div>Заказов пока нет</div>`;
    return;
  }
  $view.innerHTML = `
    <h1 class="title">Мои заказы</h1>
    <div class="list">${orders
      .map(
        (o) => `
      <button class="row" data-id="${o.id}">
        <div class="thumb">${photoHtml(o.items[0] && o.items[0].photo)}</div>
        <div class="grow">
          <div class="r-title">Заказ #${o.id}</div>
          <div class="r-sub">${o.items.length} поз. · ${fmtDate(o.created_at)}</div>
          <div style="margin-top:6px">${statusBadge(o.status)}</div>
        </div>
        <div class="r-right"><b>${money(o.total)}</b></div>
      </button>`
      )
      .join("")}</div>`;
  $view.querySelectorAll("[data-id]").forEach((b) => (b.onclick = () => go("order", { id: +b.dataset.id })));
};

function itemsPanel(o) {
  return `<div class="panel">
    ${o.items.map((i) => `<div class="kv"><span>${esc(i.title)} · ${esc(i.size)} × ${i.qty}</span><span>${money(i.price * i.qty)}</span></div>`).join("")}
    <div class="kv"><span><b>Итого</b></span><span><b>${money(o.total)}</b></span></div>
  </div>`;
}

function deliveryPanel(o) {
  return `<div class="panel">
    <div class="kv"><span>Получатель</span><span>${esc(o.customer_name)}</span></div>
    <div class="kv"><span>Телефон</span><span>${esc(o.phone)}</span></div>
    <div class="kv"><span>Доставка</span><span>${esc(o.delivery)}</span></div>
    ${o.address ? `<div class="kv"><span>Адрес</span><span>${esc(o.address)}</span></div>` : ""}
    ${o.comment ? `<div class="kv"><span>Комментарий</span><span>${esc(o.comment)}</span></div>` : ""}
    ${o.track ? `<div class="kv"><span>Трек-номер</span><span><b>${esc(o.track)}</b></span></div>` : ""}
  </div>`;
}

async function uploadReceipt(orderId, done) {
  const [file] = await pickFile("image/*,application/pdf");
  if (!file) return;
  toast("Отправляем чек…");
  try {
    await api(`/api/orders/${orderId}/receipt`, { method: "POST", file: await compressImage(file) });
    toast("Чек отправлен — проверяем оплату");
    done();
  } catch (err) {
    toast(err.message, true);
  }
}

screens.order = async ({ id, fresh }) => {
  $view.innerHTML = loaderHtml();
  const orders = await api("/api/orders/my");
  const o = orders.find((x) => x.id === id);
  if (!o) throw new Error("Заказ не найден");
  const needPay = o.status === "awaiting_payment";
  const support = supportUrl();

  $view.innerHTML = `
    <h1 class="title">${fresh ? "Заказ оформлен!" : `Заказ #${o.id}`}</h1>
    <div style="margin:-4px 0 14px">${statusBadge(o.status)} <span class="subtle">#${o.id} · ${fmtDate(o.created_at)}</span></div>
    ${
      needPay
        ? `<div class="panel">
        <div class="label" style="margin-top:0">Оплата переводом</div>
        <div>Переведи <b>${money(o.total)}</b> по реквизитам:</div>
        <div class="pay-details">${esc(state.settings.payment_details)}</div>
        <div class="kv"><span>Комментарий к переводу</span><span><b>Заказ #${o.id}</b></span></div>
        <div class="btn-row" style="margin-top:10px">
          <button class="btn ghost sm" id="copyDetails">Копировать реквизиты</button>
          <button class="btn ghost sm" id="copySum">Копировать сумму</button>
        </div>
        <p class="subtle" style="margin-top:12px">После перевода загрузи скриншот или PDF чека — или просто отправь его боту в чат. Мы проверим поступление и подтвердим заказ.</p>
      </div>`
        : ""
    }
    ${o.status === "checking" ? `<div class="panel">🔎 Чек получен — проверяем поступление денег. Как подтвердим, бот пришлёт сообщение.</div>` : ""}
    ${itemsPanel(o)}
    ${deliveryPanel(o)}
    <div class="stack" style="margin-top:14px">
      ${o.status === "checking" ? `<button class="btn ghost" id="reupload">Отправить другой чек</button>` : ""}
      ${support ? `<button class="btn ghost" id="support">Написать в поддержку</button>` : ""}
      ${needPay ? `<button class="btn danger" id="cancel">Отменить заказ</button>` : ""}
    </div>`;

  const reload = () => screens.order({ id });
  if (needPay) {
    document.getElementById("copyDetails").onclick = () => copy(state.settings.payment_details);
    document.getElementById("copySum").onclick = () => copy(String(o.total));
    setBar(`<button class="btn" id="upload">Загрузить чек</button>`).querySelector("#upload").onclick = () => uploadReceipt(o.id, reload);
    document.getElementById("cancel").onclick = async () => {
      if (!(await confirmDialog(`Отменить заказ #${o.id}?`))) return;
      try {
        await api(`/api/orders/${o.id}/cancel`, { method: "POST" });
        toast("Заказ отменён");
        state.products = [];
        reload();
      } catch (err) {
        toast(err.message, true);
      }
    };
  }
  const re = document.getElementById("reupload");
  if (re) re.onclick = () => uploadReceipt(o.id, reload);
  const sup = document.getElementById("support");
  if (sup) sup.onclick = openSupport;
};

// ---------- админка ----------

const ADMIN_TABS = [
  ["orders", "Заказы"],
  ["products", "Товары"],
  ["settings", "Настройки"],
  ["stats", "Статистика"],
];

function adminHeader() {
  return `<h1 class="title">Админка</h1>
    <div class="chips">${ADMIN_TABS.map(([id, l]) => `<button class="chip ${state.adminTab === id ? "active" : ""}" data-atab="${id}">${l}</button>`).join("")}</div>`;
}

function bindAdminTabs() {
  $view.querySelectorAll("[data-atab]").forEach((b) => (b.onclick = () => ((state.adminTab = b.dataset.atab), render())));
}

screens.admin = async () => {
  $view.innerHTML = adminHeader() + loaderHtml();
  bindAdminTabs();
  await adminTabs[state.adminTab]();
  bindAdminTabs();
};

const adminTabs = {};

adminTabs.orders = async () => {
  const [orders, stats] = await Promise.all([
    api(`/api/admin/orders${state.adminStatus ? `?status=${state.adminStatus}` : ""}`),
    api("/api/admin/stats"),
  ]);
  const counts = stats.by_status;
  const filters = [["", "Все"], ["checking", "На проверке"], ["awaiting_payment", "Ждут оплату"], ["paid", "Оплачены"], ["shipped", "Отправлены"], ["done", "Получены"], ["cancelled", "Отменены"]];
  $view.innerHTML = `${adminHeader()}
    <div class="chips">${filters
      .map(([s, l]) => `<button class="chip ${state.adminStatus === s ? "active" : ""}" data-st="${s}">${l}${s && counts[s] ? `<span class="count">${counts[s]}</span>` : ""}</button>`)
      .join("")}</div>
    ${
      orders.length
        ? `<div class="list">${orders
            .map(
              (o) => `
      <button class="row" data-id="${o.id}">
        <div class="grow">
          <div class="r-title">#${o.id} · ${esc(o.customer_name)}</div>
          <div class="r-sub">${o.items.map((i) => `${esc(i.title)} ${esc(i.size)}×${i.qty}`).join(", ")}</div>
          <div class="r-sub">${fmtDate(o.created_at)}</div>
          <div style="margin-top:6px">${statusBadge(o.status)}</div>
        </div>
        <div class="r-right"><b>${money(o.total)}</b></div>
      </button>`
            )
            .join("")}</div>`
        : `<div class="empty">Заказов нет</div>`
    }`;
  $view.querySelectorAll("[data-st]").forEach((b) => (b.onclick = () => ((state.adminStatus = b.dataset.st), render())));
  $view.querySelectorAll("[data-id]").forEach((b) => (b.onclick = () => go("adminOrder", { id: +b.dataset.id })));
};

screens.adminOrder = async ({ id }) => {
  $view.innerHTML = loaderHtml();
  const o = await api(`/api/admin/orders/${id}`);
  const tgLink = o.username ? `https://t.me/${o.username}` : null;
  const actions = {
    awaiting_payment: [["paid", "Отметить оплаченным", "ok"], ["cancelled", "Отменить заказ", "danger"]],
    checking: [["paid", "✅ Деньги пришли", "ok"], ["awaiting_payment", "❌ Деньги не пришли", "ghost"], ["cancelled", "Отменить заказ", "danger"]],
    paid: [["shipped", "Отправлен", ""], ["done", "Получен", "ghost"], ["cancelled", "Отменить заказ", "danger"]],
    shipped: [["done", "Получен", ""], ["cancelled", "Отменить заказ", "danger"]],
  }[o.status] || [];

  $view.innerHTML = `
    <h1 class="title">Заказ #${o.id}</h1>
    <div style="margin:-4px 0 14px">${statusBadge(o.status)} <span class="subtle">${fmtDate(o.created_at)}</span></div>
    <div class="panel">
      <div class="kv"><span>Покупатель</span><span>${esc(o.customer_name)}</span></div>
      <div class="kv"><span>Telegram</span><span>${o.username ? `@${esc(o.username)}` : "—"} · id ${o.user_id}</span></div>
      ${tgLink ? `<button class="btn ghost sm" id="writeUser" style="margin-top:8px">Написать покупателю</button>` : ""}
    </div>
    ${itemsPanel(o)}
    ${deliveryPanel(o)}
    <div class="panel">
      <div class="label" style="margin-top:0">Чек</div>
      ${
        o.receipt_file_id
          ? o.receipt_kind === "photo"
            ? `<div class="receipt"><img src="${photoUrl(o.receipt_file_id)}" alt="Чек"></div>`
            : `<button class="btn ghost sm" id="openReceipt">Открыть файл чека</button>`
          : `<div class="subtle">Покупатель ещё не прислал чек</div>`
      }
    </div>
    ${
      ["paid", "shipped"].includes(o.status)
        ? `<label class="field" style="margin-top:14px"><span>Трек-номер</span><input class="input" id="track" value="${esc(o.track || "")}" placeholder="Номер отправления"></label>`
        : ""
    }
    <div class="stack" style="margin-top:14px">${actions.map(([s, l, cls]) => `<button class="btn ${cls}" data-to="${s}">${l}</button>`).join("")}</div>`;

  if (tgLink) document.getElementById("writeUser").onclick = () => openLink(tgLink);
  const rc = document.getElementById("openReceipt");
  if (rc) rc.onclick = () => openLink(photoUrl(o.receipt_file_id));
  $view.querySelectorAll("[data-to]").forEach(
    (b) =>
      (b.onclick = async () => {
        const to = b.dataset.to;
        const trackEl = document.getElementById("track");
        const track = trackEl ? trackEl.value.trim() : undefined;
        if (to === "cancelled" && !(await confirmDialog(`Отменить заказ #${o.id}? Товары вернутся на склад.`))) return;
        if (to === "awaiting_payment" && !(await confirmDialog("Отклонить чек? Покупателю придёт сообщение, что оплата не найдена."))) return;
        try {
          await api(`/api/admin/orders/${o.id}/status`, { method: "POST", body: { status: to, track } });
          toast(`Статус: ${STATUS[to]}`);
          screens.adminOrder({ id });
        } catch (err) {
          toast(err.message, true);
        }
      })
  );
};

adminTabs.products = async () => {
  const products = await api("/api/admin/products");
  $view.innerHTML = `${adminHeader()}
    <button class="btn" id="addProduct" style="margin-bottom:14px">+ Добавить товар</button>
    ${
      products.length
        ? `<div class="list">${products
            .map(
              (p) => `
      <button class="row" data-id="${p.id}">
        <div class="thumb">${photoHtml(p.photos[0])}</div>
        <div class="grow">
          <div class="r-title">${esc(p.title)}</div>
          <div class="r-sub">${esc(p.category || "Без категории")} · ${money(p.price)}</div>
          <div class="r-sub">${p.sizes.map((s) => `${esc(s.size)}: ${s.stock}`).join(" · ")}</div>
          ${p.is_active ? "" : '<div style="margin-top:6px"><span class="badge">Скрыт</span></div>'}
        </div>
      </button>`
            )
            .join("")}</div>`
        : `<div class="empty">Товаров пока нет — добавь первый</div>`
    }`;
  state.adminProducts = products;
  document.getElementById("addProduct").onclick = () => go("productForm", {});
  $view.querySelectorAll("[data-id]").forEach((b) => (b.onclick = () => go("productForm", { id: +b.dataset.id })));
};

screens.productForm = async ({ id }) => {
  const existing = (state.adminProducts || []).find((p) => p.id === id);
  const p = existing
    ? JSON.parse(JSON.stringify(existing))
    : { title: "", category: "", price: "", description: "", sizes: [{ size: "S", stock: 0 }, { size: "M", stock: 0 }, { size: "L", stock: 0 }, { size: "XL", stock: 0 }], photos: [], is_active: true, sort: 0 };
  const categories = [...new Set((state.adminProducts || []).map((x) => x.category).filter(Boolean))];

  const draw = () => {
    $view.innerHTML = `
      <h1 class="title">${existing ? "Редактировать" : "Новый товар"}</h1>
      <div class="label" style="margin-top:0">Фото (первое — обложка)</div>
      <div class="photos">
        ${p.photos.map((ph, i) => `<div><img src="${photoUrl(ph)}" alt=""><button class="rm" data-rmph="${i}">✕</button></div>`).join("")}
        ${p.photos.length < 10 ? `<label id="addPhoto">+</label>` : ""}
      </div>
      <label class="field"><span>Название</span><input class="input" id="f_title" value="${esc(p.title)}"></label>
      <label class="field"><span>Категория</span><input class="input" id="f_category" list="cats" value="${esc(p.category)}" placeholder="Худи, футболки…">
        <datalist id="cats">${categories.map((c) => `<option value="${esc(c)}">`).join("")}</datalist></label>
      <label class="field"><span>Цена, ${esc(state.settings.currency)}</span><input class="input" id="f_price" type="number" inputmode="numeric" min="0" value="${esc(p.price)}"></label>
      <label class="field"><span>Описание</span><textarea class="input" id="f_description" placeholder="Материал, посадка, уход…">${esc(p.description)}</textarea></label>
      <div class="field"><span>Размеры и остатки</span>
        ${p.sizes
          .map(
            (s, i) => `<div class="size-row">
          <input class="input" data-sz="${i}" value="${esc(s.size)}" placeholder="Размер">
          <input class="input" data-st="${i}" type="number" inputmode="numeric" min="0" value="${s.stock}" placeholder="Шт">
          <button class="icon-btn" data-rmsz="${i}">✕</button></div>`
          )
          .join("")}
        <div class="btn-row"><button class="btn ghost sm" id="addSize">+ Размер</button><button class="btn ghost sm" id="oneSize">One size</button></div>
      </div>
      <label class="field"><span>Порядок в каталоге (меньше — выше)</span><input class="input" id="f_sort" type="number" value="${esc(p.sort)}"></label>
      <label class="check"><input type="checkbox" id="f_active" ${p.is_active ? "checked" : ""}> Показывать в каталоге</label>
      ${existing ? `<button class="btn danger" id="delete">Удалить товар</button>` : ""}`;

    const sync = () => {
      p.title = document.getElementById("f_title").value;
      p.category = document.getElementById("f_category").value;
      p.price = document.getElementById("f_price").value;
      p.description = document.getElementById("f_description").value;
      p.sort = document.getElementById("f_sort").value;
      p.is_active = document.getElementById("f_active").checked;
      p.sizes = p.sizes.map((s, i) => ({ size: $view.querySelector(`[data-sz="${i}"]`).value.trim(), stock: +$view.querySelector(`[data-st="${i}"]`).value || 0 }));
    };

    $view.querySelectorAll("[data-rmph]").forEach((b) => (b.onclick = () => (sync(), p.photos.splice(+b.dataset.rmph, 1), draw())));
    $view.querySelectorAll("[data-rmsz]").forEach((b) => (b.onclick = () => (sync(), p.sizes.splice(+b.dataset.rmsz, 1), draw())));
    document.getElementById("addSize").onclick = () => (sync(), p.sizes.push({ size: "", stock: 0 }), draw());
    document.getElementById("oneSize").onclick = () => (sync(), (p.sizes = [{ size: "One size", stock: 0 }]), draw());
    const add = document.getElementById("addPhoto");
    if (add)
      add.onclick = async () => {
        sync();
        const files = await pickFile("image/*", true);
        for (const f of files.slice(0, 10 - p.photos.length)) {
          toast("Загружаем фото…");
          try {
            const { file_id } = await api("/api/admin/upload", { method: "POST", file: await compressImage(f) });
            p.photos.push(file_id);
          } catch (err) {
            toast(err.message, true);
          }
        }
        draw();
      };
    const del = document.getElementById("delete");
    if (del)
      del.onclick = async () => {
        if (!(await confirmDialog(`Удалить «${p.title}»? Старые заказы останутся.`))) return;
        await api(`/api/admin/products/${id}`, { method: "DELETE" });
        state.products = [];
        toast("Товар удалён");
        back();
      };

    setBar(`<button class="btn" id="save">Сохранить</button>`).querySelector("#save").onclick = async () => {
      sync();
      try {
        await api(existing ? `/api/admin/products/${id}` : "/api/admin/products", { method: existing ? "PUT" : "POST", body: p });
        state.products = [];
        toast("Сохранено");
        back();
      } catch (err) {
        toast(err.message, true);
      }
    };
  };
  draw();
};

adminTabs.settings = async () => {
  const s = await api("/api/admin/settings");
  $view.innerHTML = `${adminHeader()}
    <label class="field"><span>Реквизиты для оплаты</span><textarea class="input" id="s_payment_details" rows="5" placeholder="Карта 0000 0000 0000 0000&#10;Банк, получатель">${esc(s.payment_details)}</textarea></label>
    <label class="field"><span>Валюта</span><input class="input" id="s_currency" value="${esc(s.currency)}"></label>
    <label class="field"><span>Способы доставки (каждый с новой строки)</span><textarea class="input" id="s_delivery_options">${esc(s.delivery_options)}</textarea></label>
    <label class="field"><span>О магазине</span><textarea class="input" id="s_about">${esc(s.about)}</textarea></label>`;
  setBar(`<button class="btn" id="save">Сохранить настройки</button>`).querySelector("#save").onclick = async () => {
    const body = {};
    ["payment_details", "currency", "delivery_options", "about"].forEach((k) => (body[k] = document.getElementById(`s_${k}`).value));
    try {
      await api("/api/admin/settings", { method: "PUT", body });
      const boot = await api("/api/bootstrap");
      state.settings = boot.settings;
      toast("Настройки сохранены");
    } catch (err) {
      toast(err.message, true);
    }
  };
};

adminTabs.stats = async () => {
  const s = await api("/api/admin/stats");
  const c = (k) => s.by_status[k] || 0;
  const total = Object.values(s.by_status).reduce((a, b) => a + b, 0);
  $view.innerHTML = `${adminHeader()}
    <div class="stats">
      <div class="stat"><b>${money(s.revenue)}</b><span>Выручка (оплаченные)</span></div>
      <div class="stat"><b>${total}</b><span>Всего заказов</span></div>
      <div class="stat"><b>${c("checking")}</b><span>Ждут проверки оплаты</span></div>
      <div class="stat"><b>${c("awaiting_payment")}</b><span>Ждут оплату</span></div>
      <div class="stat"><b>${c("paid")}</b><span>Нужно отправить</span></div>
      <div class="stat"><b>${c("shipped")}</b><span>В пути</span></div>
      <div class="stat"><b>${s.users}</b><span>Пользователей бота</span></div>
      <div class="stat"><b>${s.products}</b><span>Товаров</span></div>
    </div>`;
};

// ---------- старт ----------

async function boot() {
  if (tg) {
    tg.ready();
    tg.expand();
    try {
      tg.setHeaderColor("#000000");
      tg.setBackgroundColor("#000000");
    } catch (_) {}
    if (can("6.1")) tg.BackButton.onClick(back);
  }
  $view.innerHTML = loaderHtml("Загружаем DAYZ DROP…");

  if (!tg || !tg.initData) {
    $view.innerHTML = `<div class="hero"><img src="assets/logo-banner.jpg" alt="DAYZ DROP"></div><div class="empty">Открой магазин через бота в Telegram 🖤</div>`;
    return;
  }

  try {
    const data = await api("/api/bootstrap");
    state.me = data.user;
    state.isAdmin = data.is_admin;
    state.botUsername = data.bot_username;
    state.settings = data.settings;
  } catch (err) {
    $view.innerHTML = `<div class="empty"><div class="big">⚠️</div>${esc(err.message)}<br><br><button class="btn ghost sm" onclick="location.reload()">Повторить</button></div>`;
    return;
  }

  // Ссылки из бота: ?page=order&id=12 или ?page=admin&order=12
  const page = qs.get("page");
  if (page === "admin" && state.isAdmin) {
    state.tab = "admin";
    state.stack = [{ name: "admin" }];
    if (qs.get("order")) state.stack.push({ name: "adminOrder", params: { id: +qs.get("order") } });
  } else if (page === "order" && qs.get("id")) {
    state.tab = "orders";
    state.stack = [{ name: "orders" }, { name: "order", params: { id: +qs.get("id") } }];
  } else {
    state.stack = [{ name: "catalog" }];
  }
  renderNav();
  render();
}

boot();

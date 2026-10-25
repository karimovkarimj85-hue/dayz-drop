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
  botUsername: null,
  settings: { currency: "₽", delivery_options: [], payment_details: "" },
  products: [],
  cart: loadCart(),
  tab: "catalog",
  stack: [],
  category: "Все",
  adminTab: "orders",
  adminStatus: "",
  adminProducts: [],
};

// ---------- иконки (линейные, в духе SF Symbols) ----------

const ICON_PATHS = {
  bag: '<path d="M5.5 8h13l-1 12.5h-11z"/><path d="M9 8V6.5a3 3 0 0 1 6 0V8"/>',
  cart: '<path d="M3 4h2.2l2.3 10.5h10.3L20 7.2H6.2"/><circle cx="9" cy="19" r="1.4"/><circle cx="17" cy="19" r="1.4"/>',
  box: '<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
  sliders: '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  chevronRight: '<path d="m9 5 7 7-7 7"/>',
  chevronLeft: '<path d="m15 5-7 7 7 7"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  xmark: '<path d="M6 6l12 12M18 6 6 18"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  photo: '<rect x="3" y="5" width="18" height="14" rx="2.5"/><circle cx="9" cy="10" r="1.6"/><path d="m21 16-5-5-8 8"/>',
  tray: '<path d="M4 13h4l1.5 2.5h5L16 13h4"/><path d="M4 13 6.5 5h11L20 13v6H4z"/><path d="M12 3v7M9.5 7.5 12 10l2.5-2.5"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  doc: '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M10 17h6"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2.5"/><path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4h-9A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8"/>',
  bubble: '<path d="M20 11.5c0 4.1-3.6 7.5-8 7.5-1.3 0-2.5-.3-3.6-.8L4 19.5l1.2-3.7A7.2 7.2 0 0 1 4 11.5C4 7.4 7.6 4 12 4s8 3.4 8 7.5z"/>',
  truck: '<path d="M2.5 6h11v10h-11zM13.5 9.5H18l3 3.5V16h-7.5"/><circle cx="7" cy="17.5" r="1.8"/><circle cx="17" cy="17.5" r="1.8"/>',
  hanger: '<path d="M10 6.5a2 2 0 1 1 2.6 1.9c-.4.1-.6.5-.6.9v.7L3.5 15.5A1.4 1.4 0 0 0 4.3 18h15.4a1.4 1.4 0 0 0 .8-2.5L12 10"/>',
  card: '<rect x="3" y="5.5" width="18" height="13" rx="2.5"/><path d="M3 10h18M7 15h4"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
  checkCircle: '<circle cx="12" cy="12" r="8.5"/><path d="m8.5 12.3 2.4 2.4 4.6-5"/>',
  xCircle: '<circle cx="12" cy="12" r="8.5"/><path d="m9 9 6 6M15 9l-6 6"/>',
  warning: '<path d="M12 4 2.8 19.5h18.4z"/><path d="M12 10v4.5M12 17.3v.2"/>',
  person: '<circle cx="12" cy="8" r="3.8"/><path d="M4.5 20c.8-3.6 3.8-5.5 7.5-5.5s6.7 1.9 7.5 5.5"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  arrowUp: '<path d="M12 19V5M6 11l6-6 6 6"/>',
  arrowDown: '<path d="M12 5v14M6 13l6 6 6-6"/>',
  arrowBack: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
  pencil: '<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
  rub: '<path d="M8 20V4h5.5a4 4 0 0 1 0 8H6M6 16h8"/>',
};

const icon = (name, cls = "") => `<svg class="ico ${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICON_PATHS[name] || ""}</svg>`;

// ---------- утилиты ----------

const esc = (s) =>
  String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const money = (n) => `${Number(n || 0).toLocaleString("ru-RU")} ${state.settings.currency}`;
const photoUrl = (id) => `${API}/api/photo/${encodeURIComponent(id)}`;
const stockOf = (p) => p.sizes.reduce((s, x) => s + x.stock, 0);
const can = (v) => tg && tg.isVersionAtLeast && tg.isVersionAtLeast(v);
const fmtDate = (iso) => (iso ? new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "");
const plural = (n, one, few, many) => {
  const m10 = n % 10, m100 = n % 100;
  return m10 === 1 && m100 !== 11 ? one : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? few : many;
};

function haptic(type) {
  try {
    if (!can("6.1")) return;
    if (type === "ok" || type === "error") tg.HapticFeedback.notificationOccurred(type === "ok" ? "success" : "error");
    else if (type === "select") tg.HapticFeedback.selectionChanged();
    else tg.HapticFeedback.impactOccurred("light");
  } catch (_) {}
}

let toastTimer;
function toast(text, isError) {
  $toast.innerHTML = `${icon(isError ? "xCircle" : "checkCircle")}<span>${esc(text)}</span>`;
  $toast.className = "toast show" + (isError ? " err" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($toast.className = "toast"), 2400);
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
    if (l) l.textContent = "Сервер просыпается — это может занять до минуты";
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

// ---------- кусочки разметки ----------

const loaderHtml = (text = "Загрузка") => `<div class="loader"><div class="spin"></div><div class="slow">${text}</div></div>`;
const photoHtml = (id) => (id ? `<img src="${photoUrl(id)}" loading="lazy" alt="">` : `<div class="placeholder"><img src="assets/logo.jpg" alt=""></div>`);
const statusPill = (s) => `<span class="status st-${s}">${STATUS[s] || s}</span>`;
const title = (text) => `<h1 class="large-title">${esc(text)}</h1>`;
const header = (text) => `<div class="section-header">${esc(text)}</div>`;
const footer = (text) => `<div class="section-footer">${text}</div>`;
const kv = (k, v) => `<div class="cell kv"><span class="title">${esc(k)}</span><span class="value">${v}</span></div>`;

function emptyHtml(ico, head, text, button) {
  return `<div class="empty"><div class="e-ico">${icon(ico, "lg")}</div><b>${esc(head)}</b>${text ? `<p>${esc(text)}</p>` : ""}${
    button ? `<button class="btn sm" id="emptyBtn">${esc(button)}</button>` : ""
  }</div>`;
}

const STATUS_INFO = {
  awaiting_payment: ["card", "c-orange", "Ждём оплату", "Переведи сумму по реквизитам ниже и загрузи чек."],
  checking: ["clock", "c-blue", "Проверяем оплату", "Чек получен. Как только подтвердим поступление — бот пришлёт сообщение."],
  paid: ["checkCircle", "c-green", "Оплата подтверждена", "Собираем заказ и скоро отправим. Трек-номер придёт в бота."],
  shipped: ["truck", "c-purple", "Заказ в пути", "Трек-номер указан ниже."],
  done: ["box", "c-gray", "Заказ получен", "Спасибо, что выбрал DAYZ DROP."],
  cancelled: ["xCircle", "c-red", "Заказ отменён", "Если это ошибка — напиши в поддержку."],
};

function statusCard(status) {
  const [ico, color, head, text] = STATUS_INFO[status] || STATUS_INFO.awaiting_payment;
  return `<div class="status-card"><div class="t-ico ${color}">${icon(ico)}</div><div><b>${head}</b><p>${text}</p></div></div>`;
}

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
    $view.innerHTML = emptyHtml("warning", "Что-то пошло не так", err.message, "Повторить");
    document.getElementById("emptyBtn").onclick = render;
  }
  if (canGoBack && !can("6.1")) {
    $view.insertAdjacentHTML("afterbegin", `<button class="back" id="backBtn">${icon("chevronLeft")}Назад</button>`);
    document.getElementById("backBtn").onclick = back;
  }
}

function go(name, params) {
  haptic();
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

function renderNav() {
  const tabs = [
    ["catalog", "Каталог", "bag"],
    ["cart", "Корзина", "cart"],
    ["orders", "Заказы", "box"],
  ];
  if (state.isAdmin) tabs.push(["admin", "Управление", "sliders"]);
  const count = cartCount();
  $nav.innerHTML = tabs
    .map(
      ([id, label, ico]) =>
        `<button data-tab="${id}" class="${state.tab === id ? "active" : ""}">${icon(ico)}${label}${
          id === "cart" && count ? `<span class="badge">${count}</span>` : ""
        }</button>`
    )
    .join("");
  $nav.querySelectorAll("button").forEach((b) => (b.onclick = () => (haptic("select"), switchTab(b.dataset.tab))));
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
    ${title("Каталог")}
    ${cats.length > 2 ? `<div class="pills">${cats.map((c) => `<button class="pill ${c === state.category ? "active" : ""}" data-cat="${esc(c)}">${esc(c)}</button>`).join("")}</div>` : ""}
    ${
      list.length
        ? `<div class="grid">${list
            .map(
              (p) => `
          <button class="card" data-id="${p.id}">
            <div class="card-img">${photoHtml(p.photos[0])}${stockOf(p) ? "" : '<span class="tag">Нет в наличии</span>'}</div>
            <div class="card-title">${esc(p.title)}</div>
            <div class="card-price">${money(p.price)}</div>
          </button>`
            )
            .join("")}</div>`
        : emptyHtml("hanger", "Скоро здесь появятся вещи", "Загляни чуть позже — готовим новый дроп.")
    }`;
  $view.querySelectorAll("[data-cat]").forEach((b) => (b.onclick = () => ((state.category = b.dataset.cat), haptic("select"), render())));
  $view.querySelectorAll(".card").forEach((b) => (b.onclick = () => go("product", { id: +b.dataset.id })));
};

screens.product = async ({ id }) => {
  const p = state.products.find((x) => x.id === id);
  if (!p) throw new Error("Товар не найден");
  const available = p.sizes.filter((s) => s.stock > 0);
  let size = available.length === 1 ? available[0].size : null;

  const photos = p.photos.length ? p.photos : [null];
  $view.innerHTML = `
    <div class="gallery" id="gallery">${photos.map((ph) => `<div>${photoHtml(ph)}</div>`).join("")}</div>
    ${photos.length > 1 ? `<div class="dots" id="dots">${photos.map((_, i) => `<i class="${i ? "" : "on"}"></i>`).join("")}</div>` : ""}
    ${p.category ? `<div class="p-cat">${esc(p.category)}</div>` : ""}
    <h1 class="p-title" ${p.category ? "" : 'style="margin-top:18px"'}>${esc(p.title)}</h1>
    <div class="p-price">${money(p.price)}</div>
    <div class="section-header" style="margin-left:0">Размер</div>
    <div class="sizes">${p.sizes
      .map((s) => `<button class="size" data-size="${esc(s.size)}" ${s.stock ? "" : "disabled"}>${esc(s.size)}${s.stock && s.stock <= 3 ? `<small>осталось ${s.stock}</small>` : ""}</button>`)
      .join("")}</div>
    ${p.description ? `<div class="section-header" style="margin-left:0">Описание</div><div class="p-desc">${esc(p.description)}</div>` : ""}`;

  const gallery = document.getElementById("gallery");
  const dots = document.getElementById("dots");
  if (dots)
    gallery.onscroll = () => {
      const i = Math.round(gallery.scrollLeft / gallery.clientWidth);
      [...dots.children].forEach((d, j) => d.classList.toggle("on", i === j));
    };

  const addBtn = setBar(`<button class="btn" id="addBtn"></button>`).querySelector("#addBtn");
  const refresh = () => {
    $view.querySelectorAll(".size").forEach((b) => b.classList.toggle("active", b.dataset.size === size));
    const inCart = state.cart.find((i) => i.product_id === p.id && i.size === size);
    addBtn.disabled = !stockOf(p) || !size;
    if (!stockOf(p)) addBtn.textContent = "Нет в наличии";
    else if (!size) addBtn.textContent = "Выбери размер";
    else addBtn.innerHTML = inCart ? `${icon("check")} В корзине · ${inCart.qty} шт` : `Добавить в корзину · ${money(p.price)}`;
  };
  $view.querySelectorAll(".size").forEach((b) => (b.onclick = () => ((size = b.dataset.size), haptic("select"), refresh())));
  addBtn.onclick = () => {
    const stock = p.sizes.find((s) => s.size === size).stock;
    const item = state.cart.find((i) => i.product_id === p.id && i.size === size);
    if ((item ? item.qty : 0) >= stock) return toast(`Больше нет в наличии — всего ${stock} шт`, true);
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
    $view.innerHTML = title("Корзина") + emptyHtml("cart", "Корзина пуста", "Добавь вещи из каталога — они появятся здесь.", "Перейти в каталог");
    document.getElementById("emptyBtn").onclick = () => switchTab("catalog");
    return;
  }
  const total = lines.reduce((s, l) => s + l.product.price * l.qty, 0);
  const units = lines.reduce((s, l) => s + l.qty, 0);
  $view.innerHTML = `
    ${title("Корзина")}
    <div class="group">${lines
      .map(
        (l, idx) => `
      <div class="cell has-thumb">
        <div class="thumb">${photoHtml(l.product.photos[0])}</div>
        <div class="grow">
          <div class="title">${esc(l.product.title)}</div>
          <div class="sub">Размер ${esc(l.size)} · ${money(l.product.price)}</div>
          <div style="margin-top:8px" class="stepper"><button data-dec="${idx}" aria-label="Меньше">${icon(l.qty > 1 ? "minus" : "trash")}</button><span class="div"></span><span>${l.qty}</span><span class="div"></span><button data-inc="${idx}" aria-label="Больше">${icon("plus")}</button></div>
        </div>
      </div>`
      )
      .join("")}</div>
    <div class="group" style="margin-top:20px">
      ${kv(`${units} ${plural(units, "товар", "товара", "товаров")}`, money(total))}
      ${kv("Доставка", "по тарифу службы")}
      <div class="cell total"><span class="title">Итого</span><span class="value" style="flex:1">${money(total)}</span></div>
    </div>`;

  const change = (idx, delta) => {
    const l = lines[idx];
    const item = state.cart.find((i) => i.product_id === l.product_id && i.size === l.size);
    if (delta > 0 && item.qty >= l.stock) return toast(`Больше нет в наличии — всего ${l.stock} шт`, true);
    item.qty += delta;
    if (item.qty <= 0) state.cart = state.cart.filter((i) => i !== item);
    saveCart();
    haptic("select");
    screens.cart();
  };
  $view.querySelectorAll("[data-inc]").forEach((b) => (b.onclick = () => change(+b.dataset.inc, 1)));
  $view.querySelectorAll("[data-dec]").forEach((b) => (b.onclick = () => change(+b.dataset.dec, -1)));
  setBar(`<button class="btn" id="checkout">Оформить заказ</button>`).querySelector("#checkout").onclick = () => go("checkout");
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
    ${title("Оформление")}
    <form id="form" onsubmit="return false">
      ${header("Получатель")}
      <div class="group">
        <div class="cell field"><label for="f_name">Имя и фамилия</label><input class="input" id="f_name" name="customer_name" required autocomplete="name" value="${esc(saved.customer_name || [user.first_name, user.last_name].filter(Boolean).join(" "))}"></div>
        <div class="cell field"><label for="f_phone">Телефон</label><input class="input" id="f_phone" name="phone" type="tel" required autocomplete="tel" value="${esc(saved.phone || "")}" placeholder="+7 900 000-00-00"></div>
      </div>
      ${header("Доставка")}
      <div class="group" id="delivery">${opts
        .map((o) => `<button type="button" class="cell tap" data-d="${esc(o)}"><span class="grow title">${esc(o)}</span><span class="check-ico">${icon("check")}</span></button>`)
        .join("")}</div>
      <div id="addrBlock">
        ${header("Адрес")}
        <div class="group"><div class="cell field"><label for="f_addr">Город, адрес или пункт выдачи</label><textarea class="input" id="f_addr" name="address" rows="2">${esc(saved.address || "")}</textarea></div></div>
      </div>
      ${header("Комментарий")}
      <div class="group"><div class="cell"><input class="input" name="comment" placeholder="Необязательно"></div></div>
    </form>
    ${header("Заказ")}
    <div class="group">
      ${lines.map((l) => kv(`${l.product.title} · ${l.size} × ${l.qty}`, money(l.product.price * l.qty))).join("")}
      <div class="cell total"><span class="title">Итого</span><span class="value" style="flex:1">${money(total)}</span></div>
    </div>
    ${footer("После оформления бот пришлёт реквизиты для перевода. Оплату проверяем вручную по чеку.")}`;

  const form = document.getElementById("form");
  const addrBlock = document.getElementById("addrBlock");
  const refresh = () => {
    $view.querySelectorAll("[data-d]").forEach((b) => (b.querySelector(".check-ico").style.visibility = b.dataset.d === delivery ? "visible" : "hidden"));
    addrBlock.style.display = /самовывоз/i.test(delivery || "") ? "none" : "";
  };
  $view.querySelectorAll("[data-d]").forEach((b) => (b.onclick = () => ((delivery = b.dataset.d), haptic("select"), refresh())));
  refresh();

  const btn = setBar(`<button class="btn" id="submit">Подтвердить · ${money(total)}</button>`).querySelector("#submit");
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
      btn.textContent = `Подтвердить · ${money(total)}`;
    }
  };
};

// ---------- заказы покупателя ----------

function orderRow(o, admin) {
  const who = admin ? esc(o.customer_name) : `${o.items.length} ${plural(o.items.length, "позиция", "позиции", "позиций")}`;
  return `
    <button class="cell tap has-thumb" data-id="${o.id}">
      <div class="thumb">${photoHtml(o.items[0] && o.items[0].photo)}</div>
      <div class="grow">
        <div class="title">Заказ #${o.id}</div>
        <div class="sub">${who} · ${fmtDate(o.created_at)}</div>
        <div style="margin-top:6px">${statusPill(o.status)}</div>
      </div>
      <span class="value">${money(o.total)}</span>${icon("chevronRight", "chev")}
    </button>`;
}

screens.orders = async () => {
  $view.innerHTML = loaderHtml();
  const orders = await api("/api/orders/my");
  if (!orders.length) {
    $view.innerHTML = title("Заказы") + emptyHtml("box", "Заказов пока нет", "Оформленные заказы и их статус будут здесь.", "Перейти в каталог");
    document.getElementById("emptyBtn").onclick = () => switchTab("catalog");
    return;
  }
  $view.innerHTML = `${title("Заказы")}<div class="group">${orders.map((o) => orderRow(o)).join("")}</div>`;
  $view.querySelectorAll("[data-id]").forEach((b) => (b.onclick = () => go("order", { id: +b.dataset.id })));
};

function itemsGroup(o) {
  return `${header("Состав")}<div class="group">
    ${o.items.map((i) => kv(`${i.title} · ${i.size} × ${i.qty}`, money(i.price * i.qty))).join("")}
    <div class="cell total"><span class="title">Итого</span><span class="value" style="flex:1">${money(o.total)}</span></div>
  </div>`;
}

function deliveryGroup(o) {
  return `${header("Доставка")}<div class="group">
    ${kv("Получатель", esc(o.customer_name))}
    ${kv("Телефон", esc(o.phone))}
    ${kv("Способ", esc(o.delivery))}
    ${o.address ? kv("Адрес", esc(o.address)) : ""}
    ${o.comment ? kv("Комментарий", esc(o.comment)) : ""}
    ${o.track ? kv("Трек-номер", `<b>${esc(o.track)}</b>`) : ""}
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

  $view.innerHTML = `
    ${title(fresh ? "Заказ оформлен" : `Заказ #${o.id}`)}
    <div class="sub" style="color:var(--label-2);margin:-6px 0 14px;font-size:15px">№${o.id} · ${fmtDate(o.created_at)}</div>
    ${statusCard(o.status)}
    ${
      needPay
        ? `${header("Оплата переводом")}
      <div class="group">
        <div class="cell"><div class="grow"><div class="sub" style="margin:0 0 4px">Реквизиты</div><div class="mono">${esc(state.settings.payment_details)}</div></div><button class="icon-btn" id="copyDetails" aria-label="Скопировать">${icon("copy")}</button></div>
        <div class="cell"><div class="grow"><div class="sub" style="margin:0 0 2px">Сумма</div><div class="title"><b>${money(o.total)}</b></div></div><button class="icon-btn" id="copySum" aria-label="Скопировать">${icon("copy")}</button></div>
        <div class="cell"><div class="grow"><div class="sub" style="margin:0 0 2px">Комментарий к переводу</div><div class="title">Заказ #${o.id}</div></div><button class="icon-btn" id="copyNote" aria-label="Скопировать">${icon("copy")}</button></div>
      </div>
      ${footer("После перевода загрузи скриншот или PDF чека — или просто отправь его боту в чат.")}`
        : ""
    }
    ${itemsGroup(o)}
    ${deliveryGroup(o)}
    <div class="stack">
      ${o.status === "checking" ? `<button class="btn gray" id="reupload">${icon("doc")} Отправить другой чек</button>` : ""}
      ${supportUrl() ? `<button class="btn gray" id="support">${icon("bubble")} Написать в поддержку</button>` : ""}
      ${needPay ? `<button class="btn red" id="cancel">Отменить заказ</button>` : ""}
    </div>`;

  const reload = () => screens.order({ id });
  if (needPay) {
    document.getElementById("copyDetails").onclick = () => copy(state.settings.payment_details);
    document.getElementById("copySum").onclick = () => copy(String(o.total));
    document.getElementById("copyNote").onclick = () => copy(`Заказ #${o.id}`);
    setBar(`<button class="btn" id="upload">${icon("doc")} Загрузить чек</button>`).querySelector("#upload").onclick = () => uploadReceipt(o.id, reload);
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

// ---------- управление (админка) ----------

const ADMIN_TABS = [
  ["orders", "Заказы"],
  ["products", "Товары"],
  ["stock", "Склад"],
  ["settings", "Настройки"],
];

function adminHeader() {
  return `${title("Управление")}
    <div class="segmented">${ADMIN_TABS.map(([id, l]) => `<button class="${state.adminTab === id ? "active" : ""}" data-atab="${id}">${l}</button>`).join("")}</div>`;
}

function bindAdminTabs() {
  $view.querySelectorAll("[data-atab]").forEach((b) => (b.onclick = () => ((state.adminTab = b.dataset.atab), haptic("select"), render())));
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
  const c = (k) => stats.by_status[k] || 0;
  const filters = [["", "Все"], ["checking", "Проверка"], ["awaiting_payment", "Ждут оплату"], ["paid", "Отправить"], ["shipped", "В пути"], ["done", "Получены"], ["cancelled", "Отменены"]];
  $view.innerHTML = `${adminHeader()}
    <div class="tiles">
      <button class="tile" data-st="checking"><div class="t-ico c-blue">${icon("clock")}</div><b>${c("checking")}</b><span>Проверить оплату</span></button>
      <button class="tile" data-st="paid"><div class="t-ico c-green">${icon("truck")}</div><b>${c("paid")}</b><span>Нужно отправить</span></button>
      <button class="tile" data-st="awaiting_payment"><div class="t-ico c-orange">${icon("card")}</div><b>${c("awaiting_payment")}</b><span>Ждут оплату</span></button>
      <div class="tile"><div class="t-ico c-purple">${icon("chart")}</div><b style="font-size:20px">${money(stats.revenue)}</b><span>Выручка · ${stats.users} ${plural(stats.users, "покупатель", "покупателя", "покупателей")}</span></div>
    </div>
    <div class="pills" style="margin-top:14px">${filters
      .map(([s, l]) => `<button class="pill ${state.adminStatus === s ? "active" : ""}" data-st="${s}">${l}${s && c(s) ? `<span class="count">${c(s)}</span>` : ""}</button>`)
      .join("")}</div>
    ${orders.length ? `<div class="group">${orders.map((o) => orderRow(o, true)).join("")}</div>` : emptyHtml("box", "Заказов нет", "")}`;
  $view.querySelectorAll("[data-st]").forEach((b) => (b.onclick = () => ((state.adminStatus = b.dataset.st), haptic("select"), render())));
  $view.querySelectorAll("[data-id]").forEach((b) => (b.onclick = () => go("adminOrder", { id: +b.dataset.id })));
};

screens.adminOrder = async ({ id }) => {
  $view.innerHTML = loaderHtml();
  const o = await api(`/api/admin/orders/${id}`);
  const tgLink = o.username ? `https://t.me/${o.username}` : null;
  const actions = {
    awaiting_payment: [["paid", "Оплата пришла", "green"], ["cancelled", "Отменить заказ", "red"]],
    checking: [["paid", "Деньги пришли", "green"], ["awaiting_payment", "Деньги не пришли", "gray"], ["cancelled", "Отменить заказ", "red"]],
    paid: [["shipped", "Отправлен", ""], ["done", "Получен", "gray"], ["cancelled", "Отменить заказ", "red"]],
    shipped: [["done", "Получен", ""], ["shipped", "Обновить трек", "gray"], ["cancelled", "Отменить заказ", "red"]],
  }[o.status] || [];

  $view.innerHTML = `
    ${title(`Заказ #${o.id}`)}
    <div style="margin:-6px 0 14px;display:flex;gap:8px;align-items:center">${statusPill(o.status)}<span style="color:var(--label-2);font-size:15px">${fmtDate(o.created_at)}</span></div>
    ${header("Покупатель")}
    <div class="group">
      ${kv("Имя", esc(o.customer_name))}
      ${kv("Telegram", o.username ? `@${esc(o.username)}` : `id ${o.user_id}`)}
      ${tgLink ? `<button class="cell tap" id="writeUser"><span class="grow link">Написать в Telegram</span>${icon("chevronRight", "chev")}</button>` : ""}
    </div>
    ${itemsGroup(o)}
    ${deliveryGroup(o)}
    ${header("Чек")}
    <div class="group">${
      o.receipt_file_id
        ? o.receipt_kind === "photo"
          ? `<div style="padding-top:14px"><div class="receipt"><img src="${photoUrl(o.receipt_file_id)}" alt="Чек"></div></div>`
          : `<button class="cell tap" id="openReceipt">${icon("doc")}<span class="grow">Открыть файл чека</span>${icon("chevronRight", "chev")}</button>`
        : `<div class="cell"><span class="sub" style="margin:0">Покупатель ещё не прислал чек</span></div>`
    }</div>
    ${
      ["paid", "shipped"].includes(o.status)
        ? `${header("Трек-номер")}<div class="group"><div class="cell"><input class="input" id="track" value="${esc(o.track || "")}" placeholder="Номер отправления"></div></div>`
        : ""
    }
    <div class="stack">${actions.map(([s, l, cls]) => `<button class="btn ${cls}" data-to="${s}">${l}</button>`).join("")}</div>`;

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
  state.adminProducts = products;
  $view.innerHTML = `${adminHeader()}
    <button class="btn" id="addProduct" style="margin:10px 0 18px">${icon("plus")} Новый товар</button>
    ${
      products.length
        ? `<div class="group">${products
            .map(
              (p) => `
      <button class="cell tap has-thumb" data-id="${p.id}">
        <div class="thumb">${photoHtml(p.photos[0])}</div>
        <div class="grow">
          <div class="title">${esc(p.title)}</div>
          <div class="sub">${esc(p.category || "Без категории")} · ${money(p.price)}${p.is_active ? "" : " · скрыт"}</div>
          <div class="size-chips">${p.sizes.map((s) => `<span class="${s.stock ? "" : "zero"}">${esc(s.size)} ${s.stock}</span>`).join("")}</div>
        </div>${icon("chevronRight", "chev")}
      </button>`
            )
            .join("")}</div>`
        : emptyHtml("hanger", "Товаров пока нет", "Добавь первый — он сразу появится в каталоге.")
    }`;
  document.getElementById("addProduct").onclick = () => go("productForm", {});
  $view.querySelectorAll("[data-id]").forEach((b) => (b.onclick = () => go("productForm", { id: +b.dataset.id })));
};

screens.productForm = async ({ id }) => {
  const existing = state.adminProducts.find((p) => p.id === id);
  const p = existing
    ? JSON.parse(JSON.stringify(existing))
    : { title: "", category: "", price: "", description: "", sizes: [{ size: "S", stock: 0 }, { size: "M", stock: 0 }, { size: "L", stock: 0 }, { size: "XL", stock: 0 }], photos: [], is_active: true, sort: 0 };
  const categories = [...new Set(state.adminProducts.map((x) => x.category).filter(Boolean))];

  const draw = () => {
    $view.innerHTML = `
      ${title(existing ? "Товар" : "Новый товар")}
      ${header("Фото · первое — обложка")}
      <div class="group"><div class="photos">
        ${p.photos.map((ph, i) => `<div><img src="${photoUrl(ph)}" alt=""><button class="rm" data-rmph="${i}" aria-label="Убрать">${icon("xmark")}</button></div>`).join("")}
        ${p.photos.length < 10 ? `<button class="add" id="addPhoto" aria-label="Добавить фото">${icon("photo")}</button>` : ""}
      </div></div>
      ${header("Основное")}
      <div class="group">
        <div class="cell field"><label>Название</label><input class="input" id="f_title" value="${esc(p.title)}" placeholder="Худи DAYZ Black"></div>
        <div class="cell field"><label>Категория</label><input class="input" id="f_category" list="cats" value="${esc(p.category)}" placeholder="Худи, футболки…"><datalist id="cats">${categories.map((c) => `<option value="${esc(c)}">`).join("")}</datalist></div>
        <div class="cell field"><label>Цена, ${esc(state.settings.currency)}</label><input class="input" id="f_price" type="number" inputmode="numeric" min="0" value="${esc(p.price)}" placeholder="0"></div>
        <div class="cell field"><label>Описание</label><textarea class="input" id="f_description" placeholder="Материал, посадка, уход">${esc(p.description)}</textarea></div>
      </div>
      ${header("Размеры и остатки")}
      <div class="group">
        ${p.sizes
          .map(
            (s, i) => `<div class="cell">
          <input class="input" data-sz="${i}" value="${esc(s.size)}" placeholder="Размер" style="flex:1">
          <input class="input num" data-st="${i}" type="number" inputmode="numeric" min="0" value="${s.stock}">
          <span style="color:var(--label-2);font-size:15px">шт</span>
          <button class="icon-btn" data-rmsz="${i}" aria-label="Удалить размер">${icon("xmark")}</button></div>`
          )
          .join("")}
        <button class="cell tap" id="addSize"><span class="link">Добавить размер</span></button>
        <button class="cell tap" id="oneSize"><span class="link">Сделать One size</span></button>
      </div>
      ${footer(existing ? "Поступление товара лучше оформлять во вкладке «Склад» → «Оприходовать»: там сохраняется цена закупки и история. Правка здесь запишется как корректировка." : "Начальные остатки запишутся в журнал склада как приход.")}
      ${header("Публикация")}
      <div class="group">
        <label class="cell"><span class="grow title">Показывать в каталоге</span><input type="checkbox" class="switch" id="f_active" ${p.is_active ? "checked" : ""}></label>
        <div class="cell"><span class="grow title">Порядок</span><input class="input num" id="f_sort" type="number" value="${esc(p.sort)}"></div>
      </div>
      ${footer("Чем меньше порядок, тем выше товар в каталоге.")}
      ${existing ? `<div class="stack"><button class="btn red" id="delete">Удалить товар</button></div>` : ""}`;

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
    document.getElementById("oneSize").onclick = () => (sync(), (p.sizes = [{ size: "One size", stock: p.sizes.reduce((s, x) => s + x.stock, 0) }]), draw());
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

// ---------- склад ----------

const KIND_ICON = { receipt: ["arrowDown", "c-green"], sale: ["bag", "c-blue"], return: ["arrowBack", "c-orange"], adjust: ["pencil", "c-gray"] };

function movementRow(m) {
  const [ico, color] = KIND_ICON[m.kind] || KIND_ICON.adjust;
  const sign = m.delta > 0 ? `+${m.delta}` : `${m.delta}`;
  const extra = [m.note, m.cost != null ? `${money(m.cost)}/шт` : ""].filter(Boolean).join(" · ");
  return `<div class="cell">
    <div class="lead-ico ${color}">${icon(ico)}</div>
    <div class="grow"><div class="title" style="font-size:15px">${esc(m.product_title)} · ${esc(m.size)}</div>
    <div class="sub" style="font-size:13px">${esc(m.kind_label)} · ${fmtDate(m.created_at)}${extra ? ` · ${esc(extra)}` : ""}</div></div>
    <span class="delta ${m.delta > 0 ? "plus" : "minus"}">${sign}</span>
  </div>`;
}

adminTabs.stock = async () => {
  const data = await api("/api/admin/stock");
  state.adminProducts = data.products;
  $view.innerHTML = `${adminHeader()}
    <div class="tiles">
      <div class="tile"><div class="t-ico c-green">${icon("box")}</div><b>${data.units}</b><span>${plural(data.units, "единица", "единицы", "единиц")} на складе</span></div>
      <div class="tile"><div class="t-ico c-orange">${icon("rub")}</div><b style="font-size:20px">${money(data.received_value)}</b><span>Вложено в закупку</span></div>
    </div>
    <button class="btn" id="receipt" style="margin:16px 0 0">${icon("tray")} Оприходовать товар</button>
    ${footer("Пришла партия — нажми, выбери товар и укажи количество по размерам. Остатки обновятся, приход сохранится в журнале.")}
    ${header("Остатки")}
    ${
      data.products.length
        ? `<div class="group">${data.products
            .map(
              (p) => `<button class="cell tap has-thumb" data-id="${p.id}">
          <div class="thumb">${photoHtml(p.photos[0])}</div>
          <div class="grow"><div class="title">${esc(p.title)}</div>
          <div class="size-chips">${p.sizes.map((s) => `<span class="${s.stock ? "" : "zero"}">${esc(s.size)} ${s.stock}</span>`).join("")}</div></div>
          <span class="value">${stockOf(p)} шт</span>${icon("chevronRight", "chev")}
        </button>`
            )
            .join("")}</div>`
        : `<div class="group"><div class="cell"><span class="sub" style="margin:0">Сначала добавь товар во вкладке «Товары»</span></div></div>`
    }
    ${header("Журнал движений")}
    ${data.movements.length ? `<div class="group">${data.movements.slice(0, 40).map(movementRow).join("")}</div>` : `<div class="group"><div class="cell"><span class="sub" style="margin:0">Пока пусто</span></div></div>`}`;
  document.getElementById("receipt").onclick = () => (data.products.length ? go("receiptPick") : toast("Сначала добавь товар", true));
  $view.querySelectorAll("[data-id]").forEach((b) => (b.onclick = () => go("receipt", { id: +b.dataset.id })));
};

screens.receiptPick = async () => {
  $view.innerHTML = `${title("Приход")}${header("Выбери товар")}<div class="group">${state.adminProducts
    .map(
      (p) => `<button class="cell tap has-thumb" data-id="${p.id}">
      <div class="thumb">${photoHtml(p.photos[0])}</div>
      <div class="grow"><div class="title">${esc(p.title)}</div><div class="sub">Сейчас ${stockOf(p)} шт</div></div>${icon("chevronRight", "chev")}
    </button>`
    )
    .join("")}</div>`;
  $view.querySelectorAll("[data-id]").forEach((b) => (b.onclick = () => go("receipt", { id: +b.dataset.id })));
};

screens.receipt = async ({ id }) => {
  const p = state.adminProducts.find((x) => x.id === id);
  if (!p) throw new Error("Товар не найден");
  const rows = p.sizes.map((s) => ({ size: s.size, current: s.stock, qty: "" }));

  const draw = () => {
    $view.innerHTML = `
      ${title("Приход")}
      <div class="group"><div class="cell has-thumb"><div class="thumb">${photoHtml(p.photos[0])}</div><div class="grow"><div class="title">${esc(p.title)}</div><div class="sub">Сейчас на складе ${stockOf(p)} шт</div></div></div></div>
      ${header("Сколько пришло")}
      <div class="group">
        ${rows
          .map(
            (r, i) => `<div class="cell">
          ${r.current == null ? `<input class="input" data-size="${i}" value="${esc(r.size)}" placeholder="Новый размер" style="flex:1">` : `<span class="grow title">${esc(r.size)} <span style="color:var(--label-2);font-size:15px">· есть ${r.current}</span></span>`}
          <span style="color:var(--green);font-weight:600">+</span>
          <input class="input num" data-qty="${i}" type="number" inputmode="numeric" min="0" placeholder="0" value="${esc(r.qty)}">
          <span style="color:var(--label-2);font-size:15px">шт</span>
        </div>`
          )
          .join("")}
        <button class="cell tap" id="newSize"><span class="link">Новый размер</span></button>
      </div>
      ${header("Закупка")}
      <div class="group">
        <div class="cell"><span class="grow title">Цена за 1 шт</span><input class="input num" id="cost" type="number" inputmode="numeric" min="0" placeholder="0" style="width:110px"><span style="color:var(--label-2)">${esc(state.settings.currency)}</span></div>
        <div class="cell"><input class="input" id="note" placeholder="Поставщик или комментарий"></div>
      </div>
      ${footer("Цена закупки необязательна — она нужна, чтобы видеть, сколько вложено в товар.")}
      <div class="group" style="margin-top:20px"><div class="cell total"><span class="title">Итого</span><span class="value" id="sum" style="flex:1"></span></div></div>`;

    const sync = () =>
      rows.forEach((r, i) => {
        r.qty = $view.querySelector(`[data-qty="${i}"]`).value;
        const sizeInput = $view.querySelector(`[data-size="${i}"]`);
        if (sizeInput) r.size = sizeInput.value.trim();
      });
    const updateSum = () => {
      sync();
      const units = rows.reduce((s, r) => s + (+r.qty || 0), 0);
      const cost = +document.getElementById("cost").value || 0;
      document.getElementById("sum").textContent = `${units} шт${cost ? ` · ${money(units * cost)}` : ""}`;
    };
    $view.querySelectorAll("[data-qty], #cost").forEach((el) => (el.oninput = updateSum));
    document.getElementById("newSize").onclick = () => (sync(), rows.push({ size: "", current: null, qty: "" }), draw());
    updateSum();

    setBar(`<button class="btn" id="save">${icon("tray")} Оприходовать</button>`).querySelector("#save").onclick = async () => {
      sync();
      const items = rows.filter((r) => r.size && +r.qty > 0).map((r) => ({ size: r.size, qty: +r.qty }));
      if (!items.length) return toast("Укажи количество хотя бы по одному размеру", true);
      try {
        await api("/api/admin/stock/receipt", {
          method: "POST",
          body: { product_id: p.id, items, cost: document.getElementById("cost").value, note: document.getElementById("note").value || "Приход товара" },
        });
        state.products = [];
        toast(`Оприходовано ${items.reduce((s, i) => s + i.qty, 0)} шт`);
        state.adminTab = "stock";
        state.stack = [{ name: "admin" }];
        render();
      } catch (err) {
        toast(err.message, true);
      }
    };
  };
  draw();
};

// ---------- настройки ----------

adminTabs.settings = async () => {
  const s = await api("/api/admin/settings");
  $view.innerHTML = `${adminHeader()}
    ${header("Оплата")}
    <div class="group"><div class="cell field"><label>Реквизиты для перевода</label><textarea class="input" id="s_payment_details" rows="4" placeholder="Карта 0000 0000 0000 0000&#10;Банк, получатель">${esc(s.payment_details)}</textarea></div></div>
    ${footer("Покупатель увидит их после оформления заказа — в мини-аппе и в сообщении от бота.")}
    ${header("Магазин")}
    <div class="group">
      <div class="cell"><span class="grow title">Валюта</span><input class="input num" id="s_currency" value="${esc(s.currency)}"></div>
      <div class="cell field"><label>Способы доставки — каждый с новой строки</label><textarea class="input" id="s_delivery_options">${esc(s.delivery_options)}</textarea></div>
      <div class="cell field"><label>О магазине</label><textarea class="input" id="s_about">${esc(s.about)}</textarea></div>
    </div>`;
  setBar(`<button class="btn" id="save">Сохранить</button>`).querySelector("#save").onclick = async () => {
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

// ---------- старт ----------

async function boot() {
  if (tg) {
    tg.ready();
    tg.expand();
    try {
      tg.setHeaderColor("#000000");
      tg.setBackgroundColor("#000000");
      if (tg.setBottomBarColor) tg.setBottomBarColor("#000000");
    } catch (_) {}
    if (can("6.1")) tg.BackButton.onClick(back);
  }
  $view.innerHTML = loaderHtml("Загружаем DAYZ DROP");

  if (!tg || !tg.initData) {
    $view.innerHTML = `<div class="hero"><img src="assets/logo-banner.jpg" alt="DAYZ DROP"></div>${emptyHtml("bag", "Открой магазин в Telegram", "Мини-приложение работает внутри бота DAYZ DROP.")}`;
    return;
  }

  try {
    const data = await api("/api/bootstrap");
    state.me = data.user;
    state.isAdmin = data.is_admin;
    state.botUsername = data.bot_username;
    state.settings = data.settings;
  } catch (err) {
    $view.innerHTML = emptyHtml("warning", "Не удалось загрузить магазин", err.message, "Повторить");
    document.getElementById("emptyBtn").onclick = () => location.reload();
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

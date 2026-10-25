"use strict";
/* DAYZ DROP — мини-апп: ядро, навигация и экраны покупателя. Экраны админки — в admin.js. */

const tg = window.Telegram && window.Telegram.WebApp;
const qs = new URLSearchParams(location.search);
const API = (qs.get("api") || window.DAYZ_CONFIG.API_URL).replace(/\/+$/, "");

const $view = document.getElementById("view");
const $nav = document.getElementById("nav");
const $toast = document.getElementById("toast");

const STATUS = {
  awaiting_payment: "Ожидает оплаты",
  checking: "Проверяем оплату",
  confirmed: "Оплата при получении",
  paid: "Оплачен",
  shipped: "В пути",
  done: "Получен",
  cancelled: "Отменён",
};

const ROOTS = { catalog: "catalog", cart: "cart", orders: "orders", profile: "profile", admin: "admin" };

const state = {
  me: { registered: false, points: 0 },
  isAdmin: false,
  botUsername: null,
  settings: { currency: "сум", delivery_methods: [], card_payments: false, loyalty_enabled: true, earn_percent: 5, welcome_points: 0 },
  products: [],
  cart: loadJSON("dayz_cart", []),
  favorites: new Set(),
  subs: new Set(),
  tab: "catalog",
  stacks: Object.fromEntries(Object.keys(ROOTS).map((k) => [k, [{ name: ROOTS[k] }]])),
  category: "Все",
  sort: "new",
  checkout: { delivery: null, payment: null, coupon: "" },
};

// ---------- иконки (линейные, в духе SF Symbols) ----------

const ICON_PATHS = {
  bag: '<path d="M5.5 8h13l-1 12.5h-11z"/><path d="M9 8V6.5a3 3 0 0 1 6 0V8"/>',
  cart: '<path d="M3 4h2.2l2.3 10.5h10.3L20 7.2H6.2"/><circle cx="9" cy="19" r="1.4"/><circle cx="17" cy="19" r="1.4"/>',
  box: '<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
  user: '<circle cx="12" cy="8" r="3.8"/><path d="M4.5 20c.8-3.6 3.8-5.5 7.5-5.5s6.7 1.9 7.5 5.5"/>',
  users: '<circle cx="9" cy="8" r="3.2"/><path d="M3 19c.6-3 3-4.6 6-4.6s5.4 1.6 6 4.6"/><path d="M15.5 4.9a3.2 3.2 0 0 1 0 6.2M17.5 14.6c2 .5 3.2 2 3.5 4.4"/>',
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
  cash: '<rect x="2.5" y="6" width="19" height="12" rx="2"/><circle cx="12" cy="12" r="2.6"/><path d="M6 9.5v5M18 9.5v5"/>',
  checkCircle: '<circle cx="12" cy="12" r="8.5"/><path d="m8.5 12.3 2.4 2.4 4.6-5"/>',
  xCircle: '<circle cx="12" cy="12" r="8.5"/><path d="m9 9 6 6M15 9l-6 6"/>',
  warning: '<path d="M12 4 2.8 19.5h18.4z"/><path d="M12 10v4.5M12 17.3v.2"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  arrowDown: '<path d="M12 5v14M6 13l6 6 6-6"/>',
  arrowBack: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
  pencil: '<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
  wallet: '<path d="M4 7.5A2.5 2.5 0 0 1 6.5 5H18v4"/><rect x="3.5" y="8" width="17" height="11" rx="2.5"/><circle cx="16" cy="13.5" r="1.3"/>',
  gift: '<rect x="3.5" y="9" width="17" height="11" rx="2"/><path d="M3 9h18v-2H3zM12 7v13"/><path d="M12 7c-1.5-3-5-3-5-1s3 1 5 1zM12 7c1.5-3 5-3 5-1s-3 1-5 1z"/>',
  ticket: '<path d="M3.5 8.5V6h17v2.5a2.5 2.5 0 0 0 0 5V16h-17v-2.5a2.5 2.5 0 0 0 0-5z"/><path d="M14 6v10" stroke-dasharray="2 2"/>',
  megaphone: '<path d="M4 10v4h3l7 4V6l-7 4z"/><path d="M17.5 9a4 4 0 0 1 0 6M7 14l1 5h2"/>',
  download: '<path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19.5h14"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 2.8v2.4M12 18.8v2.4M4.2 7.5l2 1.2M17.8 15.3l2 1.2M4.2 16.5l2-1.2M17.8 8.7l2-1.2"/><circle cx="12" cy="12" r="7"/>',
  bell: '<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 1.5h-15z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
  star: '<path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/>',
  sparkle: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
  tag: '<path d="M3.5 12.5V4h8.5l8.5 8.5-8.5 8.5z"/><circle cx="8" cy="8.5" r="1.4"/>',
  rub: '<path d="M8 20V4h5.5a4 4 0 0 1 0 8H6M6 16h8"/>',
};
const HEART_SVG = '<svg viewBox="0 0 24 24"><path d="M12 20.5s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.6a4.3 4.3 0 0 1 7.5 2.7c0 5.6-7.5 10.2-7.5 10.2z"/></svg>';
const STAR_SVG = '<svg viewBox="0 0 24 24"><path d="m12 2.8 2.8 5.7 6.3.9-4.6 4.4 1.1 6.2L12 17l-5.6 3 1.1-6.2L2.9 9.4l6.3-.9z"/></svg>';
const icon = (name, cls = "") => `<svg class="ico ${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICON_PATHS[name] || ""}</svg>`;

// ---------- утилиты ----------

const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const num = (n) => Number(n || 0).toLocaleString("ru-RU");
const money = (n) => `${num(n)} ${state.settings.currency}`;
const photoUrl = (id) => `${API}/api/photo/${encodeURIComponent(id)}`;
const stockOf = (p) => p.sizes.reduce((s, x) => s + x.stock, 0);
const can = (v) => tg && tg.isVersionAtLeast && tg.isVersionAtLeast(v);
const fmtDate = (iso) => (iso ? new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "");
const plural = (n, one, few, many) => {
  const m10 = n % 10, m100 = n % 100;
  return m10 === 1 && m100 !== 11 ? one : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? few : many;
};
const debounce = (fn, ms) => {
  let t;
  return (...a) => (clearTimeout(t), (t = setTimeout(() => fn(...a), ms)));
};

function loadJSON(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) || fallback;
  } catch (_) {
    return fallback;
  }
}
function saveJSON(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (_) {}
}

function haptic(type) {
  try {
    if (!can("6.1")) return;
    if (type === "ok" || type === "error") tg.HapticFeedback.notificationOccurred(type === "ok" ? "success" : "error");
    else if (type === "select") tg.HapticFeedback.selectionChanged();
    else tg.HapticFeedback.impactOccurred(type || "light");
  } catch (_) {}
}

let toastTimer;
function toast(text, isError) {
  $toast.innerHTML = `${icon(isError ? "xCircle" : "checkCircle")}<span>${esc(text)}</span>`;
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

function saveCart() {
  saveJSON("dayz_cart", state.cart);
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

function copy(text, label = "Скопировано") {
  (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject())
    .then(() => toast(label))
    .catch(() => toast("Не удалось скопировать", true));
}

function openLink(url) {
  if (url.startsWith("https://t.me/") && tg && tg.openTelegramLink) tg.openTelegramLink(url);
  else if (tg && tg.openLink) tg.openLink(url);
  else window.open(url, "_blank");
}

// Поддержка — чат с админами через бота (бот пересылает сообщение обоим админам)
function openSupport() {
  if (!state.botUsername) return;
  openLink(`https://t.me/${state.botUsername}?start=support`);
  if (tg && tg.close) setTimeout(() => tg.close(), 300);
}

// ---------- кусочки разметки ----------

const loaderHtml = (text = "Загрузка") => `<div class="loader"><div class="spin"></div><div class="slow">${text}</div></div>`;
const photoHtml = (id) => (id ? `<img src="${photoUrl(id)}" loading="lazy" alt="">` : `<div class="placeholder"><img src="assets/logo.jpg" alt=""></div>`);
const statusPill = (s) => `<span class="status st-${s}">${STATUS[s] || s}</span>`;
const title = (text) => FX.maskedHeading(text);
const header = (text, right = "") => `<div class="section-header${right ? " row" : ""}"><span>${esc(text)}</span>${right}</div>`;
const footer = (text) => `<div class="section-footer">${text}</div>`;
const kv = (k, v, cls = "") => `<div class="cell kv ${cls}"><span class="title">${esc(k)}</span><span class="value">${v}</span></div>`;
const chev = () => icon("chevronRight", "chev");

function emptyHtml(ico, head, text, button) {
  return `<div class="empty"><div class="e-ico">${icon(ico, "lg")}</div><b>${esc(head)}</b>${text ? `<p>${esc(text)}</p>` : ""}${
    button ? `<button class="btn sm" id="emptyBtn">${esc(button)}</button>` : ""
  }</div>`;
}

function rseg(options, active, id) {
  return `<div class="rseg" id="${id}"><span class="rseg-thumb"></span>${options
    .map(([v, l]) => `<button type="button" data-v="${esc(v)}" class="${String(v) === String(active) ? "active" : ""}">${esc(l)}</button>`)
    .join("")}</div>`;
}

function heartBtn(p, big) {
  return `<button class="heart ${big ? "big" : ""}" data-heart="${p.id}" aria-label="В избранное">${HEART_SVG}${big ? '<span class="heart-count"></span>' : ""}</button>`;
}

function bindHearts(root = $view) {
  root.querySelectorAll("[data-heart]").forEach((btn) => {
    const id = +btn.dataset.heart;
    const product = state.products.find((p) => p.id === id);
    FX.pulseHeart(btn, {
      liked: state.favorites.has(id),
      count: product ? product.likes : 0,
      onToggle: async () => {
        haptic("medium");
        const res = await api(`/api/favorites/${id}`, { method: "POST" });
        res.favorite ? state.favorites.add(id) : state.favorites.delete(id);
        if (product) product.likes = res.likes;
        return res;
      },
    });
  });
}

function badgeTag(p) {
  if (p.badge === "soon") return '<span class="tag soon">Скоро</span>';
  if (p.old_price) return `<span class="tag sale">−${Math.round((1 - p.price / p.old_price) * 100)}%</span>`;
  if (p.badge === "new") return '<span class="tag new">New</span>';
  if (p.badge === "hit") return '<span class="tag hit">Хит</span>';
  if (!stockOf(p)) return '<span class="tag">Нет в наличии</span>';
  return "";
}

const priceHtml = (p) => `<span>${money(p.price)}</span>${p.old_price ? `<span class="old">${money(p.old_price)}</span>` : ""}`;

const STATUS_INFO = {
  awaiting_payment: ["card", "c-orange", "Ждём оплату", "Переведи сумму на карту ниже и загрузи чек."],
  checking: ["clock", "c-blue", "Проверяем оплату", "Чек получен. Как только подтвердим поступление — бот пришлёт сообщение."],
  confirmed: ["cash", "c-yellow", "Заказ подтверждён", "Оплатишь наличными при получении. Мы свяжемся, чтобы договориться о времени."],
  paid: ["checkCircle", "c-green", "Оплата подтверждена", "Собираем заказ и скоро отправим. Трек-номер придёт в бота."],
  shipped: ["truck", "c-purple", "Заказ в пути", "Скоро будет у тебя."],
  done: ["box", "c-gray", "Заказ получен", "Спасибо, что выбрал DAYZ DROP."],
  cancelled: ["xCircle", "c-red", "Заказ отменён", "Если это ошибка — напиши в поддержку."],
};

function statusCard(status) {
  const [ico, color, head, text] = STATUS_INFO[status] || STATUS_INFO.awaiting_payment;
  return `<div class="status-card"><div class="t-ico ${color}">${icon(ico)}</div><div><b>${head}</b><p>${text}</p></div></div>`;
}

// ---------- навигация: у каждой вкладки свой стек экранов ----------

const screens = {};
const TITLES = {
  product: "Товар", checkout: "Оформление", order: "Заказ", favorites: "Избранное", pointsHistory: "История баллов",
};

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

const stack = () => state.stacks[state.tab];
const currentScreen = () => stack()[stack().length - 1];

async function render() {
  const screen = currentScreen();
  const nested = stack().length > 1;
  setBar(null);
  window.scrollTo(0, 0);
  if (can("6.1")) nested ? tg.BackButton.show() : tg.BackButton.hide();
  try {
    await screens[screen.name](screen.params || {});
  } catch (err) {
    $view.innerHTML = emptyHtml("warning", "Что-то пошло не так", err.message, "Повторить");
    document.getElementById("emptyBtn").onclick = render;
  }
  if (nested && currentScreen() === screen) {
    const name = (screen.params && screen.params.title) || TITLES[screen.name] || "";
    $view.insertAdjacentHTML("afterbegin", `<div class="topbar"><button class="back-btn" id="backBtn">${icon("chevronLeft")}Назад</button><div class="tb-title">${esc(name)}</div></div>`);
    document.getElementById("backBtn").onclick = back;
  }
  bindHearts();
}

function go(name, params) {
  haptic();
  stack().push({ name, params });
  render();
}

function back() {
  haptic();
  if (stack().length > 1) stack().pop();
  render();
}

function switchTab(tab) {
  haptic("select");
  if (state.tab === tab) state.stacks[tab] = [state.stacks[tab][0]]; // повторное нажатие — в корень вкладки
  state.tab = tab;
  renderNav();
  render();
}

function renderNav() {
  const tabs = [["catalog", "Каталог", "bag"], ["cart", "Корзина", "cart"], ["orders", "Заказы", "box"], ["profile", "Профиль", "user"]];
  if (state.isAdmin) tabs.push(["admin", "Админ", "sliders"]);
  const count = cartCount();
  $nav.innerHTML =
    '<span class="pill-ind"></span>' +
    tabs.map(([id, label, ico]) => `<button data-tab="${id}" class="${state.tab === id ? "active" : ""}">${icon(ico)}${label}${id === "cart" && count ? `<span class="badge">${count}</span>` : ""}</button>`).join("");
  $nav.querySelectorAll("button").forEach((b) => (b.onclick = () => switchTab(b.dataset.tab)));
  requestAnimationFrame(() => FX.pillNav($nav));
}

// ---------- каталог ----------

async function loadProducts(force) {
  if (force || !state.products.length) state.products = await api("/api/products");
}

screens.catalog = async () => {
  if (!state.products.length) {
    $view.innerHTML = loaderHtml("Загружаем DAYZ DROP");
    await loadProducts();
  }
  const cats = ["Все", ...new Set(state.products.map((p) => p.category).filter(Boolean))];
  if (!cats.includes(state.category)) state.category = "Все";
  let list = state.products.filter((p) => state.category === "Все" || p.category === state.category);
  if (state.sort === "cheap") list = [...list].sort((a, b) => a.price - b.price);
  if (state.sort === "expensive") list = [...list].sort((a, b) => b.price - a.price);
  const fresh = state.products.filter((p) => p.badge === "new" || p.badge === "hit").concat(state.products.filter((p) => !p.badge)).filter((p) => p.photos.length).slice(0, 7);
  const words = cats.length > 1 ? cats.slice(1).map((c) => c.toLowerCase()) : ["худи", "футболки", "карго", "дропы"];

  $view.innerHTML = `
    <section class="hero">${FX.lightPillar()}
      <img class="logo" src="assets/logo-banner.jpg" alt="DAYZ DROP">
      <div class="tagline">Новый дроп <span class="rt" id="rt"></span></div>
    </section>
    ${fresh.length >= 2 ? `${header("Новинки")}<div class="dc" id="dc">${fresh.map((p) => `
      <div class="dc-card" data-id="${p.id}">${photoHtml(p.photos[0])}${badgeTag(p)}
        <div class="dc-info"><b>${esc(p.title)}</b><span>${money(p.price)}</span></div></div>`).join("")}</div><div class="dc-dots" id="dcDots"></div>` : ""}
    ${title("Каталог")}
    ${cats.length > 2 ? `<div class="pills">${cats.map((c) => `<button class="pill ${c === state.category ? "active" : ""}" data-cat="${esc(c)}">${esc(c)}</button>`).join("")}</div>` : ""}
    ${list.length > 1 ? rseg([["new", "Новые"], ["cheap", "Дешевле"], ["expensive", "Дороже"]], state.sort, "sort") : ""}
    ${list.length
      ? `<div class="grid" style="margin-top:12px">${list.map((p) => `
        <div class="card" data-id="${p.id}">
          <div class="card-img spot">${photoHtml(p.photos[0])}${badgeTag(p)}${heartBtn(p)}</div>
          <div class="card-title">${esc(p.title)}</div>
          <div class="card-price">${priceHtml(p)}</div>
          ${p.rating ? `<div class="rating-mini">★ ${p.rating} <span style="color:var(--label-3)">(${p.rating_count})</span></div>` : ""}
        </div>`).join("")}</div>`
      : emptyHtml("hanger", "Скоро здесь появятся вещи", "Загляни чуть позже — готовим новый дроп.")}`;

  FX.rotatingText(document.getElementById("rt"), words);
  const dc = document.getElementById("dc");
  if (dc) {
    dc.appendChild(document.getElementById("dcDots")).classList.add("dc-dots");
    FX.depthCarousel(dc, { onOpen: (id) => go("product", { id: +id }) });
  }
  $view.querySelectorAll("[data-cat]").forEach((b) => (b.onclick = () => ((state.category = b.dataset.cat), haptic("select"), render())));
  const sort = document.getElementById("sort");
  if (sort) FX.rubberSegment(sort, (v) => ((state.sort = v), haptic("select"), setTimeout(render, 380)));
  $view.querySelectorAll(".card").forEach((c) => (c.onclick = (e) => !e.target.closest(".heart") && go("product", { id: +c.dataset.id })));
};

screens.product = async ({ id }) => {
  await loadProducts();
  const p = state.products.find((x) => x.id === id);
  if (!p) throw new Error("Товар больше недоступен");
  const soon = p.badge === "soon";
  const available = p.sizes.filter((s) => s.stock > 0);
  let size = available.length === 1 && !soon ? available[0].size : null;
  const photos = p.photos.length ? p.photos : [null];

  $view.innerHTML = `
    <div class="gallery" id="gallery">${photos.map((ph) => `<div>${photoHtml(ph)}</div>`).join("")}</div>
    ${photos.length > 1 ? `<div class="dots" id="dots">${photos.map((_, i) => `<i class="${i ? "" : "on"}"></i>`).join("")}</div>` : ""}
    <div class="p-head">
      <div class="grow">
        <div class="p-cat">${esc(p.category || "DAYZ DROP")} ${badgeTag(p)}</div>
        <div class="p-title">${esc(p.title)}</div>
        <div class="p-price">${priceHtml(p)}</div>
        ${p.rating ? `<div class="rating-mini" style="font-size:14px;margin-top:6px">★ ${p.rating} · ${p.rating_count} ${plural(p.rating_count, "оценка", "оценки", "оценок")}</div>` : ""}
      </div>
      ${heartBtn(p, true)}
    </div>
    ${soon ? "" : `${header("Размер")}<div class="sizes">${p.sizes.map((s) => `<button class="size ${s.stock ? "" : "empty"}" data-size="${esc(s.size)}">${esc(s.size)}${s.stock ? (s.stock <= 3 ? `<small>осталось ${s.stock}</small>` : "") : "<small>нет</small>"}</button>`).join("")}</div>`}
    <div id="bellWrap" style="margin-top:14px"></div>
    ${p.size_chart ? `<div style="margin-top:20px"><details class="chart"><summary>Замеры по размерам ${icon("chevronRight")}</summary><pre>${esc(p.size_chart)}</pre></details></div>` : ""}
    ${p.description ? `${header("Описание")}<div class="p-desc">${esc(p.description)}</div>` : ""}`;

  const gallery = document.getElementById("gallery");
  const dots = document.getElementById("dots");
  if (dots) gallery.onscroll = () => {
    const i = Math.round(gallery.scrollLeft / gallery.clientWidth);
    [...dots.children].forEach((d, j) => d.classList.toggle("on", i === j));
  };

  const bellWrap = document.getElementById("bellWrap");
  const showBell = (sz) => {
    const key = `${p.id}:${sz}`;
    bellWrap.innerHTML = `<button class="bell-toggle" id="bell">${icon("bell")}<span class="bt-labels"><span class="bt-off">${
      sz === "*" ? "Сообщить о старте продаж" : `Сообщить, когда появится ${esc(sz)}`}</span><span class="bt-on">Напишем в бота первым делом</span></span></button>`;
    FX.bellToggle(document.getElementById("bell"), state.subs.has(key), async (on) => {
      haptic("medium");
      await api("/api/subscribe", { method: "POST", body: { product_id: p.id, size: sz, on } });
      on ? state.subs.add(key) : state.subs.delete(key);
      toast(on ? "Подписка оформлена" : "Подписка снята");
    });
  };

  const addBtn = soon ? null : setBar(`<button class="btn" id="addBtn"></button>`).querySelector("#addBtn");
  const refresh = () => {
    $view.querySelectorAll(".size").forEach((b) => b.classList.toggle("active", b.dataset.size === size));
    const entry = p.sizes.find((s) => s.size === size);
    if (soon) return showBell("*");
    if (entry && !entry.stock) showBell(size);
    else bellWrap.innerHTML = "";
    const inCart = state.cart.find((i) => i.product_id === p.id && i.size === size);
    addBtn.disabled = !entry || !entry.stock;
    if (!stockOf(p)) addBtn.textContent = "Нет в наличии";
    else if (!size) addBtn.textContent = "Выбери размер";
    else if (!entry.stock) addBtn.textContent = "Этого размера нет";
    else addBtn.innerHTML = inCart ? `${icon("check")} В корзине · ${inCart.qty} шт` : `Добавить в корзину · ${money(p.price)}`;
  };
  $view.querySelectorAll(".size").forEach((b) => (b.onclick = () => ((size = b.dataset.size), haptic("select"), refresh())));
  if (addBtn) addBtn.onclick = () => {
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

screens.favorites = async () => {
  await loadProducts(true);
  const list = state.products.filter((p) => state.favorites.has(p.id));
  $view.innerHTML = list.length
    ? `<div class="grid" style="margin-top:8px">${list.map((p) => `
      <div class="card" data-id="${p.id}"><div class="card-img spot">${photoHtml(p.photos[0])}${badgeTag(p)}${heartBtn(p)}</div>
      <div class="card-title">${esc(p.title)}</div><div class="card-price">${priceHtml(p)}</div></div>`).join("")}</div>`
    : emptyHtml("star", "Пока пусто", "Нажимай на сердечко у вещей — они соберутся здесь.");
  $view.querySelectorAll(".card").forEach((c) => (c.onclick = (e) => !e.target.closest(".heart") && go("product", { id: +c.dataset.id })));
};

// ---------- корзина и оформление ----------

function cartLines() {
  return state.cart
    .map((i) => {
      const p = state.products.find((x) => x.id === i.product_id);
      const s = p && p.sizes.find((x) => x.size === i.size);
      return { ...i, product: p, stock: s ? s.stock : 0 };
    })
    .filter((l) => l.product && l.product.badge !== "soon");
}

screens.cart = async () => {
  $view.innerHTML = loaderHtml();
  await loadProducts(true);
  state.cart = cartLines().filter((l) => l.stock > 0).map((l) => ({ product_id: l.product_id, size: l.size, qty: Math.min(l.qty, l.stock) }));
  saveCart();
  const lines = cartLines();
  if (!lines.length) {
    $view.innerHTML = title("Корзина") + emptyHtml("cart", "Корзина пуста", "Добавь вещи из каталога — они появятся здесь.", "Перейти в каталог");
    document.getElementById("emptyBtn").onclick = () => switchTab("catalog");
    return;
  }
  const subtotal = lines.reduce((s, l) => s + l.product.price * l.qty, 0);
  const units = lines.reduce((s, l) => s + l.qty, 0);
  $view.innerHTML = `
    ${title("Корзина")}
    <div class="group">${lines.map((l, idx) => `
      <div class="cell has-thumb">
        <div class="thumb">${photoHtml(l.product.photos[0])}</div>
        <div class="grow">
          <div class="title">${esc(l.product.title)}</div>
          <div class="sub">Размер ${esc(l.size)} · ${money(l.product.price)}</div>
          <div style="margin-top:8px" class="stepper"><button data-dec="${idx}" aria-label="Меньше">${icon(l.qty > 1 ? "minus" : "trash")}</button><span>${l.qty}</span><button data-inc="${idx}" aria-label="Больше">${icon("plus")}</button></div>
        </div>
      </div>`).join("")}</div>
    <div class="group" style="margin-top:20px">
      ${kv(`${units} ${plural(units, "вещь", "вещи", "вещей")}`, money(subtotal))}
      ${kv("Доставка", "на следующем шаге")}
    </div>
    ${state.me.registered && state.settings.loyalty_enabled ? footer(`За этот заказ начислим около ${num(Math.floor(subtotal * state.settings.earn_percent / 100))} баллов.`) : ""}`;
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
  setBar(`<button class="btn" id="checkout">Оформить · ${money(subtotal)}</button>`).querySelector("#checkout").onclick = () => go("checkout");
};

screens.checkout = async () => {
  await loadProducts();
  const lines = cartLines();
  if (!lines.length) return switchTab("cart");
  const methods = state.settings.delivery_methods;
  const saved = loadJSON("dayz_customer", {});
  const user = (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) || {};
  const ck = state.checkout;
  if (!methods.some((m) => m.id === ck.delivery)) ck.delivery = (methods.find((m) => m.id === saved.delivery) || methods[0]).id;
  let profile = null;
  try {
    profile = state.me.registered ? await api("/api/profile") : null;
  } catch (_) {}
  const myCoupons = profile ? profile.coupons.filter((c) => !c.spent) : [];
  const name = saved.customer_name || state.me.full_name || [user.first_name, user.last_name].filter(Boolean).join(" ");
  const phone = saved.phone || state.me.phone || "";

  $view.innerHTML = `
    <form id="form" onsubmit="return false">
      ${header("Получатель")}
      <div class="group">
        <div class="cell field"><label for="f_name">Имя и фамилия</label><input class="input" id="f_name" name="customer_name" required autocomplete="name" value="${esc(name)}"></div>
        <div class="cell field"><label for="f_phone">Телефон</label><input class="input" id="f_phone" name="phone" type="tel" required autocomplete="tel" value="${esc(phone)}" placeholder="+998 90 123 45 67"></div>
      </div>
      ${header("Доставка")}
      <div class="group">${methods.map((m) => `
        <button type="button" class="cell tap" data-d="${esc(m.id)}">
          <div class="grow"><div class="title">${esc(m.name)}</div><div class="sub" data-dprice="${esc(m.id)}"></div></div>
          <span class="check-ico">${icon("check")}</span></button>`).join("")}</div>
      <div id="addrBlock">${header("Адрес")}
        <div class="group"><div class="cell field"><label for="f_addr">Город, улица, дом, ориентир</label><textarea class="input" id="f_addr" name="address" rows="2">${esc(saved.address || "")}</textarea></div></div>
      </div>
      ${header("Оплата")}
      <div id="payBlock"></div>
      ${header("Промокод или купон")}
      <div class="group">
        <div class="codeslots" id="codeslots"><div class="slots"></div><input id="f_coupon" autocomplete="one-time-code" autocapitalize="characters" spellcheck="false" aria-label="Промокод" value="${esc(ck.coupon)}"></div>
        <div id="couponState"></div>
      </div>
      ${myCoupons.length ? `<div class="pills" style="margin-top:10px">${myCoupons.map((c) => `<button type="button" class="pill" data-coupon="${esc(c.code)}">${icon("ticket")} ${esc(c.code)} · ${esc(c.label)}</button>`).join("")}</div>` : ""}
      ${header("Комментарий")}
      <div class="group"><div class="cell"><input class="input" name="comment" placeholder="Необязательно"></div></div>
    </form>
    ${header("Итого")}
    <div class="group" id="totals">${loaderHtml("Считаем")}</div>
    <div id="pointsNote"></div>`;

  const form = document.getElementById("form");
  const addrBlock = document.getElementById("addrBlock");
  const payBlock = document.getElementById("payBlock");
  let quote = null;
  let busy = false;

  const renderPayments = () => {
    const opts = [["card", "Картой"], ["cash", "Наличными"]].filter(([k]) => quote && quote.payments[k]);
    if (!opts.length) {
      payBlock.innerHTML = `<div class="group"><div class="cell"><span class="sub" style="margin:0">Для этой доставки сейчас нет доступной оплаты — напиши в поддержку.</span></div></div>`;
      return;
    }
    if (!opts.some(([k]) => k === ck.payment)) ck.payment = opts[0][0];
    const method = methods.find((m) => m.id === ck.delivery);
    const hint = ck.payment === "card"
      ? `Переводишь на карту после оформления и присылаешь чек. Вещи держим ${state.settings.cancel_hours || 24} ч.`
      : "Платишь наличными, когда забираешь заказ или курьеру.";
    const why = !quote.payments.cash ? (method && !method.cash ? "Для этой доставки — только предоплата картой." : "Для тебя доступна только предоплата картой.") : "";
    payBlock.innerHTML = (opts.length > 1 ? rseg(opts, ck.payment, "payseg") : `<div class="group"><div class="cell">${icon(opts[0][0] === "card" ? "card" : "cash")}<span class="grow title">${opts[0][1]}</span></div></div>`) +
      footer(esc(why ? `${why} ${hint}` : hint));
    const seg = document.getElementById("payseg");
    if (seg) FX.rubberSegment(seg, (v) => ((ck.payment = v), haptic("select"), recalc()));
  };

  const renderTotals = () => {
    const t = document.getElementById("totals");
    if (!quote) return;
    t.innerHTML = `
      ${kv("Товары", money(quote.subtotal))}
      ${quote.discount ? kv(`Скидка · ${quote.coupon}`, `−${money(quote.discount)}`, "minus") : ""}
      ${kv("Доставка", quote.delivery_price ? money(quote.delivery_price) : "бесплатно")}
      <div class="cell total"><span class="title">Итого</span><span class="value" style="flex:1">${money(quote.total)}</span></div>`;
    const note = document.getElementById("pointsNote");
    if (state.settings.loyalty_enabled && quote.earn_points) {
      note.innerHTML = quote.registered
        ? footer(`${icon("gift")} После получения начислим <b>${num(quote.earn_points)}</b> баллов.`)
        : footer(`Зарегистрируйся в профиле — получишь ${num(state.settings.welcome_points)} баллов сразу и ${num(quote.earn_points)} за этот заказ.`);
    } else note.innerHTML = "";
    const cs = document.getElementById("couponState");
    cs.innerHTML = quote.coupon
      ? `<div class="coupon-ok">${icon("checkCircle")} ${esc(quote.coupon_title || "Промокод применён")} · −${money(quote.discount)}</div>`
      : quote.coupon_error ? `<div class="coupon-ok" style="color:var(--red)">${icon("xCircle")} ${esc(quote.coupon_error)}</div>` : "";
    submit.innerHTML = `Подтвердить · ${money(quote.total)}`;
    submit.disabled = !quote.payments[ck.payment];
  };

  const recalc = async () => {
    try {
      quote = await api("/api/quote", { method: "POST", body: { items: state.cart, delivery: ck.delivery, payment: ck.payment, coupon: ck.coupon } });
    } catch (err) {
      toast(err.message, true);
      return;
    }
    methods.forEach((m) => {
      const el = $view.querySelector(`[data-dprice="${m.id}"]`);
      const cost = m.free_from && quote.subtotal >= m.free_from ? 0 : m.price;
      const extra = [m.note, !m.cash ? "только предоплата" : "", m.free_from && cost ? `бесплатно от ${money(m.free_from)}` : ""].filter(Boolean).join(" · ");
      if (el) el.innerHTML = `${cost ? money(cost) : "бесплатно"}${extra ? " · " + esc(extra) : ""}`;
    });
    renderPayments();
    renderTotals();
  };

  const refreshDelivery = () => {
    $view.querySelectorAll("[data-d]").forEach((b) => (b.querySelector(".check-ico").style.visibility = b.dataset.d === ck.delivery ? "visible" : "hidden"));
    const method = methods.find((m) => m.id === ck.delivery);
    addrBlock.style.display = method && method.address ? "" : "none";
  };
  $view.querySelectorAll("[data-d]").forEach((b) => (b.onclick = () => ((ck.delivery = b.dataset.d), haptic("select"), refreshDelivery(), recalc())));
  refreshDelivery();

  const slots = FX.codeSlots(document.getElementById("codeslots"), {
    onChange: debounce((v) => {
      if (!v || v.length >= 4) (ck.coupon = v), recalc();
    }, 500),
  });
  $view.querySelectorAll("[data-coupon]").forEach((b) => (b.onclick = () => (slots.set(b.dataset.coupon), (ck.coupon = b.dataset.coupon), haptic("select"), recalc())));

  const submit = setBar(`<button class="btn" id="submit">Подтвердить</button>`).querySelector("#submit");
  submit.onclick = async () => {
    if (busy || !form.reportValidity()) return;
    const data = Object.fromEntries(new FormData(form));
    saveJSON("dayz_customer", { customer_name: data.customer_name, phone: data.phone, address: data.address, delivery: ck.delivery });
    busy = true;
    submit.disabled = true;
    submit.textContent = "Оформляем…";
    try {
      const order = await api("/api/orders", { method: "POST", body: { ...data, items: state.cart, delivery: ck.delivery, payment: ck.payment, coupon: ck.coupon } });
      state.cart = [];
      ck.coupon = "";
      saveCart();
      state.products = [];
      haptic("ok");
      state.tab = "orders";
      state.stacks.orders = [{ name: "orders" }, { name: "order", params: { id: order.id, fresh: true } }];
      state.stacks.cart = [{ name: "cart" }];
      renderNav();
      render();
    } catch (err) {
      toast(err.message, true);
      busy = false;
      submit.disabled = false;
      renderTotals();
    }
  };
  recalc();
};

// ---------- заказы покупателя ----------

function orderRow(o, admin) {
  const who = admin ? esc(o.customer_name) : `${o.items.length} ${plural(o.items.length, "позиция", "позиции", "позиций")}`;
  return `
    <button class="cell tap has-thumb" data-id="${o.id}">
      <div class="thumb">${photoHtml(o.items[0] && o.items[0].photo)}</div>
      <div class="grow">
        <div class="title">Заказ #${o.id}${admin && o.payment_method === "cash" ? ` <span style="color:var(--yellow);font-size:13px">наличные</span>` : ""}</div>
        <div class="sub">${who} · ${fmtDate(o.created_at)}</div>
        <div style="margin-top:6px">${statusPill(o.status)}${admin && o.assignee_name ? ` <span class="sub" style="font-size:12px">· ${esc(o.assignee_name)}</span>` : ""}</div>
      </div>
      <span class="value">${money(o.total)}</span>${chev()}
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
  $view.querySelectorAll("[data-id]").forEach((b) => (b.onclick = () => go("order", { id: +b.dataset.id, title: `Заказ #${b.dataset.id}` })));
};

function totalsGroup(o) {
  return `${header("Состав")}<div class="group">
    ${o.items.map((i) => kv(`${i.title} · ${i.size} × ${i.qty}`, money(i.price * i.qty))).join("")}
    ${o.discount ? kv(`Скидка${o.coupon_code ? " · " + o.coupon_code : ""}`, `−${money(o.discount)}`, "minus") : ""}
    ${kv(`Доставка`, o.delivery_price ? money(o.delivery_price) : "бесплатно")}
    <div class="cell total"><span class="title">Итого</span><span class="value" style="flex:1">${money(o.total)}</span></div>
  </div>`;
}

function deliveryGroup(o) {
  return `${header("Доставка")}<div class="group">
    ${kv("Получатель", esc(o.customer_name))}
    ${kv("Телефон", esc(o.phone))}
    ${kv("Способ", esc(o.delivery))}
    ${o.address ? kv("Адрес", esc(o.address)) : ""}
    ${kv("Оплата", o.payment_method === "cash" ? "Наличными при получении" : "Картой")}
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
  const needPay = o.status === "awaiting_payment" && o.payment_method !== "cash";

  $view.innerHTML = `
    ${title(fresh ? "Заказ оформлен" : `Заказ #${o.id}`)}
    <div class="subtitle">№${o.id} · ${fmtDate(o.created_at)}</div>
    ${statusCard(o.status)}
    ${needPay ? `${header("Перевод на карту")}
      <div class="group">
        <div class="cell"><div class="grow"><div class="sub" style="margin:0 0 4px">${esc(o.card_label || "Карта")}</div><div class="mono">${esc(o.card_details || "")}</div></div><button class="icon-btn" id="copyCard" aria-label="Скопировать">${icon("copy")}</button></div>
        <div class="cell"><div class="grow"><div class="sub" style="margin:0 0 2px">Сумма</div><div class="title"><b>${money(o.total)}</b></div></div><button class="icon-btn" id="copySum" aria-label="Скопировать">${icon("copy")}</button></div>
      </div>
      ${footer(`После перевода загрузи скриншот или PDF чека — или отправь его боту в чат. Без чека заказ снимется через ${state.settings.cancel_hours || 24} ч.`)}` : ""}
    ${o.status === "done" ? `${header("Оцени заказ")}<div class="group" style="padding:4px 16px 14px">
      <div class="peek" id="peek">${[1, 2, 3, 4, 5].map(() => `<span class="star">${STAR_SVG}</span>`).join("")}</div>
      ${o.rating ? `<div class="sub" style="text-align:center">Спасибо за оценку!${o.rating_comment ? ` «${esc(o.rating_comment)}»` : ""}</div>` : `<input class="input" id="rateComment" placeholder="Пара слов — что понравилось?" style="text-align:center;margin-top:6px">`}
    </div>` : ""}
    ${totalsGroup(o)}
    ${o.points_awarded ? footer(`${icon("gift")} За заказ начислено ${num(o.points_awarded)} баллов.`) : ""}
    ${deliveryGroup(o)}
    <div class="stack">
      ${o.status === "checking" ? `<button class="btn glass" id="reupload">${icon("doc")} Отправить другой чек</button>` : ""}
      <button class="btn glass" id="support">${icon("bubble")} Написать в поддержку</button>
      ${["awaiting_payment", "confirmed"].includes(o.status) ? `<button class="btn red" id="cancel">Отменить заказ</button>` : ""}
    </div>`;

  const reload = () => screens.order({ id });
  if (needPay) {
    document.getElementById("copyCard").onclick = () => copy((o.card_details || "").split("\n")[0].replace(/\s/g, ""), "Номер карты скопирован");
    document.getElementById("copySum").onclick = () => copy(String(o.total), "Сумма скопирована");
    setBar(`<button class="btn" id="upload">${icon("doc")} Загрузить чек</button>`).querySelector("#upload").onclick = () => uploadReceipt(o.id, reload);
  }
  const peek = document.getElementById("peek");
  if (peek) FX.peekRating(peek, {
    value: o.rating || 0,
    onChange: async (rating) => {
      haptic("medium");
      try {
        const comment = (document.getElementById("rateComment") || {}).value || o.rating_comment || "";
        await api(`/api/orders/${o.id}/rate`, { method: "POST", body: { rating, comment } });
        toast("Спасибо за оценку!");
        setTimeout(reload, 700);
      } catch (err) {
        toast(err.message, true);
      }
    },
  });
  const cancel = document.getElementById("cancel");
  if (cancel) cancel.onclick = async () => {
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
  const re = document.getElementById("reupload");
  if (re) re.onclick = () => uploadReceipt(o.id, reload);
  document.getElementById("support").onclick = openSupport;
};

// ---------- профиль, регистрация, баллы ----------

screens.profile = async () => {
  $view.innerHTML = loaderHtml();
  const data = await api("/api/profile");
  state.me = data.user;
  const s = state.settings;
  if (!data.user.registered) {
    const tgUser = (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) || {};
    $view.innerHTML = `
      ${title("Профиль")}
      <div class="points-card">${FX.lightPillar("dim")}
        <div class="pc-label">Бонусная программа DAYZ DROP</div>
        <div class="pc-num">+${num(s.welcome_points)}</div>
        <div class="pc-sub">баллов сразу после регистрации и ${s.earn_percent}% баллами с каждого заказа. Баллы меняются на скидки и вещи.</div>
      </div>
      ${header("Регистрация")}
      <form id="regForm" onsubmit="return false"><div class="group">
        <div class="cell field"><label>Имя</label><input class="input" name="name" required value="${esc([tgUser.first_name, tgUser.last_name].filter(Boolean).join(" "))}"></div>
        <div class="cell field"><label>Телефон</label><input class="input" name="phone" id="regPhone" type="tel" required placeholder="+998 90 123 45 67"></div>
        ${can("6.9") ? `<button type="button" class="cell tap" id="shareContact">${FX.glassIcon(icon("user"), "blue")}<span class="grow link">Подставить номер из Telegram</span></button>` : ""}
      </div></form>
      ${footer("Регистрация необязательна — покупать можно и без неё. Номер нужен только для связи по заказам.")}
      <div class="stack">
        <button class="btn glass" id="favs">${icon("star")} Избранное · ${state.favorites.size}</button>
        <button class="btn glass" id="support">${icon("bubble")} Поддержка</button>
      </div>`;
    setBar(`<button class="btn" id="regBtn">Зарегистрироваться</button>`).querySelector("#regBtn").onclick = async () => {
      const form = document.getElementById("regForm");
      if (!form.reportValidity()) return;
      try {
        const user = await api("/api/profile/register", { method: "POST", body: Object.fromEntries(new FormData(form)) });
        state.me = user;
        toast(`Готово! +${num(user.points)} баллов`);
        render();
      } catch (err) {
        toast(err.message, true);
      }
    };
    const share = document.getElementById("shareContact");
    if (share) share.onclick = () => tg.requestContact((ok, res) => {
      const phone = res && res.responseUnsafe && res.responseUnsafe.contact && res.responseUnsafe.contact.phone_number;
      if (phone) document.getElementById("regPhone").value = phone;
      else if (ok) toast("Номер отправлен боту — введи его здесь тоже");
    });
    document.getElementById("favs").onclick = () => go("favorites", { title: "Избранное" });
    document.getElementById("support").onclick = openSupport;
    return;
  }

  const u = data.user;
  const activeCoupons = data.coupons.filter((c) => !c.spent);
  $view.innerHTML = `
    ${title(u.full_name || u.first_name || "Профиль")}
    <div class="subtitle">${esc(u.phone || "")}</div>
    <div class="points-card">${FX.lightPillar("dim")}
      <div class="pc-label">Твои баллы</div>
      <div class="pc-num" id="pts">0</div>
      <div class="pc-sub">${s.earn_percent}% от каждого полученного заказа возвращаются баллами</div>
    </div>
    <div class="bento" style="margin-top:12px">
      <button class="bento-card" id="bOrders"><div class="b-top">${FX.glassIcon(icon("box"), "indigo")}</div><div><div class="b-num">${data.orders_count}</div><div class="b-label">${plural(data.orders_count, "заказ", "заказа", "заказов")}</div></div></button>
      <button class="bento-card" id="bFavs"><div class="b-top">${FX.glassIcon(icon("star"), "pink")}</div><div><div class="b-num">${state.favorites.size}</div><div class="b-label">в избранном</div></div></button>
    </div>
    ${header("Обменять баллы")}
    ${data.rewards.length ? `<div class="group">${data.rewards.map((r) => `
      <div class="cell has-ico reward">
        ${FX.glassIcon(icon(r.kind === "gift" ? "gift" : "ticket"), r.kind === "gift" ? "orange" : "purple")}
        <div class="grow"><div class="title">${esc(r.title)}</div><div class="sub">${esc(r.label)}</div></div>
        <button class="btn sm ${u.points >= r.cost ? "" : "glass"}" data-reward="${r.id}" ${u.points >= r.cost ? "" : "disabled"}>${num(r.cost)} б.</button>
      </div>`).join("")}</div>` : `<div class="group"><div class="cell"><span class="sub" style="margin:0">Скоро здесь появятся награды за баллы</span></div></div>`}
    ${header("Мои купоны")}
    ${data.coupons.length ? `<div class="group">${data.coupons.map((c) => `
      <div class="coupon ${c.spent ? "spent" : ""}">${FX.glassIcon(icon("ticket"), "teal")}
        <div class="grow"><div class="code">${esc(c.code)}</div><div class="sub">${esc(c.title || c.label)}${c.spent ? " · использован" : ""}</div></div>
        ${c.spent ? "" : `<button class="icon-btn" data-copy="${esc(c.code)}" aria-label="Скопировать">${icon("copy")}</button>`}
      </div>`).join("")}</div>${activeCoupons.length ? footer("Введи код при оформлении заказа — или выбери купон прямо там.") : ""}` : `<div class="group"><div class="cell"><span class="sub" style="margin:0">Обменяй баллы — купон появится здесь</span></div></div>`}
    ${header("История баллов")}
    <div class="group">${data.history.slice(0, 8).map((t) => `
      <div class="cell"><div class="grow"><div class="title" style="font-size:15px">${esc(t.reason)}</div><div class="sub" style="font-size:12px">${fmtDate(t.created_at)}</div></div>
      <span class="delta ${t.delta > 0 ? "plus" : "minus"}">${t.delta > 0 ? "+" : ""}${num(t.delta)}</span></div>`).join("") || `<div class="cell"><span class="sub" style="margin:0">Пока пусто</span></div>`}</div>
    <div class="stack"><button class="btn glass" id="support">${icon("bubble")} Поддержка</button></div>`;
  FX.countUp(document.getElementById("pts"), u.points);
  document.getElementById("bOrders").onclick = () => switchTab("orders");
  document.getElementById("bFavs").onclick = () => go("favorites", { title: "Избранное" });
  document.getElementById("support").onclick = openSupport;
  $view.querySelectorAll("[data-copy]").forEach((b) => (b.onclick = () => copy(b.dataset.copy, "Код скопирован")));
  $view.querySelectorAll("[data-reward]").forEach((b) => (b.onclick = async () => {
    const reward = data.rewards.find((r) => r.id === +b.dataset.reward);
    if (!(await confirmDialog(`Обменять ${num(reward.cost)} баллов на «${reward.title}»?`))) return;
    try {
      const res = await api(`/api/rewards/${reward.id}/exchange`, { method: "POST" });
      toast(`Купон ${res.coupon.code} — уже в профиле`);
      render();
    } catch (err) {
      toast(err.message, true);
    }
  }));
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
      if (tg.disableVerticalSwipes) tg.disableVerticalSwipes();
    } catch (_) {}
    if (can("6.1")) tg.BackButton.onClick(back);
  }
  FX.clickSpark();
  FX.pointerLights();
  $view.innerHTML = loaderHtml("Загружаем DAYZ DROP");

  if (!tg || !tg.initData) {
    $view.innerHTML = `<section class="hero">${FX.lightPillar()}<img class="logo" src="assets/logo-banner.jpg" alt="DAYZ DROP"></section>${emptyHtml("bag", "Открой магазин в Telegram", "Мини-приложение работает внутри бота DAYZ DROP.")}`;
    return;
  }
  try {
    const data = await api("/api/bootstrap");
    state.me = data.user;
    state.isAdmin = data.is_admin;
    state.botUsername = data.bot_username;
    state.settings = data.settings;
    state.favorites = new Set(data.favorites);
    state.subs = new Set(data.subscriptions.map((s) => `${s.product_id}:${s.size}`));
  } catch (err) {
    $view.innerHTML = emptyHtml("warning", "Не удалось загрузить магазин", err.message, "Повторить");
    document.getElementById("emptyBtn").onclick = () => location.reload();
    return;
  }

  // Ссылки из бота: ?page=order&id=12, ?page=product&id=3, ?page=profile, ?page=admin&order=12, ?page=admin&section=settings
  const page = qs.get("page");
  const idParam = +qs.get("id");
  if (page === "admin" && state.isAdmin) {
    state.tab = "admin";
    if (qs.get("order")) state.stacks.admin.push({ name: "adminOrders", params: { title: "Заказы" } }, { name: "adminOrder", params: { id: +qs.get("order"), title: `Заказ #${qs.get("order")}` } });
    if (qs.get("section") === "settings") state.stacks.admin.push({ name: "adminSettings", params: { title: "Настройки" } });
  } else if (page === "order" && idParam) {
    state.tab = "orders";
    state.stacks.orders.push({ name: "order", params: { id: idParam, title: `Заказ #${idParam}` } });
  } else if (page === "product" && idParam) {
    state.stacks.catalog.push({ name: "product", params: { id: idParam } });
  } else if (page === "profile") {
    state.tab = "profile";
  }
  renderNav();
  render();
}

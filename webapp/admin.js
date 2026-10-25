"use strict";
/* DAYZ DROP — экраны админки (видны только ADMIN_IDS, сервер проверяет каждый запрос). */

const sub = (name, params) => go(name, params);
const field = (label, inner) => `<div class="cell field"><label>${esc(label)}</label>${inner}</div>`;
const inputEl = (id, value, attrs = "") => `<input class="input" id="${id}" value="${esc(value == null ? "" : value)}" ${attrs}>`;
const numEl = (id, value, attrs = "") => `<input class="input num" id="${id}" type="number" inputmode="numeric" min="0" value="${esc(value == null ? "" : value)}" ${attrs}>`;
const val = (id) => (document.getElementById(id) || {}).value;
const checked = (id) => !!(document.getElementById(id) || {}).checked;
const switchRow = (id, label, on, sub = "") => `<label class="cell"><span class="grow"><span class="title">${esc(label)}</span>${sub ? `<div class="sub">${esc(sub)}</div>` : ""}</span><input type="checkbox" class="switch" id="${id}" ${on ? "checked" : ""}></label>`;
const KIND_TEXT = { percent: "Процент", amount: "Сумма", gift: "Вещь в подарок" };

async function action(promise, okText) {
  try {
    const res = await promise;
    if (okText) toast(okText);
    return res;
  } catch (err) {
    toast(err.message, true);
    throw err;
  }
}

// ---------- хаб (Magic Bento) ----------

screens.admin = async () => {
  $view.innerHTML = title("Управление") + loaderHtml();
  const d = await api("/api/admin/dashboard");
  const bs = d.by_status;
  const attention = (bs.checking || 0) + (bs.paid || 0) + (bs.confirmed || 0);
  $view.innerHTML = `
    ${title("Управление")}
    <div class="bento">
      <button class="bento-card wide" data-go="adminOrders">
        <div class="b-top">${FX.glassIcon(icon("box"), "indigo")}${attention ? `<span class="b-badge">${attention} ждут</span>` : ""}</div>
        <div><div class="b-title">Заказы</div><div class="b-label">Проверить оплату: ${bs.checking || 0} · Отправить: ${bs.paid || 0} · Наличные: ${bs.confirmed || 0}</div></div>
      </button>
      <button class="bento-card" data-go="adminFinance">
        <div class="b-top">${FX.glassIcon(icon("wallet"), "green")}</div>
        <div><div class="b-num sm" data-money="${d.today.revenue}">0</div><div class="b-label">выручка сегодня · прибыль ${money(d.today.profit)}</div></div>
      </button>
      <button class="bento-card" data-go="adminStock">
        <div class="b-top">${FX.glassIcon(icon("tray"), "orange")}${d.low_stock.length ? `<span class="b-badge">${d.low_stock.length}</span>` : ""}</div>
        <div><div class="b-num" data-count="${d.units}">0</div><div class="b-label">на складе${d.low_stock.length ? " · заканчивается" : ""}</div></div>
      </button>
      <button class="bento-card" data-go="adminProducts">
        <div class="b-top">${FX.glassIcon(icon("hanger"), "blue")}</div>
        <div><div class="b-num">${d.products}</div><div class="b-label">товаров</div></div>
      </button>
      <button class="bento-card" data-go="adminCustomers">
        <div class="b-top">${FX.glassIcon(icon("users"), "pink")}</div>
        <div><div class="b-num">${d.users}</div><div class="b-label">покупателей · ${d.registered} в программе</div></div>
      </button>
      <button class="bento-card" data-go="adminMarketing">
        <div class="b-top">${FX.glassIcon(icon("gift"), "purple")}</div>
        <div><div class="b-title">Маркетинг</div><div class="b-label">промокоды, награды, баллы</div></div>
      </button>
      <button class="bento-card" data-go="adminBroadcast">
        <div class="b-top">${FX.glassIcon(icon("megaphone"), "red")}</div>
        <div><div class="b-title">Рассылка</div><div class="b-label">дроп всем в бота</div></div>
      </button>
      <button class="bento-card" data-go="adminExport">
        <div class="b-top">${FX.glassIcon(icon("download"), "teal")}</div>
        <div><div class="b-title">Excel</div><div class="b-label">выгрузки и бэкап</div></div>
      </button>
      <button class="bento-card" data-go="adminSettings">
        <div class="b-top">${FX.glassIcon(icon("gear"), "gray")}</div>
        <div><div class="b-title">Настройки</div><div class="b-label">карты, доставка, баллы</div></div>
      </button>
    </div>
    ${header("За 30 дней")}
    <div class="tiles">
      <div class="tile"><b>${money(d.month.revenue)}</b><span>выручка</span></div>
      <div class="tile"><b>${money(d.month.profit)}</b><span>прибыль · ${d.month.orders} ${plural(d.month.orders, "заказ", "заказа", "заказов")}</span></div>
    </div>`;
  const titles = { adminOrders: "Заказы", adminFinance: "Касса", adminStock: "Склад", adminProducts: "Товары", adminCustomers: "Покупатели",
    adminMarketing: "Маркетинг", adminBroadcast: "Рассылка", adminExport: "Выгрузки", adminSettings: "Настройки" };
  $view.querySelectorAll("[data-go]").forEach((b) => (b.onclick = () => sub(b.dataset.go, { title: titles[b.dataset.go] })));
  $view.querySelectorAll("[data-money]").forEach((el) => FX.countUp(el, +el.dataset.money, { format: (n) => money(n) }));
  $view.querySelectorAll("[data-count]").forEach((el) => FX.countUp(el, +el.dataset.count));
};

// ---------- заказы ----------

let adminStatus = "";
screens.adminOrders = async () => {
  $view.innerHTML = loaderHtml();
  const [orders, d] = await Promise.all([api(`/api/admin/orders${adminStatus ? `?status=${adminStatus}` : ""}`), api("/api/admin/dashboard")]);
  const c = (k) => d.by_status[k] || 0;
  const filters = [["", "Все"], ["checking", "Проверка"], ["awaiting_payment", "Ждут оплату"], ["confirmed", "Наличные"], ["paid", "Отправить"], ["shipped", "В пути"], ["done", "Получены"], ["cancelled", "Отменены"]];
  $view.innerHTML = `
    <div class="pills">${filters.map(([s, l]) => `<button class="pill ${adminStatus === s ? "active" : ""}" data-st="${s}">${l}${s && c(s) ? `<span class="count">${c(s)}</span>` : ""}</button>`).join("")}</div>
    ${orders.length ? `<div class="group">${orders.map((o) => orderRow(o, true)).join("")}</div>` : emptyHtml("box", "Заказов нет", "")}`;
  $view.querySelectorAll("[data-st]").forEach((b) => (b.onclick = () => ((adminStatus = b.dataset.st), haptic("select"), render())));
  $view.querySelectorAll("[data-id]").forEach((b) => (b.onclick = () => sub("adminOrder", { id: +b.dataset.id, title: `Заказ #${b.dataset.id}` })));
};

screens.adminOrder = async ({ id }) => {
  $view.innerHTML = loaderHtml();
  const o = await api(`/api/admin/orders/${id}`);
  const cash = o.payment_method === "cash";
  const actions = {
    awaiting_payment: [["paid", "Оплата пришла", "green"]],
    checking: [["paid", "Деньги пришли", "green"], ["awaiting_payment", "Деньги не пришли", "glass"]],
    confirmed: [["shipped", "Передан курьеру / отправлен", ""], ["done", "Выдан и оплачен", "green"], ["paid", "Деньги получены заранее", "glass"]],
    paid: [["shipped", "Отправлен", ""], ["done", "Получен", "glass"]],
    shipped: [["done", cash && !o.paid_at ? "Получен и оплачен" : "Получен", "green"], ["shipped", "Обновить трек", "glass"]],
  }[o.status] || [];
  const profit = o.paid_at ? o.total - o.delivery_price - o.cogs : null;
  $view.innerHTML = `
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:6px 0 14px">${statusPill(o.status)}<span class="sub" style="color:var(--label-2);font-size:15px">${fmtDate(o.created_at)} · ${cash ? "наличные" : "карта " + esc(o.card_label || "")}</span></div>
    ${["done", "cancelled"].includes(o.status) ? "" : `<button class="btn ${o.assignee_id ? "glass" : "blue"}" id="assign">${icon("user")} ${o.assignee_name ? `Ведёт ${esc(o.assignee_name)} · снять` : "Взять в работу"}</button>`}
    ${header("Покупатель")}
    <div class="group">
      ${kv("Имя", esc(o.customer_name))}
      ${kv("Telegram", o.username ? `@${esc(o.username)}` : `id ${o.user_id}`)}
      ${o.customer && o.customer.registered ? kv("Баллы", num(o.customer.points)) : ""}
      ${o.customer && o.customer.no_cash ? kv("Внимание", `<span style="color:var(--red)">не выкупал — только предоплата</span>`) : ""}
      ${o.customer && o.customer.note ? kv("Заметка", esc(o.customer.note)) : ""}
      ${o.username ? `<button class="cell tap" id="writeUser"><span class="grow link">Написать в Telegram</span>${chev()}</button>` : ""}
      <button class="cell tap" id="openCustomer"><span class="grow link">Карточка покупателя</span>${chev()}</button>
    </div>
    ${totalsGroup(o)}
    ${o.paid_at ? footer(`Себестоимость ${money(o.cogs)}${o.cogs_unknown ? " (у части вещей нет цены закупки)" : ""} · прибыль <b>${money(profit)}</b> · ${esc(o.paid_via || "")}`) : ""}
    ${deliveryGroup(o)}
    ${cash ? "" : `${header("Чек")}<div class="group">${
      o.receipt_file_id
        ? o.receipt_kind === "photo"
          ? `<div style="padding-top:14px"><div class="receipt"><img src="${photoUrl(o.receipt_file_id)}" alt="Чек"></div></div>`
          : `<button class="cell tap" id="openReceipt">${icon("doc")}<span class="grow">Открыть файл чека</span>${chev()}</button>`
        : `<div class="cell"><span class="sub" style="margin:0">Покупатель ещё не прислал чек</span></div>`
    }</div>`}
    ${["confirmed", "paid", "shipped"].includes(o.status) ? `${header("Трек-номер")}<div class="group"><div class="cell"><input class="input" id="track" value="${esc(o.track || "")}" placeholder="Номер отправления или «курьер Азиз»"></div></div>` : ""}
    <div class="stack">
      ${actions.map(([s, l, cls]) => `<button class="btn ${cls}" data-to="${s}">${l}</button>`).join("")}
      ${cash && ["confirmed", "shipped"].includes(o.status) ? `<button class="btn red" id="noshow">Не выкупил</button>` : ""}
      ${["done", "cancelled"].includes(o.status) ? "" : `<button class="btn red" data-to="cancelled">Отменить заказ</button>`}
    </div>
    ${o.rating ? `${header("Оценка покупателя")}<div class="group"><div class="cell"><span class="grow" style="color:var(--yellow);font-size:20px">${"★".repeat(o.rating)}${"☆".repeat(5 - o.rating)}</span></div>${o.rating_comment ? `<div class="cell"><span class="sub" style="margin:0">«${esc(o.rating_comment)}»</span></div>` : ""}</div>` : ""}
    ${header("История")}
    <div class="group"><div class="timeline">${(o.history || []).slice().reverse().map((h) => `<div>${esc(h.text)}<small>${fmtDate(h.at)}${h.who ? " · " + esc(h.who) : ""}</small></div>`).join("") || '<div>Нет записей</div>'}</div></div>`;

  const reload = () => screens.adminOrder({ id });
  const assign = document.getElementById("assign");
  if (assign) assign.onclick = () => action(api(`/api/admin/orders/${id}/assign`, { method: "POST" })).then(reload, () => {});
  const wu = document.getElementById("writeUser");
  if (wu) wu.onclick = () => openLink(`https://t.me/${o.username}`);
  document.getElementById("openCustomer").onclick = () => sub("adminCustomer", { id: o.user_id, title: o.customer_name });
  const rc = document.getElementById("openReceipt");
  if (rc) rc.onclick = () => openLink(photoUrl(o.receipt_file_id));
  const noshow = document.getElementById("noshow");
  if (noshow) noshow.onclick = async () => {
    if (!(await confirmDialog("Покупатель не выкупил? Заказ отменится, вещи вернутся на склад, а наличные для него отключатся."))) return;
    action(api(`/api/admin/orders/${id}/noshow`, { method: "POST" }), "Отмечено: не выкупил").then(reload, () => {});
  };
  $view.querySelectorAll("[data-to]").forEach((b) => (b.onclick = async () => {
    const to = b.dataset.to;
    const trackEl = document.getElementById("track");
    const track = trackEl ? trackEl.value.trim() : undefined;
    if (to === "cancelled" && !(await confirmDialog(`Отменить заказ #${id}? Вещи вернутся на склад, покупатель получит сообщение.`))) return;
    if (to === "awaiting_payment" && !(await confirmDialog("Отклонить чек? Покупателю придёт сообщение, что оплата не найдена."))) return;
    action(api(`/api/admin/orders/${id}/status`, { method: "POST", body: { status: to, track } }), `Статус: ${STATUS[to]}`).then(reload, () => {});
  }));
};

// ---------- товары ----------

let adminProductsCache = [];
screens.adminProducts = async () => {
  $view.innerHTML = loaderHtml();
  adminProductsCache = await api("/api/admin/products");
  $view.innerHTML = `
    <button class="btn" id="addProduct" style="margin:6px 0 18px">${icon("plus")} Новый товар</button>
    ${adminProductsCache.length ? `<div class="group">${adminProductsCache.map((p) => `
      <button class="cell tap has-thumb" data-id="${p.id}">
        <div class="thumb">${photoHtml(p.photos[0])}</div>
        <div class="grow">
          <div class="title">${esc(p.title)} ${p.badge ? `<span class="tag ${p.badge}" style="vertical-align:middle">${{ new: "new", hit: "хит", soon: "скоро" }[p.badge]}</span>` : ""}</div>
          <div class="sub">${esc(p.category || "Без категории")} · ${money(p.price)}${p.is_active ? "" : " · скрыт"}${p.likes ? ` · ♥ ${p.likes}` : ""}</div>
          <div class="size-chips">${p.sizes.map((s) => `<span class="${s.stock ? "" : "zero"}">${esc(s.size)} ${s.stock}</span>`).join("")}</div>
        </div>${chev()}
      </button>`).join("")}</div>` : emptyHtml("hanger", "Товаров пока нет", "Добавь первый — он сразу появится в каталоге.")}`;
  document.getElementById("addProduct").onclick = () => sub("productForm", { title: "Новый товар" });
  $view.querySelectorAll("[data-id]").forEach((b) => (b.onclick = () => sub("productForm", { id: +b.dataset.id, title: "Товар" })));
};

screens.productForm = async ({ id }) => {
  if (!adminProductsCache.length) adminProductsCache = await api("/api/admin/products");
  const existing = adminProductsCache.find((p) => p.id === id);
  const p = existing ? JSON.parse(JSON.stringify(existing)) : {
    title: "", category: "", price: "", old_price: "", description: "", size_chart: "", badge: "new",
    sizes: [{ size: "S", stock: 0 }, { size: "M", stock: 0 }, { size: "L", stock: 0 }, { size: "XL", stock: 0 }], photos: [], is_active: true, sort: 0,
  };
  const categories = [...new Set(adminProductsCache.map((x) => x.category).filter(Boolean))];

  const sync = () => {
    ["title", "category", "price", "old_price", "description", "size_chart", "sort"].forEach((k) => (p[k] = val(`f_${k}`)));
    p.is_active = checked("f_active");
    p.sizes = p.sizes.map((s, i) => ({ size: $view.querySelector(`[data-sz="${i}"]`).value.trim(), stock: +$view.querySelector(`[data-st="${i}"]`).value || 0 }));
  };
  const draw = () => {
    $view.innerHTML = `
      ${header("Фото · первое — обложка")}
      <div class="group"><div class="photos">
        ${p.photos.map((ph, i) => `<div><img src="${photoUrl(ph)}" alt=""><button class="rm" data-rmph="${i}" aria-label="Убрать">${icon("xmark")}</button></div>`).join("")}
        ${p.photos.length < 10 ? `<button class="add" id="addPhoto" aria-label="Добавить фото">${icon("photo")}</button>` : ""}
      </div></div>
      ${header("Основное")}
      <div class="group">
        ${field("Название", inputEl("f_title", p.title, 'placeholder="Худи DAYZ Black"'))}
        ${field("Категория", inputEl("f_category", p.category, 'list="cats" placeholder="Худи, футболки, карго…"') + `<datalist id="cats">${categories.map((c) => `<option value="${esc(c)}">`).join("")}</datalist>`)}
        <div class="cell"><span class="grow title">Цена, ${esc(state.settings.currency)}</span>${numEl("f_price", p.price, 'placeholder="0"')}</div>
        <div class="cell"><span class="grow"><span class="title">Старая цена</span><div class="sub">зачёркнутая, для скидки</div></span>${numEl("f_old_price", p.old_price || "", 'placeholder="—"')}</div>
        ${field("Описание", `<textarea class="input" id="f_description" placeholder="Материал, посадка, уход">${esc(p.description)}</textarea>`)}
        ${field("Замеры по размерам", `<textarea class="input" id="f_size_chart" placeholder="M — длина 72, ширина 60&#10;L — длина 74, ширина 63">${esc(p.size_chart || "")}</textarea>`)}
      </div>
      ${header("Метка")}
      ${rseg([["", "Нет"], ["new", "New"], ["hit", "Хит"], ["soon", "Скоро"]], p.badge || "", "badgeSeg")}
      ${footer("«Скоро» — товар виден, но купить нельзя: покупатели жмут «Сообщить о поступлении» и получают сообщение, когда снимешь метку.")}
      ${header("Размеры и остатки")}
      <div class="group">
        ${p.sizes.map((s, i) => `<div class="cell">
          <input class="input" data-sz="${i}" value="${esc(s.size)}" placeholder="Размер" style="flex:1">
          <input class="input num" data-st="${i}" type="number" inputmode="numeric" min="0" value="${s.stock}" style="width:70px">
          <span style="color:var(--label-2);font-size:15px">шт</span>
          <button class="icon-btn" data-rmsz="${i}" aria-label="Удалить размер">${icon("xmark")}</button></div>`).join("")}
        <button class="cell tap" id="addSize"><span class="link">Добавить размер</span></button>
        <button class="cell tap" id="oneSize"><span class="link">Сделать One size</span></button>
      </div>
      ${footer(existing ? "Поступление лучше оформлять в «Склад» → «Оприходовать»: там сохраняется цена закупки и считается прибыль." : "Начальные остатки запишутся в журнал склада как приход.")}
      ${header("Публикация")}
      <div class="group">
        ${switchRow("f_active", "Показывать в каталоге", p.is_active)}
        <div class="cell"><span class="grow"><span class="title">Порядок</span><div class="sub">меньше — выше в каталоге</div></span>${numEl("f_sort", p.sort, "")}</div>
      </div>
      ${existing ? `<div class="stack"><button class="btn red" id="delete">Удалить товар</button></div>` : ""}`;

    FX.rubberSegment(document.getElementById("badgeSeg"), (v) => (p.badge = v || null));
    $view.querySelectorAll("[data-rmph]").forEach((b) => (b.onclick = () => (sync(), p.photos.splice(+b.dataset.rmph, 1), draw())));
    $view.querySelectorAll("[data-rmsz]").forEach((b) => (b.onclick = () => (sync(), p.sizes.splice(+b.dataset.rmsz, 1), draw())));
    document.getElementById("addSize").onclick = () => (sync(), p.sizes.push({ size: "", stock: 0 }), draw());
    document.getElementById("oneSize").onclick = () => (sync(), (p.sizes = [{ size: "One size", stock: p.sizes.reduce((s, x) => s + x.stock, 0) }]), draw());
    const add = document.getElementById("addPhoto");
    if (add) add.onclick = async () => {
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
    if (del) del.onclick = async () => {
      if (!(await confirmDialog(`Удалить «${p.title}»? Старые заказы останутся.`))) return;
      await action(api(`/api/admin/products/${id}`, { method: "DELETE" }), "Товар удалён");
      state.products = [];
      adminProductsCache = [];
      back();
    };
    setBar(`<button class="btn" id="save">Сохранить</button>`).querySelector("#save").onclick = async () => {
      sync();
      try {
        await action(api(existing ? `/api/admin/products/${id}` : "/api/admin/products", { method: existing ? "PUT" : "POST", body: p }), "Сохранено");
        state.products = [];
        adminProductsCache = [];
        back();
      } catch (_) {}
    };
  };
  draw();
};

// ---------- склад ----------

const KIND_ICON = { receipt: ["arrowDown", "c-green"], sale: ["bag", "c-blue"], return: ["arrowBack", "c-orange"], writeoff: ["trash", "c-red"], inventory: ["doc", "c-purple"], adjust: ["pencil", "c-gray"] };
let stockCache = null;

function movementRow(m) {
  const [ico, color] = KIND_ICON[m.kind] || KIND_ICON.adjust;
  const extra = [m.note, m.cost != null ? `${money(m.cost)}/шт` : ""].filter(Boolean).join(" · ");
  return `<div class="cell has-ico">
    <div class="lead-ico ${color}">${icon(ico)}</div>
    <div class="grow"><div class="title" style="font-size:15px">${esc(m.product_title)} · ${esc(m.size)}</div>
    <div class="sub" style="font-size:12px">${esc(m.kind_label)} · ${fmtDate(m.created_at)}${extra ? ` · ${esc(extra)}` : ""}</div></div>
    <span class="delta ${m.delta > 0 ? "plus" : "minus"}">${m.delta > 0 ? "+" : ""}${m.delta}</span>
  </div>`;
}

screens.adminStock = async () => {
  $view.innerHTML = loaderHtml();
  const d = (stockCache = await api("/api/admin/stock"));
  $view.innerHTML = `
    <div class="tiles">
      <div class="tile"><b data-count="${d.units}">0</b><span>${plural(d.units, "единица", "единицы", "единиц")} на складе</span></div>
      <div class="tile"><b style="font-size:18px">${money(d.stock_value)}</b><span>в товаре по закупке</span></div>
    </div>
    <div class="stack" style="margin-top:14px">
      <button class="btn" data-mode="receipt">${icon("tray")} Оприходовать</button>
      <div class="btn-row"><button class="btn glass" data-mode="writeoff">${icon("trash")} Списать</button><button class="btn glass" data-mode="inventory">${icon("doc")} Инвентаризация</button></div>
    </div>
    ${footer("Приход — пришла партия. Списание — брак, подарок, вещь для съёмки. Инвентаризация — вводишь, сколько реально лежит, разница запишется сама.")}
    ${header("Остатки")}
    ${d.products.length ? `<div class="group">${d.products.map((p) => `<div class="cell has-thumb">
      <div class="thumb">${photoHtml(p.photos[0])}</div>
      <div class="grow"><div class="title">${esc(p.title)}</div>
      <div class="size-chips">${p.sizes.map((s) => `<span class="${s.stock <= d.low_stock ? "zero" : ""}">${esc(s.size)} ${s.stock}</span>`).join("")}</div></div>
      <span class="value">${stockOf(p)} шт</span></div>`).join("")}</div>`
      : `<div class="group"><div class="cell"><span class="sub" style="margin:0">Сначала добавь товар во вкладке «Товары»</span></div></div>`}
    ${header("Журнал движений")}
    ${d.movements.length ? `<div class="group">${d.movements.slice(0, 60).map(movementRow).join("")}</div>` : `<div class="group"><div class="cell"><span class="sub" style="margin:0">Пока пусто</span></div></div>`}`;
  $view.querySelectorAll("[data-count]").forEach((el) => FX.countUp(el, +el.dataset.count));
  const names = { receipt: "Приход", writeoff: "Списание", inventory: "Инвентаризация" };
  $view.querySelectorAll("[data-mode]").forEach((b) => (b.onclick = () =>
    d.products.length ? sub("stockPick", { mode: b.dataset.mode, title: names[b.dataset.mode] }) : toast("Сначала добавь товар", true)));
};

screens.stockPick = async ({ mode }) => {
  if (!stockCache) stockCache = await api("/api/admin/stock");
  $view.innerHTML = `${header("Выбери товар")}<div class="group">${stockCache.products.map((p) => `
    <button class="cell tap has-thumb" data-id="${p.id}"><div class="thumb">${photoHtml(p.photos[0])}</div>
    <div class="grow"><div class="title">${esc(p.title)}</div><div class="sub">Сейчас ${stockOf(p)} шт</div></div>${chev()}</button>`).join("")}</div>`;
  const names = { receipt: "Приход", writeoff: "Списание", inventory: "Инвентаризация" };
  $view.querySelectorAll("[data-id]").forEach((b) => (b.onclick = () => sub("stockForm", { mode, id: +b.dataset.id, title: names[mode] })));
};

screens.stockForm = async ({ mode, id }) => {
  if (!stockCache) stockCache = await api("/api/admin/stock");
  const p = stockCache.products.find((x) => x.id === id);
  if (!p) throw new Error("Товар не найден");
  const rows = p.sizes.map((s) => ({ size: s.size, current: s.stock, qty: mode === "inventory" ? s.stock : "" }));
  const sign = { receipt: "+", writeoff: "−", inventory: "=" }[mode];
  const draw = () => {
    $view.innerHTML = `
      <div class="group"><div class="cell has-thumb"><div class="thumb">${photoHtml(p.photos[0])}</div><div class="grow"><div class="title">${esc(p.title)}</div><div class="sub">Сейчас на складе ${stockOf(p)} шт</div></div></div></div>
      ${header({ receipt: "Сколько пришло", writeoff: "Сколько списать", inventory: "Сколько реально лежит" }[mode])}
      <div class="group">
        ${rows.map((r, i) => `<div class="cell">
          ${r.current == null ? `<input class="input" data-size="${i}" value="${esc(r.size)}" placeholder="Новый размер" style="flex:1">` : `<span class="grow title">${esc(r.size)} <span style="color:var(--label-2);font-size:15px">· есть ${r.current}</span></span>`}
          <span style="color:${mode === "writeoff" ? "var(--red)" : "var(--green)"};font-weight:700">${sign}</span>
          <input class="input num" data-qty="${i}" type="number" inputmode="numeric" min="0" placeholder="0" value="${esc(r.qty)}" style="width:70px">
          <span style="color:var(--label-2);font-size:15px">шт</span></div>`).join("")}
        ${mode === "receipt" ? `<button class="cell tap" id="newSize"><span class="link">Новый размер</span></button>` : ""}
      </div>
      ${mode === "receipt" ? `${header("Закупка")}<div class="group">
        <div class="cell"><span class="grow title">Цена за 1 шт</span>${numEl("cost", "", 'placeholder="0" style="width:120px"')}<span style="color:var(--label-2)">${esc(state.settings.currency)}</span></div>
        <div class="cell"><input class="input" id="note" placeholder="Поставщик или комментарий"></div></div>
        ${footer("Цена закупки нужна, чтобы касса считала себестоимость и прибыль по каждому заказу.")}` : ""}
      ${mode === "writeoff" ? `${header("Причина")}<div class="pills" id="reasons">${["Брак", "Подарок", "Для съёмки", "Потеря"].map((r, i) => `<button class="pill ${i ? "" : "active"}" data-r="${r}">${r}</button>`).join("")}</div>` : ""}
      ${mode === "inventory" ? footer("Введи фактическое количество по каждому размеру. Разница с учётом запишется в журнал как инвентаризация.") : ""}
      <div class="group" style="margin-top:20px"><div class="cell total"><span class="title">Итого</span><span class="value" id="sum" style="flex:1"></span></div></div>`;
    const syncRows = () => rows.forEach((r, i) => {
      r.qty = $view.querySelector(`[data-qty="${i}"]`).value;
      const s = $view.querySelector(`[data-size="${i}"]`);
      if (s) r.size = s.value.trim();
    });
    const updateSum = () => {
      syncRows();
      const units = rows.reduce((s, r) => s + (+r.qty || 0), 0);
      const sumEl = document.getElementById("sum");
      if (mode === "inventory") {
        const diff = units - stockOf(p);
        sumEl.textContent = `${units} шт · ${diff > 0 ? "+" : ""}${diff} к учёту`;
      } else {
        const cost = +val("cost") || 0;
        sumEl.textContent = `${units} шт${cost ? ` · ${money(units * cost)}` : ""}`;
      }
    };
    $view.querySelectorAll("[data-qty], #cost").forEach((el) => (el.oninput = updateSum));
    const ns = document.getElementById("newSize");
    if (ns) ns.onclick = () => (syncRows(), rows.push({ size: "", current: null, qty: "" }), draw());
    let reason = "Брак";
    $view.querySelectorAll("[data-r]").forEach((b) => (b.onclick = () => {
      reason = b.dataset.r;
      $view.querySelectorAll("[data-r]").forEach((x) => x.classList.toggle("active", x === b));
    }));
    updateSum();
    const labels = { receipt: "Оприходовать", writeoff: "Списать", inventory: "Сохранить остатки" };
    setBar(`<button class="btn ${mode === "writeoff" ? "red" : ""}" id="save">${labels[mode]}</button>`).querySelector("#save").onclick = async () => {
      syncRows();
      let req;
      if (mode === "inventory") {
        req = { path: "/api/admin/stock/inventory", body: { product_id: p.id, sizes: rows.map((r) => ({ size: r.size, stock: +r.qty || 0 })) } };
      } else {
        const items = rows.filter((r) => r.size && +r.qty > 0).map((r) => ({ size: r.size, qty: +r.qty }));
        if (!items.length) return toast("Укажи количество хотя бы по одному размеру", true);
        req = mode === "receipt"
          ? { path: "/api/admin/stock/receipt", body: { product_id: p.id, items, cost: val("cost"), note: val("note") || "Приход товара" } }
          : { path: "/api/admin/stock/writeoff", body: { product_id: p.id, items, reason } };
      }
      try {
        await action(api(req.path, { method: "POST", body: req.body }), "Склад обновлён");
        state.products = [];
        stockCache = null;
        state.stacks.admin = [{ name: "admin" }, { name: "adminStock", params: { title: "Склад" } }];
        render();
      } catch (_) {}
    };
  };
  draw();
};

// ---------- касса ----------

let financePeriod = "month";
screens.adminFinance = async () => {
  $view.innerHTML = loaderHtml();
  const f = await api(`/api/admin/finance?period=${financePeriod}`);
  const maxCh = Math.max(1, ...f.channels.map((c) => c.amount));
  $view.innerHTML = `
    ${rseg([["today", "Сегодня"], ["week", "7 дней"], ["month", "30 дней"], ["all", "Всё"]], financePeriod, "period")}
    <div class="bento" style="margin-top:10px">
      <div class="bento-card"><div class="b-label">Выручка</div><div class="b-num sm" data-money="${f.revenue}">0</div></div>
      <div class="bento-card"><div class="b-label">Прибыль</div><div class="b-num sm" data-money="${f.profit}" style="color:${f.profit >= 0 ? "var(--green)" : "var(--red)"}">0</div></div>
      <div class="bento-card"><div class="b-label">Оплачено заказов</div><div class="b-num">${f.orders}</div></div>
      <div class="bento-card"><div class="b-label">Средний чек</div><div class="b-num sm">${money(f.avg_check)}</div></div>
    </div>
    ${header("Куда пришли деньги")}
    <div class="group">${f.channels.length ? `<div class="bars">${f.channels.map((c) => `<div class="b-row"><span>${esc(c.label)}</span><b>${money(c.amount)}</b><div class="b-track"><div class="b-fill" style="width:${(c.amount / maxCh) * 100}%"></div></div></div>`).join("")}</div>` : `<div class="cell"><span class="sub" style="margin:0">За период оплат не было</span></div>`}</div>
    ${header("Как считается прибыль")}
    <div class="group">
      ${kv("Выручка", money(f.revenue))}
      ${kv("− доставка (уходит курьеру)", money(f.delivery))}
      ${kv("− себестоимость проданного", money(f.cogs))}
      ${kv("− расходы", money(f.expenses))}
      <div class="cell total"><span class="title">Прибыль</span><span class="value" style="flex:1">${money(f.profit)}</span></div>
    </div>
    ${f.unknown_cost_orders ? footer(`В ${f.unknown_cost_orders} ${plural(f.unknown_cost_orders, "заказе", "заказах", "заказах")} есть вещи без цены закупки — их себестоимость посчитана как 0. Указывай цену при оприходовании.`) : ""}
    ${header("Деньги в товаре")}
    <div class="group">${kv("Закуплено за период", money(f.purchases))}${kv("Лежит на складе по закупке", money(f.stock_value))}</div>
    ${header("Расходы", `<button class="link" id="addExp">Добавить</button>`)}
    <div id="expForm"></div>
    <div class="group">${f.expense_list.length ? f.expense_list.map((e) => `
      <div class="cell"><div class="grow"><div class="title" style="font-size:15px">${esc(e.label)}${e.note ? ` · ${esc(e.note)}` : ""}</div><div class="sub" style="font-size:12px">${fmtDate(e.created_at)}${e.admin_name ? " · " + esc(e.admin_name) : ""}</div></div>
      <span class="delta minus">−${money(e.amount)}</span><button class="icon-btn" data-delexp="${e.id}" aria-label="Удалить">${icon("xmark")}</button></div>`).join("") : `<div class="cell"><span class="sub" style="margin:0">Расходов за период нет</span></div>`}</div>
    <div class="stack"><button class="btn glass" id="exportFin">${icon("download")} Выгрузить кассу в Excel</button></div>`;
  FX.rubberSegment(document.getElementById("period"), (v) => ((financePeriod = v), setTimeout(render, 360)));
  $view.querySelectorAll("[data-money]").forEach((el) => FX.countUp(el, +el.dataset.money, { format: (n) => money(n) }));
  document.getElementById("exportFin").onclick = () => action(api("/api/admin/export", { method: "POST", body: { kind: "finance" } }), "Файл отправлен тебе в чат с ботом").catch(() => {});
  $view.querySelectorAll("[data-delexp]").forEach((b) => (b.onclick = async () => {
    if (!(await confirmDialog("Удалить расход?"))) return;
    action(api(`/api/admin/expenses/${b.dataset.delexp}`, { method: "DELETE" }), "Удалено").then(render, () => {});
  }));
  document.getElementById("addExp").onclick = () => {
    let kind = "ads";
    document.getElementById("expForm").innerHTML = `
      <div class="pills">${Object.entries(f.kinds).map(([k, l]) => `<button class="pill ${k === kind ? "active" : ""}" data-k="${k}">${esc(l)}</button>`).join("")}</div>
      <div class="group" style="margin-bottom:12px">
        <div class="cell"><span class="grow title">Сумма</span>${numEl("expAmount", "", 'placeholder="0" style="width:130px"')}</div>
        <div class="cell"><input class="input" id="expNote" placeholder="Комментарий: таргет, такси, пакеты…"></div>
        <button class="cell tap" id="expSave"><span class="grow link">Сохранить расход</span></button>
      </div>`;
    document.querySelectorAll("[data-k]").forEach((b) => (b.onclick = () => {
      kind = b.dataset.k;
      document.querySelectorAll("[data-k]").forEach((x) => x.classList.toggle("active", x === b));
    }));
    document.getElementById("expAmount").focus();
    document.getElementById("expSave").onclick = () =>
      action(api("/api/admin/expenses", { method: "POST", body: { kind, amount: val("expAmount"), note: val("expNote") } }), "Расход добавлен").then(render, () => {});
  };
};

// ---------- покупатели ----------

let customerQuery = "";
screens.adminCustomers = async () => {
  $view.innerHTML = `<div class="group" style="margin-top:6px"><div class="cell">${icon("search")}<input class="input" id="cq" placeholder="Имя, @username или телефон" value="${esc(customerQuery)}"></div></div><div id="clist">${loaderHtml()}</div>`;
  const load = async () => {
    const list = await api(`/api/admin/customers?q=${encodeURIComponent(customerQuery)}`);
    document.getElementById("clist").innerHTML = list.length ? `${header(`${list.length} ${plural(list.length, "покупатель", "покупателя", "покупателей")}`)}<div class="group">${list.map((u) => `
      <button class="cell tap has-ico" data-id="${u.id}">
        ${FX.glassIcon(icon("user"), u.registered ? "purple" : "gray")}
        <div class="grow"><div class="title">${esc(u.full_name || u.first_name || "Без имени")}${u.no_cash ? ' <span style="color:var(--red);font-size:12px">не выкупал</span>' : ""}</div>
        <div class="sub">${u.username ? "@" + esc(u.username) + " · " : ""}${esc(u.phone || "")}${u.registered ? ` · ${num(u.points)} б.` : ""}</div></div>
        <span class="value">${u.orders ? `${money(u.spent)}<div class="sub" style="font-size:12px">${u.orders} ${plural(u.orders, "заказ", "заказа", "заказов")}</div>` : ""}</span>${chev()}
      </button>`).join("")}</div>` : emptyHtml("users", "Никого не нашли", "");
    document.querySelectorAll("#clist [data-id]").forEach((b) => (b.onclick = () => sub("adminCustomer", { id: +b.dataset.id, title: "Покупатель" })));
  };
  document.getElementById("cq").oninput = debounce((e) => ((customerQuery = e.target.value), load()), 350);
  load();
};

screens.adminCustomer = async ({ id }) => {
  $view.innerHTML = loaderHtml();
  const u = await api(`/api/admin/customers/${id}`);
  $view.innerHTML = `
    ${title(u.full_name || u.first_name || "Покупатель")}
    <div class="subtitle">${u.username ? "@" + esc(u.username) + " · " : ""}${esc(u.phone || "")} · ${u.registered ? "в бонусной программе" : "без регистрации"}</div>
    <div class="tiles">
      <div class="tile"><b>${money(u.spent)}</b><span>потратил</span></div>
      <div class="tile"><b>${u.orders}</b><span>${plural(u.orders, "заказ", "заказа", "заказов")}${u.cancelled ? ` · ${u.cancelled} отмен` : ""}</span></div>
    </div>
    ${header("Заметки и ограничения")}
    <div class="group">
      ${field("Заметка о покупателе", `<textarea class="input" id="note" placeholder="Например: берёт оверсайз, всегда самовывоз">${esc(u.note || "")}</textarea>`)}
      ${switchRow("noCash", "Не выкупал — только предоплата", u.no_cash, "наличные и курьер с оплатой при получении недоступны")}
      <button class="cell tap" id="saveCust"><span class="grow link">Сохранить</span></button>
    </div>
    ${u.registered ? `${header(`Баллы · ${num(u.points)}`)}
    <div class="group">
      <div class="cell"><span class="grow title">Начислить / списать</span>${`<input class="input num" id="ptsDelta" type="number" inputmode="numeric" placeholder="+5000 или -2000">`}</div>
      <div class="cell"><input class="input" id="ptsReason" placeholder="Причина — её увидит покупатель"></div>
      <button class="cell tap" id="ptsSave"><span class="grow link">Применить</span></button>
    </div>
    ${u.history.length ? `<div class="group" style="margin-top:12px">${u.history.slice(0, 10).map((t) => `<div class="cell"><div class="grow"><div class="title" style="font-size:15px">${esc(t.reason)}</div><div class="sub" style="font-size:12px">${fmtDate(t.created_at)}${t.admin_name ? " · " + esc(t.admin_name) : ""}</div></div><span class="delta ${t.delta > 0 ? "plus" : "minus"}">${t.delta > 0 ? "+" : ""}${num(t.delta)}</span></div>`).join("")}</div>` : ""}` : ""}
    ${header("Заказы")}
    ${u.orders_list.length ? `<div class="group">${u.orders_list.map((o) => orderRow(o, true)).join("")}</div>` : `<div class="group"><div class="cell"><span class="sub" style="margin:0">Заказов нет</span></div></div>`}
    ${u.username ? `<div class="stack"><button class="btn glass" id="write">${icon("bubble")} Написать в Telegram</button></div>` : ""}`;
  document.getElementById("saveCust").onclick = () => action(api(`/api/admin/customers/${id}`, { method: "PUT", body: { note: val("note"), no_cash: checked("noCash") } }), "Сохранено").catch(() => {});
  const ps = document.getElementById("ptsSave");
  if (ps) ps.onclick = () => action(api(`/api/admin/customers/${id}/points`, { method: "POST", body: { delta: val("ptsDelta"), reason: val("ptsReason") } }), "Баллы обновлены, покупатель получил сообщение").then(render, () => {});
  const w = document.getElementById("write");
  if (w) w.onclick = () => openLink(`https://t.me/${u.username}`);
  $view.querySelectorAll("[data-id]").forEach((b) => (b.onclick = () => sub("adminOrder", { id: +b.dataset.id, title: `Заказ #${b.dataset.id}` })));
};

// ---------- маркетинг: промокоды, награды, баллы ----------

let marketingTab = "coupons";
let marketingCache = null;
screens.adminMarketing = async () => {
  $view.innerHTML = loaderHtml();
  const m = (marketingCache = await api("/api/admin/coupons"));
  if (!adminProductsCache.length) adminProductsCache = await api("/api/admin/products");
  const body = {
    coupons: () => `
      <button class="btn" id="newCoupon" style="margin:12px 0 4px">${icon("plus")} Новый промокод</button>
      ${footer("Промокод покупатель вводит при оформлении. Можно сделать скидку в процентах, суммой или вещь в подарок.")}
      ${m.coupons.length ? `<div class="group" style="margin-top:14px">${m.coupons.map((c) => `
        <button class="cell tap coupon ${c.is_active && !c.spent ? "" : "spent"}" data-coupon="${c.id}">${FX.glassIcon(icon("ticket"), "teal")}
          <div class="grow"><div class="code">${esc(c.code)}</div><div class="sub">${esc(c.label)}${c.min_total ? ` · от ${money(c.min_total)}` : ""} · использован ${c.used_count}${c.max_uses ? "/" + c.max_uses : ""}${c.expires_at ? " · до " + new Date(c.expires_at).toLocaleDateString("ru-RU") : ""}</div></div>${chev()}
        </button>`).join("")}</div>` : ""}`,
    rewards: () => `
      <button class="btn" id="newReward" style="margin:12px 0 4px">${icon("plus")} Новая награда</button>
      ${footer(`Награды покупатели получают за баллы: после обмена им приходит личный одноразовый купон. Уже выдано купонов: ${m.reward_coupons_issued}.`)}
      ${m.rewards.length ? `<div class="group" style="margin-top:14px">${m.rewards.map((r) => `
        <button class="cell tap has-ico" data-reward="${r.id}">${FX.glassIcon(icon(r.kind === "gift" ? "gift" : "ticket"), r.kind === "gift" ? "orange" : "purple")}
          <div class="grow"><div class="title">${esc(r.title)}${r.is_active ? "" : ' <span class="sub">· выключена</span>'}</div><div class="sub">${esc(r.label)}</div></div>
          <span class="value">${num(r.cost)} б.</span>${chev()}</button>`).join("")}</div>` : ""}`,
    points: () => `
      ${header("Бонус всем зарегистрированным")}
      <div class="group">
        <div class="cell"><span class="grow title">Сколько баллов</span>${numEl("campAmount", "", 'placeholder="5000" style="width:120px"')}</div>
        <div class="cell"><input class="input" id="campReason" placeholder="Причина — например «Новый дроп»"></div>
        <button class="cell tap" id="campSend"><span class="grow link">Начислить всем</span></button>
      </div>
      ${footer("Каждый получит сообщение в бота. Начислить баллы одному покупателю можно в его карточке («Покупатели»).")}
      ${header("Правила программы")}
      <div class="group">${kv("Баллы с заказа", `${state.settings.earn_percent}%`)}${kv("За регистрацию", num(state.settings.welcome_points))}${kv("Программа", state.settings.loyalty_enabled ? "включена" : "выключена")}
        <button class="cell tap" id="toSettings"><span class="grow link">Изменить в настройках</span>${chev()}</button></div>`,
  };
  $view.innerHTML = rseg([["coupons", "Промокоды"], ["rewards", "Награды"], ["points", "Баллы"]], marketingTab, "mseg") + body[marketingTab]();
  FX.rubberSegment(document.getElementById("mseg"), (v) => ((marketingTab = v), setTimeout(render, 360)));
  const nc = document.getElementById("newCoupon");
  if (nc) nc.onclick = () => sub("couponForm", { title: "Промокод" });
  const nr = document.getElementById("newReward");
  if (nr) nr.onclick = () => sub("rewardForm", { title: "Награда" });
  $view.querySelectorAll("[data-coupon]").forEach((b) => (b.onclick = () => sub("couponForm", { id: +b.dataset.coupon, title: "Промокод" })));
  $view.querySelectorAll("[data-reward]").forEach((b) => (b.onclick = () => sub("rewardForm", { id: +b.dataset.reward, title: "Награда" })));
  const cs = document.getElementById("campSend");
  if (cs) cs.onclick = async () => {
    const amount = +val("campAmount");
    if (!amount) return toast("Укажи, сколько баллов начислить", true);
    if (!(await confirmDialog(`Начислить ${num(amount)} баллов всем зарегистрированным?`))) return;
    action(api("/api/admin/points/campaign", { method: "POST", body: { amount, reason: val("campReason") } })).then((r) => toast(`Начислено ${r.users} покупателям`), () => {});
  };
  const ts = document.getElementById("toSettings");
  if (ts) ts.onclick = () => sub("adminSettings", { title: "Настройки" });
};

function discountFields(item) {
  return `
    ${rseg([["percent", "Процент"], ["amount", "Сумма"], ["gift", "Подарок"]], item.kind, "kindSeg")}
    <div class="group" id="kindFields" style="margin-top:8px"></div>`;
}

function bindDiscountFields(item) {
  const box = document.getElementById("kindFields");
  const drawKind = () => {
    box.innerHTML = item.kind === "gift"
      ? field("Какая вещь в подарок", `<select class="input" id="f_product">${adminProductsCache.map((p) => `<option value="${p.id}" ${p.id === item.product_id ? "selected" : ""}>${esc(p.title)} · ${money(p.price)}</option>`).join("")}</select>`) +
        `<div class="cell"><span class="sub" style="margin:0">Одна единица этой вещи в корзине станет бесплатной</span></div>`
      : `<div class="cell"><span class="grow title">${item.kind === "percent" ? "Скидка, %" : `Скидка, ${esc(state.settings.currency)}`}</span>${numEl("f_value", item.value || "", 'placeholder="0" style="width:120px"')}</div>`;
  };
  FX.rubberSegment(document.getElementById("kindSeg"), (v) => {
    item.kind = v;
    drawKind();
  });
  drawKind();
  return () => ({ kind: item.kind, value: val("f_value"), product_id: val("f_product") });
}

screens.couponForm = async ({ id }) => {
  if (!marketingCache) marketingCache = await api("/api/admin/coupons");
  if (!adminProductsCache.length) adminProductsCache = await api("/api/admin/products");
  const c = marketingCache.coupons.find((x) => x.id === id) || { code: "", title: "", kind: "percent", value: 10, min_total: 0, max_uses: "", once_per_user: true, expires_at: null, is_active: true };
  $view.innerHTML = `
    ${header("Код")}
    <div class="group">
      ${field("Промокод (латиница и цифры)", inputEl("f_code", c.code, `placeholder="Пусто — сгенерирую сам" autocapitalize="characters" ${id ? "disabled" : ""}`))}
      ${field("Описание для себя", inputEl("f_title", c.title, 'placeholder="Например: для блогера Азизы"'))}
    </div>
    ${header("Скидка")}
    ${discountFields(c)}
    ${header("Условия")}
    <div class="group">
      <div class="cell"><span class="grow title">Минимальная сумма</span>${numEl("f_min", c.min_total || "", 'placeholder="0" style="width:120px"')}</div>
      <div class="cell"><span class="grow"><span class="title">Всего использований</span><div class="sub">пусто — без лимита</div></span>${numEl("f_max", c.max_uses || "", 'placeholder="∞"')}</div>
      ${switchRow("f_once", "Один раз на покупателя", c.once_per_user)}
      ${field("Действует до", `<input class="input" id="f_exp" type="date" value="${c.expires_at ? c.expires_at.slice(0, 10) : ""}">`)}
      ${switchRow("f_active", "Активен", c.is_active)}
    </div>
    ${id ? `<div class="stack"><button class="btn red" id="delete">Удалить промокод</button></div>` : ""}`;
  const getKind = bindDiscountFields(c);
  const del = document.getElementById("delete");
  if (del) del.onclick = async () => {
    if (!(await confirmDialog(`Удалить промокод ${c.code}?`))) return;
    action(api(`/api/admin/coupons/${id}`, { method: "DELETE" }), "Удалено").then(back, () => {});
  };
  setBar(`<button class="btn" id="save">Сохранить</button>`).querySelector("#save").onclick = () => {
    const body = { code: val("f_code"), title: val("f_title"), ...getKind(), min_total: val("f_min"), max_uses: val("f_max"), once_per_user: checked("f_once"), expires_at: val("f_exp"), is_active: checked("f_active") };
    action(api(id ? `/api/admin/coupons/${id}` : "/api/admin/coupons", { method: id ? "PUT" : "POST", body }))
      .then((r) => (toast(`Промокод ${r.code} сохранён`), back()), () => {});
  };
};

screens.rewardForm = async ({ id }) => {
  if (!marketingCache) marketingCache = await api("/api/admin/coupons");
  if (!adminProductsCache.length) adminProductsCache = await api("/api/admin/products");
  const r = marketingCache.rewards.find((x) => x.id === id) || { title: "", kind: "amount", value: 50000, cost: 20000, is_active: true, sort: 0 };
  $view.innerHTML = `
    ${header("Награда")}
    <div class="group">
      ${field("Название (видят покупатели)", inputEl("f_title", r.title, 'placeholder="Скидка 50 000 сум"'))}
      <div class="cell"><span class="grow title">Цена в баллах</span>${numEl("f_cost", r.cost, 'style="width:120px"')}</div>
    </div>
    ${header("Что получит покупатель")}
    ${discountFields(r)}
    ${header("Показ")}
    <div class="group">${switchRow("f_active", "Доступна для обмена", r.is_active)}<div class="cell"><span class="grow title">Порядок</span>${numEl("f_sort", r.sort)}</div></div>
    ${id ? `<div class="stack"><button class="btn red" id="delete">Удалить награду</button></div>` : ""}`;
  const getKind = bindDiscountFields(r);
  const del = document.getElementById("delete");
  if (del) del.onclick = async () => {
    if (!(await confirmDialog("Удалить награду? Уже выданные купоны продолжат работать."))) return;
    action(api(`/api/admin/rewards/${id}`, { method: "DELETE" }), "Удалено").then(back, () => {});
  };
  setBar(`<button class="btn" id="save">Сохранить</button>`).querySelector("#save").onclick = () => {
    const body = { title: val("f_title"), cost: val("f_cost"), ...getKind(), is_active: checked("f_active"), sort: val("f_sort") };
    action(api(id ? `/api/admin/rewards/${id}` : "/api/admin/rewards", { method: id ? "PUT" : "POST", body }), "Награда сохранена").then(back, () => {});
  };
};

// ---------- рассылка ----------

screens.adminBroadcast = async () => {
  const draft = loadJSON("dayz_broadcast", { text: "", photo: null, audience: "all", button: true });
  const draw = () => {
    $view.innerHTML = `
      ${header("Сообщение")}
      <div class="group">
        ${field("Текст", `<textarea class="input" id="bText" rows="5" placeholder="🔥 Новый дроп уже в магазине! Худи DAYZ Black — всего 20 штук">${esc(draft.text)}</textarea>`)}
        <div class="photos" style="grid-template-columns:repeat(4,1fr)">
          ${draft.photo ? `<div><img src="${photoUrl(draft.photo)}" alt=""><button class="rm" id="rmPhoto" aria-label="Убрать">${icon("xmark")}</button></div>` : `<button class="add" id="addPhoto" aria-label="Фото">${icon("photo")}</button>`}
        </div>
        ${switchRow("bButton", "Кнопка «Смотреть в магазине»", draft.button)}
      </div>
      ${header("Кому")}
      ${rseg([["all", "Всем"], ["registered", "Только в бонусной программе"]], draft.audience, "aud")}
      ${footer("Сообщение придёт в чат с ботом. Отправка идёт с паузами, чтобы Telegram не ограничил бота, — по окончании бот напишет, скольким доставлено.")}`;
    const save = () => {
      draft.text = val("bText");
      draft.button = checked("bButton");
      saveJSON("dayz_broadcast", draft);
    };
    document.getElementById("bText").oninput = save;
    document.getElementById("bButton").onchange = save;
    FX.rubberSegment(document.getElementById("aud"), (v) => ((draft.audience = v), save()));
    const ap = document.getElementById("addPhoto");
    if (ap) ap.onclick = async () => {
      save();
      const [file] = await pickFile("image/*");
      if (!file) return;
      try {
        const { file_id } = await action(api("/api/admin/upload", { method: "POST", file: await compressImage(file) }));
        draft.photo = file_id;
        saveJSON("dayz_broadcast", draft);
        draw();
      } catch (_) {}
    };
    const rp = document.getElementById("rmPhoto");
    if (rp) rp.onclick = () => (save(), (draft.photo = null), saveJSON("dayz_broadcast", draft), draw());
  };
  draw();
  setBar(`<button class="btn" id="send">${icon("megaphone")} Отправить рассылку</button>`).querySelector("#send").onclick = async () => {
    draft.text = val("bText");
    draft.button = checked("bButton");
    if (!draft.text.trim()) return toast("Напиши текст рассылки", true);
    if (!(await confirmDialog(draft.audience === "all" ? "Отправить всем пользователям бота?" : "Отправить всем участникам бонусной программы?"))) return;
    action(api("/api/admin/broadcast", { method: "POST", body: draft })).then((r) => {
      toast(`Рассылка запущена: ${r.queued} получателей`);
      saveJSON("dayz_broadcast", { text: "", photo: null, audience: "all", button: true });
      back();
    }, () => {});
  };
};

// ---------- выгрузки ----------

screens.adminExport = async () => {
  const items = [
    ["orders", "Заказы", "все заказы со статусами, оплатой, прибылью", "box", "indigo"],
    ["stock", "Склад", "остатки и журнал движений", "tray", "orange"],
    ["finance", "Касса", "выручка, прибыль, расходы по периодам", "wallet", "green"],
    ["customers", "Покупатели", "контакты, заказы, баллы", "users", "pink"],
    ["all", "Всё одним файлом", "все листы сразу", "doc", "blue"],
    ["backup", "Резервная копия", "полная копия базы (zip)", "download", "gray"],
  ];
  $view.innerHTML = `
    <div class="group" style="margin-top:6px">${items.map(([k, t, s, ico, color]) => `
      <button class="cell tap has-ico" data-k="${k}">${FX.glassIcon(icon(ico), color)}<div class="grow"><div class="title">${t}</div><div class="sub">${s}</div></div>${icon("download", "chev")}</button>`).join("")}</div>
    ${footer("Файл придёт тебе в чат с ботом — так его удобно открыть или переслать. Резервная копия также приходит каждый вечер вместе с отчётом.")}`;
  $view.querySelectorAll("[data-k]").forEach((b) => (b.onclick = () => {
    toast("Готовлю файл…");
    action(api("/api/admin/export", { method: "POST", body: { kind: b.dataset.k } }), "Файл отправлен в чат с ботом").catch(() => {});
  }));
};

// ---------- настройки ----------

screens.adminSettings = async () => {
  $view.innerHTML = loaderHtml();
  const s = await api("/api/admin/settings");
  const draw = () => {
    $view.innerHTML = `
      ${header("Карты для переводов")}
      <div class="group">${s.cards.map((c, i) => `
        <div class="cell field">
          <div style="display:flex;gap:8px;align-items:center">${inputEl(`c_label_${i}`, c.label, 'placeholder="Uzcard · Карим" style="font-weight:600"')}<input type="checkbox" class="switch" id="c_active_${i}" ${c.active !== false ? "checked" : ""}><button class="icon-btn" data-rmcard="${i}" aria-label="Удалить">${icon("xmark")}</button></div>
          ${inputEl(`c_number_${i}`, c.number || c.details || "", 'placeholder="8600 0000 0000 0000" inputmode="numeric"')}
          <div style="display:flex;gap:8px">${inputEl(`c_holder_${i}`, c.holder, 'placeholder="Получатель"')}${inputEl(`c_bank_${i}`, c.bank, 'placeholder="Банк"')}</div>
        </div>`).join("")}
        <button class="cell tap" id="addCard"><span class="link">Добавить карту</span></button>
      </div>
      ${footer("Активные карты выдаются покупателям по очереди — выручка сама делится между вами. В кассе видно, сколько пришло на каждую.")}
      ${header("Доставка")}
      <div class="group">${s.delivery_methods.map((m, i) => `
        <div class="cell field">
          <div style="display:flex;gap:8px;align-items:center">${inputEl(`d_name_${i}`, m.name, 'placeholder="Название" style="font-weight:600"')}<button class="icon-btn" data-rmdel="${i}" aria-label="Удалить">${icon("xmark")}</button></div>
          <div style="display:flex;gap:10px;align-items:center"><span class="sub" style="margin:0;flex:none">Цена</span>${numEl(`d_price_${i}`, m.price, 'style="width:auto;flex:1;text-align:left"')}<span class="sub" style="margin:0;flex:none">Бесплатно от</span>${numEl(`d_free_${i}`, m.free_from || "", 'placeholder="—" style="width:auto;flex:1;text-align:left"')}</div>
          ${inputEl(`d_note_${i}`, m.note, 'placeholder="Подсказка: сроки, адрес самовывоза"')}
          <div style="display:flex;gap:16px;align-items:center;margin-top:4px">
            <label style="display:flex;gap:8px;align-items:center;font-size:15px"><input type="checkbox" class="switch" id="d_cash_${i}" ${m.cash ? "checked" : ""}>Наличные</label>
            <label style="display:flex;gap:8px;align-items:center;font-size:15px"><input type="checkbox" class="switch" id="d_addr_${i}" ${m.address ? "checked" : ""}>Нужен адрес</label>
          </div>
        </div>`).join("")}
        <button class="cell tap" id="addDel"><span class="link">Добавить способ доставки</span></button>
      </div>
      ${footer("Выключи «Наличные», если по этому способу берёте только предоплату (например, отправка в регионы).")}
      ${header("Оплата картой")}
      <div class="group">
        <div class="cell"><span class="grow"><span class="title">Напомнить об оплате через</span><div class="sub">часов после заказа</div></span>${numEl("remind_hours", s.remind_hours)}</div>
        <div class="cell"><span class="grow"><span class="title">Снять неоплаченный через</span><div class="sub">часов · 0 — не снимать</div></span>${numEl("cancel_hours", s.cancel_hours)}</div>
      </div>
      ${header("Бонусная программа")}
      <div class="group">
        ${switchRow("loyalty_enabled", "Баллы включены", s.loyalty_enabled)}
        <div class="cell"><span class="grow"><span class="title">Баллы с заказа</span><div class="sub">% от суммы товаров, 1 балл = 1 ${esc(s.currency)}</div></span>${numEl("earn_percent", s.earn_percent)}</div>
        <div class="cell"><span class="grow title">Бонус за регистрацию</span>${numEl("welcome_points", s.welcome_points)}</div>
      </div>
      ${header("Склад и отчёты")}
      <div class="group">
        <div class="cell"><span class="grow"><span class="title">Предупреждать, когда осталось</span><div class="sub">штук одного размера</div></span>${numEl("low_stock", s.low_stock)}</div>
        <div class="cell"><span class="grow"><span class="title">Вечерний отчёт и бэкап в</span><div class="sub">час по Ташкенту, 0–23</div></span>${numEl("report_hour", s.report_hour)}</div>
      </div>
      ${header("Магазин")}
      <div class="group">
        <div class="cell"><span class="grow title">Валюта</span><input class="input num" id="currency" value="${esc(s.currency)}"></div>
        ${field("О магазине", `<textarea class="input" id="about">${esc(s.about)}</textarea>`)}
      </div>`;
    $view.querySelectorAll("[data-rmcard]").forEach((b) => (b.onclick = () => (sync(), s.cards.splice(+b.dataset.rmcard, 1), draw())));
    $view.querySelectorAll("[data-rmdel]").forEach((b) => (b.onclick = () => (sync(), s.delivery_methods.splice(+b.dataset.rmdel, 1), draw())));
    document.getElementById("addCard").onclick = () => (sync(), s.cards.push({ label: "", number: "", holder: "", bank: "", active: true }), draw());
    document.getElementById("addDel").onclick = () => (sync(), s.delivery_methods.push({ name: "", price: 0, free_from: 0, cash: true, address: true, note: "" }), draw());
  };
  const sync = () => {
    s.cards = s.cards.map((c, i) => ({ label: val(`c_label_${i}`), number: val(`c_number_${i}`), holder: val(`c_holder_${i}`), bank: val(`c_bank_${i}`), active: checked(`c_active_${i}`), details: "" }));
    s.delivery_methods = s.delivery_methods.map((m, i) => ({ id: m.id, name: val(`d_name_${i}`), price: val(`d_price_${i}`), free_from: val(`d_free_${i}`), note: val(`d_note_${i}`), cash: checked(`d_cash_${i}`), address: checked(`d_addr_${i}`) }));
    ["remind_hours", "cancel_hours", "earn_percent", "welcome_points", "low_stock", "report_hour", "currency", "about"].forEach((k) => (s[k] = val(k)));
    s.loyalty_enabled = checked("loyalty_enabled");
  };
  draw();
  setBar(`<button class="btn" id="save">Сохранить настройки</button>`).querySelector("#save").onclick = async () => {
    sync();
    try {
      Object.assign(s, await action(api("/api/admin/settings", { method: "PUT", body: s }), "Настройки сохранены"));
      const boot = await api("/api/bootstrap");
      state.settings = boot.settings;
      draw();
    } catch (_) {}
  };
};

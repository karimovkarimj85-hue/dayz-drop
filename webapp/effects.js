/* Эффекты в духе React Bits (reactbits.dev), переписанные на чистый JS без React и сборки:
   Click Spark, Masked Heading, Rotating Text, Depth Carousel, Specular Button, Magic Bento,
   Spotlight Card, Pill Nav, Glass Icons, Bell Toggle, Code Slots, Rubber Segment, Pulse Heart,
   Peek Rating, Light Pillar, Count Up. */
"use strict";

const FX = (() => {
  const reduced = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const escHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const alive = (el) => el && document.body.contains(el);

  // ---------- Click Spark: искры от каждого касания ----------
  function clickSpark({ color = "#ffffff", count = 8, radius = 22, size = 9, duration = 420 } = {}) {
    const canvas = document.createElement("canvas");
    canvas.className = "fx-spark";
    document.body.appendChild(canvas);
    const ctx = canvas.getContext("2d");
    let sparks = [];
    let raf = null;
    const resize = () => {
      const d = window.devicePixelRatio || 1;
      canvas.width = innerWidth * d;
      canvas.height = innerHeight * d;
      ctx.setTransform(d, 0, 0, d, 0, 0);
    };
    resize();
    addEventListener("resize", resize);
    const draw = (t) => {
      ctx.clearRect(0, 0, innerWidth, innerHeight);
      sparks = sparks.filter((s) => {
        const p = (t - s.t) / duration;
        if (p >= 1) return false;
        const e = p * (2 - p);
        const dist = e * radius;
        const len = size * (1 - e);
        ctx.strokeStyle = color;
        ctx.globalAlpha = 1 - p;
        ctx.lineWidth = 2;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(s.x + dist * Math.cos(s.a), s.y + dist * Math.sin(s.a));
        ctx.lineTo(s.x + (dist + len) * Math.cos(s.a), s.y + (dist + len) * Math.sin(s.a));
        ctx.stroke();
        return true;
      });
      ctx.globalAlpha = 1;
      raf = sparks.length ? requestAnimationFrame(draw) : null;
    };
    addEventListener(
      "pointerdown",
      (e) => {
        if (reduced) return;
        const t = performance.now();
        for (let i = 0; i < count; i++) sparks.push({ x: e.clientX, y: e.clientY, a: (2 * Math.PI * i) / count + Math.random() * 0.3, t });
        if (!raf) raf = requestAnimationFrame(draw);
      },
      { passive: true }
    );
  }

  // ---------- Masked Heading: слова выезжают из-под маски, сквозь буквы плывёт цветной меш ----------
  function maskedHeading(text, cls = "") {
    const words = String(text).trim().split(/\s+/);
    return `<h1 class="mh ${cls}" aria-label="${escHtml(text)}">${words
      .map((w, i) => `<span class="mh-w" aria-hidden="true"><span style="animation-delay:${i * 90}ms,${i * 90}ms">${escHtml(w)}</span></span>`)
      .join(" ")}</h1>`;
  }

  // ---------- Rotating Text: слова сменяются с посимвольной анимацией ----------
  function rotatingText(el, words, interval = 2300) {
    if (!el || !words.length) return;
    let i = 0;
    const make = (word) => {
      const span = document.createElement("span");
      span.className = "rt-word";
      span.innerHTML = [...word].map((ch, k) => `<span class="rt-ch" style="transition-delay:${k * 22}ms">${ch === " " ? "&nbsp;" : escHtml(ch)}</span>`).join("");
      return span;
    };
    const first = make(words[0]);
    el.innerHTML = "";
    el.appendChild(first);
    requestAnimationFrame(() => {
      first.classList.add("rt-in");
      el.style.width = first.offsetWidth + 24 + "px";
    });
    if (words.length < 2 || reduced) return;
    const timer = setInterval(() => {
      if (!alive(el)) return clearInterval(timer);
      const old = el.querySelector(".rt-word:not(.rt-out)");
      i = (i + 1) % words.length;
      const next = make(words[i]);
      el.appendChild(next);
      el.style.width = next.offsetWidth + 24 + "px";
      requestAnimationFrame(() => {
        if (old) old.classList.add("rt-out");
        next.classList.add("rt-in");
      });
      setTimeout(() => old && old.remove(), 700);
    }, interval);
  }

  // ---------- Depth Carousel: карточки уходят в глубину на 3D-рельсе ----------
  function depthCarousel(root, { auto = 3800, onOpen } = {}) {
    const cards = [...root.querySelectorAll(".dc-card")];
    const dots = root.querySelector(".dc-dots");
    if (!cards.length) return;
    let active = 0;
    let pausedUntil = 0;
    if (dots) dots.innerHTML = cards.map(() => "<i></i>").join("");
    const layout = () => {
      cards.forEach((card, i) => {
        const d = i - active;
        const ad = Math.abs(d);
        card.style.transform = `translateX(${d * 56}%) translateZ(${-ad * 170}px) rotateY(${-d * 16}deg) scale(${1 - ad * 0.05})`;
        card.style.opacity = ad > 2 ? "0" : String(1 - ad * 0.3);
        card.style.zIndex = String(100 - ad);
        card.style.pointerEvents = ad > 2 ? "none" : "auto";
        card.classList.toggle("is-active", d === 0);
      });
      if (dots) [...dots.children].forEach((dot, i) => dot.classList.toggle("on", i === active));
    };
    const go = (i) => {
      active = (i + cards.length) % cards.length;
      layout();
    };
    let startX = null;
    root.addEventListener("pointerdown", (e) => {
      startX = e.clientX;
      pausedUntil = Date.now() + 7000;
    });
    root.addEventListener("pointerup", (e) => {
      if (startX === null) return;
      const dx = e.clientX - startX;
      startX = null;
      if (Math.abs(dx) > 35) return go(active + (dx < 0 ? 1 : -1));
      const card = e.target.closest(".dc-card");
      if (!card) return;
      const idx = cards.indexOf(card);
      if (idx === active) onOpen && onOpen(card.dataset.id);
      else go(idx);
    });
    root.addEventListener("pointercancel", () => (startX = null));
    layout();
    if (auto && cards.length > 1 && !reduced) {
      const timer = setInterval(() => {
        if (!alive(root)) return clearInterval(timer);
        if (Date.now() > pausedUntil && !document.hidden) go(active + 1);
      }, auto);
    }
  }

  // ---------- Specular / Spotlight / Magic Bento: свет следует за пальцем ----------
  function pointerLights() {
    const update = (e) => {
      const target = e.target.closest && e.target.closest(".btn, .spot, .bento-card");
      if (!target) return;
      const r = target.getBoundingClientRect();
      const x = ((e.clientX - r.left) / r.width) * 100;
      const y = ((e.clientY - r.top) / r.height) * 100;
      target.style.setProperty("--mx", x + "%");
      target.style.setProperty("--my", y + "%");
      target.style.setProperty("--ang", Math.atan2(e.clientY - (r.top + r.height / 2), e.clientX - (r.left + r.width / 2)) + "rad");
      if (target.classList.contains("bento-card") && e.pointerType === "mouse") {
        target.style.setProperty("--rx", ((50 - y) / 18).toFixed(2) + "deg");
        target.style.setProperty("--ry", ((x - 50) / 18).toFixed(2) + "deg");
      }
      target.classList.add("lit");
      clearTimeout(target._litTimer);
      target._litTimer = setTimeout(() => {
        target.classList.remove("lit");
        target.style.setProperty("--rx", "0deg");
        target.style.setProperty("--ry", "0deg");
      }, e.pointerType === "mouse" ? 1200 : 700);
    };
    addEventListener("pointermove", update, { passive: true });
    addEventListener("pointerdown", (e) => {
      update(e);
      const card = e.target.closest && e.target.closest(".bento-card");
      if (card && !reduced) bentoParticles(card, e);
    }, { passive: true });
  }

  function bentoParticles(card, e) {
    const r = card.getBoundingClientRect();
    for (let i = 0; i < 6; i++) {
      const p = document.createElement("i");
      p.className = "bento-particle";
      p.style.left = e.clientX - r.left + "px";
      p.style.top = e.clientY - r.top + "px";
      p.style.setProperty("--dx", (Math.random() - 0.5) * 120 + "px");
      p.style.setProperty("--dy", -30 - Math.random() * 70 + "px");
      card.appendChild(p);
      setTimeout(() => p.remove(), 900);
    }
  }

  // ---------- Pill Nav: плавающая таблетка-навигация с перетекающим индикатором ----------
  function pillNav(nav) {
    const ind = nav.querySelector(".pill-ind");
    const active = nav.querySelector("button.active");
    if (!ind || !active) return;
    const place = (instant) => {
      if (instant) ind.style.transition = "none";
      ind.style.width = active.offsetWidth + "px";
      ind.style.transform = `translateX(${active.offsetLeft}px)`;
      if (instant) requestAnimationFrame(() => (ind.style.transition = ""));
    };
    place(!nav.dataset.ready);
    nav.dataset.ready = "1";
  }

  // ---------- Glass Icons ----------
  function glassIcon(svg, color = "blue") {
    return `<span class="gi gi-${color}"><span class="gi-back"></span><span class="gi-front">${svg}</span></span>`;
  }

  // ---------- Bell Toggle: колокольчик звенит, подпись меняется, таблетка раскрывается ----------
  function bellToggle(btn, on, onToggle) {
    btn.classList.toggle("on", on);
    btn.addEventListener("click", async () => {
      const next = !btn.classList.contains("on");
      btn.classList.remove("ring");
      void btn.offsetWidth;
      btn.classList.add("ring");
      btn.classList.toggle("on", next);
      try {
        await onToggle(next);
      } catch (err) {
        btn.classList.toggle("on", !next);
      }
    });
  }

  // ---------- Code Slots: символы пружинят в свои ячейки ----------
  function codeSlots(root, { length = 6, onChange, onComplete } = {}) {
    const input = root.querySelector("input");
    const slotsEl = root.querySelector(".slots");
    const render = () => {
      const value = input.value;
      const n = Math.max(length, Math.min(12, value.length + (document.activeElement === input && value.length >= length ? 1 : 0)));
      const prev = slotsEl.children.length;
      if (prev !== n) slotsEl.innerHTML = Array.from({ length: n }, () => '<span class="slot"></span>').join("");
      [...slotsEl.children].forEach((slot, i) => {
        const ch = value[i] || "";
        if (slot.textContent !== ch) {
          slot.textContent = ch;
          if (ch) {
            slot.classList.remove("pop");
            void slot.offsetWidth;
            slot.classList.add("pop");
          }
        }
        slot.classList.toggle("filled", !!ch);
        slot.classList.toggle("caret", document.activeElement === input && i === Math.min(value.length, n - 1));
      });
    };
    input.addEventListener("input", () => {
      input.value = input.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 12);
      render();
      onChange && onChange(input.value);
      if (input.value.length === length && onComplete) onComplete(input.value);
    });
    input.addEventListener("focus", render);
    input.addEventListener("blur", render);
    render();
    return { set(v) { input.value = v || ""; render(); }, get: () => input.value };
  }

  // ---------- Rubber Segment: бегунок тянется через промежуток и шлёпается на место ----------
  function rubberSegment(root, onSelect) {
    const thumb = root.querySelector(".rseg-thumb");
    const buttons = [...root.querySelectorAll("button[data-v]")];
    const place = (btn, instant) => {
      thumb.style.transition = instant ? "none" : "";
      thumb.style.left = btn.offsetLeft + "px";
      thumb.style.width = btn.offsetWidth + "px";
      thumb.style.transform = "scaleY(1)";
    };
    const current = () => buttons.find((b) => b.classList.contains("active")) || buttons[0];
    requestAnimationFrame(() => place(current(), true));
    buttons.forEach((btn) =>
      btn.addEventListener("click", () => {
        const from = current();
        if (from === btn) return;
        buttons.forEach((b) => b.classList.toggle("active", b === btn));
        if (reduced) place(btn, false);
        else {
          const left = Math.min(from.offsetLeft, btn.offsetLeft);
          const right = Math.max(from.offsetLeft + from.offsetWidth, btn.offsetLeft + btn.offsetWidth);
          thumb.classList.add("stretch");
          thumb.style.left = left + "px";
          thumb.style.width = right - left + "px";
          thumb.style.transform = "scaleY(.82)";
          setTimeout(() => {
            thumb.classList.remove("stretch");
            place(btn, false);
          }, 170);
        }
        onSelect && onSelect(btn.dataset.v);
      })
    );
  }

  // ---------- Pulse Heart: сжимается в точку, меняет цвет и пульсирует, счётчик перещёлкивается ----------
  function pulseHeart(btn, { liked, count = 0, onToggle } = {}) {
    const countEl = btn.querySelector(".heart-count");
    btn.classList.toggle("liked", !!liked);
    const setCount = (n, dir) => {
      if (!countEl) return;
      countEl.innerHTML = `<span class="hc-old">${countEl.textContent}</span><span class="hc-new ${dir}">${n || ""}</span>`;
      setTimeout(() => (countEl.textContent = n || ""), 320);
    };
    if (countEl) countEl.textContent = count || "";
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const next = !btn.classList.contains("liked");
      btn.classList.remove("pulse");
      btn.classList.add("contract");
      setTimeout(() => {
        btn.classList.remove("contract");
        btn.classList.toggle("liked", next);
        btn.classList.add("pulse");
      }, 140);
      try {
        const res = await onToggle(next);
        if (res && typeof res.likes === "number") setCount(res.likes, next ? "up" : "down");
      } catch (err) {
        btn.classList.toggle("liked", !next);
      }
    });
  }

  // ---------- Peek Rating: волна звёзд поднимается к пальцу, клик — с «попом» ----------
  function peekRating(root, { value = 0, onChange } = {}) {
    const stars = [...root.querySelectorAll(".star")];
    let committed = value;
    const paint = (n, lift) =>
      stars.forEach((s, i) => {
        s.classList.toggle("on", i < n);
        s.classList.toggle("lift", !!lift && i < n);
        s.style.transitionDelay = lift ? i * 35 + "ms" : "0ms";
      });
    const indexAt = (x) => {
      const r = root.getBoundingClientRect();
      return Math.max(1, Math.min(stars.length, Math.ceil(((x - r.left) / r.width) * stars.length)));
    };
    root.addEventListener("pointermove", (e) => paint(indexAt(e.clientX), true));
    root.addEventListener("pointerleave", () => paint(committed, false));
    root.addEventListener("click", (e) => {
      committed = indexAt(e.clientX);
      paint(committed, false);
      const star = stars[committed - 1];
      star.classList.remove("pop");
      void star.offsetWidth;
      star.classList.add("pop");
      onChange && onChange(committed);
    });
    paint(committed, false);
  }

  // ---------- Light Pillar: вертикальный световой столб ----------
  function lightPillar(cls = "") {
    return `<div class="pillar ${cls}" aria-hidden="true"><i class="p-glow"></i><i class="p-beam"></i><i class="p-core"></i><i class="p-haze"></i></div>`;
  }

  // ---------- Count Up ----------
  function countUp(el, to, { duration = 900, format = (n) => n.toLocaleString("ru-RU") } = {}) {
    if (!el) return;
    if (reduced) return (el.textContent = format(to));
    const start = performance.now();
    const step = (t) => {
      const p = Math.min(1, (t - start) / duration);
      el.textContent = format(Math.round(to * (1 - Math.pow(1 - p, 3))));
      if (p < 1 && alive(el)) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  return { reduced, clickSpark, maskedHeading, rotatingText, depthCarousel, pointerLights, pillNav, glassIcon,
    bellToggle, codeSlots, rubberSegment, pulseHeart, peekRating, lightPillar, countUp };
})();

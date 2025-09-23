// ===== Config (merged) =====
const BASE_URL = window.location.origin; // ✅ works locally & on Render

// Locale (Chinese)
const LOCALE = "zh-CN";
const LABELS = {
  sold: "已满",
  left: (n) => `剩余${n}间`,
  pickDatesFirst: "请先选择入住和退房日期。",
  checkoutAfterCheckin: "退房日期必须晚于入住日期。",
  enterGuestName: "请输入住客姓名。",
  rangeHasSold: "所选日期范围包含已满的夜晚。",
  couldNotLoad: "无法加载房态。",
  booked: "预订成功！库存已更新。",
  reset: "已重置选择"
};

// DOM refs
const monthsEl = document.getElementById("months");
const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");
const checkInInput = document.getElementById("checkinInput");
const checkOutInput = document.getElementById("checkoutInput");
const roomTypeSel = document.getElementById("roomType");
const qtySel = document.getElementById("qty");
const bookBtn = document.getElementById("bookBtn");
const nightsInfo = document.getElementById("nightsInfo");
const toastEl = document.getElementById("toast");
const resetBtn = document.getElementById("resetBtn"); // NEW

// ===== Load room types from API and populate the <select> =====
async function loadRoomTypes() {
  try {
    const res = await fetch(`${BASE_URL}/room_types`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const list = await res.json(); // [{id, name}, ...]
    if (!Array.isArray(list) || list.length === 0) {
      roomTypeSel.innerHTML = `<option value="">暂无房型</option>`;
      return;
    }
    roomTypeSel.innerHTML = list.map(rt => `<option value="${rt.id}">${rt.name}</option>`).join('');
  } catch (e) {
    console.error("Failed to load /room_types", e);
    roomTypeSel.innerHTML = `<option value="">加载失败</option>`;
  }
}

// ===== Utilities =====
const ISO_RX = /^\d{4}-\d{2}-\d{2}$/;
const tzAdj = (d) => new Date(d.getTime() - d.getTimezoneOffset()*60000);
const toISO = (d) => tzAdj(d).toISOString().slice(0,10);
const fromISO = (s) => { const [y,m,dd] = s.split("-").map(Number); return new Date(y, m-1, dd); };
const addDays = (s, n) => { const d = fromISO(s); d.setDate(d.getDate()+n); return toISO(d); };
const cmp = (a,b) => fromISO(a) - fromISO(b);
const daysBetween = (a,b) => Math.max(0, Math.round((fromISO(b)-fromISO(a))/(24*3600*1000)));
const startOfMonth = (d) => new Date(d.getFullYear(), d.getMonth(), 1);
const endOfMonth = (d) => new Date(d.getFullYear(), d.getMonth()+1, 0);
const monthLabel = (d) => d.toLocaleString(LOCALE, { month: 'long', year: 'numeric' }); // e.g., “2025年9月”

function buildMonthGrid(monthDate) {
  const first = startOfMonth(monthDate);
  const last = endOfMonth(monthDate);
  const startIdx = first.getDay(); // 0..6
  const days = last.getDate();
  const cells = [];
  for (let i=0;i<startIdx;i++) cells.push(null);
  for (let d=1; d<=days; d++) cells.push(new Date(monthDate.getFullYear(), monthDate.getMonth(), d));
  return cells;
}

// ===== State =====
const todayISO = toISO(new Date());
let viewMonth = startOfMonth(new Date());
let checkIn = "";
let checkOut = ""; // checkout-exclusive
let availabilityCache = {}; // { 'YYYY-MM-DD': {price,left} }

// ===== UI helpers =====
function showToast(msg) {
  if (!toastEl) return;
  toastEl.textContent = msg;
  toastEl.style.display = 'block';
  setTimeout(()=> toastEl.style.display='none', 1800);
}

function updateNightsInfo() {
  if (checkIn && checkOut) {
    const nights = daysBetween(checkIn, checkOut);
    nightsInfo.textContent = nights > 0 ? `${nights} 晚` : "";
  } else {
    nightsInfo.textContent = "";
  }
}

function markRangeCells() {
  document.querySelectorAll(".cell").forEach(c => {
    c.classList.remove("in-range","checkin","checkout");
    const d = c.dataset.date;
    if (!d) return;
    if (checkIn && d === checkIn) c.classList.add("checkin");
    // last NIGHT = checkout - 1 day
    if (checkOut && d === addDays(checkOut, -1)) c.classList.add("checkout");
    if (checkIn && checkOut && cmp(checkIn, d) <= 0 && cmp(d, addDays(checkOut, -1)) <= 0) {
      c.classList.add("in-range");
    }
  });
}

// === Gray-out sold nights immediately (and disable cell) ===
function paintAvailability() {
  document.querySelectorAll(".cell").forEach(c => {
    const d = c.dataset.date;
    if (!d) return;
    // Fallback for testing: default to always-available if unknown
    let info = availabilityCache[d];
    if (!info) {
      info = { price: 0, left: 99 }; // ← seed as “always available”
      availabilityCache[d] = info;
    }

    let a = c.querySelector(".a");
    if (!a) {
      a = document.createElement("div");
      a.className = "a";
      c.appendChild(a);
    }
    let p = c.querySelector(".p");
    if (!p) {
      p = document.createElement("div");
      p.className = "p";
      c.appendChild(p);
    }

    const sold = (info.left ?? 0) <= 0;
    c.classList.toggle("sold", sold);
    c.classList.toggle("disabled", sold);
    a.textContent = sold ? LABELS.sold : LABELS.left(info.left);
    p.textContent = (info.price != null) ? `¥${info.price}` : "";
  });
}

// ===== Rendering =====
function renderMonth(container, baseDate) {
  const monthBox = document.createElement("div");
  monthBox.className = "month";
  const title = document.createElement("h4");
  title.textContent = monthLabel(baseDate);
  monthBox.appendChild(title);

  const grid = document.createElement("div");
  grid.className = "grid";

  // Chinese DOWs
  const dows = ["日","一","二","三","四","五","六"];
  dows.forEach(dn => {
    const el = document.createElement("div");
    el.className = "dow";
    el.textContent = dn;
    grid.appendChild(el);
  });

  const cells = buildMonthGrid(baseDate);
  cells.forEach(d => {
    // Use a focusable button-like div for keyboard access
    const cell = document.createElement("div");
    cell.className = "cell";
    cell.setAttribute("role", "button");
    cell.setAttribute("tabindex", d ? "0" : "-1");

    if (d) {
      const iso = toISO(d);
      cell.dataset.date = iso;
      if (cmp(iso, todayISO) < 0) cell.classList.add("disabled");

      const dayEl = document.createElement("div");
      dayEl.className = "d";
      dayEl.textContent = String(d.getDate());
      const priceEl = document.createElement("div");
      priceEl.className = "p"; // filled by paintAvailability

      cell.addEventListener("click", () => onCellClick(iso));
      cell.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onCellClick(iso); }
      });

      cell.appendChild(dayEl);
      cell.appendChild(priceEl);
    } else {
      cell.classList.add("disabled");
    }
    grid.appendChild(cell);
  });

  monthBox.appendChild(grid);
  container.appendChild(monthBox);
}

function renderMonths() {
  monthsEl.innerHTML = "";
  const m1 = new Date(viewMonth.getFullYear(), viewMonth.getMonth(), 1);
  const m2 = new Date(viewMonth.getFullYear(), viewMonth.getMonth()+1, 1);
  renderMonth(monthsEl, m1);
  renderMonth(monthsEl, m2);
  paintAvailability();
  markRangeCells();
  updateNightsInfo();
  updateBookBtn();
}

// ===== Handlers =====
function onCellClick(iso) {
  // ignore disabled cells (past or sold)
  const cell = document.querySelector(`.cell[data-date="${iso}"]`);
  if (cell && cell.classList.contains("disabled")) return;

  // start or restart
  if (!checkIn || (checkIn && checkOut)) {
    checkIn = iso;
    checkOut = "";
    checkInInput.value = checkIn;
    checkOutInput.value = "";
    updateBookBtn();
    renderMonths();
    return;
  }

  // choose checkout (always allow selection first; validate after)
  if (cmp(iso, checkIn) > 0) {
    checkOut = iso;                 // checkout-exclusive
    checkOutInput.value = checkOut;
    updateBookBtn();
    renderMonths();

    // fetch availability for the selected range, then re-validate
    fetchAvailabilityForRange(checkIn, checkOut).then(() => {
      postValidateRange();
    });
  } else {
    // clicked before start — reset start
    checkIn = iso;
    checkOut = "";
    checkInInput.value = checkIn;
    checkOutInput.value = "";
    updateBookBtn();
    renderMonths();
  }
}

function updateBookBtn(){
  const ok =
    !!roomTypeSel?.value &&
    !!checkIn &&
    !!checkOut &&
    Number(qtySel?.value || 0) > 0;
  if (bookBtn) bookBtn.disabled = !ok;
}

// Validate AFTER both ends selected; if any sold night, cancel checkout
function postValidateRange(){
  if (!checkIn || !checkOut) return;
  const endInc = addDays(checkOut, -1);
  const need = Number(qtySel.value || 1);
  let cur = checkIn, ok = true;
  while (cmp(cur, endInc) <= 0) {
    const info = availabilityCache[cur] || { left: 99 }; // fallback if still missing
    if (info.left < need) { ok = false; break; }
    cur = addDays(cur, 1);
  }
  if (!ok) {
    showToast(LABELS.rangeHasSold);
    checkOut = "";
    checkOutInput.value = "";
    updateBookBtn();
    renderMonths();
  }
}

prevBtn?.addEventListener("click", () => {
  viewMonth = new Date(viewMonth.getFullYear(), viewMonth.getMonth()-1, 1);
  renderMonths();
});
nextBtn?.addEventListener("click", () => {
  viewMonth = new Date(viewMonth.getFullYear(), viewMonth.getMonth()+1, 1);
  renderMonths();
});

// typing
function validISO(s){ return ISO_RX.test(s); }

function onInputChange() {
  const ci = (checkInInput.value || "").trim();
  const co = (checkOutInput.value || "").trim();
  if (!ci || !co || !validISO(ci) || !validISO(co) || cmp(ci, co) >= 0) {
    checkIn = validISO(ci) ? ci : "";
    checkOut = "";
    updateBookBtn();
    renderMonths();
    return;
  }

  // set both ends first
  checkIn = ci;
  checkOut = co; // checkout-exclusive expectation
  updateBookBtn();
  renderMonths();

  // fetch → then validate; no pre-blocking
  fetchAvailabilityForRange(checkIn, checkOut).then(() => {
    postValidateRange();
  });
}
checkInInput?.addEventListener("input", onInputChange);
checkOutInput?.addEventListener("input", onInputChange);
qtySel?.addEventListener("change", () => { updateBookBtn(); postValidateRange(); });

// ===== Availability =====
async function fetchAvailabilityForRange(ci, co) {
  try {
    const endInc = addDays(co, -1); // API needs inclusive end
    const roomType = Number(roomTypeSel.value || 1);
    const url = `${BASE_URL}/availability?room_type=${roomType}&start=${ci}&end=${endInc}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json(); // { "YYYY-MM-DD": { price, left }, ... }
    Object.entries(data).forEach(([d, info]) => availabilityCache[d] = info);
    paintAvailability();
    // Note: postValidateRange() is called by the caller after fetch
    return true;
  } catch (err) {
    console.error("Availability failed:", err);
    showToast(LABELS.couldNotLoad);
    return false;
  }
}

// ===== Booking =====
async function bookSelected() {
  const ci = (checkIn || "").trim();
  const co = (checkOut || "").trim(); // checkout = actual day guest leaves (exclusive for API)
  const qty = Number(qtySel.value || 1);
  const roomType = Number(roomTypeSel.value || 1);
  const nameEl = document.getElementById("guestName");
  const emailEl = document.getElementById("guestEmail");
  const name = (nameEl?.value || "").trim();
  const email = (emailEl?.value || "").trim();

  if (!ci || !co) { showToast(LABELS.pickDatesFirst); return; }
  if (fromISO(ci) >= fromISO(co)) { showToast(LABELS.checkoutAfterCheckin); return; }
  if (!name) { showToast(LABELS.enterGuestName); return; }

  // quick client-side check against cached availability (with quantity)
  const endInc = addDays(co, -1);
  let cursor = ci, ok = true;
  while (cmp(cursor, endInc) <= 0) {
    const info = availabilityCache[cursor] || { left: 99 };
    if (info.left < qty) { ok = false; break; }
    cursor = addDays(cursor, 1);
  }
  if (!ok) { showToast(LABELS.rangeHasSold); return; }

  bookBtn.disabled = true;
  try {
    const res = await fetch(`${BASE_URL}/book`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        room_type: roomType,
        check_in: ci,
        check_out: co,     // API expects checkout-exclusive
        name,
        email,
        quantity: qty
      })
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`);

    showToast(LABELS.booked);
    // Refresh availability for the booked range (then re-validate just in case)
    const okFetch = await fetchAvailabilityForRange(ci, co);
    if (okFetch) postValidateRange();

  } catch (err) {
    console.error("Book failed:", err);
    showToast(String(err.message || err));
  } finally {
    bookBtn.disabled = false;
  }
}

// ===== Reset (no page reload) =====
function resetSelection(){
  checkIn = "";
  checkOut = "";
  if (checkInInput) checkInInput.value = "";
  if (checkOutInput) checkOutInput.value = "";
  updateBookBtn();
  renderMonths();
  showToast(LABELS.reset);
}

// ===== Init =====
(function init(){
  viewMonth = startOfMonth(new Date());
  renderMonths();
  bookBtn?.addEventListener("click", bookSelected);
  resetBtn?.addEventListener("click", resetSelection); // NEW

  // populate rooms, then (optionally) refresh availability
  loadRoomTypes().then(() => {
    if (checkIn && checkOut) fetchAvailabilityForRange(checkIn, checkOut).then(() => postValidateRange());
  });

  // when room changes, re-check availability for current range
  roomTypeSel?.addEventListener("change", () => {
    if (checkIn && checkOut) fetchAvailabilityForRange(checkIn, checkOut).then(() => postValidateRange());
    else paintAvailability(); // repaint with fallback if nothing selected yet
  });
})();

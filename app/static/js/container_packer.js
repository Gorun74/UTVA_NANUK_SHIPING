/**
 * NANUK Container Packer
 * Animated drag-and-drop container packing interface
 */

const CONTAINER_CAPACITY = { "20ft": 33.2, "40ft": 67.7 };
const COLOR_STYLES = {
  "Black":      { bg: "#1c1c1e", text: "#e2e8f0", border: "#444" },
  "Orange":     { bg: "#b45309", text: "#fff",    border: "#f59e0b" },
  "Olive":      { bg: "#365314", text: "#d9f99d", border: "#4d7c0f" },
  "Desert Tan": { bg: "#78350f", text: "#fde68a", border: "#d97706" },
};

let orderedItems = {};   // { sku: { sku, description, qty, price, color, volume_m3, ext_l, ext_w, ext_h } }
let currentDragSku = null;
let currentSize = "small";

/* ─── Init ─────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
  // Set today's date if not set
  const dateField = document.getElementById("date_ordered");
  if (dateField && !dateField.value)
    dateField.value = new Date().toISOString().split("T")[0];

  filterSize("small");
  setupDropZone();
  buildCatalogTable();
});

/* ─── View toggle ───────────────────────────────────────────── */
function setView(mode) {
  document.getElementById("view-animated").style.display = mode === "animated" ? "" : "none";
  document.getElementById("view-table").style.display    = mode === "table"    ? "" : "none";
  document.getElementById("btn-animated").classList.toggle("active", mode === "animated");
  document.getElementById("btn-table").classList.toggle("active", mode === "table");
}

/* ─── Case cards ────────────────────────────────────────────── */
function filterSize(size) {
  currentSize = size;
  document.querySelectorAll(".panel-tab").forEach((b, i) => {
    const map = ["small", "medium", "large", "all"];
    b.classList.toggle("active", map[i] === size);
  });
  renderCaseCards(size);
}

function renderCaseCards(size) {
  const container = document.getElementById("case-cards");
  const filtered = size === "all" ? CASES : CASES.filter(c => c.size_cat === size);
  if (!filtered.length) {
    container.innerHTML = `<div style="color:var(--text-muted);padding:20px;font-size:13px;grid-column:span 2;text-align:center;">No cases in this category</div>`;
    return;
  }

  container.innerHTML = filtered.map(c => {
    const w = c.ext_w || 100, l = c.ext_l || 100, h = c.ext_h || 80;
    const maxDim = Math.max(w, l, h, 1);
    const svgW = Math.round((l / maxDim) * 80) + 20;
    const svgH = Math.round((h / maxDim) * 48) + 12;
    const shortName = c.description.replace(/Nanuk Case /i, "").split(" - ")[0];
    const qty = orderedItems[c.sku] ? orderedItems[c.sku].qty : 0;

    return `
    <div class="case-card ${qty > 0 ? 'in-order' : ''}"
         draggable="true"
         data-sku="${c.sku}"
         ondragstart="onDragStart(event, '${c.sku}')"
         ondragend="onDragEnd(event)">
      <div class="tooltip">
        <div><strong>${c.description}</strong></div>
        <div style="color:#94a3b8;font-size:10px;">${c.sku}</div>
        ${c.ext_l ? `<div>${c.ext_l} × ${c.ext_w} × ${c.ext_h} mm</div>` : ''}
        ${c.volume_m3 ? `<div>${c.volume_m3.toFixed(4)} m³</div>` : ''}
        ${c.price ? `<div>$${c.price.toFixed(2)} USD</div>` : ''}
      </div>
      <div class="case-svg-wrap">
        <svg width="${svgW}" height="${svgH}" viewBox="0 0 ${svgW} ${svgH}">
          <!-- Case body -->
          <rect x="1" y="1" width="${svgW-2}" height="${svgH-2}"
                rx="4" ry="4"
                fill="rgba(37,99,235,0.08)"
                stroke="#2563eb" stroke-width="1.5"/>
          <!-- Lid line -->
          <line x1="4" y1="${Math.round(svgH*0.28)}"
                x2="${svgW-4}" y2="${Math.round(svgH*0.28)}"
                stroke="#2563eb" stroke-width="1" opacity=".5"/>
          <!-- Latch -->
          <rect x="${Math.round(svgW/2)-4}" y="${Math.round(svgH*0.22)}"
                width="8" height="5" rx="1"
                fill="#2563eb" opacity=".6"/>
          <!-- Handle -->
          <path d="M ${Math.round(svgW/2)-8} 2 Q ${Math.round(svgW/2)} -3 ${Math.round(svgW/2)+8} 2"
                fill="none" stroke="#2563eb" stroke-width="1.5" opacity=".5"/>
        </svg>
      </div>
      <div class="case-name">${shortName}</div>
      <div class="case-dim">${c.ext_l ? c.ext_l+'×'+c.ext_w+'×'+c.ext_h+' mm' : ''}</div>
      <div class="case-price">${c.price ? '$'+c.price.toFixed(2) : ''}</div>
      ${qty > 0 ? `<div class="case-vol" style="color:var(--accent)">×${qty} in order</div>` : `<div class="case-vol">${c.volume_m3 ? c.volume_m3.toFixed(4)+' m³' : ''}</div>`}
    </div>`;
  }).join("");
}

/* ─── Drag & Drop ───────────────────────────────────────────── */
function onDragStart(e, sku) {
  currentDragSku = sku;
  e.target.classList.add("dragging");
  e.dataTransfer.effectAllowed = "copy";
}

function onDragEnd(e) {
  e.target.classList.remove("dragging");
  currentDragSku = null;
}

function setupDropZone() {
  const zone = document.getElementById("drop-zone");
  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", e => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    if (currentDragSku) openModal(currentDragSku);
  });
}

/* ─── Modal ─────────────────────────────────────────────────── */
let pendingDropSku = null;

function openModal(sku) {
  const item = CASES.find(c => c.sku === sku);
  if (!item) return;
  pendingDropSku = sku;

  document.getElementById("modal-title").textContent = "Add to Container";
  document.getElementById("modal-sku").textContent = sku + " — " + item.description;
  document.getElementById("modal-price").value = item.price ? item.price.toFixed(2) : "";
  document.getElementById("modal-qty").value = orderedItems[sku] ? orderedItems[sku].qty : 1;

  // Preselect color based on SKU
  const colorSel = document.getElementById("modal-color");
  const skuColor = detectColorFromSku(sku);
  if (skuColor) {
    for (let opt of colorSel.options) {
      if (opt.value === skuColor) { opt.selected = true; break; }
    }
  }

  document.getElementById("modal").style.display = "flex";
  document.getElementById("modal-qty").focus();
  document.getElementById("modal-qty").select();
}

function detectColorFromSku(sku) {
  if (sku.includes("-BK-")) return "Black";
  if (sku.includes("-OR-")) return "Orange";
  if (sku.includes("-OL-")) return "Olive";
  if (sku.includes("-DT-")) return "Desert Tan";
  return null;
}

function closeModal() {
  document.getElementById("modal").style.display = "none";
  pendingDropSku = null;
}

function confirmDrop() {
  if (!pendingDropSku) return closeModal();
  const qty   = parseInt(document.getElementById("modal-qty").value) || 1;
  const color = document.getElementById("modal-color").value;
  const price = parseFloat(document.getElementById("modal-price").value) || 0;
  const item  = CASES.find(c => c.sku === pendingDropSku);
  if (!item) return closeModal();

  orderedItems[pendingDropSku] = {
    sku:         item.sku,
    description: item.description,
    qty,
    sell_price:  price,
    color,
    volume_m3:   item.volume_m3 || 0,
    ext_l: item.ext_l, ext_w: item.ext_w, ext_h: item.ext_h,
  };

  renderDropped();
  renderCaseCards(currentSize);
  updateSummary();
  updateShippingEstimate();
  closeModal();
}

// Close modal on overlay click
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("modal").addEventListener("click", e => {
    if (e.target === document.getElementById("modal")) closeModal();
  });
});

/* ─── Container visualization ───────────────────────────────── */
function renderDropped() {
  const floor = document.getElementById("container-floor");
  const hint  = document.getElementById("empty-hint");
  const keys  = Object.keys(orderedItems);

  if (!keys.length) {
    floor.innerHTML = "";
    hint.style.display = "";
    document.getElementById("fill-bar").style.width = "0%";
    document.getElementById("fill-text").textContent = "0%";
    return;
  }
  hint.style.display = "none";

  const capacity = getCapacity();
  const totalCbm = keys.reduce((s, k) => s + (orderedItems[k].volume_m3 * orderedItems[k].qty), 0);
  const fillPct  = Math.min(100, (totalCbm / capacity) * 100);

  floor.innerHTML = keys.map(sku => {
    const item = orderedItems[sku];
    const style = COLOR_STYLES[item.color] || COLOR_STYLES["Black"];
    const cbm = (item.volume_m3 * item.qty).toFixed(3);
    return `
    <div class="dropped-item" title="${item.description}\n${item.color} × ${item.qty}"
         style="background:${style.bg};border-color:${style.border};color:${style.text};"
         onclick="openModal('${sku}')">
      <div class="di-sku">${sku.split("-")[0]}</div>
      <div class="di-qty">×${item.qty}</div>
      <div class="di-vol">${cbm}m³</div>
    </div>`;
  }).join("");

  // Fill bar color: green <70%, yellow 70-90%, red >90%
  const bar = document.getElementById("fill-bar");
  bar.style.width = fillPct + "%";
  bar.style.background = fillPct > 90 ? "var(--danger)" :
                          fillPct > 70 ? "var(--warning)" :
                          "linear-gradient(90deg, var(--success), var(--accent))";
  document.getElementById("fill-text").textContent = fillPct.toFixed(1) + "%";
}

function getCapacity() {
  const size = document.getElementById("container_size")?.value || "20ft";
  return CONTAINER_CAPACITY[size] || 33.2;
}

function updateCapacity() {
  renderDropped();
  updateShippingEstimate();
}

/* ─── Shipping estimate ─────────────────────────────────────── */
let estDebounce = null;
function updateShippingEstimate() {
  clearTimeout(estDebounce);
  estDebounce = setTimeout(_fetchEstimate, 500);
}

async function _fetchEstimate() {
  const keys = Object.keys(orderedItems);
  const totalCbm = keys.reduce((s, k) => s + orderedItems[k].volume_m3 * orderedItems[k].qty, 0);
  const rate = parseFloat(document.getElementById("used_rate")?.value || "1.58");
  const goodsUsd = keys.reduce((s, k) => s + (orderedItems[k].sell_price || 0) * orderedItems[k].qty, 0);
  const goodsAud = goodsUsd * rate;

  // Hide packer panel if no items
  if (!keys.length) {
    document.getElementById("ship-estimate").style.display = "none";
    _resetHeaderEstimate();
    return;
  }

  try {
    const resp = await fetch("/api/shipping-estimate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cbm: totalCbm, goods_value_aud: goodsAud, usd_aud_rate: rate }),
    });
    const data = await resp.json();
    if (data.error) return;

    const fmt  = v => "A$" + (v || 0).toLocaleString("en-AU", { maximumFractionDigits: 0 });
    const fmt2 = v => "A$" + (v || 0).toLocaleString("en-AU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    // Update packer panel (right side)
    document.getElementById("est-ocean").textContent     = fmt(data.ocean_AUD);
    document.getElementById("est-extras").textContent    = fmt(data.extras_AUD);
    document.getElementById("est-insurance").textContent = fmt(data.insurance_AUD);
    document.getElementById("est-duty").textContent      = fmt(data.duty_AUD);
    document.getElementById("est-gst").textContent       = fmt(data.gst_AUD);
    document.getElementById("est-total").textContent     = fmt(data.TOTAL_AUD);
    document.getElementById("est-per-cbm").textContent   = "A$" + (data.per_cbm_AUD || 0).toFixed(2) + "/m³";
    document.getElementById("est-note").textContent      = data.note || "";
    document.getElementById("ship-estimate").style.display = "";

    // Update header box (always visible)
    _setEl("h-ocean",    fmt(data.ocean_AUD));
    _setEl("h-extras",   fmt(data.extras_AUD));
    _setEl("h-insurance",fmt(data.insurance_AUD));
    _setEl("h-duty",     fmt(data.duty_AUD));
    _setEl("h-gst",      fmt(data.gst_AUD));
    _setEl("h-total",    fmt2(data.TOTAL_AUD));
    _setEl("h-per-cbm",  "A$" + (data.per_cbm_AUD || 0).toFixed(2) + "/m³");
    _setEl("h-type",     data.container || "—");
    _setEl("ship-header-cbm", totalCbm.toFixed(2) + " m³");
    _setEl("ship-header-note", data.note || "");
  } catch {}
}

function _setEl(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function _resetHeaderEstimate() {
  ["h-ocean","h-extras","h-insurance","h-duty","h-gst","h-per-cbm","h-type"].forEach(id => _setEl(id, "—"));
  _setEl("h-total", "add items →");
  _setEl("ship-header-cbm", "");
  _setEl("ship-header-note", "");
}

/* ─── Order summary ─────────────────────────────────────────── */
function updateSummary() {
  const keys = Object.keys(orderedItems);
  const summary = document.getElementById("order-summary");

  if (!keys.length) {
    summary.style.display = "none";
    return;
  }
  summary.style.display = "";

  const totalCbm = keys.reduce((s, k) => s + orderedItems[k].volume_m3 * orderedItems[k].qty, 0);
  const totalUsd = keys.reduce((s, k) => s + (orderedItems[k].sell_price || 0) * orderedItems[k].qty, 0);

  document.getElementById("summary-cbm").textContent = totalCbm.toFixed(3) + " m³";
  document.getElementById("summary-usd").textContent = "$" + totalUsd.toFixed(2) + " USD";

  const tbody = document.getElementById("summary-body");
  tbody.innerHTML = keys.map(sku => {
    const item = orderedItems[sku];
    const lineTotal = ((item.sell_price || 0) * item.qty).toFixed(2);
    const cbm = (item.volume_m3 * item.qty).toFixed(3);
    return `
    <tr>
      <td class="mono">${sku}</td>
      <td>${item.description}</td>
      <td>
        <input type="number" value="${item.qty}" min="1" max="999"
               onchange="updateOrderQty('${sku}', this.value)"
               class="qty-input">
      </td>
      <td>
        <input type="number" value="${(item.sell_price||0).toFixed(2)}" step="0.01" min="0"
               onchange="updateOrderPrice('${sku}', this.value)"
               class="price-input">
      </td>
      <td>$${lineTotal}</td>
      <td>${cbm}</td>
      <td><button class="btn btn-sm btn-danger" onclick="removeItem('${sku}')">✕</button></td>
    </tr>`;
  }).join("");
}

function updateOrderQty(sku, val) {
  if (!orderedItems[sku]) return;
  orderedItems[sku].qty = Math.max(1, parseInt(val) || 1);
  renderDropped();
  updateSummary();
  updateShippingEstimate();
}
function updateOrderPrice(sku, val) {
  if (!orderedItems[sku]) return;
  orderedItems[sku].sell_price = parseFloat(val) || 0;
  updateSummary();
  updateShippingEstimate();
}
function removeItem(sku) {
  delete orderedItems[sku];
  renderDropped();
  renderCaseCards(currentSize);
  updateSummary();
  updateShippingEstimate();
}
function clearAll() {
  orderedItems = {};
  renderDropped();
  renderCaseCards(currentSize);
  updateSummary();
  updateShippingEstimate();
}

/* ─── Table view search ─────────────────────────────────────── */
function tableSearch(q) {
  q = q.toLowerCase();
  document.querySelectorAll("#catalog-body tr").forEach(tr => {
    const text = tr.textContent.toLowerCase();
    tr.style.display = text.includes(q) ? "" : "none";
  });
}

function buildCatalogTable() {
  const tbody = document.getElementById("catalog-body");
  if (!tbody) return;
  tbody.innerHTML = CASES.map(c => `
    <tr>
      <td class="mono">${c.sku}</td>
      <td>${c.description}</td>
      <td>${c.ext_l ? c.ext_l+'×'+c.ext_w+'×'+c.ext_h+' mm' : '—'}</td>
      <td>${c.volume_m3 ? c.volume_m3.toFixed(4) : '—'}</td>
      <td>${c.price ? '$'+c.price.toFixed(2) : '—'}</td>
      <td>
        <input type="number" id="tbl-qty-${c.sku}" value="1" min="1" max="999"
               class="qty-input" style="width:60px">
      </td>
      <td>
        <button class="btn btn-sm btn-primary"
                onclick="tableAddItem('${c.sku}')">+ Add</button>
      </td>
    </tr>
  `).join("");
}

function tableAddItem(sku) {
  const qty = parseInt(document.getElementById("tbl-qty-" + sku)?.value || "1") || 1;
  const item = CASES.find(c => c.sku === sku);
  if (!item) return;

  // If already added, update qty
  if (orderedItems[sku]) {
    orderedItems[sku].qty = qty;
  } else {
    orderedItems[sku] = {
      sku,
      description: item.description,
      qty,
      sell_price: item.price || 0,
      color: detectColorFromSku(sku) || "Black",
      volume_m3: item.volume_m3 || 0,
      ext_l: item.ext_l, ext_w: item.ext_w, ext_h: item.ext_h,
    };
  }
  renderDropped();
  updateSummary();
  updateShippingEstimate();
}

/* ─── Save container ────────────────────────────────────────── */
async function saveContainer() {
  const keys = Object.keys(orderedItems);
  if (!keys.length) return alert("Add at least one item to the container.");

  const payload = {
    date_ordered:           document.getElementById("date_ordered").value,
    expected_arrival_date:  document.getElementById("expected_arrival_date").value || null,
    used_rate:              parseFloat(document.getElementById("used_rate").value) || 1.58,
    shipping_aud:           parseFloat(document.getElementById("shipping_aud").value) || 0,
    other1_aud:             parseFloat(document.getElementById("other1_aud").value) || 0,
    other2_aud:             parseFloat(document.getElementById("other2_aud").value) || 0,
    container_size:         document.getElementById("container_size").value,
    container_fill:         document.getElementById("container_fill").value,
    lines: keys.map(sku => ({
      sku,
      qty_ordered: orderedItems[sku].qty,
      unit_price_usd: orderedItems[sku].sell_price || null,
    })),
  };

  const btn = event.target;
  btn.disabled = true;
  btn.textContent = "Saving...";

  try {
    const resp = await fetch("/containers/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (data.redirect) window.location = data.redirect;
    else { alert(data.error || "Error saving container"); btn.disabled = false; btn.textContent = "Save Container Order"; }
  } catch (e) {
    alert("Network error: " + e.message);
    btn.disabled = false;
    btn.textContent = "Save Container Order";
  }
}

function detectColorFromSku(sku) {
  if (sku.includes("-BK-")) return "Black";
  if (sku.includes("-OR-")) return "Orange";
  if (sku.includes("-OL-")) return "Olive";
  if (sku.includes("-DT-")) return "Desert Tan";
  return "Black";
}

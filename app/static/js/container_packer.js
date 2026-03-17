/**
 * NANUK Container Packer — model-grouped view
 * CASES is now an array of model objects, each with a `variants` dict {color: {sku, price}}
 */

const CONTAINER_CAPACITY = { "20ft": 33.2, "40ft": 67.7 };

// Visual styles per color name
const COLOR_STYLES = {
  "Black":      { bg: "#1c1c1e", text: "#e2e8f0", border: "#555" },
  "Orange":     { bg: "#92400e", text: "#fed7aa", border: "#f97316" },
  "Olive":      { bg: "#365314", text: "#d9f99d", border: "#4d7c0f" },
  "Desert Tan": { bg: "#78350f", text: "#fde68a", border: "#d97706" },
  "Yellow":     { bg: "#713f12", text: "#fef08a", border: "#eab308" },
  "Red":        { bg: "#7f1d1d", text: "#fecaca", border: "#ef4444" },
  "Graphite":   { bg: "#1f2937", text: "#d1d5db", border: "#6b7280" },
  "Blue":       { bg: "#1e3a8a", text: "#bfdbfe", border: "#3b82f6" },
  "Silver":     { bg: "#1e293b", text: "#e2e8f0", border: "#94a3b8" },
  "Lime":       { bg: "#1a2e05", text: "#d9f99d", border: "#84cc16" },
  "Tan":        { bg: "#78350f", text: "#fde68a", border: "#a16207" },
  "Clear":      { bg: "#0f172a", text: "#cbd5e1", border: "#64748b" },
  "Purple":     { bg: "#3b0764", text: "#ddd6fe", border: "#7c3aed" },
};

// orderedItems: { [sku]: { sku, model, display_name, color, qty, sell_price, volume_m3, ext_l, ext_w, ext_h } }
let orderedItems = {};
let currentDragModel = null;
let currentSize = "small";
let pendingDropModel = null;   // model group_key for the open modal

/* ─── Init ─────────────────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
  const df = document.getElementById("date_ordered");
  if (df && !df.value) df.value = new Date().toISOString().split("T")[0];

  // Pre-populate from draft if editing
  if (typeof DRAFT_PREFILL === "object" && DRAFT_PREFILL) {
    orderedItems = DRAFT_PREFILL;
  }

  filterSize("small");
  setupDropZone();
  buildCatalogTable();
  if (Object.keys(orderedItems).length) {
    renderDropped();
    updateSummary();
    updateShippingEstimate();
  }
  document.getElementById("modal").addEventListener("click", e => {
    if (e.target === document.getElementById("modal")) closeModal();
  });
});

/* ─── View toggle ─────────────────────────────────────────────────────── */
function setView(mode) {
  document.getElementById("view-animated").style.display = mode === "animated" ? "" : "none";
  document.getElementById("view-table").style.display    = mode === "table"    ? "" : "none";
  document.getElementById("btn-animated").classList.toggle("active", mode === "animated");
  document.getElementById("btn-table").classList.toggle("active", mode === "table");
}

/* ─── Size filter ─────────────────────────────────────────────────────── */
function filterSize(size) {
  currentSize = size;
  document.querySelectorAll(".panel-tab").forEach((b, i) => {
    b.classList.toggle("active", ["small","medium","large","all"][i] === size);
  });
  renderCaseCards(size);
}

/* ─── Case cards (one per model) ─────────────────────────────────────── */
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
    const svgW = Math.round((l / maxDim) * 76) + 18;
    const svgH = Math.round((h / maxDim) * 46) + 12;
    const colorNames = Object.keys(c.variants);

    // Count how many colors are already ordered for this model
    const orderedColors = colorNames.filter(col => orderedItems[c.variants[col].sku]);
    const inOrder = orderedColors.length > 0;
    const inOrderQty = orderedColors.reduce((s, col) => s + (orderedItems[c.variants[col].sku]?.qty || 0), 0);

    // Color swatches (up to 10)
    const swatchLimit = 10;
    const swatches = colorNames.slice(0, swatchLimit).map(col => {
      const st = COLOR_STYLES[col] || { bg: "#555" };
      const inOrd = orderedItems[c.variants[col]?.sku];
      return `<span class="color-swatch ${inOrd ? 'swatch-in-order' : ''}"
                    style="background:${st.bg};border-color:${st.border || st.bg}"
                    title="${col}${inOrd ? ' ✓' : ''}"></span>`;
    }).join("");
    const extra = colorNames.length > swatchLimit
      ? `<span class="swatch-extra">+${colorNames.length - swatchLimit}</span>` : "";

    // Price range
    const prices = colorNames.map(col => c.variants[col].price).filter(Boolean);
    const minP = prices.length ? Math.min(...prices) : 0;
    const priceStr = minP ? `$${minP.toFixed(2)}` : "";

    return `
    <div class="case-card ${inOrder ? 'in-order' : ''}"
         draggable="true"
         data-model="${c.model}"
         ondragstart="onDragStart(event,'${c.model}')"
         ondragend="onDragEnd(event)"
         onclick="openModal('${c.model}')">
      <div class="tooltip">
        <div><strong>${c.display_name}</strong></div>
        ${c.ext_l ? `<div style="color:#94a3b8;font-size:10px;">${c.ext_l} × ${c.ext_w} × ${c.ext_h} mm ext.</div>` : ''}
        ${c.volume_m3 ? `<div>${c.volume_m3.toFixed(4)} m³</div>` : ''}
        <div style="margin-top:4px;">${colorNames.join(', ')}</div>
      </div>
      <div class="case-svg-wrap">
        <svg width="${svgW}" height="${svgH}" viewBox="0 0 ${svgW} ${svgH}">
          <rect x="1" y="1" width="${svgW-2}" height="${svgH-2}" rx="4"
                fill="rgba(37,99,235,0.08)" stroke="#2563eb" stroke-width="1.5"/>
          <line x1="4" y1="${Math.round(svgH*0.28)}" x2="${svgW-4}" y2="${Math.round(svgH*0.28)}"
                stroke="#2563eb" stroke-width="1" opacity=".5"/>
          <rect x="${Math.round(svgW/2)-4}" y="${Math.round(svgH*0.22)}" width="8" height="5"
                rx="1" fill="#2563eb" opacity=".6"/>
          <path d="M ${Math.round(svgW/2)-8} 2 Q ${Math.round(svgW/2)} -3 ${Math.round(svgW/2)+8} 2"
                fill="none" stroke="#2563eb" stroke-width="1.5" opacity=".5"/>
        </svg>
      </div>
      <div class="case-name">${c.display_name}</div>
      <div class="case-dim">${c.ext_l ? c.ext_l+'×'+c.ext_w+'×'+c.ext_h+' mm' : ''}</div>
      <div class="case-swatches">${swatches}${extra}</div>
      <div class="case-price">${priceStr}</div>
      ${inOrder
        ? `<div class="case-vol" style="color:var(--accent)">×${inOrderQty} in order</div>`
        : `<div class="case-vol">${c.volume_m3 ? c.volume_m3.toFixed(4)+' m³' : ''}</div>`}
    </div>`;
  }).join("");
}

/* ─── Drag & Drop ─────────────────────────────────────────────────────── */
function onDragStart(e, model) {
  currentDragModel = model;
  e.target.classList.add("dragging");
  e.dataTransfer.effectAllowed = "copy";
}
function onDragEnd(e) {
  e.target.classList.remove("dragging");
  currentDragModel = null;
}
function setupDropZone() {
  const zone = document.getElementById("drop-zone");
  zone.addEventListener("dragover",  e => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", e => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    if (currentDragModel) openModal(currentDragModel);
  });
}

/* ─── Modal ────────────────────────────────────────────────────────────── */
function openModal(model_key, existing_sku = null) {
  const model = CASES.find(c => c.model === model_key);
  if (!model) return;
  pendingDropModel = model_key;

  document.getElementById("modal-title").textContent = model.display_name;

  // Build color options dynamically
  const colorSel = document.getElementById("modal-color");
  colorSel.innerHTML = Object.keys(model.variants).map(col =>
    `<option value="${col}">${col}</option>`
  ).join("");

  // Preselect color if editing existing item
  if (existing_sku) {
    const match = Object.entries(model.variants).find(([, v]) => v.sku === existing_sku);
    if (match) colorSel.value = match[0];
  }

  _refreshModalForColor(model);
  document.getElementById("modal").style.display = "flex";
  document.getElementById("modal-qty").focus();
  document.getElementById("modal-qty").select();
}

function onModalColorChange() {
  const model = CASES.find(c => c.model === pendingDropModel);
  _refreshModalForColor(model);
}

function _refreshModalForColor(model) {
  if (!model) return;
  const color   = document.getElementById("modal-color").value;
  const variant = model.variants[color];
  if (!variant) return;
  document.getElementById("modal-price").value = variant.price ? variant.price.toFixed(2) : "";
  const existing = orderedItems[variant.sku];
  document.getElementById("modal-qty").value = existing ? existing.qty : 1;
  // Show SKU info
  document.getElementById("modal-sku").textContent = variant.sku;
}

function closeModal() {
  document.getElementById("modal").style.display = "none";
  pendingDropModel = null;
}

function confirmDrop() {
  if (!pendingDropModel) return closeModal();
  const model = CASES.find(c => c.model === pendingDropModel);
  if (!model) return closeModal();

  const color   = document.getElementById("modal-color").value;
  const qty     = parseInt(document.getElementById("modal-qty").value) || 1;
  const price   = parseFloat(document.getElementById("modal-price").value) || 0;
  const variant = model.variants[color];
  if (!variant) return closeModal();

  orderedItems[variant.sku] = {
    sku:          variant.sku,
    model:        model.model,
    display_name: model.display_name,
    description:  model.display_name + " — " + color,
    color,
    qty,
    sell_price:   price,
    volume_m3:    model.volume_m3 || 0,
    ext_l: model.ext_l, ext_w: model.ext_w, ext_h: model.ext_h,
  };

  renderDropped();
  renderCaseCards(currentSize);
  updateSummary();
  updateShippingEstimate();
  closeModal();
}

/* ─── Container visualization ─────────────────────────────────────────── */
function renderDropped() {
  const floor   = document.getElementById("container-floor");
  const hint    = document.getElementById("empty-hint");
  const keys    = Object.keys(orderedItems);

  if (!keys.length) {
    floor.innerHTML = "";
    hint.style.display = "";
    document.getElementById("fill-bar").style.width = "0%";
    document.getElementById("fill-text").textContent = "0%";
    return;
  }
  hint.style.display = "none";

  const capacity = getCapacity();
  const totalCbm = keys.reduce((s, k) => s + orderedItems[k].volume_m3 * orderedItems[k].qty, 0);
  const fillPct  = Math.min(100, (totalCbm / capacity) * 100);

  floor.innerHTML = keys.map(sku => {
    const item  = orderedItems[sku];
    const style = COLOR_STYLES[item.color] || COLOR_STYLES["Black"];
    const cbm   = (item.volume_m3 * item.qty).toFixed(3);
    return `
    <div class="dropped-item"
         title="${item.display_name}\n${item.color} × ${item.qty}"
         style="background:${style.bg};border-color:${style.border};color:${style.text};"
         onclick="openModal('${item.model}','${sku}')">
      <div class="di-sku">${item.model}</div>
      <div class="di-color" style="font-size:9px;opacity:.8">${item.color}</div>
      <div class="di-qty">×${item.qty}</div>
      <div class="di-vol">${cbm}m³</div>
    </div>`;
  }).join("");

  const bar = document.getElementById("fill-bar");
  bar.style.width = fillPct + "%";
  bar.style.background = fillPct > 90 ? "var(--danger)"
                       : fillPct > 70 ? "var(--warning)"
                       : "linear-gradient(90deg, var(--success), var(--accent))";
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

/* ─── Shipping estimate ────────────────────────────────────────────────── */
let estDebounce = null;
function updateShippingEstimate() {
  clearTimeout(estDebounce);
  estDebounce = setTimeout(_fetchEstimate, 500);
}

async function _fetchEstimate() {
  const keys = Object.keys(orderedItems);
  const totalCbm = keys.reduce((s, k) => s + orderedItems[k].volume_m3 * orderedItems[k].qty, 0);
  const rate     = parseFloat(document.getElementById("used_rate")?.value || "1.58");
  const goodsUsd = keys.reduce((s, k) => s + (orderedItems[k].sell_price || 0) * orderedItems[k].qty, 0);
  const goodsAud = goodsUsd * rate;

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

    // Packer panel
    document.getElementById("est-ocean").textContent     = fmt(data.ocean_AUD);
    document.getElementById("est-extras").textContent    = fmt(data.extras_AUD);
    document.getElementById("est-insurance").textContent = fmt(data.insurance_AUD);
    document.getElementById("est-duty").textContent      = fmt(data.duty_AUD);
    document.getElementById("est-gst").textContent       = fmt(data.gst_AUD);
    document.getElementById("est-total").textContent     = fmt(data.TOTAL_AUD);
    document.getElementById("est-per-cbm").textContent   = "A$" + (data.per_cbm_AUD || 0).toFixed(2) + "/m³";
    document.getElementById("est-note").textContent      = data.note || "";
    document.getElementById("ship-estimate").style.display = "";

    // Header KPI box
    const grandTotal = goodsAud + (data.TOTAL_AUD || 0);
    _setEl("h-goods-usd",  "$" + goodsUsd.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " USD");
    _setEl("h-goods-aud",  "≈ A$" + goodsAud.toLocaleString("en-AU", { minimumFractionDigits: 0, maximumFractionDigits: 0 }));
    _setEl("h-ocean",      fmt(data.ocean_AUD));
    _setEl("h-extras",     fmt(data.extras_AUD));
    _setEl("h-insurance",  fmt(data.insurance_AUD));
    _setEl("h-duty",       fmt(data.duty_AUD));
    _setEl("h-gst",        fmt(data.gst_AUD));
    _setEl("h-total",      fmt2(data.TOTAL_AUD));
    _setEl("h-per-cbm",    "A$" + (data.per_cbm_AUD || 0).toFixed(2) + "/m³");
    _setEl("h-type",       data.container || "—");
    _setEl("h-grand-total","A$" + grandTotal.toLocaleString("en-AU", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
    _setEl("ship-header-cbm",  totalCbm.toFixed(2) + " m³");
    _setEl("ship-header-note", data.note || "");
  } catch {}
}

function _setEl(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function _resetHeaderEstimate() {
  ["h-ocean","h-extras","h-insurance","h-duty","h-gst","h-per-cbm"].forEach(id => _setEl(id, "—"));
  _setEl("h-goods-usd",  "—");
  _setEl("h-goods-aud",  "add items");
  _setEl("h-total",      "—");
  _setEl("h-type",       "add items to estimate");
  _setEl("h-grand-total","—");
  _setEl("ship-header-cbm",  "");
  _setEl("ship-header-note", "");
}

/* ─── Order summary ────────────────────────────────────────────────────── */
function updateSummary() {
  const keys    = Object.keys(orderedItems);
  const summary = document.getElementById("order-summary");

  if (!keys.length) { summary.style.display = "none"; return; }
  summary.style.display = "";

  const totalCbm = keys.reduce((s, k) => s + orderedItems[k].volume_m3 * orderedItems[k].qty, 0);
  const totalUsd = keys.reduce((s, k) => s + (orderedItems[k].sell_price || 0) * orderedItems[k].qty, 0);
  const rate     = parseFloat(document.getElementById("used_rate")?.value || "1.58");

  document.getElementById("summary-cbm").textContent = totalCbm.toFixed(3) + " m³";
  document.getElementById("summary-usd").textContent = "$" + totalUsd.toFixed(2) + " USD";

  _setEl("h-goods-usd", "$" + totalUsd.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " USD");
  _setEl("h-goods-aud", "≈ A$" + (totalUsd * rate).toLocaleString("en-AU", { minimumFractionDigits: 0, maximumFractionDigits: 0 }));

  document.getElementById("summary-body").innerHTML = keys.map(sku => {
    const item      = orderedItems[sku];
    const lineTotal = ((item.sell_price || 0) * item.qty).toFixed(2);
    const cbm       = (item.volume_m3 * item.qty).toFixed(3);
    const cs        = COLOR_STYLES[item.color] || { bg:"#333", border:"#555" };
    return `
    <tr>
      <td class="mono" style="font-size:11px">${sku}</td>
      <td>
        <span style="display:inline-block;width:10px;height:10px;border-radius:2px;
                     background:${cs.bg};border:1px solid ${cs.border};margin-right:5px;vertical-align:middle"></span>
        ${item.display_name} — ${item.color}
      </td>
      <td><input type="number" value="${item.qty}" min="1" max="999"
                 onchange="updateOrderQty('${sku}',this.value)" class="qty-input"></td>
      <td><input type="number" value="${(item.sell_price||0).toFixed(2)}" step="0.01" min="0"
                 onchange="updateOrderPrice('${sku}',this.value)" class="price-input"></td>
      <td>$${lineTotal}</td>
      <td>${cbm}</td>
      <td><button class="btn btn-sm btn-danger" onclick="removeItem('${sku}')">✕</button></td>
    </tr>`;
  }).join("");
}

function updateOrderQty(sku, val) {
  if (!orderedItems[sku]) return;
  orderedItems[sku].qty = Math.max(1, parseInt(val) || 1);
  renderDropped(); updateSummary(); updateShippingEstimate();
}
function updateOrderPrice(sku, val) {
  if (!orderedItems[sku]) return;
  orderedItems[sku].sell_price = parseFloat(val) || 0;
  updateSummary(); updateShippingEstimate();
}
function removeItem(sku) {
  delete orderedItems[sku];
  renderDropped(); renderCaseCards(currentSize); updateSummary(); updateShippingEstimate();
}
function clearAll() {
  orderedItems = {};
  renderDropped(); renderCaseCards(currentSize); updateSummary(); updateShippingEstimate();
}

/* ─── Table view ────────────────────────────────────────────────────────── */
function tableSearch(q) {
  q = q.toLowerCase();
  document.querySelectorAll("#catalog-body tr").forEach(tr => {
    tr.style.display = tr.textContent.toLowerCase().includes(q) ? "" : "none";
  });
}

function buildCatalogTable() {
  const tbody = document.getElementById("catalog-body");
  if (!tbody) return;
  tbody.innerHTML = CASES.map(c => {
    const colorOpts = Object.keys(c.variants).map(col => `<option value="${col}">${col}</option>`).join("");
    const firstVariant = Object.values(c.variants)[0] || { price: 0 };
    return `
    <tr>
      <td class="mono" style="font-size:11px">${c.model}</td>
      <td>${c.display_name}</td>
      <td>${c.ext_l ? c.ext_l+'×'+c.ext_w+'×'+c.ext_h+' mm' : '—'}</td>
      <td>${c.volume_m3 ? c.volume_m3.toFixed(4) : '—'}</td>
      <td>
        <select class="qty-input" id="tbl-color-${c.model}" style="min-width:90px"
                onchange="updateTablePrice('${c.model}')">
          ${colorOpts}
        </select>
      </td>
      <td id="tbl-price-${c.model}">${firstVariant.price ? '$'+firstVariant.price.toFixed(2) : '—'}</td>
      <td><input type="number" id="tbl-qty-${c.model}" value="1" min="1" max="999" class="qty-input" style="width:60px"></td>
      <td><button class="btn btn-sm btn-primary" onclick="tableAddItem('${c.model}')">+ Add</button></td>
    </tr>`;
  }).join("");
}

function updateTablePrice(model_key) {
  const model   = CASES.find(c => c.model === model_key);
  const color   = document.getElementById(`tbl-color-${model_key}`)?.value;
  const variant = model?.variants?.[color];
  const el      = document.getElementById(`tbl-price-${model_key}`);
  if (el && variant) el.textContent = variant.price ? '$' + variant.price.toFixed(2) : '—';
}

function tableAddItem(model_key) {
  const model   = CASES.find(c => c.model === model_key);
  if (!model) return;
  const qty     = parseInt(document.getElementById(`tbl-qty-${model_key}`)?.value || "1") || 1;
  const color   = document.getElementById(`tbl-color-${model_key}`)?.value || Object.keys(model.variants)[0];
  const variant = model.variants[color];
  if (!variant) return;

  orderedItems[variant.sku] = {
    sku:          variant.sku,
    model:        model.model,
    display_name: model.display_name,
    description:  model.display_name + " — " + color,
    color,
    qty,
    sell_price:   variant.price || 0,
    volume_m3:    model.volume_m3 || 0,
    ext_l: model.ext_l, ext_w: model.ext_w, ext_h: model.ext_h,
  };
  renderDropped(); updateSummary(); updateShippingEstimate();
}

/* ─── Save container ─────────────────────────────────────────────────────── */
async function saveContainer(asDraft = false) {
  const keys = Object.keys(orderedItems);
  if (!keys.length) return alert("Add at least one item to the container.");

  const payload = {
    date_ordered:          document.getElementById("date_ordered").value,
    expected_arrival_date: document.getElementById("expected_arrival_date").value || null,
    used_rate:             parseFloat(document.getElementById("used_rate").value) || 1.58,
    shipping_aud:          parseFloat(document.getElementById("shipping_aud").value) || 0,
    other1_aud:            parseFloat(document.getElementById("other1_aud").value) || 0,
    other2_aud:            parseFloat(document.getElementById("other2_aud").value) || 0,
    container_size:        document.getElementById("container_size").value,
    container_fill:        document.getElementById("container_fill").value,
    lines: keys.map(sku => ({
      sku,
      qty_ordered:    orderedItems[sku].qty,
      unit_price_usd: orderedItems[sku].sell_price || null,
    })),
    save_as_draft: asDraft,
    draft_id:      (typeof DRAFT_ID !== "undefined" && DRAFT_ID) ? DRAFT_ID : null,
  };

  try {
    const resp = await fetch("/containers/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (resp.redirected) { window.location.href = resp.url; return; }
    const data = await resp.json().catch(() => ({}));
    if (data.redirect) { window.location.href = data.redirect; return; }
    if (!resp.ok) alert("Error saving: " + (data.error || resp.statusText));
    else window.location.reload();
  } catch (e) {
    alert("Network error: " + e.message);
  }
}

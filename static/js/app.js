const state = {
  page: "dashboard",
  records: [],
  summary: null,
  layouts: {},
  activeLayout: "car",
  lastResult: null,
};

const pageInfo = {
  dashboard: ["Dashboard", "Current parking activity and capacity."],
  detection: ["Vehicle Detection", "Process a vehicle image for entry or exit."],
  records: ["Vehicle Records", "Search and filter the vehicle history."],
  layout: ["Parking Layout", "Review reconciled slot status by vehicle category."],
  reports: ["Parking History / Reports", "Review completed parking sessions."],
};

const statusText = (value) => String(value || "").trim();
const el = (id) => document.getElementById(id);

function showFeedback(element, message, kind = "") {
  element.textContent = message;
  element.className = `feedback ${kind}`.trim();
  element.hidden = !message;
}

async function apiData(url, options) {
  const response = await fetch(url, options);
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error("The server returned an unreadable response.");
  }
  if (!response.ok || payload.ok !== true) {
    throw new Error(payload.error?.message || `Request failed (${response.status}).`);
  }
  return payload.data;
}

function setPage(page) {
  if (!pageInfo[page]) return;
  state.page = page;
  document.querySelectorAll("[data-page]").forEach((section) => {
    section.hidden = section.dataset.page !== page;
  });
  document.querySelectorAll("[data-page-nav]").forEach((button) => {
    const active = button.dataset.pageNav === page;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "page" : "false");
  });
  el("page-title").textContent = pageInfo[page][0];
  el("page-subtitle").textContent = pageInfo[page][1];
  if (page === "layout") loadLayout(state.activeLayout);
}

function updateClock() {
  const clock = el("live-clock");
  const now = new Date();
  clock.dateTime = now.toISOString();
  clock.textContent = new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(now);
}

function sortedByEntry(records) {
  return [...records].sort((left, right) => {
    const leftTime = Date.parse(String(left.entry_time || "").replace(" ", "T")) || 0;
    const rightTime = Date.parse(String(right.entry_time || "").replace(" ", "T")) || 0;
    return rightTime - leftTime;
  });
}

function addCell(row, value, className = "") {
  const cell = document.createElement("td");
  cell.textContent = statusText(value) || "—";
  if (className) cell.className = className;
  row.append(cell);
}

function addEmptyRow(body, columns, message) {
  body.replaceChildren();
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.className = "empty-cell";
  cell.colSpan = columns;
  cell.textContent = message;
  row.append(cell);
  body.append(row);
}

function renderRecentActivity(records) {
  const body = el("recent-activity-body");
  const latest = sortedByEntry(records).slice(0, 8);
  if (!latest.length) {
    addEmptyRow(body, 5, "No parking activity is available yet.");
    return;
  }
  body.replaceChildren();
  for (const record of latest) {
    const row = document.createElement("tr");
    addCell(row, record.plate_number);
    addCell(row, record.vehicle_type);
    addCell(row, record.assigned_slot);
    addCell(row, record.entry_time);
    addCell(row, record.status, `record-status ${String(record.status).toLowerCase()}`);
    body.append(row);
  }
}

function renderRecords(records) {
  const body = el("vehicle-records-body");
  const search = el("record-search").value.trim().toLowerCase();
  const type = el("record-type-filter").value;
  const status = el("record-status-filter").value;
  const filtered = sortedByEntry(records).filter((record) => {
    const matchesPlate = String(record.plate_number || "").toLowerCase().includes(search);
    const matchesType = type === "all" || String(record.vehicle_type || "") === type;
    const matchesStatus = status === "all" || String(record.status || "") === status;
    return matchesPlate && matchesType && matchesStatus;
  });
  el("records-count").textContent = `${filtered.length} of ${records.length} records`;
  if (!filtered.length) {
    addEmptyRow(body, 6, "No records match the selected search and filters.");
    return;
  }
  body.replaceChildren();
  for (const record of filtered) {
    const row = document.createElement("tr");
    addCell(row, record.plate_number);
    addCell(row, record.vehicle_type);
    addCell(row, record.entry_time);
    addCell(row, record.assigned_slot);
    addCell(row, record.status, `record-status ${String(record.status).toLowerCase()}`);
    addCell(row, record.exit_time);
    body.append(row);
  }
}

function updateFilterOptions(select, values, label) {
  const selected = select.value;
  const unique = [...new Set(values.map(String).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  select.replaceChildren(new Option(label, "all"));
  for (const value of unique) select.add(new Option(value, value));
  select.value = unique.includes(selected) ? selected : "all";
}

function renderReports(records) {
  const inside = records.filter((record) => String(record.status).toLowerCase() === "inside");
  const exited = records.filter((record) => String(record.status).toLowerCase() === "exited");
  el("report-entries").textContent = String(records.length);
  el("report-exits").textContent = String(exited.length);
  el("report-inside").textContent = String(inside.length);
  el("report-previous").textContent = String(exited.length);

  const body = el("completed-sessions-body");
  const completed = sortedByEntry(exited);
  if (!completed.length) {
    addEmptyRow(body, 6, "No completed parking sessions are available yet.");
    return;
  }
  body.replaceChildren();
  for (const record of completed) {
    const row = document.createElement("tr");
    addCell(row, record.plate_number);
    addCell(row, record.vehicle_type);
    addCell(row, record.assigned_slot);
    addCell(row, record.entry_time);
    addCell(row, record.exit_time);
    addCell(row, durationText(record.entry_time, record.exit_time));
    body.append(row);
  }
}

function durationText(entry, exit) {
  const start = Date.parse(String(entry || "").replace(" ", "T"));
  const end = Date.parse(String(exit || "").replace(" ", "T"));
  if (!Number.isFinite(start) || !Number.isFinite(end)) return "Not available";
  let minutes = Math.max(0, Math.floor((end - start) / 60000));
  const days = Math.floor(minutes / 1440);
  minutes %= 1440;
  const hours = Math.floor(minutes / 60);
  minutes %= 60;
  if (days) return `${days}d ${hours}h ${minutes}m`;
  if (hours) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

async function loadRecords() {
  try {
    const data = await apiData("/api/vehicles");
    state.records = Array.isArray(data.records) ? data.records : [];
    updateFilterOptions(el("record-type-filter"), state.records.map((record) => record.vehicle_type), "All types");
    updateFilterOptions(el("record-status-filter"), state.records.map((record) => record.status), "All statuses");
    renderRecords(state.records);
    renderRecentActivity(state.records);
    renderReports(state.records);
    showFeedback(el("records-feedback"), "");
    return state.records;
  } catch (error) {
    showFeedback(el("records-feedback"), error.message, "error");
    showFeedback(el("global-feedback"), error.message, "error");
    return null;
  }
}

async function loadSummary() {
  try {
    const summary = await apiData("/api/summary");
    state.summary = summary;
    el("summary-total").textContent = String(summary.total_slots ?? 0);
    el("summary-occupied").textContent = String(summary.occupied ?? 0);
    el("summary-available").textContent = String(summary.empty ?? 0);
    const percent = Number(summary.occupancy_percent || 0);
    el("summary-percent").textContent = `${percent.toFixed(1)}%`;
    el("summary-progress").style.width = `${Math.max(0, Math.min(100, percent))}%`;
    el("summary-progress").parentElement.setAttribute("aria-valuenow", String(percent));
    el("summary-progress-label").textContent = `${percent.toFixed(1)}% occupied`;
    const inside = summary.vehicles_inside || {};
    el("inside-cars").textContent = String(inside.cars ?? 0);
    el("inside-buses").textContent = String(inside.buses ?? 0);
    el("inside-motorcycles").textContent = String(inside.motorcycles ?? 0);
    showFeedback(el("global-feedback"), "");
    return summary;
  } catch (error) {
    showFeedback(el("global-feedback"), error.message, "error");
    return null;
  }
}

function projectOutputUrl(path) {
  if (!path) return "";
  const normalized = String(path).replaceAll("\\", "/");
  if (normalized.startsWith("/output/")) return normalized;
  if (normalized.startsWith("output/")) return `/${normalized}`;
  return `/output/${normalized.replace(/^\/+/, "")}`;
}

function showMedia(imageId, url, placeholderText) {
  const image = el(imageId);
  const placeholder = image.nextElementSibling;
  image.onload = () => {
    image.hidden = false;
    placeholder.hidden = true;
  };
  image.onerror = () => {
    image.hidden = true;
    image.removeAttribute("src");
    placeholder.textContent = "Image is not available for this request.";
    placeholder.hidden = false;
  };
  if (!url) {
    image.hidden = true;
    image.removeAttribute("src");
    placeholder.textContent = placeholderText;
    placeholder.hidden = false;
    return;
  }
  placeholder.textContent = "Loading image…";
  placeholder.hidden = false;
  image.hidden = true;
  image.src = projectOutputUrl(url);
}

function showLayoutImage(path) {
  const image = el("layout-image");
  const placeholder = el("layout-image-placeholder");
  image.onload = () => {
    image.hidden = false;
    placeholder.hidden = true;
  };
  image.onerror = () => {
    image.hidden = true;
    image.removeAttribute("src");
    placeholder.textContent = "Layout image is not available.";
    placeholder.hidden = false;
  };
  if (!path) {
    image.hidden = true;
    image.removeAttribute("src");
    placeholder.textContent = "Layout image will appear when the layout loads.";
    placeholder.hidden = false;
    return;
  }
  placeholder.textContent = "Loading layout image…";
  placeholder.hidden = false;
  image.hidden = true;
  const url = projectOutputUrl(path);
  image.src = `${url}${url.includes("?") ? "&" : "?"}t=${Date.now()}`;
}

function renderDetectionResult(data, record) {
  const plate = data.plate_result || {};
  const images = data.images || {};
  showMedia("image-original", images.original, "Original image will appear here after processing.");
  showMedia("image-vehicle-detection", images.vehicle_detection, "Vehicle detection result will appear here after processing.");
  showMedia("image-plate-detection", images.plate_detection, "License plate detection will appear here after processing.");
  showMedia("image-plate-crop", images.plate_crop, "Plate crop will appear here after processing.");
  el("detected-vehicle-type").textContent = data.vehicle_type || "Not available";
  el("detected-plate-number").textContent = plate.plate_number || "Not readable";
  const confidence = data.ocr_confidence ?? plate.confidence;
  el("ocr-confidence").textContent = Number.isFinite(Number(confidence)) ? Number(confidence).toFixed(2) : "Not available";

  const vehicle = record || {};
  el("info-plate").textContent = vehicle.plate_number || plate.plate_number || "Not available";
  el("info-type").textContent = vehicle.vehicle_type || data.vehicle_type || "Not available";
  el("info-status").textContent = vehicle.status || (data.action === "entry" ? "Inside" : "Exited");
  el("info-entry").textContent = vehicle.entry_time || "Not available";
  el("info-slot").textContent = vehicle.assigned_slot || data.assigned_slot || "Not available";
  el("info-exit").textContent = vehicle.exit_time || "Not available";
}

function renderSlots(data) {
  const slots = Array.isArray(data.slots) ? data.slots : [];
  const available = slots.filter((slot) => String(slot.status).toLowerCase() === "empty").length;
  const occupied = slots.filter((slot) => String(slot.status).toLowerCase() === "occupied").length;
  if (available + occupied !== slots.length) {
    showFeedback(el("layout-feedback"), "The layout returned a slot with an unsupported status.", "error");
    return;
  }
  el("layout-total").textContent = String(slots.length);
  el("layout-occupied").textContent = String(occupied);
  el("layout-available").textContent = String(available);
  showLayoutImage(data.selected_layout?.path);

  const groups = new Map();
  const orderedSlots = [...slots].sort((left, right) => {
    const rowOrder = String(left.row).localeCompare(String(right.row), undefined, { numeric: true });
    if (rowOrder) return rowOrder;
    return String(left.column).localeCompare(String(right.column), undefined, { numeric: true });
  });
  for (const slot of orderedSlots) {
    const rowName = String(slot.row || "—");
    if (!groups.has(rowName)) groups.set(rowName, []);
    groups.get(rowName).push(slot);
  }

  const container = el("slot-grid");
  container.replaceChildren();
  for (const [rowName, rowSlots] of groups) {
    const section = document.createElement("section");
    section.className = "slot-row";
    const heading = document.createElement("h3");
    heading.textContent = `Row ${rowName}`;
    const grid = document.createElement("div");
    grid.className = "slot-grid";
    for (const slot of rowSlots) {
      const status = String(slot.status).toLowerCase() === "empty" ? "available" : "occupied";
      const chip = document.createElement("div");
      chip.className = `slot-chip ${status}`;
      if (
        state.lastResult?.action === "entry" &&
        state.lastResult.selected_layout?.category === data.category &&
        String(state.lastResult.assigned_slot) === String(slot.slot)
      ) chip.classList.add("assigned");
      const name = document.createElement("strong");
      name.textContent = String(slot.slot || "—");
      const label = document.createElement("span");
      label.textContent = status === "available" ? "Available" : "Occupied";
      chip.append(name, label);
      grid.append(chip);
    }
    section.append(heading, grid);
    container.append(section);
  }
}

async function loadLayout(category, force = false) {
  state.activeLayout = category;
  document.querySelectorAll("[data-layout-tab]").forEach((tab) => {
    const selected = tab.dataset.layoutTab === category;
    tab.classList.toggle("active", selected);
    tab.setAttribute("aria-selected", String(selected));
  });
  if (!force && state.layouts[category]) {
    renderSlots(state.layouts[category]);
    return;
  }
  showFeedback(el("layout-feedback"), "Loading reconciled slot status…");
  try {
    const data = await apiData(`/api/layouts/${encodeURIComponent(category)}/slots`);
    state.layouts[category] = data;
    renderSlots(data);
    showFeedback(el("layout-feedback"), "");
  } catch (error) {
    showFeedback(el("layout-feedback"), error.message, "error");
  }
}

document.querySelectorAll("[data-page-nav]").forEach((button) => {
  button.addEventListener("click", () => setPage(button.dataset.pageNav));
});
document.querySelectorAll("[data-layout-tab]").forEach((tab) => {
  tab.addEventListener("click", () => loadLayout(tab.dataset.layoutTab));
});
el("record-search").addEventListener("input", () => renderRecords(state.records));
el("record-type-filter").addEventListener("change", () => renderRecords(state.records));
el("record-status-filter").addEventListener("change", () => renderRecords(state.records));

el("vehicle-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = el("vehicle-image").files[0];
  if (!file) {
    showFeedback(el("detection-feedback"), "Choose a vehicle image first.", "error");
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  el("process-button").disabled = true;
  el("process-spinner").hidden = false;
  showFeedback(el("detection-feedback"), "");
  try {
    const result = await apiData("/api/process-vehicle", { method: "POST", body: formData });
    state.lastResult = result;
    const records = await loadRecords();
    const plate = result.plate_result?.plate_number;
    const matches = (records || []).filter((record) => String(record.plate_number).toUpperCase() === String(plate || "").toUpperCase());
    renderDetectionResult(result, matches[matches.length - 1]);
    await loadSummary();
    if (result.action === "entry" && result.selected_layout?.category) {
      const category = result.selected_layout.category;
      state.layouts[category] = null;
      if (state.page === "layout" && state.activeLayout === category) await loadLayout(category, true);
    }
  } catch (error) {
    showFeedback(el("detection-feedback"), error.message, "error");
  } finally {
    el("process-spinner").hidden = true;
    el("process-button").disabled = false;
  }
});

updateClock();
window.setInterval(updateClock, 1000);
loadRecords();
loadSummary();

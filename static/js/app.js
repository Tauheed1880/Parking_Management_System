const state = {
  page: "dashboard",
  records: [],
  summary: null,
  layouts: {},
  activeLayout: "car",
  lastResult: null,
  lastExitResult: null,
};

const pageInfo = {
  dashboard: ["Dashboard", "Current parking activity and capacity."],
  entry: ["Vehicle Entry", "Upload incoming vehicle image to assign parking slot."],
  exit: ["Vehicle Exit", "Upload departing vehicle image to verify fee and authorize exit."],
  records: ["Vehicle Records", "Search and filter the vehicle history."],
  layout: ["Parking Layout", "Review reconciled slot status by vehicle category."],
  reports: ["Parking History / Reports", "Review completed parking sessions."],
};

const statusText = (value) => String(value || "").trim();
const el = (id) => document.getElementById(id);

function showFeedback(element, message, kind = "") {
  if (!element) return;
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
    addEmptyRow(body, 6, "No parking activity is available yet.");
    return;
  }
  body.replaceChildren();
  for (const record of latest) {
    const row = document.createElement("tr");
    addCell(row, record.plate_number);
    addCell(row, record.province || "—");
    addCell(row, record.vehicle_type);
    addCell(row, record.assigned_slot);
    addCell(row, record.entry_time);
    addCell(row, record.status, `record-status ${String(record.status).toLowerCase()}`);
    body.append(row);
  }
}

function displayExitTime(record) {
  if (!record) return "—";
  const status = String(record.status || "").toLowerCase();
  if (status === "inside") return "—";
  return record.exit_time || "—";
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
    addEmptyRow(body, 10, "No records match the selected search and filters.");
    return;
  }
  body.replaceChildren();
  for (const record of filtered) {
    const row = document.createElement("tr");
    addCell(row, record.plate_number);
    addCell(row, record.province || "—");
    addCell(row, record.vehicle_type);
    addCell(row, record.entry_time);
    addCell(row, record.assigned_slot);
    addCell(row, record.status, `record-status ${String(record.status).toLowerCase()}`);
    addCell(row, displayExitTime(record));
    addCell(row, record.total_fee ? `Rs. ${record.total_fee}` : "—");
    addCell(row, record.payment_status || "—", `record-status ${String(record.payment_status || "").toLowerCase()}`);

    const actionCell = document.createElement("td");
    if (record.fee_id && String(record.status).toLowerCase() === "inside") {
      if (String(record.payment_status).toLowerCase() !== "paid") {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "primary-button";
        btn.style.cssText = "min-height: 28px; padding: 4px 8px; font-size: 0.75rem;";
        btn.textContent = "Admin Settle";
        btn.onclick = async () => {
          if (!confirm(`Settle fee of Rs. ${record.total_fee || 0} for ${record.plate_number}?`)) return;
          try {
            await apiData(`/api/fees/${record.fee_id}/pay`, {
              method: "POST",
              headers: { "Content-Type": "application/json", "X-Admin-Action": "demo-admin" },
              body: JSON.stringify({ action: "demo_admin_settlement", admin_token: "demo-admin-override" }),
            });
            await loadRecords();
          } catch (err) {
            alert(err.message);
          }
        };
        actionCell.append(btn);
      } else {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "primary-button";
        btn.style.cssText = "min-height: 28px; padding: 4px 8px; font-size: 0.75rem; background: #2d704e; border-color: #2d704e;";
        btn.textContent = "Confirm Exit";
        btn.onclick = async () => {
          try {
            await apiData(`/api/fees/${record.fee_id}/confirm-exit`, {
              method: "POST",
              headers: { "X-Admin-Action": "demo-admin" },
            });
            await loadRecords();
            await loadSummary();
            const cat = record.layout_id;
            if (cat) {
              state.layouts[cat] = null;
              if (state.page === "layout" && state.activeLayout === cat) await loadLayout(cat, true);
            }
          } catch (err) {
            alert(err.message);
          }
        };
        actionCell.append(btn);
      }
    } else {
      actionCell.textContent = record.status === "Exited" ? "Completed" : "—";
    }
    row.append(actionCell);
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
    addEmptyRow(body, 11, "No completed parking sessions are available yet.");
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
    addCell(row, record.base_fee ? `Rs. ${record.base_fee}` : "—");
    addCell(row, record.additional_fee ? `Rs. ${record.additional_fee}` : "—");
    addCell(row, record.total_fee ? `Rs. ${record.total_fee}` : "—");
    addCell(row, record.payment_status || "Unpaid", `record-status ${String(record.payment_status || "").toLowerCase()}`);

    const actionCell = document.createElement("td");
    if (record.fee_id && String(record.payment_status).toLowerCase() !== "paid") {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "primary-button";
      btn.style.cssText = "min-height: 28px; padding: 4px 10px; font-size: 0.75rem;";
      btn.textContent = "Admin Settle";
      btn.title = "Authorize administrative/demo cash settlement";
      btn.addEventListener("click", async () => {
        if (!confirm(`Settle payment for ${record.plate_number} (Rs. ${record.total_fee || 0}) as authorized admin?`)) return;
        try {
          await apiData(`/api/fees/${record.fee_id}/pay`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-Admin-Action": "demo-admin",
            },
            body: JSON.stringify({ action: "demo_admin_settlement", admin_token: "demo-admin-override" }),
          });
          await loadRecords();
        } catch (err) {
          alert(`Payment update failed: ${err.message}`);
        }
      });
      actionCell.append(btn);
    } else {
      actionCell.textContent = String(record.payment_status).toLowerCase() === "paid" ? "Settled" : "—";
    }
    row.append(actionCell);
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
  if (!image) return;
  const placeholder = image.nextElementSibling;
  image.onload = () => {
    image.hidden = false;
    if (placeholder) placeholder.hidden = true;
  };
  image.onerror = () => {
    image.hidden = true;
    image.removeAttribute("src");
    if (placeholder) {
      placeholder.textContent = "Image is not available for this request.";
      placeholder.hidden = false;
    }
  };
  if (!url) {
    image.hidden = true;
    image.removeAttribute("src");
    if (placeholder) {
      placeholder.textContent = placeholderText;
      placeholder.hidden = false;
    }
    return;
  }
  if (placeholder) {
    placeholder.textContent = "Loading image…";
    placeholder.hidden = false;
  }
  image.hidden = true;
  image.src = projectOutputUrl(url);
}

/* ============================================================
   Vehicle Entry – form handler and result rendering
   ============================================================ */

function renderEntryResult(data, record) {
  const plate = data.plate_result || {};
  const images = data.images || {};
  const fee = data.fee || {};

  showMedia("entry-image-original", images.original, "Original image will appear here after processing.");
  showMedia("entry-image-vehicle-detection", images.vehicle_detection, "Vehicle detection result will appear here after processing.");
  showMedia("entry-image-plate-detection", images.plate_detection, "License plate detection will appear here after processing.");
  showMedia("entry-image-plate-crop", images.plate_crop, "Plate crop will appear here after processing.");

  el("entry-detected-vehicle-type").textContent = data.vehicle_type || "Not available";
  el("entry-detected-plate-number").textContent = plate.plate_number || "Not readable";
  el("entry-detected-province").textContent = plate.province || "—";
  el("entry-assigned-slot-display").textContent = data.assigned_slot || "Not available";
  const confidence = data.ocr_confidence ?? plate.confidence;
  el("entry-ocr-confidence").textContent = Number.isFinite(Number(confidence)) ? Number(confidence).toFixed(2) : "Not available";

  const vehicle = record || {};
  el("entry-info-plate").textContent = vehicle.plate_number || plate.plate_number || "Not available";
  el("entry-info-province").textContent = vehicle.province || plate.province || "—";
  el("entry-info-type").textContent = vehicle.vehicle_type || data.vehicle_type || "Not available";
  el("entry-info-status").textContent = vehicle.status || "Inside";
  el("entry-info-entry").textContent = vehicle.entry_time || fee.entry_time || "Not available";
  el("entry-info-slot").textContent = vehicle.assigned_slot || data.assigned_slot || "Not available";
}

el("entry-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = el("entry-vehicle-image").files[0];
  if (!file) {
    showFeedback(el("entry-detection-feedback"), "Choose a vehicle image first.", "error");
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  el("entry-process-button").disabled = true;
  el("entry-process-spinner").hidden = false;
  showFeedback(el("entry-detection-feedback"), "");
  try {
    const result = await apiData("/api/process-entry", { method: "POST", body: formData });
    state.lastResult = result;
    const records = await loadRecords();
    const plate = result.plate_result?.plate_number;
    const matches = (records || []).filter((r) =>
      String(r.plate_number).toUpperCase() === String(plate || "").toUpperCase()
    );
    renderEntryResult(result, matches[matches.length - 1]);
    await loadSummary();
    if (result.action === "entry" && result.selected_layout?.category) {
      showFeedback(el("entry-detection-feedback"), `Vehicle entry recorded. Slot assigned: ${result.assigned_slot}`, "");
      const category = result.selected_layout.category;
      state.layouts[category] = null;
      if (state.page === "layout" && state.activeLayout === category) await loadLayout(category, true);
    }
  } catch (error) {
    showFeedback(el("entry-detection-feedback"), error.message, "error");
  } finally {
    el("entry-process-spinner").hidden = true;
    el("entry-process-button").disabled = false;
  }
});

/* ============================================================
   Vehicle Exit – form handler, result rendering, action buttons
   ============================================================ */

function renderExitResult(data, record) {
  const plate = data.plate_result || {};
  const images = data.images || {};
  const fee = data.fee || {};
  const vehicle = record || {};

  showMedia("exit-image-original", images.original, "Original image will appear here after processing.");
  showMedia("exit-image-vehicle-detection", images.vehicle_detection, "Vehicle detection result will appear here after processing.");
  showMedia("exit-image-plate-detection", images.plate_detection, "License plate detection will appear here after processing.");
  showMedia("exit-image-plate-crop", images.plate_crop, "Plate crop will appear here after processing.");

  el("exit-detected-vehicle-type").textContent = data.vehicle_type || "Not available";
  el("exit-detected-plate-number").textContent = plate.plate_number || "Not readable";
  const confidence = data.ocr_confidence ?? plate.confidence;
  el("exit-ocr-confidence").textContent = Number.isFinite(Number(confidence)) ? Number(confidence).toFixed(2) : "Not available";

  // Authorization status card and total fee card
  const isBlocked = data.action === "exit_blocked";
  const isAuthorized = data.action === "exit" && data.exit_authorized === true;
  if (isBlocked) {
    el("exit-auth-status-card").textContent = "Payment Blocked";
    el("exit-auth-status-card").style.color = "var(--occupied, #e74c3c)";
  } else if (isAuthorized) {
    el("exit-auth-status-card").textContent = "Payment Paid — Exit Authorized";
    el("exit-auth-status-card").style.color = "var(--available, #2d704e)";
  } else {
    el("exit-auth-status-card").textContent = "—";
    el("exit-auth-status-card").style.color = "";
  }

  const totalFee = fee.total_fee ?? vehicle.total_fee;
  el("exit-total-fee-card").textContent = (totalFee !== undefined && totalFee !== null && totalFee !== "")
    ? `Rs. ${totalFee}`
    : "—";

  // Information grid
  el("exit-info-plate").textContent = vehicle.plate_number || plate.plate_number || "Not available";
  el("exit-info-province").textContent = vehicle.province || plate.province || "—";
  el("exit-info-type").textContent = vehicle.vehicle_type || data.vehicle_type || "Not available";

  if (isBlocked) {
    el("exit-info-status").textContent = "Inside (Exit Blocked)";
  } else if (isAuthorized) {
    el("exit-info-status").textContent = "Exited";
  } else {
    el("exit-info-status").textContent = vehicle.status || "—";
  }

  el("exit-info-entry").textContent = vehicle.entry_time || fee.entry_time || "Not available";
  el("exit-info-slot").textContent = vehicle.assigned_slot || data.assigned_slot || "Not available";

  // Exit time: show actual time only if finalized (exited), otherwise pending message
  if (isBlocked) {
    el("exit-info-exit").textContent = "Not Exited (Pending Payment)";
  } else if (isAuthorized) {
    el("exit-info-exit").textContent = vehicle.exit_time || fee.exit_time || "Just now";
  } else {
    const vehicleStatus = String(vehicle.status || "").toLowerCase();
    if (vehicleStatus === "inside") {
      el("exit-info-exit").textContent = "Not Exited (Pending Payment)";
    } else {
      el("exit-info-exit").textContent = vehicle.exit_time || "—";
    }
  }

  // Duration
  const duration = fee.duration_minutes ?? vehicle.duration_minutes;
  el("exit-info-duration").textContent = (duration !== undefined && duration !== null && duration !== "")
    ? `${duration} min`
    : "—";

  // Fee breakdown
  const baseFee = fee.base_fee ?? vehicle.base_fee;
  el("exit-info-base-fee").textContent = (baseFee !== undefined && baseFee !== null && baseFee !== "")
    ? `Rs. ${baseFee}`
    : "—";

  const additionalFee = fee.additional_fee ?? vehicle.additional_fee;
  el("exit-info-additional-fee").textContent = (additionalFee !== undefined && additionalFee !== null && additionalFee !== "")
    ? `Rs. ${additionalFee}`
    : "—";

  el("exit-info-total-fee").textContent = (totalFee !== undefined && totalFee !== null && totalFee !== "")
    ? `Rs. ${totalFee}`
    : "—";

  const paymentStatus = fee.payment_status || vehicle.payment_status || "Unpaid";
  el("exit-info-payment-status").textContent = paymentStatus;

  // Auth banner
  const banner = el("exit-auth-banner");
  const badge = el("exit-auth-badge");
  const msg = el("exit-auth-msg");
  const bannerSettleBtn = el("exit-banner-settle-btn");
  const bannerConfirmBtn = el("exit-banner-confirm-btn");

  if (isBlocked) {
    banner.hidden = false;
    banner.className = "auth-banner blocked";
    badge.textContent = "Payment Blocked";
    badge.className = "badge-blocked";
    msg.textContent = data.message || "Payment required before exit.";
    bannerSettleBtn.hidden = false;
    bannerConfirmBtn.hidden = true;
  } else if (isAuthorized) {
    banner.hidden = false;
    banner.className = "auth-banner authorized";
    badge.textContent = "Exit Authorized";
    badge.className = "badge-authorized";
    msg.textContent = data.message || "Exit authorized. Parking slot released.";
    bannerSettleBtn.hidden = true;
    bannerConfirmBtn.hidden = true;
  } else {
    banner.hidden = true;
  }

  // Actions panel (bottom of info grid)
  wireExitActions(data, fee, vehicle, plate);
}

function wireExitActions(data, fee, vehicle, plate) {
  const actionsWrap = el("exit-actions");
  const settleBtn = el("exit-settle-btn");
  const confirmBtn = el("exit-confirm-btn");
  if (!actionsWrap || !settleBtn || !confirmBtn) return;

  const feeId = fee.id || vehicle.fee_id;
  const isInside = String(vehicle.status || (data.action === "exit_blocked" ? "Inside" : "")).toLowerCase() === "inside";
  const payment = String(fee.payment_status || vehicle.payment_status || "Unpaid").toLowerCase();

  if (feeId && isInside && payment !== "paid") {
    actionsWrap.hidden = false;
    settleBtn.hidden = false;
    confirmBtn.hidden = true;
    settleBtn.onclick = async () => {
      const total = fee.total_fee || vehicle.total_fee || 0;
      if (!confirm(`Settle payment of Rs. ${total} for ${vehicle.plate_number || plate.plate_number}?`)) return;
      try {
        await apiData(`/api/fees/${feeId}/pay`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Admin-Action": "demo-admin" },
          body: JSON.stringify({ action: "demo_admin_settlement", admin_token: "demo-admin-override" }),
        });
        showFeedback(el("exit-detection-feedback"), "Payment settled (Paid). Ready for departure confirmation.", "");
        fee.payment_status = "Paid";
        if (data.fee) data.fee.payment_status = "Paid";
        const updated = await loadRecords();
        const match = (updated || []).filter((r) =>
          String(r.plate_number).toUpperCase() === String(plate.plate_number || "").toUpperCase() &&
          String(r.status).toLowerCase() === "inside"
        ).pop();
        renderExitResult(data, match || vehicle);
      } catch (err) {
        showFeedback(el("exit-detection-feedback"), err.message, "error");
      }
    };
  } else if (feeId && isInside && payment === "paid") {
    actionsWrap.hidden = false;
    settleBtn.hidden = true;
    confirmBtn.hidden = false;
    confirmBtn.onclick = async () => {
      try {
        await apiData(`/api/fees/${feeId}/confirm-exit`, {
          method: "POST",
          headers: { "X-Admin-Action": "demo-admin" },
        });
        showFeedback(el("exit-detection-feedback"), "Exit confirmed and slot released.", "");
        actionsWrap.hidden = true;
        data.action = "exit";
        data.exit_authorized = true;
        const updated = await loadRecords();
        const match = (updated || []).filter((r) =>
          String(r.plate_number).toUpperCase() === String(plate.plate_number || "").toUpperCase()
        ).pop();
        renderExitResult(data, match || vehicle);
        await loadSummary();
        const cat = data.selected_layout?.category || vehicle.layout_id;
        if (cat) {
          state.layouts[cat] = null;
          if (state.page === "layout" && state.activeLayout === cat) await loadLayout(cat, true);
        }
      } catch (err) {
        showFeedback(el("exit-detection-feedback"), err.message, "error");
      }
    };
  } else {
    actionsWrap.hidden = true;
    settleBtn.hidden = true;
    confirmBtn.hidden = true;
  }
}

// Wire the banner settle button to delegate to the same logic as exit-settle-btn
function wireBannerButtons() {
  el("exit-banner-settle-btn").addEventListener("click", () => {
    const settleBtn = el("exit-settle-btn");
    if (settleBtn && !settleBtn.hidden && settleBtn.onclick) settleBtn.onclick();
  });
  el("exit-banner-confirm-btn").addEventListener("click", () => {
    const confirmBtn = el("exit-confirm-btn");
    if (confirmBtn && !confirmBtn.hidden && confirmBtn.onclick) confirmBtn.onclick();
  });
}

el("exit-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = el("exit-vehicle-image").files[0];
  if (!file) {
    showFeedback(el("exit-detection-feedback"), "Choose a vehicle image first.", "error");
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  el("exit-process-button").disabled = true;
  el("exit-process-spinner").hidden = false;
  showFeedback(el("exit-detection-feedback"), "");
  try {
    const result = await apiData("/api/process-exit", { method: "POST", body: formData });
    state.lastExitResult = result;
    state.lastResult = result;
    const records = await loadRecords();
    const plate = result.plate_result?.plate_number;
    const matches = (records || []).filter((r) =>
      String(r.plate_number).toUpperCase() === String(plate || "").toUpperCase()
    );
    // For blocked exits, pick the Inside match; for authorized exits, pick latest
    let match;
    if (result.action === "exit_blocked") {
      match = matches.filter((r) => String(r.status).toLowerCase() === "inside").pop() || matches[matches.length - 1];
    } else {
      match = matches[matches.length - 1];
    }
    renderExitResult(result, match);
    await loadSummary();

    if (result.action === "exit_blocked") {
      showFeedback(el("exit-detection-feedback"), result.message || "Payment required before exit.", "error");
    } else if (result.action === "exit") {
      showFeedback(el("exit-detection-feedback"), result.message || "Exit authorized. Parking slot released.", "");
      const category = result.selected_layout?.category;
      if (category) {
        state.layouts[category] = null;
        if (state.page === "layout" && state.activeLayout === category) await loadLayout(category, true);
      }
    }
  } catch (error) {
    showFeedback(el("exit-detection-feedback"), error.message, "error");
  } finally {
    el("exit-process-spinner").hidden = true;
    el("exit-process-button").disabled = false;
  }
});

/* ============================================================
   Parking Layout
   ============================================================ */

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

/* ============================================================
   Initialization and event wiring
   ============================================================ */

document.querySelectorAll("[data-page-nav]").forEach((button) => {
  button.addEventListener("click", () => setPage(button.dataset.pageNav));
});
document.querySelectorAll("[data-layout-tab]").forEach((tab) => {
  tab.addEventListener("click", () => loadLayout(tab.dataset.layoutTab));
});
el("record-search").addEventListener("input", () => renderRecords(state.records));
el("record-type-filter").addEventListener("change", () => renderRecords(state.records));
el("record-status-filter").addEventListener("change", () => renderRecords(state.records));

wireBannerButtons();

updateClock();
window.setInterval(updateClock, 1000);
loadRecords();
loadSummary();

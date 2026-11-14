"use strict";

const state = {
  translations: {},
  user: null,
  activeModule: "dashboard",
  products: [],
  warehouses: [],
  parties: [],
  accounts: [],
  transactions: [],
  tickets: [],
  documents: [],
  noticeTimer: 0,
  alertTimer: 0,
  searchRequest: 0,
  searchTimer: 0,
  commandResults: [],
  workspace: {
    branch: "central",
    fiscalYear: "2026",
  },
};

const optionGroups = {
  priorities: ["low", "normal", "high", "urgent"],
  payments: ["cash", "card", "bank_transfer", "credit"],
  currencies: ["TRY", "USD", "EUR"],
  partyTypes: ["customer", "supplier", "both"],
  transactionTypes: ["income", "expense", "transfer", "sale_payment", "purchase_payment"],
  documentTypes: ["quote", "invoice"],
  documentStatuses: ["draft", "sent", "accepted", "paid", "overdue", "cancelled"],
};

function t(key, params = {}) {
  let value = state.translations;
  for (const part of key.split(".")) value = value && value[part];
  if (typeof value !== "string") return key;
  return value.replace(/\{([^}]+)\}/g, (_, name) =>
    Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : `{${name}}`
  );
}

function translateDocument() {
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    const value = t(element.dataset.i18n);
    if (value !== element.dataset.i18n) element.textContent = value;
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    element.placeholder = t(element.dataset.i18nPlaceholder);
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
    element.setAttribute("aria-label", t(element.dataset.i18nAriaLabel));
  });
  document.querySelectorAll("[data-options]").forEach((select) => {
    const values = optionGroups[select.dataset.options] || [];
    fillSelect(select, values.map((value) => [value, t(`options.${value}`)]));
  });
  document.getElementById("app-version").textContent = t("app.version");
}

async function loadTranslations() {
  const response = await fetch("/api/locales/tr.json", { cache: "no-store" });
  if (!response.ok) throw new Error(t("messages.connection_error"));
  state.translations = await response.json();
  translateDocument();
}

function fillSelect(select, options, placeholder = null, selectedValue = undefined) {
  if (!select) return;
  const previous = selectedValue === undefined ? select.value : String(selectedValue);
  const fragment = document.createDocumentFragment();
  if (placeholder) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = placeholder;
    fragment.append(option);
  }
  for (const [value, label] of options) {
    const option = document.createElement("option");
    option.value = String(value);
    option.textContent = String(label);
    fragment.append(option);
  }
  select.replaceChildren(fragment);
  if ([...select.options].some((option) => option.value === previous)) {
    select.value = previous;
  } else if (select.options.length) {
    select.selectedIndex = 0;
  }
}

function money(cents, currency = "TRY") {
  const value = Number(cents || 0) / 100;
  return new Intl.NumberFormat("tr-TR", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(value);
}

function localDate(daysAgo = 0) {
  const date = new Date();
  date.setDate(date.getDate() - daysAgo);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 10);
}

function dateLabel(value, includeTime = false) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString("tr-TR", includeTime
    ? { dateStyle: "short", timeStyle: "short" }
    : { dateStyle: "medium" });
}

function statusLabel(value, group = "status") {
  return t(`${group}.${value}`);
}

function appendCell(row, value, className = "") {
  const cell = document.createElement("td");
  if (value instanceof Node) cell.append(value);
  else cell.textContent = value == null || value === "" ? "—" : String(value);
  if (className) cell.className = className;
  row.append(cell);
  return cell;
}

function primaryText(value, secondary = "") {
  const wrapper = document.createElement("span");
  const main = document.createElement("strong");
  main.className = "table-primary";
  main.textContent = value || "—";
  wrapper.append(main);
  if (secondary) {
    const detail = document.createElement("small");
    detail.className = "table-secondary";
    detail.textContent = secondary;
    wrapper.append(detail);
  }
  return wrapper;
}

function statusBadge(value, group = "status") {
  const badge = document.createElement("span");
  badge.className = "badge";
  if (["completed", "delivered", "paid", "received", "in_stock"].includes(value)) {
    badge.classList.add("badge-success");
  } else if (["urgent", "overdue", "cancelled", "defective"].includes(value)) {
    badge.classList.add("badge-danger");
  } else if (["waiting_parts", "draft", "reserved"].includes(value)) {
    badge.classList.add("badge-warning");
  } else {
    badge.classList.add("badge-blue");
  }
  badge.textContent = statusLabel(value, group);
  return badge;
}

function renderEmpty(target, columns, message) {
  const row = document.createElement("tr");
  const cell = appendCell(row, message, "empty-cell");
  cell.colSpan = columns;
  target.replaceChildren(row);
}

function announce(message, failed = false) {
  const notice = document.getElementById("notice");
  window.clearTimeout(state.noticeTimer);
  notice.textContent = message;
  notice.classList.toggle("error", failed);
  notice.hidden = !message;
  if (message) {
    state.noticeTimer = window.setTimeout(() => {
      notice.hidden = true;
      notice.textContent = "";
    }, 5000);
  }
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body) headers.set("Content-Type", "application/json");
  if (state.user) headers.set("x-current-user", JSON.stringify(state.user));
  let response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch {
    throw new Error(t("messages.connection_error"));
  }
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    if (response.status === 401) throw new Error(t("auth.invalid"));
    if (response.status === 403) throw new Error(t("messages.api_error"));
    throw new Error(`${t("messages.api_error")} (${response.status})`);
  }
  return data;
}

function showLogin(show) {
  document.getElementById("login-layer").hidden = !show;
  document.querySelectorAll(".nav-item, #refresh-button, #command-button, #notification-button, #backup-button").forEach((element) => {
    element.disabled = show;
  });
}

function updateWorkspaceContext(branch, fiscalYear) {
  const validBranches = ["central", "technical_service"];
  const validFiscalYears = ["2026"];
  state.workspace.branch = validBranches.includes(branch) ? branch : "central";
  state.workspace.fiscalYear = validFiscalYears.includes(String(fiscalYear))
    ? String(fiscalYear)
    : "2026";
  document.getElementById("workspace-context").textContent =
    `${t(`auth.branches.${state.workspace.branch}`)} · ${state.workspace.fiscalYear}`;
  const form = document.getElementById("login-form");
  if (form) {
    form.elements.namedItem("branch").value = state.workspace.branch;
    form.elements.namedItem("fiscal_year").value = state.workspace.fiscalYear;
  }
}

function restoreWorkspaceContext() {
  try {
    const stored = JSON.parse(sessionStorage.getItem("lavox_workspace") || "null");
    if (stored && typeof stored === "object") {
      updateWorkspaceContext(stored.branch, stored.fiscalYear);
      return;
    }
  } catch {
    sessionStorage.removeItem("lavox_workspace");
  }
  updateWorkspaceContext("central", "2026");
}

function notifyDesktopReady() {
  const reportReady = () => {
    const desktopApi = window.pywebview && window.pywebview.api;
    if (desktopApi && typeof desktopApi.report_ready === "function") {
      desktopApi.report_ready();
    }
  };
  if (window.pywebview && window.pywebview.api) reportReady();
  else window.addEventListener("pywebviewready", reportReady, { once: true });
}

function setUser(user) {
  state.user = user ? {
    id: Number(user.id),
    username: String(user.username),
    role: String(user.role),
  } : null;
  if (state.user) sessionStorage.setItem("lavox_user", JSON.stringify(state.user));
  else sessionStorage.removeItem("lavox_user");
  document.getElementById("user-name").textContent = state.user ? state.user.username : "LAVOX";
  document.getElementById("user-role").textContent = state.user
    ? statusLabel(state.user.role, "roles")
    : t("auth.welcome");
  document.getElementById("user-avatar").textContent = state.user
    ? state.user.username.slice(0, 1).toLocaleUpperCase("tr-TR")
    : "L";
  document.getElementById("backup-button").hidden =
    !state.user || state.user.role !== "Admin";
  if (!state.user && state.alertTimer) {
    window.clearInterval(state.alertTimer);
    state.alertTimer = 0;
  }
  if (!state.user) {
    document.getElementById("notification-popover").hidden = true;
    document.getElementById("notification-button").setAttribute("aria-expanded", "false");
  }
  showLogin(!state.user);
}

function setActiveModule(module) {
  if (!document.querySelector(`[data-view="${module}"]`)) return;
  state.activeModule = module;
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("active", button.dataset.module === module);
  });
  document.querySelectorAll(".module-view").forEach((view) => {
    const active = view.dataset.view === module;
    view.hidden = !active;
    view.classList.toggle("active", active);
  });
  document.getElementById("page-title").textContent = t(`nav.${module}`);
  document.getElementById("page-heading").textContent = t(`nav.${module}`);
  document.getElementById("page-description").textContent = t(`modules.${module}`);
  loadModule(module).catch((error) => announce(error.message, true));
}

function setFilterOptions() {
  fillSelect(document.getElementById("serial-status"), [
    ["", t("serials.all_statuses")],
    ...["in_stock", "sold", "reserved", "in_repair", "returned", "defective"]
      .map((value) => [value, statusLabel(value)]),
  ]);
  fillSelect(document.getElementById("service-status"), [
    ["", t("service.all_statuses")],
    ...["intake", "diagnosis", "waiting_parts", "repairing", "quality_control", "completed", "delivered", "cancelled"]
      .map((value) => [value, statusLabel(value)]),
  ]);
  fillSelect(document.getElementById("party-type"), [
    ["", t("parties.all")],
    ...["customer", "supplier", "both"].map((value) => [value, t(`parties.${value}`)]),
  ]);
  document.getElementById("today-label").textContent =
    new Intl.DateTimeFormat("tr-TR", { dateStyle: "full" }).format(new Date());
  document.querySelector('#report-form [name="start_date"]').value = localDate(30);
  document.querySelector('#report-form [name="end_date"]').value = localDate();
  document.querySelector('#document-form [name="issue_date"]').value = localDate();
}

async function loadLookups() {
  const [warehouses, products, parties, accounts] = await Promise.all([
    api("/api/warehouses"),
    api("/api/products"),
    api("/api/parties"),
    api("/api/accounts"),
  ]);
  state.warehouses = warehouses;
  state.products = products;
  state.parties = parties;
  state.accounts = accounts;
  populateLookupSelects();
}

function populateLookupSelects() {
  const warehouses = state.warehouses.map((item) => [item.id, `${item.name} · ${item.code}`]);
  const products = state.products.map((item) => [item.id, `${item.name} · ${item.sku}`]);
  const customers = state.parties
    .filter((party) => ["customer", "both"].includes(party.type))
    .map((party) => [party.code, `${party.code} · ${party.name}`]);
  const suppliers = state.parties
    .filter((party) => ["supplier", "both"].includes(party.type))
    .map((party) => [party.code, `${party.code} · ${party.name}`]);

  const inventoryWarehouse = document.getElementById("inventory-warehouse");
  const previousWarehouse = inventoryWarehouse.value;
  fillSelect(inventoryWarehouse, [
    ["", t("inventory.warehouse_all")],
    ...warehouses,
  ], null, previousWarehouse || (state.warehouses[0] && state.warehouses[0].id));
  for (const select of document.querySelectorAll('#transfer-form select[name="from_warehouse_id"], #transfer-form select[name="to_warehouse_id"], #sale-form select[name="warehouse_id"], #purchase-form select[name="warehouse_id"]')) {
    fillSelect(select, warehouses, t("messages.required_data"));
  }
  fillSelect(document.querySelector('#sale-form select[name="customer_code"]'), customers, t("sales.no_customer"));
  fillSelect(document.querySelector('#document-form select[name="customer_code"]'), customers, t("messages.required_data"));
  fillSelect(document.querySelector('#purchase-form select[name="supplier_code"]'), suppliers, t("purchasing.no_supplier"));
  fillSelect(document.querySelector('#transaction-form select[name="account_id"]'),
    state.accounts.map((account) => [account.id, `${account.name} · ${account.currency}`]),
    t("finance.empty_accounts"));
  populateLineProductSelects();
}

function populateLineProductSelects() {
  for (const select of document.querySelectorAll(".line-product")) {
    const selected = select.value;
    fillSelect(select, state.products.map((product) => [
      product.id,
      `${product.name} · ${product.sku}`,
    ]), t("messages.required_data"), selected);
  }
}

async function loadModule(module) {
  const loaders = {
    dashboard: loadDashboard,
    inventory: loadInventory,
    serials: loadSerials,
    service: loadService,
    sales: loadSales,
    purchasing: loadPurchasing,
    parties: loadParties,
    finance: loadFinance,
    documents: loadDocuments,
    analytics: loadAnalytics,
  };
  const view = document.getElementById(`view-${module}`);
  const indicator = document.getElementById("module-loading");
  view.setAttribute("aria-busy", "true");
  indicator.hidden = false;
  try {
    await loaders[module]();
  } finally {
    view.removeAttribute("aria-busy");
    indicator.hidden = true;
  }
}

async function loadDashboard() {
  const start = localDate(6);
  const end = localDate();
  const [kpis, alerts, overdue, trend] = await Promise.all([
    api("/api/analytics/kpis"),
    api("/api/alerts/critical-stock"),
    api("/api/analytics/overdue-payments"),
    api(`/api/analytics/profit-loss?start_date=${start}&end_date=${end}`),
  ]);
  document.getElementById("kpi-today-sales").textContent = money(kpis.today_sales_cents);
  document.getElementById("kpi-sale-count").textContent =
    t("analytics.sale_count", { count: kpis.today_sales_count });
  document.getElementById("kpi-month-sales").textContent = money(kpis.month_sales_cents);
  document.getElementById("kpi-month-count").textContent =
    t("analytics.sale_count", { count: kpis.month_sales_count });
  document.getElementById("kpi-open-service").textContent = kpis.open_service_tickets;
  document.getElementById("kpi-net-cash").textContent = money(kpis.month_net_cents);
  document.getElementById("dashboard-month-total").textContent = money(kpis.month_sales_cents);
  document.getElementById("dashboard-month-meta").textContent =
    t("analytics.sale_count", { count: kpis.month_sales_count });
  document.getElementById("low-stock-count").textContent = alerts.length;
  document.getElementById("low-stock-summary").textContent = alerts.length
    ? t("dashboard.low_stock_hint", { count: alerts.length })
    : t("inventory.empty_critical");
  document.getElementById("overdue-count").textContent = overdue.length;
  document.getElementById("overdue-summary").textContent = overdue.length
    ? t("dashboard.overdue_hint", { count: overdue.length })
    : t("dashboard.empty_alerts");
  document.getElementById("completed-repairs").textContent = kpis.completed_repairs;
  renderDashboardStock(alerts);
  renderSalesBars(trend.daily_sales);
}

function renderDashboardStock(products) {
  const target = document.getElementById("dashboard-low-stock");
  if (!products.length) {
    renderEmpty(target, 5, t("inventory.empty_critical"));
    return;
  }
  target.replaceChildren();
  for (const product of products.slice(0, 8)) {
    const row = document.createElement("tr");
    appendCell(row, primaryText(product.name, product.sku));
    appendCell(row, product.category);
    appendCell(row, product.warehouse_name || "—");
    appendCell(row, product.current_stock, Number(product.current_stock) <= Number(product.critical_stock_level) ? "cell-warning" : "");
    appendCell(row, product.critical_stock_level);
    target.append(row);
  }
}

function renderSalesBars(days) {
  const target = document.getElementById("sales-bars");
  target.replaceChildren();
  const byDay = new Map(days.map((day) => [day.day, day.sales_cents]));
  const range = [];
  for (let offset = 6; offset >= 0; offset -= 1) {
    const day = localDate(offset);
    range.push({ day, value: Number(byDay.get(day) || 0) });
  }
  const maximum = Math.max(1, ...range.map((item) => item.value));
  for (const item of range) {
    const column = document.createElement("div");
    column.className = "bar-column";
    const fill = document.createElement("span");
    fill.className = "bar-fill";
    fill.style.height = `${Math.max(4, item.value / maximum * 100)}%`;
    fill.title = `${item.day}: ${money(item.value)}`;
    const label = document.createElement("small");
    label.textContent = item.day.slice(5);
    column.append(fill, label);
    target.append(column);
  }
}

async function loadInventory() {
  if (!state.warehouses.length) await loadLookups();
  const warehouseId = document.getElementById("inventory-warehouse").value;
  const url = warehouseId
    ? `/api/products?warehouse_id=${encodeURIComponent(warehouseId)}`
    : "/api/products";
  const [products, alerts] = await Promise.all([
    api(url),
    api("/api/alerts/critical-stock"),
  ]);
  state.products = products;
  document.getElementById("inventory-count").textContent =
    t("inventory.count", { count: products.length });
  renderProducts(products, alerts);
  populateLineProductSelects();
}

function renderProducts(products, alerts = []) {
  const target = document.getElementById("products-table");
  const query = document.getElementById("product-search").value.trim().toLocaleLowerCase("tr-TR");
  const alertIds = new Set(alerts.map((item) => Number(item.id)));
  const filtered = products.filter((product) =>
    `${product.name} ${product.sku} ${product.category} ${product.brand}`
      .toLocaleLowerCase("tr-TR").includes(query));
  if (!filtered.length) {
    renderEmpty(target, 5, t("inventory.empty_products"));
    return;
  }
  target.replaceChildren();
  for (const product of filtered) {
    const row = document.createElement("tr");
    appendCell(row, primaryText(product.name, `${product.sku} · ${product.brand}`));
    appendCell(row, product.category);
    appendCell(row, product.warehouse_name || t("inventory.warehouse_all"));
    appendCell(row, product.current_stock, alertIds.has(Number(product.id)) ? "cell-warning" : "");
    appendCell(row, money(product.unit_price_cents));
    target.append(row);
  }
}

async function loadSerials() {
  const params = new URLSearchParams();
  const status = document.getElementById("serial-status").value;
  if (status) params.set("status", status);
  const rows = await api(`/api/serials${params.size ? `?${params}` : ""}`);
  const target = document.getElementById("serials-table");
  const query = document.getElementById("serial-search").value.trim().toLocaleLowerCase("tr-TR");
  const filtered = rows.filter((serial) =>
    `${serial.serial_number} ${serial.imei || ""} ${serial.product_name || ""}`
      .toLocaleLowerCase("tr-TR").includes(query));
  if (!filtered.length) {
    renderEmpty(target, 6, t("serials.empty"));
    return;
  }
  const productMap = new Map(state.products.map((product) => [Number(product.id), product]));
  const warehouseMap = new Map(state.warehouses.map((warehouse) => [Number(warehouse.id), warehouse]));
  target.replaceChildren();
  for (const serial of filtered) {
    const row = document.createElement("tr");
    const product = productMap.get(Number(serial.product_id));
    const warehouse = warehouseMap.get(Number(serial.warehouse_id));
    appendCell(row, primaryText(serial.serial_number, product ? product.sku : ""));
    appendCell(row, product ? product.name : "—");
    appendCell(row, warehouse ? warehouse.code : "—");
    appendCell(row, statusBadge(serial.status));
    appendCell(row, serial.warranty_end_date ? dateLabel(serial.warranty_end_date) : t("serials.no_warranty_date"));
    appendCell(row, serial.imei ? `${serial.imei.slice(0, 3)}••••••${serial.imei.slice(-2)}` : "—");
    target.append(row);
  }
}

async function loadService() {
  const status = document.getElementById("service-status").value;
  const tickets = await api(`/api/service-tickets${status ? `?status=${encodeURIComponent(status)}` : ""}`);
  state.tickets = tickets;
  const target = document.getElementById("service-table");
  const query = document.getElementById("service-search").value.trim().toLocaleLowerCase("tr-TR");
  const filtered = tickets.filter((ticket) =>
    `${ticket.ticket_number} ${ticket.customer_name} ${ticket.device_brand} ${ticket.device_model} ${ticket.serial_number || ""}`
      .toLocaleLowerCase("tr-TR").includes(query));
  if (!filtered.length) {
    renderEmpty(target, 6, t("service.empty"));
    return;
  }
  target.replaceChildren();
  for (const ticket of filtered) {
    const row = document.createElement("tr");
    appendCell(row, primaryText(ticket.ticket_number, dateLabel(ticket.intake_date)));
    appendCell(row, ticket.customer_name);
    appendCell(row, primaryText(`${ticket.device_brand} ${ticket.device_model}`, ticket.serial_number || ""));
    appendCell(row, statusBadge(ticket.priority, "priority"));
    const statusCell = appendCell(row, "");
    statusCell.replaceChildren(statusBadge(ticket.status));
    const actions = document.createElement("div");
    actions.className = "toolbar-inline";
    const statusSelect = document.createElement("select");
    statusSelect.className = "row-status-select";
    fillSelect(statusSelect,
      ["intake", "diagnosis", "waiting_parts", "repairing", "quality_control", "completed", "delivered", "cancelled"]
        .map((value) => [value, statusLabel(value)]),
      null, ticket.status);
    const updateButton = document.createElement("button");
    updateButton.type = "button";
    updateButton.className = "button button-secondary button-small";
    updateButton.textContent = t("actions.update");
    updateButton.addEventListener("click", () =>
      updateTicketStatus(ticket.id, statusSelect.value));
    const receiptButton = document.createElement("button");
    receiptButton.type = "button";
    receiptButton.className = "button button-quiet button-small";
    receiptButton.textContent = t("service.print_receipt");
    receiptButton.addEventListener("click", () =>
      loadReceipt(ticket.id).catch((error) => announce(error.message, true)));
    const messageButton = document.createElement("button");
    messageButton.type = "button";
    messageButton.className = "button button-quiet button-small";
    messageButton.textContent = t("service.whatsapp");
    messageButton.addEventListener("click", () => openServiceMessage(ticket));
    actions.append(statusSelect, updateButton, receiptButton, messageButton);
    appendCell(row, actions);
    target.append(row);
  }
}

async function updateTicketStatus(id, status) {
  await api(`/api/service-tickets/${id}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
  announce(t("service.updated"));
  await loadService();
}

async function loadReceipt(id) {
  const result = await api(`/api/service-tickets/${id}/receipt`);
  const panel = document.getElementById("service-receipt");
  panel.hidden = false;
  panel.replaceChildren();
  const heading = document.createElement("h2");
  heading.textContent = t("service.receipt_title");
  const detail = document.createElement("p");
  detail.className = "muted";
  detail.textContent = `${result.ticket.ticket_number} · ${result.ticket.device_brand} ${result.ticket.device_model} · ${money(result.ticket.final_cost_cents)}`;
  const description = document.createElement("p");
  description.textContent = result.ticket.problem_description;
  panel.append(heading, detail, description);
  openPrintReceipt(result);
}

async function loadSales() {
  const sales = await api("/api/pos-sales?limit=100");
  const target = document.getElementById("sales-table");
  if (!sales.length) {
    renderEmpty(target, 4, t("sales.empty"));
    return;
  }
  target.replaceChildren();
  for (const sale of sales) {
    const row = document.createElement("tr");
    appendCell(row, primaryText(sale.sale_number, statusLabel(sale.payment_method, "options")));
    appendCell(row, sale.customer_code || t("sales.no_customer"));
    appendCell(row, money(sale.total_cents, sale.currency));
    appendCell(row, dateLabel(sale.created_at, true));
    target.append(row);
  }
}

function addLine(container, type) {
  const row = document.createElement("div");
  row.className = "line-item";
  row.classList.add(type === "sale" ? "sale-line" : "simple-line");
  const productLabel = document.createElement("label");
  productLabel.textContent = t("labels.product");
  const productSelect = document.createElement("select");
  productSelect.className = "line-product";
  productSelect.required = true;
  productLabel.append(productSelect);

  const quantityLabel = document.createElement("label");
  quantityLabel.textContent = t("labels.amount");
  const quantity = document.createElement("input");
  quantity.type = "number";
  quantity.min = "1";
  quantity.step = "1";
  quantity.value = "1";
  quantity.required = true;
  quantity.className = "line-quantity";
  quantityLabel.append(quantity);

  const priceLabel = document.createElement("label");
  priceLabel.textContent = t("labels.unit_price");
  const price = document.createElement("input");
  price.type = "number";
  price.min = "0";
  price.step = "0.01";
  price.required = true;
  price.className = "line-price";
  priceLabel.append(price);

  const discountLabel = document.createElement("label");
  discountLabel.className = "line-discount";
  discountLabel.textContent = t("labels.discount");
  const discount = document.createElement("input");
  discount.type = "number";
  discount.min = "0";
  discount.step = "0.01";
  discount.value = "0";
  discount.className = "line-discount-value";
  discountLabel.append(discount);

  let serialLabel = null;
  if (type === "sale") {
    serialLabel = document.createElement("label");
    serialLabel.className = "line-serial";
    serialLabel.hidden = true;
    serialLabel.textContent = t("labels.serial");
    const serial = document.createElement("input");
    serial.className = "line-serial-value";
    serial.maxLength = 64;
    serialLabel.append(serial);
  }

  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "remove-line";
  remove.setAttribute("aria-label", t("actions.remove_line"));
  remove.textContent = "×";
  remove.addEventListener("click", () => {
    if (container.children.length > 1) row.remove();
  });

  productSelect.addEventListener("change", () => {
    const product = state.products.find((item) => String(item.id) === productSelect.value);
    if (product) price.value = (Number(product.unit_price_cents) / 100).toFixed(2);
    if (serialLabel) {
      const needsSerial = Boolean(product && product.is_tracked_serial);
      serialLabel.hidden = !needsSerial;
      serialLabel.querySelector("input").required = needsSerial;
      if (needsSerial) quantity.value = "1";
    }
  });
  row.append(productLabel, quantityLabel, priceLabel, discountLabel);
  if (serialLabel) row.append(serialLabel);
  row.append(remove);
  container.append(row);
  populateLineProductSelects();
}

function lineItems(container, includeDiscount = false) {
  return [...container.querySelectorAll(".line-item")].map((row) => {
    const item = {
      product_id: Number(row.querySelector(".line-product").value),
      quantity: Number(row.querySelector(".line-quantity").value),
      unit_price: row.querySelector(".line-price").value,
    };
    if (includeDiscount) item.discount = row.querySelector(".line-discount-value").value || 0;
    const serialInput = row.querySelector(".line-serial-value");
    if (serialInput && !row.querySelector(".line-serial").hidden) {
      item.serial_number = serialInput.value.trim().toUpperCase();
      if (item.quantity !== 1) throw new Error(t("sales.serial_quantity"));
    }
    if (!item.product_id || !Number.isSafeInteger(item.quantity) || item.quantity < 1) {
      throw new Error(t("messages.api_error"));
    }
    return item;
  });
}

async function loadPurchasing() {
  const orders = await api("/api/purchase-orders?limit=100");
  const target = document.getElementById("purchase-table");
  if (!orders.length) {
    renderEmpty(target, 6, t("purchasing.empty"));
    return;
  }
  target.replaceChildren();
  for (const order of orders) {
    const row = document.createElement("tr");
    appendCell(row, primaryText(order.po_number, dateLabel(order.created_at)));
    appendCell(row, order.supplier_code);
    appendCell(row, money(order.total_cents));
    appendCell(row, dateLabel(order.expected_date));
    appendCell(row, statusBadge(order.status));
    const action = document.createElement("td");
    if (order.status !== "received" && order.status !== "cancelled") {
      const receive = document.createElement("button");
      receive.type = "button";
      receive.className = "button button-secondary button-small";
      receive.textContent = t("purchasing.receive");
      receive.addEventListener("click", () => receiveOrder(order.id));
      action.append(receive);
    } else {
      action.textContent = "—";
    }
    row.append(action);
    target.append(row);
  }
}

async function receiveOrder(id) {
  await api(`/api/purchase-orders/${id}/receive`, { method: "POST" });
  announce(t("purchasing.received"));
  await Promise.all([loadPurchasing(), loadLookups()]);
}

async function loadParties() {
  const type = document.getElementById("party-type").value;
  const parties = await api(`/api/parties${type ? `?party_type=${encodeURIComponent(type)}` : ""}`);
  state.parties = parties;
  const target = document.getElementById("parties-table");
  const query = document.getElementById("party-search").value.trim().toLocaleLowerCase("tr-TR");
  const filtered = parties.filter((party) =>
    `${party.code} ${party.name} ${party.city || ""}`.toLocaleLowerCase("tr-TR").includes(query));
  if (!filtered.length) {
    renderEmpty(target, 5, t("parties.empty"));
    return;
  }
  target.replaceChildren();
  for (const party of filtered) {
    const row = document.createElement("tr");
    appendCell(row, primaryText(party.name, party.code));
    appendCell(row, statusLabel(party.type, "parties"));
    appendCell(row, party.city || "—");
    appendCell(row, money(party.balance_cents));
    appendCell(row, money(party.credit_limit_cents));
    target.append(row);
  }
}

async function loadFinance() {
  const [accounts, transactions] = await Promise.all([
    api("/api/accounts"),
    api("/api/transactions?limit=100"),
  ]);
  state.accounts = accounts;
  state.transactions = transactions;
  populateLookupSelects();
  renderAccounts(accounts);
  renderTransactions(transactions);
}

function renderAccounts(accounts) {
  const target = document.getElementById("account-cards");
  target.replaceChildren();
  if (!accounts.length) {
    const empty = document.createElement("p");
    empty.className = "empty-cell";
    empty.textContent = t("finance.empty_accounts");
    target.append(empty);
    return;
  }
  for (const account of accounts) {
    const card = document.createElement("article");
    card.className = "account-card";
    const name = document.createElement("span");
    name.textContent = account.name;
    const balance = document.createElement("strong");
    balance.textContent = money(account.balance_cents, account.currency);
    const type = document.createElement("small");
    type.textContent = `${account.type === "cash" ? t("options.cash") : t("options.bank_transfer")} · ${t(`options.${account.currency}`)}`;
    card.append(name, balance, type);
    target.append(card);
  }
}

function renderTransactions(transactions) {
  const target = document.getElementById("transactions-table");
  if (!transactions.length) {
    renderEmpty(target, 5, t("finance.empty_transactions"));
    return;
  }
  target.replaceChildren();
  for (const transaction of transactions) {
    const row = document.createElement("tr");
    appendCell(row, dateLabel(transaction.created_at, true));
    appendCell(row, transaction.account_name);
    appendCell(row, statusLabel(transaction.type, "finance"));
    appendCell(row, money(transaction.amount_cents, transaction.currency));
    appendCell(row, t(`options.${transaction.currency}`));
    target.append(row);
  }
}

async function loadDocuments() {
  const documents = await api("/api/documents?limit=100");
  state.documents = documents;
  const target = document.getElementById("documents-table");
  if (!documents.length) {
    renderEmpty(target, 7, t("documents.empty"));
    return;
  }
  target.replaceChildren();
  for (const documentRow of documents) {
    const row = document.createElement("tr");
    appendCell(row, primaryText(documentRow.document_number, dateLabel(documentRow.issue_date)));
    appendCell(row, t(`documents.${documentRow.type}`));
    appendCell(row, documentRow.customer_code);
    appendCell(row, money(documentRow.total_cents, documentRow.currency));
    appendCell(row, dateLabel(documentRow.due_date));
    appendCell(row, statusBadge(documentRow.status));
    const action = document.createElement("td");
    const printButton = document.createElement("button");
    printButton.type = "button";
    printButton.className = "button button-quiet button-small";
    printButton.textContent = t("actions.print_pdf");
    printButton.addEventListener("click", () => openDocumentPrint(documentRow));
    action.append(printButton);
    if (documentRow.type === "quote" && !["cancelled", "paid"].includes(documentRow.status)) {
      const convert = document.createElement("button");
      convert.type = "button";
      convert.className = "button button-secondary button-small";
      convert.textContent = t("documents.convert");
      convert.addEventListener("click", () => convertQuote(documentRow.id));
      action.append(document.createTextNode(" "), convert);
    }
    row.append(action);
    target.append(row);
  }
}

async function convertQuote(id) {
  await api(`/api/documents/${id}/convert`, { method: "POST" });
  announce(t("documents.converted"));
  await loadDocuments();
}

async function loadAnalytics() {
  const [overdue, defects] = await Promise.all([
    api("/api/analytics/overdue-payments"),
    api("/api/analytics/defective-devices"),
  ]);
  renderOverdue(overdue);
  renderDefects(defects);
  await runReport();
}

async function runReport() {
  const form = document.getElementById("report-form");
  const data = Object.fromEntries(new FormData(form));
  if (data.end_date < data.start_date) throw new Error(t("messages.invalid_report_dates"));
  const query = new URLSearchParams(data);
  const report = await api(`/api/analytics/profit-loss?${query}`);
  renderReport(report);
}

function renderReport(report) {
  const target = document.getElementById("report-results");
  const metrics = [
    ["analytics.sales", money(report.sales_cents)],
    ["analytics.purchases", money(report.purchase_cents)],
    ["analytics.gross_profit", money(report.gross_profit_cents)],
    ["analytics.cash_income", money(report.cash_income_cents)],
    ["analytics.cash_expense", money(report.cash_expense_cents)],
    ["analytics.net_profit", money(report.net_profit_cents)],
  ];
  target.replaceChildren();
  for (const [labelKey, value] of metrics) {
    const card = document.createElement("article");
    card.className = "panel report-card";
    const label = document.createElement("span");
    label.textContent = t(labelKey);
    const amount = document.createElement("strong");
    amount.textContent = value;
    card.append(label, amount);
    target.append(card);
  }
  const note = document.createElement("p");
  note.className = "report-note";
  note.textContent = `${t("analytics.period", { start: dateLabel(report.start_date), end: dateLabel(report.end_date) })} · ${t("analytics.sale_count", { count: report.sale_count })}`;
  target.append(note);
}

function renderOverdue(rows) {
  const target = document.getElementById("overdue-table");
  if (!rows.length) {
    renderEmpty(target, 5, t("analytics.empty_overdue"));
    return;
  }
  target.replaceChildren();
  for (const item of rows) {
    const row = document.createElement("tr");
    appendCell(row, item.document_number);
    appendCell(row, item.customer_code);
    appendCell(row, dateLabel(item.due_date));
    appendCell(row, item.days_overdue == null ? "—" : `${item.days_overdue} gün`);
    appendCell(row, money(item.total_cents, item.currency));
    target.append(row);
  }
}

function renderDefects(rows) {
  const target = document.getElementById("defects-table");
  if (!rows.length) {
    renderEmpty(target, 3, t("analytics.empty_defects"));
    return;
  }
  target.replaceChildren();
  for (const product of rows) {
    const row = document.createElement("tr");
    appendCell(row, primaryText(product.name, product.sku));
    appendCell(row, product.brand);
    appendCell(row, product.defective_count);
    target.append(row);
  }
}

function csvCell(value) {
  const text = String(value == null ? "" : value);
  const safe = /^[\s]*[=+\-@]/.test(text) ? `'${text}` : text;
  return `"${safe.replace(/"/g, '""')}"`;
}

function downloadCsv(filename, headers, rows) {
  const content = [headers, ...rows]
    .map((row) => row.map(csvCell).join(";"))
    .join("\r\n");
  const blob = new Blob([new Uint8Array([0xef, 0xbb, 0xbf]), content], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  announce(t("exports.downloaded"));
}

function exportInventory() {
  const query = document.getElementById("product-search").value.trim().toLocaleLowerCase("tr-TR");
  const products = state.products.filter((product) =>
    `${product.name} ${product.sku} ${product.category} ${product.brand}`
      .toLocaleLowerCase("tr-TR").includes(query));
  downloadCsv(`lavox-stok-${localDate()}.csv`, [
    t("labels.product_name"), t("labels.sku"), t("labels.category"),
    t("labels.warehouse"), t("labels.stock"), t("labels.unit_price"),
  ], products.map((product) => [
    product.name, product.sku, product.category, product.warehouse_name,
    product.current_stock, (Number(product.unit_price_cents || 0) / 100).toFixed(2),
  ]));
}

function exportParties() {
  const query = document.getElementById("party-search").value.trim().toLocaleLowerCase("tr-TR");
  const parties = state.parties.filter((party) =>
    `${party.code} ${party.name} ${party.city || ""}`.toLocaleLowerCase("tr-TR").includes(query));
  downloadCsv(`lavox-cariler-${localDate()}.csv`, [
    t("labels.code"), t("labels.customer"), t("labels.type"), t("labels.city"),
    t("labels.balance"), t("labels.credit_limit"),
  ], parties.map((party) => [
    party.code, party.name, t(`parties.${party.type}`), party.city,
    (Number(party.balance_cents || 0) / 100).toFixed(2),
    (Number(party.credit_limit_cents || 0) / 100).toFixed(2),
  ]));
}

function exportFinance() {
  downloadCsv(`lavox-finans-${localDate()}.csv`, [
    t("labels.date"), t("labels.account"), t("labels.type"),
    t("labels.amount"), t("labels.currency"),
  ], state.transactions.map((transaction) => [
    transaction.created_at, transaction.account_name,
    statusLabel(transaction.type, "finance"),
    (Number(transaction.amount_cents || 0) / 100).toFixed(2),
    transaction.currency,
  ]));
}

function exportService() {
  const query = document.getElementById("service-search").value.trim().toLocaleLowerCase("tr-TR");
  const tickets = state.tickets.filter((ticket) =>
    `${ticket.ticket_number} ${ticket.customer_name} ${ticket.device_brand} ${ticket.device_model} ${ticket.serial_number || ""}`
      .toLocaleLowerCase("tr-TR").includes(query));
  downloadCsv(`lavox-teknik-servis-${localDate()}.csv`, [
    t("labels.ticket"), t("labels.customer"), t("labels.device"),
    t("labels.serial"), t("labels.priority"), t("labels.status"),
    t("labels.date"), t("labels.total"),
  ], tickets.map((ticket) => [
    ticket.ticket_number, ticket.customer_name,
    `${ticket.device_brand} ${ticket.device_model}`, ticket.serial_number,
    statusLabel(ticket.priority, "priority"), statusLabel(ticket.status),
    ticket.intake_date, (Number(ticket.final_cost_cents || 0) / 100).toFixed(2),
  ]));
}

function buildPrintDocument(title, fields) {
  const fragment = document.createDocumentFragment();
  const brand = document.createElement("p");
  brand.className = "print-brand";
  brand.textContent = t("print.brand");
  const heading = document.createElement("h1");
  heading.className = "print-title";
  heading.textContent = title;
  const list = document.createElement("dl");
  list.className = "print-fields";
  for (const [label, value] of fields) {
    const term = document.createElement("dt");
    term.textContent = label;
    const description = document.createElement("dd");
    description.textContent = value == null || value === "" ? "—" : String(value);
    list.append(term, description);
  }
  const signatures = document.createElement("div");
  signatures.className = "print-signatures";
  for (const label of [t("print.signature_customer"), t("print.signature_staff")]) {
    const signature = document.createElement("div");
    signature.textContent = label;
    signatures.append(signature);
  }
  fragment.append(brand, heading, list, signatures);
  return fragment;
}

function showPrintDocument(title, content) {
  document.getElementById("record-heading").textContent = title;
  document.getElementById("record-content").replaceChildren(content);
  document.getElementById("record-layer").hidden = false;
  document.getElementById("record-close").focus();
}

function openPrintReceipt(result) {
  const ticket = result.ticket;
  const title = ticket.status === "delivered"
    ? t("service.delivery_receipt")
    : t("service.intake_receipt");
  const customerLabel = t("print.customer");
  const deviceLabel = t("print.device");
  const fields = [
    [t("labels.ticket"), ticket.ticket_number],
    [customerLabel, ticket.customer_name],
    [deviceLabel, `${ticket.device_brand} ${ticket.device_model}`],
    [t("labels.serial"), ticket.serial_number],
    [t("print.intake_date"), dateLabel(ticket.intake_date)],
    [t("print.status"), statusLabel(ticket.status)],
    [t("print.issue"), ticket.problem_description],
    [t("print.warranty"), ticket.warranty_claim ? t("print.warranty_yes") : t("print.warranty_no")],
    [t("print.total"), money(ticket.final_cost_cents)],
  ];
  const fragment = buildPrintDocument(title, fields);
  if (result.parts.length) {
    const partsHeading = document.createElement("h2");
    partsHeading.className = "print-section-title";
    partsHeading.textContent = t("print.parts");
    const partsList = document.createElement("ul");
    for (const part of result.parts) {
      const item = document.createElement("li");
      item.textContent = `${part.serial_number || t("labels.product")} · ${part.quantity_used} × ${money(part.unit_price_cents)}`;
      partsList.append(item);
    }
    fragment.append(partsHeading, partsList);
  }
  showPrintDocument(title, fragment);
}

function openDocumentPrint(documentRow) {
  const party = state.parties.find((item) => item.code === documentRow.customer_code);
  const title = t(`documents.${documentRow.type}`);
  const content = buildPrintDocument(title, [
    [t("print.document_no"), documentRow.document_number],
    [t("print.document_type"), title],
    [t("print.customer"), party ? `${party.name} · ${party.code}` : documentRow.customer_code],
    [t("print.document_date"), dateLabel(documentRow.issue_date)],
    [t("print.document_due"), dateLabel(documentRow.due_date)],
    [t("print.status"), statusLabel(documentRow.status)],
    [t("print.subtotal"), money(documentRow.subtotal_cents, documentRow.currency)],
    [t("print.tax"), money(documentRow.tax_cents, documentRow.currency)],
    [t("labels.discount"), money(documentRow.discount_cents, documentRow.currency)],
    [t("print.total"), money(documentRow.total_cents, documentRow.currency)],
  ]);
  showPrintDocument(title, content);
}

function openServiceMessage(ticket) {
  const feeCents = Number(ticket.final_cost_cents || ticket.estimated_cost_cents || 0);
  const templateKey = ticket.status === "waiting_parts"
    ? "whatsapp.waiting_parts"
    : ["completed", "delivered"].includes(ticket.status)
      ? "whatsapp.ready"
      : "whatsapp.default";
  const message = t(templateKey, {
    name: ticket.customer_name,
    ticket: ticket.ticket_number,
    device: `${ticket.device_brand} ${ticket.device_model}`,
    status: statusLabel(ticket.status),
    fee: money(feeCents),
  });
  document.getElementById("service-message").value = message;
  document.getElementById("message-layer").hidden = false;
  document.getElementById("message-copy").focus();
}

function normalizeSearch(value) {
  return String(value || "").trim().toLocaleLowerCase("tr-TR");
}

function showCommandResults(items, message = "") {
  const target = document.getElementById("command-results");
  target.replaceChildren();
  state.commandResults = message ? [] : items;
  if (message) {
    const empty = document.createElement("p");
    empty.className = "command-empty";
    empty.textContent = message;
    target.append(empty);
    return;
  }
  for (const [index, item] of items.entries()) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "command-result";
    button.dataset.index = String(index);
    const icon = document.createElement("span");
    icon.className = "command-result-icon";
    icon.textContent = item.kind === "action" ? "↗" : "⌕";
    const copy = document.createElement("span");
    copy.className = "command-result-copy";
    const title = document.createElement("strong");
    title.textContent = item.title;
    const detail = document.createElement("small");
    detail.textContent = item.detail;
    copy.append(title, detail);
    const category = document.createElement("span");
    category.className = "command-category";
    category.textContent = item.category;
    button.append(icon, copy, category);
    button.addEventListener("click", () => runCommandResult(item));
    target.append(button);
  }
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "command-empty";
    empty.textContent = t("command.no_results");
    target.append(empty);
  }
}

function openCommandPalette(prefill = "") {
  if (!state.user) return;
  const layer = document.getElementById("command-layer");
  layer.hidden = false;
  const input = document.getElementById("command-input");
  input.value = prefill;
  if (prefill) {
    performGlobalSearch(prefill);
  } else {
    showCommandResults([
      { kind: "action", action: "sale", title: t("command.quick_sale"), detail: "F2", category: t("nav.sales") },
      { kind: "action", action: "service", title: t("command.new_ticket"), detail: "F3", category: t("nav.service") },
    ]);
  }
  input.focus();
}

function closeCommandPalette() {
  document.getElementById("command-layer").hidden = true;
  document.getElementById("command-button").focus();
}

async function performGlobalSearch(value) {
  const query = normalizeSearch(value);
  const requestId = ++state.searchRequest;
  if (query.length < 2) {
    showCommandResults([
      { kind: "action", action: "sale", title: t("command.quick_sale"), detail: "F2", category: t("nav.sales") },
      { kind: "action", action: "service", title: t("command.new_ticket"), detail: "F3", category: t("nav.service") },
    ]);
    return;
  }
  showCommandResults([], t("messages.loading"));
  try {
    const [products, serials, parties, tickets] = await Promise.all([
      api("/api/products"),
      api("/api/serials"),
      api("/api/parties"),
      api("/api/service-tickets"),
    ]);
    if (requestId !== state.searchRequest) return;
    const includes = (record, fields) =>
      fields.some((field) => normalizeSearch(record[field]).includes(query));
    const results = [
      ...products.filter((item) => includes(item, ["name", "sku", "brand", "category"]))
        .slice(0, 3).map((item) => ({
          kind: "product", module: "inventory", search: item.sku,
          title: item.name, detail: `${item.sku} · ${item.brand || item.category}`,
          category: t("nav.inventory"),
        })),
      ...serials.filter((item) => includes(item, ["serial_number", "imei"]))
        .slice(0, 3).map((item) => ({
          kind: "serial", module: "serials", search: item.serial_number,
          title: item.serial_number, detail: item.status ? statusLabel(item.status) : "",
          category: t("nav.serials"),
        })),
      ...parties.filter((item) => includes(item, ["code", "name", "city"]))
        .slice(0, 3).map((item) => ({
          kind: "party", module: "parties", search: item.code,
          title: item.name, detail: `${item.code} · ${t(`parties.${item.type}`)}`,
          category: t("nav.parties"),
        })),
      ...tickets.filter((item) => includes(item, [
        "ticket_number", "customer_name", "device_brand", "device_model", "serial_number",
      ])).slice(0, 3).map((item) => ({
        kind: "service", module: "service", search: item.ticket_number,
        title: item.ticket_number, detail: `${item.customer_name} · ${item.device_brand} ${item.device_model}`,
        category: t("nav.service"),
      })),
    ];
    showCommandResults(results);
  } catch (error) {
    if (requestId === state.searchRequest) {
      showCommandResults([], t("command.search_error"));
      announce(error.message, true);
    }
  }
}

function runCommandResult(item) {
  document.getElementById("command-layer").hidden = true;
  if (item.kind === "action") {
    runQuickAction(item.action);
    return;
  }
  const filters = {
    product: ["product-search", "inventory-warehouse", "inventory"],
    serial: ["serial-search", "serial-status", "serials"],
    party: ["party-search", "party-type", "parties"],
    service: ["service-search", "service-status", "service"],
  };
  const [inputId, filterId, module] = filters[item.kind];
  document.getElementById(inputId).value = item.search;
  document.getElementById(filterId).value = "";
  setActiveModule(module);
}

function runQuickAction(action) {
  if (!state.user) return;
  const module = action === "sale" ? "sales" : "service";
  setActiveModule(module);
  const formId = action === "sale" ? "sale-form" : "service-form";
  const firstField = document.querySelector(`#${formId} input:not([type="checkbox"]), #${formId} select`);
  if (firstField) {
    firstField.focus({ preventScroll: true });
    firstField.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function alertAgeDays(value) {
  if (!value) return 0;
  const day = String(value).slice(0, 10);
  const start = new Date(`${day}T00:00:00`);
  if (Number.isNaN(start.getTime())) return 0;
  const today = new Date(`${localDate()}T00:00:00`);
  return Math.max(0, Math.floor((today.getTime() - start.getTime()) / 86400000));
}

async function refreshNotifications() {
  const [lowStock, overdue, waiting] = await Promise.all([
    api("/api/alerts/critical-stock"),
    api("/api/analytics/overdue-payments"),
    api("/api/service-tickets?status=waiting_parts"),
  ]);
  const alerts = [
    ...lowStock.map((item) => ({
      kind: "inventory",
      title: t("alerts.low_stock"),
      detail: t("alerts.low_stock_detail", {
        name: item.name || item.sku, quantity: item.current_stock,
      }),
      search: item.sku,
    })),
    ...overdue.map((item) => ({
      kind: "documents",
      title: t("alerts.overdue"),
      detail: t("alerts.overdue_detail", {
        document: item.document_number,
        amount: money(item.total_cents, item.currency),
      }),
    })),
    ...waiting.map((item) => ({
      kind: "service",
      title: t("alerts.service_waiting"),
      detail: t("alerts.service_waiting_detail", {
        ticket: item.ticket_number,
        days: alertAgeDays(item.status_updated_at || item.intake_date),
      }),
      search: item.ticket_number,
      waitingDays: alertAgeDays(item.status_updated_at || item.intake_date),
    })).filter((item) => item.waitingDays > 3),
  ];
  renderNotifications(alerts);
}

function renderNotifications(alerts) {
  const count = document.getElementById("notification-count");
  count.textContent = alerts.length > 99 ? "99+" : String(alerts.length);
  count.hidden = alerts.length === 0;
  const target = document.getElementById("notification-list");
  target.replaceChildren();
  if (!alerts.length) {
    const empty = document.createElement("p");
    empty.className = "notification-empty";
    empty.textContent = t("alerts.empty");
    target.append(empty);
  }
  const displayedAlerts = ["service", "documents", "inventory"]
    .flatMap((kind) => alerts.filter((alert) => alert.kind === kind).slice(0, 4));
  for (const alert of displayedAlerts) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "notification-item";
    const title = document.createElement("strong");
    title.textContent = alert.title;
    const detail = document.createElement("small");
    detail.textContent = alert.detail;
    button.append(title, detail);
    button.addEventListener("click", () => {
      if (alert.kind === "inventory") {
        document.getElementById("product-search").value = alert.search || "";
      } else if (alert.kind === "service") {
        document.getElementById("service-search").value = alert.search || "";
        document.getElementById("service-status").value = "waiting_parts";
      }
      document.getElementById("notification-popover").hidden = true;
      document.getElementById("notification-button").setAttribute("aria-expanded", "false");
      setActiveModule(alert.kind);
    });
    target.append(button);
  }
  document.getElementById("notification-updated").textContent =
    `${t("alerts.live")} · ${new Date().toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" })}`;
}

function toggleTheme() {
  const root = document.documentElement;
  const theme = root.dataset.theme === "dark" ? "light" : "dark";
  root.dataset.theme = theme;
  const button = document.getElementById("theme-button");
  button.setAttribute("aria-pressed", String(theme === "dark"));
  button.querySelector("span[aria-hidden]").textContent = theme === "dark" ? "☀" : "☾";
  button.querySelector("span:not([aria-hidden])").textContent =
    t(theme === "dark" ? "theme.dark" : "theme.light");
  localStorage.setItem("lavox_theme", theme);
}

function initializeTheme() {
  let theme = "light";
  try {
    if (localStorage.getItem("lavox_theme") === "dark") theme = "dark";
  } catch {
    announce(t("messages.theme_error"), true);
  }
  document.documentElement.dataset.theme = theme;
  const button = document.getElementById("theme-button");
  button.setAttribute("aria-pressed", String(theme === "dark"));
  button.querySelector("span[aria-hidden]").textContent = theme === "dark" ? "☀" : "☾";
  button.querySelector("span:not([aria-hidden])").textContent =
    t(theme === "dark" ? "theme.dark" : "theme.light");
}

function startNotificationPolling() {
  if (state.alertTimer) return;
  state.alertTimer = window.setInterval(() => {
    refreshNotifications().catch((error) => announce(error.message, true));
  }, 300000);
}

function attachHandlers() {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => setActiveModule(button.dataset.module));
  });
  document.querySelectorAll("[data-go]").forEach((button) => {
    button.addEventListener("click", () => setActiveModule(button.dataset.go));
  });
  document.getElementById("refresh-button").addEventListener("click", () => {
    loadModule(state.activeModule).catch((error) => announce(error.message, true));
  });
  document.getElementById("command-button").addEventListener("click", () => openCommandPalette());
  document.getElementById("command-close").addEventListener("click", closeCommandPalette);
  document.getElementById("command-input").addEventListener("input", (event) => {
    window.clearTimeout(state.searchTimer);
    const value = event.currentTarget.value;
    state.searchTimer = window.setTimeout(() => performGlobalSearch(value), 180);
  });
  document.getElementById("command-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && state.commandResults.length) {
      event.preventDefault();
      runCommandResult(state.commandResults[0]);
    }
  });
  document.getElementById("command-layer").addEventListener("click", (event) => {
    if (event.target === event.currentTarget) closeCommandPalette();
  });
  document.getElementById("notification-button").addEventListener("click", async () => {
    const popover = document.getElementById("notification-popover");
    const open = popover.hidden;
    popover.hidden = !open;
    document.getElementById("notification-button").setAttribute("aria-expanded", String(open));
    if (open) {
      try { await refreshNotifications(); }
      catch (error) { announce(error.message, true); }
    }
  });
  document.getElementById("notification-refresh").addEventListener("click", () => {
    refreshNotifications().catch((error) => announce(error.message, true));
  });
  document.addEventListener("pointerdown", (event) => {
    const popover = document.getElementById("notification-popover");
    const trigger = document.getElementById("notification-button");
    if (!popover.hidden && !popover.contains(event.target) && !trigger.contains(event.target)) {
      popover.hidden = true;
      trigger.setAttribute("aria-expanded", "false");
    }
  });
  document.getElementById("theme-button").addEventListener("click", () => {
    try { toggleTheme(); }
    catch { announce(t("messages.theme_error"), true); }
  });
  document.getElementById("backup-button").addEventListener("click", async () => {
    try {
      const response = await fetch("/api/backup/database", {
        headers: { "x-current-user": JSON.stringify(state.user) },
      });
      if (!response.ok) {
        if (response.status === 403) throw new Error(t("messages.api_error"));
        throw new Error(t("backup.failed"));
      }
      const blob = await response.blob();
      const disposition = response.headers.get("content-disposition") || "";
      const match = disposition.match(/filename="?([^";]+)"?/i);
      const filename = match ? match[1] : `lavox_enterprise_${localDate()}.db`;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.hidden = true;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      announce(t("backup.download_started"));
    } catch (error) {
      announce(error.message || t("backup.failed"), true);
    }
  });
  const closeRecord = () => { document.getElementById("record-layer").hidden = true; };
  document.getElementById("record-close").addEventListener("click", closeRecord);
  document.getElementById("record-close-icon").addEventListener("click", closeRecord);
  document.getElementById("record-layer").addEventListener("click", (event) => {
    if (event.target === event.currentTarget) closeRecord();
  });
  document.getElementById("record-print").addEventListener("click", () => window.print());
  const closeMessage = () => { document.getElementById("message-layer").hidden = true; };
  document.getElementById("message-close").addEventListener("click", closeMessage);
  document.getElementById("message-close-icon").addEventListener("click", closeMessage);
  document.getElementById("message-layer").addEventListener("click", (event) => {
    if (event.target === event.currentTarget) closeMessage();
  });
  document.getElementById("message-copy").addEventListener("click", async () => {
    const message = document.getElementById("service-message");
    try {
      await navigator.clipboard.writeText(message.value);
      announce(t("whatsapp.copied"));
    } catch {
      message.focus();
      message.select();
      announce(t("whatsapp.copy_failed"), true);
    }
  });
  document.getElementById("message-whatsapp").addEventListener("click", () => {
    const opened = window.open("https://web.whatsapp.com/", "_blank");
    if (opened) {
      opened.opener = null;
      announce(t("whatsapp.opened"));
    } else announce(t("whatsapp.popup_blocked"), true);
  });
  document.getElementById("export-inventory").addEventListener("click", exportInventory);
  document.getElementById("export-parties").addEventListener("click", exportParties);
  document.getElementById("export-finance").addEventListener("click", exportFinance);
  document.getElementById("export-service").addEventListener("click", exportService);
  document.getElementById("logout-button").addEventListener("click", () => {
    setUser(null);
    announce(t("auth.signed_out"));
  });
  document.getElementById("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const errorTarget = document.getElementById("login-error");
    errorTarget.hidden = true;
    const formData = new FormData(form);
    const credentials = {
      username: String(formData.get("username") || "").trim(),
      password: String(formData.get("password") || ""),
    };
    const branch = String(formData.get("branch") || "central");
    const fiscalYear = String(formData.get("fiscal_year") || "2026");
    try {
      const result = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify(credentials),
      });
      updateWorkspaceContext(branch, fiscalYear);
      sessionStorage.setItem("lavox_workspace", JSON.stringify(state.workspace));
      setUser(result.user);
      form.reset();
      form.elements.namedItem("branch").value = state.workspace.branch;
      form.elements.namedItem("fiscal_year").value = state.workspace.fiscalYear;
      announce(t("auth.signed_in"));
      await loadLookups();
      refreshNotifications().catch((error) => announce(error.message, true));
      startNotificationPolling();
      setActiveModule("dashboard");
    } catch (error) {
      errorTarget.textContent = error.message || t("auth.invalid");
      errorTarget.hidden = false;
    }
  });
  document.getElementById("inventory-warehouse").addEventListener("change", () => {
    loadInventory().catch((error) => announce(error.message, true));
  });
  document.getElementById("product-search").addEventListener("input", () => {
    loadInventory().catch((error) => announce(error.message, true));
  });
  document.getElementById("serial-status").addEventListener("change", () => {
    loadSerials().catch((error) => announce(error.message, true));
  });
  document.getElementById("serial-search").addEventListener("input", () => {
    loadSerials().catch((error) => announce(error.message, true));
  });
  document.getElementById("serial-refresh").addEventListener("click", () => {
    loadSerials().catch((error) => announce(error.message, true));
  });
  document.getElementById("service-status").addEventListener("change", () => {
    loadService().catch((error) => announce(error.message, true));
  });
  document.getElementById("service-search").addEventListener("input", () => {
    loadService().catch((error) => announce(error.message, true));
  });
  document.getElementById("party-type").addEventListener("change", () => {
    loadParties().catch((error) => announce(error.message, true));
  });
  document.getElementById("party-search").addEventListener("input", () => {
    loadParties().catch((error) => announce(error.message, true));
  });
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openCommandPalette();
      return;
    }
    const modalOpen = ["command-layer", "record-layer", "message-layer"]
      .some((id) => !document.getElementById(id).hidden);
    if (!modalOpen && !event.ctrlKey && !event.metaKey && !event.altKey) {
      if (event.key === "F2") {
        event.preventDefault();
        runQuickAction("sale");
      } else if (event.key === "F3") {
        event.preventDefault();
        runQuickAction("service");
      }
    }
    if (event.key === "Escape") {
      if (!document.getElementById("command-layer").hidden) closeCommandPalette();
      if (!document.getElementById("record-layer").hidden) document.getElementById("record-layer").hidden = true;
      if (!document.getElementById("message-layer").hidden) document.getElementById("message-layer").hidden = true;
      document.getElementById("notification-popover").hidden = true;
      document.getElementById("notification-button").setAttribute("aria-expanded", "false");
    }
  });

  document.getElementById("product-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    values.is_tracked_serial = form.elements.is_tracked_serial.checked;
    try {
      await api("/api/products", { method: "POST", body: JSON.stringify(values) });
      form.reset();
      form.elements.critical_stock_level.value = "5";
      announce(t("inventory.created"));
      await loadLookups();
      await loadInventory();
    } catch (error) { announce(error.message, true); }
  });

  document.getElementById("warranty-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const serial = new FormData(event.currentTarget).get("serial_number").trim();
    const target = document.getElementById("warranty-result");
    try {
      const data = await api(`/api/serials/${encodeURIComponent(serial)}/warranty`);
      target.hidden = false;
      target.className = `result-box ${data.in_warranty ? "success" : ""}`;
      const label = data.in_warranty ? t("serials.covered") : t("serials.not_covered");
      const remaining = data.days_remaining == null ? t("serials.no_warranty_date") : t("serials.days_left", { count: data.days_remaining });
      target.textContent = `${data.product_name} · ${label} · ${remaining}`;
      await loadSerials();
    } catch (error) { announce(error.message, true); }
  });

  document.getElementById("transfer-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    data.from_warehouse_id = Number(data.from_warehouse_id);
    data.to_warehouse_id = Number(data.to_warehouse_id);
    try {
      await api("/api/serials/transfer", { method: "POST", body: JSON.stringify(data) });
      event.currentTarget.reset();
      populateLookupSelects();
      announce(t("serials.transferred"));
      await Promise.all([loadSerials(), loadInventory()]);
    } catch (error) { announce(error.message, true); }
  });

  document.getElementById("service-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    data.warranty_claim = form.elements.warranty_claim.checked;
    try {
      await api("/api/service-tickets", { method: "POST", body: JSON.stringify(data) });
      form.reset();
      announce(t("service.created"));
      await loadService();
    } catch (error) { announce(error.message, true); }
  });

  document.getElementById("add-sale-line").addEventListener("click", () => addLine(document.getElementById("sale-lines"), "sale"));
  document.getElementById("sale-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      const data = Object.fromEntries(new FormData(form));
      data.warehouse_id = Number(data.warehouse_id);
      data.items = lineItems(document.getElementById("sale-lines"), true);
      await api("/api/pos-sales", { method: "POST", body: JSON.stringify(data) });
      form.reset();
      document.getElementById("sale-lines").replaceChildren();
      addLine(document.getElementById("sale-lines"), "sale");
      populateLookupSelects();
      announce(t("sales.created"));
      await Promise.all([loadSales(), loadLookups(), loadDashboard()]);
    } catch (error) { announce(error.message, true); }
  });

  document.getElementById("add-purchase-line").addEventListener("click", () => addLine(document.getElementById("purchase-lines"), "purchase"));
  document.getElementById("purchase-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      const data = Object.fromEntries(new FormData(form));
      data.warehouse_id = Number(data.warehouse_id);
      data.items = lineItems(document.getElementById("purchase-lines"));
      await api("/api/purchase-orders", { method: "POST", body: JSON.stringify(data) });
      form.reset();
      document.getElementById("purchase-lines").replaceChildren();
      addLine(document.getElementById("purchase-lines"), "purchase");
      populateLookupSelects();
      announce(t("purchasing.created"));
      await loadPurchasing();
    } catch (error) { announce(error.message, true); }
  });

  document.getElementById("party-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    try {
      await api("/api/parties", { method: "POST", body: JSON.stringify(data) });
      form.reset();
      announce(t("parties.created"));
      await loadLookups();
      await loadParties();
    } catch (error) { announce(error.message, true); }
  });

  document.getElementById("transaction-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    data.account_id = Number(data.account_id);
    try {
      await api("/api/transactions", { method: "POST", body: JSON.stringify(data) });
      form.reset();
      announce(t("finance.created"));
      await loadFinance();
      await loadDashboard();
    } catch (error) { announce(error.message, true); }
  });

  document.getElementById("add-document-line").addEventListener("click", () => addLine(document.getElementById("document-lines"), "document"));
  document.getElementById("document-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      const data = Object.fromEntries(new FormData(form));
      data.items = lineItems(document.getElementById("document-lines"), true)
        .map(({ product_id, ...item }) => item);
      await api("/api/documents", { method: "POST", body: JSON.stringify(data) });
      form.reset();
      document.getElementById("document-lines").replaceChildren();
      addLine(document.getElementById("document-lines"), "document");
      document.querySelector('#document-form [name="issue_date"]').value = localDate();
      announce(t("documents.created"));
      await loadDocuments();
    } catch (error) { announce(error.message, true); }
  });

  document.getElementById("report-form").addEventListener("submit", (event) => {
    event.preventDefault();
    runReport().catch((error) => announce(error.message, true));
  });
}

async function initialize() {
  let translationsLoaded = false;
  try {
    await loadTranslations();
    translationsLoaded = true;
    restoreWorkspaceContext();
    initializeTheme();
    setFilterOptions();
    attachHandlers();
    addLine(document.getElementById("sale-lines"), "sale");
    addLine(document.getElementById("purchase-lines"), "purchase");
    addLine(document.getElementById("document-lines"), "document");
    let storedUser = null;
    try {
      const serialized = sessionStorage.getItem("lavox_user");
      if (serialized) storedUser = JSON.parse(serialized);
    } catch {
      sessionStorage.removeItem("lavox_user");
    }
    setUser(storedUser);
    if (state.user) {
      await loadLookups();
      refreshNotifications().catch((error) => announce(error.message, true));
      startNotificationPolling();
      setActiveModule("dashboard");
    }
  } catch (error) {
    announce(error.message || t("messages.connection_error"), true);
    showLogin(true);
  } finally {
    if (translationsLoaded) {
      notifyDesktopReady();
    }
  }
}

initialize();

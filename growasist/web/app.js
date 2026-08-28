const app = document.querySelector("[data-app]");
const authGate = document.querySelector("[data-auth-gate]");
const authForm = document.querySelector("[data-auth-form]");
const authMessage = document.querySelector("[data-auth-message]");
const viewContent = document.querySelector("[data-view-content]");
const viewTitle = document.querySelector("[data-view-title]");
const viewKicker = document.querySelector("[data-view-kicker]");
const dialog = document.querySelector("[data-dialog]");
const dialogForm = document.querySelector("[data-dialog-form]");
const dialogKicker = document.querySelector("[data-dialog-kicker]");
const dialogTitle = document.querySelector("[data-dialog-title]");
const dialogBody = document.querySelector("[data-dialog-body]");
const dialogActions = document.querySelector("[data-dialog-actions]");
const toast = document.querySelector("[data-toast]");

const TOKEN_KEY = "growasist_api_token";
const eventLabels = {
  cultivation_started: "Yetiştirme başladı",
  cultivation_finished: "Yetiştirme tamamlandı",
  stage_transition: "Aşama değişti",
  user_note: "Not",
  water_added: "Su eklendi",
  water_changed: "Su değiştirildi",
  nutrient_dose: "Besin verildi",
  ph_dose: "pH düzenlendi",
  reservoir_volume: "Rezervuar ölçüldü",
  calibration: "Kalibrasyon",
  maintenance: "Bakım",
  photo: "Fotoğraf",
  alarm: "Alarm",
  ai_recommendation: "Grow Assistant önerisi",
};
const eventSymbols = {
  cultivation_started: "↗", cultivation_finished: "■", stage_transition: "→",
  user_note: "N", water_added: "+", water_changed: "↻", nutrient_dose: "mL",
  ph_dose: "pH", reservoir_volume: "L", calibration: "C", maintenance: "M",
  photo: "□", alarm: "!", ai_recommendation: "✦",
};
const stageOrder = ["germination", "early_veg", "veg", "bloom", "darkness", "harvest"];
const cultivationMethods = [["RDWC","RDWC"],["DWC","DWC"],["NFT","NFT"],["Ebb and Flow","Ebb & Flow"],["Drip","Damla sulama"],["Aeroponics","Aeroponik"],["Kratky","Kratky"],["Coco","Coco"],["Soil","Toprak"]];
const growingMedia = [["","Seçin"],["Expanded clay","Kil bilyesi"],["Rockwool","Taş yünü"],["Coco coir","Coco coir"],["Perlite","Perlit"],["Soil","Toprak"],["Water only","Yalnız su"],["Mixed","Karışım"]];
const viewMeta = {
  today: ["Yetiştirme", "Genel Bakış"],
  journal: ["Yetiştirme", "Günlük"],
  dosing: ["Yetiştirme", "Dozaj"],
  setup: ["Sistem", "Alan ve ışık"],
};
const setupViewIds = new Set(["overview", "plants", "nutrients", "hardware", "iot"]);

let token = sessionStorage.getItem(TOKEN_KEY) || "";
let state = null;
let currentView = "today";
let currentSetupView = "overview";
let selectedPlantId = "";
let nutrientCatalogBrand = "all";
let nutrientLibraryView = "programs";
let nutrientProgramBrand = "all";
let nutrientProgramEnvironment = "all";
let toastTimer = null;

function html(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[character]);
}

function id() {
  if (crypto.randomUUID) return crypto.randomUUID().replaceAll("-", "");
  return `${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function localDate() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

function dayNumber(start) {
  if (!start) return 0;
  const first = new Date(`${start}T00:00:00`);
  const today = new Date(`${localDate()}T00:00:00`);
  return Math.max(1, Math.floor((today - first) / 86400000) + 1);
}

function showToast(message, error = false) {
  clearTimeout(toastTimer);
  toast.textContent = message;
  toast.className = `toast show${error ? " error" : ""}`;
  toastTimer = setTimeout(() => { toast.className = "toast"; }, 3200);
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { ...options, headers });
  let payload = {};
  try { payload = await response.json(); } catch (_) { /* Empty response. */ }
  if (response.status === 401) {
    sessionStorage.removeItem(TOKEN_KEY);
    token = "";
    showAuth("Erişim anahtarı kabul edilmedi.");
    throw new Error("Yetkisiz erişim");
  }
  if (!response.ok) throw new Error(payload.message || payload.error || `HTTP ${response.status}`);
  return payload;
}

function showAuth(message = "") {
  authGate.hidden = false;
  app.hidden = true;
  authMessage.textContent = message;
  setTimeout(() => authForm.elements.token.focus(), 30);
}

async function loadState() {
  state = await api("/api/v1/bootstrap");
  authGate.hidden = true;
  app.hidden = false;
  applyRoute();
  render();
}

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = authForm.querySelector("button");
  token = authForm.elements.token.value.trim();
  if (!token) return;
  button.disabled = true;
  authMessage.textContent = "Bağlanıyor…";
  try {
    await loadState();
    sessionStorage.setItem(TOKEN_KEY, token);
    authForm.reset();
  } catch (error) {
    token = "";
    authMessage.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

document.querySelector("[data-lock]").addEventListener("click", () => {
  sessionStorage.removeItem(TOKEN_KEY);
  token = "";
  state = null;
  showAuth("Oturum kilitlendi.");
});

function applyRoute() {
  const [view, setupView] = window.location.hash.replace(/^#/, "").split("/");
  currentView = ["journal", "dosing", "setup"].includes(view) ? view : "today";
  if (currentView === "setup") {
    currentSetupView = setupView === "profiles" ? "plants" : (setupViewIds.has(setupView) ? setupView : "overview");
  }
}

function syncNavigation() {
  document.querySelectorAll("[data-view]").forEach((item) => item.classList.toggle("active", item.dataset.view === currentView));
  document.querySelectorAll("[data-setup-shortcut]").forEach((item) => item.classList.toggle("active", currentView === "setup" && item.dataset.setupShortcut === currentSetupView));
  if (!state) return;
  document.querySelector('[data-rail-count="plants"]').textContent = `${plantOptions().length} tür`;
  document.querySelector('[data-rail-count="nutrients"]').textContent = `${state.hardware?.dosing_fluids?.length || 0} ürün`;
  document.querySelector('[data-rail-count="hardware"]').textContent = `${state.hardware?.device_assignments?.length || 0} cihaz`;
  const iotCount = Object.values(state.device_registry?.devices || {}).length;
  document.querySelector('[data-rail-count="iot"]').textContent = `${iotCount} tanımlı`;
}

function navigateTo(view, setupView = null) {
  const nextHash = view === "setup" ? `#setup/${setupView || currentSetupView}` : `#${view}`;
  if (window.location.hash === nextHash) {
    applyRoute();
    window.scrollTo(0, 0);
    render();
  } else {
    window.location.hash = nextHash;
  }
}

document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => navigateTo(button.dataset.view)));
document.querySelectorAll("[data-setup-shortcut]").forEach((button) => button.addEventListener("click", () => navigateTo("setup", button.dataset.setupShortcut)));
window.addEventListener("hashchange", () => {
  applyRoute();
  window.scrollTo(0, 0);
  render();
});

function render() {
  if (!state) return;
  syncNavigation();
  const [kicker, title] = viewMeta[currentView];
  viewKicker.textContent = kicker;
  viewTitle.textContent = title;
  document.title = `${title} · GrowAsist`;
  if (currentView === "journal") renderJournal();
  else if (currentView === "dosing") renderDosing(viewContent);
  else if (currentView === "setup") renderSetup();
  else renderToday();
}

function eventRow(event) {
  const amount = event.data?.amount != null ? ` · ${html(event.data.amount)} ${html(event.data.unit || "")}` : "";
  const note = event.type === "stage_transition"
    ? (state.stage_labels[event.data?.stage || event.note] || event.note)
    : (event.note || event.data?.url || "Açıklama yok");
  return `<article class="event-row">
    <span class="event-symbol">${html(eventSymbols[event.type] || "·")}</span>
    <span><b>${html(eventLabels[event.type] || event.type)}${amount}</b><small>${html(note)}</small></span>
    <time datetime="${html(event.local_date)}">${html(event.local_date)}</time>
  </article>`;
}

function recentEvents(limit = 5) {
  const activeId = state.active_cultivation?.id;
  return state.events.filter((event) => !activeId || event.cultivation_id === activeId).slice(-limit).reverse();
}

function renderToday() {
  const grow = state.active_cultivation;
  if (!grow) {
    viewContent.innerHTML = `<section class="empty-grow">
      <div class="empty-copy">
        <h2>Yeni yetiştirme başlat</h2>
        <p>Bitkini seç, başlangıç tarihini belirle. Aşama, besin, su ve bakım kayıtlarını tek günlükten takip et.</p>
        <button class="primary-button" data-start-grow>Yetiştirmeyi başlat</button>
      </div>
    </section>`;
    viewContent.querySelector("[data-start-grow]").addEventListener("click", openStartDialog);
    return;
  }

  const identity = grow.identity || {};
  const totalDay = dayNumber(grow.start_date);
  const transitions = grow.transitions || [];
  const currentTransition = transitions.at(-1) || {};
  const stageDay = dayNumber(currentTransition.date || grow.start_date);
  const plan = grow.plan || [];
  const activeIndex = Math.max(0, plan.findIndex((item) => item.stage === state.active_stage));
  const stages = plan.map((item, index) => `<button class="stage-node ${index < activeIndex ? "done" : ""} ${index === activeIndex ? "active" : ""}" data-stage="${html(item.stage)}">
    <i></i><b>${html(state.stage_labels[item.stage] || item.stage)}</b><small>${html(item.planned_days)} gün</small>
  </button>`).join("");
  const events = recentEvents();
  const snapshot = grow.system_snapshot || state.system_profile || {};
  const lighting = snapshot.lighting || {};
  const stageTarget = grow.plant_profile_snapshot?.profile?.stages?.[state.active_stage] || {};
  const context = [
    ["Yöntem", identity.growing_method || "—"],
    ["Medya", identity.growing_medium || "—"],
    ["Işık hedefi", stageTarget.photoperiod != null ? `${stageTarget.photoperiod} saat · %${stageTarget.light_intensity}` : "—"],
    ["Armatür", lighting.model || lighting.brand || "Henüz tanımlanmadı"],
    ["Besin programı", identity.nutrient_program || "Henüz seçilmedi"],
  ];

  viewContent.innerHTML = `<section class="grow-head">
    <div><span class="grow-meta">${html(state.stage_labels[state.active_stage] || "Aktif yetiştirme")} · aşama günü ${stageDay}</span>
      <h2>${html(identity.cultivar || identity.plant_species || grow.name)}</h2>
      <p>${html(grow.name)} · ${html(identity.plant_count || 1)} bitki · ${html(identity.breeder_name || identity.botanical_name || "Kaynak belirtilmedi")}</p>
    </div>
    <div class="day-dial"><span><b>${totalDay}</b><small>yetiştirme günü</small></span></div>
  </section>
  <section class="stage-waterline stage-count-${Math.max(1, Math.min(6, plan.length))}">${stages}</section>
  <section class="quick-strip"><span>Bugüne ekle</span>
    <button class="quick-action" data-quick="user_note">Not</button>
    <button class="quick-action" data-quick="water_added">Su ekledim</button>
    <button class="quick-action" data-quick="nutrient_dose">Besin verdim</button>
    <button class="quick-action" data-quick="maintenance">Bakım yaptım</button>
  </section>
  <div class="dashboard-grid">
    <section><header class="section-head"><h3>Son kayıtlar</h3><button class="text-button" data-open-journal>Tümünü aç</button></header>
      <div class="event-list">${events.length ? events.map(eventRow).join("") : '<p class="empty-list">İlk günlük kaydınızı ekleyin.</p>'}</div>
    </section>
    <section><header class="section-head"><h3>Yetiştirme özeti</h3></header>
      <div class="assistant-wait"><div class="orb">◎</div><div>${context.map(([label, value]) => `<p><small>${html(label)}</small><br>${html(value)}</p>`).join("")}</div></div>
    </section>
  </div>
  <div class="setup-save"><button class="danger-button" data-finish-grow>Yetiştirmeyi tamamla</button></div>`;

  viewContent.querySelectorAll("[data-quick]").forEach((button) => button.addEventListener("click", () => openJournalDialog(button.dataset.quick)));
  viewContent.querySelector("[data-open-journal]").addEventListener("click", () => navigateTo("journal"));
  viewContent.querySelectorAll("[data-stage]").forEach((button) => button.addEventListener("click", () => changeStage(button.dataset.stage)));
  viewContent.querySelector("[data-finish-grow]").addEventListener("click", finishGrow);
}

function renderJournal() {
  const groups = {};
  [...state.events].reverse().forEach((event) => {
    (groups[event.local_date] ||= []).push(event);
  });
  const days = Object.entries(groups).sort(([a], [b]) => b.localeCompare(a));
  viewContent.innerHTML = `<div class="page-actions"><div><strong>${state.events.length} kayıt</strong><p>Yanlış bir kayıt için yeni bir düzeltme notu ekleyebilirsiniz.</p></div>
    <button class="primary-button" data-add-event ${state.active_cultivation ? "" : "disabled"}>Günlüğe ekle</button></div>
    <section class="journal-sheet">${days.length ? days.map(([date, events]) => `<div class="journal-day"><div class="journal-date"><b>${html(date.slice(8,10))}</b>${html(date.slice(0,7))}</div><div class="event-list">${events.map(eventRow).join("")}</div></div>`).join("") : '<p class="empty-list">Henüz günlük kaydı yok.</p>'}</section>`;
  viewContent.querySelector("[data-add-event]")?.addEventListener("click", () => openJournalDialog("user_note"));
}

function field(section, key, label, value, options = {}) {
  const name = `${section}.${key}`;
  if (options.choices) return `<label><span>${html(label)}</span><select name="${name}">${options.choices.map(([id, text]) => `<option value="${html(id)}" ${value === id ? "selected" : ""}>${html(text)}</option>`).join("")}</select></label>`;
  return `<label class="${options.wide ? "wide" : ""}"><span>${html(label)}</span><input name="${name}" type="${options.type || "text"}" value="${html(value)}" ${options.min != null ? `min="${options.min}"` : ""} ${options.step ? `step="${options.step}"` : ""}></label>`;
}

function optionRows(choices, selected) {
  return choices.map(([value, label]) => `<option value="${html(value)}" ${value === selected ? "selected" : ""}>${html(label)}</option>`).join("");
}

function renderSetup() {
  const modules = [
    ["overview", "Alan ve ışık", "Yöntem, medya ve armatür"],
    ["plants", "Bitki kütüphanesi", `${plantOptions().length} tür`],
    ["nutrients", "Besinler", `${state.hardware?.dosing_fluids?.length || 0} ürün`],
    ["hardware", "Yerel donanım", `${state.hardware?.device_assignments?.length || 0} kablolu cihaz`],
    ["iot", "IoT cihazları", `${Object.values(state.device_registry?.devices || {}).length} tanımlı`],
  ];
  const descriptions = {
    overview: ["Sistem", "Yöntemini, yetiştirme medyanı ve ışığını tanımla."],
    plants: ["Kütüphane", "Bitki kimliğini, aşama süresini ve yetiştirme hedeflerini düzenle."],
    nutrients: ["Kütüphane", "Marka programını seç; ürün setini tek işlemle kendi listene al."],
    hardware: ["Sistem", "Raspberry Pi üzerine kabloyla bağlanan kartları yönet."],
    iot: ["Sistem", "Wi-Fi ve yerel ağ cihazlarını bul, doğrula ve rol ver."],
  };
  const [group, description] = descriptions[currentSetupView] || descriptions.overview;
  const title = modules.find(([module]) => module === currentSetupView)?.[1] || "Kurulum";
  viewKicker.textContent = group;
  viewTitle.textContent = title;
  document.title = `${title} · GrowAsist`;
  viewContent.innerHTML = `<section class="setup-context"><p>${html(description)}</p></section>
    <nav class="setup-modules" aria-label="Kurulum bölümleri">${modules.map(([module, label, detail]) => `<button type="button" class="setup-module ${module === currentSetupView ? "active" : ""}" data-setup-view="${module}"><b>${html(label)}</b><small>${html(detail)}</small></button>`).join("")}</nav>
    <div data-setup-panel></div>`;
  viewContent.querySelectorAll("[data-setup-view]").forEach((button) => button.addEventListener("click", () => {
    navigateTo("setup", button.dataset.setupView);
  }));
  const panel = viewContent.querySelector("[data-setup-panel]");
  if (currentSetupView === "plants") renderPlants(panel);
  else if (currentSetupView === "nutrients") renderNutrients(panel);
  else if (currentSetupView === "hardware") renderHardware(panel);
  else if (currentSetupView === "iot") renderIoT(panel);
  else renderSetupOverview(panel);
}

function renderSetupOverview(panel) {
  const profile = state.system_profile || {};
  const area = profile.cabin || {};
  const system = profile.system || {};
  const light = profile.lighting || {};
  const lightDevices = Object.values(state.device_registry?.devices || {}).filter((item) => ["light_dimmer","light_power"].includes(item.role));
  const lightChoices = [["", lightDevices.length ? "Işık kontrolü seçin" : "Henüz ışık kontrolü eklenmedi"], ...lightDevices.map((item) => [item.id, `${item.name || item.model || item.host} · ${item.role === "light_dimmer" ? "Dimmer" : "Aç / kapat"}`])];
  panel.innerHTML = `<form data-setup-form>
    <section class="setup-section"><header><h3>Yetiştirme sistemi</h3><p>Yeni yetiştirmelerde hazır gelecek temel bilgiler.</p></header><div class="field-grid simple-grid">
      ${field("system","growing_method","Yetiştirme yöntemi",system.growing_method,{choices:cultivationMethods})}
      ${field("system","growing_medium","Yetiştirme medyası",system.growing_medium,{choices:growingMedia})}
      ${field("system","system_volume_l","Toplam su hacmi · L",system.system_volume_l,{type:"number",min:0,step:"0.1"})}
      ${field("system","plant_capacity","Bitki kapasitesi",system.plant_capacity,{type:"number",min:1})}
    </div></section>
    <section class="setup-section"><header><h3>Işık</h3><p>Kullandığın armatürün temel bilgileri.</p></header><div class="field-grid simple-grid">
      ${field("lighting","device_id","Bağlı ışık kontrolü",light.device_id,{choices:lightChoices})}${field("lighting","model","Armatür / model",light.model)}
      ${field("lighting","fixture_count","Armatür sayısı",light.fixture_count,{type:"number",min:1})}
      ${field("lighting","power_w_each","Her birinin gücü · W",light.power_w_each,{type:"number",min:0})}
    </div></section>
    <details class="advanced-settings"><summary>Diğer ölçüler</summary><div class="field-grid">
      ${field("cabin","width_cm","Alan genişliği · cm",area.width_cm,{type:"number",min:0,step:"0.1"})}
      ${field("cabin","depth_cm","Alan derinliği · cm",area.depth_cm,{type:"number",min:0,step:"0.1"})}
      ${field("cabin","height_cm","Alan yüksekliği · cm",area.height_cm,{type:"number",min:0,step:"0.1"})}
      ${field("system","reservoir_volume_l","Rezervuar hacmi · L",system.reservoir_volume_l,{type:"number",min:0,step:"0.1"})}
      ${field("lighting","brand","Işık markası",light.brand)}
      ${field("lighting","height_cm","Işığın bitkiye uzaklığı · cm",light.height_cm,{type:"number",min:0,step:"0.1"})}
    </div></details>
    <div class="setup-save"><button class="primary-button" type="submit">Kurulumu kaydet</button></div>
  </form>`;
  panel.querySelector("[data-setup-form]").addEventListener("submit", saveSetup);
}

function stageTargetFields(stage, target) {
  const fieldInput = (key, label, min, max, step) => `<label><span>${label}</span><input name="stage.${stage}.${key}" type="number" min="${min}" max="${max}" step="${step}" value="${html(target?.[key] ?? 0)}"></label>`;
  const basic = [
    fieldInput("planned_days", "Süre · gün", 1, 365, 1),
    fieldInput("photoperiod", "Işık · saat", 0, 24, .5),
    fieldInput("day_temperature", "Sıcaklık · °C", 0, 60, .1),
    fieldInput("humidity", "Nem · %", 0, 100, 1),
  ].join("");
  const advanced = [
    fieldInput("light_intensity", "Işık gücü · %", 0, 100, 1),
    fieldInput("night_temperature", "Gece sıcaklığı · °C", 0, 60, .1),
    fieldInput("vpd", "VPD · kPa", 0, 5, .01),
    fieldInput("co2", "CO₂ · ppm", 0, 5000, 10),
    fieldInput("water_temperature", "Su sıcaklığı · °C", 0, 40, .1),
    fieldInput("do_minimum", "Minimum DO · mg/L", 0, 30, .1),
  ].join("");
  return `${basic}<label><span>pH alt</span><input name="stage.${stage}.ph_min" type="number" min="0" max="14" step=".1" value="${html(target.ph_min)}"></label><label><span>pH üst</span><input name="stage.${stage}.ph_max" type="number" min="0" max="14" step=".1" value="${html(target.ph_max)}"></label><label><span>EC alt</span><input name="stage.${stage}.ec_min" type="number" min="0" max="10" step=".1" value="${html(target.ec_min)}"></label><label><span>EC üst</span><input name="stage.${stage}.ec_max" type="number" min="0" max="10" step=".1" value="${html(target.ec_max)}"></label><details class="advanced-settings full"><summary>Diğer hedefler</summary><div class="field-grid compact-grid">${advanced}</div></details>`;
}

function renderPlants(panel) {
  const plants = plantOptions();
  if (!selectedPlantId || !state.plant_catalog?.records?.[selectedPlantId]) selectedPlantId = plants[0]?.id || "";
  const plant = state.plant_catalog?.records?.[selectedPlantId];
  if (!plant) {
    panel.innerHTML = '<p class="empty-list">Bitki kütüphanesi boş.</p>';
    return;
  }
  const stages = plant.profile?.stages || {};
  const breeders = state.plant_catalog?.breeders || {};
  panel.innerHTML = `<div class="library-layout">
    <aside class="library-index"><div class="library-tools"><input type="search" data-plant-search placeholder="Bitki ara"><button class="secondary-button compact" type="button" data-add-plant>+ Bitki</button></div>
      <div data-plant-list>${plants.map((item) => `<button type="button" class="library-item ${item.id === plant.id ? "active" : ""}" data-plant-id="${html(item.id)}" data-search="${html(`${item.name} ${item.english_name} ${item.botanical_name}`.toLowerCase())}"><span><b>${html(item.name)}</b><small>${html(item.botanical_name || item.english_name)}</small></span><em>${html(item.cultivars?.length || item.cultivar_examples?.length || 0)}</em></button>`).join("")}</div>
    </aside>
    <form class="library-detail" data-plant-form>
      <div class="record-heading"><div><span class="record-type">${plant.built_in ? "Düzenlenebilir örnek profil" : "Kendi bitkin"}</span><h3>${html(plant.name)}</h3><p>${html(plant.notes || "Aşama sürelerini ve yetiştirme hedeflerini düzenle.")}</p></div><button class="primary-button" type="submit">Değişiklikleri kaydet</button></div>
      <details class="advanced-settings plant-identity"><summary>Bitki bilgileri</summary><div class="field-grid">
        ${field("plant","name","Görünen ad",plant.name)}${field("plant","english_name","İngilizce ad",plant.english_name)}${field("plant","botanical_name","Botanik ad",plant.botanical_name)}
        ${field("plant","category","Kategori",plant.category)}<label class="wide"><span>Not</span><textarea name="plant.notes">${html(plant.notes)}</textarea></label>
      </div></details>
      <section class="target-ledger"><header><div><h3>Aşama hedefleri</h3><p>Ürün seçimi Besin Programları bölümünde yapılır; burada yalnızca bitkiye ait hedefler tutulur.</p></div></header>
        ${stageOrder.map((stage) => { const target = stages[stage] || {}; return `<details class="target-row"><summary><span><b>${html(state.stage_labels[stage] || stage)}</b><small>${target.enabled ? `${html(target.planned_days)} gün · ${html(target.photoperiod)} saat` : "Kullanılmıyor"}</small></span><label class="inline-check"><input name="stage.${stage}.enabled" type="checkbox" ${target.enabled ? "checked" : ""}> Kullan</label></summary><div class="field-grid compact-grid">
          ${stageTargetFields(stage, target)}
        </div></details>`; }).join("")}
      </section>
      ${plant.cultivars?.length ? `<section class="cultivar-library"><header><div><h3>Çeşit / strain kütüphanesi</h3><p>${html(plant.cultivars.length)} kayıt · katalog ${html(state.plant_catalog.catalog_version || "yerel")}. Tamamı aranabilir.</p></div><input type="search" data-cultivar-search placeholder="Northern Light, Purple Haze…"></header><div class="cultivar-rows" data-cultivar-list>${cultivarRows(plant, breeders)}</div></section>` : ""}
    </form>
  </div>`;
  panel.querySelectorAll("[data-plant-id]").forEach((button) => button.addEventListener("click", () => { selectedPlantId = button.dataset.plantId; renderSetup(); }));
  panel.querySelector("[data-plant-search]").addEventListener("input", (event) => {
    const query = event.target.value.trim().toLowerCase();
    panel.querySelectorAll("[data-plant-id]").forEach((item) => { item.hidden = Boolean(query) && !item.dataset.search.includes(query); });
  });
  panel.querySelector("[data-add-plant]").addEventListener("click", openAddPlantDialog);
  panel.querySelector("[data-plant-form]").addEventListener("submit", savePlant);
  panel.querySelector("[data-cultivar-search]")?.addEventListener("input", (event) => {
    panel.querySelector("[data-cultivar-list]").innerHTML = cultivarRows(plant, breeders, event.target.value);
  });
}

function cultivarRows(plant, breeders, query = "") {
  const search = query.trim().toLowerCase();
  const rows = (plant.cultivars || []).filter((item) => !search || `${item.name} ${item.growth_type} ${breeders[item.breeder_id]?.name || ""}`.toLowerCase().includes(search));
  return rows.length ? rows.map((item) => `<div class="cultivar-row"><b>${html(item.name)}</b><span>${html(item.growth_type === "autoflower" ? "Autoflower" : "Photoperiod")}</span><small>${html(breeders[item.breeder_id]?.name || "Kaynak belirtilmedi")}</small></div>`).join("") : '<p class="empty-list">Eşleşen çeşit yok.</p>';
}

function openAddPlantDialog() {
  openDialog({
    kicker: "Bitki kütüphanesi", title: "Yeni bitki ekle", submitLabel: "Bitkiyi oluştur",
    body: `<div class="dialog-grid"><label class="full"><span>Bitki adı</span><input name="name" maxlength="96" required></label><label><span>İngilizce ad</span><input name="english_name" maxlength="96"></label><label><span>Kategori</span><input name="category" maxlength="32" placeholder="Yapraklı, meyveli, aromatik…"></label></div>`,
    onSubmit: async (data) => {
      const name = String(data.get("name") || "").trim();
      selectedPlantId = `custom_${id().slice(0, 16)}`;
      await api("/api/v1/plants", { method: "POST", body: JSON.stringify({ plant_id: selectedPlantId, values: { name, english_name: data.get("english_name") || name, category: data.get("category") || "custom" } }) });
      dialog.close(); await loadState(); currentSetupView = "plants"; showToast("Bitki kütüphaneye eklendi.");
    },
  });
}

async function savePlant(event) {
  event.preventDefault();
  const plant = JSON.parse(JSON.stringify(state.plant_catalog.records[selectedPlantId]));
  const data = new FormData(event.currentTarget);
  for (const key of ["name", "english_name", "botanical_name", "category", "notes"]) plant[key] = data.get(`plant.${key}`) || "";
  plant.profile ||= { kind: "editable_example", stages: {} };
  for (const stage of stageOrder) {
    const target = plant.profile.stages[stage] ||= {};
    target.enabled = data.has(`stage.${stage}.enabled`);
    for (const key of ["planned_days","photoperiod","light_intensity","day_temperature","night_temperature","humidity","vpd","co2","water_temperature","do_minimum","ph_min","ph_max","ec_min","ec_max"]) target[key] = Number(data.get(`stage.${stage}.${key}`));
  }
  await api("/api/v1/plants", { method: "POST", body: JSON.stringify({ plant_id: selectedPlantId, values: plant }) });
  await loadState(); currentSetupView = "plants"; showToast("Bitki profili kaydedildi.");
}

function fluidLabel(fluid) {
  const categories = { ph: "pH düzenleyici", base: "Ana besin", supplement: "Takviye", booster: "Güçlendirici", biostimulant: "Biyostimülan", conditioner: "Ortam düzenleyici", cleaner: "Temizleme / bitiş", other: "Diğer" };
  return categories[fluid.category] || fluid.category || "Diğer";
}

function fluidPhaseLabel(value) {
  const labels = { all: "Tüm aşamalar", germination: "Çimlenme", early_veg: "Erken gelişim", veg: "Gelişim", bloom: "Çiçeklenme", darkness: "Karanlık", harvest: "Hasat / Kurutma" };
  return labels[value] || value || "Tüm aşamalar";
}

function fluidMediumLabel(value) {
  const labels = { all: "Tüm medyalar", "hydro/coco": "Hidroponik / Coco", hydro: "Hidroponik", coco: "Coco", soil: "Toprak" };
  return labels[value] || value || "Tüm medyalar";
}

function renderNutrients(panel) {
  const catalog = state.nutrient_catalog || {};
  const programs = (catalog.program_order || []).map((programId) => catalog.programs?.[programId]).filter(Boolean);
  const products = catalog.product_order || [];
  const fluids = state.hardware?.dosing_fluids || [];
  const tabs = [
    ["programs", "Besin programları", `${programs.length}`],
    ["products", "Ürün kütüphanesi", `${products.length}`],
    ["mine", "Benim ürünlerim", `${fluids.length}`],
  ];
  panel.innerHTML = `<section class="nutrient-workflow" aria-label="Besin programı seçim akışı"><div><span>1</span><b>Bitki</b><small>Aşama planı</small></div><i>→</i><div><span>2</span><b>Ortam</b><small>Hidro · Coco · Toprak</small></div><i>→</i><div><span>3</span><b>Marka</b><small>Kullanacağın seri</small></div><i>→</i><div><span>4</span><b>Program</b><small>Ürün seti</small></div></section>
    <nav class="library-tabs" aria-label="Besin kütüphanesi bölümleri">${tabs.map(([view,label,count]) => `<button type="button" class="${nutrientLibraryView === view ? "active" : ""}" data-nutrient-view="${view}"><span>${html(label)}</span><small>${html(count)}</small></button>`).join("")}</nav>
    <div data-nutrient-library-panel></div>`;
  panel.querySelectorAll("[data-nutrient-view]").forEach((button) => button.addEventListener("click", () => {
    nutrientLibraryView = button.dataset.nutrientView;
    renderNutrients(panel);
  }));
  const body = panel.querySelector("[data-nutrient-library-panel]");
  if (nutrientLibraryView === "products") renderNutrientProducts(body);
  else if (nutrientLibraryView === "mine") renderMyNutrients(body);
  else renderNutrientPrograms(body);
}

function nutrientProgramProducts(program, scope = "core") {
  const ids = [...(program?.core_product_ids || [])];
  if (scope === "complete") ids.push(...(program?.optional_product_ids || []));
  return [...new Set(ids)].map((productId) => state.nutrient_catalog?.products?.[productId]).filter(Boolean);
}

function renderNutrientPrograms(panel) {
  const catalog = state.nutrient_catalog || {};
  const brands = (catalog.brand_order || []).map((brandId) => catalog.brands?.[brandId]).filter((brand) => brand?.program_ids?.length);
  const programs = (catalog.program_order || []).map((programId) => catalog.programs?.[programId]).filter(Boolean);
  const brandOptions = [["all",`Tüm markalar · ${brands.length}`], ...brands.map((brand) => [brand.id, `${brand.name} · ${brand.program_ids.length}`])];
  const environmentOptions = [["all","Tüm ortamlar"],["hydro","Hidroponik"],["coco","Coco"],["soil","Toprak"]];
  panel.innerHTML = `<section class="program-library"><header class="catalog-head"><div><span class="record-type">Hazır program kütüphanesi</span><h3>${programs.length} besin programı</h3><p>Önce ortamını ve markanı seç. Temel ürün setini tek işlemle ekle; miktarlar yetiştirme ve üretici çizelgesine göre ayrıca planlanır.</p></div></header>
    <div class="catalog-tools program-tools"><label><span>Marka</span><select data-program-brand>${optionRows(brandOptions,nutrientProgramBrand)}</select></label><label><span>Yetiştirme ortamı</span><select data-program-environment>${optionRows(environmentOptions,nutrientProgramEnvironment)}</select></label></div>
    <div class="program-ledger">${programs.map((program) => nutrientProgramRow(program)).join("")}</div></section>`;
  const applyFilters = () => {
    nutrientProgramBrand = panel.querySelector("[data-program-brand]").value;
    nutrientProgramEnvironment = panel.querySelector("[data-program-environment]").value;
    panel.querySelectorAll("[data-program-id]").forEach((row) => {
      const environments = row.dataset.programEnvironments.split(",");
      row.hidden = (nutrientProgramBrand !== "all" && row.dataset.programBrand !== nutrientProgramBrand)
        || (nutrientProgramEnvironment !== "all" && !environments.includes("universal") && !environments.includes(nutrientProgramEnvironment));
    });
  };
  panel.querySelector("[data-program-brand]").addEventListener("change", applyFilters);
  panel.querySelector("[data-program-environment]").addEventListener("change", applyFilters);
  panel.querySelectorAll("[data-program-id]").forEach((button) => button.addEventListener("click", () => openNutrientProgramDialog(catalog.programs?.[button.dataset.programId])));
  applyFilters();
}

function nutrientProgramRow(program) {
  const core = nutrientProgramProducts(program);
  const usedStages = stageOrder.filter((stage) => program.stages?.[stage]?.core_product_ids?.length);
  const medium = program.medium_class === "hydro_coco" ? "Hidro / Coco" : program.medium_class === "universal" ? "Tüm ortamlar" : fluidMediumLabel(program.medium_class);
  return `<button type="button" class="program-row" data-program-id="${html(program.id)}" data-program-brand="${html(program.brand_id)}" data-program-environments="${html((program.supported_environments || []).join(","))}"><span class="program-mark">${html(program.brand.slice(0,2).toUpperCase())}</span><span><small>${html(program.brand)}</small><b>${html(program.name)}</b></span><span><small>Uyum</small><b>${html(medium)}</b></span><span class="program-stages" aria-label="Kapsanan aşamalar">${usedStages.map((stage) => `<i title="${html(state.stage_labels[stage] || stage)}">${html((state.stage_labels[stage] || stage).slice(0,3))}</i>`).join("") || "—"}</span><span><b>${core.length} temel ürün</b><small>${program.optional_product_ids?.length || 0} yardımcı ürün seçilebilir</small></span><em>${program.cycle_coverage === "complete" ? "Tam döngü" : "Aşama ürünü"}</em></button>`;
}

function openNutrientProgramDialog(program) {
  if (!program) return;
  const core = nutrientProgramProducts(program, "core");
  const optional = (program.optional_product_ids || []).map((productId) => state.nutrient_catalog?.products?.[productId]).filter(Boolean);
  const stageRows = stageOrder.map((stage) => {
    const productIds = program.stages?.[stage]?.core_product_ids || [];
    const names = productIds.map((productId) => state.nutrient_catalog?.products?.[productId]?.name).filter(Boolean);
    return names.length ? `<div><dt>${html(state.stage_labels[stage] || stage)}</dt><dd>${names.map(html).join(" · ")}</dd></div>` : "";
  }).join("");
  openDialog({
    kicker: program.brand,
    title: program.name,
    submitLabel: "Ürün setini ekle",
    body: `<div class="program-dialog-lead"><span>${html(program.cycle_coverage === "complete" ? "Tam döngü programı" : "Belirli aşama programı")} · ${html(program.medium_class === "hydro_coco" ? "Hidro / Coco" : program.medium_class === "universal" ? "Tüm ortamlar" : fluidMediumLabel(program.medium_class))}</span><p>${html(program.disclaimer)}</p></div>
      <dl class="program-stage-map">${stageRows}</dl>
      <fieldset class="program-scope"><legend>Ürün kapsamı</legend><label><input type="radio" name="scope" value="core" checked><span><b>Temel set · ${core.length} ürün</b><small>${core.map((item) => item.name).join(" · ")}</small></span></label><label><input type="radio" name="scope" value="complete"><span><b>Geniş set · ${core.length + optional.length} ürün</b><small>Temel sete markanın uyumlu ${optional.length} yardımcı ürünü eklenir; hepsini kullanmak zorunlu değildir.</small></span></label></fieldset>
      <details class="advanced-settings"><summary>Yardımcı ürünleri gör</summary><div class="program-product-list">${optional.length ? optional.map((item) => `<span><b>${html(item.name)}</b><small>${html(fluidPhaseLabel(item.phase))} · ${html(fluidLabel(item))}</small></span>`).join("") : '<p class="empty-list">Bu program için ayrı yardımcı ürün yok.</p>'}</div></details>
      <p class="catalog-source">Ürün kimlikleri üretici kataloğundan doğrulandı · ${html(program.verified_on)} · <a href="${html(program.source_url)}" target="_blank" rel="noreferrer">Üretici kaynağı</a></p>`,
    onSubmit: async (data) => {
      const result = await api("/api/v1/nutrient-programs/add", { method: "POST", body: JSON.stringify({ program_id: program.id, scope: data.get("scope") || "core" }) });
      dialog.close(); await loadState(); currentSetupView = "nutrients"; nutrientLibraryView = "mine";
      showToast(`${result.result.added.length} ürün listenize eklendi.`);
    },
  });
}

function renderNutrientProducts(panel) {
  const fluids = state.hardware?.dosing_fluids || [];
  const catalog = state.nutrient_catalog || {};
  const brands = (catalog.brand_order || []).map((brandId) => catalog.brands?.[brandId]).filter(Boolean);
  const products = (catalog.product_order || []).map((productId) => catalog.products?.[productId]).filter(Boolean);
  const selectedCatalogIds = new Set(fluids.map((fluid) => fluid.catalog_id).filter(Boolean));
  const brandOptions = [["all",`Tüm markalar · ${products.length}`], ...brands.map((brand) => [brand.id, `${brand.name} · ${brand.product_ids?.length || 0}`])];
  panel.innerHTML = `<section class="nutrient-catalog"><header class="catalog-head"><div><span class="record-type">Ürün kütüphanesi</span><h3>${brands.length} marka · ${products.length} ürün</h3><p>Tek bir ürünü inceleyip listene ekleyebilirsin. Tam bir seri için Besin Programları'nı kullan.</p></div><button class="secondary-button" type="button" data-add-fluid>Özel ürün ekle</button></header>
    <div class="catalog-tools"><label><span>Ürün ara</span><input type="search" data-catalog-search placeholder="Örn. Sensi, CANNA, CalMag, Bloom…" autocomplete="off"></label><label><span>Marka</span><select data-catalog-brand>${optionRows(brandOptions,nutrientCatalogBrand)}</select></label></div>
    <div class="catalog-results">${products.map((product) => `<button type="button" class="catalog-product ${selectedCatalogIds.has(product.id) ? "selected" : ""}" data-catalog-product="${html(product.id)}" data-catalog-brand-id="${html(product.brand_id)}" data-catalog-search-text="${html(`${product.brand} ${product.name} ${product.line} ${product.part} ${product.npk}`.toLocaleLowerCase("tr"))}"><span class="catalog-brand">${html(product.brand)}</span><span><b>${html(product.name)}</b><small>${html(product.line)}${product.part ? ` · ${html(product.part)}` : ""}</small></span><span><b>${html(fluidLabel(product))}</b><small>${html(fluidPhaseLabel(product.phase))} · ${html(fluidMediumLabel(product.medium))}</small></span><span><b>${html(product.npk || "NPK etikette")}</b><small>${html(product.form === "powder" ? "Toz" : "Sıvı")} · ${html(product.input_type === "organic" ? "Organik" : product.input_type === "biological" ? "Biyolojik" : "Mineral")}</small></span><em>${selectedCatalogIds.has(product.id) ? "Eklendi" : "İncele"}</em></button>`).join("")}</div></section>`;
  panel.querySelector("[data-add-fluid]").addEventListener("click", () => openFluidDialog());
  const search = panel.querySelector("[data-catalog-search]");
  const brand = panel.querySelector("[data-catalog-brand]");
  const applyFilters = () => {
    const query = search.value.trim().toLocaleLowerCase("tr");
    nutrientCatalogBrand = brand.value;
    panel.querySelectorAll("[data-catalog-product]").forEach((row) => {
      row.hidden = (nutrientCatalogBrand !== "all" && row.dataset.catalogBrandId !== nutrientCatalogBrand) || (query && !row.dataset.catalogSearchText.includes(query));
    });
  };
  search.addEventListener("input", applyFilters);
  brand.addEventListener("change", applyFilters);
  applyFilters();
  panel.querySelectorAll("[data-catalog-product]").forEach((button) => button.addEventListener("click", () => openCatalogProductDialog(catalog.products?.[button.dataset.catalogProduct], selectedCatalogIds.has(button.dataset.catalogProduct))));
}

function renderMyNutrients(panel) {
  const fluids = state.hardware?.dosing_fluids || [];
  panel.innerHTML = `<section class="my-nutrients"><header class="catalog-head"><div><span class="record-type">Yerel ürün listen</span><h3>Benim ürünlerim · ${fluids.length}</h3><p>Elinde bulunan ürünler burada tutulur. Pompa bağlantısı ve kalibrasyon Dozaj bölümünde yapılır.</p></div><button class="secondary-button" type="button" data-add-fluid>Özel ürün ekle</button></header><div class="record-ledger">${fluids.map((fluid) => `<button type="button" class="record-row" data-fluid-id="${html(fluid.id)}"><span class="record-code">${html(fluid.required ? "pH" : "N")}</span><span><b>${html(fluid.name)}</b><small>${html(fluid.brand || "Belirtilmedi")} · ${html(fluid.line || fluid.part || "Özel ürün")}</small></span><span>${html(fluidLabel(fluid))}</span><small>${html(fluidPhaseLabel(fluid.phase))} · ${html(fluidMediumLabel(fluid.medium))}</small><em>Düzenle</em></button>`).join("") || '<p class="empty-list">Henüz ürün eklenmedi. Bir besin programı seçebilir veya özel ürün ekleyebilirsin.</p>'}</div></section>`;
  panel.querySelector("[data-add-fluid]").addEventListener("click", () => openFluidDialog());
  panel.querySelectorAll("[data-fluid-id]").forEach((button) => button.addEventListener("click", () => openFluidDialog(fluids.find((item) => item.id === button.dataset.fluidId))));
}

function openCatalogProductDialog(product, selected = false) {
  if (!product) return;
  const typeLabels = { mineral: "Mineral", organic: "Organik", biological: "Biyolojik" };
  openDialog({ kicker: product.brand, title: product.name, submitLabel: selected ? "Kütüphanemde" : "Kütüphaneme ekle", secondaryLabel: "Kapat",
    body: `<div class="catalog-detail-lead"><span>${html(product.line)}${product.part ? ` · ${html(product.part)}` : ""}</span><p>${html(product.description)}</p></div><dl class="catalog-detail-grid"><div><dt>Kategori</dt><dd>${html(fluidLabel(product))}</dd></div><div><dt>Aşama</dt><dd>${html(fluidPhaseLabel(product.phase))}</dd></div><div><dt>Medya</dt><dd>${html(fluidMediumLabel(product.medium))}</dd></div><div><dt>Form</dt><dd>${html(product.form === "powder" ? "Toz" : "Sıvı")}</dd></div><div><dt>İçerik tipi</dt><dd>${html(typeLabels[product.input_type] || product.input_type)}</dd></div><div><dt>NPK</dt><dd>${html(product.npk || "Üretici etiketi/pazara göre kontrol edilmeli")}</dd></div></dl><p class="catalog-source">Ürün kimliği ve sınıflandırma resmi üretici dizininden doğrulandı · ${html(product.verified_on)} · <a href="${html(product.source_url)}" target="_blank" rel="noreferrer">Üretici kaynağı</a></p>`,
    onSubmit: async () => {
      if (selected) { dialog.close(); return; }
      await api("/api/v1/nutrients/catalog/add", { method: "POST", body: JSON.stringify({ catalog_id: product.id }) });
      dialog.close(); await loadState(); currentSetupView = "nutrients"; showToast(`${product.name} ürünlerine eklendi.`);
    },
  });
}

function openFluidDialog(fluid = null) {
  const edit = Boolean(fluid);
  const phaseOptions = [["all","Tüm aşamalar"], ...stageOrder.map((stage) => [stage, state.stage_labels[stage] || stage])];
  const mediumOptions = [["all","Tüm medyalar"],["hydro/coco","Hidroponik / Coco"],["hydro","Hidroponik"],["coco","Coco"],["soil","Toprak"]];
  openDialog({ kicker: "Besinler", title: edit ? "Ürünü düzenle" : "Ürün ekle", submitLabel: "Kaydet",
    body: `<div class="dialog-grid"><label><span>Ürün adı</span><input name="name" value="${html(fluid?.name || "")}" required></label><label><span>Marka</span><input name="brand" value="${html(fluid?.brand || "")}"></label><label><span>Kategori</span><select name="category" ${fluid?.required ? "disabled" : ""}>${[["base","Ana besin"],["supplement","Takviye"],["booster","Güçlendirici"],["biostimulant","Biyostimülan"],["conditioner","Ortam düzenleyici"],["cleaner","Temizleme / bitiş"],["other","Diğer"],["ph","pH düzenleyici"]].map(([id,label]) => `<option value="${id}" ${(fluid?.category || "other") === id ? "selected" : ""}>${label}</option>`).join("")}</select></label></div><details class="advanced-settings dialog-advanced"><summary>Ürün detayları</summary><div class="dialog-grid"><label><span>Seri</span><input name="line" value="${html(fluid?.line || "")}"></label><label><span>Parça</span><input name="part" value="${html(fluid?.part || "")}"></label><label><span>NPK</span><input name="npk" value="${html(fluid?.npk || "")}"></label><label><span>Üreticinin önerdiği aşama</span><select name="phase">${optionRows(phaseOptions, fluid?.phase || "all")}</select></label><label><span>Üreticinin önerdiği medya</span><select name="medium">${optionRows(mediumOptions, fluid?.medium || "all")}</select></label></div></details>`,
    onSubmit: async (data) => {
      const fluids = JSON.parse(JSON.stringify(state.hardware?.dosing_fluids || []));
      const target = edit ? fluids.find((item) => item.id === fluid.id) : { id: `fluid_${id().slice(0,16)}`, required: false };
      for (const key of ["name","brand","category","line","part","npk","phase","medium"]) if (data.has(key)) target[key] = data.get(key);
      if (edit && target.catalog_id && target.name !== fluid.name) { target.catalog_id = ""; target.official = false; }
      if (!edit) fluids.push(target);
      await api("/api/v1/hardware", { method: "POST", body: JSON.stringify({ dosing_fluids: fluids }) });
      dialog.close(); await loadState(); currentSetupView = "nutrients"; showToast("Besin kataloğu kaydedildi.");
    },
  });
}

const driverLabels = { atlas_do: "Atlas EZO DO", atlas_ph: "Atlas EZO pH", atlas_ec: "Atlas EZO EC", atlas_rtd: "Atlas EZO RTD", waveshare_motor_hat: "Waveshare Motor HAT", pca9685_generic: "PCA9685" };

function i2cCandidate(address) {
  return Object.values(state.i2c_registry?.candidates || {}).find((item) => Number(item.address) === Number(address));
}

function i2cStatus(item, candidate) {
  if (!candidate?.online) return ["Bağlantı yok", "limited"];
  if (String(item.driver || "").startsWith("atlas_") && candidate.identity_verified) return ["Bağlı · kimlik doğrulandı", "supported"];
  if (item.driver === "waveshare_motor_hat") return ["Bağlı · kart tipi onaylı", "supported"];
  return ["Bağlı · sürücü tanımlı", "supported"];
}

function renderHardware(panel) {
  const hardware = state.hardware || {};
  const assignments = hardware.device_assignments || [];
  const i2cRegistry = state.i2c_registry || {};
  const i2cCandidates = Object.values(i2cRegistry.candidates || {});
  const newI2cCandidates = i2cCandidates.filter((item) => item.online && !item.configured);
  const health = i2cRegistry.health || {};
  const i2cScan = i2cRegistry.last_scan;
  const onlineCount = assignments.filter((item) => i2cCandidate(item.address)?.online).length;
  panel.innerHTML = `<section class="hardware-section wired-hardware"><header class="section-head"><div><h3>Raspberry Pi bağlantı hattı</h3><small>Kartı bağla, tara ve bulunan cihazı onayla</small></div><button class="primary-button compact" type="button" data-i2c-scan>Donanımı tara</button></header>
      <div class="hardware-busline ${health.available ? "bus-online" : "bus-offline"}">
        <div class="bus-origin"><span class="pi-port">I²C</span><div><b>Raspberry Pi</b><small>${html(health.path || `/dev/i2c-${hardware.i2c_bus ?? 1}`)}</small></div></div>
        <div class="bus-track" aria-hidden="true"><i></i><i></i><i></i></div>
        <div class="bus-metrics"><span><b>${health.available ? "Hazır" : "Bağlantı yok"}</b><small>${html(health.error || "I²C hattı erişilebilir")}</small></span><span><b>${onlineCount}/${assignments.length}</b><small>tanımlı cihaz çevrimiçi</small></span><span><b>${newI2cCandidates.length}</b><small>yeni cihaz bulundu</small></span></div>
      </div>
      <div class="subsection-label"><b>Tanımlı kablolu cihazlar</b><small>${assignments.length}</small></div>
      <div class="record-ledger">${assignments.length ? assignments.map((item) => hardwareAssignmentRow(item, i2cCandidate(item.address))).join("") : '<p class="empty-list">Henüz tanımlı cihaz yok. Kartları Raspberry Pi üzerine bağlayıp tarayın.</p>'}</div>
      ${newI2cCandidates.length ? `<div class="detected-strip"><header><b>Yeni bulunanlar</b><small>Adres otomatik okundu; yalnızca kart tipini doğrulayın.</small></header><div class="record-ledger">${newI2cCandidates.map(hardwareCandidateRow).join("")}</div></div>` : ""}
      <details class="advanced-settings"><summary>Bağlantı ayrıntıları</summary><form class="hardware-connection-form" data-hardware-base><label><span>I²C veri yolu</span><input name="i2c_bus" type="number" min="0" max="255" value="${html(hardware.i2c_bus ?? 1)}"></label><label><span>Okuma aralığı · saniye</span><input name="poll_interval" type="number" min="10" max="300" value="${html(hardware.poll_interval ?? 30)}"></label><button class="secondary-button" type="submit">Kaydet</button></form><p class="connection-footnote">Son tarama: ${html(i2cScan?.finished_at ? String(i2cScan.finished_at).replace("T", " ").slice(0, 19) : "—")}</p></details></section>`;
  panel.querySelector("[data-hardware-base]").addEventListener("submit", saveHardwareBase);
  panel.querySelector("[data-i2c-scan]").addEventListener("click", scanI2C);
  panel.querySelectorAll("[data-hardware-address]").forEach((button) => button.addEventListener("click", () => { const item = assignments.find((entry) => entry.address === Number(button.dataset.hardwareAddress)); openI2CDeviceDialog(i2cCandidate(item.address), item); }));
  panel.querySelectorAll("[data-i2c-candidate]").forEach((button) => button.addEventListener("click", () => openI2CDeviceDialog(newI2cCandidates.find((item) => item.id === button.dataset.i2cCandidate))));
}

function hardwareAssignmentRow(item, candidate) {
  const [label, statusClass] = i2cStatus(item, candidate);
  return `<button type="button" class="record-row hardware-row ${candidate?.online ? "" : "offline"}" data-hardware-address="${item.address}"><span class="record-code">0x${Number(item.address).toString(16).toUpperCase().padStart(2,"0")}</span><span><b>${html(item.name)}</b><small>${html(driverLabels[item.driver] || item.driver)}</small></span><span class="support-state ${statusClass}">${html(label)}</span><em>Yönet</em></button>`;
}

function hardwareCandidateRow(item) {
  return `<button type="button" class="record-row hardware-row discovered" data-i2c-candidate="${html(item.id)}"><span class="record-code">${html(item.address_hex)}</span><span><b>${html(item.model || item.chip)}</b><small>${html(item.chip)}${item.firmware ? ` · ${html(item.firmware)}` : ""}</small></span><span class="support-state supported">Fiziksel olarak bulundu</span><em>Tanımla</em></button>`;
}

function renderIoT(panel) {
  const registry = state.device_registry || {};
  const devices = Object.values(registry.devices || {}).sort((left, right) => Number(right.online) - Number(left.online) || String(left.name).localeCompare(String(right.name)));
  const candidates = Object.values(registry.candidates || {}).sort((left, right) => Number(right.online) - Number(left.online) || Number(right.identity_confidence || 0) - Number(left.identity_confidence || 0) || String(left.host).localeCompare(String(right.host), undefined, { numeric: true }));
  const growCandidates = candidates.filter((item) => ["grow_iot", "possible_iot"].includes(item.category));
  const inventory = candidates.filter((item) => !["grow_iot", "possible_iot"].includes(item.category));
  const scan = registry.last_scan;
  const protocolLabels = { shelly_http: "Shelly", shelly_mdns: "mDNS", tplink_udp: "Tapo", tuya_udp_broadcast: "Tuya", matter_mdns: "Matter", ssdp: "SSDP", upnp_description: "UPnP", arp_neighbor: "Ağ komşuları", tcp_probe: "Yerel portlar", http_mdns: "mDNS", homekit_mdns: "HomeKit" };
  const methods = Object.entries(scan?.protocol_counts || {}).filter(([, count]) => count).map(([method, count]) => `<span>${html(protocolLabels[method] || method)} <b>${html(count)}</b></span>`).join("");
  panel.innerHTML = `<section class="iot-workbench">
    <header class="iot-scan-hero">
      <div class="network-radar ${scan ? "has-scan" : ""}" aria-hidden="true"><i></i><i></i><span>RF</span></div>
      <div class="iot-scan-copy"><span class="kicker">YEREL AĞ ENVANTERİ</span><h3>IoT cihazlarını bul</h3><p>Wi-Fi cihazlarını tek listede gör. Bir cihaz sen doğrulamadan yetiştirme sistemine eklenmez.</p><div class="protocol-strip">${methods || "<span>mDNS</span><span>SSDP</span><span>Tapo</span><span>Tuya</span><span>MAC üreticisi</span>"}</div></div>
      <div class="scan-actions"><dl><div><dt>Ağda görülen</dt><dd>${html(scan?.observed_host_count ?? "—")}</dd></div><div><dt>Kimliği bulunan</dt><dd>${html(scan?.recognized_count ?? "—")}</dd></div><div><dt>IoT adayı</dt><dd>${html(scan?.grow_candidate_count ?? "—")}</dd></div></dl><button class="primary-button" type="button" data-network-scan>${scan ? "Yeniden tara" : "Ağı tara"}</button></div>
    </header>
    <div class="iot-scan-note"><span>${scan ? `Son tarama ${html(String(scan.finished_at || "").replace("T", " ").slice(0, 16))} · ${html(scan.duration_ms || 0)} ms` : "İlk taramada tüm yerel ağ komşuları envantere alınır."}</span><small>Pilli sensörleri uyandırıp tarayın; uyuyan cihazların önceki kaydı korunur.</small></div>
    <div class="iot-tools"><label><span>Cihaz ara</span><input type="search" placeholder="Ad, üretici, IP veya MAC" data-iot-search></label><label><span>Göster</span><select data-iot-filter><option value="all">Tüm cihazlar</option><option value="grow">IoT adayları</option><option value="identified">Kimliği bulunanlar</option><option value="unknown">Kimliği belirsizler</option></select></label></div>
    ${devices.length ? `<section class="iot-list-section approved-iot"><div class="subsection-label"><b>Tanımladığım cihazlar</b><small>${devices.length}</small></div><div class="record-ledger">${devices.map(networkDeviceRow).join("")}</div></section>` : ""}
    <section class="iot-list-section"><div class="subsection-label"><b>Yetiştirmede kullanılabilecek adaylar</b><small>${growCandidates.length}</small></div><div class="record-ledger">${growCandidates.length ? growCandidates.map(networkCandidateRow).join("") : '<p class="empty-list">Henüz bir IoT adayı bulunamadı. Cihazı uyandırıp yeniden tarayın.</p>'}</div></section>
    <details class="network-inventory" open><summary><span>Ağdaki diğer cihazlar</span><small>${inventory.length} cihaz · yanlış marka tahmini yapılmadan listelenir</small></summary><div class="record-ledger">${inventory.length ? inventory.map(networkCandidateRow).join("") : '<p class="empty-list">Başka ağ cihazı görülmedi.</p>'}</div></details>
  </section>`;
  panel.querySelector("[data-network-scan]").addEventListener("click", scanNetwork);
  panel.querySelectorAll("[data-network-candidate]").forEach((button) => button.addEventListener("click", () => openNetworkDeviceDialog(candidates.find((item) => item.id === button.dataset.networkCandidate))));
  panel.querySelectorAll("[data-network-device]").forEach((button) => button.addEventListener("click", () => openNetworkDeviceDialog(devices.find((item) => item.id === button.dataset.networkDevice))));
  const applyFilter = () => {
    const query = panel.querySelector("[data-iot-search]").value.trim().toLocaleLowerCase("tr");
    const filter = panel.querySelector("[data-iot-filter]").value;
    panel.querySelectorAll("[data-iot-row]").forEach((row) => {
      const matchesQuery = !query || row.dataset.iotSearch.includes(query);
      const confidence = Number(row.dataset.iotConfidence || 0);
      const category = row.dataset.iotCategory;
      const matchesFilter = filter === "all" || (filter === "grow" && ["grow_iot","possible_iot"].includes(category)) || (filter === "identified" && confidence >= 70) || (filter === "unknown" && confidence < 70);
      row.hidden = !(matchesQuery && matchesFilter);
    });
  };
  panel.querySelector("[data-iot-search]").addEventListener("input", applyFilter);
  panel.querySelector("[data-iot-filter]").addEventListener("change", applyFilter);
}

function networkCandidateRow(item) {
  const confidence = Number(item.identity_confidence || 0);
  const support = !item.online ? "Önceki taramada görüldü" : confidence >= 85 ? "Kimliği güçlü" : confidence >= 70 ? "Cihaz ailesi bulundu" : item.manufacturer ? "Üretici bulundu" : "Kimlik doğrulaması gerekli";
  const mark = item.vendor === "Unknown" ? "?" : (item.vendor || "?").slice(0,2).toUpperCase();
  const evidence = (item.evidence || [item.protocol]).slice(0,2).join(" · ");
  const search = `${item.name || ""} ${item.vendor || ""} ${item.manufacturer || ""} ${item.model || ""} ${item.host || ""} ${item.mac || ""}`.toLocaleLowerCase("tr");
  return `<button type="button" class="network-row ${item.online ? "" : "offline"}" data-network-candidate="${html(item.id)}" data-iot-row data-iot-search="${html(search)}" data-iot-category="${html(item.category || "unknown")}" data-iot-confidence="${confidence}"><span class="vendor-mark">${html(mark)}</span><span><b>${html(item.name || item.model || item.host)}</b><small>${html(item.vendor === "Unknown" ? (item.manufacturer || "Üretici bilinmiyor") : item.vendor)}${item.model ? ` · ${html(item.model)}` : ""}</small></span><span><b>${html(item.host)}</b><small>${html(item.mac || "MAC bilinmiyor")}</small></span><span><small>${html(evidence)}</small><span class="support-state ${confidence >= 70 ? "supported" : "limited"}">${html(support)} · ${confidence}/100</span></span><em>${confidence >= 70 ? "İncele ve tanımla" : "Kimliği doğrula"}</em></button>`;
}

function networkDeviceRow(item) {
  const roles = { environment_sensor: "Ortam sensörü", co2_sensor: "CO₂ sensörü", light_dimmer: "Işık dimmeri", light_power: "Işık gücü", outlet_bank: "Priz grubu", humidifier: "Nemlendirici", unassigned: "Rol atanmadı" };
  const connections = { credentials_required: "Giriş bilgisi gerekli", adapter_pending: "Bağlantı sürücüsü hazırlanıyor", connected: "Bağlı" };
  const search = `${item.name || ""} ${item.vendor || ""} ${item.model || ""} ${item.host || ""} ${item.mac || ""}`.toLocaleLowerCase("tr");
  return `<button type="button" class="network-row enrolled ${item.online ? "" : "offline"}" data-network-device="${html(item.id)}" data-iot-row data-iot-search="${html(search)}" data-iot-category="${html(item.category || "grow_iot")}" data-iot-confidence="${html(item.identity_confidence || 100)}"><span class="vendor-mark">${html((item.vendor || "?").slice(0,2).toUpperCase())}</span><span><b>${html(item.name || item.model || item.host)}</b><small>${html(item.vendor)} · ${html(roles[item.role] || item.role || "Rol atanmadı")}</small></span><span><b>${html(item.host)}</b><small>${html(item.mac || "MAC bilinmiyor")}</small></span><span class="support-state ${item.connection_status === "connected" ? "supported" : "limited"}">${html(item.online ? (connections[item.connection_status] || "Bağlantı sürücüsü bekliyor") : "Şu anda çevrimdışı")}</span><em>Yönet</em></button>`;
}

async function scanI2C(event) {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = "Donanım taranıyor…";
  try {
    const payload = await api("/api/v1/i2c/discover", { method: "POST", body: JSON.stringify({}) });
    await loadState(); currentSetupView = "hardware";
    showToast(`${Number(payload.result?.last_scan?.online_count || 0)} kablolu cihaz fiziksel olarak bulundu.`);
  } catch (error) {
    button.disabled = false; button.textContent = "Donanımı tara"; showToast(error.message, true);
  }
}

async function scanNetwork(event) {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = "Ağ taranıyor…";
  try {
    const payload = await api("/api/v1/network/discover", { method: "POST", body: JSON.stringify({ timeout: 6 }) });
    await loadState(); currentSetupView = "iot";
    const observed = Number(payload.result?.last_scan?.observed_host_count || 0);
    const recognized = Number(payload.result?.last_scan?.recognized_count || 0);
    showToast(`${observed} cihaz görüldü; ${recognized} cihazın kimliği bulundu.`);
  } catch (error) {
    button.disabled = false; button.textContent = "Ağı tara"; showToast(error.message, true);
  }
}

function openNetworkDeviceDialog(item) {
  if (!item) return;
  const edit = item.status === "enrolled";
  const manualIdentity = !item.supported || Number(item.identity_confidence || 0) < 70;
  const roles = [["unassigned","Şimdilik rol verme"],["environment_sensor","Ortam sıcaklık / nem sensörü"],["co2_sensor","CO₂ sensörü"],["light_dimmer","Işık dimmeri"],["light_power","Işık aç / kapat"],["outlet_bank","Priz grubu"],["humidifier","Nemlendirici"]];
  const vendors = ["Shelly","Tuya","TP-Link / Tapo","Dreo","Matter","Diğer"];
  const selectedVendor = vendors.includes(item.vendor) ? item.vendor : "Diğer";
  const evidence = (item.evidence || []).map((value) => `<li>${html(value)}</li>`).join("");
  openDialog({
    kicker: "Ağ cihazı", title: edit ? "Cihazı düzenle" : "Cihazı tanımla", submitLabel: edit ? "Kaydet" : "Cihaz listesine ekle",
    body: `<div class="device-fingerprint"><span class="vendor-mark large-mark">${html((item.vendor || "?").slice(0,2).toUpperCase())}</span><div><b>${html(item.name || item.model || item.host)}</b><small>${html(item.host)} · ${html(item.mac || "MAC bilinmiyor")} · kimlik güveni ${html(item.identity_confidence || 0)}/100</small></div></div>${manualIdentity ? '<p class="identity-warning">Bu cihaz ağda bulundu fakat ürün kimliği kesin değil. Üzerindeki marka ve modeli bir kez doğruladığınızda sonraki taramalarda hatırlanır.</p>' : ""}<div class="dialog-grid"><label class="full"><span>Cihaz adı</span><input name="name" value="${html(item.name || item.model || item.host)}" required></label><label><span>Üretici</span><select name="vendor">${vendors.map((vendor) => `<option value="${html(vendor)}" ${selectedVendor === vendor ? "selected" : ""}>${html(vendor)}</option>`).join("")}</select></label><label><span>Model</span><input name="model" value="${html(item.model || "")}" placeholder="Cihaz üzerindeki model"></label><label class="full"><span>Ne için kullanılacak?</span><select name="role">${roles.map(([role,label]) => `<option value="${role}" ${(item.role || item.suggested_role || "unassigned") === role ? "selected" : ""}>${label}</option>`).join("")}</select></label>${manualIdentity ? '<label class="identity-confirm full"><input name="confirm_identity" type="checkbox" required><span>Üretici ve cihazı kontrol ederek doğruladım</span></label>' : ""}</div><details class="advanced-settings dialog-advanced"><summary>Nasıl bulundu?</summary>${evidence ? `<ul class="evidence-list">${evidence}</ul>` : ""}<dl class="fingerprint-grid"><div><dt>Protokol</dt><dd>${html(item.protocol)}</dd></div><div><dt>MAC üreticisi</dt><dd>${html(item.manufacturer || "Bilinmiyor")}</dd></div><div><dt>Keşif yöntemleri</dt><dd>${html((item.discovery_methods || []).join(", ") || "Ağ komşusu")}</dd></div><div><dt>Bağlantı</dt><dd>Kimlik onayından sonra uygun sürücü kurulacak</dd></div></dl></details>${edit ? '<button class="danger-button dialog-remove" type="button" data-remove-network>Bu tanımı kaldır</button>' : ""}`,
    onSubmit: async (data) => {
      const vendor = data.get("vendor");
      const model = data.get("model");
      const identityChanged = vendor !== selectedVendor || model !== (item.model || "");
      await api("/api/v1/network/enroll", { method: "POST", body: JSON.stringify({ candidate_id: item.id, name: data.get("name"), vendor, model, role: data.get("role"), confirm_identity: Boolean(data.get("confirm_identity")) || identityChanged }) });
      dialog.close(); await loadState(); currentSetupView = "iot"; showToast(edit ? "IoT cihazı güncellendi." : "Cihaz kimliği kaydedildi.");
    },
  });
  dialogBody.querySelector("[data-remove-network]")?.addEventListener("click", async () => {
    if (!confirm(`${item.name || item.host} cihaz tanımı kaldırılsın mı?`)) return;
    try {
      await api("/api/v1/network/remove", { method: "POST", body: JSON.stringify({ candidate_id: item.id }) });
      dialog.close(); await loadState(); currentSetupView = "iot"; showToast("IoT cihazı tanımı kaldırıldı; keşif kaydı korundu.");
    } catch (error) { showToast(error.message, true); }
  });
}

async function saveHardwareBase(event) {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  await api("/api/v1/hardware", { method: "POST", body: JSON.stringify({ i2c_bus: Number(data.get("i2c_bus")), poll_interval: Number(data.get("poll_interval")) }) });
  await loadState(); currentSetupView = "hardware"; showToast("I²C bağlantı ayarları kaydedildi.");
}

function openI2CDeviceDialog(candidate, item = null) {
  if (!candidate && !item) return;
  const edit = Boolean(item);
  const detected = Boolean(candidate?.online);
  const address = Number(candidate?.address ?? item.address);
  const currentDriver = item?.driver || candidate?.suggested_driver || "pca9685_generic";
  const isPca = candidate?.chip === "PCA9685" || ["waveshare_motor_hat","pca9685_generic"].includes(currentDriver);
  const driverControl = isPca && !edit
    ? `<label class="full"><span>Takılı kart</span><select name="driver"><option value="waveshare_motor_hat" ${currentDriver === "waveshare_motor_hat" ? "selected" : ""}>Waveshare Motor Driver HAT</option><option value="pca9685_generic" ${currentDriver === "pca9685_generic" ? "selected" : ""}>Genel PCA9685 kartı</option></select></label>`
    : `<input name="driver" type="hidden" value="${html(currentDriver)}"><div class="locked-driver full"><span>Sürücü</span><b>${html(driverLabels[currentDriver] || currentDriver)}</b><small>${edit ? "Bağlı kanalları korumak için kilitli" : "Cihaz kimliğinden otomatik seçildi"}</small></div>`;
  openDialog({
    kicker: "Kablolu cihaz", title: edit ? "Cihazı yönet" : "Bulunan cihazı tanımla", submitLabel: "Kaydet",
    body: `<div class="device-fingerprint"><span class="record-code large-code">0x${address.toString(16).toUpperCase().padStart(2,"0")}</span><div><b>${html(candidate?.model || item?.name)}</b><small>${html(candidate?.chip || driverLabels[currentDriver])} · ${detected ? "şu anda bağlı" : "şu anda yanıt vermiyor"}</small></div></div><p class="dialog-note">Adres Raspberry Pi tarafından otomatik okundu. Motor kartında yalnızca elinizdeki kart tipini doğrulayın.</p><div class="dialog-grid"><label class="full"><span>Cihaz adı</span><input name="name" value="${html(item?.name || candidate?.model || "")}" required></label>${driverControl}</div>${edit ? '<button class="danger-button dialog-remove" type="button" data-remove-i2c>Bu cihaz tanımını kaldır</button>' : ""}`,
    onSubmit: async (data) => {
      if (edit && !detected) {
        const assignments = JSON.parse(JSON.stringify(state.hardware?.device_assignments || []));
        const target = assignments.find((entry) => Number(entry.address) === address);
        target.name = data.get("name");
        await api("/api/v1/hardware", { method: "POST", body: JSON.stringify({ device_assignments: assignments }) });
      } else {
        await api("/api/v1/i2c/enroll", { method: "POST", body: JSON.stringify({ candidate_id: candidate.id, name: data.get("name"), driver: data.get("driver") }) });
      }
      dialog.close(); await loadState(); currentSetupView = "hardware"; showToast("Kablolu cihaz tanımı kaydedildi.");
    },
  });
  dialogBody.querySelector("[data-remove-i2c]")?.addEventListener("click", async () => {
    if (!confirm(`${item.name} cihaz tanımı kaldırılsın mı? Sıvı kütüphaneniz silinmez.`)) return;
    try {
      await api("/api/v1/i2c/remove", { method: "POST", body: JSON.stringify({ address }) });
      dialog.close(); await loadState(); currentSetupView = "hardware"; showToast("Kablolu cihaz tanımı kaldırıldı; geçmişi saklandı.");
    } catch (error) { showToast(error.message, true); }
  });
}

function renderDosing(panel) {
  const hardware = state.hardware || {};
  const policy = hardware.dosing_policy || {};
  const fluids = hardware.dosing_fluids || [];
  const hats = (hardware.device_assignments || []).filter((item) => item.driver === "waveshare_motor_hat");
  const fluidOptions = (selected) => `<option value="unassigned" ${selected === "unassigned" ? "selected" : ""}>Atanmamış</option>${fluids.map((fluid) => `<option value="${html(fluid.id)}" ${selected === fluid.id ? "selected" : ""}>${html(fluid.name)} · ${html(fluid.brand || "")}</option>`).join("")}`;
  panel.innerHTML = `<form data-dosing-form><section class="hardware-section"><header class="section-head"><div><h3>Pompa kanalları</h3><small>Sıvıyı seç, kısa test yap ve ölçerek kalibre et</small></div></header>${hats.length ? hats.map((hat, hatIndex) => { const online = Boolean(i2cCandidate(hat.address)?.online); return `<div class="motor-hat ${online ? "" : "offline"}"><header><span><b>${html(hat.name)}</b><small>0x${Number(hat.address).toString(16).toUpperCase()} · ${online ? "kart bağlı" : "kart yanıt vermiyor"}</small></span></header>${(hat.channels || []).map((channel, channelIndex) => { const calibration = channel.calibration || {}; const ready = online && channel.fluid_id !== "unassigned" && calibration.flow_ml_s; const status = !online ? "Kart bağlantısı yok" : channel.fluid_id === "unassigned" ? "Sıvı seçilmedi" : !calibration.flow_ml_s ? "Kalibrasyon gerekli" : `${calibration.flow_ml_s} ml/sn · hazır`; return `<div class="motor-channel"><div class="channel-name"><span>${html(channel.id)}</span><div><b>${html(channel.name)}</b><small class="${ready ? "ready-text" : ""}">${html(status)}</small></div></div><div class="channel-setup"><label><span>Bu pompaya bağlı sıvı</span><select name="channel.${hatIndex}.${channelIndex}.fluid_id">${fluidOptions(channel.fluid_id)}</select></label><div class="channel-actions"><button class="secondary-button compact" type="button" data-pump-test data-address="${hat.address}" data-channel="${html(channel.id)}" ${online ? "" : "disabled"}>Kısa test</button><button class="secondary-button compact" type="button" data-pump-calibrate data-address="${hat.address}" data-channel="${html(channel.id)}" ${online ? "" : "disabled"}>${calibration.flow_ml_s ? "Yeniden kalibre et" : "Kalibre et"}</button></div><details class="advanced-settings channel-settings"><summary>Pompa bilgileri</summary><div class="field-grid simple-grid"><label><span>Pompa markası</span><input name="channel.${hatIndex}.${channelIndex}.pump_brand" value="${html(channel.pump?.brand || "")}"></label><label><span>Pompa modeli</span><input name="channel.${hatIndex}.${channelIndex}.pump_model" value="${html(channel.pump?.model || "")}"></label></div></details></div></div>`; }).join("")}</div>`; }).join("") : '<div class="device-empty"><span><b>Dozaj motor kartı bulunamadı</b><small>Motor kartını Raspberry Pi üzerine bağlayın ve Donanım bölümünde tarayın.</small></span><button class="secondary-button" type="button" data-go-hardware>Donanıma git</button></div>'}</section>
    <details class="advanced-settings"><summary>Dozaj güvenlik sınırları</summary><div class="field-grid">
      ${field("policy","nutrient_interval_minutes","Besin aralığı · dk",policy.nutrient_interval_minutes,{type:"number",min:30})}${field("policy","mixing_wait_minutes","Karışım bekleme · dk",policy.mixing_wait_minutes,{type:"number",min:5})}${field("policy","remeasure_wait_minutes","Yeniden ölçüm · dk",policy.remeasure_wait_minutes,{type:"number",min:1})}
      ${field("policy","ph_interval_minutes","pH aralığı · dk",policy.ph_interval_minutes,{type:"number",min:10})}${field("policy","ph_deadband","pH toleransı",policy.ph_deadband,{type:"number",min:.02,step:".01"})}${field("policy","max_nutrient_dose_ml","En fazla besin · ml",policy.max_nutrient_dose_ml,{type:"number",min:.1,step:".1"})}${field("policy","max_ph_dose_ml","En fazla pH sıvısı · ml",policy.max_ph_dose_ml,{type:"number",min:.1,step:".1"})}
    </div></details>
    <div class="setup-save"><button class="primary-button" type="submit">Dozaj kurulumunu kaydet</button></div></form>`;
  panel.querySelector("[data-go-hardware]")?.addEventListener("click", () => navigateTo("setup", "hardware"));
  panel.querySelector("[data-dosing-form]").addEventListener("submit", saveDosing);
  panel.querySelectorAll("[data-pump-test]").forEach((button) => button.addEventListener("click", () => openPumpTestDialog(Number(button.dataset.address), button.dataset.channel)));
  panel.querySelectorAll("[data-pump-calibrate]").forEach((button) => button.addEventListener("click", () => openPumpCalibrationDialog(Number(button.dataset.address), button.dataset.channel)));
}

async function saveDosing(event) {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const policy = {};
  for (const key of ["nutrient_interval_minutes","mixing_wait_minutes","remeasure_wait_minutes","ph_interval_minutes","ph_deadband","max_nutrient_dose_ml","max_ph_dose_ml"]) policy[key] = Number(data.get(`policy.${key}`));
  const assignments = JSON.parse(JSON.stringify(state.hardware?.device_assignments || []));
  const hats = assignments.filter((item) => item.driver === "waveshare_motor_hat");
  hats.forEach((hat, hatIndex) => (hat.channels || []).forEach((channel, channelIndex) => {
    const prefix = `channel.${hatIndex}.${channelIndex}`;
    channel.fluid_id = data.get(`${prefix}.fluid_id`);
    channel.pump ||= {}; channel.pump.brand = data.get(`${prefix}.pump_brand`); channel.pump.model = data.get(`${prefix}.pump_model`);
  }));
  await api("/api/v1/hardware", { method: "POST", body: JSON.stringify({ dosing_policy: policy, device_assignments: assignments }) });
  await loadState(); showToast("Dozaj eşlemeleri ve emniyet sınırları kaydedildi.");
}

function openPumpTestDialog(address, channel) {
  openDialog({ kicker: "Pompa testi", title: `Kanal ${channel} · kısa test`, submitLabel: "Pompayı çalıştır",
    body: `<p class="dialog-note">Çıkış hortumunu güvenli bir kaba yönlendirin. Pompa en fazla 3 saniye çalışır ve ardından durur.</p><div class="dialog-grid"><label><span>Süre · saniye</span><input name="seconds" type="number" min="1" max="3" step=".5" value="1" required></label><label><span>Hız · %</span><input name="speed" type="number" min="20" max="100" value="60" required></label><label class="safety-confirm full"><input name="confirm" type="checkbox" required><span>Hortum güvenli kapta; pompanın çalışmasına hazırım.</span></label></div>`,
    onSubmit: async (data) => {
      await api("/api/v1/dosing/test", { method: "POST", body: JSON.stringify({ address, channel, seconds: Number(data.get("seconds")), speed: Number(data.get("speed")), confirm: data.get("confirm") === "on" }) });
      dialog.close(); showToast(`Kanal ${channel} testi tamamlandı ve pompa durdu.`);
    },
  });
}

function openPumpCalibrationDialog(address, channel) {
  openDialog({ kicker: "Pompa kalibrasyonu", title: `Kanal ${channel} · ölçüm`, submitLabel: "Ölçümü başlat",
    body: `<p class="dialog-note">Boş bir ölçüm kabı hazırlayın. Pompa seçtiğiniz süre boyunca çalışacak; durduktan sonra kaptaki gerçek hacmi gireceksiniz.</p><div class="dialog-grid"><label><span>Ölçüm süresi · saniye</span><input name="seconds" type="number" min="2" max="30" step="1" value="10" required></label><label><span>Pompa hızı · %</span><input name="speed" type="number" min="20" max="100" value="100" required></label><label class="safety-confirm full"><input name="confirm" type="checkbox" required><span>Hortum ölçüm kabında; pompanın çalışmasına hazırım.</span></label></div>`,
    onSubmit: async (data) => {
      const result = await api("/api/v1/dosing/calibration/start", { method: "POST", body: JSON.stringify({ address, channel, seconds: Number(data.get("seconds")), speed: Number(data.get("speed")), confirm: data.get("confirm") === "on" }) });
      dialog.close(); openCalibrationVolumeDialog(result.result);
    },
  });
}

function openCalibrationVolumeDialog(run) {
  openDialog({ kicker: "Pompa kalibrasyonu", title: "Ölçülen hacim", submitLabel: "Kalibrasyonu kaydet",
    body: `<p class="dialog-note">Pompa ${html(run.seconds)} saniye çalıştı ve durdu. Ölçüm kabında gördüğünüz gerçek hacmi girin.</p><div class="dialog-grid"><label class="full"><span>Ölçülen hacim · ml</span><input name="volume_ml" type="number" min=".01" max="500" step=".01" autofocus required></label></div>`,
    onSubmit: async (data) => {
      await api("/api/v1/dosing/calibration/complete", { method: "POST", body: JSON.stringify({ token: run.token, volume_ml: Number(data.get("volume_ml")) }) });
      dialog.close(); await loadState(); showToast(`Kanal ${run.channel} kalibrasyonu ölçümden kaydedildi.`);
    },
  });
}

function openDialog({ kicker, title, body, submitLabel, onSubmit, secondaryLabel = "Vazgeç" }) {
  dialogKicker.textContent = kicker;
  dialogTitle.textContent = title;
  dialogBody.innerHTML = body;
  dialogActions.innerHTML = `<button class="secondary-button" type="button" data-dialog-cancel>${html(secondaryLabel)}</button><button class="primary-button" type="submit">${html(submitLabel)}</button>`;
  dialogActions.querySelector("[data-dialog-cancel]").addEventListener("click", () => dialog.close());
  dialogForm.onsubmit = async (event) => {
    event.preventDefault();
    const submit = dialogActions.querySelector(".primary-button");
    submit.disabled = true;
    try { await onSubmit(new FormData(dialogForm)); } catch (error) { showToast(error.message, true); submit.disabled = false; }
  };
  dialog.showModal();
}

function plantOptions() {
  const catalog = state.plant_catalog || {};
  return (catalog.order || []).map((plantId) => catalog.records?.[plantId]).filter(Boolean);
}

function openStartDialog() {
  const plants = plantOptions();
  const today = localDate();
  const system = state.system_profile?.system || {};
  openDialog({
    kicker: "Yeni yetiştirme",
    title: "Yetiştirmeyi başlat",
    submitLabel: "Yetiştirmeyi başlat",
    body: `<p class="start-lead">Önce bitkini ve başlangıç aşamasını seç. Diğer bilgiler hazır gelir.</p>
      <div class="dialog-grid start-core">
        <label><span>Bitki türü</span><select name="plant_profile_id" data-plant-select>${plants.map((plant) => `<option value="${html(plant.id)}">${html(plant.name)}</option>`).join("")}<option value="">Diğer / kendi bitkim</option></select></label>
        <label data-custom-plant hidden><span>Bitkinin adı</span><input name="plant_species" maxlength="96" placeholder="Tür veya yaygın adı"></label>
        <label><span>Bitki sayısı</span><input name="plant_count" type="number" min="1" value="1" required></label>
        <label data-cannabis-only hidden><span>Büyüme tipi</span><select name="growth_type" data-growth-type><option value="">Seçin</option><option value="photoperiod">Photoperiod</option><option value="autoflower">Autoflower</option></select></label>
        <label data-cannabis-only hidden class="full"><span>Çeşit / strain</span><input name="cultivar_choice" data-cultivar-input list="start-cultivar-options" autocomplete="off" placeholder="Yazarak ara"><datalist id="start-cultivar-options" data-cultivar-list></datalist></label>
        <label data-non-cannabis-only><span>Çeşit / cultivar</span><input name="cultivar" placeholder="İsteğe bağlı"></label>
        <label><span>Kaynak</span><input name="source" placeholder="Üretici, mağaza veya parti"></label>
        <label><span>Başlangıç tarihi</span><input name="start_date" type="date" max="${today}" value="${today}" required></label>
        <label><span>İlk aşama</span><select name="initial_stage" data-initial-stage></select></label>
        <div class="profile-preview full" data-profile-preview></div>
        <label><span>Yetiştirme yöntemi</span><select name="growing_method" data-start-method>${optionRows(cultivationMethods, system.growing_method || "RDWC")}</select></label>
        <label><span>Yetiştirme medyası</span><select name="growing_medium" data-start-medium>${optionRows(growingMedia, system.growing_medium || "")}</select></label>
        <section class="start-program-picker full"><header><span>Besin programı</span><small>Ortamına uymayan seriler otomatik elenir.</small></header><div class="dialog-grid">
          <label><span>Marka</span><select name="nutrient_brand" data-start-program-brand></select></label>
          <label><span>Program / seri</span><select name="nutrient_program_id" data-start-program></select></label>
          <label class="full"><span>Ürün kapsamı</span><select name="nutrient_program_scope" data-start-program-scope><option value="core">Temel ürün seti</option><option value="complete">Geniş set · yardımcı ürünlerle</option></select></label>
        </div><div class="start-program-preview" data-start-program-preview></div></section>
      </div>
      <details class="advanced-settings start-options"><summary>Diğer bilgiler</summary><div class="dialog-grid">
        <label class="full"><span>Yetiştirme adı</span><input name="name" placeholder="Boş bırakırsan otomatik adlandırılır"></label>
        <label class="full"><span>Not</span><textarea name="notes" placeholder="İsteğe bağlı"></textarea></label>
      </div></details>`,
    onSubmit: submitStartGrow,
  });
  const plantSelect = dialogBody.querySelector("[data-plant-select]");
  const growthSelect = dialogBody.querySelector("[data-growth-type]");
  const stageSelect = dialogBody.querySelector("[data-initial-stage]");
  plantSelect.addEventListener("change", updateStartPlantFields);
  growthSelect.addEventListener("change", updateCultivarOptions);
  stageSelect.addEventListener("change", updateStartProfilePreview);
  dialogBody.querySelector("[data-start-method]").addEventListener("change", updateStartNutrientPrograms);
  dialogBody.querySelector("[data-start-medium]").addEventListener("change", updateStartNutrientPrograms);
  dialogBody.querySelector("[data-start-program-brand]").addEventListener("change", updateStartNutrientPrograms);
  dialogBody.querySelector("[data-start-program]").addEventListener("change", updateStartProgramPreview);
  dialogBody.querySelector("[data-start-program-scope]").addEventListener("change", updateStartProgramPreview);
  updateStartPlantFields();
}

function selectedPlant() {
  const plantId = dialogBody.querySelector("[data-plant-select]")?.value;
  return state.plant_catalog?.records?.[plantId];
}

function updateStartPlantFields() {
  const plant = selectedPlant();
  const cannabis = plant?.category === "cannabis";
  const custom = !plant;
  dialogBody.querySelectorAll("[data-cannabis-only]").forEach((element) => {
    element.hidden = !cannabis;
    element.querySelectorAll("input,select").forEach((input) => { input.disabled = !cannabis; });
  });
  dialogBody.querySelectorAll("[data-non-cannabis-only]").forEach((element) => {
    element.hidden = cannabis;
    element.querySelectorAll("input,select").forEach((input) => { input.disabled = cannabis; });
  });
  dialogBody.querySelector("[data-growth-type]").required = cannabis;
  dialogBody.querySelectorAll("[data-custom-plant]").forEach((element) => {
    element.hidden = !custom;
    element.querySelector("input").required = custom;
  });
  const stageSelect = dialogBody.querySelector("[data-initial-stage]");
  const stages = plant?.profile?.stages || {};
  const options = stageOrder.filter((stage) => stages[stage]?.enabled).map((stage) => `<option value="${html(stage)}">${html(state.stage_labels[stage] || stage)}</option>`).join("");
  stageSelect.innerHTML = options || '<option value="">Örnek profile göre otomatik</option>';
  updateCultivarOptions();
  updateStartProfilePreview();
  updateStartNutrientPrograms();
}

function updateStartProfilePreview() {
  const plant = selectedPlant();
  const stage = dialogBody.querySelector("[data-initial-stage]")?.value;
  const target = plant?.profile?.stages?.[stage];
  const preview = dialogBody.querySelector("[data-profile-preview]");
  if (!preview) return;
  if (!target) {
    preview.innerHTML = `<span><b>Özel bitki şablonu</b><small>Başlangıç hedefleri daha sonra Bitki Kütüphanesi bölümünden düzenlenebilecek.</small></span>`;
    return;
  }
  preview.innerHTML = `<span><b>${html(state.stage_labels[stage] || stage)} · ${html(target.planned_days)} gün</b><small>Bu bitki için başlangıç hedefi; istediğin zaman değiştirebilirsin.</small></span>
    <dl><div><dt>Işık</dt><dd>${html(target.photoperiod)} sa · %${html(target.light_intensity)}</dd></div><div><dt>Ortam</dt><dd>${html(target.day_temperature)} °C · %${html(target.humidity)}</dd></div><div><dt>Kök bölgesi</dt><dd>pH ${html(target.ph_min)}–${html(target.ph_max)} · EC ${html(target.ec_min)}–${html(target.ec_max)}</dd></div></dl>`;
}

function startNutrientEnvironment() {
  const method = String(dialogBody.querySelector("[data-start-method]")?.value || "").toLocaleLowerCase("tr");
  const medium = String(dialogBody.querySelector("[data-start-medium]")?.value || "").toLocaleLowerCase("tr");
  if (method.includes("coco") || medium.includes("coco")) return "coco";
  if (method.includes("soil") || method.includes("toprak") || medium.includes("soil") || medium.includes("toprak")) return "soil";
  return "hydro";
}

function startProgramMatches(program) {
  const environment = startNutrientEnvironment();
  const supported = program?.supported_environments || [];
  return supported.includes("universal") || supported.includes(environment);
}

function updateStartNutrientPrograms() {
  const catalog = state.nutrient_catalog || {};
  const brandSelect = dialogBody.querySelector("[data-start-program-brand]");
  const programSelect = dialogBody.querySelector("[data-start-program]");
  if (!brandSelect || !programSelect) return;
  const programs = (catalog.program_order || []).map((programId) => catalog.programs?.[programId]).filter((program) => program?.cycle_coverage === "complete" && startProgramMatches(program));
  const previousBrand = brandSelect.value;
  const brandIds = [...new Set(programs.map((program) => program.brand_id))];
  brandSelect.innerHTML = `<option value="">Şimdilik program seçme</option>${brandIds.map((brandId) => `<option value="${html(brandId)}" ${previousBrand === brandId ? "selected" : ""}>${html(catalog.brands?.[brandId]?.name || brandId)}</option>`).join("")}`;
  const brandId = brandSelect.value;
  const previousProgram = programSelect.value;
  const matching = programs.filter((program) => program.brand_id === brandId);
  programSelect.innerHTML = brandId ? matching.map((program) => `<option value="${html(program.id)}" ${program.id === previousProgram ? "selected" : ""}>${html(program.name)}</option>`).join("") : '<option value="">Önce marka seçin</option>';
  programSelect.disabled = !brandId;
  updateStartProgramPreview();
}

function updateStartProgramPreview() {
  const programId = dialogBody.querySelector("[data-start-program]")?.value;
  const scope = dialogBody.querySelector("[data-start-program-scope]")?.value || "core";
  const program = state.nutrient_catalog?.programs?.[programId];
  const preview = dialogBody.querySelector("[data-start-program-preview]");
  if (!preview) return;
  if (!program) {
    preview.innerHTML = '<span><b>Besin programı seçilmedi</b><small>Yetiştirmeyi yalnızca takip için başlatabilir, programı daha sonra günlüğe ekleyebilirsin.</small></span>';
    return;
  }
  const products = nutrientProgramProducts(program, scope);
  preview.innerHTML = `<div><span class="record-type">${html(program.brand)}</span><b>${html(program.name)}</b><small>${html(products.map((item) => item.name).join(" · "))}</small></div><strong>${products.length}<small>ürün</small></strong><p>Seçim yetiştirme kaydına değişmez kopya olarak yazılır. Doz miktarı otomatik uygulanmaz.</p>`;
}

function updateCultivarOptions() {
  const plant = selectedPlant();
  const growth = dialogBody.querySelector("[data-growth-type]")?.value || "";
  const cultivarList = dialogBody.querySelector("[data-cultivar-list]");
  const cultivarInput = dialogBody.querySelector("[data-cultivar-input]");
  if (!cultivarList || !cultivarInput) return;
  const breeders = state.plant_catalog?.breeders || {};
  const cultivars = (plant?.cultivars || []).filter((item) => item.active !== false && (!growth || item.growth_type === growth));
  cultivarInput.value = "";
  cultivarList.innerHTML = cultivars.map((item) => `<option value="${html(item.name)}${breeders[item.breeder_id] ? ` · ${html(breeders[item.breeder_id].name)}` : ""}"></option>`).join("");
}

async function submitStartGrow(formData) {
  const plant = selectedPlant();
  const cultivarChoice = String(formData.get("cultivar_choice") || "").trim();
  const breeders = state.plant_catalog?.breeders || {};
  const cultivar = (plant?.cultivars || []).find((item) => `${item.name}${breeders[item.breeder_id] ? ` · ${breeders[item.breeder_id].name}` : ""}` === cultivarChoice);
  const payload = Object.fromEntries(formData.entries());
  delete payload.cultivar_choice;
  delete payload.nutrient_brand;
  payload.nutrient_ids = [];
  payload.plant_count = Number(payload.plant_count || 1);
  payload.cultivation_id = id();
  payload.name ||= `${plant?.name || payload.plant_species || "Yetiştirme"} · ${payload.start_date}`;
  if (cultivar) {
    payload.cultivar_id = cultivar.id;
    payload.growth_type = cultivar.growth_type;
    payload.breeder_id = cultivar.breeder_id;
  } else if (cultivarChoice) {
    payload.cultivar = cultivarChoice;
  }
  await api("/api/v1/cultivations/start", { method: "POST", body: JSON.stringify(payload) });
  dialog.close();
  await loadState();
  showToast("Yetiştirme ve ilk aşama kalıcı günlüğe eklendi.");
}

function openJournalDialog(type = "user_note") {
  const amountTypes = { water_added: "L", water_changed: "L", nutrient_dose: "ml", ph_dose: "ml", reservoir_volume: "L" };
  const types = [["user_note","Not"],["water_added","Su ekleme"],["water_changed","Su değişimi"],["nutrient_dose","Besin dozu"],["ph_dose","pH dozu"],["reservoir_volume","Rezervuar hacmi"],["calibration","Kalibrasyon"],["maintenance","Bakım"]];
  openDialog({
    kicker: "Günlük",
    title: "Bugüne kayıt ekle",
    submitLabel: "Günlüğe ekle",
    body: `<p class="dialog-note">Kaydedilen olay değiştirilmez. Yanlış bir bilgi olursa açıklayan yeni bir not ekleyin.</p><div class="dialog-grid">
      <label><span>Kayıt türü</span><select name="type" data-event-type>${types.map(([value,label]) => `<option value="${value}" ${value === type ? "selected" : ""}>${label}</option>`).join("")}</select></label>
      <label><span>Tarih</span><input name="local_date" type="date" value="${localDate()}" max="${localDate()}" required></label>
      <label data-amount-field hidden><span>Miktar · <i data-event-unit></i></span><input name="amount" type="number" min="0.01" step="0.01"></label>
      <label class="full"><span>Açıklama</span><textarea name="note" placeholder="Ne yaptınız veya ne gözlemlediniz?" required></textarea></label>
    </div>`,
    onSubmit: submitJournalEvent,
  });
  const typeSelect = dialogBody.querySelector("[data-event-type]");
  const updateAmount = () => {
    const unit = amountTypes[typeSelect.value];
    const field = dialogBody.querySelector("[data-amount-field]");
    field.hidden = !unit;
    field.querySelector("input").required = Boolean(unit);
    dialogBody.querySelector("[data-event-unit]").textContent = unit || "";
  };
  typeSelect.addEventListener("change", updateAmount);
  updateAmount();
}

async function submitJournalEvent(formData) {
  const type = String(formData.get("type"));
  const amount = formData.get("amount");
  const units = { water_added: "L", water_changed: "L", nutrient_dose: "ml", ph_dose: "ml", reservoir_volume: "L" };
  const values = units[type] ? { amount: Number(amount), unit: units[type] } : {};
  await api("/api/v1/journal/events", { method: "POST", body: JSON.stringify({
    type, local_date: formData.get("local_date"), note: formData.get("note"), values, event_id: id(),
  }) });
  dialog.close();
  await loadState();
  showToast("Kayıt kalıcı günlüğe eklendi.");
}

async function changeStage(stage) {
  if (stage === state.active_stage) return;
  const label = state.stage_labels[stage] || stage;
  if (!confirm(`${label} aşamasına geçilsin mi? Bu geçiş günlüğe eklenecek.`)) return;
  try {
    await api("/api/v1/cultivations/stage", { method: "POST", body: JSON.stringify({ stage, local_date: localDate() }) });
    await loadState();
    showToast(`${label} aşamasına geçildi.`);
  } catch (error) { showToast(error.message, true); }
}

async function finishGrow() {
  if (!confirm("Aktif yetiştirme tamamlanıp arşive alınsın mı? Günlük kayıtları silinmeyecek.")) return;
  try {
    await api("/api/v1/cultivations/finish", { method: "POST", body: JSON.stringify({ local_date: localDate() }) });
    await loadState();
    showToast("Yetiştirme arşive alındı; günlük korundu.");
  } catch (error) { showToast(error.message, true); }
}

async function saveSetup(event) {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const profile = JSON.parse(JSON.stringify(state.system_profile || {}));
  for (const [path, value] of data.entries()) {
    const [section, key] = path.split(".");
    profile[section] ||= {};
    const input = event.currentTarget.elements[path];
    profile[section][key] = input.type === "number" ? Number(value) : value;
  }
  try {
    await api("/api/v1/system-profile", { method: "POST", body: JSON.stringify(profile) });
    await loadState();
    showToast("Yetiştirme kurulumu kaydedildi.");
  } catch (error) { showToast(error.message, true); }
}

dialog.addEventListener("click", (event) => {
  if (event.target === dialog) dialog.close();
});
document.querySelector("[data-dialog-close]").addEventListener("click", () => dialog.close());

if (token) loadState().catch(() => showAuth("Erişim anahtarını yeniden girin."));
else showAuth();

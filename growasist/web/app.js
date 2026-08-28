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
  setup: ["Sistem", "Alan ve ışık"],
};
const setupViewIds = new Set(["overview", "plants", "nutrients", "hardware", "dosing"]);

let token = sessionStorage.getItem(TOKEN_KEY) || "";
let state = null;
let currentView = "today";
let currentSetupView = "overview";
let selectedPlantId = "";
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
  currentView = view === "journal" || view === "setup" ? view : "today";
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
    ["nutrients", "Besinler", `${state.hardware?.dosing_fluids?.length || 0} sıvı`],
    ["hardware", "Donanım", `${state.hardware?.device_assignments?.length || 0} kablolu cihaz`],
    ["dosing", "Dozaj", "Pompa ve kalibrasyon"],
  ];
  const descriptions = {
    overview: ["Sistem", "Yöntemini, yetiştirme medyanı ve ışığını tanımla."],
    plants: ["Kütüphane", "Her bitkinin aşamalarını ve o aşamada kullandığın besinleri düzenle."],
    nutrients: ["Kütüphane", "Elindeki besin ve sıvı ürünlerini kaydet."],
    hardware: ["Sistem", "Kablolu ve ağdaki cihazlarını tanımla."],
    dosing: ["Sistem", "Pompa bağlantılarını ve kalibrasyonlarını yönet."],
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
  else if (currentSetupView === "dosing") renderDosing(panel);
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

function stageNutrientFields(stage, target, fluids) {
  const selected = target.nutrient_ids || [];
  if (!fluids.length) return '<p class="stage-nutrient-empty">Besinler bölümüne ürün eklediğinizde burada seçebilirsiniz.</p>';
  return `<fieldset class="fluid-checks plant-fluid-list"><legend>Bu bitkinin bu aşamada kullandığı ürünler</legend>${fluids.map((fluid) => `<label><input type="checkbox" name="stage.${stage}.nutrient_ids" value="${html(fluid.id)}" ${selected.includes(fluid.id) ? "checked" : ""}> ${html(fluid.name)} <small>${html(fluid.brand || "")}</small></label>`).join("")}</fieldset>`;
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
  const nutrientFluids = (state.hardware?.dosing_fluids || []).filter((item) => !item.required && !["ph","ph_up","ph_down"].includes(item.category));
  panel.innerHTML = `<div class="library-layout">
    <aside class="library-index"><div class="library-tools"><input type="search" data-plant-search placeholder="Bitki ara"><button class="secondary-button compact" type="button" data-add-plant>+ Bitki</button></div>
      <div data-plant-list>${plants.map((item) => `<button type="button" class="library-item ${item.id === plant.id ? "active" : ""}" data-plant-id="${html(item.id)}" data-search="${html(`${item.name} ${item.english_name} ${item.botanical_name}`.toLowerCase())}"><span><b>${html(item.name)}</b><small>${html(item.botanical_name || item.english_name)}</small></span><em>${html(item.cultivars?.length || item.cultivar_examples?.length || 0)}</em></button>`).join("")}</div>
    </aside>
    <form class="library-detail" data-plant-form>
      <div class="record-heading"><div><span class="record-type">${plant.built_in ? "Başlangıç profili" : "Kendi bitkin"}</span><h3>${html(plant.name)}</h3><p>${html(plant.notes || "Bu bitkinin aşamalarını ve kullandığın ürünleri düzenle.")}</p></div><button class="primary-button" type="submit">Değişiklikleri kaydet</button></div>
      <details class="advanced-settings plant-identity"><summary>Bitki bilgileri</summary><div class="field-grid">
        ${field("plant","name","Görünen ad",plant.name)}${field("plant","english_name","İngilizce ad",plant.english_name)}${field("plant","botanical_name","Botanik ad",plant.botanical_name)}
        ${field("plant","category","Kategori",plant.category)}<label class="wide"><span>Not</span><textarea name="plant.notes">${html(plant.notes)}</textarea></label>
      </div></details>
      <section class="target-ledger"><header><div><h3>Aşamalar ve besinler</h3><p>Her bitkinin her aşaması ayrı tutulur.</p></div></header>
        ${stageOrder.map((stage) => { const target = stages[stage] || {}; const nutrientCount = (target.nutrient_ids || []).length; return `<details class="target-row"><summary><span><b>${html(state.stage_labels[stage] || stage)}</b><small>${target.enabled ? `${html(target.planned_days)} gün · ${html(target.photoperiod)} saat${nutrientCount ? ` · ${nutrientCount} ürün` : ""}` : "Kullanılmıyor"}</small></span><label class="inline-check"><input name="stage.${stage}.enabled" type="checkbox" ${target.enabled ? "checked" : ""}> Kullan</label></summary><div class="field-grid compact-grid">
          ${stageTargetFields(stage, target)}
        </div>${stageNutrientFields(stage, target, nutrientFluids)}</details>`; }).join("")}
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
    target.nutrient_ids = data.getAll(`stage.${stage}.nutrient_ids`);
  }
  await api("/api/v1/plants", { method: "POST", body: JSON.stringify({ plant_id: selectedPlantId, values: plant }) });
  await loadState(); currentSetupView = "plants"; showToast("Bitki profili kaydedildi.");
}

function fluidLabel(fluid) {
  const categories = { ph: "pH düzenleyici", base: "Ana besin", supplement: "Takviye", booster: "Güçlendirici", other: "Diğer" };
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
  const fluids = state.hardware?.dosing_fluids || [];
  panel.innerHTML = `<div class="page-actions"><div><strong>${fluids.length} ürün</strong><p>Burada ürünlerini kaydet; bitkiye ve aşamaya Bitki Kütüphanesi'nden bağla.</p></div><button class="primary-button" type="button" data-add-fluid>Ürün ekle</button></div><div class="record-ledger">${fluids.map((fluid) => `<button type="button" class="record-row" data-fluid-id="${html(fluid.id)}"><span class="record-code">${html(fluid.required ? "pH" : "N")}</span><span><b>${html(fluid.name)}</b><small>${html(fluid.brand || "Belirtilmedi")} · ${html(fluid.line || fluid.part || "Seri belirtilmedi")}</small></span><span>${html(fluidLabel(fluid))}</span><small>${html(fluidPhaseLabel(fluid.phase))} · ${html(fluidMediumLabel(fluid.medium))}</small><em>Düzenle</em></button>`).join("")}</div>`;
  panel.querySelector("[data-add-fluid]").addEventListener("click", () => openFluidDialog());
  panel.querySelectorAll("[data-fluid-id]").forEach((button) => button.addEventListener("click", () => openFluidDialog(fluids.find((item) => item.id === button.dataset.fluidId))));
}

function openFluidDialog(fluid = null) {
  const edit = Boolean(fluid);
  const phaseOptions = [["all","Tüm aşamalar"], ...stageOrder.map((stage) => [stage, state.stage_labels[stage] || stage])];
  const mediumOptions = [["all","Tüm medyalar"],["hydro/coco","Hidroponik / Coco"],["hydro","Hidroponik"],["coco","Coco"],["soil","Toprak"]];
  openDialog({ kicker: "Besinler", title: edit ? "Ürünü düzenle" : "Ürün ekle", submitLabel: "Kaydet",
    body: `<div class="dialog-grid"><label><span>Ürün adı</span><input name="name" value="${html(fluid?.name || "")}" required></label><label><span>Marka</span><input name="brand" value="${html(fluid?.brand || "")}"></label><label><span>Kategori</span><select name="category" ${fluid?.required ? "disabled" : ""}>${[["base","Ana besin"],["supplement","Takviye"],["booster","Güçlendirici"],["other","Diğer"],["ph","pH düzenleyici"]].map(([id,label]) => `<option value="${id}" ${(fluid?.category || "other") === id ? "selected" : ""}>${label}</option>`).join("")}</select></label></div><details class="advanced-settings dialog-advanced"><summary>Ürün detayları</summary><div class="dialog-grid"><label><span>Seri</span><input name="line" value="${html(fluid?.line || "")}"></label><label><span>Parça</span><input name="part" value="${html(fluid?.part || "")}"></label><label><span>NPK</span><input name="npk" value="${html(fluid?.npk || "")}"></label><label><span>Üreticinin önerdiği aşama</span><select name="phase">${optionRows(phaseOptions, fluid?.phase || "all")}</select></label><label><span>Üreticinin önerdiği medya</span><select name="medium">${optionRows(mediumOptions, fluid?.medium || "all")}</select></label></div></details>`,
    onSubmit: async (data) => {
      const fluids = JSON.parse(JSON.stringify(state.hardware?.dosing_fluids || []));
      const target = edit ? fluids.find((item) => item.id === fluid.id) : { id: `fluid_${id().slice(0,16)}`, required: false };
      for (const key of ["name","brand","category","line","part","npk","phase","medium"]) if (data.has(key)) target[key] = data.get(key);
      if (!edit) fluids.push(target);
      await api("/api/v1/hardware", { method: "POST", body: JSON.stringify({ dosing_fluids: fluids }) });
      dialog.close(); await loadState(); currentSetupView = "nutrients"; showToast("Besin kataloğu kaydedildi.");
    },
  });
}

const driverLabels = { atlas_do: "Atlas EZO DO", atlas_ph: "Atlas EZO pH", atlas_ec: "Atlas EZO EC", atlas_rtd: "Atlas EZO RTD", waveshare_motor_hat: "Waveshare Motor HAT", pca9685_generic: "PCA9685" };

function renderHardware(panel) {
  const hardware = state.hardware || {};
  const assignments = hardware.device_assignments || [];
  const networkDevices = Object.values(state.device_registry?.devices || {});
  const candidates = Object.values(state.device_registry?.candidates || {}).sort((left, right) => Number(right.online) - Number(left.online) || Number(right.supported) - Number(left.supported) || String(left.vendor).localeCompare(String(right.vendor)) || String(left.host).localeCompare(String(right.host), undefined, { numeric: true }));
  const knownCandidates = candidates.filter((item) => item.vendor !== "Unknown");
  const otherCandidates = candidates.filter((item) => item.vendor === "Unknown");
  const lastScan = state.device_registry?.last_scan;
  panel.innerHTML = `<section class="hardware-section"><header class="section-head"><div><h3>Kablolu cihazlar</h3><small>${assignments.length} cihaz</small></div><button class="primary-button compact" type="button" data-add-hardware>Cihaz ekle</button></header><div class="record-ledger">${assignments.length ? assignments.map((item) => `<button type="button" class="record-row hardware-row" data-hardware-address="${item.address}"><span class="record-code">0x${Number(item.address).toString(16).toUpperCase().padStart(2,"0")}</span><span><b>${html(item.name)}</b><small>${html(driverLabels[item.driver] || item.driver)}</small></span><span>${item.channels ? `${item.channels.length} motor kanalı` : "Sensör"}</span><em>Düzenle</em></button>`).join("") : '<p class="empty-list">Henüz kablolu cihaz yok.</p>'}</div><details class="advanced-settings"><summary>Bağlantı ayarları</summary><form class="hardware-connection-form" data-hardware-base><label><span>Bağlantı kanalı</span><input name="i2c_bus" type="number" min="0" max="255" value="${html(hardware.i2c_bus ?? 1)}"></label><label><span>Okuma aralığı · saniye</span><input name="poll_interval" type="number" min="10" max="300" value="${html(hardware.poll_interval ?? 30)}"></label><button class="secondary-button" type="submit">Kaydet</button></form></details></section>
    <section class="hardware-section network-discovery"><header class="section-head"><div><h3>Ağdaki cihazlar</h3><small>Shelly, Tapo ve diğer desteklenen cihazlar</small></div><button class="primary-button compact" type="button" data-network-scan>Ağı tara</button></header>
      <div class="scan-summary"><span><b>${lastScan ? `${html(lastScan.candidate_count)} cihaz bulundu` : "Henüz tarama yapılmadı"}</b><small>${lastScan ? html(String(lastScan.finished_at || "").replace("T", " ").slice(0, 16)) : "Bulunan cihazları sen onaylamadan eklemeyiz."}</small></span>${lastScan?.warnings?.length ? `<em>${html(lastScan.warnings.join(" · "))}</em>` : ""}</div>
      <div class="network-columns"><div><div class="subsection-label"><b>Tanınan cihazlar</b><small>${knownCandidates.length}</small></div><div class="record-ledger">${knownCandidates.length ? knownCandidates.map(networkCandidateRow).join("") : '<p class="empty-list">Shelly, Tapo veya Tuya adayı bulunamadı.</p>'}</div>${otherCandidates.length ? `<details class="other-devices"><summary>Diğer ağ cihazları <span>${otherCandidates.length}</span></summary><div class="record-ledger">${otherCandidates.map(networkCandidateRow).join("")}</div></details>` : ""}</div>
      <div><div class="subsection-label"><b>Tanımlı cihazlar</b><small>${networkDevices.length}</small></div><div class="record-ledger">${networkDevices.length ? networkDevices.map(networkDeviceRow).join("") : '<p class="empty-list">Henüz onaylanmış ağ cihazı yok.</p>'}</div></div></div>
    </section>`;
  panel.querySelector("[data-hardware-base]").addEventListener("submit", saveHardwareBase);
  panel.querySelector("[data-add-hardware]").addEventListener("click", () => openHardwareDialog());
  panel.querySelectorAll("[data-hardware-address]").forEach((button) => button.addEventListener("click", () => openHardwareDialog(assignments.find((item) => item.address === Number(button.dataset.hardwareAddress)))));
  panel.querySelector("[data-network-scan]").addEventListener("click", scanNetwork);
  panel.querySelectorAll("[data-network-candidate]").forEach((button) => button.addEventListener("click", () => openNetworkDeviceDialog(candidates.find((item) => item.id === button.dataset.networkCandidate))));
  panel.querySelectorAll("[data-network-device]").forEach((button) => button.addEventListener("click", () => openNetworkDeviceDialog(networkDevices.find((item) => item.id === button.dataset.networkDevice))));
}

function networkCandidateRow(item) {
  const support = !item.online ? "Son taramada görülmedi" : item.supported ? "Kimliği okundu" : item.vendor === "Unknown" ? "Türü belirlenemedi" : "Aday cihaz";
  return `<button type="button" class="network-row ${item.online ? "" : "offline"}" data-network-candidate="${html(item.id)}"><span class="vendor-mark">${html((item.vendor || "?").slice(0,2).toUpperCase())}</span><span><b>${html(item.name || item.model || item.host)}</b><small>${html(item.vendor)} · ${html(item.model || item.protocol)}</small></span><span><b>${html(item.host)}</b><small>${html(item.mac || "MAC bilinmiyor")}</small></span><span class="support-state ${item.online && item.supported ? "supported" : "limited"}">${html(support)}</span><em>Tanımla</em></button>`;
}

function networkDeviceRow(item) {
  const roles = { environment_sensor: "Ortam sensörü", co2_sensor: "CO₂ sensörü", light_dimmer: "Işık dimmeri", light_power: "Işık gücü", outlet_bank: "Priz grubu", humidifier: "Nemlendirici", unassigned: "Rol atanmadı" };
  return `<button type="button" class="network-row enrolled" data-network-device="${html(item.id)}"><span class="vendor-mark">${html((item.vendor || "?").slice(0,2).toUpperCase())}</span><span><b>${html(item.name || item.model || item.host)}</b><small>${html(item.vendor)} · ${html(item.model || item.protocol)}</small></span><span><b>${html(item.host)}</b><small>${html(item.mac || "MAC bilinmiyor")}</small></span><span class="support-state ${item.online ? "supported" : "limited"}">${html(roles[item.role] || item.role || "Rol atanmadı")}</span><em>${item.online ? "Düzenle" : "Son taramada yok · Düzenle"}</em></button>`;
}

async function scanNetwork(event) {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = "Ağ taranıyor…";
  try {
    const payload = await api("/api/v1/network/discover", { method: "POST", body: JSON.stringify({ timeout: 3 }) });
    await loadState(); currentSetupView = "hardware";
    const count = Number(payload.result?.last_scan?.candidate_count || 0);
    showToast(`${count} ağ cihazı adayı bulundu.`);
  } catch (error) {
    button.disabled = false; button.textContent = "Ağı tara"; showToast(error.message, true);
  }
}

function openNetworkDeviceDialog(item) {
  if (!item) return;
  const edit = item.status === "enrolled";
  const roles = [["unassigned","Şimdilik rol verme"],["environment_sensor","Ortam sıcaklık / nem sensörü"],["co2_sensor","CO₂ sensörü"],["light_dimmer","Işık dimmeri"],["light_power","Işık aç / kapat"],["outlet_bank","Priz grubu"],["humidifier","Nemlendirici"]];
  openDialog({
    kicker: "Ağ cihazı", title: edit ? "Cihazı düzenle" : "Cihazı tanımla", submitLabel: edit ? "Kaydet" : "Cihaz listesine ekle",
    body: `<div class="device-fingerprint"><span class="vendor-mark large-mark">${html((item.vendor || "?").slice(0,2).toUpperCase())}</span><div><b>${html(item.name || item.model || item.host)}</b><small>${html(item.vendor)} · ${html(item.model || "Model bilinmiyor")} · ${html(item.host)}</small></div></div><div class="dialog-grid"><label class="full"><span>Cihaz adı</span><input name="name" value="${html(item.name || item.model || item.host)}" required></label><label class="full"><span>Ne için kullanılacak?</span><select name="role">${roles.map(([role,label]) => `<option value="${role}" ${(item.role || item.suggested_role || "unassigned") === role ? "selected" : ""}>${label}</option>`).join("")}</select></label></div><details class="advanced-settings dialog-advanced"><summary>Cihaz bilgileri</summary><dl class="fingerprint-grid"><div><dt>Protokol</dt><dd>${html(item.protocol)}</dd></div><div><dt>MAC</dt><dd>${html(item.mac || "Bilinmiyor")}</dd></div><div><dt>Keşif sonucu</dt><dd>${html(item.supported ? "Kimliği okundu" : "Aday olarak bulundu")}</dd></div><div><dt>Giriş bilgisi</dt><dd>${html(item.requires_auth ? "Bağlantı sırasında gerekli" : "Gerekli görünmüyor")}</dd></div></dl></details>`,
    onSubmit: async (data) => {
      await api("/api/v1/network/enroll", { method: "POST", body: JSON.stringify({ candidate_id: item.id, name: data.get("name"), role: data.get("role") }) });
      dialog.close(); await loadState(); currentSetupView = "hardware"; showToast(edit ? "Ağ cihazı tanımı güncellendi." : "Ağ cihazı tanımlı cihazlara eklendi.");
    },
  });
}

async function saveHardwareBase(event) {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  await api("/api/v1/hardware", { method: "POST", body: JSON.stringify({ i2c_bus: Number(data.get("i2c_bus")), poll_interval: Number(data.get("poll_interval")) }) });
  await loadState(); currentSetupView = "hardware"; showToast("I²C bağlantı ayarları kaydedildi.");
}

function openHardwareDialog(item = null) {
  const edit = Boolean(item);
  openDialog({ kicker: "Kablolu cihaz", title: edit ? "Cihazı düzenle" : "Cihaz ekle", submitLabel: "Kaydet",
    body: `<p class="dialog-note">Adres ve sürücü fiziksel cihazı tanımlar. Motor kanallarına sıvı ataması Dozaj bölümünde yapılır.</p><div class="dialog-grid"><label><span>Görünen ad</span><input name="name" value="${html(item?.name || "")}" required></label><label><span>I²C adresi</span><input name="address" value="${html(item ? `0x${Number(item.address).toString(16).toUpperCase()}` : "0x63")}" required></label><label class="full"><span>Sürücü</span><select name="driver">${Object.entries(driverLabels).map(([driver,label]) => `<option value="${driver}" ${item?.driver === driver ? "selected" : ""}>${label}</option>`).join("")}</select></label></div>`,
    onSubmit: async (data) => {
      const assignments = JSON.parse(JSON.stringify(state.hardware?.device_assignments || []));
      const target = edit ? assignments.find((entry) => entry.address === item.address) : {};
      target.address = data.get("address"); target.name = data.get("name"); target.driver = data.get("driver");
      if (target.driver === "waveshare_motor_hat" && !target.channels) target.channels = ["A","B"].map((channel) => ({ id: channel, name: `Motor ${channel}`, fluid_id: "unassigned", pump: {}, calibration: null }));
      if (target.driver !== "waveshare_motor_hat") delete target.channels;
      if (!edit) assignments.push(target);
      await api("/api/v1/hardware", { method: "POST", body: JSON.stringify({ device_assignments: assignments }) });
      dialog.close(); await loadState(); currentSetupView = "hardware"; showToast("I²C cihaz tanımı kaydedildi.");
    },
  });
}

function renderDosing(panel) {
  const hardware = state.hardware || {};
  const policy = hardware.dosing_policy || {};
  const fluids = hardware.dosing_fluids || [];
  const hats = (hardware.device_assignments || []).filter((item) => item.driver === "waveshare_motor_hat");
  const fluidOptions = (selected) => `<option value="unassigned" ${selected === "unassigned" ? "selected" : ""}>Atanmamış</option>${fluids.map((fluid) => `<option value="${html(fluid.id)}" ${selected === fluid.id ? "selected" : ""}>${html(fluid.name)} · ${html(fluid.brand || "")}</option>`).join("")}`;
  panel.innerHTML = `<form data-dosing-form><section class="hardware-section"><header class="section-head"><div><h3>Pompa kanalları</h3><small>${hats.reduce((total, item) => total + (item.channels?.length || 0), 0)} kanal</small></div></header>${hats.length ? hats.map((hat, hatIndex) => `<div class="motor-hat"><header><b>${html(hat.name)}</b></header>${(hat.channels || []).map((channel, channelIndex) => { const calibration = channel.calibration || {}; return `<div class="motor-channel"><div class="channel-name"><span>${html(channel.id)}</span><div><b>${html(channel.name)}</b><small>${calibration.flow_ml_s ? `${html(calibration.flow_ml_s)} ml/sn` : "Kalibrasyon yok"}</small></div></div><div><label><span>Bağlı sıvı</span><select name="channel.${hatIndex}.${channelIndex}.fluid_id">${fluidOptions(channel.fluid_id)}</select></label><details class="advanced-settings channel-settings"><summary>Pompa ve kalibrasyon</summary><div class="field-grid compact-grid"><label><span>Pompa markası</span><input name="channel.${hatIndex}.${channelIndex}.pump_brand" value="${html(channel.pump?.brand || "")}"></label><label><span>Pompa modeli</span><input name="channel.${hatIndex}.${channelIndex}.pump_model" value="${html(channel.pump?.model || "")}"></label><label><span>Çalışma süresi · sn</span><input name="channel.${hatIndex}.${channelIndex}.seconds" type="number" min="1" max="30" step=".1" value="${html(calibration.seconds || "")}" placeholder="Ölçüm yok"></label><label><span>Ölçülen hacim · ml</span><input name="channel.${hatIndex}.${channelIndex}.volume_ml" type="number" min=".01" max="500" step=".01" value="${html(calibration.volume_ml || "")}" placeholder="Ölçüm yok"></label><label><span>Pompa hızı · %</span><input name="channel.${hatIndex}.${channelIndex}.speed" type="number" min="20" max="100" value="${html(calibration.speed || 100)}"></label></div></details></div></div>`; }).join("")}</div>`).join("") : '<div class="device-empty"><span><b>Dozaj pompası bulunamadı</b><small>Önce Donanım bölümünden motor sürücünü ekle.</small></span><button class="secondary-button" type="button" data-go-hardware>Donanıma git</button></div>'}</section>
    <details class="advanced-settings"><summary>Dozaj güvenlik sınırları</summary><div class="field-grid">
      ${field("policy","nutrient_interval_minutes","Besin aralığı · dk",policy.nutrient_interval_minutes,{type:"number",min:30})}${field("policy","mixing_wait_minutes","Karışım bekleme · dk",policy.mixing_wait_minutes,{type:"number",min:5})}${field("policy","remeasure_wait_minutes","Yeniden ölçüm · dk",policy.remeasure_wait_minutes,{type:"number",min:1})}
      ${field("policy","ph_interval_minutes","pH aralığı · dk",policy.ph_interval_minutes,{type:"number",min:10})}${field("policy","ph_deadband","pH toleransı",policy.ph_deadband,{type:"number",min:.02,step:".01"})}${field("policy","max_nutrient_dose_ml","En fazla besin · ml",policy.max_nutrient_dose_ml,{type:"number",min:.1,step:".1"})}${field("policy","max_ph_dose_ml","En fazla pH sıvısı · ml",policy.max_ph_dose_ml,{type:"number",min:.1,step:".1"})}
    </div></details>
    <div class="setup-save"><button class="primary-button" type="submit">Dozaj kurulumunu kaydet</button></div></form>`;
  panel.querySelector("[data-go-hardware]")?.addEventListener("click", () => { currentSetupView = "hardware"; renderSetup(); });
  panel.querySelector("[data-dosing-form]").addEventListener("submit", saveDosing);
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
    const seconds = Number(data.get(`${prefix}.seconds`)); const volume = Number(data.get(`${prefix}.volume_ml`));
    channel.calibration = seconds > 0 && volume > 0 ? { seconds, volume_ml: volume, speed: Number(data.get(`${prefix}.speed`) || 100), calibrated_at: localDate() } : null;
  }));
  await api("/api/v1/hardware", { method: "POST", body: JSON.stringify({ dosing_policy: policy, device_assignments: assignments }) });
  await loadState(); currentSetupView = "dosing"; showToast("Dozaj eşlemeleri ve emniyet sınırları kaydedildi.");
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
  const nutrientFluids = (state.hardware?.dosing_fluids || []).filter((item) => !item.required && !["ph","ph_up","ph_down"].includes(item.category));
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
      </div>
      <details class="advanced-settings start-options"><summary>Besin ve diğer ayarlar</summary><div class="dialog-grid">
        <label class="full"><span>Yetiştirme adı</span><input name="name" placeholder="Boş bırakırsan otomatik adlandırılır"></label>
        <label><span>Yetiştirme yöntemi</span><select name="growing_method">${optionRows(cultivationMethods, system.growing_method || "RDWC")}</select></label>
        <label><span>Yetiştirme medyası</span><select name="growing_medium">${optionRows(growingMedia, system.growing_medium || "")}</select></label>
        ${nutrientFluids.length ? `<fieldset class="fluid-checks full start-fluid-list"><legend>Başlangıç aşamasında kullanılacak ürünler</legend>${nutrientFluids.map((fluid) => `<label><input type="checkbox" name="nutrient_ids" value="${html(fluid.id)}" data-start-nutrient> <span>${html(fluid.name)}<small>${html(fluid.brand || "Marka belirtilmedi")}</small></span></label>`).join("")}</fieldset>` : '<p class="empty-list full">Henüz besin ürünü eklenmemiş.</p>'}
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
}

function updateStartProfilePreview() {
  const plant = selectedPlant();
  const stage = dialogBody.querySelector("[data-initial-stage]")?.value;
  const target = plant?.profile?.stages?.[stage];
  const preview = dialogBody.querySelector("[data-profile-preview]");
  if (!preview) return;
  if (!target) {
    preview.innerHTML = `<span><b>Özel bitki şablonu</b><small>Başlangıç hedefleri daha sonra Bitki Kütüphanesi bölümünden düzenlenebilecek.</small></span>`;
    updateStartNutrientSelection(stage, target);
    return;
  }
  preview.innerHTML = `<span><b>${html(state.stage_labels[stage] || stage)} · ${html(target.planned_days)} gün</b><small>Bu bitki için başlangıç hedefi; istediğin zaman değiştirebilirsin.</small></span>
    <dl><div><dt>Işık</dt><dd>${html(target.photoperiod)} sa · %${html(target.light_intensity)}</dd></div><div><dt>Ortam</dt><dd>${html(target.day_temperature)} °C · %${html(target.humidity)}</dd></div><div><dt>Kök bölgesi</dt><dd>pH ${html(target.ph_min)}–${html(target.ph_max)} · EC ${html(target.ec_min)}–${html(target.ec_max)}</dd></div></dl>`;
  updateStartNutrientSelection(stage, target);
}

function updateStartNutrientSelection(stage, target) {
  const suggested = target?.nutrient_ids || [];
  dialogBody.querySelectorAll("[data-start-nutrient]").forEach((input) => { input.checked = suggested.includes(input.value); });
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
  payload.nutrient_ids = formData.getAll("nutrient_ids");
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

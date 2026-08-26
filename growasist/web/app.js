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
const viewMeta = {
  today: ["YETİŞTİRME MERKEZİ", "Bugün"],
  journal: ["KALICI KAYIT", "Günlük"],
  setup: ["RASPBERRY PI", "Kurulum"],
};

let token = sessionStorage.getItem(TOKEN_KEY) || "";
let state = null;
let currentView = "today";
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

document.querySelectorAll("[data-view]").forEach((button) => {
  button.addEventListener("click", () => {
    currentView = button.dataset.view;
    document.querySelectorAll("[data-view]").forEach((item) => item.classList.toggle("active", item === button));
    window.scrollTo(0, 0);
    render();
  });
});

function render() {
  if (!state) return;
  const [kicker, title] = viewMeta[currentView];
  viewKicker.textContent = kicker;
  viewTitle.textContent = title;
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
      <div class="empty-copy"><span class="kicker">YENİ BİR KAYIT BAŞLATIN</span>
        <h2>Bitkiyi değil, bütün yetiştirmeyi takip et.</h2>
        <p>Bitki kimliği, aşamalar, su ve besin kayıtları aynı kalıcı günlükte tutulur. Başladığınız anda ilk aşama ve bugünün kaydı oluşturulur.</p>
        <button class="primary-button" data-start-grow>Yetiştirmeyi başlat</button>
      </div>
      <div class="empty-facts"><span>YEREL VERİTABANI</span><span>SİLİNMEYEN GÜNLÜK</span><span>OTOMASYON KAPALI</span></div>
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
    <div><span class="kicker">${html(state.stage_labels[state.active_stage] || "AKTİF YETİŞTİRME")} · AŞAMA GÜNÜ ${stageDay}</span>
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
    <section><header class="section-head"><h3>Bugünün bağlamı</h3><small>Yalnız kayıt</small></header>
      <div class="assistant-wait"><div class="orb">◎</div><div>${context.map(([label, value]) => `<p><small>${html(label)}</small><br>${html(value)}</p>`).join("")}</div></div>
    </section>
  </div>
  <div class="setup-save"><button class="danger-button" data-finish-grow>Yetiştirmeyi tamamla</button></div>`;

  viewContent.querySelectorAll("[data-quick]").forEach((button) => button.addEventListener("click", () => openJournalDialog(button.dataset.quick)));
  viewContent.querySelector("[data-open-journal]").addEventListener("click", () => {
    currentView = "journal";
    document.querySelectorAll("[data-view]").forEach((item) => item.classList.toggle("active", item.dataset.view === "journal"));
    window.scrollTo(0, 0);
    render();
  });
  viewContent.querySelectorAll("[data-stage]").forEach((button) => button.addEventListener("click", () => changeStage(button.dataset.stage)));
  viewContent.querySelector("[data-finish-grow]").addEventListener("click", finishGrow);
}

function renderJournal() {
  const groups = {};
  [...state.events].reverse().forEach((event) => {
    (groups[event.local_date] ||= []).push(event);
  });
  const days = Object.entries(groups).sort(([a], [b]) => b.localeCompare(a));
  viewContent.innerHTML = `<div class="page-actions"><div><span class="kicker">${state.events.length} KALICI OLAY</span><p>Bir kayıt eklendikten sonra düzenlenmez veya silinmez; düzeltme gerekiyorsa yeni not eklenir.</p></div>
    <button class="primary-button" data-add-event ${state.active_cultivation ? "" : "disabled"}>Günlüğe ekle</button></div>
    <section class="journal-sheet">${days.length ? days.map(([date, events]) => `<div class="journal-day"><div class="journal-date"><b>${html(date.slice(8,10))}</b>${html(date.slice(0,7))}</div><div class="event-list">${events.map(eventRow).join("")}</div></div>`).join("") : '<p class="empty-list">Henüz günlük kaydı yok.</p>'}</section>`;
  viewContent.querySelector("[data-add-event]")?.addEventListener("click", () => openJournalDialog("user_note"));
}

function field(section, key, label, value, options = {}) {
  const name = `${section}.${key}`;
  if (options.choices) return `<label><span>${html(label)}</span><select name="${name}">${options.choices.map(([id, text]) => `<option value="${html(id)}" ${value === id ? "selected" : ""}>${html(text)}</option>`).join("")}</select></label>`;
  return `<label class="${options.wide ? "wide" : ""}"><span>${html(label)}</span><input name="${name}" type="${options.type || "text"}" value="${html(value)}" ${options.min != null ? `min="${options.min}"` : ""} ${options.step ? `step="${options.step}"` : ""}></label>`;
}

function renderSetup() {
  const profile = state.system_profile || {};
  const area = profile.cabin || {};
  const system = profile.system || {};
  const light = profile.lighting || {};
  const methods = [["RDWC","RDWC"],["DWC","DWC"],["NFT","NFT"],["Ebb and Flow","Ebb & Flow"],["Drip","Damla sulama"],["Aeroponics","Aeroponik"],["Kratky","Kratky"],["Coco","Coco"],["Soil","Toprak"]];
  const media = [["","Seçin"],["Expanded clay","Kil bilyesi"],["Rockwool","Taş yünü"],["Coco coir","Coco coir"],["Perlite","Perlit"],["Soil","Toprak"],["Water only","Yalnız su"],["Mixed","Karışım"]];
  const devices = Object.keys(state.device_registry?.devices || {}).length;
  viewContent.innerHTML = `<section class="setup-intro"><div><span class="kicker">HOME ASSISTANT BAĞIMSIZ</span><h2>Yetiştirme kurulumu</h2><p>Burada yalnız fiziksel alanı ve armatürü tanımlayın. Canlı dimmer, aç/kapa ve sensör değerleri cihaz sürücülerinden okunacak; elle gerçek değer yazılmayacak.</p></div>
    <span class="storage-badge">SQLITE ${html(state.storage.sqlite_integrity).toUpperCase()} · ${html(state.storage.revision_count)} REVİZYON</span></section>
  <form data-setup-form>
    <section class="setup-section"><header><h3>Yetiştirme alanı</h3><p>Bitkinin gerçekten kullandığı fiziksel ölçüler.</p></header><div class="field-grid">
      ${field("cabin","width_cm","Genişlik · cm",area.width_cm,{type:"number",min:0,step:"0.1"})}
      ${field("cabin","depth_cm","Derinlik · cm",area.depth_cm,{type:"number",min:0,step:"0.1"})}
      ${field("cabin","height_cm","Yükseklik · cm",area.height_cm,{type:"number",min:0,step:"0.1"})}
      ${field("system","plant_capacity","Bitki kapasitesi",system.plant_capacity,{type:"number",min:1})}
    </div></section>
    <section class="setup-section"><header><h3>Yöntem ve medya</h3><p>Köklerin içinde bulunduğu sistem ve fiziksel ortam.</p></header><div class="field-grid">
      ${field("system","growing_method","Yetiştirme yöntemi",system.growing_method,{choices:methods})}
      ${field("system","growing_medium","Yetiştirme medyası",system.growing_medium,{choices:media})}
      ${field("system","reservoir_volume_l","Rezervuar · L",system.reservoir_volume_l,{type:"number",min:0,step:"0.1"})}
      ${field("system","system_volume_l","Toplam çözelti · L",system.system_volume_l,{type:"number",min:0,step:"0.1"})}
    </div></section>
    <section class="setup-section"><header><h3>Işık armatürü</h3><p>Fiziksel kimlik. Canlı kontrol daha sonra bağlı Shelly sürücüsünden gelir.</p></header><div class="field-grid">
      ${field("lighting","brand","Marka",light.brand)}${field("lighting","model","Model",light.model,{wide:true})}
      ${field("lighting","fixture_count","Armatür sayısı",light.fixture_count,{type:"number",min:1})}
      ${field("lighting","power_w_each","Her birinin gücü · W",light.power_w_each,{type:"number",min:0})}
      ${field("lighting","height_cm","Bitkiye uzaklık · cm",light.height_cm,{type:"number",min:0,step:"0.1"})}
    </div></section>
    <section class="setup-section"><header><h3>Yerel cihazlar</h3><p>Shelly, Tuya, Tapo, MQTT ve I²C bağlantıları burada yaşayacak.</p></header>
      <div class="device-empty"><span><b>${devices ? `${devices} cihaz kayıtlı` : "Henüz yerel cihaz eklenmedi"}</b><small>Home Assistant entity eşlemesi kullanılmıyor.</small></span><button class="secondary-button" type="button" disabled>Ağ taraması hazırlanıyor</button></div>
    </section>
    <div class="setup-save"><button class="primary-button" type="submit">Kurulumu kaydet</button></div>
  </form>`;
  viewContent.querySelector("[data-setup-form]").addEventListener("submit", saveSetup);
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
  openDialog({
    kicker: "YENİ YETİŞTİRME",
    title: "Kalıcı kaydı başlat",
    submitLabel: "Yetiştirmeyi başlat",
    body: `<p class="dialog-note">Bitki profili ve mevcut kurulum bu yetiştirmeye kopyalanır. Sonraki değişiklikler geçmiş kaydı yeniden yazmaz.</p>
      <div class="dialog-grid">
        <label class="full"><span>Yetiştirme adı</span><input name="name" placeholder="Örn. Kış yetiştirmesi" required></label>
        <label><span>Bitki türü</span><select name="plant_profile_id" data-plant-select>${plants.map((plant) => `<option value="${html(plant.id)}">${html(plant.name)}</option>`).join("")}<option value="">Diğer / kendi bitkim</option></select></label>
        <label data-custom-plant hidden><span>Bitkinin adı</span><input name="plant_species" maxlength="96" placeholder="Tür veya yaygın adı"></label>
        <label><span>Bitki sayısı</span><input name="plant_count" type="number" min="1" value="1" required></label>
        <label data-cannabis-only hidden><span>Büyüme tipi</span><select name="growth_type" data-growth-type><option value="">Seçin</option><option value="photoperiod">Photoperiod</option><option value="autoflower">Autoflower</option></select></label>
        <label data-cannabis-only hidden><span>Kütüphanedeki çeşit</span><select name="cultivar_id" data-cultivar><option value="">Özel / seçilmedi</option></select></label>
        <label><span>Çeşit / cultivar</span><input name="cultivar" placeholder="Seçili değilse yazabilirsiniz"></label>
        <label><span>Satın alma kaynağı</span><input name="source" placeholder="Mağaza, paket veya parti"></label>
        <label><span>Yetiştirme yöntemi</span><select name="growing_method"><option>RDWC</option><option>DWC</option><option>NFT</option><option>Drip</option><option>Coco</option><option>Soil</option></select></label>
        <label><span>Yetiştirme medyası</span><select name="growing_medium"><option value="">Seçin</option><option>Expanded clay</option><option>Rockwool</option><option>Coco coir</option><option>Perlite</option><option>Soil</option><option>Water only</option><option>Mixed</option></select></label>
        <label><span>Başlangıç tarihi</span><input name="start_date" type="date" max="${today}" value="${today}" required></label>
        <label><span>İlk aşama</span><select name="initial_stage" data-initial-stage></select></label>
        <div class="profile-preview full" data-profile-preview></div>
        <label class="full"><span>Besin programı</span><input name="nutrient_program" placeholder="Kullandığınız seri veya program"></label>
        <label class="full"><span>Başlangıç notu</span><textarea name="notes" placeholder="Başlangıç koşulları, hedef veya önemli bir ayrıntı"></textarea></label>
      </div>`,
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
  dialogBody.querySelectorAll("[data-cannabis-only]").forEach((element) => { element.hidden = !cannabis; });
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
    return;
  }
  preview.innerHTML = `<span><b>${html(state.stage_labels[stage] || stage)} · ${html(target.planned_days)} gün</b><small>Düzenlenebilir örnek profil; evrensel yetiştirme reçetesi değildir.</small></span>
    <dl><div><dt>Işık</dt><dd>${html(target.photoperiod)} sa · %${html(target.light_intensity)}</dd></div><div><dt>Ortam</dt><dd>${html(target.day_temperature)} °C · %${html(target.humidity)}</dd></div><div><dt>Kök bölgesi</dt><dd>pH ${html(target.ph_min)}–${html(target.ph_max)} · EC ${html(target.ec_min)}–${html(target.ec_max)}</dd></div></dl>`;
}

function updateCultivarOptions() {
  const plant = selectedPlant();
  const growth = dialogBody.querySelector("[data-growth-type]")?.value || "";
  const cultivarSelect = dialogBody.querySelector("[data-cultivar]");
  if (!cultivarSelect) return;
  const breeders = state.plant_catalog?.breeders || {};
  const cultivars = (plant?.cultivars || []).filter((item) => item.active !== false && (!growth || item.growth_type === growth));
  cultivarSelect.innerHTML = `<option value="">Özel / seçilmedi</option>${cultivars.map((item) => `<option value="${html(item.id)}">${html(item.name)}${breeders[item.breeder_id] ? ` · ${html(breeders[item.breeder_id].name)}` : ""}</option>`).join("")}`;
}

async function submitStartGrow(formData) {
  const plant = selectedPlant();
  const cultivarId = String(formData.get("cultivar_id") || "");
  const cultivar = (plant?.cultivars || []).find((item) => item.id === cultivarId);
  const payload = Object.fromEntries(formData.entries());
  payload.plant_count = Number(payload.plant_count || 1);
  payload.cultivation_id = id();
  if (cultivar) {
    payload.growth_type = cultivar.growth_type;
    payload.breeder_id = cultivar.breeder_id;
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
    kicker: "SİLİNMEYEN GÜNLÜK",
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

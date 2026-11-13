/* ===== مزرعة القهوة السريعة — منطق اللعبة ===== */

// ---------- التكامل مع تيليجرام ----------
const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand(); // توسيع اللعبة لتملأ الشاشة
}

const API_URL = "coffee-telegram-bot-production.up.railway.app"

// مفتاح الحفظ: مربوط بحساب اللاعب في تيليجرام إن وُجد
const playerId = tg?.initDataUnsafe?.user?.id || "local-player";
const SAVE_KEY = `coffee-farm-${playerId}`;

// اسم اللاعب في رسالة الترحيب
const playerName = tg?.initDataUnsafe?.user?.first_name;
if (playerName) {
  document.getElementById("welcome").textContent = `أهلاً بك يا ${playerName}! ☕`;
}

// ---------- تعريف التطويرات ----------
const UPGRADES = [
  { id: "grinder",  icon: "⚙️",  name: "مطحنة يدوية",      baseCost: 15,     cps: 0.5 },
  { id: "espresso", icon: "☕",  name: "ماكينة إسبريسو",   baseCost: 120,    cps: 3 },
  { id: "roaster",  icon: "🔥",  name: "محمصة البن",        baseCost: 1300,   cps: 15 },
  { id: "packaging",icon: "📦",  name: "خط التغليف",        baseCost: 14000,  cps: 80 },
  { id: "truck",    icon: "🚚",  name: "شاحنة التوصيل",     baseCost: 150000, cps: 400 },
  { id: "gloves",   icon: "🧤",  name: "قفازات الباريستا",  baseCost: 500,    cps: 0, clickBonus: 2 },
];

const COST_GROWTH = 1.15; // كل عملية شراء ترفع السعر 15%

// ---------- حالة اللعبة ----------
function defaultState() {
  const owned = {};
  UPGRADES.forEach((u) => (owned[u.id] = 0));
  return { coins: 0, clickPower: 1, owned, boostUntil: 0 };
}

let state = loadGame();

// ---------- الحفظ والتحميل (LocalStorage) ----------
function loadGame() {
  try {
    const raw = localStorage.getItem(SAVE_KEY);
    if (!raw) return defaultState();
    return { ...defaultState(), ...JSON.parse(raw) };
  } catch {
    return defaultState();
  }
}

function saveGame() {
  localStorage.setItem(SAVE_KEY, JSON.stringify(state));
}

// ---------- الحسابات ----------
function isBoosted() {
  return Date.now() < state.boostUntil;
}

function cps() {
  let total = 0;
  UPGRADES.forEach((u) => (total += u.cps * state.owned[u.id]));
  return total * (isBoosted() ? 2 : 1);
}

function upgradeCost(u) {
  return Math.floor(u.baseCost * Math.pow(COST_GROWTH, state.owned[u.id]));
}

function format(n) {
  if (n >= 1e9) return (n / 1e9).toFixed(1) + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return Math.floor(n).toString();
}

// ---------- واجهة المتجر ----------
const upgradesList = document.getElementById("upgrades-list");

UPGRADES.forEach((u) => {
  const row = document.createElement("div");
  row.className = "upgrade";
  row.innerHTML = `
    <span class="upgrade-icon">${u.icon}</span>
    <div class="upgrade-info">
      <div class="upgrade-name">${u.name}</div>
      <div class="upgrade-desc">${u.clickBonus ? `+${u.clickBonus} لكل نقرة` : `+${u.cps} قهوة/ثانية`}</div>
      <div class="upgrade-owned" id="owned-${u.id}">تمتلك: 0</div>
    </div>
    <button class="upgrade-buy" id="buy-${u.id}">💰 ${format(u.baseCost)}</button>
  `;
  upgradesList.appendChild(row);

  row.querySelector("button").addEventListener("click", () => buyUpgrade(u));
});

function buyUpgrade(u) {
  const cost = upgradeCost(u);
  if (state.coins < cost) return;
  state.coins -= cost;
  state.owned[u.id]++;
  if (u.clickBonus) state.clickPower += u.clickBonus;
  saveGame();
  render();
}

// ---------- النقر ----------
const coffeeBtn = document.getElementById("coffee-btn");

coffeeBtn.addEventListener("click", (e) => {
  const gain = state.clickPower * (isBoosted() ? 2 : 1);
  state.coins += gain;
  spawnFloatNum(e.clientX, e.clientY, `+${format(gain)}`);
  render();
});

function spawnFloatNum(x, y, text) {
  const el = document.createElement("span");
  el.className = "float-num";
  el.textContent = text;
  el.style.left = x - 10 + "px";
  el.style.top = y - 20 + "px";
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 900);
}

// ---------- الإعلان الوهمي (مكافأة) ----------
const adBtn = document.getElementById("ad-btn");
const adOverlay = document.getElementById("ad-overlay");
const adTimer = document.getElementById("ad-timer");
let adCooldown = false;

adBtn.addEventListener("click", () => {
  if (adCooldown) return;
  adOverlay.classList.remove("hidden");

  let seconds = 5;
  adTimer.textContent = seconds;
  const countdown = setInterval(() => {
    seconds--;
    adTimer.textContent = seconds;
    if (seconds <= 0) {
      clearInterval(countdown);
      adOverlay.classList.add("hidden");
      grantAdReward();
    }
  }, 1000);
});

function grantAdReward() {
  // مكافأة فورية = إنتاج 60 ثانية + مضاعفة الإنتاج لمدة دقيقة
  const bonus = Math.max(Math.floor(cps() * 60), 50);
  state.coins += bonus;
  state.boostUntil = Date.now() + 60 * 1000;
  saveGame();
  showToast(`🎉 +${format(bonus)} قهوة! الإنتاج مضاعف ×2 لمدة دقيقة`);

  // فترة انتظار قبل الإعلان التالي
  adCooldown = true;
  adBtn.disabled = true;
  setTimeout(() => {
    adCooldown = false;
    adBtn.disabled = false;
  }, 60 * 1000);

  render();
}

// ---------- الإشعارات ----------
const toast = document.getElementById("toast");
function showToast(msg) {
  toast.textContent = msg;
  toast.classList.remove("hidden");
  setTimeout(() => toast.classList.add("hidden"), 3000);
}

// ---------- تحديث الشاشة ----------
function render() {
  document.getElementById("coins").textContent = format(state.coins);
  document.getElementById("cps").textContent = format(cps()) + (isBoosted() ? " 🔥" : "");
  document.getElementById("perClick").textContent = format(state.clickPower * (isBoosted() ? 2 : 1));

  UPGRADES.forEach((u) => {
    document.getElementById(`owned-${u.id}`).textContent = `تمتلك: ${state.owned[u.id]}`;
    const btn = document.getElementById(`buy-${u.id}`);
    const cost = upgradeCost(u);
    btn.textContent = `💰 ${format(cost)}`;
    btn.disabled = state.coins < cost;
  });
}

// ---------- حلقة اللعبة الرئيسية ----------
// الإنتاج التلقائي: يُحسب كل 100 مللي ثانية
setInterval(() => {
  state.coins += cps() / 10;
  render();
}, 100);

// حفظ تلقائي كل ثانيتين وعند إغلاق اللعبة
setInterval(saveGame, 2000);
window.addEventListener("beforeunload", saveGame);

// تشغيل أولي
render();

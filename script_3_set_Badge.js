// --- Suppress punycode DeprecationWarning ---
process.removeAllListeners('warning');
process.on('warning', w => {
  if (w.name === 'DeprecationWarning' && /punycode/.test(w.message)) return;
  console.warn(w.name, w.message);
});

"use strict";

// ===== Imports =====
const fs = require("fs");
const path = require("path");
const SteamUser = require("steam-user");
const SteamCommunity = require("steamcommunity");
const Request = require("request");

// ===== Config =====
let config;
try {
  config = require("./config.js");
} catch {
  console.error("ОШИБКА: нет config.js или ошибка в файле");
  process.exit(1);
}

// ===== Constants =====
const PROXIES_FILE = "./proxies.txt";
const SESSIONS_DIR = "./sessions";
const COMPLETED_FILE = path.join(__dirname, "result", "set_badge.txt");
const LOGIN_WIDTH = 15;

const C = { 
  R: "\x1b[0m", 
  G: "\x1b[90m", 
  RE: "\x1b[91m", 
  GR: "\x1b[92m", 
  Y: "\x1b[93m", 
  CY: "\x1b[96m", 
  W: "\x1b[97m", 
  LG: "\x1b[37m" 
};

// ===== State =====
let totalFiles = 0;
let processedCount = 0;

// ===== Utils =====
const sleep = ms => new Promise(r => setTimeout(r, ms));
const now = () => new Date().toTimeString().split(" ")[0];

const hideText = (text) => {
  if (!config.logging?.hideLogins || !text || text.length < 4) return text;
  const p = Math.max(1, Math.floor(text.length * ((config.logging.hidePercent ?? 50) / 100)));
  return text.slice(0, p) + "*".repeat(Math.max(0, text.length - p * 2)) + text.slice(-p);
};

const trimLogin = (login) => {
  const v = hideText(login);
  const clipped = v.length > LOGIN_WIDTH ? v.slice(0, LOGIN_WIDTH - 1) + "…" : v;
  return clipped.padEnd(LOGIN_WIDTH, " ");
};

const hideProxy = (proxy) => {
  if (!proxy) return proxy;
  const withoutProto = proxy.replace(/^https?:\/\//, "").replace(/^[^@]+@/, "");
  if (!config.logging?.hideLogins) return withoutProto;
  const [ip = "", port = ""] = withoutProto.split(":");
  return `${hideText(ip)}:${hideText(port)}`;
};

const log = (level, login, text) => {
  const colors = { OK: C.GR, WARN: C.Y, ERROR: C.RE, INFO: C.W, START: C.CY, TIMEOUT: C.Y };
  const lvl = String(level).toUpperCase().padEnd(5);
  const timePrefix = config.logging?.showTime ? `${now()} | ` : "";
  console.log(`${timePrefix}${C.LG}${trimLogin(login)}${C.R} | ${colors[level] || C.G}${lvl}${C.R} | ${C.G}${text}${C.R}`);
};

const showBox = (lines) => {
  const width = Math.max(45, Math.max(...lines.map(s => s.length)) + 4);
  const border = "─".repeat(width - 2);
  console.log(`\n┌${border}┐`);
  lines.forEach(m => console.log(`│ ${m}`.padEnd(width - 1) + "│"));
  console.log(`└${border}┘\n`);
};

const withTimeout = (promise, ms, reason = "TIMEOUT") =>
  Promise.race([promise, new Promise((_, rej) => setTimeout(() => rej(new Error(reason)), ms))]);

const remaining = () => totalFiles - processedCount;

// ===== Proxies =====
const loadProxies = () => {
  if (!fs.existsSync(PROXIES_FILE)) return [];
  return fs.readFileSync(PROXIES_FILE, "utf8")
    .split("\n").map(s => s.trim()).filter(s => s && !s.startsWith("#"));
};

// ===== Badge Management =====
function loadCompletedAccounts() {
  const completed = new Set();
  if (!fs.existsSync(COMPLETED_FILE)) return completed;
  
  try {
    fs.readFileSync(COMPLETED_FILE, "utf8")
      .split("\n")
      .filter(Boolean)
      .forEach(line => {
        const [login] = line.split(":");
        if (login) completed.add(login);
      });
  } catch (e) {}
  
  return completed;
}

function saveCompletedAccount(login, steamID, badgeName, badgeId) {
  try {
    fs.mkdirSync(path.dirname(COMPLETED_FILE), { recursive: true });
    const line = `${login}:${badgeId}:${badgeName}\n`;
    fs.appendFileSync(COMPLETED_FILE, line);
  } catch (e) {
    log("ERROR", login, `Ошибка записи: ${e.message}`);
  }
}

function getBadges(community, steamID) {
  return new Promise((resolve, reject) => {
    const url = `https://steamcommunity.com/profiles/${steamID}/badges/?l=english`;
    community.httpRequestGet(url, {}, (err, res, body) => {
      if (err) return reject(err);
      
      const cheerio = require("cheerio");
      const $ = cheerio.load(body);
      const badges = [];
      
      $(".badge_row").each(function() {
        const link = $(this).find(".badge_row_overlay").attr("href");
        if (!link) return;
        
        const gameMatch = link.match(/\/gamecards\/(\d+)/);
        const steamMatch = link.match(/\/badges?\/(\d+)/);
        
        if (!gameMatch && !steamMatch) return;
        
        const name = $(this).find(".badge_title").clone().children().remove().end().text().trim();
        const hasIcon = $(this).find(".badge_icon").length > 0;
        const levelMatch = $(this).find(".badge_info_description").text().match(/Level (\d+)/);
        const level = levelMatch ? parseInt(levelMatch[1]) : (hasIcon ? 1 : 0);
        
        if (level > 0 && hasIcon) {
          badges.push({
            name: name,
            id: gameMatch ? gameMatch[1] : steamMatch[1],
            type: gameMatch ? 'game' : 'steam'
          });
        }
      });
      
      resolve(badges);
    });
  });
}

function getAccessToken(cookies) {
  for (const cookie of cookies) {
    if (cookie.includes('steamLoginSecure=')) {
      try {
        const loginSecure = decodeURIComponent(cookie.split('steamLoginSecure=')[1].split(';')[0]);
        const parts = loginSecure.split('||');
        if (parts.length >= 2) return parts[1];
      } catch (e) {}
    }
  }
  return null;
}

function setBadge(community, badgeId, cookies) {
  return new Promise((resolve, reject) => {
    const token = getAccessToken(cookies);
    
    if (!token) return reject(new Error("Нет access token"));
    
    const url = `https://api.steampowered.com/IPlayerService/SetFavoriteBadge/v1/?access_token=${token}`;
    const postData = { badgeid: badgeId };
    
    community.httpRequestPost(url, { form: postData }, (err, res, body) => {
      if (err) return reject(err);
      
      // Успехом считается только HTTP 200
      if (res.statusCode === 200) {
        resolve({ success: true, statusCode: res.statusCode });
      } else {
        reject(new Error(`HTTP ${res.statusCode}`));
      }
    });
  });
}

function selectBadge(badges, badgeConfig) {
  if (!badges.length) return null;
  
  // Если random: true - выбираем случайный значок из всех доступных
  if (badgeConfig.random === true) {
    return badges[Math.floor(Math.random() * badges.length)];
  }
  
  // Если random: false - используем массив ids
  if (badgeConfig.random === false && badgeConfig.ids && badgeConfig.ids.length > 0) {
    const availableBadges = badges.filter(b => badgeConfig.ids.includes(parseInt(b.id)));
    if (availableBadges.length > 0) {
      return availableBadges[Math.floor(Math.random() * availableBadges.length)];
    }
    return null;
  }
  
  // По умолчанию случайный если настройки некорректны
  return badges[Math.floor(Math.random() * badges.length)];
}

// ===== Auth с функционалом значков =====
async function loginAccount(login, sessionPath, proxy, threadId) {
  let sess;
  try {
    sess = JSON.parse(fs.readFileSync(sessionPath, "utf8"));
  } catch (e) {
    log("ERROR", login, `W${String(threadId).padStart(2,"0")} | Чтение: ${e.message}`);
    return { error: true };
  }
  
  if (!sess?.DesktopRefreshToken) {
    log("ERROR", login, `W${String(threadId).padStart(2,"0")} | Нет токена`);
    return { error: true };
  }

  const client = new SteamUser({
    webCompatibilityMode: true,
    dataDirectory: null,
    enablePicsCache: false,
    httpProxy: (config.useProxy && proxy) ? proxy : undefined,
  });

  try {
    const res = await new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error("Steam timeout")), 25_000);

      client.once("error", err => { clearTimeout(t); reject(err); });
      client.once("loggedOn", () => { 
        try { 
          client.setPersona(SteamUser.EPersonaState.Invisible); 
        } catch {} 
      });
      
      client.once("webSession", (sessionID, cookies) => {
        clearTimeout(t);
        if (!client.steamID) return reject(new Error("steamID не получен"));
        
        const steamID = client.steamID.getSteamID64();
        const proxyInfo = proxy ? ` | Прокси: ${hideProxy(proxy)}` : "";
        log("START", login, `W${String(threadId).padStart(2,"0")} | ID: ${C.GR}${hideText(steamID)}${C.R}${proxyInfo}`);
        
        // Настройка SteamCommunity
        const reqOpts = { timeout: (config.timeout || 30) * 1000 };
        if (proxy) reqOpts.proxy = proxy;
        const community = new SteamCommunity({ request: Request.defaults(reqOpts) });
        community.setCookies(cookies);
        
        resolve({ success: true, steamID, community, cookies, client });
      });

      client.logOn({ refreshToken: sess.DesktopRefreshToken });
    });

    // Обработка значков если включена
    if (config.badge && (config.badge.random === true || config.badge.random === false) && res.success) {
      try {
        // Получаем список значков
        const badges = await getBadges(res.community, res.steamID);
        
        if (badges.length > 0) {
          // В режиме random: true показываем найденные значки
          if (config.badge.random === true) {
            const badgeIds = badges.map(b => b.id).join(", ");
            log("INFO", login, `W${String(threadId).padStart(2,"0")} | Найдено значков: ${badges.length} [${badgeIds}]`);
          }
          
          const selectedBadge = selectBadge(badges, config.badge);
          if (selectedBadge) {
            try {
              const result = await setBadge(res.community, selectedBadge.id, res.cookies);
              if (result.success) {
                log("OK", login, `W${String(threadId).padStart(2,"0")} | Установлен значок: ${selectedBadge.name} (ID: ${selectedBadge.id})`);
                saveCompletedAccount(login, res.steamID, selectedBadge.name, selectedBadge.id);
              }
            } catch (setBadgeError) {
              log("ERROR", login, `W${String(threadId).padStart(2,"0")} | Ошибка установки значка: ${setBadgeError.message}`);
              // Не записываем в completed при ошибке
            }
          } else {
            log("WARN", login, `W${String(threadId).padStart(2,"0")} | Не найдены значки с указанными ID`);
            // Не записываем в completed если нет подходящих значков
          }
        } else {
          log("WARN", login, `W${String(threadId).padStart(2,"0")} | Нет значков для установки`);
          // Не записываем в completed если нет значков вообще
        }
      } catch (badgeError) {
        log("ERROR", login, `W${String(threadId).padStart(2,"0")} | Общая ошибка: ${badgeError.message}`);
        // Не записываем в completed при общей ошибке
      }
    }

    try { res.client.logOff(); } catch {}
    return { success: true, steamID: res.steamID };

  } catch (err) {
    try { client.logOff(); } catch {}
    log("ERROR", login, `W${String(threadId).padStart(2,"0")} | ${err.message}`);
    return { error: true };
  }
}

async function loginSafe(login, sessionPath, proxy, threadId) {
  try {
    const r = await withTimeout(
      loginAccount(login, sessionPath, proxy, threadId),
      (config.timeout || 30) * 1000,
      "ACCOUNT_TIMEOUT"
    );
    processedCount++;
    const rem = remaining();
    
    if (r?.success) {
      log("INFO", login, `Осталось: ${C.CY}${rem}${C.R}`);
      return { success: true };
    }
    
    log("ERROR", login, `W${String(threadId).padStart(2,"0")} | Ошибка входа`);
    log("INFO", login, `Осталось: ${C.CY}${rem}${C.R}`);
    return { error: true };
    
  } catch (err) {
    processedCount++;
    const rem = remaining();
    
    if (err.message === "ACCOUNT_TIMEOUT" || err.message.includes("TIMEOUT")) {
      log("TIMEOUT", login, `W${String(threadId).padStart(2,"0")} | Таймаут ${config.timeout || 30}с`);
      log("INFO", login, `Осталось: ${C.CY}${rem}${C.R}`);
      return { timeout: true };
    }
    throw err;
  }
}

// ===== Thread worker =====
async function processThread(files, proxies, fileIndex, threadId) {
  while (fileIndex.current < files.length) {
    const idx = fileIndex.current++;
    if (idx >= files.length) break;

    const file = files[idx];
    const login = path.basename(file, ".steamsession");
    const sessionPath = path.join(SESSIONS_DIR, file);
    const proxy = (config.useProxy && proxies.length) ? proxies[idx % proxies.length] : null;

    await loginSafe(login, sessionPath, proxy, threadId);
    await sleep(1200);
  }
}

// ===== Main =====
(async () => {
  if (!fs.existsSync(SESSIONS_DIR)) {
    console.error("Папка ./sessions не найдена");
    process.exit(1);
  }

  const allFiles = fs.readdirSync(SESSIONS_DIR).filter(f => f.endsWith(".steamsession"));
  if (!allFiles.length) {
    console.log("Нет сессий");
    process.exit(0);
  }

  // Исключаем уже обработанные аккаунты если включена установка значков
  let files = allFiles;
  if (config.badge && (config.badge.random === true || config.badge.random === false)) {
    const completed = loadCompletedAccounts();
    files = allFiles.filter(f => {
      const login = path.basename(f, ".steamsession");
      return !completed.has(login);
    });
    
    if (completed.size > 0) {
      console.log(`Пропущено уже обработанных аккаунтов: ${completed.size}`);
    }
    
    if (!files.length) {
      console.log("Все аккаунты уже обработаны!");
      process.exit(0);
    }
  }

  totalFiles = files.length;
  const proxies = config.useProxy ? loadProxies() : [];

  // Подготовка информации о значках для отображения
  let badgeInfo = "Выключено";
  if (config.badge) {
    if (config.badge.random === true) {
      badgeInfo = "Случайный";
    } else if (config.badge.random === false && config.badge.ids) {
      badgeInfo = `Конкретные ID: [${config.badge.ids.join(", ")}]`;
    }
  }

  showBox([
    `Всего: ${allFiles.length} | Готово: ${loadCompletedAccounts().size} | К обработке: ${files.length}`,
    `Потоков: ${config.threads} | Таймаут: ${config.timeout || 30}с`,
    `Прокси: ${config.useProxy ? 'Да' : 'Нет'} (${proxies.length})`,
    `Значки: ${badgeInfo}`
  ]);

  const fileIndex = { current: 0 };
  const n = Math.max(1, Number(config.threads) || 1);
  const threads = Array.from({ length: n }, (_, i) => processThread(files, proxies, fileIndex, i + 1));

  await Promise.allSettled(threads);

  showBox([`Готово. Обработано: ${processedCount}/${totalFiles}`]);
  process.exit(0);
})();
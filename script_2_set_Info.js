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
const COMPLETED_FILE = path.join(__dirname, "result", "set_info.txt");
const LOGIN_WIDTH = 15;

const Colors = {
  R: "\x1b[0m",
  G: "\x1b[90m",
  RE: "\x1b[91m",
  GR: "\x1b[92m",
  Y: "\x1b[93m",
  CY: "\x1b[96m",
  W: "\x1b[97m",
  LG: "\x1b[37m"
};

// ===== Global State =====
let totalFiles = 0;
let processedCount = 0;
let globalStats = { 
  processed: 0, 
  success: 0, 
  errors: 0, 
  timeouts: 0, 
  rateLimited: 0, 
  urlInUse: 0, 
  ipRateLimited: 0 
};
let stoppedThreads = new Set();

// ===== Utility Functions =====
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
  const colors = { 
    OK: Colors.GR, 
    WARN: Colors.Y, 
    ERROR: Colors.RE, 
    INFO: Colors.W, 
    START: Colors.CY, 
    TIMEOUT: Colors.Y, 
    STOP: Colors.RE 
  };
  const lvl = String(level).toUpperCase().padEnd(5);
  const timePrefix = config.logging?.showTime ? `${now()} | ` : "";
  console.log(`${timePrefix}${Colors.LG}${trimLogin(login)}${Colors.R} | ${colors[level] || Colors.G}${lvl}${Colors.R} | ${Colors.G}${text}${Colors.R}`);
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

// ===== Data Loading Functions =====
const loadProxies = () => {
  if (!fs.existsSync(PROXIES_FILE)) return [];
  return fs.readFileSync(PROXIES_FILE, "utf8")
    .split("\n").map(s => s.trim()).filter(s => s && !s.startsWith("#"));
};

const loadCompleted = () => {
  const completed = new Set();
  if (!fs.existsSync(COMPLETED_FILE)) return completed;
  
  try {
    fs.readFileSync(COMPLETED_FILE, "utf8").split("\n").filter(Boolean).forEach(line => {
      const login = line.split(':')[0];
      if (login) completed.add(login);
    });
  } catch (e) {}
  
  return completed;
};

const saveCompleted = (login, results) => {
  try {
    fs.mkdirSync(path.dirname(COMPLETED_FILE), { recursive: true });
    const line = `${login}:${results.join(',')}\n`;
    fs.appendFileSync(COMPLETED_FILE, line);
  } catch (e) {
    console.error(`Ошибка записи: ${e.message}`);
  }
};

const loadNicknames = () => {
  try {
    const data = fs.readFileSync(config.profile.nickNames, "utf8");
    return data.split("\n").map(line => line.trim()).filter(line => line.length > 0);
  } catch (e) {
    console.error("Ошибка чтения файла с никнеймами:", e.message);
    process.exit(1);
  }
};

const loadRealNames = () => {
  try {
    const data = fs.readFileSync(config.profile.realNames, "utf8");
    return data.split("\n").map(line => line.trim()).filter(line => line.length > 0);
  } catch (e) {
    console.error("Ошибка чтения файла с именами:", e.message);
    process.exit(1);
  }
};

const loadCountries = () => {
  try {
    const data = fs.readFileSync(config.profile.countries, "utf8");
    const lines = data.trim().split('\n');
    const countries = [];
    
    lines.forEach(line => {
      const [country, state, cities] = line.split(':');
      if (cities) {
        const cityList = cities.split(',');
        cityList.forEach(city => {
          countries.push({ country, state, city });
        });
      }
    });
    
    if (config.profile.allowedCountries && config.profile.allowedCountries.length > 0) {
      return countries.filter(c => config.profile.allowedCountries.includes(c.country));
    }
    
    return countries;
  } catch (e) {
    console.error("Ошибка чтения файла со странами:", e.message);
    process.exit(1);
  }
};

// ===== Profile Data Generation =====
const getRandomNickname = (nicknames) => {
  return nicknames[Math.floor(Math.random() * nicknames.length)];
};

const getRandomRealName = (realNames) => {
  return realNames[Math.floor(Math.random() * realNames.length)];
};

const getRandomCountry = (countries) => {
  return countries[Math.floor(Math.random() * countries.length)];
};

const generateCustomURL = (nickname) => {
  let url = nickname;
  const settings = config.profile.customURLSettings;

  const digitCount = Math.floor(Math.random() * (settings.maxDigits - settings.minDigits + 1)) + settings.minDigits;
  for (let i = 0; i < digitCount; i++) {
    const digit = Math.floor(Math.random() * 9) + 1;
    const pos = Math.floor(Math.random() * (url.length + 1));
    url = url.slice(0, pos) + digit + url.slice(pos);
  }

  const pool = Array.isArray(settings.allowedSpecials) ? settings.allowedSpecials.filter(Boolean) : [];
  if (pool.length) {
    const specialCount = Math.floor(Math.random() * (settings.maxSpecials - settings.minSpecials + 1)) + settings.minSpecials;
    for (let i = 0; i < specialCount; i++) {
      const special = pool[Math.floor(Math.random() * pool.length)];
      const pos = Math.floor(Math.random() * (url.length + 1));
      url = url.slice(0, pos) + special + url.slice(pos);
    }

    while (pool.some(s => url.startsWith(s))) url = url.slice(1);
    while (pool.some(s => url.endsWith(s))) url = url.slice(0, -1);
  }

  return url;
};

// ===== Steam Community Functions =====
const makeCommunity = (proxy) => {
  const opts = { timeout: 20000 };
  if (proxy) opts.proxy = proxy;
  return new SteamCommunity({ request: Request.defaults(opts) });
};

// ===== Authentication & Profile Setup =====
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

      client.once("error", err => { 
        clearTimeout(t); 
        reject(err); 
      });
      
      client.once("loggedOn", () => { 
        try { 
          client.setPersona(SteamUser.EPersonaState.Invisible); 
        } catch {} 
      });
      
      client.once("webSession", (sessionID, cookies) => {
        clearTimeout(t);
        if (!client.steamID) return reject(new Error("steamID не получен"));
        
        const steamID = client.steamID.getSteamID64();
        const community = makeCommunity(proxy);
        community.setCookies(cookies);
        client.logOff();
        
        if (config.logging?.showDetails) {
          const p = proxy ? ` | Прокси: ${hideProxy(proxy)}` : "";
          log("START", login, `W${String(threadId).padStart(2,"0")} | ID: ${Colors.GR}${hideText(steamID)}${Colors.R}${p}`);
        }
        
        resolve({ success: true, steamID, community, cookies });
      });

      client.logOn({ refreshToken: sess.DesktopRefreshToken });
    });

    return res;

  } catch (err) {
    try { client.logOff(); } catch {}
    log("ERROR", login, `W${String(threadId).padStart(2,"0")} | ${err.message}`);
    return { error: true };
  }
}

async function setupProfile(login, community, nicknames, realNames, countries, threadId) {
  try {
    const results = [];
    const profileData = {};
    
    let nickname = null;
    if (config.profile.nickname) {
      nickname = getRandomNickname(nicknames);
      profileData.name = nickname;
      results.push(`nickname:${nickname}`);
    }
    
    if (config.profile.realName) {
      let realName;
      if (config.profile.realNameMode === "same" && nickname) {
        realName = nickname;
      } else {
        realName = getRandomRealName(realNames);
      }
      profileData.realName = realName;
      results.push(`realName:${realName}`);
    }
    
    if (config.profile.country) {
      const location = getRandomCountry(countries);
      profileData.country = location.country;
      profileData.state = location.state;
      profileData.city = location.city;
      results.push(`country:${location.country}`);
    }
    
    if (config.profile.customURL) {
  const baseForURL = nickname || getRandomNickname(nicknames);
  if (/^[A-Za-z0-9_]+$/.test(baseForURL)) {
    profileData.customURL = baseForURL;            // ставим как есть
    results.push(`customURL:${baseForURL}`);
  } else if (config.logging?.showDetails) {
    log("WARN", login, `W${String(threadId).padStart(2,"0")} | пропуск customURL: никнейм содержит недопутимые символы`);
  }
}

    if (config.logging?.showDetails) {
      const details = [];
      if (profileData.name) details.push(`Ник: ${profileData.name}`);
      if (profileData.realName) details.push(`Имя: ${profileData.realName}`);
      if (profileData.country) details.push(`Страна: ${profileData.country}`);
      if (profileData.customURL) details.push(`URL: ${profileData.customURL}`);
      log("INFO", login, `W${String(threadId).padStart(2,"0")} | ${details.join(', ')}`);
    }

    if (Object.keys(profileData).length > 0) {
      await new Promise((resolve, reject) => {
        community.editProfile(profileData, (err) => {
          if (err) return reject(err);
          resolve();
        });
      });
    }

    return { success: true, results };

  } catch (err) {
    const errorMessage = err.message || "";
    
    if (errorMessage.includes("HTTP error 429")) {
      log("STOP", login, `W${String(threadId).padStart(2,"0")} | IP Rate Limit! Поток остановлен`);
      return { ipRateLimited: true };
    }
    
    if (errorMessage.includes("There was an error setting the custom URL") || 
        errorMessage.includes("An error occurred while setting account details")) {
      log("WARN", login, `W${String(threadId).padStart(2,"0")} | Лимит редактирования профиля! Попробуйте через 5 часов`);
      return { rateLimited: true };
    }
    
    if (errorMessage.includes("The profile URL specified is already in use")) {
      log("WARN", login, `W${String(threadId).padStart(2,"0")} | URL профиля занят, пропускаем аккаунт`);
      return { urlInUse: true };
    }
    
    log("ERROR", login, `W${String(threadId).padStart(2,"0")} | Ошибка настройки: ${err.message}`);
    return { error: true };
  }
}

async function processAccountSafe(login, sessionPath, proxy, nicknames, realNames, countries, threadId) {
  try {
    const loginResult = await withTimeout(
      loginAccount(login, sessionPath, proxy, threadId),
      (config.timeout || 30) * 1000,
      "ACCOUNT_TIMEOUT"
    );

    if (loginResult.error) {
      const remaining = logProgress(login, false);
      globalStats.errors++;
      log("ERROR", login, `W${String(threadId).padStart(2,"0")} | Ошибка входа [${remaining} осталось]`);
      return { error: true };
    }

    const { community } = loginResult;
    
    const profileResult = await withTimeout(
      setupProfile(login, community, nicknames, realNames, countries, threadId),
      (config.timeout || 30) * 1000,
      "PROFILE_TIMEOUT"
    );

    if (profileResult.success) {
      const remaining = logProgress(login, true, profileResult.results);
      log("OK", login, `W${String(threadId).padStart(2,"0")} | Профиль настроен`);
      log("INFO", login, `W${String(threadId).padStart(2,"0")} | Осталось: ${Colors.CY}${remaining}${Colors.R}`);
      return { success: true };
    } else if (profileResult.ipRateLimited) {
      const remaining = logProgress(login, false);
      globalStats.ipRateLimited++;
      stoppedThreads.add(threadId);
      log("STOP", login, `W${String(threadId).padStart(2,"0")} | Поток остановлен из-за IP rate limit [${remaining} осталось]`);
      return { ipRateLimited: true };
    } else if (profileResult.rateLimited) {
      const remaining = logProgress(login, false);
      globalStats.rateLimited++;
      log("WARN", login, `W${String(threadId).padStart(2,"0")} | Лимит редактирования [${remaining} осталось]`);
      return { rateLimited: true };
    } else if (profileResult.urlInUse) {
      const remaining = logProgress(login, false);
      globalStats.urlInUse++;
      log("WARN", login, `W${String(threadId).padStart(2,"0")} | URL занят [${remaining} осталось]`);
      return { urlInUse: true };
    } else {
      const remaining = logProgress(login, false);
      globalStats.errors++;
      log("ERROR", login, `W${String(threadId).padStart(2,"0")} | Ошибка настройки [${remaining} осталось]`);
      return { error: true };
    }

  } catch (err) {
    const remaining = logProgress(login, false);
    
    if (err.message.includes('TIMEOUT')) {
      globalStats.timeouts++;
      log("TIMEOUT", login, `W${String(threadId).padStart(2,"0")} | Таймаут ${config.timeout || 30}с [${remaining} осталось]`);
      return { timeout: true };
    }
    
    throw err;
  }
}

const logProgress = (login, success, items = []) => {
  processedCount++;
  if (success) {
    globalStats.success++;
    saveCompleted(login, items);
  }
  return totalFiles - processedCount;
};

// ===== Thread Processing =====
async function processThread(files, proxies, fileIndex, threadId, nicknames, realNames, countries) {
  while (fileIndex.current < files.length) {
    if (stoppedThreads.has(threadId)) {
      log("STOP", "THREAD", `W${String(threadId).padStart(2,"0")} | Поток остановлен, больше не обрабатывает аккаунты`);
      break;
    }
    
    const idx = fileIndex.current++;
    if (idx >= files.length) break;

    const file = files[idx];
    const login = path.basename(file, ".steamsession");
    const sessionPath = path.join(SESSIONS_DIR, file);
    const proxy = (config.useProxy && proxies.length) ? proxies[idx % proxies.length] : null;
    
    const result = await processAccountSafe(login, sessionPath, proxy, nicknames, realNames, countries, threadId);
    
    if (result.ipRateLimited) {
      break;
    }
    
    if (config.accountDelay) await sleep(config.accountDelay * 1000);
  }
}

// ===== Main Execution =====
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

  const completed = loadCompleted();
  const filesToProcess = allFiles.filter(f => {
    const login = path.basename(f, ".steamsession");
    return !completed.has(login);
  });

  totalFiles = filesToProcess.length;
  const proxies = config.useProxy ? loadProxies() : [];
  const nicknames = loadNicknames();
  const realNames = loadRealNames();
  const countries = loadCountries();

  const allowedCountriesText = config.profile.allowedCountries && config.profile.allowedCountries.length > 0 
    ? config.profile.allowedCountries.join(', ') 
    : 'Все';

  showBox([
    `Всего: ${allFiles.length} | Готово: ${completed.size} | К обработке: ${filesToProcess.length}`,
    `Потоков: ${config.threads} | Таймаут: ${config.timeout || 30}с`,
    `Прокси: ${config.useProxy ? 'Да' : 'Нет'} (${proxies.length})`,
    `Подробные логи: ${config.logging?.showDetails ? 'Да' : 'Нет'}`,
    `Никнеймов: ${nicknames.length} | Имен: ${realNames.length} | Локаций: ${countries.length}`,
    `Режим realName: ${config.profile.realNameMode} | Страны: ${allowedCountriesText}`
  ]);

  if (filesToProcess.length === 0) {
    console.log("Все аккаунты обработаны!");
    process.exit(0);
  }

  const start = Date.now();
  const fileIndex = { current: 0 };
  const n = Math.max(1, Number(config.threads) || 1);
  
  const threads = Array.from({ length: n }, (_, i) => 
    processThread(filesToProcess, proxies, fileIndex, i + 1, nicknames, realNames, countries)
  );

  await Promise.allSettled(threads);

  const duration = ((Date.now() - start) / 1000).toFixed(1);

  showBox([
    `Завершено за ${duration}с`,
    `Успешно: ${globalStats.success} | Ошибки: ${globalStats.errors} | Таймауты: ${globalStats.timeouts}`,
    `Лимит редактирования: ${globalStats.rateLimited || 0} (попробуйте через 5 часов)`,
    `URL занят: ${globalStats.urlInUse || 0} (будет обработано при повторном запуске)`,
    `IP Rate Limit: ${globalStats.ipRateLimited || 0} (потоки остановлены)`
  ]);

  process.exit(0);
})();
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

// ===== Consts / Colors =====
const COMPLETED_FILE = path.join(__dirname, "result", "set_cosmetics.txt");
const PROXIES_FILE   = "./proxies.txt";
const SESSIONS_DIR   = "./sessions";

const C = { R:"\x1b[0m", G:"\x1b[90m", RE:"\x1b[91m", GR:"\x1b[92m", Y:"\x1b[93m", CY:"\x1b[96m", W:"\x1b[97m", LG:"\x1b[37m" };
const LOGIN_WIDTH = 15;

let totalFiles = 0, processedCount = 0;
let globalStats = { processed: 0, success: 0, errors: 0, timeouts: 0, empty: 0 };

// ===== Utils =====
const sleep = ms => new Promise(r => setTimeout(r, ms));
const now   = () => new Date().toTimeString().split(" ")[0];

const hideText = (text) => {
  if (!config.logging?.hideLogins || !text || text.length < 4) return text;
  const p = Math.max(1, Math.floor(text.length * ((config.logging.hidePercent || 50) / 100)));
  return text.slice(0, p) + "*".repeat(Math.max(0, text.length - p*2)) + text.slice(-p);
};
const trimLogin = (login) => {
  const v = hideText(login);
  const clipped = v.length > LOGIN_WIDTH ? v.slice(0, LOGIN_WIDTH - 1) + "…" : v;
  return clipped.padEnd(LOGIN_WIDTH, " ");
};
const hideProxy = (proxy) => {
  if (!proxy) return proxy;
  const withoutProto = proxy.replace(/^https?:\/\//, '').replace(/^[^@]+@/, '');
  if (!config.logging?.hideLogins) return withoutProto;
  const parts = withoutProto.split(':');
  if (parts.length >= 2) {
    return `${hideText(parts[0])}:${hideText(parts[1])}`;
  }
  return hideText(withoutProto);
};

const log = (level, login, text) => {
  const colors = { OK:C.GR, WARN:C.Y, ERROR:C.RE, INFO:C.W, START:C.CY, TIMEOUT:C.Y };
  const lvl = String(level).toUpperCase().padEnd(5);
  const timePrefix = config.logging?.showTime ? `${now()} | ` : '';
  console.log(`${timePrefix}${C.LG}${trimLogin(login)}${C.R} | ${colors[level] || C.G}${lvl}${C.R} | ${C.G}${text}${C.R}`);
};

const showBox = (lines) => {
  const width = Math.max(45, Math.max(...lines.map(s => s.length)) + 4);
  const border = "─".repeat(width - 2);
  console.log(`\n┌${border}┐`);
  lines.forEach(m => console.log(`│ ${m}`.padEnd(width - 1) + "│"));
  console.log(`└${border}┘\n`);
};

const withTimeout = (promise, ms, reason = 'TIMEOUT') =>
  Promise.race([promise, new Promise((_, rej) => setTimeout(() => rej(new Error(reason)), ms))]);

// ===== Completed (partial progress per item) =====
// Формат файла сохраняем: каждая строка login:itemType:itemId[,item2...]
const loadCompleted = () => {
  const map = new Map(); // login -> Set(types)
  if (!fs.existsSync(COMPLETED_FILE)) return map;

  try {
    fs.readFileSync(COMPLETED_FILE, "utf8")
      .split("\n")
      .filter(Boolean)
      .forEach(line => {
        const [login, itemsStr] = line.split(':');
        if (!login) return;
        const set = map.get(login) || new Set();
        if (itemsStr) {
          // поддержка "type:id,type2:id2" и старого "type:id" без запятой
          String(itemsStr).split(',').forEach(tok => {
            const type = String(tok).split(':')[0].trim();
            if (type) set.add(type);
          });
        }
        map.set(login, set);
      });
  } catch {}
  return map;
};
const saveCompleted = (login, items) => {
  try {
    fs.mkdirSync(path.dirname(COMPLETED_FILE), { recursive: true });
    fs.appendFileSync(COMPLETED_FILE, `${login}:${items.join(',')}\n`);
  } catch (e) {
    console.error(`Ошибка записи: ${e.message}`);
  }
};

const enabledTypes = () => {
  const a = [];
  if (config.enabled?.avatar)         a.push('avatar');
  if (config.enabled?.frame)          a.push('frame');
  if (config.enabled?.background)     a.push('background');
  if (config.enabled?.miniBackground) a.push('miniBackground');
  if (config.enabled?.theme)          a.push('theme');
  return a;
};

// ===== Proxies =====
const loadProxies = () => {
  if (!fs.existsSync(PROXIES_FILE)) return [];
  return fs.readFileSync(PROXIES_FILE, "utf8")
    .split("\n").map(s => s.trim()).filter(s => s && !s.startsWith("#"));
};

// ===== Steam helpers =====
const makeCommunity = (proxy) => {
  const opts = { timeout: 20000 };
  if (proxy) opts.proxy = proxy;
  return new SteamCommunity({ request: Request.defaults(opts) });
};

const loadInventory = (community, steamID) => new Promise((res, rej) => {
  community.getUserInventory(steamID, 753, 6, false, (err, items) => err ? rej(err) : res(items || []));
});

const findItems = (items, classId) => items.filter(it =>
  (it.tags || []).some(tag => tag.category === "item_class" && tag.internal_name === classId)
).map(it => ({
  id: it.id,
  assetid: it.assetid,
  name: it.market_hash_name || it.name || "Unknown"
}));

const getAccessToken = (cookies) => {
  for (const c of cookies) {
    if (c.includes('steamLoginSecure=')) {
      try {
        const loginSecure = decodeURIComponent(c.split('steamLoginSecure=')[1].split(';')[0]);
        const parts = loginSecure.split('||');
        if (parts.length >= 2) return parts[1];
      } catch {}
    }
  }
  return null;
};

const setItem = (community, item, endpoint, token) => new Promise((resolve, reject) => {
  const url = `https://api.steampowered.com/IPlayerService/${endpoint}/v1/?access_token=${token}`;
  community.httpRequestPost(url, { form: { communityitemid: item.assetid } }, (err, res) => {
    if (err) return reject(err);
    res.statusCode === 200 ? resolve(item) : reject(new Error(`HTTP ${res.statusCode}`));
  });
});

const setProfileTheme = (community, themeId, token) => new Promise((resolve, reject) => {
  const url = `https://api.steampowered.com/IPlayerService/SetProfileTheme/v1/?access_token=${token}`;
  const body = `input_json=${encodeURIComponent(JSON.stringify({ theme_id: themeId }))}`;
  community.httpRequestPost(url, {
    form: false, body, headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
  }, (err, res) => {
    if (err) return reject(err);
    res.statusCode === 200 ? resolve(themeId) : reject(new Error(`HTTP ${res.statusCode}`));
  });
});

const selectItem = (items, configIds, typeName) => {
  if (!configIds || configIds.length === 0 || configIds[0] === 0) {
    if (items.length === 0) throw new Error(`Нет ${typeName} в инвентаре`);
    return items[Math.floor(Math.random() * items.length)];
  }
  const pool = items.filter(it => {
    const itemId = (it.name.split('-')[0] || it.assetid);
    return configIds.includes(itemId) || configIds.includes(parseInt(itemId));
  });
  if (pool.length === 0) throw new Error(`Нет ${typeName} с ID: ${configIds.join(', ')}`);
  return pool[Math.floor(Math.random() * pool.length)];
};

// ===== Auth =====
async function loginAccount(login, sessionPath, proxy, threadId) {
  let sess;
  try {
    sess = JSON.parse(fs.readFileSync(sessionPath, "utf8"));
  } catch (e) {
    log("ERROR", login, `W${String(threadId).padStart(2,'0')} | Чтение: ${e.message}`);
    return { error: true };
  }
  if (!sess?.DesktopRefreshToken) {
    log("ERROR", login, `W${String(threadId).padStart(2,'0')} | Нет токена`);
    return { error: true };
  }

  const client = new SteamUser({
    webCompatibilityMode: true,
    dataDirectory: null,
    enablePicsCache: false,
    httpProxy: (config.useProxy && proxy) ? proxy : undefined
  });

  try {
    return await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Steam timeout')), 25000);

      client.once("error", err => { clearTimeout(timeout); reject(err); });
      client.once("loggedOn", () => { try { client.setPersona(SteamUser.EPersonaState.Invisible); } catch {} });
      client.once("webSession", (sessionID, cookies) => {
        clearTimeout(timeout);
        if (!client.steamID) {
          try { client.logOff(); } catch {}
          return reject(new Error("steamID не получен"));
        }
        const steamID = client.steamID.getSteamID64();
        const community = makeCommunity(proxy);
        community.setCookies(cookies);
        client.logOff();

        // объединённая старт-строка: START | Wxx | ID: ... | Прокси: ...
        const proxyInfo = proxy ? ` | Прокси: ${hideProxy(proxy)}` : "";
        log("START", login, `W${String(threadId).padStart(2,'0')} | ID: ${C.GR}${hideText(steamID)}${C.R}${proxyInfo}`);

        resolve({ community, steamID, cookies });
      });

      client.logOn({ refreshToken: sess.DesktopRefreshToken });
    });
  } catch (err) {
    log("ERROR", login, `W${String(threadId).padStart(2,'0')} | ${err.message}`);
    try { client.logOff(); } catch {}
    return { error: true };
  }
}

// ===== Profile processing (partial writes) =====
async function processProfile(login, community, steamID, cookies, threadId, doneTypes = new Set()) {
  try {
    const inventory = await loadInventory(community, steamID);
    if (inventory.length === 0) {
      log("WARN", login, `W${String(threadId).padStart(2,'0')} | Пустой инвентарь`);
      return { empty: true };
    }

    const avatars        = findItems(inventory, "item_class_15");
    const frames         = findItems(inventory, "item_class_14");
    const backgrounds    = findItems(inventory, "item_class_3");
    const miniBackgrounds= findItems(inventory, "item_class_13");

    const token = getAccessToken(cookies);
    if (!token) {
      log("ERROR", login, `W${String(threadId).padStart(2,'0')} | Нет access token`);
      return { error: true };
    }

    const results = [];
    let anySuccess = false;

    // helper для единообразной записи и логов
    const ok = (type, id, name, msg) => {
      if (config.logging?.showDetails) log("OK", login, `W${String(threadId).padStart(2,'0')} | ${msg}`);
      results.push(`${type}:${id}`);
      saveCompleted(login, [`${type}:${id}`]); // <-- запись частичного успеха
      anySuccess = true;
    };

    // avatar
    if (config.enabled?.avatar && !doneTypes.has('avatar')) {
      try {
        const item = selectItem(avatars, config.items.avatar.ids, "аватаров");
        const itemId = item.name.split('-')[0] || item.assetid;
        const itemName = item.name.includes('-') ? item.name.split('-').slice(1).join('-') : item.name;
        await setItem(community, item, "SetAnimatedAvatar", token);
        ok('avatar', itemId, itemName, `Аватар   : ${C.LG}${itemId}${C.R} [${C.LG}${itemName}${C.R}]`);
      } catch (e) { log("ERROR", login, `W${String(threadId).padStart(2,'0')} | Ошибка аватара: ${e.message}`); }
    }

    // frame
    if (config.enabled?.frame && !doneTypes.has('frame')) {
      try {
        const item = selectItem(frames, config.items.frame.ids, "рамок");
        const itemId = item.name.split('-')[0] || item.assetid;
        const itemName = item.name.includes('-') ? item.name.split('-').slice(1).join('-') : item.name;
        await setItem(community, item, "SetAvatarFrame", token);
        ok('frame', itemId, itemName, `Рамка    : ${C.LG}${itemId}${C.R} [${C.LG}${itemName}${C.R}]`);
      } catch (e) { log("ERROR", login, `W${String(threadId).padStart(2,'0')} | Ошибка рамки: ${e.message}`); }
    }

    // background
    if (config.enabled?.background && !doneTypes.has('background')) {
      try {
        const item = selectItem(backgrounds, config.items.background.ids, "фонов");
        const itemId = item.name.split('-')[0] || item.assetid;
        const itemName = item.name.includes('-') ? item.name.split('-').slice(1).join('-') : item.name;
        await setItem(community, item, "SetProfileBackground", token);
        ok('background', itemId, itemName, `Фон      : ${C.LG}${itemId}${C.R} [${C.LG}${itemName}${C.R}]`);
      } catch (e) { log("ERROR", login, `W${String(threadId).padStart(2,'0')} | Ошибка фона: ${e.message}`); }
    }

    // miniBackground
    if (config.enabled?.miniBackground && !doneTypes.has('miniBackground')) {
      try {
        const item = selectItem(miniBackgrounds, config.items.miniBackground.ids, "мини-фонов");
        const itemId = item.name.split('-')[0] || item.assetid;
        const itemName = item.name.includes('-') ? item.name.split('-').slice(1).join('-') : item.name;
        await setItem(community, item, "SetMiniProfileBackground", token);
        ok('miniBackground', itemId, itemName, `Мини-фон : ${C.LG}${itemId}${C.R} [${C.LG}${itemName}${C.R}]`);
      } catch (e) { log("ERROR", login, `W${String(threadId).padStart(2,'0')} | Ошибка мини-фона: ${e.message}`); }
    }

    // theme
    if (config.enabled?.theme && !doneTypes.has('theme')) {
      try {
        const list = config.items?.theme?.list || [];
        if (!list.length) throw new Error("Список тем пуст");
        const theme = list[Math.floor(Math.random() * list.length)];
        await setProfileTheme(community, theme, token);
        ok('theme', theme, theme, `Тема     : ${C.LG}${theme}${C.R}`);
      } catch (e) { log("ERROR", login, `W${String(threadId).padStart(2,'0')} | Ошибка темы: ${e.message}`); }
    }

    if (anySuccess) return { success: true, results };
    return { error: true };

  } catch (err) {
    log("ERROR", login, `W${String(threadId).padStart(2,'0')} | Ошибка: ${err.message}`);
    return { error: true };
  }
}

// ===== Orchestration =====
const logProgress = (login, success) => {
  processedCount++;
  if (success) globalStats.success++;
  const remaining = totalFiles - processedCount;
  return remaining;
};

async function loginSafe(login, sessionPath, proxy, threadId, doneTypes) {
  try {
    const loginResult = await withTimeout(
      loginAccount(login, sessionPath, proxy, threadId),
      (config.timeout || 30) * 1000,
      'ACCOUNT_TIMEOUT'
    );
    if (loginResult.error) {
      const remaining = logProgress(login, false);
      globalStats.errors++;
      log("ERROR", login, `W${String(threadId).padStart(2,'0')} | Ошибка входа`);
      log("INFO",  login, `Осталось: ${C.CY}${remaining}${C.R}`);
      return { error: true };
    }

    const { community, steamID, cookies } = loginResult;
    const profileResult = await withTimeout(
      processProfile(login, community, steamID, cookies, threadId, doneTypes),
      (config.timeout || 30) * 1000,
      'PROFILE_TIMEOUT'
    );

    if (profileResult.success) {
      const remaining = logProgress(login, true);
      log("OK",   login, `W${String(threadId).padStart(2,'0')} | Успех: ${profileResult.results.join(', ')}`);
      log("INFO", login, `Осталось: ${C.CY}${remaining}${C.R}`);
      return { success: true };
    } else if (profileResult.empty) {
      const remaining = logProgress(login, false);
      globalStats.empty++;
      log("WARN", login, `W${String(threadId).padStart(2,'0')} | Пустой инвентарь`);
      log("INFO", login, `Осталось: ${C.CY}${remaining}${C.R}`);
      return { empty: true };
    } else {
      const remaining = logProgress(login, false);
      globalStats.errors++;
      log("ERROR", login, `W${String(threadId).padStart(2,'0')} | Не записано из-за ошибки`);
      log("INFO",  login, `Осталось: ${C.CY}${remaining}${C.R}`);
      return { error: true };
    }
  } catch (err) {
    const remaining = logProgress(login, false);
    if (String(err.message).includes('TIMEOUT')) {
      globalStats.timeouts++;
      log("TIMEOUT", login, `W${String(threadId).padStart(2,'0')} | Таймаут ${config.timeout || 30}с`);
      log("INFO",    login, `Осталось: ${C.CY}${remaining}${C.R}`);
      return { timeout: true };
    }
    throw err;
  }
}

async function processThread(files, proxies, fileIndex, threadId, completedMap, needTypes) {
  let processed = 0;
  while (fileIndex.current < files.length) {
    const idx = fileIndex.current++;
    if (idx >= files.length) break;

    const file = files[idx];
    const login = path.basename(file, ".steamsession");
    const sessionPath = path.join(SESSIONS_DIR, file);
    const proxy = (config.useProxy && proxies.length) ? proxies[idx % proxies.length] : null;

    const doneTypes = completedMap.get(login) || new Set();
    // если всё уже сделано — на всякий случай пропустим
    if (needTypes.every(t => doneTypes.has(t))) continue;

    await loginSafe(login, sessionPath, proxy, threadId, doneTypes);
    processed++;
    await sleep(300);
  }
  return { processed };
}

// ===== Main =====
(async () => {
  if (!fs.existsSync(SESSIONS_DIR)) { console.error("Папка ./sessions не найдена"); process.exit(1); }

  const allFiles = fs.readdirSync(SESSIONS_DIR).filter(f => f.endsWith(".steamsession"));
  if (!allFiles.length) { console.log("Нет сессий"); process.exit(0); }

  const completedMap = loadCompleted();
  const proxies = config.useProxy ? loadProxies() : [];
  const needTypes = enabledTypes();

  // к обработке — только не полностью готовые
  const filesToProcess = allFiles.filter(f => {
    const login = path.basename(f, ".steamsession");
    const done = completedMap.get(login) || new Set();
    return !needTypes.every(t => done.has(t));
  });

  totalFiles = filesToProcess.length;
  const fullyDoneCount = allFiles.length - filesToProcess.length;

  showBox([
    `Всего: ${allFiles.length} | Готово: ${fullyDoneCount} | К обработке: ${filesToProcess.length}`,
    `Потоков: ${config.threads} | Таймаут: ${config.timeout || 30}с`,
    `Прокси: ${config.useProxy ? 'Да' : 'Нет'} (${proxies.length})`,
    `Включенные элементы: ${needTypes.join(', ') || 'нет'}`
  ]);

  if (!filesToProcess.length) { console.log("Все аккаунты обработаны!"); process.exit(0); }
  if (!needTypes.length) { console.error("Все элементы отключены в конфигурации!"); process.exit(1); }

  const fileIndex = { current: 0 };
  const threads = [];
  const n = Math.max(1, +config.threads || 1);

  for (let i = 1; i <= n; i++) {
    threads.push(processThread(filesToProcess, proxies, fileIndex, i, completedMap, needTypes));
  }

  await Promise.allSettled(threads);

  showBox([
    `Успешно: ${globalStats.success} | Ошибки: ${globalStats.errors} | Таймауты: ${globalStats.timeouts} | Пустые: ${globalStats.empty}`
  ]);

  process.exit(0);
})();

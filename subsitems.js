/* ========== suppress DEP0040 (punycode) deprecation noise ========== */
process.removeAllListeners('warning');
process.on('warning', (w) => {
  if (w.name === 'DeprecationWarning' && /punycode/.test(w.message)) return;
  console.warn(w.name, w.message);
});
/* =================================================================== */

"use strict";

// === НАСТРОЙКИ ВНЕШНЕГО ВИДА ЛОГОВ ===
const MAX_LOGIN_WIDTH = 20; // Максимальная ширина колонки логинов

const fs = require("fs");
const path = require("path");
const https = require("https");
const querystring = require("querystring");
const SteamUser = require("steam-user");
const SteamCommunity = require("steamcommunity");
const SteamStore = require("steamstore");
const Request = require("request");
const { HttpsProxyAgent } = require("https-proxy-agent");

const PATHS = {
  SESSIONS_DIR: "./sessions",
  SUBS_OK: "./subs_success.txt",
  SUBS_ERR: "./subs_blacklist.txt",
  ITEMS_OK: "./items_success.txt",
  ITEMS_ERR: "./items_blacklist.txt"
};

let config;
try {
  config = JSON.parse(fs.readFileSync("./config.json", "utf8"));
} catch (e) {
  console.error("ERROR: config.json file not found or contains errors!");
  process.exit(1);
}

// Проверяем язык до проверки остальных полей
const lang = config.language || "RU";

const requiredFields = ['subs', 'items', 'enableSubs', 'enableItems', 'proxies', 'threadsPerProxy',
  'delaySubs', 'delayItems', 'delayBetween', 'timeout', 'hideLogins', 'hidePercent', 'ignoreBlacklist'];
for (const field of requiredFields) {
  if (config[field] === undefined) {
    if (lang === "EN") {
      console.error(`ERROR: Required field "${field}" is missing in config.json`);
    } else {
      console.error(`ОШИБКА: Отсутствует обязательное поле "${field}" в config.json`);
    }
    process.exit(1);
  }
}

// Установка языка по умолчанию если не указан
if (!config.language) config.language = "RU";

const AUTH_RETRIES_MAX = 3, AUTH_BACKOFF_BASE_MS = 2000, HTTP_RETRIES_MAX = 2, HTTP_BACKOFF_BASE_MS = 800;
const STARTS_PER_SECOND_LIMIT = 1, PER_PROXY_STAGGER_SEC = 4, REQUEST_FOREVER = false;

const COLORS = {
  RESET: "\x1b[0m", GRAY: "\x1b[90m", RED: "\x1b[91m", GREEN: "\x1b[92m",
  YELLOW: "\x1b[93m", BLUE: "\x1b[94m", CYAN: "\x1b[96m", WHITE: "\x1b[97m"
};

// Локализация
const L_RU = ["Вход выполнен", "Ошибка чтения сессии", "В сессии нет DesktopRefreshToken", "Нет задач", "Задачи", "подписок", "предметов", "Веб-сессия получена", "Активация", "Подписка", "уже есть", "вручную ОК", "ОШИБКА", "Предмет", "получен", "неизвестный ответ", "Ошибка авторизации", "повтор", "через", "Получение", "Не удалось извлечь токен", "Обработка завершена", "Нет сессий в ./sessions", "Предметы", "шт", "Игры", "Найдено сессий", "Отсеяно", "К обработке", "Готово: все аккаунты уже прошли норму.", "Поток", "Прокси", "СТАТИСТИКА", "Подписки", "добавлено", "ошибки", "Обработано аккаунтов", "Время выполнения", "Необработанная ошибка", "ОК"];

const L_EN = ["Logged in", "Session read error", "No DesktopRefreshToken in session", "No tasks", "Tasks", "Subs", "Items", "Get Web session", "Activating", "Subscription", "already owned", "manual OK", "ERROR", "Item", "received", "unknown response", "Auth error", "retry", "in", "Getting", "Failed to extract token", "Processing completed", "No sessions in ./sessions", "Items", "pcs", "Games", "Sessions found", "Filtered", "To process", "Done: all accounts have already reached the norm.", "Thread", "Proxy", "STATISTICS", "Subscriptions", "added", "errors", "Accounts processed", "Execution time", "Unhandled error", "OK"];

// Выбор языка
const L = config.language === "EN" ? L_EN : L_RU;

const now = () => new Date().toTimeString().split(" ")[0];
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

let loginWidth = 10;

const hideLogin = (login) => {
  let name = login;
  if (config.hideLogins && login.length > 2) {
    const p = Math.max(1, Math.floor(login.length * (config.hidePercent / 100)));
    name = login.slice(0, p) + "*".repeat(Math.max(0, login.length - p * 2)) + login.slice(-p);
  }
  if (name.length > MAX_LOGIN_WIDTH) name = name.slice(0, MAX_LOGIN_WIDTH - 1) + "…";
  return name.padEnd(loginWidth, " ");
};

const hideProxy = (url) => {
  if (!url) return config.language === "EN" ? "none" : "нет";
  try {
    const u = new URL(url);
    const proxy = `${u.hostname}:${u.port}`;
    if (config.hideLogins) {
      const parts = proxy.split(':');
      if (parts.length === 2) {
        const ip = parts[0];
        const port = parts[1];
        const ipParts = ip.split('.');
        if (ipParts.length === 4) {
          return `${ipParts[0]}.${ipParts[1]}.***.***.${port}`;
        }
      }
      return "***.***.***:****";
    }
    return proxy;
  } catch {
    return config.language === "EN" ? "unknown" : "неизвестно";
  }
};

const loadLog = (file) => {
  const data = {};
  if (fs.existsSync(file)) {
    fs.readFileSync(file, "utf8").split("\n").filter(Boolean).forEach(line => {
      const [login, ...items] = line.split(":");
      if (login && items.length) data[login] = items.map(Number);
    });
  }
  return data;
};

const saveLog = (file, login, id) => {
  const data = loadLog(file);
  if (!data[login]) data[login] = [];
  if (!data[login].includes(id)) data[login].push(id);
  const lines = Object.entries(data).map(([l, ids]) => `${l}:${ids.join(":")}`);
  fs.writeFileSync(file, lines.join("\n") + "\n");
};

class ProxyPool {
  constructor(urls, limitPerProxy) {
    this.urls = (urls && urls.length) ? urls : [null];
    this.limit = Math.max(1, limitPerProxy || 1);
    this.busy = Array(this.urls.length).fill(0);
  }

  acquire() {
    let bestIdx = -1, bestLoad = Infinity;
    for (let i = 0; i < this.urls.length; i++) {
      if (this.busy[i] < this.limit && this.busy[i] < bestLoad) {
        bestLoad = this.busy[i];
        bestIdx = i;
        if (bestLoad === 0) break;
      }
    }
    if (bestIdx === -1) return null;

    this.busy[bestIdx]++;
    const slot = this.busy[bestIdx] - 1;
    const url = this.urls[bestIdx] || null;
    return { idx: bestIdx, url, slot };
  }

  release(i) {
    if (i >= 0 && this.busy[i] > 0) this.busy[i]--;
  }
}

class RateLimiter {
  constructor(perSecond) {
    this.minInterval = Math.max(50, Math.floor(1000 / Math.max(1, perSecond)));
    this._next = 0;
  }

  async waitTurn() {
    const nowTs = Date.now();
    const ts = Math.max(this._next, nowTs);
    const wait = ts - nowTs;
    this._next = ts + this.minInterval;
    if (wait > 0) await sleep(wait);
  }
}

const isRetriableNetErr = (err) => {
  if (!err) return false;
  const msg = String(err.message || err);
  return /ETIMEDOUT|ECONNRESET|EAI_AGAIN|ENETUNREACH|EHOSTUNREACH|Proxy connection timed out/i.test(msg);
};

const makeCommunity = (lease) => {
  const opts = { timeout: config.timeout || 40000, forever: REQUEST_FOREVER, pool: { maxSockets: 32 } };
  if (lease?.url) opts.proxy = lease.url;
  return new SteamCommunity({ request: Request.defaults(opts) });
};

const makeStore = (lease) => {
  const opts = { timeout: config.timeout || 40000, forever: REQUEST_FOREVER, pool: { maxSockets: 32 }, gzip: true };
  if (lease?.url) opts.proxy = lease.url;
  return new SteamStore({ request: Request.defaults(opts) });
};

// Оптимизированное логирование
const log = (level, login, text) => {
  const lvl = (level || "LOG").toUpperCase().padEnd(5, ' ');
  const lvlColor = level === "OK" ? COLORS.GREEN : level === "WARN" ? COLORS.YELLOW : level === "ERROR" ? COLORS.RED : level === "INFO" ? COLORS.CYAN : COLORS.GRAY;

  let msg = text;
  // Подсветка чисел для обоих языков
  if (text.includes(L[9]) || text.includes(L[13])) {
    msg = text.replace(/\b\d+\b/g, (n) => `${COLORS.WHITE}${n}${COLORS.RESET}`);
  }
  // Подсветка ошибок и "уже есть"
  msg = msg.replace(new RegExp(`${L[12]}:`, 'g'), `${COLORS.YELLOW}${L[12]}:${COLORS.RESET}`)
    .replace(new RegExp(L[10], 'g'), `${COLORS.YELLOW}${L[10]}${COLORS.RESET}`);

  console.log(`${now()} | ${lvlColor}${lvl}${COLORS.RESET} | ${hideLogin(login)} | ${COLORS.GRAY}${msg}${COLORS.RESET}`);
};

const loginOnce = async ({ login, sess, lease }) => {
  const client = new SteamUser({
    webCompatibilityMode: true,
    httpProxy: lease?.url || undefined,
    dataDirectory: null,
    enablePicsCache: false
  });

  try {
    const { sessionID, cookies } = await new Promise((resolve, reject) => {
      const onError = (err) => reject(err);
      client.once("error", onError);

      client.once("loggedOn", () => {
        try { client.setPersona(SteamUser.EPersonaState.Invisible); } catch { }
        const steamId = client.steamID.getSteamID64();
        const hiddenId = config.hideLogins ? steamId.slice(0, 6) + "***" + steamId.slice(-4) : steamId;
        log("INFO", login, `${L[0]} | ID: ${COLORS.CYAN}${hiddenId}${COLORS.RESET}`);
      });

      client.once("webSession", (sessionID, cookies) => {
        client.removeListener("error", onError);
        resolve({ sessionID, cookies });
      });

      client.logOn({ refreshToken: sess.DesktopRefreshToken });
    });

    return { client, sessionID, cookies };
  } catch (err) {
    try { client.logOff(); } catch { }
    throw err;
  }
};

const loginWithRetry = async ({ login, sess, lease }) => {
  let attempt = 0;
  while (attempt < AUTH_RETRIES_MAX) {
    attempt++;
    try {
      return await loginOnce({ login, sess, lease });
    } catch (err) {
      const retriable = isRetriableNetErr(err);
      log("ERROR", login, `${L[16]}: ${err.message || err}${retriable && attempt < AUTH_RETRIES_MAX ? ` — ${L[17]} ${attempt}/${AUTH_RETRIES_MAX}` : ''}`);
      if (!retriable || attempt >= AUTH_RETRIES_MAX) return null;
      await sleep(AUTH_BACKOFF_BASE_MS * Math.pow(2, attempt - 1));
    }
  }
  return null;
};

const extractToken = (cookies) => {
  for (const c of cookies) {
    if (c.includes('steamLoginSecure=')) {
      const m = c.match(/steamLoginSecure=([^;]+)/);
      if (m) {
        const [steamId, token] = decodeURIComponent(m[1]).split('||');
        if (steamId && token) return { steamId, token };
      }
    }
  }
  return null;
};

const redeemPoints = async (loginData, itemId, agent) => {
  const post = querystring.stringify({ access_token: loginData.token, defid: itemId });
  const options = {
    hostname: 'api.steampowered.com', port: 443, path: '/ILoyaltyRewardsService/RedeemPoints/v1/',
    method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'Content-Length': Buffer.byteLength(post) },
    agent: agent
  };

  return new Promise((res, rej) => {
    const req = https.request(options, (resp) => {
      let data = '';
      resp.on('data', chunk => data += chunk);
      resp.on('end', () => res({ ok: resp.statusCode === 200, code: resp.statusCode, data }));
    });

    req.setTimeout(config.timeout || 40000, () => {
      req.destroy(new Error('Request timed out'));
    });

    req.on('error', rej);
    req.write(post);
    req.end();
  });
};


const manual = async (community, sid, sub) => {
  return new Promise((res, rej) => {
    community.httpRequestPost("https://store.steampowered.com/checkout/addfreelicense", {
      form: { sessionid: sid, subid: sub, action: "add_to_cart" }, json: true
    }, (e) => e ? rej(e) : res());
  });
};

const processSubWithRetry = async (store, community, sessionID, sub, login, i, total) => {
  let attempt = 0;
  while (true) {
    try {
      await store.addFreeLicense(sub);
      log("OK", login, `${L[9]} ${sub} ${L[39]} (${i + 1}/${total})`);
      return { success: true, type: 'normal' };
    } catch (e) {
      if (e?.eresult === 9) {
        log("INFO", login, `${L[9]} ${sub} ${L[10]} (${i + 1}/${total})`);
        return { success: true, type: 'exists' };
      }

      attempt++;
      const retriable = isRetriableNetErr(e);
      if (!retriable || attempt > HTTP_RETRIES_MAX) {
        try {
          await manual(community, sessionID, sub);
          log("OK", login, `${L[9]} ${sub} ${L[11]} (${i + 1}/${total})`);
          return { success: true, type: 'manual' };
        } catch (er) {
          const isNet = isRetriableNetErr(er);
          log(isNet ? "WARN" : "ERROR", login, `${L[9]} ${sub} ${L[12]}: ${er.message} (${i + 1}/${total})`);
          return { success: false, isNetwork: isNet, error: er.message };
        }
      }

      const backoff = HTTP_BACKOFF_BASE_MS * Math.pow(2, attempt - 1);
      log("WARN", login, `HTTP ${L[12].toLowerCase()} ${L[9].toLowerCase()} ${sub}: ${e.message || e} — ${L[17]} ${attempt}/${HTTP_RETRIES_MAX} ${L[18]} ${backoff}ms (${i + 1}/${total})`);
      await sleep(backoff);
    }
  }
};

const processItemWithRetry = async (loginData, item, agent, login, i, total) => {
  let attempt = 0;
  while (true) {
    try {
      const result = await redeemPoints(loginData, item, agent);

      if (result.ok) {
        try {
          const resp = JSON.parse(result.data);
          if (resp.response?.communityitemid) {
            // Обычный предмет
            log("OK", login, `${L[13]} ${item} ${L[14]} (${i + 1}/${total})`);
            return { success: true, type: 'normal' };

          } else if (Array.isArray(resp.response?.bundle_community_item_ids)) {
            // Бандл — несколько предметов
            const ids = resp.response.bundle_community_item_ids;
            const count = ids.length;
            log("OK", login, `${L[13]} ${item} ${L[14]} — бандл (${count} шт): ${ids.join(", ")} (${i + 1}/${total})`);
            return { success: true, type: 'bundle', bundleIds: ids };

          } else {
            // Уже получен
            log("INFO", login, `${L[13]} ${item} ${L[10]} (${i + 1}/${total})`);
            return { success: true, type: 'exists' };
          }
        } catch {
          log("ERROR", login, `${L[13]} ${item} ${L[15]} (${i + 1}/${total})`);
          return { success: false, error: L[15] };
        }
      } else {
        log("ERROR", login, `${L[13]} ${item} HTTP ${result.code} (${i + 1}/${total})`);
        return { success: false, error: `HTTP ${result.code}` };
      }
    } catch (e) {
      attempt++;
      const retriable = isRetriableNetErr(e);
      if (!retriable || attempt > HTTP_RETRIES_MAX) {
        log("ERROR", login, `${L[13]} ${item} ${L[12]}: ${e.message} (${i + 1}/${total})`);
        return { success: false, error: e.message };
      }

      const backoff = HTTP_BACKOFF_BASE_MS * Math.pow(2, attempt - 1);
      log("WARN", login, `HTTP ${L[12].toLowerCase()} ${L[13].toLowerCase()} ${item}: ${e.message || e} — ${L[17]} ${attempt}/${HTTP_RETRIES_MAX} ${L[18]} ${backoff}ms (${i + 1}/${total})`);
      await sleep(backoff);
    }
  }
};

const processAccount = async ({ login, sessionPath, lease }) => {
  let sess;
  try {
    sess = JSON.parse(fs.readFileSync(sessionPath, "utf8"));
  } catch (e) {
    log("ERROR", login, `${L[1]}: ${e.message}`);
    return;
  }

  if (!sess?.DesktopRefreshToken) {
    log("ERROR", login, L[2]);
    return;
  }

  if (lease && Number.isFinite(lease.slot) && lease.slot > 0) {
    await sleep(lease.slot * PER_PROXY_STAGGER_SEC * 1000);
  }

  const subsOk = loadLog(PATHS.SUBS_OK)[login] || [];
  const subsErr = loadLog(PATHS.SUBS_ERR)[login] || [];
  const itemsOk = loadLog(PATHS.ITEMS_OK)[login] || [];
  const itemsErr = loadLog(PATHS.ITEMS_ERR)[login] || [];

  const subsToGo = config.enableSubs ? config.subs.filter(s => !subsOk.includes(s) && (config.ignoreBlacklist || !subsErr.includes(s))) : [];
  const itemsToGo = config.enableItems ? config.items.filter(i => !itemsOk.includes(i) && (config.ignoreBlacklist || !itemsErr.includes(i))) : [];

  if (!subsToGo.length && !itemsToGo.length) {
    log("INFO", login, L[3]);
    return;
  }

  log("INFO", login, `${L[4]}: ${subsToGo.length} ${L[5]}, ${itemsToGo.length} ${L[6]}`);

  const auth = await loginWithRetry({ login, sess, lease });
  if (!auth) return;

  const { client, sessionID, cookies } = auth;
  const community = makeCommunity(lease);
  const store = makeStore(lease);

  community.setCookies(cookies);
  store.setCookies(cookies);

  log("OK", login, L[7]);

  try { client.logOff(); } catch { }
  await sleep(100);

  const stats = { subsOk: 0, subsExists: 0, subsManual: 0, subsFail: 0, itemsOk: 0, itemsExists: 0, itemsFail: 0 };

  if (subsToGo.length) {
    log("INFO", login, `${L[8]} ${subsToGo.length} ${L[5]}`);

    for (let i = 0; i < subsToGo.length; i++) {
      const sub = subsToGo[i];
      const result = await processSubWithRetry(store, community, sessionID, sub, login, i, subsToGo.length);

      if (result.success) {
        if (result.type === 'exists') stats.subsExists++;
        else if (result.type === 'manual') stats.subsManual++;
        else stats.subsOk++;
        saveLog(PATHS.SUBS_OK, login, sub);
      } else {
        stats.subsFail++;
        if (!result.isNetwork) saveLog(PATHS.SUBS_ERR, login, sub);
      }

      if (i < subsToGo.length - 1) await sleep(config.delaySubs);
    }
  }

  if (subsToGo.length && itemsToGo.length) await sleep(config.delayBetween);

  if (itemsToGo.length) {
    const loginData = extractToken(cookies);
    if (!loginData) {
      log("ERROR", login, L[20]);
    } else {
      log("INFO", login, `${L[19]} ${itemsToGo.length} ${L[6]}`);
      const agent = lease?.url ? new HttpsProxyAgent(lease.url) : null;

      for (let i = 0; i < itemsToGo.length; i++) {
        const item = itemsToGo[i];
        const result = await processItemWithRetry(loginData, item, agent, login, i, itemsToGo.length);

        if (result.success) {
          if (result.type === 'exists') stats.itemsExists++;
          else stats.itemsOk++;
          saveLog(PATHS.ITEMS_OK, login, item);
        } else {
          stats.itemsFail++;
          saveLog(PATHS.ITEMS_ERR, login, item);
        }

        if (i < itemsToGo.length - 1) await sleep(config.delayItems);
      }
    }
  }

  log("OK", login, L[21]);
  return stats;
};

(async () => {
  const files = fs.existsSync(PATHS.SESSIONS_DIR) ? fs.readdirSync(PATHS.SESSIONS_DIR).filter(f => f.endsWith(".steamsession")) : [];

  if (!files.length) {
    console.log(L[22]);
    process.exit(0);
  }

  const subsOk = loadLog(PATHS.SUBS_OK), subsErr = loadLog(PATHS.SUBS_ERR);
  const itemsOk = loadLog(PATHS.ITEMS_OK), itemsErr = loadLog(PATHS.ITEMS_ERR);

  const toProcess = files.filter(file => {
    const login = path.basename(file, ".steamsession");
    let needWork = false;

    if (config.enableSubs) {
      const done = subsOk[login] || [], blocked = subsErr[login] || [];
      needWork = config.subs.some(s => !done.includes(s) && (config.ignoreBlacklist || !blocked.includes(s)));
    }

    if (!needWork && config.enableItems) {
      const done = itemsOk[login] || [], blocked = itemsErr[login] || [];
      needWork = config.items.some(i => !done.includes(i) && (config.ignoreBlacklist || !blocked.includes(i)));
    }

    return needWork;
  });

  if (toProcess.length > 0) {
    const maxLoginLength = toProcess.reduce((max, file) => {
      const login = path.basename(file, ".steamsession");
      let displayName = login;
      if (config.hideLogins && login.length > 2) {
        const p = Math.max(1, Math.floor(login.length * (config.hidePercent / 100)));
        displayName = login.slice(0, p) + "*".repeat(Math.max(0, login.length - p * 2)) + login.slice(-p);
      }
      const len = Math.min(displayName.length, MAX_LOGIN_WIDTH);
      return Math.max(max, len);
    }, 0);
    loginWidth = Math.max(10, Math.min(maxLoginLength, MAX_LOGIN_WIDTH));
  }

  const headerLines = [], plainLines = [];

  if (config.enableItems && config.items.length > 0) {
    headerLines.push(`${L[23]} [${config.items.length} ${L[24]}]: ${COLORS.WHITE}${config.items.join(", ")}${COLORS.GRAY}`);
    plainLines.push(`${L[23]} [${config.items.length} ${L[24]}]: ${config.items.join(", ")}`);
  }

  if (config.enableSubs && config.subs.length > 0) {
    headerLines.push(`${L[25]}${" ".repeat(Math.max(0, L[23].length - L[25].length))} [${config.subs.length} ${L[24]}]: ${COLORS.WHITE}${config.subs.join(", ")}${COLORS.GRAY}`);
    plainLines.push(`${L[25]}${" ".repeat(Math.max(0, L[23].length - L[25].length))} [${config.subs.length} ${L[24]}]: ${config.subs.join(", ")}`);
  }

  const statsLine = `${L[26]}: ${files.length} | ${L[27]}: ${files.length - toProcess.length} | ${L[28]}: ${toProcess.length}`;
  headerLines.push(`${L[26]}: ${COLORS.CYAN}${files.length}${COLORS.GRAY} | ${L[27]}: ${COLORS.YELLOW}${files.length - toProcess.length}${COLORS.GRAY} | ${L[28]}: ${COLORS.GREEN}${toProcess.length}${COLORS.GRAY}`);
  plainLines.push(statsLine);

  const maxWidth = Math.max(...plainLines.map(line => line.length));
  const title = " Steam Free Collector ";
  const titlePadding = Math.max(0, Math.floor((maxWidth - title.length) / 2));
  const separatorWidth = Math.max(maxWidth, title.length + titlePadding * 2);

  console.log(`${COLORS.GRAY}${"=".repeat(titlePadding)}${COLORS.CYAN}${title}${COLORS.GRAY}${"=".repeat(separatorWidth - titlePadding - title.length)}${COLORS.RESET}`);
  headerLines.forEach(line => console.log(`${COLORS.GRAY}${line}${COLORS.RESET}`));
  console.log(`${COLORS.GRAY}${"=".repeat(separatorWidth)}${COLORS.RESET}`);

  if (!toProcess.length) {
    console.log(L[29]);
    process.exit(0);
  }

  const pool = new ProxyPool(config.proxies || [], config.threadsPerProxy || 1);
  const GLOBAL_CONCURRENCY = Math.max(1, (config.proxies?.length || 1) * (config.threadsPerProxy || 1));
  const limiter = new RateLimiter(STARTS_PER_SECOND_LIMIT);

  const totals = { subsOk: 0, subsExists: 0, subsManual: 0, subsFail: 0, itemsOk: 0, itemsExists: 0, itemsFail: 0 };

  let active = 0, cursor = 0, completed = 0;
  const start = Date.now();

  const runNext = async () => {
    while (active < GLOBAL_CONCURRENCY && cursor < toProcess.length) {
      const lease = pool.acquire();
      if (!lease) break;

      await limiter.waitTurn();

      const file = toProcess[cursor];
      cursor++;
      if (!file) break;

      const login = path.basename(file, ".steamsession");
      const sessionPath = path.join(PATHS.SESSIONS_DIR, file);

      active++;
      console.log(`${now()} | ${COLORS.GRAY}START${COLORS.RESET} | ${hideLogin(login)} | ${L[30]}: ${lease.slot + 1}/${pool.limit} | ${L[31]}: ${hideProxy(lease?.url)}`);

      processAccount({ login, sessionPath, lease })
        .then((stats) => {
          if (stats) Object.keys(totals).forEach(key => totals[key] += stats[key] || 0);
        })
        .catch((e) => log("ERROR", login, `${L[38]}: ${e?.message || e}`))
        .finally(async () => {
          pool.release(lease.idx);
          active--;
          completed++;

          console.log(`${now()} | ${COLORS.GRAY}EXIT${COLORS.RESET}  | ${hideLogin(login)} | ${COLORS.CYAN}[${completed}/${toProcess.length}]${COLORS.RESET}`);

          if (completed === toProcess.length) {
            const elapsed = ((Date.now() - start) / 1000).toFixed(1);
            const title = ` ${L[32]} `;
            const titlePadding = Math.max(0, Math.floor((maxWidth - title.length) / 2));

            console.log(`${"=".repeat(titlePadding)}${title}${"=".repeat(separatorWidth - titlePadding - title.length)}`);

            if (config.enableSubs) {
              const subsSuccess = totals.subsOk + totals.subsExists + totals.subsManual;
              console.log(`${L[33]}: ${L[34]} ${subsSuccess} | ${L[35]} ${totals.subsFail}`);
            }

            if (config.enableItems) {
              const itemsSuccess = totals.itemsOk + totals.itemsExists;
              console.log(`${L[23]}: ${L[34]} ${itemsSuccess} | ${L[35]} ${totals.itemsFail}`);
            }

            console.log(`${L[36]}: ${completed}`);
            console.log(`${L[37]}: ${elapsed}${config.language === "EN" ? "s" : "с"}`);
            console.log(`${"=".repeat(separatorWidth)}`);

            process.exit(0);
          }

          setImmediate(runNext);
        });
    }
  };

  runNext();
})();
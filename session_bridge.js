// session_bridge.js — адаптер для работы с куками из Python-базы (без .steamsession)
// Запуск: node session_bridge.js <task> <args_json>
// task: cosmetics | info | badge

"use strict";

process.removeAllListeners('warning');
process.on('warning', w => {
  if (w.name === 'DeprecationWarning' && /punycode/.test(w.message)) return;
  console.warn(w.name, w.message);
});

const fs      = require("fs");
const path    = require("path");
const SteamCommunity = require("steamcommunity");
const Request = require("request");

const task = process.argv[2] || "";
let args;
try { args = JSON.parse(process.argv[3] || "{}"); }
catch (e) { console.error("JSON parse error:", e.message); process.exit(1); }

const { login, steamid64, cookies: cookiesList, config: cfg } = args;
if (!login || !steamid64 || !cookiesList) {
  console.error("Нужны поля: login, steamid64, cookies"); process.exit(1);
}

const now   = () => new Date().toTimeString().split(" ")[0];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const log   = (level, text) => {
  const colors = { OK:"\x1b[92m", WARN:"\x1b[93m", ERROR:"\x1b[91m", INFO:"\x1b[97m", START:"\x1b[96m" };
  console.log(`${now()} | \x1b[37m${String(login).padEnd(15)}\x1b[0m | ${(colors[level]||"\x1b[37m")}${String(level).padEnd(5)}\x1b[0m | \x1b[90m${text}\x1b[0m`);
};

function convertCookies(list) {
  return list.map(c => {
    let s = `${c.name}=${c.value}`;
    if (c.domain) s += `; Domain=${c.domain}`;
    if (c.path)   s += `; Path=${c.path}`;
    return s;
  });
}
function getAccessToken(list) {
  for (const c of list) {
    if (c.name === "steamLoginSecure") {
      try { const p = decodeURIComponent(c.value).split("||"); if (p.length>=2) return p[1]; } catch {}
    }
  }
  return null;
}
function makeCommunity() {
  const timeout = (cfg.timeout || 30) * 1000;
  const community = new SteamCommunity({ request: Request.defaults({ timeout }) });
  community.setCookies(convertCookies(cookiesList));
  return community;
}

// ids: [0]=случайный, [id]=конкретный, [id1,id2]=случайный из списка
function selectItem(items, ids) {
  if (!items.length) return null;
  if (!ids || !ids.length || (ids.length===1 && ids[0]===0))
    return items[Math.floor(Math.random()*items.length)];
  const pool = items.filter(it => {
    const id = parseInt((it.market_hash_name||it.name||"").split("-")[0]) || parseInt(it.assetid);
    return ids.includes(id);
  });
  if (!pool.length) { log("WARN",`ID [${ids.join(",")}] не найдены — берём случайный`); return items[Math.floor(Math.random()*items.length)]; }
  return pool[Math.floor(Math.random()*pool.length)];
}

// ══════════════════════════════════════════════════════════════
// COSMETICS
// ══════════════════════════════════════════════════════════════
async function runCosmetics() {
  const community = makeCommunity();
  const token = getAccessToken(cookiesList);
  if (!token) { log("ERROR","Нет access_token"); process.exit(1); }
  log("START", `SteamID64: ${steamid64}`);

  const inventory = await new Promise((res,rej) =>
    community.getUserInventory(steamid64, 753, 6, false, (err,items) => err?rej(err):res(items||[]))
  );
  log("INFO", `Инвентарь: ${inventory.length} предметов`);
  if (!inventory.length) { log("WARN","Инвентарь пуст"); return; }

  const findByClass = id => inventory.filter(it => (it.tags||[]).some(t=>t.category==="item_class"&&t.internal_name===id));

  const setItem = (item, endpoint) => new Promise((res,rej) => {
    const url = `https://api.steampowered.com/IPlayerService/${endpoint}/v1/?access_token=${token}`;
    community.httpRequestPost(url,{form:{communityitemid:item.assetid}},(err,r)=>
      err?rej(err):(r.statusCode===200?res():rej(new Error(`HTTP ${r.statusCode}`)))
    );
  });
  const setTheme = themeId => new Promise((res,rej) => {
    const url = `https://api.steampowered.com/IPlayerService/SetProfileTheme/v1/?access_token=${token}`;
    const body = `input_json=${encodeURIComponent(JSON.stringify({theme_id:themeId}))}`;
    community.httpRequestPost(url,{form:false,body,headers:{"Content-Type":"application/x-www-form-urlencoded"}},
      (err,r)=>err?rej(err):(r.statusCode===200?res():rej(new Error(`HTTP ${r.statusCode}`)))
    );
  });

  const en = cfg.enabled || {};
  const it = cfg.items   || {};

  if (en.avatar) {
    const item = selectItem(findByClass("item_class_15"), it.avatar?.ids);
    if (item) { try { await setItem(item,"SetAnimatedAvatar"); log("OK",`Аватар: ${item.market_hash_name||item.name}`); } catch(e){log("ERROR",`Аватар: ${e.message}`);} }
    else log("WARN","Нет анимированных аватаров");
  }
  if (en.frame) {
    const item = selectItem(findByClass("item_class_14"), it.frame?.ids);
    if (item) { try { await setItem(item,"SetAvatarFrame"); log("OK",`Рамка: ${item.market_hash_name||item.name}`); } catch(e){log("ERROR",`Рамка: ${e.message}`);} }
    else log("WARN","Нет рамок");
  }
  if (en.background) {
    const item = selectItem(findByClass("item_class_3"), it.background?.ids);
    if (item) { try { await setItem(item,"SetProfileBackground"); log("OK",`Фон: ${item.market_hash_name||item.name}`); } catch(e){log("ERROR",`Фон: ${e.message}`);} }
    else log("WARN","Нет фонов");
  }
  if (en.miniBackground) {
    const item = selectItem(findByClass("item_class_13"), it.miniBackground?.ids);
    if (item) { try { await setItem(item,"SetMiniProfileBackground"); log("OK",`Мини-фон: ${item.market_hash_name||item.name}`); } catch(e){log("ERROR",`Мини-фон: ${e.message}`);} }
    else log("WARN","Нет мини-фонов");
  }
  if (en.theme) {
    const list = it.theme?.list || [];
    if (!list.length) log("WARN","Список тем пуст");
    else {
      const theme = list[Math.floor(Math.random()*list.length)];
      try { await setTheme(theme); log("OK",`Тема: ${theme}`); } catch(e){log("ERROR",`Тема: ${e.message}`);}
    }
  }
  log("OK","Косметика готова");
}

// ══════════════════════════════════════════════════════════════
// INFO  (читает файлы никнеймов/стран с диска)
// ══════════════════════════════════════════════════════════════
async function runInfo() {
  const community = makeCommunity();
  log("START", `SteamID64: ${steamid64}`);

  const profile = cfg.profile || {};
  const scriptDir = path.dirname(process.argv[1]);

  const loadLines = fp => {
    const full = path.isAbsolute(fp) ? fp : path.join(scriptDir, fp);
    if (!fs.existsSync(full)) { log("WARN",`Файл не найден: ${full}`); return []; }
    return fs.readFileSync(full,"utf8").split("\n").map(l=>l.trim()).filter(Boolean);
  };
  const loadCountries = fp => {
    const result = [];
    for (const line of loadLines(fp)) {
      const [country,state,cities] = line.split(":");
      if (!cities) continue;
      for (const city of cities.split(","))
        result.push({country:country.trim(), state:state?.trim()||"", city:city.trim()});
    }
    return result;
  };
  const pick = arr => arr.length ? arr[Math.floor(Math.random()*arr.length)] : null;

  const nicknames = profile.nickname  ? loadLines(profile.nickNames || "./resources/overwatch_nicknames.txt") : [];
  const realNames = (profile.realName && profile.realNameMode!=="same")
    ? loadLines(profile.realNames || "./resources/overwatch_nicknames.txt") : [];
  let countries = profile.country ? loadCountries(profile.countries || "./resources/country_ids_converted.txt") : [];
  if (countries.length && profile.allowedCountries?.length)
    countries = countries.filter(c => profile.allowedCountries.includes(c.country));

  const generateURL = base => {
    const s = profile.customURLSettings || {};
    let url = base;
    const dMin=s.minDigits??1, dMax=s.maxDigits??2;
    const sMin=s.minSpecials??0, sMax=s.maxSpecials??1;
    const specs = Array.isArray(s.allowedSpecials)?s.allowedSpecials.filter(Boolean):[];
    const dc = dMin + Math.floor(Math.random()*(dMax-dMin+1));
    for (let i=0;i<dc;i++) {
      const d=(Math.floor(Math.random()*9)+1).toString();
      const pos=Math.floor(Math.random()*(url.length+1));
      url=url.slice(0,pos)+d+url.slice(pos);
    }
    if (specs.length) {
      const sc = sMin + Math.floor(Math.random()*(sMax-sMin+1));
      for (let i=0;i<sc;i++) {
        const sp=specs[Math.floor(Math.random()*specs.length)];
        const pos=Math.floor(Math.random()*(url.length+1));
        url=url.slice(0,pos)+sp+url.slice(pos);
      }
      while(specs.some(sp=>url.startsWith(sp))) url=url.slice(1);
      while(specs.some(sp=>url.endsWith(sp)))   url=url.slice(0,-1);
    }
    return url;
  };

  const pd = {};
  let nickname = null;

  if (profile.nickname && nicknames.length) { nickname=pick(nicknames); pd.name=nickname; }
  if (profile.realName) {
    if (profile.realNameMode==="same" && nickname) pd.realName=nickname;
    else if (realNames.length) pd.realName=pick(realNames);
  }
  if (profile.country && countries.length) {
    const loc=pick(countries);
    pd.country=loc.country;
    if (loc.state) pd.state=loc.state;
    if (loc.city)  pd.city=loc.city;
  }
  if (profile.customURL) {
    const base = nickname || pick(nicknames);
    if (base && /^[A-Za-z0-9_]+$/.test(base)) pd.customURL=generateURL(base);
    else log("WARN","Пропуск customURL — недопустимые символы в никнейме");
  }

  if (!Object.keys(pd).length) { log("WARN","Нет данных для обновления"); return; }

  log("INFO", Object.entries(pd).map(([k,v])=>`${k}: ${v}`).join(" | "));

  await new Promise((res,rej) => community.editProfile(pd, err => err?rej(err):res()));
  log("OK","Профиль обновлён");
}

// ══════════════════════════════════════════════════════════════
// BADGE
// ══════════════════════════════════════════════════════════════
async function runBadge() {
  const community = makeCommunity();
  const token = getAccessToken(cookiesList);
  if (!token) { log("ERROR","Нет access_token"); process.exit(1); }
  log("START", `SteamID64: ${steamid64}`);

  const badges = await new Promise((res,rej) => {
    const cheerio = require("cheerio");
    community.httpRequestGet(`https://steamcommunity.com/profiles/${steamid64}/badges/?l=english`,{},(err,resp,body)=>{
      if (err) return rej(err);
      const $=cheerio.load(body), result=[];
      $(".badge_row").each(function(){
        const link=$(this).find(".badge_row_overlay").attr("href")||"";
        const gm=link.match(/\/gamecards\/(\d+)/), sm=link.match(/\/badges?\/(\d+)/);
        if (!gm&&!sm) return;
        const name=$(this).find(".badge_title").clone().children().remove().end().text().trim();
        const hasIcon=$(this).find(".badge_icon").length>0;
        const lm=$(this).find(".badge_info_description").text().match(/Level (\d+)/);
        const level=lm?parseInt(lm[1]):(hasIcon?1:0);
        if (level>0&&hasIcon) result.push({name,id:gm?gm[1]:sm[1]});
      });
      res(result);
    });
  });

  log("INFO",`Значков: ${badges.length}${badges.length?" ["+badges.map(b=>b.id).join(", ")+"]":""}`);
  if (!badges.length) { log("WARN","Нет значков"); return; }

  const bc=cfg.badge||{random:true,ids:[]};
  let selected=null;
  if (bc.random) selected=badges[Math.floor(Math.random()*badges.length)];
  else if (bc.ids?.length) {
    const pool=badges.filter(b=>bc.ids.includes(parseInt(b.id)));
    if (pool.length) selected=pool[Math.floor(Math.random()*pool.length)];
    else log("WARN",`ID [${bc.ids.join(",")}] не найдены`);
  }
  if (!selected) { log("WARN","Нет подходящего значка"); return; }

  await new Promise((res,rej)=>{
    const url=`https://api.steampowered.com/IPlayerService/SetFavoriteBadge/v1/?access_token=${token}`;
    community.httpRequestPost(url,{form:{badgeid:selected.id}},(err,r)=>
      err?rej(err):(r.statusCode===200?res():rej(new Error(`HTTP ${r.statusCode}`)))
    );
  });
  log("OK",`Значок: ${selected.name} (ID: ${selected.id})`);
}

// ══════════════════════════════════════════════════════════════
(async()=>{
  try {
    if      (task==="cosmetics") await runCosmetics();
    else if (task==="info")      await runInfo();
    else if (task==="badge")     await runBadge();
    else { console.error(`Неизвестный task: ${task}`); process.exit(1); }
    process.exit(0);
  } catch(err) {
    console.error(`\x1b[91mFATAL: ${err.message}\x1b[0m`);
    process.exit(1);
  }
})();

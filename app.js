/* Static guide. No credentials or background notifications. Geolocation runs only after a Near me tap and stays in memory. */
(() => {
  'use strict';
  const MOSQUE = [37.5331, 126.9969];
  const DAY = 86400000;
  const NAMES = ['Fajr', 'Sunrise', 'Dhuhr', 'Asr', 'Maghrib', 'Isha'];
  const PRAYERS = NAMES.filter(n => n !== 'Sunrise');
  const METHODS = ['3', '2', '4', '13', '17', '20'];
  const TIERS = {certified_seen:'Certificate seen', cross_checked:'Cross-checked', self_declared:'Self-declared', unverified:'Unverified'};
  const TYPES = {mosque:'Mosque', restaurant:'Restaurant', grocery:'Grocery', prayer_room:'Prayer room',cafe:'Café'};
  const PHRASE_CATEGORIES = {all:'All',greetings:'Greetings & courtesy',food_halal:'Food & halal',vegetarian:'Vegetarian requests',directions:'Directions & transport',money:'Money & shopping',prayer:'Prayer & mosque',emergency:'Emergencies & help',numbers:'Numbers',labels:'Label-spotting words'};
  const COLORS = {mosque:'#123e32', restaurant:'#bf5a29', grocery:'#316cad', prayer_room:'#8055a0',cafe:'#0f7f85'};
  const seoulFormat = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'});
  function seoulDate(now = new Date()) {
    const parts = Object.fromEntries(seoulFormat.formatToParts(now).map(p => [p.type,p.value]));
    return `${parts.year}-${parts.month}-${parts.day}`;
  }
  function validDate(value) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const epoch = Date.parse(value + 'T00:00:00Z');
    return Number.isFinite(epoch) && new Date(epoch).toISOString().slice(0,10) === value;
  }
  function shiftDate(date, days) { return new Date(Date.parse(date+'T00:00:00Z') + days * DAY).toISOString().slice(0,10); }
  function safeUrl(url) { try { const parsed = new URL(url); return parsed.protocol === 'https:' ? parsed.href : null; } catch { return null; } }
  function distanceBetween(from,lat,lng) {
    const rad = n => n*Math.PI/180;
    const a = Math.sin(rad(lat-from[0])/2)**2 + Math.cos(rad(from[0]))*Math.cos(rad(lat))*Math.sin(rad(lng-from[1])/2)**2;
    return 6371 * 2 * Math.atan2(Math.sqrt(a),Math.sqrt(1-a));
  }
  function distance(lat,lng) { return distanceBetween(MOSQUE,lat,lng); }
  function annotatePlaces(places, today) {
    return places.map(p => {
      const age = validDate(p.lastChecked) ? (Date.parse(today)-Date.parse(p.lastChecked))/DAY : NaN;
      const sources = Array.isArray(p.sources) ? [...new Set(p.sources.map(safeUrl).filter(Boolean))] : [];
      const hosts = new Set(sources.map(s => new URL(s).hostname.replace(/^www\./,'')));
      let tier = Object.hasOwn(TIERS,p.tier) ? p.tier : 'unverified';
      if (tier === 'certified_seen' && !(sources.length && safeUrl(p.certificateUrl) && sources.includes(safeUrl(p.certificateUrl)) && validDate(p.certificateExpiry) && p.certificateExpiry > today)) tier = 'unverified';
      if (tier === 'cross_checked' && hosts.size < 2) tier = 'unverified';
      if (tier === 'self_declared' && !sources.length) tier = 'unverified';
      const validCoords = Number.isFinite(p.lat) && Number.isFinite(p.lng) && Math.abs(p.lat)<=90 && Math.abs(p.lng)<=180;
      return {...p, sources, stale:!Number.isFinite(age) || age<0 || age>90, effectiveTier:tier, distanceKm:validCoords ? distance(p.lat,p.lng) : Infinity};
    });
  }
  function filterPlaces(places, filters) {
    return places.filter(p => !p.stale && Number.isFinite(p.distanceKm) && (filters.type==='all'||p.type===filters.type) && (filters.tier==='all'||p.effectiveTier===filters.tier) && (!filters.near || p.distanceKm<=1.1)).sort((a,b)=>a.distanceKm-b.distanceKm);
  }
  function sortByUser(places, user) {
    return places.map(p=>({...p,userKm:distanceBetween(user,p.lat,p.lng)})).sort((a,b)=>a.userKm-b.userKm);
  }
  // Web format, kept in one place because Naver does not document it publicly.
  function naverRouteUrl(place, mode, user) {
    const [lat,lng,name]=user?[user[0],user[1],'My location']:[MOSQUE[0],MOSQUE[1],'Seoul Central Mosque'];
    return `https://map.naver.com/p/directions/${lng},${lat},${encodeURIComponent(name)},,/${place.lng},${place.lat},${encodeURIComponent(place.name)},,/-/${mode}`;
  }
  function googleRouteUrl(place, user) {
    return `https://www.google.com/maps/dir/?api=1${user?`&origin=${user[0]},${user[1]}`:''}&destination=${place.lat},${place.lng}&travelmode=transit`;
  }
  function matchPhrases(phrases, category, query) {
    const q=query.trim().toLowerCase();
    return phrases.filter(p=>(category==='all'||p.category===category)&&(!q||p.en.toLowerCase().includes(q)||p.romanization.toLowerCase().includes(q)));
  }
  // iOS reports webkitCompassHeading; elsewhere only an absolute alpha has a north reference.
  function headingFromEvent(e) {
    if(Number.isFinite(e.webkitCompassHeading))return e.webkitCompassHeading;
    return e.absolute===true&&Number.isFinite(e.alpha)?(360-e.alpha)%360:null;
  }
  function arrowRotation(bearing,heading) { return ((bearing-heading)%360+360)%360; }
  function prayerEpoch(date,time) {
    const match = String(time).match(/^(\d{2}):(\d{2})(?:\s|$)/);
    if (!validDate(date) || !match || +match[1]>23 || +match[2]>59) return NaN;
    return Date.parse(`${date}T${match[1]}:${match[2]}:00+09:00`);
  }
  function nextPrayer(days,now) {
    return days.flatMap(d=>PRAYERS.map(name=>({name,date:d.date,epoch:prayerEpoch(d.date,d.timings[name])}))).filter(p=>p.epoch>now).sort((a,b)=>a.epoch-b.epoch)[0] || null;
  }
  window.GuideCore = {seoulDate,validDate,shiftDate,annotatePlaces,filterPlaces,sortByUser,naverRouteUrl,googleRouteUrl,matchPhrases,headingFromEvent,arrowRotation,prayerEpoch,nextPrayer};
  if (!document.querySelector('#prayer-grid')) return;

  const $ = id => document.getElementById(id);
  function el(tag,cls,text) { const n=document.createElement(tag); if(cls)n.className=cls; if(text!==undefined)n.textContent=text; return n; }
  const storage = {
    get(key) { try { return JSON.parse(localStorage.getItem(key)); } catch { return null; } },
    set(key,value) { try { localStorage.setItem(key,JSON.stringify(value)); return true; } catch { return false; } }
  };
  let settings = storage.get('shg:settings') || {};
  settings = {method:METHODS.includes(String(settings.method))?String(settings.method):'3',school:String(settings.school)==='1'?'1':'0',auto:settings.auto===true};
  let today=seoulDate(), records=[], visible=[], map=null, markers=null, days=[], generation=0, loading=false;
  // In memory only: never stored, logged or exposed on window.
  let userLoc=null, userMarker=null;
  let lastTick=Date.now(), audio=null, audioObjectUrl=null, audioReady=null, audioArmedAt=Infinity;
  const played=new Set();
  const filters={type:'all',tier:'all',near:false};
  $('method').value=settings.method;
  document.querySelector(`input[name="school"][value="${settings.school}"]`).checked=true;
  // A saved preference needs a fresh gesture to arm playback in this tab.
  $('auto-adhan').checked=false;
  if(settings.auto)$('audio-status').textContent='Automatic adhan was saved. Turn it on again to allow audio in this tab.';
  function saveSettings() { if(!storage.set('shg:settings',settings))$('prayer-status').textContent+=' Settings cannot be saved in this browser.'; }

  function updateDates(hijri) {
    $('gregorian-date').dateTime=today;
    $('gregorian-date').textContent=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Seoul',weekday:'short',day:'numeric',month:'long',year:'numeric'}).format(new Date(today+'T12:00:00+09:00'));
    $('hijri-date').textContent=hijri ? `${hijri.day} ${hijri.month.en} ${hijri.year} AH` : 'Hijri date unavailable until today’s timings load';
  }
  function refreshRecords() {
    records=annotatePlaces(window.PLACES||[],today);
    // Runtime data flags are inspectable; source dates are never rewritten.
    for(const p of window.PLACES||[])p.stale=records.find(r=>r.id===p.id)?.stale ?? true;
    const mosque=records.find(p=>p.id==='seoul-central-mosque');
    $('mosque-note-text').textContent=mosque?.notes||'Please confirm Friday arrangements with the mosque.';
    $('pending-count').textContent=`${records.filter(p=>p.stale).length} places pending check`;
    renderPlaces();
  }
  function link(text,url,cls) { const a=el('a',cls,text); a.href=safeUrl(url)||'#'; if(safeUrl(url)){a.target='_blank';a.rel='noopener noreferrer';} return a; }
  function fact(label,value) { return el('p','',`${label}: ${value}`); }
  function card(p) {
    const article=el('article','place-card');article.id=`place-${p.id}`;article.tabIndex=-1;
    const meta=el('div','card-meta');meta.append(el('span','',TYPES[p.type]||'Place'),el('span','distance',userLoc?`${p.userKm.toFixed(2)} km from you`:`${p.distanceKm.toFixed(2)} km · ~${Math.round(p.distanceKm/5*60)} min walk`));
    const title=el('h3','',p.name),address=el('p','address',p.address);
    const badge=el('span',`badge ${p.effectiveTier}`,TIERS[p.effectiveTier]);
    const basis=el('div','check-basis');basis.append(el('strong','',`Checked on ${p.lastChecked} — ${TIERS[p.effectiveTier].toLowerCase()}`),el('p','',p.halalBasis||'No basis recorded.'));
    if(p.effectiveTier!==p.tier)basis.append(el('p','','Evidence no longer supports the recorded tier; shown conservatively.'));
    const facts=el('div','facts');const yn=v=>v===true?'Yes':v===false?'No':'Not recorded';
    facts.append(fact('Prayer space',yn(p.prayerSpace)),fact('Alcohol served',yn(p.alcoholServed)),fact('Hours',p.hours||'Confirm before visiting'),fact('Price',p.priceLevel>=1&&p.priceLevel<=3?'₩'.repeat(p.priceLevel):'Not recorded'),fact('Certifier',p.certifier||'None recorded'));
    if(p.effectiveTier==='certified_seen')facts.append(fact('Certificate expiry',p.certificateExpiry));
    if(p.type==='cafe')facts.append(fact('Free WiFi',yn(p.wifi)));
    if(p.vegetarianOptions)facts.append(fact('Vegetarian options',p.vegetarianOptions));
    if(p.nearestStation)facts.append(fact('Nearest station',p.nearestStation));
    if(p.transitTime)facts.append(el('p','',`Typical: ${p.transitTime}`));
    const sources=el('details','sources');sources.append(el('summary','',`Sources (${p.sources.length})`));const list=el('ul');
    for(const url of p.sources){const li=el('li');li.append(link(new URL(url).hostname,url));list.append(li);}sources.append(list);
    const directions=el('nav','directions');directions.setAttribute('aria-label',`Directions to ${p.name}`);
    if(safeUrl(p.naverUrl))directions.append(link('Naver Map',p.naverUrl));if(safeUrl(p.googleUrl))directions.append(link('Google Maps',p.googleUrl));
    article.append(meta,title,address,badge,basis,facts);
    if(p.notes && p.type!=='mosque')article.append(el('p','card-notes',p.notes));
    const routes=el('nav','routes');routes.setAttribute('aria-label',`Routes to ${p.name}`);
    routes.append(link('Transit · Naver (live arrivals)',naverRouteUrl(p,'transit',userLoc)),link('Walking · Naver',naverRouteUrl(p,'walk',userLoc)),link('Transit · Google',googleRouteUrl(p,userLoc)));
    article.append(sources,routes,el('p','route-note','Tapping a route link opens Naver Maps and shares your location with Naver.'),directions);return article;
  }
  function renderPlaces() {
    visible=filterPlaces(records,filters);
    if(userLoc)visible=sortByUser(visible,userLoc);
    $('listings').replaceChildren(...visible.map(card));
    $('empty-state').hidden=visible.length>0;
    $('result-count').textContent=`${visible.length} current ${visible.length===1?'place':'places'} · ${userLoc?'sorted by distance from you':'nearest to Seoul Central Mosque first'}`;
    if (!markers) return;
    markers.clearLayers();
    for (const p of visible) {
      // A 44px target with a quiet 18px visual pin, usable by touch or keyboard.
      const pin = el('span', 'pin-dot');
      pin.style.backgroundColor = COLORS[p.type] || '#53675d';
      const icon = L.divIcon({className:'place-pin', html:pin, iconSize:[44,44], iconAnchor:[22,22], popupAnchor:[0,-14]});
      const marker = L.marker([p.lat,p.lng], {icon,keyboard:false,title:p.name});
      const popup = el('div');
      popup.append(el('strong','',p.name), el('br'));
      const a = el('a','','Open listing');
      a.href = `#place-${p.id}`;
      a.addEventListener('click',()=>document.getElementById(`place-${p.id}`)?.focus());
      popup.append(a);
      marker.bindPopup(popup);
      marker.on('click',()=>{
        const c = document.getElementById(`place-${p.id}`);
        c?.scrollIntoView({block:'nearest'});
        c?.focus({preventScroll:true});
      });
      marker.on('add',()=>{
        const node = marker.getElement();
        if (!node) return;
        node.setAttribute('role','button');
        node.setAttribute('tabindex','0');
        node.setAttribute('aria-label',`Open ${p.name} listing`);
        node.addEventListener('keydown',e=>{
          if (e.key==='Enter' || e.key===' ') {
            e.preventDefault();
            marker.fire('click');
            marker.openPopup();
          }
        });
      });
      marker.addTo(markers);
    }
  }
  function initMap() {
    if(!window.L){$('map-status').textContent='The map could not load. Use the Naver links on each listing.';return;}
    map=L.map('map',{scrollWheelZoom:false}).setView(MOSQUE,16);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'}).on('tileerror',()=>{$('map-status').textContent='Some map tiles could not load. Listing directions still work.';}).addTo(map);
    markers=L.layerGroup().addTo(map);renderPlaces();
  }
  function showUserOnMap() {
    if(!map)return;
    if(!userMarker){
      const icon=L.divIcon({className:'you-pin',html:el('span','you-dot'),iconSize:[24,24],iconAnchor:[12,12]});
      userMarker=L.marker(userLoc,{icon,title:'You are here',keyboard:false,zIndexOffset:1000}).bindTooltip('You are here',{permanent:true,direction:'top',offset:[0,-12]}).addTo(map);
    }
    userMarker.setLatLng(userLoc);map.setView(userLoc,15);
  }
  function setNearMe(active) { $('near-me').hidden=active;$('near-me-reset').hidden=!active; }
  function locationFailed() { $('near-me').disabled=false;$('near-me-status').textContent='Location unavailable — showing distance from the mosque instead'; }
  function useNearMe() {
    if(!navigator.geolocation){locationFailed();return;}
    $('near-me').disabled=true;$('near-me-status').textContent='';
    navigator.geolocation.getCurrentPosition(position=>{
      const {latitude,longitude}=position.coords;
      if(!Number.isFinite(latitude)||!Number.isFinite(longitude)){locationFailed();return;}
      $('near-me').disabled=false;userLoc=[latitude,longitude];setNearMe(true);renderPlaces();showUserOnMap();
    },locationFailed,{timeout:10000});
  }
  function resetNearMe() {
    userLoc=null;setNearMe(false);
    if(userMarker){userMarker.remove();userMarker=null;}
    if(map)map.setView(MOSQUE,16);
    renderPlaces();$('near-me').focus();
  }
  let phraseCategory='all', overlayOpener=null;
  function renderPhraseChips() {
    $('phrase-chips').replaceChildren(...Object.entries(PHRASE_CATEGORIES).map(([key,label])=>{
      const chip=el('button','phrase-chip',label);chip.type='button';chip.setAttribute('aria-pressed',String(key===phraseCategory));
      chip.addEventListener('click',()=>{phraseCategory=key;renderPhraseChips();renderPhrases();$('phrase-chips').querySelector('[aria-pressed="true"]').focus();});
      return chip;
    }));
  }
  function renderPhrases() {
    const shown=matchPhrases(window.PHRASES||[],phraseCategory,$('phrase-search').value);
    $('phrase-list').replaceChildren(...shown.map(p=>{
      const row=el('button','phrase-row');row.type='button';
      const ko=el('span','phrase-ko',p.ko);ko.lang='ko';
      row.append(el('span','phrase-en',p.en),ko,el('span','phrase-rom',p.romanization));
      row.addEventListener('click',()=>openOverlay(p,row));
      return row;
    }));
    $('phrase-count').textContent=`${shown.length} ${shown.length===1?'phrase':'phrases'}`;
  }
  function openOverlay(phrase,opener) {
    overlayOpener=opener;$('overlay-ko').textContent=phrase.ko;$('overlay-en').textContent=phrase.en;
    $('phrase-overlay').hidden=false;document.body.classList.add('overlay-open');$('overlay-close').focus();
  }
  function closeOverlay() {
    $('phrase-overlay').hidden=true;document.body.classList.remove('overlay-open');
    if(overlayOpener?.isConnected)overlayOpener.focus();overlayOpener=null;
  }
  function renderPrayers() {
    const d=days.find(d=>d.date===today);
    $('prayer-grid').replaceChildren(...NAMES.map(name=>{const row=el('div','prayer-time');row.dataset.prayer=name;row.append(el('span','name',name));const time=el('time','',d?d.timings[name].slice(0,5):'—:—');if(d)time.dateTime=`${today}T${d.timings[name].slice(0,5)}:00+09:00`;row.append(time,el('span','next-label',''));return row;}));
  }
  async function fetchJson(url) {
    const response=await fetch(url,{signal:AbortSignal.timeout(12000)});
    if(!response.ok)throw new Error('Network response');
    const json=await response.json();if(json.code!==200)throw new Error('API response');return json.data;
  }
  function validTimings(data,date,config) {
    return data && data.date?.gregorian?.date===date.split('-').reverse().join('-') && data.meta?.timezone==='Asia/Seoul' && String(data.meta?.method?.id)===config.method && data.meta?.school===(config.school==='1'?'HANAFI':'STANDARD') && NAMES.every(n=>Number.isFinite(prayerEpoch(date,data.timings?.[n]))) && data.date?.hijri?.day && data.date?.hijri?.month?.en && data.date?.hijri?.year;
  }
  async function getTimings(date,config,force=false) {
    const key=`shg:timings:${date}:${config.method}:${config.school}`;
    const cached=storage.get(key);
    if(!force&&validTimings(cached,date,config))return {data:cached,cached:true};
    try {
      const data=await fetchJson(`https://api.aladhan.com/v1/timings/${date.split('-').reverse().join('-')}?latitude=37.5331&longitude=126.9969&method=${config.method}&school=${config.school}&timezonestring=Asia%2FSeoul`);
      if(!validTimings(data,date,config))throw new Error('Unexpected timings');
      storage.set(key,data);return {data,cached:false};
    }catch(error){if(validTimings(cached,date,config))return {data:cached,cached:true,offline:true};throw error;}
  }
  async function loadPrayers(force=false) {
    const request=++generation, date=today, config={...settings};loading=true;days=[];updateDates();renderPrayers();$('countdown').textContent='Loading…';
    $('prayer-status').textContent='Fetching today’s timings from AlAdhan…';
    try{
      const result=await getTimings(date,config,force);
      if(request!==generation||date!==today)return;
      days=[{date,timings:result.data.timings}];updateDates(result.data.date.hijri);renderPrayers();
      $('prayer-status').textContent=`${result.offline?'Offline · using matching saved timings.':result.cached?'Today’s saved timings.':'Today’s timings from AlAdhan.'} Calculated times; confirm congregation times with the mosque.`;
      loading=false;tick();
      try{const tomorrow=shiftDate(date,1), next=await getTimings(tomorrow,config,force);if(request!==generation||date!==today)return;days.push({date:tomorrow,timings:next.data.timings});tick();}
      catch{if(request===generation)$('prayer-status').textContent+=' Tomorrow’s Fajr unavailable; refresh to retry.';}
    }catch{if(request!==generation)return;loading=false;$('countdown').textContent='Times unavailable';$('prayer-status').textContent='Could not load today’s times. Check your connection and use “Refresh times” to retry. Older-day timings are never shown.';}
  }
  async function loadQibla() {
    $('retry-qibla').hidden=true;
    try{const result=await fetchJson('https://api.aladhan.com/v1/qibla/37.5331/126.9969');if(!Number.isFinite(result.direction)||result.direction<0||result.direction>=360)throw new Error('Invalid bearing');qiblaBearing=result.direction;$('qibla-bearing').textContent=`${result.direction.toFixed(1)}°`;if(!compassOn)setArrow(result.direction);$('qibla-arrow').style.visibility='visible';}
    catch{$('qibla-bearing').textContent='Bearing unavailable';$('retry-qibla').hidden=false;}
  }
  let qiblaBearing=null, compassOn=false, compassTimer=null;
  function setArrow(degrees) { $('qibla-arrow').style.transform=`rotate(${degrees}deg)`; }
  function onOrientation(e) {
    const heading=headingFromEvent(e);
    if(heading===null||!compassOn)return;
    clearTimeout(compassTimer);
    $('compass-status').textContent='Compass on. Approximate: phone compasses read magnetic north and drift near metal.';
    setArrow(arrowRotation(qiblaBearing,heading+(screen.orientation?.angle||0)));
  }
  function stopCompass(message='') {
    compassOn=false;clearTimeout(compassTimer);
    window.removeEventListener('deviceorientationabsolute',onOrientation);window.removeEventListener('deviceorientation',onOrientation);
    $('use-compass').textContent='Use compass';$('compass-status').textContent=message;
    if(qiblaBearing!==null)setArrow(qiblaBearing);
  }
  const COMPASS_FAILED='Compass unavailable on this device. Use the bearing above.';
  async function startCompass() {
    if(qiblaBearing===null||!window.DeviceOrientationEvent){stopCompass(COMPASS_FAILED);return;}
    if(typeof DeviceOrientationEvent.requestPermission==='function'){
      // Chromium can also answer 'prompt'; only a denial stops here, and the timeout covers silence.
      try{if(await DeviceOrientationEvent.requestPermission()==='denied'){stopCompass(COMPASS_FAILED);return;}}
      catch{stopCompass(COMPASS_FAILED);return;}
    }
    compassOn=true;$('use-compass').textContent='Stop compass';$('compass-status').textContent='Looking for a compass reading…';
    window.addEventListener('deviceorientationabsolute',onOrientation);window.addEventListener('deviceorientation',onOrientation);
    compassTimer=setTimeout(()=>stopCompass(COMPASS_FAILED),4000);
  }
  async function prepareAudio() {
    if(audioReady)return audioReady;
    audioReady=(async()=>{const r=await fetch('assets/adhan.mp3');if(!r.ok)throw new Error('Audio absent');const blob=await r.blob();if(!blob.size)throw new Error('Audio placeholder');audioObjectUrl=URL.createObjectURL(blob);audio=new Audio(audioObjectUrl);audio.addEventListener('ended',()=>{$('play-adhan').lastChild.textContent='Play Adhan';});return audio;})();
    try{return await audioReady;}catch(error){audioReady=null;throw error;}
  }
  async function playAdhan() {
    try{const a=await prepareAudio();a.volume=1;a.currentTime=0;await a.play();$('audio-status').textContent='Playing adhan. Playback only runs while this page is open.';$('play-adhan').lastChild.textContent='Stop Adhan';}
    catch{$('audio-status').textContent='Adhan audio is unavailable or playback was blocked. Add a playable recording at assets/adhan.mp3, then press Play Adhan.';}
  }
  function tick() {
    const now=Date.now(), current=seoulDate(new Date(now));
    if(current!==today){today=current;lastTick=now;refreshRecords();updateDates();loadPrayers();return;}
    const next=nextPrayer(days,now);
    if(next){const seconds=Math.max(0,Math.ceil((next.epoch-now)/1000));const hours=Math.floor(seconds/3600),minutes=Math.floor(seconds%3600/60),secs=seconds%60;$('countdown').textContent=`${next.name}${next.date!==today?' tomorrow':''} in ${hours?hours+'h ':''}${minutes}m ${String(secs).padStart(2,'0')}s`;}
    else if(days.length&&!loading)$('countdown').textContent='Next Fajr unavailable — refresh';
    for(const node of document.querySelectorAll('.prayer-time')){const active=next?.date===today&&node.dataset.prayer===next.name;node.classList.toggle('is-next',active);node.querySelector('.next-label').textContent=active?'Next prayer':'';}
    if($('auto-adhan').checked && document.visibilityState==='visible' && now-lastTick<15000){for(const d of days)for(const name of PRAYERS){const epoch=prayerEpoch(d.date,d.timings[name]), key=`${d.date}:${name}`;if(epoch>lastTick&&epoch<=now&&epoch>=audioArmedAt&&!played.has(key)){played.add(key);playAdhan();}}}
    lastTick=now;
  }
  $('method').addEventListener('change',()=>{settings.method=$('method').value;saveSettings();loadPrayers();});
  for(const input of document.querySelectorAll('input[name="school"]'))input.addEventListener('change',()=>{settings.school=input.value;saveSettings();loadPrayers();});
  $('retry-prayers').addEventListener('click',()=>loadPrayers(true));$('retry-qibla').addEventListener('click',loadQibla);
  $('play-adhan').addEventListener('click',()=>{if(audio&&!audio.paused){audio.pause();audio.currentTime=0;$('play-adhan').lastChild.textContent='Play Adhan';$('audio-status').textContent='Adhan stopped.';}else playAdhan();});
  let audioToggleVersion = 0;
  $('auto-adhan').addEventListener('change', async () => {
    const version = ++audioToggleVersion;
    const wanted = $('auto-adhan').checked;
    settings.auto = wanted;
    saveSettings();
    if (!wanted) {
      audioArmedAt = Infinity;
      $('audio-status').textContent = 'Automatic adhan is off.';
      return;
    }
    let unlockedAudio = null;
    try {
      const a = await prepareAudio();
      if (version !== audioToggleVersion || !$('auto-adhan').checked) return;
      if (a.paused) {
        unlockedAudio = a;
        a.volume = 0;
        try { await a.play(); }
        finally { a.pause(); a.currentTime = 0; a.volume = 1; }
      }
      if (version !== audioToggleVersion || !$('auto-adhan').checked) return;
      audioArmedAt = Date.now();
      lastTick = Date.now();
      $('audio-status').textContent = 'Automatic adhan is on for this visible page. Keep this page open; no background or push adhan.';
    } catch {
      if (version !== audioToggleVersion) return;
      $('auto-adhan').checked = false;
      settings.auto = false;
      saveSettings();
      $('audio-status').textContent = 'Automatic adhan could not start. Add a playable assets/adhan.mp3 recording and allow audio, then turn it on again.';
    } finally {
      if (unlockedAudio) unlockedAudio.volume = 1;
    }
  });
  for(const [id,key] of [['type-filter','type'],['tier-filter','tier'],['near-filter','near']])$(id).addEventListener('change',()=>{filters[key]=key==='near'?$(id).checked:$(id).value;renderPlaces();});
  $('reset-filters').addEventListener('click',()=>{Object.assign(filters,{type:'all',tier:'all',near:false});$('type-filter').value='all';$('tier-filter').value='all';$('near-filter').checked=false;renderPlaces();});
  $('near-me').addEventListener('click',useNearMe);$('near-me-reset').addEventListener('click',resetNearMe);
  $('use-compass').addEventListener('click',()=>{if(compassOn)stopCompass();else startCompass();});
  $('phrase-search').addEventListener('input',renderPhrases);
  $('phrase-overlay').addEventListener('click',closeOverlay);
  document.addEventListener('keydown',e=>{if($('phrase-overlay').hidden)return;if(e.key==='Escape')closeOverlay();else if(e.key==='Tab'){e.preventDefault();$('overlay-close').focus();}});
  document.addEventListener('visibilitychange',()=>{lastTick=Date.now();if(document.visibilityState==='visible'){tick();if(!days.length&&!loading)loadPrayers();}});
  window.addEventListener('online',()=>{loadPrayers();loadQibla();});
  updateDates();refreshRecords();initMap();renderPhraseChips();renderPhrases();loadPrayers();loadQibla();setInterval(tick,1000);
  if('serviceWorker' in navigator)navigator.serviceWorker.register('sw.js').catch(()=>{});
})();

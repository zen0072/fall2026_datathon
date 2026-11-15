const $ = selector => document.querySelector(selector);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const aspects = {physical:'Physical access', sensory:'Sensory & communication', language:'Language assistance', financial:'Cost & fees', time:'Waits & hours'};
const services = {clinic:'Clinic',pharmacy:'Pharmacy',grocery:'Grocery'};
const statuses = {
  reported_barrier:{label:'Barrier reported',className:'barrier'},
  conflicting_or_unclear:{label:'Mixed or unclear reports',className:'mixed'},
  positive_evidence:{label:'Positive evidence',className:'positive'},
  insufficient_evidence:{label:'Insufficient evidence',className:'unknown'},
  barrier_reported:{label:'Barrier reported',className:'barrier'},
  positive_access:{label:'Positive access',className:'positive'},
  unclear_or_mixed:{label:'Mixed or unclear',className:'mixed'}
};
const state = {aspect:'physical',service:'all',search:'',status:'all',sort:'barriers',offset:0,limit:20,metadata:null,items:[],total:0,selected:null};
let map, mapLayers, requestVersion=0, detailVersion=0, markers=new Map();
const badge = status => {const s=statuses[status] || statuses.insufficient_evidence;return `<span class="badge ${s.className}">${s.label}</span>`;};
const date = value => value ? new Date(value).toLocaleDateString(undefined,{year:'numeric',month:'short',day:'numeric',timeZone:'UTC'}) : 'Unknown date';
const number = value => Number(value || 0).toLocaleString();

function notice(message, error=false) {
  $('#notice').hidden = !message;
  $('#notice').textContent = message;
  $('#notice').dataset.error = String(error);
}

async function api(path, options={}) {
  const config = {...options,headers:{...options.headers},cache:'no-store'};
  if (Object.hasOwn(config,'body')) {
    config.headers['Content-Type']='application/json';
    config.body=JSON.stringify(config.body);
  }
  const response=await fetch(path,config);
  const body=await response.json();
  if (!response.ok) {
    const error=new Error(body.error || 'The request could not be completed.');
    error.status=response.status;
    error.details=body;
    throw error;
  }
  return body;
}

function run(promise) {promise.catch(error => notice(error.message,true));}

async function loadMetadata() {
  state.metadata=await api('/api/metadata');
  const data=state.metadata;
  const reviewsOnly=data.dataset?.selection?.source_mode==='reviews_only';
  $('#coverage-notice').hidden=!reviewsOnly;
  $('#coverage-notice').textContent=reviewsOnly ? 'Partial review coverage · Classifications need verification. Coordinates are unavailable, and these locations are not limited to the Bay Area.' : '';
  $('#empty-state').hidden=Boolean(data.snapshot_id);
  $('#locations-page').hidden=!data.snapshot_id;
}

async function loadData() {
  await loadMetadata();
  if (state.metadata.snapshot_id) await loadLocations();
}

function syncFilters() {
  $('#service').value=state.service;
  $('#search').value=state.search;
  $('#report-status').value=state.status;
  $('#sort').value=state.sort;
  document.querySelectorAll('[data-aspect]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.aspect===state.aspect)));
}

async function loadLocations() {
  const version=++requestVersion;
  syncFilters();
  $('#locations-list').setAttribute('aria-busy','true');
  const common={aspect:state.aspect,service:state.service,search:state.search,status:state.status,sort:state.sort};
  const params=new URLSearchParams({...common,limit:state.limit,offset:state.offset});
  const mapParams=new URLSearchParams({...common,limit:500,offset:0});
  try {
    const [result, points]=await Promise.all([api(`/api/places?${params}`),api(`/api/places?${mapParams}`)]);
    if (version!==requestVersion) return;
    state.items=result.items;state.total=result.total;
    if (!state.items.some(p=>p.place_id===state.selected)) state.selected=state.items[0]?.place_id || null;
    renderList();renderMap(points.items,points.total);
    await loadDetail();
  } finally {
    if (version===requestVersion) $('#locations-list').removeAttribute('aria-busy');
  }
}

function renderList() {
  const start=state.total ? state.offset+1 : 0;
  $('#results-count').textContent=`${number(start)}–${number(state.offset+state.items.length)} of ${number(state.total)} locations · ${aspects[state.aspect]}`;
  $('#locations-list').innerHTML=state.items.length ? state.items.map(p=>`<button type="button" class="location-card" data-location="${escapeHTML(p.place_id)}" aria-pressed="${p.place_id===state.selected}"><span class="place-type">${services[p.service]}</span><span class="location-name">${escapeHTML(p.name)}</span><span class="muted">${number(p.sampled_reviews)} sampled reviews · ${date(p.last_date)}</span>${badge(p.status)}${p.closure_status==='temporarily_closed' ? '<span class="closure-note">Reported temporarily closed</span>' : ''}</button>`).join('') : '<p class="muted">No locations match these filters.</p>';
  $('#previous-page').disabled=state.offset===0;
  $('#next-page').disabled=state.offset+state.items.length>=state.total;
  $('#locations-list').querySelectorAll('[data-location]').forEach(button=>button.addEventListener('click',()=>run(selectLocation(button.dataset.location,true))));
}

async function selectLocation(id,scroll=false) {
  state.selected=id;
  renderList();updateMarkerSelection();
  await loadDetail();
  if (scroll) $('#location-detail').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth',block:'start'});
}

function initializeMap() {
  if (map) return true;
  if (!window.L) {$('#map-error').hidden=false;return false;}
  map=L.map('map',{scrollWheelZoom:false}).setView([37.77,-122.3],9);
  let loaded=0;
  const tiles=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,attribution:'Tiles &copy; Esri &mdash; Sources: Esri, DeLorme, NAVTEQ, USGS, Intermap, iPC, NRCAN, Esri Japan, METI, Esri China (Hong Kong), Esri (Thailand), TomTom, 2012'}).addTo(map);
  tiles.on('tileload',()=>{loaded++;$('#map-error').hidden=true;});
  tiles.on('tileerror',()=>{if (!loaded && !$('#map').hidden) $('#map-error').hidden=false;});
  mapLayers=L.layerGroup().addTo(map);
  return true;
}

function renderMap(points,total) {
  const mappable=points.filter(p=>p.valid_coordinates);
  $('#map').hidden=!mappable.length;
  $('#map-placeholder').hidden=Boolean(mappable.length);
  $('#map-placeholder-title').textContent=total ? 'Coordinates not available' : 'No matching locations';
  $('#map-placeholder-description').textContent=total ? 'The current results have no map coordinates. You can explore classifications and review evidence in the list.' : 'Try another name or adjust the filters to show matching places.';
  if (!mappable.length) {
    if (mapLayers) mapLayers.clearLayers();
    markers=new Map();
    $('#map-error').hidden=true;
    $('#map-caption').textContent=total ? `Coordinates unavailable · ${number(total)} matching locations remain in the list` : '0 matching locations';
    return;
  }
  if (!initializeMap()) return;
  map.invalidateSize();mapLayers.clearLayers();markers=new Map();
  const css=getComputedStyle(document.documentElement);
  const colors={reported_barrier:css.getPropertyValue('--warning').trim(),conflicting_or_unclear:css.getPropertyValue('--mixed').trim(),positive_evidence:css.getPropertyValue('--positive').trim(),insufficient_evidence:css.getPropertyValue('--muted').trim()};
  // Resolve light-dark() in computed styles before giving a color to Leaflet.
  const colorProbe=document.createElement('span');colorProbe.hidden=true;document.body.append(colorProbe);
  for (const key of Object.keys(colors)) {colorProbe.style.color=colors[key];colors[key]=getComputedStyle(colorProbe).color;}
  colorProbe.remove();
  for (const p of mappable) {
    const marker=L.circleMarker([p.lat,p.lon],{radius:7,color:colors[p.status],fillColor:colors[p.status],fillOpacity:.9,weight:2}).addTo(mapLayers);
    const tooltip=document.createElement('span');tooltip.textContent=`${p.name} · ${statuses[p.status].label}`;
    marker.bindTooltip(tooltip);
    marker.on('click',()=>run(selectLocation(p.place_id,true)));
    markers.set(p.place_id,marker);
  }
  if (mappable.length) map.fitBounds(L.latLngBounds(mappable.map(p=>[p.lat,p.lon])),{padding:[35,35],maxZoom:13,animate:false});
  $('#map-caption').textContent=total && !mappable.length ? `Coordinates unavailable · ${number(total)} matching locations remain in the list` : `${number(mappable.length)} mapped of ${number(total)} matches${total>500?' · first 500 results':''}`;
  updateMarkerSelection();
}

function updateMarkerSelection() {for (const [id,marker] of markers) marker.setRadius(id===state.selected?10:7);}

async function loadDetail() {
  const version=++detailVersion;
  if (!state.selected) {$('#location-detail').innerHTML='<p class="muted">Select a location to inspect its evidence.</p>';return;}
  const params=new URLSearchParams({aspect:state.aspect});
  const result=await api(`/api/places/${encodeURIComponent(state.selected)}?${params}`);
  if (version!==detailVersion) return;
  const p=result.place;
  const a=result.aspects.find(a=>a.aspect===state.aspect);
  $('#location-detail').innerHTML=`<div class="detail-heading"><span class="eyebrow">${services[p.service]} · ${aspects[state.aspect]}</span><h2>${escapeHTML(p.name)}</h2>${p.address?`<p class="small muted">${escapeHTML(p.address)}</p>`:''}<p class="small muted">${number(a.barrier_reports)} barrier · ${number(a.positive_reports)} positive · ${number(a.uncertain_reports)} mixed reports / ${number(a.sampled_reviews)} sampled reviews</p>${p.closure_status==='temporarily_closed'?'<span class="badge barrier">Reported temporarily closed</span>':''}</div><div class="evidence-grid">${result.evidence.length?result.evidence.map(e=>`<div class="evidence-item">${badge(e.state)}<blockquote>“${escapeHTML(e.text)}”</blockquote><p class="small muted">${date(e.review_date)} · Evidence ${escapeHTML(e.record_id)}</p></div>`).join(''):'<div class="evidence-item"><span class="badge">Insufficient evidence</span><p class="small muted">No relevant excerpts are available for this access issue. Current conditions need verification.</p></div>'}</div><p class="detail-footnote">Showing ${number(result.evidence.length)} of ${number(result.evidence_total)} excerpts. Classifications describe historical review text and need verification.</p>`;
}

function filterChanged() {state.offset=0;run(loadLocations());}
let searchTimer;
$('#search').addEventListener('input',event=>{state.search=event.target.value;clearTimeout(searchTimer);searchTimer=setTimeout(filterChanged,250);});
for (const [id,key] of [['service','service'],['report-status','status'],['sort','sort']]) $(`#${id}`).addEventListener('change',event=>{state[key]=event.target.value;filterChanged();});
document.querySelectorAll('[data-aspect]').forEach(button=>button.addEventListener('click',()=>{state.aspect=button.dataset.aspect;filterChanged();}));
$('#previous-page').addEventListener('click',()=>{state.offset=Math.max(0,state.offset-state.limit);run(loadLocations());});
$('#next-page').addEventListener('click',()=>{state.offset+=state.limit;run(loadLocations());});
matchMedia('(prefers-color-scheme:dark)').addEventListener('change',()=>{if (state.metadata?.snapshot_id) run(loadLocations());});
if (['#locations','#queue','#data'].includes(location.hash)) history.replaceState(null,'',location.pathname+location.search);
run(loadData());

let chatBusy=false;
function renderChatConfig(config) {
  $('#chat-llm').disabled=!config.available;
  if (!config.available) $('#chat-llm').checked=false;
  $('#chat-settings').hidden=!config.configurable;
  $('#chat-model').value=config.model || '';
  $('#chat-key-remove').disabled=!config.available;
  $('#chat-provider').textContent=config.available ? `Optional: use ${config.model} to select evidence. Your question and up to 24 review excerpts are sent to OpenAI. No conversation history is sent.` : config.configurable ? 'Offline retrieval active. Add your own key above to enable optional LLM evidence selection.' : 'Offline retrieval active. Configure server-side OpenAI credentials to enable optional LLM evidence selection.';
  $('#chat-key-status').textContent=config.available ? 'A key is configured. Select “Use LLM evidence selection” below, then ask a question. Credentials have not been tested with OpenAI yet.' : 'No key is active. Offline retrieval is available without API credentials.';
}
run(api('/api/chat/config').then(renderChatConfig));

let keyBusy=false;
async function updateChatSettings(payload) {
  if (keyBusy) return;
  keyBusy=true;
  $('#chat-key-save').disabled=true;
  $('#chat-key-remove').disabled=true;
  $('#chat-settings-form').setAttribute('aria-busy','true');
  try {
    renderChatConfig(await api('/api/chat/config',{method:'POST',body:payload}));
  } catch(error) {
    $('#chat-key-status').textContent=error.message;
    // Read only public connection status; the server never returns the key.
    try {const config=await api('/api/chat/config');$('#chat-key-remove').disabled=!config.available;}catch {}
  } finally {
    $('#chat-api-key').value='';
    $('#chat-settings-form').removeAttribute('aria-busy');
    $('#chat-key-save').disabled=false;
    keyBusy=false;
  }
}
$('#chat-settings-form').addEventListener('submit',event=>{
  event.preventDefault();
  const payload={api_key:$('#chat-api-key').value.trim(),model:$('#chat-model').value.trim()};
  $('#chat-api-key').value='';
  run(updateChatSettings(payload));
});
$('#chat-key-remove').addEventListener('click',()=>run(updateChatSettings({clear:true})));
$('#chat-form').addEventListener('submit',async event=>{
  event.preventDefault();
  if (chatBusy) return;
  if ($('#chat-selected').checked && !state.selected) {notice('Select a location first.',true);return;}
  const question=$('#chat-question').value.trim();
  if (!question) return;
  chatBusy=true;$('#chat-submit').disabled=true;$('#chat-results').setAttribute('aria-busy','true');
  $('#chat-results').textContent='Reading the current results…';
  try {
    const result=await api('/api/chat',{method:'POST',body:{question,aspect:state.aspect,service:state.service,search:state.search,place_id:$('#chat-selected').checked ? state.selected : '',use_llm:$('#chat-llm').checked}});
    const scope=result.scope;
    $('#chat-results').innerHTML=`<article class="chat-answer"><span class="badge">${result.mode==='llm'?'LLM evidence selection':'Offline retrieval'}</span><p><strong>${escapeHTML(question)}</strong></p><p>${escapeHTML(result.answer)}</p><p class="small muted">Scope: ${escapeHTML(aspects[scope.aspect])} · ${escapeHTML(scope.service)} · search: ${escapeHTML(scope.search || 'all')} · ${scope.place_id?'selected location':'all matching locations'} · all classifications. ${scope.question_overrode_filters?'Explicit aspect/service words in your question override those explorer filters. ':''}Snapshot ${escapeHTML(result.snapshot_id || 'none')}.</p><p class="small muted">${escapeHTML(result.provider_note)}</p><h3>Verification priority</h3><p class="small muted">${escapeHTML(result.ranking_method)}</p><ol>${result.ranking.map(p=>`<li><strong>${escapeHTML(p.name)}</strong>: ${number(p.barrier_reports)} barrier / ${number(p.positive_reports)} positive / ${number(p.uncertain_reports)} mixed reports from ${number(p.sampled_reviews)} sampled reviews [A1].</li>`).join('') || '<li>No matching locations.</li>'}</ol><h3>Review sources</h3><div class="chat-sources">${result.citations.map(e=>`<div class="chat-source"><strong>[${escapeHTML(e.id)}] ${escapeHTML(e.name)}</strong> ${badge(e.state)}<blockquote>${escapeHTML(e.text)}</blockquote><span class="small muted">Record ${escapeHTML(e.record_id)} · ${date(e.review_date)}</span></div>`).join('') || '<p>No supporting excerpts in this scope.</p>'}</div><p class="small muted">[A1] Imported place-aspect counts in snapshot ${escapeHTML(result.snapshot_id || 'none')}. ${escapeHTML(result.context_note)}</p><h3>Suggested verification steps</h3><ul>${result.suggestions.map(s=>`<li>${escapeHTML(s)}</li>`).join('')}</ul><p class="coverage-notice">${escapeHTML(result.notice)} Dataset mode: ${escapeHTML(result.dataset?.mode || 'none')}; labels: ${escapeHTML(result.dataset?.label_mode || 'unspecified')}.</p></article>`;
  } catch(error) {$('#chat-results').textContent=error.message;}
  finally {chatBusy=false;$('#chat-submit').disabled=false;$('#chat-results').setAttribute('aria-busy','false');}
});

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
const state = {aspect:'physical',service:'all',search:'',status:'with_evidence',sort:'barriers',offset:0,limit:20,metadata:null,items:[],total:0,selected:null};
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
  syncChatContext();
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
    renderList();renderMap(points.items,points.total);syncChatContext();
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
  renderList();updateMarkerSelection();syncChatContext();
  await loadDetail();
  if (scroll) $('#location-detail').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth',block:'start'});
}

function initializeMap() {
  if (map) return true;
  if (!window.L) {$('#map-error').hidden=false;return false;}
  map=L.map('map',{scrollWheelZoom:true}).setView([37.77,-122.3],9);
  let loaded=0;
  const attribution='Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>, GIS user community';
  const tiles=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,attribution}).addTo(map);
  const labels=map.createPane('basemap-labels');
  labels.style.zIndex=250;
  labels.style.pointerEvents='none';
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}',{pane:'basemap-labels',maxZoom:19,attribution}).addTo(map);
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
  const colors={reported_barrier:css.getPropertyValue('--map-barrier').trim(),conflicting_or_unclear:css.getPropertyValue('--map-mixed').trim(),positive_evidence:css.getPropertyValue('--map-positive').trim(),insufficient_evidence:css.getPropertyValue('--map-unknown').trim()};
  for (const p of mappable) {
    const marker=L.circleMarker([p.lat,p.lon],{radius:7,color:'#fff',fillColor:colors[p.status],fillOpacity:1,weight:2}).addTo(mapLayers);
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

const evidenceFilters=[['all','All'],['barrier_reported','Barriers'],['positive_access','Positive'],['unclear_or_mixed','Mixed']];
let evidenceView=null;

function renderEvidence(preserveScroll=false) {
  const {result,filter}=evidenceView;
  const scroll=$('#evidence-scroll');
  const previousScroll=scroll.scrollTop;
  document.querySelectorAll('[data-evidence-filter]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.evidenceFilter===filter)));
  $('#evidence-items').innerHTML=result.evidence.length ? result.evidence.map(e=>`<article class="evidence-item"><div class="evidence-meta">${badge(e.state)}<span class="small muted">${date(e.review_date)}</span></div><blockquote>“${escapeHTML(e.text)}”</blockquote><details class="evidence-source"><summary>Source details</summary><p>Evidence ${escapeHTML(e.record_id)}</p></details></article>`).join('') : `<p class="evidence-empty muted">${filter==='all'?'No relevant excerpts are available for this access issue. Current conditions need verification.':'No excerpts match this evidence type. Try another tab.'}</p>`;
  $('#evidence-load-more').hidden=result.evidence.length>=result.evidence_total;
  $('#evidence-load-more').disabled=false;
  const type={all:'',barrier_reported:'barrier ',positive_access:'positive ',unclear_or_mixed:'mixed '}[filter];
  $('#evidence-count').textContent=`Showing ${number(result.evidence.length)} of ${number(result.evidence_total)} ${type}excerpts · Newest first`;
  scroll.scrollTop=preserveScroll?previousScroll:0;
}

async function loadEvidence(filter,append=false) {
  const view=evidenceView;
  if (!view || (append && view.loading)) return;
  const version=++detailVersion;
  view.loading=true;
  $('#evidence-scroll').setAttribute('aria-busy','true');
  $('#evidence-load-more').disabled=true;
  $('#evidence-count').textContent='Loading evidence…';
  const params=new URLSearchParams({aspect:view.aspect,snapshot_id:view.result.snapshot_id,evidence_state:filter,evidence_offset:append?view.result.evidence.length:0});
  try {
    const result=await api(`/api/places/${encodeURIComponent(view.result.place.place_id)}?${params}`);
    if (version!==detailVersion || evidenceView!==view) return;
    if (append) result.evidence=[...view.result.evidence,...result.evidence];
    view.result=result;view.filter=filter;
    renderEvidence(append);
  } catch(error) {
    if (version===detailVersion && evidenceView===view) {
      renderEvidence(true);
      $('#evidence-count').textContent=`Could not load evidence: ${error.message} Try again.`;
    }
  } finally {
    if (version===detailVersion && evidenceView===view) {
      view.loading=false;
      $('#evidence-scroll').removeAttribute('aria-busy');
    }
  }
}

async function loadDetail() {
  const version=++detailVersion;
  evidenceView=null;
  if (!state.selected) {$('#location-detail').innerHTML='<p class="detail-empty muted">Select a location to inspect its evidence.</p>';return;}
  const params=new URLSearchParams({aspect:state.aspect});
  const result=await api(`/api/places/${encodeURIComponent(state.selected)}?${params}`);
  if (version!==detailVersion) return;
  const p=result.place;
  const a=result.aspects.find(a=>a.aspect===state.aspect);
  evidenceView={result,aspect:state.aspect,filter:'all',loading:false};
  syncChatContext();
  $('#location-detail').innerHTML=`<header class="detail-heading"><span class="eyebrow">${services[p.service]} · ${aspects[state.aspect]}</span><h2>${escapeHTML(p.name)}</h2>${p.address?`<p class="small muted">${escapeHTML(p.address)}</p>`:''}<div class="detail-summary"><span>${number(a.barrier_reports)} barrier reports</span><span>${number(a.positive_reports)} positive</span><span>${number(a.uncertain_reports)} mixed</span><span class="muted">${number(a.sampled_reviews)} sampled reviews</span></div>${p.closure_status==='temporarily_closed'?'<span class="badge barrier">Reported temporarily closed</span>':''}</header><div class="evidence-tabs" role="group" aria-label="Filter review evidence">${evidenceFilters.map(([key,label])=>`<button type="button" data-evidence-filter="${key}" aria-pressed="${key==='all'}" aria-controls="evidence-scroll">${label} <span>${number(result.evidence_counts[key])}</span></button>`).join('')}</div><div id="evidence-scroll" class="evidence-scroll" role="region" aria-label="Review evidence" tabindex="0"><div id="evidence-items"></div><button id="evidence-load-more" type="button" class="button secondary" hidden>Load more excerpts</button></div><div class="detail-footnote"><p id="evidence-count" role="status" aria-live="polite"></p><p>Historical reviews · Verify current conditions</p></div>`;
  renderEvidence();
}

$('#location-detail').addEventListener('click',event=>{
  const button=event.target.closest('[data-evidence-filter]');
  if (button) run(loadEvidence(button.dataset.evidenceFilter));
  if (event.target.closest('#evidence-load-more') && evidenceView) run(loadEvidence(evidenceView.filter,true));
});

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
function syncChatContext() {
  $('#chat-feedback').hidden=true;
  $('#chat-context-aspect').textContent=aspects[state.aspect];
  const selected=evidenceView?.result.place.place_id===state.selected ? evidenceView.result.place.name : state.items.find(p=>p.place_id===state.selected)?.name;
  const scope=$('#chat-selected').checked ? (state.selected ? selected || 'Selected location' : 'Select a location above') : 'All matching locations';
  const service=state.service==='all'?'All essential services':services[state.service];
  $('#chat-context-place').textContent=[scope,service,state.search?`Search: ${state.search}`:'','All classifications'].filter(Boolean).join(' · ');
}
$('#chat-selected').addEventListener('change',syncChatContext);
$('#chat-llm').addEventListener('change',()=>{$('#chat-mode-status').textContent=$('#chat-llm').checked?'OpenAI evidence selection':'Offline retrieval';});
function renderChatConfig(config) {
  $('#chat-llm').disabled=!config.available;
  if (!config.available) $('#chat-llm').checked=false;
  $('#chat-key-settings').hidden=!config.configurable;
  $('#chat-mode-status').textContent=$('#chat-llm').checked?'OpenAI evidence selection':'Offline retrieval';
  $('#chat-model').value=config.model || '';
  $('#chat-key-remove').disabled=!config.available;
  $('#chat-provider').textContent=config.available ? `Optional: use ${config.model} to select evidence. Your question and up to 24 review excerpts are sent to OpenAI. No conversation history is sent.` : config.configurable ? 'Offline retrieval active. Add your own key above to enable optional LLM evidence selection.' : 'Offline retrieval active. Configure server-side OpenAI credentials to enable optional LLM evidence selection.';
  $('#chat-key-status').textContent=config.available ? 'A key is configured. Select “Use OpenAI evidence selection” above, then ask a question. Credentials have not been tested with OpenAI yet.' : 'No key is active. Offline retrieval is available without API credentials.';
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
function renderChatAnswer(result) {
  const scope=result.scope;
  const place=scope.place_id ? result.ranking.find(p=>p.place_id===scope.place_id)?.name || 'Selected location' : 'All matching locations';
  const appliedScope=[aspects[scope.aspect],place,scope.service==='all'?'All essential services':services[scope.service],scope.search?`Search: ${scope.search}`:'','All classifications'].filter(Boolean).join(' · ');
  return `<div class="chat-answer-heading"><span class="eyebrow">Review assistant</span><span class="chat-mode">${result.mode==='llm'?'OpenAI evidence selection':'Offline retrieval'}</span></div><p class="chat-answer-text">${escapeHTML(result.answer)}</p><p class="chat-answer-scope">${escapeHTML(appliedScope)}${scope.question_overrode_filters?' · Scope adjusted to the category or service named in your question.':''}</p><details class="chat-answer-details"><summary>View ${number(result.citations.length)} supporting excerpt${result.citations.length===1?'':'s'}</summary><div class="chat-sources">${result.citations.map(e=>`<article class="chat-source"><div class="chat-source-heading"><strong>[${escapeHTML(e.id)}] ${escapeHTML(e.name)}</strong>${badge(e.state)}</div><blockquote>“${escapeHTML(e.text)}”</blockquote><p class="chat-source-meta">${date(e.review_date)} · Record ${escapeHTML(e.record_id)}</p></article>`).join('') || '<p>No supporting excerpts are available in this scope.</p>'}</div></details><details class="chat-answer-details"><summary>Counts and verification priorities [A1]</summary><p class="small muted">${escapeHTML(result.ranking_method)}</p><ol>${result.ranking.map(p=>`<li><strong>${escapeHTML(p.name)}</strong>: ${number(p.barrier_reports)} barrier / ${number(p.positive_reports)} positive / ${number(p.uncertain_reports)} mixed reports from ${number(p.sampled_reviews)} reviews analyzed.</li>`).join('') || '<li>No matching locations.</li>'}</ol><p class="small muted">[A1] Imported place-aspect counts in snapshot ${escapeHTML(result.snapshot_id || 'none')}.</p></details><details class="chat-answer-details"><summary>What to verify</summary><ul>${result.suggestions.map(s=>`<li>${escapeHTML(s)}</li>`).join('')}</ul></details><details class="chat-answer-details"><summary>Scope and method</summary><p>${escapeHTML(result.provider_note)}</p><p>${escapeHTML(result.context_note)}</p><p>${escapeHTML(result.notice)}</p><p class="small muted">Dataset: ${escapeHTML(result.dataset?.mode || 'none')} · Labels: ${escapeHTML(result.dataset?.label_mode || 'unspecified')} · Snapshot ${escapeHTML(result.snapshot_id || 'none')}.</p></details><p class="chat-caution">Historical reviews · Verify current conditions</p>`;
}

document.querySelectorAll('[data-chat-prompt]').forEach(button=>button.addEventListener('click',()=>{
  if (chatBusy) return;
  $('#chat-question').value=button.dataset.chatPrompt;
  $('#chat-form').requestSubmit();
}));

let chatTurnCount=0;
$('#chat-form').addEventListener('submit',async event=>{
  event.preventDefault();
  if (chatBusy) return;
  const feedback=$('#chat-feedback');
  feedback.hidden=true;
  if ($('#chat-selected').checked && !state.selected) {feedback.textContent='Select a location above, or turn off “Only the selected location”.';feedback.hidden=false;return;}
  const question=$('#chat-question').value.trim();
  if (!question) return;
  const payload={question,aspect:state.aspect,service:state.service,search:state.search,place_id:$('#chat-selected').checked ? state.selected : '',use_llm:$('#chat-llm').checked};
  const conversation=$('#chat-results');
  $('#chat-empty')?.remove();
  const turn=document.createElement('article');
  turn.className='chat-turn';
  turn.setAttribute('aria-label',`Question ${++chatTurnCount}`);
  turn.innerHTML=`<p class="chat-question-bubble">${escapeHTML(question)}</p><div class="chat-answer"><p class="chat-pending">Reading the review evidence…</p></div>`;
  conversation.append(turn);
  while (conversation.children.length>20) conversation.firstElementChild.remove();
  const reply=turn.querySelector('.chat-answer');
  const showTurn=()=>{conversation.scrollTop+=turn.getBoundingClientRect().top-conversation.getBoundingClientRect().top-20;};
  chatBusy=true;$('#chat-submit').disabled=true;conversation.setAttribute('aria-busy','true');
  document.querySelectorAll('[data-chat-prompt]').forEach(button=>{button.disabled=true;});
  $('#chat-question').value='';
  showTurn();
  try {
    const result=await api('/api/chat',{method:'POST',body:payload});
    reply.innerHTML=renderChatAnswer(result);
    showTurn();
  } catch(error) {
    reply.textContent=`Could not answer this question: ${error.message} You can try again below.`;
    reply.classList.add('chat-answer-error');
    if (!$('#chat-question').value) $('#chat-question').value=question;
  } finally {
    chatBusy=false;$('#chat-submit').disabled=false;conversation.setAttribute('aria-busy','false');
    document.querySelectorAll('[data-chat-prompt]').forEach(button=>{button.disabled=false;});
  }
});

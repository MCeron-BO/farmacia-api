// ----------------- Estado global -----------------
let map, markers = [];
let myPos = null;
let myPosMarker = null;          // marcador rojo de mi ubicación
let LAST_DRUG = localStorage.getItem("last_drug") || "";
let PENDING_PHARMACY_QUERY = null;
let lastPharmacyMode = "";       // "turno" | "cercanas" | ""

// ----------------- Indicador "pensando" (pastillas) -----------------
let typingNode = null;
function showThinking() {
  if (typingNode) return;
  const box = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'msg typing';
  div.id = 'typing';
  div.innerHTML = `
    <div class="typing-wrap">
      <div class="pills">
        <span class="pill" style="--d:0ms; --hd:0ms"></span>
        <span class="pill" style="--d:140ms; --hd:180ms"></span>
        <span class="pill" style="--d:280ms; --hd:360ms"></span>
      </div>
      <span class="thinking-text">Pensando…</span>
    </div>
  `;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  typingNode = div;
}
function hideThinking() {
  if (typingNode && typingNode.parentNode) typingNode.parentNode.removeChild(typingNode);
  typingNode = null;
}

// Triggers para detectar intención de farmacias en el cliente
const PHARMACY_TRIGGERS = [
  /farmacia/i, /farmacias/i, /de turno/i, /\bturno\b/i, /buscar.*farmacia/i, /farmacia.*cercan/i
];
function isPharmacyQuery(text){
  const t = (text || "").toLowerCase();
  return PHARMACY_TRIGGERS.some(r => r.test(t));
}

// ----------------- Utilidades de mapa -----------------
function mapWrap() { return document.querySelector('.mapwrap'); }
function mapIsVisible() {
  const w = mapWrap();
  return !!w && w.style.display !== 'none';
}
function showMap() {
  const w = mapWrap();
  if (!w) return;
  w.style.display = 'block';
  setTimeout(() => map.invalidateSize(), 120);
  const btn = document.getElementById('toggleMap');
  if (btn) { btn.textContent = '🗺️ Ocultar mapa'; btn.setAttribute('aria-pressed', 'true'); }
}
function hideMap() {
  const w = mapWrap();
  if (!w) return;
  w.style.display = 'none';
  const btn = document.getElementById('toggleMap');
  if (btn) { btn.textContent = '🗺️ Mostrar mapa'; btn.setAttribute('aria-pressed', 'false'); }
}
function toggleMap(){
  if (mapIsVisible()) hideMap(); else showMap();
}
function focusMap() {
  const w = mapWrap();
  if (!w) return;
  w.classList.add('pulse');
  w.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  setTimeout(() => w.classList.remove('pulse'), 1800);
}
function clearMarkers() {
  markers.forEach(m => { try { map.removeLayer(m); } catch(_){} });
  markers = [];
}
function fitMapToMarkers(maxZoom = 15) {
  if (!markers.length) return false;
  const group = L.featureGroup(markers);
  const bounds = group.getBounds();
  map.fitBounds(bounds.pad(0.18), { animate: true, maxZoom });
  setTimeout(() => { try { markers[0].openPopup(); } catch(e){} }, 350);
  return true;
}
function isDesktop() { return window.innerWidth >= 1024; }
function distanceMeters(a, b){
  return L.latLng(a[0], a[1]).distanceTo(L.latLng(b[0], b[1]));
}

// Iconos Leaflet (rojo para mi ubicación)
const RedIcon = new L.Icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png',
  iconRetinaUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
  iconSize: [25,41], iconAnchor: [12,41], popupAnchor: [1,-34], shadowSize:[41,41]
});

// Dibuja mi ubicación como marcador rojo (mismo estilo que farmacias)
function drawMyLocation(lat, lon){
  try { if (myPosMarker) map.removeLayer(myPosMarker); } catch(_) {}
  myPosMarker = L.marker([lat, lon], { icon: RedIcon }).addTo(map)
                 .bindPopup('Tu ubicación').openPopup();
}

// ----------------- Inicializa Leaflet (mapa oculto al inicio) -----------------
function initMap(){
  map = L.map('map').setView([-33.45, -70.66], 12);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap'
  }).addTo(map);
  window.map = map; // útil para depurar
  hideMap();

  // 👉 Permitir fijar/ajustar la ubicación manualmente con un click en el mapa
  map.on('click', (e) => {
    const { lat, lng } = e.latlng || {};
    if (lat == null || lng == null) return;

    // Guardar como nueva ubicación
    myPos = {
      lat: parseFloat(lat.toFixed(5)),
      lon: parseFloat(lng.toFixed(5)),
      acc: 0
    };

    showMap();
    drawMyLocation(myPos.lat, myPos.lon);
    map.setView([myPos.lat, myPos.lon], 14);

    // Feedback en el chat
    addMsg('Ubicación ajustada manualmente en el mapa.', false);

    // Si el usuario ya había buscado farmacias, reproducimos esa búsqueda con la nueva ubicación
    if (lastPharmacyMode === 'turno') {
      ask('farmacias de turno', myPos.lat, myPos.lon);
    } else if (lastPharmacyMode === 'cercanas') {
      ask('farmacias cercanas', myPos.lat, myPos.lon);
    }
  });
}
initMap();

// ----------------- Chat UI -----------------
function addMsg(text, me = false, ctas = []) {
  const box = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'msg' + (me ? ' me' : '');

  const hasTelemedCTA = Array.isArray(ctas) && ctas.some(c => c?.type === 'telemed');

  const urlRegex = /(https?:\/\/[^\s]+)/g;
  const raw = (text || '');
  const visibleText = hasTelemedCTA ? raw.replace(urlRegex, '').trim() : raw;
  const safeHTML = visibleText.replace(urlRegex, (u)=>'<a href="'+u+'" target="_blank" rel="noopener noreferrer">'+u+'</a>');

  const p = document.createElement('div');
  p.innerHTML = safeHTML || '&nbsp;';
  div.appendChild(p);

  if (!me && ctas && ctas.length){
    const row = document.createElement('div');
    row.className = 'cta-row';
    ctas.forEach((cta) => {
      const btn = document.createElement('button');
      btn.className = 'btn cta-btn';
      let label = cta.label || 'Abrir';
      if (cta.type === 'open_map') {
        const visible = mapIsVisible();
        label = visible ? 'Centrar en mapa' : 'Abrir mapa';
      }
      btn.textContent = label;
      btn.addEventListener('click', () => handleCta(cta));
      row.appendChild(btn);
    });
    div.appendChild(row);
  }

  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

// ----------------- CTA handler -----------------
function handleCta(cta){
  if(!cta || !cta.type) return;
  switch(cta.type){
    case 'telemed':
      if(cta.url) window.open(cta.url, '_blank', 'noopener,noreferrer');
      break;
    case 'use_location':
      getLocation();
      break;
    case 'open_map':
      if (!mapIsVisible()) showMap();
      if (isDesktop()) {
        const had = fitMapToMarkers(15);
        if (!had) focusMap();
      } else {
        focusMap();
        fitMapToMarkers(15);
      }
      break;
    case 'open_gmaps':
      if (cta.lat && cta.lon) {
        const url = `https://www.google.com/maps/dir/?api=1&destination=${cta.lat},${cta.lon}`;
        window.open(url, '_blank', 'noopener,noreferrer');
      }
      break;
    default:
      console.warn('CTA desconocido', cta);
  }
}

// ----------------- Backend -----------------
async function ask(msg, lat = null, lon = null) {
  const payload = { message: msg };
  if (lat != null && lon != null) { payload.lat = lat; payload.lon = lon; }
  if (LAST_DRUG) { payload.last_drug = LAST_DRUG; }

  showThinking(); // << mostrar indicador

  try{
    const r = await fetch('/chat/ask', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await r.json();

    // CTA(s)
    let ctas = [];
    if (data?.data?.ctas && Array.isArray(data.data.ctas)) ctas = data.data.ctas;
    else if (data?.data?.cta) ctas = [data.data.cta];

    // Suprimir encabezados genéricos de farmacias (luego daremos uno más humano)
    const reply = (data.reply || '').trim();
    const isPharmacyHeading =
      /^estas son (algunas )?farmacias cercanas\./i.test(reply) ||
      /^estas son las farmacias de turno cercanas/i.test(reply);

    if (!isPharmacyHeading) {
      addMsg(reply || '(sin respuesta)', false, ctas);
    }

    // Persistir last_drug
    const maybeDrug = data?.data?.last_drug ||
                      data?.data?.match?.name_es ||
                      data?.data?.match?.generic_name_es ||
                      data?.data?.match?.name || '';
    if (maybeDrug && maybeDrug !== LAST_DRUG){
      LAST_DRUG = maybeDrug;
      localStorage.setItem('last_drug', LAST_DRUG);
    }

    // Pintar farmacias
    if (data.data && data.data.pharmacies) {
      lastPharmacyMode = data.data.pharmacy_mode || lastPharmacyMode || '';
      clearMarkers();

      // Mostrar mapa si llega resultado de farmacias
      if (!mapIsVisible()) showMap();

      data.data.pharmacies.forEach(p=>{
        if (!p.lat || !p.long) return;
        const m = L.marker([parseFloat(p.lat), parseFloat(p.long)]).addTo(map);
        const gmaps = `https://www.google.com/maps/dir/?api=1&destination=${p.lat},${p.long}`;
        const dist = (p.dist_km != null) ? `${p.dist_km} km` : '';
        const name = p.local_nombre || 'Farmacia';
        const comuna = p.comuna_nombre || '';
        const dir = p.direccion || '';
        const tel = p.telefono || '';
        m.bindPopup(
          `<b>${name}</b><br>${comuna}<br>${dir}<br>${tel ? 'Tel: ' + tel + '<br>' : ''}` +
          `<a href="${gmaps}" target="_blank" rel="noopener noreferrer">Cómo llegar</a><br>${dist}`
        );
        markers.push(m);
      });

      // Ajustar vista
      if (myPos && markers.length) {
        const me = [myPos.lat, myPos.lon];
        let best = markers[0].getLatLng();
        let bestD = distanceMeters(me, [best.lat, best.lng]);
        markers.forEach(mk=>{
          const ll = mk.getLatLng();
          const d = distanceMeters(me, [ll.lat, ll.lng]);
          if (d < bestD) { bestD = d; best = ll; }
        });
        const bounds = L.latLngBounds([L.latLng(me[0], me[1]), L.latLng(best.lat, best.lng)]);
        map.fitBounds(bounds.pad(0.25), { animate:true, maxZoom: 15 });
        setTimeout(()=> {
          try {
            const nearest = markers.find(mk => mk.getLatLng().equals(best));
            nearest && nearest.openPopup();
          } catch(_) {}
        }, 350);
      } else {
        fitMapToMarkers(14);
      }

      // Mensaje amable sustituto
      if (lastPharmacyMode === 'turno') {
        addMsg('Esta es la farmacia de turno más cercana a ti.', false);
      } else {
        addMsg('Estas son las farmacias más cercanas a tu ubicación.', false);
      }
    }
  }catch(err){
    addMsg('Error al consultar el backend: ' + (err?.message || err), false);
  } finally {
    hideThinking(); // << ocultar indicador siempre
  }
}

// ----------------- Listeners -----------------
document.getElementById('send').onclick = async () => {
  const input = document.getElementById('msg');
  const v = input.value.trim();
  if (!v) return;

  // Si es consulta de farmacias y no hay ubicación -> NO llamamos backend
  if (isPharmacyQuery(v) && !myPos){
    addMsg(
      "Para mostrar farmacias cercanas o de turno necesito tu ubicación.",
      false,
      [{ type:'use_location', label:'Usar mi ubicación' }]
    );
    PENDING_PHARMACY_QUERY = v; // recuerda intención
    input.value = '';
    input.focus();
    return;
  }

  addMsg(v, true);
  input.value = '';
  await ask(v, myPos?.lat ?? null, myPos?.lon ?? null);
  input.focus();
};

document.getElementById('msg').addEventListener('keydown', (e)=>{
  if(e.key === 'Enter' && !e.shiftKey){
    e.preventDefault();
    document.getElementById('send').click();
  }
});

// Chips (sugerencias)
document.querySelectorAll('.chip[data-prompt]').forEach(chip=>{
  chip.addEventListener('click', ()=>{
    const v = chip.getAttribute('data-prompt') || '';
    const input = document.getElementById('msg');
    input.value = v;
    document.getElementById('send').click();
  });
});

// Ubicación (solo botón grande de la izquierda)
function onAskPendingAfterLocation(){
  if (PENDING_PHARMACY_QUERY){
    const q = PENDING_PHARMACY_QUERY;
    PENDING_PHARMACY_QUERY = null;
    document.getElementById('msg').value = q;
    document.getElementById('send').click();
  }
}
function getLocation(){
  if (!navigator.geolocation){ alert('Geolocalización no soportada'); return; }
  navigator.geolocation.getCurrentPosition(pos=>{
    myPos = {
      lat: parseFloat(pos.coords.latitude.toFixed(4)),
      lon: parseFloat(pos.coords.longitude.toFixed(4)),
      acc: pos.coords.accuracy || 0
    };
    showMap();
    drawMyLocation(myPos.lat, myPos.lon);
    map.setView([myPos.lat, myPos.lon], 14);
    focusMap();
    onAskPendingAfterLocation();
  }, err => alert('No se pudo obtener ubicación: ' + err.message));
}
document.getElementById('loc2')?.addEventListener('click', getLocation);

// Botón "Mapa" (mostrar/ocultar panel)
document.getElementById('toggleMap')?.addEventListener('click', toggleMap);

// Botón "Limpiar chat"
(function bindReset(){
  const btn = document.getElementById('resetCtx') || document.getElementById('clearCtx');
  if (!btn) return;
  btn.addEventListener('click', ()=>{
    LAST_DRUG = '';
    localStorage.removeItem('last_drug');
    PENDING_PHARMACY_QUERY = null;
    lastPharmacyMode = '';
    document.getElementById('messages').innerHTML = '';
    clearMarkers();
    try { if (myPosMarker) map.removeLayer(myPosMarker); } catch(_) {}
    myPosMarker = null;
    myPos = null;
    hideThinking(); // por si estaba visible
    hideMap();
    addMsg('Historial limpiado. ¿En qué puedo ayudarle?');
  });
})();

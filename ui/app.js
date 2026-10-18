'use strict';
// Vanilla-JS ohne Build: Hash-Routing, jede Ansicht ist eine Funktion. Alle dynamischen Texte laufen durch esc().
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const fmt = (x, d) => (x ?? 0).toLocaleString('de-DE', {minimumFractionDigits: d, maximumFractionDigits: d});
const eur = x => x == null ? 'kein Preis' : fmt(x, 2) + ' €';
const eur0 = x => fmt(Math.round(x), 0) + ' €';
const eurMin = x => fmt(x, x % 1 ? 2 : 0) + ' €';
const signc = x => (x < 0 ? '−' : '+') + eur(Math.abs(x));
const signc0 = x => (x < 0 ? '−' : '+') + eur0(Math.abs(x));
const num = n => (n ?? 0).toLocaleString('de-DE');
const plural = (n, one, many) => `${num(n)} ${n === 1 ? one : many}`;
const karten = n => plural(n, 'Karte', 'Karten');
const small = u => u && u.replace('/normal/', '/small/');
const art = u => u && u.replace('/normal/', '/art_crop/');
const day = iso => !iso ? 'unbekannt' : new Date(iso).toDateString() === new Date().toDateString() ? 'heute' : new Date(iso).toLocaleDateString('de-DE');
const APP = $('.brand').textContent.trim();  // der Name steht nur in index.html (und version.py)
class LoginNoetig extends Error {}
const api = async (path, opts = {}) => {
  const r = await fetch('/api/' + path, {...opts, headers: {'X-Mtg': '1', ...opts.headers}});
  const j = await r.json().catch(() => ({error: r.statusText}));
  if (r.status === 401 && j.login) { showLogin(); throw new LoginNoetig(j.error); }  // Sitzung abgelaufen oder abgemeldet
  if (!r.ok) throw Object.assign(new Error(j.error || r.statusText), {fertig: !!j.fertig, quelle: j.quelle});  // fertig: Die Einrichtung ist abgeschlossen (Phase 43)
  return j;
};
const post = (path, obj) => api(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(obj ?? {})});

// Icons: Phosphor (MIT, ui/icons-LICENSE.txt), Schnitt Bold, 256er Raster; hier nur die Pfade, das <svg> baut icon()
const ICONS = {plus: '<path d="M228,128a12,12,0,0,1-12,12H140v76a12,12,0,0,1-24,0V140H40a12,12,0,0,1,0-24h76V40a12,12,0,0,1,24,0v76h76A12,12,0,0,1,228,128Z"/>',
  minus: '<path d="M228,128a12,12,0,0,1-12,12H40a12,12,0,0,1,0-24H216A12,12,0,0,1,228,128Z"/>',
  x: '<path d="M208.49,191.51a12,12,0,0,1-17,17L128,145,64.49,208.49a12,12,0,0,1-17-17L111,128,47.51,64.49a12,12,0,0,1,17-17L128,111l63.51-63.52a12,12,0,0,1,17,17L145,128Z"/>',
  search: '<path d="M232.49,215.51,185,168a92.12,92.12,0,1,0-17,17l47.53,47.54a12,12,0,0,0,17-17ZM44,112a68,68,0,1,1,68,68A68.07,68.07,0,0,1,44,112Z"/>',
  upload: '<path d="M228,144v64a12,12,0,0,1-12,12H40a12,12,0,0,1-12-12V144a12,12,0,0,1,24,0v52H204V144a12,12,0,0,1,24,0ZM96.49,80.49,116,61v83a12,12,0,0,0,24,0V61l19.51,19.52a12,12,0,1,0,17-17l-40-40a12,12,0,0,0-17,0l-40,40a12,12,0,1,0,17,17Z"/>',
  download: '<path d="M228,144v64a12,12,0,0,1-12,12H40a12,12,0,0,1-12-12V144a12,12,0,0,1,24,0v52H204V144a12,12,0,0,1,24,0Zm-108.49,8.49a12,12,0,0,0,17,0l40-40a12,12,0,0,0-17-17L140,115V32a12,12,0,0,0-24,0v83L96.49,95.51a12,12,0,0,0-17,17Z"/>',
  external: '<path d="M228,104a12,12,0,0,1-24,0V69l-59.51,59.51a12,12,0,0,1-17-17L187,52H152a12,12,0,0,1,0-24h64a12,12,0,0,1,12,12Zm-44,24a12,12,0,0,0-12,12v64H52V84h64a12,12,0,0,0,0-24H48A20,20,0,0,0,28,80V208a20,20,0,0,0,20,20H176a20,20,0,0,0,20-20V140A12,12,0,0,0,184,128Z"/>',
  arrow: '<path d="M224.49,136.49l-72,72a12,12,0,0,1-17-17L187,140H40a12,12,0,0,1,0-24H187L135.51,64.48a12,12,0,0,1,17-17l72,72A12,12,0,0,1,224.49,136.49Z"/>',
  left: '<path d="M168.49,199.51a12,12,0,0,1-17,17l-80-80a12,12,0,0,1,0-17l80-80a12,12,0,0,1,17,17L97,128Z"/>',
  right: '<path d="M184.49,136.49l-80,80a12,12,0,0,1-17-17L159,128,87.51,56.49a12,12,0,1,1,17-17l80,80A12,12,0,0,1,184.49,136.49Z"/>',
  help: '<path d="M144,180a16,16,0,1,1-16-16A16,16,0,0,1,144,180Zm92-52A108,108,0,1,1,128,20,108.12,108.12,0,0,1,236,128Zm-24,0a84,84,0,1,0-84,84A84.09,84.09,0,0,0,212,128ZM128,64c-24.26,0-44,17.94-44,40v4a12,12,0,0,0,24,0v-4c0-8.82,9-16,20-16s20,7.18,20,16-9,16-20,16a12,12,0,0,0-12,12v8a12,12,0,0,0,23.73,2.56C158.31,137.88,172,122.37,172,104,172,81.94,152.26,64,128,64Z"/>',
  info: '<path d="M108,84a16,16,0,1,1,16,16A16,16,0,0,1,108,84Zm128,44A108,108,0,1,1,128,20,108.12,108.12,0,0,1,236,128Zm-24,0a84,84,0,1,0-84,84A84.09,84.09,0,0,0,212,128Zm-72,36.68V132a20,20,0,0,0-20-20,12,12,0,0,0-4,23.32V168a20,20,0,0,0,20,20,12,12,0,0,0,4-23.32Z"/>',
  printer: '<path d="M214.67,68H204V40a12,12,0,0,0-12-12H64A12,12,0,0,0,52,40V68H41.33C25.16,68,12,80.56,12,96v80a12,12,0,0,0,12,12H52v28a12,12,0,0,0,12,12H192a12,12,0,0,0,12-12V188h28a12,12,0,0,0,12-12V96C244,80.56,230.84,68,214.67,68ZM76,52H180V68H76ZM180,204H76V172H180Zm40-40H204v-4a12,12,0,0,0-12-12H64a12,12,0,0,0-12,12v4H36V96c0-2.17,2.44-4,5.33-4H214.67c2.89,0,5.33,1.83,5.33,4Zm-16-44a16,16,0,1,1-16-16A16,16,0,0,1,204,120Z"/>',
  trash: '<path d="M216,48H180V36A28,28,0,0,0,152,8H104A28,28,0,0,0,76,36V48H40a12,12,0,0,0,0,24h4V208a20,20,0,0,0,20,20H192a20,20,0,0,0,20-20V72h4a12,12,0,0,0,0-24ZM100,36a4,4,0,0,1,4-4h48a4,4,0,0,1,4,4V48H100Zm88,168H68V72H188ZM116,104v64a12,12,0,0,1-24,0V104a12,12,0,0,1,24,0Zm48,0v64a12,12,0,0,1-24,0V104a12,12,0,0,1,24,0Z"/>',
  refresh: '<path d="M228,48V96a12,12,0,0,1-12,12H168a12,12,0,0,1,0-24h19l-7.8-7.8a75.55,75.55,0,0,0-53.32-22.26h-.43A75.49,75.49,0,0,0,72.39,75.57,12,12,0,1,1,55.61,58.41a99.38,99.38,0,0,1,69.87-28.47H126A99.42,99.42,0,0,1,196.2,59.23L204,67V48a12,12,0,0,1,24,0ZM183.61,180.43a75.49,75.49,0,0,1-53.09,21.63h-.43A75.55,75.55,0,0,1,76.77,179.8L69,172H88a12,12,0,0,0,0-24H40a12,12,0,0,0-12,12v48a12,12,0,0,0,24,0V189l7.8,7.8A99.42,99.42,0,0,0,130,226.06h.56a99.38,99.38,0,0,0,69.87-28.47,12,12,0,0,0-16.78-17.16Z"/>',
  layers: '<path d="M234.36,170A12,12,0,0,1,230,186.37l-96,56a12,12,0,0,1-12.1,0l-96-56a12,12,0,0,1,12.09-20.74l90,52.48L218,165.63A12,12,0,0,1,234.36,170ZM218,117.63,128,170.11,38.05,117.63A12,12,0,0,0,26,138.37l96,56a12,12,0,0,0,12.1,0l96-56A12,12,0,0,0,218,117.63ZM20,80a12,12,0,0,1,6-10.37l96-56a12.06,12.06,0,0,1,12.1,0l96,56a12,12,0,0,1,0,20.74l-96,56a12,12,0,0,1-12.1,0l-96-56A12,12,0,0,1,20,80Zm35.82,0L128,122.11,200.18,80,128,37.89Z"/>',
  up: '<path d="M244,56v64a12,12,0,0,1-24,0V85l-75.51,75.52a12,12,0,0,1-17,0L96,129,32.49,192.49a12,12,0,0,1-17-17l72-72a12,12,0,0,1,17,0L136,135l67-67H168a12,12,0,0,1,0-24h64A12,12,0,0,1,244,56Z"/>',
  down: '<path d="M244,128v64a12,12,0,0,1-12,12H168a12,12,0,0,1,0-24h35l-67-67-31.51,31.52a12,12,0,0,1-17,0l-72-72a12,12,0,0,1,17-17L96,119l31.51-31.52a12,12,0,0,1,17,0L220,163V128a12,12,0,0,1,24,0Z"/>',
  euro: '<path d="M192.94,189.66a12,12,0,0,1-.94,17A84,84,0,0,1,53.55,160H40a12,12,0,0,1,0-24H52V120H40a12,12,0,0,1,0-24H53.55A84,84,0,0,1,192,49.39a12,12,0,0,1-16,17.89A60,60,0,0,0,78.18,96H136a12,12,0,0,1,0,24H76v16h44a12,12,0,0,1,0,24H78.18A60,60,0,0,0,176,188.72,12,12,0,0,1,192.94,189.66Z"/>',
  alert: '<path d="M240.26,186.1,152.81,34.23h0a28.74,28.74,0,0,0-49.62,0L15.74,186.1a27.45,27.45,0,0,0,0,27.71A28.31,28.31,0,0,0,40.55,228h174.9a28.31,28.31,0,0,0,24.79-14.19A27.45,27.45,0,0,0,240.26,186.1Zm-20.8,15.7a4.46,4.46,0,0,1-4,2.2H40.55a4.46,4.46,0,0,1-4-2.2,3.56,3.56,0,0,1,0-3.73L124,46.2a4.77,4.77,0,0,1,8,0l87.44,151.87A3.56,3.56,0,0,1,219.46,201.8ZM116,136V104a12,12,0,0,1,24,0v32a12,12,0,0,1-24,0Zm28,40a16,16,0,1,1-16-16A16,16,0,0,1,144,176Z"/>',
  infinity: '<path d="M252,128a60,60,0,0,1-102.43,42.43l-.49-.53L89.22,102.31a36,36,0,1,0,0,51.38l3.08-3.48a12,12,0,1,1,18,15.91l-3.35,3.78-.49.53a60,60,0,1,1,0-84.86l.49.53,59.86,67.59a36,36,0,1,0,0-51.38l-3.08,3.48a12,12,0,1,1-18-15.91l3.35-3.78.49-.53A60,60,0,0,1,252,128Z"/>',
  paste: '<path d="M172,164a12,12,0,0,1-12,12H96a12,12,0,0,1,0-24h64A12,12,0,0,1,172,164Zm-12-52H96a12,12,0,0,0,0,24h64a12,12,0,0,0,0-24Zm60-64V216a20,20,0,0,1-20,20H56a20,20,0,0,1-20-20V48A20,20,0,0,1,56,28H90.53a51.88,51.88,0,0,1,74.94,0H200A20,20,0,0,1,220,48ZM100.29,60h55.42a28,28,0,0,0-55.42,0ZM196,52H178.59A52.13,52.13,0,0,1,180,64v8a12,12,0,0,1-12,12H88A12,12,0,0,1,76,72V64a52.13,52.13,0,0,1,1.41-12H60V212H196Z"/>',
  sheet: '<path d="M160,208a12,12,0,0,1-12,12H120a12,12,0,0,1-12-12V152a12,12,0,0,1,24,0v44h16A12,12,0,0,1,160,208ZM91,142.22A12,12,0,0,0,74.24,145L64,159.34,53.77,145a12,12,0,1,0-19.53,14l15,21-15,21A12,12,0,1,0,53.77,215L64,200.62,74.24,215A12,12,0,0,0,93.77,201l-15-21,15-21A12,12,0,0,0,91,142.22Zm122.53,32.05c-5.12-3.45-11.32-5.24-16.79-6.82a79.69,79.69,0,0,1-7.92-2.59c2.45-1.18,9.71-1.3,16.07.33A12,12,0,0,0,211,142a69,69,0,0,0-12-1.86c-9.93-.66-18,1.08-24.1,5.17a24.45,24.45,0,0,0-10.69,17.76c-1.1,8.74,2.49,16.27,10.11,21.19,4.78,3.09,10.36,4.7,15.75,6.26,3,.89,7.94,2.3,9.88,3.53a2.48,2.48,0,0,1-.21.71c-1.37,1.55-9.58,1.79-16.39-.06a12,12,0,1,0-6.46,23.11A63.75,63.75,0,0,0,193.1,220c6.46,0,13.73-1.17,19.73-5.15a24.73,24.73,0,0,0,10.95-18C225,187.53,221.33,179.53,213.51,174.27ZM36,108V40A20,20,0,0,1,56,20h96a12,12,0,0,1,8.49,3.51l56,56A12,12,0,0,1,220,88v20a12,12,0,1,1-24,0v-4H148a12,12,0,0,1-12-12V44H60v64a12,12,0,1,1-24,0ZM160,80h23L160,57Z"/>',
  csv: '<path d="M48,180c0,8.67,5.49,16,12,16a10.27,10.27,0,0,0,7.33-3.43,12,12,0,1,1,17.34,16.6A34,34,0,0,1,60,220C40.15,220,24,202,24,180s16.15-40,36-40a34,34,0,0,1,24.67,10.83,12,12,0,1,1-17.34,16.6A10.27,10.27,0,0,0,60,164C53.49,164,48,171.31,48,180Zm97.51-5.71c-5.13-3.45-11.33-5.24-16.8-6.82a79.5,79.5,0,0,1-7.91-2.59c2.45-1.18,9.71-1.3,16.07.33A12,12,0,0,0,143,142a69.24,69.24,0,0,0-12-1.86c-9.93-.66-18,1.08-24.1,5.17a24.45,24.45,0,0,0-10.69,17.76c-1.1,8.74,2.48,16.27,10.11,21.19,4.78,3.09,10.36,4.7,15.75,6.26,3,.89,7.94,2.3,9.88,3.53a2,2,0,0,1-.22.71c-1.36,1.55-9.57,1.79-16.39-.06a12,12,0,0,0-6.45,23.11A63.73,63.73,0,0,0,125.09,220c6.47,0,13.74-1.17,19.74-5.15a24.73,24.73,0,0,0,10.95-18C157,187.53,153.32,179.53,145.51,174.27ZM216,140.68A12,12,0,0,0,200.7,148L192,172.3,183.3,148A12,12,0,1,0,160.7,156l20,56a12,12,0,0,0,22.6,0l20-56A12,12,0,0,0,216,140.68ZM36,108V40A20,20,0,0,1,56,20h96a12,12,0,0,1,8.49,3.51l56,56A12,12,0,0,1,220,88v20a12,12,0,1,1-24,0v-4H148a12,12,0,0,1-12-12V44H60v64a12,12,0,1,1-24,0ZM160,80h23L160,57Z"/>',
  text: '<path d="M48,120a12,12,0,0,0,12-12V44h76V92a12,12,0,0,0,12,12h48v4a12,12,0,0,0,24,0V88a12,12,0,0,0-3.51-8.49l-56-56A12,12,0,0,0,152,20H56A20,20,0,0,0,36,40v68A12,12,0,0,0,48,120ZM183,80H160V57Zm-25.27,79-15,21,15,21A12,12,0,1,1,138.24,215L128,200.65,117.76,215A12,12,0,1,1,98.24,201l15-21-15-21A12,12,0,1,1,117.76,145L128,159.35,138.24,145A12,12,0,1,1,157.76,159ZM92,152a12,12,0,0,1-12,12H72v44a12,12,0,0,1-24,0V164H40a12,12,0,0,1,0-24H80A12,12,0,0,1,92,152Zm136,0a12,12,0,0,1-12,12h-8v44a12,12,0,0,1-24,0V164h-8a12,12,0,0,1,0-24h40A12,12,0,0,1,228,152Z"/>',
  check: '<path d="M232.49,80.49l-128,128a12,12,0,0,1-17,0l-56-56a12,12,0,1,1,17-17L96,183,215.51,63.51a12,12,0,0,1,17,17Z"/>',
  crown: '<path d="M252,80a32,32,0,1,0-60,15.45l-20.86,25.66L150.82,74.4a32,32,0,1,0-45.64,0L84.87,121.11,64,95.45a32,32,0,1,0-35,15.78l14,84.06A19.94,19.94,0,0,0,62.78,212H193.22A19.94,19.94,0,0,0,213,195.29l14-84.06A32.05,32.05,0,0,0,252,80Zm-32-8a8,8,0,1,1-8,8A8,8,0,0,1,220,72ZM128,44a8,8,0,1,1-8,8A8,8,0,0,1,128,44ZM36,72a8,8,0,1,1-8,8A8,8,0,0,1,36,72ZM189.83,188H66.17L55.29,122.78l23.4,28.79A12,12,0,0,0,88,156a12.87,12.87,0,0,0,1.63-.11,12,12,0,0,0,9.37-7.1L127.18,84l.82,0,.82,0L157,148.79a12,12,0,0,0,9.37,7.1A12.87,12.87,0,0,0,168,156a12,12,0,0,0,9.31-4.43l23.4-28.79Z"/>',
  cloud: '<path d="M192.49,167.51a12,12,0,0,1,0,17l-32,32a12,12,0,0,1-17,0l-32-32a12,12,0,1,1,17-17L140,179V128a12,12,0,0,1,24,0v51l11.51-11.52A12,12,0,0,1,192.49,167.51ZM160,36A92.08,92.08,0,0,0,79,84.37,68,68,0,1,0,72,220H84a12,12,0,0,0,0-24H72a44,44,0,0,1-1.81-87.95A91.7,91.7,0,0,0,68,128a12,12,0,0,0,24,0,68,68,0,0,1,136,0,67.27,67.27,0,0,1-7.25,30.59,12,12,0,1,0,21.42,10.82A91.08,91.08,0,0,0,252,128,92.1,92.1,0,0,0,160,36Z"/>',
  cards: '<path d="M180,72H36A20,20,0,0,0,16,92V204a20,20,0,0,0,20,20H180a20,20,0,0,0,20-20V92A20,20,0,0,0,180,72Zm-4,128H40V96H176ZM240,52V176a12,12,0,0,1-24,0V56H64a12,12,0,0,1,0-24H220A20,20,0,0,1,240,52Z"/>',
  flashlight: '<path d="M184,12H72A20,20,0,0,0,52,32V77.33a20.12,20.12,0,0,0,4,12L76,116V224a20,20,0,0,0,20,20h64a20,20,0,0,0,20-20V116l20-26.67a20.12,20.12,0,0,0,4-12V32A20,20,0,0,0,184,12Zm-4,24V52H76V36Zm-20,66.67a20.12,20.12,0,0,0-4,12V220H100V114.67a20.12,20.12,0,0,0-4-12L76,76H180ZM140,120v32a12,12,0,0,1-24,0V120a12,12,0,0,1,24,0Z"/>',
  tray: '<path d="M208,28H48A20,20,0,0,0,28,48V208a20,20,0,0,0,20,20H208a20,20,0,0,0,20-20V48A20,20,0,0,0,208,28Zm-4,24v92H179.31a19.86,19.86,0,0,0-14.14,5.86L147,168H109L90.83,149.86A19.86,19.86,0,0,0,76.69,144H52V52ZM52,204V168H75l18.14,18.14A19.86,19.86,0,0,0,107.31,192h41.38a19.86,19.86,0,0,0,14.14-5.86L181,168h23v36Zm35.51-87.51a12,12,0,0,1,17-17L116,111V76a12,12,0,0,1,24,0v35l11.51-11.52a12,12,0,0,1,17,17l-32,32a12,12,0,0,1-17,0Z"/>'};
// Manasymbole: Phosphor Fill (Sonne, Tropfen, Totenkopf, Flamme, Baum; Raute = farblos, drei Kreise = mehrfarbig) auf den Pastelltönen der Kartensymbole
const MANA = {W: '<path d="M120,40V16a8,8,0,0,1,16,0V40a8,8,0,0,1-16,0Zm8,24a64,64,0,1,0,64,64A64.07,64.07,0,0,0,128,64ZM58.34,69.66A8,8,0,0,0,69.66,58.34l-16-16A8,8,0,0,0,42.34,53.66Zm0,116.68-16,16a8,8,0,0,0,11.32,11.32l16-16a8,8,0,0,0-11.32-11.32ZM192,72a8,8,0,0,0,5.66-2.34l16-16a8,8,0,0,0-11.32-11.32l-16,16A8,8,0,0,0,192,72Zm5.66,114.34a8,8,0,0,0-11.32,11.32l16,16a8,8,0,0,0,11.32-11.32ZM48,128a8,8,0,0,0-8-8H16a8,8,0,0,0,0,16H40A8,8,0,0,0,48,128Zm80,80a8,8,0,0,0-8,8v24a8,8,0,0,0,16,0V216A8,8,0,0,0,128,208Zm112-88H216a8,8,0,0,0,0,16h24a8,8,0,0,0,0-16Z"/>',
  U: '<path d="M174,47.75a254.19,254.19,0,0,0-41.45-38.3,8,8,0,0,0-9.18,0A254.19,254.19,0,0,0,82,47.75C54.51,79.32,40,112.6,40,144a88,88,0,0,0,176,0C216,112.6,201.49,79.32,174,47.75Zm9.85,105.59a57.6,57.6,0,0,1-46.56,46.55A8.75,8.75,0,0,1,136,200a8,8,0,0,1-1.32-15.89c16.57-2.79,30.63-16.85,33.44-33.45a8,8,0,0,1,15.78,2.68Z"/>',
  B: '<path d="M128,16C70.65,16,24,60.86,24,116c0,34.1,18.27,66,48,84.28V216a16,16,0,0,0,16,16h8a4,4,0,0,0,4-4V200.27a8.17,8.17,0,0,1,7.47-8.25,8,8,0,0,1,8.53,8v28a4,4,0,0,0,4,4h16a4,4,0,0,0,4-4V200.27a8.17,8.17,0,0,1,7.47-8.25,8,8,0,0,1,8.53,8v28a4,4,0,0,0,4,4h8a16,16,0,0,0,16-16V200.28C213.73,182,232,150.1,232,116,232,60.86,185.35,16,128,16ZM92,152a20,20,0,1,1,20-20A20,20,0,0,1,92,152Zm72,0a20,20,0,1,1,20-20A20,20,0,0,1,164,152Z"/>',
  R: '<path d="M143.38,17.85a8,8,0,0,0-12.63,3.41l-22,60.41L84.59,58.26a8,8,0,0,0-11.93.89C51,87.53,40,116.08,40,144a88,88,0,0,0,176,0C216,84.55,165.21,36,143.38,17.85Zm40.51,135.49a57.6,57.6,0,0,1-46.56,46.55A7.65,7.65,0,0,1,136,200a8,8,0,0,1-1.32-15.89c16.57-2.79,30.63-16.85,33.44-33.45a8,8,0,0,1,15.78,2.68Z"/>',
  G: '<path d="M128,187.85a72.44,72.44,0,0,0,8,4.62V232a8,8,0,0,1-16,0V192.47A72.44,72.44,0,0,0,128,187.85ZM198.1,62.59a76,76,0,0,0-140.2,0A71.71,71.71,0,0,0,16,127.8C15.9,166,48,199,86.14,200A72.22,72.22,0,0,0,120,192.47V156.94L76.42,135.16a8,8,0,1,1,7.16-14.32L120,139.06V88a8,8,0,0,1,16,0v27.06l36.42-18.22a8,8,0,1,1,7.16,14.32L136,132.94v59.53A72.17,72.17,0,0,0,168,200l1.82,0C208,199,240.11,166,240,127.8A71.71,71.71,0,0,0,198.1,62.59Z"/>',
  C: '<path d="M240,128a15.85,15.85,0,0,1-4.67,11.28l-96.05,96.06a16,16,0,0,1-22.56,0h0l-96-96.06a16,16,0,0,1,0-22.56l96.05-96.06a16,16,0,0,1,22.56,0l96.05,96.06A15.85,15.85,0,0,1,240,128Z"/>',
  M: '<path d="M128,120a44,44,0,1,1,44-44A44.05,44.05,0,0,1,128,120Zm60,8a44,44,0,1,0,44,44A44.05,44.05,0,0,0,188,128ZM68,128a44,44,0,1,0,44,44A44.05,44.05,0,0,0,68,128Z"/>'};
const svg = (paths, cls) => `<svg${cls ? ` class="${cls}"` : ''} viewBox="0 0 256 256" fill="currentColor" aria-hidden="true" focusable="false">${paths}</svg>`;
const icon = (n, cls = '') => svg(ICONS[n], 'i' + (cls ? ' ' + cls : ''));

const main = $('#main'), dlg = $('#dlg');
const COLORS = {W: 'Weiß', U: 'Blau', B: 'Schwarz', R: 'Rot', G: 'Grün', M: 'Mehrfarbig', C: 'Farblos'};
const STACKS = ['deck', 'keep', 'sell', 'bulk'];
const LABEL = {deck: 'Deck', keep: 'Behalten', sell: 'Verkaufen', bulk: 'Bulk'};
const LANG = {en: 'Englisch', de: 'Deutsch', fr: 'Französisch', it: 'Italienisch', es: 'Spanisch', pt: 'Portugiesisch', ja: 'Japanisch', ko: 'Koreanisch', ru: 'Russisch', zh_CN: 'Chinesisch', zh_TW: 'Chinesisch (trad.)'};
const COND = {mint: 'Mint', near_mint: 'Near Mint', excellent: 'Excellent', good: 'Good', light_played: 'Light Played', played: 'Played', poor: 'Poor'};
// Erklärungen an einer Stelle: erscheinen als Tooltip an den kleinen ?-Knöpfen und in der Hilfe
const TIP = {
  arena: 'Diese Drucke gibt es nur digital in MTG Arena, deshalb haben sie keinen Euro-Preis. Die Scanner-App (zum Beispiel ManaBox) hat beim Scannen wohl den Druck mit dem gleichen Bild erwischt. Dort den Papier-Druck wählen (meist die ursprüngliche Serie) und neu exportieren.',
  scan: 'Ganze Karte ruhig und aufrecht vor die Kamera, gleichmäßiges Licht, möglichst ohne Spiegelung. Erkannt werden nur Karten aus deiner Sammlung. Das Kamerabild bleibt auf diesem Gerät. Dein Handy geht als Kamera, wenn Windows es als virtuelle Kamera anbietet.',
  scanhttps: 'Die Kamera gibt der Browser nur direkt auf diesem Rechner (127.0.0.1) oder über https frei. Auf dem Handy also die Adresse über Tailscale oder deine Domain öffnen.',
  erfassen: 'Ganze Karte ruhig und aufrecht vor die Kamera, gleichmäßiges Licht, möglichst ohne Spiegelung. Erkannt werden die Drucke der gewählten Sets. Jede erkannte Karte kommt auf die Scan-Liste; nimm sie aus dem Bild, die nächste zählt, sobald kurz keine Karte zu sehen war. Das Kamerabild bleibt auf diesem Gerät, solange „Messbilder speichern“ aus ist.',
  messbilder: 'Zum Messen der Erkennung: Ist der Schalter an, geht zu jeder gezählten Karte das Kamerabild an deinen Server und nur dorthin, mit der Karte als Etikett. Korrigierst du die Karte auf der Scan-Liste, zieht das Etikett nach; nimmst du sie von der Liste, steht das Bild unter „noch zuordnen“. Messbilder sind Testdaten: Sie stehen nicht in der Sicherung, und du löschst sie einzeln oder alle.',
  messausloeser: '„Bild aufnehmen“ speichert das Kamerabild ohne Erkennung, die Karte ordnest du danach zu. Für Karten außerhalb der gewählten Sets, für schwere Fälle und für Karten frei im Bild: schräg, klein, am Rand, in der Hand.',
  scanliste: 'Erkannte Karten landen zuerst hier, noch nicht in deiner Sammlung. Prüf die Liste: doppelt gescannte mit Minus wegnehmen, eine falsch erkannte antippen und die richtige wählen (die Kandidaten der Kamera und alle Drucke dieser Karte stehen da, sonst suchen), Foil, Sprache, Zustand oder Menge ändern. Erst „übernehmen“ legt alles in den Binder. Die Liste liegt auf dem Server und bleibt, auch wenn du die Seite schließt oder später am Rechner weitermachst. Steht „Druck prüfen“ an einer Zeile, gibt es ihr Bild in mehreren Drucken und die App hat einen gewählt: antippen und den richtigen nehmen.',
  erfassenAlle: 'Ganze Karte ruhig und aufrecht vor die Kamera, gleichmäßiges Licht, möglichst ohne Spiegelung. Die App vergleicht mit allen Karten, ein Set musst du nicht wählen. Jede erkannte Karte kommt auf die Scan-Liste; nimm sie aus dem Bild, die nächste zählt, sobald kurz keine Karte zu sehen war. Das Kamerabild bleibt auf diesem Gerät, solange „Messbilder speichern“ aus ist: An den Server geht nur ein Fingerabdruck der Karte, ein paar Kilobyte.',
  ohneset: '„Nur gewählte Sets“: Der Vergleich läuft auf diesem Gerät und kennt nur die Drucke der gewählten Sets. „Alle Karten, ohne Set“: Du wählst kein Set, die App vergleicht mit allen Kartenbildern. Dafür rechnet dein Gerät einen Fingerabdruck der Karte, und der Server sucht ihn unter allen Karten; die Kartenbilder bereitest du einmal vor. Unter so vielen Karten ist die App seltener sicher und fragt öfter nach.',
  vorliebe: 'Welches Bild eine Karte zeigt, sieht die Kamera. Welcher Druck es ist, oft nicht: Viele Bilder gibt es in mehreren Sets. Liegt genau ein Druck in einem bevorzugten Set, nimmt die App den, sonst den aus dem Set deiner letzten sicher erkannten Karten, sonst einen, den du schon hast oder auf der Scan-Liste gewählt hast, sonst den neuesten. Wo sie raten musste, steht auf der Scan-Liste „Druck prüfen“. Scannst du ein Display oder einen Precon, wähl hier dessen Sets, sonst lass es leer.',
  katfehlt: 'Der Katalog aller Karten ist noch nicht geladen. Er kommt von Scryfall (rund 75 MB, einmal je Installation) und wird geladen, sobald jemand „Erfassen“ öffnet; sofort geht es im Terminal mit „mtg katalog --neu“. Bis dahin erkennt die App mit „Nur gewählte Sets“.',
  katjob: 'Dein Gerät lädt die fehlenden Kartenbilder von Scryfall (die kleine Größe), rechnet daraus Fingerabdrücke und schickt sie an den Server. Das ist je Installation einmal nötig, nicht je Gerät: Jedes weitere Gerät und Konto nutzt das Ergebnis mit. Am Rechner dauert es rund eine Viertelstunde, die Seite muss so lange offen bleiben. Erkannt wird, was schon vorbereitet ist. Anhalten und später weitermachen geht.',
  namen: 'Die deutschen Namen, wie sie auf deutschen Karten gedruckt sind, braucht „Namen der Karte lesen“, um deutsche Karten am Namen zu erkennen. Scryfall liefert sie nur in den Gesamtdaten mit allen Sprachen (rund 378 MB), die der Server dann alle 30 Tage neu lädt. Ohne sie liest die App englische Namen, und deutsche Karten erkennt sie nur am Bild. Der Schalter gilt für die ganze Installation und wird vom Hauptkonto gestellt. Laden kann der Server sie nur dort, wo er Namen lesen kann (Tesseract, im Docker-Image dabei).',
  druckpruefen: 'Die Karte ist erkannt. Ihr Bild gibt es aber in mehreren Drucken, und die App hat einen davon genommen. Welcher es ist, steht unten links auf deiner Karte: Set-Kürzel und Nummer. Tipp den passenden Druck an und speichere. Stimmt er schon, speichere einfach.',
  scandeck: 'Ein fertiges Deck: Seine Karten zählen nie als verfügbar, kommen nie in die Verkaufsliste und stehen unter Decks, dort wählst du auch den Commander. Übernimmst du später weitere Karten unter diesem Namen, kommen sie dazu.',
  deckscan: 'Deck einscannen: Scann alle Karten des Decks nacheinander. Sie kommen auf die Scan-Liste. Dort prüfst du sie, gibst dem Deck unten einen Namen und übernimmst es. Am besten mit „Alle Karten, ohne Set“, ist es ein Precon, wähl dessen Set als bevorzugtes.',
  titel: 'Die App liest zuerst den Namen oben auf der Karte und wählt dann unter den Drucken dieses Namens das passende Bild. So erkennt sie mehr Karten von selbst und verwechselt ähnliche Bilder seltener. Dafür gehen je Karte zwei schmale Streifen mit der Namenszeile an deinen Server. Sie werden dort gelesen und nicht gespeichert, das übrige Kamerabild bleibt auf dem Gerät. Ist der Name nicht lesbar (Spiegelung auf Foil oder Hülle, sehr alte Karten, Name quer), vergleicht die App wie bisher nur das Bild.',
  schnell: 'Die App zählt eine Karte, sobald sie sich sicher genug ist: bei einem sehr klaren Bild nach einem Blick, sonst nach zwei oder drei. Ein unscharfes Bild zwischendurch wirft die Zählung nicht mehr um. Beim Erfassen merkt sie auch Kopien beim Durchblättern: Schnippst du die gezählte Karte weg und liegt darunter eine gleiche, fragt sie „Weitere Kopie gelegt?“; schnippst du weiter, sammelt die Frage mit („3 weitere Kopien?“), ein Tipp auf das Plus zählt sie alle. Ohne den Haken zählt sie wie bisher erst, wenn zwei Bilder nacheinander sicher sind, und weitere Kopien nur über +1.',
  frei: 'Die App sucht die Karte im ganzen Kamerabild: Sie muss nicht im Rahmen liegen, nur ganz zu sehen sein und ungefähr aufrecht stehen. Am besten geht es auf einem ruhigen Untergrund, von dem sich die Karte abhebt. Findet die App keine Karte, gilt der Rahmen in der Mitte. Fertige Karten legst du außerhalb des Bilds ab, sonst zählt die App sie noch einmal. Ohne den Haken zählt nur der Rahmen.',
  vollbild: 'Am Handy füllt die Kamera beim Erfassen den Bildschirm. Oben steht, was auf der Scan-Liste liegt; „Liste“ am Rand zeigt sie zum Prüfen und Übernehmen. Unten stellst du Foil, Sprache und Zustand für die nächsten Karten ein, „+1“ zählt die letzte Karte noch einmal, und ein Tipp auf sie ändert sie. Das Kreuz oben links beendet die Kamera.',
  setlock: 'Die App vergleicht nur mit den Drucken der gewählten Sets. Das macht die Erkennung schnell und genau, Karten aus anderen Sets erkennt sie dann aber nicht: Set dazunehmen. Für einen Commander-Precon das Commander-Set wählen (etwa DSC), für Booster das Set und seine Specials.',
  scanbinder: 'Einen Scan-Binder führt die App selbst. Kein ManaBox-Import ändert ihn, und er zählt wie jeder Binder im Bestand, im Sortier-Plan und beim Verkaufen. Was du mit der App erfasst, scannst du nicht zusätzlich in einer Scanner-App wie ManaBox, sonst zählt es doppelt.',
  vorgaben: 'Sprache, Zustand und Foil sieht die Kamera nicht: Diese Vorgaben gelten für jede erfasste Karte, einzelne änderst du auf der Scan-Liste mit einem Tipp. Gibt es einen Druck nur als Foil, wird er als Foil erfasst.',
  erfneu: 'Neue Sets bekommen bei Scryfall oft noch Drucke nachgereicht. Das holt die Liste der Drucke noch einmal.',
  doppelt: 'Was du mit der App erfasst, scannst du nicht zusätzlich in einer Scanner-App wie ManaBox: Sonst zählt es doppelt, einmal im Scan-Binder und einmal im ManaBox-Binder.',
  kopie: 'Bleiben Binder, Foil, Sprache und Zustand gleich, änderst du die Menge. Mit anderem Binder oder anderen Angaben ziehen so viele Kopien dorthin um.',
  uebernehmen: 'Übernimmt einen Binder aus ManaBox in die App: Ab dann ist er ein Scan-Binder, du änderst ihn hier (Menge, verschieben, als verkauft buchen), und ein ManaBox-Export lässt ihn aus. Vorher legt die App eine Sicherung an. In ManaBox änderst du diesen Binder danach nicht mehr.',
  buchen: 'Karten aus Scan-Bindern führt die App selbst: „Als verkauft buchen“ nimmt sie aus dem Bestand und zählt sie bei den Verkäufen, mit Trendpreis oder deinem echten Erlös. Karten aus ManaBox-Bindern löschst du in ManaBox, der nächste Import bucht sie.',
  csv: 'Alle Binder als CSV im Format des ManaBox-Sammlungsexports, mit Kaufpreis und Datum. ManaBox kann sie importieren, und in eine leere Sammlung dieser App hochgeladen ergibt sie wieder denselben Bestand. Für eine echte Sicherung mit Decks, Notizen und Spielen: die ZIP.',
  posteingang: 'Für alle, die weiter mit einer Scanner-App wie ManaBox scannen: Den CSV-Export am Handy per Teilen in einen Sync-Ordner legen (Syncthing oder Drive), der auf diesen Ordner zeigt. Einmal am Tag übernimmt die App jede neue Datei wie beim Hochladen, jede nur einmal. Würde eine Datei mehr als ein Viertel entfernen, bleibt sie liegen und steht als Warnung in den Neuigkeiten. „rückgängig“ auf der Übersicht nimmt den letzten Import zurück.',
  aussen: 'Die tägliche Sicherung liegt auf demselben Rechner bzw. Server wie deine Sammlung. Geht der kaputt, ist sie mit weg. Deshalb eine Kopie woanders: auf dem Server jede Nacht per deploy/sicherung-aussen.sh, etwa auf eine Storage Box (Anleitung in der README), oder die App kopiert selbst in einen zweiten Ordner (unten), sonst die ZIP herunterladen und auf einen USB-Stick oder in deine Cloud legen. Beides zählt hier. Die ZIP enthält Passwort-Hashes und Kaufpreise: Mit einer Schlüsseldatei verschlüsselt gpg die Kopie vor dem Kopieren, sonst gehört sie nur an einen Ort, dem du traust.',
  zweiterordner: 'Eine zweite Kopie der täglichen Sicherung in einem Ordner auf diesem Rechner oder Server, der selbst woanders hin gesichert wird: der Ordner einer Cloud (OneDrive, Dropbox, Nextcloud), ein NAS oder eine eingehängte Storage Box. Die App legt dort nach der täglichen Sicherung eine Datei mtg-JJJJ-MM-TT.zip ab (mit Schlüssel mtg-JJJJ-MM-TT.zip.gpg) und löscht nur solche Dateien, wenn sie älter als 60 Tage sind. Alles andere im Ordner fasst sie nicht an. Auf dem Server mit Docker muss der Ordner erst in compose.yaml eingebunden sein (README).',
  einrichtung: 'Diese Installation hat noch kein Hauptkonto. Den Einrichtungs-Code schreibt der Server beim Start in sein Protokoll, die Zeile beginnt mit „Einrichtung: Code“. Mit Docker zeigt ihn „docker compose logs mtg“, auf dem Server selbst auch „mtg einrichtung“. Der Code gilt, bis das Hauptkonto angelegt ist, danach nie wieder.',
  einrneu: 'Du legst das Hauptkonto an. Es sieht und verwaltet alle Sammlungen dieser Installation und legt später Unterkonten an. Mit Name und Passwort meldest du dich ab jetzt an. Ein vergessenes Passwort setzt nur die Kommandozeile neu: mtg konto passwort NAME.',
  einrzip: 'Für den Umzug auf einen neuen Server: die ZIP aus „Konten und Sicherung“ oder aus dem Ordner data/sicherungen. Die App prüft sie und setzt Konten, Sammlungen und hochgeladene Dateien ein. Danach meldest du dich mit Name und Passwort von damals an. Eine verschlüsselte Datei (.gpg) vorher mit gpg entschlüsseln.',
  einrbelegt: 'Im Datenordner dieser Installation liegen schon Dateien, deshalb gibt es hier nur „Neu anfangen“. Eine vorhandene Sammlung gehört danach dem Hauptkonto. Eine Sicherung spielst du in diesem Fall auf dem Server ein: mtg wiederherstellen DATEI.zip.',
  proxyblatt: 'Das Proxy-Blatt druckt Karten in Originalgröße, jede mit dem Aufdruck „Playtest“, zum Ausprobieren, bevor du kaufst. Es ist aus, bis das Hauptkonto es einschaltet, und der Schalter gilt für die ganze Installation. Die Fan Content Policy von Wizards nimmt Proxys aus: Der Hinweis im Fuß der Seite deckt sie nicht. Drucke sie nur zum Testen.',
  fertigedecks: 'Manche Exporte nennen nicht, ob ein Binder ein fertiges Deck ist. Trägst du hier den Namen eines Binders ein, gilt er als fertiges Deck: Seine Karten bleiben im Stapel Deck und zählen nicht als verfügbar. Exporte, die den Typ „deck“ nennen, und hochgeladene Decklisten brauchen keinen Eintrag. Die Liste gilt für diese Sammlung.',
  beispiel: 'Die Beispielsammlung zeigt in einer Minute, was die App kann: gut 170 Karten in einem Binder, ein Commander-Deck und die Pläne dazu (Behalten, Verkaufen, Bulk). Dafür fragt die App einmal bei Scryfall nach den Kartendaten (zwei Anfragen), die Bilder lädt dein Browser von dort. Kaufpreise und Daten im Beispiel sind erfunden. Oben entfernst du sie mit einem Klick, sie verschwindet auch von selbst, wenn du deine erste echte Datei importierst.',
  quellen: 'Jede Quelle außer Scryfall kannst du abschalten, für die ganze Installation: auch für Unterkonten und den täglichen Lauf. Abgeschaltet heißt: Die App ruft sie nicht mehr auf, die Ansichten sagen es, und alles andere läuft weiter. Nur das Hauptkonto stellt das ein.',
  hauptsieht: 'Das Hauptkonto dieser Installation kann deine Sammlung sehen und ändern, auch wenn du ein eigenes Passwort hast. Es verwaltet die Installation und hat ohnehin Zugriff auf ihre Dateien.',
  hauptsiehtanlegen: 'Sag es dem, für den du das Konto anlegst: Du als Hauptkonto kannst seine Sammlung sehen und ändern, auch wenn er ein eigenes Passwort hat. Auf seiner Seite „Dein Konto“ steht das auch.',
  coverage: 'Wie viel von dem, was EDHREC für diesen Commander empfiehlt, du schon frei hast. Oft gespielte Karten zählen mehr. 41 % heißt: Knapp die Hälfte eines typischen Decks liegt schon bei dir.',
  have: 'Empfohlene Karten, die du frei hast, von allen, die EDHREC für diesen Commander empfiehlt. 79 / 251 heißt: 79 von 251.',
  decks: 'So viele Decks mit diesem Commander kennt EDHREC. Viele Decks: beliebter Commander und verlässlichere Empfehlungen. Wenige: eher Nische.',
  cmdprice: 'Was die Commander-Karte selbst wert ist (deine günstigste Kopie).',
  build: 'Stellt ein Deck mit 100 Karten aus deinen freien Karten zusammen. Reserviert wird erst, wenn du es speicherst.',
  free: 'Frei heißt: in keinem fertigen und keinem gespeicherten Deck. Nur daraus wird gebaut, bestehende Decks bleiben unangetastet.',
  bracket: 'Machtstufe von 1 (ganz locker) bis 5 (Turnier). Bracket 1 und 2: keine Game Changer, 3: höchstens drei, ab 4 beliebig viele.',
  theme: 'EDHREC kennt zu jedem Commander Themen wie Landfall, Marken oder Friedhof und die Karten aus Decks genau dieses Themas. Das Deck baut sich aus diesen Karten. Automatisch nimmt die App von den gängigen Themen das, dessen Karten du am vollständigsten hast.',
  themeweight: 'Wie stark die EDHREC-Liste des Themas zählt, der Rest kommt aus der allgemeinen Liste des Commanders. Das hängt an der Zahl der Decks: bei 39 Decks 28 %, bei 1.600 Decks 94 %. So ändern dünne Daten wenig.',
  modes: 'Wie das Ranking sortiert ist. Machbar: was du am vollständigsten frei hast. Beliebt: die meistgespielten Commander. Geheimtipp: gut machbar, aber wenig gespielt. Günstig: der kleinste Zukauf. Mit „EDHREC-Decks mindestens“ blendest du Commander mit dünnen Daten aus.',
  buy: 'Was die zehn wichtigsten Karten kosten, die dir für diesen Commander noch fehlen (Cardmarket-Trend). Karten ohne Preis zählen nicht mit.',
  curve: 'Wie viele Karten ohne Länder es je Manawert gibt. Viele Karten mit 5 und mehr machen ein Deck träge, viele mit 1 und 2 schnell.',
  sources: 'Länder im Deck, die diese Farbe erzeugen, gegen die Farbsymbole in den Kosten der Zauber. Wenig Länder bei vielen Symbolen heißt: Die Farbe klemmt oft.',
  want: 'Diese Karte steht auf den EDHREC-Listen von mindestens zwei deiner zehn besten Commander. Eine Kopie reicht für ein Deck, für zwei gleichzeitig brauchst du zwei.',
  bracketcheck: 'Commander Spellbook prüft die Liste auf Game Changer, Combos, Extrazüge und Massen-Landzerstörung. Die App rechnet daraus das niedrigste Bracket, das noch passt.',
  spellbook: 'Spellbooks eigene Einstufung (Exhibition, Core, Powerful, Oddball, Spicy, Ruthless). Das ist nicht die Bracket-Zahl, sondern ein zweiter Blick darauf.',
  themefit: 'Von den weiteren Karten (ohne Ramp, Kartenziehen, Removal und Wipes) prüft die App am Kartentext, ob sie zum Thema passen, zum Beispiel Landfall-Karten und Karten, die Länder ins Spiel bringen. Ein Textvergleich, keine Garantie. Passende Karten stehen oben in der Gruppe „Thema“.',
  gc: 'Game Changer sind Karten, die Wizards als besonders spielentscheidend einstuft, etwa Rhystic Study. Sie bestimmen das Bracket mit.',
  cmc: 'Durchschnittliche Manakosten der Karten ohne Länder. Unter 3 spielt sich flott, über 3,5 eher träge.',
  staple: 'Staples laufen in sehr vielen Decks (EDHREC-Rang bis 200) oder stehen auf der Liste eines deiner zehn besten Commander.',
  bulk: 'Bulk sind günstige Karten, die man in Mengen verkauft, zum Beispiel pro 1.000 Stück, statt jede einzeln anzubieten.',
  value: 'Summe aller Karten zum Cardmarket-Trendpreis laut Scryfall. Foils mit Foil-Preis, der Zustand fließt nicht ein.',
  sellable: 'Alles, was nicht in einem Deck steckt und über die Behalten-Regel hinausgeht: einzeln (ab Mindestpreis) und als Bulk.',
  unique: 'Verschiedene Karten, egal in welcher Edition, Sprache oder Foil.',
  available: 'Karten in deinen Bindern, die in keinem fertigen Deck stecken.',
  deck: 'Steckt in einem fertigen oder in der App gespeicherten Deck und bleibt dort.',
  keep: 'Was du laut Regel behältst (Standard: eine Kopie je Karte, zwei je Staple, Standardländer alle). Das ist deine Reserve für neue Decks. Ändern unter Verkaufen.',
  sell: 'Weitere Kopien ab dem Mindestpreis: lohnt sich einzeln.',
  bulkstack: 'Weitere Kopien unter dem Mindestpreis: gehen als Masse weg.',
  sold: 'Lädst du einen neuen Export hoch und Karten von der Verkaufsliste fehlen, bucht die App sie als verkauft.',
  hand: 'Wie sich das Deck auf die Hand verteilt, exakt gerechnet aus der Zahl der Länder und Ramp-Karten (keine Simulation). Gerechnet wird mit 7 Karten auf der Hand und einer weiteren je Zug ab Zug 2.',
  spielbar: 'Wie oft die ersten 7 Karten 2 bis 5 Länder enthalten. Mit weniger fehlt Mana, mit mehr fehlen Zauber.',
  land3: 'Wie oft du bis Zug 3 drei Länder gesehen hast (7 Karten plus 2 gezogen), also in jedem Zug ein Land spielen kannst.',
  ramp2: 'Wie oft bis Zug 2 mindestens eine Ramp-Karte dabei ist (7 Karten plus 1 gezogen).',
  quelle: 'Wie oft du bis Zug 3 mindestens ein Land dieser Farbe gesehen hast. Hat eine Karte zwei Symbole derselben Farbe (etwa zweimal Schwarz), zählt außerdem, ob bis Zug 4 zwei solche Länder da sind. Unter 90 % klemmt die Farbe öfter (Faustregel).',
  improve: 'Karten von der EDHREC-Liste deines Commanders, die beliebter sind als die schwächste Karte derselben Rolle in deinem Deck (Ramp gegen Ramp, Länder gegen Länder). Erst was du frei hast, dann was wenig kostet. Das Deck selbst änderst du von Hand.',
  bedarf: 'Karten von den EDHREC-Listen der Commander deiner Decks (gebaute und fertige), die dem jeweiligen Deck fehlen und die du nicht frei hast. Oben die, die mehreren Decks helfen: Eine Kopie davon bringt gleich mehrere Decks weiter.',
  wunsch: 'Fällt der günstigste Preis (Cardmarket „ab“ oder der Trend) auf deinen Zielpreis oder darunter, steht die Karte hier oben und auf der Übersicht.',
  provision: 'Cardmarket behält bei Privatverkäufern 5 % des Kartenpreises, das Porto zahlt der Käufer (Stand Oktober 2026, aus zwei unabhängigen Quellen; die offizielle Gebührentabelle war für die App nicht abrufbar).',
  k7bulk: 'Ein Beispiel nach der Bulk-Preisliste von KEEPSEVEN (sammelkartenankauf.de, Stand 8.10.2026), je Karte: Mythic 0,12 €, Rare 0,10 €, Uncommon 0,005 €, Common 0,003 €, Standardland 0,002 €, Foils etwas mehr. Tokens und andere Sprachen als Englisch und Deutsch kauft KEEPSEVEN nicht.',
  sprachen: 'Manche Ankäufer, zum Beispiel KEEPSEVEN, kaufen nur englische und deutsche Karten. Mit diesem Haken zeigen Liste und Exporte nur diese.',
  reserved: 'Karten auf der Reserved List druckt Wizards nicht nach. Ihr Preis fällt deshalb nicht durch Neuauflagen.',
  meldegrenze: 'Plattformen wie Cardmarket melden Verkäufer dem Bundeszentralamt für Steuern, wenn sie im Jahr 30 oder mehr Verkäufe oder 2.000 € oder mehr Umsatz haben (Plattformen-Steuertransparenzgesetz). Gezählt werden dort Verkäufe auf der Plattform, hier die Karten, die die App als verkauft erkannt hat. Keine Steuerberatung.',
  combos: 'Commander Spellbook kennt über 7.000 Karten, die in Combos vorkommen. Die App prüft, welche Combos du komplett besitzt und bei welchen genau eine Karte fehlt. Spellbook nimmt höchstens 600 Karten je Anfrage, deshalb fragt die App je drei Farben einzeln: Combos mit vier oder fünf Farben fehlen. 2-Karten-Combos heben das Bracket (ab 4).',
  frage: 'Dein lokales Sprachmodell (Ollama) übersetzt die Frage in eine Suche, die App prüft und zeigt sie und sucht dann selbst. Das Modell erfindet keine Karten: Es schreibt nur die Suche.',
  aehnlich: 'Karten deiner Sammlung, deren Text und Typ dieser Karte am ähnlichsten sind, berechnet von deinem lokalen Ollama (nomic-embed-text). Gut, um Ersatz für eine fehlende Karte zu finden.',
  dossier: 'Recherche zu diesem Commander: Strategie, Themen, typische Fehler, Regelfallen, Upgrade-Pfad, jeweils mit Quellen und Abrufdatum. Claude Code legt es mit dem Skill mtg-recherche an, die App zeigt es nur.',
  salt: 'Wie sehr eine Karte den Tisch ärgert, aus der Umfrage von EDHREC (0 bis 4). Gezählt werden die 100 salzigsten Karten, die Zahl ist ihre Summe im Deck.',
  bracketfertig: 'Bei gebauten Decks das gewählte Bracket. Bei fertigen Decks geschätzt aus den Game Changern (keine: 2, bis drei: 3, mehr: 4), du kannst es ändern.',
  tisch: 'Hak an, wer heute mitspielt. Die App nimmt das mittlere Bracket der Gegner und schlägt deine Decks vor, die höchstens eine Stufe davon entfernt sind: zuerst gleiches Bracket, dann andere Farben als der Tisch, dann das am längsten nicht gespielte.',
  setstand: 'Wie viele verschiedene Drucke des Sets du hast. Gezählt wie bei Scryfall, also mit Showcase- und Rahmen-Varianten. Die Set-Größe holt der tägliche Lauf.',
  rulings: 'Offizielle Erläuterungen zu dieser Karte von Wizards und Scryfall. Die App zeigt sie nur an, sie schreibt keine Regeln selbst.',
  reprint: 'Diese Karte erscheint in einem neuen oder angekündigten Set. Neuauflagen drücken oft den Preis: Verkaufen lohnt eher vorher.',
  gewinn: 'Was die Karten, für die der Import einen Kaufpreis kennt (zum Beispiel aus ManaBox), heute wert sind, minus was du für sie bezahlt hast. Karten ohne Kaufpreis (zum Beispiel Tokens oder hochgeladene Decklisten) zählen nicht mit.',
  verlauf: 'Der Wert deiner Sammlung an jedem Tag, an dem die App lief (Preise oder Import). Er ändert sich durch neue oder verkaufte Karten und durch Preise. Punkte markieren die Tage mit Wert, solange es wenige sind. Gestrichelt heißt: Dazwischen lief die App nicht, die Linie verbindet nur.',
  cardmarket: 'Aus der täglichen Preisliste von Cardmarket: der niedrigste Angebotspreis (ab), der Trend und der Schnitt der letzten 30 Tage, ohne Sprache und Zustand. Fürs Verkaufen ist „ab“ die Untergrenze.',
};
const info = (k, label) => `<button type="button" class="info" data-tip="${esc(TIP[k] || k)}" aria-label="${esc((label ? label + ': ' : '') + (TIP[k] || k))}">${icon('help')}</button>`;
// Manasymbol wie auf der Karte; deco = nur Schmuck (der Knopf drumherum trägt die Beschriftung)
const pip = (k, deco) => {
  const t = COLORS[k] || k, aria = deco ? ' aria-hidden="true"' : ` role="img" aria-label="${esc(t)}" title="${esc(t)}"`;
  return MANA[k] ? `<span class="pip ${k.toLowerCase()}"${aria}>${svg(MANA[k])}</span>` : `<span class="pip c"${deco ? ' aria-hidden="true"' : ''}>${esc(k)}</span>`;
};
const pips = ci => `<span class="pips">${(ci ? [...ci] : ['C']).map(k => pip(k)).join('')}</span>`;
const mana = s => `<span class="cost">${esc(s || '').replace(/\{([^}]+)\}/g, (_, t) => /^[WUBRGC]$/.test(t) ? pip(t) : `<span class="pip c" title="${t}">${t}</span>`)}</span>`;
const pic = (u, alt, cls = '') => u ? `<img loading="lazy" alt="${esc(alt)}" src="${esc(u)}"${cls ? ` class="${cls}"` : ''}>` : `<span class="noimg ${cls}">${esc(alt)}</span>`;
// Art-Crops zeigen nicht die ganze Karte: Scryfall bittet, den Künstler zu nennen
const credit = c => c && c.artist ? `<span class="credit">Illustration: ${esc(c.artist)}</span>` : '';
const artImg = (c, extra = '') => c && c.image ? `<img class="art" loading="lazy" alt="" src="${esc(art(c.image))}"${c.artist ? ` title="Illustration: ${esc(c.artist)}"` : ''}${extra}>` : '';
// Hover-Vorschau: Element mit data-img zeigt das große Kartenbild neben dem Mauszeiger
const peekAt = (img, name, sub) => img ? ` data-img="${esc(img)}" data-cap="${esc(name)}" data-sub="${esc(sub || '')}"` : '';
let toastTimer;
const toast = (t, ms) => { clearTimeout(toastTimer); $('#toast').textContent = t; if (ms) toastTimer = setTimeout(() => toast(''), ms); };
const flash = t => toast(t, 4500);
const head = (title, sub, actions = '') => `<div class="head"><div class="min0"><h1>${title}</h1>${sub ? `<p>${sub}</p>` : ''}</div>${actions ? `<div class="actions">${actions}</div>` : ''}</div>`;

// --- Bausteine ---------------------------------------------------------------------------------------------------
const chip = (stack, text) => `<span class="chip s-${stack}">${esc(text)}</span>`;
const stackChips = (st, long) => !st ? '' : [
  ...[...new Set(st.deck)].map(d => chip('deck', long ? 'Deck: ' + d : d)),
  ...['keep', 'sell', 'bulk'].filter(k => st[k]).map(k => chip(k, st[k] > 1 || st.deck.length ? `${st[k]} ${LABEL[k].toLowerCase()}` : LABEL[k])),
].join('');
// Kachel: Bild frei, Preis und Anzahl darunter (nichts liegt auf dem Kartenbild); withNo: Serie und Sammlernummer (Serien-Sicht, zum Abgleich mit der echten Karte)
const tile = (c, withQty, withNo) => `<a class="card" href="#" data-oid="${esc(c.oracle_id)}"${peekAt(c.image, c.name, `${eur(c.price)}${c.type ? ' · ' + c.type : ''}`)}>
  ${pic(c.image, c.name)}<span class="cap"><span class="p">${eur(c.price)}</span>${withQty && c.qty > 1 ? `<span class="q">×${c.qty}</span>` : ''}</span>
  ${withNo ? `<span class="no">${esc(c.set)} #${esc(c.number)}</span>` : ''}<span class="chips">${stackChips(c.stacks, true)}</span></a>`;
const row = c => `<a class="row" href="#" data-oid="${esc(c.oracle_id)}"${peekAt(c.image, c.name, eur(c.price))}>${pic(small(c.image), '', 'thumb')}
  <div class="min0"><div class="name">${esc(c.name)}</div><div class="sub2">${c.qty}×${c.foil ? ' · Foil' : ''}</div></div>
  <div class="chips">${stackChips(c.stacks)}</div><div class="price">${eur(c.price)}</div></a>`;
// anteil: über jeder Spalte ein Balken mit dem Anteil am Gesamtwert (gleiche Skala in allen vier), so steht jeder Text unter seinem eigenen Balken
const legend = (counts, sub = {}, anteil = false) => {
  const gesamt = STACKS.reduce((n, k) => n + (counts[k].value || 0), 0);
  return `<div class="legend">${STACKS.map(k => {
    const c = counts[k], n = c.cards ?? c, v = c.value;
    return `<div>${anteil ? `<span class="anteil" aria-hidden="true"><span class="d-${k}" style="--w:${v > 0 ? Math.max(v / gesamt * 100, 1.2).toFixed(1) : 0}%"></span></span>` : ''}<b><span class="dot d-${k}"></span>${LABEL[k]} ${info(k === 'bulk' ? 'bulkstack' : k, LABEL[k])}</b>
    <span class="v">${v != null ? eur0(v) : num(n)}</span><span class="muted">${v != null ? karten(n) : n === 1 ? 'Karte' : 'Karten'}${sub[k] ? ` ${esc(sub[k])}` : ''}</span></div>`;
  }).join('')}</div>`;
};
const skeleton = () => `<div class="skel" aria-busy="true" aria-label="Lädt"><div class="s-head"></div><div class="s-hero"></div><div class="s-rows"></div></div>`;
const note = ([ic, t, sub, act, job]) => `<div class="note"><span class="ic">${icon(ic)}</span>
  <div class="min0"><b>${esc(t)}</b><div class="muted">${esc(sub)}</div>${job ? `<div data-jobbox="${job}"></div>` : ''}</div>${act || '<span></span>'}</div>`;

// Quellen (Phase 44, PLAN E25): abgeschaltet = der Betreiber hat die Quelle auf der Seite „Quellen“ ausgestellt (sess.quellen kommt von /api/session).
// Dann gibt es keine Fehlermeldung, sondern an jeder Stelle, die sie braucht, einen Hinweis mit Link dorthin.
const QNAME = {edhrec: 'EDHREC', spellbook: 'Commander Spellbook', cardmarket: 'Cardmarket-Preisliste'};
const aus = k => sess.quellen?.[k] === false;
const proxyAn = () => !!sess.proxy;  // das Proxy-Blatt ist aus, bis das Hauptkonto es einschaltet (E23)
const ausLink = `<a class="btn" href="#/quellen">Quellen</a>`;
const ausNote = (k, was) => note(['info', `${QNAME[k]} ist abgeschaltet`, was, ausLink]);
const ausZeile = (k, was) => `<p class="note-line">${esc(QNAME[k])} ist abgeschaltet. ${esc(was)} <a href="#/quellen">Zur Seite Quellen</a></p>`;
const ladeFehler = e => e.quelle ? ausZeile(e.quelle, 'Deshalb gibt es hier nichts Neues.') : `<p class="muted">Nicht geladen: ${esc(e.message)}</p>`;

// --- Übersicht ---------------------------------------------------------------------------------------------------
const FORMATS = 'CSV aus ManaBox, Moxfield, Deckbox, Dragon Shield, TCGplayer, Archidekt oder Cardmarket, außerdem Decklisten als Text (.txt).';
function welcome(s = {}) {
  main.innerHTML = `<section class="welcome" aria-labelledby="w-title">
    <div><h1 id="w-title">${fremd() ? `Die Sammlung ${esc(fremd().anzeige)} ist noch leer.` : 'Deine Sammlung, sortiert.'}</h1>
      <p>Exportiere deine Karten aus einer Scanner-App (zum Beispiel ManaBox) und leg die Datei hier ab, oder erfasse sie unter <a href="#/scan?modus=erfassen">Scannen</a> direkt mit der Kamera. Den Rest rechnet die App aus.</p>
      <ol class="steps">
        <li><div><b>Exportieren</b><span>In deiner Scanner-App (zum Beispiel ManaBox) den Binder oder die ganze Sammlung als CSV exportieren. Decks kommen als Textliste. Ohne Scanner-App geht es per Kamera.</span></div></li>
        <li><div><b>Ablegen</b><span>Datei hierher ziehen oder auswählen. Das Format erkennt die App selbst und zeigt vorher, was sich ändert.</span></div></li>
        <li><div><b>Loslegen</b><span>Sortier-Plan, Verkaufsliste und Commander-Vorschläge sind sofort da.</span></div></li>
      </ol>
      ${s.beispiel?.angebot ? `<div class="beispiel-angebot"><button class="btn" type="button" data-beispiel="laden">${icon('cards')}Beispielsammlung ansehen</button>${info('beispiel', 'Beispielsammlung')}<span class="muted">Zum Ausprobieren, ohne eigene Datei.</span></div>` : ''}</div>
    <div class="dropzone" data-dropzone>${icon('upload', 'lg')}<b>Datei hier ablegen</b><span class="muted">${FORMATS}</span>
      <div class="seg"><button class="btn primary" type="button" data-pick>${icon('upload')}Datei auswählen</button><button class="btn" type="button" data-paste>${icon('paste')}Liste einfügen</button></div></div>
  </section>
  <p class="muted welcome-foot">Alles bleibt bei dir: auf deinem Rechner oder deinem eigenen Server, keine fremde Cloud. Mehr in der <a href="#/help">Hilfe</a>.</p>`;
}

async function viewHome() {
  const s = await api('summary');
  if (!s.cards) return welcome(s);
  const li = s.last_import, P = s.plan, R = s.rules, minTxt = eurMin(R.sell_min), andere = fremd();
  undoInfo = s.undo;
  const vk = {cards: P.sell.cards + P.bulk.cards, value: P.sell.value + P.bulk.value};
  const todo = [];
  if (!s.setup.edhrec && aus('edhrec')) todo.push(['info', 'EDHREC ist abgeschaltet', 'Commander-Ranking und Deckbau brauchen die Daten von EDHREC. Auf der Seite „Quellen“ siehst du, was EDHREC erfährt, und kannst es einschalten.', ausLink]);
  else if (!s.setup.edhrec) todo.push(['cloud', 'Commander-Daten laden', 'Einmal nötig für Ranking und Deckbau. Dauert ein paar Minuten (eine EDHREC-Seite pro Sekunde), du kannst weiterarbeiten.', `<button class="btn" type="button" data-job="commanders">${icon('cloud')}Jetzt laden</button>`, 'commanders']);
  if (vk.cards) todo.push(['euro', `${karten(vk.cards)} kannst du verkaufen`, `Zusammen ${eur0(vk.value)}: ${num(P.sell.cards)} einzeln ab ${minTxt}, ${num(P.bulk.cards)} als Bulk. Von jeder Karte bleibt mindestens eine bei dir.`, `<a class="btn" href="#/sell">Verkaufsliste</a>`]);
  if (s.wuensche.length) todo.push(['check', `Zielpreis erreicht: ${s.wuensche.slice(0, 3).join(', ')}${s.wuensche.length > 3 ? ` und ${s.wuensche.length - 3} weitere` : ''}`, 'Auf deiner Wunschliste ist der günstigste Preis jetzt bei deinem Ziel oder darunter.', `<a class="btn" href="#/wuensche">Wünsche</a>`]);
  const arena = s.arena.reduce((n, a) => n + a.qty, 0);
  if (arena) todo.push(['alert', `${karten(arena)} als Arena-Druck eingetragen: ${s.arena.slice(0, 3).map(a => `${a.name} (${a.set_code})`).join(', ')}${s.arena.length > 3 ? ` und ${s.arena.length - 3} weitere` : ''}`, TIP.arena, `<a class="btn" href="#/cards?q=${encodeURIComponent('is:arena')}">Anzeigen</a>`]);
  const aussen = aussenStand(s.sicherung);
  if (sess.rolle === 'haupt' && s.sicherung.scan_karten && aussen.alt) todo.push(['alert', aussen.titel, `${karten(s.sicherung.scan_karten)} aus Scan-Bindern gibt es nur in dieser App, und die tägliche Sicherung liegt auf demselben Rechner. Leg eine Kopie woanders ab.`, `<a class="btn" href="#/konten">Zur Sicherung</a>`]);
  if (s.verliehen.length) todo.push(['info', `Verliehen: ${s.verliehen.slice(0, 3).map(v => `${v.name} an ${v.verliehen}`).join(', ')}${s.verliehen.length > 3 ? ` und ${s.verliehen.length - 3} weitere` : ''}`, 'Steht bei der Kopie im Kartendetail. Zurück? Dort den Namen löschen.', `<a class="btn" href="#/cards?q=${encodeURIComponent('is:verliehen')}">Anzeigen</a>`]);
  if (!s.decks && s.setup.edhrec) todo.push(['layers', 'Erstes Deck bauen', 'Das Commander-Ranking zeigt, welche Decks du schon fast zusammen hast.', `<a class="btn" href="#/decks">Zu den Decks</a>`]);
  // Fächer: die drei wertvollsten Karten, die teuerste liegt vorn in der Mitte
  const top = s.top.filter(c => c.image).slice(0, 3), fan = top.length === 3 ? [top[1], top[0], top[2]] : top;
  const max = Math.max(...s.colors.map(c => c.value), 1);
  main.innerHTML = `
    <section class="hero${fan.length ? '' : ' solo'}" aria-label="Deine Sammlung">
      <div class="min0"><h1 class="sr-only">Übersicht</h1>
        <p class="kicker">${andere ? `Sammlung ${esc(andere.anzeige)}` : 'Deine Sammlung'} ${info('value', 'Sammlungswert')}</p>
        <p class="display">${eur0(s.value)}</p>
        <p class="delta">${li ? `<span>${icon(li.value < 0 ? 'down' : 'up')}${signc(li.value)} seit dem letzten Import</span>` : ''}
          <span>Preise von ${day(s.prices_at)} <button class="link" type="button" data-job="prices">${icon('refresh', 'sm')}aktualisieren</button></span></p><div data-jobbox="prices"></div>
        <dl class="hstats"><div><dt>Karten</dt><dd>${num(s.cards)}</dd></div><div><dt>Verschiedene ${info('unique', 'Verschiedene')}</dt><dd>${num(s.unique)}</dd></div>
          <div><dt>Frei verfügbar ${info('available', 'Frei verfügbar')}</dt><dd>${num(s.available)}</dd></div>
          ${s.paid.cards ? `<div><dt>Seit dem Kauf ${info('gewinn', 'Seit dem Kauf')}</dt><dd title="${karten(s.paid.cards)} mit Kaufpreis: bezahlt ${eur(s.paid.paid)}, heute ${eur(s.paid.value)}">${signc0(s.paid.value - s.paid.paid)}</dd></div>` : ''}</dl></div>
      ${fan.length ? `<div class="fanwrap"><div class="fan n${fan.length}">${fan.map((c, i) => `<a href="#" data-oid="${esc(c.oracle_id)}" aria-label="${esc(c.name)}, ${eur(c.price)}"><img alt="" src="${esc(c.image)}"${i === 1 || fan.length < 3 ? ' fetchpriority="high"' : ''}></a>`).join('')}</div>
        <p class="fan-cap">Deine wertvollsten Karten</p></div>` : ''}
    </section>
    ${todo.length ? `<section class="sec" aria-label="Als Nächstes"><h2>Als Nächstes</h2><div class="todo">${todo.map(note).join('')}</div></section>` : ''}
    <section class="sec" aria-label="Plan für deine Sammlung"><h2>Plan für deine Sammlung <small>nach Wert</small><a class="more" href="#/sort">Sortieren ${icon('arrow')}</a></h2>
      ${legend(P, {deck: s.decks ? `in ${s.decks} Deck${s.decks > 1 ? 's' : ''}` : ''}, true)}
    </section>
    ${verlaufHtml(s.history)}
    <p class="note-line"><a href="#/rueckblick">Rückblick auf dein Sammeljahr</a> · <a href="#/bericht">Wert-Bericht zum Drucken</a></p>
    <div class="split">
      <section class="sec" aria-label="Wertvollste Karten"><h2>Wertvollste Karten <a class="more" href="#/cards?sort=price">alle ${icon('arrow')}</a></h2><div class="rows">${s.top.map(row).join('')}</div></section>
      <section class="sec" aria-label="Wert nach Farbe"><h2>Wert nach Farbe</h2><div class="bars">
        ${s.colors.map(c => `<span class="lbl">${pip(c.key)}${esc(c.label)}</span><span class="track"><span style="--w:${(c.value / max * 100).toFixed(1)}%" title="${esc(c.key === 'C' ? 'Farblos und Länder' : c.label)}: ${eur0(c.value)}, ${karten(c.cards)}"></span></span><span class="val">${eur0(c.value)}</span>`).join('')}
      </div></section>
    </div>
    ${s.movers.ready && (s.movers.up.length || s.movers.down.length) ? `<section class="sec" aria-label="Preisbewegung"><h2>Preisbewegung <small>${moversSub(s.movers)}</small><a class="more" href="#/sell">Verkaufen ${icon('arrow')}</a></h2>${moversHtml(s.movers)}</section>` : ''}
    <section class="sec" aria-label="Zuletzt hinzugefügt"><h2>Zuletzt hinzugefügt${li ? ` <small>letzter Import: +${num(li.added)} / −${num(li.removed)} Karten${li.scope === '*' ? '' : `, ${esc(li.scope)}`}</small>` : ''}${s.undo ? `<button class="link small-print" type="button" id="undo" title="Import „${esc(s.undo.file)}“ zurücknehmen">${icon('refresh', 'sm')}rückgängig</button>` : ''}<a class="more" href="#/cards?sort=added">alle ${icon('arrow')}</a></h2>
      <div class="rail">${s.recent.map(c => tile(c)).join('')}</div></section>
    <div class="${s.news.length ? 'split' : 'solo'}"><section class="sec" aria-label="Decks"><h2>Decks <a class="more" href="#/decks">${s.decks ? 'alle Decks' : 'Deck bauen'} ${icon('arrow')}</a></h2>
      ${s.deck_tiles.length ? `<div class="decks list">${s.deck_tiles.map(deckTile).join('')}</div>` : '<p class="muted">Noch kein Deck. Fertige Decks lädst du als Textliste hoch, neue baust du unter Decks.</p>'}</section>
    ${s.news.length ? `<section class="sec" aria-label="Neuigkeiten"><h2>Neuigkeiten <small>seit dem letzten Import</small></h2>
      <ul class="news">${s.news.map(n => `<li><span class="ic${NEWS_WARN.has(n.kind) ? ' warn' : ''}">${icon(NEWS_ICON[n.kind] || 'info')}</span><div${n.oracle_id ? ` data-oid="${esc(n.oracle_id)}"` : ''}>${esc(n.text)}<div class="s">${esc(n.sub)}</div></div></li>`).join('')}</ul></section>` : ''}</div>`;
  jobsUi(); verlaufHover();
  if (neueAnsicht) {
    zaehlen($('.display'), s.value, eur0);
    [s.cards, s.unique, s.available].forEach((n, i) => zaehlen($$('.hstats dd')[i], n, x => num(Math.round(x))));
    STACKS.forEach((k, i) => zaehlen($$('.legend .v')[i], P[k].value, eur0));
  }
}

// Wertverlauf: eine Linie (Wert je Tag), Fläche als Hauch, Wert am Ende, Fadenkreuz mit Tooltip, Tabelle zum Aufklappen (dataviz-Regeln)
const VB_W = 1000, VB_H = 220;
const VERLAUF_PUNKTE = 31;  // ponytail: bis zu so vielen Tagen bekommt jeder Tag mit Wert einen Punkt; darüber lägen sie am Handy aneinander (dann nach Breite statt Zahl entscheiden)
let verlaufDaten = [], verlaufPts = [];
function verlaufHtml(h) {
  const head2 = `<h2>Wert im Verlauf ${info('verlauf', 'Wert im Verlauf')}`;
  if (!h || h.length < 2) return `<section class="sec" aria-label="Wert im Verlauf">${head2}</h2><p class="muted">Der Verlauf beginnt ${h?.length && day(h[0].day) !== 'heute' ? `am ${day(h[0].day)}` : 'heute'}. Ab dem nächsten Tag steht hier, wie sich der Wert deiner Sammlung entwickelt.</p></section>`;
  const t = h.map(p => Date.parse(p.day + 'T12:00:00')), v = h.map(p => p.value);
  let lo = Math.min(...v), hi = Math.max(...v);
  const pad = Math.max((hi - lo) * 0.12, hi * 0.01, 1);
  lo = Math.max(0, lo - pad); hi += pad;
  const x = i => t.at(-1) === t[0] ? 0 : (t[i] - t[0]) / (t.at(-1) - t[0]) * VB_W, y = val => VB_H - (val - lo) / (hi - lo) * VB_H;
  const P = v.map((val, i) => [+x(i).toFixed(1), +y(val).toFixed(1)]), pts = P.map(p => p.join(',')).join(' ');
  const luecke = i => t[i] - t[i - 1] > 1.5 * 864e5;  // zwischen zwei Werten liegt mehr als ein Tag: Die App lief dort nicht, die Strecke ist nur verbunden
  const strecke = l => P.slice(1).reduce((d, p, i) => luecke(i + 1) !== l ? d : d + (i && luecke(i) === l ? '' : `M${P[i]}`) + `L${p}`, '');
  const ticks = [hi, (hi + lo) / 2, lo];
  verlaufDaten = h; verlaufPts = P;
  return `<section class="sec" aria-label="Wert im Verlauf">${head2}<small>${signc0(v.at(-1) - v[0])} seit ${day(h[0].day)}</small></h2>
    <div class="vchart"><div class="vy" aria-hidden="true">${ticks.map(tk => `<span>${eur0(tk)}</span>`).join('')}</div>
      <div class="vplot" id="vplot" tabindex="0" role="img" aria-label="Wert der Sammlung vom ${day(h[0].day)} (${eur0(v[0])}) bis ${day(h.at(-1).day)} (${eur0(v.at(-1))}), ${h.length} Tage. Pfeiltasten zeigen einzelne Tage.">
        <svg viewBox="0 0 ${VB_W} ${VB_H}" preserveAspectRatio="none" aria-hidden="true">${ticks.map(tk => `<line class="grid" x1="0" x2="${VB_W}" y1="${y(tk).toFixed(1)}" y2="${y(tk).toFixed(1)}"/>`).join('')}
          <polygon class="area" points="0,${VB_H} ${pts} ${VB_W},${VB_H}"/><path class="line" d="${strecke(false)}"/><path class="line luecke" d="${strecke(true)}"/>${h.length <= VERLAUF_PUNKTE ? `<path class="pkt" d="${P.map(p => `M${p}h.01`).join('')}"/>` : ''}<line class="cross" id="vcross" x1="0" x2="0" y1="0" y2="${VB_H}"/></svg>
        <span class="vdot" id="vdot"></span><span class="vend" style="top:${(y(v.at(-1)) / VB_H * 100).toFixed(1)}%">${eur0(v.at(-1))}</span><div class="vtip" id="vtip" role="status"></div></div>
      <div class="vx" aria-hidden="true"><span>${day(h[0].day)}</span><span>${day(h.at(-1).day)}</span></div></div>
    <details class="vtable"><summary>Als Tabelle</summary><table class="tbl">${h.slice().reverse().map(p => `<tr><td>${day(p.day)}</td><td class="rt">${eur(p.value)}</td><td class="rt muted">${karten(p.cards)}</td></tr>`).join('')}</table></details></section>`;
}
function verlaufHover() {
  const plot = $('#vplot');
  if (!plot) return;
  const h = verlaufDaten, t = h.map(p => Date.parse(p.day + 'T12:00:00')), tip = $('#vtip'), cross = $('#vcross'), dot = $('#vdot');
  const pts = verlaufPts;
  let idx = h.length - 1;
  const show = i => {
    idx = Math.max(0, Math.min(h.length - 1, i));
    const [px, py] = pts[idx], w = plot.getBoundingClientRect().width;
    cross.setAttribute('x1', px); cross.setAttribute('x2', px); cross.style.opacity = 1;
    dot.style.left = px / VB_W * 100 + '%'; dot.style.top = py / VB_H * 100 + '%'; dot.style.opacity = 1;
    tip.replaceChildren(Object.assign(document.createElement('b'), {textContent: eur(h[idx].value)}), Object.assign(document.createElement('span'), {textContent: `${day(h[idx].day)}, ${karten(h[idx].cards)}`}));
    tip.style.left = Math.min(Math.max(px / VB_W * w, 70), w - 70) + 'px'; tip.style.opacity = 1;
  };
  const hide = () => { cross.style.opacity = 0; dot.style.opacity = 0; tip.style.opacity = 0; };
  plot.addEventListener('pointermove', e => {  // Fadenkreuz: der Tag, der dem Zeiger am nächsten liegt
    const r = plot.getBoundingClientRect(), tz = t[0] + (e.clientX - r.left) / r.width * (t.at(-1) - t[0]);
    show(t.reduce((best, tt, i) => Math.abs(tt - tz) < Math.abs(t[best] - tz) ? i : best, 0));
  });
  plot.addEventListener('pointerleave', hide);
  plot.addEventListener('focus', () => show(idx));
  plot.addEventListener('blur', hide);
  plot.addEventListener('keydown', e => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); show(idx + (e.key === 'ArrowLeft' ? -1 : 1)); } });
}

const NEWS_ICON = {upgrade: 'up', commander: 'crown', sell: 'euro', combo: 'infinity', combo_warn: 'alert', price: 'up', ban: 'alert', unban: 'check', gc: 'alert', gc_weg: 'info', reprint: 'refresh',
  radar_up: 'up', radar_down: 'down', posteingang: 'download', posteingang_warn: 'alert', sicherung_warn: 'alert'};
const NEWS_WARN = new Set(['combo_warn', 'ban', 'gc', 'posteingang_warn', 'sicherung_warn']);

// Preisbewegung: gestiegene und gefallene Karten im Besitz (Verlauf ab dem ersten Preis-Update, siehe mtg.movers)
const moverRow = e => `<div class="row" data-oid="${esc(e.oracle_id)}"${peekAt(e.image, e.name, `${eur(e.old)} auf ${eur(e.price)}`)}>${pic(small(e.image), '', 'thumb')}
  <div class="min0"><div class="name">${esc(e.name)}${e.foil ? ', Foil' : ''}</div><div class="sub2">${eur(e.old)} auf ${eur(e.price)} in ${e.days} Tagen</div></div>
  <div class="chips">${stackChips(e.stacks)}</div><div class="price">${icon(e.pct > 0 ? 'up' : 'down', 'sm')}${Math.round(Math.abs(e.pct) * 100)} %</div></div>`;
const moversHtml = m => !m.ready ? '<p class="muted">Die App merkt sich bei jeder Preis-Aktualisierung den Preis jeder Karte. Nach ein paar Tagen steht hier, was gestiegen oder gefallen ist.</p>'
  : !m.up.length && !m.down.length ? `<p class="muted">In den letzten ${m.span} Tagen hat sich bei keiner Karte der Preis um ${Math.round(m.min_pct * 100)} % oder mehr verändert (Karten ab ${eurMin(m.min_eur)}).</p>`
  : `<div class="split even">${[['Gestiegen', m.up], ['Gefallen', m.down]].map(([t, l]) => `<div><h3>${t}</h3>${l.length ? `<div class="rows">${l.map(moverRow).join('')}</div>` : '<p class="muted">nichts</p>'}</div>`).join('')}</div>`;
const moversSub = m => m.ready ? (m.span >= m.days ? `Vergleich mit dem Stand von vor ${m.days} Tagen oder früher` : `Vergleich mit dem ältesten Stand, ${m.span} Tage alt`) : '';

// --- Karten ------------------------------------------------------------------------------------------------------
const TYPES = [['Creature', 'Kreatur'], ['Instant', 'Spontanzauber'], ['Sorcery', 'Hexerei'], ['Artifact', 'Artefakt'], ['Enchantment', 'Verzauberung'], ['Land', 'Land'], ['Planeswalker', 'Planeswalker'], ['Legendary', 'Legendär']];
const RARITIES = [['common', 'Common'], ['uncommon', 'Uncommon'], ['rare', 'Rare'], ['mythic', 'Mythic']];
const SET_ORDER = [['set', 'Serie (neueste zuerst)'], ['setaz', 'Serie (A bis Z)']];  // innerhalb der Serie nach Sammlernummer
const SORTS = [['name', 'Name'], ['price', 'Preis'], ['qty', 'Menge'], ['added', 'Zuletzt hinzugefügt'], ['rank', 'Beliebtheit (EDHREC)'], ...SET_ORDER];
let seq = 0;

// Suchhilfe (Phase 18): dieselbe Syntax wie in der Kommandozeile (mtg suche), angelehnt an Scryfall
const SUCHHILFE = [['t:vampire', 'Typ enthält „vampire“'], ['o:"draw a card"', 'Kartentext enthält'], ['c:rg', 'mindestens Rot und Grün (c=rg: genau)'],
  ['id:bg', 'passt in ein Schwarz-Grün-Deck (Farbidentität)'], ['mv<=3', 'Manawert bis 3 (auch =, <, >, >=)'], ['r:m', 'Seltenheit: c, u, r, m'],
  ['set:dsk', 'Serie (Kürzel)'], ['lang:de', 'Sprache deiner Kopie'], ['is:foil', 'auch is:gamechanger, is:commander, is:reserved, is:arena'],
  ['otag:ramp', 'Rolle: ramp, draw, removal, wipe, tutor'], ['fn:landfall', 'Funktion wie beim Deckbau (auch fn:tokens, fn:graveyard …)'],
  ['eur>=5', 'Preis'], ['ort:kiste', 'Lagerort deiner Kopie (auch notiz:geschenk, is:verliehen)'], ['-t:land', 'Minus: nicht'], ['(r:m or eur>=10)', 'oder, mit Klammern']];
const FILTER_NAME = {q: 'Suche', type: 'Typ', rarity: 'Seltenheit', status: 'Stapel', binder: 'Binder', set: 'Serie', min: 'ab', fn: 'Funktion', color: 'Farben'};
let funktionen = null, llmStatus = null, llmZeit = 0;
const llmInfo = async () => { if (!llmStatus || Date.now() - llmZeit > 60000) { try { llmStatus = await api('llm'); } catch { llmStatus = {}; } llmZeit = Date.now(); } return llmStatus; };

async function viewCards(p) {
  const [{items: binders}, sets, fns, lm] = await Promise.all([api('binders'), api('sets'), funktionen || api('funktionen'), llmInfo()]);
  funktionen = fns;
  const bySet = Object.fromEntries(sets.items.map(x => [x.code, x]));
  const opt = (list, sel) => list.map(([v, l]) => `<option value="${esc(v)}"${v === sel ? ' selected' : ''}>${esc(l)}</option>`).join('');
  const on = new Set((p.get('color') || '').split(',').filter(Boolean));
  main.innerHTML = `${head('Karten', 'Alles, was du besitzt. Eine Kachel je Karte, über alle Editionen. Klick öffnet Details und Plan.')}
    <section class="sec" aria-label="Kartenliste">
    <form class="filters bar2" id="f" role="search" aria-label="Karten filtern">
      <span class="search wide">${icon('search', 'sm')}<input type="search" name="q" placeholder="${lm.chat ? 'Name, Suche wie t:vampire c:r, oder eine Frage' : 'Name, oder Suche wie t:vampire c:r mv<=3'}" aria-label="Name oder Suche" aria-describedby="suchhilfe" value="${esc(p.get('q') || '')}" spellcheck="false"></span>
      ${lm.chat ? `<button class="btn" type="button" id="frage" title="${esc(TIP.frage)}">Als Frage</button>` : ''}
      <span class="picks" id="colors" role="group" aria-label="Farben">${Object.keys(COLORS).map(k => `<button type="button" class="pick" data-c="${k}" aria-pressed="${on.has(k)}" aria-label="${COLORS[k]}" title="${COLORS[k]}">${pip(k, true)}</button>`).join('')}</span>
      <select name="sort" aria-label="Sortierung">${opt(SORTS.map(([v, l]) => [v, 'Sortiert nach ' + l]), p.get('sort') || 'name')}</select>
      <button class="btn" type="button" id="mehr-filter" aria-expanded="false" aria-controls="filter-mehr">Filter<span class="zahl" id="filter-n" hidden></span>${icon('arrow', 'sm')}</button>
      <div class="filter-mehr" id="filter-mehr" hidden>
        <select name="type" aria-label="Typ"><option value="">Alle Typen</option>${opt(TYPES, p.get('type'))}</select>
        <select name="rarity" aria-label="Seltenheit"><option value="">Alle Seltenheiten</option>${opt(RARITIES, p.get('rarity'))}</select>
        <select name="status" aria-label="Stapel"><option value="">Alle Stapel</option>${opt(STACKS.map(k => [k, LABEL[k]]), p.get('status'))}</select>
        <select name="binder" aria-label="Binder"><option value="">Alle Binder</option>${opt(binders.map(b => [b.name, `${b.name}${b.deck ? ' (Deck)' : b.type === 'scan' ? ' (Scan)' : ''}, ${num(b.cards)}`]), p.get('binder'))}</select>
        <select name="set" aria-label="Serie"><option value="">Alle Serien</option>${opt(sets.items.map(x => [x.code, `${x.name} (${x.code}), ${num(x.copies)}`]), (p.get('set') || '').toUpperCase())}</select>
        <select name="fn" aria-label="Funktion"><option value="">Alle Funktionen</option>${opt(fns.items, p.get('fn'))}</select>
        <label class="inl">ab <input type="number" name="min" min="0" step="0.5" value="${esc(p.get('min') || '')}" aria-label="Mindestpreis in Euro"> €</label>
      </div>
    </form>
    <details class="suchhilfe" id="suchhilfe"><summary>Suchhilfe</summary><dl>${SUCHHILFE.map(([k, t]) => `<dt><button type="button" class="link" data-suche="${esc(k)}">${esc(k)}</button></dt><dd>${esc(t)}</dd>`).join('')}</dl>
      <p class="note-line">Begriffe lassen sich kombinieren, zum Beispiel <code>t:creature id:bg fn:graveyard mv<=3</code>. Wörter ohne Doppelpunkt suchen im Namen.</p></details>
    ${lm.embed && lm.vektoren < lm.karten ? `<div class="gap-top">${note(['cards', 'Ähnliche Karten einschalten', `Dein lokales Ollama kann zu jeder Karte die ähnlichsten deiner Sammlung finden. Dafür rechnet es einmal ${num(lm.karten - lm.vektoren)} Karten durch (wenige Minuten).`, `<button class="btn" type="button" data-job="vektoren">Berechnen</button>`, 'vektoren'])}</div>` : ''}
    <div class="chips aktiv" id="aktiv"></div>
    <p class="muted count-line" id="count" aria-live="polite"></p><div class="grid" id="grid"></div><nav class="pager" id="pager" aria-label="Seiten"></nav></section>`;
  const f = $('#f'), mehr = $('#filter-mehr'), mehrNamen = $$('[name]', mehr).map(x => x.name);  // Typ, Seltenheit, Stapel, Binder, Serie, Funktion, Preis: hinter dem Knopf „Filter“
  $('#mehr-filter').onclick = e => { mehr.hidden = !mehr.hidden; e.currentTarget.setAttribute('aria-expanded', !mehr.hidden); };
  const query = page => {
    const q = new URLSearchParams();
    for (const [k, v] of new FormData(f)) if (v && !(k === 'sort' && v === 'name')) q.set(k, v);
    const c = $$('#colors [aria-pressed=true]').map(b => b.dataset.c).join(',');
    if (c) q.set('color', c);
    if (page > 1) q.set('page', page);
    return q;
  };
  const load = async page => {
    const q = query(page), mine = ++seq;
    const viewHash = '#/cards' + (String(q) ? '?' + q : '');
    history.replaceState(null, '', viewHash);
    rendered = viewHash;
    const nMehr = [...q].filter(([k]) => mehrNamen.includes(k)).length;
    $('#filter-n').textContent = nMehr; $('#filter-n').hidden = !nMehr;
    // aktive Filter als Marken, ein Klick nimmt einen weg
    $('#aktiv').innerHTML = [...q].filter(([k]) => FILTER_NAME[k]).map(([k, v]) => `<button type="button" class="chip" data-unset="${k}" aria-label="Filter ${esc(FILTER_NAME[k])} entfernen">${esc(FILTER_NAME[k])}: ${esc(
      k === 'color' ? v.split(',').map(c => COLORS[c]).join(', ') : k === 'fn' ? (fns.items.find(([x]) => x === v) || [, v])[1] : k === 'status' ? LABEL[v] : k === 'min' ? eurMin(+v) : v)}${icon('x', 'sm')}</button>`).join('');
    let r;
    try { r = await api('cards?' + q); }
    catch (e) {
      if (mine !== seq || e instanceof LoginNoetig) return;
      $('#count').innerHTML = `<span class="say bad">${esc(e.message)}</span>`; $('#grid').innerHTML = ''; $('#pager').innerHTML = '';
      return;
    }
    if (mine !== seq) return;  // neuere Anfrage läuft schon
    $('#count').textContent = r.total ? `${karten(r.total)} (${num(r.copies)} Exemplare)${r.pages > 1 ? `, Seite ${r.page} von ${r.pages}` : ''}` : '';
    if (r.hinweise?.length) $('#count').insertAdjacentHTML('beforeend', ` <span class="say">${esc(r.hinweise.join(' · '))}</span>`);
    // Serien-Sicht (Filter oder Sortierung nach Serie): ein Druck je Kachel mit Sammlernummer, bei Sortierung nach Serie mit Überschrift je Serie
    const grouped = SET_ORDER.some(([v]) => v === q.get('sort')), perPrint = grouped || q.get('set');
    const sethead = c => { const x = bySet[c.set]; return `<h3 class="sethead">${esc(c.set_name)} <small>${esc(c.set)}${x ? `, ${karten(x.copies)}${x.prints !== x.copies ? `, ${num(x.prints)} verschiedene` : ''}` : ''}</small></h3>`; };
    $('#grid').innerHTML = r.total ? r.items.map((c, i) => (grouped && (!i || c.set !== r.items[i - 1].set) ? sethead(c) : '') + tile(c, true, perPrint)).join('')
      : '<div class="empty">Keine Karte passt zu diesen Filtern.</div>';
    $('#pager').innerHTML = r.pages > 1 ? `<button class="btn" type="button" ${r.page <= 1 ? 'disabled' : ''} data-p="${r.page - 1}">${icon('left')}Zurück</button><span class="muted">Seite ${r.page} / ${r.pages}</span><button class="btn" type="button" ${r.page >= r.pages ? 'disabled' : ''} data-p="${r.page + 1}">Weiter${icon('right')}</button>` : '';
  };
  let timer;
  f.addEventListener('input', e => { clearTimeout(timer); timer = setTimeout(() => load(1), e.target.type === 'search' || e.target.type === 'number' ? 300 : 0); });
  $('#colors').addEventListener('click', e => { const b = e.target.closest('button'); if (b) { b.setAttribute('aria-pressed', b.getAttribute('aria-pressed') !== 'true'); load(1); } });
  $('#pager').addEventListener('click', e => { const b = e.target.closest('button[data-p]'); if (b) { load(+b.dataset.p); f.scrollIntoView(); } });
  $('#aktiv').addEventListener('click', e => {
    const b = e.target.closest('[data-unset]');
    if (!b) return;
    const k = b.dataset.unset;
    if (k === 'color') $$('#colors [aria-pressed=true]').forEach(x => x.setAttribute('aria-pressed', 'false')); else f.elements[k].value = '';
    load(1);
  });
  const fb = $('#frage');
  if (fb) fb.onclick = async () => {  // Frage an das lokale Modell: zurück kommt nur eine Suche, die angezeigt und normal ausgeführt wird
    const text = f.q.value.trim();
    if (!text) { f.q.focus(); return flash('Erst eine Frage eintippen, zum Beispiel: rote Drachen unter 2 Euro'); }
    fb.disabled = true; fb.textContent = 'Denkt nach …';
    try { const r = await post('frage', {text}); f.q.value = r.suche; flash(`Gesucht: ${r.suche}`); load(1); }
    catch (e) { flash(e.message); }
    fb.disabled = false; fb.textContent = 'Als Frage';
  };
  jobsUi();
  $('#suchhilfe').addEventListener('click', e => {  // Beispiel anklicken: an die Suche anhängen
    const b = e.target.closest('[data-suche]');
    if (!b) return;
    f.q.value = (f.q.value.trim() + ' ' + b.dataset.suche).trim(); f.q.focus(); load(1);
  });
  await load(+p.get('page') || 1);
}

// --- Serien: welche Serien sind im Bestand, wie viele Karten, wann zuletzt hinzugefügt ---------------------------------
const SETS_SORTS = [['new', 'Erscheinungsdatum (neueste zuerst)'], ['added', 'Zuletzt hinzugefügt'], ['name', 'Name'], ['cards', 'Meiste Karten'], ['value', 'Wert']];
const date = iso => iso ? new Date(iso.slice(0, 10) + 'T12:00:00').toLocaleDateString('de-DE') : 'unbekannt';
const setRow = x => `<a class="row set" href="#/binder?set=${encodeURIComponent(x.code)}"${peekAt(x.image, x.name, eur(x.value))}>${pic(small(x.image), '', 'thumb')}
  <div class="min0"><div class="name">${esc(x.name)} <span class="muted">${esc(x.code)}</span></div>
    <div class="sub2">${x.released ? `erschienen ${date(x.released)}, ` : ''}zuletzt hinzugefügt ${day(x.last_added)}</div>
    ${x.size ? `<div class="setstand" title="${esc(TIP.setstand)}"><span class="progress"><span style="--p:${(x.have / x.size).toFixed(3)}"></span></span><span class="sub2">${num(x.have)} von ${num(x.size)} Drucken</span></div>` : ''}</div>
  <div class="cnt">${karten(x.copies)}${x.prints !== x.copies && !x.size ? `<div class="sub2">${num(x.prints)} verschiedene</div>` : ''}</div><div class="price">${eur(x.value)}</div></a>`;

async function viewSets(p) {
  main.innerHTML = `${head('Serien', 'Welche Serien du schon eingescannt hast, mit Karten, Wert und wie viel vom Set dir fehlt. Klick zeigt die Serie als Binder, fehlende Karten grau.')}
    <section class="sec" aria-label="Serien">
    <form class="filters bar2" id="f" role="search" aria-label="Serien filtern">
      <span class="search">${icon('search', 'sm')}<input type="search" name="q" placeholder="Serie oder Kürzel" aria-label="Serie suchen (Name oder Kürzel)" value="${esc(p.get('q') || '')}"></span>
      <select name="sort" aria-label="Sortierung">${SETS_SORTS.map(([v, l]) => `<option value="${v}"${v === (p.get('sort') || 'new') ? ' selected' : ''}>Sortiert nach ${esc(l)}</option>`).join('')}</select>
    </form>
    <p class="muted count-line" id="count" aria-live="polite"></p><div class="rows" id="list"></div></section>`;
  const f = $('#f');
  const load = async () => {
    const q = new URLSearchParams();
    for (const [k, v] of new FormData(f)) if (v && !(k === 'sort' && v === 'new')) q.set(k, v);
    const viewHash = '#/sets' + (String(q) ? '?' + q : ''), mine = ++seq;
    history.replaceState(null, '', viewHash);
    rendered = viewHash;
    const r = await api('sets?' + q);
    if (mine !== seq) return;  // neuere Anfrage läuft schon
    $('#count').textContent = r.total ? `${plural(r.total, 'Serie', 'Serien')}, ${karten(r.copies)}` : '';
    $('#list').innerHTML = r.total ? r.items.map(setRow).join('')
      : `<div class="empty">${q.get('q') ? `Keine Karte aus einer Serie „${esc(q.get('q'))}“ im Bestand: noch nicht eingescannt oder der Export deiner Scanner-App noch nicht hochgeladen.` : 'Noch keine Karten im Bestand.'}</div>`;
  };
  let timer;
  f.addEventListener('input', e => { clearTimeout(timer); timer = setTimeout(load, e.target.type === 'search' ? 300 : 0); });
  await load();
}

// --- Sammler-Bibel (Phase 20): Set als Binder, Jahresrückblick, Wert-Bericht ------------------------------------------
async function viewBinder(p) {
  const code = p.get('set') || '', nur = p.get('fehlend') === '1';
  const r = await api('set-binder?set=' + encodeURIComponent(code));
  const hat = r.karten.filter(k => k.qty).length, zeigen = nur ? r.karten.filter(k => !k.qty) : r.karten, seiten = [];
  for (let i = 0; i < zeigen.length; i += 9) seiten.push(zeigen.slice(i, i + 9));
  const link = `#/binder?set=${encodeURIComponent(r.set)}`;
  main.innerHTML = `${head(`${esc(r.name)} <span class="muted">${esc(r.set)}</span>`, `Du hast ${num(hat)} von ${num(r.karten.length)} Drucken. Neun Karten je Binderseite, nach Sammlernummer, fehlende grau.`,
    `<a class="btn ghost" href="#/sets">${icon('left')}Alle Serien</a><a class="btn" href="${nur ? link : link + '&fehlend=1'}">${nur ? 'Alle zeigen' : 'Nur fehlende'}</a><a class="btn" href="#/cards?set=${encodeURIComponent(r.set)}&sort=set">Als Liste</a>`)}
    ${seiten.map((seite, i) => `<section class="sec" aria-label="Binderseite ${i + 1}"><h2>Seite ${i + 1}</h2><div class="binder9">${seite.map(k => k.qty
      ? `<a class="card" href="#" data-oid="${esc(k.oracle_id)}"${peekAt(k.image, k.name, `#${k.number}, ${k.qty}× im Besitz`)}>${pic(k.image, k.name)}<span class="cap"><span class="q">#${esc(k.number)}</span><span class="p">${k.qty}×</span></span></a>`
      : `<div class="card fehlt"${peekAt(k.image, k.name, `#${k.number} fehlt`)}>${pic(k.image, k.name)}<span class="cap"><span class="q">#${esc(k.number)}</span><span class="q">fehlt</span></span></div>`).join('')}</div></section>`).join('')
    || `<div class="empty">${nur ? 'Dir fehlt keine Karte aus diesem Set.' : 'Scryfall kennt keine Karten zu diesem Kürzel.'}</div>`}`;
}

const MONAT = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];
async function viewRueckblick(p) {
  const r = await api('rueckblick' + (p.get('jahr') ? '?jahr=' + encodeURIComponent(p.get('jahr')) : ''));
  const max = Math.max(...r.monate.map(m => m.karten), 1);
  main.innerHTML = `${head(`Rückblick ${esc(r.jahr)}`, 'Dein Sammeljahr in Zahlen: wann du wie viel eingescannt hast (Datum aus dem Export oder vom Erfassen), deine besten Funde und was verkauft ist. Wert zu heutigen Preisen.',
    r.jahre.filter(j => j !== r.jahr).slice(0, 4).map(j => `<a class="btn ghost" href="#/rueckblick?jahr=${esc(j)}">${esc(j)}</a>`).join(''))}
    <section class="sec" aria-label="Zahlen"><dl class="hstats"><div><dt>Eingescannt</dt><dd>${num(r.karten)}</dd></div><div><dt>Wert heute</dt><dd>${eur0(r.wert)}</dd></div>
      <div><dt>Verkauft</dt><dd>${num(r.verkauft.karten)}</dd></div><div><dt>Erlös laut Preis</dt><dd>${eur0(r.verkauft.wert)}</dd></div><div><dt>Decks gebaut</dt><dd>${num(r.decks)}</dd></div>${r.spiele ? `<div><dt>Spiele</dt><dd>${num(r.spiele)}</dd></div><div><dt>Meist gespielt</dt><dd class="txt">${esc(r.meist.deck)}</dd></div>` : ''}</dl></section>
    ${r.monate.length ? `<section class="sec" aria-label="Je Monat"><h2>Je Monat <small>eingescannte Karten</small></h2><div class="bars wide">${r.monate.map(m => `<span class="lbl">${MONAT[+m.monat.slice(5, 7) - 1]}</span>
      <span class="track"><span style="--w:${(m.karten / max * 100).toFixed(1)}%" title="${esc(m.monat)}: ${karten(m.karten)}, ${eur0(m.wert)}"></span></span><span class="val">${karten(m.karten)}, ${eur0(m.wert)}</span>`).join('')}</div></section>`
      : `<div class="empty">In ${esc(r.jahr)} hast du keine Karten eingescannt, die noch im Bestand sind.</div>`}
    ${r.funde.length ? `<section class="sec" aria-label="Beste Funde"><h2>Beste Funde ${esc(r.jahr)}</h2><div class="rail">${r.funde.map(c => tile(c)).join('')}</div></section>` : ''}
    <p class="note-line"><a href="#/bericht">${icon('printer', 'sm')}Wert-Bericht zum Drucken</a></p>`;
}

async function viewBericht(p) {
  const mit = p.get('kaufpreise') === '1', r = await api('bericht' + (mit ? '?kaufpreise=1' : '')), wer = fremd();
  const stand = new Date(r.stichtag).toLocaleString('de-DE', {dateStyle: 'long', timeStyle: 'short'});
  main.innerHTML = `${head('Wert-Bericht', `Für Versicherung oder Nachlass: Stand ${esc(stand)}${wer ? `, Sammlung ${esc(wer.anzeige)}` : ''}.`,
    `<a class="btn ghost noprint" href="#/bericht${mit ? '' : '?kaufpreise=1'}">${mit ? 'Ohne Kaufpreise' : 'Mit Kaufpreisen'}</a><button class="btn primary noprint" type="button" id="drucken">${icon('printer')}Drucken</button>`)}
    <section class="sec" aria-label="Summe"><dl class="hstats"><div><dt>Wert</dt><dd>${eur(r.wert)}</dd></div><div><dt>Karten</dt><dd>${num(r.karten)}</dd></div><div><dt>Verschiedene</dt><dd>${num(r.unique)}</dd></div>
      ${r.paid ? `<div><dt>Bezahlt (${karten(r.paid.cards)})</dt><dd>${eur(r.paid.paid)}</dd></div>` : ''}</dl><p class="note-line">${esc(r.quelle)}.</p></section>
    <section class="sec" aria-label="Nach Binder"><h2>Nach Binder</h2><div class="tblscroll"><table class="tbl bericht"><thead><tr><th>Binder</th><th class="rt">Karten</th><th class="rt">Wert</th></tr></thead>
      <tbody>${r.binder.map(b => `<tr><td>${esc(b.binder)}</td><td class="rt">${num(b.karten)}</td><td class="rt">${eur(b.wert)}</td></tr>`).join('')}</tbody></table></div></section>
    <section class="sec" aria-label="Wertvollste Karten"><h2>Die ${r.top.length} wertvollsten Karten</h2><div class="tblscroll"><table class="tbl bericht"><thead><tr><th>Karte</th><th>Druck</th><th>Ausführung</th><th class="rt">Anzahl</th><th class="rt">Preis</th><th class="rt">Summe</th>${mit ? '<th class="rt">Bezahlt</th>' : ''}</tr></thead>
      <tbody>${r.top.map(k => `<tr><td>${esc(k.name)}</td><td>${esc(k.set_code)} #${esc(k.number)}</td><td>${[k.foil !== 'normal' ? k.foil : '', LANG[k.language] || k.language, COND[k.condition] || k.condition].filter(Boolean).map(esc).join(', ')}</td>
        <td class="rt">${k.qty}</td><td class="rt">${eur(k.price)}</td><td class="rt">${eur(k.summe)}</td>${mit ? `<td class="rt">${k.paid != null ? eur(k.paid) : ''}</td>` : ''}</tr>`).join('')}</tbody></table></div></section>`;
  $('#drucken').onclick = () => print();
}

// --- Spiele (Phase 21): eintragen in zwei Klicks, Auswertung je Deck, Spielgruppe und „Welches Deck heute?“ ---------------
async function viewSpiele() {
  const r = await api('spiele'), mine = r.decks.filter(d => d.kind), letzt = r.letzte[0]?.deck;
  const brSel = d => `<select data-dbr="${esc(d.name)}" aria-label="Bracket von ${esc(d.name)}">${[1, 2, 3, 4, 5].map(b => `<option value="${b}"${b === d.bracket ? ' selected' : ''}>${b}${d.geschaetzt && b === d.bracket ? ' (geschätzt)' : ''}</option>`).join('')}</select>`;
  main.innerHTML = `${head('Spiele', 'Nach jeder Runde: Deck wählen, Gewonnen oder Nicht gewonnen. Daraus kommen Siegquote, Lieblingsdecks und Decks, die nur noch im Regal stehen.')}
    ${aus('edhrec') && !r.salt_da ? ausZeile('edhrec', 'Die Salt-Werte der Karten (Umfrage von EDHREC) fehlen deshalb.') : ''}
    ${mine.length ? `<section class="sec" aria-label="Spiel eintragen"><form class="spielform" data-spiel="1"><button type="submit" hidden disabled aria-hidden="true"></button>
      <div class="filters"><select name="deck" required aria-label="Deck">${mine.map(d => `<option${d.name === letzt ? ' selected' : ''}>${esc(d.name)}</option>`).join('')}</select>
        <button class="btn primary" type="submit" value="1">${icon('check')}Gewonnen</button><button class="btn" type="submit" value="0">Nicht gewonnen</button></div>
      <details class="mehr"><summary>Tisch, Spieler, Züge, Notiz</summary><div class="filters">
        <input name="pod" list="pods" placeholder="Tisch, zum Beispiel Freitagsrunde" aria-label="Tisch">
        <label class="inl">Spieler <input name="players" type="number" min="2" max="10" value="4" class="tight"></label>
        <label class="inl">Züge <input name="turns" type="number" min="1" max="99" class="tight"></label>
        <input name="notes" maxlength="500" class="grow" placeholder="Notiz" aria-label="Notiz"></div></details></form>
      <datalist id="pods">${r.pods.map(x => `<option value="${esc(x)}">`).join('')}</datalist></section>`
      : `<div class="empty">Noch kein Deck. Bau eins unter Decks oder lade eine fertige Deckliste hoch, dann trägst du hier Spiele ein.</div>`}
    ${r.ruhen.length ? `<section class="sec" aria-label="Lange nicht gespielt"><div class="todo">${note(['info', `Seit ${r.ruht_tage} Tagen nicht gespielt: ${r.ruhen.slice(0, 4).join(', ')}${r.ruhen.length > 4 ? ` und ${r.ruhen.length - 4} weitere` : ''}`, 'Kandidaten zum Zerlegen: ihre Karten werden wieder frei für neue Decks.', ''])}</div></section>` : ''}
    ${r.decks.length ? `<section class="sec" aria-label="Deine Decks"><h2>Deine Decks <small>Quote ab ${r.min} Spielen</small></h2>
      <div class="tblscroll"><table class="tbl spiele"><thead><tr><th>Deck</th><th>Bracket ${info('bracketfertig', 'Bracket')}</th><th class="rt">Spiele</th><th class="rt">Siege</th><th class="rt">Quote</th><th>Zuletzt</th>${r.salt_da ? `<th>Salt ${info('salt', 'Salt')}</th>` : ''}</tr></thead>
      <tbody>${r.decks.map(d => `<tr><td>${pips(d.ci)} ${esc(d.name)}</td><td>${d.kind === 'fertig' ? brSel(d) : d.bracket ?? ''}</td>
        <td class="rt">${num(d.spiele)}</td><td class="rt">${num(d.siege)}</td><td class="rt">${d.quote != null ? Math.round(d.quote * 100) + ' %' : '<span class="muted">zu wenige</span>'}</td>
        <td>${d.zuletzt ? date(d.zuletzt) : '<span class="muted">nie</span>'}</td>${r.salt_da ? `<td>${d.salt?.karten.length ? `${fmt(d.salt.summe, 1)} <span class="sub2">${esc(d.salt.karten.join(', '))}</span>` : '<span class="muted">0</span>'}</td>` : ''}</tr>`).join('')}</tbody></table></div></section>` : ''}
    <section class="sec" aria-label="Spielgruppe"><h2>Spielgruppe <small>Welches Deck passt heute? ${info('tisch', 'Welches Deck passt heute?')}</small></h2>
      ${r.gruppe.length ? `<form data-tisch="1"><div class="gruppe">${r.gruppe.map(g => `<div class="gzeile"><label><input type="checkbox" name="g" value="${g.id}"> <span><b>${esc(g.spieler)}</b>: ${esc(g.deck)}</span> ${g.ci ? pips(g.ci) : '<span class="muted">Farben?</span>'} <span class="muted">Bracket ${g.bracket}${g.pod ? ', ' + esc(g.pod) : ''}</span></label>
        <button class="btn small ghost" type="button" data-gweg="${g.id}" aria-label="${esc(g.deck)} von ${esc(g.spieler)} entfernen">${icon('x', 'sm')}</button></div>`).join('')}</div>
        <button class="btn primary" type="submit">Welches Deck heute?</button></form><div id="tisch" aria-live="polite"></div>`
        : '<p class="muted">Trag die Decks deiner Mitspieler ein. Dann schlägt die App vor, welches deiner Decks zum Tisch passt.</p>'}
      <form class="filters gform" data-gruppe="1"><input name="spieler" required placeholder="Spieler" aria-label="Spieler"><input name="deck" required class="grow" placeholder="Deck oder Commander" aria-label="Deck oder Commander">
        <select name="bracket" aria-label="Bracket">${[1, 2, 3, 4, 5].map(b => `<option value="${b}"${b === 3 ? ' selected' : ''}>Bracket ${b}</option>`).join('')}</select>
        <input name="farben" maxlength="5" class="tight" placeholder="Farben" aria-label="Farben als Buchstaben, zum Beispiel wub (leer: vom Commander)" title="Farben als Buchstaben, zum Beispiel wub. Leer: vom Commander, wenn die App die Karte kennt.">
        <input name="pod" list="pods" placeholder="Tisch" aria-label="Tisch"><button class="btn" type="submit">${icon('plus')}Hinzufügen</button></form></section>
    ${r.letzte.length ? `<section class="sec" aria-label="Letzte Spiele"><h2>Letzte Spiele</h2><div class="rows">${r.letzte.map(g => `<div class="row spiel"><div class="min0"><div class="name">${esc(g.deck)}</div>
      <div class="sub2">${[date(g.at), g.pod, `${g.players} Spieler`, g.turns ? `${g.turns} Züge` : '', g.notes].filter(Boolean).map(esc).join(', ')}</div></div>
      <span class="chip">${g.won ? 'gewonnen' : 'nicht gewonnen'}</span><button class="btn small ghost" type="button" data-sweg="${g.id}" aria-label="Spiel vom ${esc(date(g.at))} löschen">${icon('x', 'sm')}</button></div>`).join('')}</div></section>` : ''}`;
}
async function spielForm(f, knopf) {  // Enter in einem Feld trägt nichts ein: der erste (versteckte) Knopf ist gesperrt
  const d = Object.fromEntries(new FormData(f)), won = knopf?.value === '1';
  try { await post('spiel', {...d, won}); flash(`Eingetragen: ${d.deck}, ${won ? 'gewonnen' : 'nicht gewonnen'}`); await render(true); }
  catch (e) { flash('Fehler: ' + e.message); }
}
async function gruppeForm(f) {
  try { await post('gruppe', Object.fromEntries(new FormData(f))); flash('Zur Spielgruppe hinzugefügt'); await render(true); }
  catch (e) { flash('Fehler: ' + e.message); }
}
const tischGrund = (d, ziel) => [d.abstand ? `Bracket ${d.bracket}, eine Stufe ${d.bracket > ziel ? 'stärker' : 'schwächer'} als der Tisch` : `Bracket ${d.bracket} wie der Tisch`,
  d.gleich ? `teilt ${d.gleich.length === 1 ? 'die Farbe' : 'die Farben'} ${d.gleich} mit dem Tisch` : 'andere Farben als der Tisch', d.zuletzt ? `zuletzt am ${date(d.zuletzt)}` : 'noch nie gespielt'].join(', ');
async function tischForm(f) {
  const ids = new FormData(f).getAll('g');
  if (!ids.length) return flash('Wähl die Decks, die heute am Tisch sitzen.');
  try {
    const r = await api('tisch?ids=' + ids.join(','));
    $('#tisch').innerHTML = `<p class="lead">Der Tisch spielt Bracket ${r.ziel}. ${r.decks.length ? 'Am besten passt:' : ''}</p>${r.decks.length
      ? `<div class="rows">${r.decks.map((d, i) => `<div class="row tischdeck${i ? '' : ' erst'}"><div class="min0"><div class="name">${pips(d.ci)} ${esc(d.name)}</div><div class="sub2">${esc(tischGrund(d, r.ziel))}</div></div></div>`).join('')}</div>`
      : '<div class="empty">Keins deiner Decks liegt höchstens eine Stufe vom Tisch entfernt. Bau eins unter Decks oder stell bei fertigen Decks das Bracket ein.</div>'}`;
  } catch (e) { flash('Fehler: ' + e.message); }
}
const spielWeg = async (pfad, id, text) => { try { await post(pfad, {id: +id}); flash(text); await render(true); } catch (e) { flash('Fehler: ' + e.message); } };

// --- Drucken (Phase 22): Trennkarten und Etiketten, Proxy-Blatt. Maße stehen als Konstanten in style.css (--trenn-*, --etikett-*, --proxy-*) ---
const BOGEN = {trenn: 9, etikett: 24, proxy: 9};  // je A4-Seite: Trennkarten 3×3, Etiketten 3×8, Proxys 3×3
const boegen = (art, html) => { const seiten = []; for (let i = 0; i < html.length; i += BOGEN[art]) seiten.push(html.slice(i, i + BOGEN[art])); return seiten.map(x => `<div class="bogen ${art}">${x.join('')}</div>`).join(''); };
async function viewDruck(p) {
  const art = p.get('art') === 'etikett' ? 'etikett' : 'trenn', was = ['serien', 'binder', 'decks'].includes(p.get('was')) ? p.get('was') : 'serien';
  const [sets, binders, spiele] = await Promise.all([api('sets'), api('binders'), api('spiele')]);
  const items = was === 'serien' ? sets.items.map(x => ({titel: x.name, sub: [x.code, x.released?.slice(0, 4)].filter(Boolean).join(', '), zahl: karten(x.copies)}))
    : was === 'binder' ? binders.items.filter(b => !b.deck).map(b => ({titel: b.name, sub: 'Binder', zahl: karten(b.cards)}))
    : spiele.decks.filter(d => d.kind).map(d => ({titel: d.name, sub: `Bracket ${d.bracket}`, ci: d.ci, zahl: d.kind === 'fertig' ? 'fertiges Deck' : 'gebaut'}));
  const link = (a, w) => `#/druck?art=${a}&was=${w}`;
  main.innerHTML = `${head('Drucken', 'Trennkarten für Kisten und Etiketten für Boxen und Binder. Hak an, was du brauchst, dann Drucken (A4, Skalierung 100 %).',
    `${proxyAn() ? '<a class="btn ghost" href="#/proxy">Proxy-Blatt</a>' : ''}<button class="btn primary" type="button" id="print">${icon('printer')}Drucken</button>`)}
    <section class="sec noprint" aria-label="Auswahl"><div class="seg">${[['trenn', 'Trennkarten 63 × 95 mm'], ['etikett', 'Etiketten 70 × 37 mm']].map(([a, l]) => `<a class="btn small" href="${link(a, was)}" aria-pressed="${a === art}">${l}</a>`).join('')}</div>
      <div class="seg gap-top">${[['serien', 'Serien'], ['binder', 'Binder'], ['decks', 'Decks']].map(([w, l]) => `<a class="btn small" href="${link(art, w)}" aria-pressed="${w === was}">${l}</a>`).join('')}</div>
      <div class="druckwahl gap-top">${items.length ? `<label class="inl"><input type="checkbox" id="alle"> alle</label>${items.map((x, i) => `<label class="inl"><input type="checkbox" data-druck="${i}"> ${esc(x.titel)}</label>`).join('')}` : '<span class="muted">Nichts da.</span>'}</div></section>
    <section class="sec" aria-label="Vorschau"><div class="boegen" id="boegen"><p class="muted noprint">Noch nichts ausgewählt.</p></div></section>`;
  const zeichnen = () => {
    const wahl = [...document.querySelectorAll('[data-druck]')].filter(c => c.checked).map(c => items[+c.dataset.druck]);
    $('#boegen').innerHTML = wahl.length ? boegen(art, wahl.map(x => `<div class="${art}karte"><b>${esc(x.titel)}</b><span>${x.ci != null ? pips(x.ci) + ' ' : ''}${esc(x.sub)}</span><small>${esc(x.zahl)}</small></div>`))
      : '<p class="muted noprint">Noch nichts ausgewählt.</p>';
  };
  main.querySelector('.druckwahl')?.addEventListener('change', e => {
    if (e.target.id === 'alle') document.querySelectorAll('[data-druck]').forEach(c => { c.checked = e.target.checked; });
    zeichnen();
  });
  $('#print').onclick = () => print();
}

async function viewProxy(p) {
  if (!proxyAn()) {  // aus: kein Formular, die Schnittstelle antwortet ebenfalls nicht (403); das Hauptkonto schaltet es unter Konten und Sicherung ein
    main.innerHTML = `${head('Proxy-Blatt', 'Das Proxy-Blatt ist ausgeschaltet.', `<a class="btn ghost" href="#/druck">Trennkarten und Etiketten</a>`)}
      <div class="todo">${note(['info', 'Das Proxy-Blatt ist aus', `${TIP.proxyblatt} ${sess.rolle === 'haupt' ? 'Einschalten kannst du es unter „Konten und Sicherung“.' : 'Das Hauptkonto schaltet es ein.'}`,
        sess.rolle === 'haupt' ? `<a class="btn" href="#/konten">Konten und Sicherung</a>` : ''])}</div>`;
    return;
  }
  main.innerHTML = `${head('Proxy-Blatt', 'Zum Ausprobieren, bevor du kaufst: neun Karten je A4-Seite in Originalgröße, jede mit dem Aufdruck „Playtest“. Ein Name je Zeile, Anzahl davor geht auch, Decklisten auch.',
    `<a class="btn ghost" href="#/druck">Trennkarten und Etiketten</a><button class="btn primary" type="button" id="print" disabled>${icon('printer')}Drucken</button>`)}
    <section class="sec noprint" aria-label="Karten"><form class="proxyform" data-proxy="1"><textarea name="text" rows="8" required aria-label="Karten, eine je Zeile" placeholder="1 Sol Ring&#10;Rhystic Study">${esc(p.get('karten') || '')}</textarea>
      <button class="btn" type="submit">Blatt erstellen</button></form><p class="muted" id="proxyinfo" aria-live="polite"></p></section>
    <section class="sec" aria-label="Vorschau"><div class="boegen" id="boegen"></div></section>`;
  $('#print').onclick = () => print();
  if (p.get('karten')) proxyForm(main.querySelector('[data-proxy]'));
}
async function proxyForm(f) {
  try {
    const r = await post('proxy', {text: f.text.value});
    const bilder = r.karten.flatMap(k => Array(k.qty).fill(k)).map(k => `<figure class="proxykarte">${k.image ? `<img alt="${esc(k.name)}" src="${esc(k.image)}">` : `<span class="noimg">${esc(k.name)}</span>`}<figcaption>Playtest</figcaption></figure>`);
    $('#boegen').innerHTML = boegen('proxy', bilder);
    $('#proxyinfo').textContent = `${karten(bilder.length)} auf ${plural(Math.ceil(bilder.length / BOGEN.proxy), 'Seite', 'Seiten')}${r.fehlt.length ? `. Nicht gefunden: ${r.fehlt.join(', ')}` : ''}`;
    $('#print').disabled = !bilder.length;
  } catch (e) { flash('Fehler: ' + e.message); }
}

// --- Sortieren: Binder wählen, Karten in Reihenfolge mit Ziel-Stapel ---------------------------------------------
async function viewSort(p) {
  const binder = p.get('binder');
  if (!binder) {
    const r = await api('sort');
    main.innerHTML = `${head('Sortieren', 'Wähl einen Binder. Du bekommst die Karten in Scan-Reihenfolge und legst jede auf den angezeigten Stapel.')}${aus('edhrec') ? ausZeile('edhrec', 'Staples zählen nach dem EDHREC-Rang von Scryfall und den schon gemerkten Listen deiner besten Commander; neue Listen lädt die App nicht.') : ''}
      <section class="sec" aria-label="Binder"><div class="rows">${r.binders.map(b => `
      <a class="row binder" href="#/sort?binder=${encodeURIComponent(b.name)}"><div class="min0"><div class="name">${esc(b.name)}</div><div class="sub2">${karten(b.cards)}</div></div>
      <div class="chips">${STACKS.filter(k => b.stacks[k]).map(k => chip(k, `${num(b.stacks[k])} ${LABEL[k].toLowerCase()}`)).join('')}</div><span class="go">${icon('right')}</span></a>`).join('') || '<div class="empty">Noch keine Binder. Lade zuerst eine Datei hoch.</div>'}</div></section>`;
    return;
  }
  const ORDERS = [['scan', 'wie gescannt'], ['name', 'nach Name'], ['set', 'nach Serie (neueste zuerst)'], ['setaz', 'nach Serie (A bis Z)']];
  const order = p.get('order') || 'scan', page = +p.get('page') || 1;
  const r = await api(`sort?binder=${encodeURIComponent(binder)}&order=${order}&page=${page}`);
  const link = (o, pg) => `#/sort?binder=${encodeURIComponent(binder)}${o !== 'scan' ? '&order=' + o : ''}${pg > 1 ? '&page=' + pg : ''}`;
  main.innerHTML = `${head(esc(binder), `${num(r.total)} Zeilen. Nimm die Karten der Reihe nach und leg jede auf den Stapel daneben.`, `<a class="btn ghost" href="#/sort">${icon('left')}Alle Binder</a>${r.rows.length ? `<button class="btn primary" id="spiel" type="button">${icon('cards')}Karte für Karte</button>` : ''}<button class="btn" id="print" type="button">${icon('printer')}Drucken</button>`)}
    <section class="sec" aria-label="Stapel">${legend(Object.fromEntries(STACKS.map(k => [k, r.counts[k]])))}</section>
    <section class="sec" aria-label="Karten in Reihenfolge">
      <div class="toolbar noprint"><label class="inl">Reihenfolge <select id="order">${ORDERS.map(([v, l]) => `<option value="${v}"${v === order ? ' selected' : ''}>${l}</option>`).join('')}</select></label></div>
      <div class="rows">${r.rows.map(z => `<div class="row" data-oid="${esc(z.oracle_id)}"${peekAt(z.image, z.name, eur(z.price))}>${pic(small(z.image), '', 'thumb')}
        <div class="min0"><div class="name">${esc(z.name)}</div><div class="sub2">${esc(z.set)} #${esc(z.number)}, ${esc(LANG[z.language] || z.language)}${z.foil !== 'normal' ? ', ' + esc(z.foil) : ''}</div></div>
        <div class="chips big">${z.stacks.map(s => chip(s.stack, stapelText(z, s))).join('')}</div>
        <div class="price">${eur(z.price)}</div></div>`).join('')}</div>
      ${r.pages > 1 ? `<nav class="pager noprint" aria-label="Seiten"><a class="btn" ${page <= 1 ? 'aria-disabled="true"' : `href="${link(order, page - 1)}"`}>${icon('left')}Zurück</a><span class="muted">Seite ${r.page} / ${r.pages}</span><a class="btn" ${page >= r.pages ? 'aria-disabled="true"' : `href="${link(order, page + 1)}"`}>Weiter${icon('right')}</a></nav>` : ''}
    </section>`;
  $('#order').onchange = e => { location.hash = link(e.target.value, 1); };
  $('#print').onclick = () => print();
  $('#spiel')?.addEventListener('click', () => sortSpiel(r.rows, page < r.pages ? link(order, page + 1) : null));
}
const stapelText = (z, s) => `${s.qty > 1 || z.stacks.length > 1 ? s.qty + '× ' : ''}${s.stack === 'deck' ? s.deck : LABEL[s.stack]}`;
// Karte für Karte: die Karten einer Seite nacheinander, groß, mit dem Stapel, auf den sie gehören. Die Karte fliegt dorthin, der Zähler springt.
function sortSpiel(rows, naechste) {
  const gelegt = Object.fromEntries(STACKS.map(k => [k, 0])), von = document.activeElement;
  let i = 0, busy = false;
  const box = document.createElement('div');
  box.className = 'kk noprint';
  box.setAttribute('role', 'dialog'); box.setAttribute('aria-modal', 'true'); box.setAttribute('aria-label', 'Karte für Karte sortieren');
  box.innerHTML = `<div class="kk-kopf"><button class="btn ghost" type="button" data-s="zu">${icon('x')}Beenden</button><span class="progress" aria-hidden="true"><span id="sp-p" style="--p:0"></span></span><span class="muted" id="sp-n"></span></div>
    <div class="kk-buehne" id="sp-b" aria-live="polite"></div>
    <div class="kk-stapel">${STACKS.map(k => `<div class="kk-haufen s-${k}" data-pile="${k}"><span>${LABEL[k]}</span><b>0</b></div>`).join('')}</div>
    <div class="kk-tasten"><button class="btn" type="button" data-s="zurueck">${icon('left')}Zurück</button><button class="btn primary" type="button" data-s="weiter">Weiter${icon('right')}</button><span class="muted">Leertaste oder Pfeiltasten</span></div>`;
  const zeigen = () => {
    const z = rows[i];
    $('#sp-n', box).textContent = z ? `${i + 1} von ${rows.length}` : '';
    $('#sp-p', box).style.setProperty('--p', (i / rows.length).toFixed(3));
    $$('.kk-haufen', box).forEach(p => p.classList.toggle('ziel', !!z && z.stacks.some(s => s.stack === p.dataset.pile)));
    $('[data-s=weiter]', box).disabled = !z; $('[data-s=zurueck]', box).disabled = !i;
    $('#sp-b', box).innerHTML = z
      ? `${pic(z.image, z.name, 'kk-karte')}<div class="kk-text"><h2>${esc(z.name)}</h2><p class="muted">${esc(z.set)} #${esc(z.number)}, ${esc(LANG[z.language] || z.language)}${z.foil !== 'normal' ? ', ' + esc(z.foil) : ''}</p>
        <div class="chips big">${z.stacks.map(s => chip(s.stack, stapelText(z, s))).join('')}</div><p class="kk-preis">${eur(z.price)}</p></div>`
      : `<div class="kk-ende"><h2>Alles sortiert</h2><p class="muted">${karten(STACKS.reduce((n, k) => n + gelegt[k], 0))} liegen auf ihren Stapeln.</p>
        <div class="seg">${naechste ? `<a class="btn primary" href="${naechste}">Nächste Seite</a>` : ''}<button class="btn${naechste ? '' : ' primary'}" type="button" data-s="zu">Zur Liste</button></div></div>`;
    if (rows[i + 1]?.image) new Image().src = rows[i + 1].image;
    if (!z) $('.kk-ende .btn', box).focus();
  };
  const zaehler = (k, d) => { gelegt[k] += d; const p = $(`[data-pile="${k}"]`, box); $('b', p).textContent = gelegt[k]; p.classList.remove('pop'); void p.offsetWidth; p.classList.add('pop'); };
  const vor = async () => {
    const z = rows[i];
    if (busy || !z) return;
    busy = true;
    const img = $('.kk-karte', box), ziel = $(`[data-pile="${z.stacks[0].stack}"]`, box);
    if (img && !calm.matches) {  // die Karte fliegt auf ihren Stapel
      const a = img.getBoundingClientRect(), b = ziel.getBoundingClientRect();
      await img.animate([{transform: 'none', opacity: 1}, {transform: `translate(${b.left + b.width / 2 - a.left - a.width / 2}px, ${b.top + b.height / 2 - a.top - a.height / 2}px) scale(.12) rotate(14deg)`, opacity: .3}],
        {duration: 380, easing: 'cubic-bezier(.5, 0, .8, .4)', fill: 'forwards'}).finished.catch(() => {});
    }
    z.stacks.forEach(s => zaehler(s.stack, s.qty));
    i++; zeigen(); busy = false;
  };
  const zurueck = () => {
    if (busy || !i) return;
    rows[--i].stacks.forEach(s => zaehler(s.stack, -s.qty));
    zeigen();
  };
  const zu = () => { removeEventListener('hashchange', zu); document.removeEventListener('keydown', taste); box.remove(); von?.focus?.(); };
  const taste = e => {
    if (e.key === 'Escape') zu();
    else if (e.key === 'ArrowLeft') zurueck();
    else if (e.key === 'ArrowRight' || (/^( |Enter)$/.test(e.key) && !e.target.closest('button, a'))) { e.preventDefault(); vor(); }
  };
  box.onclick = e => {
    const b = e.target.closest('[data-s], .kk-karte');
    if (b) ({zu, zurueck, weiter: vor})[b.dataset.s || 'weiter']();
  };
  document.body.append(box);
  document.addEventListener('keydown', taste); addEventListener('hashchange', zu);
  zeigen(); $('[data-s=weiter]', box).focus();
}

// --- Verkaufen: Einzeln und Bulk, Regeln, Exporte, erkannte Verkäufe ----------------------------------------------
const skip = new Set(JSON.parse((() => { try { return localStorage.getItem('mtg-skip') || '[]'; } catch { return '[]'; } })()));
const saveSkip = () => { try { localStorage.setItem('mtg-skip', JSON.stringify([...skip])); } catch { /* privates Fenster */ } };
let sellTab = 'single';
const sellLang = () => { try { return localStorage.getItem('mtg-sell-lang') || ''; } catch { return ''; } };
const RARITY = {common: 'Common', uncommon: 'Uncommon', rare: 'Rare', mythic: 'Mythic', other: 'Sonstige (Tokens, Specials)'};

async function viewSell() {
  const lang = sellLang();
  const [r, pm, fd] = await Promise.all([api('sell' + (lang ? '?lang=' + lang : '')), api('prices'), api('fertige-decks')]);
  const R = r.rules, keepS = Math.max(R.keep, R.staples), kand = fd.binder.filter(b => !b.deck && b.type !== 'scan');
  const exp = (format, group, label, ic, cls = '') => `<a class="btn ${cls}" data-export="${format}" data-group="${group}" href="#">${icon(ic)}${label}</a>`;
  const sold = r.sold;
  main.innerHTML = `${head('Verkaufen', `Alles, was in keinem Deck steckt und über deine Behalten-Regel hinausgeht. Von jeder Karte bleibt mindestens ${R.keep === 1 ? 'eine' : R.keep} bei dir.`)}
    ${aus('edhrec') ? ausZeile('edhrec', 'Staples zählen nach dem EDHREC-Rang von Scryfall und den schon gemerkten Listen deiner besten Commander; neue Listen lädt die App nicht.') : ''}${aus('cardmarket') ? ausZeile('cardmarket', 'Die Preise „ab“ und der Trend stammen aus dem letzten Stand.') : ''}
    <section class="panel" aria-label="Regeln"><h2>Regeln <small>gelten für die ganze App</small></h2>
      <div class="rules">
        <div class="field"><span>Behalten je Karte</span><div class="stepper" data-rule="keep"><button type="button" data-d="-1" aria-label="weniger">${icon('minus', 'sm')}</button><output class="num">${R.keep}</output><button type="button" data-d="1" aria-label="mehr">${icon('plus', 'sm')}</button></div></div>
        <div class="field"><span>Behalten je Staple ${info('staple', 'Staple')}</span><div class="stepper" data-rule="staples"><button type="button" data-d="-1" aria-label="weniger">${icon('minus', 'sm')}</button><output class="num">${keepS}</output><button type="button" data-d="1" aria-label="mehr">${icon('plus', 'sm')}</button></div></div>
        <div class="field"><label for="min">Einzeln verkaufen ab, darunter Bulk</label><span class="inl"><input type="range" id="min" min="0" max="10" step="0.25" value="${r.min}"><output id="minv" class="minv" for="min"></output></span></div>
        <p class="say" id="say"></p>
      </div>
      <form class="fertige" data-fertig="1"><div class="field"><label for="fertig-namen">Binder, die fertige Decks sind ${info('fertigedecks', 'Fertige Decks')}</label>
        <textarea id="fertig-namen" name="namen" rows="3" placeholder="Ein Binder-Name je Zeile">${esc(fd.namen.join('\n'))}</textarea></div>
        <p class="note-line">Nur für Exporte ohne Typ „deck“. ${kand.length ? `Binder, die noch keine fertigen Decks sind: ${kand.slice(0, 12).map(b => esc(b.name)).join(', ')}${kand.length > 12 ? ' und weitere' : ''}.` : fd.binder.length ? 'Alle Binder im Bestand gelten schon als fertige Decks oder werden von der App geführt.' : 'Noch keine Binder im Bestand.'}</p>
        <button class="btn small" type="submit">Speichern</button></form></section>
    <section class="sec" aria-label="Verkaufsliste">
      <div class="tabs" role="tablist">
        <button role="tab" type="button" data-tab="single" aria-selected="${sellTab === 'single'}">Einzeln verkaufen <span class="count" id="c-single"></span></button>
        <button role="tab" type="button" data-tab="bulk" aria-selected="${sellTab === 'bulk'}">Bulk <span class="count" id="c-bulk"></span></button>
      </div>
      <div class="toolbar"><label class="inl"><input type="checkbox" id="k7lang"${lang ? ' checked' : ''}> Nur Englisch und Deutsch ${info('sprachen', 'Sprachen')}</label>
        ${!lang && r.andere_sprachen ? `<span class="muted small-print">${karten(r.andere_sprachen)} in anderen Sprachen</span>` : ''}</div>
      <div class="toolbar"><div class="sum"><b id="sum-v"></b><span id="rows-info"></span></div><div class="right">
        <button class="btn" type="button" id="buchen" hidden title="${esc(TIP.buchen)}">${icon('check')}<span></span></button>
        ${exp('excel', sellTab, 'Liste für den Ankauf (Excel)', 'sheet', 'primary')}${exp('manabox', sellTab, 'ManaBox-CSV', 'csv')}${exp('text', sellTab, 'Textliste', 'text')}</div></div>
      <div id="conf"></div><div id="rar"></div><div class="rows" id="list"></div>
    </section>
    <section class="sec" aria-label="Preisbewegung"><h2>Preisbewegung <small>${moversSub(pm)}</small></h2>${moversHtml(pm)}</section>
    <div class="split even">
      <section class="sec" aria-label="So verkaufst du"><h2>So verkaufst du</h2><ol class="howto">
        <li><b>Liste exportieren.</b> Die Excel-Liste ist für einen Sammlungsankauf gedacht. Bei einem Ankäufer wie KEEPSEVEN schickst du zuerst das Formular ab und lädst die Liste danach über den Link in der Bestätigungs-Mail hoch (er kauft nur englische und deutsche Karten, dafür gibt es den Haken oben). Einzelne Karten legst du über deren Kartensuche in die Verkaufsliste.</li>
        <li><b>Verkaufte Karten in deiner Scanner-App löschen</b> (zum Beispiel ManaBox). Die App liest die Sammlung aus deren Export, so bleiben Handy und Rechner gleich.</li>
        <li><b>Neuen Export hier ablegen.</b> Was von dieser Liste fehlt, bucht die App als verkauft. Fehlt etwas anderes, zeigt sie es vorher an.</li>
        <li><b>Karten aus Scan-Bindern</b> führt die App selbst: auswählen und „Als verkauft buchen“, ohne Umweg über eine Scanner-App.</li>
      </ol></section>
      <section class="sec" aria-label="Verkauft"><h2>Verkauft ${info('sold', 'Verkauft')}</h2>
        ${sold.jahre.length ? `<div class="facts">${sold.jahre.map(j => `<div><b>${eur0(j.value)}</b><span>${esc(j.jahr)}: ${karten(j.cards)}</span></div>`).join('')}</div><p class="note-line">Meldegrenze der Plattformen ${info('meldegrenze', 'Meldegrenze')}: 30 Verkäufe oder 2.000 € im Jahr.</p>` : ''}
        ${sold.last ? `<p class="lead gap-top">${sold.last.file === 'Verkauf' ? 'Zuletzt gebucht' : 'Beim letzten Import erkannt'}: <b>${karten(sold.last.cards)}, ${eur(sold.last.value)}</b>.${sold.last.file === 'Verkauf' ? ` <button class="link" type="button" id="buchung-weg">zurücknehmen</button>` : ''} Insgesamt bisher ${karten(sold.cards)}, ${eur(sold.value)}.</p>
          <div class="rows">${sold.last.items.slice(0, 8).map(c => `<div class="row" data-oid="${esc(c.oracle_id)}"${peekAt(c.image, c.name, eur(c.price))}>${pic(small(c.image), '', 'thumb')}<div class="min0"><div class="name">${esc(c.name)}</div><div class="sub2">${esc(c.set)}${c.foil !== 'normal' ? ', ' + esc(c.foil) : ''}</div></div><span class="muted">${c.qty}×</span><span class="price">${eur(c.price)}</span></div>`).join('')}</div>`
          : '<p class="muted">Noch nichts. Sobald ein neuer Export Karten von dieser Liste nicht mehr enthält, stehen sie hier.</p>'}
      </section></div>`;
  const say = () => { $('#say').textContent = `Von jeder Karte ${R.keep === 0 ? 'keine' : R.keep === 1 ? 'eine' : R.keep} behalten, von Staples ${keepS}, Standardländer alle. Weitere Kopien ab ${eurMin(r.min)} einzeln, darunter als Bulk.`; };
  const info2 = () => {  // Zähler und Export-Links; die Liste selbst bleibt stehen (Fokus beim Abhaken)
    const g = r[sellTab], mine = g.rows.filter(z => !skip.has(z.id));
    for (const k of ['single', 'bulk']) $('#c-' + k).textContent = `${karten(r[k].cards)}, ${eur(r[k].value)}`;
    $('#minv').textContent = eur(r.min);
    const summe = mine.reduce((n, z) => n + z.qty * z.price, 0);
    zaehlen($('#sum-v'), summe, eur);
    $('#rows-info').textContent = `${karten(mine.reduce((n, z) => n + z.qty, 0))} ausgewählt${sellTab === 'single' && summe ? `, bei Cardmarket nach Provision etwa ${eur(summe * (1 - r.provision))}` : ''}${g.total_rows > g.rows.length ? `. Angezeigt die ersten ${num(g.rows.length)} Zeilen, die Exporte enthalten alle.` : ''}`;
    $('#rows-info').insertAdjacentHTML('beforeend', sellTab === 'single' && summe ? ' ' + info('provision', 'Cardmarket-Provision') : '');
    const scanSel = mine.filter(z => z.scan), bu = $('#buchen');  // Scan-Binder in der Auswahl: hier buchen (Phase 26)
    bu.hidden = !scanSel.length;
    bu.querySelector('span').textContent = `${karten(scanSel.reduce((n, z) => n + z.qty, 0))} als verkauft buchen`;
    bu.onclick = () => buchenDialog(scanSel, mine.length - scanSel.length);
    $$('[data-export]').forEach(a => {
      a.href = `/api/sell.${a.dataset.export === 'text' ? 'txt' : 'csv'}?` + new URLSearchParams({group: sellTab, format: a.dataset.export, ...(lang ? {lang} : {}), ...(skip.size ? {skip: [...skip].join(',')} : {})});
      a.download = `${sellTab === 'bulk' ? 'bulk' : 'verkaufen'}-${new Date().toISOString().slice(0, 10)}.${a.dataset.export === 'text' ? 'txt' : 'csv'}`;
    });
  };
  const list = () => {
    const g = r[sellTab];
    $('#rar').innerHTML = sellTab !== 'bulk' ? '' : `<p class="lead">${esc(TIP.bulk)} Ankäufer zählen meist nach Seltenheit:</p>`
      + (g.rarity.length ? `<div class="rar">${g.rarity.map(x => `<div><span>${esc(RARITY[x.rarity])}</span><b>${num(x.cards)}</b><span>${eur(x.value)}</span></div>`).join('')}</div>` : '')
      + (g.k7.cards ? `<p class="note-line">Beispiel nach der Preisliste von KEEPSEVEN (Stand 8.10.2026): etwa <b>${eur(g.k7.value)}</b> ${info('k7bulk', 'Bulk-Preise KEEPSEVEN')}${g.k7.ohne ? `, ${karten(g.k7.ohne)} kauft KEEPSEVEN nicht (Tokens oder andere Sprachen)` : ''}. Den Versand übernimmt KEEPSEVEN ab ${eur0(g.k7.frei_ab)} Ankaufswert${g.k7.value < g.k7.frei_ab ? ', darunter zahlst du ihn' : ''}.</p>` : '');
    const conf = g.rows.filter(z => z.want?.length);  // Konfliktkarten: stehen auf den Listen von mindestens zwei Top-Commandern
    $('#conf').innerHTML = conf.length ? `<div class="note warn"><span class="ic">${icon('alert')}</span><div><b>${karten(conf.reduce((n, z) => n + z.qty, 0))} in dieser Liste stehen auf den Listen von mindestens zwei deiner besten Commander ${info('want', 'Konfliktkarten')}</b>
      <div class="muted">Eine Kopie reicht nur für ein Deck. Willst du mehrere Decks bauen, behalte sie.</div></div><button class="btn small" type="button" id="unconf">Abwählen</button></div>` : '';
    if (conf.length) $('#unconf').onclick = () => { conf.forEach(z => skip.add(z.id)); saveSkip(); list(); };
    $('#list').innerHTML = g.rows.map(z => `<div class="srow${skip.has(z.id) ? ' off' : ''}"><input type="checkbox" data-id="${esc(z.id)}"${skip.has(z.id) ? '' : ' checked'} aria-label="${esc(z.name)} verkaufen">
      ${pic(small(z.image), '', 'thumb')}<div class="who" data-oid="${esc(z.oracle_id)}"${peekAt(z.image, z.name, eur(z.price))}><div class="name">${esc(z.name)}</div><div class="sub2">${esc(z.set)} #${esc(z.number)}, ${esc(LANG[z.language] || z.language)}, ${esc(COND[z.condition] || z.condition)}${z.foil !== 'normal' ? ', ' + esc(z.foil) : ''}, ${esc(z.binder)}</div>${z.want?.length || z.reserved || z.reprint?.length ? `<div class="chips">${z.want?.length ? `<span class="chip warn" title="${esc(z.want.join(', '))}">gefragt in ${z.want.length} Top-Decks</span>` : ''}${z.reserved ? `<span class="chip" title="${esc(TIP.reserved)}">Reserved List</span>` : ''}${z.reprint?.length ? `<span class="chip warn" title="${esc(TIP.reprint)}">Reprint: ${esc(z.reprint[0])}</span>` : ''}</div>` : ''}</div>
      <div class="num muted">${z.qty}×</div><div class="price">${eur(z.price)}${z.cm_low != null ? `<div class="sub2">ab ${eur(z.cm_low)}</div>` : ''}</div></div>`).join('') || `<div class="empty">${sellTab === 'single' ? `Nichts ab ${eur(r.min)}. Schieb den Regler nach links, dann landet mehr in dieser Liste.` : 'Kein Bulk bei diesem Mindestpreis.'}</div>`;
    info2();
  };
  $('#k7lang').onchange = e => { try { localStorage.setItem('mtg-sell-lang', e.target.checked ? 'en,de' : ''); } catch { /* privates Fenster */ } render(true); };
  $('#list').onchange = e => { const id = e.target.dataset.id; e.target.checked ? skip.delete(id) : skip.add(id); e.target.closest('.srow').classList.toggle('off', !e.target.checked); saveSkip(); info2(); };
  $('.tabs').onclick = e => { const b = e.target.closest('[data-tab]'); if (!b) return; sellTab = b.dataset.tab; $$('.tabs [data-tab]').forEach(x => x.setAttribute('aria-selected', x === b)); list(); };
  $('#min').oninput = e => { r.min = +e.target.value; say(); $('#minv').textContent = eur(r.min); };
  $('#min').onchange = async e => {  // beim Loslassen speichern: gilt dann auch für Übersicht und Sortieren
    try { await post('settings', {sell_min: +e.target.value}); render(true); } catch (err) { flash('Fehler: ' + err.message); }
  };
  $$('.stepper').forEach(st => st.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return;
    const k = st.dataset.rule, cur = k === 'keep' ? R.keep : keepS, val = Math.max(0, Math.min(4, cur + +b.dataset.d));
    try { await post('settings', k === 'keep' ? {keep: val, staples: Math.max(val, R.staples)} : {staples: val}); render(true); } catch (err) { flash('Fehler: ' + err.message); }
  });
  const weg = $('#buchung-weg');
  if (weg) weg.onclick = async () => {
    if (!confirm(`Die letzte Buchung zurücknehmen? ${karten(sold.last.cards)} kommen in ihre Scan-Binder zurück.`)) return;
    try { await post('verkauft-zurueck', {import_id: sold.last.import_id}); flash('Buchung zurückgenommen'); render(true); } catch (e) { flash('Fehler: ' + e.message); }
  };
  say(); list();
}
async function fertigForm(f) {
  const namen = f.elements.namen.value.split('\n').map(x => x.trim()).filter(Boolean);
  try { await post('fertige-decks', {namen}); flash('Fertige Decks gespeichert'); render(true); } catch (e) { flash('Fehler: ' + e.message); }
}
let buchenZeilen = [];
function buchenDialog(zeilen, andere) {
  buchenZeilen = zeilen;
  const n = zeilen.reduce((s, z) => s + z.qty, 0), wert = zeilen.reduce((s, z) => s + z.qty * z.price, 0);
  dlg.className = 'modal';
  dlg.innerHTML = `<button class="x" data-close aria-label="Schließen">${icon('x')}</button><div class="box"><h2 id="dlg-title">Als verkauft buchen</h2>
    <p class="muted">${karten(n)} aus Scan-Bindern, Trendwert ${eur(wert)}. Die App nimmt sie aus dem Bestand und zählt sie bei den Verkäufen.${andere ? ` ${plural(andere, 'Zeile', 'Zeilen')} der Auswahl stammen aus ManaBox: Die löschst du in ManaBox, der nächste Import bucht sie.` : ''}</p>
    <form class="kform" data-buchen="1"><div class="field"><label for="b-erloes">Was du insgesamt bekommen hast, in Euro (leer: Trendpreise)</label><input id="b-erloes" name="erloes" type="number" min="0" step="0.01"></div>
      <div class="actions"><button class="btn ghost" type="button" data-close>Abbrechen</button><button class="btn primary" type="submit">${icon('check')}Buchen</button></div></form></div>`;
  showDlg();
  $('#b-erloes').focus();
}
async function buchenForm(f) {
  const erloes = f.elements.erloes.value;
  try {
    const r = await post('verkauft', {zeilen: buchenZeilen.map(z => ({key: [z.binder, z.scryfall_id, z.foil, z.condition, z.language], qty: z.qty})), erloes: erloes === '' ? null : +erloes});
    buchenZeilen.forEach(z => skip.delete(z.id)); saveSkip();
    dlg.close(); flash(`Gebucht: ${karten(r.karten)}, ${eur(r.wert)}`); render(true);
  } catch (e) { if (!(e instanceof LoginNoetig)) flash('Fehler: ' + e.message); }
}

// --- Decks: fertige und gebaute Decks, Commander-Ranking, mehrere Decks planen, Deckbau ---------------------------
const deckTile = d => {
  const fertig = d.kind === 'fertig', c = d.commander;
  const href = fertig ? `#/decks?binder=${encodeURIComponent(d.binder)}` : `#/decks?id=${d.id}`;
  return `<a class="deck" href="${href}">${artImg(c) || '<span class="noimg">kein Commander</span>'}
  <div class="body"><div class="trow"><span class="t">${esc(d.name)}</span><span class="v">${eur0(d.value)}</span></div>
  <div class="m">${pips(fertig ? d.ci : c?.ci)}<span class="tag">${fertig ? 'fertig' : 'gebaut'}</span>${fertig ? '' : `Bracket ${d.bracket},`} ${karten(d.cards)}</div>
  ${fertig ? `<div class="m">${c ? esc(c.name) : 'Commander noch wählen'}</div>` : ''}${credit(c)}</div></a>`;
};
// die drei besten Commander groß: Art, Abdeckung als große Zahl, Kennzahlen, Bauen
const featCard = (r, i) => `<article class="fc">
  <a class="art" href="#" data-oid="${esc(r.oracle_id)}"${peekAt(r.image, r.name, eur(r.price))} aria-label="${esc(r.name)} ansehen">${artImg(r) || '<span class="noimg"></span>'}</a>
  <div class="body"><div class="who" data-oid="${esc(r.oracle_id)}"><span class="name">${esc(r.name)}</span>${pips(r.ci)}${r.themes?.length ? `<span class="sub2">${esc(r.themes.join(' · '))}</span>` : ''}</div>
    <div class="cov2"><b>${Math.round(r.coverage * 100)} %</b><span>Abdeckung ${info('coverage', 'Abdeckung')}</span></div>
    <dl><div><dt>Karten ${info('have', 'Karten')}</dt><dd>${r.have} / ${r.total}</dd></div><div><dt>EDHREC-Decks ${info('decks', 'EDHREC-Decks')}</dt><dd>${num(r.decks)}</dd></div>
      ${r.buy != null ? `<div><dt>Zukauf ${info('buy', 'Zukauf')}</dt><dd>${r.buy_n ? eur(r.buy) : 'nichts'}</dd></div>` : `<div><dt>Preis ${info('cmdprice', 'Preis')}</dt><dd>${eur(r.price)}</dd></div>`}</dl>
    <div class="foot">${credit(r) || '<span></span>'}<a class="btn${i ? '' : ' primary'}" href="#/decks?build=${esc(r.oracle_id)}">Bauen</a></div></div></article>`;
const MODES = [['machbar', 'Machbar'], ['beliebt', 'Beliebt'], ['geheimtipp', 'Geheimtipp'], ['guenstig', 'Günstig']];
const MODE_TEXT = {
  machbar: 'Wie viel der EDHREC-Empfehlungen du schon frei hast, die vollständigsten zuerst.',
  beliebt: 'Die meistgespielten Commander, von denen du mindestens ein Fünftel der empfohlenen Karten frei hast.',
  geheimtipp: 'Gut machbar, aber nur wenige spielen ihn: höchstens so viele EDHREC-Decks wie der mittlere deiner Commander.',
  guenstig: 'Die zwölf machbarsten Commander, sortiert nach dem Preis der zehn wichtigsten Karten, die dir noch fehlen. Beim ersten Mal holt die App die Preise von Scryfall, das dauert gut zehn Sekunden.',
};
let rankMode = 'machbar', rankMin = null;
const rankControls = cm => `<div class="toolbar"><div class="seg" role="group" aria-label="Sortierung des Rankings">${MODES.map(([k, l]) => `<button type="button" class="btn small" data-mode="${k}" aria-pressed="${cm.mode === k}">${l}</button>`).join('')}</div>
  <label class="inl">EDHREC-Decks mindestens <select id="rmin">${[0, 30, 100, 500].map(n => `<option value="${n}"${cm.min_decks === n ? ' selected' : ''}>${n ? num(n) : 'egal'}</option>`).join('')}</select></label>${info('modes', 'Sortierung')}</div>
  <p class="lead">${esc(MODE_TEXT[cm.mode])}</p>`;
const rankRow = (r, buy) => `<div class="rrow">${pic(small(r.image), '', 'thumb')}
  <div class="who" data-oid="${esc(r.oracle_id)}"${peekAt(r.image, r.name, eur(r.price))}><div class="name">${esc(r.name)}</div><div class="sub2">${pips(r.ci)}${r.themes?.length ? ` ${esc(r.themes.join(' · '))}` : ''}</div></div>
  <div class="cov" title="${r.have} von ${r.total} empfohlenen Karten hast du frei"><span class="track"><span style="--w:${(r.coverage * 100).toFixed(1)}%"></span></span><span class="num">${Math.round(r.coverage * 100)} %</span></div>
  <div class="ink2 hide-s r">${r.have} / ${r.total}</div><div class="ink2 hide-s r">${num(r.decks)}</div><div class="ink2 hide-s r">${buy ? (r.buy_n ? eur(r.buy) : 'nichts') : r.price != null ? eur(r.price) : ''}</div>
  <a class="btn small" href="#/decks?build=${esc(r.oracle_id)}">Bauen</a></div>`;
let rankAll = false;

async function viewDecks(p) {
  if (p.get('id') && p.get('pick')) return showPick(await api(`pick?id=${p.get('id')}&order=${p.get('order') || 'set'}`), p.get('order') || 'set');
  if (p.get('zerlegen')) return showZerlegen(await api('zerlegen?' + (p.get('id') ? 'id=' + p.get('id') : 'binder=' + encodeURIComponent(p.get('binder') || ''))), p);
  if (p.get('id')) return showDeck(await api('deck/' + p.get('id')), null);
  if (p.get('binder')) return showBinderDeck(await api('binder-deck?name=' + encodeURIComponent(p.get('binder'))));
  if (p.get('build')) {
    const bracket = +p.get('bracket') || 3, theme = p.get('theme') || 'auto';
    main.innerHTML = `${head('Deck wird gebaut', 'EDHREC-Listen zum Commander und seinen Themen sowie Preise werden zusammengetragen.')}${skeleton()}`;
    let deck;
    try { deck = await post('build', {commander: p.get('build'), bracket, theme}); }
    catch (e) {
      if (!e.quelle) throw e;  // abgeschaltet: kein Fehler, ein Hinweis
      main.innerHTML = `${head('Deck bauen', 'Der Deckbau stützt sich auf die Listen von EDHREC.', `<a class="btn ghost" href="#/decks">${icon('left')}Decks</a>`)}<div class="todo">${ausNote(e.quelle, 'Zu diesem Commander gibt es noch keine gemerkten Daten, und neue lädt die App nicht. Einen Deckbau ohne EDHREC gibt es nicht.')}</div>`;
      return;
    }
    return showDeck(deck, p.get('build'), theme);
  }
  const [dl, cm] = await Promise.all([api('decks'), api('commanders?' + new URLSearchParams({mode: rankMode, ...(rankMin != null ? {min_decks: rankMin} : {})}))]);
  const alle = [...dl.fertig, ...dl.items.map(d => ({...d, kind: 'gebaut'}))];
  const items = rankAll ? cm.items : cm.items.slice(0, 30), top = items.slice(0, 3), rest = items.slice(3), buy = cm.mode === 'guenstig';
  main.innerHTML = `${head('Decks', `Fertige Decks lädst du als Textliste hoch oder scannst sie ein, neue baut die App aus deinen freien Karten ${info('free', 'frei')}. Bestehende Decks werden dabei nie auseinandergenommen.`,
    `<a class="btn" href="#/scan?modus=erfassen&deck=1">${icon('cards')}Deck einscannen</a>`)}
    <section class="sec" aria-label="Deine Decks"><h2>Deine Decks <small>${alle.length ? `${dl.fertig.length} fertig, ${dl.items.length} gebaut` : ''}</small></h2>
      ${alle.length ? `<div class="decks">${alle.map(deckTile).join('')}</div>` : '<p class="muted">Noch keine Decks. Lade ein fertiges Deck hoch (als Text, zum Beispiel aus ManaBox oder Moxfield) oder bau unten eins aus dem Ranking.</p>'}</section>
    <section class="sec" aria-label="Commander-Ranking"><h2>Welche Commander passen zu deiner Sammlung? ${cm.all ? `<small>${cm.total === cm.all ? `${num(cm.all)} Kandidaten` : `${num(cm.total)} von ${num(cm.all)} Kandidaten`}</small>` : ''}</h2>
      ${aus('edhrec') ? (cm.all ? ausZeile('edhrec', 'Das Ranking zeigt die gemerkten Daten, neue lädt die App nicht.') : ausNote('edhrec', 'Ohne EDHREC gibt es kein Commander-Ranking und keinen Deckbau. Auf der Seite „Quellen“ siehst du, was EDHREC erfährt, und kannst es einschalten.'))
      : cm.pending || !cm.tags ? note(['cloud', cm.all ? `Für ${num(cm.pending)} Commander fehlen noch Daten` : 'Commander-Daten laden',
        'Die App fragt EDHREC einmal pro Sekunde nach den empfohlenen Karten jedes Commanders, den du besitzt. Das dauert ein paar Minuten, du kannst währenddessen weiterarbeiten.',
        `<button class="btn primary" type="button" data-job="commanders">${icon('cloud')}Jetzt laden</button>`, 'commanders']) : ''}
      <p class="lead">Lieber selbst wählen? <a href="#/cards?q=${encodeURIComponent('is:commander')}">Alle möglichen Commander deiner Sammlung</a>, Karte antippen, dann „Deck um diesen Commander bauen“.</p>
      ${cm.all ? rankControls(cm) : ''}
      ${cm.items.length ? `<div class="feat n${top.length}">${top.map(featCard).join('')}</div>
        ${rest.length ? `<div class="rtable"><div class="rrow headrow"><span></span><span>Weitere Commander</span><span>Abdeckung ${info('coverage', 'Abdeckung')}</span><span class="hide-s r">Karten ${info('have', 'Karten')}</span>
          <span class="hide-s r">EDHREC-Decks ${info('decks', 'EDHREC-Decks')}</span><span class="hide-s r">${buy ? `Zukauf ${info('buy', 'Zukauf')}` : `Preis ${info('cmdprice', 'Preis')}`}</span><span class="r">${info('build', 'Bauen')}</span></div>
          ${rest.map(r => rankRow(r, buy)).join('')}</div>` : ''}
        ${cm.items.length > items.length ? `<div class="pager"><button class="btn" type="button" id="rank-all">Alle ${num(cm.items.length)} zeigen</button></div>` : ''}`
        : cm.pending ? '' : cm.all ? '<p class="muted">Kein Commander passt zu dieser Auswahl. Stell „EDHREC-Decks mindestens“ niedriger oder wähle eine andere Sortierung.</p>'
        : '<p class="muted">Keine legendären Kreaturen in deiner Sammlung gefunden.</p>'}
    </section>
    ${aus('edhrec') && !cm.all ? `<section class="sec" aria-label="Was dir fehlt"><h2>Was dir für deine besten Commander fehlt</h2>${ausZeile('edhrec', 'Die Lücken auf den Listen deiner besten Commander brauchen seine Daten.')}</section>` : ''}
    ${cm.all ? `<section class="sec" aria-label="Was dir fehlt"><h2>Was dir für deine besten Commander fehlt</h2>
      <p class="lead">Karten, die auf den Listen mehrerer deiner zehn besten Commander stehen und die du nicht frei hast. Eine davon hilft gleich mehreren Decks.</p>
      <div id="gaps"><p class="muted">Preise werden geladen …</p></div></section>` : ''}
    ${cm.all ? `<section class="sec" aria-label="Mehrere Decks auf einmal"><h2>Mehrere Decks auf einmal</h2>
      <p class="lead">Baut nacheinander die besten Commander und verplant jede Karte nur einmal. So siehst du, welche Decks du gleichzeitig aus deiner Sammlung bauen kannst.</p>
      <div class="toolbar"><label class="inl">Anzahl <select id="pcount">${[2, 3, 4, 5].map(n => `<option${n === 3 ? ' selected' : ''}>${n}</option>`).join('')}</select></label>
        <label class="inl">Bracket ${info('bracket', 'Bracket')} <select id="pbr">${[1, 2, 3, 4, 5].map(b => `<option${b === 3 ? ' selected' : ''}>${b}</option>`).join('')}</select></label>
        <button class="btn" type="button" id="pgo">Planen</button></div><div id="presult"></div></section>` : ''}
    <section class="sec" aria-label="Combos in deiner Sammlung" id="combos"><h2>Combos in deiner Sammlung ${info('combos', 'Combos in deiner Sammlung')}</h2><p class="muted">Wird geladen …</p></section>
    <section class="sec" aria-label="Bracket prüfen"><h2>Bracket einer Deckliste prüfen ${info('bracketcheck', 'Bracket prüfen')}</h2>
      <p class="lead">Füg die Liste eines Decks ein, zum Beispiel aus Moxfield, Archidekt oder ManaBox. Die App sagt, ab welchem Bracket es mindestens passt, und nennt die Gründe. Das hilft vor dem Spiel.</p>
      <div class="field"><label for="bracket-text">Deckliste</label><textarea id="bracket-text" spellcheck="false" placeholder="Commander&#10;1 Atraxa, Praetors' Voice&#10;&#10;Deck&#10;1 Sol Ring"></textarea></div>
      <div class="actions gap-top"><span class="left muted">${aus('spellbook') ? `${esc(QNAME.spellbook)} ist abgeschaltet, deshalb geht das nicht. <a href="#/quellen">Zur Seite Quellen</a>` : 'Die Liste geht dafür an Commander Spellbook.'}</span><button class="btn" type="button" id="bracket-go"${aus('spellbook') ? ' disabled' : ''}>${icon('check')}Prüfen</button></div></section>`;
  const all = $('#rank-all');
  if (all) all.onclick = () => { rankAll = true; render(true); };
  $$('[data-mode]').forEach(b => b.onclick = () => { rankMode = b.dataset.mode; rankMin = null; render(true); });
  const mn = $('#rmin');
  if (mn) mn.onchange = () => { rankMin = +mn.value; render(true); };
  $('#bracket-go').onclick = () => openBracket($('#bracket-text').value);
  const gp = $('#gaps');
  const gapList = (g, all) => g.items.length ? `<div class="rows">${(all ? g.items : g.items.slice(0, 10)).map(u => `<div class="row" data-oid="${esc(u.oracle_id)}"${peekAt(u.image, u.name, eur(u.price))} title="${esc(u.commanders.join(', '))}">${pic(small(u.image), '', 'thumb')}
      <div class="min0"><div class="name">${esc(u.name)}</div><div class="sub2">fehlt bei ${u.n} von ${g.commanders.length} Top-Commandern${u.gc ? ', Game Changer' : ''}</div></div><div></div><div class="price">${eur(u.price)}</div></div>`).join('')}</div>
    ${!all && g.items.length > 10 ? `<div class="pager"><button class="btn" type="button" id="gaps-all">Alle ${g.items.length} zeigen</button></div>` : ''}` : '<p class="muted">Nichts, was auf mehreren Listen fehlt.</p>';
  if (gp) api('gaps').then(g => {
    gp.innerHTML = gapList(g, false);
    const more = $('#gaps-all');
    if (more) more.onclick = () => { gp.innerHTML = gapList(g, true); };
  }).catch(e => { gp.innerHTML = ladeFehler(e); });
  combosUi();
  const go = $('#pgo');
  if (go) go.onclick = async () => {
    const body = {count: +$('#pcount').value, bracket: +$('#pbr').value};
    go.disabled = true; $('#presult').innerHTML = '<div class="progress busy"><span></span></div><p class="muted">Plane Decks …</p>';
    try {
      const r = await post('plan-decks', body);
      $('#presult').innerHTML = r.items.length ? `<div class="decks list">${r.items.map(d => `<a class="deck" href="#/decks?build=${esc(d.commander.oracle_id)}&bracket=${d.bracket}&theme=${encodeURIComponent(d.theme?.slug || 'none')}">
          ${artImg(d.commander) || '<span class="noimg"></span>'}<div class="body"><div class="trow"><span class="t">${esc(d.commander.name)}</span><span class="v">${eur0(d.value)}</span></div>
          <div class="m">${pips(d.commander.ci)}${d.theme?.name ? `Thema ${esc(d.theme.name)}, ` : ''}Abdeckung ${Math.round(d.coverage * 100)} %, ${d.warnings.length ? esc(d.warnings[0]) : 'Quoten erfüllt'}</div></div></a>`).join('')}</div>
        <div class="actions gap-top"><span class="left muted">Diese ${r.items.length} Decks kannst du gleichzeitig bauen. Noch ist nichts reserviert.</span><button class="btn primary" type="button" id="psave">Alle speichern</button></div>`
        : '<p class="muted">Kein Deck möglich, es fehlen Commander-Daten.</p>';
      const sv = $('#psave');
      if (sv) sv.onclick = async () => { sv.disabled = true; try { await post('plan-decks', {...body, save: true}); flash(`${r.items.length} Decks gespeichert`); render(true); } catch (e) { flash('Fehler: ' + e.message); sv.disabled = false; } };
    } catch (e) { $('#presult').innerHTML = e.quelle ? ausZeile(e.quelle, 'Deshalb lässt sich nichts planen.') : `<p class="muted">Fehler: ${esc(e.message)}</p>`; }
    go.disabled = false;
  };
  jobsUi();
}

// Combos der ganzen Sammlung (Phase 18): Spellbook als Hintergrund-Job, Ergebnis 30 Tage gespeichert
const comboLi = c => `<li><a href="https://commanderspellbook.com/combo/${encodeURIComponent(c.id)}/" target="_blank" rel="noopener noreferrer">${esc(c.cards.join(' + '))}<span class="sr-only"> (Commander Spellbook, neues Fenster)</span></a>${c.result ? `: ${esc(c.result)}` : ''}
  ${c.fehlt?.length ? `<span class="chip warn">fehlt: ${esc(c.fehlt.join(', '))}</span>` : ''} <span class="muted small-print">${pips(c.identity)} ${esc(c.tag || '')}</span></li>`;
async function combosUi(alle) {
  const box = $('#combos');
  if (!box) return;
  const h2 = `<h2>Combos in deiner Sammlung ${info('combos', 'Combos in deiner Sammlung')}`;
  try {
    const r = await api('combos');
    if (!r.at && aus('spellbook')) {
      box.innerHTML = `${h2}</h2><div class="todo">${ausNote('spellbook', 'Ohne Commander Spellbook gibt es keine Combos in deiner Sammlung.')}</div>`;
      return;
    }
    if (!r.at) {
      box.innerHTML = `${h2}</h2>${note(['infinity', 'Combos suchen', 'Die App fragt Commander Spellbook, welche Combos du schon komplett besitzt und bei welchen eine Karte fehlt. Beim ersten Mal lädt sie die Liste aller Combo-Karten, das dauert gut eine Minute.', `<button class="btn" type="button" data-job="combos">${icon('infinity')}Combos suchen</button>`, 'combos'])}`;
      return jobsUi();
    }
    const zeig = (l, n) => alle ? l : l.slice(0, n);
    box.innerHTML = `${h2}<small>Stand ${day(r.at)}, ${num(r.karten)} deiner Karten kommen in Combos vor</small>${aus('spellbook') ? '' : `<button class="link more" type="button" data-job="combos">${icon('refresh', 'sm')}neu suchen</button>`}</h2>${aus('spellbook') ? ausZeile('spellbook', 'Gezeigt wird der letzte Stand.') : ''}<div data-jobbox="combos"></div>
      ${r.abgeschnitten ? `<p class="note-line">Bei einer Farbkombination waren es mehr als 600 Karten, die ${num(r.abgeschnitten)} mit den wenigsten Combos fehlen.</p>` : ''}
      <div class="split even"><div><h3>Komplett in deiner Sammlung <small>${num(r.fertig.length)}</small></h3>${r.fertig.length ? `<ul class="combos">${zeig(r.fertig, 12).map(comboLi).join('')}</ul>` : '<p class="muted">Keine.</p>'}</div>
        <div><h3>Eine Karte fehlt <small>${num(r.fast.length)}</small></h3>${r.fast.length ? `<ul class="combos">${zeig(r.fast, 12).map(comboLi).join('')}</ul>` : '<p class="muted">Keine.</p>'}</div></div>
      ${!alle && (r.fertig.length > 12 || r.fast.length > 12) ? '<div class="pager"><button class="btn" type="button" id="combos-alle">Alle zeigen</button></div>' : ''}`;
    const b = $('#combos-alle');
    if (b) b.onclick = () => combosUi(true);
    jobsUi();
  } catch (e) { if (!(e instanceof LoginNoetig)) box.innerHTML = `${h2}</h2>${ladeFehler(e)}`; }
}

// Karten eines Decks (Phase 15): Bilder, Stapel oder Liste, gruppiert nach Rolle, Kartentyp oder Manawert; die Wahl merkt sich der Browser
const DVIEW = [['bilder', 'Bilder'], ['stapel', 'Stapel'], ['liste', 'Liste']], DGROUP = [['rolle', 'Rolle'], ['typ', 'Kartentyp'], ['mv', 'Manawert']];
const merk = (k, d, ok) => { try { const v = localStorage.getItem(k); return ok.some(([x]) => x === v) ? v : d; } catch { return d; } };
const merke = (k, v) => { try { localStorage.setItem(k, v); } catch { /* privates Fenster: gilt bis zum Neuladen */ } };
const TYPEN = [['Land', 'Länder'], ['Creature', 'Kreaturen'], ['Planeswalker', 'Planeswalker'], ['Battle', 'Schlachten'], ['Instant', 'Spontanzauber'], ['Sorcery', 'Hexereien'], ['Artifact', 'Artefakte'], ['Enchantment', 'Verzauberungen']];
const TYP_FOLGE = ['Kreaturen', 'Planeswalker', 'Schlachten', 'Spontanzauber', 'Hexereien', 'Artefakte', 'Verzauberungen', 'Sonstige', 'Länder'];
let aktDeck = null;
function gruppen(d, by) {
  if (by === 'rolle') return d.groups.filter(g => g.role !== 'commander').map(g => g.role === 'basic' ? {...g, label: 'Standardländer'} : g);
  const je = {};
  for (const c of d.cards.filter(c => c.role !== 'commander')) {
    const typ = (c.type || '').split(' // ')[0];
    const k = by === 'typ' ? (TYPEN.find(([t]) => typ.includes(t)) || [, 'Sonstige'])[1]
      : /Land/.test(typ) ? 'Länder' : (c.cmc || 0) >= 6 ? 'Manawert 6 und mehr' : `Manawert ${Math.floor(c.cmc || 0)}`;
    (je[k] ||= []).push(c);
  }
  const folge = by === 'typ' ? TYP_FOLGE : [0, 1, 2, 3, 4, 5].map(i => `Manawert ${i}`).concat('Manawert 6 und mehr', 'Länder');
  return folge.filter(k => je[k]).map(k => ({label: k, role: k, count: je[k].reduce((n, c) => n + c.qty, 0),
    cards: je[k].sort((a, b) => (a.cmc || 0) - (b.cmc || 0) || a.name.localeCompare(b.name))}));
}
const deckPeek = x => peekAt(x.image, x.name, `${x.price != null && x.role !== 'basic' ? eur(x.price) : ''}${x.qty > 1 ? ` · ${x.qty}×` : ''}`);
const bilderHtml = gs => gs.map(g => `<div class="group"><h2>${esc(g.label)} <small>${g.count}</small></h2>${g.role === 'basic'
  ? `<div class="chips big">${g.cards.map(x => `<span class="chip">${esc(x.name)} ×${x.qty}</span>`).join('')}</div>`
  : `<div class="grid small">${g.cards.map(x => `<a class="card" href="#" data-oid="${esc(x.oracle_id)}"${deckPeek(x)}>${pic(x.image, x.name)}
    <span class="cap"><span class="p">${x.price != null && x.role !== 'basic' ? eur(x.price) : ''}</span>${x.qty > 1 ? `<span class="q">×${x.qty}</span>` : ''}</span></a>`).join('')}</div>`}</div>`).join('');
// Stapel wie auf dem Tisch: Karten überlappen, sichtbar bleibt die Titelzeile; Mehrfache liegen bis zu viermal übereinander
const stapelHtml = gs => `<div class="piles">${gs.map(g => `<div class="pile"><h3>${esc(g.label)} <small>${g.count}</small></h3><div class="pcards">${g.cards.flatMap(x => Array(Math.min(x.qty, 4)).fill(x))
  .map(x => `<a class="pc" href="#" data-oid="${esc(x.oracle_id)}" aria-label="${esc(x.name)}${x.qty > 1 ? `, ${x.qty}×` : ''}"${deckPeek(x)}>${pic(x.image, x.name)}</a>`).join('')}</div></div>`).join('')}</div>`;
const listeHtml = gs => `<div class="dlist">${gs.map(g => `<div class="group"><h3>${esc(g.label)} <small>${g.count}</small></h3><table class="tbl dl">${g.cards.map(x => `
  <tr data-oid="${esc(x.oracle_id)}"${deckPeek(x)}><td class="num">${x.qty}</td><td class="nm">${esc(x.name)}</td><td>${x.mana_cost ? mana(x.mana_cost) : ''}</td>
  <td class="rt">${x.price != null && x.role !== 'basic' ? eur(x.price) : ''}</td></tr>`).join('')}</table></div>`).join('')}</div>`;
function deckKarten(d) {
  aktDeck = d;
  const view = merk('mtg-deckview', 'bilder', DVIEW), by = merk('mtg-deckgroup', 'rolle', DGROUP), gs = gruppen(d, by);
  return `<section class="sec" aria-label="Karten im Deck" id="deckkarten"><div class="toolbar noprint">
    <div class="seg" role="group" aria-label="Ansicht">${DVIEW.map(([k, l]) => `<button type="button" class="btn small" data-dview="${k}" aria-pressed="${view === k}">${l}</button>`).join('')}</div>
    <label class="inl">Gruppiert nach <select id="dgroup">${DGROUP.map(([k, l]) => `<option value="${k}"${by === k ? ' selected' : ''}>${l}</option>`).join('')}</select></label></div>
    ${view === 'liste' ? listeHtml(gs) : view === 'stapel' ? stapelHtml(gs) : bilderHtml(gs)}</section>`;
}
const deckNeu = () => { const alt = $('#deckkarten'); if (alt && aktDeck) alt.outerHTML = deckKarten(aktDeck); };

// Starthand: exakte Wahrscheinlichkeiten vom Server, dazu eine Hand zum Ausprobieren (Mulligan, nächste Karte)
const pct = x => x == null ? 'keine' : `${Math.round(x * 100)} %`;
function handHtml(d) {
  const h = d.stats?.hand;
  if (!h || !h.n) return '';
  return `<section class="sec" aria-label="Starthand"><h2>Starthand ${info('hand', 'Starthand')} <small>${karten(h.n)}, davon ${h.lands} Länder</small></h2>
    ${facts([[pct(h.spielbar), 'spielbare Starthand', 'spielbar'], [pct(h.land3), 'drei Länder bis Zug 3', 'land3'], [h.ramp2 == null ? 'keine' : pct(h.ramp2), 'Ramp bis Zug 2', 'ramp2'], [fmt(h.lands_hand, 1), 'Länder auf der Hand im Schnitt']])}
    <div class="toolbar gap-top noprint"><button class="btn" type="button" id="h-neu">${icon('cards')}Starthand ziehen</button><button class="btn" type="button" id="h-mull" disabled>Mulligan</button>
      <button class="btn" type="button" id="h-zieh" disabled>Nächste Karte</button><span class="muted" id="h-info" aria-live="polite"></span></div>
    <div class="grid small hand" id="hand"></div></section>`;
}
function handUi(d) {
  const neu = $('#h-neu');
  if (!neu) return;
  const stapel = d.cards.filter(c => c.role !== 'commander').flatMap(c => Array(c.qty).fill(c));
  let deck = [], pos = 0, mull = 0;
  const misch = () => { deck = stapel.slice(); for (let i = deck.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [deck[i], deck[j]] = [deck[j], deck[i]]; } pos = 7; };
  const zeig = () => {
    const hand = deck.slice(0, pos), lands = hand.filter(c => c.role === 'land' || c.role === 'basic').length;
    $('#hand').innerHTML = hand.map(x => `<a class="card" href="#" data-oid="${esc(x.oracle_id)}"${deckPeek(x)}>${pic(x.image, x.name)}</a>`).join('');
    $('#h-info').textContent = `${lands} ${lands === 1 ? 'Land' : 'Länder'} unter ${pos} Karten${pos > 7 ? `, Zug ${pos - 6}` : ''}${mull ? `, ${mull}. Mulligan` : ''}`;
    $('#h-mull').disabled = false; $('#h-zieh').disabled = pos >= deck.length;
  };
  neu.onclick = () => { mull = 0; misch(); zeig(); };
  $('#h-mull').onclick = () => { mull++; misch(); zeig(); };
  $('#h-zieh').onclick = () => { pos++; zeig(); };
}

// Verbessern: Upgrade-Leiter vom Server (frei, bis 1 €, bis 5 €), je „rein X, raus Y“
const improveSec = q => `<section class="sec" aria-label="Verbessern" id="improve" data-q="${esc(q)}"><h2>Verbessern ${info('improve', 'Verbessern')}</h2><p class="muted">Vorschläge werden geladen …</p></section>`;
// Recherche-Dossier (Phase 23): schreibt Claude Code mit dem Skill mtg-recherche; der Server liefert es als escaptes HTML
const dossierSec = name => name ? `<section class="sec dossier" id="dossier" data-name="${esc(name)}" hidden aria-label="Dossier"></section>` : '';
async function dossierUi() {
  const box = $('#dossier');
  if (!box) return;
  try {
    const r = await api('dossier?name=' + encodeURIComponent(box.dataset.name));
    if (!r.html || !box.isConnected) return;
    box.innerHTML = `<h2>Dossier ${info('dossier', 'Dossier')}</h2><div class="dtext">${r.html}</div>`;  // r.html ist serverseitig escapt (deckbuild.dossier_html)
    box.hidden = false;
  } catch { /* ohne Dossier bleibt der Abschnitt aus */ }
}
async function improveUi() {
  const box = $('#improve');
  if (!box) return;
  try {
    const r = await api('improve?' + box.dataset.q), voll = r.stufen.filter(st => st.items.length);
    box.innerHTML = `<h2>Verbessern ${info('improve', 'Verbessern')}</h2>${r.grund ? `<p class="muted">${esc(r.grund)}</p>` : !voll.length ? '<p class="muted">Nichts gefunden, was beliebter ist als die schwächsten Karten im Deck und frei oder bis 5 € zu haben ist.</p>'
      : `<p class="lead">Karten, die bei EDHREC für diesen Commander beliebter sind als die schwächste Karte derselben Rolle in deinem Deck.${proxyAn() ? ` <a href="#/proxy?karten=${encodeURIComponent(voll.filter(st => st.key !== 'frei').flatMap(st => st.items.map(u => u.rein.name)).join('\n'))}">Die zum Kaufen als Proxys ausprobieren</a>` : ''}</p>${voll.map(st => `<h3>${esc(st.label)}</h3><div class="rows">${st.items.map(u => `
        <div class="row swap"><span data-oid="${esc(u.rein.oracle_id)}"${peekAt(u.rein.image, u.rein.name, eur(u.rein.price))}>${pic(small(u.rein.image), '', 'thumb')}</span>
          <div class="min0"><div class="name" data-oid="${esc(u.rein.oracle_id)}">${esc(u.rein.name)}</div><div class="sub2">statt <span class="link" data-oid="${esc(u.raus.oracle_id)}">${esc(u.raus.name)}</span>, ${esc(u.label)}, in ${Math.round(u.rein.inc * 100)} % der Decks</div></div>
          <div></div><div class="price">${st.key === 'frei' ? 'hast du' : eur(u.rein.price)}</div></div>`).join('')}</div>`).join('')}`}`;
  } catch (e) { if (!(e instanceof LoginNoetig)) box.innerHTML = `<h2>Verbessern</h2>${ladeFehler(e)}`; }
}

// Änderungen fertiger Decks (beim erneuten Hochladen erkannt), mit Notiz, warum
const logHtml = d => !d.log?.length ? '' : `<section class="sec" aria-label="Änderungen"><h2>Änderungen <small>${d.log.length}</small></h2><div class="log">${d.log.map(l => `
  <div class="logrow"><div class="muted">${day(l.at)}</div><div class="min0"><div class="chips">${l.rein.map(([n, name]) => `<span class="chip">+${n} ${esc(name)}</span>`).join('')}${l.raus.map(([n, name]) => `<span class="chip">−${n} ${esc(name)}</span>`).join('')}</div>
    <input class="grund" data-log="${l.id}" value="${esc(l.grund)}" maxlength="500" placeholder="Warum? Zum Beispiel: zu langsam, neue Karte ausprobiert" aria-label="Grund für die Änderung vom ${day(l.at)}"></div></div>`).join('')}</div></section>`;

// Zusammensuchen: wo die Kopien eines gespeicherten Decks liegen, zum Abhaken und Drucken
function showPick(r, order) {
  main.innerHTML = `${head(`Zusammensuchen: ${esc(r.name)}`, `Diese Kopien hat der Sortier-Plan für das Deck vorgesehen (die günstigsten), nach Binder und ${order === 'scan' ? 'in der Reihenfolge, in der du sie eingescannt hast' : 'nach Edition und Nummer'}. Hak ab, was du herausgenommen hast.`,
      `<a class="btn ghost" href="#/decks?id=${r.id}">${icon('left')}Zum Deck</a><label class="inl noprint">Reihenfolge <select id="pickorder"><option value="set">nach Serie und Nummer</option><option value="scan"${order === 'scan' ? ' selected' : ''}>wie eingescannt</option></select></label><button class="btn" type="button" id="print">${icon('printer')}Drucken</button>`)}
    ${r.binders.map(b => `<section class="sec" aria-label="${esc(b.binder)}"><h2>${esc(b.binder)} <small>${karten(b.cards)}</small></h2><div class="rows">${b.items.map(i => `
      <label class="row pick"><input type="checkbox"><span class="min0"><span class="name">${esc(i.name)}</span><span class="sub2">${esc(i.set)} #${esc(i.number)}, ${esc(LANG[i.language] || i.language)}${i.foil !== 'normal' ? ', ' + esc(i.foil) : ''}</span></span><span class="num">${i.qty}×</span></label>`).join('')}</div></section>`).join('')}
    ${r.basics.length ? `<section class="sec" aria-label="Standardländer"><h2>Standardländer</h2><div class="chips big">${r.basics.map(x => `<span class="chip">${x.qty}× ${esc(x.name)}</span>`).join('')}</div></section>` : ''}
    ${r.fehlt.length ? `<section class="sec" aria-label="Ohne Kopie"><h2>Ohne Kopie <small>${karten(r.fehlt.reduce((n, f) => n + f.qty, 0))}</small></h2><p class="lead">Für diese Karten hat der Plan keine Kopie in einem Binder, zum Beispiel weil sie in einem anderen Deck steckt.</p>
      <div class="chips big">${r.fehlt.map(f => `<span class="chip warn">${f.qty}× ${esc(f.name)}</span>`).join('')}</div></section>` : ''}`;
  $('#print').onclick = () => print();
  $('#pickorder').onchange = e => { location.hash = `#/decks?id=${r.id}&pick=1${e.target.value === 'scan' ? '&order=scan' : ''}`; };
}
// Rückweg: wohin die Karten gehen, wenn das Deck aufgelöst wird (Sortier-Plan ohne das Deck)
function showZerlegen(r, p) {
  const zurueck = p.get('id') ? `#/decks?id=${p.get('id')}` : `#/decks?binder=${encodeURIComponent(r.name)}`;
  const titel = z => z.stack === 'deck' ? `In ${z.deck}` : LABEL[z.stack];  // chip() escapt selbst
  main.innerHTML = `${head(`Zerlegen: ${esc(r.name)}`, `Wohin die ${karten(r.karten)} gehen, wenn du das Deck auflöst. Die App rechnet den Sortier-Plan ohne das Deck neu. ${p.get('id') ? 'Aufgelöst ist es erst, wenn du es löschst.' : 'Aufgelöst ist es, sobald du die Karten in deiner Scanner-App (zum Beispiel ManaBox) umsortierst und neu exportierst.'}`,
    `<a class="btn ghost" href="${zurueck}">${icon('left')}Zum Deck</a><button class="btn" type="button" id="print">${icon('printer')}Drucken</button>`)}
    ${legend(Object.fromEntries(STACKS.map(k => [k, {cards: r.ziele.filter(z => z.stack === k).reduce((n, z) => n + z.items.reduce((m, i) => m + i.qty, 0), 0), value: r.ziele.filter(z => z.stack === k).reduce((n, z) => n + z.items.reduce((m, i) => m + i.qty * i.price, 0), 0)}])))}
    ${r.ziele.map(z => `<section class="sec" aria-label="${esc(titel(z))}"><h2>${chip(z.stack, titel(z))} <small>${karten(z.items.reduce((n, i) => n + i.qty, 0))}</small></h2><div class="rows">${z.items.map(i => `
      <label class="row pick"><input type="checkbox"><span class="min0"><span class="name">${esc(i.name)}</span><span class="sub2">${esc(i.set)} #${esc(i.number)}${i.foil !== 'normal' ? ', ' + esc(i.foil) : ''}, aus ${esc(i.binder)}</span></span><span class="num">${i.qty}×</span></label>`).join('')}</div></section>`).join('')
      || '<div class="empty">Das Deck hat keine Karten aus deinem Bestand.</div>'}
    <p class="note-line">Standardländer gehen zu den anderen Standardländern, sie stehen hier nicht einzeln.</p>`;
  $('#print').onclick = () => print();
}
const facts = list => `<div class="facts">${list.map(([v, l, t]) => `<div><b>${v}</b><span>${l}${t ? ' ' + info(t, l) : ''}</span></div>`).join('')}</div>`;
const deckArt = c => `<figure>${c && c.image ? `<img class="art" alt="${esc(c.name)}" src="${esc(art(c.image))}" data-oid="${esc(c.oracle_id)}"${peekAt(c.image, c.name, eur(c.price))}>` : '<span class="noimg">kein Commander</span>'}
  ${c && c.artist ? `<figcaption class="credit">Illustration: ${esc(c.artist)}</figcaption>` : ''}</figure>`;

// Thema des Decks: EDHREC-Thema (zählt nach Deckzahl) und wie viele der weiteren Karten per Kartentext dazu passen
const themeLine = t => {
  if (!t) return '';
  const head = t.name ? `Thema <b>${esc(t.name)}</b>${t.auto ? ' (automatisch gewählt)' : ''}: ${num(t.count)} EDHREC-Decks, zählt zu ${Math.round(t.weight * 100)} % ${info('themeweight', 'Einfluss des Themas')}`
    : 'Kein EDHREC-Thema, die Funktion stammt aus dem Kartentext des Commanders';
  const fit = t.fit != null ? `. ${t.fit} von ${t.of} weiteren Karten passen zu ${esc(t.fn_label)}${t.fn_from === 'text' ? ' (laut Kartentext des Commanders)' : ''} ${info('themefit', 'passende Karten')}` : '';
  const tried = t.tried.length > 1 ? `. Geprüft: ${t.tried.map(([n, c]) => `${esc(n)} ${Math.round(c * 100)} %`).join(', ')}` : '';
  return `<p class="note-line">${head}${fit}${tried}.</p>`;
};
const themeSelect = (d, sel) => `<label class="inl">Thema ${info('theme', 'Thema')} <select id="theme">
  <option value="auto"${sel === 'auto' ? ' selected' : ''}>Automatisch${d.theme?.auto && d.theme.name ? ` (${esc(d.theme.name)})` : ''}</option>
  ${(d.themes || []).map(t => `<option value="${esc(t[2] || t[0])}"${sel === (t[2] || t[0]) ? ' selected' : ''}>${esc(t[0])} (${num(t[1])} Decks)</option>`).join('')}
  <option value="none"${sel === 'none' ? ' selected' : ''}>Ohne Thema (allgemeine Liste)</option></select></label>`;

function showDeck(d, buildId, themeSel = 'auto') {
  const c = d.commander, preview = buildId != null, saved = d.id != null;
  const text = `Commander\n1 ${c.name}\n\nDeck\n` + d.cards.map(x => `${x.qty} ${x.name}`).join('\n') + '\n';
  const karten = d.cards.reduce((n, x) => n + x.qty, 0) + 1;
  main.innerHTML = `<section class="dh" aria-label="Deck">${deckArt(c)}<div class="min0">
      <h1>${esc(c.name)} ${pips(c.ci)}</h1>
      <p class="muted">${preview ? 'Vorschlag aus deinen freien Karten, noch nicht gespeichert.' : `Gespeichert am ${day(d.saved_at)}. Die Karten sind für dieses Deck reserviert.`}</p>
      ${facts([[karten, 'Karten'], [eur(d.value), 'Wert'], [fmt(d.avg_cmc, 2), 'Ø Manawert', 'cmc'], [d.gc, 'Game Changer', 'gc'], [`${Math.round((d.coverage || 0) * 100)} %`, 'Abdeckung', 'coverage']])}
      ${d.warnings.length ? `<div class="chips gap-top">${d.warnings.map(w => `<span class="chip warn">${esc(w)}</span>`).join('')}</div>` : ''}
      ${themeLine(d.theme)}
      <div class="seg noprint gap-top">${preview ? `<label class="inl">Bracket ${info('bracket', 'Bracket')} <select id="bracket">${[1, 2, 3, 4, 5].map(b => `<option${b === d.bracket ? ' selected' : ''}>${b}</option>`).join('')}</select></label>
          ${themeSelect(d, themeSel)}
          <button class="btn primary" type="button" id="save">Deck speichern</button>` : `<span class="tag">Bracket ${d.bracket}</span>`}
        <a class="btn" ${saved ? `href="/api/deck/${d.id}.txt" download="${esc(c.name)}.txt"` : 'href="#" id="txt"'}>${icon('text')}Textliste (Moxfield, Archidekt)</a>${bracketBtn}
        ${saved ? `<a class="btn" href="#/decks?id=${d.id}&pick=1">${icon('layers')}Zusammensuchen</a><a class="btn" href="#/decks?id=${d.id}&zerlegen=1">Zerlegen: wohin?</a><button class="btn danger" type="button" id="del">${icon('trash')}Deck auflösen</button>` : ''}<a class="btn ghost" href="#/decks">${icon('left')}Alle Decks</a></div></div></section>
    ${deckKarten(d)}
    ${manaHtml(d.stats)}
    ${handHtml(d)}
    ${dossierSec(c?.name)}
    ${saved ? improveSec(`id=${d.id}`) : ''}
    ${!saved && d.upgrades.length ? `<section class="sec" aria-label="Was noch fehlt"><h2>Was noch fehlt <small>beliebteste Karten für diesen Commander, die du nicht frei hast</small></h2><div class="rows">${d.upgrades.map(u => `<div class="row" data-oid="${esc(u.oracle_id)}"${peekAt(u.image, u.name, eur(u.price))}>${pic(small(u.image), '', 'thumb')}
      <div class="min0"><div class="name">${esc(u.name)}</div><div class="sub2">in ${Math.round(u.inc * 100)} % der Decks${u.gc ? ', Game Changer' : ''}</div></div><div></div><div class="price">${eur(u.price)}</div></div>`).join('')}</div></section>` : ''}`;
  $('#bracketcheck').onclick = () => openBracket(text);
  handUi(d); improveUi(); dossierUi();
  if (preview) {
    const go = (bracket, theme) => { location.hash = `#/decks?build=${encodeURIComponent(buildId)}&bracket=${bracket}&theme=${encodeURIComponent(theme)}`; };
    $('#bracket').onchange = e => go(e.target.value, themeSel);
    $('#theme').onchange = e => go(d.bracket, e.target.value);
    $('#save').onclick = async () => {
      try { const r = await post('build', {commander: buildId, bracket: d.bracket, theme: themeSel, save: true}); flash(`Gespeichert, die Karten sind jetzt reserviert`); location.hash = `#/decks?id=${r.id}`; }
      catch (e) { flash('Fehler: ' + e.message); }
    };
    $('#txt').onclick = e => { e.currentTarget.href = URL.createObjectURL(new Blob([text], {type: 'text/plain'})); e.currentTarget.download = c.name + '.txt'; };
  }
  if (saved) $('#del').onclick = async () => {
    if (!confirm(`Deck „${c.name}“ auflösen? Die Karten werden wieder frei.`)) return;
    await post(`deck/${d.id}/delete`);
    location.hash = '#/decks';
  };
}

// Mana: Manakurve (Karten ohne Länder je Manawert) und Farbquellen (Länder, die die Farbe erzeugen, gegen Farbsymbole der Zauber)
const manaHtml = st => !st ? '' : `<section class="sec" aria-label="Mana"><h2>Mana <small>Manakurve und Farbquellen</small></h2><div class="split even">
  <div><h3>Manakurve ${info('curve', 'Manakurve')}</h3><div class="bars">${st.curve.map((n, i) => `<span class="lbl">${i === 6 ? '6 und mehr' : `Manawert ${i}`}</span>
    <span class="track"><span style="--w:${(n / Math.max(...st.curve, 1) * 100).toFixed(1)}%"></span></span><span class="val">${n}</span>`).join('')}</div></div>
  <div><h3>Farbquellen ${info('sources', 'Farbquellen')}</h3>${st.colors.length ? `<div class="bars wide">${st.colors.map(c => `<span class="lbl">${pip(c.c)}${esc(COLORS[c.c])}</span>
    <span class="track"><span style="--w:${(c.sources / Math.max(...st.colors.map(x => x.sources), 1) * 100).toFixed(1)}%"></span></span><span class="val">${c.sources} Länder, ${c.symbols} Symbole</span>`).join('')}</div>
    <p class="note-line">Der Balken zeigt, wie viele der ${st.lands} Länder die Farbe erzeugen. Dazu stehen die Farbsymbole in den Kosten der Zauber.</p>
    ${st.colors.some(c => c.p1 != null) ? `<h3>Farbe rechtzeitig da ${info('quelle', 'Farbe rechtzeitig da')}</h3><div class="chips big">${st.colors.filter(c => c.p1 != null).map(c => `<span class="chip${c.knapp ? ' warn' : ''}">${esc(COLORS[c.c])}: ${pct(c.p1)} bis Zug 3${c.p2 != null ? `, zwei bis Zug 4 ${pct(c.p2)}` : ''}</span>`).join('')}</div>` : ''}`
    : '<p class="muted">Farblos: keine Farbquellen nötig.</p>'}</div></div></section>`;

// Bracket-Prüfung: Liste an Commander Spellbook, Ergebnis im Dialog
const bracketHtml = r => `<button class="x" data-close aria-label="Schließen">${icon('x')}</button><div class="box">
  <h2 id="dlg-title">${r.min_bracket <= 2 ? 'Passt zu Bracket 1 und 2, auch höher' : `Mindestens Bracket ${r.min_bracket}`}</h2>
  <p class="muted">${esc(r.commanders.join(', ') || 'Commander nicht erkannt')}, ${karten(r.cards)}. Einstufung von Commander Spellbook: ${esc(r.spellbook)} ${info('spellbook', 'Einstufung')}</p>
  ${r.banned.length ? `<div class="note bad"><span class="ic">${icon('alert')}</span><div><b>In Commander verboten</b><div class="muted">${esc(r.banned.join(', '))}</div></div><span></span></div>` : ''}
  ${r.why.length ? `<ul>${r.why.map(w => `<li>${esc(w)}</li>`).join('')}</ul>` : '<p>Die App findet nichts, was ein höheres Bracket verlangt: keine Game Changer, keine Extrazüge, keine Massen-Landzerstörung, keine 2-Karten-Combo.</p>'}
  ${[['Game Changer', r.game_changers], ['Massen-Landzerstörung', r.mass_land_denial], ['Extrazüge', r.extra_turns]].filter(([, l]) => l.length)
    .map(([t, l]) => `<div><h3>${t}</h3><div class="chips big">${l.map(n => `<span class="chip">${esc(n)}</span>`).join('')}</div></div>`).join('')}
  ${r.combos.length ? `<div><h3>Combos</h3><ul>${r.combos.map(c => `<li>${esc(c.cards.join(' + '))}: ${esc(c.result)}${c.two_card ? ', nur 2 Karten' : ''} (Spellbook: ${esc(c.tag)})</li>`).join('')}</ul></div>` : ''}
  <p class="note-line">Das Bracket selbst sprecht ihr am Tisch ab. Die Zahl ist eine Untergrenze nach den Regeln dieser App: Game Changer (bis zu drei ab Bracket 3, mehr ab 4), Extrazüge ab 3, Massen-Landzerstörung, Combos mit Lock und 2-Karten-Combos ab 4.</p>
  <div class="actions"><button class="btn primary" type="button" data-close>Schließen</button></div></div>`;
async function openBracket(text) {
  if (!text.trim()) { flash('Erst eine Deckliste einfügen'); return; }
  dlg.className = 'modal';
  dlg.innerHTML = `<button class="x" data-close aria-label="Schließen">${icon('x')}</button><div class="box"><h2 id="dlg-title">Bracket wird geprüft</h2><div class="progress busy"><span></span></div><p class="muted">Die Liste geht an Commander Spellbook.</p></div>`;
  showDlg();
  try { dlg.innerHTML = bracketHtml(await post('bracket', {text})); }
  catch (e) { dlg.innerHTML = `<button class="x" data-close aria-label="Schließen">${icon('x')}</button><div class="box"><h2 id="dlg-title">Das ging nicht</h2><p>${esc(e.message)}</p><div class="actions"><button class="btn primary" type="button" data-close>Schließen</button></div></div>`; }
}
const bracketBtn = `<button class="btn" type="button" id="bracketcheck">${icon('check')}Bracket prüfen</button>`;

function showBinderDeck(d) {
  const c = d.commander;
  const kand = d.cards.filter(x => /Legendary/.test(x.type) && /Creature|can be your commander/.test(x.type));
  main.innerHTML = `<section class="dh" aria-label="Deck">${deckArt(c)}<div class="min0">
      <h1>${esc(d.name)} ${pips(d.ci)}</h1>
      <p class="muted">Fertiges Deck${c ? ` mit ${esc(c.name)}` : ''}. Seine Karten stehen im Stapel Deck und werden für neue Decks nicht angefasst.</p>
      ${facts([[d.count, 'Karten'], [eur(d.value), 'Wert'], [fmt(d.avg_cmc, 2), 'Ø Manawert', 'cmc'], [d.gc, 'Game Changer', 'gc']])}
      <div class="seg noprint gap-top">
        ${!c && kand.length ? `<label class="inl">Commander <select id="cmd"><option value="">wählen</option>${kand.map(x => `<option value="${esc(x.oracle_id)}">${esc(x.name)}</option>`).join('')}</select></label>` : ''}
        <a class="btn" href="/api/binder-deck.txt?name=${encodeURIComponent(d.binder)}" download="${esc(d.name)}.txt">${icon('text')}Textliste</a>${bracketBtn}
        <a class="btn" href="#/decks?binder=${encodeURIComponent(d.binder)}&zerlegen=1">Zerlegen: wohin?</a><button class="btn danger" type="button" id="del">${icon('trash')}Aus der Sammlung entfernen</button><a class="btn ghost" href="#/decks">${icon('left')}Alle Decks</a></div></div></section>
    ${deckKarten(d)}
    ${manaHtml(d.stats)}
    ${handHtml(d)}
    ${dossierSec(c?.name)}
    ${improveSec(`binder=${encodeURIComponent(d.binder)}`)}
    ${logHtml(d)}`;
  handUi(d); improveUi(); dossierUi();
  $('#bracketcheck').onclick = () => openBracket((c ? `Commander\n1 ${c.name}\n\nDeck\n` : '') + d.cards.map(x => `${x.qty} ${x.name}`).join('\n') + '\n');
  const sel = $('#cmd');
  if (sel) sel.onchange = async () => { try { await api('binder-deck?name=' + encodeURIComponent(d.binder), {method: 'POST', body: JSON.stringify({commander: sel.value})}); render(true); } catch (e) { flash('Fehler: ' + e.message); } };
  $('#del').onclick = async () => {
    if (!confirm(`„${d.name}“ mit ${d.count} Karten aus der Sammlung entfernen? Das betrifft nur diese App, nicht deine Scanner-App.`)) return;
    await api('binder-deck?delete=1&name=' + encodeURIComponent(d.binder), {method: 'POST'});
    flash(`„${d.name}“ entfernt`); location.hash = '#/decks';
  };
}

// --- Konten und Sicherung (Phase 13): Hauptkonto, Unterkonten mit eigener Sammlung, Anmeldung, Sicherung ----------------
// sess kommt von /api/session: modus einfach (keine Konten), lokal (Konten, kein Login) oder anmeldung (Login Pflicht)
let sess = {modus: 'einfach', angemeldet: true, rolle: 'haupt', sammlungen: []}, loginOffen = false;
const fremd = () => sess.aktiv && sess.aktiv !== sess.konto && sess.sammlungen.find(k => k.name === sess.aktiv);

function showLogin(msg) {
  if (loginOffen) return;  // schon offen: nichts überschreiben, was gerade getippt wird
  loginOffen = true; hidePeek(); hideTip();
  if (dlg.open) dlg.close();
  $('#nav').innerHTML = ''; $('#who').innerHTML = ''; $('#import').hidden = true;
  document.title = `Anmelden · ${APP}`;
  main.innerHTML = `<section class="login" aria-labelledby="l-title"><h1 id="l-title">Anmelden</h1>
    <p class="muted">Diese Sammlung ist mit einem Passwort geschützt.</p>
    <form id="login" class="kform">
      <div class="field"><label for="l-name">Name</label><input id="l-name" name="name" required autocomplete="username" autocapitalize="none" spellcheck="false"></div>
      <div class="field"><label for="l-pw">Passwort</label><input id="l-pw" name="passwort" type="password" required autocomplete="current-password"></div>
      <p class="say bad" id="l-msg" role="alert">${esc(msg || '')}</p>
      <div class="actions"><button class="btn primary" type="submit">Anmelden</button></div></form></section>`;
  $('#l-name').focus();
}
async function login(f) {
  try {
    sess = await post('login', Object.fromEntries(new FormData(f)));
    loginOffen = false; $('#import').hidden = false; rendered = null; whoUi(); render(true);
  } catch (e) { $('#l-msg').textContent = e.message; $('#l-pw').select(); }
}
async function logout() {
  try { await post('logout'); } catch { /* ohnehin abgemeldet */ }
  sess = {...sess, angemeldet: false}; showLogin('Abgemeldet.');
}

// Erste Einrichtung (Phase 43, PLAN E28): Ein Server ohne Hauptkonto liefert nur diese Seite. Erst der Code, dann „Neu anfangen“ oder,
// in einen leeren Datenordner, „Sicherung einspielen“. Der Code bleibt im Speicher dieser Seite und geht nur im Körper der Anfragen mit.
let einrCode = '';
function einrSeite(html) {
  loginOffen = true; hidePeek(); hideTip();  // wie bei der Anmeldung: keine Ansicht lädt, solange die Einrichtung offen ist
  if (dlg.open) dlg.close();
  $('#nav').innerHTML = ''; $('#who').innerHTML = ''; $('#import').hidden = true;
  document.title = `Einrichtung · ${APP}`;
  main.innerHTML = `<section class="login einr" aria-labelledby="e-title"><h1 id="e-title">Einrichtung</h1>${html}</section>`;
}
function showEinrichtung(msg) {
  einrCode = '';
  einrSeite(`<p class="muted">${esc(TIP.einrichtung)}</p>
    <form id="einr-code" class="kform">
      <div class="field"><label for="e-code">Einrichtungs-Code</label><input id="e-code" name="code" required maxlength="40" placeholder="XXXXX-XXXXX-XXXXX-XXXXX" autocomplete="off" autocapitalize="characters" autocorrect="off" spellcheck="false"></div>
      <p class="say bad" id="e-msg" role="alert">${esc(msg || '')}</p>
      <div class="actions"><button class="btn primary" type="submit">Weiter</button></div></form>`);
  $('#e-code').focus();
}
function einrWahl(stand, hinweis) {
  einrSeite(`<p class="muted">${esc(hinweis || 'Der Code stimmt.')}</p>
    <form id="einr-neu" class="kform"><h2>Neu anfangen</h2>
      <p class="muted">${esc(TIP.einrneu)}</p>
      <div class="field"><label for="n-name">Dein Name</label><input id="n-name" name="name" required maxlength="40" autocomplete="username"></div>
      <div class="field"><label for="n-pw">Passwort (mindestens 8 Zeichen)</label><input id="n-pw" name="passwort" type="password" required minlength="8" autocomplete="new-password"></div>
      <p class="say bad" id="n-msg" role="alert"></p>
      <div class="actions"><button class="btn primary" type="submit">Hauptkonto anlegen</button></div></form>
    ${stand.sicherung ? `<form id="einr-zip" class="kform"><h2>Sicherung einspielen</h2>
      <p class="muted">${esc(TIP.einrzip)}</p>
      <div class="field"><label for="z-datei">Sicherung (ZIP, höchstens ${num(stand.max_mb)} MB)</label><input id="z-datei" name="datei" type="file" required accept=".zip,application/zip"></div>
      <p class="say bad" id="z-msg" role="alert"></p>
      <div class="actions"><button class="btn" type="submit">${icon('upload')}Sicherung einspielen</button></div></form>` : `<p class="note-line">${esc(TIP.einrbelegt)}</p>`}`);
  $('#n-name').focus();
}
// Ist die Einrichtung inzwischen abgeschlossen (ein anderes Gerät war schneller), hilft nur neu laden: Dann kommt die Anmeldung.
const einrFehler = (e, ziel) => { if (e.fertig) location.reload(); else $(ziel).textContent = e.message; };
async function einrCodeForm(f) {
  const code = new FormData(f).get('code').trim();
  try { const stand = await post('einrichtung', {aktion: 'code', code}); einrCode = code; einrWahl(stand); }
  catch (e) { einrFehler(e, '#e-msg'); $('#e-code')?.select(); }
}
async function einrNeuForm(f) {
  try { await post('einrichtung', {aktion: 'neu', code: einrCode, ...Object.fromEntries(new FormData(f))}); location.reload(); }  // angemeldet: Die App lädt jetzt ganz
  catch (e) { einrFehler(e, '#n-msg'); }
}
async function einrZipForm(f) {
  const datei = f.datei.files[0], knopf = $('button[type=submit]', f), msg = $('#z-msg');
  if (!datei) return;
  knopf.disabled = true; msg.className = 'say'; msg.textContent = 'Lädt hoch und prüft. Bei einer großen Sammlung dauert das einige Minuten, die Seite so lange offen lassen.';
  try {  // erste Zeile der Code, dahinter die ZIP: Der Server prüft den Code, bevor er die Datei annimmt
    const r = await api('einrichtung/sicherung', {method: 'POST', headers: {'Content-Type': 'application/octet-stream'}, body: new Blob([einrCode + '\n', datei])});
    const was = `Eingespielt: Stand vom ${r.datum}, ${plural(r.sammlungen, 'Sammlung', 'Sammlungen')}, ${karten(r.karten)}, ${plural(r.konten, 'Konto', 'Konten')}.`;
    if (!r.anmeldung) return einrWahl({sicherung: false}, `${was} Die Sicherung bringt kein Konto mit: Leg jetzt das Hauptkonto an, die Sammlung gehört dann ihm.`);
    einrSeite(`<p class="muted">${esc(was)} Melde dich jetzt mit Name und Passwort aus der Sicherung an.</p>
      <div class="actions"><button class="btn primary" type="button" id="einr-fertig">Zur Anmeldung</button></div>`);
    $('#einr-fertig').onclick = () => location.reload();
    $('#einr-fertig').focus();
  } catch (e) { knopf.disabled = false; msg.className = 'say bad'; einrFehler(e, '#z-msg'); }
}

// Kopf: Sammlung wählen (nur bei mehreren) und Abmelden (nur mit Anmeldung)
function whoUi() {
  const show = sess.modus !== 'einfach' && sess.angemeldet;
  $('#who').innerHTML = !show ? '' : `${sess.sammlungen.length > 1 ? `<select id="sammlung" aria-label="Sammlung wählen" title="Welche Sammlung du gerade siehst">${sess.sammlungen.map(k => `<option value="${esc(k.name)}"${k.name === sess.aktiv ? ' selected' : ''}>${esc(k.anzeige)}</option>`).join('')}</select>` : ''}
    ${sess.modus === 'anmeldung' ? `<button class="btn ghost small" type="button" id="logout" title="${esc(sess.anzeige)} abmelden">Abmelden</button>` : ''}`;
}
async function switchTo(name) {
  try {
    sess = await post('session', {aktiv: name}); jobs = {}; whoUi();
    flash(`Sammlung: ${sess.sammlungen.find(k => k.name === name)?.anzeige || name}`);
    if (location.hash.startsWith('#/konten')) location.hash = '#/'; else render(true);
  } catch (e) { flash('Fehler: ' + e.message); whoUi(); }
}

// Sicherung außer Haus (Phase 27): Kopie per deploy/sicherung-aussen.sh oder Download, die jüngere zählt
const AUSSEN_TAGE = 14;  // älter: Hinweis auf der Übersicht (nur mit Scan-Bindern, die gibt es sonst nirgends)
function aussenStand(a) {
  const t = [a?.aussen?.at, a?.geladen].filter(Boolean).sort().at(-1), am = x => day(x) === 'heute' ? 'heute' : `am ${day(x)}`;
  const wege = [a?.aussen && `${am(a.aussen.at)} nach ${a.aussen.ziel || 'außer Haus'} kopiert (${a.aussen.verschluesselt ? 'verschlüsselt' : 'unverschlüsselt'})`, a?.geladen && `${am(a.geladen)} heruntergeladen`].filter(Boolean);
  return {alt: !t || Date.now() - Date.parse(t) > AUSSEN_TAGE * 864e5, titel: t ? `Letzte Sicherung außer Haus ${am(t)}` : 'Noch keine Sicherung außer Haus', wege,
    offen: !!a?.aussen && !a.aussen.verschluesselt};  // offen: Die jüngste Kopie ging unverschlüsselt hinaus
}
// Zweiter Ordner (Phase 42): Haken, Pfad und was daraus geworden ist; die Verschlüsselung (gpg) hängt an der Schlüsseldatei der App
const VERSCHL = {ok: ['check', 'Die Kopie wird verschlüsselt', 'Mit gpg und der Schlüsseldatei dieser App. Ohne den Schlüssel kann niemand sie lesen, und du auch nicht: Bewahre ihn getrennt von diesem Rechner auf.'],
  aus: ['alert', 'Die Kopie geht unverschlüsselt in den Ordner', 'Die ZIP enthält Passwort-Hashes und Kaufpreise. Wer an den Ordner kommt, liest sie. Mit einer Schlüsseldatei (MTG_AUSSEN_SCHLUESSEL, Anleitung in der README) verschlüsselt die App sie vorher.'],
  defekt: ['alert', 'Verschlüsseln geht gerade nicht', 'Kopiert wird deshalb nichts, bis es geht.']};
function ordnerHtml(o) {
  const v = VERSCHL[o.verschluesselung] || VERSCHL.aus, e = o.ergebnis;
  const stand = e ? `<p class="note-line" id="o-stand">Zuletzt ${day(e.at)}: ${e.ok ? 'kopiert, ' : '<b>nicht geklappt:</b> '}${esc(e.text)}</p>` : `<p class="note-line" id="o-stand">${o.an ? 'Noch nicht kopiert. Der nächste Lauf der App tut es, spätestens in einer Stunde.' : 'Aus.'}</p>`;
  return `<section class="sec" aria-label="Zweiter Ordner"><h2>Zweiter Ordner ${info('zweiterordner', 'Zweiter Ordner')}</h2>
    <p class="lead">Die App legt nach der täglichen Sicherung eine Kopie in diesen Ordner, zum Beispiel den einer Cloud, eines NAS oder einer eingehängten Storage Box. Nur du als Hauptkonto stellst das ein.</p>
    <form class="kform" data-ordner="1">
      <label class="inl"><input type="checkbox" name="an"${o.an ? ' checked' : ''}> Sicherung zusätzlich in diesen Ordner kopieren</label>
      <div class="field"><label for="o-pfad">Ordner (ganzer Pfad)</label><input id="o-pfad" name="pfad" value="${esc(o.pfad)}" placeholder="D:/Cloud/Pappenheimer oder /mnt/nas/sicherung" autocomplete="off" autocapitalize="none" spellcheck="false" maxlength="1000"></div>
      <p class="say bad" id="o-msg" role="alert"></p>
      <div class="actions"><button class="btn primary" type="submit">Speichern</button></div></form>
    <div class="todo">${note(o.verschluesselung === 'defekt' ? [v[0], v[1], `${o.problem}. ${v[2]}`] : v)}</div>
    ${stand}</section>`;
}
async function ordnerForm(f) {
  const d = Object.fromEntries(new FormData(f));
  try {
    await post('sicherung', {ordner: {an: !!d.an, pfad: d.pfad || ''}});
    flash(d.an ? 'Zweiter Ordner gespeichert' : 'Zweiter Ordner aus'); render(true);
  } catch (e) { $('#o-msg').textContent = e.message; flash('Fehler: ' + e.message); }
}
const PE_STATUS = {importiert: 'übernommen', 'keine Änderung': 'keine Änderung', abgebrochen: 'liegen geblieben (würde mehr als ein Viertel entfernen)', fehler: 'nicht lesbar', wartet: 'gerade erst gespeichert, in einer Minute noch einmal', später: 'gerade nicht möglich (kein Netz?), nächstes Mal'};
const peHtml = p => `<section class="sec" aria-label="Posteingang"><h2>Posteingang ${info('posteingang', 'Posteingang')}</h2>
    <p class="lead">Nur wenn du weiter mit einer Scanner-App (zum Beispiel ManaBox) scannst: Neue CSV-Dateien aus diesem Ordner übernimmt die App einmal am Tag von selbst, mit derselben Vorsicht wie beim Hochladen.</p>
    <p><code>${esc(p.ordner)}</code></p>
    <div class="toolbar"><label class="inl"><input type="checkbox" id="pe-an"${p.an ? ' checked' : ''}> Einmal am Tag übernehmen</label>
      <button class="btn" type="button" id="pe-jetzt">${icon('tray')}Jetzt übernehmen</button></div>
    <p class="note-line" id="pe-stand">${p.ergebnis ? `Zuletzt geprüft ${day(p.ergebnis.at)}: ${p.ergebnis.items.length ? esc(p.ergebnis.items.map(i => `„${i.datei}“ ${PE_STATUS[i.status] || i.status}`).join(', ')) : 'nichts Neues'}` : 'Noch nie geprüft.'}</p></section>`;
async function peSetzen(d) {
  try {
    const p = await post('posteingang', d);
    $('[aria-label="Posteingang"]').outerHTML = peHtml(p);
    flash(d.jetzt ? `Posteingang geprüft: ${p.ergebnis.items.filter(i => i.status === 'importiert').length} übernommen` : `Posteingang ${p.an ? 'an' : 'aus'}`);
  } catch (e) { flash('Fehler: ' + e.message); render(true); }
}

// Quellen (Phase 44, PLAN E25): je Quelle Zweck, was hingeschickt wird, wie oft, Link zu den Bedingungen und der Schalter für die ganze Installation
let quellenDaten = [];
async function viewQuellen() {
  const r = await api('quellen');
  quellenDaten = r.items;
  sess = {...sess, quellen: Object.fromEntries(r.items.filter(q => q.schaltbar).map(q => [q.key, q.an]))};
  const kann = r.haupt && !r.gesperrt;
  main.innerHTML = `${head('Quellen', 'Woher die App Daten holt, was sie dabei hinschickt und wie oft. Jede Quelle außer Scryfall lässt sich abschalten, für die ganze Installation: auch für Unterkonten und den täglichen Lauf.',
      `<a class="btn ghost" href="#/konten">${icon('left')}Konten und Sicherung</a>`)}
    <p class="note-line">${esc(TIP.quellen)}</p>
    ${r.gesperrt ? `<div class="todo">${note(['info', 'Festgelegt in der Umgebung', `Die Variable ${r.env} legt fest, welche Quellen laufen. Die Schalter hier sind gesperrt; ändern lässt es sich nur dort (Liste der eingeschalteten Quellen, zum Beispiel spellbook,cardmarket; alle; keine).`])}</div>`
      : !r.haupt ? `<div class="todo">${note(['info', 'Das Hauptkonto stellt das ein', 'Du siehst hier, was die App abruft. Die Schalter stellt nur das Hauptkonto.'])}</div>` : ''}
    ${r.items.map(q => `<section class="sec" aria-label="${esc(q.name)}" id="q-${esc(q.key)}"><h2>${esc(q.name)} <small>${q.schaltbar ? (q.an ? 'an' : 'aus') : q.key === 'github' ? 'nur auf Knopfdruck' : 'immer an'}</small></h2>
      <p class="lead">${esc(q.zweck)}</p>
      <p class="note-line"><b>Was hingeschickt wird:</b> ${esc(q.schickt)}</p>
      <p class="note-line"><b>Wie oft:</b> ${esc(q.wie_oft)}</p>
      ${q.hinweis ? `<p class="note-line">${esc(q.hinweis)}</p>` : ''}
      <p class="note-line"><a href="${esc(q.link)}" target="_blank" rel="noopener noreferrer">${q.key === 'edhrec' ? 'Nutzungsbedingungen von EDHREC' : q.key === 'scryfall' ? 'Regeln von Scryfall' : q.key === 'github' ? 'Veröffentlichungen auf GitHub' : `Website von ${esc(q.name)}`}<span class="sr-only"> (neues Fenster)</span></a></p>
      ${q.schaltbar ? `<label class="inl quelle-an"><input type="checkbox" data-quelle="${esc(q.key)}"${q.an ? ' checked' : ''}${kann ? '' : ' disabled'}> ${esc(q.name)} verwenden</label>` : ''}
    </section>`).join('')}`;
}
async function quelleSetzen(t) {
  const k = t.dataset.quelle, q = quellenDaten.find(x => x.key === k);
  if (t.checked && q?.hinweis && k === 'edhrec' && !confirm(`${q.hinweis}\n\n${q.name} einschalten?`)) { t.checked = false; return; }
  try {
    const r = await post('quellen', {[k]: t.checked});
    sess = {...sess, quellen: Object.fromEntries(r.items.filter(x => x.schaltbar).map(x => [x.key, x.an]))};
    flash(`${QNAME[k]} ${t.checked ? 'eingeschaltet' : 'abgeschaltet'}`);
  } catch (e) { flash('Fehler: ' + e.message); }
  render(true);
}

async function proxySetzen(t) {
  if (t.checked && !confirm(`${TIP.proxyblatt}\n\nDas Proxy-Blatt einschalten?`)) { t.checked = false; return; }
  try {
    const r = await post('proxy-blatt', {an: t.checked});
    sess = {...sess, proxy: r.an};
    flash(`Proxy-Blatt ${r.an ? 'eingeschaltet' : 'ausgeschaltet'}`);
  } catch (e) { flash('Fehler: ' + e.message); }
  render(true);
}

// Updates (Phase 50, PLAN E31): nur auf Knopfdruck und nur fürs Hauptkonto; die App fragt nie von selbst bei GitHub nach
const UPDATE_WEGE = 'Docker: die neue compose.yaml holen (Anleitung in der README), dann „docker compose pull“ und „docker compose up -d“. Windows: pappenheimer-windows.zip der Veröffentlichung an dieselbe Stelle entpacken und Dateien ersetzen. Deine Sammlung in data bleibt in beiden Fällen.';
function updateHtml(u) {
  const l = u.letzte;
  const link = l?.url ? `<a class="btn" href="${esc(l.url)}" target="_blank" rel="noopener noreferrer">${icon('cloud')}Änderungen ansehen<span class="sr-only"> (neues Fenster)</span></a>` : '';
  const stand = !l ? ['info', 'Noch nicht nachgesehen', 'Drück „Nach Updates suchen“, dann fragt die App einmal bei GitHub nach.']
    : !l.version ? ['info', `Zuletzt ${day(l.at)} nachgesehen`, 'GitHub kennt noch keine Veröffentlichung.']
    : l.neu ? [l.sicherheit ? 'alert' : 'up', `Version ${l.version} ist da${l.sicherheit ? ' (Sicherheit)' : ''}`, `${l.titel ? l.titel + '. ' : ''}${UPDATE_WEGE}`, link]
    : ['check', 'Du hast die neueste Version', `Zuletzt ${day(l.at)} nachgesehen: ${l.version} ist die neueste Veröffentlichung.`];
  return `<section class="sec" aria-label="Updates"><h2>Updates</h2>
    <p class="lead">Du hast Version ${esc(u.eigene)}. Die App fragt nie von selbst nach Updates, nur wenn du den Knopf drückst. GitHub erfährt dabei die Adresse deines Rechners und den Programmnamen mit Version, nichts aus deiner Sammlung (mehr unter <a href="#/quellen">Quellen</a>).</p>
    <div class="toolbar"><button class="btn" type="button" id="up-suchen">${icon('refresh')}Nach Updates suchen</button></div>
    ${u.fehler ? `<p class="say bad" role="alert">${esc(u.fehler)}</p>` : ''}
    <div class="todo">${note(stand)}</div></section>`;
}
async function updateSuchen() {
  const b = $('#up-suchen'); b.disabled = true;
  try {
    const u = await post('update', {});
    $('[aria-label="Updates"]').outerHTML = updateHtml(u);
    flash(u.fehler ? 'Nachsehen nicht gelungen' : u.letzte?.neu ? `Version ${u.letzte.version} ist da` : 'Du hast die neueste Version');
  } catch (e) { b.disabled = false; flash('Fehler: ' + e.message); }
}

// Handy verbinden: QR-Code mit der Adresse dieser Seite (der Server zeichnet ihn, qr.py). Er hilft nur, wenn die Seite über eine Adresse läuft, die das
// Handy erreicht, also nicht über 127.0.0.1; sonst steht dort, was zu tun ist.
const LOKAL = /^(localhost|127(\.\d+){3}|\[?::1\]?)$/;
function handyHtml(adresse, qr) {
  const inhalt = !adresse ? `<p class="note-line">Du hast diese Seite über die Adresse dieses Rechners geöffnet (${esc(location.host)}). Die erreicht das Handy nicht. Öffne die App einmal über die Adresse deines Servers, zum Beispiel https://dein-server.dein-netz.ts.net, dann steht hier der QR-Code.</p>`
    : qr?.svg ? `<div class="handy-qr"><div class="qr">${qr.svg}</div><div class="min0"><p>Adresse: <code>${esc(adresse)}</code></p>
        <p class="muted">So geht es: Kamera-App am Handy öffnen und auf den Code halten, die Seite öffnen und anmelden. Danach im Browsermenü „App installieren“ oder „Zum Startbildschirm“ wählen. Die Kamera gibt der Browser nur über https frei.</p></div></div>`
    : `<p class="note-line">Der QR-Code ließ sich nicht zeichnen${qr?.fehler ? ` (${esc(qr.fehler)})` : ''}. Tipp die Adresse am Handy ab: <code>${esc(adresse)}</code></p>`;
  return `<section class="sec" aria-label="Handy verbinden"><h2>Handy verbinden</h2>
    <p class="lead">Scanne den Code mit dem Handy, öffne die Seite dort und installiere sie als App. Das Handy zeigt dann deine Sammlung auf diesem Server.</p>${inhalt}</section>`;
}

async function viewKonten() {
  sess = await api('session'); whoUi();
  const haupt = sess.rolle === 'haupt';
  const quellenSec = `<section class="sec" aria-label="Quellen"><h2>Quellen ${info('quellen', 'Quellen')}</h2><p class="lead">Woher die App Daten holt und was sie dabei hinschickt. ${haupt ? 'Du kannst jede Quelle außer Scryfall abschalten.' : 'Das Hauptkonto stellt sie ein.'}</p>
    <a class="btn" href="#/quellen">${icon('cloud')}Zu den Quellen</a></section>`;
  const proxySec = !haupt ? '' : `<section class="sec" aria-label="Proxy-Blatt"><h2>Proxy-Blatt ${info('proxyblatt', 'Proxy-Blatt')}</h2><p class="lead">Karten zum Ausprobieren drucken, bevor du kaufst. Ausgeschaltet gibt es keinen Link dazu und keine Schnittstelle. Der Schalter gilt für die ganze Installation.</p>
    <label class="inl quelle-an"><input type="checkbox" data-proxyblatt="1"${proxyAn() ? ' checked' : ''}> Proxy-Blatt einschalten</label></section>`;
  const adresse = haupt && !LOKAL.test(location.hostname) ? location.origin + '/' : '';
  const [sich, pe, up, qr] = haupt ? await Promise.all([api('sicherung'), api('posteingang'), api('update'),
    adresse ? post('qr', {text: adresse}).catch(e => ({fehler: e.message})) : null]) : [null, null, null, null];
  const updateSec = haupt ? updateHtml(up) : '';
  const handySec = haupt ? handyHtml(adresse, qr) : '';
  const aussen = aussenStand(sich);
  const backup = !haupt ? '' : `<section class="sec" aria-label="Sicherung"><h2>Sicherung</h2>
    <p class="lead">Eine ZIP-Datei mit allen Sammlungen, Konten und den hochgeladenen Dateien. Solange die App läuft, legt sie außerdem jeden Tag selbst eine im Ordner <code>data/sicherungen</code> an, die letzten 14 bleiben. Zurückspielen: App beenden, dann <code>mtg wiederherstellen DATEI.zip</code> (eine verschlüsselte Datei vorher mit <code>gpg -d</code> entschlüsseln, README).</p>
    <div class="todo">${note([aussen.alt ? 'alert' : 'check', aussen.titel, aussen.wege.length ? `Zuletzt ${aussen.wege.join(', ')}. ${TIP.aussen}` : TIP.aussen,
      `<a class="btn" href="/api/backup.zip" download>${icon('download')}Sicherung herunterladen</a>`])}</div>
    <p class="note-line">Die heruntergeladene ZIP ist nicht verschlüsselt und enthält Passwort-Hashes und Kaufpreise. Leg sie nur an einen Ort, dem du traust.${aussen.offen ? ' Auch die jüngste Kopie außer Haus ist unverschlüsselt.' : ''}</p></section>${ordnerHtml(sich.ordner)}`;
  const csvSec = `<section class="sec" aria-label="Bestand als CSV"><h2>Bestand als CSV</h2><p class="lead">${esc(TIP.csv)}</p>
    <a class="btn" href="/api/bestand.csv" download="bestand-${new Date().toISOString().slice(0, 10)}.csv">${icon('csv')}Bestand als ManaBox-CSV</a></section>`;
  const pwFelder = (alt, neuLabel = 'Neues Passwort') => `${alt ? '<div class="field"><label for="p-alt">Bisheriges Passwort</label><input id="p-alt" name="alt" type="password" required autocomplete="current-password"></div>' : ''}
    <div class="field"><label for="p-neu">${neuLabel} (mindestens 8 Zeichen)</label><input id="p-neu" name="passwort" type="password" required minlength="8" autocomplete="new-password"></div>`;
  if (sess.modus === 'einfach') {
    main.innerHTML = `${head('Konten und Sicherung', 'Noch gibt es eine Sammlung und keine Anmeldung. Das reicht, solange die App nur auf deinem Rechner läuft.')}
      <section class="sec" aria-label="Hauptkonto anlegen"><h2>Mehrere Sammlungen oder Anmeldung</h2>
        <p class="lead">Mit einem Hauptkonto legst du getrennte Sammlungen an, zum Beispiel für deine Kinder, und schützt die App mit einem Passwort. Das Passwort brauchst du, wenn sie auf deinem eigenen Server läuft. Deine jetzige Sammlung gehört dann dem Hauptkonto und bleibt, wie sie ist.</p>
        <form class="kform" data-konto="haupt">
          <div class="field"><label for="k-name">Dein Name</label><input id="k-name" name="name" required maxlength="40" autocomplete="username"></div>
          <div class="field"><label for="k-pw">Passwort (leer lassen: keine Anmeldung, nur auf diesem Rechner)</label><input id="k-pw" name="passwort" type="password" minlength="8" autocomplete="new-password"></div>
          <div class="actions"><button class="btn primary" type="submit">Hauptkonto anlegen</button></div></form></section>${handySec}${backup}${quellenSec}${updateSec}${proxySec}${csvSec}${peHtml(pe)}`;
    return;
  }
  if (!haupt) {
    main.innerHTML = `${head('Dein Konto', `Angemeldet als ${esc(sess.anzeige)}. Du siehst nur deine eigene Sammlung.`)}
      <div class="todo" id="hauptsieht">${note(['info', 'Das Hauptkonto sieht deine Sammlung', TIP.hauptsieht])}</div>
      <section class="sec" aria-label="Passwort ändern"><h2>Passwort ändern</h2><form class="kform" data-konto="pw">${pwFelder(true)}
        <div class="actions"><button class="btn primary" type="submit">Passwort ändern</button></div></form></section>${quellenSec}${csvSec}`;
    return;
  }
  const {items} = await api('konten');
  const ich = items.find(k => k.rolle === 'haupt');
  main.innerHTML = `${head('Konten und Sicherung', `Jedes Konto hat seine eigene Sammlung. Du bist das Hauptkonto und siehst alle, Unterkonten mit Passwort sehen nur ihre eigene.`)}
    <section class="sec" aria-label="Sammlungen"><h2>Sammlungen <small>${items.length}</small></h2><div class="rows">${items.map(k => `
      <div class="row konto"><div class="min0"><div class="name">${esc(k.anzeige)}${k.name === sess.aktiv ? ' <span class="tag">offen</span>' : ''}</div>
        <div class="sub2">${k.rolle === 'haupt' ? 'Hauptkonto' : 'Unterkonto'}, ${k.pw ? 'mit Passwort' : k.rolle === 'haupt' ? 'ohne Passwort (keine Anmeldung)' : 'ohne Passwort (nur du verwaltest es)'}, ${karten(k.karten)}, ${eur0(k.wert)}</div></div>
        <div class="seg">${k.name === sess.aktiv ? '' : `<button class="btn small" type="button" data-open="${esc(k.name)}">Öffnen</button>`}
          ${k.rolle === 'haupt' ? '' : `<button class="btn small" type="button" data-pw="${esc(k.name)}" data-label="${esc(k.anzeige)}" data-has="${k.pw ? 1 : 0}">Passwort</button><button class="btn small danger" type="button" data-del="${esc(k.name)}" data-label="${esc(k.anzeige)}">${icon('trash', 'sm')}Entfernen</button>`}</div></div>`).join('')}</div></section>
    <section class="sec" aria-label="Unterkonto anlegen"><h2>Unterkonto anlegen</h2>
      <p class="lead">Ohne Passwort verwaltest nur du diese Sammlung, zum Beispiel die deines Kindes: oben rechts wechseln, Karten hinzufügen, fertig. Mit Passwort kann sich das Konto selbst anmelden und sieht nur seine eigene Sammlung.</p>
      <form class="kform" data-konto="add"><div class="field"><label for="u-name">Name</label><input id="u-name" name="name" required maxlength="40"></div>
        <div class="field"><label for="u-pw">Passwort (optional, mindestens 8 Zeichen)</label><input id="u-pw" name="passwort" type="password" minlength="8" autocomplete="new-password"></div>
        <p class="note-line" id="hauptsieht-anlegen">${esc(TIP.hauptsiehtanlegen)}</p>
        <div class="actions"><button class="btn primary" type="submit">${icon('plus')}Unterkonto anlegen</button></div></form></section>
    <section class="sec" aria-label="Anmeldung"><h2>${sess.modus === 'lokal' ? 'Anmeldung einschalten' : 'Dein Passwort'}</h2>
      <p class="lead">${sess.modus === 'lokal' ? 'Noch braucht die App kein Passwort, deshalb läuft sie nur auf diesem Rechner. Mit einem Passwort für dein Hauptkonto kannst du sie auch auf deinem eigenen Server betreiben (Anleitung in der README).' : 'Mit dem Passwort meldest du dich an, auf dem Server und von jedem Gerät.'}</p>
      <form class="kform" data-konto="pw">${pwFelder(ich?.pw, sess.modus === 'lokal' ? 'Passwort' : 'Neues Passwort')}
        <div class="actions"><button class="btn primary" type="submit">${sess.modus === 'lokal' ? 'Anmeldung einschalten' : 'Passwort ändern'}</button></div></form></section>
    ${handySec}${backup}${quellenSec}${updateSec}${proxySec}${csvSec}${peHtml(pe)}`;
}

function openPw(name, label, has) {
  dlg.className = 'modal';
  dlg.innerHTML = `<button class="x" data-close aria-label="Schließen">${icon('x')}</button><div class="box">
    <h2 id="dlg-title">Passwort für ${esc(label)}</h2>
    <p class="muted">${has ? 'Ein neues Passwort ersetzt das alte, ohne Passwort kann sich das Konto nicht mehr selbst anmelden.' : 'Mit Passwort kann sich das Konto selbst anmelden und sieht dann nur seine eigene Sammlung.'}</p>
    <form class="kform" data-konto="pw" data-name="${esc(name)}"><div class="field"><label for="d-pw">Neues Passwort (mindestens 8 Zeichen)</label><input id="d-pw" name="passwort" type="password" required minlength="8" autocomplete="new-password"></div>
      <div class="actions">${has ? `<button class="btn danger" type="button" data-nopw="${esc(name)}">Passwort entfernen</button>` : ''}<button class="btn ghost" type="button" data-close>Abbrechen</button><button class="btn primary" type="submit">Speichern</button></div></form></div>`;
  showDlg();
  $('#d-pw').focus();
  const weg = $('[data-nopw]');
  if (weg) weg.onclick = async () => { try { await post('konten', {aktion: 'passwort', name, passwort: null}); dlg.close(); flash(`${label}: ohne Passwort`); render(true); } catch (e) { flash('Fehler: ' + e.message); } };
}
async function delKonto(name, label) {
  if (!confirm(`Konto „${label}“ entfernen? Es kann sich dann nicht mehr anmelden und erscheint nicht mehr. Seine Sammlung bleibt als Datei auf dem Rechner liegen.`)) return;
  try { await post('konten', {aktion: 'del', name}); flash(`„${label}“ entfernt`); sess = await api('session'); whoUi(); render(true); } catch (e) { flash('Fehler: ' + e.message); }
}
async function kontoForm(f) {
  const d = Object.fromEntries(new FormData(f)), art = f.dataset.konto;
  if (!d.passwort) delete d.passwort;
  try {
    if (art === 'haupt' || art === 'add') {
      const r = await post('konten', {aktion: 'add', ...d});
      flash(art === 'haupt' ? `Hauptkonto angelegt${d.passwort ? ', Anmeldung ist an' : ''}` : `Unterkonto „${d.name}“ angelegt`);
      sess = art === 'haupt' ? r : await api('session');
    } else {
      const r = await post('konten', {aktion: 'passwort', name: f.dataset.name || '', ...d});
      if (r.modus) sess = r;  // eigenes Passwort: neue Sitzung
      if (dlg.open) dlg.close();
      flash('Passwort gespeichert');
    }
    whoUi(); render(true);
  } catch (e) { flash('Fehler: ' + e.message); }
}
async function undo() {
  const u = undoInfo;
  if (!u || !confirm(`Den letzten Import zurücknehmen?\n\n„${u.file}“ vom ${day(u.at)}: +${num(u.added)} / −${num(u.removed)} Karten${u.scope === '*' ? ' (ganze Sammlung)' : ` (${u.scope})`}. Danach ist alles wie vor diesem Import.`)) return;
  try { const r = await post('undo'); flash(`Zurückgenommen: ${r.file}`); render(true); } catch (e) { flash('Fehler: ' + e.message); }
}
let undoInfo = null;

document.addEventListener('submit', e => {
  const f = e.target;
  e.preventDefault();  // kein Formular verlässt die Seite (Filter, Anmeldung, Konten)
  if (f.id === 'login') login(f);
  else if (f.id === 'einr-code') einrCodeForm(f);
  else if (f.id === 'einr-neu') einrNeuForm(f);
  else if (f.id === 'einr-zip') einrZipForm(f);
  else if (f.dataset.konto) kontoForm(f);
  else if (f.dataset.ordner) ordnerForm(f);
  else if (f.dataset.wunsch) wunschForm(f);
  else if (f.dataset.notiz) notizForm(f);
  else if (f.dataset.spiel) spielForm(f, e.submitter);
  else if (f.dataset.gruppe) gruppeForm(f);
  else if (f.dataset.tisch) tischForm(f);
  else if (f.dataset.proxy) proxyForm(f);
  else if (f.dataset.erf) erfForm(f);
  else if (f.dataset.erfab) erfUebernehmen(f);
  else if (f.dataset.mess) messForm(f);
  else if (f.dataset.kopie) kopieForm(f);
  else if (f.dataset.umbenennen) umbenennenForm(f);
  else if (f.dataset.uebernehmen) uebernehmenForm(f);
  else if (f.dataset.buchen) buchenForm(f);
  else if (f.dataset.fertig) fertigForm(f);
});
document.addEventListener('change', async e => {
  const t = e.target;
  if (t.id === 'sammlung') return switchTo(t.value);
  if (t.id === 'pe-an') return peSetzen({an: t.checked});
  if (t.dataset.quelle) return quelleSetzen(t);
  if (t.dataset.proxyblatt) return proxySetzen(t);
  if (t.id === 'dgroup') { merke('mtg-deckgroup', t.value); return deckNeu(); }
  if (t.dataset.dbr) { try { await post('deck-bracket', {name: t.dataset.dbr, bracket: +t.value}); flash('Bracket gespeichert'); await render(true); } catch (err) { flash('Fehler: ' + err.message); } return; }
  if (t.dataset.log) { try { await post('deck-log', {id: +t.dataset.log, grund: t.value}); flash('Notiz gespeichert'); } catch (err) { flash('Fehler: ' + err.message); } }
});

// --- Wünsche (Phase 16): Wunschliste mit Zielpreis, ManaBox-Wunschlisten, was deinen Decks fehlt ----------------------------
const wunschRow = w => `<div class="row wunsch" data-oid="${esc(w.oracle_id)}"${peekAt(w.image, w.name, w.cm_low != null ? `ab ${eur(w.cm_low)}` : eur(w.price))}>${pic(small(w.image), '', 'thumb')}
  <div class="min0"><div class="name">${esc(w.name)}</div><div class="sub2">${[`${esc(w.set_code)} #${esc(w.number)}`, w.qty > 1 ? `${w.qty} gewünscht` : '', w.have ? `${w.have} im Besitz` : '',
    w.listen.length ? `ManaBox: ${w.listen.map(esc).join(', ')}` : '', esc(w.note || '')].filter(Boolean).join(', ')}</div>
    ${w.reached ? `<div><span class="chip">${icon('check', 'sm')}Zielpreis erreicht</span></div>` : ''}</div>
  <div class="price">${w.cm_low != null ? `ab ${eur(w.cm_low)}` : eur(w.price)}<div class="sub2">${w.max_eur != null ? `Ziel ${eur(w.max_eur)}` : 'kein Ziel'}</div></div>
  <div class="seg"><button class="btn small" type="button" data-wedit="${esc(w.oracle_id)}">Ziel</button>${w.quelle === 'app' ? `<button class="btn small ghost" type="button" data-wdel="${esc(w.oracle_id)}" aria-label="${esc(w.name)} von der Wunschliste nehmen">${icon('x', 'sm')}</button>` : ''}</div></div>`;
let wunschDaten = [];
async function viewWuensche() {
  const {items} = await api('wuensche');
  wunschDaten = items;
  const erreicht = items.filter(w => w.reached).length;
  main.innerHTML = `${head('Wünsche', 'Karten, die du haben willst, mit Zielpreis. Wunschlisten aus einer Scanner-App (zum Beispiel ManaBox) erscheinen hier von selbst.', items.length ? `<a class="btn" href="/api/wuensche.txt" download="wuensche.txt">${icon('text')}Textliste</a>${proxyAn() ? `<a class="btn" href="#/proxy?karten=${encodeURIComponent(items.map(w => w.name).join('\n'))}">${icon('printer')}Als Proxys</a>` : ''}` : '')}
    <section class="sec" aria-label="Karte wünschen"><form class="filters" data-wunsch="neu">
      <input name="name" required class="grow" placeholder="Kartenname, zum Beispiel Sol Ring" aria-label="Kartenname (englisch)" autocomplete="off">
      <label class="inl">Ziel <input name="max_eur" type="number" min="0" step="0.01" aria-label="Zielpreis in Euro"> €</label>
      <button class="btn primary" type="submit">${icon('plus')}Auf die Wunschliste</button></form></section>
    <section class="sec" aria-label="Wunschliste"><h2>Wunschliste ${info('wunsch', 'Zielpreis')} <small>${karten(items.reduce((n, w) => n + w.qty, 0))}${erreicht ? `, ${erreicht} mit erreichtem Zielpreis` : ''}</small></h2>
      ${items.length ? `<div class="rows">${items.map(wunschRow).join('')}</div>` : '<p class="muted">Noch leer. Füg oben eine Karte hinzu oder merk sie dir im Kartendetail (Klick auf eine Karte).</p>'}</section>
    <section class="sec" aria-label="Was deinen Decks fehlt" id="bedarf"><h2>Was deinen Decks fehlt ${info('bedarf', 'Was deinen Decks fehlt')}</h2><p class="muted">Wird geladen …</p></section>`;
  const box = $('#bedarf');
  try {
    const b = await api('bedarf');
    box.innerHTML = `<h2>Was deinen Decks fehlt ${info('bedarf', 'Was deinen Decks fehlt')} <small>${b.decks.length ? `${b.decks.length} Decks verglichen` : ''}</small></h2>${!b.decks.length ? '<p class="muted">Noch kein Deck mit Commander. Fertige Decks lädst du als Textliste hoch, neue baust du unter Decks.</p>'
      : !b.items.length ? '<p class="muted">Nichts: Was deine Decks laut EDHREC oft spielen, hast du frei oder schon drin.</p>'
      : `<div class="rows">${b.items.map(u => `<div class="row wunsch" data-oid="${esc(u.oracle_id)}"${peekAt(u.image, u.name, eur(u.price))}>${pic(small(u.image), '', 'thumb')}
        <div class="min0"><div class="name">${esc(u.name)}</div><div class="sub2" title="${esc(u.decks.join(', '))}">hilft ${u.n === 1 ? 'einem Deck' : `${u.n} Decks`}: ${esc(u.decks.join(', '))}${u.gc ? ', Game Changer' : ''}</div></div>
        <div class="price">${eur(u.price)}</div><div class="seg">${items.some(w => w.oracle_id === u.oracle_id) ? '<span class="muted small-print">gemerkt</span>' : `<button class="btn small" type="button" data-wadd="${esc(u.oracle_id)}">Merken</button>`}</div></div>`).join('')}</div>`}`;
  } catch (e) { if (!(e instanceof LoginNoetig)) box.innerHTML = `<h2>Was deinen Decks fehlt</h2>${ladeFehler(e)}`; }
}
async function wunschForm(f) {
  const d = Object.fromEntries(new FormData(f));
  try {
    await post('wunsch', {...d, oracle_id: f.dataset.oid || undefined, max_eur: d.max_eur === '' ? null : d.max_eur});
    if (dlg.open) dlg.close();
    flash(f.dataset.wunsch === 'neu' ? `${d.name} steht auf der Wunschliste` : 'Gespeichert');
    render(true);
  } catch (e) { flash('Fehler: ' + e.message); }
}
function openWunsch(oid) {
  const w = wunschDaten.find(x => x.oracle_id === oid);
  if (!w) return;
  dlg.className = 'modal';
  dlg.innerHTML = `<button class="x" data-close aria-label="Schließen">${icon('x')}</button><div class="box"><h2 id="dlg-title">${esc(w.name)}</h2>
    <p class="muted">Jetzt ${w.cm_low != null ? `ab ${eur(w.cm_low)} bei Cardmarket, ` : ''}Trend ${eur(w.price)}.${w.quelle === 'manabox' ? ' Steht auf deiner Wunschliste in ManaBox; Ziel und Notiz merkt sich die App.' : ''}</p>
    <form class="kform" data-wunsch="edit" data-oid="${esc(w.oracle_id)}">
      <div class="field"><label for="w-max">Zielpreis in Euro (leer: kein Ziel)</label><input id="w-max" name="max_eur" type="number" min="0" step="0.01" value="${w.max_eur ?? ''}"></div>
      <div class="field"><label for="w-qty">Wie viele</label><input id="w-qty" name="qty" type="number" min="1" max="99" value="${w.qty || 1}"></div>
      <div class="field"><label for="w-note">Notiz</label><input id="w-note" name="note" maxlength="300" value="${esc(w.note || '')}"></div>
      <div class="actions"><button class="btn ghost" type="button" data-close>Abbrechen</button><button class="btn primary" type="submit">Speichern</button></div></form></div>`;
  showDlg();
  $('#w-max').focus();
}
async function wunschSetzen(oid, weg) {
  try { await post('wunsch', weg ? {oracle_id: oid, weg: true} : {oracle_id: oid}); flash(weg ? 'Von der Wunschliste genommen' : 'Auf der Wunschliste'); }
  catch (e) { return flash('Fehler: ' + e.message); }
  if (dlg.open && dlg.className === 'sheet') return openCard(oid).then(() => { dirty = true; });
  render(true);
}

// --- Hilfe -------------------------------------------------------------------------------------------------------
function viewHelp() {
  const sec = [['add', 'Karten hinzufügen'], ['stapel', 'Die vier Stapel'], ['verkaufen', 'Verkaufen'], ['decks', 'Decks'], ['wuensche', 'Wünsche'], ['begriffe', 'Begriffe'], ['konten', 'Konten und Server'], ['daten', 'Deine Daten']];
  main.innerHTML = `${head('Hilfe', 'Alles Wichtige auf einer Seite. Die kleinen ?-Knöpfe in der App erklären einzelne Zahlen direkt dort.')}
    <div class="help"><nav aria-label="Abschnitte">${sec.map(([id, t]) => `<a href="#/help" data-jump="${id}">${t}</a>`).join('')}</nav><div class="doc">
    <section id="h-add"><h2>Karten hinzufügen</h2>
      <p>Oben rechts auf „Karten hinzufügen“ klicken oder eine Datei irgendwo auf die Seite ziehen. Die App erkennt das Format selbst und zeigt vor dem Übernehmen, was sich ändert.</p>
      <ul><li><b>Binder oder ganze Sammlung aus einer Scanner-App</b> (zum Beispiel ManaBox): als CSV exportieren. Ein Binder-Export ersetzt nur diesen Binder, ein Sammlungsexport alles.</li>
        <li><b>Fertige Decks:</b> als Text exportieren (aus ManaBox, Moxfield, Archidekt oder Arena) und hochladen oder einfügen. Sie erscheinen unter Decks, ihre Karten sind reserviert.</li>
        <li><b>Andere Apps:</b> CSVs aus Moxfield, Deckbox, Dragon Shield, TCGplayer, Archidekt oder Cardmarket. Die Karten werden über Scryfall erkannt.</li>
        <li><b>Per Kamera, ohne Export:</b> unter <a href="#/scan?modus=erfassen">Scannen, Erfassen</a> das Set wählen und die Karten nacheinander vor die Kamera halten. ${TIP.setlock} ${TIP.ohneset} ${TIP.titel} ${TIP.vorgaben} ${TIP.vollbild}</li></ul>
      <p><b>Scan-Liste.</b> ${TIP.scanliste} Ging beim Übernehmen etwas schief, holt „zurück auf die Liste“ die letzte Übernahme wieder auf die Liste, solange du an den Karten im Binder nichts geändert hast.</p>
      <p><b>Messbilder.</b> ${TIP.messbilder} ${TIP.messausloeser} Ansehen, zuordnen und löschen unter <a href="#/messbilder">Messbilder</a>.</p>
      <p><b>Scan-Binder.</b> ${TIP.scanbinder}</p>
      <p>Neu hochladen ist jederzeit sicher: Die App vergleicht mit dem letzten Stand. Würde mehr als ein Viertel deiner Karten verschwinden, fragt sie nach. Heißt die Datei anders als dein Binder (zum Beispiel „packs neu.csv“), gleicht die App den Inhalt ab: Steckt ein vorhandener Binder fast ganz darin, gilt die Datei als sein neuer Stand, und nur die neuen Karten kommen dazu.</p>
      <p><b>Suchen.</b> Im Suchfeld unter Karten gehen Name und Suchbegriffe wie bei Scryfall, zum Beispiel <code>t:creature id:bg fn:graveyard mv&lt;=3</code> oder <code>(r:m or eur&gt;=10) lang:de</code>. Die Suchhilfe darunter zeigt alle Begriffe, ein Klick fügt sie ein. Aktive Filter stehen als Marken über den Karten, ein Klick nimmt sie weg. Dieselbe Suche gibt es in der Kommandozeile: <code>mtg suche "…"</code>.</p>
      <p><b>Mit lokalem Sprachmodell (optional).</b> Läuft auf deinem Rechner oder Server <a href="https://ollama.com" target="_blank" rel="noopener noreferrer">Ollama</a> mit den Modellen <code>qwen3:4b-instruct</code> und <code>nomic-embed-text</code>, kannst du im Suchfeld eine Frage stellen („Als Frage“) und siehst im Kartendetail ähnliche Karten deiner Sammlung. ${TIP.frage} Ohne Ollama fehlen nur diese zwei Knöpfe.</p>
      <p><b>Ist eine Serie schon drin?</b> Unter Serien stehen alle Serien in deinem Bestand mit Erscheinungsdatum, Karten, Wert und wann zuletzt etwas dazukam. Ein Klick zeigt ihre Karten nach Sammlernummer, so wie sie im Binder liegen.</p></section>
    <section id="h-stapel"><h2>Die vier Stapel</h2>
      <dl><dt><span class="dot d-deck"></span>Deck</dt><dd>${TIP.deck}</dd><dt><span class="dot d-keep"></span>Behalten</dt><dd>${TIP.keep}</dd>
        <dt><span class="dot d-sell"></span>Verkaufen</dt><dd>${TIP.sell}</dd><dt><span class="dot d-bulk"></span>Bulk</dt><dd>${TIP.bulkstack}</dd></dl>
      <p>Die Regeln stellst du unter Verkaufen ein. Für eine einzelne Karte entscheidest du im Kartendetail (Klick auf die Karte): behalten, verkaufen oder Bulk.</p>
      <p><b>Karte für Karte.</b> Unter Sortieren zeigt „Karte für Karte“ jede Karte eines Binders groß mit dem Stapel, auf den sie gehört. Mit der Leertaste (oder „Weiter“) kommt die nächste, die Pfeiltaste nach links geht einen Schritt zurück, Esc beendet. Die Zähler unten zeigen, wie hoch die Stapel auf dem Tisch schon sind.</p></section>
    <section id="h-verkaufen"><h2>Verkaufen</h2>
      <ol><li>Unter Verkaufen die Liste für den Ankauf herunterladen (Excel). Bei einem Ankäufer wie KEEPSEVEN schickst du das Formular des Sammlungsankaufs ab und lädst die Liste über den Link in der Bestätigungs-Mail hoch (er kauft nur englische und deutsche Karten). Oder einzelne Karten über deren Kartensuche anbieten.</li>
        <li>Verkaufte Karten in deiner Scanner-App löschen (zum Beispiel ManaBox).</li><li>Neuen Export hier ablegen. Karten von der Verkaufsliste, die fehlen, bucht die App als verkauft und zeigt die Summe.</li></ol>
      <p>Die ManaBox-CSV lässt sich auch in ManaBox selbst als Liste importieren, die Textliste passt in die meisten Eingabefelder für Kartenlisten.</p>
      <p><b>Preisbewegung.</b> Bei jeder Preis-Aktualisierung merkt sich die App den Preis jeder Karte. Nach ein paar Tagen zeigt sie unter Verkaufen und auf der Übersicht, was seit gut zwei Wochen um mindestens 15 % gestiegen oder gefallen ist (Karten ab 1 €). Steigt eine Karte, von der du Kopien zum Verkaufen hast, meldet das die Übersicht.</p>
      <p><b>Kaufpreis und Wert.</b> Scanner-Apps wie ManaBox exportieren den Kaufpreis jeder Karte mit. Die Übersicht zeigt unter „Seit dem Kauf“, was die Karten mit Kaufpreis heute mehr (oder weniger) wert sind, das Kartendetail den Kaufpreis je Kopie. „Wert im Verlauf“ zeigt den Wert deiner Sammlung an jedem Tag, an dem die App lief.</p>
      <p><b>Cardmarket.</b> ${TIP.cardmarket} Die App holt die Liste einmal am Tag (sie ist groß, etwa 26 MB).</p>
      <p><b>Cardmarket und Ankauf.</b> Neben jedem Preis steht der niedrigste Angebotspreis bei Cardmarket („ab“). Über der Liste steht, was nach 5 % Provision bleibt. ${TIP.sprachen} Im Reiter Bulk rechnet die App als Beispiel aus, was KEEPSEVEN laut seiner Bulk-Preisliste zahlen würde.</p>
      <p><b>Verkauft je Jahr.</b> ${TIP.meldegrenze}</p>
      <p><b>Recherche.</b> Mit Claude Code auf dem Desktop (Skill mtg-recherche) entstehen Dossiers zu deinen Commandern und ein Markt-Radar aus Foren und Preisseiten. Das Dossier steht dann beim Deck, Treffer aus dem Radar bei deinen Karten unter Neuigkeiten. Beides sind Hinweise mit Quelle, keine Anlageberatung.</p>
      <p><b>Drucken.</b> Unter „Drucken“ (Link im Fuß) gibt es Trennkarten in Kartenbreite (63 × 95 mm, neun je Seite) und Etiketten (70 × 37 mm, 24 je Bogen) für Serien, Binder und Decks. ${proxyAn() ? 'Das Proxy-Blatt druckt Karten zum Ausprobieren in Originalgröße, jede mit „Playtest“, erreichbar auch aus den Upgrade-Vorschlägen eines Decks und aus den Wünschen. ' : 'Das Proxy-Blatt ist aus; das Hauptkonto kann es unter „Konten und Sicherung“ einschalten. '}Beim Drucken die Skalierung auf 100 % lassen. Zu jedem Deck zeigt „Zerlegen: wohin?“, auf welchen Stapel jede Karte zurückgeht.</p>
      <p><b>Spiele.</b> Nach jeder Runde Deck wählen und Gewonnen oder Nicht gewonnen klicken, mehr braucht es nicht (Tisch, Züge und Notiz sind freiwillig). Die Siegquote steht ab fünf Spielen, Decks, die seit zwei Monaten ruhen, nennt die App als Kandidaten zum Zerlegen. In der Spielgruppe trägst du die Decks deiner Mitspieler mit Bracket ein und lässt dir zeigen, welches deiner Decks heute passt. Salt zeigt, wie viele der von EDHREC als besonders ärgerlich gewählten Karten in einem Deck stecken.</p>
      <p><b>Sammler.</b> Im Kartendetail bekommt jede Kopie einen Ort (Kiste, Binder), „verliehen an“ und eine Notiz. Das steht getrennt vom importierten Bestand und bleibt bei jedem neuen Import erhalten. Suche danach mit <code>ort:kiste</code> oder <code>is:verliehen</code>. Unter Serien siehst du, wie viel von jedem Set dir fehlt, ein Klick zeigt das Set als Binder mit neun Karten je Seite. Dazu gibt es den Rückblick auf dein Sammeljahr und einen Wert-Bericht zum Drucken (für Versicherung oder Nachlass), beide über die Übersicht.</p>
      <p><b>Wächter.</b> Bei jeder Preis-Aktualisierung vergleicht die App, ob eine deiner Karten gebannt, wieder erlaubt oder zum Game Changer wurde, und meldet das auf der Übersicht mit den betroffenen Decks. Einmal am Tag schaut sie in neue und angekündigte Sets: Erscheint eine deiner Karten ab 5 € neu, steht „Reprint“ in der Verkaufsliste. Im Kartendetail stehen die offiziellen Rulings.</p>
      <p><b>Gefragte Karten.</b> ${TIP.want} In der Verkaufsliste sind sie markiert, „Abwählen“ nimmt alle auf einmal aus der Liste.</p></section>
    <section id="h-decks"><h2>Decks</h2>
      <p>Das Ranking zeigt für jede legendäre Kreatur, die du besitzt, wie viel von einem typischen Deck du schon hast. „Bauen“ stellt 100 Karten zusammen (Ramp, Kartenziehen, Removal, Wipes, 37 Länder), nur aus freien Karten. Erst „Deck speichern“ reserviert sie. Fertige oder gespeicherte Decks werden nie auseinandergenommen.</p>
      <p><b>Sortierung.</b> ${TIP.modes}</p>
      <p><b>Was dir fehlt.</b> Unter dem Ranking listet die App Karten, die auf den Listen mehrerer deiner zehn besten Commander stehen und die du nicht frei hast. Wer sie kauft, hilft mehreren Decks auf einmal.</p>
      <p><b>Mana.</b> Auf jeder Deckseite zeigt die App die Manakurve und, ob die Länder zu den Farbsymbolen der Zauber passen. ${TIP.sources}</p>
      <p><b>Combos in deiner Sammlung.</b> ${TIP.combos}</p>
      <p><b>Bracket prüfen.</b> ${TIP.bracketcheck} Ganz unten auf der Decks-Seite fügst du eine fremde Liste ein, auf jeder Deckseite prüfst du das Deck selbst.</p>
      <p><b>Ansicht.</b> Über den Karten eines Decks wählst du Bilder, Stapel (wie auf dem Tisch) oder eine Liste, gruppiert nach Rolle, Kartentyp oder Manawert. Die Wahl merkt sich der Browser.</p>
      <p><b>Starthand.</b> ${TIP.hand} „Starthand ziehen“ mischt das Deck und zeigt 7 Karten zum Ausprobieren.</p>
      <p><b>Verbessern.</b> ${TIP.improve}</p>
      <p><b>Zusammensuchen.</b> Für ein gespeichertes Deck zeigt die App, aus welchem Binder du welche Kopie nimmst, zum Abhaken und Drucken. <b>Änderungen</b> an fertigen Decks erkennt sie beim erneuten Hochladen der Liste; zu jeder kannst du notieren, warum.</p>
      <p><b>Thema.</b> ${TIP.theme} Karten ohne EDHREC-Angabe füllen die letzten Plätze, und zwar zuerst die, deren Kartentext zum Thema passt. Über „Thema“ im Deck wählst du ein anderes Thema oder die allgemeine Liste.</p></section>
    <section id="h-wuensche"><h2>Wünsche</h2>
      <p>Unter Wünsche führst du eine Wunschliste: Karte eintragen oder im Kartendetail „Auf die Wunschliste“, auf Wunsch mit Zielpreis. ${TIP.wunsch} Wunschlisten aus einer Scanner-App (zum Beispiel ManaBox, im Sammlungsexport) erscheinen von selbst, ihr Ziel setzt du hier.</p>
      <p><b>Was deinen Decks fehlt.</b> ${TIP.bedarf} „Merken“ setzt die Karte auf die Wunschliste.</p></section>
    <section id="h-begriffe"><h2>Begriffe</h2><dl>
      <dt>Abdeckung</dt><dd>${TIP.coverage}</dd><dt>Karten (79 / 251)</dt><dd>${TIP.have}</dd><dt>EDHREC-Decks</dt><dd>${TIP.decks}</dd>
      <dt>Bracket</dt><dd>${TIP.bracket}</dd><dt>Game Changer</dt><dd>${TIP.gc}</dd><dt>Ø Manawert</dt><dd>${TIP.cmc}</dd><dt>Staple</dt><dd>${TIP.staple}</dd>
      <dt>Bulk</dt><dd>${TIP.bulk}</dd><dt>Preis</dt><dd>${TIP.value}</dd></dl></section>
    <section id="h-konten"><h2>Konten und Server</h2>
      <p>Unter <a href="#/konten">Konten und Sicherung</a> (ganz unten auf jeder Seite) legst du ein Hauptkonto an. Danach kannst du weitere, getrennte Sammlungen anlegen, zum Beispiel für deine Kinder, und oben rechts zwischen ihnen wechseln. Jede Sammlung hat ihre eigenen Karten, Decks und Regeln.</p>
      <ul><li><b>Ohne Passwort</b> läuft die App wie bisher nur auf deinem Rechner.</li>
        <li><b>Mit Passwort</b> fürs Hauptkonto kannst du sie auf deinem eigenen Server betreiben und von jedem Gerät aus öffnen, auch wenn dein Rechner aus ist. Wie das geht, steht in der README.</li>
        <li>Ein Unterkonto <b>mit Passwort</b> meldet sich selbst an und sieht nur seine eigene Sammlung, eins <b>ohne Passwort</b> verwaltest nur du.</li>
        <li>Das <b>Hauptkonto</b> sieht und ändert jede Sammlung der Installation, auch die eines Unterkontos mit eigenem Passwort.</li></ul>
      <p><b>Rückgängig.</b> Hat ein Import etwas falsch gemacht, nimmt „rückgängig“ auf der Übersicht (bei „Zuletzt hinzugefügt“) den letzten Import zurück.</p>
      <p><b>Am Handy.</b> Öffnest du die App über https (Tailscale oder deine Domain), lässt sie sich installieren: im Browsermenü „App installieren“ oder „Zum Startbildschirm“. Dann startet sie im Vollbild wie eine App, auf Android bietet langes Drücken auf das Symbol „Karten erfassen“ an. Beim Scannen bleibt der Bildschirm an, bei jeder erkannten Karte ertönt ein kurzer Ton, und wo die Kamera es kann, gibt es eine Taschenlampe.</p>
      <p><b>Posteingang.</b> ${TIP.posteingang} Einschalten unter <a href="#/konten">Konten und Sicherung</a>.</p>
      <p><b>Quellen.</b> ${TIP.quellen} Was jede Quelle erfährt und wie oft sie gefragt wird, steht auf der Seite <a href="#/quellen">Quellen</a>. EDHREC ist in einer neuen Installation aus: Ohne EDHREC gibt es kein Commander-Ranking und keinen Deckbau, alles andere läuft.</p></section>
    <section id="h-daten"><h2>Deine Daten</h2><p>Alles liegt im Ordner <code>data</code> auf deinem Rechner bzw. Server, jede hochgeladene Datei zusätzlich unter <code>data/imports</code>. Solange die App läuft, frischt sie einmal am Tag die Preise auf und legt eine Sicherung unter <code>data/sicherungen</code> an. Ohne Passwort ist sie nur von diesem Rechner aus erreichbar.</p>
      <p><b>Sicherung außer Haus.</b> ${TIP.aussen}</p>
      <p>Hell oder dunkel stellst du ganz unten auf jeder Seite unter „Darstellung“ ein.</p>
      <p><b>Rechtliches.</b> ${APP} steht unter der MIT-Lizenz (Datei <code>LICENSE</code>); die Lizenzen der Schrift, der Icons und der Datenquellen stehen in <code>LIZENZEN.md</code>. Die App ist ein inoffizielles Fan-Projekt und kein Produkt von Wizards of the Coast. Der Hinweis dazu im Wortlaut der Fan Content Policy: <span lang="en">${esc($('footer .hinweis').textContent)}</span></p></section>
    </div></div>`;
  main.onclick = e => { const a = e.target.closest('[data-jump]'); if (a) { e.preventDefault(); $('#h-' + a.dataset.jump).scrollIntoView(); } };
}

function viewMissing() {
  main.innerHTML = `${head('Diese Seite gibt es nicht', 'Vielleicht ein alter Link oder ein Tippfehler in der Adresse.')}
    <p><a class="btn primary" href="#/">${icon('left')}Zur Übersicht</a></p>`;
}

// --- Karten-Detail als Sheet von rechts: Plan und Entscheidung, die Liste dahinter bleibt sichtbar --------------
let dirty = false;
async function openCard(oid) {
  const k = await api('card/' + encodeURIComponent(oid));
  const total = k.owned.reduce((n, o) => n + o.qty, 0), st = k.status?.status || '';
  const L = {scryfall: 'Scryfall', cardmarket: 'Cardmarket', edhrec: 'EDHREC'};
  dlg.className = 'sheet';
  dlg.innerHTML = `<button class="x" data-close aria-label="Schließen">${icon('x')}</button><div class="detail" data-oid-box="${esc(oid)}">
    <div class="dtop"><div class="img">${pic(k.image, k.name)}
      <div class="links">${Object.entries(k.links || {}).map(([n, u]) => `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${L[n] || n}${icon('external', 'sm')}<span class="sr-only"> (neues Fenster)</span></a>`).join('')}</div></div>
      <div class="min0"><h2 id="dlg-title">${esc(k.name)} ${k.mana_cost ? mana(k.mana_cost) : ''}</h2>
        <div class="muted">${esc(k.type)}${k.set_name ? ', ' + esc(k.set_name) : ''}, ${esc(k.rarity)}${k.rank ? `, EDHREC-Rang ${num(k.rank)}` : ''}</div>
        ${k.text ? `<div class="oracle">${esc(k.text)}</div>` : ''}
        <div class="chips">${k.legal ? '<span class="chip">Commander-legal</span>' : '<span class="chip warn">nicht Commander-legal</span>'}${k.game_changer ? `<span class="chip">Game Changer ${info('gc', 'Game Changer')}</span>` : ''}${k.reserved ? `<span class="chip">Reserved List ${info('reserved', 'Reserved List')}</span>` : ''}${(k.reprints || []).map(r => `<span class="chip warn">Reprint: ${esc(r)} ${info('reprint', 'Reprint')}</span>`).join('')}
          <span class="chip">Preis ${eur(k.price)}</span>${k.price_foil != null ? `<span class="chip">Foil ${eur(k.price_foil)}</span>` : ''}</div></div></div>
    <div class="dbody">
      <section><h3>Plan für deine Kopien</h3><div class="chips big">${stackChips(k.stacks, true) || '<span class="muted">nicht im Bestand</span>'}</div>
        <div class="seg" role="group" aria-label="Entscheidung für die Kopien ohne Deck">${[['', 'Automatisch'], ['keep', 'Alle behalten'], ['sell', 'Verkaufen'], ['bulk', 'Bulk']].map(([v, l]) => `<button type="button" class="btn small" data-st="${v}" aria-pressed="${st === v}">${l}</button>`).join('')}
          ${st === 'sell' || st === 'bulk' ? `<label class="inl">davon behalten <input type="number" id="keep" class="tight" min="0" value="${k.status.keep}"></label>` : ''}</div>
        <p class="note-line">Automatisch heißt: ${esc(TIP.keep)}</p></section>
      <section><h3>Besitz: ${total} insgesamt, ${k.available} frei</h3>
        <table class="tbl">${k.owned.map((o, i) => `<tr><td>${o.qty}×</td><td>${esc(o.set_code)} #${esc(o.number)}${o.foil !== 'normal' ? ', ' + esc(o.foil) : ''}</td><td>${esc(LANG[o.language] || o.language)}, ${esc(COND[o.condition] || o.condition)}</td><td class="muted">${esc(o.binder)}${o.scan ? ` <button class="link small-print" type="button" data-kopie="${i}">ändern</button>` : ''}</td><td class="rt">${eur(o.price)}${o.paid != null ? `<div class="sub2">bezahlt ${eur(o.paid)}</div>` : ''}</td></tr>
          <tr class="notiz-tr"><td></td><td colspan="4">${notizUi(o, i)}</td></tr>`).join('')}</table>
        ${cmLine(k.owned.find(o => o.cm))}</section>
      <section id="rulings" hidden><h3>Rulings ${info('rulings', 'Rulings')}</h3><ul class="rulings" id="rulings-liste"></ul></section>
      <section id="aehnlich" hidden><h3>Ähnlich in deiner Sammlung ${info('aehnlich', 'Ähnlich in deiner Sammlung')}</h3><div class="grid small" id="aehnlich-liste"></div></section>
      ${k.legal && k.available && (/Legendary/.test(k.type) && /Creature/.test(k.type) || /can be your commander/.test(k.text || '')) ? `<section><h3>Als Commander</h3>
        <p class="lead">Die App baut ein ganzes Deck mit 100 Karten um diese Karte, nur aus deinen freien Karten ${info('free', 'frei')}. Gespeichert wird erst auf deinen Klick.</p>
        <a class="btn small primary" href="#/decks?build=${esc(oid)}" data-close>${icon('crown', 'sm')}Deck um diesen Commander bauen</a></section>` : ''}
      <section><h3>Wunschliste</h3>${k.wunsch ? `<p class="lead">Steht auf deiner Wunschliste${k.wunsch.max_eur != null ? `, Ziel ${eur(k.wunsch.max_eur)}` : ''}${k.wunsch.qty > 1 ? `, ${k.wunsch.qty} Stück` : ''}. <button class="link" type="button" data-wdel="${esc(oid)}">Entfernen</button></p>`
        : `<button class="btn small" type="button" data-wadd="${esc(oid)}">${icon('plus', 'sm')}Auf die Wunschliste</button>`}</section>
      ${k.want?.length ? `<section><h3>Gefragt bei deinen besten Commandern ${info('want', 'Konfliktkarte')}</h3><div class="chips big">${k.want.map(n => `<span class="chip">${esc(n)}</span>`).join('')}</div></section>` : ''}
      ${k.decks.length ? `<section><h3>In Decks</h3><div class="chips big">${k.decks.map(d => `<a class="chip s-deck" href="${d.binder ? `#/decks?binder=${encodeURIComponent(d.binder)}` : `#/decks?id=${d.id}`}" data-close>${esc(d.name)}</a>`).join('')}</div></section>` : ''}
    </div></div>`;
  kopien = k.owned; kopieKarte = {oid, name: k.name};
  showDlg();
  aehnlichUi(oid); rulingsUi(oid);
}
let kopien = [], kopieKarte = null;
async function kopieDialog(i) {  // Kopie eines Scan-Binders (Phase 26): Menge, oder umziehen in anderen Binder, Foil, Sprache, Zustand
  const o = kopien[i];
  let scanB = [];
  try { scanB = (await api('binders')).items.filter(b => b.type === 'scan').map(b => b.name); } catch { /* ohne Vorschläge */ }
  dlg.className = 'modal';
  dlg.innerHTML = `<button class="x" data-close aria-label="Schließen">${icon('x')}</button><div class="box"><h2 id="dlg-title">${esc(kopieKarte.name)}</h2>
    <p class="muted">${o.qty}× ${esc([`${o.set_code} #${o.number}`, o.foil !== 'normal' && FOIL[o.foil], LANG[o.language] || o.language, COND[o.condition] || o.condition].filter(Boolean).join(', '))} in „${esc(o.binder)}“. ${esc(TIP.kopie)}</p>
    <form class="kform" data-kopie="${i}">
      <div class="field"><label for="k-binder">Binder</label><input id="k-binder" name="binder" list="k-binderliste" maxlength="80" value="${esc(o.binder)}" autocomplete="off"></div>
      <datalist id="k-binderliste">${scanB.map(b => `<option value="${esc(b)}">`).join('')}</datalist>
      <div class="field"><label for="k-foil">Foil</label><select id="k-foil" name="foil">${optionen(FOIL, o.foil)}</select></div>
      <div class="field"><label for="k-lang">Sprache</label><select id="k-lang" name="language">${optionen(LANG, o.language)}</select></div>
      <div class="field"><label for="k-cond">Zustand</label><select id="k-cond" name="condition">${optionen(COND, o.condition)}</select></div>
      <div class="field"><label for="k-qty" id="k-qtyl">Menge</label><input id="k-qty" name="qty" type="number" min="0" max="9999" value="${o.qty}" required></div>
      <div class="actions"><button class="btn danger" type="button" id="k-weg">${icon('trash', 'sm')}Löschen</button><button class="btn ghost" type="button" data-close>Abbrechen</button><button class="btn primary" type="submit">Speichern</button></div></form></div>`;
  showDlg();
  const f = $('form[data-kopie]', dlg);
  f.addEventListener('input', () => {  // gleiche Zeile: neue Menge; anderes Ziel: wie viele davon umziehen
    const um = ['binder', 'foil', 'language', 'condition'].some(k => f.elements[k].value.trim() !== o[k]);
    $('#k-qtyl').textContent = um ? `Wie viele davon (von ${o.qty})` : 'Menge';
    f.elements.qty.max = um ? o.qty : 9999;
    if (um && +f.elements.qty.value > o.qty) f.elements.qty.value = o.qty;
  });
  $('#k-weg').onclick = () => kopieSenden(o, {qty: 0});
}
async function kopieForm(f) {
  const d = Object.fromEntries(new FormData(f));
  return kopieSenden(kopien[+f.dataset.kopie], {qty: +d.qty, binder: d.binder.trim(), foil: d.foil, condition: d.condition, language: d.language});
}
async function kopieSenden(o, neu) {
  const gleich = ['binder', 'foil', 'language', 'condition'].every(k => neu[k] === undefined || neu[k] === o[k]);
  if (gleich && neu.qty === 0 && !confirm(`${o.qty}× ${kopieKarte.name} aus „${o.binder}“ löschen? Ort und Notiz dieser Kopie gehen mit. Verkauft? Dann besser unter Verkaufen „Als verkauft buchen“.`)) return;
  try { await post('kopie', {key: [o.binder, o.scryfall_id, o.foil, o.condition, o.language], ...neu}); flash('Gespeichert'); dirty = true; await openCard(kopieKarte.oid); }
  catch (e) { if (!(e instanceof LoginNoetig)) flash('Fehler: ' + e.message); }
}
const notizUi = (o, i) => {
  const da = [o.ort && `liegt in ${o.ort}`, o.verliehen && `verliehen an ${o.verliehen}`, o.notiz].filter(Boolean);
  return `<details class="notiz"${o.verliehen ? ' open' : ''}><summary>${da.length ? esc(da.join(', ')) : 'Ort, Verleih, Notiz'}</summary>
    <form class="notizform" data-notiz="${i}"><input name="ort" maxlength="200" placeholder="Ort, zum Beispiel Kiste 3" aria-label="Lagerort" value="${esc(o.ort || '')}">
      <input name="verliehen" maxlength="200" placeholder="verliehen an" aria-label="Verliehen an" value="${esc(o.verliehen || '')}">
      <input name="notiz" maxlength="200" placeholder="Notiz" aria-label="Notiz" value="${esc(o.notiz || '')}"><button class="btn small" type="submit">Speichern</button></form></details>`;
};
async function notizForm(f) {
  const o = kopien[+f.dataset.notiz], oid = f.closest('[data-oid-box]').dataset.oidBox, d = Object.fromEntries(new FormData(f));
  try { await post('notiz', {key: [o.binder, o.scryfall_id, o.foil, o.condition, o.language], ...d}); flash('Gespeichert'); dirty = true; await openCard(oid); }
  catch (e) { flash('Fehler: ' + e.message); }
}
async function rulingsUi(oid) {  // Scryfall, 30 Tage gemerkt; ohne Netz bleibt der Abschnitt einfach aus
  try {
    const r = await api('rulings?oracle_id=' + encodeURIComponent(oid));
    const box = $('#rulings');
    if (!box || box.closest('[data-oid-box]')?.dataset.oidBox !== oid || !r.items.length) return;
    $('#rulings-liste').innerHTML = r.items.map(x => `<li><span class="muted small-print">${esc(x.date ? new Date(x.date + 'T12:00:00').toLocaleDateString('de-DE') : '')}</span> ${esc(x.text)}</li>`).join('');
    box.hidden = false;
  } catch { /* kein Netz */ }
}
async function aehnlichUi(oid) {  // nur mit lokalem Ollama und berechneten Embeddings (PLAN E15)
  const lm = await llmInfo();
  if (!lm.embed || !lm.vektoren) return;
  try {
    const r = await api('aehnlich?oracle_id=' + encodeURIComponent(oid));
    const box = $('#aehnlich');
    if (!box || box.closest('[data-oid-box]')?.dataset.oidBox !== oid || !r.items?.length) return;
    $('#aehnlich-liste').innerHTML = r.items.slice(0, 8).map(x => `<a class="card" href="#" data-oid="${esc(x.oracle_id)}"${peekAt(x.image, x.name, eur(x.price))}>${pic(small(x.image), x.name)}<span class="cap"><span class="p">${eur(x.price)}</span></span></a>`).join('');
    box.hidden = false;
  } catch { /* Ollama weg: Abschnitt bleibt aus */ }
}
const cmLine = o => !o ? '' : `<p class="note-line">Cardmarket ${info('cardmarket', 'Cardmarket')}: ab ${eur(o.cm.low)}, Trend ${eur(o.cm.trend)}, Schnitt 30 Tage ${eur(o.cm.avg30)} (${o.foil !== 'normal' ? 'Foil, ' : ''}${esc(o.set_code)}, Stand ${day(o.cm.day)})</p>`;
const setStatus = async (oid, status, keep) => {
  try { await post('status', {oracle_id: oid, status: status || null, keep}); dirty = true; await openCard(oid); }
  catch (e) { flash('Fehler: ' + e.message); }
};
const showDlg = () => { hidePeek(); if (!dlg.open) dlg.showModal(); };

// --- Beispielsammlung (Phase 47, PLAN E33) -------------------------------------------------------------------------
// In einer leeren Sammlung bietet die Startseite „Beispielsammlung ansehen“ an (nur dort, der Server prüft es auch). Solange das Beispiel liegt, steht oben
// auf jeder Ansicht die Leiste mit „Beispiel entfernen“; der erste echte Import entfernt es von selbst und nennt das in der Vorschau.
async function beispielLeiste() {
  const box = $('#beispiel-leiste');
  let b;
  try { b = await api('beispiel'); } catch { return; }  // ohne Antwort bleibt die Leiste, wie sie ist
  box.hidden = !b.da;
  box.innerHTML = b.da ? note(['info', 'Das ist die Beispielsammlung', `${karten(b.karten)} aus einem Binder und einem Deck, zum Ausprobieren. Sie verschwindet auch von selbst, sobald du deine erste echte Datei importierst.`,
    `<button class="btn" type="button" data-beispiel="entfernen">${icon('trash')}Beispiel entfernen</button>`]) : '';
}
async function beispielAktion(aktion, knopf) {
  if (aktion === 'entfernen' && !confirm('Die Beispielsammlung entfernen? Sie verschwindet mit allem, was dazugehört. Andere Karten bleiben, wie sie sind.')) return;
  const vorher = knopf.innerHTML;
  knopf.disabled = true; knopf.textContent = aktion === 'laden' ? 'Lädt die Kartendaten …' : 'Wird entfernt …';
  try {
    const r = await post('beispiel', {aktion});
    flash(aktion === 'laden' ? `Beispielsammlung geladen: ${karten(r.karten)} und ein Deck mit ${karten(r.deck)}` : `Beispielsammlung entfernt (${karten(r.entfernt)})`);
    jobs = {}; render(true);
  } catch (e) { flash('Fehler: ' + e.message); knopf.disabled = false; knopf.innerHTML = vorher; }
}

// --- Import: Datei oder eingefügte Liste, Vorschau mit Ziel, dann übernehmen --------------------------------------
let imports = [], binderNames = [];
const KIND = {manabox: 'ManaBox-CSV', csv: 'CSV einer anderen App', deck: 'Deckliste'};

function openChooser(paste) {
  dlg.className = 'modal';
  dlg.innerHTML = `<button class="x" data-close aria-label="Schließen">${icon('x')}</button><div class="box">
    <h2 id="dlg-title">Karten hinzufügen</h2>
    <div class="dropzone" data-dropzone>${icon('upload', 'lg')}<b>Datei hier ablegen</b><span class="muted">${FORMATS}</span><button class="btn primary" type="button" data-pick>${icon('upload')}Datei auswählen</button></div>
    <div class="field"><label for="pastebox">Oder eine Liste einfügen, zum Beispiel ein Deck aus ManaBox, Moxfield oder Archidekt</label>
      <textarea id="pastebox" spellcheck="false" placeholder="// COMMANDER&#10;1 Atraxa, Praetors' Voice (C16) 28&#10;&#10;1 Sol Ring (C21) 263"></textarea></div>
    <div class="actions"><span class="left muted hint">Vor dem Speichern siehst du immer erst, was sich ändert.</span><button class="btn ghost" type="button" data-close>Abbrechen</button><button class="btn" type="button" id="pastego">${icon('paste')}Liste prüfen</button></div>
  </div>`;
  showDlg();
  $('#pastego').onclick = () => {
    const t = $('#pastebox').value.trim();
    if (!t) { $('#pastebox').focus(); return; }
    importFiles([new File([t + '\n'], 'Eingefügte Liste.txt', {type: 'text/plain'})]);
  };
  if (paste) $('#pastebox').focus();
}

const upload = (it, dry) => {
  const q = new URLSearchParams();
  if (dry) q.set('dry', '1');
  for (const k of ['binder', 'commander']) if (it.q[k]) q.set(k, it.q[k]);
  if (!dry && it.force) q.set('force', '1');
  return api('import?' + q, {method: 'POST', headers: {'X-Filename': encodeURIComponent(it.file.name)}, body: it.file});
};

async function importFiles(files) {
  hidePeek();
  imports = files.map(file => ({file, q: {}, busy: true}));
  try { binderNames = (await api('binders')).items.map(b => b.name); } catch { binderNames = []; }
  renderImports();
  showDlg();
  await Promise.all(imports.map(check));
}

async function check(it) {
  it.busy = true; renderImports();
  try { it.r = await upload(it, true); it.error = null; } catch (e) { it.r = null; it.error = e.message; }
  it.busy = false; renderImports();
}

function impCard(it, i) {
  const r = it.r;
  if (it.busy) return `<div class="imp"><div class="top2"><span class="file">${esc(it.file.name)}</span><span class="muted">wird geprüft …</span></div><div class="progress busy"><span></span></div></div>`;
  if (it.error) return `<div class="imp bad"><div class="top2"><span class="file">${esc(it.file.name)}</span></div><div>Das ging nicht: ${esc(it.error)}</div></div>`;
  if (it.done) return `<div class="imp"><div class="top2"><span class="file">${esc(it.file.name)}</span><span class="tag">${esc(KIND[r.format])}</span></div><div class="ok">${icon('check')}${esc(it.done)}</div></div>`;
  const full = r.scope === '*', deck = r.format === 'deck';
  const ziel = full ? '<div class="field"><span>Ziel</span><b>Ganze Sammlung (alle Binder)</b></div>'
    : `<label class="field"><span>${deck ? (r.scope === 'Eingefügte Liste' ? 'Name des Decks (bitte anpassen)' : 'Name des Decks') : 'Binder'}</span><input data-i="${i}" data-k="binder" list="binderlist" value="${esc(r.scope)}"></label>`;
  const cmd = deck ? `<label class="field"><span>Commander</span><select data-i="${i}" data-k="commander"><option value="">${r.deck.candidates.length ? 'keiner' : 'keine legendäre Kreatur gefunden'}</option>
    ${r.deck.candidates.map(c => `<option value="${esc(c.oracle_id)}"${(it.q.commander || r.deck.commanders[0]?.oracle_id) === c.oracle_id ? ' selected' : ''}>${esc(c.name)}</option>`).join('')}</select></label>` : '';
  const status = r.status === 'keine Änderung' ? (full ? 'Keine Änderung: Deine Sammlung ist schon auf diesem Stand.' : `Keine Änderung: „${esc(r.scope)}“ ist schon auf diesem Stand.`)
    : full ? (r.bestand ? `Ersetzt deine bisherige Sammlung (${karten(r.bestand)}). Hochgeladene Decklisten bleiben.` : 'Erster Import deiner Sammlung.')
    : r.bestand ? `Gleicht „${esc(r.scope)}“ ab (bisher ${karten(r.bestand)}): übernommen werden nur die Unterschiede.`
    : deck ? 'Neues fertiges Deck. Seine Karten stehen danach im Stapel Deck.' : `Neuer Binder „${esc(r.scope)}“.`;
  const verlust = r.status === 'abgebrochen';
  return `<div class="imp"><div class="top2"><span class="file">${esc(it.file.name)}</span><span class="tag">${esc(KIND[r.format])}</span></div>
    <div class="grid2">${ziel}${cmd}</div>
    <div class="muted">${status}</div>
    ${r.status !== 'keine Änderung' ? `<div class="nums"><div><b>+${num(r.added)}</b><span>neu</span></div><div><b>−${num(r.removed)}</b><span>entfernt</span></div>
      ${r.sold.cards ? `<div><b>${num(r.sold.cards)}</b><span>davon verkauft, ${eur(r.sold.value)}</span></div>` : ''}<div><b>${signc(r.value)}</b><span>Wertänderung</span></div></div>` : ''}
    ${verlust ? `<div class="note warn"><span class="ic">${icon('alert')}</span><div><b>${Math.round(r.removed / r.bestand * 100)} % der Karten würden verschwinden.</b><div class="muted">Stimmt das Ziel? Ein Binder-Export sollte nur seinen eigenen Binder ersetzen.${r.sold.cards ? ` ${num(r.sold.cards)} davon standen auf der Verkaufsliste.` : ''}</div></div>
      <label class="inl"><input type="checkbox" data-force="${i}"${it.force ? ' checked' : ''}> trotzdem übernehmen</label></div>` : ''}
    ${r.beispiel && r.status !== 'abgebrochen' ? `<div class="note"><span class="ic">${icon('info')}</span><div><b>Die Beispielsammlung wird vorher entfernt</b><div class="muted">${karten(r.beispiel.karten)} darin. Deine Datei kommt in eine leere Sammlung, das Beispiel liegt danach nicht zwischen deinen echten Karten.</div></div><span></span></div>` : ''}
    ${r.erkannt ? `<div class="note"><span class="ic">${icon('check')}</span><div><b>Abgleich: „${esc(r.erkannt.datei)}“ ist dein Binder „${esc(r.erkannt.binder)}“</b><div class="muted">${num(r.erkannt.gleich)} von ${karten(r.erkannt.von)} sind schon da, deshalb kommen nur die neuen dazu. Soll es doch ein eigener Binder werden, oben den Namen ändern.</div></div><span></span></div>` : ''}
    ${r.doppelt ? `<div class="note warn"><span class="ic">${icon('alert')}</span><div><b>${karten(r.doppelt.cards)} davon liegen schon in einem Scan-Binder</b><div class="muted">${esc(r.doppelt.names.slice(0, 6).join(', '))}${r.doppelt.names.length > 6 ? ' …' : ''}. Doppelt erfasst? ${esc(TIP.doppelt)}</div></div><span></span></div>` : ''}
    ${r.unknown?.length ? `<div class="note"><span class="ic">${icon('help')}</span><div><b>${karten(r.unknown.length)} nicht erkannt</b><div class="muted">${esc(r.unknown.slice(0, 8).join(', '))}${r.unknown.length > 8 ? ' …' : ''}</div></div><span></span></div>` : ''}
    ${Object.keys(r.skipped || {}).length ? `<div class="muted hint">Übersprungen: ${esc(Object.entries(r.skipped).map(([k, n]) => `${n}× ${k}`).join(', '))}</div>` : ''}
    ${r.lines.length ? `<details><summary>Wichtigste Änderungen</summary><ul class="difflines">${r.lines.map(l => `<li>${esc(l)}</li>`).join('')}</ul></details>` : ''}</div>`;
}

function renderImports() {
  const busy = imports.some(it => it.busy), doing = imports.some(it => it.applying);
  const ready = imports.filter(it => it.r && !it.done && (it.r.status === 'probelauf' || (it.r.status === 'abgebrochen' && it.force)));
  const fertig = imports.length && imports.every(it => it.done || it.error || it.r?.status === 'keine Änderung');
  dlg.className = 'modal';
  dlg.innerHTML = `<button class="x" data-close aria-label="Schließen">${icon('x')}</button><div class="box">
    <h2 id="dlg-title">${fertig ? (imports.every(it => it.error) ? 'Nicht importiert' : 'Fertig') : imports.length > 1 ? `${imports.length} Dateien prüfen` : 'Vorschau'}</h2>
    ${imports.map(impCard).join('')}
    <datalist id="binderlist">${binderNames.map(b => `<option value="${esc(b)}">`).join('')}</datalist>
    <div class="actions">${fertig ? '<button class="btn primary" type="button" data-close>Schließen</button>'
      : `<button class="btn ghost" type="button" data-close>Abbrechen</button><button class="btn primary" type="button" id="apply"${busy || doing || !ready.length ? ' disabled' : ''}>${doing ? 'Wird übernommen …' : 'Übernehmen'}</button>`}</div></div>`;
  const ap = $('#apply');
  if (ap) ap.onclick = applyImports;
}

async function applyImports() {
  for (const it of imports.filter(it => it.r && !it.done && (it.r.status === 'probelauf' || (it.r.status === 'abgebrochen' && it.force)))) {
    it.applying = true; renderImports();
    try {
      const r = await upload(it, false);
      it.r = r;
      it.done = r.status === 'importiert' ? `Übernommen: +${num(r.added)} / −${karten(r.removed)}${r.sold.cards ? `, ${num(r.sold.cards)} als verkauft gebucht (${eur(r.sold.value)})` : ''}.${r.beispiel?.entfernt ? ' Die Beispielsammlung ist entfernt.' : ''}` : r.text;
    } catch (e) { it.error = e.message; }
    it.applying = false;
  }
  renderImports();
  dirty = true;
}

dlg.addEventListener('change', e => {
  const t = e.target;
  if (t.id === 'keep') return setStatus(t.closest('[data-oid-box]').dataset.oidBox, $('[data-st][aria-pressed=true]').dataset.st, +t.value);
  if (t.dataset.force != null) { imports[+t.dataset.force].force = t.checked; return renderImports(); }
  if (t.dataset.i != null) {
    const it = imports[+t.dataset.i];
    it.q[t.dataset.k] = t.value.trim();
    if (t.dataset.k === 'binder') check(it);
  }
});
dlg.addEventListener('close', () => { if (dirty) { dirty = false; render(true); } });

// --- Hintergrund-Jobs (Commander-Daten, Preise) mit Fortschritt ----------------------------------------------------
let jobs = {}, jobTimer = null;
const JOBNAME = {commanders: 'Commander-Daten', prices: 'Preise', combos: 'Combos', vektoren: 'Ähnliche Karten'};
async function startJob(name) {
  try { jobs[name] = await api('jobs?start=' + name, {method: 'POST'}); jobsUi(); pollJobs(); }
  catch (e) { flash('Fehler: ' + e.message); }
}
async function pollJobs() {
  clearTimeout(jobTimer);
  try {
    const vorher = jobs;
    jobs = await api('jobs');
    for (const [n, j] of Object.entries(jobs)) if (vorher[n]?.running && !j.running) {
      flash(j.error ? `${JOBNAME[n]}: ${j.error}` : `${JOBNAME[n]} fertig: ${j.label}`);
      render(true);
    }
  } catch { /* Server kurz weg: beim nächsten Mal */ }
  jobsUi();
  if (Object.values(jobs).some(j => j.running)) jobTimer = setTimeout(pollJobs, 1000);
}
function jobsUi() {
  for (const box of $$('[data-jobbox]')) {
    const j = jobs[box.dataset.jobbox];
    box.innerHTML = j?.running ? `<div class="jobline">${j.total ? `${num(j.done)} / ${num(j.total)}` : j.label ? '' : 'startet'} ${esc(j.label || '')}</div><div class="progress"><span style="--p:${j.total ? (j.done / j.total).toFixed(3) : 0.04}"></span></div>`
      : j?.error ? `<div class="jobline">Zuletzt fehlgeschlagen: ${esc(j.error)}</div>` : '';
  }
  for (const b of $$('[data-job]')) b.disabled = !!jobs[b.dataset.job]?.running;
}

// --- Globale Ereignisse: Klicks, Hover-Vorschau, Tooltips, Ablegen -------------------------------------------------
const outside = (e, el) => { const r = el.getBoundingClientRect(); return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom; };
document.addEventListener('click', e => {
  if (e.target.closest('[data-close]')) { if (e.target.closest('a[href^="#/"]')) dlg.close(); else { e.preventDefault(); return dlg.close(); } }
  if (e.target === dlg && outside(e, dlg)) return dlg.close();  // Klick auf den abgedunkelten Hintergrund
  const ex = e.target.closest('[data-export]');
  if (ex) return;  // echter Download-Link
  const b = e.target.closest('[data-st]');
  if (b) return setStatus(b.closest('[data-oid-box]').dataset.oidBox, b.dataset.st, 0);
  const kb = e.target.closest('[data-kopie]');
  if (kb && kb.tagName === 'BUTTON') return kopieDialog(+kb.dataset.kopie);
  const bs = e.target.closest('[data-beispiel]');
  if (bs) return beispielAktion(bs.dataset.beispiel, bs);
  if (e.target.closest('[data-pick]')) return $('#file').click();
  if (e.target.closest('[data-paste]')) return openChooser(true);
  const j = e.target.closest('[data-job]');
  if (j) return startJob(j.dataset.job);
  if (e.target.closest('.info')) { e.preventDefault(); return; }
  if (e.target.closest('[data-retry]')) return render(true);
  const wb = e.target.closest('[data-wedit], [data-wdel], [data-wadd]');
  if (wb) { e.preventDefault(); e.stopPropagation(); return wb.dataset.wedit ? openWunsch(wb.dataset.wedit) : wunschSetzen(wb.dataset.wdel || wb.dataset.wadd, !!wb.dataset.wdel); }
  const dv = e.target.closest('[data-dview]');
  if (dv) { merke('mtg-deckview', dv.dataset.dview); return deckNeu(); }
  const sp = e.target.closest('[data-sweg], [data-gweg]');
  if (sp) return sp.dataset.sweg ? spielWeg('spiel-weg', sp.dataset.sweg, 'Spiel gelöscht') : spielWeg('gruppe-weg', sp.dataset.gweg, 'Aus der Spielgruppe entfernt');
  if (e.target.closest('#logout')) return logout();
  if (e.target.closest('#undo')) return undo();
  if (e.target.closest('#pe-jetzt')) return peSetzen({jetzt: 1});
  if (e.target.closest('#up-suchen')) return updateSuchen();
  const pw = e.target.closest('[data-pw]');
  if (pw) return openPw(pw.dataset.pw, pw.dataset.label, pw.dataset.has === '1');
  const sw = e.target.closest('[data-open]');
  if (sw) return switchTo(sw.dataset.open);
  const del = e.target.closest('[data-del]');
  if (del) return delKonto(del.dataset.del, del.dataset.label);
  const a = e.target.closest('[data-oid]');
  if (a && !e.target.closest('input')) { e.preventDefault(); openCard(a.dataset.oid).catch(err => flash('Fehler: ' + err.message)); }
});

// Vorschau und Tooltip als Popover: liegen in der obersten Ebene, also auch über einem offenen Dialog
const pop = (el, on) => {
  if (!el.showPopover) { el.hidden = !on; return; }
  try { if (on) { if (el.matches(':popover-open')) el.hidePopover(); el.showPopover(); } else if (el.matches(':popover-open')) el.hidePopover(); } catch { /* schon im gewünschten Zustand */ }
};
const peek = $('#peek'), canHover = matchMedia('(hover: hover) and (pointer: fine)');
let peekEl = null, peekTimer, mx = 0, my = 0;
const hidePeek = () => { clearTimeout(peekTimer); peekEl = null; peek.classList.remove('on'); pop(peek, false); };
const placePeek = () => {
  const w = 250, hgt = peek.offsetHeight || 400, gap = 22;
  let x = mx + gap, y = my - hgt / 2;
  if (x + w > innerWidth - 8) x = mx - gap - w;
  y = Math.max(8, Math.min(y, innerHeight - hgt - 8));
  peek.style.left = Math.max(8, x) + 'px'; peek.style.top = y + 'px';
};
document.addEventListener('mouseover', e => {
  const el = e.target.closest('[data-img]');
  if (el === peekEl) return;
  hidePeek();
  if (!el || !canHover.matches || (dlg.open && !dlg.contains(el))) return;
  peekEl = el;
  peekTimer = setTimeout(() => {
    peek.innerHTML = `<img alt="" src="${esc(el.dataset.img)}"><div class="cap"><b>${esc(el.dataset.cap)}</b>${esc(el.dataset.sub || '')}</div>`;
    pop(peek, true); placePeek(); requestAnimationFrame(() => peek.classList.add('on'));
  }, el.classList.contains('card') ? 380 : 140);
});
document.addEventListener('mousemove', e => { mx = e.clientX; my = e.clientY; if (peekEl && peek.classList.contains('on')) placePeek(); }, {passive: true});
addEventListener('scroll', () => { if (peekEl) hidePeek(); }, {passive: true});
document.addEventListener('mousedown', hidePeek);

const tip = $('#tip');
let tipEl = null, tipBy = '';  // tipBy: hover oder focus (Tastatur); Hover blendet nur seine eigenen Tooltips aus
const showTip = (el, by = tipBy) => {
  tipEl = el; tipBy = by; tip.textContent = el.dataset.tip; pop(tip, true);
  const r = el.getBoundingClientRect(), w = tip.offsetWidth, hh = tip.offsetHeight;
  let x = r.left + r.width / 2 - w / 2, y = r.bottom + 8;
  if (y + hh > innerHeight - 8) y = r.top - hh - 8;
  tip.style.left = Math.max(8, Math.min(x, innerWidth - w - 8)) + 'px'; tip.style.top = y + 'px';
};
const hideTip = () => { tipEl = null; tipBy = ''; pop(tip, false); };
document.addEventListener('mouseover', e => { const el = e.target.closest('[data-tip]'); if (el) showTip(el, 'hover'); else if (tipBy === 'hover') hideTip(); });
document.addEventListener('focusin', e => { const el = e.target.closest('[data-tip]'); el ? showTip(el, 'focus') : hideTip(); });
document.addEventListener('focusout', () => { if (tipBy === 'focus') hideTip(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') { hideTip(); hidePeek(); } });
addEventListener('scroll', () => { if (tipEl) tipEl.isConnected ? showTip(tipEl) : hideTip(); }, {passive: true});  // Tooltip wandert mit

$('#import').onclick = () => openChooser(false);
$('#file').onchange = e => { if (e.target.files.length) importFiles([...e.target.files]); e.target.value = ''; };
let depth = 0;
const dropUi = on => { $('#drop').hidden = !on || dlg.open; $$('[data-dropzone]').forEach(z => z.classList.toggle('over', on)); };
addEventListener('dragenter', e => { if (e.dataTransfer?.types.includes('Files')) { depth++; dropUi(true); } });
addEventListener('dragleave', () => { if (--depth <= 0) { depth = 0; dropUi(false); } });
addEventListener('dragover', e => e.preventDefault());
addEventListener('drop', e => { e.preventDefault(); depth = 0; dropUi(false); if (e.dataTransfer.files.length) importFiles([...e.dataTransfer.files]); });

// --- Darstellung: Dunkel (Standard), Hell oder wie das System; gesetzt wird schon im <head> ------------------------
const sysLight = matchMedia('(prefers-color-scheme: light)'), themeSel = $('#theme');
const themePref = () => { try { return localStorage.getItem('mtg-theme') || 'dark'; } catch { return 'dark'; } };
const applyTheme = () => { const t = themePref(); document.documentElement.dataset.theme = t === 'system' ? (sysLight.matches ? 'light' : 'dark') : t; };
themeSel.value = themePref();
themeSel.onchange = () => { try { localStorage.setItem('mtg-theme', themeSel.value); } catch { /* privates Fenster: gilt bis zum Neuladen */ } applyTheme(); };
sysLight.addEventListener('change', applyTheme);
applyTheme();

// --- Routing -----------------------------------------------------------------------------------------------------
// --- Scanner (Phase 24, PLAN E17): eigene Karten per Kamera erkennen ------------------------------------------
// Fingerabdruck: Namenszeile und Bild der Karte (FP_BOX) auf FP_W × FP_H Felder verkleinert, je Farbkanal auf Mittel 0 und Streuung 1
// (Helligkeit und Weißabgleich fallen raus), als Int8. Dieselbe Rechnung für das Scryfall-Bild und den Kamera-Ausschnitt.
const FP_V = 2, FP_W = 16, FP_H = 14, FP_BOX = [0.07, 0.04, 0.93, 0.58];  // links, oben, rechts, unten als Anteil der Karte
const fpMid = document.createElement('canvas'), fpOut = document.createElement('canvas');
// Karte mit Mitte (cx, cy), Größe w × h und Drehung a (Grad) in src
function fingerprint(src, cx, cy, w, h, a = 0) {
  const [l, t, r, b] = FP_BOX;
  fpMid.width = FP_W * 4; fpMid.height = FP_H * 4; fpOut.width = FP_W; fpOut.height = FP_H;
  const m = fpMid.getContext('2d'), o = fpOut.getContext('2d', {willReadFrequently: true});
  m.imageSmoothingQuality = o.imageSmoothingQuality = 'high';
  m.setTransform(fpMid.width / ((r - l) * w), 0, 0, fpMid.height / ((b - t) * h), 0, 0);
  m.translate(-(l - .5) * w, -(t - .5) * h); m.rotate(-a * Math.PI / 180); m.translate(-cx, -cy);
  m.drawImage(src, 0, 0);
  o.drawImage(fpMid, 0, 0, FP_W, FP_H);  // zwei Stufen: mittelt sauberer
  const d = o.getImageData(0, 0, FP_W, FP_H).data, n = FP_W * FP_H, fp = new Int8Array(n * 3);
  fp.sd = 0;  // größte Streuung der Kanäle: fast 0 = einfarbige Fläche, also keine Karte im Rahmen
  for (let k = 0; k < 3; k++) {
    let s = 0, q = 0;
    for (let i = 0; i < n; i++) { const v = d[i * 4 + k]; s += v; q += v * v; }
    const mw = s / n, sd = Math.sqrt(Math.max(q / n - mw * mw, 1));
    fp.sd = Math.max(fp.sd, sd);
    for (let i = 0; i < n; i++) fp[k * n + i] = Math.max(-127, Math.min(127, Math.round((d[i * 4 + k] - mw) / sd * 32)));
  }
  return fp;
}
// Index aus GET /api/scan: Fingerabdrücke als Float32 ohne den Durchschnitt aller (Rahmen, Rand und Namenszeile sehen bei vielen Karten
// gleich aus, so zählt nur, was eine Karte unterscheidet), jede Zeile auf Länge 1, damit das Skalarprodukt der Kosinus ist
function fpIndex(r) {
  const raw = Uint8Array.from(atob(r.fp), ch => ch.charCodeAt(0)), L = r.len, n = r.ids.length, m = new Float32Array(n * L), mu = new Float32Array(L);
  for (let j = 0; j < n * L; j++) { m[j] = (raw[j] << 24) >> 24; mu[j % L] += m[j] / n; }
  for (let j = 0; j < n; j++) {
    let s = 0;
    for (let i = 0; i < L; i++) { const v = m[j * L + i] -= mu[i]; s += v * v; }
    for (let i = 0, f = 1 / Math.sqrt(s || 1); i < L; i++) m[j * L + i] *= f;
  }
  return {...r, m, mu, n, L};
}
const fpNorm = (ix, fp) => { const q = Float32Array.from(fp, (v, i) => v - ix.mu[i]); let s = 0; for (const v of q) s += v * v; const f = 1 / Math.sqrt(s || 1); return q.map(v => v * f); };
const fpDot = (ix, q, j) => { let d = 0; for (let i = 0, o = j * ix.L; i < ix.L; i++) d += ix.m[o + i] * q[i]; return d; };
// die k besten verschiedenen Karten unter rows: [{i (Zeile im Index), oid, score}]; verschieden heißt je Karte (Prüfen) bzw. je Druck (Erfassen: ix.keys)
function fpTop(ix, sc, rows, k) {
  const out = [], seen = new Set(), key = ix.keys || ix.oids;
  for (const j of rows.sort((a, b) => sc[b] - sc[a])) {
    if (seen.has(key[j])) continue;
    seen.add(key[j]); out.push({i: j, oid: key[j], score: sc[j]});
    if (out.length === k) break;
  }
  return out;
}
// Kamera: Karte liegt nie genau im Rahmen. Erst FP_VOR (Versatz als Anteil der Karte) gegen alle, dann für die FP_KANDIDATEN besten jede Lage
// aus FP_LAGEN (Versatz, Größe, Drehung in Grad); je Druck zählt die beste Lage. Gemessen mit tests/scan_eval.js (PLAN Phase 24): 93 % richtig
// an verzerrten Scryfall-Bildern, ca. 130 ms. Ab FP_SICHER gilt die Karte als erkannt, darunter bis FP_NEIN als unsicher (Auswahl aus drei);
// 95 % der Karten, die nicht in der Sammlung sind, bleiben unter 0,77.
const FP_KANDIDATEN = 150, FP_SICHER = 0.8, FP_NEIN = 0.72, FP_FLACH = 12, FP_VOR = [[0, 0], [.03, 0], [-.03, 0], [0, .03], [0, -.03]], FP_LAGEN = [];
for (const dx of [-.03, 0, .03]) for (const dy of [-.03, 0, .03]) for (const [s, a] of [[1, 0], [.96, 0], [1.04, 0], [1, -3], [1, 3]]) FP_LAGEN.push([dx, dy, s, a]);
function fpSuche(ix, src, cx, cy, w, h, k = 3, vor = FP_VOR, lagen = FP_LAGEN) {
  if (fingerprint(src, cx, cy, w, h).sd < FP_FLACH) return [];  // leerer Tisch, Hand davor: nichts suchen
  const sc = new Float32Array(ix.n).fill(-1);
  for (const [dx, dy] of vor) {
    const q = fpNorm(ix, fingerprint(src, cx + dx * w, cy + dy * h, w, h));
    for (let j = 0; j < ix.n; j++) sc[j] = Math.max(sc[j], fpDot(ix, q, j));
  }
  const kand = [...sc.keys()].sort((a, b) => sc[b] - sc[a]).slice(0, FP_KANDIDATEN);
  for (const [dx, dy, s, a, sy = s] of lagen) {
    const q = fpNorm(ix, fingerprint(src, cx + dx * w, cy + dy * h, w * s, h * sy, a));
    for (const j of kand) sc[j] = Math.max(sc[j], fpDot(ix, q, j));
  }
  return fpTop(ix, sc, kand, k);
}
const fpB64 = fp => btoa(String.fromCharCode(...new Uint8Array(fp.buffer)));
// fehlende Fingerabdrücke aus den kleinen Scryfall-Bildern rechnen (CDN ohne Limit, erlaubt CORS) und in Paketen speichern: je Druck unter
// „scan“ oder je Aussehen unter „scan/katalog“ (Phase 32); stopp() = true bricht ab, das Gerechnete ist dann gespeichert
async function fpJob(fehlt, progress, ziel = 'scan', stopp) {
  const laden = u => new Promise((ok, err) => { const im = new Image(); im.crossOrigin = 'anonymous'; im.onload = () => ok(im); im.onerror = err; im.src = u; });
  let fertig = 0, paket = {};
  const senden = async () => { const p = paket; paket = {}; if (Object.keys(p).length) await post(ziel, {v: FP_V, fp: p}); };
  const queue = [...fehlt];
  await Promise.all(Array.from({length: 16}, async () => {  // die Zeit geht fürs Laden drauf (rund 180 ms je Bild), das Rechnen kostet 1,5 ms
    for (let f; !stopp?.() && (f = queue.shift());) {
      try { const im = await laden(small(f.image)); const w = im.naturalWidth, h = im.naturalHeight; paket[f.id] = fpB64(fingerprint(im, w / 2, h / 2, w, h)); }
      catch { /* Bild fehlt: beim nächsten Mal wieder versucht */ }
      if (++fertig % 200 === 0) { await senden(); progress?.(fertig, fehlt.length); }
    }
  }));
  await senden(); progress?.(fertig, fehlt.length);
}

// --- Karte frei im Bild finden (Phase 33, PLAN E20) ---------------------------------------------------------------
// Ohne Bibliothek und ohne Modell, auf dem verkleinerten Bild (lange Seite FIND_PX): Kanten (Sobel je Farbkanal, der stärkste zählt, davon das
// stärkste FIND_KANTEN-tel und nur der Kamm), daraus lange Geraden (Hough: Jedes Kantenpixel stimmt nur für die Richtungen um seine eigene, hell
// nach dunkel getrennt von dunkel nach hell. So bleiben Kartenrand und innerer Rahmen zwei Geraden, auch wenn sie nur zwei Pixel auseinander
// liegen), die stärksten zuerst, nachgezogen durch ihre Kantenpixel. Zwei eher senkrechte und zwei eher waagrechte geben ein Viereck. Es zählt,
// wenn Größe, Seitenverhältnis (63 zu 88, schräg gesehen etwas anders) und Winkel zu einer aufrechten Karte passen (bis etwa 40° gedreht) und
// unter seinen Seiten Kanten liegen, die an den Ecken aufhören. -> bis zu FIND_ZAHL Vierecke {e: Ecken oben links, oben rechts, unten rechts,
// unten links in Pixeln von src, s: Güte, hell: rundum außen heller als innen}, das beste zuerst. Oft sind es der Kartenrand, der innere Rahmen
// und eine Mischung aus beiden: Welches die Karte ist, sagt erst die Erkennung (freiSuche), ein falsches Viereck findet keine.
// Die Werte sind gemessen (tests/finden_eval.js, PLAN Phase 33): vor einer Änderung neu messen.
const FIND_PX = 320, FIND_ZAHL = 3, FIND_GERADEN = 16, FIND_JE = 4, FIND_KANTEN = .25, FIND_SCHWACH = 24, FIND_MIN = .28, FIND_EINIG = .3, FIND_AUSSEN = .5, FIND_GROSS = .3, FIND_RUHIG = .06;
const FIND_COS = [], FIND_SIN = [];
for (let t = 0; t < 360; t++) { FIND_COS.push(Math.cos((t - 45) * Math.PI / 180)); FIND_SIN.push(Math.sin((t - 45) * Math.PI / 180)); }  // Richtung t = Grad + 45: vier Viertel ohne Sprung
const findWork = document.createElement('canvas');
function karteFinden(src, sw, sh) {
  const f = FIND_PX / Math.max(sw, sh), W = Math.round(sw * f), H = Math.round(sh * f), N = W * H;
  findWork.width = W; findWork.height = H;
  const c = findWork.getContext('2d', {willReadFrequently: true});
  c.imageSmoothingQuality = 'high';
  c.drawImage(src, 0, 0, W, H);
  const px = c.getImageData(0, 0, W, H).data, gx = new Float32Array(N), gy = new Float32Array(N), mag = new Float32Array(N), hist = new Uint32Array(256);
  for (let y = 1; y < H - 1; y++) for (let x = 1; x < W - 1; x++) {
    const i = y * W + x, z = 4 * W;
    for (let k = 0, p = i * 4; k < 3; k++, p++) {
      const dx = px[p - z + 4] + 2 * px[p + 4] + px[p + z + 4] - px[p - z - 4] - 2 * px[p - 4] - px[p + z - 4];
      const dy = px[p + z - 4] + 2 * px[p + z] + px[p + z + 4] - px[p - z - 4] - 2 * px[p - z] - px[p - z + 4], m = dx * dx + dy * dy;
      if (m > mag[i]) { mag[i] = m; gx[i] = dx; gy[i] = dy; }
    }
    hist[Math.min(255, (mag[i] = Math.sqrt(mag[i])) >> 2)]++;
  }
  let T = 255;
  for (let n = 0; T > FIND_SCHWACH / 4 && (n += hist[T]) < FIND_KANTEN * N;) T--;
  T *= 4;
  // Kamm der Kanten: die Pixel je Richtung (kanten) und ihre Stimmen im Hough-Raum (Richtung × Abstand von der Bildmitte)
  const R = Math.ceil(Math.hypot(W, H)) + 4, acc = new Uint16Array(360 * R), kanten = Array.from({length: 360}, () => []);
  for (let y = 1; y < H - 1; y++) for (let x = 1; x < W - 1; x++) {
    const i = y * W + x, m = mag[i];
    if (m < T) continue;
    const ax = Math.abs(gx[i]), ay = Math.abs(gy[i]), d = ax > 2.414 * ay ? 1 : ay > 2.414 * ax ? W : (gx[i] > 0) === (gy[i] > 0) ? W + 1 : W - 1;
    if (m < mag[i - d] || m <= mag[i + d]) continue;
    const t0 = (Math.round(Math.atan2(gy[i], gx[i]) * 180 / Math.PI) + 405) % 360;
    kanten[t0].push(i);
    for (let dt = -2; dt <= 2; dt++) { const t = (t0 + dt + 360) % 360; acc[t * R + Math.round((x - W / 2) * FIND_COS[t] + (y - H / 2) * FIND_SIN[t] + R / 2)]++; }
  }
  const quer = (a, b) => { const d = Math.abs(a - b) % 360; return Math.min(d, 360 - d); };  // Winkel zwischen zwei Richtungen
  const jede = (t, breit, fn) => { for (let d = -breit; d <= breit; d++) for (const i of kanten[(t + d + 720) % 360]) fn(i % W - W / 2, (i / W | 0) - H / 2); };  // Kantenpixel um die Richtung t
  // Geraden = Gipfel im Hough-Raum, die stärksten zuerst: je Viertel (Richtung und hell/dunkel) höchstens FIND_GERADEN und je 15° höchstens
  // FIND_JE, damit die Maserung eines Holztischs nicht alle Plätze nimmt (mit 12 und 3 fand die Messung 5 Punkte weniger Karten)
  const gipfel = [], genug = Math.max(12, .07 * Math.min(W, H));
  for (let t = 0; t < 360; t++) for (let r = 2, o = t * R; r < R - 2; r++) {
    const v = acc[o + r - 1] + acc[o + r] + acc[o + r + 1];
    if (v >= genug && v >= acc[o + r - 2] + acc[o + r - 1] + acc[o + r] && v > acc[o + r] + acc[o + r + 1] + acc[o + r + 2]) gipfel.push([v, t, r]);
  }
  const geraden = [[], []], genommen = [], zahl = new Uint8Array(4), jeWinkel = new Uint8Array(24);  // geraden: [eher senkrecht, eher waagrecht]
  for (const [, t, r] of gipfel.sort((a, b) => b[0] - a[0])) {
    const q = t / 90 | 0;
    if (zahl[q] >= FIND_GERADEN || jeWinkel[t / 15 | 0] >= FIND_JE || genommen.some(([t2, r2]) => quer(t, t2) <= 5 && Math.abs(r - r2) <= 4)) continue;
    genommen.push([t, r]);
    // nachziehen: Ausgleichsgerade durch die Kantenpixel, die auf ihr liegen und ihre Richtung haben, erst grob, dann eng (der innere Rahmen
    // liegt oft nur drei Pixel neben dem Kartenrand und darf die Gerade nicht zu sich ziehen)
    let g = {nx: FIND_COS[t], ny: FIND_SIN[t], rho: r - R / 2};
    for (const eng of [2, 1]) {
      let sx = 0, sy = 0, sxx = 0, sxy = 0, syy = 0, k = 0;
      jede(t, 6, (x, y) => { if (Math.abs(x * g.nx + y * g.ny - g.rho) <= eng) { sx += x; sy += y; sxx += x * x; sxy += x * y; syy += y * y; k++; } });
      if (k < genug) { g = null; break; }
      const mx = sx / k, my = sy / k, phi = .5 * Math.atan2(2 * (sxy / k - mx * my), sxx / k - mx * mx - syy / k + my * my);
      const nx = -Math.sin(phi), ny = Math.cos(phi), v = nx * FIND_COS[t] + ny * FIND_SIN[t] < 0 ? -1 : 1;  // die Normale zeigt weiter von dunkel nach hell
      g = {nx: nx * v, ny: ny * v, rho: (nx * mx + ny * my) * v};
    }
    if (!g || geraden[q % 2].some(h => h.nx * g.nx + h.ny * g.ny > .9994 && Math.abs(h.rho - g.rho) < 1.5)) continue;  // dieselbe Gerade noch einmal (2°)
    // wo entlang der Geraden eine Kante liegt (gleich ob hell oder dunkel außen), als laufende Summe: so kostet jede Seite eines Vierecks nichts
    const da = new Uint8Array(R + 1), tg = Math.round(Math.atan2(g.ny, g.nx) * 180 / Math.PI) + 405;
    for (const u of [0, 180]) jede(tg + u, 12, (x, y) => { if (Math.abs(x * g.nx + y * g.ny - g.rho) <= 1.5) { const s = Math.round(y * g.nx - x * g.ny + R / 2); da[s] = da[s + 1] = 1; } });
    g.bel = new Uint16Array(R + 1);
    for (let s = 0; s < R; s++) g.bel[s + 1] = g.bel[s] + da[s];
    geraden[q % 2].push(g); zahl[q]++; jeWinkel[t / 15 | 0]++;
  }
  const schnitt = (a, b) => { const d = a.nx * b.ny - a.ny * b.nx; return [(a.rho * b.ny - a.ny * b.rho) / d, (a.nx * b.rho - a.rho * b.nx) / d]; };
  const lang = (p, q) => Math.hypot(q[0] - p[0], q[1] - p[1]);
  // Seite p-q auf der Geraden g -> [Anteil mit Kante (ohne die runden Ecken), Anteil mit Kante in der Verlängerung über die Ecken hinaus]:
  // Der Rand einer Karte hört an der Ecke auf, eine Tischkante oder Maserung läuft weiter
  const seite = (g, p, q) => {
    let a = p[1] * g.nx - p[0] * g.ny + R / 2, b = q[1] * g.nx - q[0] * g.ny + R / 2;
    if (a > b) [a, b] = [b, a];
    const L = b - a, sum = (u, v) => g.bel[Math.max(0, Math.min(R, Math.round(v)))] - g.bel[Math.max(0, Math.min(R, Math.round(u)))];
    return [sum(a + .08 * L, b - .08 * L) / (.84 * L), (sum(a - .3 * L, a - .06 * L) + sum(b + .06 * L, b + .3 * L)) / (.48 * L)];
  };
  // Paare gegenüberliegender Seiten: höchstens 15° zueinander und in der Bildmitte mindestens eine kleine Karte auseinander (wo = 0: x, 1: y)
  const paare = (gs, wo, weit) => gs.flatMap((a, i) => gs.slice(i + 1).filter(b => Math.abs(a.nx * b.ny - a.ny * b.nx) < .26 && Math.abs(a.rho / (wo ? a.ny : a.nx) - b.rho / (wo ? b.ny : b.nx)) > weit).map(b => [a, b]));
  const alle = [], rand = 1.04, klein = FIND_MIN * Math.min(W, H);
  for (const [s1, s2] of paare(geraden[0], 0, .5 * klein)) for (const [w1, w2] of paare(geraden[1], 1, .8 * klein)) {
    const [li, re] = s1.rho / s1.nx < s2.rho / s2.nx ? [s1, s2] : [s2, s1], [ob, un] = w1.rho / w1.ny < w2.rho / w2.ny ? [w1, w2] : [w2, w1];
    if (Math.abs(li.nx * ob.nx + li.ny * ob.ny) > .42) continue;  // schiefer als 25°
    const e = [schnitt(li, ob), schnitt(re, ob), schnitt(re, un), schnitt(li, un)];
    if (e.some(([x, y]) => !(Math.abs(x) <= W / 2 * rand && Math.abs(y) <= H / 2 * rand))) continue;
    const oben = lang(e[0], e[1]), rechts = lang(e[1], e[2]), unten = lang(e[2], e[3]), links = lang(e[3], e[0]), w = (oben + unten) / 2, h = (links + rechts) / 2;
    if (h < klein || w / h < .56 || w / h > .9 || Math.abs(oben - unten) > .25 * w || Math.abs(links - rechts) > .25 * h) continue;
    if (e[1][0] <= e[0][0] || e[2][0] <= e[3][0] || e[3][1] <= e[0][1] || e[2][1] <= e[1][1]) continue;  // verdreht
    const k = [seite(ob, e[0], e[1]), seite(re, e[1], e[2]), seite(un, e[3], e[2]), seite(li, e[0], e[3])], innen = (k[0][0] + k[1][0] + k[2][0] + k[3][0]) / 4;
    if (innen < .55 || Math.min(k[0][0], k[1][0], k[2][0], k[3][0]) < .25) continue;
    // rundum dieselbe Kante (überall außen heller oder überall außen dunkler) spricht für Kartenrand oder inneren Rahmen und gegen eine Mischung;
    // unter gleich guten zählt das größere (der Kartenrand liegt außen)
    const hell = ob.ny < 0, einig = hell === (re.nx > 0) && hell === (un.ny > 0) && hell === (li.nx < 0);
    alle.push({e, w, hell: einig && hell, s: innen - FIND_AUSSEN * (k[0][1] + k[1][1] + k[2][1] + k[3][1]) / 4 + (einig ? FIND_EINIG : 0) + FIND_GROSS * w * h / N});
  }
  const beste = [];  // fast dasselbe Viereck nur einmal
  for (const v of alle.sort((a, b) => b.s - a.s)) {
    if (!beste.some(g => g.e.every(([x, y], i) => Math.hypot(x - v.e[i][0], y - v.e[i][1]) < .03 * g.w))) beste.push(v);
    if (beste.length === FIND_ZAHL) break;
  }
  return beste.map(v => ({e: v.e.map(([x, y]) => [(x + W / 2 + .5) / f, (y + H / 2 + .5) / f]), s: v.s, hell: v.hell}));  // + .5: Mitte des Pixels
}

// Ansicht „Scannen“: Kamera mit Kartenrahmen, je Bild fpSuche. Prüfen (Phase 24): eigene Karte, das Ergebnis steht, sobald dieselbe Karte zweimal
// nacheinander sicher erkannt ist. Erfassen (Phase 25): neue Karten mit Set-Lock in einen Scan-Binder (erfZeigen).
let scanIx = null, scanStream = null, scanTimer = null, scanLog = [], scanStand = '', scanModus = 'pruefen', scanQ = null, scanBei = null, scanVier = null, scanBox = '';
let scanFrei = merk('mtg-scan-frei', '1', [['1'], ['0']]) === '1';  // Karte frei im Bild suchen (Phase 33); aus: nur der Rahmen
const scanWork = document.createElement('canvas'), scanQuelle = document.createElement('canvas');
let scanWache = null;  // Wake Lock (Phase 27): der Bildschirm bleibt an, solange die Kamera läuft
const scanStop = () => { clearTimeout(scanTimer); scanTimer = null; blaettern = null; scanStream?.getTracks().forEach(t => t.stop()); scanStream = null; scanWache?.release().catch(() => {}); scanWache = null; blatt(); document.body.classList.remove('vollbild'); };
const wachHalten = async () => {
  if (!scanStream || scanWache || document.visibilityState !== 'visible') return;
  try { scanWache = await navigator.wakeLock.request('screen'); scanWache.addEventListener('release', () => { scanWache = null; }); } catch { /* ohne Wake Lock: der Bildschirm darf ausgehen */ }
};
document.addEventListener('visibilitychange', wachHalten);  // nach dem Wechsel in eine andere App gibt der Browser die Sperre frei
// Ton bei jeder gezählten Karte, statt zu vibrieren (auf einem Ständer verrutscht das Handy davon): kurzer Sinus über Web Audio, ohne Datei. Der
// Browser lässt Ton erst nach einem Tipp zu, deshalb weckt ihn „Kamera starten“ (tonAn). Laut und leise regelt die Medienlautstärke des Geräts.
let tonCtx = null;
const tonAn = () => { try { tonCtx = tonCtx || new AudioContext(); tonCtx.resume().catch(() => {}); } catch { /* ohne Web Audio: still */ } };
function ton(hz = 1320, s = .09) {
  if (!tonCtx) return;
  tonCtx.resume().catch(() => {});  // nach dem Wechsel in eine andere App hält der Browser ihn an
  const t = tonCtx.currentTime, o = tonCtx.createOscillator(), g = tonCtx.createGain();
  o.frequency.value = hz;
  g.gain.setValueAtTime(.0001, t); g.gain.exponentialRampToValueAtTime(.3, t + .01); g.gain.exponentialRampToValueAtTime(.0001, t + s);  // weich an und aus, sonst knackt es
  o.connect(g).connect(tonCtx.destination);
  o.start(t); o.stop(t + s);
}
// Rahmen im Kamerabild (Pixel): Karte hochkant in der Mitte, 86 % der Bildhöhe, höchstens 90 % der Breite. Im Vollbild (Phase 34) füllt das
// Kamerabild die Anzeige (bw × bh) und ist beschnitten: Dort zählt der sichtbare Teil, und der Rahmen ist kleiner und sitzt höher, weil rechts
// und unten die Bedienung liegt.
const scanRahmen = (vw, vh, bw = vw, bh = vh, voll = false) => {
  const f = Math.max(bw / vw, bh / vh), sw = bw / f, sh = bh / f, h = Math.min(sh * (voll ? .56 : .86), sw * (voll ? .66 : .9) * 88 / 63), w = h * 63 / 88;
  return {x: (vw - w) / 2, y: (vh - sh) / 2 + sh * (voll ? .44 : .5) - h / 2, w, h};
};
// Vollbild (Phase 34): Am Handy füllt die Kamera den Bildschirm, solange sie läuft (body.vollbild, die Aufteilung steht in style.css)
const vollbild = () => document.body.classList.contains('vollbild') && matchMedia('(max-width: 768px)').matches;
const scanG = v => scanRahmen(v.videoWidth, v.videoHeight, v.clientWidth || v.videoWidth, v.clientHeight || v.videoHeight, vollbild());
// Rahmen über dem Kamerabild zeichnen, neu nur, wenn sich die Anzeige geändert hat (Handy gedreht, Vollbild an oder aus) -> der Rahmen
function scanRahmenZeigen(v) {
  const vw = v.videoWidth, vh = v.videoHeight, g = scanG(v), key = [vw, vh, v.clientWidth, v.clientHeight, vollbild()].join(), lage = $('#cam-lage');
  if (lage && key !== scanBox) {
    scanBox = key;
    lage.setAttribute('viewBox', `0 0 ${vw} ${vh}`);
    $('.aussen', lage).setAttribute('d', `M0 0H${vw}V${vh}H0ZM${g.x} ${g.y}v${g.h}h${g.w}v${-g.h}Z`);  // alles außer dem Rahmen abdunkeln
    for (const [k, x] of Object.entries({x: g.x, y: g.y, width: g.w, height: g.h, rx: g.w * 3 / 63})) $('.rahmen', lage).setAttribute(k, x);
  }
  return g;
}
// Blatt von unten im Vollbild: Scan-Liste oder Einstellungen (id), ohne id alle zu. Solange eins offen ist, ruht die Erkennung (scanLoop).
function blatt(id) {
  for (const b of $$('#erf-liste, #erf-setup')) b.classList.toggle('offen', b.id === id);
  const zu = $('#voll-schleier');
  if (!zu) return;
  zu.hidden = !id;
  if (id === 'erf-setup' || vollbild()) $('#erf-setup').open = id === 'erf-setup';  // als Blatt aufgeklappt, danach wieder zu wie beim Start der Kamera
  if (id) $('button', zu).focus();
}
function scanEnde() {  // Kamera aus, die Ansicht bleibt: am Handy zurück aus dem Vollbild zur Seite
  scanStop();
  $('#cam-video').srcObject = null;
  $('#cam-lage').setAttribute('hidden', '');
  for (const el of [$('#cam'), $('#cam-lampe'), $('#cam-aufl')]) el.hidden = true;
  $('#cam-go').hidden = false; $('#cam-go').closest('.toolbar').hidden = false;
  $('#cam-box').style.aspectRatio = '';  // ohne Bild wieder flach: Am Handy stünde sonst ein leerer hoher Kasten über dem Ergebnis
  scanStand = ''; $('#scan-status').className = 'muted';
  if (scanModus !== 'erfassen') { $('#scan-status').textContent = 'Kamera starten, dann eine Karte davor halten.'; return; }  // Prüfen: das letzte Urteil bleibt stehen
  $('#scan-status').textContent = erfStart(); $('#scan-hit').innerHTML = '';
  messUi();
  if (erf.liste?.karten) $('#erf-liste').scrollIntoView();  // der nächste Schritt: Liste prüfen und übernehmen
}
const scanTeile = st => [...[...new Set(st.deck)].map(d => ['deck', 'Deck: ' + d]), ...['keep', 'sell', 'bulk'].filter(k => st[k]).map(k => [k, LABEL[k]])];
const scanRow = e => {
  const k = scanIx.karten[e.oid];
  return `<div class="row" data-oid="${esc(e.oid)}"${peekAt(e.bild, k.name, eur(e.preis))}>${pic(small(e.bild), '', 'thumb')}<div class="min0"><div class="name">${esc(k.name)}</div><div class="sub2">${esc(e.druck)}</div></div>
    <div class="chips">${stackChips(k.stacks)}</div><div class="price">${eur(e.preis)}</div></div>`;
};
const KAMERA_TIPPS = [['Licht', 'Gleichmäßig und hell, am besten Tageslicht oder eine Lampe schräg von der Seite. Eine Lampe direkt über der Karte spiegelt. Die Taschenlampe nur im Dunkeln, auf Foils und Hüllen blendet sie.'],
  ['Hintergrund', 'Einfarbig und matt, etwa eine Spielmatte. Dann findet die App die Karte überall im Bild und merkt sofort, wann sie weg ist. Auf Holz mit starker Maserung oder zwischen anderen Karten hilft der Rahmen in der Mitte.'],
  ['Hüllen', 'Matte Hüllen gehen gut, glänzende spiegeln. Spiegelt es, die Karte leicht kippen oder aus der Hülle nehmen.'],
  ['Foils', 'Der Glanz stört die Erkennung: Karte kippen, bis die Spiegelung weg ist. Ob eine Karte Foil ist, sieht die Kamera nicht, das stellst du beim Erfassen ein.'],
  ['Halten', 'Die ganze Karte ins Bild, aufrecht und ruhig. Das Handy aufstützen oder die Karte hinlegen hilft.'],
  ['Stapel', 'Fertige Karten außerhalb des Bilds ablegen. Liegt eine gezählte Karte später wieder ruhig im Bild, zählt die App sie noch einmal.']];
const SCAN_MODI = [['pruefen', 'Prüfen'], ['erfassen', 'Erfassen']];
const scanKopf = modus => head('Scannen', modus === 'erfassen' ? 'Neue Karten erfassen: Karten nacheinander vor die Kamera halten. Jede erkannte Karte kommt auf die Scan-Liste, nach dem Prüfen übernimmst du alle in einen Binder.'
  : 'Halte eine Karte aus deiner Sammlung vor die Kamera. Die App sagt dir, wohin sie gehört: in ein Deck, behalten, verkaufen oder Bulk.',
  `<div class="seg" role="group" aria-label="Was die Kamera tut">${SCAN_MODI.map(([k, l]) => `<button class="btn small" type="button" data-modus="${k}" aria-pressed="${k === modus}">${l}</button>`).join('')}</div>`);
const camBox = (bereit, status) => `<section class="split scan ${scanModus}" aria-label="Kamera und Ergebnis">
    <div class="sec"><div class="toolbar camleiste"><div class="voll-oben nur-voll"><button class="btn" type="button" id="voll-zu" aria-label="Kamera beenden">${icon('x')}</button><span id="voll-summe">${scanModus === 'erfassen' ? '' : 'Karte prüfen'}</span>
          ${scanModus === 'erfassen' ? '<button class="btn" type="button" data-blatt="erf-setup">Einstellungen</button>' : ''}</div>
        <select id="cam" aria-label="Kamera" hidden></select>
        <div class="voll-rand"><button class="btn" type="button" id="cam-lampe" aria-pressed="false" hidden>${icon('flashlight')}Licht</button>${scanModus === 'erfassen' ? `<button class="btn nur-voll" type="button" data-blatt="erf-liste">Liste</button>
          <button class="btn nur-voll" type="button" data-messbild aria-label="Bild aufnehmen" hidden>Bild</button>` : ''}</div>
        <button class="btn primary" type="button" id="cam-go"${bereit ? '' : ' disabled'}>Kamera starten</button></div>
      <div class="cam" id="cam-box"><video id="cam-video" playsinline muted></video>
        <svg class="lage" id="cam-lage" preserveAspectRatio="xMidYMid slice" aria-hidden="true" hidden><path class="aussen"/><rect class="rahmen"/><polygon class="viereck"/></svg></div>
      <p class="note-line" id="cam-aufl" hidden></p>
      <div class="toolbar gap-top" id="cam-mess" hidden><button class="btn" type="button" data-messbild disabled>Bild aufnehmen</button>${info('messausloeser', 'Bild aufnehmen')}
        <span class="muted small-print">Messbilder an: Jedes gezählte Kamerabild geht an deinen Server.</span></div>
      <p class="note-line">${esc(scanModus !== 'erfassen' ? TIP.scan : erf.alle ? TIP.erfassenAlle : TIP.erfassen)}</p>
      <details class="suchhilfe"><summary>Tipps für gute Erkennung</summary><dl>${KAMERA_TIPPS.map(([k, t]) => `<dt>${k}</dt><dd>${esc(t)}</dd>`).join('')}</dl></details></div>
    <div class="sec scanres" aria-live="polite"><div id="scan-status" class="muted">${status}</div><div id="scan-hit"></div></div>
    ${scanModus === 'erfassen' ? `<div class="schnell nur-voll" role="group" aria-label="Vorgaben für die nächste Karte">
      <select data-erfvor="foil" aria-label="Foil">${optionen(FOIL, erf.foil)}</select><select data-erfvor="lang" aria-label="Sprache">${optionen(LANG_KURZ, erf.lang)}</select>
      <select data-erfvor="cond" aria-label="Zustand">${optionen(COND_KURZ, erf.cond)}</select>
      <button class="btn primary" type="button" data-erfplus aria-label="Eine weitere Kopie der letzten Karte">${icon('plus', 'sm')}1</button></div>` : ''}
  </section>`;
const scanModusWahl = e => {  // Reiter Prüfen/Erfassen; die Wahl merkt sich der Browser (am Handy wird meist erfasst)
  const b = e.target.closest('[data-modus]');
  if (!b) return false;
  merke('mtg-scan-modus', b.dataset.modus);
  location.hash = b.dataset.modus === 'erfassen' ? '#/scan?modus=erfassen' : '#/scan?modus=pruefen';
  return true;
};

async function viewScan(p) {
  scanStand = ''; scanKons = null;
  scanModus = merk('mtg-scan-modus', 'pruefen', SCAN_MODI);
  if (p.get('modus')) scanModus = p.get('modus') === 'erfassen' ? 'erfassen' : 'pruefen';
  if (scanModus === 'erfassen') return viewErfassen(p.get('deck') === '1');
  const r = await api('scan?v=' + FP_V);
  scanIx = r.ids.length ? fpIndex(r) : null;
  main.innerHTML = `${scanKopf('pruefen')}
    <div id="scan-prep"></div>
    ${camBox(scanIx, scanIx ? 'Kamera starten, dann eine Karte davor halten.' : 'Erst die Erkennungsbilder vorbereiten.')}
    <div class="toolbar">${schnellSchalter()}</div>
    <section class="sec" aria-label="Zuletzt gescannt"><h2>Zuletzt gescannt</h2><div class="rows" id="scan-log">${scanIx && scanLog.length ? scanLog.map(scanRow).join('') : '<p class="muted">Noch nichts.</p>'}</div></section>`;
  $('#cam-go').onclick = () => scanStart();
  $('#cam').onchange = e => scanStart(e.target.value);
  $('#scan-schnell').onchange = schnellSetzen;
  main.onclick = e => { if (scanModusWahl(e)) return; if (e.target.closest('#voll-zu')) return scanEnde(); const b = e.target.closest('[data-scanpick]'); if (b) scanTreffer(+b.dataset.scanpick); };
  if (!r.fehlt.length) return;
  const lauf = async () => {  // einmalig alle, später nur neue Drucke (nach einem Import)
    $('#scan-prep').innerHTML = `<div class="note"><span class="ic">${icon('cloud')}</span><div class="min0"><b>Erkennungsbilder werden vorbereitet</b>
      <div class="muted">${num(r.fehlt.length)} Drucke, ein paar Minuten. Die Seite muss so lange offen bleiben.</div><div class="progress"><span style="--p:0"></span></div></div><span></span></div>`;
    await fpJob(r.fehlt, (a, n) => $('#scan-prep .progress span')?.style.setProperty('--p', a / n));
    const neu = await api('scan?v=' + FP_V);
    scanIx = neu.ids.length ? fpIndex(neu) : null;
    if (!$('#scan-prep')) return;
    $('#scan-prep').innerHTML = '';
    $('#cam-go').disabled = !scanIx;
    if (!scanStream) $('#scan-status').textContent = 'Bereit. Kamera starten, dann eine Karte davor halten.';
  };
  if (scanIx && r.fehlt.length <= 60) return lauf();  // ein paar neue Karten: still nachrechnen
  $('#scan-prep').innerHTML = note(['cloud', 'Erkennungsbilder vorbereiten', `Einmal nötig: Die App merkt sich von jedem deiner ${num(r.fehlt.length)} Drucke ein kleines Bild von Scryfall. Das dauert ein paar Minuten, die Seite muss so lange offen bleiben.`,
    `<button class="btn primary" type="button" id="scan-job">${icon('cloud')}Jetzt vorbereiten</button>`]);
  $('#scan-job').onclick = lauf;
}

async function scanStart(deviceId) {
  const voll = document.body.classList.contains('vollbild');  // andere Kamera gewählt: im Vollbild bleiben
  tonAn();
  scanStop();
  document.body.classList.toggle('vollbild', voll);
  const st = $('#scan-status');
  if (!navigator.mediaDevices?.getUserMedia) { st.textContent = TIP.scanhttps; return; }
  let gemerkt = null;
  try { gemerkt = localStorage.getItem('mtg-cam'); } catch { /* ohne Speicher: Standardkamera */ }
  const id = deviceId || gemerkt;
  try {
    scanStream = await navigator.mediaDevices.getUserMedia({audio: false, video: {width: {ideal: 1920}, height: {ideal: 1080}, ...(id ? {deviceId: {ideal: id}} : {facingMode: 'environment'})}});
  } catch (e) { st.textContent = `Keine Kamera: ${e.name === 'NotAllowedError' ? 'Zugriff abgelehnt. Erlaube die Kamera für diese Seite in der Adresszeile.' : e.message}`; return; }
  const v = $('#cam-video');
  if (!v) return scanStop();  // Ansicht schon verlassen
  v.srcObject = scanStream;
  await v.play();
  const aktiv = scanStream.getVideoTracks()[0].getSettings().deviceId;
  try { localStorage.setItem('mtg-cam', aktiv); } catch { /* egal */ }
  const devs = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === 'videoinput'), sel = $('#cam');
  sel.innerHTML = devs.map((d, i) => `<option value="${esc(d.deviceId)}"${d.deviceId === aktiv ? ' selected' : ''}>${esc(d.label || 'Kamera ' + (i + 1))}</option>`).join('');
  sel.hidden = devs.length < 2;  // nur eine Kamera: nichts zu wählen
  // Handy (Phase 27): Dauerfokus und Taschenlampe, nur wo die Kamera sie kann; sonst bleibt alles wie gehabt
  const track = scanStream.getVideoTracks()[0], cap = track.getCapabilities?.() || {}, lampe = $('#cam-lampe');
  if (cap.focusMode?.includes('continuous')) track.applyConstraints({advanced: [{focusMode: 'continuous'}]}).catch(() => {});
  lampe.hidden = !cap.torch; lampe.setAttribute('aria-pressed', 'false');
  lampe.onclick = async () => {
    const an = lampe.getAttribute('aria-pressed') !== 'true';
    try { await track.applyConstraints({advanced: [{torch: an}]}); lampe.setAttribute('aria-pressed', String(an)); } catch { lampe.hidden = true; }
  };
  sel.closest('.toolbar').hidden = sel.hidden && lampe.hidden;
  wachHalten();
  const vw = v.videoWidth, vh = v.videoHeight;
  $('#cam-box').style.aspectRatio = `${vw} / ${vh}`;
  document.body.classList.add('vollbild');
  scanBox = ''; scanRahmenZeigen(v); scanViereck(null);
  $('#cam-lage').removeAttribute('hidden'); $('#cam-go').hidden = true;
  const aufl = $('#cam-aufl');  // eigene Zeile: die Statuszeile wechselt mit jeder Karte
  aufl.hidden = vw * vh >= 1280 * 720;
  aufl.textContent = `Die Kamera liefert nur ${vw} × ${vh} Pixel, darunter leidet die Erkennung. Gutes Licht hilft${sel.hidden ? '' : ', oder eine andere Kamera wählen'}.`;
  st.textContent = 'Karte vor die Kamera halten.';
  if (scanModus === 'erfassen') erfKamera();
  scanLoop();
  blaetternStart(v);
}

// Rahmen g (Pixel in src) samt 8 % Rand auf 300 px Kartenbreite (doppelt so groß wie das Scryfall-Bild im Index). src ist das Kamerabild oder
// ein Messbild (tests/messbilder_eval.js, tests/suche_eval.js): beide laufen durch denselben Ausschnitt. -> Quelle, Mitte und Kartengröße für
// fingerprint, fpSuche und fpLagen
// Statt des Rahmens geht auch ein Viereck aus karteFinden (g.e, Phase 33): Dann wird die Karte entzerrt, also jedes Pixel des Ziels über die
// Abbildung Einheitsquadrat -> Viereck (Heckbert) aus der Quelle geholt. Die Quelle ist dafür erst auf etwa die Zielgröße verkleinert (das
// mittelt der Browser sauber), geholt wird zwischen vier Nachbarn gemittelt.
function scanBild(src, g) {
  const m = .08, kw = 300, kh = kw * 88 / 63, bw = scanWork.width = Math.round(kw * (1 + 2 * m)), bh = scanWork.height = Math.round(kh * (1 + 2 * m));
  const c = scanWork.getContext('2d', {willReadFrequently: true});
  c.imageSmoothingQuality = 'high';
  if (!g.e) c.drawImage(src, g.x - m * g.w, g.y - m * g.h, g.w * (1 + 2 * m), g.h * (1 + 2 * m), 0, 0, bw, bh);
  else {
    const [[x0, y0], [x1, y1], [x2, y2], [x3, y3]] = g.e, dx1 = x1 - x2, dx2 = x3 - x2, sx = x0 - x1 + x2 - x3, dy1 = y1 - y2, dy2 = y3 - y2, sy = y0 - y1 + y2 - y3;
    const den = dx1 * dy2 - dx2 * dy1, hg = (sx * dy2 - dx2 * sy) / den, hh = (dx1 * sy - sx * dy1) / den;
    const ha = x1 - x0 + hg * x1, hb = x3 - x0 + hh * x3, hd = y1 - y0 + hg * y1, he = y3 - y0 + hh * y3;
    const rand = [[-m, -m], [1 + m, -m], [1 + m, 1 + m], [-m, 1 + m]].map(([u, v]) => { const w = hg * u + hh * v + 1; return [(ha * u + hb * v + x0) / w, (hd * u + he * v + y0) / w]; });
    const qx = Math.floor(Math.min(...rand.map(p => p[0]))), qy = Math.floor(Math.min(...rand.map(p => p[1])));
    const qw = Math.ceil(Math.max(...rand.map(p => p[0]))) - qx, qh = Math.ceil(Math.max(...rand.map(p => p[1]))) - qy, f = Math.min(1, Math.max(bw / qw, bh / qh));
    const tw = scanQuelle.width = Math.max(2, Math.round(qw * f)), th = scanQuelle.height = Math.max(2, Math.round(qh * f));
    const t = scanQuelle.getContext('2d', {willReadFrequently: true});
    t.imageSmoothingQuality = 'high';
    t.drawImage(src, qx, qy, qw, qh, 0, 0, tw, th);
    const sp = t.getImageData(0, 0, tw, th).data, out = c.createImageData(bw, bh), o = out.data, z = tw * 4;
    for (let j = 0, p = 0; j < bh; j++) for (let i = 0, v = (j + .5) / kh - m; i < bw; i++, p += 4) {
      const u = (i + .5) / kw - m, w = hg * u + hh * v + 1;
      const X = ((ha * u + hb * v + x0) / w - qx) * tw / qw - .5, Y = ((hd * u + he * v + y0) / w - qy) * th / qh - .5, xi = Math.floor(X), yi = Math.floor(Y);
      if (xi < 0 || yi < 0 || xi >= tw - 1 || yi >= th - 1) continue;  // neben dem Bild: bleibt leer wie beim Rahmen am Bildrand
      const ax = X - xi, ay = Y - yi, q = yi * z + xi * 4;
      for (let k = 0; k < 3; k++) o[p + k] = (sp[q + k] * (1 - ax) + sp[q + 4 + k] * ax) * (1 - ay) + (sp[q + z + k] * (1 - ax) + sp[q + z + 4 + k] * ax) * ay;
      o[p + 3] = 255;
    }
    c.putImageData(out, 0, 0);
  }
  return [scanWork, bw / 2, bh / 2, kw, kh];
}
const scanSuche = (ix, src, g, k) => fpSuche(ix, ...scanBild(src, g), k);
// Phase 35 (PLAN E21): Streifen mit der Namenszeile für die Texterkennung auf dem Server (POST /api/scan/titel). g wie bei scanBild (Rahmen
// oder Viereck g.e), geschnitten aber aus dem vollen Kamerabild: Die Schrift ist klein, 300 px Kartenbreite reichen ihr nicht. Der Streifen
// ist schmal: Drei Ecken des Felds genügen (schief statt perspektivisch). kontrast: Graustufen, das hellste und dunkelste Dreißigstel
// abgeschnitten und auf den vollen Umfang gespreizt. TITEL_VERSUCHE in dieser Reihenfolge, bis der Server einen Namen findet: erst eng um die
// Namenszeile mit Kontrast, dann großzügig (so liegt der Name auch darin, wenn das Viereck der innere Rahmen statt des Kartenrands ist).
// Gemessen mit tests/titel_eval.js (PLAN Phase 35): Breite, Ausschnitte und Kontrast kommen von dort, vor einer Änderung neu messen.
const TITEL_W = 800, TITEL_VERSUCHE = [{box: [.05, .035, .95, .11], kontrast: true}, {box: [.04, .015, .96, .125]}], titelWork = document.createElement('canvas');
function titelBild(src, g, {box = TITEL_VERSUCHE[0].box, breite = TITEL_W, kontrast = false} = {}) {
  const [l, t, r, b] = box, e = g.e || [[g.x, g.y], [g.x + g.w, g.y], [g.x + g.w, g.y + g.h], [g.x, g.y + g.h]];
  const P = (u, v) => [0, 1].map(i => e[0][i] * (1 - u) * (1 - v) + e[1][i] * u * (1 - v) + e[2][i] * u * v + e[3][i] * (1 - u) * v);
  const [ax, ay] = P(l, t), [bx, by] = P(r, t), [cx, cy] = P(l, b);
  const w = titelWork.width = breite, h = titelWork.height = Math.max(8, Math.round(breite * Math.hypot(cx - ax, cy - ay) / Math.hypot(bx - ax, by - ay)));
  const c = titelWork.getContext('2d', {willReadFrequently: true});
  c.imageSmoothingQuality = 'high';
  c.setTransform(new DOMMatrix([(bx - ax) / w, (by - ay) / w, (cx - ax) / h, (cy - ay) / h, ax, ay]).inverse());  // Quelle -> Streifen
  c.drawImage(src, 0, 0);
  c.setTransform(1, 0, 0, 1, 0, 0);
  if (kontrast) {
    const d = c.getImageData(0, 0, w, h), px = d.data, n = w * h, grau = new Uint8Array(n), zahl = new Uint32Array(256);
    for (let i = 0; i < n; i++) { grau[i] = .299 * px[i * 4] + .587 * px[i * 4 + 1] + .114 * px[i * 4 + 2]; zahl[grau[i]]++; }
    let lo = 0, hi = 255;
    for (let s = 0; (s += zahl[lo]) < n / 30;) lo++;
    for (let s = 0; (s += zahl[hi]) < n / 30;) hi--;
    for (let i = 0, f = 255 / Math.max(1, hi - lo); i < n; i++) px[i * 4] = px[i * 4 + 1] = px[i * 4 + 2] = Math.max(0, Math.min(255, (grau[i] - lo) * f));
    c.putImageData(d, 0, 0);
  }
  return titelWork;
}
// Suche im Browser je Kamerabild: erst die frei gefundenen Vierecke (freiSuche), erkennt sie in keinem eine Karte, der Rahmen in der Mitte
function sucheLokal(ix, src, g, vierecke) {
  const frei = freiSuche(ix, src, vierecke);
  if (frei[0]?.score >= FP_NEIN) return frei;
  const rahmen = scanSuche(ix, src, g);
  return frei[0]?.score > (rahmen[0]?.score ?? -1) ? frei : rahmen;
}
// Viereck q, das gerade zur erkannten Karte führte, über dem Kamerabild zeigen (sonst den Rahmen) -> liegt es ruhig, also seine Mitte etwa dort,
// wo sie im Bild davor lag (höchstens FIND_RUHIG der Kartenbreite daneben; die Mitte, weil mal der Kartenrand und mal der innere Rahmen zur
// Karte führt)? Ohne Viereck (Rahmen) immer: Gezählt wird nur, was ruhig liegt.
function scanViereck(q) {
  const lage = $('#cam-lage'), alt = scanQ;
  if (lage) { lage.classList.toggle('frei', !!q); if (q) $('.viereck', lage).setAttribute('points', q.e.map(p => p.map(Math.round).join()).join(' ')); }
  scanQ = q ? [0, 1].map(i => (q.e[0][i] + q.e[1][i] + q.e[2][i] + q.e[3][i]) / 4) : null;
  scanBei = q ? [...scanQ, FIND_RUHIG * Math.hypot(q.e[1][0] - q.e[0][0], q.e[1][1] - q.e[0][1])] : null;  // für Konsens: dasselbe Viereck wie qBei
  scanVier = q || null;  // für die Stapelzone (Phase 57)
  return !q || (!!alt && Math.hypot(scanQ[0] - alt[0], scanQ[1] - alt[1]) < FIND_RUHIG * Math.hypot(q.e[1][0] - q.e[0][0], q.e[1][1] - q.e[0][1]));
}
// Suche auf dem Server (Phase 32): die Fingerabdrücke der Lagen FP_VOR als base64; leer, wenn keine Karte im Rahmen liegt (einfarbige Fläche)
const fpLagen = (src, cx, cy, w, h) => fingerprint(src, cx, cy, w, h).sd < FP_FLACH ? [] : FP_VOR.map(([dx, dy]) => fpB64(fingerprint(src, cx + dx * w, cy + dy * h, w, h)));
// Erkennung für die Vierecke aus karteFinden (Phase 33). Ein Viereck ist der Kartenrand oder, wo der Rand keine Kante hat (schwarzer Rand auf
// dunkler Matte), der innere Rahmen: Dann ist die Karte um den schwarzen Rand größer (FIND_RAND: links und rechts, oben, unten als Anteil des
// Vierecks, gemessen am heutigen Kartenrahmen; alte Rahmen haben unten weniger). Je Viereck einmal entzerren, dann beide Größen prüfen, die
// wahrscheinlichere zuerst (außen heller: Kartenrand). Die Ecken sind gefunden, deshalb genügt ein Fingerabdruck gegen alle (FREI_VOR) und für
// die besten Kandidaten zehn Lagen (FREI_LAGEN: Versatz, Höhe bei festem oberen Rand, Größe, Drehung) statt der 50 für den Rahmen: gemessen
// gleich gut wie alle 50 und dreimal so schnell. Das erste sichere Ergebnis gilt, sonst das beste. q = das Viereck dazu.
const FIND_RAND = [.046, .031, .09];
const FREI_VOR = [[0, 0]], FREI_LAGEN = [[.03, 0, 1, 0], [-.03, 0, 1, 0], [0, .03, 1, 0], [0, -.03, 1, 0], [0, .02, 1, 0, 1.04], [0, -.02, 1, 0, .96], [0, 0, 1.04, 0], [0, 0, .96, 0], [0, 0, 1, 3], [0, 0, 1, -3]];
const freiLagen = ([src, cx, cy, w, h], hell) => { const l = [[src, cx, cy, w, h], [src, cx, cy + (FIND_RAND[2] - FIND_RAND[1]) / 2 * h, w * (1 + 2 * FIND_RAND[0]), h * (1 + FIND_RAND[1] + FIND_RAND[2])]]; return hell ? l : l.reverse(); };
function freiSuche(ix, src, vierecke, k = 3) {
  let best = [];
  for (const q of vierecke) for (const lage of freiLagen(scanBild(src, q), q.hell)) {
    const r = fpSuche(ix, ...lage, k, FREI_VOR, FREI_LAGEN);
    if (r.length && !(best[0]?.score >= r[0].score)) { best = r; best.q = q; }
    if (best[0]?.score >= FP_SICHER) return best;
  }
  return best;
}
// Dasselbe mit der Suche auf dem Server -> seine beste Antwort oder null. Ein Viereck ist nicht immer eine Karte, und unter allen Karten
// findet sich auch für ein Stück Spielmatte manchmal eine, die der Server sicher nennt (gemessen: 3 von 300 Szenen, je mit 0,08 bis 0,10 Abstand
// zum nächsten Bild; neun von zehn richtigen Treffern liegen über 0,12). Deshalb gilt ein Viereck erst ab FREI_ABSTAND als sicher, darunter
// fragt die App.
const FREI_ABSTAND = .12;
async function freiServer(src, vierecke, mehr = {}) {
  let best = null;
  for (const q of vierecke) for (const lage of freiLagen(scanBild(src, q), q.hell)) {
    const fp = fpLagen(...lage);
    if (!fp.length) continue;
    const a = await post('scan/suche', {v: FP_V, fp, ...mehr});
    if (a.urteil === 'sicher' && !a.titel && a.treffer[0].abstand < FREI_ABSTAND) a.urteil = 'unsicher';  // mit gelesenem Namen (Phase 35) urteilt der Server aus Name und Bild
    if (a.urteil === 'sicher') return {...a, q};
    if (a.treffer.length && !(best?.treffer[0].wert >= a.treffer[0].wert)) best = {...a, q};
  }
  return best;
}

// --- Mini-Bild je Kamerabild (Phasen 56 und 57, PLAN E37, E38) ---------------------------------------------------------------------------
// Neben der Erkennung (scanLoop, 120 ms und länger je Bild) misst eine eigene Schleife im Takt der Kamera (requestVideoFrameCallback, sonst
// requestAnimationFrame) ein Mini-Bild des ganzen Kamerabilds (BLAETTERN_MINI Punkte, grau), nur mit „Schnell zählen“; aus: wie vorher.
// Ruhig (Phase 56): Hat sich im Viereck einer erkannten Karte in den RUHIG_BILDER Kamerabildern bis zum Bild der Erkennung nichts bewegt
// (Zaehler.ruhigIn, mittlere Änderung unter RUHIG_DIFF), liegt sie ruhig, auch wenn das Bild der Erkennung davor sie noch nicht kannte. So
// zählt Konsens „sofort“ auch frei im Bild nach einem Bild; im Rahmen gilt die Karte ohnehin als ruhig.
// Kopien (Phase 57): Die zuletzt gezählte Karte liegt in ihrer Stapelzone (der innere Teil BLAETTERN_INNEN des Vierecks bzw. Rahmens), die
// Mini-Bilder gehen an Zaehler.Kopien. Wird sie weggeschnippt und liegt eine gleiche darunter, zählt die App sie wie „+1“ (erfZaehlen), mit
// Zeugen von selbst (BLAETTERN_SELBST), ohne Zeugen fragt sie in einer Zeile unter der Karte; nur beim Erfassen.
// Die Werte kommen aus dem Prüfstand (tests/blaettern_eval.js, PLAN Phasen 56 und 57): vor einer Änderung neu messen.
// Gemessen am 2026-10-18 (PLAN Phase 57): Von selbst gezählt stimmte die Zahl nur in 70 % der Folgen (Hürde 90 %), mit Frage bei jeder erkannten
// Kopie in 91 %, überzählt nie. Deshalb fragt die App (BLAETTERN_SELBST aus, der Rückweg aus dem Plan); die Werte von Zaehler.Kopien gelten.
const BLAETTERN_MINI = [48, 80], RUHIG_BILDER = 3, RUHIG_DIFF = 4, BLAETTERN_INNEN = .8, BLAETTERN_OPT = {}, BLAETTERN_SELBST = false;
const miniWork = document.createElement('canvas');
function miniBild(src, sw, sh) {  // -> {w, h, px} (Graubild, zeilenweise), hochkant oder quer wie das Kamerabild
  const [k, l] = BLAETTERN_MINI, w = sw > sh ? l : k, h = sw > sh ? k : l;
  if (miniWork.width !== w || miniWork.height !== h) { miniWork.width = w; miniWork.height = h; }
  const c = miniWork.getContext('2d', {willReadFrequently: true});
  c.imageSmoothingQuality = 'high';
  c.drawImage(src, 0, 0, w, h);
  const d = c.getImageData(0, 0, w, h).data, px = new Uint8Array(w * h);
  for (let i = 0, j = 0; i < px.length; i++, j += 4) px[i] = (77 * d[j] + 150 * d[j + 1] + 29 * d[j + 2]) >> 8;
  return {w, h, px};
}
// Rechteck um ein Viereck; Stapelzone im Mini-Bild aus einem Rechteck in Pixeln des Kamerabilds (sw breit)
const rechteck = q => { const xs = q.e.map(p => p[0]), ys = q.e.map(p => p[1]); return {x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys)}; };
const blaetternZone = (m, r, sw) => { const f = m.w / sw, i = (1 - BLAETTERN_INNEN) / 2; return [(r.x + r.w * i) * f, (r.y + r.h * i) * f, r.w * BLAETTERN_INNEN * f, r.h * BLAETTERN_INNEN * f]; };
// Kostet ein Mini-Bild im Mittel mehr als BLAETTERN_MS (am Rechner aus dem Hauptspeicher 0,1 bis 0,6 ms; was es aus dem Kamerabild kostet,
// hängt am Gerät), nimmt die Schleife nur jedes zweite, dritte oder vierte Kamerabild, damit die Erkennung nicht wartet.
const BLAETTERN_MS = 2;
let blaettern = null;  // {v, verlauf (die letzten Mini-Bilder), kop, id, wie (der gezählte Druck), ms (gleitendes Mittel), n}
function blaetternStart(v) {
  const strom = scanStream;
  blaettern = {v, verlauf: [], kop: new Zaehler.Kopien(BLAETTERN_OPT), id: null, wie: null, ms: 0, n: 0};
  const schritt = () => {
    if (scanStream !== strom || !blaettern) return;
    const b = blaettern;
    if (scanSchnell && v.readyState >= 2 && $('#voll-schleier')?.hidden !== false) {
      if (++b.n % Math.min(4, Math.max(1, Math.ceil(b.ms / BLAETTERN_MS))) === 0) {
        const t0 = performance.now(), m = miniBild(v, v.videoWidth, v.videoHeight);
        b.verlauf = [...b.verlauf.slice(-RUHIG_BILDER), m];
        if (scanModus === 'erfassen') { const r = b.kop.bild(m); if (r.ereignis) blaetternEreignis(r.ereignis); }
        b.ms = .9 * b.ms + .1 * (performance.now() - t0);
      }
    } else b.verlauf = [];
    if (v.requestVideoFrameCallback) v.requestVideoFrameCallback(schritt); else requestAnimationFrame(schritt);
  };
  schritt();
}
// lag das Viereck q in den Mini-Bildern verlauf (bis zum Bild der Erkennung) still? (Phase 56)
const miniRuhig = (q, verlauf) => !!q && !!blaettern && verlauf.length > RUHIG_BILDER && Zaehler.ruhigIn(verlauf, blaetternZone(verlauf[0], rechteck(q), blaettern.v.videoWidth), RUHIG_DIFF);
// eine Karte ist gezählt (erkannt, gewählt oder „+1“): ab jetzt ihre Stapelzone verfolgen (Phase 57)
function blaetternKarte(id, wie) {
  const b = blaettern, m = b?.verlauf.at(-1);
  $('#blaettern-frage')?.remove();
  if (b) b.offen = 0;
  if (!m || !scanSchnell || scanModus !== 'erfassen') return;
  Object.assign(b, {id, wie});
  b.kop.karte(m, blaetternZone(m, scanVier ? rechteck(scanVier) : scanG(b.v), b.v.videoWidth));
}
function blaetternEreignis(art) {
  const b = blaettern;
  if (!b?.id) return;
  if (art === 'kopie' && BLAETTERN_SELBST) {
    erfZug = {...erfZug, frei: false, fremd: 0};  // die Erkennung zählt dieselbe Karte nicht noch einmal
    erfZaehlen(b.id, b.wie);
    return;
  }
  // ohne Zeugen (oder BLAETTERN_SELBST aus) fragt die App; schnippst du weiter, sammelt die Frage die erkannten Kopien („3 weitere Kopien?“).
  // Die Erkennung zählt die Kopie dann nicht selbst (sonst zählte sie doppelt, wenn du die Frage auch beantwortest)
  erfZug = {...erfZug, frei: false, fremd: 0};
  const n = b.offen = (b.offen || 0) + 1, el = $('#blaettern-frage');
  const html = `${n === 1 ? 'Weitere Kopie gelegt?' : `${n} weitere Kopien gelegt?`} <button class="btn small primary" type="button" data-blaettern="${n}">${icon('plus', 'sm')}${n}</button>
    <button class="btn small" type="button" data-blaettern="0" aria-label="Keine weitere Kopie">${icon('x', 'sm')}</button>`;
  if (el) el.innerHTML = html;
  else $('#scan-hit .hit .min0')?.insertAdjacentHTML('beforeend', `<p class="note-line" id="blaettern-frage">${html}</p>`);
}

// je Bild eine Suche: Prüfen und Erfassen mit Set-Lock im Browser, Erfassen ohne Set-Wahl beim Server (die nächste erst nach seiner Antwort)
async function scanLoop() {
  const v = $('#cam-video'), strom = scanStream;
  let pause = 120;
  if (!v || !strom) return;
  if (v.readyState >= 2 && $('#voll-schleier')?.hidden !== false) {  // ein offenes Blatt verdeckt die Kamera: nichts zählen
    const g = scanRahmenZeigen(v), frei = scanFrei ? karteFinden(v, v.videoWidth, v.videoHeight) : [], verlauf = blaettern?.verlauf || [];
    const ruhig = q => scanViereck(q) || miniRuhig(q, verlauf);  // Mini-Bilder bis zu diesem Kamerabild (Phase 56)
    if (scanModus !== 'erfassen') { if (scanIx) { const best = sucheLokal(scanIx, v, g, frei); scanZeigen(best, ruhig(best[0]?.score >= FP_NEIN && best.q)); } }
    else if (!erf.alle) { if (erfIx?.codes === erf.sets.join()) { const best = sucheLokal(erfIx.ix, v, g, frei); erfZeigen(erfLokal(best), ruhig(best[0]?.score >= FP_NEIN && best.q)); } }
    else {
      try { const r = await erfServer(v, g, frei); if (scanStream === strom) erfZeigen(r, ruhig(r.urteil !== 'nichts' && r.q)); }
      catch (e) { if (e instanceof LoginNoetig) return; pause = 1500; if (scanStream === strom) erfStatus('netz'); }
    }
  }
  if (scanStream === strom) scanTimer = setTimeout(scanLoop, pause);  // sonst: Kamera inzwischen aus oder neu gestartet
}

function scanZeigen(best, ruhig = true) {
  const b = best[0], st = $('#scan-status');
  if (!st) return;
  const sicher = b && b.score >= FP_SICHER, stand = !b || b.score < FP_NEIN ? 'leer' : sicher ? 'sicher' : 'unsicher:' + best.map(x => x.oid).join();
  const k = konsens('lokal').bild({urteil: stand.split(':')[0], id: b?.oid, oid: b?.oid, wert: b?.score, abstand: b && (best[1] ? b.score - best[1].score : 1), ruhig, bei: scanBei});
  if (k.zaehlen) scanTreffer(b.i);  // genau einmal je Karte im Rahmen; nimmst du sie raus und legst die nächste hin, zählt es neu
  if (stand === scanStand) return;  // nur bei Änderung neu zeichnen, sonst flackert es und Klicks gehen verloren
  scanStand = stand;
  $('#scan-hit .hit')?.classList.toggle('alt', stand !== 'sicher' && stand !== 'leer');  // unsicher: das Urteil darunter gehört zur Karte davor
  st.className = stand === 'sicher' ? '' : 'muted';
  st.innerHTML = stand === 'leer' ? 'Keine Karte aus deiner Sammlung im Bild.' : stand === 'sicher' ? 'Erkannt.'
    : `Unsicher. Ist es eine davon? <div class="kand">${best.map(x => {
      const k = scanIx.karten[x.oid];
      return `<button type="button" class="kandb" data-scanpick="${x.i}" title="${esc(k.name)}">${pic(small(scanIx.bilder[x.i]), k.name)}</button>`;
    }).join('')}</div>`;
}

function scanTreffer(i) {  // gezeigt wird der erkannte Druck (Bild, Set, Preis), das Urteil gilt für die Karte
  const oid = scanIx.oids[i], k = scanIx.karten[oid], preis = scanIx.preise[i], bild = scanIx.bilder[i], druck = scanIx.drucke[i], teile = scanTeile(k.stacks);
  ton();
  scanLog = [{oid, preis, bild, druck}, ...scanLog].slice(0, 20);
  $('#scan-hit').innerHTML = `<div class="hit"><a href="#" data-oid="${esc(oid)}" aria-label="${esc(k.name)} ansehen">${pic(small(bild), k.name)}</a><div class="min0">
    <div class="name">${esc(k.name)}</div>
    ${teile.length === 1 ? `<div class="urteil u-${teile[0][0]}">${esc(teile[0][1])}</div>` : `<div class="urteil">${teile.length === 2 ? esc(teile.map(t => t[1]).join(' oder ')) : teile.length ? 'Mehrere Stapel' : 'Kein Stapel'}</div><div class="chips big">${stackChips(k.stacks, true)}</div>`}
    <div class="sub2">${esc(druck)}, ${eur(preis)}</div></div></div>`;
  $('#scan-log').innerHTML = scanLog.map(scanRow).join('');
}

// --- Erfassen (Phase 25, PLAN E18) mit Scan-Liste (Phase 29, wie ManaBox): neue Karten erkennen, erst prüfen, dann in einen Scan-Binder ---
// Zwei Wege (erf.alle). Ohne Set-Wahl (Phase 32, PLAN E20): Der Browser rechnet nur die Fingerabdrücke der Karte im Rahmen (fpLagen), der Server
// sucht sie unter allen Kartenbildern (POST /api/scan/suche) und wählt den Druck nach dem Zusammenhang: bevorzugte Sets (erf.sets), Sets der
// letzten Karten (erf.kontext), sonst der neueste; ist er geraten, steht die Zeile auf der Scan-Liste als „Druck prüfen“. Mit Set-Lock (Phase 25):
// Index nur aus den Drucken der gewählten Sets (GET /api/scan?set=…), je Druck verschieden. Gezählt wird, wenn derselbe Druck zweimal nacheinander
// sicher erkannt ist, er FP_ABSTAND vor dem zweitbesten liegt und der Rahmen seit der letzten Karte leer war (ERF_FREI Bilder ohne Treffer) oder eine
// andere Karte darin liegt; weitere Kopien derselben Karte mit „+1“. Gleiches Bild in zwei gewählten Sets: Auswahl mit Kürzel, nie raten. Jede Karte
// geht sofort auf die Scan-Liste des Servers (Zug-Kennung: doppelt gesendet zählt einmal), mit den anderen Kandidaten zum Tauschen beim Prüfen;
// erst „Übernehmen“ legt die geprüfte Liste in einen Scan-Binder.
const FP_ABSTAND = 0.03;  // vor dem Echttest geschätzt (PLAN Phase 25): darunter zählt nichts von selbst, die App fragt
const ERF_FREI = 4;       // so viele Bilder nacheinander ohne Karte aus den Sets gelten als „Karte herausgenommen“
// Schnell zählen (Phase 56, PLAN E37, E38): Konsens über mehrere Bilder (ui/zaehler.js) statt zweier sicherer nacheinander. Sofort zählt ein
// ruhiges Bild mit Wert und Abstand ab KONS_SOFORT_*, gestützt (unsicher, aber ab KONS_GESTUETZT_WERT und mit dem Abstand des Urteils) zählt
// mit zwei weiteren Bildern derselben Karte, von denen eins sicher ist. Getrennt für den Index im Browser (lokal: Prüfen und Set-Lock) und die
// Suche auf dem Server (Werte und Schwellen sind dort andere, katalog.SUCHE_*). Die Zahlen kommen aus der Messung (tests/suche_eval.js,
// tests/finden_eval.js; PLAN Phase 56): vor einer Änderung neu messen. Aus: wie vor Phase 56.
// Gemessen am 2026-10-18 (PLAN Phase 56): Kein falscher Treffer lag lokal über Wert 0,813 oder Abstand 0,098, auf dem Server über Abstand
// 0,128; sofort liegt mit gut 0,02 Reserve darüber. Gestützt bleibt aus (unendlich): Es zählte 1 bis 3 % mehr Karten, aber knapp unter der
// Schwelle auch falsche (Server bei 0,65: 2 von 200 Folgen, lokal bei 0,76: 5 falsche Bilder).
const KONS_SOFORT_WERT = {lokal: .86, server: .75}, KONS_SOFORT_ABSTAND = {lokal: .12, server: .15};
const KONS_GESTUETZT_WERT = {lokal: Infinity, server: Infinity}, KONS_GESTUETZT_ABSTAND = {lokal: FP_ABSTAND, server: .08};
let scanSchnell = merk('mtg-scan-schnell', '0', [['1'], ['0']]) === '1', scanKons = null;
const schnellSchalter = () => `<label class="inl"><input type="checkbox" id="scan-schnell"${scanSchnell ? ' checked' : ''}> Schnell zählen ${info('schnell', 'Schnell zählen')}</label>`;
const schnellSetzen = e => { scanSchnell = e.target.checked; merke('mtg-scan-schnell', scanSchnell ? '1' : '0'); };  // gilt fürs Prüfen und Erfassen
const konsens = weg => scanKons?.weg === weg && scanKons.schnell === scanSchnell ? scanKons : (scanKons = Object.assign(new Zaehler.Konsens({schnell: scanSchnell,
  sofortWert: KONS_SOFORT_WERT[weg], sofortAbstand: KONS_SOFORT_ABSTAND[weg], gestuetztWert: KONS_GESTUETZT_WERT[weg], gestuetztAbstand: KONS_GESTUETZT_ABSTAND[weg]}), {weg}));
const ERF_ZULETZT_H = 12; // so lange bietet die Liste an, die zuletzt übernommene Erfassung zurückzuholen
const FOIL = {normal: 'Normal', foil: 'Foil', etched: 'Etched Foil'};
// Schnellwahl im Vollbild (Phase 34): vier Felder in einer Zeile, deshalb Kürzel (Sprache wie Scryfall, Zustand wie Cardmarket)
const LANG_KURZ = Object.fromEntries(Object.keys(LANG).map(k => [k, {zh_CN: 'ZHS', zh_TW: 'ZHT'}[k] || k.toUpperCase()]));
const COND_KURZ = {mint: 'MT', near_mint: 'NM', excellent: 'EX', good: 'GD', light_played: 'LP', played: 'PL', poor: 'PO'};
const erfArt = z => [`${z.set_code} #${z.number}`, z.foil !== 'normal' && FOIL[z.foil], LANG[z.language] || z.language, COND[z.condition] || z.condition].filter(Boolean).join(', ');
const optionen = (obj, sel) => Object.entries(obj).map(([v, l]) => `<option value="${esc(v)}"${v === sel ? ' selected' : ''}>${esc(l)}</option>`).join('');
let erf = null, erfIx = null, erfSetsAlle = null, erfZug = {frei: true, wahl: false, oids: [], fremd: 0, anders: 0}, erfNr = 0, erfKette = Promise.resolve(), erfBest = [], erfKand = [], katJob = null, katalogTimer = null;
const erfMerken = () => merke('mtg-erfassen', JSON.stringify({sets: erf.sets, binder: erf.binder, lang: erf.lang, cond: erf.cond, foil: erf.foil, mess: erf.mess, huelle: erf.huelle, alle: erf.alle, titel: erf.titel}));
// Scans, die den Server nicht erreicht haben, merkt sich der Browser je Sammlung: Sie überstehen den Neuaufbau der Ansicht und das Neuladen
const erfOffenKey = () => 'mtg-erf-offen:' + (sess.aktiv || '');
const erfOffenMerken = () => merke(erfOffenKey(), JSON.stringify(erf.offen));
const uhr = iso => new Date(iso).toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'});
const erfSetName = c => erfSetsAlle?.find(x => x.code === c)?.name || c;

async function viewErfassen(deck = false) {  // deck (Phase 60): aus „Deck einscannen“, die Liste wird ein fertiges Deck
  let alt = {}, offen = [];
  try { alt = JSON.parse(localStorage.getItem('mtg-erfassen') || '{}'); offen = JSON.parse(localStorage.getItem(erfOffenKey()) || '[]'); } catch { /* privates Fenster: Standard */ }
  const [ei, kat] = await Promise.all([api('erfassen'), api('scan/katalog?v=' + FP_V)]), heute = ei.vorschlag;
  const binder = deck ? '' : !alt.binder || (/^Scan \d{4}-\d\d-\d\d$/.test(alt.binder) && alt.binder !== heute) ? heute : alt.binder;  // gestriger Standardname: heute ein neuer
  erf = {sets: alt.sets || [], binder, deck, decks: new Set(ei.binder.filter(b => b.deck).map(b => b.name)), lang: alt.lang || 'en', cond: alt.cond || 'near_mint', foil: alt.foil || 'normal', liste: ei.liste, zuletzt: ei.zuletzt, offen, letzte: null,
         mess: !!alt.mess, huelle: !!alt.huelle, messStand: null, alle: alt.alle === true, titel: alt.titel !== false, kat, kontext: []};
  erfZug = {frei: true, wahl: false, oids: [], fremd: 0, anders: 0}; erfBest = []; scanKons = null; erfTitel = null; erfDa = false;
  const bereit = erfKann();
  main.innerHTML = `${scanKopf('erfassen')}
    <details class="panel erf" id="erf-setup"${bereit ? '' : ' open'}><summary><span id="erf-sum"></span><span class="muted small-print">ändern</span></summary>
      <h2 class="nur-voll">Einstellungen ${info('vollbild', 'Scannen im Vollbild')}</h2>
      <div class="field"><span>Erkennung ${info('ohneset', 'Erkennung')}</span>
        <div class="seg" role="group" aria-label="Womit die Kamera vergleicht">${[[false, 'Nur gewählte Sets'], [true, 'Alle Karten, ohne Set']].map(([a, l]) =>
          `<button class="btn small" type="button" data-erfalle="${a ? 1 : ''}" aria-pressed="${a === erf.alle}">${l}</button>`).join('')}</div>
        <div id="erf-kat"></div>
        <div id="erf-katalog"></div>
        <label class="inl"><input type="checkbox" id="erf-frei"${scanFrei ? ' checked' : ''}> Karte frei im Bild suchen ${info('frei', 'Karte frei im Bild suchen')}</label>
        ${schnellSchalter()}
        ${erf.alle && kat.titel ? `<label class="inl"><input type="checkbox" id="erf-titel"${erf.titel ? ' checked' : ''}> Namen der Karte lesen ${info('titel', 'Namen der Karte lesen')}</label>` : ''}
        ${erf.alle ? `<label class="inl"><input type="checkbox" id="erf-namen" disabled> Deutsche Kartennamen laden (rund ${num(DEUTSCH_MB)} MB) ${info('namen', 'Deutsche Kartennamen laden')}</label><div id="erf-namen-stand"></div>` : ''}</div>
      <div class="erf-grid gap-top">
        <div class="field"><span>${erf.alle ? `Bevorzugte Sets ${info('vorliebe', 'Bevorzugte Sets')}` : `Sets ${info('setlock', 'Set wählen')}`}</span><div class="chips aktiv" id="erf-sets"></div>
          <span class="search wide">${icon('search', 'sm')}<input type="search" id="erf-q" placeholder="Set suchen, zum Beispiel Duskmourn oder DSK" aria-label="Set suchen (Name oder Kürzel)" autocomplete="off" spellcheck="false"></span>
          <div class="rows erf-treffer" id="erf-treffer"><p class="muted">Sets werden geladen …</p></div></div>
        <div class="erf-vorgaben">
          <label class="field"><span>Sprache</span><select id="erf-lang" data-erfvor="lang">${optionen(LANG, erf.lang)}</select></label>
          <label class="field"><span>Zustand</span><select id="erf-cond" data-erfvor="cond">${optionen(COND, erf.cond)}</select></label>
          <label class="field"><span>Foil</span><select id="erf-foil" data-erfvor="foil">${optionen(FOIL, erf.foil)}</select></label>
          <p class="note-line wide">${esc(TIP.vorgaben)}</p>
          <div class="field wide"><span>Messbilder ${info('messbilder', 'Messbilder')}</span>
            <div class="seg"><label class="inl"><input type="checkbox" id="erf-mess"${erf.mess ? ' checked' : ''}> Messbilder speichern</label>
              <label class="inl"><input type="checkbox" id="erf-huelle"${erf.huelle ? ' checked' : ''}> Karten stecken in Hüllen</label></div>
            <p class="note-line" id="erf-mess-stand"></p></div>
        </div></div>
      <div class="toolbar gap-top"${erf.alle ? ' hidden' : ''}><button class="btn primary" type="button" id="erf-vor">${icon('cloud')}Erkennung vorbereiten</button>
        <button class="link" type="button" id="erf-neu" title="${esc(TIP.erfneu)}">${icon('refresh', 'sm')}Drucke neu laden</button></div>
      <div id="erf-prep"></div>
    </details>
    <datalist id="erf-binderliste"></datalist>
    ${deck ? `<p class="note-line">${esc(TIP.deckscan)}</p>` : ''}
    ${camBox(bereit, erfStart())}
    <div class="nur-voll" id="voll-schleier" hidden><button class="btn" type="button">${icon('x')}Schließen</button></div>
    <section class="sec" aria-label="Scan-Liste" id="erf-liste"></section>
    <section class="sec" aria-label="Deine Scan-Binder" id="erf-binder-sec"></section>`;
  erfSetsUi(); erfSumme(); erfListe(); erfBinderUi(ei); katUi(); erfBereit();
  $('#cam-go').onclick = () => scanStart();
  $('#cam').onchange = e => scanStart(e.target.value);
  $('#erf-vor').onclick = () => erfVorbereiten(false);
  $('#erf-neu').onclick = () => erfVorbereiten(true);
  $('#erf-q').oninput = () => erfTreffer();
  $('#erf-q').onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); $('#erf-treffer [data-setneu]')?.click(); } };
  main.onkeydown = e => { if (e.key === 'Escape' && $('#voll-schleier').hidden === false) blatt(); };
  main.onchange = e => {  // Vorgaben stehen in den Einstellungen und im Vollbild als Schnellwahl unter der Kamera: beide zeigen denselben Stand
    const k = e.target.dataset.erfvor;
    if (!k) return;
    erf[k] = e.target.value; erfMerken(); erfSumme();
    for (const el of $$(`[data-erfvor="${k}"]`)) el.value = erf[k];
  };
  for (const [id, k] of [['erf-mess', 'mess'], ['erf-huelle', 'huelle']]) $('#' + id).onchange = e => { erf[k] = e.target.checked; erfMerken(); erfSumme(); messUi(); };
  $('#erf-frei').onchange = e => { scanFrei = e.target.checked; merke('mtg-scan-frei', scanFrei ? '1' : '0'); };
  $('#scan-schnell').onchange = schnellSetzen;
  if ($('#erf-titel')) $('#erf-titel').onchange = e => { erf.titel = e.target.checked; erfTitel = null; erfMerken(); };
  if ($('#erf-namen')) $('#erf-namen').onchange = e => katalogNamen(e.target.checked);
  katalogOeffnen();
  messUi();
  api('messbilder').then(r => { if (erf) { erf.messStand = {zahl: r.zahl, bytes: r.bytes}; messUi(); } }).catch(() => {});
  main.onclick = erfKlick;
  try { erfSetsAlle = erfSetsAlle || (await api('set-liste')).items; erfSetsUi(); erfTreffer(); }
  catch (e) { if (e instanceof LoginNoetig) return; const t = $('#erf-treffer'); if (t) t.innerHTML = `<p class="say bad">Set-Liste nicht geladen: ${esc(e.message)}</p>`; }
}

function erfBinderUi(ei) {  // Scan-Binder mit Karten und Wert (Klick zeigt ihre Karten), CSV und Umbenennen; ManaBox-Binder übernehmen (Phase 26)
  const box = $('#erf-binder-sec'), vor = $('#erf-binderliste');
  if (erf) erf.decks = new Set(ei.binder.filter(b => b.deck).map(b => b.name));
  if (vor) vor.innerHTML = ei.binder.map(b => `<option value="${esc(b.name)}">`).join('');
  if (!box) return;
  const csvName = n => n.replace(/[\\/:*?"<>|]+/g, '_') + '.csv';
  box.innerHTML = `<h2>Deine Scan-Binder ${info('scanbinder', 'Scan-Binder')}${ei.binder.length ? `<a class="more" href="/api/bestand.csv" download="bestand-${new Date().toISOString().slice(0, 10)}.csv" title="${esc(TIP.csv)}">${icon('download', 'sm')}Alles als CSV</a>` : ''}</h2>${ei.binder.length
    ? `<div class="rows">${ei.binder.map(b => `<div class="row binder"><a class="min0 binderlink" href="${b.deck ? '#/decks?binder=' : '#/cards?binder='}${encodeURIComponent(b.name)}"><div class="name">${esc(b.name)}</div><div class="sub2">${b.deck ? 'Fertiges Deck, ' : ''}${karten(b.karten)}, ${eur(b.wert)}, zuletzt ${day(b.zuletzt)}</div></a>
        <div class="seg"><a class="btn small" href="/api/bestand.csv?binder=${encodeURIComponent(b.name)}" download="${esc(csvName(b.name))}">${icon('csv', 'sm')}CSV</a><button class="btn small" type="button" data-binderneu="${esc(b.name)}">Umbenennen</button></div></div>`).join('')}</div>`
    : '<p class="muted">Noch keiner. Der erste entsteht, wenn du die erste Scan-Liste übernimmst.</p>'}
    ${ei.manabox?.length ? `<form class="filters gap-top" data-uebernehmen="1"><label class="inl">ManaBox-Binder übernehmen ${info('uebernehmen', 'Übernehmen')}
      <select name="binder" aria-label="ManaBox-Binder">${ei.manabox.map(b => `<option value="${esc(b.name)}">${esc(b.name)}, ${karten(b.karten)}</option>`).join('')}</select></label>
      <button class="btn small" type="submit">Übernehmen</button></form>` : ''}`;
}
const erfBinderNeu = async () => { try { erfBinderUi(await api('erfassen')); } catch { /* bleibt beim alten Stand */ } };
function umbenennenDialog(alt) {
  dlg.className = 'modal';
  dlg.innerHTML = `<button class="x" data-close aria-label="Schließen">${icon('x')}</button><div class="box"><h2 id="dlg-title">„${esc(alt)}“ umbenennen</h2>
    <p class="muted">Karten, Orte, Notizen und gebuchte Verkäufe ziehen mit.</p>
    <form class="kform" data-umbenennen="${esc(alt)}"><div class="field"><label for="u-neu">Neuer Name</label><input id="u-neu" name="neu" required maxlength="80" value="${esc(alt)}"></div>
      <div class="actions"><button class="btn ghost" type="button" data-close>Abbrechen</button><button class="btn primary" type="submit">Umbenennen</button></div></form></div>`;
  showDlg();
  $('#u-neu').select();
}
async function umbenennenForm(f) {
  const alt = f.dataset.umbenennen, neu = f.elements.neu.value.trim();
  try {
    await post('binder-name', {alt, neu});
    if (erf?.binder === alt) { erf.binder = neu; erfMerken(); }  // der vorgeschlagene Binder zieht mit
    dlg.close(); flash(`Umbenannt: ${neu}`); render(true);
  } catch (e) { if (!(e instanceof LoginNoetig)) flash('Fehler: ' + e.message); }
}
async function uebernehmenForm(f) {
  const b = f.elements.binder.value;
  if (!confirm(`„${b}“ in die App übernehmen?\n\nAb dann führt die App diesen Binder: Du änderst ihn hier, und ein ManaBox-Export lässt ihn aus. In ManaBox änderst du ihn danach nicht mehr. Vorher legt die App eine Sicherung an.`)) return;
  try { const r = await post('uebernehmen', {binder: b}); flash(`Übernommen: „${b}“ mit ${karten(r.karten)}, Sicherung ${r.sicherung}`); render(true); }
  catch (e) { if (!(e instanceof LoginNoetig)) flash('Fehler: ' + e.message); }
}

function erfSumme() {  // eine Zeile über allem, sichtbar auch bei zugeklappter Vorbereitung
  const s = $('#erf-sum'), k = erf.kat, teil = erf.alle && k?.gesamt && k.fertig < k.gesamt ? ` (${Math.floor(k.fertig / k.gesamt * 100)} % vorbereitet)` : '';
  if (s) s.textContent = `${erf.alle ? 'Alle Karten' + teil + (erf.sets.length ? ', bevorzugt ' + erf.sets.join(', ') : '') : erf.sets.length ? erf.sets.join(', ') : 'Kein Set gewählt'} · ${LANG[erf.lang]} · ${COND[erf.cond]}${erf.foil !== 'normal' ? ' · ' + FOIL[erf.foil] : ''}${erf.mess ? ' · Messbilder an' : ''}`;
}

function erfSetsUi() {
  const box = $('#erf-sets');
  if (!box) return;
  box.innerHTML = erf.sets.map(c => `<button type="button" class="chip" data-setweg="${esc(c)}" aria-label="Set ${esc(erfSetName(c))} entfernen">${esc(erfSetName(c))} (${esc(c)})${icon('x', 'sm')}</button>`).join('');
  const vor = $('#erf-vor');
  if (vor) vor.disabled = !erf.sets.length;
}

function erfTreffer() {  // ohne Suche die jüngsten Sets (bis 30 Tage voraus), sonst Treffer in Name oder Kürzel
  const box = $('#erf-treffer'), q = ($('#erf-q')?.value || '').trim().toLowerCase();
  if (!box || !erfSetsAlle) return;
  const bis = new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10);
  const liste = (q ? erfSetsAlle.filter(x => x.code.toLowerCase().includes(q) || x.name.toLowerCase().includes(q)) : erfSetsAlle.filter(x => x.datum <= bis))
    .filter(x => !erf.sets.includes(x.code)).slice(0, q ? 12 : 8);
  box.innerHTML = liste.map(x => `<button type="button" class="row binder" data-setneu="${esc(x.code)}"><div class="min0"><div class="name">${esc(x.name)} <span class="muted">${esc(x.code)}</span></div>
    <div class="sub2">${x.datum ? date(x.datum) : 'ohne Datum'}${x.typ === 'commander' ? ', Commander' : ''}${x.size ? `, ${num(x.size)} Drucke` : ''}</div></div><span class="go">${icon('plus')}</span></button>`).join('')
    || `<p class="muted">${q ? `Kein Set „${esc(q)}“.` : 'Keine neuen Sets.'}</p>`;
}

async function erfVorbereiten(neu) {
  if (!erf.sets.length) return flash('Erst ein Set wählen');
  const prep = $('#erf-prep'), knopf = $('#erf-vor'), codes = erf.sets.join();
  knopf.disabled = true;
  prep.innerHTML = `<div class="jobline">Drucke von Scryfall …</div><div class="progress busy"><span></span></div>`;
  try {
    let r = await api(`scan?v=${FP_V}&set=${encodeURIComponent(codes)}${neu ? '&neu=1' : ''}`);
    if (r.fehlt.length) {
      prep.innerHTML = `<div class="jobline">Erkennungsbilder: <span id="erf-n">0</span> von ${num(r.fehlt.length)}. Die Seite muss so lange offen bleiben.</div><div class="progress"><span style="--p:0"></span></div>`;
      await fpJob(r.fehlt, (a, n) => { $('#erf-prep .progress span')?.style.setProperty('--p', a / n); const z = $('#erf-n'); if (z) z.textContent = num(a); });
      r = await api(`scan?v=${FP_V}&set=${encodeURIComponent(codes)}`);
    }
    if (!r.ids.length) throw new Error('Keine Drucke mit Bild in diesen Sets');
    const ix = fpIndex({...r, keys: r.ids}), bild = {};
    r.ids.forEach((id, j) => { const ill = r.drucke[id].ill; if (ill) (bild[ill] = bild[ill] || []).push(j); });
    erfIx = {codes, ix, bild, sets: r.sets};
    if (codes !== erf.sets.join() || !$('#erf-prep')) return;  // inzwischen andere Sets oder Ansicht verlassen
    erfBereit();
    $('#erf-setup').open = false;
  } catch (e) {
    if (e instanceof LoginNoetig) return;
    if ($('#erf-prep')) prep.innerHTML = `<p class="say bad">Nicht vorbereitet: ${esc(e.message)}</p>`;
  } finally { if ($('#erf-vor')) knopf.disabled = !erf.sets.length; }
}

// Gibt es etwas zu erkennen? Ohne Set-Wahl, sobald die ersten Kartenbilder vorbereitet sind, mit Set-Lock, wenn der Index zu den Sets passt
const erfKann = () => erf.alle ? erf.kat?.fertig > 0 : erfIx?.codes === erf.sets.join();
const erfStart = () => erfKann() ? 'Kamera starten, dann die erste Karte davor halten.' : erf.alle ? 'Erst die Kartenbilder vorbereiten, oben unter „Erkennung“.' : 'Erst Sets wählen und die Erkennung vorbereiten.';
function erfBereit() {
  if (!$('#cam-go')) return;
  const kann = erfKann();
  if (kann && !erf.alle) $('#erf-prep').innerHTML = `<p class="note-line">${icon('check', 'sm')} Bereit: ${num(erfIx.ix.n)} Drucke aus ${erfIx.sets.map(x => `${esc(x.name)} (${esc(x.code)})`).join(', ')}.</p>`;
  $('#cam-go').disabled = !kann;
  if (!scanStream) $('#scan-status').textContent = erfStart();
}

// Erkennung ohne Set-Wahl vorbereiten (Phase 32): je Aussehen ein Fingerabdruck aus dem Scryfall-Bild, paketweise vom Server erfragt und dort für
// alle Konten gespeichert. Der Lauf geht weiter, wenn du die Ansicht wechselst; „Anhalten“ oder ein geschlossenes Fenster beenden ihn, der nächste
// macht dort weiter.
// Katalog und deutsche Namen (Phase 45, PLAN E26): Beide lädt der Server von Scryfall, aber nur bei Bedarf. „Erfassen“ öffnen meldet dem Server den
// Bedarf (POST katalog {oeffnen}); fehlt der Katalog, lädt ihn ein Hintergrund-Job, den diese Ansicht mit Fortschritt zeigt. Die Größen gelten
// für die Anzeige (Stand 2026-10-12, gepackt; dieselben Zahlen wie katalog.KATALOG_MB und DEUTSCH_MB). KAT_BILD_KB ist eine Schätzung für die
// kleine Bildgröße, keine Messung (tests/live_check.py nennt die echte Größe).
const KAT_MB = 75, DEUTSCH_MB = 378, KAT_BILD_KB = 10;
const katPct = j => j?.total ? Math.min(100, Math.floor(j.done / j.total * 100)) : null;
async function katalogOeffnen() {
  const t = erf;
  try { t.katalog = await post('katalog', {oeffnen: true}); }
  catch (e) { if (e instanceof LoginNoetig || erf !== t) return; t.katalog = null; return; }
  if (erf === t) { katalogUi(); katUi(); katalogPollen(t); }
}
function katalogPollen(t) {
  clearTimeout(katalogTimer);
  const j = t.katalog;
  if (erf !== t || !(j?.job?.running || j?.namen?.job?.running)) return;
  katalogTimer = setTimeout(async () => {
    if (erf !== t || !$('#erf-katalog')) return;
    const lief = !!t.katalog?.job?.running;
    try { t.katalog = await api('katalog'); } catch (e) { if (e instanceof LoginNoetig) return; }
    if (erf !== t) return;
    if (lief && !t.katalog?.job?.running && t.katalog?.katalog) {  // der Katalog ist da: Stand der Erkennung neu lesen
      try { t.kat = await api('scan/katalog?v=' + FP_V); } catch (e) { if (e instanceof LoginNoetig) return; }
      erfBereit(); erfSumme();
    }
    katalogUi(); katUi(); katalogPollen(t);
  }, 1000);
}
function katalogUi() {
  const s = erf?.katalog, box = $('#erf-katalog');
  if (box) {
    const j = s?.job, p = katPct(j);
    box.innerHTML = !s ? '' : j?.running ? `<p class="note-line">Der Katalog aller Karten (rund ${KAT_MB} MB) wird von Scryfall geladen${p === null ? '' : ': ' + p + ' %'}. Das geschieht einmal im Hintergrund auf dem Server, die Seite darf offen bleiben oder geschlossen werden.</p><div class="progress${p === null ? ' busy' : ''}"><span${p === null ? '' : ` style="--p:${p / 100}"`}></span></div>`
      : !s.katalog && j?.error ? `<p class="say bad">Der Katalog ließ sich nicht laden: ${esc(j.error)}. Höchstens ein Abruf der Gesamtdaten am Tag: Der nächste Versuch ist morgen, sofort geht es im Terminal mit „mtg katalog --neu“.</p>`
      : s.katalog ? `<p class="note-line">${icon('check', 'sm')} Katalog: ${num(s.katalog.drucke)} Papier-Drucke, Stand ${esc(day(s.katalog.gebaut))}, ${num(s.katalog.mb)} MB auf dem Server.</p>` : '';
  }
  const n = s?.namen, schalter = $('#erf-namen'), stand = $('#erf-namen-stand');
  if (!schalter || !stand || !n) return;
  const j = n.job, p = katPct(j);
  schalter.checked = n.an;
  schalter.disabled = !n.darf || !n.moeglich;
  stand.innerHTML = !n.moeglich ? `<p class="note-line">Dieser Server kann keine Namen lesen (Tesseract fehlt), deshalb lädt er auch keine deutschen.</p>`
    : j?.running ? `<p class="note-line">Die deutschen Kartennamen (rund ${num(n.mb)} MB) werden geladen${p === null ? '' : ': ' + p + ' %'}. Das dauert einige Minuten und läuft im Hintergrund auf dem Server.</p><div class="progress${p === null ? ' busy' : ''}"><span${p === null ? '' : ` style="--p:${p / 100}"`}></span></div>`
    : j?.error && n.an && !n.zahl ? `<p class="say bad">Die deutschen Kartennamen ließen sich nicht laden: ${esc(j.error)}. Der nächste Versuch ist morgen.</p>`
    : n.zahl ? `<p class="note-line">${icon('check', 'sm')} ${num(n.zahl)} deutsche Kartennamen, Stand ${esc(day(n.gebaut))}${n.an ? '' : ', sie werden nicht mehr aufgefrischt'}.${n.darf ? '' : ' Das Hauptkonto stellt das ein.'}</p>`
    : n.an ? `<p class="note-line">Eingeschaltet: ${s.katalog ? 'Der Server lädt sie im Laufe der nächsten Stunde.' : 'Der Server lädt sie, sobald der Katalog da ist.'}</p>`
    : `<p class="note-line">Aus: Die App liest englische Namen, deutsche Karten erkennt sie am Bild.${n.darf ? '' : ' Das Hauptkonto stellt das ein.'}</p>`;
}
async function katalogNamen(an) {
  const t = erf;
  try { t.katalog = await post('katalog', {namen: an}); }
  catch (e) { if (!(e instanceof LoginNoetig)) flash('Fehler: ' + e.message); try { t.katalog = await api('katalog'); } catch { /* bleibt */ } }
  if (erf === t) { katalogUi(); katalogPollen(t); }
}
function katUi() {
  const box = $('#erf-kat'), k = erf?.kat;
  if (!box || !k) return;
  const rest = k.gesamt - k.fertig, mb = Math.max(1, Math.round(rest * KAT_BILD_KB / 1000));
  box.innerHTML = !k.gesamt ? (erf.katalog?.job?.running || erf.katalog?.job?.error ? '<p class="note-line">Bis der Katalog da ist, erkennt die App mit „Nur gewählte Sets“.</p>' : `<p class="note-line">${esc(TIP.katfehlt)}</p>`)
    : k.fertig >= k.gesamt ? `<p class="note-line">${icon('check', 'sm')} Alle ${num(k.gesamt)} Kartenbilder sind vorbereitet.</p>`
    : `<p class="note-line"><span id="erf-kat-n">${num(k.fertig)}</span> von ${num(k.gesamt)} Kartenbildern vorbereitet. Die ${num(rest)} fehlenden sind rund ${num(mb)} MB (kleine Bilder, geschätzt), je Installation einmal. ${esc(TIP.katjob)}
        <button class="link" type="button" id="erf-kat-go">${katJob ? 'Anhalten' : icon('cloud', 'sm') + 'Jetzt vorbereiten'}</button></p>
      ${katJob ? `<div class="progress"><span style="--p:${k.fertig / k.gesamt}"></span></div>` : ''}`;
}
async function katVorbereiten() {
  if (katJob) { katJob.stopp = true; return; }
  const job = katJob = {stopp: false};
  let zuletzt = -1;
  try {
    for (;;) {
      const r = await api(`scan/katalog?v=${FP_V}&fehlt=1`);
      if (erf) { erf.kat = r; katUi(); erfBereit(); erfSumme(); }
      if (job.stopp || !r.fehlt.length || r.fertig === zuletzt) break;  // eine Runde ohne neues Bild: Die übrigen lassen sich gerade nicht laden
      const start = zuletzt = r.fertig;  // erf.kat ist r: nicht darauf weiterzählen
      await fpJob(r.fehlt, a => {
        if (!erf?.kat) return;
        erf.kat.fertig = Math.min(start + a, r.gesamt); erfBereit(); erfSumme();
        const z = $('#erf-kat-n');
        if (z) { z.textContent = num(erf.kat.fertig); $('#erf-kat .progress span')?.style.setProperty('--p', erf.kat.fertig / r.gesamt); }
      }, 'scan/katalog', () => job.stopp);
    }
  } catch (e) { if (!(e instanceof LoginNoetig)) flash('Vorbereiten unterbrochen: ' + e.message); }
  katJob = null;
  katUi();
}

function erfKamera() {  // Kamera läuft: Vorbereitung zuklappen, Platz fürs Bild
  const d = $('#erf-setup');
  if (d) d.open = false;
  messUi();
}

// je Bild: zählen, Auswahl anbieten oder warten (siehe oben). Nach „Letzte zurück“ (erfZug.wahl) zählt nichts von selbst, bis du wählst oder
// die Karte herausnimmst: sonst käme dieselbe falsche Erkennung gleich wieder. erfZug.oids = was die Karte im Rahmen ist oder sein könnte (die
// gezählte bzw. alle zur Wahl angebotenen): Davon zählt nichts von selbst noch einmal. Liegt ERF_FREI Bilder lang etwas anderes darin (Stapel,
// schneller Wechsel ohne leeren Rahmen) und ist es unsicher, fragt die App, statt die neue Karte still liegen zu lassen.
// Beide Wege liefern dieselbe Form: urteil (leer, nichts, unsicher, zwilling, sicher) und kand = die Drucke zur Wahl, der beste zuerst, je Druck
// {id, oid, name, set_code, number, image}; ohne Set-Wahl dazu pruefen (der Druck ist geraten) und wahl (die anderen Drucke desselben Bilds).
// Dazu wert und abstand des besten Treffers (für Konsens, Phase 56).
function erfLokal(best) {  // Set-Lock: Ergebnis von fpSuche über den Index im Browser
  const ix = erfIx.ix, b = best[0], z = best[1];
  const druck = j => { const id = ix.ids[j], d = ix.drucke[id]; return {id, oid: d.oid, name: d.name, set_code: d.set, number: d.number, image: d.image}; };
  if (!b || b.score < FP_NEIN) return {urteil: b ? 'nichts' : 'leer', kand: best.map(x => druck(x.i)), wert: b?.score};
  const d = ix.drucke[ix.ids[b.i]], zwillinge = (erfIx.bild[d.ill] || []).filter(j => j !== b.i && ix.drucke[ix.ids[j]].set !== d.set);
  return {urteil: zwillinge.length ? 'zwilling' : b.score >= FP_SICHER && (!z || b.score - z.score >= FP_ABSTAND) ? 'sicher' : 'unsicher',
          kand: (zwillinge.length ? [b.i, ...zwillinge] : best.map(x => x.i)).map(druck), wert: b.score, abstand: z ? b.score - z.score : 1};
}
// Erst den Namen lesen (Phase 35, PLAN E21). Liegt die Karte ruhig (ein Viereck dort, wo das Viereck der Karte im Bild davor lag, oder ohne
// Viereck die Karte im Rahmen), gehen einmal je Karte die Streifen mit der Namenszeile an den Server (titelBild, TITEL_VERSUCHE). Er nennt die
// Karten, deren Name passt, und ob der Name sicher gelesen ist; jede Suche für diese Karte schickt beides mit, und der Server urteilt aus
// Name und Bild (katalog.suche). Liest er keinen Namen, folgen höchstens TITEL_RUNDEN Versuche, dann bleibt es beim Bild allein.
// erfTitel = {wo: Mitte des Vierecks oder null (Rahmen), n: Versuche ohne Namen, karten, sicher}; erfDa: Im Bild davor lag eine Karte.
const TITEL_RUNDEN = 3;
let erfTitel = null, erfDa = false;
const qMitte = q => [0, 1].map(i => (q.e[0][i] + q.e[1][i] + q.e[2][i] + q.e[3][i]) / 4);
const qBei = (q, wo) => { const m = qMitte(q); return Math.hypot(m[0] - wo[0], m[1] - wo[1]) < FIND_RUHIG * Math.hypot(q.e[1][0] - q.e[0][0], q.e[1][1] - q.e[0][1]); };
async function erfNamen(src, g, vierecke) {
  if (!erf.titel || !erf.kat.titel) return {};
  const q = scanQ ? vierecke.find(x => qBei(x, scanQ)) : null;
  if (scanQ ? !q : !erfDa) { erfTitel = null; return {}; }  // Karte bewegt, neu im Bild oder keine da: noch nichts zu lesen
  if (!erfTitel || (q ? !erfTitel.wo || !qBei(q, erfTitel.wo) : !!erfTitel.wo)) erfTitel = {wo: q ? qMitte(q) : null, n: 0};
  if (!erfTitel.karten && erfTitel.n < TITEL_RUNDEN) {
    const t = await post('scan/titel', {streifen: TITEL_VERSUCHE.map(wie => titelBild(src, q || g, wie).toDataURL('image/jpeg', .9).split(',')[1])});
    if (t.karten.length) Object.assign(erfTitel, {karten: t.karten, sicher: t.sicher ? t.namen[0].karten : []});
    else erfTitel.n++;
  }
  return erfTitel.karten ? {karten: erfTitel.karten, sicher: erfTitel.sicher} : {};
}
// ohne Set-Wahl: Der Server sucht unter allen Kartenbildern; Schwellen und Urteil stehen dort (katalog.suche). Erst die frei gefundenen
// Vierecke; ist er sich bei keinem sicher, dazu der Rahmen in der Mitte: Er gilt, wenn er sicher ist oder besser passt. q = das Viereck, das
// zur Karte führte.
async function erfServer(src, g, vierecke = []) {
  const mehr = {sets: erf.sets, kontext: erf.kontext, ...await erfNamen(src, g, vierecke)};
  let a = await freiServer(src, vierecke, mehr);
  if (a?.urteil !== 'sicher') {
    const fp = fpLagen(...scanBild(src, g)), r = fp.length ? await post('scan/suche', {v: FP_V, fp, ...mehr}) : null;
    if (r && (r.urteil === 'sicher' || !(a?.treffer[0].wert >= r.treffer[0]?.wert))) a = r;
  }
  erfDa = !!a && a.urteil !== 'nichts';
  return a ? {urteil: a.urteil, q: a.q, kand: a.treffer.map(t => ({...t.druck, pruefen: t.pruefen, wahl: t.drucke.map(d => d.id)})), wert: a.treffer[0]?.wert, abstand: a.treffer[0]?.abstand}
    : {urteil: 'leer', kand: []};
}
// was zu einem gezählten Druck auf die Scan-Liste geht: ist er geraten, die anderen Drucke desselben Bilds, sonst die anderen Kandidaten
const erfWie = (d, kand) => ({wahl: d.pruefen ? d.wahl : kand.filter(x => x.id !== d.id).map(x => x.id), pruefen: !!d.pruefen});

function erfZeigen(r, ruhig = true) {
  if (!$('#scan-status')) return;
  erfBest = r.kand;
  const kons = konsens(erf.alle ? 'server' : 'lokal');
  if (r.urteil === 'leer' || r.urteil === 'nichts') {  // leerer Rahmen sofort, sonst erst nach ERF_FREI Bildern ohne Treffer: die Karte ist raus
    kons.bild({urteil: r.urteil});
    erfZug = {...erfZug, anders: 0, fremd: r.urteil === 'nichts' ? erfZug.fremd + 1 : ERF_FREI};
    if (erfZug.fremd >= ERF_FREI) erfZug = {...erfZug, frei: true, wahl: false};
    return erfStatus(r.urteil === 'nichts' ? 'fremd' : 'leer');
  }
  erfZug.fremd = 0;
  const d = r.kand[0], ids = r.kand.map(x => x.id).join();
  erfZug.anders = !erfZug.frei && !erfZug.oids.includes(d.oid) ? erfZug.anders + 1 : 0;
  if (erfZug.wahl) return erfStatus('wahl:' + ids, r.kand);
  const k = kons.bild({urteil: r.urteil, id: d.id, oid: d.oid, wert: r.wert, abstand: r.abstand, ruhig, bei: scanBei});
  const sicher = r.urteil === 'sicher', neu = erfZug.frei || !erfZug.oids.includes(d.oid);
  if (k.zaehlen && neu) {
    erfZug = {...erfZug, frei: false, oids: [d.oid]};
    erfZaehlen(d.id, erfWie(d, r.kand), true);
    blaetternKarte(d.id, erfWie(d, r.kand));
    return erfStatus('gezaehlt');
  }
  if (sicher || (!erfZug.frei && erfZug.anders < ERF_FREI)) return erfStatus(sicher && neu ? 'sicher' : 'gezaehlt');  // die gezählte Karte liegt noch im Rahmen
  if (kons.schnell && kons.id !== null && erfZug.anders < ERF_FREI) return erfStatus(kons.gezaehlt ? 'gezaehlt' : 'sicher');  // gehört zur laufenden Folge: keine Auswahl dazwischen
  return erfStatus(`${r.urteil === 'zwilling' ? 'zwilling' : 'unsicher'}:${ids}`, r.kand);
}

function erfStatus(stand, kand) {
  if (stand === scanStand) return;  // nur bei Änderung neu zeichnen (Klicks auf die Auswahl gehen sonst verloren)
  scanStand = stand;
  const st = $('#scan-status'), art = stand.split(':')[0], k = erf.kat;
  $('#scan-hit .hit')?.classList.toggle('alt', art !== 'gezaehlt' && art !== 'leer');  // die nächste Karte ist dran: die letzte tritt zurück
  st.className = art === 'sicher' || art === 'gezaehlt' ? '' : 'muted';
  if (art === 'netz') { st.textContent = 'Keine Verbindung zum Server, dort läuft die Erkennung. Die App versucht es weiter.'; return; }
  if (art === 'leer' || art === 'fremd') {
    st.textContent = art === 'leer' ? (erfZug.frei ? 'Bereit für die nächste Karte.' : 'Karte vor die Kamera halten.')
      : !erf.alle ? `Keine Karte aus ${erf.sets.join(', ')} erkannt. Andere Karte, mehr Licht oder ein weiteres Set?`
      : `Keine Karte erkannt. Mehr Licht, ruhiger halten oder die ganze Karte ins Bild?${k.fertig < k.gesamt ? ` Vorbereitet sind erst ${num(k.fertig)} von ${num(k.gesamt)} Kartenbildern.` : ''}`;
    return;
  }
  if (art === 'sicher') { st.textContent = 'Erkannt …'; return; }
  if (art === 'gezaehlt') { st.innerHTML = `Auf der Scan-Liste. Karte herausnehmen, dann die nächste. Weitere Kopie dieser Karte: ${icon('plus', 'sm')}1.`; return; }
  erfKand = kand;
  st.innerHTML = `${art === 'zwilling' ? 'Dieses Bild gibt es in mehreren gewählten Sets. Welches ist es?' : art === 'wahl' ? 'Welche ist es? Tipp die richtige an oder nimm die Karte heraus.'
    : 'Unsicher. Welche ist es?'} <div class="kand">${kand.map(d =>
    `<button type="button" class="kandb" data-erfpick="${esc(d.id)}" title="${esc(`${d.name}, ${d.set_code} #${d.number}`)}">${pic(small(d.image), d.name)}<span>${esc(d.set_code)} #${esc(d.number)}</span></button>`).join('')}</div>`;
}

// kamera: Die Karte liegt gerade vor der Kamera (erkannt oder aus den Kandidaten gewählt, nicht „+1“). Mit „Messbilder speichern“ wird das Bild
// jetzt aufgenommen und geht an den Server, sobald die Scan-Liste den Zug kennt. Erreicht der Scan den Server nicht, gibt es kein Messbild.
function erfZaehlen(id, wie = {}, kamera = false) {  // Reihenfolge bleibt: jede Anfrage wartet auf die vorige
  const body = {aktion: 'liste', id, foil: wie.foil || erf.foil, condition: wie.condition || erf.cond, language: wie.language || erf.lang,
                wahl: wie.wahl || [], pruefen: !!wie.pruefen, zug: `${Date.now().toString(36)}-${++erfNr}`};
  const bild = kamera && erf.mess && scanStream ? messBild() : null;
  ton();
  erfKette = erfKette.then(() => erfSenden(body, bild));
  return erfKette;
}

async function erfSenden(body, bild) {
  try {
    const l = await post('erfassen', body);
    if (bild) messSenden(bild, body.zug);
    erf.offen = erf.offen.filter(x => x.zug !== body.zug); erfOffenMerken();
    erf.liste = l; erfListe();
    const z = l.zeilen.find(x => x.scryfall_id === body.id) || l.zeilen[0];  // jüngster Scan zuerst
    erf.letzte = {id: body.id, foil: z.foil, condition: z.condition, language: z.language, pruefen: body.pruefen};  // „+1“ einer geratenen bleibt geraten
    if (z.set_code && !body.pruefen) kontextDazu(z.set_code);  // Zusammenhang für die Druckwahl, nur aus Drucken, die nicht geraten sind
    erfHit(z);
  } catch (e) {
    if (e instanceof LoginNoetig) return;
    if (!erf.offen.some(x => x.zug === body.zug)) erf.offen.push(body);
    erfOffenMerken();
    erfListe(e.message);
  }
}

// Sets der letzten Karten, jüngstes zuerst: ein geratener Druck käme sonst als Zusammenhang zurück und zöge die nächsten mit (Phase 60)
const kontextDazu = c => { erf.kontext = [c, ...erf.kontext.filter(x => x !== c)].slice(0, 3); };

function erfHit(z) {
  const box = $('#scan-hit');
  if (!box) return;
  box.innerHTML = `<div class="hit"><a href="#" data-oid="${esc(z.oracle_id)}" aria-label="${esc(z.name)} ${vollbild() ? 'ändern' : 'ansehen'}">${pic(small(z.image), z.name)}</a><div class="min0">
    <div class="name">${esc(z.name)}</div><div class="sub2">${esc(erfArt(z))}</div>
    <div class="urteil">Auf der Liste</div><div class="sub2">${eur(z.price)}, ${z.hat ? `${num(z.hat)} schon im Bestand` : 'noch nicht im Bestand'}</div>
    <div class="seg gap-top"><button class="btn small" type="button" id="erf-plus">${icon('plus', 'sm')}1 weitere</button><button class="btn small" type="button" data-erfzurueck>${icon('left', 'sm')}Letzte zurück</button></div></div></div>`;
}

function erfListe(fehler) {  // die Scan-Liste zum Prüfen; erst „übernehmen“ legt sie in den Binder
  const box = $('#erf-liste'), l = erf.liste, n = l?.karten || 0, z = erf.zuletzt, pruefen = (l?.zeilen || []).filter(x => x.pruefen).length;
  if (!box) return;
  $('#voll-summe').textContent = n ? `${karten(n)} · ${eur(l.wert)}` : 'Scan-Liste leer';
  const vorher = +box.dataset.n || 0; box.dataset.n = n;
  const frisch = z && Date.now() - Date.parse(z.at) < ERF_ZULETZT_H * 36e5;
  box.innerHTML = `<h2>Scan-Liste ${info('scanliste', 'Scan-Liste')} <small>${n ? `${karten(n)}, ${eur(l.wert)}${pruefen ? `, ${num(pruefen)}× Druck prüfen` : ''}` : 'leer'}</small>
      ${n ? `<span class="seg h2r"><button class="btn small" type="button" data-erfzurueck>${icon('left', 'sm')}Letzte zurück</button></span>` : ''}</h2>
    ${erf.offen.length ? `<div class="note warn"><span class="ic">${icon('alert')}</span><div><b>${karten(erf.offen.length)} nicht gespeichert</b><div class="muted">${esc(fehler || 'Keine Verbindung zum Server.')} Die App merkt sie sich, bis du sie erneut sendest.</div></div><button class="btn small" type="button" id="erf-nochmal">Erneut senden</button></div>` : ''}
    ${n ? `<div class="rows">${l.zeilen.map(erfRow).join('')}</div>
      <form class="erf-ab" data-erfab="1"><label class="field"><span>${erf.deck ? 'In das Deck' : `In den Scan-Binder ${info('scanbinder', 'Scan-Binder')}`}</span>
          <input name="binder" list="erf-binderliste" maxlength="80" required value="${esc(erf.binder)}" autocomplete="off"${erf.deck ? ' placeholder="Name des Decks"' : ''}></label>
        <label class="inl"><input type="checkbox" name="deck"> Fertiges Deck ${info('scandeck', 'Fertiges Deck')}</label>
        <button class="btn primary" type="submit">${icon('check')}${karten(n)} übernehmen</button></form>
      <div class="toolbar gap-top"><button class="btn ghost" type="button" id="erf-verwerfen">${icon('trash', 'sm')}Liste verwerfen</button></div>`
    : `<p class="muted">${esc(TIP.scanliste)}</p>`}
    ${frisch ? `<p class="note-line">${icon('check', 'sm')} Zuletzt übernommen: ${karten(z.karten)} in „${esc(z.binder)}“, ${day(z.at)} um ${uhr(z.at)}.
      ${z.zuruecknehmbar ? `<button class="link" type="button" id="erf-zurueckholen">${icon('left', 'sm')}zurück auf die Liste</button>` : ''}</p>` : ''}`;
  if (n > vorher) bump($('h2 small', box));
  const f = $('[data-erfab]', box), haken = () => {  // ein eingescanntes Deck bleibt eins; sonst entscheidet der Haken (aus „Deck einscannen“ gesetzt)
    const ist = erf.decks.has(f.elements.binder.value.trim());
    Object.assign(f.elements.deck, {checked: ist || erf.deck, disabled: ist});
  };
  if (f) { f.elements.binder.oninput = haken; haken(); }
}

const erfRow = (z, i) => `<div class="row erf"><a href="#" data-oid="${esc(z.oracle_id)}"${peekAt(z.image, z.name, eur(z.price))} aria-label="${esc(z.name)} ansehen">${pic(small(z.image), '', 'thumb')}</a>
  <button type="button" class="who" data-erfedit="${i}" title="Karte, Foil, Sprache, Zustand oder Menge ändern"><span class="name">${esc(z.name)}</span><span class="sub2">${esc(erfArt(z))}${z.scans > 1 ? `, ${z.scans}× gescannt` : ''}${z.pruefen ? ' · <b>Druck prüfen</b>' : ''}</span></button>
  <div class="stepper" role="group" aria-label="Menge"><button type="button" data-erfqty="${i}" data-d="-1" aria-label="eine weniger">${icon('minus', 'sm')}</button><output class="num">${z.qty}</output><button type="button" data-erfqty="${i}" data-d="1" aria-label="eine mehr">${icon('plus', 'sm')}</button></div>
  <div class="price">${eur(z.price)}</div></div>`;

async function erfAendern(z, neu) {
  try { erf.liste = await post('erfassen', {aktion: 'liste-aendern', key: [z.scryfall_id, z.foil, z.condition, z.language], ...neu}); erfListe(); return true; }
  catch (e) { if (!(e instanceof LoginNoetig)) flash('Fehler: ' + e.message); return false; }
}

// Zeile prüfen: welche Karte es ist (Kandidaten der Erkennung oder Suche), Foil, Sprache, Zustand, Menge
const erfKachel = (d, an) => `<button type="button" class="kandb" data-ewahl="${esc(d.id)}"${d.oid ? ` data-oid2="${esc(d.oid)}"` : ''} aria-pressed="${an}" title="${esc(`${d.name}, ${d.set_code} #${d.number}`)}">${pic(small(d.image), d.name)}<span>${esc(d.set_code)} #${esc(d.number)}</span></button>`;
// „Welche Karte ist es?“ im Dialog: Kacheln (Kandidaten der Erkennung, an = gewählte Id) und die Suche; die Wahl steht im Feld id des Formulars
const wahlHtml = (kand, an, frage = 'Welche Karte ist es?') => `<div class="field"><span>${frage}</span><div class="kand umbruch" id="e-kand">${kand.map(d => erfKachel(d, d.id === an)).join('')}</div>
        <div class="toolbar gap-top"><span class="search grow">${icon('search', 'sm')}<input type="search" id="e-q" placeholder="Andere Karte suchen" aria-label="Andere Karte suchen (Name)" autocomplete="off" spellcheck="false"></span>
          <button class="btn small" type="button" id="e-suchen">Suchen</button></div>
        <div class="kand umbruch" id="e-treffer"></div></div>`;
function wahlUi(f) {
  $('.box', dlg).onclick = e => {  // Karte wählen: Kandidat oder Suchtreffer
    const b = e.target.closest('[data-ewahl]');
    if (!b) return;
    f.elements.id.value = b.dataset.ewahl;
    $$('[data-ewahl]', dlg).forEach(x => x.setAttribute('aria-pressed', String(x.dataset.ewahl === b.dataset.ewahl)));
    if (b.dataset.oid2) druckeLaden(b.dataset.oid2, f);  // eine andere Karte gewählt (Suche): deren Drucke zeigen
  };
  const suchen = async () => {
    const q = $('#e-q').value.trim(), box = $('#e-treffer');
    if (q.length < 2) { box.innerHTML = '<p class="muted">Mindestens zwei Buchstaben.</p>'; return; }
    box.innerHTML = '<p class="muted">Sucht …</p>';
    try {
      const {items} = await api(`erfassen?suche=${encodeURIComponent(q)}`);
      box.innerHTML = items.map(d => erfKachel(d, d.id === f.elements.id.value)).join('') || '<p class="muted">Nichts gefunden.</p>';
    } catch (err) { if (!(err instanceof LoginNoetig)) box.innerHTML = `<p class="say bad">${esc(err.message)}</p>`; }
  };
  $('#e-suchen').onclick = suchen;
  $('#e-q').onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); suchen(); } };
}
// Alle Drucke einer Karte (Phase 60), auch mit anderem Bild: Die Kamera unterscheidet Drucke mit demselben Bild nicht, die Kandidaten der
// Erkennung nennen davon höchstens sechs. Nur im Dialog der Scan-Liste (#e-drucke), neu geladen, wenn eine andere Karte gewählt wird.
async function druckeLaden(oid, f) {
  const box = $('#e-drucke', dlg);
  if (!box || box.dataset.oid === oid) return;
  box.dataset.oid = oid;
  box.innerHTML = '<p class="muted">Lädt …</p>';
  try {
    const {items} = await api('erfassen?drucke=' + encodeURIComponent(oid));
    if (box.dataset.oid !== oid) return;  // inzwischen eine andere Karte gewählt
    $('#e-drucke-t', dlg).textContent = items.length > 1 ? `Alle ${num(items.length)} Drucke von ${items[0].name}` : 'Drucke dieser Karte';
    box.innerHTML = items.map(d => erfKachel({...d, oid: null}, d.id === f.elements.id.value)).join('') || '<p class="muted">Keine weiteren Drucke bekannt.</p>';
  } catch (e) { if (!(e instanceof LoginNoetig)) box.innerHTML = `<p class="say bad">${esc(e.message)}</p>`; }
}
function erfEdit(i) {
  const z = erf.liste.zeilen[i];
  dlg.className = 'modal';
  dlg.innerHTML = `<button class="x" data-close aria-label="Schließen">${icon('x')}</button><div class="box"><h2 id="dlg-title">${esc(z.name)}</h2>
    <p class="muted">${esc(z.set_code)} #${esc(z.number)}${z.scans > 1 ? `, ${z.scans}× gescannt` : ''}. ${z.hat ? `${num(z.hat)} schon im Bestand.` : 'Noch nicht im Bestand.'}</p>
    ${z.pruefen ? `<p class="note-line">${esc(TIP.druckpruefen)}</p>` : ''}
    <form class="kform" data-erf="${i}"><input type="hidden" name="id" value="${esc(z.scryfall_id)}">
      ${wahlHtml([{...z, id: z.scryfall_id}, ...z.wahl], z.scryfall_id, z.pruefen ? 'Welcher Druck ist es?' : undefined)}
      <div class="field"><span id="e-drucke-t">Drucke dieser Karte</span><div class="kand umbruch" id="e-drucke"></div></div>
      <div class="field"><label for="e-foil">Foil</label><select id="e-foil" name="foil">${optionen(FOIL, z.foil)}</select></div>
      <div class="field"><label for="e-lang">Sprache</label><select id="e-lang" name="language">${optionen(LANG, z.language)}</select></div>
      <div class="field"><label for="e-cond">Zustand</label><select id="e-cond" name="condition">${optionen(COND, z.condition)}</select></div>
      <div class="field"><label for="e-qty">Menge (0 nimmt sie von der Liste)</label><input id="e-qty" name="qty" type="number" min="0" max="99" value="${z.qty}"></div>
      <div class="actions"><button class="btn ghost" type="button" id="e-weg">${icon('trash', 'sm')}Von der Liste</button><button class="btn ghost" type="button" data-close>Abbrechen</button><button class="btn primary" type="submit">Speichern</button></div></form></div>`;
  showDlg();
  wahlUi($('form', dlg));
  if (z.oracle_id) druckeLaden(z.oracle_id, $('form', dlg));
  $('#e-weg').onclick = async () => { if (await erfAendern(z, {qty: 0})) { dlg.close(); flash(`${z.name}: von der Liste genommen`); } };
}

async function erfForm(f) {
  const z = erf.liste.zeilen[+f.dataset.erf], d = Object.fromEntries(new FormData(f));
  if (+d.qty === 0 && !confirm(`${z.name} von der Liste nehmen?`)) return;
  const neu = {foil: d.foil, condition: d.condition, language: d.language, qty: +d.qty, ...(d.id !== z.scryfall_id || z.pruefen ? {id: d.id} : {})};  // mit id gilt der Druck als geprüft
  if (!await erfAendern(z, neu)) return;
  const g = neu.id && erf.liste.zeilen.find(x => x.scryfall_id === neu.id);  // von dir gewählt: gilt als Zusammenhang
  if (g?.set_code) kontextDazu(g.set_code);
  dlg.close(); flash(+d.qty === 0 ? `${z.name}: von der Liste genommen` : 'Gespeichert');
}

async function erfUebernehmen(f) {  // die geprüfte Liste in den Binder
  const b = f.elements.binder.value.trim(), deck = f.elements.deck.checked;
  await erfKette;  // erst die laufenden Scans
  if (erf.offen.length && !confirm(`${karten(erf.offen.length)} sind noch nicht beim Server angekommen. Sie kommen nicht mit in den Binder, bleiben aber zum erneuten Senden stehen. Trotzdem übernehmen?`)) return;
  try {
    const r = await post('erfassen', {aktion: 'uebernehmen', binder: b, deck});
    erf.binder = b; erf.liste = r.liste; erf.zuletzt = r.zuletzt; erf.letzte = null; erfMerken();
    if ($('#scan-hit')) $('#scan-hit').innerHTML = '';
    erfListe(); erfBinderNeu();
    if (vollbild()) blatt();  // die Runde ist fertig: zurück zur Kamera, ohne das Blatt eigens zu schließen
    flash(`Übernommen: ${karten(r.sitzung.karten)} in ${deck ? 'das Deck ' : ''}„${b}“`);
  } catch (e) { if (!(e instanceof LoginNoetig)) flash('Fehler: ' + e.message); }
}

async function erfKlick(e) {
  if (scanModusWahl(e)) return;
  const t = e.target;
  if (t.closest('#voll-zu')) return scanEnde();
  if (t.closest('#voll-schleier')) return blatt();
  const bl = t.closest('[data-blatt]');
  if (bl) return blatt(bl.dataset.blatt);
  if (vollbild() && t.closest('#scan-hit .hit')) {  // im Vollbild: Tipp auf die letzte Karte öffnet ihre Zeile zum Ändern
    e.preventDefault(); e.stopPropagation();
    const m = erf.letzte, i = m ? erf.liste.zeilen.findIndex(z => z.scryfall_id === m.id && z.foil === m.foil && z.condition === m.condition && z.language === m.language) : -1;
    return i < 0 ? blatt('erf-liste') : erfEdit(i);
  }
  const neu = t.closest('[data-setneu]'), weg = t.closest('[data-setweg]');
  if (neu || weg) {
    const c = (neu || weg).dataset[neu ? 'setneu' : 'setweg'];
    erf.sets = neu ? [...erf.sets, c].slice(0, 6) : erf.sets.filter(x => x !== c);
    if (neu) $('#erf-q').value = '';
    erfMerken(); erfSetsUi(); erfSumme(); erfTreffer();
    if (erf.alle) return;  // ohne Set-Wahl sind die Sets nur eine Vorliebe: nichts neu vorzubereiten
    if (erfIx?.codes === erf.sets.join()) erfBereit();
    else {
      $('#cam-go').disabled = true;
      $('#erf-prep').innerHTML = erf.sets.length ? '<p class="note-line">Sets geändert: Erkennung neu vorbereiten.</p>' : '';
      if (scanStream) { scanStand = 'neu'; $('#scan-status').textContent = 'Sets geändert: erst die Erkennung neu vorbereiten.'; $('#erf-setup').open = true; }
    }
    return;
  }
  const alle = t.closest('[data-erfalle]');
  if (alle) { erf.alle = !!alle.dataset.erfalle; erfMerken(); return render(true); }
  if (t.closest('#erf-kat-go')) return katVorbereiten();
  const pick = t.closest('[data-erfpick]');
  if (pick) {
    const d = erfKand.find(x => x.id === pick.dataset.erfpick);
    erfZug = {...erfZug, frei: false, wahl: false, oids: [d.oid, ...erfKand.filter(x => x !== d).map(x => x.oid)]}; scanStand = '';
    blaetternKarte(d.id, erfWie(d, erfKand));
    return erfZaehlen(d.id, erfWie(d, erfKand), true);
  }
  if (t.closest('[data-messbild]')) return messAusloeser();
  const kb = t.closest('[data-blaettern]');  // Antwort auf „Weitere Kopie gelegt?“ (Phase 57): so viele Kopien wie angeboten, oder keine
  if (kb && blaettern?.id) {
    $('#blaettern-frage')?.remove();
    blaettern.offen = 0;
    for (let i = 0; i < +kb.dataset.blaettern; i++) erfZaehlen(blaettern.id, blaettern.wie);
    return;
  }
  if (t.closest('#erf-plus, [data-erfplus]')) { if (!erf.letzte) return flash('Erst eine Karte scannen'); blaetternKarte(erf.letzte.id, erf.letzte); return erfZaehlen(erf.letzte.id, erf.letzte); }
  if (t.closest('[data-erfzurueck]')) {
    await erfKette;  // erst die laufenden Scans, sonst nähme „zurück“ die vorletzte Karte
    try { const l = await post('erfassen', {aktion: 'liste-zurueck'}); erf.liste = l; erfListe(); flash(`Von der Liste genommen: ${l.weg}`); }
    catch (err) { if (!(err instanceof LoginNoetig)) flash('Fehler: ' + err.message); return; }
    if ($('#scan-hit')) $('#scan-hit').innerHTML = '';
    erf.letzte = null; erfZug = {...erfZug, frei: false, wahl: true}; scanStand = '';
    return;
  }
  if (t.closest('#erf-verwerfen')) {
    if (!confirm(`Die ganze Scan-Liste verwerfen? ${karten(erf.liste.karten)} kommen dann nicht in deine Sammlung.`)) return;
    try { erf.liste = await post('erfassen', {aktion: 'liste-leeren'}); erf.letzte = null; erfListe(); if ($('#scan-hit')) $('#scan-hit').innerHTML = ''; flash('Scan-Liste verworfen'); }
    catch (err) { if (!(err instanceof LoginNoetig)) flash('Fehler: ' + err.message); }
    return;
  }
  if (t.closest('#erf-zurueckholen')) {
    const z = erf.zuletzt;
    if (!confirm(`Die ${karten(z.karten)} wieder aus „${z.binder}“ nehmen und zurück auf die Scan-Liste legen? Dort korrigierst du sie und übernimmst sie neu.`)) return;
    try { const r = await post('erfassen', {aktion: 'sitzung-zurueck', sitzung: z.id}); erf.liste = r.liste; erf.zuletzt = r.zuletzt; erfListe(); erfBinderNeu(); flash('Zurück auf der Scan-Liste'); }
    catch (err) { if (!(err instanceof LoginNoetig)) flash('Fehler: ' + err.message); }
    return;
  }
  if (t.closest('#erf-nochmal')) { for (const b of [...erf.offen]) erfKette = erfKette.then(() => erfSenden(b)); return; }
  const q = t.closest('[data-erfqty]');
  if (q) {
    const z = erf.liste.zeilen[+q.dataset.erfqty], menge = z.qty + +q.dataset.d;
    if (menge === 0 && !confirm(`${z.name} von der Liste nehmen?`)) return;
    return erfAendern(z, {qty: menge});
  }
  const ed = t.closest('[data-erfedit]');
  if (ed) return erfEdit(+ed.dataset.erfedit);
  const um = t.closest('[data-binderneu]');
  if (um) umbenennenDialog(um.dataset.binderneu);
}

// --- Messbilder (Phase 30, PLAN E20): echte Kamerabilder mit Etikett, zum Messen der Erkennung (tests/messbilder_eval.js) ------------------
// Mit „Messbilder speichern“ geht zu jeder gezählten Karte das ganze Kamerabild als JPEG an den eigenen Server (lange Seite höchstens MESS_PX),
// dazu die Lage des Rahmens im Bild. Das Etikett führt der Server über die Zug-Kennung der Scan-Liste. „Bild aufnehmen“ speichert ohne
// Erkennung, die Karte wird danach von Hand zugeordnet (Kandidaten der Erkennung, sonst Suche).
const MESS_PX = 1920, MESS_MERKMAL = {foil: 'Foil', huelle: 'Hülle', deutsch: 'deutsch', schraeg: 'schräg', frei: 'frei im Bild'};
const messWork = document.createElement('canvas');
const mb = b => fmt(b / 1048576, 1) + ' MB';
const messZahl = s => `${plural(s.zahl, 'Messbild', 'Messbilder')}, ${mb(s.bytes)}${s.ohne ? `, ${num(s.ohne)} noch zuordnen` : ''}`;
// Merkmale eines Messbilds: Foil und deutsch stehen im Etikett, die anderen sind angekreuzt
const messMerkmale = m => [...(m.foil && m.foil !== 'normal' ? ['foil'] : []), ...(m.language === 'de' ? ['deutsch'] : []), ...m.merkmale];
let messDaten = [];

function messUi() {  // beim Erfassen: Zeile unter der Kamera nur mit Schalter, Auslöser nur bei laufender Kamera, Zahl und Platz in den Einstellungen
  const zeile = $('#cam-mess'), st = $('#erf-mess-stand'), s = erf.messStand;
  if (zeile) { zeile.hidden = !erf.mess; for (const b of $$('[data-messbild]')) { b.disabled = !scanStream; if (b.closest('.voll-rand')) b.hidden = !erf.mess; } }
  if (st) st.innerHTML = s ? `${s.zahl ? messZahl(s) + '.' : 'Noch keine Messbilder.'} <a href="#/messbilder">Ansehen, zuordnen, löschen</a>` : '';
}

function messBild() {  // das Kamerabild von jetzt -> Versprechen {blob, rahmen}
  const v = $('#cam-video'), f = Math.min(1, MESS_PX / Math.max(v.videoWidth, v.videoHeight)), g = scanG(v);
  messWork.width = Math.round(v.videoWidth * f); messWork.height = Math.round(v.videoHeight * f);
  messWork.getContext('2d').drawImage(v, 0, 0, messWork.width, messWork.height);
  return new Promise(ok => messWork.toBlob(blob => ok({blob, rahmen: [g.x, g.y, g.w, g.h].map(x => (x * f).toFixed(1)).join()}), 'image/jpeg', .85));
}

async function messSenden(bild, zug) {  // -> Eintrag des Servers; bei einem Fehler nichts (Meldung)
  try {
    const {blob, rahmen} = await bild;
    const q = new URLSearchParams({rahmen, ...(erf.huelle ? {merkmale: 'huelle'} : {}), ...(zug ? {zug} : {})});
    const m = await api('messbild?' + q, {method: 'POST', headers: {'Content-Type': 'image/jpeg'}, body: blob});
    if (erf.messStand) { erf.messStand.zahl++; erf.messStand.bytes += m.bytes; messUi(); }
    return m;
  } catch (e) { if (!(e instanceof LoginNoetig)) flash('Messbild nicht gespeichert: ' + e.message); }
}

async function messAusloeser() {  // „Bild aufnehmen“: ohne Erkennung speichern, dann zuordnen; Vorschlag sind die Kandidaten des letzten Bilds
  if (!scanStream) return;
  const m = await messSenden(messBild());
  if (m) { ton(); messDialog(m, erfBest); }
}

function messDialog(m, kand = []) {  // welche Karte das Bild zeigt und die Merkmale zum Ankreuzen
  const foil = m.foil || erf?.foil || 'normal', lang = m.language || erf?.lang || 'en';
  const an = new Set(messMerkmale({foil, language: lang, merkmale: m.merkmale}));
  const eigen = m.scryfall_id ? [{id: m.scryfall_id, name: m.name, set_code: m.set_code, number: m.number, image: m.image}] : [];
  dlg.className = 'modal';
  dlg.innerHTML = `<button class="x" data-close aria-label="Schließen">${icon('x')}</button><div class="box"><h2 id="dlg-title">Messbild ${m.scryfall_id ? 'ändern' : 'zuordnen'}</h2>
    <img class="messbild" alt="Das aufgenommene Kamerabild" src="/api/messbild/${m.id}.jpg">
    <form class="kform" data-mess="${m.id}" data-foil="${esc(foil)}" data-lang="${esc(lang)}"><input type="hidden" name="id" value="${esc(m.scryfall_id || '')}">
      ${wahlHtml([...eigen, ...kand.filter(d => d.id !== m.scryfall_id)], m.scryfall_id)}
      <div class="field"><span>Merkmale</span><div class="seg">${Object.entries(MESS_MERKMAL).map(([k, l]) => `<label class="inl"><input type="checkbox" name="merkmal" value="${k}"${an.has(k) ? ' checked' : ''}> ${l}</label>`).join('')}</div></div>
      <div class="actions"><button class="btn ghost" type="button" id="m-weg">${icon('trash', 'sm')}Löschen</button><button class="btn ghost" type="button" data-close>Später</button><button class="btn primary" type="submit">Speichern</button></div></form></div>`;
  showDlg();
  wahlUi($('form', dlg));
  $('#m-weg').onclick = () => messWeg(m.id);
}

async function messForm(f) {  // Foil und deutsch gehen ins Etikett (sonst bleibt die Sprache bzw. Foil-Art von vorher), der Rest in die Merkmale
  const an = new Set(new FormData(f).getAll('merkmal')), {foil, lang} = f.dataset;
  if (!f.elements.id.value) return flash('Erst die Karte wählen: antippen oder suchen');
  try {
    messNeu(await post('messbilder', {aktion: 'setzen', id: +f.dataset.mess, scryfall_id: f.elements.id.value, foil: !an.has('foil') ? 'normal' : foil !== 'normal' ? foil : 'foil',
      language: an.has('deutsch') ? 'de' : lang === 'de' ? 'en' : lang, merkmale: [...an].filter(k => k !== 'foil' && k !== 'deutsch')}));
    dlg.close(); flash('Messbild gespeichert');
  } catch (e) { if (!(e instanceof LoginNoetig)) flash('Fehler: ' + e.message); }
}

async function messWeg(id) {  // eins, ohne id alle
  try {
    messNeu(await post('messbilder', id ? {aktion: 'weg', id} : {aktion: 'leeren'}));
    if (dlg.open) dlg.close();
    flash(id ? 'Messbild gelöscht' : 'Alle Messbilder gelöscht');
  } catch (e) { if (!(e instanceof LoginNoetig)) flash('Fehler: ' + e.message); }
}

function messNeu(r) {  // nach Zuordnen oder Löschen: die Liste in der Ansicht „Messbilder“ bzw. Zahl und Platz beim Erfassen
  if (erf) erf.messStand = {zahl: r.zahl, bytes: r.bytes};
  if ($('#mess-liste')) messListe(r); else if ($('#erf-mess-stand')) messUi();
}

const messRow = (m, i) => `<div class="row mess"><a href="/api/messbild/${m.id}.jpg" target="_blank" rel="noopener" aria-label="Messbild ${m.id} groß ansehen"><img loading="lazy" alt="" src="/api/messbild/${m.id}.jpg"></a>
  <div class="min0"><div class="name">${m.scryfall_id ? esc(m.name || 'Unbekannter Druck') : 'Noch zuordnen'}</div>
    <div class="sub2">${esc([m.name && `${m.set_code} #${m.number}`, ...messMerkmale(m).map(k => MESS_MERKMAL[k]), `${m.breite} × ${m.hoehe}`, day(m.at)].filter(Boolean).join(', '))}</div></div>
  <div class="seg"><button class="btn small" type="button" data-messedit="${i}">${m.scryfall_id ? 'Ändern' : 'Zuordnen'}</button><button class="btn small" type="button" data-messweg="${m.id}" aria-label="Messbild ${m.id} löschen">${icon('trash', 'sm')}</button></div></div>`;
function messListe(r) {
  messDaten = r.items;
  $('#mess-liste').innerHTML = `<h2>${r.zahl ? messZahl(r) : 'Noch keine Messbilder'}${r.zahl ? `<span class="seg h2r"><button class="btn small" type="button" id="mess-leeren">${icon('trash', 'sm')}Alle löschen</button></span>` : ''}</h2>
    ${r.zahl ? `<div class="rows">${r.items.map(messRow).join('')}</div>` : '<p class="muted">Unter Scannen, Erfassen in den Einstellungen „Messbilder speichern“ einschalten, dann Karten scannen.</p>'}`;
}

async function viewMessbilder() {
  const r = await api('messbilder');
  main.innerHTML = `${head('Messbilder', 'Echte Kamerabilder mit der richtigen Karte als Etikett. Mit ihnen lässt sich messen, wie gut die Erkennung ist, ohne jedes Mal Karten vor die Kamera zu halten.',
    `<a class="btn" href="#/scan?modus=erfassen">${icon('left')}Zum Erfassen</a>`)}
    <p class="note-line">${esc(TIP.messbilder)}</p>
    <section class="sec" aria-label="Messbilder" id="mess-liste"></section>`;
  messListe(r);
  main.onclick = e => {
    const ed = e.target.closest('[data-messedit]'), weg = e.target.closest('[data-messweg]');
    if (ed) return messDialog(messDaten[+ed.dataset.messedit]);
    if (weg) return confirm('Dieses Messbild löschen?') && messWeg(+weg.dataset.messweg);
    if (e.target.closest('#mess-leeren') && confirm(`Alle ${plural(messDaten.length, 'Messbild', 'Messbilder')} löschen? Das lässt sich nicht zurücknehmen.`)) messWeg();
  };
}

const VIEWS = {'': ['Übersicht', viewHome], cards: ['Karten', viewCards], sets: ['Serien', viewSets], sort: ['Sortieren', viewSort], scan: ['Scannen', viewScan], sell: ['Verkaufen', viewSell], decks: ['Decks', viewDecks], wuensche: ['Wünsche', viewWuensche], spiele: ['Spiele', viewSpiele], help: ['Hilfe', viewHelp],
  konten: ['Konten und Sicherung', viewKonten, true], quellen: ['Quellen', viewQuellen, true], binder: ['Binder', viewBinder, true], druck: ['Drucken', viewDruck, true], proxy: ['Proxy-Blatt', viewProxy, true], rueckblick: ['Rückblick', viewRueckblick, true], bericht: ['Wert-Bericht', viewBericht, true], messbilder: ['Messbilder', viewMessbilder, true]};  // true: nicht in der Navigation (Link im Fuß)
const calm = matchMedia('(prefers-reduced-motion: reduce)');
let rendered = null, enterTimer, neueAnsicht = false;
// Zahl läuft beim ersten Aufruf der Ansicht hoch (nicht beim Neuzeichnen, nicht bei reduzierter Bewegung)
const zaehlen = (el, ziel, fmt) => {
  if (!el) return;
  const von = +el.dataset.z || 0, t0 = performance.now(), dauer = 800 * Math.min(1, Math.abs(ziel - von) / Math.max(Math.abs(ziel), 1) + .2);
  el.dataset.z = ziel;
  if (calm.matches) { el.textContent = fmt(ziel); return; }
  el.textContent = fmt(von);
  const schritt = t => { const k = Math.min((t - t0) / dauer, 1); el.textContent = fmt(von + (ziel - von) * (1 - (1 - k) ** 3)); if (k < 1) requestAnimationFrame(schritt); };
  requestAnimationFrame(schritt);
};
const bump = el => { el.classList.remove('bump'); void el.offsetWidth; el.classList.add('bump'); };  // kurzes Springen, wenn sich eine Zahl erhöht
// Kacheln und die Karte im Detail neigen sich zur Maus (nur mit Maus, nicht bei reduzierter Bewegung, höchstens 7 Grad)
let geneigt = null;
const aufrichten = () => { geneigt?.style.removeProperty('--rx'); geneigt?.style.removeProperty('--ry'); geneigt = null; };
document.addEventListener('pointermove', e => {
  const c = e.pointerType === 'mouse' && !calm.matches ? e.target.closest('.grid > .card, .dtop .img') : null;
  if (c !== geneigt) aufrichten();
  if (!c) return;
  geneigt = c;
  const b = c.getBoundingClientRect();
  c.style.setProperty('--ry', `${((e.clientX - b.left) / b.width - .5) * 14}deg`);
  c.style.setProperty('--rx', `${(.5 - (e.clientY - b.top) / b.height) * 14}deg`);
}, {passive: true});
document.documentElement.addEventListener('pointerleave', aufrichten);

// --- Hintergrund (E35): „Meine Karten“ (kartenHg, Standard), Funken oder nur der Schimmer aus CSS. Funken in den fünf Mana-Farben treiben hinter der Seite, verbinden sich zu Sternbildern und weichen der Maus aus; beim Öffnen stieben sie aus der Mitte.
// Der Schimmer dahinter ist reines CSS. Bei „weniger Bewegung“ steht ein ruhiges Bild, im Scanner (Vollbild) und im Druck ruht alles; im Fuß lässt sich der Hintergrund wählen.
const hgSel = $('#hintergrund'), cv = $('#funken'), cx = cv.getContext('2d');
const hgPref = () => { try { return localStorage.getItem('mtg-hg') || 'karten'; } catch { return 'karten'; } };
let fPts = [], fFarben = [], fA = .85, fLaeuft = false, fN = 0;
const fMaus = {x: -1e4, y: -1e4};
const fLesen = () => { const s = getComputedStyle(document.documentElement); fFarben = ['w', 'u', 'b', 'r', 'g'].map(k => s.getPropertyValue('--aura-' + k).trim()); fA = +s.getPropertyValue('--funken-a') || .85; };
const fGroesse = () => { const d = Math.min(devicePixelRatio || 1, 1.5); cv.width = innerWidth * d; cv.height = innerHeight * d; cx.setTransform(d, 0, 0, d, 0, 0); };
const fNeu = burst => {
  const n = Math.max(28, Math.min(90, Math.round(innerWidth * innerHeight / 17000)));
  fPts = Array.from({length: n}, (_, i) => {
    const w = Math.random() * 6.283, v = burst ? 4 + Math.random() * 12 : 0;
    return {x: burst ? innerWidth / 2 : Math.random() * innerWidth, y: burst ? innerHeight * .4 : Math.random() * innerHeight, vx: Math.cos(w) * v, vy: Math.sin(w) * v,
      bx: (Math.random() - .5) * .35, by: (Math.random() - .5) * .35, r: .9 + Math.random() * 1.6, c: i % 5, ph: Math.random() * 6.283};
  });
};
const fZeichnen = t => {
  cx.clearRect(0, 0, innerWidth, innerHeight);
  for (const p of fPts) { cx.globalAlpha = (.45 + .4 * Math.sin(t / 900 + p.ph)) * fA; cx.fillStyle = fFarben[p.c]; cx.beginPath(); cx.arc(p.x, p.y, p.r, 0, 6.283); cx.fill(); }
  cx.lineWidth = .6;
  for (let i = 0; i < fPts.length; i++) for (let k = i + 1; k < fPts.length; k++) {
    const a = fPts[i], b = fPts[k], d = Math.hypot(a.x - b.x, a.y - b.y);
    if (d < 130) { cx.globalAlpha = (1 - d / 130) * .32 * fA; cx.strokeStyle = fFarben[a.c]; cx.beginPath(); cx.moveTo(a.x, a.y); cx.lineTo(b.x, b.y); cx.stroke(); }
  }
};
const fLauf = t => {
  if (calm.matches || hgPref() !== 'an') { fLaeuft = false; return; }
  if (cv.getClientRects().length) {  // nicht im Scanner (Vollbild): dort ist das Canvas ausgeblendet
    if (++fN % 120 === 0) fLesen();  // Darstellung (dunkel oder hell) kann sich geändert haben
    for (const p of fPts) {
      p.vx += (p.bx - p.vx) * .03; p.vy += (p.by - p.vy) * .03;
      const dx = p.x - fMaus.x, dy = p.y - fMaus.y, d = Math.hypot(dx, dy);
      if (d < 140 && d > 0) { p.vx += dx / d * (1 - d / 140) * .06; p.vy += dy / d * (1 - d / 140) * .06; }
      p.x += p.vx; p.y += p.vy;
      if (p.x < -10) p.x = innerWidth + 10; else if (p.x > innerWidth + 10) p.x = -10;
      if (p.y < -10) p.y = innerHeight + 10; else if (p.y > innerHeight + 10) p.y = -10;
    }
    fZeichnen(t);
  }
  requestAnimationFrame(fLauf);
};
// „Meine Karten“: zufällige der zuletzt gescannten Karten schweben und drehen sich sehr langsam hinter der Seite. Kleine Bilder (146 px), nur transform und opacity, nie ein Filter
// (Scryfall verbietet Weichzeichnen, Schärfen, Entsättigen, Umfärben und Verzerren). Geladen wird erst nach der ersten Ansicht, höchstens einmal je Start.
let kFertig = false, kBusy = false;
const kBox = $('#karten-hg');
const kartenHg = async () => {
  if (kFertig || kBusy || hgPref() !== 'karten') return;
  kBusy = true;
  try {
    let r = await api(`cards?sort=added&per_page=120&page=${1 + Math.floor(Math.random() * 3)}`);
    if (!r.items.length) r = await api('cards?sort=added&per_page=120');
    const schmal = innerWidth < 700, n = schmal ? 9 : 18, spalten = schmal ? 3 : 6, rnd = (a, b) => a + Math.random() * (b - a);
    const wahl = r.items.filter(c => c.image).sort(() => Math.random() - .5).slice(0, n), zeilen = Math.ceil(wahl.length / spalten);
    kBox.innerHTML = wahl.map((c, i) => {
      const f = schmal ? .7 : 1, w = rnd(90, 160) * f, nah = (w / f - 90) / 70, t = rnd(70, 130);  // größer heißt näher: deckender, bewegt sich mehr mit der Maus
      const v = {px: ((i % spalten + .5) / spalten * 100 + rnd(-5, 5)).toFixed(1) + '%', py: ((Math.floor(i / spalten) + .5) / zeilen * 100 + rnd(-7, 7)).toFixed(1) + '%', w: w.toFixed(0) + 'px',
        o: (.24 + nah * .2).toFixed(2), d: Math.round(8 + nah * 26), t: t.toFixed(0) + 's', s: '-' + rnd(0, t).toFixed(0) + 's', dx: rnd(-60, 60).toFixed(0) + 'px', dy: rnd(-50, 50).toFixed(0) + 'px',
        z0: rnd(-18, 18).toFixed(0) + 'deg', z1: rnd(-18, 18).toFixed(0) + 'deg', y0: rnd(-50, 50).toFixed(0) + 'deg', y1: rnd(-50, 50).toFixed(0) + 'deg', x0: rnd(-14, 14).toFixed(0) + 'deg', x1: rnd(-14, 14).toFixed(0) + 'deg'};
      return `<span class="bk" style="${Object.entries(v).map(([k, x]) => `--${k}:${x}`).join(';')}"><img alt="" src="${esc(small(c.image))}"></span>`;
    }).join('');
    kFertig = true;
  } catch { /* ohne Karten oder ohne Anmeldung bleibt der Schimmer allein; render() versucht es nach der Anmeldung noch einmal */ }
  kBusy = false;
};
const hgAnwenden = burst => {
  const m = hgPref();
  document.documentElement.dataset.hg = m;
  if (m !== 'an') return;
  fLesen(); fGroesse(); fNeu(burst && !calm.matches);
  if (calm.matches) fZeichnen(0);  // ein ruhiges Bild statt Bewegung
  else if (!fLaeuft) { fLaeuft = true; requestAnimationFrame(fLauf); }
};
hgSel.value = hgPref();
hgSel.onchange = () => { try { localStorage.setItem('mtg-hg', hgSel.value); } catch { /* privates Fenster: gilt bis zum Neuladen */ } hgAnwenden(true); kartenHg(); };
addEventListener('pointermove', e => {
  fMaus.x = e.clientX; fMaus.y = e.clientY;
  if (kBox.firstChild) { kBox.style.setProperty('--mx', (.5 - e.clientX / innerWidth) * 2); kBox.style.setProperty('--my', (.5 - e.clientY / innerHeight) * 2); }  // die Karten wandern gegen die Maus, die nahen mehr
}, {passive: true});
document.documentElement.addEventListener('pointerleave', () => { fMaus.x = -1e4; });
addEventListener('resize', () => { if (hgPref() === 'an') { fGroesse(); fNeu(false); if (calm.matches) fZeichnen(0); } });
hgAnwenden(true);
// neue Ansicht: Abschnitte blenden gestaffelt ein (nicht bei Neuzeichnen derselben Ansicht, das soll ruhig bleiben)
const animateIn = () => {
  if (calm.matches) return;
  [...main.children].forEach((el, i) => el.style.setProperty('--i', Math.min(i, 8)));
  main.classList.remove('enter'); void main.offsetWidth; main.classList.add('enter');
  clearTimeout(enterTimer); enterTimer = setTimeout(() => main.classList.remove('enter'), 1500);
};
async function render(force) {
  const hash = location.hash || '#/';
  if (!hash.startsWith('#/') || loginOffen) return;  // Sprunglink (#main) ist keine Ansicht; vor der Anmeldung nichts laden
  if (!force && hash === rendered) return;
  const neu = neueAnsicht = hash.split('?')[0] !== (rendered || '').split('?')[0];
  rendered = hash;
  const [path, qs] = hash.slice(2).split('?');
  const [title, view] = VIEWS[path] || ['Nicht gefunden', viewMissing];
  document.title = `${title} · ${APP}`;
  $('#nav').innerHTML = Object.entries(VIEWS).filter(([, [, , versteckt]]) => !versteckt).map(([k, [l]]) => `<a href="#/${k}"${k === path ? ' aria-current="page"' : ''}>${l}</a>`).join('');
  hidePeek(); hideTip(); scanStop(); main.onclick = main.onchange = main.onkeydown = null;
  const vorher = main.firstElementChild;  // Skelett nur, solange die neue Ansicht noch nichts geschrieben hat (viewCards schreibt vor dem Laden)
  const slow = setTimeout(() => { if (rendered === hash && main.firstElementChild === vorher) main.innerHTML = skeleton(); }, 160);
  try { await view(new URLSearchParams(qs || '')); if (neu) { scrollTo(0, 0); animateIn(); } beispielLeiste(); kartenHg(); }
  catch (e) { if (e instanceof LoginNoetig) return; main.innerHTML = `<section class="panel error"><h2>${icon('alert')}Das hat nicht geklappt</h2><p class="muted">${esc(e.message)}</p><button class="btn" type="button" data-retry>${icon('refresh')}Nochmal versuchen</button></section>`; }
  finally { clearTimeout(slow); }
}
addEventListener('hashchange', () => render());
navigator.serviceWorker?.register('/sw.js').catch(() => {});  // nur damit der Browser die Installation als App anbietet (sw.js)
(async () => {  // erst die Sitzung: mit Anmeldung und ohne gültiges Cookie gleich die Anmeldeseite
  try { sess = await api('session'); $('#version').textContent = sess.version || ''; }
  catch {  // keine Auskunft: Wartet der Server auf die erste Einrichtung (Phase 43), antwortet er nur noch darauf
    try { if ((await api('einrichtung')).modus === 'einrichtung') return showEinrichtung(); } catch { /* ohne Antwort wie bisher: eine Sammlung */ }
  }
  if (sess.modus === 'anmeldung' && !sess.angemeldet) return showLogin();
  whoUi(); render();
  api('jobs').then(j => { jobs = j; if (Object.values(j).some(x => x.running)) pollJobs(); }).catch(() => {});
})();

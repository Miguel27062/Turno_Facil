(() => {
  const raiz = document.getElementById('hud');
  const $ = id => document.getElementById(id);
  const reducir = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let voz = false, primera = true, ultimaMarca = 0, firmaActuales = '', firmaProximos = '', temporizador;

  // QR para pedir turno desde el celular
  if (window.QRCode) new QRCode($('qr'), { text: location.origin + raiz.dataset.solicitar, width: 96, height: 96 });

  // Reloj
  const reloj = () => {
    const d = new Date();
    $('reloj').replaceChildren(
      d.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' }),
      Object.assign(document.createElement('small'), { textContent: d.toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'long' }) }));
  };
  reloj(); setInterval(reloj, 15000);

  // Voz y sonido (el navegador exige un clic para permitirlos)
  $('sonido').addEventListener('click', e => {
    voz = !voz; e.target.textContent = voz ? 'Voz activada' : 'Activar voz y sonido';
    if (voz) hablar('Sonido activado');
  });
  function hablar(texto) {
    if (!voz || !('speechSynthesis' in window)) return;
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)(), o = ctx.createOscillator(), g = ctx.createGain();
      o.type = 'sine'; o.connect(g); g.connect(ctx.destination);
      o.frequency.setValueAtTime(660, ctx.currentTime); o.frequency.setValueAtTime(990, ctx.currentTime + .18);
      g.gain.setValueAtTime(.2, ctx.currentTime); g.gain.exponentialRampToValueAtTime(.001, ctx.currentTime + .6);
      o.start(); o.stop(ctx.currentTime + .6);
    } catch (_) {}
    const u = new SpeechSynthesisUtterance(texto); u.lang = 'es-ES'; u.rate = .9;
    setTimeout(() => speechSynthesis.speak(u), 650);
  }
  const decir = t => { const [p, n] = t.codigo.split('-'); return `Turno ${p.split('').join(' ')} ${parseInt(n, 10) || ''}, ${t.puesto}`; };

  const el = (tag, cls, txt) => { const n = document.createElement(tag); if (cls) n.className = cls; if (txt !== undefined) n.textContent = txt; return n; };

  // Anuncio a pantalla completa cuando llaman un turno
  function anunciar(t) {
    const a = $('anuncio');
    $('a-codigo').textContent = t.codigo; $('a-puesto').textContent = t.puesto;
    a.classList.add('on');
    dispatchEvent(new Event('turno:llamado'));  // la rueda 3D se acelera
    if (window.gsap && !reducir) {
      gsap.fromTo('.a-cuerpo', { scale: .55, opacity: 0, rotateX: -30 }, { scale: 1, opacity: 1, rotateX: 0, duration: .8, ease: 'back.out(1.8)' });
      gsap.fromTo('.choque', { scale: .2, opacity: .9 }, { scale: 3.4, opacity: 0, duration: 1.7, stagger: .25, ease: 'power2.out' });
    }
    clearTimeout(temporizador); temporizador = setTimeout(() => a.classList.remove('on'), 5000);
  }

  function pintarActuales(d) {
    const caja = $('actuales'); caja.replaceChildren();
    if (!d.actuales.length) { caja.append(el('div', 'vacio', 'Esperando el próximo llamado…')); return; }
    d.actuales.forEach(t => {
      const nuevo = !primera && t.marca > ultimaMarca;
      const c = el('article', 'tarjeta tilt' + (nuevo ? ' nuevo' : ''));
      c.append(el('div', 't-puesto', t.puesto), el('div', 't-codigo', t.codigo),
               el('div', 't-info', [t.cliente, t.servicio].filter(Boolean).join(' · ')));
      caja.append(c);
    });
  }

  function pintarProximos(d) {
    const caja = $('proximos'); caja.replaceChildren();
    if (!d.proximos.length) { caja.append(el('p', '', 'No hay turnos en espera.')); return; }
    d.proximos.forEach(t => {
      const f = el('div', 'proximo');
      const meta = el('span'); meta.append(el('span', '', t.servicio));
      meta.append(el('br'), el('small', '', t.espera ? `en unos ${t.espera} min` : 'es el siguiente'));
      f.append(el('span', 'codigo p-' + t.prioridad, t.codigo), meta);
      caja.append(f);
    });
  }

  function pintarTicker(d) {
    const frases = [
      ['Personas en espera: ', d.en_espera],
      ['Si llegas ahora, esperas unos ', d.espera_nuevo + ' min'],
      ['Pide tu turno escaneando el código QR', ''],
      ['Te avisamos en pantalla y con voz cuando sea tu turno', ''],
    ];
    const bloque = () => { const s = el('span'); frases.forEach(([a, b], i) => { s.append(a); if (b !== '') s.append(el('b', '', b)); if (i < frases.length - 1) s.append('   ·   '); }); return s; };
    const pista = $('ticker'), firma = JSON.stringify(frases);
    if (pista.dataset.firma === firma) return;
    pista.dataset.firma = firma; pista.replaceChildren(bloque(), bloque());
  }

  function pintar(d) {
    const fa = JSON.stringify(d.actuales), fp = JSON.stringify(d.proximos);
    const ultimo = d.actuales[0];
    const llamaron = ultimo && ultimo.marca > ultimaMarca && !primera;
    if (fa !== firmaActuales) pintarActuales(d);
    if (fp !== firmaProximos) pintarProximos(d);
    pintarTicker(d);
    firmaActuales = fa; firmaProximos = fp;
    if (llamaron) { anunciar(ultimo); hablar(decir(ultimo)); }
    if (ultimo) ultimaMarca = Math.max(ultimaMarca, ultimo.marca);
    primera = false;
    if (window.initTilt) window.initTilt();
  }

  async function ciclo() {
    try { const r = await fetch(raiz.dataset.url, { cache: 'no-store' }); if (r.ok) pintar(await r.json()); } catch (_) {}
  }
  ciclo(); setInterval(ciclo, 3000);
})();

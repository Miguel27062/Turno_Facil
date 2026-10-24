(() => {
  const reducir = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const movil = innerWidth < 760;

  /* ---------- Fondo: autopista nocturna en exposición larga ----------
     Faros blancos que se acercan, luces traseras ámbar y rojas que se alejan.
     Carros (dos luces) y motos (una luz) comparten la carretera. */
  let warp = 0;  // al llamar un turno las estelas se estiran
  addEventListener('turno:llamado', () => { warp = 1; });

  function iniciarFondo(canvas) {
    const ctx = canvas.getContext('2d');
    const modo = document.body.dataset.fx;
    const Z0 = 9, Z1 = 520, CAMARA = 5.2, RITMO = modo === 'pantalla' ? .85 : .65;
    const N = movil ? 54 : modo === 'pantalla' ? 140 : 100;
    const suave = (a, b, x) => { x = Math.min(1, Math.max(0, (x - a) / (b - a))); return x * x * (3 - 2 * x); };
    let W, H, DPR, F, vx0, vy0, vx, vy, mx = 0, my = 0, t = 0, visible = true, previo = performance.now();

    const elegir = lista => lista[Math.floor(Math.random() * lista.length)];
    function vehiculo(inicial) {
      const entrante = Math.random() < .5, moto = Math.random() < .3;
      const lado = entrante ? -1 : 1;
      return {
        entrante, moto,
        x: moto ? (Math.random() - .5) * 18 : lado * (2.5 + Math.random() * 7),
        sep: moto ? 0 : .75,
        z: inicial ? Z0 * Math.pow(Z1 / Z0, Math.random()) : entrante ? Z1 * (.75 + Math.random() * .25) : Z0 * (1 + Math.random() * 1.5),
        v: (20 + Math.random() * 40) * RITMO,
        brillo: .55 + Math.random() * .45,
        rgb: entrante ? elegir(['225,242,255', '225,242,255', '120,232,255']) : elegir(['255,150,50', '255,178,36', '255,78,70']),
      };
    }
    const flota = Array.from({ length: N }, () => vehiculo(true));

    function ajustar() {
      DPR = Math.min(devicePixelRatio || 1, 1.5);
      W = canvas.width = Math.round(innerWidth * DPR); H = canvas.height = Math.round(innerHeight * DPR);
      F = H * .95;
      vx0 = W * (modo === 'pantalla' || movil ? .5 : .66); vy0 = H * (modo === 'pantalla' ? .36 : movil ? .26 : .3);
      vx = vx0; vy = vy0;
      const r = document.documentElement.style;
      r.setProperty('--vx', (vx0 / W * 100).toFixed(1) + '%'); r.setProperty('--vy', (vy0 / H * 100).toFixed(1) + '%');
    }
    addEventListener('resize', ajustar); ajustar();
    addEventListener('pointermove', e => { mx = e.clientX / innerWidth - .5; my = e.clientY / innerHeight - .5; });
    document.addEventListener('visibilitychange', () => { visible = !document.hidden; previo = performance.now(); });

    function paso(dt) {
      t += dt; warp *= Math.pow(.2, dt);   // el efecto se apaga en un par de segundos
      for (const c of flota) {
        c.z += (c.entrante ? -1 : 1) * c.v * (1 + warp * 2.2) * dt;
        if (c.entrante ? c.z < Z0 : c.z > Z1) Object.assign(c, vehiculo(false));
      }
    }

    function dibujar() {
      ctx.clearRect(0, 0, W, H);
      ctx.globalCompositeOperation = 'lighter'; ctx.lineCap = 'round';
      const curva = (Math.sin(t * .09) * .6 + Math.sin(t * .037 + 1) * .4) * (modo === 'pantalla' ? .6 : 1);
      vx += (vx0 + mx * W * .05 - vx) * .05; vy += (vy0 + my * H * .03 - vy) * .05;
      const proy = (X, Y, z) => { const k = F / z; return [vx + (X + curva * .0006 * z * z) * k, vy + Y * k]; };

      for (const c of flota) {
        const a = suave(Z0, 60, c.z) * (1 - suave(260, Z1, c.z)) * c.brillo;
        if (a < .02) continue;
        const largo = c.v * (1.25 + warp * 1.1), z2 = Math.max(Z0 * .6, c.z - (c.entrante ? -1 : 1) * largo);
        const Y = CAMARA - (c.moto ? .55 : .75);
        for (const d of c.moto ? [0] : [-c.sep, c.sep]) {
          const [x1, y1] = proy(c.x + d, Y, c.z), [x2, y2] = proy(c.x + d, Y, z2);
          if ((x1 < -300 && x2 < -300) || (x1 > W + 300 && x2 > W + 300) || y1 > H + 300) continue;
          const w = Math.max(1.1 * DPR, .06 * F / c.z);
          const g = ctx.createLinearGradient(x1, y1, x2, y2);
          g.addColorStop(0, `rgba(${c.rgb},${a})`); g.addColorStop(1, `rgba(${c.rgb},0)`);
          ctx.strokeStyle = g; ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
          ctx.globalAlpha = .2; ctx.lineWidth = w * 3.6; ctx.stroke();   // resplandor
          ctx.globalAlpha = 1; ctx.lineWidth = w; ctx.stroke();           // núcleo
          if (c.z < 140) {                                                 // punto brillante del faro
            ctx.fillStyle = `rgba(255,255,255,${a * .8})`; ctx.beginPath(); ctx.arc(x1, y1, w * .75, 0, 6.2832); ctx.fill();
          }
        }
      }
      ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
    }

    if (reducir) { for (let i = 0; i < 120; i++) paso(.05); dibujar(); return; }  // un solo cuadro estático
    (function bucle(ahora) {
      requestAnimationFrame(bucle);
      if (!visible) return;
      const dt = Math.min(.05, (ahora - previo) / 1000 || .016); previo = ahora;
      paso(dt); dibujar();
    })(performance.now());
  }

  const canvas = document.getElementById('fx');
  if (canvas) { try { iniciarFondo(canvas); } catch (_) { canvas.remove(); } }

  /* ---------- Tarjetas 3D que siguen el puntero (también las creadas después) ---------- */
  window.initTilt = () => {
    if (reducir || !matchMedia('(hover:hover)').matches) return;
    document.querySelectorAll('.tilt:not([data-tilt])').forEach(el => {
      el.dataset.tilt = '1';
      el.addEventListener('pointermove', e => {
        const r = el.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
        el.style.transform = `perspective(900px) rotateY(${x * 10}deg) rotateX(${-y * 10}deg) translateY(-3px)`;
      });
      el.addEventListener('pointerleave', () => el.style.transform = '');
    });
  };
  window.initTilt();

  /* ---------- Entrada orquestada (una sola vez por página) ---------- */
  if (window.gsap && !reducir) {
    gsap.from('.entra', { y: 28, opacity: 0, duration: .8, stagger: .09, ease: 'power3.out', clearProps: 'transform,opacity' });
  }

  /* ---------- Contadores ---------- */
  document.querySelectorAll('[data-cuenta]').forEach(el => {
    const fin = +el.dataset.cuenta;
    if (reducir || !window.gsap) { el.textContent = fin; return; }
    const o = { v: 0 };
    gsap.to(o, { v: fin, duration: 1.2, ease: 'power2.out', onUpdate: () => el.textContent = Math.round(o.v) });
  });

  /* ---------- Onda al pulsar botones ---------- */
  document.addEventListener('pointerdown', e => {
    const b = e.target.closest('.btn'); if (!b || reducir) return;
    const r = b.getBoundingClientRect(), d = Math.max(r.width, r.height) / 2, s = document.createElement('span');
    s.className = 'ripple'; s.style.cssText = `width:${d}px;height:${d}px;left:${e.clientX - r.left - d / 2}px;top:${e.clientY - r.top - d / 2}px`;
    b.appendChild(s); setTimeout(() => s.remove(), 600);
  });

  /* ---------- Transición suave entre páginas ---------- */
  const velo = document.getElementById('velo');
  document.addEventListener('click', e => {
    const a = e.target.closest('a[href]');
    if (!a || !velo || reducir || a.target || e.metaKey || e.ctrlKey || a.origin !== location.origin || a.hash) return;
    e.preventDefault(); velo.classList.add('on'); setTimeout(() => location.href = a.href, 260);
  });
  addEventListener('pageshow', () => velo && velo.classList.remove('on'));
})();

(() => {
  const reducir = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const movil = innerWidth < 760;

  /* ---------- Fondo 3D: freno de disco con pinza (carros y motos) ---------- */
  let impulso = 0;  // el disco se acelera cuando llaman un turno
  addEventListener('turno:llamado', () => { impulso = .22; });

  function iniciarEscena(canvas) {
    const modo = document.body.dataset.fx;
    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: !movil, powerPreference: 'low-power' });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75));
    renderer.outputEncoding = THREE.sRGBEncoding;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, .1, 100);
    camera.position.set(0, 0, 13);

    // Reflejos de estudio: paneles de luz cian, ámbar y blanca que le dan brillo metálico
    const estudio = new THREE.Scene();
    const panel = (color, fuerza, w, h, x, y, z) => {
      const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h),
        new THREE.MeshBasicMaterial({ color: new THREE.Color(color).multiplyScalar(fuerza), side: THREE.DoubleSide }));
      m.position.set(x, y, z); m.lookAt(0, 0, 0); estudio.add(m);
    };
    panel(0x35e6ff, 3.2, 10, 3, -8, 4, 4); panel(0xffb224, 3.6, 8, 2, 8, -2, 5);
    panel(0xffffff, 2.2, 12, 2, 0, 9, 2); panel(0x1a2640, 1, 40, 40, 0, 0, -14);
    const pmrem = new THREE.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(estudio, .04).texture;

    scene.add(new THREE.AmbientLight(0x8fa3c4, .25));
    const luz = new THREE.DirectionalLight(0xcfeeff, 1.1); luz.position.set(-5, 6, 8); scene.add(luz);
    const calida = new THREE.PointLight(0xffb224, 2, 30); calida.position.set(6, -3, 5); scene.add(calida);

    const conjunto = new THREE.Group();   // todo el mecanismo
    const rotor = new THREE.Group();      // la parte que gira
    const R = 3;

    // Disco ventilado: agujero central, tornillos y dos coronas de perforaciones
    const forma = new THREE.Shape(); forma.absarc(0, 0, R, 0, Math.PI * 2, false);
    const hueco = (x, y, r) => { const h = new THREE.Path(); h.absarc(x, y, r, 0, Math.PI * 2, true); forma.holes.push(h); };
    hueco(0, 0, 1.05);
    for (let i = 0; i < 5; i++) { const t = i / 5 * Math.PI * 2; hueco(Math.cos(t) * 1.5, Math.sin(t) * 1.5, .11); }
    const N = movil ? 20 : 28;
    for (let i = 0; i < N; i++) {
      const t = i / N * Math.PI * 2, u = (i + .5) / N * Math.PI * 2;
      hueco(Math.cos(t) * 2.3, Math.sin(t) * 2.3, .13);
      hueco(Math.cos(u) * 2.65, Math.sin(u) * 2.65, .1);
    }
    const gDisco = new THREE.ExtrudeGeometry(forma, { depth: .32, bevelEnabled: true, bevelThickness: .03, bevelSize: .03, bevelSegments: 2, curveSegments: movil ? 16 : 28 });
    gDisco.translate(0, 0, -.16);
    rotor.add(new THREE.Mesh(gDisco, new THREE.MeshStandardMaterial({ color: 0xaab6c6, metalness: .92, roughness: .3 })));

    const aro = r => {   // surcos maquinados sobre la cara del disco
      const pts = []; for (let i = 0; i <= 128; i++) pts.push(new THREE.Vector3(Math.cos(i / 128 * Math.PI * 2) * r, Math.sin(i / 128 * Math.PI * 2) * r, .2));
      return new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0x35e6ff, transparent: true, opacity: .35 }));
    };
    rotor.add(aro(1.9), aro(2.95), aro(1.25));
    const campana = new THREE.Mesh(new THREE.CylinderGeometry(1.3, 1.45, .55, 48), new THREE.MeshStandardMaterial({ color: 0x3b4352, metalness: .8, roughness: .5 }));
    campana.rotation.x = Math.PI / 2; campana.position.z = -.38; rotor.add(campana);
    for (let i = 0; i < 5; i++) {
      const t = i / 5 * Math.PI * 2;
      const tornillo = new THREE.Mesh(new THREE.CylinderGeometry(.17, .17, .08, 6), new THREE.MeshStandardMaterial({ color: 0xd5dde8, metalness: 1, roughness: .25 }));
      tornillo.rotation.x = Math.PI / 2; tornillo.position.set(Math.cos(t) * 1.5, Math.sin(t) * 1.5, .2); rotor.add(tornillo);
    }
    conjunto.add(rotor);

    // Pinza de freno ámbar (fija) con ventana
    const c = new THREE.Shape(), a0 = -.42, a1 = .42;
    c.absarc(0, 0, 3.5, a0, a1, false); c.absarc(0, 0, 2.05, a1, a0, true);
    const vent = new THREE.Path(); vent.moveTo(2.45, -.3); vent.lineTo(3.15, -.3); vent.lineTo(3.15, .3); vent.lineTo(2.45, .3); vent.closePath(); c.holes.push(vent);
    const gPinza = new THREE.ExtrudeGeometry(c, { depth: .95, bevelEnabled: true, bevelThickness: .08, bevelSize: .08, bevelSegments: 3, curveSegments: 24 });
    gPinza.translate(0, 0, -.475);
    const pinza = new THREE.Mesh(gPinza, new THREE.MeshStandardMaterial({ color: 0xffb224, metalness: .55, roughness: .38, emissive: 0x3a2200, emissiveIntensity: .5 }));
    pinza.rotation.z = .62; conjunto.add(pinza);

    // Bisel de telemetría: arcos y marcas que giran en sentido contrario
    const telemetria = new THREE.Group();
    const mat = (o) => new THREE.MeshBasicMaterial({ color: 0x35e6ff, transparent: true, opacity: o, side: THREE.DoubleSide });
    [[0, 1.7, .55], [2.1, .9, .35], [3.4, 2.2, .5], [5.8, .4, .7]].forEach(([ini, largo, o]) =>
      telemetria.add(new THREE.Mesh(new THREE.RingGeometry(4, 4.06, 64, 1, ini, largo), mat(o))));
    const marcas = []; for (let i = 0; i < 90; i++) {
      const t = i / 90 * Math.PI * 2, largo = i % 5 === 0 ? .22 : .1;
      marcas.push(Math.cos(t) * 4.25, Math.sin(t) * 4.25, 0, Math.cos(t) * (4.25 + largo), Math.sin(t) * (4.25 + largo), 0);
    }
    const gMarcas = new THREE.BufferGeometry(); gMarcas.setAttribute('position', new THREE.Float32BufferAttribute(marcas, 3));
    telemetria.add(new THREE.LineSegments(gMarcas, new THREE.LineBasicMaterial({ color: 0x35e6ff, transparent: true, opacity: .3 })));
    conjunto.add(telemetria);

    // Composición según la página
    const base = modo === 'pantalla' ? { x: 0, y: 0, z: -3, s: 1.25 } : movil ? { x: 0, y: 3.4, z: -2, s: .6 } : { x: 5.2, y: .2, z: -1, s: .95 };
    conjunto.position.set(base.x, base.y, base.z); conjunto.scale.setScalar(base.s);
    conjunto.rotation.set(.16, -.55, 0);
    scene.add(conjunto);

    // Polvo de luz
    const NP = movil ? 60 : 140, pos = new Float32Array(NP * 3);
    for (let i = 0; i < NP * 3; i++) pos[i] = (Math.random() - .5) * 28;
    const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    const polvo = new THREE.Points(geo, new THREE.PointsMaterial({ color: 0x9fdcff, size: .035, transparent: true, opacity: .35 }));
    scene.add(polvo);

    let mx = 0, my = 0, visible = true;
    addEventListener('pointermove', e => { mx = e.clientX / innerWidth - .5; my = e.clientY / innerHeight - .5; });
    document.addEventListener('visibilitychange', () => { visible = !document.hidden; });
    const ajustar = () => { renderer.setSize(innerWidth, innerHeight, false); camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); };
    addEventListener('resize', ajustar); ajustar();

    (function bucle() {
      requestAnimationFrame(bucle);
      if (!visible) return;
      const desplazado = Math.min(scrollY, 1200);
      rotor.rotation.z -= .005 + impulso;
      telemetria.rotation.z += .0022 + impulso * .35;
      conjunto.rotation.y += (-.55 + mx * .5 - conjunto.rotation.y) * .04;
      conjunto.rotation.x += (.16 + my * .35 - conjunto.rotation.x) * .04;
      conjunto.position.y = base.y + desplazado * .0025;
      conjunto.scale.setScalar(base.s * (1 + impulso * .45));
      polvo.rotation.y += .0004 + impulso * .03;
      impulso *= .965;
      renderer.render(scene, camera);
    })();
  }

  const canvas = document.getElementById('fx');
  if (canvas && window.THREE && !reducir) {
    try { iniciarEscena(canvas); } catch (_) { canvas.remove(); }  // si no hay WebGL, queda el fondo en CSS
  }

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

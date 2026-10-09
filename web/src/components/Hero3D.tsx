import { useEffect, useRef } from "react";
import * as THREE from "three";
import { useTheme } from "./theme";

/**
 * Two ink ribbons drawn on moving chart paper: universe A (before the PR) and universe B (after).
 * Where they agree the ribbons run together; where behavior diverges, B spikes away and a marker lights up.
 */

const N = 260;
const SPAN = 14;

function cssHsl(name: string): THREE.Color {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const [h, s, l] = raw.split(/\s+/);
  return new THREE.Color(`hsl(${parseFloat(h)}, ${s}, ${l})`);
}

function base(s: number) {
  return 0.16 * Math.sin(s * 1.7) + 0.07 * Math.sin(s * 4.3 + 1.3) + 0.035 * Math.sin(s * 9.1 + 0.4);
}

function hash(k: number) {
  const x = Math.sin(k * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
}

// Divergence bumps sit at fixed points on the paper, so they scroll past with it.
function bump(s: number) {
  const period = 3.4;
  const k = Math.floor(s / period);
  let v = 0;
  for (const j of [k - 1, k, k + 1]) {
    if (hash(j) < 0.45) continue;
    const c = j * period + period * 0.5;
    const amp = (hash(j + 99) > 0.5 ? 1 : -1) * (0.45 + hash(j + 7) * 0.7);
    const w = 0.08 + hash(j + 3) * 0.1;
    v += amp * Math.exp(-((s - c) ** 2) / w);
  }
  return v;
}

function ribbon(width: number, color: THREE.Color, opacity: number) {
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(N * 2 * 3);
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  const idx: number[] = [];
  for (let i = 0; i < N - 1; i++) {
    const a = i * 2;
    idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
  }
  geo.setIndex(idx);
  const mat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity, side: THREE.DoubleSide, depthWrite: false });
  const mesh = new THREE.Mesh(geo, mat);
  return { mesh, pos, width, mat };
}

export default function Hero3D({ className }: { className?: string }) {
  const host = useRef<HTMLDivElement>(null);
  const theme = useTheme();

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100);
    camera.position.set(0, 2.2, 9.5);
    camera.lookAt(0, 0, 0);

    const ua = cssHsl("--ua");
    const ub = cssHsl("--ub");
    const ember = cssHsl("--ember");
    const grid = cssHsl("--grid");

    const group = new THREE.Group();
    scene.add(group);

    // Chart paper.
    const gridHelper = new THREE.GridHelper(SPAN * 1.6, 56, grid, grid);
    (gridHelper.material as THREE.Material).transparent = true;
    (gridHelper.material as THREE.Material).opacity = theme === "dark" ? 0.14 : 0.22;
    gridHelper.position.y = -1.15;
    group.add(gridHelper);

    const glowA = ribbon(0.11, ua, 0.12);
    const lineA = ribbon(0.035, ua, 0.95);
    const glowB = ribbon(0.13, ub, 0.16);
    const lineB = ribbon(0.04, ub, 1);
    [glowA, lineA, glowB, lineB].forEach((r) => group.add(r.mesh));

    // Probe inputs travelling between the universes.
    const dotCount = 70;
    const dotGeo = new THREE.BufferGeometry();
    const dotPos = new Float32Array(dotCount * 3);
    const dotSeed = Array.from({ length: dotCount }, (_, i) => hash(i + 0.5));
    dotGeo.setAttribute("position", new THREE.BufferAttribute(dotPos, 3));
    const dots = new THREE.Points(
      dotGeo,
      new THREE.PointsMaterial({ color: ember, size: 0.05, transparent: true, opacity: 0.85, depthWrite: false }),
    );
    group.add(dots);

    // Divergence markers.
    const markerGeo = new THREE.RingGeometry(0.09, 0.12, 40);
    const markers = Array.from({ length: 6 }, () => {
      const m = new THREE.Mesh(markerGeo, new THREE.MeshBasicMaterial({ color: ub, transparent: true, opacity: 0, side: THREE.DoubleSide }));
      group.add(m);
      return m;
    });

    const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
    const onMove = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      pointer.tx = ((e.clientX - r.left) / r.width - 0.5) * 2;
      pointer.ty = ((e.clientY - r.top) / r.height - 0.5) * 2;
    };
    window.addEventListener("pointermove", onMove);

    const resize = () => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      renderer.setSize(w, h, false);
      renderer.domElement.style.width = "100%";
      renderer.domElement.style.height = "100%";
      camera.aspect = w / h;
      camera.fov = w < 640 ? 46 : 32;
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();

    const fill = (r: ReturnType<typeof ribbon>, t: number, z: number, withBump: boolean) => {
      for (let i = 0; i < N; i++) {
        const x = (i / (N - 1) - 0.5) * SPAN;
        const s = x + t;
        const y = base(s) + (withBump ? bump(s) : 0);
        const o = i * 6;
        r.pos[o] = x;
        r.pos[o + 1] = y + r.width;
        r.pos[o + 2] = z;
        r.pos[o + 3] = x;
        r.pos[o + 4] = y - r.width;
        r.pos[o + 5] = z;
      }
      r.mesh.geometry.attributes.position.needsUpdate = true;
    };

    let raf = 0;
    let visible = true;
    const io = new IntersectionObserver(([entry]) => (visible = entry.isIntersecting));
    io.observe(el);
    const clock = new THREE.Clock();

    const frame = () => {
      raf = requestAnimationFrame(frame);
      if (!visible) return;
      const t = reduced ? 2 : clock.getElapsedTime() * 0.55;
      fill(glowA, t, -0.35, false);
      fill(lineA, t, -0.35, false);
      fill(glowB, t, 0.35, true);
      fill(lineB, t, 0.35, true);

      for (let i = 0; i < dotCount; i++) {
        const p = (dotSeed[i] + t * 0.05 * (0.6 + dotSeed[i])) % 1;
        const x = (p - 0.5) * SPAN;
        const s = x + t;
        dotPos[i * 3] = x;
        dotPos[i * 3 + 1] = base(s) + (dotSeed[i] - 0.5) * 0.25 - 0.02;
        dotPos[i * 3 + 2] = (dotSeed[(i * 7) % dotCount] - 0.5) * 0.7;
      }
      dotGeo.attributes.position.needsUpdate = true;

      // Place markers on the visible divergence peaks.
      let m = 0;
      const period = 3.4;
      const startK = Math.floor((-SPAN / 2 + t) / period) - 1;
      for (let k = startK; k < startK + 8 && m < markers.length; k++) {
        if (hash(k) < 0.45) continue;
        const c = k * period + period * 0.5;
        const x = c - t;
        if (Math.abs(x) > SPAN / 2) continue;
        const mk = markers[m++];
        mk.position.set(x, base(c) + bump(c), 0.36);
        const edge = 1 - Math.min(1, Math.abs(x) / (SPAN / 2));
        (mk.material as THREE.MeshBasicMaterial).opacity = 0.9 * edge;
        mk.scale.setScalar(1 + 0.25 * Math.sin(clock.getElapsedTime() * 4 + k));
      }
      for (; m < markers.length; m++) (markers[m].material as THREE.MeshBasicMaterial).opacity = 0;

      pointer.x += (pointer.tx - pointer.x) * 0.05;
      pointer.y += (pointer.ty - pointer.y) * 0.05;
      group.rotation.y = pointer.x * 0.28 - 0.18;
      group.rotation.x = pointer.y * 0.1 + 0.05;
      camera.position.y = 2.2 - pointer.y * 0.4;
      camera.lookAt(0, 0, 0);
      renderer.render(scene, camera);
    };
    frame();

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onMove);
      ro.disconnect();
      io.disconnect();
      renderer.dispose();
      scene.traverse((o) => {
        const mesh = o as THREE.Mesh;
        mesh.geometry?.dispose?.();
        const mat = mesh.material as THREE.Material | undefined;
        mat?.dispose?.();
      });
      el.removeChild(renderer.domElement);
    };
  }, [theme]);

  return <div ref={host} className={className} aria-hidden />;
}

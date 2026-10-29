import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Grid, Sparkles } from "@react-three/drei";
import { Bloom, EffectComposer, Noise, Vignette } from "@react-three/postprocessing";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { moodOf, useArgus } from "../lib/store";
import type { Mood } from "../lib/types";
import { frame, gaze } from "../lib/layout";
import { VIDEO_MODE } from '../lib/keyboard';
import { useTheme } from '../lib/themes';

/* Argus Panoptes: a black-figure orb of one hundred eyes. */

const EYES = 100;
const R = 1.5;
const ER = 0.1; // eyeball radius

type Params = { glow: number; spin: number; ring: number; follow: number; bloom: number; saccade: number };
const MOODS: Record<Mood, Params> = {
  idle:       { glow: 0.8, spin: 0.05, ring: 0.12, follow: 0.55, bloom: 0.45, saccade: 0.0 },
  observe:    { glow: 1.3, spin: 0.09, ring: 0.45, follow: 0.4,  bloom: 0.65, saccade: 0.45 },
  deliberate: { glow: 2.1, spin: 0.13, ring: 1.0,  follow: 0.22, bloom: 0.9,  saccade: 0.12 },
  act:        { glow: 1.6, spin: 0.1,  ring: 0.65, follow: 0.3,  bloom: 0.75, saccade: 0.9 },
  gaze:       { glow: 2.8, spin: 0.012, ring: 0.2, follow: 1.0,  bloom: 1.15, saccade: 0.0 },
};

// Pointer tracked on window so panels layered over the canvas don't blind the eyes.
const pointer = { x: 0, y: 0 };
if (typeof window !== "undefined" && !VIDEO_MODE) {
  window.addEventListener("pointermove", (e) => {
    pointer.x = (e.clientX / window.innerWidth) * 2 - 1;
    pointer.y = -(e.clientY / window.innerHeight) * 2 + 1;
  });
}

function fibonacci(n: number, r: number) {
  const pts: THREE.Vector3[] = [];
  const phi = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y = 1 - ((i + 0.5) / n) * 2; // offset avoids exact poles
    const rad = Math.sqrt(1 - y * y);
    const th = phi * i;
    pts.push(new THREE.Vector3(Math.cos(th) * rad, y, Math.sin(th) * rad).multiplyScalar(r));
  }
  return pts;
}

/** Grungy terracotta glow -- the orange field behind black-figure pottery. */
function useHaloTexture(glow: string) {
  return useMemo(() => {
    const c = document.createElement("canvas");
    c.width = c.height = 1024;
    const g = c.getContext("2d")!;
    const n = parseInt(glow.slice(1), 16);
    const tint = (k: number, a: number) =>
      `rgba(${Math.round(((n >> 16) & 255) * k)},${Math.round(((n >> 8) & 255) * k)},${Math.round((n & 255) * k)},${a})`;
    const grad = g.createRadialGradient(512, 512, 0, 512, 512, 512);
    grad.addColorStop(0, tint(0.9, 0.62));
    grad.addColorStop(0.28, tint(0.74, 0.42));
    grad.addColorStop(0.55, tint(0.43, 0.16));
    grad.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = grad;
    g.fillRect(0, 0, 1024, 1024);
    // weathered blotches, like aged clay
    let seed = 7;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    g.globalCompositeOperation = "destination-out";
    for (let i = 0; i < 260; i++) {
      const x = rnd() * 1024, y = rnd() * 1024, r = 4 + rnd() * 40;
      g.fillStyle = `rgba(0,0,0,${0.05 + rnd() * 0.18})`;
      g.beginPath();
      g.ellipse(x, y, r, r * (0.4 + rnd()), rnd() * Math.PI, 0, Math.PI * 2);
      g.fill();
    }
    const t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    return t;
  }, [glow]);
}

function Orb({ mood, compact = false }: { mood: Mood; compact?: boolean }) {
  const orb = useRef<THREE.Group>(null!);
  const rings = useRef<THREE.Group[]>([]);
  const eyes = useRef<(THREE.Group | null)[]>([]);
  const points = useMemo(() => fibonacci(EYES, R * 0.985), []);

  const sockets = useMemo(() => {
    const m = new THREE.Matrix4();
    const zero = new THREE.Vector3();
    return points.map((p) => {
      const n = p.clone().normalize();
      const up = Math.abs(n.y) > 0.98 ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(0, 1, 0);
      m.lookAt(n, zero, up); // +Z = outward normal, almond kept horizontal
      return {
        pos: p,
        quat: new THREE.Quaternion().setFromRotationMatrix(m),
        normal: n,
        nextBlink: Math.random() * 7,
        blinkStart: -1,
        sacc: new THREE.Vector3(),
        nextSacc: Math.random() * 2,
        lid: 1,
      };
    });
  }, [points]);

  const mats = useMemo(
    () => {
      const initial = useTheme.getState().palette;
      return {
        body: new THREE.MeshStandardMaterial({ color: initial.void, roughness: 0.72, metalness: 0.3 }),
        sclera: new THREE.MeshStandardMaterial({
          color: initial.bone, emissive: new THREE.Color(initial.goldDim), emissiveIntensity: 0.25, roughness: 0.4,
        }),
        iris: new THREE.MeshStandardMaterial({
          color: initial.iris, emissive: new THREE.Color(initial.amber), emissiveIntensity: 0.8, roughness: 0.3,
        }),
        pupil: new THREE.MeshBasicMaterial({ color: initial.void }),
        rim: new THREE.MeshBasicMaterial({ color: new THREE.Color(initial.gold).multiplyScalar(1.15), toneMapped: false }),
        line: new THREE.MeshBasicMaterial({
          color: new THREE.Color(initial.gold), transparent: true, opacity: 0.18, toneMapped: false,
        }),
        ring: new THREE.MeshBasicMaterial({ color: new THREE.Color(initial.amber).multiplyScalar(1.4), toneMapped: false }),
        bead: new THREE.MeshBasicMaterial({ color: new THREE.Color(initial.glow).multiplyScalar(2.5), toneMapped: false }),
      };
    },
    []
  );

  // The colour theme repaints the eyes in place (no rebuild, no flicker).
  const pal = useTheme((t) => t.palette);
  useEffect(() => {
    mats.body.color.set(pal.void);
    mats.pupil.color.set(pal.void);
    mats.sclera.color.set(pal.bone);
    mats.sclera.emissive.set(pal.goldDim).multiplyScalar(0.6);
    mats.iris.color.set(pal.iris);
    mats.iris.emissive.set(pal.amber);
    mats.rim.color.set(pal.gold).multiplyScalar(1.15);
    mats.line.color.set(pal.gold);
    mats.ring.color.set(pal.amber).multiplyScalar(1.4);
    mats.bead.color.set(pal.glow).multiplyScalar(2.5);
  }, [pal, mats]);

  const geo = useMemo(
    () => ({
      body: new THREE.SphereGeometry(R, 96, 64),
      sclera: new THREE.SphereGeometry(ER, 28, 20),
      iris: new THREE.SphereGeometry(ER * 1.006, 32, 6, 0, Math.PI * 2, 0, 0.62),
      pupil: new THREE.SphereGeometry(ER * 1.012, 24, 4, 0, Math.PI * 2, 0, 0.27),
      rim: new THREE.TorusGeometry(ER * 1.18, 0.0055, 6, 48),
    }),
    []
  );

  const p = useRef<Params>({ ...MOODS.idle });
  const prevMood = useRef<Mood>("idle");
  const tmp = useMemo(
    () => ({
      world: new THREE.Vector3(),
      target: new THREE.Vector3(),
      dir: new THREE.Vector3(),
      n: new THREE.Vector3(),
      q: new THREE.Quaternion(),
      parentQ: new THREE.Quaternion(),
    }),
    []
  );

  useFrame((st, dt) => {
    dt = Math.min(dt, 0.05);
    const t = st.clock.elapsedTime;
    const goal = compact && mood === "idle" ? COMPACT_IDLE : MOODS[mood];
    const cur = p.current;
    const k = 1 - Math.exp(-dt * 2.2);
    (Object.keys(goal) as (keyof Params)[]).forEach((key) => (cur[key] += (goal[key] - cur[key]) * k));

    // One synchronised blink when Argus turns to speak -- then a stare.
    if (mood === "gaze" && prevMood.current !== "gaze") {
      sockets.forEach((s) => (s.blinkStart = t + Math.random() * 0.06));
    }
    prevMood.current = mood;

    const o = orb.current;
    o.rotation.y += dt * cur.spin;
    o.position.y = ORB_Y + Math.sin(t * 0.55) * 0.05;
    mats.iris.emissiveIntensity = cur.glow;

    rings.current.forEach((r, i) => {
      if (r) r.rotation.z += dt * cur.ring * (i === 1 ? -1.3 : i === 2 ? 0.8 : 1);
    });

    const watching = mood !== "gaze" && Date.now() < gaze.until && frame.r > 0;
    if (mood === "gaze") tmp.target.copy(st.camera.position);
    else if (watching) {
      // Look at the sight window Argus is focused on, relative to the orb on screen.
      const nx = ((gaze.x - frame.cx) / window.innerWidth) * 2;
      const ny = -((gaze.y - frame.cy) / window.innerHeight) * 2;
      tmp.target.set(nx * 10, ORB_Y + ny * 6, 3.5);
    } else tmp.target.set(pointer.x * 6, pointer.y * 3.5 + 0.9, 6);
    const follow = watching ? Math.max(cur.follow, 0.88) : cur.follow;
    o.getWorldQuaternion(tmp.parentQ);

    const ease = 1 - Math.exp(-dt * (mood === "gaze" ? 6 : 9));
    sockets.forEach((s, i) => {
      const g = eyes.current[i];
      if (!g) return;
      if (t > s.nextSacc) {
        s.sacc.set((Math.random() - 0.5) * 9, (Math.random() - 0.5) * 6, (Math.random() - 0.5) * 9);
        s.nextSacc = t + 0.25 + Math.random() * 1.4;
      }
      g.getWorldPosition(tmp.world);
      tmp.dir.copy(s.sacc).multiplyScalar(cur.saccade).add(tmp.target).sub(tmp.world).normalize();
      tmp.n.copy(s.normal).applyQuaternion(tmp.parentQ);
      tmp.dir.lerp(tmp.n, 1 - follow).normalize();

      tmp.q.copy(g.quaternion);
      g.lookAt(tmp.world.x + tmp.dir.x, tmp.world.y + tmp.dir.y, tmp.world.z + tmp.dir.z);
      g.quaternion.copy(tmp.q.slerp(g.quaternion, ease));

      // Blinks: random, except mid-stare.
      if (s.blinkStart < 0 && t > s.nextBlink && mood !== "gaze") s.blinkStart = t;
      if (s.blinkStart >= 0 && t >= s.blinkStart) {
        const ph = (t - s.blinkStart) / 0.17;
        s.lid = ph < 0.5 ? 1 - ph * 1.84 : 0.08 + (ph - 0.5) * 1.84;
        if (ph >= 1) {
          s.lid = 1;
          s.blinkStart = -1;
          s.nextBlink = t + 2.5 + Math.random() * 9;
        }
      }
      g.scale.set(1, Math.max(0.08, Math.min(1, s.lid)), 1);
    });
  });

  // engraved meridians and parallels -- the gold linework of the figure
  const lines = useMemo(() => {
    const out: { rot: [number, number, number]; r: number; y: number }[] = [];
    for (let i = 0; i < 6; i++) out.push({ rot: [0, (i * Math.PI) / 6, 0], r: R * 1.002, y: 0 });
    [-0.62, -0.25, 0.25, 0.62].forEach((f) =>
      out.push({ rot: [Math.PI / 2, 0, 0], r: R * Math.sqrt(1 - f * f) * 1.002, y: R * f })
    );
    return out;
  }, []);

  return (
    <group ref={orb} position={[0, ORB_Y, 0]}>
      <mesh geometry={geo.body} material={mats.body} />
      {lines.map((l, i) => (
        <mesh key={i} position={[0, l.y, 0]} rotation={l.rot} material={mats.line}>
          <torusGeometry args={[l.r, 0.0028, 4, 160]} />
        </mesh>
      ))}
      {sockets.map((s, i) => (
        <group key={i} position={s.pos} quaternion={s.quat}>
          <mesh geometry={geo.rim} material={mats.rim} scale={[1.38, 0.72, 1]} position={[0, 0, 0.035]} />
          <group ref={(el) => { eyes.current[i] = el; }}>
            <mesh geometry={geo.sclera} material={mats.sclera} />
            <mesh geometry={geo.iris} material={mats.iris} rotation={[Math.PI / 2, 0, 0]} />
            <mesh geometry={geo.pupil} material={mats.pupil} rotation={[Math.PI / 2, 0, 0]} />
          </group>
        </group>
      ))}
      {/* armillary rings with running beads */}
      {[
        { r: R * 1.42, rot: [Math.PI / 2, 0, 0] as [number, number, number] },
        { r: R * 1.56, rot: [Math.PI / 2 + 0.55, 0, 0.5] as [number, number, number] },
        { r: R * 1.7, rot: [Math.PI / 2 - 0.75, 0.35, -0.3] as [number, number, number] },
      ].map((ring, i) => (
        <group key={i} rotation={ring.rot}>
          <group ref={(el) => { if (el) rings.current[i] = el; }}>
            <mesh material={mats.ring}>
              <torusGeometry args={[ring.r, i === 0 ? 0.009 : 0.005, 8, 256]} />
            </mesh>
            {[0, 2.1, 4.2].map((a, j) => (
              <mesh key={j} position={[Math.cos(a + i) * ring.r, Math.sin(a + i) * ring.r, 0]} material={mats.bead}>
                <sphereGeometry args={[0.028, 12, 8]} />
              </mesh>
            ))}
          </group>
        </group>
      ))}
    </group>
  );
}

function Halo() {
  const tex = useHaloTexture(useTheme((t) => t.palette.amber));
  const ref = useRef<THREE.Mesh>(null!);
  const mood = useArgus((s) => moodOf(s));
  useFrame((st, dt) => {
    const m = ref.current.material as THREE.MeshBasicMaterial;
    const goal = mood === "gaze" ? 0.6 : mood === "deliberate" ? 0.48 : 0.3;
    m.opacity += (goal - m.opacity) * (1 - Math.exp(-dt * 2));
    ref.current.scale.setScalar(15 + Math.sin(st.clock.elapsedTime * 0.4) * 0.25);
  });
  return (
    <mesh ref={ref} position={[0, 1.0, -5]}>
      <planeGeometry args={[1, 1]} />
      <meshBasicMaterial map={tex} transparent opacity={0.3} depthWrite={false} toneMapped={false} />
    </mesh>
  );
}

const ORB_Y = 0.95;

// Floating orb at rest: eyes drift on their own, since there is no cursor in
// its tiny window to follow.
const COMPACT_IDLE: Params = { ...MOODS.idle, saccade: 0.35, follow: 0.45, glow: 1.25 };

/** Render at a fixed rate instead of every display frame: the floating orb sits
 *  over games and video all day and should cost almost nothing. */
function Ticker({ fps }: { fps: number }) {
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    const id = window.setInterval(() => invalidate(), 1000 / fps);
    return () => window.clearInterval(id);
  }, [fps, invalidate]);
  return null;
}

function CameraRig({ mood, compact = false }: { mood: Mood; compact?: boolean }) {
  const zoom = useRef(1);
  useFrame((st, dt) => {
    const cam = st.camera as THREE.PerspectiveCamera;
    const W = st.size.width;
    const H = st.size.height;
    const k = 1 - Math.exp(-dt * 1.6);

    // Lean in a little when Argus speaks.
    zoom.current += ((mood === "gaze" ? 1.1 : 1) - zoom.current) * (1 - Math.exp(-dt * 1.2));
    // The floating orb frames itself to its own small window.
    const baseR = compact ? Math.min(W, H) * 0.27 : frame.r || H * 0.3;
    const rpx = baseR * zoom.current;
    const tanH = Math.tan(THREE.MathUtils.degToRad(cam.fov / 2));
    const dist = R / ((rpx / (H / 2)) * tanH);

    const par = compact ? 0 : 1;
    const tx = pointer.x * 0.06 * dist * par;
    const ty = ORB_Y + 0.12 * dist + pointer.y * 0.03 * dist * par;
    cam.position.x += (tx - cam.position.x) * k;
    cam.position.y += (ty - cam.position.y) * k;
    cam.position.z += (dist - cam.position.z) * k;
    cam.lookAt(0, ORB_Y, 0);

    // Shift the projection so the orb lands in the layout's orb zone.
    const cx = compact ? W / 2 : frame.r ? frame.cx : W / 2;
    const cy = compact ? H / 2 : frame.r ? frame.cy : H * 0.35;
    cam.setViewOffset(W, H, W / 2 - cx, H / 2 - cy, W, H);
    cam.updateProjectionMatrix();
  });
  return null;
}

function BloomDriver({ mood }: { mood: Mood }) {
  // Animate bloom with the mood instead of snapping it.
  const ref = useRef<{ intensity: number } | null>(null);
  useFrame((_, dt) => {
    if (ref.current) {
      const goal = MOODS[mood].bloom;
      ref.current.intensity += (goal - ref.current.intensity) * (1 - Math.exp(-dt * 2));
    }
  });
  return (
    <EffectComposer multisampling={4}>
      <Bloom ref={ref as never} mipmapBlur intensity={0.45} luminanceThreshold={0.45} luminanceSmoothing={0.25} />
      <Noise opacity={0.018} />
      <Vignette offset={0.22} darkness={0.82} />
    </EffectComposer>
  );
}

function Scene({ compact = false }: { compact?: boolean }) {
  const mood = useArgus((s) => moodOf(s));
  const pal = useTheme((t) => t.palette);
  return (
    <>
      {!compact && <color attach="background" args={[pal.void]} />}
      <ambientLight intensity={0.22} color={pal.glow} />
      <directionalLight position={[2.5, 4, 6]} intensity={1.5} color={pal.bone} />
      <pointLight position={[0, 1.2, -3.2]} intensity={40} distance={12} color={pal.amber} />
      <pointLight position={[-4, -1, 2]} intensity={6} distance={10} color={pal.goldDim} />
      {!compact && <Halo />}
      <group>
        <Orb mood={mood} compact={compact} />
      </group>
      {!compact && <Grid
        position={[0, -1.45, 0]}
        args={[40, 40]}
        cellSize={0.5}
        cellThickness={0.6}
        cellColor={pal.grid}
        sectionSize={2.5}
        sectionThickness={1.15}
        sectionColor={pal.amber}
        fadeDistance={24}
        fadeStrength={1.7}
        infiniteGrid
      />}
      {!compact && <Sparkles count={90} scale={[12, 6, 8]} position={[0, 1, -1]} size={2.2} speed={0.25} color={pal.glow} opacity={0.55} />}
      <CameraRig mood={mood} compact={compact} />
      {compact ? <Ticker fps={30} /> : <BloomDriver mood={mood} />}
    </>
  );
}

export default function Panoptes({ compact = false }: { compact?: boolean }) {
  const voidColor = useTheme((t) => t.palette.void);
  useEffect(() => {
    if (!compact) document.body.style.background = voidColor;
  }, [compact, voidColor]);
  return (
    <div className={compact ? "panoptes-canvas compact" : "panoptes-canvas"} aria-hidden>
      <Canvas
        dpr={compact ? [1, 2] : [1, 1.6]}
        frameloop={compact ? "demand" : "always"}
        camera={{ position: [0, 0.75, 7.4], fov: 38 }}
        gl={compact
          ? { alpha: true, antialias: true, powerPreference: "low-power" }
          : { antialias: false, powerPreference: "high-performance" }}
      >
        <Scene compact={compact} />
      </Canvas>
    </div>
  );
}

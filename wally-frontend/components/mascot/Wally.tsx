"use client";

import { CSSProperties, useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { View } from "../Sidebar";
import { CLICK_LINES, FAINT_LINES, GREETINGS, PAGE_LINES, RAMPAGE_END, RAMPAGE_START, RESPAWN_LINES, pick } from "./lines";

/* ------------------------------------------------------------------ */
/* Sprite atlas: five vertical strips of 119×124 frames, side by side  */
/* ------------------------------------------------------------------ */

const ATLAS = "/wally/wally-atlas.png";
const ATLAS_W = 595;
const ATLAS_H = 2604;
const FW = 119;
const FH = 124;
const CX = 53; // character's horizontal centre inside a frame
const HEAD = 81; // top of the storm-head inside a frame (feet sit on the bottom row)

type AnimName = "idle" | "run" | "attack" | "damaged" | "death" | "respawn";

const ANIMS: Record<AnimName, { col: number; frames: number; ms: number; loop?: boolean; times?: number; reverse?: boolean }> = {
  idle: { col: 0, frames: 9, ms: 100, loop: true },
  run: { col: 1, frames: 10, ms: 60, loop: true },
  attack: { col: 2, frames: 21, ms: 45 },
  damaged: { col: 3, frames: 2, ms: 90, times: 4 },
  death: { col: 4, frames: 9, ms: 80 },
  respawn: { col: 4, frames: 9, ms: 60, reverse: true },
};

const animMs = (name: AnimName) => ANIMS[name].frames * ANIMS[name].ms * (ANIMS[name].times ?? 1);

const SPRING = "cubic-bezier(0.22, 1.45, 0.36, 1)";
const EASE_OUT = "cubic-bezier(0.16, 1, 0.3, 1)";
const EASE_IN = "cubic-bezier(0.55, 0, 1, 0.45)";
const RUN_SPEED = 1.4; // px per ms

/* ------------------------------------------------------------------ */
/* Placement                                                           */
/* ------------------------------------------------------------------ */

type Pose = { at: "peek" | "peekHover" } | { at: "ground" | "hidden"; cx?: number };
type Viewport = { w: number; h: number };

const scaleFor = (vp: Viewport) => (vp.w < 640 ? 2 : 3);
const cornerCx = (vp: Viewport) => (vp.w < 640 ? vp.w - 44 : vp.w - 64);

/** Box position (top-left, px) and rotation for a pose. Rotation pivots on the feet. */
function place(pose: Pose, vp: Viewport) {
  const s = scaleFor(vp);
  if (pose.at === "peek" || pose.at === "peekHover") {
    const visible = (pose.at === "peek" ? 27 : 38) * s;
    if (vp.w < 640) {
      // Phones: poke in sideways from the right edge, clear of the question box
      const feetX = vp.w - visible + (FH - HEAD) * s;
      const feetY = Math.round(vp.h * 0.58);
      return { x: feetX - CX * s, y: feetY - FH * s, rot: -90 };
    }
    return { x: vp.w - 64 - CX * s, y: vp.h - HEAD * s - visible, rot: 0 };
  }
  const x = (("cx" in pose ? pose.cx : undefined) ?? cornerCx(vp)) - CX * s;
  return pose.at === "ground" ? { x, y: vp.h - FH * s - 4, rot: 0 } : { x, y: vp.h - HEAD * s + 8, rot: 0 };
}

/* ------------------------------------------------------------------ */
/* Browser state as external stores (no setState-in-effect)            */
/* ------------------------------------------------------------------ */

const subscribeResize = (cb: () => void) => {
  window.addEventListener("resize", cb);
  return () => window.removeEventListener("resize", cb);
};
const viewportSnapshot = () => `${window.innerWidth}x${window.innerHeight}`;

const REDUCED = "(prefers-reduced-motion: reduce)";
const subscribeMotion = (cb: () => void) => {
  const mq = window.matchMedia(REDUCED);
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
};
const motionSnapshot = () => window.matchMedia(REDUCED).matches;

/* ------------------------------------------------------------------ */
/* Speech bubble                                                       */
/* ------------------------------------------------------------------ */

const BUBBLE_MAX = 236;
const CHAR_MS = 14;

function Bubble({ text, centerX, width, tailX, instant }: { text: string; centerX: number; width: number; tailX: number; instant: boolean }) {
  const [shown, setShown] = useState(instant ? text.length : 0);

  useEffect(() => {
    if (instant) return;
    const started = performance.now();
    const t = setInterval(() => {
      const n = Math.min(text.length, Math.floor((performance.now() - started) / CHAR_MS) + 1);
      setShown(n);
      if (n >= text.length) clearInterval(t);
    }, CHAR_MS);
    return () => clearInterval(t);
  }, [text, instant]);

  return (
    <div
      role="status"
      className="wally-bubble pointer-events-none absolute"
      style={{ left: centerX, width, transformOrigin: `${tailX}px 100%` }}
    >
      <p className="font-pixel text-[13px] leading-[1.4] font-medium text-ink">
        {text.slice(0, shown)}
        <span className="invisible">{text.slice(shown)}</span>
      </p>
      <svg className="absolute top-full" style={{ left: tailX - 10 }} width="18" height="12" viewBox="0 0 6 4" shapeRendering="crispEdges" aria-hidden>
        <path fill="#fff" d="M1 0h3v1H1zM2 1h2v1H2zM3 2h1v1H3z" />
        <path fill="#1a1a1a" d="M0 0h1v1H0zM4 0h1v3H4zM1 1h1v1H1zM2 2h1v1H2zM3 3h1v1H3z" />
      </svg>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Director: runs one cancellable sequence at a time                   */
/* ------------------------------------------------------------------ */

const CANCEL = Symbol("cancel");
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const nextFrames = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
const rand = (a: number, b: number) => a + Math.random() * (b - a);

interface Director {
  vp: () => Viewport;
  wait: (ms: number) => Promise<void>;
  move: (pose: Pose, ms?: number, ease?: string) => Promise<void>;
  play: (name: AnimName) => number;
  perform: (name: AnimName) => Promise<number>;
  say: (text: string) => void;
  hush: () => void;
  face: (left: boolean) => void;
  here: () => number;
}

export function Wally({ view }: { view: View }) {
  const vpKey = useSyncExternalStore(subscribeResize, viewportSnapshot, () => "");
  const reduced = useSyncExternalStore(subscribeMotion, motionSnapshot, () => true);

  const [pose, setPose] = useState<Pose>({ at: "hidden" });
  const [transition, setTransition] = useState("none");
  const [anim, setAnim] = useState<{ name: AnimName; n: number }>({ name: "idle", n: 0 });
  const [flip, setFlip] = useState(false);
  const [bubble, setBubble] = useState<{ text: string; n: number } | null>(null);

  const vpRef = useRef<Viewport>({ w: 1280, h: 800 });
  const reducedRef = useRef(reduced);
  const runId = useRef(0);
  const busy = useRef(false);
  const posRef = useRef<number | undefined>(undefined); // current cx; undefined = corner
  const clicks = useRef<number[]>([]);
  const prevView = useRef(view);

  const vp: Viewport | null = vpKey ? { w: +vpKey.split("x")[0], h: +vpKey.split("x")[1] } : null;

  useEffect(() => {
    if (vp) vpRef.current = vp;
    reducedRef.current = reduced;
  });

  const start = useCallback((script: (d: Director) => Promise<void>) => {
    const id = ++runId.current;
    const guard = () => {
      if (runId.current !== id) throw CANCEL;
    };
    const d: Director = {
      vp: () => vpRef.current,
      wait: async (ms) => {
        await sleep(ms);
        guard();
      },
      move: async (p, ms = 0, ease = SPRING) => {
        const dur = reducedRef.current ? 0 : Math.round(ms);
        setTransition(dur ? `transform ${dur}ms ${ease}` : "none");
        setPose(p);
        posRef.current = "cx" in p ? p.cx : undefined;
        if (dur) await d.wait(dur);
        else {
          await nextFrames();
          guard();
        }
      },
      play: (name) => {
        setAnim((a) => ({ name, n: a.n + 1 }));
        return animMs(name);
      },
      perform: async (name) => {
        const ms = d.play(name);
        if (ANIMS[name].loop) return 0;
        await d.wait(ms);
        d.play("idle");
        return ms;
      },
      say: (text) => setBubble((b) => ({ text, n: (b?.n ?? 0) + 1 })),
      hush: () => setBubble(null),
      face: setFlip,
      here: () => posRef.current ?? cornerCx(vpRef.current),
    };
    busy.current = true;
    script(d)
      .catch((e) => {
        if (e !== CANCEL) throw e;
      })
      .finally(() => {
        if (runId.current === id) busy.current = false;
      });
  }, []);

  /* ---------------- sequences ---------------- */

  const settle = async (d: Director) => {
    d.hush();
    d.face(false);
    d.play("idle");
    await d.move({ at: "peek" }, 340, EASE_OUT);
  };

  const runTo = async (d: Director, from: number, to: number, anim: AnimName = "run") => {
    d.face(to < from);
    d.play(anim);
    await d.move({ at: "ground", cx: to }, Math.max(180, Math.abs(to - from) / RUN_SPEED), "linear");
  };

  const greet = useCallback(
    () =>
      start(async (d) => {
        d.play("idle");
        await d.move({ at: "hidden" });
        await d.wait(900);
        await d.move({ at: "ground" }, 420, SPRING);
        d.say(pick(GREETINGS));
        await d.wait(2800);
        await settle(d);
      }),
    [start],
  );

  const reactToClick = () =>
    start(async (d) => {
      const cx = d.here();
      await d.move({ at: "ground", cx }, 260, SPRING);
      d.say(pick(CLICK_LINES));
      const t0 = performance.now();
      await d.perform(pick(["attack", "attack", "damaged", "idle"] as const));
      await d.wait(Math.max(0, 2300 - (performance.now() - t0)));
      await settle(d);
    });

  const faint = () =>
    start(async (d) => {
      await d.move({ at: "ground", cx: d.here() }, 200, SPRING);
      d.say(pick(FAINT_LINES));
      await d.wait(d.play("damaged"));
      await d.wait(d.play("death") + 250);
      d.hush();
      d.play("respawn");
      await d.move({ at: "ground" });
      await d.wait(animMs("respawn"));
      d.play("idle");
      d.say(pick(RESPAWN_LINES));
      await d.wait(2000);
      await settle(d);
    });

  const rampage = useCallback(
    () =>
      start(async (d) => {
        const vp = d.vp();
        let cx = d.here();
        d.hush();
        await d.move({ at: "ground", cx }, 240, SPRING);
        d.say(pick(RAMPAGE_START));
        await d.perform("attack");
        d.hush();
        const legs = 3 + Math.round(Math.random());
        for (let i = 0; i < legs; i++) {
          let target = rand(vp.w * 0.12, vp.w * 0.88);
          if (Math.abs(target - cx) < 180) target = cx > vp.w / 2 ? cx - rand(220, 420) : cx + rand(220, 420);
          target = Math.min(vp.w - 50, Math.max(50, target));
          if (i % 2 === 0) {
            // sprint, then fire on arrival
            await runTo(d, cx, target);
            cx = target;
            await d.perform("attack");
          } else {
            // dash while the lightning fires
            d.face(target < cx);
            d.play("attack");
            await d.move({ at: "ground", cx: target }, animMs("attack"), "cubic-bezier(0.5, 0, 0.2, 1)");
            cx = target;
          }
        }
        d.face(false);
        d.play("idle");
        d.say(pick(RAMPAGE_END));
        await d.wait(1500);
        d.hush();
        await runTo(d, cx, cornerCx(vp));
        await settle(d);
      }),
    [start],
  );

  const cameo = useCallback(
    (v: View) =>
      start(async (d) => {
        const vp = d.vp();
        d.hush();
        await d.move({ at: "hidden", cx: d.here() }, 140, EASE_IN);
        const cx = rand(vp.w * 0.2, vp.w * 0.8);
        d.face(Math.random() < 0.5);
        d.play("idle");
        await d.move({ at: "hidden", cx });
        await d.move({ at: "ground", cx }, 320, SPRING);
        d.say(pick(PAGE_LINES[v]));
        const t0 = performance.now();
        await d.perform(pick(["attack", "damaged", "idle"] as const));
        await d.wait(Math.max(0, 2400 - (performance.now() - t0)));
        d.hush();
        if (Math.random() < 0.5) {
          // sprint home
          await runTo(d, cx, cornerCx(vp));
          await settle(d);
        } else {
          // beam out, reappear in the corner
          await d.wait(d.play("death"));
          d.play("idle");
          d.face(false);
          await d.move({ at: "hidden" });
          await d.move({ at: "peek" }, 300, SPRING);
        }
      }),
    [start],
  );

  /* ---------------- triggers ---------------- */

  // Greeting on first load
  useEffect(() => {
    if (!vpKey) return;
    if (reducedRef.current) {
      start(async (d) => d.move({ at: "peek" }));
      return;
    }
    greet();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Boolean(vpKey)]);

  // Cameo on page change
  useEffect(() => {
    if (prevView.current === view) return;
    prevView.current = view;
    if (!reducedRef.current) cameo(view);
  }, [view, cameo]);

  // Easter egg: Shift + W unleashes a rampage on demand
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement;
      if (e.shiftKey && e.key.toLowerCase() === "w" && !typing && !reducedRef.current) rampage();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rampage]);

  // Occasional rampage while idle
  useEffect(() => {
    let t: ReturnType<typeof setTimeout>;
    const schedule = () => {
      t = setTimeout(() => {
        const typing = document.activeElement instanceof HTMLTextAreaElement || document.activeElement instanceof HTMLInputElement;
        if (!busy.current && !document.hidden && !typing && !reducedRef.current) rampage();
        schedule();
      }, rand(45000, 90000));
    };
    schedule();
    return () => clearTimeout(t);
  }, [rampage]);

  const onClick = () => {
    const now = performance.now();
    clicks.current = [...clicks.current.filter((c) => now - c < 1400), now];
    if (reducedRef.current) {
      start(async (d) => {
        await d.move({ at: "ground" });
        d.say(pick(CLICK_LINES));
        await d.wait(2600);
        d.hush();
        await d.move({ at: "peek" });
      });
      return;
    }
    if (clicks.current.length >= 4) {
      clicks.current = [];
      faint();
    } else if (Math.random() < 0.18) rampage();
    else reactToClick();
  };

  const onHover = (enter: boolean) => {
    if (busy.current || reducedRef.current) return;
    if (enter ? pose.at !== "peek" : pose.at !== "peekHover") return;
    setTransition(`transform 180ms ${EASE_OUT}`);
    setPose({ at: enter ? "peekHover" : "peek" });
  };

  if (!vp) return null;

  /* ---------------- render ---------------- */

  const s = scaleFor(vp);
  const { x, y, rot } = place(pose, vp);
  const a = ANIMS[anim.name];
  const spriteStyle = {
    width: ATLAS_W * s,
    height: ATLAS_H * s,
    "--wx": `${-a.col * FW * s}px`,
    "--wy": `${-(a.frames - 1) * FH * s}px`,
    animation: `${anim.n % 2 ? "wally-frames-a" : "wally-frames-b"} ${a.frames * a.ms}ms steps(${a.frames}, jump-none) ${
      a.loop ? "infinite" : (a.times ?? 1)
    } ${a.reverse ? "reverse" : "normal"} both`,
  } as CSSProperties;

  // Bubble: centred over the head, kept inside the viewport
  let bubbleEl = null;
  if (bubble && rot === 0) {
    const headX = x + CX * s;
    const est = Math.min(BUBBLE_MAX, bubble.text.length * 7.4 + 26);
    const center = Math.min(vp.w - est / 2 - 12, Math.max(est / 2 + 12, headX));
    const tailX = Math.min(est - 14, Math.max(14, headX - (center - est / 2)));
    bubbleEl = (
      <div className="absolute" style={{ left: 0, bottom: (FH - HEAD) * s + 30 }}>
        <Bubble key={bubble.n} text={bubble.text} centerX={center - x - est / 2} width={est} tailX={tailX} instant={reduced} />
      </div>
    );
  }

  return (
    <div className="pointer-events-none fixed inset-0 z-30 overflow-hidden">
      <div
        className="absolute top-0 left-0 will-change-transform"
        style={{
          width: FW * s,
          height: FH * s,
          transform: `translate3d(${x}px, ${y}px, 0) rotate(${rot}deg)`,
          transformOrigin: `${CX * s}px ${FH * s}px`,
          transition,
        }}
      >
        <div
          className="h-full w-full overflow-hidden"
          style={{
            transform: flip ? "scaleX(-1)" : undefined,
            transformOrigin: `${CX * s}px 50%`,
            // one-art-pixel outline so the pale storm-head reads on white
            filter: `drop-shadow(${s}px 0 0 #1a1a1a) drop-shadow(-${s}px 0 0 #1a1a1a) drop-shadow(0 ${s}px 0 #1a1a1a) drop-shadow(0 -${s}px 0 #1a1a1a)`,
          }}
          aria-hidden
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- pixel sprite atlas, stepped with CSS */}
          <img src={ATLAS} alt="" draggable={false} className="wally-sprite" style={spriteStyle} />
        </div>
        <button
          type="button"
          onClick={onClick}
          onPointerEnter={() => onHover(true)}
          onPointerLeave={() => onHover(false)}
          aria-label="Wally, the mascot. Click for a surprise."
          className="pointer-events-auto absolute cursor-pointer rounded-full outline-offset-4"
          style={{ left: (CX - 15) * s, top: (HEAD - 4) * s, width: 30 * s, height: (FH - HEAD + 4) * s }}
        />
        {bubbleEl}
      </div>
    </div>
  );
}

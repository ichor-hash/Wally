import type { View } from "../Sidebar";

/** Wally's lines. Short enough to read in two seconds. */

export const GREETINGS = [
  "Hi, I'm Wally. I read the fine print so you don't have to.",
  "Wally here. Fully charged, mildly overcast.",
  "Hello! I run on documents and a little static.",
];

export const PAGE_LINES: Record<View, string[]> = {
  ask: [
    "Ask me anything. I cite my sources like a nervous intern.",
    "Citations or it didn't happen.",
    "Ask away. I only make things up in my free time.",
    "Questions in, footnotes out.",
  ],
  library: [
    "Feed me PDFs. Nom.",
    "Every file here, I've read. Twice. Personally.",
    "Drop it like it's a 10-K.",
    "Chunk, embed, store. My three love languages.",
  ],
  performance: [
    "Embeddings in 20 ms. I'm basically weather.",
    "If it's slow, blame the language model. Not me. Never me.",
    "Look at those tiny bars. Adorable.",
    "Speed check: still faster than reading the 10-K.",
  ],
  gaps: [
    "Things I don't know yet. A short list. Ish.",
    "Every gap here is a document someone forgot to write.",
    "I'd rather say 'no idea' than invent one.",
    "My to-do list, written by your questions.",
  ],
  settings: [
    "Careful. That toggle bites.",
    "Rerank on means big-brain mode.",
    "Turning knobs is how wizards start.",
    "More sources, more tokens, more me.",
  ],
};

export const CLICK_LINES = [
  "Hey! That tickles.",
  "Bzzt. You've been zapped.",
  "I'm not a button. Okay, I'm a little button.",
  "Static shock incoming. Brace.",
  "You clicked me. Bold.",
  "Need a fact checked? I know a guy. It's me.",
  "Professional cloud. Amateur comedian.",
  "Careful, I'm 90% lightning.",
  "Boop received. Boop returned.",
  "I've read every chunk in here. Ask me something.",
];

export const FAINT_LINES = ["Too... many... clicks.", "Okay, okay. I'm down.", "Tell my embeddings I loved them."];

export const RESPAWN_LINES = ["I'm back. Did you miss me?", "Respawned. Fully indexed.", "Rebooted. No hard feelings."];

export const RAMPAGE_START = [
  "Hallucination spotted. Engaging!",
  "Unsourced claim detected. Hold still!",
  "Stale document on the loose!",
  "Someone said 'trust me bro'. Get 'em!",
];

export const RAMPAGE_END = ["Got it. Facts restored.", "Threat neutralised. Citations intact.", "And stay grounded!"];

export const pick = <T,>(list: readonly T[]) => list[Math.floor(Math.random() * list.length)];

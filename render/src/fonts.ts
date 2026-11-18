import {loadFont as loadArchivo} from '@remotion/google-fonts/Archivo';
import {loadFont as loadMono} from '@remotion/google-fonts/JetBrainsMono';
import {loadFont as loadAnton} from '@remotion/google-fonts/Anton';
import {loadFont as loadEmoji} from '@remotion/google-fonts/NotoColorEmoji';

export const DISPLAY = loadArchivo('normal', {weights: ['700', '800', '900'], subsets: ['latin']}).fontFamily;
export const MONO = loadMono('normal', {weights: ['400', '700'], subsets: ['latin']}).fontFamily;
export const MEME = loadAnton('normal', {weights: ['400'], subsets: ['latin']}).fontFamily;
export const EMOJI = loadEmoji('normal', {weights: ['400'], subsets: ['emoji']}).fontFamily;

/** Brand colors with fallbacks so older shots.json files (no accent2/highlight/fire) still render. */
export const palette = (c: Record<string, string>) => ({
  ...c,
  accent2: c.accent2 ?? '#FF2D87',
  highlight: c.highlight ?? '#E8FF3A',
  fire: c.fire ?? '#FF8A00',
}) as {bg: string; surface: string; text: string; muted: string; accent: string; accent2: string; highlight: string; warning: string; fire: string};

/** Split "*word*" markup into [{text, accent}] tokens. */
export const parseAccent = (s: string): {text: string; accent: boolean}[] => {
  // Supports spans across words: "*16 years* unpatched" accents both "16" and "years".
  const out: {text: string; accent: boolean}[] = [];
  let inSpan = false;
  for (const raw of s.split(/\s+/).filter(Boolean)) {
    const opens = raw.startsWith('*');
    const closes = /\*[.,!?:;]*$/.test(raw) && (raw.length > 1 || !opens);
    const accent = inSpan || opens;
    out.push({text: raw.replace(/\*/g, ''), accent});
    if (opens && !closes) inSpan = true;
    else if (closes) inSpan = false;
  }
  return out;
};

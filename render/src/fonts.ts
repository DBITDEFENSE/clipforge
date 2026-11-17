import {loadFont as loadArchivo} from '@remotion/google-fonts/Archivo';
import {loadFont as loadMono} from '@remotion/google-fonts/JetBrainsMono';

export const DISPLAY = loadArchivo('normal', {weights: ['700', '800', '900'], subsets: ['latin']}).fontFamily;
export const MONO = loadMono('normal', {weights: ['400', '700'], subsets: ['latin']}).fontFamily;

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

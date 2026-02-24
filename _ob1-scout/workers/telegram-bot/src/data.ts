import { Env, RadarData, Signal } from './types';

let cache: { data: RadarData | null; ts: number } = { data: null, ts: 0 };
const CACHE_TTL = 5 * 60 * 1000; // 5 min

export async function fetchData(env: Env): Promise<RadarData | null> {
  if (cache.data && Date.now() - cache.ts < CACHE_TTL) return cache.data;
  try {
    const r = await fetch(env.DATA_URL);
    if (!r.ok) return null;
    cache.data = await r.json() as RadarData;
    cache.ts = Date.now();
    return cache.data;
  } catch {
    return null;
  }
}

export function topSignals(items: Signal[], n = 5): Signal[] {
  return [...items].sort((a, b) => b.score - a.score).slice(0, n);
}

export function filterByRegion(items: Signal[], region: string): Signal[] {
  return items.filter(it => it.why.includes(region));
}

export function filterByType(items: Signal[], type: string): Signal[] {
  return items.filter(it => it.anomaly_type === type);
}

export function searchSignals(items: Signal[], q: string): Signal[] {
  const lq = q.toLowerCase();
  return items.filter(it => it.label.toLowerCase().includes(lq) || it.why.some(w => w.includes(lq)));
}

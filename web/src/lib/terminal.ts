import type { ActivityEvent } from './types';

export interface TerminalRow {
  id: number;
  text: string;
  tone?: NonNullable<ActivityEvent['lines']>[number]['tone'];
  arrivedAt: number;
}
let nextId = 0;

/** Sensor events are overlapping windows, not append-only batches. */
export function terminalRows(previous: TerminalRow[], lines: ActivityEvent['lines'], now: number): TerminalRow[] {
  const incoming = lines ?? [];
  let overlap = Math.min(previous.length, incoming.length);
  while (overlap > 0) {
    if (incoming.slice(0, overlap).every((line, i) => {
      const old = previous[previous.length - overlap + i];
      return old.text === line.text && old.tone === line.tone;
    })) break;
    overlap--;
  }
  return [...previous.slice(previous.length - overlap), ...incoming.slice(overlap).map(line => ({
    ...line, id: ++nextId, arrivedAt: now,
  }))];
}

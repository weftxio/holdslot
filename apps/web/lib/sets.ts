// Return a NEW Set with `key` toggled — added when absent, removed when present. The immutable
// `setState(prev => …)` idiom the list-page multi-selects / expand-collapse groups and the campaign
// log rows all repeat (S7). Kept pure so it drops straight into a state updater.
export function toggleInSet<T>(prev: Set<T>, key: T): Set<T> {
  const next = new Set(prev);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  return next;
}

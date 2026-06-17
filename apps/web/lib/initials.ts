// Two-letter initials from a name/label: first letters of the first two words.
// Strips punctuation so "Quill & Vane" → "QV" and "D'Angelo Rivera" → "DR".
export function nameInitials(name: string): string {
  return name
    .replace(/[^a-zA-Z ]/g, "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");
}

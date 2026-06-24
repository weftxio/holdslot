// CSV handling for the exclusion lists (and, later, the Phase C prospect import).
// Each record is three columns in a fixed order: company domain, company name, website —
// the same contract the textareas show inline. Pure + dependency-free so it is unit-testable
// and so the backend (Phase C / C2) can mirror the exact validation server-side.

export type ExclRow = { domain: string; name: string; website: string };
export type RowError = { line: number; raw: string; reasons: string[] };
type ExclParseResult = {
  valid: ExclRow[];
  errors: RowError[];
  headerSkipped: boolean;
  total: number; // data rows examined (excludes the header row)
};

// --- low-level RFC-4180-ish parser ------------------------------------------
// Handles quoted fields, commas/newlines inside quotes, escaped quotes (""),
// CRLF or LF line endings, and a leading UTF-8 BOM. Returns a grid of strings.
// Fully-empty rows are dropped.
function parseCsv(input: string): string[][] {
  let text = input;
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1); // strip BOM

  const rows: string[][] = [];
  let field = "";
  let row: string[] = [];
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field += c;
      }
    } else if (c === '"') {
      inQuotes = true;
    } else if (c === ",") {
      row.push(field);
      field = "";
    } else if (c === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (c !== "\r") {
      field += c;
    }
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows.filter((r) => r.some((cell) => cell.trim() !== ""));
}

// --- normalizers ------------------------------------------------------------
function isDomain(d: string): boolean {
  return /^(?=.{1,253}$)([a-z0-9](-?[a-z0-9])*\.)+[a-z]{2,}$/i.test(d);
}

function normalizeDomain(raw: string): string | null {
  let d = (raw || "").trim().toLowerCase();
  if (!d) return null;
  d = d.replace(/^https?:\/\//, "").replace(/^www\./, "");
  d = d.split("/")[0].split("?")[0].split("#")[0]; // strip any path/query/hash
  d = d.replace(/\.$/, "");
  return isDomain(d) ? d : null;
}

function normalizeUrl(raw: string): string | null {
  const v = (raw || "").trim();
  if (!v) return null;
  const withScheme = /^https?:\/\//i.test(v) ? v : "https://" + v;
  try {
    const u = new URL(withScheme);
    if (!isDomain(u.hostname.replace(/^www\./, ""))) return null;
    return u.toString().replace(/\/$/, "");
  } catch {
    return null;
  }
}

// --- header detection -------------------------------------------------------
const HEADER_SYNONYMS: Record<"domain" | "name" | "website", string[]> = {
  domain: ["domain", "company domain", "website domain", "root domain"],
  name: ["name", "company", "company name", "account", "account name", "organization"],
  website: ["website", "url", "site", "web", "homepage"],
};

type ColKey = "domain" | "name" | "website";

function detectHeader(first: string[]): { isHeader: boolean; order: (ColKey | null)[] } {
  const order = first.map((cell) => {
    const c = cell.trim().toLowerCase();
    for (const key of ["domain", "name", "website"] as ColKey[]) {
      if (HEADER_SYNONYMS[key].includes(c)) return key;
    }
    return null;
  });
  // Two or more recognised column names → treat row 1 as a header.
  return { isHeader: order.filter(Boolean).length >= 2, order };
}

// True when a row parses as a valid record under the positional [domain, name, website]
// contract — used to keep a real first data row from being mistaken for a header.
function isPositionalDataRow(cells: string[]): boolean {
  const name = (cells[1] ?? "").trim();
  const website = normalizeUrl(cells[2] ?? "");
  const domain = normalizeDomain(cells[0] ?? "") || (website && normalizeDomain(website));
  return !!(domain && name && website);
}

// --- the exclusion-list parser ---------------------------------------------
export function parseExclusionCsv(text: string): ExclParseResult {
  const grid = parseCsv(text);
  const valid: ExclRow[] = [];
  const errors: RowError[] = [];
  if (grid.length === 0) return { valid, errors, headerSkipped: false, total: 0 };

  // A genuine first data row can coincidentally match ≥2 header synonyms (e.g. a company
  // literally named "Account" with website "homepage"). If row 1 parses as a valid record
  // positionally, it's data — never silently discard it as a header.
  const detected = detectHeader(grid[0]);
  const { order } = detected;
  const isHeader = detected.isHeader && !isPositionalDataRow(grid[0]);
  const POSITIONAL: Record<ColKey, number> = { domain: 0, name: 1, website: 2 };
  const colOf = (key: ColKey): number => {
    if (isHeader) {
      const idx = order.indexOf(key);
      if (idx >= 0) return idx;
    }
    return POSITIONAL[key];
  };

  const dataRows = isHeader ? grid.slice(1) : grid;
  const seen = new Set<string>();

  dataRows.forEach((cells, i) => {
    const line = isHeader ? i + 2 : i + 1; // 1-based line number in the file
    const raw = cells.join(", ").trim();
    const reasons: string[] = [];

    const name = (cells[colOf("name")] ?? "").trim();
    const website = normalizeUrl(cells[colOf("website")] ?? "");
    let domain = normalizeDomain(cells[colOf("domain")] ?? "");
    // Leniency: derive the domain from the website when the domain cell is blank/bad.
    if (!domain && website) domain = normalizeDomain(website);

    if (!domain) reasons.push("invalid or missing company domain");
    if (!name) reasons.push("missing company name");
    if (!website) reasons.push("invalid or missing website");
    if (reasons.length) {
      errors.push({ line, raw, reasons });
      return;
    }
    if (seen.has(domain!)) {
      errors.push({ line, raw, reasons: ["duplicate domain within the file"] });
      return;
    }
    seen.add(domain!);
    valid.push({ domain: domain!, name, website: website! });
  });

  return { valid, errors, headerSkipped: isHeader, total: dataRows.length };
}

// --- text <-> rows, for merge/dedupe against the textarea -------------------
// Quote any cell containing a comma/quote/newline so the textarea stays valid CSV that
// re-parses to the same three columns (company names often contain commas).
function csvCell(s: string): string {
  return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}
function rowsToText(rows: ExclRow[]): string {
  return rows
    .map((r) => `${csvCell(r.domain)}, ${csvCell(r.name)}, ${csvCell(r.website)}`)
    .join("\n");
}

// Every domain mentioned in free-form field text, however it was entered — full 3-column
// rows, or legacy one-domain-per-line / comma lists. Used to dedupe a merge against content
// the strict parser would reject (so re-importing a company already typed in won't double it).
function domainsInText(text: string): Set<string> {
  const out = new Set<string>();
  for (const line of (text || "").split(/\r?\n/)) {
    for (const cell of line.split(",")) {
      const c = cell.trim();
      if (!c) continue;
      const d = normalizeDomain(c) || (normalizeUrl(c) ? normalizeDomain(normalizeUrl(c)!) : null);
      if (d) out.add(d);
    }
  }
  return out;
}

// Merge new rows into whatever is already in the field, deduping by domain.
// Existing text is preserved verbatim (even manually-typed lines); only non-duplicate
// new rows are appended.
export function mergeExclusionText(
  existing: string,
  incoming: ExclRow[]
): { text: string; added: number; duplicates: number } {
  const existingTrimmed = (existing || "").trim();
  const seen = domainsInText(existingTrimmed);

  const toAppend: ExclRow[] = [];
  let duplicates = 0;
  for (const r of incoming) {
    if (seen.has(r.domain)) {
      duplicates++;
      continue;
    }
    seen.add(r.domain);
    toAppend.push(r);
  }

  const appendText = rowsToText(toAppend);
  const text = existingTrimmed
    ? appendText
      ? existingTrimmed + "\n" + appendText
      : existingTrimmed
    : appendText;
  return { text, added: toAppend.length, duplicates };
}

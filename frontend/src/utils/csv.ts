export interface CsvColumn<T> {
  header: string;
  value: (row: T) => string | number | null | undefined;
}

function escapeCell(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "";
  const text = String(value);
  if (/[",\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

/** Build CSV text with UTF-8 BOM prefix (for Excel). */
export function serializeCsv<T>(
  columns: CsvColumn<T>[],
  rows: T[]
): string {
  const head = columns.map((c) => escapeCell(c.header)).join(",");
  const body = rows
    .map((row) => columns.map((c) => escapeCell(c.value(row))).join(","))
    .join("\n");
  return `\uFEFF${head}\n${body}`;
}

/**
 * Serialize rows to a CSV string and trigger a client-side download.
 * Prepends a UTF-8 BOM so Excel renders Chinese headers correctly.
 */
export function exportCsv<T>(
  filename: string,
  columns: CsvColumn<T>[],
  rows: T[]
): void {
  const csv = serializeCsv(columns, rows);

  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

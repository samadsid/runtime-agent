const datePattern = /^\d{4}-\d{2}-\d{2}$/;

export function buildDateRange(from: string, to: string): {
  createdFrom?: string; createdTo?: string; error?: string;
} {
  if ((from && !datePattern.test(from)) || (to && !datePattern.test(to))) return { error: "Use YYYY-MM-DD dates." };
  const start = from ? new Date(`${from}T00:00:00.000Z`) : null;
  const end = to ? new Date(`${to}T23:59:59.999Z`) : null;
  if ((start && Number.isNaN(start.valueOf())) || (end && Number.isNaN(end.valueOf()))) return { error: "Enter valid calendar dates." };
  if (start && end && (start > end || end.valueOf() - start.valueOf() > 31 * 86_400_000)) return { error: "Date range must be ordered and no longer than 31 days." };
  return { createdFrom: start?.toISOString(), createdTo: end?.toISOString() };
}

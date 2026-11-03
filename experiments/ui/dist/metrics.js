// Pure calculations shared by maps and research charts.
export function treemap(items, x, y, w, h) {
    if (items.length === 1)
        return [{ ...items[0], x, y, w, h }];
    const wide = w >= h, sorted = [...items].sort((p, q) => wide ? p.col - q.col || p.row - q.row : p.row - q.row || p.col - q.col);
    const total = sorted.reduce((n, item) => n + item.count, 0);
    let left = sorted[0].count, cut = 1;
    while (cut < sorted.length - 1 &&
        Math.abs(total - 2 * (left + sorted[cut].count)) < Math.abs(total - 2 * left)) {
        left += sorted[cut].count;
        cut++;
    }
    const share = left / total, first = sorted.slice(0, cut), second = sorted.slice(cut);
    return wide
        ? [
            ...treemap(first, x, y, w * share, h),
            ...treemap(second, x + w * share, y, w * (1 - share), h),
        ]
        : [
            ...treemap(first, x, y, w, h * share),
            ...treemap(second, x, y + h * share, w, h * (1 - share)),
        ];
}
export function metricValues(frame, metric) {
    const property = new Map(), homes = new Map();
    for (const h of frame.homes) {
        property.set(h.owner, (property.get(h.owner) || 0) + Number(h.value));
        homes.set(h.owner, (homes.get(h.owner) || 0) + 1);
    }
    return frame.people.map((p) => ({
        id: p.id,
        value: metric === 'property'
            ? property.get(p.id) || 0
            : metric === 'net'
                ? Number(p.cash) + (property.get(p.id) || 0)
                : metric === 'homes'
                    ? homes.get(p.id) || 0
                    : Number(p[metric]),
    }));
}
export function distribution(values) {
    const sorted = values.map((p) => p.value).sort((a, b) => a - b), total = sorted.reduce((a, b) => a + b, 0), n = sorted.length;
    if (!n || total <= 0 || sorted[0] < 0)
        return { total, gini: null, curve: null };
    let sum = 0;
    const curve = [0];
    for (const value of sorted) {
        sum += value;
        curve.push(sum / total);
    }
    const gini = sorted.reduce((sum, value, i) => sum + (2 * (i + 1) - n - 1) * value, 0) / (n * total);
    return { total, gini, curve };
}
export function ranks(values) {
    const sorted = [...values].sort((a, b) => b.value - a.value || a.id - b.id), result = new Map();
    let rank = 0;
    sorted.forEach((p, i) => {
        if (!i || p.value !== sorted[i - 1].value)
            rank = i + 1;
        result.set(p.id, rank);
    });
    return result;
}
export function summarizeOutcomes(history, contracts) {
    let due = 0, paid = 0;
    const initiallyHoused = new Set(history[0].homes.map((h) => h.resident).filter((id) => id !== null));
    return history.map((frame) => {
        const housed = new Set(frame.homes.map((h) => h.resident).filter((id) => id !== null)), intact = new Set(frame.homes.filter((h) => !h.destroyed).map((h) => h.id)), t = Math.max(1, frame.period);
        const insured = new Set(contracts
            .filter((c) => c.starts <= t && c.ends >= t && intact.has(c.home))
            .map((c) => c.home));
        for (const transfer of frame.transfers) {
            if (transfer.kind === 'claim') {
                due += Number(transfer.due);
                paid += Number(transfer.amount);
            }
        }
        return {
            displaced: [...initiallyHoused].filter((id) => !housed.has(id)).length,
            intact: intact.size,
            insured: insured.size,
            due,
            paid,
            events: frame.events.length,
        };
    });
}
export function histogramBins(values, binCount = 10) {
    const max = Math.max(0, ...values), step = max === 0 ? 1 : max / binCount, counts = Array(binCount).fill(0);
    for (const value of values)
        counts[Math.min(binCount - 1, Math.max(0, Math.floor(value / step)))]++;
    return { counts, step };
}

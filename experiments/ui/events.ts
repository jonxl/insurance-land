import type { Frame, Transfer, Money } from './types.js';
// Recorded events and payment groups, independent of the DOM.

export function createEventHelpers({
  money,
  firmName,
}: {
  money: (value: Money) => string;
  firmName: (id: number) => string;
}) {
  function buildLog(history: Frame[]) {
    const log = { disasters: [], insurance: [] },
      capital = new Map();
    const span = (v) =>
        Math.min(...v) === Math.max(...v)
          ? Math.min(...v)
          : `${Math.min(...v)} to ${Math.max(...v)}`,
      plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
    const sum = (rows, key) => rows.reduce((n, t) => n + Number(t[key] || 0), 0);
    history.forEach((frame, period) => {
      for (const firm of frame.firms) {
        const now = Number(firm.capital);
        if (capital.get(firm.id) > 0 && now === 0)
          log.insurance.push({
            period,
            key: `capital:${period}:${firm.id}`,
            alert: true,
            title: `${firmName(firm.id)} insurance ran out of capital`,
            detail: 'Later claims go unpaid until it has capital again.',
          });
        capital.set(firm.id, now);
      }
      const claims = frame.transfers.filter((t) => t.kind === 'claim');
      for (const event of frame.events) {
        const lost = new Set(event.losses),
          own = claims.filter((t) => lost.has(t.home)),
          replies = [];
        if (event.losses.length) replies.push({ title: `Homes lost: ${event.losses.join(', ')}` });
        if (event.displaced.length)
          replies.push({ title: `People displaced: ${event.displaced.join(', ')}` });
        for (const t of own) replies.push(describeTransfer(t));
        if (!replies.length)
          replies.push({
            title: 'These homes were already destroyed, so there are no new losses or claims.',
          });
        log.disasters.push({
          period,
          key: `disaster:${period}:${event.id}`,
          event: event.id,
          strike: true,
          count: 1,
          lost: event.losses.length,
          claims: own.length,
          title: `Disaster at rows ${span(event.cells.map((c) => c[0]))}, columns ${span(event.cells.map((c) => c[1]))}`,
          detail: event.losses.length
            ? `${plural(event.losses.length, 'home', 'homes')} lost, ${plural(event.displaced.length, 'person', 'people')} displaced, ${plural(own.length, 'claim', 'claims')}`
            : 'Only struck homes that were already destroyed',
          replies,
        });
      }
      const premiums = frame.transfers.filter((t) => t.kind === 'premium');
      if (premiums.length)
        log.insurance.push({
          period,
          key: `premium:${period}`,
          title: `${premiums.length} premiums collected`,
          amount: sum(premiums, 'amount'),
          replies: premiums.map(describeTransfer),
        });
      for (const firm of frame.firms) {
        const own = claims.filter((t) => t.firm === firm.id);
        if (!own.length) continue;
        const due = sum(own, 'due'),
          short = sum(own, 'shortfall');
        log.insurance.push({
          period,
          key: `claims:${period}:${firm.id}`,
          count: own.length,
          due,
          short,
          alert: short > 0,
          title: `${firmName(firm.id)}: ${plural(own.length, 'claim', 'claims')}`,
          detail: `Due ${money(due)}, paid ${money(sum(own, 'amount'))}${short > 0 ? `, short ${money(short)}` : ''}`,
          amount: sum(own, 'amount'),
          replies: own.map(describeTransfer),
        });
      }
    });
    return log;
  }
  function timelineEvents(history: Frame[]) {
    const log = buildLog(history),
      events = [];
    history.forEach((frame, period) => {
      events.push(...ledgerGroups(frame, period).filter((group) => group.kind !== 'claim'));
      events.push(...log.disasters.filter((event) => event.period === period));
      const linkedHomes = new Set(frame.events.flatMap((event) => event.losses));
      const otherClaims = frame.transfers.filter(
        (t) => t.kind === 'claim' && !linkedHomes.has(t.home),
      );
      if (otherClaims.length)
        events.push({
          period,
          key: `other-claims:${period}`,
          title: 'Other recorded claims',
          replies: otherClaims.map(describeTransfer),
        });
      events.push(
        ...log.insurance.filter(
          (event) => event.period === period && event.key.startsWith('capital:'),
        ),
      );
    });
    return events;
  }
  // Groups one period's transfers so repeated payments read as one message.
  function ledgerGroups(frame, period) {
    const pick = (test) => frame.transfers.filter(test),
      sum = (rows, key) => rows.reduce((n, t) => n + Number(t[key] || 0), 0),
      groups = [];
    const add = (kind, rows, title, key, extra = {}) => {
      if (rows.length)
        groups.push({
          period,
          kind,
          key: `ledger:${period}:${kind}`,
          title: title(rows.length),
          amount: sum(rows, key),
          rows,
          ...extra,
        });
    };
    add(
      'income',
      pick((t) => t.kind === 'income'),
      (n) => `${n} ${n === 1 ? 'person' : 'people'} received income`,
      'amount',
    );
    add(
      'rent',
      pick((t) => t.kind === 'rent' && t.paid),
      (n) => `${n} ${n === 1 ? 'rent' : 'rents'} paid`,
      'amount',
    );
    add(
      'unpaid',
      pick((t) => t.kind === 'rent' && !t.paid),
      (n) => `${n} ${n === 1 ? 'rent' : 'rents'} missed`,
      'requested',
      { alert: true },
    );
    add(
      'premium',
      pick((t) => t.kind === 'premium'),
      (n) => `${n} ${n === 1 ? 'premium' : 'premiums'} collected`,
      'amount',
    );
    const claims = pick((t) => t.kind === 'claim'),
      short = sum(claims, 'shortfall');
    add(
      'claim',
      claims,
      (n) => `${n} ${n === 1 ? 'claim' : 'claims'} paid out`,
      'amount',
      short > 0 ? { alert: true, detail: `Short ${money(short)}` } : {},
    );
    return groups;
  }
  // Every transfer in period order. Rows hold references, and text is built only for rows on screen.
  function ledgerRows(history: Frame[]) {
    const rows = [];
    history.forEach((frame, period) => {
      for (const transfer of frame.transfers) rows.push({ period, transfer });
    });
    return rows;
  }
  const unpaidRent = (t) => t.kind === 'rent' && !t.paid;
  function matchesKind(transfer: Transfer, kind: string) {
    return kind === 'all' || (kind === 'unpaid' ? unpaidRent(transfer) : transfer.kind === kind);
  }
  // Rows are sorted by period, so the count through a period is a binary search.
  function countThrough(rows: { period: number }[], period: number) {
    let low = 0,
      high = rows.length;
    while (low < high) {
      const mid = (low + high) >> 1;
      if (rows[mid].period <= period) low = mid + 1;
      else high = mid;
    }
    return low;
  }
  function describeTransfer(t: Transfer) {
    if (t.kind === 'income')
      return { title: `Person ${t.person} received income`, amount: t.amount };
    if (t.kind === 'premium')
      return {
        title: `Person ${t.person} paid a premium to ${firmName(t.firm)}`,
        detail: `Home ${t.home}`,
        amount: t.amount,
      };
    if (t.kind === 'rent')
      return t.paid
        ? {
            title: `Person ${t.person} paid rent to person ${t.recipient}`,
            detail: `Home ${t.home}`,
            amount: t.amount,
          }
        : {
            title: `Person ${t.person} missed rent to person ${t.recipient}`,
            detail: `Home ${t.home}, unpaid`,
            amount: t.requested,
            alert: true,
          };
    const short = Number(t.shortfall),
      paid = Number(t.amount);
    return {
      title:
        short <= 0
          ? `${firmName(t.firm)} paid a claim to person ${t.person}`
          : paid > 0
            ? `${firmName(t.firm)} partly paid a claim to person ${t.person}`
            : `${firmName(t.firm)} could not pay a claim to person ${t.person}`,
      detail: `Home ${t.home}, due ${money(t.due)}${short > 0 ? `, short ${money(short)}` : ''}`,
      amount: t.amount,
      alert: short > 0,
    };
  }
  return {
    buildLog,
    timelineEvents,
    ledgerGroups,
    ledgerRows,
    matchesKind,
    countThrough,
    describeTransfer,
  };
}

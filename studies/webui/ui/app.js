import { treemap, metricValues, distribution, ranks, summarizeOutcomes, histogramBins, } from './metrics.js';
import { createEventHelpers } from './events.js';
export function initializeDiagnostics(bundle) {
    const worlds = 'worlds' in bundle ? bundle.worlds : { Standard: bundle };
    let worldName = ('default' in bundle ? bundle.default : undefined) ?? 'Standard', data = worlds[worldName], frames = data.frames;
    const $ = (id) => document.getElementById(id), money = (n) => Number(n).toLocaleString('en-US', {
        style: 'currency',
        currency: 'USD',
        maximumFractionDigits: 2,
    });
    // Semantic palette: purple only for disasters, gray only for "unaffected in this field".
    const CALM = '#d9d6d1', CALM_INK = '#4f4a44', SCAR = '#4a2496', INK = '#2e1c12', QUIET = '#8f8173';
    const PURPLES = ['#c9b3f3', '#a783ea', '#7c50d4', '#5c33ae', SCAR], CARAMELS = ['#f2dfbd', '#e0bb85', '#c08f55', '#8f5f30', '#5a371c'];
    const FIRM_LINES = { 1: '#c8352d', 2: '#16875a', 3: '#2563c9' };
    const onDark = new Set(['#7c50d4', '#5c33ae', SCAR, '#8f5f30', '#5a371c']);
    const inkOn = (bg) => (onDark.has(bg) ? '#fff' : bg === CALM ? CALM_INK : INK);
    const clamp = (v, low, high) => Math.min(high, Math.max(low, v));
    let view = 'map', activeRun = null, pollTimer = null, libraryTimer = null, libraryRefreshing = false, runnerReady = false, lastRun = null;
    function experimentLabel(name = worldName) {
        return Object.keys(worlds).length > 1 ? 'Dev ' + name : bundle.title || name + ' experiment';
    }
    function updateHeader() {
        const library = view === 'start', loading = view === 'loading';
        $('headerDivider').hidden = library;
        $('experimentIdentity').hidden = library;
        $('experimentTabs').hidden = library || loading;
        $('experimentState').hidden = !loading;
        $('workspaceTitle').textContent = loading
            ? lastRun?.title || 'Preparing experiment'
            : experimentLabel();
        $('experimentType').textContent =
            'Type: ' + (loading ? lastRun?.configuration.name || '…' : worldName);
        $('experimentState').textContent = loading
            ? lastRun?.state === 'failed'
                ? 'Failed'
                : lastRun?.state === 'queued'
                    ? 'Queued'
                    : 'Running'
            : '';
        document.title = library
            ? 'Insurance Land · Experiments'
            : 'Insurance Land · ' + $('workspaceTitle').textContent;
    }
    function navigateView(next) {
        const query = new URLSearchParams(location.search);
        query.delete('run');
        query.set('view', next);
        query.set('world', worldName);
        history.pushState(null, '', '?' + query.toString());
        showView(next);
    }
    function showView(next) {
        view = next;
        if (next !== 'start')
            clearTimeout(libraryTimer);
        const start = next === 'start', loading = next === 'loading', research = next === 'research';
        $('experimentView').hidden = !start;
        $('loadingView').hidden = !loading;
        $('snapshotView').hidden = start || loading;
        $('worlds').hidden = start || loading;
        $('worldName').hidden = start || loading;
        $('snapshotMap').hidden = research;
        $('researchView').hidden = !research;
        $('readView').setAttribute('aria-pressed', String(next === 'map' || loading));
        $('researchTab').setAttribute('aria-pressed', String(research));
        $('startView').setAttribute('aria-pressed', String(start));
        $('readView').disabled = loading;
        $('researchTab').disabled = loading;
        hideTip();
        stopPlay();
        if (research)
            renderResearch();
        if (next === 'map')
            render();
        updateHeader();
    }
    function openLibrary(push = true) {
        activeRun = null;
        clearTimeout(pollTimer);
        if (push)
            history.pushState(null, '', location.pathname);
        showView('start');
        refreshLibrary();
    }
    $('researchTab').onclick = () => navigateView('research');
    $('readView').onclick = () => navigateView('map');
    $('startView').onclick = () => openLibrary();
    $('backToLibrary').onclick = () => openLibrary();
    function openExperiment(settings = null) {
        $('runStatus').textContent = '';
        if (settings)
            for (const [key, value] of Object.entries(settings)) {
                const input = $('experimentForm').elements.namedItem(key);
                if (input)
                    input.value = String(value);
            }
        syncExperimentType();
        $('experimentDialog').showModal();
    }
    $('closeExperiment').onclick = $('cancelExperiment').onclick = () => $('experimentDialog').close();
    const config = worlds[worldName].configuration;
    if (config)
        for (const [key, value] of Object.entries(config)) {
            const input = $('experimentForm').elements.namedItem(key);
            if (input)
                input.value = String(value);
        }
    function syncExperimentType() {
        const chaos = $('experimentForm').elements.namedItem('name').value === 'Chaos';
        $('chaosRateControl').hidden = !chaos;
        $('experimentForm').elements.namedItem('chaos_rate_ratio').disabled =
            !chaos;
    }
    syncExperimentType();
    $('experimentForm').elements.namedItem('name').onchange = (event) => {
        $('experimentForm').elements.namedItem('rate').value = String(worlds[event.target.value]?.configuration?.rate ??
            (event.target.value === 'Standard' ? 0.1 : 0.5));
        syncExperimentType();
    };
    function slotCard(title, detail, state, open) {
        const card = document.createElement('button');
        card.type = 'button';
        card.className = 'world-slot';
        card.onclick = open;
        const preview = document.createElement('div');
        preview.className = 'slot-preview';
        preview.setAttribute('aria-hidden', 'true');
        for (let i = 0; i < 24; i++)
            preview.append(document.createElement('i'));
        const heading = document.createElement('h3');
        heading.textContent = title;
        const info = document.createElement('p');
        info.textContent = detail;
        const status = document.createElement('p');
        status.className = 'slot-state';
        status.textContent = state;
        card.append(preview, heading, info, status);
        return card;
    }
    function renderLibrary(runs = []) {
        const focused = document.activeElement?.dataset?.slot;
        const grid = $('worldLibrary');
        grid.replaceChildren();
        for (const name of ['Peace', 'Standard', 'Chaos']) {
            const card = slotCard('Dev ' + name, 'Type: ' + name + ' · Dev reference experiment', 'Open experiment →', () => {
                if (Object.keys(worlds).length > 1 && worlds[name]) {
                    setWorld(name);
                    navigateView('map');
                }
                else
                    location.href = '/diagnostics.html?world=' + encodeURIComponent(name) + '&view=map';
            });
            card.dataset.slot = name;
            grid.append(card);
        }
        for (const run of runs) {
            const c = run.configuration;
            const state = run.state === 'complete'
                ? 'Open experiment →'
                : run.state === 'failed'
                    ? 'Needs attention →'
                    : run.state === 'queued'
                        ? 'Queued →'
                        : `Running · ${run.completed_periods} / ${c.periods} periods →`;
            const card = slotCard(run.title, `Type: ${c.name} · Seed ${c.seed} · ${c.rows} × ${c.columns} regions · ${c.periods} periods`, state, () => openRun(run));
            card.dataset.slot = run.id;
            const date = document.createElement('time');
            date.dateTime = run.created_at;
            date.textContent = new Date(run.created_at).toLocaleString();
            card.insertBefore(date, card.lastChild);
            grid.append(card);
        }
        const add = document.createElement('button');
        add.type = 'button';
        add.dataset.slot = 'new';
        add.className = 'world-slot new-world';
        add.setAttribute('aria-label', 'Create a new experiment');
        add.innerHTML =
            '<span class="plus" aria-hidden="true">+</span><span>Create a new experiment</span>';
        add.onclick = () => openExperiment();
        grid.append(add);
        if (focused)
            Array.from(grid.children)
                .find((card) => card.dataset.slot === focused)
                ?.focus({ preventScroll: true });
    }
    async function refreshLibrary() {
        clearTimeout(libraryTimer);
        if (view !== 'start' || document.hidden || libraryRefreshing)
            return;
        libraryRefreshing = true;
        let pending = false;
        try {
            const response = await fetch('/api/runs');
            if (!response.ok)
                throw new Error('Saved experiments are unavailable. Check that the local runner is running.');
            const payload = await response.json();
            if (view !== 'start' || document.hidden)
                return;
            pending = payload.runs.some((run) => run.state === 'queued' || run.state === 'running');
            if (!$('experimentDialog').open)
                renderLibrary(payload.runs);
            $('libraryStatus').textContent = payload.runs.length
                ? `${payload.runs.length} saved experiment${payload.runs.length === 1 ? '' : 's'}`
                : 'Your saved experiments will appear here.';
        }
        catch (error) {
            if (view === 'start')
                $('libraryStatus').textContent = error.message;
        }
        finally {
            libraryRefreshing = false;
        }
        if (view === 'start' && !document.hidden && runnerReady && pending)
            libraryTimer = setTimeout(refreshLibrary, 2500);
    }
    function renderRun(run) {
        lastRun = run;
        $('loadingTitle').textContent = run.title;
        const c = run.configuration;
        $('loadingSettings').textContent =
            `Type: ${c.name} · Seed ${c.seed} · ${c.rows} × ${c.columns} regions · ${c.periods} periods`;
        $('loadingStage').textContent =
            run.state === 'failed' ? 'Experiment could not finish' : run.stage || 'Waiting to start';
        $('loadingView').setAttribute('aria-busy', String(run.state === 'running' || run.state === 'queued'));
        $('runProgress').max = c.periods;
        $('runProgress').value = run.completed_periods;
        $('runProgress').hidden = run.state === 'failed';
        $('loadingStatus').textContent =
            run.state === 'failed'
                ? run.error
                : run.state === 'queued'
                    ? 'Waiting for the current experiment to finish.'
                    : `${run.completed_periods} of ${c.periods} periods completed.`;
        $('retryWorld').hidden = run.state !== 'failed';
        $('retryStatus').hidden = true;
        updateHeader();
    }
    function openRun(run) {
        if (run.state === 'complete') {
            location.href = run.url;
            return;
        }
        lastRun = run;
        activeRun = run.id;
        history.pushState(null, '', '?run=' + encodeURIComponent(run.id));
        showView('loading');
        renderRun(run);
        $('loadingTitle').focus();
        pollRun(run.id);
    }
    async function pollRun(id) {
        clearTimeout(pollTimer);
        try {
            const response = await fetch('/api/runs/' + encodeURIComponent(id));
            const run = await response.json();
            if (activeRun !== id)
                return;
            if (!response.ok)
                throw new Error(run.error || 'Could not load this experiment.');
            renderRun(run);
            if (run.state === 'complete') {
                location.replace(run.url);
                return;
            }
            if (run.state !== 'failed')
                pollTimer = setTimeout(() => pollRun(id), 1000);
        }
        catch (error) {
            if (activeRun !== id)
                return;
            $('loadingStatus').textContent = error.message + ' Reconnect to check progress.';
            $('loadingView').setAttribute('aria-busy', 'false');
            $('retryStatus').hidden = false;
        }
    }
    $('retryStatus').onclick = () => {
        if (activeRun)
            pollRun(activeRun);
    };
    $('retryWorld').onclick = () => openExperiment({ ...lastRun.configuration, title: lastRun.title });
    $('loadingMap').replaceChildren(...Array.from({ length: 64 }, () => document.createElement('i')));
    $('experimentForm').onsubmit = async (event) => {
        event.preventDefault();
        $('launch').disabled = true;
        $('runStatus').textContent = 'Saving your experiment…';
        try {
            const settings = Object.fromEntries(new FormData(event.currentTarget));
            for (const key of Object.keys(settings))
                if (!['name', 'title'].includes(key))
                    settings[key] = Number(settings[key]);
            const response = await fetch('/api/runs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings),
            });
            const run = await response.json();
            if (!response.ok)
                throw new Error(run.error || 'Could not create experiment');
            $('experimentDialog').close();
            openRun(run);
        }
        catch (error) {
            $('runStatus').textContent = error.message;
        }
        finally {
            $('launch').disabled = !runnerReady;
        }
    };
    function restoreRoute() {
        activeRun = null;
        lastRun = null;
        clearTimeout(pollTimer);
        clearTimeout(libraryTimer);
        const query = new URLSearchParams(location.search);
        if (query.has('run')) {
            activeRun = query.get('run');
            showView('loading');
            $('loadingStatus').textContent = 'Reconnecting to your saved experiment…';
            pollRun(activeRun);
        }
        else if (['map', 'research'].includes(query.get('view'))) {
            const selected = query.get('world');
            if (selected && worlds[selected])
                setWorld(selected);
            showView(query.get('view'));
        }
        else {
            showView('start');
            if (runnerReady)
                refreshLibrary();
        }
    }
    window.addEventListener('popstate', restoreRoute);
    document.addEventListener('visibilitychange', () => {
        if (document.hidden)
            clearTimeout(libraryTimer);
        else if (view === 'start' && runnerReady)
            refreshLibrary();
    });
    async function initializeLibrary() {
        renderLibrary();
        restoreRoute();
        if (['http:', 'https:'].includes(location.protocol)) {
            try {
                const response = await fetch('/api/health');
                const result = await response.json();
                runnerReady = response.ok && result.ready;
            }
            catch { }
        }
        $('launch').disabled = !runnerReady;
        if (runnerReady) {
            $('runnerHelp').textContent =
                'Experiments are saved on this computer. Keep the local runner active while experiments run.';
            if (view === 'start')
                refreshLibrary();
        }
        else
            $('libraryStatus').textContent =
                'Dev experiments are ready to explore. Start the local runner to create and load saved experiments.';
    }
    let chartView = 'balance';
    let period = 0, homeId = null, selectedKind = 'person', selectedId = null;
    // Overview is the default; individual stats only appear on the People tab.
    let panelTab = 'overview', focusEvent = null, ledgerKind = 'all';
    const openThreads = new Set();
    function setTab(tab) {
        panelTab = tab;
        hideTip();
        render();
        $('panelBody').scrollTop = 0;
    }
    const worldBlurbs = {
        Peace: 'Equal income, one owner-occupied home per person, identical prices. Disaster risk is still spatially unequal.',
        Standard: 'Unequal income and ownership, spatially varying prices, and a constant disaster rate.',
        Chaos: 'Standard’s people and prices, with a disaster rate that grows over time.',
    };
    function setWorld(name) {
        mountedTimelineKey = null;
        if (worldName !== name)
            clearSelection();
        worldName = name;
        data = worlds[name];
        frames = data.frames;
        period = Math.min(period, frames.length - 1);
        $('period').max = String(frames.length - 1);
        focusEvent = null;
        openThreads.clear();
        renderRibbon();
        render();
    }
    Object.keys(worlds).forEach((name) => {
        const b = document.createElement('button');
        b.textContent = experimentLabel(name);
        b.dataset.world = name;
        b.onclick = () => {
            setWorld(name);
            navigateView(view === 'research' ? 'research' : 'map');
        };
        $('worlds').append(b);
    });
    $('period').max = String(frames.length - 1);
    // A person keeps the same owner color across worlds and all recorded periods.
    const personColors = new Map(), usedPersonColors = new Set();
    const reservedFirmColors = ['#f5b7b5', '#ccebc5', '#b3cde3', '#e53935', '#00a651', '#007aff'].map((hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)));
    function ownerColor(id) {
        // Build in ID order so a person's hex stays the same across worlds and exports.
        // Hues 250-320 are left out: purple is reserved for disasters.
        for (let person = personColors.size + 1; person <= id; person++) {
            let seed = person >>> 0, color;
            do {
                seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
                const bands = [
                    [0, 60],
                    [60, 130],
                    [130, 225],
                    [322, 360],
                ], band = bands[seed % bands.length];
                const hue = band[0] + (((seed >>> 2) % 1000) / 1000) * (band[1] - band[0]);
                const saturation = 0.46 + ((seed >>> 12) % 25) / 100, light = 0.66 + ((seed >>> 20) % 19) / 100;
                const amplitude = saturation * Math.min(light, 1 - light);
                const rgb = [0, 8, 4].map((n) => {
                    const k = (n + hue / 30) % 12;
                    return Math.round(255 * (light - amplitude * Math.max(-1, Math.min(k - 3, 9 - k, 1))));
                });
                if (reservedFirmColors.some((firm) => Math.hypot(...rgb.map((v, i) => v - firm[i])) < 40))
                    continue;
                color = '#' + rgb.map((v) => v.toString(16).padStart(2, '0')).join('');
            } while (!color || usedPersonColors.has(color));
            personColors.set(person, color);
            usedPersonColors.add(color);
        }
        return personColors.get(id);
    }
    const shape = [
        Math.max(...frames[0].homes.map((h) => h.position[0])) + 1,
        Math.max(...frames[0].homes.map((h) => h.position[1])) + 1,
    ];
    $('grid').style.gridTemplateColumns = `1.4em repeat(${shape[1]},minmax(0,1fr))`;
    // A treemap that keeps geography: split by grid position, giving each side area by home count.
    const regionMembers = new Map();
    frames[0].homes.forEach((h) => {
        const key = h.position.join(',');
        if (!regionMembers.has(key))
            regionMembers.set(key, []);
        regionMembers.get(key).push(h.id);
    });
    const regionSize = (h) => regionMembers.get(h.position.join(',')).length;
    const blocks = treemap([...regionMembers].map(([key, ids]) => {
        const [row, col] = key.split(',').map(Number);
        return { key, row, col, count: ids.length, ids };
    }), 0, 0, shape[1], shape[0]);
    const tiles = new Map(), heads = new Map(), spots = new Map(), homeBoxes = new Map();
    $('grid').style.aspectRatio = `${shape[1]}/${shape[0]}`;
    $('grid').classList.toggle('dense', blocks.length > 256);
    blocks.forEach((block) => {
        const tile = document.createElement('div'), head = document.createElement('div'), inner = document.createElement('div');
        tile.className = 'region';
        tile.style.cssText = `left:${(100 * block.x) / shape[1]}%;top:${(100 * block.y) / shape[0]}%;width:${(100 * block.w) / shape[1]}%;height:${(100 * block.h) / shape[0]}%`;
        head.className = 'region-head';
        inner.className = 'region-homes';
        tile.append(head, inner);
        $('grid').append(tile);
        tiles.set(block.key, inner);
        heads.set(block.key, head);
        // Homes sit in even rows matched to the block's shape; the last row stretches to fill it.
        const count = block.ids.length, across = Math.max(1, Math.min(count, Math.round(Math.sqrt((count * block.w) / block.h)))), lines = Math.ceil(count / across), extra = lines * across - count;
        block.ids.forEach((id, i) => {
            const line = Math.floor(i / across), inLine = line === lines - 1 ? across - extra : across, place = i - line * across;
            homeBoxes.set(id, {
                left: (100 * place) / inLine,
                top: (100 * line) / lines,
                width: 100 / inLine,
                height: 100 / lines,
            });
            spots.set(id, {
                x: block.x + (block.w * place) / inLine + 0.015,
                y: block.y + (block.h * line) / lines + 0.015,
                w: block.w / inLine - 0.03,
                h: block.h / lines - 0.03,
            });
        });
    });
    // Size labels to the drawn map, and drop the strip where it would crowd a thin block's homes.
    function fitBlocks() {
        const unit = $('grid').clientWidth / shape[1];
        if (!unit)
            return;
        $('grid').style.setProperty('--home-side', `${unit * Math.sqrt((shape[0] * shape[1]) / frames[0].homes.length)}px`);
        for (const block of blocks)
            heads.get(block.key).hidden = block.h * unit < 44 || block.w * unit < 48;
    }
    fitBlocks();
    new ResizeObserver(fitBlocks).observe($('grid'));
    const buttons = new Map();
    frames[0].homes.forEach((h) => {
        let b = document.createElement('button');
        b.className = 'cell';
        b.onclick = () => selectHome(h.id);
        b.dataset.home = String(h.id);
        tiles.get(h.position.join(',')).append(b);
        const box = homeBoxes.get(h.id);
        b.style.left = `${box.left}%`;
        b.style.top = `${box.top}%`;
        b.style.width = `calc(${box.width}% - 1px)`;
        b.style.height = `calc(${box.height}% - 1px)`;
        buttons.set(h.id, b);
    });
    const initialMax = Math.max(...Object.values(worlds).flatMap((w) => w.frames[0].homes.map((h) => Number(h.value))));
    const currentLayer = () => document.querySelector('input[name=layer]:checked').value;
    function setLayer(value) {
        document.querySelector(`input[name=layer][value=${value}]`).checked = true;
    }
    function displacedResident(home) {
        if (!home.destroyed)
            return null;
        const resident = frames[0].homes.find((initial) => initial.id === home.id)?.resident;
        return resident != null &&
            !frames[period].homes.some((current) => current.resident === resident)
            ? resident
            : null;
    }
    function covered(frame) {
        const t = Math.max(frame.period, 1);
        return data.contracts.filter((c) => c.starts <= t && c.ends >= t && !frame.homes.find((h) => h.id === c.home).destroyed);
    }
    const personIcon = '<svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="7" r="4"/><path d="M4 22v-3a8 8 0 0 1 16 0v3"/></svg>';
    const firmStyles = {
        1: { name: 'Red', color: '#f5b7b5', border: '#e53935' },
        2: { name: 'Green', color: '#ccebc5', border: '#00a651' },
        3: { name: 'Blue', color: '#b3cde3', border: '#007aff' },
    };
    const firmName = (id) => firmStyles[id]?.name ?? `Firm ${id}`;
    const { buildLog, timelineEvents, ledgerGroups, ledgerRows, matchesKind, countThrough, describeTransfer, } = createEventHelpers({ money, firmName });
    const firmColor = (id) => firmStyles[id]?.color ?? CALM;
    const firmBorder = (id) => firmStyles[id]?.border ?? 'transparent';
    frames[0].firms.forEach((f) => {
        const button = document.createElement('button');
        const swatch = document.createElement('span');
        swatch.className = 'firm-swatch';
        swatch.style.background = firmBorder(f.id);
        swatch.setAttribute('aria-hidden', 'true');
        const label = document.createElement('span');
        button.append(swatch, label);
        button.dataset.firm = String(f.id);
        button.onclick = () => {
            if (selectedKind === 'firm' && selectedId === f.id) {
                clearInsurer();
                return;
            }
            panelTab = 'people';
            selectedKind = 'firm';
            selectedId = f.id;
            render();
        };
        $('firms').append(button);
    });
    /* Hover readout shared by the map, the ribbon, and time charts. */
    function showTip(html, x, y) {
        const tip = $('tip');
        tip.innerHTML = html;
        tip.hidden = false;
        const r = tip.getBoundingClientRect();
        tip.style.left = clamp(x + 14, 8, innerWidth - r.width - 8) + 'px';
        tip.style.top = (y + 14 + r.height > innerHeight - 8 ? y - r.height - 10 : y + 14) + 'px';
    }
    function hideTip() {
        $('tip').hidden = true;
    }
    function bindTimeline(host, left, width, viewWidth, top, bottom, describe) {
        const svg = host.querySelector('svg');
        svg.classList.add('timed');
        const hair = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        hair.setAttribute('class', 'hair');
        hair.setAttribute('y1', top);
        hair.setAttribute('y2', bottom);
        hair.style.display = 'none';
        svg.append(hair);
        const indexAt = (e) => {
            const r = svg.getBoundingClientRect();
            return clamp(Math.round(((((e.clientX - r.left) / r.width) * viewWidth - left) / width) * (frames.length - 1)), 0, frames.length - 1);
        };
        svg.onpointermove = (e) => {
            const i = indexAt(e), x = left + (width * i) / Math.max(1, frames.length - 1);
            hair.setAttribute('x1', x);
            hair.setAttribute('x2', x);
            hair.style.display = '';
            showTip(`<b>Period ${i}</b>${describe(i)}<div class="sub">Click to jump here</div>`, e.clientX, e.clientY);
        };
        svg.onpointerleave = () => {
            hair.style.display = 'none';
            hideTip();
        };
        svg.onclick = (e) => goTo(indexAt(e));
    }
    function chart(series, labels, isMoney, colors = [INK, QUIET], h = 200) {
        const ticks = h < 200 ? 2 : 4, w = 620, left = 84, right = 24, top = 12, bottom = 32;
        const max = Math.max(1, ...series.flat()), x = (i) => left + (i / Math.max(1, frames.length - 1)) * (w - left - right), y = (v) => h - bottom - (v / max) * (h - top - bottom);
        let s = `<svg class="chart" role="img" aria-label="${labels.join(' and ')} across periods" viewBox="0 0 ${w} ${h}">`;
        for (let j = 0; j <= ticks; j++) {
            let v = (max * j) / ticks;
            s += `<line x1="${left}" x2="${w - right}" y1="${y(v)}" y2="${y(v)}" stroke="#ece1cf"/><text x="${left - 6}" y="${y(v) + 6}" text-anchor="end" font-size="20">${isMoney ? '$' : ''}${v >= 1e6 ? (v / 1e6).toFixed(1) + 'm' : v >= 1000 ? (v / 1000).toFixed(1) + 'k' : Number.isInteger(v) ? v : v.toFixed(1)}</text>`;
        }
        series.forEach((values, j) => {
            s += `<polyline fill="none" stroke="${colors[j]}" stroke-width="3" stroke-linejoin="round" ${j ? `stroke-dasharray="${j === 1 ? '8 6' : '2 6'}"` : ''} points="${values.map((v, i) => `${x(i)},${y(v)}`).join(' ')}"/>`;
        });
        s += `<line x1="${x(period)}" x2="${x(period)}" y1="${top}" y2="${h - bottom}" stroke="${INK}" stroke-dasharray="4 3"/>`;
        series.forEach((values, j) => {
            s += `<circle cx="${x(period)}" cy="${y(values[period])}" r="4" fill="${colors[j]}" stroke="#fffbf5" stroke-width="2"/>`;
        });
        s += `<text x="${left}" y="${h - 6}" font-size="20">Period 0</text><text x="${w - right}" y="${h - 6}" text-anchor="end" font-size="20">${frames.length - 1}</text></svg>`;
        return s;
    }
    function cashFlow(frame, id, person) {
        let incoming = 0, outgoing = 0;
        for (const t of frame.transfers) {
            const amount = Number(t.amount);
            if (person) {
                if (t.kind === 'income' && t.person === id)
                    incoming += amount;
                if (t.kind === 'rent') {
                    if (t.person === id)
                        outgoing += amount;
                    if (t.recipient === id)
                        incoming += amount;
                }
                if (t.kind === 'premium' && t.person === id)
                    outgoing += amount;
                if (t.kind === 'claim' && t.person === id)
                    incoming += amount;
            }
            else if (t.firm === id) {
                if (t.kind === 'premium')
                    incoming += amount;
                if (t.kind === 'claim')
                    outgoing += amount;
            }
        }
        return [incoming, outgoing];
    }
    function chartData(view, id, person) {
        if (view === 'flows') {
            const values = frames.map((f) => cashFlow(f, id, person));
            return {
                title: person ? 'Money in and out' : 'Insurer money in and out',
                labels: ['Received', 'Paid'],
                series: [values.map((v) => v[0]), values.map((v) => v[1])],
                money: true,
                note: 'Actual cash transfers per period. Period 0 includes opening premiums. Unpaid amounts are excluded.',
            };
        }
        if (view === 'claims') {
            let due = 0, paid = 0;
            const values = frames.map((f) => {
                for (const t of f.transfers) {
                    if (t.kind === 'claim' && (person ? t.person === id : t.firm === id)) {
                        due += Number(t.due);
                        paid += Number(t.amount);
                    }
                }
                return [due, paid];
            });
            return {
                title: person ? 'Cumulative insurance claims' : 'Insurer cumulative insurance claims',
                labels: ['Due', 'Paid'],
                series: [values.map((v) => v[0]), values.map((v) => v[1])],
                money: true,
                note: 'Contractual claims only. The gap is unpaid claims caused by insufficient insurer capital; it excludes uninsured losses and deductibles.',
            };
        }
        if (view === 'disasters') {
            return {
                title: `Disaster counts in “${experimentLabel()}”`,
                labels: ['Observed', 'Expected'],
                series: [
                    frames.map((f) => f.events.length),
                    frames.map((f, i) => (i === 0 ? 0 : (data.rates?.[i - 1] ?? 0.5))),
                ],
                money: false,
                note: 'Whole-world event counts per period, not losses or the selected agent’s exposure. Period 0 has no disasters. Random counts fluctuate around the expected rate.',
            };
        }
        return person
            ? {
                title: 'Cash and property',
                labels: ['Cash', 'Property'],
                series: [
                    frames.map((f) => Number(f.people.find((p) => p.id === id).cash)),
                    frames.map((f) => f.homes.filter((h) => h.owner === id).reduce((n, h) => n + Number(h.value), 0)),
                ],
                money: true,
                note: 'End-of-period balances. Destroyed titles remain owned but have zero modeled property value.',
            }
            : {
                title: 'Insurer capital',
                labels: ['Capital'],
                series: [frames.map((f) => Number(f.firms.find((x) => x.id === id).capital))],
                money: true,
                note: 'Capital after premiums and claims. Zero capital limits future claim payments.',
            };
    }
    function renderChart() {
        const d = chartData(chartView, selectedId, selectedKind === 'person');
        document
            .querySelectorAll('[data-chart]')
            .forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.chart === chartView)));
        const colors = chartView === 'disasters' ? [PURPLES[3], PURPLES[2]] : [INK, QUIET];
        const format = (v) => d.money ? money(v) : Number(v).toLocaleString('en-US', { maximumFractionDigits: 3 });
        $('chartTitle').textContent = d.title;
        $('history').innerHTML = chart(d.series, d.labels, d.money, colors);
        bindTimeline($('history'), 84, 512, 620, 12, 168, (i) => d.labels.map((label, j) => `<div>${label} ${format(d.series[j][i])}</div>`).join(''));
        $('chartKey').innerHTML =
            d.labels
                .map((label, i) => `<span class="key"><i class="${i ? 'dashed' : ''}" style="color:${colors[i]}"></i>${label} <b>${format(d.series[i][period])}</b></span>`)
                .join('') +
                (chartView === 'claims'
                    ? `<span class="key">Unpaid <b>${money(d.series[0][period] - d.series[1][period])}</b></span>`
                    : '');
        $('chartNote').textContent = d.note;
    }
    document.querySelectorAll('[data-chart]').forEach((b) => (b.onclick = () => {
        chartView = b.dataset.chart;
        renderChart();
    }));
    function renderHome() {
        const h = frames[period].homes.find((h) => h.id === homeId);
        const initial = frames[0].homes.find((x) => x.id === homeId);
        const resident = h.resident ?? initial.resident;
        const former = h.resident === null;
        const displaced = displacedResident(h);
        const policies = covered(frames[period]).filter((c) => c.home === h.id);
        const wasOpen = $('home').querySelector('details')?.open;
        $('home').innerHTML =
            `<div class="home-heading"><strong>Home ${h.id}</strong>${h.destroyed ? '<span class="home-destroyed">Destroyed, uninhabitable</span>' : `<span>${money(h.value)}</span>`}${displaced !== null ? `<span class="displaced-note">† Resident ${displaced} displaced</span>` : ''}</div><div class="person-buttons"><button id="inspectOwner" aria-label="Follow owner ${h.owner}" aria-pressed="${selectedKind === 'person' && selectedId === h.owner}">${personIcon} Owner ${h.owner}</button>${resident && resident !== h.owner ? `<button id="inspectResident" aria-label="Follow ${former ? 'former ' : ''}resident ${resident}" aria-pressed="${selectedKind === 'person' && selectedId === resident}">${personIcon} ${former ? 'Former resident' : 'Resident'} ${resident}</button>` : ''}</div><details${wasOpen ? ' open' : ''}><summary>Home details</summary><p>Neighborhood at row ${h.position[0]}, column ${h.position[1]}, with ${regionSize(h) === 1 ? '1 home' : `${regionSize(h)} homes`}. ${h.destroyed ? 'Destroyed; owner retains title.' : 'Intact.'} ${h.resident ? 'Resident ' + h.resident : 'No current resident.'}</p><p>${policies.length ? policies.map((c) => `${c.product}: ${firmName(c.firm)} insurance, person ${c.person}`).join('<br>') : 'No current coverage on an intact home.'}</p></details>`;
        $('inspectOwner').style.background = ownerColor(h.owner);
        $('inspectOwner').title = `Owner ${h.owner}, ${ownerColor(h.owner)}`;
        $('inspectOwner').onclick = () => selectPerson(h.owner);
        if ($('inspectResident')) {
            $('inspectResident').style.background = ownerColor(resident);
            $('inspectResident').onclick = () => selectPerson(resident);
        }
    }
    function clearInsurer() {
        if (homeId === null) {
            clearSelection();
            setTab('overview');
            return;
        }
        selectPerson(frames[period].homes.find((h) => h.id === homeId).owner);
    }
    $('clearInsurer').onclick = clearInsurer;
    function clearSelection() {
        homeId = null;
        selectedKind = 'person';
        selectedId = null;
    }
    function selectHome(id) {
        const home = frames[period].homes.find((home) => home.id === id);
        if (!home)
            return;
        homeId = home.id;
        stopPlay();
        selectPerson(home.owner);
    }
    function selectPerson(id) {
        panelTab = 'people';
        selectedKind = 'person';
        selectedId = id;
        render();
    }
    document
        .querySelectorAll('[data-tab]')
        .forEach((b) => (b.onclick = () => setTab(b.dataset.tab)));
    /* The rule for every lens lives here: what a home looks like under that field. */
    const lensNames = {
        damage: 'Damage',
        observed_hits: 'Observed hits',
        exposure: 'Hit probability',
        residence: 'Residents',
        ownership: 'Owners',
        value: 'Home values',
        income_field: 'Initial resident income',
        coverage: 'Coverage',
        insurers: 'Insurer portfolios',
    };
    const lensNotes = {
        damage: 'Each block is a neighborhood, sized by how many homes it holds. Its strip counts destroyed homes, and each square inside is one home with its own agent. A disaster strikes every home in the neighborhoods it reaches. Purple homes were struck and are uninhabitable; their owners keep title. Gray homes have not been struck.',
        ownership: 'Numbers identify owners. Each owner has a unique color, shared by every home they own, including rented homes. Destroyed homes turn purple and keep the owner ID. † marks a displaced resident, who may differ from the owner; select the home to see their ID.',
        residence: 'Numbers and colors identify residents. On destroyed homes, purple and † preserve the displaced resident’s ID; they no longer live there. Gray means no resident is recorded.',
        value: 'Each block is a neighborhood, sized by how many homes it holds. Its strip shows the mean value of its homes, and each square inside shows that home’s value. Darker caramel means higher value, on a fixed scale across periods and worlds. Purple homes were destroyed and have zero modeled value.',
        insurers: 'Initial assignments follow whole ownership portfolios ranked by initial property value. R = Red, G = Green, B = Blue. Assignments persist after damage and do not guarantee active coverage.',
        coverage: 'B = building policy; R = renters contents policy. Both can cover one home. Only intact, in-term interests count. Gray homes have no active policy.',
    };
    const printsValues = (layer) => ['value', 'income_field', 'exposure', 'observed_hits'].includes(layer);
    function bin(fraction) {
        return Math.min(4, Math.max(0, Math.floor(fraction * 5)));
    }
    function cellLook(layer, h, at, field, withValues = false) {
        const look = (bg, label = '') => ({ bg, fg: inkOn(bg), label, mark: null });
        if (field) {
            const value = field.values.get(h.id);
            if (value === undefined)
                return look(CALM, withValues ? '–' : '');
            const disaster = layer !== 'income_field', floor = field.floor ?? field.min;
            const calm = disaster && value <= floor;
            const fraction = field.max === floor ? 0.5 : (value - floor) / (field.max - floor);
            const bg = calm ? CALM : (disaster ? PURPLES : CARAMELS)[bin(fraction)];
            const printed = layer === 'exposure'
                ? (value * 100).toFixed(1)
                : Math.abs(value) >= 1000
                    ? (value / 1000).toFixed(0) + 'k'
                    : Number(value).toFixed(Number.isInteger(value) ? 0 : 1);
            const result = look(bg, withValues ? printed : '');
            // Fields that describe a place keep their value, so destruction is a corner mark instead of a fill.
            if (h.destroyed && layer !== 'observed_hits')
                result.mark = layer === 'exposure' ? INK : SCAR;
            return result;
        }
        const displaced = displacedResident(h);
        if (layer === 'damage')
            return h.destroyed ? look(SCAR, '×') : look(CALM);
        if (layer === 'ownership') {
            const dagger = displaced !== null ? '†' : '';
            return h.destroyed
                ? look(SCAR, h.owner + dagger)
                : look(ownerColor(h.owner), String(h.owner));
        }
        if (layer === 'residence') {
            const resident = h.resident ?? displaced;
            if (h.destroyed)
                return look(SCAR, resident !== null ? resident + '†' : '×');
            return resident !== null ? look(ownerColor(resident), String(resident)) : look(CALM, '–');
        }
        if (h.destroyed)
            return look(SCAR, '×');
        if (layer === 'value')
            return look(CARAMELS[bin(Number(h.value) / initialMax)], withValues ? Math.round(Number(h.value) / 1000) + 'k' : '');
        if (layer === 'insurers') {
            const firm = data.insurance_assignments?.[h.id];
            return firm ? look(firmColor(firm), firmName(firm).slice(0, 1)) : look(CALM, '–');
        }
        if (layer === 'coverage') {
            if (!at.length)
                return look(CALM, '');
            const label = at.map((c) => (c.product === 'renters' ? 'R' : 'B')).join('/');
            return new Set(at.map((c) => c.firm)).size === 1
                ? look(firmColor(at[0].firm), label)
                : look('#fffbf5', label);
        }
        return look(CALM);
    }
    // The strip on each block summarizes its homes for the current lens.
    function regionSummary(layer, homes, field) {
        const count = homes.length, lost = homes.filter((h) => h.destroyed).length, average = (values) => values.reduce((a, b) => a + b, 0) / values.length, thousands = (v) => `$${Math.round(v / 1000)}k`;
        const neutral = { bg: '#e9dfcf', label: count === 1 ? '1 home' : `${count} homes` };
        if (layer === 'damage')
            return {
                bg: lost === 0 ? CALM : lost === count ? SCAR : PURPLES[2],
                label: `${lost} of ${count}`,
            };
        if (layer === 'value') {
            const mean = average(homes.map((h) => Number(h.value)));
            return {
                bg: lost === count ? SCAR : CARAMELS[bin(mean / initialMax)],
                label: thousands(mean),
            };
        }
        if (!field)
            return neutral;
        const values = homes.map((h) => field.values.get(h.id)).filter((v) => v !== undefined);
        if (!values.length)
            return neutral;
        const mean = average(values), disaster = layer !== 'income_field', floor = field.floor ?? field.min, fraction = field.max === floor ? 0.5 : (mean - floor) / (field.max - floor);
        const label = layer === 'income_field'
            ? thousands(mean)
            : layer === 'exposure'
                ? `${(mean * 100).toFixed(1)}%`
                : mean.toFixed(1);
        return {
            bg: disaster && mean <= floor ? CALM : (disaster ? PURPLES : CARAMELS)[bin(fraction)],
            label,
        };
    }
    function byHome(policies) {
        const map = new Map();
        for (const c of policies) {
            if (!map.has(c.home))
                map.set(c.home, []);
            map.get(c.home).push(c);
        }
        return map;
    }
    function renderLegend(layer, field, f, policyMap, person) {
        const item = (bg, label, count = undefined) => `<span class="lg"><i class="sw" style="background:${bg}"></i>${label}${count === undefined ? '' : ` <b>${count}</b>`}</span>`;
        const ramp = (colors, low, high) => `<span class="lg">${low}<span class="ramp">${colors.map((c) => `<i class="sw" style="background:${c}"></i>`).join('')}</span>${high}</span>`;
        const corner = (mark, label) => `<span class="lg"><i class="sw corner" style="--mark:${mark}"></i>${label}</span>`;
        const destroyed = f.homes.filter((h) => h.destroyed).length, intact = f.homes.length - destroyed;
        let parts = [];
        if (layer === 'damage')
            parts = [item(CALM, 'Not struck', intact), item(SCAR, 'Destroyed, uninhabitable', destroyed)];
        if (layer === 'observed_hits') {
            const n = f.homes.filter((h) => (field.values.get(h.id) || 0) === 0).length;
            parts = [item(CALM, 'Never struck', n), ramp(PURPLES, '1 hit', `${field.max} hits`)];
        }
        if (layer === 'exposure') {
            if (field.values.size) {
                const n = f.homes.filter((h) => field.values.get(h.id) <= field.floor).length;
                parts = [
                    item(CALM, 'Under 1% per period', n),
                    ramp(PURPLES, '1%', field.format(field.max)),
                    corner(INK, 'Destroyed'),
                ];
            }
            else
                parts = [item(CALM, 'Not recorded')];
        }
        if (layer === 'income_field')
            parts = [ramp(CARAMELS, money(field.min), money(field.max)), corner(SCAR, 'Destroyed')];
        if (layer === 'value')
            parts = [ramp(CARAMELS, '$0', money(initialMax)), item(SCAR, 'Destroyed', destroyed)];
        if (layer === 'ownership' || layer === 'residence')
            parts = [
                item(SCAR, 'Destroyed', destroyed),
                ...(layer === 'residence' ? [item(CALM, 'No resident')] : []),
            ];
        if (layer === 'insurers' || layer === 'coverage') {
            const firmCount = (id) => layer === 'insurers'
                ? f.homes.filter((h) => !h.destroyed && data.insurance_assignments?.[h.id] === id).length
                : f.homes.filter((h) => {
                    const at = policyMap.get(h.id) || [];
                    return at.length && new Set(at.map((c) => c.firm)).size === 1 && at[0].firm === id;
                }).length;
            parts = f.firms.map((x) => item(firmColor(x.id), firmName(x.id), firmCount(x.id)));
            if (layer === 'coverage') {
                const none = f.homes.filter((h) => !h.destroyed && !(policyMap.get(h.id) || []).length).length, several = f.homes.filter((h) => new Set((policyMap.get(h.id) || []).map((c) => c.firm)).size > 1).length;
                parts.push(item(CALM, 'No active policy', none));
                if (several)
                    parts.push(item('#fffbf5', 'Several insurers', several));
            }
            parts.push(item(SCAR, 'Destroyed', destroyed));
        }
        if (f.events.length)
            parts.push(`<span class="lg"><i class="sw ring"></i>${focusEvent === null ? 'Struck this period' : 'Selected disaster'}</span>`);
        if (person)
            parts.push(`<span class="lg"><i class="sw line"></i>Selected person’s homes</span><span class="lg"><i class="sw line dash"></i>Their residence</span>`);
        $('legend').innerHTML = parts.join('');
    }
    function homeTip(h) {
        const f = frames[period], layer = currentLayer(), field = fieldFor(layer), displaced = displacedResident(h), firm = data.insurance_assignments?.[h.id], at = covered(f).filter((c) => c.home === h.id);
        const rows = [
            h.destroyed ? 'Destroyed, uninhabitable' : `Value ${money(h.value)}`,
            `Owner ${h.owner}`,
        ];
        const neighbors = f.homes.filter((x) => x.position.join(',') === h.position.join(','));
        rows.push(`Neighborhood mean value ${money(neighbors.reduce((n, x) => n + Number(x.value), 0) / neighbors.length)}`);
        rows.push(h.resident !== null
            ? `Resident ${h.resident}`
            : displaced !== null
                ? `Resident ${displaced} displaced`
                : 'No resident');
        if (field && field.values.has(h.id))
            rows.push(`${field.label}: ${field.format(field.values.get(h.id))}`);
        if (['coverage', 'insurers'].includes(layer)) {
            rows.push(`Assigned to ${firm ? firmName(firm) : 'no insurer'}`);
            rows.push(at.length
                ? at.map((c) => `${c.product} with ${firmName(c.firm)}`).join(', ')
                : 'No active policy');
        }
        return `<b>Home ${h.id}</b><div class="sub">Row ${h.position[0]}, column ${h.position[1]}, ${regionSize(h) === 1 ? '1 home' : `${regionSize(h)} homes`} in this neighborhood</div>${rows.map((r) => `<div>${r}</div>`).join('')}`;
    }
    $('grid').onpointerover = (e) => {
        const b = e.target.closest('[data-home]');
        if (!b)
            return;
        const h = frames[period].homes.find((x) => x.id === Number(b.dataset.home));
        showTip(homeTip(h), e.clientX, e.clientY);
    };
    $('grid').onpointermove = (e) => {
        if (!$('tip').hidden && e.target.closest('[data-home]'))
            showTip($('tip').innerHTML, e.clientX, e.clientY);
    };
    $('grid').onpointerleave = hideTip;
    function render() {
        $('worldName').textContent = worldBlurbs[worldName] ?? `“${worldName}” world`;
        updateHeader();
        document
            .querySelectorAll('[data-world]')
            .forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.world === worldName)));
        const f = frames[period], id = selectedId, person = selectedKind === 'person', active = panelTab === 'people' && selectedId !== null, layer = currentLayer(), policies = covered(f), policyMap = byHome(policies);
        document
            .querySelectorAll('[data-tab]')
            .forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.tab === panelTab ||
            (b.dataset.tab === 'timeline' &&
                feedTabs[panelTab] &&
                !b.closest('.timeline-filters')))));
        $('globalPanel').hidden = panelTab !== 'overview';
        $('feedPanel').hidden = !feedTabs[panelTab];
        $('pickPrompt').hidden = panelTab !== 'people' || active;
        $('agentBody').hidden = !active;
        $('grid').classList.add('selecting');
        document.querySelectorAll('[data-firm]').forEach((b) => {
            const firmId = Number(b.dataset.firm), count = policies.filter((c) => c.firm === firmId).length;
            b.setAttribute('aria-pressed', String(!person && firmId === id));
            b.lastChild.textContent = `${firmName(firmId)}: ${count}`;
            b.setAttribute('aria-label', `${firmName(firmId)} insurance, ${count} current policies`);
        });
        $('period').value = String(period);
        $('periodLabel').value = String(period);
        $('periodMax').textContent = `of ${frames.length - 1}`;
        $('previous').disabled = period === 0;
        $('next').disabled = period === frames.length - 1;
        const chosen = f.events.filter((e) => focusEvent === null || e.id === focusEvent);
        const hits = new Set(chosen.flatMap((e) => e.cells.map((c) => c.join(','))));
        const owned = f.homes.filter((h) => h.owner === id), residence = f.homes.find((h) => h.resident === id);
        const relevant = policies.filter((c) => (person ? c.person === id : c.firm === id)), field = fieldFor(layer);
        const withValues = $('showValues').checked && printsValues(layer);
        $('valuesToggle').hidden = !printsValues(layer);
        $('lensTitle').textContent = lensNames[layer];
        $('lensWhen').textContent = `in “${experimentLabel()}” at period ${period}`;
        $('lensNote').textContent =
            (field ? field.note : lensNotes[layer]) +
                (person && id !== null
                    ? ` Person ${id}: ${owned.length} owned homes outlined, including destroyed homes. Press Esc to clear.`
                    : ' Click any home to inspect its owner and highlight their homes.');
        f.homes.forEach((h) => {
            let b = buttons.get(h.id), at = policyMap.get(h.id) || [];
            b.className = 'cell';
            b.tabIndex = 0;
            b.setAttribute('aria-pressed', String(homeId === h.id));
            const displaced = displacedResident(h);
            const assignedFirm = data.insurance_assignments?.[h.id];
            b.style.setProperty('--insurer-border', 'transparent');
            const look = cellLook(layer, h, at, field, withValues);
            b.style.background = look.bg;
            b.style.color = look.fg;
            if (look.mark) {
                b.classList.add('scarred');
                b.style.setProperty('--mark', look.mark);
            }
            if (person && id !== null && h.owner === id)
                b.classList.add('selected');
            if (active && !person) {
                const matches = layer === 'coverage'
                    ? at.some((c) => c.firm === id)
                    : assignedFirm === id || (!assignedFirm && at.some((c) => c.firm === id));
                if (matches) {
                    b.classList.add('insurer-match');
                    b.style.setProperty('--insurer-border', firmBorder(id));
                }
            }
            if (person && id !== null && h.resident === id && h.owner !== id)
                b.classList.add('residence');
            if (hits.has(h.position.join(',')))
                b.classList.add('hit');
            b.textContent = look.label;
            b.classList.toggle('long-label', look.label.length > 3);
            let label = `Home ${h.id}, row ${h.position[0]}, column ${h.position[1]}, owner ${h.owner}, resident ${h.resident ?? 'none'}${displaced !== null ? `, displaced resident ${displaced}` : ''}, ${h.destroyed ? 'destroyed' : 'intact'}, value ${money(h.value)}, assigned insurer ${assignedFirm ? firmName(assignedFirm) : 'none'}`;
            if (field)
                label += `, ${field.label}: ${field.values.has(h.id) ? field.format(field.values.get(h.id)) : 'not applicable'}`;
            b.setAttribute('aria-label', label);
        });
        const homesByRegion = new Map();
        for (const h of f.homes) {
            const key = h.position.join(',');
            if (!homesByRegion.has(key))
                homesByRegion.set(key, []);
            homesByRegion.get(key).push(h);
        }
        for (const block of blocks) {
            const summary = regionSummary(layer, homesByRegion.get(block.key), field), head = heads.get(block.key);
            head.textContent = summary.label;
            head.style.background = summary.bg;
            head.style.color = inkOn(summary.bg);
        }
        renderLegend(layer, field, f, policyMap, active && person);
        $('insurerFocus').hidden = !active || person;
        if (active && !person) {
            const count = $('grid').querySelectorAll('.insurer-match').length;
            $('insurerFocusLabel').textContent =
                `${firmName(id)} insurance: ${count} ${layer === 'coverage' ? 'currently covered' : 'assigned'} homes outlined.`;
        }
        if (active) {
            const selectedTransfers = f.transfers.filter((t) => person ? t.person === id || t.recipient === id : t.firm === id);
            let stats = [];
            if (person) {
                let p = f.people.find((p) => p.id === id), wealth = owned.reduce((n, h) => n + Number(h.value), 0);
                let roles = [];
                if (residence)
                    roles.push(residence.owner === id ? 'Owner-occupier' : 'Renter');
                else
                    roles.push(frames[0].homes.some((h) => h.resident === id) &&
                        f.homes.some((h) => displacedResident(h) === id)
                        ? 'Displaced, no current residence'
                        : 'No residence');
                if (owned.some((h) => h.resident !== null && h.resident !== id))
                    roles.push('landlord');
                if (owned.some((h) => h.destroyed))
                    roles.push('owns destroyed titles');
                $('agentTitle').textContent = `Person ${id}`;
                $('roles').textContent = roles.join(', ');
                stats = [
                    ['Cash', money(p.cash)],
                    ['Property wealth', money(wealth)],
                    ['Net position', money(Number(p.cash) + wealth)],
                    ['Annual external income', money(p.annual_income)],
                    ['Owned titles', owned.length],
                    ['Current policies', relevant.length],
                ];
            }
            else {
                let firm = f.firms.find((x) => x.id === id);
                $('agentTitle').textContent = `${firmName(id)} insurance`;
                $('roles').textContent =
                    (Number(firm.capital) > 0 ? 'Capital available' : 'Capital exhausted') +
                        (relevant.length ? '' : ', no current policies');
                const ts = frames
                    .slice(0, period + 1)
                    .flatMap((f) => f.transfers)
                    .filter((t) => t.firm === id);
                const sum = (kind, key) => ts.filter((t) => t.kind === kind).reduce((n, t) => n + Number(t[key] || 0), 0);
                stats = [
                    ['Capital', money(firm.capital)],
                    ['Current policies', relevant.length],
                    ['Premium receipts to date', money(sum('premium', 'amount'))],
                    ['Claims due to date', money(sum('claim', 'due'))],
                    ['Claims paid to date', money(sum('claim', 'amount'))],
                    ['Shortfall to date', money(sum('claim', 'shortfall'))],
                ];
            }
            $('portfolioHelp').hidden = person;
            $('stats').innerHTML = stats
                .map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`)
                .join('');
            renderChart();
            $('flows').innerHTML = selectedTransfers.length
                ? '<table><thead><tr><th>Flow</th><th>Amount</th><th>Details</th></tr></thead><tbody>' +
                    selectedTransfers
                        .map((t) => {
                        let direction = t.kind === 'premium'
                            ? person
                                ? 'Paid'
                                : 'Received'
                            : t.kind === 'claim'
                                ? person
                                    ? 'Received'
                                    : 'Paid'
                                : t.kind === 'rent'
                                    ? t.recipient === id
                                        ? 'Received'
                                        : 'Paid'
                                    : 'Received';
                        let detail = t.kind === 'claim'
                            ? `Due ${money(t.due)}; short ${money(t.shortfall)}`
                            : t.kind === 'rent'
                                ? `Person ${t.person} to ${t.recipient}; ${t.paid ? 'paid' : 'unpaid; requested ' + money(t.requested)}`
                                : t.home
                                    ? 'Home ' + t.home
                                    : 'External income';
                        return `<tr><td>${direction}: ${t.kind}</td><td>${money(t.amount)}</td><td>${detail}</td></tr>`;
                    })
                        .join('') +
                    '</tbody></table>'
                : '<p>No transfers for this agent in this period. Step to another period to inspect it.</p>';
        }
        const destroyed = f.homes.filter((h) => h.destroyed).length, displaced = f.people.length - f.homes.filter((h) => h.resident !== null).length;
        $('status').innerHTML = [
            ['Events', f.events.length, ''],
            ['Homes destroyed', `${destroyed} of ${f.homes.length}`, 'struck'],
            ['No residence', displaced, ''],
            ...(data.rates
                ? [['Expected rate', Number(data.rates[Math.max(0, period - 1)]).toFixed(3), '']]
                : []),
        ]
            .map(([k, v, c]) => `<div class="${c}"><dt>${k}</dt><dd>${v}</dd></div>`)
            .join('');
        $('home').hidden = homeId === null;
        if (active && homeId !== null)
            renderHome();
        if (panelTab === 'overview' && !$('snapshotMap').hidden)
            renderGlobal();
        if (!$('snapshotMap').hidden)
            renderFeed();
        renderResearch();
    }
    const metricNames = {
        annual_income: 'Annual external income',
        cash: 'Cash',
        property: 'Property value',
        net: 'Cash + property',
        homes: 'Owned home titles',
    };
    function plotKey(series) {
        return ('<div class="key-row">' +
            series
                .map((s) => `<span class="key"><i class="${s.dash ? 'dashed' : ''}" style="color:${s.color}"></i>${s.label}</span>`)
                .join('') +
            '</div>');
    }
    function diagnosticPlot(series, xLabel, marker = null) {
        const left = 45, top = 16, width = 450, height = 180;
        let svg = `<svg class="chart" viewBox="0 0 520 245" role="img" aria-label="${xLabel}; ${series.map((s) => s.label).join(', ')}">`;
        for (let i = 0; i <= 4; i++) {
            const y = top + height * (1 - i / 4);
            svg += `<line x1="${left}" x2="${left + width}" y1="${y}" y2="${y}" stroke="#e0d3c0"/><text x="${left - 8}" y="${y + 4}" text-anchor="end" font-size="13">${i / 4}</text>`;
        }
        for (const s of series) {
            let points = [];
            const flush = () => {
                if (points.length)
                    svg += `<polyline points="${points.join(' ')}" fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round" ${s.dash ? 'stroke-dasharray="5 4"' : ''}/>`;
                points = [];
            };
            s.values.forEach((v, i) => {
                if (v === null) {
                    flush();
                    return;
                }
                points.push(`${left + (width * i) / Math.max(1, s.values.length - 1)},${top + height * (1 - v)}`);
            });
            flush();
        }
        if (marker !== null)
            svg += `<line x1="${left + marker * width}" x2="${left + marker * width}" y1="${top}" y2="${top + height}" stroke="${INK}" stroke-dasharray="3 3"/>`;
        svg += `<text x="${left}" y="225" font-size="13">${xLabel}</text></svg>`;
        return svg + plotKey(series);
    }
    function outcomePlot(series, isMoney) {
        const left = 76, top = 16, width = 650, height = 220, max = Math.max(1, ...series.flatMap((s) => s.values)), x = (i) => left + (width * i) / Math.max(1, frames.length - 1), y = (v) => top + height * (1 - v / max);
        const compact = (v) => (isMoney ? '$' : '') +
            (v >= 1e6
                ? (v / 1e6).toFixed(1) + 'm'
                : v >= 1000
                    ? (v / 1000).toFixed(1) + 'k'
                    : v.toLocaleString('en-US', { maximumFractionDigits: 1 }));
        let svg = `<svg class="chart outcome-chart" viewBox="0 0 750 280" role="img" aria-label="${series.map((s) => s.label).join(', ')} over simulation periods">`;
        for (let j = 0; j <= 4; j++) {
            const v = (max * j) / 4;
            svg += `<line x1="${left}" x2="${left + width}" y1="${y(v)}" y2="${y(v)}" stroke="#e0d3c0"/><text x="${left - 8}" y="${y(v) + 4}" text-anchor="end" font-size="13">${compact(v)}</text>`;
        }
        series.forEach((s, index) => {
            svg += `<polyline fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round" ${index ? 'stroke-dasharray="' + (index === 1 ? '7 4' : '2 4') + '"' : ''} points="${s.values.map((v, i) => `${x(i)},${y(v)}`).join(' ')}"/><circle cx="${x(period)}" cy="${y(s.values[period])}" r="4" fill="${s.color}" stroke="#f8f2e8" stroke-width="2"/>`;
        });
        svg += `<line x1="${x(period)}" x2="${x(period)}" y1="${top}" y2="${top + height}" stroke="${INK}" stroke-dasharray="3 4"/><text x="${left}" y="265" font-size="13">Period 0</text><text x="${left + width}" y="265" text-anchor="end" font-size="13">Period ${frames.length - 1}</text></svg>`;
        const format = (v) => isMoney ? money(v) : v.toLocaleString('en-US', { maximumFractionDigits: 3 });
        return (svg +
            '<div class="key-row">' +
            series
                .map((s, i) => `<span class="key"><i class="${i ? 'dashed' : ''}" style="color:${s.color}"></i>${s.label} <b>${format(s.values[period])}</b></span>`)
                .join('') +
            '</div>');
    }
    const outcomeCache = new Map();
    function outcomesFor(name) {
        if (!outcomeCache.has(name))
            outcomeCache.set(name, summarizeOutcomes(worlds[name].frames, worlds[name].contracts));
        return outcomeCache.get(name);
    }
    function renderOutcomes() {
        const history = outcomesFor(worldName), metric = $('outcomeMetric').value;
        let series = [], note = '', isMoney = false;
        const seriesFor = (label, key, color) => ({
            label,
            color,
            values: history.map((row) => row[key]),
        });
        if (metric === 'housing') {
            series = [seriesFor('Displaced people', 'displaced', PURPLES[3])];
            note =
                'People who were initially housed and now have no residence. Destroyed-home counts coincide in these baseline worlds, so they are not drawn as a duplicate line.';
        }
        if (metric === 'coverage') {
            series = [
                seriesFor('Intact homes', 'intact', QUIET),
                seriesFor('Homes with active coverage', 'insured', INK),
            ];
            note =
                'Each home counts once, even with both building and renters coverage. Coverage means at least one in-term contract on an intact home; it does not guarantee full protection or claim payment.';
        }
        if (metric === 'claims') {
            series = [seriesFor('Claims due', 'due', INK), seriesFor('Claims paid', 'paid', '#16875a')];
            isMoney = true;
            note =
                'Cumulative contractual claims. The gap is unpaid claims, excluding uninsured losses and deductibles.';
        }
        if (metric === 'capital') {
            series = frames[0].firms.map((firm) => ({
                label: firmName(firm.id) + ' insurance',
                color: FIRM_LINES[firm.id] || INK,
                values: frames.map((frame) => Number(frame.firms.find((f) => f.id === firm.id).capital)),
            }));
            isMoney = true;
            note =
                'Insurer capital after premiums and claims, including opening premiums at period zero. This is an outcome, not a learning reward.';
        }
        if (metric === 'disasters') {
            series = [seriesFor('Observed events', 'events', PURPLES[3])];
            if (data.rates)
                series.push({
                    label: 'Expected events',
                    color: PURPLES[2],
                    values: frames.map((f, i) => (i === 0 ? 0 : data.rates[i - 1])),
                });
            note =
                'Whole-world counts per period. Expected rates are Poisson means, not cumulative totals. Period zero precedes disaster exposure.';
        }
        $('outcomePlot').innerHTML = outcomePlot(series, isMoney);
        $('outcomeNote').textContent = note;
        const format = (v) => isMoney ? money(v) : v.toLocaleString('en-US', { maximumFractionDigits: 3 });
        bindTimeline($('outcomePlot'), 76, 650, 750, 16, 236, (i) => series.map((s) => `<div>${s.label} ${format(s.values[i])}</div>`).join(''));
    }
    function histogramPlot(values, isMoney) {
        const { counts, step } = histogramBins(values), max = Math.max(1, ...counts), left = 45, top = 16, width = 450, height = 180;
        let svg = '<svg class="chart" viewBox="0 0 520 245" role="img" aria-label="People per value interval in the initial distribution">';
        for (let j = 0; j <= 4; j++) {
            const v = (max * j) / 4, y = top + height * (1 - j / 4);
            svg += `<line x1="${left}" x2="${left + width}" y1="${y}" y2="${y}" stroke="#e0d3c0"/><text x="${left - 6}" y="${y + 4}" text-anchor="end" font-size="13">${v.toLocaleString('en-US', { maximumFractionDigits: 1 })}</text>`;
        }
        const format = (v) => isMoney ? money(v) : v.toLocaleString('en-US', { maximumFractionDigits: 1 });
        counts.forEach((count, i) => {
            const barHeight = (height * count) / max;
            svg += `<rect x="${left + (i * width) / counts.length + 2}" y="${top + height - barHeight}" width="${width / counts.length - 4}" height="${barHeight}" rx="2" fill="${QUIET}"><title>${format(i * step)} to ${format((i + 1) * step)}: ${count} people</title></rect>`;
        });
        svg += `<text x="${left}" y="225" font-size="13">0</text><text x="${left + width}" y="225" text-anchor="end" font-size="13">${format(step * counts.length)}</text></svg>`;
        return svg;
    }
    /* Timeline ribbon: bars count events per period; the strip below deepens as homes are lost. */
    /* Admin console logs. Rent is grouped per period because there are thousands of payments. */
    const logCache = new Map(), feedTabs = { timeline: 1, disasters: 1, insurance: 1, ledger: 1, trades: 1 };
    function logFor(name) {
        if (!logCache.has(name))
            logCache.set(name, buildLog(worlds[name].frames));
        return logCache.get(name);
    }
    const ledgerCache = new Map(), groupCache = new Map();
    function ledgerFor(name, kind) {
        const key = name + ':' + kind;
        if (!ledgerCache.has(key)) {
            const all = kind === 'all'
                ? ledgerRows(worlds[name].frames)
                : ledgerFor(name, 'all').filter((row) => matchesKind(row.transfer, kind));
            ledgerCache.set(key, all);
        }
        return ledgerCache.get(key);
    }
    function groupsFor(name) {
        if (!groupCache.has(name))
            groupCache.set(name, worlds[name].frames.flatMap((frame, i) => ledgerGroups(frame, i)));
        return groupCache.get(name);
    }
    const compactCount = (n) => n >= 10000 ? (n / 1000).toFixed(1) + 'k' : n.toLocaleString('en-US');
    const replyHtml = (r) => `<div class="reply${r.alert ? ' alert' : ''}"><span>${r.title}${r.detail ? `<span class="detail">${r.detail}</span>` : ''}</span><span>${r.amount !== undefined ? money(r.amount) : ''}</span></div>`;
    function messageHtml(m) {
        const tone = `${m.strike ? ' strike' : ''}${m.alert ? ' alert' : ''}`, body = `<span><b>${m.title}</b>${m.detail ? `<span class="detail">${m.detail}</span>` : ''}</span><span class="amount">${m.amount !== undefined ? money(m.amount) : ''}</span>`;
        const replies = m.replies ?? m.rows?.map(describeTransfer);
        if (!replies)
            return `<div class="msg plain${tone}">${body}</div>`;
        const open = openThreads.has(m.key), selected = m.event !== undefined && focusEvent === m.event && m.period === period;
        return `<details class="msg${tone}${selected ? ' selected' : ''}" data-key="${m.key}"${m.event !== undefined ? ` data-event="${m.event}" data-period="${m.period}"` : ''}${open ? ' open' : ''}><summary>${body}</summary>${open ? `<div class="thread">${replies.map(replyHtml).join('')}</div>` : ''}</details>`;
    }
    // Build every stop once, including quiet periods, before playback begins.
    function sectionsHtml(messages, showGaps, periodCount) {
        const count = periodCount ?? (messages.length ? Math.max(...messages.map((m) => m.period)) + 1 : 0);
        const groups = new Map();
        for (const message of messages) {
            if (!groups.has(message.period))
                groups.set(message.period, []);
            groups.get(message.period).push(message);
        }
        const html = Array.from({ length: count }, (_, p) => {
            const events = groups.get(p) || [];
            return `<li class="day" data-stop="${p}"><button class="day-mark" data-jump="${p}" aria-label="Go to period ${p}"><span class="period-node" aria-hidden="true"></span><span>Period ${p}</span><span class="note" hidden>On the map</span></button><ol class="period-events">${events.length ? events.map((m) => `<li class="timeline-event">${messageHtml(m)}</li>`).join('') : `<li class="quiet-stop">${p === 0 ? 'Initial state' : showGaps ? 'No disasters this period' : 'No events in this view'}</li>`}</ol></li>`;
        }).join('');
        return {
            html: html
                ? `<ol class="event-timeline" aria-label="Full recorded timeline">${html}</ol>`
                : '',
            total: count,
        };
    }
    let mountedTimelineKey = null, playheadFrame = null, lastPlayheadPeriod = null;
    function syncPlayhead() {
        if (playheadFrame !== null)
            cancelAnimationFrame(playheadFrame);
        playheadFrame = requestAnimationFrame(() => {
            playheadFrame = null;
            if ($('feedPanel').hidden || $('snapshotView').hidden || $('snapshotMap').hidden)
                return;
            const route = $('feed').querySelector('.timeline-route'), stop = $('feed').querySelector(`[data-jump="${period}"]`);
            if (!route || !stop)
                return;
            const marker = route.querySelector('.timeline-train'), node = stop.querySelector('.period-node');
            // Read geometry together, then update only the small marker's transform.
            const routeRect = route.getBoundingClientRect(), nodeRect = node.getBoundingClientRect(), body = $('panelBody'), bodyRect = body.getBoundingClientRect();
            const headerHeight = document.querySelector('.feed-head').offsetHeight;
            const top = nodeRect.top - routeRect.top, changed = lastPlayheadPeriod !== period;
            const follow = $('followTimeline').checked &&
                changed &&
                (nodeRect.top < bodyRect.top + headerHeight + 20 || nodeRect.bottom > bodyRect.bottom - 30);
            const scrollTarget = body.scrollTop + nodeRect.top - bodyRect.top - headerHeight - 48;
            route.querySelectorAll('[data-jump]').forEach((button) => {
                const current = Number(button.dataset.jump) === period;
                if (current)
                    button.setAttribute('aria-current', 'step');
                else
                    button.removeAttribute('aria-current');
                button.querySelector('.note').hidden = !current;
            });
            route
                .querySelectorAll('.msg.selected')
                .forEach((message) => message.classList.remove('selected'));
            if (focusEvent !== null)
                route
                    .querySelector(`[data-event="${focusEvent}"][data-period="${period}"]`)
                    ?.classList.add('selected');
            marker.style.transform = `translateY(${top}px)`;
            marker.hidden = false;
            if (follow)
                body.scrollTo({
                    top: Math.max(0, scrollTarget),
                    behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
                });
            lastPlayheadPeriod = period;
        });
    }
    const timelineCache = new Map();
    function timelineFor(name) {
        if (!timelineCache.has(name))
            timelineCache.set(name, timelineEvents(worlds[name].frames));
        return timelineCache.get(name);
    }
    function renderFeed() {
        const log = logFor(worldName), seen = (key) => log[key].filter((row) => row.period <= period), tally = (rows) => rows.reduce((n, row) => n + (row.count || 0), 0);
        for (const key of ['disasters', 'insurance'])
            document.querySelector(`[data-tab=${key}] .count`).textContent = String(tally(seen(key)));
        document.querySelector('[data-tab=ledger] .count').textContent = compactCount(countThrough(ledgerFor(worldName, 'all'), period));
        document.querySelector('[data-tab=trades] .count').textContent = '0';
        if (!feedTabs[panelTab])
            return;
        $('ledgerFilter').hidden = panelTab !== 'ledger';
        document
            .querySelectorAll('[data-kind]')
            .forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.kind === ledgerKind)));
        if (panelTab === 'trades') {
            $('feedHead').textContent = 'No trades to show.';
            $('feed').innerHTML =
                '<p class="muted">This simulation does not record trades yet. People under the fixed baseline policies can only pay rent or wait.</p>';
            return;
        }
        let messages;
        if (panelTab === 'timeline') {
            messages = timelineFor(worldName);
            $('feedHead').textContent =
                `Period ${period} of ${frames.length - 1} · ${messages.length} recorded event groups.`;
        }
        else if (panelTab === 'ledger') {
            const rows = ledgerFor(worldName, ledgerKind), end = countThrough(rows, period);
            let moved = 0;
            for (let i = 0; i < end; i++) {
                const t = rows[i].transfer;
                moved += Number(ledgerKind === 'unpaid' ? t.requested : t.amount);
            }
            $('feedHead').textContent =
                `${end.toLocaleString('en-US')} transactions through period ${period}, ${money(moved)} ${ledgerKind === 'unpaid' ? 'missed' : 'paid'}.`;
            messages = groupsFor(worldName).filter((g) => ledgerKind === 'all' ||
                g.kind === ledgerKind ||
                (ledgerKind === 'rent' && g.kind === 'unpaid'));
        }
        else {
            messages = log[panelTab];
            const current = seen(panelTab), sum = (key) => current.reduce((n, row) => n + (row[key] || 0), 0);
            $('feedHead').textContent = {
                disasters: `${tally(current)} disasters through period ${period}, ${sum('lost')} homes lost, ${sum('claims')} claims.`,
                insurance: `${tally(current)} claims through period ${period}, ${money(sum('due'))} due, ${money(sum('short'))} unpaid.`,
            }[panelTab];
        }
        const key = worldName + ':' + panelTab + ':' + ledgerKind;
        if (mountedTimelineKey !== key || !$('feed').querySelector('.timeline-route')) {
            const { html } = sectionsHtml(messages, panelTab === 'disasters', frames.length);
            $('feed').innerHTML =
                `<div class="timeline-route"><span class="timeline-train" aria-hidden="true" hidden></span>${html}</div>`;
            mountedTimelineKey = key;
            lastPlayheadPeriod = null;
        }
        syncPlayhead();
    }
    $('feed').onclick = (e) => {
        const mark = e.target.closest('[data-jump]');
        if (mark) {
            const target = mark.dataset.jump;
            stopPlay();
            goTo(Number(target), null);
            document
                .querySelector(`[data-jump="${target}"]`)
                ?.focus({ preventScroll: true });
            return;
        }
        const summary = e.target.closest('summary');
        if (!summary)
            return;
        e.preventDefault();
        const message = summary.parentElement, key = message.dataset.key;
        if (openThreads.has(key))
            openThreads.delete(key);
        else
            openThreads.add(key);
        const entry = (panelTab === 'timeline'
            ? timelineFor(worldName)
            : panelTab === 'ledger'
                ? groupsFor(worldName)
                : logFor(worldName)[panelTab]).find((row) => row.key === key);
        if (entry)
            message.outerHTML = messageHtml(entry);
        if (message.dataset.event) {
            stopPlay();
            goTo(Number(message.dataset.period), Number(message.dataset.event));
        }
        else
            syncPlayhead();
        document
            .querySelector(`[data-key="${key}"] summary`)
            ?.focus({ preventScroll: true });
    };
    $('ledgerFilter').onclick = (e) => {
        const b = e.target.closest('[data-kind]');
        if (!b)
            return;
        ledgerKind = b.dataset.kind;
        renderFeed();
        $('panelBody').scrollTop = 0;
    };
    $('followTimeline').onchange = () => {
        lastPlayheadPeriod = null;
        syncPlayhead();
    };
    new ResizeObserver(() => {
        if (!$('feedPanel').hidden)
            syncPlayhead();
    }).observe($('feed'));
    document.addEventListener('visibilitychange', () => {
        if (document.hidden)
            stopPlay();
    });
    /* Overview: the graphs worth watching while a simulation runs. */
    const giniCache = new Map();
    function giniFor(name) {
        if (!giniCache.has(name))
            giniCache.set(name, worlds[name].frames.map((frame) => distribution(metricValues(frame, 'net')).gini));
        return giniCache.get(name);
    }
    function renderGlobal() {
        const history = outcomesFor(worldName), total = frames[0].homes.length, column = (key) => history.map((row) => row[key]), gini = giniFor(worldName);
        const panels = [
            {
                title: 'Homes destroyed',
                labels: ['Destroyed'],
                series: [history.map((row) => total - row.intact)],
                colors: [SCAR],
            },
            {
                title: 'Disasters per period',
                labels: ['Observed', 'Expected'],
                series: [
                    column('events'),
                    frames.map((f, i) => (i === 0 ? 0 : (data.rates?.[i - 1] ?? 0))),
                ],
                colors: [PURPLES[3], PURPLES[2]],
            },
            {
                title: 'Homes with active coverage',
                labels: ['Covered'],
                series: [column('insured')],
                colors: [INK],
            },
            {
                title: 'Claims to date',
                labels: ['Due', 'Paid'],
                series: [column('due'), column('paid')],
                colors: [INK, '#16875a'],
                money: true,
            },
            {
                title: 'Insurer capital',
                labels: frames[0].firms.map((x) => firmName(x.id)),
                series: frames[0].firms.map((x) => frames.map((frame) => Number(frame.firms.find((y) => y.id === x.id).capital))),
                colors: frames[0].firms.map((x) => FIRM_LINES[x.id] || INK),
                money: true,
            },
        ];
        if (gini.every((v) => v !== null))
            panels.push({
                title: 'Inequality in cash + property',
                labels: ['Gini'],
                series: [gini],
                colors: [INK],
            });
        const host = $('globalPanel');
        if (host.children.length !== panels.length)
            host.innerHTML = panels
                .map(() => '<div class="pulse"><h3></h3><div class="key-row"></div><div class="plot"></div></div>')
                .join('');
        panels.forEach((d, n) => {
            const box = host.children[n], format = (v) => d.money ? money(v) : Number(v).toLocaleString('en-US', { maximumFractionDigits: 3 });
            box.querySelector('h3').textContent = d.title;
            box.querySelector('.key-row').innerHTML = d.labels
                .map((label, i) => `<span class="key"><i class="${i ? 'dashed' : ''}" style="color:${d.colors[i]}"></i>${label} <b>${format(d.series[i][period])}</b></span>`)
                .join('');
            const plot = box.querySelector('.plot');
            plot.innerHTML = chart(d.series, d.labels, d.money, d.colors, 150);
            bindTimeline(plot, 84, 512, 620, 12, 118, (i) => d.labels.map((label, j) => `<div>${label} ${format(d.series[j][i])}</div>`).join(''));
        });
    }
    function renderRibbon() {
        const history = outcomesFor(worldName), n = history.length, total = frames[0].homes.length, peak = Math.max(1, ...history.map((row) => row.events));
        let svg = '';
        history.forEach((row, i) => {
            if (row.events) {
                const height = (30 * row.events) / peak;
                svg += `<rect x="${i - 0.36}" y="${34 - height}" width=".72" height="${height}" fill="${SCAR}"/>`;
            }
            const lost = total - row.intact;
            svg += `<rect x="${i - 0.5}" y="38" width="1" height="14" shape-rendering="crispEdges" fill="${lost ? PURPLES[bin(lost / total)] : CALM}"/>`;
        });
        const plot = $('ribbonPlot');
        plot.setAttribute('viewBox', `0 0 ${Math.max(1, n - 1)} 52`);
        plot.setAttribute('preserveAspectRatio', 'none');
        plot.innerHTML = svg;
    }
    $('ribbon').onpointermove = (e) => {
        const r = $('ribbon').getBoundingClientRect(), i = clamp(Math.round(((e.clientX - r.left) / r.width) * (frames.length - 1)), 0, frames.length - 1), row = outcomesFor(worldName)[i];
        showTip(`<b>Period ${i}</b><div>${row.events} ${row.events === 1 ? 'event' : 'events'}</div><div>${frames[0].homes.length - row.intact} homes destroyed so far</div>`, e.clientX, e.clientY);
    };
    $('ribbon').onpointerleave = hideTip;
    /* Small multiples: one plate per field, and one per world. */
    const atlasPlates = [
        ['damage', 'Damage', 'Gray: not struck. Purple: destroyed.'],
        ['observed_hits', 'Observed hits', 'Gray: never struck. Darker: struck more often.'],
        ['exposure', 'Hit probability', 'Gray: under 1% per period. Darker: riskier.'],
        ['value', 'Home values', 'Darker caramel: higher value. Purple: destroyed.'],
        [
            'income_field',
            'Initial resident income',
            'Darker caramel: higher income. Corner: destroyed.',
        ],
        ['coverage', 'Coverage', 'Insurer colors. Gray: no active policy.'],
    ];
    function miniMap(homes, fill, name = worldName) {
        const [rows, columns] = shape;
        return `<svg viewBox="0 0 ${columns} ${rows}" aria-hidden="true">${homes
            .map((h) => {
            const look = fill(h), s = spots.get(h.id), corner = Math.min(s.w, s.h) * 0.3;
            const selected = name === worldName &&
                selectedKind === 'person' &&
                selectedId !== null &&
                h.owner === selectedId;
            return `<g data-home="${h.id}"><rect class="${selected ? 'mini-owned' : ''}" x="${s.x}" y="${s.y}" width="${s.w}" height="${s.h}" fill="${look.bg}"/>${look.mark ? `<path d="M${s.x + s.w} ${s.y}v${corner}h${-corner}z" fill="${look.mark}"/>` : ''}</g>`;
        })
            .join('')}${blocks.map((b) => `<rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" fill="none" pointer-events="none" stroke="var(--page)" stroke-width=".07"/>`).join('')}</svg>`;
    }
    atlasPlates.forEach(([layer, title, caption]) => {
        const b = document.createElement('button');
        b.className = 'plate';
        b.dataset.field = layer;
        b.setAttribute('aria-label', `Open ${title} on the world map`);
        b.innerHTML = `<span class="mini"></span><strong>${title}</strong><span class="cap">${caption}</span>`;
        b.onclick = (event) => {
            const home = event.target.closest('[data-home]');
            setLayer(layer);
            if (home)
                selectHome(Number(home.dataset.home));
            navigateView('map');
            if (home)
                buttons.get(Number(home.dataset.home))?.focus({ preventScroll: true });
        };
        $('atlas').append(b);
    });
    Object.keys(worlds).forEach((name) => {
        const b = document.createElement('button');
        b.className = 'plate';
        b.dataset.plateWorld = name;
        b.innerHTML = `<span class="mini"></span><strong>Dev ${name}</strong><span class="cap"></span>`;
        b.onclick = (event) => {
            const home = event.target.closest('[data-home]');
            setWorld(name);
            if (home)
                selectHome(Number(home.dataset.home));
            navigateView(home ? 'map' : view === 'research' ? 'research' : 'map');
            if (home)
                buttons.get(Number(home.dataset.home))?.focus({ preventScroll: true });
        };
        $('worldPlates').append(b);
    });
    $('worldCompare').hidden = Object.keys(worlds).length < 2;
    function renderPlates() {
        const f = frames[period], policyMap = byHome(covered(f));
        document.querySelectorAll('#atlas .plate').forEach((b) => {
            const layer = b.dataset.field, field = fieldFor(layer);
            b.querySelector('.mini').innerHTML = miniMap(f.homes, (h) => cellLook(layer, h, policyMap.get(h.id) || [], field));
        });
        document.querySelectorAll('#worldPlates .plate').forEach((b) => {
            const name = b.dataset.plateWorld, w = worlds[name], frame = w.frames[Math.min(period, w.frames.length - 1)], lost = frame.homes.filter((h) => h.destroyed).length;
            b.setAttribute('aria-pressed', String(name === worldName));
            b.setAttribute('aria-label', `Open Dev ${name}: ${lost} of ${frame.homes.length} homes destroyed`);
            b.querySelector('.mini').innerHTML = miniMap(frame.homes, (h) => ({
                bg: h.destroyed ? SCAR : CALM,
            }), name);
            b.querySelector('.cap').textContent =
                `${lost} of ${frame.homes.length} homes destroyed by period ${frame.period}`;
        });
    }
    const researchCache = new Map();
    function renderResearch() {
        if ($('researchView').hidden)
            return;
        renderPlates();
        renderOutcomes();
        const metric = $('researchMetric').value, format = (v) => (metric === 'homes' ? Number(v).toLocaleString() : money(v)), f = frames[period];
        const key = worldName + ':' + metric;
        if (!researchCache.has(key))
            researchCache.set(key, frames.map((frame) => distribution(metricValues(frame, metric))));
        const history = researchCache.get(key), initial = metricValues(frames[0], metric), current = metricValues(f, metric), before = new Map(initial.map((p) => [p.id, p.value])), initialRanks = ranks(initial), currentRanks = ranks(current), summary = history[period];
        $('metricNote').textContent = {
            annual_income: 'Fixed annual external income, excluding rent and claims; this distribution does not change under the current policies.',
            cash: 'Cash after transfers. Period zero already includes opening premiums.',
            property: 'Sum of current home values by owner; destroyed titles remain owned but have zero modeled value.',
            net: 'Cash plus current property value. This is a modeled net position, not a Q-learning reward.',
            homes: 'All owned titles, including destroyed homes. No trading or rebuilding occurs under current policies.',
        }[metric];
        const gini = (d) => (d.gini === null ? 'Unavailable' : d.gini.toFixed(3));
        $('distributionStats').innerHTML = [
            ['Period 0 total', format(history[0].total)],
            ['Current total', format(summary.total)],
            ['Current mean', format(summary.total / current.length)],
            ['Period 0 Gini', gini(history[0])],
            ['Current Gini', gini(summary)],
            ['People', current.length],
        ]
            .map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`)
            .join('');
        const curves = [
            { label: 'Equality', values: [0, 1], color: '#bdb0a0', dash: true },
        ];
        if (history[0].curve)
            curves.push({ label: 'Period 0', values: history[0].curve, color: QUIET, dash: true });
        if (summary.curve &&
            period !== 0 &&
            JSON.stringify(summary.curve) !== JSON.stringify(history[0].curve))
            curves.push({ label: `Period ${period}`, values: summary.curve, color: INK });
        const target = metric === 'annual_income'
            ? data.diagnostics?.income_lorenz
            : metric === 'homes'
                ? data.diagnostics?.ownership_lorenz
                : null;
        if (target)
            curves.push({
                label: 'Configured initial target',
                values: target,
                color: '#16875a',
                dash: true,
            });
        $('distributionPlot').innerHTML = diagnosticPlot(curves, 'Population share: 0 to 1');
        const fixed = ['annual_income', 'homes'].includes(metric);
        $('secondaryDistributionTitle').textContent = fixed
            ? 'Initial distribution: people per interval'
            : 'Inequality across periods';
        $('secondaryDistributionNote').textContent = fixed
            ? 'This measure is fixed in these baseline runs. The histogram shows its distribution instead of a flat time-series line. Intervals include the lower bound; the last also includes the maximum.'
            : 'Gini: 0 = equal, approaching 1 = concentrated. All-zero distributions are unavailable.';
        $('inequalityPlot').innerHTML = fixed
            ? histogramPlot(initial.map((p) => p.value), metric !== 'homes')
            : diagnosticPlot([{ label: 'Gini', values: history.map((d) => d.gini), color: INK }], `Periods: 0 to ${frames.length - 1}`, period / Math.max(1, frames.length - 1));
        if (!fixed)
            bindTimeline($('inequalityPlot'), 45, 450, 520, 16, 196, (i) => `<div>Gini ${gini(history[i])}</div>`);
        const residents = new Set(f.homes.map((h) => h.resident).filter((id) => id !== null)), displaced = new Set(f.homes.map(displacedResident).filter((id) => id !== null));
        $('leaderboard').innerHTML = [...current]
            .sort((a, b) => b.value - a.value || a.id - b.id)
            .map((p) => {
            const change = p.value - before.get(p.id), rankChange = initialRanks.get(p.id) - currentRanks.get(p.id);
            return `<tr><td>${currentRanks.get(p.id)}</td><td><button data-person="${p.id}">Person ${p.id}</button></td><td>${format(p.value)}</td><td>${format(before.get(p.id))}</td><td>${change > 0 ? '+' : ''}${format(change)}</td><td>${rankChange > 0 ? '↑ ' + rankChange : rankChange < 0 ? '↓ ' + -rankChange : '—'}</td><td>${residents.has(p.id) ? 'Housed' : displaced.has(p.id) ? 'Displaced' : 'No residence'}</td></tr>`;
        })
            .join('');
        $('leaderboard')
            .querySelectorAll('[data-person]')
            .forEach((b) => (b.onclick = () => {
            showView('map');
            selectPerson(Number(b.dataset.person));
        }));
        const policies = covered(f), transfers = frames.slice(0, period + 1).flatMap((frame) => frame.transfers), sum = (kind, key, firm = undefined) => transfers
            .filter((t) => t.kind === kind && (firm === undefined || t.firm === firm))
            .reduce((n, t) => n + Number(t[key] || 0), 0);
        $('policyStats').innerHTML = [
            ['Displaced people', displaced.size],
            ['Destroyed homes', f.homes.filter((h) => h.destroyed).length],
            ['Homes with current coverage', new Set(policies.map((p) => p.home)).size],
            ['Current contracts', policies.length],
            ['Unpaid claims to date', money(sum('claim', 'shortfall'))],
            ['Unpaid rent this period', f.transfers.filter((t) => t.kind === 'rent' && !t.paid).length],
        ]
            .map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`)
            .join('');
        const actions = f.actions;
        $('actionStats').textContent = actions
            ? `Actions in period ${period}: ${actions.filter((a) => a.action === 'Wait').length} wait; ${actions.filter((a) => a.action === 'PayRent').length} pay-rent attempts; ${actions.filter((a) => a.action === 'PayRent' && a.paid === false).length} unsuccessful payments.`
            : 'Action records are unavailable in this snapshot.';
        $('insurerLeaderboard').innerHTML = f.firms
            .map((firm) => `<tr><td><button data-inspect-firm="${firm.id}">${firmName(firm.id)}</button></td><td>${money(firm.capital)}</td><td>${policies.filter((c) => c.firm === firm.id).length}</td><td>${money(sum('premium', 'amount', firm.id))}</td><td>${money(sum('claim', 'due', firm.id))}</td><td>${money(sum('claim', 'amount', firm.id))}</td><td>${money(sum('claim', 'shortfall', firm.id))}</td></tr>`)
            .join('');
        $('insurerLeaderboard')
            .querySelectorAll('[data-inspect-firm]')
            .forEach((b) => (b.onclick = () => {
            showView('map');
            panelTab = 'people';
            selectedKind = 'firm';
            selectedId = Number(b.dataset.inspectFirm);
            render();
        }));
        const settings = data.diagnostics?.settings;
        $('setupFacts').textContent = settings
            ? `Seed ${data.configuration.seed}. Reference price ${money(settings.reference_price)}. Log-price spread ${settings.price_spread}. Spread among homes in a neighborhood ${settings.home_price_spread}. Price smoothing ${settings.price_length_scale}. Placement noise ${settings.placement_noise}. Risk contrast ${settings.risk_contrast}. Risk smoothing ${settings.risk_length_scale}. Mean homes per neighborhood ${settings.homes_per_region}. Neighborhood size contrast ${settings.region_size_contrast}. Neighborhood size smoothing ${settings.region_size_length_scale}. Disaster radius ⌊Y⌋ neighborhoods, with Y Tweedie of mean ${settings.radius_mean} and dispersion ${settings.radius_dispersion}.`
            : 'Initialization metadata is unavailable in this snapshot. Recorded price and income fields remain inspectable.';
    }
    $('researchMetric').onchange = renderResearch;
    $('outcomeMetric').onchange = renderOutcomes;
    // One scale across periods and worlds, so a rising risk reads as darker rather than rescaled.
    function peakExposure() {
        let peak = 0;
        for (const w of Object.values(worlds)) {
            const field = w.diagnostics?.hit_probability_per_event;
            if (!field)
                continue;
            const rate = Math.max(0, ...(w.rates ?? [0]));
            peak = Math.max(peak, 1 - Math.exp(-rate * Math.max(...field.flat())));
        }
        return peak;
    }
    const exposureFloor = 0.01, exposurePeak = peakExposure();
    function fieldFor(layer) {
        const first = frames[0], values = new Map(), info = {
            values,
            label: '',
            note: '',
            format: (v) => Number(v).toLocaleString('en-US', { maximumFractionDigits: 3 }),
        };
        const names = {
            income_field: 'Initial resident annual income',
            exposure: 'Probability of at least one hit',
            observed_hits: 'Cumulative disaster hits',
        };
        if (!names[layer])
            return null;
        info.label = names[layer];
        if (layer === 'income_field')
            info.format = money;
        const exposure = data.diagnostics?.hit_probability_per_event;
        if (layer === 'exposure' && !exposure) {
            info.note =
                'This snapshot does not contain the research exposure field. Start a new experiment to record it.';
            info.floor = 0;
            info.max = 1;
            return info;
        }
        const income = new Map(first.people.map((p) => [p.id, Number(p.annual_income)])), hits = new Map(), allHits = new Map();
        if (layer === 'observed_hits')
            for (const [i, frame] of frames.entries())
                for (const event of frame.events)
                    for (const cell of event.cells) {
                        const key = cell.join(',');
                        allHits.set(key, (allHits.get(key) || 0) + 1);
                        if (i <= period)
                            hits.set(key, (hits.get(key) || 0) + 1);
                    }
        const rate = data.rates?.[Math.max(0, period - 1)] ?? 0;
        for (const home of first.homes) {
            const [row, col] = home.position;
            const value = layer === 'income_field'
                ? income.get(home.resident)
                : layer === 'observed_hits'
                    ? hits.get(home.position.join(',')) || 0
                    : 1 - Math.exp(-rate * exposure[row][col]);
            if (value !== undefined)
                values.set(home.id, value);
        }
        if (layer === 'exposure')
            info.format = (v) => (v * 100).toFixed(2) + '%';
        info.note = {
            income_field: 'Fixed annual income of the initial resident at each location, not current occupancy. A corner mark means that home has since been destroyed.',
            exposure: `Research-only probability of at least one hit in ${period === 0 ? 'the first exposure period' : `period ${period}`}, across every disaster zone that could reach the neighborhood (event rate ${rate.toFixed(3)}). Same scale across periods and worlds. Gray means under 1%. A corner mark means the home has already been destroyed.`,
            observed_hits: 'All sampled disaster zones through the selected period, including repeated hits on destroyed homes. This counts exposure, not new losses. Gray means never struck.',
        }[layer];
        info.min = Math.min(...values.values());
        info.max = Math.max(...values.values());
        if (layer === 'exposure') {
            info.floor = exposureFloor;
            info.min = 0;
            info.max = Math.max(exposureFloor * 2, exposurePeak);
        }
        if (layer === 'observed_hits') {
            info.floor = 0;
            info.min = 0;
            info.max = Math.max(1, ...allHits.values());
        }
        return info;
    }
    // The map and the persistent timeline playhead share the same recorded period.
    function goTo(next, event = null) {
        period = clamp(next, 0, frames.length - 1);
        focusEvent = event;
        render();
    }
    const playIcon = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 2v12l10-6z"/></svg>', pauseIcon = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 2h4v12H3zM9 2h4v12H9z"/></svg>';
    let player = null;
    function stopPlay() {
        if (player === null)
            return;
        clearInterval(player);
        player = null;
        $('play').innerHTML = playIcon;
        $('play').setAttribute('aria-pressed', 'false');
        $('play').setAttribute('aria-label', 'Play through periods');
        $('status').setAttribute('aria-live', 'polite');
    }
    function startPlay() {
        if (period >= frames.length - 1)
            goTo(0);
        $('play').innerHTML = pauseIcon;
        $('play').setAttribute('aria-pressed', 'true');
        $('play').setAttribute('aria-label', 'Pause');
        $('status').setAttribute('aria-live', 'off');
        player = setInterval(() => {
            if (period >= frames.length - 1) {
                stopPlay();
                return;
            }
            goTo(period + 1);
        }, 240);
    }
    $('play').innerHTML = playIcon;
    $('play').onclick = () => (player === null ? startPlay() : stopPlay());
    $('period').oninput = () => {
        stopPlay();
        goTo(Number($('period').value));
    };
    $('previous').onclick = () => {
        stopPlay();
        goTo(period - 1);
    };
    $('next').onclick = () => {
        stopPlay();
        goTo(period + 1);
    };
    // Left, right, and space drive the timeline unless a control needs those keys for itself.
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' &&
            !$('experimentDialog').open &&
            (view === 'map' || view === 'research')) {
            clearSelection();
            setTab(panelTab === 'people' ? 'overview' : panelTab);
            return;
        }
        if ($('experimentDialog').open ||
            view === 'start' ||
            view === 'loading' ||
            e.altKey ||
            e.ctrlKey ||
            e.metaKey ||
            e.target.closest('input,select,textarea'))
            return;
        if (e.key === 'ArrowLeft') {
            stopPlay();
            goTo(period - 1);
            e.preventDefault();
        }
        if (e.key === 'ArrowRight') {
            stopPlay();
            goTo(period + 1);
            e.preventDefault();
        }
        if (e.key === ' ' && e.target === document.body) {
            player === null ? startPlay() : stopPlay();
            e.preventDefault();
        }
    });
    document
        .querySelectorAll('input[name=layer]')
        .forEach((input) => (input.onchange = render));
    $('showValues').onchange = render;
    renderRibbon();
    render();
    initializeLibrary();
}

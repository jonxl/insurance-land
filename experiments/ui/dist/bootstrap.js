import { initializeDiagnostics } from './app.js';
import { loadRecording } from './recording.js';
export async function startViewer({ document = globalThis.document, location = globalThis.location, load = loadRecording, initialize = initializeDiagnostics, } = {}) {
    const status = document.getElementById('appStatus');
    const message = document.getElementById('appStatusMessage');
    const retry = document.getElementById('retryLoad');
    try {
        if (location.protocol === 'file:') {
            throw new Error('Start the command center with uv run python -m experiments.command_center and open http://127.0.0.1:8000 to view this recording.');
        }
        const bundle = await load(new URL('assets/world-history.json', location.href));
        document.body.removeAttribute('data-loading');
        status.hidden = true;
        initialize(bundle);
        return true;
    }
    catch (error) {
        document.body.setAttribute('data-loading', '');
        status.hidden = false;
        status.setAttribute('role', 'alert');
        message.textContent = error instanceof Error ? error.message : 'Could not open the experiment.';
        retry.hidden = false;
        retry.onclick = () => location.reload();
        return false;
    }
}
if (typeof document !== 'undefined')
    startViewer();

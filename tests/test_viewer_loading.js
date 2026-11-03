import { test } from 'bun:test';
import assert from 'node:assert/strict';
import { loadRecording } from '../experiments/ui/dist/recording.js';
import { startViewer } from '../experiments/ui/dist/bootstrap.js';

const bundle = { default: 'Standard', worlds: { Standard: { frames: [{ period: 0 }] } } };

function page(href) {
  const nodes = new Map();
  const document = {
    body: {
      loading: true,
      removeAttribute() {
        this.loading = false;
      },
      setAttribute() {
        this.loading = true;
      },
    },
    getElementById(id) {
      if (!nodes.has(id)) nodes.set(id, { hidden: false, setAttribute() {} });
      return nodes.get(id);
    },
  };
  const location = {
    href,
    protocol: new URL(href).protocol,
    reload() {
      this.reloaded = true;
    },
  };
  return { document, location };
}

test('recording loader accepts bundled and single-world exports', async () => {
  for (const data of [bundle, { frames: [{ period: 0 }] }]) {
    assert.equal(
      await loadRecording('/recording', async () => ({ ok: true, json: async () => data })),
      data,
    );
  }
});

test('recording loader reports missing files and rejects empty or malformed snapshots', async () => {
  await assert.rejects(
    loadRecording('/missing', async () => ({ ok: false, status: 404 })),
    /HTTP 404/,
  );
  for (const data of [null, {}, { frames: [] }, { default: 'Missing', worlds: bundle.worlds }]) {
    await assert.rejects(
      loadRecording('/invalid', async () => ({ ok: true, json: async () => data })),
      /usable snapshots/,
    );
  }
  await assert.rejects(
    loadRecording('/invalid', async () => ({
      ok: true,
      json: async () => {
        throw new SyntaxError('Invalid JSON');
      },
    })),
    /Invalid JSON/,
  );
});

test('viewer resolves the recording relative to root and nested experiment pages', async () => {
  for (const path of ['/', '/diagnostics.html', '/runs/saved/diagnostics.html']) {
    const env = page('http://localhost:8000' + path + '?view=map');
    let initialized = false;
    const result = await startViewer({
      ...env,
      load: async (url) => {
        assert.equal(
          url.pathname,
          path.startsWith('/runs/')
            ? '/runs/saved/assets/world-history.json'
            : '/assets/world-history.json',
        );
        assert.equal(env.document.body.loading, true);
        return bundle;
      },
      initialize: (data) => {
        assert.equal(data, bundle);
        initialized = true;
      },
    });
    assert.equal(result, true);
    assert.equal(initialized, true);
    assert.equal(env.document.body.loading, false);
    assert.equal(env.document.getElementById('appStatus').hidden, true);
  }
});

test('failed loading keeps partial UI hidden and offers a reload', async () => {
  const env = page('http://localhost:8000/diagnostics.html');
  const result = await startViewer({
    ...env,
    load: async () => {
      throw new Error('Recording unavailable');
    },
    initialize: () => assert.fail('must not initialize without a recording'),
  });
  assert.equal(result, false);
  assert.equal(env.document.body.loading, true);
  assert.equal(
    env.document.getElementById('appStatusMessage').textContent,
    'Recording unavailable',
  );
  env.document.getElementById('retryLoad').onclick();
  assert.equal(env.location.reloaded, true);
});

test('direct file access explains how to serve the viewer', async () => {
  const env = page('file:///tmp/diagnostics.html');
  assert.equal(
    await startViewer({ ...env, load: () => assert.fail('must not fetch file URLs') }),
    false,
  );
  assert.match(
    env.document.getElementById('appStatusMessage').textContent,
    /experiments.command_center/,
  );
});

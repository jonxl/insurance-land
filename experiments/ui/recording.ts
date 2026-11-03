import type { RecordingBundle, Recording } from './types.js';
// Fetch recording data separately so HTML stays small and recordings are not duplicated.
export async function loadRecording(
  url: string | URL,
  fetchRecording: typeof fetch = fetch,
): Promise<RecordingBundle> {
  const response = await fetchRecording(url);
  if (!response.ok) {
    throw new Error(`Could not load the experiment recording (HTTP ${response.status}).`);
  }
  const bundle: unknown = await response.json();
  if (!bundle || typeof bundle !== 'object') {
    throw new Error('The experiment recording does not contain any usable snapshots.');
  }
  const worlds = 'worlds' in bundle ? bundle.worlds : { Standard: bundle };
  const selected = 'default' in bundle ? String(bundle.default ?? 'Standard') : 'Standard';
  if (
    !worlds ||
    typeof worlds !== 'object' ||
    !worlds[selected] ||
    !Object.values(worlds as Record<string, Recording>).every(
      (world) => Array.isArray(world?.frames) && world.frames.length > 0,
    )
  ) {
    throw new Error('The experiment recording does not contain any usable snapshots.');
  }
  return bundle as RecordingBundle;
}

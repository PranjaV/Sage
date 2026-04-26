// Stagehand singleton — one browser process for the life of the bridge.
//
// The browser instance is heavy to spin up; LangGraph asks the bridge to run
// each browser_agent step via POST /internal/browser-task. We reuse a single
// page across calls and recover by reloading on errors.

import { Stagehand } from '@browserbasehq/stagehand';
import { z } from 'zod';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { randomUUID } from 'node:crypto';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const repoRoot = resolve(__dirname, '..', '..', '..');
const outDir = resolve(repoRoot, 'out');

const HARD_TIMEOUT_MS = Number(process.env.STAGEHAND_TASK_TIMEOUT_MS || 60_000);

let stagehand = null;
let initPromise = null;
let lastError = null;

/** Boot Stagehand eagerly so the first browser_task request doesn't pay init cost. */
export function prewarm() {
  ensureStagehand().catch((err) => {
    console.warn(`[stagehand] prewarm failed: ${err.message}`);
  });
}

async function ensureStagehand() {
  if (stagehand) return stagehand;
  if (initPromise) return initPromise;

  const forceLocal = (process.env.STAGEHAND_ENV || '').toUpperCase() === 'LOCAL';
  const useBrowserbase = !forceLocal && !!process.env.BROWSERBASE_API_KEY;
  const env = useBrowserbase ? 'BROWSERBASE' : 'LOCAL';

  initPromise = (async () => {
    const sh = new Stagehand({
      env,
      modelName: process.env.STAGEHAND_MODEL || 'gpt-4.1-mini',
      modelClientOptions: { apiKey: process.env.OPENAI_API_KEY },
      ...(useBrowserbase
        ? { apiKey: process.env.BROWSERBASE_API_KEY, projectId: process.env.BROWSERBASE_PROJECT_ID }
        : { headless: true }),
    });
    console.log(`[stagehand] init env=${env}`);
    await sh.init();
    stagehand = sh;
    return sh;
  })();

  try {
    return await initPromise;
  } finally {
    initPromise = null;
  }
}

/**
 * Run one browser task: navigate Amazon, search for `goal`, extract first product.
 * @param {{goal: string, onTrace?: (text: string) => void}} args
 * @returns {Promise<{title: string, price: string, screenshot_url: string}>}
 */
export async function runBrowserTask({ goal, onTrace }) {
  if (!goal) throw new Error('goal is required');

  const trace = onTrace ?? (() => {});

  let timer;
  const run = async () => {
    trace('opening amazon.com');
    const sh = await ensureStagehand();
    const page = sh.page;

    const onAmazon = page.url().includes('amazon.');
    if (!onAmazon) {
      await page.goto('https://www.amazon.com/?language=en_US', { waitUntil: 'domcontentloaded' });
    }

    trace(`searching: ${goal}`);
    await page.act(`type '${goal.replace(/'/g, "\\'")}' into the main search input`);
    await page.act('press Enter to submit the search');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1200);

    const product = await page.extract({
      instruction:
        'On the Amazon search results page, extract the product title and visible price (e.g. "$12.99") of the first sponsored or organic product card that has a price.',
      schema: z.object({ title: z.string(), price: z.string() }),
    });

    const screenshotName = `${randomUUID()}.png`;
    await mkdir(outDir, { recursive: true });
    await page.screenshot({ path: resolve(outDir, screenshotName), fullPage: false });

    trace(`found: ${product.title}`);
    return {
      title: product.title,
      price: product.price,
      screenshot_url: `/static/${screenshotName}`,
    };
  };

  return await Promise.race([
    run(),
    new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error('timeout')), HARD_TIMEOUT_MS);
    }),
  ]).finally(() => clearTimeout(timer));
}

export async function shutdownStagehand() {
  if (stagehand) {
    try { await stagehand.close(); } catch (err) { lastError = err; }
    stagehand = null;
  }
}

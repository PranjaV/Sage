// B3 — Verify Stagehand opens Amazon and finds a product.

import { config } from 'dotenv';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { Stagehand } from '@browserbasehq/stagehand';
import { z } from 'zod';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const repoRoot = resolve(__dirname, '..', '..', '..');
config({ path: resolve(repoRoot, '.env') });

// STAGEHAND_ENV=LOCAL forces local Playwright; otherwise use Browserbase if a key is set.
const forceLocal = (process.env.STAGEHAND_ENV || '').toUpperCase() === 'LOCAL';
const useBrowserbase = !forceLocal && !!process.env.BROWSERBASE_API_KEY;
const env = useBrowserbase ? 'BROWSERBASE' : 'LOCAL';

const outDir = resolve(repoRoot, 'out');
await mkdir(outDir, { recursive: true });
const screenshotPath = resolve(outDir, 'test-stagehand.png');

const HARD_TIMEOUT_MS = Number(process.env.STAGEHAND_TIMEOUT_MS || 30_000);
const overall = setTimeout(() => {
  console.error(`✗ overall timeout (${HARD_TIMEOUT_MS}ms)`);
  process.exit(1);
}, HARD_TIMEOUT_MS);

// gpt-4.1 is the production model for the browser agent (PLAN_A B11), but
// this org's Tier 1 TPM cap (30k) is below Stagehand's full-DOM extract token
// load. Use gpt-4.1-mini for the verification path; production swaps in gpt-4.1
// once the rate-limit tier is raised, or once we scope the extract DOM.
const stagehand = new Stagehand({
  env,
  modelName: process.env.STAGEHAND_MODEL || 'gpt-4.1-mini',
  modelClientOptions: { apiKey: process.env.OPENAI_API_KEY },
  ...(useBrowserbase
    ? {
        apiKey: process.env.BROWSERBASE_API_KEY,
        projectId: process.env.BROWSERBASE_PROJECT_ID,
      }
    : { headless: true }),
});

console.log(`… launching Stagehand (env=${env})`);
const tInit = performance.now();
await stagehand.init();
console.log(`  init: ${Math.round(performance.now() - tInit)}ms`);

try {
  const page = stagehand.page;
  console.log('  goto amazon.com');
  await page.goto('https://www.amazon.com/?language=en_US', { waitUntil: 'domcontentloaded' });
  console.log('  act: type into search box');
  await page.act("type 'weekly pill organizer 7 day' into the main search input");
  console.log('  act: submit search');
  await page.act('press Enter to submit the search');
  console.log('  wait for results');
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(1500);

  console.log('  extract: first product');
  const product = await page.extract({
    instruction:
      'On the Amazon search results page, extract the product title and visible price (e.g. "$12.99") of the first sponsored or organic product card that has a price.',
    schema: z.object({ title: z.string(), price: z.string() }),
  });

  await page.screenshot({ path: screenshotPath, fullPage: false });

  await stagehand.close();
  clearTimeout(overall);

  console.log(`✓ Stagehand ok | ${product.title} | ${product.price}`);
  console.log(`  screenshot: ${screenshotPath}`);
  process.exit(0);
} catch (err) {
  clearTimeout(overall);
  try { await stagehand.close(); } catch {}
  console.error(`✗ ${err?.message ?? err}`);
  process.exit(1);
}

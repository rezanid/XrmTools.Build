import { cpSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

const outputFlag = process.argv.indexOf('--outDir');
if (outputFlag < 0 || !process.argv[outputFlag + 1]) {
  throw new Error('The Microsoft PCF targets must supply --outDir.');
}
const destination = join(process.argv[outputFlag + 1], 'FixtureControl');
mkdirSync(destination, { recursive: true });
cpSync(new URL('./prebuilt/', import.meta.url), destination, { recursive: true });

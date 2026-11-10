import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const outputFlag = process.argv.indexOf('--outDir');
if (outputFlag < 0 || !process.argv[outputFlag + 1]) {
  throw new Error('The Microsoft PCF targets must supply --outDir.');
}

const output = join(process.argv[outputFlag + 1], 'ExampleControl');
mkdirSync(output, { recursive: true });
copyFileSync(new URL('./src/ControlManifest.Input.xml', import.meta.url),
  join(output, 'ControlManifest.xml'));
writeFileSync(join(output, 'bundle.js'),
  readFileSync(new URL('./src/index.js', import.meta.url), 'utf8'));

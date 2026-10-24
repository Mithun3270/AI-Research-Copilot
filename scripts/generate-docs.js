const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const rootDir = path.resolve(__dirname, '..');
const python = process.platform === 'win32'
  ? path.join(rootDir, '.venv', 'Scripts', 'python.exe')
  : path.join(rootDir, '.venv', 'bin', 'python');
const generator = path.join(rootDir, 'docs', 'generate_pdf.py');

if (!fs.existsSync(python)) {
  process.stderr.write('Documentation generation needs the project virtual environment. Run npm run setup first.\n');
  process.exit(1);
}

const result = spawnSync(python, [generator], {
  cwd: rootDir,
  stdio: 'inherit',
  windowsHide: true,
});

if (result.error) {
  process.stderr.write(`Documentation generation failed: ${result.error.message}\n`);
  process.exit(1);
}

if (result.status !== 0) {
  process.exit(result.status || 1);
}

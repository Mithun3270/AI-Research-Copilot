const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { rootDir } = require('./process-utils');

const python = process.platform === 'win32'
  ? path.join(rootDir, '.venv', 'Scripts', 'python.exe')
  : path.join(rootDir, '.venv', 'bin', 'python');

const result = spawnSync(python, [path.join(rootDir, 'backend', 'seed.py')], {
  cwd: rootDir,
  stdio: 'inherit',
  windowsHide: true,
});

if (result.error) {
  process.stderr.write(`Could not run the seed script: ${result.error.message}\n`);
  process.exitCode = 1;
} else if (result.status !== 0) {
  process.stderr.write(`Seed script exited with code ${result.status}.\n`);
  process.exitCode = result.status || 1;
}

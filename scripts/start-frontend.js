const path = require('node:path');
const { rootDir, runManaged } = require('./process-utils');
const frontendDir = path.join(rootDir, 'frontend');

runManaged(
  'frontend',
  process.execPath,
  [
    path.join(frontendDir, 'node_modules', 'vite', 'bin', 'vite.js'),
    '--host',
    '127.0.0.1',
    '--port',
    '5173',
  ],
  { cwd: frontendDir },
);

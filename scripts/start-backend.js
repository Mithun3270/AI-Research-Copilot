const path = require('node:path');
const { rootDir, runManaged } = require('./process-utils');

const python = process.platform === 'win32'
  ? path.join(rootDir, '.venv', 'Scripts', 'python.exe')
  : path.join(rootDir, '.venv', 'bin', 'python');

runManaged('backend', python, [
  '-m',
  'uvicorn',
  'backend.app:app',
  '--host',
  '127.0.0.1',
  '--port',
  '8000',
  '--reload',
], { restartOnExit: true, pidTarget: 'manager' });

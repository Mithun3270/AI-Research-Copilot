const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const rootDir = path.resolve(__dirname, '..');
const venvPython = process.platform === 'win32'
  ? path.join(rootDir, '.venv', 'Scripts', 'python.exe')
  : path.join(rootDir, '.venv', 'bin', 'python');

function run(command, args, cwd, shell = false) {
  const result = spawnSync(command, args, {
    cwd,
    stdio: 'inherit',
    shell,
    windowsHide: true,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(`${command} exited with code ${result.status}`);
  }
}

function runNpm(args, cwd) {
  const command = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  run(command, args, cwd, process.platform === 'win32');
}

try {
  runNpm(['ci'], rootDir);
  runNpm(['ci'], path.join(rootDir, 'frontend'));
  if (!fs.existsSync(venvPython)) {
    const python = process.platform === 'win32' ? 'py' : (process.env.PYTHON || 'python3');
    const pythonArgs = process.platform === 'win32'
      ? ['-3.14', '-m', 'venv', '.venv']
      : ['-m', 'venv', '.venv'];
    run(python, pythonArgs, rootDir);
  }
  run(venvPython, ['-m', 'pip', 'install', '--upgrade', 'pip==26.2.2'], rootDir);
  const envExample = path.join(rootDir, '.env.example');
  const envFile = path.join(rootDir, '.env');
  if (!fs.existsSync(envFile)) {
    fs.copyFileSync(envExample, envFile);
  }
  run(venvPython, ['-m', 'pip', 'install', '-r', path.join(rootDir, 'backend', 'requirements.txt')], rootDir);
  process.stdout.write('\nSetup complete. Start the app with npm run dev.\n');
} catch (error) {
  process.stderr.write(`Setup failed: ${error.message}\n`);
  process.exitCode = 1;
}

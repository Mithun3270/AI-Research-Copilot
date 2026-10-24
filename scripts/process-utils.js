const fs = require('node:fs');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');

const rootDir = path.resolve(__dirname, '..');
const runtimeDir = path.join(rootDir, '.runtime');

function pidPath(name) {
  return path.join(runtimeDir, `${name}.pid`);
}

function savePid(name, pid) {
  fs.mkdirSync(runtimeDir, { recursive: true });
  fs.writeFileSync(pidPath(name), String(pid));
}

function removePid(name, pid) {
  const file = pidPath(name);
  try {
    if (!pid || fs.readFileSync(file, 'utf8').trim() === String(pid)) {
      fs.rmSync(file, { force: true });
    }
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
}

function terminatePid(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return;
  if (process.platform === 'win32') {
    const result = spawnSync('taskkill.exe', ['/PID', String(pid), '/T', '/F'], {
      encoding: 'utf8',
      windowsHide: true,
    });
    if (result.error) throw result.error;
    if (result.status !== 0 && !`${result.stderr}${result.stdout}`.includes('not found')) {
      process.stderr.write(result.stderr || result.stdout);
    }
    return;
  }
  try {
    process.kill(pid, 'SIGTERM');
  } catch (error) {
    if (error.code !== 'ESRCH') throw error;
  }
}

function runManaged(name, command, args, options = {}) {
  let child;
  let stopping = false;
  let restartTimer;
  const trackedPid = options.pidTarget === 'manager' ? process.pid : undefined;
  const trackedProcess = () => trackedPid || (child && child.pid);
  const removeSignalHandlers = () => {
    process.removeListener('SIGINT', handleSignal);
    process.removeListener('SIGTERM', handleSignal);
  };
  const stopChild = () => {
    if (!child || !child.pid) return;
    if (process.platform === 'win32') terminatePid(child.pid);
    else child.kill('SIGTERM');
  };
  const handleSignal = (signal) => {
    if (stopping) return;
    stopping = true;
    if (restartTimer) clearTimeout(restartTimer);
    removePid(name, trackedProcess());
    stopChild();
    process.exitCode = signal === 'SIGINT' ? 130 : 143;
    setTimeout(() => process.exit(), 5000).unref();
  };

  process.on('SIGINT', handleSignal);
  process.on('SIGTERM', handleSignal);
  const startChild = () => {
    if (stopping) return;
    child = spawn(command, args, {
      cwd: options.cwd || rootDir,
      env: process.env,
      stdio: 'inherit',
      windowsHide: true,
      shell: options.shell || false,
    });
    const pid = trackedProcess();
    savePid(name, pid);

    child.on('error', (error) => {
      if (stopping) return;
      stopping = true;
      process.stderr.write(`${name} failed to start: ${error.message}\n`);
      removePid(name, pid);
      removeSignalHandlers();
      process.exitCode = 1;
    });
    child.on('close', (code, signal) => {
      if (stopping) {
        removePid(name, pid);
        removeSignalHandlers();
        return;
      }
      if (options.restartOnExit) {
        process.stderr.write(
          `${name} exited${signal ? ` from ${signal}` : ` with code ${code}`}; restarting in 1 second.\n`,
        );
        restartTimer = setTimeout(startChild, 1000);
        return;
      }
      removePid(name, pid);
      removeSignalHandlers();
      if (signal) process.exitCode = signal === 'SIGINT' ? 130 : 1;
      else process.exitCode = code || 0;
    });
  };

  startChild();
}

module.exports = {
  rootDir,
  runtimeDir,
  pidPath,
  savePid,
  removePid,
  terminatePid,
  runManaged,
};

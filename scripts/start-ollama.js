const net = require('node:net');
const { spawn } = require('node:child_process');
const { rootDir, savePid, removePid, terminatePid } = require('./process-utils');

const host = '127.0.0.1';
const port = 11434;

function probeOllama() {
  return new Promise((resolve) => {
    const request = require('node:http').get(
      `http://${host}:${port}/api/tags`,
      { timeout: 1500 },
      (response) => {
        response.resume();
        resolve({ running: true, status: response.statusCode });
      },
    );
    request.on('timeout', () => request.destroy());
    request.on('error', () => resolve({ running: false }));
  });
}

function probePort() {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host, port });
    socket.once('connect', () => {
      socket.destroy();
      resolve(true);
    });
    socket.once('error', () => resolve(false));
  });
}

async function main() {
  const existing = await probeOllama();
  if (existing.running) {
    process.stdout.write('Ollama is already responding on port 11434; leaving it running.\n');
    return;
  }
  if (await probePort()) {
    process.stdout.write('Port 11434 is already in use; skipping Ollama startup.\n');
    return;
  }

  const command = process.platform === 'win32' ? 'ollama.exe' : 'ollama';
  const child = spawn(command, ['serve'], {
    cwd: rootDir,
    stdio: 'inherit',
    windowsHide: true,
  });
  savePid('ollama', child.pid);

  const stopChild = () => {
    if (!child.pid) return;
    if (process.platform === 'win32') terminatePid(child.pid);
    else child.kill('SIGTERM');
  };
  const handleSignal = () => stopChild();
  process.on('SIGINT', handleSignal);
  process.on('SIGTERM', handleSignal);
  child.on('error', (error) => {
    process.stderr.write(`Could not start Ollama: ${error.message}\n`);
    removePid('ollama', child.pid);
    process.exitCode = 1;
  });
  child.on('close', (code, signal) => {
    removePid('ollama', child.pid);
    process.removeListener('SIGINT', handleSignal);
    process.removeListener('SIGTERM', handleSignal);
    if (signal) process.exitCode = 1;
    else process.exitCode = code || 0;
  });
}

main().catch((error) => {
  process.stderr.write(`Ollama startup check failed: ${error.message}\n`);
  process.exitCode = 1;
});

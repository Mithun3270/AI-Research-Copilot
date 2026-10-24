const fs = require('node:fs');
const { pidPath, terminatePid } = require('./process-utils');

for (const name of ['backend', 'frontend', 'ollama']) {
  const file = pidPath(name);
  if (!fs.existsSync(file)) {
    process.stdout.write(`${name}: no process started by this project.\n`);
    continue;
  }
  const pid = Number(fs.readFileSync(file, 'utf8').trim());
  if (!Number.isInteger(pid) || pid <= 0) {
    process.stderr.write(`${name}: invalid PID file; leaving it untouched.\n`);
    process.exitCode = 1;
    continue;
  }
  try {
    terminatePid(pid);
    fs.rmSync(file, { force: true });
    process.stdout.write(`${name}: stopped project process ${pid}.\n`);
  } catch (error) {
    process.stderr.write(`${name}: failed to stop PID ${pid}: ${error.message}\n`);
    process.exitCode = 1;
  }
}

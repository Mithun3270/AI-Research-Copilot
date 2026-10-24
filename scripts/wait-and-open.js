const { execFile } = require('node:child_process');
const waitOn = require('wait-on');

const frontendUrl = 'http://127.0.0.1:5173';

function openBrowser(url) {
  if (process.platform === 'win32') {
    execFile('cmd.exe', ['/c', 'start', '""', url], (error) => {
      if (error) process.stderr.write(`Could not open browser automatically: ${error.message}\n`);
    });
    return;
  }
  const command = process.platform === 'darwin' ? 'open' : 'xdg-open';
  execFile(command, [url], (error) => {
    if (error) process.stderr.write(`Could not open browser automatically: ${error.message}\n`);
  });
}

waitOn({
  resources: ['http-get://127.0.0.1:8000/health', `http-get://${new URL(frontendUrl).host}/`],
  timeout: 180000,
  interval: 1000,
}).then(() => {
  process.stdout.write('\nAI Research Copilot is ready.\n');
  process.stdout.write(`Frontend: ${frontendUrl}\n`);
  process.stdout.write('Backend:  http://127.0.0.1:8000\n');
  process.stdout.write('API docs: http://127.0.0.1:8000/docs\n\n');
  openBrowser(frontendUrl);
}).catch((error) => {
  process.stderr.write(`Startup readiness check failed: ${error.message}\n`);
  process.exitCode = 1;
});

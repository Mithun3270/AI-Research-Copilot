const http = require('node:http');
const { spawn } = require('node:child_process');

const host = '127.0.0.1';
const port = 11434;
const model = 'qwen2.5:3b';

function getModels() {
  return new Promise((resolve, reject) => {
    const request = http.get(`http://${host}:${port}/api/tags`, { timeout: 3000 }, (response) => {
      let body = '';
      response.setEncoding('utf8');
      response.on('data', (part) => { body += part; });
      response.on('end', () => {
        if (response.statusCode !== 200) {
          reject(new Error(`Ollama returned HTTP ${response.statusCode}`));
          return;
        }
        try {
          resolve(JSON.parse(body).models || []);
        } catch (error) {
          reject(new Error(`Invalid response from Ollama: ${error.message}`));
        }
      });
    });
    request.on('timeout', () => request.destroy(new Error('Ollama health request timed out')));
    request.on('error', reject);
  });
}

function pullModel() {
  return new Promise((resolve, reject) => {
    const command = process.platform === 'win32' ? 'ollama.exe' : 'ollama';
    const child = spawn(command, ['pull', model], { stdio: 'inherit', windowsHide: true });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`ollama pull ${model} exited with code ${code}`));
    });
  });
}

async function main() {
  const deadline = Date.now() + 180000;
  let models;
  while (Date.now() < deadline) {
    try {
      models = await getModels();
      break;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
  }
  if (!models) throw new Error('Ollama did not become available on port 11434 within 180 seconds.');

  if (models.some((entry) => entry.name === model || entry.name === `${model}:latest`)) {
    process.stdout.write(`Ollama model ${model} is available.\n`);
    return;
  }
  process.stdout.write(`Ollama model ${model} is missing; pulling it now.\n`);
  await pullModel();
  process.stdout.write(`Ollama model ${model} is ready.\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
});

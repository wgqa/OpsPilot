import { existsSync, lstatSync, realpathSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(frontendRoot, '..');
const runtimeName = process.env.OPSPILOT_USER_DEMO_RUNTIME_NAME ?? 'user-demo';
if (!/^user-demo(?:-[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?)?$/.test(runtimeName)) {
  throw new Error('OPSPILOT_USER_DEMO_RUNTIME_NAME must be user-demo or a safe user-demo-* name.');
}
const runtimeRoot = path.join(projectRoot, '.runtime');
const runtimeDirectory = path.join(runtimeRoot, runtimeName);
if (!existsSync(runtimeRoot) || !existsSync(runtimeDirectory)) {
  throw new Error('The selected User Demo runtime directory is missing.');
}
if (lstatSync(runtimeRoot).isSymbolicLink() || lstatSync(runtimeDirectory).isSymbolicLink()) {
  throw new Error('The selected User Demo runtime cannot be a symlink.');
}
const resolvedRuntimeRoot = realpathSync(runtimeRoot);
const resolvedRuntimeDirectory = realpathSync(runtimeDirectory);
if (path.dirname(resolvedRuntimeDirectory) !== resolvedRuntimeRoot ||
    path.basename(resolvedRuntimeDirectory) !== runtimeName) {
  throw new Error('The selected User Demo runtime must be a direct child of repository .runtime.');
}
const stopRequest = path.join(resolvedRuntimeDirectory, 'shutdown.request');
const port = Number(process.env.OPSPILOT_USER_DEMO_WEB_PORT ?? '5173');
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error('OPSPILOT_USER_DEMO_WEB_PORT must be a valid TCP port.');
}

// Start-UserDemo redirects stdin to an empty file. Keep Vite from treating
// that expected EOF as its own shutdown signal; shutdown.request owns lifecycle.
process.env.CI = 'true';

const server = await createServer({
  configFile: path.join(frontendRoot, 'vite.config.ts'),
  root: frontendRoot,
  server: { host: '127.0.0.1', port, strictPort: true },
});

await server.listen();
server.printUrls();

let closing = null;
let stopPoll = null;

function closeGracefully(reason) {
  if (closing) return closing;
  if (stopPoll) clearInterval(stopPoll);
  closing = (async () => {
    await server.close();
    console.log(`User-demo Vite server closed gracefully (${reason}).`);
  })();
  return closing;
}

function handleStop(reason) {
  void closeGracefully(reason).catch((error) => {
    console.error('User-demo Vite graceful shutdown failed.', error);
    process.exitCode = 1;
  });
}

stopPoll = setInterval(() => {
  if (existsSync(stopRequest)) handleStop('shutdown.request');
}, 200);
stopPoll.unref();

process.once('SIGINT', () => handleStop('SIGINT'));
process.once('SIGTERM', () => handleStop('SIGTERM'));

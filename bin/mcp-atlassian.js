#!/usr/bin/env node

const { spawn, spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const rootDir = path.resolve(__dirname, '..');
const venvDir = path.join(rootDir, '.venv');
const venvBinDir = process.platform === 'win32' ? path.join(venvDir, 'Scripts') : path.join(venvDir, 'bin');
const pipCmd = process.platform === 'win32' ? path.join(venvBinDir, 'pip.exe') : path.join(venvBinDir, 'pip');
const pythonCmd = process.platform === 'win32' ? path.join(venvBinDir, 'python.exe') : path.join(venvBinDir, 'python');
const serverCmd = process.platform === 'win32' ? path.join(venvBinDir, 'mcp-atlassian.exe') : path.join(venvBinDir, 'mcp-atlassian');

// Helper to log to stderr so we don't pollute stdout (critical for MCP stdio)
function log(msg) {
  process.stderr.write(`[Node Wrapper] ${msg}\n`);
}

// Check which python executable is available on the system
function getSystemPython() {
  const checkPython3 = spawnSync('python3', ['--version']);
  if (checkPython3.status === 0) return 'python3';
  
  const checkPython = spawnSync('python', ['--version']);
  if (checkPython.status === 0) return 'python';
  
  return null;
}

const systemPython = getSystemPython();
if (!systemPython && !fs.existsSync(pythonCmd)) {
  log('Error: Python is not installed or not in PATH.');
  process.exit(1);
}

// 1. Create virtual environment if it doesn't exist
if (!fs.existsSync(venvDir)) {
  log('Creating virtual environment (.venv)...');
  const createVenv = spawnSync(systemPython, ['-m', 'venv', '.venv'], { cwd: rootDir, stdio: 'inherit' });
  if (createVenv.status !== 0) {
    log('Failed to create virtual environment. Make sure python3-venv (on Ubuntu/Debian) or venv module is installed.');
    process.exit(1);
  }
}

// 2. Install/editable install if server script/executable does not exist
if (!fs.existsSync(serverCmd)) {
  log('Installing python dependencies via pip...');
  
  // Make sure pip is upgraded and install package in editable mode
  const installDeps = spawnSync(pipCmd, ['install', '-e', '.'], { cwd: rootDir, stdio: 'inherit' });
  if (installDeps.status !== 0) {
    log('Failed to install python dependencies.');
    process.exit(1);
  }
}

// 3. Run the MCP server
log('Starting Atlassian MCP server...');
const child = spawn(serverCmd, process.argv.slice(2), {
  cwd: rootDir,
  stdio: ['pipe', 'pipe', 'inherit'] // Pipe stdin/stdout, inherit stderr
});

process.stdin.pipe(child.stdin);
child.stdout.pipe(process.stdout);

child.on('exit', (code) => {
  process.exit(code || 0);
});

process.on('SIGINT', () => child.kill('SIGINT'));
process.on('SIGTERM', () => child.kill('SIGTERM'));

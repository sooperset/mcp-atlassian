#!/usr/bin/env node

const { spawn } = require('child_process');
const path = require('path');

// Determine the correct path to the executable based on the OS
const executableName = 'mcp-atlassian' + (process.platform === 'win32' ? '.exe' : '');
// Adjust the path to where PyInstaller places the executable (e.g., dist folder)
const executablePath = path.join(__dirname, 'dist', executableName);

const child = spawn(executablePath, process.argv.slice(2), {
  stdio: 'inherit' // Pipe stdin, stdout, and stderr to the child process
});

child.on('error', (err) => {
  console.error('Failed to start subprocess.', err);
});

child.on('exit', (code, signal) => {
  if (code !== null) {
    process.exitCode = code;
  } else if (signal !== null) {
    console.log(`Subprocess exited with signal ${signal}`);
    process.exit(1); // Exit with an error code if killed by a signal
  }
});

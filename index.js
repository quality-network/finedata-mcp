#!/usr/bin/env node

/**
 * FineData MCP Server Launcher
 * 
 * This script launches the Python MCP server.
 * It tries multiple methods in order:
 * 1. uvx (recommended, from uv)
 * 2. pipx run (alternative)
 * 3. pipx install + run
 * 
 * Usage:
 *   npx @finedata/mcp-server
 * 
 * Environment variables:
 *   FINEDATA_API_KEY - Your FineData API key (required)
 *   FINEDATA_API_URL - API URL (default: https://api.finedata.ai)
 */

const { spawn, spawnSync } = require('child_process');

// Check if API key is set
if (!process.env.FINEDATA_API_KEY) {
  console.error('Error: FINEDATA_API_KEY environment variable is required.');
  console.error('Get your API key at https://finedata.ai');
  process.exit(1);
}

// Check if a command exists
function commandExists(cmd) {
  const result = spawnSync('which', [cmd], { stdio: 'pipe' });
  return result.status === 0;
}

// Run a command and wait for completion
function runSync(cmd, args) {
  return spawnSync(cmd, args, { stdio: 'inherit', env: process.env });
}

// Method 1: Try uvx (best option - from astral's uv)
function tryUvx(onFail) {
  if (!commandExists('uvx')) {
    return onFail();
  }

  const proc = spawn('uvx', ['finedata-mcp'], {
    stdio: 'inherit',
    env: process.env,
  });

  proc.on('error', () => onFail());
  proc.on('exit', (code) => {
    process.exit(code || 0);
  });
}

// Method 2: Try pipx run (runs in isolated env)
function tryPipxRun(onFail) {
  if (!commandExists('pipx')) {
    return onFail();
  }

  const proc = spawn('pipx', ['run', 'finedata-mcp'], {
    stdio: 'inherit',
    env: process.env,
  });

  proc.on('error', () => onFail());
  proc.on('exit', (code) => {
    if (code !== 0) {
      // pipx run failed, try installing
      tryPipxInstall(onFail);
    } else {
      process.exit(0);
    }
  });
}

// Method 3: Install via pipx and run
function tryPipxInstall(onFail) {
  if (!commandExists('pipx')) {
    return onFail();
  }

  console.error('Installing finedata-mcp via pipx...');
  const install = runSync('pipx', ['install', 'finedata-mcp', '--force']);
  
  if (install.status !== 0) {
    console.error('Failed to install via pipx');
    return onFail();
  }

  // Now run it
  const proc = spawn('finedata-mcp', [], {
    stdio: 'inherit',
    env: process.env,
  });

  proc.on('error', (err) => {
    console.error('Error running finedata-mcp:', err.message);
    onFail();
  });

  proc.on('exit', (code) => {
    process.exit(code || 0);
  });
}

// Final fallback - show help
function showHelp() {
  console.error('');
  console.error('Error: Could not start FineData MCP Server.');
  console.error('');
  console.error('Please install uv or pipx:');
  console.error('');
  console.error('  Option 1 - Install uv (recommended):');
  console.error('    curl -LsSf https://astral.sh/uv/install.sh | sh');
  console.error('');
  console.error('  Option 2 - Install pipx:');
  console.error('    brew install pipx && pipx ensurepath');
  console.error('');
  console.error('Then restart your terminal and Cursor.');
  console.error('');
  console.error('Or configure MCP to use uvx directly:');
  console.error('  {');
  console.error('    "command": "uvx",');
  console.error('    "args": ["finedata-mcp"],');
  console.error('    "env": { "FINEDATA_API_KEY": "your_key" }');
  console.error('  }');
  console.error('');
  process.exit(1);
}

// Start: try methods in order
tryUvx(() => tryPipxRun(() => showHelp()));

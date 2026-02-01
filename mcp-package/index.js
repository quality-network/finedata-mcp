#!/usr/bin/env node

/**
 * FineData MCP Server Launcher
 * 
 * This script launches the Python MCP server.
 * It tries multiple methods in order:
 * 1. uvx (recommended, from uv)
 * 2. pipx run (alternative)
 * 3. python -m with auto-install
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

// Check if Python module is installed
function moduleInstalled(pythonCmd, moduleName) {
  const result = spawnSync(pythonCmd, ['-c', `import ${moduleName}`], { 
    stdio: 'pipe',
    env: process.env 
  });
  return result.status === 0;
}

// Install Python package
function installPackage(pythonCmd) {
  console.error('Installing finedata-mcp...');
  const result = spawnSync(pythonCmd, ['-m', 'pip', 'install', '--user', '-q', 'finedata-mcp'], {
    stdio: 'inherit',
    env: process.env
  });
  return result.status === 0;
}

// Method 1: Try uvx (recommended)
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
    if (code !== 0 && code !== null) {
      // uvx failed, try next method
      onFail();
    } else {
      process.exit(code || 0);
    }
  });
}

// Method 2: Try pipx run
function tryPipx(onFail) {
  if (!commandExists('pipx')) {
    return onFail();
  }

  const proc = spawn('pipx', ['run', 'finedata-mcp'], {
    stdio: 'inherit',
    env: process.env,
  });

  proc.on('error', () => onFail());
  proc.on('exit', (code) => {
    if (code !== 0 && code !== null) {
      onFail();
    } else {
      process.exit(code || 0);
    }
  });
}

// Method 3: Try python with auto-install
function tryPython() {
  const pythonCommands = ['python3', 'python'];
  
  for (const pythonCmd of pythonCommands) {
    if (!commandExists(pythonCmd)) continue;

    // Check if module is installed, if not - install it
    if (!moduleInstalled(pythonCmd, 'mcp_server')) {
      const installed = installPackage(pythonCmd);
      if (!installed) {
        console.error(`Failed to install finedata-mcp with ${pythonCmd}`);
        continue;
      }
    }

    // Run the server
    const proc = spawn(pythonCmd, ['-m', 'mcp_server'], {
      stdio: 'inherit',
      env: process.env,
    });

    proc.on('error', (err) => {
      console.error('Error starting server:', err.message);
      process.exit(1);
    });

    proc.on('exit', (code) => {
      process.exit(code || 0);
    });

    return; // Started successfully
  }

  // No Python found
  console.error('Error: Python 3.10+ is required but not found.');
  console.error('');
  console.error('Options:');
  console.error('  1. Install uv (recommended): curl -LsSf https://astral.sh/uv/install.sh | sh');
  console.error('  2. Install Python: https://www.python.org/downloads/');
  console.error('');
  console.error('Or use uvx directly in your MCP config:');
  console.error('  "command": "uvx", "args": ["finedata-mcp"]');
  process.exit(1);
}

// Start: try methods in order
tryUvx(() => tryPipx(() => tryPython()));

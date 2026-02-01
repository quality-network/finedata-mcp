#!/usr/bin/env node

/**
 * FineData MCP Server Launcher
 * 
 * This script launches the Python MCP server using uvx (uv tool).
 * uvx automatically handles Python environment and dependencies.
 * 
 * Usage:
 *   npx @finedata/mcp-server
 * 
 * Environment variables:
 *   FINEDATA_API_KEY - Your FineData API key (required)
 *   FINEDATA_API_URL - API URL (default: https://api.finedata.ai)
 */

const { spawn } = require('child_process');
const path = require('path');

// Check if API key is set
if (!process.env.FINEDATA_API_KEY) {
  console.error('Error: FINEDATA_API_KEY environment variable is required.');
  console.error('Get your API key at https://finedata.ai');
  process.exit(1);
}

// Try uvx first (recommended), fallback to python -m
function tryUvx() {
  const uvx = spawn('uvx', ['finedata-mcp'], {
    stdio: 'inherit',
    env: process.env,
  });

  uvx.on('error', (err) => {
    if (err.code === 'ENOENT') {
      // uvx not found, try python
      tryPython();
    } else {
      console.error('Error starting server:', err.message);
      process.exit(1);
    }
  });

  uvx.on('exit', (code) => {
    process.exit(code || 0);
  });
}

function tryPython() {
  // Try python3 first, then python
  const pythonCommands = ['python3', 'python'];
  
  function tryNextPython(index) {
    if (index >= pythonCommands.length) {
      console.error('Error: Python not found. Please install Python 3.10+ or uv.');
      console.error('Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh');
      process.exit(1);
    }

    const cmd = pythonCommands[index];
    const python = spawn(cmd, ['-m', 'finedata_mcp'], {
      stdio: 'inherit',
      env: process.env,
    });

    python.on('error', (err) => {
      if (err.code === 'ENOENT') {
        tryNextPython(index + 1);
      } else {
        console.error('Error starting server:', err.message);
        process.exit(1);
      }
    });

    python.on('exit', (code) => {
      if (code === null) {
        // Process was killed, try next
        tryNextPython(index + 1);
      } else {
        process.exit(code);
      }
    });
  }

  tryNextPython(0);
}

// Start with uvx
tryUvx();

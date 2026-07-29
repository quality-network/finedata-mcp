#!/usr/bin/env node

/**
 * FineData MCP Server Launcher
 *
 * Tries: uvx → pipx run → pipx install → help.
 * Windows-compatible commandExists (where.exe / --version probe).
 */

const { spawn, spawnSync } = require('child_process');
const os = require('os');

if (!process.env.FINEDATA_API_KEY) {
  console.error('Error: FINEDATA_API_KEY environment variable is required.');
  console.error('Get your API key at https://finedata.ai');
  process.exit(1);
}

function commandExists(cmd) {
  if (process.platform === 'win32') {
    const where = spawnSync('where', [cmd], { stdio: 'pipe', shell: true });
    if (where.status === 0) return true;
  } else {
    const which = spawnSync('which', [cmd], { stdio: 'pipe' });
    if (which.status === 0) return true;
  }
  // Fallback: try running with --version
  const probe = spawnSync(cmd, ['--version'], {
    stdio: 'pipe',
    shell: process.platform === 'win32',
  });
  return probe.status === 0 || probe.status === null;
}

function runSync(cmd, args) {
  return spawnSync(cmd, args, {
    stdio: 'inherit',
    env: process.env,
    shell: process.platform === 'win32',
  });
}

function tryUvx(onFail) {
  if (!commandExists('uvx')) {
    return onFail();
  }
  const proc = spawn('uvx', ['finedata-mcp'], {
    stdio: 'inherit',
    env: process.env,
    shell: process.platform === 'win32',
  });
  proc.on('error', () => onFail());
  proc.on('exit', (code) => process.exit(code || 0));
}

function tryPipxRun(onFail) {
  if (!commandExists('pipx')) {
    return onFail();
  }
  const proc = spawn('pipx', ['run', 'finedata-mcp'], {
    stdio: 'inherit',
    env: process.env,
    shell: process.platform === 'win32',
  });
  proc.on('error', () => onFail());
  proc.on('exit', (code) => {
    if (code !== 0) {
      tryPipxInstall(onFail);
    } else {
      process.exit(0);
    }
  });
}

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
  const proc = spawn('finedata-mcp', [], {
    stdio: 'inherit',
    env: process.env,
    shell: process.platform === 'win32',
  });
  proc.on('error', (err) => {
    console.error('Error running finedata-mcp:', err.message);
    onFail();
  });
  proc.on('exit', (code) => process.exit(code || 0));
}

function showHelp() {
  console.error('');
  console.error('Error: Could not start FineData MCP Server.');
  console.error('');
  console.error('Please install uv or pipx:');
  console.error('');
  console.error('  Option 1 - Install uv (recommended):');
  console.error('    curl -LsSf https://astral.sh/uv/install.sh | sh');
  console.error('    # Windows: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"');
  console.error('');
  console.error('  Option 2 - Install pipx:');
  console.error('    brew install pipx && pipx ensurepath');
  console.error('    # Windows: pip install pipx && pipx ensurepath');
  console.error('');
  console.error(`Platform: ${os.platform()} ${os.arch()}`);
  console.error('');
  process.exit(1);
}

tryUvx(() => tryPipxRun(() => showHelp()));

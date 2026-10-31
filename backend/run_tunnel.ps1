# Opens a temporary public HTTPS address (Cloudflare quick tunnel) for the frontend dev server.
# Usage (from anywhere):  .\run_tunnel.ps1             -> tunnel to http://localhost:5173
#                         .\run_tunnel.ps1 -Port 5174
# The https://<random>.trycloudflare.com address appears in the output; it changes every time and works only
# while this terminal stays open. Start the frontend first (npm run dev -- --host).
# Anyone who knows the address can open the site, so do not share it publicly.
param([int]$Port = 5173)

$ErrorActionPreference = 'Stop'
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) { throw 'cloudflared was not found in PATH.' }

# A config.yml in ~/.cloudflared (made for named tunnels) turns quick tunnels into "404" pages.
# Running with an empty config file avoids it and leaves that config.yml untouched.
$empty = Join-Path $env:TEMP 'movar-cloudflared-empty.yml'
Set-Content -Path $empty -Value '# intentionally empty' -Encoding ascii

cloudflared tunnel --config $empty --url "http://localhost:$Port"

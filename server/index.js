// SensorLab Local Telemetry Hub aur Web Server
// Phone, Board aur Simulator se sensor data ingest karke Three.js clients ko broadcast karta hai.

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { WebSocketServer, WebSocket } = require('ws');

const PORT = parseInt(process.env.PORT || '8080', 10);
const HOST = process.env.HOST || '0.0.0.0';

// Local network IPv4 addresses dhoondo taaki mobile phone connect ho sake
function getLocalIpAddresses() {
  const interfaces = os.networkInterfaces();
  const addresses = [];
  for (const name of Object.keys(interfaces)) {
    for (const iface of interfaces[name]) {
      // Sirf IPv4 aur non-internal addresses consider karo
      if (iface.family === 'IPv4' && !iface.internal) {
        addresses.push({ interface: name, address: iface.address });
      }
    }
  }
  return addresses;
}

// PROTOCOL.md ke mutabiq incoming message validate karne ka function
function validateSensorMessage(msg) {
  if (!msg || typeof msg !== 'object') return false;

  // Source check: phone, board ya sim hona zaroori hai
  const validSources = ['phone', 'board', 'sim'];
  if (!validSources.includes(msg.source)) return false;

  // Sensor name non-empty string hona chahiye
  if (typeof msg.sensor !== 'string' || !msg.sensor.trim()) return false;

  // Values array of numbers hona chahiye
  if (!Array.isArray(msg.values) || msg.values.length === 0) return false;
  for (const val of msg.values) {
    if (typeof val !== 'number' || Number.isNaN(val)) return false;
  }

  // Timestamp non-negative number hona chahiye
  if (typeof msg.time !== 'number' || msg.time < 0) return false;

  return true;
}

// Static files serve karne ke liye basic MIME map
const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml'
};

const server = http.createServer((req, res) => {
  // CORS headers enable karo taaki local clients access kar sakein
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  const parsedUrl = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  let pathname = parsedUrl.pathname;

  // Default routes mapping
  if (pathname === '/' || pathname === '/index.html') {
    pathname = '/client/index.html';
  } else if (pathname === '/phone' || pathname === '/phone.html') {
    pathname = '/client/phone.html';
  } else if (pathname.startsWith('/vendor/')) {
    pathname = '/client' + pathname;
  } else if (!pathname.startsWith('/client/')) {
    pathname = '/client' + pathname;
  }

  // API endpoint: local server info aur IPs return karta hai
  if (parsedUrl.pathname === '/api/info') {
    const info = {
      app: 'SensorLab Telemetry Hub',
      version: '0.1.0',
      port: PORT,
      ips: getLocalIpAddresses()
    };
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(info, null, 2));
    return;
  }

  // File system se static file fetch karo
  const projectRoot = path.resolve(__dirname, '..');
  const filePath = path.join(projectRoot, pathname);

  // Path traversal attack rokne ke liye check karo
  if (!filePath.startsWith(projectRoot)) {
    res.writeHead(403, { 'Content-Type': 'text/plain' });
    res.end('403 Forbidden');
    return;
  }

  fs.stat(filePath, (err, stats) => {
    if (err || !stats.isFile()) {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('404 Not Found: ' + pathname);
      return;
    }

    const ext = path.extname(filePath).toLowerCase();
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';
    res.writeHead(200, { 'Content-Type': contentType });
    fs.createReadStream(filePath).pipe(res);
  });
});

// WebSocket Server initialize karo
const wss = new WebSocketServer({ server });

let clientCount = 0;
let lastTelemetry = null;

wss.on('connection', (ws, req) => {
  clientCount++;
  const clientIp = req.socket.remoteAddress;
  console.log(`[WS] Client connect hua (${clientIp}). Total clients: ${clientCount}`);

  // Naye client ko latest telemetry state turant bhej do agar available ho
  if (lastTelemetry) {
    ws.send(JSON.stringify({ type: 'telemetry', data: lastTelemetry }));
  }

  ws.on('message', (data) => {
    try {
      const parsed = JSON.parse(data.toString());

      // Validate karo PROTOCOL.md ke rules ke hisaab se
      if (!validateSensorMessage(parsed)) {
        ws.send(JSON.stringify({ type: 'error', message: 'Invalid payload structure (violates PROTOCOL.md)' }));
        return;
      }

      lastTelemetry = parsed;

      // Sabhi connected clients ko broadcast karo
      const broadcastPayload = JSON.stringify({ type: 'telemetry', data: parsed });
      for (const client of wss.clients) {
        if (client !== ws && client.readyState === WebSocket.OPEN) {
          client.send(broadcastPayload);
        }
      }
    } catch (parseError) {
      ws.send(JSON.stringify({ type: 'error', message: 'Malformed JSON payload' }));
    }
  });

  ws.on('close', () => {
    clientCount--;
    console.log(`[WS] Client disconnect hua. Total clients: ${clientCount}`);
  });

  ws.on('error', (err) => {
    console.error('[WS Error]', err.message);
  });
});

if (require.main === module) {
  server.listen(PORT, HOST, () => {
    console.log('='.repeat(65));
    console.log(` SensorLab Telemetry Hub running on port ${PORT}`);
    console.log('='.repeat(65));
    console.log(` > Desktop 3D View:  http://localhost:${PORT}/`);
    console.log(` > Phone Sensor UI:  http://localhost:${PORT}/phone`);

    const localIps = getLocalIpAddresses();
    if (localIps.length > 0) {
      console.log('\n Mobile browser se connect karne ke liye same Wi-Fi pe ye URL kholein:');
      for (const iface of localIps) {
        console.log(`   * http://${iface.address}:${PORT}/phone  (${iface.interface})`);
      }
    }
    console.log('='.repeat(65));
  });
}

module.exports = { server, validateSensorMessage };

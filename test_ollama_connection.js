const https = require('https');
const http = require('http');

const endpoints = [
  'https://mtia.globaltechsolutions.net.pe/api/tags',
  'https://mtia.globaltechsolutions.net.pe/v1/models',
  'http://mtia.globaltechsolutions.net.pe/api/tags',
  'http://192.168.42.21:11434/api/tags'
];

async function checkEndpoint(urlStr) {
  return new Promise((resolve) => {
    const url = new URL(urlStr);
    const client = url.protocol === 'https:' ? https : http;
    const req = client.get(urlStr, { timeout: 3000 }, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        console.log(`[STATUS ${res.statusCode}] ${urlStr} => ${data.substring(0, 100).replace(/\n/g, ' ')}`);
        resolve(res.statusCode);
      });
    });

    req.on('error', (err) => {
      console.log(`[ERROR] ${urlStr} => ${err.message}`);
      resolve(null);
    });

    req.on('timeout', () => {
      req.destroy();
      console.log(`[TIMEOUT] ${urlStr}`);
      resolve(null);
    });
  });
}

async function run() {
  console.log('Probando conectividad desde la red corporativa...\n');
  for (const ep of endpoints) {
    await checkEndpoint(ep);
  }
}

run();

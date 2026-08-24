const http = require('http');
const https = require('https');

const targets = [
  'https://mtia.globaltechsolutions.net.pe/api/tags',
  'https://mtia.globaltechsolutions.net.pe/api/version',
  'http://mtia.globaltechsolutions.net.pe:8080/api/tags',
  'http://172.16.10.1:11434/api/tags',
  'http://192.168.1.11:11434/api/tags'
];

async function testTarget(urlStr) {
  return new Promise((resolve) => {
    try {
      const url = new URL(urlStr);
      const client = url.protocol === 'https:' ? https : http;
      const req = client.get(urlStr, { timeout: 2500 }, (res) => {
        let data = '';
        res.on('data', c => data += c);
        res.on('end', () => {
          console.log(`RESULT: [${res.statusCode}] ${urlStr} -> ${data.substring(0, 80).replace(/\n/g, ' ')}`);
          resolve(res.statusCode);
        });
      });

      req.on('error', (err) => {
        console.log(`RESULT: [ERROR: ${err.message}] ${urlStr}`);
        resolve(null);
      });

      req.on('timeout', () => {
        req.destroy();
        console.log(`RESULT: [TIMEOUT] ${urlStr}`);
        resolve(null);
      });
    } catch (e) {
      console.log(`RESULT: [INVALID URL] ${urlStr}`);
      resolve(null);
    }
  });
}

async function run() {
  console.log('--- Diagnóstico Detallado de Conexión ---');
  for (const t of targets) {
    await testTarget(t);
  }
}

run();

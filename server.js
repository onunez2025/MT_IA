const express = require('express');
const https = require('https');
const http = require('http');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// OLLAMA_URL predeterminado hacia el dominio de la empresa
const OLLAMA_URL = process.env.OLLAMA_URL || 'https://mtia.globaltechsolutions.net.pe';

// DeepSeek configuration
const DEEPSEEK_API_KEY = process.env.DEEPSEEK_API_KEY || '';
const DEEPSEEK_API_URL = process.env.DEEPSEEK_API_URL || 'https://api.deepseek.com/v1';

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

app.get('/favicon.ico', (req, res) => res.status(204).end());

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'MT.IA OpenAI-Compatible API', timestamp: new Date().toISOString() });
});

// Helper: Detectar el proveedor basado en el nombre del modelo
function getProvider(modelName) {
  if (modelName && modelName.toLowerCase().includes('deepseek')) {
    return 'deepseek';
  }
  return 'ollama';
}

// Helper: Obtener lista de modelos de Ollama
async function getOllamaModels() {
  return new Promise((resolve) => {
    const url = new URL(`${OLLAMA_URL}/api/tags`);
    const client = url.protocol === 'https:' ? https : http;

    const options = {
      hostname: url.hostname,
      port: url.port || (url.protocol === 'https:' ? 443 : 80),
      path: url.pathname,
      method: 'GET',
      timeout: 5000
    };

    const req = client.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (parsed.models) {
            resolve(parsed.models.map(m => ({ id: m.name, object: 'model', owned_by: 'ollama' })));
          } else {
            resolve([]);
          }
        } catch (e) {
          resolve([]);
        }
      });
    });

    req.on('error', () => resolve([]));
    req.on('timeout', () => {
      req.destroy();
      resolve([]);
    });

    req.end();
  });
}

// Endpoint OpenAI-compatible: GET /v1/models
app.get('/v1/models', async (req, res) => {
  try {
    const ollamaModels = await getOllamaModels();

    // Agregar DeepSeek si está disponible
    const allModels = [...ollamaModels];
    if (DEEPSEEK_API_KEY) {
      allModels.push({ id: 'deepseek-chat', object: 'model', owned_by: 'deepseek' });
    }

    res.json({
      object: 'list',
      data: allModels
    });
  } catch (err) {
    res.status(500).json({
      object: 'list',
      data: [{ id: 'llama3.2:3b', object: 'model', owned_by: 'ollama' }]
    });
  }
});

// Endpoint OpenAI-compatible: POST /v1/chat/completions
app.post('/v1/chat/completions', (req, res) => {
  const { messages, model = 'llama3.2:3b', stream = true } = req.body;

  if (!messages || !Array.isArray(messages)) {
    return res.status(400).json({ error: 'messages array is required' });
  }

  const provider = getProvider(model);

  if (provider === 'deepseek') {
    // Proxy a DeepSeek API
    if (!DEEPSEEK_API_KEY) {
      return res.status(503).json({ error: 'DeepSeek API key not configured' });
    }

    const postData = JSON.stringify({
      model: 'deepseek-chat',
      messages: messages,
      stream: stream
    });

    const url = new URL(`${DEEPSEEK_API_URL}/chat/completions`);
    const client = url.protocol === 'https:' ? https : http;

    const options = {
      hostname: url.hostname,
      port: url.port || (url.protocol === 'https:' ? 443 : 80),
      path: url.pathname + url.search,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(postData),
        'Authorization': `Bearer ${DEEPSEEK_API_KEY}`
      },
      timeout: 30000
    };

    const deepseekReq = client.request(options, (deepseekRes) => {
      if (!res.headersSent) {
        res.setHeader('Content-Type', 'text/event-stream');
        res.setHeader('Cache-Control', 'no-cache');
        res.setHeader('Connection', 'keep-alive');
      }

      deepseekRes.on('data', (chunk) => {
        res.write(chunk);
      });

      deepseekRes.on('end', () => {
        res.end();
      });
    });

    deepseekReq.on('error', (err) => {
      console.error('Error connecting to DeepSeek:', err.message);
      if (!res.headersSent) {
        res.status(503).json({ error: `DeepSeek API error: ${err.message}` });
      } else {
        res.write(`data: ${JSON.stringify({ error: err.message })}\n\n`);
        res.end();
      }
    });

    deepseekReq.on('timeout', () => {
      deepseekReq.destroy();
      if (!res.headersSent) {
        res.status(504).json({ error: 'DeepSeek API timeout' });
      }
    });

    req.on('close', () => {
      deepseekReq.destroy();
    });

    deepseekReq.write(postData);
    deepseekReq.end();
  } else {
    // Proxy a Ollama
    const postData = JSON.stringify({
      model: model,
      messages: messages,
      stream: stream
    });

    const url = new URL(`${OLLAMA_URL}/api/chat`);
    const client = url.protocol === 'https:' ? https : http;

    const options = {
      hostname: url.hostname,
      port: url.port || (url.protocol === 'https:' ? 443 : 80),
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(postData)
      },
      timeout: 30000
    };

    const ollamaReq = client.request(options, (ollamaRes) => {
      if (!res.headersSent) {
        res.setHeader('Content-Type', 'text/event-stream');
        res.setHeader('Cache-Control', 'no-cache');
        res.setHeader('Connection', 'keep-alive');
      }

      ollamaRes.on('data', (chunk) => {
        res.write(chunk);
      });

      ollamaRes.on('end', () => {
        res.end();
      });
    });

    ollamaReq.on('error', (err) => {
      console.error('Error connecting to Ollama:', err.message);
      if (!res.headersSent) {
        res.status(503).json({ error: `Ollama error: ${err.message}` });
      } else {
        res.write(`data: ${JSON.stringify({ error: err.message })}\n\n`);
        res.end();
      }
    });

    ollamaReq.on('timeout', () => {
      ollamaReq.destroy();
      if (!res.headersSent) {
        res.status(504).json({ error: 'Ollama timeout' });
      }
    });

    req.on('close', () => {
      ollamaReq.destroy();
    });

    ollamaReq.write(postData);
    ollamaReq.end();
  }
});

// Endpoint 1: Obtener la lista de modelos disponibles en Ollama
app.get('/api/models', (req, res) => {
  const url = new URL(`${OLLAMA_URL}/api/tags`);
  const client = url.protocol === 'https:' ? https : http;

  const options = {
    hostname: url.hostname,
    port: url.port || (url.protocol === 'https:' ? 443 : 80),
    path: url.pathname,
    method: 'GET',
    timeout: 5000
  };

  const ollamaReq = client.request(options, (ollamaRes) => {
    let data = '';
    ollamaRes.on('data', chunk => data += chunk);
    ollamaRes.on('end', () => {
      if (res.headersSent) return;
      if (ollamaRes.statusCode === 200) {
        try {
          const parsed = JSON.parse(data);
          res.json(parsed);
        } catch (e) {
          res.status(500).json({ error: 'Formato de respuesta inválido del servidor Ollama' });
        }
      } else {
        res.status(ollamaRes.statusCode).json({ error: `Servidor Ollama respondió con código ${ollamaRes.statusCode}` });
      }
    });
  });

  ollamaReq.on('error', (err) => {
    if (res.headersSent) return;
    res.status(503).json({
      error: `No se pudo conectar a ${OLLAMA_URL}. ${err.message}`,
      fallbackModels: [{ name: 'llama3.5:3b' }]
    });
  });

  ollamaReq.on('timeout', () => {
    ollamaReq.destroy();
    if (!res.headersSent) {
      res.status(504).json({
        error: `Timeout al conectar con ${OLLAMA_URL}`,
        fallbackModels: [{ name: 'llama3.5:3b' }]
      });
    }
  });

  ollamaReq.end();
});

// Endpoint 2: Proxy con Streaming para Chat
app.post('/api/chat', (req, res) => {
  const { messages, model = 'llama3.5:3b', system = '' } = req.body;

  const postData = JSON.stringify({
    model: model,
    messages: messages,
    system: system,
    stream: true
  });

  const url = new URL(`${OLLAMA_URL}/api/chat`);
  const client = url.protocol === 'https:' ? https : http;

  const options = {
    hostname: url.hostname,
    port: url.port || (url.protocol === 'https:' ? 443 : 80),
    path: url.pathname,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(postData)
    },
    timeout: 30000
  };

  const ollamaReq = client.request(options, (ollamaRes) => {
    if (!res.headersSent) {
      res.setHeader('Content-Type', 'text/event-stream');
      res.setHeader('Cache-Control', 'no-cache');
      res.setHeader('Connection', 'keep-alive');
    }

    ollamaRes.on('data', (chunk) => {
      res.write(chunk);
    });

    ollamaRes.on('end', () => {
      res.end();
    });
  });

  ollamaReq.on('error', (err) => {
    console.error('Error al conectar con Ollama:', err.message);
    if (!res.headersSent) {
      res.status(500).json({ error: `No se pudo conectar a ${OLLAMA_URL} (${err.message})` });
    } else {
      res.write(JSON.stringify({ error: err.message }));
      res.end();
    }
  });

  ollamaReq.on('timeout', () => {
    ollamaReq.destroy();
    if (!res.headersSent) {
      res.status(504).json({ error: `Timeout: El servidor ${OLLAMA_URL} no respondió` });
    }
  });

  req.on('close', () => {
    ollamaReq.destroy();
  });

  ollamaReq.write(postData);
  ollamaReq.end();
});

app.listen(PORT, () => {
  console.log(`\n==================================================`);
  console.log(`🚀 Plataforma MT.IA tipo ChatGPT lista en:`);
  console.log(`👉 http://localhost:${PORT}`);
  console.log(`🔗 Conectada al servidor Ollama: ${OLLAMA_URL}`);
  console.log(`==================================================\n`);
});

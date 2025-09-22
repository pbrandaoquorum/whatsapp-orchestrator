/**
 * Utilitários gerais para o processamento de dados clínicos
 */

/**
 * Gera um UUID v4 simples
 */
function generateUUID() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0;
    const v = c == 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

/**
 * Retorna timestamp BR para salvar no Dynamo (sem conversão para UTC)
 * Formato: "YYYY-MM-DDTHH:MM:SS"
 */
function getCurrentTimestampBR() {
  const nowString = new Date().toLocaleString("sv-SE", {
    timeZone: "America/Sao_Paulo",
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
  return nowString.replace(" ", "T");
}

/**
 * Retorna um objeto Date ajustado para America/Sao_Paulo.
 */
function getNowInSaoPaulo() {
  const tz = "America/Sao_Paulo";
  const s  = new Date().toLocaleString("sv-SE", { timeZone: tz, hour12: false });
  return new Date(s.replace(" ", "T") + "-03:00");
}

/**
 * Converte timestamp para formato de data seguro
 */
function toDateSafe(s) {
  if (!s) return null;
  // Se vier só data (YYYY-MM-DD), usa meia-noite local
  const isDateOnly = /^\d{4}-\d{2}-\d{2}$/.test(s);
  // Se já vier com TZ (Z ou ±HH:MM/±HHMM), usa direto
  const hasTZ = /([zZ]|[+\-]\d{2}:?\d{2})$/.test(s);
  const base = isDateOnly ? `${s}T00:00:00` : s.replace(' ', 'T');

  // Trate strings locais (ex.: "YYYY-MM-DDTHH:MM:SS" sem TZ) como America/Sao_Paulo
  if (!hasTZ) return new Date(`${base}-03:00`);
  return new Date(base);
}

/**
 * Parse do body do evento (API Gateway vs invocação direta)
 */
function parseEventBody(event) {
  try {
    return event.body
      ? (typeof event.body === 'string' ? JSON.parse(event.body) : event.body)
      : event;
  } catch (err) {
    throw new Error(`JSON inválido no body: ${err.message}`);
  }
}

/**
 * Valida campos obrigatórios do body
 */
function validateRequiredFields(body, requiredFields) {
  const missing = requiredFields.filter(field => !body[field]);
  if (missing.length > 0) {
    throw new Error(`Campos obrigatórios ausentes: ${missing.join(', ')}`);
  }
}

/**
 * Cria resposta HTTP padronizada
 */
function createResponse(statusCode, data, error = null) {
  const body = error 
    ? { error: error.message || error, ...(data || {}) }
    : { ...data };

  return {
    statusCode,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
    },
    body: JSON.stringify(body)
  };
}

module.exports = {
  generateUUID,
  getCurrentTimestampBR,
  getNowInSaoPaulo,
  toDateSafe,
  parseEventBody,
  validateRequiredFields,
  createResponse
};

import { 
  DynamoDBClient, 
  QueryCommand, 
  PutItemCommand, 
  UpdateItemCommand,
  GetItemCommand,
  ScanCommand
} from "@aws-sdk/client-dynamodb";
import { SESClient, SendEmailCommand } from "@aws-sdk/client-ses";
import { createClient } from 'redis';

// Inicializa o cliente do DynamoDB
const dynamoDB = new DynamoDBClient({ region: "sa-east-1" });
const sesClient = new SESClient({ region: "sa-east-1" });

// ⚠️ TODO: Mover para variável de ambiente e rotacionar a senha exposta
const REDIS_CONFIG = {
  host: 'redis-11078.c8.us-east-1-4.ec2.redns.redis-cloud.com',
  port: 11078,
  username: 'default',
  password: 'xiVN875C0UoyfMc2TtGTFDBQnp3ADR7k',
  // ssl: true, // ⚠️ Ative se TLS estiver habilitado no painel Redis Cloud
};

let redis;           // client singleton por container
let redisReady;      // promise para evitar connect concorrente

async function getRedis() {
  if (!redis) {
    redis = createClient({
      socket: {
        host: REDIS_CONFIG.host,
        port: REDIS_CONFIG.port,
        connectTimeout: 5000,
        // reconexão com backoff suave
        reconnectStrategy: (retries) => Math.min(1000, retries * 50),
        // ssl: REDIS_CONFIG.ssl, // descomente se TLS estiver ativo
      },
      username: REDIS_CONFIG.username,
      password: REDIS_CONFIG.password,
      pingInterval: 10_000, // mantém viva
      // Configurações adicionais baseadas no script Python
      database: 0, // equivalente ao db=0
    });

    redis.on("error", (e) => {
      console.error("❌ Redis error:", e);
    });

    redis.on("connect", () => {
      console.log("✅ Redis conectado");
    });

    redis.on("disconnect", () => {
      console.log("🔌 Redis desconectado");
    });

    redis.on("ready", async () => {
      try {
        // Testa a conexão similar ao script Python
        await redis.ping();
        console.log("🏓 Redis ping successful - conexão ativa");
      } catch (err) {
        console.error("❌ Redis ping failed:", err);
      }
    });

    // memoiza a tentativa de conectar (previne múltiplos connects)
    redisReady = redis.connect().catch((err) => {
      // zera os singletons se falhar, para permitir nova tentativa depois
      redis = undefined;
      redisReady = undefined;
      throw err;
    });
  }

  if (redisReady) {
    await redisReady;
  }
  return redis;
}

/**
 * Envia notificação de erro por email via SES
 */
async function sendErrorNotification(error, context = {}) {
  try {
    const timestamp = new Date().toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' });
    const lambdaName = "getScheduleStarted";
    
    const subject = `[ERRO] Lambda ${lambdaName} - ${timestamp}`;
    const htmlBody = `
      <h3>Erro no Lambda ${lambdaName}</h3>
      <p><strong>Data/Hora:</strong> ${timestamp}</p>
      <p><strong>Erro:</strong> ${error.message || error}</p>
      <p><strong>Stack:</strong></p>
      <pre>${error.stack || 'Stack não disponível'}</pre>
      <p><strong>Contexto:</strong></p>
      <pre>${JSON.stringify(context, null, 2)}</pre>
    `;
    
    const textBody = `
Erro no Lambda ${lambdaName}

Data/Hora: ${timestamp}
Erro: ${error.message || error}
Stack: ${error.stack || 'Stack não disponível'}
Contexto: ${JSON.stringify(context, null, 2)}
    `;

    const emailParams = {
      Source: "p.brandao@quorumsaude.com",
      Destination: {
        ToAddresses: ["p.brandao@quorumsaude.com", "m.rosa@quorumsaude.com"]
      },
      Message: {
        Subject: {
          Data: subject,
          Charset: "UTF-8"
        },
        Body: {
          Html: {
            Data: htmlBody,
            Charset: "UTF-8"
          },
          Text: {
            Data: textBody,
            Charset: "UTF-8"
          }
        }
      }
    };

    await sesClient.send(new SendEmailCommand(emailParams));
    console.log(`📧 Email de erro enviado com sucesso para ${lambdaName}`);
    
  } catch (emailError) {
    console.error(`❌ Erro ao enviar email de notificação:`, emailError);
  }
}

/**
 * Gera uma UUID de forma simples.
 */
function generateUUID() {
  let dt = new Date().getTime();
  const uuid = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
    const r = (dt + Math.random() * 16) % 16 | 0;
    dt = Math.floor(dt / 16);
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
  return uuid;
}

/**
 * Calcula [t0,t1] do turno a partir de day, start, finish.
 * Mantém a mesma convenção do código (Date local + regras de 24h / cruza-meia-noite).
 */
function computeScheduleInterval(day, start, finish) {
  const [d, m, y] = (day || "").split("/").map(Number);
  const [sh, sm] = (start || "").split(":").map(Number);
  const [fh, fm] = (finish || "").split(":").map(Number);
  if ([d, m, y, sh, sm, fh, fm].some(isNaN)) return null;

  let t0 = new Date(y, m - 1, d, sh, sm);
  let t1 = new Date(y, m - 1, d, fh, fm);

  const startTotal = sh * 60 + sm;
  const finishTotal = fh * 60 + fm;
  const is24HourShift = startTotal === finishTotal;

  if (is24HourShift) {
    t1 = new Date(t0.getTime() + 24 * 60 * 60000);
  } else if (finishTotal < startTotal) {
    // cruza a meia-noite
    t1.setDate(t1.getDate() + 1);
  }

  return { t0, t1 };
}

/**
 * Retorna o schedule anterior mais próximo (terminado antes de "now"),
 * ignorando cancelados e deletados.
 */
function findPreviousScheduleForCaregiver(schedules, now) {
  const candidates = [];
  for (const s of schedules) {
    if (!s.day || !s.start || !s.finish) continue;
    const respLower = (s.response || "").toLowerCase();
    if (respLower === "cancelado") continue;
    
    // Ignora schedules deletados
    if (s.deletedAt) {
      console.log(`🗑️  Schedule anterior ${s.scheduleID} foi deletado em ${s.deletedAt} - ignorando`);
      continue;
    }

    const interval = computeScheduleInterval(s.day, s.start, s.finish);
    if (!interval) continue;

    // Considera "anterior" os que JÁ terminaram
    if (interval.t1.getTime() < now.getTime()) {
      candidates.push({ s, endTs: interval.t1.getTime() });
    }
  }

  // Mais recente no passado
  candidates.sort((a, b) => b.endTs - a.endTs);
  return candidates.length ? candidates[0].s : null;
}

/**
 * Limpa os dados do chat memory no Redis para um sessionID específico
 */
async function clearRedisChatMemory(sessionID) {
  try {
    const client = await getRedis();
    const exists = await client.exists(sessionID);
    if (exists) {
      await client.del(sessionID);
      console.log(`✅ Redis chat memory limpo para sessionID: ${sessionID}`);
      return true;
    }
    console.log(`ℹ️ Nenhum chat memory para sessionID: ${sessionID}`);
    return false;
  } catch (err) {
    console.error(`❌ Erro Redis clear ${sessionID}:`, err);
    return false;
  }
}

/**
 * Limpa todas as conexões Redis relacionadas a um usuário específico
 * Busca por padrões como: phoneNumber, caregiverID, etc.
 */
async function clearAllUserConnections(phoneNumber, caregiverID = null) {
  try {
    const client = await getRedis();
    let keysDeleted = 0;
    
    // Lista de padrões para buscar chaves relacionadas ao usuário
    const searchPatterns = [];
    
    if (phoneNumber) {
      // Adiciona o phoneNumber direto e variações com/sem +
      searchPatterns.push(phoneNumber);
      if (phoneNumber.startsWith('+')) {
        searchPatterns.push(phoneNumber.substring(1));
      } else {
        searchPatterns.push(`+${phoneNumber}`);
      }
    }
    
    if (caregiverID) {
      searchPatterns.push(caregiverID);
    }
    
    console.log(`🔍 Buscando conexões Redis para padrões: ${searchPatterns.join(', ')}`);
    
    // Para cada padrão, busca e deleta chaves correspondentes
    for (const pattern of searchPatterns) {
      try {
        // Busca chaves que contenham o padrão
        const keys = await client.keys(`*${pattern}*`);
        
        if (keys.length > 0) {
          console.log(`🔑 Encontradas ${keys.length} chaves para padrão '${pattern}': ${keys.join(', ')}`);
          
          // Deleta todas as chaves encontradas
          for (const key of keys) {
            await client.del(key);
            keysDeleted++;
            console.log(`🗑️  Chave deletada: ${key}`);
          }
        } else {
          console.log(`ℹ️  Nenhuma chave encontrada para padrão '${pattern}'`);
        }
      } catch (patternError) {
        console.error(`❌ Erro ao buscar padrão '${pattern}':`, patternError);
      }
    }
    
    if (keysDeleted > 0) {
      console.log(`✅ Total de ${keysDeleted} conexões Redis limpas para o usuário`);
    } else {
      console.log(`ℹ️  Nenhuma conexão Redis anterior encontrada para o usuário`);
    }
    
    return keysDeleted;
  } catch (err) {
    console.error(`❌ Erro ao limpar conexões Redis do usuário:`, err);
    return 0;
  }
}

/**
 * Zera o status de todos os agentes para um dado sessionID
 */
async function resetAgentsStatus(sessionID, timestamp) {
  const item = {
    sessionID:          { S: sessionID },
    AgenteEscalas:      { M: { status: { S: "" }, motivo: { S: "" }, lastUpdateTimestamp: { S: timestamp } } },
    AgenteSinaisVitais: { M: { status: { S: "" }, motivo: { S: "" }, lastUpdateTimestamp: { S: timestamp } } },
    AgenteBlocoDeNotas: { M: { status: { S: "" }, motivo: { S: "" }, lastUpdateTimestamp: { S: timestamp } } },
    AgenteFinalizar:    { M: { status: { S: "" }, motivo: { S: "" }, lastUpdateTimestamp: { S: timestamp } } },
  };
  await dynamoDB.send(new PutItemCommand({
    TableName: "AgentsStatus",
    Item: item
  }));
  
  // Limpa o chat memory do Redis após resetar os agentes
  console.log(`🔄 Limpando Redis chat memory para sessionID: ${sessionID}`);
  await clearRedisChatMemory(sessionID);
  
  return JSON.stringify({
    sessionID,
    AgenteEscalas:      { status: "", motivo: "", lastUpdateTimestamp: timestamp },
    AgenteSinaisVitais: { status: "", motivo: "", lastUpdateTimestamp: timestamp },
    AgenteBlocoDeNotas: { status: "", motivo: "", lastUpdateTimestamp: timestamp },
    AgenteFinalizar:    { status: "", motivo: "", lastUpdateTimestamp: timestamp },
  });
}

export const handler = async (event, context) => {
  context.callbackWaitsForEmptyEventLoop = false;
  console.log("Received event:", JSON.stringify(event, null, 2));

  try {
    // Parse do input
    let input;
    try {
      input = event.body 
        ? (typeof event.body === "string" ? JSON.parse(event.body) : event.body)
        : event;
    } catch (error) {
      console.error("Erro ao interpretar o input:", error);
      await sendErrorNotification(error, { event, step: "parse_input" });
      return { statusCode: 400, body: JSON.stringify({ error: "Request body inválido" }) };
    }

  // Extrai identificadores
  const rawPhoneNumber = input.phoneNumber ? String(input.phoneNumber).trim() : null;
  // Normaliza phoneNumber removendo o + se existir para uso como sessionID
  const phoneNumber = rawPhoneNumber && rawPhoneNumber.startsWith('+') 
    ? rawPhoneNumber.substring(1) 
    : rawPhoneNumber;
  
  console.log(`🔍 [DEBUG] Phone number normalization: "${rawPhoneNumber}" → "${phoneNumber}"`);
  
  let caregiverIdentifier = input.caregiverIdentifier
    || input.caregiverID
    || (input.caregiverId && input.caregiverId.caregiverID)
    || null;

  // Timestamp para atualização de agentes
  const lastUpdateTimestamp = new Date().toLocaleString("sv-SE", {
    timeZone: "America/Sao_Paulo",
    hour12: false,
    year:   "numeric",
    month:  "2-digit",
    day:    "2-digit",
    hour:   "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).replace(" ", "T");

  // 1) Recupera ou inicializa AgentsStatus
  let agentsStatus = "{}";
  try {
    if (phoneNumber) {
      const getAgentsParams = {
        TableName: "AgentsStatus",
        Key: { sessionID: { S: phoneNumber } }
      };
      const agentsData = await dynamoDB.send(new GetItemCommand(getAgentsParams));
      if (agentsData.Item && Object.keys(agentsData.Item).length > 0) {
        agentsStatus = JSON.stringify(agentsData.Item);
      } else {
        agentsStatus = await resetAgentsStatus(phoneNumber, lastUpdateTimestamp);
      }
    }
  } catch (err) {
    console.error("Erro ao recuperar/inicializar AgentsStatus:", err);
    agentsStatus = "{}";
  }

  // 2) Busca caregiver por phoneNumber, se fornecido
  let caregiverInfo = { firstName: null, fullName: null, company: null, cooperative: null, checkID: null, checkLGPD: null };
  if (phoneNumber) {
    try {
      const result = await dynamoDB.send(new QueryCommand({
        TableName: "Caregivers",
        IndexName: "phoneNumber-index",
        KeyConditionExpression: "#ph = :phVal",
        ExpressionAttributeNames: { "#ph": "phoneNumber", "#fn": "firstName", "#fn2": "fullName", "#comp": "company", "#coop": "cooperative", "#cid": "checkID", "#clgpd": "checkLGPD" },
        ExpressionAttributeValues: { ":phVal": { S: phoneNumber } },
        ProjectionExpression: "caregiverID, #fn, #fn2, #comp, #coop, #cid, #clgpd"
      }));
      if (result.Items && result.Items.length > 0) {
        const rec = result.Items[0];
        caregiverIdentifier = rec.caregiverID?.S || caregiverIdentifier;
        caregiverInfo = {
          firstName:   rec.firstName?.S ?? null,
          fullName:    rec.fullName?.S  ?? null,
          company:     rec.company?.S   ?? null,
          cooperative: rec.cooperative?.S ?? null,
          checkID:     (rec.checkID && "BOOL" in rec.checkID) ? rec.checkID.BOOL : null,
          checkLGPD:   (rec.checkLGPD && "BOOL" in rec.checkLGPD) ? rec.checkLGPD.BOOL : null
        };
      } else {
        return {
          statusCode: 200,
          body: JSON.stringify({
            caregiverID: caregiverIdentifier,
            shiftAllow: false,
            caregiverNotFound: true,
            message: "Nenhum schedule encontrado para este caregiver",
            checkID: null,
            checkLGPD: null,
            caregiverName: null,
            cooperative: null,
            company: null
          })
        };
      }
    } catch (err) {
      console.error("Erro ao consultar phoneNumber-index:", err);
      return {
        statusCode: 200,
        body: JSON.stringify({
          caregiverID: caregiverIdentifier,
          shiftAllow: false,
          caregiverNotFound: false,
          message: "Nenhum schedule encontrado para este caregiver",
          // => campos adicionais pedidos
          checkID:   caregiverInfo.checkID ?? null,
          checkLGPD: caregiverInfo.checkLGPD ?? null,
          caregiverName: caregiverInfo.fullName ?? caregiverInfo.firstName ?? null,
          cooperative: caregiverInfo.cooperative ?? null,
          company: caregiverInfo.company ?? null
        })
      };
    }
  }

  // 3) Se faltar dados, busca por PK caregiverID
  if ((!caregiverInfo.firstName || !caregiverInfo.fullName) && caregiverIdentifier) {
    try {
      const getResult = await dynamoDB.send(new GetItemCommand({
        TableName: "Caregivers",
        Key: { caregiverID: { S: caregiverIdentifier } },
        ProjectionExpression: "firstName, fullName, company, cooperative, checkID, checkLGPD"
      }));
      if (getResult.Item) {
        caregiverInfo = {
          firstName:    getResult.Item.firstName?.S ?? caregiverInfo.firstName,
          fullName:     getResult.Item.fullName?.S  ?? caregiverInfo.fullName,
          company:      getResult.Item.company?.S   ?? caregiverInfo.company,
          cooperative:  getResult.Item.cooperative?.S ?? caregiverInfo.cooperative,
          checkID:      (getResult.Item.checkID && "BOOL" in getResult.Item.checkID) ? getResult.Item.checkID.BOOL : caregiverInfo.checkID,
          checkLGPD:    (getResult.Item.checkLGPD && "BOOL" in getResult.Item.checkLGPD) ? getResult.Item.checkLGPD.BOOL : caregiverInfo.checkLGPD
        };
      }
    } catch (err) {
      console.error("Erro ao buscar caregiver pela PK:", err);
    }
  }

  if (!caregiverIdentifier) {
    return { statusCode: 400, body: JSON.stringify({ error: "Parâmetro caregiverIdentifier é obrigatório" }) };
  }

  // 4) Consulta WorkSchedules via GSI 'caregiverID-index'
  let schedules = [];
  try {
    const res = await dynamoDB.send(new QueryCommand({
      TableName: "WorkSchedules",
      IndexName: "caregiverID-index",
      KeyConditionExpression: "caregiverID = :cgID",
      ExpressionAttributeValues: { ":cgID": { S: caregiverIdentifier } }
    }));
    schedules = (res.Items || [])
      .map(item => ({
        scheduleID:      item.scheduleID?.S,
        caregiverID:     item.caregiverID?.S,
        patientID:       item.patientID?.S,
        day:             item.day?.S,
        start:           item.start?.S,
        finish:          item.finish?.S,
        response:        item.response?.S,
        finishReport:    item.finishReport?.BOOL || false,
        finishReminderSent: item.finishReminderSent?.BOOL || false,
        scheduleStarted: item.scheduleStarted?.BOOL || false,
        company:         item.company?.S,
        deletedAt:       item.deletedAt?.S || null
      }))
      .filter(schedule => {
        // Filtra schedules que têm deletedAt (schedules deletados)
        if (schedule.deletedAt) {
          console.log(`🗑️  Schedule ${schedule.scheduleID} foi deletado em ${schedule.deletedAt} - ignorando`);
          return false;
        }
        return true;
      });
    if (schedules.length === 0) {
      return {
        statusCode: 200,
        body: JSON.stringify({
          caregiverID: caregiverIdentifier,
          shiftAllow: false,
          caregiverNotFound: false,
          message: "Nenhum schedule encontrado para este caregiver",
          checkID:   caregiverInfo.checkID ?? null,
          checkLGPD: caregiverInfo.checkLGPD ?? null,
          caregiverName: caregiverInfo.fullName ?? caregiverInfo.firstName ?? null,
          cooperative: caregiverInfo.cooperative ?? null,
          company: caregiverInfo.company ?? null
        })
      };
    }
  } catch (err) {
    console.error("Erro ao consultar WorkSchedules:", err);
    return {
      statusCode: 200,
      body: JSON.stringify({
        caregiverID: caregiverIdentifier,
        shiftAllow: false,
        caregiverNotFound: false,
        message: "Nenhum schedule encontrado para este caregiver",
        checkID:   caregiverInfo.checkID ?? null,
        checkLGPD: caregiverInfo.checkLGPD ?? null,
        caregiverName: caregiverInfo.fullName ?? caregiverInfo.firstName ?? null,
        cooperative: caregiverInfo.cooperative ?? null,
        company: caregiverInfo.company ?? null
      })
    };
  }

      // 5) Identifica turno ativo (confirmado ou aguardando resposta)
  const now = new Date(new Date().toLocaleString("sv-SE", { timeZone: "America/Sao_Paulo", hour12: false }).replace(" ", "T"));
  let shiftAllow = false;
  let selectedScheduleID = null;
  let selectedPatientID = null;
  let selectedScheduleStarted = null;
  let selectedDay = null;
  let selectedStart = null;
  let selectedFinish = null;
  let selectedCompany = null;
  let selectedResponse = null;

  // Coleta todos os schedules elegíveis primeiro
  const eligibleSchedules = [];

  for (const s of schedules) {
    if (s.finishReport) continue;
    const { day, start, finish, response, scheduleID, patientID, company, scheduleStarted } = s;
    if (!day || !start || !finish || !response) continue;
    const respLower = response.toLowerCase();
    const compUpper = company ? company.toUpperCase() : "";

    // Se for HOMEMATER ou PLURALCARE, só permite "confirmado"
    if (compUpper === "HOMEMATER" || compUpper === "PLURALCARE") {
      if (respLower !== "confirmado" && respLower !== "aguardando resposta" ) continue;
    } else {
      // Para as demais empresas, mantém permitido "confirmado" ou "aguardando resposta"
      if (!["confirmado", "aguardando resposta"].includes(respLower)) continue;
    }

    const [d, m, y] = day.split("/").map(Number);
    const [sh, sm] = start.split(":").map(Number);
    const [fh, fm] = finish.split(":").map(Number);
    if ([d,m,y,sh,sm,fh,fm].some(isNaN)) continue;
    let t0 = new Date(y, m-1, d, sh, sm);
    let t1 = new Date(y, m-1, d, fh, fm);

    const startTotal = sh * 60 + sm;
    const finishTotal = fh * 60 + fm;
    const is24HourShift = startTotal === finishTotal;

    if (is24HourShift) {
      // turno de 24h: soma 24h (1440 minutos)
      t1 = new Date(t0.getTime() + 24 * 60 * 60000);
    } else if (finishTotal < startTotal) {
      // cruza meia-noite
      t1.setDate(t1.getDate() + 1);
    }

    const earliest = new Date(t0.getTime() - 3*3600000);
    const latest   = new Date(t1.getTime() + 4*3600000);

    if (now >= earliest && now <= latest) {
      // Adiciona à lista de elegíveis com timestamp para ordenação
      eligibleSchedules.push({
        scheduleData: s,
        day, start, finish, response, scheduleID, patientID, company, scheduleStarted,
        startTimestamp: t0.getTime() // Para ordenação
      });
    }
  }

  // Se há schedules elegíveis, seleciona o mais recente
  if (eligibleSchedules.length > 0) {
    console.log(`🔍 [DEBUG] Encontrados ${eligibleSchedules.length} schedules elegíveis. Selecionando o mais recente...`);
    
    // Ordena por data/hora de início (mais recente primeiro)
    eligibleSchedules.sort((a, b) => b.startTimestamp - a.startTimestamp);
    
    // Seleciona o mais recente (primeiro da lista ordenada)
    const selected = eligibleSchedules[0];
    
    shiftAllow = true;
    selectedScheduleID = selected.scheduleID;
    selectedPatientID = selected.patientID;
    selectedScheduleStarted = selected.scheduleStarted;
    selectedDay = selected.day;
    selectedStart = selected.start;
    selectedFinish = selected.finish;
    selectedCompany = selected.company;
    selectedResponse = selected.response;
    
    console.log(`✅ [DEBUG] Schedule mais recente selecionado: ${selectedScheduleID} (${selectedDay} ${selectedStart})`);
    
    // Log dos schedules elegíveis para debug
    eligibleSchedules.forEach((eligible, index) => {
      const indicator = index === 0 ? "👑 SELECIONADO" : "   alternativa";
      console.log(`   ${indicator}: ${eligible.scheduleID} (${eligible.day} ${eligible.start})`);
    });
  }

      // 6) Se não encontrou turno ativo, mas há cancelamentos, escolhe o mais recente
  if (!selectedScheduleID) {
    console.log(`🔍 [DEBUG] Nenhum schedule ativo encontrado. Buscando por schedules cancelados...`);
    
    // 6.1) filtra só os schedules cancelados
    const cancelledList = schedules
      .filter(s => s.response?.toLowerCase() === "cancelado")
      .map(s => ({
        ...s,
        // converte day+finish (ou start) em timestamp para ordenar
        ts: (() => {
          const [d, m, y] = s.day.split("/").map(Number);
          const [hh, mm] = (s.finish || s.start || "00:00").split(":").map(Number);
          return new Date(y, m - 1, d, hh, mm).getTime();
        })()
      }));

    if (cancelledList.length > 0) {
      console.log(`🔍 [DEBUG] Encontrados ${cancelledList.length} schedules cancelados. Selecionando o mais recente...`);
      
      // 6.2) ordena decrescente e pega o primeiro (mais recente)
      cancelledList.sort((a, b) => b.ts - a.ts);
      const recent = cancelledList[0];

      selectedScheduleID       = recent.scheduleID;
      selectedPatientID        = recent.patientID;
      selectedScheduleStarted  = recent.scheduleStarted;
      selectedDay              = recent.day;
      selectedStart            = recent.start;
      selectedFinish           = recent.finish;
      selectedCompany          = recent.company;
      selectedResponse         = recent.response;
      // shiftAllow continua false
      
      console.log(`⚠️ [DEBUG] Schedule cancelado mais recente selecionado: ${selectedScheduleID} (${selectedDay} ${selectedStart}) - shiftAllow=false`);
      
      // Log dos schedules cancelados para debug
      cancelledList.forEach((cancelled, index) => {
        const indicator = index === 0 ? "👑 SELECIONADO" : "   alternativa";
        console.log(`   ${indicator}: ${cancelled.scheduleID} (${cancelled.day} ${cancelled.start}) - CANCELADO`);
      });
    } else {
      console.log(`ℹ️ [DEBUG] Nenhum schedule cancelado encontrado.`);
    }
  }
  

  // 7) Cria ou recupera report apenas se não for cancelado nem deletado
  let reportID = null;
  let reportDate = null;
  let message = null;

  if (selectedScheduleID && selectedResponse?.toLowerCase() !== 'cancelado') {
    if (selectedScheduleStarted) {
      // 7.1) Schedule já marcado como iniciado — tenta recuperar, senão cria só o report
      const qr = await dynamoDB.send(new QueryCommand({
        TableName: 'Reports',
        IndexName: 'scheduleID-index',
        KeyConditionExpression: 'scheduleID = :sid',
        ExpressionAttributeValues: { ':sid': { S: selectedScheduleID } },
      }));

      if (qr.Items && qr.Items.length > 0) {
        // já existe
        const rec = qr.Items[0];
        reportID     = rec.reportID.S;
        reportDate   = rec.reportDate.S;
        caregiverIdentifier = rec.caregiverID?.S || caregiverIdentifier;
        selectedPatientID   = rec.patientID?.S   || selectedPatientID;
        message      = 'Relatório já iniciado; dados recuperados com sucesso';
      } else {
        // não existe → cria apenas o report (não toca em WorkSchedules)
        reportDate = new Date().toLocaleString('sv-SE', {
          timeZone: 'America/Sao_Paulo',
          hour12: false,
        }).replace(' ', 'T');
        reportID   = generateUUID();

        await dynamoDB.send(new PutItemCommand({
          TableName: 'Reports',
          Item: {
            reportID:   { S: reportID },
            reportDate: { S: reportDate },
            scheduleID: { S: selectedScheduleID },
            company:    { S: selectedCompany || '' },
          },
        }));
        await dynamoDB.send(new UpdateItemCommand({
          TableName: 'Reports',
          Key: { reportID: { S: reportID }, reportDate: { S: reportDate } },
          UpdateExpression: 'SET caregiverID = :cg, patientID = :pt',
          ExpressionAttributeValues: {
            ':cg': { S: caregiverIdentifier },
            ':pt': { S: selectedPatientID },
          },
        }));
        message = 'Relatório criado (scheduleStarted já estava true)';
      }

    } else {
      // 7.2) Primeiro início do turno — cria report e só então marca scheduleStarted=true
      reportDate = new Date().toLocaleString('sv-SE', {
        timeZone: 'America/Sao_Paulo',
        hour12: false,
      }).replace(' ', 'T');
      reportID   = generateUUID();

      try {
        // 🔄 PRIMEIRA INTERAÇÃO: Limpa todas as conexões Redis anteriores do usuário
        console.log(`🧹 Primeira interação detectada - limpando conexões Redis anteriores do usuário`);
        await clearAllUserConnections(phoneNumber, caregiverIdentifier);
        
        await dynamoDB.send(new PutItemCommand({
          TableName: 'Reports',
          Item: {
            reportID:   { S: reportID },
            reportDate: { S: reportDate },
            scheduleID: { S: selectedScheduleID },
            company:    { S: selectedCompany || '' },
          },
        }));
        await dynamoDB.send(new UpdateItemCommand({
          TableName: 'Reports',
          Key: { reportID: { S: reportID }, reportDate: { S: reportDate } },
          UpdateExpression: 'SET caregiverID = :cg, patientID = :pt',
          ExpressionAttributeValues: {
            ':cg': { S: caregiverIdentifier },
            ':pt': { S: selectedPatientID },
          },
        }));
        await dynamoDB.send(new UpdateItemCommand({
          TableName: 'WorkSchedules',
          Key: { scheduleID: { S: selectedScheduleID } },
          UpdateExpression: 'SET scheduleStarted = :trueVal',
          ExpressionAttributeValues: { ':trueVal': { BOOL: true } },
        }));
        message      = 'Relatório criado e scheduleStarted atualizado com sucesso';
        agentsStatus = await resetAgentsStatus(phoneNumber, lastUpdateTimestamp);
      } catch (err) {
        console.error('Erro ao criar/atualizar report:', err);
        return {
          statusCode: 500,
          body: JSON.stringify({
            error: 'Falha ao criar ou atualizar report',
            details: err.message,
          }),
        };
      }
    }

  } else if (selectedScheduleID && selectedResponse?.toLowerCase() === 'cancelado') {
    message = 'Plantão cancelado';
  } else {
    message = 'Nenhum schedule ativo encontrado; report não criado';
  }  

  // 8) Busca dados do paciente
  let patientInfo = { firstName: null, fullName: null };
  if (selectedPatientID) {
    try {
      const pr = await dynamoDB.send(new GetItemCommand({
        TableName: "Patients",
        Key: { patientID: { S: selectedPatientID } }
      }));
      if (pr.Item) {
        patientInfo = {
          firstName: pr.Item.firstName?.S,
          fullName:  pr.Item.fullName?.S
        };
      }
    } catch (err) {
      console.error("Erro ao buscar patient:", err);
    }
  }

  // 9) Monta substituteInfo
  let substituteInfo = "";
  if (selectedPatientID) {
    try {
      const scanRes = await dynamoDB.send(new ScanCommand({
        TableName: "Caregivers",
        FilterExpression: "contains(patientsIdentifiers, :p)",
        ExpressionAttributeValues: { ":p": { S: selectedPatientID } }
      }));
      const substitutes = (scanRes.Items || [])
        .filter(item => item.caregiverID?.S !== caregiverIdentifier)
        .map(item => ({
          caregiverIdentifier: item.caregiverID?.S,
          caregiverName:       item.fullName?.S
        }));
      substituteInfo = substitutes.length
        ? JSON.stringify(substitutes)
        : "Nao há profissionais substitutos";
    } catch (err) {
      console.error("Erro ao montar substituteInfo:", err);
      substituteInfo = "Nao há profissionais substitutos";
    }
  }

  // === (NOVO) 5b) Schedule anterior e paciente anterior ===
  let previousScheduleID = null;
  let previousPatientID = null;
  let previousPatientFullName = null;
  let previousDay = null;
  let previousStart = null;
  let previousFinish = null;

  try {
    const prev = findPreviousScheduleForCaregiver(schedules, now);
    if (prev) {
      previousScheduleID = prev.scheduleID || null;
      previousPatientID  = prev.patientID  || null;
      previousDay        = prev.day        || null;
      previousStart      = prev.start      || null;
      previousFinish     = prev.finish     || null;

      if (previousPatientID) {
        const prevPatientRes = await dynamoDB.send(new GetItemCommand({
          TableName: "Patients",
          Key: { patientID: { S: previousPatientID } },
          ProjectionExpression: "fullName"
        }));
        previousPatientFullName = prevPatientRes.Item?.fullName?.S || null;
      }
      console.log("🕓 [DEBUG] Schedule anterior encontrado:", {
        previousScheduleID, previousPatientID, previousDay, previousStart, previousFinish, previousPatientFullName
      });
    } else {
      console.log("ℹ️ [DEBUG] Nenhum schedule anterior encontrado para este caregiver.");
    }
  } catch (e) {
    console.error("❌ [DEBUG] Erro ao calcular schedule/paciente anterior:", e);
  }

    // 10) Retorna todos os dados
    const response = {
      statusCode: 200,
      body: JSON.stringify({
        caregiverID:          caregiverIdentifier,
        caregiverFirstName:   caregiverInfo.firstName,
        caregiverFullName:    caregiverInfo.fullName,
        caregiverCompany:     caregiverInfo.company,
        caregiverCooperative: caregiverInfo.cooperative,
        scheduleID:           selectedScheduleID,
        day:                  selectedDay,
        start:                selectedStart,
        finish:               selectedFinish,
        shiftAllow:           shiftAllow,
        response:             selectedResponse,  // NOVO: Status do plantão ("confirmado", "aguardando resposta", "cancelado")
        patientID:            selectedPatientID,
        patientFirstName:     patientInfo.firstName,
        patientFullName:      patientInfo.fullName,
        scheduleStarted:      selectedScheduleStarted,
        reportID:             reportID,
        reportDate:           reportDate,
        message:              message,
        timestampMessage:     lastUpdateTimestamp,
        substituteInfo:       substituteInfo,
        agentsStatus:         agentsStatus,
        finishReminderSent:   schedules.find(s => s.scheduleID === selectedScheduleID)?.finishReminderSent || false,
        caregiverNotFound:    false,
        // --- NOVOS CAMPOS (schedule/paciente anterior) ---
        previousScheduleID:     previousScheduleID,
        previousPatientID:      previousPatientID,
        previousPatientFullName: previousPatientFullName,
        previousDay:            previousDay,
        previousStart:          previousStart,
        previousFinish:         previousFinish,
        checkID:                (caregiverInfo.checkID ?? null),
        checkLGPD:              (caregiverInfo.checkLGPD ?? null),
        // também entregue os campos pedidos, sempre:
        caregiverName:          caregiverInfo.fullName ?? caregiverInfo.firstName ?? null,
        cooperative:            caregiverInfo.cooperative ?? null,
        company:                caregiverInfo.company ?? null
      }),
    };
    
    return response;
  } catch (error) {
    console.error("Erro geral no handler getScheduleStarted:", error);
    await sendErrorNotification(error, { event, step: "handler_execution" });
    return {
      statusCode: 500,
      body: JSON.stringify({
        error: "Erro interno do servidor",
        message: "Ocorreu um erro durante o processamento da requisição"
      })
    };
  }
};

/**
 * Handler para processamento de sinais vitais
 */

const { 
  dynamoDB, 
  TABLES,
  getCurrentSymptomReport,
  getCaregiverData,
  incrementQtVSMeasures
} = require('/opt/nodejs/dynamoHelpers');

const { 
  validateVitalSignsRanges,
  processSymptomReport,
  getAllMeasures,
  computeHistoricStats,
  calculateAbsoluteScore,
  computeZScores,
  computeRelativeScore,
  computeRelativeBreakdown
} = require('/opt/nodejs/vitalSignsProcessor');

const { 
  sendWebhookAlert 
} = require('/opt/nodejs/alertProcessor');

const { 
  generateUUID 
} = require('/opt/nodejs/utils');

const { processAlertsAndSave } = require('../services/alertService');

const { 
  DynamoDBClient, 
  UpdateItemCommand, 
  PutItemCommand, 
  GetItemCommand 
} = require('@aws-sdk/client-dynamodb');

/**
 * Processa sinais vitais com toda a lógica completa do updateVitalSignsTable
 */
async function processVitalSignsComplete(body, regras = []) {
  const { reportID, reportDate, scheduleID } = body;
  const vitalSignsData = body.vitalSignsData || body;
  
  // Converte regras em mapa para acesso rápido
  let symptomConfig = {};
  if (Array.isArray(regras) && regras.length > 0) {
    for (const regra of regras) {
      if (regra?.sintoma && typeof regra.pontuacao === 'number') {
        symptomConfig[regra.sintoma] = {
          score: regra.pontuacao,
          freq: regra.freq === 'Sim',
        };
      }
    }
    console.log(`📋 Regras recebidas: ${Object.keys(symptomConfig).length} sintomas mapeados`);
  }

  // 1) Company
  let company = '';
  if (scheduleID) {
    const wsResp = await dynamoDB.send(new GetItemCommand({
      TableName: TABLES.WORK_SCHEDULES,
      Key: { scheduleID: { S: scheduleID } },
      ProjectionExpression: 'company'
    }));
    company = wsResp.Item?.company?.S || company;
  }

  // 2) IDs e timestamp
  const vitalSignsID = generateUUID();
  const now = new Date();
  now.setHours(now.getHours() - 3);
  const isoNow = now.toISOString();
  const timestamp = isoNow.replace('Z', '-03:00');
  const [dateISO, timeWithMs] = isoNow.split('T');
  const time = timeWithMs.split('.')[0];
  
  // Converte data para formato DD/MM/YYYY
  const [year, month, dayNum] = dateISO.split('-');
  const day = `${dayNum}/${month}/${year}`;

  // 3) Concentrator
  let concentrator = false;
  if (vitalSignsData.oxygenConcentrator === true || vitalSignsData.oxygenConcentrator === 'Sim') {
    concentrator = true;
  }

  // 4) Caregiver Data
  let caregiverID = vitalSignsData.caregiverIdentifier;
  let caregiverName = '', caregiverCompany = '', caregiverCooperative = '';
  
  // Se não tem caregiverID, tenta buscar nas tabelas Reports ou WorkSchedules
  if (!caregiverID && (reportID || scheduleID)) {
    console.log('🔍 caregiverID não informado, buscando nas tabelas...');
    
    // Primeiro tenta na tabela Reports
    if (reportID && reportDate) {
      try {
        const reportResp = await dynamoDB.send(new GetItemCommand({
          TableName: TABLES.REPORTS,
          Key: { 
            reportID: { S: reportID },
            reportDate: { S: reportDate }
          },
          ProjectionExpression: 'caregiverID'
        }));
        caregiverID = reportResp.Item?.caregiverID?.S;
        console.log('📋 caregiverID encontrado na tabela Reports:', caregiverID);
      } catch (reportError) {
        console.warn('⚠️ Erro ao buscar caregiverID na tabela Reports:', reportError.message);
      }
    }
    
    // Se ainda não encontrou, tenta na tabela WorkSchedules
    if (!caregiverID && scheduleID) {
      try {
        const scheduleResp = await dynamoDB.send(new GetItemCommand({
          TableName: TABLES.WORK_SCHEDULES,
          Key: { scheduleID: { S: scheduleID } },
          ProjectionExpression: 'caregiverID'
        }));
        caregiverID = scheduleResp.Item?.caregiverID?.S;
        console.log('📅 caregiverID encontrado na tabela WorkSchedules:', caregiverID);
      } catch (scheduleError) {
        console.warn('⚠️ Erro ao buscar caregiverID na tabela WorkSchedules:', scheduleError.message);
      }
    }
  }
  
  // Busca dados completos do caregiver se temos o ID
  if (caregiverID) {
    try {
      const caregiverData = await getCaregiverData(caregiverID);
      caregiverName = caregiverData.fullName || '';
      caregiverCompany = caregiverData.company || '';
      caregiverCooperative = caregiverData.cooperative || '';
      console.log('✅ Dados do caregiver recuperados:', { caregiverID, caregiverName });
    } catch (caregiverError) {
      console.warn('⚠️ Erro ao buscar dados do caregiver:', caregiverError.message);
      // Mantém o ID mas sem dados completos
    }
  } else {
    console.warn('⚠️ caregiverID não encontrado em nenhuma fonte');
  }

  // 5) Patient Data
  let patientID = vitalSignsData.patientIdentifier;
  let patientName = '';
  
  // Se não tem patientID, tenta buscar nas tabelas Reports ou WorkSchedules
  if (!patientID && (reportID || scheduleID)) {
    console.log('🔍 patientID não informado, buscando nas tabelas...');
    
    // Primeiro tenta na tabela Reports
    if (reportID && reportDate) {
      try {
        const reportResp = await dynamoDB.send(new GetItemCommand({
          TableName: TABLES.REPORTS,
          Key: { 
            reportID: { S: reportID },
            reportDate: { S: reportDate }
          },
          ProjectionExpression: 'patientID'
        }));
        patientID = reportResp.Item?.patientID?.S;
        console.log('📋 patientID encontrado na tabela Reports:', patientID);
      } catch (reportError) {
        console.warn('⚠️ Erro ao buscar patientID na tabela Reports:', reportError.message);
      }
    }
    
    // Se ainda não encontrou, tenta na tabela WorkSchedules
    if (!patientID && scheduleID) {
      try {
        const scheduleResp = await dynamoDB.send(new GetItemCommand({
          TableName: TABLES.WORK_SCHEDULES,
          Key: { scheduleID: { S: scheduleID } },
          ProjectionExpression: 'patientID'
        }));
        patientID = scheduleResp.Item?.patientID?.S;
        console.log('📅 patientID encontrado na tabela WorkSchedules:', patientID);
      } catch (scheduleError) {
        console.warn('⚠️ Erro ao buscar patientID na tabela WorkSchedules:', scheduleError.message);
      }
    }
  }
  
  // Busca nome do paciente se temos o ID
  if (patientID) {
    try {
      const pd = await dynamoDB.send(new GetItemCommand({
        TableName: TABLES.PATIENTS,
        Key: { patientID: { S: patientID } },
        ProjectionExpression: 'fullName'
      }));
      patientName = pd.Item?.fullName?.S || '';
      console.log('✅ Dados do paciente recuperados:', { patientID, patientName });
    } catch (patientError) {
      console.warn('⚠️ Erro ao buscar dados do paciente:', patientError.message);
      // Mantém o ID mas sem nome completo
    }
  } else {
    console.warn('⚠️ patientID não encontrado em nenhuma fonte');
  }

  // 6) PAS
  let PAS = 0;
  if (vitalSignsData.bloodPressure?.includes('x')) {
    const [sys] = vitalSignsData.bloodPressure.split('x');
    const nsys = Number(sys);
    if (!isNaN(nsys)) PAS = nsys;
  }

  // Validação dos intervalos
  const validation = validateVitalSignsRanges(vitalSignsData, PAS);
  if (!validation.isValid) {
    throw new Error(`Sinais vitais fora do padrão: ${validation.errors.join('; ')}`);
  }

  // Busca SymptomReport atual
  let currentSymptomReport = [];
  if (reportID && reportDate) {
    currentSymptomReport = await getCurrentSymptomReport(reportID, reportDate);
  }

  // Score absoluto
  const { totalScore: absoluteScore, scoreBreakdown, allSymptomsWithScores } =
    await calculateAbsoluteScore({
      ...vitalSignsData,
      heartRate: Number(vitalSignsData.heartRate || 0),
      respRate: Number(vitalSignsData.respRate || 0),
      saturationO2: Number(vitalSignsData.saturationO2 || 0),
      SymptomReport: body.SymptomReport || vitalSignsData.SymptomReport || [] // Added this line
    }, PAS, patientID, symptomConfig, currentSymptomReport, reportID, reportDate);

  return {
    processed: true,
    vitalSignsID,
    absoluteScore,
    scoreBreakdown,
    allSymptomsWithScores,
    day,
    time,
    timestamp,
    company,
    caregiverID,
    caregiverName,
    caregiverCompany,
    caregiverCooperative,
    patientID,
    patientName,
    PAS,
    concentrator,
    validation
  };
}

/**
 * Processa sinais vitais com TODA a lógica, incluindo alertas, histórico e salvamento em tabelas
 */
async function processVitalSignsCompleteWithTables(body) {
  console.log('🔍 Iniciando processVitalSignsCompleteWithTables');
  console.log('📊 body completo:', JSON.stringify(body, null, 2));
  console.log('📊 body.regras:', JSON.stringify(body.regras));
  console.log('📊 body.SymptomReport:', JSON.stringify(body.SymptomReport));
  console.log('📊 body.vitalSignsData:', JSON.stringify(body.vitalSignsData));
  
  const baseResult = await processVitalSignsComplete(body, body.regras);
  console.log('📊 baseResult obtido:', JSON.stringify(baseResult, null, 2));
  
  const { reportID, reportDate } = body;
  const vitalSignsData = body.vitalSignsData || body;
  
  console.log('📊 reportID:', reportID);
  console.log('📊 reportDate:', reportDate);
  console.log('📊 vitalSignsData processado:', JSON.stringify(vitalSignsData, null, 2));
  
  // Se não tem sinais vitais, retorna resultado básico
  if (!vitalSignsData.heartRate && !vitalSignsData.respRate && !vitalSignsData.saturationO2 && !vitalSignsData.bloodPressure) {
    return baseResult;
  }

  // Busca histórico para calcular estatísticas
  const allMeasures = await getAllMeasures(baseResult.patientID);
  const completeMeasures = allMeasures.filter(item =>
    item.PAS && item.temperature && item.saturationO2 && item.heartRate && item.respRate && (item.risk || item.risco)
  );

  // Estatísticas, z-scores, score relativo e risco
  let stats = {
    avgHeartRate: 0, sdHeartRate: 0,
    avgRespRate: 0, sdRespRate: 0,
    avgSaturationO2: 0, sdSaturationO2: 0,
    avgPAS: 0, sdPAS: 0
  };
  let zScores = { zHeartRate: 0, zRespRate: 0, zSaturationO2: 0, zPAS: 0 };
  let relativeScore = 0;
  let relativeBreakdown = { heartRate: 0, respRate: 0, saturationO2: 0, PAS: 0, symptoms: 0, temperature: 0 };
  let risco = '';

  if (completeMeasures.length < 6) {
    console.log('Não há 7 aferições anteriores completas');
    risco = 'Sem 7 afericoes anteriores completas ainda';
  } else {
    const measuresForStats = [
      ...completeMeasures,
      {
        heartRate: { N: String(vitalSignsData.heartRate || 0) },
        respRate: { N: String(vitalSignsData.respRate || 0) },
        saturationO2: { N: String(vitalSignsData.saturationO2 || 0) },
        PAS: { N: baseResult.PAS.toString() }
      }
    ];
    stats = computeHistoricStats(measuresForStats);
    zScores = computeZScores({
      heartRate: Number(vitalSignsData.heartRate || 0),
      respRate: Number(vitalSignsData.respRate || 0),
      saturationO2: Number(vitalSignsData.saturationO2 || 0)
    }, baseResult.PAS, stats);
    relativeScore = computeRelativeScore(baseResult.scoreBreakdown, zScores);
    relativeBreakdown = computeRelativeBreakdown(baseResult.scoreBreakdown, zScores);

    // Risco
    if (relativeScore >= 10) risco = 'Critico';
    else if (relativeScore >= 7) risco = 'Alto';
    else if (relativeScore >= 5) risco = 'Moderado';
    else risco = 'Baixo';
  }

  // Processa alertas e salva
  console.log('🔍 Antes de chamar processAlertsAndSave:');
  console.log('📊 body para alertas:', JSON.stringify(body, null, 2));
  console.log('📊 baseResult para alertas:', JSON.stringify(baseResult, null, 2));
  console.log('📊 vitalSignsData para alertas:', JSON.stringify(vitalSignsData, null, 2));
  console.log('📊 stats:', JSON.stringify(stats));
  console.log('📊 zScores:', JSON.stringify(zScores));
  console.log('📊 risco:', risco);
  console.log('📊 relativeScore:', relativeScore);
  console.log('📊 relativeBreakdown:', JSON.stringify(relativeBreakdown));
  
  const alertResult = await processAlertsAndSave(
    body, 
    baseResult, 
    vitalSignsData, 
    stats, 
    zScores, 
    risco, 
    completeMeasures, 
    relativeScore, 
    relativeBreakdown,
    reportID,
    reportDate
  );
  
  console.log('📊 alertResult obtido:', JSON.stringify(alertResult, null, 2));

  return {
    ...baseResult,
    relativeScore,
    risco,
    alert: alertResult.alert,
    alertItems: alertResult.alertItems,
    additionalSymptomsForReport: alertResult.additionalSymptomsForReport,
    stats,
    zScores
  };
}

/**
 * Processa sinais vitais (versão simplificada para compatibilidade)
 */
async function processVitalSigns(body) {
  const result = await processVitalSignsComplete(body, body.regras);
  
  // Incrementa contador
  if (body.scheduleID) {
    await incrementQtVSMeasures(body.scheduleID);
  }
  
  return result;
}

module.exports = {
  processVitalSignsComplete,
  processVitalSignsCompleteWithTables,
  processVitalSigns
};

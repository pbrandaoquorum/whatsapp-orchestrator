/**
 * Serviço completo para processamento de alertas de sinais vitais
 */

const { 
  dynamoDB, 
  TABLES,
  getCurrentSymptomReport,
  incrementQtVSMeasures
} = require('/opt/nodejs/dynamoHelpers');

const { 
  processSymptomReport 
} = require('/opt/nodejs/vitalSignsProcessor');

const { 
  sendWebhookAlert 
} = require('/opt/nodejs/alertProcessor');

const { 
  generateUUID 
} = require('/opt/nodejs/utils');

const { formatSymptomForDynamoDB } = require('../utils/symptomFormatter');
const { saveToSymptomReportsTable } = require('../handlers/symptomHandler');

const { 
  DynamoDBClient, 
  UpdateItemCommand, 
  PutItemCommand, 
  GetItemCommand 
} = require('@aws-sdk/client-dynamodb');

/**
 * Processa alertas e salva dados de sinais vitais
 */
async function processAlertsAndSave(body, baseResult, vitalSignsData, stats, zScores, risco, completeMeasures, relativeScore, relativeBreakdown, reportID, reportDate) {
  // Geração de alertas
  let alertItems = [];
  const additionalSymptomsForReport = [];
  const alertTimestamp = baseResult.timestamp;

  // Processa sintomas do SymptomReport para alertas (armazena info para incluir depois se houver qualquer alerta)
  let reportSymptoms = [];
  let allSymptomsForAlert = [];
  const symptomReport = vitalSignsData.SymptomReport || body.SymptomReport || [];
  if (Array.isArray(symptomReport) && symptomReport.length > 0) {
    const symptomConfig = {};
    if (Array.isArray(body.regras) && body.regras.length > 0) {
      body.regras.forEach(regra => {
        if (regra.sintoma && typeof regra.pontuacao === 'number') {
          symptomConfig[regra.sintoma] = {
            score: regra.pontuacao,
            freq: regra.freq === 'Sim'
          };
        }
      });
    }
    
    const currentSymptomReport = await getCurrentSymptomReport(reportID, reportDate);
    const result = await processSymptomReport(
      symptomReport, // Changed from vitalSignsData.SymptomReport
      baseResult.patientID, 
      symptomConfig, 
      risco, 
      currentSymptomReport, 
      reportID, 
      reportDate
    );
    reportSymptoms = result.symptomsToAlert;
    allSymptomsForAlert = result.allSymptomsForAlert;
    
    console.log(`🔍 Encontrados ${reportSymptoms.length} sintomas para alerta de ${allSymptomsForAlert.length} sintomas totais`);
  }

  // NÃO adiciona sintomas aqui - será feito no final se houver qualquer alerta

  // Temperatura elevada
  if (Number(vitalSignsData.temperature) > 0 && Number(vitalSignsData.temperature) >= 37.8) {
    const tempSymptom = {
      altNotepadMain: `Temperatura elevada: ${vitalSignsData.temperature}°C`,
      symptomCategory: 'Temperatura',
      symptomSubCategory: 'Febre',
      symptomDefinition: 'Febre'
    };
    
    alertItems.push({
      M: {
        altNotepadMain: { S: tempSymptom.altNotepadMain },
        symptomCategory: { S: tempSymptom.symptomCategory },
        symptomSubCategory: { S: tempSymptom.symptomSubCategory },
        symptomDefinition: { S: tempSymptom.symptomDefinition },
        timestamp: { S: alertTimestamp }
      }
    });
    
    additionalSymptomsForReport.push(tempSymptom);
  }

  // Alertas por score = 5 em sinais vitais
  addCriticalVitalSignsAlerts(vitalSignsData, baseResult, stats, alertItems, additionalSymptomsForReport, alertTimestamp);

  // Alertas por z-score/variações extremas
  addZScoreAlerts(vitalSignsData, baseResult, zScores, alertItems, additionalSymptomsForReport, alertTimestamp);

  // Mudança para Crítico
  addRiskChangeAlerts(completeMeasures, risco, alertItems, additionalSymptomsForReport, alertTimestamp);

  // Fallback para risco alto/crítico
  addRiskFallbackAlerts(risco, alertItems, additionalSymptomsForReport, alertTimestamp);

  // Se há qualquer alerta (temperatura, z-score, mudança de risco, etc), inclui TODOS os sintomas do SymptomReport
  if (alertItems.length > 0 && allSymptomsForAlert.length > 0) {
    console.log(`📋 Alerta detectado - incluindo TODOS os ${allSymptomsForAlert.length} sintomas do SymptomReport:`, allSymptomsForAlert.map(s => s.symptomDefinition));
    allSymptomsForAlert.forEach(symptom => {
      alertItems.push({
        M: {
          altNotepadMain: { S: symptom.altNotepadMain || '' },
          symptomCategory: { S: symptom.symptomCategory || '' },
          symptomSubCategory: { S: symptom.symptomSubCategory || '' },
          symptomDefinition: { S: symptom.symptomDefinition || '' },
          timestamp: { S: alertTimestamp }
        }
      });
    });
  } else if (reportSymptoms.length > 0 && allSymptomsForAlert.length > 0) {
    // Se apenas sintomas do SymptomReport geram alertas, inclui todos os sintomas
    console.log(`📋 Apenas sintomas do SymptomReport geram alertas - incluindo TODOS os ${allSymptomsForAlert.length} sintomas:`, allSymptomsForAlert.map(s => s.symptomDefinition));
    allSymptomsForAlert.forEach(symptom => {
      alertItems.push({
        M: {
          altNotepadMain: { S: symptom.altNotepadMain || '' },
          symptomCategory: { S: symptom.symptomCategory || '' },
          symptomSubCategory: { S: symptom.symptomSubCategory || '' },
          symptomDefinition: { S: symptom.symptomDefinition || '' },
          timestamp: { S: alertTimestamp }
        }
      });
    });
  }

  // Salva alerta se necessário
  const alert = alertItems.length > 0;
  if (alert) {
    // Valida se temos campos obrigatórios para os índices
    if (!baseResult.caregiverID) {
      console.warn('⚠️ Alerta não será salvo: caregiverID é obrigatório para o índice caregiverID-index');
    } else if (!baseResult.patientID) {
      console.warn('⚠️ Alerta não será salvo: patientID é obrigatório para o índice patientID-index');
    } else {
      await saveAlert(baseResult, alertItems);
      await sendWebhook(baseResult, alertItems);
    }
  }

  // Salva em VitalSigns e VitalSignsTest
  await saveVitalSignsTables(baseResult, vitalSignsData, relativeScore, relativeBreakdown, stats, zScores, risco, alert, allSymptomsForAlert, additionalSymptomsForReport, reportID, body);

  // Atualiza scores no paciente
  await updatePatientScores(baseResult, relativeScore);

  // Atualiza SymptomReport na tabela Reports
  await updateReportsSymptomReport(reportID, reportDate, vitalSignsData, baseResult, allSymptomsForAlert, additionalSymptomsForReport, risco, body);

  // Salva na tabela SymptomReports
  await saveSymptomReports(reportID, reportDate, vitalSignsData, baseResult, allSymptomsForAlert, additionalSymptomsForReport, risco, body);

  // Incrementa contador
  if (body.scheduleID) {
    await incrementQtVSMeasures(body.scheduleID);
  }

  return {
    alert,
    alertItems: alertItems.length,
    additionalSymptomsForReport
  };
}

/**
 * Adiciona alertas por sinais vitais críticos
 */
function addCriticalVitalSignsAlerts(vitalSignsData, baseResult, stats, alertItems, additionalSymptomsForReport, alertTimestamp) {
  if (vitalSignsData.heartRate > 0 && baseResult.scoreBreakdown.heartRate === 5) {
    const fcSymptom = {
      altNotepadMain: `FC crítica: ${vitalSignsData.heartRate} bpm`,
      symptomCategory: 'Sinais Vitais',
      symptomSubCategory: 'Frequência Cardíaca',
      symptomDefinition: 'FC requer atenção'
    };
    
    alertItems.push({
      M: {
        altNotepadMain: { S: fcSymptom.altNotepadMain },
        symptomCategory: { S: fcSymptom.symptomCategory },
        symptomSubCategory: { S: fcSymptom.symptomSubCategory },
        symptomDefinition: { S: fcSymptom.symptomDefinition },
        timestamp: { S: alertTimestamp }
      }
    });
    
    additionalSymptomsForReport.push(fcSymptom);
  }

  if (vitalSignsData.respRate > 0 && baseResult.scoreBreakdown.respRate === 5 && stats.avgRespRate <= 40) {
    const frSymptom = {
      altNotepadMain: `FR crítica: ${vitalSignsData.respRate} rpm`,
      symptomCategory: 'Sinais Vitais',
      symptomSubCategory: 'Frequência Respiratória',
      symptomDefinition: 'FR requer atenção'
    };
    
    alertItems.push({
      M: {
        altNotepadMain: { S: frSymptom.altNotepadMain },
        symptomCategory: { S: frSymptom.symptomCategory },
        symptomSubCategory: { S: frSymptom.symptomSubCategory },
        symptomDefinition: { S: frSymptom.symptomDefinition },
        timestamp: { S: alertTimestamp }
      }
    });
    
    additionalSymptomsForReport.push(frSymptom);
  }

  if (vitalSignsData.saturationO2 > 0 && baseResult.scoreBreakdown.saturationO2 === 5 && stats.avgSaturationO2 >= 88) {
    const satSymptom = {
      altNotepadMain: `SatO2 crítica: ${vitalSignsData.saturationO2}%`,
      symptomCategory: 'Sinais Vitais',
      symptomSubCategory: 'Saturação de Oxigênio',
      symptomDefinition: 'SatO2 requer atenção'
    };
    
    alertItems.push({
      M: {
        altNotepadMain: { S: satSymptom.altNotepadMain },
        symptomCategory: { S: satSymptom.symptomCategory },
        symptomSubCategory: { S: satSymptom.symptomSubCategory },
        symptomDefinition: { S: satSymptom.symptomDefinition },
        timestamp: { S: alertTimestamp }
      }
    });
    
    additionalSymptomsForReport.push(satSymptom);
  }

  if (baseResult.PAS > 0 && baseResult.scoreBreakdown.PAS === 5 && stats.avgPAS >= 80) {
    const pasSymptom = {
      altNotepadMain: `PAS crítica: ${baseResult.PAS} mmHg`,
      symptomCategory: 'Sinais Vitais',
      symptomSubCategory: 'Pressão Arterial',
      symptomDefinition: 'PAS requer atenção'
    };
    
    alertItems.push({
      M: {
        altNotepadMain: { S: pasSymptom.altNotepadMain },
        symptomCategory: { S: pasSymptom.symptomCategory },
        symptomSubCategory: { S: pasSymptom.symptomSubCategory },
        symptomDefinition: { S: pasSymptom.symptomDefinition },
        timestamp: { S: alertTimestamp }
      }
    });
    
    additionalSymptomsForReport.push(pasSymptom);
  }
}

/**
 * Adiciona alertas por z-score/variações extremas
 */
function addZScoreAlerts(vitalSignsData, baseResult, zScores, alertItems, additionalSymptomsForReport, alertTimestamp) {
  if (vitalSignsData.heartRate > 0 && Math.abs(zScores.zHeartRate) >= 3 && baseResult.scoreBreakdown.heartRate >= 1) {
    const zScoreSymptom = {
      altNotepadMain: `FC com alta variação: ${vitalSignsData.heartRate} bpm`,
      symptomCategory: 'Sinais Vitais',
      symptomSubCategory: 'Variação FC',
      symptomDefinition: 'FC com alta variação em relação basal'
    };
    
    alertItems.push({
      M: {
        altNotepadMain: { S: zScoreSymptom.altNotepadMain },
        symptomCategory: { S: zScoreSymptom.symptomCategory },
        symptomSubCategory: { S: zScoreSymptom.symptomSubCategory },
        symptomDefinition: { S: zScoreSymptom.symptomDefinition },
        timestamp: { S: alertTimestamp }
      }
    });
    
    additionalSymptomsForReport.push(zScoreSymptom);
  }
  
  if (vitalSignsData.respRate > 0 && zScores.zRespRate >= 3 && baseResult.scoreBreakdown.respRate >= 2 && baseResult.scoreBreakdown.heartRate >= 1) {
    const zScoreSymptom = {
      altNotepadMain: `FR com alta variação: ${vitalSignsData.respRate} rpm`,
      symptomCategory: 'Sinais Vitais',
      symptomSubCategory: 'Variação FR',
      symptomDefinition: 'FR com alta variação em relação basal'
    };
    
    alertItems.push({
      M: {
        altNotepadMain: { S: zScoreSymptom.altNotepadMain },
        symptomCategory: { S: zScoreSymptom.symptomCategory },
        symptomSubCategory: { S: zScoreSymptom.symptomSubCategory },
        symptomDefinition: { S: zScoreSymptom.symptomDefinition },
        timestamp: { S: alertTimestamp }
      }
    });
    
    additionalSymptomsForReport.push(zScoreSymptom);
  }
  
  if (vitalSignsData.saturationO2 > 0 && zScores.zSaturationO2 < 0 && Math.abs(zScores.zSaturationO2) >= 3 && baseResult.scoreBreakdown.saturationO2 >= 2) {
    const zScoreSymptom = {
      altNotepadMain: `SatO2 com alta variação: ${vitalSignsData.saturationO2}%`,
      symptomCategory: 'Sinais Vitais',
      symptomSubCategory: 'Variação SatO2',
      symptomDefinition: 'SatO2 com alta variação em relação basal'
    };
    
    alertItems.push({
      M: {
        altNotepadMain: { S: zScoreSymptom.altNotepadMain },
        symptomCategory: { S: zScoreSymptom.symptomCategory },
        symptomSubCategory: { S: zScoreSymptom.symptomSubCategory },
        symptomDefinition: { S: zScoreSymptom.symptomDefinition },
        timestamp: { S: alertTimestamp }
      }
    });
    
    additionalSymptomsForReport.push(zScoreSymptom);
  }
  
  if (baseResult.PAS > 0 && zScores.zPAS < 0 && Math.abs(zScores.zPAS) >= 3 && baseResult.scoreBreakdown.PAS >= 2) {
    const zScoreSymptom = {
      altNotepadMain: `PAS com alta variação: ${baseResult.PAS} mmHg`,
      symptomCategory: 'Sinais Vitais',
      symptomSubCategory: 'Variação PAS',
      symptomDefinition: 'PAS com alta variação em relação basal'
    };
    
    alertItems.push({
      M: {
        altNotepadMain: { S: zScoreSymptom.altNotepadMain },
        symptomCategory: { S: zScoreSymptom.symptomCategory },
        symptomSubCategory: { S: zScoreSymptom.symptomSubCategory },
        symptomDefinition: { S: zScoreSymptom.symptomDefinition },
        timestamp: { S: alertTimestamp }
      }
    });
    
    additionalSymptomsForReport.push(zScoreSymptom);
  }
}

/**
 * Adiciona alertas por mudança de risco para crítico
 */
function addRiskChangeAlerts(completeMeasures, risco, alertItems, additionalSymptomsForReport, alertTimestamp) {
  if (completeMeasures.length >= 6) {
    const previousRisk = completeMeasures[0].risk?.S || completeMeasures[0].risco?.S || null;
    if (previousRisk && risco === 'Critico' && previousRisk !== 'Critico') {
      const riskChangeSymptom = {
        altNotepadMain: `Mudança de risco: ${previousRisk} para ${risco}`,
        symptomCategory: 'Risco',
        symptomSubCategory: 'Mudança de Status',
        symptomDefinition: 'Mudança de risco para Crítico'
      };
      
      alertItems.push({
        M: {
          altNotepadMain: { S: riskChangeSymptom.altNotepadMain },
          symptomCategory: { S: riskChangeSymptom.symptomCategory },
          symptomSubCategory: { S: riskChangeSymptom.symptomSubCategory },
          symptomDefinition: { S: riskChangeSymptom.symptomDefinition },
          timestamp: { S: alertTimestamp }
        }
      });
      
      additionalSymptomsForReport.push(riskChangeSymptom);
    }
  }
}

/**
 * Adiciona alertas de fallback para risco alto/crítico
 */
function addRiskFallbackAlerts(risco, alertItems, additionalSymptomsForReport, alertTimestamp) {
  if (risco === 'Critico' && alertItems.length === 0) {
    const riskFallbackSymptom = {
      altNotepadMain: `Risco global classificado como ${risco}`,
      symptomCategory: 'Risco',
      symptomSubCategory: 'Classificação',
      symptomDefinition: `Risco ${risco} da aferição`
    };
    
    alertItems.push({
      M: {
        altNotepadMain: { S: riskFallbackSymptom.altNotepadMain },
        symptomCategory: { S: riskFallbackSymptom.symptomCategory },
        symptomSubCategory: { S: riskFallbackSymptom.symptomSubCategory },
        symptomDefinition: { S: riskFallbackSymptom.symptomDefinition },
        timestamp: { S: alertTimestamp }
      }
    });
    
    additionalSymptomsForReport.push(riskFallbackSymptom);
  }
}

/**
 * Salva alerta na tabela Alerts
 */
async function saveAlert(baseResult, alertItems) {
  // Validação de campos obrigatórios para índices
  if (!baseResult.caregiverID) {
    throw new Error('caregiverID é obrigatório para salvar alerta (índice caregiverID-index)');
  }
  if (!baseResult.patientID) {
    throw new Error('patientID é obrigatório para salvar alerta');
  }

  const alertID = generateUUID();
  console.log('💾 Salvando alerta com caregiverID:', baseResult.caregiverID);
  
  await dynamoDB.send(new PutItemCommand({
    TableName: TABLES.ALERTS,
    Item: {
      alertID: { S: alertID },
      caregiverID: { S: baseResult.caregiverID },
      caregiverName: { S: baseResult.caregiverName || 'Não informado' },
      patientID: { S: baseResult.patientID },
      patientName: { S: baseResult.patientName || 'Não informado' },
      vitalSignsID: { S: baseResult.vitalSignsID || '' },
      day: { S: baseResult.day || '' },
      time: { S: baseResult.time || '' },
      solved: { BOOL: false },
      company: { S: baseResult.company || '' },
      alerts: { L: alertItems },
      source: { S: 'vitalsigns' }
    }
  }));
  
  console.log('✅ Alerta salvo com sucesso');
}

/**
 * Envia webhook de alerta
 */
async function sendWebhook(baseResult, alertItems) {
  try {
    const webhookAlerts = alertItems.map(item => ({
      altNotepadMain: item.M.altNotepadMain?.S || '',
      symptomDefinition: item.M.symptomDefinition?.S || '',
      symptomCategory: item.M.symptomCategory?.S || ''
    }));

    const webhookData = {
      company: baseResult.caregiverCompany,
      cooperative: baseResult.caregiverCooperative,
      patientName: baseResult.patientName,
      caregiverName: baseResult.caregiverName,
      alertDay: baseResult.day,
      alertTime: baseResult.time,
      alerts: webhookAlerts
    };

    await sendWebhookAlert(webhookData);
    console.log('✅ Webhook de alerta enviado com sucesso');
  } catch (webhookError) {
    console.error('❌ Erro ao enviar webhook de alerta:', webhookError);
  }
}

/**
 * Salva dados nas tabelas VitalSigns e VitalSignsTest
 */
async function saveVitalSignsTables(baseResult, vitalSignsData, relativeScore, relativeBreakdown, stats, zScores, risco, alert, allSymptomsToAlert, additionalSymptomsForReport, reportID, body = null) {
  console.log('🔍 Iniciando saveVitalSignsTables');
  console.log('📊 baseResult keys:', Object.keys(baseResult));
  console.log('📊 vitalSignsData keys:', Object.keys(vitalSignsData));
  console.log('📊 relativeScore:', relativeScore);
  console.log('📊 relativeBreakdown:', JSON.stringify(relativeBreakdown));
  console.log('📊 stats:', JSON.stringify(stats));
  console.log('📊 zScores:', JSON.stringify(zScores));
  console.log('📊 risco:', risco);
  console.log('📊 alert:', alert);
  console.log('📊 allSymptomsToAlert:', allSymptomsToAlert);
  console.log('📊 additionalSymptomsForReport:', additionalSymptomsForReport);
  console.log('📊 reportID:', reportID);

  // Prepara sintomas para VitalSigns
  const allSymptomsForVitalSigns = [];
  
  // Busca sintomas do SymptomReport (pode estar em vitalSignsData ou diretamente no body)
  const symptomReport = vitalSignsData.SymptomReport || (body && body.SymptomReport) || [];
  console.log('📊 symptomReport:', JSON.stringify(symptomReport));
  
  if (Array.isArray(symptomReport)) {
    symptomReport.forEach(symptom => {
      if (symptom && symptom.symptomDefinition) {
        allSymptomsForVitalSigns.push(symptom.symptomDefinition);
      }
    });
  }
  
  if (additionalSymptomsForReport && additionalSymptomsForReport.length > 0) {
    additionalSymptomsForReport.forEach(symptom => {
      if (symptom && symptom.symptomDefinition) {
        allSymptomsForVitalSigns.push(symptom.symptomDefinition);
      }
    });
  }
  
  console.log('📊 allSymptomsForVitalSigns:', allSymptomsForVitalSigns);

  // Validar campos críticos antes de criar o item
  console.log('🔍 Validando campos antes de criar vitalSignsItem');
  console.log('📊 baseResult.vitalSignsID:', baseResult.vitalSignsID);
  console.log('📊 baseResult.company:', baseResult.company);
  console.log('📊 baseResult.caregiverID:', baseResult.caregiverID);
  console.log('📊 baseResult.caregiverName:', baseResult.caregiverName);
  console.log('📊 baseResult.patientID:', baseResult.patientID);
  console.log('📊 baseResult.patientName:', baseResult.patientName);
  console.log('📊 baseResult.PAS:', baseResult.PAS);
  console.log('📊 baseResult.day:', baseResult.day);
  console.log('📊 baseResult.time:', baseResult.time);
  console.log('📊 baseResult.timestamp:', baseResult.timestamp);
  console.log('📊 baseResult.absoluteScore:', baseResult.absoluteScore);
  console.log('📊 baseResult.scoreBreakdown:', JSON.stringify(baseResult.scoreBreakdown));
  console.log('📊 baseResult.allSymptomsWithScores:', JSON.stringify(baseResult.allSymptomsWithScores));

  // Verificar se allSymptomsWithScores existe e tem a estrutura correta
  const symptomsWithScores = baseResult.allSymptomsWithScores || [];
  console.log('📊 symptomsWithScores length:', symptomsWithScores.length);
  if (symptomsWithScores.length > 0) {
    console.log('📊 Primeiro item de symptomsWithScores:', JSON.stringify(symptomsWithScores[0]));
  }

  // Item para VitalSigns
  const vitalSignsItem = {
    vitalSignsID: { S: baseResult.vitalSignsID || '' },
    reportID: { S: reportID || '' },
    company: { S: baseResult.company || '' },
    caregiverID: { S: baseResult.caregiverID || '' },
    caregiverName: { S: baseResult.caregiverName || '' },
    patientID: { S: baseResult.patientID || '' },
    patientName: { S: baseResult.patientName || '' },
    PAS: { N: (baseResult.PAS || 0).toFixed(2) },
    bloodPressure: { S: vitalSignsData.bloodPressure || 'Nao analisado' },
    temperature: { N: String(vitalSignsData.temperature || 0) },
    heartRate: { N: String(vitalSignsData.heartRate || 0) },
    respRate: { N: String(vitalSignsData.respRate || 0) },
    concentrator: { BOOL: baseResult.concentrator || false },
    oxygenVolume: { N: String(vitalSignsData.oxygenVolume || 0) },
    saturationO2: { N: String(vitalSignsData.saturationO2 || 0) },
    supplementaryOxygen: { S: vitalSignsData.supplementaryOxygen || 'Nao analisado' },
    consciousness: { S: vitalSignsData.consciousness || 'Nao analisado' },
    day: { S: baseResult.day || '' },
    time: { S: baseResult.time || '' },
    timestamp: { S: baseResult.timestamp || '' },
    absoluteScore: { N: (baseResult.absoluteScore || 0).toString() },
    relativeScore: { N: (relativeScore || 0).toFixed(2) },
    absoluteBreakdown: { S: JSON.stringify(baseResult.scoreBreakdown || {}) },
    relativeBreakdown: { S: JSON.stringify(relativeBreakdown || {}) },
    avgHeartRate: { N: (stats.avgHeartRate || 0).toFixed(2) },
    sdHeartRate: { N: (stats.sdHeartRate || 0).toFixed(2) },
    avgRespRate: { N: (stats.avgRespRate || 0).toFixed(2) },
    sdRespRate: { N: (stats.sdRespRate || 0).toFixed(2) },
    avgSaturationO2: { N: (stats.avgSaturationO2 || 0).toFixed(2) },
    sdSaturationO2: { N: (stats.sdSaturationO2 || 0).toFixed(2) },
    avgPAS: { N: (stats.avgPAS || 0).toFixed(2) },
    sdPAS: { N: (stats.sdPAS || 0).toFixed(2) },
    zHeartRate: { N: (zScores.zHeartRate || 0).toFixed(2) },
    zRespRate: { N: (zScores.zRespRate || 0).toFixed(2) },
    zSaturationO2: { N: (zScores.zSaturationO2 || 0).toFixed(2) },
    zPAS: { N: (zScores.zPAS || 0).toFixed(2) },
    alert: { BOOL: alert || false },
    risk: { S: risco || 'Baixo' },
    Symptoms: { L: allSymptomsForVitalSigns.map(symptom => ({ S: symptom || '' })) },
    symptomsScore: { L: symptomsWithScores.filter(item => item && item.symptom).map(item => ({ 
      M: {
        symptom: { S: item.symptom || '' },
        score: { N: (item.score || 0).toString() }
      }
    })) }
  };
  
  console.log('📊 vitalSignsItem criado, validando campos problemáticos...');
  console.log('📊 vitalSignsItem.Symptoms:', JSON.stringify(vitalSignsItem.Symptoms));
  console.log('📊 vitalSignsItem.symptomsScore:', JSON.stringify(vitalSignsItem.symptomsScore));

  // Validação adicional antes de salvar
  if (!baseResult.caregiverID) {
    console.warn('⚠️ caregiverID está vazio - isso pode causar problemas com índices');
    console.warn('⚠️ Pulando salvamento em VitalSigns devido a caregiverID vazio');
    return;
  }
  
  if (!baseResult.patientID) {
    console.warn('⚠️ patientID está vazio - isso pode causar problemas com índices');
    console.warn('⚠️ Pulando salvamento em VitalSigns devido a patientID vazio');
    return;
  }

  try {
    console.log('📊 Tentando salvar na tabela VitalSigns...');
    console.log('📊 caregiverID sendo usado:', baseResult.caregiverID);
    console.log('📊 patientID sendo usado:', baseResult.patientID);
    await dynamoDB.send(new PutItemCommand({
      TableName: TABLES.VITAL_SIGNS,
      Item: vitalSignsItem
    }));
    console.log('✅ Salvamento na tabela VitalSigns bem-sucedido');
  } catch (putError) {
    console.error('❌ Erro ao salvar na tabela VitalSigns:', putError);
    console.error('❌ Stack trace:', putError.stack);
    console.error('❌ VitalSigns Item que causou erro:', JSON.stringify(vitalSignsItem, null, 2));
    throw putError;
  }

  // Replica em VitalSignsTest
  const vitalSignsTestItem = {
    vitalSignsTestID: vitalSignsItem.vitalSignsID,
    absoluteBreakdown: vitalSignsItem.absoluteBreakdown,
    relativeBreakdown: vitalSignsItem.relativeBreakdown,
    absoluteScore: vitalSignsItem.absoluteScore,
    alert: vitalSignsItem.alert,
    caregiverID: vitalSignsItem.caregiverID,
    caregiverName: vitalSignsItem.caregiverName,
    company: vitalSignsItem.company,
    concentrator: vitalSignsItem.concentrator,
    consciousness: vitalSignsItem.consciousness,
    heartRate: vitalSignsItem.heartRate,
    oxygenVolume: vitalSignsItem.oxygenVolume,
    PAS: vitalSignsItem.PAS,
    patientID: vitalSignsItem.patientID,
    patientName: vitalSignsItem.patientName,
    reportID: vitalSignsItem.reportID,
    respRate: vitalSignsItem.respRate,
    saturationO2: vitalSignsItem.saturationO2,
    supplementaryOxygen: vitalSignsItem.supplementaryOxygen,
    temperature: vitalSignsItem.temperature,
    timestamp: vitalSignsItem.timestamp,
    symptomsScore: vitalSignsItem.symptomsScore
  };
  
  try {
    console.log('📊 Tentando salvar na tabela VitalSignsTest...');
    console.log('📊 VitalSignsTest Item:', JSON.stringify(vitalSignsTestItem, null, 2));
    await dynamoDB.send(new PutItemCommand({
      TableName: TABLES.VITAL_SIGNS_TEST,
      Item: vitalSignsTestItem
    }));
    console.log('✅ Salvamento na tabela VitalSignsTest bem-sucedido');
  } catch (putTestError) {
    console.error('❌ Erro ao salvar na tabela VitalSignsTest:', putTestError);
    console.error('❌ Stack trace:', putTestError.stack);
    console.error('❌ VitalSignsTest Item que causou erro:', JSON.stringify(vitalSignsTestItem, null, 2));
    throw putTestError;
  }
}

/**
 * Atualiza scores no paciente
 */
async function updatePatientScores(baseResult, relativeScore) {
  if (baseResult.patientID) {
    try {
      console.log('📊 Atualizando scores do paciente:', baseResult.patientID);
      await dynamoDB.send(new UpdateItemCommand({
        TableName: TABLES.PATIENTS,
        Key: { patientID: { S: baseResult.patientID } },
        UpdateExpression: 'SET currentAbsoluteScore = :abs, currentRelativeScore = :rel',
        ExpressionAttributeValues: {
          ':abs': { N: baseResult.absoluteScore.toString() },
          ':rel': { N: relativeScore.toFixed(2) }
        }
      }));
      console.log('✅ Scores do paciente atualizados com sucesso');
    } catch (patientError) {
      console.error('❌ Erro ao atualizar scores do paciente:', patientError);
      // Não relança o erro para não interromper o processo principal
    }
  } else {
    console.warn('⚠️ patientID não informado, pulando atualização de scores');
  }
}

/**
 * Atualiza SymptomReport na tabela Reports
 */
async function updateReportsSymptomReport(reportID, reportDate, vitalSignsData, baseResult, allSymptomsToAlert, additionalSymptomsForReport, risco, body) {
  if (reportID && reportDate && (vitalSignsData.SymptomReport || additionalSymptomsForReport.length > 0)) {
    try {
      let existingSymptomReport = [];
      
      try {
        const existingReport = await dynamoDB.send(new GetItemCommand({
          TableName: TABLES.REPORTS,
          Key: {
            reportID: { S: reportID },
            reportDate: { S: reportDate }
          },
          ProjectionExpression: 'SymptomReport'
        }));
        
        if (existingReport.Item && existingReport.Item.SymptomReport && existingReport.Item.SymptomReport.L) {
          existingSymptomReport = existingReport.Item.SymptomReport.L.map(item => ({
            altNotepadMain: item.M.altNotepadMain?.S || '',
            symptomCategory: item.M.symptomCategory?.S || '',
            symptomSubCategory: item.M.symptomSubCategory?.S || '',
            symptomDefinition: item.M.symptomDefinition?.S || '',
            timestamp: item.M.timestamp?.S || ''
          }));
        }
      } catch (getError) {
        console.log('📋 Nenhum SymptomReport existente encontrado');
      }
      
      // Coleta todos os sintomas com score e info de alerta
      let allFormattedSymptomsForReport = [];
      
      // Adiciona sintomas existentes (preserva formatação)
      if (existingSymptomReport.length > 0) {
        const existingFormatted = existingSymptomReport.map(item => ({
          M: {
            altNotepadMain: { S: item.altNotepadMain },
            symptomCategory: { S: item.symptomCategory },
            symptomSubCategory: { S: item.symptomSubCategory },
            symptomDefinition: { S: item.symptomDefinition },
            score: { N: (item.score || 0).toString() },
            alert: { BOOL: item.alert || false },
            timestamp: { S: item.timestamp },
          }
        }));
        allFormattedSymptomsForReport = [...allFormattedSymptomsForReport, ...existingFormatted];
      }
      
      // Adiciona sintomas do SymptomReport (com score das regras)
      if (vitalSignsData.SymptomReport && Array.isArray(vitalSignsData.SymptomReport)) {
        const symptomConfig = {};
        if (Array.isArray(body.regras) && body.regras.length > 0) {
          body.regras.forEach(regra => {
            if (regra.sintoma && typeof regra.pontuacao === 'number') {
              symptomConfig[regra.sintoma] = regra.pontuacao;
            }
          });
        }
        
        const symptomsFormatted = vitalSignsData.SymptomReport.map((item) => {
          const score = symptomConfig[item.symptomDefinition] || 0;
          const isInAlert = allSymptomsToAlert.some(s => s.symptomDefinition === item.symptomDefinition);
          
          return {
            M: {
              altNotepadMain: { S: item.altNotepadMain || "" },
              symptomCategory: { S: item.symptomCategory || "" },
              symptomSubCategory: { S: item.symptomSubCategory || "" },
              symptomDefinition: { S: item.symptomDefinition || "" },
              score: { N: score.toString() },
              alert: { BOOL: isInAlert },
              timestamp: { S: baseResult.timestamp },
            }
          };
        });
        allFormattedSymptomsForReport = [...allFormattedSymptomsForReport, ...symptomsFormatted];
      }
      
      // Adiciona sintomas gerados por sinais vitais (score diferenciado por tipo)
      if (additionalSymptomsForReport.length > 0) {
        const vitalSignsSymptoms = additionalSymptomsForReport.map((item) => {
          // Define score baseado no tipo de sintoma
          let score = 5; // Default para sinais vitais críticos
          
          if (item.symptomDefinition.includes('alta variação')) {
            // Sintomas de z-score/variação têm score baseado no scoreBreakdown original
            if (item.symptomDefinition.includes('FC')) score = baseResult.scoreBreakdown.heartRate;
            else if (item.symptomDefinition.includes('FR')) score = baseResult.scoreBreakdown.respRate;
            else if (item.symptomDefinition.includes('SatO2')) score = baseResult.scoreBreakdown.saturationO2;
            else if (item.symptomDefinition.includes('PAS')) score = baseResult.scoreBreakdown.PAS;
          } else if (item.symptomDefinition.includes('Mudança de risco') || item.symptomDefinition.includes('Risco')) {
            // Sintomas de mudança de risco têm score baseado no risco
            if (risco === 'Critico') score = 5;
            else if (risco === 'Alto') score = 4;
            else if (risco === 'Moderado') score = 3;
            else score = 2;
          }
          
          return {
            M: {
              altNotepadMain: { S: item.altNotepadMain || "" },
              symptomCategory: { S: item.symptomCategory || "" },
              symptomSubCategory: { S: item.symptomSubCategory || "" },
              symptomDefinition: { S: item.symptomDefinition || "" },
              score: { N: score.toString() },
              alert: { BOOL: true }, // Todos os additionalSymptoms geram alerta
              timestamp: { S: baseResult.timestamp },
            }
          };
        });
        allFormattedSymptomsForReport = [...allFormattedSymptomsForReport, ...vitalSignsSymptoms];
      }
      
      if (allFormattedSymptomsForReport.length > 0) {
        await dynamoDB.send(new UpdateItemCommand({
          TableName: TABLES.REPORTS,
          Key: {
            reportID: { S: reportID },
            reportDate: { S: reportDate },
          },
          UpdateExpression: "SET SymptomReport = :sr",
          ExpressionAttributeValues: {
            ":sr": { L: allFormattedSymptomsForReport },
          },
        }));
        console.log(`✅ SymptomReport atualizado na tabela Reports com ${allFormattedSymptomsForReport.length} sintomas`);
      }
    } catch (reportError) {
      console.error('❌ Erro ao atualizar SymptomReport na tabela Reports:', reportError);
    }
  }
}

/**
 * Salva na tabela SymptomReports
 */
async function saveSymptomReports(reportID, reportDate, vitalSignsData, baseResult, allSymptomsToAlert, additionalSymptomsForReport, risco, body) {
  if (reportID && reportDate && (vitalSignsData.SymptomReport || additionalSymptomsForReport.length > 0)) {
    try {
      // Converte o formato para salvar na SymptomReports (idêntico ao da Reports)
      const allSymptomsForSymptomReports = [];
      
      // Sintomas originais do SymptomReport
      if (vitalSignsData.SymptomReport && Array.isArray(vitalSignsData.SymptomReport)) {
        const symptomConfig = {};
        if (Array.isArray(body.regras) && body.regras.length > 0) {
          body.regras.forEach(regra => {
            if (regra.sintoma && typeof regra.pontuacao === 'number') {
              symptomConfig[regra.sintoma] = regra.pontuacao;
            }
          });
        }
        
        const originalSymptoms = vitalSignsData.SymptomReport.map((item) => {
          const score = symptomConfig[item.symptomDefinition] || 0;
          const isInAlert = allSymptomsToAlert.some(s => s.symptomDefinition === item.symptomDefinition);
          
          return {
            altNotepadMain: item.altNotepadMain || "",
            symptomCategory: item.symptomCategory || "",
            symptomSubCategory: item.symptomSubCategory || "",
            symptomDefinition: item.symptomDefinition || "",
            score: score,
            alert: isInAlert,
            timestamp: baseResult.timestamp
          };
        });
        allSymptomsForSymptomReports.push(...originalSymptoms);
      }
      
      // Sintomas gerados por sinais vitais (com scores corretos)
      if (additionalSymptomsForReport.length > 0) {
        const generatedSymptoms = additionalSymptomsForReport.map((item) => {
          let score = 5; // Default para sinais vitais críticos
          
          if (item.symptomDefinition.includes('alta variação')) {
            if (item.symptomDefinition.includes('FC')) score = baseResult.scoreBreakdown.heartRate;
            else if (item.symptomDefinition.includes('FR')) score = baseResult.scoreBreakdown.respRate;
            else if (item.symptomDefinition.includes('SatO2')) score = baseResult.scoreBreakdown.saturationO2;
            else if (item.symptomDefinition.includes('PAS')) score = baseResult.scoreBreakdown.PAS;
          } else if (item.symptomDefinition.includes('Mudança de risco') || item.symptomDefinition.includes('Risco')) {
            if (risco === 'Critico') score = 5;
            else if (risco === 'Alto') score = 4;
            else if (risco === 'Moderado') score = 3;
            else score = 2;
          }
          
          return {
            altNotepadMain: item.altNotepadMain || "",
            symptomCategory: item.symptomCategory || "",
            symptomSubCategory: item.symptomSubCategory || "",
            symptomDefinition: item.symptomDefinition || "",
            score: score,
            alert: true, // Todos os sintomas gerados geram alerta
            timestamp: baseResult.timestamp
          };
        });
        allSymptomsForSymptomReports.push(...generatedSymptoms);
      }
      
      // Salva na tabela SymptomReports se há sintomas
      if (allSymptomsForSymptomReports.length > 0) {
        await saveToSymptomReportsTable(
          allSymptomsForSymptomReports,
          {
            caregiverID: baseResult.caregiverID,
            patientID: baseResult.patientID,
            scheduleID: body.scheduleID || "",
            reportID: reportID,
            reportType: "caregiver"
          },
          [], // symptomsWithScores já incluído nos objetos acima
          []  // symptomsToAlert já incluído nos objetos acima
        );
      }
      
    } catch (symptomReportsError) {
      console.error('❌ Erro ao salvar na tabela SymptomReports:', symptomReportsError);
    }
  }
}

module.exports = {
  processAlertsAndSave
};

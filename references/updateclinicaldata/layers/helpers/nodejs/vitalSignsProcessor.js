/**
 * Processador de sinais vitais - lógica consolidada do updateVitalSignsTable
 */

const { toDateSafe } = require('./utils');
const { dynamoDB, TABLES, getCurrentSymptomReport } = require('./dynamoHelpers');
const { QueryCommand } = require('@aws-sdk/client-dynamodb');

/**
 * Intervalos de normalidade para sinais vitais
 */
const VITAL_SIGNS_RANGES = {
  PAS: { min: 60, max: 220, name: 'Pressão Arterial Sistólica (PAS)' },
  FC: { min: 40, max: 190, name: 'Frequência Cardíaca (FC)' },
  FR: { min: 8, max: 70, name: 'Frequência Respiratória (FR)' },
  Temp: { min: 32, max: 41, name: 'Temperatura' },
  Sat: { min: 70, max: 100, name: 'Saturação de Oxigênio (SatO2)' }
};

/**
 * Valida se os sinais vitais estão dentro dos intervalos de normalidade
 */
function validateVitalSignsRanges(vitalSignsData, PAS) {
  const errors = [];
  
  // Valida PAS
  if (PAS > 0) {
    const pasRange = VITAL_SIGNS_RANGES.PAS;
    if (PAS < pasRange.min || PAS > pasRange.max) {
      errors.push(`${pasRange.name} está fora do padrão de normalidade (${PAS} mmHg). Intervalo aceito: ${pasRange.min}-${pasRange.max} mmHg`);
    }
  }
  
  // Valida FC
  const heartRate = Number(vitalSignsData.heartRate || 0);
  if (heartRate > 0) {
    const fcRange = VITAL_SIGNS_RANGES.FC;
    if (heartRate < fcRange.min || heartRate > fcRange.max) {
      errors.push(`${fcRange.name} está fora do padrão de normalidade (${heartRate} bpm). Intervalo aceito: ${fcRange.min}-${fcRange.max} bpm`);
    }
  }
  
  // Valida FR
  const respRate = Number(vitalSignsData.respRate || 0);
  if (respRate > 0) {
    const frRange = VITAL_SIGNS_RANGES.FR;
    if (respRate < frRange.min || respRate > frRange.max) {
      errors.push(`${frRange.name} está fora do padrão de normalidade (${respRate} rpm). Intervalo aceito: ${frRange.min}-${frRange.max} rpm`);
    }
  }
  
  // Valida Temperatura
  const temperature = Number(vitalSignsData.temperature || 0);
  if (temperature > 0) {
    const tempRange = VITAL_SIGNS_RANGES.Temp;
    if (temperature < tempRange.min || temperature > tempRange.max) {
      errors.push(`${tempRange.name} está fora do padrão de normalidade (${temperature}°C). Intervalo aceito: ${tempRange.min}-${tempRange.max}°C`);
    }
  }
  
  // Valida Saturação O2
  const saturationO2 = Number(vitalSignsData.saturationO2 || 0);
  if (saturationO2 > 0) {
    const satRange = VITAL_SIGNS_RANGES.Sat;
    if (saturationO2 < satRange.min || saturationO2 > satRange.max) {
      errors.push(`${satRange.name} está fora do padrão de normalidade (${saturationO2}%). Intervalo aceito: ${satRange.min}-${satRange.max}%`);
    }
  }
  
  return {
    isValid: errors.length === 0,
    errors: errors
  };
}

/**
 * Verifica se um sintoma teve recorrência nas últimas 72 horas
 */
async function hasRecentSymptom(
  patientID,
  symptomDefinition,
  hours = 72,
  currentSymptomReport = [],
  reportID = null,
  reportDate = null
) {
  try {
    const cutoffTime = new Date();
    cutoffTime.setHours(cutoffTime.getHours() - hours);

    // 1) Checa o SymptomReport "atual" (do plantão)
    if (reportID && reportDate && Array.isArray(currentSymptomReport) && currentSymptomReport.length > 0) {
      const hasInCurrent = currentSymptomReport.some(s =>
        s.symptomDefinition === symptomDefinition &&
        (!s.timestamp || toDateSafe(s.timestamp) >= cutoffTime)
      );
      if (hasInCurrent) {
        console.log(`🔄 Recorrência detectada para "${symptomDefinition}" no SymptomReport atual`);
        return true;
      }
    }

    // 2) Reports → busca por patientID e filtra item a item pelo timestamp do sintoma
    const reportsResp = await dynamoDB.send(new QueryCommand({
      TableName: TABLES.REPORTS,
      IndexName: 'patientIDIndex',
      KeyConditionExpression: 'patientID = :pid',
      ExpressionAttributeValues: { ':pid': { S: patientID } },
      ScanIndexForward: false,
      Limit: 100
    }));

    if (reportsResp.Items?.length) {
      for (const item of reportsResp.Items) {
        const symptoms = item.SymptomReport?.L || [];
        const reportBaseDate = toDateSafe(item.reportDate?.S || item.timestamp?.S || null);
        for (const s of symptoms) {
          const def = s.M?.symptomDefinition?.S;
          if (def !== symptomDefinition) continue;
          const ts = toDateSafe(s.M?.timestamp?.S) || reportBaseDate;
          if (ts && ts >= cutoffTime) {
            console.log(`🔄 Recorrência detectada para "${symptomDefinition}" nas últimas ${hours}h (Reports)`);
            return true;
          }
        }
      }
    }

    // 3) FamilyReports → mesma lógica
    const familyResp = await dynamoDB.send(new QueryCommand({
      TableName: TABLES.FAMILY_REPORTS,
      IndexName: 'patientID-index',
      KeyConditionExpression: 'patientID = :pid',
      ExpressionAttributeValues: { ':pid': { S: patientID } },
      ScanIndexForward: false,
      Limit: 100
    }));

    if (familyResp.Items?.length) {
      for (const item of familyResp.Items) {
        const symptoms = item.SymptomReport?.L || [];
        const reportBaseDate = toDateSafe(item.reportDate?.S || item.timestamp?.S || null);
        for (const s of symptoms) {
          const def = s.M?.symptomDefinition?.S;
          if (def !== symptomDefinition) continue;
          const ts = toDateSafe(s.M?.timestamp?.S) || reportBaseDate;
          if (ts && ts >= cutoffTime) {
            console.log(`🔄 Recorrência detectada para "${symptomDefinition}" nas últimas ${hours}h (FamilyReports)`);
            return true;
          }
        }
      }
    }

    return false;
  } catch (err) {
    console.error(`❌ Erro ao verificar recorrência do sintoma "${symptomDefinition}":`, err);
    return false;
  }
}

/**
 * Processa sintomas e calcula pontuação com lógica de recorrência
 */
async function processSymptomReport(symptomReportArray, patientID, symptomConfig, risco, currentSymptomReport = [], reportID = null, reportDate = null) {
  let totalSymptomScore = 0;
  const symptomsToAlert = [];
  const symptomsWithScores = [];
  const symptomsWithRecurrence = [];
  const allSymptomsForAlert = []; // Array com TODOS os sintomas para incluir em alertas

  if (!Array.isArray(symptomReportArray)) {
    return { totalSymptomScore, symptomsToAlert, symptomsWithScores, symptomsWithRecurrence, allSymptomsForAlert };
  }

  // Primeiro passo: calcular o totalSymptomScore e verificar recorrência
  for (const symptomItem of symptomReportArray) {
    const symptomDefinition = symptomItem.symptomDefinition;
    if (!symptomDefinition) continue;
    
    const config = symptomConfig[symptomDefinition];
    
    if (!config || typeof config !== 'object') {
      console.log(`⚠️  Sintoma não mapeado nas regras: "${symptomDefinition}"`);
      continue;
    }
    
    const score = typeof config === 'number' ? config : config.score;
    const shouldCheckFreq = typeof config === 'object' && config.freq;
    
    if (typeof score !== 'number') {
      console.log(`⚠️  Score inválido para sintoma: "${symptomDefinition}"`);
      continue;
    }
    
    // Adiciona TODOS os sintomas ao allSymptomsForAlert (para incluir em alertas quando necessário)
    allSymptomsForAlert.push({
      altNotepadMain: symptomItem.altNotepadMain || symptomDefinition,
      symptomCategory: symptomItem.symptomCategory || '',
      symptomSubCategory: symptomItem.symptomSubCategory || '',
      symptomDefinition: symptomDefinition
    });
    
    // Verifica recorrência se necessário
    let hasRecurrence = false;
    if (shouldCheckFreq && patientID) {
      try {
        hasRecurrence = await hasRecentSymptom(
          patientID, 
          symptomDefinition, 
          72, // hours
          currentSymptomReport, 
          reportID, 
          reportDate
        );
        if (hasRecurrence) {
          symptomsWithRecurrence.push({
            symptomDefinition: symptomDefinition,
            symptomCategory: symptomItem.symptomCategory || '',
            symptomSubCategory: symptomItem.symptomSubCategory || '',
            altNotepadMain: symptomItem.altNotepadMain || symptomDefinition,
            recurrence: true
          });
          console.log(`🔄 Sintoma com recorrência detectada: "${symptomDefinition}" - conta no score mas não gera alerta individual`);
        }
      } catch (err) {
        console.error(`❌ Erro ao verificar recorrência para "${symptomDefinition}":`, err);
        hasRecurrence = false;
      }
    }
    
    // Nova lógica: sintomas com freq=Sim e recorrência não contam no score
    let effectiveScore = score;
    if (shouldCheckFreq && hasRecurrence) {
      effectiveScore = 0;
      console.log(`📊 Sintoma "${symptomDefinition}" tem recorrência e freq=Sim - score zerado (original: ${score}, efetivo: ${effectiveScore})`);
    } else {
      console.log(`📊 Adicionando ${score} pontos para "${symptomDefinition}"`);
    }
    
    totalSymptomScore += effectiveScore;
    console.log(`📊 Score total atual: ${totalSymptomScore}${hasRecurrence && shouldCheckFreq ? ' [RECORRÊNCIA - SCORE ZERADO]' : ''}`);
    
    // Adiciona sintoma com score ao array (mostra score original e efetivo)
    symptomsWithScores.push({
      symptom: symptomDefinition,
      score: effectiveScore,
      originalScore: score,
      hasRecurrence: hasRecurrence
    });
  }

  // Segundo passo: avaliar alertas
  let hasNonRecurrentAlert = false;
  const potentialAlerts = [];

  for (const symptomItem of symptomReportArray) {
    const symptomDefinition = symptomItem.symptomDefinition;
    if (!symptomDefinition) continue;
    
    const config = symptomConfig[symptomDefinition];
    if (!config) continue;
    
    const score = typeof config === 'number' ? config : config.score;
    const shouldCheckFreq = typeof config === 'object' && config.freq;
    
    if (typeof score !== 'number') continue;
    
    // Verifica se tem recorrência
    const hasRecurrence = symptomsWithRecurrence.some(s => s.symptomDefinition === symptomDefinition);
    
    // Nova lógica para ALERTAS (usa score original, não efetivo):
    let shouldAlert = false;
    if (score >= 4 && !hasRecurrence) {
      console.log(`🚨 Sintoma com score alto (${score}): "${symptomDefinition}" - sempre gera alerta`);
      shouldAlert = true;
      hasNonRecurrentAlert = true;
    } else if (score >= 4 && hasRecurrence) {
      console.log(`⏭️  Sintoma com score alto (${score}) mas com recorrência: "${symptomDefinition}" - não gera alerta individual`);
      potentialAlerts.push({
        symptomDefinition: symptomDefinition,
        symptomCategory: symptomItem.symptomCategory || '',
        symptomSubCategory: symptomItem.symptomSubCategory || '',
        altNotepadMain: symptomItem.altNotepadMain || symptomDefinition,
        isRecurrent: true
      });
    } else if (risco === 'Alto' || risco === 'Critico') {
      if (!hasRecurrence) {
        console.log(`⚠️  Sintoma com score baixo (${score}) mas risco ${risco}: "${symptomDefinition}" - gera alerta`);
        shouldAlert = true;
        hasNonRecurrentAlert = true;
      } else {
        console.log(`⏭️  Sintoma com score baixo (${score}) e risco ${risco} mas com recorrência: "${symptomDefinition}" - potencial para alerta`);
        potentialAlerts.push({
          symptomDefinition: symptomDefinition,
          symptomCategory: symptomItem.symptomCategory || '',
          symptomSubCategory: symptomItem.symptomSubCategory || '',
          altNotepadMain: symptomItem.altNotepadMain || symptomDefinition,
          isRecurrent: true
        });
      }
    } else if (risco === 'Moderado' && totalSymptomScore >= 4) {
      if (!hasRecurrence) {
        console.log(`⚠️  Sintoma com score baixo (${score}) mas risco Moderado e totalSymptomScore >= 4 (${totalSymptomScore}): "${symptomDefinition}" - gera alerta`);
        shouldAlert = true;
        hasNonRecurrentAlert = true;
      } else {
        console.log(`⏭️  Sintoma com score baixo (${score}) e risco Moderado mas com recorrência: "${symptomDefinition}" - potencial para alerta`);
        potentialAlerts.push({
          symptomDefinition: symptomDefinition,
          symptomCategory: symptomItem.symptomCategory || '',
          symptomSubCategory: symptomItem.symptomSubCategory || '',
          altNotepadMain: symptomItem.altNotepadMain || symptomDefinition,
          isRecurrent: true
        });
      }
    } else {
      if (risco === 'SemSinaisVitais') {
        console.log(`⏭️  Sintoma com score baixo (${score}) (totalSymptomScore: ${totalSymptomScore}): "${symptomDefinition}" - não gera alerta`);
      } else {
        console.log(`⏭️  Sintoma com score baixo (${score}) e risco ${risco} (totalSymptomScore: ${totalSymptomScore}): "${symptomDefinition}" - não gera alerta`);
      }
    }
    
    if (shouldAlert) {
      symptomsToAlert.push({
        symptomDefinition: symptomDefinition,
        symptomCategory: symptomItem.symptomCategory || '',
        symptomSubCategory: symptomItem.symptomSubCategory || '',
        altNotepadMain: symptomItem.altNotepadMain || symptomDefinition
      });
    }
  }

  // Se há alertas não recorrentes, inclui também os sintomas com recorrência
  if (hasNonRecurrentAlert && potentialAlerts.length > 0) {
    console.log(`🔄 Incluindo ${potentialAlerts.length} sintomas com recorrência no alerta devido a outros sintomas que geram alerta`);
    symptomsToAlert.push(...potentialAlerts.filter(s => !symptomsToAlert.some(existing => existing.symptomDefinition === s.symptomDefinition)));
  }

  return { totalSymptomScore, symptomsToAlert, symptomsWithScores, symptomsWithRecurrence, allSymptomsForAlert };
}

/**
 * Converte day (DD/MM/YYYY) e time (HH:MM:SS) em um objeto Date.
 * Caso sejam valores inválidos, retorna null.
 * Também suporta o formato antigo diaAfericao (YYYY-MM-DD) para compatibilidade.
 */
function parseDateTime(dia, horario) {
  if (!dia || !horario || dia === 'Nao analisado' || horario === 'Nao analisado') {
    return null;
  }

  // Verifica se é o formato antigo (YYYY-MM-DD) ou novo (DD/MM/YYYY)
  let dateTimeString;
  if (dia.includes('/')) {
    // Formato novo (DD/MM/YYYY) - converte para ISO
    const [day, month, year] = dia.split('/');
    dateTimeString = `${year}-${month}-${day}T${horario}`;
  } else {
    // Formato antigo (YYYY-MM-DD)
    dateTimeString = `${dia}T${horario}`;
  }

  const dateObj = new Date(dateTimeString);
  return isNaN(dateObj.getTime()) ? null : dateObj;
}

/**
 * Busca todas as aferições anteriores de um paciente via GSI patientID-index,
 * ordena por data/hora e retorna todos os itens (sem limite).
 */
async function getAllMeasures(patientID) {
  if (!patientID) return [];
  try {
    const result = await dynamoDB.send(
      new QueryCommand({
        TableName: TABLES.VITAL_SIGNS,
        IndexName: 'patientID-index',
        KeyConditionExpression: 'patientID = :pid',
        ExpressionAttributeValues: {
          ':pid': { S: patientID },
        },
      })
    );
    const allItems = result.Items || [];
    return allItems.sort((a, b) => {
      // Suporta tanto o formato antigo (diaAfericao/horarioAfericao) quanto o novo (day/time)
      const dateA = parseDateTime(a.day?.S || a.diaAfericao?.S, a.time?.S || a.horarioAfericao?.S);
      const dateB = parseDateTime(b.day?.S || b.diaAfericao?.S, b.time?.S || b.horarioAfericao?.S);
      if (!dateA && !dateB) return 0;
      if (!dateA) return 1;
      if (!dateB) return -1;
      return dateB - dateA;
    });
  } catch (err) {
    console.error('Erro ao buscar todas aferições:', err);
    return [];
  }
}

/**
 * Calcula média (avg) e desvio padrão (sd) de um array de números.
 * Retorna { avg, sd }.
 */
function calcAvgAndSD(values) {
  const n = values.length;
  if (n === 0) return { avg: 0, sd: 0 };
  const mean = values.reduce((acc, v) => acc + v, 0) / n;
  const variance = values.reduce((acc, v) => acc + Math.pow(v - mean, 2), 0) / n;
  return { avg: mean, sd: Math.sqrt(variance) };
}

/**
 * Calcula as médias e desvios padrão das variáveis: heartRate, respRate, saturationO2 e PAS
 * a partir de um array de itens do DynamoDB.
 */
function computeHistoricStats(items) {
  if (items.length < 1) {
    return {
      avgHeartRate: 0, sdHeartRate: 0,
      avgRespRate: 0, sdRespRate: 0,
      avgSaturationO2: 0, sdSaturationO2: 0,
      avgPAS: 0, sdPAS: 0
    };
  }
  const heartRates = [], respRates = [], saturations = [], pass = [];
  for (const item of items) {
    const hr = Number(item.heartRate?.N || '0');
    const rr = Number(item.respRate?.N || '0');
    const sat = Number(item.saturationO2?.N || '0');
    const p = Number(item.PAS?.N || '0');
    if (hr > 0) heartRates.push(hr);
    if (rr > 0) respRates.push(rr);
    if (sat > 0) saturations.push(sat);
    if (p > 0) pass.push(p);
  }
  const { avg: avgHeartRate, sd: sdHeartRate } = calcAvgAndSD(heartRates);
  const { avg: avgRespRate, sd: sdRespRate } = calcAvgAndSD(respRates);
  const { avg: avgSaturationO2, sd: sdSaturationO2 } = calcAvgAndSD(saturations);
  const { avg: avgPAS, sd: sdPAS } = calcAvgAndSD(pass);
  return { avgHeartRate, sdHeartRate, avgRespRate, sdRespRate, avgSaturationO2, sdSaturationO2, avgPAS, sdPAS };
}

/**
 * Calcula a pontuação absoluta e o breakdown com base nas variáveis:
 * heartRate, respRate, saturationO2, PAS, sintomas e temperatura.
 */
async function calculateAbsoluteScore(vitalSignsData, PAS, patientID, symptomConfig, currentSymptomReport = [], reportID = null, reportDate = null) {
  let scoreBreakdown = {
    heartRate: 0, respRate: 0, saturationO2: 0, PAS: 0,
    symptoms: 0, temperature: 0
  };

  // FC
  if (vitalSignsData.heartRate > 0) {
    if (vitalSignsData.heartRate < 40 || vitalSignsData.heartRate > 150) scoreBreakdown.heartRate = 5;
    else if ((vitalSignsData.heartRate >= 40 && vitalSignsData.heartRate <= 44) || (vitalSignsData.heartRate >= 141 && vitalSignsData.heartRate <= 150)) scoreBreakdown.heartRate = 4;
    else if ((vitalSignsData.heartRate >= 45 && vitalSignsData.heartRate <= 49) || (vitalSignsData.heartRate >= 121 && vitalSignsData.heartRate <= 140)) scoreBreakdown.heartRate = 3;
    else if ((vitalSignsData.heartRate >= 50 && vitalSignsData.heartRate <= 54) || (vitalSignsData.heartRate >= 111 && vitalSignsData.heartRate <= 120)) scoreBreakdown.heartRate = 2;
    else if ((vitalSignsData.heartRate >= 55 && vitalSignsData.heartRate <= 59) || (vitalSignsData.heartRate >= 101 && vitalSignsData.heartRate <= 110)) scoreBreakdown.heartRate = 1;
  }

  // FR
  if (vitalSignsData.respRate > 0) {
    if (vitalSignsData.respRate < 5 || vitalSignsData.respRate > 40) scoreBreakdown.respRate = 5;
    else if (vitalSignsData.respRate >= 36 && vitalSignsData.respRate <= 40) scoreBreakdown.respRate = 4;
    else if (vitalSignsData.respRate >= 31 && vitalSignsData.respRate <= 35) scoreBreakdown.respRate = 3;
    else if ((vitalSignsData.respRate >= 6 && vitalSignsData.respRate <= 8) || (vitalSignsData.respRate >= 25 && vitalSignsData.respRate <= 30)) scoreBreakdown.respRate = 2;
    else if ((vitalSignsData.respRate >= 9 && vitalSignsData.respRate <= 11) || (vitalSignsData.respRate >= 21 && vitalSignsData.respRate <= 24)) scoreBreakdown.respRate = 1;
  }

  // Saturação O2 (nova regra)
  const sat = vitalSignsData.saturationO2;
  if (sat > 0) {
    if (sat >= 95) scoreBreakdown.saturationO2 = 0;
    else if (sat >= 93) scoreBreakdown.saturationO2 = 1;
    else if (sat >= 91) scoreBreakdown.saturationO2 = 2;
    else if (sat >= 89) scoreBreakdown.saturationO2 = 3;
    else if (sat >= 87) scoreBreakdown.saturationO2 = 4;
    else scoreBreakdown.saturationO2 = 5;
  }

  // PAS
  if (PAS > 0) {
    if (PAS >= 180) scoreBreakdown.PAS = 5;       // nova regra
    else if (PAS >= 160) scoreBreakdown.PAS = 4;  // nova regra
    else if (PAS >= 110) scoreBreakdown.PAS = 0;
    else if (PAS >= 100) scoreBreakdown.PAS = 1;
    else if (PAS >= 90) scoreBreakdown.PAS = 2;
    else if (PAS >= 80) scoreBreakdown.PAS = 3;
    else if (PAS >= 75) scoreBreakdown.PAS = 4;
    else scoreBreakdown.PAS = 5;
  }

  // Processa apenas sintomas do SymptomReport
  let symptomReportScore = 0;
  let allSymptomsWithScores = [];
  if (vitalSignsData.SymptomReport && Array.isArray(vitalSignsData.SymptomReport)) {
    const { totalSymptomScore: reportScore, symptomsWithScores: reportSymptomsWithScores } = await processSymptomReport(vitalSignsData.SymptomReport, patientID, symptomConfig, 'Baixo', currentSymptomReport, reportID, reportDate);
    symptomReportScore = reportScore;
    allSymptomsWithScores = reportSymptomsWithScores;
  }

  // Score de sintomas vem apenas do SymptomReport
  scoreBreakdown.symptoms = symptomReportScore;

  // Temperatura
  if (Number(vitalSignsData.temperature) > 37.7) {
    scoreBreakdown.temperature = 5;
  }

  const totalScore = Object.values(scoreBreakdown).reduce((acc, v) => acc + v, 0);
  return { totalScore, scoreBreakdown, allSymptomsWithScores };
}

/**
 * Calcula os z-scores para FC (Frequência Cardíaca), FR (Frequência Respiratória), 
 * SatO2 (Saturação de Oxigênio) e PAS (Pressão Arterial Sistólica).
 * 
 * Limites aplicados:
 * - PAS e FR: z-score limitado entre -3 e 3
 * - FC e SatO2: z-score limitado entre -5 e 5 (padrão anterior)
 */
function computeZScores(vitalSignsData, PAS, stats) {
  function zScore(value, avg, sd, minLimit = -5, maxLimit = 5) {
    if (sd === 0) return 0;
    let z = (value - avg) / sd;
    if (z > maxLimit) z = maxLimit;
    if (z < minLimit) z = minLimit;
    return z;
  }
  
  return {
    zHeartRate: zScore(vitalSignsData.heartRate, stats.avgHeartRate, stats.sdHeartRate, -5, 5), // Limite padrão -5 a 5
    zRespRate: zScore(vitalSignsData.respRate, stats.avgRespRate, stats.sdRespRate, -3, 3),     // Limite específico -3 a 3 para FR
    zSaturationO2: zScore(vitalSignsData.saturationO2, stats.avgSaturationO2, stats.sdSaturationO2, -5, 5), // Limite padrão -5 a 5
    zPAS: zScore(PAS, stats.avgPAS, stats.sdPAS, -3, 3)  // Limite específico -3 a 3 para PAS
  };
}

/**
 * Calcula a pontuação relativa combinada.
 */
function computeRelativeScore(scoreBreakdown, zScores) {
  function contribution(z, breakdown, type) {
    if (type === 'FC' || type === 'FR') {
      return breakdown < 2 ? breakdown : breakdown * Math.abs(z);
    } else if (type === 'SatO2' || type === 'PAS') {
      return z > 0 ? breakdown : breakdown * Math.abs(z);
    }
    return breakdown * Math.abs(z);
  }
  const numeric =
    contribution(zScores.zHeartRate, scoreBreakdown.heartRate, 'FC') +
    contribution(zScores.zRespRate, scoreBreakdown.respRate, 'FR') +
    contribution(zScores.zSaturationO2, scoreBreakdown.saturationO2, 'SatO2') +
    contribution(zScores.zPAS, scoreBreakdown.PAS, 'PAS');
  const symptom = scoreBreakdown.symptoms + scoreBreakdown.temperature;
  return numeric + symptom;
}

/**
 * Calcula o breakdown relativo com a contribuição de cada aferição no score relativo.
 */
function computeRelativeBreakdown(scoreBreakdown, zScores) {
  function contribution(z, breakdown, type) {
    if (type === 'FC' || type === 'FR') {
      return breakdown < 2 ? breakdown : breakdown * Math.abs(z);
    } else if (type === 'SatO2' || type === 'PAS') {
      return z > 0 ? breakdown : breakdown * Math.abs(z);
    }
    return breakdown * Math.abs(z);
  }

  return {
    heartRate: contribution(zScores.zHeartRate, scoreBreakdown.heartRate, 'FC'),
    respRate: contribution(zScores.zRespRate, scoreBreakdown.respRate, 'FR'),
    saturationO2: contribution(zScores.zSaturationO2, scoreBreakdown.saturationO2, 'SatO2'),
    PAS: contribution(zScores.zPAS, scoreBreakdown.PAS, 'PAS'),
    symptoms: scoreBreakdown.symptoms,
    temperature: scoreBreakdown.temperature
  };
}

module.exports = {
  VITAL_SIGNS_RANGES,
  validateVitalSignsRanges,
  hasRecentSymptom,
  processSymptomReport,
  parseDateTime,
  getAllMeasures,
  calcAvgAndSD,
  computeHistoricStats,
  calculateAbsoluteScore,
  computeZScores,
  computeRelativeScore,
  computeRelativeBreakdown
};

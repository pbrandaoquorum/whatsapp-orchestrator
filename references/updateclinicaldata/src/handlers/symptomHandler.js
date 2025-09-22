/**
 * Handler para processamento de SymptomReport
 */

const { 
  dynamoDB, 
  TABLES,
  getReportData,
  getCurrentSymptomReport,
  getCaregiverData,
  getPatientData
} = require('/opt/nodejs/dynamoHelpers');

const { 
  processSymptomReport 
} = require('/opt/nodejs/vitalSignsProcessor');

const { 
  createAlert 
} = require('/opt/nodejs/alertProcessor');

const { 
  generateUUID, 
  getCurrentTimestampBR, 
  getNowInSaoPaulo 
} = require('/opt/nodejs/utils');

const { formatSymptomForDynamoDB } = require('../utils/symptomFormatter');

const { 
  DynamoDBClient, 
  UpdateItemCommand, 
  PutItemCommand, 
  GetItemCommand 
} = require('@aws-sdk/client-dynamodb');

/**
 * Processa SymptomReport e salva nas tabelas Reports/FamilyReports e SymptomReports
 */
async function processSymptomReportData(body, familyData = null, regras = [], shouldCreateAlerts = true) {
  const { reportID, reportDate, SymptomReport, phoneNumber } = body;
  
  if (!Array.isArray(SymptomReport) || SymptomReport.length === 0) {
    console.log('ℹ️ Nenhum SymptomReport para processar');
    return { saved: false, symptomsProcessed: 0 };
  }

  // Converte regras em mapa para acesso rápido
  const symptomConfig = {};
  if (Array.isArray(regras) && regras.length > 0) {
    regras.forEach(regra => {
      if (regra.sintoma && typeof regra.pontuacao === 'number') {
        symptomConfig[regra.sintoma] = {
          score: regra.pontuacao,
          freq: regra.freq === 'Sim'
        };
      }
    });
    console.log(`📋 Regras carregadas: ${Object.keys(symptomConfig).length} sintomas mapeados`);
  }

  const timestamp = getNowInSaoPaulo().toISOString();
  const timestampBR = getCurrentTimestampBR();

  // Determina patientID para verificação de recorrência
  let patientIDForRecurrence = familyData?.patientID || null;
  let reportData = null;
  
  if (!patientIDForRecurrence && reportID && reportDate) {
    reportData = await getReportData(reportID, reportDate);
    patientIDForRecurrence = reportData.patientID;
  }

  // Busca SymptomReport atual do plantão para verificação de recorrência
  let currentSymptomReport = [];
  if (reportID && reportDate) {
    currentSymptomReport = await getCurrentSymptomReport(reportID, reportDate);
  }

  // Processa sintomas para score e alertas usando a lógica completa
  const { totalSymptomScore: totalScore, symptomsToAlert, symptomsWithScores, symptomsWithRecurrence } = 
    await processSymptomReport(
      SymptomReport, 
      patientIDForRecurrence, 
      symptomConfig, 
      'SemSinaisVitais', // risco especial para cenário sem sinais vitais
      currentSymptomReport, 
      reportID, 
      reportDate
    );
  
  console.log(`📊 Score total dos sintomas: ${totalScore}`);
  console.log(`🔍 Encontrados ${symptomsToAlert.length} sintomas para alerta`);
  
  // Identificar sintomas com score alto
  const highScoreSymptoms = SymptomReport.filter(item => {
    const config = symptomConfig[item.symptomDefinition];
    return config && config.score >= 4;
  });

  // Determina se deve criar alerta baseado no resultado do processamento
  let shouldCreateAlert = false;
  let alertReason = "";

  if (symptomsToAlert.length > 0) {
    shouldCreateAlert = true;
    if (highScoreSymptoms.length > 0) {
      alertReason = `${highScoreSymptoms.length} sintoma(s) com score alto (>=4)`;
    } else if (totalScore >= 5) {
      alertReason = `somatório total de ${totalScore} (>=5)`;
    } else {
      alertReason = `critérios de alerta atendidos`;
    }
  }

  // Cria alerta se necessário (apenas se shouldCreateAlerts for true)
  if (shouldCreateAlerts && shouldCreateAlert && symptomsToAlert.length > 0) {
    try {
      let alertData = null;
      
      if (phoneNumber && familyData) {
        const patientData = await getPatientData(familyData.patientID);
        alertData = {
          caregiverID: "",
          caregiverName: `familiar ${familyData.fullName}`,
          caregiverCompany: patientData.company,
          caregiverCooperative: "",
          company: patientData.company,
          patientID: familyData.patientID,
          patientName: patientData.fullName
        };
      } else if (reportID && reportDate) {
        if (!reportData) {
          reportData = await getReportData(reportID, reportDate);
        }
        
        if (reportData.caregiverID && reportData.patientID) {
          const caregiverData = await getCaregiverData(reportData.caregiverID);
          const patientData = await getPatientData(reportData.patientID);
          
          alertData = {
            caregiverID: reportData.caregiverID,
            caregiverName: caregiverData.fullName,
            caregiverCompany: caregiverData.company,
            caregiverCooperative: caregiverData.cooperative,
            company: reportData.company,
            patientID: reportData.patientID,
            patientName: patientData.fullName
          };
        }
      }
      
      if (alertData && alertData.patientID) {
        // Se há sintomas que causaram alerta, inclui TODOS os sintomas no alerta
        const allSymptomsForAlert = SymptomReport.map(symptom => ({
          altNotepadMain: symptom.altNotepadMain || symptom.symptomDefinition,
          symptomCategory: symptom.symptomCategory || '',
          symptomSubCategory: symptom.symptomSubCategory || '',
          symptomDefinition: symptom.symptomDefinition || ''
        })).filter(item => item.symptomDefinition);
        
        const alertSymptoms = allSymptomsForAlert.map(symptom => ({
          M: {
            altNotepadMain: { S: symptom.altNotepadMain || "" },
            symptomCategory: { S: symptom.symptomCategory || "" },
            symptomSubCategory: { S: symptom.symptomSubCategory || "" },
            symptomDefinition: { S: symptom.symptomDefinition || "" },
            timestamp: { S: timestamp }
          }
        }));

        await createAlert({
          alerts: alertSymptoms,
          ...alertData
        });
        console.log(`🚨 Alerta criado para ${allSymptomsForAlert.length} sintomas - Motivo: ${alertReason}`);
      }
    } catch (err) {
      console.error("❌ Erro ao processar sintomas para alertas:", err);
    }
  } else if (!shouldCreateAlerts && shouldCreateAlert && symptomsToAlert.length > 0) {
    console.log(`⏸️ Alertas de sintomas desabilitados - será tratado pelos sinais vitais`);
  }

  // Salva SymptomReport na tabela apropriada
  if (phoneNumber && familyData) {
    // Fluxo família - salva na FamilyReports
    await saveFamilySymptomReport(familyData, SymptomReport, symptomsWithScores, symptomsToAlert, timestamp, timestampBR);
    
  } else {
    // Fluxo normal - atualiza Reports
    await saveNormalSymptomReport(reportID, reportDate, SymptomReport, symptomsWithScores, symptomsToAlert, timestamp, body, reportData, shouldCreateAlerts);
  }

  return { 
    saved: true, 
    symptomsProcessed: SymptomReport.length, 
    totalScore,
    alertCreated: shouldCreateAlert,
    alertReason: shouldCreateAlert ? alertReason : "Score insuficiente"
  };
}

/**
 * Salva SymptomReport para fluxo da família
 */
async function saveFamilySymptomReport(familyData, SymptomReport, symptomsWithScores, symptomsToAlert, timestamp, timestampBR) {
  const familyReportID = generateUUID();
  
  // Formata com score e alert para FamilyReports
  const formattedSymptomReport = SymptomReport.map((item) => 
    formatSymptomForDynamoDB(item, symptomsWithScores, symptomsToAlert, timestamp)
  );

  const putCmd = new PutItemCommand({
    TableName: TABLES.FAMILY_REPORTS,
    Item: {
      familyReportID: { S: familyReportID },
      familyMemberID: { S: familyData.familyMemberID },
      familyID: { S: familyData.familyID },
      patientID: { S: familyData.patientID },
      SymptomReport: { L: formattedSymptomReport },
      timestamp: { S: timestampBR }
    }
  });

  await dynamoDB.send(putCmd);
  console.log(`✅ SymptomReport salvo na FamilyReports - familyReportID=${familyReportID}`);
  
  // Salva também na tabela SymptomReports
  await saveToSymptomReportsTable(SymptomReport, {
    caregiverID: "",
    patientID: familyData.patientID,
    scheduleID: "",
    reportID: familyReportID,
    reportType: "family"
  }, symptomsWithScores, symptomsToAlert);
}

/**
 * Salva SymptomReport para fluxo normal
 */
async function saveNormalSymptomReport(reportID, reportDate, SymptomReport, symptomsWithScores, symptomsToAlert, timestamp, body, reportData, shouldCreateAlerts = true) {
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
        score: parseInt(item.M.score?.N || '0'),
        alert: item.M.alert?.BOOL || false,
        timestamp: item.M.timestamp?.S || ''
      }));
    }
  } catch (getError) {
    console.log('📋 Nenhum SymptomReport existente encontrado');
  }
  
  // Combina sintomas existentes + novos (novos com score e alert)
  const newSymptomsFormatted = SymptomReport.map((item) => 
    formatSymptomForDynamoDB(item, symptomsWithScores, symptomsToAlert, timestamp)
  );
  
  // Preserva sintomas existentes (já formatados) e adiciona novos
  const existingFormatted = existingSymptomReport.map(item => ({
    M: {
      altNotepadMain: { S: item.altNotepadMain },
      symptomCategory: { S: item.symptomCategory },
      symptomSubCategory: { S: item.symptomSubCategory },
      symptomDefinition: { S: item.symptomDefinition },
      score: { N: item.score.toString() },
      alert: { BOOL: item.alert },
      timestamp: { S: item.timestamp },
    }
  }));
  
  const finalFormattedSymptomReport = [...existingFormatted, ...newSymptomsFormatted];

  await dynamoDB.send(
    new UpdateItemCommand({
      TableName: TABLES.REPORTS,
      Key: {
        reportID: { S: reportID },
        reportDate: { S: reportDate },
      },
      UpdateExpression: "SET SymptomReport = :sr",
      ExpressionAttributeValues: {
        ":sr": { L: finalFormattedSymptomReport },
      },
    })
  );
  console.log(`✅ SymptomReport atualizado na Reports com ${finalFormattedSymptomReport.length} sintomas`);
  
  // Salva também na tabela SymptomReports apenas se shouldCreateAlerts for true
  if (shouldCreateAlerts) {
    if (!reportData) {
      reportData = await getReportData(reportID, reportDate);
    }
    
    await saveToSymptomReportsTable(SymptomReport, {
      caregiverID: reportData.caregiverID,
      patientID: reportData.patientID,
      scheduleID: body.scheduleID || "",
      reportID: reportID,
      reportType: "caregiver"
    }, symptomsWithScores, symptomsToAlert);
  } else {
    console.log(`⏸️ Salvamento na SymptomReports desabilitado - será tratado pelos sinais vitais`);
  }
}

/**
 * Salva dados na tabela SymptomReports
 */
async function saveToSymptomReportsTable(symptomReport, metadata, symptomsWithScores = [], symptomsToAlert = []) {
  const symptomReportID = generateUUID();
  const timestamp = getCurrentTimestampBR();
  
  // Formata SymptomReport para DynamoDB com score e alert
  const formattedSymptomReport = symptomReport.map((item) => 
    formatSymptomForDynamoDB(item, symptomsWithScores, symptomsToAlert, timestamp)
  );

  const putCmd = new PutItemCommand({
    TableName: TABLES.SYMPTOM_REPORTS,
    Item: {
      symptomReportID: { S: symptomReportID },
      caregiverID: { S: metadata.caregiverID },
      patientID: { S: metadata.patientID },
      scheduleID: { S: metadata.scheduleID },
      reportID: { S: metadata.reportID },
      reportType: { S: metadata.reportType },
      SymptomReport: { L: formattedSymptomReport },
      timestamp: { S: timestamp }
    }
  });

  await dynamoDB.send(putCmd);
  console.log(`✅ SymptomReport salvo na tabela SymptomReports - symptomReportID=${symptomReportID}`);
  
  return symptomReportID;
}

module.exports = {
  processSymptomReportData,
  saveToSymptomReportsTable
};

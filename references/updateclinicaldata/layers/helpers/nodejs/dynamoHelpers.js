/**
 * Helpers para operações com DynamoDB
 */

const { DynamoDBClient, GetItemCommand, UpdateItemCommand, PutItemCommand, QueryCommand } = require('@aws-sdk/client-dynamodb');

const dynamoDB = new DynamoDBClient({ region: process.env.REGION || 'sa-east-1' });

// Nomes das tabelas
const TABLES = {
  REPORTS: process.env.REPORTS_TABLE || 'Reports',
  FAMILY_REPORTS: process.env.FAMILY_REPORTS_TABLE || 'FamilyReports',
  FAMILY_MEMBERS: process.env.FAMILY_MEMBERS_TABLE || 'FamilyMembers',
  SYMPTOM_REPORTS: process.env.SYMPTOM_REPORTS_TABLE || 'SymptomReports',
  ALERTS: process.env.ALERTS_TABLE || 'Alerts',
  CAREGIVERS: process.env.CAREGIVERS_TABLE || 'Caregivers',
  PATIENTS: process.env.PATIENTS_TABLE || 'Patients',
  VITAL_SIGNS: process.env.VITAL_SIGNS_TABLE || 'VitalSigns',
  VITAL_SIGNS_TEST: process.env.VITAL_SIGNS_TEST_TABLE || 'VitalSignsTest',
  WORK_SCHEDULES: process.env.WORK_SCHEDULES_TABLE || 'WorkSchedules'
};

/**
 * Busca dados da família pelo phoneNumber
 */
async function getFamilyDataByPhone(phoneNumber) {
  try {
    const queryCommand = new QueryCommand({
      TableName: TABLES.FAMILY_MEMBERS,
      IndexName: "phoneNumber-index",
      KeyConditionExpression: "#pn = :pn",
      ExpressionAttributeNames: { "#pn": "phoneNumber" },
      ExpressionAttributeValues: { ":pn": { S: phoneNumber } },
      ProjectionExpression: "familyMemberID, familyID, patientID, fullName"
    });
    
    const result = await dynamoDB.send(queryCommand);
    if (!result.Items || result.Items.length === 0) {
      throw new Error("Membro da família não encontrado para o telefone informado");
    }
    
    const member = result.Items[0];
    return {
      familyMemberID: member.familyMemberID?.S || "",
      familyID: member.familyID?.S || "",
      patientID: member.patientID?.S || "",
      fullName: member.fullName?.S || ""
    };
  } catch (err) {
    console.error(`❌ Erro ao buscar família pelo telefone ${phoneNumber}:`, err);
    throw err;
  }
}

/**
 * Busca dados do caregiver na tabela Caregivers
 */
async function getCaregiverData(caregiverID) {
  try {
    const response = await dynamoDB.send(
      new GetItemCommand({
        TableName: TABLES.CAREGIVERS,
        Key: { caregiverID: { S: caregiverID } },
        ProjectionExpression: "fullName, company, cooperative"
      })
    );
    return {
      fullName: response.Item?.fullName?.S || "",
      company: response.Item?.company?.S || "",
      cooperative: response.Item?.cooperative?.S || ""
    };
  } catch (err) {
    console.error(`❌ Erro ao buscar caregiver ${caregiverID}:`, err);
    return { fullName: "", company: "", cooperative: "" };
  }
}

/**
 * Busca dados do paciente na tabela Patients
 */
async function getPatientData(patientID) {
  try {
    const response = await dynamoDB.send(
      new GetItemCommand({
        TableName: TABLES.PATIENTS,
        Key: { patientID: { S: patientID } },
        ProjectionExpression: "fullName, company"
      })
    );
    return {
      fullName: response.Item?.fullName?.S || "",
      company: response.Item?.company?.S || ""
    };
  } catch (err) {
    console.error(`❌ Erro ao buscar paciente ${patientID}:`, err);
    return { fullName: "", company: "" };
  }
}

/**
 * Busca dados adicionais do report (caregiverID, patientID, company)
 */
async function getReportData(reportID, reportDate) {
  try {
    const response = await dynamoDB.send(
      new GetItemCommand({
        TableName: TABLES.REPORTS,
        Key: {
          reportID: { S: reportID },
          reportDate: { S: reportDate }
        },
        ProjectionExpression: "caregiverID, patientID, company"
      })
    );
    return {
      caregiverID: response.Item?.caregiverID?.S || "",
      patientID: response.Item?.patientID?.S || "",
      company: response.Item?.company?.S || ""
    };
  } catch (err) {
    console.error(`❌ Erro ao buscar dados do report ${reportID}:`, err);
    return { caregiverID: "", patientID: "", company: "" };
  }
}

/**
 * Busca o SymptomReport atual do plantão se existir
 */
async function getCurrentSymptomReport(reportID, reportDate) {
  if (!reportID || !reportDate) return [];
  
  try {
    const response = await dynamoDB.send(
      new GetItemCommand({
        TableName: TABLES.REPORTS,
        Key: {
          reportID: { S: reportID },
          reportDate: { S: reportDate }
        },
        ProjectionExpression: "SymptomReport"
      })
    );
    
    if (response.Item && response.Item.SymptomReport && response.Item.SymptomReport.L) {
      // Converte o formato DynamoDB de volta para objeto JavaScript
      return response.Item.SymptomReport.L.map(item => ({
        altNotepadMain: item.M.altNotepadMain?.S || '',
        symptomCategory: item.M.symptomCategory?.S || '',
        symptomSubCategory: item.M.symptomSubCategory?.S || '',
        symptomDefinition: item.M.symptomDefinition?.S || '',
        timestamp: item.M.timestamp?.S || ''
      }));
    }
    
    return [];
  } catch (err) {
    console.error(`❌ Erro ao buscar SymptomReport atual:`, err);
    return [];
  }
}

/**
 * Atualiza contador de notas no WorkSchedules
 */
async function incrementQtNotes(scheduleID) {
  if (!scheduleID) return;
  
  try {
    await dynamoDB.send(new UpdateItemCommand({
      TableName: TABLES.WORK_SCHEDULES,
      Key: { scheduleID: { S: scheduleID } },
      UpdateExpression: 'SET qtNotes = if_not_exists(qtNotes, :start) + :inc',
      ExpressionAttributeValues: {
        ':start': { N: '0' },
        ':inc': { N: '1' }
      }
    }));
    console.log('✅ qtNotes incrementado com sucesso');
  } catch (err) {
    console.error('❌ Erro ao incrementar qtNotes:', err);
  }
}

/**
 * Atualiza contador de sinais vitais no WorkSchedules
 */
async function incrementQtVSMeasures(scheduleID) {
  if (!scheduleID) return;
  
  try {
    await dynamoDB.send(new UpdateItemCommand({
      TableName: TABLES.WORK_SCHEDULES,
      Key: { scheduleID: { S: scheduleID } },
      UpdateExpression: 'SET qtVSMeasures = if_not_exists(qtVSMeasures, :start) + :inc',
      ExpressionAttributeValues: {
        ':start': { N: '0' },
        ':inc': { N: '1' }
      }
    }));
    console.log('✅ qtVSMeasures incrementado com sucesso');
  } catch (err) {
    console.error('❌ Erro ao incrementar qtVSMeasures:', err);
  }
}

module.exports = {
  dynamoDB,
  TABLES,
  getFamilyDataByPhone,
  getCaregiverData,
  getPatientData,
  getReportData,
  getCurrentSymptomReport,
  incrementQtNotes,
  incrementQtVSMeasures
};

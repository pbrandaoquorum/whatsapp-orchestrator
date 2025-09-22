/**
 * Lambda consolidado updateClinicalData
 * 
 * Combina funcionalidades dos lambdas:
 * - updateNoteAltInfo (NoteReport)
 * - updateSymptomReport (SymptomReport + tabela SymptomReports)
 * - updateVitalSignsTable (sinais vitais + alertas + SymptomReport)
 * 
 * Cenários suportados (clinicalNote é OPCIONAL):
 * 1. VITAL_SIGNS_NOTE_SYMPTOMS: Sinais Vitais + clinicalNote + SymptomReport + reportID/reportDate
 * 2. VITAL_SIGNS_SYMPTOMS: Sinais Vitais + SymptomReport + reportID/reportDate (SEM clinicalNote)
 * 3. VITAL_SIGNS_NOTE: Sinais Vitais + clinicalNote + reportID/reportDate
 * 4. VITAL_SIGNS_ONLY: Sinais Vitais + reportID/reportDate (SEM clinicalNote e sintomas)
 * 5. NOTE_SYMPTOMS: clinicalNote + SymptomReport + reportID/reportDate
 * 6. SYMPTOMS_ONLY: SymptomReport + reportID/reportDate (SEM clinicalNote)
 * 7. NOTE_ONLY: clinicalNote + reportID/reportDate
 * 
 * Mudanças recentes (v2.0):
 * - clinicalNote tornou-se opcional (não gera erro se ausente/vazio)
 * - caregiverID e patientID são recuperados automaticamente das tabelas Reports/WorkSchedules
 * - Validações para índices DynamoDB (caregiverID-index, patientID-index)
 * - Logs detalhados para debugging de campos obrigatórios
 */

const { 
  parseEventBody, 
  validateRequiredFields, 
  createResponse, 
  getCurrentTimestampBR 
} = require('/opt/nodejs/utils');

const { 
  getFamilyDataByPhone 
} = require('/opt/nodejs/dynamoHelpers');

// Handlers
const { processNoteReport } = require('./handlers/noteHandler');
const { processSymptomReportData } = require('./handlers/symptomHandler');
const { processVitalSignsCompleteWithTables } = require('./handlers/vitalSignsHandler');

// Utils
const { identifyScenario } = require('./utils/scenarioIdentifier');

/**
 * Handler principal
 */
exports.handler = async (event) => {
  console.log('🔔 Received event:', JSON.stringify(event, null, 2));

  try {
    // Parse do body
    const body = parseEventBody(event);
    console.log('✅ Parsed body:', JSON.stringify(body, null, 2));

    // Identifica o cenário
    const scenario = identifyScenario(body);
    console.log(`🎯 Cenário identificado: ${scenario}`);

    // Validações básicas baseadas no cenário
    let familyData = null;
    
    if (body.phoneNumber) {
      // Fluxo da família
      try {
        familyData = await getFamilyDataByPhone(body.phoneNumber);
        console.log(`✅ Dados da família encontrados:`, familyData);
      } catch (err) {
        return createResponse(404, null, `Não foi possível encontrar dados da família: ${err.message}`);
      }
    } else {
      // Fluxo normal - valida campos obrigatórios
      if (scenario === 'UNKNOWN') {
        return createResponse(400, null, 'Cenário não reconhecido. Verifique os campos enviados.');
      }
      
      validateRequiredFields(body, ['reportID', 'reportDate']);
    }

    const results = {};

    // Processa baseado no cenário
    switch (scenario) {
      case 'VITAL_SIGNS_NOTE_SYMPTOMS':
        console.log('📊 Processando: Sinais Vitais + NoteReport + SymptomReport');
        
        // 1. Processa sinais vitais
        const vitalSignsResult = await processVitalSignsCompleteWithTables(body);
        results.vitalSigns = vitalSignsResult;
        
        // 2. Processa SymptomReport (sem criar alertas - será feito pelos sinais vitais)
        const symptomResult = await processSymptomReportData(body, familyData, body.regras, false);
        results.symptomReport = symptomResult;
        
        // 3. Processa NoteReport
        const noteResult = await processNoteReport(body, familyData);
        results.noteReport = noteResult;
        
        break;

      case 'VITAL_SIGNS_SYMPTOMS':
        console.log('📊 Processando: Sinais Vitais + SymptomReport (sem NoteReport)');
        
        // 1. Processa sinais vitais
        const vsSymptomResult = await processVitalSignsCompleteWithTables(body);
        results.vitalSigns = vsSymptomResult;
        
        // 2. Processa SymptomReport (sem criar alertas - será feito pelos sinais vitais)
        const symptomOnlyResult = await processSymptomReportData(body, familyData, body.regras, false);
        results.symptomReport = symptomOnlyResult;
        
        break;

      case 'VITAL_SIGNS_NOTE':
        console.log('📊 Processando: Sinais Vitais + NoteReport');
        
        // 1. Processa sinais vitais
        const vsResult = await processVitalSignsCompleteWithTables(body);
        results.vitalSigns = vsResult;
        
        // 2. Processa NoteReport
        const nResult = await processNoteReport(body, familyData);
        results.noteReport = nResult;
        
        break;

      case 'VITAL_SIGNS_ONLY':
        console.log('📊 Processando: Sinais Vitais apenas');
        
        // Processa apenas sinais vitais
        const vsOnlyResult = await processVitalSignsCompleteWithTables(body);
        results.vitalSigns = vsOnlyResult;
        
        break;

      case 'NOTE_SYMPTOMS':
        console.log('📊 Processando: NoteReport + SymptomReport');
        
        // 1. Processa SymptomReport
        const sResult = await processSymptomReportData(body, familyData, body.regras);
        results.symptomReport = sResult;
        
        // 2. Processa NoteReport
        const n2Result = await processNoteReport(body, familyData);
        results.noteReport = n2Result;
        
        break;

      case 'SYMPTOMS_ONLY':
        console.log('📊 Processando: SymptomReport apenas');
        
        // Processa apenas SymptomReport
        const symptomOnlyMainResult = await processSymptomReportData(body, familyData, body.regras);
        results.symptomReport = symptomOnlyMainResult;
        
        break;

      case 'NOTE_ONLY':
        console.log('📊 Processando: NoteReport apenas');
        
        // Processa apenas NoteReport
        const onlyNoteResult = await processNoteReport(body, familyData);
        results.noteReport = onlyNoteResult;
        
        break;

      default:
        return createResponse(400, null, `Cenário ${scenario} não implementado`);
    }

    // Monta resposta de sucesso
    let message = 'Dados clínicos processados com sucesso';
    const responseData = {
      scenario,
      results,
      timestamp: getCurrentTimestampBR()
    };

    // Detalha o que foi processado
    const processedParts = [];
    
    if (results.vitalSigns?.processed) {
      processedParts.push('Sinais Vitais');
    }
    
    if (results.symptomReport?.symptomsProcessed > 0) {
      processedParts.push(`${results.symptomReport.symptomsProcessed} sintomas`);
    }
    
    if (results.noteReport?.saved) {
      processedParts.push('Nota Clínica');
    } else if (results.noteReport?.reason) {
      console.log(`📝 NoteReport não processado: ${results.noteReport.reason}`);
    }

    if (processedParts.length > 0) {
      message += ` - Processados: ${processedParts.join(', ')}`;
    }

    if (results.symptomReport?.alertCreated) {
      message += ` - Alerta criado: ${results.symptomReport.alertReason}`;
    }

    return createResponse(200, {
      message,
      ...responseData
    });

  } catch (error) {
    console.error('❌ Erro no processamento:', error);
    return createResponse(500, null, `Falha no processamento: ${error.message}`);
  }
};

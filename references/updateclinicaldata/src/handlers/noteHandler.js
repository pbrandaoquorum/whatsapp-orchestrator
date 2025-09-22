/**
 * Handler para processamento de NoteReport
 */

const { 
  dynamoDB, 
  TABLES,
  incrementQtNotes 
} = require('/opt/nodejs/dynamoHelpers');

const { 
  generateUUID, 
  getCurrentTimestampBR 
} = require('/opt/nodejs/utils');

const { 
  DynamoDBClient, 
  UpdateItemCommand, 
  PutItemCommand, 
  GetItemCommand 
} = require('@aws-sdk/client-dynamodb');

/**
 * Processa NoteReport e salva na tabela Reports ou FamilyReports
 * Se clinicalNote estiver vazio ou ausente, retorna sem processar
 */
async function processNoteReport(body, familyData = null) {
  const { reportID, reportDate, altnotepadMain, adminInfo, scheduleID, phoneNumber } = body;
  const noteDescAI = body.clinicalNote || body.noteDescAI;
  
  // Se não tem nota clínica e não tem outros campos opcionais, não processa
  if (!noteDescAI && !altnotepadMain && !adminInfo) {
    console.log('📝 Nenhum dado para NoteReport (clinicalNote vazio/ausente) - pulando processamento');
    return { saved: false, reason: 'No note data to process' };
  }
  
  const now = new Date();
  const local = new Date(now.getTime() - 3 * 60 * 60 * 1000);
  const timestamp = local.toISOString();
  const timestampBR = getCurrentTimestampBR();

  // Fluxo da família
  if (phoneNumber && familyData) {
    if (!noteDescAI) {
      console.log('📝 Fluxo da família: clinicalNote vazio - pulando processamento');
      return { saved: false, reason: 'No clinical note for family flow' };
    }
    
    const familyReportID = generateUUID();
    
    const noteReportData = [{
      M: {
        noteDesc: { S: noteDescAI },
        noteDescAI: { S: noteDescAI },
        timestamp: { S: timestamp }
      }
    }];

    const putCmd = new PutItemCommand({
      TableName: TABLES.FAMILY_REPORTS,
      Item: {
        familyReportID: { S: familyReportID },
        familyMemberID: { S: familyData.familyMemberID },
        familyID: { S: familyData.familyID },
        patientID: { S: familyData.patientID },
        NoteReport: { L: noteReportData },
        timestamp: { S: timestampBR }
      }
    });

    await dynamoDB.send(putCmd);
    console.log(`✅ NoteReport salvo na FamilyReports - familyReportID=${familyReportID}`);
    
    return { familyReportID, saved: true };
  }

  // Fluxo normal - Reports
  if (!reportID || !reportDate) {
    throw new Error('reportID e reportDate são obrigatórios para o fluxo normal');
  }

  const updateParts = [];
  const exprValues = {};

  // NoteReport
  if (noteDescAI) {
    exprValues[':empty_note_array'] = { L: [] };
    exprValues[':new_note'] = {
      L: [{
        M: {
          noteDesc: { S: noteDescAI },
          noteDescAI: { S: noteDescAI },
          timestamp: { S: timestamp },
        },
      }],
    };
    updateParts.push(
      'NoteReport = list_append(if_not_exists(NoteReport, :empty_note_array), :new_note)'
    );
  }

  // AlterationsReport
  if (altnotepadMain) {
    exprValues[':empty_alt_array'] = { L: [] };
    exprValues[':new_alt'] = {
      L: [{
        M: {
          altnotepadMain: { S: altnotepadMain },
          timestamp: { S: timestamp },
        },
      }],
    };
    updateParts.push(
      'AlterationsReport = list_append(if_not_exists(AlterationsReport, :empty_alt_array), :new_alt)'
    );
  }

  // AdminInfo (FETCH → MERGE → REPLACE)
  if (adminInfo) {
    console.log('🔍 Buscando AdminInfo existente para acumular...');
    const getParams = {
      TableName: TABLES.REPORTS,
      Key: {
        reportID: { S: reportID },
        reportDate: { S: reportDate },
      },
      ProjectionExpression: 'AdminInfo',
    };

    let existingAdminListAV = [];
    try {
      const getResp = await dynamoDB.send(new GetItemCommand(getParams));
      const attr = getResp.Item?.AdminInfo;
      if (attr) {
        if (Array.isArray(attr.L)) {
          existingAdminListAV = attr.L;
        } else if (attr.M) {
          existingAdminListAV = [{ M: attr.M }];
        }
      }
    } catch (err) {
      console.warn('⚠️ Não foi possível ler AdminInfo existente:', err);
    }

    const newAdminAV = {
      M: {
        adminInfo: { S: adminInfo },
        timestamp: { S: timestamp },
      },
    };
    exprValues[':full_admin_list'] = {
      L: [...existingAdminListAV, newAdminAV],
    };
    updateParts.push('AdminInfo = :full_admin_list');
  }

  if (updateParts.length === 0) {
    return { saved: false };
  }

  // Executa o UpdateItem na tabela Reports
  const params = {
    TableName: TABLES.REPORTS,
    Key: {
      reportID: { S: reportID },
      reportDate: { S: reportDate },
    },
    UpdateExpression: 'SET ' + updateParts.join(', '),
    ExpressionAttributeValues: exprValues,
  };

  await dynamoDB.send(new UpdateItemCommand(params));
  console.log(`✅ NoteReport atualizado na tabela Reports`);
  
  // Incrementa qtNotes se scheduleID fornecido
  if (scheduleID) {
    await incrementQtNotes(scheduleID);
  }
  
  return { saved: true };
}

module.exports = {
  processNoteReport
};

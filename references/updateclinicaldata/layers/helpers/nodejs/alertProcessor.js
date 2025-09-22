/**
 * Processador de alertas - criação e envio
 */

const { generateUUID, getNowInSaoPaulo } = require('./utils');
const { dynamoDB, TABLES } = require('./dynamoHelpers');
const { PutItemCommand } = require('@aws-sdk/client-dynamodb');

/**
 * Cria um alerta na tabela Alerts e envia webhook
 */
async function createAlert(alertData) {
  const now = getNowInSaoPaulo();
  const day = now.toLocaleDateString('pt-BR', { 
    timeZone: 'America/Sao_Paulo',
    day: '2-digit',
    month: '2-digit', 
    year: 'numeric'
  }); // DD/MM/YYYY
  const time = now.toLocaleTimeString('pt-BR', { 
    timeZone: 'America/Sao_Paulo', 
    hour12: false 
  }); // HH:MM:SS

  const alertItem = {
    alertID: { S: generateUUID() },
    action: { S: "" },
    alerts: { L: alertData.alerts },
    caregiverID: { S: alertData.caregiverID },
    caregiverName: { S: alertData.caregiverName },
    comment: { S: "" },
    comments: { S: "" },
    company: { S: alertData.company },
    day: { S: day },
    patientID: { S: alertData.patientID },
    patientName: { S: alertData.patientName },
    solved: { BOOL: false },
    time: { S: time },
    vitalSignsID: { S: "" },
    source: { S: alertData.source || "note" }
  };

  try {
    // Salva o alerta na tabela
    await dynamoDB.send(
      new PutItemCommand({
        TableName: TABLES.ALERTS,
        Item: alertItem
      })
    );
    console.log(`✅ Alerta criado: ${alertItem.alertID.S}`);

    // Prepara dados para o webhook
    const webhookAlerts = alertData.alerts.map(alert => ({
      altNotepadMain: alert.M.altNotepadMain?.S || '',
      symptomDefinition: alert.M.symptomDefinition?.S || '',
      symptomCategory: alert.M.symptomCategory?.S || ''
    }));

    const webhookData = {
      company: alertData.caregiverCompany || '',
      cooperative: alertData.caregiverCooperative || '',
      patientName: alertData.patientName,
      caregiverName: alertData.caregiverName,
      alertDay: day,
      alertTime: time,
      alerts: webhookAlerts
    };

    // Envia webhook
    try {
      const webhookSent = await sendWebhookAlert(webhookData);
      if (webhookSent) {
        console.log('✅ Webhook de alerta enviado com sucesso');
      } else {
        console.log('❌ Falha no envio do webhook (não interrompe execução)');
      }
    } catch (webhookError) {
      console.error('❌ Erro ao enviar webhook de alerta (não interrompe execução):', webhookError);
    }

    return true;
  } catch (err) {
    console.error(`❌ Erro ao criar alerta:`, err);
    return false;
  }
}

/**
 * Envia alerta via webhook
 */
async function sendWebhookAlert(alertData) {
  const webhookUrl = "https://primary-production-031c.up.railway.app/webhook/5b85966c-3fc6-4531-b2b2-f0d70ab4c9cd";
  
  try {
    const response = await fetch(webhookUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(alertData)
    });

    if (response.ok) {
      console.log(`✅ Webhook enviado com sucesso para ${alertData.patientName}`);
      return true;
    } else {
      console.error(`❌ Erro no webhook: ${response.status} - ${response.statusText}`);
      return false;
    }
  } catch (err) {
    console.error(`❌ Erro ao enviar webhook:`, err);
    return false;
  }
}

module.exports = {
  createAlert,
  sendWebhookAlert
};

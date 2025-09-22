/**
 * Utilitários para formatação de sintomas
 */

const { getCurrentTimestampBR } = require('/opt/nodejs/utils');

/**
 * Formata um sintoma para DynamoDB incluindo score e alert
 */
function formatSymptomForDynamoDB(item, symptomsWithScores = [], symptomsToAlert = [], timestamp = null) {
  const symptomDefinition = item.symptomDefinition || "";
  
  // Se o item já tem score e alert definidos (sintomas de sinais vitais), usa esses valores
  if (typeof item.score === 'number' && typeof item.alert === 'boolean') {
    return {
      M: {
        altNotepadMain: { S: item.altNotepadMain || "" },
        symptomCategory: { S: item.symptomCategory || "" },
        symptomSubCategory: { S: item.symptomSubCategory || "" },
        symptomDefinition: { S: symptomDefinition },
        score: { N: item.score.toString() },
        alert: { BOOL: item.alert },
        timestamp: { S: item.timestamp || timestamp || getCurrentTimestampBR() },
      },
    };
  }
  
  // Busca score do sintoma (lógica original)
  const scoreInfo = symptomsWithScores.find(s => s.symptom === symptomDefinition);
  const score = scoreInfo ? scoreInfo.score : 0;
  
  // Verifica se sintoma gerou alerta (lógica original)
  const generatedAlert = symptomsToAlert.some(s => s.symptomDefinition === symptomDefinition);
  
  return {
    M: {
      altNotepadMain: { S: item.altNotepadMain || "" },
      symptomCategory: { S: item.symptomCategory || "" },
      symptomSubCategory: { S: item.symptomSubCategory || "" },
      symptomDefinition: { S: symptomDefinition },
      score: { N: score.toString() },
      alert: { BOOL: generatedAlert },
      timestamp: { S: timestamp || getCurrentTimestampBR() },
    },
  };
}

module.exports = {
  formatSymptomForDynamoDB
};

/**
 * Utilitário para identificação de cenários
 */

/**
 * Identifica o cenário baseado nos campos presentes no body
 * clinicalNote agora é opcional - cenários são determinados pelos outros campos
 */
function identifyScenario(body) {
  const hasVitalSigns = body.vitalSignsData || (
    body.heartRate !== undefined || 
    body.respRate !== undefined || 
    body.saturationO2 !== undefined || 
    body.bloodPressure !== undefined || 
    body.temperature !== undefined
  );
  const hasNoteDescAI = body.clinicalNote !== undefined && body.clinicalNote !== '';
  const hasSymptomReport = body.SymptomReport && Array.isArray(body.SymptomReport);
  const hasReportInfo = body.reportID && body.reportDate;

  // Prioriza cenários com dados mais específicos
  if (hasVitalSigns && hasNoteDescAI && hasSymptomReport && hasReportInfo) {
    return 'VITAL_SIGNS_NOTE_SYMPTOMS';
  } else if (hasVitalSigns && hasSymptomReport && hasReportInfo) {
    return 'VITAL_SIGNS_SYMPTOMS'; // Novo cenário sem note
  } else if (hasVitalSigns && hasNoteDescAI && hasReportInfo) {
    return 'VITAL_SIGNS_NOTE';
  } else if (hasVitalSigns && hasReportInfo) {
    return 'VITAL_SIGNS_ONLY'; // Novo cenário só sinais vitais
  } else if (hasNoteDescAI && hasSymptomReport && hasReportInfo) {
    return 'NOTE_SYMPTOMS';
  } else if (hasSymptomReport && hasReportInfo) {
    return 'SYMPTOMS_ONLY'; // Novo cenário só sintomas
  } else if (hasNoteDescAI && hasReportInfo) {
    return 'NOTE_ONLY';
  } else {
    return 'UNKNOWN';
  }
}

module.exports = {
  identifyScenario
};

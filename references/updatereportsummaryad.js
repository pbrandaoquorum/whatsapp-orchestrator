import {
    DynamoDBClient,
    UpdateItemCommand,
    GetItemCommand,
    QueryCommand,
  } from "@aws-sdk/client-dynamodb";
  
  // Força timezone BR
  process.env.TZ = 'America/Sao_Paulo';
  
  /** Nome da tabela de Reports */
  const REPORTS_TABLE = "Reports";
  const CAREGIVERS_TABLE = "Caregivers";
  const WORK_SCHEDULES_TABLE = "WorkSchedules";
  
  /** Inicializa o client do DynamoDB */
  const dynamoDB = new DynamoDBClient({ region: "sa-east-1" });
  
  /**
   * Mapeia a cooperative para o seu respectivo phoneId.
   */
  function getPhoneIdByCooperative(cooperative) {
    switch (cooperative) {
      case "LSMULTIPROF": return "541200072414395";
      case "LSMEDICARE": return "492730200600407";
      case "LSSINERGIA": return "543829242150005";
      case "LSVGRSAUDE": return "564927043365423";
      case "LSHOPE": return "548116938385407";
      case "LSSALUS": return "542303792304090";
      case "LSVALORIZA": return "523703820835086";
      case "LSGAPCARE": return "563010530228990";
      case "LSCUIDADOTOTAL": return "586476601211256";
      case "LSGRUPOSG": return "602191772967357";
      case "LSINFINITY": return "580096998515702";
      case "LSMAISSAUDE": return "496549703551191";
      case "LSATESA": return "548248348373511";
      case "LSHOMEMED": return "610088775521400";
      case "ISALAB": return "594719373725109";
      case "DEMO": return "485960291270106";
      case "HOMEMATER": return "646955208504038";
      case "PCMAISHUMANUS": return "679470751911218";
      case "PCVITALIZACARE": return "679470751911218";
      case "PCCUIDADOSDOURADOS": return "679470751911218";
      case "PCENFQUALY": return "679470751911218";
      case "PCLIFEVIDA": return "679470751911218";
      case "PCMAISSAUDE": return "679470751911218";
      case "LS": return "359329063927112";
      default: return "646955208504038"; // Default para HOMEMATER
    }
  }
  
  /**
   * Mapeia cooperativas para grupos de números de WhatsApp
   */
  function getPhoneNumbersByCooperative(cooperative) {
    const phoneGroups = {
      "LS": ["5511991261390", "5511999383569", "5511983975177"],
      "LSMULTIPROF": ["5511991261390", "5511999383569", "5511983975177"],
      "LSMEDICARE": ["5511991261390", "5511999383569", "5511983975177"],
      "LSSINERGIA": ["5511991261390", "5511999383569", "5511983975177"],
      "LSVGRSAUDE": ["5511991261390", "5511999383569", "5511983975177"],
      "LSHOPE": ["5511991261390", "5511999383569", "5511983975177"],
      "LSSALUS": ["5511991261390", "5511999383569", "5511983975177"],
      "LSVALORIZA": ["5511991261390", "5511999383569", "5511983975177"],
      "LSGAPCARE": ["5511991261390", "5511999383569", "5511983975177"],
      "LSCUIDADOTOTAL": ["5511991261390", "5511999383569", "5511983975177"],
      "LSGRUPOSG": ["5511991261390", "5511999383569", "5511983975177"],
      "LSINFINITY": ["5511991261390", "5511999383569", "5511983975177"],
      "LSMAISSAUDE": ["5511991261390", "5511999383569", "5511983975177"],
      "LSHOMEMED": ["5511991261390", "5511999383569", "5511983975177"],
      "LSATESA": ["5511991261390", "5511999383569", "5511983975177"],
      "ISALAB": ["5511991261390", "5511999383569", "5511983975177", "5511982361286"],
    };
  
    // Retorna o grupo de números da cooperativa ou um grupo padrão
    const numbers = phoneGroups[cooperative];
    
    if (!numbers) {
      return ["5511991261390", "5511999383569", "5511983975177"]; // Números padrão
    }
    
    return numbers;
  }
  
  /**
   * Busca dados do schedule atual pela scheduleID
   */
  async function getCurrentSchedule(scheduleID) {
    try {
      const response = await dynamoDB.send(
        new GetItemCommand({
          TableName: WORK_SCHEDULES_TABLE,
          Key: { scheduleID: { S: scheduleID } },
          ProjectionExpression: "patientID, caregiverID, #day, #start",
          ExpressionAttributeNames: {
            "#day": "day",
            "#start": "start"
          }
        })
      );
      return response.Item;
    } catch (err) {
      console.error("Erro ao buscar schedule atual:", err);
      return null;
    }
  }
  
  /**
   * Converte string de data DD/MM/YYYY para objeto Date
   */
  function parseDate(dateStr) {
    if (!dateStr) return null;
    const [day, month, year] = dateStr.split('/');
    return new Date(parseInt(year), parseInt(month) - 1, parseInt(day));
  }
  
  /**
   * Converte string de horário HH:MM para minutos desde meia-noite
   */
  function parseTime(timeStr) {
    if (!timeStr) return 0;
    const [hours, minutes] = timeStr.split(':');
    return parseInt(hours) * 60 + parseInt(minutes);
  }
  
  /**
   * Busca o próximo schedule do mesmo paciente que seja posterior ao atual
   */
  async function getNextScheduleForPatient(patientID, currentDay, currentStart, currentCaregiverID) {
    try {
      // Buscar todos os schedules do paciente usando GSI patientID-index
      const response = await dynamoDB.send(
        new QueryCommand({
          TableName: WORK_SCHEDULES_TABLE,
          IndexName: "patientID-index",
          KeyConditionExpression: "patientID = :patientID",
          ExpressionAttributeValues: {
            ":patientID": { S: patientID }
          },
          ProjectionExpression: "scheduleID, caregiverID, #day, #start",
          ExpressionAttributeNames: {
            "#day": "day",
            "#start": "start"
          }
        })
      );
  
      const schedules = response.Items || [];
      console.log(`Encontrados ${schedules.length} schedules para paciente ${patientID}`);
  
      // Converter data atual para comparação
      const currentDateObj = parseDate(currentDay);
      const currentTimeMinutes = parseTime(currentStart);
  
      // Filtrar schedules posteriores ao atual
      const futureSchedules = schedules.filter(schedule => {
        const scheduleDay = schedule.day?.S;
        const scheduleStart = schedule.start?.S;
        const scheduleCaregiverID = schedule.caregiverID?.S;
  
        if (!scheduleDay || !scheduleStart) return false;
  
        // Ignorar se for o mesmo caregiver
        if (scheduleCaregiverID === currentCaregiverID) return false;
  
        // Converter data e horário do schedule para comparação
        const scheduleDateObj = parseDate(scheduleDay);
        const scheduleTimeMinutes = parseTime(scheduleStart);
  
        if (!currentDateObj || !scheduleDateObj) return false;
  
        // Comparar data e horário corretamente
        if (scheduleDateObj > currentDateObj) return true;
        if (scheduleDateObj.getTime() === currentDateObj.getTime() && scheduleTimeMinutes > currentTimeMinutes) return true;
        
        return false;
      });
  
      console.log(`Filtrados ${futureSchedules.length} schedules futuros com caregivers diferentes`);
  
      if (futureSchedules.length === 0) return null;
  
      // Ordenar por data e horário para pegar o mais próximo (comparação temporal correta)
      futureSchedules.sort((a, b) => {
        const dayA = a.day?.S;
        const dayB = b.day?.S;
        const startA = a.start?.S;
        const startB = b.start?.S;
  
        const dateA = parseDate(dayA);
        const dateB = parseDate(dayB);
        const timeA = parseTime(startA);
        const timeB = parseTime(startB);
  
        // Primeiro compara as datas
        if (dateA.getTime() !== dateB.getTime()) {
          return dateA.getTime() - dateB.getTime();
        }
        
        // Se as datas são iguais, compara os horários
        return timeA - timeB;
      });
  
      const nextSchedule = futureSchedules[0];
      console.log(`Próximo schedule temporal: day=${nextSchedule.day?.S}, start=${nextSchedule.start?.S}`);
  
      return nextSchedule;
    } catch (err) {
      console.error("Erro ao buscar próximo schedule:", err);
      return null;
    }
  }
  
  /**
   * Envia template de WhatsApp
   */
  async function sendTemplate(phoneNumber, phoneId, components, template = "dailyreport") {
    const payload = {
      template,
      language: "pt_BR",
      components,
      to: phoneNumber.startsWith("+") ? phoneNumber : `+${phoneNumber}`,
      phoneId: phoneId,
    };
    
    console.log("Enviando payload:", JSON.stringify(payload));
    
    const resp = await fetch("https://cqlzucjr8g.execute-api.sa-east-1.amazonaws.com/Prod/webhook/send-template", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    
    if (!resp.ok) {
      throw new Error(`HTTP status ${resp.status}`);
    }
    
    return resp;
  }
  
  /**
   * Handler principal do Lambda.
   */
  export const handler = async (event) => {
    console.log("=== EVENTO COMPLETO RECEBIDO ===");
    console.log(JSON.stringify(event, null, 2));
  
    // Parse do body (pode vir dentro de event.body ou diretamente em event)
    const body = event.body
      ? JSON.parse(event.body)
      : typeof event === "object"
      ? event
      : {};
  
    console.log("=== BODY PARSEADO ===");
    console.log(JSON.stringify(body, null, 2));
  
    console.log("=== PARA COPIAR NO POSTMAN ===");
    console.log("Raw Body (se vier de API Gateway):");
    console.log(event.body || "N/A");
    console.log("Objeto direto (se vier de invocação direta):");
    console.log(JSON.stringify(body, null, 2));
  
    const {
      reportID,
      reportDate,
      scheduleID,
      patientFirstName,
      shiftDay,
      shiftStart,
      shiftEnd,
      caregiverFirstName,
      caregiverID,
      foodHydrationSpecification,
      stoolUrineSpecification,
      sleepSpecification,
      moodSpecification,
      medicationsSpecification,
      activitiesSpecification,
      additionalInformationSpecification,
      administrativeInfo,
      reportSummarySpecification,
    } = body;
  
    // Validação básica: precisa de reportID e reportDate para atualizar Reports
    if (!reportID || !reportDate) {
      return {
        statusCode: 400,
        body: JSON.stringify({
          error: "reportID e reportDate são obrigatórios",
        }),
      };
    }
  
    // 1) Atualiza Reports.reportSummarySpecification (mesma lógica usada anteriormente)
    let summarySpec = reportSummarySpecification;
    if (!summarySpec) {
      summarySpec = {};
      if (foodHydrationSpecification !== undefined) {
        summarySpec.foodHydrationSpecification = foodHydrationSpecification;
      }
      if (stoolUrineSpecification !== undefined) {
        summarySpec.stoolUrineSpecification = stoolUrineSpecification;
      }
      if (sleepSpecification !== undefined) {
        summarySpec.sleepSpecification = sleepSpecification;
      }
      if (moodSpecification !== undefined) {
        summarySpec.moodSpecification = moodSpecification;
      }
      if (additionalInformationSpecification !== undefined) {
        summarySpec.additionalInformationSpecification =
          additionalInformationSpecification;
      }
      if (administrativeInfo !== undefined) {
        summarySpec.administrativeInfo = administrativeInfo;
      }
      if (medicationsSpecification !== undefined) {
        summarySpec.medicationsSpecification = medicationsSpecification;
      }
      if (activitiesSpecification !== undefined) {
        summarySpec.activitiesSpecification = activitiesSpecification;
      }
    }
  
    // Formata para DynamoDB Map<String,S>
    const formattedSummarySpec = Object.keys(summarySpec).reduce((acc, key) => {
      acc[key] = { S: summarySpec[key] };
      return acc;
    }, {});
  
    try {
      // Update em Reports
      await dynamoDB.send(
        new UpdateItemCommand({
          TableName: REPORTS_TABLE,
          Key: {
            reportID: { S: reportID },
            reportDate: { S: reportDate },
          },
          UpdateExpression: "SET reportSummarySpecification = :spec",
          ExpressionAttributeValues: {
            ":spec": { M: formattedSummarySpec },
          },
        })
      );
      console.log(
        `Reports atualizado (reportID=${reportID}, reportDate=${reportDate})`
      );
  
      // Após atualizar Reports, atualiza finishReport e shiftAllow na tabela WorkSchedules se scheduleID for fornecido
      if (scheduleID) {
        try {
          await dynamoDB.send(
            new UpdateItemCommand({
              TableName: WORK_SCHEDULES_TABLE,
              Key: { scheduleID: { S: scheduleID } },
              UpdateExpression: "SET finishReport = :true, shiftAllow = :false",
              ConditionExpression: "attribute_not_exists(finishReport) OR finishReport = :false",
              ExpressionAttributeValues: {
                ":true": { BOOL: true },
                ":false": { BOOL: false }
              },
            })
          );
          console.log(`WorkSchedules.finishReport atualizado para true e shiftAllow para false (scheduleID=${scheduleID})`);
        } catch (scheduleErr) {
          if (scheduleErr.name === "ConditionalCheckFailedException") {
            console.log(`finishReport já estava como true para scheduleID=${scheduleID}`);
          } else {
            console.error(`Erro ao atualizar finishReport e shiftAllow para scheduleID=${scheduleID}:`, scheduleErr.message);
            // Não retorna erro aqui para não quebrar o fluxo principal
          }
        }
      } else {
        console.log("⚠️  scheduleID não fornecido, não foi possível atualizar WorkSchedules");
      }
  
    } catch (err) {
      console.error("Erro ao atualizar Reports:", err);
      return {
        statusCode: 500,
        body: JSON.stringify({
          error: "Falha ao atualizar reportSummarySpecification",
          details: err.message,
        }),
      };
    }
  
    // 2.5) Busca dados do schedule atual para encontrar próximo caregiver
    let currentSchedule = null;
    let currentPatientID = null;
    let currentDay = null;
    let currentStart = null;
    
    if (scheduleID) {
      console.log("=== BUSCANDO DADOS DO SCHEDULE ATUAL ===");
      currentSchedule = await getCurrentSchedule(scheduleID);
      if (currentSchedule) {
        currentPatientID = currentSchedule.patientID?.S;
        currentDay = currentSchedule.day?.S;
        currentStart = currentSchedule.start?.S;
        console.log("Schedule atual:", {
          patientID: currentPatientID,
          caregiverID: currentSchedule.caregiverID?.S,
          day: currentDay,
          start: currentStart
        });
      }
    }
  
    // 2.6) Busca o telefone do caregiver atual se caregiverID estiver disponível
    let caregiverPhone = null;
    let cooperative = null;
    
    if (caregiverID) {
      try {
        const caregiverResponse = await dynamoDB.send(
          new GetItemCommand({
            TableName: CAREGIVERS_TABLE,
            Key: { caregiverID: { S: caregiverID } },
            ProjectionExpression: "phoneNumber, cooperative",
          })
        );
        
        if (caregiverResponse.Item?.phoneNumber?.S) {
          caregiverPhone = caregiverResponse.Item.phoneNumber.S;
          console.log(`📱 Telefone do caregiver atual encontrado: ${caregiverPhone}`);
        } else {
          console.log(`⚠️  Caregiver encontrado mas sem phoneNumber (caregiverID: ${caregiverID})`);
        }
        
        if (caregiverResponse.Item?.cooperative?.S) {
          cooperative = caregiverResponse.Item.cooperative.S;
          console.log(`🏢 Cooperativa encontrada: ${cooperative}`);
        } else {
          console.log(`⚠️  Cooperative não encontrada para caregiverID: ${caregiverID}`);
        }
        
      } catch (err) {
        console.error("❌ Erro ao buscar dados do caregiver atual:", err);
      }
    } else {
      console.log("⚠️  caregiverID não fornecido");
    }
  
    const isDemo = cooperative === "DEMO";
  
    // 2.7) Busca próximo caregiver
    console.log("=== BUSCANDO PRÓXIMO CAREGIVER ===");
    let nextCaregiverData = null;
    
    if (currentPatientID && currentDay && currentStart && caregiverID) {
      const nextSchedule = await getNextScheduleForPatient(currentPatientID, currentDay, currentStart, caregiverID);
      
      if (nextSchedule) {
        const nextCaregiverID = nextSchedule.caregiverID?.S;
        console.log("Próximo schedule encontrado:", {
          scheduleID: nextSchedule.scheduleID?.S,
          caregiverID: nextCaregiverID,
          day: nextSchedule.day?.S,
          start: nextSchedule.start?.S
        });
  
        // Buscar dados do próximo caregiver
        if (nextCaregiverID) {
          try {
            const nextCgRes = await dynamoDB.send(
              new GetItemCommand({
                TableName: CAREGIVERS_TABLE,
                Key: { caregiverID: { S: nextCaregiverID } },
                ProjectionExpression: "firstName, phoneNumber, cooperative",
              })
            );
            nextCaregiverData = {
              firstName: nextCgRes.Item?.firstName?.S || "",
              phoneNumber: nextCgRes.Item?.phoneNumber?.S || "",
              cooperative: nextCgRes.Item?.cooperative?.S || ""
            };
            console.log("📱 Próximo caregiver encontrado:", nextCaregiverData);
          } catch (err) {
            console.error("❌ Erro ao buscar dados do próximo caregiver:", err);
          }
        }
      } else {
        console.log("ℹ️  Nenhum próximo schedule encontrado");
      }
    } else {
      console.log("⚠️  Dados insuficientes para buscar próximo caregiver");
    }
  
    // 3) Monta lista de números baseada na cooperative
    const phoneNumbers = getPhoneNumbersByCooperative(cooperative);
    
    console.log(`📋 Números configurados para cooperative ${cooperative}: ${phoneNumbers.join(', ')}`);
  
    // Adiciona o telefone do caregiver atual se encontrado
    if (caregiverPhone) {
      // Remove caracteres especiais e garante que não seja duplicado
      const cleanCaregiverPhone = caregiverPhone.replace(/\D/g, '');
      if (!phoneNumbers.some(num => num.replace(/\D/g, '') === cleanCaregiverPhone)) {
        phoneNumbers.push(cleanCaregiverPhone);
        console.log(`✅ Telefone do caregiver atual adicionado à lista: ${cleanCaregiverPhone}`);
      } else {
        console.log("ℹ️  Telefone do caregiver atual já está na lista de números fixos");
      }
    }
  
    // Adiciona o telefone do próximo caregiver se encontrado
    if (nextCaregiverData?.phoneNumber) {
      const cleanNextCaregiverPhone = nextCaregiverData.phoneNumber.replace(/\D/g, '');
      if (!phoneNumbers.some(num => num.replace(/\D/g, '') === cleanNextCaregiverPhone)) {
        phoneNumbers.push(cleanNextCaregiverPhone);
        console.log(`✅ Telefone do próximo caregiver adicionado à lista: ${cleanNextCaregiverPhone}`);
      } else {
        console.log("ℹ️  Telefone do próximo caregiver já está na lista de números");
      }
    }
  
    console.log(`📱 Lista final de números para envio: ${phoneNumbers.join(', ')}`);
    console.log(`📊 Total de números: ${phoneNumbers.length}`);
    
    // Determina o phoneId baseado na cooperative
    const phoneId = getPhoneIdByCooperative(cooperative);
    console.log(`📞 PhoneId para cooperative ${cooperative}: ${phoneId}`);
  
    const components = isDemo
    ? [
        {
          type: "body",
          parameters: [
            // apenas 1 variável (firstName) no DEMO
            { type: "text", text: caregiverFirstName || "" },
          ],
        },
      ]
    : [
        {
          type: "body",
          parameters: [
            { type: "text", text: patientFirstName || "" },      // 1
            { type: "text", text: shiftDay || "" },               // 2
            { type: "text", text: shiftStart || "" },             // 3
            { type: "text", text: shiftEnd || "" },               // 4
            { type: "text", text: caregiverFirstName || "" },     // 5
            { type: "text", text: foodHydrationSpecification || "" },      // 6
            { type: "text", text: stoolUrineSpecification || "" },         // 7
            { type: "text", text: sleepSpecification || "" },              // 8
            { type: "text", text: moodSpecification || "" },               // 9
            { type: "text", text: medicationsSpecification || "" },        // 10
            { type: "text", text: activitiesSpecification || "" },         // 11
            { type: "text", text: additionalInformationSpecification || "" }, // 12
            { type: "text", text: administrativeInfo || "" },              // 13
          ],
        },
      ];
  
    const templateName = isDemo ? "resumo_do_plantao" : "dailyreport";
  
  
  
    // 4) Envia o template "dailyreport" para todos os números (fixos + caregivers atual e próximo)
    for (const rawPhone of phoneNumbers) {
      try {
        console.log(`[${templateName}][ENVIANDO] para ${rawPhone}`);
        await sendTemplate(rawPhone, phoneId, components, templateName);
        console.log(`[${templateName}][ENVIADO] para ${rawPhone}`);
      } catch (err) {
        console.error(`[${templateName}][ERRO] ao enviar para ${rawPhone}:`, err);
      }
    }
    
  
    // Calcula quantos números extras foram adicionados
    const baseNumbers = getPhoneNumbersByCooperative(cooperative).length;
    const currentCaregiverAdded = caregiverPhone && !getPhoneNumbersByCooperative(cooperative).some(num => num.replace(/\D/g, '') === caregiverPhone.replace(/\D/g, ''));
    const nextCaregiverAdded = nextCaregiverData?.phoneNumber && !phoneNumbers.slice(0, baseNumbers + (currentCaregiverAdded ? 1 : 0)).some(num => num.replace(/\D/g, '') === nextCaregiverData.phoneNumber.replace(/\D/g, ''));
    
    return {
      statusCode: 200,
      body: JSON.stringify({
        message: `Report atualizado e dailyreport enviado para ${phoneNumbers.length} números (${baseNumbers} fixos${currentCaregiverAdded ? ' + caregiver atual' : ''}${nextCaregiverAdded ? ' + próximo caregiver' : ''}).`,
        phoneNumbers: phoneNumbers.length,
        currentCaregiverIncluded: currentCaregiverAdded,
        nextCaregiverIncluded: nextCaregiverAdded
      }),
    };
  };
  
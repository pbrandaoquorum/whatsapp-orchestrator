const {
    DynamoDBClient,
    UpdateItemCommand,
    GetItemCommand,
  } = require("@aws-sdk/client-dynamodb");
  const axios = require("axios");
  
  // Inicializa o cliente DynamoDB
  const dynamoDB = new DynamoDBClient({ region: "sa-east-1" });
  
  // Nome das tabelas
  const WORK_SCHEDULES_TABLE = "WorkSchedules";
  const CAREGIVERS_TABLE = "Caregivers";
  const PATIENTS_TABLE = "Patients";
  
  exports.handler = async (event) => {
    console.log("🔍 Received event:", JSON.stringify(event, null, 2));
  
    // 2) Parse do body (se existir) ou do próprio event
    const raw = event.body ? JSON.parse(event.body) : event;
  
    // 3) Captura dos parâmetros, aceitando ambos os nomes
    const scheduleIdentifier = raw.scheduleIdentifier ?? raw.scheduleID;
    const responseValue     = raw.responseValue     ?? raw.checkAttend;
  
    // 4) Validação
    if (!scheduleIdentifier || !responseValue) {
      console.error("❌ Parâmetros ausentes:", {
        scheduleIdentifier,
        responseValue,
      });
      return {
        statusCode: 400,
        body: JSON.stringify({
          error: "É obrigatório enviar scheduleIdentifier (ou scheduleID) e responseValue (ou checkAttend).",
        }),
      };
    }
  
    try {
      // 1) Recupera o schedule pelo scheduleIdentifier
      const schedule = await getScheduleItem(scheduleIdentifier);
      if (!schedule) {
        return {
          statusCode: 400,
          body: JSON.stringify({
            error: "Nenhum schedule encontrado para o scheduleIdentifier fornecido.",
          }),
        };
      }
  
      // 2) Atualiza o schedule com o novo response
      await updateWorkScheduleResponse(scheduleIdentifier, responseValue);
  
      // 3) Se responseValue for 'cancelado', envia e-mail e WhatsApp
      if (responseValue === "cancelado") {
        const caregiverID = schedule.caregiverID?.S;
        if (caregiverID) {
          await sendCancellationWebhook(caregiverID, schedule);
          await sendCancellationWhatsApp(caregiverID, schedule);
        } else {
          console.error("CaregiverID não encontrado no schedule.");
        }
      }
  
      return {
        statusCode: 200,
        body: JSON.stringify({ message: "Schedule updated successfully" }),
      };
    } catch (error) {
      console.error("Error:", error);
      return {
        statusCode: 500,
        body: JSON.stringify({
          error: "Failed to process request",
          details: error.message,
        }),
      };
    }
  };
  
  /**
   * Recupera o schedule pelo scheduleIdentifier.
   */
  async function getScheduleItem(scheduleIdentifier) {
    try {
      const command = new GetItemCommand({
        TableName: WORK_SCHEDULES_TABLE,
        Key: { scheduleID: { S: scheduleIdentifier } },
      });
      const result = await dynamoDB.send(command);
      return result.Item || null;
    } catch (err) {
      console.error(`Erro ao buscar scheduleIdentifier=${scheduleIdentifier}:`, err);
      return null;
    }
  }
  
  /**
   * Atualiza o schedule com o responseValue informado.
   */
  async function updateWorkScheduleResponse(scheduleID, responseValue) {
    if (!scheduleID) return;
  
    const updateParams = {
      TableName: WORK_SCHEDULES_TABLE,
      Key: { scheduleID: { S: scheduleID } },
      UpdateExpression: "SET #resp = :rv",
      ExpressionAttributeNames: {
        "#resp": "response",
      },
      ExpressionAttributeValues: {
        ":rv": { S: responseValue },
      },
    };
  
    await dynamoDB.send(new UpdateItemCommand(updateParams));
  }
  
  
  
    /**
   * Envia webhook de cancelamento via API
   */
  async function sendCancellationWebhook(caregiverID, schedule) {
    try {
      // Recupera caregiver para obter o fullName e cooperative
      const caregiverItem = await getCaregiverItem(caregiverID);
      const caregiverFullName = caregiverItem?.fullName?.S || "Profissional";
      const cooperative = caregiverItem?.cooperative?.S || "";
      
      console.log(`📧 Processando webhook para cooperativa: ${cooperative}`);
      console.log(`👤 Caregiver: ${caregiverFullName}`);
  
      // Recupera nome completo do paciente
      let patientFullName = "Paciente";
      const patientIdentifier = schedule.patientID?.S;
      if (patientIdentifier) {
        const patientItem = await getPatientItemFullName(patientIdentifier);
        if (patientItem?.fullName?.S) {
          patientFullName = patientItem.fullName.S;
        }
      }
  
      const day = schedule.day?.S || "Data não informada";
      const time = schedule.start?.S || "Horário não informado";
  
      // Prepara dados para o webhook com nomes completos
      const webhookData = {
        caregiverFirstName: caregiverFullName,  // Usando nome completo para webhook
        patientFirstName: patientFullName,      // Usando nome completo para webhook
        day: day,
        time: time,
        cooperative: cooperative,
        template: "plantaocancelado"
      };
  
      console.log(`📧 Enviando webhook para cooperativa: ${cooperative}`);
      console.log(`📋 Dados do webhook:`, webhookData);
  
      // Envia webhook
      try {
        const webhookSent = await sendWebhookEmail(webhookData);
        if (webhookSent) {
          console.log('✅ Webhook de cancelamento enviado com sucesso');
        } else {
          console.log('❌ Falha no envio do webhook (não interrompe execução)');
        }
      } catch (webhookError) {
        console.error('❌ Erro ao enviar webhook de cancelamento (não interrompe execução):', webhookError);
      }
    } catch (error) {
      console.error("❌ Erro geral na função sendCancellationWebhook:", error);
    }
  }
  
  /**
   * Envia webhook de email
   */
  async function sendWebhookEmail(emailData) {
    const webhookUrl = "https://primary-production-031c.up.railway.app/webhook/a1a46b24-5856-41c1-940c-6b888c5f71c3";
    
    try {
      const response = await fetch(webhookUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(emailData)
      });
  
      if (response.ok) {
        console.log(`✅ Webhook de email enviado com sucesso`);
        return true;
      } else {
        console.error(`❌ Erro no webhook de email: ${response.status} - ${response.statusText}`);
        return false;
      }
    } catch (err) {
      console.error(`❌ Erro ao enviar webhook de email:`, err);
      return false;
    }
  }
  
  /**
   * Mapeia cooperativas para grupos de números de WhatsApp
   * 
   * INSTRUÇÕES PARA ADICIONAR NOVOS GRUPOS:
   * 1. Adicione a cooperativa como chave no objeto phoneGroups
   * 2. Defina um array com os números de telefone (com código do país)
   * 3. Para desabilitar WhatsApp para uma cooperativa, use array vazio: []
   * 
   * FORMATO DOS NÚMEROS: "5511999999999" (código país + DDD + número)
   */
  function getPhoneNumbersByCooperative(cooperative) {
    const phoneGroups = {
      // ===========================================
      // GRUPO LARE SAÚDE (LS) - Cooperativas LS*
      // ===========================================
      "LSMULTIPROF": ["5511991261390", "5511999383569", "5581982402013", "5581971187389", "5541999780937", "5584998441203"],
      //"LSMEDICARE": ["5511991261390", "5511999383569"],
      //"LSSINERGIA": ["5511991261390", "5511999383569"],
      //"LSVGRSAUDE": ["5511991261390", "5511999383569"],
      //"LSHOPE": ["5511991261390", "5511999383569"],
      //"LSSALUS": ["5511991261390", "5511999383569"],
      //"LSVALORIZA": ["5511991261390", "5511999383569"],
      //"LSGAPCARE": ["5511991261390", "5511999383569"],
      //"LSGRUPOSG": ["5511991261390", "5511999383569"],
      //"LSINFINITY": ["5511991261390", "5511999383569"],
      //"LSMAISSAUDE": ["5511991261390", "5511999383569"],
      //"LSATESA": ["5511991261390", "5511999383569"],
      //"LSHOMEMED": ["5511991261390", "5511999383569"],
      //"LSCUIDADOTOTAL": ["5511991261390", "5511999383569"],
      "LS": ["5511991261390", "5511999383569", "5541985254724", "5541999780937", "5541997499898"],
  
      // ===========================================
      // GRUPO ISALAB
      // ===========================================
      //"ISALAB": ["5511991261390", "5511999383569"],
  
      // ===========================================
      // GRUPO HOMEMATER
      // ===========================================
      "HOMEMATER": ["5511991261390", "5511999383569", "5511989635667", "5511967050314"],
  
      // ===========================================
      // GRUPOS PLURALCARE (PC*)
      // ===========================================
      "PCMAISHUMANUS": ["5511991261390", "5511999383569", "5582996211011", "5582993666730"],
      "PCVITALIZACARE": ["5511991261390", "5511999383569", "5541984901799", "5541992053949"],
      "PCCUIDADOSDOURADOS": ["5511991261390", "5511999383569", "5511993088691"],
      "PCENFQUALY": ["5511991261390", "5511999383569", "5511975581143"],
      "PCLIFEVIDA": ["5511991261390", "5511999383569", "5531971025170", "5531998755276"],
      "PCMAISSAUDE": ["5511991261390", "5511999383569", "5582991786935", "5582981539104"],
      //"PLURALCARE": ["5511991261390", "5511999383569"],
  
      // ===========================================
      // GRUPO DEMO/TESTE
      // ===========================================
      "DEMO": ["5511991261390", "5511999383569"],
  
    };
  
    // Retorna o grupo de números da cooperativa ou um grupo padrão
    const numbers = phoneGroups[cooperative];
    
    if (!numbers) {
      console.log(`⚠️  Cooperativa '${cooperative}' não mapeada, usando grupo padrão`);
      return ["5511991261390"]; // Número padrão
    }
    
    return numbers;
  }
  
  /**
   * Envia WhatsApp de cancelamento via Make.
   */
  async function sendCancellationWhatsApp(caregiverID, schedule) {
    try {
      const caregiverItem = await getCaregiverItem(caregiverID);
      const caregiverFirstName = caregiverItem?.firstName?.S || "Profissional";
      const cooperative = caregiverItem?.cooperative?.S || "";
      const company = caregiverItem?.company?.S || "";
      
      console.log(`📱 Processando WhatsApp para cooperativa: ${cooperative}`);
      console.log(`👤 Caregiver: ${caregiverFirstName} | Company: ${company}`);
  
      // Obtém os números de telefone baseado na cooperativa
      const phoneNumbers = getPhoneNumbersByCooperative(cooperative);
      
      // Se não há números (como ISALAB), não envia WhatsApp
      if (phoneNumbers.length === 0) {
        console.log(`⏭️  Nenhum WhatsApp configurado para cooperativa: ${cooperative}`);
        return;
      }
  
      // Obtém dados do paciente
      let patientFirstName = "Paciente";
      const patientIdentifier = schedule.patientID?.S;
      if (patientIdentifier) {
        const patientItem = await getPatientItem(patientIdentifier);
        if (patientItem?.firstName?.S) {
          patientFirstName = patientItem.firstName.S;
        }
      }
  
      const day = schedule.day?.S || "Data não informada";
      const time = schedule.start?.S || "Horário não informado";
      const phoneId = getPhoneIdByCooperative(cooperative);
  
      console.log(`📱 Enviando WhatsApp para ${phoneNumbers.length} números da cooperativa ${cooperative}`);
      console.log(`📞 Números alvo: ${phoneNumbers.join(', ')}`);
  
      // Envia WhatsApp para cada número do grupo
      for (const phoneNumberRaw of phoneNumbers) {
        let cgPhone = phoneNumberRaw.startsWith("+") ? phoneNumberRaw : `+${phoneNumberRaw}`;
        
        const body = {
          template: "plantaocancelado",
          language: "pt_BR",
          components: [
            {
              type: "body",
              parameters: [
                { type: "text", text: patientFirstName },
                { type: "text", text: caregiverFirstName },
                { type: "text", text: day },
                { type: "text", text: time }
              ]
            }
          ],
          to: cgPhone,
          phoneId: phoneId,
        };
        
        try {
          await axios.post(
            "https://cqlzucjr8g.execute-api.sa-east-1.amazonaws.com/Prod/webhook/send-template",
            body,
            {
              headers: {
                "Content-Type": "application/json",
              },
            }
          );
          console.log(`✅ WhatsApp enviado para: ${cgPhone}`);
        } catch (whatsappError) {
          console.error(`❌ Erro ao enviar WhatsApp para ${cgPhone}:`, whatsappError.message);
        }
  
        // Aguarda 1 segundo entre os envios para evitar rate limiting
        await sleep(1000);
      }
  
      console.log(`✅ Processo de WhatsApp concluído para cooperativa: ${cooperative}`);
    } catch (error) {
      console.error("❌ Erro geral na função sendCancellationWhatsApp:", error);
    }
  }
  
  /**
   * Recupera o item do caregiver na tabela Caregivers.
   */
  async function getCaregiverItem(caregiverID) {
    try {
      const { Item } = await dynamoDB.send(
        new GetItemCommand({
          TableName: CAREGIVERS_TABLE,
          Key: { caregiverID: { S: caregiverID } },
        })
      );
      return Item || null;
    } catch (err) {
      console.error(`Erro ao buscar caregiverID=${caregiverID}:`, err);
      return null;
    }
  }
  
  /**
   * Recupera o item do paciente na tabela Patients (apenas firstName).
   */
  async function getPatientItem(patientID) {
    try {
      const { Item } = await dynamoDB.send(
        new GetItemCommand({
          TableName: PATIENTS_TABLE,
          Key: { patientID: { S: patientID } },
          ProjectionExpression: "firstName",
        })
      );
      return Item || null;
    } catch (err) {
      console.error(`Erro ao buscar patientID=${patientID}:`, err);
      return null;
    }
  }
  
  /**
   * Recupera o item do paciente na tabela Patients (nome completo).
   */
  async function getPatientItemFullName(patientID) {
    try {
      const { Item } = await dynamoDB.send(
        new GetItemCommand({
          TableName: PATIENTS_TABLE,
          Key: { patientID: { S: patientID } },
          ProjectionExpression: "fullName",
        })
      );
      return Item || null;
    } catch (err) {
      console.error(`Erro ao buscar patientID=${patientID} (fullName):`, err);
      return null;
    }
  }
  
  /**
   * Retorna o phoneId do Make de acordo com a cooperative.
   */
  function getPhoneIdByCooperative(cooperative) {
    switch (cooperative) {
      case "LSMULTIPROF":
        return "541200072414395";
      case "LSMEDICARE":
        return "492730200600407";
      case "LSSINERGIA":
        return "543829242150005";
      case "LSVGRSAUDE":
        return "564927043365423";
      case "LSHOPE":
        return "548116938385407";
      case "LSSALUS":
        return "542303792304090";
      case "LSVALORIZA":
        return "523703820835086";
      case "LSGAPCARE":
        return "563010530228990";
      case "LSCUIDADOTOTAL":
        return "586476601211256";
      case "LSGRUPOSG":
        return "602191772967357";
      case "LSINFINITY":
        return "580096998515702";
      case "LSMAISSAUDE":
        return "496549703551191";
      case "LSATESA":
        return "548248348373511";
      case "LSHOMEMED":
        return "610088775521400";
      case "ISALAB":
        return '594719373725109';
      case "DEMO": 
        return "485960291270106";
      case "HOMEMATER": 
        return "646955208504038";
      case "PCMAISHUMANUS": 
        return "679470751911218";
      case "PCVITALIZACARE": 
        return "679470751911218";
      case "PCCUIDADOSDOURADOS": 
        return "679470751911218";
      case "PCENFQUALY": 
        return "679470751911218";
      case "PCLIFEVIDA": 
        return "679470751911218";
      case "PCMAISSAUDE":
        return "679470751911218";
      case "PLURALCARE":
        return "679470751911218";
      case "LS":
        return "359329063927112";
    }
  }
  
  /**
   * Função para aguardar 'ms' milissegundos.
   */
  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
  
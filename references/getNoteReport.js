import { DynamoDBClient, GetItemCommand } from '@aws-sdk/client-dynamodb';

const dynamoDB = new DynamoDBClient({ region: 'sa-east-1' });

export const handler = async (event) => {
    console.log('Received event:', JSON.stringify(event, null, 2)); 

    let reportID, reportDate;
    if (event.body) {
        const body = JSON.parse(event.body);
        reportID = body.reportID;
        reportDate = body.reportDate;
    } else {
        reportID = event.reportID;
        reportDate = event.reportDate;
    }

    try {
        const data = await dynamoDB.send(new GetItemCommand({
            TableName: "Reports",
            Key: {
                reportID: { S: reportID },
                reportDate: { S: reportDate }
            }
        }));

        if (!data.Item) {
            throw new Error('No data found for the given reportID and reportDate');
        }

        const noteReport = data.Item.NoteReport ? data.Item.NoteReport.L.map(note => ({
            noteDescAI: note.M.noteDescAI.S,
            timestamp: note.M.timestamp.S
        })) : [];

        return {
            statusCode: 200,
            body: JSON.stringify({
                notes: noteReport
            })
        };
    } catch (error) {
        console.error('Error:', error);
        return {
            statusCode: 500,
            body: JSON.stringify({ error: 'Failed to process request', details: error.message })
        };
    }
};

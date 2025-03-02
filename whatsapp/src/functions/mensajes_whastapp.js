const { app } = require('@azure/functions');
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const fs = require('fs');
const pino = require('pino');
const Boom = require('@hapi/boom');
const path = require('path');

let sock;
let isConnected = false;

async function connectToWhatsApp() {
    const dirPath = path.join(__dirname, '..', '..', 'session_auth_info');
    console.log(`Conectando a WhatsApp usando el directorio: ${dirPath}`);

    if (!fs.existsSync(dirPath)) {
        console.log(`El directorio ${dirPath} no existe. Asegúrate de que las credenciales están correctamente configuradas.`);
        throw new Error('Directorio de autenticación no encontrado.');
    }

    const { state } = await useMultiFileAuthState(dirPath);
    
    sock = makeWASocket({
        auth: state,
        logger: pino({ level: 'silent' }),
        printQRInTerminal: true
    });

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            console.log('Nuevo QR generado. Escanéalo para conectar.');
        }

        if (connection === 'close') {
            const disconnectReason = lastDisconnect?.error;
            console.log(`Conexión cerrada. Razón: ${disconnectReason}`);
        } else if (connection === 'open') {
            console.log('Conexión establecida exitosamente.');
            isConnected = true;
        }
    });

    return new Promise((resolve, reject) => {
        sock.ev.on('connection.update', (update) => {
            const { connection, lastDisconnect } = update;
            if (connection === 'close') {
                reject('Conexión cerrada inesperadamente.');
            } else if (connection === 'open') {
                console.log('Conexión a WhatsApp establecida');
                isConnected = true;
                resolve(sock);
            }
        });
    });
}

function closeWhatsAppConnection() {
    if (sock?.ws) {
        sock.ws.close();
        console.log('Conexión de socket cerrada manualmente.');
    }
}

async function verifyNumber(id) {
    try {
        const exists = await sock.onWhatsApp(id);
        if (exists && exists.length > 0) {
            return exists[0]?.jid;
        } else {
            console.error(`El número ${id} no está registrado en WhatsApp.`);
            return null;
        }
    } catch (error) {
        console.error('Error al verificar el número en WhatsApp:', error);
        return null;
    }
}

async function sendMessage(id, messageText, pdfBuffer = null) {
    if (!isConnected) {
        console.error('El cliente no está conectado');
        return;
    }

    try {
        const jid = await verifyNumber(id);
        if (!jid) {
            return;
        }

        const messageOptions = pdfBuffer
            ? { document: pdfBuffer, fileName: 'consentimiento.pdf', mimetype: 'application/pdf', caption: messageText }
            : { text: messageText };

        const result = await sock.sendMessage(jid, messageOptions);

        if (result?.key?.id) {
            console.log(pdfBuffer ? 'PDF con mensaje enviado correctamente' : 'Mensaje de texto enviado correctamente');
        } else {
            console.error('Error: No se pudo confirmar el envío del mensaje.');
        }

        closeWhatsAppConnection();

    } catch (error) {
        console.error('Error al enviar el mensaje:', error);
    }
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}


app.http('mensajes-whatsapp', {
    methods: ['POST'],
    authLevel: 'anonymous',
    handler: async (request, context) => {
        context.log(`Http function processed request for url "${request.url}"`);

        try {
            const { numero, mensaje, pdfHex } = await request.json();

            if (!numero || !mensaje) {
                return { status: 400, body: 'Debe proporcionar el número y el mensaje.' };
            }

            const pdfBuffer = pdfHex ? Buffer.from(pdfHex, 'hex') : null;

            await connectToWhatsApp();
            
            await sleep(2000);

            await sendMessage(numero, mensaje, pdfBuffer);

            return { body: `Mensaje enviado a ${numero} con éxito.` };

        } catch (error) {
            context.log(`Error en enviar-mensaje-whatsapp: ${error}`);
            closeWhatsAppConnection();
            return { status: 500, body: 'Hubo un error al procesar la solicitud.' };
        } finally {
            closeWhatsAppConnection();
        }
    }
});

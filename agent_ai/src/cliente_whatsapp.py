#!/usr/bin/env python3
import socketio
import asyncio
from datetime import datetime
from inference.graphs.restaurant_graph import PDFChatAgent

class ClienteWhatsApp:
    def __init__(self, server_url="https://tars-whatsapp.blueriver-8537145c.westus2.azurecontainerapps.io"):
        self.sio = socketio.AsyncClient(
            reconnection=True,
            reconnection_attempts=5,
            reconnection_delay=1,
            reconnection_delay_max=5,
            logger=True,
            engineio_logger=True
        )
        self.server_url = server_url
        self.esta_conectado = False
        self.setup_eventos()

    def setup_eventos(self):
        @self.sio.event
        async def connect():
            print(f"[{self.get_timestamp()}] Conectado al servidor (ID: {self.sio.get_sid()})")
            self.esta_conectado = True

        @self.sio.event
        async def disconnect():
            print(f"[{self.get_timestamp()}] Desconectado del servidor")
            self.esta_conectado = False

        @self.sio.event
        async def connect_error(data):
            print(f"[{self.get_timestamp()}] Error de conexión: {data}")
            self.esta_conectado = False

        @self.sio.event
        async def keep_alive():
            print(f"[{self.get_timestamp()}] Keep-alive recibido")

        # Al recibir un mensaje entrante, se genera una respuesta y se envía
        @self.sio.on('new_message')
        async def on_new_message(data):
            # Extraer información del mensaje entrante
            try:
                timestamp = datetime.fromtimestamp(data.get('timestamp', 0) / 1000).strftime('%H:%M:%S')
            except Exception:
                timestamp = self.get_timestamp()
            sender = data.get('sender', 'desconocido')
            raw_number = data.get('from', '')
            number = raw_number.split('@')[0] if '@' in raw_number else raw_number
            incoming_message = data.get('message', '')

            print(f"\n{'='*50}")
            print(f"📱 [{timestamp}] Mensaje de {sender}")
            print(f"📞 Número: {number}")
            print(f"💬 Mensaje: {incoming_message}")
            print(f"{'='*50}")

            # Invocar al agente para generar la respuesta
            try:
                pdf_chat_agent = PDFChatAgent()
                new_state, message_id = await pdf_chat_agent.invoke_flow(
                    user_input=incoming_message,
                    pdf_text=None,
                    conversation_id=f"conversation_{number}",
                    conversation_name=f"Conversación con {number}",
                    user_id=number
                )
                final_msg = new_state["messages"][-1].content
                print(f"[{self.get_timestamp()}] Respuesta generada: {final_msg}")

                # Responder al mensaje recibido
                await self.enviar_mensaje(number, final_msg)
            except Exception as e:
                print(f"[{self.get_timestamp()}] Error al generar la respuesta: {str(e)}")

    def get_timestamp(self):
        return datetime.now().strftime('%H:%M:%S')

    async def conectar(self):
        if not self.esta_conectado:
            try:
                print(f"[{self.get_timestamp()}] Conectando a {self.server_url}...")
                await self.sio.connect(self.server_url, wait_timeout=10)
                await asyncio.sleep(1)  # Aseguramos que la conexión se establezca
                return self.esta_conectado
            except Exception as e:
                print(f"[{self.get_timestamp()}] Error al conectar: {str(e)}")
                return False
        return True

    async def desconectar(self):
        if self.esta_conectado:
            print(f"[{self.get_timestamp()}] Desconectando...")
            await self.sio.disconnect()
            self.esta_conectado = False

    async def enviar_mensaje(self, numero: str, mensaje: str):
        if not self.esta_conectado:
            print(f"[{self.get_timestamp()}] No hay conexión con el servidor")
            return False

        # Limpiar y validar el número (se espera que solo contenga dígitos)
        numero_formateado = numero.replace('+', '').replace(' ', '').replace('-', '')
        if not numero_formateado.isdigit() or len(numero_formateado) < 10:
            print(f"[{self.get_timestamp()}] Número inválido: {numero}")
            return False

        print(f"[{self.get_timestamp()}] Enviando mensaje a {numero_formateado}...")
        try:
            # Enviar un ping antes de enviar el mensaje
            await self.sio.emit('ping')
            # Llamada al evento 'send_message' esperando respuesta
            response = await asyncio.wait_for(
                self.sio.call('send_message', {'number': numero_formateado, 'message': mensaje}),
                timeout=30.0
            )
            await self.sio.emit('ping')
            if response and response.get('success'):
                print(f"[{self.get_timestamp()}] Mensaje enviado exitosamente")
                return True
            else:
                error = response.get('error') if response else 'Error desconocido'
                print(f"[{self.get_timestamp()}] Error al enviar mensaje: {error}")
                return False
        except asyncio.TimeoutError:
            print(f"[{self.get_timestamp()}] Tiempo de espera agotado")
            return False
        except Exception as e:
            print(f"[{self.get_timestamp()}] Error: {str(e)}")
            return False

# Ejemplo de uso: iniciar el cliente y dejarlo escuchando mensajes
if __name__ == "__main__":
    async def main():
        cliente = ClienteWhatsApp()
        if not await cliente.conectar():
            print("No se pudo conectar al servidor")
            return
        print("Cliente listo para recibir mensajes...\nPresiona Ctrl+C para salir.")
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\nCerrando cliente...")
        await cliente.desconectar()

    asyncio.run(main())

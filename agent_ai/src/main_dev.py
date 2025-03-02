#!/usr/bin/env python3
import asyncio
from cliente_whatsapp import ClienteWhatsApp

async def main():
    cliente = ClienteWhatsApp()

    if not await cliente.conectar():
        print("No se pudo conectar al servidor")
        return

    # Enviar un mensaje de ejemplo
    numero = "573204259649"
    mensaje = "Hola, este es un mensaje de prueba."
    await cliente.enviar_mensaje(numero, mensaje)

    print("Esperando mensajes entrantes. Presiona Ctrl+C para salir...")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Cerrando conexión...")

    await cliente.desconectar()

if __name__ == "__main__":
    asyncio.run(main())

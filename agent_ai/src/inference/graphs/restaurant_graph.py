from typing import Optional, Literal, List, Any

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage, ToolMessage
from langgraph.graph import StateGraph, START, MessagesState, END
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from core.config import settings
from core.schema_services import AzureServices
# from inference.cosmosDB import AsyncCosmosDBSaver
from core import utils
import pdb
from IPython.display import Image, display
from langchain_core.runnables.graph import CurveStyle, MermaidDrawMethod, NodeStyles
from datetime import datetime
from inference.tools.restaurant_tools import get_menu_tool,confirm_order_tool
import json
import asyncio

ai_services = AzureServices()
cosmos_db = ai_services.CosmosDBClient()



######################################################
# 1) Estado del Bot (hereda messages + pdf_text)
######################################################
class RestaurantState(MessagesState):
    pdf_text: Optional[str] = None
    thread_id: Optional[str] = None
        # - consultar_menu:

        #     Utiliza esta herramienta para mostrar el menú actualizado del restaurante.
        #     Informa al cliente que la consulta puede tardar unos segundos.
            
SYSTEM_PROMPT =     """
        Fecha y Hora Actual: {{fecha-hora}}
        Eres un asistente de IA especializado en atención a clientes en nuestro restaurante. Tu misión es guiar a los comensales en el proceso de seleccionar y confirmar cada producto o plato de su pedido.
        Debes indagar o preguntar los datos necesarios para realizar la orden.

        Herramientas disponibles:


        - confirmar_pedido:

            Esta herramienta se utiliza para registrar y actualizar el documento del pedido en Cosmos cada vez que se confirme un producto o plato.
            Importante: Cada vez que el cliente confirme un producto, debes llamar a esta herramienta una unica vezpor producto, con un input que sean exactamente los siguientes campos:
            "nombre_producto": Nombre o descripción del producto o plato.
            "cantidad": Número de unidades solicitadas.
            "observaciones": Comentarios adicionales o modificaciones solicitadas para el producto.
            "table_id": Número de mesa del cliente.
            "user_name": Nombre del cliente.
        
        - get menu tool:

            Esta herramienta se utiliza para obtener la disponibilidad del menú en tiempo real.
            Importante: Cada vez que el cliente pregunte por el menú, debes llamar a esta herramienta.
            
        Instrucciones y Reglas de Interacción:

        Saludo y cortesía: Inicia cada conversación saludando de forma amistosa, amable y profesional.
        Indagación: Pregunta al cliente si desea consultar el menú, obtener detalles sobre algún plato o confirmar un producto.
        Proceso de pedido:
        Una vez que el cliente seleccione un producto o plato y preguntes confirmando su elección, llama a la herramienta confirmar_pedido utilizando el formato exacto especificado anteriormente.
        La herramienta actualizará el documento del pedido cada vez que se confirme un producto, permitiendo que cada usuario en la mesa gestione sus productos de forma independiente.
        Claridad y veracidad: Proporciona respuestas claras y precisas. Si ocurre algún error o la herramienta no procesa correctamente la solicitud, informa al cliente de forma amable.
        Información de espera: Comunica al cliente que la acción puede tardar algunos segundos en procesarse.
        Actúa de manera muy servicial siempre preguntando si hay alguna otra orden o pedido que quiera realizar, preguntando por bebidas u otros platos que deseen ordenar.
        
        Recuerda: Tu objetivo es ofrecer una atención personalizada y eficiente. Cada vez que se confirme un producto o plato, y confirmes los datos del pedido, asegúrate de llamar a la herramienta confirmar_pedido con el input exacto (
            "mesa",
            "nombre_del_cliente",
            "nombre_producto",
            "cantidad",
            "observaciones"
            ) para actualizar correctamente el pedido."""
                

######################################################
# 2) main_agent_node (asíncrono) + tools usage
######################################################
async def main_agent_node(state: RestaurantState) -> RestaurantState:
    """
    1) Inyecta system prompt y PDF
    2) Llama repetidamente al LLM (con .bind_tools([...]))
       Si el LLM produce tool_calls (ej: name="search_tool"), se ejecutan
       y se añade un AIMessage con los resultados. 
       Se repite hasta que no haya más tool_calls.
    3) Devuelve el estado final
    """
    # Preparar la conversacion
    max_messages = 10 

    system_msg = SystemMessage(content=SYSTEM_PROMPT.replace("{{fecha-hora}}",datetime.now().isoformat()) + f" {state['pdf_text']}" )#\n Documentos consultables a través de la tool 'retrieval_tool':
    new_messages = [system_msg] + state["messages"][-max_messages:]

    # 1) Preparamos el LLM que tenga "search_tool" enlazado
    llm_raw = AzureServices().service_azure_open_ai.model_ai
    # bind_tools => el LLM sabe formatear la tool call como 
    # {"tool_calls": [{"name": "search_tool", "args": "..."}]}
    llm_with_tools = llm_raw.bind_tools([confirm_order_tool])#get_menu_tool

    # 2) Bucle: Llamamos al LLM -> revisamos tool_calls -> ejecutamos -> loop
    # while True:
    #     # Llamado sincrónico al LLM

    response_msg = llm_with_tools.invoke(new_messages)
    #     # Añadimos su output al historial
    new_messages.append(response_msg)
    # pdb.set_trace()
    # 3) Retornar el estado final
    return {
        "messages": new_messages,
        "pdf_text": state["pdf_text"],
        "thread_id": state["thread_id"]
    }
async def get_menu_node(state: RestaurantState) -> RestaurantState:
    """
    Nodo que utiliza la herramienta 'get_menu' para obtener el menú de un restaurante.
    
    Extrae la llamada a tool desde el último mensaje del estado. Si la llamada
    especifica la herramienta "get_menu", se extrae el parámetro 'restaurant_name' y se
    invoca la herramienta. El resultado se empaqueta en un ToolMessage y se agrega al 
    historial de mensajes.
    
    :param state: Estado actual del grafo, que debe incluir al menos:
                  - "messages": lista de mensajes (donde el último puede contener tool_calls)
                  - "pdf_text": (opcional) texto de referencia
                  - "thread_id": identificador del hilo
    :return: Estado actualizado con los nuevos mensajes resultantes de la invocación de la tool.
    """
    new_messages: List[Any] = []

    # Se toma el último mensaje recibido para inspeccionar si contiene tool_calls
    response_msg = state["messages"][-1]
    # Se espera que el mensaje tenga un atributo 'tool_calls', que es una lista de diccionarios
    tool_calls = getattr(response_msg, "tool_calls", None) or []
    
    for call in tool_calls:
        tool_name = call.get("name")
        tool_id = call.get("id")  # ID asignado por el LLM
        tool_args = call.get("args")
        
        if tool_name == "get_menu_tool":
            # Extraer el parámetro 'restaurant_name'. Se puede recibir como dict o directamente un str.
            if isinstance(tool_args, dict) and "restaurant_name" in tool_args:
                restaurant_name = tool_args["restaurant_name"]
            elif isinstance(tool_args, str):
                restaurant_name = tool_args
            else:
                restaurant_name = "Macchiato"  # Valor por defecto
            
            try:
                # Ejecutar la tool de forma asíncrona (ejecuta la función síncrona en un thread separado)
                # results = await asyncio.to_thread(get_menu_tool, restaurant_name)
                results = await get_menu_tool(restaurant_name)

                tool_content = f"Tool '{tool_name}' result:\n{json.dumps(results, indent=4)}"
                
                tool_msg = ToolMessage(
                    content=tool_content,
                    message=tool_content,
                    name=tool_name,
                    tool_call_id=tool_id
                )
                new_messages.append(tool_msg)
            except Exception as e:
                error_content = f"Error al ejecutar la herramienta '{tool_name}': {str(e)}"
                error_msg = AIMessage(
                    content=error_content,
                    additional_kwargs={"tool_call_id": tool_id}
                )
                new_messages.append(error_msg)
        else:
            # Si no se reconoce la herramienta, se genera un mensaje indicándolo
            no_tool_msg = AIMessage(
                content=f"No se encontró la herramienta llamada '{tool_name}'",
                additional_kwargs={"tool_call_id": tool_id}
            )
            new_messages.append(no_tool_msg)
    
    # Se combina el historial anterior de mensajes con los nuevos mensajes generados
    updated_state = {
        "messages": state["messages"] + new_messages,
        "pdf_text": state.get("pdf_text", ""),
        "thread_id": state.get("thread_id", "")
    }
    
    return updated_state

async def confirm_order_node(state: RestaurantState) -> RestaurantState:
    """
    Nodo que utiliza la herramienta 'confirm_order_tool' para confirmar un pedido.

    Extrae la llamada a tool desde el último mensaje del estado. Si la llamada
    especifica la herramienta "confirm_order_tool", se extraen los parámetros:
    'nombre_producto', 'cantidad' y 'observaciones', se invoca la herramienta y se
    empaqueta el resultado en un ToolMessage. En caso de error, se envía un AIMessage
    con la información del error.

    :param state: Estado actual del grafo, que debe incluir al menos:
                  - "messages": lista de mensajes (donde el último puede contener tool_calls)
                  - "pdf_text": (opcional) texto de referencia
                  - "thread_id": identificador del hilo
    :return: Estado actualizado con el historial de mensajes modificado.
    """
    new_messages: List[Any] = []

    # Se obtiene el último mensaje del historial, el cual se espera contenga tool_calls.
    response_msg = state["messages"][-1]
    tool_calls = getattr(response_msg, "tool_calls", None) or []

    for call in tool_calls:
        tool_name = call.get("name")
        tool_id = call.get("id")  # ID asignado por el LLM para la llamada a tool
        tool_args = call.get("args")

        if tool_name == "confirm_order_tool":
            # Extraer los parámetros necesarios de tool_args.
            if isinstance(tool_args, dict):
                nombre_producto = tool_args.get("nombre_producto", "default_nombre_producto")
                table_id = tool_args.get("table_id", "default_table_id")
                cantidad = tool_args.get("cantidad", 0)
                observaciones = tool_args.get("observaciones", "Sin Observaciones")
                user_name = tool_args.get("user_name", "default_user_name")
            else:
                error_msg = f"Parámetros inválidos para confirm_order_tool: {tool_args}"
                new_messages.append(
                    AIMessage(
                        content=error_msg,
                        additional_kwargs={"tool_call_id": tool_id}
                    )
                )
                continue

            try:
                # Invocar la tool de forma asíncrona.
                result = await confirm_order_tool(
                    nombre_producto=nombre_producto,
                    cantidad=cantidad,
                    observaciones=observaciones,
                    table_id=table_id,
                    user_name=user_name
                )
                tool_content = f"Tool 'confirm_order_tool' result:\n{result}"
                new_messages.append(
                    ToolMessage(
                        content=tool_content,
                        message=tool_content,
                        name=tool_name,
                        tool_call_id=tool_id
                    )
                )
            except Exception as e:
                error_content = f"Error al ejecutar confirm_order_tool: {str(e)}"
                new_messages.append(
                    AIMessage(
                        content=error_content,
                        additional_kwargs={"tool_call_id": tool_id}
                    )
                )
        else:
            # Si la llamada no corresponde a confirm_order_tool, se notifica.
            new_messages.append(
                AIMessage(
                    content=f"No se encontró la herramienta '{tool_name}'",
                    additional_kwargs={"tool_call_id": tool_id}
                )
            )

    # Se actualiza el estado combinando el historial anterior con los nuevos mensajes generados.
    updated_state: RestaurantState = {
        "messages": state["messages"] + new_messages,
        "pdf_text": state.get("pdf_text", ""),
        "thread_id": state.get("thread_id", "")
    }
    return updated_state


def route_after_agent(
        state: RestaurantState,
    ) -> Literal[
        "MainAgentNode",
        "ConfirmOrderNode",
        "GetMenuNode",
        "__end__"]: #, "call_agent_model",
        
    """Direcciona el siguiente nodo tras la acción del agente.

    Esta función determina el siguiente paso en el proceso de investigación basándose en el
    último mensaje en el estado. Maneja tres escenarios principales:

    
    1. Scraper en Ecommerce de Bata
    """
    last_message = state["messages"][-1]

    # "If for some reason the last message is not an AIMessage (due to a bug or unexpected behavior elsewhere in the code),
    # it ensures the system doesn't crash but instead tries to recover by calling the agent model again.
    if not isinstance(last_message, AIMessage):
        return "MainAgentNode"
    # If the "Into" tool was called, then the model provided its extraction output. Reflect on the result
    
    if last_message.tool_calls:
        if last_message.tool_calls and last_message.tool_calls[0]["name"] == "confirm_order_tool":
            return "ConfirmOrderNode"
        if last_message.tool_calls and last_message.tool_calls[0]["name"] == "get_menu_tool":
            return "GetMenuNode"
        # if last_message.tool_calls and last_message.tool_calls[0]["name"] == "scrape_tool":
        #     return "WebScraperNode"
        # The last message is a tool call that is not "Info" (extraction output)
        else:
            return "__end__"
    else:
        return "__end__"

######################################################
# 3) Construir el Graph + checkpoint
######################################################
class PDFChatAgent:
    def __init__(self):
        # 1) Creamos un StateGraph con RestaurantState
        workflow = StateGraph(state_schema=RestaurantState)
        
        # 2) Añadimos un solo nodo (main_agent_node)
        workflow.add_node("MainAgentNode", main_agent_node)
        workflow.add_node("ConfirmOrderNode", confirm_order_node)
        workflow.add_node("GetMenuNode", get_menu_node)

        # 3) Edge: START -> MainAgentNode
        workflow.add_edge(START, "MainAgentNode")
        workflow.add_conditional_edges("MainAgentNode", route_after_agent)
        workflow.add_edge("ConfirmOrderNode", "MainAgentNode")
        workflow.add_edge("GetMenuNode", "MainAgentNode")
        # workflow.add_edge("MainAgentNode", END)
        
        # 4) Saver con Cosmos
        self.cosmos_saver = ManualCosmosSaver(cosmos_db)

        # 5) Compilar
        self.app = workflow.compile() 

        # (Opcional) Generar imagen del grafo
        # image_data = self.app.get_graph().draw_mermaid_png(draw_method=MermaidDrawMethod.API)
        # image = Image(image_data)
        # with open("graph_image.png", "wb") as f:
        #     f.write(image.data)
    
    async def invoke_flow(
    self,
    user_input: str,  # Ahora recibimos el input directo
    pdf_text: Optional[str],
    conversation_id: str,
    conversation_name: str,
    user_id: str
    ) -> RestaurantState:
        # 1. Recuperar historial previo
        history_messages , last_pdf = await self.cosmos_saver.get_conversation_history(
            conversation_id, user_id
        )
        current_pdf = pdf_text if pdf_text is not None else last_pdf
        # 2. Construir lista de mensajes completa
        new_human_message = HumanMessage(
            content=user_input,
            id=utils.genereta_id(),
            response_metadata={"timestamp": datetime.now().isoformat()}
        )
        all_messages = history_messages + [new_human_message]
        
        # 3. Ejecutar el flujo
        new_state = await self.app.ainvoke(
            {"messages": all_messages, "pdf_text": current_pdf,"thread_id": conversation_id},
            config={
                "configurable": {
                    "thread_id": conversation_id,
                    "user_id": user_id
                    }}
        )
        
        # 4. Extraer y guardar solo el último intercambio
        new_messages = new_state["messages"][len(all_messages):]
        new_ai_messages = [msg for msg in new_messages if isinstance(msg, AIMessage)]
        if not new_ai_messages:
            raise ValueError("No se generó respuesta de AI")
        ai_response = new_ai_messages[-1]
        
        doc_id = await self.cosmos_saver.save_conversation(
            user_message=new_human_message,
            ai_message=ai_response,
            conversation_id=conversation_id,
            conversation_name=conversation_name,
            pdf_text=current_pdf,
            user_id=user_id
        )
        
        # Solicitud APi Whatsapp
        # requests
        # - endpoint: https://api.whatsapp.com/send
        # - method: POST
        # - body: {message:""}
        # 
        
        return new_state, doc_id

class ManualCosmosSaver:
    def __init__(self, cosmos_client):
        self.cosmos_client = cosmos_client

    def _message_to_dict(self, message: BaseMessage) -> dict:
        return {
            "content": message.content,
            "additional_kwargs": getattr(message, "additional_kwargs", {}),
            "response_metadata": getattr(message, "response_metadata", {}),
            "id": getattr(message, "id", ""),
            "created_at": datetime.now().isoformat()
        }
        
    async def save_conversation(self, user_message: BaseMessage, ai_message: BaseMessage, pdf_text: Optional[str], conversation_id: str, conversation_name: str, user_id: str) -> str:
        document = {
            "id": utils.genereta_id(),
            "user_id": user_id,
            "conversation_id": conversation_id,
            "conversation_name": conversation_name,
            "pdf_text": pdf_text,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "user_message": self._message_to_dict(user_message),
            "ai_message": self._message_to_dict(ai_message),
            "rate": False
        }
        created_doc = await self.cosmos_client.create_document(document)
        return created_doc["id"]
        
    async def get_conversation_history(self, conversation_id: str, user_id: str, max_messages: int = 20) -> tuple[list[BaseMessage], Optional[str]]:
        query = f"SELECT * FROM c WHERE c.conversation_id = '{conversation_id}' AND c.user_id = '{user_id}' ORDER BY c.created_at DESC OFFSET 0 LIMIT {max_messages}"
        docs = await self.cosmos_client.query_documents(query)
        
        history = []
        for doc in reversed(docs):  # Orden cronológico
            history.append(HumanMessage(
                content=doc["user_message"]["content"],
                additional_kwargs=doc["user_message"]["additional_kwargs"],
                response_metadata=doc["user_message"].get("response_metadata", {}),
                id=doc["user_message"]["id"]
            ))
            history.append(AIMessage(
                content=doc["ai_message"]["content"],
                additional_kwargs=doc["ai_message"]["additional_kwargs"],
                response_metadata=doc["ai_message"].get("response_metadata", {}),
                id=doc["ai_message"]["id"]
            ))
            
        latest_pdf = next(
            (doc["pdf_text"] for doc in docs if doc.get("pdf_text")), None)
        
        return history, latest_pdf



from typing import Optional, Literal

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
from inference.tools.bata_tools import search_tool, retrieval_tool, scrape_tool


ai_services = AzureServices()
cosmos_db = ai_services.CosmosDBClient()



######################################################
# 1) Estado del Bot (hereda messages + pdf_text)
######################################################
class PDFChatState(MessagesState):
    pdf_text: Optional[str] = None
    thread_id: Optional[str] = None

SYSTEM_PROMPT =     """

        Fecha y Hora Actual: {{fecha-hora}}
        Eres un asistente de IA de Bata llamado BataBot, encargado de asesorar a los clientes a través de WhatsApp y guiarlos en su proceso de compra en nuestro ecommerce. Tu objetivo es ayudar a los clientes a encontrar el producto ideal y dirigirlos al enlace de compra. Para ello, debes:

        Indagar los intereses y necesidades del cliente: Pregunta de manera amable y respetuosa sobre qué tipo de producto busca, asegurándote de identificar si se trata de artículos para hombre, mujer, 'niño' o 'niña' y a qué categoría pertenece el producto deseado: 'zapatos', 'accesorios', 'ofertas' o 'tendencia'.

        Utilizar la herramienta de búsqueda en tiempo real:

                scrape_tool: Esta herramienta te permite extraer información en tiempo real del ecommerce utilizando los parámetros gender, category y query. La query debe estar alineada con los intereses mencionados por el cliente para obtener resultados precisos.
                Nota importante: Antes de activar la herramienta, informa al cliente que realizarás una búsqueda que puede tardar algunos segundos y al responder siempre entrega el link contruyendolo con 'https://www.bata.com' al principio.
                Entrega los links sin ponerlos entre parentesis como un hipervinculo, retornalos como strings sin parentesis.
                Si notas que el link es demasiado genérico como https://www.bata.com/co/mujer/accesorios/cinturones/, aclara al usuario que no se trata de un solo cinturón sino de varios productos de la categoría de cinturones, por lo que no deberías retornan ningún precio o descripción específica como si fuera de solo un producto ya que podría ser erroneo.

        Proceso de respuesta:

            Si ya tienes suficiente información para responder, procede sin llamar a herramientas adicionales.
            Antes de realizar una busqueda a travez de alguna herramienta, confirma con el cliente si quiere que realices la busqueda ya que puede tardar algunos segundos
            Si la herramienta no arroja resultados, comunica de forma clara y amable que no se encontró información relacionada.
            Siempre que se active la herramienta 'scrape_tool', retorna el link, entrega exactamente el link en cuestión, agregando 'https://www.bata.com' al principio.
        Reglas generales:
            Siempre saluda presentandote de manera muy amigable y usa emojis
            Sé conciso, preciso y veraz; evita inventar información.
            Saluda siempre al cliente con un tono respetuoso y servicial.
            Recuerda: Tu atención debe ser proactiva y orientada a guiar al cliente eficazmente hasta el enlace de compra en el ecommerce de Bata.
            Responde en el idioma que hable el cliente.
            Para resaltar el texto en negrilla solo utiliza un asterisco al final y otro al principio del texto (*ejemplo*)

        """
        

######################################################
# 2) main_agent_node (asíncrono) + tools usage
######################################################
async def main_agent_node(state: PDFChatState) -> PDFChatState:
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
    llm_with_tools = llm_raw.bind_tools([search_tool,retrieval_tool, scrape_tool])

    # 2) Bucle: Llamamos al LLM -> revisamos tool_calls -> ejecutamos -> loop
    # while True:
    #     # Llamado sincrónico al LLM

    response_msg = llm_with_tools.invoke(new_messages)
    print("\033[92mresponse_msg:", response_msg.content, "\033[0m")
    response_msg.content=response_msg.content.replace("**","*")
    #     # Añadimos su output al historial
    new_messages.append(response_msg)

    # 3) Retornar el estado final
    return {
        "messages": new_messages,
        "pdf_text": state["pdf_text"],
        "thread_id": state["thread_id"]
    }
async def web_search_node(state: PDFChatState) -> PDFChatState:
    """
    1) Nodo con Tool de Busqueda Web
    """

    # while True:

    new_messages=[]
    # Llamado sincrónico al LLM
    response_msg = state["messages"][-1]#llm_with_tools.invoke(new_messages)
    # Añadimos su output al historial
    # new_messages.append(response_msg)

    # Ver tool_calls en el AIMessage
    tool_calls = getattr(response_msg, "tool_calls", None) or []
    # if not tool_calls:
    #     # No hay tools que invocar => rompemos el bucle
    #     break

    # De lo contrario, para cada tool_call => ejecutar
    for call in tool_calls:
        tool_name = call["name"]
        tool_id = call["id"]      # ID con que el LLM etiquetó la llamada
        tool_args = call["args"]

        # # Tool Search
        if tool_name == "search_tool":

            if isinstance(tool_args, dict) and "query" in tool_args:
                actual_query = tool_args["query"]   # extraemos string
            else:
                actual_query = tool_args            # asumimos que es str

            results = await search_tool(actual_query)
            tool_content = f"Tool '{tool_name}' result:\n{results}"

            # Mensaje "tool" (o "assistant") con el ID correspondiente
            tool_msg = ToolMessage(
                content=tool_content,
                name=tool_name,
                tool_call_id=tool_id
            )
            new_messages.append(tool_msg)
        
        else:
            no_tool_msg = AIMessage(
                content=f"No tool found named {tool_name}",
                additional_kwargs={"tool_call_id": tool_id}
            )
            new_messages.append(no_tool_msg)
            
        # state["messages"] = state["messages"] + new_messages
    # Se repite el while => el LLM ve esos ToolMessage y puede decidir 
    # si volver a llamar la tool o responder.

    # 3) Retornar el estado final
    return {
        "messages": new_messages,
        "pdf_text": state["pdf_text"],
        "thread_id": state["thread_id"]
    }
async def document_retrieval_node(state: PDFChatState) -> PDFChatState:
    """
    1) Nodo con Tool de Busqueda en Base de Datos vectorial. 
    """
    
    # while True:
    new_messages=[]
    # Llamado sincrónico al LLM
    response_msg = state["messages"][-1]#llm_with_tools.invoke(new_messages)
    # Añadimos su output al historial
    # new_messages.append(response_msg)

    # Ver tool_calls en el AIMessage
    tool_calls = getattr(response_msg, "tool_calls", None) or []
    # if not tool_calls:
    #     # No hay tools que invocar => rompemos el bucle
    #     break

    # De lo contrario, para cada tool_call => ejecutar
    for call in tool_calls:
        tool_name = call["name"]
        tool_id = call["id"]      # ID con que el LLM etiquetó la llamada
        tool_args = call["args"]

        
        # Mensaje "tool" (o "assistant") con el ID correspondiente
        #Tool Retrieval
        if tool_name == "retrieval_tool":
            # pdb.set_trace()
            if isinstance(tool_args, dict) and "query" in tool_args:
                actual_query = tool_args["query"]   # extraemos string
            else:
                actual_query = tool_args            # asumimos que es str

            results = await retrieval_tool(actual_query, state["thread_id"])
            tool_content = f"Tool '{tool_name}' result:\n{results}"

            # Mensaje "tool" (o "assistant") con el ID correspondiente
            tool_msg = ToolMessage(
                content=tool_content,
                name=tool_name,
                tool_call_id=tool_id
            )
            new_messages.append(tool_msg)
            
        else:
            no_tool_msg = AIMessage(
                content=f"No tool found named {tool_name}",
                additional_kwargs={"tool_call_id": tool_id}
            )
            new_messages.append(no_tool_msg)

        # Se repite el while => el LLM ve esos ToolMessage y puede decidir 
        # si volver a llamar la tool o responder.

    # 3) Retornar el estado final
    return {
        "messages": new_messages,
        "pdf_text": state["pdf_text"],
        "thread_id": state["thread_id"]
    }

async def web_scraper_node(state: PDFChatState) -> PDFChatState:
    """
    1) Nodo con Tool de Web Scraping
    
    """
    
    # while True:
    new_messages=[]
    # Llamado sincrónico al LLM
    response_msg = state["messages"][-1]#llm_with_tools.invoke(new_messages)
    # Añadimos su output al historial
    # new_messages.append(response_msg)

    # Ver tool_calls en el AIMessage
    tool_calls = getattr(response_msg, "tool_calls", None) or []
    # if not tool_calls:
    #     # No hay tools que invocar => rompemos el bucle
    #     break

    # De lo contrario, para cada tool_call => ejecutar
    for call in tool_calls:
        tool_name = call["name"]
        tool_id = call["id"]      # ID con que el LLM etiquetó la llamada
        tool_args = call["args"]

        
        # Mensaje "tool" (o "assistant") con el ID correspondiente
        #Tool Retrieval
        if tool_name == "scrape_tool":

            results = scrape_tool(
                query=tool_args["query"],
                gender=tool_args["gender"],
                category=tool_args["category"]
                )
            tool_content = f"Tool '{tool_name}' result:\n{results}"

            # Mensaje "tool" (o "assistant") con el ID correspondiente
            tool_msg = ToolMessage(
                content=tool_content,
                name=tool_name,
                tool_call_id=tool_id
            )
            new_messages.append(tool_msg)
            
        else:
            no_tool_msg = AIMessage(
                content=f"No tool found named {tool_name}",
                additional_kwargs={"tool_call_id": tool_id}
            )
            new_messages.append(no_tool_msg)

        # Se repite el while => el LLM ve esos ToolMessage y puede decidir 
        # si volver a llamar la tool o responder.

    # 3) Retornar el estado final
    return {
        "messages": new_messages,
        "pdf_text": state["pdf_text"],
        "thread_id": state["thread_id"]
    }
def route_after_agent(
        state: PDFChatState,
    ) -> Literal[
        "MainAgentNode",
        # "SearchNode",
        # "RetrievalNode",
        "WebScraperNode",
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
        # if last_message.tool_calls and last_message.tool_calls[0]["name"] == "search_tool":
        #     return "SearchNode"
        # if last_message.tool_calls and last_message.tool_calls[0]["name"] == "retrieval_tool":
        #     return "RetrievalNode"
        if last_message.tool_calls and last_message.tool_calls[0]["name"] == "scrape_tool":
            return "WebScraperNode"
        # The last message is a tool call that is not "Info" (extraction output)
    else:
        return "__end__"

######################################################
# 3) Construir el Graph + checkpoint
######################################################
class PDFChatAgent:
    def __init__(self):
        # 1) Creamos un StateGraph con PDFChatState
        workflow = StateGraph(state_schema=PDFChatState)
        
        # 2) Añadimos un solo nodo (main_agent_node)
        workflow.add_node("MainAgentNode", main_agent_node)
        # workflow.add_node("SearchNode", web_search_node)
        # workflow.add_node("RetrievalNode", document_retrieval_node)
        workflow.add_node("WebScraperNode", web_scraper_node)
        
        # 3) Edge: START -> MainAgentNode
        workflow.add_edge(START, "MainAgentNode")
        workflow.add_conditional_edges("MainAgentNode", route_after_agent)
        # workflow.add_edge("SearchNode", "MainAgentNode")
        # workflow.add_edge("RetrievalNode", "MainAgentNode")
        workflow.add_edge("WebScraperNode", "MainAgentNode")
        # workflow.add_edge("MainAgentNode", END)
        
        # 4) Saver con Cosmos
        self.cosmos_saver = ManualCosmosSaver(cosmos_db)

        # 5) Compilar
        self.app = workflow.compile() 

        # (Opcional) Generar imagen del grafo
        image_data = self.app.get_graph().draw_mermaid_png(draw_method=MermaidDrawMethod.API)
        image = Image(image_data)
        with open("graph_image.png", "wb") as f:
            f.write(image.data)
    
    async def invoke_flow(
    self,
    user_input: str,  # Ahora recibimos el input directo
    pdf_text: Optional[str],
    conversation_id: str,
    conversation_name: str,
    user_id: str
    ) -> PDFChatState:
        print(f"\033[92mConversation_id: {conversation_id}\033[0m")
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

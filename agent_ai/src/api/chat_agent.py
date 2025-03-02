
from typing import List
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from core.schema_http import (
    RequestHTTPChat, ResponseHTTPChat,
    RequestHTTPVote, ResponseHTTPVote,
    ResponseHTTPStartConversation, RequestHTTPStartConversation,RequestHTTPUpdateState,
    RequestHTTPSessions, ResponseHTTPSessions,
    ResponseHTTPOneSession, RequestHTTPOneSession
)
from core.utils import genereta_id
import pdb
from inference.graphs.restaurant_graph import PDFChatAgent
from langchain_core.messages import HumanMessage
from core.utils import extract_text_content,extract_word_content,extract_excel_content
from core.schema_services import AzureServices
# from enviar_mensaje import ClienteWhatsApp


chat_agent_router = APIRouter()

# Instancias de servicios
pdf_extractor = AzureServices.PdfProcessor()
cosmos_db = AzureServices.CosmosDBClient()
orders_db = AzureServices.AsyncOrderManager()
pdf_chat_agent = PDFChatAgent()

@chat_agent_router.post("/message", response_model=ResponseHTTPChat)
async def endpoint_message(request: RequestHTTPChat):
    """
    Endpoint para procesar el mensaje y generar respuesta.
    """

    if pdf_chat_agent is None:
        raise HTTPException(status_code=500, detail="chat_agent no está inicializado")

    #human_msg = HumanMessage(content=request.query)
    new_state, message_id = await pdf_chat_agent.invoke_flow(
        user_input=request.query,
        pdf_text=None,
        conversation_id=request.conversation_id,
        conversation_name=request.conversation_name,
        user_id=request.user_id
    )
    final_msg = new_state["messages"][-1]
    pdb.set_trace()
    client_whatsapp.enviar_mensaje("573204259649", final_msg.content)
    return {"id": message_id, "text": final_msg.content}





@chat_agent_router.post("/vote", response_model=ResponseHTTPVote)
async def endpoint_vote(request: RequestHTTPVote):
    """
    Ejemplo de cómo se maneja el voto o rating de un documento en Cosmos.
    """
    res = await cosmos_db.update_document_rate(document_id=request.id,  rate=request.rate, partition_key=request.thread_id, )
    return {"id": genereta_id(), "text": "OK", "state": res}

@chat_agent_router.post("/attachment", response_model=dict)  # Ajusta el response_model según tu modelo
async def upload_attachment(
    user_id: str = Form(...),
    conversation_id: str = Form(...),
    conversation_name: str = Form(...),
    message: str = Form(...),
    files: List[UploadFile] = File(...)
):
    """
    Endpoint para cargar uno o varios archivos (PDF, TXT, DOC/DOCX, XLS/XLSX)
    y extraer su contenido.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Se requiere al menos un archivo.")

    # Lista de content types permitidos
    allowed_types = [
        "application/pdf",
        "text/plain",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ]

    files_contents = []
    for file in files:
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400, 
                detail=f"Tipo de archivo no soportado: {file.content_type}. "
                       "Solo se permiten PDF, TXT, DOC/DOCX, XLS/XLSX."
            )
        content = await file.read()

        if file.content_type == "application/pdf":
            text = content
            doc_type = "pdf"
        elif file.content_type == "text/plain":
            text = extract_text_content(content)
            doc_type = "txt"
        elif file.content_type in [
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ]:
            text = extract_word_content(content)
            doc_type = "word"
            
        elif file.content_type in [
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ]:
            text = extract_excel_content(content)
            doc_type = "excel"
            
        else:
            text = ""
        
        files_contents.append({
            "file_name": file.filename,
            "content": text,
            "doc_type":doc_type
        })

    # Aquí se llama a la función que procesa el contenido extraído.
    # Si bien en el ejemplo original se usaba 'pdf_extractor.main', quizá debas refactorizarla
    # para que trabaje con distintos tipos de archivos. Por ahora se mantiene el nombre.
    text_content, response_info = await pdf_extractor.main(
        user_id=user_id,
        conversation_id=conversation_id,
        files_obj=files_contents
    )

    if not text_content:
        raise HTTPException(status_code=400, detail="No se pudo extraer contenido de los archivos.")

    resultado_texto = ""
    if response_info.get('read_files'):
        read_files = [res.get('file_name') for res in response_info.get('read_files')]
        resultado_texto += f"\nDocumentos almacenados en base de conocimientos y consultables a través de la tool 'retrieval_tool': {read_files}"
        
    if response_info.get('unread_files'):
        unread_files = [res.get('file_name') for res in response_info.get('unread_files')]
        resultado_texto += f"\nDocumentos no almacenados en base de conocimientos: {unread_files}"

    new_state, message_id = await pdf_chat_agent.invoke_flow(
        user_input=message,
        pdf_text=resultado_texto,
        conversation_id=conversation_id,
        conversation_name=conversation_name,
        user_id=user_id
    )

    return {
        "id": message_id,
        "text": new_state['messages'][-1].content,
    }

@chat_agent_router.post("/sessions", response_model=ResponseHTTPSessions)
async def read_sessions(request: RequestHTTPSessions):
    """
    Ruta para cargar las sesiones (conversaciones) de un usuario.
    Lanza HTTP 404 si no existen conversaciones para ese usuario.
    """
    response = await cosmos_db.get_user_conversations(request.user_id)
    
    if not response:
        # Si la lista está vacía, asumimos que no hay conversaciones
        # y lanzamos un 404.
        raise HTTPException(
            status_code=404, 
            detail=f"No se encontraron conversaciones para el user_id {request.user_id}."
        )
    
    return {"user_id": request.user_id, "sessions": response}

@chat_agent_router.post("/get_one_session", response_model=ResponseHTTPOneSession)
async def read_one_session(request: RequestHTTPOneSession):
    """
    Ruta para cargar los documentos (mensajes) de una sola conversación.
    Lanza HTTP 404 si no existe o no se encontraron documentos en esa conversación.
    """
    response = await cosmos_db.get_documents_by_thread_id(request.conversation_id)

    if not response:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró la conversación con el conversation_id {request.conversation_id}."
        )
    return response


@chat_agent_router.post("/orders")#response_model=ResponseHTTPSessions
async def read_orders(request: RequestHTTPSessions):
    """
    Ruta para cargar los pedidos.
    Lanza HTTP 404 si no existen conversaciones para ese usuario.
    """
    response = await orders_db.get_today_orders_not_paid()
    
    if not response:
        # Si la lista está vacía, asumimos que no hay conversaciones
        # y lanzamos un 404.
        raise HTTPException(
            status_code=404, 
            detail=f"No se encontraron conversaciones para el user_id {request.user_id}."
        )
    return response#{"user_id": request.user_id, "sessions": response}
    
@chat_agent_router.post("/update_state")#response_model=ResponseHTTPSessions
async def update_order_state (request: RequestHTTPUpdateState):
    """
    Ruta para cargar los pedidos.
    Lanza HTTP 404 si no existen conversaciones para ese usuario.
    """
    response = await orders_db.update_order_status(order_id=request.order_id, state=request.state,partition_key=request.partition_key)
    
    if not response:
        # Si la lista está vacía, asumimos que no hay conversaciones
        # y lanzamos un 404.
        raise HTTPException(
            status_code=404, 
            detail=f"No se encontraron conversaciones para el order_id {request.order_id}."
        )
    
    return response#{"user_id": request.user_id, "sessions": response}


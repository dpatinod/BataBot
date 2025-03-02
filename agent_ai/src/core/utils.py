from datetime import datetime
from pytz import timezone
from docx import Document
import pandas as pd
import timeit
import uuid
import tiktoken
import pdb
import io


def genereta_id() -> str: 
    now = datetime.now()
    str_now = now.strftime("%Y%m%d")
    uuid_id = str(uuid.uuid4())
    chat_id = f'{str_now}-{uuid_id}'
    return chat_id

def current_colombian_time() -> str:
    current_time = datetime.now(timezone('America/Bogota')).strftime('%Y-%m-%d %H:%M:%S')
    return current_time

def timeit_decorator(func):
    def wrapper(*args, **kwargs):
        start_time = timeit.default_timer()
        result = func(*args, **kwargs)
        end_time = timeit.default_timer()
        elapsed_time = end_time - start_time
        return result, elapsed_time
    return wrapper

def count_tokens(texts=None, model_reference="cl100k_base"):   
    if texts:
        encoding = tiktoken.get_encoding(model_reference)
        count = encoding.encode(texts)
        return count
    



def format_conversation_data(documents):
    # Suponiendo que todos son de la misma conversación
    
    if len(documents)==0:
        return None
    
    conversation_id = documents[0]['conversation_id'] if documents else None

    messages = []
    for doc in documents:
        user_msg = doc.get("user_message", {})
        ai_msg = doc.get("ai_message", {})
        
        # Mensaje de usuario
        messages.append({
            "id": doc.get("id"),
            "role": "user",
            "content": user_msg.get("content"),
            "created_at": user_msg.get("created_at")
        })
        
        # Mensaje de la IA
        messages.append({
            "id": doc.get("id"),
            "role": "assistant",
            "content": ai_msg.get("content"),
            "created_at": ai_msg.get("created_at"),
            "rate": doc.get("rate")
        })

    # Ordenar por fecha si es necesario
    messages.sort(key=lambda msg: datetime.fromisoformat(msg["created_at"]))

    return {
        "conversation_id": conversation_id,
        "conversation_name": documents[0].get("conversation_name"),
        "user_id": documents[0].get("user_id"),
        "messages": messages
    }


def extract_text_content(content: bytes) -> str:
    # Asumimos que el contenido está en UTF-8
    return content.decode("utf-8")

def extract_word_content(content: bytes) -> str:
    """
    Extrae el texto de un archivo Word (DOCX) a partir de un objeto de bytes.

    Args:
        content (bytes): Contenido del archivo Word en formato bytes.

    Returns:
        str: Texto extraído del archivo Word.
    """
    # Convertir los bytes en un stream de memoria
    stream = io.BytesIO(content)
    # Abrir el documento usando python-docx
    document = Document(stream)
    
    # Extraer el texto de cada párrafo del documento
    full_text = []
    for paragraph in document.paragraphs:
        full_text.append(paragraph.text)
    
    # Unir los párrafos en un único string, separándolos por saltos de línea
    return "\n".join(full_text)

def extract_excel_content(content: bytes) -> str:
    """
    Lee el contenido de un archivo Excel (en formato bytes) y lo convierte a JSONL,
    donde cada línea representa un registro del Excel.

    Args:
        content (bytes): Contenido del archivo Excel en formato bytes.

    Returns:
        str: Un string en formato JSONL con los registros del Excel.
    """
    try:
        # Crear un objeto BytesIO a partir de los bytes del archivo Excel
        excel_io = io.BytesIO(content)
        # Leer el contenido del Excel en un DataFrame de pandas
        df = pd.read_excel(excel_io)
    except Exception as e:
        raise ValueError(f"Error al leer el archivo Excel: {str(e)}")
    
    # Convertir el DataFrame a JSON Lines (cada registro en una línea)
    jsonl_string = df.to_json(orient="records", lines=True, force_ascii=False)
    return jsonl_string



    

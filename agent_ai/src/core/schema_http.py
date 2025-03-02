from pydantic import BaseModel
from typing import Optional, Literal
from fastapi import UploadFile


class ResponseHTTPChat(BaseModel):
    id: str
    text: str
class ResponseHTTPStartConversation(BaseModel):
    user_id: str
    conversation_id: str
    conversation_name: str
class RequestHTTPStartConversation(BaseModel):
    user_id: str
    conversation_name: str
class RequestHTTPChat(BaseModel):
    user_id: str
    conversation_id: str
    conversation_name: str
    query: str

class RequestHTTPVote(BaseModel):
    id: str
    thread_id: str
    rate:bool

class ResponseHTTPVote(BaseModel):
    id: str
    text: str
    state: bool
    
class RequestHTTPSessions(BaseModel):
    user_id: str
class ResponseHTTPSessions(BaseModel):
    user_id: str
    sessions:list
    
class RequestHTTPOneSession(BaseModel):
    conversation_id: str
class ResponseHTTPOneSession(BaseModel):
    conversation_id: str
    conversation_name:str
    user_id:str
    messages: list
    
class RequestHTTPUpdateState(BaseModel):
    order_id: str
    state: Literal["0","1","2"] = "0"
    partition_key: Optional[str] = None
    
    
    
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import logging
from datetime import datetime

# IMPORTANTE: Ajusta la siguiente línea para importar tu clase AsyncInventoryManager
from core.schema_services import AzureServices
# Suponemos que la clase AsyncInventoryManager está definida así:
# class AsyncInventoryManager:
#     ...

# Instancia del administrador de inventario
inventory_manager = AzureServices.AsyncInventoryManager()  # O bien: AsyncInventoryManager()

# Definición de modelos Pydantic para las solicitudes y respuestas

class Product(BaseModel):
    id: str
    restaurant_id: str
    name: str
    quantity: int
    unit: str
    price: Optional[float] = None
    last_updated: str

class AddProductRequest(BaseModel):
    restaurant_id: str
    name: str
    quantity: int
    unit: str
    price: Optional[float] = None

class UpdateProductRequest(BaseModel):
    product_id: str
    restaurant_id: str
    name: Optional[str] = None
    quantity: Optional[int] = None
    unit: Optional[str] = None
    price: Optional[float] = None

class DeleteProductRequest(BaseModel):
    product_id: str
    restaurant_id: str
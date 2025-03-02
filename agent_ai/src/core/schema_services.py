from openai import AzureOpenAI
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
import pdb
import asyncio
from core.config import settings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
import tiktoken
import logging
from typing import List, Tuple, Optional, Dict, Any, Literal
from io import BytesIO
# Azure Cognitive Search
from azure.search.documents.indexes.aio import SearchIndexClient
# from azure.search.documents import SearchClient
from azure.search.documents.aio import SearchClient
import pandas as pd
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchField,
    SearchableField,
    SearchFieldDataType,
    VectorSearch,
    VectorSearchProfile,
    HnswAlgorithmConfiguration,
    SemanticConfiguration,
    SemanticPrioritizedFields,
    SemanticField,
    SemanticSearch
)
import hashlib
from datetime import datetime
from azure.core.exceptions import ResourceNotFoundError
from core import utils

from azure.cosmos.aio import CosmosClient
from azure.cosmos import exceptions, PartitionKey
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceNotFoundError
from pydantic import BaseModel
from azure.storage.filedatalake import DataLakeServiceClient
from core.config import Settings  # Ajusta la importación según tu estructura de proyecto
from azure.storage.blob import BlobServiceClient

class AzureServices:
    class AzureOpenAI:
        def __init__(self):
            api_key: str = settings.ai_services.azure_openai_api_key
            api_version: str = settings.ai_services.openai_api_version
            azure_endpoint: str = settings.ai_services.azure_openai_endpoint
            self._client_AzureOpenAI: AzureOpenAI = AzureOpenAI(
                api_key = api_key, 
                api_version = api_version,  
                azure_endpoint = azure_endpoint,
            )
            self.model_ai: AzureChatOpenAI = AzureChatOpenAI(
                api_key = api_key, 
                openai_api_version = api_version,
                azure_endpoint = azure_endpoint,
                azure_deployment = settings.ai_services.model_gpt4o_name
            )
            self.model_embeddings: AzureOpenAIEmbeddings = AzureOpenAIEmbeddings(
                api_key = api_key, 
                openai_api_version = api_version,
                azure_endpoint = azure_endpoint,
                azure_deployment = settings.ai_services.model_embeddings_name
            )
            
    class BlobStorage:
        """
        Clase para consultar el menú actualizado de un restaurante desde Azure Blob Storage.
        """

        def __init__(self):
            """
            Inicializa la conexión a Azure Blob Storage utilizando la cadena de conexión y el contenedor 
            especificados en la configuración.
            """
            # Se asume que la configuración correspondiente se encuentra en settings.blob_services
            self.connection_string: str = settings.db_services.azure_blob_storage_connection_string
            self.container_name: str = settings.db_services.azure_blob_storage_container_name
            
            # Crear el cliente del servicio Blob a partir de la cadena de conexión
            self.blob_service_client: BlobServiceClient = BlobServiceClient.from_connection_string(self.connection_string)
            self.container_client = self.blob_service_client.get_container_client(self.container_name)

        def get_menu_excel(self, restaurant_name: str) -> str:
            """
            Descarga el archivo Excel que contiene el menú actualizado del restaurante desde Blob Storage,
            lo convierte a un DataFrame y retorna su contenido en formato JSONL, donde cada línea es un diccionario.

            :param restaurant_name: Nombre del restaurante. Este valor se usa para identificar la carpeta 
                                    en el contenedor donde se encuentra el menú (por ejemplo, "Macciato").
            :return: Un string en formato JSONL con cada registro del menú.
            """
            # Construir la ruta del blob usando el nombre del restaurante y el nombre del archivo
            blob_path = f"{restaurant_name}/config/menu.xlsx"
            try:
                blob_client = self.container_client.get_blob_client(blob=blob_path)
                logging.info(f"Descargando el menú desde el blob: {blob_path}")
                
                download_stream = blob_client.download_blob()
                excel_content = download_stream.readall()
                
                # Leer el contenido Excel en un DataFrame
                df = pd.read_excel(BytesIO(excel_content))
                
                # Convertir el DataFrame a JSONL (una línea por registro)
                jsonl = df.to_json(orient="records", lines=True)
                
                return jsonl

            except Exception as e:
                logging.error(f"Error al descargar el menú para el restaurante '{restaurant_name}': {e}")
                raise
    
    class AsyncOrderManager:
        def __init__(self):
            """
            Inicializa la conexión a Cosmos DB utilizando los parámetros de configuración
            definidos en la clase 'settings'.

            Se esperan los siguientes atributos en 'settings.db_services':
                - azure_cosmos_db_endpoint: URL del endpoint de Cosmos DB.
                - azure_cosmos_db_api_key: Clave de autenticación para Cosmos DB.
                - azure_cosmos_db_name: Nombre de la base de datos.
                - azure_cosmos_db_container_name: Nombre del contenedor para los pedidos.
            """
            self.endpoint = settings.db_services.azure_cosmos_db_endpoint
            self.key = settings.db_services.azure_cosmos_db_api_key
            self.database_name = settings.db_services.azure_cosmos_db_name
            self.container_name = settings.db_services.azure_cosmos_db_container_name
            
            # Crear el cliente de Cosmos DB utilizando la versión asíncrona de la SDK
            self.client = CosmosClient(self.endpoint, self.key)
            self.database = self.client.get_database_client(self.database_name)
            self.container = self.database.get_container_client(self.container_name)

            logging.info(
                "Conexión a Cosmos DB establecida. Base de datos: '%s', Contenedor: '%s'",
                self.database_name, self.container_name
            )
        async def create_order(self, order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            """
            Crea un nuevo pedido en Cosmos DB.

            :param order: Diccionario que representa el pedido.
            :return: El pedido creado (con campos adicionales, como 'id') o None en caso de error.
            """
            try:
                # Asignar fecha de creación
                # TABLE_ID= "1"
                order["id"] = f"{datetime.now().isoformat()}-{order.get('table_id', '0')}"
                order["created_at"] = datetime.now().isoformat()
                
                created_order = await self.container.create_item(body=order)#, partitionKey=order["table_id"]
                logging.info("Pedido creado con id: %s", created_order.get("id"))
                return created_order
            except CosmosHttpResponseError as e:
                logging.exception("Error al crear el pedido: %s", e)
                return None

        async def get_order(self, order_id: str, partition_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
            """
            Recupera un pedido a partir de su ID.

            :param order_id: ID del pedido.
            :param partition_key: Clave de partición del pedido (si es distinta de order_id).
            :return: El pedido encontrado o None si no existe o se produce algún error.
            """
            try:
                # Si no se especifica la clave de partición, se asume que es el mismo order_id
                if partition_key is None:
                    partition_key = order_id
                order = await self.container.read_item(item=order_id, partitionKey=partition_key)
                logging.info("Pedido recuperado con id: %s", order_id)
                return order
            except CosmosResourceNotFoundError:
                logging.warning("Pedido no encontrado con id: %s", order_id)
                return None
            except CosmosHttpResponseError as e:
                logging.exception("Error al recuperar el pedido %s: %s", order_id, e)
                return None

        async def update_order(self, order_id: str, updated_fields: Dict[str, Any],
                            partition_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
            """
            Actualiza un pedido completo, modificando los campos especificados.

            :param order_id: ID del pedido a actualizar.
            :param updated_fields: Diccionario con los campos a actualizar.
            :param partition_key: Clave de partición del pedido (si aplica).
            :return: El pedido actualizado o None en caso de error.
            """
            try:
                if partition_key is None:
                    partition_key = order_id

                # Recuperar el pedido actual
                order = await self.container.read_item(item=order_id, partitionKey=partition_key)

                # Actualizar los campos del pedido
                order.update(updated_fields)
                order["updated_at"] = datetime.utcnow().isoformat()

                updated_order = await self.container.replace_item(item=order_id, body=order)
                logging.info("Pedido actualizado con id: %s", order_id)
                return updated_order
            except CosmosResourceNotFoundError:
                logging.warning("Pedido no encontrado para actualizar con id: %s", order_id)
                return None
            except CosmosHttpResponseError as e:
                logging.exception("Error al actualizar el pedido %s: %s", order_id, e)
                return None

        async def delete_order(self, order_id: str, partition_key: Optional[str] = None) -> bool:
            """
            Elimina un pedido de Cosmos DB.

            :param order_id: ID del pedido a eliminar.
            :param partition_key: Clave de partición del pedido (si aplica).
            :return: True si se eliminó correctamente, False en caso contrario.
            """
            try:
                if partition_key is None:
                    partition_key = order_id
                await self.container.delete_item(item=order_id, partitionKey=partition_key)
                logging.info("Pedido eliminado con id: %s", order_id)
                return True
            except CosmosResourceNotFoundError:
                logging.warning("Pedido no encontrado para eliminar con id: %s", order_id)
                return False
            except CosmosHttpResponseError as e:
                logging.exception("Error al eliminar el pedido %s: %s", order_id, e)
                return False

        async def update_order_status(self, order_id: str, state: str,
                                    partition_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
            """
            Actualiza el campo 'state' de un pedido.

            :param order_id: ID del pedido a actualizar.
            :param state: Nuevo valor para el campo 'state' (por ejemplo, "pendiente", "enviado", "cancelado", etc.).
            :param partition_key: Clave de partición del pedido (si aplica).
            :return: El pedido actualizado o None en caso de error.
            """
            try:
                if partition_key is None:
                    partition_key = order_id

                # Leer el pedido actual
                order = await self.container.read_item(item=order_id, partition_key=partition_key)
                order["state"] = state
                order["updated_at"] = datetime.now().isoformat()

                updated_order = await self.container.replace_item(item=order_id, body=order)
                logging.info("state del pedido (id: %s) actualizado a: %s", order_id, state)
                print("state del pedido (id: %s) actualizado a: %s", order_id, state)
                return updated_order
            except CosmosResourceNotFoundError:
                logging.warning("Pedido no encontrado para actualizar state con id: %s", order_id)
                return None
            except CosmosHttpResponseError as e:
                logging.exception("Error al actualizar el state del pedido %s: %s", order_id, e)
                return None
    
        async def get_today_orders_not_paid(self) -> List[Dict[str, Any]]:
            """
            Retorna todos los pedidos creados el día actual (UTC) cuyo estado sea distinto de 'pagado'.
            """
            try:
                # pdb.set_trace()
                # Obtenemos la fecha actual en UTC, por ejemplo '2025-02-08'
                today_str = datetime.now().date().isoformat()
                
                # Construimos el rango de tiempo para el día actual (desde 00:00:00 a 23:59:59).
                start_of_today = f"{today_str}T00:00:00"
                end_of_today = f"{today_str}T23:59:59"

                # Consulta a Cosmos DB: pedidos creados hoy y state != 'pagado'
                query = (
                    "SELECT * FROM c "
                    # f"WHERE c.created_at >= '{start_of_today}' "
                    # f"AND c.created_at <= '{end_of_today}' "
                    # "AND c.state != 'pagado'"
                )

                items = []
                feed = self.container.query_items(
                    query=query
                    # enable_cross_partition_query=True
                )

                # Al iterar asíncronamente sobre el resultado, los documentos se agregan a la lista 'items'
                async for item in feed:
                    items.append(item)

                 
                response = {
                    "stats":{
                        "total_orders": len(items),
                        "pending_orders":len(items),
                        "complete_orders":len(items)
                    },
                    "orders":[
                        {
                            "table_id":item["table_id"],
                            "product_name":item["nombre_producto"],
                            "cantidad":item["cantidad"],
                            "created_at":item["created_at"],
                            "updated_at":item["created_at"],
                            "state":item["state"] if "state" in item else "0",
                            "id":item["id"]
                            
                        } for item in items]
                }

                # pdb.set_trace()
                logging.info("Se han obtenido %s pedidos del día actual con estado != 'pagado'.", len(items))
                return response

            except CosmosHttpResponseError as e:
                logging.exception("Error al obtener los pedidos del día actual: %s", e)
                return []

    class AsyncInventoryManager:
        def __init__(self):
            """
            Inicializa la conexión a Cosmos DB para el inventario de restaurantes.
            """
            self.endpoint = settings.db_services.azure_cosmos_db_endpoint
            self.key = settings.db_services.azure_cosmos_db_api_key
            self.database_name = settings.db_services.azure_cosmos_db_name_inventory
            self.container_name = settings.db_services.azure_cosmos_db_container_name_inventory#"inventory"  # Nuevo contenedor

            self.client = CosmosClient(self.endpoint, self.key)
            self.database = self.client.get_database_client(self.database_name)
            self.container = self.database.get_container_client(self.container_name)

            logging.info("Conexión a Cosmos DB establecida. Contenedor: '%s'", self.container_name)

        async def add_product(self, restaurant_id: str, name: str, quantity: int, unit: str, price: float = None):
            """
            Agrega un nuevo producto al inventario.
            """
            product = {
                "id": f"p-{datetime.utcnow().timestamp()}",
                "restaurant_id": restaurant_id,
                "name": name,
                "quantity": quantity,
                "unit": unit,
                "price": price,
                "last_updated": datetime.utcnow().isoformat()
            }
            await self.container.create_item(product)
            logging.info("Producto '%s' agregado al inventario del restaurante %s", name, restaurant_id)
            return product

        async def get_inventory(self, restaurant_id: str):
            """
            Obtiene el inventario de un restaurante.
            """
            query = f"SELECT * FROM c WHERE c.restaurant_id = '{restaurant_id}'"
            items = [item async for item in self.container.query_items(query=query)]
            return items

        async def update_product(self, product_id: str, updated_fields: dict):
            """
            Actualiza la información de un producto en el inventario.
            """
            try:
                product = await self.container.read_item(item=product_id, partition_key=updated_fields.get("restaurant_id"))
                product.update(updated_fields)
                product["last_updated"] = datetime.utcnow().isoformat()

                updated_product = await self.container.replace_item(item=product_id, body=product)
                logging.info("Producto actualizado: %s", product_id)
                return updated_product
            except CosmosResourceNotFoundError:
                logging.warning("Producto no encontrado: %s", product_id)
                return None

        async def delete_product(self, product_id: str, restaurant_id: str):
            """
            Elimina un producto del inventario.
            """
            try:
                await self.container.delete_item(item=product_id, partition_key=restaurant_id)
                logging.info("Producto eliminado: %s", product_id)
                return True
            except CosmosResourceNotFoundError:
                logging.warning("Producto no encontrado: %s", product_id)
                return False


    class CosmosDBClient:
        def __init__(self):
            """
            Inicializa la conexión a Azure Cosmos DB.
            
            :param endpoint: URL del endpoint de Cosmos DB.
            :param key: Clave de autenticación para Cosmos DB.
            :param database_name: Nombre de la base de datos a utilizar.
            :param container_name: Nombre del contenedor a utilizar.
            """
            self.endpoint: str = settings.db_services.azure_cosmos_db_endpoint
            self.key: str = settings.db_services.azure_cosmos_db_api_key
            self.database_name: str = settings.db_services.azure_cosmos_db_name
            self.container_name: str = settings.db_services.azure_cosmos_db_container_name
            self.container_name_message_pairs: str = settings.db_services.azure_cosmos_db_container_name_message_pairs

            try:
                self.client = CosmosClient(self.endpoint, self.key)
                self.database = self.client.get_database_client(self.database_name)
                self.container = self.database.get_container_client(self.container_name)
                self.container_message_pairs=self.database.get_container_client(self.container_name_message_pairs)
                logging.info("Conexión a Cosmos DB establecida correctamente.")
            except CosmosHttpResponseError as e:
                logging.exception("Error al conectar con Cosmos DB: %s", str(e))
                raise

        async def query_documents(self, query: str) -> list[dict]:
            try:
                items = []
                async for item in self.container_message_pairs.query_items(
                    query=query  # <-- Elimina enable_cross_partition_query
                ):
                    items.append(item)
                return items
            except exceptions.CosmosHttpResponseError as e:
                logging.error(f"Error en query_documents: {str(e)}")
                return []

        async def create_document(self, document: dict) -> Optional[dict]:
            
            try:
                created_document = await self.container_message_pairs.create_item(body=document)
                logging.info(f"Documento creado con id: {created_document['id']}")
                return created_document
            except exceptions.CosmosHttpResponseError as e:
                logging.error(f"Error en create_document: {str(e)}")
                return None

        async def get_documents_by_thread_id(self, conversation_id: str) -> List[dict]:
            """
            Recupera todos los documentos que coinciden con el thread_id proporcionado.
            
            :param thread_id: El ID del thread para filtrar los documentos.
            :return: Lista de documentos que coinciden con el thread_id.
            """
            query = "SELECT * FROM c WHERE c.conversation_id = @conversation_id"
            parameters = [
                {"name": "@conversation_id", "value": conversation_id}
            ]

            try:
                items_iterator = self.container_message_pairs.query_items(
                    query=query,
                    parameters=parameters,
                    #enable_cross_partition_query=True
                )

                items = [item async for item in items_iterator]
                logging.info(f"Se recuperaron {len(items)} documentos para conversation_id: {conversation_id}")
                
                # pdb.set_trace()
                response = utils.format_conversation_data(items)
                return response
            except CosmosHttpResponseError as e:
                logging.exception(f"Error al recuperar documentos para conversation_id {conversation_id}: {str(e)}")
                return []

        async def get_user_conversations(self, user_id: str) -> List[dict]:
            """
            Retorna una lista de conversaciones (conversation_id) para un user_id dado,
            junto con la fecha de creación (created_at) del primer mensaje registrado
            en cada conversación.
            """
            # Agregas `c.conversation_name` a la consulta si existe en tu documento
            query = """
                SELECT c.id, c.user_id, c.conversation_id, c.created_at, c.conversation_name
                FROM c
                WHERE c.user_id = @user_id
            """
            parameters = [
                {"name": "@user_id", "value": user_id}
            ]

            try:
                items_iterator = self.container_message_pairs.query_items(
                    query=query,
                    parameters=parameters,
                    #enable_cross_partition_query=True
                )

                items = [item async for item in items_iterator]

                if len(items) == 0:
                    return None
                
                conversations_map = {}
                
                for doc in items:
                    conv_id = doc["conversation_id"]
                    # Usar get para evitar KeyError si no existe la clave
                    conversation_name = doc.get("conversation_name", "Conversación sin nombre definido")
                    doc_created_at = doc["created_at"]  

                    # Mantener el menor (más antiguo) created_at
                    if conv_id not in conversations_map:
                        conversations_map[conv_id] = {
                            "created_at": doc_created_at,
                            "conversation_name": conversation_name
                        }
                    else:
                        if doc_created_at < conversations_map[conv_id]["created_at"]:
                            conversations_map[conv_id]["created_at"] = doc_created_at

                # Convertir a lista
                result = []
                for conv_id, data in conversations_map.items():
                    result.append({
                        "conversation_id": conv_id,
                        "conversation_name": data["conversation_name"],
                        "created_at": data["created_at"]
                    })

                # Ordenar
                result.sort(key=lambda x: x["created_at"])

                return result

            except CosmosHttpResponseError as e:
                logging.exception(f"Error al obtener conversaciones para {user_id}: {str(e)}")
                return []
        
        # def toggle_document_rate(self, document_id: str, partition_key: Optional[str] = None) -> Optional[bool]:
        #     """
        #     Alterna el valor del campo 'rate' de un documento específico.
        #     - Si 'rate' existe y es True, lo cambia a False.
        #     - Si 'rate' existe y es False, lo cambia a True.
        #     - Si 'rate' no existe, lo crea y lo establece en True.
            
        #     :param document_id: El ID del documento a actualizar.
        #     :param partition_key: La clave de partición del documento (si aplica).
        #     :return: El nuevo valor de 'rate' si la actualización fue exitosa, None en caso contrario.
        #     """
        #     try:
                
        #         if partition_key:
        #             document = self.container_message_pairs.read_item(item=document_id, partition_key=partition_key)
        #         else:
        #             # Asumiendo que 'id' es la clave de partición si no se proporciona otra
        #             document = self.container_message_pairs.read_item(item=document_id, partition_key=document_id)
                
        #         # Verificar el state actual de 'rate' y alternarlo
        #         current_rate = document.get('rate', None)
        #         if current_rate is None:
        #             # El campo 'rate' no existe; lo crea y lo establece en True
        #             new_rate = True
        #             logging.info(f"El campo 'rate' no existe en el documento {document_id}. Creándolo y asignando True.")
        #         elif isinstance(current_rate, bool):
        #             # El campo 'rate' existe y es booleano; lo alterna
        #             new_rate = not current_rate
        #             logging.info(f"El campo 'rate' en el documento {document_id} es {current_rate}. Cambiándolo a {new_rate}.")
        #         else:
        #             # El campo 'rate' existe pero no es booleano; lo actualiza a True
        #             new_rate = True
        #             logging.warning(f"El campo 'rate' en el documento {document_id} no es booleano. Actualizándolo a True.")
                
        #         # Asignar el nuevo valor al campo 'rate'
        #         document['rate'] = new_rate
        #         document['updated_at'] = datetime.now().isoformat()
                
        #         # Reemplazar el documento en Cosmos DB
        #         _ = self.container_message_pairs.replace_item(item=document_id, body=document)
        #         logging.info(f"Documento {document_id} actualizado exitosamente con rate={new_rate}.")
        #         return new_rate
        #     except CosmosResourceNotFoundError:
        #         logging.warning(f"Documento con id {document_id} no encontrado.")
        #         return None
        #     except CosmosHttpResponseError as e:
        #         logging.exception(f"Error al actualizar el documento {document_id}: {str(e)}")
        #         return None
        
        async def update_document_rate(
            self,
            document_id: str,
            rate: bool,
            partition_key: Optional[str] = None
        ) -> Optional[bool]:
            """
            Actualiza el valor del campo 'rate' de un documento específico con el booleano proporcionado.

            :param document_id: El ID del documento a actualizar.
            :param rate: Valor booleano que se asignará al campo 'rate'.
            :param partition_key: La clave de partición del documento (si aplica).
            :return: El nuevo valor de 'rate' si la actualización fue exitosa, None en caso contrario.
            """
            try:
                # Leer el documento utilizando la clave de partición apropiada.
                if partition_key:
                    document = await self.container_message_pairs.read_item(
                        item=document_id, 
                        partition_key=partition_key
                    )
                else:
                    # Asumiendo que 'id' es la clave de partición si no se proporciona otra
                    document = await self.container_message_pairs.read_item(
                        item=document_id, 
                        partition_key=document_id
                    )

                # Asignar directamente el parámetro 'rate' al campo 'rate'
                document['rate'] = rate
                # Actualizar el campo 'updated_at' con la fecha/hora actual
                document['updated_at'] = datetime.now().isoformat()

                # Reemplazar el documento en Cosmos DB con los cambios
                await self.container_message_pairs.replace_item(
                    item=document_id,
                    body=document
                )

                logging.info(f"Documento {document_id} actualizado exitosamente con rate={rate}.")
                return rate

            except CosmosResourceNotFoundError:
                logging.warning(f"Documento con id {document_id} no encontrado.")
                return None
            except CosmosHttpResponseError as e:
                logging.exception(f"Error al actualizar el documento {document_id}: {str(e)}")
                return None
    
        # def create_document(self, document: dict) -> Optional[dict]:
        #     """
        #     Crea un nuevo documento en el contenedor.
            
        #     :param document: El documento a crear.
        #     :return: El documento creado si la operación es exitosa, None en caso contrario.
        #     """
        #     try:
        #         created_document = self.container_message_pairs.create_item(body=document)
        #         logging.info(f"Documento creado con id: {created_document['id']}")
        #         return created_document
        #     except CosmosHttpResponseError as e:
        #         logging.exception(f"Error al crear el documento: {str(e)}")
        #         return None

        def delete_document(self, document_id: str, partition_key: Optional[str] = None) -> bool:
            """
            Elimina un documento específico de Cosmos DB.
            
            :param document_id: El ID del documento a eliminar.
            :param partition_key: La clave de partición del documento (si aplica).
            :return: True si la eliminación fue exitosa, False en caso contrario.
            """
            try:
                if partition_key:
                    self.container.delete_item(item=document_id, partition_key=partition_key)
                else:
                    self.container.delete_item(item=document_id, partition_key=document_id)
                logging.info(f"Documento {document_id} eliminado exitosamente.")
                return True
            except exceptions.CosmosResourceNotFoundError:
                logging.warning(f"Documento con id {document_id} no encontrado para eliminar.")
                return False
            except CosmosHttpResponseError as e:
                logging.exception(f"Error al eliminar el documento {document_id}: {str(e)}")
                return False


    class AzureDocumentIntelligence:
        def __init__(self):
            
            api_key: str = settings.ai_services.document_intelligence_key
            api_version: str = settings.ai_services.document_intelligence_api_version
            document_intelligence_endpoint: str = settings.ai_services.document_intelligence_endpoint
            
            self.document_analysis_client = DocumentAnalysisClient(
                                                                    endpoint=document_intelligence_endpoint, 
                                                                    credential=AzureKeyCredential(key=api_key), 
                                                                    apiversion=api_version
            )
            
        def analyze_read(self, file_obj=None):
            """
            Analiza el contenido de un documento PDF proporcionado como un objeto de archivo en memoria.

            param file_obj: Objeto de archivo en memoria para analizar (BytesIO, por ejemplo).
            return: Lista con el texto extraído de cada página.
            """
            if file_obj is None:
                raise ValueError("Debe proporcionarse 'file_obj'.")

            try:
                # Llama al modelo "prebuilt-read" para extraer contenido del archivo PDF
                poller = self.document_analysis_client.begin_analyze_document(
                    "prebuilt-read", document=file_obj
                )
                result = poller.result()
                
                full_content_list = []
                for page in result.pages:
                    # Extrae líneas de texto por página
                    page_text_lines = [line.content for line in page.lines]
                    page_text = ' '.join(page_text_lines)
                    full_content_list.append(page_text)

                return full_content_list

            except Exception as e:
                raise RuntimeError(f"Error al analizar el PDF: {e}")
    

    class DatalakeStorage:
        """
        Clase para conectarse a Azure Data Lake Storage y descargar contenido (por ejemplo, prompts).
        """

        def __init__(self):
            """
            Inicializa la conexión al Data Lake de Azure, tomando las claves del archivo de configuración.
            """
            settings = Settings()
            connection_string: str = settings.AzureServices().azure_datalake_connection_string
            filesystem_name: str = settings.AzureServices().azure_datalake_filesystem_name

            self._service_client: DataLakeServiceClient = DataLakeServiceClient.from_connection_string(
                connection_string
            )
            self._file_system_client = self._service_client.get_file_system_client(
                file_system=filesystem_name
            )

        def download_file_content(self, file_path: str) -> str:
            """
            Descarga y retorna el contenido de un archivo de texto almacenado en el Data Lake.
            """
            print("Downloading file content...")
            file_client = self._file_system_client.get_file_client(file_path)
            download = file_client.download_file()
            content = download.readall()
            return content.decode('utf-8')

        def list_files_in_directory(self, directory_path: str) -> list:
            """
            Lista todos los archivos dentro de un directorio específico en el Data Lake.
            """
            print("Listing files in directory...")
            paths = self._file_system_client.get_paths(path=directory_path)
            files = []
            for path in paths:
                # Verificamos que no sea un directorio
                if not path.is_directory:
                    files.append(path.name)
            return files

        def download_prompts_from_directory(self, directory_path: str) -> dict:
            """
            Descarga el contenido de todos los archivos (por ejemplo, prompts) dentro de un directorio,
            retornando un diccionario donde la clave es el nombre del archivo y el valor es su contenido.
            """
            print("Downloading all prompts from directory...")
            files = self.list_files_in_directory(directory_path)
            prompts = {}
            for file in files:
                content = self.download_file_content(file)
                file_name = file.split('/')[-1]  # Extraemos solo el nombre del archivo
                prompts[file_name] = content
            return prompts

    class AzureAiSearch:
        def __init__(self):
            self.search_endpoint: str = settings.ai_services.azure_search_endpoint
            self.search_key: str = settings.ai_services.azure_search_key
            self.search_credential = AzureKeyCredential(self.search_key)

        async def create_upload_index(self, docs: List[dict] = None, fields: List[SearchField] = None, vector_search: VectorSearch = None, semantic_config: SemanticConfiguration = None, index_name: str = "index_name"):
            async with SearchIndexClient(
                endpoint=self.search_endpoint,
                credential=self.search_credential
            ) as index_client:

                if not fields:
                    fields = [
                        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
                        SearchableField(name="file_name", type=SearchFieldDataType.String, filterable=True),
                        SearchableField(name="page_content", type=SearchFieldDataType.String, filterable=True),
                        SimpleField(name="last_update", type=SearchFieldDataType.DateTimeOffset, filterable=True),
                        SimpleField(name="count_tokens", type=SearchFieldDataType.Int64, filterable=True),
                        SearchField(
                            name="content_vector",
                            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                            searchable=True,
                            vector_search_dimensions=1536,
                            vector_search_profile_name="myHnswProfile",
                        ),
                        SearchField(
                            name="user_id",
                            type=SearchFieldDataType.String,
                            filterable=True
                        ),
                        SearchField(
                            name="conversation_id",
                            type=SearchFieldDataType.String,
                            filterable=True
                        )
                    ]

                if not vector_search:
                    vector_search = VectorSearch(
                        algorithms=[HnswAlgorithmConfiguration(name="myHnsw")],
                        profiles=[
                            VectorSearchProfile(
                                name="myHnswProfile",
                                algorithm_configuration_name="myHnsw"
                            )
                        ],
                    )

                if not semantic_config:
                    semantic_config = SemanticConfiguration(
                        name="my-semantic-config",
                        prioritized_fields=SemanticPrioritizedFields(
                            title_field=SemanticField(field_name="file_name"),
                        ),
                    )

                semantic_search = SemanticSearch(configurations=[semantic_config])

                try:
                    index = SearchIndex(
                        name=index_name,
                        fields=fields,
                        vector_search=vector_search,
                        semantic_search=semantic_search,
                    )

                    result = await index_client.create_or_update_index(index)
                    print(f"Index {result.name} created/updated")
                    logging.info(f"Index {result.name} created/updated")

                    if docs:
                        async with SearchClient(
                            endpoint=self.search_endpoint,
                            index_name=index_name,
                            credential=self.search_credential
                        ) as search_client:
                            resp = await search_client.upload_documents(docs)
                            print(f"Uploaded {len(docs)} documents")
                            logging.info(f"Uploaded {len(docs)} documents")

                except Exception as e:
                    logging.exception("Error al crear o actualizar el índice: %s", str(e))

        async def get_all_document_ids(self, index_name: str, conversation_id: str) -> List[str]:
            try:
                async with SearchClient(
                    endpoint=self.search_endpoint,
                    index_name=index_name,
                    credential=self.search_credential
                ) as search_client:
                    document_ids = []

                    results = await search_client.search(
                        search_text="*",
                        filter=f"conversation_id eq '{conversation_id}'",
                        select="id",
                        top=10000
                    )

                    async for result in results:
                        document_ids.append(result["id"])

                    return document_ids

            except Exception as e:
                logging.warning(f"Error retrieving document IDs from index '{index_name}': {str(e)}")
                return []

        async def process_hash_ids(self, conversation_id, index_name: str, hash_ids_list: List[str]) -> Tuple[List[str], List[str], List[str]]:
            logging.info("Proceso de Indexación Automática Iniciado")

            input_hash_ids = set(hash_ids_list)

            index_created = await self.index_exists(index_name)
            if not index_created:
                logging.warning(f"El índice '{index_name}' no existe en Azure Search.")
                return hash_ids_list, [], []

            existing_hash_ids = set(await self.get_all_document_ids(index_name, conversation_id))

            new_hash_ids = input_hash_ids - existing_hash_ids
            already_existing_hash_ids = list(input_hash_ids & existing_hash_ids)
            to_delete_hashes_ids = list(existing_hash_ids - input_hash_ids)

            return list(new_hash_ids), already_existing_hash_ids, to_delete_hashes_ids

        async def index_exists(self, index_name: str) -> bool:
            async with SearchIndexClient(
                endpoint=self.search_endpoint,
                credential=self.search_credential
            ) as index_client:
                try:
                    await index_client.get_index(index_name)
                    return True
                except ResourceNotFoundError:
                    return False
                except Exception as e:
                    logging.exception(f"Error consultando existencia del índice '{index_name}': {str(e)}")
                    raise
    
        async def delete_documents_by_ids(self, index_name: str, document_ids: List[str]) -> bool:
            async with SearchClient(
                endpoint=self.search_endpoint,
                index_name=index_name,
                credential=self.search_credential
            ) as search_client:

                documents_to_delete = [{"id": doc_id} for doc_id in document_ids]

                try:
                    result = await search_client.delete_documents(documents=documents_to_delete)
                    return True if result else False
                except Exception as e:
                    logging.exception(f"Error al eliminar documentos: {str(e)}")
                    return False
                
        async def search_documents_in_index(self, index_name: str, search_text: str, conversation_id: str) -> List[dict]:
            """
            Realiza una búsqueda en un índice de Azure Cognitive Search y devuelve los documentos encontrados.

            :param index_name: Nombre del índice a consultar.
            :param search_text: Texto de búsqueda.
            :param conversation_id: ID de la conversación.
            :return: Lista de diccionarios con los resultados de la búsqueda.
            """
            # search_client = SearchClient(
            #     endpoint=self.search_endpoint,
            #     index_name=index_name,
            #     credential=self.search_credential
            # )
            documents = []
            async with SearchClient(
                endpoint=self.search_endpoint,
                index_name=index_name,
                credential=self.search_credential
            ) as search_client:
                
                results = await search_client.search(search_text=search_text, filter=f"conversation_id eq '{conversation_id}'", top=6, select=['file_name', 'page_content'])
                
                async for result in results:
                    documents.append(result)
            

            logging.info(f"Se encontraron {len(documents)} documentos en la búsqueda.")
            return documents
    class PdfProcessor:
        def __init__(self):
            self.document_intelligence_service = AzureServices.AzureDocumentIntelligence()
            self.azure_ai_search_service =  AzureServices.AzureAiSearch()
            self.azure_openai_service =  AzureServices.AzureOpenAI()
            
        async def main(self, user_id,conversation_id, files_obj:list=None):
            """
            Analiza el contenido de un documento PDF proporcionado como un objeto de archivo en memoria.

            param file_obj: Objeto de archivo en memoria para analizar (BytesIO, por ejemplo).
            return: Lista con el texto extraído de cada página.
            """
            
            if files_obj is None:
                raise ValueError("Debe proporcionarse 'file_obj'.")

            read_files = []
            unread_files = []
            for file in files_obj:
                
                if file.get("doc_type") in ["pdf"]:
                    
                    extracted_content = self.document_intelligence_service.analyze_read(file_obj=file.get("content"))
                else:
                    extracted_content = file.get("content")
                
                response_message = f"Archivo {file.get('file_name')} procesado correctamente" if extracted_content else f"No se pudo extraer el contenido del archivo {file.get('file_name')}"
                if extracted_content:
                    read_files.append({
                        "file_name": file.get("file_name"),
                        "message": response_message,
                        "content": extracted_content
                    })
                else:
                    unread_files.append({
                        "file_name": file.get("file_name"),
                        "message": response_message
                    })
            text_content = [res.get("content") for res in read_files]
            
            # Identificar Cantidad de Tokens del texto
            encoder = tiktoken.get_encoding("cl100k_base")
            count_tokens=len(encoder.encode(str(text_content)))
            max_tokens_input_model = 0
            
            if count_tokens > max_tokens_input_model:
                # Si es demasiado "grande" para ser procesada por el llm:    
                ## Chunkear 
                chunks = self.chunk_extracted_texts(user_id=user_id,extracted_files=read_files)
                
                ## Validar qué documentos son nuevos y cuáles ya están en el indice o deben eliminarse?
                hash_ids_list = [doc.metadata.get("id") for doc in chunks]
                new_hash_ids, already_existing_hash_ids, to_delete_hashes_ids = await self.azure_ai_search_service.process_hash_ids(conversation_id=conversation_id, index_name="geo-gpk", hash_ids_list=hash_ids_list)
                index_info = {
                    "num_added": len(new_hash_ids),
                    "num_skipped": len(already_existing_hash_ids),
                    "num_deleted": len(to_delete_hashes_ids)
                    }
                print(f"\033[32mResultado esperado del proceso de verificacion de hashes:\n{index_info}\033[0m")
                docs = [doc if doc.metadata.get("id") in new_hash_ids else None for doc in chunks]
                
                if len(to_delete_hashes_ids) > 0:
                    asyncio.create_task(self.azure_ai_search_service.delete_documents_by_ids(index_name="geo-gpk", document_ids=to_delete_hashes_ids))
                if len(docs)>0:
                    ldocs = [
                            {
                                "id":doc.metadata.get("id"),
                                "user_id": user_id,
                                "conversation_id":conversation_id,
                                "file_name":doc.metadata.get("file_name"),
                                "page_content":doc.page_content,
                                "content_vector": self.azure_openai_service.model_embeddings.embed_query(doc.page_content),
                                "last_update": datetime.now(),
                                "count_tokens": len(encoder.encode(doc.page_content))
                            } for doc in docs if doc is not None
                        ]
                else:
                    ldocs = []
                
                _ = await self.azure_ai_search_service.create_upload_index(docs=ldocs, index_name="geo-gpk")
                # asyncio.create_task(self.azure_ai_search_service.create_upload_index(docs=ldocs, index_name="geo-gpk"))
            else:
                # Si es lo suficientemente "pequeña" para ser procesada por el llm:    
                ## Insertar en prompt directamente para reducir tiempos ¿?
                pass
                
            response = {
                "user_id": user_id,
                "read_files": [
                                {
                                "file_name":res.get("file_name"),
                                "message":res.get("message")
                                } for res in read_files
                               ],
                "unread_files": [res.get("file_name") for res in unread_files]
            }
            return text_content , response
        
        def chunk_extracted_texts(
            self,
            user_id:str,
            extracted_files: list, 
            chunk_size: int = 5000, 
            chunk_overlap: int = 200
        ) -> list:
            """
            Recibe la lista de diccionarios con 'file_name' y 'content' (que es 
            una lista de textos por cada página), combina el texto y lo divide
            en chunks usando un TextSplitter de LangChain.
            
            :param extracted_files: lista de diccionarios con la forma:
                [
                    {
                        "file_name": "archivo.pdf",
                        "content": ["texto página 1", "texto página 2", ...]
                    },
                    ...
                ]
            :param chunk_size: tamaño máximo de cada chunk (en caracteres)
            :param chunk_overlap: solapamiento entre chunks
            :return: lista de objetos Document de langchain con el texto chunked 
                    y metadatos (file_name).
            """
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size, 
                chunk_overlap=chunk_overlap
            )
            
            splitted_docs = []
            
            for file_info in extracted_files:
                file_name = file_info.get("file_name")
                # 'content' es una lista de strings (cada string es el texto de una página).
                # Si deseas combinarlas, por ejemplo, en un solo string:
                combined_text = "\n".join(file_info.get("content", []))
                
                # Creamos los documentos troceados
                docs = text_splitter.create_documents(
                    texts=[combined_text], 
                    # Si quieres meter metadatos, por ejemplo, el nombre del archivo:
                    metadatas=[{"file_name": file_name}]
                )
                for i in range(len(docs)):
                    string_to_hash = f"{user_id}-{docs[i].page_content.encode()}"
                    docs[i].metadata["id"] = hashlib.sha256(string_to_hash.encode()).hexdigest()
                    
                splitted_docs.extend(docs)
            
            return splitted_docs
        
    def __init__(self):
        self.service_azure_open_ai = AzureServices.AzureOpenAI()


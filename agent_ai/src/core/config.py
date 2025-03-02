from dotenv import load_dotenv, find_dotenv
import os

load_dotenv(find_dotenv())

class Settings():
    class AzureServices():
        def __init__(self):
            self.azure_openai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY")
            self.openai_api_version: str = os.getenv("OPENAI_API_VERSION")
            self.azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT")
            self.model_gpt4o_name: str = os.getenv("MODEL_GPT4o_NAME")
            self.model_embeddings_name: str = os.getenv("EMBEDDING_NAME")
            self.azure_search_endpoint: str = os.getenv("AZURE_AI_SEARCH_ENDPOINT")
            self.azure_search_key: str = os.getenv("AZURE_AI_SEARCH_API_KEY")
            self.document_intelligence_endpoint: str = os.getenv("AZURE_FORM_RECOGNIZER_ENDPOINT")
            self.document_intelligence_key: str = os.getenv("AZURE_FORM_RECOGNIZER_API_KEY")
            self.document_intelligence_api_version: str = os.getenv("AZURE_FORM_RECOGNIZER_API_VERSION")
            self.tavily_api_key: str = os.getenv("TAVILY_API_KEY")

    class DBServices:
        """
        Clase para gestionar las configuraciones y claves necesarias para 
        los servicios de Azure utilizados en la aplicación:
        - Azure Cosmos DB
        - Azure Blob Storage
        - Azure Data Lake Storage
        """

        def __init__(self):
            # Claves y configuración de Azure Cosmos DB
            self.azure_cosmos_db_api_key = os.getenv("AZURE_COSMOSDB_KEY")
            self.azure_cosmos_db_endpoint = os.getenv("AZURE_COSMOSDB_ENDPOINT")
            self.azure_cosmos_db_name = os.getenv("AZURE_COSMOSDB_NAME")
            self.azure_cosmos_db_name_inventory = os.getenv("AZURE_COSMOSDB_NAME_INVENTORY")
            self.azure_cosmos_db_container_name_inventory = os.getenv("AZURE_COSMOSDB_CONTAINER_NAME_INVENTORY")
            self.azure_cosmos_db_container_name = os.getenv("AZURE_COSMOSDB_CONTAINER_NAME_ORDERS")
            self.azure_cosmos_db_container_name_message_pairs = os.getenv("AZURE_COSMOSDB_CONTAINER_NAME_MESSAGE_PAIRS")
            
            # Claves y configuración de Azure Blob Storage
            self.azure_blob_storage_connection_string = os.getenv("AZURE_BLOB_STORAGE_CONNECTION_STRING")
            self.azure_blob_storage_container_name = os.getenv("AZURE_BLOB_STORAGE_CONTAINER_NAME")
            
            # Claves y configuración de Azure Data Lake Storage
            self.azure_datalake_connection_string = os.getenv("AZURE_DATALAKE_CONNECTION_STRING")
            self.azure_datalake_filesystem_name = os.getenv("AZURE_DATALAKE_FILESYSTEM_NAME")
            
    def __init__(self):
        self.app_name: str = "CHAT GPK"
        self.admin_email: str = "admin@example.com"
        self.ai_services: Settings.AzureServices = Settings.AzureServices()
        self.db_services: Settings.DBServices = Settings.DBServices()

settings = Settings()
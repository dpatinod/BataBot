import pdb
import json
import os
import logging
from typing import Any, Optional, List, Dict, cast

import nest_asyncio
nest_asyncio.apply()

from langchain_core.tools import tool
from core.schema_services import AzureServices
from core.config import settings


# Crear una única instancia de AzureServices y extraer los servicios necesarios
azure_services = AzureServices()
ai_search_service = azure_services.AzureAiSearch()
blob_service = azure_services.BlobStorage()

async_order_manager = azure_services.AsyncOrderManager()
async_inventory_manager = azure_services.AsyncInventoryManager()




async def get_menu_tool(restaurant_name: str = "Macciato") -> List[Dict[str, Any]]:
    """
    Obtiene el menú del restaurante en formato Excel.

    :param restaurant_name: Nombre del restaurante a consultar.
    :return: Lista de diccionarios con la información del menú.
    """
    results = await async_inventory_manager.get_inventory(restaurant_name)
    results_list = [res for res in results]

    # Mostrar el resultado formateado en JSON
    print(json.dumps(results_list, indent=4))
    print("\033[92mget_menu_tool activada\033[0m")
    return cast(List[Dict[str, Any]], results)



async def confirm_order_tool(
    nombre_producto: str,
    cantidad: int,
    observaciones: str,
    table_id: str,
    user_name: Optional[str]
) -> Optional[str]:
    """
    Realiza un pedido de un producto y lo guarda en Cosmos DB.

    :param nombre_producto: Nombre del producto a pedir.
    :param cantidad: Cantidad del producto.
    :param observaciones: Observaciones adicionales del pedido.
    :return: Mensaje de confirmación o None en caso de error.
    """

    print(
        f"\033[92mconfirm_order_tool activada\n"
        f"nombre_producto: {nombre_producto}\n"
        f"cantidad: {cantidad}\n"
        f"observaciones: {observaciones}\033[0m"
    )
    state = "default"
    order = {
        "nombre_producto": nombre_producto,
        "cantidad": cantidad,
        "observaciones": observaciones,
        "state":state,
        "table_id":table_id,
        "user_name":user_name
    }
    
    try:
        created_order = await async_order_manager.create_order(order)
        if created_order is not None:
            return "Pedido realizado con éxito"
        else:
            return "Error al realizar el pedido"
    except Exception as e:
        logging.exception("Error al confirmar el pedido: %s", e)
        return None

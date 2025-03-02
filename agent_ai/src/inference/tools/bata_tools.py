import json
from typing import Any, Optional, cast
import pdb
import aiohttp
from typing import Optional, Literal

from langchain_community.tools.tavily_search import TavilySearchResults
from scrapegraphai.graphs import SmartScraperGraph, SmartScraperMultiGraph,SearchGraph
from langchain_core.tools import tool
from core.schema_services import AzureServices
from dotenv import load_dotenv
# Importa tu settings con la clave ya cargada
from core.config import settings
import os

import nest_asyncio
nest_asyncio.apply()

# Resto de tu código


openai_key = os.getenv("OPENAI_APIKEY")
ai_search_service = AzureServices().AzureAiSearch()

async def search_tool(query: str) -> Optional[list[dict[str, Any]]]:
    """
    Query a search engine (TavilySearchResults) usando la key de config.
    """
    print(f"\033[92msearch_tool activada | query: {query}\033[0m")
    wrapped = TavilySearchResults(
        max_results=5,
        tavily_api_key=settings.ai_services.tavily_api_key  
    )
    result = await wrapped.ainvoke({"query": query})
    return cast(list[dict[str, Any]], result)


async def retrieval_tool(query: str, conversation_id:str ) -> Optional[list[dict[str, Any]]]:
    """
    Hace
    """
    print(f"\033[92mretrieval_tool activada | query: {query}\033[0m")

    documents = await ai_search_service.search_documents_in_index(
        index_name="geo-gpk",
        search_text=query,
        conversation_id=conversation_id
    )
    print(f"\033[92m{len(documents)} Documentos Recuperados\033[0m")
    if len(documents) == 0:
        return []
    
    docs = [
        {"file_name": d["file_name"], "page_content": d["page_content"]}
        for d in documents
    ]


    return cast(list[dict[str, Any]], docs)

def scrape_tool(
                query: str,
                gender:Literal["mujer","hombre","niño","niña"],
                category:Literal["ofertas","tendencia","zapatos","accesorios"]
                ) -> Optional[list[dict[str, Any]]]:
    """
    Hace
    """
    print(f"\033[92mscrape_tool activada | query: {query} | gender: {gender} | category: {category}\033[0m")


    graph_config = {
                    "llm": {
                        "api_key":openai_key,
                        "model": "openai/gpt-4o-mini",
                        "max_tokens":10000
                    },
                    "verbose": True,
                    "headless": False
                    }

    url_data =    {
                        "main_url": "https://www.bata.com/co/",
                        "url": {
                            "mujer":{
                                # "mujer":"https://www.bata.com/co/mujer/",
                                "ofertas":"https://www.bata.com/co/ofertas/mujer/",
                                "tendencia":"https://www.bata.com/co/nuevo/mujer/",
                                "zapatos":"https://www.bata.com/co/mujer/zapatos/",
                                "accesorios":"https://www.bata.com/co/mujer/accesorios/"
                            },
                            "hombre":{
                                "ofertas":"https://www.bata.com/co/ofertas/hombre/",
                                "tendencia":"https://www.bata.com/co/nuevo/hombre/",
                                "zapatos":"https://www.bata.com/co/hombre/zapatos/",
                                "accesorios":"https://www.bata.com/co/hombre/accesorios/"
                            },
                            "niño":{
                                "ofertas":"https://www.bata.com/co/ofertas/ni%C3%B1os/",
                                "tendencia":"https://www.bata.com/co/nuevo/infantil/",
                                "zapatos":"https://www.bata.com/co/infantil/ni%C3%B1o/zapatos/",
                                "accesorios":"https://www.bata.com/co/infantil/ni%C3%B1o/"     
                            },
                            "niña":{
                                "ofertas":"https://www.bata.com/co/ofertas/ni%C3%B1os/",
                                "tendencia":"https://www.bata.com/co/nuevo/infantil/",
                                "zapatos":"https://www.bata.com/co/infantil/ni%C3%B1a/zapatos/",
                                "accesorios":"https://www.bata.com/co/infantil/ni%C3%B1a/accesorios/"     
                            }
                        }
                    }
    

    source = url_data.get('url').get(gender).get(category)

    smart_scraper_graph = SmartScraperGraph(
        prompt=f"Extrae información de los productos como nombre, talla, color, precio, link y más caracteristicas en relación a la query: {query} ",
        source=source,
        config=graph_config
    )

    # Run the pipeline
    result = smart_scraper_graph.run()

    
    print(json.dumps(result, indent=4))
        
    return cast(list[dict[str, Any]], result)


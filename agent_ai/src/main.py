# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.chat import chat_router, pdf_chat_agent 
from api.chat_agent import chat_agent_router
from api.inventory_router import inventory_router
# from api import auth
from fastapi.staticfiles import StaticFiles
app = FastAPI(title="TARS Agents Graphs")

# Configura CORS para permitir peticiones del frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar routers
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
app.include_router(chat_agent_router, prefix="/api/agent/chat", tags=["RestaurantsAgents"])
app.include_router(inventory_router, prefix="/api/inventory/stock", tags=["StockRestaurants"])
# app.include_router(auth.router, prefix="/api/auth", tags=["auth"])

# app.mount("/", StaticFiles(directory="./dist", html=True), name="static")
# app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")

# Evento de inicio
@app.on_event("startup")
async def startup_event():
    """
    Se llama una sola vez al iniciar la app.
    Puedes inicializar variables globales aquí si fuera necesario
    o delegar a un módulo de dependencias.
    """
    print("Aplicación iniciada")
    #return await pdf_chat_agent.checkpointer_async.setup()  
    # O directamente:
    # await pdf_chat_agent.app.checkpointer.setup()

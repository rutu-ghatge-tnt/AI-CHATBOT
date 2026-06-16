from motor.motor_asyncio import AsyncIOMotorClient

from app.config import DB_NAME, MONGO_URI

# Dedicated HL engine Mongo client sourced directly from .env config.
hl_mongo_client = AsyncIOMotorClient(
    MONGO_URI,
    serverSelectionTimeoutMS=30000,
    connectTimeoutMS=20000,
    socketTimeoutMS=60000,
    maxPoolSize=30,
    minPoolSize=3,
    retryWrites=True,
    retryReads=True,
)

hl_db = hl_mongo_client[DB_NAME]

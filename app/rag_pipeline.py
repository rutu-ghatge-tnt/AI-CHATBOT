from app.config import CHROMA_DB_PATH
from langchain.vectorstores import Chroma
from langchain.embeddings import SentenceTransformerEmbeddings
from langchain.chains import RetrievalQA
from app.llm_claude import get_claude_llm

def get_rag_chain():
    db = Chroma(
        persist_directory=CHROMA_DB_PATH,
        embedding_function=SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
    )
    retriever = db.as_retriever(search_type="similarity", search_kwargs={"k": 3})
    return RetrievalQA.from_chain_type(
        llm=get_claude_llm(),
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=True
    )

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from app.config import CHROMA_DB_PATH

def verify_embeddings():
    print(f"Loading Chroma vectorstore from: {CHROMA_DB_PATH}")
    
    # Initialize the same embedding model you used during ingestion
    embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    
    # Load the vectorstore with the embedding function
    vectorstore = Chroma(persist_directory=CHROMA_DB_PATH, embedding_function=embedding_model)
    
    # Perform a similarity search with an empty query to fetch top k documents (adjust k as needed)
    retrieved_docs = vectorstore.similarity_search("", k=5)
    
    print(f"Retrieved {len(retrieved_docs)} documents/chunks from vectorstore:")
    for i, doc in enumerate(retrieved_docs):
        print(f"\nDocument {i + 1}:")
        print(f"Metadata: {doc.metadata}")
        print(f"Content preview: {doc.page_content[:200]}...")  # preview first 200 chars

if __name__ == "__main__":
    verify_embeddings()

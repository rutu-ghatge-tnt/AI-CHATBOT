#app/rag_pipeline
from app.config import CHROMA_DB_PATH
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from app.llm_claude import get_claude_llm

def get_rag_chain():
    # Initialize the vector database with sentence embeddings
    vector_db = Chroma(
        persist_directory=CHROMA_DB_PATH,
        embedding_function=HuggingFaceEmbeddings(model_name="sentence-transformers/all-mpnet-base-v2")

    )

    # Configure retriever with top-k similarity search
    retriever = vector_db.as_retriever(
        search_type="mmr",  # more diverse context
        search_kwargs={"k": 8, "fetch_k": 12}  # higher fetch_k ensures better context
    )


    # Prompt template used by the Claude model
    prompt_template = PromptTemplate.from_template(
        """
        You are SkinSage, a friendly skincare assistant with expert knowledge of skincare ingredients, products, and routines.

        Your task is to answer user questions based on the provided context. You should:
        - Use the most relevant information from the context to provide accurate and helpful answers
        When answering the user's question:
        - Identify any skincare-related abbreviations or slang (e.g., HA, AHA, BHA, Vit C, Niac, Ret, Sal)
        - Automatically expand those terms to their full scientific names (e.g., HA → Hyaluronic Acid)
        - Use the expanded version to match the context for the most relevant answer
        - If something is ambiguous, interpret it in a helpful way, or kindly ask for clarification
        - Pay attention to price information like MRP and selling price when answering.
        - If the context doesn't provide enough information, politely inform the user and suggest they ask a skincare-related question.
        - If the question is off-topic, kindly say something helpful like:
          "I'm not sure about that, but I'd be happy to help with anything skincare-related!"
        - If the question is about your identity, respond with:
          "Welcome to SkinBB Metaverse! I'm SkinSage, your wise virtual skincare assistant
     
        Answer accurately using the most relevant information from the provided context below.

        Context:
        {context}

        User Question:
        {question}

        If the context doesn't help or the question is off-topic, kindly say something helpful like:
        "I'm not sure about that, but I'd be happy to help with anything skincare-related!"

        Your response:
        """
    )


    # Build and return the RetrievalQA chain
    return RetrievalQA.from_chain_type(
        llm=get_claude_llm(),
        chain_type="stuff",
        retriever=retriever,
        chain_type_kwargs={"prompt": prompt_template},
        return_source_documents=True
    )
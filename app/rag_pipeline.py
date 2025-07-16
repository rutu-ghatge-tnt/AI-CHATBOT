from app.config import CHROMA_DB_PATH
from langchain.vectorstores import Chroma
from langchain.embeddings import SentenceTransformerEmbeddings
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from app.llm_claude import get_claude_llm

def get_rag_chain():
    db = Chroma(
        persist_directory=CHROMA_DB_PATH,
        embedding_function=SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
    )

    retriever = db.as_retriever(search_type="similarity", search_kwargs={"k": 4})

    # Custom prompt with structured, friendly fallback
    prompt_template = PromptTemplate.from_template(
        """
You are SkinBB, a friendly skincare assistant with expert knowledge of ingredients, routines, and product usage.
Answer the question using the most relevant facts from the provided context.

Context:
{context}

User Question:
{question}

If the context doesn't help or the question is off-topic, kindly say something helpful like:
"I'm not sure about that, but I’d be happy to help with anything skincare-related!"

Your response:
"""
    )

    return RetrievalQA.from_chain_type(
        llm=get_claude_llm(),
        chain_type="stuff",
        retriever=retriever,
        chain_type_kwargs={"prompt": prompt_template},
        return_source_documents=True
    )

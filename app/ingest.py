# app/ingest.py
import os
from pathlib import Path
from tqdm import tqdm
from rich import print as rprint
import traceback

from app.config import CHROMA_DB_PATH
from app.utils import extract_text
from app.embedd_manifest import load_manifest, save_manifest

# LangChain setup
os.environ["LANGCHAIN_ENDPOINT"] = "none"

from langchain_community.vectorstores import Chroma
from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings


def ingest_documents():
    folder = Path("data/raw_documents")
    if not folder.exists():
        rprint("[red]❌ Folder data/raw_documents does not exist.[/]")
        return

    files = list(folder.glob("*"))
    if not files:
        rprint("[red]❌ No files found in data/raw_documents/[/]")
        return

    rprint(f"[bold blue]📂 Found {len(files)} files in data/raw_documents/[/]")

    embedded_files = load_manifest()
    rprint(f"[yellow]📜 Previously embedded: {len(embedded_files)} files[/]")

    docs = []
    newly_embedded_files = set()
    total_chars = 0

    rprint("\n[bold white]📄 Processing documents...[/]")

    for f in tqdm(files, desc="Reading and chunking files"):
        if f.name in embedded_files:
            rprint(f"[dim]⏭️ Skipping {f.name} — already embedded.[/]")
            continue

        try:
            text = extract_text(f)
            if not text.strip():
                rprint(f"[yellow]⚠️ Skipping {f.name} — empty or unreadable.[/]")
                continue

            total_chars += len(text)
            splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
            chunks = splitter.split_text(text)

            for chunk in chunks:
                docs.append(Document(page_content=chunk, metadata={"source": f.name}))

            newly_embedded_files.add(f.name)
            rprint(f"[green]📄 {f.name} — {len(chunks)} chunks | {len(text)} chars[/]")

        except Exception as e:
            rprint(f"[red]❌ Error processing {f.name}: {e}[/]")
            traceback.print_exc()

    if not docs:
        rprint("[red]❌ No new documents to embed.[/]")
        return

    rprint(f"\n✅ Total characters processed: {total_chars}")
    rprint(f"✅ Total new chunks to embed: {len(docs)}")

    # Load embedding model
    rprint("\n[bold]🔗 Loading embedding model...[/]")
    embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

    rprint("[yellow]💡 Creating embeddings...[/]")
    texts = [doc.page_content for doc in docs]
    embeddings = []
    batch_size = 100

    for i in tqdm(range(0, len(texts), batch_size), desc="Embedding chunks"):
        batch = texts[i:i + batch_size]
        batch_embeddings = embedding_model.embed_documents(batch)
        embeddings.extend(batch_embeddings)

    # Reattach embeddings to documents
    for i, emb in enumerate(embeddings):
        docs[i].metadata["embedding"] = emb  # Optional for debugging

    # Load existing vectorstore if present
    rprint("\n[bold cyan]💾 Saving to Chroma vectorstore...[/]")
    vectorstore = Chroma(persist_directory=CHROMA_DB_PATH, embedding_function=embedding_model)

    try:
        vectorstore.add_documents(docs)
        vectorstore.persist()
        rprint(f"✅ Saved {len(docs)} chunks to ChromaDB at: [green]{CHROMA_DB_PATH}[/]")
    except Exception as e:
        rprint(f"[red]❌ Failed to save to Chroma: {e}[/]")
        return

    embedded_files.update(newly_embedded_files)
    save_manifest(embedded_files)
    rprint(f"[bold green]📝 Updated embed manifest with {len(newly_embedded_files)} new files.[/]")


if __name__ == "__main__":
    ingest_documents()

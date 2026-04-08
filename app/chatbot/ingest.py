# app/chatbot/ingest.py
"""Ingest and embed documents into ChromaDB vectorstore"""
import hashlib
import json
import os
from pathlib import Path
from tqdm import tqdm
from rich import print as rprint
import traceback
import pandas as pd
from app.config import CHROMA_DB_PATH
from app.chatbot.utils import extract_text
from app.chatbot.embedd_manifest import load_manifest, save_manifest
from app.chatbot.mongo_ingest import fetch_mongo_rag_documents, purge_mongo_logical_from_chroma

# LangChain setup
os.environ["LANGCHAIN_ENDPOINT"] = "none"

from langchain_chroma import Chroma
try:
    from langchain.docstore.document import Document
    from langchain.text_splitter import RecursiveCharacterTextSplitter
except ImportError:
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings

# Lives alongside other ingest sources under data/raw_documents/
SYSTEM_KNOWLEDGE_JSON = "system_knowledge_chunks.json"
LEGACY_SK_MANIFEST_PREFIX = "system_knowledge:chunks.json@"


def _chunk_metadata_for_chroma(meta: dict) -> dict:
    """Chroma accepts str, int, float, bool — coerce the rest."""
    out = {}
    for k, v in (meta or {}).items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        else:
            out[k] = str(v)
    return out


def ingest_documents():
    embedded_files = load_manifest()
    rprint(f"[yellow]📜 Previously embedded manifest keys: {len(embedded_files)}[/]")

    docs = []
    newly_embedded_files = set()
    total_chars = 0
    mongo_purge: list = []

    folder = Path("data/raw_documents")
    files = list(folder.glob("*")) if folder.exists() else []
    if not folder.exists():
        rprint("[yellow]⚠️ data/raw_documents does not exist — skipping raw file ingest.[/]")
    elif not files:
        rprint("[yellow]⚠️ No files in data/raw_documents/ — skipping raw file ingest.[/]")
    else:
        rprint(f"[bold blue]📂 Found {len(files)} files in data/raw_documents/[/]")

    rprint("\n[bold white]📄 Processing raw documents...[/]")

    for f in tqdm(files, desc="Reading and chunking files"):
        if f.name == SYSTEM_KNOWLEDGE_JSON:
            raw = f.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            sk_key = f"{SYSTEM_KNOWLEDGE_JSON}@{digest}"
            sk_prefix = f"{SYSTEM_KNOWLEDGE_JSON}@"
            if sk_key in embedded_files:
                rprint(f"[dim]⏭️ Skipping {f.name} — unchanged (hash in manifest).[/]")
                continue
            try:
                payload = json.loads(raw.decode("utf-8"))
                sk_chunks = payload.get("chunks", [])
                for item in sk_chunks:
                    text = (item.get("text") or "").strip()
                    if not text:
                        continue
                    base_meta = {
                        "source": "system_knowledge",
                        "chunk_id": item.get("id", ""),
                    }
                    base_meta.update(_chunk_metadata_for_chroma(item.get("metadata") or {}))
                    docs.append(Document(page_content=text, metadata=base_meta))
                embedded_files = {
                    k
                    for k in embedded_files
                    if not (
                        (isinstance(k, str) and k.startswith(sk_prefix))
                        or (isinstance(k, str) and k.startswith(LEGACY_SK_MANIFEST_PREFIX))
                    )
                }
                newly_embedded_files.add(sk_key)
                rprint(f"[green]🧠 {f.name} — {len(sk_chunks)} platform knowledge chunks (new hash).[/]")
            except Exception as e:
                rprint(f"[red]❌ Failed to load {f.name}: {e}[/]")
                traceback.print_exc()
            continue

        if f.name in embedded_files:
            rprint(f"[dim]⏭️ Skipping {f.name} — already embedded.[/]")
            continue

        if f.suffix == ".xlsx":
            try:
                df = pd.read_excel(f)
                df.columns = [col.strip().lower().replace(" ", "_") for col in df.columns]
                
                for i, row in df.iterrows():
                    product_text = f"""
                    Product Name: {row.get('product_name', '')}
                    Brand: {row.get('brand_name', '')}
                    Key Ingredients: {row.get('key_ingredients', '')}
                    All Ingredients: {row.get('all_ingredients', '')}
                    MRP: ₹{row.get('mrp', '')}
                    Description: {row.get('product_description', '')}
                    Features & Benefits: {row.get('key_features_&_benefits', '')}
                    How To Use: {row.get('how_to_use', '')}
                    About Brand: {row.get('about_the_brand', '')}
                    Age Suitability: {row.get('age', '')}
                    Skin Type: {row.get('skin_type', '')}
                    Hair Type: {row.get('hair_type', '')}
                    Skin Tone: {row.get('skin_tone', '')}
                    SPF: {row.get('spf', '')}
                    Super Ingredients: {row.get('super_ingredients', '')}
                    Benefits: {row.get('benefits', '')}
                    Fragrance Family: {row.get('fragrance_family', '')}
                    Makeup Finish: {row.get('make_up_finish', '')}
                    Dimensions: {row.get('dimensions', '')}
                    Imported By: {row.get('imported_by', '')}
                    """

                    docs.append(Document(page_content=product_text.strip(), metadata={"source": f.name}))
                
                newly_embedded_files.add(f.name)
                rprint(f"[green]📘 {f.name} — embedded {len(df)} Excel rows[/]")
                continue  # Skip default chunking/extract for Excel

            except Exception as e:
                rprint(f"[red]❌ Failed to process Excel file {f.name}: {e}[/]")
                traceback.print_exc()
                continue

        try:
            text = extract_text(f)
            if not text.strip():
                rprint(f"[yellow]⚠️ Skipping {f.name} — empty or unreadable.[/]")
                continue

            total_chars += len(text)
            splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=400)
            chunks = splitter.split_text(text)

            for chunk in chunks:
                docs.append(Document(page_content=chunk, metadata={"source": f.name}))

            newly_embedded_files.add(f.name)
            rprint(f"[green]📄 {f.name} — {len(chunks)} chunks | {len(text)} chars[/]")

        except Exception as e:
            rprint(f"[red]❌ Error processing {f.name}: {e}[/]")
            traceback.print_exc()

    try:
        mongo_docs, mongo_new_keys, mongo_purge, embedded_files = fetch_mongo_rag_documents(embedded_files)
        if mongo_docs:
            docs.extend(mongo_docs)
            embedded_files.update(mongo_new_keys)
            mc = sum(len(d.page_content) for d in mongo_docs)
            total_chars += mc
            rprint(f"[green]🍃 MongoDB — {len(mongo_docs)} chunks, {mc} chars[/]")
    except Exception as e:
        rprint(f"[yellow]⚠️ Mongo ingest error (continuing without Mongo): {e}[/]")
        traceback.print_exc()
        mongo_purge = []

    if not docs:
        rprint("[red]❌ No new documents to embed.[/]")
        return

    rprint(f"\n✅ Total characters processed: {total_chars}")
    rprint(f"✅ Total new chunks to embed: {len(docs)}")

    # Load embedding model
    rprint("\n[bold]🔗 Loading embedding model...[/]")
    embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-mpnet-base-v2"
    )


    rprint("[yellow]💡 Creating embeddings...[/]")
    texts = [doc.page_content for doc in docs]
    batch_size = 100

    # embeddings are created here but not directly used; can be omitted if unnecessary
    for i in tqdm(range(0, len(texts), batch_size), desc="Embedding chunks"):
        batch = texts[i:i + batch_size]
        _ = embedding_model.embed_documents(batch)  # call to warm up or generate embeddings if needed

    # Remove any existing 'embedding' from metadata to avoid Chroma errors
    for doc in docs:
        if "embedding" in doc.metadata:
            del doc.metadata["embedding"]

    # Save documents to Chroma vectorstore
    rprint(f"\n[bold cyan]💾 Saving to Chroma vectorstore at: {Path(CHROMA_DB_PATH).resolve()}[/]")
    try:
        vectorstore = Chroma(
            persist_directory=CHROMA_DB_PATH,
            embedding_function=embedding_model
        )

        purge_mongo_logical_from_chroma(vectorstore, mongo_purge)

        for i in tqdm(range(0, len(docs), batch_size), desc="Saving to vectorstore"):
            batch_docs = docs[i:i + batch_size]
            vectorstore.add_documents(batch_docs)

        # No explicit persist() call needed — auto-persist enabled by persist_directory
        rprint(f"✅ Saved {len(docs)} chunks to ChromaDB.")
    except Exception as e:
        rprint(f"[red]❌ Failed to save to Chroma: {e}[/]")
        return

    # Print vector count
    try:
        count = vectorstore._collection.count()
        rprint(f"ℹ️ Vectorstore now contains {count} vectors.")
    except Exception as e:
        rprint(f"[yellow]⚠️ Could not get vectorstore count: {e}[/]")

    # Update manifest file with newly embedded files
    embedded_files.update(newly_embedded_files)
    save_manifest(embedded_files)
    rprint(f"[bold green]📝 Updated embed manifest with {len(newly_embedded_files)} new files.[/]")


if __name__ == "__main__":
    ingest_documents()

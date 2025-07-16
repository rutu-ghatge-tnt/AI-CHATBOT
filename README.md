


Create Virtual Environment
```bash
python -m venv venv
```


Activate Environment

```bash
.\venv\Scripts\activate
```


Install packages
```bash
pip install -r requirements.txt
```

Run Embedding
```bash 
python -m app.ingest.py
```

Run Server python

```bash
uvicorn app.main:app --reload
```
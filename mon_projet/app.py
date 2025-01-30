from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Prospect(BaseModel):
    name: str
    email: str
    message: str

@app.get("/")
def read_root():
    return {"message": "API de Prospects - En attente de requêtes"}

@app.post("/add_prospect/")
def add_prospect(prospect: Prospect):
    # Ici tu pourras ajouter le code pour insérer un prospect dans ta base de données
    return {"message": f"Prospect {prospect.name} ajouté"}


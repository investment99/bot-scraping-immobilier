from flask import Flask, request, jsonify
import pdfplumber
import openai
import requests
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv
import tempfile
import json
import hashlib  # Pour le hash du PDF

load_dotenv()

app = Flask(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

cache = {}  # Dictionnaire pour le cache

def extract_relevant_info(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            info = {}
            for page in pdf.pages:
                text = page.extract_text()
                # Extraction des infos clés (à adapter à vos PDFs)
                # Exemple:
                if "Type de bien" in text:
                    info["type_de_bien"] = text.split("Type de bien:")[1].split("\n")[0].strip()
                if "Budget" in text:
                    budget_str = text.split("Budget:")[1].split("\n")[0].strip()
                    try:
                        budget = int(budget_str.replace(" ", "")) # Supprimer espaces
                        info["budget_min"] = budget * 0.9 # Marge de 10%
                        info["budget_max"] = budget * 1.1
                    except ValueError:
                        pass  # Gérer le cas où le budget n'est pas un nombre
                if "Localisation" in text:
                    info["localisation"] = text.split("Localisation:")[1].split("\n")[0].strip()
                # ... extraire d'autres infos pertinentes
            return info
    except Exception as e:
        print(f"Erreur extraction PDF: {e}")
        return None

def analyze_report(pdf_hash, infos):
    if pdf_hash in cache:
        return cache[pdf_hash]

    prompt = f"""
    Analyse les critères de recherche suivants et renvoie-les au format JSON :
    {json.dumps(infos)}
    """
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",  # Ou un modèle moins coûteux
            messages=[
                {"role": "system", "content": "You are a helpful real estate report analyzer."},
                {"role": "user", "content": prompt},
            ]
        )
        result = response.choices[0].message.content.strip()
        try:
            criteria = json.loads(result)
            cache[pdf_hash] = criteria  # Ajoute au cache
            return criteria
        except json.JSONDecodeError as e:
            print(f"Erreur JSON: {e}, Resultat OpenAI: {result}")
            return None
    except Exception as e:
        print(f"Erreur OpenAI: {e}")
        return None


# ... (scrape_leboncoin inchangé)

@app.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if not file.filename.endswith('.pdf'):
        return jsonify({"error": "Invalid file type"}), 400

    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            file_path = tmp.name
            file.save(tmp)

        with open(file_path, "rb") as f: # Hashage du PDF
            file_hash = hashlib.md5(f.read()).hexdigest()

        relevant_info = extract_relevant_info(file_path)
        if not relevant_info:
            return jsonify({"error": "Erreur lors de l'extraction des infos du PDF"}), 500

        criteria = analyze_report(file_hash, relevant_info)
        if not criteria:
            return jsonify({"error": "Erreur lors de l'analyse du rapport"}), 500

        results = scrape_leboncoin(criteria, limit=5)

        return jsonify({"criteria": criteria, "results": results}), 200

    except Exception as e:
        print(f"Erreur générale: {e}")
        return jsonify({"error": "An error occurred during PDF processing: " + str(e)}), 500

    finally:
        os.remove(file_path)

# ... (route / et app.run inchangés)

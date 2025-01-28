from flask import Flask, request, jsonify
import pdfplumber
import openai
import requests
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv
import tempfile
import json

load_dotenv()

app = Flask(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# ... (fonctions extract_text_from_pdf et scrape_leboncoin inchangées)

def analyze_report(text):
    prompt = f"Voici un rapport immobilier :\n{text}\n\nIdentifie les critères de recherche (localisation, budget, type de bien, surface, etc.) et renvoie-les au format JSON. Utilise les clés 'location', 'budget_min', 'budget_max', 'type', 'surface_min', 'surface_max', etc."
    response = openai.Completion.create(
        engine="text-davinci-003",
        prompt=prompt,
        max_tokens=500
    )
    return response.choices[0].text.strip()

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

        text = extract_text_from_pdf(file_path)

        criteria_text = analyze_report(text)

        try:
            criteria = json.loads(criteria_text)
        except json.JSONDecodeError as e:
            print(f"Erreur lors du décodage JSON des critères : {e}")
            return jsonify({"error": "Failed to decode JSON criteria from OpenAI response: " + str(e)}), 500

        results = scrape_leboncoin(criteria)

        return jsonify({"criteria": criteria, "results": results}), 200 # Code 200 OK explicite

    except Exception as e:
        print(f"Erreur lors du traitement du PDF : {e}")
        return jsonify({"error": "An error occurred during PDF processing: " + str(e)}), 500

    finally:
        os.remove(file_path) # Supprimer le fichier temporaire (même en cas d'erreur)


@app.route('/')
def home():
    return "API Flask fonctionne correctement !"

if __name__ == "__main__":
    app.run(debug=True, port=5000)

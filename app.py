from flask import Flask, request, jsonify
import pdfplumber
import openai
import requests
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

app = Flask(__name__)

# Récupérer la clé API OpenAI depuis les variables d'environnement
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

def extract_text_from_pdf(pdf_path):
    """Extraire le texte d'un fichier PDF."""
    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

def analyze_report(text):
    """Analyser le texte pour extraire les critères de recherche."""
    prompt = f"Voici un rapport immobilier :\n{text}\n\nIdentifie les critères de recherche : localisation, budget, type de bien, surface, etc."
    response = openai.Completion.create(
        engine="text-davinci-003",
        prompt=prompt,
        max_tokens=500
    )
    return response.choices[0].text.strip()

def scrape_leboncoin(criteria):
    """Scraper les annonces sur Leboncoin en fonction des critères."""
    url = "https://www.leboncoin.fr/recherche"
    params = {
        "category": "ventes_immobilieres",
        "location": criteria.get("location", ""),
        "price_min": criteria.get("budget_min", ""),
        "price_max": criteria.get("budget_max", ""),
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        for ad in soup.find_all("div", class_="aditem-container"):
            title = ad.find("a", class_="aditem-title").text.strip()
            price = ad.find("span", class_="item-price").text.strip()
            link = ad.find("a")["href"]
            results.append({"title": title, "price": price, "link": link})
        return results
    except Exception as e:
        return [{"error": str(e)}]

@@app.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    print("Requête POST reçue sur /upload_pdf")
    if 'file' not in request.files:
        print("Aucun fichier reçu")
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if not file.filename.endswith('.pdf'):
        print("Type de fichier invalide")
        return jsonify({"error": "Invalid file type"}), 400

    file_path = os.path.join("uploads", file.filename)
    os.makedirs("uploads", exist_ok=True)
    file.save(file_path)
    print(f"Fichier enregistré à {file_path}")

    # Extraction du texte du PDF
    text = extract_text_from_pdf(file_path)
    print("Texte extrait du PDF")

    # Analyse des critères via OpenAI
    criteria_text = analyze_report(text)
    print("Critères analysés via OpenAI")

    try:
        # Convertir les critères en dictionnaire Python
        criteria = eval(criteria_text)
    except Exception as e:
        print(f"Erreur lors de l'analyse des critères : {e}")
        return jsonify({"error": "Failed to parse criteria from OpenAI response"}), 500

    # Scraper les annonces immobilières
    results = scrape_leboncoin(criteria)
    print("Scraping terminé")

    # Retourner les résultats
    return jsonify({"criteria": criteria, "results": results})

@app.route('/')
def home():
    return "API Flask fonctionne correctement !"

if __name__ == "__main__":
    app.run(debug=True, port=5000)

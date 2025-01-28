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

def extract_text_from_pdf(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

def analyze_report(text):
    prompt = f"Voici un rapport immobilier :\n{text}\n\nIdentifie les critères de recherche (localisation, budget, type de bien, surface, etc.) et renvoie-les au format JSON. Utilise les clés 'location', 'budget_min', 'budget_max', 'type', 'surface_min', 'surface_max', etc."
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful real estate report analyzer."},
            {"role": "user", "content": prompt},
        ]
    )
    return response.choices[0].message.content.strip()

def scrape_leboncoin(criteria):
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
        for ad in soup.find_all("div", class_="aditem-container"):  # Adaptez la classe si nécessaire
            title = ad.find("a", class_="aditem-title").text.strip()  # Adaptez la classe si nécessaire
            price = ad.find("span", class_="item-price").text.strip()  # Adaptez la classe si nécessaire
            link = ad.find("a")["href"]  # Adaptez la classe si nécessaire
            results.append({"title": title, "price": price, "link": link})
        return results
    except requests.exceptions.RequestException as e: # Gestion plus précise des erreurs
        return [{"error": str(e)}]
    except AttributeError as e: # Gestion du cas où les éléments ne sont pas trouvés
        return [{"error": "Éléments non trouvés sur la page (Leboncoin a peut-être changé son code): " + str(e)}]


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

        return jsonify({"criteria": criteria, "results": results}), 200

    except Exception as e:
        print(f"Erreur lors du traitement du PDF : {e}")
        return jsonify({"error": "An error occurred during PDF processing: " + str(e)}), 500

    finally:
        os.remove(file_path)

@app.route('/')
def home():
    return "API Flask fonctionne correctement !"

if __name__ == "__main__":
    app.run(debug=True, port=5000)

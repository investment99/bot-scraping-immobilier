from flask import Flask, request, jsonify
import pdfplumber
import openai
import requests
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv
import tempfile
import json
import hashlib
import re
import time

load_dotenv()

app = Flask(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

cache = {}

def extract_info(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                print("Erreur: PDF vide")
                return None

            info = {}
            for i, page in enumerate(pdf.pages):
                if i < 4:
                    continue

                text = page.extract_text()
                if text:
                    match = re.search(r"Type de bien\s*:\s*(.*)", text)
                    if match:
                        info["type_de_bien"] = match.group(1).strip()

                    match = re.search(r"superficie habitable de\s*(\d+)\s*m²", text, re.IGNORECASE)
                    if match:
                        info["superficie"] = int(match.group(1))

                    match = re.search(r"(centre-ville|Promenade des Anglais)", text, re.IGNORECASE)
                    if match:
                        info["localisation"] = match.group(1).strip()
                    elif "centre-ville" in text.lower() or "Promenade des Anglais" in text.lower():
                        if "centre-ville" in text.lower():
                            info["localisation"] = "centre-ville"
                        else:
                            info["localisation"] = "Promenade des Anglais"

                    match = re.search(r"budget idéal de\s*([\d\s]+)\s*EUR", text, re.IGNORECASE)
                    if match:
                        budget_str = match.group(1).replace(" ", "")
                        try:
                            info["budget"] = int(budget_str)
                        except ValueError:
                            print("Erreur: Budget non trouvé ou mal formaté")

            return info

    except Exception as e:
        print(f"Erreur générale lors de l'extraction PDF: {e}")
        return None

def analyze_report(pdf_hash, infos):
    if pdf_hash in cache:
        return cache[pdf_hash]

    prompt = f"""
    Analyse les critères de recherche suivants et renvoie-les au format JSON:
    {json.dumps(infos)}
    """
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful real estate report analyzer."},
                {"role": "user", "content": prompt},
            ]
        )
        result = response.choices[0].message.content.strip()
        try:
            criteria = json.loads(result)
            cache[pdf_hash] = criteria
            return criteria
        except json.JSONDecodeError as e:
            print(f"Erreur JSON: {e}, Resultat OpenAI: {result}")
            return None
    except Exception as e:
        print(f"Erreur OpenAI: {e}")
        return None

def scrape_leboncoin(criteria, limit=5):
    url = "https://www.leboncoin.fr/recherche"
    params = {
        "category": "ventes_immobilieres",
        "location": criteria.get("location", ""),
        "price_min": criteria.get("budget_min", ""),
        "price_max": criteria.get("budget_max", ""),
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()  # Important pour détecter les erreurs HTTP (403, etc.)

        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        for i, ad in enumerate(soup.find_all("div", class_="aditem-container")):
            if i >= limit:
                break
            title = ad.find("a", class_="aditem-title").text.strip()
            price = ad.find("span", class_="item-price").text.strip()
            link = ad.find("a")["href"]
            results.append({"title": title, "price": price, "link": link})

        if not results:
            return [{"error": "Aucune annonce trouvée"}]

        time.sleep(2)  # Délai entre les requêtes
        return results

    except requests.exceptions.RequestException as e:
        print(f"Erreur scraping: {e}")
        return [{"error": str(e)}]  # Retourne l'erreur pour l'afficher dans l'application
    except AttributeError as e:
        return [{"error": "Éléments non trouvés sur la page (Leboncoin a peut-être changé son code): " + str(e)}]
    except Exception as e:
        print(f"Erreur scraping générale: {e}")
        return [{"error": "Erreur inconnue lors du scraping"}]


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

        with open(file_path, "rb") as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        relevant_info = extract_info(file_path)
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

@app.route('/')
def home():
    return "API Flask fonctionne correctement !"

if __name__ == "__main__":
    app.run(debug=True, port=5000)

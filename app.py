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
import random
from urllib.parse import quote
import traceback  # Pour afficher les traces d'erreurs

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
                if i < 4:  # Commence à la page 5 (index 4)
                    continue

                text = page.extract_text()
                if text:
                    # Extraction "Type de bien"
                    match = re.search(r"Type de bien\s*:\s*(.*)", text)
                    if match:
                        info["type_de_bien"] = match.group(1).strip()

                    # Extraction "superficie habitable de X m²"
                    match = re.search(r"superficie habitable de\s*(\d+)\s*m²", text, re.IGNORECASE)
                    if match:
                        info["superficie"] = int(match.group(1))

                    # Extraction localisation (ex : "centre-ville", "Promenade des Anglais")
                    match = re.search(r"(centre-ville|Promenade des Anglais)", text, re.IGNORECASE)
                    if match:
                        info["localisation"] = match.group(1).strip()
                    elif "centre-ville" in text.lower() or "promenade des anglais" in text.lower():
                        info["localisation"] = "centre-ville" if "centre-ville" in text.lower() else "Promenade des Anglais"

                    # Extraction budget idéal
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
            print(f"Erreur JSON: {e}, Résultat OpenAI: {result}")
            return None

    except Exception as e:
        print(f"Erreur OpenAI: {e}")
        return None


# ----------------------------------------------------------------
# BLOC B (inchangé) : parse_price_to_int + scrape_annonces
# ----------------------------------------------------------------
def parse_price_to_int(price_str):
    try:
        cleaned = (price_str
                   .replace("€", "")
                   .replace(",", "")
                   .replace(" ", "")
                   .strip())
        return int(cleaned)
    except:
        return None

def scrape_annonces(criteria, limit=5):
    """
    Scrape plusieurs sites en fonction des 'sources' fournies dans 'criteria'.
    Ex: criteria["sources"] = "bienici, century21"
    """
    annonces = []

    # --- Century 21 : ex. page "trouver_logement/resultat/?transaction=acheter&ville=Nice"
    if "century21" in criteria.get("sources", "").lower():
        try:
            # Exemple d'URL de recherche sur Century21 (à adapter selon la ville / code postal)
            url_century21 = (
                "https://www.century21.fr/trouver_logement/resultat/"
                "?transaction=acheter&ville=Nice"
            )
            response_century21 = requests.get(url_century21)
            response_century21.raise_for_status()
            soup_century21 = BeautifulSoup(response_century21.content, "html.parser")

            # Exemple de sélecteurs (fictifs) à adapter
            # Recherchez la vraie structure via F12 -> Inspecter sur la page
            for annonce_century21 in soup_century21.find_all("div", class_="annonce-item"):
                title_el = annonce_century21.find("h2", class_="annonce-title")
                price_el = annonce_century21.find("span", class_="annonce-price")
                link_el = annonce_century21.find("a", class_="annonce-link")

                if title_el and price_el and link_el and link_el.has_attr("href"):
                    annonces.append({
                        "title": title_el.get_text(strip=True),
                        "price": price_el.get_text(strip=True),
                        "link": "https://www.century21.fr" + link_el["href"],
                        "source": "Century21"
                    })

        except requests.exceptions.RequestException as e:
            print(f"Erreur scraping Century 21 (requête): {e}")
            traceback.print_exc()
        except AttributeError as e:
            print(f"Erreur parsing Century 21: {e}")
            traceback.print_exc()

    # --- Bien'ici : on interroge DIRECTEMENT l'API JSON (pas le HTML)
    if "bienici" in criteria.get("sources", "").lower():
        try:
            # On construit un "filters_payload" : on peut y inclure surface/budget s'il faut.
            # Voici un exemple simplifié : on suppose code postal = "06000" (Nice)
            # ou on peut coder la "localisation" en param.
            budget_min = criteria.get("budget_min", 0)
            budget_max = criteria.get("budget_max", 999999999)
            surface_min = criteria.get("surface_min", 0)
            surface_max = criteria.get("surface_max", 9999)

            filters_payload = {
                "size": 24,
                "from": 0,
                "filters": {
                    "category": {"value": "buy"},  # "buy" pour vente
                    "locations": [
                        {
                            "type": "city",
                            "postalCode": "06000"  # ex. Nice
                        }
                    ],
                    "price": {
                        "min": int(budget_min),
                        "max": int(budget_max)
                    },
                    "livingArea": {
                        "min": int(surface_min),
                        "max": int(surface_max)
                    }
                }
            }

            base_url = "https://api.bienici.com/api/v1/realEstateAds"
            params = {
                "filters": json.dumps(filters_payload)
            }
            headers = {"User-Agent": "Mozilla/5.0"}

            resp = requests.get(base_url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            ads = data.get("realEstateAds", [])
            for ad in ads:
                title = ad.get("title", "N/A")
                p_obj = ad.get("price", {})
                price_value = p_obj.get("value", "N/A")

                # Lien d'annonce (id ?)
                ad_id = ad.get("id", "")
                link = f"https://www.bienici.com/annonce/{ad_id}"

                annonces.append({
                    "title": str(title),
                    "price": str(price_value),
                    "link": link,
                    "source": "Bienici"
                })

        except requests.exceptions.RequestException as e:
            print(f"Erreur scraping Bien'ici (requête): {e}")
            traceback.print_exc()
        except AttributeError as e:
            print(f"Erreur parsing Bien'ici: {e}")
            traceback.print_exc()

    if not annonces:
        return [{"error": "Aucune annonce trouvée sur les sites spécifiés"}]

    # ----------------------
    # Filtrage local
    # ----------------------
    filtered = []
    bmin = criteria.get("budget_min")
    bmax = criteria.get("budget_max")

    for a in annonces:
        p = parse_price_to_int(a.get("price", ""))
        if p is not None and bmin is not None and bmax is not None:
            if p < bmin or p > bmax:
                continue
        filtered.append(a)

    if not filtered:
        return [{"error": "Aucune annonce ne correspond aux critères élargis"}]

    return filtered[:limit]


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

        # Élargir les critères (BLOC A inchangé)
        if "superficie" in criteria:
            surf = criteria["superficie"]
            criteria["surface_min"] = max(0, surf - 10)
            criteria["surface_max"] = surf + 20

        if "budget" in criteria:
            budg = criteria["budget"]
            criteria["budget_min"] = budg
            criteria["budget_max"] = budg + 200000

        if "sources" not in criteria:
            criteria["sources"] = "bienici, century21"

        results = scrape_annonces(criteria, limit=5)

        return jsonify({"criteria": criteria, "results": results}), 200

    except Exception as e:
        print(f"Erreur générale: {e}")
        traceback.print_exc()
        return jsonify({"error": "An error occurred during PDF processing: " + str(e)}), 500

    finally:
        os.remove(file_path)

@app.route('/')
def home():
    return "API Flask fonctionne correctement !"

if __name__ == "__main__":
    app.run(debug=True, port=5000)

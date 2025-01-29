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

    # --- Century 21 ---
    if "century21" in criteria.get("sources", "").lower():
        try:
            # NOUVELLE URL
            url_century21 = "https://www.century21.fr/annonces/f/achat/v-nice/d-06_alpes_maritimes/?cible=d-06_alpes_maritimes"
            response_century21 = requests.get(url_century21)
            response_century21.raise_for_status()

            soup_century21 = BeautifulSoup(response_century21.content, "html.parser")

            # On cible <div class="c-the-property-thumbnail-with-content__col-right">
            blocks = soup_century21.find_all("div", class_="c-the-property-thumbnail-with-content__col-right")

            for block in blocks:
                # Récupération du bloc "NICE 06, 315 m², 10 pièces, etc."
                info_el = block.find("div", class_="c-text-theme-heading-4")
                info_text = info_el.get_text(strip=True) if info_el else ""

                surface, pieces = None, None
                match_surface_pieces = re.search(r"(\d+)\s*m².*?(\d+)\s*pièces", info_text)
                if match_surface_pieces:
                    surface = int(match_surface_pieces.group(1))
                    pieces = int(match_surface_pieces.group(2))

                # Type de bien : "Maison à vendre" (c-text-theme-heading-3)
                type_el = block.find("div", class_="c-text-theme-heading-3")
                property_type = type_el.get_text(strip=True) if type_el else None

                # Prix : dans c-text-theme-heading-1
                price_el = block.find("div", class_="c-text-theme-heading-1")
                price = price_el.get_text(strip=True) if price_el else None

                # Lien : <a class="c-the-button" href="...">
                link_el = block.find("a", class_="c-the-button")
                link = None
                if link_el and link_el.has_attr("href"):
                    link = link_el["href"]
                    if link.startswith("/"):
                        link = "https://www.century21.fr" + link

                annonces.append({
                    "info_complet": info_text,
                    "surface": surface,
                    "pieces": pieces,
                    "type_de_bien": property_type,
                    "price": price,
                    "link": link
                })

        except requests.exceptions.RequestException as e:
            print(f"Erreur scraping Century 21 (requête): {e}")
            traceback.print_exc()
        except AttributeError as e:
            print(f"Erreur parsing Century 21: {e}")
            traceback.print_exc()

    # --- Bien'ici (reste inchangé) ---
    if "bienici" in criteria.get("sources", "").lower():
        try:
            url_bienici = "https://www.bienici.com/recherche/location/appartement/nice"  # Exemple d'URL, à adapter
            response_bienici = requests.get(url_bienici)
            response_bienici.raise_for_status()
            soup_bienici = BeautifulSoup(response_bienici.content, "html.parser")

            for annonce_bienici in soup_bienici.find_all("a", class_="search-result-card"):
                title_bienici = annonce_bienici.find("h2")
                price_bienici = annonce_bienici.find("span", class_="price")
                link_bienici = annonce_bienici.get("href")

                if title_bienici and price_bienici and link_bienici:
                    annonces.append({
                        "title": title_bienici.text.strip(),
                        "price": price_bienici.text.strip(),
                        "link": "https://www.bienici.com" + link_bienici,
                        "source": "Bien'ici"
                    })
        except requests.exceptions.RequestException as e:
            print(f"Erreur scraping Bien'ici (requête): {e}")
            traceback.print_exc()
        except AttributeError as e:
            print(f"Erreur parsing Bien'ici: {e}")
            traceback.print_exc()

    if not annonces:
        return [{"error": "Aucune annonce trouvée sur les sites spécifiés"}]

    # Filtrage local final (inchangé)
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

        # Élargir
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

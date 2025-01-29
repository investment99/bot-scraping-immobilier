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
        cleaned = (
            price_str
            .replace("€", "")
            .replace(",", "")
            .replace(" ", "")
            .strip()
        )
        return int(cleaned)
    except:
        return None

def scrape_annonces(criteria, limit=5):
    """
    Scrape UNIQUEMENT sur la route :
    https://www.century21.fr/annonces/f/achat-appartement/v-nice/tri-prix-desc/page-{page_num}/?cible=d-06_alpes_maritimes
    
    On ajoute un User-Agent plus “classique” pour éviter d’être bloqué.
    """
    annonces = []

    # On suppose que "century21" est dans criteria["sources"]
    if "century21" in criteria.get("sources", "").lower():
        try:
            # Si la ville n'est pas "nice", vous pouvez l'adapter
            ville = criteria.get("ville", "nice")

            # On tente 3 pages
            max_pages = 3
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/108.0.0.0 Safari/537.36"
                )
            }

            for page_num in range(1, max_pages + 1):
                url_century21 = (
                    f"https://www.century21.fr/annonces/f/achat-appartement/v-{ville}/tri-prix-desc/"
                    f"page-{page_num}/?cible=d-06_alpes_maritimes"
                )
                print("Scraping:", url_century21)

                resp_c21 = requests.get(url_century21, headers=headers)
                if resp_c21.status_code in [404, 410]:
                    break
                resp_c21.raise_for_status()

                soup_c21 = BeautifulSoup(resp_c21.text, "html.parser")

                # On recherche les blocs d'annonces
                blocks = soup_c21.find_all("div", class_="c-the-property-thumbnail-with-content")
                print(f"Nombre de blocks trouvés (page {page_num}):", len(blocks))

                if not blocks:
                    break  # plus de pages ?

                # Pour chaque annonce, extraire l'info
                for block in blocks:
                    right_part = block.find("div", class_="c-the-property-thumbnail-with-content__col-right")
                    if not right_part:
                        continue

                    zone_info_el = right_part.find("div", class_="c-text-theme-heading-4")
                    zone_info_text = zone_info_el.get_text(strip=True) if zone_info_el else ""

                    surface, pieces = None, None
                    match_sp = re.search(r"(\d+)\s*m².*?(\d+)\s*pièces", zone_info_text)
                    if match_sp:
                        surface = int(match_sp.group(1))
                        pieces = int(match_sp.group(2))

                    type_el = right_part.find("div", class_="c-text-theme-heading-3")
                    property_type = type_el.get_text(strip=True) if type_el else None

                    price_el = right_part.find("div", class_="c-text-theme-heading-1")
                    price = price_el.get_text(strip=True) if price_el else None

                    link_el = right_part.find("a", class_="c-the-button")
                    link = None
                    if link_el and link_el.has_attr("href"):
                        link = link_el["href"]
                        if link.startswith("/"):
                            link = "https://www.century21.fr" + link

                    desc_el = right_part.find("div", class_="c-text-theme-base")
                    description = desc_el.get_text(strip=True) if desc_el else None

                    annonces.append({
                        "info_complet": zone_info_text,
                        "surface": surface,
                        "pieces": pieces,
                        "type_de_bien": property_type,
                        "price": price,
                        "link": link,
                        "description": description,
                        "source": "Century21"
                    })

        except requests.exceptions.RequestException as e:
            print(f"Erreur scraping Century 21 (requête): {e}")
            traceback.print_exc()
        except AttributeError as e:
            print(f"Erreur parsing Century 21: {e}")
            traceback.print_exc()

    if not annonces:
        return [{"error": "Aucune annonce trouvée sur Century21"}]

    # Filtrage local final (ex: budget_min, budget_max)
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

        # Ex: élargir la surface
        if "superficie" in criteria:
            surf = criteria["superficie"]
            criteria["surface_min"] = max(0, surf - 10)
            criteria["surface_max"] = surf + 20

        # Ex: élargir le budget
        if "budget" in criteria:
            budg = criteria["budget"]
            criteria["budget_min"] = budg
            criteria["budget_max"] = budg + 200000

        # si "sources" n'est pas dans criteria => on force
        if "sources" not in criteria:
            criteria["sources"] = "century21"

        # si "ville" pas présent => fallback "nice"
        if "ville" not in criteria:
            criteria["ville"] = "nice"

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

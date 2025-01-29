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
                    # Extraction "Type de bien"
                    match = re.search(r"Type de bien\s*:\s*(.*)", text)
                    if match:
                        info["type_de_bien"] = match.group(1).strip()

                    # Extraction "superficie habitable de X m²"
                    match = re.search(r"superficie habitable de\s*(\d+)\s*m²", text, re.IGNORECASE)
                    if match:
                        info["superficie"] = int(match.group(1))

                    # Extraction localisation
                    match = re.search(r"(centre-ville|Promenade des Anglais)", text, re.IGNORECASE)
                    if match:
                        info["localisation"] = match.group(1).strip()
                    elif "centre-ville" in text.lower() or "promenade des anglais" in text.lower():
                        if "centre-ville" in text.lower():
                            info["localisation"] = "centre-ville"
                        else:
                            info["localisation"] = "Promenade des Anglais"

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
    # On conserve la même logique de cache
    if pdf_hash in cache:
        return cache[pdf_hash]

    prompt = f"""
    Analyse les critères de recherche suivants et renvoie-les au format JSON:
    {json.dumps(infos)}
    """

    try:
        # On garde openai.Chat.create (nouvelle API)
        response = openai.Chat.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful real estate report analyzer."},
                {"role": "user", "content": prompt},
            ]
        )
        result = response.choices[0].message["content"].strip()
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


# -----------------------------------------------------------------------------------
# SCRAPERS (remplacement de l'ancien scrape_leboncoin par 4 scrapers + agrégateur)
# -----------------------------------------------------------------------------------

def scrape_bienici(criteria, limit=5):
    """
    Scraper (ou appel API) de Bien'ici, exemple JSON + param filters.
    À adapter selon la structure réelle actuelle.
    """
    results = []
    try:
        budget_max = criteria.get("budget", 400000)
        surface_min = criteria.get("superficie", 40)
        postcode = criteria.get("localisation", "75001")

        filters_payload = {
            "size": 24,
            "from": 0,
            "filters": {
                "category": {"value": "buy"},
                "locations": [
                    {
                        "type": "city",
                        "postalCode": str(postcode)
                    }
                ],
                "price": {"max": int(budget_max)},
                "livingArea": {"min": int(surface_min)}
            }
        }

        base_url = "https://api.bienici.com/api/v1/realEstateAds"
        params = {"filters": json.dumps(filters_payload)}
        headers = {"User-Agent": "Mozilla/5.0"}

        resp = requests.get(base_url, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        ads = data.get("realEstateAds", [])
        for i, ad in enumerate(ads):
            if i >= limit:
                break
            title = ad.get("title", "N/A")
            price = ad.get("price", {}).get("value", "N/A")
            link = "https://www.bienici.com/annonce/" + str(ad.get("id", ""))
            results.append({
                "site": "Bienici",
                "title": title,
                "price": price,
                "link": link
            })

        time.sleep(random.uniform(2, 4))

    except Exception as e:
        print(f"Erreur scraping Bienici: {e}")
        results.append({"error": f"Bienici: {str(e)}"})
    return results


def scrape_century21(criteria, limit=5):
    """
    Scraper HTML sur Century21.fr, exemple GET avec params (transaction=, ville=, etc.)
    """
    results = []
    try:
        base_url = "https://www.century21.fr/trouver_logement/resultat/"
        ville = criteria.get("localisation", "paris")
        budget_max = criteria.get("budget", 300000)
        surface_min = criteria.get("superficie", 40)

        params = {
            "transaction": "acheter",
            "ville": ville,
            "prix_max": budget_max,
            "surface_min": surface_min
        }
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(base_url, params=params, headers=headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        annonces = soup.find_all("div", class_="annonce-item")
        for i, annonce in enumerate(annonces):
            if i >= limit:
                break

            title_el = annonce.find("h2", class_="annonce-title")
            price_el = annonce.find("span", class_="annonce-price")
            link_el = annonce.find("a", class_="annonce-link")

            title = title_el.get_text(strip=True) if title_el else "N/A"
            price = price_el.get_text(strip=True) if price_el else "N/A"
            link = link_el["href"] if (link_el and link_el.has_attr("href")) else "#"

            results.append({
                "site": "Century21",
                "title": title,
                "price": price,
                "link": link
            })

        time.sleep(random.uniform(2, 4))

    except Exception as e:
        print(f"Erreur scraping Century21: {e}")
        results.append({"error": f"Century21: {str(e)}"})
    return results


def scrape_seloger(criteria, limit=5):
    """
    Exemple d'API SeLoger (endpoint fictif, à adapter).
    """
    results = []
    try:
        base_url = "https://api-seloger.com/api/v1/listings/search"
        budget_max = criteria.get("budget", 300000)
        surface_min = criteria.get("superficie", 40)
        ville = criteria.get("localisation", "75001")  # code postal ?

        payload = {
            "pageIndex": 1,
            "pageSize": limit,
            "realtyTypes": [1, 2],
            "transactionType": 2,  # 2 = vente
            "price": {"max": budget_max},
            "livingArea": {"min": surface_min},
            "zipCodes": [ville]
        }
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json"
        }
        r = requests.post(base_url, headers=headers, data=json.dumps(payload))
        r.raise_for_status()
        data = r.json()

        items = data.get("items", [])
        for item in items:
            title = item.get("title", "N/A")
            price = item.get("price", {}).get("amount", "N/A")
            link = item.get("permalink", "#")

            results.append({
                "site": "SeLoger",
                "title": title,
                "price": price,
                "link": link
            })

        time.sleep(random.uniform(2, 4))

    except Exception as e:
        print(f"Erreur scraping SeLoger: {e}")
        results.append({"error": f"SeLoger: {str(e)}"})
    return results


def scrape_pap(criteria, limit=5):
    """
    Scraper HTML sur PAP.fr, exemple URL slug /vente-appartements-paris-75-g439
    """
    results = []
    try:
        base_url = "https://www.pap.fr/annonce/vente-appartements"
        ville = criteria.get("localisation", "paris").lower().replace(" ", "-")
        # Simplification: pour Paris => '-75-g439', pour Nice => '-06-g21067', etc.
        slug = f"{ville}-75-g439"
        url = f"{base_url}-{slug}"

        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        annonces = soup.find_all("div", class_="search-list-item")
        count = 0
        for annonce in annonces:
            if count >= limit:
                break
            title_el = annonce.find("h3", class_="item-title")
            price_el = annonce.find("h4", class_="item-price")
            link_el = annonce.find("a", class_="item-title")

            if title_el and price_el and link_el:
                title = title_el.get_text(strip=True)
                price = price_el.get_text(strip=True)
                link = link_el["href"]
                if link.startswith("/"):
                    link = "https://www.pap.fr" + link

                results.append({
                    "site": "PAP",
                    "title": title,
                    "price": price,
                    "link": link
                })
                count += 1

        time.sleep(random.uniform(2, 4))

    except Exception as e:
        print(f"Erreur scraping PAP: {e}")
        results.append({"error": f"PAP: {str(e)}"})
    return results


def scrape_all_sites(criteria, limit=5):
    """
    Regroupe les 4 scrapers dans une seule fonction.
    """
    results = []
    results.extend(scrape_bienici(criteria, limit))
    results.extend(scrape_century21(criteria, limit))
    results.extend(scrape_seloger(criteria, limit))
    results.extend(scrape_pap(criteria, limit))
    return results


# -----------------------------------------------------------------------------------
# ROUTES FLASK
# -----------------------------------------------------------------------------------

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

        # Appel de la nouvelle fonction: on scrape Bienici, Century21, SeLoger, PAP
        results = scrape_all_sites(criteria, limit=5)

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

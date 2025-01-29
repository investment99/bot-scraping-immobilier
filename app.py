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
from urllib.parse import quote  # Importez quote

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

def scrape_annonces(criteria, limit=5):
    annonces = []

    # --- Century 21 ---
    if "century21" in criteria.get("sources", "").lower():
        try:
            url_century21 = "https://www.century21.fr/annonces/vente-maison-nice-06000/"  # Example URL, adapt as needed
            response_century21 = requests.get(url_century21)
            response_century21.raise_for_status()
            soup_century21 = BeautifulSoup(response_century21.content, "html.parser")

            for annonce_century21 in soup_century21.find_all("article", class_="ad-item"):  # Example selector, adapt as needed
                title_century21 = annonce_century21.find("a", class_="ad-title")  # Example selector, adapt as needed
                price_century21 = annonce_century21.find("span", class_="ad-price")  # Example selector, adapt as needed
                link_century21 = annonce_century21.find("a", class_="ad-title")  # Example selector, adapt as needed

                if title_century21 and price_century21 and link_century21 and link_century21.has_attr("href"):
                    annonces.append({
                        "title": title_century21.text.strip() if title_century21 else "N/A",
                        "price": price_century21.text.strip() if price_century21 else "N/A",
                        "link": "https://www.century21.fr" + link_century21["href"] if link_century21.has_attr("href") else "N/A",
                        "source": "Century 21"
                    })
        except requests.exceptions.RequestException as e:
            print(f"Erreur scraping Century 21: {e}")
        except AttributeError as e:
            print(f"Erreur parsing Century 21: {e}")
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        # ... d'autres User-Agents (ajoutez-en plusieurs)
    ]

    proxies_list = [  # Liste de vos proxies
        {"url": "http://user1:password@proxy1_ip:port"},  # Exemple
        {"url": "http://user2:password@proxy2_ip:port"},  # Exemple
        # ... d'autres proxies
    ]

    try:
        user_agent = random.choice(user_agents)

        proxy_data = random.choice(proxies_list)
        proxy_url = proxy_data["url"]

        # Encodage des caractères spéciaux dans l'URL du proxy
        try:  # si user et password
            username, password_host = proxy_url.split("@")
            username = quote(username.split("//")[1].split(":")[0])  # extraction user
            password, host = password_host.split(":")
            password = quote(password)
            proxy_url = f"http://{username}:{password}@{host}"
        except:  # sinon juste l'host et le port
            pass

        proxies = {"http": proxy_url, "https": proxy_url}

        headers = {"User-Agent": user_agent}

        response = requests.get(url, params=params, headers=headers, proxies=proxies)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        results = []

        annonces = soup.find_all("li", class_="ad-list-item")
        for i, annonce in enumerate(annonces):
            if i >= limit:
                break

            title = annonce.find("a", class_="ad-list-item__title")
            price = annonce.find("span", class_="ad-list-item__price")
            link = annonce.find("a", class_="ad-list-item__title")

            if title and price and link:
                results.append({
                    "title": title.text.strip(),
                    "price": price.text.strip(),
                    "link": "https://www.leboncoin.fr" + link["href"] if link.has_attr("href") else ""
                })

        if not results:
            return [{"error": "Aucune annonce trouvée"}]

        time.sleep(random.uniform(2, 5))
        return results

    except requests.exceptions.RequestException as e:
        print(f"Erreur scraping: {e}")
        return [{"error": str(e)}]
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

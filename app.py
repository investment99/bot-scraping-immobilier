import psycopg2
import requests
from bs4 import BeautifulSoup
import openai
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
import traceback
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time
import zipfile
import stat

load_dotenv()

app = Flask(__name__)  # ✅ Définition de Flask ici

# 🟢 Activer CORS uniquement pour ton site WordPress
CORS(app, origins=["https://p-i-investment.com"])

# 📌 Connexion API OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# 📌 Connexion à la base de données PostgreSQL
def connect_db():
    try:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise ValueError("❌ DATABASE_URL non configurée")
        return psycopg2.connect(db_url)
    except Exception as e:
        print(f"❌ Erreur connexion DB : {e}")
        return None

# 📌 Installation de Chromium et ChromeDriver
CHROMIUM_URL = "https://storage.googleapis.com/chrome-for-testing-public/121.0.6167.85/linux64/chrome-linux64.zip"
CHROMEDRIVER_URL = "https://storage.googleapis.com/chrome-for-testing-public/121.0.6167.85/linux64/chromedriver-linux64.zip"
CHROME_DIR = "/tmp/chrome-linux64"
CHROMEDRIVER_DIR = "/tmp/chromedriver-linux64"
CHROME_PATH = f"{CHROME_DIR}/chrome"
CHROMEDRIVER_PATH = f"{CHROMEDRIVER_DIR}/chromedriver"

def download_and_extract(url, extract_to):
    """Télécharge et extrait un fichier ZIP dans /tmp/."""
    zip_path = extract_to + ".zip"
    print(f"🔽 Téléchargement de {url}...")
    
    response = requests.get(url, stream=True)
    with open(zip_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=128):
            f.write(chunk)
    
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall("/tmp/")
    
    os.chmod(extract_to, stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)  # Donner les permissions d'exécution
    os.remove(zip_path)  # Supprimer le fichier ZIP après extraction

def setup_chromium():
    """Télécharge Chromium et ChromeDriver si nécessaire et corrige les chemins."""
    if not os.path.exists(CHROME_PATH):
        print("🔽 Chromium non trouvé, téléchargement en cours...")
        os.makedirs(CHROME_DIR, exist_ok=True)
        download_and_extract(CHROMIUM_URL, CHROME_PATH)

    if not os.path.exists(CHROMEDRIVER_PATH):
        print("🔽 ChromeDriver non trouvé, téléchargement en cours...")
        os.makedirs(CHROMEDRIVER_DIR, exist_ok=True)
        download_and_extract(CHROMEDRIVER_URL, CHROMEDRIVER_PATH)

def scrape_with_selenium(forum_url):
    """Scraper une page avec Selenium et retourner son HTML."""
    try:
        setup_chromium()  # Vérifie que Chromium est installé

        # Configuration pour Chromium
        chrome_options = Options()
        chrome_options.binary_location = CHROME_PATH
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-dev-shm-usage")

        # Lancer Chromium avec ChromeDriver
        service = Service(CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=chrome_options)

        print(f"🔍 Chargement de la page {forum_url}")
        driver.get(forum_url)
        time.sleep(3)  # Attente du chargement de la page

        # Essayer d'accepter les cookies
        try:
            accept_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Accepter') or contains(text(), 'J'accepte') or contains(text(), 'OK')]")
            accept_button.click()
            print("✅ Cookies acceptés avec succès")
            time.sleep(2)
        except:
            print("⚠️ Aucun bouton de cookies détecté.")

        # Récupérer le HTML après acceptation des cookies
        page_source = driver.page_source
        print("🔍 HTML récupéré :", page_source[:1000])  # Voir les 1000 premiers caractères du HTML
        driver.quit()
        return page_source

    except Exception as e:
        print(f"❌ Erreur Selenium sur Render: {str(e)}")
        return None

# 📌 Route de test pour voir si l'API fonctionne
@app.route('/')
def home():
    return "✅ API Flask fonctionne correctement !"

# 📌 Route pour tester Selenium
@app.route('/test_selenium', methods=['GET'])
def test_selenium():
    try:
        html = scrape_with_selenium("https://www.google.com")
        return jsonify({"message": "✅ Selenium fonctionne !"}), 200
    except Exception as e:
        return jsonify({"error": f"❌ Selenium ne fonctionne pas: {str(e)}"}), 500

# 📌 Route pour scraper les prospects sur un forum
@app.route('/scrape_prospects', methods=['POST'])
def scrape_prospects():
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"error": "❌ Aucune donnée reçue"}), 400

        user_id = data.get("user_id")
        forum_url = data.get("forum_url")
        keyword = data.get("keyword", "investir")

        if not forum_url:
            return jsonify({"error": "❌ URL du forum manquante"}), 400

        # Scraper la page avec Selenium
        html_content = scrape_with_selenium(forum_url)
        if not html_content:
            return jsonify({"error": "❌ Impossible d'accéder au forum avec Selenium"}), 500

        soup = BeautifulSoup(html_content, 'html.parser')
        posts = soup.find_all('div', class_="post")  # Modifier cette classe si nécessaire
        prospects = []

        for post in posts:
            post_content = post.text.strip()
            if keyword.lower() in post_content.lower():
                prospects.append(post_content)

        if not prospects:
            return jsonify({"message": "Aucun prospect trouvé avec ce mot-clé."}), 200

        conn = connect_db()
        if not conn:
            return jsonify({"error": "❌ Impossible de se connecter à la base de données"}), 500

        cursor = conn.cursor()
        for prospect in prospects:
            cursor.execute("INSERT INTO prospects (user_id, content) VALUES (%s, %s)", (user_id, prospect))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"message": f"{len(prospects)} prospects ajoutés pour l'abonné {user_id}."}), 200

    except Exception as e:
        print(f"❌ Erreur dans /scrape_prospects : {e}")
        traceback.print_exc()
        return jsonify({"error": f"Une erreur s'est produite: {str(e)}"}), 500

# 📌 Forcer Flask à utiliser le port de Render
port = int(os.environ.get("PORT", 5000))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port, debug=True)

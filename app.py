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
        os.makedirs(CHROME_DIR, exist_ok=True)  # Assurer que le dossier existe
        download_and_extract(CHROMIUM_URL, CHROME_PATH)

    if not os.path.exists(CHROMEDRIVER_PATH):
        print("🔽 ChromeDriver non trouvé, téléchargement en cours...")
        os.makedirs(CHROMEDRIVER_DIR, exist_ok=True)  # Assurer que le dossier existe
        download_and_extract(CHROMEDRIVER_URL, CHROMEDRIVER_PATH)

# 📌 Route de test pour vérifier que Selenium fonctionne
@app.route('/test_selenium', methods=['GET'])
def test_selenium():
    try:
        setup_chromium()  # Assure l'installation de Chromium

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

        # Aller sur un site simple (Google)
        driver.get("https://www.google.com")
        title = driver.title
        driver.quit()

        return jsonify({"message": "✅ Selenium fonctionne !", "title": title}), 200

    except Exception as e:
        print(f"❌ Erreur Selenium : {str(e)}")
        return jsonify({"error": f"❌ Selenium ne fonctionne pas: {str(e)}"}), 500

# 📌 Route de test pour voir si l'API fonctionne
@app.route('/')
def home():
    return "✅ API Flask fonctionne correctement !"

# 📌 Forcer Flask à utiliser le port de Render
port = int(os.environ.get("PORT", 5000))  # Récupère le port donné par Render ou utilise 5000 par défaut

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port, debug=True)

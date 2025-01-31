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
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time

load_dotenv()

app = Flask(__name__)

# 🟢 Activer CORS uniquement pour ton site WordPress
CORS(app, origins=["https://p-i-investment.com"])

# Connexion API OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Connexion à la base de données PostgreSQL
def connect_db():
    try:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise ValueError("❌ DATABASE_URL non configurée")
        return psycopg2.connect(db_url)
    except Exception as e:
        print(f"❌ Erreur connexion DB : {e}")
        return None

# Fonction pour scraper avec Selenium (accepter les cookies)
def scrape_with_selenium(forum_url):
    try:
        # Télécharger ChromeDriver automatiquement sans ChromeType
        chrome_driver_path = ChromeDriverManager().install()

        # Configuration spécifique pour Render
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Mode sans affichage
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--window-size=1920x1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

        # Lancer Chrome avec WebDriver Manager
        service = Service(chrome_driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)

        print("✅ Selenium a démarré avec succès sur Render.")

        driver.get(forum_url)
        time.sleep(3)  # Attente du chargement de la page

        # Chercher et cliquer sur "Accepter les cookies"
        try:
            accept_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Accepter') or contains(text(), 'J'accepte') or contains(text(), 'OK')]")
            accept_button.click()
            print("✅ Cookies acceptés avec succès")
            time.sleep(2)  # Laisser la page se recharger après acceptation
        except:
            print("⚠️ Aucun bouton de cookies détecté.")

        # Récupérer le HTML après acceptation des cookies
        page_source = driver.page_source
        driver.quit()
        return page_source

    except Exception as e:
        print(f"❌ Erreur Selenium sur Render: {str(e)}")
        return None

# Scraping des groupes/forums pour identifier les prospects
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

        # Utilisation de Selenium pour accepter les cookies et récupérer la page HTML
        html_content = scrape_with_selenium(forum_url)
        if not html_content:
            return jsonify({"error": "❌ Impossible d'accéder au forum avec Selenium"}), 500

        soup = BeautifulSoup(html_content, 'html.parser')
        posts = soup.find_all('div', class_="post")  # Modifier cette classe si besoin
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

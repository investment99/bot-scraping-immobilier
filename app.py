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

app = Flask(__name__)  # ✅ Définition de Flask ici

# 🟢 Activer CORS uniquement pour ton site WordPress
CORS(app, origins=["https://p-i-investment.com"])

# 📌 Route de test pour vérifier que Selenium fonctionne
@app.route('/test_selenium', methods=['GET'])
def test_selenium():
    try:
        # Télécharger ChromeDriver automatiquement
        chrome_driver_path = ChromeDriverManager().install()

        # Configuration pour Chromium
        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        # Lancer Chromium
        service = Service(chrome_driver_path)
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

import psycopg2
import requests
from bs4 import BeautifulSoup
import openai
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
import traceback

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
        db_url = os.getenv("DATABASE_URL")  # Utilisation de l'URL PostgreSQL sur Render
        if not db_url:
            raise ValueError("❌ DATABASE_URL non configurée")
        return psycopg2.connect(db_url)
    except Exception as e:
        print(f"❌ Erreur connexion DB : {e}")
        return None

# Route de test
@app.route('/')
def home():
    return "✅ API Flask fonctionne correctement !"

# Scraping des groupes/forums pour identifier les prospects
@app.route('/scrape_prospects', methods=['POST'])
def scrape_prospects():
    try:
        # Récupération des données envoyées
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"error": "❌ Aucune donnée reçue"}), 400

        user_id = data.get("user_id")  # ID de l'abonné
        forum_url = data.get("forum_url")  # URL du forum à scrapper
        keyword = data.get("keyword", "investir")  # Mot-clé à rechercher

        if not forum_url:
            return jsonify({"error": "❌ URL du forum manquante"}), 400

        # Scraper le forum avec un User-Agent pour éviter le blocage
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        response = requests.get(forum_url, headers=headers)
        
        if response.status_code != 200:
            return jsonify({"error": f"❌ Impossible d'accéder au forum (Code: {response.status_code})"}), 400

        soup = BeautifulSoup(response.text, 'html.parser')
        posts = soup.find_all('div', class_="post")  # À adapter selon la structure du forum
        prospects = []

        for post in posts:
            post_content = post.text.strip()
            if keyword.lower() in post_content.lower():
                prospects.append(post_content)

        if not prospects:
            return jsonify({"message": "Aucun prospect trouvé avec ce mot-clé."}), 200

        # Connexion à la base de données
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

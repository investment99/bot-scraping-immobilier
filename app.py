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
    conn = psycopg2.connect(
        dbname="your_db",
        user="your_user",
        password="your_password",
        host="localhost"
    )
    return conn

# Route de test
@app.route('/')
def home():
    return "✅ API Flask fonctionne correctement !"

# Scraping des groupes/forums pour identifier les prospects
@app.route('/scrape_prospects', methods=['POST'])
def scrape_prospects():
    try:
        # Récupération des données envoyées par l'abonné (par exemple, un forum à scrapper)
        data = request.json
        if not data:
            return jsonify({"error": "❌ Aucune donnée reçue"}), 400

        user_id = data.get("user_id")  # ID de l'abonné
        forum_url = data.get("forum_url")  # URL du forum à scrapper
        keyword = data.get("keyword", "investir")  # Mot-clé à rechercher

        # Scraper le forum (exemple avec BeautifulSoup)
        response = requests.get(forum_url)
        soup = BeautifulSoup(response.text, 'html.parser')

        posts = soup.find_all('div', class_="post")  # À adapter selon la structure du forum
        prospects = []

        for post in posts:
            post_content = post.text.strip()
            if keyword.lower() in post_content.lower():
                prospects.append(post_content)

        # Enregistrer les prospects dans la base de données, associés à l'utilisateur
        conn = connect_db()
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

# Générer un message personnalisé pour un prospect et l'envoyer
@app.route('/send_message', methods=['POST'])
def send_message():
    try:
        # Récupérer les données envoyées (message à envoyer et ID du prospect)
        data = request.json
        if not data:
            return jsonify({"error": "❌ Aucune donnée reçue"}), 400

        user_id = data.get("user_id")  # ID de l'abonné
        prospect_id = data.get("prospect_id")  # ID du prospect
        message = data.get("message")  # Message personnalisé à envoyer

        # Créer un message via OpenAI (par exemple, personnaliser le message)
        prompt = f"Rédige un message engageant pour un prospect concernant l'immobilier : {message}"

        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )

        final_message = response.choices[0].message.content.strip()

        # Ici, tu pourrais envoyer le message via un bot ou autre méthode
        print(f"🧠 Message généré pour le prospect {prospect_id}: {final_message}")

        # Enregistrer l'envoi du message dans la base de données (par exemple)
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO messages (user_id, prospect_id, message) VALUES (%s, %s, %s)", (user_id, prospect_id, final_message))
        
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"message": f"Message envoyé au prospect {prospect_id}."}), 200

    except Exception as e:
        print(f"❌ Erreur dans /send_message : {e}")
        traceback.print_exc()
        return jsonify({"error": f"Une erreur s'est produite: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

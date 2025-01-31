import psycopg2
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
import traceback
import csv
from googlesearch import search
import openai

load_dotenv()

app = Flask(__name__)  # ✅ Définition de Flask ici
CORS(app, origins=["https://p-i-investment.com"])

# 📌 Connexion à OpenAI
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

# 📌 Route de test pour voir si l'API fonctionne
@app.route('/')
def home():
    return "✅ API Flask fonctionne correctement !"

# 📌 Route pour la Recherche de Prospects via Google Search
@app.route('/search_google', methods=['POST'])
def search_google():
    try:
        data = request.get_json(force=True, silent=True)
        query = data.get("query")

        if not query:
            return jsonify({"error": "❌ Aucun mot-clé fourni"}), 400

        results = list(search(query, num_results=10))

        return jsonify({"results": results}), 200

    except Exception as e:
        print(f"❌ Erreur dans /search_google : {e}")
        return jsonify({"error": f"Une erreur s'est produite: {str(e)}"}), 500

# 📌 Route pour Importer un Fichier CSV contenant des Prospects LinkedIn
@app.route('/upload_csv', methods=['POST'])
def upload_csv():
    try:
        if 'csv_file' not in request.files:
            return jsonify({"error": "❌ Aucun fichier reçu"}), 400

        file = request.files['csv_file']
        if file.filename == '':
            return jsonify({"error": "❌ Fichier invalide"}), 400

        file_content = file.read().decode("utf-8").splitlines()
        csv_reader = csv.reader(file_content)

        conn = connect_db()
        if not conn:
            return jsonify({"error": "❌ Impossible de se connecter à la base de données"}), 500

        cursor = conn.cursor()
        prospects = []

        for row in csv_reader:
            if len(row) >= 3:
                full_name, profile_url, job_title = row[:3]
                prospects.append((full_name, profile_url, job_title))

        cursor.executemany("INSERT INTO linkedin_prospects (full_name, profile_url, job_title) VALUES (%s, %s, %s)", prospects)
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"message": f"✅ {len(prospects)} prospects importés avec succès."}), 200

    except Exception as e:
        print(f"❌ Erreur dans /upload_csv : {e}")
        traceback.print_exc()
        return jsonify({"error": f"Une erreur s'est produite: {str(e)}"}), 500

# 📌 Route pour envoyer les données à Make.com via Webhook
@app.route('/send_to_make', methods=['POST'])
def send_to_make():
    try:
        data = request.get_json(force=True, silent=True)
        webhook_url = "https://hook.eu2.make.com/z60ssi7icgai6s9sjky51ckhcp3xtvtl"

        response = requests.post(webhook_url, json=data)
        response.raise_for_status()

        return jsonify({"message": "✅ Données envoyées avec succès à Make.com."}), 200
    except Exception as e:
        print(f"❌ Erreur dans /send_to_make : {e}")
        traceback.print_exc()
        return jsonify({"error": f"Une erreur s'est produite: {str(e)}"}), 500

# 📌 Autres routes déjà définies...

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

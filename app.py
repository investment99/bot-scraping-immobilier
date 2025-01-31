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

# 📌 Route pour Analyser et Classer les Prospects avec OpenAI
@app.route('/analyze_prospects', methods=['POST'])
def analyze_prospects():
    try:
        conn = connect_db()
        if not conn:
            return jsonify({"error": "❌ Impossible de se connecter à la base de données"}), 500

        cursor = conn.cursor()
        cursor.execute("SELECT full_name, profile_url, job_title FROM linkedin_prospects")
        prospects = cursor.fetchall()
        cursor.close()
        conn.close()

        analyzed_prospects = []
        for p in prospects:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Classifie ce prospect selon son potentiel d'investissement."},
                    {"role": "user", "content": f"Nom: {p[0]}, Poste: {p[2]}. Est-il un bon investisseur ?"}
                ]
            )
            classification = response['choices'][0]['message']['content']
            analyzed_prospects.append({"nom": p[0], "linkedin": p[1], "poste": p[2], "classement": classification})

        return jsonify(analyzed_prospects), 200

    except Exception as e:
        print(f"❌ Erreur dans /analyze_prospects : {e}")
        traceback.print_exc()
        return jsonify({"error": f"Une erreur s'est produite: {str(e)}"}), 500

# 📌 Route pour Générer Automatiquement un Post avec OpenAI
@app.route('/generate_post', methods=['POST'])
def generate_post():
    try:
        data = request.get_json(force=True, silent=True)
        topic = data.get("topic", "Investissement immobilier")

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Génère un post engageant sur le sujet donné."},
                {"role": "user", "content": f"Crée un post pour les réseaux sociaux sur {topic}."}
            ]
        )
        generated_post = response['choices'][0]['message']['content']

        return jsonify({"post": generated_post}), 200

    except Exception as e:
        print(f"❌ Erreur dans /generate_post : {e}")
        traceback.print_exc()
        return jsonify({"error": f"Une erreur s'est produite: {str(e)}"}), 500

# 📌 Route pour Déterminer la Meilleure Heure de Publication
@app.route('/best_time_to_post', methods=['GET'])
def best_time_to_post():
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Analyse les meilleures heures pour publier sur les réseaux sociaux."},
                {"role": "user", "content": "Quelle est la meilleure heure pour publier sur LinkedIn et Facebook ?"}
            ]
        )
        best_time = response['choices'][0]['message']['content']

        return jsonify({"best_time": best_time}), 200

    except Exception as e:
        print(f"❌ Erreur dans /best_time_to_post : {e}")
        traceback.print_exc()
        return jsonify({"error": f"Une erreur s'est produite: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

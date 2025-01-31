import psycopg2
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
import traceback
import csv
import openai

load_dotenv()

app = Flask(__name__)  # ✅ Définition de Flask ici
CORS(app, origins=["https://p-i-investment.com"])

# 📌 Connexion à OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# 📌 Connexion à la base de données PostgreSQL (si nécessaire)
def connect_db():
    try:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise ValueError("❌ DATABASE_URL non configurée")
        return psycopg2.connect(db_url)
    except Exception as e:
        print(f"❌ Erreur connexion DB : {e}")
        return None

# 📌 Route de test pour vérifier si l'API fonctionne
@app.route('/')
def home():
    return "✅ API Flask fonctionne correctement !"

# 📌 Route pour la Recherche de Prospects via Google Search (reste inchangée)
@app.route('/search_google', methods=['POST'])
def search_google():
    try:
        data = request.get_json(force=True, silent=True)
        query = data.get("query")

        if not query:
            return jsonify({"error": "❌ Aucun mot-clé fourni"}), 400

        # Effectuer une recherche Google et retourner les résultats
        results = list(search(query, num_results=10))

        return jsonify({"results": results}), 200

    except Exception as e:
        print(f"❌ Erreur dans /search_google : {e}")
        return jsonify({"error": f"Une erreur s'est produite: {str(e)}"}), 500

# 📌 Route pour analyser et trier les prospects avec OpenAI
@app.route('/analyse_prospects', methods=['POST'])
def analyse_prospects():
    try:
        # Récupérer les données JSON envoyées par PHP
        data = request.get_json(force=True, silent=True)
        prospects = data.get("prospects")

        if not prospects or len(prospects) == 0:
            return jsonify({"error": "❌ Aucune donnée de prospect reçue."}), 400

        sorted_prospects = []
        for prospect in prospects:
            name = prospect['name']
            company = prospect['company']

            # Analyse OpenAI pour chaque prospect (exemple simple)
            prompt = f"Évalue ce prospect : {name} travaillant pour {company}. Quelle est sa pertinence ?"
            response = openai.Completion.create(
                model="text-davinci-003",
                prompt=prompt,
                max_tokens=50
            )

            score = response.choices[0].text.strip()
            sorted_prospects.append({
                'name': name,
                'company': company,
                'score': score
            })

        # Trier les prospects par score
        sorted_prospects.sort(key=lambda x: x['score'], reverse=True)

        # Retourner les prospects triés
        return jsonify(sorted_prospects), 200

    except Exception as e:
        print(f"❌ Erreur dans /analyse_prospects : {e}")
        traceback.print_exc()
        return jsonify({"error": f"Une erreur s'est produite: {str(e)}"}), 500

# 📌 Autres routes déjà définies...

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

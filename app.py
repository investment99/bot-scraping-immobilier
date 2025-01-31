import psycopg2
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
import traceback
import csv
import openai
from functools import wraps

load_dotenv()

app = Flask(__name__)
CORS(app, origins=["https://p-i-investment.com"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

def connect_db():
    try:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise ValueError("❌ DATABASE_URL non configurée")
        return psycopg2.connect(db_url)
    except Exception as e:
        print(f"❌ Erreur connexion DB : {e}")
        return None

def error_handler(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            print(f"❌ Erreur dans {f.__name__} : {e}")
            traceback.print_exc()
            return jsonify({"error": f"Une erreur s'est produite: {str(e)}"}), 500
    return decorated_function

@app.route('/')
def home():
    return "✅ API Flask fonctionne correctement !"

@app.route('/search_openai', methods=['POST'])
@error_handler
def search_openai():
    data = request.get_json(force=True, silent=True)
    query = data.get("query")

    if not query:
        return jsonify({"error": "❌ Aucun mot-clé fourni"}), 400

    response = openai.Completion.create(
        engine="text-davinci-002",
        prompt=f"Générer des suggestions de prospects pour la recherche : {query}",
        max_tokens=100
    )
    results = response.choices[0].text.strip().split('\n')
    return jsonify({"results": results}), 200

@app.route('/analyse_prospects', methods=['POST'])
@error_handler
def analyse_prospects():
    data = request.get_json(force=True, silent=True)
    prospects = data.get("prospects")

    if not prospects or len(prospects) == 0:
        return jsonify({"error": "❌ Aucune donnée de prospect reçue."}), 400

    sorted_prospects = []
    for prospect in prospects:
        name = prospect['name']
        company = prospect['company']

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

    sorted_prospects.sort(key=lambda x: x['score'], reverse=True)
    return jsonify(sorted_prospects), 200

@app.route('/generate_post', methods=['POST'])
@error_handler
def generate_post():
    data = request.get_json(force=True, silent=True)
    topic = data.get("topic")

    if not topic:
        return jsonify({"error": "❌ Aucun sujet fourni"}), 400

    response = openai.Completion.create(
        engine="text-davinci-002",
        prompt=f"Générer un post sur le sujet : {topic}",
        max_tokens=200
    )
    generated_post = response.choices[0].text.strip()
    return jsonify({"generated_post": generated_post}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

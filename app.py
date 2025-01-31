import psycopg2
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
import traceback
import csv
import openai
import logging
from functools import wraps

load_dotenv()

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
CORS(app, origins=["https://p-i-investment.com"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

def connect_db():
    try:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise ValueError("❌ DATABASE_URL non configurée")
        logging.info("Connexion à la base de données en cours...")
        return psycopg2.connect(db_url)
    except Exception as e:
        logging.error(f"❌ Erreur connexion DB : {e}")
        return None

def error_handler(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logging.error(f"❌ Erreur dans {f.__name__} : {e}")
            traceback.print_exc()
            return jsonify({"error": f"Une erreur s'est produite: {str(e)}"}), 500
    return decorated_function

@app.route('/')
def home():
    logging.info("API Flask fonctionne correctement !")
    return "✅ API Flask fonctionne correctement !"

@app.route('/search_openai', methods=['POST'])
@error_handler
def search_openai():
    data = request.get_json(force=True, silent=True)
    query = data.get("query")
    
    if not query:
        logging.warning("Aucun mot-clé fourni")
        return jsonify({"error": "❌ Aucun mot-clé fourni"}), 400
    
    logging.info(f"Requête OpenAI pour la recherche : {query}")
    response = openai.Completion.create(
        engine="gpt-4",
        prompt=f"Générer des suggestions de prospects pour la recherche : {query}",
        max_tokens=100
    )
    results = response.choices[0].text.strip().split('\n')
    logging.info(f"Résultats OpenAI : {results}")
    return jsonify({"results": results}), 200

@app.route('/analyse_prospects', methods=['POST'])
@error_handler
def analyse_prospects():
    data = request.get_json(force=True, silent=True)
    prospects = data.get("prospects")
    
    if not prospects or len(prospects) == 0:
        logging.warning("Aucune donnée de prospect reçue.")
        return jsonify({"error": "❌ Aucune donnée de prospect reçue."}), 400
    
    sorted_prospects = []
    for prospect in prospects:
        name = prospect['name']
        company = prospect['company']
        logging.info(f"Évaluation du prospect : {name} - {company}")
        prompt = f"Évalue ce prospect : {name} travaillant pour {company}. Quelle est sa pertinence ?"
        response = openai.Completion.create(
            model="gpt-4",
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
    logging.info("Prospects triés et envoyés à l'interface PHP.")
    return jsonify(sorted_prospects), 200

@app.route('/generate_post', methods=['POST'])
@error_handler
def generate_post():
    data = request.get_json(force=True, silent=True)
    topic = data.get("topic")
    
    if not topic:
        logging.warning("Aucun sujet fourni")
        return jsonify({"error": "❌ Aucun sujet fourni"}), 400
    
    logging.info(f"Génération d'un post pour le sujet : {topic}")
    response = openai.Completion.create(
        engine="gpt-4",
        prompt=f"Générer un post sur le sujet : {topic}",
        max_tokens=200
    )
    generated_post = response.choices[0].text.strip()
    logging.info("Post généré avec succès")
    return jsonify({"generated_post": generated_post}), 200

@app.route('/test_db', methods=['GET'])
def test_db():
    conn = connect_db()
    if conn:
        logging.info("Connexion à la DB réussie")
        return jsonify({"message": "✅ Connexion à la DB réussie !"}), 200
    else:
        logging.error("Impossible de se connecter à la base de données.")
        return jsonify({"error": "❌ Impossible de se connecter à la base de données."}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"Démarrage du serveur Flask sur le port {port}")
    app.run(host="0.0.0.0", port=port, debug=True)

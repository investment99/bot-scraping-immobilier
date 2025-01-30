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
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"error": "❌ Aucune donnée reçue"}), 400

        user_id = data.get("user_id")
        forum_url = data.get("forum_url")
        keyword = data.get("keyword", "investir")

        if not forum_url:
            return jsonify({"error": "❌ URL du forum manquante"}), 400

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        response = requests.get(forum_url, headers=headers)
        
        if response.status_code != 200:
            return jsonify({"error": f"❌ Impossible d'accéder au forum (Code: {response.status_code})"}), 400

        soup = BeautifulSoup(response.text, 'html.parser')
        posts = soup.find_all('div', class_="post")
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

# Nouvelle route pour la planification des posts
@app.route('/schedule_post', methods=['POST'])
def schedule_post():
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"error": "❌ Aucune donnée reçue"}), 400

        user_id = data.get("user_id")
        content = data.get("content")
        scheduled_time = data.get("scheduled_time")

        if not all([user_id, content, scheduled_time]):
            return jsonify({"error": "❌ Données manquantes"}), 400

        conn = connect_db()
        if not conn:
            return jsonify({"error": "❌ Impossible de se connecter à la base de données"}), 500

        cursor = conn.cursor()
        cursor.execute("INSERT INTO scheduled_posts (user_id, content, scheduled_time) VALUES (%s, %s, %s)",
                       (user_id, content, scheduled_time))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"message": "Post programmé avec succès"}), 200

    except Exception as e:
        print(f"❌ Erreur dans /schedule_post : {e}")
        traceback.print_exc()
        return jsonify({"error": f"Une erreur s'est produite: {str(e)}"}), 500

# Nouvelle route pour récupérer les posts programmés
@app.route('/scheduled_posts', methods=['GET'])
def get_scheduled_posts():
    try:
        user_id = request.args.get("user_id")
        if not user_id:
            return jsonify({"error": "❌ ID utilisateur manquant"}), 400

        conn = connect_db()
        if not conn:
            return jsonify({"error": "❌ Impossible de se connecter à la base de données"}), 500

        cursor = conn.cursor()
        cursor.execute("SELECT content, scheduled_time FROM scheduled_posts WHERE user_id = %s ORDER BY scheduled_time", (user_id,))
        posts = cursor.fetchall()

        cursor.close()
        conn.close()

        formatted_posts = [{"content": post[0], "scheduled_time": post[1].isoformat()} for post in posts]
        return jsonify({"posts": formatted_posts}), 200

    except Exception as e:
        print(f"❌ Erreur dans /scheduled_posts : {e}")
        traceback.print_exc()
        return jsonify({"error": f"Une erreur s'est produite: {str(e)}"}), 500

# Nouvelle route pour récupérer les prospects
@app.route('/prospects', methods=['GET'])
def get_prospects():
    try:
        user_id = request.args.get("user_id")
        if not user_id:
            return jsonify({"error": "❌ ID utilisateur manquant"}), 400

        conn = connect_db()
        if not conn:
            return jsonify({"error": "❌ Impossible de se connecter à la base de données"}), 500

        cursor = conn.cursor()
        cursor.execute("SELECT content FROM prospects WHERE user_id = %s", (user_id,))
        prospects = cursor.fetchall()

        cursor.close()
        conn.close()

        formatted_prospects = [{"content": prospect[0]} for prospect in prospects]
        return jsonify({"prospects": formatted_prospects}), 200

    except Exception as e:
        print(f"❌ Erreur dans /prospects : {e}")
        traceback.print_exc()
        return jsonify({"error": f"Une erreur s'est produite: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

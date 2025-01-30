from flask import Flask, request, jsonify
from flask_cors import CORS  
import openai
import os
from dotenv import load_dotenv
import traceback

load_dotenv()

app = Flask(__name__)

# 🟢 Activer CORS uniquement pour ton site WordPress
CORS(app, origins=["https://p-i-investment.com"])

print("🚀 Lancement de l'application Flask...")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

@app.route('/')
def home():
    return "✅ API Flask fonctionne correctement !"

@app.route('/test')
def test():
    return "🚀 Route de test fonctionne !"

@app.route('/routes', methods=['GET'])
def list_routes():
    """Affiche toutes les routes disponibles"""
    routes = [str(rule) for rule in app.url_map.iter_rules()]
    return jsonify({"routes": routes})

# 🟢 NOUVEAU ENDPOINT : GÉNÉRATION DE POSTS MARKETING
@app.route('/generate_post', methods=['POST'])
def generate_post():
    """Génère un post marketing pour attirer des clients dans l'immobilier"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "❌ Aucune donnée reçue"}), 400

        client_type = data.get("client_type", "investisseur")  
        ville = data.get("ville", "Paris")

        print(f"📡 Génération d'un post pour {client_type} à {ville}")

        # Prompt OpenAI
        prompt = f"""
        Rédige un post attractif pour un {client_type} qui veut attirer des clients cherchant à investir dans l'immobilier à {ville}. 
        - Ton professionnel mais engageant.
        - Utilise des emojis pour rendre le post dynamique.
        - Intègre un appel à l'action clair pour inciter à contacter.
        - Ajoute une touche de storytelling si possible.

        Exemple :
        📢 Vous cherchez à investir à {ville} ? Découvrez des opportunités rentables dès maintenant ! 🏡💰
        """
        
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )

        post_text = response.choices[0].message.content.strip()

        print(f"🧠 Post généré : {post_text}")

        return jsonify({"post": post_text}), 200

    except Exception as e:
        print(f"❌ Erreur dans /generate_post : {e}")
        traceback.print_exc()
        return jsonify({"error": f"Une erreur s'est produite: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

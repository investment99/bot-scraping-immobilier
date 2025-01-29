from flask import Flask, request, jsonify
from flask_cors import CORS  # 🟢 Importation pour gérer les requêtes CORS
import openai
import os
from dotenv import load_dotenv
import json
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
    """Affiche toutes les routes disponibles pour voir si /search_real_estate est bien chargée."""
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append(str(rule))
    return jsonify({"routes": routes})

@app.route('/search_real_estate', methods=['POST'])
def search_real_estate():
    """Génère des annonces basées sur les critères envoyés par WordPress"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "❌ Aucune donnée reçue"}), 400
        
        print(f"📡 Recherche reçue : {data}")

        # Vérifier si tous les champs sont présents
        required_fields = ["city", "property_type", "surface_min", "surface_max", "price_min", "price_max"]
        for field in required_fields:
            if field not in data:
                print(f"❌ Champ manquant : {field}")
                return jsonify({"error": f"Champ {field} manquant"}), 400

        # Création du prompt pour OpenAI
        prompt = f"""
        Je cherche des annonces immobilières avec ces critères :
        - Ville : {data["city"]}
        - Type : {data["property_type"]}
        - Surface : entre {data["surface_min"]} et {data["surface_max"]} m²
        - Budget : entre {data["price_min"]} et {data["price_max"]} €

        Génère 5 annonces fictives avec :
        - Type
        - Surface (m²)
        - Nombre de pièces
        - Prix (en €)
        - Localisation
        - Une description courte
        - Un lien fictif (ex: "https://annonce-immobiliere-fictive.com/annonce1")

        Répond uniquement avec du texte brut, formaté comme suit :
        - Annonce 1 : [Description] (Lien)
        - Annonce 2 : [Description] (Lien)
        - Annonce 3 : [Description] (Lien)
        - Annonce 4 : [Description] (Lien)
        - Annonce 5 : [Description] (Lien)
        """

        print("📡 Envoi du prompt à OpenAI...")

        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )

        raw_result = response.choices[0].message.content.strip()
        print(f"🧠 Réponse brute OpenAI : {raw_result}")

        # Vérifier si la réponse est bien sous forme de texte
        if raw_result:
            print(f"✅ Réponse OpenAI reçue.")
            return jsonify({"suggestions": raw_result}), 200
        else:
            print("❌ Erreur : La réponse d'OpenAI est vide.")
            return jsonify({"error": "Erreur lors de la génération des annonces"}), 500

    except Exception as e:
        print(f"❌ Erreur générale dans /search_real_estate : {e}")
        traceback.print_exc()
        return jsonify({"error": f"Une erreur s'est produite: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

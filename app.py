from flask import Flask, request, jsonify
import openai
import os
from dotenv import load_dotenv
import json
import traceback

load_dotenv()

app = Flask(__name__)

print("🚀 Lancement de l'application Flask...")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

@app.route('/')
def home():
    return "✅ API Flask fonctionne correctement !"

@app.route('/test')
def test():
    return "🚀 Route de test fonctionne !"

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

        Répond uniquement avec du JSON strictement formaté.
        """

        print("📡 Envoi du prompt à OpenAI...")

        rresponse = openai.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": prompt}]
        )

        raw_result = response["choices"][0]["message"]["content"].strip()
        print(f"🧠 Réponse brute OpenAI : {raw_result}")

        # Vérifier et corriger JSON si nécessaire
        try:
            suggestions = json.loads(raw_result)
            print(f"✅ OpenAI a généré {len(suggestions)} annonces.")
            return jsonify({"suggestions": suggestions}), 200
        except json.JSONDecodeError:
            print(f"❌ Erreur JSON OpenAI : {raw_result}")
            return jsonify({"error": "Erreur lors de la génération des annonces"}), 500

    except Exception as e:
        print(f"❌ Erreur générale : {e}")
        traceback.print_exc()
        return jsonify({"error": f"Une erreur s'est produite: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

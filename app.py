from flask import Flask, request, jsonify
import pdfplumber
import openai
import os
from dotenv import load_dotenv
import tempfile
import json
import hashlib
import re
import traceback

load_dotenv()

app = Flask(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

cache = {}

def extract_info(pdf_path):
    """Extrait les informations du PDF en ignorant les 4 premières pages"""
    try:
        print(f"📄 Début de l'extraction du PDF : {pdf_path}")
        with pdfplumber.open(pdf_path) as pdf:
            if len(pdf.pages) <= 4:
                print("❌ Erreur: Le PDF contient moins de 5 pages.")
                return None

            info = {}
            full_text = "\n".join([page.extract_text() for page in pdf.pages[4:] if page.extract_text()])
            print("✅ Texte extrait du PDF.")

            # Extraction des informations via regex
            type_match = re.search(r"Type de bien\s*:\s*(.*)", full_text)
            if type_match:
                info["type_de_bien"] = type_match.group(1).strip()

            superficie_match = re.search(r"superficie habitable de\s*(\d+)\s*m²", full_text, re.IGNORECASE)
            if superficie_match:
                info["superficie"] = int(superficie_match.group(1))

            localisation_match = re.search(r"(centre-ville|Promenade des Anglais)", full_text, re.IGNORECASE)
            if localisation_match:
                info["localisation"] = localisation_match.group(1).strip()

            budget_match = re.search(r"budget idéal de\s*([\d\s]+)\s*EUR", full_text, re.IGNORECASE)
            if budget_match:
                budget_str = budget_match.group(1).replace(" ", "")
                try:
                    info["budget"] = int(budget_str)
                except ValueError:
                    print("⚠️ Erreur: Budget mal formaté.")

            print(f"✅ Infos extraites : {info}")
            return info if info else None

    except Exception as e:
        print(f"❌ Erreur d'extraction PDF: {e}")
        traceback.print_exc()
        return None


def analyze_report(pdf_hash, infos):
    """Utilise OpenAI pour générer des annonces basées sur les critères extraits"""
    if pdf_hash in cache:
        print(f"🔄 Résultat en cache pour {pdf_hash}")
        return cache[pdf_hash]

    print(f"📡 Envoi des critères à OpenAI : {infos}")
    
    prompt = f"""
    Basé sur les critères suivants extraits d'un PDF:
    {json.dumps(infos, indent=2)}

    Génère 5 annonces immobilières fictives contenant:
    - Type de bien
    - Surface (m²)
    - Nombre de pièces
    - Prix (en €)
    - Localisation
    - Une description courte
    - Un lien fictif (ex: "https://annonce-immobiliere-fictive.com/annonce1")

    Répond uniquement avec du JSON strictement formaté.
    """

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Tu es un assistant spécialisé en immobilier."},
                {"role": "user", "content": prompt}
            ]
        )

        raw_result = response["choices"][0]["message"]["content"].strip()
        print(f"🧠 Réponse brute OpenAI : {raw_result}")

        try:
            suggestions = json.loads(raw_result)
            cache[pdf_hash] = suggestions
            print(f"✅ OpenAI a généré {len(suggestions)} suggestions.")
            return suggestions
        except json.JSONDecodeError as json_err:
            print(f"❌ Erreur JSON OpenAI : {json_err}")
            return None

    except Exception as e:
        print(f"❌ Erreur OpenAI : {e}")
        traceback.print_exc()
        return None


@app.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    """API permettant d'envoyer un PDF et de recevoir des annonces générées"""
    print("📩 Requête reçue sur /upload_pdf")

    if 'file' not in request.files:
        print("❌ Aucune fichier reçu !")
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    print(f"📂 Fichier reçu : {file.filename}")

    if not file.filename.endswith('.pdf'):
        print("❌ Fichier non valide (doit être un PDF).")
        return jsonify({"error": "Invalid file type"}), 400

    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            file_path = tmp.name
            file.save(tmp)

        print(f"📌 PDF enregistré temporairement : {file_path}")

        with open(file_path, "rb") as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
            print(f"🆔 Hash du fichier : {file_hash}")

        relevant_info = extract_info(file_path)
        if not relevant_info:
            print("❌ Impossible d'extraire des informations du PDF.")
            return jsonify({"error": "Impossible d'extraire des informations du PDF"}), 500

        suggestions = analyze_report(file_hash, relevant_info)
        if not suggestions:
            print("❌ Problème lors de la génération des annonces.")
            return jsonify({"error": "Problème lors de la génération des annonces"}), 500

        print(f"✅ Réponse envoyée avec {len(suggestions)} suggestions.")
        return jsonify({"criteria": relevant_info, "suggestions": suggestions}), 200

    except Exception as e:
        print(f"❌ Erreur générale : {e}")
        traceback.print_exc()
        return jsonify({"error": "Une erreur s'est produite: " + str(e)}), 500

    finally:
        try:
            os.remove(file_path)
            print(f"🗑️ Fichier temporaire supprimé : {file_path}")
        except Exception as cleanup_error:
            print(f"⚠️ Erreur lors de la suppression du fichier temporaire : {cleanup_error}")


@app.route('/')
def home():
    return "✅ API Flask fonctionne correctement !"


if __name__ == "__main__":
    app.run(debug=True, port=5000)

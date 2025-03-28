from flask import request, send_file, jsonify
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, Table, TableStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from datetime import datetime
import os
import tempfile
from openai import OpenAI
from markdown2 import markdown as md_to_html
from bs4 import BeautifulSoup

client = OpenAI()

PDF_FOLDER = "./pdf_reports/"
os.makedirs(PDF_FOLDER, exist_ok=True)

def markdown_to_elements(md_text):
    elements = []
    html_content = md_to_html(md_text, extras=["tables"])
    soup = BeautifulSoup(html_content, "html.parser")
    styles = getSampleStyleSheet()
    PAGE_WIDTH = A4[0] - 4 * cm

    for elem in soup.contents:
        if elem.name == "table":
            table_data = []
            for row in elem.find_all("tr"):
                row_data = [Paragraph(cell.get_text(strip=True), styles['BodyText']) for cell in row.find_all(["td", "th"])]
                table_data.append(row_data)
            col_count = len(table_data[0]) if table_data and table_data[0] else 1
            col_width = PAGE_WIDTH / col_count
            table_style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ])
            table = Table(table_data, colWidths=[col_width] * col_count, style=table_style)
            elements.append(table)
        elif elem.name:
            paragraph = Paragraph(elem.get_text(strip=True), styles['BodyText'])
            elements.append(paragraph)
            elements.append(Spacer(1, 12))
    return elements

def add_section_title(elements, title):
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'SectionTitle',
        fontSize=16,
        fontName='Helvetica',
        textColor=colors.HexColor("#00C7C4"),
        alignment=1,
        spaceAfter=12,
        underline=True
    )
    elements.append(Paragraph(title, title_style))
    elements.append(Spacer(1, 12))

def generate_estimation_section(prompt, min_tokens=800):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Tu es un expert en immobilier, en estimation et en analyse prédictive du marché."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=min_tokens,
        temperature=0.7,
    )
    return markdown_to_elements(response.choices[0].message.content)

def resize_image(image_path, output_path, target_size=(469, 716)):
    from PIL import Image as PILImage
    with PILImage.open(image_path) as img:
        img = img.resize(target_size, PILImage.LANCZOS)
        img.save(output_path)

@app.route("/generate_estimation", methods=["POST"])
def generate_estimation():
    try:
        form_data = request.json
        name = form_data.get("nom", "Client")
        city = form_data.get("quartier", "Non spécifié")
        adresse = form_data.get("adresse", "Non spécifiée")

        filename = os.path.join(PDF_FOLDER, f"estimation_{name.replace(' ', '_')}.pdf")
        doc = SimpleDocTemplate(filename, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm, leftMargin=2*cm, rightMargin=2*cm)
        elements = []

        # Page de garde
        covers = ["static/cover_image.png", "static/cover_image1.png"]
        resized = []
        for img_path in covers:
            if os.path.exists(img_path):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                    resize_image(img_path, tmp.name)
                    resized.append(tmp.name)

        elements.append(Image(resized[0], width=469, height=716))
        elements.append(PageBreak())

        # Sections du rapport
        sections = [
            ("Informations personnelles", "Analysez les informations personnelles du client."),
            ("Informations générales sur le bien", "Analysez les caractéristiques générales du bien indiqué par le client."),
            ("État général du bien", "Évaluez l'état global du bien, les travaux récents et l'entretien."),
            ("Équipements et commodités", "Détaillez les équipements présents dans le bien."),
            ("Environnement et emplacement", f"Faites une analyse du quartier '{city}' et des commodités à proximité."),
            ("Historique et marché", "Analysez la présence du bien sur le marché, les offres et l'évolution des prix similaires."),
            ("Caractéristiques spécifiques", "Analysez les caractéristiques comme l'orientation, le DPE, etc."),
            ("Informations légales", "Passez en revue les documents légaux et contraintes."),
            ("Prix et conditions de vente", "Analysez le prix souhaité par le client et les conditions."),
            ("Autres informations", "Analysez les données complémentaires (occupation, dettes, charges)."),
            ("Estimation IA", f"Donnez une estimation du prix du bien situé à {adresse} dans le quartier {city}, en tenant compte du marché actuel."),
            ("Analyse prédictive", f"Prévoyez l'évolution de la valeur de ce bien immobilier dans les 5 à 10 ans à venir."),
            ("Recommandations IA", f"Faites des recommandations personnalisées pour optimiser la vente du bien."),
        ]

        for title, prompt in sections:
            add_section_title(elements, title)
            section = generate_estimation_section(prompt)
            elements.extend(section)
            elements.append(PageBreak())

        # Page de fin
        if len(resized) > 1:
            elements.append(Image(resized[1], width=469, height=716))

        doc.build(elements)
        return send_file(filename, as_attachment=True)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

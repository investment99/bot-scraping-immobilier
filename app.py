@app.route('/test_selenium', methods=['GET'])
def test_selenium():
    try:
        # Télécharger ChromeDriver automatiquement
        chrome_driver_path = ChromeDriverManager().install()

        # Configuration pour Chromium
        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        # Lancer Chromium
        service = Service(chrome_driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # Aller sur un site simple (Google)
        driver.get("https://www.google.com")
        title = driver.title
        driver.quit()

        return jsonify({"message": "✅ Selenium fonctionne !", "title": title}), 200

    except Exception as e:
        print(f"❌ Erreur Selenium : {str(e)}")
        return jsonify({"error": f"❌ Selenium ne fonctionne pas: {str(e)}"}), 500

import json
import pdb
import requests
from bs4 import BeautifulSoup
#import urllib.robotparser   # Si deseas verificar el robots.txt, puedes descomentar esta parte

# URL que deseamos scrapear (página de accesorios para mujer de Bata)
# url = "https://www.bata.com/co/mujer/accesorios/"
url = "https://www.bata.com/co/ofertas/ni%C3%B1os/"

# User-Agent personalizado para simular un navegador
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.85 Safari/537.36'
}

try:
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()   # Lanza excepción para errores HTTP

    # Parseamos el HTML con BeautifulSoup
    soup = BeautifulSoup(response.content, 'html.parser')
    # pdb.set_trace() # Descomenta si necesitas depurar en este punto

    # Guardar el contenido HTML formateado (para inspección, opcional)
    with open("contenido_corregido.html", "w", encoding="utf-8") as f:
        f.write(soup.prettify())

    # Mostrar el título de la página (opcional)
    titulo = soup.find('title')
    if titulo:
        print("Título de la página:", titulo.get_text())
    else:
        print("No se encontró la etiqueta <title> en la página.")

    # --- Extracción de información de productos ---
    products = {} # Diccionario para almacenar productos por ID (evitar duplicados)
    product_links = soup.find_all("a", attrs={"data-analytics-product-id": True})

    for prod_link in product_links:
        product_id = prod_link.get("data-analytics-product-id")

        name_tag = prod_link.find("span", class_="cc-tile-product-name")
        brand_tag = prod_link.find("span", class_="cc-tile-product-brand")

        if not name_tag or not brand_tag:
            continue    # Saltar si falta nombre o marca

        name = name_tag.get_text(strip=True)
        brand = brand_tag.get_text(strip=True)

        link = prod_link.get("href")
        if link and link.startswith("/"):
            link = "https://www.bata.com" + link

        # --- Extracción del PRECIO (Código corregido - Selector basado en imagen) ---
        price_tag = None
        # pdb.set_trace()
        product_container = prod_link.find_parent('div', class_='cc-col-tile') # **Verifica si 'tile-wrapper' es correcto inspeccionando el HTML completo**
        if product_container:
            tile_body = product_container.find('div', class_='tile-body cc-tile-body')
            if tile_body:
                price_wrapper = tile_body.find('div', class_='cc-price--wrapper')
                if price_wrapper:
                    sales_span = price_wrapper.find('span', class_='sales')
                    if sales_span:
                        price_tag = sales_span.find('span', class_='cc-price')

        price = None
        if price_tag:
            price_text = price_tag.get_text(strip=True)
            print(price_text)
            price = price_text.replace("Col$ ", "")#.replace(".", "").strip() # Limpieza para "Col$ ", comas y puntos
            try:
                price = int(price) # Intenta convertir a entero
            except ValueError:
                price = price_text # Si no es número, guarda el texto original

        # --- Extracción de TALLAS (Código existente, puede requerir ajustes para tallas específicas) ---
        sizes = []
        size_buttons = soup.find_all("a", class_="js-sizeBtn")
        prefix = "tile_" + product_id
        for btn in size_buttons:
            dcf = btn.get("data-classtorefresh", "")
            if dcf.startswith(prefix):
                size_val = btn.get("data-size")
                if not size_val:
                    size_val = btn.get_text(strip=True)
                if size_val and size_val not in sizes:
                    sizes.append(size_val)

        product_data = {
            "name": name,
            "brand": brand,
            "link": link,
            "sizes": sizes, # Tallas genéricas, verificar si necesitas tallas específicas en página individual
            "price": price, # Precio extraído
            "colors": [], # COLORES: Deberás extraer de la página individual del producto (si está disponible)
            "mas_info": {} # Campo para información adicional si se extrae de páginas individuales
        }
        products[product_id] = product_data

    product_list = list(products.values())

    # Escribir los datos en formato JSONL
    with open("products_corregido.jsonl", "w", encoding="utf-8") as outfile:
        for product in product_list:
            json.dump(product, outfile, ensure_ascii=False)
            outfile.write("\n")

    print(f"Se han extraído {len(product_list)} productos y guardado en 'products_corregido.jsonl'.")
    # pdb.set_trace() # Descomenta si necesitas depurar al final

except requests.exceptions.RequestException as e:
    print("Error al realizar la petición:", e)
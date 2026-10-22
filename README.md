# Laddresan

Ruttplanerare för elbil i Sverige. Laddresan föreslår laddstopp vid snabbladdare från 150 kW. Förbrukningen räknas med en fysikmodell som tar hänsyn till hastighet, temperatur, vind, höjdskillnader, last och vinterdäck.

**Webbplats:** https://bonormark-crypto.github.io/laddresan/

## Vad den gör

- Väljer rutt mellan start, mål och mellanstationer på tre sätt: snabbaste, kortaste (på större vägar) eller lägst förbrukning (högst 10 % längre körtid än snabbaste).
- Räknar förbrukning och laddning för 8 bilmodeller i grundurvalet och drygt 200 fler bilar. För de senare kommer förbrukningen från normaliserade räckviddstester vid 90 och 120 km/h och laddningen från uppmätta laddkurvor.
- Väljer laddstopp efter kortast restid, lägst kostnad eller färst stopp. Den laddar bara så mycket som behövs till nästa stopp.
- Tar hänsyn till föredragna och undvikna laddoperatörer och deras priser.
- Hämtar väderprognos längs rutten (temperatur och vind) från Open-Meteo.
- Har en länk till Google Maps per etapp, med passagepunkter så att Google följer den valda rutten.
- Låter dig spara egna platser ("Mina platser"). De sparas bara i din webbläsare.

## Så är projektet uppbyggt

| Sökväg | Innehåll |
| --- | --- |
| `src/index.src.html` | Hela appen (HTML, CSS och JavaScript) med platshållare för data |
| `scripts/assemble.py` | Bygger `dist/index.html` från mallen och datan |
| `scripts/update_chargers.py` | Hämtar nya laddplatser från Open Charge Map och supercharge.info |
| `data/graph_stage1b.json` | Vägnätet: ca 26 500 km huvudvägar från OpenStreetMap via OSRM |
| `data/elev_b.json` | Höjd för vägnätets punkter (AWS Terrain Tiles) |
| `data/chargers.json`, `data/tesla_se.json` | Snabbladdare från 150 kW |
| `data/cars_extra.json` | Fler bilar: kapacitet, vikt, kalibrerat luft- och rullmotstånd, uppmätt laddkurva |
| `scripts/build_cars.py`, `scripts/car_mapping.py` | Bygger `cars_extra.json` från arbetsböckerna Rackvidd_normaliserad.xlsx och Charging_curves.xlsx (kräver `pip install openpyxl`) |
| `data/se_cities.json` | Ca 800 svenska orter (GeoNames) |
| `data/basemap.json` | Baskarta (Natural Earth) |
| `.github/workflows/deploy.yml` | Bygger och publicerar på GitHub Pages |

## Bygga lokalt

```bash
pip install -r requirements.txt
python scripts/assemble.py          # skapar dist/index.html
```

Öppna `dist/index.html` direkt i webbläsaren. Någon server behövs inte.

## Publicering och uppdatering

- Varje push till `main` bygger om och publicerar sidan på GitHub Pages.
- Varje måndag hämtar GitHub Actions nya laddplatser, sparar dem i `data/` och publicerar om.
- Uppdateringen kan också köras för hand: **Actions → Bygg och publicera → Run workflow**.

## Datakällor och licenser

- Vägnät: © OpenStreetMap-bidragsgivare (ODbL), via OSRM
- Laddplatser: [Open Charge Map](https://openchargemap.org) (CC BY 4.0) och [supercharge.info](https://supercharge.info)
- Väder: [Open-Meteo](https://open-meteo.com) (CC BY 4.0)
- Adressökning: [Photon](https://photon.komoot.io) och [Nominatim](https://nominatim.org), © OpenStreetMap-bidragsgivare
- Höjd: AWS Terrain Tiles (bland annat EU-DEM, SRTM)
- Orter: GeoNames (CC BY 4.0). Baskarta: Natural Earth (public domain)

Kontrollera alltid status och pris i operatörens app före avresa.

# Manufacturer nutrient catalogue

GrowAsist ships a versioned, read-only manufacturer catalogue. It is separate
from `hardware.dosing_fluids`, which is the user's selected product list. A
catalogue update cannot remove a selected product or rewrite a cultivation
snapshot.

Catalogue version `2026.08.28.2` contains 367 products from 20 manufacturers:

| Manufacturer | Products | Official source |
| --- | ---: | --- |
| Advanced Nutrients | 42 | <https://www.advancednutrients.com/products/> |
| General Hydroponics | 28 | <https://generalhydroponics.com/products> |
| CANNA | 28 | <https://other.canna.com/products> |
| Athena | 14 | <https://store.athenaag.com/> |
| Terra Aquatica | 35 | <https://www.terraaquatica.com/products/> |
| House & Garden | 21 | <https://house-garden.us/products/> |
| Plagron | 23 | <https://plagron.com/en/hobby/products> |
| Biobizz | 13 | <https://biobizz.com/products/> |
| Green House Feeding | 10 | <https://www.greenhousefeeding.com/en/> |
| Mills Nutrients | 6 | <https://millsnutrients.com/category/products/> |
| Grotek | 21 | <https://www.grotek.com/products/> |
| Remo Nutrients | 8 | <https://www.remonutrients.com/> |
| Hesi | 11 | <https://hesi.nl/> |
| Dutchpro | 21 | <https://dutchpro.com/en/producten/> |
| FoxFarm | 14 | <https://foxfarm.com/> |
| Botanicare | 20 | <https://www.botanicare.com/category/products/> |
| Emerald Harvest | 18 | <https://emeraldharvest.co/about/product-overview/> |
| Jack's Nutrients | 12 | <https://www.jacksnutrients.com/online-store/Jacks-Nutrients-FeED-c42781056> |
| FloraFlex | 6 | <https://www.floraflex.com/dry-nutrients> |
| Cyco | 16 | <https://cycoflower.com/brochure/CYCO-brochure-english.pdf> |

Each record stores brand, line, product/part identity, category, growth phase,
compatible medium, physical form, input type, a short purpose, official source,
and verification date. NPK is populated only when the manufacturer publishes an
unambiguous value. Labels and guaranteed analyses can vary by country; the
physical product label and current manufacturer feed chart remain authoritative.

Automatic dosing never follows catalogue text. A product must first be copied
into the user's list, assigned to a plant and stage, mapped to a physical pump,
and calibrated. The automatic control engine remains disabled.

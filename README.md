# Optimiseur de tournées techniciens — démo Axione

Outil web qui transforme une liste de sites (Excel/CSV avec GPS) en tournées
optimisées pour des techniciens : minimise les kilomètres, respecte les
contraintes (nb de techniciens, période, départ, km max, horaires), et exporte
le planning. Carte interactive + export Excel/CSV.

## Lancer
```bash
pip install -r requirements.txt
streamlit run app.py
```
L'appli s'ouvre sur http://localhost:8501

## Fichier d'entrée
Excel ou CSV avec (au minimum) : nom du site, adresse, ville, code postal,
latitude, longitude. Les colonnes sont reconnues automatiquement.
Un fichier `Fichier_démo.xlsx` (79 sites télécom) est fourni pour tester.

## Structure
```
app.py              interface (Streamlit, charte Axione)
engine.py           moteur d'optimisation (OR-Tools)
.streamlit/config.toml   thème couleurs
requirements.txt    dépendances
Fichier_démo.xlsx   jeu de test
```

## Réglages disponibles
Nombre de techniciens · période (1 à 5 jours) · point de départ (adresse Axione,
barycentre, ou chacun chez soi) · km max par tournée · sites max par tournée ·
amplitude horaire · pause déjeuner · durée par site · filtre par département ·
coût du km (pour estimer l'économie en €).


## Nouveautés (version pro)
- **Distances routières réelles GRATUITES** via OSRM (aucune clé, aucun coût). Repli
  automatique sur estimation si le service est momentanément indisponible.
- **Point de départ cliquable sur la carte** : choisissez le dépôt en cliquant.
- **Lien Google Maps par tournée** : le technicien ouvre l'itinéraire et navigue.
  Liens aussi exportés dans l'onglet « Liens_Maps » du fichier Excel.

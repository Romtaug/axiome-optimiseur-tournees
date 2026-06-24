"""
app.py — Optimiseur de tournées techniciens (interface)
Lancement : streamlit run app.py    |    Dépend de engine.py
Charte Axione : bleu nuit #201E5B, vert turquoise #00ECA6.
"""

import io
import requests
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

import engine as e

NUIT, NUIT2, VERT, BLANC = "#201E5B", "#2A2770", "#00ECA6", "#FFFFFF"

st.set_page_config(page_title="Axione — Optimiseur de tournées", page_icon="🛰️", layout="wide")

st.markdown(f"""
<style>
  .stApp {{ background:{NUIT}; color:{BLANC}; }}
  section[data-testid="stSidebar"] {{ background:{NUIT2}; }}
  h1,h2,h3,h4,p,label,span,div {{ color:{BLANC}; }}
  .axione-logo {{ font-size:34px; font-weight:800; letter-spacing:1px; }}
  .axione-logo .o {{ color:{VERT}; }}
  .axione-tag {{ color:#B9B7E0; font-size:13px; margin-top:-8px; letter-spacing:2px; }}
  .accent {{ height:4px; width:60px; background:{VERT}; border-radius:3px; margin:8px 0 18px; }}
  .kpi {{ background:{NUIT2}; border-radius:16px; padding:18px; text-align:center; border:1px solid #3A3690; }}
  .kpi .v {{ font-size:30px; font-weight:800; color:{VERT}; }}
  .kpi .l {{ font-size:13px; color:#B9B7E0; }}
  .stButton>button {{ background:{VERT}; color:{NUIT}; font-weight:800; border:none; border-radius:30px; padding:10px 26px; }}
  .stButton>button:hover {{ background:#00FFB4; color:{NUIT}; }}
  .stDownloadButton>button {{ background:transparent; color:{VERT}; border:2px solid {VERT}; border-radius:30px; font-weight:700; }}
  div[data-testid="stMetricValue"] {{ color:{VERT}; }}
  [data-testid="stFileUploaderDropzone"] {{ background:{NUIT2} !important; border:1px dashed {VERT} !important; color:{BLANC} !important; }}
  [data-testid="stFileUploaderDropzone"] * {{ color:{BLANC} !important; }}
  .stTextInput input, .stNumberInput input, textarea {{ background:{NUIT2} !important; color:{BLANC} !important; border:1px solid #3A3690 !important; }}
  div[data-baseweb="select"] > div, div[data-baseweb="input"] > div {{ background:{NUIT2} !important; color:{BLANC} !important; border-color:#3A3690 !important; }}
  div[data-baseweb="popover"], ul[role="listbox"] {{ background:{NUIT2} !important; color:{BLANC} !important; }}
  div[data-baseweb="tag"] {{ background:{VERT} !important; color:{NUIT} !important; }}
  [data-testid="stExpander"] {{ background:{NUIT2} !important; border:1px solid #3A3690 !important; border-radius:12px !important; }}
  [data-testid="stExpander"] summary {{ color:{BLANC} !important; }}
  [data-testid="stDataFrame"], [data-testid="stTable"] {{ background:{NUIT2} !important; }}
  .stRadio, .stCheckbox, .stSlider {{ color:{BLANC} !important; }}
  [data-testid="stWidgetLabel"] p {{ color:{BLANC} !important; }}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div style="background:linear-gradient(120deg,{NUIT} 0%,#2A2770 60%,#322B86 100%);
     border-radius:20px;padding:26px 30px;margin-bottom:8px;border:1px solid #3A3690;">
  <div class="axione-logo">axi<span class="o">o</span>ne</div>
  <div class="axione-tag">ANIMONS LE MONDE</div>
  <div style="font-size:30px;font-weight:800;margin-top:14px;">Optimiseur de tournées
     <span style="color:{VERT}">techniciens</span></div>
  <div class="accent"></div>
  <div style="color:#C9C7EC;max-width:760px;">Importez vos sites, réglez vos contraintes,
     obtenez les tournées les plus courtes - distances routières réelles, carte interactive
     et itinéraire Google Maps pour chaque technicien.</div>
</div>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def geocoder_lot(queries):
    """Géocode une liste d'adresses en un seul appel via la BAN (CSV bulk, gratuit)."""
    import io as _io, csv as _csv
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["adresse"])
    for q in queries:
        w.writerow([q])
    try:
        r = requests.post("https://api-adresse.data.gouv.fr/search/csv/",
                          files={"data": ("a.csv", buf.getvalue())},
                          data={"columns": ["adresse"]},
                          headers={"User-Agent": "axione-tournees"}, timeout=40)
        res = pd.read_csv(_io.StringIO(r.text), dtype=str)
        lats = pd.to_numeric(res.get("latitude"), errors="coerce").tolist()
        lons = pd.to_numeric(res.get("longitude"), errors="coerce").tolist()
        return lats, lons
    except Exception:
        return None, None


@st.cache_data(show_spinner=False)
def ban_search(q):
    """Suggestions d'adresses via la Base Adresse Nationale (gratuit, sans clé)."""
    if len(q.strip()) < 4:
        return []
    try:
        r = requests.get("https://api-adresse.data.gouv.fr/search/",
                         params={"q": q.strip(), "limit": 5, "autocomplete": 1},
                         headers={"User-Agent": "axione-tournees"}, timeout=6)
        out = []
        for feat in r.json().get("features", []):
            p = feat["properties"]; co = feat["geometry"]["coordinates"]
            dept = (p.get("context", "").split(",")[0].strip())
            out.append({"label": p.get("label", ""), "dept": dept[:2],
                        "lat": round(co[1], 7), "lon": round(co[0], 7)})
        return out
    except Exception:
        return []


@st.cache_data(show_spinner=False)
def geocoder(adresse):
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params={"q": adresse, "format": "json", "limit": 1},
                         headers={"User-Agent": "axione-tournees"}, timeout=6)
        d = r.json()
        if d:
            return float(d[0]["lat"]), float(d[0]["lon"])
    except Exception:
        return None
    return None


# ── 1. Données ──
st.markdown("### 1 · Vos sites")
f = st.file_uploader("Fichier Excel des sites (nom, adresse, ville, code postal, "
                     "latitude, longitude)", type=["xlsx", "xls", "csv"])

df_raw = None
if f is not None:
    df_raw = pd.read_csv(f) if f.name.endswith("csv") else pd.read_excel(f)

if df_raw is None:
    st.info("Importez un fichier de sites (Excel ou CSV) pour commencer.")
    st.stop()

sites = e.normaliser(df_raw)

# Géocodage automatique des sites sans coordonnées
manque = sites["lat"].isna() | sites["lon"].isna()
n_manque = int(manque.sum())
if n_manque:
    a_geocoder = sites.loc[manque & (sites["q_geo"].str.len() > 3)]
    if len(a_geocoder):
        with st.spinner(f"Géocodage de {len(a_geocoder)} adresses…"):
            lats, lons = geocoder_lot(list(a_geocoder["q_geo"]))
        if lats is not None:
            for pos, idx in enumerate(a_geocoder.index):
                if pos < len(lats) and pd.notna(lats[pos]):
                    sites.at[idx, "lat"] = lats[pos]
                    sites.at[idx, "lon"] = lons[pos]

avant = len(sites)
sites = sites.dropna(subset=["lat", "lon"]).reset_index(drop=True)
ignores = avant - len(sites)
if ignores:
    st.warning(f"{ignores} site(s) sans adresse exploitable ont été ignorés.")
if sites.empty:
    st.error("Aucun site géolocalisable dans ce fichier."); st.stop()
st.success(f"{len(sites)} sites prêts (coordonnées trouvées).")

# ── 2. Paramètres ──
st.markdown("### 2 · Réglages")

ce1, ce2 = st.columns(2)
with ce1:
    adresse_depot = st.text_input("Adresse de départ",
                                  value="5 Route du Fief, 69780 Toussieu",
                                  key="addr_query")
    sel = st.session_state.get("depot_sel")
    if not (sel and sel["label"] == adresse_depot):
        for s in ban_search(adresse_depot):
            if st.button(f"📍 {s['label']}", key=f"sg_{s['label']}", use_container_width=True):
                st.session_state["depot_sel"] = s
                st.rerun()
    sel = st.session_state.get("depot_sel")
    if sel:
        st.caption(f"✅ Adresse retenue : {sel['label']} ({sel['lat']:.4f}, {sel['lon']:.4f})")
with ce2:
    sites_jour = st.slider("Sites à visiter par jour", 1, 15, 5)

depts = e.departements(sites)

with st.expander("Options supplémentaires"):
    oc = st.columns(3)
    with oc[0]:
        n_techs = st.number_input("Nombre de techniciens", 1, 50, 1)
        n_jours = st.number_input("Nombre de jours", 1, 30, 1)
        depot_choix = st.radio("Point de départ", [
            "Adresse saisie ci-dessus", "Choisir sur la carte",
            "Barycentre des sites", "Chacun chez soi (tournées ouvertes)"])
    with oc[1]:
        amplitude = st.slider("Amplitude horaire (heures)", 6, 20, (8, 17))
        pause = st.slider("Pause déjeuner (min)", 0, 120, 60, step=15)
        duree = st.slider("Durée par site (min)", 10, 180, 30, step=5)
    with oc[2]:
        max_km = st.number_input("Km max par tournée (0 = illimité)", 0, 2000, 0, step=10)
        sel_depts = st.multiselect("Filtrer par département", depts, default=depts)
        cout_km = st.number_input("Coût du km (€)", 0.0, 5.0, 0.40, 0.05)
        routier_reel = st.toggle("Distances routières réelles (gratuit)", value=True)

max_sites = int(sites_jour)

sites_f = sites[sites["dept"].isin(sel_depts)].reset_index(drop=True) if sel_depts else sites

depot = None
depot_mode = "depot"
if depot_choix == "Adresse saisie ci-dessus" and adresse_depot:
    sel = st.session_state.get("depot_sel")
    if sel and sel["label"] == adresse_depot:
        depot = (sel["lat"], sel["lon"])
    else:
        cand = ban_search(adresse_depot)
        if cand:
            depot = (cand[0]["lat"], cand[0]["lon"])
            st.caption(f"📍 Adresse localisée : {cand[0]['label']}")
        else:
            g = geocoder(adresse_depot)
            if g:
                depot = g
            else:
                st.warning("Adresse non localisée : on utilise le barycentre des sites.")
elif depot_choix == "Choisir sur la carte":
    st.markdown("##### 📍 Cliquez sur la carte pour placer le point de départ")
    cdef = st.session_state.get("depot_clic",
                                [float(sites_f["lat"].mean()), float(sites_f["lon"].mean())])
    pick = folium.Map(location=cdef, zoom_start=9, tiles="cartodbpositron")
    folium.Marker(cdef, tooltip="Départ", icon=folium.Icon(color="green", icon="play")).add_to(pick)
    for _, s in sites_f.iterrows():
        folium.CircleMarker([s["lat"], s["lon"]], radius=3, color=VERT, fill=True,
                            fill_opacity=0.7).add_to(pick)
    clic = st_folium(pick, height=320, use_container_width=True, key="pickmap")
    if clic and clic.get("last_clicked"):
        st.session_state["depot_clic"] = [clic["last_clicked"]["lat"], clic["last_clicked"]["lng"]]
        cdef = st.session_state["depot_clic"]
    depot = tuple(cdef)
    st.caption(f"Point de départ : {cdef[0]:.4f}, {cdef[1]:.4f}")
elif depot_choix.startswith("Chacun"):
    depot_mode = "ouverte"

# ── 3. Optimisation ──
st.markdown("### 3 · Optimisation")
if st.button("⚙️  Calculer les tournées optimisées"):
    params = dict(n_techs=int(n_techs), n_jours=int(n_jours), depot=depot,
                  depot_mode=depot_mode, max_km_tour=int(max_km), max_sites_tour=int(max_sites),
                  h_debut=amplitude[0]*60, h_fin=amplitude[1]*60, pause_dej=int(pause),
                  duree_site=int(duree), vitesse_kmh=50, cout_km=float(cout_km),
                  routing_reel=bool(routier_reel), temps_max_s=12)
    with st.spinner("Calcul en cours…"):
        routes, stats = e.optimiser(sites_f, params)
    if stats["status"] != "OK":
        st.error(stats["status"]); st.stop()
    st.session_state["res"] = (routes, stats, params)

# ── Résultats ──
if "res" in st.session_state:
    routes, stats, params = st.session_state["res"]
    base = e.baseline_km(sites_f, params, set(routes["site_id"])) if not routes.empty else 0
    gain = (base - stats["total_km"]) / base * 100 if base else 0
    km_eco = max(0, base - stats["total_km"])
    co2_evite = km_eco * 0.15
    h_conduite = stats["total_km"] / 50

    st.markdown("## Résultats")
    st.markdown('<div class="accent"></div>', unsafe_allow_html=True)
    k = st.columns(4)
    kpis = [("Km optimisés", f"{stats['total_km']:.0f} km"),
            ("Gain vs non optimisé", f"{gain:.0f} %"),
            ("Économie estimée", f"{stats.get('cout_total', 0):.0f} €" if cout_km else "—"),
            ("CO₂ évité", f"{co2_evite:.0f} kg")]
    for col, (l, v) in zip(k, kpis):
        col.markdown(f'<div class="kpi"><div class="v">{v}</div><div class="l">{l}</div></div>',
                     unsafe_allow_html=True)
    k2 = st.columns(4)
    sub_kpis = [("Tournées", f"{stats['n_tournees']}"),
                ("Sites planifiés", f"{stats['n_planifies']}/{stats['n_sites']}"),
                ("Km économisés", f"{km_eco:.0f} km"),
                ("Heures de conduite", f"{h_conduite:.1f} h")]
    for col, (l, v) in zip(k2, sub_kpis):
        col.markdown(f'<div class="kpi" style="padding:12px"><div class="v" style="font-size:22px">{v}</div>'
                     f'<div class="l">{l}</div></div>', unsafe_allow_html=True)

    if stats["n_non_planifies"]:
        st.info(f"{stats['n_planifies']} sites planifiés sur {stats['n_sites']}. "
                "Pour en visiter plus, augmentez le nombre de jours ou de techniciens "
                "dans « Options supplémentaires ».")
    if stats.get("routier_reel"):
        st.caption("✅ Distances routières réelles (OSRM, gratuit).")
    else:
        st.caption("ℹ️ Distances estimées (vol d'oiseau × 1,3) - service routier indisponible "
                   "ou option désactivée.")
    st.caption("ℹ️ Le « non optimisé » est une organisation sans regroupement géographique. "
               "Le gain réel face à une planification manuelle se situe en général entre 15 et 30 %.")

    st.markdown("### 🗺️ Carte des tournées")
    from folium.plugins import AntPath
    centre = [sites_f["lat"].mean(), sites_f["lon"].mean()]
    fmap = folium.Map(location=centre, zoom_start=9, tiles="cartodbpositron")
    palette = [VERT, "#FF6B6B", "#4D96FF", "#FFD93D", "#A66CFF", "#FF9F45", "#6BCB77",
               "#F178B6", "#43C6DB", "#E84393", "#FFB562", "#7AE7C7", "#FF8DC7", "#62B6FF", "#B5E48C"]
    depot_pt = stats.get("depot")
    if depot_pt:
        folium.Marker(list(depot_pt), tooltip="Départ",
                      icon=folium.Icon(color="green", icon="play", prefix="fa")).add_to(fmap)
    groupes = list(routes.groupby(["technicien", "jour"]))
    legende = []
    for i, ((tech, jour), sub) in enumerate(groupes):
        col = palette[i % len(palette)]
        sub = sub.sort_values("ordre")
        chemin = ([list(depot_pt)] if depot_pt else []) + list(zip(sub["lat"], sub["lon"]))
        AntPath(chemin, color=col, weight=4, opacity=0.9, delay=800,
                tooltip=f"{tech} — jour {jour}").add_to(fmap)
        for _, r in sub.iterrows():
            folium.Marker([r["lat"], r["lon"]],
                tooltip=f"{tech} J{jour} · arrêt {int(r['ordre'])} · {r['nom']}",
                icon=folium.DivIcon(html=(
                    f'<div style="background:{col};color:#201E5B;border:2px solid white;'
                    f'border-radius:50%;width:22px;height:22px;line-height:18px;text-align:center;'
                    f'font-weight:800;font-size:11px;box-shadow:0 1px 4px rgba(0,0,0,.4)">{int(r["ordre"])}</div>'))
            ).add_to(fmap)
        legende.append((f"{tech} · J{jour}", col))
    st_folium(fmap, height=540, use_container_width=True)
    chips = "".join(
        f'<span style="display:inline-block;margin:3px 8px 3px 0;font-size:12px;color:#fff">'
        f'<span style="display:inline-block;width:12px;height:12px;border-radius:3px;'
        f'background:{c};margin-right:5px;vertical-align:middle"></span>{n}</span>'
        for n, c in legende)
    st.markdown(chips, unsafe_allow_html=True)

    st.markdown("### 📥 Export")
    recap = []
    ouverte_flag = params.get("depot_mode") == "ouverte"
    for (tech, jour), sub in groupes:
        url = e.lien_google_maps(stats.get("depot"), sub, "driving", ouverte_flag)
        recap.append({"technicien": tech, "jour": jour, "nb_sites": len(sub),
                      "km": round(sub["km_segment"].sum(), 1), "lien_google_maps": url})
    recap_df = pd.DataFrame(recap)

    def to_excel(routes_df, recap_df):
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            routes_df.to_excel(w, index=False, sheet_name="Tournees")
            recap_df.to_excel(w, index=False, sheet_name="Liens_Maps")
        return buf.getvalue()
    d1, d2 = st.columns(2)
    d1.download_button("Télécharger Excel (tournées + liens Maps)",
                       to_excel(routes, recap_df), "tournees_optimisees.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    d2.download_button("Télécharger CSV", routes.to_csv(index=False).encode("utf-8"),
                       "tournees_optimisees.csv", "text/csv")

    st.markdown("### Feuilles de route")
    ouverte = params.get("depot_mode") == "ouverte"
    depot_pt = stats.get("depot")
    for (tech, jour), sub in groupes:
        sub = sub.sort_values("ordre")
        km_t = sub["km_segment"].sum()
        duree_t = len(sub) * params.get("duree_site", 30) + (km_t / 50) * 60
        with st.expander(f"{tech} — jour {jour} · {len(sub)} sites · "
                         f"{km_t:.0f} km · ≈{duree_t/60:.1f} h"):
            url = e.lien_google_maps(depot_pt, sub, mode="driving", ouverte=ouverte)
            if url:
                st.link_button("🧭 Ouvrir cette tournée dans Google Maps", url)
            st.dataframe(sub[["ordre", "site_id", "nom", "ville", "dept", "km_segment"]],
                         hide_index=True, use_container_width=True)

st.markdown("---")
st.markdown("### Comment ça marche")
st.markdown("**1.** Importez votre fichier de sites (Excel/CSV avec coordonnées GPS).  \n"
            "**2.** Réglez vos contraintes : techniciens, période, départ, km max, horaires.  \n"
            "**3.** L'algorithme calcule les tournées les plus courtes et les affiche sur la carte.  \n"
            "**4.** Exportez le planning prêt à distribuer aux équipes.")
st.markdown("<p style='color:#8784BE;font-size:12px;'>© 2026 — Outil d'optimisation de "
            "tournées · propulsé par OR-Tools</p>", unsafe_allow_html=True)

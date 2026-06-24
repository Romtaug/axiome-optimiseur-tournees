"""
engine.py — Moteur d'optimisation de tournées techniciens
Logique pure (pas d'interface). Utilisé par app.py.
"""

import math
import pandas as pd
import numpy as np
from ortools.constraint_solver import routing_enums_pb2, pywrapcp

ROAD_FACTOR = 1.3  # majoration vol d'oiseau -> distance routière approx


def normaliser(df):
    """Mappe un fichier de sites (colonnes variables) vers un format standard."""
    def find(cols, *cands):
        for c in cols:
            cl = str(c).lower().strip().replace("*", "")
            for cand in cands:
                if cand in cl:
                    return c
        return None

    cols = df.columns
    c_id   = find(cols, "site", "id", "code")
    c_nom  = find(cols, "nom", "name", "libell")
    c_adr  = find(cols, "adresse", "rue", "address")
    c_ville= find(cols, "ville", "commune", "city")
    c_cp   = find(cols, "code postal", "cp", "postal", "zip")
    c_lat  = find(cols, "lat")
    c_lon  = find(cols, "lon", "lng", "long")

    out = pd.DataFrame()
    out["id"]   = df[c_id].astype(str) if c_id else [f"S{i+1}" for i in range(len(df))]
    out["nom"]  = df[c_nom].astype(str) if c_nom else out["id"]
    out["adresse"] = df[c_adr].astype(str) if c_adr else ""
    out["ville"]= df[c_ville].astype(str) if c_ville else ""
    out["cp"]   = df[c_cp] if c_cp else ""
    out["lat"]  = pd.to_numeric(df[c_lat], errors="coerce") if c_lat else np.nan
    out["lon"]  = pd.to_numeric(df[c_lon], errors="coerce") if c_lon else np.nan

    def dept(cp):
        s = str(cp).split(".")[0].zfill(5)
        return s[:2] if s[:2].isdigit() else ""
    out["dept"] = out["cp"].apply(dept)

    def _q(row):
        bits = [str(row["adresse"]).strip(),
                str(row.get("cp", "")).split(".")[0].strip(),
                str(row["ville"]).strip()]
        q = " ".join(b for b in bits if b and b.lower() != "nan")
        if not q:
            nom = str(row["nom"]).strip()
            q = nom if nom and nom.lower() != "nan" else ""
        return q
    out["q_geo"] = out.apply(_q, axis=1)

    return out.reset_index(drop=True)


def departements(df):
    return sorted([d for d in df["dept"].unique() if d])


def _haversine_km(la1, lo1, la2, lo2):
    R = 6371.0
    p1, p2 = math.radians(la1), math.radians(la2)
    dphi = math.radians(la2 - la1)
    dl = math.radians(lo2 - lo1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a)) * ROAD_FACTOR


def _matrice_km(coords):
    n = len(coords)
    M = np.zeros((n, n))
    for i in range(n):
        for j in range(i+1, n):
            d = _haversine_km(*coords[i], *coords[j])
            M[i][j] = M[j][i] = d
    return M


def optimiser(df_sites, params):
    p = params
    sites = df_sites.reset_index(drop=True)
    n_sites = len(sites)
    if n_sites == 0:
        return pd.DataFrame(), {"status": "Aucun site à optimiser."}

    if p.get("depot"):
        depot = tuple(p["depot"])
    else:
        depot = (float(sites["lat"].mean()), float(sites["lon"].mean()))
    ouverte = p.get("depot_mode") == "ouverte"

    coords = [depot] + list(zip(sites["lat"], sites["lon"]))
    n_nodes = len(coords)

    T_osrm = None
    M = None
    routing_reel = p.get("routing_reel", False)
    if routing_reel:
        M_osrm, T_osrm = _matrices_osrm(coords)
        if M_osrm is not None:
            M = M_osrm
        else:
            T_osrm = None
    if M is None:
        M = _matrice_km(coords)
    p["_reel_ok"] = M is not None and routing_reel and T_osrm is not None

    n_veh = max(1, p["n_techs"]) * max(1, p["n_jours"])
    manager = pywrapcp.RoutingIndexManager(n_nodes, n_veh, 0)
    routing = pywrapcp.RoutingModel(manager)

    vitesse = max(5, p.get("vitesse_kmh", 50))
    duree_site = p.get("duree_site", 30)

    def dist_cb(i, j):
        a, b = manager.IndexToNode(i), manager.IndexToNode(j)
        return int(M[a][b] * 1000)
    dist_idx = routing.RegisterTransitCallback(dist_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(dist_idx)

    max_km = p.get("max_km_tour", 0) or 0
    routing.AddDimension(dist_idx, 0, 10**9, True, "Distance")
    dist_dim = routing.GetDimensionOrDie("Distance")
    if max_km > 0:
        for v in range(n_veh):
            dist_dim.SetSpanUpperBoundForVehicle(int(max_km * 1000), v)

    def temps_cb(i, j):
        a, b = manager.IndexToNode(i), manager.IndexToNode(j)
        if T_osrm is not None:
            trajet = T_osrm[a][b]
        else:
            trajet = (M[a][b] / vitesse) * 60.0
        service = duree_site if b != 0 else 0
        return int(trajet + service)
    temps_idx = routing.RegisterTransitCallback(temps_cb)
    routing.AddDimension(temps_idx, 0, 10**7, True, "Temps")
    temps_dim = routing.GetDimensionOrDie("Temps")
    budget_jour = (p["h_fin"] - p["h_debut"]) - p.get("pause_dej", 0)
    for v in range(n_veh):
        temps_dim.SetSpanUpperBoundForVehicle(int(max(30, budget_jour)), v)

    def demande_cb(i):
        return 0 if manager.IndexToNode(i) == 0 else 1
    dem_idx = routing.RegisterUnaryTransitCallback(demande_cb)
    cap = p.get("max_sites_tour", 0) or int(math.ceil(n_sites / n_veh) + 3)
    routing.AddDimensionWithVehicleCapacity(dem_idx, 0, [cap]*n_veh, True, "Sites")

    if ouverte:
        for v in range(n_veh):
            routing.SetArcCostEvaluatorOfVehicle(
                routing.RegisterTransitCallback(
                    lambda i, j: 0 if manager.IndexToNode(j) == 0 else dist_cb(i, j)), v)

    for node in range(1, n_nodes):
        routing.AddDisjunction([manager.NodeToIndex(node)], 5_000_000)

    sp = pywrapcp.DefaultRoutingSearchParameters()
    sp.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    sp.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    sp.time_limit.FromSeconds(int(p.get("temps_max_s", 10)))
    sol = routing.SolveWithParameters(sp)
    if not sol:
        return pd.DataFrame(), {"status": "Aucune solution trouvée (contraintes trop serrées ?)."}

    rows, total_km = [], 0.0
    for v in range(n_veh):
        tech = v // max(1, p["n_jours"]) + 1
        jour = v % max(1, p["n_jours"]) + 1
        idx = routing.Start(v)
        ordre = 0
        prev = manager.IndexToNode(idx)
        while not routing.IsEnd(idx):
            nxt = sol.Value(routing.NextVar(idx))
            node = manager.IndexToNode(nxt)
            if node != 0:
                km = M[prev][node]
                total_km += km
                ordre += 1
                s = sites.iloc[node-1]
                rows.append({
                    "technicien": f"Tech {tech}", "jour": jour, "ordre": ordre,
                    "site_id": s["id"], "nom": s["nom"],
                    "adresse": s["adresse"], "ville": s["ville"], "dept": s["dept"],
                    "lat": s["lat"], "lon": s["lon"], "km_segment": round(km, 2),
                })
            prev = node
            idx = nxt

    routes = pd.DataFrame(rows)
    planifies = set(routes["site_id"]) if not routes.empty else set()
    non_planifies = [s for s in sites["id"] if s not in planifies]

    stats = {
        "status": "OK", "total_km": round(total_km, 1), "n_sites": n_sites,
        "n_planifies": len(planifies), "n_non_planifies": len(non_planifies),
        "non_planifies": non_planifies,
        "n_tournees": routes.groupby(["technicien", "jour"]).ngroups if not routes.empty else 0,
        "depot": depot, "routier_reel": bool(p.get("_reel_ok")),
    }
    if p.get("cout_km", 0):
        stats["cout_total"] = round(total_km * p["cout_km"], 0)
    return routes, stats


def lien_google_maps(depot, sub, mode="driving", ouverte=False):
    """Lien d'itinéraire Google Maps pour une tournée (sans clé API)."""
    sub = sub.sort_values("ordre")
    pts = []
    if depot:
        pts.append(f"{depot[0]},{depot[1]}")
    for _, r in sub.iterrows():
        pts.append(f"{r['lat']},{r['lon']}")
    if depot and not ouverte:
        pts.append(f"{depot[0]},{depot[1]}")
    if len(pts) < 2:
        return None
    url = "https://www.google.com/maps/dir/" + "/".join(pts)
    modes = {"driving": "3e0", "bicycling": "3e1", "walking": "3e2", "transit": "3e3"}
    url += f"/data=!4m2!4m1!{modes.get(mode, '3e0')}"
    return url


def _matrices_osrm(coords, timeout=12):
    """Distances routières RÉELLES via OSRM (libre, sans clé). Repli haversine si KO."""
    import requests
    locs = ";".join(f"{lo},{la}" for la, lo in coords)
    url = f"https://router.project-osrm.org/table/v1/driving/{locs}"
    try:
        r = requests.get(url, params={"annotations": "distance,duration"}, timeout=timeout)
        d = r.json()
        if d.get("code") != "Ok":
            return None, None
        dist = np.array(d["distances"], dtype=float) / 1000.0
        dur = np.array(d["durations"], dtype=float) / 60.0
        if np.isnan(dist).any() or np.isnan(dur).any():
            return None, None
        return dist, dur
    except Exception:
        return None, None


def baseline_km(df_sites, params, subset_ids=None):
    """Km 'avant optimisation' : sites dans l'ordre du fichier, répartis naïvement."""
    p = params
    sites = df_sites.reset_index(drop=True)
    if subset_ids is not None:
        sites = sites[sites["id"].isin(subset_ids)].reset_index(drop=True)
    if len(sites) == 0:
        return 0.0
    depot = tuple(p["depot"]) if p.get("depot") else (
        float(sites["lat"].mean()), float(sites["lon"].mean()))
    n_veh = max(1, p["n_techs"]) * max(1, p["n_jours"])
    groupes = np.array_split(np.arange(len(sites)), n_veh)
    total = 0.0
    for g in groupes:
        prev = depot
        for i in g:
            s = sites.iloc[int(i)]
            total += _haversine_km(prev[0], prev[1], s["lat"], s["lon"])
            prev = (s["lat"], s["lon"])
        if p.get("depot_mode") != "ouverte":
            total += _haversine_km(prev[0], prev[1], depot[0], depot[1])
    return round(total, 1)

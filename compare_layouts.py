"""
================================================================================
  compare_layouts.py  —  3-Way Layout Comparison Dashboard  (v4)
  Changes v4:
    • Added Z_REWORK and Z_CuttingTubes as recognized zones
    • KAPPA02, BoB_KAPPA02 added as separate KAPPA machines
    • BoB_P57, P57 added as separate KOMAX machines
    • All BOX_*, Dereeling_tbl*, PC_cuttingtubes, BOXDEL, BOX → INFRA
    • BoB_KAPPA01 / BoB_P57 naming variants handled
    • Radar chart updated with new zone labels
================================================================================
"""

import json, os
from pathlib import Path
import pandas as pd

# ==============================================================================
# CONFIG
# ==============================================================================
LAYOUT_FILES = {
    "Initial"    : "INITIAL_Layout.csv",
    "Algorithme" : "RECOVER_102.csv",
    "Manuel"     : "RECOVER_102BACKUP.csv",
}
OUTPUT_HTML = "layout_comparison.html"

ZONE_COLORS_DEF = {
    "Z_A"          : "#378ADD",
    "Z_FREE"       : "#1D9E75",
    "Z_B"          : "#378ADD",
    "Z_REWORK"     : "#E57373",
    "Z_CuttingTubes": "#8D6E63",
}

POUTRE = {
    "name":"poutre",
    "xmin": 2905.9809, "xmax": 3001.1555,
    "ymin": 1118.7542, "ymax": 1213.9288,
}
POUTRE["cx"] = (POUTRE["xmin"] + POUTRE["xmax"]) / 2
POUTRE["cy"] = (POUTRE["ymin"] + POUTRE["ymax"]) / 2
POUTRE["w"]  =  POUTRE["xmax"] - POUTRE["xmin"]
POUTRE["h"]  =  POUTRE["ymax"] - POUTRE["ymin"]

OPERATOR_WAGE_MAD_HR = 17.92
HOURS_PER_DAY        = 7.67
DAYS_PER_WEEK        = 5.75
WEEKLY_WAGE          = OPERATOR_WAGE_MAD_HR * HOURS_PER_DAY * DAYS_PER_WEEK

# ==============================================================================
# FAMILY MAP  — all names from all 3 CSVs
# ==============================================================================
FAMILY_MAP = {
    # ── Infrastructure / support ──────────────────────────────────────────────
    "METZNER_10":"INFRA", "SM30_04":"INFRA", "METZNER_05":"INFRA",
    "SM15_12":"INFRA",    "SM15_08":"INFRA", "SM15_07":"INFRA",
    "SM15_11":"INFRA",    "SM15_06":"INFRA", "HSGM_02":"INFRA",
    "HSGM_01":"INFRA",    "pagoda":"INFRA",  "SMED02_P75":"INFRA",
    "SMED_P57":"INFRA",   "PC-A":"INFRA",    "PC_B":"INFRA",
    "poutre":"OBSTACLE",
    "mangera":"INFRA",    "Bubble_Test":"INFRA",
    "BoB_KAPPA01":"INFRA","REWORK_03":"INFRA",
    # Cutting-tubes zone infrastructure
    "BOX_1":"INFRA",  "BOX_2":"INFRA",  "BOX_3":"INFRA",  "BOX_4":"INFRA",
    "BOX_5":"INFRA",  "BOX_6":"INFRA",  "BOX_7":"INFRA",  "BOX_8":"INFRA",
    "BOX_9":"INFRA",  "BOX_10":"INFRA",
    "BOX_01":"INFRA","BOX_02":"INFRA","BOX_04":"INFRA","BOX_05":"INFRA",
    "BOX_06":"INFRA","BOX_07":"INFRA","BOX_08":"INFRA","BOX_11":"INFRA",
    "BOX_12":"INFRA","BOXDEL":"INFRA","BOX":"INFRA",
    "PC_cuttingtubes":"INFRA",
    "Dereeling_tbl10":"INFRA","Dereeling_tbl04":"INFRA","Dereeling_tbl05":"INFRA",
    "Dereeling_tbl12":"INFRA","Dereeling_tbl08":"INFRA","Dereeling_tbl11":"INFRA",
    "Dereeling_tb11":"INFRA", "Dereeling_tbl06":"INFRA",
    # Rework zone infra
    "WORKMAN_A":"WORKSTATION",
    # Zones
    "Z_FREE":"_ZONE","Z_A":"_ZONE","Z_B":"_ZONE","Z_NEW":"_ZONE",
    "Z_REWORK":"_ZONE","Z_CuttingTubes":"_ZONE",
    "PRESSE_03":"PRESSE",

    # ── Active production machines ────────────────────────────────────────────
    "P19+Ref":"ELOPAR",   "P18+Ref":"ELOPAR",   "P17+Ref":"ELOPAR",
    "P16+Ref":"ELOPAR",   "P16-B+Ref":"ELOPAR",
    # KOMAX family — P57 line now split into machine + BoB
    "ToTaL_P57":"KOMAX",
    "P57":"KOMAX",        "BoB_P57":"INFRA",
    # KAPPA family — KAPPA02 line now split into machine + BoB
    "BoB+KAPPA01":"KAPPA","BoB+KAPPA02":"INFRA",
    "KAPPA02":"KAPPA",  
    "P34":"BT722","P35":"BT722","P37":"BT752",
    "P10":"HANKE","P12":"HANKE","P13":"HANKE","P11":"HANKE",
    "P08":"MECAL","P07":"MECAL","P04":"MECAL","P05":"MECAL",
    "P09":"MECAL","P02":"MECAL","P14":"MECAL",
    "P20":"DINEFER","P25":"DINEFER",
    "P15-B":"PASSE_FIL","P15":"PASSE_FIL",
    "P21":"RAYCHEM","P22":"RAYCHEM","P23":"RAYCHEM","P24":"RAYCHEM",
    "P01":"SEAL",
    "CONTENTION":"CONTENTION",
}

EXCLUDED_FAMILIES = {"_ZONE", "INFRA", "OBSTACLE"}

# Canvas colors per family
FAM_CANVAS_COLORS = {
    "_ZONE"      : "transparent",
    "OBSTACLE"   : "#8B4513",
    "INFRA"      : "#9E9E9E",
    "WORKSTATION": "#FF9800",
    "PRESSE"     : "#9C27B0",
    "CONTENTION" : "#E91E63",
    "KAPPA"      : "#1565C0",
    "KOMAX"      : "#1565C0",
    "ELOPAR"     : "#2E7D32",
    "RAYCHEM"    : "#EF6C00",
    "DINEFER"    : "#4527A0",
    "HANKE"      : "#00695C",
    "PASSE_FIL"  : "#558B2F",
    "MECAL"      : "#1976D2",
    "SEAL"       : "#AD1457",
    "BT722"      : "#37474F",
    "BT752"      : "#37474F",
    "UNKNOWN"    : "#E91E63",
}

LAYOUT_COLORS = ["#378ADD", "#1D9E75", "#EF9F27"]

# ==============================================================================
# PRODUCTION DATA  (fils/hr per machine)
# ==============================================================================
PRODUCTION = {
    "KAPPA"    :[{"id":"BoB+KAPPA01","fils_hr":328.98},
                 {"id":"BoB+KAPPA02","fils_hr":0},
                 {"id":"KAPPA02",    "fils_hr":0},
                 {"id":"BoB_KAPPA02","fils_hr":0}],
    "KOMAX"    :[{"id":"ToTaL_P57",  "fils_hr":604.44},
                 {"id":"P57",        "fils_hr":604.44},
                 {"id":"BoB_P57",    "fils_hr":0}],
    "ELOPAR"   :[{"id":"P19+Ref","fils_hr":313.32},{"id":"P18+Ref","fils_hr":283.94},
                 {"id":"P17+Ref","fils_hr":365.54},{"id":"P16+Ref","fils_hr":350},
                 {"id":"P16-B+Ref","fils_hr":0}],
    "RAYCHEM"  :[{"id":"P21","fils_hr":339.43},{"id":"P22","fils_hr":352.48},
                 {"id":"P23","fils_hr":156.66},{"id":"P24","fils_hr":0}],
    "DINEFER"  :[{"id":"P20","fils_hr":189.29},{"id":"P25","fils_hr":0}],
    "HANKE"    :[{"id":"P10","fils_hr":84.86},{"id":"P12","fils_hr":169.71},
                 {"id":"P13","fils_hr":189.29},{"id":"P11","fils_hr":104.44}],
    "PASSE_FIL":[{"id":"P15-B","fils_hr":110.97},{"id":"P15","fils_hr":0}],
    "CONTENTION":[{"id":"CONTENTION","fils_hr":2500}],
    "MECAL"    :[{"id":"P08","fils_hr":169.71},{"id":"P07","fils_hr":22.85},
                 {"id":"P04","fils_hr":104.44},{"id":"P05","fils_hr":104.44},
                 {"id":"P09","fils_hr":283.94},{"id":"P02","fils_hr":365.54},
                 {"id":"P14","fils_hr":0}],
    "SEAL"     :[{"id":"P01","fils_hr":832.25}],
    "BT722"    :[{"id":"P34","fils_hr":535.25},{"id":"P35","fils_hr":391.64}],
    "BT752"    :[{"id":"P37","fils_hr":800}],
}

# ==============================================================================
# RELATIONSHIP MATRIX
# ==============================================================================
REL = {
    ("KAPPA","KOMAX"):1,    ("KAPPA","ELOPAR"):1,   ("KAPPA","RAYCHEM"):1,
    ("KAPPA","DINEFER"):1,  ("KAPPA","HANKE"):7,    ("KAPPA","PASSE_FIL"):5,
    ("KAPPA","CONTENTION"):1,("KAPPA","MECAL"):1,   ("KAPPA","SEAL"):5,
    ("KAPPA","BT722"):0,    ("KAPPA","BT752"):0,
    ("KOMAX","ELOPAR"):1,   ("KOMAX","RAYCHEM"):1,  ("KOMAX","DINEFER"):1,
    ("KOMAX","HANKE"):6,    ("KOMAX","PASSE_FIL"):0,("KOMAX","CONTENTION"):1,
    ("KOMAX","MECAL"):6,    ("KOMAX","SEAL"):6,     ("KOMAX","BT722"):0,("KOMAX","BT752"):0,
    ("ELOPAR","RAYCHEM"):7, ("ELOPAR","DINEFER"):1, ("ELOPAR","HANKE"):6,
    ("ELOPAR","PASSE_FIL"):1,("ELOPAR","CONTENTION"):6,("ELOPAR","MECAL"):7,
    ("ELOPAR","SEAL"):3,    ("ELOPAR","BT722"):1,   ("ELOPAR","BT752"):1,
    ("RAYCHEM","DINEFER"):5,("RAYCHEM","HANKE"):3,  ("RAYCHEM","PASSE_FIL"):6,
    ("RAYCHEM","CONTENTION"):7,("RAYCHEM","MECAL"):6,("RAYCHEM","SEAL"):1,
    ("RAYCHEM","BT722"):0,  ("RAYCHEM","BT752"):0,
    ("DINEFER","HANKE"):6,  ("DINEFER","PASSE_FIL"):6,("DINEFER","CONTENTION"):3,
    ("DINEFER","MECAL"):1,  ("DINEFER","SEAL"):3,   ("DINEFER","BT722"):0,("DINEFER","BT752"):0,
    ("HANKE","PASSE_FIL"):7,("HANKE","CONTENTION"):1,("HANKE","MECAL"):3,
    ("HANKE","SEAL"):7,     ("HANKE","BT722"):1,    ("HANKE","BT752"):1,
    ("PASSE_FIL","CONTENTION"):3,("PASSE_FIL","MECAL"):1,("PASSE_FIL","SEAL"):3,
    ("PASSE_FIL","BT722"):1,("PASSE_FIL","BT752"):1,
    ("CONTENTION","MECAL"):1,("CONTENTION","SEAL"):1,("CONTENTION","BT722"):7,
    ("CONTENTION","BT752"):7,
    ("MECAL","SEAL"):7,("MECAL","BT722"):1,("MECAL","BT752"):1,
    ("SEAL","BT722"):1,("SEAL","BT752"):1,
    ("BT722","BT752"):3,
}

# ==============================================================================
# FLOW + WEIGHT
# ==============================================================================
_FLOW  = {}
_MFLOW = 1.0

def _init_flow():
    global _FLOW, _MFLOW
    CONNECTED = [
        ("KAPPA","HANKE"),("KAPPA","SEAL"),("KOMAX","HANKE"),("KOMAX","MECAL"),
        ("KOMAX","SEAL"),("ELOPAR","RAYCHEM"),("ELOPAR","CONTENTION"),
        ("RAYCHEM","HANKE"),("RAYCHEM","PASSE_FIL"),("RAYCHEM","CONTENTION"),
        ("DINEFER","RAYCHEM"),("DINEFER","PASSE_FIL"),("HANKE","ELOPAR"),
        ("HANKE","DINEFER"),("HANKE","CONTENTION"),("PASSE_FIL","HANKE"),
        ("PASSE_FIL","SEAL"),("MECAL","ELOPAR"),("MECAL","RAYCHEM"),
        ("MECAL","CONTENTION"),("SEAL","HANKE"),("SEAL","MECAL"),
        ("BT722","CONTENTION"),("BT752","CONTENTION"),
    ]
    def fam_flow(f1, f2):
        t1 = sum(m["fils_hr"] for m in PRODUCTION.get(f1,[]))
        t2 = sum(m["fils_hr"] for m in PRODUCTION.get(f2,[]))
        return (t1 + t2) / 2.0
    _FLOW  = {(f1,f2): fam_flow(f1,f2) for f1,f2 in CONNECTED}
    _MFLOW = max(_FLOW.values()) if _FLOW else 1.0

def _get_rel(f1, f2):
    return REL.get((f1,f2), REL.get((f2,f1), 0))

def _get_flow(f1, f2):
    return _FLOW.get((f1,f2), _FLOW.get((f2,f1), 0.0))

def combined_weight(f1, f2):
    return _get_rel(f1, f2) + (_get_flow(f1,f2) / _MFLOW) * 4

# ==============================================================================
# ZONE HELPERS
# ==============================================================================
# All 5 zones — bounds auto-read from each CSV; these are fallback defaults
DEFAULT_ZONES = {
    "Z_REWORK"     : {"xmin":1331.6,"xmax":2081.6,"ymin":578.0, "ymax":1278.0,"color":"#E57373"},
    "Z_A"          : {"xmin":2139.2,"xmax":3389.2,"ymin":615.8, "ymax":1185.8,"color":"#378ADD"},
    "Z_FREE"       : {"xmin":2137.8,"xmax":3389.2,"ymin":1756.8,"ymax":2953.3,"color":"#1D9E75"},
    "Z_CuttingTubes": {"xmin":16.2, "xmax":2007.8,"ymin":1756.8,"ymax":2953.3,"color":"#8D6E63"},
    "Z_B"          : {"xmin":3516.2,"xmax":5108.2,"ymin":1386.8,"ymax":2916.8,"color":"#378ADD"},
}

# Ordered for display
ZONE_ORDER = ["Z_REWORK", "Z_A", "Z_CuttingTubes", "Z_FREE", "Z_B"]

def read_zones_from_df(df):
    zones = {}
    for zname, zdef in DEFAULT_ZONES.items():
        row = df[df["Name"] == zname]
        if not row.empty:
            r = row.iloc[0]
            zones[zname] = {
                "xmin" : float(r["Xmin"]),
                "xmax" : float(r["Xmax"]),
                "ymin" : float(r["Ymin"]),
                "ymax" : float(r["Ymax"]),
                "color": zdef["color"],
            }
        else:
            zones[zname] = dict(zdef)
    return zones

def zone_of(cx, cy, zones):
    for name in ZONE_ORDER:        # priority order matters for overlapping zones
        z = zones.get(name)
        if z and z["xmin"] <= cx <= z["xmax"] and z["ymin"] <= cy <= z["ymax"]:
            return name
    return "OUTSIDE"

def zone_area(z):
    return (z["xmax"] - z["xmin"]) * (z["ymax"] - z["ymin"])

# ==============================================================================
# DATA LOADING
# ==============================================================================
def load_csv(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    df = pd.read_csv(path) if not path.endswith((".xlsx",".xls")) else pd.read_excel(path)
    df.columns = df.columns.str.strip()
    df["Name"] = df["Name"].astype(str).str.strip()

    if "CenterX" in df.columns:
        df["cx"] = df["CenterX"].astype(float); df["cy"] = df["CenterY"].astype(float)
        df["w"]  = df["Width"].astype(float);   df["h"]  = df["Height"].astype(float)
    elif "Center X" in df.columns:
        df["cx"] = df["Center X"].astype(float); df["cy"] = df["Center Y"].astype(float)
        df["w"]  = df["Width"].astype(float);    df["h"]  = df["Height"].astype(float)
    else:
        df["cx"] = (df["Xmin"].astype(float) + df["Xmax"].astype(float)) / 2
        df["cy"] = (df["Ymin"].astype(float) + df["Ymax"].astype(float)) / 2
        df["w"]  = (df["Xmax"].astype(float) - df["Xmin"].astype(float)).abs()
        df["h"]  = (df["Ymax"].astype(float) - df["Ymin"].astype(float)).abs()

    zones = read_zones_from_df(df)

    df["family"] = df["Name"].map(FAMILY_MAP)
    unmapped = df[df["family"].isna()]["Name"].tolist()
    if unmapped:
        print(f"  [WARN] Unmapped names → 'INFRA': {unmapped}")
        df["family"] = df["family"].fillna("INFRA")

    machines = []
    for _, r in df.iterrows():
        fam = r["family"]
        cx, cy = float(r["cx"]), float(r["cy"])
        w,  h  = abs(float(r["w"])), abs(float(r["h"]))
        machines.append({
            "name"    : r["Name"],
            "family"  : fam,
            "cx": cx, "cy": cy,
            "w":  w,  "h":  h,
            "area"    : w * h,
            "zone"    : zone_of(cx, cy, zones),
            "excluded": fam in EXCLUDED_FAMILIES,
        })
    return machines, zones

# ==============================================================================
# KPI COMPUTATION
# ==============================================================================
def compute_kpis(machines, zones, ref_cost=None):
    active = [m for m in machines if not m["excluded"]]
    n = len(active)

    coeff = WEEKLY_WAGE / 1e6
    cost, pair_costs = 0.0, []
    for i in range(n):
        for j in range(i+1, n):
            f1, f2 = active[i]["family"], active[j]["family"]
            w = combined_weight(f1, f2)
            if abs(w) < 0.01: continue
            dist = abs(active[i]["cx"]-active[j]["cx"]) + abs(active[i]["cy"]-active[j]["cy"])
            c = w * dist * coeff
            cost += c
            pair_costs.append({"pair":f"{active[i]['name']}↔{active[j]['name']}","cost":c,"w":w,"dist":dist})
    pair_costs.sort(key=lambda x: -x["cost"])

    zoned_active = [m for m in active if m["zone"] != "OUTSIDE"]
    overlaps, max_overlap_depth = [], 0.0
    for i in range(len(zoned_active)):
        for j in range(i+1, len(zoned_active)):
            mi, mj = zoned_active[i], zoned_active[j]
            sep_x = abs(mi["cx"]-mj["cx"]) - (mi["w"]+mj["w"])/2
            sep_y = abs(mi["cy"]-mj["cy"]) - (mi["h"]+mj["h"])/2
            if sep_x < 0 and sep_y < 0:
                ov_x = round(-sep_x,1); ov_y = round(-sep_y,1)
                depth = round(min(ov_x,ov_y),1)
                overlaps.append({
                    "pair":f"{mi['name']} / {mj['name']}",
                    "ov_x":ov_x,"ov_y":ov_y,"depth":depth,
                    "area":round(ov_x*ov_y,0),
                    "zone1":mi["zone"],"zone2":mj["zone"],
                })
                max_overlap_depth = max(max_overlap_depth, depth)
    overlaps.sort(key=lambda x: -x["depth"])

    zone_stats = {}
    for zname in ZONE_ORDER:
        z = zones.get(zname)
        if not z:
            continue
        za = zone_area(z)
        mach_in = [m for m in active if m["zone"] == zname]
        occ = sum(m["area"] for m in mach_in)
        zone_stats[zname] = {
            "zone_area":za,"occupied_area":occ,
            "fill_rate":round(occ/za*100,1) if za>0 else 0,
            "dead_space":za-occ,
            "machine_count":len(mach_in),
            "machines":[m["name"] for m in mach_in],
        }

    outside = [m["name"] for m in active if m["zone"] == "OUTSIDE"]

    family_avg_dist = {}
    all_fams = list({m["family"] for m in active})
    for fam in all_fams:
        members = [m for m in active if m["family"]==fam]
        related = [(f2,_get_rel(fam,f2)) for f2 in all_fams if f2!=fam and _get_rel(fam,f2)>=3]
        if not members or not related: continue
        total_dist, total_w = 0.0, 0.0
        for m in members:
            for f2,rel in related:
                for o in [x for x in active if x["family"]==f2]:
                    d = abs(m["cx"]-o["cx"])+abs(m["cy"]-o["cy"])
                    total_dist += d*rel; total_w += rel
        family_avg_dist[fam] = round(total_dist/total_w,0) if total_w>0 else 0

    improvement_pct = round((ref_cost-cost)/ref_cost*100,1) if ref_cost and ref_cost>0 else 0.0

    return {
        "cost"             : round(cost,2),
        "cost_annual"      : round(cost*52,0),
        "improvement_pct"  : improvement_pct,
        "machine_count"    : n,
        "overlap_count"    : len(overlaps),
        "max_overlap_depth": round(max_overlap_depth,1),
        "overlaps_list"    : overlaps[:10],
        "pair_costs"       : pair_costs[:8],
        "zone_stats"       : zone_stats,
        "outside_count"    : len(outside),
        "outside_list"     : outside,
        "family_avg_dist"  : family_avg_dist,
        "machines"         : active,
        "all_machines"     : machines,
    }

# ==============================================================================
# HTML GENERATION
# ==============================================================================
def _badge(val, ref, lower_is_better=True, fmt=lambda v: str(v)):
    if ref is None or ref == 0:
        return f"<span class='badge badge-neu'>{fmt(val)}</span>"
    delta = val - ref
    pct   = delta / abs(ref) * 100
    cls   = ("badge-good" if (delta<-0.5 if lower_is_better else delta>0.5)
             else ("badge-bad" if (delta>0.5 if lower_is_better else delta<-0.5)
             else "badge-neu"))
    sign  = "+" if delta > 0 else ""
    return f"<span class='badge {cls}'>{fmt(val)} ({sign}{pct:.1f}%)</span>"

def build_html(kpis_list, labels, zones_list):
    layout_count = len(labels)
    ref_kpis     = kpis_list[0]
    ref_zones    = zones_list[0]
    zone_names   = ZONE_ORDER   # always use canonical order

    costs        = [k["cost"] for k in kpis_list]
    overlap_cnts = [k["overlap_count"] for k in kpis_list]
    max_cost     = max(costs) if max(costs)>0 else 1
    max_machines = max(k["machine_count"] for k in kpis_list) or 1
    max_ov       = max(overlap_cnts) or 1

    def radar_vals(kpis):
        cost_inv    = round((1-kpis["cost"]/max_cost)*100,1)
        fill_free   = kpis["zone_stats"].get("Z_FREE",{}).get("fill_rate",0)
        fill_za     = kpis["zone_stats"].get("Z_A",{}).get("fill_rate",0)
        fill_ct     = kpis["zone_stats"].get("Z_CuttingTubes",{}).get("fill_rate",0)
        no_overlap  = round((1-kpis["overlap_count"]/max_ov)*100,1) if max_ov>0 else 100
        placed      = round(kpis["machine_count"]/max_machines*100,1)
        return [cost_inv, fill_free, fill_za, fill_ct, no_overlap, placed]

    radar_data = [{"label":l,"data":radar_vals(k),"color":LAYOUT_COLORS[i]}
                  for i,(k,l) in enumerate(zip(kpis_list,labels))]

    fill_data_arr = [[k["zone_stats"].get(z,{}).get("fill_rate",0) for z in zone_names]
                     for k in kpis_list]

    # ── Global canvas bounds
    all_cx, all_cy = [], []
    for kpis in kpis_list:
        for m in kpis["all_machines"]:
            if m["family"] != "_ZONE":
                all_cx.append(m["cx"]); all_cy.append(m["cy"])
    all_zone_vals = [z for zd in zones_list for z in zd.values()]
    x_min = min([z["xmin"] for z in all_zone_vals] + all_cx) - 180
    x_max = max([z["xmax"] for z in all_zone_vals] + all_cx) + 180
    y_min = min([z["ymin"] for z in all_zone_vals] + all_cy) - 180
    y_max = max([z["ymax"] for z in all_zone_vals] + all_cy) + 180

    CW, CH = 1500, 950

    def nx(v): return round((v-x_min)/(x_max-x_min)*CW, 2)
    def ny(v): return round((1-(v-y_min)/(y_max-y_min))*CH, 2)
    def nw(v): return max(6, round(v/(x_max-x_min)*CW, 2))
    def nh(v): return max(4, round(v/(y_max-y_min)*CH, 2))

    # Per-layout zone canvas data
    zones_canvas_per_layout = []
    for zones in zones_list:
        zc = []
        for zname in ZONE_ORDER:
            z = zones.get(zname)
            if not z:
                continue
            zc.append({
                "name":zname,
                "x":nx(z["xmin"]),"y":ny(z["ymax"]),
                "w":nx(z["xmax"])-nx(z["xmin"]),
                "h":ny(z["ymin"])-ny(z["ymax"]),
                "color":z["color"],
            })
        zones_canvas_per_layout.append(zc)

    # Per-layout machine canvas data
    machines_canvas = []
    for i,(kpis,label) in enumerate(zip(kpis_list,labels)):
        ms = []
        for m in kpis["all_machines"]:
            if m["family"] == "_ZONE": continue
            color = FAM_CANVAS_COLORS.get(m["family"],"#607D8B")
            ms.append({
                "name":m["name"],"family":m["family"],"zone":m["zone"],
                "cx":nx(m["cx"]),"cy":ny(m["cy"]),
                "w":nw(m["w"]),"h":nh(m["h"]),
                "color":color,"excluded":m["excluded"],
            })
        machines_canvas.append({"label":label,"machines":ms,"color":LAYOUT_COLORS[i]})

    def pair_cost_rows(kpis):
        return "".join(
            f"<tr><td>{p['pair']}</td><td>{p['dist']:.0f}cm</td><td>{p['cost']:.3f}</td></tr>"
            for p in kpis["pair_costs"][:6])

    def overlap_rows(kpis):
        if not kpis["overlaps_list"]:
            return "<tr><td colspan='5' style='color:var(--green);text-align:center'>✅ Aucun chevauchement détecté</td></tr>"
        rows = ""
        for ov in kpis["overlaps_list"]:
            zt = ov["zone1"] if ov["zone1"]==ov["zone2"] else f"{ov['zone1']} / {ov['zone2']}"
            c  = ZONE_COLORS_DEF.get(ov["zone1"],"#888")
            rows += (f"<tr><td>{ov['pair']}</td>"
                     f"<td><span class='dot' style='background:{c}'></span>{zt}</td>"
                     f"<td class='bad'>{ov['ov_x']} cm</td>"
                     f"<td class='bad'>{ov['ov_y']} cm</td>"
                     f"<td class='bad'>{ov['depth']} cm</td></tr>")
        return rows

    ZONE_COLORS_DEF = {zn: DEFAULT_ZONES[zn]["color"] for zn in DEFAULT_ZONES}

    def zone_machine_list(kpis, zones):
        rows = ""
        for zname in ZONE_ORDER + ["OUTSIDE"]:
            ms = kpis["outside_list"] if zname=="OUTSIDE" else kpis["zone_stats"].get(zname,{}).get("machines",[])
            if ms:
                c = zones.get(zname,{}).get("color", DEFAULT_ZONES.get(zname,{}).get("color","#888888"))
                rows += (f"<tr><td><span class='dot' style='background:{c}'></span>{zname}</td>"
                         f"<td>{len(ms)}</td><td class='mlist'>{', '.join(ms)}</td></tr>")
        return rows

    # Tab headers
    tab_headers = "".join(
        f'<button class="tab-btn" onclick="showTab({i})">{label}</button>'
        for i,label in enumerate(labels))
    tab_headers += '<button class="tab-btn" onclick="showTab(99)">📊 Comparaison</button>'

    # Per-layout tab panels
    tab_panels = ""
    for i,(kpis,label,zones) in enumerate(zip(kpis_list,labels,zones_list)):
        zs = kpis["zone_stats"]
        ann_economy = round((ref_kpis["cost"]-kpis["cost"])*52, 0)
        impr_pct    = kpis["improvement_pct"]
        impr_cls    = "kpi-good" if impr_pct>0 else ("kpi-bad" if impr_pct<0 else "")
        impr_sign   = "+" if impr_pct>0 else ""
        zone_table_rows = ""
        for zn in zone_names:
            if zn not in zs:
                continue
            zcolor = zones.get(zn,{}).get("color", DEFAULT_ZONES.get(zn,{}).get("color","#888"))
            zone_table_rows += f"""<tr>
              <td><span class="dot" style="background:{zcolor}"></span>{zn}</td>
              <td>{zs[zn]['zone_area']/1e4:.0f} m²</td>
              <td>{zs[zn]['occupied_area']/1e4:.1f} m²</td>
              <td><div class="fill-bar"><div class="fill-inner" style="width:{min(100,zs[zn]['fill_rate'])}%;background:{zcolor}"></div></div>{zs[zn]['fill_rate']}%</td>
              <td>{zs[zn]['dead_space']/1e4:.1f} m²</td>
              <td>{zs[zn]['machine_count']}</td>
            </tr>"""
        tab_panels += f"""
<div class="tab-panel" id="tab-{i}">
  <h2>{label}</h2>
  <div class="kpi-row">
    <div class="kpi-card">
      <div class="kpi-label">Coût hebdo</div>
      <div class="kpi-val">{kpis['cost']:.2f}</div>
      <div class="kpi-sub">MAD·cm / semaine</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Projection annuelle</div>
      <div class="kpi-val">{kpis['cost_annual']:,.0f}</div>
      <div class="kpi-sub">MAD·cm / an</div>
    </div>
    <div class="kpi-card {'kpi-good' if ann_economy>0 else ''}">
      <div class="kpi-label">Économie vs Initial</div>
      <div class="kpi-val">{"+" if ann_economy>=0 else ""}{ann_economy:,.0f}</div>
      <div class="kpi-sub">MAD·cm / an</div>
    </div>
    <div class="kpi-card {impr_cls}">
      <div class="kpi-label">🏆 Score d'amélioration</div>
      <div class="kpi-val">{impr_sign}{impr_pct}%</div>
      <div class="kpi-sub">Réduction coût de déplacement vs Initial</div>
    </div>
    <div class="kpi-card {'kpi-bad' if kpis['overlap_count']>0 else 'kpi-good'}">
      <div class="kpi-label">Chevauchements</div>
      <div class="kpi-val">{kpis['overlap_count']}</div>
      <div class="kpi-sub">{'✅ Aucune superposition' if kpis['overlap_count']==0 else '⚠️ paires en superposition'}</div>
    </div>
    <div class="kpi-card {'kpi-bad' if kpis['max_overlap_depth']>0 else 'kpi-good'}">
      <div class="kpi-label">Profondeur max</div>
      <div class="kpi-val">{kpis['max_overlap_depth']}</div>
      <div class="kpi-sub">cm pénétration (pire paire)</div>
    </div>
    <div class="kpi-card {'kpi-bad' if kpis['outside_count']>0 else 'kpi-good'}">
      <div class="kpi-label">Machines hors zones</div>
      <div class="kpi-val">{kpis['outside_count']}</div>
      <div class="kpi-sub">{"✅ Toutes placées" if kpis['outside_count']==0 else "⚠️ " + ", ".join(kpis['outside_list'][:3])}</div>
    </div>
  </div>

  <div class="two-col">
    <div>
      <h3>Occupation par zone</h3>
      <table class="data-table">
        <thead><tr><th>Zone</th><th>Surface</th><th>Occupée</th><th>Taux</th><th>Dead space</th><th>Machines</th></tr></thead>
        <tbody>{zone_table_rows}</tbody>
      </table>
    </div>
    <div>
      <h3>Top paires coûteuses</h3>
      <table class="data-table">
        <thead><tr><th>Paire</th><th>Distance</th><th>Coût</th></tr></thead>
        <tbody>{pair_cost_rows(kpis)}</tbody>
      </table>
    </div>
  </div>

  <h3>Machines par zone</h3>
  <table class="data-table full-width">
    <thead><tr><th>Zone</th><th>Nb</th><th>Machines</th></tr></thead>
    <tbody>{zone_machine_list(kpis, zones)}</tbody>
  </table>

  <h3>{'⚠️ Chevauchements physiques détectés' if kpis['overlaps_list'] else '✅ Chevauchements physiques'}</h3>
  <table class="data-table full-width">
    <thead><tr><th>Paire</th><th>Zone</th><th>Intrusion X</th><th>Intrusion Y</th><th>Profondeur</th></tr></thead>
    <tbody>{overlap_rows(kpis)}</tbody>
  </table>
</div>"""

    # Comparison tab
    cmp_rows = f"""
<tr><td class='row-label'>Coût hebdo (MAD·cm)</td>{"".join(f"<td>{_badge(k['cost'],ref_kpis['cost'],True,lambda v:f'{v:.2f}')}</td>" for k in kpis_list)}</tr>
<tr><td class='row-label'>Coût annuel (MAD·cm)</td>{"".join(f"<td>{_badge(k['cost_annual'],ref_kpis['cost_annual'],True,lambda v:f'{v:,.0f}')}</td>" for k in kpis_list)}</tr>
<tr><td class='row-label'>🏆 Score d'amélioration</td>{"".join(f"<td><span class='badge {'badge-good' if k['improvement_pct']>0 else ('badge-bad' if k['improvement_pct']<0 else 'badge-neu')}'>{'+' if k['improvement_pct']>0 else ''}{k['improvement_pct']}%</span></td>" for k in kpis_list)}</tr>
<tr><td class='row-label'>Chevauchements</td>{"".join(f"<td>{_badge(k['overlap_count'],ref_kpis['overlap_count'],True,str)}</td>" for k in kpis_list)}</tr>
<tr><td class='row-label'>Profondeur max (cm)</td>{"".join(f"<td>{_badge(k['max_overlap_depth'],ref_kpis['max_overlap_depth'],True,str)}</td>" for k in kpis_list)}</tr>
<tr><td class='row-label'>Machines hors zone</td>{"".join(f"<td>{_badge(k['outside_count'],ref_kpis['outside_count'],True,str)}</td>" for k in kpis_list)}</tr>"""
    for zn in zone_names:
        vals = [k["zone_stats"].get(zn,{}).get("fill_rate",0) for k in kpis_list]
        cmp_rows += f"<tr><td class='row-label'>Fill rate {zn}</td>"
        for ii,v in enumerate(vals):
            cmp_rows += f"<td>{_badge(v, vals[0] if ii>0 else None, False, lambda x:f'{x}%')}</td>"
        cmp_rows += "</tr>"

    tab_panels += f"""
<div class="tab-panel" id="tab-99">
  <h2>Comparaison des {layout_count} Layouts</h2>
  <div class="chart-row">
    <div class="chart-box"><h3>Coût de walking (MAD·cm/sem)</h3>
      <div style="position:relative;height:220px"><canvas id="chart-cost"></canvas></div></div>
    <div class="chart-box"><h3>Taux de remplissage par zone (%)</h3>
      <div style="position:relative;height:220px"><canvas id="chart-fill"></canvas></div></div>
  </div>
  <div class="chart-row">
    <div class="chart-box"><h3>Chevauchements physiques (paires)</h3>
      <div style="position:relative;height:220px"><canvas id="chart-viol"></canvas></div></div>
    <div class="chart-box"><h3>Vue radar — Performance globale</h3>
      <div style="position:relative;height:220px"><canvas id="chart-radar"></canvas></div></div>
  </div>
  <h3>Tableau comparatif</h3>
  <table class="data-table full-width">
    <thead><tr><th>Indicateur</th>{"".join(f'<th>{l}</th>' for l in labels)}</tr></thead>
    <tbody>{cmp_rows}</tbody>
  </table>
  <h3>Vue plan — Toutes les machines</h3>
  <div style="display:flex;gap:8px;margin-bottom:8px;flex-wrap:wrap;align-items:center">
    {"".join(f'<button class="layout-btn" onclick="showLayout({i})" style="border-left:4px solid {LAYOUT_COLORS[i]}">{label}</button>' for i,label in enumerate(labels))}
    <span style="font-size:11px;color:var(--muted);margin-left:6px">Survole une machine pour voir son nom &amp; famille</span>
  </div>
  <div id="canvas-legend" style="display:flex;flex-wrap:wrap;gap:5px 12px;margin-bottom:10px;font-size:11px"></div>
  <div style="overflow-x:auto">
    <canvas id="layout-canvas" width="{CW}" height="{CH}"
      style="border:0.5px solid var(--border);border-radius:8px;width:100%;min-width:700px;display:block"></canvas>
  </div>
  <div id="canvas-tooltip"
    style="position:fixed;background:#1a1a1a;color:#fff;padding:5px 10px;border-radius:5px;
           font-size:12px;pointer-events:none;display:none;z-index:9999;line-height:1.6"></div>
</div>"""

    js_data = f"""
const LABELS               = {json.dumps(labels)};
const LAYOUT_COLORS        = {json.dumps(LAYOUT_COLORS[:layout_count])};
const COSTS                = {json.dumps(costs)};
const OVERLAPS             = {json.dumps(overlap_cnts)};
const ZONE_NAMES           = {json.dumps(zone_names)};
const FILL_DATA            = {json.dumps(fill_data_arr)};
const RADAR_DATA           = {json.dumps(radar_data)};
const ZONES_CANVAS_PER_LYT = {json.dumps(zones_canvas_per_layout)};
const MACHINES_CV          = {json.dumps(machines_canvas)};
const FAM_COLORS           = {json.dumps(FAM_CANVAS_COLORS)};
const CANVAS_W             = {CW};
const CANVAS_H             = {CH};
"""

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Layout Comparison Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
:root{{
  --bg:#f9f9f7;--surface:#fff;--border:rgba(0,0,0,.12);
  --text:#1a1a1a;--muted:#666;--radius:10px;
  --blue:#378ADD;--green:#1D9E75;--amber:#EF9F27;--red:#E24B4A;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);font-size:14px;line-height:1.5}}
.header{{background:var(--surface);border-bottom:.5px solid var(--border);padding:14px 24px;
  position:sticky;top:0;z-index:100;display:flex;align-items:center;gap:14px;flex-wrap:wrap}}
.header h1{{font-size:16px;font-weight:500;flex:1;min-width:0}}
.tab-btn{{padding:7px 14px;border:.5px solid var(--border);border-radius:6px;
  background:transparent;cursor:pointer;font-size:13px;color:var(--muted);white-space:nowrap}}
.tab-btn:hover,.tab-btn.active{{background:var(--blue);color:#fff;border-color:var(--blue)}}
.main{{padding:24px;max-width:1500px;margin:0 auto}}
h2{{font-size:18px;font-weight:500;margin:0 0 16px}}
h3{{font-size:12px;font-weight:700;margin:18px 0 8px;color:var(--muted);
  text-transform:uppercase;letter-spacing:.5px}}
.kpi-row{{display:flex;flex-wrap:nowrap;gap:10px;margin-bottom:20px;
  overflow-x:auto;padding-bottom:4px}}
.kpi-row::-webkit-scrollbar{{height:4px}}
.kpi-row::-webkit-scrollbar-thumb{{background:#ccc;border-radius:2px}}
.kpi-card{{flex:1 0 148px;min-width:148px;max-width:220px;
  background:var(--surface);border:.5px solid var(--border);
  border-radius:var(--radius);padding:13px 15px}}
.kpi-card.kpi-good{{border-left:3px solid var(--green)}}
.kpi-card.kpi-bad{{border-left:3px solid var(--red)}}
.kpi-label{{font-size:11px;color:var(--muted);margin-bottom:4px}}
.kpi-val{{font-size:21px;font-weight:500;line-height:1.2}}
.kpi-sub{{font-size:10px;color:var(--muted);margin-top:3px;line-height:1.4}}
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:16px 0}}
@media(max-width:700px){{.two-col{{grid-template-columns:1fr}}}}
.data-table{{width:auto;border-collapse:collapse;font-size:12px}}
.data-table.full-width{{width:100%}}
.data-table th,.data-table td{{padding:6px 10px;border-bottom:.5px solid var(--border);
  text-align:left;white-space:nowrap}}
.data-table th{{font-weight:700;color:var(--muted);font-size:11px;
  text-transform:uppercase;letter-spacing:.3px}}
.data-table tr:hover td{{background:var(--bg)}}
.row-label{{font-weight:500;white-space:nowrap}}
.badge{{font-size:11px;padding:2px 8px;border-radius:20px;white-space:nowrap}}
.badge-good{{background:#EAF3DE;color:#27500A}}
.badge-bad{{background:#FCEBEB;color:#791F1F}}
.badge-neu{{background:#F1EFE8;color:#444}}
.dot{{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:5px;vertical-align:middle}}
.fill-bar{{background:#eee;border-radius:4px;height:7px;width:70px;display:inline-block;
  vertical-align:middle;margin-right:5px}}
.fill-inner{{height:7px;border-radius:4px}}
.bad{{color:var(--red);font-weight:500}}
.chart-row{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:16px 0}}
@media(max-width:700px){{.chart-row{{grid-template-columns:1fr}}}}
.chart-box{{background:var(--surface);border:.5px solid var(--border);
  border-radius:var(--radius);padding:14px}}
.mlist{{color:var(--muted);font-size:11px;max-width:500px;
  white-space:normal;word-break:break-word}}
.layout-btn{{padding:6px 13px;border:.5px solid var(--border);border-radius:6px;
  background:transparent;cursor:pointer;font-size:12px;margin-bottom:4px}}
.layout-btn.active{{background:#f0f0f0;font-weight:600}}
.tab-panel{{display:none}}.tab-panel.active{{display:block}}
.legend-item{{display:flex;align-items:center;gap:4px;white-space:nowrap}}
.legend-swatch{{width:12px;height:12px;border-radius:2px;flex-shrink:0}}
</style>
</head>
<body>
<div class="header">
  <h1>🏭 Layout Comparison Dashboard</h1>
  <nav style="display:flex;gap:6px;flex-wrap:wrap">{tab_headers}</nav>
</div>
<div class="main">{tab_panels}</div>
<script>
{js_data}

let chartsBuilt = false;
function showTab(idx) {{
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  (idx===99 ? document.getElementById('tab-99') : document.getElementById('tab-'+idx))
    ?.classList.add('active');
  const btns = document.querySelectorAll('.tab-btn');
  if (btns[idx===99 ? LABELS.length : idx]) btns[idx===99 ? LABELS.length : idx].classList.add('active');
  if (idx===99 && !chartsBuilt) {{ buildCharts(); chartsBuilt=true; showLayout(0); buildLegend(); }}
}}
showTab(0);

const hex2rgb = h => {{
  return `${{parseInt(h.slice(1,3),16)}},${{parseInt(h.slice(3,5),16)}},${{parseInt(h.slice(5,7),16)}}`;
}};

function buildCharts() {{
  new Chart(document.getElementById('chart-cost'), {{
    type:'bar',
    data:{{labels:LABELS,datasets:[{{label:'Coût hebdo',data:COSTS,
      backgroundColor:LAYOUT_COLORS.map(c=>`rgba(${{hex2rgb(c)}},0.8)`),
      borderColor:LAYOUT_COLORS,borderWidth:1.5}}]}},
    options:{{responsive:true,maintainAspectRatio:false,
      plugins:{{legend:{{display:false}}}},
      scales:{{y:{{beginAtZero:true,title:{{display:true,text:'MAD·cm/sem'}}}}}}}}
  }});
  new Chart(document.getElementById('chart-fill'), {{
    type:'bar',
    data:{{labels:ZONE_NAMES,datasets:LABELS.map((l,i)=>({{\
      label:l,data:FILL_DATA[i],
      backgroundColor:`rgba(${{hex2rgb(LAYOUT_COLORS[i])}},0.7)`,
      borderColor:LAYOUT_COLORS[i],borderWidth:1}})) }},
    options:{{responsive:true,maintainAspectRatio:false,
      plugins:{{legend:{{position:'bottom',labels:{{boxWidth:10,font:{{size:10}}}}}}}},
      scales:{{y:{{beginAtZero:true,max:100,title:{{display:true,text:'%'}}}}}}}}
  }});
  new Chart(document.getElementById('chart-viol'), {{
    type:'bar',
    data:{{labels:LABELS,datasets:[{{label:'Chevauchements',data:OVERLAPS,
      backgroundColor:OVERLAPS.map(v=>v===0?'rgba(29,158,117,0.8)':'rgba(226,75,74,0.8)'),
      borderWidth:1}}]}},
    options:{{responsive:true,maintainAspectRatio:false,
      plugins:{{legend:{{display:false}}}},
      scales:{{y:{{beginAtZero:true,ticks:{{stepSize:1}},title:{{display:true,text:'Paires'}}}}}}}}
  }});
  new Chart(document.getElementById('chart-radar'), {{
    type:'radar',
    data:{{
      labels:['Coût↓','Fill Z_FREE','Fill Z_A','Fill Z_CuttingTubes','Sans chevauch.','Machines'],
      datasets:RADAR_DATA.map((d,i)=>({{
        label:d.label,data:d.data,
        backgroundColor:`rgba(${{hex2rgb(d.color)}},0.15)`,
        borderColor:d.color,borderWidth:2,pointRadius:3}}))
    }},
    options:{{responsive:true,maintainAspectRatio:false,
      plugins:{{legend:{{position:'bottom',labels:{{boxWidth:10,font:{{size:10}}}}}}}},
      scales:{{r:{{beginAtZero:true,max:100,ticks:{{display:false}}}}}}}}
  }});
}}

function buildLegend() {{
  const el = document.getElementById('canvas-legend');
  if (!el) return;
  const seen = new Set();
  if (MACHINES_CV[0]) MACHINES_CV[0].machines.forEach(m => {{
    if (!seen.has(m.family) && m.color!=='transparent') {{
      seen.add(m.family);
      el.innerHTML += `<div class="legend-item">
        <div class="legend-swatch" style="background:${{m.color}};border:1px solid #ccc"></div>
        <span>${{m.family}}</span></div>`;
    }}
  }});
  [['Z_REWORK','#E57373'],['Z_A','#378ADD'],['Z_CuttingTubes','#8D6E63'],
   ['Z_FREE','#1D9E75'],['Z_B','#378ADD']].forEach(([n,c]) => {{
    el.innerHTML += `<div class="legend-item">
      <div class="legend-swatch" style="background:${{c}}33;border:1.5px solid ${{c}}"></div>
      <span>${{n}}</span></div>`;
  }});
}}

let activeLayout = 0;
function showLayout(idx) {{
  activeLayout = idx;
  document.querySelectorAll('.layout-btn').forEach((b,i) => b.classList.toggle('active',i===idx));
  drawLayout(idx);
}}

function drawLayout(idx) {{
  const canvas = document.getElementById('layout-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0,0,CANVAS_W,CANVAS_H);
  ctx.fillStyle='#fafaf8'; ctx.fillRect(0,0,CANVAS_W,CANVAS_H);

  const zones = ZONES_CANVAS_PER_LYT[idx] || ZONES_CANVAS_PER_LYT[0];
  zones.forEach(z => {{
    ctx.fillStyle   = z.color+'1A';
    ctx.strokeStyle = z.color;
    ctx.lineWidth   = 2;
    ctx.beginPath(); ctx.roundRect(z.x,z.y,z.w,z.h,6); ctx.fill(); ctx.stroke();
    ctx.fillStyle = z.color;
    ctx.font = 'bold 14px system-ui';
    ctx.fillText(z.name, z.x+8, z.y+20);
  }});

  const layout = MACHINES_CV[idx];
  if (!layout) return;
  layout.machines.forEach(m => {{
    if (m.color==='transparent') return;
    const x=m.cx-m.w/2, y=m.cy-m.h/2;
    ctx.fillStyle   = m.color+(m.excluded?'55':'BB');
    ctx.strokeStyle = m.color;
    ctx.lineWidth   = m.excluded ? 0.5 : 1.5;
    ctx.fillRect(x,y,m.w,m.h); ctx.strokeRect(x,y,m.w,m.h);

    const name = m.name;
    const minDim = Math.min(m.w,m.h);
    if (m.w>=28 && m.h>=10) {{
      let fs = Math.min(12, Math.max(7, Math.floor(minDim*0.42)));
      ctx.font = `${{m.excluded?'normal':'600'}} ${{fs}}px system-ui`;
      ctx.fillStyle = '#111';
      ctx.textBaseline = 'middle';
      const tw = ctx.measureText(name).width;
      if (tw <= m.w-4) {{
        ctx.fillText(name, m.cx-tw/2, m.cy);
      }} else if (m.h > m.w && tw <= m.h-4) {{
        ctx.save(); ctx.translate(m.cx,m.cy); ctx.rotate(-Math.PI/2);
        ctx.fillText(name,-tw/2,0); ctx.restore();
      }} else {{
        let t=name;
        while(t.length>3 && ctx.measureText(t+'…').width > m.w-4) t=t.slice(0,-1);
        const twr=ctx.measureText(t+'…').width;
        ctx.fillText(t+'…',m.cx-twr/2,m.cy);
      }}
    }}
  }});
}}

const canvas = document.getElementById('layout-canvas');
if (canvas) {{
  canvas.addEventListener('mousemove', e => {{
    const rect=canvas.getBoundingClientRect();
    const mx=(e.clientX-rect.left)*(CANVAS_W/rect.width);
    const my=(e.clientY-rect.top )*(CANVAS_H/rect.height);
    const tip=document.getElementById('canvas-tooltip');
    let found=null;
    const layout=MACHINES_CV[activeLayout];
    if (layout) layout.machines.forEach(m=>{{
      if(Math.abs(mx-m.cx)<m.w/2+2 && Math.abs(my-m.cy)<m.h/2+2) found=m;
    }});
    if (found) {{
      tip.style.display='block';
      tip.style.left=(e.clientX+14)+'px';
      tip.style.top=(e.clientY-10)+'px';
      tip.innerHTML=`<strong>${{found.name}}</strong> <span style="color:#aaa">${{found.family}}</span><br>
        <span style="color:#888;font-size:11px">Zone: ${{found.zone}}</span>`;
    }} else tip.style.display='none';
  }});
  canvas.addEventListener('mouseleave',()=>{{
    document.getElementById('canvas-tooltip').style.display='none';
  }});
}}
</script>
</body>
</html>"""

# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == "__main__":
    _init_flow()
    print("\n"+"="*60)
    print("  LAYOUT COMPARISON DASHBOARD GENERATOR  v4")
    print("="*60)

    kpis_list, zones_list, labels, missing = [], [], [], []
    ref_cost = None

    for label, path in LAYOUT_FILES.items():
        print(f"\n[{label}] Loading: {path}")
        if not os.path.exists(path):
            print(f"  ⚠️  File not found — skipping"); missing.append(label); continue
        try:
            machines, zones = load_csv(path)
            kpis = compute_kpis(machines, zones, ref_cost)
            if ref_cost is None:
                ref_cost = kpis["cost"]
            kpis_list.append(kpis); zones_list.append(zones); labels.append(label)
            print(f"  ✅ {len(machines)} items | Active: {kpis['machine_count']} | "
                  f"Cost: {kpis['cost']:.2f} | Improvement: {kpis['improvement_pct']:+.1f}%")
            for zn in ZONE_ORDER:
                if zn not in kpis["zone_stats"]:
                    continue
                zs = kpis["zone_stats"][zn]
                z  = zones[zn]
                print(f"     {zn}: bounds=({z['xmin']:.0f},{z['ymin']:.0f})"
                      f"→({z['xmax']:.0f},{z['ymax']:.0f}) | "
                      f"{zs['machine_count']} machines | Fill: {zs['fill_rate']}%")
            if kpis["outside_count"]:
                print(f"     ⚠️  OUTSIDE ({kpis['outside_count']}): {kpis['outside_list']}")
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"  ❌ Error: {e}"); missing.append(label)

    if missing: print(f"\n[WARN] Skipped: {missing}")
    if not kpis_list: print("\n❌ No layouts loaded."); exit(1)

    print(f"\n[HTML] Generating → {OUTPUT_HTML}")
    html = build_html(kpis_list, labels, zones_list)
    Path(OUTPUT_HTML).write_text(html, encoding="utf-8")
    print(f"  ✅ Done! {Path(OUTPUT_HTML).stat().st_size//1024} KB")

    if len(kpis_list) >= 2:
        print(f"\n{'='*60}")
        for label,kpis in zip(labels,kpis_list):
            print(f"  {label:12s} | Cost: {kpis['cost']:10.2f} | "
                  f"Overlaps: {kpis['overlap_count']:2d} | Improvement: {kpis['improvement_pct']:+.1f}%")
        best = min(zip(labels,kpis_list), key=lambda x: x[1]["cost"])
        print(f"\n  🏆 Best layout: {best[0]}")
        print(f"{'='*60}\n")

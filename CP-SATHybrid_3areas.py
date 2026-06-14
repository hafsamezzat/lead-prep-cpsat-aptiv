"""
=============================================================================
  FACILITY LAYOUT OPTIMIZER v4 — 3-ZONE STRICT + POUTRE OBSTACLE
  
  ZONES:
    Z_A    = Area A (red rect, left)  → MECAL, HANKE currently here
    Z_FREE = Green rectangle (middle) → mixing zone, high-interaction machines
    Z_B    = Area B (red rect, right) → KAPPA, KOMAX currently here
  
  RULES:
    1. EVERY movable machine must end up inside Z_A, Z_FREE, or Z_B
    2. Evacuate Z_B as much as possible → machines go to Z_FREE or Z_A
    3. KAPPA01 (170×1428cm) is too tall for Z_A & Z_FREE → stays in Z_B
    4. KOMAX & KAPPA02 are too tall for Z_A → can go to Z_FREE or Z_B
    5. High-interaction machines are pulled into Z_FREE
    6. Fixed objects (PC-A, WORKMAN_A, zone markers) never move
    7. 65cm minimum gap between all machine edges
    8. ★ NEW: 65cm minimum gap between EVERY movable machine and 'poutre'
       (the structural beam — hard constraint, no exception)

  pip install ortools pandas openpyxl
  python CP_SAT_3ZONE_v4.py
=============================================================================
"""

import math, copy, time, os
import pandas as pd
from ortools.sat.python import cp_model

# =============================================================================
# PARAMETERS
# =============================================================================
OPERATOR_WAGE_MAD_HR = 17.92
HOURS_PER_DAY        = 7.67
DAYS_PER_WEEK        = 5.75
MIN_GAP              = 65       # cm — minimum edge-to-edge gap (machines + poutre)
GRID                 = 10       # cm — solver grid resolution
TIME_LIMIT_SEC       = 21600    # seconds — solver time limit
TOP_N_INTO_ZFREE     = 10
    # top N machines forced into Z_FREE
ZB_PENALTY_WEIGHT    = 8000     # objective penalty per machine staying in Z_B
CSV_INPUT            = "RECOVER_102_RECENT.xlsx"   # ← UPDATE if filename changed
CSV_OUTPUT           = "optimized_layout.csv"

WEEKLY_WAGE = OPERATOR_WAGE_MAD_HR * HOURS_PER_DAY * DAYS_PER_WEEK

# =============================================================================
# ZONE DEFINITIONS  (centimeters — from your AutoCAD file)
# ⚠️  IF YOU MOVED THE ZONE RECTANGLES IN AUTOCAD, UPDATE THESE VALUES.
#     How to get them: select the rectangle → PROPERTIES → note Xmin, Xmax,
#     Ymin, Ymax (or Center X/Y + Width/Height).
# =============================================================================
ZA = {"name": "Z_A",    "xmin": 2139.2153, "xmax": 3389.2153,
                         "ymin":  615.8415, "ymax": 1185.8415}

ZF = {"name": "Z_FREE", "xmin": 2137.799, "xmax": 3389.2153,
                         "ymin": 1756.8415, "ymax": 2953.3415}

ZB = {"name": "Z_B",    "xmin": 3516.2153, "xmax": 5108.2153,
                         "ymin": 1386.8415, "ymax": 2916.8415}

ZONES = [ZA, ZF, ZB]

# =============================================================================
# POUTRE (structural beam) — fixed obstacle, hard gap constraint
#
# ⚠️  YOU MUST UPDATE THESE VALUES from AutoCAD after adding the block.
#     Step-by-step instructions are at the bottom of this file.
#
#     Temporary placeholder — replace with real values before running!
# =============================================================================
POUTRE = {
    "name" : "poutre",
    # ── REPLACE the four values below with real AutoCAD coordinates ─────────
    "xmin" : 2905.9809,   # ← TODO: Xmin of poutre bounding box (cm)
    "xmax" : 3001.1555,   # ← TODO: Xmax of poutre bounding box (cm)
    "ymin" : 1118.7542,   # ← TODO: Ymin of poutre bounding box (cm)
    "ymax" : 1213.9288,   # ← TODO: Ymax of poutre bounding box (cm)
    # ────────────────────────────────────────────────────────────────────────
}
# Derived center + half-sizes (computed once at load time)
POUTRE["cx"] = (POUTRE["xmin"] + POUTRE["xmax"]) / 2
POUTRE["cy"] = (POUTRE["ymin"] + POUTRE["ymax"]) / 2
POUTRE["w"]  =  POUTRE["xmax"] - POUTRE["xmin"]
POUTRE["h"]  =  POUTRE["ymax"] - POUTRE["ymin"]

# =============================================================================
# FAMILY MAP — machine name → family group
# IGNORE  = fixed objects (zone markers, furniture, PC workstations)
# OBSTACLE= fixed physical obstacle (poutre) — not moved, but gap is enforced
# ⚠️  If you renamed any block in AutoCAD, update the key here to match.
# =============================================================================
FAMILY_MAP = {
    "P19+Ref" :"ELOPAR",   "P18+Ref" :"ELOPAR",
    "P17+Ref" :"ELOPAR",   "P16+Ref" :"ELOPAR",   "P16-B+Ref":"ELOPAR",
    "ToTaL_P57":"KOMAX",
    "BoB+KAPPA02":"KAPPA", "BoB+KAPPA01":"KAPPA",
    "P34":"BT722",  "P35":"BT722",  "P37":"BT752",
    "P10":"HANKE",  "P12":"HANKE",  "P13":"HANKE",  "P11":"HANKE",
    "P08":"MECAL",  "P07":"MECAL",  "P04":"MECAL",  "P05":"MECAL",
    "P09":"MECAL",  "P02":"MECAL",  "P14":"MECAL",
    "P20":"DINEFER","P25":"DINEFER",
    "P15-B":"PASSE_FIL","P15":"PASSE_FIL",
    "P21":"RAYCHEM","P22":"RAYCHEM","P23":"RAYCHEM","P24":"RAYCHEM",
    "P01":"SEAL",
    "CONTENTION":"CONTENTION",
    # ── Fixed zone markers / furniture ──────────────────────────────────────
    "Z_FREE"    :"IGNORE",  "Z_A"      :"IGNORE",  "Z_B"     :"IGNORE",
    "WORKMAN_A" :"IGNORE",  "REWORK_03":"IGNORE",  "PRESSE_03":"IGNORE",
    "PC-A"      :"IGNORE",  "PC_B"     :"IGNORE",
    "BoB+KAPPA02":"IGNORE", "BoB+KAPPA01":"IGNORE",
    "ToTaL_P57" :"IGNORE",
    # Add to FAMILY_MAP (all are fixed/decorative, so IGNORE):
    "mangera":    "IGNORE",
    "Bubble_Test":"IGNORE",
    "BoB_KAPPA01":"IGNORE",   # note: underscore, different from BoB+KAPPA01
    "SMED02_P75": "IGNORE",
    "SMED_P57":   "IGNORE",
    "METZNER_10": "IGNORE",
    "SM30_04":    "IGNORE",
    "METZNER_05": "IGNORE",
    "SM15_12":    "IGNORE",
    "SM15_08":    "IGNORE",
    "SM15_07":    "IGNORE",
    "SM15_11":    "IGNORE",
    "SM15_06":    "IGNORE",
    "HSGM_02":    "IGNORE",
    "HSGM_01":    "IGNORE",
    # ── Structural beam — fixed obstacle ────────────────────────────────────
    "poutre"    :"OBSTACLE",   # ★ NEW: treated as hard obstacle, not moved
}

# =============================================================================
# PRODUCTION DATA — fils/hr per machine (wire throughput)
# =============================================================================
PRODUCTION = {
    "KAPPA"    :[{"id":"BoB+KAPPA01","fils_hr":328.98,"active":True},
                 {"id":"BoB+KAPPA02","fils_hr":0,"active":True}],
    "KOMAX"    :[{"id":"ToTaL_P57",  "fils_hr":604.44,"active":True}],
    "ELOPAR"   :[{"id":"P19+Ref",    "fils_hr":313.32, "active":True},
                 {"id":"P18+Ref",    "fils_hr":283.94, "active":True},
                 {"id":"P17+Ref",    "fils_hr":365.54, "active":True},
                 {"id":"P16+Ref",    "fils_hr":350, "active":True},
                 {"id":"P16-B+Ref",  "fils_hr":0, "active":True}],
    "RAYCHEM"  :[{"id":"P21","fils_hr":339.43, "active":True},
                 {"id":"P22","fils_hr":352.48, "active":True},
                 {"id":"P23","fils_hr":156.66, "active":True},
                 {"id":"P24","fils_hr":0, "active":True}],
    "DINEFER"  :[{"id":"P20","fils_hr":189.29, "active":True},
                 {"id":"P25","fils_hr":0, "active":True}],
    "HANKE"    :[{"id":"P10","fils_hr":84.86, "active":True},
                 {"id":"P12","fils_hr":169.71, "active":True},
                 {"id":"P13","fils_hr":189.29, "active":True},
                 {"id":"P11","fils_hr":104.44, "active":True}],
    "PASSE_FIL":[{"id":"P15-B","fils_hr":110.97,"active":True},
                 {"id":"P15",  "fils_hr":0,"active":True}],
    "CONTENTION":[{"id":"CONTENTION","fils_hr":2500,"active":True}],
    "MECAL"    :[{"id":"P08","fils_hr":169.71,"active":True},
                 {"id":"P07","fils_hr":22.85,"active":True},
                 {"id":"P04","fils_hr":104.44,"active":True},
                 {"id":"P05","fils_hr":104.44,"active":True},
                 {"id":"P09","fils_hr":283.94,"active":True},
                 {"id":"P02","fils_hr":365.54,"active":True},
                 {"id":"P14","fils_hr":0,"active":True}],
    "SEAL"     :[{"id":"P01","fils_hr":832.25,"active":True}],
    "BT722"    :[{"id":"P34","fils_hr":535.25,"active":True},
                 {"id":"P35","fils_hr":391.64,"active":True}],
    "BT752"    :[{"id":"P37","fils_hr":800,"active":True}],
}

# Pre-compute flow cache
_FLOW  = {}
_MFLOW = 1

def _init_flow():
    global _FLOW, _MFLOW
    CONNECTED = [
        ("KAPPA","HANKE"),    ("KAPPA","SEAL"),
        ("KOMAX","HANKE"),    ("KOMAX","MECAL"),     ("KOMAX","SEAL"),
        ("ELOPAR","RAYCHEM"), ("ELOPAR","CONTENTION"),
        ("RAYCHEM","HANKE"),  ("RAYCHEM","PASSE_FIL"),("RAYCHEM","CONTENTION"),
        ("DINEFER","RAYCHEM"),  ("DINEFER","PASSE_FIL"),
        ("HANKE","ELOPAR"),   ("HANKE","DINEFER"),   ("HANKE","CONTENTION"),
        ("PASSE_FIL","HANKE"),("PASSE_FIL","SEAL"),
        ("MECAL","ELOPAR"),   ("MECAL","RAYCHEM"),   ("MECAL","CONTENTION"),
        ("SEAL","HANKE"),     ("SEAL","MECAL"),
        ("BT722","CONTENTION"),("BT752","CONTENTION"),
    ]
    def fam_flow(f1, f2):
        t1 = sum(m["fils_hr"] for m in PRODUCTION.get(f1,[]) if m["active"])
        t2 = sum(m["fils_hr"] for m in PRODUCTION.get(f2,[]) if m["active"])
        return (t1 + t2) / 2
    _FLOW  = {(f1,f2): fam_flow(f1,f2) for f1,f2 in CONNECTED if f1 != f2}
    _MFLOW = max(_FLOW.values()) if _FLOW else 1

# =============================================================================
# REL CHART  (7=must be adjacent, -1=keep apart)
# =============================================================================
REL = {
    ("KAPPA","KOMAX"):1,    ("KAPPA","ELOPAR"):1,   ("KAPPA","RAYCHEM"):1,
    ("KAPPA","DINEFER"):1,  ("KAPPA","HANKE"):7,    ("KAPPA","PASSE_FIL"):5,
    ("KAPPA","CONTENTION"):1,("KAPPA","MECAL"):1,   ("KAPPA","SEAL"):5,
    ("KAPPA","BT722"):0,    ("KAPPA","BT752"):0,

    ("KOMAX","ELOPAR"):1,   ("KOMAX","RAYCHEM"):1,  ("KOMAX","DINEFER"):1,
    ("KOMAX","HANKE"):6,    ("KOMAX","PASSE_FIL"):0,("KOMAX","CONTENTION"):1,
    ("KOMAX","MECAL"):6,    ("KOMAX","SEAL"):6,     ("KOMAX","BT722"):0,   ("KOMAX","BT752"):0,

    ("ELOPAR","RAYCHEM"):7, ("ELOPAR","DINEFER"):1, ("ELOPAR","HANKE"):6,
    ("ELOPAR","PASSE_FIL"):1,("ELOPAR","CONTENTION"):6,("ELOPAR","MECAL"):7,
    ("ELOPAR","SEAL"):3,    ("ELOPAR","BT722"):1,   ("ELOPAR","BT752"):1,

    ("RAYCHEM","DINEFER"):5,("RAYCHEM","HANKE"):3,  ("RAYCHEM","PASSE_FIL"):6,
    ("RAYCHEM","CONTENTION"):7,("RAYCHEM","MECAL"):6,("RAYCHEM","SEAL"):1,
    ("RAYCHEM","BT722"):0,  ("RAYCHEM","BT752"):0,

    ("DINEFER","HANKE"):6,  ("DINEFER","PASSE_FIL"):6,("DINEFER","CONTENTION"):3,
    ("DINEFER","MECAL"):1,  ("DINEFER","SEAL"):3,   ("DINEFER","BT722"):0,
    ("DINEFER","BT752"):0,

    ("HANKE","PASSE_FIL"):7,("HANKE","CONTENTION"):1,("HANKE","MECAL"):3,
    ("HANKE","SEAL"):7,     ("HANKE","BT722"):1,    ("HANKE","BT752"):1,

    ("PASSE_FIL","CONTENTION"):3,("PASSE_FIL","MECAL"):1,("PASSE_FIL","SEAL"):3,
    ("PASSE_FIL","BT722"):1,     ("PASSE_FIL","BT752"):1,

    ("CONTENTION","MECAL"):1,("CONTENTION","SEAL"):1,("CONTENTION","BT722"):7,
    ("CONTENTION","BT752"):7,

    ("MECAL","SEAL"):7,("MECAL","BT722"):1,("MECAL","BT752"):1,

    ("SEAL","BT722"):1,("SEAL","BT752"):1,

    ("BT722","BT752"):3,
}

def _get_rel(f1, f2):
    return REL.get((f1,f2), REL.get((f2,f1), 0))

def _get_flow(f1, f2):
    return _FLOW.get((f1,f2), _FLOW.get((f2,f1), 0.0))

def combined_weight(f1, f2):
    rel    = _get_rel(f1, f2)
    flow_n = (_get_flow(f1, f2) / _MFLOW) * 4
    return rel + flow_n

ALL_FAMILIES = list(set(FAMILY_MAP.values()) - {"IGNORE", "OBSTACLE"})

def interaction_score(family):
    return sum(max(0.0, combined_weight(family, f2))
               for f2 in ALL_FAMILIES if f2 != family)

# =============================================================================
# ZONE HELPERS
# =============================================================================
def zone_of(cx, cy):
    for z in ZONES:
        if z["xmin"] <= cx <= z["xmax"] and z["ymin"] <= cy <= z["ymax"]:
            return z["name"]
    return "OUTSIDE"

def in_zone(m, z):
    return (z["xmin"] <= m["cx"] <= z["xmax"] and
            z["ymin"] <= m["cy"] <= z["ymax"])

def fits_in_zone(w, h, z, gap=MIN_GAP):
    zw = z["xmax"] - z["xmin"]
    zh = z["ymax"] - z["ymin"]
    return (w + gap) < zw and (h + gap) < zh

# =============================================================================
# LOAD MACHINES FROM EXCEL
# ⚠️  After re-exporting from AutoCAD, just replace the xlsx file.
#     The loader reads ALL coordinates fresh from the file — nothing is hardcoded.
# =============================================================================
def load_machines(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    df = pd.read_excel(path) if path.endswith(".xlsx") else pd.read_csv(path)
    df["Name"] = df["Name"].str.strip()

    if "Center X" in df.columns:
        df["CenterX"] = df["Center X"]
        df["CenterY"] = df["Center Y"]
    else:
        df["CenterX"] = (df["Xmin"] + df["Xmax"]) / 2
        df["CenterY"] = (df["Ymin"] + df["Ymax"]) / 2

    df["Width"]  = df["Xmax"] - df["Xmin"]
    df["Height"] = df["Ymax"] - df["Ymin"]
    df["family"] = df["Name"].map(FAMILY_MAP)

    unmapped = df[df["family"].isna()]["Name"].tolist()
    if unmapped:
        print(f"[WARN] Unmapped names (skipped): {unmapped}")
    df = df.dropna(subset=["family"]).reset_index(drop=True)

    machines = []
    for _, r in df.iterrows():
        cx  = float(r["CenterX"])
        cy  = float(r["CenterY"])
        w   = float(r["Width"])
        h   = float(r["Height"])
        fam = r["family"]

        # IGNORE and OBSTACLE are both fixed (never moved)
        fixed    = fam in ("IGNORE", "OBSTACLE")
        cur_zone = zone_of(cx, cy)
        in_zb    = (cur_zone == "Z_B")

        can_ZA = fits_in_zone(w, h, ZA)
        can_ZF = fits_in_zone(w, h, ZF)
        can_ZB = fits_in_zone(w, h, ZB)

        machines.append({
            "name"    : r["Name"],
            "family"  : fam,
            "cx"      : cx,
            "cy"      : cy,
            "w"       : w,
            "h"       : h,
            "rot"     : float(r.get("Rotation", 0)),
            "fixed"   : fixed,
            "in_zb"   : in_zb,
            "cur_zone": cur_zone,
            "can_ZA"  : can_ZA,
            "can_ZF"  : can_ZF,
            "can_ZB"  : can_ZB,
            "zone"    : cur_zone,
        })

    # ── Sync POUTRE global from what was loaded in the Excel ────────────────
    # If poutre is in the Excel it will be loaded above; sync it back to global.
    poutre_rows = [m for m in machines if m["name"] == "poutre"]
    if poutre_rows:
        p = poutre_rows[0]
        POUTRE["cx"]   = p["cx"]
        POUTRE["cy"]   = p["cy"]
        POUTRE["w"]    = p["w"]
        POUTRE["h"]    = p["h"]
        POUTRE["xmin"] = p["cx"] - p["w"] / 2
        POUTRE["xmax"] = p["cx"] + p["w"] / 2
        POUTRE["ymin"] = p["cy"] - p["h"] / 2
        POUTRE["ymax"] = p["cy"] + p["h"] / 2
        print(f"[POUTRE] Loaded from Excel → center ({POUTRE['cx']:.1f}, {POUTRE['cy']:.1f}) | "
              f"size {POUTRE['w']:.1f}×{POUTRE['h']:.1f} cm")
    else:
        print(f"[POUTRE] ⚠️  'poutre' NOT found in Excel — using hardcoded POUTRE dict.")
        print(f"          Make sure to export it from AutoCAD and re-run!")

    movable = [m for m in machines if not m["fixed"]]
    in_zb_m = [m for m in movable if m["in_zb"]]

    print(f"\n[DATA] {len(movable)} movable machines | {len(in_zb_m)} currently in Z_B")
    print(f"\n[DATA] Zone fit analysis:")
    print(f"  {'Name':15s} {'Size':12s} {'ZA':3s} {'ZF':3s} {'ZB':3s} {'Currently':8s}")
    print(f"  {'-'*55}")
    for m in movable:
        loc = "← IN ZB" if m["in_zb"] else ""
        za  = "✓" if m["can_ZA"] else "✗"
        zf  = "✓" if m["can_ZF"] else "✗"
        zb  = "✓" if m["can_ZB"] else "✗"
        print(f"  {m['name']:15s} {m['w']:.0f}x{m['h']:.0f}cm  {za:3s}{zf:3s}{zb:3s} {loc}")

    stuck = [m for m in in_zb_m if not m["can_ZA"] and not m["can_ZF"]]
    if stuck:
        print(f"\n[WARN] {len(stuck)} machines CANNOT fit in Z_A or Z_FREE → must stay in Z_B:")
        for m in stuck:
            print(f"       {m['name']} ({m['w']:.0f}×{m['h']:.0f}cm)")

    return machines

# =============================================================================
# COST FUNCTIONS
# =============================================================================
def manhattan(m1, m2):
    return abs(m1["cx"] - m2["cx"]) + abs(m1["cy"] - m2["cy"])

def layout_cost(machines):
    c      = WEEKLY_WAGE / 1e6
    active = [m for m in machines if not m["fixed"]]
    n      = len(active)
    total  = 0.0
    for i in range(n):
        for j in range(i+1, n):
            w = combined_weight(active[i]["family"], active[j]["family"])
            total += w * manhattan(active[i], active[j]) * c
    return total

def edge_gap(m1, m2):
    """Minimum edge-to-edge clearance between two rectangles."""
    gx = abs(m1["cx"] - m2["cx"]) - (m1["w"] + m2["w"]) / 2
    gy = abs(m1["cy"] - m2["cy"]) - (m1["h"] + m2["h"]) / 2
    return min(gx, gy)

def poutre_gap_ok(m):
    """True if machine m has >= MIN_GAP clearance from the poutre."""
    if POUTRE["w"] == 0 and POUTRE["h"] == 0:
        return True   # poutre not configured yet — skip check
    return edge_gap(m, POUTRE) >= MIN_GAP

# =============================================================================
# RANK MACHINES BY INTERACTION SCORE
# =============================================================================
def rank_by_interaction(machines):
    scores  = {m["name"]: interaction_score(m["family"])
               for m in machines if not m["fixed"]}
    ranked  = sorted(scores.items(), key=lambda x: -x[1])
    print(f"\n[RANK] Machines by interaction score (top → most important for Z_FREE):")
    for name, sc in ranked:
        fam = next(m["family"] for m in machines if m["name"] == name)
        print(f"       {name:15s} ({fam:12s}) {sc:.2f}")
    return [n for n, _ in ranked]

# =============================================================================
# CP-SAT SOLVER — 3-ZONE STRICT + POUTRE HARD CONSTRAINT
# =============================================================================
def run_cpsat(machines, time_limit=TIME_LIMIT_SEC):
    movable = [m for m in machines if not m["fixed"]]
    n       = len(movable)
    G       = GRID
    t0      = time.time()

    def g(v): return int(round(v / G))

    ZA_X1,ZA_X2,ZA_Y1,ZA_Y2 = g(ZA["xmin"]),g(ZA["xmax"]),g(ZA["ymin"]),g(ZA["ymax"])
    ZF_X1,ZF_X2,ZF_Y1,ZF_Y2 = g(ZF["xmin"]),g(ZF["xmax"]),g(ZF["ymin"]),g(ZF["ymax"])
    ZB_X1,ZB_X2,ZB_Y1,ZB_Y2 = g(ZB["xmin"]),g(ZB["xmax"]),g(ZB["ymin"]),g(ZB["ymax"])

    X_MIN = min(ZA_X1, ZF_X1, ZB_X1)
    X_MAX = max(ZA_X2, ZF_X2, ZB_X2)
    Y_MIN = min(ZA_Y1, ZF_Y1, ZB_Y1)
    Y_MAX = max(ZA_Y2, ZF_Y2, ZB_Y2)

    gap_g = math.ceil(MIN_GAP / G)

    # Poutre in grid units (half-sizes for separation math)
    P_HW  = math.ceil(POUTRE["w"] / (2 * G))   # half-width  in grid units
    P_HH  = math.ceil(POUTRE["h"] / (2 * G))   # half-height in grid units
    P_GX  = g(POUTRE["cx"])                     # center x    in grid units
    P_GY  = g(POUTRE["cy"])                     # center y    in grid units
    poutre_defined = (POUTRE["w"] > 0 and POUTRE["h"] > 0)

    if poutre_defined:
        print(f"[POUTRE] Hard constraint active | grid center ({P_GX},{P_GY}) | "
              f"half-size ({P_HW},{P_HH}) grid units")
    else:
        print("[POUTRE] ⚠️  Poutre size is 0 — hard constraint SKIPPED. "
              "Update POUTRE dict and re-run.")

    # Pick top machines for Z_FREE
    ranked_names = rank_by_interaction(machines)
    top_for_zf   = [nm for nm in ranked_names
                    if next(m["can_ZF"] for m in movable if m["name"] == nm)][:TOP_N_INTO_ZFREE]
    top_set = set(top_for_zf)
    print(f"\n[ZONES] Top {len(top_set)} machines targeted for Z_FREE: {list(top_set)}")

    model = cp_model.CpModel()

    # Position variables (machine center in grid units)
    gx = [model.NewIntVar(X_MIN, X_MAX, f"gx_{i}") for i in range(n)]
    gy = [model.NewIntVar(Y_MIN, Y_MAX, f"gy_{i}") for i in range(n)]

    # Half-sizes in grid units
    hw = [math.ceil(movable[i]["w"] / (2 * G)) for i in range(n)]
    hh = [math.ceil(movable[i]["h"] / (2 * G)) for i in range(n)]

    # Zone assignment booleans
    bA = [model.NewBoolVar(f"bA_{i}") for i in range(n)]
    bF = [model.NewBoolVar(f"bF_{i}") for i in range(n)]
    bB = [model.NewBoolVar(f"bB_{i}") for i in range(n)]

    for i, m in enumerate(movable):
        # Exactly one zone
        model.Add(bA[i] + bF[i] + bB[i] == 1)

        if not m["can_ZA"]: model.Add(bA[i] == 0)
        if not m["can_ZF"]: model.Add(bF[i] == 0)
        if not m["can_ZB"]: model.Add(bB[i] == 0)

        if m["name"] in top_set:
            model.Add(bF[i] == 1)

        # Zone bounds (machine center must stay inside zone with half-size margin)
        model.Add(gx[i] >= ZA_X1 + hw[i]).OnlyEnforceIf(bA[i])
        model.Add(gx[i] <= ZA_X2 - hw[i]).OnlyEnforceIf(bA[i])
        model.Add(gy[i] >= ZA_Y1 + hh[i]).OnlyEnforceIf(bA[i])
        model.Add(gy[i] <= ZA_Y2 - hh[i]).OnlyEnforceIf(bA[i])

        model.Add(gx[i] >= ZF_X1 + hw[i]).OnlyEnforceIf(bF[i])
        model.Add(gx[i] <= ZF_X2 - hw[i]).OnlyEnforceIf(bF[i])
        model.Add(gy[i] >= ZF_Y1 + hh[i]).OnlyEnforceIf(bF[i])
        model.Add(gy[i] <= ZF_Y2 - hh[i]).OnlyEnforceIf(bF[i])

        model.Add(gx[i] >= ZB_X1 + hw[i]).OnlyEnforceIf(bB[i])
        model.Add(gx[i] <= ZB_X2 - hw[i]).OnlyEnforceIf(bB[i])
        model.Add(gy[i] >= ZB_Y1 + hh[i]).OnlyEnforceIf(bB[i])
        model.Add(gy[i] <= ZB_Y2 - hh[i]).OnlyEnforceIf(bB[i])

        # ================================================================
        # ★ HARD CONSTRAINT — POUTRE GAP (≥ MIN_GAP on at least one axis)
        # ================================================================
        # For each movable machine i, at least ONE of the four half-plane
        # separations from poutre must hold:
        #   machine is fully to the right  of poutre  → gx[i] - P_GX ≥ hw[i]+P_HW+gap_g
        #   machine is fully to the left   of poutre  → P_GX - gx[i] ≥ hw[i]+P_HW+gap_g
        #   machine is fully above         poutre     → gy[i] - P_GY ≥ hh[i]+P_HH+gap_g
        #   machine is fully below         poutre     → P_GY - gy[i] ≥ hh[i]+P_HH+gap_g
        # This is the same disjunctive no-overlap used between machines,
        # but with the poutre center/size as a constant.
        # ================================================================
        if poutre_defined:
            p_xp = model.NewBoolVar(f"p_xp_{i}")
            p_xn = model.NewBoolVar(f"p_xn_{i}")
            p_yp = model.NewBoolVar(f"p_yp_{i}")
            p_yn = model.NewBoolVar(f"p_yn_{i}")
            # At least one separator must be active
            model.AddBoolOr([p_xp, p_xn, p_yp, p_yn])
            # Separation distances (machine half + poutre half + gap)
            sep_x = hw[i] + P_HW + gap_g
            sep_y = hh[i] + P_HH + gap_g
            model.Add(gx[i] - P_GX >=  sep_x).OnlyEnforceIf(p_xp)
            model.Add(P_GX - gx[i] >=  sep_x).OnlyEnforceIf(p_xn)
            model.Add(gy[i] - P_GY >=  sep_y).OnlyEnforceIf(p_yp)
            model.Add(P_GY - gy[i] >=  sep_y).OnlyEnforceIf(p_yn)

    # ── ELOPAR family: same zone + aligned vertically (same x column) ───────
    elopar_idx = [i for i, m in enumerate(movable) if m["family"] == "ELOPAR"]
    if len(elopar_idx) > 1:
        ref_x_el = gx[elopar_idx[0]]
        for idx in elopar_idx[1:]:
            model.Add(gx[idx] == ref_x_el)
            model.Add(bA[idx] == bA[elopar_idx[0]])
            model.Add(bF[idx] == bF[elopar_idx[0]])
            model.Add(bB[idx] == bB[elopar_idx[0]])

    # ── BT family: same zone + aligned vertically (same x column) ───────────
    bt_idx = [i for i, m in enumerate(movable) if m["family"] in ("BT722", "BT752")]
    if len(bt_idx) > 1:
        ref_x_bt = gx[bt_idx[0]]
        for idx in bt_idx[1:]:
            model.Add(gx[idx] == ref_x_bt)
            model.Add(bA[idx] == bA[bt_idx[0]])
            model.Add(bF[idx] == bF[bt_idx[0]])
            model.Add(bB[idx] == bB[bt_idx[0]])

    # ── Pairwise machine separation (0 cm within ELOPAR, 65 cm otherwise) ───
    for i in range(n):
        for j in range(i+1, n):
            fi = movable[i]["family"]
            fj = movable[j]["family"]
            gap = 0 if (fi == "ELOPAR" and fj == "ELOPAR") else gap_g

            min_dx = hw[i] + hw[j] + gap
            min_dy = hh[i] + hh[j] + gap

            b_xp = model.NewBoolVar(f"xp_{i}_{j}")
            b_xn = model.NewBoolVar(f"xn_{i}_{j}")
            b_yp = model.NewBoolVar(f"yp_{i}_{j}")
            b_yn = model.NewBoolVar(f"yn_{i}_{j}")
            model.AddBoolOr([b_xp, b_xn, b_yp, b_yn])
            model.Add(gx[i] - gx[j] >=  min_dx).OnlyEnforceIf(b_xp)
            model.Add(gx[j] - gx[i] >=  min_dx).OnlyEnforceIf(b_xn)
            model.Add(gy[i] - gy[j] >=  min_dy).OnlyEnforceIf(b_yp)
            model.Add(gy[j] - gy[i] >=  min_dy).OnlyEnforceIf(b_yn)

    # ── Objective ────────────────────────────────────────────────────────────
    obj = []

    # Part 1: Weighted Manhattan walking cost
    for i in range(n):
        for j in range(i+1, n):
            w_raw = combined_weight(movable[i]["family"], movable[j]["family"])
            if abs(w_raw) < 0.01:
                continue
            w_int = int(round(abs(w_raw) * 100))
            dx  = model.NewIntVar(0, X_MAX-X_MIN, f"dx_{i}_{j}")
            dy  = model.NewIntVar(0, Y_MAX-Y_MIN, f"dy_{i}_{j}")
            dfx = model.NewIntVar(X_MIN-X_MAX, X_MAX-X_MIN, f"dfx_{i}_{j}")
            dfy = model.NewIntVar(Y_MIN-Y_MAX, Y_MAX-Y_MIN, f"dfy_{i}_{j}")
            model.Add(dfx == gx[i] - gx[j])
            model.Add(dfy == gy[i] - gy[j])
            model.AddAbsEquality(dx, dfx)
            model.AddAbsEquality(dy, dfy)
            obj.append(w_int * (dx + dy))

    # Part 2: Z_B stay penalty (evacuate Z_B)
    for i, m in enumerate(movable):
        if m["in_zb"]:
            obj.append(ZB_PENALTY_WEIGHT * bB[i])

    model.Minimize(sum(obj))

    # ── Warm start ───────────────────────────────────────────────────────────
    for i, m in enumerate(movable):
        model.AddHint(gx[i], g(m["cx"]))
        model.AddHint(gy[i], g(m["cy"]))
        cur = m["cur_zone"]
        if   cur == "Z_A"    and m["can_ZA"]: model.AddHint(bA[i], 1)
        elif cur == "Z_FREE" and m["can_ZF"]: model.AddHint(bF[i], 1)
        else:                                  model.AddHint(bB[i], 1)

    # ── Solve ─────────────────────────────────────────────────────────────
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers  = 8
    solver.parameters.log_search_progress = False
    print(f"\n[CP-SAT] Solving {n} machines | Grid: {G}cm | Gap: {MIN_GAP}cm | "
          f"Limit: {time_limit}s...")

    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        lbl = "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE"
        print(f"[CP-SAT] {lbl} | {time.time()-t0:.1f}s | Obj: {solver.ObjectiveValue():.0f}")

        result = copy.deepcopy(machines)
        idx = 0
        for m in result:
            if not m["fixed"]:
                m["cx"] = solver.Value(gx[idx]) * G
                m["cy"] = solver.Value(gy[idx]) * G
                if   solver.Value(bA[idx]): m["zone"] = "Z_A"
                elif solver.Value(bF[idx]): m["zone"] = "Z_FREE"
                else:                       m["zone"] = "Z_B"
                idx += 1
        return result, solver.ObjectiveValue()
    else:
        print("[CP-SAT] ⚠️  INFEASIBLE — check TOP_N_INTO_ZFREE, zone sizes, or poutre position")
        return machines, float("inf")

# =============================================================================
# LOCAL SEARCH POLISH
# =============================================================================
def local_search_polish(machines, max_passes=40):
    print(f"\n[LS] Polishing with pairwise swaps (max {max_passes} passes)...")
    best      = copy.deepcopy(machines)
    best_cost = layout_cost(best)
    idx       = [i for i, m in enumerate(best) if not m["fixed"]]
    n         = len(idx)

    for p in range(max_passes):
        improved = False
        for ii in range(n):
            for jj in range(ii+1, n):
                i, j = idx[ii], idx[jj]
                zi = best[i].get("zone", "Z_B")
                zj = best[j].get("zone", "Z_B")
                if zi != zj:
                    continue

                best[i]["cx"], best[j]["cx"] = best[j]["cx"], best[i]["cx"]
                best[i]["cy"], best[j]["cy"] = best[j]["cy"], best[i]["cy"]

                # ★ Check gap from ALL other machines AND from poutre
                gap_ok = all(
                    edge_gap(best[i], best[k]) >= MIN_GAP and
                    edge_gap(best[j], best[k]) >= MIN_GAP
                    for k in range(len(best)) if k != i and k != j
                ) and poutre_gap_ok(best[i]) and poutre_gap_ok(best[j])

                if gap_ok:
                    nc = layout_cost(best)
                    if nc < best_cost:
                        best_cost = nc
                        improved  = True
                        continue

                # Revert
                best[i]["cx"], best[j]["cx"] = best[j]["cx"], best[i]["cx"]
                best[i]["cy"], best[j]["cy"] = best[j]["cy"], best[i]["cy"]

        if not improved:
            print(f"[LS] Converged at pass {p+1} | Cost: {best_cost:.4f}")
            break

    return best, best_cost

# =============================================================================
# EXPORT — CSV for AutoCAD APPLYLAYOUT_v2.lsp
# =============================================================================
def export(machines, original, path):
    orig_map = {m["name"]: m for m in original}
    rows = []
    for m in machines:
        o = orig_map.get(m["name"], m)
        rows.append({
            "Name"    : m["name"],
            "Family"  : m["family"],
            "OldCX"   : round(o["cx"], 2),
            "OldCY"   : round(o["cy"], 2),
            "NewCX"   : round(m["cx"], 2),
            "NewCY"   : round(m["cy"], 2),
            "DeltaX"  : round(m["cx"] - o["cx"], 2),
            "DeltaY"  : round(m["cy"] - o["cy"], 2),
            "Width"   : round(m["w"],  2),
            "Height"  : round(m["h"],  2),
            "Rotation": round(m["rot"], 2),
            "Zone"    : m.get("zone", "FIXED"),
            "InZA"    : "YES" if in_zone(m, ZA) else "no",
            "InZFree" : "YES" if in_zone(m, ZF) else "no",
            "InZB"    : "YES" if in_zone(m, ZB) else "no",
        })
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)
    print(f"\n[OUT] Saved → {path}")

    mob    = df[df["Family"].isin(ALL_FAMILIES)]
    in_za  = mob[mob["InZA"]    == "YES"]
    in_zf  = mob[mob["InZFree"] == "YES"]
    in_zb  = mob[mob["InZB"]    == "YES"]
    out    = mob[(mob["InZA"] == "no") & (mob["InZFree"] == "no") & (mob["InZB"] == "no")]

    print(f"\n── ZONE SUMMARY ─────────────────────────────────────────────")
    print(f"  Z_A    : {len(in_za):2d} machines → {in_za['Name'].tolist()}")
    print(f"  Z_FREE : {len(in_zf):2d} machines → {in_zf['Name'].tolist()}")
    print(f"  Z_B    : {len(in_zb):2d} machines → {in_zb['Name'].tolist()}")
    if len(out):
        print(f"  ⚠️  OUTSIDE ALL ZONES: {out['Name'].tolist()} ← PROBLEM!")
    else:
        print(f"  ✅ All machines inside the 3 zones — constraint satisfied")

    # ── Poutre gap verification ──────────────────────────────────────────────
    print(f"\n── POUTRE GAP VERIFICATION ──────────────────────────────────")
    if POUTRE["w"] > 0:
        violations = []
        for m in machines:
            if not m["fixed"] and m["family"] not in ("IGNORE", "OBSTACLE"):
                gap = edge_gap(m, POUTRE)
                status_sym = "✅" if gap >= MIN_GAP else "❌"
                if gap < MIN_GAP:
                    violations.append(m["name"])
                    print(f"  {status_sym} {m['name']:15s} gap={gap:.1f} cm  ← VIOLATION")
        if not violations:
            print(f"  ✅ All machines respect {MIN_GAP} cm gap from poutre")
    else:
        print(f"  ⚠️  Poutre not configured — gap check skipped")
    print()
    print(df[["Name","Family","DeltaX","DeltaY","Zone","InZA","InZFree","InZB"]].to_string())

# =============================================================================
# REPORT
# =============================================================================
def report(before, after, cb, ca):
    print("\n" + "="*60)
    print("  OPTIMIZATION REPORT")
    print("="*60)
    pct = (cb - ca) / abs(cb) * 100 if cb else 0
    print(f"  Initial cost   : {cb:.4f} MAD·cm/week")
    print(f"  Optimized cost : {ca:.4f} MAD·cm/week")
    print(f"  Improvement    : {pct:.1f}%")
    print(f"  Weekly wage    : {WEEKLY_WAGE:.2f} MAD/week")
    print(f"  Min gap        : {MIN_GAP} cm  (machines ↔ machines AND machines ↔ poutre)")
    print(f"  Grid           : {GRID} cm")
    moves = sorted(
        [(m["name"], math.hypot(m["cx"] - b["cx"], m["cy"] - b["cy"]))
         for m, b in zip(after, before) if not m["fixed"]],
        key=lambda x: -x[1]
    )
    print(f"\n  TOP 5 MACHINES MOVED:")
    for name, d in moves[:5]:
        print(f"    {name:20s}  {d:8.1f} cm")
    print("="*60)

# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    _init_flow()

    machines    = load_machines(CSV_INPUT)
    original    = copy.deepcopy(machines)
    cost_before = layout_cost(machines)

    in_zb_n = sum(1 for m in machines if not m["fixed"] and m["in_zb"])
    print(f"\n[START] Initial cost: {cost_before:.4f} | {in_zb_n} machines in Z_B")

    cpsat_result, _     = run_cpsat(machines, TIME_LIMIT_SEC)
    final_result, cost_after = local_search_polish(cpsat_result)

    export(final_result, original, CSV_OUTPUT)
    report(original, final_result, cost_before, cost_after)

    print(f"\n✅ Done! Feed '{CSV_OUTPUT}' → AutoCAD with APPLYLAYOUT_v2.lsp")


# =============================================================================
#  ██████╗ ██╗   ██╗██╗██████╗ ███████╗    ████████╗ ██████╗      ██████╗ ███████╗████████╗
# ██╔════╝ ██║   ██║██║██╔══██╗██╔════╝    ╚══██╔══╝██╔═══██╗    ██╔════╝ ██╔════╝╚══██╔══╝
# ██║  ███╗██║   ██║██║██║  ██║█████╗         ██║   ██║   ██║    ██║  ███╗█████╗     ██║
# ██║   ██║██║   ██║██║██║  ██║██╔══╝         ██║   ██║   ██║    ██║   ██║██╔══╝     ██║
# ╚██████╔╝╚██████╔╝██║██████╔╝███████╗       ██║   ╚██████╔╝    ╚██████╔╝███████╗   ██║
#  ╚═════╝  ╚═════╝ ╚═╝╚═════╝ ╚══════╝       ╚═╝    ╚═════╝      ╚═════╝ ╚══════╝   ╚═╝
#
# HOW TO GET ALL UPDATED COORDINATES FROM AUTOCAD — STEP BY STEP
# =============================================================================
#
# ─── WHAT YOU NEED TO UPDATE ────────────────────────────────────────────────
#
#  After re-defining blocks in AutoCAD (poutre + all modified machine blocks),
#  their Xmin/Xmax/Ymin/Ymax bounding boxes have changed.
#  The Python code reads everything from the Excel export — so you only need
#  to re-export from AutoCAD and drop the new .xlsx file in place.
#  The ONE exception is the POUTRE dict above (if poutre is NOT in the Excel).
#
# ─── STEP 1 : Export all blocks to Excel from AutoCAD ───────────────────────
#
#  Option A — via a LISP script (recommended, gets every block automatically):
#
#    1. Copy-paste this into the AutoCAD command line (or save as .lsp and LOAD):
#
#       (defun C:EXPORT_BLOCKS ( / ss i ent obj data file)
#         (setq file (open "C:\\layout_export.csv" "w"))
#         (write-line "Name,Xmin,Xmax,Ymin,Ymax,Center X,Center Y,Rotation" file)
#         (setq ss (ssget "X" '((0 . "INSERT"))))
#         (if ss
#           (progn
#             (setq i 0)
#             (while (< i (sslength ss))
#               (setq ent (ssname ss i)
#                     obj (vlax-ename->vla-object ent))
#               (vla-GetBoundingBox obj 'mn 'mx)
#               (setq mn (vlax-safearray->list mn)
#                     mx (vlax-safearray->list mx))
#               (write-line
#                 (strcat
#                   (vla-get-EffectiveName obj) ","
#                   (rtos (car mn) 2 4) ","   ; Xmin
#                   (rtos (car mx) 2 4) ","   ; Xmax
#                   (rtos (cadr mn) 2 4) ","  ; Ymin
#                   (rtos (cadr mx) 2 4) ","  ; Ymax
#                   (rtos (/ (+ (car mn)(car mx)) 2) 2 4) ","   ; Center X
#                   (rtos (/ (+ (cadr mn)(cadr mx)) 2) 2 4) "," ; Center Y
#                   (rtos (vla-get-Rotation obj) 2 4))           ; Rotation
#                 file)
#               (setq i (1+ i)))))
#         (close file)
#         (princ "\nExported to C:\\layout_export.csv"))
#
#    2. Run command: EXPORT_BLOCKS  (type in AutoCAD command line, press Enter)
#    3. Open the .csv in Excel, save as .xlsx, rename to RECOVER_102_RECENT.xlsx
#    4. Put it in the same folder as this Python script
#    5. Run the Python script — it reads everything fresh, including poutre
#
#  Option B — manual, for just the poutre block:
#
#    1. Click on the poutre block in AutoCAD to select it
#    2. Open PROPERTIES panel (Ctrl+1)
#    3. Note: Position X, Position Y  (this is the insertion point)
#    4. Note: Width, Height (or Geometry → Xmin/Xmax/Ymin/Ymax)
#    5. Compute:
#         cx   = Position X  (or (Xmin+Xmax)/2 )
#         cy   = Position Y  (or (Ymin+Ymax)/2 )
#         w    = Width  = Xmax - Xmin
#         h    = Height = Ymax - Ymin
#    6. Update the POUTRE dict at the top of this file:
#         POUTRE = {
#           "name" : "poutre",
#           "xmin" : <Xmin value>,
#           "xmax" : <Xmax value>,
#           "ymin" : <Ymin value>,
#           "ymax" : <Ymax value>,
#         }
#
# ─── STEP 2 : Verify the zone rectangles haven't moved ──────────────────────
#
#  If you also moved Z_A, Z_FREE, or Z_B rectangles, you need to update the
#  ZA / ZF / ZB dicts at the top of this file the same way:
#
#    1. Click the zone rectangle → PROPERTIES → Geometry
#    2. Read Xmin, Xmax, Ymin, Ymax
#    3. Update ZA["xmin"], ZA["xmax"], etc.
#
# ─── STEP 3 : Verify machine names match FAMILY_MAP ─────────────────────────
#
#  If you renamed any blocks in AutoCAD (Edit Block Definition dialog),
#  update the key in FAMILY_MAP to match the new name exactly.
#  The script will warn you about unmapped names at startup.
#
# ─── SUMMARY TABLE ──────────────────────────────────────────────────────────
#
#  What changed in AutoCAD │ What to update in Python
#  ─────────────────────────┼────────────────────────────────────────────────
#  Machine block moved      │ Nothing — re-export Excel, script reads it
#  Machine block resized    │ Nothing — re-export Excel, script reads it
#  poutre block added/moved │ Re-export Excel OR update POUTRE dict manually
#  Zone rect moved          │ Update ZA / ZF / ZB dicts (top of file)
#  Block renamed            │ Update key in FAMILY_MAP
#  New machine block added  │ Add entry to FAMILY_MAP + PRODUCTION
#
# =============================================================================

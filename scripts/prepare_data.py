import argparse
import csv
import gzip
import hashlib
import json
import pathlib
import re
import zipfile

import openpyxl
import pandas as pd
from lxml import etree as ET


# =============================================================================
# PATHS / ARGUMENTS
# =============================================================================

SCRIPT_PATH = pathlib.Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parents[1]  # .../bloomberg_data
DEFAULT_INPUT = SCRIPT_PATH.parents[3] / "splashtop"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "bloomberg_data"

parser = argparse.ArgumentParser()
parser.add_argument(
    "--input",
    default=str(DEFAULT_INPUT),
    help="Folder containing the raw Bloomberg .xlsx files",
)
parser.add_argument(
    "--output",
    default=str(DEFAULT_OUTPUT),
    help="Folder where cleaned outputs will be written",
)
args = parser.parse_args()

src = pathlib.Path(args.input)
out = pathlib.Path(args.output)

for d in ["data", "supplementary", "audit", "scripts"]:
    (out / d).mkdir(parents=True, exist_ok=True)

ASOF = "2026-10-07"

manifest = []
quality = []
mappings = []


# =============================================================================
# REQUIRED INPUT FILES
# =============================================================================

REQUIRED_FILES = [
    "wls_universe.xlsx",
    "wls_static.xlsx",
    "wls_momentum.xlsx",
    "wls_rmom_inputs.xlsx",
    "wls_eps.xlsx",
    "wls_eps_revisions.xlsx",
    "wls_roe.xlsx",
    "Classeur7wls_roe2.xlsx",
    "wls_leverage.xlsx",
    "wls_eps_rev_breadth_1m_3m.xlsx",
    "wls_benchmark_10y 1.xlsx",
    "wls_benchmark_10y.xlsx",
    "wls_greater_0,01 1.xlsx",
    "best_eps_5y.xlsx",
]

missing = [name for name in REQUIRED_FILES if not (src / name).exists()]
if missing:
    raise FileNotFoundError(
        "Missing Bloomberg input files in:\n"
        f"  {src}\n\n"
        "Missing:\n  - " + "\n  - ".join(missing)
    )

print(f"INPUT : {src}")
print(f"OUTPUT: {out}")


# =============================================================================
# HELPERS
# =============================================================================

def clean(x):
    if x is None:
        return None
    if isinstance(x, str) and x.startswith("#"):
        return None
    if isinstance(x, str):
        return x.strip()
    return x


def date(x):
    if x is None or pd.isna(x):
        return None
    if isinstance(x, (int, float)):
        x = openpyxl.utils.datetime.from_excel(x)
    return x.strftime("%Y-%m-%d") if hasattr(x, "strftime") else str(x)


def read(name, sheet=None, skip=0):
    p = src / name
    w = openpyxl.load_workbook(p, read_only=True, data_only=True)
    ws = w[sheet] if sheet else w.active
    rows_ = list(ws.values)
    w.close()
    return rows_[skip]


def rows(name, sheet=None, skip=0):
    p = src / name
    w = openpyxl.load_workbook(p, read_only=True, data_only=True)
    ws = w[sheet] if sheet else w.active
    raw = list(ws.values)
    w.close()

    cleaned = [[clean(c) for c in row] for row in raw[skip + 1 :]]
    return [row for row in cleaned if any(c is not None for c in row)]


def frame(name, cols, sheet=None, skip=0):
    header = read(name, sheet, skip)

    mappings.extend(
        {
            "source": name,
            "sheet": sheet or "first",
            "source_column": str(a),
            "output_column": b,
        }
        for a, b in zip(header, cols)
    )

    data = rows(name, sheet, skip)

    if data and len(data[0]) != len(cols):
        raise ValueError(
            f"{name}: expected {len(cols)} columns but found {len(data[0])}. "
            f"Expected output columns: {cols}"
        )

    return pd.DataFrame(data, columns=cols)


def save(df, name, keys=None, folder="data"):
    if keys:
        if df.duplicated(keys).any():
            raise AssertionError((name, "duplicate keys"))
        df = df.sort_values(keys, kind="stable")

    p = out / folder / name
    p.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(
        p,
        index=False,
        float_format="%.17g",
        encoding="utf-8",
        compression="gzip" if name.endswith(".gz") else None,
    )

    manifest.append(
        {
            "path": str(p.relative_to(out)),
            "rows": len(df),
            "columns": len(df.columns),
            "size_bytes": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
    )

    for c in df.columns:
        quality.append(
            {
                "file": str(p.relative_to(out)),
                "column": c,
                "rows": len(df),
                "missing": int(df[c].isna().sum()),
            }
        )

    return df


# =============================================================================
# SMALL / SNAPSHOT FILES
# =============================================================================

u = frame(
    "wls_universe.xlsx",
    [
        "ticker_exchange",
        "name",
        "index_weight_pct",
        "index_position_source",
        "px_last_universe",
    ],
)
u.insert(0, "id", u.ticker_exchange + " Equity")
u["index_weight"] = u.index_weight_pct / 100

if abs(u.index_weight.sum() - 1) >= 1e-10:
    raise AssertionError(
        f"Universe weights do not sum to 1: {u.index_weight.sum()}"
    )

save(u, "universe.csv", ["id"])


st = frame(
    "wls_static.xlsx",
    ["id", "px_last", "volume_latest", "market_cap", "sector"],
    skip=1,
)
st.insert(1, "as_of_date", ASOF)
save(st, "static.csv", ["id"])


mo = frame(
    "wls_momentum.xlsx",
    ["id", "as_of_date", "px_last", "mom_1m", "mom_3m", "mom_6m"],
)
mo.as_of_date = mo.as_of_date.map(date)
save(mo, "momentum.csv", ["id"])


rm = frame(
    "wls_rmom_inputs.xlsx",
    ["id", "as_of_date", "mom_1m", "mom_3m"],
)
rm.as_of_date = rm.as_of_date.map(date)

rmcheck = rm.merge(
    mo[["id", "mom_1m", "mom_3m"]],
    on="id",
    suffixes=("_r", "_m"),
    validate="one_to_one",
)

rm_diffs = {
    c: int(
        (
            ~(
                rmcheck[c + "_r"].eq(rmcheck[c + "_m"])
                | (
                    rmcheck[c + "_r"].isna()
                    & rmcheck[c + "_m"].isna()
                )
            )
        ).sum()
    )
    for c in ["mom_1m", "mom_3m"]
}

same_mom_1m = (
    rmcheck.mom_1m_r.eq(rmcheck.mom_1m_m)
    | (rmcheck.mom_1m_r.isna() & rmcheck.mom_1m_m.isna())
)
same_mom_3m = (
    rmcheck.mom_3m_r.eq(rmcheck.mom_3m_m)
    | (rmcheck.mom_3m_r.isna() & rmcheck.mom_3m_m.isna())
)

save(
    rmcheck[~(same_mom_1m & same_mom_3m)],
    "momentum_conflicts.csv",
    ["id"],
    folder="audit",
)

save(rm, "rmom_inputs.csv", ["id"])


eps = frame(
    "wls_eps.xlsx",
    ["id", "eps_actual_latest_quarter"],
)
eps.insert(1, "as_of_date", ASOF)
save(eps, "eps_actual.csv", ["id"])


def pivot_snap(name, cols):
    df = frame(name, ["id", "observation_date"] + cols)
    df.observation_date = df.observation_date.map(date)

    if df.duplicated(["id", "observation_date"]).any():
        raise AssertionError(f"{name}: duplicate id/observation_date rows")

    rec = []

    for ident, g in df.groupby("id", sort=False):
        r = {"id": ident, "as_of_date": ASOF}

        for c in cols:
            good = g[g[c].notna()]

            if len(good) > 1:
                raise AssertionError((name, ident, c, "more than one non-null value"))

            r[c] = good[c].iloc[0] if len(good) else None
            r[c + "_date"] = good.observation_date.iloc[0] if len(good) else None

        rec.append(r)

    return pd.DataFrame(rec)


er = pivot_snap(
    "wls_eps_revisions.xlsx",
    [
        "eps_estimate_now",
        "eps_estimate_1m_ago",
        "eps_estimate_3m_ago",
    ],
)
save(er, "eps_estimates.csv", ["id"])


ro = pivot_snap(
    "wls_roe.xlsx",
    ["roe_now_pct", "roe_3m_ago_pct"],
)
save(ro, "roe.csv", ["id"])

if rows("wls_roe.xlsx") != rows("Classeur7wls_roe2.xlsx"):
    raise AssertionError("wls_roe.xlsx and Classeur7wls_roe2.xlsx differ")


le = pivot_snap(
    "wls_leverage.xlsx",
    ["debt_now", "assets_now", "debt_3m_ago", "assets_3m_ago"],
)

for suffix in ["now", "3m_ago"]:
    le["leverage_" + suffix] = (
        le["debt_" + suffix]
        / le["assets_" + suffix].where(le["assets_" + suffix].ne(0))
    )

save(le, "leverage.csv", ["id"])


breads = []

for window, sheet in [
    ("1m", "EPS_REV_BREADTH_1M"),
    ("3m", "EPS_BREADTH_3M"),
]:
    b = frame(
        "wls_eps_rev_breadth_1m_3m.xlsx",
        [
            "id",
            "as_of_date",
            "eps_num_up_" + window,
            "eps_num_down_" + window,
        ],
        sheet,
    )

    b.as_of_date = b.as_of_date.map(date)

    den = (
        b["eps_num_up_" + window]
        + b["eps_num_down_" + window]
    )

    b["revision_breadth_" + window] = (
        b["eps_num_up_" + window]
        - b["eps_num_down_" + window]
    ) / den.where(den.ne(0))

    breads.append(b)

br = breads[0].merge(
    breads[1],
    on=["id", "as_of_date"],
    validate="one_to_one",
)
save(br, "revision_breadth.csv", ["id"])


master = u.copy()

for f in [
    st,
    mo.drop(columns=["px_last"]),
    eps,
    er,
    ro,
    le,
    br,
]:
    f = f.drop(columns=["as_of_date"], errors="ignore")

    if set(f.id) != set(u.id):
        missing_from_f = set(u.id) - set(f.id)
        extra_in_f = set(f.id) - set(u.id)
        raise AssertionError(
            "Universe mismatch:\n"
            f"missing={len(missing_from_f)}, extra={len(extra_in_f)}"
        )

    master = master.merge(
        f,
        on="id",
        how="left",
        validate="one_to_one",
    )

master.insert(1, "as_of_date", ASOF)
save(master, "features_snapshot.csv", ["id"])


# =============================================================================
# BENCHMARK FILES
# =============================================================================

bench = []

for name in [
    "wls_benchmark_10y 1.xlsx",
    "wls_benchmark_10y.xlsx",
]:
    b = frame(name, ["date", "px_last"], skip=1)
    b.date = b.date.map(date)
    bench.append(b)

save(bench[0], "benchmark_10y.csv", ["date"])
save(
    bench[1],
    "benchmark_10y_alternative.csv",
    ["date"],
    folder="supplementary",
)

bc = bench[0].merge(
    bench[1],
    on="date",
    suffixes=("_primary", "_alternative"),
    validate="one_to_one",
)

diff = bc[
    ~(
        bc.px_last_primary.eq(bc.px_last_alternative)
        | (
            bc.px_last_primary.isna()
            & bc.px_last_alternative.isna()
        )
    )
]

save(
    diff,
    "benchmark_conflicts.csv",
    ["date"],
    folder="audit",
)

print(
    "SMALL FILES DONE",
    len(master),
    "benchmark conflicts",
    len(diff),
    flush=True,
)


# =============================================================================
# LARGE HISTORICAL WORKBOOK
# =============================================================================

p = src / "wls_greater_0,01 1.xlsx"
ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

history_stats = []
unknown = []
formulas = []
headers = {}
prior = {}
current = None
handles = []


def val(c, ss):
    t = c.get("t")
    v = c.find(ns + "v")
    s = v.text if v is not None else None

    if t == "s":
        return ss[int(s)] if s is not None else None

    if t == "inlineStr":
        is_node = c.find(ns + "is")
        return "".join(is_node.itertext()) if is_node is not None else None

    if t == "e":
        return s

    if s is None:
        return None

    try:
        return float(s) if any(a in s for a in ".eE") else int(s)
    except ValueError:
        return s


def colnum(ref):
    v = 0
    m = re.match(r"[A-Z]+", ref)

    if not m:
        raise ValueError(f"Invalid Excel cell reference: {ref}")

    for c in m.group():
        v = v * 26 + ord(c) - 64

    return v


with zipfile.ZipFile(p) as z:
    shared_strings_path = "xl/sharedStrings.xml"

    if shared_strings_path in z.namelist():
        ss = [
            "".join(si.itertext())
            for _, si in ET.iterparse(
                z.open(shared_strings_path),
                tag=ns + "si",
            )
        ]
    else:
        ss = []

    sheet_path = "xl/worksheets/sheet1.xml"

    for _, r in ET.iterparse(
        z.open(sheet_path),
        tag=ns + "row",
    ):
        rn = int(r.get("r"))

        values = {
            colnum(c.get("r")): val(c, ss)
            for c in r
        }

        for c in list(r):
            f = c.find(ns + "f")

            if f is not None:
                formulas.append(
                    {
                        "cell": c.get("r"),
                        "formula": f.text,
                        "cached_value": val(c, ss),
                    }
                )

        if any(values.get(c) is not None for c in range(1, 10)):
            unknown.append(
                {
                    "source_excel_row": rn,
                    **{
                        "col_" + chr(64 + c): values.get(c)
                        for c in range(1, 10)
                    },
                }
            )

        if values.get(11) == "DATES":
            current = None

            fields = [
                (c, str(v))
                for c, v in sorted(values.items())
                if c >= 12 and v is not None
            ]

            if fields:
                field = fields[0][1]

                if not all(f == field for _, f in fields):
                    raise AssertionError(
                        f"Row {rn}: inconsistent Bloomberg field headers"
                    )

                if not all(
                    isinstance(prior.get(c), str)
                    and (
                        " Equity" in prior[c]
                        or " Index" in prior[c]
                    )
                    for c, _ in fields
                ):
                    raise AssertionError(
                        (rn, "missing ticker header")
                    )

                ids = [prior[c] for c, _ in fields]

                if len(ids) != len(set(ids)):
                    raise AssertionError(
                        f"Row {rn}: duplicate tickers"
                    )

                # FIXED: group(1).lower(), not group.lower()
                match = re.search(
                    r"range\(-(\d+Y)",
                    field,
                    flags=re.IGNORECASE,
                )

                if match is None:
                    raise ValueError(
                        f"Could not extract historical window from field "
                        f"at row {rn}: {field!r}"
                    )

                window = match.group(1).lower()

                metric = (
                    "volumes"
                    if "px_volume" in field.lower()
                    else "prices"
                )

                label = (
                    "benchmark"
                    if ids == ["WLS Index"]
                    else metric
                ) + "_" + window

                key = label
                version = 1

                while key in headers:
                    version += 1
                    key = label + "_v" + str(version)

                headers[key] = ids

                folder = (
                    "data"
                    if key in ["prices_10y", "volumes_10y"]
                    else "supplementary"
                )

                filename = key + ".csv.gz"
                hp = out / folder / filename

                handle = gzip.open(
                    hp,
                    "wt",
                    encoding="utf-8",
                    newline="",
                )
                handles.append(handle)

                writer = csv.writer(handle)
                writer.writerow(["date"] + ids)

                stat = {
                    "path": str(hp.relative_to(out)),
                    "field": field,
                    "source_header_row": rn,
                    "rows": 0,
                    "tickers": len(ids),
                    "missing": 0,
                    "nonpositive": 0,
                    "start_date": None,
                    "end_date": None,
                }

                history_stats.append(stat)
                current = (writer, fields, stat, hp)

                print(
                    "BLOCK",
                    key,
                    len(ids),
                    "row",
                    rn,
                    flush=True,
                )

        elif current and isinstance(values.get(11), (int, float)):
            writer, fields, stat, hp = current

            d = date(values[11])
            vv = [
                clean(values.get(c))
                for c, _ in fields
            ]

            writer.writerow([d] + vv)

            stat["rows"] += 1
            stat["missing"] += sum(v is None for v in vv)
            stat["nonpositive"] += sum(
                isinstance(v, (int, float)) and v <= 0
                for v in vv
            )

            if stat["start_date"] is None:
                stat["start_date"] = d

            if (
                stat["end_date"] is not None
                and d <= stat["end_date"]
            ):
                raise AssertionError((hp, d))

            stat["end_date"] = d

        elif current:
            current = None

        prior = values

        r.clear()

        while r.getprevious() is not None:
            del r.getparent()[0]


for h in handles:
    h.close()


for stat in history_stats:
    hp = out / stat["path"]

    manifest.append(
        {
            **stat,
            "size_bytes": hp.stat().st_size,
            "sha256": hashlib.sha256(
                hp.read_bytes()
            ).hexdigest(),
        }
    )


# =============================================================================
# BEST EPS 5Y HISTORY
# =============================================================================
# The Bloomberg workbook is wide: column A contains observation dates and the
# remaining columns contain tickers. Bloomberg can return slightly different
# month-end dates for different tickers, so sparse rows from the same YYYY-MM
# bucket are merged. A ticker/month conflict is treated as an error.

eps_path = src / "best_eps_5y.xlsx"
eps_shared_strings = []
eps_by_month = {}
eps_headers = {}
eps_conflicts = []
eps_source_rows = 0

with zipfile.ZipFile(eps_path) as z:
    shared_strings_path = "xl/sharedStrings.xml"

    if shared_strings_path in z.namelist():
        eps_shared_strings = [
            "".join(si.itertext())
            for _, si in ET.iterparse(
                z.open(shared_strings_path),
                tag=ns + "si",
            )
        ]

    def eps_cell_value(c):
        t = c.get("t")
        v = c.find(ns + "v")
        s = v.text if v is not None else None

        if t == "s":
            return eps_shared_strings[int(s)] if s is not None else None

        if t == "inlineStr":
            is_node = c.find(ns + "is")
            return "".join(is_node.itertext()) if is_node is not None else None

        return s

    for _, r in ET.iterparse(
        z.open("xl/worksheets/sheet1.xml"),
        tag=ns + "row",
    ):
        rn = int(r.get("r"))
        values = {
            colnum(c.get("r")): eps_cell_value(c)
            for c in r
            if c.get("r")
        }

        if rn == 1:
            if values.get(1) != "Date":
                raise ValueError(
                    f"best_eps_5y.xlsx: expected A1='Date', found {values.get(1)!r}"
                )

            eps_headers = {
                c: str(v).strip()
                for c, v in values.items()
                if c >= 2 and v is not None
            }

            if len(eps_headers) != len(set(eps_headers.values())):
                raise AssertionError(
                    "best_eps_5y.xlsx contains duplicate ticker headers"
                )

            r.clear()
            continue

        raw_date = values.get(1)
        if raw_date is None:
            r.clear()
            continue

        try:
            source_date = openpyxl.utils.datetime.from_excel(float(raw_date))
        except Exception as exc:
            raise ValueError(
                f"best_eps_5y.xlsx row {rn}: invalid Excel date {raw_date!r}"
            ) from exc

        month = source_date.strftime("%Y-%m")
        bucket = eps_by_month.setdefault(month, {})
        eps_source_rows += 1

        for c, raw_value in values.items():
            if c == 1 or c not in eps_headers:
                continue

            value = clean(raw_value)
            if value in (None, "", "#N/A N/A", "#N/A"):
                continue

            try:
                value = float(value)
            except (TypeError, ValueError):
                value = str(value)

            if c in bucket and bucket[c] != value:
                eps_conflicts.append(
                    {
                        "month": month,
                        "ticker": eps_headers[c],
                        "existing_value": bucket[c],
                        "new_value": value,
                        "source_excel_row": rn,
                    }
                )
            else:
                bucket[c] = value

        r.clear()

if eps_conflicts:
    save(
        pd.DataFrame(eps_conflicts),
        "eps_history_conflicts.csv",
        ["month", "ticker"],
        folder="audit",
    )
    raise AssertionError(
        f"best_eps_5y.xlsx contains {len(eps_conflicts)} conflicting "
        "non-null ticker/month observations"
    )

eps_tickers = [eps_headers[c] for c in sorted(eps_headers)]

unknown_tickers = sorted(set(eps_tickers) - set(u.id))

if unknown_tickers:
    print(
        "EPS HISTORY: dropping tickers absent from current WLS universe:",
        ", ".join(unknown_tickers),
        flush=True,
    )

valid_eps_cols = [
    c for c in sorted(eps_headers)
    if eps_headers[c] in set(u.id)
]

eps_tickers = [eps_headers[c] for c in valid_eps_cols]

eps_out_path = out / "data" / "eps_history_5y.csv.gz"

with gzip.open(
    eps_out_path,
    "wt",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.writer(handle)
    writer.writerow(["month"] + eps_tickers)

    for month in sorted(eps_by_month):
        bucket = eps_by_month[month]
        writer.writerow(
            [month]
            + [
                bucket.get(c)
                for c in valid_eps_cols
            ]
        )

eps_months = sorted(eps_by_month)
eps_non_null = sum(len(v) for v in eps_by_month.values())
eps_total_slots = len(eps_months) * len(eps_tickers)

eps_stats = {
    "path": str(eps_out_path.relative_to(out)),
    "months": len(eps_months),
    "tickers": len(eps_tickers),
    "universe_tickers_without_eps_column": len(set(u.id) - set(eps_tickers)),
    "source_rows": eps_source_rows,
    "non_null_values": eps_non_null,
    "total_slots": eps_total_slots,
    "coverage_pct": 100.0 * eps_non_null / eps_total_slots if eps_total_slots else 0.0,
    "start_month": eps_months[0] if eps_months else None,
    "end_month": eps_months[-1] if eps_months else None,
    "size_bytes": eps_out_path.stat().st_size,
    "sha256": hashlib.sha256(eps_out_path.read_bytes()).hexdigest(),
}
manifest.append(eps_stats)

print(
    "EPS HISTORY DONE",
    json.dumps(
        {
            "months": eps_stats["months"],
            "tickers": eps_stats["tickers"],
            "missing_universe_columns": eps_stats["universe_tickers_without_eps_column"],
            "coverage_pct": round(eps_stats["coverage_pct"], 2),
            "start_month": eps_stats["start_month"],
            "end_month": eps_stats["end_month"],
        }
    ),
    flush=True,
)

# =============================================================================
# AUDIT / FINAL REPORT
# =============================================================================

save(
    pd.DataFrame(unknown),
    "unlabeled_columns_a_i.csv",
    folder="supplementary",
)

(out / "audit" / "unlabeled_formulas.json").write_text(
    json.dumps(
        formulas,
        indent=2,
        default=str,
    ),
    encoding="utf-8",
)


if "prices_10y" not in headers:
    raise KeyError(
        "prices_10y block not found in wls_greater_0,01 1.xlsx"
    )

if "volumes_10y" not in headers:
    raise KeyError(
        "volumes_10y block not found in wls_greater_0,01 1.xlsx"
    )

if set(headers["prices_10y"]) != set(headers["volumes_10y"]):
    raise AssertionError(
        "Price and volume historical universes differ"
    )

if not set(headers["prices_10y"]) <= set(u.id):
    raise AssertionError(
        "Historical universe contains tickers absent from universe.xlsx"
    )


hs = pd.DataFrame(
    {"id": headers["prices_10y"]}
)

hs = hs.merge(
    u[["id", "index_weight_pct"]],
    on="id",
    validate="one_to_one",
)

save(
    hs,
    "history_universe.csv",
    ["id"],
)


q = pd.DataFrame(quality)
save(
    q,
    "missing_values.csv",
    folder="audit",
)

save(
    pd.DataFrame(mappings),
    "column_mapping.csv",
    folder="audit",
)


sources = [
    {
        "file": f.name,
        "size_bytes": f.stat().st_size,
        "sha256": hashlib.sha256(
            f.read_bytes()
        ).hexdigest(),
    }
    for f in sorted(src.glob("*.xlsx"))
]


report = {
    "as_of_date": ASOF,
    "universe_tickers": len(u),
    "history_tickers": len(hs),
    "history_weight_pct": float(
        hs.index_weight_pct.sum()
    ),
    "benchmark_conflicts": diff.to_dict("records"),
    "history_blocks": history_stats,
    "roe_duplicate_verified": True,
    "rmom_momentum_different_values": rm_diffs,
    "unlabeled_formulas_count": len(formulas),
    "sources": sources,
    "eps_history_5y": eps_stats,
    "outputs": manifest,
}


(out / "audit" / "report.json").write_text(
    json.dumps(
        report,
        indent=2,
        default=str,
    ),
    encoding="utf-8",
)


print(
    "DONE",
    json.dumps(
        {
            k: report[k]
            for k in [
                "universe_tickers",
                "history_tickers",
                "history_weight_pct",
                "benchmark_conflicts",
                "unlabeled_formulas_count",
            ]
        }
    ),
    flush=True,
)

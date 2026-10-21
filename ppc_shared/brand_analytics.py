"""Brand Analytics CSV import and workbook-equivalent reporting.

Additive module: existing parsers and numeric conventions are unchanged.
"""
import csv
import hashlib
import io
import math
import re
import unicodedata
from datetime import date, datetime
from collections import defaultdict

from .utils import normalize_text, safe_float


def header_key(value):
    value = unicodedata.normalize("NFKC", str(value)).lstrip("\ufeff")
    return re.sub(r"\s*:\s*", ":", normalize_text(value))


UNKNOWN_QUERY = "Unknown search query"

STAGES = ("impressions", "clicks", "cart adds", "purchases")


def _fields(family):
    fields = {"reporting date": ("reporting_date", "text")}
    if family == "catalog":
        fields.update({"asin": ("asin", "text"), "asin title": ("title", "text"), "category": ("category", "text")})
        for stage in STAGES:
            prefix = stage.replace(" ", "_")
            fields[f"{stage}:{stage}"] = (prefix, "count")
            for name, suffix, kind in [("price (median)", "price", "number"), ("rating (median)", "rating", "number"),
                                       ("same day shipping speed", "same_day", "count"), ("1d shipping speed", "one_day", "count"), ("2d shipping speed", "two_day", "count")]:
                fields[f"{stage}:{name}"] = (f"{prefix}_{suffix}", kind)
        fields["purchases:search traffic sales"] = ("sales", "number")
        fields["clicks:click rate (ctr)"] = ("source_ctr", "percent")
        fields["purchases:conversion rate %"] = ("source_cvr", "percent")
    else:
        entity = "brand" if family == "brand" else "asin"
        fields.update({"search query": ("query", "text"), "search query score": ("score", "count"), "search query volume": ("volume", "count")})
        for stage in STAGES:
            prefix = stage.replace(" ", "_")
            fields[f"{stage}:total count"] = (f"market_{prefix}", "count")
            fields[f"{stage}:{entity} count"] = (prefix, "count")
            fields[f"{stage}:{entity} share %"] = (f"source_{prefix}_share", "percent")
            for owner, qualifier in [("market_", ""), ("", f"{entity} ")]:
                fields[f"{stage}:{qualifier}price (median)"] = (f"{owner}{prefix}_price", "number")
            for name, suffix in [("same day shipping speed", "same_day"), ("1d shipping speed", "one_day"), ("2d shipping speed", "two_day")]:
                fields[f"{stage}:{name}"] = (f"market_{prefix}_{suffix}", "count")
        for stage, rate in [("clicks", "click"), ("cart adds", "cart add"), ("purchases", "purchase")]:
            fields[f"{stage}:{rate} rate %"] = (f"source_{stage.replace(' ', '_')}_rate", "percent")
    return fields


def _metadata(row):
    result = {}
    for cell in row:
        match = re.fullmatch(r'\s*(.*?)\s*=\s*\["(.*)"\]\s*', cell)
        if match:
            result[header_key(match[1])] = match[2]
    return result


def parse_report(content):
    """Read original CSV bytes. Headers/unknown source columns are retained."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp1252")
    records = list(csv.reader(io.StringIO(text)))
    header_index = next((i for i, row in enumerate(records[:12]) if "search query" in map(header_key, row) or "asin title" in map(header_key, row)), None)
    if header_index is None:
        raise ValueError("No Search Query or ASIN Title header row found")
    headers = records[header_index]
    keys = [header_key(h) for h in headers]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate headers after normalization")
    metadata = {}
    for row in records[:header_index]:
        metadata.update(_metadata(row))
    family = "catalog" if "asin title" in keys else "brand" if "impressions:brand count" in keys else "asin" if "impressions:asin count" in keys else None
    if not family:
        raise ValueError("Cannot distinguish Brand and ASIN Search Query Performance")
    fields = _fields(family)
    required = ["reporting_date", "asin"] if family == "catalog" else ["query", "score", "volume", "reporting_date"]
    required += [stage.replace(" ", "_") for stage in STAGES]
    if family != "catalog":
        required += [f"market_{stage.replace(' ', '_')}" for stage in STAGES]
    mapped = {fields[k][0] for k in keys if k in fields}
    missing = sorted(set(required) - mapped)
    if missing:
        raise ValueError("Missing columns: " + ", ".join(missing))
    if normalize_text(metadata.get("reporting range")) != "weekly":
        raise ValueError("Only weekly exports are currently supported")
    period_label = metadata.get("select week", "")
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", period_label)
    if len(dates) != 2:
        raise ValueError("Weekly metadata must contain start and end dates")
    start, end = [date.fromisoformat(d) for d in dates]
    if (end - start).days != 6:
        raise ValueError("A weekly report must span seven days")
    identity = metadata.get("brand" if family == "brand" else "asin or product", "")
    if family != "catalog" and not identity.strip():
        raise ValueError("Missing Brand or ASIN metadata")
    if family == "asin":
        identity = identity.strip().upper()
    rows, seen, warnings = [], set(), []
    for index, values in enumerate(records[header_index + 1:], header_index + 2):
        if not any(v.strip() for v in values):
            continue
        if len(values) != len(headers):
            raise ValueError(f"Row {index}: expected {len(headers)} columns, received {len(values)}")
        row = {"source": dict(zip(headers, values))}
        for key, value in zip(keys, values):
            if key not in fields:
                continue
            field, kind = fields[key]
            if kind == "text":
                parsed = value.strip()
            else:
                # Keep the existing shared number parser's behavior intact.
                parsed = safe_float(value, None)
                if parsed is not None and (not math.isfinite(parsed) or (kind == "count" and (parsed < 0 or not parsed.is_integer()))):
                    raise ValueError(f"Row {index}: invalid {key}")
                if parsed is None and value.strip() and normalize_text(value) not in {"n/a", "na", "-", "--", "null"}:
                    raise ValueError(f"Row {index}: invalid number in {key}")
                if kind == "percent" and parsed is not None:
                    parsed /= 100
            row[field] = parsed
        observation = row.get("query") if family != "catalog" else row.get("asin", "").upper()
        if not observation:
            if family == "catalog":
                raise ValueError(f"Row {index}: empty ASIN")
            warnings.append(f"Row {index}: blank Search Query retained as {UNKNOWN_QUERY}; its metrics are included in totals.")
        row["match_key"] = normalize_text(observation)
        if row["match_key"] in seen:
            raise ValueError(f"Row {index}: duplicate observation {observation}")
        seen.add(row["match_key"])
        if any(row.get(field) is None for field in required):
            raise ValueError(f"Row {index}: missing required count")
        raw_date = row.get("reporting_date", "")
        try:
            report_date = date.fromisoformat(raw_date) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date) else datetime.strptime(raw_date, "%m/%d/%Y").date()
        except ValueError:
            raise ValueError(f"Row {index}: invalid Reporting Date") from None
        if report_date != end:
            raise ValueError(f"Row {index}: Reporting Date conflicts with weekly metadata")
        row["reporting_date"] = report_date.isoformat()
        if family == "catalog":
            row["asin"] = row["asin"].upper()
        rows.append(row)
    if not rows:
        raise ValueError("This file is an empty template; no observations to import")
    if len(rows) > 50000:
        raise ValueError("Maximum 50,000 observations per report")
    return {"family": family, "identity": identity.strip(), "period_start": start.isoformat(), "period_end": end.isoformat(),
            "period_label": period_label, "granularity": "weekly", "headers": headers, "metadata": metadata,
            "checksum": hashlib.sha256(content).hexdigest(), "rows": rows, "warnings": warnings}


def _sum(rows, key):
    values = [r[key] for r in rows if r.get(key) is not None]
    return sum(values) if values else None


def _avg(rows, key):
    values = [r[key] for r in rows if r.get(key) is not None]
    return sum(values) / len(values) if values else None


def _divide(a, b):
    return a / b if a is not None and b else None


def metrics(rows):
    result = {key: _sum(rows, key) for key in ["volume", "impressions", "clicks", "cart_adds", "purchases", "sales", "market_impressions", "market_clicks", "market_cart_adds", "market_purchases"]}
    for key in ["volume", "score", "impressions", "clicks", "cart_adds"]:
        result[f"avg_{key}"] = _avg(rows, key)
    for prefix in ["", "market_"]:
        for stage in STAGES:
            key = f"{prefix}{stage.replace(' ', '_')}_price"
            result[key] = _avg(rows, key)
        for label, num, den in [("ctr", "clicks", "impressions"), ("atc", "cart_adds", "clicks"), ("cvr", "purchases", "clicks")]:
            result[prefix + label] = _divide(result.get(prefix + num), result.get(prefix + den))
    for stage in STAGES:
        key = stage.replace(" ", "_")
        result[key + "_share"] = _divide(result[key], result["market_" + key])
    for stage in STAGES:
        key = stage.replace(" ", "_")
        result[key + "_rating"] = _avg(rows, key + "_rating")
        for suffix in ["same_day", "one_day", "two_day"]:
            result[key + "_" + suffix] = _sum(rows, key + "_" + suffix)
    for key in ["source_ctr", "source_cvr"]:
        result[key] = _avg(rows, key)
    for key in ["ctr", "atc", "cvr"]:
        result[key + "_performance"] = result[key] - result["market_" + key] if result[key] is not None and result["market_" + key] is not None else None
    return result


def columns(family, view):
    def col(field, label, kind="count"):
        return {"field": field, "label": label, "kind": kind}
    identity = "Brand" if family == "brand" else "ASIN"
    if family == "catalog":
        extra = []
        for stage in STAGES:
            key = stage.replace(" ", "_")
            extra.append(col(key + "_price", stage.title() + " price (avg. reported median)", "money"))
            if stage in {"impressions", "purchases"}:
                extra.append(col(key + "_rating", stage.title() + " rating (avg. reported median)", "number"))
            for suffix, name in [("same_day", "same-day"), ("one_day", "1-day"), ("two_day", "2-day")]:
                extra.append(col(key + "_" + suffix, stage.title() + " " + name + " shipping"))
        extra += [col("source_ctr", "Average reported CTR", "percent"), col("source_cvr", "Average reported CVR", "percent")]
        for c in extra:
            c["hidden"] = True
        return [col("label", "ASIN / Period", "text"), col("title", "Product title", "text"), col("category", "Category", "text")] + [col(k, t) for k, t in [("impressions", "Impressions"), ("clicks", "Clicks"), ("cart_adds", "Cart adds"), ("purchases", "Purchases")]] + [col("sales", "Search traffic sales", "money"), col("ctr", "CTR", "percent"), col("cvr", "CVR", "percent")] + extra
    label = col("label", "Period" if view in {"funnel", "trend", "comparison"} else "Search Query", "text")
    shares = [col(k + "_share", t + " share", "percent") for k, t in [("impressions", "Impression"), ("clicks", "Click"), ("cart_adds", "Cart-add"), ("purchases", "Purchase")]]
    if view == "funnel":
        return [label] + shares
    if view == "trend":
        return [label, col("volume", "Query volume")] if family == "asin" else [label] + [c for c in shares if c["field"] != "cart_adds_share"]
    prices = [col("purchases_price", identity + " price (avg. reported median)", "money"), col("market_purchases_price", "Market price (avg. reported median)", "money")]
    rates = [col(prefix + k, name + " " + k.upper(), "pp" if prefix.endswith("performance") else "percent") for prefix, name in [("", identity), ("market_", "Market")] for k in ["ctr", "atc", "cvr"]]
    performance = [col(k + "_performance", k.upper() + " performance", "pp") for k in ["ctr", "atc", "cvr"]]
    if view == "performance":
        return [label, col("avg_volume", "Average query volume"), shares[0], col("purchases", identity + " purchases"), col("avg_impressions", "Average " + identity.lower() + " impressions"), col("avg_clicks" if family == "brand" else "clicks", "Average brand clicks" if family == "brand" else "ASIN clicks"), col("avg_cart_adds" if family == "brand" else "cart_adds", "Average brand cart adds" if family == "brand" else "ASIN cart adds")] + prices + rates + performance
    volume = col("volume" if view == "comparison" else "avg_volume", "Query volume" if view == "comparison" else "Average query volume")
    counts = [col("impressions" if family == "brand" or view == "comparison" else "avg_impressions", "Impressions" if family == "brand" or view == "comparison" else "Average impressions"), col("clicks", "Clicks"), col("avg_cart_adds" if family == "asin" and view == "details" else "cart_adds", "Average cart adds" if family == "asin" and view == "details" else "Cart adds"), col("purchases", "Purchases"), col("market_purchases", "Market purchases")]
    return [label, volume, col("avg_score", "Average query score")] + prices + counts + shares + rates + performance


def _text_match(actual, model):
    value = normalize_text(actual)
    needle = normalize_text(model.get("filter", ""))
    op = model.get("type", "contains")
    return {"contains": needle in value, "notContains": needle not in value, "equals": value == needle,
            "notEqual": value != needle, "startsWith": value.startswith(needle), "endsWith": value.endswith(needle),
            "blank": not value, "notBlank": bool(value)}.get(op, False)


def filter_match(row, field, model, kind):
    if model.get("conditions"):
        values = [filter_match(row, field, m, kind) for m in model["conditions"]]
        return any(values) if model.get("operator") == "OR" else all(values)
    expected = "text" if kind == "text" else "number"
    if model.get("filterType", expected) != expected:
        raise ValueError(f"Filter for {field} must be {expected}")
    if kind == "text":
        return _text_match(row.get(field), model)
    value = row.get(field)
    op = model.get("type", "equals")
    if op in {"blank", "notBlank"}:
        return (value is None) == (op == "blank")
    if value is None:
        return False
    # GUI filters are entered in displayed percentage / percentage-point units.
    if kind in {"percent", "pp"}:
        value *= 100
    target = model.get("filter")
    if target is None:
        return False
    if op == "inRange":
        return target <= value <= model.get("filterTo", target)
    return {"equals": value == target, "notEqual": value != target, "greaterThan": value > target,
            "greaterThanOrEqual": value >= target, "lessThan": value < target, "lessThanOrEqual": value <= target}.get(op, False)


def query_reports(reports, options):
    family, view = options.get("family", "brand"), options.get("view", "performance")
    observations = []
    for report in reports:
        for source in report["rows"]:
            row = dict(source, period_id=report["id"], period_label=report["period_label"], period_end=report["period_end"])
            if "keywords" in options and row.get("match_key") not in {normalize_text(k) for k in options["keywords"]}:
                continue
            display_text = (row.get("query") or UNKNOWN_QUERY) if family != "catalog" else row.get("title", "")
            if options.get("search") and normalize_text(options["search"]) not in normalize_text(display_text + " " + row.get("asin", "")):
                continue
            if "asins" in options and family == "catalog" and row.get("asin") not in options["asins"]:
                continue
            if options.get("category") and normalize_text(row.get("category")) != normalize_text(options["category"]):
                continue
            observations.append(row)
    by_period = view in {"funnel", "trend", "comparison"}
    groups = defaultdict(list)
    for row in observations:
        key = (row["period_id"] if by_period else row["match_key"]) if family != "catalog" else row["asin"] + ":" + row["period_id"]
        groups[key].append(row)
    result = []
    for key, group in groups.items():
        first = group[0]
        result.append(dict(metrics(group), id=key, label=(first.get("asin", "") + " · " + first["period_label"]) if family == "catalog" else first["period_label"] if by_period else (first.get("query") or UNKNOWN_QUERY), title=first.get("title"), category=first.get("category"), period_end=first["period_end"]))
    defs = columns(family, view)
    kinds = {c["field"]: c["kind"] for c in defs}
    filters = options.get("filters", {})
    unknown = set(filters) - set(kinds)
    if unknown:
        raise ValueError("Unknown filter fields: " + ", ".join(sorted(unknown)))
    result = [r for r in result if all(filter_match(r, field, model, kinds[field]) for field, model in filters.items())]
    ids = {r["id"] for r in result}
    matching = [r for key, group in groups.items() if key in ids for r in group]
    summary = dict(metrics(matching), id="__total__", label="Total / Average") if matching else None
    for sort in reversed(options.get("sort", [])):
        field = sort["field"]
        if field not in kinds:
            raise ValueError("Unknown sort field")
        result.sort(key=lambda r: (r.get(field) is None, r.get(field) if r.get(field) is not None else ""), reverse=sort.get("direction") == "desc")
    if not options.get("sort"):
        result.sort(key=lambda r: (r["period_end"], r["label"]) if by_period or family == "catalog" else r["label"])
    trends = []
    for period_id in dict.fromkeys(r["period_id"] for r in sorted(matching, key=lambda r: r["period_end"])):
        group = [r for r in matching if r["period_id"] == period_id]
        trends.append(dict(metrics(group), label=group[0]["period_label"], id=period_id, period_end=group[0]["period_end"]))
    delta = None
    if view == "comparison" and len(trends) == 2:
        a, b = trends
        delta = {"from": a["label"], "to": b["label"], "values": {c["field"]: (b[c["field"]] - a[c["field"]]) if isinstance(a.get(c["field"]), (float, int)) and isinstance(b.get(c["field"]), (float, int)) else None for c in defs if c["kind"] != "text"}}
    page, size = options.get("page", 1), options.get("page_size", 100)
    return {"columns": defs, "rows": result[(page - 1) * size:page * size], "row_count": len(result), "summary": summary, "trends": trends, "delta": delta}

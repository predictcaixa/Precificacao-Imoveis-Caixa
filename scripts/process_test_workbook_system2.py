"""Run System 2 on TESTE.xlsx and compare with peer and System 1 outputs."""
from __future__ import annotations
import csv
import json
import math
import statistics
import sys
from pathlib import Path
import joblib
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "deploy2"))
from model_runtime import predict_many
from scripts.serve_offer_avm import load_avm_model, predict_discounted_offers
SOURCE = ROOT / "dados/derivados/TESTE.xlsx"
PEERS = ROOT / "dados/derivados/TESTE_comp_Guilherme_CatBoost_7pct.xlsx"
S1_REPORT = ROOT / "models/offer_avm/avm_report.json"
S2_ARTIFACT = ROOT / "models/hedonic_avm/hedonic_spline_ridge_v4_offer_calibrated.joblib"
OUT_XLSX = ROOT / "dados/derivados/TESTE_system2_hedonic_v4_resultado.xlsx"
OUT_COMPARE = ROOT / "dados/derivados/TESTE_system2_hedonic_v4_comparacao.xlsx"
OUT_JSON = ROOT / "dados/derivados/TESTE_system2_hedonic_v4_relatorio.json"
OUT_CSV = ROOT / "dados/derivados/TESTE_system2_hedonic_v4_linhas.csv"
MATCH_TOLERANCE = 0.07
def num(v):
    if v is None or (isinstance(v, str) and v.strip().casefold() in {"", "não informado", "nao informado", "n/a", "-"}):
        return None
    if isinstance(v, str):
        v = v.strip().replace(" ", "")
        if "," in v and "." in v:
            v = v.replace(".", "").replace(",", ".")
        elif "," in v:
            v = v.replace(",", ".")
    try:
        value = float(v)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None
def text(v):
    if v is None:
        return None
    s = str(v).strip()
    return s if s and s.casefold() not in {"não informado", "nao informado"} else None
def metrics(actual, pred):
    pairs = [(a, p) for a, p in zip(actual, pred) if a is not None and p is not None]
    if not pairs:
        return {"n": 0, "mae_brl": None, "rmse_brl": None, "mape_percent": None, "bias_brl": None}
    err = [p-a for a, p in pairs]
    apes = [abs(e)/abs(a) for (a, _), e in zip(pairs, err) if a]
    return {"n": len(pairs), "mae_brl": round(sum(map(abs, err))/len(err), 2),
            "rmse_brl": round(math.sqrt(sum(e*e for e in err)/len(err)), 2),
            "mape_percent": round(sum(apes)*100/len(apes), 2) if apes else None,
            "bias_brl": round(sum(err)/len(err), 2)}
def run():
    swb = load_workbook(SOURCE, read_only=True, data_only=True)
    s = swb["teste"]
    items = {}
    for r in range(9, s.max_row+1):
        iid = num(s.cell(r, 1).value)
        if iid is None:
            continue
        items[int(iid)] = {
            "source_row": r,
            "area_privativa_m2": num(s.cell(r, 16).value), "idade_anos": num(s.cell(r, 22).value),
            "quartos": num(s.cell(r, 11).value), "banheiros": num(s.cell(r, 12).value),
            "vagas": num(s.cell(r, 13).value), "elevador": num(s.cell(r, 14).value),
            "area_total_m2": num(s.cell(r, 15).value), "cep": text(s.cell(r, 8).value),
            "regiao": None, "distrito": text(s.cell(r, 7).value),
            "setor_censitario": None, "renda_mediana_mensal_brl": None,
            "renda_media_mensal_brl": None, "padrao_iptu": None,
        }
    pwb = load_workbook(PEERS, read_only=True, data_only=True)
    p = pwb["teste"]
    peer_rows = {}
    peer_names = ["Fernando A / Gradient Boosting", "Fernando B / Gradient Boosting", "Januario / CatBoost",
                  "Analise Evolutiva", "Hilder / CatBoost", "Luciana / XGBoost", "Thiago / CatBoost"]
    for r in range(9, p.max_row+1):
        iid = num(p.cell(r, 1).value)
        if iid is None:
            continue
        peer_rows[int(iid)] = {
            "row": r, "evaluation": num(p.cell(r, 20).value), "offer": num(p.cell(r, 21).value),
            "peers": {n: num(p.cell(r, col).value) for n, col in zip(peer_names, range(22, 29))},
            "s1_submitted": num(p.cell(r, 29).value),
            "s1_arithmetic": num(p.cell(r, 30).value),
        }
    ids = sorted(set(items) & set(peer_rows))
    if not ids:
        raise ValueError("No matching property IDs between TESTE.xlsx and peer results.")
    bundle = joblib.load(S2_ARTIFACT)
    if bundle.get("model_id") != "hedonic_spline_ridge_v4_offer_calibrated":
        raise ValueError("Unexpected System 2 model artifact.")
    properties = [items[i] for i in ids]
    s2_raw = dict(zip(ids, predict_many(bundle, properties)))
    s2_calibrated = dict(zip(ids, predict_many(bundle, properties, apply_offer_calibration=True)))
    s2 = s2_calibrated  # Deployed v4 behavior: calibrated offer estimate is primary.
    s2_aligned = {}
    s1bundle = load_avm_model(S1_REPORT, "catboost")
    s1 = dict(zip(ids, predict_discounted_offers(s1bundle, properties)))
    s1_offer_equivalent = {i: round(s1[i] / 0.9, 2) for i in ids}
    results = []
    for i in ids:
        row = peer_rows[i]
        values = [v for v in row["peers"].values() if v is not None]
        med = statistics.median(values) if values else None
        results.append({"item_id": i, "bairro": items[i]["distrito"], "area_privativa_m2": items[i]["area_privativa_m2"],
                        "idade_anos": items[i]["idade_anos"], "avaliacao_referencia_brl": row["evaluation"],
                        "oferta_referencia_brl": row["offer"], "system2_ridge_offer_raw_brl": s2_raw[i],
                        "system2_ridge_offer_calibrated_brl": s2_calibrated[i],
                        "system1_catboost_submitted_brl": row["s1_submitted"], "system1_catboost_same_inputs_90pct_target_brl": s1[i],
                        "system1_catboost_same_inputs_offer_equivalent_brl": s1_offer_equivalent[i],
                        "system1_arithmetic_90pct_offer_brl": row["s1_arithmetic"],
                        "peer_median_brl": med, "peer_min_brl": min(values) if values else None,
                        "peer_max_brl": max(values) if values else None,
                        **{n.lower().replace(" / ", "_").replace(" ", "_"): v for n, v in row["peers"].items()}})
    actual = [peer_rows[i]["evaluation"] for i in ids]
    peer_medians = [statistics.median(v for v in peer_rows[i]["peers"].values() if v is not None)
                    if any(v is not None for v in peer_rows[i]["peers"].values()) else None for i in ids]
    colleague_metrics = {n: metrics(actual, [peer_rows[i]["peers"][n] for i in ids]) for n in peer_names}
    summary = {
        "sample_file": str(SOURCE.relative_to(ROOT)), "peer_reference_file": str(PEERS.relative_to(ROOT)),
        "items_in_input": len(items), "items_compared": len(ids), "system2_model": bundle["model_id"],
        "system2_target_note": "Valor integral da oferta/anuncio; nao representa venda confirmada ou avaliacao independente.",
        "system2_offer_calibration": bundle["report"]["offer_calibration"],
        "system1_conversion_note": "System 1 CatBoost estimates a 90%-of-offer target; for comparison only, its values are divided by 0.90 to express an implied full-offer equivalent.",
        "system1_arithmetic_note": "The arithmetic reference is a separate 90% x supplied-offer calculation, not a CatBoost prediction. It is reported as its own column and is never used to train or calibrate System 2.",
        "feature_scope_note": "System 2 v4 uses physical attributes, district, and five-digit CEP prefix in a hedonic Ridge spline model; it excludes System 1 income, census-sector, and IPTU-standard features.",
        "peer_alignment_factor": None,
        "metrics_vs_avaliacao_reference": {
            "system2_offer_raw_vs_appraisal_reference": metrics(actual, [s2_raw[i] for i in ids]),
            "system2_offer_calibrated_vs_appraisal_reference": metrics(actual, [s2_calibrated[i] for i in ids]),
            **({"system2_peer_aligned": metrics(actual, [s2_aligned[i] for i in ids])} if s2_aligned else {}),
            "system1_catboost_submitted": metrics(actual, [peer_rows[i]["s1_submitted"] for i in ids]),
            "system1_arithmetic_90pct_offer": metrics(actual, [peer_rows[i]["s1_arithmetic"] for i in ids]),
            "system1_catboost_rerun_90pct_target": metrics(actual, [s1[i] for i in ids]),
            "system1_catboost_rerun_offer_equivalent": metrics(actual, [s1_offer_equivalent[i] for i in ids]),
            "peer_median": metrics(actual, peer_medians), **colleague_metrics,
        },
        "alignment": {
            "system2_within_7pct_of_any_peer": sum(any(v is not None and v > 0 and abs(s2[i]-v)/v <= .07 for v in peer_rows[i]["peers"].values()) for i in ids),
            "system2_within_7pct_of_januario_or_analysis": sum(any(v is not None and v > 0 and abs(s2[i]-v)/v <= .07 for v in (peer_rows[i]["peers"]["Januario / CatBoost"], peer_rows[i]["peers"]["Analise Evolutiva"])) for i in ids),
            "system2_inside_peer_range": sum(bool([v for v in peer_rows[i]["peers"].values() if v is not None]) and min(v for v in peer_rows[i]["peers"].values() if v is not None) <= s2[i] <= max(v for v in peer_rows[i]["peers"].values() if v is not None) for i in ids),
            "median_abs_difference_system2_vs_system1_submitted_brl": round(statistics.median(abs(s2[i]-peer_rows[i]["s1_submitted"]) for i in ids if peer_rows[i]["s1_submitted"] is not None), 2),
            **({
                "peer_aligned_within_7pct_of_any_reference": sum(any(v is not None and v > 0 and abs(v-s2_aligned[i])/s2_aligned[i] <= MATCH_TOLERANCE for v in [*peer_rows[i]["peers"].values(), peer_rows[i]["s1_submitted"]]) for i in ids),
                "peer_aligned_within_7pct_of_all_three_named": sum(all(v is not None and abs(v-s2_aligned[i])/s2_aligned[i] <= MATCH_TOLERANCE for v in (peer_rows[i]["s1_submitted"], peer_rows[i]["peers"]["Januario / CatBoost"], peer_rows[i]["peers"]["Analise Evolutiva"])) for i in ids),
                "peer_aligned_match_denominator": "system2_estimate_brl",
                "peer_aligned_within_7pct_of_any_named_reference": sum(any(v is not None and v > 0 and abs(v-s2_aligned[i])/s2_aligned[i] <= MATCH_TOLERANCE for v in (peer_rows[i]["s1_submitted"], peer_rows[i]["peers"]["Januario / CatBoost"], peer_rows[i]["peers"]["Analise Evolutiva"])) for i in ids),
                "peer_aligned_within_7pct_of_januario_or_analysis": sum(any(v is not None and v > 0 and abs(v-s2_aligned[i])/s2_aligned[i] <= MATCH_TOLERANCE for v in (peer_rows[i]["peers"]["Januario / CatBoost"], peer_rows[i]["peers"]["Analise Evolutiva"])) for i in ids),
                "peer_aligned_inside_named_reference_range": sum(min(v for v in (peer_rows[i]["s1_submitted"], peer_rows[i]["peers"]["Januario / CatBoost"], peer_rows[i]["peers"]["Analise Evolutiva"]) if v is not None) <= s2_aligned[i] <= max(v for v in (peer_rows[i]["s1_submitted"], peer_rows[i]["peers"]["Januario / CatBoost"], peer_rows[i]["peers"]["Analise Evolutiva"]) if v is not None) for i in ids),
                "median_abs_difference_peer_aligned_vs_system1_submitted_brl": round(statistics.median(abs(s2_aligned[i]-peer_rows[i]["s1_submitted"]) for i in ids if peer_rows[i]["s1_submitted"] is not None), 2),
            } if s2_aligned else {}),
        },
        "rows_csv": str(OUT_CSV.relative_to(ROOT)),
    }
    # Fill the standard last four output fields in the input template.
    out = load_workbook(SOURCE)
    sh = out["teste"]
    for i in ids:
        r = items[i]["source_row"]
        val = s2_calibrated[i]; area = items[i]["area_privativa_m2"]
        sh.cell(r, 23, val).number_format = '"R$" #,##0.00'
        sh.cell(r, 24, round(val/area, 2) if area else None).number_format = '"R$" #,##0.00'
        sh.cell(r, 25, "Hedonic Ridge spline with CEP micro-location - System 2 v4")
        sh.cell(r, 26, "Target: full asking/list price. Not an independent market/appraisal valuation. Missing fields are treated as absent.")
        sh.cell(r, 26).alignment = Alignment(wrap_text=True, vertical="top")
    out.save(OUT_XLSX); out.close()
    offer_alignment = {}
    estimate_sources = [(name, lambda i, name=name: peer_rows[i]["peers"][name]) for name in peer_names]
    estimate_sources += [("Sistema 1 / Guilherme CatBoost convertido para oferta (dividido por 0,90)", lambda i: round(peer_rows[i]["s1_submitted"] / 0.9, 2) if peer_rows[i]["s1_submitted"] else None),
                         ("Sistema 1 / calculo aritmetico 90% da oferta (coluna de referencia)", lambda i: peer_rows[i]["s1_arithmetic"]),
                         ("Sistema 2 v4 oferta sem calibracao", lambda i: s2_raw[i]),
                         ("Sistema 2 v4 oferta calibrada (padrao de deploy)", lambda i: s2_calibrated[i]),
                                                  ("Sistema 1 / CatBoost reexecutado convertido para oferta (dividido por 0,90)", lambda i: s1_offer_equivalent[i])]
    for label, getter in estimate_sources:
        valid = [(peer_rows[i]["offer"], getter(i)) for i in ids
                 if peer_rows[i]["offer"] is not None and peer_rows[i]["offer"] > 0 and getter(i) is not None]
        offer_alignment[label] = {
            "within_7pct_count": sum(abs(value - offer) / offer <= MATCH_TOLERANCE for offer, value in valid),
            "compared_count": len(valid),
        }
    summary["alignment_vs_offer"] = {
        "rule": "abs(estimativa - valor_oferta) / valor_oferta <= 0.07",
        "counts_by_estimate": offer_alignment,
    }
    # Development-only benchmark sheet; deploy output uses calibrated System 2.
    cmp = load_workbook(PEERS)
    sh = cmp["teste"]
    c2, c2_cal, c1_sub, c1_run, c1_formula, status_col = (sh.max_column+1, sh.max_column+2, sh.max_column+3, sh.max_column+4, sh.max_column+5, sh.max_column+6)
    headers = [(c2, "System 2 v4 | calibrated offer estimate (deploy default)"),
               (c2_cal, "System 2 v4 | raw offer estimate (diagnostic)"),
               (c1_sub, "System 1 submitted | implied full-offer equivalent (divide by 0.90)"),
               (c1_run, "System 1 rerun | implied full-offer equivalent (divide by 0.90)"),
               (c1_formula, "System 1 arithmetic reference | 90% of supplied offer (not CatBoost)"),
               (status_col, "Estimates within +/-7% of asking price")]
    for col, title in headers:
        cell = sh.cell(8, col, title)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="284B63")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        sh.column_dimensions[cell.column_letter].width = 32
    green = PatternFill("solid", fgColor="C6EFCE")
    red = PatternFill("solid", fgColor="F4CCCC")
    for i in ids:
        r = peer_rows[i]["row"]
        offer = peer_rows[i]["offer"]
        estimate_values = [
            ("System 2 v4 calibrated primary", s2_calibrated[i], c2),
            ("System 2 v4 raw diagnostic", s2_raw[i], c2_cal),
            ("System 1 submitted offer-equivalent", round(peer_rows[i]["s1_submitted"] / .9, 2) if peer_rows[i]["s1_submitted"] else None, c1_sub),
            ("System 1 rerun offer-equivalent", s1_offer_equivalent[i], c1_run),
            ("System 1 arithmetic 90% of offer", peer_rows[i]["s1_arithmetic"], c1_formula),
        ]
        peer_values = [(name, value, 22 + peer_names.index(name)) for name, value in peer_rows[i]["peers"].items()]
        for _, value, col in estimate_values:
            cell = sh.cell(r, col, value)
            cell.number_format = '\"R$\" #,##0.00'
        matches = []
        for name, value, col in peer_values + estimate_values:
            within = offer is not None and offer > 0 and value is not None and abs(value - offer) / offer <= MATCH_TOLERANCE
            sh.cell(r, col).fill = green if within else red
            if within:
                matches.append(name)
        status = sh.cell(r, status_col, "; ".join(matches) if matches else "No estimate within +/-7% of asking price")
        primary_match = offer is not None and offer > 0 and abs(s2_calibrated[i] - offer) / offer <= MATCH_TOLERANCE
        status.fill = green if primary_match else red
        status.alignment = Alignment(wrap_text=True, vertical="top")
        # The original System 1 submitted column targets 90% of offer; keep it uncolored.
        sh.cell(r, 29).fill = PatternFill(fill_type=None)
    sm = cmp.create_sheet("Resumo Sistema 2")
    sm.append(["Comparação dos sistemas | Sistema 2 Ridge independente como resultado principal"])
    sm.append(["Amostra", f"{len(ids)} imoveis comparados; {len(items)} no arquivo de entrada."])
    sm.append(["Target", summary["system2_target_note"]])

    sm.append(["System 2 features", summary["feature_scope_note"]])
    sm.append(["Color rule", "Each estimate is compared with asking price. Green: 93%-107%; red: outside the band. abs(estimate-offer)/offer <= 7%."])
    sm.append(["System 2 calibrated primary", "Hedonic Ridge v4 trained for full asking price; separate offer calibration is enabled as the deploy default. No peer-derived factor is applied."])
    sm.append(["Offer calibration", "The factor comes from a separate district-held-out offer sample. It worsened independent geographic holdout MAE and MAPE; that limitation is retained in the report."])
    sm.append(["System 1 comparison", summary["system1_conversion_note"]])
    sm.append(["System 1 arithmetic column", summary["system1_arithmetic_note"]])
    sm.append([]); sm.append(["Modelo vs AVALIAÇÃO de referência", "N", "MAE (R$)", "RMSE (R$)", "MAPE (%)", "Viés (R$)"])
    for name, metric in summary["metrics_vs_avaliacao_reference"].items():
        sm.append([name, metric["n"], metric["mae_brl"], metric["rmse_brl"], metric["mape_percent"], metric["bias_brl"]])
    sm.append([]); sm.append(["Aderência Sistema 2", "Quantidade"])
    sm.append([]); sm.append(["Estimativas dentro de ±7% do valor de oferta/anúncio", "Dentro da faixa", "Comparadas"])
    for label, counts in offer_alignment.items():
        sm.append([label, counts["within_7pct_count"], counts["compared_count"]])
    for cell in sm[6]:
        cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="284B63")
    sm.column_dimensions["A"].width = 54
    for col in "BCDEF": sm.column_dimensions[col].width = 20
    cmp.save(OUT_COMPARE); cmp.close(); swb.close(); pwb.close()
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0])); writer.writeheader(); writer.writerows(results)
    return summary
if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))

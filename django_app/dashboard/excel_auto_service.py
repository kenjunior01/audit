"""
Excel Auto — a experiência de 1 clique do Excel Studio (método REA aplicado à UX).
==================================================================================
O utilizador larga UM ficheiro (ou clica "Testar com exemplo") e recebe, numa
única resposta:
  · folha + mapeamento detetados (com retry multi-folha resiliente)
  · perfil dos dados (linhas, período, totais, fornecedores, categorias)
  · score de QUALIDADE 0-100 com checks pass/warn/fail e nota A-D
  · score de RISCO (Benford, duplicados, fraccionamento, redondos, weekend)
  · insights narrativos determinísticos em PT
  · próximos passos sugeridos (importar / relatório / copiloto)

E fecha o ciclo:
  · Reconciliação Auto — 2 ficheiros (ou ficheiro vs base) cruzados sem configuração
  · Dossiê de Auditoria — analisa, importa, gera o painel REA e consolida
    tudo num único workbook premium

Princípio de leitura pura: NADA é importado sem um clique explícito do
utilizador (Importar / Dossiê completo).
"""

import io
import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from . import excel_service as es

logger = logging.getLogger(__name__)

GRADE_MSG = {
    "A": "Dados prontos para importar e analisar.",
    "B": "Bons dados — pequenos avisos a rever.",
    "C": "Dados utilizáveis, mas com problemas relevantes.",
    "D": "Dados frágeis — corrija antes de confiar nas conclusões.",
}

RISK_LEVEL_MSG = {
    "low": "Risco baixo",
    "medium": "Risco médio",
    "high": "Risco elevado",
}


# ---------------------------------------------------------------------------
# Núcleo — folha + mapeamento + linhas (retry multi-folha resiliente)
# ---------------------------------------------------------------------------

def _read_auto_frame(frames: dict, sheet: str = None, filename: str = ""):
    """Folha + mapeamento + linhas padronizadas, com retry multi-folha:
    se a folha escolhida não produzir linhas válidas, tenta TODAS as outras.
    Devolve (sheet_name, mapping, rows, skipped, sheets_tried)."""
    order = []
    preferred = str(sheet) if sheet else es.pick_best_sheet(frames)
    if preferred in frames:
        order.append(preferred)
    for name in frames:
        if name not in order:
            order.append(str(name))

    last_sheet, last_mapping, last_cols = preferred, {}, []
    for name in order:
        df = frames[name]
        mapping = es.map_columns([str(h) for h in df.columns])
        rows, skipped = es.standardize_frame(df, mapping)
        last_sheet, last_mapping = name, mapping
        last_cols = [str(h) for h in df.columns]
        if rows:
            return name, mapping, rows, skipped, order
    fname = f"'{filename}'" if filename else "deste ficheiro"
    raise ValueError(
        f"Não consegui ler linhas válidas de {fname}: preciso de colunas "
        f"reconhecíveis de Valor e Data. Colunas detetadas em '{last_sheet}': "
        f"{', '.join(last_cols) if last_cols else '(folha vazia)'}. "
        "Abra a aba Importar para associar as colunas manualmente.")


def _fmt_eur(v) -> str:
    """Formato pt-PT para valores nos insights."""
    try:
        s = f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")
    except (TypeError, ValueError):
        return str(v)
    return s


def _quality(rows: list, skipped: list, mapping: dict, df_raw: pd.DataFrame,
             analyses: dict) -> dict:
    """Qualidade 0-100 (penalty acumulado) + checks pass/warn/fail + nota A-D."""
    checks = []
    penalty = 0.0

    total = len(rows) + len(skipped)
    valid = len(rows)

    # 1) mapeamento
    missing_req = [f for f in ("amount", "timestamp") if f not in mapping]
    if missing_req:
        penalty += 20 * len(missing_req)
        checks.append({"id": "mapping", "status": "fail",
                       "label": "Mapeamento de colunas",
                       "detail": f"Campos obrigatórios sem coluna: {', '.join(missing_req)}."})
    else:
        checks.append({"id": "mapping", "status": "pass",
                       "label": "Mapeamento de colunas",
                       "detail": "Valor e Data mapeados automaticamente."})

    # 2) linhas válidas / saltadas
    skip_rate = (len(skipped) / total * 100) if total else 100.0
    penalty += min(skip_rate, 50)
    if valid == 0:
        status = "fail"
    elif skip_rate == 0:
        status = "pass"
    elif skip_rate <= 10:
        status = "warn"
    else:
        status = "fail"
    checks.append({"id": "valid_rows", "status": status,
                   "label": "Linhas válidas",
                   "detail": f"{valid} linhas legíveis, {len(skipped)} ignoradas "
                             f"({skip_rate:.0f}% de rejeição)." if total else
                             "Nenhuma linha lida."})

    # 3) duplicados exatos (fornecedor + valor)
    exact = analyses.get("duplicates", {}).get("exact") or []
    dup_rows = sum(g.get("count", 0) - 1 for g in exact)
    if valid:
        dup_rate = dup_rows / valid * 100
        penalty += min(dup_rate * 1.5, 25)
    if not exact:
        checks.append({"id": "dup_ids", "status": "pass", "label": "IDs duplicados",
                       "detail": "Sem duplicados exatos (mesmo fornecedor + valor)."})
    else:
        total_dup = sum(g.get("total", 0) for g in exact)
        checks.append({"id": "dup_ids", "status": "warn", "label": "IDs duplicados",
                       "detail": f"{len(exact)} grupo(s) de possíveis duplicados — "
                                 f"{_fmt_eur(total_dup)} expostos."})

    # 4) período
    dates = pd.to_datetime(pd.DataFrame(rows).get("timestamp"), errors="coerce").dropna() \
        if rows else pd.Series(dtype="datetime64[ns]")
    distinct_days = dates.dt.date.nunique() if len(dates) else 0
    if distinct_days >= 2:
        span = (dates.max() - dates.min()).days + 1
        checks.append({"id": "period", "status": "pass", "label": "Período dos dados",
                       "detail": f"{distinct_days} dias distintos ({span} dias de intervalo)."})
    elif distinct_days == 1:
        penalty += 5
        checks.append({"id": "period", "status": "warn", "label": "Período dos dados",
                       "detail": "Todas as linhas são do mesmo dia — verifique a coluna Data."})
    else:
        penalty += 10
        checks.append({"id": "period", "status": "fail", "label": "Período dos dados",
                       "detail": "Sem datas legíveis."})

    # 5) valores em falta nas colunas mapeadas
    high_missing = []
    if not df_raw.empty:
        for field, col in (mapping or {}).items():
            if col in df_raw.columns:
                miss = df_raw[col].isna().mean()
                if miss > 0.4:
                    high_missing.append((col, miss))
    if high_missing:
        penalty += min(8 * len(high_missing), 16)
        cols_txt = ", ".join(f"{c} ({m:.0%})" for c, m in high_missing)
        checks.append({"id": "missing", "status": "warn", "label": "Valores em falta",
                       "detail": f"Colunas com muitos vazios: {cols_txt}."})
    else:
        checks.append({"id": "missing", "status": "pass", "label": "Valores em falta",
                       "detail": "Colunas mapeadas completas."})

    # 6) Benford (sinaliza, não penaliza qualidade)
    b = analyses.get("benford") or {}
    if not b.get("applicable"):
        checks.append({"id": "benford", "status": "pass", "label": "Lei de Benford",
                       "detail": b.get("reason", "Não aplicável à amostra.")})
    elif "Conformidade elevada" in b.get("verdict", ""):
        checks.append({"id": "benford", "status": "pass", "label": "Lei de Benford",
                       "detail": f"{b.get('verdict')} (MAD {b.get('mad', 0):.4f})."})
    else:
        checks.append({"id": "benford", "status": "warn", "label": "Lei de Benford",
                       "detail": f"{b.get('verdict')} (MAD {b.get('mad', 0):.4f}) — "
                                 "recomenda-se amostragem."})

    score = int(max(0, min(100, round(100 - penalty))))
    grade = "A" if score >= 90 else ("B" if score >= 75 else ("C" if score >= 60 else "D"))
    return {"score": score, "grade": grade,
            "grade_msg": GRADE_MSG[grade], "checks": checks}


def _insights(result: dict) -> list:
    """10 insights narrativos determinísticos em PT (prioridade: período,
    totais, qualidade, duplicados, Benford, risco; restantes preenchem)."""
    p, q, a = result["profile"], result["quality"], result["analyses"]
    core, flags = [], []
    if p.get("period_start") and p.get("period_end"):
        core.append(f"Período dos dados: {p['period_start']} → {p['period_end']} "
                    f"({p['days_span']} dias, {p['valid_rows']} transações legíveis).")
    else:
        core.append(f"{p['valid_rows']} transações legíveis; sem datas reconhecíveis.")
    core.append(f"Valor total movimentado: {_fmt_eur(p['total_amount'])} "
                f"(média {_fmt_eur(p['avg_amount'])}, máxima {_fmt_eur(p['max_amount'])}).")
    core.append(f"{p['vendors']} fornecedore(s) e {p['categories']} categoria(s) distintas.")
    if p.get("negatives"):
        flags.append(f"{p['negatives']} valor(es) negativo(s) — estornos ou erros de sinal a confirmar.")
    if p.get("currencies"):
        flags.append(f"Moedas detetadas: {', '.join(p['currencies'])}.")
    top = result.get("top_vendors") or []
    if top:
        core.append(f"Maior fornecedor: {top[0]['name']} — {_fmt_eur(top[0]['total'])} "
                    f"({top[0]['share']}% do total, {top[0]['count']} transações).")
    core.append(f"Qualidade dos dados: {q['score']}/100 (nota {q['grade']}) — {q['grade_msg']}")
    dups = (a.get("duplicates") or {}).get("exact") or []
    if dups:
        tot = sum(g.get("total", 0) for g in dups)
        core.append(f"Alerta: {len(dups)} grupo(s) de possíveis duplicados exatos "
                    f"({_fmt_eur(tot)} em risco) — ver folha Duplicados no relatório.")
    b = a.get("benford") or {}
    if b.get("applicable"):
        core.append(f"Lei de Benford: {b['verdict']} (MAD {b.get('mad', 0):.4f} sobre "
                    f"{b.get('n', 0)} valores).")
    core.append(f"Risco global: {a.get('risk_score', 0):.2f} — {a.get('verdict', '')}")
    splits = (a.get("splits") or {}).get("groups") or []
    if splits:
        flags.insert(0, f"Padrão de fraccionamento: {len(splits)} grupo(s) de transações "
                        "seguidas abaixo do limiar que somam acima dele.")
    rv = (a.get("round_values") or {}).get("count") or 0
    if rv:
        flags.append(f"{rv} valor(es) redondo(s) de alto valor (múltiplos de 1 000+) — "
                     "típico de estimativas manuais.")
    wk = (a.get("weekend") or {}).get("count") or 0
    if wk:
        flags.append(f"{wk} transação(ões) registadas em fim-de-semana.")
    return (core + flags)[:10]


def _alert_suggestions(profile: dict, analyses: dict, threshold: float,
                       top_vendors: list, above_count: int) -> list:
    """Sugestões de alertas BI (MeasureAlert) a partir dos padrões detetados.

    Só sugere padrões expressáveis na gramática do motor BI — cada `rule` é
    válida para validate_measure/_validate_filter e pronta para POST /bi/alerts
    (avaliada depois sobre as transações importadas, via BI Studio › Alertas).
    """
    out = []

    wk = (analyses.get("weekend") or {}).get("count") or 0
    if wk:
        out.append({
            "key": "weekend",
            "title": "Transações ao fim de semana",
            "why": f"{wk} transação(ões) deste ficheiro foram registadas ao sábado/"
                   "domingo — padrão típico de lançamentos fora do horário útil.",
            "rule": {
                "name": "Transações ao fim de semana",
                "measure": {"op": "calc",
                            "measure": {"op": "agg", "agg": "count", "field": "id"},
                            "filters": [{"field": "weekday", "op": "in",
                                         "value": ["Saturday", "Sunday"]}]},
                "filters": [], "comparator": "gt", "threshold": 0, "active": True,
            },
        })

    if threshold and float(threshold) > 0:
        t = abs(float(threshold))
        ja = (f"{above_count} transação(ões) do ficheiro já ultrapassam "
              f"{_fmt_eur(t)}." if above_count else
              "Nenhuma transação atual ultrapassa o limiar — a regra fica a "
              "monitorizar futuras importações.")
        out.append({
            "key": "materialidade",
            "title": f"Transações acima da materialidade (≥ {_fmt_eur(t)})",
            "why": ja,
            "rule": {
                "name": f"Transações acima de {_fmt_eur(t)}",
                "measure": {"op": "calc",
                            "measure": {"op": "agg", "agg": "count", "field": "id"},
                            "filters": [{"field": "amount", "op": "gte", "value": t}]},
                "filters": [], "comparator": "gt", "threshold": 0, "active": True,
            },
        })

    top = top_vendors or []
    if len(top) > 1 and (top[0].get("share") or 0) >= 40:
        v = top[0]
        out.append({
            "key": "concentracao",
            "title": f"Concentração no fornecedor {v['name']}",
            "why": f"{v['name']} concentra {v['share']}% do valor do ficheiro "
                   f"({_fmt_eur(v['total'])}) — dependência a monitorizar.",
            "rule": {
                "name": f"Concentração: {v['name']}"[:120],
                "measure": {"op": "calc",
                            "measure": {"op": "agg", "agg": "sum", "field": "amount"},
                            "filters": [{"field": "vendor", "op": "eq",
                                         "value": str(v["name"])}]},
                "filters": [], "comparator": "gte",
                "threshold": float(v["total"]), "active": True,
            },
        })
    return out


def auto_analyze(content: bytes, filename: str, threshold: float = 10000.0,
                 sheet: str = None) -> dict:
    """UMA chamada = análise completa (leitura pura — não importa nada)."""
    frames = es.read_uploaded_file(content, filename)
    if not frames:
        raise ValueError("Ficheiro vazio ou ilegível (formatos suportados: "
                         "xlsx, xlsm, xls, csv).")

    sheet_name, mapping, rows, skipped, tried = _read_auto_frame(
        frames, sheet=sheet, filename=filename)
    df_raw = frames[sheet_name]
    df = pd.DataFrame(rows)

    analyses = es.run_all_analyses(df, threshold=threshold) if not df.empty else {
        "rows_analyzed": 0, "benford": {"applicable": False},
        "duplicates": {"exact": [], "fuzzy": []}, "round_values": {"items": [], "count": 0},
        "weekend": {"items": [], "count": 0}, "splits": {"groups": []},
        "risk_score": 0, "verdict": "Sem linhas para analisar.",
    }

    # perfil
    amounts = pd.to_numeric(df["amount"], errors="coerce").dropna() if not df.empty \
        else pd.Series(dtype=float)
    dts = pd.to_datetime(df["timestamp"], errors="coerce").dropna() if not df.empty \
        else pd.Series(dtype="datetime64[ns]")
    profile = {
        "total_rows": int(sum(len(f) for f in frames.values())),
        "valid_rows": int(len(rows)),
        "skipped_rows": int(len(skipped)),
        "columns": [str(h) for h in df_raw.columns],
        "period_start": dts.min().strftime("%Y-%m-%d") if len(dts) else None,
        "period_end": dts.max().strftime("%Y-%m-%d") if len(dts) else None,
        "days_span": int((dts.max() - dts.min()).days) + 1 if len(dts) else 0,
        "vendors": int(df["vendor"].nunique()) if "vendor" in df and not df.empty else 0,
        "categories": int(df["category"].nunique()) if "category" in df and not df.empty else 0,
        "total_amount": round(float(amounts.sum()), 2) if len(amounts) else 0.0,
        "avg_amount": round(float(amounts.mean()), 2) if len(amounts) else 0.0,
        "max_amount": round(float(amounts.abs().max()), 2) if len(amounts) else 0.0,
        "negatives": int((amounts < 0).sum()) if len(amounts) else 0,
        "currencies": sorted({str(c) for c in df.get("currency", pd.Series(dtype=str)).dropna().unique()})[:6]
        if "currency" in df and not df.empty else [],
    }

    # top fornecedores / categorias
    def _top(group_col):
        if df.empty or group_col not in df:
            return []
        g = (df.assign(_v=pd.to_numeric(df["amount"], errors="coerce"))
               .dropna(subset=["_v"]).groupby(group_col)["_v"]
               .agg(["sum", "count"]).sort_values("sum", ascending=False).head(5))
        total = float(g["sum"].sum()) or 1.0
        return [{"name": str(idx), "total": round(float(r["sum"]), 2),
                 "count": int(r["count"]), "share": round(float(r["sum"]) / total * 100, 1)}
                for idx, r in g.iterrows()]

    top_vendors = _top("vendor")
    by_category = _top("category")

    quality = _quality(rows, skipped, mapping, df_raw, analyses)
    above_count = int((amounts.abs() >= abs(float(threshold or 0))).sum()) \
        if len(amounts) and threshold else 0

    risk = {
        "score": analyses.get("risk_score", 0),
        "verdict": analyses.get("verdict", ""),
        "level": ("low" if analyses.get("risk_score", 0) == 0
                  else "medium" if analyses.get("risk_score", 0) <= 0.6 else "high"),
        "benford_applicable": bool((analyses.get("benford") or {}).get("applicable")),
        "duplicates_exact": len((analyses.get("duplicates") or {}).get("exact") or []),
        "round_values": (analyses.get("round_values") or {}).get("count", 0),
        "weekend": (analyses.get("weekend") or {}).get("count", 0),
        "splits": len((analyses.get("splits") or {}).get("groups") or []),
    }

    result = {
        "file": filename,
        "sheet": sheet_name,
        "sheets": [{"name": str(n), "rows": int(len(f))} for n, f in frames.items()],
        "sheets_tried": tried,
        "mapping": mapping,
        "mapping_missing": [f for f in es.REQUIRED_FIELDS if f not in mapping],
        "profile": profile,
        "quality": quality,
        "risk": risk,
        "insights": [],
        "top_vendors": top_vendors,
        "by_category": by_category,
        "analyses": analyses,
        "next_steps": ["import", "report", "copilot"],
    }
    result["insights"] = _insights(result)
    result["alert_suggestions"] = _alert_suggestions(
        profile, analyses, threshold, top_vendors, above_count)
    return result


# ---------------------------------------------------------------------------
# Relatório Premium da análise Auto
# ---------------------------------------------------------------------------

def _auto_df_pt(std_rows: list) -> pd.DataFrame:
    """DataFrame com colunas PT para os workbooks (Dados)."""
    df = pd.DataFrame(std_rows)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M")
        df = df.rename(columns={
            "transaction_id": "ID Transação", "vendor": "Fornecedor",
            "amount": "Valor", "currency": "Moeda", "timestamp": "Data",
            "category": "Categoria", "user_id": "Usuário", "status": "Estado"})
    return df


def _quality_checks_df(quality: dict) -> pd.DataFrame:
    return pd.DataFrame([{
        "Verificação": c["label"],
        "Estado": {"pass": "OK", "warn": "Atenção", "fail": "Falha"}[c["status"]],
        "Detalhe": c["detail"],
    } for c in quality["checks"]])


def build_auto_report(content: bytes, filename: str, threshold: float = 10000.0):
    """Workbook premium com Qualidade, Risco e análises do ficheiro carregado.
    -> (bytes_xlsx, nome_ficheiro)."""
    result = auto_analyze(content, filename, threshold=threshold)
    analyses, profile, quality = result["analyses"], result["profile"], result["quality"]

    frames = es.read_uploaded_file(content, filename)
    df_raw = frames[result["sheet"]]
    std_rows, _ = es.standardize_frame(df_raw, result["mapping"])
    df = _auto_df_pt(std_rows)

    extra = [{"name": "Qualidade", "df": _quality_checks_df(quality)}]
    b = analyses.get("benford") or {}
    if b.get("applicable") and b.get("distribution"):
        extra.append({"name": "Benford",
                      "df": pd.DataFrame(b["distribution"]).rename(columns={
                          "digit": "Dígito", "observed_pct": "Observado %",
                          "expected_pct": "Esperado %", "deviation_pct": "Desvio %"})})
    if analyses["duplicates"].get("exact"):
        extra.append({"name": "Duplicados",
                      "df": pd.DataFrame(analyses["duplicates"]["exact"])})
    if analyses["splits"].get("groups"):
        extra.append({"name": "Fraccionamento",
                      "df": pd.DataFrame(analyses["splits"]["groups"])})
    if analyses["round_values"].get("items"):
        extra.append({"name": "Valores Redondos",
                      "df": pd.DataFrame(analyses["round_values"]["items"])})

    wb = es.build_premium_workbook(
        title=f"Análise Auto — {filename}",
        df=df,
        kpis={
            "Linhas Válidas": profile["valid_rows"],
            "Valor Total": profile["total_amount"],
            "Valor Médio": profile["avg_amount"],
            "Fornecedores": profile["vendors"],
            "Qualidade (0-100)": quality["score"],
            "Risco (0-1)": analyses.get("risk_score", 0),
        },
        charts=es.aggregate_for_charts(df.rename(columns={
            "Valor": "amount", "Fornecedor": "vendor",
            "Categoria": "category", "Data": "timestamp"})) if not df.empty else [],
        extra_sheets=extra,
    )
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
    return wb, f"Analise_Auto_{stamp}.xlsx"


# ---------------------------------------------------------------------------
# Importação partilhada + Dossiê de Auditoria (1 clique fecha o ciclo)
# ---------------------------------------------------------------------------

def import_standardized(rows: list, name: str, uploaded_by: str,
                        sheet_name: str, mapping: dict, skipped: list,
                        mode: str = "skip") -> tuple:
    """Núcleo de importação partilhado por /excel/import e /excel/auto/dossier.
    Dedup no ficheiro (mantém 1ª ocorrência) + dedup na base (mode=skip;
    mode=update sobrescreve). Cria ExcelImportJob e notifica.
    -> (criadas, dup, job_id)."""
    from django.db import transaction as db_transaction
    from .models import ExcelImportJob, Transaction
    from .notifications_service import notify_user

    seen, unique_rows = set(), []
    for r in rows:
        if r["transaction_id"] in seen:
            continue
        seen.add(r["transaction_id"])
        unique_rows.append(r)
    duplicates = len(rows) - len(unique_rows)

    existing_ids = set(Transaction.objects.filter(
        transaction_id__in=[r["transaction_id"] for r in unique_rows]
    ).values_list("transaction_id", flat=True))

    to_create = []
    for r in unique_rows:
        if r["transaction_id"] in existing_ids:
            duplicates += 1
            if mode != "update":
                continue
            Transaction.objects.filter(
                transaction_id=r["transaction_id"]).update(
                vendor=r["vendor"], amount=r["amount"], currency=r["currency"],
                timestamp=r["timestamp"], category=r["category"],
                user_id=r["user_id"], status=r["status"])
            continue
        to_create.append(Transaction(**r))

    with db_transaction.atomic():
        created = len(Transaction.objects.bulk_create(to_create, batch_size=500))

    job_id = None
    try:
        job = ExcelImportJob.objects.create(
            file_name=name,
            uploaded_by=uploaded_by,
            rows_imported=created,
            rows_skipped=len(skipped) + duplicates,
            mapping=mapping,
            errors=[str(x) for x in skipped[:200]],
            status="Completed",
            sheet=sheet_name,
        )
        job_id = job.id
    except Exception:
        pass
    try:
        sev = "success" if created else "warn"
        notify_user(uploaded_by, "excel.import",
                    f"Importação concluída: {name}",
                    body=f"{created} transações importadas, {duplicates} "
                         f"duplicados ignorados, {len(skipped)} linhas inválidas.",
                    route="/excel", severity=sev)
    except Exception:
        pass
    return created, duplicates, job_id


def build_dossier(content: bytes, filename: str, threshold: float = 10000.0,
                  user_id: str = "", role: str = "", mode: str = "skip") -> tuple:
    """Dossiê de Auditoria de 1 clique: analisa → importa → painel REA →
    workbook único (Dossiê, Painel, Qualidade, Benford, Duplicados,
    Fraccionamento, Redondos, Dados). -> (bytes_xlsx, nome, meta)."""
    result = auto_analyze(content, filename, threshold=threshold)
    analyses, profile, quality = result["analyses"], result["profile"], result["quality"]

    frames = es.read_uploaded_file(content, filename)
    df_raw = frames[result["sheet"]]
    std_rows, skipped = es.standardize_frame(df_raw, result["mapping"])
    created, duplicates, job_id = import_standardized(
        std_rows, filename, uploaded_by=user_id, sheet_name=result["sheet"],
        mapping=result["mapping"], skipped=skipped, mode=mode)

    # Painel REA sobre a base (agora inclui o que acabou de ser importado)
    try:
        from . import bi_auto_service
        panel = bi_auto_service.auto_dashboard(user_id=user_id, role=role)
    except Exception:
        panel = {"kpis": [], "insights": [], "visuals": {}}

    df_pt = _auto_df_pt(std_rows)

    # ---- folha Dossiê: sumário executivo narrativo
    risco_txt = RISK_LEVEL_MSG.get(result["risk"].get("level"), "Risco médio")
    verdict = result["risk"].get("verdict", "—")
    dossier_lines = [
        ("Ficheiro", filename),
        ("Folha analisada", result["sheet"]),
        ("Gerado em", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")),
        ("", ""),
        ("— ANÁLISE —", ""),
        ("Linhas válidas", profile["valid_rows"]),
        ("Linhas ignoradas", profile["skipped_rows"]),
        ("Período", f'{profile.get("period_start") or "—"} → {profile.get("period_end") or "—"}'),
        ("Valor total", profile["total_amount"]),
        ("Fornecedores", profile["vendors"]),
        ("Qualidade", f'{quality["score"]}/100 — nota {quality["grade"]}'),
        ("Risco", f'{risco_txt} ({result["risk"].get("score", 0):.2f}) — {verdict}'),
        ("", ""),
        ("— IMPORTAÇÃO —", ""),
        ("Transações criadas", created),
        ("Duplicados ignorados", duplicates),
        ("Linhas inválidas", len(skipped)),
        ("", ""),
        ("— PAINEL REA —", ""),
    ]
    for k in panel.get("kpis", []):
        dossier_lines.append((k.get("label", ""), k.get("value", "")))
    dossier_lines.append(("", ""))

    dossier_df = pd.DataFrame(dossier_lines, columns=["Resumo", "Valor"])
    painel_df = pd.DataFrame(
        [{"Insight": x} for x in (panel.get("insights") or result["insights"][:5])])

    extra = [{"name": "Dossiê", "df": dossier_df}]
    if not painel_df.empty:
        extra.append({"name": "Painel", "df": painel_df})
    extra.append({"name": "Qualidade", "df": _quality_checks_df(quality)})
    b = analyses.get("benford") or {}
    if b.get("applicable") and b.get("distribution"):
        extra.append({"name": "Benford",
                      "df": pd.DataFrame(b["distribution"]).rename(columns={
                          "digit": "Dígito", "observed_pct": "Observado %",
                          "expected_pct": "Esperado %", "deviation_pct": "Desvio %"})})
    if analyses["duplicates"].get("exact"):
        extra.append({"name": "Duplicados",
                      "df": pd.DataFrame(analyses["duplicates"]["exact"])})
    if analyses["splits"].get("groups"):
        extra.append({"name": "Fraccionamento",
                      "df": pd.DataFrame(analyses["splits"]["groups"])})
    if analyses["round_values"].get("items"):
        extra.append({"name": "Valores Redondos",
                      "df": pd.DataFrame(analyses["round_values"]["items"])})

    charts = es.aggregate_for_charts(pd.DataFrame(std_rows)) if std_rows else []

    wb = es.build_premium_workbook(
        title=f"Dossiê de Auditoria — {filename}",
        df=df_pt,
        kpis={
            "Transações Importadas": created,
            "Linhas Válidas": profile["valid_rows"],
            "Valor Total": profile["total_amount"],
            "Qualidade (0-100)": quality["score"],
            "Risco (0-1)": analyses.get("risk_score", 0),
            "Fornecedores": profile["vendors"],
        },
        charts=charts,
        extra_sheets=extra,
    )
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
    meta = {"imported": created, "duplicates": duplicates,
            "skipped": len(skipped), "sheet": result["sheet"],
            "job_id": job_id, "quality": quality, "risk": result["risk"]}
    return wb, f"Dossier_Auditoria_{stamp}.xlsx", meta


# ---------------------------------------------------------------------------
# Reconciliação Auto — 2 fontes cruzadas sem configuração
# ---------------------------------------------------------------------------

def _verdict_reconcile(s: dict) -> tuple:
    """(rótulo, nível, mensagem) determinísticos a partir do resumo."""
    rows_a = s.get("rows_a") or 0
    matched = s.get("matched") or 0
    rate = (matched / rows_a) if rows_a else 0.0
    pct = rate * 100
    diff = s.get("difference") or 0.0
    if rows_a and rate >= 0.999 and not s.get("unmatched_b") and abs(diff) <= 0.05:
        return ("Reconciliação perfeita", "ok",
                "Todas as linhas de A têm correspondência em B e os totais batem certo.")
    if rate >= 0.9:
        return ("Quase perfeita", "warn",
                f"{pct:.0f}% conciliado; diferença de {_fmt_eur(diff)} — rever órfãos.")
    if rate >= 0.5:
        return ("Parcial", "warn",
                f"Reconciliação parcial — {pct:.0f}% conciliado ({matched} de {rows_a}); "
                "análise dos órfãos recomendada.")
    return ("Divergência relevante", "high",
            f"Divergência relevante — só {pct:.0f}% conciliado; investigação necessária.")


def auto_reconcile(content_a: bytes, name_a: str,
                   content_b: bytes = None, name_b: str = None,
                   sheet: str = None, df_b: pd.DataFrame = None,
                   amount_tol: float = 0.01, date_tol_days: int = 3) -> dict:
    """Reconciliação de 1 clique: folha+mapeamento automáticos nos 2 lados.
    df_b direto = lado B é a base de dados. -> dict com summary, veredicto,
    insights, matches e órfãos."""
    frames_a = es.read_uploaded_file(content_a, name_a)
    sheet_a, map_a, rows_a, skipped_a, tried_a = _read_auto_frame(
        frames_a, sheet=sheet, filename=name_a)
    df_a = pd.DataFrame(rows_a)

    source_b = "ficheiro"
    if df_b is not None:
        # lado B pode chegar bruto (colunas PT) — canonicalizar se necessário
        if "amount" not in df_b.columns:
            map_b = es.map_columns([str(c) for c in df_b.columns])
            rows_b, _ = es.standardize_frame(df_b, map_b)
            if not rows_b:
                raise ValueError("A fonte B não tem linhas legíveis — preciso de "
                                 "colunas reconhecíveis de Valor e Data.")
            df_b = pd.DataFrame(rows_b)
        sheet_b, name_b_out = "—", "Base de dados (transações importadas)"
    else:
        if not content_b:
            raise ValueError("Envie o 2º ficheiro (file_b) ou use use_db_b=1 "
                             "para reconciliar contra a base de dados.")
        frames_b = es.read_uploaded_file(content_b, name_b)
        sheet_b, map_b, rows_b, skipped_b, tried_b = _read_auto_frame(
            frames_b, filename=name_b)
        df_b = pd.DataFrame(rows_b)
        name_b_out = name_b
        source_b = "ficheiro"

    rec = es.reconcile(df_a, df_b, amount_tol=amount_tol, date_tol_days=date_tol_days)
    if rec.get("error"):
        raise ValueError(rec["error"])

    s = rec["summary"]
    label, level, message = _verdict_reconcile(s)

    insights = [
        f"{s['matched']} de {s['rows_a']} linhas de A conciliadas com B "
        f"({(s['matched'] / s['rows_a'] * 100) if s['rows_a'] else 0:.0f}%).",
        f"Diferença de totais: {_fmt_eur(s['difference'])} "
        f"(A {_fmt_eur(s['total_a'])} vs B {_fmt_eur(s['total_b'])}).",
    ]
    if s.get("weak_matches"):
        insights.append(f"{s['weak_matches']} correspondência(s) fraca(s) — fornecedor "
                        "semelhante mas não idêntico; confirmar entidades.")
    if s.get("unmatched_a"):
        insights.append(f"{s['unmatched_a']} linha(s) só em A (sem correspondência em B) "
                        "— pagamentos não lançados ou datas divergentes.")
    if s.get("unmatched_b"):
        insights.append(f"{s['unmatched_b']} linha(s) só em B — recebimentos sem documento "
                        "de suporte em A.")
    insights.append(f"Veredicto: {label} — {message}")

    return {
        "file_a": name_a, "sheet_a": sheet_a,
        "file_b": name_b_out, "source_b": source_b,
        "threshold": {"amount_tol": amount_tol, "date_tol_days": date_tol_days},
        "summary": s,
        "verdict": label, "level": level, "message": message,
        "insights": insights,
        "matches": rec["matches"][:50],
        "unmatched_a": rec["unmatched_a"][:20],
        "unmatched_b": rec["unmatched_b"][:20],
    }


def build_reconcile_report(content_a: bytes, name_a: str,
                           content_b: bytes = None, name_b: str = None,
                           df_b: pd.DataFrame = None,
                           amount_tol: float = 0.01,
                           date_tol_days: int = 3) -> tuple:
    """Workbook da reconciliação Auto (Sumário + Conciliadas + Só em A + Só em B).
    -> (bytes_xlsx, nome_ficheiro)."""
    r = auto_reconcile(content_a, name_a, content_b=content_b, name_b=name_b,
                       df_b=df_b, amount_tol=amount_tol, date_tol_days=date_tol_days)
    s = r["summary"]

    matches_df = pd.DataFrame(r["matches"]) if r["matches"] else pd.DataFrame(
        columns=["a_id", "b_id", "amount"])
    matches_df = matches_df.rename(columns={
        "a_id": "ID em A", "b_id": "ID em B", "a_vendor": "Fornecedor em A",
        "b_vendor": "Fornecedor em B", "a_date": "Data em A", "b_date": "Data em B",
        "amount": "Valor", "vendor_similarity": "Semelhança", "weak": "Fraca"})
    only_a_df = pd.DataFrame(r["unmatched_a"]) if r["unmatched_a"] \
        else pd.DataFrame([{"(sem linhas)": "— todas conciliadas —"}])
    only_b_df = pd.DataFrame(r["unmatched_b"]) if r["unmatched_b"] \
        else pd.DataFrame([{"(sem linhas)": "— todas conciliadas —"}])

    extra = [{"name": "Só em A", "df": only_a_df},
             {"name": "Só em B", "df": only_b_df}]

    pie_df = pd.DataFrame({
        "Resultado": ["Conciliadas", "Só em A", "Só em B"],
        "Total": [s["matched"], s["unmatched_a"], s["unmatched_b"]]})

    wb = es.build_premium_workbook(
        title=f"Reconciliação Auto — {name_a} vs {r['file_b']}",
        df=matches_df,
        kpis={
            "Linhas em A": s["rows_a"],
            "Linhas em B": s["rows_b"],
            "Conciliadas": s["matched"],
            "Só em A": s["unmatched_a"],
            "Só em B": s["unmatched_b"],
            "Diferença": s["difference"],
            "Veredicto": r["verdict"],
        },
        charts=[{"type": "pie", "title": "Resultado da reconciliação", "df": pie_df}],
        extra_sheets=extra,
    )
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
    return wb, f"Reconciliacao_Auto_{stamp}.xlsx"


# ---------------------------------------------------------------------------
# Análise Comparativa — o que mudou entre dois períodos (A → B)
# ---------------------------------------------------------------------------

def _cmp_overview(df: pd.DataFrame, threshold: float) -> dict:
    """Overview compacto de um df canônico (rows canônicas do standardize)."""
    amounts = pd.to_numeric(df["amount"], errors="coerce").dropna()
    dates = pd.to_datetime(df["timestamp"], errors="coerce").dropna()
    n_weekend = 0
    if len(dates):
        n_weekend = int(dates.dt.day_name().isin(["Saturday", "Sunday"]).sum())
    ids = df["transaction_id"].astype(str)
    return {
        "rows": int(len(df)),
        "total": float(amounts.sum()),
        "avg": float(amounts.mean()) if len(amounts) else 0.0,
        "max": float(amounts.max()) if len(amounts) else 0.0,
        "n_vendors": int(df["vendor"].nunique()),
        "weekend": n_weekend,
        "duplicates": int(ids.duplicated().sum()),
        "above_threshold": int((amounts.abs() >= abs(float(threshold))).sum()),
        "period": ({"start": dates.min().date().isoformat(),
                    "end": dates.max().date().isoformat()} if len(dates) else {}),
    }


def _pct(delta: float, base: float) -> float:
    """Variação % honesta: denominador |base|; base 0 → 0.0 (evita ∞)."""
    if not base:
        return 0.0
    return delta / abs(base) * 100.0


def _verdict_compare(ov_a: dict, ov_b: dict, rep_count: int,
                     new_share: float) -> tuple:
    """(rótulo, nível, mensagem) determinísticos para a comparação."""
    tot_a, tot_b = ov_a["total"], ov_b["total"]
    pct = _pct(tot_b - tot_a, tot_a)
    flags = (1 if rep_count > 0 else 0) + (1 if new_share >= 0.2 else 0)
    ap = abs(pct)
    if ap < 5 and flags == 0:
        return ("Períodos estáveis", "ok",
                f"Total varia {pct:+.1f}% entre A e B, sem sinais de alerta.")
    if ap >= 30 or flags >= 2:
        msg = f"Total varia {pct:+.1f}%"
        if rep_count:
            msg += f" e há {rep_count} documento(s) repetido(s) nos dois ficheiros"
        return ("Variação acentuada", "high", msg + " — investigação recomendada.")
    return ("Variação moderada", "warn",
            f"Total varia {pct:+.1f}% entre períodos — rever os principais movimentos.")


def auto_compare(content_a: bytes, name_a: str,
                 content_b: bytes, name_b: str,
                 sheet: str = None, threshold: float = 10000.0) -> dict:
    """Análise comparativa de 1 clique entre dois períodos (A = base, B = novo).
    Folha+mapeamento automáticos nos dois lados. Devolve overview com deltas,
    movimentos por fornecedor (aumentos/reduções/novos/desaparecidos), padrões
    (fim-de-semana, duplicados, materialidade), documentos repetidos entre
    ficheiros, veredicto e insights narrativos."""
    frames_a = es.read_uploaded_file(content_a, name_a)
    sheet_a, _, rows_a, _, _ = _read_auto_frame(frames_a, sheet=sheet,
                                                filename=name_a)
    df_a = pd.DataFrame(rows_a)
    frames_b = es.read_uploaded_file(content_b, name_b)
    sheet_b, _, rows_b, _, _ = _read_auto_frame(frames_b, sheet=sheet,
                                                filename=name_b)
    df_b = pd.DataFrame(rows_b)

    if df_a.empty or df_b.empty:
        raise ValueError("Não consegui ler linhas válidas nos dois ficheiros — "
                         "preciso de colunas reconhecíveis de Valor e Data em A e B.")

    ov_a = _cmp_overview(df_a, threshold)
    ov_b = _cmp_overview(df_b, threshold)

    ta = df_a.assign(v=df_a["vendor"].fillna("(sem fornecedor)")).groupby("v")["amount"].sum()
    tb = df_b.assign(v=df_b["vendor"].fillna("(sem fornecedor)")).groupby("v")["amount"].sum()
    deltas = [{"vendor": v,
               "a": float(ta.get(v, 0.0)), "b": float(tb.get(v, 0.0))}
              for v in sorted(set(ta.index) | set(tb.index))]
    for d in deltas:
        d["delta"] = d["b"] - d["a"]
        d["pct"] = round(_pct(d["delta"], d["a"]), 1)
    increases = sorted([d for d in deltas if d["delta"] > 0.005],
                       key=lambda d: d["delta"], reverse=True)[:5]
    decreases = sorted([d for d in deltas if d["delta"] < -0.005],
                       key=lambda d: d["delta"])[:5]
    new_vendors = sorted([d for d in deltas if d["a"] == 0 and d["b"] > 0],
                         key=lambda d: d["b"], reverse=True)[:10]
    dropped = sorted([d for d in deltas if d["b"] == 0 and d["a"] > 0],
                     key=lambda d: d["a"], reverse=True)[:10]
    new_total = sum(d["b"] for d in new_vendors)
    new_share = (new_total / ov_b["total"]) if ov_b["total"] else 0.0

    # documentos (transaction_id) presentes nos DOIS ficheiros
    ia = df_a[["transaction_id", "vendor", "amount"]].copy()
    ia["vendor"] = ia["vendor"].fillna("(sem fornecedor)")
    ib = df_b[["transaction_id", "vendor", "amount"]].copy()
    ib["vendor"] = ib["vendor"].fillna("(sem fornecedor)")
    m = ia.merge(ib, on="transaction_id", suffixes=("_a", "_b"))
    rep_count = int(m["transaction_id"].nunique()) if len(m) else 0
    rep_rows = []
    for r in m.itertuples(index=False):
        va_, vb_ = pd.to_numeric(r.amount_a, errors="coerce"), \
            pd.to_numeric(r.amount_b, errors="coerce")
        rep_rows.append({
            "id": str(r.transaction_id),
            "vendor_a": r.vendor_a, "vendor_b": r.vendor_b,
            "amount_a": float(va_) if pd.notna(va_) else None,
            "amount_b": float(vb_) if pd.notna(vb_) else None,
            "same_amount": bool(pd.notna(va_) and pd.notna(vb_)
                                and abs(va_ - vb_) <= 0.01),
        })
    rep_rows = rep_rows[:20]

    label, level, message = _verdict_compare(ov_a, ov_b, rep_count, new_share)

    tot_delta = ov_b["total"] - ov_a["total"]
    insights = [
        f"Linhas: {ov_a['rows']} → {ov_b['rows']} ({ov_b['rows'] - ov_a['rows']:+d}); "
        f"total: {_fmt_eur(ov_a['total'])} → {_fmt_eur(ov_b['total'])} "
        f"({_pct(tot_delta, ov_a['total']):+.1f}%).",
    ]
    if ov_a.get("period") and ov_b.get("period"):
        insights.append(
            f"Períodos: A {ov_a['period']['start']} → {ov_a['period']['end']} · "
            f"B {ov_b['period']['start']} → {ov_b['period']['end']}.")
    if increases:
        d0 = increases[0]
        insights.append(
            f"Maior aumento: {d0['vendor']} ({_fmt_eur(d0['a'])} → {_fmt_eur(d0['b'])}, "
            f"{d0['pct']:+.1f}%).")
    if decreases:
        d0 = decreases[0]
        insights.append(
            f"Maior redução: {d0['vendor']} ({_fmt_eur(d0['a'])} → {_fmt_eur(d0['b'])}, "
            f"{d0['pct']:+.1f}%).")
    if new_vendors:
        insights.append(
            f"{len(new_vendors)} fornecedor(es) novo(s) em B — {_fmt_eur(new_total)} "
            f"({new_share * 100:.0f}% do total de B): "
            + ", ".join(d["vendor"] for d in new_vendors[:3]) + ".")
    if dropped:
        insights.append(
            f"{len(dropped)} fornecedor(es) sem movimentos em B: "
            + ", ".join(d["vendor"] for d in dropped[:3]) + ".")
    if ov_b["weekend"] != ov_a["weekend"]:
        insights.append(
            f"Fim-de-semana: {ov_a['weekend']} → {ov_b['weekend']} transações "
            f"({ov_b['weekend'] - ov_a['weekend']:+d}).")
    if ov_b["above_threshold"] != ov_a["above_threshold"]:
        insights.append(
            f"Acima da materialidade ({_fmt_eur(threshold)}): "
            f"{ov_a['above_threshold']} → {ov_b['above_threshold']} "
            f"({ov_b['above_threshold'] - ov_a['above_threshold']:+d}).")
    if rep_count:
        insights.append(
            f"{rep_count} documento(s) repetido(s) nos dois ficheiros — se os "
            "períodos não se sobrepõem, confirmar que não são pagamentos duplicados.")
    insights.append(f"Veredicto: {label} — {message}")

    return {
        "file_a": name_a, "sheet_a": sheet_a,
        "file_b": name_b, "sheet_b": sheet_b,
        "threshold": threshold,
        "overview": {"a": ov_a, "b": ov_b,
                     "delta": {"rows": ov_b["rows"] - ov_a["rows"],
                               "total": tot_delta,
                               "total_pct": round(_pct(tot_delta, ov_a["total"]), 1)}},
        "vendors": {"deltas": deltas, "top_increases": increases,
                    "top_decreases": decreases, "new": new_vendors,
                    "dropped": dropped},
        "patterns": {"weekend": {"a": ov_a["weekend"], "b": ov_b["weekend"]},
                     "duplicates": {"a": ov_a["duplicates"], "b": ov_b["duplicates"]},
                     "above_threshold": {"a": ov_a["above_threshold"],
                                         "b": ov_b["above_threshold"]}},
        "repeated_ids": {"count": rep_count, "rows": rep_rows},
        "verdict": label, "level": level, "message": message,
        "insights": insights,
    }


def build_compare_report(content_a: bytes, name_a: str,
                         content_b: bytes, name_b: str,
                         sheet: str = None,
                         threshold: float = 10000.0) -> tuple:
    """Workbook da Análise Comparativa (Sumário + Variação por fornecedor +
    Novos/Desaparecidos + Repetidos + Padrões). -> (bytes_xlsx, nome)."""
    r = auto_compare(content_a, name_a, content_b, name_b,
                     sheet=sheet, threshold=threshold)
    ov, v, p = r["overview"], r["vendors"], r["patterns"]

    main_df = pd.DataFrame(v["deltas"]).rename(columns={
        "vendor": "Fornecedor", "a": "Total em A", "b": "Total em B",
        "delta": "Diferença", "pct": "Variação %"})
    main_df = main_df.sort_values("Diferença", key=lambda s: s.abs(),
                                  ascending=False)

    def _df(rows, cols):
        return pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=cols)

    novos_df = _df([{"Fornecedor": d["vendor"], "Total em B": d["b"],
                     "% do total de B": round(100 * d["b"] / ov["b"]["total"], 1)
                     if ov["b"]["total"] else 0.0} for d in v["new"]],
                   ["Fornecedor", "Total em B", "% do total de B"])
    fora_df = _df([{"Fornecedor": d["vendor"], "Total em A": d["a"]}
                   for d in v["dropped"]], ["Fornecedor", "Total em A"])
    rep_df = _df([{"Documento": x["id"], "Fornecedor em A": x["vendor_a"],
                   "Fornecedor em B": x["vendor_b"], "Valor em A": x["amount_a"],
                   "Valor em B": x["amount_b"], "Mesmo valor": "sim" if x["same_amount"] else "NÃO"}
                  for x in r["repeated_ids"]["rows"]],
                 ["Documento", "Fornecedor em A", "Fornecedor em B",
                  "Valor em A", "Valor em B", "Mesmo valor"])
    padroes_df = pd.DataFrame([
        {"Padrão": "Fim-de-semana", "Em A": p["weekend"]["a"], "Em B": p["weekend"]["b"]},
        {"Padrão": "Duplicados no próprio ficheiro", "Em A": p["duplicates"]["a"], "Em B": p["duplicates"]["b"]},
        {"Padrão": "Acima da materialidade", "Em A": p["above_threshold"]["a"], "Em B": p["above_threshold"]["b"]},
    ])

    top_chart = pd.DataFrame({
        "Fornecedor": main_df["Fornecedor"].head(10),
        "Diferença": main_df["Diferença"].head(10)})

    wb = es.build_premium_workbook(
        title=f"Análise Comparativa — {name_a} → {r['file_b']}",
        df=main_df,
        kpis={
            "Linhas em A": ov["a"]["rows"],
            "Linhas em B": ov["b"]["rows"],
            "Total em A": ov["a"]["total"],
            "Total em B": ov["b"]["total"],
            "Variação do total": f"{r['overview']['delta']['total_pct']:+.1f}%",
            "Fornecedores novos": len(v["new"]),
            "Sem movimentos em B": len(v["dropped"]),
            "Documentos repetidos": r["repeated_ids"]["count"],
            "Veredicto": r["verdict"],
        },
        charts=[{"type": "bar", "title": "Top 10 variações por fornecedor",
                 "df": top_chart}],
        extra_sheets=[
            {"name": "Novos fornecedores", "df": novos_df},
            {"name": "Sem movimentos em B", "df": fora_df},
            {"name": "Documentos repetidos", "df": rep_df},
            {"name": "Padrões", "df": padroes_df},
        ],
    )
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
    return wb, f"Comparacao_Auto_{stamp}.xlsx"


# ---------------------------------------------------------------------------
# Ficheiro de exemplo (problemas plantados para demonstração)
# ---------------------------------------------------------------------------

def generate_sample_xlsx() -> bytes:
    """Exemplo 'movimentos' com ~60 linhas limpas + 6 problemáticas plantadas:
    1 duplicado exato, 2 valores redondos, 1 par de fraccionamento, 1 linha
    inválida ('N/D'). Datas dinâmicas (últimos ~50 dias) para funcionar com a
    janela de 365 dias da reconciliação vs base."""
    from openpyxl import Workbook

    vendors = ["Belver Construções", " Marques & Filhos", "Norte Logística",
               "TechSupply Portugal", "Office Directo Lda"]
    cats = ["Obras", "Administrativo", "Transportes", "Equipamento", "Consumíveis"]
    base = (datetime.utcnow() - timedelta(days=50)).date()

    wb = Workbook()
    ws = wb.active
    ws.title = "Movimentos"
    ws.append(["Data", "Documento", "Fornecedor", "Categoria", "Descrição",
               "Valor", "Moeda", "Estado"])

    for i in range(60):
        d = (base + timedelta(days=i % 45)).strftime("%Y-%m-%d")
        # valores com decimais variados (evita falsos duplicados) e magnitudes
        # variadas para a distribuição do 1º dígito aproximar Benford;
        # i=0 fica em 1025.5 para o duplicado plantado ter par exato
        valor = 1025.5 if i == 0 else round(
            120.5 + (i * 137.7) % 4800 + (i % 7) * 0.3, 2)
        if i % 9 == 0 and i != 0:
            valor = round(valor * 6.5, 2)
        ws.append([d, f"DOC-{i + 1:04d}", vendors[i % 5].strip(), cats[i % 5],
                   f"Compra #{i + 1}", valor, "EUR", "Approved"])

    # plantados (6 linhas)
    dup_day = base.strftime("%Y-%m-%d")
    ws.append([dup_day, "DOC-2026-0001", vendors[0].strip(), cats[0],
               "Compra #1 (duplicado)", 1025.5, "EUR", "Approved"])
    ws.append([(base + timedelta(days=3)).strftime("%Y-%m-%d"), "DOC-2026-0100",
               vendors[1].strip(), cats[1], "Estimativa anual", 5000, "EUR", "Pending"])
    ws.append([(base + timedelta(days=4)).strftime("%Y-%m-%d"), "DOC-2026-0101",
               vendors[2].strip(), cats[2], "Adiantamento", 3000, "EUR", "Pending"])
    ws.append([(base + timedelta(days=6)).strftime("%Y-%m-%d"), "DOC-2026-0102",
               vendors[3].strip(), cats[3], "Parcela 1", 9800, "EUR", "Approved"])
    ws.append([(base + timedelta(days=6)).strftime("%Y-%m-%d"), "DOC-2026-0103",
               vendors[3].strip(), cats[3], "Parcela 2", 9500, "EUR", "Approved"])
    ws.append([(base + timedelta(days=7)).strftime("%Y-%m-%d"), "DOC-2026-0104",
               vendors[4].strip(), cats[4], "Valor por corrigir", "N/D", "EUR", "Pending"])

    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()

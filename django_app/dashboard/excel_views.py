"""
Excel Studio — Endpoints REST (DRF) para o super auxílio Excel.
================================================================

Rotas (registradas em urls.py):
    POST /excel/preview      → estrutura do ficheiro + mapeamento sugerido + qualidade
    POST /excel/import       → importa transações com o mapeamento confirmado
    GET  /excel/analyze      → análises de auditor sobre as transações da base
    POST /excel/analyze      → análises sobre um ficheiro carregado
    POST /excel/reconcile    → reconcilia 2 ficheiros (ou ficheiro vs base)
    GET  /excel/export       → workbook premium (transactions|alerts|cases|full)
"""

import json
import logging

from django.db import transaction as db_transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from .auth import IsAuditorOrAdmin, IsViewerOrAbove
from .models import Transaction, Alert, AuditCase, ExcelImportJob
from . import excel_service as es
from . import excel_ai_service as ai
from . import excel_auto_service as auto

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


def _auth_user_id(request):
    user = getattr(request, "user", None)
    return str(getattr(user, "id", "system") or "system")


def _read_files(request, field="file", multiple=False):
    files = request.FILES.getlist(field) if multiple else \
        ([request.FILES.get(field)] if request.FILES.get(field) else [])
    out = []
    for f in files:
        if f.size > MAX_UPLOAD_BYTES:
            raise ValueError(f"Ficheiro '{f.name}' excede o limite de 25 MB.")
        content = f.read()
        out.append((f.name, content))
    return out


def _transactions_dataframe(days: int = 365, vendor: str = None,
                            category: str = None, limit: int = 50000) -> "object":
    """DataFrame canônico das transações da base de dados."""
    import pandas as pd
    qs = Transaction.objects.all().order_by("-timestamp")
    if days and days > 0:
        since = timezone.now() - timezone.timedelta(days=days)
        qs = qs.filter(timestamp__gte=since)
    if vendor:
        qs = qs.filter(vendor__icontains=vendor)
    if category:
        qs = qs.filter(category__icontains=category)
    rows = list(qs.values("id", "transaction_id", "vendor", "amount", "currency",
                          "timestamp", "category", "user_id", "status")[:limit])
    df = pd.DataFrame(rows)
    if not df.empty:
        ts = pd.to_datetime(df["timestamp"])
        if getattr(ts.dt, "tz", None) is not None:
            # ORM devolve tz-aware (UTC); ficheiros chegam tz-naive — alinhar
            # para o cruzamento na reconciliação não rebentar com TypeError
            ts = ts.dt.tz_localize(None)
        df["timestamp"] = ts
    return df


# ---------------------------------------------------------------------------
# 1) PREVIEW
# ---------------------------------------------------------------------------

@api_view(["POST"])
@permission_classes([IsAuditorOrAdmin])
@parser_classes([MultiPartParser])
def excel_preview(request):
    """Devolve folhas, mapeamento sugerido, qualidade e amostra (dry-run)."""
    try:
        files = _read_files(request, "file")
        if not files:
            return Response({"error": "Envie um ficheiro (.xlsx, .xlsm, .xls ou .csv) no campo 'file'."}, status=400)
        name, content = files[0]
        frames = es.read_uploaded_file(content, name)
        sheet = request.data.get("sheet") or request.query_params.get("sheet")
        preview = es.preview_workbook(frames, sheet=str(sheet) if sheet else None)
        preview["file_name"] = name
        return Response(preview)
    except ValueError as e:
        return Response({"error": str(e)}, status=400)
    except Exception as e:
        logger.exception("excel_preview failed")
        return Response({"error": f"Falha ao ler o ficheiro: {e}"}, status=500)


# ---------------------------------------------------------------------------
# 2) IMPORT
# ---------------------------------------------------------------------------

@api_view(["POST"])
@permission_classes([IsAuditorOrAdmin])
@parser_classes([MultiPartParser])
def excel_import(request):
    """
    Importa transações a partir de Excel/CSV.
    Body (multipart): file, mapping (JSON string campo→coluna), sheet (opcional),
    mode: 'skip' (default) mantém IDs existentes, 'update' sobrescreve.
    """
    mode = (request.data.get("mode") or "skip").lower()
    try:
        files = _read_files(request, "file")
        if not files:
            return Response({"error": "Envie um ficheiro no campo 'file'."}, status=400)
        name, content = files[0]

        mapping_raw = request.data.get("mapping")
        if not mapping_raw:
            frames = es.read_uploaded_file(content, name)
            preview = es.preview_workbook(frames)
            mapping = preview["mapping"]
        else:
            mapping = json.loads(mapping_raw)

        frames = es.read_uploaded_file(content, name)
        sheet = request.data.get("sheet")
        sheet_name = str(sheet) if sheet else es.pick_best_sheet(frames)
        df = frames[sheet_name]

        rows, skipped = es.standardize_frame(df, mapping)
        if not rows:
            return Response({
                "error": "Nenhuma linha válida encontrada. Verifique o mapeamento.",
                "skipped": skipped[:50],
            }, status=400)

        user_id = _auth_user_id(request)
        created, duplicates, job_id = auto.import_standardized(
            rows, name, uploaded_by=user_id, sheet_name=sheet_name,
            mapping=mapping, skipped=skipped, mode=mode)
        return Response({
            "job_id": job_id,
            "file": name,
            "sheet": sheet_name,
            "imported": created,
            "duplicates_ignored": duplicates,
            "skipped": skipped[:50],
            "total_valid_rows": len(rows),
            "message": f"{created} transações importadas ({duplicates} duplicados ignorados, {len(skipped)} linhas inválidas).",
        })
    except json.JSONDecodeError:
        return Response({"error": "Campo 'mapping' deve ser JSON válido."}, status=400)
    except ValueError as e:
        return Response({"error": str(e)}, status=400)
    except Exception as e:
        logger.exception("excel_import failed")
        return Response({"error": f"Erro na importação: {e}"}, status=500)


# ---------------------------------------------------------------------------
# 2-b) EXCEL AUTO — análise, relatório, reconciliação, dossiê e exemplo (1 clique)
# ---------------------------------------------------------------------------

@api_view(["POST"])
@permission_classes([IsViewerOrAbove])
@parser_classes([MultiPartParser])
def excel_auto(request):
    """
    Larga o ficheiro e recebe TUDO numa resposta: folha+mapeamento detetados
    (com retry multi-folha), perfil, qualidade 0-100 com checks, risco,
    insights e próximos passos. Nada é importado — isso é um clique explícito.
    Body (multipart): file, threshold (opcional), sheet (opcional).
    """
    try:
        files = _read_files(request, "file")
        if not files:
            return Response({"error": "Envie o ficheiro no campo 'file' (ou clique em 'Testar com exemplo')."}, status=400)
        name, content = files[0]
        threshold = float(request.data.get("threshold", 10000) or 10000)
        result = auto.auto_analyze(content, name, threshold=threshold,
                                   sheet=request.data.get("sheet") or None)
        return Response(result)
    except ValueError as e:
        return Response({"error": str(e)}, status=400)
    except Exception as e:
        logger.exception("excel_auto failed")
        return Response({"error": f"Erro na análise automática: {e}"}, status=500)


@api_view(["POST"])
@permission_classes([IsViewerOrAbove])
@parser_classes([MultiPartParser])
def excel_auto_report(request):
    """Relatório Premium (.xlsx) da análise Auto do ficheiro carregado."""
    try:
        files = _read_files(request, "file")
        if not files:
            return Response({"error": "Envie o ficheiro no campo 'file'."}, status=400)
        name, content = files[0]
        threshold = float(request.data.get("threshold", 10000) or 10000)
        wb_bytes, fname = auto.build_auto_report(content, name, threshold=threshold)
        return HttpResponse(
            wb_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'})
    except ValueError as e:
        return Response({"error": str(e)}, status=400)
    except Exception as e:
        logger.exception("excel_auto_report failed")
        return Response({"error": f"Erro ao gerar o relatório: {e}"}, status=500)


@api_view(["GET"])
@permission_classes([IsViewerOrAbove])
def excel_sample(request):
    """Ficheiro de exemplo (com pequenos problemas plantados) para
    experimentar a análise Auto em 1 clique."""
    try:
        wb_bytes = auto.generate_sample_xlsx()
        return HttpResponse(
            wb_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="exemplo_movimentos.xlsx"'})
    except Exception as e:
        logger.exception("excel_sample failed")
        return Response({"error": f"Erro ao gerar o exemplo: {e}"}, status=500)


def _auto_reconcile_payload(request):
    """Lê file_a (+file_b ou use_db_b) e devolve os argumentos prontos."""
    files = _read_files(request, "file_a")
    if not files:
        return None, None, Response(
            {"error": "Envie o 1º ficheiro no campo 'file_a'."}, status=400)
    name_a, content_a = files[0]

    df_b = content_b = name_b = None
    if str(request.data.get("use_db_b", "")).lower() in ("1", "true", "yes"):
        df_b = _transactions_dataframe(
            days=int(request.data.get("days_b", 365) or 365))
        if df_b.empty:
            return None, None, Response(
                {"error": "A base de dados não tem transações nos últimos dias "
                          "indicados (days_b). Importe dados ou use um 2º ficheiro."},
                status=400)
    else:
        files_b = _read_files(request, "file_b")
        if not files_b:
            return None, None, Response(
                {"error": "Envie o 2º ficheiro no campo 'file_b' ou use use_db_b=1 "
                          "para reconciliar contra a base de dados."}, status=400)
        name_b, content_b = files_b[0]
    return (content_a, name_a, content_b, name_b, df_b), None, None


@api_view(["POST"])
@permission_classes([IsAuditorOrAdmin])
@parser_classes([MultiPartParser])
def excel_auto_reconcile(request):
    """Reconciliação Auto de 1 clique: folha+mapeamento automáticos nos 2 lados.
    Body (multipart): file_a, file_b OU use_db_b=1 (+days_b), sheet (opcional),
    amount_tol, date_tol_days (opcionais)."""
    try:
        args, _, err = _auto_reconcile_payload(request)
        if err:
            return err
        content_a, name_a, content_b, name_b, df_b = args
        result = auto.auto_reconcile(
            content_a, name_a, content_b=content_b, name_b=name_b, df_b=df_b,
            sheet=request.data.get("sheet") or None,
            amount_tol=float(request.data.get("amount_tol", 0.01) or 0.01),
            date_tol_days=int(request.data.get("date_tol_days", 3) or 3))
        return Response(result)
    except ValueError as e:
        return Response({"error": str(e)}, status=400)
    except Exception as e:
        logger.exception("excel_auto_reconcile failed")
        return Response({"error": f"Erro na reconciliação automática: {e}"}, status=500)


@api_view(["POST"])
@permission_classes([IsAuditorOrAdmin])
@parser_classes([MultiPartParser])
def excel_auto_reconcile_report(request):
    """Workbook premium da reconciliação Auto (Sumário + Conciliadas +
    Só em A + Só em B)."""
    try:
        args, _, err = _auto_reconcile_payload(request)
        if err:
            return err
        content_a, name_a, content_b, name_b, df_b = args
        wb_bytes, fname = auto.build_reconcile_report(
            content_a, name_a, content_b=content_b, name_b=name_b, df_b=df_b,
            amount_tol=float(request.data.get("amount_tol", 0.01) or 0.01),
            date_tol_days=int(request.data.get("date_tol_days", 3) or 3))
        return HttpResponse(
            wb_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'})
    except ValueError as e:
        return Response({"error": str(e)}, status=400)
    except Exception as e:
        logger.exception("excel_auto_reconcile_report failed")
        return Response({"error": f"Erro ao gerar o relatório de reconciliação: {e}"}, status=500)


@api_view(["POST"])
@permission_classes([IsAuditorOrAdmin])
@parser_classes([MultiPartParser])
def excel_auto_dossier(request):
    """Dossiê de Auditoria de 1 clique: analisa o ficheiro, importa as
    transações (clique explícito = este POST), gera o painel REA sobre a base
    e devolve UM workbook consolidado (Dossiê, Painel, Qualidade, Benford,
    Duplicados, Fraccionamento, Redondos, Dados).
    Body (multipart): file, threshold (opcional), mode (skip|update)."""
    try:
        files = _read_files(request, "file")
        if not files:
            return Response({"error": "Envie o ficheiro no campo 'file' (ou clique em 'Testar com exemplo')."}, status=400)
        name, content = files[0]
        threshold = float(request.data.get("threshold", 10000) or 10000)
        mode = (request.data.get("mode") or "skip").lower()
        user_id = _auth_user_id(request)
        role = getattr(getattr(request, "user", None), "role", "") or ""
        wb_bytes, fname, meta = auto.build_dossier(
            content, name, threshold=threshold,
            user_id=user_id, role=role, mode=mode)
        return HttpResponse(
            wb_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{fname}"',
                "X-Dossier-Imported": str(meta["imported"]),
                "X-Dossier-Duplicates": str(meta["duplicates"]),
                "X-Dossier-Skipped": str(meta["skipped"]),
            })
    except ValueError as e:
        return Response({"error": str(e)}, status=400)
    except Exception as e:
        logger.exception("excel_auto_dossier failed")
        return Response({"error": f"Erro ao gerar o dossiê: {e}"}, status=500)


# ---------------------------------------------------------------------------
# 3) ANÁLISES DE AUDITOR
# ---------------------------------------------------------------------------

@api_view(["GET", "POST"])
@permission_classes([IsViewerOrAbove])
def excel_analyze(request):
    """
    GET  → análises sobre a base (dias, vendor, category, threshold).
    POST → análises sobre ficheiro carregado (file + mapping opcional).
    """
    threshold = float(request.data.get("threshold", 10000) if request.method == "POST"
                      else request.query_params.get("threshold", 10000) or 10000)
    import pandas as pd

    try:
        if request.method == "POST":
            files = _read_files(request, "file")
            if not files:
                return Response({"error": "Envie um ficheiro no campo 'file'."}, status=400)
            name, content = files[0]
            frames = es.read_uploaded_file(content, name)
            sheet = request.data.get("sheet")
            df = frames[str(sheet)] if sheet else frames[es.pick_best_sheet(frames)]
            mapping = (json.loads(request.data["mapping"])
                       if request.data.get("mapping") else es.map_columns([str(c) for c in df.columns]))
            rows, _ = es.standardize_frame(df, mapping)
            if not rows:
                return Response({"error": "Nenhuma linha válida para análise."}, status=400)
            data = pd.DataFrame(rows)
            source = {"type": "file", "name": name}
        else:
            days = int(request.query_params.get("days", 365) or 365)
            vendor = request.query_params.get("vendor")
            category = request.query_params.get("category")
            data = _transactions_dataframe(days=days, vendor=vendor, category=category)
            if data.empty:
                return Response({"error": "Sem transações na base para o período/filtros escolhidos."}, status=404)
            source = {"type": "database", "days": days,
                      "filters": {"vendor": vendor, "category": category}}

        result = es.run_all_analyses(data, threshold=threshold)
        result["source"] = source
        return Response(result)
    except ValueError as e:
        return Response({"error": str(e)}, status=400)
    except Exception as e:
        logger.exception("excel_analyze failed")
        return Response({"error": f"Erro nas análises: {e}"}, status=500)


# ---------------------------------------------------------------------------
# 4) RECONCILIAÇÃO
# ---------------------------------------------------------------------------

@api_view(["POST"])
@permission_classes([IsAuditorOrAdmin])
@parser_classes([MultiPartParser])
def excel_reconcile(request):
    """
    Reconcilia 2 fontes: file_a (ex.: extrato bancário) vs file_b
    (ex.: contabilidade). Se 'use_db_b=1', o lado B são as transações da base.
    Parâmetros: amount_tol, date_tol_days, vendor_ratio.
    """
    import pandas as pd
    try:
        amount_tol = float(request.data.get("amount_tol", 0.01) or 0.01)
        date_tol = int(request.data.get("date_tol_days", 3) or 3)
        vendor_ratio = float(request.data.get("vendor_ratio", 0.75) or 0.75)

        files_a = _read_files(request, "file_a")
        if not files_a:
            return Response({"error": "Envie o 1º ficheiro no campo 'file_a'."}, status=400)
        name_a, content_a = files_a[0]

        frames_a = es.read_uploaded_file(content_a, name_a)
        df_a = frames_a[es.pick_best_sheet(frames_a)]
        map_a = (json.loads(request.data["map_a"]) if request.data.get("map_a")
                 else es.map_columns([str(c) for c in df_a.columns]))
        rows_a, _ = es.standardize_frame(df_a, map_a)
        if not rows_a:
            return Response({"error": "Ficheiro A sem linhas válidas."}, status=400)
        dfA = pd.DataFrame(rows_a)

        if str(request.data.get("use_db_b", "")).lower() in ("1", "true", "yes"):
            dfB = _transactions_dataframe(days=int(request.data.get("days_b", 365) or 365))
        else:
            files_b = _read_files(request, "file_b")
            if not files_b:
                return Response({"error": "Envie o 2º ficheiro no campo 'file_b' ou use use_db_b=1."}, status=400)
            name_b, content_b = files_b[0]
            frames_b = es.read_uploaded_file(content_b, name_b)
            df_b = frames_b[es.pick_best_sheet(frames_b)]
            map_b = (json.loads(request.data["map_b"]) if request.data.get("map_b")
                     else es.map_columns([str(c) for c in df_b.columns]))
            rows_b, _ = es.standardize_frame(df_b, map_b)
            if not rows_b:
                return Response({"error": "Ficheiro B sem linhas válidas."}, status=400)
            dfB = pd.DataFrame(rows_b)

        result = es.reconcile(dfA, dfB, amount_tol=amount_tol,
                              date_tol_days=date_tol, vendor_ratio=vendor_ratio)
        if "error" in result:
            return Response(result, status=400)
        return Response(result)
    except ValueError as e:
        return Response({"error": str(e)}, status=400)
    except Exception as e:
        logger.exception("excel_reconcile failed")
        return Response({"error": f"Erro na reconciliação: {e}"}, status=500)


# ---------------------------------------------------------------------------
# 5) EXPORT PREMIUM
# ---------------------------------------------------------------------------

def _download(purpose: str, wb_bytes: bytes):
    stamp = timezone.now().strftime("%Y%m%d_%H%M")
    return HttpResponse(
        wb_bytes,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{purpose}_{stamp}.xlsx"'},
    )


@api_view(["GET"])
@permission_classes([IsViewerOrAbove])
def excel_export(request):
    """
    Workbook premium com Sumário (KPIs + gráficos), Dados formatados e
    folhas de análise. type=transactions|alerts|cases|full.
    Aceita os mesmos filtros dos viewsets (vendor, category, status, days...).
    """
    import pandas as pd
    t = (request.query_params.get("type") or "transactions").lower()
    days = int(request.query_params.get("days", 365) or 365)
    since = timezone.now() - timezone.timedelta(days=days) if days > 0 else None

    try:
        if t in ("transactions", "full"):
            qs = Transaction.objects.order_by("-timestamp")
            if since:
                qs = qs.filter(timestamp__gte=since)
            if request.query_params.get("vendor"):
                qs = qs.filter(vendor__icontains=request.query_params["vendor"])
            if request.query_params.get("category"):
                qs = qs.filter(category__icontains=request.query_params["category"])
            if request.query_params.get("status"):
                qs = qs.filter(status=request.query_params["status"])
            df = pd.DataFrame(list(qs.values(
                "id", "transaction_id", "vendor", "amount", "currency",
                "timestamp", "category", "user_id", "status")[:50000]))
            if df.empty:
                return Response({"error": "Sem dados para exportar."}, status=404)
            df.rename(columns={
                "transaction_id": "ID Transação", "vendor": "Fornecedor",
                "amount": "Valor", "currency": "Moeda", "timestamp": "Data",
                "category": "Categoria", "user_id": "Usuário", "status": "Estado",
            }, inplace=True)

            analyses = None
            extra = []
            if t == "full":
                dfa = df.rename(columns={"Valor": "amount", "Fornecedor": "vendor",
                                         "Categoria": "category", "Usuário": "user_id",
                                         "Data": "timestamp"})
                analyses = es.run_all_analyses(dfa, threshold=float(
                    request.query_params.get("threshold", 10000) or 10000))
                if analyses["duplicates"].get("exact"):
                    extra.append({"name": "Duplicados",
                                  "df": pd.DataFrame(analyses["duplicates"]["exact"])})
                if analyses["splits"].get("groups"):
                    extra.append({"name": "Fraccionamento",
                                  "df": pd.DataFrame(analyses["splits"]["groups"])})
                if analyses["round_values"].get("count"):
                    extra.append({"name": "Valores Redondos",
                                  "df": pd.DataFrame(analyses["round_values"]["items"])})

            wb = es.build_premium_workbook(
                title=f"Relatório de Transações — Auditoria ({days}d)",
                df=df,
                kpis={
                    "Transações": int(len(df)),
                    "Valor Total": float(df["Valor"].sum()),
                    "Valor Médio": float(df["Valor"].mean()),
                    "Valor Máximo": float(df["Valor"].max()),
                    "Fornecedores": int(df["Fornecedor"].nunique()),
                    **({"Score de Risco": analyses["risk_score"]} if analyses else {}),
                },
                charts=es.aggregate_for_charts(df.rename(columns={
                    "Valor": "amount", "Fornecedor": "vendor",
                    "Categoria": "category", "Data": "timestamp"})),
                extra_sheets=extra,
            )
            return _download("Transacoes_Premium", wb)

        if t == "alerts":
            qs = Alert.objects.select_related("transaction").order_by("-timestamp")
            if since:
                qs = qs.filter(timestamp__gte=since)
            if request.query_params.get("severity"):
                qs = qs.filter(severity=request.query_params["severity"])
            if request.query_params.get("status"):
                qs = qs.filter(status=request.query_params["status"])
            rows = [{
                "ID": a.id,
                "Data": a.timestamp,
                "Tipo": a.alert_type,
                "Severidade": a.severity,
                "Estado": a.status,
                "Fornecedor": a.vendor,
                "Valor": float(a.amount or 0),
                "Materialidade": float(a.materiality or 0),
                "Descrição": a.description or "",
                "Transação": a.transaction.transaction_id if a.transaction else "",
            } for a in qs[:50000]]
            if not rows:
                return Response({"error": "Sem alertas para exportar."}, status=404)
            df = pd.DataFrame(rows)
            sev = df.groupby("Severidade").size().reset_index(name="N")
            types = (df.groupby("Tipo")["Valor"].sum()
                       .sort_values(ascending=False).head(10).reset_index())
            wb = es.build_premium_workbook(
                title="Relatório de Alertas de Risco",
                df=df,
                kpis={
                    "Alertas": int(len(df)),
                    "Críticos/Altos": int((df["Severidade"].isin(["Critical", "High"])).sum()),
                    "Em Aberto": int((df["Estado"].isin(["New", "Investigating"])).sum()),
                    "Valor Total": float(df["Valor"].sum()),
                },
                charts=[
                    {"type": "pie", "title": "Alertas por Severidade", "df": sev},
                    {"type": "bar", "title": "Top 10 Tipos por Valor", "df": types},
                ],
            )
            return _download("Alertas_Premium", wb)

        if t == "cases":
            qs = AuditCase.objects.order_by("-created_at")
            if since:
                qs = qs.filter(created_at__gte=since)
            rows = [{
                "ID": c.id, "Título": c.title, "Estado": c.status,
                "Prioridade": c.priority, "Responsável": c.assigned_to or "",
                "Criado": c.created_at, "Prazo": c.deadline,
                "Tipo de Achado": c.finding_type or "",
                "Risco Inerente": c.inherent_risk, "Risco Residual": c.residual_risk,
                "Plano de Ação": c.action_plan or "",
            } for c in qs[:20000]]
            if not rows:
                return Response({"error": "Sem casos para exportar."}, status=404)
            df = pd.DataFrame(rows)
            st = df.groupby("Estado").size().reset_index(name="N")
            pr = df.groupby("Prioridade").size().reset_index(name="N")
            wb = es.build_premium_workbook(
                title="Relatório de Casos de Auditoria",
                df=df,
                kpis={
                    "Casos": int(len(df)),
                    "Abertos": int((~df["Estado"].isin(["Resolved", "Closed"])).sum()),
                    "Atrasados": int(df["Prazo"].notna().sum() and 0) if "Prazo" in df else 0,
                },
                charts=[
                    {"type": "pie", "title": "Casos por Estado", "df": st},
                    {"type": "bar", "title": "Casos por Prioridade", "df": pr},
                ],
            )
            return _download("Casos_Premium", wb)

        return Response({"error": f"Tipo '{t}' inválido. Use transactions|alerts|cases|full."}, status=400)
    except Exception as e:
        logger.exception("excel_export failed")
        return Response({"error": f"Erro no export: {e}"}, status=500)


# ---------------------------------------------------------------------------
# 6) COPILOTO IA — assistente NL→Excel (pergunte ao ficheiro)
# ---------------------------------------------------------------------------

@api_view(["POST"])
@permission_classes([IsAuditorOrAdmin])
@parser_classes([MultiPartParser])
def excel_assistant(request):
    """
    Copiloto conversacional: file (+sheet/+mapping) + question →
    resposta com operações aplicadas, preview, fórmulas PT/EN e followups.
    history: JSON string [{role, content}] das últimas mensagens (opcional).
    """
    question = (request.data.get("question") or "").strip()
    if not question:
        return Response({"error": "Envie a pergunta no campo 'question'."}, status=400)
    if len(question) > 2000:
        return Response({"error": "Pergunta demasiado longa (máx. 2000 caracteres)."}, status=400)

    try:
        history = json.loads(request.data.get("history") or "[]")
        if not isinstance(history, list):
            history = []
    except json.JSONDecodeError:
        history = []

    try:
        use_db = str(request.data.get("use_db", "")).lower() in ("1", "true", "yes")
        if use_db:
            df = _transactions_dataframe(days=int(request.data.get("days", 365) or 365))
            if df.empty:
                return Response({"error": "Sem transações na base para o período escolhido."}, status=404)
            result = ai._chat_core(df, "(base de dados)", {}, question, history)
            result["source"] = {"type": "database"}
        else:
            files = _read_files(request, "file")
            if not files:
                return Response({"error": "Envie o ficheiro no campo 'file' (ou use use_db=1)."}, status=400)
            name, content = files[0]
            result = ai.chat(content, name, question,
                             sheet=request.data.get("sheet"),
                             mapping_json=request.data.get("mapping"),
                             history=history)
            result["source"] = {"type": "file", "name": name}
        return Response(result)
    except ValueError as e:
        return Response({"error": str(e)}, status=400)
    except Exception as e:
        logger.exception("excel_assistant failed")
        return Response({"error": f"Erro no Copiloto: {e}"}, status=500)


@api_view(["POST"])
@permission_classes([IsAuditorOrAdmin])
@parser_classes([MultiPartParser])
def excel_assistant_apply(request):
    """
    Aplica o plano confirmado do Copiloto e devolve o workbook .xlsx com
    Tabela 'tblDados', KPIs vivos e folha de Fórmulas.
    Body (multipart): file, plan (JSON list de operações), sheet, mapping.
    """
    try:
        files = _read_files(request, "file")
        if not files:
            return Response({"error": "Envie o ficheiro no campo 'file'."}, status=400)
        name, content = files[0]
        try:
            plan = json.loads(request.data.get("plan") or "[]")
        except json.JSONDecodeError:
            return Response({"error": "Campo 'plan' deve ser JSON (lista de operações)."}, status=400)
        if not isinstance(plan, list):
            return Response({"error": "Campo 'plan' deve ser uma lista de operações."}, status=400)

        wb_bytes, fname = ai.apply_and_build(
            content, name, plan,
            sheet=request.data.get("sheet"),
            mapping_json=request.data.get("mapping"),
            title=request.data.get("title") or None)
        return HttpResponse(
            wb_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'})
    except ValueError as e:
        return Response({"error": str(e)}, status=400)
    except Exception as e:
        logger.exception("excel_assistant_apply failed")
        return Response({"error": f"Erro ao gerar o workbook: {e}"}, status=500)

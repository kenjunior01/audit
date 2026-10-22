"""Endpoints do BI Studio — Power BI parity (REA Fase 4) + integração com o
Copiloto (Fase 5: tudo consultável em linguagem natural via tools existentes).

v2 (iteração REA): Relatórios guardados com cross-filtering, Q&A em linguagem
natural, inteligência temporal (séries/forecast/anomalias), novos visuais
(waterfall/funnel/scatter/KPI), alertas de medidas com notificações e
exportação Excel formatada.
"""
import json

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import (api_view, parser_classes,
                                       permission_classes, throttle_classes)
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from .auth import IsAuditorOrAdmin, IsViewerOrAbove
from .bi_export_service import export_visual_xlsx
from .bi_qa_service import ask_question
from .bi_service import (BIValidationError, DIMENSIONS, anomaly_view,
                         decompose_view, drillthrough_view, forecast_view,
                         funnel_view, group_measure, kpi_view, matrix_view,
                         pareto_view, run_measure, scatter_view, series_view,
                         what_if_view, waterfall_view,
                         _validate as validate_measure,
                         _validate_filter)
from .excel_service import read_uploaded_file, pick_best_sheet, standardize_frame
from .etl_service import apply_pipeline
from .models import (BIDashboard, BIMeasure, ETLPipeline, ExcelImportJob,
                     MeasureAlert, RLSRule, Transaction)
from .notification_views import _recipient  # mesma lógica de identidade
from .notifications_service import notify_user


def _uid(request):
    return _recipient(request)


def _role(request):
    if isinstance(request.auth, dict):
        return request.auth.get('role', '')
    return getattr(request.auth, 'role', '') if request.auth else ''


def _bi_error(e):
    return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------- medidas

@api_view(['GET', 'POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_measures(request):
    if request.method == 'GET':
        data = [{'id': m.id, 'name': m.name, 'description': m.description,
                 'expression': m.expression, 'format': m.format,
                 'created_by': m.created_by} for m in BIMeasure.objects.all()]
        return Response({'results': data, 'count': len(data)})
    # POST: criar medida (auditor/admin)
    if _role(request) not in ('auditor', 'admin'):
        return Response({'error': 'requer auditor/admin'}, status=status.HTTP_403_FORBIDDEN)
    data = request.data if isinstance(request.data, dict) else {}
    name = (data.get('name') or '').strip()
    expr = data.get('expression')
    if not name or not isinstance(expr, dict):
        return Response({'error': 'name e expression são obrigatórios'}, status=400)
    from .bi_service import _validate, BIValidationError as E
    try:
        _validate(expr)
    except E as e:
        return _bi_error(e)
    if BIMeasure.objects.filter(name=name).exists():
        return Response({'error': f"medida '{name}' já existe"}, status=409)
    m = BIMeasure.objects.create(name=name, description=data.get('description', ''),
                                 expression=expr, format=data.get('format', ''),
                                 created_by=_uid(request))
    return Response({'id': m.id, 'name': m.name}, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAuditorOrAdmin])
@throttle_classes([UserRateThrottle])
def bi_measure_delete(request, pk):
    try:
        m = BIMeasure.objects.get(pk=pk)
    except BIMeasure.DoesNotExist:
        return Response({'error': 'medida não encontrada'}, status=404)
    m.delete()
    return Response({'deleted': pk})


@api_view(['GET'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_dimensions(request):
    """Metadados para o construtor visual (campos, dimensões, agregações)."""
    from .bi_service import AGGS, DIMENSIONS, FIELDS
    return Response({'dimensions': sorted(DIMENSIONS), 'fields': sorted(FIELDS),
                     'aggregations': sorted(AGGS),
                     'ops': ['agg', 'calc', 'ratio', 'diff', 'add', 'mul',
                             'yoy', 'mom', 'pct_of_total', 'running_total', 'const']})


# ---------------------------------------------------------------- visuais

@api_view(['POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_evaluate(request):
    data = request.data if isinstance(request.data, dict) else {}
    try:
        value, nrows = run_measure(data.get('measure'), data.get('filters'),
                                   user_id=_uid(request), role=_role(request))
        return Response({'value': value, 'rows': nrows})
    except BIValidationError as e:
        return _bi_error(e)


@api_view(['POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_group(request):
    data = request.data if isinstance(request.data, dict) else {}
    try:
        return Response(group_measure(
            data.get('measure'), data.get('dimension'),
            top_n=data.get('top_n', 20), filters=data.get('filters'),
            user_id=_uid(request), role=_role(request),
            mode=data.get('mode', 'plain')))
    except BIValidationError as e:
        return _bi_error(e)


@api_view(['POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_matrix(request):
    data = request.data if isinstance(request.data, dict) else {}
    try:
        return Response(matrix_view(
            data.get('measure'), data.get('rows'), data.get('cols'),
            filters=data.get('filters'), user_id=_uid(request),
            role=_role(request)))
    except BIValidationError as e:
        return _bi_error(e)


@api_view(['POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_pareto(request):
    data = request.data if isinstance(request.data, dict) else {}
    try:
        return Response(pareto_view(
            data.get('measure'), data.get('dimension'), filters=data.get('filters'),
            user_id=_uid(request), role=_role(request)))
    except BIValidationError as e:
        return _bi_error(e)


@api_view(['POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_decompose(request):
    data = request.data if isinstance(request.data, dict) else {}
    try:
        return Response(decompose_view(
            data.get('measure'), data.get('dimensions'),
            filters=data.get('filters'), user_id=_uid(request),
            role=_role(request)))
    except BIValidationError as e:
        return _bi_error(e)


@api_view(['POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_whatif(request):
    data = request.data if isinstance(request.data, dict) else {}
    try:
        return Response(what_if_view(
            data.get('measure'), data.get('adjustment_pct', 0),
            filters=data.get('filters'), user_id=_uid(request),
            role=_role(request)))
    except BIValidationError as e:
        return _bi_error(e)


@api_view(['POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_drillthrough(request):
    data = request.data if isinstance(request.data, dict) else {}
    return Response(drillthrough_view(
        data.get('filters'), dimension=data.get('dimension'),
        value=data.get('value'), user_id=_uid(request), role=_role(request),
        limit=data.get('limit', 50)))


# ---------------------------------------------------------------- pipelines

@api_view(['GET', 'POST'])
@permission_classes([IsAuditorOrAdmin])
@throttle_classes([UserRateThrottle])
def bi_pipelines(request):
    if request.method == 'GET':
        data = [{'id': p.id, 'name': p.name, 'description': p.description,
                 'steps': p.steps, 'run_count': p.run_count,
                 'last_run_at': p.last_run_at, 'last_run_rows': p.last_run_rows,
                 'last_run_imported': p.last_run_imported}
                for p in ETLPipeline.objects.all()]
        return Response({'results': data, 'count': len(data)})
    d = request.data if isinstance(request.data, dict) else {}
    name = (d.get('name') or '').strip()
    steps = d.get('steps') or []
    if not name:
        return Response({'error': 'name é obrigatório'}, status=400)
    if not isinstance(steps, list) or len(steps) > 50:
        return Response({'error': 'steps deve ser lista ≤ 50'}, status=400)
    if ETLPipeline.objects.filter(name=name).exists():
        return Response({'error': f"pipeline '{name}' já existe"}, status=409)
    p = ETLPipeline.objects.create(name=name, description=d.get('description', ''),
                                   steps=steps, created_by=_uid(request))
    return Response({'id': p.id, 'name': p.name}, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAuditorOrAdmin])
@throttle_classes([UserRateThrottle])
def bi_pipeline_delete(request, pk):
    try:
        p = ETLPipeline.objects.get(pk=pk)
    except ETLPipeline.DoesNotExist:
        return Response({'error': 'pipeline não encontrado'}, status=404)
    p.delete()
    return Response({'deleted': pk})


@api_view(['POST'])
@permission_classes([IsAuditorOrAdmin])
@throttle_classes([UserRateThrottle])
@parser_classes([MultiPartParser, JSONParser])
def bi_pipeline_run(request, pk):
    """Executa o pipeline: multipart file (xlsx/csv) + opcional import=true."""
    try:
        p = ETLPipeline.objects.get(pk=pk)
    except ETLPipeline.DoesNotExist:
        return Response({'error': 'pipeline não encontrado'}, status=404)

    files = request.FILES
    if 'file' not in files:
        return Response({'error': "Envie um ficheiro no campo 'file'."}, status=400)
    name = files['file'].name
    content = files['file'].read()

    try:
        frames = read_uploaded_file(content, name)
    except Exception as e:
        return Response({'error': f'falha ao ler ficheiro: {e}'}, status=400)
    sheet = pick_best_sheet(frames)
    df = frames[sheet]

    df_out, log, ok_steps = apply_pipeline(df, p.steps)

    imported = 0
    want_import = str(request.data.get('import',
                                       request.query_params.get('import', ''))).lower() \
        in ('1', 'true', 'yes')
    if want_import and not df_out.empty:
        mapping = {c: c for c in ('transaction_id', 'vendor', 'amount', 'timestamp',
                                  'category', 'status', 'user_id', 'currency')
                   if c in df_out.columns}
        if 'transaction_id' in mapping and 'amount' in mapping and 'timestamp' in mapping:
            rows, skipped = standardize_frame(df_out, mapping)
            uid = _uid(request)
            existing = set(Transaction.objects.filter(
                transaction_id__in=[r['transaction_id'] for r in rows]
            ).values_list('transaction_id', flat=True))
            to_create = [Transaction(**r) for r in rows if r['transaction_id'] not in existing]
            imported = len(Transaction.objects.bulk_create(to_create, batch_size=500))
            ExcelImportJob.objects.create(
                file_name=f"[pipeline:{p.name}] {name}", uploaded_by=uid,
                rows_imported=imported, rows_skipped=len(skipped) + (len(rows) - len(to_create)),
                mapping=mapping, status='Completed', sheet=sheet)
        else:
            log.append({'step': '-', 'op': 'import', 'note': 'colunas canónicas ausentes '
                        '(transaction_id, amount, timestamp) — importação ignorada',
                        'rows_after': len(df_out)})

    p.run_count += 1
    p.last_run_at = timezone.now()
    p.last_run_rows = len(df_out)
    p.last_run_imported = imported
    p.save(update_fields=['run_count', 'last_run_at', 'last_run_rows', 'last_run_imported'])

    preview_cols = [c for c in df_out.columns[:12]]
    preview = df_out[preview_cols].head(15).copy()
    for c in preview.columns:
        if preview[c].dtype == object:
            preview[c] = preview[c].astype(str).str.slice(0, 40)
    return Response({
        'pipeline': p.name, 'source_sheet': sheet, 'rows_in': log[0]['rows_after'] if log else len(df_out),
        'rows_out': len(df_out), 'steps_ok': ok_steps, 'steps_total': len(p.steps),
        'imported': imported, 'log': log,
        'preview': {'columns': list(preview.columns), 'rows': preview.to_dict('records')},
    })


# ---------------------------------------------------------------- RLS

@api_view(['GET', 'POST'])
@permission_classes([IsAuditorOrAdmin])
@throttle_classes([UserRateThrottle])
def bi_rls(request):
    if request.method == 'GET':
        data = [{'id': r.id, 'name': r.name, 'user_id': r.user_id, 'role': r.role,
                 'dimension': r.dimension, 'allowed_values': r.allowed_values,
                 'active': r.active} for r in RLSRule.objects.all()]
        return Response({'results': data, 'count': len(data)})
    d = request.data if isinstance(request.data, dict) else {}
    dimension = d.get('dimension')
    if dimension not in ('vendor', 'category', 'status', 'currency', 'user_id'):
        return Response({'error': 'dimensão inválida'}, status=400)
    values = d.get('allowed_values') or []
    if not isinstance(values, list) or not values:
        return Response({'error': 'allowed_values deve ser lista não vazia'}, status=400)
    if not d.get('user_id') and not d.get('role'):
        return Response({'error': 'indique user_id ou role'}, status=400)
    r = RLSRule.objects.create(
        name=d.get('name') or f"RLS {dimension}",
        user_id=d.get('user_id', ''), role=d.get('role', ''),
        dimension=dimension, allowed_values=values,
        active=bool(d.get('active', True)), created_by=_uid(request))
    return Response({'id': r.id, 'name': r.name}, status=status.HTTP_201_CREATED)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuditorOrAdmin])
@throttle_classes([UserRateThrottle])
def bi_rls_detail(request, pk):
    try:
        r = RLSRule.objects.get(pk=pk)
    except RLSRule.DoesNotExist:
        return Response({'error': 'regra não encontrada'}, status=404)
    if request.method == 'DELETE':
        r.delete()
        return Response({'deleted': pk})
    d = request.data if isinstance(request.data, dict) else {}
    if 'active' in d:
        r.active = bool(d['active'])
    if 'allowed_values' in d and isinstance(d['allowed_values'], list):
        r.allowed_values = d['allowed_values']
    r.save(update_fields=['active', 'allowed_values'])
    return Response({'id': r.id, 'active': r.active,
                     'allowed_values': r.allowed_values})


# ---------------------------------------------------------------- visuais v2

VISUAL_KINDS = {'bar', 'line', 'pie', 'series', 'pareto', 'matrix', 'decompose',
                'whatif', 'waterfall', 'funnel', 'scatter', 'kpi', 'anomaly',
                'forecast'}


def _run_visual(kind, spec, filters, user_id, role):
    """Dispatcher: kind + spec → dados do visual (usado no explorador e nos
    relatórios guardados para garantir comportamento idêntico)."""
    measure = spec.get('measure')
    dimension = spec.get('dimension')
    kw = {'filters': filters, 'user_id': user_id, 'role': role}
    if kind in ('bar', 'pie', 'line'):
        return group_measure(measure, dimension, top_n=spec.get('top_n', 20),
                             mode=spec.get('mode', 'plain'), **kw)
    if kind == 'series':
        return series_view(measure, granularity=spec.get('granularity', 'month'),
                           window=spec.get('window', 3), **kw)
    if kind == 'pareto':
        return pareto_view(measure, dimension, **kw)
    if kind == 'matrix':
        return matrix_view(measure, spec.get('rows', dimension),
                           spec.get('cols', 'month'), **kw)
    if kind == 'decompose':
        return decompose_view(measure, spec.get('dimensions') or [dimension],
                              **kw)
    if kind == 'whatif':
        return what_if_view(measure, spec.get('adjustment_pct', 0), **kw)
    if kind == 'waterfall':
        return waterfall_view(measure, dimension, **kw)
    if kind == 'funnel':
        return funnel_view(measure, dimension, **kw)
    if kind == 'scatter':
        return scatter_view(spec.get('measure_x') or measure,
                            spec.get('measure_y') or measure, dimension, **kw)
    if kind == 'kpi':
        return kpi_view(measure, target=spec.get('target'), **kw)
    if kind == 'anomaly':
        return anomaly_view(measure, granularity=spec.get('granularity', 'month'),
                            z_threshold=spec.get('z_threshold', 2.5), **kw)
    if kind == 'forecast':
        return forecast_view(measure, granularity=spec.get('granularity', 'month'),
                             periods=spec.get('periods', 3), **kw)
    raise BIValidationError(f"tipo de visual desconhecido: {kind}")


def _validate_visual_spec(v):
    if not isinstance(v, dict) or v.get('kind') not in VISUAL_KINDS:
        raise BIValidationError(f"visual: 'kind' inválido ({v.get('kind') if isinstance(v, dict) else v})")
    validate_measure(v.get('measure'))
    if v.get('kind') == 'scatter' and v.get('measure_y'):
        validate_measure(v['measure_y'])
    for f in v.get('filters', []) or []:
        _validate_filter(f)
    if v.get('dimension') and v['dimension'] not in DIMENSIONS:
        raise BIValidationError(f"visual: dimensão inválida {v['dimension']}")


@api_view(['POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_visual(request):
    """Executa um visual genérico pelo dispatcher (bar/series/waterfall/...)."""
    data = request.data if isinstance(request.data, dict) else {}
    try:
        _validate_visual_spec(data)
        payload = _run_visual(data['kind'], data, data.get('filters'),
                              _uid(request), _role(request))
        return Response({'kind': data['kind'], 'data': payload})
    except BIValidationError as e:
        return _bi_error(e)


@api_view(['POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_series(request):
    data = request.data if isinstance(request.data, dict) else {}
    try:
        return Response(series_view(
            data.get('measure'), granularity=data.get('granularity', 'month'),
            window=data.get('window', 3), filters=data.get('filters'),
            user_id=_uid(request), role=_role(request)))
    except BIValidationError as e:
        return _bi_error(e)


@api_view(['POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_forecast(request):
    data = request.data if isinstance(request.data, dict) else {}
    try:
        return Response(forecast_view(
            data.get('measure'), granularity=data.get('granularity', 'month'),
            periods=data.get('periods', 3), filters=data.get('filters'),
            user_id=_uid(request), role=_role(request)))
    except BIValidationError as e:
        return _bi_error(e)


@api_view(['POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_anomaly(request):
    data = request.data if isinstance(request.data, dict) else {}
    try:
        return Response(anomaly_view(
            data.get('measure'), granularity=data.get('granularity', 'month'),
            z_threshold=data.get('z_threshold', 2.5), filters=data.get('filters'),
            user_id=_uid(request), role=_role(request)))
    except BIValidationError as e:
        return _bi_error(e)


@api_view(['POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_waterfall(request):
    data = request.data if isinstance(request.data, dict) else {}
    try:
        return Response(waterfall_view(
            data.get('measure'), data.get('dimension'), filters=data.get('filters'),
            user_id=_uid(request), role=_role(request)))
    except BIValidationError as e:
        return _bi_error(e)


@api_view(['POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_funnel(request):
    data = request.data if isinstance(request.data, dict) else {}
    try:
        return Response(funnel_view(
            data.get('measure'), data.get('dimension'), filters=data.get('filters'),
            user_id=_uid(request), role=_role(request)))
    except BIValidationError as e:
        return _bi_error(e)


@api_view(['POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_scatter(request):
    data = request.data if isinstance(request.data, dict) else {}
    try:
        return Response(scatter_view(
            data.get('measure_x'), data.get('measure_y'), data.get('dimension'),
            filters=data.get('filters'), user_id=_uid(request),
            role=_role(request)))
    except BIValidationError as e:
        return _bi_error(e)


@api_view(['POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_kpi(request):
    data = request.data if isinstance(request.data, dict) else {}
    try:
        return Response(kpi_view(
            data.get('measure'), target=data.get('target'),
            filters=data.get('filters'), user_id=_uid(request),
            role=_role(request)))
    except BIValidationError as e:
        return _bi_error(e)


# ---------------------------------------------------------------- relatórios

@api_view(['GET', 'POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_dashboards(request):
    if request.method == 'GET':
        data = [{'id': d.id, 'name': d.name, 'description': d.description,
                 'config': d.config, 'created_by': d.created_by,
                 'updated_at': d.updated_at} for d in BIDashboard.objects.all()]
        return Response({'results': data, 'count': len(data)})
    if _role(request) not in ('auditor', 'admin'):
        return Response({'error': 'requer auditor/admin'}, status=status.HTTP_403_FORBIDDEN)
    d = request.data if isinstance(request.data, dict) else {}
    name = (d.get('name') or '').strip()
    config = d.get('config')
    if not name:
        return Response({'error': 'name é obrigatório'}, status=400)
    if not isinstance(config, dict):
        return Response({'error': 'config deve ser objeto'}, status=400)
    visuals = config.get('visuals') or []
    if not isinstance(visuals, list) or not (1 <= len(visuals) <= 12):
        return Response({'error': 'config.visuals: lista de 1..12 visuais'}, status=400)
    try:
        for v in visuals:
            _validate_visual_spec(v)
        for s in config.get('slicers', []) or []:
            _validate_filter(s)
    except BIValidationError as e:
        return _bi_error(e)
    if BIDashboard.objects.filter(name=name).exists():
        return Response({'error': f"relatório '{name}' já existe"}, status=409)
    obj = BIDashboard.objects.create(name=name,
                                     description=d.get('description', ''),
                                     config=config, created_by=_uid(request))
    return Response({'id': obj.id, 'name': obj.name}, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_dashboard_detail(request, pk):
    try:
        obj = BIDashboard.objects.get(pk=pk)
    except BIDashboard.DoesNotExist:
        return Response({'error': 'relatório não encontrado'}, status=404)
    if request.method == 'DELETE':
        if _role(request) not in ('auditor', 'admin'):
            return Response({'error': 'requer auditor/admin'}, status=status.HTTP_403_FORBIDDEN)
        obj.delete()
        return Response({'deleted': pk})
    if request.method == 'GET':
        return Response({'id': obj.id, 'name': obj.name,
                         'description': obj.description, 'config': obj.config,
                         'created_by': obj.created_by, 'updated_at': obj.updated_at})
    if _role(request) not in ('auditor', 'admin'):
        return Response({'error': 'requer auditor/admin'}, status=status.HTTP_403_FORBIDDEN)
    d = request.data if isinstance(request.data, dict) else {}
    config = d.get('config')
    if not isinstance(config, dict):
        return Response({'error': 'config deve ser objeto'}, status=400)
    try:
        for v in config.get('visuals') or []:
            _validate_visual_spec(v)
    except BIValidationError as e:
        return _bi_error(e)
    obj.config = config
    if d.get('description') is not None:
        obj.description = d['description']
    obj.save(update_fields=['config', 'description', 'updated_at'])
    return Response({'id': obj.id, 'name': obj.name, 'updated_at': obj.updated_at})


@api_view(['POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_dashboard_run(request, pk):
    """Executa o relatório completo numa só chamada: cada visual é avaliado
    com slicers partilhados + cross-filters do pedido (estilo interação do
    Power BI). Erros por visual não abortam o relatório."""
    try:
        obj = BIDashboard.objects.get(pk=pk)
    except BIDashboard.DoesNotExist:
        return Response({'error': 'relatório não encontrado'}, status=404)
    d = request.data if isinstance(request.data, dict) else {}
    cross = d.get('cross_filters') or []
    if not isinstance(cross, list):
        cross = []
    slicers = list((obj.config or {}).get('slicers') or [])
    uid, role = _uid(request), _role(request)
    out = []
    for i, v in enumerate((obj.config or {}).get('visuals') or []):
        vid = v.get('id') or f"v{i + 1}"
        try:
            _validate_visual_spec(v)
            data = _run_visual(v['kind'], v,
                               slicers + list(v.get('filters') or []) + cross,
                               uid, role)
            out.append({'id': vid, 'kind': v['kind'],
                        'title': v.get('title') or vid, 'ok': True, 'data': data})
        except BIValidationError as e:
            out.append({'id': vid, 'kind': v.get('kind', '?'),
                        'title': v.get('title') or vid, 'ok': False,
                        'error': str(e)})
        except Exception as e:  # um visual nunca derruba o relatório
            out.append({'id': vid, 'kind': v.get('kind', '?'),
                        'title': v.get('title') or vid, 'ok': False,
                        'error': f"erro: {e}"})
    return Response({'dashboard': obj.name, 'slicers': slicers,
                     'cross_filters': cross, 'visuals': out})


# ---------------------------------------------------------------- Q&A

@api_view(['POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_qa(request):
    """Pergunte aos dados: PT/EN → especificação executável + visual."""
    d = request.data if isinstance(request.data, dict) else {}
    try:
        return Response(ask_question(d.get('question') or '',
                                     user_id=_uid(request), role=_role(request)))
    except BIValidationError as e:
        return _bi_error(e)


# ---------------------------------------------------------------- exportação

@api_view(['POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_export(request):
    """Exporta o payload de um visual para Excel formatado (.xlsx)."""
    d = request.data if isinstance(request.data, dict) else {}
    kind = d.get('kind') or 'group'
    data = d.get('data')
    if not isinstance(data, dict):
        return Response({'error': "envie 'kind' e 'data' (payload do visual)"}, status=400)
    # limite de segurança: 5.000 linhas por exportação
    if isinstance(data.get('rows'), list) and len(data['rows']) > 5000:
        data = {**data, 'rows': data['rows'][:5000]}
    try:
        content = export_visual_xlsx(kind, data,
                                     title=d.get('title') or 'Visual BI',
                                     subtitle=d.get('subtitle') or '')
    except Exception as e:
        return Response({'error': f'falha ao gerar Excel: {e}'}, status=400)
    fname = (d.get('filename') or f"bi-{kind}").strip().replace(' ', '-')[:80]
    resp = HttpResponse(content,
                        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = f'attachment; filename="{fname}.xlsx"'
    return resp


# ---------------------------------------------------------------- alertas

@api_view(['GET', 'POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def bi_alerts(request):
    if request.method == 'GET':
        data = [{'id': a.id, 'name': a.name, 'measure': a.measure,
                 'filters': a.filters, 'comparator': a.comparator,
                 'threshold': a.threshold, 'active': a.active,
                 'last_value': a.last_value, 'last_state': a.last_state,
                 'last_checked_at': a.last_checked_at,
                 'breach_count': a.breach_count} for a in MeasureAlert.objects.all()]
        return Response({'results': data, 'count': len(data)})
    if _role(request) not in ('auditor', 'admin'):
        return Response({'error': 'requer auditor/admin'}, status=status.HTTP_403_FORBIDDEN)
    d = request.data if isinstance(request.data, dict) else {}
    name = (d.get('name') or '').strip()
    if not name or not isinstance(d.get('measure'), dict):
        return Response({'error': 'name e measure são obrigatórios'}, status=400)
    if d.get('comparator') not in ('gt', 'lt', 'gte', 'lte'):
        return Response({'error': 'comparator: gt|lt|gte|lte'}, status=400)
    try:
        validate_measure(d['measure'])
        for f in d.get('filters', []) or []:
            _validate_filter(f)
    except BIValidationError as e:
        return _bi_error(e)
    try:
        threshold = float(d.get('threshold', 0))
    except (TypeError, ValueError):
        return Response({'error': 'threshold numérico obrigatório'}, status=400)
    if MeasureAlert.objects.filter(name=name).exists():
        return Response({'error': f"alerta '{name}' já existe"}, status=409)
    a = MeasureAlert.objects.create(
        name=name, measure=d['measure'], filters=d.get('filters') or [],
        comparator=d['comparator'], threshold=threshold,
        active=bool(d.get('active', True)), created_by=_uid(request))
    return Response({'id': a.id, 'name': a.name}, status=status.HTTP_201_CREATED)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuditorOrAdmin])
@throttle_classes([UserRateThrottle])
def bi_alert_detail(request, pk):
    try:
        a = MeasureAlert.objects.get(pk=pk)
    except MeasureAlert.DoesNotExist:
        return Response({'error': 'alerta não encontrado'}, status=404)
    if request.method == 'DELETE':
        a.delete()
        return Response({'deleted': pk})
    d = request.data if isinstance(request.data, dict) else {}
    if 'active' in d:
        a.active = bool(d['active'])
    if 'threshold' in d:
        try:
            a.threshold = float(d['threshold'])
        except (TypeError, ValueError):
            return _bi_error(BIValidationError('threshold numérico obrigatório'))
    if 'comparator' in d and d['comparator'] in ('gt', 'lt', 'gte', 'lte'):
        a.comparator = d['comparator']
    a.save(update_fields=['active', 'threshold', 'comparator'])
    return Response({'id': a.id, 'active': a.active, 'threshold': a.threshold,
                     'comparator': a.comparator})


_CMP_FUNCS = {
    'gt': lambda v, t: v > t,
    'lt': lambda v, t: v < t,
    'gte': lambda v, t: v >= t,
    'lte': lambda v, t: v <= t,
}


def evaluate_measure_alert(a):
    """Avalia um alerta: devolve (state, value, notified:bool)."""
    try:
        value, _ = run_measure(a.measure, a.filters)
    except Exception as e:
        a.last_state, a.last_checked_at = 'error', timezone.now()
        a.save(update_fields=['last_state', 'last_checked_at'])
        return 'error', None, False
    breached = _CMP_FUNCS[a.comparator](value, a.threshold)
    prev_state = a.last_state
    a.last_value, a.last_checked_at = value, timezone.now()
    a.last_state = 'breach' if breached else 'ok'
    if breached:
        a.breach_count = (a.breach_count or 0) + 1
    a.save(update_fields=['last_value', 'last_state', 'last_checked_at',
                          'breach_count'])
    notified = False
    if breached and prev_state != 'breach':  # transição ok→breach notifica
        sev = 'critical' if a.threshold and abs(value) >= abs(a.threshold) * 1.25 \
            else 'warn'
        cmp_pt = a.get_comparator_display()
        notified = notify_user(
            a.created_by, kind='bi.alert',
            title=f"Alerta BI: {a.name}",
            body=f"Medida em {value:,.2f} — {cmp_pt} {a.threshold:,.2f}.",
            route='/bi', severity=sev,
            meta={'alert_id': a.id, 'value': value, 'threshold': a.threshold},
            dedupe_minutes=0) is not None
    return a.last_state, value, notified


@api_view(['POST'])
@permission_classes([IsAuditorOrAdmin])
@throttle_classes([UserRateThrottle])
def bi_alerts_run(request):
    """Avalia todos os alertas ativos (agendável via cron/management command)."""
    results = []
    for a in MeasureAlert.objects.filter(active=True):
        state, value, notified = evaluate_measure_alert(a)
        results.append({'id': a.id, 'name': a.name, 'state': state,
                        'value': value, 'notified': notified})
    return Response({'evaluated': len(results), 'results': results})

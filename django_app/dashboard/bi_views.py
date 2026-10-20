"""Endpoints do BI Studio — Power BI parity (REA Fase 4) + integração com o
Copiloto (Fase 5: tudo consultável em linguagem natural via tools existentes)."""
import json

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import (api_view, parser_classes,
                                       permission_classes, throttle_classes)
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from .auth import IsAuditorOrAdmin, IsViewerOrAbove
from .bi_service import (BIValidationError, decompose_view, drillthrough_view,
                         group_measure, matrix_view, pareto_view,
                         run_measure, what_if_view)
from .excel_service import read_uploaded_file, pick_best_sheet, standardize_frame
from .etl_service import apply_pipeline
from .models import BIMeasure, ETLPipeline, ExcelImportJob, RLSRule, Transaction
from .notification_views import _recipient  # mesma lógica de identidade


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

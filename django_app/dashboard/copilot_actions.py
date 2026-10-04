"""
Ações executáveis do Copiloto Global — modelo de suporte que ACTUA
(sempre com confirmação humana no frontend e whitelist fechada).

Fluxo:
1. O utilizador pede "resolve o alerta 42" no chat;
2. detect_action() reconhece a intenção + ID explícito e o copiloto
   DEVOLVE uma proposta (nunca executa diretamente);
3. O utilizador confirma no cartão → POST /ai/copilot/act;
4. execute_action() valida ação, parâmetros e papel (role), executa e
   escreve no ImmutableAuditLog (trilha imutável com hash chain).

Whitelist fechada: só existe aqui. Qualquer ação nova tem de ser
adicionada explicitamente com os seus papéis autorizados.
"""
import logging
import re

from django.utils import timezone

from .models import Alert, AuditCase, ImmutableAuditLog

logger = logging.getLogger(__name__)

ALERT_STATUSES = ["New", "Investigating", "Resolved", "False Positive"]
CASE_STATUSES = ["New", "In Progress", "Resolved", "Closed"]
CASE_PRIORITIES = ["Low", "Medium", "High", "Critical"]

# papéis autorizados por ação (viewer nunca executa ações)
ACTIONS = {
    "set_alert_status": {
        "params": ["alert_id", "status"],
        "roles": {"admin", "auditor"},
        "choices": {"status": ALERT_STATUSES},
    },
    "set_case_status": {
        "params": ["case_id", "status"],
        "roles": {"admin", "auditor"},
        "choices": {"status": CASE_STATUSES},
    },
    "set_case_priority": {
        "params": ["case_id", "priority"],
        "roles": {"admin", "auditor"},
        "choices": {"priority": CASE_PRIORITIES},
    },
}

_STATUS_PT = {"New": "Novo", "Investigating": "Em investigação",
              "Resolved": "Resolvido", "False Positive": "Falso positivo",
              "In Progress": "Em progresso", "Closed": "Fechado"}
_PRIORITY_PT = {"Low": "Baixa", "Medium": "Média", "High": "Alta",
                "Critical": "Crítica"}

# --- deteção de intenção de ação (PT/EN, exige ID explícito) ---------------
_RE_ALERT = re.compile(r"\b(?:alertas?|alert)\s*#?\s*(\d{1,9})\b", re.I)
_RE_CASE = re.compile(r"\b(?:casos?|case)\s*#?\s*(\d{1,9})\b", re.I)
_RE_RESOLVE = re.compile(r"\bresolver?|marc\w* como resolvid|mark\w*\s+(?:as\s+)?resolved\b", re.I)
_RE_FP = re.compile(r"falso\s+positivo|false\s+positive", re.I)
_RE_INVESTIGATE = re.compile(r"\binvestiga|em\s+investiga|investigating\b", re.I)
_RE_CLOSE = re.compile(r"\bfech\w+|encerr\w+|\bclose[ds]?\b", re.I)
_RE_INPROGRESS = re.compile(r"em\s+(?:progresso|andamento)|in\s+progress", re.I)
_RE_PRIORITY = re.compile(r"prioridade\s+(cr[íi]tica|alta|m[ée]dia|baixa)|priority\s+(critical|high|medium|low)", re.I)
_PRIO_MAP = {"crítica": "Critical", "critica": "Critical", "critical": "Critical",
             "alta": "High", "high": "High", "média": "Medium", "media": "Medium",
             "medium": "Medium", "baixa": "Low", "low": "Low"}


def detect_action(question: str):
    """Reconhece uma intenção de ação com ID explícito.
    Devolve {action, params, label, detail} ou None (nada proposto).
    Ação NUNCA é executada aqui — só proposta para confirmação."""
    q = question or ""
    m_alert = _RE_ALERT.search(q)
    m_case = _RE_CASE.search(q)

    if m_alert:
        alert_id = int(m_alert.group(1))
        if _RE_FP.search(q):
            status = "False Positive"
        elif _RE_RESOLVE.search(q):
            status = "Resolved"
        elif _RE_INVESTIGATE.search(q):
            status = "Investigating"
        else:
            return None
        return {"action": "set_alert_status",
                "params": {"alert_id": alert_id, "status": status},
                "label": f"Marcar alerta {alert_id} como {_STATUS_PT[status]}",
                "detail": "A alteração fica registada no log de auditoria "
                          "imutável. Requer confirmação."}

    if m_case:
        case_id = int(m_case.group(1))
        if _RE_PRIORITY.search(q):
            word = (_RE_PRIORITY.search(q).group(1)
                    or _RE_PRIORITY.search(q).group(2) or "").lower()
            prio = _PRIO_MAP.get(word)
            if not prio:
                return None
            return {"action": "set_case_priority",
                    "params": {"case_id": case_id, "priority": prio},
                    "label": f"Definir prioridade do caso {case_id} "
                             f"como {_PRIORITY_PT[prio]}",
                    "detail": "A alteração fica registada no log de "
                              "auditoria imutável. Requer confirmação."}
        if _RE_CLOSE.search(q):
            status = "Closed"
        elif _RE_RESOLVE.search(q):
            status = "Resolved"
        elif _RE_INPROGRESS.search(q) or _RE_INVESTIGATE.search(q):
            status = "In Progress"
        else:
            return None
        return {"action": "set_case_status",
                "params": {"case_id": case_id, "status": status},
                "label": f"Marcar caso {case_id} como {_STATUS_PT[status]}",
                "detail": "A alteração fica registada no log de auditoria "
                          "imutável. Requer confirmação."}
    return None


def execute_action(action: str, params: dict, username: str = "",
                   role: str = "") -> dict:
    """Executa uma ação da whitelist após validação completa.
    Contrato de retorno:
      ok  → {"ok": True, "action", "summary", "changed"}
      erro → {"ok": False, "error", "status_code": 400|403|404}
    Escreve sempre no ImmutableAuditLog quando bem-sucedida."""
    if action not in ACTIONS:
        return {"ok": False,
                "error": f"Ação '{action}' não está na whitelist de ações "
                         "do copiloto.",
                "status_code": 400}
    if role not in ACTIONS[action]["roles"]:
        return {"ok": False,
                "error": "O seu papel não permite executar ações pelo "
                         "copiloto (apenas auditor/admin).",
                "status_code": 403}
    params = params if isinstance(params, dict) else {}

    missing = [p for p in ACTIONS[action]["params"] if params.get(p) is None]
    if missing:
        return {"ok": False,
                "error": f"Parâmetros em falta: {', '.join(missing)}.",
                "status_code": 400}

    # valida valores contra listas fechadas
    for field, allowed in ACTIONS[action]["choices"].items():
        if params.get(field) not in allowed:
            return {"ok": False,
                    "error": f"Valor inválido para {field}: "
                             f"{params.get(field)}. Permitidos: "
                             f"{', '.join(allowed)}.",
                    "status_code": 400}

    try:
        if action == "set_alert_status":
            obj = Alert.objects.get(id=int(params["alert_id"]))
            old = obj.status
            obj.status = params["status"]
            obj.save(update_fields=["status"])
            summary = (f"Alerta {obj.id} ({obj.alert_type}) mudou de "
                       f"«{old}» para «{_STATUS_PT[obj.status]}».")
        elif action == "set_case_status":
            obj = AuditCase.objects.get(id=int(params["case_id"]))
            old = obj.status
            obj.status = params["status"]
            obj.save(update_fields=["status"])
            summary = (f"Caso {obj.id} («{obj.title[:60]}») mudou de "
                       f"«{old}» para «{_STATUS_PT[obj.status]}».")
        elif action == "set_case_priority":
            obj = AuditCase.objects.get(id=int(params["case_id"]))
            old = obj.priority
            obj.priority = params["priority"]
            obj.save(update_fields=["priority"])
            summary = (f"Prioridade do caso {obj.id} («{obj.title[:60]}») "
                       f"mudou de «{_PRIORITY_PT.get(old, old)}» para "
                       f"«{_PRIORITY_PT[obj.priority]}».")
        else:  # defensivo — não deve acontecer
            return {"ok": False, "error": "Ação não implementada.",
                    "status_code": 400}
    except (Alert.DoesNotExist, AuditCase.DoesNotExist):
        return {"ok": False,
                "error": "O objeto indicado já não existe (pode ter sido "
                         "removido).", "status_code": 404}
    except (TypeError, ValueError):
        return {"ok": False, "error": "IDs devem ser numéricos.",
                "status_code": 400}
    except Exception as e:
        logger.warning("copilot act falhou: %s", e)
        return {"ok": False, "error": f"Falha ao executar: {e}",
                "status_code": 500}

    try:
        ImmutableAuditLog.objects.create(
            actor_id=username or "copilot_user",
            action_type=f"COPILOT_{action.upper()}",
            resource_id=str(obj.id),
            details={"role": role, "params": dict(params),
                     "via": "copilot_act"},
        )
    except Exception as e:
        logger.warning("copilot act audit log falhou: %s", e)

    return {"ok": True, "action": action, "summary": summary,
            "changed": {k: v for k, v in params.items()},
            "executed_at": timezone.now().isoformat()}

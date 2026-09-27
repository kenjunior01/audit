import operator
from typing import Annotated, List, TypedDict, Union
from langgraph.graph import StateGraph, END
from django.utils import timezone
from .ai_service import AuditAI
from .models import Transaction, AuditCase, Alert

# --- State Definition ---
class AuditState(TypedDict):
    transaction_id: str
    risk_score: float
    reasons: Annotated[List[str], operator.add]
    status: str # 'New', 'Investigating', 'Approved', 'Flagged'
    decision: str
    logs: Annotated[List[str], operator.add]
    work_paper: str  # Generated Audit Work Paper

# --- Nodes ---

def initial_risk_assessment(state: AuditState):
    """
    Step 1: Calculate base risk using existing AuditAI logic (Rules + Basic Context).
    """
    tx_id = state['transaction_id']
    logs = [f"[{timezone.now().strftime('%H:%M:%S')}] Started Initial Assessment for {tx_id}"]
    
    try:
        transaction = Transaction.objects.get(id=tx_id)
        ai = AuditAI(user_id=transaction.user_id)
        
        # Use existing logic
        risk_score, reasons = ai.analyze_transaction_risk(transaction)
        
        return {
            "risk_score": risk_score,
            "reasons": reasons,
            "status": "Investigating",
            "logs": logs + [f"Base Risk Score: {risk_score:.2f}"]
        }
    except Transaction.DoesNotExist:
        return {
            "status": "Error",
            "logs": logs + ["Transaction not found."]
        }

def deep_investigation(state: AuditState):
    """
    Step 2: If risk is significant, dig deeper into RAG and Memory.
    Also generates a Draft Work Paper.
    """
    logs = [f"[{timezone.now().strftime('%H:%M:%S')}] Triggered Deep Investigation (Risk > 0.4)"]
    reasons = []
    work_paper = ""
    
    try:
        transaction = Transaction.objects.get(id=state['transaction_id'])
        ai = AuditAI(user_id=transaction.user_id)
        
        # 1. Generate Work Paper using LLM
        logs.append("Generating Draft Work Paper (NBC TA)...")
        work_paper = ai.generate_work_paper_content(transaction, state['risk_score'], state['reasons'])
        logs.append("Work Paper Generated.")
        
        # 2. Check Mem0 for Institutional Knowledge (Feedback Loop)
        if ai.mem0:
            memories = ai.mem0.search(f"audit rules for {transaction.vendor} {transaction.category}", user_id="project_brain")
            if memories:
                for m in memories:
                    reasons.append(f"[Institutional Memory] {m.get('text', '')}")
                    logs.append(f"Memory Recall: {m.get('text', '')[:50]}...")

    except Exception as e:
        logs.append(f"Investigation Error: {str(e)}")
    
    return {
        "reasons": reasons,
        "logs": logs,
        "work_paper": work_paper
    }

def supervisor_review(state: AuditState):
    """
    Step 3: 'Senior Agent' review. Adjusts score based on global policies.
    """
    logs = [f"[{timezone.now().strftime('%H:%M:%S')}] Supervisor Agent Reviewing..."]
    adjustment = 0.0
    
    # Example: If many reasons are "Personal", reduce severity slightly (trust the human context)
    personal_factors = [r for r in state['reasons'] if '[Personal]' in r]
    if len(personal_factors) > 2:
        adjustment = -0.1
        logs.append("Supervisor: Detected strong personal context. Reducing risk slightly.")
    
    # Institutional Memory Impact
    memory_factors = [r for r in state['reasons'] if '[Institutional Memory]' in r]
    if memory_factors:
        # If memory says "Ignore" or "Safe", massive reduction
        if any("safe" in m.lower() or "false positive" in m.lower() for m in memory_factors):
            adjustment -= 0.5
            logs.append("Supervisor: Institutional Memory indicates FALSE POSITIVE history. Reducing risk significantly.")
        elif any("fraud" in m.lower() or "risk" in m.lower() for m in memory_factors):
            adjustment += 0.3
            logs.append("Supervisor: Institutional Memory indicates FRAUD history. Increasing risk.")

    return {
        "risk_score": state['risk_score'] + adjustment,
        "logs": logs
    }

def final_decision(state: AuditState):
    """
    Step 4: Finalize status and persist results.
    """
    score = state['risk_score']
    decision = "Approve"
    status = "Approved"
    
    if score > 0.7:
        decision = "Reject / Freeze"
        status = "Flagged"
    elif score > 0.4:
        decision = "Manual Review Required"
        status = "Flagged"
        
    logs = [f"[{timezone.now().strftime('%H:%M:%S')}] Final Decision: {decision}"]
    
    return {
        "decision": decision,
        "status": status,
        "logs": logs
    }

# --- Edge Logic ---

def should_investigate(state: AuditState):
    if state.get('status') == 'Error':
        return "end"
    if state['risk_score'] > 0.4:
        return "investigate"
    return "decide"

# --- Graph Construction ---

def create_audit_graph():
    workflow = StateGraph(AuditState)
    
    # Add Nodes
    workflow.add_node("initial_risk_assessment", initial_risk_assessment)
    workflow.add_node("deep_investigation", deep_investigation)
    workflow.add_node("supervisor_review", supervisor_review)
    workflow.add_node("final_decision", final_decision)
    
    # Set Entry
    workflow.set_entry_point("initial_risk_assessment")
    
    # Add Conditional Edges
    workflow.add_conditional_edges(
        "initial_risk_assessment",
        should_investigate,
        {
            "investigate": "deep_investigation",
            "decide": "final_decision",
            "end": END
        }
    )
    
    # Add Normal Edges
    workflow.add_edge("deep_investigation", "supervisor_review")
    workflow.add_edge("supervisor_review", "final_decision")
    workflow.add_edge("final_decision", END)
    
    return workflow.compile()

# Singleton accessor
_graph = None
def get_audit_graph():
    global _graph
    if _graph is None:
        _graph = create_audit_graph()
    return _graph

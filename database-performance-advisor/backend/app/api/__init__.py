"""API routes for Database Performance Advisor."""

import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.optimizer.query_optimizer import optimize_query

router = APIRouter(prefix="/api")


class AnalyzeRequest(BaseModel):
    query: str = Field(min_length=1, max_length=5000)


def find_table(node):
    if node.get("Relation Name"):
        return node["Relation Name"]

    for child in node.get("Plans", []):
        table = find_table(child)
        if table:
            return table

    return None


@router.post("/analyze")
def analyze(request: AnalyzeRequest):
    query = request.query.strip()

    if query.endswith(";"):
        query = query[:-1].strip()

    if not re.match(r"(?i)^SELECT\b", query) or ";" in query:
        raise HTTPException(
            status_code=400,
            detail="Submit one SELECT statement without internal semicolons.",
        )

    try:
        result = optimize_query(query)
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="PostgreSQL analysis failed. Check database configuration and tables.",
        )

    plan = result.plan or {}
    root = plan.get("Plan", {})

    return {
        "query": query,
        "query_type": "SELECT",
        "primary_table": find_table(root),
        "execution_time_ms": result.execution_time_ms,
        "planning_time_ms": result.planning_time_ms,
        "estimated_cost": root.get("Total Cost", 0),
        "rows_returned": result.rows_returned or 0,
        "detected_issue": (
            result.diagnosis[0]
            if result.diagnosis
            else "No significant issue detected."
        ),
        "recommendation": (
            result.recommendations[0]
            if result.recommendations
            else "No additional recommendation."
        ),
        "diagnosis": result.diagnosis,
        "recommendations": result.recommendations,
        "scan_types": result.scan_types,
        "indexes_used": result.indexes_used,
        "result_source": "PostgreSQL EXPLAIN ANALYZE",
        "database_execution": "Performed",
        "demo": False,
        "plan": result.plan,
    }

"""Router for analytics endpoints.

Each endpoint performs SQL aggregation queries on the interaction data
populated by the ETL pipeline. All endpoints require a `lab` query
parameter to filter results by lab (e.g., "lab-01").
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlmodel import select, func, case
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List

from app.database import get_session
from app.models.item import ItemRecord
from app.models.interaction import InteractionLog
from app.models.learner import Learner

router = APIRouter()


def _lab_title_from_param(lab_param: str) -> str:
    """Convert 'lab-04' to 'Lab 04' format for searching."""
    parts = lab_param.split('-')
    if len(parts) == 2 and parts[0] == 'lab':
        try:
            num = int(parts[1])
            return f"Lab {num:02d}"
        except ValueError:
            pass
    return lab_param


async def _get_lab_and_tasks(lab: str, session: AsyncSession):
    """Helper to get lab item and its task items."""
    lab_title = _lab_title_from_param(lab)
    
    # Find the lab
    stmt = select(ItemRecord).where(
        ItemRecord.type == "lab",
        ItemRecord.title.contains(lab_title)
    )
    result = await session.exec(stmt)
    lab_item = result.first()
    
    if not lab_item:
        raise HTTPException(status_code=404, detail=f"Lab '{lab}' not found")
    
    # Find all tasks for this lab
    stmt = select(ItemRecord).where(
        ItemRecord.type == "task",
        ItemRecord.parent_id == lab_item.id
    )
    result = await session.exec(stmt)
    tasks = result.all()
    task_ids = [task.id for task in tasks]
    
    return lab_item, tasks, task_ids


@router.get("/scores")
async def get_scores(
    lab: str = Query(..., description="Lab identifier, e.g. 'lab-01'"),
    session: AsyncSession = Depends(get_session),
):
    """Score distribution histogram for a given lab.
    
    Returns 4 buckets: 0-25, 26-50, 51-75, 76-100
    """
    try:
        # Get lab and tasks
        _, _, task_ids = await _get_lab_and_tasks(lab, session)
        
        if not task_ids:
            # Return empty buckets if no tasks
            return [
                {"bucket": "0-25", "count": 0},
                {"bucket": "26-50", "count": 0},
                {"bucket": "51-75", "count": 0},
                {"bucket": "76-100", "count": 0}
            ]
        
        # Query with CASE expression for buckets
        stmt = select(
            case(
                (InteractionLog.score <= 25, "0-25"),
                (InteractionLog.score <= 50, "26-50"),
                (InteractionLog.score <= 75, "51-75"),
                else_="76-100"
            ).label("bucket"),
            func.count().label("count")
        ).where(
            InteractionLog.item_id.in_(task_ids),
            InteractionLog.score.isnot(None)
        ).group_by("bucket")
        
        result = await session.exec(stmt)
        rows = result.all()
        
        # Convert to dict for easy lookup
        counts = {row.bucket: row.count for row in rows}
        
        # Return all buckets in order
        return [
            {"bucket": "0-25", "count": counts.get("0-25", 0)},
            {"bucket": "26-50", "count": counts.get("26-50", 0)},
            {"bucket": "51-75", "count": counts.get("51-75", 0)},
            {"bucket": "76-100", "count": counts.get("76-100", 0)}
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pass-rates")
async def get_pass_rates(
    lab: str = Query(..., description="Lab identifier, e.g. 'lab-01'"),
    session: AsyncSession = Depends(get_session),
):
    """Per-task pass rates for a given lab."""
    try:
        # Get lab and tasks
        _, tasks, task_ids = await _get_lab_and_tasks(lab, session)
        
        if not tasks:
            return []
        
        # Build result for each task
        result = []
        for task in tasks:
            stmt = select(
                func.avg(InteractionLog.score).label("avg_score"),
                func.count().label("attempts")
            ).where(
                InteractionLog.item_id == task.id,
                InteractionLog.score.isnot(None)
            )
            row = await session.exec(stmt)
            stats = row.one()
            
            result.append({
                "task": task.title,
                "avg_score": round(stats.avg_score or 0, 1),
                "attempts": stats.attempts or 0
            })
        
        # Sort by task title
        result.sort(key=lambda x: x["task"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timeline")
async def get_timeline(
    lab: str = Query(..., description="Lab identifier, e.g. 'lab-01'"),
    session: AsyncSession = Depends(get_session),
):
    """Submissions per day for a given lab."""
    try:
        # Get task IDs
        _, _, task_ids = await _get_lab_and_tasks(lab, session)
        
        if not task_ids:
            return []
        
        # Group by date
        stmt = select(
            func.date(InteractionLog.created_at).label("date"),
            func.count().label("submissions")
        ).where(
            InteractionLog.item_id.in_(task_ids)
        ).group_by(
            func.date(InteractionLog.created_at)
        ).order_by("date")
        
        result = await session.exec(stmt)
        rows = result.all()
        
        return [
            {"date": str(row.date), "submissions": row.submissions}
            for row in rows
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/groups")
async def get_groups(
    lab: str = Query(..., description="Lab identifier, e.g. 'lab-01'"),
    session: AsyncSession = Depends(get_session),
):
    """Per-group performance for a given lab."""
    try:
        # Get task IDs
        _, _, task_ids = await _get_lab_and_tasks(lab, session)
        
        if not task_ids:
            return []
        
        # Join with learners to get group info
        stmt = select(
            Learner.student_group.label("group"),
            func.avg(InteractionLog.score).label("avg_score"),
            func.count(func.distinct(Learner.id)).label("students")
        ).join(
            InteractionLog, Learner.id == InteractionLog.learner_id
        ).where(
            InteractionLog.item_id.in_(task_ids),
            InteractionLog.score.isnot(None),
            Learner.student_group.isnot(None),
            Learner.student_group != ""
        ).group_by(
            Learner.student_group
        ).order_by(
            Learner.student_group
        )
        
        result = await session.exec(stmt)
        rows = result.all()
        
        return [
            {
                "group": row.group,
                "avg_score": round(row.avg_score or 0, 1),
                "students": row.students or 0
            }
            for row in rows
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
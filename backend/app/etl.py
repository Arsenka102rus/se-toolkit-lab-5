"""ETL pipeline: fetch data from the autochecker API and load it into the database.

The autochecker dashboard API provides two endpoints:
- GET /api/items — lab/task catalog
- GET /api/logs  — anonymized check results (supports ?since= and ?limit= params)

Both require HTTP Basic Auth (email + password from settings).
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
import httpx
from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession

from app.settings import settings
from app.models.item import ItemRecord
from app.models.learner import Learner
from app.models.interaction import InteractionLog


# ---------------------------------------------------------------------------
# Extract — fetch data from the autochecker API
# ---------------------------------------------------------------------------


async def fetch_items() -> List[dict]:
    """Fetch the lab/task catalog from the autochecker API."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.autochecker_api_url}/api/items",
            auth=(settings.autochecker_email, settings.autochecker_password)
        )
        response.raise_for_status()
        return response.json()


async def fetch_logs(since: Optional[datetime] = None) -> List[dict]:
    """Fetch check results from the autochecker API with pagination."""
    all_logs = []
    has_more = True
    current_since = since
    
    async with httpx.AsyncClient() as client:
        while has_more:
            # Формируем параметры запроса
            params: Dict[str, Any] = {"limit": 500}
            if current_since:
                # Конвертируем datetime в ISO формат
                if isinstance(current_since, datetime):
                    params["since"] = current_since.strftime("%Y-%m-%dT%H:%M:%SZ")
                else:
                    params["since"] = str(current_since)
            
            # Делаем запрос
            response = await client.get(
                f"{settings.autochecker_api_url}/api/logs",
                auth=(settings.autochecker_email, settings.autochecker_password),
                params=params
            )
            response.raise_for_status()
            data = response.json()
            
            # Добавляем логи к общему списку
            all_logs.extend(data["logs"])
            
            # Проверяем, есть ли еще страницы
            has_more = data.get("has_more", False)
            
            # Если есть еще страницы, обновляем since для следующего запроса
            if has_more and data["logs"]:
                # Берем submitted_at последнего лога
                last_log = data["logs"][-1]
                current_since = datetime.fromisoformat(
                    last_log["submitted_at"].replace("Z", "+00:00")
                )
    
    return all_logs


# ---------------------------------------------------------------------------
# Load — insert fetched data into the local database
# ---------------------------------------------------------------------------


async def load_items(items: List[dict], session: AsyncSession) -> int:
    """Load items (labs and tasks) into the database."""
    new_count = 0
    labs_dict = {}  # Для хранения созданных лаб по short_id
    
    # Сначала обрабатываем лабы
    for item in items:
        if item["type"] == "lab":
            # Проверяем, существует ли уже такая лаба
            statement = select(ItemRecord).where(
                ItemRecord.type == "lab",
                ItemRecord.title == item["title"]
            )
            result = await session.exec(statement)
            existing = result.first()
            
            if not existing:
                # Создаем новую лабу
                new_lab = ItemRecord(
                    type="lab",
                    title=item["title"]
                )
                session.add(new_lab)
                await session.flush()  # Чтобы получить id
                labs_dict[item["lab"]] = new_lab
                new_count += 1
            else:
                labs_dict[item["lab"]] = existing
    
    # Затем обрабатываем задачи
    for item in items:
        if item["type"] == "task":
            # Находим родительскую лабу
            parent_lab = labs_dict.get(item["lab"])
            if not parent_lab:
                continue  # Пропускаем если лаба не найдена
            
            # Проверяем, существует ли уже такая задача
            statement = select(ItemRecord).where(
                ItemRecord.type == "task",
                ItemRecord.title == item["title"],
                ItemRecord.parent_id == parent_lab.id
            )
            result = await session.exec(statement)
            existing = result.first()
            
            if not existing:
                # Создаем новую задачу
                new_task = ItemRecord(
                    type="task",
                    title=item["title"],
                    parent_id=parent_lab.id
                )
                session.add(new_task)
                new_count += 1
    
    await session.commit()
    return new_count


async def load_logs(
    logs: List[dict], items_catalog: List[dict], session: AsyncSession
) -> int:
    """Load interaction logs into the database."""
    new_count = 0
    
    # Создаем lookup для поиска item'ов по (lab, task)
    item_lookup = {}
    for item in items_catalog:
        if item["type"] == "lab":
            item_lookup[(item["lab"], None)] = item["title"]
        else:  # task
            item_lookup[(item["lab"], item["task"])] = item["title"]
    
    for log in logs:
        try:
            # 1. Находим или создаем Learner
            statement = select(Learner).where(Learner.external_id == log["student_id"])
            result = await session.exec(statement)
            learner = result.first()
            
            if not learner:
                learner = Learner(
                    external_id=log["student_id"],
                    student_group=log.get("group", "")
                )
                session.add(learner)
                await session.flush()
            
            # 2. Находим Item по title
            item_title = item_lookup.get((log["lab"], log.get("task")))
            if not item_title:
                print(f"Warning: No item title found for lab={log['lab']}, task={log.get('task')}")
                continue
            
            # Находим предмет с таким названием
            statement = select(ItemRecord).where(ItemRecord.title == item_title)
            result = await session.exec(statement)
            item = result.first()
            
            if not item:
                print(f"Warning: No items found with title '{item_title}'")
                continue
            
            # 3. Проверяем, существует ли уже такой лог (идемпотентность)
            try:
                log_id = int(log["id"])  # Конвертируем строку в число
            except (ValueError, TypeError):
                print(f"Warning: Could not convert log id '{log['id']}' to int")
                continue
                
            statement = select(InteractionLog).where(
                InteractionLog.external_id == log_id
            )
            result = await session.exec(statement)
            existing_log = result.first()
            
            if existing_log:
                continue  # Пропускаем если лог уже есть
            
            # 4. Создаем новый InteractionLog
            submitted_at = datetime.fromisoformat(
                log["submitted_at"].replace("Z", "+00:00")
            )
            
            new_log = InteractionLog(
                external_id=log_id,
                learner_id=learner.id,
                item_id=item.id,
                kind="attempt",
                score=float(log["score"]),
                checks_passed=int(log["passed"]),
                checks_total=int(log["total"]),
                created_at=submitted_at
            )
            session.add(new_log)
            new_count += 1
            
        except Exception as e:
            print(f"Error processing log {log.get('id')}: {e}")
            continue
    
    await session.commit()
    return new_count


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def sync(session: AsyncSession) -> dict:
    """Run the full ETL pipeline."""
    # Step 1: Fetch and load items
    items_data = await fetch_items()
    items_new = await load_items(items_data, session)
    
    # Step 2: Determine last sync timestamp
    statement = select(InteractionLog).order_by(InteractionLog.created_at.desc()).limit(1)
    result = await session.exec(statement)
    last_log = result.first()
    
    since = last_log.created_at if last_log else None
    
    # Step 3: Fetch and load logs
    logs_data = await fetch_logs(since=since)
    logs_new = await load_logs(logs_data, items_data, session)
    
    # Step 4: Get total count
    statement = select(func.count()).select_from(InteractionLog)
    result = await session.exec(statement)
    total_logs = result.one()
    
    return {
        "new_records": logs_new,
        "total_records": total_logs
    }
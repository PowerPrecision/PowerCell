import pytest


@pytest.mark.asyncio
async def test_create_activity_comment(client, admin_token):
    """Test creating a comment on a process"""
    list_response = await client.get(
        "/processes",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    processes = list_response.json()
    
    if processes:
        process_id = processes[0]["id"]
        response = await client.post(
            "/activities",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "process_id": process_id,
                "comment": "Comentário de teste pytest"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["comment"] == "Comentário de teste pytest"
        assert data["process_id"] == process_id


@pytest.mark.asyncio
async def test_get_activities_for_process(client, admin_token):
    """Test getting activities for a process"""
    list_response = await client.get(
        "/processes",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    processes = list_response.json()
    
    if processes:
        process_id = processes[0]["id"]
        response = await client.get(
            f"/activities?process_id={process_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_get_history_for_process(client, admin_token):
    """Test getting history for a process"""
    list_response = await client.get(
        "/processes",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    processes = list_response.json()
    
    if processes:
        process_id = processes[0]["id"]
        response = await client.get(
            f"/history?process_id={process_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_history_entry_has_required_fields(client, admin_token):
    """Test history entries have required fields"""
    list_response = await client.get(
        "/processes",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    processes = list_response.json()
    
    if processes:
        process_id = processes[0]["id"]
        response = await client.get(
            f"/history?process_id={process_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        history = response.json()
        
        if history:
            entry = history[0]
            assert "id" in entry
            assert "process_id" in entry
            assert "user_name" in entry
            assert "action" in entry
            assert "created_at" in entry


@pytest.mark.asyncio
async def test_create_deadline(client, admin_token):
    """Test creating a deadline for a process"""
    list_response = await client.get(
        "/processes",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    processes = list_response.json()
    
    if processes:
        process_id = processes[0]["id"]
        response = await client.post(
            "/deadlines",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "process_id": process_id,
                "title": "Prazo de teste pytest",
                "due_date": "2026-02-01",
                "priority": "high"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Prazo de teste pytest"
        assert data["priority"] == "high"


@pytest.mark.asyncio
async def test_get_deadlines(client, admin_token):
    """Test getting all deadlines"""
    response = await client.get(
        "/deadlines",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_get_deadlines_for_process(client, admin_token):
    """Test getting deadlines for specific process"""
    list_response = await client.get(
        "/processes",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    processes = list_response.json()
    
    if processes:
        process_id = processes[0]["id"]
        response = await client.get(
            f"/deadlines?process_id={process_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        deadlines = response.json()
        for deadline in deadlines:
            assert deadline["process_id"] == process_id

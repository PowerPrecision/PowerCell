import pytest


@pytest.mark.asyncio
async def test_get_processes_as_admin(client, admin_token):
    """Test admin can get all processes"""
    response = await client.get(
        "/processes",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_get_processes_unauthorized(client):
    """Test cannot get processes without auth - returns 401/403 when no token"""
    response = await client.get("/processes")
    # HTTPBearer returns 403 when no credentials provided
    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_get_single_process(client, admin_token):
    """Test get single process by ID"""
    list_response = await client.get(
        "/processes",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    processes = list_response.json()
    
    if processes:
        process_id = processes[0]["id"]
        response = await client.get(
            f"/processes/{process_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        assert response.json()["id"] == process_id


@pytest.mark.asyncio
async def test_get_nonexistent_process(client, admin_token):
    """Test get process that doesn't exist"""
    response = await client.get(
        "/processes/nonexistent-id-12345",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_process_status_as_admin(client, admin_token):
    """Test admin can update process status"""
    list_response = await client.get(
        "/processes",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    processes = list_response.json()
    
    if processes:
        process_id = processes[0]["id"]
        original_status = processes[0]["status"]
        
        response = await client.put(
            f"/processes/{process_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"status": "em_analise"}
        )
        assert response.status_code == 200
        
        # Restore original status
        await client.put(
            f"/processes/{process_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"status": original_status}
        )


@pytest.mark.asyncio
async def test_consultor_can_update_real_estate_data(client, consultor_token):
    """Test consultor can update real estate data"""
    list_response = await client.get(
        "/processes",
        headers={"Authorization": f"Bearer {consultor_token}"}
    )
    processes = list_response.json()
    
    if processes:
        process_id = processes[0]["id"]
        response = await client.put(
            f"/processes/{process_id}",
            headers={"Authorization": f"Bearer {consultor_token}"},
            json={
                "real_estate_data": {
                    "property_type": "Apartamento T2",
                    "property_zone": "Lisboa",
                    "max_budget": 250000.00
                }
            }
        )
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_mediador_cannot_update_credit_data_before_authorization(client, mediador_token):
    """Test mediador cannot add credit data before bank authorization"""
    list_response = await client.get(
        "/processes",
        headers={"Authorization": f"Bearer {mediador_token}"}
    )
    processes = list_response.json()
    
    early_process = next(
        (p for p in processes if p["status"] == "pedido_inicial"),
        None
    )
    
    if early_process:
        response = await client.put(
            f"/processes/{early_process['id']}",
            headers={"Authorization": f"Bearer {mediador_token}"},
            json={
                "credit_data": {
                    "requested_amount": 200000.00,
                    "loan_term_years": 30
                }
            }
        )
        assert response.status_code == 400
        assert "autorização bancária" in response.json()["detail"].lower()

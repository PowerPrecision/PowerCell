"""
End-to-End Tests for PowerCell Frontend
Using Playwright for browser automation
"""
import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:3000"


@pytest.fixture(scope="session")
def browser_context_args():
    return {
        "viewport": {"width": 1920, "height": 1080},
        "ignore_https_errors": True
    }


class TestPublicForm:
    """Tests for the public client registration form"""
    
    def test_public_form_loads(self, page: Page):
        """Test that the public form loads correctly"""
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        
        # Should see the registration form
        expect(page.locator("text=Formulário de Registo")).to_be_visible()
        expect(page.locator("text=Tipo de Serviço")).to_be_visible()
    
    def test_public_form_step_navigation(self, page: Page):
        """Test form step navigation"""
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        
        # Step 1: Select service type using data-testid
        page.click('[data-testid="process-type-credito"]')
        page.click("text=Próximo")
        
        # Step 2: Should show personal data form
        expect(page.locator("text=Dados Pessoais")).to_be_visible()
    
    def test_public_form_all_service_types(self, page: Page):
        """Test all three service types are selectable"""
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        
        # Check all three types exist
        expect(page.locator('[data-testid="process-type-credito"]')).to_be_visible()
        expect(page.locator('[data-testid="process-type-imobiliaria"]')).to_be_visible()
        expect(page.locator('[data-testid="process-type-ambos"]')).to_be_visible()
    
    def test_public_form_complete_flow(self, page: Page):
        """Test complete form flow navigation"""
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        
        # Step 1: Select Crédito
        page.click('[data-testid="process-type-credito"]')
        page.wait_for_timeout(500)
        
        # Verify selection is visible
        expect(page.locator('[data-testid="process-type-credito"]')).to_be_visible()
        
        # Click next to go to step 2
        page.click("text=Próximo")
        page.wait_for_timeout(1000)
        
        # Step 2: Should show personal data form
        expect(page.locator('[data-testid="client-name"]')).to_be_visible()
        expect(page.locator('[data-testid="client-email"]')).to_be_visible()
        expect(page.locator('[data-testid="client-phone"]')).to_be_visible()


class TestLogin:
    """Tests for the login page"""
    
    def test_login_page_loads(self, page: Page):
        """Test that login page loads correctly"""
        page.goto(f"{BASE_URL}/login")
        page.wait_for_load_state("networkidle")
        
        # Check for login form elements
        expect(page.locator('input[type="email"]')).to_be_visible()
        expect(page.locator('input[type="password"]')).to_be_visible()
        expect(page.locator('button[type="submit"]')).to_be_visible()
    
    def test_login_with_invalid_credentials(self, page: Page):
        """Test login with wrong credentials shows error"""
        page.goto(f"{BASE_URL}/login")
        page.wait_for_load_state("networkidle")
        
        page.fill('input[type="email"]', "wrong@email.pt")
        page.fill('input[type="password"]', "wrongpassword")
        page.click('button[type="submit"]')
        
        page.wait_for_timeout(2000)
        # Should show error - check for toast or error message
        error_visible = page.locator("text=Credenciais inválidas").is_visible() or \
                       page.locator("text=inválidas").is_visible() or \
                       page.locator("[data-sonner-toast]").is_visible()
        assert error_visible, "Error message should be visible"
    
    def test_login_admin_success(self, page: Page):
        """Test successful admin login"""
        page.goto(f"{BASE_URL}/login")
        page.wait_for_load_state("networkidle")
        
        page.fill('input[type="email"]', "admin@sistema.pt")
        page.fill('input[type="password"]', "admin123")
        page.click('button[type="submit"]')
        
        page.wait_for_timeout(3000)
        # Should redirect to dashboard
        assert "/admin" in page.url or "admin" in page.url.lower()
    
    def test_login_consultor_success(self, page: Page):
        """Test successful consultor login"""
        page.goto(f"{BASE_URL}/login")
        page.wait_for_load_state("networkidle")
        
        page.fill('input[type="email"]', "consultor@sistema.pt")
        page.fill('input[type="password"]', "consultor123")
        page.click('button[type="submit"]')
        
        page.wait_for_timeout(3000)
        # Should redirect to consultor dashboard
        assert "/consultor" in page.url or "consultor" in page.url.lower()
    
    def test_login_mediador_success(self, page: Page):
        """Test successful mediador login"""
        page.goto(f"{BASE_URL}/login")
        page.wait_for_load_state("networkidle")
        
        page.fill('input[type="email"]', "mediador@sistema.pt")
        page.fill('input[type="password"]', "mediador123")
        page.click('button[type="submit"]')
        
        page.wait_for_timeout(3000)
        # Should redirect to mediador dashboard
        assert "/mediador" in page.url or "mediador" in page.url.lower()


class TestAdminDashboard:
    """Tests for the admin dashboard"""
    
    def _login_as_admin(self, page: Page):
        """Helper to login as admin"""
        page.goto(f"{BASE_URL}/login")
        page.wait_for_load_state("networkidle")
        page.fill('input[type="email"]', "admin@sistema.pt")
        page.fill('input[type="password"]', "admin123")
        page.click('button[type="submit"]')
        page.wait_for_timeout(3000)
    
    def test_admin_dashboard_loads(self, page: Page):
        """Test admin dashboard loads with stats"""
        self._login_as_admin(page)
        
        # Should be on admin page and see dashboard elements
        expect(page.locator("text=Processos")).to_be_visible()
    
    def test_admin_can_see_processes(self, page: Page):
        """Test admin can see processes list"""
        self._login_as_admin(page)
        
        page.wait_for_timeout(1000)
        # Should show processes section
        expect(page.locator("text=Processos")).to_be_visible()
    
    def test_admin_can_see_stats(self, page: Page):
        """Test admin can see statistics"""
        self._login_as_admin(page)
        
        page.wait_for_timeout(1000)
        # Should show some stats
        stats_visible = page.locator("text=Total").is_visible() or \
                       page.locator("text=Estatísticas").is_visible()
        assert stats_visible


class TestNavigation:
    """Tests for navigation between pages"""
    
    def test_navigate_to_login_from_home(self, page: Page):
        """Test navigation from home to login"""
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        
        # Click on "Aceder ao sistema" link
        page.click("text=Aceder ao sistema")
        page.wait_for_timeout(1000)
        
        expect(page).to_have_url(f"{BASE_URL}/login")
    
    def test_protected_route_redirects_to_login(self, page: Page):
        """Test that protected routes redirect to login"""
        page.goto(f"{BASE_URL}/admin")
        page.wait_for_timeout(2000)
        
        # Should redirect to login
        assert "/login" in page.url or page.locator('input[type="email"]').is_visible()


class TestResponsiveness:
    """Tests for responsive design"""
    
    def test_mobile_public_form(self, page: Page):
        """Test public form works on mobile viewport"""
        page.set_viewport_size({"width": 375, "height": 812})  # iPhone X
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        
        expect(page.locator("text=Formulário de Registo")).to_be_visible()
        expect(page.locator('[data-testid="process-type-credito"]')).to_be_visible()
    
    def test_mobile_login(self, page: Page):
        """Test login works on mobile viewport"""
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(f"{BASE_URL}/login")
        page.wait_for_load_state("networkidle")
        
        expect(page.locator('input[type="email"]')).to_be_visible()
        expect(page.locator('input[type="password"]')).to_be_visible()
    
    def test_tablet_view(self, page: Page):
        """Test form on tablet viewport"""
        page.set_viewport_size({"width": 768, "height": 1024})  # iPad
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        
        expect(page.locator("text=Formulário de Registo")).to_be_visible()

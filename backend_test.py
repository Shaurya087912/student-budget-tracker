import requests
import sys
import json
from datetime import datetime, timedelta
import uuid

class FuturaBudgetTrackerTester:
    def __init__(self, base_url="https://neon-tracker-1.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.user_id = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_user_email = f"test_user_{uuid.uuid4().hex[:8]}@example.com"
        self.test_user_password = "TestPass123!"
        self.test_user_name = "Test User"

    def log_test(self, name, success, details=""):
        """Log test results"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name} - PASSED")
        else:
            print(f"❌ {name} - FAILED: {details}")

    def make_request(self, method, endpoint, data=None, auth_required=True):
        """Make HTTP request with proper headers"""
        url = f"{self.base_url}/api/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        if auth_required and self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=10)
            
            return response
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {str(e)}")
            return None

    def test_user_registration(self):
        """Test user registration"""
        data = {
            "name": self.test_user_name,
            "email": self.test_user_email,
            "password": self.test_user_password
        }
        
        response = self.make_request('POST', 'auth/register', data, auth_required=False)
        
        if response and response.status_code == 200:
            response_data = response.json()
            if 'access_token' in response_data and 'user' in response_data:
                self.token = response_data['access_token']
                self.user_id = response_data['user']['id']
                self.log_test("User Registration", True)
                return True
            else:
                self.log_test("User Registration", False, "Missing token or user in response")
                return False
        else:
            error_msg = response.text if response else "No response"
            self.log_test("User Registration", False, f"Status: {response.status_code if response else 'None'}, Error: {error_msg}")
            return False

    def test_user_login(self):
        """Test user login"""
        data = {
            "email": self.test_user_email,
            "password": self.test_user_password
        }
        
        response = self.make_request('POST', 'auth/login', data, auth_required=False)
        
        if response and response.status_code == 200:
            response_data = response.json()
            if 'access_token' in response_data:
                self.token = response_data['access_token']
                self.log_test("User Login", True)
                return True
            else:
                self.log_test("User Login", False, "Missing access token")
                return False
        else:
            error_msg = response.text if response else "No response"
            self.log_test("User Login", False, f"Status: {response.status_code if response else 'None'}, Error: {error_msg}")
            return False

    def test_get_current_user(self):
        """Test getting current user info"""
        response = self.make_request('GET', 'user/me')
        
        if response and response.status_code == 200:
            user_data = response.json()
            if 'id' in user_data and 'email' in user_data:
                self.log_test("Get Current User", True)
                return True
            else:
                self.log_test("Get Current User", False, "Missing user data fields")
                return False
        else:
            error_msg = response.text if response else "No response"
            self.log_test("Get Current User", False, f"Status: {response.status_code if response else 'None'}, Error: {error_msg}")
            return False

    def test_create_transaction(self):
        """Test creating a transaction"""
        data = {
            "type": "expense",
            "amount": 150.0,
            "category": "Food",
            "description": "Lunch at restaurant",
            "payment_type": "Card",
            "tags": ["lunch", "restaurant"]
        }
        
        response = self.make_request('POST', 'transactions', data)
        
        if response and response.status_code == 200:
            transaction_data = response.json()
            if 'id' in transaction_data and transaction_data['amount'] == 150.0:
                self.transaction_id = transaction_data['id']
                self.log_test("Create Transaction", True)
                return True
            else:
                self.log_test("Create Transaction", False, "Invalid transaction data returned")
                return False
        else:
            error_msg = response.text if response else "No response"
            self.log_test("Create Transaction", False, f"Status: {response.status_code if response else 'None'}, Error: {error_msg}")
            return False

    def test_get_transactions(self):
        """Test getting transactions list"""
        response = self.make_request('GET', 'transactions')
        
        if response and response.status_code == 200:
            transactions = response.json()
            if isinstance(transactions, list):
                self.log_test("Get Transactions", True)
                return True
            else:
                self.log_test("Get Transactions", False, "Response is not a list")
                return False
        else:
            error_msg = response.text if response else "No response"
            self.log_test("Get Transactions", False, f"Status: {response.status_code if response else 'None'}, Error: {error_msg}")
            return False

    def test_dashboard_data(self):
        """Test getting dashboard data"""
        response = self.make_request('GET', 'dashboard')
        
        if response and response.status_code == 200:
            dashboard_data = response.json()
            required_fields = ['total_income', 'total_expenses', 'balance', 'budget_used_percent', 'recent_transactions']
            
            if all(field in dashboard_data for field in required_fields):
                self.log_test("Get Dashboard Data", True)
                return True
            else:
                missing_fields = [field for field in required_fields if field not in dashboard_data]
                self.log_test("Get Dashboard Data", False, f"Missing fields: {missing_fields}")
                return False
        else:
            error_msg = response.text if response else "No response"
            self.log_test("Get Dashboard Data", False, f"Status: {response.status_code if response else 'None'}, Error: {error_msg}")
            return False

    def test_create_budget(self):
        """Test creating a budget"""
        data = {
            "category": "Food",
            "limit": 5000.0,
            "period": "monthly"
        }
        
        response = self.make_request('POST', 'budgets', data)
        
        if response and response.status_code == 200:
            budget_data = response.json()
            if 'id' in budget_data and budget_data['limit'] == 5000.0:
                self.log_test("Create Budget", True)
                return True
            else:
                self.log_test("Create Budget", False, "Invalid budget data returned")
                return False
        else:
            error_msg = response.text if response else "No response"
            self.log_test("Create Budget", False, f"Status: {response.status_code if response else 'None'}, Error: {error_msg}")
            return False

    def test_get_budgets(self):
        """Test getting budgets list"""
        response = self.make_request('GET', 'budgets')
        
        if response and response.status_code == 200:
            budgets = response.json()
            if isinstance(budgets, list):
                self.log_test("Get Budgets", True)
                return True
            else:
                self.log_test("Get Budgets", False, "Response is not a list")
                return False
        else:
            error_msg = response.text if response else "No response"
            self.log_test("Get Budgets", False, f"Status: {response.status_code if response else 'None'}, Error: {error_msg}")
            return False

    def test_get_insights(self):
        """Test getting insights"""
        response = self.make_request('GET', 'insights')
        
        if response and response.status_code == 200:
            insights_data = response.json()
            if 'tips' in insights_data and 'projection' in insights_data:
                self.log_test("Get Insights", True)
                return True
            else:
                self.log_test("Get Insights", False, "Missing tips or projection in response")
                return False
        else:
            error_msg = response.text if response else "No response"
            self.log_test("Get Insights", False, f"Status: {response.status_code if response else 'None'}, Error: {error_msg}")
            return False

    def test_delete_transaction(self):
        """Test deleting a transaction"""
        if not hasattr(self, 'transaction_id'):
            self.log_test("Delete Transaction", False, "No transaction ID available")
            return False
            
        response = self.make_request('DELETE', f'transactions/{self.transaction_id}')
        
        if response and response.status_code == 200:
            self.log_test("Delete Transaction", True)
            return True
        else:
            error_msg = response.text if response else "No response"
            self.log_test("Delete Transaction", False, f"Status: {response.status_code if response else 'None'}, Error: {error_msg}")
            return False

    def run_all_tests(self):
        """Run all backend API tests"""
        print("🚀 Starting FUTURA Budget Tracker Backend API Tests")
        print(f"📍 Testing against: {self.base_url}")
        print("=" * 60)

        # Test authentication flow
        if not self.test_user_registration():
            print("❌ Registration failed, stopping tests")
            return False

        # Test other endpoints
        self.test_get_current_user()
        self.test_create_transaction()
        self.test_get_transactions()
        self.test_dashboard_data()
        self.test_create_budget()
        self.test_get_budgets()
        self.test_get_insights()
        self.test_delete_transaction()

        # Test login separately (after registration)
        self.test_user_login()

        print("=" * 60)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} tests passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All backend API tests passed!")
            return True
        else:
            print(f"⚠️  {self.tests_run - self.tests_passed} tests failed")
            return False

def main():
    tester = FuturaBudgetTrackerTester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
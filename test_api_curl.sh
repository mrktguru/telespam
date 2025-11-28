#!/bin/bash
# API Testing with curl - Examples for terminal testing
# Run the API server first: USE_MOCK_STORAGE=true python main.py

API_URL="http://localhost:8000"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Check if server is running
check_server() {
    print_header "Checking API Server"

    response=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/health")

    if [ "$response" = "200" ]; then
        print_success "API server is running"
        return 0
    else
        print_error "API server is not running (HTTP $response)"
        echo "Start it with: USE_MOCK_STORAGE=true python main.py"
        return 1
    fi
}

# Test 1: Get API info
test_api_info() {
    print_header "TEST 1: Get API Info"

    echo "Request: GET /"
    curl -s "$API_URL/" | jq '.'
    print_success "API info retrieved"
}

# Test 2: Get all accounts
test_get_accounts() {
    print_header "TEST 2: Get All Accounts"

    echo "Request: GET /accounts"
    curl -s "$API_URL/accounts" | jq '.'
    print_success "Accounts list retrieved"
}

# Test 3: Add a test account (simulated)
test_add_account() {
    print_header "TEST 3: Add Test Account"

    echo "Note: This would normally process a tdata/session file"
    echo "For testing without real files, use the Python test script"
    echo ""
    echo "Example command:"
    echo "curl -X POST '$API_URL/accounts/upload' \\"
    echo "  -F 'file=@account.zip' \\"
    echo "  -F 'notes=Test account'"
}

# Test 4: Check account status
test_check_account() {
    print_header "TEST 4: Check Account Status"

    account_id="${1:-test_1}"
    echo "Request: POST /accounts/$account_id/check"

    response=$(curl -s -X POST "$API_URL/accounts/$account_id/check")
    echo "$response" | jq '.'

    if echo "$response" | jq -e '.success' > /dev/null 2>&1; then
        success=$(echo "$response" | jq -r '.success')
        if [ "$success" = "true" ]; then
            print_success "Account check successful"
        else
            print_error "Account check failed"
        fi
    fi
}

# Test 5: Get specific account
test_get_account() {
    print_header "TEST 5: Get Specific Account"

    account_id="${1:-test_1}"
    echo "Request: GET /accounts/$account_id"

    curl -s "$API_URL/accounts/$account_id" | jq '.'
    print_success "Account details retrieved"
}

# Test 6: Send text message
test_send_text() {
    print_header "TEST 6: Send Text Message"

    user_id="${1:-123456789}"
    message="${2:-Hello from test!}"

    echo "Request: POST /send"
    echo "User ID: $user_id"
    echo "Message: $message"

    curl -s -X POST "$API_URL/send" \
        -H "Content-Type: application/json" \
        -d "{
            \"user_id\": $user_id,
            \"type\": \"text\",
            \"content\": \"$message\"
        }" | jq '.'

    print_success "Message send request sent"
}

# Test 7: Get settings
test_get_settings() {
    print_header "TEST 7: Get Settings"

    echo "Request: GET /settings"
    curl -s "$API_URL/settings" | jq '.'
    print_success "Settings retrieved"
}

# Test 8: Update proxy settings
test_update_proxy() {
    print_header "TEST 8: Update Proxy Settings"

    echo "Request: POST /settings/proxy"

    curl -s -X POST "$API_URL/settings/proxy" \
        -H "Content-Type: application/json" \
        -d '{
            "enabled": true,
            "default_proxy": {
                "type": "socks5",
                "host": "1.2.3.4",
                "port": 1080,
                "username": "user",
                "password": "pass"
            }
        }' | jq '.'

    print_success "Proxy settings updated"
}

# Test 9: Set account-specific proxy
test_set_account_proxy() {
    print_header "TEST 9: Set Account Proxy"

    account_id="${1:-test_1}"
    echo "Request: PUT /accounts/$account_id/proxy"

    curl -s -X PUT "$API_URL/accounts/$account_id/proxy" \
        -H "Content-Type: application/json" \
        -d '{
            "use_proxy": true,
            "type": "socks5",
            "host": "5.6.7.8",
            "port": 1080
        }' | jq '.'

    print_success "Account proxy settings updated"
}

# Test 10: Get dialog history
test_get_dialog() {
    print_header "TEST 10: Get Dialog History"

    user_id="${1:-123456789}"
    echo "Request: GET /dialogs/$user_id"

    curl -s "$API_URL/dialogs/$user_id?limit=10" | jq '.'
    print_success "Dialog history retrieved"
}

# Run all tests
run_all_tests() {
    if ! check_server; then
        return 1
    fi

    test_api_info
    test_get_accounts
    test_add_account
    test_get_account "test_1"
    test_check_account "test_1"
    test_send_text 123456789 "Test message"
    test_get_settings
    test_update_proxy
    test_set_account_proxy "test_1"
    test_get_dialog 123456789

    print_header "ALL TESTS COMPLETED"
}

# Interactive menu
show_menu() {
    echo ""
    echo "===== API Testing Menu ====="
    echo "1.  Check server status"
    echo "2.  Get API info"
    echo "3.  Get all accounts"
    echo "4.  Get specific account"
    echo "5.  Check account status"
    echo "6.  Send text message"
    echo "7.  Get settings"
    echo "8.  Update proxy settings"
    echo "9.  Set account proxy"
    echo "10. Get dialog history"
    echo "11. Run all tests"
    echo "12. Exit"
    echo ""
}

interactive_mode() {
    while true; do
        show_menu
        read -p "Select option (1-12): " choice

        case $choice in
            1) check_server ;;
            2) test_api_info ;;
            3) test_get_accounts ;;
            4)
                read -p "Account ID (default: test_1): " acc_id
                test_get_account "${acc_id:-test_1}"
                ;;
            5)
                read -p "Account ID (default: test_1): " acc_id
                test_check_account "${acc_id:-test_1}"
                ;;
            6)
                read -p "User ID (default: 123456789): " user_id
                read -p "Message text: " message
                test_send_text "${user_id:-123456789}" "${message:-Hello}"
                ;;
            7) test_get_settings ;;
            8) test_update_proxy ;;
            9)
                read -p "Account ID (default: test_1): " acc_id
                test_set_account_proxy "${acc_id:-test_1}"
                ;;
            10)
                read -p "User ID (default: 123456789): " user_id
                test_get_dialog "${user_id:-123456789}"
                ;;
            11) run_all_tests ;;
            12)
                echo "Exiting..."
                break
                ;;
            *) print_error "Invalid option" ;;
        esac
    done
}

# Main script
main() {
    print_header "TELEGRAM OUTREACH SYSTEM - API TESTING"

    # Check if jq is installed
    if ! command -v jq &> /dev/null; then
        print_error "jq is not installed (for JSON formatting)"
        echo "Install it with: apt-get install jq"
        echo "Tests will still work but output won't be formatted"
    fi

    if [ "$1" = "--auto" ]; then
        run_all_tests
    elif [ "$1" = "--help" ]; then
        echo "Usage:"
        echo "  ./test_api_curl.sh         - Interactive menu"
        echo "  ./test_api_curl.sh --auto  - Run all tests"
        echo "  ./test_api_curl.sh --help  - Show this help"
    else
        interactive_mode
    fi
}

main "$@"

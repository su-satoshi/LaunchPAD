#!/bin/bash

# AI Job Pilot - API Testing Script
# Tests all major endpoints after search completes

BASE_URL="http://localhost:8001/api"
PASS=0
FAIL=0

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================="
echo "AI Job Pilot - API Test Suite"
echo "========================================="
echo ""

# Test function
test_endpoint() {
    local name=$1
    local method=$2
    local endpoint=$3
    local expected_status=$4
    
    echo -n "Testing: $name ... "
    
    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" "$BASE_URL$endpoint")
    elif [ "$method" = "POST" ]; then
        response=$(curl -s -X POST -w "\n%{http_code}" "$BASE_URL$endpoint")
    fi
    
    http_code=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | head -n -1)
    
    if [ "$http_code" = "$expected_status" ] || [ "$http_code" = "200" ]; then
        echo -e "${GREEN}✓ PASS${NC} (HTTP $http_code)"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}✗ FAIL${NC} (HTTP $http_code, expected $expected_status)"
        echo "  Response: $body"
        FAIL=$((FAIL + 1))
    fi
}

# 1. Job Statistics
echo -e "${YELLOW}1. Dashboard Statistics${NC}"
test_endpoint "Job Stats Summary" "GET" "/jobs/stats/summary" "200"
echo ""

# 2. Job Listing
echo -e "${YELLOW}2. Job Listing & Filtering${NC}"
test_endpoint "List All Jobs" "GET" "/jobs" "200"
test_endpoint "List Matched Jobs" "GET" "/jobs?status=matched" "200"
test_endpoint "Filter by Source" "GET" "/jobs?source=linkedin" "200"
test_endpoint "Filter by Score" "GET" "/jobs?min_score=0.7" "200"
test_endpoint "Search Term" "GET" "/jobs?search=engineer" "200"
echo ""

# 3. Job Details (need to get a job ID first)
echo -e "${YELLOW}3. Job Details${NC}"
job_id=$(curl -s "$BASE_URL/jobs?limit=1" | python3 -c "import sys, json; jobs = json.load(sys.stdin).get('jobs', []); print(jobs[0]['id'] if jobs else '')" 2>/dev/null)

if [ -n "$job_id" ]; then
    test_endpoint "Get Job Details" "GET" "/jobs/$job_id" "200"
    echo ""
fi

# 4. Preferences
echo -e "${YELLOW}4. Settings & Preferences${NC}"
test_endpoint "Get Preferences" "GET" "/settings/preferences" "200"
test_endpoint "Get Profile" "GET" "/settings/profile" "200"
echo ""

# 5. Summary
echo "========================================="
echo "Test Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}"
echo "========================================="

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi

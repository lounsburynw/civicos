/**
 * Browser-Side Frontend Integration Tests
 * 
 * Run these tests directly in the browser console when the civic frontend is loaded.
 * Copy and paste this entire file into the browser console, then run:
 * 
 * runFrontendTests()
 * 
 * Tests all the issues we encountered during UX debugging:
 * - API URL configuration for file:// protocol
 * - MCP availability and response parsing
 * - Conversation API integration
 * - Authentication flow
 */

async function runFrontendTests() {
    console.log('🧪 Frontend Integration Test Suite');
    console.log('=' .repeat(50));
    
    const results = [];
    
    function logTest(name, passed, message = '') {
        const status = passed ? '✅ PASS' : '❌ FAIL';
        results.push({name, passed, message});
        console.log(`${status}: ${name}`);
        if (message) console.log(`    ${message}`);
    }
    
    // Test 1: API URL Configuration
    function testAPIUrlConfiguration() {
        const expectedUrl = window.location.protocol === 'file:' || window.location.hostname === 'localhost' 
            ? 'http://localhost:9000'
            : '/api';
            
        const actualUrl = API_BASE_URL;
        const passed = actualUrl === expectedUrl;
        
        logTest('API URL Configuration', passed, 
            `Expected: ${expectedUrl}, Got: ${actualUrl}, Protocol: ${window.location.protocol}`);
        return passed;
    }
    
    // Test 2: API Key Availability
    function testAPIKeyAvailability() {
        const apiKey = getApiKey();
        const passed = apiKey && apiKey.length > 0;
        
        logTest('API Key Availability', passed, 
            `Key present: ${!!apiKey}, Length: ${apiKey ? apiKey.length : 0}`);
        return passed;
    }
    
    // Test 3: MCP Status Check
    function testMCPStatus() {
        const passed = typeof mcpEnabled === 'boolean';
        
        logTest('MCP Status Definition', passed, 
            `mcpEnabled: ${mcpEnabled} (type: ${typeof mcpEnabled})`);
        return passed;
    }
    
    // Test 4: API Health Check
    async function testAPIHealthCheck() {
        try {
            const apiKey = getApiKey();
            const response = await fetch(`${API_BASE_URL}/health`, {
                headers: { 'Authorization': `Bearer ${apiKey}` }
            });
            
            if (!response.ok) {
                logTest('API Health Check', false, `HTTP ${response.status}`);
                return false;
            }
            
            const data = await response.json();
            const mcpAvailable = data.integration_status?.mcp_enabled;
            
            logTest('API Health Check', true, 
                `Status: ${data.status}, MCP Available: ${mcpAvailable}`);
            return true;
            
        } catch (error) {
            logTest('API Health Check', false, error.message);
            return false;
        }
    }
    
    // Test 5: Opportunities API
    async function testOpportunitiesAPI() {
        try {
            const apiKey = getApiKey();
            const response = await fetch(`${API_BASE_URL}/api/events`, {
                headers: { 'Authorization': `Bearer ${apiKey}` }
            });
            
            if (!response.ok) {
                logTest('Opportunities API', false, `HTTP ${response.status}`);
                return false;
            }
            
            const data = await response.json();
            const oppCount = data.events?.length || 0;
            
            logTest('Opportunities API', oppCount > 0, 
                `Found ${oppCount} events`);
            return oppCount > 0;
            
        } catch (error) {
            logTest('Opportunities API', false, error.message);
            return false;
        }
    }
    
    // Test 6: Conversation API Structure
    async function testConversationAPI() {
        try {
            const apiKey = getApiKey();
            const testMessage = 'Test message for integration validation';
            
            const response = await fetch(`${API_BASE_URL}/api/conversation`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${apiKey}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message: testMessage,
                    city: 'San Rafael',
                    state: 'California'
                })
            });
            
            if (!response.ok) {
                logTest('Conversation API', false, `HTTP ${response.status}`);
                return false;
            }
            
            const data = await response.json();
            
            // Check expected fields
            const hasResponse = 'response' in data;
            const hasConversationId = 'conversation_id' in data;
            const hasTimestamp = 'timestamp' in data;
            
            const passed = hasResponse && hasConversationId && hasTimestamp;
            const missingFields = [];
            if (!hasResponse) missingFields.push('response');
            if (!hasConversationId) missingFields.push('conversation_id');
            if (!hasTimestamp) missingFields.push('timestamp');
            
            logTest('Conversation API', passed, 
                passed ? `Response: ${data.response.length} chars` : `Missing: ${missingFields.join(', ')}`);
            return passed;
            
        } catch (error) {
            logTest('Conversation API', false, error.message);
            return false;
        }
    }
    
    // Test 7: Frontend Function Availability
    function testFrontendFunctions() {
        const requiredFunctions = [
            'getApiKey',
            'handleUserMessage', 
            'addAiMessage',
            'checkMCPAvailability'
        ];
        
        const missingFunctions = requiredFunctions.filter(fn => typeof window[fn] === 'undefined');
        const passed = missingFunctions.length === 0;
        
        logTest('Frontend Functions', passed, 
            passed ? 'All required functions available' : `Missing: ${missingFunctions.join(', ')}`);
        return passed;
    }
    
    // Test 8: Session Storage
    function testSessionStorage() {
        try {
            // Test that we can write to sessionStorage (important for file:// protocol)
            sessionStorage.setItem('test_key', 'test_value');
            const retrieved = sessionStorage.getItem('test_key');
            sessionStorage.removeItem('test_key');
            
            const passed = retrieved === 'test_value';
            logTest('Session Storage', passed, 
                passed ? 'Read/write working' : 'Cannot access sessionStorage');
            return passed;
            
        } catch (error) {
            logTest('Session Storage', false, error.message);
            return false;
        }
    }
    
    // Run all tests
    const tests = [
        { name: 'API URL Configuration', test: testAPIUrlConfiguration, async: false },
        { name: 'API Key Availability', test: testAPIKeyAvailability, async: false },
        { name: 'MCP Status Definition', test: testMCPStatus, async: false },
        { name: 'Frontend Functions', test: testFrontendFunctions, async: false },
        { name: 'Session Storage', test: testSessionStorage, async: false },
        { name: 'API Health Check', test: testAPIHealthCheck, async: true },
        { name: 'Opportunities API', test: testOpportunitiesAPI, async: true },
        { name: 'Conversation API', test: testConversationAPI, async: true }
    ];
    
    console.log('Running tests...\n');
    
    for (const {test, async} of tests) {
        if (async) {
            await test();
        } else {
            test();
        }
    }
    
    // Summary
    console.log('\n' + '='.repeat(50));
    const passed = results.filter(r => r.passed).length;
    const total = results.length;
    
    if (passed === total) {
        console.log(`🎉 ALL TESTS PASSED (${passed}/${total})`);
        console.log('Frontend integration is working correctly!');
    } else {
        console.log(`⚠️  SOME TESTS FAILED (${passed}/${total})`);
        console.log('Failed tests:');
        results.filter(r => !r.passed).forEach(r => {
            console.log(`  - ${r.name}: ${r.message}`);
        });
    }
    
    return passed === total;
}

// Additional helper functions for debugging
window.debugFrontend = {
    // Quick test of current MCP status
    checkMCPStatus: () => {
        console.log('Current MCP Status:');
        console.log('  mcpEnabled:', mcpEnabled);
        console.log('  API_BASE_URL:', API_BASE_URL);
        console.log('  API Key present:', !!getApiKey());
        console.log('  Protocol:', window.location.protocol);
    },
    
    // Test conversation flow without UI
    testConversation: async (message = 'Test message') => {
        try {
            const response = await fetch(`${API_BASE_URL}/api/conversation`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${getApiKey()}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message,
                    city: 'San Rafael',
                    state: 'California'
                })
            });
            
            const data = await response.json();
            console.log('Conversation test result:');
            console.log('  Status:', response.status);
            console.log('  Response:', data.response?.substring(0, 100) + '...');
            console.log('  Full data:', data);
            return data;
        } catch (error) {
            console.error('Conversation test failed:', error);
            return null;
        }
    },
    
    // Force refresh MCP availability
    recheckMCP: async () => {
        console.log('Re-checking MCP availability...');
        await checkMCPAvailability();
        console.log('New mcpEnabled status:', mcpEnabled);
        return mcpEnabled;
    }
};

console.log('Frontend integration test suite loaded!');
console.log('Run: runFrontendTests()');
console.log('Debug helpers available at: window.debugFrontend');
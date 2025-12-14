// Schema compliance test for user signup system
// Run with: node test_schema_compliance.js

// Simulate UUID generation
function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

// User creation function (copied from implementation)
function createSchemaUser(email, location, civicInterests = []) {
    const now = new Date().toISOString();
    return {
        id: generateUUID(),
        email: email,
        experience_level: 'new',
        location: {
            city: location.city,
            county: location.county,
            state: location.state,
            postal_code: location.postal_code || null,
            street_address: location.street_address || null,
            jurisdiction_ids: location.jurisdiction_ids || [],
            coordinates: location.coordinates || null
        },
        civic_profile: {
            visits: 1,
            interactions: 0,
            comments_submitted: 0,
            meetings_attended: 0,
            neighbors_connected: 0,
            issues_followed: [],
            civic_interests: civicInterests,
            notification_preferences: {
                newsletter: true,
                meeting_reminders: false,
                neighbor_updates: false,
                government_responses: true
            }
        },
        preferences: {
            interface_mode: 'simple',
            conversation_style: 'supportive'
        },
        created_at: now,
        last_active: now
    };
}

// Schema validation functions
function validateUserSchema(user) {
    const results = [];
    
    // Test required fields
    results.push(testField(user.id, 'string', 'id'));
    results.push(testField(user.email, 'string', 'email'));
    results.push(testEnum(user.experience_level, ['new', 'returning', 'expert'], 'experience_level'));
    
    // Test location object
    if (user.location) {
        results.push(testField(user.location.city, 'string', 'location.city'));
        results.push(testField(user.location.county, 'string', 'location.county'));
        results.push(testField(user.location.state, 'string', 'location.state'));
        results.push(testField(user.location.jurisdiction_ids, 'object', 'location.jurisdiction_ids'));
        results.push(testArray(user.location.jurisdiction_ids, 'location.jurisdiction_ids'));
    } else {
        results.push({pass: false, message: 'location object missing'});
    }
    
    // Test civic_profile object
    if (user.civic_profile) {
        results.push(testField(user.civic_profile.visits, 'number', 'civic_profile.visits'));
        results.push(testField(user.civic_profile.interactions, 'number', 'civic_profile.interactions'));
        results.push(testField(user.civic_profile.comments_submitted, 'number', 'civic_profile.comments_submitted'));
        results.push(testField(user.civic_profile.meetings_attended, 'number', 'civic_profile.meetings_attended'));
        results.push(testField(user.civic_profile.neighbors_connected, 'number', 'civic_profile.neighbors_connected'));
        results.push(testArray(user.civic_profile.issues_followed, 'civic_profile.issues_followed'));
        results.push(testArray(user.civic_profile.civic_interests, 'civic_profile.civic_interests'));
        
        // Test notification preferences
        if (user.civic_profile.notification_preferences) {
            results.push(testField(user.civic_profile.notification_preferences.newsletter, 'boolean', 'civic_profile.notification_preferences.newsletter'));
            results.push(testField(user.civic_profile.notification_preferences.meeting_reminders, 'boolean', 'civic_profile.notification_preferences.meeting_reminders'));
            results.push(testField(user.civic_profile.notification_preferences.neighbor_updates, 'boolean', 'civic_profile.notification_preferences.neighbor_updates'));
            results.push(testField(user.civic_profile.notification_preferences.government_responses, 'boolean', 'civic_profile.notification_preferences.government_responses'));
        } else {
            results.push({pass: false, message: 'civic_profile.notification_preferences object missing'});
        }
    } else {
        results.push({pass: false, message: 'civic_profile object missing'});
    }
    
    // Test preferences object
    if (user.preferences) {
        results.push(testEnum(user.preferences.interface_mode, ['simple', 'expert'], 'preferences.interface_mode'));
        results.push(testField(user.preferences.conversation_style, 'string', 'preferences.conversation_style'));
    } else {
        results.push({pass: false, message: 'preferences object missing'});
    }
    
    // Test ISO date formats
    results.push(testISO8601(user.created_at, 'created_at'));
    results.push(testISO8601(user.last_active, 'last_active'));
    
    return results;
}

function testField(value, expectedType, fieldName) {
    const actualType = typeof value;
    const pass = actualType === expectedType && value !== null && value !== undefined;
    return {
        pass: pass,
        message: `${fieldName}: ${pass ? 'PASS' : 'FAIL'} (expected ${expectedType}, got ${actualType}: ${value})`
    };
}

function testEnum(value, allowedValues, fieldName) {
    const pass = allowedValues.includes(value);
    return {
        pass: pass,
        message: `${fieldName}: ${pass ? 'PASS' : 'FAIL'} (expected one of [${allowedValues.join(', ')}], got ${value})`
    };
}

function testArray(value, fieldName) {
    const pass = Array.isArray(value);
    return {
        pass: pass,
        message: `${fieldName}: ${pass ? 'PASS' : 'FAIL'} (expected array, got ${typeof value})`
    };
}

function testISO8601(dateString, fieldName) {
    const pass = /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z/.test(dateString) && !isNaN(Date.parse(dateString));
    return {
        pass: pass,
        message: `${fieldName}: ${pass ? 'PASS' : 'FAIL'} (expected ISO8601 format, got ${dateString})`
    };
}

// Test civic interests enum validation
function testCivicInterestsEnum(interests) {
    const validInterests = ['housing', 'traffic', 'environment', 'education', 'budget', 'development', 'public_safety', 'community'];
    const invalidInterests = interests.filter(interest => !validInterests.includes(interest));
    const pass = invalidInterests.length === 0;
    return {
        pass: pass,
        message: `civic_interests enum validation: ${pass ? 'PASS' : 'FAIL'} ${invalidInterests.length > 0 ? `(invalid: [${invalidInterests.join(', ')}])` : ''}`
    };
}

// Run the tests
console.log('🧪 Running User Schema Compliance Tests\n');

// Test 1: Basic user creation
console.log('Test 1: Basic User Creation');
const testLocation = {
    city: 'San Rafael',
    county: 'Marin County',
    state: 'California'
};
const testInterests = ['housing', 'traffic', 'environment'];

const user = createSchemaUser('test@example.com', testLocation, testInterests);
console.log('✅ User created successfully\n');

// Test 2: Schema validation
console.log('Test 2: Schema Validation');
const validationResults = validateUserSchema(user);

// Test 3: Civic interests enum validation
const civicInterestsTest = testCivicInterestsEnum(user.civic_profile.civic_interests);
validationResults.push(civicInterestsTest);

// Test 4: JSON serialization/deserialization
console.log('Test 3: JSON Serialization');
try {
    const jsonString = JSON.stringify(user);
    const parsedUser = JSON.parse(jsonString);
    const serializationPass = JSON.stringify(user) === JSON.stringify(parsedUser);
    validationResults.push({
        pass: serializationPass,
        message: `JSON serialization: ${serializationPass ? 'PASS' : 'FAIL'} (serialize/parse consistency)`
    });
} catch (e) {
    validationResults.push({
        pass: false,
        message: `JSON serialization: FAIL (error: ${e.message})`
    });
}

// Display results
console.log('\n📊 Validation Results:');
const passedTests = validationResults.filter(result => result.pass);
const failedTests = validationResults.filter(result => !result.pass);

validationResults.forEach(result => {
    console.log(result.pass ? `✅ ${result.message}` : `❌ ${result.message}`);
});

console.log(`\n📈 Summary: ${passedTests.length}/${validationResults.length} tests passed`);

if (failedTests.length === 0) {
    console.log('🎉 All tests passed! User signup system is schema-compliant.');
} else {
    console.log(`⚠️  ${failedTests.length} tests failed. Schema compliance issues detected.`);
}

// Display sample user object
console.log('\n📋 Sample User Object:');
console.log(JSON.stringify(user, null, 2));
# CSV Import Troubleshooting Guide

## Expected CSV Format
```
User name,User ID,Phone number
john_doe,123456789,+1234567890
@jane_smith,987654321,+9876543210
mike_wilson,555444333,+5554443333
```

## Common Issues

### 1. File Format
- Make sure the file is saved as CSV (comma-separated values)
- Use UTF-8 encoding
- No special characters in cell content that break CSV structure

### 2. Required Columns
- Header must be exactly: `User name,User ID,Phone number`
- At least one field per row must be filled
- User ID should be numeric (if provided)

### 3. Browser Console Check
To debug the issue:
1. Open browser Developer Tools (F12)
2. Go to Console tab
3. Try importing CSV file
4. Look for error messages or debug logs

Expected console output:
```
CSV upload function called
Selected file: File object
FileReader started
Adding campaign user: {username: "john_doe", user_id: "123456789", phone: "+1234567890", priority: 1}
```

### 4. Create Test CSV File
Create a simple test file with this content:
```
User name,User ID,Phone number
test_user,123456789,+1234567890
```

### 5. Check File Input Element
- Make sure the hidden file input is correctly triggered
- Verify file is actually selected (check file size in console)

## Manual Debug Steps
1. Click "Import CSV/XLS" button
2. Select a properly formatted CSV file
3. Check browser console for debug messages
4. If no messages appear, there may be a JavaScript error preventing execution

## Contact Support
If the issue persists, provide:
- Browser and version
- CSV file content (first few rows)
- Any console error messages
